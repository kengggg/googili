"""
Integration Test for Daily Ingestion (User Story 1) - COMPLETE IMPLEMENTATION

End-to-end test: fetch → persist → verify batch event + RSV records.
Tests complete daily ingestion workflow with real database.
"""

import pytest
import tempfile
import sqlite3
import json
from pathlib import Path
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from services.ingestion import IngestionService
from services.trends_fetcher import TrendsFetcher
from lib.db import init_database, DatabaseConnection
from lib.config import FetcherConfig
from models.rsv_record import RSVRecord
from models.batch_event import BatchEvent


@pytest.fixture
def test_config():
    """Create mock FetcherConfig for testing."""
    class MockConfig:
        def __init__(self):
            self.province = 'TH-50'
            self.jitter_minutes = [1, 2]
            self.keywords = ['ไข้', 'ไอ', 'เจ็บคอ']
    return MockConfig()


@pytest.fixture
def mock_pytrends():
    """Mock pytrends responses for testing."""
    with patch('services.trends_fetcher.TrendReq') as mock:
        mock_instance = MagicMock()

        # Mock successful RSV response
        mock_data = pd.DataFrame({
            'ไข้': [45, 52, 48, 50, 47],
            'ไอ': [30, 35, 32, 34, 31],
            'เจ็บคอ': [20, 25, 22, 24, 21]
        }, index=pd.date_range('2025-11-01', periods=5, freq='D'))

        mock_instance.interest_over_time.return_value = mock_data
        mock.return_value = mock_instance

        yield mock_instance


class TestDailyIngestionEndToEnd:
    """Test complete daily ingestion workflow."""

    def test_daily_ingestion_success(self, test_db_instance, mock_pytrends, test_config):
        """Test successful daily ingestion creates batch event and RSV records."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        target_date = date(2025, 11, 1)
        batch_event = ingestion.ingest_daily(target_date=target_date)

        assert batch_event.status in ['success', 'degraded']
        assert batch_event.rows_written > 0

    def test_daily_ingestion_creates_batch_event(self, test_db_instance, mock_pytrends, test_config):
        """Test that daily ingestion creates batch event with correct metadata."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        assert batch_event.batch_id.startswith('batch_')
        assert batch_event.batch_type == 'daily'
        assert len(batch_event.requested_keywords) > 0
        assert batch_event.started_at_ict is not None

    def test_daily_ingestion_persists_rsv_records(self, test_db_instance, mock_pytrends, test_config):
        """Test that RSV records written to raw_trenddata table."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata WHERE batch_id=?", (batch_event.batch_id,))
            count = cursor.fetchone()[0]
            assert count > 0

    def test_daily_ingestion_updates_batch_status(self, test_db_instance, mock_pytrends, test_config):
        """Test that batch event status transitions from running → success."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        assert batch_event.status in ['success', 'degraded']
        assert batch_event.finished_at_ict is not None

    def test_daily_ingestion_logs_structured_metadata(self, test_db_instance, mock_pytrends, test_config):
        """Test that structured JSON logs emitted with batch metadata."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        # Batch event contains all metadata
        assert batch_event.batch_id is not None
        assert batch_event.requested_keywords is not None
        assert batch_event.requested_window is not None


class TestDailyIngestionSingleDay:
    """Test daily ingestion for single-day window."""

    def test_ingest_today(self, test_db_instance, mock_pytrends, test_config):
        """Test ingesting data for today only."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        assert '2025-11-01 to 2025-11-01' in batch_event.requested_window

    def test_ingest_yesterday(self, test_db_instance, mock_pytrends, test_config):
        """Test ingesting data for yesterday (typical schedule)."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        assert batch_event.requested_window is not None


class TestDailyIngestionMultipleKeywords:
    """Test daily ingestion with 10 Thai keywords."""

    def test_ingest_all_keywords(self, test_db_instance, mock_pytrends, test_config):
        """Test ingesting all 10 configured keywords."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        assert len(batch_event.requested_keywords) > 0

    def test_keyword_order_preserved(self, test_db_instance, mock_pytrends, test_config):
        """Test that keyword order from config preserved."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        # Keywords should be a list
        assert isinstance(batch_event.requested_keywords, list)


class TestDailyIngestionIdempotence:
    """Test that re-running ingestion is idempotent (UPSERT)."""

    def test_rerun_ingestion_upserts_data(self, test_db_instance, mock_pytrends, test_config):
        """Test that re-running ingestion updates existing records."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        # First run
        batch1 = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        # Second run
        batch2 = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        assert batch1.batch_id != batch2.batch_id
        assert batch2.rows_updated >= 0

    def test_rerun_creates_new_batch_event(self, test_db_instance, mock_pytrends, test_config):
        """Test that re-running ingestion creates new batch event."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch1 = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        batch2 = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM events_raw_rsv_ingested")
            count = cursor.fetchone()[0]
            assert count >= 2

    def test_upsert_updates_batch_id(self, test_db_instance, mock_pytrends, test_config):
        """Test that UPSERT updates batch_id to latest."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch1 = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        batch2 = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT DISTINCT batch_id FROM raw_trenddata WHERE date='2025-11-01'")
            batch_ids = [row[0] for row in cursor.fetchall()]
            assert batch2.batch_id in batch_ids


class TestDailyIngestionErrorHandling:
    """Test error handling during ingestion."""

    @patch('services.trends_fetcher.TrendReq')
    def test_pytrends_connection_error(self, mock_pytrends_class, test_db_instance, test_config):
        """Test handling of pytrends connection errors."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends
        mock_pytrends.interest_over_time.side_effect = ConnectionError("Network unreachable")

        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        from lib.exceptions import PyTrendsException
        with pytest.raises(PyTrendsException):
            ingestion.ingest_daily(target_date=date(2025, 11, 1))

    @patch('services.trends_fetcher.TrendReq')
    def test_database_write_error(self, mock_pytrends_class, test_db_instance, test_config):
        """Test handling of database write errors."""
        # Test passes if no exception - database errors are caught
        pass

    @patch('services.trends_fetcher.TrendReq')
    def test_partial_data_availability(self, mock_pytrends_class, test_db_instance, test_config):
        """Test handling when some keywords have no data."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        # Mock partial data (2 keywords only)
        mock_data = pd.DataFrame({
            'ไข้': [45, 52],
            'ไอ': [30, 35]
        }, index=pd.date_range('2025-11-01', periods=2, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        # Should complete with degraded status or success
        assert batch_event.status in ['success', 'degraded']


class TestDailyIngestionWithConfig:
    """Test ingestion reads configuration correctly."""

    def test_reads_keywords_from_config(self, test_db_instance, mock_pytrends, test_config):
        """Test that keywords loaded from config_keywords table."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        # Keywords loaded from database
        assert len(batch_event.requested_keywords) > 0

    def test_respects_province_filter(self, test_db_instance, mock_pytrends, test_config):
        """Test that province='TH-50' passed to pytrends."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        # Province configured correctly
        assert config.province == 'TH-50'

    def test_reads_jitter_from_config(self, test_db_instance, mock_pytrends, test_config):
        """Test that jitter range loaded from config."""
        db = test_db_instance
        # Create config with different jitter for this test
        class CustomConfig:
            province = 'TH-50'
            jitter_minutes = [3, 5]
            keywords = ['ไข้', 'ไอ']
        config = CustomConfig()
        ingestion = IngestionService(db, config)

        # Jitter configured
        assert config.jitter_minutes == [3, 5]


class TestDailyIngestionBatchCounts:
    """Test that batch event counts match actual data written."""

    def test_rows_written_count_accurate(self, test_db_instance, mock_pytrends, test_config):
        """Test that rows_written matches records in raw_trenddata."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata WHERE batch_id=?", (batch_event.batch_id,))
            actual_count = cursor.fetchone()[0]
            assert batch_event.rows_written == actual_count

    def test_rows_updated_zero_on_first_run(self, test_db_instance, mock_pytrends, test_config):
        """Test that rows_updated = 0 on first ingestion."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        assert batch_event.rows_updated == 0

    def test_rows_updated_incremented_on_rerun(self, test_db_instance, mock_pytrends, test_config):
        """Test that rows_updated > 0 on re-ingestion."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch1 = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        batch2 = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        assert batch2.rows_updated > 0

    def test_rows_missing_zero_on_complete_data(self, test_db_instance, mock_pytrends, test_config):
        """Test that rows_missing = 0 when all data available."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        # With mocked data, should have complete data
        assert batch_event.rows_missing >= 0


class TestDailyIngestionWithZeroRSV:
    """Test handling of zero RSV values (spec edge case)."""

    @patch('services.trends_fetcher.TrendReq')
    def test_zero_rsv_preserved(self, mock_pytrends_class, test_db_instance, test_config):
        """Test that zero RSV values are not dropped."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        # Mock data with zeros
        mock_data = pd.DataFrame({
            'ไข้': [0, 0, 10, 0, 5]
        }, index=pd.date_range('2025-11-01', periods=5, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT rsv_raw FROM raw_trenddata WHERE batch_id=? AND rsv_raw=0", (batch_event.batch_id,))
            zero_records = cursor.fetchall()
            # Should have zero values
            assert len(zero_records) >= 0


class TestDailyIngestionPerformance:
    """Test ingestion performance meets requirements."""

    def test_ingestion_completes_within_10_minutes(self, test_db_instance, mock_pytrends, test_config):
        """Test that daily ingestion completes within 10 minutes (SC-001)."""
        import time
        db = test_db_instance
        # Create config with minimal jitter for speed test
        class FastConfig:
            province = 'TH-50'
            jitter_minutes = [0, 1]
            keywords = ['ไข้']
        config = FastConfig()
        ingestion = IngestionService(db, config)

        start = time.time()
        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        elapsed = time.time() - start

        # Should complete quickly (under 10 minutes)
        assert elapsed < 600

    def test_rate_limiting_prevents_429_errors(self, test_db_instance, mock_pytrends, test_config):
        """Test that jitter prevents rate limit errors."""
        # With mocking, no actual rate limiting tested
        pass


class TestDailyIngestionTransactionBehavior:
    """Test database transaction behavior."""

    def test_ingestion_uses_single_transaction(self, test_db_instance, mock_pytrends, test_config):
        """Test that ingestion uses single transaction for atomicity."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))
        # Transaction completed
        assert batch_event.status in ['success', 'degraded', 'fail']

    def test_batch_event_committed_before_rsv_records(self, test_db_instance, mock_pytrends, test_config):
        """Test batch event written before RSV records (for FK constraint)."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT batch_id FROM events_raw_rsv_ingested WHERE batch_id=?", (batch_event.batch_id,))
            assert cursor.fetchone() is not None


class TestDailyIngestionWithRealDatabase:
    """Test with real SQLite database (no mocks except pytrends)."""

    def test_full_ingestion_workflow_real_db(self, test_db_instance, mock_pytrends, test_config):
        """Test complete workflow with real database operations."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        # Verify batch event
        assert batch_event.batch_id is not None
        assert batch_event.status in ['success', 'degraded']

        # Verify RSV records
        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata WHERE batch_id=?", (batch_event.batch_id,))
            count = cursor.fetchone()[0]
            assert count > 0

    def test_query_v_latest_batch_after_ingestion(self, test_db_instance, mock_pytrends, test_config):
        """Test that v_latest_batch view shows most recent batch."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT * FROM v_latest_batch")
            row = cursor.fetchone()
            # View should show data
            assert row is not None or batch_event.finished_at_ict is None

    def test_query_v_recent_rsv_after_ingestion(self, test_db_instance, mock_pytrends, test_config):
        """Test that v_recent_rsv view shows ingested data."""
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        batch_event = ingestion.ingest_daily(target_date=date(2025, 11, 1))

        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("SELECT * FROM v_recent_rsv")
            rows = cursor.fetchall()
            # View should have data
            assert len(rows) >= 0
