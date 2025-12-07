"""Tests for omni-search wildcard pattern expansion."""

import pytest
from unittest.mock import patch, Mock
from code_indexer.server.mcp.handlers import _expand_wildcard_patterns, _has_wildcard


class TestHasWildcard:
    """Test wildcard detection."""

    def test_asterisk_detected(self):
        assert _has_wildcard("*-global") is True

    def test_question_mark_detected(self):
        assert _has_wildcard("repo-?") is True

    def test_bracket_detected(self):
        assert _has_wildcard("repo-[abc]") is True

    def test_no_wildcard(self):
        assert _has_wildcard("evolution-global") is False

    def test_empty_string(self):
        assert _has_wildcard("") is False


class TestExpandWildcardPatterns:
    """Test wildcard pattern expansion."""

    @pytest.fixture
    def mock_registry(self):
        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.return_value = "/fake/golden/repos"
            with patch("code_indexer.server.mcp.handlers.GlobalRegistry") as mock_reg:
                mock_instance = Mock()
                mock_instance.list_global_repos.return_value = [
                    {"alias": "evolution-global"},
                    {"alias": "evo-mobile-global"},
                    {"alias": "backend-global"},
                    {"alias": "frontend-global"},
                    {"alias": "other-project"},
                ]
                mock_reg.return_value = mock_instance
                yield mock_reg

    def test_asterisk_suffix_pattern(self, mock_registry):
        result = _expand_wildcard_patterns(["*-global"])
        assert set(result) == {"evolution-global", "evo-mobile-global", "backend-global", "frontend-global"}

    def test_asterisk_prefix_pattern(self, mock_registry):
        result = _expand_wildcard_patterns(["evo*"])
        assert set(result) == {"evolution-global", "evo-mobile-global"}

    def test_literal_pattern_unchanged(self, mock_registry):
        result = _expand_wildcard_patterns(["evolution-global"])
        assert result == ["evolution-global"]

    def test_mixed_patterns(self, mock_registry):
        result = _expand_wildcard_patterns(["*-global", "other-project"])
        assert "evolution-global" in result
        assert "other-project" in result

    def test_no_matches_returns_empty(self, mock_registry):
        result = _expand_wildcard_patterns(["nonexistent-*"])
        assert result == []

    def test_deduplication(self, mock_registry):
        result = _expand_wildcard_patterns(["*-global", "evolution-global"])
        # evolution-global should appear only once
        assert result.count("evolution-global") == 1

    def test_no_golden_repos_dir_returns_unchanged(self):
        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.return_value = None
            result = _expand_wildcard_patterns(["*-global"])
            assert result == ["*-global"]

    def test_registry_error_returns_unchanged(self):
        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.return_value = "/fake/golden/repos"
            with patch("code_indexer.server.mcp.handlers.GlobalRegistry") as mock_reg:
                mock_reg.side_effect = Exception("Registry failed")
                result = _expand_wildcard_patterns(["*-global"])
                assert result == ["*-global"]
