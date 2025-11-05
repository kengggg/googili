"""
Fetcher Core Library Modules

Shared utilities for database, configuration, logging, timezone handling.
"""

from .db import DatabaseConnection, init_database
from .config import FetcherConfig
from .logging_utils import setup_logger, log_batch_event, setup_logging
from .timezone_utils import (
    ICT,
    now_ict,
    today_ict,
    days_ago_ict,
    date_to_ict_datetime,
    format_ict_timestamp,
    parse_ict_timestamp,
    date_range_ict,
    format_date_range
)
from .exceptions import (
    FetcherException,
    DatabaseException,
    ConfigException,
    PyTrendsException,
    StitchingException,
    ValidationException,
    SchedulingException
)

__all__ = [
    # Database
    'DatabaseConnection',
    'init_database',
    # Configuration
    'FetcherConfig',
    # Logging
    'setup_logger',
    'log_batch_event',
    'setup_logging',
    # Timezone
    'ICT',
    'now_ict',
    'today_ict',
    'days_ago_ict',
    'date_to_ict_datetime',
    'format_ict_timestamp',
    'parse_ict_timestamp',
    'date_range_ict',
    'format_date_range',
    # Exceptions
    'FetcherException',
    'DatabaseException',
    'ConfigException',
    'PyTrendsException',
    'StitchingException',
    'ValidationException',
    'SchedulingException',
]
