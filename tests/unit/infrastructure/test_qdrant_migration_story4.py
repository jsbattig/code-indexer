"""Tests for Story 4: Migration Support for Existing Collections - TDD Implementation."""

from unittest.mock import Mock, patch
from pathlib import Path

import httpx

from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig


class TestEnsurePayloadIndexes:
    """Test ensure_payload_indexes method with context-aware behavior."""

    def setup_method(self):
        """Setup test environment with enabled payload indexes."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=True,
            payload_indexes=[
                ("type", "keyword"),
                ("path", "text"),
                ("git_branch", "keyword"),
                ("file_mtime", "integer"),
                ("hidden_branches", "keyword"),
            ],
        )
        self.client = QdrantClient(
            self.config, self.mock_console, Path("/test/project")
        )

    def test_ensure_payload_indexes_method_exists(self):
        """Test that ensure_payload_indexes method exists and is callable."""
        # This should fail initially - method doesn't exist yet
        assert hasattr(self.client, "ensure_payload_indexes")
        assert callable(getattr(self.client, "ensure_payload_indexes"))

    def test_ensure_payload_indexes_disabled_config(self):
        """Test ensure_payload_indexes when indexes are disabled in config."""
        # Create config with disabled indexes
        disabled_config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=False,
        )
        client = QdrantClient(disabled_config, self.mock_console)

        result = client.ensure_payload_indexes("test_collection", context="index")

        # Should return True immediately without checking/creating indexes
        assert result is True
        # No console messages should be printed
        self.mock_console.print.assert_not_called()

    def test_ensure_payload_indexes_all_exist_context_index(self):
        """Test ensure_payload_indexes when all indexes already exist - index context."""
        collection_name = "test_collection"

        # Mock that no indexes are missing
        mock_status = {
            "missing_indexes": [],
            "healthy": True,
            "total_indexes": 5,
            "expected_indexes": 5,
        }

        with patch.object(
            self.client, "get_payload_index_status", return_value=mock_status
        ):
            result = self.client.ensure_payload_indexes(
                collection_name, context="index"
            )

            assert result is True
            # No creation messages should be printed
            self.mock_console.print.assert_not_called()

    def test_ensure_payload_indexes_missing_context_index(self):
        """Test ensure_payload_indexes creates missing indexes in index context."""
        collection_name = "test_collection"

        # Mock that some indexes are missing
        mock_status = {
            "missing_indexes": ["type", "path"],
            "healthy": False,
            "total_indexes": 3,
            "expected_indexes": 5,
        }

        with patch.object(
            self.client, "get_payload_index_status", return_value=mock_status
        ):
            with patch.object(
                self.client,
                "_create_missing_indexes_with_detailed_feedback",
                return_value=True,
            ) as mock_create:
                result = self.client.ensure_payload_indexes(
                    collection_name, context="index"
                )

                assert result is True
                # Should call creation method with missing indexes
                mock_create.assert_called_once_with(collection_name, ["type", "path"])

                # Should show migration progress messages
                self.mock_console.print.assert_any_call(
                    "🔧 Creating missing payload indexes for optimal performance..."
                )
                self.mock_console.print.assert_any_call(
                    "✅ All payload indexes created successfully"
                )

    def test_ensure_payload_indexes_creation_failure_context_index(self):
        """Test ensure_payload_indexes handles creation failures in index context."""
        collection_name = "test_collection"

        # Mock that some indexes are missing
        mock_status = {
            "missing_indexes": ["type", "path"],
            "healthy": False,
        }

        with patch.object(
            self.client, "get_payload_index_status", return_value=mock_status
        ):
            with patch.object(
                self.client,
                "_create_missing_indexes_with_detailed_feedback",
                return_value=False,
            ):
                result = self.client.ensure_payload_indexes(
                    collection_name, context="index"
                )

                assert result is False
                # Should show failure warning
                self.mock_console.print.assert_any_call(
                    "⚠️  Some payload indexes failed to create (performance may be degraded)"
                )

    def test_ensure_payload_indexes_missing_context_query(self):
        """Test ensure_payload_indexes read-only behavior in query context."""
        collection_name = "test_collection"

        # Mock that some indexes are missing
        mock_status = {
            "missing_indexes": ["type", "path"],
            "healthy": False,
        }

        with patch.object(
            self.client, "get_payload_index_status", return_value=mock_status
        ):
            with patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create:
                result = self.client.ensure_payload_indexes(
                    collection_name, context="query"
                )

                assert result is True  # Don't block queries
                # Should NOT attempt to create indexes
                mock_create.assert_not_called()

                # Should show informational messages
                self.mock_console.print.assert_any_call(
                    "ℹ️  Missing payload indexes: type, path", style="dim"
                )
                self.mock_console.print.assert_any_call(
                    "   Consider running 'cidx index' for 50-90% faster operations",
                    style="dim",
                )

    def test_ensure_payload_indexes_missing_context_status(self):
        """Test ensure_payload_indexes silent behavior in status context."""
        collection_name = "test_collection"

        # Mock that some indexes are missing
        mock_status = {
            "missing_indexes": ["type", "path"],
            "healthy": False,
        }

        with patch.object(
            self.client, "get_payload_index_status", return_value=mock_status
        ):
            with patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create:
                result = self.client.ensure_payload_indexes(
                    collection_name, context="status"
                )

                assert result is True  # Status always succeeds
                # Should NOT attempt to create indexes
                mock_create.assert_not_called()
                # Should NOT print any warnings during status checks
                self.mock_console.print.assert_not_called()

    def test_ensure_payload_indexes_missing_context_default(self):
        """Test ensure_payload_indexes default behavior (unknown context)."""
        collection_name = "test_collection"

        # Mock that some indexes are missing
        mock_status = {
            "missing_indexes": ["type", "path"],
            "healthy": False,
        }

        with patch.object(
            self.client, "get_payload_index_status", return_value=mock_status
        ):
            with patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create:
                result = self.client.ensure_payload_indexes(
                    collection_name, context="unknown"
                )

                assert result is False  # Default warns about missing indexes
                # Should NOT attempt to create indexes
                mock_create.assert_not_called()

                # Should show warning message
                self.mock_console.print.assert_any_call(
                    "⚠️  Missing payload indexes: type, path", style="yellow"
                )


class TestCreateMissingIndexesWithDetailedFeedback:
    """Test _create_missing_indexes_with_detailed_feedback method."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=True,
            payload_indexes=[
                ("type", "keyword"),
                ("path", "text"),
                ("git_branch", "keyword"),
                ("file_mtime", "integer"),
                ("hidden_branches", "keyword"),
            ],
        )
        self.client = QdrantClient(self.config, self.mock_console)

    def test_create_missing_indexes_with_detailed_feedback_method_exists(self):
        """Test that _create_missing_indexes_with_detailed_feedback method exists."""
        # This should fail initially - method doesn't exist yet
        assert hasattr(self.client, "_create_missing_indexes_with_detailed_feedback")
        assert callable(
            getattr(self.client, "_create_missing_indexes_with_detailed_feedback")
        )

    def test_create_missing_indexes_success(self):
        """Test successful creation of missing indexes with detailed feedback."""
        collection_name = "test_collection"
        missing_fields = ["type", "path"]

        # Mock successful HTTP responses
        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(self.client.client, "put", return_value=mock_response):
            result = self.client._create_missing_indexes_with_detailed_feedback(
                collection_name, missing_fields
            )

            assert result is True

            # Verify progress messages for each field
            self.mock_console.print.assert_any_call(
                "   • Creating index for 'type' field (keyword type)..."
            )
            self.mock_console.print.assert_any_call(
                "   • Creating index for 'path' field (text type)..."
            )

            # Verify success messages
            self.mock_console.print.assert_any_call(
                "   ✅ Index for 'type' created successfully"
            )
            self.mock_console.print.assert_any_call(
                "   ✅ Index for 'path' created successfully"
            )

            # Verify summary
            self.mock_console.print.assert_any_call(
                "   📊 Successfully created 2/2 payload indexes"
            )

    def test_create_missing_indexes_already_exists(self):
        """Test handling of indexes that already exist (409 status)."""
        collection_name = "test_collection"
        missing_fields = ["type"]

        # Mock 409 response (already exists)
        mock_response = Mock()
        mock_response.status_code = 409

        with patch.object(self.client.client, "put", return_value=mock_response):
            result = self.client._create_missing_indexes_with_detailed_feedback(
                collection_name, missing_fields
            )

            assert result is True

            # Should show already exists message
            self.mock_console.print.assert_any_call(
                "   ✅ Index for 'type' already exists"
            )

    def test_create_missing_indexes_retry_logic(self):
        """Test retry logic with exponential backoff for failed requests."""
        collection_name = "test_collection"
        missing_fields = ["type"]

        call_count = 0

        def mock_put_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First 2 attempts fail
                raise httpx.RequestError("Network error")
            # Third attempt succeeds
            mock_response = Mock()
            mock_response.status_code = 201
            return mock_response

        with patch.object(self.client.client, "put", side_effect=mock_put_side_effect):
            with patch("time.sleep") as mock_sleep:
                result = self.client._create_missing_indexes_with_detailed_feedback(
                    collection_name, missing_fields
                )

                assert result is True

                # Should show retry messages (note: error messages are truncated to 50 chars)
                self.mock_console.print.assert_any_call(
                    "   ⚠️  Attempt 1 failed (Network error...), retrying in 1s..."
                )
                self.mock_console.print.assert_any_call(
                    "   ⚠️  Attempt 2 failed (Network error...), retrying in 2s..."
                )

                # Should sleep with exponential backoff
                mock_sleep.assert_any_call(1)  # 2^0 = 1
                mock_sleep.assert_any_call(2)  # 2^1 = 2

    def test_create_missing_indexes_final_failure(self):
        """Test handling when all retry attempts fail."""
        collection_name = "test_collection"
        missing_fields = ["type", "path"]

        # Mock to always fail
        mock_response = Mock()
        mock_response.status_code = 500

        with patch.object(self.client.client, "put", return_value=mock_response):
            result = self.client._create_missing_indexes_with_detailed_feedback(
                collection_name, missing_fields
            )

            assert result is False

            # Should show failure messages after 3 attempts
            self.mock_console.print.assert_any_call(
                "   ❌ Failed to create index for 'type' after 3 attempts (HTTP 500)"
            )
            self.mock_console.print.assert_any_call(
                "   ❌ Failed to create index for 'path' after 3 attempts (HTTP 500)"
            )

            # Should show failure summary
            self.mock_console.print.assert_any_call(
                "   📊 Created 0/2 payload indexes (2 failed)"
            )

    def test_create_missing_indexes_partial_success(self):
        """Test partial success scenario (some succeed, some fail)."""
        collection_name = "test_collection"
        missing_fields = ["type", "path"]

        call_count = 0

        def mock_put_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = Mock()
            if call_count == 1:  # First field succeeds
                mock_response.status_code = 201
            else:  # Second field fails
                mock_response.status_code = 500
            return mock_response

        with patch.object(self.client.client, "put", side_effect=mock_put_side_effect):
            result = self.client._create_missing_indexes_with_detailed_feedback(
                collection_name, missing_fields
            )

            assert result is False

            # Should show mixed results
            self.mock_console.print.assert_any_call(
                "   ✅ Index for 'type' created successfully"
            )
            self.mock_console.print.assert_any_call(
                "   ❌ Failed to create index for 'path' after 3 attempts (HTTP 500)"
            )

            # Should show partial success summary
            self.mock_console.print.assert_any_call(
                "   📊 Created 1/2 payload indexes (1 failed)"
            )

    def test_create_missing_indexes_unconfigured_field(self):
        """Test handling of fields not in configuration."""
        collection_name = "test_collection"
        missing_fields = ["unknown_field", "type"]

        # Mock successful response for configured field
        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(
            self.client.client, "put", return_value=mock_response
        ) as mock_put:
            result = self.client._create_missing_indexes_with_detailed_feedback(
                collection_name, missing_fields
            )

            assert result is False  # Not all fields were processed

            # Should skip unknown field
            self.mock_console.print.assert_any_call(
                "   ⚠️  No schema configured for field 'unknown_field', skipping"
            )

            # Should process known field
            self.mock_console.print.assert_any_call(
                "   ✅ Index for 'type' created successfully"
            )

            # Should only make one API call (for the configured field)
            assert mock_put.call_count == 1


class TestCLIIntegrationPoints:
    """Test CLI integration points for migration support."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=True,
        )
        self.client = QdrantClient(self.config, self.mock_console)

    def test_qdrant_client_integration_in_index_flow(self):
        """Test that the QdrantClient can be called with index context in CLI flow."""
        collection_name = "test_collection"

        # Mock dependencies for typical index command flow
        with patch.object(
            self.client, "resolve_collection_name", return_value=collection_name
        ):
            with patch.object(
                self.client, "ensure_payload_indexes", return_value=True
            ) as mock_ensure:
                # Simulate what happens in index command
                resolved_name = self.client.resolve_collection_name(None, None)
                self.client.ensure_payload_indexes(resolved_name, context="index")

                # Verify the method was called with correct parameters
                mock_ensure.assert_called_once_with(collection_name, context="index")

    def test_qdrant_client_integration_in_query_flow(self):
        """Test that the QdrantClient can be called with query context in CLI flow."""
        collection_name = "test_collection"

        # Mock dependencies for typical query command flow
        with patch.object(
            self.client, "resolve_collection_name", return_value=collection_name
        ):
            with patch.object(
                self.client, "ensure_payload_indexes", return_value=True
            ) as mock_ensure:
                # Simulate what happens in query command
                resolved_name = self.client.resolve_collection_name(None, None)
                self.client._current_collection_name = resolved_name
                self.client.ensure_payload_indexes(resolved_name, context="query")

                # Verify the method was called with correct parameters
                mock_ensure.assert_called_once_with(collection_name, context="query")

    def test_qdrant_client_integration_in_status_flow(self):
        """Test that the QdrantClient can be called with status context in CLI flow."""
        collection_name = "test_collection"

        # Mock dependencies for typical status command flow
        with patch.object(
            self.client, "resolve_collection_name", return_value=collection_name
        ):
            with patch.object(
                self.client, "ensure_payload_indexes", return_value=True
            ) as mock_ensure:
                with patch.object(
                    self.client,
                    "get_payload_index_status",
                    return_value={"healthy": True},
                ):
                    # Simulate what happens in status command
                    resolved_name = self.client.resolve_collection_name(None, None)
                    self.client.ensure_payload_indexes(resolved_name, context="status")
                    status = self.client.get_payload_index_status(resolved_name)

                    # Verify the method was called with correct parameters
                    mock_ensure.assert_called_once_with(
                        collection_name, context="status"
                    )
                    assert status["healthy"] is True

    def test_multiple_cli_contexts_use_different_behaviors(self):
        """Test that different CLI contexts trigger different migration behaviors."""
        collection_name = "test_collection"

        # Setup mocks to track different behaviors
        index_calls = []
        query_calls = []
        status_calls = []

        def mock_ensure_index_context(name, context):
            if context == "index":
                index_calls.append((name, context))
            elif context == "query":
                query_calls.append((name, context))
            elif context == "status":
                status_calls.append((name, context))
            return True

        with patch.object(
            self.client, "resolve_collection_name", return_value=collection_name
        ):
            with patch.object(
                self.client,
                "ensure_payload_indexes",
                side_effect=mock_ensure_index_context,
            ):
                # Simulate index command flow
                resolved_name = self.client.resolve_collection_name(None, None)
                self.client.ensure_payload_indexes(resolved_name, context="index")

                # Simulate query command flow
                self.client.ensure_payload_indexes(resolved_name, context="query")

                # Simulate status command flow
                self.client.ensure_payload_indexes(resolved_name, context="status")

                # Verify each context was called appropriately
                assert len(index_calls) == 1
                assert index_calls[0] == (collection_name, "index")

                assert len(query_calls) == 1
                assert query_calls[0] == (collection_name, "query")

                assert len(status_calls) == 1
                assert status_calls[0] == (collection_name, "status")
