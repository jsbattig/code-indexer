"""Integration tests for MCP tool handlers."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from code_indexer.server.mcp.handlers import (
    search_code,
    list_repositories,
    activate_repository,
    deactivate_repository,
    get_repository_status,
    sync_repository,
    switch_branch,
    list_files,
    get_file_content,
    browse_directory,
    get_branches,
    check_health,
    add_golden_repo,
    remove_golden_repo,
    refresh_golden_repo,
    list_users,
    create_user,
    get_repository_statistics,
    get_job_statistics,
    get_all_repositories_status,
    manage_composite_repository,
    discover_repositories,
    HANDLER_REGISTRY,
)
from code_indexer.server.auth.user_manager import User, UserRole
from datetime import datetime, timezone


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.role = UserRole.NORMAL_USER
    user.has_permission = Mock(return_value=True)
    return user


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user for testing."""
    user = Mock(spec=User)
    user.username = "admin"
    user.role = UserRole.ADMIN
    user.has_permission = Mock(return_value=True)
    return user


class TestHandlerRegistry:
    """Test handler registry completeness."""

    def test_all_22_handlers_registered(self):
        """Verify all 22 tool handlers are registered."""
        expected_handlers = [
            "search_code",
            "discover_repositories",
            "list_repositories",
            "activate_repository",
            "deactivate_repository",
            "get_repository_status",
            "sync_repository",
            "switch_branch",
            "list_files",
            "get_file_content",
            "browse_directory",
            "get_branches",
            "check_health",
            "add_golden_repo",
            "remove_golden_repo",
            "refresh_golden_repo",
            "list_users",
            "create_user",
            "get_repository_statistics",
            "get_job_statistics",
            "get_all_repositories_status",
            "manage_composite_repository",
        ]

        assert len(HANDLER_REGISTRY) == 22, f"Expected 22 handlers, found {len(HANDLER_REGISTRY)}"
        
        for handler_name in expected_handlers:
            assert handler_name in HANDLER_REGISTRY, f"Handler '{handler_name}' not registered"

    def test_all_handlers_are_coroutines(self):
        """Verify all handlers are async functions."""
        import inspect

        for handler_name, handler_func in HANDLER_REGISTRY.items():
            assert inspect.iscoroutinefunction(handler_func), \
                f"Handler '{handler_name}' is not an async function"


@pytest.mark.asyncio
class TestSearchCode:
    """Test search_code handler."""

    async def test_search_code_success(self, mock_user):
        """Test successful code search."""
        params = {
            "query_text": "authentication",
            "limit": 10,
            "search_mode": "semantic",
        }

        with patch("code_indexer.server.app.search_service") as mock_service:
            mock_service.semantic_search = AsyncMock(return_value=[{"file": "auth.py"}])
            
            result = await search_code(params, mock_user)

            assert result["success"] is True
            assert "results" in result

    async def test_search_code_error_handling(self, mock_user):
        """Test search_code error handling."""
        params = {"query_text": "test"}

        with patch("code_indexer.server.app.search_service") as mock_service:
            mock_service.semantic_search = AsyncMock(side_effect=Exception("Search failed"))
            
            result = await search_code(params, mock_user)

            assert result["success"] is False
            assert "error" in result
            assert result["results"] == []


@pytest.mark.asyncio
class TestListRepositories:
    """Test list_repositories handler."""

    async def test_list_repositories_success(self, mock_user):
        """Test successful repository listing."""
        mock_repos = [
            {"user_alias": "repo1", "golden_repo_alias": "golden1"},
            {"user_alias": "repo2", "golden_repo_alias": "golden2"},
        ]

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.list_activated_repositories = Mock(return_value=mock_repos)
            
            result = await list_repositories({}, mock_user)

            assert result["success"] is True
            assert len(result["repositories"]) == 2

    async def test_list_repositories_error_handling(self, mock_user):
        """Test list_repositories error handling."""
        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.list_activated_repositories = Mock(side_effect=Exception("DB error"))
            
            result = await list_repositories({}, mock_user)

            assert result["success"] is False
            assert result["repositories"] == []


@pytest.mark.asyncio
class TestActivateRepository:
    """Test activate_repository handler."""

    async def test_activate_single_repository(self, mock_user):
        """Test activating a single repository."""
        params = {
            "golden_repo_alias": "my-repo",
            "branch_name": "main",
        }

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.activate_repository = Mock(return_value="job-123")
            
            result = await activate_repository(params, mock_user)

            assert result["success"] is True
            assert result["job_id"] == "job-123"

    async def test_activate_composite_repository(self, mock_user):
        """Test activating a composite repository."""
        params = {
            "golden_repo_aliases": ["repo1", "repo2"],
            "user_alias": "my-composite",
        }

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.activate_repository = Mock(return_value="job-456")
            
            result = await activate_repository(params, mock_user)

            assert result["success"] is True
            assert result["job_id"] == "job-456"


@pytest.mark.asyncio
class TestDeactivateRepository:
    """Test deactivate_repository handler."""

    async def test_deactivate_repository_success(self, mock_user):
        """Test successful repository deactivation."""
        params = {"user_alias": "my-repo"}

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.deactivate_repository = Mock(return_value="job-789")
            
            result = await deactivate_repository(params, mock_user)

            assert result["success"] is True
            assert result["job_id"] == "job-789"


@pytest.mark.asyncio
class TestAdminHandlers:
    """Test admin-only handlers."""

    async def test_add_golden_repo(self, mock_admin_user):
        """Test adding a golden repository."""
        params = {
            "url": "https://github.com/user/repo.git",
            "alias": "my-golden-repo",
            "branch": "main",
        }

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.add_golden_repo = Mock(return_value="job-golden-1")
            
            result = await add_golden_repo(params, mock_admin_user)

            assert result["success"] is True
            assert result["job_id"] == "job-golden-1"

    async def test_remove_golden_repo(self, mock_admin_user):
        """Test removing a golden repository."""
        params = {"alias": "my-golden-repo"}

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.remove_golden_repo = Mock()
            
            result = await remove_golden_repo(params, mock_admin_user)

            assert result["success"] is True

    async def test_list_users(self, mock_admin_user):
        """Test listing all users."""
        mock_users = [
            Mock(username="user1", role=UserRole.NORMAL_USER, created_at=datetime.now(timezone.utc)),
            Mock(username="user2", role=UserRole.ADMIN, created_at=datetime.now(timezone.utc)),
        ]

        with patch("code_indexer.server.app.user_manager") as mock_manager:
            mock_manager.get_all_users = Mock(return_value=mock_users)
            
            result = await list_users({}, mock_admin_user)

            assert result["success"] is True
            assert result["total"] == 2

    async def test_create_user(self, mock_admin_user):
        """Test creating a new user."""
        params = {
            "username": "newuser",
            "password": "SecurePass123!",
            "role": "normal_user",
        }

        mock_new_user = Mock(
            username="newuser",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc)
        )

        with patch("code_indexer.server.app.user_manager") as mock_manager:
            mock_manager.create_user = Mock(return_value=mock_new_user)
            
            result = await create_user(params, mock_admin_user)

            assert result["success"] is True
            assert result["user"]["username"] == "newuser"


@pytest.mark.asyncio
class TestFileHandlers:
    """Test file-related handlers."""

    async def test_list_files(self, mock_user):
        """Test listing files in a repository."""
        params = {"repository_alias": "my-repo", "path": "src/"}

        with patch("code_indexer.server.app.file_service") as mock_service:
            mock_service.list_files = AsyncMock(return_value={"files": ["file1.py", "file2.py"]})
            
            result = await list_files(params, mock_user)

            assert result["success"] is True
            assert len(result["files"]) == 2

    async def test_get_file_content(self, mock_user):
        """Test getting file content."""
        params = {
            "repository_alias": "my-repo",
            "file_path": "src/main.py",
        }

        with patch("code_indexer.server.app.file_service") as mock_service:
            mock_service.get_file_content = AsyncMock(
                return_value={"content": "def main():\n    pass", "metadata": {}}
            )
            
            result = await get_file_content(params, mock_user)

            assert result["success"] is True
            assert "content" in result

    async def test_browse_directory(self, mock_user):
        """Test browsing directory structure."""
        params = {
            "repository_alias": "my-repo",
            "path": "src/",
            "recursive": True,
        }

        with patch("code_indexer.server.app.file_service") as mock_service:
            mock_service.browse_directory = AsyncMock(return_value={"src": {"main.py": None}})
            
            result = await browse_directory(params, mock_user)

            assert result["success"] is True
            assert "structure" in result


@pytest.mark.asyncio
class TestHealthCheck:
    """Test health check handler."""

    async def test_check_health(self, mock_user):
        """Test system health check."""
        with patch("code_indexer.server.app.health_service") as mock_service:
            mock_service.check_health = AsyncMock(
                return_value={"status": "healthy", "uptime": 3600}
            )
            
            result = await check_health({}, mock_user)

            assert result["success"] is True
            assert "health" in result


@pytest.mark.asyncio
class TestStatisticsHandlers:
    """Test statistics handlers."""

    async def test_get_repository_statistics(self, mock_user):
        """Test getting repository statistics."""
        params = {"repository_alias": "my-repo"}

        with patch("code_indexer.server.app.stats_service") as mock_service:
            mock_service.get_repository_statistics = AsyncMock(
                return_value={"file_count": 100, "total_lines": 5000}
            )
            
            result = await get_repository_statistics(params, mock_user)

            assert result["success"] is True
            assert "statistics" in result

    async def test_get_job_statistics(self, mock_user):
        """Test getting job statistics."""
        with patch("code_indexer.server.app.background_job_manager") as mock_manager:
            mock_manager.get_job_statistics = Mock(
                return_value={"total": 50, "pending": 5, "completed": 45}
            )
            
            result = await get_job_statistics({}, mock_user)

            assert result["success"] is True
            assert "statistics" in result


@pytest.mark.asyncio
class TestCompositeRepository:
    """Test composite repository management."""

    async def test_create_composite_repository(self, mock_user):
        """Test creating a composite repository."""
        params = {
            "operation": "create",
            "user_alias": "my-composite",
            "golden_repo_aliases": ["repo1", "repo2", "repo3"],
        }

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.activate_repository = Mock(return_value="job-composite-1")
            
            result = await manage_composite_repository(params, mock_user)

            assert result["success"] is True
            assert result["job_id"] == "job-composite-1"

    async def test_delete_composite_repository(self, mock_user):
        """Test deleting a composite repository."""
        params = {
            "operation": "delete",
            "user_alias": "my-composite",
        }

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.deactivate_repository = Mock(return_value="job-deactivate-1")
            
            result = await manage_composite_repository(params, mock_user)

            assert result["success"] is True
