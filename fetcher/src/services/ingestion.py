"""
Ingestion Service

Orchestrates daily RSV data ingestion workflow:
1. Create batch event
2. Fetch keywords from config
3. Fetch RSV data from Google Trends
4. Persist to database
5. Update batch event status
6. Emit structured logs

Constitution alignment:
- Principle VIII: Observability & Data Health - Structured logging with batch metadata
- Principle IV: Data Governance - Complete provenance via batch events
"""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any

from lib.db import DatabaseConnection
from lib.db_operations import DBOperations
from lib.config import FetcherConfig
from lib.logging_utils import log_batch_event
from lib.exceptions import PyTrendsException, DatabaseException, ValidationException
from models.batch_event import BatchEvent
from models.rsv_record import RSVRecord
from services.trends_fetcher import TrendsFetcher

logger = logging.getLogger(__name__)


class IngestionService:
    """
    RSV data ingestion orchestration service.

    Manages complete ingestion workflow from fetch to persistence,
    with error handling and comprehensive logging.
    """

    def __init__(
        self,
        db: DatabaseConnection,
        config: FetcherConfig,
        trends_fetcher: Optional[TrendsFetcher] = None
    ):
        """
        Initialize ingestion service.

        Args:
            db: DatabaseConnection instance
            config: FetcherConfig instance
            trends_fetcher: Optional TrendsFetcher (will create if not provided)
        """
        self.db = db
        self.config = config
        self.db_ops = DBOperations(db)

        # Initialize TrendsFetcher
        if trends_fetcher:
            self.trends_fetcher = trends_fetcher
        else:
            self.trends_fetcher = TrendsFetcher(
                province=config.province,
                jitter_range=tuple(config.jitter_minutes)
            )

        logger.info("IngestionService initialized")

    def ingest_daily(
        self,
        target_date: Optional[date] = None,
        batch_type: str = 'daily'
    ) -> BatchEvent:
        """
        Perform daily ingestion for a single date.

        Args:
            target_date: Date to fetch (default: yesterday)
            batch_type: Type of batch ('daily', 'manual')

        Returns:
            Completed BatchEvent instance

        Raises:
            PyTrendsException: If fetch fails
            DatabaseException: If persistence fails
        """
        # Default to yesterday (data usually available next day)
        if target_date is None:
            from lib.timezone_utils import today_ict
            target_date = today_ict() - timedelta(days=1)

        logger.info(f"Starting daily ingestion for {target_date}")

        # Load active keywords
        keyword_configs = self.db_ops.get_active_keywords()
        keywords = [kw.term for kw in keyword_configs]

        if not keywords:
            raise ValidationException("No active keywords configured")

        # Create batch event
        batch_event = BatchEvent.create(
            batch_type=batch_type,
            keywords=keywords,
            start_date=target_date,
            end_date=target_date,
            notes=f"Daily ingestion for {target_date}"
        )

        # Log batch start
        log_batch_event(
            logger,
            'info',
            f"Daily ingestion started: {target_date}",
            batch_id=batch_event.batch_id,
            keywords=keywords,
            window=batch_event.requested_window,
            status='running'
        )

        # Insert batch event (status='running')
        try:
            self.db_ops.insert_batch_event(batch_event)
        except DatabaseException as e:
            logger.error(f"Failed to create batch event: {e}")
            raise

        # Fetch RSV data
        try:
            records = self.trends_fetcher.fetch_with_batching(
                keywords=keywords,
                start_date=target_date,
                end_date=target_date,
                batch_id=batch_event.batch_id,
                granularity='daily'
            )

            if not records:
                # Mark as degraded (no data returned)
                batch_event.mark_degraded(
                    rows_written=0,
                    rows_missing=len(keywords),
                    reason=f"No RSV data returned for {target_date}"
                )
                self.db_ops.update_batch_event(batch_event)

                log_batch_event(
                    logger,
                    'warning',
                    f"Daily ingestion degraded: no data",
                    batch_id=batch_event.batch_id,
                    status='degraded',
                    rows_missing=len(keywords)
                )

                return batch_event

        except PyTrendsException as e:
            # Mark as failed
            batch_event.mark_fail(str(e))
            self.db_ops.update_batch_event(batch_event)

            log_batch_event(
                logger,
                'error',
                f"Daily ingestion failed: {e}",
                batch_id=batch_event.batch_id,
                status='fail',
                error=str(e)
            )

            raise

        # Persist RSV records
        try:
            result = self.db_ops.upsert_rsv_records(records)

            rows_written = result['inserted']
            rows_updated = result['updated']

            # Check for missing data
            expected_records = len(keywords) * 1  # 1 day
            rows_missing = expected_records - len(records)

            if rows_missing > 0:
                # Degraded: some keywords missing
                batch_event.mark_degraded(
                    rows_written=rows_written,
                    rows_missing=rows_missing,
                    reason=f"Missing data for {rows_missing} keyword-date combinations"
                )
                batch_event.rows_updated = rows_updated

                log_batch_event(
                    logger,
                    'warning',
                    f"Daily ingestion degraded: {rows_missing} missing",
                    batch_id=batch_event.batch_id,
                    status='degraded',
                    rows_written=rows_written,
                    rows_updated=rows_updated,
                    rows_missing=rows_missing
                )
            else:
                # Success: all data present
                batch_event.mark_success(
                    rows_written=rows_written,
                    rows_updated=rows_updated,
                    notes=f"Successfully ingested {len(keywords)} keywords for {target_date}"
                )

                log_batch_event(
                    logger,
                    'info',
                    f"Daily ingestion success",
                    batch_id=batch_event.batch_id,
                    status='success',
                    rows_written=rows_written,
                    rows_updated=rows_updated
                )

            # Update batch event
            self.db_ops.update_batch_event(batch_event)

        except DatabaseException as e:
            # Mark as failed
            batch_event.mark_fail(str(e))
            try:
                self.db_ops.update_batch_event(batch_event)
            except:
                pass  # Best effort

            log_batch_event(
                logger,
                'error',
                f"Daily ingestion failed: database error",
                batch_id=batch_event.batch_id,
                status='fail',
                error=str(e)
            )

            raise

        logger.info(
            f"Daily ingestion complete: batch_id={batch_event.batch_id}, "
            f"status={batch_event.status}, rows={rows_written}"
        )

        return batch_event

    def ingest_date_range(
        self,
        start_date: date,
        end_date: date,
        batch_type: str = 'backfill'
    ) -> BatchEvent:
        """
        Ingest RSV data for a date range (for backfill).

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            batch_type: Type of batch ('initial_backfill', 'recovery_backfill')

        Returns:
            Completed BatchEvent instance

        Raises:
            PyTrendsException: If fetch fails
            DatabaseException: If persistence fails
        """
        logger.info(f"Starting backfill ingestion: {start_date} to {end_date}")

        # Load active keywords
        keyword_configs = self.db_ops.get_active_keywords()
        keywords = [kw.term for kw in keyword_configs]

        if not keywords:
            raise ValidationException("No active keywords configured")

        # Create batch event
        batch_event = BatchEvent.create(
            batch_type=batch_type,
            keywords=keywords,
            start_date=start_date,
            end_date=end_date,
            notes=f"{batch_type} for {(end_date - start_date).days + 1} days"
        )

        log_batch_event(
            logger,
            'info',
            f"Backfill ingestion started: {start_date} to {end_date}",
            batch_id=batch_event.batch_id,
            keywords=keywords,
            window=batch_event.requested_window,
            status='running'
        )

        # Insert batch event
        self.db_ops.insert_batch_event(batch_event)

        # Fetch RSV data for full range
        try:
            records = self.trends_fetcher.fetch_with_batching(
                keywords=keywords,
                start_date=start_date,
                end_date=end_date,
                batch_id=batch_event.batch_id,
                granularity='daily'
            )

            if not records:
                batch_event.mark_degraded(
                    rows_written=0,
                    rows_missing=len(keywords) * ((end_date - start_date).days + 1),
                    reason=f"No RSV data returned for {start_date} to {end_date}"
                )
                self.db_ops.update_batch_event(batch_event)

                log_batch_event(
                    logger,
                    'warning',
                    "Backfill degraded: no data",
                    batch_id=batch_event.batch_id,
                    status='degraded'
                )

                return batch_event

        except PyTrendsException as e:
            batch_event.mark_fail(str(e))
            self.db_ops.update_batch_event(batch_event)

            log_batch_event(
                logger,
                'error',
                f"Backfill failed: {e}",
                batch_id=batch_event.batch_id,
                status='fail',
                error=str(e)
            )

            raise

        # Persist RSV records
        try:
            result = self.db_ops.upsert_rsv_records(records)

            rows_written = result['inserted']
            rows_updated = result['updated']

            # Check for missing data
            num_days = (end_date - start_date).days + 1
            expected_records = len(keywords) * num_days
            rows_missing = expected_records - len(records)

            if rows_missing > 0:
                batch_event.mark_degraded(
                    rows_written=rows_written,
                    rows_missing=rows_missing,
                    reason=f"Missing {rows_missing} of {expected_records} expected records"
                )
                batch_event.rows_updated = rows_updated

                log_batch_event(
                    logger,
                    'warning',
                    f"Backfill degraded: {rows_missing} missing",
                    batch_id=batch_event.batch_id,
                    status='degraded',
                    rows_written=rows_written,
                    rows_missing=rows_missing
                )
            else:
                batch_event.mark_success(
                    rows_written=rows_written,
                    rows_updated=rows_updated,
                    notes=f"Backfill complete: {num_days} days × {len(keywords)} keywords"
                )

                log_batch_event(
                    logger,
                    'info',
                    "Backfill success",
                    batch_id=batch_event.batch_id,
                    status='success',
                    rows_written=rows_written,
                    rows_updated=rows_updated
                )

            self.db_ops.update_batch_event(batch_event)

        except DatabaseException as e:
            batch_event.mark_fail(str(e))
            try:
                self.db_ops.update_batch_event(batch_event)
            except:
                pass

            log_batch_event(
                logger,
                'error',
                "Backfill failed: database error",
                batch_id=batch_event.batch_id,
                status='fail',
                error=str(e)
            )

            raise

        logger.info(
            f"Backfill complete: batch_id={batch_event.batch_id}, "
            f"status={batch_event.status}, rows={rows_written}"
        )

        return batch_event

    def ingest_with_initial_backfill_check(
        self,
        backfill_days: int = 90
    ) -> Optional[BatchEvent]:
        """
        Check if database is empty and trigger initial backfill if needed.

        This method implements the automatic 90-day backfill on first deployment
        (User Story 2). It detects empty database state and triggers a complete
        historical backfill, marking the batch event as 'initial_backfill' for
        provenance.

        If database already has data, this method skips the backfill and returns None,
        allowing normal daily ingestion to proceed.

        Args:
            backfill_days: Number of days to backfill (default: 90)

        Returns:
            BatchEvent if backfill was triggered, None if database already populated

        Raises:
            PyTrendsException: If backfill fetch fails
            DatabaseException: If persistence fails

        Examples:
            >>> # First deployment - empty database
            >>> service = IngestionService(db, config)
            >>> batch_event = service.ingest_with_initial_backfill_check()
            >>> # Triggers 90-day backfill, returns batch event with batch_type='initial_backfill'

            >>> # Subsequent runs - database has data
            >>> batch_event = service.ingest_with_initial_backfill_check()
            >>> # Returns None, allowing daily ingestion to proceed
        """
        # Check if database is empty
        is_empty = self._is_database_empty()

        if is_empty:
            logger.info(
                "Empty database detected - triggering initial backfill "
                f"({backfill_days} days)"
            )

            # Import here to avoid circular dependency
            from services.backfill import calculate_backfill_window

            # Calculate backfill window
            start_date, end_date = calculate_backfill_window(days=backfill_days)

            # Trigger backfill using existing ingest_date_range method
            batch_event = self.ingest_date_range(
                start_date=start_date,
                end_date=end_date,
                batch_type='initial_backfill'
            )

            logger.info(
                f"Initial backfill complete: {batch_event.rows_written} records written "
                f"(batch_id={batch_event.batch_id})"
            )

            return batch_event

        else:
            logger.debug("Database not empty - skipping initial backfill")
            return None

    def _is_database_empty(self) -> bool:
        """
        Check if raw_trenddata table is empty.

        Returns:
            True if raw_trenddata has zero rows, False otherwise
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata")
            count = cursor.fetchone()[0]
            return count == 0
