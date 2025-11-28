"""
Tests for automatic global activation on golden repo registration.

Tests AC1: Automatic Global Activation on Registration
- Hook into golden repo registration completion
- Create alias pointer JSON file atomically
- Register in global registry
- Handle failures gracefully
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

from code_indexer.global_repos.global_registry import GlobalRegistry
from code_indexer.global_repos.alias_manager import AliasManager
from code_indexer.global_repos.global_activation import GlobalActivator


class TestGlobalRegistry:
    """Test GlobalRegistry for managing global repo metadata."""

    def test_registry_initialization_creates_directory(self):
        """Test that registry initialization creates the golden-repos directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"

            _ = GlobalRegistry(str(golden_repos_dir))

            assert golden_repos_dir.exists()
            assert (golden_repos_dir / "aliases").exists()
            assert (golden_repos_dir / "global_registry.json").exists()

    def test_registry_loads_empty_on_first_run(self):
        """Test that registry loads empty on first run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"

            registry = GlobalRegistry(str(golden_repos_dir))

            assert registry.list_global_repos() == []

    def test_register_global_repo_adds_metadata(self):
        """Test that registering a global repo adds metadata to registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            registry.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/repo.git",
                index_path="/path/to/index",
            )

            global_repos = registry.list_global_repos()
            assert len(global_repos) == 1
            assert global_repos[0]["repo_name"] == "test-repo"
            assert global_repos[0]["alias_name"] == "test-repo-global"
            assert global_repos[0]["repo_url"] == "https://github.com/test/repo.git"
            assert global_repos[0]["index_path"] == "/path/to/index"
            assert "created_at" in global_repos[0]
            assert "last_refresh" in global_repos[0]

    def test_registry_persists_across_instances(self):
        """Test that registry persists across instances (AC3)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"

            # First instance registers a repo
            registry1 = GlobalRegistry(str(golden_repos_dir))
            registry1.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/repo.git",
                index_path="/path/to/index",
            )

            # Second instance should load the same data
            registry2 = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry2.list_global_repos()

            assert len(global_repos) == 1
            assert global_repos[0]["repo_name"] == "test-repo"

    def test_registry_atomic_write_prevents_corruption(self):
        """Test that registry uses atomic writes to prevent corruption (AC3)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            # Register first repo
            registry.register_global_repo(
                repo_name="repo1",
                alias_name="repo1-global",
                repo_url="https://github.com/test/repo1.git",
                index_path="/path/to/index1",
            )

            # Simulate atomic write by checking no .tmp files left behind
            registry_file = Path(golden_repos_dir) / "global_registry.json"
            tmp_files = list(Path(golden_repos_dir).glob("*.tmp"))

            assert registry_file.exists()
            assert len(tmp_files) == 0  # No temp files should remain

    def test_unregister_global_repo_removes_metadata(self):
        """Test that unregistering a global repo removes it from registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            registry.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/repo.git",
                index_path="/path/to/index",
            )

            registry.unregister_global_repo("test-repo-global")

            assert registry.list_global_repos() == []

    def test_get_global_repo_returns_metadata(self):
        """Test that get_global_repo returns correct metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            registry.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/repo.git",
                index_path="/path/to/index",
            )

            repo_metadata = registry.get_global_repo("test-repo-global")

            assert repo_metadata is not None
            assert repo_metadata["repo_name"] == "test-repo"
            assert repo_metadata["alias_name"] == "test-repo-global"

    def test_get_global_repo_returns_none_for_nonexistent(self):
        """Test that get_global_repo returns None for nonexistent repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            repo_metadata = registry.get_global_repo("nonexistent-global")

            assert repo_metadata is None


class TestGlobalRegistryAdditionalCoverage:
    """Additional tests for GlobalRegistry coverage."""

    def test_update_refresh_timestamp(self):
        """Test updating refresh timestamp for a global repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            # Register a repo
            registry.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/repo.git",
                index_path="/path/to/index",
            )

            # Get initial timestamp
            initial_repo = registry.get_global_repo("test-repo-global")
            initial_timestamp = initial_repo["last_refresh"]

            # Wait a tiny bit to ensure timestamp changes
            import time

            time.sleep(0.01)

            # Update timestamp
            registry.update_refresh_timestamp("test-repo-global")

            # Verify timestamp was updated
            updated_repo = registry.get_global_repo("test-repo-global")
            assert updated_repo["last_refresh"] != initial_timestamp


class TestAliasManager:
    """Test AliasManager for managing alias pointer files."""

    def test_create_alias_creates_json_file(self):
        """Test that creating an alias creates a JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            alias_manager.create_alias(
                alias_name="test-repo-global", target_path="/path/to/index"
            )

            alias_file = aliases_dir / "test-repo-global.json"
            assert alias_file.exists()

    def test_alias_file_contains_correct_structure(self):
        """Test that alias file contains correct JSON structure (AC1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            alias_manager.create_alias(
                alias_name="test-repo-global", target_path="/path/to/index"
            )

            alias_file = aliases_dir / "test-repo-global.json"
            with open(alias_file) as f:
                alias_data = json.load(f)

            assert "target_path" in alias_data
            assert alias_data["target_path"] == "/path/to/index"
            assert "created_at" in alias_data
            assert "last_refresh" in alias_data
            assert "repo_name" in alias_data

    def test_read_alias_returns_target_path(self):
        """Test that reading an alias returns the target path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            alias_manager.create_alias(
                alias_name="test-repo-global", target_path="/path/to/index"
            )

            target_path = alias_manager.read_alias("test-repo-global")

            assert target_path == "/path/to/index"

    def test_read_alias_returns_none_for_nonexistent(self):
        """Test that reading nonexistent alias returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            target_path = alias_manager.read_alias("nonexistent-global")

            assert target_path is None

    def test_delete_alias_removes_file(self):
        """Test that deleting an alias removes the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            alias_manager.create_alias(
                alias_name="test-repo-global", target_path="/path/to/index"
            )

            alias_manager.delete_alias("test-repo-global")

            alias_file = aliases_dir / "test-repo-global.json"
            assert not alias_file.exists()

    def test_alias_creation_is_atomic(self):
        """Test that alias creation is atomic (AC1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            alias_manager.create_alias(
                alias_name="test-repo-global", target_path="/path/to/index"
            )

            # Check no temp files remain
            tmp_files = list(aliases_dir.glob("*.tmp"))
            assert len(tmp_files) == 0

    def test_alias_exists(self):
        """Test checking if an alias exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            # Should not exist initially
            assert not alias_manager.alias_exists("test-repo-global")

            # Create alias
            alias_manager.create_alias(
                alias_name="test-repo-global", target_path="/path/to/index"
            )

            # Should exist now
            assert alias_manager.alias_exists("test-repo-global")

    def test_update_refresh_timestamp(self):
        """Test updating refresh timestamp for an alias."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            # Create alias
            alias_manager.create_alias(
                alias_name="test-repo-global", target_path="/path/to/index"
            )

            # Read initial timestamp
            alias_file = aliases_dir / "test-repo-global.json"
            with open(alias_file) as f:
                initial_data = json.load(f)
                initial_timestamp = initial_data["last_refresh"]

            # Wait a tiny bit
            import time

            time.sleep(0.01)

            # Update timestamp
            alias_manager.update_refresh_timestamp("test-repo-global")

            # Read updated timestamp
            with open(alias_file) as f:
                updated_data = json.load(f)
                updated_timestamp = updated_data["last_refresh"]

            # Should be different
            assert updated_timestamp != initial_timestamp

    def test_read_alias_handles_corrupted_file(self):
        """Test that read_alias handles corrupted JSON gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            # Create a corrupted alias file
            alias_file = aliases_dir / "corrupted-global.json"
            alias_file.write_text("not valid json {{{")

            # Should return None for corrupted file
            result = alias_manager.read_alias("corrupted-global")
            assert result is None

    def test_update_refresh_timestamp_nonexistent_alias(self):
        """Test that updating timestamp for nonexistent alias raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            # Should raise error for nonexistent alias
            with pytest.raises(RuntimeError, match="does not exist"):
                alias_manager.update_refresh_timestamp("nonexistent-global")

    def test_delete_alias_nonexistent(self):
        """Test deleting nonexistent alias doesn't raise error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aliases_dir = Path(tmpdir) / "aliases"
            aliases_dir.mkdir()
            alias_manager = AliasManager(str(aliases_dir))

            # Should not raise error for nonexistent alias
            alias_manager.delete_alias("nonexistent-global")  # Should succeed silently


class TestGlobalActivator:
    """Test GlobalActivator for orchestrating global activation."""

    def test_activate_creates_alias_and_registers(self):
        """Test that activation creates alias and registers in registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            activator = GlobalActivator(str(golden_repos_dir))

            activator.activate_golden_repo(
                repo_name="test-repo",
                repo_url="https://github.com/test/repo.git",
                clone_path=str(Path(tmpdir) / "clone"),
            )

            # Check alias was created
            alias_file = golden_repos_dir / "aliases" / "test-repo-global.json"
            assert alias_file.exists()

            # Check registry was updated
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry.list_global_repos()
            assert len(global_repos) == 1
            assert global_repos[0]["repo_name"] == "test-repo"

    def test_activate_uses_correct_alias_naming(self):
        """Test that activation uses {repo-name}-global naming (AC1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            activator = GlobalActivator(str(golden_repos_dir))

            activator.activate_golden_repo(
                repo_name="my-test-repo",
                repo_url="https://github.com/test/repo.git",
                clone_path=str(Path(tmpdir) / "clone"),
            )

            # Check alias naming
            alias_file = golden_repos_dir / "aliases" / "my-test-repo-global.json"
            assert alias_file.exists()

    def test_activate_failure_does_not_create_partial_state(self):
        """Test that activation failure doesn't create partial state (AC1, AC4)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            activator = GlobalActivator(str(golden_repos_dir))

            # Make aliases directory read-only to force failure
            # (GlobalActivator already created it)
            aliases_dir = golden_repos_dir / "aliases"
            aliases_dir.chmod(0o444)

            try:
                activator.activate_golden_repo(
                    repo_name="test-repo",
                    repo_url="https://github.com/test/repo.git",
                    clone_path=str(Path(tmpdir) / "clone"),
                )
            except Exception:
                pass  # Expected to fail

            # Restore permissions for cleanup
            aliases_dir.chmod(0o755)

            # Check no partial state exists
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry.list_global_repos()
            assert len(global_repos) == 0  # Should not have registered if alias failed

    def test_activate_logs_clear_error_on_failure(self):
        """Test that activation logs clear error on failure (AC4)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            activator = GlobalActivator(str(golden_repos_dir))

            # Make aliases directory read-only to force failure
            # (GlobalActivator already created it)
            aliases_dir = golden_repos_dir / "aliases"
            aliases_dir.chmod(0o444)

            with patch(
                "code_indexer.global_repos.global_activation.logger.error"
            ) as mock_error:
                try:
                    activator.activate_golden_repo(
                        repo_name="test-repo",
                        repo_url="https://github.com/test/repo.git",
                        clone_path=str(Path(tmpdir) / "clone"),
                    )
                except Exception:
                    pass

                # Restore permissions
                aliases_dir.chmod(0o755)

                # Check error was logged (could be activation or cleanup error)
                assert mock_error.called
                # Check any of the error calls contains failure message
                error_messages = [
                    str(call[0][0]).lower() for call in mock_error.call_args_list
                ]
                assert any("failed" in msg for msg in error_messages)

    def test_deactivate_golden_repo(self):
        """Test deactivating a golden repo removes alias and registry entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            activator = GlobalActivator(str(golden_repos_dir))

            # First activate
            activator.activate_golden_repo(
                repo_name="test-repo",
                repo_url="https://github.com/test/repo.git",
                clone_path=str(Path(tmpdir) / "clone"),
            )

            # Verify it's active
            assert activator.is_globally_active("test-repo")

            # Deactivate
            activator.deactivate_golden_repo("test-repo")

            # Verify it's not active anymore
            assert not activator.is_globally_active("test-repo")

            # Verify alias is gone
            alias_file = golden_repos_dir / "aliases" / "test-repo-global.json"
            assert not alias_file.exists()

    def test_is_globally_active(self):
        """Test checking if a repo is globally active."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            activator = GlobalActivator(str(golden_repos_dir))

            # Should not be active initially
            assert not activator.is_globally_active("test-repo")

            # Activate
            activator.activate_golden_repo(
                repo_name="test-repo",
                repo_url="https://github.com/test/repo.git",
                clone_path=str(Path(tmpdir) / "clone"),
            )

            # Should be active now
            assert activator.is_globally_active("test-repo")

    def test_get_global_alias_name(self):
        """Test getting the global alias name for a repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            activator = GlobalActivator(str(golden_repos_dir))

            # Test naming convention
            assert activator.get_global_alias_name("test-repo") == "test-repo-global"
            assert (
                activator.get_global_alias_name("my-cool-repo") == "my-cool-repo-global"
            )

    def test_deactivate_error_handling(self):
        """Test that deactivation errors are handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            activator = GlobalActivator(str(golden_repos_dir))

            # Try to deactivate non-existent repo
            # Should raise GlobalActivationError but not crash

            # Deactivating non-existent repo should not raise error (it's idempotent)
            # Just verify it handles it gracefully
            activator.deactivate_golden_repo("nonexistent-repo")  # Should succeed
