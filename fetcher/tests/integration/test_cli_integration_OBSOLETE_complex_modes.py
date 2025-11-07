"""
Integration Tests for CLI Entry Points - NO OVER-MOCKING

These tests verify that CLI commands actually work end-to-end with minimal mocking.
They would have caught the IngestionService signature bug that unit tests missed.

Constitution alignment:
- Principle III: TDD - Integration tests prevent over-mocking bugs
- Case Study: The Over-Mocking Bug (2025-11-05) - Documented lesson learned

CRITICAL: Only mock EXTERNAL dependencies (Google Trends API), NOT our own classes!
"""

import pytest
import tempfile
import subprocess
import sys
from pathlib import Path
from datetime import date
from unittest.mock import patch, Mock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from main import run_manual, run_daily
from lib.db import DatabaseConnection
from lib.config import FetcherConfig
from services.ingestion import IngestionService


class TestCLIIntegrationWithoutOverMocking:
    """
    Integration tests that catch signature bugs by NOT mocking our own classes.
    These tests would have caught the IngestionService(db) missing config parameter.
    """

    @patch('services.ingestion.TrendsFetcher')  # Mock EXTERNAL dependency only
    def test_run_manual_integration_without_mocking_our_classes(self, mock_trends_class):
        """
        INTEGRATION TEST: Verify run_manual actually works with real IngestionService

        This test does NOT mock IngestionService (our code), only TrendsFetcher (external).
        If IngestionService signature is wrong, this test FAILS immediately.
        """
        # Setup: Mock only external Google Trends API
        mock_trends = Mock()
        mock_trends.fetch_with_batching.return_value = []  # Empty results OK for signature test
        mock_trends_class.return_value = mock_trends

        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = tmp_db.name

        try:
            # Execute: Run REAL code with REAL classes
            # This will FAIL if IngestionService signature is wrong
            exit_code = run_manual(db_path, 'schema.sql', '2025-11-01')

            # Verify: Integration succeeded
            assert exit_code == 0, "Manual ingestion should succeed"

        finally:
            # Cleanup
            Path(db_path).unlink(missing_ok=True)

    @patch('services.ingestion.TrendsFetcher')  # Mock EXTERNAL dependency only
    def test_run_daily_integration_without_mocking_our_classes(self, mock_trends_class):
        """
        INTEGRATION TEST: Verify run_daily actually works with real IngestionService

        This test does NOT mock IngestionService (our code), only TrendsFetcher (external).
        If IngestionService signature is wrong, this test FAILS immediately.
        """
        # Setup: Mock only external Google Trends API
        mock_trends = Mock()
        mock_trends.fetch_with_batching.return_value = []  # Empty results OK for signature test
        mock_trends_class.return_value = mock_trends

        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = tmp_db.name

        try:
            # Execute: Run REAL code with REAL classes
            # This will FAIL if IngestionService signature is wrong
            exit_code = run_daily(db_path, 'schema.sql')

            # Verify: Integration succeeded
            assert exit_code == 0, "Daily ingestion should succeed"

        finally:
            # Cleanup
            Path(db_path).unlink(missing_ok=True)

    def test_ingestion_service_signature_requires_config(self):
        """
        CONTRACT TEST: Verify IngestionService requires config parameter

        This simple test enforces the signature contract.
        If anyone changes IngestionService to not require config, this fails.
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = tmp_db.name

        try:
            db = DatabaseConnection(db_path)
            config = FetcherConfig()

            # This should work with correct signature
            ingestion = IngestionService(db, config)
            assert ingestion is not None

            # This should FAIL - missing config parameter
            with pytest.raises(TypeError, match="missing.*required.*positional argument.*config"):
                IngestionService(db)  # Wrong signature!

        finally:
            Path(db_path).unlink(missing_ok=True)


class TestCLISubprocessIntegration:
    """
    Subprocess integration tests - ultimate verification that CLI actually works.
    These run the actual CLI command via subprocess, no Python mocking at all.
    """

    @pytest.mark.slow
    @patch('services.trends_fetcher.TrendsFetcher')  # Mock at module level
    def test_cli_manual_command_actually_runs(self, mock_trends_class):
        """
        SUBPROCESS TEST: Verify CLI command actually works when run from shell

        This is the ultimate integration test - runs actual command as user would.
        No Python mocking possible at this level.
        """
        # Setup: Mock trends at import time
        mock_trends = Mock()
        mock_trends.fetch_daily.return_value = []
        mock_trends_class.return_value = mock_trends

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = tmp_db.name

        try:
            # Execute: Run ACTUAL CLI command via subprocess
            result = subprocess.run(
                [
                    sys.executable, 'main.py',
                    '--manual', '--date', '2025-11-01',
                    '--db', db_path,
                    '--log-level', 'ERROR'  # Suppress logs
                ],
                cwd=Path(__file__).parent.parent.parent,
                capture_output=True,
                text=True,
                timeout=30
            )

            # This will show the actual TypeError if signature is wrong
            if result.returncode != 0:
                pytest.fail(f"CLI failed with exit code {result.returncode}\n"
                          f"STDERR: {result.stderr}\n"
                          f"STDOUT: {result.stdout}")

            # Verify: CLI succeeded
            assert result.returncode == 0

        finally:
            # Cleanup
            Path(db_path).unlink(missing_ok=True)
