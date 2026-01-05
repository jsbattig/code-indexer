"""
Unit tests for SCIP Audit Log API Handler.

Tests the MCP handler for querying SCIP dependency installation audit logs.
Part of AC4: Enhanced Job Status API for Per-Language Audit Access.
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import patch
from code_indexer.server.mcp.handlers import get_scip_audit_log
from code_indexer.server.auth.user_manager import User, UserRole


class TestSCIPAuditLogAPI:
    """Unit tests for get_scip_audit_log API handler."""

    @pytest.fixture
    def admin_user(self):
        """Create admin user for testing."""
        return User(
            username="admin",
            role=UserRole.ADMIN,
            password_hash="hash123",
            created_at=datetime.now(timezone.utc)
        )

    @pytest.fixture
    def normal_user(self):
        """Create normal user for testing."""
        return User(
            username="user",
            role=UserRole.NORMAL_USER,
            password_hash="hash456",
            created_at=datetime.now(timezone.utc)
        )

    @pytest.fixture
    def mock_audit_repo(self):
        """Create mock SCIPAuditRepository."""
        with patch('code_indexer.server.mcp.handlers.scip_audit_repository') as mock_repo:
            yield mock_repo

    @pytest.mark.asyncio
    async def test_get_audit_log_success_admin(self, admin_user, mock_audit_repo):
        """Test successful audit log retrieval by admin user."""
        # Mock repository response
        mock_records = [
            {
                "id": 1,
                "timestamp": "2025-12-31 10:00:00",
                "job_id": "job-1",
                "repo_alias": "test-repo",
                "project_path": "src/project",
                "project_language": "python",
                "project_build_system": "pip",
                "package": "numpy",
                "command": "pip install numpy",
                "reasoning": "Scientific computing",
                "username": "testuser"
            }
        ]
        mock_audit_repo.query_audit_records.return_value = (mock_records, 1)

        # Call handler
        params = {}
        response = await get_scip_audit_log(params, admin_user)

        # Verify response structure
        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"

        # Parse response data
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is True
        assert "records" in data
        assert "total" in data
        assert "filters" in data
        assert len(data["records"]) == 1
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_get_audit_log_permission_denied_non_admin(self, normal_user, mock_audit_repo):
        """Test that non-admin users are denied access."""
        params = {}
        response = await get_scip_audit_log(params, normal_user)

        # Parse response
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "permission" in data["error"].lower() or "admin" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_get_audit_log_filter_by_job_id(self, admin_user, mock_audit_repo):
        """Test filtering audit log by job_id."""
        mock_records = [
            {
                "id": 1,
                "timestamp": "2025-12-31 10:00:00",
                "job_id": "job-1",
                "repo_alias": "test-repo",
                "project_path": "src/project",
                "project_language": "python",
                "project_build_system": "pip",
                "package": "numpy",
                "command": "pip install numpy",
                "reasoning": None,
                "username": "testuser"
            }
        ]
        mock_audit_repo.query_audit_records.return_value = (mock_records, 1)

        # Call handler with job_id filter
        params = {"job_id": "job-1"}
        response = await get_scip_audit_log(params, admin_user)

        # Verify repository was called with correct filter
        mock_audit_repo.query_audit_records.assert_called_once()
        call_kwargs = mock_audit_repo.query_audit_records.call_args.kwargs
        assert call_kwargs["job_id"] == "job-1"

        # Verify response
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is True
        assert data["filters"]["job_id"] == "job-1"

    @pytest.mark.asyncio
    async def test_get_audit_log_filter_by_repo_alias(self, admin_user, mock_audit_repo):
        """Test filtering audit log by repo_alias."""
        mock_audit_repo.query_audit_records.return_value = ([], 0)

        params = {"repo_alias": "my-repo"}
        response = await get_scip_audit_log(params, admin_user)

        # Verify filter was passed
        call_kwargs = mock_audit_repo.query_audit_records.call_args.kwargs
        assert call_kwargs["repo_alias"] == "my-repo"

        data = json.loads(response["content"][0]["text"])
        assert data["filters"]["repo_alias"] == "my-repo"

    @pytest.mark.asyncio
    async def test_get_audit_log_filter_by_project_language(self, admin_user, mock_audit_repo):
        """Test filtering audit log by project_language."""
        mock_audit_repo.query_audit_records.return_value = ([], 0)

        params = {"project_language": "python"}
        response = await get_scip_audit_log(params, admin_user)

        # Verify filter
        call_kwargs = mock_audit_repo.query_audit_records.call_args.kwargs
        assert call_kwargs["project_language"] == "python"

        data = json.loads(response["content"][0]["text"])
        assert data["filters"]["project_language"] == "python"

    @pytest.mark.asyncio
    async def test_get_audit_log_filter_by_build_system(self, admin_user, mock_audit_repo):
        """Test filtering audit log by project_build_system."""
        mock_audit_repo.query_audit_records.return_value = ([], 0)

        params = {"project_build_system": "pip"}
        response = await get_scip_audit_log(params, admin_user)

        # Verify filter
        call_kwargs = mock_audit_repo.query_audit_records.call_args.kwargs
        assert call_kwargs["project_build_system"] == "pip"

        data = json.loads(response["content"][0]["text"])
        assert data["filters"]["project_build_system"] == "pip"

    @pytest.mark.asyncio
    async def test_get_audit_log_pagination(self, admin_user, mock_audit_repo):
        """Test pagination parameters."""
        mock_audit_repo.query_audit_records.return_value = ([], 0)

        params = {"limit": 50, "offset": 10}
        response = await get_scip_audit_log(params, admin_user)

        # Verify pagination params
        call_kwargs = mock_audit_repo.query_audit_records.call_args.kwargs
        assert call_kwargs["limit"] == 50
        assert call_kwargs["offset"] == 10

    @pytest.mark.asyncio
    async def test_get_audit_log_default_pagination(self, admin_user, mock_audit_repo):
        """Test default pagination values."""
        mock_audit_repo.query_audit_records.return_value = ([], 0)

        params = {}
        response = await get_scip_audit_log(params, admin_user)

        # Verify defaults
        call_kwargs = mock_audit_repo.query_audit_records.call_args.kwargs
        assert call_kwargs["limit"] == 100  # Default limit
        assert call_kwargs["offset"] == 0   # Default offset

    @pytest.mark.asyncio
    async def test_get_audit_log_multiple_filters(self, admin_user, mock_audit_repo):
        """Test combining multiple filters."""
        mock_audit_repo.query_audit_records.return_value = ([], 0)

        params = {
            "job_id": "job-1",
            "repo_alias": "test-repo",
            "project_language": "python",
            "limit": 20
        }
        response = await get_scip_audit_log(params, admin_user)

        # Verify all filters passed
        call_kwargs = mock_audit_repo.query_audit_records.call_args.kwargs
        assert call_kwargs["job_id"] == "job-1"
        assert call_kwargs["repo_alias"] == "test-repo"
        assert call_kwargs["project_language"] == "python"
        assert call_kwargs["limit"] == 20

        # Verify filters echoed in response
        data = json.loads(response["content"][0]["text"])
        assert data["filters"]["job_id"] == "job-1"
        assert data["filters"]["repo_alias"] == "test-repo"
        assert data["filters"]["project_language"] == "python"

    @pytest.mark.asyncio
    async def test_get_audit_log_error_handling(self, admin_user, mock_audit_repo):
        """Test error handling when repository raises exception."""
        # Mock repository to raise exception
        mock_audit_repo.query_audit_records.side_effect = Exception("Database error")

        params = {}
        response = await get_scip_audit_log(params, admin_user)

        # Verify error response
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "error" in data
        assert "Database error" in data["error"]

    @pytest.mark.asyncio
    async def test_get_audit_log_invalid_limit(self, admin_user, mock_audit_repo):
        """Test handling of invalid limit parameter."""
        mock_audit_repo.query_audit_records.return_value = ([], 0)

        # Pass non-integer limit
        params = {"limit": "invalid"}
        response = await get_scip_audit_log(params, admin_user)

        # Should handle gracefully (use default or return error)
        data = json.loads(response["content"][0]["text"])
        # Either success with default limit or error response is acceptable
        assert "success" in data

    @pytest.mark.asyncio
    async def test_get_audit_log_response_structure(self, admin_user, mock_audit_repo):
        """Test complete response structure matches specification."""
        mock_records = [
            {
                "id": 1,
                "timestamp": "2025-12-31 10:00:00",
                "job_id": "job-1",
                "repo_alias": "test-repo",
                "project_path": "src/project",
                "project_language": "python",
                "project_build_system": "pip",
                "package": "numpy",
                "command": "pip install numpy",
                "reasoning": "Scientific computing",
                "username": "testuser"
            }
        ]
        mock_audit_repo.query_audit_records.return_value = (mock_records, 1)

        params = {"repo_alias": "test-repo"}
        response = await get_scip_audit_log(params, admin_user)

        data = json.loads(response["content"][0]["text"])

        # Verify structure
        assert data["success"] is True
        assert isinstance(data["records"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["filters"], dict)

        # Verify record structure
        record = data["records"][0]
        assert "id" in record
        assert "timestamp" in record
        assert "job_id" in record
        assert "repo_alias" in record
        assert "package" in record
        assert "command" in record
