"""Unit tests for CLI integration in SemanticQueryManager.

Tests the thin wrapper around CLI's _execute_query function, ensuring:
1. Parameter conversion (server params -> CLI args)
2. CLI function is called correctly
3. Output parsing (CLI format -> QueryResult objects)
4. Error handling
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    QueryResult,
)


class TestCLIParameterConversion:
    """Test parameter conversion from server format to CLI args."""

    def test_converts_basic_query_parameters(self):
        """Test basic query parameters are converted to CLI args format."""
        manager = SemanticQueryManager()

        # Expected: query text and --quiet flag
        args = manager._build_cli_args(query="test query", limit=10, min_score=None)

        assert "test query" in args
        assert "--quiet" in args
        assert "--limit" in args
        assert "10" in args

    def test_converts_all_query_parameters(self):
        """Test all query parameters are converted correctly."""
        manager = SemanticQueryManager()

        args = manager._build_cli_args(
            query="authentication logic",
            limit=20,
            min_score=0.75,
            language="python",
            path="*/tests/*",
            accuracy="high",
        )

        assert "authentication logic" in args
        assert "--quiet" in args
        assert "--limit" in args
        assert "20" in args
        assert "--min-score" in args
        assert "0.75" in args
        assert "--language" in args
        assert "python" in args
        assert "--path" in args
        assert "*/tests/*" in args
        assert "--accuracy" in args
        assert "high" in args

    def test_quiet_flag_always_set(self):
        """Test that --quiet flag is always set for parsing."""
        manager = SemanticQueryManager()

        args = manager._build_cli_args(query="test", limit=10)

        assert "--quiet" in args or "-q" in args

    def test_handles_none_optional_parameters(self):
        """Test that None optional parameters are not included in args."""
        manager = SemanticQueryManager()

        args = manager._build_cli_args(
            query="test",
            limit=10,
            min_score=None,
            language=None,
            path=None,
            accuracy=None,
        )

        # Should only have query, --quiet, and --limit
        assert "test" in args
        assert "--quiet" in args
        assert "--limit" in args
        # Should NOT have other parameters
        assert "--min-score" not in args
        assert "--language" not in args
        assert "--path" not in args
        assert "--accuracy" not in args


class TestCLIOutputParsing:
    """Test parsing of CLI output to QueryResult objects."""

    def test_parses_quiet_mode_output(self):
        """Test parsing of quiet mode CLI output."""
        manager = SemanticQueryManager()

        # Quiet mode format: "score path:line_range\n  line_num: code\n"
        cli_output = """0.95 repo1/auth.py:10-20
  10: def authenticate(user):
  11:     return True

0.85 repo2/user.py:5-15
  5: class User:
  6:     pass
"""

        results = manager._parse_cli_output(
            cli_output, repo_path=Path("/tmp/composite")
        )

        assert len(results) == 2
        assert results[0].similarity_score == 0.95
        assert "repo1/auth.py" in results[0].file_path
        assert results[0].line_number == 10
        assert "def authenticate" in results[0].code_snippet

        assert results[1].similarity_score == 0.85
        assert "repo2/user.py" in results[1].file_path

    def test_parses_empty_output(self):
        """Test parsing of empty CLI output returns empty list."""
        manager = SemanticQueryManager()

        results = manager._parse_cli_output("", repo_path=Path("/tmp/composite"))

        assert results == []

    def test_handles_malformed_output_gracefully(self):
        """Test that malformed output doesn't crash parsing."""
        manager = SemanticQueryManager()

        # Malformed output
        cli_output = "Some random text\nNot a valid result\n"

        results = manager._parse_cli_output(
            cli_output, repo_path=Path("/tmp/composite")
        )

        # Should return empty list for unparseable output
        assert isinstance(results, list)

    def test_extracts_repository_alias_from_path(self):
        """Test that repository alias is extracted from file path."""
        manager = SemanticQueryManager()

        cli_output = """0.95 repo1/auth.py:10-20
  10: def authenticate(user):
"""

        results = manager._parse_cli_output(
            cli_output, repo_path=Path("/tmp/composite")
        )

        assert len(results) == 1
        # Repository alias should be extracted from "repo1/auth.py"
        assert results[0].repository_alias == "repo1"


class TestCLIFunctionIntegration:
    """Test integration with CLI's _execute_query function."""

    @patch("code_indexer.server.query.semantic_query_manager.ProxyConfigManager")
    @patch("code_indexer.server.query.semantic_query_manager._execute_query")
    def test_calls_execute_query_with_correct_args(
        self, mock_execute_query, mock_proxy_config
    ):
        """Test that _execute_query is called with correct arguments."""
        # Setup mocks
        mock_config_manager = Mock()
        mock_config = Mock()
        mock_config.discovered_repos = ["repo1", "repo2"]
        mock_config_manager.load_config.return_value = mock_config
        mock_proxy_config.return_value = mock_config_manager

        mock_execute_query.return_value = 0  # Success exit code

        # Create manager and call search_composite
        manager = SemanticQueryManager()

        with patch.object(manager, "_parse_cli_output", return_value=[]):
            manager._execute_cli_query(
                repo_path=Path("/tmp/composite"),
                query="test query",
                limit=10,
                min_score=0.7,
            )

        # Verify _execute_query was called
        assert mock_execute_query.called

        # Verify args contain our parameters
        call_args = mock_execute_query.call_args[0][0]  # First positional arg
        assert "test query" in call_args
        assert "--quiet" in call_args
        assert "--limit" in call_args

    @patch("code_indexer.server.query.semantic_query_manager.ProxyConfigManager")
    @patch("code_indexer.server.query.semantic_query_manager._execute_query")
    def test_gets_repository_paths_from_proxy_config(
        self, mock_execute_query, mock_proxy_config
    ):
        """Test that repository paths are obtained from ProxyConfigManager."""
        # Setup mocks
        mock_config_manager = Mock()
        mock_config = Mock()
        mock_config.discovered_repos = ["repo1", "repo2"]
        mock_config_manager.load_config.return_value = mock_config
        mock_proxy_config.return_value = mock_config_manager

        mock_execute_query.return_value = 0

        # Create manager and call
        manager = SemanticQueryManager()

        with patch.object(manager, "_parse_cli_output", return_value=[]):
            manager._execute_cli_query(
                repo_path=Path("/tmp/composite"), query="test", limit=10
            )

        # Verify ProxyConfigManager was instantiated with correct path
        mock_proxy_config.assert_called_once_with(Path("/tmp/composite"))

        # Verify _execute_query received repo_paths
        call_args = mock_execute_query.call_args
        repo_paths = call_args[0][1]  # Second positional arg
        assert len(repo_paths) == 2


class TestCLIErrorHandling:
    """Test error handling in CLI integration."""

    @patch("code_indexer.server.query.semantic_query_manager.ProxyConfigManager")
    def test_raises_error_when_proxy_config_fails(self, mock_proxy_config):
        """Test that errors from ProxyConfigManager are handled."""
        # Setup mock to raise exception
        mock_proxy_config.side_effect = Exception("Config not found")

        manager = SemanticQueryManager()

        with pytest.raises(Exception) as exc_info:
            manager._execute_cli_query(
                repo_path=Path("/tmp/composite"), query="test", limit=10
            )

        assert "Config not found" in str(exc_info.value)

    @patch("code_indexer.server.query.semantic_query_manager.ProxyConfigManager")
    @patch("code_indexer.server.query.semantic_query_manager._execute_query")
    def test_handles_cli_execution_failure(self, mock_execute_query, mock_proxy_config):
        """Test handling of CLI execution failures."""
        # Setup mocks
        mock_config_manager = Mock()
        mock_config = Mock()
        mock_config.discovered_repos = ["repo1"]
        mock_config_manager.load_config.return_value = mock_config
        mock_proxy_config.return_value = mock_config_manager

        # Simulate CLI failure (non-zero exit code)
        mock_execute_query.return_value = 1

        manager = SemanticQueryManager()

        # Should handle non-zero exit code gracefully
        with patch.object(manager, "_parse_cli_output", return_value=[]):
            result = manager._execute_cli_query(
                repo_path=Path("/tmp/composite"), query="test", limit=10
            )

        # Should return empty results or raise appropriate error
        assert isinstance(result, list)


class TestSearchCompositeIntegration:
    """Test async search_composite() method."""

    @pytest.mark.asyncio
    @patch("code_indexer.server.query.semantic_query_manager.ProxyConfigManager")
    @patch("code_indexer.server.query.semantic_query_manager._execute_query")
    async def test_search_composite_returns_query_results(
        self, mock_execute_query, mock_proxy_config
    ):
        """Test that search_composite returns list of QueryResult objects."""
        # Setup mocks
        mock_config_manager = Mock()
        mock_config = Mock()
        mock_config.discovered_repos = ["repo1"]
        mock_config_manager.load_config.return_value = mock_config
        mock_proxy_config.return_value = mock_config_manager

        mock_execute_query.return_value = 0

        manager = SemanticQueryManager()

        # Mock CLI output parsing
        mock_results = [
            QueryResult(
                file_path="repo1/auth.py",
                line_number=10,
                code_snippet="def auth():",
                similarity_score=0.95,
                repository_alias="repo1",
            )
        ]

        with patch.object(manager, "_parse_cli_output", return_value=mock_results):
            results = await manager.search_composite(
                repo_path=Path("/tmp/composite"), query="authentication", limit=10
            )

        assert len(results) == 1
        assert isinstance(results[0], QueryResult)
        assert results[0].similarity_score == 0.95

    @pytest.mark.asyncio
    async def test_search_composite_no_longer_returns_empty_list(self):
        """Test that search_composite returns actual results (not stub)."""
        manager = SemanticQueryManager()

        with patch.object(
            manager,
            "_execute_cli_query",
            return_value=[
                QueryResult(
                    file_path="test.py",
                    line_number=1,
                    code_snippet="test",
                    similarity_score=0.8,
                    repository_alias="repo1",
                )
            ],
        ):
            results = await manager.search_composite(
                repo_path=Path("/tmp/test"), query="test", limit=10
            )

        # Should NOT return empty list (stub removed)
        assert len(results) > 0
        assert isinstance(results[0], QueryResult)
