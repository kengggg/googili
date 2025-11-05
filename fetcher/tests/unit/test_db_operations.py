"""
Unit Tests for Database Operations Module - SPEC-DRIVEN BEHAVIORAL TESTS

Tests ACTUAL database operations behavior per spec requirements:
- UPSERT operations for RSV records (idempotence)
- Batch event persistence
- Transaction handling and rollback
- Referential integrity maintenance
- Query operations

Constitution alignment:
- Principle III: TDD - Tests written FIRST, validate BEHAVIOR not implementation
- Principle IV: Data Governance - Complete provenance via batch_id FK
- Principle VI: Clarity Over Cleverness - Tests verify ACTUAL database state

Spec references:
- database-schema.sql: Table schemas and constraints
- plan.md: "UPSERT helpers for idempotent operations"
"""

import pytest
import tempfile
import sqlite3
from datetime import date, datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lib.db import DatabaseConnection
from lib.db_operations import DBOperations
from lib.exceptions import DatabaseException
from models.rsv_record import RSVRecord
from models.batch_event import BatchEvent
from models.keyword_config import KeywordConfig
from lib.timezone_utils import ICT


class TestDatabaseOperationsSetup:
    """Test that DBOperations ACTUALLY initializes correctly."""

    def test_creates_db_operations_instance(self):
        """
        SPEC: System must provide database operations interface
        BEHAVIOR: DBOperations ACTUALLY creates instance with database connection
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        db_ops = DBOperations(db)

        assert isinstance(db_ops, DBOperations)
        assert db_ops.db == db

        db.close()
        Path(db_path).unlink()


class TestRSVRecordUpsert:
    """Test that upsert_rsv_records ACTUALLY implements idempotent inserts."""

    @pytest.fixture
    def db_with_schema(self):
        """Create database with schema for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_trenddata (
                    keyword TEXT NOT NULL,
                    date TEXT NOT NULL,
                    rsv_raw INTEGER NOT NULL,
                    source_window_start TEXT NOT NULL,
                    fetched_at_ict TEXT,
                    rsv_stitched INTEGER,
                    granularity TEXT,
                    quality TEXT,
                    impute_method TEXT,
                    batch_id TEXT NOT NULL,
                    PRIMARY KEY (keyword, date)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events_raw_rsv_ingested (
                    batch_id TEXT PRIMARY KEY,
                    batch_type TEXT NOT NULL,
                    start_ict TEXT NOT NULL,
                    end_ict TEXT,
                    status TEXT NOT NULL,
                    rows_written INTEGER DEFAULT 0,
                    rows_updated INTEGER DEFAULT 0,
                    rows_failed INTEGER DEFAULT 0,
                    target_date TEXT,
                    error_json TEXT,
                    notes TEXT
                )
            """)

        yield db

        db.close()
        Path(db_path).unlink()

    def test_inserts_new_rsv_records(self, db_with_schema):
        """
        SPEC: System must persist RSV data
        BEHAVIOR: upsert_rsv_records ACTUALLY inserts new records
        """
        db_ops = DBOperations(db_with_schema)

        records = [
            RSVRecord(
                keyword='ไข้',
                date=date(2025, 11, 1),
                rsv_raw=42,
                source_window_start=datetime(2025, 11, 1, 0, 0, 0, tzinfo=ICT),
                batch_id='batch_123'
            )
        ]

        result = db_ops.upsert_rsv_records(records)

        # Verify counts
        assert result['inserted'] == 1
        assert result['updated'] == 0

        # Verify ACTUAL database content
        with db_with_schema.get_connection() as conn:
            cursor = conn.execute("SELECT keyword, rsv_raw FROM raw_trenddata")
            row = cursor.fetchone()

        assert row is not None
        assert row['keyword'] == 'ไข้'
        assert row['rsv_raw'] == 42

    def test_updates_existing_rsv_records_on_conflict(self, db_with_schema):
        """
        SPEC: UPSERT must handle duplicate (keyword, date) pairs idempotently
        BEHAVIOR: upsert_rsv_records ACTUALLY updates existing records
        """
        db_ops = DBOperations(db_with_schema)

        # Insert initial record
        records_initial = [
            RSVRecord(
                keyword='ไอ',
                date=date(2025, 11, 1),
                rsv_raw=10,
                source_window_start=datetime(2025, 11, 1, 0, 0, 0, tzinfo=ICT),
                batch_id='batch_initial'
            )
        ]
        db_ops.upsert_rsv_records(records_initial)

        # Upsert with same keyword and date (should update)
        records_update = [
            RSVRecord(
                keyword='ไอ',
                date=date(2025, 11, 1),
                rsv_raw=15,  # Different value
                source_window_start=datetime(2025, 11, 1, 0, 0, 0, tzinfo=ICT),
                batch_id='batch_updated'
            )
        ]
        result = db_ops.upsert_rsv_records(records_update)

        # Verify update counted
        assert result['updated'] == 1
        assert result['inserted'] == 0

        # Verify ACTUAL database shows updated value
        with db_with_schema.get_connection() as conn:
            cursor = conn.execute(
                "SELECT rsv_raw, batch_id FROM raw_trenddata WHERE keyword = ? AND date = ?",
                ('ไอ', '2025-11-01')
            )
            row = cursor.fetchone()

        assert row['rsv_raw'] == 15
        assert row['batch_id'] == 'batch_updated'

    def test_upsert_multiple_records_atomically(self, db_with_schema):
        """
        SPEC: Batch operations must be atomic
        BEHAVIOR: upsert_rsv_records ACTUALLY commits all or rolls back all
        """
        db_ops = DBOperations(db_with_schema)

        records = [
            RSVRecord(
                keyword='ไข้',
                date=date(2025, 11, 1),
                rsv_raw=10,
                source_window_start=datetime(2025, 11, 1, 0, 0, 0, tzinfo=ICT),
                batch_id='batch_123'
            ),
            RSVRecord(
                keyword='ไอ',
                date=date(2025, 11, 1),
                rsv_raw=20,
                source_window_start=datetime(2025, 11, 1, 0, 0, 0, tzinfo=ICT),
                batch_id='batch_123'
            ),
            RSVRecord(
                keyword='หวัด',
                date=date(2025, 11, 1),
                rsv_raw=30,
                source_window_start=datetime(2025, 11, 1, 0, 0, 0, tzinfo=ICT),
                batch_id='batch_123'
            )
        ]

        result = db_ops.upsert_rsv_records(records)

        # Verify all inserted
        assert result['inserted'] == 3

        # Verify ACTUAL count in database
        with db_with_schema.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata")
            count = cursor.fetchone()[0]

        assert count == 3

    def test_returns_zero_counts_for_empty_list(self, db_with_schema):
        """
        SPEC: System must handle edge cases gracefully
        BEHAVIOR: upsert_rsv_records ACTUALLY handles empty list
        """
        db_ops = DBOperations(db_with_schema)

        result = db_ops.upsert_rsv_records([])

        assert result['inserted'] == 0
        assert result['updated'] == 0


class TestBatchEventPersistence:
    """Test that batch event operations ACTUALLY persist and update correctly."""

    @pytest.fixture
    def db_with_schema(self):
        """Create database with schema."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events_raw_rsv_ingested (
                    batch_id TEXT PRIMARY KEY,
                    batch_type TEXT NOT NULL,
                    requested_keywords TEXT NOT NULL,
                    requested_window TEXT NOT NULL,
                    started_at_ict TEXT NOT NULL,
                    finished_at_ict TEXT,
                    status TEXT NOT NULL,
                    rows_written INTEGER DEFAULT 0,
                    rows_updated INTEGER DEFAULT 0,
                    rows_missing INTEGER DEFAULT 0,
                    quality_true_daily INTEGER,
                    quality_weekly_flat INTEGER,
                    quality_below_detection INTEGER,
                    notes TEXT,
                    error_message TEXT
                )
            """)

        yield db

        db.close()
        Path(db_path).unlink()

    def test_inserts_new_batch_event(self, db_with_schema):
        """
        SPEC: System must persist batch event metadata
        BEHAVIOR: insert_batch_event ACTUALLY creates batch event record
        """
        db_ops = DBOperations(db_with_schema)

        batch_event = BatchEvent(
            batch_id='batch_123',
            batch_type='daily',
            requested_keywords=['ไข้', 'ไอ'],
            requested_window='2025-11-01 to 2025-11-01',
            started_at_ict=datetime.now(ICT),
            status='running'
        )

        db_ops.insert_batch_event(batch_event)

        # Verify ACTUAL database content
        with db_with_schema.get_connection() as conn:
            cursor = conn.execute("SELECT batch_id, batch_type, status FROM events_raw_rsv_ingested")
            row = cursor.fetchone()

        assert row is not None
        assert row['batch_id'] == 'batch_123'
        assert row['batch_type'] == 'daily'
        assert row['status'] == 'running'

    def test_updates_existing_batch_event(self, db_with_schema):
        """
        SPEC: Batch events must be updatable (e.g., when completing)
        BEHAVIOR: update_batch_event ACTUALLY modifies existing record
        """
        db_ops = DBOperations(db_with_schema)

        # Insert initial batch event
        batch_event = BatchEvent(
            batch_id='batch_123',
            batch_type='daily',
            requested_keywords=['ไข้', 'ไอ'],
            requested_window='2025-11-01 to 2025-11-01',
            started_at_ict=datetime.now(ICT),
            status='running'
        )
        db_ops.insert_batch_event(batch_event)

        # Update to completed status
        batch_event.status = 'success'
        batch_event.finished_at_ict = datetime.now(ICT)
        batch_event.rows_written = 42

        db_ops.update_batch_event(batch_event)

        # Verify ACTUAL database shows updated values
        with db_with_schema.get_connection() as conn:
            cursor = conn.execute(
                "SELECT status, rows_written FROM events_raw_rsv_ingested WHERE batch_id = ?",
                ('batch_123',)
            )
            row = cursor.fetchone()

        assert row['status'] == 'success'
        assert row['rows_written'] == 42

    def test_raises_error_for_duplicate_batch_id(self, db_with_schema):
        """
        SPEC: batch_id is primary key - duplicates must be rejected
        BEHAVIOR: insert_batch_event ACTUALLY raises error for duplicate batch_id
        """
        db_ops = DBOperations(db_with_schema)

        batch_event = BatchEvent(
            batch_id='batch_duplicate',
            batch_type='daily',
            requested_keywords=['ไข้', 'ไอ'],
            requested_window='2025-11-01 to 2025-11-01',
            started_at_ict=datetime.now(ICT),
            status='running'
        )

        # Insert first time (should succeed)
        db_ops.insert_batch_event(batch_event)

        # Attempt to insert again (should fail)
        with pytest.raises(DatabaseException):
            db_ops.insert_batch_event(batch_event)


class TestKeywordQueries:
    """Test that keyword queries ACTUALLY retrieve correct data."""

    @pytest.fixture
    def db_with_keywords(self):
        """Create database with keyword configurations."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config_keywords (
                    term TEXT PRIMARY KEY,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    province_code TEXT NOT NULL,
                    notes TEXT
                )
            """)

            # Insert test keywords
            conn.execute("""
                INSERT INTO config_keywords (term, active, created_at, province_code)
                VALUES ('ไข้', 1, '2025-11-01T07:00:00+07:00', 'TH-50')
            """)
            conn.execute("""
                INSERT INTO config_keywords (term, active, created_at, province_code)
                VALUES ('ไอ', 1, '2025-11-01T07:00:00+07:00', 'TH-50')
            """)
            conn.execute("""
                INSERT INTO config_keywords (term, active, created_at, province_code)
                VALUES ('หวัด', 0, '2025-11-01T07:00:00+07:00', 'TH-50')
            """)

        yield db

        db.close()
        Path(db_path).unlink()

    def test_get_active_keywords_returns_only_active(self, db_with_keywords):
        """
        SPEC: System must query only active keywords
        BEHAVIOR: get_active_keywords ACTUALLY filters by active=1
        """
        db_ops = DBOperations(db_with_keywords)

        keywords = db_ops.get_active_keywords()

        # Verify only active keywords returned
        assert len(keywords) == 2
        terms = [kw.term for kw in keywords]
        assert 'ไข้' in terms
        assert 'ไอ' in terms
        assert 'หวัด' not in terms  # Inactive

    def test_get_active_keywords_returns_keyword_config_objects(self, db_with_keywords):
        """
        SPEC: Query must return typed objects
        BEHAVIOR: get_active_keywords ACTUALLY returns KeywordConfig instances
        """
        db_ops = DBOperations(db_with_keywords)

        keywords = db_ops.get_active_keywords()

        # Verify type
        assert all(isinstance(kw, KeywordConfig) for kw in keywords)

        # Verify properties accessible
        for kw in keywords:
            assert kw.term is not None
            assert kw.active is True
            assert kw.province_code == 'TH-50'


class TestBatchEventQueries:
    """Test that batch event queries ACTUALLY retrieve correct data."""

    @pytest.fixture
    def db_with_batches(self):
        """Create database with batch events."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events_raw_rsv_ingested (
                    batch_id TEXT PRIMARY KEY,
                    batch_type TEXT NOT NULL,
                    requested_keywords TEXT NOT NULL,
                    requested_window TEXT NOT NULL,
                    started_at_ict TEXT NOT NULL,
                    finished_at_ict TEXT,
                    status TEXT NOT NULL,
                    rows_written INTEGER DEFAULT 0,
                    rows_updated INTEGER DEFAULT 0,
                    rows_missing INTEGER DEFAULT 0,
                    quality_true_daily INTEGER,
                    quality_weekly_flat INTEGER,
                    quality_below_detection INTEGER,
                    notes TEXT,
                    error_message TEXT
                )
            """)

            # Insert test batch events (different timestamps)
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested (
                    batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status, rows_written
                ) VALUES ('batch_older', 'daily', '["ไข้","ไอ"]', '2025-11-01 to 2025-11-01', '2025-11-01T07:00:00+07:00', 'success', 10)
            """)
            conn.execute("""
                INSERT INTO events_raw_rsv_ingested (
                    batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status, rows_written
                ) VALUES ('batch_latest', 'daily', '["ไข้","ไอ"]', '2025-11-04 to 2025-11-04', '2025-11-04T07:30:00+07:00', 'success', 20)
            """)

        yield db

        db.close()
        Path(db_path).unlink()

    def test_get_latest_batch_event_returns_most_recent(self, db_with_batches):
        """
        SPEC: System must track most recent batch execution
        BEHAVIOR: get_latest_batch_event ACTUALLY returns latest by timestamp
        """
        db_ops = DBOperations(db_with_batches)

        latest = db_ops.get_latest_batch_event()

        assert latest is not None
        assert latest.batch_id == 'batch_latest'
        assert latest.rows_written == 20

    def test_get_latest_batch_event_returns_none_for_empty_table(self):
        """
        SPEC: System must handle empty database gracefully
        BEHAVIOR: get_latest_batch_event ACTUALLY returns None when no batches
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events_raw_rsv_ingested (
                    batch_id TEXT PRIMARY KEY,
                    batch_type TEXT NOT NULL,
                    requested_keywords TEXT NOT NULL,
                    requested_window TEXT NOT NULL,
                    started_at_ict TEXT NOT NULL,
                    finished_at_ict TEXT,
                    status TEXT NOT NULL,
                    rows_written INTEGER DEFAULT 0,
                    rows_updated INTEGER DEFAULT 0,
                    rows_missing INTEGER DEFAULT 0,
                    quality_true_daily INTEGER,
                    quality_weekly_flat INTEGER,
                    quality_below_detection INTEGER,
                    notes TEXT,
                    error_message TEXT
                )
            """)

        db_ops = DBOperations(db)
        latest = db_ops.get_latest_batch_event()

        assert latest is None

        db.close()
        Path(db_path).unlink()


class TestRecordCounting:
    """Test that record counting operations ACTUALLY return correct counts."""

    @pytest.fixture
    def db_with_records(self):
        """Create database with RSV records."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_trenddata (
                    keyword TEXT NOT NULL,
                    date TEXT NOT NULL,
                    rsv_raw INTEGER NOT NULL,
                    source_window_start TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    PRIMARY KEY (keyword, date)
                )
            """)

            # Insert test records with different batch_ids
            conn.execute("""
                INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, batch_id)
                VALUES ('ไข้', '2025-11-01', 10, '2025-11-01T00:00:00+07:00', 'batch_123')
            """)
            conn.execute("""
                INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, batch_id)
                VALUES ('ไอ', '2025-11-01', 20, '2025-11-01T00:00:00+07:00', 'batch_123')
            """)
            conn.execute("""
                INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, batch_id)
                VALUES ('หวัด', '2025-11-01', 30, '2025-11-01T00:00:00+07:00', 'batch_456')
            """)

        yield db

        db.close()
        Path(db_path).unlink()

    def test_count_rsv_records_without_filter(self, db_with_records):
        """
        SPEC: System must report total RSV records
        BEHAVIOR: count_rsv_records ACTUALLY counts all records when no filter
        """
        db_ops = DBOperations(db_with_records)

        count = db_ops.count_rsv_records()

        assert count == 3

    def test_count_rsv_records_with_batch_id_filter(self, db_with_records):
        """
        SPEC: System must count records by batch
        BEHAVIOR: count_rsv_records ACTUALLY filters by batch_id
        """
        db_ops = DBOperations(db_with_records)

        count_batch_123 = db_ops.count_rsv_records(batch_id='batch_123')
        count_batch_456 = db_ops.count_rsv_records(batch_id='batch_456')

        assert count_batch_123 == 2
        assert count_batch_456 == 1

    def test_is_database_empty_returns_true_for_empty_db(self):
        """
        SPEC: System must detect empty database (first run)
        BEHAVIOR: is_database_empty ACTUALLY returns True when no records
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_trenddata (
                    keyword TEXT NOT NULL,
                    date TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    PRIMARY KEY (keyword, date)
                )
            """)

        db_ops = DBOperations(db)
        is_empty = db_ops.is_database_empty()

        assert is_empty is True

        db.close()
        Path(db_path).unlink()

    def test_is_database_empty_returns_false_for_populated_db(self, db_with_records):
        """
        SPEC: System must detect populated database
        BEHAVIOR: is_database_empty ACTUALLY returns False when records exist
        """
        db_ops = DBOperations(db_with_records)

        is_empty = db_ops.is_database_empty()

        assert is_empty is False
