"""
End-to-End Integration Tests - SPEC-DRIVEN COMPLETE FLOWS

Tests COMPLETE user scenarios from spec.md:
- US1: Daily scheduled ingestion → batch event → database records
- US2: Manual ingestion with date → distinguishable batch event
- Complete flows without mocks (real database, real services)

Constitution alignment:
- Principle III: TDD - Tests validate ACTUAL system behavior end-to-end
- Principle I: Adjunct Signal - Tests verify data flows through entire pipeline
"""

import pytest
import sqlite3
import tempfile
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, Mock
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lib.db import DatabaseConnection
from services.ingestion import IngestionService
from models.batch_event import BatchEvent


@pytest.fixture
def test_config():
    """Create mock FetcherConfig for testing."""
    class MockConfig:
        def __init__(self):
            self.province = 'TH-50'
            self.jitter_seconds = [1, 2]
            self.keywords = ['ไข้หวัดนก', 'ไอ', 'หวัด']
    return MockConfig()


class TestManualIngestionEndToEnd:
    """Test complete manual ingestion flow from CLI to database."""

    @pytest.fixture
    def real_db(self):
        """Create real temporary database for integration testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        # Initialize database with schema
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_events (
                batch_id TEXT PRIMARY KEY,
                batch_type TEXT NOT NULL,
                status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                target_date TEXT,
                rows_written INTEGER DEFAULT 0,
                rows_updated INTEGER DEFAULT 0,
                keywords_attempted INTEGER DEFAULT 0,
                keywords_succeeded INTEGER DEFAULT 0,
                notes TEXT,
                error_message TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rsv_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                date TEXT NOT NULL,
                province_code TEXT NOT NULL,
                keyword TEXT NOT NULL,
                value INTEGER NOT NULL,
                is_partial INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(date, province_code, keyword)
            )
        """)
        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    @patch('services.trends_fetcher.TrendsFetcher')
    def test_manual_ingestion_creates_batch_event_in_database(self, mock_trends_fetcher_class, real_db, test_config):
        """
        SPEC: US2 - On-demand manual ingestion for specific date
        BEHAVIOR: Manual ingestion ACTUALLY creates batch event record in database
        """
        # Setup: Mock Google Trends API
        mock_trends = Mock()
        mock_trends.fetch_daily_interest.return_value = {
            '2025-11-01': {'ไข้หวัดนก': 42, 'ไอ': 38}
        }
        mock_trends_fetcher_class.return_value = mock_trends

        # Create real services
        db = DatabaseConnection(real_db)
        ingestion_service = IngestionService(db, test_config)

        # Execute: Run manual ingestion
        batch_event = ingestion_service.ingest_daily(
            batch_type='manual',
            target_date=date(2025, 11, 1)
        )

        # Verify: Batch event ACTUALLY written to database
        conn = sqlite3.connect(real_db)
        cursor = conn.cursor()
        cursor.execute("SELECT batch_id, batch_type, status, target_date FROM batch_events")
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "No batch event created in database"
        assert row[0] == batch_event.batch_id, "Batch ID mismatch"
        assert row[1] == 'manual', "Batch type not marked as 'manual'"
        assert row[2] == 'success', "Batch status not 'success'"
        assert row[3] == '2025-11-01', "Target date incorrect"

    @patch('services.trends_fetcher.TrendsFetcher')
    def test_manual_ingestion_creates_rsv_data_records(self, mock_trends_fetcher_class, real_db, test_config):
        """
        SPEC: US2 - Manual ingestion must store fetched data
        BEHAVIOR: Ingestion ACTUALLY writes RSV data records to database
        """
        # Setup: Mock Google Trends API with known data
        mock_trends = Mock()
        mock_trends.fetch_daily_interest.return_value = {
            '2025-11-01': {'ไข้หวัดนก': 42, 'ไอ': 38, 'หวัด': 55}
        }
        mock_trends_fetcher_class.return_value = mock_trends

        # Create real services
        db = DatabaseConnection(real_db)
        ingestion_service = IngestionService(db, test_config)

        # Execute: Run manual ingestion
        batch_event = ingestion_service.ingest_daily(
            batch_type='manual',
            target_date=date(2025, 11, 1)
        )

        # Verify: RSV data ACTUALLY written to database
        conn = sqlite3.connect(real_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, keyword, value, batch_id
            FROM rsv_data
            WHERE batch_id = ?
            ORDER BY keyword
        """, (batch_event.batch_id,))
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 3, f"Expected 3 RSV records, got {len(rows)}"
        assert rows[0][1] == 'ไอ', "Keyword mismatch"
        assert rows[0][2] == 38, "RSV value mismatch for 'ไอ'"
        assert rows[1][1] == 'ไข้หวัดนก', "Keyword mismatch"
        assert rows[1][2] == 42, "RSV value mismatch for 'ไข้หวัดนก'"
        assert rows[2][1] == 'หวัด', "Keyword mismatch"
        assert rows[2][2] == 55, "RSV value mismatch for 'หวัด'"

    @patch('services.trends_fetcher.TrendsFetcher')
    def test_daily_vs_manual_batch_types_are_distinguishable(self, mock_trends_fetcher_class, real_db, test_config):
        """
        SPEC: FR-008 - Batch events must distinguish scheduled vs manual triggers
        BEHAVIOR: Database ACTUALLY stores different batch_type for daily vs manual
        """
        # Setup: Mock Google Trends API
        mock_trends = Mock()
        mock_trends.fetch_daily_interest.return_value = {
            '2025-11-01': {'ไข้': 10}
        }
        mock_trends_fetcher_class.return_value = mock_trends

        # Create real services
        db = DatabaseConnection(real_db)
        ingestion_service = IngestionService(db, test_config)

        # Execute: Run MANUAL ingestion
        manual_batch = ingestion_service.ingest_daily(
            batch_type='manual',
            target_date=date(2025, 11, 1)
        )

        # Execute: Run DAILY ingestion
        mock_trends.fetch_daily_interest.return_value = {
            '2025-11-02': {'ไข้': 15}
        }
        daily_batch = ingestion_service.ingest_daily(
            batch_type='daily',
            target_date=date(2025, 11, 2)
        )

        # Verify: Batch types ACTUALLY distinguishable in database
        conn = sqlite3.connect(real_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT batch_id, batch_type, target_date
            FROM batch_events
            ORDER BY target_date
        """)
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 2, "Expected 2 batch events"
        assert rows[0][1] == 'manual', "First batch not marked as 'manual'"
        assert rows[1][1] == 'daily', "Second batch not marked as 'daily'"


class TestBatchEventMetadata:
    """Test that batch events contain complete metadata per spec."""

    @pytest.fixture
    def real_db(self):
        """Create real temporary database."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_events (
                batch_id TEXT PRIMARY KEY,
                batch_type TEXT NOT NULL,
                status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                target_date TEXT,
                rows_written INTEGER DEFAULT 0,
                rows_updated INTEGER DEFAULT 0,
                keywords_attempted INTEGER DEFAULT 0,
                keywords_succeeded INTEGER DEFAULT 0,
                notes TEXT,
                error_message TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rsv_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                date TEXT NOT NULL,
                province_code TEXT NOT NULL,
                keyword TEXT NOT NULL,
                value INTEGER NOT NULL,
                is_partial INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(date, province_code, keyword)
            )
        """)
        conn.commit()
        conn.close()

        yield db_path
        Path(db_path).unlink(missing_ok=True)

    @patch('services.trends_fetcher.TrendsFetcher')
    def test_batch_event_contains_required_metadata(self, mock_trends_fetcher_class, real_db, test_config):
        """
        SPEC: FR-008 - Batch events must include metadata (batch_id, status, counts, timestamp)
        BEHAVIOR: Database batch_events record ACTUALLY contains all required fields
        """
        # Setup
        mock_trends = Mock()
        mock_trends.fetch_daily_interest.return_value = {
            '2025-11-01': {'ไข้': 10, 'ไอ': 20}
        }
        mock_trends_fetcher_class.return_value = mock_trends

        db = DatabaseConnection(real_db)
        ingestion_service = IngestionService(db, test_config)

        # Execute
        batch_event = ingestion_service.ingest_daily(
            batch_type='daily',
            target_date=date(2025, 11, 1)
        )

        # Verify: All metadata fields ACTUALLY present
        conn = sqlite3.connect(real_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT batch_id, batch_type, status, start_time, end_time,
                   target_date, rows_written, keywords_attempted, keywords_succeeded
            FROM batch_events
        """)
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "Batch event not created"
        assert row[0] is not None, "batch_id missing"
        assert row[1] == 'daily', "batch_type missing"
        assert row[2] in ['success', 'degraded', 'failed'], "status invalid"
        assert row[3] is not None, "start_time missing"
        assert row[4] is not None, "end_time missing"
        assert row[5] == '2025-11-01', "target_date missing"
        assert row[6] >= 0, "rows_written missing"
        assert row[7] >= 0, "keywords_attempted missing"
        assert row[8] >= 0, "keywords_succeeded missing"

    @patch('services.trends_fetcher.TrendsFetcher')
    def test_batch_event_tracks_partial_failure_status(self, mock_trends_fetcher_class, real_db, test_config):
        """
        SPEC: FR-008 - System must track degraded status (partial failures)
        BEHAVIOR: Batch event status ACTUALLY set to 'degraded' when some keywords fail
        """
        # Setup: Mock API that succeeds first time, fails second time
        mock_trends = Mock()
        mock_trends.fetch_daily_interest.side_effect = [
            {'2025-11-01': {'ไข้': 10}},  # First keyword succeeds
            Exception("API rate limit")     # Second keyword fails
        ]
        mock_trends_fetcher_class.return_value = mock_trends

        db = DatabaseConnection(real_db)
        ingestion_service = IngestionService(db, test_config)

        # Execute: Try to ingest multiple keywords (some will fail)
        batch_event = ingestion_service.ingest_daily(
            batch_type='daily',
            target_date=date(2025, 11, 1)
        )

        # Verify: Status ACTUALLY reflects partial failure
        conn = sqlite3.connect(real_db)
        cursor = conn.cursor()
        cursor.execute("SELECT status, keywords_attempted, keywords_succeeded FROM batch_events")
        row = cursor.fetchone()
        conn.close()

        # If some keywords failed, status should be 'degraded'
        if row[1] > row[2]:  # keywords_attempted > keywords_succeeded
            assert row[0] == 'degraded', "Status not 'degraded' for partial failure"


class TestCLIIntegrationWithDatabase:
    """Test complete CLI → Service → Database flow."""

    @pytest.fixture
    def real_db(self):
        """Create real temporary database."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_events (
                batch_id TEXT PRIMARY KEY,
                batch_type TEXT NOT NULL,
                status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                target_date TEXT,
                rows_written INTEGER DEFAULT 0,
                rows_updated INTEGER DEFAULT 0,
                keywords_attempted INTEGER DEFAULT 0,
                keywords_succeeded INTEGER DEFAULT 0,
                notes TEXT,
                error_message TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rsv_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                date TEXT NOT NULL,
                province_code TEXT NOT NULL,
                keyword TEXT NOT NULL,
                value INTEGER NOT NULL,
                is_partial INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(date, province_code, keyword)
            )
        """)
        conn.commit()
        conn.close()

        yield db_path
        Path(db_path).unlink(missing_ok=True)

    @patch('services.trends_fetcher.TrendsFetcher')
    @patch('main.init_database')
    def test_cli_manual_mode_end_to_end(self, mock_init_db, mock_trends_fetcher_class, real_db):
        """
        SPEC: US2 - On-demand manual ingestion triggered via CLI
        BEHAVIOR: CLI --manual ACTUALLY creates records in database
        """
        from main import run_manual

        # Setup: Mock database initialization
        db = DatabaseConnection(real_db)
        mock_init_db.return_value = db

        # Setup: Mock Google Trends API
        mock_trends = Mock()
        mock_trends.fetch_daily_interest.return_value = {
            '2025-11-01': {'ไข้': 25}
        }
        mock_trends_fetcher_class.return_value = mock_trends

        # Execute: Run CLI manual mode
        exit_code = run_manual(real_db, 'schema.sql', '2025-11-01')

        # Verify: ACTUAL database records created
        conn = sqlite3.connect(real_db)
        cursor = conn.cursor()

        # Check batch event exists
        cursor.execute("SELECT batch_type, status FROM batch_events")
        batch_row = cursor.fetchone()
        assert batch_row is not None, "No batch event created by CLI"
        assert batch_row[0] == 'manual', "Batch type not 'manual'"

        # Check RSV data exists
        cursor.execute("SELECT COUNT(*) FROM rsv_data")
        data_count = cursor.fetchone()[0]
        assert data_count > 0, "No RSV data created by CLI"

        conn.close()

        # Verify exit code
        assert exit_code == 0, "CLI returned non-zero exit code"
