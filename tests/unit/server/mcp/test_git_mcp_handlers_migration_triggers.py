"""
Unit tests for Bug #639: MCP handlers bypass Story #636 migration triggers.

Tests verify that MCP git_push, git_pull, and git_fetch handlers call
the wrapper methods (push_to_remote, pull_from_remote, fetch_from_remote)
that contain migration triggers, instead of calling low-level git methods
directly.

CRITICAL: These tests use REAL GitOperationsService with MOCKED _trigger_migration_if_needed
to verify the migration trigger is called without actually running migration logic.
This follows Anti-Mock Rule #1: Real systems only, minimal mocking.
"""

import json
from datetime import datetime
from typing import cast
from unittest.mock import MagicMock, patch
import pytest

from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.services.git_operations_service import GitOperationsService
from code_indexer.server.mcp import handlers


@pytest.fixture
def mock_user():
    """Create mock user for testing."""
    return User(
        username="testuser",
        role=UserRole.NORMAL_USER,
        password_hash="dummy_hash",
        created_at=datetime.now(),
    )


@pytest.fixture
def real_git_service_with_mocked_migration():
    """
    Create REAL GitOperationsService with migration trigger mocked.

    This follows Anti-Mock Rule #1: Use real implementation, mock only the
    specific behavior we're testing (migration trigger).
    """
    # Create real GitOperationsService instance
    service = GitOperationsService()

    # Mock only the migration trigger method
    service._trigger_migration_if_needed = MagicMock()

    # Mock the low-level git methods to avoid actual git operations
    service.git_push = MagicMock(
        return_value={
            "success": True,
            "pushed_commits": 2,
            "remote": "origin",
            "branch": "main",
        }
    )
    service.git_pull = MagicMock(
        return_value={
            "success": True,
            "fetched_commits": 1,
            "remote": "origin",
            "branch": "main",
        }
    )
    service.git_fetch = MagicMock(
        return_value={
            "success": True,
            "refs_updated": 3,
            "remote": "origin",
        }
    )

    # Mock activated_repo_manager to return test path
    service.activated_repo_manager.get_activated_repo_path = MagicMock(
        return_value="/tmp/test-repo"
    )

    return service


@pytest.fixture
def mock_repo_manager():
    """Create mock ActivatedRepoManager."""
    with patch("code_indexer.server.mcp.handlers.ActivatedRepoManager") as MockClass:
        mock_instance = MockClass.return_value
        mock_instance.get_activated_repo_path.return_value = "/tmp/test-repo"
        yield mock_instance


def _extract_response_data(mcp_response: dict) -> dict:
    """Extract actual response data from MCP wrapper."""
    content = mcp_response["content"][0]
    return cast(dict, json.loads(content["text"]))


class TestGitPushMigrationTrigger:
    """Test that git_push handler triggers migration (Bug #639)."""

    @pytest.mark.asyncio
    async def test_git_push_calls_wrapper_method(
        self, mock_user, real_git_service_with_mocked_migration, mock_repo_manager
    ):
        """
        Test that git_push MCP handler calls push_to_remote wrapper (which triggers migration).

        EXPECTED BEHAVIOR (after fix):
        - MCP handler calls push_to_remote() wrapper
        - Wrapper calls _trigger_migration_if_needed()
        - Wrapper calls git_push() low-level method

        CURRENT BEHAVIOR (before fix):
        - MCP handler calls git_push() directly
        - Migration trigger is NEVER called
        - This test will FAIL initially
        """
        # Patch git_operations_service in handlers module with our real service
        with patch(
            "code_indexer.server.mcp.handlers.git_operations_service",
            real_git_service_with_mocked_migration,
        ):
            params = {
                "repository_alias": "test-repo",
                "remote": "origin",
                "branch": "main",
            }

            mcp_response = await handlers.git_push(params, mock_user)
            data = _extract_response_data(mcp_response)

            # Verify response is successful
            assert data["success"] is True

            # CRITICAL ASSERTION: Migration trigger must be called
            # This will FAIL before fix because handlers call git_push() directly
            real_git_service_with_mocked_migration._trigger_migration_if_needed.assert_called_once()

            # Verify it was called with correct parameters
            call_args = (
                real_git_service_with_mocked_migration._trigger_migration_if_needed.call_args
            )
            assert call_args[0][0] == "/tmp/test-repo"  # repo_path
            assert call_args[0][1] == "testuser"  # username
            assert call_args[0][2] == "test-repo"  # repo_alias

    @pytest.mark.asyncio
    async def test_git_push_migration_trigger_called_before_push(
        self, mock_user, real_git_service_with_mocked_migration, mock_repo_manager
    ):
        """
        Test that migration trigger is called BEFORE git_push operation.

        This ensures migration happens before attempting remote operation.
        """
        call_order = []

        # Track call order
        real_git_service_with_mocked_migration._trigger_migration_if_needed.side_effect = lambda *args, **kwargs: call_order.append(
            "migration"
        )
        original_git_push = real_git_service_with_mocked_migration.git_push
        real_git_service_with_mocked_migration.git_push = MagicMock(
            side_effect=lambda *args, **kwargs: (
                call_order.append("git_push"),
                original_git_push(*args, **kwargs),
            )[1]
        )

        with patch(
            "code_indexer.server.mcp.handlers.git_operations_service",
            real_git_service_with_mocked_migration,
        ):
            params = {
                "repository_alias": "test-repo",
                "remote": "origin",
                "branch": "main",
            }

            await handlers.git_push(params, mock_user)

            # Verify migration was called before git_push
            assert call_order == ["migration", "git_push"]


class TestGitPullMigrationTrigger:
    """Test that git_pull handler triggers migration (Bug #639)."""

    @pytest.mark.asyncio
    async def test_git_pull_calls_wrapper_method(
        self, mock_user, real_git_service_with_mocked_migration, mock_repo_manager
    ):
        """
        Test that git_pull MCP handler calls pull_from_remote wrapper (which triggers migration).
        """
        with patch(
            "code_indexer.server.mcp.handlers.git_operations_service",
            real_git_service_with_mocked_migration,
        ):
            params = {
                "repository_alias": "test-repo",
                "remote": "origin",
                "branch": "main",
            }

            mcp_response = await handlers.git_pull(params, mock_user)
            data = _extract_response_data(mcp_response)

            # Verify response is successful
            assert data["success"] is True

            # CRITICAL ASSERTION: Migration trigger must be called
            real_git_service_with_mocked_migration._trigger_migration_if_needed.assert_called_once()

            # Verify it was called with correct parameters
            call_args = (
                real_git_service_with_mocked_migration._trigger_migration_if_needed.call_args
            )
            assert call_args[0][0] == "/tmp/test-repo"  # repo_path
            assert call_args[0][1] == "testuser"  # username
            assert call_args[0][2] == "test-repo"  # repo_alias

    @pytest.mark.asyncio
    async def test_git_pull_migration_trigger_called_before_pull(
        self, mock_user, real_git_service_with_mocked_migration, mock_repo_manager
    ):
        """
        Test that migration trigger is called BEFORE git_pull operation.
        """
        call_order = []

        # Track call order
        real_git_service_with_mocked_migration._trigger_migration_if_needed.side_effect = lambda *args, **kwargs: call_order.append(
            "migration"
        )
        original_git_pull = real_git_service_with_mocked_migration.git_pull
        real_git_service_with_mocked_migration.git_pull = MagicMock(
            side_effect=lambda *args, **kwargs: (
                call_order.append("git_pull"),
                original_git_pull(*args, **kwargs),
            )[1]
        )

        with patch(
            "code_indexer.server.mcp.handlers.git_operations_service",
            real_git_service_with_mocked_migration,
        ):
            params = {
                "repository_alias": "test-repo",
                "remote": "origin",
                "branch": "main",
            }

            await handlers.git_pull(params, mock_user)

            # Verify migration was called before git_pull
            assert call_order == ["migration", "git_pull"]


class TestGitFetchMigrationTrigger:
    """Test that git_fetch handler triggers migration (Bug #639)."""

    @pytest.mark.asyncio
    async def test_git_fetch_calls_wrapper_method(
        self, mock_user, real_git_service_with_mocked_migration, mock_repo_manager
    ):
        """
        Test that git_fetch MCP handler calls fetch_from_remote wrapper (which triggers migration).
        """
        with patch(
            "code_indexer.server.mcp.handlers.git_operations_service",
            real_git_service_with_mocked_migration,
        ):
            params = {
                "repository_alias": "test-repo",
                "remote": "origin",
            }

            mcp_response = await handlers.git_fetch(params, mock_user)
            data = _extract_response_data(mcp_response)

            # Verify response is successful
            assert data["success"] is True

            # CRITICAL ASSERTION: Migration trigger must be called
            real_git_service_with_mocked_migration._trigger_migration_if_needed.assert_called_once()

            # Verify it was called with correct parameters
            call_args = (
                real_git_service_with_mocked_migration._trigger_migration_if_needed.call_args
            )
            assert call_args[0][0] == "/tmp/test-repo"  # repo_path
            assert call_args[0][1] == "testuser"  # username
            assert call_args[0][2] == "test-repo"  # repo_alias

    @pytest.mark.asyncio
    async def test_git_fetch_migration_trigger_called_before_fetch(
        self, mock_user, real_git_service_with_mocked_migration, mock_repo_manager
    ):
        """
        Test that migration trigger is called BEFORE git_fetch operation.
        """
        call_order = []

        # Track call order
        real_git_service_with_mocked_migration._trigger_migration_if_needed.side_effect = lambda *args, **kwargs: call_order.append(
            "migration"
        )
        original_git_fetch = real_git_service_with_mocked_migration.git_fetch
        real_git_service_with_mocked_migration.git_fetch = MagicMock(
            side_effect=lambda *args, **kwargs: (
                call_order.append("git_fetch"),
                original_git_fetch(*args, **kwargs),
            )[1]
        )

        with patch(
            "code_indexer.server.mcp.handlers.git_operations_service",
            real_git_service_with_mocked_migration,
        ):
            params = {
                "repository_alias": "test-repo",
                "remote": "origin",
            }

            await handlers.git_fetch(params, mock_user)

            # Verify migration was called before git_fetch
            assert call_order == ["migration", "git_fetch"]
