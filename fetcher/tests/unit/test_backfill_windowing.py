"""
Unit Tests for Backfill Window Calculation - User Story 2

Tests WHAT the backfill window calculator does, not HOW:
- Calculates 90-day date range ending T-1 (yesterday ICT)
- Handles timezone correctly (Asia/Bangkok)
- Validates partial availability scenarios

Constitution alignment:
- Principle III: TDD - Tests written BEFORE implementation (RED phase)
- Principle VII: Configuration-as-Code - Uses config for days parameter

Test Strategy:
- Behavioral tests: Verify date range calculation logic
- Timezone tests: Verify ICT timezone handling
- Edge cases: Handle month boundaries, leap years
"""

import pytest
from datetime import date, timedelta
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestBackfillWindowCalculation:
    """Test that backfill window calculator produces correct date ranges."""

    def test_calculate_90_day_backfill_window_from_today(self):
        """
        SPEC: US2 - 90-day historical backfill on first deployment
        BEHAVIOR: calculate_backfill_window(days=90) returns [today-90, today-1] date range
        """
        from services.backfill import calculate_backfill_window
        from lib.timezone_utils import ICT
        from datetime import datetime

        # Execute: Calculate 90-day window ending yesterday (T-1)
        start_date, end_date = calculate_backfill_window(days=90)

        # Calculate expected values using ICT timezone
        today_ict = datetime.now(ICT).date()
        yesterday_ict = today_ict - timedelta(days=1)
        expected_start = yesterday_ict - timedelta(days=89)  # 90 days total including end date

        # Verify: Date range is exactly 90 days ending yesterday
        assert start_date == expected_start, \
            f"Start date should be 90 days before yesterday: {expected_start}, got {start_date}"
        assert end_date == yesterday_ict, \
            f"End date should be yesterday in ICT: {yesterday_ict}, got {end_date}"

        # Verify: Range is exactly 90 days
        range_days = (end_date - start_date).days + 1
        assert range_days == 90, f"Range should be exactly 90 days, got {range_days}"

    def test_calculate_custom_day_backfill_window(self):
        """
        SPEC: US2 - Support configurable backfill days
        BEHAVIOR: calculate_backfill_window(days=N) returns N-day range
        """
        from services.backfill import calculate_backfill_window
        from lib.timezone_utils import ICT
        from datetime import datetime

        # Execute: Calculate 30-day window
        start_date, end_date = calculate_backfill_window(days=30)

        # Calculate expected values
        today_ict = datetime.now(ICT).date()
        yesterday_ict = today_ict - timedelta(days=1)
        expected_start = yesterday_ict - timedelta(days=29)

        # Verify: Range is exactly 30 days
        assert start_date == expected_start
        assert end_date == yesterday_ict
        range_days = (end_date - start_date).days + 1
        assert range_days == 30, f"Range should be exactly 30 days, got {range_days}"

    def test_calculate_backfill_window_uses_ict_timezone(self):
        """
        SPEC: US2 - All date calculations use Asia/Bangkok timezone
        BEHAVIOR: Window calculation uses ICT timezone, not system timezone
        """
        from services.backfill import calculate_backfill_window
        from lib.timezone_utils import ICT
        from datetime import datetime

        # Execute: Get window
        start_date, end_date = calculate_backfill_window(days=90)

        # Calculate what "yesterday" is in ICT
        today_ict = datetime.now(ICT).date()
        yesterday_ict = today_ict - timedelta(days=1)

        # Verify: End date matches ICT yesterday, not system timezone yesterday
        assert end_date == yesterday_ict, \
            "End date must use ICT timezone, not system timezone"

    def test_calculate_backfill_window_returns_date_objects(self):
        """
        SPEC: US2 - Date range should be date objects for API compatibility
        BEHAVIOR: Returns tuple of (start_date: date, end_date: date)
        """
        from services.backfill import calculate_backfill_window
        from datetime import date

        # Execute
        start_date, end_date = calculate_backfill_window(days=90)

        # Verify: Both are date objects (not datetime)
        assert isinstance(start_date, date), "Start date must be date object"
        assert isinstance(end_date, date), "End date must be date object"

    def test_calculate_backfill_window_handles_month_boundaries(self):
        """
        SPEC: US2 - Handle month/year boundaries correctly
        BEHAVIOR: Window calculation works across month boundaries
        """
        from services.backfill import calculate_backfill_window

        # Execute: 90-day window will cross month boundaries
        start_date, end_date = calculate_backfill_window(days=90)

        # Verify: Start and end dates are valid
        assert start_date < end_date, "Start date must be before end date"

        # Verify: No invalid dates (would raise ValueError if date arithmetic wrong)
        assert start_date.year >= 2000, "Start date should be reasonable"
        assert end_date.year >= 2000, "End date should be reasonable"


class TestBackfillWindowEdgeCases:
    """Test edge cases for backfill window calculation."""

    def test_calculate_backfill_window_minimum_1_day(self):
        """
        SPEC: US2 - Minimum backfill is 1 day
        BEHAVIOR: days=1 returns single-day window (yesterday)
        """
        from services.backfill import calculate_backfill_window
        from lib.timezone_utils import ICT
        from datetime import datetime

        # Execute
        start_date, end_date = calculate_backfill_window(days=1)

        # Calculate expected
        today_ict = datetime.now(ICT).date()
        yesterday_ict = today_ict - timedelta(days=1)

        # Verify: Both dates are yesterday (single-day range)
        assert start_date == yesterday_ict
        assert end_date == yesterday_ict
        range_days = (end_date - start_date).days + 1
        assert range_days == 1

    def test_calculate_backfill_window_rejects_zero_days(self):
        """
        SPEC: US2 - Backfill must have at least 1 day
        BEHAVIOR: days=0 raises ValueError
        """
        from services.backfill import calculate_backfill_window

        # Execute & Verify: Should raise ValueError
        with pytest.raises(ValueError, match="days must be >= 1"):
            calculate_backfill_window(days=0)

    def test_calculate_backfill_window_rejects_negative_days(self):
        """
        SPEC: US2 - Backfill days must be positive
        BEHAVIOR: days<0 raises ValueError
        """
        from services.backfill import calculate_backfill_window

        # Execute & Verify: Should raise ValueError
        with pytest.raises(ValueError, match="days must be >= 1"):
            calculate_backfill_window(days=-5)


class TestBackfillWindowFormatting:
    """Test that backfill window dates are formatted correctly for logging."""

    def test_backfill_window_str_representation(self):
        """
        SPEC: US2 - Log backfill window for audit trail
        BEHAVIOR: Window should be representable as ISO 8601 date range
        """
        from services.backfill import calculate_backfill_window

        # Execute
        start_date, end_date = calculate_backfill_window(days=90)

        # Verify: Can convert to ISO 8601 string (YYYY-MM-DD format)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        assert len(start_str) == 10, "ISO date should be 10 chars (YYYY-MM-DD)"
        assert len(end_str) == 10, "ISO date should be 10 chars (YYYY-MM-DD)"
        assert start_str < end_str, "Start date string should be lexically before end date"
