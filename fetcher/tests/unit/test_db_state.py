"""
Unit Tests for Database State Detection - User Story 2

Tests WHAT the database state detector does, not HOW:
- Detects empty database (first-run scenario)
- Distinguishes first-run from recovery scenarios
- Works with actual database connection

Constitution alignment:
- Principle III: TDD - Tests written BEFORE implementation (RED phase)
- Principle IV: Provenance - Detect state for audit trail

Test Strategy:
- Behavioral tests: Verify empty detection logic
- Integration-style unit tests: Use real test database
- State-based testing: Test different database states
"""

import pytest
from datetime import date
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestDatabaseEmptyDetection:
    """Test that database state detector correctly identifies empty databases."""

    @pytest.fixture
    def empty_test_db(self):
        """Create empty test database with schema."""
        import tempfile
        from lib.db import DatabaseConnection

        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)

        # Initialize schema
        with open('schema.sql', 'r') as f:
            schema = f.read()
        with db.get_connection() as conn:
            conn.executescript(schema)

        yield db

        # Cleanup
        db.close()
        Path(db_path).unlink()

    @pytest.fixture
    def populated_test_db(self):
        """Create test database with some RSV records."""
        import tempfile
        from lib.db import DatabaseConnection
        from models.rsv_record import RSVRecord

        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)

        # Initialize schema
        with open('schema.sql', 'r') as f:
            schema = f.read()
        with db.get_connection() as conn:
            conn.executescript(schema)

        # Insert a few test records
        with db.get_connection() as conn:
            # First add a batch event (foreign key requirement)
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested
                (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status)
                VALUES ('test-batch-001', 'manual', '["ไข้"]', '2025-11-01', '2025-11-01T08:00:00+07:00', 'success')
            """)

            # Then add raw data
            conn.execute("""
                INSERT INTO raw_trenddata
                (keyword, date, rsv_raw, granularity, batch_id, source_window_start, fetched_at_ict, quality)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ('ไข้', '2025-11-01', 75, 'daily', 'test-batch-001', '2025-11-01', '2025-11-01T08:00:00+07:00', 'true'))

        yield db

        # Cleanup
        db.close()
        Path(db_path).unlink()

    def test_is_database_empty_returns_true_for_empty_db(self, empty_test_db):
        """
        SPEC: US2 - Detect empty database to trigger 90-day backfill
        BEHAVIOR: is_database_empty() returns True when raw_trenddata table has zero rows
        """
        from lib.db_state import is_database_empty

        # Execute: Check empty database
        result = is_database_empty(empty_test_db)

        # Verify: Returns True for empty database
        assert result is True, "Empty database should return True"

    def test_is_database_empty_returns_false_for_populated_db(self, populated_test_db):
        """
        SPEC: US2 - Skip initial backfill if data already exists
        BEHAVIOR: is_database_empty() returns False when raw_trenddata has rows
        """
        from lib.db_state import is_database_empty

        # Execute: Check populated database
        result = is_database_empty(populated_test_db)

        # Verify: Returns False for populated database
        assert result is False, "Populated database should return False"

    def test_is_database_empty_only_checks_raw_trenddata_table(self, empty_test_db):
        """
        SPEC: US2 - First-run detection based on data table only
        BEHAVIOR: is_database_empty() checks raw_trenddata, ignores other tables
        """
        from lib.db_state import is_database_empty

        # Setup: Add data to other tables (not raw_trenddata)
        with empty_test_db.get_connection() as conn:
            # Add a batch event (should not affect empty detection)
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested
                (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status)
                VALUES ('test-001', 'manual', '[]', '2025-11-01', '2025-11-01T12:00:00+07:00', 'running')
            """)

        # Execute: Check database state
        result = is_database_empty(empty_test_db)

        # Verify: Still empty because raw_trenddata has no rows
        assert result is True, "Database should be empty if raw_trenddata is empty"


class TestDatabaseStateMetadata:
    """Test that database state detector provides useful metadata."""

    @pytest.fixture
    def empty_test_db(self):
        """Create empty test database with schema."""
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

    @pytest.fixture
    def test_db_with_records(self):
        """Create test database with known record count."""
        import tempfile
        from lib.db import DatabaseConnection

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)

        with open('schema.sql', 'r') as f:
            schema = f.read()
        with db.get_connection() as conn:
            conn.executescript(schema)

        # Insert 5 test records
        with db.get_connection() as conn:
            # First add a batch event (foreign key requirement)
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested
                (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status)
                VALUES ('batch-001', 'manual', '[]', '2025-11-01', '2025-11-01T08:00:00+07:00', 'success')
            """)

            for i in range(5):
                conn.execute("""
                    INSERT INTO raw_trenddata
                    (keyword, date, rsv_raw, granularity, batch_id, source_window_start, fetched_at_ict, quality)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (f'keyword{i}', f'2025-11-0{i+1}', 75, 'daily', 'batch-001',
                      f'2025-11-0{i+1}', '2025-11-01T08:00:00+07:00', 'true'))

        yield db

        db.close()
        Path(db_path).unlink()

    def test_get_raw_trenddata_count_returns_zero_for_empty_db(self, empty_test_db):
        """
        SPEC: US2 - Provide record count for logging/debugging
        BEHAVIOR: get_raw_trenddata_count() returns 0 for empty database
        """
        from lib.db_state import get_raw_trenddata_count

        # Execute
        count = get_raw_trenddata_count(empty_test_db)

        # Verify
        assert count == 0, "Empty database should have 0 records"

    def test_get_raw_trenddata_count_returns_actual_count(self, test_db_with_records):
        """
        SPEC: US2 - Accurate record count for validation
        BEHAVIOR: get_raw_trenddata_count() returns exact row count
        """
        from lib.db_state import get_raw_trenddata_count

        # Execute
        count = get_raw_trenddata_count(test_db_with_records)

        # Verify: Should match 5 inserted records
        assert count == 5, f"Database should have 5 records, got {count}"


class TestFirstRunDetection:
    """Test distinguishing first-run vs. recovery scenarios."""

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

    def test_is_first_run_true_for_empty_db_no_batch_events(self, test_db):
        """
        SPEC: US2 - First-run means no data AND no batch events
        BEHAVIOR: is_first_run() returns True when both tables empty
        """
        from lib.db_state import is_first_run

        # Execute
        result = is_first_run(test_db)

        # Verify: First run detected
        assert result is True, "First run should be detected for fresh database"

    def test_is_first_run_false_if_batch_events_exist(self, test_db):
        """
        SPEC: US2 - Recovery scenario: no data but has batch events (past run failed)
        BEHAVIOR: is_first_run() returns False if batch events exist
        """
        from lib.db_state import is_first_run

        # Setup: Add a batch event (past attempt)
        with test_db.get_connection() as conn:
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested
                (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status)
                VALUES ('batch-001', 'initial_backfill', '[]', '2025-08-01 to 2025-11-01',
                        '2025-11-01T08:00:00+07:00', 'fail')
            """)

        # Execute
        result = is_first_run(test_db)

        # Verify: Not first run (recovery scenario)
        assert result is False, "Should not be first run if batch events exist"

    def test_is_first_run_false_if_data_exists(self, test_db):
        """
        SPEC: US2 - Not first run if data exists
        BEHAVIOR: is_first_run() returns False if raw_trenddata has rows
        """
        from lib.db_state import is_first_run

        # Setup: Add data
        with test_db.get_connection() as conn:
            # First add a batch event (foreign key requirement)
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested
                (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status)
                VALUES ('batch-001', 'manual', '["ไข้"]', '2025-11-01', '2025-11-01T08:00:00+07:00', 'success')
            """)

            conn.execute("""
                INSERT INTO raw_trenddata
                (keyword, date, rsv_raw, granularity, batch_id, source_window_start, fetched_at_ict, quality)
                VALUES ('ไข้', '2025-11-01', 75, 'daily', 'batch-001', '2025-11-01', '2025-11-01T08:00:00+07:00', 'true')
            """)

        # Execute
        result = is_first_run(test_db)

        # Verify: Not first run
        assert result is False, "Should not be first run if data exists"
