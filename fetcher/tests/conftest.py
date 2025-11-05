"""
Pytest Configuration and Shared Fixtures

Provides shared fixtures for all test files, particularly database setup.
Per Constitution Principle III: TDD - Proper test infrastructure.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
import sys

# Add src to path for all tests
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lib.db import init_database, DatabaseConnection


@pytest.fixture
def test_db():
    """
    Create temporary test database path with schema applied.

    This fixture is shared across all test files and provides a clean
    database for each test that needs it.

    Yields:
        str: Path to temporary database file
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    # Apply schema - init_database closes init connection internally
    schema_path = Path(__file__).parent.parent / "schema.sql"
    db = init_database(str(schema_path), db_path)
    db.close()  # Close the fresh instance (hasn't been used yet)

    yield db_path

    # Cleanup: delete file
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def test_db_instance(test_db):
    """
    Provide DatabaseConnection instance for test database.

    Args:
        test_db: Path to test database (from test_db fixture)

    Yields:
        DatabaseConnection: Database connection wrapper
    """
    db = DatabaseConnection(test_db)
    yield db
    db.close()


@pytest.fixture
def test_db_connection(test_db):
    """
    Provide SQLite connection to test database.

    Args:
        test_db: Path to test database (from test_db fixture)

    Yields:
        sqlite3.Connection: Raw SQLite connection
    """
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def test_db_ops(test_db_instance):
    """
    Provide DBOperations instance for test database.

    Args:
        test_db_instance: DatabaseConnection instance (from test_db_instance fixture)

    Yields:
        DBOperations: Database operations wrapper
    """
    from lib.db_operations import DBOperations
    yield DBOperations(test_db_instance)
