"""
Ingestion Service

Simplified ingestion workflow for past 30 days of daily RSV data:
1. Create batch event
2. Fetch keywords from config
3. Fetch RSV data using 'today 1-m' timeframe
4. Persist to database
5. Update batch event status
6. Emit structured logs

Constitution alignment:
- Principle VIII: Observability & Data Health - Structured logging with batch metadata
- Principle IV: Data Governance - Complete provenance via batch events
"""

import logging
from typing import Optional

from lib.db import DatabaseConnection
from lib.db_operations import DBOperations
from lib.config import FetcherConfig
from lib.logging_utils import log_batch_event
from lib.exceptions import PyTrendsException, DatabaseException, ValidationException
from models.batch_event import BatchEvent
from services.trends_fetcher import TrendsFetcher

logger = logging.getLogger(__name__)


class IngestionService:
    """
    RSV data ingestion orchestration service.

    Simplified to fetch past 30 days of daily RSV data using pytrends 'today 1-m' format.
    Idempotent - safe to re-run.
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
                jitter_range=tuple(config.jitter_seconds),
                hl=config.language,
                config=config
            )

        logger.info("IngestionService initialized")

    def ingest(self, batch_type: str = 'ingestion') -> BatchEvent:
        """
        Fetch past 30 days of daily RSV data using pytrends 'today 1-m' format.

        Simple, idempotent ingestion - safe to re-run. Upserts data into database.

        Args:
            batch_type: Type of batch for provenance (default: 'ingestion')

        Returns:
            Completed BatchEvent instance

        Raises:
            PyTrendsException: If fetch fails
            DatabaseException: If persistence fails
            ValidationException: If no active keywords configured
        """
        logger.info("Starting RSV ingestion (past 30 days)")

        # Load active keywords
        keyword_configs = self.db_ops.get_active_keywords()
        keywords = [kw.term for kw in keyword_configs]

        if not keywords:
            raise ValidationException("No active keywords configured")

        # Create batch event with approximate window (actual data from 'today 1-m')
        from lib.timezone_utils import today_ict
        from datetime import timedelta

        today = today_ict()
        approx_start = today - timedelta(days=30)

        batch_event = BatchEvent.create(
            batch_type=batch_type,
            keywords=keywords,
            start_date=approx_start,
            end_date=today,
            notes="Ingestion using 'today 1-m' timeframe (~30 days)"
        )

        # Log batch start
        log_batch_event(
            logger,
            'info',
            "RSV ingestion started (timeframe='today 1-m')",
            batch_id=batch_event.batch_id,
            keywords=keywords,
            status='running'
        )

        # Insert batch event (status='running')
        try:
            self.db_ops.insert_batch_event(batch_event)
        except DatabaseException as e:
            logger.error(f"Failed to create batch event: {e}")
            raise

        # Fetch RSV data using 'today 1-m' timeframe
        # ONE keyword per request to respect pytrends API limits
        try:
            all_records = []

            for keyword in keywords:
                logger.info(f"Fetching RSV for keyword: {keyword}")

                keyword_records = self.trends_fetcher.fetch_daily_rsv(
                    keywords=[keyword],  # ONE keyword per request
                    batch_id=batch_event.batch_id,
                    timeframe='today 1-m'
                )
                all_records.extend(keyword_records)

                # Apply jitter between requests (except after last keyword)
                if keyword != keywords[-1]:
                    self.trends_fetcher._apply_jitter()

            records = all_records

            if not records:
                # Mark as degraded (no data returned)
                batch_event.mark_degraded(
                    rows_written=0,
                    rows_missing=0,
                    reason="No RSV data returned from pytrends"
                )
                self.db_ops.update_batch_event(batch_event)

                log_batch_event(
                    logger,
                    'warning',
                    "Ingestion degraded: no data returned",
                    batch_id=batch_event.batch_id,
                    status='degraded'
                )

                return batch_event

        except PyTrendsException as e:
            # Mark as failed
            batch_event.mark_fail(str(e))
            self.db_ops.update_batch_event(batch_event)

            log_batch_event(
                logger,
                'error',
                f"Ingestion failed: {e}",
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

            # Success
            batch_event.mark_success(
                rows_written=rows_written,
                rows_updated=rows_updated,
                notes=f"Successfully ingested {len(records)} RSV records for {len(keywords)} keywords"
            )

            log_batch_event(
                logger,
                'info',
                "Ingestion success",
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
                "Ingestion failed: database error",
                batch_id=batch_event.batch_id,
                status='fail',
                error=str(e)
            )

            raise

        logger.info(
            f"Ingestion complete: batch_id={batch_event.batch_id}, "
            f"status={batch_event.status}, rows_written={rows_written}, rows_updated={rows_updated}"
        )

        return batch_event
