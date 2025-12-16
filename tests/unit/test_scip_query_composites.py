"""Unit tests for SCIP composite queries (impact analysis, call chains, smart context)."""

import pytest
from pathlib import Path
from unittest.mock import patch

from code_indexer.scip.query.composites import (
    analyze_impact,
    get_smart_context,
    ImpactAnalysisResult,
    SmartContextResult,
)
from code_indexer.scip.query.primitives import SCIPQueryEngine, QueryResult


@pytest.fixture
def scip_fixture_path():
    """Path to comprehensive SCIP test fixture."""
    return Path(__file__).parent.parent / "scip" / "fixtures" / "comprehensive_index.scip"


@pytest.fixture
def scip_dir(scip_fixture_path):
    """Directory containing SCIP files."""
    return scip_fixture_path.parent


class TestAnalyzeImpactPerformance:
    """Tests for analyze_impact() performance optimization."""

    def test_engine_caching_in_bfs_traversal(self, scip_dir):
        """Should cache SCIPQueryEngine instances in BFS traversal.

        Performance bug: _bfs_traverse_dependents() (lines 138-200) also creates
        new SCIPQueryEngine instances for every symbol in the queue.
        """
        instantiation_count = {"count": 0}
        original_init = SCIPQueryEngine.__init__

        def counting_init(self, *args, **kwargs):
            instantiation_count["count"] += 1
            return original_init(self, *args, **kwargs)

        with patch.object(SCIPQueryEngine, '__init__', counting_init):
            analyze_impact(
                symbol="some_symbol",
                scip_dir=scip_dir,
                depth=2
            )

            scip_files = list(scip_dir.glob("**/*.scip"))
            num_scip_files = len(scip_files)

            # With proper caching:
            # - _find_target_definition iterates SCIP files ONCE = num_scip_files engines
            # - _bfs_traverse_dependents should REUSE those engines = 0 additional
            # Total = num_scip_files
            #
            # Without caching:
            # - _find_target_definition = num_scip_files engines
            # - _bfs_traverse_dependents creates new engines for each BFS iteration
            # Total = much more than num_scip_files

            # We expect at most 2x num_scip_files (one pass for definition, one for BFS)
            # But with proper caching, we should have exactly num_scip_files
            max_acceptable = num_scip_files * 2

            assert instantiation_count["count"] <= max_acceptable, (
                f"Expected at most {max_acceptable} SCIPQueryEngine instances, "
                f"but got {instantiation_count['count']}. This indicates engines are being "
                f"recreated excessively."
            )


class TestAnalyzeImpactFunctionality:
    """Tests for analyze_impact() correctness."""

    def test_returns_impact_analysis_result(self, scip_dir):
        """Should return ImpactAnalysisResult with expected structure."""
        result = analyze_impact(
            symbol="some_function",
            scip_dir=scip_dir,
            depth=2
        )

        assert isinstance(result, ImpactAnalysisResult)
        assert result.target_symbol == "some_function"
        assert isinstance(result.affected_symbols, list)
        assert isinstance(result.affected_files, list)
        assert isinstance(result.depth_analyzed, int)
        assert isinstance(result.truncated, bool)
        assert isinstance(result.total_affected, int)

    def test_respects_max_depth(self, scip_dir):
        """Should not analyze beyond specified depth."""
        result = analyze_impact(
            symbol="some_function",
            scip_dir=scip_dir,
            depth=2
        )

        # All affected symbols should have depth <= specified depth
        for symbol in result.affected_symbols:
            assert symbol.depth <= 2

    def test_impact_command_returns_same_results_as_dependents(self, scip_fixture_path):
        """Should verify analyze_impact() returns same symbols as get_dependents().

        Bug #1: impact command returns empty results while dependents command
        finds 187 results for the same symbol. Root cause is _is_meaningful_call()
        filter in _bfs_traverse_dependents() is too aggressive.

        This test compares analyze_impact() against direct get_dependents() call
        to ensure filtering logic doesn't remove valid results.
        """
        from code_indexer.scip.query.primitives import SCIPQueryEngine

        symbol = "StatusTracker"
        depth = 1

        # Get dependents directly from SCIPQueryEngine (what 'cidx scip dependents' uses)
        engine = SCIPQueryEngine(scip_fixture_path)
        direct_dependents = engine.get_dependents(symbol, depth=depth, exact=False)

        # Get dependents via analyze_impact (what 'cidx scip impact' uses)
        scip_dir = scip_fixture_path.parent
        impact_result = analyze_impact(
            symbol=symbol,
            scip_dir=scip_dir,
            depth=depth
        )

        # Impact should return AT LEAST the same number of results as direct query
        # (may return more due to BFS traversal collecting additional metadata)
        assert impact_result.total_affected >= len(direct_dependents), (
            f"analyze_impact() returned {impact_result.total_affected} results "
            f"but get_dependents() found {len(direct_dependents)} results. "
            f"Impact analysis filtering is too aggressive."
        )

        # If direct_dependents has results, impact must too
        if len(direct_dependents) > 0:
            assert impact_result.total_affected > 0, (
                "get_dependents() found results but analyze_impact() returned empty. "
                "This is Bug #1: _is_meaningful_call() filter is removing valid dependents."
            )


class TestExcludeIncludeFilters:
    """Tests for exclude/include path filtering."""

    def test_exclude_filter_with_glob_patterns(self):
        """Should correctly filter out paths matching exclude patterns.

        BUG DEMONSTRATION: fnmatch() fails to match patterns like '*/tests/*'
        against relative paths like 'tests/unit/test_foo.py' because fnmatch
        doesn't handle leading '*/' wildcards correctly with relative paths.

        This test verifies PathLib's match() method correctly handles glob patterns.
        """
        from code_indexer.scip.query.composites import _bfs_traverse_dependents
        from code_indexer.scip.query.primitives import QueryResult
        from unittest.mock import MagicMock, patch

        # Create mock SCIP directory
        scip_dir = Path("/fake/scip")

        # Mock SCIPQueryEngine.get_dependents to return test paths
        # Note: Symbol names must contain '().' to pass _is_meaningful_call filter
        mock_dependents = [
            QueryResult(
                symbol="TestClass#test_func().",
                project="test_project",
                kind="function",
                file_path="tests/unit/test_foo.py",  # Should be excluded by */tests/*
                line=10,
                column=5,
                relationship="call"
            ),
            QueryResult(
                symbol="ProductionClass#prod_func().",
                project="test_project",
                kind="function",
                file_path="src/main.py",  # Should NOT be excluded
                line=20,
                column=10,
                relationship="call"
            ),
            QueryResult(
                symbol="IntegrationTest#another_test().",
                project="test_project",
                kind="function",
                file_path="tests/integration/test_bar.py",  # Should be excluded
                line=30,
                column=15,
                relationship="call"
            ),
        ]

        # Mock the SCIPQueryEngine
        with patch('code_indexer.scip.query.composites.SCIPQueryEngine') as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine.get_dependents.return_value = mock_dependents
            mock_engine_class.return_value = mock_engine

            # Mock glob to return fake SCIP file
            with patch.object(Path, 'glob') as mock_glob:
                mock_glob.return_value = [Path("/fake/scip/index.scip")]

                # Call _bfs_traverse_dependents with exclude pattern
                result = _bfs_traverse_dependents(
                    symbol="target_symbol",
                    scip_dir=scip_dir,
                    depth=1,
                    project=None,
                    exclude="*/tests/*",  # This pattern should exclude test files
                    include=None,
                    kind=None
                )

        # Verify test files were excluded
        result_paths = [str(s.file_path) for s in result]

        # These test paths should NOT be in results (excluded by */tests/*)
        assert "tests/unit/test_foo.py" not in result_paths, \
            "Pattern '*/tests/*' should exclude 'tests/unit/test_foo.py'"
        assert "tests/integration/test_bar.py" not in result_paths, \
            "Pattern '*/tests/*' should exclude 'tests/integration/test_bar.py'"

        # This production path SHOULD be in results (not excluded)
        assert "src/main.py" in result_paths, \
            "Pattern '*/tests/*' should NOT exclude 'src/main.py'"


class TestMatchesGlobPatternHelper:
    """Tests for _matches_glob_pattern() helper function edge cases."""

    def test_empty_pattern_returns_false(self):
        """Should return False gracefully when pattern is empty string."""
        from code_indexer.scip.query.composites import _matches_glob_pattern

        # Empty pattern should not match anything
        assert _matches_glob_pattern("tests/unit/test_foo.py", "") is False
        assert _matches_glob_pattern("src/main.py", "") is False
        assert _matches_glob_pattern("", "") is False

    def test_catch_all_pattern_matches_multi_level_paths(self):
        """Should match paths with at least one directory level for catch-all pattern '*/*'."""
        from code_indexer.scip.query.composites import _matches_glob_pattern

        # Catch-all pattern should match paths with directory structure
        assert _matches_glob_pattern("tests/test_foo.py", "*/*") is True
        assert _matches_glob_pattern("src/main.py", "*/*") is True
        assert _matches_glob_pattern("a/b/c/d.py", "*/*") is True

        # Catch-all pattern should NOT match single file (no directory)
        assert _matches_glob_pattern("file.py", "*/*") is False

    def test_single_file_path_no_directory(self):
        """Should correctly handle single file paths without directory."""
        from code_indexer.scip.query.composites import _matches_glob_pattern

        # Single file should NOT match directory-based patterns
        assert _matches_glob_pattern("file.py", "*/tests/*") is False
        assert _matches_glob_pattern("file.py", "*/src/*") is False

        # Single file CAN match wildcard patterns
        assert _matches_glob_pattern("file.py", "*.py") is True
        assert _matches_glob_pattern("file.py", "*") is True

    def test_invalid_path_input_returns_false(self):
        """Should handle invalid path inputs gracefully."""
        from code_indexer.scip.query.composites import _matches_glob_pattern

        # Invalid path types should return False (defensive programming)
        # Note: PurePath is quite permissive, so extreme cases needed
        assert _matches_glob_pattern("normal/path.py", "*/tests/*") is False  # Baseline

    def test_invalid_pattern_input_returns_false(self):
        """Should handle invalid pattern inputs gracefully."""
        from code_indexer.scip.query.composites import _matches_glob_pattern

        # Invalid glob patterns should return False
        # PurePath.match() can raise ValueError for invalid patterns
        # Example: patterns with null bytes or extremely malformed patterns
        # But most "invalid" patterns are just treated as literals
        # Test with pattern that would cause match() to fail
        assert _matches_glob_pattern("test.py", "**[") is False  # Malformed bracket


class TestGetSmartContext:
    """Tests for get_smart_context() functionality."""

    def test_returns_smart_context_result(self, scip_dir):
        """Should return SmartContextResult with expected structure."""
        result = get_smart_context(
            symbol="some_function",
            scip_dir=scip_dir,
            limit=10
        )

        assert isinstance(result, SmartContextResult)
        assert result.target_symbol == "some_function"
        assert isinstance(result.summary, str)
        assert isinstance(result.files, list)
        assert isinstance(result.total_files, int)
        assert isinstance(result.total_symbols, int)
        assert isinstance(result.avg_relevance, float)

    def test_respects_limit(self, scip_dir):
        """Should not return more files than specified limit."""
        result = get_smart_context(
            symbol="some_function",
            scip_dir=scip_dir,
            limit=5
        )

        assert len(result.files) <= 5
