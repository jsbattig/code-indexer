"""Unit tests for temporal query parameters in MCP API (Story #446).

Tests temporal parameter support in MCP search_code tool:
- Time-range filtering
- Point-in-time queries
- Include removed code
- Evolution display
- Graceful fallback when temporal index missing
- Error handling for invalid parameters
"""

import json
import pytest
from unittest.mock import Mock, patch
from code_indexer.server.mcp.handlers import search_code
from code_indexer.server.mcp.tools import TOOL_REGISTRY
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.role = UserRole.NORMAL_USER
    user.has_permission = Mock(return_value=True)
    return user


class TestMCPToolSchemaTemporalParameters:
    """Test that MCP search_code tool schema includes temporal parameters."""

    def test_search_code_tool_has_time_range_parameter(self):
        """Acceptance Criterion 1: POST /api/query accepts time_range parameter."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        properties = schema["properties"]

        assert (
            "time_range" in properties
        ), "time_range parameter missing from search_code tool schema"

        time_range_spec = properties["time_range"]
        assert time_range_spec["type"] == "string"
        assert "Time range filter" in time_range_spec["description"]
        assert "2024-01-01..2024-12-31" in time_range_spec["description"]

    def test_search_code_tool_has_at_commit_parameter(self):
        """Acceptance Criterion 1: POST /api/query accepts at_commit parameter."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        properties = schema["properties"]

        assert (
            "at_commit" in properties
        ), "at_commit parameter missing from search_code tool schema"

        at_commit_spec = properties["at_commit"]
        assert at_commit_spec["type"] == "string"
        assert "specific commit" in at_commit_spec["description"].lower()

    def test_search_code_tool_has_include_removed_parameter(self):
        """Acceptance Criterion 1: POST /api/query accepts include_removed parameter."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        properties = schema["properties"]

        assert (
            "include_removed" in properties
        ), "include_removed parameter missing from search_code tool schema"

        include_removed_spec = properties["include_removed"]
        assert include_removed_spec["type"] == "boolean"
        assert include_removed_spec["default"] is False

    def test_search_code_tool_has_show_evolution_parameter(self):
        """Acceptance Criterion 1: POST /api/query accepts show_evolution parameter."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        properties = schema["properties"]

        assert (
            "show_evolution" in properties
        ), "show_evolution parameter missing from search_code tool schema"

        show_evolution_spec = properties["show_evolution"]
        assert show_evolution_spec["type"] == "boolean"
        assert show_evolution_spec["default"] is False

    def test_search_code_tool_has_evolution_limit_parameter(self):
        """Acceptance Criterion 1: POST /api/query accepts evolution_limit parameter."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        properties = schema["properties"]

        assert (
            "evolution_limit" in properties
        ), "evolution_limit parameter missing from search_code tool schema"

        evolution_limit_spec = properties["evolution_limit"]
        assert evolution_limit_spec["type"] == "integer"
        assert evolution_limit_spec["minimum"] >= 1
        # User-controlled, NO arbitrary max per story requirement
        assert (
            "maximum" not in evolution_limit_spec
            or evolution_limit_spec["maximum"] >= 100
        )


@pytest.mark.asyncio
class TestTemporalQueryHandlerIntegration:
    """Test that MCP handler passes temporal parameters to semantic query manager."""

    async def test_handler_passes_time_range_to_query_manager(self, mock_user):
        """Acceptance Criterion 2: Time-range filtering passes through to query manager."""
        params = {
            "query_text": "authentication",
            "time_range": "2023-01-01..2024-01-01",
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                return_value={
                    "results": [],
                    "total_results": 0,
                    "query_metadata": {
                        "query_text": "authentication",
                        "execution_time_ms": 50,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }
            )

            result = await search_code(params, mock_user)

            # Verify handler called query_manager with temporal parameters
            call_kwargs = mock_qm.query_user_repositories.call_args[1]
            assert "time_range" in call_kwargs
            assert call_kwargs["time_range"] == "2023-01-01..2024-01-01"

    async def test_handler_passes_at_commit_to_query_manager(self, mock_user):
        """Acceptance Criterion 3: Point-in-time query passes through to query manager."""
        params = {
            "query_text": "login handler",
            "at_commit": "abc123",
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                return_value={
                    "results": [],
                    "total_results": 0,
                    "query_metadata": {
                        "query_text": "login handler",
                        "execution_time_ms": 50,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }
            )

            result = await search_code(params, mock_user)

            call_kwargs = mock_qm.query_user_repositories.call_args[1]
            assert "at_commit" in call_kwargs
            assert call_kwargs["at_commit"] == "abc123"

    async def test_handler_passes_include_removed_to_query_manager(self, mock_user):
        """Acceptance Criterion 4: Include removed code flag passes through."""
        params = {
            "query_text": "deprecated function",
            "include_removed": True,
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                return_value={
                    "results": [],
                    "total_results": 0,
                    "query_metadata": {
                        "query_text": "deprecated function",
                        "execution_time_ms": 50,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }
            )

            result = await search_code(params, mock_user)

            call_kwargs = mock_qm.query_user_repositories.call_args[1]
            assert "include_removed" in call_kwargs
            assert call_kwargs["include_removed"] is True

    async def test_handler_passes_show_evolution_to_query_manager(self, mock_user):
        """Acceptance Criterion 5: Evolution display flag passes through."""
        params = {
            "query_text": "user authentication",
            "show_evolution": True,
            "limit": 5,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                return_value={
                    "results": [],
                    "total_results": 0,
                    "query_metadata": {
                        "query_text": "user authentication",
                        "execution_time_ms": 50,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }
            )

            result = await search_code(params, mock_user)

            call_kwargs = mock_qm.query_user_repositories.call_args[1]
            assert "show_evolution" in call_kwargs
            assert call_kwargs["show_evolution"] is True

    async def test_handler_passes_evolution_limit_to_query_manager(self, mock_user):
        """Acceptance Criterion 6: Evolution limit passes through (user-controlled)."""
        params = {
            "query_text": "database query",
            "show_evolution": True,
            "evolution_limit": 5,
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                return_value={
                    "results": [],
                    "total_results": 0,
                    "query_metadata": {
                        "query_text": "database query",
                        "execution_time_ms": 50,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }
            )

            result = await search_code(params, mock_user)

            call_kwargs = mock_qm.query_user_repositories.call_args[1]
            assert "evolution_limit" in call_kwargs
            assert call_kwargs["evolution_limit"] == 5


@pytest.mark.asyncio
class TestTemporalResponseFormat:
    """Test that temporal query responses include required metadata."""

    async def test_response_includes_temporal_metadata(self, mock_user):
        """Acceptance Criterion 7: Response includes temporal metadata."""
        params = {
            "query_text": "authentication",
            "time_range": "2023-01-01..2024-01-01",
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                return_value={
                    "results": [
                        {
                            "file_path": "auth.py",
                            "score": 0.9,
                            "content": "def authenticate():\n    pass",
                            "temporal_context": {
                                "first_seen": "2023-06-15",
                                "last_seen": "2023-12-20",
                                "commit_count": 5,
                                "commits": [
                                    {
                                        "hash": "abc123",
                                        "date": "2023-06-15",
                                        "author": "dev@example.com",
                                        "message": "Add authentication",
                                    }
                                ],
                            },
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

            # Parse MCP response
            data = json.loads(result["content"][0]["text"])
            assert data["success"] is True

            # Verify temporal context in results
            assert len(data["results"]["results"]) == 1
            result_item = data["results"]["results"][0]
            assert "temporal_context" in result_item

            temporal = result_item["temporal_context"]
            assert "first_seen" in temporal
            assert "last_seen" in temporal
            assert "commit_count" in temporal
            assert "commits" in temporal


@pytest.mark.asyncio
class TestGracefulFallback:
    """Test graceful fallback when temporal index missing."""

    async def test_fallback_returns_current_code_with_warning(self, mock_user):
        """Acceptance Criterion 9: Graceful fallback when temporal index missing."""
        params = {
            "query_text": "authentication",
            "time_range": "2023-01-01..2024-01-01",
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            # Simulate fallback: returns current code with warning
            mock_qm.query_user_repositories = Mock(
                return_value={
                    "results": [
                        {
                            "file_path": "auth.py",
                            "score": 0.9,
                            "content": "def authenticate():\n    pass",
                        }
                    ],
                    "total_results": 1,
                    "query_metadata": {
                        "query_text": "authentication",
                        "execution_time_ms": 100,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                    "warning": "Temporal index not available. Showing results from current code only.",
                }
            )

            result = await search_code(params, mock_user)

            # Parse MCP response
            data = json.loads(result["content"][0]["text"])
            assert data["success"] is True

            # Verify warning present
            assert "warning" in data["results"]
            assert "Temporal index not available" in data["results"]["warning"]


@pytest.mark.asyncio
class TestTemporalErrorHandling:
    """Test error handling for invalid temporal parameters."""

    async def test_error_on_invalid_date_format(self, mock_user):
        """Acceptance Criterion 10: Clear error for invalid date formats."""
        params = {
            "query_text": "authentication",
            "time_range": "2023-1-1..2024-1-1",  # Invalid: not zero-padded
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                side_effect=ValueError(
                    "Invalid date format. Use YYYY-MM-DD with zero-padded month/day (e.g., 2023-01-01)"
                )
            )

            result = await search_code(params, mock_user)

            # Parse MCP response
            data = json.loads(result["content"][0]["text"])
            assert data["success"] is False
            assert "Invalid date format" in data["error"]
            assert "YYYY-MM-DD" in data["error"]

    async def test_error_on_invalid_date_separator(self, mock_user):
        """Acceptance Criterion 10: Clear error for wrong separator."""
        params = {
            "query_text": "authentication",
            "time_range": "2023-01-01-2024-01-01",  # Invalid: wrong separator
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                side_effect=ValueError(
                    "Time range must use '..' separator (format: YYYY-MM-DD..YYYY-MM-DD)"
                )
            )

            result = await search_code(params, mock_user)

            data = json.loads(result["content"][0]["text"])
            assert data["success"] is False
            assert "must use '..' separator" in data["error"]

    async def test_error_on_end_before_start_date(self, mock_user):
        """Acceptance Criterion 10: Clear error for invalid date range."""
        params = {
            "query_text": "authentication",
            "time_range": "2024-01-01..2023-01-01",  # Invalid: end before start
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                side_effect=ValueError("End date must be after start date")
            )

            result = await search_code(params, mock_user)

            data = json.loads(result["content"][0]["text"])
            assert data["success"] is False
            assert "End date must be after start date" in data["error"]

    async def test_error_on_unknown_commit(self, mock_user):
        """Acceptance Criterion 10: Clear error for unknown commit."""
        params = {
            "query_text": "authentication",
            "at_commit": "nonexistent",
            "limit": 10,
        }

        with patch("code_indexer.server.app.semantic_query_manager") as mock_qm:
            mock_qm.query_user_repositories = Mock(
                side_effect=ValueError("Commit 'nonexistent' not found in repository")
            )

            result = await search_code(params, mock_user)

            data = json.loads(result["content"][0]["text"])
            assert data["success"] is False
            assert "not found" in data["error"]
