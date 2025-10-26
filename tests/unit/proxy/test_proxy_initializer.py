"""Unit tests for ProxyInitializer - TDD Red Phase.

Tests written FIRST to define expected behavior for proxy mode initialization.
"""

import json
import pytest
from pathlib import Path

from code_indexer.proxy.proxy_initializer import (
    ProxyInitializer,
    ProxyInitializationError,
    NestedProxyError,
)


class TestProxyInitializerConstruction:
    """Tests for ProxyInitializer construction and basic setup."""

    def test_proxy_initializer_requires_target_directory(self):
        """ProxyInitializer must be created with a target directory path."""
        # EXPECTED: Constructor accepts a Path object
        with pytest.raises(TypeError):
            ProxyInitializer()  # Should fail without target_dir

    def test_proxy_initializer_accepts_path_object(self):
        """ProxyInitializer accepts Path object for target directory."""
        target_dir = Path("/tmp/test_proxy")
        initializer = ProxyInitializer(target_dir=target_dir)
        assert initializer.target_dir == target_dir

    def test_proxy_initializer_converts_string_to_path(self):
        """ProxyInitializer converts string path to Path object."""
        target_dir_str = "/tmp/test_proxy"
        initializer = ProxyInitializer(target_dir=target_dir_str)
        assert isinstance(initializer.target_dir, Path)
        assert initializer.target_dir == Path(target_dir_str)


class TestProxyConfigurationCreation:
    """Tests for creating proxy configuration structure."""

    def test_create_proxy_config_creates_code_indexer_directory(self, tmp_path):
        """create_proxy_config() creates .code-indexer directory at target location."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        initializer.create_proxy_config()

        config_dir = target_dir / ".code-indexer"
        assert config_dir.exists()
        assert config_dir.is_dir()

    def test_create_proxy_config_creates_config_json_file(self, tmp_path):
        """create_proxy_config() creates config.json file inside .code-indexer."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        initializer.create_proxy_config()

        config_file = target_dir / ".code-indexer" / "config.json"
        assert config_file.exists()
        assert config_file.is_file()

    def test_create_proxy_config_sets_proxy_mode_flag(self, tmp_path):
        """config.json contains proxy_mode: true flag."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        initializer.create_proxy_config()

        config_file = target_dir / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert "proxy_mode" in config_data
        assert config_data["proxy_mode"] is True

    def test_create_proxy_config_initializes_empty_discovered_repos(self, tmp_path):
        """config.json contains discovered_repos as empty list initially."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        initializer.create_proxy_config()

        config_file = target_dir / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert "discovered_repos" in config_data
        assert config_data["discovered_repos"] == []

    def test_create_proxy_config_fails_if_already_initialized(self, tmp_path):
        """create_proxy_config() fails gracefully if directory already initialized."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()
        config_dir = target_dir / ".code-indexer"
        config_dir.mkdir()
        (config_dir / "config.json").write_text('{"proxy_mode": true}')

        initializer = ProxyInitializer(target_dir=target_dir)

        with pytest.raises(ProxyInitializationError) as exc_info:
            initializer.create_proxy_config()

        assert "already initialized" in str(exc_info.value).lower()


class TestNestedProxyDetection:
    """Tests for detecting and preventing nested proxy directories."""

    def test_check_nested_proxy_passes_when_no_parent_proxy(self, tmp_path):
        """check_nested_proxy() succeeds when no parent proxy exists."""
        target_dir = tmp_path / "level1" / "level2" / "proxy_root"
        target_dir.mkdir(parents=True)

        initializer = ProxyInitializer(target_dir=target_dir)
        # Should not raise exception
        initializer.check_nested_proxy()

    def test_check_nested_proxy_detects_parent_proxy_one_level_up(self, tmp_path):
        """check_nested_proxy() detects proxy configuration one level up."""
        parent_dir = tmp_path / "parent_proxy"
        parent_dir.mkdir()
        parent_config = parent_dir / ".code-indexer"
        parent_config.mkdir()
        (parent_config / "config.json").write_text('{"proxy_mode": true}')

        child_dir = parent_dir / "child_proxy"
        child_dir.mkdir()

        initializer = ProxyInitializer(target_dir=child_dir)

        with pytest.raises(NestedProxyError) as exc_info:
            initializer.check_nested_proxy()

        assert "nested proxy" in str(exc_info.value).lower()
        assert str(parent_dir) in str(exc_info.value)

    def test_check_nested_proxy_detects_parent_proxy_multiple_levels_up(self, tmp_path):
        """check_nested_proxy() detects proxy configuration multiple levels up."""
        root_proxy = tmp_path / "root_proxy"
        root_proxy.mkdir()
        root_config = root_proxy / ".code-indexer"
        root_config.mkdir()
        (root_config / "config.json").write_text('{"proxy_mode": true}')

        deep_child = root_proxy / "level1" / "level2" / "level3" / "child_proxy"
        deep_child.mkdir(parents=True)

        initializer = ProxyInitializer(target_dir=deep_child)

        with pytest.raises(NestedProxyError) as exc_info:
            initializer.check_nested_proxy()

        assert "nested proxy" in str(exc_info.value).lower()

    def test_check_nested_proxy_ignores_non_proxy_config_in_parent(self, tmp_path):
        """check_nested_proxy() ignores regular (non-proxy) config in parent."""
        parent_dir = tmp_path / "parent_regular"
        parent_dir.mkdir()
        parent_config = parent_dir / ".code-indexer"
        parent_config.mkdir()
        # Regular config without proxy_mode flag
        (parent_config / "config.json").write_text('{"embedding_provider": "ollama"}')

        child_dir = parent_dir / "child_proxy"
        child_dir.mkdir()

        initializer = ProxyInitializer(target_dir=child_dir)
        # Should not raise - parent is regular config, not proxy
        initializer.check_nested_proxy()


class TestRepositoryDiscovery:
    """Tests for discovering repositories with .code-indexer directories."""

    def test_discover_repositories_returns_empty_list_when_no_repos(self, tmp_path):
        """discover_repositories() returns empty list when no subdirectories exist."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        assert repos == []

    def test_discover_repositories_finds_single_repository(self, tmp_path):
        """discover_repositories() finds repository with .code-indexer directory."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        repo1 = target_dir / "repo1"
        repo1.mkdir()
        (repo1 / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        assert len(repos) == 1
        assert "repo1" in repos

    def test_discover_repositories_finds_multiple_repositories(self, tmp_path):
        """discover_repositories() finds all repositories in subdirectories."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Create 3 repositories
        for i in range(1, 4):
            repo = target_dir / f"repo{i}"
            repo.mkdir()
            (repo / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        assert len(repos) == 3
        assert set(repos) == {"repo1", "repo2", "repo3"}

    def test_discover_repositories_returns_relative_paths(self, tmp_path):
        """discover_repositories() returns relative paths, not absolute."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        repo1 = target_dir / "myrepo"
        repo1.mkdir()
        (repo1 / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        assert repos == ["myrepo"]
        # Verify not absolute path
        assert not repos[0].startswith("/")

    def test_discover_repositories_ignores_directories_without_code_indexer(
        self, tmp_path
    ):
        """discover_repositories() ignores subdirectories without .code-indexer."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Repository with .code-indexer
        repo_with_config = target_dir / "valid_repo"
        repo_with_config.mkdir()
        (repo_with_config / ".code-indexer").mkdir()

        # Directory without .code-indexer
        regular_dir = target_dir / "regular_folder"
        regular_dir.mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        assert len(repos) == 1
        assert repos == ["valid_repo"]

    def test_discover_repositories_searches_recursively_all_levels(self, tmp_path):
        """discover_repositories() searches recursively through all subdirectory levels."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Immediate child repository
        immediate_repo = target_dir / "immediate_repo"
        immediate_repo.mkdir()
        (immediate_repo / ".code-indexer").mkdir()

        # Nested repository (should NOW be found)
        nested_dir = target_dir / "level1" / "nested_repo"
        nested_dir.mkdir(parents=True)
        (nested_dir / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        assert len(repos) == 2
        assert "immediate_repo" in repos
        assert "level1/nested_repo" in repos

    def test_discover_repositories_finds_deeply_nested_repos(self, tmp_path):
        """discover_repositories() finds repositories at multiple nesting levels."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Create repositories at different depths
        repos_paths = [
            "services/auth",
            "services/user",
            "frontend",
            "backend/api/v1",
        ]

        for repo_path in repos_paths:
            full_path = target_dir / repo_path
            full_path.mkdir(parents=True)
            (full_path / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        assert len(repos) == 4
        for repo_path in repos_paths:
            assert repo_path in repos

    def test_discover_repositories_excludes_proxy_own_config(self, tmp_path):
        """discover_repositories() excludes the proxy's own .code-indexer directory."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Create proxy config
        proxy_config = target_dir / ".code-indexer"
        proxy_config.mkdir()

        # Create actual repository
        repo = target_dir / "myrepo"
        repo.mkdir()
        (repo / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        # Should only find myrepo, not the proxy's own config
        assert len(repos) == 1
        assert repos == ["myrepo"]

    def test_discover_repositories_handles_symlinks_safely(self, tmp_path):
        """discover_repositories() handles symbolic links without following circular references."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Create real repository
        real_repo = target_dir / "real_repo"
        real_repo.mkdir()
        (real_repo / ".code-indexer").mkdir()

        # Create symlink to repository
        symlink_repo = target_dir / "symlink_repo"
        symlink_repo.symlink_to(real_repo)

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        # Should find both, but handle resolution properly
        assert len(repos) >= 1
        assert "real_repo" in repos

    def test_discover_repositories_prevents_circular_symlink_infinite_loop(
        self, tmp_path
    ):
        """discover_repositories() detects and prevents circular symlink loops."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Create directory A with .code-indexer
        dir_a = target_dir / "dir_a"
        dir_a.mkdir()
        (dir_a / ".code-indexer").mkdir()

        # Create directory B
        dir_b = target_dir / "dir_b"
        dir_b.mkdir()

        # Create circular symlink: dir_b/link_to_a -> dir_a
        (dir_b / "link_to_a").symlink_to(dir_a)

        # Create symlink back: dir_a/link_to_b -> dir_b (circular)
        (dir_a / "link_to_b").symlink_to(dir_b)

        initializer = ProxyInitializer(target_dir=target_dir)

        # Should complete without infinite loop
        repos = initializer.discover_repositories()

        # Should find at least dir_a
        assert "dir_a" in repos

    def test_discover_repositories_returns_sorted_relative_paths(self, tmp_path):
        """discover_repositories() returns sorted relative paths for deterministic results."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Create repositories in random order
        repo_paths = ["zebra", "alpha", "services/middle", "beta"]
        for repo_path in repo_paths:
            full_path = target_dir / repo_path
            full_path.mkdir(parents=True)
            (full_path / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        repos = initializer.discover_repositories()

        # Should be sorted alphabetically
        expected = sorted(["alpha", "beta", "services/middle", "zebra"])
        assert repos == expected


class TestProxyInitializationIntegration:
    """Integration tests for complete proxy initialization workflow."""

    def test_initialize_creates_complete_proxy_structure(self, tmp_path):
        """initialize() creates complete proxy configuration with discovery."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Create some repositories
        for i in range(1, 3):
            repo = target_dir / f"repo{i}"
            repo.mkdir()
            (repo / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        initializer.initialize()

        # Verify .code-indexer directory created
        config_dir = target_dir / ".code-indexer"
        assert config_dir.exists()

        # Verify config.json exists and contains correct data
        config_file = config_dir / "config.json"
        assert config_file.exists()

        with open(config_file) as f:
            config_data = json.load(f)

        assert config_data["proxy_mode"] is True
        assert set(config_data["discovered_repos"]) == {"repo1", "repo2"}

    def test_initialize_performs_nested_proxy_check_first(self, tmp_path):
        """initialize() checks for nested proxy before creating config."""
        parent_proxy = tmp_path / "parent_proxy"
        parent_proxy.mkdir()
        parent_config = parent_proxy / ".code-indexer"
        parent_config.mkdir()
        (parent_config / "config.json").write_text('{"proxy_mode": true}')

        child_dir = parent_proxy / "child_proxy"
        child_dir.mkdir()

        initializer = ProxyInitializer(target_dir=child_dir)

        with pytest.raises(NestedProxyError):
            initializer.initialize()

        # Verify no config was created in child
        assert not (child_dir / ".code-indexer").exists()

    def test_initialize_force_bypasses_existing_config_check(self, tmp_path):
        """initialize(force=True) allows overwriting existing proxy config."""
        target_dir = tmp_path / "proxy_root"
        target_dir.mkdir()

        # Create existing config
        config_dir = target_dir / ".code-indexer"
        config_dir.mkdir()
        old_config = config_dir / "config.json"
        old_config.write_text('{"proxy_mode": true, "discovered_repos": ["old_repo"]}')

        # Create new repository
        new_repo = target_dir / "new_repo"
        new_repo.mkdir()
        (new_repo / ".code-indexer").mkdir()

        initializer = ProxyInitializer(target_dir=target_dir)
        initializer.initialize(force=True)

        # Verify config was updated with new discovery
        with open(old_config) as f:
            config_data = json.load(f)

        assert config_data["discovered_repos"] == ["new_repo"]
