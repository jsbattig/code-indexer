"""
Unit tests for _expand_wildcard_patterns() in handlers.py.

Tests focus on validating that ** glob patterns work correctly with pathspec
(gitignore-style matching) instead of fnmatch.

The critical bug being fixed:
- fnmatch: '**/*.txt' does NOT match 'file.txt' (requires at least one directory)
- pathspec: '**/*.txt' DOES match 'file.txt' (zero or more directories)
"""

import pytest
from unittest.mock import MagicMock, patch
from code_indexer.server.mcp.handlers import _expand_wildcard_patterns


class TestExpandWildcardPatterns:
    """Test suite for _expand_wildcard_patterns() with pathspec matching."""

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_double_star_matches_zero_directories(
        self, mock_registry_class, mock_get_dir
    ):
        """Test ** matches zero directories (pathspec behavior)."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "repo1"},
            {"alias_name": "repo2"},
            {"alias_name": "deep-repo"},
        ]
        mock_registry_class.return_value = mock_registry

        # Pattern **-repo should match "deep-repo" (zero dirs before -repo)
        result = _expand_wildcard_patterns(["**-repo"])

        assert "deep-repo" in result, "** should match zero directories"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_double_star_matches_multiple_directories(
        self, mock_registry_class, mock_get_dir
    ):
        """Test ** matches multiple directory levels."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "org/team/project"},
            {"alias_name": "company/dept/team/app"},
            {"alias_name": "simple"},
        ]
        mock_registry_class.return_value = mock_registry

        # Pattern **project should match both shallow and deep paths
        result = _expand_wildcard_patterns(["**/project"])

        assert "org/team/project" in result, "** should match nested paths"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_star_matches_single_segment(self, mock_registry_class, mock_get_dir):
        """Test * matches within single path segment."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "test-repo1"},
            {"alias_name": "test-repo2"},
            {"alias_name": "prod-repo"},
        ]
        mock_registry_class.return_value = mock_registry

        result = _expand_wildcard_patterns(["test-*"])

        assert "test-repo1" in result
        assert "test-repo2" in result
        assert "prod-repo" not in result, "* should not match different prefix"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_question_mark_matches_single_char(
        self, mock_registry_class, mock_get_dir
    ):
        """Test ? matches exactly one character."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "repo1"},
            {"alias_name": "repo2"},
            {"alias_name": "repo10"},
        ]
        mock_registry_class.return_value = mock_registry

        result = _expand_wildcard_patterns(["repo?"])

        assert "repo1" in result
        assert "repo2" in result
        assert "repo10" not in result, "? should match exactly one char"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_exact_match_no_wildcard(self, mock_registry_class, mock_get_dir):
        """Test literal patterns without wildcards pass through."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "exact-repo"},
            {"alias_name": "other-repo"},
        ]
        mock_registry_class.return_value = mock_registry

        result = _expand_wildcard_patterns(["exact-repo"])

        assert result == ["exact-repo"], "Non-wildcard patterns should pass through"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_no_matches_returns_empty(self, mock_registry_class, mock_get_dir):
        """Test wildcard with no matches returns empty (with warning logged)."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "repo1"},
            {"alias_name": "repo2"},
        ]
        mock_registry_class.return_value = mock_registry

        result = _expand_wildcard_patterns(["nonexistent-*"])

        assert result == [], "Wildcard with no matches should return empty list"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    def test_no_golden_repos_dir_returns_unchanged(self, mock_get_dir):
        """Test when golden_repos_dir is None, patterns returned unchanged."""
        mock_get_dir.return_value = None

        result = _expand_wildcard_patterns(["test-*", "repo?"])

        assert result == [
            "test-*",
            "repo?",
        ], "Should return patterns unchanged when no golden_repos_dir"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_deduplication_preserves_order(self, mock_registry_class, mock_get_dir):
        """Test that duplicate matches are removed while preserving first occurrence order."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "repo1"},
            {"alias_name": "repo2"},
        ]
        mock_registry_class.return_value = mock_registry

        # Both patterns will match repo1 and repo2
        result = _expand_wildcard_patterns(["repo*", "repo?"])

        assert len(result) == 2, "Duplicates should be removed"
        assert result == ["repo1", "repo2"], "Order should be preserved"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_mixed_literal_and_wildcard(self, mock_registry_class, mock_get_dir):
        """Test mixing literal patterns with wildcards."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "exact-match"},
            {"alias_name": "wildcard-repo1"},
            {"alias_name": "wildcard-repo2"},
        ]
        mock_registry_class.return_value = mock_registry

        result = _expand_wildcard_patterns(["exact-match", "wildcard-*"])

        assert "exact-match" in result
        assert "wildcard-repo1" in result
        assert "wildcard-repo2" in result
        assert len(result) == 3

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_empty_pattern_list(self, mock_registry_class, mock_get_dir):
        """Test empty pattern list returns empty."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [{"alias_name": "repo1"}]
        mock_registry_class.return_value = mock_registry

        result = _expand_wildcard_patterns([])

        assert result == [], "Empty pattern list should return empty"

    @patch("code_indexer.server.mcp.handlers._get_golden_repos_dir")
    @patch("code_indexer.server.mcp.handlers.GlobalRegistry")
    def test_complex_double_star_pattern(self, mock_registry_class, mock_get_dir):
        """Test complex ** patterns like org/**/prod."""
        mock_get_dir.return_value = "/fake/path"
        mock_registry = MagicMock()
        mock_registry.list_global_repos.return_value = [
            {"alias_name": "org/prod"},
            {"alias_name": "org/team/prod"},
            {"alias_name": "org/dept/team/prod"},
            {"alias_name": "company/prod"},
        ]
        mock_registry_class.return_value = mock_registry

        result = _expand_wildcard_patterns(["org/**/prod"])

        assert "org/prod" in result, "** should match zero directories"
        assert "org/team/prod" in result, "** should match one directory"
        assert "org/dept/team/prod" in result, "** should match multiple directories"
        assert (
            "company/prod" not in result
        ), "Should not match different organization"
