"""Tests for get_job_details MCP tool."""

import pytest
from code_indexer.server.mcp import handlers, tools


class TestGetJobDetailsTool:
    """Test get_job_details tool definition and handler."""

    def test_tool_registered(self):
        """Verify get_job_details is registered in TOOL_REGISTRY."""
        assert "get_job_details" in tools.TOOL_REGISTRY
        tool = tools.TOOL_REGISTRY["get_job_details"]
        assert tool["name"] == "get_job_details"
        assert "job_id" in tool["inputSchema"]["properties"]
        assert tool["required_permission"] == "query_repos"

    def test_handler_registered(self):
        """Verify get_job_details handler is registered."""
        assert "get_job_details" in handlers.HANDLER_REGISTRY
        assert handlers.HANDLER_REGISTRY["get_job_details"] == handlers.get_job_details

    def test_tool_schema_complete(self):
        """Verify tool definition has complete schema."""
        tool = tools.TOOL_REGISTRY["get_job_details"]

        # Check input schema
        assert tool["inputSchema"]["required"] == ["job_id"]
        assert tool["inputSchema"]["properties"]["job_id"]["type"] == "string"

        # Check output schema includes error field
        output_props = tool["outputSchema"]["properties"]
        assert "success" in output_props
        assert "job" in output_props
        assert "error" in output_props

        # Verify job object includes error message field
        job_props = output_props["job"]["properties"]
        assert "error" in job_props
        assert job_props["error"]["type"] == ["string", "null"]
        assert "error message" in job_props["error"]["description"].lower()

    @pytest.mark.asyncio
    async def test_handler_missing_job_id(self):
        """Test handler returns error when job_id is missing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        user = User(username="testuser", password_hash="dummy_hash", role=UserRole.ADMIN, created_at="2025-01-01T00:00:00Z")
        result = await handlers.get_job_details({}, user)

        assert "content" in result
        assert result["content"][0]["type"] == "text"

        import json
        response = json.loads(result["content"][0]["text"])
        assert response["success"] is False
        assert "job_id" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_handler_job_not_found(self, monkeypatch):
        """Test handler returns error when job doesn't exist."""
        from code_indexer.server.auth.user_manager import User, UserRole
        import code_indexer.server.app as app_module

        # Mock background_job_manager.get_job to return None
        class MockJobManager:
            def get_job(self, job_id):
                return None

        monkeypatch.setattr(app_module, "background_job_manager", MockJobManager())

        user = User(username="testuser", password_hash="dummy_hash", role=UserRole.ADMIN, created_at="2025-01-01T00:00:00Z")
        result = await handlers.get_job_details({"job_id": "nonexistent"}, user)

        assert "content" in result
        import json
        response = json.loads(result["content"][0]["text"])
        assert response["success"] is False
        assert "not found" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_handler_returns_job_with_error(self, monkeypatch):
        """Test handler returns job details including error message."""
        from code_indexer.server.auth.user_manager import User, UserRole
        import code_indexer.server.app as app_module

        # Mock background_job_manager.get_job to return job with error
        class MockJobManager:
            def get_job(self, job_id):
                return {
                    "job_id": job_id,
                    "operation_type": "add_golden_repo",
                    "status": "failed",
                    "created_at": "2025-01-01T00:00:00Z",
                    "started_at": "2025-01-01T00:00:01Z",
                    "completed_at": "2025-01-01T00:00:02Z",
                    "progress": 0,
                    "result": None,
                    "error": "Git clone failed with code 128: fatal: Remote branch main not found in upstream origin",
                    "username": "testuser",
                }

        monkeypatch.setattr(app_module, "background_job_manager", MockJobManager())

        user = User(username="testuser", password_hash="dummy_hash", role=UserRole.ADMIN, created_at="2025-01-01T00:00:00Z")
        result = await handlers.get_job_details({"job_id": "test-job-123"}, user)

        assert "content" in result
        import json
        response = json.loads(result["content"][0]["text"])
        assert response["success"] is True
        assert "job" in response

        job = response["job"]
        assert job["job_id"] == "test-job-123"
        assert job["status"] == "failed"
        assert "Git clone failed" in job["error"]
        assert "Remote branch main not found" in job["error"]
