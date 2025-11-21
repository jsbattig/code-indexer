"""Integration tests for MCP tool handlers."""

import pytest
from unittest.mock import Mock, patch
from code_indexer.server.mcp.handlers import (
    search_code,
    list_repositories,
    activate_repository,
    deactivate_repository,
    list_files,
    get_file_content,
    browse_directory,
    check_health,
    add_golden_repo,
    remove_golden_repo,
    list_users,
    create_user,
    get_repository_statistics,
    get_job_statistics,
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


@pytest.mark.e2e
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

        assert (
            len(HANDLER_REGISTRY) == 22
        ), f"Expected 22 handlers, found {len(HANDLER_REGISTRY)}"

        for handler_name in expected_handlers:
            assert (
                handler_name in HANDLER_REGISTRY
            ), f"Handler '{handler_name}' not registered"

    def test_all_handlers_are_coroutines(self):
        """Verify all handlers are async functions."""
        import inspect

        for handler_name, handler_func in HANDLER_REGISTRY.items():
            assert inspect.iscoroutinefunction(
                handler_func
            ), f"Handler '{handler_name}' is not an async function"


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSearchCode:
    """Test search_code handler."""

    async def test_search_code_success(self, mock_user):
        """Test successful code search."""
        params = {
            "query_text": "authentication",
            "limit": 10,
        }

        with patch(
            "code_indexer.server.app.semantic_query_manager"
        ) as mock_query_manager:
            mock_query_manager.query_user_repositories = Mock(
                return_value={
                    "results": [
                        {
                            "file_path": "auth.py",
                            "score": 0.9,
                            "line_start": 1,
                            "line_end": 10,
                            "content": "auth code",
                            "language": "python",
                        }
                    ],
                    "total_results": 1,
                    "query_metadata": {
                        "query_text": "authentication",
                        "execution_time_ms": 100,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }
            )

            result = await search_code(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])
            assert data["success"] is True
            assert "results" in data

    async def test_search_code_error_handling(self, mock_user):
        """Test search_code error handling."""
        params = {"query_text": "test"}

        with patch(
            "code_indexer.server.app.semantic_query_manager"
        ) as mock_query_manager:
            mock_query_manager.query_user_repositories = Mock(
                side_effect=Exception("Search failed")
            )

            result = await search_code(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is False
            assert "error" in data
            assert data["results"] == []

    async def test_search_code_with_activated_repository(self, mock_user):
        """Test search_code uses semantic_query_manager for activated repositories."""
        params = {
            "query_text": "function",
            "repository_alias": "my-tries",
            "limit": 10,
            "min_score": 0.5,
        }

        with patch(
            "code_indexer.server.app.semantic_query_manager"
        ) as mock_query_manager:
            mock_query_manager.query_user_repositories = Mock(
                return_value={
                    "results": [
                        {
                            "file_path": "test.py",
                            "score": 0.9,
                            "line_start": 1,
                            "line_end": 10,
                            "content": "def function():\n    pass",
                            "language": "python",
                        }
                    ],
                    "total_results": 1,
                    "query_metadata": {
                        "query_text": "function",
                        "execution_time_ms": 100,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }
            )

            result = await search_code(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert "results" in data
            assert len(data["results"]["results"]) == 1

            mock_query_manager.query_user_repositories.assert_called_once_with(
                username=mock_user.username,
                query_text="function",
                repository_alias="my-tries",
                limit=10,
                min_score=0.5,
                file_extensions=None,
                language=None,
                exclude_language=None,
                path_filter=None,
                exclude_path=None,
                accuracy="balanced",
                # Temporal parameters (Story #446)
                time_range=None,
                at_commit=None,
                include_removed=False,
                show_evolution=False,
                evolution_limit=None,
                # FTS parameters (Story #503 Phase 2)
                case_sensitive=False,
                fuzzy=False,
                edit_distance=0,
                snippet_lines=5,
                regex=False,
            )

    async def test_search_code_with_fts_parameters(self, mock_user):
        """Test search_code passes FTS parameters through to semantic_query_manager.

        This is a RED test proving Phase 2 requirement: FTS parameters must be
        wired through the complete call chain.
        """
        params = {
            "query_text": "authenticate",
            "repository_alias": "test-repo",
            "limit": 5,
            "case_sensitive": True,
            "fuzzy": True,
            "edit_distance": 2,
            "snippet_lines": 10,
            "regex": False,
        }

        with patch(
            "code_indexer.server.app.semantic_query_manager"
        ) as mock_query_manager:
            mock_query_manager.query_user_repositories = Mock(
                return_value={
                    "results": [],
                    "total_results": 0,
                    "query_metadata": {
                        "query_text": "authenticate",
                        "execution_time_ms": 50,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }
            )

            await search_code(params, mock_user)

            # Verify FTS parameters were passed to query manager
            mock_query_manager.query_user_repositories.assert_called_once_with(
                username=mock_user.username,
                query_text="authenticate",
                repository_alias="test-repo",
                limit=5,
                min_score=0.5,
                file_extensions=None,
                language=None,
                exclude_language=None,
                path_filter=None,
                exclude_path=None,
                accuracy="balanced",
                # Temporal parameters (Story #446)
                time_range=None,
                at_commit=None,
                include_removed=False,
                show_evolution=False,
                evolution_limit=None,
                # FTS parameters that MUST be passed through
                case_sensitive=True,
                fuzzy=True,
                edit_distance=2,
                snippet_lines=10,
                regex=False,
            )


@pytest.mark.asyncio
@pytest.mark.e2e
class TestDiscoverRepositories:
    """Test discover_repositories handler."""

    async def test_discover_repositories_success(self, mock_user):
        """Test successful repository discovery.

        Should list all golden repositories from golden_repo_manager.
        """
        params = {}  # No params needed - lists all repos

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.list_golden_repos = Mock(
                return_value=[{"alias": "repo1"}, {"alias": "repo2"}]
            )

            result = await discover_repositories(params, mock_user)

            # Verify list_golden_repos was called
            mock_manager.list_golden_repos.assert_called_once()

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert len(data["repositories"]) == 2
            assert data["repositories"][0]["alias"] == "repo1"
            assert data["repositories"][1]["alias"] == "repo2"


@pytest.mark.asyncio
@pytest.mark.e2e
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

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert len(data["repositories"]) == 2

    async def test_list_repositories_error_handling(self, mock_user):
        """Test list_repositories error handling."""
        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.list_activated_repositories = Mock(
                side_effect=Exception("DB error")
            )

            result = await list_repositories({}, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is False
            assert data["repositories"] == []


@pytest.mark.asyncio
@pytest.mark.e2e
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

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["job_id"] == "job-123"

    async def test_activate_composite_repository(self, mock_user):
        """Test activating a composite repository."""
        params = {
            "golden_repo_aliases": ["repo1", "repo2"],
            "user_alias": "my-composite",
        }

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.activate_repository = Mock(return_value="job-456")

            result = await activate_repository(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["job_id"] == "job-456"


@pytest.mark.asyncio
@pytest.mark.e2e
class TestDeactivateRepository:
    """Test deactivate_repository handler."""

    async def test_deactivate_repository_success(self, mock_user):
        """Test successful repository deactivation."""
        params = {"user_alias": "my-repo"}

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.deactivate_repository = Mock(return_value="job-789")

            result = await deactivate_repository(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["job_id"] == "job-789"


@pytest.mark.asyncio
@pytest.mark.e2e
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
            mock_manager.add_golden_repo = Mock(
                return_value={
                    "success": True,
                    "message": "Golden repository 'my-golden-repo' added successfully",
                }
            )

            result = await add_golden_repo(params, mock_admin_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert "message" in data

    async def test_remove_golden_repo(self, mock_admin_user):
        """Test removing a golden repository."""
        params = {"alias": "my-golden-repo"}

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            # Mock to return job_id (async version)
            mock_manager.remove_golden_repo = Mock(return_value="test-job-id-12345")

            result = await remove_golden_repo(params, mock_admin_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["job_id"] == "test-job-id-12345"
            assert "removal started" in data["message"]

    async def test_list_users(self, mock_admin_user):
        """Test listing all users."""
        mock_users = [
            Mock(
                username="user1",
                role=UserRole.NORMAL_USER,
                created_at=datetime.now(timezone.utc),
            ),
            Mock(
                username="user2",
                role=UserRole.ADMIN,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        with patch("code_indexer.server.app.user_manager") as mock_manager:
            mock_manager.get_all_users = Mock(return_value=mock_users)

            result = await list_users({}, mock_admin_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["total"] == 2

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
            created_at=datetime.now(timezone.utc),
        )

        with patch("code_indexer.server.app.user_manager") as mock_manager:
            mock_manager.create_user = Mock(return_value=mock_new_user)

            result = await create_user(params, mock_admin_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["user"]["username"] == "newuser"


@pytest.mark.asyncio
@pytest.mark.e2e
class TestFileHandlers:
    """Test file-related handlers."""

    async def test_list_files(self, mock_user):
        """Test listing files in a repository."""
        params = {"repository_alias": "my-repo", "path": "src/"}

        with patch("code_indexer.server.app.file_service") as mock_service:
            # list_files is NOT async, use Mock not AsyncMock
            mock_service.list_files = Mock(
                return_value={"files": ["file1.py", "file2.py"]}
            )

            result = await list_files(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert len(data["files"]) == 2

    async def test_list_files_with_fileinfo_objects(self, mock_user):
        """Test list_files properly serializes FileInfo objects with datetime fields."""
        from code_indexer.server.models.api_models import (
            FileInfo,
            FileListResponse,
            PaginationInfo,
        )

        params = {"repository_alias": "my-repo", "path": "src/"}

        # Create FileInfo objects with datetime fields (as returned by actual service)
        file_info_1 = FileInfo(
            path="src/main.py",
            size_bytes=1024,
            modified_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            language="python",
            is_indexed=True,
        )
        file_info_2 = FileInfo(
            path="src/utils.py",
            size_bytes=512,
            modified_at=datetime(2024, 1, 2, 14, 30, 0, tzinfo=timezone.utc),
            language="python",
            is_indexed=False,
        )

        # Create proper PaginationInfo object
        pagination = PaginationInfo(page=1, limit=500, total=2, has_next=False)

        # Mock service returns FileListResponse with FileInfo objects
        mock_response = FileListResponse(
            files=[file_info_1, file_info_2],
            pagination=pagination,
        )

        with patch("code_indexer.server.app.file_service") as mock_service:
            mock_service.list_files = Mock(return_value=mock_response)

            result = await list_files(params, mock_user)

            # MCP format: parse content array
            import json

            # This should NOT raise "Object of type FileInfo is not JSON serializable"
            # or "Object of type datetime is not JSON serializable"
            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert len(data["files"]) == 2

            # Verify datetime fields are properly serialized as ISO format strings
            assert data["files"][0]["path"] == "src/main.py"
            assert data["files"][0]["size_bytes"] == 1024
            assert (
                data["files"][0]["modified_at"] == "2024-01-01T12:00:00Z"
            )  # ISO format
            assert data["files"][0]["language"] == "python"
            assert data["files"][0]["is_indexed"] is True

            assert data["files"][1]["path"] == "src/utils.py"
            assert data["files"][1]["size_bytes"] == 512
            assert (
                data["files"][1]["modified_at"] == "2024-01-02T14:30:00Z"
            )  # ISO format
            assert data["files"][1]["language"] == "python"
            assert data["files"][1]["is_indexed"] is False

    async def test_get_file_content(self, mock_user):
        """Test getting file content."""
        params = {
            "repository_alias": "my-repo",
            "file_path": "src/main.py",
        }

        with patch("code_indexer.server.app.file_service") as mock_service:
            # get_file_content is NOT async, use Mock not AsyncMock
            mock_service.get_file_content = Mock(
                return_value={
                    "content": "def main():\n    pass",
                    "metadata": {"size": 100},
                }
            )

            result = await get_file_content(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert "content" in data
            # MCP spec: content must be an array of content blocks
            assert isinstance(data["content"], list), "content must be an array"
            assert len(data["content"]) > 0, "content array must not be empty"
            # First content block must have type and text fields
            assert (
                "type" in result["content"][0]
            ), "content block must have 'type' field"
            assert (
                result["content"][0]["type"] == "text"
            ), "content block type must be 'text'"
            assert (
                "text" in result["content"][0]
            ), "content block must have 'text' field"
            assert data["content"][0]["text"] == "def main():\n    pass"
            # Metadata should still be returned
            assert "metadata" in data
            assert data["metadata"]["size"] == 100

    async def test_get_file_content_error(self, mock_user):
        """Test get_file_content error handling returns MCP-compliant format."""
        params = {
            "repository_alias": "my-repo",
            "file_path": "nonexistent.py",
        }

        with patch("code_indexer.server.app.file_service") as mock_service:
            # get_file_content is NOT async, use Mock not AsyncMock
            mock_service.get_file_content = Mock(
                side_effect=Exception("File not found")
            )

            result = await get_file_content(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is False
            assert "error" in data
            # Even on error, content should be array (empty array is valid)
            assert isinstance(
                result["content"], list
            ), "content must be an array even on error"
            assert data["content"] == [], "content should be empty array on error"

    async def test_browse_directory(self, mock_user):
        """Test browsing directory structure.

        FileListingService doesn't have browse_directory method.
        Should use list_files method with path patterns instead.
        """
        params = {
            "repository_alias": "my-repo",
            "path": "src/",
            "recursive": True,
        }

        with patch("code_indexer.server.app.file_service") as mock_service:
            # Mock FileListResponse with files attribute
            mock_response = Mock()
            mock_response.files = [
                Mock(
                    path="src/main.py",
                    size_bytes=1024,
                    modified_at=datetime.now(timezone.utc),
                    language="python",
                    is_indexed=True,
                    model_dump=lambda mode=None: {
                        "path": "src/main.py",
                        "size_bytes": 1024,
                        "modified_at": datetime.now(timezone.utc).isoformat(),
                        "language": "python",
                        "is_indexed": True,
                    },
                ),
            ]
            mock_service.list_files = Mock(return_value=mock_response)

            result = await browse_directory(params, mock_user)

            # Verify list_files was called (not browse_directory which doesn't exist)
            mock_service.list_files.assert_called_once()

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert "structure" in data
            assert len(data["structure"]["files"]) >= 1


@pytest.mark.asyncio
@pytest.mark.e2e
class TestHealthCheck:
    """Test health check handler."""

    async def test_check_health(self, mock_user):
        """Test system health check."""
        with patch(
            "code_indexer.server.services.health_service.health_service"
        ) as mock_service:
            mock_response = Mock()
            mock_response.model_dump = Mock(
                return_value={"status": "healthy", "uptime": 3600}
            )
            mock_service.get_system_health = Mock(return_value=mock_response)

            result = await check_health({}, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert "health" in data


@pytest.mark.asyncio
@pytest.mark.e2e
class TestRepositoryStatus:
    """Test get_repository_status handler."""

    async def test_get_repository_status_activated_repo(self, mock_user):
        """Test getting status for activated repository.

        Should look in activated repos (user workspace) not golden repos.
        Uses repository_listing_manager.get_repository_details with username.
        """
        from code_indexer.server.mcp.handlers import get_repository_status

        params = {"user_alias": "my-activated-repo"}

        with patch(
            "code_indexer.server.app.repository_listing_manager"
        ) as mock_manager:
            mock_manager.get_repository_details = Mock(
                return_value={
                    "alias": "my-activated-repo",
                    "repo_url": "https://github.com/user/repo.git",
                    "current_branch": "main",
                    "activation_status": "activated",
                    "file_count": 150,
                }
            )

            result = await get_repository_status(params, mock_user)

            # Verify correct method called with username
            mock_manager.get_repository_details.assert_called_once_with(
                "my-activated-repo", mock_user.username
            )

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["status"]["alias"] == "my-activated-repo"
            assert data["status"]["activation_status"] == "activated"


@pytest.mark.asyncio
@pytest.mark.e2e
class TestStatisticsHandlers:
    """Test statistics handlers."""

    async def test_get_repository_statistics(self, mock_user):
        """Test getting repository statistics."""
        params = {"repository_alias": "my-repo"}

        with patch(
            "code_indexer.server.services.stats_service.stats_service"
        ) as mock_service:
            mock_response = Mock()
            mock_response.model_dump = Mock(
                return_value={"file_count": 100, "total_lines": 5000}
            )
            mock_service.get_repository_stats = Mock(return_value=mock_response)

            result = await get_repository_statistics(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert "statistics" in data

    async def test_get_job_statistics(self, mock_user):
        """Test getting job statistics.

        BackgroundJobManager doesn't have get_job_statistics method.
        Should use get_active_job_count, get_pending_job_count, get_failed_job_count instead.
        """
        with patch("code_indexer.server.app.background_job_manager") as mock_manager:
            mock_manager.get_active_job_count = Mock(return_value=5)
            mock_manager.get_pending_job_count = Mock(return_value=10)
            mock_manager.get_failed_job_count = Mock(return_value=2)

            result = await get_job_statistics({}, mock_user)

            # Verify actual methods called
            mock_manager.get_active_job_count.assert_called_once()
            mock_manager.get_pending_job_count.assert_called_once()
            mock_manager.get_failed_job_count.assert_called_once()

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert "statistics" in data
            assert data["statistics"]["active"] == 5
            assert data["statistics"]["pending"] == 10
            assert data["statistics"]["failed"] == 2
            assert data["statistics"]["total"] == 17  # 5 + 10 + 2


@pytest.mark.asyncio
@pytest.mark.e2e
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

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["job_id"] == "job-composite-1"

    async def test_delete_composite_repository(self, mock_user):
        """Test deleting a composite repository."""
        params = {
            "operation": "delete",
            "user_alias": "my-composite",
        }

        with patch("code_indexer.server.app.activated_repo_manager") as mock_manager:
            mock_manager.deactivate_repository = Mock(return_value="job-deactivate-1")

            result = await manage_composite_repository(params, mock_user)

            # MCP format: parse content array
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSyncRepository:
    """Test sync_repository handler."""

    async def test_sync_repository_submits_background_job(self, mock_user):
        """Test that sync_repository correctly submits a background job."""
        from code_indexer.server.mcp.handlers import sync_repository

        params = {"user_alias": "my-repo"}

        # Mock activated_repo_manager to return repo info
        mock_repos = [
            {
                "user_alias": "my-repo",
                "golden_repo_alias": "golden-repo",
                "actual_repo_id": "repo-123",
            }
        ]

        with (
            patch("code_indexer.server.app.activated_repo_manager") as mock_repo_mgr,
            patch("code_indexer.server.app.background_job_manager") as mock_job_mgr,
            patch("code_indexer.server.app._execute_repository_sync") as mock_exec_sync,
        ):

            mock_repo_mgr.list_activated_repositories = Mock(return_value=mock_repos)
            mock_job_mgr.submit_job = Mock(return_value="job-sync-123")
            mock_exec_sync.return_value = {"status": "completed"}

            result = await sync_repository(params, mock_user)

            # Verify submit_job was called with correct signature
            mock_job_mgr.submit_job.assert_called_once()
            call_kwargs = mock_job_mgr.submit_job.call_args[1]

            # Check correct parameter names
            assert (
                "operation_type" in call_kwargs
            ), "Must use 'operation_type' parameter"
            assert call_kwargs["operation_type"] == "sync_repository"

            assert "func" in call_kwargs, "Must provide 'func' callable parameter"
            assert callable(call_kwargs["func"]), "func must be callable"

            assert (
                "submitter_username" in call_kwargs
            ), "Must use 'submitter_username' parameter"
            assert call_kwargs["submitter_username"] == mock_user.username

            # Verify MCP response format
            import json

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["job_id"] == "job-sync-123"
            assert "message" in data
