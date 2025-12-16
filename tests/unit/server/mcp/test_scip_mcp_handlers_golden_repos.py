"""Unit tests for SCIP MCP handlers golden repo integration.

Tests verify that SCIP handlers search golden repos directory instead of Path.cwd()
and handle missing SCIP indexes appropriately.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the internal helper function for testing
from code_indexer.server.mcp.handlers import _find_scip_files


class TestFindScipFilesGoldenRepos:
    """Tests for _find_scip_files() golden repos directory search."""

    def test_find_scip_files_searches_golden_repos(self, tmp_path: Path) -> None:
        """Verify _find_scip_files() searches golden repos directory, not Path.cwd()."""
        # Setup: Create mock golden repos structure
        golden_repos_dir = tmp_path / "golden-repos"
        repo1_scip = golden_repos_dir / "repo1" / ".code-indexer" / "scip"
        repo2_scip = golden_repos_dir / "repo2" / ".code-indexer" / "scip"
        repo1_scip.mkdir(parents=True)
        repo2_scip.mkdir(parents=True)

        # Create mock .scip files
        scip_file1 = repo1_scip / "index.scip"
        scip_file2 = repo2_scip / "index.scip"
        scip_file1.write_text("mock scip data 1")
        scip_file2.write_text("mock scip data 2")

        # Mock _get_golden_repos_dir to return our test directory
        with patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_golden:
            mock_get_golden.return_value = str(golden_repos_dir)

            # Execute
            scip_files = _find_scip_files()

            # Verify: Should find both .scip files from golden repos
            assert len(scip_files) == 2
            scip_file_paths = {str(f) for f in scip_files}
            assert str(scip_file1) in scip_file_paths
            assert str(scip_file2) in scip_file_paths

    def test_find_scip_files_returns_empty_when_no_golden_repos_dir(
        self, tmp_path: Path
    ) -> None:
        """Verify _find_scip_files() returns empty list when golden_repos_dir not configured."""
        # Mock _get_golden_repos_dir to raise RuntimeError (not configured)
        with patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_golden:
            mock_get_golden.side_effect = RuntimeError(
                "golden_repos_dir not configured"
            )

            # Execute
            scip_files = _find_scip_files()

            # Verify: Should return empty list, not crash
            assert scip_files == []

    def test_find_scip_files_returns_empty_when_golden_repos_dir_not_exists(
        self, tmp_path: Path
    ) -> None:
        """Verify _find_scip_files() returns empty list when golden_repos_dir doesn't exist."""
        nonexistent_dir = tmp_path / "nonexistent"

        # Mock _get_golden_repos_dir to return nonexistent directory
        with patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_golden:
            mock_get_golden.return_value = str(nonexistent_dir)

            # Execute
            scip_files = _find_scip_files()

            # Verify: Should return empty list
            assert scip_files == []

    def test_find_scip_files_handles_nested_scip_files(self, tmp_path: Path) -> None:
        """Verify _find_scip_files() finds nested .scip files using glob(**/*.scip)."""
        # Setup: Create nested structure
        golden_repos_dir = tmp_path / "golden-repos"
        repo_scip = golden_repos_dir / "repo1" / ".code-indexer" / "scip"
        nested_dir = repo_scip / "subdir"
        nested_dir.mkdir(parents=True)

        # Create .scip files at different levels
        scip_file1 = repo_scip / "index.scip"
        scip_file2 = nested_dir / "nested.scip"
        scip_file1.write_text("mock scip data 1")
        scip_file2.write_text("mock scip data 2")

        # Mock _get_golden_repos_dir
        with patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_golden:
            mock_get_golden.return_value = str(golden_repos_dir)

            # Execute
            scip_files = _find_scip_files()

            # Verify: Should find both files
            assert len(scip_files) == 2

    def test_find_scip_files_ignores_non_directory_entries(
        self, tmp_path: Path
    ) -> None:
        """Verify _find_scip_files() skips non-directory entries in golden repos."""
        # Setup: Create golden repos with file and directory
        golden_repos_dir = tmp_path / "golden-repos"
        golden_repos_dir.mkdir(parents=True)

        # Create a file (should be ignored)
        file_entry = golden_repos_dir / "somefile.txt"
        file_entry.write_text("not a repo")

        # Create a valid repo directory
        repo_scip = golden_repos_dir / "repo1" / ".code-indexer" / "scip"
        repo_scip.mkdir(parents=True)
        scip_file = repo_scip / "index.scip"
        scip_file.write_text("mock scip data")

        # Mock _get_golden_repos_dir
        with patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_golden:
            mock_get_golden.return_value = str(golden_repos_dir)

            # Execute
            scip_files = _find_scip_files()

            # Verify: Should only find the one valid .scip file
            assert len(scip_files) == 1
            assert str(scip_files[0]) == str(scip_file)


class TestScipHandlersErrorHandling:
    """Tests for SCIP handlers error handling when no indexes exist."""

    @pytest.mark.asyncio
    async def test_scip_definition_returns_error_when_no_indexes(self) -> None:
        """Verify scip_definition returns error when _find_scip_files() returns empty."""
        from code_indexer.server.mcp.handlers import scip_definition

        # Mock _find_scip_files to return empty list
        with patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find:
            mock_find.return_value = []

            # Mock user
            mock_user = MagicMock()

            # Execute
            params = {"symbol": "some_function"}
            result = await scip_definition(params, mock_user)

            # Verify: Should return error, not empty results
            content = result.get("content", [])
            assert len(content) > 0
            data = json.loads(content[0]["text"])
            assert data["success"] is False
            assert "No SCIP indexes found" in data["error"]
            assert "cidx scip generate" in data["error"]

    @pytest.mark.asyncio
    async def test_scip_references_returns_error_when_no_indexes(self) -> None:
        """Verify scip_references returns error when _find_scip_files() returns empty."""
        from code_indexer.server.mcp.handlers import scip_references

        with patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find:
            mock_find.return_value = []
            mock_user = MagicMock()
            params = {"symbol": "some_function"}
            result = await scip_references(params, mock_user)

            content = result.get("content", [])
            assert len(content) > 0
            data = json.loads(content[0]["text"])
            assert data["success"] is False
            assert "No SCIP indexes found" in data["error"]

    @pytest.mark.asyncio
    async def test_scip_dependencies_returns_error_when_no_indexes(self) -> None:
        """Verify scip_dependencies returns error when _find_scip_files() returns empty."""
        from code_indexer.server.mcp.handlers import scip_dependencies

        with patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find:
            mock_find.return_value = []
            mock_user = MagicMock()
            params = {"symbol": "some_function"}
            result = await scip_dependencies(params, mock_user)

            content = result.get("content", [])
            assert len(content) > 0
            data = json.loads(content[0]["text"])
            assert data["success"] is False
            assert "No SCIP indexes found" in data["error"]

    @pytest.mark.asyncio
    async def test_scip_dependents_returns_error_when_no_indexes(self) -> None:
        """Verify scip_dependents returns error when _find_scip_files() returns empty."""
        from code_indexer.server.mcp.handlers import scip_dependents

        with patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find:
            mock_find.return_value = []
            mock_user = MagicMock()
            params = {"symbol": "some_function"}
            result = await scip_dependents(params, mock_user)

            content = result.get("content", [])
            assert len(content) > 0
            data = json.loads(content[0]["text"])
            assert data["success"] is False
            assert "No SCIP indexes found" in data["error"]

    @pytest.mark.asyncio
    async def test_scip_impact_returns_error_when_no_indexes(self) -> None:
        """Verify scip_impact returns error when _find_scip_files() returns empty."""
        from code_indexer.server.mcp.handlers import scip_impact

        with patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find:
            mock_find.return_value = []
            mock_user = MagicMock()
            params = {"symbol": "some_function"}
            result = await scip_impact(params, mock_user)

            content = result.get("content", [])
            assert len(content) > 0
            data = json.loads(content[0]["text"])
            assert data["success"] is False
            assert "No SCIP indexes found" in data["error"]

    @pytest.mark.asyncio
    async def test_scip_callchain_returns_error_when_no_indexes(self) -> None:
        """Verify scip_callchain returns error when _find_scip_files() returns empty."""
        from code_indexer.server.mcp.handlers import scip_callchain

        with patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find:
            mock_find.return_value = []
            mock_user = MagicMock()
            params = {"from_symbol": "func1", "to_symbol": "func2"}
            result = await scip_callchain(params, mock_user)

            content = result.get("content", [])
            assert len(content) > 0
            data = json.loads(content[0]["text"])
            assert data["success"] is False
            assert "No SCIP indexes found" in data["error"]

    @pytest.mark.asyncio
    async def test_scip_context_returns_error_when_no_indexes(self) -> None:
        """Verify scip_context returns error when _find_scip_files() returns empty."""
        from code_indexer.server.mcp.handlers import scip_context

        with patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find:
            mock_find.return_value = []
            mock_user = MagicMock()
            params = {"symbol": "some_function"}
            result = await scip_context(params, mock_user)

            content = result.get("content", [])
            assert len(content) > 0
            data = json.loads(content[0]["text"])
            assert data["success"] is False
            assert "No SCIP indexes found" in data["error"]


class TestScipCompositeHandlersGoldenReposDirectory:
    """Tests verifying composite handlers pass golden repos directory to composite functions."""

    @pytest.mark.asyncio
    async def test_scip_impact_uses_golden_repos_directory(self, tmp_path: Path) -> None:
        """Verify scip_impact passes golden repos directory to analyze_impact()."""
        from code_indexer.server.mcp.handlers import scip_impact

        # Create golden repos structure with SCIP files
        golden_repos_dir = tmp_path / "golden-repos"
        repo1_scip = golden_repos_dir / "repo1" / ".code-indexer" / "scip"
        repo1_scip.mkdir(parents=True)
        (repo1_scip / "index.scip").write_text("mock")

        with patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_golden:
            mock_get_golden.return_value = str(golden_repos_dir)

            with patch(
                "code_indexer.scip.query.composites.analyze_impact"
            ) as mock_analyze:
                # Mock successful result
                from code_indexer.scip.query.composites import ImpactAnalysisResult

                mock_result = ImpactAnalysisResult(
                    target_symbol="test",
                    target_location=None,
                    depth_analyzed=2,
                    affected_symbols=[],
                    affected_files=[],
                    truncated=False,
                    total_affected=0,
                )
                mock_analyze.return_value = mock_result

                # Execute
                mock_user = MagicMock()
                result = await scip_impact({"symbol": "test", "depth": 2}, mock_user)

                # Verify analyze_impact was called with golden_repos_dir
                assert mock_analyze.called
                call_args = mock_analyze.call_args
                scip_dir_arg = call_args[0][1]  # Second positional arg

                # Should NOT be Path.cwd()
                assert str(scip_dir_arg) != str(Path.cwd() / ".code-indexer" / "scip")
                # Should be golden repos directory
                assert Path(scip_dir_arg) == golden_repos_dir
                # Should contain SCIP files
                assert list(Path(scip_dir_arg).glob("**/*.scip"))

    @pytest.mark.asyncio
    async def test_scip_callchain_uses_golden_repos_directory(
        self, tmp_path: Path
    ) -> None:
        """Verify scip_callchain passes golden repos directory to trace_call_chain()."""
        from code_indexer.server.mcp.handlers import scip_callchain

        # Create golden repos structure with SCIP files
        golden_repos_dir = tmp_path / "golden-repos"
        repo1_scip = golden_repos_dir / "repo1" / ".code-indexer" / "scip"
        repo1_scip.mkdir(parents=True)
        (repo1_scip / "index.scip").write_text("mock")

        with patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_golden:
            mock_get_golden.return_value = str(golden_repos_dir)

            with patch(
                "code_indexer.scip.query.composites.trace_call_chain"
            ) as mock_trace:
                # Mock successful result
                from code_indexer.scip.query.composites import CallChainResult

                mock_result = CallChainResult(
                    from_symbol="func1",
                    to_symbol="func2",
                    total_chains_found=0,
                    truncated=False,
                    max_depth_reached=False,
                    chains=[],
                )
                mock_trace.return_value = mock_result

                # Execute
                mock_user = MagicMock()
                result = await scip_callchain(
                    {"from_symbol": "func1", "to_symbol": "func2"}, mock_user
                )

                # Verify trace_call_chain was called with golden_repos_dir
                assert mock_trace.called
                call_args = mock_trace.call_args
                scip_dir_arg = call_args[0][2]  # Third positional arg

                # Should NOT be Path.cwd()
                assert str(scip_dir_arg) != str(Path.cwd() / ".code-indexer" / "scip")
                # Should be golden repos directory
                assert Path(scip_dir_arg) == golden_repos_dir
                # Should contain SCIP files
                assert list(Path(scip_dir_arg).glob("**/*.scip"))

    @pytest.mark.asyncio
    async def test_scip_context_uses_golden_repos_directory(
        self, tmp_path: Path
    ) -> None:
        """Verify scip_context passes golden repos directory to get_smart_context()."""
        from code_indexer.server.mcp.handlers import scip_context

        # Create golden repos structure with SCIP files
        golden_repos_dir = tmp_path / "golden-repos"
        repo1_scip = golden_repos_dir / "repo1" / ".code-indexer" / "scip"
        repo1_scip.mkdir(parents=True)
        (repo1_scip / "index.scip").write_text("mock")

        with patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_golden:
            mock_get_golden.return_value = str(golden_repos_dir)

            with patch(
                "code_indexer.scip.query.composites.get_smart_context"
            ) as mock_context:
                # Mock successful result
                from code_indexer.scip.query.composites import SmartContextResult

                mock_result = SmartContextResult(
                    target_symbol="test",
                    summary="Test summary",
                    total_files=0,
                    total_symbols=0,
                    avg_relevance=0.0,
                    files=[],
                )
                mock_context.return_value = mock_result

                # Execute
                mock_user = MagicMock()
                result = await scip_context({"symbol": "test"}, mock_user)

                # Verify get_smart_context was called with golden_repos_dir
                assert mock_context.called
                call_args = mock_context.call_args
                scip_dir_arg = call_args[0][1]  # Second positional arg

                # Should NOT be Path.cwd()
                assert str(scip_dir_arg) != str(Path.cwd() / ".code-indexer" / "scip")
                # Should be golden repos directory
                assert Path(scip_dir_arg) == golden_repos_dir
                # Should contain SCIP files
                assert list(Path(scip_dir_arg).glob("**/*.scip"))


class TestScipHandlerRegistration:
    """Tests for SCIP handler registration in HANDLER_REGISTRY."""

    def test_scip_handlers_registered_in_handler_registry(self) -> None:
        """Verify all 7 SCIP handlers are registered in HANDLER_REGISTRY.

        This test prevents regression of the bug where SCIP handlers were defined
        but not registered, causing "Handler not implemented" errors.
        """
        from code_indexer.server.mcp.handlers import HANDLER_REGISTRY

        expected_handlers = [
            "scip_definition",
            "scip_references",
            "scip_dependencies",
            "scip_dependents",
            "scip_impact",
            "scip_callchain",
            "scip_context",
        ]

        for handler_name in expected_handlers:
            assert handler_name in HANDLER_REGISTRY, f"Handler '{handler_name}' not registered in HANDLER_REGISTRY"
            assert callable(HANDLER_REGISTRY[handler_name]), f"Handler '{handler_name}' is not callable"
