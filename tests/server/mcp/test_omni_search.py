"""
Tests for omni-search integration into MCP layer.

Tests polymorphic repository_alias parameter and routing to OmniSearchService.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from code_indexer.server.mcp.handlers import search_code, _mcp_response
from code_indexer.server.auth.user_manager import User, UserRole
from datetime import datetime


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
def mock_omni_service():
    """Mock OmniSearchService."""
    with patch("code_indexer.server.mcp.handlers.OmniSearchService") as mock:
        yield mock


@pytest.fixture
def mock_semantic_query_manager():
    """Mock semantic_query_manager for single-repo searches."""
    with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
        mock_app.semantic_query_manager.query_user_repositories.return_value = {
            "results": [],
            "total_results": 0,
            "query_metadata": {
                "query_text": "test",
                "execution_time_ms": 100,
                "repositories_searched": 1,
                "timeout_occurred": False,
            },
        }
        yield mock_app.semantic_query_manager


class TestOmniSearchDetection:
    """Test detection of omni-search vs single-repo search."""

    @pytest.mark.asyncio
    async def test_string_repository_alias_routes_to_single_repo(
        self, mock_user, mock_semantic_query_manager
    ):
        """Single-repo search when repository_alias is a string."""
        params = {
            "query_text": "authentication",
            "repository_alias": "backend",
            "limit": 5,
        }

        result = await search_code(params, mock_user)

        # Should call single-repo query manager
        assert mock_semantic_query_manager.query_user_repositories.called
        assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_array_repository_alias_routes_to_omni_search(
        self, mock_user, mock_omni_service
    ):
        """Omni-search when repository_alias is an array."""
        params = {
            "query_text": "authentication",
            "repository_alias": ["backend-global", "frontend-global"],
            "limit": 10,
        }

        # Mock OmniSearchService
        mock_service_instance = Mock()
        mock_service_instance.search.return_value = {
            "cursor": "abc123",
            "total_results": 5,
            "total_repos_searched": 2,
            "results": [],
            "errors": {},
        }
        mock_omni_service.return_value = mock_service_instance

        with patch("code_indexer.server.mcp.handlers._omni_search_code") as mock_omni:
            mock_omni.return_value = _mcp_response(
                {
                    "success": True,
                    "results": {
                        "cursor": "abc123",
                        "total_results": 5,
                        "total_repos_searched": 2,
                        "results": [],
                        "errors": {},
                    },
                }
            )

            result = await search_code(params, mock_user)

            # Should route to omni-search handler
            assert mock_omni.called
            call_args = mock_omni.call_args
            assert call_args[0][0] == params
            assert call_args[0][1] == mock_user

    @pytest.mark.asyncio
    async def test_no_repository_alias_routes_to_single_repo(
        self, mock_user, mock_semantic_query_manager
    ):
        """No repository_alias defaults to single-repo (all activated repos)."""
        params = {
            "query_text": "authentication",
            "limit": 5,
        }

        result = await search_code(params, mock_user)

        # Should call single-repo query manager (searches all activated repos)
        assert mock_semantic_query_manager.query_user_repositories.called


class TestOmniSearchParameters:
    """Test omni-search specific parameters."""

    @pytest.mark.asyncio
    async def test_aggregation_mode_parameter(self, mock_user):
        """Test aggregation_mode parameter is passed to service."""
        params = {
            "query_text": "authentication",
            "repository_alias": ["backend-global", "frontend-global"],
            "aggregation_mode": "per_repo",
            "limit": 10,
        }

        with patch("code_indexer.server.mcp.handlers._omni_search_code") as mock_omni:
            mock_omni.return_value = _mcp_response(
                {
                    "success": True,
                    "results": {
                        "cursor": "abc123",
                        "total_results": 5,
                        "total_repos_searched": 2,
                        "results": [],
                        "errors": {},
                    },
                }
            )

            await search_code(params, mock_user)

            # Check aggregation_mode was passed
            call_args = mock_omni.call_args
            assert call_args[0][0]["aggregation_mode"] == "per_repo"

    @pytest.mark.asyncio
    async def test_exclude_patterns_parameter(self, mock_user):
        """Test exclude_patterns parameter is passed to service."""
        params = {
            "query_text": "authentication",
            "repository_alias": ["*-global"],
            "exclude_patterns": [".*-test-.*", ".*-deprecated-.*"],
            "limit": 10,
        }

        with patch("code_indexer.server.mcp.handlers._omni_search_code") as mock_omni:
            mock_omni.return_value = _mcp_response(
                {
                    "success": True,
                    "results": {
                        "cursor": "abc123",
                        "total_results": 5,
                        "total_repos_searched": 2,
                        "results": [],
                        "errors": {},
                    },
                }
            )

            await search_code(params, mock_user)

            # Check exclude_patterns was passed
            call_args = mock_omni.call_args
            assert call_args[0][0]["exclude_patterns"] == [
                ".*-test-.*",
                ".*-deprecated-.*",
            ]


class TestOmniSearchResponseFormat:
    """Test omni-search response format."""

    @pytest.mark.asyncio
    async def test_omni_search_response_structure(self, mock_user):
        """Omni-search returns expected response structure."""
        params = {
            "query_text": "authentication",
            "repository_alias": ["backend-global", "frontend-global"],
            "limit": 10,
        }

        mock_results = [
            {
                "file_path": "src/auth.py",
                "line_number": 42,
                "code_snippet": "def authenticate_user():",
                "similarity_score": 0.95,
                "repository_alias": "backend-global",
            },
            {
                "file_path": "src/login.js",
                "line_number": 10,
                "code_snippet": "function login() {",
                "similarity_score": 0.87,
                "repository_alias": "frontend-global",
            },
        ]

        with patch("code_indexer.server.mcp.handlers._omni_search_code") as mock_omni:
            mock_omni.return_value = _mcp_response(
                {
                    "success": True,
                    "results": {
                        "cursor": "abc123",
                        "total_results": 2,
                        "total_repos_searched": 2,
                        "results": mock_results,
                        "errors": {},
                    },
                }
            )

            result = await search_code(params, mock_user)

            # Verify MCP response format
            assert "content" in result
            assert len(result["content"]) == 1
            assert result["content"][0]["type"] == "text"

            import json

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert "results" in response_data
            assert "cursor" in response_data["results"]
            assert "total_results" in response_data["results"]
            assert "total_repos_searched" in response_data["results"]
            assert "errors" in response_data["results"]
            assert len(response_data["results"]["results"]) == 2


class TestOmniSearchErrorHandling:
    """Test error handling in omni-search."""

    @pytest.mark.asyncio
    async def test_partial_repo_failures(self, mock_user):
        """Omni-search returns partial results when some repos fail."""
        params = {
            "query_text": "authentication",
            "repository_alias": ["backend-global", "broken-global"],
            "limit": 10,
        }

        with patch("code_indexer.server.mcp.handlers._omni_search_code") as mock_omni:
            mock_omni.return_value = _mcp_response(
                {
                    "success": True,
                    "results": {
                        "cursor": "abc123",
                        "total_results": 1,
                        "total_repos_searched": 1,
                        "results": [
                            {
                                "file_path": "src/auth.py",
                                "similarity_score": 0.95,
                                "repository_alias": "backend-global",
                            }
                        ],
                        "errors": {"broken-global": "Repository not found"},
                    },
                }
            )

            result = await search_code(params, mock_user)

            import json

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert len(response_data["results"]["results"]) == 1
            assert "broken-global" in response_data["results"]["errors"]

    @pytest.mark.asyncio
    async def test_all_repos_fail(self, mock_user):
        """Omni-search returns error when all repos fail."""
        params = {
            "query_text": "authentication",
            "repository_alias": ["broken1-global", "broken2-global"],
            "limit": 10,
        }

        with patch("code_indexer.server.mcp.handlers._omni_search_code") as mock_omni:
            mock_omni.return_value = _mcp_response(
                {
                    "success": True,
                    "results": {
                        "cursor": "abc123",
                        "total_results": 0,
                        "total_repos_searched": 0,
                        "results": [],
                        "errors": {
                            "broken1-global": "Repository not found",
                            "broken2-global": "Timeout",
                        },
                    },
                }
            )

            result = await search_code(params, mock_user)

            import json

            response_data = json.loads(result["content"][0]["text"])
            # Still returns success=True with empty results + errors
            assert response_data["success"] is True
            assert response_data["results"]["total_results"] == 0
            assert len(response_data["results"]["errors"]) == 2
