"""
Tests for group name case-sensitivity bug fix.

Bug: get_group_by_name() uses case-sensitive comparison while create_group() and
update_group() use case-insensitive comparison, causing inconsistent behavior.

Required Fix: get_group_by_name() should use case-insensitive comparison to match
the behavior of create_group() and update_group().
"""

import tempfile
from pathlib import Path

import pytest

from src.code_indexer.server.services.group_access_manager import GroupAccessManager


@pytest.fixture
def group_manager():
    """Create a GroupAccessManager with a temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    manager = GroupAccessManager(db_path)
    yield manager

    # Cleanup
    if db_path.exists():
        db_path.unlink()


class TestGetGroupByNameCaseSensitivity:
    """Tests for case-insensitive get_group_by_name() behavior."""

    def test_get_group_by_name_exact_case_match(self, group_manager):
        """Test that get_group_by_name() finds group with exact case match."""
        # Create a custom group with mixed case
        group = group_manager.create_group("TestGroup", "Test group description")

        # Should find with exact case
        found = group_manager.get_group_by_name("TestGroup")

        assert found is not None
        assert found.id == group.id
        assert found.name == "TestGroup"

    def test_get_group_by_name_lowercase_finds_mixed_case_group(self, group_manager):
        """Test that get_group_by_name() finds group using lowercase name."""
        # Create a custom group with mixed case
        group = group_manager.create_group("TestGroup", "Test group description")

        # Should find with lowercase (case-insensitive)
        found = group_manager.get_group_by_name("testgroup")

        assert found is not None, "Should find group with lowercase name"
        assert found.id == group.id
        assert found.name == "TestGroup"  # Original case preserved

    def test_get_group_by_name_uppercase_finds_mixed_case_group(self, group_manager):
        """Test that get_group_by_name() finds group using uppercase name."""
        # Create a custom group with mixed case
        group = group_manager.create_group("TestGroup", "Test group description")

        # Should find with uppercase (case-insensitive)
        found = group_manager.get_group_by_name("TESTGROUP")

        assert found is not None, "Should find group with uppercase name"
        assert found.id == group.id
        assert found.name == "TestGroup"  # Original case preserved

    def test_get_group_by_name_different_case_finds_lowercase_group(
        self, group_manager
    ):
        """Test that get_group_by_name() finds lowercase group with any case."""
        # Create a group with lowercase name
        group = group_manager.create_group("mygroup", "Lowercase group")

        # Should find with different case variations
        found_mixed = group_manager.get_group_by_name("MyGroup")
        found_upper = group_manager.get_group_by_name("MYGROUP")

        assert found_mixed is not None, "Should find lowercase group with mixed case"
        assert found_upper is not None, "Should find lowercase group with uppercase"
        assert found_mixed.id == group.id
        assert found_upper.id == group.id

    def test_get_group_by_name_default_group_case_insensitive(self, group_manager):
        """Test that default groups can be found case-insensitively."""
        # Default groups are created as lowercase (admins, powerusers, users)

        # Find with different case variations
        admins_exact = group_manager.get_group_by_name("admins")
        admins_upper = group_manager.get_group_by_name("ADMINS")
        admins_mixed = group_manager.get_group_by_name("Admins")

        assert admins_exact is not None
        assert admins_upper is not None, "Should find 'admins' with uppercase"
        assert admins_mixed is not None, "Should find 'admins' with mixed case"

        # All should be the same group
        assert admins_exact.id == admins_upper.id
        assert admins_exact.id == admins_mixed.id

    def test_get_group_by_name_returns_none_for_nonexistent(self, group_manager):
        """Test that get_group_by_name() returns None for non-existent groups."""
        found = group_manager.get_group_by_name("NonExistentGroup")
        assert found is None

    def test_consistency_between_create_and_get(self, group_manager):
        """Test that create_group() and get_group_by_name() behave consistently.

        If create_group() rejects 'testgroup' because 'TestGroup' exists
        (case-insensitive check), then get_group_by_name('testgroup') should
        find 'TestGroup' (case-insensitive lookup).
        """
        # Create with mixed case
        group_manager.create_group("TestGroup", "Original")

        # create_group() should reject duplicate (case-insensitive)
        with pytest.raises(ValueError, match="already exists"):
            group_manager.create_group("testgroup", "Duplicate")

        # get_group_by_name() should find with any case (same behavior)
        found = group_manager.get_group_by_name("testgroup")
        assert (
            found is not None
        ), "get_group_by_name() should be case-insensitive to match create_group()"
        assert found.name == "TestGroup"

    def test_auto_assign_golden_repo_works_with_case_variants(self, group_manager):
        """Test auto_assign_golden_repo() works regardless of group name case.

        auto_assign_golden_repo() calls get_group_by_name('admins') and
        get_group_by_name('powerusers'), which should work even if the default
        groups were somehow created with different casing.
        """
        # auto_assign_golden_repo relies on get_group_by_name internally
        # This test verifies the integration works correctly

        # Get initial group repo list
        admins = group_manager.get_group_by_name("admins")
        powerusers = group_manager.get_group_by_name("powerusers")

        assert admins is not None
        assert powerusers is not None

        # Auto-assign a repo
        group_manager.auto_assign_golden_repo("test-repo")

        # Verify both groups got access
        admins_repos = group_manager.get_group_repos(admins.id)
        powerusers_repos = group_manager.get_group_repos(powerusers.id)

        assert "test-repo" in admins_repos
        assert "test-repo" in powerusers_repos
