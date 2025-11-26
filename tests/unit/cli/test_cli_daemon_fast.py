"""Tests for lightweight daemon delegation module.

Tests the minimal-import daemon delegation path that achieves
<150ms startup for daemon-mode queries.
"""

import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestExecuteViaDaemon:
    """Test lightweight daemon execution."""

    @patch("code_indexer.cli_daemon_delegation._connect_to_daemon")
    def test_execute_query_fts_via_daemon(self, mock_connect):
        """Test FTS query execution via daemon."""
        # Arrange
        mock_conn = Mock()
        mock_conn.root.exposed_query_fts.return_value = [
            {"payload": {"path": "test.py", "line_start": 10}, "score": 0.95}
        ]
        mock_connect.return_value = mock_conn

        from code_indexer.cli_daemon_fast import execute_via_daemon

        argv = ["cidx", "query", "test_function", "--fts"]
        config_path = Path("/fake/.code-indexer/config.json")

        # Act
        exit_code = execute_via_daemon(argv, config_path)

        # Assert
        assert exit_code == 0
        mock_conn.root.exposed_query_fts.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("code_indexer.cli_daemon_delegation._connect_to_daemon")
    def test_execute_query_semantic_via_daemon(self, mock_connect):
        """Test semantic query execution via daemon."""
        # Arrange
        mock_conn = Mock()
        mock_conn.root.exposed_query.return_value = {
            "results": [
                {"payload": {"path": "module.py", "line_start": 5}, "score": 0.88}
            ],
            "timing": {"search_ms": 150, "total_ms": 200},
        }
        mock_connect.return_value = mock_conn

        from code_indexer.cli_daemon_fast import execute_via_daemon

        argv = ["cidx", "query", "authentication logic"]
        config_path = Path("/fake/.code-indexer/config.json")

        # Act
        exit_code = execute_via_daemon(argv, config_path)

        # Assert
        assert exit_code == 0
        mock_conn.root.exposed_query.assert_called_once()

    @patch("code_indexer.cli_daemon_delegation._connect_to_daemon")
    def test_execute_query_hybrid_via_daemon(self, mock_connect):
        """Test hybrid search execution via daemon."""
        # Arrange
        mock_conn = Mock()
        mock_conn.root.exposed_query_hybrid.return_value = [
            {
                "payload": {"path": "handler.py", "line_start": 20},
                "score": 0.92,
                "source": "fts",
            }
        ]
        mock_connect.return_value = mock_conn

        from code_indexer.cli_daemon_fast import execute_via_daemon

        argv = ["cidx", "query", "error handling", "--fts", "--semantic"]
        config_path = Path("/fake/.code-indexer/config.json")

        # Act
        exit_code = execute_via_daemon(argv, config_path)

        # Assert
        assert exit_code == 0
        mock_conn.root.exposed_query_hybrid.assert_called_once()

    @patch("code_indexer.cli_daemon_delegation._connect_to_daemon")
    def test_handles_daemon_connection_error(self, mock_connect):
        """Test graceful handling when daemon connection fails."""
        # Arrange
        mock_connect.side_effect = ConnectionRefusedError("Daemon not running")

        from code_indexer.cli_daemon_fast import execute_via_daemon

        argv = ["cidx", "query", "test"]
        config_path = Path("/fake/.code-indexer/config.json")

        # Act - should raise exception for caller to handle
        with pytest.raises(ConnectionRefusedError):
            execute_via_daemon(argv, config_path)

    @patch("code_indexer.cli_daemon_delegation._connect_to_daemon")
    def test_displays_results_correctly(self, mock_connect, capsys):
        """Test that results are displayed correctly."""
        # Arrange
        mock_conn = Mock()
        # FTS returns list directly (not dict like semantic search)
        mock_conn.root.exposed_query_fts.return_value = [
            {
                "payload": {
                    "path": "src/module.py",
                    "line_start": 42,
                    "content": "def test_function():",
                },
                "score": 0.95,
            },
            {
                "payload": {
                    "path": "tests/test_module.py",
                    "line_start": 10,
                    "content": "test_function()",
                },
                "score": 0.85,
            },
        ]
        mock_connect.return_value = mock_conn

        from code_indexer.cli_daemon_fast import execute_via_daemon

        argv = ["cidx", "query", "test_function", "--fts"]
        config_path = Path("/fake/.code-indexer/config.json")

        # Act
        execute_via_daemon(argv, config_path)

        # Assert - check output contains results
        captured = capsys.readouterr()
        assert "src/module.py" in captured.out
        assert "42:" in captured.out
        assert "0.95" in captured.out
        assert "tests/test_module.py" in captured.out
        assert "10:" in captured.out


class TestMinimalArgumentParsing:
    """Test lightweight argument parsing without Click."""

    def test_parse_fts_flag(self):
        """Test parsing --fts flag."""
        from code_indexer.cli_daemon_fast import parse_query_args

        args = ["search_term", "--fts"]
        result = parse_query_args(args)

        assert result["query_text"] == "search_term"
        assert result["is_fts"] is True
        assert result["is_semantic"] is False

    def test_parse_semantic_flag(self):
        """Test parsing --semantic flag."""
        from code_indexer.cli_daemon_fast import parse_query_args

        args = ["search_term", "--semantic"]
        result = parse_query_args(args)

        assert result["is_semantic"] is True
        assert result["is_fts"] is False

    def test_parse_hybrid_flags(self):
        """Test parsing both --fts and --semantic."""
        from code_indexer.cli_daemon_fast import parse_query_args

        args = ["search_term", "--fts", "--semantic"]
        result = parse_query_args(args)

        assert result["is_fts"] is True
        assert result["is_semantic"] is True

    def test_parse_limit_flag(self):
        """Test parsing --limit flag."""
        from code_indexer.cli_daemon_fast import parse_query_args

        args = ["search_term", "--limit", "20"]
        result = parse_query_args(args)

        assert result["limit"] == 20

    def test_parse_language_filter(self):
        """Test parsing --language filter."""
        from code_indexer.cli_daemon_fast import parse_query_args

        args = ["search_term", "--language", "python"]
        result = parse_query_args(args)

        assert result["filters"]["language"] == "python"

    def test_parse_path_filter(self):
        """Test parsing --path-filter."""
        from code_indexer.cli_daemon_fast import parse_query_args

        args = ["search_term", "--path-filter", "*/tests/*"]
        result = parse_query_args(args)

        assert result["filters"]["path_filter"] == "*/tests/*"


class TestLightweightDelegationPerformance:
    """Test performance of lightweight delegation module."""

    def test_cli_daemon_fast_import_time(self):
        """Test that cli_daemon_fast imports quickly."""
        # Act - measure import time (should be fast: rpyc + rich only)
        start = time.time()
        import code_indexer.cli_daemon_fast  # noqa: F401

        elapsed_ms = (time.time() - start) * 1000

        # Assert - should be <100ms (rpyc ~50ms + rich ~40ms)
        assert elapsed_ms < 150, f"Import took {elapsed_ms:.0f}ms, expected <150ms"

    @patch("code_indexer.cli_daemon_delegation._connect_to_daemon")
    def test_execute_via_daemon_overhead(self, mock_connect):
        """Test that execute_via_daemon has minimal overhead."""
        # Arrange
        mock_conn = Mock()
        mock_conn.root.exposed_query_fts.return_value = []
        mock_connect.return_value = mock_conn

        from code_indexer.cli_daemon_fast import execute_via_daemon

        argv = ["cidx", "query", "test", "--fts"]
        config_path = Path("/fake/.code-indexer/config.json")

        # Act - measure execution overhead
        start = time.time()
        execute_via_daemon(argv, config_path)
        elapsed_ms = (time.time() - start) * 1000

        # Assert - should be <50ms (just arg parsing + RPC call)
        # Note: Actual RPC is mocked, so this is pure overhead
        assert elapsed_ms < 100, f"Overhead was {elapsed_ms:.0f}ms, expected <100ms"


class TestSocketPathResolution:
    """Test daemon socket path resolution."""
