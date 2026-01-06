"""
Integration tests for Universal Timestamp Collection end-to-end workflow.

Tests the complete integration from FileChunkingManager through metadata schema
to query result models, ensuring timestamps flow correctly through the system.

Following TDD methodology: These tests verify the complete working functionality.
"""

import time
import tempfile
from pathlib import Path
from unittest.mock import Mock
import pytest

from code_indexer.services.file_chunking_manager import FileChunkingManager
from code_indexer.services.metadata_schema import GitAwareMetadataSchema
from code_indexer.server.models.api_models import SearchResultItem
from code_indexer.server.app import QueryResultItem
from code_indexer.search.query import SearchResult


@pytest.mark.integration
class TestTimestampIntegrationWorkflow:
    """Test end-to-end timestamp integration workflow."""

    @pytest.fixture
    def test_file_with_timestamps(self):
        """Create a test file with known timestamps for integration testing."""
        import os

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("def integration_test():\n    return 'timestamp_integration'\n")
            f.flush()

            # Set specific mtime for testing
            file_path = Path(f.name)
            test_mtime = 1641081600.0  # January 2, 2022
            os.utime(file_path, (test_mtime, test_mtime))

            yield file_path, test_mtime

            # Cleanup
            file_path.unlink(missing_ok=True)

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for integration testing."""
        mock_vector_manager = Mock()
        mock_vector_manager.embedding_provider = Mock()
        mock_vector_manager.embedding_provider.get_current_model.return_value = (
            "voyage-2"
        )
        mock_vector_manager.embedding_provider._get_model_token_limit.return_value = (
            120000
        )

        # Mock successful batch processing
        batch_result = Mock()
        batch_result.error = None
        batch_result.embeddings = [[0.1, 0.2, 0.3]]  # Single embedding
        mock_future = Mock()
        mock_future.result.return_value = batch_result
        mock_vector_manager.submit_batch_task.return_value = mock_future

        mock_chunker = Mock()
        mock_chunker.chunk_file.return_value = [
            {
                "text": "def integration_test():",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 1,
                "file_extension": "py",
            }
        ]

        mock_filesystem_client = Mock()
        mock_filesystem_client.upsert_points.return_value = True

        mock_slot_tracker = Mock()
        mock_slot_tracker.acquire_slot.return_value = "integration-slot"
        mock_slot_tracker.get_concurrent_files_data.return_value = {}

        return {
            "vector_manager": mock_vector_manager,
            "chunker": mock_chunker,
            "filesystem_client": mock_filesystem_client,
            "slot_tracker": mock_slot_tracker,
        }

    def test_end_to_end_timestamp_workflow_file_to_filesystem(
        self, test_file_with_timestamps, mock_dependencies
    ):
        """
        Test complete workflow from file processing to Filesystem point creation.

        Verifies timestamps are collected and flow through entire system.
        """
        file_path, expected_mtime = test_file_with_timestamps
        start_time = time.time()

        with FileChunkingManager(
            mock_dependencies["vector_manager"],
            mock_dependencies["chunker"],
            mock_dependencies["filesystem_client"],
            4,
            mock_dependencies["slot_tracker"],
            codebase_dir=file_path.parent,
        ) as manager:
            metadata = {
                "project_id": "integration-test-project",
                "file_hash": "integration-hash",
                "git_available": False,
                "collection_name": "integration-collection",
            }

            # Process file through complete lifecycle
            result = manager._process_file_clean_lifecycle(
                file_path, metadata, None, mock_dependencies["slot_tracker"]
            )

            assert result.success
            assert result.chunks_processed == 1

            # Verify upsert_points was called with timestamps
            mock_dependencies["filesystem_client"].upsert_points.assert_called_once()
            call_args = mock_dependencies["filesystem_client"].upsert_points.call_args[
                1
            ]
            points = call_args["points"]

            assert len(points) == 1
            payload = points[0]["payload"]

            # Verify universal timestamp fields are present
            assert "file_last_modified" in payload
            assert payload["file_last_modified"] == expected_mtime

            assert "indexed_timestamp" in payload
            indexed_time = payload["indexed_timestamp"]
            assert start_time <= indexed_time <= time.time()

            # Verify backward compatibility - existing fields preserved
            assert payload["path"] == str(file_path)
            assert payload["content"] == "def integration_test():"
            assert payload["language"] == "py"
            assert payload["project_id"] == "integration-test-project"

    def test_metadata_schema_integration_with_universal_timestamps(
        self, test_file_with_timestamps
    ):
        """
        Test metadata schema integration includes universal timestamp fields.

        Verifies schema validation works with new timestamp fields.
        """
        file_path, expected_mtime = test_file_with_timestamps
        indexed_time = time.time()

        # Create metadata with universal timestamps
        metadata = {
            "path": str(file_path),
            "content": "def integration_test():",
            "language": "python",
            "file_size": file_path.stat().st_size,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2022-01-02T12:00:00Z",
            "project_id": "schema-integration-test",
            "file_hash": "schema-hash",
            "git_available": False,
            "schema_version": "2.0",
            "type": "content",
            "file_last_modified": expected_mtime,
            "indexed_timestamp": indexed_time,
        }

        # Validate metadata schema accepts universal timestamps
        validation_result = GitAwareMetadataSchema.validate_metadata(metadata)

        assert len(validation_result["errors"]) == 0
        assert "file_last_modified" not in str(validation_result.get("warnings", []))
        assert "indexed_timestamp" not in str(validation_result.get("warnings", []))

    def test_query_result_models_integration_with_timestamp_data(
        self, test_file_with_timestamps
    ):
        """
        Test query result models correctly handle timestamp data from payloads.

        Verifies SearchResultItem and QueryResultItem work with timestamp data.
        """
        file_path, expected_mtime = test_file_with_timestamps
        indexed_time = time.time()

        # Test SearchResultItem with timestamp data
        search_data = {
            "score": 0.95,
            "file_path": str(file_path),
            "line_start": 1,
            "line_end": 1,
            "content": "def integration_test():",
            "language": "python",
            "file_last_modified": expected_mtime,
            "indexed_timestamp": indexed_time,
        }

        search_item = SearchResultItem(**search_data)
        assert search_item.file_last_modified == expected_mtime
        assert search_item.indexed_timestamp == indexed_time

        # Test QueryResultItem with timestamp data
        query_data = {
            "file_path": str(file_path),
            "line_number": 1,
            "code_snippet": "def integration_test():",
            "similarity_score": 0.95,
            "repository_alias": "integration-repo",
            "file_last_modified": expected_mtime,
            "indexed_timestamp": indexed_time,
        }

        query_item = QueryResultItem(**query_data)
        assert query_item.file_last_modified == expected_mtime
        assert query_item.indexed_timestamp == indexed_time

    def test_legacy_searchresult_compatibility_with_universal_timestamps(
        self, test_file_with_timestamps
    ):
        """
        Test legacy SearchResult class compatibility with new timestamp fields.

        Verifies existing SearchResult.from_backend_result still works.
        """
        file_path, expected_mtime = test_file_with_timestamps
        indexed_time = time.time()

        # Simulate backend result with universal timestamp fields
        backend_result = {
            "score": 0.88,
            "payload": {
                "path": str(file_path),
                "content": "def integration_test():",
                "language": "python",
                "file_size": 50,
                "chunk_index": 0,
                "total_chunks": 1,
                "indexed_at": "2022-01-02T12:00:00Z",
                "file_last_modified": expected_mtime,
                "indexed_timestamp": indexed_time,
            },
        }

        # Test SearchResult can handle enhanced payload
        search_result = SearchResult.from_backend_result(backend_result)

        # Verify existing fields work
        assert search_result.file_path == str(file_path)
        assert search_result.content == "def integration_test():"
        assert search_result.language == "python"
        assert search_result.score == 0.88

        # New timestamp fields don't break existing functionality
        assert search_result.indexed_at == "2022-01-02T12:00:00Z"

    def test_git_and_non_git_projects_both_collect_universal_timestamps(
        self, test_file_with_timestamps, mock_dependencies
    ):
        """
        Test that both git and non-git projects collect universal timestamps.

        Verifies universal collection works regardless of git status.
        """
        file_path, expected_mtime = test_file_with_timestamps

        with FileChunkingManager(
            mock_dependencies["vector_manager"],
            mock_dependencies["chunker"],
            mock_dependencies["filesystem_client"],
            4,
            mock_dependencies["slot_tracker"],
            codebase_dir=file_path.parent,
        ) as manager:
            chunk = {
                "text": "universal timestamps",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 1,
                "file_extension": "py",
            }
            embedding = [0.1, 0.2, 0.3]

            # Test non-git project
            non_git_metadata = {
                "project_id": "non-git-project",
                "file_hash": "non-git-hash",
                "git_available": False,
            }

            non_git_point = manager._create_filesystem_point(
                chunk, embedding, non_git_metadata, file_path
            )

            # Test git project
            git_metadata = {
                "project_id": "git-project",
                "file_hash": "git-hash",
                "git_available": True,
                "commit_hash": "abc123def456",
                "branch": "main",
            }

            git_point = manager._create_filesystem_point(
                chunk, embedding, git_metadata, file_path
            )

            # Both should have universal timestamps
            for point, project_type in [(non_git_point, "non-git"), (git_point, "git")]:
                payload = point["payload"]

                assert (
                    "file_last_modified" in payload
                ), f"{project_type} missing file_last_modified"
                assert payload["file_last_modified"] == expected_mtime

                assert (
                    "indexed_timestamp" in payload
                ), f"{project_type} missing indexed_timestamp"
                assert isinstance(payload["indexed_timestamp"], float)

    def test_timestamp_collection_performance_acceptable_in_integration(
        self, mock_dependencies, tmp_path
    ):
        """
        Test that timestamp collection doesn't significantly impact performance.

        Measures performance of processing multiple files with timestamp collection.
        """
        # Create multiple test files
        test_files = []
        try:
            for i in range(10):
                with tempfile.NamedTemporaryFile(
                    mode="w", delete=False, suffix=".py"
                ) as f:
                    f.write(f"def test_function_{i}():\n    return {i}\n")
                    test_files.append(Path(f.name))

            with FileChunkingManager(
                mock_dependencies["vector_manager"],
                mock_dependencies["chunker"],
                mock_dependencies["filesystem_client"],
                4,
                mock_dependencies["slot_tracker"],
                codebase_dir=tmp_path,
            ) as manager:
                chunk = {
                    "text": "performance test",
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "line_start": 1,
                    "line_end": 1,
                    "file_extension": "py",
                }
                embedding = [0.1, 0.2, 0.3]
                metadata = {
                    "project_id": "performance-test",
                    "file_hash": "perf-hash",
                    "git_available": False,
                }

                # Measure time for processing multiple files
                start_time = time.time()

                for file_path in test_files:
                    point = manager._create_filesystem_point(
                        chunk, embedding, metadata, file_path
                    )
                    # Verify timestamp collection worked
                    assert "file_last_modified" in point["payload"]
                    assert "indexed_timestamp" in point["payload"]

                total_time = time.time() - start_time

                # Performance should be acceptable - less than 1 second for 10 files
                assert (
                    total_time < 1.0
                ), f"Timestamp collection too slow: {total_time}s for 10 files"

        finally:
            # Cleanup test files
            for file_path in test_files:
                file_path.unlink(missing_ok=True)

    def test_error_handling_integration_preserves_indexing_workflow(
        self, mock_dependencies, tmp_path
    ):
        """
        Test that timestamp collection errors don't break the indexing workflow.

        Verifies graceful error handling in integration context.
        """
        # Use non-existent file to trigger stat() errors
        non_existent_file = Path("/tmp/nonexistent_integration_test.py")

        with FileChunkingManager(
            mock_dependencies["vector_manager"],
            mock_dependencies["chunker"],
            mock_dependencies["filesystem_client"],
            4,
            mock_dependencies["slot_tracker"],
            codebase_dir=tmp_path,
        ) as manager:
            chunk = {
                "text": "error handling test",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 1,
                "file_extension": "py",
            }
            embedding = [0.1, 0.2, 0.3]
            metadata = {
                "project_id": "error-test",
                "file_hash": "error-hash",
                "git_available": False,
                "file_size": 100,  # Provide fallback size
            }

            # Should handle error gracefully and continue processing
            point = manager._create_filesystem_point(
                chunk, embedding, metadata, non_existent_file
            )

            # Verify point was created despite stat() error
            assert point is not None
            payload = point["payload"]

            # file_last_modified should be None due to error
            assert "file_last_modified" in payload
            assert payload["file_last_modified"] is None

            # indexed_timestamp should still work
            assert "indexed_timestamp" in payload
            assert isinstance(payload["indexed_timestamp"], float)

            # Other fields should be preserved
            assert payload["content"] == "error handling test"
            assert payload["project_id"] == "error-test"
