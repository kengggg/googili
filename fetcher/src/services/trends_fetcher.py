"""
TrendsFetcher Service

Wrapper around pytrends for fetching Google Trends RSV data.
Handles rate limiting, province scoping, and granularity selection.

Per research.md Decision 3: pytrends library for Google Trends access
Per research.md Decision 4: 3-5 second jitter for rate limiting

Constitution alignment:
- Principle VI: Clarity Over Cleverness - Simple, explicit API calls
- Principle IV: Data Governance - Province scoping enforced
"""

import time
import random
import logging
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError

from lib.exceptions import PyTrendsException, RateLimitException
from lib.config import FetcherConfig
from models.rsv_record import RSVRecord

logger = logging.getLogger(__name__)


class TrendsFetcher:
    """
    Google Trends RSV data fetcher with rate limiting and error handling.

    Handles:
    - Province scoping (TH-50 for Chiang Mai)
    - Daily and weekly granularity
    - Rate limiting with configurable jitter
    - Error handling and retries
    """

    def __init__(
        self,
        province: str = 'TH-50',
        jitter_range: tuple = (3, 5),
        hl: str = 'th',
        tz: int = 420,  # UTC+7 for Asia/Bangkok
        config: Optional[FetcherConfig] = None
    ):
        """
        Initialize TrendsFetcher.

        Args:
            province: ISO 3166-2 province code (default: TH-50 for Chiang Mai)
            jitter_range: Min/max seconds for rate limiting jitter (default: 3-5)
            hl: Language code for Google Trends (default: 'th' for Thai)
            tz: Timezone offset in minutes (default: 420 for UTC+7)
            config: Optional FetcherConfig for retry configuration

        Raises:
            ValueError: If province is not TH-50 (MVP constraint)
        """
        # MVP constraint: Only TH-50 supported
        if province != 'TH-50':
            raise ValueError(
                f"MVP constraint: Only TH-50 (Chiang Mai) supported. Got: {province}"
            )

        self.province = province
        self.jitter_range = jitter_range
        self.hl = hl
        self.tz = tz

        # Load retry configuration
        if config is None:
            config = FetcherConfig()
        self.config = config

        # Initialize pytrends (will be refreshed for each request batch)
        self._pytrends = None

        logger.info(
            f"TrendsFetcher initialized: province={province}, "
            f"jitter={jitter_range[0]}-{jitter_range[1]}s, "
            f"max_retries={self.config.max_retries}"
        )

    def _get_pytrends(self) -> TrendReq:
        """
        Get or create pytrends instance.

        Returns:
            TrendReq instance
        """
        if self._pytrends is None:
            self._pytrends = TrendReq(hl=self.hl, tz=self.tz)
        return self._pytrends

    def _apply_jitter(self):
        """Apply rate limiting jitter between requests."""
        jitter_seconds = random.uniform(self.jitter_range[0], self.jitter_range[1])
        logger.debug(f"Applying jitter: {jitter_seconds:.2f}s")
        time.sleep(jitter_seconds)

    def _format_timeframe(self, start_date: date, end_date: date) -> str:
        """
        Format date range for pytrends timeframe parameter.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Timeframe string (e.g., "2025-11-01 2025-11-05")
        """
        return f"{start_date.isoformat()} {end_date.isoformat()}"

    def _calculate_backoff(self, attempt: int, retry_after: Optional[int] = None) -> float:
        """
        Calculate backoff time for retry with exponential backoff and jitter.

        Args:
            attempt: Retry attempt number (0-indexed)
            retry_after: Optional Retry-After header value in seconds

        Returns:
            Backoff time in seconds with jitter applied
        """
        # If Retry-After header present and config allows, use it
        if retry_after is not None and self.config.respect_retry_after:
            base_backoff = retry_after
        else:
            # Exponential backoff: base * (multiplier ** attempt)
            base_backoff = self.config.backoff_base_seconds * (
                self.config.backoff_multiplier ** attempt
            )
            # Cap at max_backoff_seconds
            base_backoff = min(base_backoff, self.config.max_backoff_seconds)

        # Add ±20% jitter
        jitter_factor = random.uniform(0.8, 1.2)
        backoff_with_jitter = base_backoff * jitter_factor

        return backoff_with_jitter

    def _fetch_with_retry(self, pytrends: TrendReq) -> pd.DataFrame:
        """
        Fetch data from pytrends with exponential backoff retry on 429 errors.

        Args:
            pytrends: Configured TrendReq instance (build_payload already called)

        Returns:
            DataFrame with interest over time data

        Raises:
            RateLimitException: If max retries exhausted
            PyTrendsException: For other pytrends errors
        """
        attempt = 0
        max_attempts = self.config.max_retries + 1  # initial + retries

        while attempt < max_attempts:
            try:
                df = pytrends.interest_over_time()
                return df

            except TooManyRequestsError as e:
                attempt += 1

                if attempt >= max_attempts:
                    # Exhausted all retries
                    logger.error(f"Rate limited after {self.config.max_retries} retries")
                    raise RateLimitException(
                        f"Rate limited after {self.config.max_retries} retries"
                    ) from e

                # Extract Retry-After header if present
                retry_after = None
                if hasattr(e, 'response') and e.response is not None:
                    retry_after_header = e.response.headers.get('Retry-After')
                    if retry_after_header:
                        try:
                            retry_after = int(retry_after_header)
                        except ValueError:
                            pass  # Ignore invalid Retry-After values

                # Calculate backoff
                backoff_time = self._calculate_backoff(attempt - 1, retry_after)

                logger.warning(
                    f"HTTP 429 rate limit hit (attempt {attempt}/{max_attempts}). "
                    f"Retrying after {backoff_time:.1f}s backoff"
                )

                # Sleep with backoff
                time.sleep(backoff_time)

            except Exception as e:
                # Non-429 errors - don't retry
                raise PyTrendsException(f"pytrends API call failed: {e}") from e

        # Should never reach here
        raise RateLimitException(f"Rate limited after {self.config.max_retries} retries")

    def fetch_daily_rsv(
        self,
        keywords: List[str],
        start_date: date,
        end_date: date,
        batch_id: str
    ) -> List[RSVRecord]:
        """
        Fetch daily granularity RSV data for keywords.

        Args:
            keywords: List of Thai keywords to fetch
            start_date: Start date of window
            end_date: End date of window (inclusive)
            batch_id: Batch identifier for provenance

        Returns:
            List of RSVRecord instances

        Raises:
            PyTrendsException: If pytrends API call fails
        """
        logger.info(
            f"Fetching daily RSV: keywords={len(keywords)}, "
            f"window={start_date} to {end_date}"
        )

        records = []

        try:
            # Build payload for pytrends
            pytrends = self._get_pytrends()
            timeframe = self._format_timeframe(start_date, end_date)

            logger.debug(f"pytrends payload: kw_list={keywords}, timeframe={timeframe}, geo={self.province}")

            # Build interest over time query
            pytrends.build_payload(
                kw_list=keywords,
                timeframe=timeframe,
                geo=self.province
            )

            # Fetch data with retry on 429
            df = self._fetch_with_retry(pytrends)

            if df is None or df.empty:
                logger.warning(f"No data returned from pytrends for keywords={keywords}")
                raise PyTrendsException(
                    f"pytrends returned empty data for keywords: {keywords}"
                )

            # Drop 'isPartial' column if present
            if 'isPartial' in df.columns:
                df = df.drop(columns=['isPartial'])

            # Convert DataFrame to RSVRecord instances
            for keyword in keywords:
                if keyword not in df.columns:
                    logger.warning(f"Keyword '{keyword}' not in pytrends response")
                    continue

                for date_index, rsv_value in df[keyword].items():
                    # Convert pandas Timestamp to date
                    date_val = date_index.date() if hasattr(date_index, 'date') else date_index

                    # Handle NaN values (treat as 0)
                    if pd.isna(rsv_value):
                        rsv_value = 0

                    # Create RSVRecord
                    record = RSVRecord.from_pytrends_row(
                        keyword=keyword,
                        date_val=date_val,
                        rsv_value=int(rsv_value),
                        source_window_start=start_date,
                        batch_id=batch_id,
                        granularity='daily'
                    )
                    records.append(record)

            logger.info(f"Fetched {len(records)} daily RSV records")

        except (RateLimitException, PyTrendsException):
            # Re-raise rate limit and pytrends exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Failed to fetch daily RSV: {e}", exc_info=True)
            raise PyTrendsException(f"pytrends API call failed: {e}") from e

        return records

    def fetch_weekly_rsv(
        self,
        keywords: List[str],
        start_date: date,
        end_date: date,
        batch_id: str
    ) -> List[RSVRecord]:
        """
        Fetch weekly granularity RSV data for keywords (sparse-day fallback).

        Args:
            keywords: List of Thai keywords to fetch
            start_date: Start date of window
            end_date: End date of window (inclusive)
            batch_id: Batch identifier for provenance

        Returns:
            List of RSVRecord instances with granularity='weekly'

        Raises:
            PyTrendsException: If pytrends API call fails
        """
        logger.info(
            f"Fetching weekly RSV: keywords={len(keywords)}, "
            f"window={start_date} to {end_date}"
        )

        records = []

        try:
            # For weekly data, need longer timeframe (pytrends switches to weekly automatically)
            # Use "today 3-m" format for last 3 months
            pytrends = self._get_pytrends()

            # Calculate timeframe for weekly (need longer period)
            # For weekly granularity, pytrends requires wider window
            extended_start = start_date - timedelta(days=90)
            timeframe = self._format_timeframe(extended_start, end_date)

            logger.debug(f"pytrends payload (weekly): kw_list={keywords}, timeframe={timeframe}, geo={self.province}")

            pytrends.build_payload(
                kw_list=keywords,
                timeframe=timeframe,
                geo=self.province
            )

            # Fetch data with retry on 429
            df = self._fetch_with_retry(pytrends)

            if df is None or df.empty:
                logger.warning(f"No weekly data returned from pytrends for keywords={keywords}")
                raise PyTrendsException(
                    f"pytrends returned empty data for keywords: {keywords}"
                )

            # Drop 'isPartial' column if present
            if 'isPartial' in df.columns:
                df = df.drop(columns=['isPartial'])

            # Filter to requested date range
            df = df[(df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))]

            # Convert DataFrame to RSVRecord instances
            for keyword in keywords:
                if keyword not in df.columns:
                    logger.warning(f"Keyword '{keyword}' not in pytrends response")
                    continue

                for date_index, rsv_value in df[keyword].items():
                    date_val = date_index.date() if hasattr(date_index, 'date') else date_index

                    if pd.isna(rsv_value):
                        rsv_value = 0

                    record = RSVRecord.from_pytrends_row(
                        keyword=keyword,
                        date_val=date_val,
                        rsv_value=int(rsv_value),
                        source_window_start=start_date,
                        batch_id=batch_id,
                        granularity='weekly'
                    )
                    record.impute_method = 'weekly_flat'
                    records.append(record)

            logger.info(f"Fetched {len(records)} weekly RSV records")

        except (RateLimitException, PyTrendsException):
            # Re-raise rate limit and pytrends exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Failed to fetch weekly RSV: {e}", exc_info=True)
            raise PyTrendsException(f"pytrends API call failed: {e}") from e

        return records

    def fetch_with_batching(
        self,
        keywords: List[str],
        start_date: date,
        end_date: date,
        batch_id: str,
        granularity: str = 'daily',
        batch_size: int = 5
    ) -> List[RSVRecord]:
        """
        Fetch RSV data with keyword batching and rate limiting.

        Pytrends has limits on number of keywords per request (~5).
        This method batches keywords and applies jitter between batches.

        Args:
            keywords: List of Thai keywords to fetch
            start_date: Start date of window
            end_date: End date of window
            batch_id: Batch identifier for provenance
            granularity: 'daily' or 'weekly'
            batch_size: Keywords per batch (default: 5)

        Returns:
            List of all RSVRecord instances from all batches

        Raises:
            PyTrendsException: If any batch fails
        """
        all_records = []

        # Split keywords into batches
        for i in range(0, len(keywords), batch_size):
            batch_keywords = keywords[i:i + batch_size]

            logger.info(
                f"Fetching batch {i // batch_size + 1}/{(len(keywords) + batch_size - 1) // batch_size}: "
                f"{len(batch_keywords)} keywords"
            )

            # Fetch data for this batch
            if granularity == 'daily':
                batch_records = self.fetch_daily_rsv(
                    batch_keywords,
                    start_date,
                    end_date,
                    batch_id
                )
            elif granularity == 'weekly':
                batch_records = self.fetch_weekly_rsv(
                    batch_keywords,
                    start_date,
                    end_date,
                    batch_id
                )
            else:
                raise ValueError(f"Invalid granularity: {granularity}")

            all_records.extend(batch_records)

            # Apply jitter between batches (except after last batch)
            if i + batch_size < len(keywords):
                self._apply_jitter()

        logger.info(f"Fetched {len(all_records)} total RSV records across all batches")
        return all_records
