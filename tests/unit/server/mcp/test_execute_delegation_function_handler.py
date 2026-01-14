"""
Unit tests for execute_delegation_function MCP tool handler.

Story #719: Execute Delegation Function with Async Job

Tests follow TDD methodology - tests written FIRST before implementation.
"""

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def temp_function_repo():
    """Create a temporary function repository with sample functions."""
    temp_dir = tempfile.mkdtemp()
    repo_path = Path(temp_dir)

    # Create sample function file with all required fields
    function1 = """---
name: semantic-search
description: "Search code semantically"
allowed_groups:
  - engineering
impersonation_user: service_account_search
required_repos:
  - alias: main-app
    remote: https://github.com/org/main-app
    branch: main
parameters:
  - name: query
    type: string
    required: true
---
Search for: {{query}}
{{user_prompt}}
"""
    (repo_path / "semantic-search.md").write_text(function1)

    # Admin-only function
    function2 = """---
name: admin-tool
description: "Admin only tool"
allowed_groups:
  - admins
impersonation_user: admin_service
required_repos: []
parameters: []
---
Admin template.
"""
    (repo_path / "admin-tool.md").write_text(function2)

    yield repo_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_user():
    """Create a test user."""
    return User(
        username="testuser",
        password_hash="hashed",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_delegation_config():
    """Create mock delegation config."""
    from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

    return ClaudeDelegationConfig(
        function_repo_alias="test-repo",
        claude_server_url="https://claude-server.example.com",
        claude_server_username="service_user",
        claude_server_credential="service_pass",
    )


class TestExecuteDelegationFunctionHandler:
    """Tests for execute_delegation_function handler."""

    @pytest.mark.asyncio
    async def test_handler_returns_job_id_on_success(
        self, test_user, temp_function_repo, mock_delegation_config, httpx_mock: HTTPXMock
    ):
        """Handler returns job_id on successful execution."""
        from code_indexer.server.mcp.handlers import handle_execute_delegation_function

        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://claude-server.example.com/repositories/main-app",
            json={"alias": "main-app"},
        )
        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/jobs",
            json={"job_id": "job-12345", "status": "created"},
            status_code=201,
        )
        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/jobs/job-12345/start",
            json={"job_id": "job-12345", "status": "running"},
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"engineering"},
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_execute_delegation_function(
                {"function_name": "semantic-search", "parameters": {"query": "bugs"}, "prompt": "Find"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is True
        assert data["job_id"] == "job-12345"

    @pytest.mark.asyncio
    async def test_handler_returns_error_for_unauthorized_user(
        self, test_user, temp_function_repo, mock_delegation_config
    ):
        """Handler returns error when user lacks access."""
        from code_indexer.server.mcp.handlers import handle_execute_delegation_function

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"random_group"},
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_execute_delegation_function(
                {"function_name": "admin-tool", "parameters": {}, "prompt": "Test"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "access" in data["error"].lower() or "denied" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_handler_returns_error_for_unknown_function(
        self, test_user, temp_function_repo, mock_delegation_config
    ):
        """Handler returns error for non-existent function."""
        from code_indexer.server.mcp.handlers import handle_execute_delegation_function

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"engineering"},
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_execute_delegation_function(
                {"function_name": "nonexistent", "parameters": {}, "prompt": "Test"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_handler_returns_error_when_not_configured(self, test_user):
        """Handler returns error when delegation not configured."""
        from code_indexer.server.mcp.handlers import handle_execute_delegation_function

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: None,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: None,
            )

            response = await handle_execute_delegation_function(
                {"function_name": "any", "parameters": {}, "prompt": "Test"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "not configured" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_handler_returns_error_for_missing_required_parameter(
        self, test_user, temp_function_repo, mock_delegation_config
    ):
        """Handler returns error when required parameter is missing."""
        from code_indexer.server.mcp.handlers import handle_execute_delegation_function

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"engineering"},
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_execute_delegation_function(
                {"function_name": "semantic-search", "parameters": {}, "prompt": "Test"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "required" in data["error"].lower() or "query" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_response_has_mcp_format(self, test_user):
        """Response follows MCP content array format."""
        from code_indexer.server.mcp.handlers import handle_execute_delegation_function

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: None,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: None,
            )

            response = await handle_execute_delegation_function(
                {"function_name": "test", "parameters": {}, "prompt": "test"},
                test_user,
            )

        assert "content" in response
        assert response["content"][0]["type"] == "text"
        json.loads(response["content"][0]["text"])  # Should be valid JSON

    @pytest.mark.asyncio
    async def test_handler_returns_error_when_job_id_missing(
        self, test_user, temp_function_repo, mock_delegation_config, httpx_mock: HTTPXMock
    ):
        """
        Handler returns error when create_job response has no job_id.

        Given job creation succeeds but returns empty job_id
        When execute_delegation_function is called
        Then it should return error instead of calling start_job
        """
        from code_indexer.server.mcp.handlers import handle_execute_delegation_function

        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://claude-server.example.com/repositories/main-app",
            json={"alias": "main-app"},
        )
        # Job creation returns no job_id
        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/jobs",
            json={"status": "created"},  # Missing job_id!
            status_code=201,
        )
        # NOTE: We do NOT add a start_job mock - it should NOT be called!

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"engineering"},
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_execute_delegation_function(
                {"function_name": "semantic-search", "parameters": {"query": "bugs"}, "prompt": "Find"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "job_id" in data["error"].lower() or "no job" in data["error"].lower()
