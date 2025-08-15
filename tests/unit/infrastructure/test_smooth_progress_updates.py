"""
Test smooth progress updates for queue-based processing.

This test verifies that progress updates are smooth and incremental,
showing individual file progress rather than batch updates.
"""

from pathlib import Path
import uuid
from unittest.mock import Mock, patch
import pytest

from ...conftest import get_local_tmp_dir

from code_indexer.config import Config
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.services import QdrantClient
from ..services.test_vector_calculation_manager import MockEmbeddingProvider


class TestSmoothProgressUpdates:
    """Test cases for smooth progress updates."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        self.temp_dir = str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}")
        self.temp_path = Path(self.temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.temp_path / "metadata.json"

        # Create test files
        self.test_files = []
        for i in range(5):
            file_path = self.temp_path / f"test_file_{i}.py"
            content = f"""
def function_{i}():
    '''Function {i} with content for chunking.'''
    return "This is function {i} with substantial content for testing."

class TestClass_{i}:
    '''Test class {i}'''
    
    def method_1(self):
        return "Method implementation"
    
    def method_2(self):
        return "Another method"
"""
            file_path.write_text(content)
            self.test_files.append(file_path)

        # Create mock config
        self.config = Mock(spec=Config)
        self.config.codebase_dir = self.temp_path
        self.config.exclude_dirs = []
        self.config.exclude_files = []
        self.config.file_extensions = ["py"]

        # Mock nested config attributes
        self.config.qdrant = Mock()
        self.config.qdrant.vector_size = 768

        self.config.indexing = Mock()
        self.config.indexing.chunk_size = 200
        self.config.indexing.overlap_size = 50
        self.config.indexing.max_file_size = 1000000
        self.config.indexing.min_file_size = 1

        self.config.chunking = Mock()
        self.config.chunking.chunk_size = 200
        self.config.chunking.overlap_size = 50

        # Mock Qdrant client
        self.mock_qdrant = Mock(spec=QdrantClient)
        self.mock_qdrant.upsert_points.return_value = True
        self.mock_qdrant.create_point.return_value = {"id": "test-point"}
        # Make get_point return None so _content_exists returns False (forces chunking path)
        self.mock_qdrant.get_point.return_value = None
        self.mock_qdrant.scroll_points.return_value = ([], None)  # For branch isolation

        # Mock embedding provider
        self.mock_embedding_provider = MockEmbeddingProvider(delay=0.01)

    @pytest.mark.unit
    def test_smooth_progress_implementation(self):
        """Test the new smooth progress callback implementation."""

        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        progress_calls = []

        def progress_callback(current, total, file_path, info=None, error=None):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                    "error": error,
                }
            )

        # Process files and capture progress calls
        processor.process_files_high_throughput(
            self.test_files,
            vector_thread_count=2,
            batch_size=10,
            progress_callback=progress_callback,
        )

        # Analyze smooth progress behavior
        print(f"Total progress calls: {len(progress_calls)}")
        for i, call in enumerate(progress_calls):
            print(
                f"Call {i}: current={call['current']}, total={call['total']}, file={call['file_path']}, info={call['info']}"
            )

        # Verify smooth progress implementation
        assert len(progress_calls) >= len(
            self.test_files
        ), "Should have at least one call per file"

        # Check that we have actual file names in info messages (since we use empty paths for CLI compatibility)
        info_messages = [call["info"] for call in progress_calls if call["info"]]
        assert not any(
            "processing..." in info for info in info_messages
        ), "Should show actual file names, not generic processing message"

        # Check that we show individual files being processed (now in info messages)
        unique_files = set()
        for call in progress_calls:
            if call["info"] and "test_file_" in call["info"]:
                # Extract filename from info message
                info_parts = call["info"].split(" | ")
                for part in info_parts:
                    if "test_file_" in part:
                        # Extract just the filename part (before any status indicators)
                        file_name = part.split(" ")[0].split(".py")[0] + ".py"
                        unique_files.add(file_name)
                        break

        assert len(unique_files) == len(
            self.test_files
        ), f"Should show all {len(self.test_files)} files, got {len(unique_files)}"

        # Check file-based progress tracking (not just chunk-based)
        assert progress_calls[0]["total"] == len(
            self.test_files
        ), "Progress should be file-based"
        assert progress_calls[-1]["current"] == len(
            self.test_files
        ), "Should complete all files"

        # Check for completion indicators (checkmarks in info messages)
        completed_calls = [
            call for call in progress_calls if call["info"] and "✓" in call["info"]
        ]
        assert len(completed_calls) >= len(
            self.test_files
        ), "Should show file completions with checkmarks in info messages"

        # Verify smooth incremental updates (small gaps between calls)
        if len(progress_calls) > 1:
            gaps = []
            for i in range(1, len(progress_calls)):
                gap = progress_calls[i]["current"] - progress_calls[i - 1]["current"]
                gaps.append(gap)

            avg_gap = sum(gaps) / len(gaps) if gaps else 0
            print(f"Average gap between progress calls: {avg_gap} files")

            # Should have smooth updates (much smaller gaps than old implementation)
            assert (
                avg_gap <= 1
            ), f"Should have smooth updates, got average gap of {avg_gap} files"

    @pytest.mark.unit
    def test_desired_smooth_progress(self):
        """Test what we want: smooth, file-based progress updates."""

        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        progress_calls = []
        completed_files = set()

        def progress_callback(current, total, file_path, info=None, error=None):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                    "error": error,
                }
            )

            # Track when files are completed
            if "test_file_" in str(file_path):
                completed_files.add(str(file_path))

        # Process files
        processor.process_files_high_throughput(
            self.test_files,
            vector_thread_count=2,
            batch_size=10,
            progress_callback=progress_callback,
        )

        # What we want to see:
        # 1. Progress should be called more frequently (ideally for each completed file)
        # 2. file_path should show actual file names, not "processing..."
        # 3. Progress should be smooth and incremental

        print(f"Completed files tracked: {len(completed_files)}")
        print(
            f"Unique file paths in progress: {len(set(call['file_path'] for call in progress_calls))}"
        )

        # For now, just document what we currently get
        # TODO: After implementation, these assertions should pass

        # This test currently documents the limitations we want to fix:
        # - File paths are generic "processing..."
        # - Progress updates are too infrequent
        # - No clear file-level completion tracking

    @pytest.mark.unit
    def test_branch_aware_indexer_smooth_progress(self):
        """Test that BranchAwareIndexer also provides smooth progress updates."""
        from code_indexer.services.branch_aware_indexer import BranchAwareIndexer

        # Create BranchAwareIndexer instance
        branch_indexer = BranchAwareIndexer(
            qdrant_client=self.mock_qdrant,
            embedding_provider=self.mock_embedding_provider,
            text_chunker=Mock(),  # We'll mock chunking
            config=self.config,
        )

        # Mock text chunker to return predictable chunks
        chunks_per_file = 3  # Each file will have 3 chunks
        mock_chunks = []
        for i in range(chunks_per_file):
            mock_chunks.append(
                {
                    "chunk_index": i,
                    "total_chunks": chunks_per_file,  # Add total_chunks field expected by BranchAwareIndexer
                    "text": f"chunk {i} content",
                    "metadata": {"start": i * 100, "end": (i + 1) * 100},
                }
            )

        branch_indexer.text_chunker.chunk_file.return_value = mock_chunks

        # Also mock other required dependencies
        branch_indexer.file_identifier = Mock()
        branch_indexer.file_identifier.get_file_metadata.return_value = {"type": "test"}

        # Mock git service methods
        branch_indexer.git_topology_service = Mock()
        branch_indexer.git_topology_service.get_current_commit.return_value = "abc123"

        # Mock collection name resolution
        self.mock_qdrant.resolve_collection_name.return_value = "test_collection"

        # Mock the _content_exists method to return False to force chunking path
        # This ensures we test the chunk-level progress updates
        branch_indexer._content_exists = Mock(return_value=False)

        # Mock the _get_file_commit method to return a predictable commit hash
        branch_indexer._get_file_commit = Mock(return_value="abc123")

        # Mock the embedding provider to return a simple vector
        branch_indexer.embedding_provider.get_embedding = Mock(return_value=[0.1] * 768)
        branch_indexer.embedding_provider.get_current_model = Mock(
            return_value="test-model"
        )

        # Mock the file detection methods
        branch_indexer._detect_language = Mock(return_value="python")
        branch_indexer._determine_working_dir_status = Mock(return_value="committed")
        branch_indexer._get_embedding_dimensions = Mock(return_value=768)

        progress_calls = []

        def progress_callback(current, total, file_path, info=None, error=None):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                    "error": error,
                }
            )

        # Convert file paths to relative strings
        relative_files = [f"test_file_{i}.py" for i in range(len(self.test_files))]

        # Process files and capture progress calls
        branch_indexer.index_branch_changes(
            old_branch="",
            new_branch="main",
            changed_files=relative_files,
            unchanged_files=[],
            collection_name="test_collection",
            progress_callback=progress_callback,
        )

        # Analyze smooth progress behavior for BranchAwareIndexer
        print(f"BranchAwareIndexer progress calls: {len(progress_calls)}")
        for i, call in enumerate(progress_calls):
            print(
                f"Call {i}: current={call['current']}, total={call['total']}, file={call['file_path']}, info={call['info']}"
            )

        # Verify BranchAwareIndexer provides proper progress updates (one per file)
        assert len(progress_calls) == len(
            self.test_files
        ), "Should have exactly one call per file for file-level progress"

        # Check that we have progress indicators in info messages with correct format
        info_messages = [call["info"] for call in progress_calls if call["info"]]
        assert len(info_messages) > 0, "Should provide informative progress messages"

        # Verify the progress format matches CLI expectations: "files (%) | emb/s {icon} | threads | filename"
        for info in info_messages:
            assert "files (" in info, f"Should show file count format in: {info}"
            assert "%) |" in info, f"Should show percentage format in: {info}"
            # Updated to account for throttling icons (⚡🟡🔴)
            assert (
                "emb/s ⚡ |" in info
                or "emb/s 🟡 |" in info
                or "emb/s 🔴 |" in info
                or "emb/s |" in info
            ), f"Should show emb/s format with optional throttling icon in: {info}"
            assert "threads |" in info, f"Should show thread count in: {info}"
            assert "✓" in info, f"Should show completion status in: {info}"

        # Check that progress provides meaningful file paths and info messages
        assert all(
            call["file_path"] and call["info"] for call in progress_calls
        ), "All calls should provide file paths and info messages"

    @pytest.mark.unit
    def test_reconcile_inherits_smooth_progress(self):
        """Test that reconcile operations get smooth progress from both code paths."""
        from code_indexer.services.smart_indexer import SmartIndexer

        # Create SmartIndexer instance
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        progress_calls = []

        def progress_callback(current, total, file_path, info=None, error=None):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                    "error": error,
                }
            )

        # Test reconcile with BranchAwareIndexer path (force failure to test fallback)
        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback to queue-based"),
        ):
            # Should raise RuntimeError due to disabled fallbacks
            with pytest.raises(
                RuntimeError,
                match="Git-aware reconcile failed and fallbacks are disabled",
            ):
                smart_indexer.smart_index(
                    reconcile_with_database=True,
                    progress_callback=progress_callback,
                    batch_size=10,
                )

            # The reconcile operation may show both database checking AND file processing progress
            # We mainly want to verify it doesn't have the old "jumpy" progress behavior

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
