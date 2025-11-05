"""
Database Connection Module

SQLite database connection with WAL mode, connection pooling, and PRAGMA settings.
Per research.md Decision 5: SQLite with WAL Mode for MVP.

Constitution alignment:
- Principle IV: Data Governance - WAL mode enables concurrent reads
- Principle VI: Clarity Over Cleverness - Simple file-based database
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional
import threading


class DatabaseConnection:
    """
    Manages SQLite database connections with WAL mode and connection pooling.

    Thread-safe connection management for single-writer, multiple-reader pattern.
    """

    def __init__(self, db_path: str = "data/googili.db"):
        """
        Initialize database connection manager.

        Args:
            db_path: Path to SQLite database file (default: data/googili.db)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._wal_init_lock = threading.Lock()  # Ensure WAL mode set atomically
        self._wal_mode_set = False  # Track if WAL mode has been set
        # Note: Removed class-level _initialized flag to fix threading issue
        # Each thread's connection tracks its own initialization state

    def _init_connection(self, conn: sqlite3.Connection) -> None:
        """
        Initialize connection with WAL mode and optimizations.

        Args:
            conn: SQLite connection to initialize
        """
        # WAL mode must be set by first connection only (thread-safe)
        with self._wal_init_lock:
            if not self._wal_mode_set:
                # Enable WAL mode for concurrent reads during writes
                conn.execute("PRAGMA journal_mode=WAL")
                self._wal_mode_set = True

        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys=ON")

        # Optimize for performance
        conn.execute("PRAGMA synchronous=NORMAL")  # WAL mode allows NORMAL sync
        conn.execute("PRAGMA cache_size=-64000")    # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")    # Temp tables in memory

        # Additional optimizations (Fix 5)
        conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
        conn.execute("PRAGMA wal_autocheckpoint=1000")  # Checkpoint every 1000 pages

        # Use row factory for dict-like access
        conn.row_factory = sqlite3.Row

    @contextmanager
    def get_connection(self, auto_commit: bool = True):
        """
        Get thread-local database connection with context manager.

        Args:
            auto_commit: Automatically commit on successful exit (default: True)

        Yields:
            sqlite3.Connection: Database connection with WAL mode enabled

        Example:
            with db.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM raw_trenddata LIMIT 1")
                row = cursor.fetchone()
            # Automatically commits on successful completion
        """
        # Get or create thread-local connection
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,  # Allow thread-local connections
                timeout=30.0  # 30 second timeout for lock acquisition
            )
            # Initialize THIS thread's connection
            self._init_connection(self._local.conn)
            # Mark this thread as initialized
            self._local.initialized = True

        try:
            yield self._local.conn
            # Fix 4: Auto-commit on successful completion
            if auto_commit:
                self._local.conn.commit()
        except Exception:
            self._local.conn.rollback()
            raise

    def execute_script(self, script: str) -> None:
        """
        Execute SQL script (for schema initialization).

        Args:
            script: SQL script content
        """
        with self.get_connection() as conn:
            conn.executescript(script)
            conn.commit()

    def close(self) -> None:
        """Close thread-local connection if exists."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


def init_database(schema_path: str, db_path: str) -> DatabaseConnection:
    """
    Initialize database with schema and return fresh connection.

    Creates tables, indexes, views, triggers from schema.sql.
    Safe to run multiple times (uses IF NOT EXISTS in schema).

    The initialization connection is closed before returning.
    Caller receives a fresh DatabaseConnection instance.

    Args:
        schema_path: Path to schema.sql file
        db_path: Path to SQLite database file

    Returns:
        DatabaseConnection: Fresh database connection instance (no open connection yet)

    Raises:
        FileNotFoundError: If schema file doesn't exist

    Example:
        db = init_database("fetcher/schema.sql", "data/googili.db")
        try:
            # Use db...
        finally:
            db.close()
    """
    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    print(f"[DB INIT] Initializing database at {db_path}")
    print(f"[DB INIT] Using schema from {schema_path}")

    # Load schema SQL
    schema_sql = schema_file.read_text(encoding='utf-8')

    # Create temp connection to apply schema
    db_init = DatabaseConnection(db_path)
    try:
        db_init.execute_script(schema_sql)
    finally:
        db_init.close()  # Close init connection

    print(f"[DB INIT] Database initialized successfully")
    print(f"[DB INIT] Tables: raw_trenddata, events_raw_rsv_ingested, config_keywords, health_probe")
    print(f"[DB INIT] Views: v_latest_batch, v_recent_rsv, v_data_quality")

    # Return fresh instance for caller
    return DatabaseConnection(db_path)
