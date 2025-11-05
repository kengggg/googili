"""
Base Exception Classes

Custom exceptions for Fetcher core error handling.

Constitution alignment:
- Principle VI: Clarity Over Cleverness - Explicit error types
"""


class FetcherException(Exception):
    """Base exception for all Fetcher core errors."""
    pass


class DatabaseException(FetcherException):
    """Raised when database operations fail."""
    pass


class ConfigException(FetcherException):
    """Raised when configuration is invalid or missing."""
    pass


class PyTrendsException(FetcherException):
    """Raised when pytrends API calls fail."""
    pass


class RateLimitException(PyTrendsException):
    """
    Raised when Google Trends API returns HTTP 429 (rate limiting).

    This is a retriable error - ingestion service should mark batch as degraded
    and retry with exponential backoff.

    Args:
        message: Error message describing the rate limiting
        retry_after: Optional seconds to wait before retry (from Retry-After header)
    """
    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class StitchingException(FetcherException):
    """Raised when stitching algorithm fails."""
    pass


class ValidationException(FetcherException):
    """Raised when data validation fails."""
    pass


class SchedulingException(FetcherException):
    """Raised when APScheduler operations fail."""
    pass
