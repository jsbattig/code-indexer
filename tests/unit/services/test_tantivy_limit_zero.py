"""
Test --limit 0 (unlimited results) feature for FTS queries.

Tests the behavior when user requests all results with minimal output.
"""

import tempfile
from pathlib import Path

import pytest

from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestTantivyLimitZero:
    """Test unlimited results with --limit 0."""

    @pytest.fixture
    def temp_index_dir(self):
        """Create temporary index directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def populated_index(self, temp_index_dir):
        """Create index with multiple matching documents."""
        manager = TantivyIndexManager(str(temp_index_dir))
        manager.initialize_index(create_new=True)

        # Create 50 test files with "Service" keyword
        for i in range(50):
            content = (
                f"public class Service{i} implements IService {{\n"
                f"    // Service implementation {i}\n"
                f"    public void execute() {{}}\n"
                f"}}"
            )
            doc = {
                "path": f"src/services/Service{i}.java",
                "content": content,
                "content_raw": content,
                "identifiers": ["Service" + str(i), "IService", "execute"],
                "line_start": 1,
                "line_end": 4,
                "language": "java",
            }
            manager.add_document(doc)

        manager.commit()
        return manager

    def test_limit_zero_does_not_panic(self, populated_index):
        """Test that limit=0 doesn't cause Tantivy panic."""
        # This should NOT raise "Limit must be strictly greater than 0"
        results = populated_index.search(query_text="Service", limit=0, snippet_lines=5)

        # Should return results, not crash
        assert isinstance(results, list)

    def test_limit_zero_returns_more_than_default(self, populated_index):
        """Test that limit=0 returns more results than default limit."""
        # Default limit
        limited_results = populated_index.search(
            query_text="Service", limit=10, snippet_lines=5
        )

        # Unlimited
        unlimited_results = populated_index.search(
            query_text="Service", limit=0, snippet_lines=5
        )

        assert len(unlimited_results) > len(limited_results)
        assert len(unlimited_results) >= 50  # Should get all 50 documents

    def test_limit_zero_sets_snippet_lines_zero(self, populated_index):
        """Test that limit=0 automatically disables snippets."""
        results = populated_index.search(
            query_text="Service",
            limit=0,
            snippet_lines=5,  # User sets 5
        )

        # Verify all results have no snippet or empty snippet
        for result in results:
            snippet = result.get("snippet", "")
            # With limit=0, snippets should be minimal/empty
            assert (
                snippet == "" or len(snippet.split("\n")) <= 1
            ), f"Expected minimal snippet for limit=0, got: {snippet}"

    def test_limit_zero_minimal_output_format(self, populated_index):
        """Test that limit=0 results have minimal fields (grep-like)."""
        results = populated_index.search(query_text="Service", limit=0)

        # Each result should have essential fields
        for result in results:
            assert "path" in result
            assert "line" in result  # Line number field in results
            # Snippet should be absent or minimal (empty when snippet_lines=0)
            snippet = result.get("snippet", "")
            assert snippet == "", f"Expected empty snippet for limit=0, got: {snippet}"

    def test_limit_zero_returns_all_matches(self, populated_index):
        """Test that limit=0 truly returns all matches."""
        # Search for common term that appears in all documents
        results = populated_index.search(query_text="Service", limit=0)

        # Should find all 50 documents
        assert len(results) >= 50, f"Expected at least 50 results, got {len(results)}"

    def test_limit_zero_performance_with_large_results(self, temp_index_dir):
        """Test performance with limit=0 on large result sets."""
        manager = TantivyIndexManager(str(temp_index_dir))
        manager.initialize_index(create_new=True)

        # Create 200 documents
        for i in range(200):
            content = (
                f"public class Test{i} {{\n"
                f"    @Test public void testMethod() {{}}\n"
                f"}}"
            )
            doc = {
                "path": f"src/test/Test{i}.java",
                "content": content,
                "content_raw": content,
                "identifiers": ["Test" + str(i), "testMethod"],
                "line_start": 1,
                "line_end": 3,
                "language": "java",
            }
            manager.add_document(doc)

        manager.commit()

        # Search with limit=0 should complete quickly
        import time

        start = time.time()
        results = manager.search(query_text="Test", limit=0)
        duration = time.time() - start

        # Should return many results
        assert len(results) >= 200

        # Should complete in reasonable time (< 1 second)
        assert duration < 1.0, f"limit=0 search took {duration}s, expected < 1s"

    def test_limit_zero_with_filters(self, populated_index):
        """Test that limit=0 works with language/path filters."""
        results = populated_index.search(
            query_text="Service",
            limit=0,
            languages=["java"],
            path_filters=["src/services/*"],
        )

        # Should return filtered results
        assert len(results) > 0
        for result in results:
            assert result["path"].startswith("src/services/")
            assert result.get("language") == "java"

    def test_limit_zero_vs_high_limit(self, populated_index):
        """Test that limit=0 behaves same as very high limit."""
        # High limit
        high_limit_results = populated_index.search(query_text="Service", limit=100000)

        # Unlimited
        unlimited_results = populated_index.search(query_text="Service", limit=0)

        # Should return same number of results
        assert len(unlimited_results) == len(high_limit_results)
