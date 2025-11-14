"""Test daemon mode --quiet flag parsing and propagation.

This test validates that the --quiet flag is correctly parsed from command-line
arguments and propagated to display functions in daemon mode.

Critical Bug: The --quiet flag was correctly parsed but hardcoded to False
in display function calls, causing daemon mode to always show verbose output.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from code_indexer.cli_daemon_fast import (
    parse_query_args,
    _display_results,
)


class TestDaemonQuietFlagParsing:
    """Test suite for --quiet flag parsing in daemon mode."""

    def test_parse_query_args_quiet_flag_true(self):
        """Test that parse_query_args correctly sets quiet=True when --quiet is present."""
        args = ["test query", "--quiet", "--limit", "10"]
        result = parse_query_args(args)

        assert (
            result["quiet"] is True
        ), "quiet flag should be True when --quiet is present"
        assert result["query_text"] == "test query"
        assert result["limit"] == 10


class TestDaemonQuietFlagPropagation:
    """Test suite for --quiet flag propagation to display functions."""

    def test_display_results_passes_quiet_to_fts_display(self):
        """Test that _display_results passes quiet parameter to FTS display function."""
        # Patch where the function is imported (in cli_daemon_fast._display_results)
        with patch("code_indexer.cli._display_fts_results") as mock_fts:
            from rich.console import Console

            console = Console()

            # FTS result format (has 'match_text', no 'payload')
            fts_results = [{"match_text": "test match", "file_path": "test.py"}]

            # Test with quiet=True - should pass to display function
            _display_results(fts_results, console, timing_info=None, quiet=True)

            # Verify FTS display was called with quiet=True
            mock_fts.assert_called_once()
            call_kwargs = mock_fts.call_args[1]
            assert (
                call_kwargs.get("quiet") is True
            ), "_display_fts_results should receive quiet=True"

    @patch("code_indexer.config.ConfigManager")
    @patch("code_indexer.cli_daemon_fast.get_socket_path")
    @patch("code_indexer.cli_daemon_delegation._connect_to_daemon")
    @patch("code_indexer.cli_daemon_fast._display_results")
    def test_execute_query_with_quiet_passes_to_display(
        self, mock_display, mock_connect, mock_socket_path, mock_config_mgr
    ):
        """Test that execute_via_daemon extracts and passes quiet flag to _display_results."""
        # Setup mocks
        mock_socket_path.return_value = Path("/tmp/test.sock")

        mock_conn = MagicMock()
        mock_conn.root.exposed_query.return_value = {
            "results": [{"payload": {"content": "test"}, "score": 0.85}],
            "timing": {"embedding_time_ms": 50},
        }
        mock_connect.return_value = mock_conn

        mock_config_mgr.create_with_backtrack.return_value.get_daemon_config.return_value = {
            "enabled": True,
            "retry_delays_ms": [100],
        }

        # Simulate query with --quiet flag
        from code_indexer.cli_daemon_fast import execute_via_daemon

        argv = ["cidx", "query", "test query", "--quiet"]
        config_path = Path("/fake/.code-indexer/config.json")

        # Execute query
        execute_via_daemon(argv, config_path)

        # Verify _display_results was called with quiet=True
        assert mock_display.called, "_display_results should be called"
        call_kwargs = mock_display.call_args[1]
        assert (
            call_kwargs.get("quiet") is True
        ), "quiet=True should be passed to _display_results"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
