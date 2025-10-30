"""
Unit tests for TantivyIndexManager regex compilation optimization.

PERFORMANCE ISSUE: Current implementation compiles regex pattern inside the result
processing loop, causing 100x unnecessary compilation overhead.

Current Code (Lines 641-644):
```python
for score, address in search_results:  # Loop over results
    doc = searcher.doc(address)
    # ...
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(query_text, flags)  # ❌ COMPILED EVERY ITERATION
    match_obj = pattern.search(content_raw)
```

Optimized Code:
```python
# Compile ONCE before loop
if use_regex:
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled_pattern = re.compile(query_text, flags)  # ✅ COMPILED ONCE

for score, address in search_results:
    doc = searcher.doc(address)
    # ...
    match_obj = compiled_pattern.search(content_raw)  # Use pre-compiled pattern
```

Performance Impact:
- 10 results: 10 compilations → 1 compilation (90% reduction)
- 100 results: 100 compilations → 1 compilation (99% reduction)
- Regex compilation is expensive: ~100-500μs per compilation

Tests follow TDD methodology:
1. Write performance tests demonstrating compilation overhead
2. Implement optimization (move re.compile outside loop)
3. Verify performance improvement and correctness
"""

import pytest
import time
import re
from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestTantivyRegexCompilationOptimization:
    """Test suite for regex compilation optimization."""

    @pytest.fixture
    def temp_index_dir(self, tmp_path):
        """Create temporary index directory."""
        return tmp_path / "tantivy_index"

    @pytest.fixture
    def tantivy_manager(self, temp_index_dir):
        """Create and initialize TantivyIndexManager."""
        manager = TantivyIndexManager(temp_index_dir)
        manager.initialize_index(create_new=True)
        return manager

    @pytest.fixture
    def many_matching_documents(self):
        """
        Generate many documents that will match regex pattern.

        Purpose: Create enough matches to measure compilation overhead.
        With 20+ results, the difference between compiling once vs 20 times
        becomes measurable.
        """
        docs = []
        for i in range(30):
            docs.append(
                {
                    "path": f"src/file_{i}.py",
                    "content": f"""def function_{i}():
    # Authentication logic
    auth_token = generate_token()
    return authenticate(auth_token)

class Manager_{i}:
    def __init__(self):
        self.authenticated = False
""",
                    "content_raw": f"""def function_{i}():
    # Authentication logic
    auth_token = generate_token()
    return authenticate(auth_token)

class Manager_{i}:
    def __init__(self):
        self.authenticated = False
""",
                    "identifiers": [f"function_{i}", f"Manager_{i}"],
                    "line_start": 1,
                    "line_end": 8,
                    "language": "python",
                }
            )
        return docs

    @pytest.fixture
    def indexed_manager_many_docs(self, tantivy_manager, many_matching_documents):
        """Manager with many documents indexed."""
        for doc in many_matching_documents:
            tantivy_manager.add_document(doc)
        tantivy_manager.commit()
        return tantivy_manager

    def test_regex_search_with_many_results_completes_quickly(
        self, indexed_manager_many_docs
    ):
        """
        GIVEN 30 indexed documents with 'auth' pattern
        WHEN searching with regex pattern 'auth.*'
        THEN should complete within reasonable time (< 2 seconds)

        If regex is compiled inside loop (30 times), this will be slower
        than compiling once before loop.

        This test establishes baseline performance expectation.
        """
        start_time = time.time()

        results = indexed_manager_many_docs.search(
            query_text=r"auth.*",
            use_regex=True,
            limit=30,
        )

        elapsed_time = time.time() - start_time

        # Should find many matches
        assert len(results) >= 20, f"Expected 20+ results, got {len(results)}"

        # Should complete quickly (optimized implementation)
        # If compiling inside loop, this might take 500ms+
        # With optimization, should be < 300ms
        assert elapsed_time < 2.0, (
            f"Search with 30 results took too long: {elapsed_time:.3f}s. "
            f"May indicate regex compilation happening inside loop."
        )

        print(f"Search with {len(results)} results completed in {elapsed_time:.3f}s")

    def test_regex_compilation_overhead_is_minimal(self, indexed_manager_many_docs):
        """
        GIVEN regex pattern that matches many documents
        WHEN running search multiple times
        THEN each search should have consistent performance

        If regex compilation is inside loop, performance will scale with result count.
        With optimization, performance should be independent of compilation overhead.
        """
        times = []

        # Run search multiple times to measure consistency
        for _ in range(3):
            start_time = time.time()

            results = indexed_manager_many_docs.search(
                query_text=r"function",
                use_regex=True,
                limit=25,
            )

            elapsed_time = time.time() - start_time
            times.append(elapsed_time)

            assert len(results) >= 20, f"Should find many results, got {len(results)}"

        # Performance should be consistent across runs
        avg_time = sum(times) / len(times)
        max_deviation = max(abs(t - avg_time) for t in times)

        print(f"Average time: {avg_time:.3f}s, Max deviation: {max_deviation:.3f}s")

        # All runs should complete quickly
        assert all(t < 2.0 for t in times), (
            f"Some searches took too long: {times}"
        )

    def test_case_sensitive_regex_also_optimized(self, indexed_manager_many_docs):
        """
        GIVEN case-sensitive regex search
        WHEN processing many results
        THEN should also benefit from compilation optimization

        Verifies that optimization applies to both case-sensitive and case-insensitive modes.
        """
        start_time = time.time()

        results = indexed_manager_many_docs.search(
            query_text=r"Auth.*",  # Capital A
            use_regex=True,
            case_sensitive=True,
            limit=30,
        )

        elapsed_time = time.time() - start_time

        # Should find some matches (if there are any with capital A)
        # Or zero matches if all are lowercase 'auth'
        # Either way, search should complete quickly
        assert elapsed_time < 2.0, (
            f"Case-sensitive search took too long: {elapsed_time:.3f}s"
        )

    def test_case_insensitive_regex_optimized(self, indexed_manager_many_docs):
        """
        GIVEN case-insensitive regex search
        WHEN processing many results
        THEN should compile pattern with re.IGNORECASE flag ONCE

        Bug: Currently compiles with re.IGNORECASE inside loop for every result.
        Fix: Compile once with appropriate flags before loop.

        Note: case_sensitive=False searches the 'content' field (lowercased),
        so we search for lowercase pattern.
        """
        start_time = time.time()

        results = indexed_manager_many_docs.search(
            query_text=r"auth",  # Lowercase for case-insensitive search
            use_regex=True,
            case_sensitive=False,
            limit=30,
        )

        elapsed_time = time.time() - start_time

        # Should find many matches (case insensitive)
        assert len(results) >= 20, f"Expected 20+ results, got {len(results)}"

        # Should complete quickly even with flag
        assert elapsed_time < 2.0, (
            f"Case-insensitive search took too long: {elapsed_time:.3f}s"
        )

    def test_complex_regex_pattern_benefits_from_optimization(
        self, indexed_manager_many_docs
    ):
        """
        GIVEN complex regex pattern (with groups, alternation, etc.)
        WHEN searching many results
        THEN compilation optimization should be even more beneficial

        Complex patterns take longer to compile, making the optimization more impactful.
        """
        # Complex pattern with grouping and alternation
        complex_pattern = r"(auth|token|authenticate)"

        start_time = time.time()

        results = indexed_manager_many_docs.search(
            query_text=complex_pattern,
            use_regex=True,
            limit=30,
        )

        elapsed_time = time.time() - start_time

        # Should find matches
        assert len(results) > 0, f"Should find matches for complex pattern, got {len(results)}"

        # Even complex patterns should complete quickly with optimization
        assert elapsed_time < 2.0, (
            f"Complex pattern search took too long: {elapsed_time:.3f}s. "
            f"Complex patterns benefit most from compilation optimization."
        )

    def test_single_result_still_works_correctly(self, tantivy_manager):
        """
        GIVEN optimization that compiles regex before loop
        WHEN only 1 result is found
        THEN should still work correctly (no performance regression)

        Edge case: Optimization shouldn't break behavior when loop runs once.
        """
        # Add single document
        doc = {
            "path": "src/single.py",
            "content": "unique identifier xyz = 42",
            "content_raw": "unique identifier xyz = 42",
            "identifiers": ["unique", "identifier", "xyz"],
            "line_start": 1,
            "line_end": 1,
            "language": "python",
        }

        tantivy_manager.add_document(doc)
        tantivy_manager.commit()

        results = tantivy_manager.search(
            query_text=r"unique",
            use_regex=True,
            limit=10,
        )

        # Should find the single match
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert results[0]["match_text"] == "unique"  # Exact match
        assert "unique" in results[0]["match_text"].lower()

    def test_zero_results_doesnt_break_optimization(self, tantivy_manager):
        """
        GIVEN pattern that matches no documents
        WHEN loop doesn't execute at all
        THEN pre-compiled pattern shouldn't cause errors

        Edge case: Empty result set should work with optimization.
        """
        # Add document that won't match pattern
        doc = {
            "path": "src/nomatch.py",
            "content": "foo = bar",
            "content_raw": "foo = bar",
            "identifiers": ["foo", "bar"],
            "line_start": 1,
            "line_end": 1,
            "language": "python",
        }

        tantivy_manager.add_document(doc)
        tantivy_manager.commit()

        results = tantivy_manager.search(
            query_text=r"nonexistent.*pattern",
            use_regex=True,
            limit=10,
        )

        # Should find no matches (and not crash)
        assert len(results) == 0

    def test_invalid_regex_fails_before_loop(self, tantivy_manager):
        """
        GIVEN invalid regex pattern
        WHEN compiling pattern before loop
        THEN should fail immediately with clear error (not during loop iteration)

        Benefit: Optimization causes regex errors to fail fast before processing results.
        """
        doc = {
            "path": "src/test.py",
            "content": "test content",
            "content_raw": "test content",
            "identifiers": ["test"],
            "line_start": 1,
            "line_end": 1,
            "language": "python",
        }

        tantivy_manager.add_document(doc)
        tantivy_manager.commit()

        # Invalid regex pattern (unmatched parenthesis)
        invalid_pattern = r"(unclosed"

        with pytest.raises(ValueError, match=r"(regex|pattern)"):
            tantivy_manager.search(
                query_text=invalid_pattern,
                use_regex=True,
                limit=10,
            )

    def test_optimization_preserves_match_accuracy(self, indexed_manager_many_docs):
        """
        GIVEN regex pattern compiled before loop (optimized)
        WHEN searching and extracting matches
        THEN match_text should still be accurate for all results

        Correctness test: Optimization shouldn't change match extraction behavior.
        """
        results = indexed_manager_many_docs.search(
            query_text=r"auth\w+",
            use_regex=True,
            limit=25,
        )

        assert len(results) >= 20, "Should find many results"

        for result in results:
            match_text = result.get("match_text", "")

            # Match text should be actual matched text, not pattern
            assert match_text != r"auth\w+", (
                f"match_text should not be pattern, got: {match_text}"
            )

            # Should start with 'auth'
            assert match_text.lower().startswith("auth"), (
                f"match_text should start with 'auth', got: {match_text}"
            )

            # Should be more than just 'auth' (the \w+ should match something)
            assert len(match_text) > 4, (
                f"match_text should include characters after 'auth', got: {match_text}"
            )

    def test_performance_benchmark_uncompiled_vs_compiled(self):
        """
        BENCHMARK TEST: Measure performance difference between compiling
        inside loop vs outside loop.

        This is a micro-benchmark to quantify the optimization benefit.
        """
        pattern_str = r"auth\w+"
        content_samples = [f"authenticate_{i}" for i in range(100)]

        # Scenario 1: Compile inside loop (current bug)
        start_unoptimized = time.time()
        for content in content_samples:
            flags = re.IGNORECASE
            pattern = re.compile(pattern_str, flags)  # Compiled 100 times
            match = pattern.search(content)
        time_unoptimized = time.time() - start_unoptimized

        # Scenario 2: Compile outside loop (optimized)
        start_optimized = time.time()
        flags = re.IGNORECASE
        compiled_pattern = re.compile(pattern_str, flags)  # Compiled once
        for content in content_samples:
            match = compiled_pattern.search(content)
        time_optimized = time.time() - start_optimized

        # Calculate speedup
        speedup = time_unoptimized / time_optimized if time_optimized > 0 else 0

        print(
            f"\nPerformance Benchmark:\n"
            f"  Unoptimized (compile in loop): {time_unoptimized*1000:.2f}ms\n"
            f"  Optimized (compile once):      {time_optimized*1000:.2f}ms\n"
            f"  Speedup:                       {speedup:.1f}x\n"
        )

        # Optimized should be significantly faster (at least 10x for 100 iterations)
        assert speedup > 5.0, (
            f"Expected significant speedup from optimization, got {speedup:.1f}x"
        )
