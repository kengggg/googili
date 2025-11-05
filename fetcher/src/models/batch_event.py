"""
Batch Event Data Model

Represents a single batch ingestion event with complete provenance metadata.
Maps to events_raw_rsv_ingested table in database-schema.sql.

Per spec.md FR-008: Complete batch event metadata for governance and audit trail.

Constitution alignment:
- Principle IV: Data Governance - Complete provenance and lineage
- Principle VIII: Observability - Structured metadata for monitoring
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import json
from zoneinfo import ZoneInfo

from lib.timezone_utils import ICT, now_ict, format_ict_timestamp


@dataclass
class BatchEvent:
    """
    Batch ingestion event with complete provenance metadata.

    Per FR-008, tracks:
    - What was requested (keywords, window)
    - When it ran (start/finish timestamps)
    - What was written (row counts)
    - How it went (status, errors, notes)

    Attributes:
        batch_id: Unique identifier (format: batch_YYYYMMDD_HHMMSS)
        batch_type: Type of batch ('daily', 'initial_backfill', 'recovery_backfill', 'manual')
        requested_keywords: List of keywords requested
        requested_window: Date range string (format: "YYYY-MM-DD to YYYY-MM-DD")
        started_at_ict: Start timestamp in Asia/Bangkok timezone
        status: Current status ('running', 'success', 'degraded', 'fail')
        finished_at_ict: Finish timestamp (null while running)
        rows_written: Count of RSV records inserted
        rows_updated: Count of RSV records updated (re-ingestion)
        rows_missing: Count of expected but missing records
        quality_true_daily: Count of true_daily quality records
        quality_weekly_flat: Count of weekly_flat quality records
        quality_below_detection: Count of below_detection quality records
        notes: Audit notes (stitching factors, warnings, context)
        error_message: Error details if status='fail'
    """

    # Core identification
    batch_id: str
    batch_type: str
    requested_keywords: List[str]
    requested_window: str

    # Timestamps
    started_at_ict: datetime
    status: str = 'running'

    # Optional timestamps and counts
    finished_at_ict: Optional[datetime] = None
    rows_written: int = 0
    rows_updated: int = 0
    rows_missing: int = 0

    # Quality metrics (nullable, added in User Story 5)
    quality_true_daily: Optional[int] = None
    quality_weekly_flat: Optional[int] = None
    quality_below_detection: Optional[int] = None

    # Metadata
    notes: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        """Validate field values after initialization."""
        # Validate batch_type
        valid_types = ['daily', 'initial_backfill', 'recovery_backfill', 'manual']
        if self.batch_type not in valid_types:
            raise ValueError(f"batch_type must be one of {valid_types}, got '{self.batch_type}'")

        # Validate status
        valid_statuses = ['running', 'success', 'degraded', 'fail']
        if self.status not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}, got '{self.status}'")

        # Validate keywords not empty
        if not self.requested_keywords or len(self.requested_keywords) == 0:
            raise ValueError("requested_keywords cannot be empty")

        # Validate requested_window not empty
        if not self.requested_window or not self.requested_window.strip():
            raise ValueError("requested_window cannot be empty")

        # Validate batch_id format
        if not self.batch_id.startswith('batch_'):
            raise ValueError(f"batch_id must start with 'batch_', got '{self.batch_id}'")

    @classmethod
    def generate_batch_id(cls) -> str:
        """
        Generate batch_id in format: batch_YYYYMMDD_HHMMSS (Asia/Bangkok time).

        Returns:
            Batch ID string
        """
        now = now_ict()
        return now.strftime("batch_%Y%m%d_%H%M%S")

    @classmethod
    def create(
        cls,
        batch_type: str,
        keywords: List[str],
        start_date: date,
        end_date: date,
        notes: Optional[str] = None
    ) -> 'BatchEvent':
        """
        Create new batch event with generated batch_id and current timestamp.

        Args:
            batch_type: Type of batch operation
            keywords: List of keywords to fetch
            start_date: Window start date
            end_date: Window end date
            notes: Optional notes for context

        Returns:
            New BatchEvent instance with status='running'
        """
        from lib.timezone_utils import format_date_range

        batch_id = cls.generate_batch_id()
        window = format_date_range(start_date, end_date)
        started_at = now_ict()

        return cls(
            batch_id=batch_id,
            batch_type=batch_type,
            requested_keywords=keywords,
            requested_window=window,
            started_at_ict=started_at,
            status='running',
            notes=notes
        )

    def mark_success(self, rows_written: int, rows_updated: int = 0, notes: Optional[str] = None):
        """
        Mark batch as successfully completed.

        Args:
            rows_written: Number of records inserted
            rows_updated: Number of records updated
            notes: Optional success notes
        """
        if self.status in ['success', 'fail']:
            raise ValueError(f"Cannot change status from terminal state '{self.status}'")

        self.status = 'success'
        self.finished_at_ict = now_ict()
        self.rows_written = rows_written
        self.rows_updated = rows_updated

        if notes:
            self.notes = notes if not self.notes else f"{self.notes}\n{notes}"

    def mark_degraded(self, rows_written: int, rows_missing: int, reason: str):
        """
        Mark batch as degraded (partial success).

        Args:
            rows_written: Number of records successfully written
            rows_missing: Number of expected but missing records
            reason: Explanation of degradation
        """
        if self.status in ['success', 'fail']:
            raise ValueError(f"Cannot change status from terminal state '{self.status}'")

        self.status = 'degraded'
        self.finished_at_ict = now_ict()
        self.rows_written = rows_written
        self.rows_missing = rows_missing

        self.notes = reason if not self.notes else f"{self.notes}\n{reason}"

    def mark_fail(self, error_message: str):
        """
        Mark batch as failed.

        Args:
            error_message: Error details
        """
        if self.status in ['success', 'fail']:
            raise ValueError(f"Cannot change status from terminal state '{self.status}'")

        self.status = 'fail'
        self.finished_at_ict = now_ict()
        self.error_message = error_message

    def add_notes(self, notes: str):
        """
        Append notes to batch event.

        Args:
            notes: Notes to append
        """
        if self.notes:
            self.notes = f"{self.notes}\n{notes}"
        else:
            self.notes = notes

    def set_quality_metrics(self, true_daily: int, weekly_flat: int, below_detection: int):
        """
        Set quality metric counts (User Story 5).

        Args:
            true_daily: Count of true_daily quality records
            weekly_flat: Count of weekly_flat quality records
            below_detection: Count of below_detection quality records
        """
        self.quality_true_daily = true_daily
        self.quality_weekly_flat = weekly_flat
        self.quality_below_detection = below_detection

    def duration_seconds(self) -> Optional[float]:
        """
        Calculate batch duration in seconds.

        Returns:
            Duration in seconds, or None if not finished
        """
        if not self.finished_at_ict:
            return None

        delta = self.finished_at_ict - self.started_at_ict
        return delta.total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database insertion.

        Returns:
            Dictionary with all fields, timestamps as ISO 8601 strings
        """
        data = asdict(self)

        # Convert requested_keywords list to JSON string
        data['requested_keywords'] = json.dumps(self.requested_keywords, ensure_ascii=False)

        # Convert timestamps to ISO 8601 strings
        data['started_at_ict'] = format_ict_timestamp(self.started_at_ict)
        if self.finished_at_ict:
            data['finished_at_ict'] = format_ict_timestamp(self.finished_at_ict)

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchEvent':
        """
        Create BatchEvent from dictionary (e.g., database row).

        Args:
            data: Dictionary with batch event fields

        Returns:
            BatchEvent instance
        """
        # Parse requested_keywords from JSON string
        if isinstance(data.get('requested_keywords'), str):
            data['requested_keywords'] = json.loads(data['requested_keywords'])

        # Parse timestamps from ISO 8601 strings
        if isinstance(data.get('started_at_ict'), str):
            from lib.timezone_utils import parse_ict_timestamp
            data['started_at_ict'] = parse_ict_timestamp(data['started_at_ict'])

        if isinstance(data.get('finished_at_ict'), str):
            from lib.timezone_utils import parse_ict_timestamp
            data['finished_at_ict'] = parse_ict_timestamp(data['finished_at_ict'])

        return cls(**data)

    def __repr__(self) -> str:
        """Human-readable representation."""
        duration_str = ""
        if self.finished_at_ict:
            duration = self.duration_seconds()
            duration_str = f", duration={duration:.1f}s"

        return (
            f"BatchEvent(batch_id='{self.batch_id}', type='{self.batch_type}', "
            f"status='{self.status}', keywords={len(self.requested_keywords)}, "
            f"rows_written={self.rows_written}{duration_str})"
        )
