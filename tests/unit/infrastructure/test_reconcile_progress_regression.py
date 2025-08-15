"""
Test for reconcile operation progress display regression.

This test reproduces the issue where reconcile operations show individual
progress messages instead of using a progress bar like regular indexing.
"""

from pathlib import Path
from unittest.mock import Mock, patch
from code_indexer.services.branch_aware_indexer import BranchAwareIndexer
from code_indexer.services import QdrantClient
from code_indexer.config import Config
from ..services.test_vector_calculation_manager import MockEmbeddingProvider


class TestReconcileProgressRegression:
    """Test suite for reconcile progress bar regression."""

    def test_cli_progress_callback_behavior_simulation(self):
        """Test that demonstrates the CLI progress callback logic that the fix addresses."""

        # Simulate the CLI progress callback logic
        progress_bar_created = False
        individual_messages = []
        progress_bar_updates = []

        def simulate_cli_progress_callback(
            current, total, file_path, error=None, info=None
        ):
            nonlocal progress_bar_created, individual_messages, progress_bar_updates

            # This simulates the logic in cli.py lines 954-1024

            # Handle info messages before progress bar exists (cli.py line 963-965)
            if info and not progress_bar_created:
                individual_messages.append(f"ℹ️  {info}")
                return

            # Initialize progress bar on first real progress call (cli.py line 972-990)
            if not progress_bar_created and file_path != Path(""):
                progress_bar_created = True
                progress_bar_updates.append("Progress bar created")
                return

            # Handle info-only updates for status messages during processing (cli.py line 967-970)
            if file_path == Path("") and info and progress_bar_created:
                progress_bar_updates.append(f"Progress bar description: {info}")
                return

            # THE BUG: info with real path after progress bar creation (this is what was happening)
            if file_path != Path("") and info and progress_bar_created:
                # This path causes individual messages instead of progress bar updates
                individual_messages.append(f"ℹ️  {info}")  # This is the regression!
                return

            # Normal progress update
            if progress_bar_created:
                progress_bar_updates.append(
                    f"Progress: {current}/{total} - {file_path}"
                )

        # Test the OLD buggy behavior (what BranchAwareIndexer was doing before the fix)
        print("=== BEFORE FIX (buggy behavior) ===")
        individual_messages.clear()
        progress_bar_updates.clear()
        progress_bar_created = False

        # This simulates what BranchAwareIndexer was doing before the fix
        simulate_cli_progress_callback(
            1, 2, Path("file1.py"), info="1/2 files | Processing file1.py"
        )

        print(f"Individual messages: {individual_messages}")
        print(f"Progress bar updates: {progress_bar_updates}")

        # Before fix: should have created an individual message (the bug)
        assert (
            len(individual_messages) == 1
        ), "Before fix should create individual message"
        assert "1/2 files | Processing file1.py" in individual_messages[0]

        # Test the NEW fixed behavior (what BranchAwareIndexer does after the fix)
        print("\n=== AFTER FIX (correct behavior) ===")
        individual_messages.clear()
        progress_bar_updates.clear()
        progress_bar_created = False

        # First call to create progress bar
        simulate_cli_progress_callback(1, 2, Path("file1.py"))

        # This simulates what BranchAwareIndexer does after the fix
        simulate_cli_progress_callback(
            1, 2, Path(""), info="1/2 files | Processing file1.py"
        )

        print(f"Individual messages: {individual_messages}")
        print(f"Progress bar updates: {progress_bar_updates}")

        # After fix: should have updated progress bar description (correct)
        assert (
            len(individual_messages) == 0
        ), "After fix should not create individual messages"
        assert len(progress_bar_updates) >= 2, "After fix should update progress bar"
        assert any(
            "1/2 files | Processing file1.py" in update
            for update in progress_bar_updates
        ), "Progress bar should show the file processing info"

    def test_high_throughput_processor_progress_callback_format(self, local_tmp_path):
        """Test that HighThroughputProcessor uses correct progress callback format for CLI compatibility."""
        from code_indexer.services.high_throughput_processor import (
            HighThroughputProcessor,
        )

        # Setup test environment
        project_dir = local_tmp_path / "test_project"
        project_dir.mkdir()

        test_files = []
        for i in range(3):
            test_file = project_dir / f"test_file_{i}.py"
            test_file.write_text(f"print('hello {i}')")
            test_files.append(test_file)

        # Mock configuration and services
        config = Mock(spec=Config)
        config.codebase_dir = project_dir
        config.exclude_dirs = []
        config.exclude_files = []
        config.file_extensions = ["py"]

        config.qdrant = Mock()
        config.qdrant.vector_size = 768

        config.indexing = Mock()
        config.indexing.chunk_size = 200
        config.indexing.overlap_size = 50
        config.indexing.max_file_size = 1000000
        config.indexing.min_file_size = 1

        config.chunking = Mock()
        config.chunking.chunk_size = 200
        config.chunking.overlap_size = 50

        mock_qdrant = Mock(spec=QdrantClient)
        mock_qdrant.upsert_points.return_value = True
        mock_qdrant.create_point.return_value = {"id": "test-point"}

        mock_embedding_provider = MockEmbeddingProvider(delay=0.01)

        processor = HighThroughputProcessor(
            config=config,
            embedding_provider=mock_embedding_provider,
            qdrant_client=mock_qdrant,
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
            test_files,
            vector_thread_count=2,
            batch_size=10,
            progress_callback=progress_callback,
        )

        # Verify no calls use the problematic "real path + info" pattern
        problematic_calls = [
            call
            for call in progress_calls
            if call["file_path"] != "." and call["info"] is not None
        ]

        assert len(problematic_calls) == 0, (
            f"Found {len(problematic_calls)} problematic progress calls that would cause "
            f"individual messages instead of progress bar updates. "
            f"Examples: {problematic_calls[:3]}"
        )

        # Verify all calls with info use empty path (represented as '.' when converted to string)
        info_calls = [call for call in progress_calls if call["info"] is not None]
        assert len(info_calls) > 0, "Should have progress calls with info messages"

        for call in info_calls:
            assert (
                call["file_path"] == "."
            ), f"Progress calls with info should use empty path, but got: {call['file_path']}"

    def test_branch_aware_indexer_progress_callback_format(self, local_tmp_path):
        """Test that BranchAwareIndexer calls progress callback with correct parameters."""

        # Setup test environment
        project_dir = local_tmp_path / "test_project"
        project_dir.mkdir()

        test_file = project_dir / "test_file.py"
        test_file.write_text("print('hello')")

        # Mock configuration and services
        config = Mock(spec=Config)
        config.codebase_dir = project_dir

        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = [0.1] * 768
        mock_embedding_provider.get_current_model.return_value = "test-model"
        mock_embedding_provider.get_model_info.return_value = {"dimensions": 768}

        mock_qdrant_client = Mock()
        mock_qdrant_client.create_point.return_value = {"id": "test-id"}
        mock_qdrant_client.upsert_points.return_value = True
        mock_qdrant_client.scroll_points.return_value = (
            [],
            None,
        )  # For branch isolation

        mock_text_chunker = Mock()
        mock_text_chunker.chunk_file.return_value = [
            {"text": "print('hello')", "chunk_index": 0, "total_chunks": 1}
        ]

        # Create BranchAwareIndexer
        indexer = BranchAwareIndexer(
            mock_qdrant_client, mock_embedding_provider, mock_text_chunker, config
        )

        # Track progress callback calls
        progress_calls = []

        def progress_callback(current, total, file_path, error=None, info=None):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "error": error,
                    "info": info,
                }
            )
            return None

        # Mock file commit lookup
        with patch.object(indexer, "_get_file_commit", return_value="abc123"):
            with patch.object(indexer, "_content_exists", return_value=False):
                with patch.object(indexer, "_detect_language", return_value="python"):
                    with patch.object(
                        indexer,
                        "_determine_working_dir_status",
                        return_value="committed",
                    ):

                        # Call index_branch_changes
                        indexer.index_branch_changes(
                            old_branch="",
                            new_branch="main",
                            changed_files=["test_file.py"],
                            unchanged_files=[],
                            collection_name="test-collection",
                            progress_callback=progress_callback,
                        )

        # Analyze the calls
        print(f"Total progress calls: {len(progress_calls)}")
        for i, call in enumerate(progress_calls):
            print(
                f"  Call {i}: current={call['current']}, total={call['total']}, file_path='{call['file_path']}', info='{call['info']}'"
            )

        assert len(progress_calls) > 0, "No progress callback calls made"

        # Check for the CORRECT pattern: info parameter with empty file_path for progress bar
        # With the fixed CLI, this should work correctly and use progress bar
        correct_calls = [
            call
            for call in progress_calls
            if call["info"]
            and call["file_path"] == "."  # Empty path indicator for progress bar mode
        ]

        assert len(correct_calls) > 0, (
            "BranchAwareIndexer should call progress_callback with empty file_path and info - "
            "this is the correct pattern for CLI progress bar updates"
        )

        # Verify the info format is correct: "files (%) | emb/s {icon} | threads | filename"
        for call in correct_calls:
            info = call["info"]
            assert (
                "files (" in info and "%) |" in info
            ), f"Should show file progress format in: {info}"
            # Updated to account for throttling icons (⚡🟡🔴)
            assert (
                "emb/s ⚡ |" in info
                or "emb/s 🟡 |" in info
                or "emb/s 🔴 |" in info
                or "emb/s |" in info
            ), f"Should show emb/s format with optional throttling icon in: {info}"
            assert "threads |" in info, f"Should show thread count in: {info}"
