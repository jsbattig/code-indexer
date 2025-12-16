"""Tests for temporal status visibility in omni-search."""

from unittest.mock import patch, Mock
from code_indexer.server.mcp.handlers import _is_temporal_query, _get_temporal_status


class TestIsTemporalQuery:
    """Test temporal query detection."""

    def test_time_range_is_temporal(self):
        assert _is_temporal_query({"time_range": "2024-01-01..2024-12-31"}) is True

    def test_time_range_all_is_temporal(self):
        assert _is_temporal_query({"time_range_all": True}) is True

    def test_at_commit_is_temporal(self):
        assert _is_temporal_query({"at_commit": "abc123"}) is True

    def test_include_removed_is_temporal(self):
        assert _is_temporal_query({"include_removed": True}) is True

    def test_no_temporal_params(self):
        assert _is_temporal_query({"query_text": "test"}) is False

    def test_false_values_not_temporal(self):
        assert _is_temporal_query({"time_range_all": False, "include_removed": False}) is False


class TestGetTemporalStatus:
    """Test temporal status lookup."""

    def test_returns_temporal_and_non_temporal_repos(self):
        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.return_value = "/fake/path"
            with patch("code_indexer.server.mcp.handlers.GlobalRegistry") as mock_reg:
                mock_instance = Mock()
                mock_instance.list_global_repos.return_value = [
                    {"alias_name": "repo1-global", "enable_temporal": True},
                    {"alias_name": "repo2-global", "enable_temporal": False},
                ]
                mock_reg.return_value = mock_instance

                status = _get_temporal_status(["repo1-global", "repo2-global"])

                assert status["temporal_repos"] == ["repo1-global"]
                assert status["non_temporal_repos"] == ["repo2-global"]
                assert "warning" not in status

    def test_warning_when_no_temporal_repos(self):
        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.return_value = "/fake/path"
            with patch("code_indexer.server.mcp.handlers.GlobalRegistry") as mock_reg:
                mock_instance = Mock()
                mock_instance.list_global_repos.return_value = [
                    {"alias_name": "repo1-global", "enable_temporal": False},
                    {"alias_name": "repo2-global", "enable_temporal": False},
                ]
                mock_reg.return_value = mock_instance

                status = _get_temporal_status(["repo1-global", "repo2-global"])

                assert status["temporal_repos"] == []
                assert len(status["non_temporal_repos"]) == 2
                assert "warning" in status
                assert "--index-commits" in status["warning"]

    def test_returns_empty_on_error(self):
        with patch("code_indexer.server.mcp.handlers._get_golden_repos_dir") as mock_dir:
            mock_dir.side_effect = RuntimeError("No config")

            status = _get_temporal_status(["repo1-global"])

            assert status == {}
