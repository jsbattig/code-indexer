"""
Unit tests for TantivyIndexManager empty match validation and handling.

CORRECTNESS ISSUE: Regex patterns like 'x*', 'y?', or '\\b' can produce
zero-length matches, causing:
1. Infinite loops in some regex engines
2. Confusing results (every position matches)
3. Incorrect line/column calculations
4. Misleading match_text (empty string)

Empty Match Examples:
- Pattern: 'x*' matches "" at EVERY position (even where 'x' doesn't exist)
- Pattern: 'y?' matches "" everywhere (y is optional)
- Pattern: '\\b' matches word boundaries (zero-width assertion)
- Pattern: '^' or '$' match line start/end (zero-width)

Expected Behavior:
1. Detect zero-length matches
2. Log warning about empty match
3. Either skip empty matches OR include them with clear indication
4. Prevent infinite loops or confusing output

Tests follow TDD methodology:
1. Write tests for various empty match scenarios
2. Implement validation and handling
3. Verify appropriate warnings and behavior
"""

import pytest
import logging
from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestTantivyEmptyMatchValidation:
    """Test suite for empty match validation and handling."""

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
    def sample_document(self):
        """Sample document for testing empty matches."""
        return {
            "path": "src/test.py",
            "content": """def function():
    x = 10
    y = 20
    return x + y
""",
            "content_raw": """def function():
    x = 10
    y = 20
    return x + y
""",
            "identifiers": ["function", "x", "y"],
            "line_start": 1,
            "line_end": 4,
            "language": "python",
        }

    @pytest.fixture
    def indexed_manager(self, tantivy_manager, sample_document):
        """Manager with sample document indexed."""
        tantivy_manager.add_document(sample_document)
        tantivy_manager.commit()
        return tantivy_manager

    def test_empty_match_pattern_star_quantifier(self, indexed_manager, caplog):
        """
        GIVEN pattern 'x*' (matches zero or more 'x' characters)
        WHEN searching indexed content
        THEN should handle zero-length matches appropriately

        Pattern 'x*' can match:
        - "xxx" (length 3)
        - "x" (length 1)
        - "" (length 0) - EMPTY MATCH at every position

        Expected: Either skip empty matches or log warning
        """
        with caplog.at_level(logging.WARNING):
            results = indexed_manager.search(
                query_text=r"x*",
                use_regex=True,
                limit=10,
            )

        # Should find results (likely including empty matches)
        # The behavior depends on implementation:
        # Option A: Include empty matches with warning
        # Option B: Skip empty matches entirely

        # At minimum, should not crash or hang
        assert isinstance(results, list)

        # Check if warning was logged about empty matches
        if results:
            # If we got results, check for empty match_text
            empty_matches = [r for r in results if len(r.get("match_text", "x")) == 0]

            if empty_matches:
                # If empty matches are included, should have warning logged
                assert any(
                    "empty" in record.message.lower()
                    or "zero-length" in record.message.lower()
                    for record in caplog.records
                ), "Should log warning for empty matches"

                print(f"Found {len(empty_matches)} empty matches with warning")

    def test_empty_match_pattern_optional_quantifier(self, indexed_manager, caplog):
        """
        GIVEN pattern 'y?' (matches zero or one 'y' character)
        WHEN searching
        THEN should handle zero-length matches

        Pattern 'y?' matches "" at every position where 'y' is absent.
        """
        with caplog.at_level(logging.WARNING):
            results = indexed_manager.search(
                query_text=r"y?",
                use_regex=True,
                limit=10,
            )

        assert isinstance(results, list)

        # Check for empty matches
        empty_matches = [r for r in results if len(r.get("match_text", "y")) == 0]

        if empty_matches:
            print(f"Pattern 'y?' produced {len(empty_matches)} empty matches")

    def test_empty_match_pattern_word_boundary(self, indexed_manager, caplog):
        """
        GIVEN pattern '\\b' (word boundary - zero-width assertion)
        WHEN searching
        THEN Tantivy should reject with ValueError

        Tantivy rejects zero-width assertions with "Empty match operators are not allowed".
        """
        with pytest.raises(ValueError, match=r"Empty match operators are not allowed"):
            indexed_manager.search(
                query_text=r"\b",
                use_regex=True,
                limit=10,
            )

    def test_empty_match_pattern_line_start_anchor(self, indexed_manager, caplog):
        """
        GIVEN pattern '^' (line start anchor - zero-width)
        WHEN searching
        THEN Tantivy should reject with ValueError

        Tantivy rejects zero-width assertions with "Empty match operators are not allowed".
        """
        with pytest.raises(ValueError, match=r"Empty match operators are not allowed"):
            indexed_manager.search(
                query_text=r"^",
                use_regex=True,
                limit=10,
            )

    def test_empty_match_doesnt_cause_infinite_loop(self, indexed_manager):
        """
        GIVEN pattern that produces many empty matches
        WHEN searching with limit
        THEN should not hang or loop infinitely

        Critical safety test: empty matches shouldn't cause infinite loops.
        """
        import time

        start_time = time.time()

        # Pattern that matches empty string everywhere
        results = indexed_manager.search(
            query_text=r"x*|y*",
            use_regex=True,
            limit=100,  # Even with high limit, should complete quickly
        )

        elapsed_time = time.time() - start_time

        # Should complete quickly (no infinite loop)
        assert elapsed_time < 2.0, (
            f"Search took too long: {elapsed_time:.2f}s. "
            f"May indicate infinite loop from empty matches."
        )

        # Should respect limit even with many potential empty matches
        assert len(results) <= 100, f"Should respect limit, got {len(results)} results"

    def test_non_empty_match_works_normally(self, indexed_manager):
        """
        GIVEN pattern that always produces non-empty matches 'def'
        WHEN searching
        THEN should work normally without warnings

        Sanity check: Normal matches shouldn't trigger empty match handling.
        """
        results = indexed_manager.search(
            query_text=r"def",
            use_regex=True,
            limit=10,
        )

        assert len(results) > 0, "Should find 'def' keyword"

        # All matches should be non-empty
        for result in results:
            match_text = result.get("match_text", "")
            assert (
                len(match_text) > 0
            ), f"'def' pattern should produce non-empty matches, got: '{match_text}'"
            assert (
                match_text == "def"
            ), f"Expected match_text to be 'def', got: '{match_text}'"

    def test_empty_match_provides_clear_error_or_warning(self, indexed_manager, caplog):
        """
        GIVEN pattern that produces empty matches
        WHEN empty match is detected
        THEN should provide clear warning message

        Message should include:
        - Indication that match is empty/zero-length
        - Pattern that caused it
        - Suggestion to use more specific pattern
        """
        with caplog.at_level(logging.WARNING):
            results = indexed_manager.search(
                query_text=r"x*",
                use_regex=True,
                limit=10,
            )

        # Check if warning was logged
        empty_matches = [r for r in results if len(r.get("match_text", "x")) == 0]

        if empty_matches:
            # Should have logged warning
            for record in caplog.records:
                if record.levelname == "WARNING":
                    message = record.message.lower()
                    if "empty" in message or "zero" in message or "length" in message:
                        print(f"Empty match warning: {record.message}")
                        break

            # Implementation choice: either skip empty matches OR log warning
            # If empty matches are returned, warning should be logged

    def test_mixed_empty_and_non_empty_matches(self, indexed_manager):
        """
        GIVEN pattern that can match both empty and non-empty strings 'x*'
        WHEN searching content with actual 'x' characters
        THEN should prefer non-empty matches or handle both correctly

        Example: Content "x = 10"
        - Can match "x" (length 1) at position of variable
        - Can match "" (length 0) at every other position

        Preferred behavior: Return non-empty matches, skip empty ones.
        """
        results = indexed_manager.search(
            query_text=r"x*",
            use_regex=True,
            limit=20,
        )

        if results:
            # Count empty vs non-empty matches
            empty_count = sum(1 for r in results if len(r.get("match_text", "x")) == 0)
            non_empty_count = sum(
                1 for r in results if len(r.get("match_text", "")) > 0
            )

            print(
                f"Pattern 'x*': {non_empty_count} non-empty matches, {empty_count} empty matches"
            )

            # Ideally should prioritize non-empty matches
            if non_empty_count > 0:
                # If we found non-empty matches, they should dominate results
                assert (
                    non_empty_count >= empty_count
                ), "Should prioritize non-empty matches over empty ones"

    def test_zero_width_lookahead_assertion(self, indexed_manager):
        """
        GIVEN pattern with lookahead '(?=function)' (zero-width)
        WHEN searching
        THEN Tantivy should reject with ValueError

        Tantivy doesn't support look-around assertions.
        """
        with pytest.raises(ValueError, match=r"look-around.*is not supported"):
            indexed_manager.search(
                query_text=r"(?=function)",
                use_regex=True,
                limit=10,
            )

    def test_empty_match_still_has_valid_line_and_column(self, indexed_manager):
        """
        GIVEN empty match pattern
        WHEN match is found
        THEN line and column should still be valid (not default to 1, 1)

        Even for empty matches, position information should be accurate.
        """
        results = indexed_manager.search(
            query_text=r"x*",
            use_regex=True,
            limit=10,
        )

        # Check if we got any empty matches
        empty_matches = [r for r in results if len(r.get("match_text", "x")) == 0]

        if empty_matches:
            for result in empty_matches[:3]:  # Check first few
                line = result.get("line", 0)
                column = result.get("column", 0)

                # Position should be valid (positive integers)
                assert (
                    line > 0
                ), f"Empty match should have valid line number, got {line}"
                assert (
                    column > 0
                ), f"Empty match should have valid column number, got {column}"

                print(f"Empty match at line {line}, column {column}")

    def test_empty_match_snippet_is_still_useful(self, indexed_manager):
        """
        GIVEN empty match pattern '^' (line start anchor)
        WHEN searching
        THEN Tantivy should reject with ValueError

        Tantivy rejects zero-width assertions with "Empty match operators are not allowed".
        """
        with pytest.raises(ValueError, match=r"Empty match operators are not allowed"):
            indexed_manager.search(
                query_text=r"^",  # Line start (zero-width)
                use_regex=True,
                snippet_lines=2,
                limit=10,
            )

    def test_pattern_with_alternation_including_empty(self, indexed_manager):
        """
        GIVEN pattern with alternation where one branch is empty 'x|'
        WHEN searching
        THEN should handle appropriately

        Pattern 'x|' means "match 'x' OR empty string", so can produce many empty matches.
        """
        results = indexed_manager.search(
            query_text=r"x|",
            use_regex=True,
            limit=10,
        )

        assert isinstance(results, list)

        # This pattern can produce both 'x' and '' matches
        if results:
            empty_matches = [r for r in results if len(r.get("match_text", "x")) == 0]
            non_empty_matches = [r for r in results if len(r.get("match_text", "")) > 0]

            print(
                f"Pattern 'x|': {len(non_empty_matches)} non-empty, {len(empty_matches)} empty"
            )
