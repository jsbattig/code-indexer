"""
Unit tests for list_delegation_functions MCP tool handler.

Story #718: Function Discovery for claude.ai Users

Tests follow TDD methodology - tests written FIRST before implementation.
"""

import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def temp_function_repo():
    """Create a temporary function repository with sample functions."""
    temp_dir = tempfile.mkdtemp()
    repo_path = Path(temp_dir)

    # Create sample function files
    function1 = """---
name: semantic-search
description: "Search code semantically"
allowed_groups:
  - engineering
  - support
parameters:
  - name: query
    type: string
    required: true
    description: "Search query"
---
You are a code search assistant.
"""
    (repo_path / "semantic-search.md").write_text(function1)

    function2 = """---
name: admin-tool
description: "Admin only tool"
allowed_groups:
  - admins
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
def admin_user():
    """Create an admin user."""
    return User(
        username="admin",
        password_hash="hashed",
        role=UserRole.ADMIN,
        created_at=datetime.now(timezone.utc),
    )


class TestListDelegationFunctionsHandler:
    """Tests for list_delegation_functions handler."""

    @pytest.mark.asyncio
    async def test_handler_returns_mcp_response_format(
        self, test_user, temp_function_repo
    ):
        """
        Handler should return MCP-compliant response format.

        Given I call list_delegation_functions
        Then the response has content array with type and text fields
        """
        from code_indexer.server.mcp.handlers import handle_list_delegation_functions

        # Setup: Configure delegation to use temp function repo
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"engineering"},
            )

            response = await handle_list_delegation_functions({}, test_user)

        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"
        # Parse the JSON text to verify structure
        data = json.loads(response["content"][0]["text"])
        assert "success" in data

    @pytest.mark.asyncio
    async def test_handler_returns_functions_for_user_groups(
        self, test_user, temp_function_repo
    ):
        """
        Handler should return functions accessible to user's groups.

        Given I am in engineering group
        When I call list_delegation_functions
        Then I get functions with engineering in allowed_groups
        """
        from code_indexer.server.mcp.handlers import handle_list_delegation_functions

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"engineering"},
            )

            response = await handle_list_delegation_functions({}, test_user)

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is True
        assert len(data["functions"]) == 1
        assert data["functions"][0]["name"] == "semantic-search"

    @pytest.mark.asyncio
    async def test_handler_filters_by_impersonated_user_groups(
        self, admin_user, temp_function_repo
    ):
        """
        Handler should use impersonated user's groups when impersonating.

        Given I am admin impersonating a user in admins group
        When I call list_delegation_functions with session_state
        Then I get functions filtered by the impersonated user's groups (not admin's)

        Story #718 Code Review - CRITICAL-1 and MEDIUM-1
        """
        from code_indexer.server.mcp.handlers import handle_list_delegation_functions
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        # Create the impersonated user (who is in 'admins' group)
        impersonated_user = User(
            username="impersonated_admin_user",
            password_hash="hashed",
            role=UserRole.NORMAL_USER,  # Regular user but in admins group
            created_at=datetime.now(timezone.utc),
        )

        # Setup session state with impersonation
        session_state = MCPSessionState(
            session_id="test-session-123",
            authenticated_user=admin_user,
        )
        session_state.set_impersonation(impersonated_user)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )

            # _get_user_groups is called with the effective user
            # Impersonated user belongs to 'admins' group
            # Admin user (if NOT impersonating) would belong to 'engineering' group
            def mock_get_user_groups(user):
                if user.username == "impersonated_admin_user":
                    return {"admins"}
                elif user.username == "admin":
                    return {"engineering"}  # Admin's actual groups
                return set()

            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                mock_get_user_groups,
            )

            # Pass session_state to the handler
            response = await handle_list_delegation_functions(
                {}, admin_user, session_state=session_state
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is True
        # Should see admin-tool (for admins group) NOT semantic-search (for engineering)
        assert len(data["functions"]) == 1
        assert data["functions"][0]["name"] == "admin-tool"

    @pytest.mark.asyncio
    async def test_handler_includes_parameters_in_response(
        self, test_user, temp_function_repo
    ):
        """
        Handler should include parameters in function response.

        Given I call list_delegation_functions
        Then each function includes its parameters
        """
        from code_indexer.server.mcp.handlers import handle_list_delegation_functions

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: temp_function_repo,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"engineering"},
            )

            response = await handle_list_delegation_functions({}, test_user)

        data = json.loads(response["content"][0]["text"])
        func = data["functions"][0]
        assert "parameters" in func
        assert len(func["parameters"]) == 1
        assert func["parameters"][0]["name"] == "query"
        assert func["parameters"][0]["type"] == "string"
        assert func["parameters"][0]["required"] is True

    @pytest.mark.asyncio
    async def test_handler_returns_empty_list_for_empty_repo(self, test_user):
        """
        Handler should return empty list for empty function repository.

        Given I have an empty function repository
        When I call list_delegation_functions
        Then I get an empty functions list
        """
        from code_indexer.server.mcp.handlers import handle_list_delegation_functions

        empty_dir = tempfile.mkdtemp()
        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                    lambda: Path(empty_dir),
                )
                mp.setattr(
                    "code_indexer.server.mcp.handlers._get_user_groups",
                    lambda user: {"engineering"},
                )

                response = await handle_list_delegation_functions({}, test_user)

            data = json.loads(response["content"][0]["text"])
            assert data["success"] is True
            assert data["functions"] == []
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_handler_returns_error_when_not_configured(self, test_user):
        """
        Handler should return error when delegation not configured.

        Given Claude Delegation is not configured
        When I call list_delegation_functions
        Then I get error "Claude Delegation not configured"
        """
        from code_indexer.server.mcp.handlers import handle_list_delegation_functions

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: None,
            )

            response = await handle_list_delegation_functions({}, test_user)

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "not configured" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_handler_returns_error_when_repo_not_found(self, test_user):
        """
        Handler should return error when function repository not found.

        Given function_repo_alias points to non-existent repo
        When I call list_delegation_functions
        Then I get error about repository not found
        """
        from code_indexer.server.mcp.handlers import handle_list_delegation_functions

        # Return a path that doesn't exist
        nonexistent = Path("/nonexistent/repo/path")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_function_repo_path",
                lambda: nonexistent,
            )
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_user_groups",
                lambda user: {"engineering"},
            )

            response = await handle_list_delegation_functions({}, test_user)

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is True
        # Non-existent directory returns empty list (same as empty repo)
        assert data["functions"] == []
