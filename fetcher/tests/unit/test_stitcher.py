"""
Unit tests for StitcherService - Overlap-based stitching with trimmed mean.

Tests the core stitching algorithm that normalizes consecutive 'today 1-m' fetches
into a continuous time series without normalization jumps.

TDD: WRITE FIRST, ENSURE FAIL per Constitution Principle III.
"""

import pytest
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock
from scipy.stats import trim_mean

# Import the service to be tested (will fail until implemented)
try:
    from src.services.stitcher import StitcherService
    from src.models.rsv_record import RSVRecord
except ImportError:
    # Expected to fail initially (TDD RED phase)
    StitcherService = None
    RSVRecord = None

from src.lib.exceptions import StitchingException


def create_mock_db_connection(cursor_mock):
    """Helper to create a mock DatabaseConnection with context manager support."""
    mock_conn = Mock()
    mock_conn.cursor.return_value = cursor_mock
    mock_conn.execute = cursor_mock.execute

    mock_db = Mock()
    mock_db.get_connection = Mock(return_value=mock_conn)
    mock_db.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_db.get_connection.return_value.__exit__ = Mock(return_value=False)

    return mock_db


class TestStitcherServiceInitialization:
    """Test StitcherService initialization and configuration."""

    def test_stitcher_initializes_with_config(self):
        """Test StitcherService accepts configuration parameters."""
        # ARRANGE
        mock_db = Mock()
        min_overlap = 1
        trim_percent = 20

        # ACT
        stitcher = StitcherService(
            db_conn=mock_db,
            min_overlap_days=min_overlap,
            trim_percent=trim_percent
        )

        # ASSERT
        assert stitcher.min_overlap_days == 1
        assert stitcher.trim_percent == 20
        assert stitcher.db_conn is mock_db

    def test_stitcher_validates_trim_percent_range(self):
        """Test trim_percent must be in range 0-50."""
        mock_db = Mock()

        # Valid range
        StitcherService(mock_db, min_overlap_days=1, trim_percent=0)
        StitcherService(mock_db, min_overlap_days=1, trim_percent=25)
        StitcherService(mock_db, min_overlap_days=1, trim_percent=50)

        # Invalid range
        with pytest.raises(ValueError, match="trim_percent must be between 0 and 50"):
            StitcherService(mock_db, min_overlap_days=1, trim_percent=-1)

        with pytest.raises(ValueError, match="trim_percent must be between 0 and 50"):
            StitcherService(mock_db, min_overlap_days=1, trim_percent=51)


class TestOverlapWindowExtraction:
    """Test finding overlap region between consecutive fetches."""

    def test_find_overlap_queries_database_for_keyword(self):
        """Test find_overlap queries database for existing records in date range."""
        # ARRANGE
        mock_cursor = Mock()
        mock_db = create_mock_db_connection(mock_cursor)

        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        keyword = "ไข้"
        overlap_start = date(2025, 10, 10)
        overlap_end = date(2025, 11, 7)

        # Mock database response: [(date, rsv_stitched or rsv_raw), ...]
        mock_cursor.fetchall.return_value = [
            (date(2025, 10, 10), 45.0),
            (date(2025, 10, 11), 48.0),
            (date(2025, 10, 12), 50.0),
        ]

        # ACT
        overlap_records = stitcher.find_overlap(
            keyword=keyword,
            overlap_start=overlap_start,
            overlap_end=overlap_end
        )

        # ASSERT
        assert len(overlap_records) == 3
        assert overlap_records[0] == (date(2025, 10, 10), 45.0)

        # Verify SQL query structure (should query raw_trenddata with quality='true')
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "raw_trenddata" in sql_call
        assert "quality = 'true'" in sql_call  # Exclude coarse records per FR-012
        assert "keyword = ?" in sql_call
        assert "date >= ?" in sql_call
        assert "date <= ?" in sql_call

    def test_find_overlap_returns_empty_list_when_no_existing_data(self):
        """Test find_overlap returns empty list for first ingestion (no overlap)."""
        # ARRANGE
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = []  # No existing data
        mock_db = create_mock_db_connection(mock_cursor)

        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        # ACT
        overlap_records = stitcher.find_overlap(
            keyword="ไข้",
            overlap_start=date(2025, 10, 10),
            overlap_end=date(2025, 11, 7)
        )

        # ASSERT
        assert overlap_records == []

    def test_find_overlap_prefers_stitched_over_raw(self):
        """Test find_overlap uses rsv_stitched if available, else rsv_raw."""
        # ARRANGE
        mock_cursor = Mock()
        # Mock response with mixed stitched/raw values
        mock_cursor.fetchall.return_value = [
            (date(2025, 10, 10), 45.0),   # Has stitched value
            (date(2025, 10, 11), 48),     # Raw value (no stitched yet)
        ]
        mock_db = create_mock_db_connection(mock_cursor)

        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        # ACT
        overlap_records = stitcher.find_overlap(
            keyword="ไข้",
            overlap_start=date(2025, 10, 10),
            overlap_end=date(2025, 11, 11)
        )

        # ASSERT
        assert overlap_records[0] == (date(2025, 10, 10), 45.0)
        assert overlap_records[1] == (date(2025, 10, 11), 48)

        # Verify SQL uses COALESCE(rsv_stitched, rsv_raw)
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "COALESCE(rsv_stitched, rsv_raw)" in sql_call


class TestScalingFactorComputation:
    """Test compute_scaling_factor with trimmed mean algorithm."""

    def test_compute_scaling_factor_with_trimmed_mean(self):
        """Test scaling factor computation using scipy.stats.trim_mean (20% trim)."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        # Overlap data: old vs. new window for same date range
        old_overlap = [40, 42, 45, 48, 50, 52, 55, 58, 60, 100]  # Last value is outlier
        new_overlap = [20, 21, 22, 24, 25, 26, 27, 29, 30, 50]   # Last value is outlier

        # ACT
        scaling_factor = stitcher.compute_scaling_factor(old_overlap, new_overlap)

        # ASSERT
        # Manually compute expected value
        old_trimmed = trim_mean(old_overlap, proportiontocut=0.2)  # Drops top/bottom 20%
        new_trimmed = trim_mean(new_overlap, proportiontocut=0.2)
        expected_factor = old_trimmed / new_trimmed

        assert scaling_factor == pytest.approx(expected_factor, rel=1e-6)

    def test_trimmed_mean_down_weights_outliers(self):
        """Test trimmed mean produces different result than simple mean (outlier robustness)."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        # Create data with extreme outlier spike
        old_overlap = [45, 46, 47, 48, 49, 50, 51, 52, 53, 200]  # 200 is spike
        new_overlap = [22, 23, 24, 25, 26, 27, 28, 29, 30, 31]

        # ACT
        trimmed_factor = stitcher.compute_scaling_factor(old_overlap, new_overlap)

        # ASSERT
        # Compute simple mean for comparison
        simple_mean_old = sum(old_overlap) / len(old_overlap)
        simple_mean_new = sum(new_overlap) / len(new_overlap)
        simple_factor = simple_mean_old / simple_mean_new

        # Trimmed mean should differ from simple mean by >10% (SC-005 criterion)
        assert abs(trimmed_factor - simple_factor) / simple_factor > 0.10

    def test_zero_division_handling_returns_one(self):
        """Test scaling factor defaults to 1.0 when new_trimmed == 0 (zero preservation)."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        old_overlap = [40, 42, 45, 48, 50]
        new_overlap = [0, 0, 0, 0, 0]  # All zeros

        # ACT
        scaling_factor = stitcher.compute_scaling_factor(old_overlap, new_overlap)

        # ASSERT
        assert scaling_factor == 1.0  # No manufactured signal per FR-006

    def test_insufficient_overlap_raises_exception(self):
        """Test exception raised when overlap < min_overlap_days."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=3, trim_percent=20)

        old_overlap = [40, 42]  # Only 2 days
        new_overlap = [20, 21]

        # ACT & ASSERT
        with pytest.raises(StitchingException, match="Insufficient overlap"):
            stitcher.compute_scaling_factor(old_overlap, new_overlap)

    def test_empty_overlap_raises_exception(self):
        """Test exception raised when overlap is empty."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        old_overlap = []
        new_overlap = []

        # ACT & ASSERT
        with pytest.raises(StitchingException, match="Insufficient overlap"):
            stitcher.compute_scaling_factor(old_overlap, new_overlap)

    def test_overlap_length_mismatch_raises_exception(self):
        """Test exception when old and new overlap have different lengths."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        old_overlap = [40, 42, 45]
        new_overlap = [20, 21]  # Different length

        # ACT & ASSERT
        with pytest.raises(StitchingException, match="Overlap length mismatch"):
            stitcher.compute_scaling_factor(old_overlap, new_overlap)


class TestStitchingApplication:
    """Test apply_stitching method that updates rsv_stitched values."""

    def test_apply_stitching_to_new_records(self):
        """Test stitching application multiplies rsv_raw by scaling factor."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        # Mock RSVRecord objects
        new_records = [
            Mock(date=date(2025, 11, 8), rsv_raw=25, rsv_stitched=None),
            Mock(date=date(2025, 11, 9), rsv_raw=30, rsv_stitched=None),
            Mock(date=date(2025, 11, 10), rsv_raw=35, rsv_stitched=None),
        ]

        scaling_factor = 2.0

        # ACT
        stitched_records = stitcher.apply_stitching(new_records, scaling_factor)

        # ASSERT
        assert stitched_records[0].rsv_stitched == pytest.approx(50.0)  # 25 * 2.0
        assert stitched_records[1].rsv_stitched == pytest.approx(60.0)  # 30 * 2.0
        assert stitched_records[2].rsv_stitched == pytest.approx(70.0)  # 35 * 2.0

    def test_apply_stitching_preserves_zeros(self):
        """Test stitching preserves zero values (no manufactured signal)."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        new_records = [
            Mock(date=date(2025, 11, 8), rsv_raw=0, rsv_stitched=None),
            Mock(date=date(2025, 11, 9), rsv_raw=25, rsv_stitched=None),
        ]

        scaling_factor = 2.0

        # ACT
        stitched_records = stitcher.apply_stitching(new_records, scaling_factor)

        # ASSERT
        assert stitched_records[0].rsv_stitched == 0.0  # Zero preserved
        assert stitched_records[1].rsv_stitched == pytest.approx(50.0)

    def test_apply_stitching_with_no_overlap_copies_raw(self):
        """Test first ingestion (no overlap): rsv_stitched = rsv_raw."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        new_records = [
            Mock(date=date(2025, 10, 10), rsv_raw=45, rsv_stitched=None),
            Mock(date=date(2025, 10, 11), rsv_raw=48, rsv_stitched=None),
        ]

        scaling_factor = None  # Indicates no overlap

        # ACT
        stitched_records = stitcher.apply_stitching(new_records, scaling_factor)

        # ASSERT
        assert stitched_records[0].rsv_stitched == 45.0  # Copy of rsv_raw
        assert stitched_records[1].rsv_stitched == 48.0


class TestStitchingDegradationWarnings:
    """Test degradation detection when overlap is insufficient."""

    def test_warn_when_overlap_less_than_3_days(self):
        """Test warning logged when overlap < 3 days (FR-007)."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        old_overlap = [40, 42]  # Only 2 days
        new_overlap = [20, 21]

        # ACT & ASSERT
        # Should compute scaling factor but log degradation warning
        with patch('src.services.stitcher.logger') as mock_logger:
            scaling_factor = stitcher.compute_scaling_factor(
                old_overlap, new_overlap,
                keyword="ไข้"  # Pass keyword for warning message
            )

            # Verify warning logged
            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "overlap=2 days" in warning_msg
            assert "warning: <3 days" in warning_msg
            assert "keyword='ไข้'" in warning_msg

    def test_no_warning_when_overlap_sufficient(self):
        """Test no warning when overlap >= 3 days."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        old_overlap = [40, 42, 45, 48]  # 4 days
        new_overlap = [20, 21, 22, 24]

        # ACT & ASSERT
        with patch('src.services.stitcher.logger') as mock_logger:
            scaling_factor = stitcher.compute_scaling_factor(
                old_overlap, new_overlap,
                keyword="ไข้"
            )

            # Verify no warning logged
            mock_logger.warning.assert_not_called()


class TestStitchingMetadata:
    """Test stitching metadata formatting for batch event notes."""

    def test_format_stitching_metadata(self):
        """Test metadata formatting for batch event audit trail (FR-008)."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        keyword = "ไข้"
        scaling_factor = 1.18456
        overlap_days = 29

        # ACT
        metadata = stitcher.format_stitching_metadata(
            keyword=keyword,
            scaling_factor=scaling_factor,
            overlap_days=overlap_days
        )

        # ASSERT
        assert "keyword='ไข้'" in metadata
        assert "factor=1.18" in metadata  # Rounded to 2 decimals
        assert "overlap=29 days" in metadata

    def test_metadata_includes_no_overlap_message(self):
        """Test metadata when no overlap found (first ingestion)."""
        # ARRANGE
        mock_db = Mock()
        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        keyword = "ไข้"

        # ACT
        metadata = stitcher.format_stitching_metadata(
            keyword=keyword,
            scaling_factor=None,  # No overlap
            overlap_days=0
        )

        # ASSERT
        assert "keyword='ไข้'" in metadata
        assert "no overlap" in metadata.lower()
        assert "first ingestion" in metadata.lower()


class TestEndToEndStitchingWorkflow:
    """Integration-style tests for complete stitching workflow."""

    def test_complete_stitching_workflow(self):
        """Test complete workflow: find overlap → compute factor → apply stitching."""
        # ARRANGE
        mock_cursor = Mock()
        # Mock existing overlap data from database
        mock_cursor.fetchall.return_value = [
            (date(2025, 10, 10), 40),
            (date(2025, 10, 11), 42),
            (date(2025, 10, 12), 45),
            (date(2025, 10, 13), 48),
            (date(2025, 10, 14), 50),
        ]
        mock_db = create_mock_db_connection(mock_cursor)

        stitcher = StitcherService(mock_db, min_overlap_days=1, trim_percent=20)

        keyword = "ไข้"
        overlap_start = date(2025, 10, 10)
        overlap_end = date(2025, 11, 7)

        # New records from today's fetch (overlap Oct 10-14, new Nov 8)
        new_records_with_overlap = [
            Mock(date=date(2025, 10, 10), rsv_raw=20, rsv_stitched=None),
            Mock(date=date(2025, 10, 11), rsv_raw=21, rsv_stitched=None),
            Mock(date=date(2025, 10, 12), rsv_raw=22, rsv_stitched=None),
            Mock(date=date(2025, 10, 13), rsv_raw=24, rsv_stitched=None),
            Mock(date=date(2025, 10, 14), rsv_raw=25, rsv_stitched=None),
            Mock(date=date(2025, 11, 8), rsv_raw=30, rsv_stitched=None),  # NEW
        ]

        # ACT
        # Step 1: Find overlap
        overlap_records = stitcher.find_overlap(keyword, overlap_start, overlap_end)

        # Step 2: Extract overlap values from new records
        new_overlap = [rec.rsv_raw for rec in new_records_with_overlap[:5]]
        old_overlap = [val for _, val in overlap_records]

        # Step 3: Compute scaling factor
        scaling_factor = stitcher.compute_scaling_factor(old_overlap, new_overlap)

        # Step 4: Apply stitching to NEW records only (Nov 8)
        new_only = [new_records_with_overlap[-1]]  # Just Nov 8
        stitched_records = stitcher.apply_stitching(new_only, scaling_factor)

        # ASSERT
        assert len(overlap_records) == 5
        assert scaling_factor > 0
        assert stitched_records[0].rsv_stitched == pytest.approx(30 * scaling_factor)
