"""Unit tests for ReposAPIClient activation and deactivation methods.

Testing the API client methods required for repository activation lifecycle:
- activate_repository()
- deactivate_repository()
- get_activation_progress() (for monitoring)

Tests follow TDD methodology with failing tests first.
"""

import pytest
from unittest.mock import Mock, patch

from code_indexer.api_clients.repos_client import ReposAPIClient, APIClientError


class TestRepositoryActivationAPI:
    """Test repository activation API client methods."""

    @pytest.fixture
    def repos_client(self):
        """Create ReposAPIClient instance for testing."""
        return ReposAPIClient(
            server_url="https://test-server.com",
            credentials={"username": "test", "password": "test"},
            project_root=None,
        )

    def test_activate_repository_method_exists(self, repos_client):
        """Test that activate_repository method exists."""
        assert hasattr(repos_client, "activate_repository")
        assert callable(repos_client.activate_repository)

    @pytest.mark.asyncio
    async def test_activate_repository_success_response(self, repos_client):
        """Test successful repository activation API call."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 202  # Accepted for async operation
        mock_response.json.return_value = {
            "status": "accepted",
            "activation_id": "act-123",
            "user_alias": "my-repo",
            "golden_alias": "web-service",
            "message": "Repository activation started",
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            result = await repos_client.activate_repository(
                golden_alias="web-service", user_alias="my-repo", target_branch="main"
            )

            assert result["status"] == "accepted"
            assert result["user_alias"] == "my-repo"
            assert result["golden_alias"] == "web-service"
            assert "activation_id" in result

    @pytest.mark.asyncio
    async def test_activate_repository_api_call_parameters(self, repos_client):
        """Test that activate_repository makes correct API call."""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"status": "accepted"}

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ) as mock_request:
            await repos_client.activate_repository(
                golden_alias="web-service",
                user_alias="my-repo",
                target_branch="feature-branch",
            )

            # Should call POST /api/repos/activate
            mock_request.assert_called_once_with(
                "POST",
                "/api/repos/activate",
                json={
                    "golden_alias": "web-service",
                    "user_alias": "my-repo",
                    "target_branch": "feature-branch",
                },
            )

    @pytest.mark.asyncio
    async def test_activate_repository_optional_parameters(self, repos_client):
        """Test activate_repository with optional parameters."""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"status": "accepted"}

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ) as mock_request:
            # Call with only required parameters
            await repos_client.activate_repository(
                golden_alias="web-service", user_alias="my-repo"
            )

            # Should call with None for optional target_branch
            mock_request.assert_called_once_with(
                "POST",
                "/api/repos/activate",
                json={
                    "golden_alias": "web-service",
                    "user_alias": "my-repo",
                    "target_branch": None,
                },
            )

    @pytest.mark.asyncio
    async def test_activate_repository_conflict_error(self, repos_client):
        """Test activation when repository alias already exists."""
        mock_response = Mock()
        mock_response.status_code = 409  # Conflict
        mock_response.json.return_value = {"detail": "Repository alias already in use"}

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError) as exc_info:
                await repos_client.activate_repository(
                    golden_alias="web-service", user_alias="existing-repo"
                )

            assert "Repository alias already in use" in str(exc_info.value)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_activate_repository_not_found_error(self, repos_client):
        """Test activation when golden repository not found."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Golden repository not found"}

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError) as exc_info:
                await repos_client.activate_repository(
                    golden_alias="nonexistent", user_alias="my-repo"
                )

            assert "Golden repository not found" in str(exc_info.value)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_activate_repository_server_error(self, repos_client):
        """Test activation with server error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "detail": "Internal server error during activation"
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError) as exc_info:
                await repos_client.activate_repository(
                    golden_alias="web-service", user_alias="my-repo"
                )

            assert exc_info.value.status_code == 500


class TestRepositoryDeactivationAPI:
    """Test repository deactivation API client methods."""

    @pytest.fixture
    def repos_client(self):
        """Create ReposAPIClient instance for testing."""
        return ReposAPIClient(
            server_url="https://test-server.com",
            credentials={"username": "test", "password": "test"},
            project_root=None,
        )

    def test_deactivate_repository_method_exists(self, repos_client):
        """Test that deactivate_repository method exists."""
        assert hasattr(repos_client, "deactivate_repository")
        assert callable(repos_client.deactivate_repository)

    @pytest.mark.asyncio
    async def test_deactivate_repository_success_response(self, repos_client):
        """Test successful repository deactivation API call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "completed",
            "user_alias": "my-repo",
            "message": "Repository deactivated successfully",
            "cleanup_summary": {
                "containers_stopped": 3,
                "directories_removed": 1,
                "storage_freed": "1.2GB",
            },
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            result = await repos_client.deactivate_repository(
                user_alias="my-repo", force=False
            )

            assert result["status"] == "completed"
            assert result["user_alias"] == "my-repo"
            assert "cleanup_summary" in result

    @pytest.mark.asyncio
    async def test_deactivate_repository_api_call_parameters(self, repos_client):
        """Test that deactivate_repository makes correct API call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "completed"}

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ) as mock_request:
            await repos_client.deactivate_repository(user_alias="my-repo", force=True)

            # Should call DELETE /api/repos/{user_alias}
            mock_request.assert_called_once_with(
                "DELETE", "/api/repos/my-repo", json={"force": True}
            )

    @pytest.mark.asyncio
    async def test_deactivate_repository_not_found_error(self, repos_client):
        """Test deactivation when repository not found."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "detail": "Repository not found or not owned by user"
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError) as exc_info:
                await repos_client.deactivate_repository(
                    user_alias="nonexistent", force=False
                )

            assert "Repository not found" in str(exc_info.value)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_deactivate_repository_conflict_error(self, repos_client):
        """Test deactivation with resource conflicts."""
        mock_response = Mock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            "detail": "Repository has running operations, use --force to override"
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError) as exc_info:
                await repos_client.deactivate_repository(
                    user_alias="busy-repo", force=False
                )

            assert "running operations" in str(exc_info.value)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_deactivate_repository_force_mode(self, repos_client):
        """Test deactivation with force mode."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "completed",
            "message": "Repository forcefully deactivated",
            "warnings": ["Some containers may not have stopped cleanly"],
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ) as mock_request:
            result = await repos_client.deactivate_repository(
                user_alias="problematic-repo", force=True
            )

            # Should send force flag in request
            mock_request.assert_called_once_with(
                "DELETE", "/api/repos/problematic-repo", json={"force": True}
            )

            assert result["status"] == "completed"
            assert "warnings" in result


class TestActivationProgressMonitoring:
    """Test activation progress monitoring API methods."""

    @pytest.fixture
    def repos_client(self):
        """Create ReposAPIClient instance for testing."""
        return ReposAPIClient(
            server_url="https://test-server.com",
            credentials={"username": "test", "password": "test"},
            project_root=None,
        )

    def test_get_activation_progress_method_exists(self, repos_client):
        """Test that get_activation_progress method exists."""
        assert hasattr(repos_client, "get_activation_progress")
        assert callable(repos_client.get_activation_progress)

    @pytest.mark.asyncio
    async def test_get_activation_progress_success(self, repos_client):
        """Test successful activation progress monitoring."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "activation_id": "act-123",
            "status": "in_progress",
            "progress_percent": 65.0,
            "current_step": "indexing",
            "steps_completed": ["cloning", "configuring"],
            "estimated_remaining_seconds": 45,
            "user_alias": "my-repo",
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            result = await repos_client.get_activation_progress(activation_id="act-123")

            assert result["status"] == "in_progress"
            assert result["progress_percent"] == 65.0
            assert result["current_step"] == "indexing"

    @pytest.mark.asyncio
    async def test_get_activation_progress_api_call(self, repos_client):
        """Test that get_activation_progress makes correct API call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "completed"}

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ) as mock_request:
            await repos_client.get_activation_progress(activation_id="act-456")

            # Should call GET /api/repos/activation/{activation_id}/progress
            mock_request.assert_called_once_with(
                "GET", "/api/repos/activation/act-456/progress"
            )

    @pytest.mark.asyncio
    async def test_get_activation_progress_not_found(self, repos_client):
        """Test progress monitoring when activation not found."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "detail": "Activation not found or completed"
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError) as exc_info:
                await repos_client.get_activation_progress(activation_id="nonexistent")

            assert "Activation not found" in str(exc_info.value)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_activation_progress_completed_status(self, repos_client):
        """Test progress monitoring for completed activation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "activation_id": "act-789",
            "status": "completed",
            "progress_percent": 100.0,
            "current_step": "finished",
            "completion_timestamp": "2024-01-15T10:30:00Z",
            "user_alias": "completed-repo",
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            result = await repos_client.get_activation_progress(activation_id="act-789")

            assert result["status"] == "completed"
            assert result["progress_percent"] == 100.0
            assert "completion_timestamp" in result

    @pytest.mark.asyncio
    async def test_get_activation_progress_error_status(self, repos_client):
        """Test progress monitoring for failed activation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "activation_id": "act-error",
            "status": "failed",
            "progress_percent": 45.0,
            "current_step": "cloning",
            "error_message": "Git clone failed: repository not accessible",
            "failure_timestamp": "2024-01-15T10:25:00Z",
        }

        with patch.object(
            repos_client, "_authenticated_request", return_value=mock_response
        ):
            result = await repos_client.get_activation_progress(
                activation_id="act-error"
            )

            assert result["status"] == "failed"
            assert "error_message" in result
            assert "Git clone failed" in result["error_message"]


class TestAPIClientMethodSignatures:
    """Test API client method signatures and parameter validation."""

    @pytest.fixture
    def repos_client(self):
        """Create ReposAPIClient instance for testing."""
        return ReposAPIClient(
            server_url="https://test-server.com",
            credentials={"username": "test", "password": "test"},
            project_root=None,
        )

    def test_activate_repository_required_parameters(self, repos_client):
        """Test activate_repository method signature for required parameters."""
        import inspect

        sig = inspect.signature(repos_client.activate_repository)
        params = sig.parameters

        # Should have golden_alias and user_alias as required
        assert "golden_alias" in params
        assert "user_alias" in params
        assert params["golden_alias"].default == inspect.Parameter.empty
        assert params["user_alias"].default == inspect.Parameter.empty

        # Should have target_branch as optional
        assert "target_branch" in params
        assert params["target_branch"].default is None

    def test_deactivate_repository_required_parameters(self, repos_client):
        """Test deactivate_repository method signature for required parameters."""
        import inspect

        sig = inspect.signature(repos_client.deactivate_repository)
        params = sig.parameters

        # Should have user_alias as required
        assert "user_alias" in params
        assert params["user_alias"].default == inspect.Parameter.empty

        # Should have force as optional
        assert "force" in params
        assert params["force"].default is False

    def test_get_activation_progress_required_parameters(self, repos_client):
        """Test get_activation_progress method signature."""
        import inspect

        sig = inspect.signature(repos_client.get_activation_progress)
        params = sig.parameters

        # Should have activation_id as required
        assert "activation_id" in params
        assert params["activation_id"].default == inspect.Parameter.empty
