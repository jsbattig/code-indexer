"""Test TemporalSearchService with complete SQLite removal (Story 2).

This test ensures temporal queries work purely with JSON payloads,
without any SQLite database dependencies.
"""

import unittest
from unittest.mock import Mock
from pathlib import Path

from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


class TestTemporalSearchSQLiteFree(unittest.TestCase):
    """Test temporal search with complete SQLite removal."""

    def setUp(self):
        """Set up test environment."""
        self.config_manager = Mock()
        self.project_root = Path("/test/project")
        self.vector_store_client = Mock()
        self.embedding_provider = Mock()

        self.service = TemporalSearchService(
            config_manager=self.config_manager,
            project_root=self.project_root,
            vector_store_client=self.vector_store_client,
            embedding_provider=self.embedding_provider,
            collection_name="test-collection",
        )

    def test_no_sqlite_imports(self):
        """Verify no SQLite imports in module."""
        import src.code_indexer.services.temporal.temporal_search_service as module

        # Check module source doesn't contain sqlite3 import
        import inspect

        source = inspect.getsource(module)
        self.assertNotIn("import sqlite3", source)
        self.assertNotIn("from sqlite3", source)

    def test_no_sqlite_usage_in_generate_chunk_diff(self):
        """Verify _generate_chunk_diff doesn't use SQLite."""
        import src.code_indexer.services.temporal.temporal_search_service as module
        import inspect

        # Check if method exists
        if hasattr(module.TemporalSearchService, "_generate_chunk_diff"):
            source = inspect.getsource(
                module.TemporalSearchService._generate_chunk_diff
            )
            # Should not contain any SQLite references
            self.assertNotIn("sqlite3.connect", source)
            self.assertNotIn("commits_db_path", source)
            self.assertNotIn("conn.execute", source)

    def test_filter_by_time_range_uses_json_payloads(self):
        """Test that _filter_by_time_range uses JSON payloads without SQLite."""
        from datetime import datetime

        # Create mock semantic results with payloads
        # NEW FORMAT: chunk_text at root level (not deprecated "content" key)
        semantic_results = [
            {
                "score": 0.9,
                "chunk_text": "authentication code",  # NEW FORMAT
                "payload": {
                    "file_path": "src/auth.py",
                    "chunk_index": 0,
                    "commit_timestamp": int(datetime(2025, 11, 1).timestamp()),
                    "commit_date": "2025-11-01",
                    "commit_hash": "abc123",
                    "commit_message": "Add authentication",
                    "author_name": "Test User",
                    "diff_type": "added",
                },
            },
            {
                "score": 0.8,
                "chunk_text": "database connection",  # NEW FORMAT
                "payload": {
                    "file_path": "src/db.py",
                    "chunk_index": 0,
                    "commit_timestamp": int(datetime(2025, 11, 2).timestamp()),
                    "commit_date": "2025-11-02",
                    "commit_hash": "def456",
                    "commit_message": "Add database",
                    "author_name": "Test User",
                    "diff_type": "added",
                },
            },
        ]

        # Filter for Nov 1 only
        results, blob_time = self.service._filter_by_time_range(
            semantic_results=semantic_results,
            start_date="2025-11-01",
            end_date="2025-11-01",
        )

        # Should return only Nov 1 result
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].file_path, "src/auth.py")
        self.assertEqual(results[0].temporal_context["commit_hash"], "abc123")
        self.assertEqual(results[0].temporal_context["diff_type"], "added")
        # Blob fetch time should be 0 (no blob fetching in JSON approach)
        self.assertEqual(blob_time, 0.0)

    def test_get_head_file_blobs_removed(self):
        """Verify _get_head_file_blobs method is removed (blob-based helper)."""
        # Method should not exist
        self.assertFalse(hasattr(self.service, "_get_head_file_blobs"))


if __name__ == "__main__":
    unittest.main()
