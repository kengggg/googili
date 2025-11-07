"""
Integration Tests for Simplified Ingestion with Stitching

Tests the complete workflow:
1. Day 1 ingestion (no stitching - first run)
2. Day 2 ingestion (with stitching - overlap detected)
3. Verify continuous time series without normalization jumps

Per spec.md US1 + US3: Daily 'today 1-m' ingestion with overlap-based stitching
"""

import pytest
import tempfile
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from services.ingestion import IngestionService
from lib.db import init_database, DatabaseConnection
from lib.config import FetcherConfig


@pytest.fixture
def test_config():
    """Create mock FetcherConfig for testing."""
    class MockConfig:
        def __init__(self):
            self.province = 'TH'
            self.language = 'en-US'
            self.jitter_seconds = [1, 2]
            self.keywords = ['ไข้', 'ไอ']
            self.stitching_min_overlap_days = 1
            self.stitching_trim_percent = 20
            # Rate limiting config
            self.max_retries = 3
            self.backoff_base_seconds = 60
            self.backoff_multiplier = 5.0
            self.max_backoff_seconds = 1800
            self.respect_retry_after = True
    return MockConfig()


class TestSimplifiedIngestionWorkflow:
    """Test simplified 'today 1-m' ingestion workflow."""

    @patch('services.trends_fetcher.TrendReq')
    def test_one_keyword_per_request_with_jitter(self, mock_trend_req, test_db_instance, test_config):
        """
        Test that ingestion fetches ONE keyword per request with 3-5s jitter.

        Per spec.md FR-002: ONE keyword per request to respect API limits
        Per spec.md: Jitter between requests to prevent rate limiting
        """
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        # Mock pytrends responses
        mock_instance = MagicMock()
        mock_trend_req.return_value = mock_instance

        # Create separate dataframes for each keyword
        dates = pd.date_range('2025-10-08', periods=32, freq='D')

        # First keyword response
        df1 = pd.DataFrame({'ไข้': [45, 47, 50, 48, 52] + [50] * 27}, index=dates[:32])

        # Second keyword response
        df2 = pd.DataFrame({'ไอ': [30, 32, 35, 33, 36] + [35] * 27}, index=dates[:32])

        # Return different data on subsequent calls
        mock_instance.interest_over_time.side_effect = [df1, df2]

        # Run ingestion
        batch_event = ingestion.ingest()

        # Verify ONE keyword per request
        assert mock_instance.interest_over_time.call_count == 2

        # Verify batch type is 'ingestion'
        assert batch_event.batch_type == 'ingestion'

        # Verify records persisted
        assert batch_event.rows_written > 0

    @patch('services.trends_fetcher.TrendReq')
    def test_first_ingestion_no_stitching(self, mock_trend_req, test_db_instance, test_config):
        """
        Test first ingestion: rsv_stitched = rsv_raw (no overlap exists).

        Per spec.md US3 Scenario 2: First run has no existing data
        """
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        # Mock pytrends
        mock_instance = MagicMock()
        mock_trend_req.return_value = mock_instance

        dates = pd.date_range('2025-10-08', periods=32, freq='D')
        df1 = pd.DataFrame({'ไข้': [45, 47, 50]}, index=dates[:3])
        df2 = pd.DataFrame({'ไอ': [30, 32, 35]}, index=dates[:3])
        mock_instance.interest_over_time.side_effect = [df1, df2]

        # Run first ingestion
        batch_event = ingestion.ingest()

        # Verify records created
        assert batch_event.status == 'success'

        # Query database and verify rsv_stitched == rsv_raw
        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("""
                SELECT keyword, date, rsv_raw, rsv_stitched
                FROM raw_trenddata
                WHERE batch_id = ?
                ORDER BY keyword, date
            """, (batch_event.batch_id,))

            records = cursor.fetchall()

            # Verify stitched values equal raw values
            for rec in records:
                keyword, date, rsv_raw, rsv_stitched = rec
                assert rsv_stitched == float(rsv_raw), \
                    f"First ingestion: expected rsv_stitched={rsv_raw}, got {rsv_stitched}"

    @patch('services.trends_fetcher.TrendReq')
    def test_second_ingestion_with_stitching(self, mock_trend_req, test_db_instance, test_config):
        """
        Test second ingestion: detects overlap, computes scaling factor, applies stitching.

        Per spec.md US3 Scenario 3: Consecutive ingestions with overlapping windows
        """
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        mock_instance = MagicMock()
        mock_trend_req.return_value = mock_instance

        # Day 1: Oct 8 - Nov 8 (32 days)
        dates_day1 = pd.date_range('2025-10-08', periods=32, freq='D')
        df1_day1 = pd.DataFrame({'ไข้': list(range(40, 72))}, index=dates_day1)
        df2_day1 = pd.DataFrame({'ไอ': list(range(20, 52))}, index=dates_day1)

        mock_instance.interest_over_time.side_effect = [df1_day1, df2_day1]

        # Run Day 1 ingestion
        batch1 = ingestion.ingest()
        assert batch1.status == 'success'

        # Day 2: Oct 9 - Nov 9 (32 days, 31-day overlap: Oct 9 - Nov 8)
        # Simulate different normalization (scaling factor ~0.8)
        dates_day2 = pd.date_range('2025-10-09', periods=32, freq='D')

        # New window has higher raw values due to independent normalization
        df1_day2 = pd.DataFrame({'ไข้': list(range(50, 82))}, index=dates_day2)
        df2_day2 = pd.DataFrame({'ไอ': list(range(25, 57))}, index=dates_day2)

        mock_instance.interest_over_time.side_effect = [df1_day2, df2_day2]

        # Run Day 2 ingestion
        batch2 = ingestion.ingest()
        assert batch2.status == 'success'

        # Verify stitching metadata in batch notes
        assert 'Stitching' in batch2.notes
        assert 'factor=' in batch2.notes
        assert 'overlap=' in batch2.notes

        # Query only NEW data (Nov 9) and verify it was stitched
        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("""
                SELECT keyword, date, rsv_raw, rsv_stitched
                FROM raw_trenddata
                WHERE batch_id = ?
                  AND date = '2025-11-09'
                ORDER BY keyword
            """, (batch2.batch_id,))

            new_records = cursor.fetchall()

            # Verify NEW records have stitched values different from raw
            for rec in new_records:
                keyword, date, rsv_raw, rsv_stitched = rec
                # Stitched value should be scaled (not equal to raw for second batch)
                # Since we simulated higher values, scaling factor should adjust them
                assert rsv_stitched != rsv_raw, \
                    f"Expected stitching to scale Nov 9 data for {keyword}"

    @patch('services.trends_fetcher.TrendReq')
    def test_stitching_creates_continuous_time_series(self, mock_trend_req, test_db_instance, test_config):
        """
        Test that stitching produces continuous time series without level jumps.

        Per spec.md SC-004: Stitched series shows no jumps >20% on stable days
        """
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        mock_instance = MagicMock()
        mock_trend_req.return_value = mock_instance

        # Simulate stable search behavior (small variation)
        base_value = 50
        variation = 2  # ±2 variation

        # Day 1: Oct 8 - Nov 8
        dates_day1 = pd.date_range('2025-10-08', periods=32, freq='D')
        values_day1 = [base_value + (i % variation) for i in range(32)]
        df1 = pd.DataFrame({'ไข้': values_day1}, index=dates_day1)

        mock_instance.interest_over_time.side_effect = [df1]
        batch1 = ingestion.ingest()

        # Day 2: Oct 9 - Nov 9 (simulate different normalization scale)
        # Raw values are doubled due to independent normalization
        dates_day2 = pd.date_range('2025-10-09', periods=32, freq='D')
        values_day2 = [(base_value + (i % variation)) * 2 for i in range(32)]
        df2 = pd.DataFrame({'ไข้': values_day2}, index=dates_day2)

        mock_instance.interest_over_time.side_effect = [df2]
        batch2 = ingestion.ingest()

        # Query stitched time series
        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("""
                SELECT date, rsv_stitched
                FROM raw_trenddata
                WHERE keyword = 'ไข้'
                ORDER BY date
            """)

            stitched_series = [(row[0], row[1]) for row in cursor.fetchall()]

            # Verify no large jumps in stitched values
            for i in range(1, len(stitched_series)):
                date_prev, val_prev = stitched_series[i-1]
                date_curr, val_curr = stitched_series[i]

                # Calculate percentage change
                pct_change = abs(val_curr - val_prev) / val_prev if val_prev != 0 else 0

                # Assert no jumps > 20% on consecutive days
                assert pct_change < 0.20, \
                    f"Large jump detected: {date_prev} ({val_prev:.1f}) → {date_curr} ({val_curr:.1f}), change={pct_change*100:.1f}%"

    @patch('services.trends_fetcher.TrendReq')
    def test_stitching_handles_zero_values(self, mock_trend_req, test_db_instance, test_config):
        """
        Test that stitching preserves zero values (no manufactured signal).

        Per spec.md FR-006: Zero preservation
        """
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        mock_instance = MagicMock()
        mock_trend_req.return_value = mock_instance

        # Day 1: Some zeros
        dates = pd.date_range('2025-10-08', periods=5, freq='D')
        df1 = pd.DataFrame({'ไข้': [0, 0, 0, 45, 50]}, index=dates)

        mock_instance.interest_over_time.side_effect = [df1]
        batch = ingestion.ingest()

        # Query and verify zeros preserved
        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("""
                SELECT date, rsv_raw, rsv_stitched
                FROM raw_trenddata
                WHERE keyword = 'ไข้' AND rsv_raw = 0
                ORDER BY date
            """)

            zero_records = cursor.fetchall()

            # Verify all zeros remain zero in stitched column
            for rec in zero_records:
                date, rsv_raw, rsv_stitched = rec
                assert rsv_raw == 0
                assert rsv_stitched == 0.0, \
                    f"Zero preservation failed: date={date}, rsv_stitched={rsv_stitched}"

    @patch('services.trends_fetcher.TrendReq')
    def test_idempotent_rerun_no_duplicates(self, mock_trend_req, test_db_instance, test_config):
        """
        Test that re-running ingestion doesn't create duplicates (UPSERT semantics).

        Per spec.md FR-015: Idempotent UPSERT
        Per spec.md SC-002: Zero duplicate records
        """
        db = test_db_instance
        config = test_config
        ingestion = IngestionService(db, config)

        mock_instance = MagicMock()
        mock_trend_req.return_value = mock_instance

        dates = pd.date_range('2025-10-08', periods=5, freq='D')
        df1 = pd.DataFrame({'ไข้': [45, 47, 50, 48, 52]}, index=dates)

        # Run ingestion twice with same data
        mock_instance.interest_over_time.side_effect = [df1, df1]

        batch1 = ingestion.ingest()
        rows_first = batch1.rows_written

        batch2 = ingestion.ingest()
        rows_updated = batch2.rows_updated

        # Verify second run updated existing records
        assert rows_updated > 0, "Second run should update existing records"

        # Verify no duplicates exist
        with db.get_connection(auto_commit=False) as conn:
            cursor = conn.execute("""
                SELECT keyword, date, COUNT(*) as cnt
                FROM raw_trenddata
                GROUP BY keyword, date
                HAVING cnt > 1
            """)

            duplicates = cursor.fetchall()
            assert len(duplicates) == 0, f"Duplicates found: {duplicates}"
