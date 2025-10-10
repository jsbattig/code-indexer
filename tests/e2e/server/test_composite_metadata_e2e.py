"""
End-to-end tests for composite metadata management.

Tests complete metadata lifecycle from creation through loading and listing.
Following MESSI Rule #1: Zero mocking - uses real filesystem and real services.
"""

import pytest
import json
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

from code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from code_indexer.server.models.activated_repository import ActivatedRepository
from code_indexer.proxy.proxy_initializer import ProxyInitializer
from code_indexer.proxy.config_manager import ProxyConfigManager


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for E2E tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def real_composite_repo(temp_data_dir):
    """
    Create a real composite repository with proxy configuration.

    This fixture creates the complete structure that would exist after
    composite activation, including proxy config and subdirectories.
    """
    username = "testuser"
    user_alias = "composite"
    golden_repo_aliases = ["repo1", "repo2"]

    # Create directory structure
    user_dir = Path(temp_data_dir) / "activated-repos" / username
    user_dir.mkdir(parents=True, exist_ok=True)
    composite_path = user_dir / user_alias
    composite_path.mkdir(parents=True, exist_ok=True)

    # Initialize proxy configuration using real ProxyInitializer
    proxy_init = ProxyInitializer(composite_path)
    proxy_init.initialize(force=True)

    # Create subdirectories for repos
    for alias in golden_repo_aliases:
        repo_dir = composite_path / alias
        repo_dir.mkdir(parents=True, exist_ok=True)
        # Create minimal git structure
        git_dir = repo_dir / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        # Create .code-indexer directory to make it discoverable
        code_indexer_dir = repo_dir / ".code-indexer"
        code_indexer_dir.mkdir(parents=True, exist_ok=True)

    # Refresh repositories using real ProxyConfigManager
    proxy_config = ProxyConfigManager(composite_path)
    proxy_config.refresh_repositories()

    return {
        "temp_data_dir": temp_data_dir,
        "username": username,
        "user_alias": user_alias,
        "composite_path": composite_path,
        "golden_repo_aliases": golden_repo_aliases,
        "user_dir": user_dir,
    }


class TestCompositeMetadataE2E:
    """End-to-end tests for composite metadata lifecycle."""

    def test_complete_metadata_creation_and_persistence(self, real_composite_repo):
        """Test complete metadata creation and file persistence."""
        # Arrange
        composite_info = real_composite_repo
        composite_path = composite_info["composite_path"]
        user_alias = composite_info["user_alias"]
        username = composite_info["username"]
        golden_repo_aliases = composite_info["golden_repo_aliases"]
        user_dir = composite_info["user_dir"]

        # Get discovered repos from real proxy config
        proxy_config = ProxyConfigManager(composite_path)
        discovered_repos = proxy_config.get_repositories()

        # Act - Create and save metadata
        metadata = ActivatedRepository(
            user_alias=user_alias,
            username=username,
            path=composite_path,
            activated_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            is_composite=True,
            golden_repo_aliases=golden_repo_aliases,
            discovered_repos=discovered_repos,
        )

        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Assert - Verify file exists and contains correct data
        assert metadata_file.exists()
        loaded_data = json.loads(metadata_file.read_text())
        assert loaded_data["is_composite"] is True
        assert loaded_data["golden_repo_aliases"] == golden_repo_aliases
        assert len(loaded_data["discovered_repos"]) == len(golden_repo_aliases)

    def test_metadata_survives_reload(self, real_composite_repo):
        """Test that metadata can be saved and loaded correctly."""
        # Arrange
        composite_info = real_composite_repo
        composite_path = composite_info["composite_path"]
        user_alias = composite_info["user_alias"]
        username = composite_info["username"]
        golden_repo_aliases = composite_info["golden_repo_aliases"]
        user_dir = composite_info["user_dir"]

        # Get discovered repos
        proxy_config = ProxyConfigManager(composite_path)
        discovered_repos = proxy_config.get_repositories()

        # Create and save metadata
        original_metadata = ActivatedRepository(
            user_alias=user_alias,
            username=username,
            path=composite_path,
            activated_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            is_composite=True,
            golden_repo_aliases=golden_repo_aliases,
            discovered_repos=discovered_repos,
        )

        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(original_metadata.to_dict(), indent=2))

        # Act - Load metadata from file
        loaded_data = json.loads(metadata_file.read_text())
        loaded_metadata = ActivatedRepository.from_dict(loaded_data)

        # Assert - Verify loaded metadata matches original
        assert loaded_metadata.user_alias == original_metadata.user_alias
        assert loaded_metadata.username == original_metadata.username
        assert loaded_metadata.is_composite == original_metadata.is_composite
        assert (
            loaded_metadata.golden_repo_aliases == original_metadata.golden_repo_aliases
        )
        assert loaded_metadata.discovered_repos == original_metadata.discovered_repos

    def test_list_operation_returns_composite_repos(self, real_composite_repo):
        """Test that list operation correctly returns composite repositories."""
        # Arrange
        composite_info = real_composite_repo
        temp_data_dir = composite_info["temp_data_dir"]
        composite_path = composite_info["composite_path"]
        user_alias = composite_info["user_alias"]
        username = composite_info["username"]
        golden_repo_aliases = composite_info["golden_repo_aliases"]
        user_dir = composite_info["user_dir"]

        # Create metadata
        proxy_config = ProxyConfigManager(composite_path)
        discovered_repos = proxy_config.get_repositories()

        metadata = ActivatedRepository(
            user_alias=user_alias,
            username=username,
            path=composite_path,
            activated_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            is_composite=True,
            golden_repo_aliases=golden_repo_aliases,
            discovered_repos=discovered_repos,
        )

        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Create ActivatedRepoManager
        manager = ActivatedRepoManager(data_dir=temp_data_dir)

        # Act - List repositories
        repos = manager.list_activated_repositories(username)

        # Assert
        assert len(repos) == 1
        repo = repos[0]
        assert repo["user_alias"] == user_alias
        assert repo["is_composite"] is True
        assert repo["golden_repo_aliases"] == golden_repo_aliases
        assert len(repo["discovered_repos"]) == len(golden_repo_aliases)

    def test_discovered_repos_refresh_when_config_changes(self, real_composite_repo):
        """Test that discovered_repos refreshes when proxy config changes."""
        # Arrange
        composite_info = real_composite_repo
        composite_path = composite_info["composite_path"]
        user_alias = composite_info["user_alias"]
        username = composite_info["username"]
        golden_repo_aliases = composite_info["golden_repo_aliases"]
        user_dir = composite_info["user_dir"]

        # Create initial metadata
        proxy_config = ProxyConfigManager(composite_path)
        initial_discovered = proxy_config.get_repositories()

        metadata = ActivatedRepository(
            user_alias=user_alias,
            username=username,
            path=composite_path,
            activated_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            is_composite=True,
            golden_repo_aliases=golden_repo_aliases,
            discovered_repos=initial_discovered,
        )

        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Act - Add a new repository and refresh
        new_repo_dir = composite_path / "repo3"
        new_repo_dir.mkdir(parents=True, exist_ok=True)
        git_dir = new_repo_dir / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        # Create .code-indexer directory to make it discoverable
        code_indexer_dir = new_repo_dir / ".code-indexer"
        code_indexer_dir.mkdir(parents=True, exist_ok=True)

        # Refresh proxy config
        proxy_config.refresh_repositories()
        updated_discovered = proxy_config.get_repositories()

        # Assert - Verify new repo is discovered
        assert len(updated_discovered) == len(initial_discovered) + 1
        assert "repo3" in updated_discovered
