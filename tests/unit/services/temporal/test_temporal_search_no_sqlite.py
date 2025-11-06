"""Test suite verifying complete SQLite elimination from temporal query service.

Story 2: Complete SQLite removal - all data from JSON payloads.
"""

import unittest
from unittest.mock import Mock
from pathlib import Path

from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


class TestTemporalSearchNoSQLite(unittest.TestCase):
    """Verify complete SQLite elimination from temporal query service."""

    def test_no_sqlite3_import(self):
        """Verify sqlite3 is NOT imported in temporal_search_service module."""
        # Check module imports
        import src.code_indexer.services.temporal.temporal_search_service as tss_module

        # sqlite3 should NOT be in the module's namespace
        self.assertNotIn('sqlite3', dir(tss_module),
                        "sqlite3 should not be imported in temporal_search_service")

    def test_no_commits_db_path_attribute(self):
        """Verify commits_db_path is not initialized in the service."""
        config_manager = Mock()
        project_root = Path("/test/repo")

        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
        )

        # commits_db_path should NOT exist
        self.assertFalse(hasattr(service, 'commits_db_path'),
                        "commits_db_path should not exist (SQLite removed)")

    def test_filter_by_time_range_uses_payloads_only(self):
        """Verify _filter_by_time_range uses JSON payloads, not SQLite."""
        config_manager = Mock()
        project_root = Path("/test/repo")

        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
        )

        # Create mock semantic results with temporal metadata in payloads
        semantic_results = [
            {
                "score": 0.95,
                "content": "Authentication implementation",
                "payload": {
                    "type": "commit_diff",
                    "file_path": "src/auth.py",
                    "commit_hash": "abc123",
                    "commit_timestamp": 1761973200,  # 2025-11-01
                    "commit_date": "2025-11-01",
                    "commit_message": "Add authentication",
                    "author_name": "Test User",
                    "diff_type": "added",
                    "chunk_index": 0,
                }
            },
            {
                "score": 0.88,
                "content": "Database connection setup",
                "payload": {
                    "type": "commit_diff",
                    "file_path": "src/database.py",
                    "commit_hash": "def456",
                    "commit_timestamp": 1762059600,  # 2025-11-02
                    "commit_date": "2025-11-02",
                    "commit_message": "Update database",
                    "author_name": "Another User",
                    "diff_type": "modified",
                    "chunk_index": 1,
                }
            },
            {
                "score": 0.76,
                "content": "Old API implementation",
                "payload": {
                    "type": "commit_diff",
                    "file_path": "src/old_api.py",
                    "commit_hash": "ghi789",
                    "commit_timestamp": 1761800400,  # 2025-10-30 (outside range)
                    "commit_date": "2025-10-30",
                    "commit_message": "Legacy API",
                    "author_name": "Old User",
                    "diff_type": "deleted",
                    "chunk_index": 0,
                }
            }
        ]

        # Call _filter_by_time_range - should work without SQLite
        results, fetch_time = service._filter_by_time_range(
            semantic_results=semantic_results,
            start_date="2025-11-01",
            end_date="2025-11-02",
            min_score=None
        )

        # Verify results filtered by payload timestamps
        self.assertEqual(len(results), 2, "Should return 2 results in date range")

        # Check first result (Nov 1)
        self.assertEqual(results[0].file_path, "src/auth.py")
        self.assertEqual(results[0].metadata["diff_type"], "added")
        self.assertEqual(results[0].temporal_context["commit_hash"], "abc123")
        self.assertEqual(results[0].temporal_context["commit_date"], "2025-11-01")

        # Check second result (Nov 2)
        self.assertEqual(results[1].file_path, "src/database.py")
        self.assertEqual(results[1].metadata["diff_type"], "modified")
        self.assertEqual(results[1].temporal_context["commit_hash"], "def456")
        self.assertEqual(results[1].temporal_context["commit_date"], "2025-11-02")

    def test_fetch_commit_details_no_sqlite(self):
        """Verify _fetch_commit_details doesn't use SQLite."""
        config_manager = Mock()
        project_root = Path("/test/repo")

        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
        )

        # This should not raise an error even without SQLite
        # It should return dummy data for backward compatibility
        result = service._fetch_commit_details("abc123")

        # Should return something, not None
        self.assertIsNotNone(result)

        # Should have required fields for CLI display
        self.assertIn("hash", result)
        self.assertIn("date", result)
        self.assertIn("author_name", result)
        self.assertIn("author_email", result)
        self.assertIn("message", result)

        # Should indicate it's placeholder data
        self.assertEqual(result["hash"], "abc123")

    def test_unused_sqlite_methods_removed(self):
        """Verify SQLite-dependent helper methods are removed or stubbed."""
        config_manager = Mock()
        project_root = Path("/test/repo")

        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
        )

        # These methods should either not exist or return empty/stub values
        # _is_new_file - should not exist (unused)
        self.assertFalse(hasattr(service, '_is_new_file'),
                        "_is_new_file should be removed (unused)")

        # _generate_chunk_diff - should not exist (unused)
        self.assertFalse(hasattr(service, '_generate_chunk_diff'),
                        "_generate_chunk_diff should be removed (unused)")

        # _get_head_file_blobs - should not exist (blob-based, unused)
        self.assertFalse(hasattr(service, '_get_head_file_blobs'),
                        "_get_head_file_blobs should be removed (blob-based)")

        # _fetch_commit_file_changes - used by CLI but should return empty
        if hasattr(service, '_fetch_commit_file_changes'):
            result = service._fetch_commit_file_changes("dummy")
            self.assertEqual(result, [], "Should return empty list")


if __name__ == "__main__":
    unittest.main()