"""
Tests for omni-regex search integration into MCP layer.

Tests polymorphic repository_alias parameter and routing to omni-regex search.
"""

import pytest
from unittest.mock import Mock, patch
from code_indexer.server.mcp.handlers import handle_regex_search, _mcp_response
from code_indexer.server.auth.user_manager import User, UserRole
from datetime import datetime
import json


@pytest.fixture
def mock_user():
    """Create mock user for testing."""
    return User(
        username="testuser",
        password_hash="hash",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(),
    )


@pytest.fixture
def mock_regex_search_service():
    """Mock RegexSearchService for single-repo searches."""
    with patch("code_indexer.global_repos.regex_search.RegexSearchService") as mock:
        # Mock search result
        mock_result = Mock()
        mock_result.matches = []
        mock_result.total_matches = 0
        mock_result.truncated = False
        mock_result.search_engine = "ripgrep"
        mock_result.search_time_ms = 50

        mock_service_instance = Mock()
        mock_service_instance.search.return_value = mock_result
        mock.return_value = mock_service_instance

        yield mock


@pytest.fixture
def mock_resolve_repo_path():
    """Mock _resolve_repo_path for single-repo searches."""
    with patch("code_indexer.server.mcp.handlers._resolve_repo_path") as mock:
        mock.return_value = "/fake/repo/path"
        yield mock


@pytest.fixture
def mock_golden_repos_dir():
    """Mock _get_golden_repos_dir."""
    with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock:
        mock.return_value = "/fake/golden/repos"
        yield mock


class TestOmniRegexSearchDetection:
    """Test detection of omni-regex vs single-repo regex search."""

    @pytest.mark.asyncio
    async def test_string_repository_alias_routes_to_single_repo(
        self, mock_user, mock_regex_search_service, mock_resolve_repo_path, mock_golden_repos_dir
    ):
        """Single-repo regex search when repository_alias is a string."""
        params = {
            "repository_alias": "backend",
            "pattern": "def test_.*",
        }

        result = await handle_regex_search(params, mock_user)

        # Should call single-repo regex search service
        assert mock_regex_search_service.called
        assert result["content"][0]["type"] == "text"

        # Verify response structure
        response_data = json.loads(result["content"][0]["text"])
        assert "success" in response_data
        assert "matches" in response_data

    @pytest.mark.asyncio
    async def test_array_repository_alias_routes_to_omni_search(
        self, mock_user, mock_golden_repos_dir
    ):
        """Omni-regex search when repository_alias is an array."""
        params = {
            "repository_alias": ["backend-global", "frontend-global"],
            "pattern": "TODO|FIXME",
            "aggregation_mode": "global",
        }

        with patch("code_indexer.server.mcp.handlers._omni_regex_search") as mock_omni:
            mock_omni.return_value = _mcp_response(
                {
                    "success": True,
                    "matches": [],
                    "total_matches": 0,
                    "truncated": False,
                    "search_engine": "ripgrep",
                    "search_time_ms": 0,
                    "repos_searched": 2,
                    "errors": {},
                }
            )

            result = await handle_regex_search(params, mock_user)

            # Should call omni-regex search
            assert mock_omni.called
            call_args = mock_omni.call_args
            assert call_args[0][0] == params  # First positional arg is params
            assert call_args[0][1] == mock_user  # Second positional arg is user

    @pytest.mark.asyncio
    async def test_aggregation_mode_parameter_passed(
        self, mock_user, mock_golden_repos_dir
    ):
        """Verify aggregation_mode parameter is passed to omni-regex search."""
        params = {
            "repository_alias": ["repo1", "repo2"],
            "pattern": "class.*Controller",
            "aggregation_mode": "per_repo",
        }

        with patch("code_indexer.server.mcp.handlers._omni_regex_search") as mock_omni:
            mock_omni.return_value = _mcp_response(
                {
                    "success": True,
                    "matches": [],
                    "total_matches": 0,
                    "truncated": False,
                    "search_engine": "ripgrep",
                    "search_time_ms": 0,
                    "repos_searched": 2,
                    "errors": {},
                }
            )

            await handle_regex_search(params, mock_user)

            # Verify aggregation_mode is in params passed to omni-regex search
            call_args = mock_omni.call_args
            passed_params = call_args[0][0]
            assert passed_params["aggregation_mode"] == "per_repo"

    @pytest.mark.asyncio
    async def test_missing_repository_alias_error(self, mock_user):
        """Error when repository_alias is missing."""
        params = {
            "pattern": "def test_.*",
        }

        result = await handle_regex_search(params, mock_user)

        # Should return error
        response_data = json.loads(result["content"][0]["text"])
        assert "success" in response_data
        assert response_data["success"] is False
        assert "error" in response_data
        assert "repository_alias" in response_data["error"]

    @pytest.mark.asyncio
    async def test_missing_pattern_error(self, mock_user):
        """Error when pattern is missing."""
        params = {
            "repository_alias": "backend",
        }

        result = await handle_regex_search(params, mock_user)

        # Should return error
        response_data = json.loads(result["content"][0]["text"])
        assert "success" in response_data
        assert response_data["success"] is False
        assert "error" in response_data
        assert "pattern" in response_data["error"]
