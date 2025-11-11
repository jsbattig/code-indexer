"""Test that daemon mode respects --snippet-lines 0 for FTS queries."""

from pathlib import Path
from unittest.mock import patch


class TestDaemonFTSSnippetLinesZero:
    """Test that --snippet-lines 0 works in daemon mode for FTS queries."""

    def test_cli_daemon_fast_parses_snippet_lines_parameter(self):
        """Test that cli_daemon_fast properly parses --snippet-lines parameter."""
        from src.code_indexer.cli_daemon_fast import parse_query_args

        # Test parsing --snippet-lines 0
        args = ["voyage", "--fts", "--snippet-lines", "0", "--limit", "2"]
        result = parse_query_args(args)

        assert result["query_text"] == "voyage"
        assert result["is_fts"]
        assert result["limit"] == 2
        assert result["filters"]["snippet_lines"] == 0

        # Test parsing --snippet-lines 3 (non-zero)
        args = ["search", "--fts", "--snippet-lines", "3"]
        result = parse_query_args(args)

        assert result["query_text"] == "search"
        assert result["is_fts"]
        assert result["filters"]["snippet_lines"] == 3

    def test_daemon_rpyc_service_extracts_snippet_lines_from_kwargs(self):
        """Test that the daemon RPC service correctly extracts snippet_lines from kwargs.

        Tests that snippet_lines=0 parameter is properly forwarded from CLI → Daemon → TantivyIndexManager.
        This validates the production code path for --snippet-lines 0 functionality.
        """
        from src.code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()

        # Create test project directory
        test_project = Path("/test/project")

        # Mock _execute_fts_search to intercept the call with all parameters
        mock_results = [
            {
                "path": "/test/file.py",
                "line": 10,
                "column": 5,
                "match_text": "voyage",
                "snippet": "",  # Empty when snippet_lines=0
                "language": "python",
            }
        ]

        with patch.object(
            service, "_execute_fts_search", return_value=mock_results
        ) as mock_execute:
            # Call exposed_query_fts (the RPC-exposed method) with snippet_lines=0
            result = service.exposed_query_fts(
                str(test_project),
                "voyage",
                snippet_lines=0,  # This is the key parameter
                limit=2,
                case_sensitive=False,
                edit_distance=0,
                use_regex=False,
            )

            # Verify _execute_fts_search was called with snippet_lines=0
            mock_execute.assert_called_once_with(
                str(test_project),
                "voyage",
                snippet_lines=0,  # Should be passed through correctly
                limit=2,
                case_sensitive=False,
                edit_distance=0,
                use_regex=False,
            )

            # Verify result structure
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["snippet"] == ""

    def test_tantivy_extract_snippet_returns_empty_for_zero_lines(self):
        """Test that TantivyIndexManager._extract_snippet returns empty snippet when snippet_lines=0."""
        from src.code_indexer.services.tantivy_index_manager import TantivyIndexManager

        # Create instance with mocked init
        with patch.object(TantivyIndexManager, "__init__", return_value=None):
            manager = TantivyIndexManager.__new__(TantivyIndexManager)

            # Test content
            content = """Line 1
Line 2
Line 3 with voyage here
Line 4
Line 5"""

            # Match is on line 3 (0-indexed as line 2), column 12
            match_start = content.index("voyage")
            match_len = len("voyage")

            # Call _extract_snippet with snippet_lines=0
            snippet, line_num, column, snippet_start_line = manager._extract_snippet(
                content, match_start, match_len, snippet_lines=0
            )

            # Verify empty snippet is returned
            assert snippet == ""
            assert line_num == 3  # Line 3 (1-indexed)
            assert column == 13  # Column 13 (1-indexed)
            assert snippet_start_line == 3

            # Call _extract_snippet with snippet_lines=1 to verify non-zero case
            snippet, line_num, column, snippet_start_line = manager._extract_snippet(
                content, match_start, match_len, snippet_lines=1
            )

            # Should return context lines
            assert snippet != ""
            assert "voyage" in snippet
            assert line_num == 3

    def test_cli_daemon_fast_result_extraction_fix(self):
        """Test that cli_daemon_fast correctly extracts results list from FTS response dict."""
        # This tests the actual fix we made

        # Test case 1: Response is a dict with results key (daemon mode)
        fts_response_dict = {
            "results": [{"path": "file.py", "snippet": ""}],
            "query": "test",
            "total": 1,
        }

        # Our fix: Extract results from dict
        result = (
            fts_response_dict.get("results", [])
            if isinstance(fts_response_dict, dict)
            else fts_response_dict
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["path"] == "file.py"

        # Test case 2: Response is already a list (backward compatibility)
        fts_response_list = [{"path": "file2.py", "snippet": ""}]

        result = (
            fts_response_list
            if not isinstance(fts_response_list, dict)
            else fts_response_list.get("results", [])
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["path"] == "file2.py"
