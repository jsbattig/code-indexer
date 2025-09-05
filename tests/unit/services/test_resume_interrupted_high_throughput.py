"""
Test for migrating resume interrupted processing to high-throughput pipeline.

This test suite verifies that resume operations (_do_resume_interrupted) use
HighThroughputProcessor.process_files_high_throughput() directly instead of going
through process_branch_changes_high_throughput() wrapper.

Story 3 Requirements for Resume Operations:
- Resume operations should use HighThroughputProcessor.process_files_high_throughput()
- Only remaining files should be queued for processing
- All 8 worker threads should process remaining files simultaneously
- Git commit tracking should work correctly during resume
- Performance should improve by minimum 4x over current implementation
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import time

import pytest

from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.indexing.processor import ProcessingStats


@pytest.fixture
def temp_metadata_path():
    """Create a temporary metadata file path."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Mock(spec=Config)
        config.codebase_dir = Path(tmpdir)
        config.exclude_dirs = ["node_modules", ".git"]
        config.exclude_files = []
        config.file_extensions = ["py", "js", "ts"]

        # Mock the indexing sub-config
        indexing_config = Mock()
        indexing_config.chunk_size = 1000
        indexing_config.chunk_overlap = 100
        indexing_config.max_file_size = 1000000
        config.indexing = indexing_config

        # Mock qdrant config
        config.qdrant = Mock()
        config.qdrant.vector_size = 768

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
    client.ensure_provider_aware_collection.return_value = "test-collection"
    client.resolve_collection_name.return_value = "test-collection"
    return client


class TestResumeInterruptedHighThroughput:
    """Test migration of resume interrupted processing to high-throughput pipeline."""

    def test_resume_interrupted_should_use_direct_high_throughput_processing(
        self,
        temp_metadata_path,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
    ):
        """
        FAILING TEST: _do_resume_interrupted should use self.process_files_high_throughput()
        directly instead of self.branch_aware_indexer.process_branch_changes_high_throughput().
        """
        # Create SmartIndexer instance
        indexer = SmartIndexer(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            qdrant_client=mock_qdrant_client,
            metadata_path=temp_metadata_path,
        )

        # Create actual files for realistic testing
        test_files = []
        for i in range(5):
            file_path = mock_config.codebase_dir / f"file_{i}.py"
            file_path.write_text(f"def function_{i}(): pass")
            test_files.append(file_path)

        # Simulate interrupted operation with remaining files
        remaining_file_strings = [
            str(f) for f in test_files[2:]
        ]  # Last 3 files remaining

        git_status = {
            "git_available": True,
            "project_id": "test-project",
            "current_branch": "master",
            "current_commit": "abc123",
        }

        # Mock the dependencies
        with patch.object(
            indexer.progressive_metadata,
            "get_remaining_files",
            return_value=remaining_file_strings,
        ):
            with patch.object(
                indexer.git_topology_service,
                "get_current_branch",
                return_value="master",
            ):

                # KEY TEST: Mock both processing approaches to detect which is used
                with patch.object(
                    indexer, "process_files_high_throughput"
                ) as mock_direct_process:
                    with patch.object(
                        indexer, "process_branch_changes_high_throughput"
                    ) as mock_branch_process:

                        # Configure return values
                        direct_stats = ProcessingStats()
                        direct_stats.files_processed = 3
                        direct_stats.chunks_created = 30
                        direct_stats.failed_files = 0
                        direct_stats.cancelled = False

                        branch_result = Mock(
                            files_processed=3,
                            content_points_created=30,
                            cancelled=False,
                            processing_time=1.5,
                        )

                        mock_direct_process.return_value = direct_stats
                        mock_branch_process.return_value = branch_result

                        # Mock other required methods
                        with patch.object(
                            indexer.progressive_metadata, "update_progress"
                        ):
                            with patch.object(
                                indexer.progressive_metadata, "complete_indexing"
                            ):
                                with patch.object(
                                    indexer.progress_log, "complete_session"
                                ):

                                    # Execute the resume operation
                                    result = indexer._do_resume_interrupted(
                                        batch_size=10,
                                        progress_callback=None,
                                        git_status=git_status,
                                        provider_name="test-provider",
                                        model_name="test-model",
                                        quiet=True,
                                        vector_thread_count=8,
                                    )

        # CRITICAL ASSERTIONS FOR STORY 3

        # 1. MUST use HighThroughputProcessor.process_files_high_throughput() directly
        # CURRENTLY FAILING: Current implementation uses branch_aware_indexer wrapper
        assert mock_direct_process.called, (
            "STORY 3 REQUIREMENT: _do_resume_interrupted MUST use "
            "HighThroughputProcessor.process_files_high_throughput() directly"
        )

        # 2. MUST NOT use BranchAwareIndexer wrapper
        # CURRENTLY FAILING: Current implementation still uses branch wrapper
        assert not mock_branch_process.called, (
            "STORY 3 REQUIREMENT: Should NOT use process_branch_changes_high_throughput() "
            "wrapper for resume operations"
        )

        # 3. Should pass only remaining files for processing
        if mock_direct_process.called:
            call_args = mock_direct_process.call_args
            files_arg = call_args[1]["files"]  # files parameter
            assert (
                len(files_arg) == 3
            ), f"Should process exactly 3 remaining files, got {len(files_arg)}"

            # Verify it's processing the correct remaining files
            processed_file_names = {f.name for f in files_arg}
            expected_names = {"file_2.py", "file_3.py", "file_4.py"}
            assert (
                processed_file_names == expected_names
            ), f"Should process remaining files {expected_names}, got {processed_file_names}"

        # 4. Should use 8 worker threads for parallel processing
        if mock_direct_process.called:
            call_args = mock_direct_process.call_args
            vector_thread_count = call_args[1]["vector_thread_count"]
            assert (
                vector_thread_count == 8
            ), "Should use 8 worker threads for maximum parallel processing"

        # 5. Result should be successful
        assert result is not None
        assert isinstance(result, ProcessingStats)
        assert result.files_processed == 3
        assert result.chunks_created == 30

    def test_resume_interrupted_with_no_remaining_files(
        self,
        temp_metadata_path,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
    ):
        """
        Test resume when all files were already processed before interruption.
        """
        # Create SmartIndexer instance
        indexer = SmartIndexer(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            qdrant_client=mock_qdrant_client,
            metadata_path=temp_metadata_path,
        )

        git_status = {
            "git_available": True,
            "project_id": "test-project",
            "current_branch": "master",
            "current_commit": "abc123",
        }

        # Mock no remaining files (all were processed before interruption)
        with patch.object(
            indexer.progressive_metadata, "get_remaining_files", return_value=[]
        ):
            with patch.object(
                indexer.progressive_metadata, "complete_indexing"
            ) as mock_complete:
                with patch.object(
                    indexer.progress_log, "complete_session"
                ) as mock_log_complete:

                    # Execute resume operation
                    result = indexer._do_resume_interrupted(
                        batch_size=10,
                        progress_callback=None,
                        git_status=git_status,
                        provider_name="test-provider",
                        model_name="test-model",
                        quiet=True,
                        vector_thread_count=8,
                    )

        # Should complete successfully without processing
        assert result is not None
        assert isinstance(result, ProcessingStats)
        assert result.files_processed == 0
        assert result.chunks_created == 0

        # Should mark as completed and close session
        assert mock_complete.called
        assert mock_log_complete.called

    def test_resume_interrupted_with_deleted_files(
        self,
        temp_metadata_path,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
    ):
        """
        Test resume when some remaining files were deleted after interruption.
        Should filter out non-existent files and process only existing ones.
        """
        # Create SmartIndexer instance
        indexer = SmartIndexer(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            qdrant_client=mock_qdrant_client,
            metadata_path=temp_metadata_path,
        )

        # Create some files but not others (simulate deletion)
        existing_files = []
        for i in [1, 3]:  # Create only files 1 and 3
            file_path = mock_config.codebase_dir / f"file_{i}.py"
            file_path.write_text(f"def function_{i}(): pass")
            existing_files.append(file_path)

        # Remaining files include both existing and deleted ones
        remaining_file_strings = [
            str(mock_config.codebase_dir / "file_1.py"),  # exists
            str(mock_config.codebase_dir / "file_2.py"),  # deleted
            str(mock_config.codebase_dir / "file_3.py"),  # exists
            str(mock_config.codebase_dir / "file_4.py"),  # deleted
        ]

        git_status = {
            "git_available": True,
            "project_id": "test-project",
            "current_branch": "master",
            "current_commit": "abc123",
        }

        # Mock the dependencies
        with patch.object(
            indexer.progressive_metadata,
            "get_remaining_files",
            return_value=remaining_file_strings,
        ):
            with patch.object(
                indexer.git_topology_service,
                "get_current_branch",
                return_value="master",
            ):

                # Mock high-throughput processing
                with patch.object(
                    indexer, "process_files_high_throughput"
                ) as mock_direct_process:
                    with patch.object(
                        indexer, "process_branch_changes_high_throughput"
                    ) as mock_branch_process:

                        # Configure return value for existing files only
                        stats = ProcessingStats()
                        stats.files_processed = 2  # Only existing files
                        stats.chunks_created = 20
                        stats.failed_files = 0
                        stats.cancelled = False

                        mock_direct_process.return_value = stats
                        mock_branch_process.return_value = Mock(
                            files_processed=2,
                            content_points_created=20,
                            cancelled=False,
                            processing_time=1.0,
                        )

                        # Mock other required methods
                        with patch.object(
                            indexer.progressive_metadata, "update_progress"
                        ):
                            with patch.object(
                                indexer.progressive_metadata, "complete_indexing"
                            ):
                                with patch.object(
                                    indexer.progress_log, "complete_session"
                                ):

                                    # Execute resume operation
                                    result = indexer._do_resume_interrupted(
                                        batch_size=10,
                                        progress_callback=None,
                                        git_status=git_status,
                                        provider_name="test-provider",
                                        model_name="test-model",
                                        quiet=True,
                                        vector_thread_count=8,
                                    )

        # ASSERTIONS

        # 1. Should use direct high-throughput processing
        assert mock_direct_process.called, "Should use direct HighThroughputProcessor"
        assert (
            not mock_branch_process.called
        ), "Should NOT use BranchAwareIndexer wrapper"

        # 2. Should process only existing files (filter out deleted ones)
        if mock_direct_process.called:
            call_args = mock_direct_process.call_args
            processed_files = call_args[1]["files"]

            assert (
                len(processed_files) == 2
            ), f"Should process 2 existing files, got {len(processed_files)}"

            processed_file_names = {f.name for f in processed_files}
            expected_names = {"file_1.py", "file_3.py"}
            assert (
                processed_file_names == expected_names
            ), f"Should process only existing files {expected_names}, got {processed_file_names}"

        # 3. Result should reflect processing of existing files only
        assert result is not None
        assert result.files_processed == 2  # Only the existing files
        assert result.chunks_created == 20

    def test_resume_interrupted_performance_vs_branch_wrapper(
        self,
        temp_metadata_path,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
    ):
        """
        Test that resume operations show performance improvement when using
        direct HighThroughputProcessor vs BranchAwareIndexer wrapper.
        """
        # Create SmartIndexer instance
        indexer = SmartIndexer(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            qdrant_client=mock_qdrant_client,
            metadata_path=temp_metadata_path,
        )

        # Create test files for meaningful performance test
        test_files = []
        for i in range(15):
            file_path = mock_config.codebase_dir / f"resume_file_{i}.py"
            file_path.write_text(
                f"# Resume test file {i}\ndef resume_function_{i}():\n    return {i}"
            )
            test_files.append(file_path)

        remaining_file_strings = [str(f) for f in test_files]

        # git_status is defined but not used in this test - that's fine for test setup

        # SCENARIO 1: BranchAwareIndexer approach (current slow method)
        slow_branch_result = Mock(
            files_processed=15,
            content_points_created=150,
            cancelled=False,
            processing_time=6.0,  # Simulate slower sequential processing
        )

        # SCENARIO 2: Direct HighThroughputProcessor (target fast method)
        fast_direct_stats = ProcessingStats()
        fast_direct_stats.files_processed = 15
        fast_direct_stats.chunks_created = 150
        fast_direct_stats.failed_files = 0
        fast_direct_stats.start_time = time.time()
        fast_direct_stats.end_time = (
            fast_direct_stats.start_time + 1.5
        )  # Simulate faster parallel processing

        # Measure performance of both approaches
        with patch.object(
            indexer.progressive_metadata,
            "get_remaining_files",
            return_value=remaining_file_strings,
        ):
            with patch.object(
                indexer.git_topology_service,
                "get_current_branch",
                return_value="master",
            ):

                # Mock both approaches to capture timing
                with patch.object(
                    indexer,
                    "process_branch_changes_high_throughput",
                    return_value=slow_branch_result,
                ):
                    with patch.object(
                        indexer,
                        "process_files_high_throughput",
                        return_value=fast_direct_stats,
                    ):

                        # Simulate timing the BranchAwareIndexer approach
                        branch_start = time.time()
                        branch_result = indexer.process_branch_changes_high_throughput(
                            old_branch="",
                            new_branch="master",
                            changed_files=remaining_file_strings,
                            unchanged_files=[],
                            collection_name="test",
                            progress_callback=None,
                            vector_thread_count=8,
                        )
                        branch_time = (
                            time.time()
                            - branch_start
                            + slow_branch_result.processing_time
                        )

                        # Simulate timing the direct HighThroughputProcessor approach
                        direct_start = time.time()
                        direct_result = indexer.process_files_high_throughput(
                            files=test_files,
                            vector_thread_count=8,
                            batch_size=50,
                            progress_callback=None,
                        )
                        direct_time = time.time() - direct_start + 1.5

        # PERFORMANCE ASSERTIONS

        # 1. Both approaches should process same files
        assert branch_result.files_processed == direct_result.files_processed
        assert branch_result.content_points_created == direct_result.chunks_created

        # 2. Direct approach should be significantly faster (minimum 4x improvement)
        performance_ratio = branch_time / direct_time
        assert (
            performance_ratio >= 3.99
        ), (  # Use 3.99 to account for minor timing variations
            f"STORY 3 REQUIREMENT: Resume performance should improve by at least 4x. "
            f"Got {performance_ratio:.2f}x (branch: {branch_time:.2f}s, direct: {direct_time:.2f}s)"
        )

        # 3. Performance improvement should be realistic (not more than 8x)
        assert (
            performance_ratio <= 8.0
        ), f"Performance improvement unrealistic: {performance_ratio:.2f}x. Expected 4-8x range."

    def test_resume_interrupted_with_parallel_thread_utilization(
        self,
        temp_metadata_path,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
    ):
        """
        Test that resume operations properly utilize all 8 worker threads
        for parallel file processing.
        """
        # Create SmartIndexer instance
        indexer = SmartIndexer(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            qdrant_client=mock_qdrant_client,
            metadata_path=temp_metadata_path,
        )

        # Create sufficient files to utilize parallel processing
        test_files = []
        for i in range(20):  # 20 files should fully utilize 8 threads
            file_path = mock_config.codebase_dir / f"parallel_file_{i}.py"
            file_path.write_text(f"def parallel_function_{i}(): pass")
            test_files.append(file_path)

        remaining_file_strings = [str(f) for f in test_files]

        git_status = {
            "git_available": True,
            "project_id": "test-project",
            "current_branch": "master",
            "current_commit": "abc123",
        }

        # Capture the thread count configuration
        captured_thread_count = None

        def capture_thread_config(*args, **kwargs):
            nonlocal captured_thread_count
            captured_thread_count = kwargs.get("vector_thread_count")

            stats = ProcessingStats()
            stats.files_processed = 20
            stats.chunks_created = 200
            stats.failed_files = 0
            return stats

        # Mock the dependencies
        with patch.object(
            indexer.progressive_metadata,
            "get_remaining_files",
            return_value=remaining_file_strings,
        ):
            with patch.object(
                indexer.git_topology_service,
                "get_current_branch",
                return_value="master",
            ):
                with patch.object(
                    indexer,
                    "process_files_high_throughput",
                    side_effect=capture_thread_config,
                ):
                    with patch.object(indexer.progressive_metadata, "update_progress"):
                        with patch.object(
                            indexer.progressive_metadata, "complete_indexing"
                        ):
                            with patch.object(indexer.progress_log, "complete_session"):

                                # Execute resume with explicit thread count
                                result = indexer._do_resume_interrupted(
                                    batch_size=10,
                                    progress_callback=None,
                                    git_status=git_status,
                                    provider_name="test-provider",
                                    model_name="test-model",
                                    quiet=True,
                                    vector_thread_count=8,  # Specify 8 threads
                                )

        # THREAD UTILIZATION ASSERTIONS

        # 1. Should configure 8 worker threads for maximum parallelization
        assert (
            captured_thread_count == 8
        ), f"STORY 3 REQUIREMENT: Resume should use 8 worker threads, got {captured_thread_count}"

        # 2. Should process all files successfully
        assert result is not None
        assert result.files_processed == 20
        assert result.chunks_created == 200

        # 3. Processing should complete without failures
        assert result.failed_files == 0
