"""End-to-End tests for manual proxy configuration editing.

Tests the complete workflow of manually editing proxy configuration files
and verifying that changes take effect on next load.

Story 1.3 - Proxy Configuration Management:
AC #4: Configuration file can be manually edited without breaking functionality
AC #5: Configuration changes take effect immediately on next command
"""

import json
import pytest

from code_indexer.proxy.proxy_initializer import ProxyInitializer
from code_indexer.proxy.config_manager import ProxyConfigManager


class TestManualProxyConfigEditingWorkflow:
    """E2E tests for manual editing workflow."""

    def test_user_manually_adds_repository_via_json_edit(self, tmp_path):
        """Complete workflow: initialize proxy, manually edit JSON, verify changes loaded.

        Simulates user workflow:
        1. Initialize proxy mode
        2. Manually edit config.json to add repository
        3. Load configuration and verify manual changes respected
        """
        # Step 1: Initialize proxy mode
        proxy_root = tmp_path / "proxy_root"
        proxy_root.mkdir()

        initializer = ProxyInitializer(proxy_root)
        initializer.initialize()

        # Create repository manually (user creates new repo directory)
        new_repo = proxy_root / "new_service"
        new_repo.mkdir()
        (new_repo / ".code-indexer").mkdir()

        # Step 2: User manually edits config.json
        config_file = proxy_root / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        # User adds new repository manually
        config_data["discovered_repos"].append("new_service")

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        # Step 3: Verify changes take effect on next load
        manager = ProxyConfigManager(proxy_root)
        repos = manager.get_repositories()

        assert "new_service" in repos

    def test_user_manually_removes_repository_via_json_edit(self, tmp_path):
        """User manually removes repository from discovered_repos list.

        Workflow:
        1. Initialize with multiple repositories
        2. User manually removes one from JSON
        3. Verify removal reflected in loaded config
        """
        # Step 1: Initialize with repositories
        proxy_root = tmp_path / "proxy_root"
        proxy_root.mkdir()

        # Create multiple repositories
        repos = ["repo1", "repo2", "repo3"]
        for repo_name in repos:
            repo_dir = proxy_root / repo_name
            repo_dir.mkdir()
            (repo_dir / ".code-indexer").mkdir()

        initializer = ProxyInitializer(proxy_root)
        initializer.initialize()

        # Step 2: User manually removes repo2
        config_file = proxy_root / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        config_data["discovered_repos"].remove("repo2")

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        # Step 3: Verify removal respected
        manager = ProxyConfigManager(proxy_root)
        current_repos = manager.get_repositories()

        assert len(current_repos) == 2
        assert "repo2" not in current_repos
        assert "repo1" in current_repos
        assert "repo3" in current_repos

    def test_user_manually_reorders_repositories_via_json_edit(self, tmp_path):
        """User manually reorders repositories and order is preserved.

        Workflow:
        1. Initialize with repositories in alphabetical order
        2. User manually reorders in JSON
        3. Verify custom order preserved
        """
        # Step 1: Initialize
        proxy_root = tmp_path / "proxy_root"
        proxy_root.mkdir()

        repos = ["alpha", "beta", "gamma"]
        for repo_name in repos:
            repo_dir = proxy_root / repo_name
            repo_dir.mkdir()
            (repo_dir / ".code-indexer").mkdir()

        initializer = ProxyInitializer(proxy_root)
        initializer.initialize()

        # Step 2: User manually reorders to custom priority
        config_file = proxy_root / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        # User wants gamma first, then alpha, then beta
        config_data["discovered_repos"] = ["gamma", "alpha", "beta"]

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        # Step 3: Verify custom order preserved
        manager = ProxyConfigManager(proxy_root)
        current_repos = manager.get_repositories()

        assert current_repos == ["gamma", "alpha", "beta"]

    def test_manual_edit_survives_validation(self, tmp_path):
        """Manual edits pass validation when repositories are valid.

        Workflow:
        1. Initialize proxy
        2. Create new repository
        3. Manually add to config.json
        4. Run validation - should pass
        """
        # Step 1: Initialize
        proxy_root = tmp_path / "proxy_root"
        proxy_root.mkdir()

        initializer = ProxyInitializer(proxy_root)
        initializer.initialize()

        # Step 2: Create new repository
        new_repo = proxy_root / "services" / "api"
        new_repo.mkdir(parents=True)
        (new_repo / ".code-indexer").mkdir()

        # Step 3: Manually add to config
        config_file = proxy_root / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        config_data["discovered_repos"].append("services/api")

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        # Step 4: Validation should pass
        manager = ProxyConfigManager(proxy_root)
        config = manager.load_config()

        # Should not raise exception
        manager.validate_repositories(config)

    def test_manual_edit_with_invalid_path_caught_by_validation(self, tmp_path):
        """Manual addition of invalid path is caught by validation.

        Workflow:
        1. Initialize proxy
        2. User manually adds nonexistent repository
        3. Validation detects error
        """
        # Step 1: Initialize
        proxy_root = tmp_path / "proxy_root"
        proxy_root.mkdir()

        initializer = ProxyInitializer(proxy_root)
        initializer.initialize()

        # Step 2: User manually adds nonexistent repo (mistake)
        config_file = proxy_root / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        config_data["discovered_repos"].append("nonexistent_service")

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        # Step 3: Validation catches error
        from code_indexer.proxy.config_manager import InvalidRepositoryError

        manager = ProxyConfigManager(proxy_root)
        config = manager.load_config()

        with pytest.raises(InvalidRepositoryError) as exc_info:
            manager.validate_repositories(config)

        assert "nonexistent_service" in str(exc_info.value)

    def test_changes_take_effect_immediately_on_next_command(self, tmp_path):
        """Configuration changes take effect on next command invocation.

        Simulates multiple command invocations:
        1. First command: get repositories
        2. Manual edit
        3. Second command: get repositories (new instance)
        4. Verify changes reflected
        """
        # Setup
        proxy_root = tmp_path / "proxy_root"
        proxy_root.mkdir()

        repo1 = proxy_root / "repo1"
        repo1.mkdir()
        (repo1 / ".code-indexer").mkdir()

        initializer = ProxyInitializer(proxy_root)
        initializer.initialize()

        # First command invocation
        manager1 = ProxyConfigManager(proxy_root)
        repos_before = manager1.get_repositories()
        assert len(repos_before) == 1

        # Manual edit between commands
        repo2 = proxy_root / "repo2"
        repo2.mkdir()
        (repo2 / ".code-indexer").mkdir()

        config_file = proxy_root / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        config_data["discovered_repos"].append("repo2")

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        # Second command invocation (new instance simulates new command)
        manager2 = ProxyConfigManager(proxy_root)
        repos_after = manager2.get_repositories()

        # Changes should be immediately visible
        assert len(repos_after) == 2
        assert "repo2" in repos_after

    def test_refresh_respects_prior_manual_additions(self, tmp_path):
        """Refresh operation preserves manually added repositories.

        Workflow:
        1. Initialize with auto-discovered repos
        2. Manually add additional repository
        3. Run refresh
        4. Verify both auto-discovered and manually-added repos present
        """
        # Step 1: Initialize
        proxy_root = tmp_path / "proxy_root"
        proxy_root.mkdir()

        auto_repo = proxy_root / "auto_discovered"
        auto_repo.mkdir()
        (auto_repo / ".code-indexer").mkdir()

        initializer = ProxyInitializer(proxy_root)
        initializer.initialize()

        # Step 2: Manually add repository
        manual_repo = proxy_root / "manually_added"
        manual_repo.mkdir()
        (manual_repo / ".code-indexer").mkdir()

        config_file = proxy_root / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        config_data["discovered_repos"].append("manually_added")

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        # Step 3: Run refresh
        manager = ProxyConfigManager(proxy_root)
        manager.refresh_repositories()

        # Step 4: Both should be present
        repos = manager.get_repositories()
        assert "auto_discovered" in repos
        assert "manually_added" in repos

    def test_proxy_mode_flag_cannot_be_manually_disabled(self, tmp_path):
        """Manually disabling proxy_mode flag causes load to fail.

        Workflow:
        1. Initialize proxy
        2. User manually sets proxy_mode to false
        3. Load should fail with clear error
        """
        # Step 1: Initialize
        proxy_root = tmp_path / "proxy_root"
        proxy_root.mkdir()

        initializer = ProxyInitializer(proxy_root)
        initializer.initialize()

        # Step 2: User manually disables proxy_mode
        config_file = proxy_root / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        config_data["proxy_mode"] = False

        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        # Step 3: Load should fail
        from code_indexer.proxy.config_manager import ProxyConfigError

        manager = ProxyConfigManager(proxy_root)

        with pytest.raises(ProxyConfigError) as exc_info:
            manager.load_config()

        assert "not a proxy" in str(exc_info.value).lower()
