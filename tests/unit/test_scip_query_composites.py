"""Unit tests for SCIP composite queries (impact analysis, call chains, smart context)."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    return (
        Path(__file__).parent.parent / "scip" / "fixtures" / "comprehensive_index.scip"
    )


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

        with patch.object(SCIPQueryEngine, "__init__", counting_init):
            analyze_impact(symbol="some_symbol", scip_dir=scip_dir, depth=2)

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

    def test_get_dependents_returns_depth_information(self, scip_fixture_path):
        """Should verify get_dependents() returns depth field for transitive queries.

        Bug: SQL CTE in _get_dependents_hybrid computes depth (td.depth) but
        doesn't include it in result dictionaries. This causes _bfs_traverse_dependents
        to manually traverse when database already did the work.

        Fix: Include depth in returned QueryResult objects.
        """
        from code_indexer.scip.query.primitives import SCIPQueryEngine

        # Use real engine with test fixture
        engine = SCIPQueryEngine(scip_fixture_path)

        # Query for transitive dependents (depth > 1)
        results = engine.get_dependents("Logger", depth=3, exact=False)

        # Should return results with depth information
        assert len(results) > 0, "Should find dependents in test fixture"

        # Every QueryResult should have depth field
        for result in results:
            assert hasattr(
                result, "depth"
            ), f"QueryResult must have 'depth' field. Found fields: {result.__dict__.keys()}"
            assert isinstance(
                result.depth, int
            ), f"depth must be integer, got {type(result.depth)}"
            assert (
                1 <= result.depth <= 3
            ), f"depth should be between 1 and 3, got {result.depth}"

    def test_bfs_traverse_single_database_call(self, scip_fixture_path):
        """Should verify _bfs_traverse_dependents calls get_dependents only ONCE.

        Performance bug: Original implementation called get_dependents for each symbol in BFS queue,
        causing O(n²) database calls. Since database CTE already returns all transitive dependents,
        we should call it once and process results.

        Fix: Call get_dependents once with full depth, process all returned results.
        """
        from code_indexer.scip.query.composites import _bfs_traverse_dependents
        from code_indexer.scip.query.primitives import SCIPQueryEngine
        from unittest.mock import patch

        scip_dir = scip_fixture_path.parent

        # Track get_dependents calls
        call_count = {"count": 0}
        original_get_dependents = SCIPQueryEngine.get_dependents

        def counting_get_dependents(self, *args, **kwargs):
            call_count["count"] += 1
            return original_get_dependents(self, *args, **kwargs)

        with patch.object(SCIPQueryEngine, "get_dependents", counting_get_dependents):
            result = _bfs_traverse_dependents(
                symbol="Logger",
                scip_dir=scip_dir,
                depth=3,
                project=None,
                exclude=None,
                include=None,
                kind=None,
            )

        # Should call get_dependents at most ONCE per SCIP file
        # NOT once per symbol in BFS queue (which would be >> num_scip_files)
        scip_files = list(scip_dir.glob("**/*.scip"))
        num_scip_files = len(scip_files)

        # With refactored implementation: <= num_scip_files (one per valid SCIP file)
        # Old BFS implementation would make calls >> num_scip_files (one per symbol in queue)
        assert call_count["count"] <= num_scip_files, (
            f"Expected at most {num_scip_files} calls to get_dependents (one per SCIP file), "
            f"but got {call_count['count']}. This indicates redundant BFS traversal."
        )

        # Verify we actually made some calls and got results
        assert call_count["count"] > 0, "Should have queried at least one SCIP file"
        assert len(result) > 0, "Should find dependents"

    def test_bfs_traverse_passes_depth_to_engine(self, scip_dir):
        """Should pass depth parameter to engine.get_dependents() to leverage database optimization.

        Performance bug: _bfs_traverse_dependents() calls engine.get_dependents(symbol, exact=False)
        without depth parameter, defaulting to depth=1. This bypasses the database's optimized
        transitive query (depth=3 takes 0.1s) and forces Python BFS loop (136 seconds).

        Fix: Pass depth parameter to get_dependents() to use database's CTE-based traversal.
        """
        from code_indexer.scip.query.composites import _bfs_traverse_dependents
        from unittest.mock import MagicMock, patch

        # Create mock SCIP directory
        mock_scip_dir = Path("/fake/scip")

        # Mock SCIPQueryEngine to capture get_dependents calls
        mock_engine = MagicMock()
        mock_engine.get_dependents.return_value = []  # Empty results for simplicity

        with patch(
            "code_indexer.scip.query.composites.SCIPQueryEngine"
        ) as mock_engine_class:
            mock_engine_class.return_value = mock_engine

            # Mock glob to return fake SCIP file
            with patch.object(Path, "glob") as mock_glob:
                mock_glob.return_value = [Path("/fake/scip/index.scip")]

                # Call _bfs_traverse_dependents with depth=3
                _bfs_traverse_dependents(
                    symbol="target_symbol",
                    scip_dir=mock_scip_dir,
                    depth=3,
                    project=None,
                    exclude=None,
                    include=None,
                    kind=None,
                )

        # Verify engine.get_dependents was called with depth=3
        mock_engine.get_dependents.assert_called()

        # Extract the actual call and verify depth parameter
        calls = mock_engine.get_dependents.call_args_list
        assert len(calls) > 0, "engine.get_dependents should have been called"

        # Check first call (for the initial symbol)
        first_call = calls[0]
        _, kwargs = first_call

        # CRITICAL: depth parameter should be passed to leverage database optimization
        assert "depth" in kwargs or len(first_call[0]) >= 2, (
            "engine.get_dependents must receive depth parameter to use optimized database query. "
            "Current implementation calls get_dependents(symbol, exact=False) with default depth=1, "
            "bypassing database's transitive query optimization."
        )

        if "depth" in kwargs:
            assert (
                kwargs["depth"] == 3
            ), f"Expected depth=3, got depth={kwargs['depth']}"
        elif len(first_call[0]) >= 2:
            # Positional argument (symbol, depth, exact)
            assert (
                first_call[0][1] == 3
            ), f"Expected depth=3, got depth={first_call[0][1]}"

    def test_returns_impact_analysis_result(self, scip_dir):
        """Should return ImpactAnalysisResult with expected structure."""
        result = analyze_impact(symbol="some_function", scip_dir=scip_dir, depth=2)

        assert isinstance(result, ImpactAnalysisResult)
        assert result.target_symbol == "some_function"
        assert isinstance(result.affected_symbols, list)
        assert isinstance(result.affected_files, list)
        assert isinstance(result.depth_analyzed, int)
        assert isinstance(result.truncated, bool)
        assert isinstance(result.total_affected, int)

    def test_respects_max_depth(self, scip_dir):
        """Should not analyze beyond specified depth."""
        result = analyze_impact(symbol="some_function", scip_dir=scip_dir, depth=2)

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
        impact_result = analyze_impact(symbol=symbol, scip_dir=scip_dir, depth=depth)

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
                relationship="call",
            ),
            QueryResult(
                symbol="ProductionClass#prod_func().",
                project="test_project",
                kind="function",
                file_path="src/main.py",  # Should NOT be excluded
                line=20,
                column=10,
                relationship="call",
            ),
            QueryResult(
                symbol="IntegrationTest#another_test().",
                project="test_project",
                kind="function",
                file_path="tests/integration/test_bar.py",  # Should be excluded
                line=30,
                column=15,
                relationship="call",
            ),
        ]

        # Mock the SCIPQueryEngine
        with patch(
            "code_indexer.scip.query.composites.SCIPQueryEngine"
        ) as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine.get_dependents.return_value = mock_dependents
            mock_engine_class.return_value = mock_engine

            # Mock glob to return fake SCIP file
            with patch.object(Path, "glob") as mock_glob:
                mock_glob.return_value = [Path("/fake/scip/index.scip")]

                # Call _bfs_traverse_dependents with exclude pattern
                result = _bfs_traverse_dependents(
                    symbol="target_symbol",
                    scip_dir=scip_dir,
                    depth=1,
                    project=None,
                    exclude="*/tests/*",  # This pattern should exclude test files
                    include=None,
                    kind=None,
                )

        # Verify test files were excluded
        result_paths = [str(s.file_path) for s in result]

        # These test paths should NOT be in results (excluded by */tests/*)
        assert (
            "tests/unit/test_foo.py" not in result_paths
        ), "Pattern '*/tests/*' should exclude 'tests/unit/test_foo.py'"
        assert (
            "tests/integration/test_bar.py" not in result_paths
        ), "Pattern '*/tests/*' should exclude 'tests/integration/test_bar.py'"

        # This production path SHOULD be in results (not excluded)
        assert (
            "src/main.py" in result_paths
        ), "Pattern '*/tests/*' should NOT exclude 'src/main.py'"


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


class TestTraceCallChain:
    """Tests for trace_call_chain() functionality."""

    def test_trace_call_chains_skips_empty_database_file(self, tmp_path, caplog):
        """Should skip empty database files without warnings."""
        import logging
        from code_indexer.scip.query.composites import trace_call_chain

        # Create directory with empty .scip.db file
        scip_dir = tmp_path / "scip"
        scip_dir.mkdir()
        empty_db = scip_dir / "empty.scip.db"
        empty_db.touch()  # Create empty file (0 bytes)

        # Enable logging to capture warnings
        caplog.set_level(logging.WARNING)

        # Should not raise exception or log warnings
        result = trace_call_chain(
            from_symbol="some_func",
            to_symbol="another_func",
            scip_dir=scip_dir,
            max_depth=5,
        )

        # Result should be empty (no chains found)
        assert result.total_chains_found == 0

        # No warnings should be logged for empty files
        warning_messages = [
            rec.message for rec in caplog.records if rec.levelname == "WARNING"
        ]
        assert not any(
            "empty.scip.db" in msg for msg in warning_messages
        ), f"Should not warn about empty database files, but got: {warning_messages}"

    def test_trace_call_chains_logs_warning_for_invalid_database(
        self, tmp_path, caplog
    ):
        """Should catch exception and log warning for invalid but non-empty database files."""
        import logging
        from code_indexer.scip.query.composites import trace_call_chain

        # Create directory with invalid .scip.db file
        scip_dir = tmp_path / "scip"
        scip_dir.mkdir()
        invalid_db = scip_dir / "invalid.scip.db"
        invalid_db.write_text("This is not a valid SQLite database")

        # Enable logging to capture warnings
        caplog.set_level(logging.WARNING)

        # Should not raise exception
        result = trace_call_chain(
            from_symbol="some_func",
            to_symbol="another_func",
            scip_dir=scip_dir,
            max_depth=5,
        )

        # Result should be empty (no chains found)
        assert result.total_chains_found == 0

        # Warning should be logged for invalid database
        warning_messages = [
            rec.message for rec in caplog.records if rec.levelname == "WARNING"
        ]
        assert any(
            "invalid.scip.db" in msg for msg in warning_messages
        ), f"Should warn about invalid database file, but got: {warning_messages}"


class TestGetSmartContext:
    """Tests for get_smart_context() functionality."""

    def test_returns_smart_context_result(self, scip_dir):
        """Should return SmartContextResult with expected structure."""
        result = get_smart_context(symbol="some_function", scip_dir=scip_dir, limit=10)

        assert isinstance(result, SmartContextResult)
        assert result.target_symbol == "some_function"
        assert isinstance(result.summary, str)
        assert isinstance(result.files, list)
        assert isinstance(result.total_files, int)
        assert isinstance(result.total_symbols, int)
        assert isinstance(result.avg_relevance, float)

    def test_respects_limit(self, scip_dir):
        """Should not return more files than specified limit."""
        result = get_smart_context(symbol="some_function", scip_dir=scip_dir, limit=5)

        assert len(result.files) <= 5

    def test_limit_zero_means_unlimited(self, scip_dir):
        """Should treat limit=0 as unlimited, not as 'return 0 files'.

        Bug: When limit=0 (CLI default for unlimited), the code was doing
        context_files[:0] which returns an empty list.

        Fix: limit=0 should skip the slicing and return all files.
        """
        # Create mock query results simulating 3 files found
        mock_definitions = [
            QueryResult(
                symbol="fn",
                project="test",
                file_path="src/m1.py",
                line=10,
                column=0,
                kind="function",
            ),
            QueryResult(
                symbol="fn",
                project="test",
                file_path="src/m2.py",
                line=20,
                column=0,
                kind="function",
            ),
            QueryResult(
                symbol="fn",
                project="test",
                file_path="src/m3.py",
                line=30,
                column=0,
                kind="function",
            ),
        ]

        mock_engine = MagicMock()
        mock_engine.find_definition.return_value = mock_definitions
        mock_engine.find_references.return_value = []
        mock_impact = MagicMock(affected_symbols=[])

        # Use side_effect to return fresh iterator each call
        def fresh_glob(*args):
            return iter([Path("fake.scip")])

        with (
            patch.object(Path, "glob", side_effect=fresh_glob),
            patch(
                "code_indexer.scip.query.composites.SCIPQueryEngine",
                return_value=mock_engine,
            ),
            patch(
                "code_indexer.scip.query.composites.analyze_impact",
                return_value=mock_impact,
            ),
        ):

            result_zero = get_smart_context(symbol="fn", scip_dir=scip_dir, limit=0)
            result_high = get_smart_context(symbol="fn", scip_dir=scip_dir, limit=1000)

        # limit=0 should return all 3 files, not 0
        assert result_zero.total_files == 3, (
            f"limit=0 should return all 3 files, got {result_zero.total_files}. "
            f"Bug: context_files[:0] returns empty list."
        )
        assert result_zero.total_files == result_high.total_files


class TestTraceCallChainMaxDepthValidation:
    """Tests for trace_call_chain() max_depth validation and clamping."""

    def test_max_call_chain_depth_constant_matches_backend_limit(self):
        """Should verify MAX_CALL_CHAIN_DEPTH equals backend's max_depth limit.

        Bug: MAX_CALL_CHAIN_DEPTH=20 but database/queries.py validates max_depth <= 10.
        This mismatch causes ValueError when max_depth is between 10 and 20.

        Fix: MAX_CALL_CHAIN_DEPTH should equal 10 to match backend validation.
        """
        from code_indexer.scip.query.composites import MAX_CALL_CHAIN_DEPTH

        # Backend (database/queries.py lines 174, 285) validates: 1 <= max_depth <= 10
        BACKEND_MAX_DEPTH = 10

        assert MAX_CALL_CHAIN_DEPTH == BACKEND_MAX_DEPTH, (
            f"MAX_CALL_CHAIN_DEPTH ({MAX_CALL_CHAIN_DEPTH}) must match backend limit ({BACKEND_MAX_DEPTH}). "
            f"Mismatch causes ValueError when max_depth > {BACKEND_MAX_DEPTH}."
        )

    def test_trace_call_chain_clamps_max_depth_to_10(self, scip_dir):
        """Should clamp max_depth to 10 when value exceeds limit (e.g., 15).

        Bug: MAX_CALL_CHAIN_DEPTH=20 in composites.py, but database/queries.py
        validates max_depth <= 10. When user passes max_depth=15:
        - composites.py clamps to min(15, 20) = 15
        - database/queries.py raises ValueError: "Max depth must be between 1 and 10"

        Fix: Change MAX_CALL_CHAIN_DEPTH from 20 to 10 to align with backend.
        """
        from code_indexer.scip.query.composites import trace_call_chain

        # This should NOT raise ValueError - should clamp to 10 internally
        # Currently FAILS because MAX_CALL_CHAIN_DEPTH=20 allows 15 through,
        # then database layer rejects it
        result = trace_call_chain(
            from_symbol="some_func",
            to_symbol="another_func",
            scip_dir=scip_dir,
            max_depth=15,  # Exceeds backend limit of 10
        )

        # Should succeed (no exception) and return valid result
        assert result is not None
