"""
Scheduler Service

APScheduler configuration for automated daily RSV data ingestion.

Per spec.md FR-002: Daily automated execution at 07:30 ICT (± 2 min jitter)
Per spec.md FR-003: Graceful daemon management with SIGTERM support

Constitution alignment:
- Principle III: Pragmatic Defaults - 07:30 ICT for reliable data availability
- Principle VIII: Observability - Structured logging for all scheduled jobs
"""

import logging
import signal
import sys
from datetime import datetime, time
from typing import Optional
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from zoneinfo import ZoneInfo

from lib.db import DatabaseConnection
from lib.db_operations import DBOperations
from lib.timezone_utils import ICT
from services.ingestion import IngestionService
from services.trends_fetcher import TrendsFetcher
from lib.logging_utils import log_batch_event

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Automated daily RSV data ingestion scheduler.

    Handles:
    - Daily cron job at 07:30 ICT with jitter
    - Graceful shutdown on SIGTERM
    - Job execution monitoring and logging
    - Error handling and recovery
    """

    def __init__(
        self,
        db: DatabaseConnection,
        schedule_time: str = "07:30",
        jitter: int = 120  # ± 2 minutes in seconds
    ):
        """
        Initialize scheduler service.

        Args:
            db: DatabaseConnection instance
            schedule_time: Daily execution time in HH:MM format (default: "07:30")
            jitter: Random jitter in seconds (default: 120 = ±2 minutes)

        Raises:
            ValueError: If schedule_time format is invalid
        """
        self.db = db
        self.jitter = jitter

        # Parse schedule time
        try:
            hour, minute = schedule_time.split(":")
            self.schedule_hour = int(hour)
            self.schedule_minute = int(minute)
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid schedule_time format: {schedule_time}. Expected HH:MM")

        # Initialize services
        self.db_ops = DBOperations(db)
        self.trends_fetcher = TrendsFetcher()
        self.ingestion_service = IngestionService(db)

        # Initialize APScheduler (BlockingScheduler for daemon mode)
        self.scheduler = BlockingScheduler(timezone=ICT)

        # Configure signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        # Job listeners for monitoring
        self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)

        logger.info(
            f"SchedulerService initialized: schedule={schedule_time} ICT, jitter=±{jitter}s"
        )

    def _handle_shutdown(self, signum, frame):
        """
        Handle shutdown signals (SIGTERM, SIGINT).

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")

        # Shutdown scheduler
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)

        logger.info("Scheduler shutdown complete")
        sys.exit(0)

    def _job_executed(self, event):
        """
        Handle successful job execution.

        Args:
            event: APScheduler job execution event
        """
        logger.info(
            f"Scheduled job executed successfully: job_id={event.job_id}, "
            f"run_time={event.scheduled_run_time}"
        )

    def _job_error(self, event):
        """
        Handle job execution errors.

        Args:
            event: APScheduler job error event
        """
        logger.error(
            f"Scheduled job failed: job_id={event.job_id}, "
            f"exception={event.exception}",
            exc_info=True
        )

    def _daily_ingestion_job(self):
        """
        Scheduled job: Daily RSV data ingestion.

        Fetches yesterday's RSV data and persists to database.
        Logs batch event with complete metadata.
        """
        logger.info("Starting scheduled daily ingestion job")

        try:
            # Run daily ingestion (fetches yesterday's data by default)
            batch_event = self.ingestion_service.ingest_daily(batch_type='daily')

            # Log success
            log_batch_event(
                logger,
                'info',
                'Scheduled daily ingestion complete',
                batch_id=batch_event.batch_id,
                status=batch_event.status,
                rows_written=batch_event.rows_written,
                rows_updated=batch_event.rows_updated,
                duration_seconds=batch_event.duration_seconds()
            )

        except Exception as e:
            logger.error(
                f"Scheduled daily ingestion failed: {e}",
                exc_info=True,
                extra={'batch_type': 'daily', 'error': str(e)}
            )
            raise

    def add_daily_job(self):
        """
        Add daily ingestion job to scheduler.

        Configures cron trigger for execution at configured time with jitter.
        """
        self.scheduler.add_job(
            func=self._daily_ingestion_job,
            trigger=CronTrigger(
                hour=self.schedule_hour,
                minute=self.schedule_minute,
                timezone=ICT,
                jitter=self.jitter
            ),
            id='daily_rsv_ingestion',
            name='Daily RSV Data Ingestion',
            replace_existing=True,
            max_instances=1,  # Prevent concurrent executions
            misfire_grace_time=3600  # Allow 1 hour grace for missed jobs
        )

        logger.info(
            f"Daily ingestion job scheduled: {self.schedule_hour:02d}:{self.schedule_minute:02d} ICT "
            f"(±{self.jitter}s jitter)"
        )

    def run(self):
        """
        Start scheduler in daemon mode (blocking).

        Runs until SIGTERM/SIGINT received.
        """
        logger.info("Starting scheduler daemon...")

        # Add daily job
        self.add_daily_job()

        # Print next run time
        next_run = self.scheduler.get_jobs()[0].next_run_time
        logger.info(f"Next scheduled run: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # Start scheduler (blocking)
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler interrupted, shutting down...")
