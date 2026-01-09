"""
SQLite backend implementations for all server managers.

Story #702: Migrate Central JSON Files to SQLite

Provides SQLite-backed storage implementations that replace JSON file storage,
eliminating race conditions from concurrent GlobalRegistry instances.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)


class GlobalReposSqliteBackend:
    """
    SQLite backend for global repository registry.

    Replaces global_registry.json with atomic SQLite operations,
    eliminating race conditions from concurrent instances.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialize the backend.

        Args:
            db_path: Path to SQLite database file.
        """
        self._conn_manager = DatabaseConnectionManager(db_path)

    def register_repo(
        self,
        alias_name: str,
        repo_name: str,
        repo_url: Optional[str],
        index_path: str,
        enable_temporal: bool = False,
        temporal_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a new repository or update existing one.

        Args:
            alias_name: Unique alias for the repository (primary key).
            repo_name: Name of the repository.
            repo_url: Optional URL of the repository.
            index_path: Path to the repository index.
            enable_temporal: Whether temporal indexing is enabled.
            temporal_options: Optional temporal indexing options (stored as JSON).
        """
        now = datetime.now(timezone.utc).isoformat()
        temporal_json = json.dumps(temporal_options) if temporal_options else None

        def operation(conn):
            conn.execute(
                """INSERT OR REPLACE INTO global_repos
                   (alias_name, repo_name, repo_url, index_path, created_at,
                    last_refresh, enable_temporal, temporal_options)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alias_name,
                    repo_name,
                    repo_url,
                    index_path,
                    now,
                    now,
                    enable_temporal,
                    temporal_json,
                ),
            )
            return None

        self._conn_manager.execute_atomic(operation)
        logger.info(f"Registered repo: {alias_name}")

    def get_repo(self, alias_name: str) -> Optional[Dict[str, Any]]:
        """
        Get repository details by alias.

        Args:
            alias_name: Alias of the repository to retrieve.

        Returns:
            Dictionary with repository details, or None if not found.
        """
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT alias_name, repo_name, repo_url, index_path, created_at,
                      last_refresh, enable_temporal, temporal_options
               FROM global_repos WHERE alias_name = ?""",
            (alias_name,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "alias_name": row[0],
            "repo_name": row[1],
            "repo_url": row[2],
            "index_path": row[3],
            "created_at": row[4],
            "last_refresh": row[5],
            "enable_temporal": bool(row[6]),
            "temporal_options": json.loads(row[7]) if row[7] else None,
        }

    def list_repos(self) -> Dict[str, Dict[str, Any]]:
        """
        List all registered repositories.

        Returns:
            Dictionary mapping alias names to repository details.
        """
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT alias_name, repo_name, repo_url, index_path, created_at,
                      last_refresh, enable_temporal, temporal_options
               FROM global_repos"""
        )

        result = {}
        for row in cursor.fetchall():
            alias = row[0]
            result[alias] = {
                "alias_name": alias,
                "repo_name": row[1],
                "repo_url": row[2],
                "index_path": row[3],
                "created_at": row[4],
                "last_refresh": row[5],
                "enable_temporal": bool(row[6]),
                "temporal_options": json.loads(row[7]) if row[7] else None,
            }

        return result

    def delete_repo(self, alias_name: str) -> bool:
        """
        Delete a repository by alias.

        Args:
            alias_name: Alias of the repository to delete.

        Returns:
            True if a record was deleted, False if not found.
        """

        def operation(conn):
            cursor = conn.execute(
                "DELETE FROM global_repos WHERE alias_name = ?",
                (alias_name,),
            )
            return cursor.rowcount > 0

        deleted = self._conn_manager.execute_atomic(operation)
        if deleted:
            logger.info(f"Deleted repo: {alias_name}")
        return deleted

    def update_last_refresh(self, alias_name: str) -> bool:
        """
        Update the last_refresh timestamp for a repository.

        Args:
            alias_name: Alias of the repository to update.

        Returns:
            True if record was updated, False if not found.
        """
        now = datetime.now(timezone.utc).isoformat()

        def operation(conn):
            cursor = conn.execute(
                "UPDATE global_repos SET last_refresh = ? WHERE alias_name = ?",
                (now, alias_name),
            )
            return cursor.rowcount > 0

        updated = self._conn_manager.execute_atomic(operation)
        if updated:
            logger.debug(f"Updated last_refresh for repo: {alias_name}")
        return updated

    def close(self) -> None:
        """Close database connections."""
        self._conn_manager.close_all()


class UsersSqliteBackend:
    """
    SQLite backend for user management with normalized tables.

    Replaces users.json with atomic SQLite operations. User data is normalized
    across 4 tables: users, user_api_keys, user_mcp_credentials, user_oidc_identities.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the backend."""
        self._conn_manager = DatabaseConnectionManager(db_path)

    def create_user(
        self,
        username: str,
        password_hash: str,
        role: str,
        email: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> None:
        """Create a new user."""
        now = created_at if created_at else datetime.now(timezone.utc).isoformat()

        def operation(conn):
            conn.execute(
                """INSERT INTO users (username, password_hash, role, email, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (username, password_hash, role, email, now),
            )
            return None

        self._conn_manager.execute_atomic(operation)
        logger.info(f"Created user: {username}")

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user with all related data (api_keys, mcp_credentials)."""
        conn = self._conn_manager.get_connection()

        cursor = conn.execute(
            """SELECT username, password_hash, role, email, created_at, oidc_identity
               FROM users WHERE username = ?""",
            (username,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return {
            "username": row[0],
            "password_hash": row[1],
            "role": row[2],
            "email": row[3],
            "created_at": row[4],
            "oidc_identity": json.loads(row[5]) if row[5] else None,
            "api_keys": self._get_api_keys(conn, username),
            "mcp_credentials": self._get_mcp_credentials(conn, username),
        }

    def _get_api_keys(self, conn, username: str) -> list:
        """Get api_keys for a user."""
        cursor = conn.execute(
            """SELECT key_id, key_hash, key_prefix, name, created_at
               FROM user_api_keys WHERE username = ?""",
            (username,),
        )
        return [
            {"key_id": r[0], "key_hash": r[1], "key_prefix": r[2],
             "name": r[3], "created_at": r[4]}
            for r in cursor.fetchall()
        ]

    def _get_mcp_credentials(self, conn, username: str) -> list:
        """Get mcp_credentials for a user."""
        cursor = conn.execute(
            """SELECT credential_id, client_id, client_secret_hash, client_id_prefix,
                      name, created_at, last_used_at
               FROM user_mcp_credentials WHERE username = ?""",
            (username,),
        )
        return [
            {"credential_id": r[0], "client_id": r[1], "client_secret_hash": r[2],
             "client_id_prefix": r[3], "name": r[4], "created_at": r[5],
             "last_used_at": r[6]}
            for r in cursor.fetchall()
        ]

    def add_api_key(
        self,
        username: str,
        key_id: str,
        key_hash: str,
        key_prefix: str,
        name: Optional[str] = None,
    ) -> None:
        """Add an API key for a user."""
        now = datetime.now(timezone.utc).isoformat()

        def operation(conn):
            conn.execute(
                """INSERT INTO user_api_keys
                   (key_id, username, key_hash, key_prefix, name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (key_id, username, key_hash, key_prefix, name, now),
            )
            return None

        self._conn_manager.execute_atomic(operation)

    def add_mcp_credential(
        self,
        username: str,
        credential_id: str,
        client_id: str,
        client_secret_hash: str,
        client_id_prefix: str,
        name: Optional[str] = None,
    ) -> None:
        """Add MCP credential for a user."""
        now = datetime.now(timezone.utc).isoformat()

        def operation(conn):
            conn.execute(
                """INSERT INTO user_mcp_credentials
                   (credential_id, username, client_id, client_secret_hash,
                    client_id_prefix, name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (credential_id, username, client_id, client_secret_hash,
                 client_id_prefix, name, now),
            )
            return None

        self._conn_manager.execute_atomic(operation)

    def list_users(self) -> list:
        """List all users with their related data."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT username, password_hash, role, email, created_at, oidc_identity
               FROM users"""
        )
        results = []
        for row in cursor.fetchall():
            username = row[0]
            results.append({
                "username": username,
                "password_hash": row[1],
                "role": row[2],
                "email": row[3],
                "created_at": row[4],
                "oidc_identity": json.loads(row[5]) if row[5] else None,
                "api_keys": self._get_api_keys(conn, username),
                "mcp_credentials": self._get_mcp_credentials(conn, username),
            })
        return results

    def update_user(
        self,
        username: str,
        new_username: Optional[str] = None,
        email: Optional[str] = None,
    ) -> bool:
        """
        Update user's username or email.

        Args:
            username: Current username
            new_username: New username (if changing)
            email: New email (if changing)

        Returns:
            True if successful, False if user not found
        """
        # First check if user exists
        if self.get_user(username) is None:
            return False

        def operation(conn):
            if new_username and new_username != username:
                # Update username (primary key change)
                conn.execute(
                    "UPDATE users SET username = ?, email = COALESCE(?, email) WHERE username = ?",
                    (new_username, email, username),
                )
                # Update foreign keys in related tables
                conn.execute(
                    "UPDATE user_api_keys SET username = ? WHERE username = ?",
                    (new_username, username),
                )
                conn.execute(
                    "UPDATE user_mcp_credentials SET username = ? WHERE username = ?",
                    (new_username, username),
                )
            elif email is not None:
                # Only update email
                conn.execute(
                    "UPDATE users SET email = ? WHERE username = ?",
                    (email, username),
                )
            return True

        self._conn_manager.execute_atomic(operation)
        logger.info(f"Updated user: {username}")
        return True

    def delete_user(self, username: str) -> bool:
        """Delete user and all related records (cascade)."""
        def operation(conn):
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.execute("DELETE FROM users WHERE username = ?", (username,))
            return cursor.rowcount > 0

        deleted = self._conn_manager.execute_atomic(operation)
        if deleted:
            logger.info(f"Deleted user: {username}")
        return deleted

    def update_user_role(self, username: str, role: str) -> bool:
        """Update user's role."""
        def operation(conn):
            cursor = conn.execute(
                "UPDATE users SET role = ? WHERE username = ?",
                (role, username),
            )
            return cursor.rowcount > 0
        updated = self._conn_manager.execute_atomic(operation)
        if updated:
            logger.info(f"Updated role for user: {username}")
        return updated

    def update_password_hash(self, username: str, password_hash: str) -> bool:
        """Update user's password hash."""
        def operation(conn):
            cursor = conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (password_hash, username),
            )
            return cursor.rowcount > 0
        updated = self._conn_manager.execute_atomic(operation)
        if updated:
            logger.info(f"Updated password for user: {username}")
        return updated

    def delete_api_key(self, username: str, key_id: str) -> bool:
        """Delete an API key for a user."""
        def operation(conn):
            cursor = conn.execute(
                "DELETE FROM user_api_keys WHERE username = ? AND key_id = ?",
                (username, key_id),
            )
            return cursor.rowcount > 0
        return self._conn_manager.execute_atomic(operation)

    def close(self) -> None:
        """Close database connections."""
        self._conn_manager.close_all()


class SyncJobsSqliteBackend:
    """
    SQLite backend for sync job management.

    Replaces JSON file storage with atomic SQLite operations.
    Complex nested data (phases, analytics) stored as JSON blobs.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the backend."""
        self._conn_manager = DatabaseConnectionManager(db_path)

    def create_job(
        self,
        job_id: str,
        username: str,
        user_alias: str,
        job_type: str,
        status: str,
        repository_url: Optional[str] = None,
    ) -> None:
        """Create a new sync job."""
        now = datetime.now(timezone.utc).isoformat()

        def operation(conn):
            conn.execute(
                """INSERT INTO sync_jobs
                   (job_id, username, user_alias, job_type, status, created_at, repository_url, progress)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, username, user_alias, job_type, status, now, repository_url, 0),
            )
            return None

        self._conn_manager.execute_atomic(operation)
        logger.info(f"Created sync job: {job_id}")

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by job ID."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT job_id, username, user_alias, job_type, status, created_at,
                      started_at, completed_at, repository_url, progress, error_message,
                      phases, phase_weights, current_phase, progress_history,
                      recovery_checkpoint, analytics_data
               FROM sync_jobs WHERE job_id = ?""",
            (job_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert a database row to job dictionary."""
        return {
            "job_id": row[0], "username": row[1], "user_alias": row[2],
            "job_type": row[3], "status": row[4], "created_at": row[5],
            "started_at": row[6], "completed_at": row[7], "repository_url": row[8],
            "progress": row[9], "error_message": row[10],
            "phases": json.loads(row[11]) if row[11] else None,
            "phase_weights": json.loads(row[12]) if row[12] else None,
            "current_phase": row[13],
            "progress_history": json.loads(row[14]) if row[14] else None,
            "recovery_checkpoint": json.loads(row[15]) if row[15] else None,
            "analytics_data": json.loads(row[16]) if row[16] else None,
        }

    def update_job(self, job_id: str, **kwargs) -> None:
        """Update job fields. Accepts: status, progress, error_message, phases, etc."""
        json_fields = {"phases", "phase_weights", "progress_history", "recovery_checkpoint", "analytics_data"}
        updates, params = [], []
        for key, value in kwargs.items():
            if value is not None:
                updates.append(f"{key} = ?")
                params.append(json.dumps(value) if key in json_fields else value)
        if not updates:
            return
        params.append(job_id)

        def operation(conn):
            conn.execute(f"UPDATE sync_jobs SET {', '.join(updates)} WHERE job_id = ?", params)
            return None
        self._conn_manager.execute_atomic(operation)

    def list_jobs(self) -> list:
        """List all sync jobs."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT job_id, username, user_alias, job_type, status, created_at,
                      started_at, completed_at, repository_url, progress, error_message,
                      phases, phase_weights, current_phase, progress_history,
                      recovery_checkpoint, analytics_data FROM sync_jobs"""
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        def operation(conn):
            cursor = conn.execute("DELETE FROM sync_jobs WHERE job_id = ?", (job_id,))
            return cursor.rowcount > 0
        deleted = self._conn_manager.execute_atomic(operation)
        if deleted:
            logger.info(f"Deleted sync job: {job_id}")
        return deleted

    def close(self) -> None:
        """Close database connections."""
        self._conn_manager.close_all()


class CITokensSqliteBackend:
    """SQLite backend for CI token storage. Replaces ci_tokens.json."""

    def __init__(self, db_path: str) -> None:
        """Initialize the backend."""
        self._conn_manager = DatabaseConnectionManager(db_path)

    def save_token(self, platform: str, encrypted_token: str, base_url: Optional[str] = None) -> None:
        """Save or update a CI token."""
        def operation(conn):
            conn.execute(
                "INSERT OR REPLACE INTO ci_tokens (platform, encrypted_token, base_url) VALUES (?, ?, ?)",
                (platform, encrypted_token, base_url),
            )
            return None
        self._conn_manager.execute_atomic(operation)
        logger.info(f"Saved CI token for platform: {platform}")

    def get_token(self, platform: str) -> Optional[Dict[str, Any]]:
        """Get token for a platform."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            "SELECT platform, encrypted_token, base_url FROM ci_tokens WHERE platform = ?",
            (platform,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {"platform": row[0], "encrypted_token": row[1], "base_url": row[2]}

    def delete_token(self, platform: str) -> bool:
        """Delete token for a platform."""
        def operation(conn):
            cursor = conn.execute("DELETE FROM ci_tokens WHERE platform = ?", (platform,))
            return cursor.rowcount > 0
        deleted = self._conn_manager.execute_atomic(operation)
        if deleted:
            logger.info(f"Deleted CI token for platform: {platform}")
        return deleted

    def list_tokens(self) -> Dict[str, Dict[str, Any]]:
        """List all tokens keyed by platform."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute("SELECT platform, encrypted_token, base_url FROM ci_tokens")
        result = {}
        for row in cursor.fetchall():
            result[row[0]] = {"platform": row[0], "encrypted_token": row[1], "base_url": row[2]}
        return result

    def close(self) -> None:
        """Close database connections."""
        self._conn_manager.close_all()


class SessionsSqliteBackend:
    """SQLite backend for session management (invalidated_sessions and password_change_timestamps)."""

    def __init__(self, db_path: str) -> None:
        """Initialize the backend."""
        self._conn_manager = DatabaseConnectionManager(db_path)

    def invalidate_session(self, username: str, token_id: str) -> None:
        """Invalidate a specific session token."""
        now = datetime.now(timezone.utc).isoformat()

        def operation(conn):
            conn.execute(
                "INSERT OR REPLACE INTO invalidated_sessions (username, token_id, created_at) VALUES (?, ?, ?)",
                (username, token_id, now),
            )
            return None
        self._conn_manager.execute_atomic(operation)

    def is_session_invalidated(self, username: str, token_id: str) -> bool:
        """Check if a session token has been invalidated."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            "SELECT 1 FROM invalidated_sessions WHERE username = ? AND token_id = ?",
            (username, token_id),
        )
        return cursor.fetchone() is not None

    def clear_invalidated_sessions(self, username: str) -> None:
        """Clear all invalidated sessions for a user."""
        def operation(conn):
            conn.execute("DELETE FROM invalidated_sessions WHERE username = ?", (username,))
            return None
        self._conn_manager.execute_atomic(operation)

    def set_password_change_timestamp(self, username: str, changed_at: str) -> None:
        """Set password change timestamp for a user."""
        def operation(conn):
            conn.execute(
                "INSERT OR REPLACE INTO password_change_timestamps (username, changed_at) VALUES (?, ?)",
                (username, changed_at),
            )
            return None
        self._conn_manager.execute_atomic(operation)

    def get_password_change_timestamp(self, username: str) -> Optional[str]:
        """Get password change timestamp for a user."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            "SELECT changed_at FROM password_change_timestamps WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def close(self) -> None:
        """Close database connections."""
        self._conn_manager.close_all()


class SSHKeysSqliteBackend:
    """SQLite backend for SSH key management. Uses junction table ssh_key_hosts."""

    def __init__(self, db_path: str) -> None:
        """Initialize the backend."""
        self._conn_manager = DatabaseConnectionManager(db_path)

    def create_key(
        self, name: str, fingerprint: str, key_type: str, private_path: str, public_path: str,
        public_key: Optional[str] = None, email: Optional[str] = None,
        description: Optional[str] = None, is_imported: bool = False,
    ) -> None:
        """Create a new SSH key record."""
        now = datetime.now(timezone.utc).isoformat()

        def operation(conn):
            conn.execute(
                """INSERT INTO ssh_keys (name, fingerprint, key_type, private_path, public_path,
                   public_key, email, description, created_at, is_imported) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, fingerprint, key_type, private_path, public_path, public_key, email, description, now, is_imported),
            )
            return None
        self._conn_manager.execute_atomic(operation)
        logger.info(f"Created SSH key: {name}")

    def get_key(self, name: str) -> Optional[Dict[str, Any]]:
        """Get SSH key details with hosts."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT name, fingerprint, key_type, private_path, public_path, public_key,
               email, description, created_at, imported_at, is_imported FROM ssh_keys WHERE name = ?""",
            (name,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        hosts = self._get_hosts_for_key(conn, name)
        return {
            "name": row[0], "fingerprint": row[1], "key_type": row[2], "private_path": row[3],
            "public_path": row[4], "public_key": row[5], "email": row[6], "description": row[7],
            "created_at": row[8], "imported_at": row[9], "is_imported": bool(row[10]), "hosts": hosts,
        }

    def _get_hosts_for_key(self, conn: Any, key_name: str) -> list:
        """Get hosts for a key from junction table."""
        cursor = conn.execute("SELECT hostname FROM ssh_key_hosts WHERE key_name = ?", (key_name,))
        return [row[0] for row in cursor.fetchall()]

    def assign_host(self, key_name: str, hostname: str) -> None:
        """Assign a host to a key."""
        def operation(conn):
            conn.execute("INSERT OR IGNORE INTO ssh_key_hosts (key_name, hostname) VALUES (?, ?)", (key_name, hostname))
            return None
        self._conn_manager.execute_atomic(operation)

    def remove_host(self, key_name: str, hostname: str) -> None:
        """Remove a host from a key."""
        def operation(conn):
            conn.execute("DELETE FROM ssh_key_hosts WHERE key_name = ? AND hostname = ?", (key_name, hostname))
            return None
        self._conn_manager.execute_atomic(operation)

    def delete_key(self, name: str) -> bool:
        """Delete an SSH key (cascades to hosts)."""
        def operation(conn):
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.execute("DELETE FROM ssh_keys WHERE name = ?", (name,))
            return cursor.rowcount > 0
        deleted = self._conn_manager.execute_atomic(operation)
        if deleted:
            logger.info(f"Deleted SSH key: {name}")
        return deleted

    def list_keys(self) -> list:
        """List all SSH keys with their hosts."""
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT name, fingerprint, key_type, private_path, public_path, public_key,
               email, description, created_at, imported_at, is_imported FROM ssh_keys"""
        )
        results = []
        for row in cursor.fetchall():
            key_name = row[0]
            hosts = self._get_hosts_for_key(conn, key_name)
            results.append({
                "name": key_name, "fingerprint": row[1], "key_type": row[2], "private_path": row[3],
                "public_path": row[4], "public_key": row[5], "email": row[6], "description": row[7],
                "created_at": row[8], "imported_at": row[9], "is_imported": bool(row[10]), "hosts": hosts,
            })
        return results

    def close(self) -> None:
        """Close database connections."""
        self._conn_manager.close_all()


class GoldenRepoMetadataSqliteBackend:
    """
    SQLite backend for golden repository metadata (Story #711).

    Replaces golden-repos/metadata.json with atomic SQLite operations,
    eliminating race conditions from concurrent access.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialize the backend.

        Args:
            db_path: Path to SQLite database file.
        """
        self._conn_manager = DatabaseConnectionManager(db_path)

    def add_repo(
        self,
        alias: str,
        repo_url: str,
        default_branch: str,
        clone_path: str,
        created_at: str,
        enable_temporal: bool = False,
        temporal_options: Optional[Dict] = None,
    ) -> None:
        """
        Add a new golden repository.

        Args:
            alias: Unique alias for the repository (primary key).
            repo_url: Git repository URL.
            default_branch: Default branch name.
            clone_path: Path to cloned repository.
            created_at: ISO 8601 timestamp when repository was created.
            enable_temporal: Whether temporal indexing is enabled.
            temporal_options: Optional temporal indexing options (stored as JSON).

        Raises:
            sqlite3.IntegrityError: If alias already exists.
        """
        temporal_json = json.dumps(temporal_options) if temporal_options else None

        def operation(conn):
            conn.execute(
                """INSERT INTO golden_repos_metadata
                   (alias, repo_url, default_branch, clone_path, created_at,
                    enable_temporal, temporal_options)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    alias,
                    repo_url,
                    default_branch,
                    clone_path,
                    created_at,
                    1 if enable_temporal else 0,
                    temporal_json,
                ),
            )
            return None

        self._conn_manager.execute_atomic(operation)
        logger.info(f"Added golden repo: {alias}")

    def get_repo(self, alias: str) -> Optional[Dict[str, Any]]:
        """
        Get golden repository details by alias.

        Args:
            alias: Alias of the repository to retrieve.

        Returns:
            Dictionary with repository details, or None if not found.
        """
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT alias, repo_url, default_branch, clone_path, created_at,
                      enable_temporal, temporal_options
               FROM golden_repos_metadata WHERE alias = ?""",
            (alias,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "alias": row[0],
            "repo_url": row[1],
            "default_branch": row[2],
            "clone_path": row[3],
            "created_at": row[4],
            "enable_temporal": bool(row[5]),
            "temporal_options": json.loads(row[6]) if row[6] else None,
        }

    def list_repos(self) -> List[Dict[str, Any]]:
        """
        List all golden repositories.

        Returns:
            List of repository dictionaries.
        """
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            """SELECT alias, repo_url, default_branch, clone_path, created_at,
                      enable_temporal, temporal_options
               FROM golden_repos_metadata"""
        )

        result = []
        for row in cursor.fetchall():
            result.append({
                "alias": row[0],
                "repo_url": row[1],
                "default_branch": row[2],
                "clone_path": row[3],
                "created_at": row[4],
                "enable_temporal": bool(row[5]),
                "temporal_options": json.loads(row[6]) if row[6] else None,
            })

        return result

    def remove_repo(self, alias: str) -> bool:
        """
        Remove a golden repository by alias.

        Args:
            alias: Alias of the repository to remove.

        Returns:
            True if a record was deleted, False if not found.
        """

        def operation(conn):
            cursor = conn.execute(
                "DELETE FROM golden_repos_metadata WHERE alias = ?",
                (alias,),
            )
            return cursor.rowcount > 0

        deleted = self._conn_manager.execute_atomic(operation)
        if deleted:
            logger.info(f"Removed golden repo: {alias}")
        return deleted

    def repo_exists(self, alias: str) -> bool:
        """
        Check if a golden repository exists.

        Args:
            alias: Alias to check.

        Returns:
            True if alias exists, False otherwise.
        """
        conn = self._conn_manager.get_connection()
        cursor = conn.execute(
            "SELECT 1 FROM golden_repos_metadata WHERE alias = ?",
            (alias,),
        )
        return cursor.fetchone() is not None

    def close(self) -> None:
        """Close database connections."""
        self._conn_manager.close_all()
