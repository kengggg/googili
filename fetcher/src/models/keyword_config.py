"""
Keyword Configuration Data Model

Represents keyword configuration for tracking.
Maps to config_keywords table in database-schema.sql.

Constitution alignment:
- Principle VII: Configuration-as-Code - Keywords managed as data
- Principle IV: Data Governance - Province scoping enforced
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

ICT = ZoneInfo("Asia/Bangkok")


@dataclass
class KeywordConfig:
    """
    Keyword configuration for Google Trends tracking.

    Attributes:
        term: Thai keyword to track (e.g., "ไข้", "ไอ")
        active: Whether keyword is currently active for tracking
        created_at: Timestamp when keyword was added (ICT)
        province_code: ISO 3166-2 province code (TH-50 for Chiang Mai)
        notes: Optional notes about keyword (e.g., synonym info, deprecation reason)
    """

    term: str
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(ICT))
    province_code: str = 'TH-50'
    notes: Optional[str] = None

    def __post_init__(self):
        """Validate field values after initialization."""
        # Validate term not empty
        if not self.term or not self.term.strip():
            raise ValueError("term cannot be empty")

        # Validate province_code (MVP constraint: only TH-50)
        if self.province_code != 'TH-50':
            raise ValueError(
                f"MVP constraint: Only TH-50 (Chiang Mai) supported. Got: {self.province_code}"
            )

    def deactivate(self, reason: str):
        """
        Deactivate keyword with reason.

        Args:
            reason: Explanation for deactivation
        """
        self.active = False
        if self.notes:
            self.notes = f"{self.notes}\nDeactivated: {reason}"
        else:
            self.notes = f"Deactivated: {reason}"

    def activate(self):
        """Activate keyword for tracking."""
        self.active = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database insertion.

        Returns:
            Dictionary with all fields
        """
        data = asdict(self)

        # Convert created_at to ISO 8601 string
        if isinstance(self.created_at, datetime):
            data['created_at'] = self.created_at.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KeywordConfig':
        """
        Create KeywordConfig from dictionary (e.g., database row).

        Args:
            data: Dictionary with keyword config fields

        Returns:
            KeywordConfig instance
        """
        # Convert active from 1/0 (SQLite) to bool
        if isinstance(data.get('active'), int):
            data['active'] = bool(data['active'])

        # Parse created_at from string
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])

        return cls(**data)

    def __repr__(self) -> str:
        """Human-readable representation."""
        status = "active" if self.active else "inactive"
        return (
            f"KeywordConfig(term='{self.term}', {status}, "
            f"province='{self.province_code}')"
        )
