"""
Timezone Utilities Module

Asia/Bangkok (ICT) timezone handling per Constitution Principle IV.

All timestamps in GOOGILI use Asia/Bangkok timezone for consistency with
local public health workflows.
"""

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Optional


# ICT timezone constant
ICT = ZoneInfo("Asia/Bangkok")


def now_ict() -> datetime:
    """
    Get current datetime in Asia/Bangkok timezone.

    Returns:
        datetime: Current time in ICT (Asia/Bangkok)
    """
    return datetime.now(ICT)


def date_to_ict_datetime(d: date, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    """
    Convert date to datetime in ICT timezone.

    Args:
        d: Date to convert
        hour: Hour (0-23)
        minute: Minute (0-59)
        second: Second (0-59)

    Returns:
        datetime: Datetime in Asia/Bangkok timezone

    Raises:
        ValueError: If hour, minute, or second are out of valid ranges
    """
    # Fix 7: Validate time components
    if not (0 <= hour <= 23):
        raise ValueError(f"Hour must be 0-23, got {hour}")
    if not (0 <= minute <= 59):
        raise ValueError(f"Minute must be 0-59, got {minute}")
    if not (0 <= second <= 59):
        raise ValueError(f"Second must be 0-59, got {second}")

    return datetime(d.year, d.month, d.day, hour, minute, second, tzinfo=ICT)


def format_ict_timestamp(dt: datetime) -> str:
    """
    Format datetime as ISO 8601 string with ICT timezone.

    Args:
        dt: Datetime to format (will be converted to ICT if not already)

    Returns:
        str: ISO 8601 formatted string (e.g., "2025-11-04T07:32:15+07:00")
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ICT)
    elif dt.tzinfo != ICT:
        dt = dt.astimezone(ICT)

    return dt.isoformat()


def parse_ict_timestamp(timestamp_str: str) -> datetime:
    """
    Parse ISO 8601 timestamp string to datetime in ICT.

    Args:
        timestamp_str: ISO 8601 formatted string

    Returns:
        datetime: Parsed datetime in Asia/Bangkok timezone
    """
    dt = datetime.fromisoformat(timestamp_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ICT)
    else:
        dt = dt.astimezone(ICT)
    return dt


def today_ict() -> date:
    """
    Get today's date in Asia/Bangkok timezone.

    Returns:
        date: Today's date in ICT
    """
    return now_ict().date()


def days_ago_ict(days: int) -> date:
    """
    Get date N days ago in Asia/Bangkok timezone.

    Args:
        days: Number of days to go back

    Returns:
        date: Date N days ago in ICT
    """
    return today_ict() - timedelta(days=days)


def date_range_ict(start_date: date, end_date: date) -> list[date]:
    """
    Generate list of dates between start and end (inclusive).

    Args:
        start_date: Start date
        end_date: End date (inclusive)

    Returns:
        list[date]: List of dates from start to end

    Raises:
        ValueError: If start_date is after end_date
    """
    # Fix 7: Validate date range
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) must be <= end_date ({end_date})")

    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def format_date_range(start_date: date, end_date: date) -> str:
    """
    Format date range as string for batch events.

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        str: Formatted range (e.g., "2025-11-03 to 2025-11-04")
    """
    return f"{start_date.isoformat()} to {end_date.isoformat()}"
