"""Unit tests for temporal search service file_path bug fixes.

Tests that temporal_search_service correctly handles both 'path' and 'file_path'
fields in payloads to fix display bugs in binary file detection and commit diff display.

Bug: Lines 430 and 478 only checked 'file_path' field, but some payloads use 'path' field.
"""

import unittest
from unittest.mock import Mock
from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


class TestTemporalSearchFilePathBug(unittest.TestCase):
    """Test cases for file_path field handling bug fixes."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_config_manager = Mock()
        self.mock_vector_store = Mock()
        self.mock_embedding = Mock()

        from pathlib import Path

        self.project_root = Path("/test/repo")

        self.service = TemporalSearchService(
            config_manager=self.mock_config_manager,
            project_root=self.project_root,
            vector_store_client=self.mock_vector_store,
            embedding_provider=self.mock_embedding,
        )

    def test_binary_file_detection_with_path_field(self):
        """Test that binary file detection works with 'path' field (line 430 bug)."""
        # Create mock Qdrant result with 'path' field (NOT 'file_path')
        mock_result = Mock()
        mock_result.id = "point1"
        mock_result.score = 0.85
        mock_result.payload = {
            "type": "file_chunk",
            "path": "images/logo.png",  # Use 'path' field
            "commit_hash": "abc123",
            "blob_hash": "blob456",
            "line_start": 1,
            "line_end": 1,
            # No content field - binary file
        }

        # Get content - should detect binary from 'path' field
        content = self.service._fetch_match_content(mock_result.payload)

        # Should return binary file message with correct extension
        self.assertEqual(content, "[Binary file - .png]")

    def test_commit_diff_display_with_path_field(self):
        """Test that commit diff display works with 'path' field (line 478 bug)."""
        # Create mock payload with 'path' field (NOT 'file_path')
        payload = {
            "type": "commit_diff",
            "path": "src/main.py",  # Use 'path' field
            "diff_type": "modified",
            "commit_hash": "def456",
        }

        # Get content - should show actual path, not "unknown"
        content = self.service._fetch_match_content(payload)

        # Should show actual path in the diff description
        self.assertEqual(content, "[MODIFIED file: src/main.py]")

    def test_helper_method_prefers_path_over_file_path(self):
        """Test that helper method prefers 'path' field over 'file_path'."""
        payload_with_both = {
            "path": "correct/path.py",
            "file_path": "wrong/path.py",
        }
        result = self.service._get_file_path_from_payload(payload_with_both, "default")
        self.assertEqual(result, "correct/path.py")


if __name__ == "__main__":
    unittest.main()
