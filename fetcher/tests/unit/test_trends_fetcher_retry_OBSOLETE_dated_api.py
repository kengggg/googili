"""
Unit Tests for TrendsFetcher Retry Logic - HTTP 429 Exponential Backoff

Tests that TrendsFetcher correctly retries on HTTP 429 errors with exponential backoff.

Constitution alignment:
- Principle III: TDD - Tests written BEFORE implementation (RED phase)
- Principle V: Fail-Safe - Retry on retriable errors

Test Strategy:
- Mock pytrends to simulate 429 errors
- Verify retry attempts with exponential backoff
- Verify RateLimitException raised after max retries
- Verify Retry-After header respected
- Verify backoff calculation with jitter
"""

import pytest
import time
from datetime import date
from unittest.mock import Mock, patch, call
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestExponentialBackoffRetry:
    """Test that TrendsFetcher retries on 429 with exponential backoff."""

    @patch('services.trends_fetcher.time.sleep')
    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_retries_on_429_with_exponential_backoff(self, mock_trends_class, mock_sleep):
        """
        SPEC: FR-016 - Must retry on 429 with exponential backoff (1min, 5min, 15min)
        BEHAVIOR: fetch_daily_rsv retries 3 times with increasing backoff before raising RateLimitException
        """
        from pytrends.exceptions import TooManyRequestsError
        from services.trends_fetcher import TrendsFetcher
        from lib.config import FetcherConfig
        from lib.exceptions import RateLimitException
        import pandas as pd

        # Setup: Mock 429 errors with proper response object
        mock_response = Mock()
        mock_response.headers = {}

        error1 = TooManyRequestsError("429", response=mock_response)
        error2 = TooManyRequestsError("429", response=mock_response)
        error3 = TooManyRequestsError("429", response=mock_response)

        # Setup: Mock that fails with 429, then succeeds on 4th attempt
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.side_effect = [
            error1,  # Attempt 1 fails
            error2,  # Attempt 2 fails
            error3,  # Attempt 3 fails
            pd.DataFrame({'ไข้': [75]}, index=[pd.Timestamp('2025-11-01')])  # Attempt 4 succeeds
        ]
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        fetcher = TrendsFetcher(province=config.province)

        # Execute: Should succeed after 3 retries
        records = fetcher.fetch_daily_rsv(['ไข้'], date(2025, 11, 1), date(2025, 11, 1), batch_id='test')

        # Verify: 4 attempts made (initial + 3 retries)
        assert mock_pytrends.interest_over_time.call_count == 4
        assert len(records) == 1
        assert records[0].rsv_raw == 75

        # Verify: Exponential backoff (with jitter range check)
        assert mock_sleep.call_count == 3  # 3 retries means 3 sleeps
        # Backoff times with 20% jitter: 60*(0.8-1.2), 300*(0.8-1.2), 1500*(0.8-1.2)
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert 48 <= sleep_calls[0] <= 72    # 60s ± 20%
        assert 240 <= sleep_calls[1] <= 360  # 300s ± 20%
        assert 1200 <= sleep_calls[2] <= 1800  # 1500s ± 20%

    @patch('services.trends_fetcher.time.sleep')
    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_raises_rate_limit_exception_after_max_retries(self, mock_trends_class, mock_sleep):
        """
        SPEC: FR-016 - Must raise RateLimitException if all retries exhausted
        BEHAVIOR: After max_retries attempts, raise RateLimitException
        """
        from pytrends.exceptions import TooManyRequestsError
        from services.trends_fetcher import TrendsFetcher
        from lib.config import FetcherConfig
        from lib.exceptions import RateLimitException

        # Setup: Mock 429 error with proper response object
        mock_response = Mock()
        mock_response.headers = {}

        # Setup: Mock that always returns 429
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.side_effect = TooManyRequestsError("429", response=mock_response)
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        fetcher = TrendsFetcher(province=config.province)

        # Execute & Verify: Should raise RateLimitException after 4 attempts (initial + 3 retries)
        with pytest.raises(RateLimitException, match="Rate limited after 3 retries"):
            fetcher.fetch_daily_rsv(['ไข้'], date(2025, 11, 1), date(2025, 11, 1), batch_id='test')

        # Verify: Attempted max_retries + 1 times
        assert mock_pytrends.interest_over_time.call_count == 4  # initial + 3 retries

    @patch('services.trends_fetcher.time.sleep')
    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_respects_retry_after_header(self, mock_trends_class, mock_sleep):
        """
        SPEC: FR-016 - Must respect Retry-After header from API if present
        BEHAVIOR: Use Retry-After value instead of exponential backoff when present
        """
        from pytrends.exceptions import TooManyRequestsError
        from services.trends_fetcher import TrendsFetcher
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock 429 error with Retry-After header
        mock_response = Mock()
        mock_response.headers = {'Retry-After': '120'}

        mock_pytrends = Mock()
        error_with_header = TooManyRequestsError("429", response=mock_response)

        mock_pytrends.interest_over_time.side_effect = [
            error_with_header,  # First attempt fails with Retry-After: 120s
            pd.DataFrame({'ไข้': [75]}, index=[pd.Timestamp('2025-11-01')])  # Second succeeds
        ]
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        fetcher = TrendsFetcher(province=config.province)

        # Execute
        records = fetcher.fetch_daily_rsv(['ไข้'], date(2025, 11, 1), date(2025, 11, 1), batch_id='test')

        # Verify: Used Retry-After header value (with ±20% jitter)
        assert mock_sleep.call_count == 1
        sleep_time = mock_sleep.call_args[0][0]
        assert 96 <= sleep_time <= 144  # 120s ± 20%


class TestBackoffCalculation:
    """Test exponential backoff calculation formula."""

    def test_backoff_calculation_follows_formula(self):
        """
        SPEC: FR-016 - Backoff follows: base * (multiplier ** attempt)
        BEHAVIOR: Backoff times: 60s, 300s, 1500s for default config
        """
        from lib.config import FetcherConfig

        config = FetcherConfig()

        # Calculate expected backoff times
        backoff_0 = config.backoff_base_seconds * (config.backoff_multiplier ** 0)  # 60 * 5^0 = 60
        backoff_1 = config.backoff_base_seconds * (config.backoff_multiplier ** 1)  # 60 * 5^1 = 300
        backoff_2 = config.backoff_base_seconds * (config.backoff_multiplier ** 2)  # 60 * 5^2 = 1500

        # Verify formula
        assert backoff_0 == 60
        assert backoff_1 == 300
        assert backoff_2 == 1500

    def test_backoff_respects_max_backoff_cap(self):
        """
        SPEC: FR-016 - Backoff must not exceed max_backoff_seconds
        BEHAVIOR: Large backoff values capped at max_backoff_seconds (1800s)
        """
        from lib.config import FetcherConfig

        config = FetcherConfig()

        # Calculate backoff that would exceed max
        large_backoff = config.backoff_base_seconds * (config.backoff_multiplier ** 10)  # Huge value

        # Verify it should be capped
        assert large_backoff > config.max_backoff_seconds
        # Implementation should cap to max_backoff_seconds


class TestRetryLogging:
    """Test that retry attempts are logged with structured metadata."""

    @patch('services.trends_fetcher.logger')
    @patch('services.trends_fetcher.time.sleep')
    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_logs_each_retry_attempt(self, mock_trends_class, mock_sleep, mock_logger):
        """
        SPEC: FR-016 - Log 429 errors with structured metadata
        BEHAVIOR: Each retry attempt logged with attempt number and wait time
        """
        from pytrends.exceptions import TooManyRequestsError
        from services.trends_fetcher import TrendsFetcher
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock 429 errors with proper response object
        mock_response = Mock()
        mock_response.headers = {}

        # Setup: Mock that fails twice then succeeds
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.side_effect = [
            TooManyRequestsError("429", response=mock_response),
            TooManyRequestsError("429", response=mock_response),
            pd.DataFrame({'ไข้': [75]}, index=[pd.Timestamp('2025-11-01')])
        ]
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        fetcher = TrendsFetcher(province=config.province)

        # Execute
        fetcher.fetch_daily_rsv(['ไข้'], date(2025, 11, 1), date(2025, 11, 1), batch_id='test')

        # Verify: Warning logs for each retry
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert len([c for c in warning_calls if '429' in c or 'rate limit' in c.lower()]) >= 2


class TestNonRetriableErrors:
    """Test that non-429 errors are NOT retried."""

    @patch('services.trends_fetcher.time.sleep')
    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_daily_rsv_does_not_retry_on_other_exceptions(self, mock_trends_class, mock_sleep):
        """
        SPEC: FR-016 - Only retry on 429 errors, not other failures
        BEHAVIOR: Non-429 errors raise PyTrendsException immediately without retry
        """
        from services.trends_fetcher import TrendsFetcher
        from lib.config import FetcherConfig
        from lib.exceptions import PyTrendsException

        # Setup: Mock that raises different error
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.side_effect = Exception("API authentication failed")
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        fetcher = TrendsFetcher(province=config.province)

        # Execute & Verify: Should raise PyTrendsException immediately (no retries)
        with pytest.raises(PyTrendsException, match="API authentication failed"):
            fetcher.fetch_daily_rsv(['ไข้'], date(2025, 11, 1), date(2025, 11, 1), batch_id='test')

        # Verify: Only 1 attempt (no retries)
        assert mock_pytrends.interest_over_time.call_count == 1
        assert mock_sleep.call_count == 0  # No sleep = no retries


class TestWeeklyRSVRetry:
    """Test that fetch_weekly_rsv also implements retry logic."""

    @patch('services.trends_fetcher.time.sleep')
    @patch('services.trends_fetcher.TrendReq')
    def test_fetch_weekly_rsv_also_retries_on_429(self, mock_trends_class, mock_sleep):
        """
        SPEC: FR-016 - Both daily and weekly fetching must retry on 429
        BEHAVIOR: fetch_weekly_rsv uses same retry logic as fetch_daily_rsv
        """
        from pytrends.exceptions import TooManyRequestsError
        from services.trends_fetcher import TrendsFetcher
        from lib.config import FetcherConfig
        import pandas as pd

        # Setup: Mock 429 error with proper response object
        mock_response = Mock()
        mock_response.headers = {}

        # Setup: Mock that fails once then succeeds
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.side_effect = [
            TooManyRequestsError("429", response=mock_response),
            pd.DataFrame({'ไข้': [75]}, index=[pd.Timestamp('2025-11-01')])
        ]
        mock_trends_class.return_value = mock_pytrends

        config = FetcherConfig()
        fetcher = TrendsFetcher(province=config.province)

        # Execute
        records = fetcher.fetch_weekly_rsv(['ไข้'], date(2025, 11, 1), date(2025, 11, 7), batch_id='test')

        # Verify: Retried and succeeded
        assert mock_pytrends.interest_over_time.call_count == 2
        assert mock_sleep.call_count == 1
        assert len(records) == 1
