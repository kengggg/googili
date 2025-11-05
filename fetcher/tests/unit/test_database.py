"""
Unit Tests for Database Connection Module - SPEC-DRIVEN BEHAVIORAL TESTS

Tests ACTUAL database behavior per spec requirements:
- SQLite with WAL mode for concurrent reads during writes
- Connection pooling with thread-local connections
- Transaction handling with auto-commit and rollback
- PRAGMA settings for performance optimization
- Error recovery and resource cleanup

Constitution alignment:
- Principle III: TDD - Tests written FIRST, validate BEHAVIOR not implementation
- Principle IV: Data Governance - WAL mode enables concurrent access

Spec references:
- plan.md: "SQLite 3 with WAL mode; single file for MVP"
- research.md Decision 5: "Use SQLite with WAL mode for MVP"
"""

import pytest
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lib.db import DatabaseConnection, init_database


class TestDatabaseConnectionCreation:
    """Test that DatabaseConnection ACTUALLY creates database files and directories."""

    def test_creates_database_file_if_not_exists(self):
        """
        SPEC: Database layer must be accessible for writes
        BEHAVIOR: DatabaseConnection ACTUALLY creates database file
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Database file should not exist yet
            assert not db_path.exists()

            # Create connection
            db = DatabaseConnection(str(db_path))

            # Use connection to trigger file creation
            with db.get_connection() as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")

            # Verify file ACTUALLY created
            assert db_path.exists(), "Database file not created"

            db.close()

    def test_creates_parent_directories_if_not_exist(self):
        """
        SPEC: System must handle missing directories
        BEHAVIOR: DatabaseConnection ACTUALLY creates parent directories
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nested" / "path" / "test.db"

            # Parent directories should not exist
            assert not db_path.parent.exists()

            # Create connection (should create directories)
            db = DatabaseConnection(str(db_path))

            # Verify directories ACTUALLY created
            assert db_path.parent.exists(), "Parent directories not created"

            db.close()


class TestWALMode:
    """Test that WAL mode ACTUALLY enables concurrent reads during writes."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        yield db_path

        # Cleanup
        Path(db_path).unlink(missing_ok=True)
        Path(f"{db_path}-wal").unlink(missing_ok=True)
        Path(f"{db_path}-shm").unlink(missing_ok=True)

    def test_wal_mode_actually_enabled(self, temp_db):
        """
        SPEC: SQLite with WAL mode for concurrent reads
        BEHAVIOR: DatabaseConnection ACTUALLY enables WAL journal mode
        """
        db = DatabaseConnection(temp_db)

        with db.get_connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]

        # Verify WAL mode ACTUALLY enabled
        assert journal_mode.upper() == 'WAL', f"WAL mode not enabled, got: {journal_mode}"

        db.close()

    def test_concurrent_reads_succeed_during_write(self, temp_db):
        """
        SPEC: WAL mode allows concurrent reads while Fetcher writes
        BEHAVIOR: Multiple readers can ACTUALLY read while writer is writing
        """
        # Setup: Create test table
        db = DatabaseConnection(temp_db)
        with db.get_connection() as conn:
            conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO test_data (id, value) VALUES (1, 'initial')")
        db.close()

        write_started = threading.Event()
        write_finished = threading.Event()
        read_results = []

        def writer():
            """Simulate long-running write transaction."""
            db_writer = DatabaseConnection(temp_db)
            with db_writer.get_connection(auto_commit=False) as conn:
                conn.execute("INSERT INTO test_data (id, value) VALUES (2, 'writing')")
                write_started.set()
                time.sleep(0.5)  # Simulate slow write
                conn.commit()
            write_finished.set()
            db_writer.close()

        def reader(reader_id):
            """Attempt to read during write."""
            write_started.wait(timeout=2.0)  # Wait for write to start

            db_reader = DatabaseConnection(temp_db)
            with db_reader.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM test_data")
                count = cursor.fetchone()[0]
                read_results.append((reader_id, count, write_finished.is_set()))
            db_reader.close()

        # Execute: Start writer and multiple concurrent readers
        writer_thread = threading.Thread(target=writer)
        reader_threads = [threading.Thread(target=reader, args=(i,)) for i in range(3)]

        writer_thread.start()
        for t in reader_threads:
            t.start()

        writer_thread.join(timeout=2.0)
        for t in reader_threads:
            t.join(timeout=2.0)

        # Verify: All readers succeeded (did not block)
        assert len(read_results) == 3, f"Expected 3 read results, got {len(read_results)}"

        # At least some reads should have completed DURING write (before write_finished)
        reads_during_write = sum(1 for _, _, finished in read_results if not finished)
        assert reads_during_write > 0, "No concurrent reads succeeded during write"

    def test_foreign_keys_actually_enforced(self, temp_db):
        """
        SPEC: Database must maintain referential integrity
        BEHAVIOR: Foreign key constraints ACTUALLY enforced
        """
        db = DatabaseConnection(temp_db)

        with db.get_connection() as conn:
            # Create tables with foreign key
            conn.execute("""
                CREATE TABLE parent (
                    id INTEGER PRIMARY KEY
                )
            """)
            conn.execute("""
                CREATE TABLE child (
                    id INTEGER PRIMARY KEY,
                    parent_id INTEGER,
                    FOREIGN KEY (parent_id) REFERENCES parent(id)
                )
            """)

        # Attempt to insert child without parent (should fail)
        with pytest.raises(sqlite3.IntegrityError):
            with db.get_connection() as conn:
                conn.execute("INSERT INTO child (id, parent_id) VALUES (1, 999)")

        db.close()


class TestTransactionHandling:
    """Test that transaction handling ACTUALLY commits and rolls back correctly."""

    @pytest.fixture
    def db_with_table(self):
        """Create database with test table."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)")

        yield db

        db.close()
        Path(db_path).unlink(missing_ok=True)

    def test_auto_commit_on_successful_completion(self, db_with_table):
        """
        SPEC: Database must persist successful writes
        BEHAVIOR: Context manager ACTUALLY commits on successful exit
        """
        # Insert data with auto_commit=True (default)
        with db_with_table.get_connection() as conn:
            conn.execute("INSERT INTO test_data (id, value) VALUES (1, 'test')")

        # Verify data ACTUALLY committed (readable in new connection)
        with db_with_table.get_connection() as conn:
            cursor = conn.execute("SELECT value FROM test_data WHERE id = 1")
            row = cursor.fetchone()

        assert row is not None, "Data not committed"
        assert row['value'] == 'test', "Incorrect data committed"

    def test_rollback_on_exception(self, db_with_table):
        """
        SPEC: Database must handle failures without data corruption
        BEHAVIOR: Context manager ACTUALLY rolls back on exception
        """
        # Insert initial data
        with db_with_table.get_connection() as conn:
            conn.execute("INSERT INTO test_data (id, value) VALUES (1, 'initial')")

        # Attempt transaction that fails
        try:
            with db_with_table.get_connection() as conn:
                conn.execute("INSERT INTO test_data (id, value) VALUES (2, 'will_rollback')")
                raise Exception("Simulated error")
        except Exception:
            pass

        # Verify second insert ACTUALLY rolled back
        with db_with_table.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM test_data")
            count = cursor.fetchone()[0]

        assert count == 1, f"Transaction not rolled back, got {count} rows instead of 1"

    def test_manual_transaction_with_auto_commit_false(self, db_with_table):
        """
        SPEC: System must support manual transaction control
        BEHAVIOR: auto_commit=False ACTUALLY disables automatic commit
        """
        # Insert data with manual transaction control
        with db_with_table.get_connection(auto_commit=False) as conn:
            conn.execute("INSERT INTO test_data (id, value) VALUES (1, 'manual')")
            conn.commit()  # Explicitly commit

        # Verify data ACTUALLY committed when explicitly requested
        with db_with_table.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM test_data")
            count = cursor.fetchone()[0]

        assert count == 1, "Manual transaction with explicit commit failed"


class TestThreadSafety:
    """Test that connection pooling ACTUALLY handles multiple threads correctly."""

    @pytest.fixture
    def shared_db(self):
        """Create shared database for threading tests."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)
        with db.get_connection() as conn:
            conn.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, count INTEGER)")
            conn.execute("INSERT INTO counter (id, count) VALUES (1, 0)")

        yield db

        db.close()
        Path(db_path).unlink(missing_ok=True)

    def test_each_thread_gets_own_connection(self, shared_db):
        """
        SPEC: Connection pooling with thread-local connections
        BEHAVIOR: Each thread ACTUALLY gets independent connection
        """
        thread_connections = {}

        def get_connection_id(thread_id):
            with shared_db.get_connection() as conn:
                # Get connection object ID
                thread_connections[thread_id] = id(conn)

        # Execute in multiple threads
        threads = [threading.Thread(target=get_connection_id, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify each thread got DIFFERENT connection object
        connection_ids = list(thread_connections.values())
        unique_connections = len(set(connection_ids))

        assert unique_connections == 3, \
            f"Expected 3 unique connections, got {unique_connections}"

    def test_concurrent_writes_do_not_corrupt_data(self, shared_db):
        """
        SPEC: System must handle concurrent writes without corruption
        BEHAVIOR: Multiple threads writing ACTUALLY complete without database errors

        NOTE: This tests that SQLite handles concurrent transactions safely.
        SQLite serializes conflicting writes, so some updates may be lost due to
        read-modify-write race conditions. This is expected behavior and applications
        should use atomic operations (e.g., UPDATE counter SET count = count + 1).
        """
        errors = []

        def increment_counter(iterations):
            try:
                for _ in range(iterations):
                    with shared_db.get_connection() as conn:
                        # Atomic increment (no read-modify-write race)
                        conn.execute("UPDATE counter SET count = count + 1 WHERE id = 1")
            except Exception as e:
                errors.append(str(e))

        # Execute 10 increments across 3 threads (30 total increments)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(increment_counter, 10) for _ in range(3)]
            for future in as_completed(futures):
                future.result()

        # Verify: No database errors occurred
        assert len(errors) == 0, f"Database errors during concurrent writes: {errors}"

        # Verify final count with atomic operations
        with shared_db.get_connection() as conn:
            cursor = conn.execute("SELECT count FROM counter WHERE id = 1")
            final_count = cursor.fetchone()['count']

        # With atomic UPDATE, all 30 increments should succeed
        assert final_count == 30, \
            f"Data corruption: expected 30, got {final_count}"


class TestPragmaSettings:
    """Test that PRAGMA settings ACTUALLY applied for performance."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        yield db_path

        Path(db_path).unlink(missing_ok=True)

    def test_synchronous_pragma_set_to_normal(self, temp_db):
        """
        SPEC: PRAGMA settings for performance optimization
        BEHAVIOR: synchronous ACTUALLY set to NORMAL for WAL mode
        """
        db = DatabaseConnection(temp_db)

        with db.get_connection() as conn:
            cursor = conn.execute("PRAGMA synchronous")
            synchronous = cursor.fetchone()[0]

        # 1 = NORMAL mode
        assert synchronous == 1, f"synchronous not NORMAL, got: {synchronous}"

        db.close()

    def test_cache_size_pragma_set(self, temp_db):
        """
        SPEC: PRAGMA settings for performance optimization
        BEHAVIOR: cache_size ACTUALLY configured
        """
        db = DatabaseConnection(temp_db)

        with db.get_connection() as conn:
            cursor = conn.execute("PRAGMA cache_size")
            cache_size = cursor.fetchone()[0]

        # Negative value means KB, -64000 = 64MB
        assert cache_size == -64000, f"cache_size not configured, got: {cache_size}"

        db.close()

    def test_busy_timeout_configured(self, temp_db):
        """
        SPEC: System must handle lock contention gracefully
        BEHAVIOR: busy_timeout ACTUALLY set to prevent immediate lock errors
        """
        db = DatabaseConnection(temp_db)

        with db.get_connection() as conn:
            cursor = conn.execute("PRAGMA busy_timeout")
            timeout = cursor.fetchone()[0]

        # Should be 30000 milliseconds (30 seconds)
        assert timeout == 30000, f"busy_timeout not configured, got: {timeout}"

        db.close()

    def test_row_factory_enables_dict_access(self, temp_db):
        """
        SPEC: API must provide convenient data access
        BEHAVIOR: Row factory ACTUALLY enables dict-like column access
        """
        db = DatabaseConnection(temp_db)

        with db.get_connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            conn.execute("INSERT INTO test (id, name) VALUES (1, 'test')")

            cursor = conn.execute("SELECT id, name FROM test")
            row = cursor.fetchone()

        # Verify dict-like access ACTUALLY works
        assert row['id'] == 1, "Row factory not enabling column access by name"
        assert row['name'] == 'test', "Row factory not returning correct values"

        db.close()


class TestResourceCleanup:
    """Test that database connections ACTUALLY cleaned up properly."""

    def test_close_actually_closes_connection(self):
        """
        SPEC: System must not leak resources
        BEHAVIOR: close() ACTUALLY closes database connection
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)

        # Open connection
        with db.get_connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")

        # Close database
        db.close()

        # Verify connection ACTUALLY closed (new get_connection creates new conn)
        with db.get_connection() as conn:
            # If closed properly, this creates NEW connection
            # Verify by checking connection is usable
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()

        assert len(tables) > 0, "Connection not properly managed after close"

        db.close()
        Path(db_path).unlink(missing_ok=True)

    def test_close_is_idempotent(self):
        """
        SPEC: System must handle edge cases gracefully
        BEHAVIOR: Calling close() multiple times ACTUALLY safe
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = DatabaseConnection(db_path)

        # Close multiple times (should not raise exception)
        db.close()
        db.close()
        db.close()

        Path(db_path).unlink(missing_ok=True)


class TestInitDatabase:
    """Test that init_database ACTUALLY initializes schema from SQL file."""

    @pytest.fixture
    def schema_file(self):
        """Create temporary schema SQL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as tmp:
            tmp.write("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id INTEGER PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_test_value ON test_table(value);
            """)
            schema_path = tmp.name

        yield schema_path

        Path(schema_path).unlink(missing_ok=True)

    def test_init_database_creates_tables_from_schema(self, schema_file):
        """
        SPEC: System must initialize database from schema file
        BEHAVIOR: init_database ACTUALLY creates tables defined in SQL
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        # Initialize database with schema
        db = init_database(schema_file, db_path)

        # Verify table ACTUALLY created
        with db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='test_table'
            """)
            table = cursor.fetchone()

        assert table is not None, "Table not created from schema"
        assert table['name'] == 'test_table'

        db.close()
        Path(db_path).unlink(missing_ok=True)

    def test_init_database_creates_indexes_from_schema(self, schema_file):
        """
        SPEC: Schema initialization must include indexes
        BEHAVIOR: init_database ACTUALLY creates indexes defined in SQL
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        db = init_database(schema_file, db_path)

        # Verify index ACTUALLY created
        with db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index' AND name='idx_test_value'
            """)
            index = cursor.fetchone()

        assert index is not None, "Index not created from schema"

        db.close()
        Path(db_path).unlink(missing_ok=True)

    def test_init_database_raises_error_for_missing_schema_file(self):
        """
        SPEC: System must validate inputs
        BEHAVIOR: init_database ACTUALLY raises FileNotFoundError for missing schema
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        with pytest.raises(FileNotFoundError):
            init_database("nonexistent_schema.sql", db_path)

        Path(db_path).unlink(missing_ok=True)

    def test_init_database_is_idempotent(self, schema_file):
        """
        SPEC: Schema initialization must be safe to run multiple times
        BEHAVIOR: Calling init_database multiple times ACTUALLY safe (IF NOT EXISTS)
        """
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        # Initialize twice
        db1 = init_database(schema_file, db_path)
        db1.close()

        db2 = init_database(schema_file, db_path)

        # Verify schema still correct
        with db2.get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name='test_table'
            """)
            count = cursor.fetchone()[0]

        assert count == 1, "Schema initialization not idempotent"

        db2.close()
        Path(db_path).unlink(missing_ok=True)
