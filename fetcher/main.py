#!/usr/bin/env python3
"""
Fetcher CLI Entry Point

Command-line interface for RSV data ingestion and daemon management.

Usage:
    # Daily ingestion (fetch yesterday's data)
    python main.py --daily

    # Manual ingestion (specify date)
    python main.py --manual --date 2025-11-01

    # Daemon mode (automated scheduler)
    python main.py --daemon

    # Initial backfill (fetch last 90 days)
    python main.py --backfill-initial

Per spec.md:
- FR-001: Manual and automated ingestion modes
- FR-002: Daily scheduler at 07:30 ICT
- FR-003: Graceful daemon management

Constitution alignment:
- Principle VI: Clarity Over Cleverness - Simple CLI with clear flags
- Principle VIII: Observability - Structured logging throughout
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import date, timedelta, datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lib.db import init_database, DatabaseConnection
from lib.db_operations import DBOperations
from lib.logging_utils import setup_logging
from services.ingestion import IngestionService
from services.scheduler import SchedulerService
from lib.timezone_utils import now_ict

logger = logging.getLogger(__name__)


def parse_args():
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="RSV Data Fetcher - Google Trends ingestion for Chiang Mai",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch yesterday's data
  python main.py --daily

  # Fetch specific date
  python main.py --manual --date 2025-11-01

  # Run scheduler daemon (07:30 ICT daily)
  python main.py --daemon

  # Initial backfill (last 90 days)
  python main.py --backfill-initial

  # Custom database path
  python main.py --daily --db /path/to/custom.db

  # Debug logging
  python main.py --daily --log-level DEBUG
        """
    )

    # Execution mode (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--daily',
        action='store_true',
        help='Run daily ingestion (fetch yesterday\'s data)'
    )
    mode_group.add_argument(
        '--manual',
        action='store_true',
        help='Run manual ingestion (requires --date)'
    )
    mode_group.add_argument(
        '--daemon',
        action='store_true',
        help='Run scheduler daemon (07:30 ICT daily with ±2 min jitter)'
    )
    mode_group.add_argument(
        '--backfill-initial',
        action='store_true',
        help='Run initial backfill (last 90 days, for first-time setup)'
    )

    # Optional arguments
    parser.add_argument(
        '--date',
        type=str,
        help='Target date for manual ingestion (format: YYYY-MM-DD)'
    )
    parser.add_argument(
        '--db',
        type=str,
        default='data/rsv_trends.db',
        help='Database file path (default: data/rsv_trends.db)'
    )
    parser.add_argument(
        '--schema',
        type=str,
        default='schema.sql',
        help='Schema file path (default: schema.sql)'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )
    parser.add_argument(
        '--schedule-time',
        type=str,
        default='07:30',
        help='Daily schedule time in HH:MM format (default: 07:30, only for --daemon)'
    )

    return parser.parse_args()


def validate_args(args):
    """
    Validate argument combinations.

    Args:
        args: Parsed arguments namespace

    Raises:
        SystemExit: If validation fails
    """
    # Manual mode requires --date
    if args.manual and not args.date:
        logger.error("--manual mode requires --date argument")
        sys.exit(1)

    # Validate date format
    if args.date:
        try:
            datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Expected YYYY-MM-DD")
            sys.exit(1)


def run_daily(db_path: str, schema_path: str):
    """
    Run daily ingestion (fetch yesterday's data).

    Args:
        db_path: Database file path
        schema_path: Schema file path
    """
    logger.info("=== DAILY INGESTION MODE ===")

    db = None
    try:
        # Initialize database
        db = init_database(schema_path, db_path)

        # Run ingestion
        ingestion_service = IngestionService(db)
        batch_event = ingestion_service.ingest_daily(batch_type='daily')

        # Log results
        logger.info(
            f"Daily ingestion complete: batch_id={batch_event.batch_id}, "
            f"status={batch_event.status}, rows_written={batch_event.rows_written}, "
            f"rows_updated={batch_event.rows_updated}, duration={batch_event.duration_seconds():.1f}s"
        )

        if batch_event.status == 'success':
            logger.info("✅ Daily ingestion successful")
            return 0
        elif batch_event.status == 'degraded':
            logger.warning(f"⚠️  Daily ingestion degraded: {batch_event.notes}")
            return 0  # Still exit 0 for partial success
        else:
            logger.error(f"❌ Daily ingestion failed: {batch_event.error_message}")
            return 1
    finally:
        if db:
            db.close()
            logger.debug("Database connection closed")


def run_manual(db_path: str, schema_path: str, target_date_str: str):
    """
    Run manual ingestion for specific date.

    Args:
        db_path: Database file path
        schema_path: Schema file path
        target_date_str: Target date string (YYYY-MM-DD)
    """
    logger.info(f"=== MANUAL INGESTION MODE (date={target_date_str}) ===")

    db = None
    try:
        # Parse date
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()

        # Initialize database
        db = init_database(schema_path, db_path)

        # Run ingestion
        ingestion_service = IngestionService(db)
        batch_event = ingestion_service.ingest_daily(target_date=target_date, batch_type='manual')

        # Log results
        logger.info(
            f"Manual ingestion complete: batch_id={batch_event.batch_id}, "
            f"status={batch_event.status}, rows_written={batch_event.rows_written}, "
            f"duration={batch_event.duration_seconds():.1f}s"
        )

        if batch_event.status == 'success':
            logger.info("✅ Manual ingestion successful")
            return 0
        elif batch_event.status == 'degraded':
            logger.warning(f"⚠️  Manual ingestion degraded: {batch_event.notes}")
            return 0
        else:
            logger.error(f"❌ Manual ingestion failed: {batch_event.error_message}")
            return 1
    finally:
        if db:
            db.close()
            logger.debug("Database connection closed")


def run_daemon(db_path: str, schema_path: str, schedule_time: str):
    """
    Run scheduler daemon (blocking).

    Args:
        db_path: Database file path
        schema_path: Schema file path
        schedule_time: Daily schedule time (HH:MM)
    """
    import signal

    logger.info(f"=== DAEMON MODE (schedule={schedule_time} ICT) ===")

    db = None
    scheduler_service = None

    def signal_handler(signum, frame):
        """Handle SIGTERM and SIGINT for graceful shutdown."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        if scheduler_service:
            scheduler_service.stop()
        if db:
            db.close()
            logger.debug("Database connection closed")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Initialize database
        db = init_database(schema_path, db_path)

        # Start scheduler
        scheduler_service = SchedulerService(db, schedule_time=schedule_time)
        scheduler_service.run()  # Blocking
    finally:
        if db:
            db.close()
            logger.debug("Database connection closed")


def run_backfill_initial(db_path: str, schema_path: str):
    """
    Run initial backfill (last 90 days).

    Args:
        db_path: Database file path
        schema_path: Schema file path
    """
    logger.info("=== INITIAL BACKFILL MODE (last 90 days) ===")

    db = None
    try:
        # Initialize database
        db = init_database(schema_path, db_path)
        db_ops = DBOperations(db)

        # Check if database is empty
        if not db_ops.is_database_empty():
            logger.warning(
                "Database already contains data. Initial backfill should only be run once. "
                "Use --manual for targeted backfills."
            )
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                logger.info("Backfill cancelled")
                return 0

        # Run backfill
        ingestion_service = IngestionService(db)
        batch_event = ingestion_service.ingest_initial_backfill()

        # Log results
        logger.info(
            f"Initial backfill complete: batch_id={batch_event.batch_id}, "
            f"status={batch_event.status}, rows_written={batch_event.rows_written}, "
            f"duration={batch_event.duration_seconds():.1f}s"
        )

        if batch_event.status == 'success':
            logger.info("✅ Initial backfill successful")
            return 0
        elif batch_event.status == 'degraded':
            logger.warning(f"⚠️  Initial backfill degraded: {batch_event.notes}")
            return 0
        else:
            logger.error(f"❌ Initial backfill failed: {batch_event.error_message}")
            return 1
    finally:
        if db:
            db.close()
            logger.debug("Database connection closed")


def main():
    """
    Main entry point.
    """
    # Parse and validate arguments
    args = parse_args()
    validate_args(args)

    # Setup logging
    log_level = getattr(logging, args.log_level)
    setup_logging(level=log_level)

    logger.info(f"RSV Fetcher started: {now_ict().strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # Route to appropriate handler
    try:
        if args.daily:
            sys.exit(run_daily(args.db, args.schema))
        elif args.manual:
            sys.exit(run_manual(args.db, args.schema, args.date))
        elif args.daemon:
            run_daemon(args.db, args.schema, args.schedule_time)  # Never returns
        elif args.backfill_initial:
            sys.exit(run_backfill_initial(args.db, args.schema))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
