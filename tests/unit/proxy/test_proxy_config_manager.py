"""Unit tests for ProxyConfigManager - TDD Red Phase.

Tests written FIRST to define expected behavior for proxy configuration management.

Story 1.3 - Proxy Configuration Management:
- Load and validate proxy configurations
- Add/remove repositories
- Validate repository paths exist
- Refresh repository list
- Prevent invalid path entries
"""

import json
import pytest
from pathlib import Path

from code_indexer.proxy.config_manager import (
    ProxyConfigManager,
    ProxyConfigError,
    InvalidRepositoryError,
)


class TestProxyConfigManagerConstruction:
    """Tests for ProxyConfigManager construction."""

    def test_proxy_config_manager_requires_proxy_root(self):
        """ProxyConfigManager requires proxy root directory path."""
        with pytest.raises(TypeError):
            ProxyConfigManager()  # Should fail without proxy_root

    def test_proxy_config_manager_accepts_path_object(self, tmp_path):
        """ProxyConfigManager accepts Path object for proxy root."""
        manager = ProxyConfigManager(proxy_root=tmp_path)
        assert manager.proxy_root == tmp_path

    def test_proxy_config_manager_converts_string_to_path(self, tmp_path):
        """ProxyConfigManager converts string path to Path object."""
        manager = ProxyConfigManager(proxy_root=str(tmp_path))
        assert isinstance(manager.proxy_root, Path)
        assert manager.proxy_root == tmp_path


class TestProxyConfigLoading:
    """Tests for loading proxy configuration."""

    def test_load_config_reads_proxy_mode_and_discovered_repos(self, tmp_path):
        """load_config() reads proxy_mode and discovered_repos from config.json."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["repo1", "repo2"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)
        config = manager.load_config()

        assert config.proxy_mode is True
        assert config.discovered_repos == ["repo1", "repo2"]

    def test_load_config_fails_if_not_proxy_mode(self, tmp_path):
        """load_config() fails if proxy_mode is False."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": False, "discovered_repos": []}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)

        with pytest.raises(ProxyConfigError) as exc_info:
            manager.load_config()

        assert "not a proxy" in str(exc_info.value).lower()

    def test_load_config_fails_if_config_missing(self, tmp_path):
        """load_config() fails gracefully if config.json doesn't exist."""
        manager = ProxyConfigManager(proxy_root=tmp_path)

        with pytest.raises(ProxyConfigError) as exc_info:
            manager.load_config()

        assert "not found" in str(exc_info.value).lower()


class TestRepositoryValidation:
    """Tests for validating discovered repository paths."""

    def test_validate_repositories_checks_all_paths_exist(self, tmp_path):
        """validate_repositories() checks that all repository paths exist."""
        # Create config with repository that exists
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        repo1 = tmp_path / "repo1"
        repo1.mkdir()
        (repo1 / ".code-indexer").mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["repo1"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)
        config = manager.load_config()

        # Should not raise exception
        manager.validate_repositories(config)

    def test_validate_repositories_fails_if_repository_missing(self, tmp_path):
        """validate_repositories() fails if repository path doesn't exist."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["nonexistent_repo"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)
        config = manager.load_config()

        with pytest.raises(InvalidRepositoryError) as exc_info:
            manager.validate_repositories(config)

        assert "nonexistent_repo" in str(exc_info.value)

    def test_validate_repositories_checks_code_indexer_directory_exists(self, tmp_path):
        """validate_repositories() verifies .code-indexer directory exists in each repo."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        # Create repository WITHOUT .code-indexer directory
        repo1 = tmp_path / "repo1"
        repo1.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["repo1"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)
        config = manager.load_config()

        with pytest.raises(InvalidRepositoryError) as exc_info:
            manager.validate_repositories(config)

        assert ".code-indexer" in str(exc_info.value).lower()

    def test_validate_repositories_detects_path_escaping_proxy_root(self, tmp_path):
        """validate_repositories() prevents paths that escape proxy root."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["../outside_proxy"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)
        config = manager.load_config()

        with pytest.raises(InvalidRepositoryError) as exc_info:
            manager.validate_repositories(config)

        assert "outside proxy root" in str(exc_info.value).lower()


class TestAddRepository:
    """Tests for adding repositories to proxy configuration."""

    def test_add_repository_appends_to_discovered_repos(self, tmp_path):
        """add_repository() adds repository path to discovered_repos list."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["repo1"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create new repository
        repo2 = tmp_path / "repo2"
        repo2.mkdir()
        (repo2 / ".code-indexer").mkdir()

        manager = ProxyConfigManager(proxy_root=tmp_path)
        manager.add_repository("repo2")

        # Verify config updated
        with open(config_file) as f:
            updated_data = json.load(f)

        assert "repo2" in updated_data["discovered_repos"]
        assert set(updated_data["discovered_repos"]) == {"repo1", "repo2"}

    def test_add_repository_prevents_duplicates(self, tmp_path):
        """add_repository() prevents adding duplicate repository paths."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        repo1 = tmp_path / "repo1"
        repo1.mkdir()
        (repo1 / ".code-indexer").mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["repo1"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)

        # Attempt to add same repository
        with pytest.raises(InvalidRepositoryError) as exc_info:
            manager.add_repository("repo1")

        assert "already exists" in str(exc_info.value).lower()

    def test_add_repository_validates_path_exists(self, tmp_path):
        """add_repository() validates repository path exists before adding."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": []}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)

        with pytest.raises(InvalidRepositoryError) as exc_info:
            manager.add_repository("nonexistent_repo")

        assert "does not exist" in str(exc_info.value).lower()

    def test_add_repository_validates_code_indexer_directory(self, tmp_path):
        """add_repository() validates .code-indexer directory exists."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": []}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create directory WITHOUT .code-indexer
        repo1 = tmp_path / "repo1"
        repo1.mkdir()

        manager = ProxyConfigManager(proxy_root=tmp_path)

        with pytest.raises(InvalidRepositoryError) as exc_info:
            manager.add_repository("repo1")

        assert ".code-indexer" in str(exc_info.value).lower()


class TestRemoveRepository:
    """Tests for removing repositories from proxy configuration."""

    def test_remove_repository_removes_from_discovered_repos(self, tmp_path):
        """remove_repository() removes repository path from discovered_repos list."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {
            "proxy_mode": True,
            "discovered_repos": ["repo1", "repo2", "repo3"],
        }

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)
        manager.remove_repository("repo2")

        # Verify config updated
        with open(config_file) as f:
            updated_data = json.load(f)

        assert "repo2" not in updated_data["discovered_repos"]
        assert set(updated_data["discovered_repos"]) == {"repo1", "repo3"}

    def test_remove_repository_fails_if_not_in_list(self, tmp_path):
        """remove_repository() fails if repository not in discovered_repos."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["repo1"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)

        with pytest.raises(InvalidRepositoryError) as exc_info:
            manager.remove_repository("repo2")

        assert "not found" in str(exc_info.value).lower()


class TestRefreshRepositories:
    """Tests for refreshing repository discovery."""

    def test_refresh_repositories_rediscovers_all_repos(self, tmp_path):
        """refresh_repositories() rediscovers all repositories in proxy root."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        # Initial config with one repo
        config_data = {"proxy_mode": True, "discovered_repos": ["repo1"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create additional repositories
        for i in range(1, 4):
            repo = tmp_path / f"repo{i}"
            repo.mkdir()
            (repo / ".code-indexer").mkdir()

        manager = ProxyConfigManager(proxy_root=tmp_path)
        manager.refresh_repositories()

        # Verify all repos discovered
        with open(config_file) as f:
            updated_data = json.load(f)

        assert set(updated_data["discovered_repos"]) == {"repo1", "repo2", "repo3"}

    def test_refresh_repositories_removes_deleted_repos(self, tmp_path):
        """refresh_repositories() removes repositories that no longer exist."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        # Config lists repo1 and repo2
        config_data = {"proxy_mode": True, "discovered_repos": ["repo1", "repo2"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Only create repo1
        repo1 = tmp_path / "repo1"
        repo1.mkdir()
        (repo1 / ".code-indexer").mkdir()

        manager = ProxyConfigManager(proxy_root=tmp_path)
        manager.refresh_repositories()

        # Verify repo2 removed
        with open(config_file) as f:
            updated_data = json.load(f)

        assert updated_data["discovered_repos"] == ["repo1"]

    def test_refresh_repositories_uses_proxy_initializer_discovery(self, tmp_path):
        """refresh_repositories() uses ProxyInitializer discovery logic."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": []}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create nested repository structure
        nested_repo = tmp_path / "services" / "auth"
        nested_repo.mkdir(parents=True)
        (nested_repo / ".code-indexer").mkdir()

        manager = ProxyConfigManager(proxy_root=tmp_path)
        manager.refresh_repositories()

        # Verify nested repo discovered
        with open(config_file) as f:
            updated_data = json.load(f)

        assert "services/auth" in updated_data["discovered_repos"]


class TestGetRepositories:
    """Tests for getting current repository list."""

    def test_get_repositories_returns_current_list(self, tmp_path):
        """get_repositories() returns current discovered_repos list."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        repos = ["repo1", "repo2", "repo3"]
        config_data = {"proxy_mode": True, "discovered_repos": repos}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)
        result = manager.get_repositories()

        assert result == repos

    def test_get_repositories_returns_copy_not_reference(self, tmp_path):
        """get_repositories() returns copy to prevent external modification."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_data = {"proxy_mode": True, "discovered_repos": ["repo1"]}

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        manager = ProxyConfigManager(proxy_root=tmp_path)
        result1 = manager.get_repositories()
        result2 = manager.get_repositories()

        # Modifying one should not affect the other
        result1.append("modified")

        assert "modified" not in result2
