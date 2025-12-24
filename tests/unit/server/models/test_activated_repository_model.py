"""
Unit tests for ActivatedRepository model.

Tests model behavior, serialization, deserialization, and backward compatibility.
Following TDD methodology - these tests will initially fail.
"""

from datetime import datetime, timezone
from pathlib import Path
from code_indexer.server.models.activated_repository import ActivatedRepository


class TestActivatedRepositoryModel:
    """Test suite for ActivatedRepository model."""

    def test_create_single_repository_instance(self):
        """Test creating a single repository instance with all fields."""
        # Arrange
        now = datetime.now(timezone.utc)
        repo_path = Path("/home/user/.cidx-server/data/activated-repos/testuser/myrepo")

        # Act
        repo = ActivatedRepository(
            user_alias="myrepo",
            username="testuser",
            path=repo_path,
            activated_at=now,
            last_accessed=now,
            golden_repo_alias="upstream-repo",
            current_branch="main",
            is_composite=False,
        )

        # Assert
        assert repo.user_alias == "myrepo"
        assert repo.username == "testuser"
        assert repo.path == repo_path
        assert repo.activated_at == now
        assert repo.last_accessed == now
        assert repo.golden_repo_alias == "upstream-repo"
        assert repo.current_branch == "main"
        assert repo.is_composite is False
        assert repo.golden_repo_aliases == []
        assert repo.discovered_repos == []

    def test_create_composite_repository_instance(self):
        """Test creating a composite repository instance with new fields."""
        # Arrange
        now = datetime.now(timezone.utc)
        repo_path = Path(
            "/home/user/.cidx-server/data/activated-repos/testuser/composite"
        )
        aliases = ["repo1", "repo2", "repo3"]
        discovered = ["repo1", "repo2", "repo3"]

        # Act
        repo = ActivatedRepository(
            user_alias="composite",
            username="testuser",
            path=repo_path,
            activated_at=now,
            last_accessed=now,
            is_composite=True,
            golden_repo_aliases=aliases,
            discovered_repos=discovered,
        )

        # Assert
        assert repo.user_alias == "composite"
        assert repo.username == "testuser"
        assert repo.is_composite is True
        assert repo.golden_repo_aliases == aliases
        assert repo.discovered_repos == discovered
        assert repo.golden_repo_alias == ""  # Not set for composite
        assert repo.current_branch == "main"  # Default

    def test_serialization_to_dict_single_repo(self):
        """Test serialization of single repository to dictionary."""
        # Arrange
        now = datetime.now(timezone.utc)
        repo_path = Path("/home/user/.cidx-server/data/activated-repos/testuser/myrepo")
        repo = ActivatedRepository(
            user_alias="myrepo",
            username="testuser",
            path=repo_path,
            activated_at=now,
            last_accessed=now,
            golden_repo_alias="upstream-repo",
            current_branch="feature",
            is_composite=False,
        )

        # Act
        data = repo.to_dict()

        # Assert
        assert data["user_alias"] == "myrepo"
        assert data["username"] == "testuser"
        assert data["path"] == str(repo_path)
        assert data["activated_at"] == now.isoformat()
        assert data["last_accessed"] == now.isoformat()
        assert data["golden_repo_alias"] == "upstream-repo"
        assert data["current_branch"] == "feature"
        assert data["is_composite"] is False
        assert data["golden_repo_aliases"] == []
        assert data["discovered_repos"] == []

    def test_serialization_to_dict_composite_repo(self):
        """Test serialization of composite repository to dictionary."""
        # Arrange
        now = datetime.now(timezone.utc)
        repo_path = Path(
            "/home/user/.cidx-server/data/activated-repos/testuser/composite"
        )
        aliases = ["repo1", "repo2"]
        discovered = ["repo1", "repo2"]
        repo = ActivatedRepository(
            user_alias="composite",
            username="testuser",
            path=repo_path,
            activated_at=now,
            last_accessed=now,
            is_composite=True,
            golden_repo_aliases=aliases,
            discovered_repos=discovered,
        )

        # Act
        data = repo.to_dict()

        # Assert
        assert data["is_composite"] is True
        assert data["golden_repo_aliases"] == aliases
        assert data["discovered_repos"] == discovered

    def test_deserialization_from_dict_single_repo(self):
        """Test deserialization from dictionary for single repository."""
        # Arrange
        now = datetime.now(timezone.utc)
        data = {
            "user_alias": "myrepo",
            "username": "testuser",
            "path": "/home/user/.cidx-server/data/activated-repos/testuser/myrepo",
            "activated_at": now.isoformat(),
            "last_accessed": now.isoformat(),
            "golden_repo_alias": "upstream-repo",
            "current_branch": "main",
            "is_composite": False,
        }

        # Act
        repo = ActivatedRepository.from_dict(data)

        # Assert
        assert repo.user_alias == "myrepo"
        assert repo.username == "testuser"
        assert isinstance(repo.path, Path)
        assert isinstance(repo.activated_at, datetime)
        assert isinstance(repo.last_accessed, datetime)
        assert repo.golden_repo_alias == "upstream-repo"
        assert repo.current_branch == "main"
        assert repo.is_composite is False

    def test_deserialization_from_dict_composite_repo(self):
        """Test deserialization from dictionary for composite repository."""
        # Arrange
        now = datetime.now(timezone.utc)
        aliases = ["repo1", "repo2", "repo3"]
        discovered = ["repo1", "repo2", "repo3"]
        data = {
            "user_alias": "composite",
            "username": "testuser",
            "path": "/home/user/.cidx-server/data/activated-repos/testuser/composite",
            "activated_at": now.isoformat(),
            "last_accessed": now.isoformat(),
            "is_composite": True,
            "golden_repo_aliases": aliases,
            "discovered_repos": discovered,
        }

        # Act
        repo = ActivatedRepository.from_dict(data)

        # Assert
        assert repo.is_composite is True
        assert repo.golden_repo_aliases == aliases
        assert repo.discovered_repos == discovered

    def test_backward_compatibility_without_new_fields(self):
        """Test backward compatibility - old metadata without new fields."""
        # Arrange - Old metadata format without composite fields
        now = datetime.now(timezone.utc)
        data = {
            "user_alias": "oldrepo",
            "username": "testuser",
            "path": "/home/user/.cidx-server/data/activated-repos/testuser/oldrepo",
            "activated_at": now.isoformat(),
            "last_accessed": now.isoformat(),
            "golden_repo_alias": "upstream-repo",
            "current_branch": "main",
            # is_composite, golden_repo_aliases, discovered_repos NOT present
        }

        # Act
        repo = ActivatedRepository.from_dict(data)

        # Assert - Should use defaults
        assert repo.user_alias == "oldrepo"
        assert repo.is_composite is False  # Default
        assert repo.golden_repo_aliases == []  # Default
        assert repo.discovered_repos == []  # Default

    def test_round_trip_serialization(self):
        """Test that to_dict() and from_dict() produce equivalent objects."""
        # Arrange
        now = datetime.now(timezone.utc)
        repo_path = Path(
            "/home/user/.cidx-server/data/activated-repos/testuser/composite"
        )
        original = ActivatedRepository(
            user_alias="composite",
            username="testuser",
            path=repo_path,
            activated_at=now,
            last_accessed=now,
            is_composite=True,
            golden_repo_aliases=["repo1", "repo2"],
            discovered_repos=["repo1", "repo2"],
        )

        # Act
        data = original.to_dict()
        restored = ActivatedRepository.from_dict(data)

        # Assert
        assert restored.user_alias == original.user_alias
        assert restored.username == original.username
        assert restored.path == original.path
        assert restored.is_composite == original.is_composite
        assert restored.golden_repo_aliases == original.golden_repo_aliases
        assert restored.discovered_repos == original.discovered_repos
