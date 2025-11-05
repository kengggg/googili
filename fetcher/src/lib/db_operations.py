"""
Database Operations Module

UPSERT operations for RSV records and batch events.
Ensures idempotence and maintains referential integrity.

Per database-schema.sql:
- RSV records: PRIMARY KEY (keyword, date) → UPSERT with INSERT OR REPLACE
- Batch events: PRIMARY KEY (batch_id) → INSERT only

Constitution alignment:
- Principle IV: Data Governance - Complete provenance via batch_id FK
- Principle VI: Clarity Over Cleverness - Explicit SQL, no ORM magic
"""

import logging
import json
from typing import List, Optional, Dict, Any
import sqlite3

from lib.db import DatabaseConnection
from lib.exceptions import DatabaseException
from models.rsv_record import RSVRecord
from models.batch_event import BatchEvent
from models.keyword_config import KeywordConfig

logger = logging.getLogger(__name__)


class DBOperations:
    """
    Database persistence operations for RSV data and batch events.

    Handles:
    - UPSERT for RSV records (idempotent ingestion)
    - INSERT for batch events
    - Query helpers for keywords and batch metadata
    """

    def __init__(self, db: DatabaseConnection):
        """
        Initialize database operations.

        Args:
            db: DatabaseConnection instance
        """
        self.db = db

    def upsert_rsv_records(self, records: List[RSVRecord]) -> Dict[str, int]:
        """
        Insert or update RSV records (idempotent).

        Uses INSERT OR REPLACE to handle duplicate (keyword, date) pairs.
        Updates batch_id to most recent batch on conflict.

        Args:
            records: List of RSVRecord instances to persist

        Returns:
            Dict with 'inserted' and 'updated' counts

        Raises:
            DatabaseException: If database operation fails
        """
        if not records:
            return {'inserted': 0, 'updated': 0}

        inserted = 0
        updated = 0

        try:
            with self.db.get_connection() as conn:
                for record in records:
                    # Check if record exists
                    cursor = conn.execute(
                        "SELECT batch_id FROM raw_trenddata WHERE keyword = ? AND date = ?",
                        (record.keyword, record.date.isoformat())
                    )
                    existing = cursor.fetchone()

                    # INSERT OR REPLACE (UPSERT)
                    conn.execute("""
                        INSERT OR REPLACE INTO raw_trenddata (
                            keyword, date, rsv_raw, source_window_start, fetched_at_ict,
                            rsv_stitched, granularity, quality, impute_method, batch_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.keyword,
                        record.date.isoformat(),
                        record.rsv_raw,
                        record.source_window_start.isoformat(),
                        record.fetched_at_ict.isoformat() if record.fetched_at_ict else None,
                        record.rsv_stitched,
                        record.granularity,
                        record.quality,
                        record.impute_method,
                        record.batch_id
                    ))

                    if existing:
                        updated += 1
                        logger.debug(
                            f"Updated RSV record: {record.keyword} @ {record.date}, "
                            f"old_batch={existing['batch_id']}, new_batch={record.batch_id}"
                        )
                    else:
                        inserted += 1

            logger.info(f"UPSERT RSV records: {inserted} inserted, {updated} updated")

        except sqlite3.Error as e:
            logger.error(f"Failed to UPSERT RSV records: {e}", exc_info=True)
            raise DatabaseException(f"RSV record UPSERT failed: {e}") from e

        return {'inserted': inserted, 'updated': updated}

    def insert_batch_event(self, batch_event: BatchEvent) -> None:
        """
        Insert new batch event.

        Batch events are immutable after creation (PRIMARY KEY batch_id).

        Args:
            batch_event: BatchEvent instance to persist

        Raises:
            DatabaseException: If batch_id already exists or insert fails
        """
        try:
            with self.db.get_connection() as conn:
                # Convert keywords list to JSON
                keywords_json = json.dumps(batch_event.requested_keywords, ensure_ascii=False)

                conn.execute("""
                    INSERT INTO events_raw_rsv_ingested (
                        batch_id, batch_type, requested_keywords, requested_window,
                        started_at_ict, finished_at_ict, status,
                        rows_written, rows_updated, rows_missing,
                        quality_true_daily, quality_weekly_flat, quality_below_detection,
                        notes, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    batch_event.batch_id,
                    batch_event.batch_type,
                    keywords_json,
                    batch_event.requested_window,
                    batch_event.started_at_ict.isoformat(),
                    batch_event.finished_at_ict.isoformat() if batch_event.finished_at_ict else None,
                    batch_event.status,
                    batch_event.rows_written,
                    batch_event.rows_updated,
                    batch_event.rows_missing,
                    batch_event.quality_true_daily,
                    batch_event.quality_weekly_flat,
                    batch_event.quality_below_detection,
                    batch_event.notes,
                    batch_event.error_message
                ))

            logger.info(f"Inserted batch event: {batch_event.batch_id}, status={batch_event.status}")

        except sqlite3.IntegrityError as e:
            logger.error(f"Batch event already exists: {batch_event.batch_id}")
            raise DatabaseException(f"Duplicate batch_id: {batch_event.batch_id}") from e
        except sqlite3.Error as e:
            logger.error(f"Failed to insert batch event: {e}", exc_info=True)
            raise DatabaseException(f"Batch event insert failed: {e}") from e

    def update_batch_event(self, batch_event: BatchEvent) -> None:
        """
        Update existing batch event (for status transitions).

        Args:
            batch_event: BatchEvent instance with updated fields

        Raises:
            DatabaseException: If update fails or batch_id not found
        """
        try:
            with self.db.get_connection() as conn:
                keywords_json = json.dumps(batch_event.requested_keywords, ensure_ascii=False)

                cursor = conn.execute("""
                    UPDATE events_raw_rsv_ingested SET
                        batch_type = ?,
                        requested_keywords = ?,
                        requested_window = ?,
                        started_at_ict = ?,
                        finished_at_ict = ?,
                        status = ?,
                        rows_written = ?,
                        rows_updated = ?,
                        rows_missing = ?,
                        quality_true_daily = ?,
                        quality_weekly_flat = ?,
                        quality_below_detection = ?,
                        notes = ?,
                        error_message = ?
                    WHERE batch_id = ?
                """, (
                    batch_event.batch_type,
                    keywords_json,
                    batch_event.requested_window,
                    batch_event.started_at_ict.isoformat(),
                    batch_event.finished_at_ict.isoformat() if batch_event.finished_at_ict else None,
                    batch_event.status,
                    batch_event.rows_written,
                    batch_event.rows_updated,
                    batch_event.rows_missing,
                    batch_event.quality_true_daily,
                    batch_event.quality_weekly_flat,
                    batch_event.quality_below_detection,
                    batch_event.notes,
                    batch_event.error_message,
                    batch_event.batch_id
                ))

                if cursor.rowcount == 0:
                    raise DatabaseException(f"Batch event not found: {batch_event.batch_id}")

            logger.info(f"Updated batch event: {batch_event.batch_id}, status={batch_event.status}")

        except sqlite3.Error as e:
            logger.error(f"Failed to update batch event: {e}", exc_info=True)
            raise DatabaseException(f"Batch event update failed: {e}") from e

    def get_active_keywords(self) -> List[KeywordConfig]:
        """
        Get list of active keywords from config_keywords table.

        Returns:
            List of KeywordConfig instances where active=1

        Raises:
            DatabaseException: If query fails
        """
        try:
            with self.db.get_connection(auto_commit=False) as conn:
                cursor = conn.execute("""
                    SELECT term, active, province_code, notes
                    FROM config_keywords
                    WHERE active = 1
                    ORDER BY term
                """)

                keywords = []
                for row in cursor.fetchall():
                    keyword = KeywordConfig(
                        term=row['term'],
                        active=bool(row['active']),
                        province_code=row['province_code'],
                        notes=row['notes']
                    )
                    keywords.append(keyword)

            logger.info(f"Loaded {len(keywords)} active keywords")
            return keywords

        except sqlite3.Error as e:
            logger.error(f"Failed to load keywords: {e}", exc_info=True)
            raise DatabaseException(f"Keyword query failed: {e}") from e

    def get_latest_batch_event(self) -> Optional[BatchEvent]:
        """
        Get most recent batch event (by started_at_ict).

        Returns:
            BatchEvent instance or None if no batches exist

        Raises:
            DatabaseException: If query fails
        """
        try:
            with self.db.get_connection(auto_commit=False) as conn:
                cursor = conn.execute("""
                    SELECT * FROM events_raw_rsv_ingested
                    ORDER BY started_at_ict DESC
                    LIMIT 1
                """)

                row = cursor.fetchone()
                if not row:
                    return None

                # Parse JSON keywords
                keywords = json.loads(row['requested_keywords'])

                from lib.timezone_utils import parse_ict_timestamp

                batch_event = BatchEvent(
                    batch_id=row['batch_id'],
                    batch_type=row['batch_type'],
                    requested_keywords=keywords,
                    requested_window=row['requested_window'],
                    started_at_ict=parse_ict_timestamp(row['started_at_ict']),
                    finished_at_ict=parse_ict_timestamp(row['finished_at_ict']) if row['finished_at_ict'] else None,
                    status=row['status'],
                    rows_written=row['rows_written'],
                    rows_updated=row['rows_updated'],
                    rows_missing=row['rows_missing'],
                    quality_true_daily=row['quality_true_daily'],
                    quality_weekly_flat=row['quality_weekly_flat'],
                    quality_below_detection=row['quality_below_detection'],
                    notes=row['notes'],
                    error_message=row['error_message']
                )

                return batch_event

        except sqlite3.Error as e:
            logger.error(f"Failed to load latest batch event: {e}", exc_info=True)
            raise DatabaseException(f"Batch event query failed: {e}") from e

    def count_rsv_records(self, batch_id: Optional[str] = None) -> int:
        """
        Count RSV records, optionally filtered by batch_id.

        Args:
            batch_id: Optional batch identifier to filter by

        Returns:
            Count of matching records

        Raises:
            DatabaseException: If query fails
        """
        try:
            with self.db.get_connection(auto_commit=False) as conn:
                if batch_id:
                    cursor = conn.execute(
                        "SELECT COUNT(*) as cnt FROM raw_trenddata WHERE batch_id = ?",
                        (batch_id,)
                    )
                else:
                    cursor = conn.execute("SELECT COUNT(*) as cnt FROM raw_trenddata")

                count = cursor.fetchone()['cnt']
                return count

        except sqlite3.Error as e:
            logger.error(f"Failed to count RSV records: {e}", exc_info=True)
            raise DatabaseException(f"RSV count query failed: {e}") from e

    def is_database_empty(self) -> bool:
        """
        Check if database has any RSV data (for first-run detection).

        Returns:
            True if raw_trenddata table is empty

        Raises:
            DatabaseException: If query fails
        """
        try:
            count = self.count_rsv_records()
            return count == 0
        except Exception as e:
            raise DatabaseException(f"Empty check failed: {e}") from e
