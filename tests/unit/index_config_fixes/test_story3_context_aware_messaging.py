"""
Tests for Story 3: Context-Aware Messaging
Testing different messages for creation vs verification contexts.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from code_indexer.config import QdrantConfig
from code_indexer.services.qdrant import QdrantClient


class TestStory3ContextAwareMessaging:
    """Test context-aware messaging functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=True,
            payload_indexes=[
                ("type", "keyword"),
                ("path", "text"),
                ("git_branch", "keyword"),
                ("file_mtime", "integer"),
                ("hidden_branches", "keyword"),
                ("language", "keyword"),
                ("chunk_index", "integer"),
            ],
        )
        self.mock_console = Mock()
        self.client = QdrantClient(self.config, self.mock_console, Path("."))

    def test_collection_creation_context_shows_setup_message(self):
        """FAILING TEST: collection_creation context should show setup message."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {
                "missing_indexes": ["type", "path"],
                "healthy": False,
            }
            mock_create.return_value = True

            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is True

            # Should show setup message for collection creation
            self.mock_console.print.assert_any_call("🔧 Setting up payload indexes...")

    def test_index_verification_context_shows_verification_message_when_all_exist(self):
        """FAILING TEST: index_verification context should show verification message."""
        collection_name = "test_collection"

        with patch.object(self.client, "get_payload_index_status") as mock_status:
            mock_status.return_value = {
                "missing_indexes": [],  # All exist
                "healthy": True,
                "total_indexes": 7,
                "expected_indexes": 7,
            }

            result = self.client.ensure_payload_indexes(
                collection_name, context="index_verification"
            )

            assert result is True

            # Should show verification message, not setup message
            self.mock_console.print.assert_any_call("✅ Verified 7 existing indexes")

            # Should NOT show setup message
            setup_calls = [
                call
                for call in self.mock_console.print.call_args_list
                if "🔧 Setting up payload indexes" in str(call)
            ]
            assert len(setup_calls) == 0

    def test_index_verification_context_shows_creation_message_when_missing(self):
        """FAILING TEST: index_verification with missing indexes should show specific message."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {
                "missing_indexes": ["type", "path"],
                "healthy": False,
                "total_indexes": 5,
                "expected_indexes": 7,
            }
            mock_create.return_value = True

            result = self.client.ensure_payload_indexes(
                collection_name, context="index_verification"
            )

            assert result is True

            # Should show missing indexes creation message
            self.mock_console.print.assert_any_call("🔧 Creating 2 missing indexes...")

    def test_silent_context_shows_no_messages(self):
        """FAILING TEST: silent context should produce no console output."""
        collection_name = "test_collection"

        with patch.object(self.client, "get_payload_index_status") as mock_status:
            mock_status.return_value = {
                "missing_indexes": [],
                "healthy": True,
                "total_indexes": 7,
                "expected_indexes": 7,
            }

            result = self.client.ensure_payload_indexes(
                collection_name, context="silent"
            )

            assert result is True

            # Should make NO console prints in silent mode
            assert self.mock_console.print.call_count == 0

    def test_context_affects_success_messages(self):
        """FAILING TEST: Different contexts should show different success messages."""
        collection_name = "test_collection"

        # Test collection_creation context
        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {"missing_indexes": ["type"], "healthy": False}
            mock_create.return_value = True

            self.mock_console.reset_mock()
            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is True
            # Should show creation success
            self.mock_console.print.assert_any_call("✅ Created 1 index")

        # Test index_verification context
        with (
            patch.object(self.client, "get_payload_index_status") as mock_status2,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create2,
        ):

            mock_status2.return_value = {"missing_indexes": ["path"], "healthy": False}
            mock_create2.return_value = True

            self.mock_console.reset_mock()
            result = self.client.ensure_payload_indexes(
                collection_name, context="index_verification"
            )

            assert result is True
            # Should show verification-style success
            self.mock_console.print.assert_any_call("✅ Added 1 missing index")

    def test_context_affects_failure_messages(self):
        """FAILING TEST: Different contexts should show different failure messages."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {
                "missing_indexes": ["type", "path"],
                "healthy": False,
            }
            mock_create.return_value = False  # Creation failed

            # Test collection_creation context failure
            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is False
            # Should show setup failure message
            self.mock_console.print.assert_any_call(
                "⚠️ Failed to set up some payload indexes"
            )

    def test_legacy_direct_context_shows_traditional_message(self):
        """FAILING TEST: legacy_direct context should show traditional messages."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {"missing_indexes": ["type"], "healthy": False}
            mock_create.return_value = True

            result = self.client.ensure_payload_indexes(
                collection_name, context="legacy_direct"
            )

            assert result is True
            # Should show traditional message for backward compatibility
            self.mock_console.print.assert_any_call(
                "🔧 Setting up payload indexes for optimal query performance..."
            )

    def test_unknown_context_shows_default_message(self):
        """FAILING TEST: Unknown context should show default message."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {"missing_indexes": ["type"], "healthy": False}
            mock_create.return_value = True

            result = self.client.ensure_payload_indexes(
                collection_name, context="unknown_context"
            )

            assert result is True
            # Should show default message
            self.mock_console.print.assert_any_call("🔧 Managing payload indexes...")

    def test_message_format_includes_context_specific_details(self):
        """FAILING TEST: Messages should include context-specific details."""
        collection_name = "test_collection"

        with patch.object(self.client, "get_payload_index_status") as mock_status:
            # Test with 3 missing indexes
            mock_status.return_value = {
                "missing_indexes": ["type", "path", "git_branch"],
                "healthy": False,
                "total_indexes": 4,
                "expected_indexes": 7,
            }

            self.client.ensure_payload_indexes(
                collection_name, context="index_verification"
            )

            # Should include specific counts in message
            verification_calls = [
                call
                for call in self.mock_console.print.call_args_list
                if "Creating 3 missing indexes" in str(call)
            ]
            assert len(verification_calls) > 0

    def test_context_parameter_is_required(self):
        """FAILING TEST: context parameter should be required for ensure_payload_indexes."""
        collection_name = "test_collection"

        # Should fail without context parameter
        with pytest.raises(TypeError):
            self.client.ensure_payload_indexes(collection_name)
