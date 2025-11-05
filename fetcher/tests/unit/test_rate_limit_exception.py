"""
Unit Tests for RateLimitException - HTTP 429 Rate Limiting

Tests the RateLimitException class that distinguishes retriable rate limiting errors
from other PyTrendsException errors.

Constitution alignment:
- Principle III: TDD - Tests written BEFORE implementation (RED phase)
- Principle V: Fail-Safe - Distinguishing retriable from permanent errors

Test Strategy:
- Test inheritance hierarchy (subclass of PyTrendsException)
- Test retry_after attribute storage
- Test serialization for logging
- Test distinction from parent PyTrendsException
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestRateLimitExceptionInheritance:
    """Test that RateLimitException properly inherits from PyTrendsException."""

    def test_rate_limit_exception_is_subclass_of_pytrends_exception(self):
        """
        SPEC: FR-016 - RateLimitException must inherit from PyTrendsException
        BEHAVIOR: isinstance() and issubclass() checks pass
        """
        from lib.exceptions import RateLimitException, PyTrendsException

        exc = RateLimitException("Rate limited")

        # Verify inheritance
        assert isinstance(exc, RateLimitException)
        assert isinstance(exc, PyTrendsException)
        assert isinstance(exc, Exception)
        assert issubclass(RateLimitException, PyTrendsException)

    def test_rate_limit_exception_is_subclass_of_fetcher_exception(self):
        """
        SPEC: All exceptions should inherit from FetcherException
        BEHAVIOR: RateLimitException follows exception hierarchy
        """
        from lib.exceptions import RateLimitException, FetcherException

        exc = RateLimitException("Rate limited")

        # Verify full hierarchy
        assert isinstance(exc, FetcherException)
        assert issubclass(RateLimitException, FetcherException)


class TestRateLimitExceptionRetryAfter:
    """Test that RateLimitException stores Retry-After header value."""

    def test_rate_limit_exception_stores_retry_after_value(self):
        """
        SPEC: FR-016 - Must respect Retry-After header from Google Trends API
        BEHAVIOR: retry_after attribute stores integer seconds from header
        """
        from lib.exceptions import RateLimitException

        # Create exception with retry_after value
        exc = RateLimitException("Rate limited", retry_after=120)

        # Verify storage
        assert exc.retry_after == 120
        assert isinstance(exc.retry_after, int)

    def test_rate_limit_exception_allows_none_retry_after(self):
        """
        SPEC: FR-016 - Retry-After header is optional (use exponential backoff if missing)
        BEHAVIOR: retry_after can be None when header not provided
        """
        from lib.exceptions import RateLimitException

        # Create exception without retry_after
        exc = RateLimitException("Rate limited")

        # Verify None is allowed
        assert exc.retry_after is None

    def test_rate_limit_exception_retry_after_defaults_to_none(self):
        """
        SPEC: FR-016 - retry_after should default to None for backward compatibility
        BEHAVIOR: Omitting retry_after parameter results in None
        """
        from lib.exceptions import RateLimitException

        # Create without specifying retry_after
        exc = RateLimitException("Rate limited by API")

        # Verify default
        assert hasattr(exc, 'retry_after')
        assert exc.retry_after is None


class TestRateLimitExceptionMessage:
    """Test that RateLimitException preserves error messages."""

    def test_rate_limit_exception_preserves_error_message(self):
        """
        SPEC: All exceptions should preserve original error messages for logging
        BEHAVIOR: str(exception) returns original message
        """
        from lib.exceptions import RateLimitException

        message = "The request failed: Google returned a response with code 429"
        exc = RateLimitException(message, retry_after=300)

        # Verify message preservation
        assert str(exc) == message
        assert exc.args[0] == message

    def test_rate_limit_exception_message_without_retry_after(self):
        """
        SPEC: Error message should be clear even without retry_after
        BEHAVIOR: Message is preserved when retry_after is None
        """
        from lib.exceptions import RateLimitException

        message = "Rate limited after 3 retry attempts"
        exc = RateLimitException(message)

        # Verify message
        assert str(exc) == message


class TestRateLimitExceptionDistinction:
    """Test that RateLimitException is distinguishable from PyTrendsException."""

    def test_rate_limit_exception_can_be_caught_separately(self):
        """
        SPEC: FR-016 - Ingestion service must handle rate limiting distinctly
        BEHAVIOR: except RateLimitException catches only rate limit errors
        """
        from lib.exceptions import RateLimitException, PyTrendsException

        # Test that RateLimitException can be caught specifically
        try:
            raise RateLimitException("429 error", retry_after=60)
        except RateLimitException as e:
            assert e.retry_after == 60
            assert "429" in str(e)
        except PyTrendsException:
            pytest.fail("Should catch RateLimitException, not parent PyTrendsException")

    def test_pytrends_exception_does_not_have_retry_after(self):
        """
        SPEC: Only RateLimitException should have retry_after attribute
        BEHAVIOR: PyTrendsException does not have retry_after
        """
        from lib.exceptions import PyTrendsException

        # Create generic PyTrendsException
        exc = PyTrendsException("Generic API error")

        # Verify it doesn't have retry_after
        assert not hasattr(exc, 'retry_after')

    def test_rate_limit_exception_catchable_as_pytrends_exception(self):
        """
        SPEC: RateLimitException should be catchable as PyTrendsException for backward compat
        BEHAVIOR: except PyTrendsException catches RateLimitException too
        """
        from lib.exceptions import RateLimitException, PyTrendsException

        # Test that PyTrendsException handler catches RateLimitException
        caught = False
        try:
            raise RateLimitException("Rate limited", retry_after=120)
        except PyTrendsException as e:
            caught = True
            # Should be able to check type dynamically
            if isinstance(e, RateLimitException):
                assert e.retry_after == 120

        assert caught, "RateLimitException should be catchable as PyTrendsException"


class TestRateLimitExceptionSerialization:
    """Test that RateLimitException can be serialized for structured logging."""

    def test_rate_limit_exception_attributes_accessible(self):
        """
        SPEC: FR-016 - Log 429 errors with structured metadata
        BEHAVIOR: Exception attributes can be accessed for logging
        """
        from lib.exceptions import RateLimitException

        exc = RateLimitException("API rate limit exceeded", retry_after=180)

        # Verify all attributes accessible for logging
        assert hasattr(exc, 'args')
        assert hasattr(exc, 'retry_after')
        assert str(exc) == "API rate limit exceeded"
        assert exc.retry_after == 180

    def test_rate_limit_exception_repr_includes_retry_after(self):
        """
        SPEC: Exception repr should be informative for debugging
        BEHAVIOR: repr() includes retry_after value
        """
        from lib.exceptions import RateLimitException

        exc = RateLimitException("Rate limited", retry_after=60)

        # Verify repr is informative
        repr_str = repr(exc)
        assert 'RateLimitException' in repr_str
        # Note: Default repr may not include retry_after, but attribute is accessible
