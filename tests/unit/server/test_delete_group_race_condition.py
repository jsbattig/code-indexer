"""
Unit tests for delete_group() TOCTOU race condition and transaction atomicity fix.

TDD Tests covering:
1. Atomicity - all delete operations in single transaction
2. Transaction rollback on failure (no partial deletes)
3. TOCTOU protection (single connection for entire operation)

Bug Description:
- delete_group() used THREE separate connections (get_group, get_user_count, delete)
- Between checking user count and deleting, another request could add a user
- Multiple DELETE statements were NOT in a proper transaction

TDD: These tests are written FIRST, before the fix is implemented.
"""

import pytest
import tempfile
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
    GroupHasUsersError,
    DefaultGroupCannotBeDeletedError,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def group_manager(temp_db_path):
    """Create and initialize a GroupAccessManager for testing."""
    return GroupAccessManager(temp_db_path)


class TestDeleteGroupAtomicity:
    """
    Tests verifying that delete_group() operates atomically.

    All operations (group lookup, user count check, deletes) must happen
    within a single database transaction.
    """

    def test_delete_group_uses_single_connection_pattern(
        self, group_manager, temp_db_path
    ):
        """
        Test that delete_group() uses a single connection for entire operation.

        The fixed implementation should only call _get_connection() once
        for the entire delete_group() operation.
        """
        group = group_manager.create_group("test-atomic", "Test atomicity")

        original_get_connection = group_manager._get_connection
        connection_call_count = 0

        def counting_get_connection():
            nonlocal connection_call_count
            connection_call_count += 1
            return original_get_connection()

        with patch.object(
            group_manager, "_get_connection", side_effect=counting_get_connection
        ):
            group_manager.delete_group(group.id)

        assert connection_call_count == 1, (
            f"delete_group() should use only 1 connection, but used {connection_call_count}. "
            "This indicates potential TOCTOU vulnerability."
        )

    def test_delete_group_all_tables_deleted_in_transaction(
        self, group_manager, temp_db_path
    ):
        """
        Test that all DELETE statements happen within a single transaction.
        """
        group = group_manager.create_group("test-cascade", "Test cascade")
        group_manager.grant_repo_access("repo-1", group.id, "admin")
        group_manager.grant_repo_access("repo-2", group.id, "admin")

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (group.id,)
        )
        assert cursor.fetchone()[0] == 2, "Setup: should have 2 repo access records"
        conn.close()

        result = group_manager.delete_group(group.id)
        assert result is True

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (group.id,)
        )
        assert cursor.fetchone()[0] == 0, "All repo_group_access should be deleted"
        cursor.execute("SELECT COUNT(*) FROM groups WHERE id = ?", (group.id,))
        assert cursor.fetchone()[0] == 0, "Group should be deleted"
        conn.close()


class TestDeleteGroupEdgeCases:
    """Edge case tests for delete_group() atomicity."""

    def test_delete_returns_false_for_nonexistent_group(self, group_manager):
        """Test delete returns False (not exception) for non-existent group."""
        result = group_manager.delete_group(99999)
        assert result is False

    def test_delete_returns_true_for_successful_delete(self, group_manager):
        """Test delete returns True for successful deletion."""
        group = group_manager.create_group("success-test", "Test success")
        result = group_manager.delete_group(group.id)
        assert result is True

    def test_delete_idempotent_second_delete_returns_false(self, group_manager):
        """Test that deleting same group twice returns False on second attempt."""
        group = group_manager.create_group("idempotent-test", "Test idempotent")
        group_id = group.id

        result1 = group_manager.delete_group(group_id)
        assert result1 is True

        result2 = group_manager.delete_group(group_id)
        assert result2 is False


class TestDeleteGroupTransactionRollback:
    """
    Tests verifying transaction rollback behavior.

    If any part of delete_group() fails, no partial deletes should occur.
    """

    def test_rollback_when_group_not_found(self, group_manager, temp_db_path):
        """Test that no changes occur when group is not found."""
        non_existent_id = 99999

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM groups")
        count_before = cursor.fetchone()[0]
        conn.close()

        result = group_manager.delete_group(non_existent_id)
        assert result is False

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM groups")
        count_after = cursor.fetchone()[0]
        conn.close()

        assert (
            count_before == count_after
        ), "No changes should occur for non-existent group"

    def test_rollback_when_default_group(self, group_manager, temp_db_path):
        """Test that no partial changes occur when trying to delete default group."""
        admins = group_manager.get_group_by_name("admins")
        group_manager.grant_repo_access("test-repo", admins.id, "admin")

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (admins.id,)
        )
        repo_access_before = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM groups WHERE id = ?", (admins.id,))
        group_before = cursor.fetchone()[0]
        conn.close()

        with pytest.raises(DefaultGroupCannotBeDeletedError):
            group_manager.delete_group(admins.id)

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (admins.id,)
        )
        repo_access_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM groups WHERE id = ?", (admins.id,))
        group_after = cursor.fetchone()[0]
        conn.close()

        assert repo_access_before == repo_access_after, "repo_group_access unchanged"
        assert group_before == group_after, "Group should be unchanged"

    def test_rollback_when_group_has_users(self, group_manager, temp_db_path):
        """Test that no partial changes occur when deleting group with users."""
        group = group_manager.create_group("test-rollback", "Test rollback")
        group_manager.grant_repo_access("repo-1", group.id, "admin")
        group_manager.assign_user_to_group("testuser", group.id, "admin")

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (group.id,)
        )
        repo_access_before = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM groups WHERE id = ?", (group.id,))
        group_before = cursor.fetchone()[0]
        conn.close()

        with pytest.raises(GroupHasUsersError):
            group_manager.delete_group(group.id)

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE group_id = ?", (group.id,)
        )
        repo_access_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM groups WHERE id = ?", (group.id,))
        group_after = cursor.fetchone()[0]
        conn.close()

        assert repo_access_before == repo_access_after, "repo_group_access unchanged"
        assert group_before == group_after, "Group should be unchanged"


def _group_exists(db_path: Path, group_id: int) -> bool:
    """Helper to check if a group exists in the database."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()
    exists = bool(row is not None and row[0] > 0)
    conn.close()
    return exists


class TestDeleteGroupTOCTOUProtection:
    """Tests verifying protection against Time-Of-Check-To-Time-Of-Use attacks."""

    def test_concurrent_user_add_during_delete_is_prevented(self, temp_db_path):
        """Test that concurrent user add and delete maintain data integrity."""
        manager = GroupAccessManager(temp_db_path)
        group = manager.create_group("race-test", "Test race condition")
        group_id = group.id

        results = {"delete_result": None, "delete_error": None}
        barrier = threading.Barrier(2, timeout=5)

        def delete_thread():
            try:
                barrier.wait()
                time.sleep(0.01)
                results["delete_result"] = manager.delete_group(group_id)
            except GroupHasUsersError as e:
                results["delete_error"] = e

        def add_user_thread():
            try:
                barrier.wait()
                manager.assign_user_to_group("concurrent-user", group_id, "admin")
            except sqlite3.IntegrityError:
                pass  # Expected if group deleted first (FK constraint)

        t1 = threading.Thread(target=delete_thread)
        t2 = threading.Thread(target=add_user_thread)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # Verify test actually executed
        assert (
            results["delete_result"] is not None or results["delete_error"] is not None
        )

        # Verify data integrity based on outcome
        if results["delete_result"] is True:
            assert not _group_exists(temp_db_path, group_id), "Group should be deleted"
        elif isinstance(results["delete_error"], GroupHasUsersError):
            assert _group_exists(temp_db_path, group_id), "Group should exist"


class TestDeleteGroupLookupWithinTransaction:
    """Tests verifying lookups happen within the same transaction as delete."""

    def test_group_lookup_inside_transaction(self, group_manager, temp_db_path):
        """Test that delete_group() does NOT call get_group or get_user_count separately."""
        group = group_manager.create_group("lookup-test", "Test lookup")

        get_group_calls = []
        get_user_count_calls = []
        original_get_group = group_manager.get_group
        original_get_user_count = group_manager.get_user_count_in_group

        def tracking_get_group(group_id):
            get_group_calls.append(group_id)
            return original_get_group(group_id)

        def tracking_get_user_count(group_id):
            get_user_count_calls.append(group_id)
            return original_get_user_count(group_id)

        with patch.object(group_manager, "get_group", side_effect=tracking_get_group):
            with patch.object(
                group_manager,
                "get_user_count_in_group",
                side_effect=tracking_get_user_count,
            ):
                group_manager.delete_group(group.id)

        assert (
            len(get_group_calls) == 0
        ), f"delete_group() should NOT call get_group(). Found {len(get_group_calls)} calls."
        assert len(get_user_count_calls) == 0, (
            f"delete_group() should NOT call get_user_count_in_group(). "
            f"Found {len(get_user_count_calls)} calls."
        )
