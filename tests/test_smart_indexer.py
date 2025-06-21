"""Tests for smart indexer functionality."""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.services.progressive_metadata import ProgressiveMetadata
from code_indexer.indexing.processor import ProcessingStats
from code_indexer.services.branch_aware_indexer import BranchIndexingResult


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    # Use a real temporary directory that can be created
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Mock(spec=Config)
        config.exclude_dirs = ["node_modules", ".git"]
        config.file_extensions = ["py", "js", "ts"]
        config.codebase_dir = Path(tmpdir)

        # Mock the indexing sub-config
        indexing_config = Mock()
        indexing_config.chunk_size = 1000
        indexing_config.chunk_overlap = 100
        indexing_config.max_file_size = 1000000
        config.indexing = indexing_config

        yield config


@pytest.fixture
def mock_embedding_provider():
    """Create a mock embedding provider."""
    provider = Mock()
    provider.get_provider_name.return_value = "test-provider"
    provider.get_current_model.return_value = "test-model"
    provider.get_embedding.return_value = [0.1, 0.2, 0.3]
    return provider


@pytest.fixture
def mock_qdrant_client():
    """Create a mock Qdrant client."""
    client = Mock()
    client.collection_exists.return_value = True
    client.create_point.return_value = {"id": "test-id", "vector": [0.1, 0.2, 0.3]}
    client.upsert_points.return_value = True
    return client


@pytest.fixture
def temp_metadata_path():
    """Create a temporary metadata file path."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


class TestProgressiveMetadata:
    """Test the ProgressiveMetadata class."""

    def test_initial_metadata_structure(self, temp_metadata_path):
        """Test that initial metadata has correct structure."""
        metadata = ProgressiveMetadata(temp_metadata_path)

        assert metadata.metadata["status"] == "not_started"
        assert metadata.metadata["last_index_timestamp"] == 0.0
        assert metadata.metadata["files_processed"] == 0
        assert metadata.metadata["chunks_indexed"] == 0
        assert metadata.metadata["failed_files"] == 0

    def test_start_indexing(self, temp_metadata_path):
        """Test starting an indexing operation."""
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {
            "git_available": True,
            "project_id": "test-project",
            "current_branch": "main",
            "current_commit": "abc123",
        }

        metadata.start_indexing("test-provider", "test-model", git_status)

        assert metadata.metadata["status"] == "in_progress"
        assert metadata.metadata["embedding_provider"] == "test-provider"
        assert metadata.metadata["embedding_model"] == "test-model"
        assert metadata.metadata["git_available"] is True
        assert metadata.metadata["project_id"] == "test-project"

    def test_update_progress(self, temp_metadata_path):
        """Test updating progress during indexing."""
        metadata = ProgressiveMetadata(temp_metadata_path)

        # Start indexing first
        git_status = {"git_available": False}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Update progress
        metadata.update_progress(files_processed=1, chunks_added=5, failed_files=0)

        assert metadata.metadata["files_processed"] == 1
        assert metadata.metadata["chunks_indexed"] == 5
        assert metadata.metadata["failed_files"] == 0
        assert metadata.metadata["last_index_timestamp"] > 0

    def test_complete_indexing(self, temp_metadata_path):
        """Test completing an indexing operation."""
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False}
        metadata.start_indexing("test-provider", "test-model", git_status)

        metadata.complete_indexing()

        assert metadata.metadata["status"] == "completed"

    def test_fail_indexing(self, temp_metadata_path):
        """Test failing an indexing operation."""
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False}
        metadata.start_indexing("test-provider", "test-model", git_status)

        error_msg = "Test error"
        metadata.fail_indexing(error_msg)

        assert metadata.metadata["status"] == "failed"
        assert metadata.metadata["error_message"] == error_msg

    def test_get_resume_timestamp_with_safety_buffer(self, temp_metadata_path):
        """Test getting resume timestamp with safety buffer."""
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Set a specific timestamp
        test_timestamp = time.time()
        metadata.metadata["last_index_timestamp"] = test_timestamp
        metadata._save_metadata()

        # Get resume timestamp with 60-second buffer
        resume_timestamp = metadata.get_resume_timestamp(60)

        assert resume_timestamp == test_timestamp - 60

    def test_should_force_full_index_provider_change(self, temp_metadata_path):
        """Test that provider change forces full index."""
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False}
        metadata.start_indexing("old-provider", "old-model", git_status)

        # Check with different provider
        should_force = metadata.should_force_full_index(
            "new-provider", "old-model", git_status
        )

        assert should_force is True

    def test_should_force_full_index_model_change(self, temp_metadata_path):
        """Test that model change forces full index."""
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False}
        metadata.start_indexing("provider", "old-model", git_status)

        # Check with different model
        should_force = metadata.should_force_full_index(
            "provider", "new-model", git_status
        )

        assert should_force is True

    def test_should_force_full_index_no_change(self, temp_metadata_path):
        """Test that no change doesn't force full index."""
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False, "project_id": "test"}
        metadata.start_indexing("provider", "model", git_status)

        # Check with same configuration
        should_force = metadata.should_force_full_index("provider", "model", git_status)

        assert should_force is False

    def test_get_stats(self, temp_metadata_path):
        """Test getting indexing statistics."""
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False}
        metadata.start_indexing("provider", "model", git_status)
        metadata.update_progress(files_processed=5, chunks_added=25, failed_files=1)

        stats = metadata.get_stats()

        assert stats["status"] == "in_progress"
        assert stats["files_processed"] == 5
        assert stats["chunks_indexed"] == 25
        assert stats["failed_files"] == 1
        assert stats["can_resume"] is True

    def test_metadata_persistence(self, temp_metadata_path):
        """Test that metadata persists between instances."""
        # Create first instance and save data
        metadata1 = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": True, "project_id": "test"}
        metadata1.start_indexing("provider", "model", git_status)
        metadata1.update_progress(files_processed=3, chunks_added=10)

        # Create second instance and verify data persists
        metadata2 = ProgressiveMetadata(temp_metadata_path)

        assert metadata2.metadata["status"] == "in_progress"
        assert metadata2.metadata["files_processed"] == 3
        assert metadata2.metadata["chunks_indexed"] == 10
        assert metadata2.metadata["embedding_provider"] == "provider"


class TestSmartIndexer:
    """Test the SmartIndexer class."""

    def test_smart_index_force_full(
        self,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
        temp_metadata_path,
    ):
        """Test smart indexing with force_full=True."""
        indexer = SmartIndexer(
            mock_config, mock_embedding_provider, mock_qdrant_client, temp_metadata_path
        )

        with patch.object(indexer, "get_git_status") as mock_git_status, patch.object(
            indexer, "file_finder"
        ) as mock_file_finder, patch.object(
            indexer.branch_aware_indexer, "index_branch_changes"
        ) as mock_branch_indexer:
            # Setup mocks
            mock_git_status.return_value = {"git_available": False}
            mock_file_finder.find_files.return_value = [Path("test.py")]
            mock_branch_indexer.return_value = BranchIndexingResult(
                files_processed=1,
                content_points_created=5,
                visibility_points_created=1,
                visibility_points_updated=0,
                content_points_reused=0,
                processing_time=0.1,
            )
            mock_qdrant_client.collection_exists.return_value = False

            stats = indexer.smart_index(force_full=True)

            # Verify full index was performed
            mock_qdrant_client.ensure_provider_aware_collection.assert_called_once()
            mock_qdrant_client.clear_collection.assert_called_once()
            assert stats.files_processed == 1
            assert stats.chunks_created == 5

    def test_smart_index_incremental_no_previous(
        self,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
        temp_metadata_path,
    ):
        """Test smart indexing with no previous index (should do full index)."""
        indexer = SmartIndexer(
            mock_config, mock_embedding_provider, mock_qdrant_client, temp_metadata_path
        )

        with patch.object(indexer, "get_git_status") as mock_git_status, patch.object(
            indexer, "file_finder"
        ) as mock_file_finder, patch.object(
            indexer.branch_aware_indexer, "index_branch_changes"
        ) as mock_branch_indexer:
            # Setup mocks
            mock_git_status.return_value = {"git_available": False}
            mock_file_finder.find_files.return_value = [Path("test.py")]
            mock_branch_indexer.return_value = BranchIndexingResult(
                files_processed=1,
                content_points_created=5,
                visibility_points_created=1,
                visibility_points_updated=0,
                content_points_reused=0,
                processing_time=0.1,
            )

            stats = indexer.smart_index(force_full=False)

            # Should fall back to full index since no previous data
            mock_qdrant_client.ensure_provider_aware_collection.assert_called_once()
            mock_qdrant_client.clear_collection.assert_called_once()
            assert stats.files_processed == 1

    def test_smart_index_incremental_with_changes(
        self,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
        temp_metadata_path,
    ):
        """Test smart indexing with previous index and file changes."""
        # Pre-populate metadata
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False, "project_id": "test"}
        metadata.start_indexing("test-provider", "test-model", git_status)
        metadata.update_progress(files_processed=1, chunks_added=5)
        metadata.complete_indexing()

        indexer = SmartIndexer(
            mock_config, mock_embedding_provider, mock_qdrant_client, temp_metadata_path
        )

        with patch.object(indexer, "get_git_status") as mock_git_status, patch.object(
            indexer, "file_finder"
        ) as mock_file_finder, patch.object(
            indexer, "_process_files_with_metadata"
        ) as mock_process:
            # Setup mocks - use the same git_status as the pre-populated metadata
            mock_git_status.return_value = git_status
            mock_file_finder.find_modified_files.return_value = [Path("changed.py")]
            mock_process.return_value = ProcessingStats(
                files_processed=1, chunks_created=3
            )
            # Mock embedding provider info to match metadata
            mock_embedding_provider.get_provider_name.return_value = "test-provider"
            mock_embedding_provider.get_current_model.return_value = "test-model"

            stats = indexer.smart_index(force_full=False)

            # Should do incremental update
            mock_qdrant_client.ensure_provider_aware_collection.assert_called_once()
            mock_qdrant_client.clear_collection.assert_not_called()
            assert stats.files_processed == 1
            assert stats.chunks_created == 3

    def test_smart_index_no_files_to_index(
        self,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
        temp_metadata_path,
    ):
        """Test smart indexing when no files need incremental indexing."""
        # Pre-populate metadata with a proper resume timestamp
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False, "project_id": "test"}
        metadata.start_indexing("test-provider", "test-model", git_status)
        metadata.update_progress(files_processed=1, chunks_added=5)  # Add some progress
        metadata.complete_indexing()

        indexer = SmartIndexer(
            mock_config, mock_embedding_provider, mock_qdrant_client, temp_metadata_path
        )

        with patch.object(indexer, "get_git_status") as mock_git_status, patch.object(
            indexer, "file_finder"
        ) as mock_file_finder:
            # Setup mocks
            mock_git_status.return_value = git_status
            mock_file_finder.find_modified_files.return_value = []  # No changes

            stats = indexer.smart_index(force_full=False)

            # Should return empty stats for incremental update with no changes
            assert stats.files_processed == 0
            assert stats.chunks_created == 0

    def test_get_indexing_status(
        self,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
        temp_metadata_path,
    ):
        """Test getting indexing status."""
        indexer = SmartIndexer(
            mock_config, mock_embedding_provider, mock_qdrant_client, temp_metadata_path
        )

        status = indexer.get_indexing_status()

        assert "status" in status
        assert "files_processed" in status
        assert "chunks_indexed" in status
        assert "can_resume" in status

    def test_can_resume(
        self,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
        temp_metadata_path,
    ):
        """Test can_resume functionality."""
        # Create indexer with no previous data
        indexer = SmartIndexer(
            mock_config, mock_embedding_provider, mock_qdrant_client, temp_metadata_path
        )

        assert indexer.can_resume() is False

        # Add some progress
        git_status = {"git_available": False}
        indexer.progressive_metadata.start_indexing("provider", "model", git_status)
        indexer.progressive_metadata.update_progress(files_processed=1)

        assert indexer.can_resume() is True

    def test_clear_progress(
        self,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
        temp_metadata_path,
    ):
        """Test clearing progress metadata."""
        indexer = SmartIndexer(
            mock_config, mock_embedding_provider, mock_qdrant_client, temp_metadata_path
        )

        # Add some progress
        git_status = {"git_available": False}
        indexer.progressive_metadata.start_indexing("provider", "model", git_status)
        indexer.progressive_metadata.update_progress(files_processed=5)

        # Clear progress
        indexer.clear_progress()

        assert indexer.progressive_metadata.metadata["status"] == "not_started"
        assert indexer.progressive_metadata.metadata["files_processed"] == 0

    def test_configuration_change_forces_full_index(
        self,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
        temp_metadata_path,
    ):
        """Test that configuration changes force a full index."""
        # Pre-populate metadata with different provider
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False, "project_id": "test"}
        metadata.start_indexing("old-provider", "old-model", git_status)
        metadata.complete_indexing()

        indexer = SmartIndexer(
            mock_config, mock_embedding_provider, mock_qdrant_client, temp_metadata_path
        )

        with patch.object(indexer, "get_git_status") as mock_git_status, patch.object(
            indexer, "file_finder"
        ) as mock_file_finder, patch.object(
            indexer.branch_aware_indexer, "index_branch_changes"
        ) as mock_branch_indexer:
            # Setup mocks - different provider now
            mock_git_status.return_value = git_status
            mock_file_finder.find_files.return_value = [Path("test.py")]
            mock_branch_indexer.return_value = BranchIndexingResult(
                files_processed=1,
                content_points_created=5,
                visibility_points_created=1,
                visibility_points_updated=0,
                content_points_reused=0,
                processing_time=0.1,
            )
            mock_embedding_provider.get_provider_name.return_value = (
                "new-provider"  # Changed!
            )
            mock_embedding_provider.get_current_model.return_value = "new-model"

            stats = indexer.smart_index(force_full=False)

            # Should force full index due to provider change
            mock_qdrant_client.clear_collection.assert_called_once()
            assert stats.files_processed == 1


class TestProgressiveMetadataIntegration:
    """Integration tests for progressive metadata functionality."""

    def test_interrupted_indexing_resume(self, temp_metadata_path):
        """Test that interrupted indexing can be properly resumed."""
        # Simulate an interrupted indexing session
        metadata = ProgressiveMetadata(temp_metadata_path)
        git_status = {"git_available": False, "project_id": "test"}

        # Start indexing
        metadata.start_indexing("provider", "model", git_status)

        # Process some files
        metadata.update_progress(files_processed=3, chunks_added=15)
        metadata.update_progress(files_processed=2, chunks_added=10)

        # Simulate interruption (don't call complete_indexing)
        assert metadata.metadata["status"] == "in_progress"
        assert metadata.metadata["files_processed"] == 5
        assert metadata.metadata["chunks_indexed"] == 25

        # Create new instance (simulating restart)
        metadata2 = ProgressiveMetadata(temp_metadata_path)

        # Should detect in-progress state and allow resume
        stats = metadata2.get_stats()
        assert stats["status"] == "in_progress"
        assert stats["can_resume"] is True
        assert stats["files_processed"] == 5
        assert stats["chunks_indexed"] == 25

        # Should be able to get a resume timestamp
        resume_timestamp = metadata2.get_resume_timestamp(60)
        assert resume_timestamp > 0

    def test_safety_buffer_edge_case(self, temp_metadata_path):
        """Test safety buffer handles edge cases properly."""
        metadata = ProgressiveMetadata(temp_metadata_path)

        # Start indexing to set status to in_progress
        git_status = {"git_available": False}
        metadata.start_indexing("provider", "model", git_status)

        # Test with timestamp of 0
        metadata.metadata["last_index_timestamp"] = 0.0
        metadata._save_metadata()
        assert metadata.get_resume_timestamp(60) == 0.0

        # Test with very small timestamp (should not go negative)
        metadata.metadata["last_index_timestamp"] = 30.0
        metadata._save_metadata()
        resume_timestamp = metadata.get_resume_timestamp(60)
        assert resume_timestamp == 0.0  # max(0.0, 30 - 60) = 0.0

        # Test with normal timestamp
        current_time = time.time()
        metadata.metadata["last_index_timestamp"] = current_time
        metadata._save_metadata()
        resume_timestamp = metadata.get_resume_timestamp(60)
        assert resume_timestamp == current_time - 60
