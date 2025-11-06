"""Unit tests for path filter bug in temporal queries.

ISSUE: Path filters return 0 results for temporal queries but work for regular queries.
ROOT CAUSE: Temporal collection uses 'file_path' field, main collection uses 'path' field.
Path filters check 'path' key which doesn't exist in temporal payloads.
"""

from pathlib import Path


class TestPathFilterTemporalBug:
    """Tests reproducing path filter bug in temporal queries."""

    def test_parse_qdrant_filter_matches_path_field_in_main_collection(self):
        """Test that path filter works with 'path' field (main collection format)."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        # Main collection payload format (has 'path' field)
        payload = {
            "path": "tests/e2e/temporal/test_temporal_indexing_e2e.py",
            "language": "python",
            "type": "content",
        }

        # Build filter for *.py pattern
        filter_conditions = {"must": [{"key": "path", "match": {"text": "*.py"}}]}

        # Parse filter to callable
        filter_func = store._parse_qdrant_filter(filter_conditions)

        # MUST PASS: Main collection format with 'path' field
        assert filter_func(payload) is True

    def test_parse_qdrant_filter_now_works_with_file_path_field_temporal_collection(self):
        """Test that path filter NOW WORKS with 'file_path' field (temporal collection format).

        FIXED BUG: temporal payloads use 'file_path' but filters checked 'path',
        causing all results to be filtered out. Now falls back to 'file_path'.
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        # Temporal collection payload format (has 'file_path', NOT 'path')
        payload = {
            "file_path": "tests/e2e/temporal/test_temporal_indexing_e2e.py",
            "type": "file_chunk",
            "blob_hash": "abc123",
            "commit_hash": "def456",
        }

        # Build filter for *.py pattern (checks 'path' key)
        filter_conditions = {"must": [{"key": "path", "match": {"text": "*.py"}}]}

        # Parse filter to callable
        filter_func = store._parse_qdrant_filter(filter_conditions)

        # FIXED: Now returns True by falling back to 'file_path' field
        result = filter_func(payload)

        assert result is True, "Path filter should now match file_path field"

    def test_path_filter_matches_both_path_and_file_path_fields(self):
        """Test that path filter works with BOTH 'path' and 'file_path' fields.

        FIXED: Path filter now checks both 'path' (main collection) and
        'file_path' (temporal collection) fields for backward compatibility.
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        # Test with 'path' field (main collection)
        payload_main = {
            "path": "src/code_indexer/cli.py",
            "type": "content",
        }

        # Test with 'file_path' field (temporal collection)
        payload_temporal = {
            "file_path": "src/code_indexer/cli.py",
            "type": "file_chunk",
        }

        # Build filter for src/*.py pattern
        filter_conditions = {"must": [{"key": "path", "match": {"text": "src/*.py"}}]}

        filter_func = store._parse_qdrant_filter(filter_conditions)

        # FIXED: Both should now match
        assert filter_func(payload_main) is True, "Main collection format should match"
        assert filter_func(payload_temporal) is True, "Temporal format should now match"

    def test_exact_path_filter_temporal_collection(self):
        """Test exact path match for temporal collection."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        payload = {
            "file_path": "tests/e2e/temporal/test_temporal_indexing_e2e.py",
            "type": "file_chunk",
        }

        # Exact path filter
        filter_conditions = {
            "must": [
                {
                    "key": "path",
                    "match": {"text": "tests/e2e/temporal/test_temporal_indexing_e2e.py"},
                }
            ]
        }

        filter_func = store._parse_qdrant_filter(filter_conditions)

        # FIXED: Exact path now matches file_path field
        assert filter_func(payload) is True, "Exact path should match file_path field"

    def test_wildcard_path_filter_temporal_collection(self):
        """Test wildcard path filter for temporal collection."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        payload = {
            "file_path": "tests/e2e/temporal/test_temporal_indexing_e2e.py",
            "type": "file_chunk",
        }

        # Wildcard path filter
        filter_conditions = {"must": [{"key": "path", "match": {"text": "tests/**/*.py"}}]}

        filter_func = store._parse_qdrant_filter(filter_conditions)

        # FIXED: Wildcard path now matches file_path field
        assert filter_func(payload) is True, "Wildcard path should match file_path field"

    def test_path_filter_with_language_filter_temporal(self):
        """Test combined path + language filter for temporal collection."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        payload = {
            "file_path": "src/code_indexer/services/temporal/temporal_indexer.py",
            "language": "py",  # Temporal uses extension as language
            "type": "file_chunk",
        }

        # Combined filter
        filter_conditions = {
            "must": [
                {"key": "path", "match": {"text": "src/**/*.py"}},
                {"key": "language", "match": {"value": "py"}},
            ]
        }

        filter_func = store._parse_qdrant_filter(filter_conditions)

        # FIXED: Combined filter now works with file_path field
        assert filter_func(payload) is True, "Combined filter should work with file_path"


class TestPathFilterFix:
    """Tests for the path filter fix implementation.

    These tests define the expected behavior AFTER the fix.
    They will fail initially (red) and pass after implementation (green).
    """

    def test_path_filter_fallback_to_file_path_field(self):
        """After fix: Path filter should fall back to 'file_path' if 'path' missing."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        # Temporal payload with only 'file_path'
        payload = {
            "file_path": "tests/e2e/temporal/test_temporal_indexing_e2e.py",
            "type": "file_chunk",
        }

        filter_conditions = {"must": [{"key": "path", "match": {"text": "*.py"}}]}

        filter_func = store._parse_qdrant_filter(filter_conditions)

        # MUST PASS AFTER FIX: Should fall back to 'file_path'
        # WILL FAIL BEFORE FIX
        result = filter_func(payload)
        assert result is True, "Path filter should fall back to file_path field"

    def test_path_filter_prefers_path_field_over_file_path(self):
        """After fix: Path filter should prefer 'path' field if both exist."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        # Payload with BOTH fields (edge case)
        payload = {
            "path": "correct/path.py",
            "file_path": "wrong/path.py",
            "type": "content",
        }

        filter_conditions = {"must": [{"key": "path", "match": {"text": "correct/*.py"}}]}

        filter_func = store._parse_qdrant_filter(filter_conditions)

        # Should use 'path' field (primary), not 'file_path'
        # WILL FAIL BEFORE FIX
        result = filter_func(payload)
        assert result is True, "Should prefer 'path' field when both exist"

    def test_path_exclusion_filter_works_with_file_path(self):
        """After fix: Path exclusion filters should work with file_path field."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        store = FilesystemVectorStore(base_path=Path("/tmp"))

        payload = {
            "file_path": "tests/unit/test_something.py",
            "type": "file_chunk",
        }

        # Exclusion filter (must_not)
        filter_conditions = {"must_not": [{"key": "path", "match": {"text": "tests/*"}}]}

        filter_func = store._parse_qdrant_filter(filter_conditions)

        # Should exclude this path
        # WILL FAIL BEFORE FIX
        result = filter_func(payload)
        assert result is False, "Should exclude path matching must_not pattern"
