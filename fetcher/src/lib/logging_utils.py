"""
Structured JSON Logger Module

Per research.md Decision 7: Structured JSON logging for operational monitoring.

Constitution alignment:
- Principle VIII: Observability & Data Health - Structured logs with batch metadata
"""

import logging
import sys
from typing import Any, Dict, Optional
from pythonjsonlogger.json import JsonFormatter


class CustomJsonFormatter(JsonFormatter):
    """
    Custom JSON formatter with additional fields.

    Adds service name and ensures consistent timestamp format.
    """

    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)

        # Add service identifier
        log_record['service'] = 'googili-fetcher'

        # Add log level
        log_record['level'] = record.levelname

        # Rename 'message' to 'msg' for consistency
        if 'message' in log_record:
            log_record['msg'] = log_record.pop('message')


def setup_logger(
    name: str = 'fetcher',
    level: str = 'INFO',
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Setup structured JSON logger.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs (in addition to stdout)

    Returns:
        logging.Logger: Configured logger instance

    Example:
        logger = setup_logger('fetcher', 'INFO')
        logger.info('Daily ingestion started', extra={
            'batch_id': 'batch_20251104_073215',
            'keywords': ['ไข้', 'ไอ'],
            'window': '2025-11-03 to 2025-11-04'
        })
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper()))
    logger.propagate = False

    # JSON formatter
    formatter = CustomJsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def log_batch_event(
    logger: logging.Logger,
    level: str,
    message: str,
    batch_id: Optional[str] = None,
    keywords: Optional[list] = None,
    rows_written: Optional[int] = None,
    status: Optional[str] = None,
    **extra_fields
) -> None:
    """
    Log batch event with structured metadata.

    Args:
        logger: Logger instance
        level: Log level (info, warning, error)
        message: Log message
        batch_id: Batch identifier
        keywords: List of keywords processed
        rows_written: Number of RSV records written
        status: Batch status (success, degraded, fail)
        **extra_fields: Additional fields to include in log

    Raises:
        ValueError: If level is invalid
    """
    # Fix 6: Validate log level
    valid_levels = ['debug', 'info', 'warning', 'error', 'critical']
    if level.lower() not in valid_levels:
        raise ValueError(f"Invalid log level: {level}. Must be one of {valid_levels}")

    extra = {}
    if batch_id:
        extra['batch_id'] = batch_id
    if keywords:
        extra['keywords'] = keywords
    if rows_written is not None:
        extra['rows_written'] = rows_written
    if status:
        extra['status'] = status

    extra.update(extra_fields)

    try:
        log_method = getattr(logger, level.lower())
        log_method(message, extra=extra)
    except Exception as e:
        # Fallback to error logging if primary logging fails
        logger.error(f"Failed to log batch event: {e}", extra={'original_message': message})


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> None:
    """
    Setup root logger with structured JSON formatting.

    Args:
        level: Logging level (logging.INFO, logging.DEBUG, etc.)
        log_file: Optional file path to write logs

    This is an alias for configuring the root logger.
    Used by CLI entry point (main.py).
    """
    # Get root logger
    root_logger = logging.getLogger()

    # Prevent duplicate handlers if called multiple times
    if root_logger.handlers:
        root_logger.setLevel(level)
        return

    root_logger.setLevel(level)
    root_logger.propagate = False

    # JSON formatter
    formatter = CustomJsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
