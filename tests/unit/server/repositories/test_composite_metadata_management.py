"""
Unit tests for composite metadata management in ActivatedRepoManager.

Tests metadata creation, loading, refresh, and listing operations for
composite repositories. Following TDD methodology.
"""

import pytest
import json
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from code_indexer.server.models.activated_repository import ActivatedRepository


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def activated_repo_manager(temp_data_dir):
    """Create ActivatedRepoManager instance with temporary data directory."""
    # Mock golden repo manager to avoid external dependencies
    with patch(
        "code_indexer.server.repositories.activated_repo_manager.GoldenRepoManager"
    ):
        with patch(
            "code_indexer.server.repositories.activated_repo_manager.BackgroundJobManager"
        ):
            manager = ActivatedRepoManager(data_dir=temp_data_dir)
            return manager


class TestCompositeMetadataCreation:
    """Test suite for composite repository metadata creation."""

    def test_metadata_includes_is_composite_flag(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that composite metadata includes is_composite=True flag."""
        # Arrange
        username = "testuser"
        user_alias = "composite"
        golden_repo_aliases = ["repo1", "repo2"]

        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        composite_path = user_dir / user_alias
        composite_path.mkdir(parents=True, exist_ok=True)

        # Create proxy config file (required for ProxyConfigManager)
        proxy_config_file = composite_path / ".code-indexer" / "config.json"
        proxy_config_file.parent.mkdir(parents=True, exist_ok=True)
        proxy_config_file.write_text(
            json.dumps(
                {
                    "embedding_provider": "voyage-ai",
                    "proxy_mode": True,
                    "discovered_repos": ["repo1", "repo2"],
                }
            )
        )

        # Act - Create metadata using internal method
        metadata = ActivatedRepository(
            user_alias=user_alias,
            username=username,
            path=composite_path,
            activated_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            is_composite=True,
            golden_repo_aliases=golden_repo_aliases,
            discovered_repos=["repo1", "repo2"],
        )

        # Save metadata to file
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Assert
        assert metadata_file.exists()
        loaded_data = json.loads(metadata_file.read_text())
        assert loaded_data["is_composite"] is True

    def test_metadata_includes_golden_repo_aliases(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that composite metadata includes list of golden repo aliases."""
        # Arrange
        username = "testuser"
        user_alias = "composite"
        golden_repo_aliases = ["repo1", "repo2", "repo3"]

        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        composite_path = user_dir / user_alias
        composite_path.mkdir(parents=True, exist_ok=True)

        # Create proxy config
        proxy_config_file = composite_path / ".code-indexer" / "config.json"
        proxy_config_file.parent.mkdir(parents=True, exist_ok=True)
        proxy_config_file.write_text(
            json.dumps(
                {
                    "embedding_provider": "voyage-ai",
                    "proxy_mode": True,
                    "discovered_repos": ["repo1", "repo2", "repo3"],
                }
            )
        )

        # Act
        metadata = ActivatedRepository(
            user_alias=user_alias,
            username=username,
            path=composite_path,
            activated_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            is_composite=True,
            golden_repo_aliases=golden_repo_aliases,
            discovered_repos=["repo1", "repo2", "repo3"],
        )

        # Save metadata
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Assert
        loaded_data = json.loads(metadata_file.read_text())
        assert loaded_data["golden_repo_aliases"] == golden_repo_aliases

    def test_metadata_includes_discovered_repos(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that composite metadata includes discovered repos from proxy config."""
        # Arrange
        username = "testuser"
        user_alias = "composite"
        golden_repo_aliases = ["repo1", "repo2"]
        discovered_repos = ["repo1", "repo2"]

        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        composite_path = user_dir / user_alias
        composite_path.mkdir(parents=True, exist_ok=True)

        # Create proxy config
        proxy_config_file = composite_path / ".code-indexer" / "config.json"
        proxy_config_file.parent.mkdir(parents=True, exist_ok=True)
        proxy_config_file.write_text(
            json.dumps(
                {
                    "embedding_provider": "voyage-ai",
                    "proxy_mode": True,
                    "discovered_repos": ["repo1", "repo2"],
                }
            )
        )

        # Act
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

        # Save metadata
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

        # Assert
        loaded_data = json.loads(metadata_file.read_text())
        assert loaded_data["discovered_repos"] == discovered_repos


class TestMetadataLoading:
    """Test suite for metadata loading and refresh operations."""

    def test_load_composite_metadata_from_file(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test loading composite metadata from file."""
        # Arrange
        username = "testuser"
        user_alias = "composite"
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        composite_path = user_dir / user_alias
        composite_path.mkdir(parents=True, exist_ok=True)

        # Create metadata file
        metadata_data = {
            "user_alias": user_alias,
            "username": username,
            "path": str(composite_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "is_composite": True,
            "golden_repo_aliases": ["repo1", "repo2"],
            "discovered_repos": ["repo1", "repo2"],
        }
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata_data, indent=2))

        # Act
        loaded_metadata = ActivatedRepository.from_dict(metadata_data)

        # Assert
        assert loaded_metadata.is_composite is True
        assert loaded_metadata.golden_repo_aliases == ["repo1", "repo2"]
        assert loaded_metadata.discovered_repos == ["repo1", "repo2"]

    def test_refresh_discovered_repos_from_proxy_config(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that discovered_repos is refreshed from proxy config on load."""
        # Arrange
        username = "testuser"
        user_alias = "composite"
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        composite_path = user_dir / user_alias
        composite_path.mkdir(parents=True, exist_ok=True)

        # Create metadata with old discovered repos
        metadata_data = {
            "user_alias": user_alias,
            "username": username,
            "path": str(composite_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "is_composite": True,
            "golden_repo_aliases": ["repo1", "repo2"],
            "discovered_repos": ["repo1", "repo2"],  # Old list
        }
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata_data, indent=2))

        # Create updated proxy config with new repo
        # ProxyConfigManager expects config.json, not proxy_config.json
        proxy_config_file = composite_path / ".code-indexer" / "config.json"
        proxy_config_file.parent.mkdir(parents=True, exist_ok=True)
        proxy_config_file.write_text(
            json.dumps(
                {
                    "embedding_provider": "voyage-ai",
                    "proxy_mode": True,
                    "discovered_repos": ["repo1", "repo2", "repo3"],  # NEW repo
                }
            )
        )

        # Act - This would be done by get_repository() method
        # For now, simulate the refresh logic
        from code_indexer.proxy.config_manager import ProxyConfigManager

        proxy_config = ProxyConfigManager(composite_path)
        updated_discovered = proxy_config.get_repositories()

        # Assert
        assert len(updated_discovered) == 3
        assert "repo3" in updated_discovered

    def test_load_single_repo_metadata_backward_compatibility(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test loading old single-repo metadata without new fields."""
        # Arrange
        username = "testuser"
        user_alias = "oldrepo"
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        repo_path = user_dir / user_alias
        repo_path.mkdir(parents=True, exist_ok=True)

        # Create old metadata without composite fields
        metadata_data = {
            "user_alias": user_alias,
            "username": username,
            "path": str(repo_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "golden_repo_alias": "upstream-repo",
            "current_branch": "main",
            # No is_composite, golden_repo_aliases, discovered_repos
        }
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata_data, indent=2))

        # Act
        loaded_metadata = ActivatedRepository.from_dict(metadata_data)

        # Assert - Should use defaults
        assert loaded_metadata.is_composite is False
        assert loaded_metadata.golden_repo_aliases == []
        assert loaded_metadata.discovered_repos == []


class TestGetRepositoryMethod:
    """Test suite for get_repository() method."""

    def test_get_repository_returns_metadata(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that get_repository() returns repository metadata."""
        # Arrange
        username = "testuser"
        user_alias = "testrepo"
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        repo_path = user_dir / user_alias
        repo_path.mkdir(parents=True, exist_ok=True)

        # Create metadata file
        metadata_data = {
            "user_alias": user_alias,
            "username": username,
            "path": str(repo_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "golden_repo_alias": "upstream",
            "current_branch": "main",
            "is_composite": False,
        }
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata_data, indent=2))

        # Act
        result = activated_repo_manager.get_repository(username, user_alias)

        # Assert
        assert result is not None
        assert result["user_alias"] == user_alias
        assert result["username"] == username

    def test_get_repository_returns_none_if_not_found(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that get_repository() returns None if repository doesn't exist."""
        # Act
        result = activated_repo_manager.get_repository("nonexistent", "nothere")

        # Assert
        assert result is None

    def test_get_repository_refreshes_discovered_repos_for_composite(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that get_repository() refreshes discovered_repos for composite repositories."""
        # Arrange
        username = "testuser"
        user_alias = "composite"
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        composite_path = user_dir / user_alias
        composite_path.mkdir(parents=True, exist_ok=True)

        # Create .code-indexer directory and config
        code_indexer_dir = composite_path / ".code-indexer"
        code_indexer_dir.mkdir(parents=True, exist_ok=True)

        # Create config.json with proxy_mode enabled
        config_file = code_indexer_dir / "config.json"
        config_data = {
            "embedding_provider": "voyage-ai",
            "proxy_mode": True,
            "discovered_repos": ["repo1", "repo2", "repo3"],
        }
        config_file.write_text(json.dumps(config_data, indent=2))

        # Create metadata with old discovered repos
        metadata_data = {
            "user_alias": user_alias,
            "username": username,
            "path": str(composite_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "is_composite": True,
            "golden_repo_aliases": ["repo1", "repo2"],
            "discovered_repos": ["repo1", "repo2"],  # Old list, missing repo3
        }
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata_data, indent=2))

        # Act
        result = activated_repo_manager.get_repository(username, user_alias)

        # Assert
        assert result is not None
        assert result["is_composite"] is True
        assert len(result["discovered_repos"]) == 3
        assert "repo3" in result["discovered_repos"]

    def test_get_repository_handles_missing_proxy_config_gracefully(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that get_repository() handles missing proxy config gracefully."""
        # Arrange
        username = "testuser"
        user_alias = "composite"
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        composite_path = user_dir / user_alias
        composite_path.mkdir(parents=True, exist_ok=True)

        # Create metadata WITHOUT creating proxy config
        old_discovered = ["repo1", "repo2"]
        metadata_data = {
            "user_alias": user_alias,
            "username": username,
            "path": str(composite_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "is_composite": True,
            "golden_repo_aliases": ["repo1", "repo2"],
            "discovered_repos": old_discovered,
        }
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        metadata_file.write_text(json.dumps(metadata_data, indent=2))

        # Act - Should not raise exception
        result = activated_repo_manager.get_repository(username, user_alias)

        # Assert - Should return with original discovered_repos
        assert result is not None
        assert result["discovered_repos"] == old_discovered  # Fallback to cached list


class TestListOperation:
    """Test suite for list operation with composite repositories."""

    def test_list_shows_composite_repos(self, activated_repo_manager, temp_data_dir):
        """Test that list operation includes composite repositories."""
        # Arrange
        username = "testuser"
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)

        # Create composite repo metadata
        composite_alias = "composite"
        composite_path = user_dir / composite_alias
        composite_path.mkdir(parents=True, exist_ok=True)
        composite_metadata = {
            "user_alias": composite_alias,
            "username": username,
            "path": str(composite_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "is_composite": True,
            "golden_repo_aliases": ["repo1", "repo2"],
            "discovered_repos": ["repo1", "repo2"],
        }
        (user_dir / f"{composite_alias}_metadata.json").write_text(
            json.dumps(composite_metadata, indent=2)
        )

        # Create single repo metadata
        single_alias = "single"
        single_path = user_dir / single_alias
        single_path.mkdir(parents=True, exist_ok=True)
        single_metadata = {
            "user_alias": single_alias,
            "username": username,
            "path": str(single_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "golden_repo_alias": "upstream",
            "current_branch": "main",
            "is_composite": False,
        }
        (user_dir / f"{single_alias}_metadata.json").write_text(
            json.dumps(single_metadata, indent=2)
        )

        # Act
        repos = activated_repo_manager.list_activated_repositories(username)

        # Assert
        assert len(repos) == 2
        composite_repos = [r for r in repos if r.get("is_composite")]
        single_repos = [r for r in repos if not r.get("is_composite")]
        assert len(composite_repos) == 1
        assert len(single_repos) == 1
        assert composite_repos[0]["user_alias"] == composite_alias

    def test_list_loads_all_metadata_fields(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that list operation loads all metadata fields including new ones."""
        # Arrange
        username = "testuser"
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)

        composite_alias = "composite"
        composite_path = user_dir / composite_alias
        composite_path.mkdir(parents=True, exist_ok=True)
        golden_aliases = ["repo1", "repo2", "repo3"]
        discovered = ["repo1", "repo2", "repo3"]
        composite_metadata = {
            "user_alias": composite_alias,
            "username": username,
            "path": str(composite_path),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "is_composite": True,
            "golden_repo_aliases": golden_aliases,
            "discovered_repos": discovered,
        }
        (user_dir / f"{composite_alias}_metadata.json").write_text(
            json.dumps(composite_metadata, indent=2)
        )

        # Act
        repos = activated_repo_manager.list_activated_repositories(username)

        # Assert
        assert len(repos) == 1
        repo = repos[0]
        assert repo["is_composite"] is True
        assert repo["golden_repo_aliases"] == golden_aliases
        assert repo["discovered_repos"] == discovered
