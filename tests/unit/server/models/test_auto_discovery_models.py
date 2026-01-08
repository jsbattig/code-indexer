"""
Tests for Auto-Discovery Models.

Following TDD methodology - these tests are written FIRST before implementation.
Tests define the expected behavior for:
- DiscoveredRepository: Model for a discovered repository from GitLab/GitHub
- RepositoryDiscoveryResult: Paginated response model for discovery endpoint
- DiscoveryProviderError: Error response model for discovery failures
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError


class TestDiscoveredRepository:
    """Tests for DiscoveredRepository model."""

    def test_create_discovered_repository_with_required_fields(self):
        """Test creating a DiscoveredRepository with all required fields."""
        from code_indexer.server.models.auto_discovery import DiscoveredRepository

        repo = DiscoveredRepository(
            platform="gitlab",
            name="group/project",
            clone_url_https="https://gitlab.com/group/project.git",
            clone_url_ssh="git@gitlab.com:group/project.git",
            default_branch="main",
            is_private=False,
        )

        assert repo.platform == "gitlab"
        assert repo.name == "group/project"
        assert repo.clone_url_https == "https://gitlab.com/group/project.git"
        assert repo.clone_url_ssh == "git@gitlab.com:group/project.git"
        assert repo.default_branch == "main"
        assert repo.is_private is False

    def test_create_discovered_repository_with_optional_fields(self):
        """Test creating a DiscoveredRepository with optional fields."""
        from code_indexer.server.models.auto_discovery import DiscoveredRepository

        now = datetime.now(timezone.utc)
        repo = DiscoveredRepository(
            platform="gitlab",
            name="group/project",
            description="A test project",
            clone_url_https="https://gitlab.com/group/project.git",
            clone_url_ssh="git@gitlab.com:group/project.git",
            default_branch="main",
            last_commit_hash="abc1234",
            last_commit_author="John Doe",
            last_activity=now,
            is_private=True,
        )

        assert repo.description == "A test project"
        assert repo.last_commit_hash == "abc1234"
        assert repo.last_commit_author == "John Doe"
        assert repo.last_activity == now
        assert repo.is_private is True

    def test_platform_must_be_gitlab_or_github(self):
        """Test that platform field must be 'gitlab' or 'github'."""
        from code_indexer.server.models.auto_discovery import DiscoveredRepository

        with pytest.raises(ValidationError) as exc_info:
            DiscoveredRepository(
                platform="bitbucket",  # Invalid platform
                name="group/project",
                clone_url_https="https://gitlab.com/group/project.git",
                clone_url_ssh="git@gitlab.com:group/project.git",
                default_branch="main",
                is_private=False,
            )

        assert "platform" in str(exc_info.value)

    def test_name_cannot_be_empty(self):
        """Test that name field cannot be empty."""
        from code_indexer.server.models.auto_discovery import DiscoveredRepository

        with pytest.raises(ValidationError) as exc_info:
            DiscoveredRepository(
                platform="gitlab",
                name="",  # Empty name
                clone_url_https="https://gitlab.com/group/project.git",
                clone_url_ssh="git@gitlab.com:group/project.git",
                default_branch="main",
                is_private=False,
            )

        assert "name" in str(exc_info.value)

    def test_clone_urls_must_be_valid(self):
        """Test that clone URLs must be valid git URLs."""
        from code_indexer.server.models.auto_discovery import DiscoveredRepository

        with pytest.raises(ValidationError) as exc_info:
            DiscoveredRepository(
                platform="gitlab",
                name="group/project",
                clone_url_https="not-a-url",  # Invalid URL
                clone_url_ssh="git@gitlab.com:group/project.git",
                default_branch="main",
                is_private=False,
            )

        assert "clone_url_https" in str(exc_info.value)


class TestRepositoryDiscoveryResult:
    """Tests for RepositoryDiscoveryResult model."""

    def test_create_discovery_result_with_repositories(self):
        """Test creating a RepositoryDiscoveryResult with repositories."""
        from code_indexer.server.models.auto_discovery import (
            DiscoveredRepository,
            RepositoryDiscoveryResult,
        )

        repo = DiscoveredRepository(
            platform="gitlab",
            name="group/project",
            clone_url_https="https://gitlab.com/group/project.git",
            clone_url_ssh="git@gitlab.com:group/project.git",
            default_branch="main",
            is_private=False,
        )

        result = RepositoryDiscoveryResult(
            repositories=[repo],
            total_count=100,
            page=1,
            page_size=50,
            total_pages=2,
            platform="gitlab",
        )

        assert len(result.repositories) == 1
        assert result.total_count == 100
        assert result.page == 1
        assert result.page_size == 50
        assert result.total_pages == 2
        assert result.platform == "gitlab"

    def test_empty_repositories_list_is_valid(self):
        """Test that an empty repositories list is valid."""
        from code_indexer.server.models.auto_discovery import RepositoryDiscoveryResult

        result = RepositoryDiscoveryResult(
            repositories=[],
            total_count=0,
            page=1,
            page_size=50,
            total_pages=0,
            platform="gitlab",
        )

        assert len(result.repositories) == 0
        assert result.total_count == 0

    def test_page_must_be_positive(self):
        """Test that page must be a positive integer."""
        from code_indexer.server.models.auto_discovery import RepositoryDiscoveryResult

        with pytest.raises(ValidationError) as exc_info:
            RepositoryDiscoveryResult(
                repositories=[],
                total_count=0,
                page=0,  # Invalid: must be >= 1
                page_size=50,
                total_pages=0,
                platform="gitlab",
            )

        assert "page" in str(exc_info.value)

    def test_page_size_must_be_positive(self):
        """Test that page_size must be a positive integer."""
        from code_indexer.server.models.auto_discovery import RepositoryDiscoveryResult

        with pytest.raises(ValidationError) as exc_info:
            RepositoryDiscoveryResult(
                repositories=[],
                total_count=0,
                page=1,
                page_size=0,  # Invalid: must be > 0
                total_pages=0,
                platform="gitlab",
            )

        assert "page_size" in str(exc_info.value)

    def test_total_count_cannot_be_negative(self):
        """Test that total_count cannot be negative."""
        from code_indexer.server.models.auto_discovery import RepositoryDiscoveryResult

        with pytest.raises(ValidationError) as exc_info:
            RepositoryDiscoveryResult(
                repositories=[],
                total_count=-1,  # Invalid: cannot be negative
                page=1,
                page_size=50,
                total_pages=0,
                platform="gitlab",
            )

        assert "total_count" in str(exc_info.value)

    def test_total_pages_calculated_correctly(self):
        """Test that total_pages is validated against total_count and page_size."""
        from code_indexer.server.models.auto_discovery import RepositoryDiscoveryResult

        # 100 total with page_size 50 = 2 pages
        result = RepositoryDiscoveryResult(
            repositories=[],
            total_count=100,
            page=1,
            page_size=50,
            total_pages=2,
            platform="gitlab",
        )
        assert result.total_pages == 2


class TestDiscoveryProviderError:
    """Tests for DiscoveryProviderError model."""

    def test_create_provider_error(self):
        """Test creating a DiscoveryProviderError."""
        from code_indexer.server.models.auto_discovery import DiscoveryProviderError

        error = DiscoveryProviderError(
            platform="gitlab",
            error_type="api_error",
            message="Failed to fetch repositories",
            details="Rate limit exceeded",
        )

        assert error.platform == "gitlab"
        assert error.error_type == "api_error"
        assert error.message == "Failed to fetch repositories"
        assert error.details == "Rate limit exceeded"

    def test_error_type_must_be_valid(self):
        """Test that error_type must be a valid error type."""
        from code_indexer.server.models.auto_discovery import DiscoveryProviderError

        error = DiscoveryProviderError(
            platform="gitlab",
            error_type="not_configured",
            message="GitLab token not configured",
        )

        assert error.error_type == "not_configured"
