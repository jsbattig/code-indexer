"""
Group Access Manager for CIDX Server.

Manages user groups and group-based access control:
- Default groups (admins, powerusers, users) created at bootstrap
- 1:1 user-to-group membership (user belongs to exactly one group)
- Group CRUD operations with protection for default groups

Story #705: Default Group Bootstrap and User Assignment Infrastructure
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from .constants import (
    CIDX_META_REPO,
    DEFAULT_GROUP_ADMINS,
    DEFAULT_GROUP_POWERUSERS,
    DEFAULT_GROUP_USERS,
)

logger = logging.getLogger(__name__)


class DefaultGroupCannotBeDeletedError(Exception):
    """Raised when attempting to delete a default group."""

    pass


class GroupHasUsersError(Exception):
    """Raised when attempting to delete a group that has users assigned."""

    pass


class CidxMetaCannotBeRevokedError(Exception):
    """Raised when attempting to revoke cidx-meta access from any group."""

    pass


@dataclass
class Group:
    """Represents a user group."""

    id: int
    name: str
    description: str
    is_default: bool
    created_at: datetime


@dataclass
class GroupMembership:
    """Represents a user's group membership."""

    user_id: str
    group_id: int
    assigned_at: datetime
    assigned_by: str


@dataclass
class RepoGroupAccess:
    """Represents a repository-to-group access grant."""

    repo_name: str
    group_id: int
    granted_at: datetime
    granted_by: str


# Default groups to create at bootstrap
DEFAULT_GROUPS = [
    {
        "name": DEFAULT_GROUP_ADMINS,
        "description": "Full administrative access",
    },
    {
        "name": DEFAULT_GROUP_POWERUSERS,
        "description": "Access to all golden repositories",
    },
    {
        "name": DEFAULT_GROUP_USERS,
        "description": f"Basic access to {CIDX_META_REPO} only",
    },
]


class GroupAccessManager:
    """
    Manages user groups and group-based access control.

    Features:
    - Creates default groups (admins, powerusers, users) at initialization
    - Enforces 1:1 user-to-group relationship
    - Protects default groups from deletion
    - Records assignment metadata (who assigned, when)
    """

    def __init__(self, db_path: Path):
        """
        Initialize the GroupAccessManager.

        Args:
            db_path: Path to the SQLite database file for groups
        """
        self.db_path = Path(db_path)
        self._ensure_schema()
        self._bootstrap_default_groups()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory and foreign key enforcement."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        # CRITICAL: SQLite does NOT enforce foreign keys by default.
        # This MUST be executed after each connection for FK constraints to work.
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Create groups table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL,
                    is_default BOOLEAN NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """
            )

            # Create user_group_membership table with user_id as PRIMARY KEY
            # This enforces the 1:1 relationship (one user = one group)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_group_membership (
                    user_id TEXT PRIMARY KEY,
                    group_id INTEGER NOT NULL,
                    assigned_at TEXT NOT NULL,
                    assigned_by TEXT NOT NULL,
                    FOREIGN KEY (group_id) REFERENCES groups(id)
                )
            """
            )

            # Create index for user_group_membership performance
            # Queries filter by group_id: get_users_in_group, get_user_count_in_group,
            # delete_group (user count check and cascade delete)
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_group_membership_group_id
                ON user_group_membership(group_id)
            """
            )

            # Create repo_group_access table for many-to-many repository-group access
            # Story #706: Repository-to-Group Access Mapping
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS repo_group_access (
                    repo_name TEXT NOT NULL,
                    group_id INTEGER NOT NULL,
                    granted_at TEXT NOT NULL,
                    granted_by TEXT,
                    PRIMARY KEY (repo_name, group_id),
                    FOREIGN KEY (group_id) REFERENCES groups(id)
                )
            """
            )

            # Create indexes for repo_group_access performance
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_repo_group
                ON repo_group_access(group_id)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_repo_name
                ON repo_group_access(repo_name)
            """
            )

            # Create audit_logs table for administrative action tracking
            # Story #710: AC7 - Audit Log for Administrative Actions
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    admin_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    details TEXT
                )
            """
            )

            # Create indexes for audit_logs queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_logs(timestamp DESC)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_action_type
                ON audit_logs(action_type)
            """
            )

            conn.commit()
        finally:
            conn.close()

    def _bootstrap_default_groups(self) -> None:
        """Create default groups if they don't exist (idempotent)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            for group_def in DEFAULT_GROUPS:
                # INSERT OR IGNORE makes this idempotent
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO groups (name, description, is_default, created_at)
                    VALUES (?, ?, 1, ?)
                """,
                    (group_def["name"], group_def["description"], now),
                )

            conn.commit()
            logger.debug("Default groups bootstrap completed")
        finally:
            conn.close()

    def _row_to_group(self, row: sqlite3.Row) -> Group:
        """Convert a database row to a Group object."""
        created_at_str = row["created_at"]
        if isinstance(created_at_str, str):
            # Parse ISO format datetime
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        else:
            created_at = created_at_str

        return Group(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            is_default=bool(row["is_default"]),
            created_at=created_at,
        )

    def get_all_groups(self) -> List[Group]:
        """
        Get all groups.

        Story #709: Custom Group Management (AC9)

        Returns:
            List of all Group objects sorted by:
            - Default groups first (is_default DESC)
            - Then by name alphabetically (name ASC)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # AC9: Sort default groups first, then custom groups by name
            cursor.execute("SELECT * FROM groups ORDER BY is_default DESC, name ASC")
            rows = cursor.fetchall()
            return [self._row_to_group(row) for row in rows]
        finally:
            conn.close()

    def get_group(self, group_id: int) -> Optional[Group]:
        """
        Get a group by ID.

        Args:
            group_id: The group ID to look up

        Returns:
            Group object if found, None otherwise
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
            row = cursor.fetchone()
            return self._row_to_group(row) if row else None
        finally:
            conn.close()

    def get_group_by_name(self, name: str) -> Optional[Group]:
        """
        Get a group by name.

        Args:
            name: The group name to look up

        Returns:
            Group object if found, None otherwise
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM groups WHERE LOWER(name) = LOWER(?)", (name,))
            row = cursor.fetchone()
            return self._row_to_group(row) if row else None
        finally:
            conn.close()

    def create_group(self, name: str, description: str) -> Group:
        """
        Create a new custom group.

        Story #709: Custom Group Management (AC1, AC8)

        Args:
            name: The group name (must be unique, case-insensitive)
            description: Description of the group

        Returns:
            The created Group object

        Raises:
            ValueError: If a group with the same name already exists (case-insensitive)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            # AC8: Check for case-insensitive uniqueness
            cursor.execute(
                "SELECT id FROM groups WHERE LOWER(name) = LOWER(?)",
                (name,),
            )
            existing = cursor.fetchone()
            if existing:
                raise ValueError(f"Group with name '{name}' already exists")

            cursor.execute(
                """
                INSERT INTO groups (name, description, is_default, created_at)
                VALUES (?, ?, 0, ?)
            """,
                (name, description, now),
            )
            conn.commit()

            group_id = cursor.lastrowid
            assert group_id is not None, "INSERT should always return a valid lastrowid"
            group = self.get_group(group_id)
            assert group is not None, "Newly created group must exist"
            return group
        finally:
            conn.close()

    def update_group(
        self,
        group_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Group]:
        """
        Update a custom group's name and/or description.

        Story #709: Custom Group Management (AC4, AC8)

        Args:
            group_id: The ID of the group to update
            name: New name for the group (optional, case-insensitive unique)
            description: New description for the group (optional)

        Returns:
            The updated Group object, or None if not found

        Raises:
            ValueError: If attempting to update a default group or duplicate name
        """
        # First check if group exists
        group = self.get_group(group_id)
        if group is None:
            return None

        # Cannot update default groups
        if group.is_default:
            raise ValueError("Cannot update default groups")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # AC8: Check for case-insensitive name uniqueness if name is being updated
            if name is not None:
                cursor.execute(
                    "SELECT id FROM groups WHERE LOWER(name) = LOWER(?) AND id != ?",
                    (name, group_id),
                )
                existing = cursor.fetchone()
                if existing:
                    raise ValueError(f"Group with name '{name}' already exists")

            # Build UPDATE query dynamically based on provided fields
            updates: list[str] = []
            params: list[Any] = []

            if name is not None:
                updates.append("name = ?")
                params.append(name)

            if description is not None:
                updates.append("description = ?")
                params.append(description)

            if not updates:
                # No fields to update
                return group

            params.append(group_id)

            cursor.execute(
                f"UPDATE groups SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

            return self.get_group(group_id)
        finally:
            conn.close()

    def delete_group(self, group_id: int) -> bool:
        """
        Delete a custom group.

        Story #709: Custom Group Management (AC5, AC6, AC7)

        Uses a single connection with BEGIN IMMEDIATE transaction to prevent
        TOCTOU race conditions. All checks and deletes happen atomically.

        Args:
            group_id: The ID of the group to delete

        Returns:
            True if the group was deleted

        Raises:
            DefaultGroupCannotBeDeletedError: If attempting to delete a default group (AC5)
            GroupHasUsersError: If the group has users assigned (AC6)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # BEGIN IMMEDIATE acquires write lock immediately, preventing TOCTOU
            cursor.execute("BEGIN IMMEDIATE")

            try:
                # Check if group exists - WITHIN the transaction
                cursor.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
                row = cursor.fetchone()
                if row is None:
                    conn.rollback()
                    return False

                group = self._row_to_group(row)

                # AC5: Check if this is a default group
                if group.is_default:
                    conn.rollback()
                    raise DefaultGroupCannotBeDeletedError(
                        f"Cannot delete default group: {group.name}"
                    )

                # AC6: Check user count - WITHIN the same transaction
                cursor.execute(
                    "SELECT COUNT(*) FROM user_group_membership WHERE group_id = ?",
                    (group_id,),
                )
                user_count = cursor.fetchone()[0]
                if user_count > 0:
                    conn.rollback()
                    raise GroupHasUsersError(
                        f"Cannot delete group with {user_count} active user(s)"
                    )

                # AC7: Cascade delete repo_group_access records
                cursor.execute(
                    "DELETE FROM repo_group_access WHERE group_id = ?", (group_id,)
                )

                # Delete any user memberships (should be 0 due to check, but be safe)
                cursor.execute(
                    "DELETE FROM user_group_membership WHERE group_id = ?", (group_id,)
                )

                # Finally delete the group
                cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))

                conn.commit()
                return True

            except (DefaultGroupCannotBeDeletedError, GroupHasUsersError):
                # Re-raise business logic exceptions (rollback already done)
                raise
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

    def assign_user_to_group(
        self, user_id: str, group_id: int, assigned_by: str
    ) -> None:
        """
        Assign a user to a group.

        If the user is already in a group, the previous assignment is replaced.
        This enforces the 1:1 user-to-group relationship.

        Args:
            user_id: The user's unique identifier
            group_id: The target group's ID
            assigned_by: The admin user ID who made the assignment
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            # Use INSERT OR REPLACE to handle the 1:1 relationship
            # Since user_id is PRIMARY KEY, this will replace any existing row
            cursor.execute(
                """
                INSERT OR REPLACE INTO user_group_membership
                (user_id, group_id, assigned_at, assigned_by)
                VALUES (?, ?, ?, ?)
            """,
                (user_id, group_id, now, assigned_by),
            )
            conn.commit()
        finally:
            conn.close()

    def get_user_group(self, user_id: str) -> Optional[Group]:
        """
        Get the group a user belongs to.

        Args:
            user_id: The user's unique identifier

        Returns:
            The Group the user belongs to, or None if not assigned
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT g.* FROM groups g
                JOIN user_group_membership m ON g.id = m.group_id
                WHERE m.user_id = ?
            """,
                (user_id,),
            )
            row = cursor.fetchone()
            return self._row_to_group(row) if row else None
        finally:
            conn.close()

    def get_user_membership(self, user_id: str) -> Optional[GroupMembership]:
        """
        Get the full membership record for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            GroupMembership object if found, None otherwise
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_group_membership WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            assigned_at_str = row["assigned_at"]
            if isinstance(assigned_at_str, str):
                assigned_at = datetime.fromisoformat(
                    assigned_at_str.replace("Z", "+00:00")
                )
            else:
                assigned_at = assigned_at_str

            return GroupMembership(
                user_id=row["user_id"],
                group_id=row["group_id"],
                assigned_at=assigned_at,
                assigned_by=row["assigned_by"],
            )
        finally:
            conn.close()

    def get_users_in_group(self, group_id: int) -> List[str]:
        """
        Get all user IDs in a group.

        Args:
            group_id: The group ID

        Returns:
            List of user IDs in the group
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id FROM user_group_membership WHERE group_id = ?",
                (group_id,),
            )
            rows = cursor.fetchall()
            return [row["user_id"] for row in rows]
        finally:
            conn.close()

    def get_user_count_in_group(self, group_id: int) -> int:
        """
        Get the count of users in a group.

        Args:
            group_id: The group ID

        Returns:
            Number of users in the group
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM user_group_membership WHERE group_id = ?",
                (group_id,),
            )
            row = cursor.fetchone()
            return row["count"] if row else 0
        finally:
            conn.close()

    # =========================================================================
    # Repository-to-Group Access Methods (Story #706)
    # =========================================================================

    def grant_repo_access(self, repo_name: str, group_id: int, granted_by: str) -> bool:
        """
        Grant a group access to a repository.

        Args:
            repo_name: The repository name/alias
            group_id: The target group's ID
            granted_by: The admin user ID or "system:auto-assignment"

        Returns:
            True if access was newly granted, False if already existed

        Raises:
            ValueError: If the group does not exist
        """
        # Validate group exists
        group = self.get_group(group_id)
        if group is None:
            raise ValueError(f"Group with ID {group_id} not found")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            # Use INSERT OR IGNORE for idempotent behavior
            cursor.execute(
                """
                INSERT OR IGNORE INTO repo_group_access
                (repo_name, group_id, granted_at, granted_by)
                VALUES (?, ?, ?, ?)
            """,
                (repo_name, group_id, now, granted_by),
            )
            conn.commit()

            # rowcount is 0 if INSERT was ignored (already exists)
            return cursor.rowcount > 0
        finally:
            conn.close()

    def revoke_repo_access(self, repo_name: str, group_id: int) -> bool:
        """
        Revoke a group's access to a repository.

        Args:
            repo_name: The repository name/alias
            group_id: The group's ID

        Returns:
            True if access was revoked, False if it didn't exist

        Raises:
            CidxMetaCannotBeRevokedError: If attempting to revoke cidx-meta
        """
        # AC2: cidx-meta access cannot be revoked
        if repo_name == CIDX_META_REPO:
            raise CidxMetaCannotBeRevokedError(
                f"{CIDX_META_REPO} access cannot be revoked from any group"
            )

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM repo_group_access
                WHERE repo_name = ? AND group_id = ?
            """,
                (repo_name, group_id),
            )
            conn.commit()

            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_group_repos(self, group_id: int) -> List[str]:
        """
        Get all repositories accessible by a group.

        cidx-meta is always included first (implicit access).

        Args:
            group_id: The group ID

        Returns:
            List of repository names, with cidx-meta always first
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT repo_name FROM repo_group_access
                WHERE group_id = ?
                ORDER BY repo_name
            """,
                (group_id,),
            )
            rows = cursor.fetchall()
            repos = [row["repo_name"] for row in rows]

            # AC2: cidx-meta is always accessible (implicit, not stored)
            # Always include it first
            return [CIDX_META_REPO] + repos
        finally:
            conn.close()

    def get_repo_groups(self, repo_name: str) -> List[Group]:
        """
        Get all groups that can access a repository.

        For cidx-meta, returns all groups (implicit universal access).

        Args:
            repo_name: The repository name/alias

        Returns:
            List of Group objects that can access the repository
        """
        # AC2: cidx-meta is accessible to all groups
        if repo_name == CIDX_META_REPO:
            return self.get_all_groups()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT g.* FROM groups g
                JOIN repo_group_access rga ON g.id = rga.group_id
                WHERE rga.repo_name = ?
                ORDER BY g.name
            """,
                (repo_name,),
            )
            rows = cursor.fetchall()
            return [self._row_to_group(row) for row in rows]
        finally:
            conn.close()

    def get_repo_access(
        self, repo_name: str, group_id: int
    ) -> Optional[RepoGroupAccess]:
        """
        Get the access record for a specific repo-group combination.

        Args:
            repo_name: The repository name/alias
            group_id: The group ID

        Returns:
            RepoGroupAccess record if found, None otherwise
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM repo_group_access
                WHERE repo_name = ? AND group_id = ?
            """,
                (repo_name, group_id),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            granted_at_str = row["granted_at"]
            if isinstance(granted_at_str, str):
                granted_at = datetime.fromisoformat(
                    granted_at_str.replace("Z", "+00:00")
                )
            else:
                granted_at = granted_at_str

            return RepoGroupAccess(
                repo_name=row["repo_name"],
                group_id=row["group_id"],
                granted_at=granted_at,
                granted_by=row["granted_by"],
            )
        finally:
            conn.close()

    def auto_assign_golden_repo(self, repo_name: str) -> None:
        """
        Auto-assign a new golden repository to admins and powerusers groups.

        AC3: New golden repos are automatically assigned to admins and powerusers.
        AC4: Users group never receives automatic access.

        Args:
            repo_name: The repository name/alias to assign
        """
        # Get admins and powerusers groups
        admins = self.get_group_by_name(DEFAULT_GROUP_ADMINS)
        powerusers = self.get_group_by_name(DEFAULT_GROUP_POWERUSERS)

        # Grant access to admins and powerusers only (not users)
        if admins:
            self.grant_repo_access(repo_name, admins.id, "system:auto-assignment")
        if powerusers:
            self.grant_repo_access(repo_name, powerusers.id, "system:auto-assignment")

    # =========================================================================
    # User Management Methods (Story #710)
    # =========================================================================

    def get_all_users_with_groups(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> tuple[List[dict], int]:
        """
        Get all users with their group membership information.

        Story #710: Admin User and Group Management Interface (AC1)

        Args:
            limit: Maximum number of users to return (None for all)
            offset: Number of users to skip

        Returns:
            Tuple of (list of user dicts, total count)
            Each dict contains: user_id, group_id, group_name, assigned_at, assigned_by
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Get total count first
            cursor.execute("SELECT COUNT(*) as count FROM user_group_membership")
            total = cursor.fetchone()["count"]

            # Build query with JOIN to get group name
            query = """
                SELECT
                    m.user_id,
                    m.group_id,
                    g.name as group_name,
                    m.assigned_at,
                    m.assigned_by
                FROM user_group_membership m
                JOIN groups g ON m.group_id = g.id
                ORDER BY m.user_id ASC
            """

            params: list[Any] = []
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])

            cursor.execute(query, params) if params else cursor.execute(query)
            rows = cursor.fetchall()

            users = []
            for row in rows:
                users.append(
                    {
                        "user_id": row["user_id"],
                        "group_id": row["group_id"],
                        "group_name": row["group_name"],
                        "assigned_at": row["assigned_at"],
                        "assigned_by": row["assigned_by"],
                    }
                )

            return users, total
        finally:
            conn.close()

    def user_exists(self, user_id: str) -> bool:
        """
        Check if a user exists in the group membership table.

        Story #710: Admin User and Group Management Interface (AC2)

        Args:
            user_id: The user ID to check

        Returns:
            True if user exists, False otherwise
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM user_group_membership WHERE user_id = ?",
                (user_id,),
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    # =========================================================================
    # Audit Logging Methods (Story #710: AC7)
    # =========================================================================

    def log_audit(
        self,
        admin_id: str,
        action_type: str,
        target_type: str,
        target_id: str,
        details: Optional[str] = None,
    ) -> None:
        """
        Record an audit log entry.

        Story #710: AC7 - Audit Log for Administrative Actions

        Args:
            admin_id: ID of the admin performing the action
            action_type: Type of action (user_group_change, repo_access_grant, etc.)
            target_type: Type of target (user, group, repo)
            target_id: ID of the target
            details: Optional JSON details about the action
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                INSERT INTO audit_logs
                (timestamp, admin_id, action_type, target_type, target_id, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (now, admin_id, action_type, target_type, target_id, details),
            )
            conn.commit()
        finally:
            conn.close()

    def get_audit_logs(
        self,
        action_type: Optional[str] = None,
        target_type: Optional[str] = None,
        admin_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Get audit log entries with optional filters.

        Story #710: AC8 - Get Audit Logs

        Args:
            action_type: Filter by action type
            target_type: Filter by target type
            admin_id: Filter by admin who performed the action
            date_from: Filter logs from this date (ISO format YYYY-MM-DD)
            date_to: Filter logs up to this date (ISO format YYYY-MM-DD)
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            Tuple of (list of log dicts, total count)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Build WHERE clause
            conditions: list[str] = []
            params: list[Any] = []

            if action_type:
                conditions.append("action_type = ?")
                params.append(action_type)
            if target_type:
                conditions.append("target_type = ?")
                params.append(target_type)
            if admin_id:
                conditions.append("admin_id = ?")
                params.append(admin_id)
            if date_from:
                conditions.append("timestamp >= ?")
                params.append(f"{date_from}T00:00:00")
            if date_to:
                conditions.append("timestamp <= ?")
                params.append(f"{date_to}T23:59:59")

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            # Get total count
            count_query = f"SELECT COUNT(*) as count FROM audit_logs {where_clause}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()["count"]

            # Build main query
            query = f"""
                SELECT id, timestamp, admin_id, action_type, target_type,
                       target_id, details
                FROM audit_logs
                {where_clause}
                ORDER BY timestamp DESC
            """

            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            logs = []
            for row in rows:
                logs.append(
                    {
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "admin_id": row["admin_id"],
                        "action_type": row["action_type"],
                        "target_type": row["target_type"],
                        "target_id": row["target_id"],
                        "details": row["details"],
                    }
                )

            return logs, total
        finally:
            conn.close()


def seed_users_to_groups(
    user_manager: Any, group_manager: "GroupAccessManager"
) -> tuple[int, int]:
    """
    Seed existing users to appropriate groups based on their role.

    - Admin users → admins group
    - All other users → users group

    This function should be called during server startup after GroupAccessManager
    is initialized. It ensures that existing users (from before the
    group-based security model upgrade) are properly assigned to groups.

    This function is IDEMPOTENT - safe to run on every server startup because
    it checks for existing membership before assigning.

    Args:
        user_manager: The UserManager instance with existing users
        group_manager: The GroupAccessManager instance to assign users to

    Returns:
        tuple[int, int]: (admin_count, regular_count) - Number of users assigned
    """
    admin_count = 0
    regular_count = 0

    try:
        # Get the groups
        admins_group = group_manager.get_group_by_name(DEFAULT_GROUP_ADMINS)
        users_group = group_manager.get_group_by_name(DEFAULT_GROUP_USERS)

        if not admins_group:
            logger.warning("Cannot seed users: admins group not found")
            return 0, 0
        if not users_group:
            logger.warning("Cannot seed users: users group not found")
            return 0, 0

        # Get all users
        all_users = user_manager.get_all_users()

        for user in all_users:
            # Check if already assigned to any group
            existing_group = group_manager.get_user_group(user.username)
            if existing_group is not None:
                # User already has a group assignment, skip
                continue

            # Determine target group based on role
            is_admin = hasattr(user, "role") and str(user.role.value) == "admin"
            target_group = admins_group if is_admin else users_group
            assigned_by = (
                "system:admin-migration" if is_admin else "system:user-migration"
            )

            try:
                group_manager.assign_user_to_group(
                    user_id=user.username,
                    group_id=target_group.id,
                    assigned_by=assigned_by,
                )
                if is_admin:
                    admin_count += 1
                    logger.debug(
                        f"Auto-assigned admin user '{user.username}' to admins group"
                    )
                else:
                    regular_count += 1
                    logger.debug(f"Auto-assigned user '{user.username}' to users group")
            except Exception as assign_error:
                logger.warning(
                    f"Failed to assign user '{user.username}' to {target_group.name} group: {assign_error}"
                )

        if admin_count > 0 or regular_count > 0:
            logger.info(
                f"Seeded users to groups: {admin_count} admins, {regular_count} regular users"
            )

    except Exception as e:
        logger.warning(f"Failed to seed users to groups: {e}")

    return admin_count, regular_count


# Backward compatibility alias
def seed_admin_users(user_manager: Any, group_manager: "GroupAccessManager") -> int:
    """Backward compatibility wrapper for seed_users_to_groups."""
    admin_count, regular_count = seed_users_to_groups(user_manager, group_manager)
    return admin_count + regular_count


def seed_existing_golden_repos(
    golden_repo_manager: Any, group_manager: "GroupAccessManager"
) -> int:
    """
    Seed existing golden repositories to admins and powerusers groups.

    This function should be called during server startup after GroupAccessManager
    is initialized and injected into GoldenRepoManager. It ensures that existing
    golden repos (from before the group-based security model upgrade) are properly
    assigned to the default groups.

    This function is IDEMPOTENT - safe to run on every server startup because
    auto_assign_golden_repo() internally uses INSERT OR IGNORE.

    Args:
        golden_repo_manager: The GoldenRepoManager instance with existing repos
        group_manager: The GroupAccessManager instance to assign repos to

    Returns:
        int: Number of repos successfully processed (attempted to seed)
    """
    seeded_count = 0

    try:
        existing_repos = golden_repo_manager.list_golden_repos()

        for repo in existing_repos:
            # Handle both 'alias' and 'name' field names for compatibility
            repo_alias = repo.get("alias") or repo.get("name")

            if not repo_alias:
                logger.warning(
                    "Skipping repo during migration: no alias or name field found"
                )
                continue

            try:
                group_manager.auto_assign_golden_repo(repo_alias)
                seeded_count += 1
            except Exception as repo_error:
                logger.warning(
                    f"Failed to seed repo '{repo_alias}' to default groups: {repo_error}"
                )
                # Continue with other repos - don't let one failure stop migration

        if seeded_count > 0:
            logger.info(
                f"Seeded {seeded_count} existing golden repos to admins/powerusers groups"
            )

    except Exception as e:
        logger.warning(f"Failed to seed existing golden repos: {e}")

    return seeded_count
