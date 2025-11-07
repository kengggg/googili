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
from datetime import date
from typing import Optional

from lib.db import DatabaseConnection
from lib.db_operations import DBOperations
from lib.config import FetcherConfig
from lib.logging_utils import log_batch_event
from lib.exceptions import PyTrendsException, DatabaseException, ValidationException, StitchingException
from models.batch_event import BatchEvent
from services.trends_fetcher import TrendsFetcher
from services.stitcher import StitcherService

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

        # Initialize StitcherService for overlap-based stitching
        self.stitcher = StitcherService(
            db_conn=db,  # Pass DatabaseConnection object
            min_overlap_days=config.stitching_min_overlap_days,
            trim_percent=config.stitching_trim_percent
        )

        logger.info("IngestionService initialized with stitching support")

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
        # Apply stitching to each keyword after fetch
        try:
            all_records = []
            stitching_notes = []

            for keyword in keywords:
                logger.info(f"Fetching RSV for keyword: {keyword}")

                keyword_records = self.trends_fetcher.fetch_daily_rsv(
                    keywords=[keyword],  # ONE keyword per request
                    batch_id=batch_event.batch_id,
                    timeframe='today 1-m'
                )

                # Apply stitching to this keyword's records
                if keyword_records:
                    try:
                        stitched_records = self._apply_stitching_to_keyword(
                            keyword=keyword,
                            new_records=keyword_records,
                            approx_start=approx_start,
                            today=today
                        )
                        all_records.extend(stitched_records['records'])
                        stitching_notes.append(stitched_records['metadata'])
                    except StitchingException as e:
                        # Log stitching error but continue with raw values
                        logger.warning(f"Stitching failed for keyword '{keyword}': {e}")
                        # Use raw values as fallback
                        for record in keyword_records:
                            record.rsv_stitched = float(record.rsv_raw)
                        all_records.extend(keyword_records)
                        stitching_notes.append(f"Stitching failed for '{keyword}': {e}")

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

            # Success - include stitching metadata in notes
            stitching_summary = "\n".join(stitching_notes) if stitching_notes else "No stitching metadata"
            batch_event.mark_success(
                rows_written=rows_written,
                rows_updated=rows_updated,
                notes=f"Successfully ingested {len(records)} RSV records for {len(keywords)} keywords\n\nStitching:\n{stitching_summary}"
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

    def _apply_stitching_to_keyword(
        self,
        keyword: str,
        new_records: list,
        approx_start: date,
        today: date
    ) -> dict:
        """
        Apply stitching to a single keyword's records.

        Workflow:
        1. Find overlap region with existing data
        2. Extract overlap values from old (database) and new (fetched) records
        3. Compute scaling factor using trimmed mean
        4. Apply stitching to NEW records only (non-overlapping dates)
        5. Return stitched records + metadata

        Args:
            keyword: Thai keyword term
            new_records: Fresh records from pytrends (all dates including overlap)
            approx_start: Approximate start date of new window
            today: Today's date

        Returns:
            Dictionary with 'records' (stitched) and 'metadata' (audit string)
        """
        # Find existing overlap records from database
        overlap_records = self.stitcher.find_overlap(
            keyword=keyword,
            overlap_start=approx_start,
            overlap_end=today
        )

        if not overlap_records:
            # First ingestion: no existing data, copy raw values
            logger.info(f"No overlap found for keyword '{keyword}' - first ingestion")
            for record in new_records:
                record.rsv_stitched = float(record.rsv_raw)

            metadata = self.stitcher.format_stitching_metadata(
                keyword=keyword,
                scaling_factor=None,
                overlap_days=0
            )

            return {'records': new_records, 'metadata': metadata}

        # Extract overlap region from new records
        overlap_dates = {rec[0] for rec in overlap_records}  # Set of dates
        new_overlap_records = [rec for rec in new_records if rec.date in overlap_dates]
        new_only_records = [rec for rec in new_records if rec.date not in overlap_dates]

        if not new_overlap_records:
            # No overlap match (shouldn't happen but handle gracefully)
            logger.warning(f"Overlap dates don't match for keyword '{keyword}'")
            for record in new_records:
                record.rsv_stitched = float(record.rsv_raw)

            metadata = f"Stitching keyword='{keyword}': date mismatch, using raw values"
            return {'records': new_records, 'metadata': metadata}

        # Extract RSV values for scaling factor computation
        # Sort both by date to ensure alignment
        overlap_records_sorted = sorted(overlap_records, key=lambda x: x[0])
        new_overlap_records_sorted = sorted(new_overlap_records, key=lambda x: x.date)

        old_overlap_values = [rec[1] for rec in overlap_records_sorted]
        new_overlap_values = [rec.rsv_raw for rec in new_overlap_records_sorted]

        # Compute scaling factor
        scaling_factor = self.stitcher.compute_scaling_factor(
            old_overlap=old_overlap_values,
            new_overlap=new_overlap_values,
            keyword=keyword
        )

        # Apply stitching to NEW records only
        stitched_new_records = self.stitcher.apply_stitching(
            new_records=new_only_records,
            scaling_factor=scaling_factor
        )

        # Overlap records keep their existing stitched values (already in database)
        # We don't update them, just use raw values for these records in this batch
        for rec in new_overlap_records:
            rec.rsv_stitched = float(rec.rsv_raw)  # Will be ignored during UPSERT

        # Combine all records
        all_stitched = new_overlap_records + stitched_new_records

        # Format metadata for batch event
        metadata = self.stitcher.format_stitching_metadata(
            keyword=keyword,
            scaling_factor=scaling_factor,
            overlap_days=len(overlap_records)
        )

        logger.info(f"Stitching applied to keyword '{keyword}': {len(stitched_new_records)} new records scaled")

        return {'records': all_stitched, 'metadata': metadata}
