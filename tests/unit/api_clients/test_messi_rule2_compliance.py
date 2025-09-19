"""Test Messi Rule #2 (Anti-Fallback) Compliance for Remote Query Client.

This test ensures that the RemoteQueryClient adheres to Messi Rule #2:
- No fallbacks with fake data
- Graceful failure with clear error messages
- No unsafe type casting
"""

import asyncio
from pathlib import Path
from unittest import TestCase

from src.code_indexer.api_clients.remote_query_client import (
    RemoteQueryClient,
    RepositoryAccessError,
)
from tests.unit.api_clients.test_isolation_utils import MockIsolationManager


class TestMessiRule2Compliance(TestCase):
    """Test that RemoteQueryClient follows Anti-Fallback Principle."""

    def setUp(self):
        """Set up isolated test environment."""
        self.isolation = MockIsolationManager()
        self.server_config = self.isolation.start_test_server()
        credentials = {
            "username": "test_user",
            "password": "Test123!Pass",
            "server_url": f"http://localhost:{self.server_config['port']}",
        }
        self.client = RemoteQueryClient(
            server_url=f"http://localhost:{self.server_config['port']}",
            credentials=credentials,
        )

    def tearDown(self):
        """Clean up test environment."""
        if hasattr(self, "client"):
            asyncio.run(self.client.close())
        if hasattr(self, "isolation"):
            self.isolation.cleanup()

    def test_no_fake_statistics_fallback(self):
        """Test that missing statistics raise error instead of returning fake data."""

        # Simulate a response without statistics field
        async def test_missing_stats():
            # Mock a response without statistics
            self.isolation.mock_server_response(
                "/api/repositories/test-repo",
                {"name": "test-repo", "path": "/path/to/repo"},
                status_code=200,
            )

            # Should raise error, not return fake data
            with self.assertRaises(RepositoryAccessError) as ctx:
                await self.client.get_repository_statistics("test-repo")

            # Verify error message is helpful
            error_msg = str(ctx.exception)
            self.assertIn("statistics not available", error_msg.lower())
            self.assertIn("test-repo", error_msg)

        asyncio.run(test_missing_stats())

    def test_invalid_statistics_format_error(self):
        """Test that invalid statistics format raises proper error."""

        async def test_invalid_stats():
            # Mock a response with invalid statistics type
            self.isolation.mock_server_response(
                "/api/repositories/test-repo",
                {"name": "test-repo", "statistics": "invalid_string_not_dict"},
                status_code=200,
            )

            # Should raise error about invalid format
            with self.assertRaises(ValueError) as ctx:
                await self.client.get_repository_statistics("test-repo")

            # Verify error message is helpful
            error_msg = str(ctx.exception)
            self.assertIn("invalid statistics format", error_msg.lower())
            self.assertIn("expected dict", error_msg.lower())
            self.assertIn("got str", error_msg.lower())

        asyncio.run(test_invalid_stats())

    def test_valid_statistics_returned_correctly(self):
        """Test that valid statistics are returned without modification."""

        async def test_valid_stats():
            expected_stats = {
                "total_files": 42,
                "indexed_files": 40,
                "total_size_bytes": 1024000,
                "embeddings_count": 500,
                "languages": ["python", "javascript"],
            }

            # Mock a response with valid statistics
            self.isolation.mock_server_response(
                "/api/repositories/test-repo",
                {"name": "test-repo", "statistics": expected_stats},
                status_code=200,
            )

            # Should return exact statistics
            stats = await self.client.get_repository_statistics("test-repo")
            self.assertEqual(stats, expected_stats)

        asyncio.run(test_valid_stats())

    def test_no_cast_without_validation(self):
        """Test that no unsafe cast() is used in the codebase."""
        # Read the source file to verify no unsafe casts
        source_file = (
            Path(__file__).parent.parent.parent.parent
            / "src/code_indexer/api_clients/remote_query_client.py"
        )
        content = source_file.read_text()

        # Should not have any cast() calls
        self.assertNotIn(
            "cast(", content, "Found unsafe cast() usage in remote_query_client.py"
        )

        # Verify we validate before returning
        self.assertIn(
            "isinstance(stats, dict)", content, "Missing type validation for statistics"
        )

    def test_error_messages_are_actionable(self):
        """Test that error messages provide actionable information."""

        async def test_error_messages():
            # Test 404 error
            self.isolation.mock_server_response(
                "/api/repositories/nonexistent",
                {"detail": "Repository not found"},
                status_code=404,
            )

            with self.assertRaises(RepositoryAccessError) as ctx:
                await self.client.get_repository_statistics("nonexistent")

            error_msg = str(ctx.exception)
            self.assertIn("not found", error_msg.lower())

            # Test 403 error
            self.isolation.mock_server_response(
                "/api/repositories/forbidden",
                {"detail": "Access denied"},
                status_code=403,
            )

            with self.assertRaises(RepositoryAccessError) as ctx:
                await self.client.get_repository_statistics("forbidden")

            error_msg = str(ctx.exception)
            self.assertIn("access denied", error_msg.lower())

        asyncio.run(test_error_messages())


if __name__ == "__main__":
    import unittest

    unittest.main()
