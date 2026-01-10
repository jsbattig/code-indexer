"""
Tests for SQLite foreign key constraint enforcement.

CRITICAL BUG: SQLite does NOT enforce foreign keys by default.
The _get_connection() method MUST execute 'PRAGMA foreign_keys = ON'
after each connection for foreign keys to work.

TDD Test Strategy:
1. Test that inserting repo_group_access with non-existent group_id fails
2. Test that user_group_membership with non-existent group_id fails
3. Test that FK enforcement is active on all connections

These tests should FAIL before the fix (FK not enforced) and PASS after.
"""

import sqlite3
from pathlib import Path

import pytest


class TestSqliteForeignKeyEnforcement:
    """Test that foreign key constraints are properly enforced."""

    def test_repo_group_access_rejects_invalid_group_id(self, tmp_path: Path) -> None:
        """
        Test that inserting a repo_group_access record with a non-existent
        group_id raises an IntegrityError due to foreign key constraint.

        This test should FAIL before the fix because FK is not enforced.
        After the fix, the insert should raise sqlite3.IntegrityError.
        """
        # Import here to get fresh module state
        from src.code_indexer.server.services.group_access_manager import (
            GroupAccessManager,
        )

        db_path = tmp_path / "test_fk.db"
        manager = GroupAccessManager(db_path)

        # The default groups exist (admins, powerusers, users)
        # Their IDs will be 1, 2, 3 respectively
        # Let's use a group_id that definitely doesn't exist
        non_existent_group_id = 99999

        # Get a raw connection to bypass the manager's validation
        conn = manager._get_connection()
        try:
            cursor = conn.cursor()

            # This should FAIL if FK enforcement is working
            # But will SUCCEED if FK is not enforced (the bug)
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                cursor.execute(
                    """
                    INSERT INTO repo_group_access
                    (repo_name, group_id, granted_at, granted_by)
                    VALUES (?, ?, datetime('now'), ?)
                    """,
                    ("test-repo", non_existent_group_id, "test-admin"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_user_group_membership_rejects_invalid_group_id(
        self, tmp_path: Path
    ) -> None:
        """
        Test that inserting a user_group_membership record with a non-existent
        group_id raises an IntegrityError due to foreign key constraint.

        This test should FAIL before the fix because FK is not enforced.
        After the fix, the insert should raise sqlite3.IntegrityError.
        """
        from src.code_indexer.server.services.group_access_manager import (
            GroupAccessManager,
        )

        db_path = tmp_path / "test_fk.db"
        manager = GroupAccessManager(db_path)

        non_existent_group_id = 99999

        conn = manager._get_connection()
        try:
            cursor = conn.cursor()

            # This should FAIL if FK enforcement is working
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                cursor.execute(
                    """
                    INSERT INTO user_group_membership
                    (user_id, group_id, assigned_at, assigned_by)
                    VALUES (?, ?, datetime('now'), ?)
                    """,
                    ("test-user", non_existent_group_id, "test-admin"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_foreign_key_pragma_is_enabled(self, tmp_path: Path) -> None:
        """
        Test that PRAGMA foreign_keys returns 1 (ON) for connections
        obtained from _get_connection().

        This directly tests the fix - the pragma should be enabled.
        """
        from src.code_indexer.server.services.group_access_manager import (
            GroupAccessManager,
        )

        db_path = tmp_path / "test_fk.db"
        manager = GroupAccessManager(db_path)

        conn = manager._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys")
            result = cursor.fetchone()

            # Should be 1 (ON) after the fix
            # Will be 0 (OFF) before the fix
            assert result[0] == 1, (
                "PRAGMA foreign_keys should be ON (1), but got OFF (0). "
                "The _get_connection() method must execute "
                "'PRAGMA foreign_keys = ON' after creating the connection."
            )
        finally:
            conn.close()

    def test_cascade_delete_when_group_deleted_via_raw_sql(
        self, tmp_path: Path
    ) -> None:
        """
        Test that deleting a group via raw SQL cascades to repo_group_access
        when foreign key constraints are enforced.

        Note: The current schema doesn't define ON DELETE CASCADE, so this
        test verifies that the delete is BLOCKED when FK is enforced.
        """
        from src.code_indexer.server.services.group_access_manager import (
            GroupAccessManager,
        )

        db_path = tmp_path / "test_fk.db"
        manager = GroupAccessManager(db_path)

        # Create a custom group
        custom_group = manager.create_group("test-group", "Test group for FK test")
        group_id = custom_group.id

        # Grant repo access to this group
        manager.grant_repo_access("test-repo", group_id, "test-admin")

        # Now try to delete the group via raw SQL (bypassing manager's cascade)
        conn = manager._get_connection()
        try:
            cursor = conn.cursor()

            # With FK enforcement ON and no CASCADE clause, this should fail
            # because repo_group_access references this group
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))
                conn.commit()
        finally:
            conn.close()

    def test_multiple_connections_all_have_fk_enabled(self, tmp_path: Path) -> None:
        """
        Test that multiple successive connections all have FK enforcement.

        Since PRAGMA foreign_keys must be set per-connection, each new
        connection should have it enabled.
        """
        from src.code_indexer.server.services.group_access_manager import (
            GroupAccessManager,
        )

        db_path = tmp_path / "test_fk.db"
        manager = GroupAccessManager(db_path)

        # Get multiple connections and verify FK is enabled on each
        for i in range(5):
            conn = manager._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys")
                result = cursor.fetchone()
                assert result[0] == 1, (
                    f"Connection {i+1}: PRAGMA foreign_keys should be ON (1), "
                    f"but got {result[0]}"
                )
            finally:
                conn.close()

    def test_user_group_membership_has_group_id_index(self, tmp_path: Path) -> None:
        """
        Test that user_group_membership table has an index on group_id column.

        Multiple queries in GroupAccessManager use WHERE group_id = ?:
        - Line 477: SELECT COUNT(*) FROM user_group_membership WHERE group_id = ?
        - Line 494: DELETE FROM user_group_membership WHERE group_id = ?
        - Line 623: SELECT user_id FROM user_group_membership WHERE group_id = ?
        - Line 645: SELECT COUNT(*) as count FROM user_group_membership WHERE group_id = ?

        Without an index, these queries perform full table scans.
        """
        from src.code_indexer.server.services.group_access_manager import (
            GroupAccessManager,
        )

        db_path = tmp_path / "test_indexes.db"
        manager = GroupAccessManager(db_path)

        conn = manager._get_connection()
        try:
            cursor = conn.cursor()
            # Query sqlite_master for indexes on user_group_membership table
            cursor.execute(
                """
                SELECT name, sql FROM sqlite_master
                WHERE type = 'index'
                AND tbl_name = 'user_group_membership'
                AND name LIKE '%group_id%'
                """
            )
            index_row = cursor.fetchone()

            assert index_row is not None, (
                "Missing index on user_group_membership.group_id. "
                "Queries filtering by group_id will perform full table scans. "
                "Expected index: idx_user_group_membership_group_id"
            )
            assert "group_id" in index_row["sql"].lower(), (
                f"Index {index_row['name']} does not include group_id column: "
                f"{index_row['sql']}"
            )
        finally:
            conn.close()
