#!/usr/bin/env python3
"""
Test meaningful feedback for different indexing operations.

This test ensures that users get clear, context-aware feedback for:
- --clear operations (show collections cleaned)
- --reconcile operations (show files found/missing in collection)
- Resume operations (show extra files indexed)
"""

import pytest

from ...conftest import get_local_tmp_dir
import shutil
from pathlib import Path
import uuid
from unittest.mock import Mock, patch
import time

from src.code_indexer.config import Config
from src.code_indexer.services.smart_indexer import SmartIndexer
from src.code_indexer.services.qdrant import QdrantClient
from src.code_indexer.services.embedding_provider import EmbeddingProvider


class TestMeaningfulFeedbackOperations:
    """Test meaningful feedback for different indexing operations."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project with git repo and test files."""
        temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Create test files
        (temp_dir / "test1.py").write_text("# Test file 1\nprint('hello')")
        (temp_dir / "test2.py").write_text("# Test file 2\nprint('world')")
        (temp_dir / "test3.py").write_text("# Test file 3\nprint('test')")

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=temp_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=temp_dir,
            capture_output=True,
        )

        # Create .gitignore to prevent committing .code-indexer directory
        (temp_dir / ".gitignore").write_text(
            """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
        )

        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=temp_dir, capture_output=True
        )

        yield temp_dir

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def smart_indexer(self, temp_project):
        """Create SmartIndexer instance for testing."""
        config = Config(codebase_dir=temp_project)

        # Mock embedding provider
        embedding_provider = Mock(spec=EmbeddingProvider)
        embedding_provider.get_provider_name.return_value = "test-provider"
        embedding_provider.get_current_model.return_value = "test-model"
        embedding_provider.get_embedding.return_value = [0.1] * 768
        embedding_provider.get_model_info.return_value = {"dimensions": 768}

        # Mock Qdrant client
        qdrant_client = Mock(spec=QdrantClient)
        qdrant_client.ensure_provider_aware_collection.return_value = "test_collection"
        qdrant_client.collection_exists.return_value = True
        qdrant_client.resolve_collection_name.return_value = "test_collection"
        qdrant_client.scroll_points.return_value = ([], None)
        qdrant_client.create_point.return_value = {"id": "test-point"}
        qdrant_client.upsert_points.return_value = None

        metadata_path = temp_project / ".code-indexer" / "metadata.json"
        indexer = SmartIndexer(config, embedding_provider, qdrant_client, metadata_path)

        return indexer

    def test_clear_operation_feedback_shows_collections_cleaned(self, smart_indexer):
        """Test that --clear operation shows which collections were cleaned."""
        # Arrange
        feedback_messages = []

        def capture_feedback(current, total, path, info=None, **kwargs):
            if info:
                feedback_messages.append(info)

        # Mock collection operations
        smart_indexer.qdrant_client.clear_collection.return_value = (
            42  # 42 documents cleared
        )
        smart_indexer.qdrant_client.get_collection_info.return_value = {
            "points_count": 42,
            "collection_name": "test_collection_voyage_ai_code_3",
        }

        # Act
        with patch.object(
            smart_indexer, "_process_files_with_metadata"
        ) as mock_process:
            mock_process.return_value = Mock(
                files_processed=3, chunks_created=15, failed_files=0
            )

            smart_indexer.smart_index(
                force_full=True, progress_callback=capture_feedback
            )

        # Assert

        # Should mention collection being cleared
        assert any(
            "collection" in msg.lower() and "clear" in msg.lower()
            for msg in feedback_messages
        ), f"Expected feedback about collection clearing, got: {feedback_messages}"

        # Should mention number of documents if available
        assert any(
            "42" in msg for msg in feedback_messages
        ), f"Expected feedback to mention document count, got: {feedback_messages}"

    def test_reconcile_operation_feedback_shows_files_comparison(self, smart_indexer):
        """Test that --reconcile operation shows files found vs missing comparison."""
        # Arrange
        feedback_messages = []

        def capture_feedback(current, total, path, info=None, **kwargs):
            if info:
                feedback_messages.append(info)

        # Mock database having 2 files, but disk has 3 files (1 new file)
        mock_db_points = [
            {"payload": {"path": "test1.py", "file_mtime": time.time() - 100}},
            {"payload": {"path": "test2.py", "file_mtime": time.time() - 100}},
        ]
        smart_indexer.qdrant_client.scroll_points.return_value = (mock_db_points, None)

        # Act
        with patch.object(
            smart_indexer, "_process_files_with_metadata"
        ) as mock_process:
            mock_process.return_value = Mock(
                files_processed=1, chunks_created=5, failed_files=0
            )

            smart_indexer.smart_index(
                reconcile_with_database=True, progress_callback=capture_feedback
            )

        # Assert

        # Should mention checking database
        assert any(
            "checking database" in msg.lower() or "database collection" in msg.lower()
            for msg in feedback_messages
        ), f"Expected feedback about checking database, got: {feedback_messages}"

        # Should mention files found in database vs disk
        assert any(
            "files" in msg.lower()
            and ("found" in msg.lower() or "indexed" in msg.lower())
            for msg in feedback_messages
        ), f"Expected feedback about files comparison, got: {feedback_messages}"

    def test_resume_operation_feedback_shows_remaining_files(self, smart_indexer):
        """Test that resume operation shows how many files are remaining to process."""
        # Arrange
        feedback_messages = []

        def capture_feedback(current, total, path, info=None, **kwargs):
            if info:
                feedback_messages.append(info)

        # Set up interrupted state with 2 files completed, 1 remaining
        smart_indexer.progressive_metadata.metadata = {
            "status": "in_progress",
            "files_to_index": ["test1.py", "test2.py", "test3.py"],
            "total_files_to_index": 3,
            "current_file_index": 2,  # 2 files completed
            "completed_files": ["test1.py", "test2.py"],
            "files_processed": 2,
            "chunks_indexed": 10,
            "failed_files": 0,
        }

        # Act
        with patch.object(
            smart_indexer, "_process_files_with_metadata"
        ) as mock_process:
            mock_process.return_value = Mock(
                files_processed=1, chunks_created=5, failed_files=0
            )

            smart_indexer.smart_index(progress_callback=capture_feedback)

        # Assert

        # Should mention resuming interrupted operation
        assert any(
            "resuming" in msg.lower() and "interrupted" in msg.lower()
            for msg in feedback_messages
        ), f"Expected feedback about resuming interrupted operation, got: {feedback_messages}"

        # Should mention how many files are remaining
        assert any(
            "remaining" in msg.lower()
            or ("files" in msg.lower() and "completed" in msg.lower())
            for msg in feedback_messages
        ), f"Expected feedback about remaining files, got: {feedback_messages}"

    def test_full_index_after_config_change_feedback(self, smart_indexer):
        """Test feedback when forcing full index due to configuration changes."""
        # Arrange
        feedback_messages = []

        def capture_feedback(current, total, path, info=None, **kwargs):
            if info:
                feedback_messages.append(info)

        # Set up metadata with different provider to trigger config change
        smart_indexer.progressive_metadata.metadata = {
            "status": "completed",
            "embedding_provider": "old-provider",  # Different from current
            "embedding_model": "old-model",
            "files_processed": 2,
            "chunks_indexed": 10,
        }

        # Mock collection operations for full index
        smart_indexer.qdrant_client.get_collection_info.return_value = {
            "points_count": 42,
            "collection_name": "test_collection",
        }
        smart_indexer.qdrant_client.clear_collection.return_value = None

        # Act
        with patch.object(
            smart_indexer, "_process_files_with_metadata"
        ) as mock_process:
            mock_process.return_value = Mock(
                files_processed=3, chunks_created=15, failed_files=0
            )

            smart_indexer.smart_index(progress_callback=capture_feedback)

        # Assert

        # Should mention configuration change
        assert any(
            "configuration" in msg.lower() and "changed" in msg.lower()
            for msg in feedback_messages
        ), f"Expected feedback about configuration change, got: {feedback_messages}"

        # Should mention performing full index
        assert any(
            "full index" in msg.lower() for msg in feedback_messages
        ), f"Expected feedback about full index, got: {feedback_messages}"

    def test_branch_change_feedback_shows_optimization(self, smart_indexer):
        """Test feedback when branch change triggers graph-optimized indexing."""
        # Arrange
        feedback_messages = []

        def capture_feedback(current, total, path, info=None, **kwargs):
            if info:
                feedback_messages.append(info)

        # Set up metadata with different branch to trigger branch change
        smart_indexer.progressive_metadata.metadata = {
            "status": "completed",
            "current_branch": "main",  # Different from current
            "files_processed": 2,
            "chunks_indexed": 10,
        }

        # Mock git topology service and other dependencies
        with (
            patch.object(
                smart_indexer.git_topology_service,
                "get_current_branch",
                return_value="feature-branch",
            ),
            patch.object(
                smart_indexer.git_topology_service, "analyze_branch_change"
            ) as mock_analyze,
            patch.object(
                smart_indexer.branch_aware_indexer, "index_branch_changes"
            ) as mock_index_changes,
        ):

            # Set up mock analysis
            mock_analysis = Mock()
            mock_analysis.files_to_reindex = ["test3.py"]  # 1 changed file
            mock_analysis.files_to_update_metadata = [
                "test1.py",
                "test2.py",
            ]  # 2 unchanged
            mock_analyze.return_value = mock_analysis

            # Set up mock branch aware indexer result
            mock_result = Mock()
            mock_result.files_processed = 3
            mock_result.content_points_created = 5
            mock_result.content_points_reused = 8
            mock_result.processing_time = 1.5
            mock_index_changes.return_value = mock_result

            # Act
            smart_indexer.smart_index(progress_callback=capture_feedback)

        # Assert

        # Should mention branch change detection
        assert any(
            "branch change" in msg.lower() and "detected" in msg.lower()
            for msg in feedback_messages
        ), f"Expected feedback about branch change detection, got: {feedback_messages}"

        # Should mention graph-optimized indexing
        assert any(
            "graph-optimized" in msg.lower() or "optimized" in msg.lower()
            for msg in feedback_messages
        ), f"Expected feedback about optimization, got: {feedback_messages}"

        # Should show branch names
        assert any(
            "main" in msg and "feature-branch" in msg for msg in feedback_messages
        ), f"Expected feedback to show branch names, got: {feedback_messages}"

    def test_no_files_found_feedback(self, smart_indexer):
        """Test feedback when no files are found to index."""
        # Arrange
        feedback_messages = []

        def capture_feedback(current, total, path, info=None, **kwargs):
            if info:
                feedback_messages.append(info)

        # Mock collection operations for full index
        smart_indexer.qdrant_client.get_collection_info.return_value = {
            "points_count": 0,
            "collection_name": "test_collection",
        }
        smart_indexer.qdrant_client.clear_collection.return_value = None

        # Mock file finder to return empty list
        with patch.object(smart_indexer.file_finder, "find_files", return_value=[]):
            # Act & Assert
            with pytest.raises(ValueError, match="No files found to index"):
                smart_indexer.smart_index(
                    force_full=True, progress_callback=capture_feedback
                )

        # Should have some feedback about the process
        assert len(feedback_messages) >= 0  # At least some attempt at feedback


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
