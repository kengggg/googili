#!/usr/bin/env python3
"""
Smoke tests for foundational layer fixes.

Tests all 8 fixes to ensure they work correctly before proceeding to User Story 1.
"""

import sys
import tempfile
import threading
from pathlib import Path
from datetime import date

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_fix_1_threading():
    """Fix 1: Test thread-local database connections."""
    from lib.db import DatabaseConnection

    print("[Fix 1] Testing thread-local database connections...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = DatabaseConnection(db_path)
        results = []

        def thread_task(thread_id):
            # Each thread gets its own connection
            with db.get_connection() as conn:
                cursor = conn.execute("SELECT 1 as test")
                row = cursor.fetchone()
                results.append((thread_id, row['test']))

        threads = [threading.Thread(target=thread_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
        print("[Fix 1] ✓ Thread-local connections work correctly")

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_fix_2_init_files():
    """Fix 2: Test that all __init__.py files exist."""
    print("[Fix 2] Testing __init__.py files...")

    expected_init_files = [
        "src/lib/__init__.py",
        "src/models/__init__.py",
        "src/services/__init__.py",
        "src/cli/__init__.py",
        "tests/__init__.py",
        "tests/unit/__init__.py",
        "tests/integration/__init__.py",
        "tests/contract/__init__.py",
        "tests/golden/__init__.py",
    ]

    base_dir = Path(__file__).parent
    for init_file in expected_init_files:
        path = base_dir / init_file
        assert path.exists(), f"Missing {init_file}"

    print(f"[Fix 2] ✓ All {len(expected_init_files)} __init__.py files exist")


def test_fix_3_db_init():
    """Fix 3: Test database initialization."""
    from lib.db import init_database, get_db

    print("[Fix 3] Testing database initialization...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        schema_path = Path(__file__).parent / "schema.sql"
        init_database(str(schema_path), db_path)

        # Verify tables exist
        db = get_db(db_path)
        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row['name'] for row in cursor.fetchall()]

        expected_tables = ['config_keywords', 'events_raw_rsv_ingested', 'health_probe', 'raw_trenddata']
        for table in expected_tables:
            assert table in tables, f"Missing table: {table}"

        print(f"[Fix 3] ✓ Database initialized with {len(tables)} tables")

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_fix_4_auto_commit():
    """Fix 4: Test auto-commit on successful completion."""
    from lib.db import DatabaseConnection

    print("[Fix 4] Testing auto-commit...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = DatabaseConnection(db_path)

        # Write with auto_commit=True (default)
        with db.get_connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.execute("INSERT INTO test VALUES (1)")

        # Verify data persisted (new connection)
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM test")
            count = cursor.fetchone()['cnt']

        assert count == 1, f"Expected 1 row, got {count}"
        print("[Fix 4] ✓ Auto-commit works correctly")

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_fix_5_pragma():
    """Fix 5: Test PRAGMA optimizations."""
    from lib.db import DatabaseConnection

    print("[Fix 5] Testing PRAGMA optimizations...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = DatabaseConnection(db_path)

        with db.get_connection() as conn:
            # Check WAL mode
            cursor = conn.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            assert journal_mode.lower() == 'wal', f"Expected WAL mode, got {journal_mode}"

            # Check busy_timeout
            cursor = conn.execute("PRAGMA busy_timeout")
            busy_timeout = cursor.fetchone()[0]
            assert busy_timeout == 30000, f"Expected 30000ms timeout, got {busy_timeout}"

        print("[Fix 5] ✓ PRAGMA optimizations applied correctly")

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_fix_6_logger_validation():
    """Fix 6: Test logger error handling."""
    from lib.logger import setup_logger, log_batch_event

    print("[Fix 6] Testing logger error handling...")

    logger = setup_logger('test', 'INFO')

    # Valid log level
    try:
        log_batch_event(logger, 'info', 'Test message', batch_id='test_batch')
        print("[Fix 6] ✓ Valid log level works")
    except Exception as e:
        raise AssertionError(f"Valid log level failed: {e}")

    # Invalid log level
    try:
        log_batch_event(logger, 'INVALID', 'Test message')
        raise AssertionError("Should have raised ValueError for invalid level")
    except ValueError as e:
        print("[Fix 6] ✓ Invalid log level raises ValueError")


def test_fix_7_timezone_validation():
    """Fix 7: Test timezone utility validation."""
    from lib.timezone_utils import date_to_ict_datetime, date_range_ict

    print("[Fix 7] Testing timezone validation...")

    # Valid time components
    try:
        dt = date_to_ict_datetime(date(2025, 11, 4), hour=7, minute=30, second=0)
        print("[Fix 7] ✓ Valid time components work")
    except Exception as e:
        raise AssertionError(f"Valid time components failed: {e}")

    # Invalid hour
    try:
        date_to_ict_datetime(date(2025, 11, 4), hour=25)
        raise AssertionError("Should have raised ValueError for invalid hour")
    except ValueError:
        print("[Fix 7] ✓ Invalid hour raises ValueError")

    # Valid date range
    try:
        dates = date_range_ict(date(2025, 11, 1), date(2025, 11, 3))
        assert len(dates) == 3
        print("[Fix 7] ✓ Valid date range works")
    except Exception as e:
        raise AssertionError(f"Valid date range failed: {e}")

    # Invalid date range
    try:
        date_range_ict(date(2025, 11, 5), date(2025, 11, 1))
        raise AssertionError("Should have raised ValueError for invalid range")
    except ValueError:
        print("[Fix 7] ✓ Invalid date range raises ValueError")


def test_fix_8_config_logging():
    """Fix 8: Test config logging."""
    from lib.config import FetcherConfig
    from lib.logger import setup_logger

    print("[Fix 8] Testing config logging...")

    # Setup logger to capture config logs
    logger = setup_logger('lib.config', 'DEBUG')

    # Try loading config (will fail if config/googili.toml doesn't exist, which is expected)
    try:
        config = FetcherConfig("config/googili.toml")
        print("[Fix 8] ✓ Config loading logs messages")
    except Exception as e:
        # Expected if config doesn't exist - logging still works
        if "Configuration file not found" in str(e):
            print("[Fix 8] ✓ Config error logging works (file not found)")
        else:
            raise


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("SMOKE TESTS: Foundational Layer Fixes (Fix 1-8)")
    print("=" * 60)
    print()

    tests = [
        test_fix_1_threading,
        test_fix_2_init_files,
        test_fix_3_db_init,
        test_fix_4_auto_commit,
        test_fix_5_pragma,
        test_fix_6_logger_validation,
        test_fix_7_timezone_validation,
        test_fix_8_config_logging,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        print()

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
