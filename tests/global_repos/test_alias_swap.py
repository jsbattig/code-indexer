"""
Tests for AliasManager.swap_alias() - atomic alias swapping.

Tests AC2 Technical Requirements:
- Atomic write of alias pointer file (write temp, rename)
- Alias pointer includes: target path, previous path, version timestamp
- Swap completes in <100ms
- Old index path preserved in alias for cleanup tracking
"""

import json
import pytest
import time
from code_indexer.global_repos.alias_manager import AliasManager


class TestAliasSwap:
    """Test suite for alias swapping functionality."""

    def test_swap_alias_updates_target_path(self, tmp_path):
        """
        Test that swap_alias() updates the target path atomically.

        AC2: New queries immediately use the new index
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        # Create initial alias
        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        # Swap to new path
        new_path = str(tmp_path / "v_5678")
        mgr.swap_alias("test-global", new_path, old_path)

        # Verify target updated
        current_target = mgr.read_alias("test-global")
        assert current_target == new_path

    def test_swap_alias_preserves_previous_path(self, tmp_path):
        """
        Test that swap_alias() preserves previous path for cleanup.

        AC2: Old index path preserved in alias for cleanup tracking
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        new_path = str(tmp_path / "v_5678")
        mgr.swap_alias("test-global", new_path, old_path)

        # Read alias file directly to verify previous path
        alias_file = aliases_dir / "test-global.json"
        with open(alias_file) as f:
            alias_data = json.load(f)

        assert alias_data["target_path"] == new_path
        assert alias_data["previous_path"] == old_path

    def test_swap_alias_includes_swap_timestamp(self, tmp_path):
        """
        Test that swap_alias() includes swap timestamp.

        AC2: Alias pointer includes version timestamp
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        before_swap = time.time()
        new_path = str(tmp_path / "v_5678")
        mgr.swap_alias("test-global", new_path, old_path)
        after_swap = time.time()

        # Read alias file
        alias_file = aliases_dir / "test-global.json"
        with open(alias_file) as f:
            alias_data = json.load(f)

        assert "swapped_at" in alias_data

        # Verify timestamp is reasonable (not ancient or future)
        from datetime import datetime

        swap_time = datetime.fromisoformat(alias_data["swapped_at"])
        swap_timestamp = swap_time.timestamp()

        assert before_swap <= swap_timestamp <= after_swap

    def test_swap_alias_completes_quickly(self, tmp_path):
        """
        Test that swap_alias() completes in <100ms.

        AC2: Swap completes in <100ms
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        new_path = str(tmp_path / "v_5678")

        # Measure swap time
        start = time.time()
        mgr.swap_alias("test-global", new_path, old_path)
        duration = time.time() - start

        # Should complete in <100ms
        assert duration < 0.1, f"Swap took {duration * 1000:.1f}ms, expected <100ms"

    def test_swap_alias_is_atomic(self, tmp_path):
        """
        Test that swap_alias() uses atomic write (temp + rename).

        AC2: Atomic write of alias pointer file
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        new_path = str(tmp_path / "v_5678")
        mgr.swap_alias("test-global", new_path, old_path)

        # Verify no temp files left behind
        temp_files = list(aliases_dir.glob(".test-global_*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up"

    def test_swap_alias_validates_old_path(self, tmp_path):
        """
        Test that swap_alias() validates old_path matches current target.

        Safety: Prevent accidental swaps with wrong old path
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        # Try to swap with wrong old path
        new_path = str(tmp_path / "v_5678")
        wrong_old_path = str(tmp_path / "v_9999")

        with pytest.raises(ValueError, match="Current target.*does not match"):
            mgr.swap_alias("test-global", new_path, wrong_old_path)

    def test_swap_alias_raises_if_alias_not_exists(self, tmp_path):
        """
        Test that swap_alias() raises error if alias doesn't exist.

        Safety: Fail fast on non-existent aliases
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        new_path = str(tmp_path / "v_5678")
        old_path = str(tmp_path / "v_1234")

        with pytest.raises(RuntimeError, match="Alias.*does not exist"):
            mgr.swap_alias("nonexistent-global", new_path, old_path)

    def test_swap_alias_preserves_other_metadata(self, tmp_path):
        """
        Test that swap_alias() preserves created_at and repo_name.

        Data integrity: Don't lose metadata during swap
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path, repo_name="my-repo")

        # Read original metadata
        alias_file = aliases_dir / "test-global.json"
        with open(alias_file) as f:
            original_data = json.load(f)

        original_created_at = original_data["created_at"]
        original_repo_name = original_data["repo_name"]

        # Swap
        new_path = str(tmp_path / "v_5678")
        mgr.swap_alias("test-global", new_path, old_path)

        # Verify metadata preserved
        with open(alias_file) as f:
            swapped_data = json.load(f)

        assert swapped_data["created_at"] == original_created_at
        assert swapped_data["repo_name"] == original_repo_name

    def test_read_alias_after_swap_returns_new_path(self, tmp_path):
        """
        Test that read_alias() returns new path after swap.

        Integration: Verify read_alias() works with swapped alias
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        new_path = str(tmp_path / "v_5678")
        mgr.swap_alias("test-global", new_path, old_path)

        # read_alias() should return new path
        target = mgr.read_alias("test-global")
        assert target == new_path

    def test_get_previous_path_returns_old_path(self, tmp_path):
        """
        Test that get_previous_path() returns the old path after swap.

        New method for cleanup manager to get previous path
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        new_path = str(tmp_path / "v_5678")
        mgr.swap_alias("test-global", new_path, old_path)

        # New method: get_previous_path()
        previous = mgr.get_previous_path("test-global")
        assert previous == old_path

    def test_get_previous_path_returns_none_if_no_swap(self, tmp_path):
        """
        Test that get_previous_path() returns None if no swap occurred.

        Edge case: Alias created but never swapped
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        old_path = str(tmp_path / "v_1234")
        mgr.create_alias("test-global", old_path)

        # No swap yet, should return None
        previous = mgr.get_previous_path("test-global")
        assert previous is None

    def test_swap_alias_multiple_times_tracks_latest_previous(self, tmp_path):
        """
        Test that multiple swaps track the latest previous path.

        Scenario: Multiple refreshes in sequence
        """
        aliases_dir = tmp_path / "aliases"
        mgr = AliasManager(str(aliases_dir))

        path1 = str(tmp_path / "v_1111")
        mgr.create_alias("test-global", path1)

        # First swap
        path2 = str(tmp_path / "v_2222")
        mgr.swap_alias("test-global", path2, path1)

        # Second swap
        path3 = str(tmp_path / "v_3333")
        mgr.swap_alias("test-global", path3, path2)

        # Current target should be path3
        assert mgr.read_alias("test-global") == path3

        # Previous should be path2 (not path1)
        assert mgr.get_previous_path("test-global") == path2
