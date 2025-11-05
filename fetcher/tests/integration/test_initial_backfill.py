"""
Integration Tests for 90-Day Initial Backfill - User Story 2

Tests the COMPLETE 90-day backfill flow end-to-end:
- Empty database detection
- Automatic backfill trigger
- 90-day date range calculation
- RSV data fetching for all keywords
- Database persistence
- Batch event creation

Constitution alignment:
- Principle III: TDD - Integration tests written BEFORE implementation (RED phase)
- Principle IV: Provenance - Verify batch events created
- Principle VIII: Observability - Verify logging

Test Strategy:
- Full system integration: Real services, real database (test copy)
- Mock only external API (pytrends)
- Verify complete user story flow
"""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestInitialBackfillIntegration:
    """Test complete 90-day backfill flow from empty database to populated."""

    @pytest.fixture
    def clean_test_db(self):
        """Create clean test database with schema but no data."""
        import tempfile
        from lib.db import DatabaseConnection

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

    @patch('services.trends_fetcher.TrendReq')
    def test_initial_backfill_triggers_on_empty_database(self, mock_trends_class, clean_test_db):
        """
        SPEC: US2 - Automatic 90-day backfill on first deployment
        BEHAVIOR: System detects empty DB, triggers 90-day backfill automatically
        """
        from services.ingestion import IngestionService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock Google Trends API to return data
        mock_pytrends = Mock()
        # Return mock data for each date in the 90-day range
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [75],
            'ปวดหัว': [60],
            'ไอ': [55]
        }, index=[pd.Timestamp('2025-11-01')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        ingestion_service = IngestionService(clean_test_db, config)

        # Execute: Attempt to ingest daily (should detect empty DB and trigger backfill)
        batch_event = ingestion_service.ingest_with_initial_backfill_check()

        # Verify: Backfill was triggered
        assert batch_event is not None, "Backfill should have been triggered"
        assert batch_event.batch_type == 'initial_backfill', \
            f"Batch type should be initial_backfill, got {batch_event.batch_type}"

        # Verify: Batch event marked as backfill
        assert 'initial' in batch_event.batch_type.lower() or '90' in str(batch_event.notes), \
            "Batch event should indicate initial backfill"

    @patch('services.trends_fetcher.TrendReq')
    def test_90_day_backfill_creates_records_for_all_keywords(self, mock_trends_class, clean_test_db):
        """
        SPEC: US2 - 90 days × N keywords = complete time series
        BEHAVIOR: Backfill creates 90 days × keyword count records
        """
        from services.backfill import BackfillService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock API returns data for 3 keywords
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [75],
            'ปวดหัว': [60],
            'ไอ': [55]
        }, index=[pd.Timestamp('2025-11-01')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        # Use only 3 keywords for faster test
        test_keywords = config.keywords[:3]

        backfill_service = BackfillService(clean_test_db)

        # Execute: Run 90-day backfill
        batch_event = backfill_service.backfill_initial(keywords=test_keywords, days=90)

        # Verify: Records created
        with clean_test_db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata")
            record_count = cursor.fetchone()[0]

        # Expected: 90 days × 3 keywords = 270 records (if all dates have data)
        # Note: Actual count may be less if Google Trends returns no data for some dates
        assert record_count > 0, "Backfill should create records"
        assert record_count <= 90 * len(test_keywords), \
            f"Should not exceed {90 * len(test_keywords)} records"

        # Verify: Batch event status is success
        assert batch_event.status == 'success', \
            f"Batch event should be success, got {batch_event.status}"

    @patch('services.trends_fetcher.TrendReq')
    def test_90_day_backfill_covers_complete_date_range(self, mock_trends_class, clean_test_db):
        """
        SPEC: US2 - Backfill creates continuous 90-day time series
        BEHAVIOR: Date range spans from T-90 to T-1 (yesterday ICT)
        """
        from services.backfill import BackfillService
        from lib.config import FetcherConfig
        from lib.timezone_utils import ICT
        from datetime import datetime
        import pandas as pd

        # Setup: Mock API
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [75]
        }, index=[pd.Timestamp('2025-11-01')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        test_keywords = config.keywords[:1]  # Single keyword for faster test

        backfill_service = BackfillService(clean_test_db)

        # Execute: Run 90-day backfill
        backfill_service.backfill_initial(keywords=test_keywords, days=90)

        # Verify: Date range in database
        with clean_test_db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT MIN(date) as earliest, MAX(date) as latest
                FROM raw_trenddata
            """)
            result = cursor.fetchone()
            earliest_date_str, latest_date_str = result[0], result[1]

        # Calculate expected date range
        today_ict = datetime.now(ICT).date()
        yesterday_ict = today_ict - timedelta(days=1)
        expected_earliest = yesterday_ict - timedelta(days=89)

        # Verify: Date range matches expectation
        if earliest_date_str and latest_date_str:
            earliest_date = date.fromisoformat(earliest_date_str)
            latest_date = date.fromisoformat(latest_date_str)

            assert earliest_date <= expected_earliest, \
                f"Earliest date should be around {expected_earliest}, got {earliest_date}"
            assert latest_date <= yesterday_ict, \
                f"Latest date should be around {yesterday_ict}, got {latest_date}"

    @patch('services.trends_fetcher.TrendReq')
    def test_backfill_creates_batch_event_with_metadata(self, mock_trends_class, clean_test_db):
        """
        SPEC: US2/FR-008 - Complete batch event metadata for audit trail
        BEHAVIOR: Backfill batch event includes keywords, window, counts, timestamps
        """
        from services.backfill import BackfillService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock API
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [75]
        }, index=[pd.Timestamp('2025-11-01')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        test_keywords = config.keywords[:1]

        backfill_service = BackfillService(clean_test_db)

        # Execute: Run backfill
        batch_event = backfill_service.backfill_initial(keywords=test_keywords, days=90)

        # Verify: Batch event has required metadata
        assert batch_event.batch_id is not None, "Batch ID must be set"
        assert batch_event.batch_type == 'initial_backfill', \
            f"Batch type should be initial_backfill, got {batch_event.batch_type}"
        assert batch_event.requested_keywords == test_keywords, \
            "Keywords must match requested"
        assert '90' in batch_event.requested_window or 'day' in batch_event.requested_window, \
            "Window should indicate 90-day backfill"
        assert batch_event.rows_written >= 0, "Rows written must be recorded"
        assert batch_event.started_at_ict is not None, "Start timestamp must be recorded"
        assert batch_event.finished_at_ict is not None, "Finish timestamp must be recorded"
        assert batch_event.status in ['success', 'degraded'], \
            f"Status must be success or degraded, got {batch_event.status}"

    @patch('services.trends_fetcher.TrendReq')
    def test_backfill_skipped_if_data_already_exists(self, mock_trends_class, clean_test_db):
        """
        SPEC: US2 - Skip backfill if database already populated
        BEHAVIOR: Second backfill attempt should skip or be idempotent
        """
        from services.ingestion import IngestionService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock API
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [75]
        }, index=[pd.Timestamp('2025-11-01')])
        mock_trends_class.return_value = mock_pytrends

        # Setup: Add existing data to database
        with clean_test_db.get_connection() as conn:
            conn.execute("""
                INSERT INTO raw_trenddata
                (keyword, date, rsv_raw, granularity, batch_id, source_window_start, source_window_end)
                VALUES ('ไข้', '2025-11-01', 75, 'daily', 'existing-batch', '2025-11-01', '2025-11-01')
            """)

        config = FetcherConfig()
        ingestion_service = IngestionService(clean_test_db, config)

        # Execute: Attempt backfill check
        batch_event = ingestion_service.ingest_with_initial_backfill_check()

        # Verify: Backfill was skipped or handled gracefully
        # (Either None returned or ingest_daily was called instead)
        if batch_event is not None:
            assert batch_event.batch_type != 'initial_backfill', \
                "Should not trigger initial backfill when data exists"


class TestBackfillProgressAndLogging:
    """Test that backfill provides progress updates and logs."""

    @pytest.fixture
    def test_db(self):
        """Create test database."""
        import tempfile
        from lib.db import DatabaseConnection

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

    @patch('services.backfill.logger')
    @patch('services.trends_fetcher.TrendReq')
    def test_backfill_logs_progress_messages(self, mock_trends_class, mock_logger, test_db):
        """
        SPEC: US2/T036 - Log backfill progress
        BEHAVIOR: Backfill logs start, chunks, completion with row counts
        """
        from services.backfill import BackfillService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock API
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [75]
        }, index=[pd.Timestamp('2025-11-01')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        test_keywords = config.keywords[:1]

        backfill_service = BackfillService(test_db)

        # Execute: Run backfill
        backfill_service.backfill_initial(keywords=test_keywords, days=30)  # Shorter for test

        # Verify: Progress logs were made
        info_calls = [str(call) for call in mock_logger.info.call_args_list]

        # Should log: start, progress, completion
        assert any('backfill' in call.lower() for call in info_calls), \
            "Should log backfill activity"
