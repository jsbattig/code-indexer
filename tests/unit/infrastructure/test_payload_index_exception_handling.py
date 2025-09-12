"""Test cases for payload index exception handling that causes false positives.

This test reproduces the actual bug:
- list_payload_indexes() catches exceptions and returns [] instead of propagating
- get_payload_index_status() interprets empty list as "no indexes exist"
- This causes false positive "missing indexes" when there's actually a connection/parsing error
"""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from code_indexer.config import Config
from code_indexer.services.qdrant import QdrantClient


class TestPayloadIndexExceptionHandling(unittest.TestCase):
    """Test for exception handling in payload index detection."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Config()
        self.config.codebase_dir = Path("/tmp/test")

        # Set up Qdrant config with payload indexes enabled
        self.config.qdrant.enable_payload_indexes = True
        self.config.qdrant.payload_indexes = [
            ("type", "keyword"),
            ("path", "text"),
            ("git_branch", "keyword"),
            ("file_mtime", "integer"),
            ("hidden_branches", "keyword"),
            ("language", "keyword"),
            ("embedding_model", "keyword"),
        ]

        # Mock console
        self.console = Mock()
        self.client = QdrantClient(self.config.qdrant, self.console)

    def test_list_payload_indexes_exception_fixed_behavior(self):
        """Test that exceptions in list_payload_indexes are properly propagated (FIXED).

        BEFORE FIX (BUG):
        1. get_collection_info throws an exception (network, parsing, etc.)
        2. list_payload_indexes catches it and returns []
        3. get_payload_index_status thinks no indexes exist and reports all as missing
        4. Query command shows false "Missing payload indexes" message

        AFTER FIX (CORRECT):
        1. get_collection_info throws an exception
        2. list_payload_indexes catches it, logs error, and re-raises RuntimeError
        3. get_payload_index_status catches RuntimeError and returns error status
        4. Query command shows appropriate error message, not false missing indexes
        """
        collection_name = "test_collection"

        # Mock get_collection_info to throw a network/parsing exception (not collection not found)
        with patch.object(
            self.client,
            "get_collection_info",
            side_effect=RuntimeError("Connection timeout"),
        ):

            # Test list_payload_indexes - should now raise RuntimeError for network errors
            with self.assertRaises(RuntimeError) as context:
                self.client.list_payload_indexes(collection_name)

            # Should raise proper error message
            self.assertIn("Unable to retrieve payload indexes", str(context.exception))
            self.assertIn("Connection timeout", str(context.exception))

            # Check that error was printed before re-raising
            self.console.print.assert_called_with(
                "Failed to list indexes: Connection timeout", style="red"
            )

            # Test get_payload_index_status - should now handle the exception properly
            status = self.client.get_payload_index_status(collection_name)

            # FIXED BEHAVIOR: Should return error status instead of false missing indexes
            self.assertIn(
                "error",
                status,
                "Status should contain error field when exception occurs",
            )
            self.assertFalse(
                status.get("healthy", True),
                "Status should be unhealthy when exception occurs",
            )

            # Should not contain false positive missing indexes
            self.assertNotIn(
                "missing_indexes",
                status,
                "Should not calculate missing indexes when error occurs",
            )
            self.assertNotIn(
                "total_indexes",
                status,
                "Should not calculate total indexes when error occurs",
            )

    def test_ensure_payload_indexes_query_context_with_exception(self):
        """Test that exceptions cause false missing index messages in query context."""
        collection_name = "test_collection"

        # Mock get_collection_info to throw an exception (simulating network/parsing issue)
        with patch.object(
            self.client,
            "get_collection_info",
            side_effect=RuntimeError("Qdrant API error"),
        ):

            # This should NOT print missing indexes message when there's an exception
            # Instead, it should handle the error gracefully
            result = self.client.ensure_payload_indexes(
                collection_name, context="query"
            )

            # Result should be False due to error, not True with false missing indexes
            self.assertFalse(
                result,
                "Should return False when exception occurs, not hide error with false positives",
            )

            # Check console output - should show error, not missing indexes
            printed_calls = [str(call) for call in self.console.print.call_args_list]

            # Should contain error message, not false positive missing indexes
            error_messages = [
                call for call in printed_calls if "Failed to list indexes" in call
            ]
            self.assertGreater(
                len(error_messages),
                0,
                f"Should show error message when exception occurs. Console calls: {printed_calls}",
            )

            # Should NOT contain false positive missing indexes message
            missing_messages = [
                call for call in printed_calls if "Missing payload indexes" in call
            ]
            self.assertEqual(
                len(missing_messages),
                0,
                f"Should not show false positive missing indexes when exception occurs. "
                f"Console calls: {printed_calls}",
            )

    def test_collection_not_found_still_returns_empty_list(self):
        """Test that collection not found errors still return empty list (expected behavior)."""
        collection_name = "nonexistent_collection"

        # Mock get_collection_info to throw collection not found error
        with patch.object(
            self.client,
            "get_collection_info",
            side_effect=RuntimeError("Collection not found"),
        ):

            # Should return empty list for collection not found (this is expected)
            existing_indexes = self.client.list_payload_indexes(collection_name)

            # Should return empty list, not raise exception
            self.assertEqual(
                len(existing_indexes),
                0,
                "Should return empty list when collection doesn't exist",
            )

            # Should still print error message
            self.console.print.assert_called_with(
                "Failed to list indexes: Collection not found", style="red"
            )


if __name__ == "__main__":
    unittest.main()
