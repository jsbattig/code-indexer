"""
Unit tests for TantivyIndexManager DFA-based regex safety.

SECURITY ASSURANCE: Tantivy uses deterministic finite automaton (DFA) for regex
matching, which is immune to Regular Expression Denial of Service (ReDoS) attacks.

DFA Architecture Benefits:
- Linear time complexity O(n) for all patterns
- No backtracking mechanism (DFA reads input sequentially)
- Patterns like (a+)+, (a|a)*b that cause catastrophic backtracking in
  PCRE/Python/JavaScript are safely handled in milliseconds

ReDoS-Vulnerable Pattern Examples (Safe in Tantivy):
- Pattern: (a|a)*b with input: "aaaaaaaaaaaaaaaaaaaac"
  Traditional engines: O(2^n) time | Tantivy DFA: O(n) time

- Pattern: (a+)+ with input: "aaaaaaaaaaaaaaaaaaaaX"
  Traditional engines: Exponential backtracking | Tantivy DFA: Linear time

Implementation: tantivy-fst crate using Rust's regex library (Pike NFA/DFA hybrid)

Test Approach:
- Verify patterns complete quickly (<100ms) instead of expecting timeout
- Test both "dangerous" patterns (safe in DFA) and safe patterns
- Ensure search functionality works correctly with complex regex patterns
- Confirm DFA provides built-in ReDoS immunity
"""

import pytest
import time
from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestTantivyRegexDFASafety:
    """Test suite verifying Tantivy's DFA-based regex engine handles complex patterns safely."""

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
    def sample_document_with_long_text(self):
        """
        Document with long repetitive text designed to trigger catastrophic backtracking.
        """
        # Create content with many repeated 'a' characters followed by non-matching char
        long_repeated_text = "a" * 30 + "X"  # 30 'a's then 'X' (won't match patterns ending in 'b')

        return {
            "path": "test/vulnerable.txt",
            "content": f"""# Test file for ReDoS testing
This line has repeated characters: {long_repeated_text}
Another line with pattern: {"b" * 20}c
Normal text without patterns here
Final line: {long_repeated_text}""",
            "content_raw": f"""# Test file for ReDoS testing
This line has repeated characters: {long_repeated_text}
Another line with pattern: {"b" * 20}c
Normal text without patterns here
Final line: {long_repeated_text}""",
            "identifiers": ["test", "vulnerable"],
            "line_start": 1,
            "line_end": 5,
            "language": "text",
        }

    @pytest.fixture
    def indexed_manager_with_vulnerable_content(
        self, tantivy_manager, sample_document_with_long_text
    ):
        """Manager with document containing content vulnerable to ReDoS."""
        tantivy_manager.add_document(sample_document_with_long_text)
        tantivy_manager.commit()
        return tantivy_manager

    def test_dfa_handles_nested_quantifiers_instantly(
        self, indexed_manager_with_vulnerable_content
    ):
        """
        GIVEN indexed content with repeated characters (aaaaaaaaaa...X)
        WHEN searching with pattern '(a+)+' that causes ReDoS in backtracking engines
        THEN Tantivy's DFA-based engine completes in linear time (<100ms)
        AND returns results without catastrophic backtracking

        ReDoS Pattern (Safe in DFA): (a+)+ causes O(2^n) backtracking in PCRE/Python,
        but Tantivy's DFA handles it in O(n) linear time.

        Expected Behavior:
        - Search completes instantly (well under 100ms)
        - No timeout or error (DFA doesn't backtrack)
        - Returns empty or valid results depending on pattern match
        """
        pattern = r"(a+)+"  # Nested quantifiers = exponential time in backtracking engines

        start_time = time.time()

        # Should NOT raise any timeout/error - DFA completes instantly
        results = indexed_manager_with_vulnerable_content.search(
            query_text=pattern,
            use_regex=True,
            limit=10,
        )

        elapsed_time = time.time() - start_time

        # CRITICAL: DFA must complete in linear time (well under 100ms)
        assert elapsed_time < 0.1, (
            f"DFA-based regex should complete instantly, took {elapsed_time:.2f}s"
        )

        # Results are valid (may be empty if pattern doesn't match - that's OK)
        # The key is that it completed quickly without catastrophic backtracking
        assert isinstance(results, list)

    def test_dfa_handles_overlapping_alternation_instantly(
        self, indexed_manager_with_vulnerable_content
    ):
        """
        GIVEN indexed content with repeated characters
        WHEN searching with pattern '(a|a)*b' that causes ReDoS in backtracking engines
        THEN Tantivy's DFA-based engine completes in linear time (<100ms)

        ReDoS Pattern (Safe in DFA): (a|a)*b with overlapping alternatives causes
        exponential backtracking in PCRE/Python, but Tantivy's DFA handles it safely.
        """
        pattern = r"(a|a)*b"  # Overlapping alternation

        start_time = time.time()

        # Should NOT raise any timeout/error - DFA completes instantly
        results = indexed_manager_with_vulnerable_content.search(
            query_text=pattern,
            use_regex=True,
            limit=10,
        )

        elapsed_time = time.time() - start_time

        # Must complete quickly (DFA is linear time)
        assert elapsed_time < 0.1, (
            f"DFA should complete instantly, took {elapsed_time:.2f}s"
        )
        assert isinstance(results, list)

    def test_dfa_handles_nested_groups_instantly(
        self, indexed_manager_with_vulnerable_content
    ):
        """
        GIVEN indexed content
        WHEN searching with pattern '(a*)*b' that causes ReDoS in backtracking engines
        THEN Tantivy's DFA-based engine completes in linear time (<100ms)

        ReDoS Pattern (Safe in DFA): (a*)*b causes catastrophic backtracking in
        PCRE/Python, but Tantivy's DFA handles it safely.
        """
        pattern = r"(a*)*b"

        start_time = time.time()

        results = indexed_manager_with_vulnerable_content.search(
            query_text=pattern,
            use_regex=True,
            limit=10,
        )

        elapsed_time = time.time() - start_time
        assert elapsed_time < 0.1
        assert isinstance(results, list)

    def test_safe_regex_pattern_completes_quickly(
        self, indexed_manager_with_vulnerable_content
    ):
        """
        GIVEN indexed content
        WHEN searching with simple regex pattern '.*'
        THEN should complete successfully within 100ms
        AND return valid results

        This verifies that DFA-based regex works correctly for simple patterns.
        """
        safe_pattern = r".*"  # Simple pattern that matches content

        start_time = time.time()

        results = indexed_manager_with_vulnerable_content.search(
            query_text=safe_pattern,
            use_regex=True,
            limit=10,
        )

        elapsed_time = time.time() - start_time

        # Should complete quickly (DFA is linear time)
        assert elapsed_time < 0.1, (
            f"Safe regex should complete instantly, took {elapsed_time:.2f}s"
        )

        # Results should be valid (may be empty or contain matches)
        assert isinstance(results, list)

    def test_dfa_handles_complex_patterns_gracefully(
        self, indexed_manager_with_vulnerable_content
    ):
        """
        GIVEN complex regex pattern that would cause ReDoS in backtracking engines
        WHEN executing search with Tantivy's DFA engine
        THEN search completes quickly without errors
        AND returns valid results

        This verifies that DFA handles complex patterns gracefully without
        needing error messages about timeouts or ReDoS.
        """
        pattern = r"(a+)+"

        start_time = time.time()

        # Should complete successfully without errors
        results = indexed_manager_with_vulnerable_content.search(
            query_text=pattern,
            use_regex=True,
            limit=10,
        )

        elapsed_time = time.time() - start_time

        # DFA completes quickly
        assert elapsed_time < 0.1, (
            f"DFA should complete instantly, took {elapsed_time:.2f}s"
        )

        # Results are valid
        assert isinstance(results, list)

    def test_multiple_searches_remain_fast(
        self, indexed_manager_with_vulnerable_content
    ):
        """
        GIVEN multiple sequential regex searches
        WHEN executing searches back-to-back
        THEN each search remains fast (DFA linear time)
        AND performance doesn't degrade over time

        This verifies DFA's consistent linear-time performance.
        """
        pattern = r".*"

        # Execute multiple searches
        for i in range(5):
            start_time = time.time()

            results = indexed_manager_with_vulnerable_content.search(
                query_text=pattern,
                use_regex=True,
                limit=10,
            )

            elapsed_time = time.time() - start_time

            # Each search should complete quickly with DFA
            assert elapsed_time < 0.1, (
                f"Search {i+1} took too long: {elapsed_time:.2f}s"
            )

            assert isinstance(results, list)

    def test_case_insensitive_patterns_handled_safely(
        self, indexed_manager_with_vulnerable_content
    ):
        """
        GIVEN complex regex pattern with case_sensitive=False
        WHEN executing search
        THEN DFA protection applies regardless of case sensitivity flag

        Verifies that DFA's linear-time guarantee works for case-insensitive searches.
        """
        pattern = r"(A+)+"

        start_time = time.time()

        results = indexed_manager_with_vulnerable_content.search(
            query_text=pattern,
            use_regex=True,
            case_sensitive=False,  # Case insensitive mode
            limit=10,
        )

        elapsed_time = time.time() - start_time
        assert elapsed_time < 0.1
        assert isinstance(results, list)

    @pytest.mark.parametrize(
        "pattern",
        [
            r"(a+)+",  # Nested quantifiers
            r"(a|a)*b",  # Overlapping alternation
            r"(a*)*b",  # Nested star quantifiers
            r"(a|ab)*c",  # Overlapping alternation with suffix
            r"(x+x+)+y",  # Multiple nested quantifiers
        ],
    )
    def test_various_complex_patterns_handled_instantly(
        self, indexed_manager_with_vulnerable_content, pattern
    ):
        """
        GIVEN various complex regex patterns that cause ReDoS in backtracking engines
        WHEN executing search with any pattern
        THEN all complete instantly with DFA's linear-time guarantee

        Comprehensive test covering multiple patterns that are safe in DFA engines.
        """
        start_time = time.time()

        results = indexed_manager_with_vulnerable_content.search(
            query_text=pattern,
            use_regex=True,
            limit=10,
        )

        elapsed_time = time.time() - start_time
        assert elapsed_time < 0.1, (
            f"Pattern '{pattern}' took too long: {elapsed_time:.2f}s"
        )
        assert isinstance(results, list)
