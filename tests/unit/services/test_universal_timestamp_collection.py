"""
Unit tests for Universal Timestamp Collection in FileChunkingManager.

Tests the core requirement: collect file_last_modified timestamp for every file during indexing
regardless of git status, and include indexed_timestamp for when indexing occurred.

Following TDD methodology: These tests MUST FAIL initially, then be made to pass.
"""

import time
import tempfile
from pathlib import Path
from unittest.mock import Mock
from dataclasses import dataclass
from typing import Optional
import pytest

from code_indexer.services.file_chunking_manager import FileChunkingManager


@dataclass
class MockChunk:
    """Mock chunk data structure for testing."""

    text: str
    chunk_index: int
    total_chunks: int
    line_start: Optional[int] = None
    line_end: Optional[int] = None


class TestUniversalTimestampCollection:
    """Test universal timestamp collection during file processing."""

    @pytest.fixture
    def mock_vector_manager(self):
        """Mock VectorCalculationManager for tests."""
        mock = Mock()
        mock.embedding_provider = Mock()
        mock.embedding_provider.get_current_model.return_value = "voyage-2"
        mock.embedding_provider._get_model_token_limit.return_value = 120000
        mock.submit_batch_task.return_value = Mock()
        return mock

    @pytest.fixture
    def mock_chunker(self):
        """Mock FixedSizeChunker for tests."""
        mock = Mock()
        return mock

    @pytest.fixture
    def mock_filesystem_client(self):
        """Mock Filesystem client for tests."""
        mock = Mock()
        mock.upsert_points.return_value = True
        return mock

    @pytest.fixture
    def mock_slot_tracker(self):
        """Mock CleanSlotTracker for tests."""
        mock = Mock()
        mock.acquire_slot.return_value = "slot-1"
        mock.get_concurrent_files_data.return_value = {}
        return mock

    @pytest.fixture
    def test_file(self):
        """Create a temporary test file with known mtime."""
        import os

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("def test_function():\n    return 'test'\n")
            f.flush()

            # Set specific mtime for testing
            file_path = Path(f.name)
            test_mtime = 1640995200.0  # January 1, 2022
            os.utime(file_path, (test_mtime, test_mtime))  # (access_time, modify_time)

            yield file_path, test_mtime

            # Cleanup
            file_path.unlink(missing_ok=True)

    def test_create_filesystem_point_includes_file_last_modified_timestamp(
        self,
        mock_vector_manager,
        mock_chunker,
        mock_filesystem_client,
        mock_slot_tracker,
        test_file,
    ):
        """
        Test that _create_filesystem_point includes file_last_modified timestamp.

        This test MUST FAIL initially because the field doesn't exist yet.
        """
        file_path, expected_mtime = test_file

        with FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_filesystem_client,
            4,
            mock_slot_tracker,
            codebase_dir=file_path.parent,
        ) as manager:

            chunk = {
                "text": "test content",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 2,
                "file_extension": "py",
            }

            embedding = [0.1, 0.2, 0.3]
            metadata = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": False,
            }

            # This should collect file mtime and add to payload
            point = manager._create_filesystem_point(
                chunk, embedding, metadata, file_path
            )

            # MUST FAIL: file_last_modified field doesn't exist yet
            assert "file_last_modified" in point["payload"]
            assert point["payload"]["file_last_modified"] == expected_mtime

    def test_create_filesystem_point_includes_indexed_timestamp(
        self,
        mock_vector_manager,
        mock_chunker,
        mock_filesystem_client,
        mock_slot_tracker,
        test_file,
    ):
        """
        Test that _create_filesystem_point includes indexed_timestamp.

        This test MUST FAIL initially because the field doesn't exist yet.
        """
        file_path, _ = test_file
        start_time = time.time()

        with FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_filesystem_client,
            4,
            mock_slot_tracker,
            codebase_dir=file_path.parent,
        ) as manager:

            chunk = {
                "text": "test content",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 2,
                "file_extension": "py",
            }

            embedding = [0.1, 0.2, 0.3]
            metadata = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": False,
            }

            point = manager._create_filesystem_point(
                chunk, embedding, metadata, file_path
            )
            end_time = time.time()

            # MUST FAIL: indexed_timestamp field doesn't exist yet
            assert "indexed_timestamp" in point["payload"]
            indexed_time = point["payload"]["indexed_timestamp"]
            assert start_time <= indexed_time <= end_time

    def test_timestamp_collection_works_for_git_projects(
        self,
        mock_vector_manager,
        mock_chunker,
        mock_filesystem_client,
        mock_slot_tracker,
        test_file,
    ):
        """
        Test timestamp collection for git-enabled projects.

        Universal timestamp collection should work regardless of git status.
        """
        file_path, expected_mtime = test_file

        with FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_filesystem_client,
            4,
            mock_slot_tracker,
            codebase_dir=file_path.parent,
        ) as manager:

            chunk = {
                "text": "test content",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 2,
                "file_extension": "py",
            }

            embedding = [0.1, 0.2, 0.3]
            metadata = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": True,
                "commit_hash": "abc123",
                "branch": "main",
            }

            point = manager._create_filesystem_point(
                chunk, embedding, metadata, file_path
            )

            # MUST FAIL: Universal timestamp fields don't exist yet
            assert "file_last_modified" in point["payload"]
            assert point["payload"]["file_last_modified"] == expected_mtime
            assert "indexed_timestamp" in point["payload"]
            assert isinstance(point["payload"]["indexed_timestamp"], float)

    def test_timestamp_collection_handles_permission_errors_gracefully(
        self,
        mock_vector_manager,
        mock_chunker,
        mock_filesystem_client,
        mock_slot_tracker,
    ):
        """
        Test that permission errors during stat() don't break indexing.

        When file.stat() fails, set timestamp to None and continue processing.
        """
        # Create a mock file path that will cause stat() to fail
        file_path = Path("/nonexistent/permission_denied.py")

        with FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_filesystem_client,
            4,
            mock_slot_tracker,
            codebase_dir=file_path.parent,
        ) as manager:

            chunk = {
                "text": "test content",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 2,
                "file_extension": "py",
            }

            embedding = [0.1, 0.2, 0.3]
            metadata = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": False,
            }

            # Should handle stat() failure gracefully
            point = manager._create_filesystem_point(
                chunk, embedding, metadata, file_path
            )

            # MUST FAIL: Error handling doesn't exist yet
            assert "file_last_modified" in point["payload"]
            assert point["payload"]["file_last_modified"] is None  # Failed to get mtime
            assert "indexed_timestamp" in point["payload"]
            assert isinstance(point["payload"]["indexed_timestamp"], float)

    def test_process_file_includes_timestamps_in_all_chunks(
        self,
        mock_vector_manager,
        mock_chunker,
        mock_filesystem_client,
        mock_slot_tracker,
        test_file,
    ):
        """
        Test that file processing includes timestamps in ALL chunk payloads.

        Every chunk from a file should have the same file_last_modified
        but individual indexed_timestamp values.
        """
        file_path, expected_mtime = test_file

        # Mock chunker to return multiple chunks
        mock_chunks = [
            MockChunk("chunk 1", 0, 2, 1, 1),
            MockChunk("chunk 2", 1, 2, 2, 2),
        ]
        mock_chunker.chunk_file.return_value = [
            {
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "file_extension": "py",
            }
            for chunk in mock_chunks
        ]

        # Mock successful batch processing
        batch_result = Mock()
        batch_result.error = None
        batch_result.embeddings = [[0.1, 0.2], [0.3, 0.4]]  # Two embeddings
        mock_future = Mock()
        mock_future.result.return_value = batch_result
        mock_vector_manager.submit_batch_task.return_value = mock_future

        with FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_filesystem_client,
            4,
            mock_slot_tracker,
            codebase_dir=file_path.parent,
        ) as manager:

            metadata = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": False,
                "collection_name": "test-collection",
            }

            result = manager._process_file_clean_lifecycle(
                file_path, metadata, None, mock_slot_tracker
            )

            assert result.success

            # Verify upsert_points was called with timestamps in all chunks
            mock_filesystem_client.upsert_points.assert_called_once()
            call_args = mock_filesystem_client.upsert_points.call_args[1]
            points = call_args["points"]

            # MUST FAIL: Timestamp fields don't exist in payloads yet
            assert len(points) == 2
            for point in points:
                payload = point["payload"]
                assert "file_last_modified" in payload
                assert payload["file_last_modified"] == expected_mtime
                assert "indexed_timestamp" in payload
                assert isinstance(payload["indexed_timestamp"], float)

    def test_timestamp_collection_works_with_symbolic_links(
        self,
        mock_vector_manager,
        mock_chunker,
        mock_filesystem_client,
        mock_slot_tracker,
        test_file,
    ):
        """
        Test timestamp collection resolves symbolic links correctly.

        Should get target file timestamp, not link timestamp.
        """
        target_file, target_mtime = test_file

        # Create symbolic link to target file
        with tempfile.TemporaryDirectory() as temp_dir:
            link_path = Path(temp_dir) / "link.py"
            link_path.symlink_to(target_file)

            with FileChunkingManager(
                mock_vector_manager,
                mock_chunker,
                mock_filesystem_client,
                4,
                mock_slot_tracker,
                codebase_dir=Path(temp_dir),
            ) as manager:

                chunk = {
                    "text": "test content",
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "line_start": 1,
                    "line_end": 1,
                    "file_extension": "py",
                }

                embedding = [0.1, 0.2, 0.3]
                metadata = {
                    "project_id": "test-project",
                    "file_hash": "test-hash",
                    "git_available": False,
                }

                point = manager._create_filesystem_point(
                    chunk, embedding, metadata, link_path
                )

                # MUST FAIL: Symbolic link handling doesn't exist yet
                assert "file_last_modified" in point["payload"]
                # Should resolve to target file's mtime, not link mtime
                assert point["payload"]["file_last_modified"] == target_mtime

    def test_backward_compatibility_with_existing_metadata(
        self,
        mock_vector_manager,
        mock_chunker,
        mock_filesystem_client,
        mock_slot_tracker,
        test_file,
    ):
        """
        Test that adding timestamp fields doesn't break existing metadata.

        New timestamp fields should be added alongside existing metadata fields.
        """
        file_path, expected_mtime = test_file

        with FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_filesystem_client,
            4,
            mock_slot_tracker,
            codebase_dir=file_path.parent,
        ) as manager:

            chunk = {
                "text": "test content",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 2,
                "file_extension": "py",
            }

            embedding = [0.1, 0.2, 0.3]
            metadata = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": True,
                "commit_hash": "abc123def456",
                "branch": "feature-branch",
                "git_hash": "blob123",
            }

            point = manager._create_filesystem_point(
                chunk, embedding, metadata, file_path
            )
            payload = point["payload"]

            # MUST FAIL: New timestamp fields don't exist yet
            # Verify existing fields are preserved
            assert payload["project_id"] == "test-project"
            assert payload["file_hash"] == "test-hash"
            assert payload["git_commit_hash"] == "abc123def456"
            assert payload["git_branch"] == "feature-branch"

            # Verify new timestamp fields are added
            assert "file_last_modified" in payload
            assert payload["file_last_modified"] == expected_mtime
            assert "indexed_timestamp" in payload
            assert isinstance(payload["indexed_timestamp"], float)

    def test_performance_impact_is_minimal(
        self,
        mock_vector_manager,
        mock_chunker,
        mock_filesystem_client,
        mock_slot_tracker,
        test_file,
    ):
        """
        Test that timestamp collection has minimal performance impact.

        file.stat() calls should be fast and not significantly slow indexing.
        """
        file_path, _ = test_file

        with FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_filesystem_client,
            4,
            mock_slot_tracker,
            codebase_dir=file_path.parent,
        ) as manager:

            chunk = {
                "text": "test content",
                "chunk_index": 0,
                "total_chunks": 1,
                "line_start": 1,
                "line_end": 1,
                "file_extension": "py",
            }

            embedding = [0.1, 0.2, 0.3]
            metadata = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": False,
            }

            # Measure time for multiple timestamp collections
            start_time = time.time()
            for _ in range(100):
                point = manager._create_filesystem_point(
                    chunk, embedding, metadata, file_path
                )
                # MUST FAIL: Timestamp fields don't exist yet
                assert "file_last_modified" in point["payload"]
                assert "indexed_timestamp" in point["payload"]

            total_time = time.time() - start_time

            # Should be very fast - less than 1 second for 100 operations
            assert (
                total_time < 1.0
            ), f"Timestamp collection too slow: {total_time}s for 100 operations"
