"""
Database State Detection

Determines database state for conditional ingestion logic:
- Empty database detection (trigger initial backfill)
- First-run vs. recovery scenario detection
- Gap detection for recovery backfills

Constitution alignment:
- Principle IV: Provenance - State detection enables audit trail decisions
- Principle III: TDD - Functions designed for behavioral testing
"""

import logging
from typing import Optional, Tuple
from datetime import date, timedelta

from lib.db import DatabaseConnection
from lib.timezone_utils import today_ict

logger = logging.getLogger(__name__)


def is_database_empty(db: DatabaseConnection) -> bool:
    """
    Check if raw_trenddata table is empty.

    Returns True if the table has zero rows, indicating this is the first
    deployment and initial backfill should be triggered.

    Args:
        db: Database connection

    Returns:
        True if raw_trenddata has 0 rows, False otherwise

    Examples:
        >>> # Fresh deployment
        >>> is_database_empty(db)
        True

        >>> # After initial backfill
        >>> is_database_empty(db)
        False
    """
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata")
        count = cursor.fetchone()[0]
        return count == 0


def get_raw_trenddata_count(db: DatabaseConnection) -> int:
    """
    Get total number of records in raw_trenddata table.

    Useful for logging and validation during backfill operations.

    Args:
        db: Database connection

    Returns:
        Total row count in raw_trenddata
    """
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata")
        return cursor.fetchone()[0]


def is_first_run(db: DatabaseConnection) -> bool:
    """
    Determine if this is truly the first run (no data AND no batch events).

    Distinguishes between:
    - First run: Empty database, no batch events (fresh deployment)
    - Recovery: Empty database but batch events exist (past backfill failed)

    Args:
        db: Database connection

    Returns:
        True if both raw_trenddata and events_raw_rsv_ingested are empty

    Examples:
        >>> # Fresh deployment - no data, no events
        >>> is_first_run(db)
        True

        >>> # Recovery scenario - no data but has failed batch events
        >>> is_first_run(db)
        False
    """
    with db.get_connection() as conn:
        # Check if raw_trenddata is empty
        cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata")
        data_count = cursor.fetchone()[0]

        # Check if batch events exist
        cursor = conn.execute("SELECT COUNT(*) FROM events_raw_rsv_ingested")
        event_count = cursor.fetchone()[0]

        # First run only if both are empty
        return data_count == 0 and event_count == 0


def needs_recovery(db: DatabaseConnection) -> bool:
    """
    Determine if recovery backfill is needed.

    Recovery is needed when:
    - Database is not empty (has some data)
    - But has failed batch events
    - OR has gaps in the data (missing recent days)

    Args:
        db: Database connection

    Returns:
        True if recovery backfill should be triggered

    Examples:
        >>> # Database has data but last backfill failed
        >>> needs_recovery(db)
        True

        >>> # Database healthy, daily ingestion working
        >>> needs_recovery(db)
        False
    """
    with db.get_connection() as conn:
        # Check if raw_trenddata is empty
        cursor = conn.execute("SELECT COUNT(*) FROM raw_trenddata")
        data_count = cursor.fetchone()[0]

        if data_count == 0:
            # Empty database - check if batch events exist (recovery scenario)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM events_raw_rsv_ingested WHERE status IN ('fail', 'degraded')"
            )
            failed_events = cursor.fetchone()[0]
            return failed_events > 0

        # Database has data - check for recent gaps
        # Get most recent date in database
        cursor = conn.execute("SELECT MAX(date) FROM raw_trenddata")
        most_recent_date_str = cursor.fetchone()[0]

        if most_recent_date_str is None:
            return False

        most_recent_date = date.fromisoformat(most_recent_date_str)
        today = today_ict()
        days_behind = (today - most_recent_date).days

        # If more than 2 days behind, recovery needed
        # (Yesterday's data should be available by today)
        return days_behind > 2


def get_database_state(db: DatabaseConnection) -> str:
    """
    Get overall database state for decision making.

    Returns one of:
    - 'empty_first_run': Fresh deployment, trigger initial backfill
    - 'empty_recovery': Past backfill failed, retry initial backfill
    - 'has_gaps': Data exists but missing recent days, trigger recovery backfill
    - 'healthy': Database up-to-date, normal daily ingestion

    Args:
        db: Database connection

    Returns:
        State string indicating what action should be taken
    """
    if is_database_empty(db):
        if is_first_run(db):
            return 'empty_first_run'
        else:
            return 'empty_recovery'
    elif needs_recovery(db):
        return 'has_gaps'
    else:
        return 'healthy'


def get_data_gap_info(db: DatabaseConnection) -> Optional[Tuple[date, date, int]]:
    """
    Detect gaps in data and return gap information.

    Identifies the date range where data is missing and needs to be backfilled.

    Args:
        db: Database connection

    Returns:
        Tuple of (gap_start, gap_end, days_missing) or None if no gap

    Examples:
        >>> # Database missing last 5 days
        >>> get_data_gap_info(db)
        (date(2025, 10, 30), date(2025, 11, 04), 5)

        >>> # Database up-to-date
        >>> get_data_gap_info(db)
        None
    """
    with db.get_connection() as conn:
        # Get most recent date in database
        cursor = conn.execute("SELECT MAX(date) FROM raw_trenddata")
        most_recent_date_str = cursor.fetchone()[0]

        if most_recent_date_str is None:
            # Empty database - no gap info, needs full backfill
            return None

        most_recent_date = date.fromisoformat(most_recent_date_str)
        today = today_ict()
        yesterday = today - timedelta(days=1)

        # Gap exists if most recent date is before yesterday
        if most_recent_date < yesterday:
            gap_start = most_recent_date + timedelta(days=1)
            gap_end = yesterday
            days_missing = (gap_end - gap_start).days + 1
            return (gap_start, gap_end, days_missing)

        return None
