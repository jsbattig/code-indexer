"""Tests for context-aware error suggestions in MCP handlers."""

import pytest
from unittest.mock import patch, Mock
from datetime import datetime
import json


class TestErrorWithSuggestions:
    """Test the error suggestion helper function."""

    def test_fuzzy_match_typo(self):
        """Test that typos get matched to correct values."""
        from code_indexer.server.mcp.handlers import _error_with_suggestions

        result = _error_with_suggestions(
            error_msg="Repository not found",
            attempted_value="evolution-gloabl",  # typo: gloabl -> global
            available_values=["evolution-global", "backend-global", "frontend-global"],
        )

        assert result["success"] is False
        assert result["error"] == "Repository not found"
        assert "evolution-global" in result["suggestions"]
        assert len(result["suggestions"]) <= 3
        assert "available_values" in result

    def test_no_match_returns_empty_suggestions(self):
        """Test that completely wrong value returns empty suggestions."""
        from code_indexer.server.mcp.handlers import _error_with_suggestions

        result = _error_with_suggestions(
            error_msg="Repository not found",
            attempted_value="xyzabc123",  # no match
            available_values=["evolution-global", "backend-global"],
        )

        assert result["suggestions"] == []
        assert len(result["available_values"]) > 0

    def test_available_values_limited(self):
        """Test that available_values are limited to prevent huge responses."""
        from code_indexer.server.mcp.handlers import _error_with_suggestions

        many_repos = [f"repo-{i}-global" for i in range(50)]
        result = _error_with_suggestions(
            error_msg="Not found",
            attempted_value="repo-1-global",
            available_values=many_repos,
        )

        assert len(result["available_values"]) <= 10


class TestGetAvailableRepos:
    """Test the available repos helper."""

    def test_returns_repo_list(self):
        """Test that available repos are returned."""
        from code_indexer.server.mcp.handlers import _get_available_repos

        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.return_value = "/fake/path"
            with patch("code_indexer.server.mcp.handlers.GlobalRegistry") as mock_reg:
                mock_instance = Mock()
                mock_instance.list_global_repos.return_value = [
                    {"alias_name": "evolution-global"},
                    {"alias_name": "backend-global"},
                ]
                mock_reg.return_value = mock_instance

                result = _get_available_repos()

                assert result == ["evolution-global", "backend-global"]

    def test_returns_empty_on_error(self):
        """Test graceful handling of registry errors."""
        from code_indexer.server.mcp.handlers import _get_available_repos

        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.side_effect = RuntimeError("No golden_repos_dir")

            result = _get_available_repos()

            assert result == []


class TestSearchCodeErrorSuggestions:
    """Test that search_code returns suggestions on repo not found."""

    @pytest.mark.asyncio
    async def test_search_code_repo_not_found_has_suggestions(self):
        """Test search_code returns suggestions when repo not found."""
        from code_indexer.server.mcp.handlers import search_code
        from code_indexer.server.auth.user_manager import User, UserRole

        user = User(
            username="testuser",
            password_hash="hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(),
        )

        params = {
            "query_text": "test",
            "repository_alias": "evolution-gloabl",  # typo
        }

        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.return_value = "/fake/path"
            with patch("code_indexer.server.mcp.handlers.GlobalRegistry") as mock_reg:
                mock_instance = Mock()
                mock_instance.list_global_repos.return_value = [
                    {"alias_name": "evolution-global"},
                    {"alias_name": "backend-global"},
                ]
                mock_reg.return_value = mock_instance

                result = await search_code(params, user)

                response_data = json.loads(result["content"][0]["text"])

                assert response_data["success"] is False
                assert "suggestions" in response_data
                assert "evolution-global" in response_data["suggestions"]
                assert "available_values" in response_data
