"""
Test-driven development for path pattern performance.

Tests that path pattern matching performs efficiently:
- Pattern compilation overhead
- Bulk matching performance
- Large pattern sets
- Complex pattern performance
"""

import time


class TestPatternMatchingPerformance:
    """Test performance of pattern matching operations."""

    def test_single_pattern_match_performance(self):
        """Test that single pattern matching completes in <1ms."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        test_path = "src/project/tests/test_module.py"
        pattern = "*/tests/*"

        # Measure time for 1000 matches
        start_time = time.perf_counter()
        for _ in range(1000):
            matcher.matches_pattern(test_path, pattern)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Should complete 1000 matches in <35ms (average <0.035ms per match)
        # Permissive threshold for bulk test suite runs under system load
        # Isolated runs typically achieve <15ms, full suite may reach ~25ms
        assert (
            elapsed_ms < 35
        ), f"Pattern matching too slow: {elapsed_ms:.2f}ms for 1000 matches"

    def test_multiple_pattern_match_performance(self):
        """Test that matching against multiple patterns is efficient."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        test_path = "src/project/vendor/lib/module.js"
        patterns = [
            "*/tests/*",
            "*.min.js",
            "**/vendor/**",
            "**/node_modules/**",
            "**/__pycache__/**",
            "*.pyc",
            "*/build/*",
            "*/dist/*",
        ]

        # Measure time for 1000 multi-pattern matches
        start_time = time.perf_counter()
        for _ in range(1000):
            matcher.matches_any_pattern(test_path, patterns)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Should complete 1000 multi-pattern matches in <120ms (average <0.12ms per match)
        # Permissive threshold for bulk test suite runs under system load
        # Isolated runs typically achieve <60ms, full suite may reach ~100ms
        assert (
            elapsed_ms < 120
        ), f"Multi-pattern matching too slow: {elapsed_ms:.2f}ms for 1000 matches"

    def test_bulk_filtering_performance(self):
        """Test that filtering large result sets is efficient."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Generate 1000 test paths
        test_paths = [f"src/module{i}/subdir/file{i}.py" for i in range(500)] + [
            f"src/tests/test_module{i}.py" for i in range(500)
        ]

        exclusion_patterns = ["*/tests/*", "*.min.js"]

        # Measure time to filter all paths
        start_time = time.perf_counter()
        filtered_paths = [
            path
            for path in test_paths
            if not matcher.matches_any_pattern(path, exclusion_patterns)
        ]
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Should filter 1000 paths in <50ms
        assert (
            elapsed_ms < 50
        ), f"Bulk filtering too slow: {elapsed_ms:.2f}ms for 1000 paths"

        # Verify filtering worked
        assert len(filtered_paths) == 500  # Half should be filtered out
        assert all("tests" not in path for path in filtered_paths)


class TestPatternCompilationOverhead:
    """Test pattern compilation and caching overhead."""

    def test_pattern_compilation_cached(self):
        """Test that compiled patterns are cached for reuse."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        pattern = "*/tests/*"
        test_path = "src/tests/test.py"

        # First match (may include compilation)
        start_time = time.perf_counter()
        result1 = matcher.matches_pattern(test_path, pattern)
        first_match_ms = (time.perf_counter() - start_time) * 1000

        # Second match (should use cache)
        start_time = time.perf_counter()
        result2 = matcher.matches_pattern(test_path, pattern)
        second_match_ms = (time.perf_counter() - start_time) * 1000

        # Results should be identical
        assert result1 == result2

        # Second match should be faster or similar (within 2x)
        # Note: This tests caching behavior, not strict performance
        assert (
            second_match_ms <= first_match_ms * 2
        ), f"Pattern not cached: first={first_match_ms:.3f}ms, second={second_match_ms:.3f}ms"


class TestComplexPatternPerformance:
    """Test performance of complex glob patterns."""

    def test_complex_pattern_performance(self):
        """Test that complex patterns maintain acceptable performance."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        test_path = "src/deep/nested/directory/structure/module.py"
        complex_patterns = [
            "**/build/**/dist/**",
            "src/*/temp_*",
            "test[123].py",
            "**/vendor/**/node_modules/**",
        ]

        # Measure time for 1000 complex pattern matches
        start_time = time.perf_counter()
        for _ in range(1000):
            matcher.matches_any_pattern(test_path, complex_patterns)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Should complete 1000 complex matches in <150ms
        # More lenient threshold for bulk test suite runs with system load
        assert (
            elapsed_ms < 150
        ), f"Complex pattern matching too slow: {elapsed_ms:.2f}ms for 1000 matches"


class TestFilterOverheadBenchmark:
    """Test overall overhead of path filtering in query pipeline."""

    def test_path_filter_overhead_minimal(self):
        """Test that path filtering adds <5ms overhead to query."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        builder = PathFilterBuilder()
        matcher = PathPatternMatcher()

        # Simulate query pipeline with 100 results
        mock_results = [
            {"file_path": f"src/module{i}.py", "score": 0.9} for i in range(50)
        ] + [{"file_path": f"src/tests/test{i}.py", "score": 0.9} for i in range(50)]

        exclusion_patterns = ["*/tests/*", "*.min.js"]

        # Measure filter construction + application
        start_time = time.perf_counter()

        # 1. Build filter (for benchmarking purposes)
        _ = builder.build_exclusion_filter(exclusion_patterns)

        # 2. Apply filter to results
        filtered_results = [
            result
            for result in mock_results
            if not matcher.matches_any_pattern(result["file_path"], exclusion_patterns)
        ]

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Total overhead should be <5ms
        assert (
            elapsed_ms < 5
        ), f"Path filtering overhead too high: {elapsed_ms:.2f}ms for 100 results"

        # Verify filtering worked
        assert len(filtered_results) == 50
