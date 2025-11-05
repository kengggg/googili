"""
Unit Tests for Structured JSON Logger Module - SPEC-DRIVEN BEHAVIORAL TESTS

Tests ACTUAL logging behavior per spec requirements:
- Structured JSON output format
- Batch event metadata logging
- Log levels and filtering
- Thai Unicode support in logs
- File and console output handling

Constitution alignment:
- Principle III: TDD - Tests written FIRST, validate BEHAVIOR not implementation
- Principle VIII: Observability - Structured logging with batch metadata

Spec references:
- plan.md: "Structured JSON logging (python-json-logger, batch metadata support)"
- research.md Decision 7: "Structured JSON logging for operational monitoring"
"""

import pytest
import logging
import json
import tempfile
from pathlib import Path
from io import StringIO

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lib.logging_utils import setup_logger, log_batch_event, setup_logging, CustomJsonFormatter


class TestLoggerSetup:
    """Test that setup_logger ACTUALLY creates configured logger."""

    def test_creates_logger_with_specified_name(self):
        """
        SPEC: System must provide named loggers
        BEHAVIOR: setup_logger ACTUALLY creates logger with specified name
        """
        logger = setup_logger(name='test_logger')

        assert logger.name == 'test_logger'
        assert isinstance(logger, logging.Logger)

    def test_sets_log_level_correctly(self):
        """
        SPEC: System must support different log levels
        BEHAVIOR: setup_logger ACTUALLY sets specified log level
        """
        logger_info = setup_logger(name='logger_info', level='INFO')
        logger_debug = setup_logger(name='logger_debug', level='DEBUG')
        logger_warning = setup_logger(name='logger_warning', level='WARNING')

        assert logger_info.level == logging.INFO
        assert logger_debug.level == logging.DEBUG
        assert logger_warning.level == logging.WARNING

    def test_prevents_duplicate_handlers(self):
        """
        SPEC: System must not leak resources
        BEHAVIOR: Calling setup_logger multiple times ACTUALLY reuses logger
        """
        logger1 = setup_logger(name='reused_logger')
        initial_handlers = len(logger1.handlers)

        logger2 = setup_logger(name='reused_logger')
        final_handlers = len(logger2.handlers)

        # Should not add duplicate handlers
        assert final_handlers == initial_handlers
        assert logger1 is logger2  # Same logger instance

    def test_creates_file_handler_when_log_file_specified(self):
        """
        SPEC: System must support file logging
        BEHAVIOR: setup_logger ACTUALLY creates file handler when log_file provided
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as tmp:
            log_file = tmp.name

        logger = setup_logger(name='file_logger', log_file=log_file)

        # Verify file handler ACTUALLY created
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0, "File handler not created"

        # Cleanup
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()
        Path(log_file).unlink(missing_ok=True)


class TestJsonFormatting:
    """Test that CustomJsonFormatter ACTUALLY produces valid JSON output."""

    def test_log_output_is_valid_json(self):
        """
        SPEC: Structured JSON logging
        BEHAVIOR: Log output ACTUALLY valid JSON
        """
        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('json_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Log message
        logger.info('Test message')

        # Verify output is ACTUALLY valid JSON
        output = stream.getvalue().strip()
        parsed = json.loads(output)  # Should not raise exception

        assert isinstance(parsed, dict)
        assert 'msg' in parsed  # Custom field name

        # Cleanup
        logger.handlers.clear()

    def test_json_includes_service_field(self):
        """
        SPEC: Logs must identify service
        BEHAVIOR: JSON output ACTUALLY includes 'service' field
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('service_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info('Test message')

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert 'service' in parsed
        assert parsed['service'] == 'googili-fetcher'

        logger.handlers.clear()

    def test_json_includes_level_field(self):
        """
        SPEC: Logs must include severity level
        BEHAVIOR: JSON output ACTUALLY includes 'level' field
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('level_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.warning('Warning message')

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert 'level' in parsed
        assert parsed['level'] == 'WARNING'

        logger.handlers.clear()

    def test_json_renames_message_to_msg(self):
        """
        SPEC: Consistent field naming
        BEHAVIOR: JSON formatter ACTUALLY renames 'message' to 'msg'
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('msg_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info('Test message')

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        # Should use 'msg' not 'message'
        assert 'msg' in parsed
        assert 'message' not in parsed
        assert parsed['msg'] == 'Test message'

        logger.handlers.clear()


class TestThaiUnicodeSupport:
    """Test that logging ACTUALLY handles Thai Unicode characters correctly."""

    def test_logs_thai_keywords_correctly(self):
        """
        SPEC: System must handle Thai language keywords
        BEHAVIOR: Logger ACTUALLY preserves Thai Unicode characters
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('thai_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Log message with Thai Unicode
        thai_keywords = ['ไข้หวัดนก', 'ไอ', 'หวัด', 'อุจจาระร่วง']
        logger.info('Thai keywords test', extra={'keywords': thai_keywords})

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        # Verify Thai text ACTUALLY preserved
        assert 'keywords' in parsed
        assert 'ไข้หวัดนก' in parsed['keywords']
        assert 'ไอ' in parsed['keywords']
        assert 'หวัด' in parsed['keywords']

        logger.handlers.clear()

    def test_batch_event_with_thai_keyword_names(self):
        """
        SPEC: Batch events must support Thai keywords
        BEHAVIOR: log_batch_event ACTUALLY handles Thai Unicode in metadata
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('thai_batch_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Log batch event with Thai keywords
        log_batch_event(
            logger,
            'info',
            'Batch processing complete',
            batch_id='batch_123',
            keywords=['ไข้หวัดนก', 'ไอ'],
            status='success'
        )

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        # Verify Thai keywords ACTUALLY in output
        assert 'keywords' in parsed
        assert 'ไข้หวัดนก' in parsed['keywords']

        logger.handlers.clear()


class TestBatchEventLogging:
    """Test that log_batch_event ACTUALLY logs batch metadata correctly."""

    def test_logs_batch_id_in_metadata(self):
        """
        SPEC: Batch events must include batch_id
        BEHAVIOR: log_batch_event ACTUALLY includes batch_id in JSON
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('batch_id_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        log_batch_event(
            logger,
            'info',
            'Test batch event',
            batch_id='batch_20251104_073215'
        )

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert 'batch_id' in parsed
        assert parsed['batch_id'] == 'batch_20251104_073215'

        logger.handlers.clear()

    def test_logs_keywords_in_metadata(self):
        """
        SPEC: Batch events must include keywords processed
        BEHAVIOR: log_batch_event ACTUALLY includes keywords in JSON
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('keywords_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        log_batch_event(
            logger,
            'info',
            'Test batch event',
            keywords=['ไข้', 'ไอ', 'หวัด']
        )

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert 'keywords' in parsed
        assert parsed['keywords'] == ['ไข้', 'ไอ', 'หวัด']

        logger.handlers.clear()

    def test_logs_rows_written_in_metadata(self):
        """
        SPEC: Batch events must include row counts
        BEHAVIOR: log_batch_event ACTUALLY includes rows_written in JSON
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('rows_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        log_batch_event(
            logger,
            'info',
            'Test batch event',
            rows_written=42
        )

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert 'rows_written' in parsed
        assert parsed['rows_written'] == 42

        logger.handlers.clear()

    def test_logs_status_in_metadata(self):
        """
        SPEC: Batch events must include status
        BEHAVIOR: log_batch_event ACTUALLY includes status in JSON
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('status_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        log_batch_event(
            logger,
            'info',
            'Test batch event',
            status='success'
        )

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert 'status' in parsed
        assert parsed['status'] == 'success'

        logger.handlers.clear()

    def test_logs_extra_fields_in_metadata(self):
        """
        SPEC: Batch events must support extensible metadata
        BEHAVIOR: log_batch_event ACTUALLY includes **extra_fields in JSON
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('extra_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        log_batch_event(
            logger,
            'info',
            'Test batch event',
            duration_seconds=5.2,
            rows_updated=3,
            custom_field='custom_value'
        )

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert 'duration_seconds' in parsed
        assert parsed['duration_seconds'] == 5.2
        assert 'rows_updated' in parsed
        assert parsed['rows_updated'] == 3
        assert 'custom_field' in parsed
        assert parsed['custom_field'] == 'custom_value'

        logger.handlers.clear()

    def test_raises_error_for_invalid_log_level(self):
        """
        SPEC: System must validate inputs
        BEHAVIOR: log_batch_event ACTUALLY raises ValueError for invalid level
        """
        logger = logging.getLogger('invalid_level_test')

        with pytest.raises(ValueError) as exc_info:
            log_batch_event(
                logger,
                'invalid_level',  # Not a valid log level
                'Test message'
            )

        assert 'invalid log level' in str(exc_info.value).lower()


class TestLogLevelFiltering:
    """Test that log levels ACTUALLY filter messages correctly."""

    def test_info_logger_does_not_log_debug_messages(self):
        """
        SPEC: Log level filtering must work correctly
        BEHAVIOR: Logger at INFO level ACTUALLY filters out DEBUG messages
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('filter_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Try to log DEBUG (should be filtered)
        logger.debug('Debug message')

        output = stream.getvalue()
        assert output == '', "DEBUG message not filtered by INFO logger"

        logger.handlers.clear()

    def test_info_logger_logs_info_messages(self):
        """
        SPEC: Log level filtering must work correctly
        BEHAVIOR: Logger at INFO level ACTUALLY logs INFO messages
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('info_test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info('Info message')

        output = stream.getvalue().strip()
        assert len(output) > 0, "INFO message not logged"

        parsed = json.loads(output)
        assert parsed['level'] == 'INFO'

        logger.handlers.clear()

    def test_warning_logger_logs_error_messages(self):
        """
        SPEC: Log level filtering must work correctly
        BEHAVIOR: Logger at WARNING level ACTUALLY logs ERROR messages
        """
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger('warning_test')
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

        logger.error('Error message')

        output = stream.getvalue().strip()
        assert len(output) > 0, "ERROR message not logged"

        parsed = json.loads(output)
        assert parsed['level'] == 'ERROR'

        logger.handlers.clear()


class TestFileLogging:
    """Test that file logging ACTUALLY writes to files."""

    def test_writes_logs_to_file(self):
        """
        SPEC: System must support file logging
        BEHAVIOR: setup_logger ACTUALLY writes logs to specified file
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as tmp:
            log_file = tmp.name

        logger = setup_logger(name='file_write_test', log_file=log_file)
        logger.info('Test file logging')

        # Force flush
        for handler in logger.handlers:
            handler.flush()

        # Verify file ACTUALLY contains log
        log_content = Path(log_file).read_text()
        assert len(log_content) > 0, "No content written to log file"
        assert 'Test file logging' in log_content

        # Cleanup
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()
        Path(log_file).unlink(missing_ok=True)

    def test_file_logs_are_valid_json(self):
        """
        SPEC: File logs must use same JSON format
        BEHAVIOR: File logs ACTUALLY valid JSON
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as tmp:
            log_file = tmp.name

        logger = setup_logger(name='file_json_test', log_file=log_file)
        logger.info('Test JSON file logging', extra={'batch_id': 'batch_123'})

        # Force flush
        for handler in logger.handlers:
            handler.flush()

        # Read and parse log file
        log_content = Path(log_file).read_text().strip()
        parsed = json.loads(log_content)  # Should not raise exception

        assert 'msg' in parsed
        assert 'batch_id' in parsed
        assert parsed['batch_id'] == 'batch_123'

        # Cleanup
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()
        Path(log_file).unlink(missing_ok=True)


class TestRootLoggerSetup:
    """Test that setup_logging ACTUALLY configures root logger."""

    def test_configures_root_logger(self):
        """
        SPEC: System must provide root logger configuration
        BEHAVIOR: setup_logging ACTUALLY configures root logger
        """
        # Clear existing handlers
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(level=logging.INFO)

        # Verify root logger ACTUALLY configured
        assert len(root.handlers) > 0
        assert root.level == logging.INFO

        # Cleanup
        root.handlers.clear()

    def test_root_logger_uses_json_formatter(self):
        """
        SPEC: Root logger must use structured JSON format
        BEHAVIOR: setup_logging ACTUALLY applies JSON formatter
        """
        # Clear existing handlers
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(level=logging.INFO)

        # Verify JSON formatter ACTUALLY applied
        for handler in root.handlers:
            assert isinstance(handler.formatter, CustomJsonFormatter)

        # Cleanup
        root.handlers.clear()

    def test_prevents_duplicate_root_handlers(self):
        """
        SPEC: System must not leak resources
        BEHAVIOR: Calling setup_logging multiple times ACTUALLY prevents duplicates
        """
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(level=logging.INFO)
        initial_count = len(root.handlers)

        setup_logging(level=logging.DEBUG)
        final_count = len(root.handlers)

        # Should not add duplicate handlers
        assert final_count == initial_count

        # Cleanup
        root.handlers.clear()
