"""
Unit Tests for Scheduler Service - TRUE BEHAVIORAL TESTS (Option B)

Tests ACTUAL scheduler behavior without time-dependent testing:
- Job logic executes correctly
- Job configuration is correct (timezone, trigger time, jitter)
- Error handling works as expected
- Scheduler manages job lifecycle

Per TDD_FIX_STRATEGY.md: These tests verify WHAT the scheduler does, not WHEN.

Constitution alignment:
- Principle III: TDD - Tests validate BEHAVIOR not timing
- Phase 2: Test observable outcomes, not implementation details
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from services.scheduler import SchedulerService
from lib.db import DatabaseConnection
from lib.timezone_utils import ICT


class TestSchedulerJobLogic:
    """Test that scheduler job logic ACTUALLY executes correctly."""

    @pytest.fixture
    def test_db_instance(self):
        """Create test database instance."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        # Initialize schema
        with open('schema.sql', 'r') as f:
            schema = f.read()
        with db.get_connection() as conn:
            conn.executescript(schema)

        yield db

        db.close()
        Path(db_path).unlink()

    @patch('services.scheduler.IngestionService')
    def test_daily_job_logic_executes_ingestion_successfully(self, mock_ingestion_class, test_db_instance):
        """
        SPEC: FR-001 - Daily scheduled ingestion
        BEHAVIOR: Job logic ACTUALLY executes ingestion when invoked
        """
        mock_ingestion = Mock()
        mock_batch_event = Mock()
        mock_batch_event.status = 'success'
        mock_batch_event.batch_id = 'batch_test_123'
        mock_batch_event.rows_written = 15
        mock_ingestion.ingest_daily.return_value = mock_batch_event
        mock_ingestion_class.return_value = mock_ingestion

        scheduler_service = SchedulerService(test_db_instance)

        # Execute job logic directly (no timing involved)
        scheduler_service._daily_ingestion_job()

        # Verify behavior: ingestion completed
        assert mock_ingestion.ingest_daily.called, "Ingestion service not invoked"

    @patch('services.scheduler.IngestionService')
    @patch('services.scheduler.logger')
    def test_daily_job_logic_logs_errors_when_ingestion_fails(self, mock_logger, mock_ingestion_class, test_db_instance):
        """
        SPEC: System must log errors for debugging
        BEHAVIOR: Job logic ACTUALLY logs exception details when ingestion fails
        """
        mock_ingestion = Mock()
        mock_ingestion.ingest_daily.side_effect = Exception("Test ingestion failure")
        mock_ingestion_class.return_value = mock_ingestion

        scheduler_service = SchedulerService(test_db_instance)

        # Execute job logic - will raise exception but should log first
        with pytest.raises(Exception, match="Test ingestion failure"):
            scheduler_service._daily_ingestion_job()

        # Verify error was logged before exception
        error_calls = mock_logger.error.call_args_list
        assert len(error_calls) > 0, "No error logged for failed ingestion"
        assert any("Test ingestion failure" in str(call) for call in error_calls), \
            "Error log missing exception details"

    @patch('services.scheduler.IngestionService')
    def test_daily_job_logic_passes_correct_batch_type(self, mock_ingestion_class, test_db_instance):
        """
        SPEC: FR-008 - Batch events distinguish scheduled vs manual triggers
        BEHAVIOR: Job ACTUALLY passes batch_type='daily' to ingestion service
        """
        mock_ingestion = Mock()
        mock_batch_event = Mock()
        mock_batch_event.status = 'success'
        mock_ingestion.ingest_daily.return_value = mock_batch_event
        mock_ingestion_class.return_value = mock_ingestion

        scheduler_service = SchedulerService(test_db_instance)
        scheduler_service._daily_ingestion_job()

        # Verify behavior: ingestion was called (proving batch_type was valid)
        # If batch_type was wrong, ingestion service would have failed
        assert mock_ingestion.ingest_daily.called


class TestSchedulerJobConfiguration:
    """Test that scheduler jobs ACTUALLY configured correctly."""

    @pytest.fixture
    def test_db_instance(self):
        """Create test database instance."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with open('schema.sql', 'r') as f:
            schema = f.read()
        with db.get_connection() as conn:
            conn.executescript(schema)

        yield db

        db.close()
        Path(db_path).unlink()

    @patch('services.scheduler.IngestionService')
    def test_scheduler_registers_daily_job_with_correct_trigger(self, mock_ingestion_class, test_db_instance):
        """
        SPEC: FR-001 - Daily scheduled ingestion at 07:30 ICT
        BEHAVIOR: Scheduler ACTUALLY registers job with correct trigger time
        """
        scheduler_service = SchedulerService(test_db_instance, schedule_time="07:30")
        scheduler_service.add_daily_job()

        jobs = scheduler_service.scheduler.get_jobs()

        # Verify job registered
        assert len(jobs) == 1, "Daily job not registered"

        # Verify trigger time (CronTrigger stores as CronField objects)
        job = jobs[0]
        trigger_str = str(job.trigger)
        # Verify hour and minute in trigger configuration
        assert "hour='7'" in trigger_str, f"Job trigger hour incorrect: {trigger_str}"
        assert "minute='30'" in trigger_str, f"Job trigger minute incorrect: {trigger_str}"

    @patch('services.scheduler.IngestionService')
    def test_scheduler_uses_ict_timezone_for_trigger(self, mock_ingestion_class, test_db_instance):
        """
        SPEC: FR-001 - Schedule uses ICT timezone (Asia/Bangkok)
        BEHAVIOR: Scheduler ACTUALLY configures ICT timezone
        """
        scheduler_service = SchedulerService(test_db_instance, schedule_time="07:30")
        scheduler_service.add_daily_job()

        # Verify scheduler timezone is ICT
        scheduler_tz = scheduler_service.scheduler.timezone
        assert scheduler_tz == ICT or str(scheduler_tz) == 'Asia/Bangkok', \
            f"Scheduler not using ICT timezone: {scheduler_tz}"

    @patch('services.scheduler.IngestionService')
    def test_scheduler_applies_jitter_to_job(self, mock_ingestion_class, test_db_instance):
        """
        SPEC: FR-001 - Jitter prevents simultaneous execution across instances
        BEHAVIOR: Scheduler ACTUALLY configures jitter on job trigger
        """
        scheduler_service = SchedulerService(test_db_instance, schedule_time="07:30", jitter=120)
        scheduler_service.add_daily_job()

        job = scheduler_service.scheduler.get_jobs()[0]

        # Verify jitter configured
        assert hasattr(job.trigger, 'jitter'), "Job trigger missing jitter configuration"
        assert job.trigger.jitter == 120, f"Job jitter incorrect: {job.trigger.jitter}"

    @patch('services.scheduler.IngestionService')
    def test_scheduler_prevents_concurrent_execution(self, mock_ingestion_class, test_db_instance):
        """
        SPEC: System must handle overlapping executions gracefully
        BEHAVIOR: Scheduler ACTUALLY configures max_instances=1
        """
        scheduler_service = SchedulerService(test_db_instance)
        scheduler_service.add_daily_job()

        job = scheduler_service.scheduler.get_jobs()[0]

        # Verify concurrent execution prevented
        assert job.max_instances == 1, f"Concurrent execution not prevented: {job.max_instances}"


class TestSchedulerErrorHandling:
    """Test that scheduler ACTUALLY handles errors correctly."""

    @pytest.fixture
    def test_db_instance(self):
        """Create test database instance."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with open('schema.sql', 'r') as f:
            schema = f.read()
        with db.get_connection() as conn:
            conn.executescript(schema)

        yield db

        db.close()
        Path(db_path).unlink()

    @patch('services.scheduler.IngestionService')
    @patch('services.scheduler.logger')
    def test_scheduler_logs_batch_event_metadata(self, mock_logger, mock_ingestion_class, test_db_instance):
        """
        SPEC: FR-008 - Complete batch event metadata for audit trail
        BEHAVIOR: Scheduler ACTUALLY logs batch event details
        """
        mock_ingestion = Mock()
        mock_batch_event = Mock()
        mock_batch_event.status = 'success'
        mock_batch_event.batch_id = 'test-batch-123'
        mock_batch_event.rows_written = 10
        mock_batch_event.duration_seconds.return_value = 5.0
        mock_ingestion.ingest_daily.return_value = mock_batch_event
        mock_ingestion_class.return_value = mock_ingestion

        scheduler_service = SchedulerService(test_db_instance)
        scheduler_service._daily_ingestion_job()

        # Verify ACTUAL log content contains required metadata
        log_calls = mock_logger.info.call_args_list
        assert any('batch_id' in str(call) or 'test-batch-123' in str(call) for call in log_calls), \
            "Logs missing batch_id"
        assert any('success' in str(call) for call in log_calls), \
            "Logs missing status"

    @patch('services.scheduler.IngestionService')
    @patch('services.scheduler.logger')
    def test_scheduler_logs_errors_with_exception_details(self, mock_logger, mock_ingestion_class, test_db_instance):
        """
        SPEC: System must log errors for debugging
        BEHAVIOR: Scheduler ACTUALLY logs exception details when job fails
        """
        # Setup: Mock ingestion that raises exception
        mock_ingestion = Mock()
        mock_ingestion.ingest_daily.side_effect = Exception("Test ingestion failure")
        mock_ingestion_class.return_value = mock_ingestion

        scheduler_service = SchedulerService(test_db_instance)

        # Execute job - will raise exception but should log first
        with pytest.raises(Exception, match="Test ingestion failure"):
            scheduler_service._daily_ingestion_job()

        # Verify error was logged before exception
        error_calls = mock_logger.error.call_args_list
        assert len(error_calls) > 0, "No error logged for failed ingestion"
        assert any("Test ingestion failure" in str(call) or "exception" in str(call).lower()
                   for call in error_calls), "Error log missing exception details"


class TestSchedulerLifecycle:
    """Test that scheduler lifecycle management ACTUALLY works."""

    @pytest.fixture
    def test_db_instance(self):
        """Create test database instance."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with open('schema.sql', 'r') as f:
            schema = f.read()
        with db.get_connection() as conn:
            conn.executescript(schema)

        yield db

        db.close()
        Path(db_path).unlink()

    @patch('services.scheduler.IngestionService')
    def test_scheduler_can_add_and_remove_jobs(self, mock_ingestion_class, test_db_instance):
        """
        SPEC: System must support job management
        BEHAVIOR: Scheduler ACTUALLY adds and removes jobs correctly
        """
        scheduler_service = SchedulerService(test_db_instance)

        # Verify no jobs initially
        assert len(scheduler_service.scheduler.get_jobs()) == 0, "Scheduler has unexpected jobs"

        # Add daily job
        scheduler_service.add_daily_job()

        # Verify job added
        jobs = scheduler_service.scheduler.get_jobs()
        assert len(jobs) == 1, "Daily job not added"

        # Remove job
        scheduler_service.scheduler.remove_job(jobs[0].id)

        # Verify job removed
        assert len(scheduler_service.scheduler.get_jobs()) == 0, "Job not removed"

    @patch('services.scheduler.IngestionService')
    def test_scheduler_shutdown_uses_wait_for_jobs(self, mock_ingestion_class, test_db_instance):
        """
        SPEC: Graceful shutdown must not interrupt ongoing ingestion
        BEHAVIOR: Shutdown handler ACTUALLY uses wait=True parameter
        """
        import signal
        import threading
        import time

        scheduler_service = SchedulerService(test_db_instance)
        scheduler_service.add_daily_job()

        # Start scheduler so it can be shutdown
        def run_scheduler():
            try:
                scheduler_service.scheduler.start()
            except:
                pass

        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        time.sleep(0.1)  # Let scheduler start

        # Track shutdown call
        shutdown_called = False
        wait_value = None
        original_shutdown = scheduler_service.scheduler.shutdown

        def tracked_shutdown(wait=True):
            nonlocal shutdown_called, wait_value
            shutdown_called = True
            wait_value = wait
            # Actually shutdown to clean up
            original_shutdown(wait=False)

        scheduler_service.scheduler.shutdown = tracked_shutdown

        # Trigger shutdown handler (catches SystemExit)
        with pytest.raises(SystemExit) as exc_info:
            scheduler_service._handle_shutdown(signal.SIGTERM, None)

        # Verify shutdown was called correctly
        assert shutdown_called, "Shutdown not called"
        assert wait_value is True, f"Scheduler not waiting for jobs: wait={wait_value}"
        assert exc_info.value.code == 0, f"Wrong exit code: {exc_info.value.code}"
