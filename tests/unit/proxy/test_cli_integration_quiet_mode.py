"""Unit tests for CLI integration quiet mode handling.

Tests that cli_integration._execute_query properly respects user's --quiet
preference and doesn't force --quiet flag.
"""

from unittest.mock import Mock, patch
from code_indexer.proxy.cli_integration import _execute_query, _extract_limit_from_args


class TestCliIntegrationQuietMode:
    """Test CLI integration handling of --quiet flag."""

    @patch("code_indexer.proxy.cli_integration.ParallelCommandExecutor")
    @patch("code_indexer.proxy.cli_integration.QueryResultAggregator")
    @patch("code_indexer.proxy.cli_integration.RichFormatAggregator")
    def test_user_quiet_flag_is_respected(
        self, mock_rich_agg, mock_query_agg, mock_executor
    ):
        """Test that user-specified --quiet flag is preserved."""
        # Setup
        repo_paths = ["/repo1", "/repo2"]
        args = ["search query", "--quiet", "--limit", "10"]

        mock_executor_instance = Mock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_parallel.return_value = {
            "/repo1": ("0.9 /repo1/file.py:1-10\n  1: code", "", 0),
            "/repo2": ("0.8 /repo2/test.py:5-15\n  5: test", "", 0),
        }

        mock_query_agg_instance = Mock()
        mock_query_agg.return_value = mock_query_agg_instance
        mock_query_agg_instance.aggregate_results.return_value = (
            "aggregated quiet output"
        )

        # Execute
        result = _execute_query(args, repo_paths)

        # Verify
        # Should NOT add another --quiet flag
        call_args = mock_executor_instance.execute_parallel.call_args[0]
        query_args = call_args[1]

        # Count --quiet flags - should be exactly 1
        quiet_count = query_args.count("--quiet")
        assert quiet_count == 1, "Should preserve single --quiet flag"

        # Should use QueryResultAggregator (quiet mode)
        mock_query_agg_instance.aggregate_results.assert_called_once()

        assert result == 0

    @patch("code_indexer.proxy.cli_integration.ParallelCommandExecutor")
    @patch("code_indexer.proxy.cli_integration.RichFormatAggregator")
    def test_no_quiet_flag_uses_rich_format(self, mock_rich_agg, mock_executor):
        """Test that absence of --quiet flag uses rich format aggregator."""
        # Setup
        repo_paths = ["/repo1", "/repo2"]
        args = ["search query", "--limit", "10"]  # NO --quiet flag

        mock_executor_instance = Mock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_parallel.return_value = {
            "/repo1": ("rich format output 1", "", 0),
            "/repo2": ("rich format output 2", "", 0),
        }

        mock_rich_agg_instance = Mock()
        mock_rich_agg.return_value = mock_rich_agg_instance
        mock_rich_agg_instance.aggregate_results.return_value = "aggregated rich output"

        # Execute
        result = _execute_query(args, repo_paths)

        # Verify
        # Should NOT add --quiet flag
        call_args = mock_executor_instance.execute_parallel.call_args[0]
        query_args = call_args[1]

        assert "--quiet" not in query_args, "Should NOT add --quiet flag"
        assert "-q" not in query_args, "Should NOT add -q flag"

        # Should use RichFormatAggregator (non-quiet mode)
        mock_rich_agg_instance.aggregate_results.assert_called_once()

        assert result == 0

    @patch("code_indexer.proxy.cli_integration.ParallelCommandExecutor")
    @patch("code_indexer.proxy.cli_integration.QueryResultAggregator")
    def test_short_quiet_flag_is_respected(self, mock_query_agg, mock_executor):
        """Test that user-specified -q flag is preserved."""
        # Setup
        repo_paths = ["/repo1"]
        args = ["search query", "-q"]

        mock_executor_instance = Mock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_parallel.return_value = {
            "/repo1": ("0.9 /repo1/file.py:1-10\n  1: code", "", 0)
        }

        mock_query_agg_instance = Mock()
        mock_query_agg.return_value = mock_query_agg_instance
        mock_query_agg_instance.aggregate_results.return_value = "quiet output"

        # Execute
        result = _execute_query(args, repo_paths)

        # Verify
        call_args = mock_executor_instance.execute_parallel.call_args[0]
        query_args = call_args[1]

        # Should preserve -q flag
        assert "-q" in query_args or "--quiet" in query_args
        # Should NOT duplicate
        quiet_count = query_args.count("-q") + query_args.count("--quiet")
        assert quiet_count == 1

        # Should use quiet aggregator
        mock_query_agg_instance.aggregate_results.assert_called_once()

        assert result == 0

    @patch("code_indexer.proxy.cli_integration.ParallelCommandExecutor")
    @patch("code_indexer.proxy.cli_integration.RichFormatAggregator")
    def test_rich_format_includes_repository_context(
        self, mock_rich_agg, mock_executor
    ):
        """Test that rich format aggregator receives repository context."""
        # Setup
        repo_paths = ["/home/dev/repo1", "/home/dev/repo2"]
        args = ["search query"]  # No --quiet

        mock_executor_instance = Mock()
        mock_executor.return_value = mock_executor_instance
        mock_executor_instance.execute_parallel.return_value = {
            "/home/dev/repo1": ("rich output 1", "", 0),
            "/home/dev/repo2": ("rich output 2", "", 0),
        }

        mock_rich_agg_instance = Mock()
        mock_rich_agg.return_value = mock_rich_agg_instance
        mock_rich_agg_instance.aggregate_results.return_value = "rich output"

        # Execute
        result = _execute_query(args, repo_paths)

        # Verify - aggregator called with repository outputs
        call_args = mock_rich_agg_instance.aggregate_results.call_args
        repository_outputs = call_args[0][0]

        assert "/home/dev/repo1" in repository_outputs
        assert "/home/dev/repo2" in repository_outputs
        assert repository_outputs["/home/dev/repo1"] == "rich output 1"
        assert repository_outputs["/home/dev/repo2"] == "rich output 2"

        assert result == 0

    def test_extract_limit_from_args_with_long_flag(self):
        """Test extracting limit from --limit flag."""
        args = ["query", "--limit", "20", "--language", "python"]
        limit = _extract_limit_from_args(args)
        assert limit == 20

    def test_extract_limit_from_args_with_short_flag(self):
        """Test extracting limit from -l flag."""
        args = ["query", "-l", "15"]
        limit = _extract_limit_from_args(args)
        assert limit == 15

    def test_extract_limit_from_args_default(self):
        """Test default limit when flag not present."""
        args = ["query", "--language", "python"]
        limit = _extract_limit_from_args(args)
        assert limit == 10  # Default limit

    def test_extract_limit_from_args_invalid_value(self):
        """Test handling invalid limit value."""
        args = ["query", "--limit", "invalid"]
        limit = _extract_limit_from_args(args)
        assert limit == 10  # Falls back to default

    def test_extract_limit_from_args_missing_value(self):
        """Test handling --limit flag without value."""
        args = ["query", "--limit"]
        limit = _extract_limit_from_args(args)
        assert limit == 10  # Falls back to default
