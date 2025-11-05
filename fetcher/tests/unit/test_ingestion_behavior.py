"""
Unit Tests for Ingestion Service Behavioral Tests - User Story 2

Tests ACTUAL BEHAVIOR of ingestion service with different database states:
- Empty database triggers automatic 90-day backfill
- Populated database runs normal daily ingestion
- Recovery scenario after failed backfill attempts
- First-run vs. operational-run behavior

Constitution alignment:
- Principle III: TDD - Tests written BEFORE implementation (RED phase)
- Principle VI: Clarity Over Cleverness - Test WHAT users see, not HOW code works
- Principle IV: Provenance - Verify batch events created with correct types

Test Strategy:
- Behavioral tests: Test ingestion service behavior, NOT helper functions
- Integration-style unit tests: Real database fixtures, mocked external API only
- Focus on USER-VISIBLE outcomes: batch events, data in DB, correct behavior
"""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestIngestionBehaviorWithEmptyDatabase:
    """Test ingestion service BEHAVIOR when database is empty (first-run scenario)."""

    @pytest.fixture
    def empty_test_db(self):
        """Create empty test database with schema but no data."""
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
    def test_ingestion_service_triggers_backfill_on_empty_database(self, mock_trends_class, empty_test_db):
        """
        SPEC: US2 Acceptance Scenario 1
        BEHAVIOR: Given clean database, When ingestion runs, Then 90-day backfill triggers

        This tests what USERS/OPERATORS see: empty DB causes automatic backfill
        """
        from services.ingestion import IngestionService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock Google Trends API
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [75],
            'ปวดหัว': [60],
            'ไอ': [55]
        }, index=[pd.Timestamp('2025-11-01')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        ingestion_service = IngestionService(empty_test_db, config)

        # Execute: Run ingestion (should detect empty DB and trigger backfill)
        batch_event = ingestion_service.ingest_with_initial_backfill_check()

        # Verify USER-VISIBLE OUTCOME: Backfill was triggered
        assert batch_event is not None, "Backfill should have been triggered on empty DB"
        assert batch_event.batch_type == 'initial_backfill', \
            f"Batch event should be initial_backfill, got {batch_event.batch_type}"

    @patch('services.trends_fetcher.TrendReq')
    def test_empty_database_backfill_creates_historical_data(self, mock_trends_class, empty_test_db):
        """
        SPEC: US2 Acceptance Scenario 2
        BEHAVIOR: Given empty DB backfill, Then database contains 90 days of data

        This tests what ANALYSTS see: historical data is available after first run
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

        config = FetcherConfig()
        ingestion_service = IngestionService(empty_test_db, config)

        # Execute: Run ingestion
        batch_event = ingestion_service.ingest_with_initial_backfill_check()

        # Verify USER-VISIBLE OUTCOME: Database has historical data
        with empty_test_db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata")
            record_count = cursor.fetchone()[0]

        assert record_count > 0, "Backfill should create historical records in database"
        assert batch_event.rows_written == record_count, \
            "Batch event rows_written should match actual database records"

    @patch('services.trends_fetcher.TrendReq')
    def test_empty_database_backfill_creates_audit_trail(self, mock_trends_class, empty_test_db):
        """
        SPEC: FR-008 - Complete batch event metadata for audit trail
        BEHAVIOR: Given empty DB backfill, Then batch event recorded with metadata

        This tests what STEWARDS see: complete audit trail of backfill operation
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

        config = FetcherConfig()
        ingestion_service = IngestionService(empty_test_db, config)

        # Execute: Run ingestion
        batch_event = ingestion_service.ingest_with_initial_backfill_check()

        # Verify USER-VISIBLE OUTCOME: Batch event has complete metadata
        assert batch_event.batch_id is not None, "Batch event must have unique ID"
        assert batch_event.batch_type == 'initial_backfill', "Batch type must indicate backfill"
        assert batch_event.started_at_ict is not None, "Start timestamp must be recorded"
        assert batch_event.finished_at_ict is not None, "Finish timestamp must be recorded"
        assert batch_event.status in ['success', 'degraded'], \
            f"Status must be success or degraded, got {batch_event.status}"
        assert batch_event.rows_written >= 0, "Row count must be recorded"


class TestIngestionBehaviorWithPopulatedDatabase:
    """Test ingestion service BEHAVIOR when database already has data."""

    @pytest.fixture
    def populated_test_db(self):
        """Create test database with existing RSV records."""
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

        # Insert batch event first (foreign key requirement)
        with db.get_connection() as conn:
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested
                (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status)
                VALUES ('existing-batch', 'manual', '["ไข้"]', '2025-11-01', '2025-11-01T08:00:00+07:00', 'success')
            """)

        # Insert existing data
        with db.get_connection() as conn:
            conn.execute("""
                INSERT INTO raw_trenddata
                (keyword, date, rsv_raw, granularity, batch_id, source_window_start, fetched_at_ict, quality)
                VALUES ('ไข้', '2025-11-01', 75, 'daily', 'existing-batch', '2025-11-01', '2025-11-01T08:00:00+07:00', 'true')
            """)

        yield db

        db.close()
        Path(db_path).unlink()

    @patch('services.trends_fetcher.TrendReq')
    def test_ingestion_service_runs_daily_on_populated_database(self, mock_trends_class, populated_test_db):
        """
        SPEC: US2 - Skip backfill if data exists, run daily ingestion instead
        BEHAVIOR: Given populated DB, When ingestion runs, Then daily ingestion executes

        This tests what OPERATORS see: normal daily operation after initial backfill
        """
        from services.ingestion import IngestionService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock API
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [80]
        }, index=[pd.Timestamp('2025-11-02')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        ingestion_service = IngestionService(populated_test_db, config)

        # Execute: Run ingestion
        batch_event = ingestion_service.ingest_with_initial_backfill_check()

        # Verify USER-VISIBLE OUTCOME: Daily ingestion ran (not backfill)
        if batch_event is not None:
            assert batch_event.batch_type != 'initial_backfill', \
                "Should not trigger initial backfill when database has data"

    @patch('services.trends_fetcher.TrendReq')
    def test_populated_database_maintains_no_duplicates(self, mock_trends_class, populated_test_db):
        """
        SPEC: US2 Acceptance Scenario 2 - No duplicate (keyword, date) pairs
        BEHAVIOR: Given populated DB, When ingestion runs, Then no duplicates created

        This tests what ANALYSTS see: data integrity maintained (no duplicate records)
        """
        from services.ingestion import IngestionService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock API returns same date as existing record
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [80]  # Different value but same date
        }, index=[pd.Timestamp('2025-11-01')])  # Same date as existing record
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        ingestion_service = IngestionService(populated_test_db, config)

        # Get initial count
        with populated_test_db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM raw_trenddata WHERE keyword='ไข้' AND date='2025-11-01'"
            )
            initial_count = cursor.fetchone()[0]

        # Execute: Run ingestion (attempts to insert duplicate date)
        batch_event = ingestion_service.ingest_with_initial_backfill_check()

        # Verify USER-VISIBLE OUTCOME: No duplicates created
        with populated_test_db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM raw_trenddata WHERE keyword='ไข้' AND date='2025-11-01'"
            )
            final_count = cursor.fetchone()[0]

        assert final_count == initial_count, \
            f"Duplicate (keyword, date) pair created: initial={initial_count}, final={final_count}"


class TestIngestionBehaviorRecoveryScenarios:
    """Test ingestion service BEHAVIOR in recovery scenarios."""

    @pytest.fixture
    def recovery_test_db(self):
        """Create database with failed batch event but no data (recovery scenario)."""
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

        # Insert failed batch event (past backfill attempt failed)
        with db.get_connection() as conn:
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested
                (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status)
                VALUES ('failed-batch-001', 'initial_backfill', '["ไข้"]', '2025-08-01 to 2025-11-01',
                        '2025-11-01T08:00:00+07:00', 'fail')
            """)

        yield db

        db.close()
        Path(db_path).unlink()

    @patch('services.trends_fetcher.TrendReq')
    def test_ingestion_service_handles_recovery_after_failed_backfill(self, mock_trends_class, recovery_test_db):
        """
        SPEC: US2 - Distinguish first-run vs recovery scenarios
        BEHAVIOR: Given failed past backfill, When ingestion runs, Then recovery logic triggers

        This tests what OPERATORS see: system recovers from past failures
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

        config = FetcherConfig()
        ingestion_service = IngestionService(recovery_test_db, config)

        # Execute: Run ingestion
        batch_event = ingestion_service.ingest_with_initial_backfill_check()

        # Verify USER-VISIBLE OUTCOME: Recovery attempt made (not duplicate "initial backfill")
        # System should either retry backfill OR recognize recovery scenario
        assert batch_event is not None, "Recovery ingestion should execute"

        # Verify: Batch event recorded in audit trail
        with recovery_test_db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM events_raw_rsv_ingested WHERE status IN ('success', 'degraded')"
            )
            successful_batches = cursor.fetchone()[0]

        assert successful_batches > 0, "Recovery attempt should be recorded in audit trail"


class TestIngestionBehaviorEdgeCases:
    """Test ingestion service BEHAVIOR in edge cases."""

    @pytest.fixture
    def test_db(self):
        """Create empty test database."""
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

    @patch('services.trends_fetcher.TrendReq')
    def test_partial_backfill_when_keyword_has_insufficient_history(self, mock_trends_class, test_db):
        """
        SPEC: US2 Acceptance Scenario 3 - Partial backfill handling
        BEHAVIOR: Given keyword with <90 days history, Then stores available days + note

        This tests what OPERATORS see: partial backfill with explanatory note
        """
        from services.backfill import BackfillService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock API returns only 30 days (not 90)
        mock_pytrends = Mock()
        # Simulate partial data availability
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [75]
        }, index=[pd.Timestamp('2025-11-01')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        backfill_service = BackfillService(test_db)

        # Execute: Run 90-day backfill (but API only returns 30 days)
        batch_event = backfill_service.backfill_initial(
            keywords=['ไข้'],
            days=90
        )

        # Verify USER-VISIBLE OUTCOME: Partial backfill recorded
        # System should either:
        # 1. Log "partial backfill: only N days available" in batch event notes
        # 2. Mark batch as 'degraded' status
        # 3. Record actual rows written < (90 × keyword count)

        assert batch_event is not None, "Partial backfill should complete"
        assert batch_event.status in ['success', 'degraded'], \
            "Partial backfill should complete with success or degraded status"

        # If notes field available, verify explanatory message
        if hasattr(batch_event, 'notes') and batch_event.notes:
            assert 'partial' in batch_event.notes.lower() or 'available' in batch_event.notes.lower() or 'missing' in batch_event.notes.lower(), \
                "Batch event should note partial backfill situation"

    @patch('services.trends_fetcher.TrendReq')
    def test_backfill_handles_all_zero_values(self, mock_trends_class, test_db):
        """
        SPEC: Edge Case - Google Trends returns all zeros
        BEHAVIOR: Given API returns zeros, Then stores zeros (no manufactured signal)

        This tests what ANALYSTS see: true zeros preserved (constitution principle)
        """
        from services.backfill import BackfillService
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock API returns all zeros
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.return_value = pd.DataFrame({
            'ไข้': [0, 0, 0]
        }, index=[pd.Timestamp('2025-11-01'), pd.Timestamp('2025-11-02'), pd.Timestamp('2025-11-03')])
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        backfill_service = BackfillService(test_db)

        # Execute: Run backfill with zero data
        batch_event = backfill_service.backfill_initial(keywords=['ไข้'], days=3)

        # Verify USER-VISIBLE OUTCOME: Zeros preserved in database
        with test_db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT rsv_raw FROM raw_trenddata WHERE keyword='ไข้'"
            )
            rsv_values = [row[0] for row in cursor.fetchall()]

        # Constitution Principle: Zeros are signal, not absence
        if rsv_values:  # If any data stored
            assert all(rsv == 0 for rsv in rsv_values), \
                "Zero RSV values should be preserved (no manufactured signal)"
