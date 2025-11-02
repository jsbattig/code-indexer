"""Test that cli_daemon_fast.py uses correct RPC signatures.

This test ensures that the fast path delegation calls daemon RPC methods
with the correct argument signatures to avoid TypeError exceptions.

The daemon service expects:
- exposed_query(project_path, query, limit, **kwargs)
- exposed_query_fts(project_path, query, **kwargs)
- exposed_query_hybrid(project_path, query, **kwargs)

The fast path must call these with keyword arguments, not positional.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from code_indexer.cli_daemon_fast import execute_via_daemon, parse_query_args


class TestFastPathRPCSignatures:
    """Test RPC call signatures in fast path delegation."""

    def test_parse_query_args_fts_mode(self):
        """Test parsing query args for FTS mode."""
        args = ["test", "--fts", "--limit", "20"]
        result = parse_query_args(args)

        assert result["query_text"] == "test"
        assert result["is_fts"] is True
        assert result["is_semantic"] is False
        assert result["limit"] == 20

    def test_parse_query_args_semantic_mode_default(self):
        """Test parsing query args defaults to semantic mode."""
        args = ["authentication"]
        result = parse_query_args(args)

        assert result["query_text"] == "authentication"
        assert result["is_fts"] is False
        assert result["is_semantic"] is True
        assert result["limit"] == 10

    def test_parse_query_args_hybrid_mode(self):
        """Test parsing query args for hybrid mode."""
        args = ["login", "--fts", "--semantic", "--limit", "15"]
        result = parse_query_args(args)

        assert result["query_text"] == "login"
        assert result["is_fts"] is True
        assert result["is_semantic"] is True
        assert result["limit"] == 15

    def test_parse_query_args_with_filters(self):
        """Test parsing query args with language and path filters."""
        args = [
            "test",
            "--fts",
            "--language",
            "python",
            "--path-filter",
            "*/tests/*",
            "--exclude-language",
            "javascript",
        ]
        result = parse_query_args(args)

        assert result["query_text"] == "test"
        assert result["filters"]["language"] == "python"
        assert result["filters"]["path_filter"] == "*/tests/*"
        assert result["filters"]["exclude_language"] == "javascript"

    @patch("code_indexer.cli_daemon_fast.unix_connect")
    def test_fts_query_uses_kwargs_not_positional(self, mock_unix_connect):
        """Test that FTS query calls daemon with **kwargs, not positional args.

        This is the CRITICAL test that reproduces the bug:
        - Before fix: TypeError (3 positional args expected, 4 given)
        - After fix: Correct **kwargs call
        """
        # Setup mock connection
        mock_conn = MagicMock()
        mock_root = MagicMock()
        mock_conn.root = mock_root
        mock_unix_connect.return_value = mock_conn

        # Mock FTS query result
        mock_root.exposed_query_fts.return_value = [
            {
                "score": 0.95,
                "payload": {
                    "path": "test.py",
                    "line_start": 10,
                    "content": "test content",
                },
            }
        ]

        # Create config path
        config_path = Path("/tmp/test/.code-indexer/config.json")

        # Execute FTS query
        argv = ["cidx", "query", "test", "--fts", "--limit", "20"]
        with patch("code_indexer.cli_daemon_fast.Console"):
            exit_code = execute_via_daemon(argv, config_path)

        # Verify success
        assert exit_code == 0

        # CRITICAL: Verify RPC call signature
        # Should be: exposed_query_fts(project_path, query, **kwargs)
        # NOT: exposed_query_fts(project_path, query, options_dict)
        mock_root.exposed_query_fts.assert_called_once()

        call_args = mock_root.exposed_query_fts.call_args
        assert len(call_args.args) == 2  # project_path, query (NO positional options)
        assert "limit" in call_args.kwargs  # limit passed as kwarg

    @patch("code_indexer.cli_daemon_fast.unix_connect")
    def test_semantic_query_signature(self, mock_unix_connect):
        """Test that semantic query uses correct signature."""
        # Setup mock connection
        mock_conn = MagicMock()
        mock_root = MagicMock()
        mock_conn.root = mock_root
        mock_unix_connect.return_value = mock_conn

        # Mock semantic query result (should return dict with results/timing)
        mock_root.exposed_query.return_value = {"results": [], "timing": {}}

        # Create config path
        config_path = Path("/tmp/test/.code-indexer/config.json")

        # Execute semantic query
        argv = ["cidx", "query", "authentication", "--limit", "15"]
        with patch("code_indexer.cli_daemon_fast.Console"):
            exit_code = execute_via_daemon(argv, config_path)

        # Verify success
        assert exit_code == 0

        # Verify RPC call signature
        mock_root.exposed_query.assert_called_once()
        call_args = mock_root.exposed_query.call_args

        # Should be: exposed_query(project_path, query, limit, **kwargs)
        assert len(call_args.args) == 3  # project_path, query, limit
        assert call_args.kwargs == {}  # No additional kwargs in this case

    @patch("code_indexer.cli_daemon_fast.unix_connect")
    def test_hybrid_query_signature(self, mock_unix_connect):
        """Test that hybrid query uses correct signature."""
        # Setup mock connection
        mock_conn = MagicMock()
        mock_root = MagicMock()
        mock_conn.root = mock_root
        mock_unix_connect.return_value = mock_conn

        # Mock hybrid query result
        mock_root.exposed_query_hybrid.return_value = []

        # Create config path
        config_path = Path("/tmp/test/.code-indexer/config.json")

        # Execute hybrid query
        argv = ["cidx", "query", "login", "--fts", "--semantic", "--limit", "25"]
        with patch("code_indexer.cli_daemon_fast.Console"):
            exit_code = execute_via_daemon(argv, config_path)

        # Verify success
        assert exit_code == 0

        # Verify RPC call signature
        mock_root.exposed_query_hybrid.assert_called_once()
        call_args = mock_root.exposed_query_hybrid.call_args

        # Should be: exposed_query_hybrid(project_path, query, **kwargs)
        assert len(call_args.args) == 2  # project_path, query (NO positional options)
        assert "limit" in call_args.kwargs  # limit passed as kwarg

    @patch("code_indexer.cli_daemon_fast.unix_connect")
    def test_fts_query_with_language_filter(self, mock_unix_connect):
        """Test FTS query with language filter passes kwargs correctly."""
        # Setup mock connection
        mock_conn = MagicMock()
        mock_root = MagicMock()
        mock_conn.root = mock_root
        mock_unix_connect.return_value = mock_conn

        # Mock FTS query result
        mock_root.exposed_query_fts.return_value = []

        # Create config path
        config_path = Path("/tmp/test/.code-indexer/config.json")

        # Execute FTS query with language filter
        argv = [
            "cidx",
            "query",
            "test",
            "--fts",
            "--language",
            "python",
            "--limit",
            "30",
        ]
        with patch("code_indexer.cli_daemon_fast.Console"):
            exit_code = execute_via_daemon(argv, config_path)

        # Verify success
        assert exit_code == 0

        # Verify RPC call signature includes language in kwargs
        mock_root.exposed_query_fts.assert_called_once()
        call_args = mock_root.exposed_query_fts.call_args

        assert len(call_args.args) == 2  # project_path, query
        assert call_args.kwargs["limit"] == 30
        assert call_args.kwargs["language"] == "python"

    @patch("code_indexer.cli_daemon_fast.unix_connect")
    def test_connection_error_raises_properly(self, mock_unix_connect):
        """Test that connection errors are raised properly for fallback."""
        # Simulate connection refused
        mock_unix_connect.side_effect = ConnectionRefusedError("Daemon not running")

        # Create config path
        config_path = Path("/tmp/test/.code-indexer/config.json")

        # Execute query should raise ConnectionRefusedError
        argv = ["cidx", "query", "test", "--fts"]
        with pytest.raises(ConnectionRefusedError):
            with patch("code_indexer.cli_daemon_fast.Console"):
                execute_via_daemon(argv, config_path)


class TestFastPathPerformance:
    """Test that fast path achieves performance targets."""

    @pytest.mark.performance
    @patch("code_indexer.cli_daemon_fast.unix_connect")
    def test_fast_path_execution_time(self, mock_unix_connect):
        """Test that fast path executes in <200ms.

        This test verifies the performance target is met when daemon is available.
        """
        import time

        # Setup mock connection (simulate fast daemon response)
        mock_conn = MagicMock()
        mock_root = MagicMock()
        mock_conn.root = mock_root
        mock_unix_connect.return_value = mock_conn

        # Mock fast FTS query result
        mock_root.exposed_query_fts.return_value = []

        # Create config path
        config_path = Path("/tmp/test/.code-indexer/config.json")

        # Measure execution time
        start = time.perf_counter()
        argv = ["cidx", "query", "test", "--fts"]
        with patch("code_indexer.cli_daemon_fast.Console"):
            execute_via_daemon(argv, config_path)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Verify performance target
        # NOTE: This test focuses on fast path logic, not full startup time
        # Full startup includes entry point overhead measured separately
        assert (
            elapsed_ms < 100
        ), f"Fast path execution took {elapsed_ms:.1f}ms (target: <100ms)"
