"""
Unit tests for Repository-to-Group Access Mapping.

Story #706: Repository-to-Group Access Mapping with Auto-Assignment

This file covers:
- repo_group_access table schema
- AC2: cidx-meta Always Accessible to All Groups

Additional acceptance criteria are tested in separate files.
TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path

from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
    CidxMetaCannotBeRevokedError,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


class TestRepoGroupAccessSchema:
    """Tests for repo_group_access table schema."""

    def test_repo_group_access_table_exists(self, temp_db_path):
        """Test that repo_group_access table is created on initialization."""
        _manager = GroupAccessManager(temp_db_path)  # noqa: F841

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='repo_group_access'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None, "repo_group_access table should exist"
        assert result[0] == "repo_group_access"

    def test_repo_group_access_table_has_correct_columns(self, temp_db_path):
        """Test that repo_group_access table has all required columns."""
        _manager = GroupAccessManager(temp_db_path)  # noqa: F841

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(repo_group_access)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        assert "repo_name" in columns
        assert "group_id" in columns
        assert "granted_at" in columns
        assert "granted_by" in columns

    def test_repo_group_access_primary_key_composite(self, temp_db_path):
        """Test that repo_group_access has composite primary key."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        # Insert first record
        manager.grant_repo_access("test-repo", admins.id, "admin_user")

        # Attempting to insert duplicate should be idempotent
        result = manager.grant_repo_access("test-repo", admins.id, "admin_user")

        # Should return False for duplicate (already exists)
        assert result is False


class TestCidxMetaAlwaysAccessible:
    """Tests for AC2: cidx-meta Always Accessible to All Groups."""

    def test_cidx_meta_included_in_admins_repos(self, temp_db_path):
        """Test that cidx-meta is always included in admins group repos."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        repos = manager.get_group_repos(admins.id)

        assert "cidx-meta" in repos

    def test_cidx_meta_included_in_powerusers_repos(self, temp_db_path):
        """Test that cidx-meta is always included in powerusers group repos."""
        manager = GroupAccessManager(temp_db_path)
        powerusers = manager.get_group_by_name("powerusers")

        repos = manager.get_group_repos(powerusers.id)

        assert "cidx-meta" in repos

    def test_cidx_meta_included_in_users_repos(self, temp_db_path):
        """Test that cidx-meta is always included in users group repos."""
        manager = GroupAccessManager(temp_db_path)
        users = manager.get_group_by_name("users")

        repos = manager.get_group_repos(users.id)

        assert "cidx-meta" in repos

    def test_cidx_meta_included_in_custom_group_repos(self, temp_db_path):
        """Test that cidx-meta is always included in custom group repos."""
        manager = GroupAccessManager(temp_db_path)
        custom_group = manager.create_group("custom", "Custom group")

        repos = manager.get_group_repos(custom_group.id)

        assert "cidx-meta" in repos

    def test_cidx_meta_cannot_be_revoked(self, temp_db_path):
        """Test that cidx-meta access cannot be revoked."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        with pytest.raises(CidxMetaCannotBeRevokedError) as exc_info:
            manager.revoke_repo_access("cidx-meta", admins.id)

        assert "cidx-meta" in str(exc_info.value).lower()

    def test_cidx_meta_not_stored_in_repo_group_access(self, temp_db_path):
        """Test that cidx-meta access is implicit (not stored in table)."""
        _manager = GroupAccessManager(temp_db_path)  # noqa: F841

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM repo_group_access WHERE repo_name = 'cidx-meta'"
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "cidx-meta should not be stored in repo_group_access"
