"""
Backfill Service

Handles historical data backfill operations:
- Calculates date ranges for backfill windows
- Chunks large backfills into weekly batches
- Progress logging for long-running operations

Constitution alignment:
- Principle IV: Provenance - Complete batch event metadata for backfill operations
- Principle VIII: Observability - Progress logging for long-running backfills
"""

import logging
from datetime import date, datetime, timedelta
from typing import Tuple, List, Optional

from lib.timezone_utils import ICT
from lib.db import DatabaseConnection
from lib.config import FetcherConfig
from services.trends_fetcher import TrendsFetcher
from models.batch_event import BatchEvent

logger = logging.getLogger(__name__)


def calculate_backfill_window(days: int) -> Tuple[date, date]:
    """
    Calculate date range for backfill operation.

    Returns a date range ending yesterday (T-1 in ICT timezone) and spanning
    the requested number of days. This ensures backfill fetches complete days
    with no partial data.

    Args:
        days: Number of days to backfill (must be >= 1)

    Returns:
        Tuple of (start_date, end_date) as date objects

    Raises:
        ValueError: If days < 1

    Examples:
        >>> # Today is 2025-11-05 ICT
        >>> start, end = calculate_backfill_window(days=90)
        >>> # Returns (2025-08-06, 2025-11-04) - 90 days ending yesterday

        >>> start, end = calculate_backfill_window(days=1)
        >>> # Returns (2025-11-04, 2025-11-04) - single day (yesterday)
    """
    # Validate input
    if days < 1:
        raise ValueError("days must be >= 1")

    # Calculate date range using ICT timezone
    today_ict = datetime.now(ICT).date()
    yesterday_ict = today_ict - timedelta(days=1)

    # Calculate start date: yesterday minus (days - 1)
    # Example: 90 days means yesterday - 89 days = 90 days total
    start_date = yesterday_ict - timedelta(days=days - 1)
    end_date = yesterday_ict

    return start_date, end_date


class BackfillService:
    """
    Service for handling historical data backfills with chunking and progress tracking.

    Breaks large backfills (e.g., 90 days) into smaller weekly chunks to:
    - Reduce API rate limit risk
    - Improve resilience to failures
    - Provide incremental progress feedback

    Constitution alignment:
    - Principle VIII: Observability - Progress logging for each chunk
    - Principle IV: Provenance - Complete batch event metadata
    """

    CHUNK_SIZE_DAYS = 7  # Weekly chunks

    def __init__(
        self,
        db: DatabaseConnection,
        config: Optional[FetcherConfig] = None,
        trends_fetcher: Optional[TrendsFetcher] = None
    ):
        """
        Initialize backfill service.

        Args:
            db: DatabaseConnection instance
            config: FetcherConfig instance (will create if not provided)
            trends_fetcher: Optional TrendsFetcher (will create if not provided)
        """
        self.db = db
        self.config = config or FetcherConfig()

        # Import here to avoid circular dependency
        from lib.db_operations import DBOperations
        self.db_ops = DBOperations(db)

        # Initialize TrendsFetcher
        if trends_fetcher:
            self.trends_fetcher = trends_fetcher
        else:
            self.trends_fetcher = TrendsFetcher(
                province=self.config.province,
                jitter_range=tuple(self.config.jitter_minutes)
            )

    def backfill_initial(
        self,
        keywords: List[str],
        days: int = 90
    ) -> BatchEvent:
        """
        Perform initial backfill with weekly chunking and progress logging.

        Args:
            keywords: List of keywords to fetch
            days: Number of days to backfill (default: 90)

        Returns:
            Completed BatchEvent instance with aggregated results

        Raises:
            PyTrendsException: If fetch fails
            DatabaseException: If persistence fails
        """
        logger.info(f"Starting initial backfill: {days} days for {len(keywords)} keywords")

        # Calculate overall date range
        start_date, end_date = calculate_backfill_window(days=days)

        # Create parent batch event
        from models.batch_event import BatchEvent
        batch_event = BatchEvent.create(
            batch_type='initial_backfill',
            keywords=keywords,
            start_date=start_date,
            end_date=end_date,
            notes=f"Initial backfill: {days} days in weekly chunks"
        )

        # Insert batch event
        self.db_ops.insert_batch_event(batch_event)

        # Calculate chunks
        chunks = self._calculate_chunks(start_date, end_date)
        total_chunks = len(chunks)

        logger.info(f"Backfill will process {total_chunks} weekly chunks")

        # Process each chunk
        total_rows_written = 0
        total_rows_updated = 0
        total_rows_missing = 0

        from lib.exceptions import PyTrendsException, DatabaseException

        try:
            for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
                chunk_days = (chunk_end - chunk_start).days + 1
                logger.info(
                    f"Processing chunk {i}/{total_chunks}: "
                    f"{chunk_start} to {chunk_end} ({chunk_days} days)"
                )

                # Fetch data for this chunk
                try:
                    records = self.trends_fetcher.fetch_with_batching(
                        keywords=keywords,
                        start_date=chunk_start,
                        end_date=chunk_end,
                        batch_id=batch_event.batch_id,
                        granularity='daily'
                    )

                    # Persist records
                    if records:
                        result = self.db_ops.upsert_rsv_records(records)
                        chunk_rows_written = result['inserted']
                        chunk_rows_updated = result['updated']

                        total_rows_written += chunk_rows_written
                        total_rows_updated += chunk_rows_updated

                        # Calculate missing records for this chunk
                        expected_chunk_records = len(keywords) * chunk_days
                        chunk_rows_missing = expected_chunk_records - len(records)
                        total_rows_missing += chunk_rows_missing

                        logger.info(
                            f"Chunk {i}/{total_chunks} complete: "
                            f"{chunk_rows_written} rows written, "
                            f"{chunk_rows_updated} updated, "
                            f"{chunk_rows_missing} missing. "
                            f"Progress: {i}/{total_chunks} chunks ({i*100//total_chunks}%)"
                        )
                    else:
                        # No data returned for this chunk
                        expected_chunk_records = len(keywords) * chunk_days
                        total_rows_missing += expected_chunk_records

                        logger.warning(
                            f"Chunk {i}/{total_chunks}: No data returned for "
                            f"{chunk_start} to {chunk_end}"
                        )

                except PyTrendsException as e:
                    logger.error(f"Chunk {i}/{total_chunks} failed: {e}")
                    # Continue with next chunk instead of failing entire backfill
                    expected_chunk_records = len(keywords) * chunk_days
                    total_rows_missing += expected_chunk_records

            # Finalize batch event
            if total_rows_missing > 0:
                batch_event.mark_degraded(
                    rows_written=total_rows_written,
                    rows_missing=total_rows_missing,
                    reason=f"Missing {total_rows_missing} records across {total_chunks} chunks"
                )
                batch_event.rows_updated = total_rows_updated
            else:
                batch_event.mark_success(
                    rows_written=total_rows_written,
                    rows_updated=total_rows_updated,
                    notes=f"Complete backfill: {total_chunks} chunks processed"
                )

            self.db_ops.update_batch_event(batch_event)

            logger.info(
                f"Backfill complete: {total_rows_written} rows written, "
                f"{total_rows_updated} updated, {total_rows_missing} missing, "
                f"status={batch_event.status}"
            )

            return batch_event

        except Exception as e:
            # Mark batch as failed
            batch_event.mark_fail(str(e))
            batch_event.rows_written = total_rows_written
            batch_event.rows_updated = total_rows_updated
            self.db_ops.update_batch_event(batch_event)
            raise

    def _calculate_chunks(
        self,
        start_date: date,
        end_date: date
    ) -> List[Tuple[date, date]]:
        """
        Break date range into weekly chunks.

        Args:
            start_date: Overall start date
            end_date: Overall end date

        Returns:
            List of (chunk_start, chunk_end) tuples

        Examples:
            >>> # 90 days -> ~13 chunks of 7 days
            >>> chunks = service._calculate_chunks(
            ...     date(2025, 8, 6),
            ...     date(2025, 11, 4)
            ... )
            >>> len(chunks)
            13
        """
        chunks = []
        current_start = start_date

        while current_start <= end_date:
            # Calculate chunk end (either CHUNK_SIZE_DAYS ahead or end_date)
            chunk_end = min(
                current_start + timedelta(days=self.CHUNK_SIZE_DAYS - 1),
                end_date
            )

            chunks.append((current_start, chunk_end))

            # Move to next chunk
            current_start = chunk_end + timedelta(days=1)

        return chunks
