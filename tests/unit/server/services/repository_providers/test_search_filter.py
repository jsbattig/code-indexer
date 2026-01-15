"""
Tests for GitLab provider search filtering functionality.

Following TDD methodology - these tests are written FIRST before implementation.
Tests define the expected behavior for search filtering in Auto-Discovery.
"""

from typing import Optional
import pytest
from unittest.mock import MagicMock, patch


def create_mock_gitlab_project(
    name: str,
    path_with_namespace: str,
    description: Optional[str] = None,
    visibility: str = "private",
    last_commit_hash: Optional[str] = None,
    last_commit_author: Optional[str] = None,
) -> dict:
    """Helper to create mock GitLab project API response."""
    project = {
        "id": hash(name) % 10000,
        "name": name,
        "path_with_namespace": path_with_namespace,
        "description": description,
        "http_url_to_repo": f"https://gitlab.com/{path_with_namespace}.git",
        "ssh_url_to_repo": f"git@gitlab.com:{path_with_namespace}.git",
        "default_branch": "main",
        "last_activity_at": "2024-01-15T10:30:00Z",
        "visibility": visibility,
    }
    # Add commit info if provided (simulating extended API data)
    if last_commit_hash or last_commit_author:
        project["_last_commit_hash"] = last_commit_hash
        project["_last_commit_author"] = last_commit_author
    return project


@pytest.fixture
def gitlab_provider():
    """Create a GitLab provider with mocked dependencies."""
    from code_indexer.server.services.repository_providers.gitlab_provider import (
        GitLabProvider,
    )
    from code_indexer.server.services.ci_token_manager import TokenData

    token_manager = MagicMock()
    token_manager.get_token.return_value = TokenData(
        platform="gitlab",
        token="glpat-test-token-123456789012",
        base_url=None,
    )
    golden_repo_manager = MagicMock()
    golden_repo_manager.list_golden_repos.return_value = []

    return GitLabProvider(
        token_manager=token_manager,
        golden_repo_manager=golden_repo_manager,
    )


def create_mock_response(
    projects: list, total: Optional[int] = None, total_pages: int = 1
):
    """Create a mock HTTP response for GitLab API."""
    if total is None:
        total = len(projects)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"x-total": str(total), "x-total-pages": str(total_pages)}
    mock_response.json.return_value = projects
    mock_response.raise_for_status = MagicMock()
    return mock_response


class TestGitLabProviderSearchFilter:
    """Tests for GitLab provider search filtering."""

    @pytest.mark.asyncio
    async def test_search_by_name_matches(self, gitlab_provider):
        """Test that search matches repository name substring."""
        projects = [
            create_mock_gitlab_project("auth-service", "team/auth-service", "Auth"),
            create_mock_gitlab_project(
                "payment-service", "team/payment-service", "Pay"
            ),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="auth"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "team/auth-service"

    @pytest.mark.asyncio
    async def test_search_by_description_matches(self, gitlab_provider):
        """Test that search matches repository description substring."""
        projects = [
            create_mock_gitlab_project(
                "gateway", "team/gateway", "API with authentication"
            ),
            create_mock_gitlab_project("utils", "team/utils", "Utility functions"),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="authentication"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "team/gateway"

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, gitlab_provider):
        """Test that search is case-insensitive."""
        projects = [
            create_mock_gitlab_project("MyProject", "team/MyProject", "IMPORTANT"),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="myproject"
            )
        assert len(result.repositories) == 1

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="important"
            )
        assert len(result.repositories) == 1

    @pytest.mark.asyncio
    async def test_search_no_matches(self, gitlab_provider):
        """Test that search returns empty list when no matches."""
        projects = [
            create_mock_gitlab_project(
                "api-service", "team/api-service", "API backend"
            ),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="nonexistent"
            )

        assert len(result.repositories) == 0

    @pytest.mark.asyncio
    async def test_search_empty_string_returns_all(self, gitlab_provider):
        """Test that empty search string returns all repositories."""
        projects = [
            create_mock_gitlab_project("project-a", "team/project-a"),
            create_mock_gitlab_project("project-b", "team/project-b"),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search=""
            )
        assert len(result.repositories) == 2

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search=None
            )
        assert len(result.repositories) == 2

    @pytest.mark.asyncio
    async def test_search_special_characters_handled_safely(self, gitlab_provider):
        """Test that special characters in search are handled safely."""
        projects = [
            create_mock_gitlab_project(
                "test-project", "team/test-project", "Test (v1.0)"
            ),
        ]
        mock_response = create_mock_response(projects)

        special_searches = ["(v1.0)", "[test]", "test.*", "test/path"]
        for search_term in special_searches:
            with patch.object(
                gitlab_provider, "_make_api_request", return_value=mock_response
            ):
                result = await gitlab_provider.discover_repositories(
                    page=1, page_size=50, search=search_term
                )
                assert isinstance(result.repositories, list)

    @pytest.mark.asyncio
    async def test_search_with_null_description(self, gitlab_provider):
        """Test that search handles repositories with null description."""
        projects = [
            create_mock_gitlab_project("no-desc", "team/no-desc", None),
            create_mock_gitlab_project("target", "team/target", "Has description"),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="target"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "team/target"

    @pytest.mark.asyncio
    async def test_search_applies_after_indexed_repo_exclusion(self, gitlab_provider):
        """Test that search filter is applied after excluding already-indexed repos."""
        gitlab_provider._golden_repo_manager.list_golden_repos.return_value = [
            {"repo_url": "https://gitlab.com/team/auth-service.git"}
        ]

        projects = [
            create_mock_gitlab_project("auth-service", "team/auth-service", "Indexed"),
            create_mock_gitlab_project(
                "auth-middleware", "team/auth-middleware", "Not indexed"
            ),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="auth"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "team/auth-middleware"

    @pytest.mark.asyncio
    async def test_search_by_commit_hash_matches(self, gitlab_provider):
        """Search by commit hash should find matching repos."""
        projects = [
            create_mock_gitlab_project(
                "project-a",
                "team/project-a",
                "Desc A",
                last_commit_hash="abc1234def5678",
                last_commit_author="John Doe",
            ),
            create_mock_gitlab_project(
                "project-b",
                "team/project-b",
                "Desc B",
                last_commit_hash="xyz9999fff1111",
                last_commit_author="Jane Smith",
            ),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="abc1234"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "team/project-a"

    @pytest.mark.asyncio
    async def test_search_by_committer_matches(self, gitlab_provider):
        """Search by committer name should find matching repos."""
        projects = [
            create_mock_gitlab_project(
                "project-a",
                "team/project-a",
                "Desc A",
                last_commit_hash="abc1234def5678",
                last_commit_author="John Doe",
            ),
            create_mock_gitlab_project(
                "project-b",
                "team/project-b",
                "Desc B",
                last_commit_hash="xyz9999fff1111",
                last_commit_author="Jane Smith",
            ),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="jane"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "team/project-b"

    @pytest.mark.asyncio
    async def test_search_by_committer_case_insensitive(self, gitlab_provider):
        """Search by committer should be case insensitive."""
        projects = [
            create_mock_gitlab_project(
                "project-a",
                "team/project-a",
                "Desc A",
                last_commit_hash="abc1234def5678",
                last_commit_author="John Doe",
            ),
        ]
        mock_response = create_mock_response(projects)

        # Search with different case variations
        for search_term in ["john", "JOHN", "John", "doe", "DOE"]:
            with patch.object(
                gitlab_provider, "_make_api_request", return_value=mock_response
            ):
                result = await gitlab_provider.discover_repositories(
                    page=1, page_size=50, search=search_term
                )
            assert len(result.repositories) == 1, f"Search '{search_term}' should match"

    @pytest.mark.asyncio
    async def test_search_with_null_commit_info(self, gitlab_provider):
        """Search should handle repos with null commit info gracefully."""
        projects = [
            create_mock_gitlab_project(
                "no-commit",
                "team/no-commit",
                "No commit info",
            ),
            create_mock_gitlab_project(
                "has-commit",
                "team/has-commit",
                "Has commit info",
                last_commit_hash="abc1234",
                last_commit_author="Author",
            ),
        ]
        mock_response = create_mock_response(projects)

        with patch.object(
            gitlab_provider, "_make_api_request", return_value=mock_response
        ):
            result = await gitlab_provider.discover_repositories(
                page=1, page_size=50, search="abc1234"
            )

        # Should only find the one with commit info, not crash on null
        assert len(result.repositories) == 1
        assert result.repositories[0].name == "team/has-commit"


def create_mock_github_repo(
    name: str,
    full_name: str,
    description: Optional[str] = None,
    private: bool = False,
    last_commit_hash: Optional[str] = None,
    last_commit_author: Optional[str] = None,
) -> dict:
    """Helper to create mock GitHub repo API response."""
    repo = {
        "id": hash(name) % 10000,
        "name": name,
        "full_name": full_name,
        "description": description,
        "clone_url": f"https://github.com/{full_name}.git",
        "ssh_url": f"git@github.com:{full_name}.git",
        "default_branch": "main",
        "pushed_at": "2024-01-15T10:30:00Z",
        "private": private,
    }
    # Add commit info if provided (simulating extended API data)
    if last_commit_hash or last_commit_author:
        repo["_last_commit_hash"] = last_commit_hash
        repo["_last_commit_author"] = last_commit_author
    return repo


@pytest.fixture
def github_provider():
    """Create a GitHub provider with mocked dependencies."""
    from code_indexer.server.services.repository_providers.github_provider import (
        GitHubProvider,
    )
    from code_indexer.server.services.ci_token_manager import TokenData

    token_manager = MagicMock()
    token_manager.get_token.return_value = TokenData(
        platform="github",
        token="ghp_test123456789012345678901234567890",
        base_url=None,
    )
    golden_repo_manager = MagicMock()
    golden_repo_manager.list_golden_repos.return_value = []

    return GitHubProvider(
        token_manager=token_manager,
        golden_repo_manager=golden_repo_manager,
    )


def create_github_mock_response(repos: list, link_header: str = ""):
    """Create a mock HTTP response for GitHub API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Link": link_header} if link_header else {}
    mock_response.json.return_value = repos
    mock_response.raise_for_status = MagicMock()
    return mock_response


class TestGitHubProviderSearchFilter:
    """Tests for GitHub provider search filtering."""

    @pytest.mark.asyncio
    async def test_search_by_name_matches(self, github_provider):
        """Test that search matches repository name substring."""
        repos = [
            create_mock_github_repo("auth-lib", "owner/auth-lib", "Auth library"),
            create_mock_github_repo("payment-sdk", "owner/payment-sdk", "Payment SDK"),
        ]
        mock_response = create_github_mock_response(repos)

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search="auth"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "owner/auth-lib"

    @pytest.mark.asyncio
    async def test_search_by_description_matches(self, github_provider):
        """Test that search matches repository description substring."""
        repos = [
            create_mock_github_repo(
                "gateway", "owner/gateway", "API with authentication"
            ),
            create_mock_github_repo("utils", "owner/utils", "Utility functions"),
        ]
        mock_response = create_github_mock_response(repos)

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search="authentication"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "owner/gateway"

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, github_provider):
        """Test that search is case-insensitive."""
        repos = [
            create_mock_github_repo("AwesomeProject", "owner/AwesomeProject", "GREAT"),
        ]
        mock_response = create_github_mock_response(repos)

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search="awesome"
            )
        assert len(result.repositories) == 1

    @pytest.mark.asyncio
    async def test_search_no_matches(self, github_provider):
        """Test that search returns empty list when no matches."""
        repos = [
            create_mock_github_repo(
                "my-service", "owner/my-service", "Service backend"
            ),
        ]
        mock_response = create_github_mock_response(repos)

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search="nonexistent"
            )

        assert len(result.repositories) == 0

    @pytest.mark.asyncio
    async def test_search_empty_string_returns_all(self, github_provider):
        """Test that empty search string returns all repositories."""
        repos = [
            create_mock_github_repo("repo-a", "owner/repo-a"),
            create_mock_github_repo("repo-b", "owner/repo-b"),
        ]
        mock_response = create_github_mock_response(repos)

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search=""
            )
        assert len(result.repositories) == 2

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search=None
            )
        assert len(result.repositories) == 2

    @pytest.mark.asyncio
    async def test_search_special_characters_handled_safely(self, github_provider):
        """Test that special characters in search are handled safely."""
        repos = [
            create_mock_github_repo("test-repo", "owner/test-repo", "Test (v2.0)"),
        ]
        mock_response = create_github_mock_response(repos)

        special_searches = ["(v2.0)", "[test]", "test.*", "test/path"]
        for search_term in special_searches:
            with patch.object(
                github_provider, "_make_api_request", return_value=mock_response
            ):
                result = await github_provider.discover_repositories(
                    page=1, page_size=50, search=search_term
                )
                assert isinstance(result.repositories, list)

    @pytest.mark.asyncio
    async def test_search_by_commit_hash_matches(self, github_provider):
        """Search by commit hash should find matching repos."""
        repos = [
            create_mock_github_repo(
                "repo-a",
                "owner/repo-a",
                "Desc A",
                last_commit_hash="abc1234def5678",
                last_commit_author="John Doe",
            ),
            create_mock_github_repo(
                "repo-b",
                "owner/repo-b",
                "Desc B",
                last_commit_hash="xyz9999fff1111",
                last_commit_author="Jane Smith",
            ),
        ]
        mock_response = create_github_mock_response(repos)

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search="abc1234"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "owner/repo-a"

    @pytest.mark.asyncio
    async def test_search_by_committer_matches(self, github_provider):
        """Search by committer name should find matching repos."""
        repos = [
            create_mock_github_repo(
                "repo-a",
                "owner/repo-a",
                "Desc A",
                last_commit_hash="abc1234def5678",
                last_commit_author="John Doe",
            ),
            create_mock_github_repo(
                "repo-b",
                "owner/repo-b",
                "Desc B",
                last_commit_hash="xyz9999fff1111",
                last_commit_author="Jane Smith",
            ),
        ]
        mock_response = create_github_mock_response(repos)

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search="jane"
            )

        assert len(result.repositories) == 1
        assert result.repositories[0].name == "owner/repo-b"

    @pytest.mark.asyncio
    async def test_search_by_committer_case_insensitive(self, github_provider):
        """Search by committer should be case insensitive."""
        repos = [
            create_mock_github_repo(
                "repo-a",
                "owner/repo-a",
                "Desc A",
                last_commit_hash="abc1234def5678",
                last_commit_author="John Doe",
            ),
        ]
        mock_response = create_github_mock_response(repos)

        # Search with different case variations
        for search_term in ["john", "JOHN", "John", "doe", "DOE"]:
            with patch.object(
                github_provider, "_make_api_request", return_value=mock_response
            ):
                result = await github_provider.discover_repositories(
                    page=1, page_size=50, search=search_term
                )
            assert len(result.repositories) == 1, f"Search '{search_term}' should match"

    @pytest.mark.asyncio
    async def test_search_with_null_commit_info(self, github_provider):
        """Search should handle repos with null commit info gracefully."""
        repos = [
            create_mock_github_repo(
                "no-commit",
                "owner/no-commit",
                "No commit info",
            ),
            create_mock_github_repo(
                "has-commit",
                "owner/has-commit",
                "Has commit info",
                last_commit_hash="abc1234",
                last_commit_author="Author",
            ),
        ]
        mock_response = create_github_mock_response(repos)

        with patch.object(
            github_provider, "_make_api_request", return_value=mock_response
        ):
            result = await github_provider.discover_repositories(
                page=1, page_size=50, search="abc1234"
            )

        # Should only find the one with commit info, not crash on null
        assert len(result.repositories) == 1
        assert result.repositories[0].name == "owner/has-commit"
