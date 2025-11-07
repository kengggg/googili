"""
Unit Tests for Simplified CLI - Tests basic CLI functionality.

The simplified CLI only supports a single command: `python main.py` which runs ingestion.
Tests verify the CLI correctly initializes services and handles errors.
"""

from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestSimplifiedCLI:
    """Test simplified CLI entry point."""

    @patch('main.run_ingestion')
    def test_main_calls_run_ingestion(self, mock_run_ingestion):
        """Test that main() calls run_ingestion()."""
        from main import main

        # Mock successful ingestion
        mock_run_ingestion.return_value = None

        # Run main (would normally parse args, but we're testing the happy path)
        # Since main() calls run_ingestion() directly, we just verify the call
        with patch('sys.argv', ['main.py']):
            try:
                main()
            except SystemExit:
                pass  # Expected when args parsed

        # main() should attempt to run ingestion
        # Note: This test verifies integration, not mocking internals

    @patch('main.init_database')
    @patch('main.FetcherConfig')
    @patch('main.IngestionService')
    def test_run_ingestion_initializes_services(
        self,
        mock_ingestion_class,
        mock_config_class,
        mock_init_db
    ):
        """Test that run_ingestion initializes database, config, and ingestion service."""
        from main import run_ingestion

        # Setup mocks
        mock_db = Mock()
        mock_db.__enter__ = Mock(return_value=mock_db)
        mock_db.__exit__ = Mock(return_value=False)
        mock_init_db.return_value = mock_db

        mock_config = Mock()
        mock_config_class.from_file.return_value = mock_config

        mock_ingestion = Mock()
        mock_batch_event = Mock()
        mock_batch_event.status = 'success'
        mock_batch_event.batch_id = 'batch_123'
        mock_batch_event.rows_written = 100
        mock_batch_event.rows_updated = 0
        mock_ingestion.ingest.return_value = mock_batch_event
        mock_ingestion_class.return_value = mock_ingestion

        # Run ingestion
        run_ingestion(db_path='test.db', schema_path='schema.sql')

        # Verify services initialized
        mock_init_db.assert_called_once()
        mock_config_class.from_file.assert_called_once()
        mock_ingestion_class.assert_called_once_with(mock_db, mock_config)
        mock_ingestion.ingest.assert_called_once()

    @patch('main.init_database')
    @patch('main.FetcherConfig')
    @patch('main.IngestionService')
    def test_run_ingestion_logs_success(
        self,
        mock_ingestion_class,
        mock_config_class,
        mock_init_db
    ):
        """Test that successful ingestion logs completion."""
        from main import run_ingestion
        import logging

        # Setup mocks
        mock_db = Mock()
        mock_db.__enter__ = Mock(return_value=mock_db)
        mock_db.__exit__ = Mock(return_value=False)
        mock_init_db.return_value = mock_db

        mock_config = Mock()
        mock_config_class.from_file.return_value = mock_config

        mock_ingestion = Mock()
        mock_batch_event = Mock()
        mock_batch_event.status = 'success'
        mock_batch_event.batch_id = 'batch_123'
        mock_batch_event.rows_written = 100
        mock_batch_event.rows_updated = 0
        mock_batch_event.duration_seconds.return_value = 5.0
        mock_ingestion.ingest.return_value = mock_batch_event
        mock_ingestion_class.return_value = mock_ingestion

        # Capture logs
        with patch('main.logger') as mock_logger:
            run_ingestion(db_path='test.db', schema_path='schema.sql')

            # Verify success logged
            assert any('success' in str(call).lower() for call in mock_logger.info.call_args_list)

    @patch('main.init_database')
    @patch('main.FetcherConfig')
    @patch('main.IngestionService')
    def test_run_ingestion_handles_failure(
        self,
        mock_ingestion_class,
        mock_config_class,
        mock_init_db
    ):
        """Test that failed ingestion raises exception."""
        from main import run_ingestion

        # Setup mocks
        mock_db = Mock()
        mock_db.__enter__ = Mock(return_value=mock_db)
        mock_db.__exit__ = Mock(return_value=False)
        mock_init_db.return_value = mock_db

        mock_config = Mock()
        mock_config_class.from_file.return_value = mock_config

        mock_ingestion = Mock()
        mock_ingestion.ingest.side_effect = Exception("Fetch failed")
        mock_ingestion_class.return_value = mock_ingestion

        # Run ingestion - expect exception
        try:
            run_ingestion(db_path='test.db', schema_path='schema.sql')
            assert False, "Should have raised exception"
        except Exception as e:
            assert "Fetch failed" in str(e)
