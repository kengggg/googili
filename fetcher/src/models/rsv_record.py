"""
RSV Record Data Model

Represents a single Google Trends RSV data point per keyword per date.
Maps to raw_trenddata table in database-schema.sql.

Constitution alignment:
- Principle IV: Data Governance - Complete provenance via batch_id
- Principle VIII: Observability - Quality and granularity badges
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional, Dict, Any

from lib.timezone_utils import ICT


@dataclass
class RSVRecord:
    """
    RSV (Relative Search Volume) data point for a keyword on a specific date.

    Attributes:
        keyword: Thai keyword term (e.g., "ไข้", "ไอ")
        date: Date of RSV measurement (YYYY-MM-DD)
        rsv_raw: Raw RSV value from Google Trends (0-100 scale)
        source_window_start: Start date of fetch window (for provenance)
        batch_id: Foreign key to events_raw_rsv_ingested (provenance)
        rsv_stitched: Stitched RSV value (after overlap-based scaling)
        granularity: 'daily' or 'weekly'
        quality: 'true' (high quality) or 'coarse' (degraded quality)
        impute_method: Method used if imputed (e.g., 'weekly_flat')
        fetched_at_ict: ICT timestamp when record fetched
    """

    # Primary key fields
    keyword: str
    date: date

    # RSV values
    rsv_raw: int

    # Provenance (required)
    source_window_start: date
    batch_id: str

    # Optional fields with defaults
    rsv_stitched: Optional[float] = None
    granularity: str = 'daily'
    quality: str = 'true'
    impute_method: Optional[str] = None
    fetched_at_ict: Optional[datetime] = field(default_factory=lambda: datetime.now(ICT))

    def __post_init__(self):
        """Validate field values after initialization."""
        # Validate granularity
        valid_granularities = ['daily', 'weekly']
        if self.granularity not in valid_granularities:
            raise ValueError(f"granularity must be one of {valid_granularities}, got '{self.granularity}'")

        # Validate quality (matches schema CHECK constraint)
        valid_qualities = ['true', 'coarse']
        if self.quality not in valid_qualities:
            raise ValueError(f"quality must be one of {valid_qualities}, got '{self.quality}'")

        # Validate rsv_raw range (0-100 typical for Google Trends)
        if self.rsv_raw < 0:
            raise ValueError(f"rsv_raw cannot be negative, got {self.rsv_raw}")

        # Validate keyword not empty
        if not self.keyword or not self.keyword.strip():
            raise ValueError("keyword cannot be empty")

        # Validate batch_id not empty
        if not self.batch_id or not self.batch_id.strip():
            raise ValueError("batch_id cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database insertion.

        Returns:
            Dictionary with all fields, dates and timestamp as strings
        """
        data = asdict(self)

        # Convert date to ISO 8601 string (YYYY-MM-DD)
        data['date'] = self.date.isoformat()

        # Convert source_window_start to ISO 8601 string
        data['source_window_start'] = self.source_window_start.isoformat()

        # Convert fetched_at_ict to ISO 8601 string
        if self.fetched_at_ict:
            data['fetched_at_ict'] = self.fetched_at_ict.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RSVRecord':
        """
        Create RSVRecord from dictionary (e.g., database row).

        Args:
            data: Dictionary with RSV record fields

        Returns:
            RSVRecord instance
        """
        # Parse date from string
        if isinstance(data.get('date'), str):
            data['date'] = date.fromisoformat(data['date'])

        # Parse source_window_start from string
        if isinstance(data.get('source_window_start'), str):
            data['source_window_start'] = date.fromisoformat(data['source_window_start'])

        # Parse fetched_at_ict from string
        if isinstance(data.get('fetched_at_ict'), str):
            data['fetched_at_ict'] = datetime.fromisoformat(data['fetched_at_ict'])

        return cls(**data)

    @classmethod
    def from_pytrends_row(
        cls,
        keyword: str,
        date_val: date,
        rsv_value: int,
        source_window_start: date,
        batch_id: str,
        granularity: str = 'daily'
    ) -> 'RSVRecord':
        """
        Create RSVRecord from pytrends API response row.

        Args:
            keyword: Keyword term
            date_val: Date of measurement
            rsv_value: RSV value from pytrends (0-100)
            source_window_start: Start date of fetch window (for provenance)
            batch_id: Batch identifier for provenance
            granularity: 'daily' or 'weekly'

        Returns:
            RSVRecord instance
        """
        return cls(
            keyword=keyword,
            date=date_val,
            rsv_raw=rsv_value,
            source_window_start=source_window_start,
            batch_id=batch_id,
            granularity=granularity,
            quality='true' if granularity == 'daily' else 'coarse'
        )

    def is_stitched(self) -> bool:
        """Check if this record has been stitched."""
        return self.rsv_stitched is not None

    def is_daily(self) -> bool:
        """Check if this is true daily granularity data."""
        return self.granularity == 'daily' and self.quality == 'true'

    def is_high_quality(self) -> bool:
        """
        Check if record is high quality (usable for stitching factors).

        Per FR-011: Only 'true' quality should be used for computing
        future scaling factors.
        """
        return self.quality == 'true'

    def __repr__(self) -> str:
        """Human-readable representation."""
        return (
            f"RSVRecord(keyword='{self.keyword}', date={self.date}, "
            f"rsv_raw={self.rsv_raw}, quality='{self.quality}', "
            f"granularity='{self.granularity}', batch_id='{self.batch_id}')"
        )
