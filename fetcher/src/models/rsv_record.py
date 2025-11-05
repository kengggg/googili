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
from zoneinfo import ZoneInfo

ICT = ZoneInfo("Asia/Bangkok")


@dataclass
class RSVRecord:
    """
    RSV (Relative Search Volume) data point for a keyword on a specific date.

    Attributes:
        keyword: Thai keyword term (e.g., "ไข้", "ไอ")
        date: Date of RSV measurement (YYYY-MM-DD)
        rsv_raw: Raw RSV value from Google Trends (0-100 scale)
        batch_id: Foreign key to events_raw_rsv_ingested (provenance)
        rsv_stitched: Stitched RSV value (after overlap-based scaling)
        granularity: 'daily' or 'weekly'
        quality: 'true_daily', 'weekly_flat', or 'below_detection'
        impute_method: Method used if imputed (e.g., 'weekly_flat')
        inserted_at_utc: UTC timestamp when record inserted
    """

    # Primary key fields
    keyword: str
    date: date

    # RSV values
    rsv_raw: int

    # Provenance
    batch_id: str

    # Optional fields with defaults
    rsv_stitched: Optional[float] = None
    granularity: str = 'daily'
    quality: str = 'true_daily'
    impute_method: Optional[str] = None
    inserted_at_utc: Optional[datetime] = field(default_factory=lambda: datetime.now(ZoneInfo("UTC")))

    def __post_init__(self):
        """Validate field values after initialization."""
        # Validate granularity
        valid_granularities = ['daily', 'weekly']
        if self.granularity not in valid_granularities:
            raise ValueError(f"granularity must be one of {valid_granularities}, got '{self.granularity}'")

        # Validate quality
        valid_qualities = ['true_daily', 'weekly_flat', 'below_detection']
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
            Dictionary with all fields, date and timestamp as strings
        """
        data = asdict(self)

        # Convert date to ISO 8601 string (YYYY-MM-DD)
        data['date'] = self.date.isoformat()

        # Convert inserted_at_utc to ISO 8601 string
        if self.inserted_at_utc:
            data['inserted_at_utc'] = self.inserted_at_utc.isoformat()

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

        # Parse inserted_at_utc from string
        if isinstance(data.get('inserted_at_utc'), str):
            data['inserted_at_utc'] = datetime.fromisoformat(data['inserted_at_utc'])

        return cls(**data)

    @classmethod
    def from_pytrends_row(
        cls,
        keyword: str,
        date_val: date,
        rsv_value: int,
        batch_id: str,
        granularity: str = 'daily'
    ) -> 'RSVRecord':
        """
        Create RSVRecord from pytrends API response row.

        Args:
            keyword: Keyword term
            date_val: Date of measurement
            rsv_value: RSV value from pytrends (0-100)
            batch_id: Batch identifier for provenance
            granularity: 'daily' or 'weekly'

        Returns:
            RSVRecord instance
        """
        return cls(
            keyword=keyword,
            date=date_val,
            rsv_raw=rsv_value,
            batch_id=batch_id,
            granularity=granularity,
            quality='true_daily' if granularity == 'daily' else 'weekly_flat'
        )

    def is_stitched(self) -> bool:
        """Check if this record has been stitched."""
        return self.rsv_stitched is not None

    def is_daily(self) -> bool:
        """Check if this is true daily granularity data."""
        return self.granularity == 'daily' and self.quality == 'true_daily'

    def is_high_quality(self) -> bool:
        """
        Check if record is high quality (usable for stitching factors).

        Per FR-011: Only true_daily quality should be used for computing
        future scaling factors.
        """
        return self.quality == 'true_daily'

    def __repr__(self) -> str:
        """Human-readable representation."""
        return (
            f"RSVRecord(keyword='{self.keyword}', date={self.date}, "
            f"rsv_raw={self.rsv_raw}, quality='{self.quality}', "
            f"granularity='{self.granularity}', batch_id='{self.batch_id}')"
        )
