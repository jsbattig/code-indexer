"""
Database connection pooling and schema management for SQLite storage.

Story #702: Migrate Central JSON Files to SQLite

Provides:
- DatabaseSchema: Creates and manages the SQLite schema for server state
"""

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class DatabaseSchema:
    """
    Manages SQLite database schema creation and initialization.

    Creates all tables required for storing server state that was previously
    stored in JSON files (global_registry.json, users.json, jobs.json, etc.).
    """

    # SQL statements for creating each table
    CREATE_GLOBAL_REPOS_TABLE = """
        CREATE TABLE IF NOT EXISTS global_repos (
            alias_name TEXT PRIMARY KEY,
            repo_name TEXT NOT NULL,
            repo_url TEXT,
            index_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_refresh TEXT NOT NULL,
            enable_temporal BOOLEAN DEFAULT FALSE,
            temporal_options TEXT
        )
    """

    CREATE_USERS_TABLE = """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            email TEXT,
            created_at TEXT NOT NULL,
            oidc_identity TEXT
        )
    """

    CREATE_USER_API_KEYS_TABLE = """
        CREATE TABLE IF NOT EXISTS user_api_keys (
            key_id TEXT PRIMARY KEY,
            username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
            key_hash TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            name TEXT,
            created_at TEXT NOT NULL
        )
    """

    CREATE_USER_MCP_CREDENTIALS_TABLE = """
        CREATE TABLE IF NOT EXISTS user_mcp_credentials (
            credential_id TEXT PRIMARY KEY,
            username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
            client_id TEXT NOT NULL,
            client_secret_hash TEXT NOT NULL,
            client_id_prefix TEXT NOT NULL,
            name TEXT,
            created_at TEXT NOT NULL,
            last_used_at TEXT
        )
    """

    CREATE_USER_OIDC_IDENTITIES_TABLE = """
        CREATE TABLE IF NOT EXISTS user_oidc_identities (
            username TEXT PRIMARY KEY REFERENCES users(username) ON DELETE CASCADE,
            subject TEXT NOT NULL,
            email TEXT,
            linked_at TEXT NOT NULL,
            last_login TEXT
        )
    """

    CREATE_SYNC_JOBS_TABLE = """
        CREATE TABLE IF NOT EXISTS sync_jobs (
            job_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            user_alias TEXT NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            repository_url TEXT,
            progress INTEGER DEFAULT 0,
            error_message TEXT,
            phases TEXT,
            phase_weights TEXT,
            current_phase TEXT,
            progress_history TEXT,
            recovery_checkpoint TEXT,
            analytics_data TEXT
        )
    """

    CREATE_CI_TOKENS_TABLE = """
        CREATE TABLE IF NOT EXISTS ci_tokens (
            platform TEXT PRIMARY KEY,
            encrypted_token TEXT NOT NULL,
            base_url TEXT
        )
    """

    CREATE_INVALIDATED_SESSIONS_TABLE = """
        CREATE TABLE IF NOT EXISTS invalidated_sessions (
            username TEXT NOT NULL,
            token_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (username, token_id)
        )
    """

    CREATE_PASSWORD_CHANGE_TIMESTAMPS_TABLE = """
        CREATE TABLE IF NOT EXISTS password_change_timestamps (
            username TEXT PRIMARY KEY,
            changed_at TEXT NOT NULL
        )
    """

    CREATE_SSH_KEYS_TABLE = """
        CREATE TABLE IF NOT EXISTS ssh_keys (
            name TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            key_type TEXT NOT NULL,
            private_path TEXT NOT NULL,
            public_path TEXT NOT NULL,
            public_key TEXT,
            email TEXT,
            description TEXT,
            created_at TEXT,
            imported_at TEXT,
            is_imported BOOLEAN DEFAULT FALSE
        )
    """

    CREATE_SSH_KEY_HOSTS_TABLE = """
        CREATE TABLE IF NOT EXISTS ssh_key_hosts (
            key_name TEXT NOT NULL REFERENCES ssh_keys(name) ON DELETE CASCADE,
            hostname TEXT NOT NULL,
            PRIMARY KEY (key_name, hostname)
        )
    """

    # Story #711: Golden Repository Metadata table
    CREATE_GOLDEN_REPOS_METADATA_TABLE = """
        CREATE TABLE IF NOT EXISTS golden_repos_metadata (
            alias TEXT PRIMARY KEY NOT NULL,
            repo_url TEXT NOT NULL,
            default_branch TEXT NOT NULL,
            clone_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            enable_temporal INTEGER NOT NULL DEFAULT 0,
            temporal_options TEXT
        )
    """

    # Background Jobs table (Bug fix: BackgroundJobManager SQLite migration)
    CREATE_BACKGROUND_JOBS_TABLE = """
        CREATE TABLE IF NOT EXISTS background_jobs (
            job_id TEXT PRIMARY KEY NOT NULL,
            operation_type TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            progress INTEGER NOT NULL DEFAULT 0,
            username TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            cancelled INTEGER NOT NULL DEFAULT 0,
            repo_alias TEXT,
            resolution_attempts INTEGER NOT NULL DEFAULT 0,
            claude_actions TEXT,
            failure_reason TEXT,
            extended_error TEXT,
            language_resolution_status TEXT
        )
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize DatabaseSchema.

        Args:
            db_path: Path to SQLite database file. If None, uses default
                     location based on CIDX_SERVER_DATA_DIR or ~/.cidx-server/data/
        """
        if db_path is not None:
            self.db_path = db_path
        else:
            server_data_dir = os.environ.get(
                "CIDX_SERVER_DATA_DIR", str(Path.home() / ".cidx-server")
            )
            self.db_path = str(Path(server_data_dir) / "data" / "cidx_server.db")

    def initialize_database(self) -> None:
        """
        Initialize the database with all required tables.

        Creates parent directories with secure permissions (0700) if they don't exist.
        Enables WAL mode for concurrent reads during writes.
        """
        db_path = Path(self.db_path)

        # Create parent directory with secure permissions
        parent_dir = db_path.parent
        if not parent_dir.exists():
            parent_dir.mkdir(parents=True, mode=0o700)
        else:
            # Ensure existing directory has secure permissions
            os.chmod(parent_dir, 0o700)

        # Create database and tables
        conn = sqlite3.connect(str(db_path))
        try:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            # Enable WAL mode for concurrent reads
            conn.execute("PRAGMA journal_mode = WAL")

            # Create all tables
            conn.execute(self.CREATE_GLOBAL_REPOS_TABLE)
            conn.execute(self.CREATE_USERS_TABLE)
            conn.execute(self.CREATE_USER_API_KEYS_TABLE)
            conn.execute(self.CREATE_USER_MCP_CREDENTIALS_TABLE)
            conn.execute(self.CREATE_USER_OIDC_IDENTITIES_TABLE)
            conn.execute(self.CREATE_SYNC_JOBS_TABLE)
            conn.execute(self.CREATE_CI_TOKENS_TABLE)
            conn.execute(self.CREATE_INVALIDATED_SESSIONS_TABLE)
            conn.execute(self.CREATE_PASSWORD_CHANGE_TIMESTAMPS_TABLE)
            conn.execute(self.CREATE_SSH_KEYS_TABLE)
            conn.execute(self.CREATE_SSH_KEY_HOSTS_TABLE)
            conn.execute(self.CREATE_GOLDEN_REPOS_METADATA_TABLE)
            conn.execute(self.CREATE_BACKGROUND_JOBS_TABLE)

            conn.commit()
            logger.info(f"Database initialized at {db_path}")

        finally:
            conn.close()


class DatabaseConnectionManager:
    """
    Thread-local connection pooling with atomic transaction support.

    Each thread gets its own SQLite connection, enabling concurrent reads
    while maintaining proper isolation for writes.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialize connection manager.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._local = threading.local()
        self._connections: Dict[int, sqlite3.Connection] = {}
        self._lock = threading.Lock()

    def get_connection(self) -> sqlite3.Connection:
        """
        Get thread-local database connection.

        Returns the same connection for repeated calls from the same thread.
        Creates a new connection if one doesn't exist for the current thread.

        Returns:
            SQLite connection for the current thread.
        """
        thread_id = threading.get_ident()

        # Check if connection exists for this thread
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.connection = conn

            # Track connection for cleanup
            with self._lock:
                self._connections[thread_id] = conn

        return self._local.connection

    def execute_atomic(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """
        Execute operation atomically with exclusive transaction.

        Uses BEGIN EXCLUSIVE to prevent concurrent writes, ensuring data
        integrity. Commits on success, rolls back on any exception.

        Args:
            operation: Callable that takes a connection and performs database
                      operations. Return value is passed through.

        Returns:
            The return value from the operation callable.

        Raises:
            Any exception raised by the operation (after rollback).
        """
        conn = self.get_connection()
        conn.execute("BEGIN EXCLUSIVE")
        try:
            result = operation(conn)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise

    def close_all(self) -> None:
        """
        Close all thread-local connections.

        Should be called during application shutdown to release resources.
        """
        with self._lock:
            for conn in self._connections.values():
                try:
                    conn.close()
                except Exception:
                    pass  # Ignore errors during cleanup
            self._connections.clear()

        # Clear local connection reference
        if hasattr(self._local, "connection"):
            self._local.connection = None
