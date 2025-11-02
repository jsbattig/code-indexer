"""Test that --snippet-lines 0 works correctly in daemon mode for FTS queries.

This test reproduces the issue where daemon mode shows snippets even when
snippet_lines=0 is specified, while standalone mode correctly shows only file listings.

BUG CONTEXT:
- Standalone mode: `cidx query "voyage" --fts --snippet-lines 0 --limit 2` works correctly
- Daemon mode: Same command shows full snippets instead of empty snippets
- Root cause: Parameter not properly propagated through RPC call chain

Expected behavior: Both modes should produce identical output (no snippets).
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from code_indexer.services.rpyc_daemon import CIDXDaemonService


class TestFTSSnippetLinesZeroDaemon:
    """Test FTS query with snippet_lines=0 in daemon mode."""

    def test_daemon_execute_fts_search_passes_snippet_lines(self, tmp_path):
        """Test that _execute_fts_search passes snippet_lines to TantivyIndexManager.

        This tests the parameter propagation from daemon RPC to TantivyIndexManager.search().
        """
        # Setup test project
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create daemon service
        daemon = CIDXDaemonService()

        # Create cache entry with mock tantivy index
        from code_indexer.services.rpyc_daemon import CacheEntry
        daemon.cache_entry = CacheEntry(project_path)

        # Mock tantivy searcher
        mock_searcher = Mock()
        daemon.cache_entry.tantivy_searcher = mock_searcher
        daemon.cache_entry.tantivy_index = Mock()

        # Mock TantivyIndexManager inside _execute_fts_search
        with patch("code_indexer.services.tantivy_index_manager.TantivyIndexManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            # Setup mock index and schema
            daemon.cache_entry.tantivy_index = Mock()
            daemon.cache_entry.tantivy_index.schema.return_value = Mock()

            # Mock search method to capture parameters
            captured_kwargs = {}
            def capture_search_params(**kwargs):
                captured_kwargs.update(kwargs)
                # Return mock results with snippets
                return [
                    {
                        "path": "test.py",
                        "line": 10,
                        "column": 5,
                        "match_text": "voyage",
                        "snippet": "this should be empty",  # Will be empty after fix
                        "snippet_start_line": 9,
                        "language": "python"
                    }
                ]

            mock_manager.search.side_effect = capture_search_params

            # Call _execute_fts_search directly with snippet_lines=0
            result = daemon._execute_fts_search(
                mock_searcher,
                "voyage",
                snippet_lines=0,  # CRITICAL: Pass snippet_lines=0
                limit=2
            )

            # Verify search was called
            mock_manager.search.assert_called_once()

            # FAILING ASSERTION: Verify snippet_lines was passed
            assert "snippet_lines" in captured_kwargs, \
                "snippet_lines parameter not passed to TantivyIndexManager.search()"

            assert captured_kwargs["snippet_lines"] == 0, \
                f"Expected snippet_lines=0, got {captured_kwargs.get('snippet_lines')}"

    def test_daemon_fts_query_snippet_lines_zero_returns_empty_snippets(self, tmp_path):
        """Test that daemon FTS query with snippet_lines=0 returns empty snippets (end-to-end).

        FAILING TEST: This will fail until we fix parameter propagation.

        Expected: results should have empty snippets when snippet_lines=0
        Actual: results currently have non-empty snippets
        """
        # Setup test project
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create daemon service
        daemon = CIDXDaemonService()

        # Create cache entry with mock tantivy index
        from code_indexer.services.rpyc_daemon import CacheEntry
        daemon.cache_entry = CacheEntry(project_path)
        daemon.cache_entry.tantivy_index = Mock()
        daemon.cache_entry.tantivy_searcher = Mock()
        daemon.cache_entry.fts_available = True

        # Mock TantivyIndexManager
        with patch("code_indexer.services.tantivy_index_manager.TantivyIndexManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            mock_manager._index = daemon.cache_entry.tantivy_index
            mock_manager._index.schema.return_value = Mock()

            # Mock search to return results with snippets
            mock_manager.search.return_value = [
                {
                    "path": "test.py",
                    "line": 10,
                    "column": 5,
                    "match_text": "voyage",
                    "snippet": "",  # This should be empty with snippet_lines=0
                    "snippet_start_line": 9,
                    "language": "python"
                }
            ]

            # Execute FTS query with snippet_lines=0
            result = daemon.exposed_query_fts(
                project_path=str(project_path),
                query="voyage",
                snippet_lines=0,  # CRITICAL: Request no snippets
                limit=2
            )

            # Verify search was called with snippet_lines=0
            mock_manager.search.assert_called_once()
            call_kwargs = mock_manager.search.call_args.kwargs

            # CRITICAL ASSERTION: Verify snippet_lines was passed
            assert "snippet_lines" in call_kwargs, \
                "snippet_lines parameter not passed to TantivyIndexManager.search()"

            assert call_kwargs["snippet_lines"] == 0, \
                f"Expected snippet_lines=0, got {call_kwargs.get('snippet_lines')}"

    def test_daemon_fts_rpc_call_includes_snippet_lines_parameter(self, tmp_path):
        """Test that RPC call from client to daemon includes snippet_lines parameter.

        This tests the CLIENT -> DAEMON parameter passing.
        """
        # Setup
        project_path = tmp_path / "test_project"
        project_path.mkdir()
        (project_path / ".code-indexer").mkdir()

        daemon = CIDXDaemonService()

        # Call exposed_query_fts with snippet_lines=0 in kwargs
        with patch.object(daemon, "_execute_fts_search") as mock_search:
            mock_search.return_value = {"results": [], "query": "test", "total": 0}

            # Simulate RPC call from client
            result = daemon.exposed_query_fts(
                project_path=str(project_path),
                query="test",
                snippet_lines=0,  # Pass as keyword argument
                limit=5
            )

            # Verify _execute_fts_search was called with snippet_lines
            mock_search.assert_called_once()
            call_args = mock_search.call_args

            # Check if snippet_lines is in kwargs passed to _execute_fts_search
            assert "snippet_lines" in call_args.kwargs or "snippet_lines" in call_args.args[1:], \
                "snippet_lines parameter not forwarded to _execute_fts_search"

    def test_client_delegation_passes_snippet_lines_to_daemon(self):
        """Test that client delegation correctly passes snippet_lines to daemon RPC.

        This tests the CLI -> DELEGATION -> RPC parameter passing.
        """
        from code_indexer.cli_daemon_delegation import _query_via_daemon

        # Mock daemon connection
        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find, \
             patch("code_indexer.cli_daemon_delegation._connect_to_daemon") as mock_connect:

            # Setup mocks
            mock_config_path = Path("/tmp/test/.code-indexer/config.json")
            mock_find.return_value = mock_config_path

            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Mock daemon response
            mock_conn.root.exposed_query_fts.return_value = {
                "results": [],
                "query": "test",
                "total": 0
            }

            # Call delegation function with snippet_lines=0
            daemon_config = {"enabled": True, "retry_delays_ms": [100]}

            exit_code = _query_via_daemon(
                query_text="voyage",
                daemon_config=daemon_config,
                fts=True,
                semantic=False,
                limit=2,
                snippet_lines=0,  # CRITICAL: Pass snippet_lines parameter
            )

            # Verify RPC call included snippet_lines
            mock_conn.root.exposed_query_fts.assert_called_once()
            call_kwargs = mock_conn.root.exposed_query_fts.call_args.kwargs

            # FAILING ASSERTION: snippet_lines should be in RPC call
            assert "snippet_lines" in call_kwargs, \
                "snippet_lines parameter not included in RPC call to daemon"

            assert call_kwargs["snippet_lines"] == 0, \
                f"Expected snippet_lines=0 in RPC call, got {call_kwargs.get('snippet_lines')}"

            assert exit_code == 0, "Query should succeed"

    def test_tantivy_manager_respects_snippet_lines_zero(self, tmp_path):
        """Test that TantivyIndexManager returns empty snippets when snippet_lines=0.

        This is the LOW-LEVEL test for the actual snippet extraction logic.
        """
        from code_indexer.services.tantivy_index_manager import TantivyIndexManager

        # Create test index directory
        index_dir = tmp_path / "tantivy_index"
        index_dir.mkdir()

        # This test will be skipped if Tantivy not available
        pytest.importorskip("tantivy")

        # Create TantivyIndexManager (will fail if no index, but that's OK for this test)
        manager = TantivyIndexManager(index_dir)

        # Test the snippet extraction logic directly
        test_content = "line1\nline2\nline3\nline4\nline5"
        match_start = 6  # Start of "line2"
        match_len = 5

        # Call _extract_snippet with snippet_lines=0
        snippet, line_num, col, snippet_start = manager._extract_snippet(
            content=test_content,
            match_start=match_start,
            match_len=match_len,
            snippet_lines=0  # Request no context
        )

        # PASSING ASSERTION: This should already work (verifying existing behavior)
        assert snippet == "", \
            f"Expected empty snippet with snippet_lines=0, got: '{snippet}'"

        # Line/column should still be calculated
        assert line_num == 2, f"Expected line 2, got {line_num}"
        assert col > 0, f"Expected positive column, got {col}"
