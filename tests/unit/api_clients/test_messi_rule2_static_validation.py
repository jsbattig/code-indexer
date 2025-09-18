"""Static validation of Messi Rule #2 compliance in RemoteQueryClient."""

from pathlib import Path
from unittest import TestCase


class TestMessiRule2StaticValidation(TestCase):
    """Static code analysis to ensure Messi Rule #2 compliance."""

    def test_no_unsafe_cast_usage(self):
        """Verify no unsafe cast() is used in remote_query_client.py."""
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src/code_indexer/api_clients/remote_query_client.py"
        )
        content = source_file.read_text()

        # Should not have any cast() calls
        self.assertNotIn(
            "cast(", content, "Found unsafe cast() usage in remote_query_client.py"
        )
        self.assertNotIn(
            "from typing import", "cast", "cast import found but should be removed"
        )

    def test_no_fallback_statistics(self):
        """Verify no fake statistics fallback exists."""
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src/code_indexer/api_clients/remote_query_client.py"
        )
        content = source_file.read_text()

        # Should not have fallback statistics
        self.assertNotIn('"total_files": 0', content, "Found fake fallback statistics")
        self.assertNotIn(
            '"indexed_files": 0', content, "Found fake fallback statistics"
        )
        self.assertNotIn(
            '"embeddings_count": 0', content, "Found fake fallback statistics"
        )

        # Should have proper error handling instead
        self.assertIn(
            "statistics not available",
            content.lower(),
            "Missing proper error for missing statistics",
        )
        self.assertIn(
            "isinstance(stats, dict)", content, "Missing type validation for statistics"
        )

    def test_proper_error_handling_exists(self):
        """Verify proper error handling for missing/invalid statistics."""
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src/code_indexer/api_clients/remote_query_client.py"
        )
        content = source_file.read_text()

        # Check for Messi Rule #2 compliance comment
        self.assertIn(
            "MESSI RULE #2 COMPLIANCE",
            content,
            "Missing Messi Rule #2 compliance comment",
        )

        # Should raise errors for missing statistics
        self.assertIn('if "statistics" not in repository_data:', content)
        self.assertIn("raise RepositoryAccessError", content)

        # Should validate statistics type
        self.assertIn("if not isinstance(stats, dict):", content)
        self.assertIn("raise ValueError", content)

    def test_error_messages_are_informative(self):
        """Verify error messages provide actionable information."""
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src/code_indexer/api_clients/remote_query_client.py"
        )
        content = source_file.read_text()

        # Check for informative error messages
        self.assertIn(
            "may not be fully indexed yet",
            content.lower(),
            "Missing helpful context in error message",
        )
        self.assertIn(
            "invalid statistics format", content.lower(), "Missing format error message"
        )
        self.assertIn(
            "expected dict, got", content.lower(), "Missing type information in error"
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
