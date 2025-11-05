"""
Unit Tests for TrendsFetcher Service

Tests pytrends wrapper with mocked responses, error handling, and rate limiting.
Per Constitution Principle III: TDD - Write tests first, ensure they fail.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import date, datetime
import pandas as pd
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from services.trends_fetcher import TrendsFetcher
from lib.exceptions import PyTrendsException
from models.rsv_record import RSVRecord


class TestTrendsFetcherInitialization:
    """Test TrendsFetcher initialization and configuration."""

    def test_init_with_defaults(self):
        """Test initialization with default province TH-50."""
        fetcher = TrendsFetcher()

        assert fetcher.province == 'TH-50'
        assert fetcher.jitter_range == (3, 5)
        assert fetcher.hl == 'th'
        assert fetcher.tz == 420  # UTC+7

    def test_init_with_custom_jitter(self):
        """Test initialization with custom jitter range."""
        fetcher = TrendsFetcher(jitter_range=(1, 2))

        assert fetcher.jitter_range == (1, 2)

    def test_init_validates_province_constraint(self):
        """Test that non-TH-50 province raises error in MVP."""
        with pytest.raises(ValueError, match="MVP constraint.*TH-50"):
            TrendsFetcher(province='TH-10')


class TestDailyRSVFetch:
    """Test daily granularity RSV data fetching."""

    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_single_keyword(self, mock_pytrends_class):
        """Test fetching daily RSV for single keyword with mock pytrends."""
        # Setup mock
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        # Mock response data
        mock_data = pd.DataFrame({
            'ไข้': [45, 52, 48, 50, 47]
        }, index=pd.date_range('2025-11-01', periods=5, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher(province='TH-50')
        result = fetcher.fetch_daily_rsv(
            keywords=['ไข้'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 5),
            batch_id='batch_test_001'
        )

        # Verify results
        assert len(result) == 5
        assert all(isinstance(r, RSVRecord) for r in result)
        assert result[0].keyword == 'ไข้'
        assert result[0].date == date(2025, 11, 1)
        assert result[0].rsv_raw == 45
        assert result[0].granularity == 'daily'
        assert result[0].quality == 'true'
        assert result[0].batch_id == 'batch_test_001'

    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_multiple_keywords(self, mock_pytrends_class):
        """Test fetching daily RSV for multiple keywords."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        # Mock data with multiple keywords
        mock_data = pd.DataFrame({
            'ไข้': [45, 52, 48],
            'ไอ': [30, 35, 33]
        }, index=pd.date_range('2025-11-01', periods=3, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher()
        result = fetcher.fetch_daily_rsv(
            keywords=['ไข้', 'ไอ'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 3),
            batch_id='batch_test_002'
        )

        # Should return records for both keywords
        assert len(result) == 6  # 3 dates × 2 keywords
        keywords_in_results = {r.keyword for r in result}
        assert keywords_in_results == {'ไข้', 'ไอ'}

    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_with_zeros(self, mock_pytrends_class):
        """Test that zero RSV values are preserved (not dropped)."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        # Mock data with zeros
        mock_data = pd.DataFrame({
            'ไข้': [0, 0, 10, 0, 5]
        }, index=pd.date_range('2025-11-01', periods=5, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher()
        result = fetcher.fetch_daily_rsv(
            keywords=['ไข้'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 5),
            batch_id='batch_test_003'
        )

        # Zeros should be preserved
        assert len(result) == 5
        assert result[0].rsv_raw == 0
        assert result[1].rsv_raw == 0
        assert result[2].rsv_raw == 10
        assert result[3].rsv_raw == 0
        assert result[4].rsv_raw == 5

        # All should have quality='true' (daily granularity)
        assert all(r.quality == 'true' for r in result)

    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_handles_nan(self, mock_pytrends_class):
        """Test handling of NaN values in pytrends response."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        # Mock data with NaN
        mock_data = pd.DataFrame({
            'ไข้': [45, float('nan'), 48]
        }, index=pd.date_range('2025-11-01', periods=3, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher()
        result = fetcher.fetch_daily_rsv(
            keywords=['ไข้'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 3),
            batch_id='batch_test_004'
        )

        # NaN should be converted to 0
        assert len(result) == 3
        assert result[1].rsv_raw == 0


class TestWeeklyRSVFetch:
    """Test weekly granularity RSV data fetching (for resampling)."""

    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_weekly_rsv(self, mock_pytrends_class):
        """Test fetching weekly RSV for sparse-day fallback."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        # Mock weekly data
        mock_data = pd.DataFrame({
            'ไข้': [45, 52, 48]
        }, index=pd.date_range('2025-11-01', periods=3, freq='W'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher()
        result = fetcher.fetch_weekly_rsv(
            keywords=['ไข้'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 21),
            batch_id='batch_test_005'
        )

        # Verify weekly granularity
        assert len(result) == 3
        assert all(r.granularity == 'weekly' for r in result)
        assert all(r.quality == 'coarse' for r in result)
        assert all(r.impute_method == 'weekly_flat' for r in result)


class TestErrorHandling:
    """Test error handling and retries."""

    @patch('services.trends_fetcher.TrendReq')
    def test_pytrends_connection_error(self, mock_pytrends_class):
        """Test handling of network errors when calling pytrends."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends
        mock_pytrends.interest_over_time.side_effect = ConnectionError("Network unreachable")

        fetcher = TrendsFetcher()

        with pytest.raises(PyTrendsException, match="pytrends API call failed"):
            fetcher.fetch_daily_rsv(
                keywords=['ไข้'],
                start_date=date(2025, 11, 1),
                end_date=date(2025, 11, 5),
                batch_id='batch_test_006'
            )

    @patch('services.trends_fetcher.TrendReq')
    def test_pytrends_invalid_response_none(self, mock_pytrends_class):
        """Test handling of None response from pytrends."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends
        mock_pytrends.interest_over_time.return_value = None

        fetcher = TrendsFetcher()

        with pytest.raises(PyTrendsException, match="pytrends returned empty data"):
            fetcher.fetch_daily_rsv(
                keywords=['ไข้'],
                start_date=date(2025, 11, 1),
                end_date=date(2025, 11, 5),
                batch_id='batch_test_007'
            )

    @patch('services.trends_fetcher.TrendReq')
    def test_pytrends_invalid_response_empty(self, mock_pytrends_class):
        """Test handling of empty DataFrame from pytrends."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends
        mock_pytrends.interest_over_time.return_value = pd.DataFrame()

        fetcher = TrendsFetcher()

        with pytest.raises(PyTrendsException, match="pytrends returned empty data"):
            fetcher.fetch_daily_rsv(
                keywords=['ไข้'],
                start_date=date(2025, 11, 1),
                end_date=date(2025, 11, 5),
                batch_id='batch_test_008'
            )


class TestRateLimiting:
    """Test rate limiting and jitter implementation."""

    @patch('services.trends_fetcher.TrendReq')
    @patch('services.trends_fetcher.time.sleep')
    def test_jitter_applied_between_batches(self, mock_sleep, mock_pytrends_class):
        """Test that 3-5 second jitter is applied between keyword batches."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        # Mock response for each batch
        mock_data = pd.DataFrame({
            'ไข้': [45]
        }, index=pd.date_range('2025-11-01', periods=1, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher(jitter_range=(3, 5))

        # Fetch with batching (7 keywords = 2 batches of 5)
        fetcher.fetch_with_batching(
            keywords=['k1', 'k2', 'k3', 'k4', 'k5', 'k6', 'k7'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 1),
            batch_id='batch_test_009',
            granularity='daily',
            batch_size=5
        )

        # Sleep should be called once (between 2 batches)
        assert mock_sleep.call_count == 1
        sleep_duration = mock_sleep.call_args[0][0]
        assert 3 <= sleep_duration <= 5

    def test_jitter_range_configuration(self):
        """Test that jitter range can be configured."""
        fetcher = TrendsFetcher(jitter_range=(1, 2))
        assert fetcher.jitter_range == (1, 2)


class TestProvinceScoping:
    """Test TH-50 province scoping for pytrends requests."""

    @patch('services.trends_fetcher.TrendReq')
    def test_province_parameter_passed_to_pytrends(self, mock_pytrends_class):
        """Test that TH-50 province code is passed to pytrends API."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        mock_data = pd.DataFrame({
            'ไข้': [45]
        }, index=pd.date_range('2025-11-01', periods=1, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher(province='TH-50')
        fetcher.fetch_daily_rsv(
            keywords=['ไข้'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 1),
            batch_id='batch_test_010'
        )

        # Verify build_payload was called with geo='TH-50'
        mock_pytrends.build_payload.assert_called_once()
        call_kwargs = mock_pytrends.build_payload.call_args[1]
        assert call_kwargs['geo'] == 'TH-50'


class TestGranularityHandling:
    """Test granularity field assignment."""

    @patch('services.trends_fetcher.TrendReq')
    def test_daily_fetch_sets_granularity_daily(self, mock_pytrends_class):
        """Test that daily fetches set granularity='daily'."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        mock_data = pd.DataFrame({
            'ไข้': [45]
        }, index=pd.date_range('2025-11-01', periods=1, freq='D'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher()
        result = fetcher.fetch_daily_rsv(
            keywords=['ไข้'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 1),
            batch_id='batch_test_011'
        )

        assert all(r.granularity == 'daily' for r in result)

    @patch('services.trends_fetcher.TrendReq')
    def test_weekly_fetch_sets_granularity_weekly(self, mock_pytrends_class):
        """Test that weekly fetches set granularity='weekly'."""
        mock_pytrends = MagicMock()
        mock_pytrends_class.return_value = mock_pytrends

        mock_data = pd.DataFrame({
            'ไข้': [45]
        }, index=pd.date_range('2025-11-01', periods=1, freq='W'))
        mock_pytrends.interest_over_time.return_value = mock_data

        fetcher = TrendsFetcher()
        result = fetcher.fetch_weekly_rsv(
            keywords=['ไข้'],
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 7),
            batch_id='batch_test_012'
        )

        assert all(r.granularity == 'weekly' for r in result)
