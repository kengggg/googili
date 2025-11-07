"""
StitcherService - Overlap-based stitching for continuous time series.

Implements trimmed mean algorithm to normalize consecutive 'today 1-m' fetches
into a continuous time series without normalization jumps.

Constitution alignment:
- Principle III: TDD - All tests written first
- Principle VI: Clarity Over Cleverness - Explicit algorithm steps
- Principle VIII: Data Lineage - Complete provenance tracking
"""

import logging
from datetime import date
from typing import List, Optional, Tuple
from scipy.stats import trim_mean

from src.lib.exceptions import StitchingException

logger = logging.getLogger(__name__)


class StitcherService:
    """
    Service for stitching overlapping Google Trends RSV data.

    Each daily 'today 1-m' fetch returns ~30 days with independent 0-100 normalization.
    Consecutive fetches overlap by ~29 days. Without stitching, this creates artificial
    level jumps. Stitching normalizes windows into continuous time series.

    Algorithm:
    1. Find overlap region between old (database) and new (fetched) windows
    2. Compute scaling factor using trimmed mean (20% trim) from overlap
    3. Apply scaling factor to new (non-overlapping) records
    4. Store both rsv_raw and rsv_stitched for audit trail

    Args:
        db_conn: SQLite database connection
        min_overlap_days: Minimum required overlap (default: 1, warn if <3)
        trim_percent: Percentage to trim from each tail for robust mean (0-50)
    """

    def __init__(
        self,
        db_conn,
        min_overlap_days: int = 1,
        trim_percent: int = 20
    ):
        """Initialize StitcherService with configuration."""
        if not (0 <= trim_percent <= 50):
            raise ValueError("trim_percent must be between 0 and 50")

        self.db_conn = db_conn
        self.min_overlap_days = min_overlap_days
        self.trim_percent = trim_percent

        logger.info(
            f"StitcherService initialized: min_overlap={min_overlap_days} days, "
            f"trim={trim_percent}%"
        )

    def find_overlap(
        self,
        keyword: str,
        overlap_start: date,
        overlap_end: date
    ) -> List[Tuple[date, float]]:
        """
        Find existing records in overlap region for keyword.

        Queries database for records in date range, preferring rsv_stitched
        over rsv_raw (for consecutive stitching).

        Excludes records with quality='coarse' per FR-012 to prevent
        normalization drift from weekly-derived records.

        Args:
            keyword: Thai keyword term (e.g., ไข้)
            overlap_start: First date in overlap window
            overlap_end: Last date in overlap window

        Returns:
            List of (date, rsv_value) tuples, empty if no existing data
        """
        # Get connection from DatabaseConnection object
        with self.db_conn.get_connection(auto_commit=False) as conn:
            cursor = conn.cursor()

            # Query existing records, preferring stitched over raw
            # Exclude coarse quality records from stitching calculations (FR-012)
            sql = """
            SELECT date, COALESCE(rsv_stitched, rsv_raw) as rsv_value
            FROM raw_trenddata
            WHERE keyword = ?
              AND date >= ?
              AND date <= ?
              AND quality = 'true'
            ORDER BY date ASC
            """

            cursor.execute(sql, (keyword, overlap_start, overlap_end))
            overlap_records = cursor.fetchall()

            logger.info(
                f"Found {len(overlap_records)} overlap records for keyword='{keyword}' "
                f"in range {overlap_start} to {overlap_end}"
            )

            return overlap_records

    def compute_scaling_factor(
        self,
        old_overlap: List[float],
        new_overlap: List[float],
        keyword: str = None
    ) -> float:
        """
        Compute scaling factor using trimmed mean algorithm.

        Uses scipy.stats.trim_mean with configurable trim percentage to
        down-weight outliers and single-day spikes.

        Formula:
            scaling_factor = trimmed_mean(old_overlap) / trimmed_mean(new_overlap)

        Edge cases:
        - If new_trimmed == 0: return 1.0 (preserve zeros, no manufactured signal)
        - If overlap < min_overlap_days: raise StitchingException
        - If overlap < 3 days: log degradation warning (FR-007)
        - If old/new lengths mismatch: raise StitchingException

        Args:
            old_overlap: RSV values from previous fetch (database)
            new_overlap: RSV values from current fetch
            keyword: Optional keyword for warning messages

        Returns:
            Scaling factor to apply to new records

        Raises:
            StitchingException: If overlap insufficient or lengths mismatch
        """
        # Validate overlap length
        if len(old_overlap) < self.min_overlap_days:
            raise StitchingException(
                f"Insufficient overlap: {len(old_overlap)} days "
                f"(minimum {self.min_overlap_days} required)"
            )

        if len(old_overlap) != len(new_overlap):
            raise StitchingException(
                f"Overlap length mismatch: old={len(old_overlap)}, "
                f"new={len(new_overlap)}"
            )

        # Warn if overlap < 3 days (degradation threshold per FR-007)
        if len(old_overlap) < 3:
            warning_msg = (
                f"Stitching degradation: keyword='{keyword}', "
                f"overlap={len(old_overlap)} days, warning: <3 days"
            )
            logger.warning(warning_msg)

        # Compute trimmed means (proportiontocut is fraction from EACH tail)
        proportiontocut = self.trim_percent / 100.0
        old_trimmed = trim_mean(old_overlap, proportiontocut=proportiontocut)
        new_trimmed = trim_mean(new_overlap, proportiontocut=proportiontocut)

        # Handle zero-division: preserve zeros, no manufactured signal (FR-006)
        if new_trimmed == 0:
            logger.info(
                f"Zero-division handling for keyword='{keyword}': "
                f"new_trimmed=0, returning scaling_factor=1.0"
            )
            return 1.0

        scaling_factor = old_trimmed / new_trimmed

        logger.info(
            f"Computed scaling factor for keyword='{keyword}': "
            f"factor={scaling_factor:.3f}, overlap={len(old_overlap)} days, "
            f"old_trimmed={old_trimmed:.2f}, new_trimmed={new_trimmed:.2f}"
        )

        return scaling_factor

    def apply_stitching(
        self,
        new_records: List,
        scaling_factor: Optional[float]
    ) -> List:
        """
        Apply scaling factor to new records, updating rsv_stitched attribute.

        For first ingestion (scaling_factor=None), sets rsv_stitched = rsv_raw.
        For subsequent ingestions, applies scaling factor: rsv_stitched = rsv_raw * factor.

        Preserves zeros as zero (no manufactured signal).

        Args:
            new_records: List of RSVRecord objects to stitch
            scaling_factor: Scaling factor from compute_scaling_factor(), or None for first ingestion

        Returns:
            Same list of records with rsv_stitched updated (modified in-place)
        """
        for record in new_records:
            if scaling_factor is None:
                # First ingestion: no overlap, copy raw value
                record.rsv_stitched = float(record.rsv_raw)
            else:
                # Apply stitching: multiply by scaling factor
                if record.rsv_raw == 0:
                    record.rsv_stitched = 0.0  # Preserve zeros
                else:
                    record.rsv_stitched = record.rsv_raw * scaling_factor

        logger.debug(
            f"Applied stitching to {len(new_records)} records "
            f"(scaling_factor={scaling_factor})"
        )

        return new_records

    def format_stitching_metadata(
        self,
        keyword: str,
        scaling_factor: Optional[float],
        overlap_days: int
    ) -> str:
        """
        Format stitching metadata for batch event notes (audit trail per FR-008).

        Args:
            keyword: Thai keyword term
            scaling_factor: Computed scaling factor, or None if no overlap
            overlap_days: Number of days in overlap region

        Returns:
            Formatted metadata string for batch event notes
        """
        if scaling_factor is None:
            return (
                f"Stitching keyword='{keyword}': no overlap, "
                f"first ingestion (rsv_stitched = rsv_raw)"
            )
        else:
            return (
                f"Stitching keyword='{keyword}': "
                f"factor={scaling_factor:.2f}, overlap={overlap_days} days"
            )
