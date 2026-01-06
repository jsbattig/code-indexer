"""Test thread ramp-up fix for temporal indexer.

CRITICAL BUG FIX TEST (Story 2):
User reported: "threads start at 3, slowly grow to 4 then 6, and get stuck instead
of immediately using all 8 configured threads"

Root cause: Current implementation uses Queue-based pattern WITHOUT pre-populating
queue before starting workers AND acquires slots inside diff loop (not at worker start).

MANDATORY FIX: Refactor _process_commits_parallel() to follow EXACT pattern from
HighThroughputProcessor.process_files_high_throughput():
1. Pre-populate Queue with ALL commits BEFORE creating ThreadPoolExecutor
2. Create ThreadPoolExecutor with max_workers=thread_count
3. Submit ALL workers immediately: [executor.submit(worker) for _ in range(thread_count)]
4. Workers: acquire_slot() → process → release_slot()

This ensures ALL 8 threads become active immediately, not gradually.
"""

import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


class TestTemporalIndexerThreadRampup(unittest.TestCase):
    """Test that all threads become active immediately (not gradually)."""

    def test_all_threads_active_immediately(self):
        """Test that ALL configured threads are active within 100ms of worker start.

        CRITICAL REQUIREMENT: With 8 configured threads, all 8 should be active
        immediately when processing starts, NOT ramping up gradually (3→4→6→stuck).
        """
        # Setup
        test_dir = Path("/tmp/test-repo-thread-rampup")
        thread_count = 8
        commit_count = 100  # Enough commits to saturate threads

        # Track slot acquisition timeline (indicates thread activity)
        slot_acquisition_timeline = []
        timeline_lock = threading.Lock()

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = thread_count
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()  # No existing points

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
            patch(
                "src.code_indexer.services.clean_slot_tracker.CleanSlotTracker"
            ) as mock_slot_tracker_class,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create mock slot tracker to track acquisition timing
            mock_slot_tracker = Mock()
            slot_counter = [0]
            start_time = [None]

            def mock_acquire_slot(file_data):
                """Track slot acquisition timing."""
                if start_time[0] is None:
                    start_time[0] = time.time()

                slot_id = slot_counter[0]
                slot_counter[0] += 1

                elapsed_ms = (time.time() - start_time[0]) * 1000
                with timeline_lock:
                    slot_acquisition_timeline.append((elapsed_ms, slot_id))

                return slot_id

            mock_slot_tracker.acquire_slot = Mock(side_effect=mock_acquire_slot)
            mock_slot_tracker.release_slot = Mock()
            mock_slot_tracker.update_slot = Mock()
            mock_slot_tracker.get_concurrent_files_data = Mock(return_value=[])
            mock_slot_tracker_class.return_value = mock_slot_tracker

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock progressive metadata to return empty set (no completed commits)
            indexer.progressive_metadata = Mock()
            indexer.progressive_metadata.load_completed.return_value = set()
            indexer.progressive_metadata.save_completed = Mock()

            # Mock diff scanner to simulate real work
            # Return ONE diff per commit to ensure slot acquisition happens
            indexer.diff_scanner = Mock()

            def get_diffs_side_effect(commit_hash):
                # Simulate some work (10ms per commit)
                time.sleep(0.01)
                return [
                    Mock(
                        file_path=f"file_{commit_hash[:8]}.py",
                        diff_content=f"test diff for {commit_hash}",
                        diff_type="modified",
                        blob_hash=None,
                    )
                ]

            indexer.diff_scanner.get_diffs_for_commit = Mock(
                side_effect=get_diffs_side_effect
            )

            # Mock chunker to avoid real chunking
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = []  # No chunks = fast path

            # Create test commits
            commits = [
                CommitInfo(
                    hash=f"commit{i:03d}abcd1234",
                    timestamp=1700000000 + i,
                    author_name="Test Author",
                    author_email="test@example.com",
                    message=f"Test commit {i}",
                    parent_hashes="",
                )
                for i in range(commit_count)
            ]

            # Mock embedding provider and vector manager
            mock_embedding_provider = Mock()
            mock_vector_manager = Mock()

            # Run parallel processing
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=mock_embedding_provider,
                vector_manager=mock_vector_manager,
                progress_callback=None,
            )

            # CRITICAL ASSERTION: First 8 slot acquisitions should happen within 100ms
            # (indicating all threads started immediately)
            first_8_acquisitions = slot_acquisition_timeline[:8]

            # All 8 should happen within 100ms
            max_time_for_8_threads = max(
                (t for t, _ in first_8_acquisitions), default=0
            )

            self.assertLess(
                max_time_for_8_threads,
                100,  # 100ms threshold for all 8 threads to acquire slots
                f"First 8 slot acquisitions should happen within 100ms, but took {max_time_for_8_threads:.1f}ms. "
                f"Timeline: {first_8_acquisitions}",
            )

    def test_worker_acquires_slot_immediately_not_in_diff_loop(self):
        """Test that workers acquire slots at the START of commit processing.

        CRITICAL BUG: Current implementation acquires slots INSIDE the diff loop,
        causing gradual ramp-up. Workers should acquire slots BEFORE processing
        any diffs, ensuring all threads are active immediately.
        """
        # Setup
        test_dir = Path("/tmp/test-repo-slot-acquisition")
        thread_count = 8

        # Track slot acquisition timing
        slot_acquisition_timeline = []
        timeline_lock = threading.Lock()

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = thread_count
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
            patch(
                "src.code_indexer.services.clean_slot_tracker.CleanSlotTracker"
            ) as mock_slot_tracker_class,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create mock slot tracker
            mock_slot_tracker = Mock()
            slot_counter = [0]  # Track number of acquire calls

            def mock_acquire_slot(file_data):
                """Record slot acquisition timing."""
                slot_id = slot_counter[0]
                slot_counter[0] += 1

                elapsed_ms = (time.time() - start_time) * 1000
                with timeline_lock:
                    slot_acquisition_timeline.append((elapsed_ms, slot_id))

                return slot_id

            mock_slot_tracker.acquire_slot = Mock(side_effect=mock_acquire_slot)
            mock_slot_tracker.release_slot = Mock()
            mock_slot_tracker.update_slot = Mock()
            mock_slot_tracker.get_concurrent_files_data = Mock(return_value=[])
            mock_slot_tracker_class.return_value = mock_slot_tracker

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock diff scanner
            indexer.diff_scanner = Mock()
            indexer.diff_scanner.get_diffs_for_commit.return_value = [
                Mock(
                    file_path="test.py",
                    diff_content="test diff",
                    diff_type="modified",
                    blob_hash=None,
                )
            ]

            # Mock chunker
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = []

            # Create commits
            commits = [
                CommitInfo(
                    hash=f"commit{i:03d}",
                    timestamp=1700000000 + i,
                    author_name="Test",
                    author_email="test@example.com",
                    message=f"Commit {i}",
                    parent_hashes="",
                )
                for i in range(20)  # 20 commits, 8 threads
            ]

            # Start timing
            start_time = time.time()

            # Run parallel processing
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=Mock(),
                progress_callback=None,
            )

            # CRITICAL ASSERTION: First 8 slot acquisitions should happen within 50ms
            # (indicating all threads start processing immediately)
            first_8_acquisitions = slot_acquisition_timeline[:8]

            # All 8 should happen within 50ms
            max_time_for_8_threads = max(
                (t for t, _ in first_8_acquisitions), default=0
            )

            self.assertLess(
                max_time_for_8_threads,
                50,  # 50ms threshold for all 8 threads to acquire slots
                f"First 8 slot acquisitions should happen within 50ms, but took {max_time_for_8_threads:.1f}ms. "
                f"Timeline: {first_8_acquisitions}",
            )

    def test_queue_prepopulated_before_executor_creation(self):
        """Test that Queue is pre-populated with ALL commits before ThreadPoolExecutor starts.

        CRITICAL PATTERN: Queue must be fully populated BEFORE any workers start,
        matching HighThroughputProcessor pattern (lines 456-458, then 472-473).
        """
        # Setup
        test_dir = Path("/tmp/test-repo-prepopulation")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 8
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        # Track Queue.put() calls vs ThreadPoolExecutor creation
        queue_put_count = [0]
        executor_created = [False]

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
            patch(
                "src.code_indexer.services.temporal.temporal_indexer.Queue"
            ) as mock_queue_class,
            patch(
                "src.code_indexer.services.temporal.temporal_indexer.ThreadPoolExecutor"
            ) as mock_executor_class,
            patch(
                "src.code_indexer.services.temporal.temporal_indexer.as_completed"
            ) as mock_as_completed,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Mock Queue
            from queue import Empty

            mock_queue = Mock()
            commits_to_return = [Mock(hash=f"commit{i}") for i in range(10)]
            mock_queue.get_nowait = Mock(side_effect=commits_to_return + [Empty()])
            mock_queue.task_done = Mock()

            def mock_put(item):
                """Track Queue.put() calls."""
                # Ensure ThreadPoolExecutor hasn't been created yet
                if executor_created[0]:
                    raise AssertionError(
                        "Queue.put() called AFTER ThreadPoolExecutor creation. "
                        "Queue must be pre-populated BEFORE executor is created!"
                    )
                queue_put_count[0] += 1

            mock_queue.put = Mock(side_effect=mock_put)
            mock_queue_class.return_value = mock_queue

            # Mock ThreadPoolExecutor
            mock_executor = Mock()
            mock_executor.__enter__ = Mock(return_value=mock_executor)
            mock_executor.__exit__ = Mock(return_value=None)

            futures_list = []

            def mock_submit(func):
                """Track submit() calls and return proper mock future."""
                future = Mock()
                future.result = Mock(return_value=None)
                futures_list.append(future)
                return future

            mock_executor.submit = Mock(side_effect=mock_submit)

            def mock_executor_init(*args, **kwargs):
                """Track ThreadPoolExecutor creation."""
                executor_created[0] = True
                return mock_executor

            mock_executor_class.side_effect = mock_executor_init

            # as_completed should just return the futures immediately
            mock_as_completed.side_effect = lambda futures: futures

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock diff scanner
            indexer.diff_scanner = Mock()
            indexer.diff_scanner.get_diffs_for_commit.return_value = []

            # Create commits
            commits = [Mock(hash=f"commit{i}") for i in range(10)]

            # Run parallel processing
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=Mock(),
                progress_callback=None,
            )

            # CRITICAL ASSERTION: All commits should be added to queue BEFORE executor
            self.assertEqual(
                queue_put_count[0],
                10,
                f"Expected all 10 commits in queue before executor creation, "
                f"but only {queue_put_count[0]} were added",
            )
            self.assertTrue(
                executor_created[0], "ThreadPoolExecutor should have been created"
            )

    def test_all_workers_submitted_immediately(self):
        """Test that ALL workers are submitted to ThreadPoolExecutor at once.

        CRITICAL PATTERN: Should use list comprehension to submit all workers:
        futures = [executor.submit(worker) for _ in range(thread_count)]

        NOT submitting workers one at a time or conditionally.
        """
        # Setup
        test_dir = Path("/tmp/test-repo-workers")
        thread_count = 8

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = thread_count
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock diff scanner
            indexer.diff_scanner = Mock()
            indexer.diff_scanner.get_diffs_for_commit.return_value = []

            # Create commits
            commits = [Mock(hash=f"commit{i}") for i in range(20)]

            # Mock the ThreadPoolExecutor.submit() to count calls

            submit_calls = []

            with (
                patch(
                    "src.code_indexer.services.temporal.temporal_indexer.ThreadPoolExecutor"
                ) as mock_executor_class,
                patch(
                    "src.code_indexer.services.temporal.temporal_indexer.as_completed"
                ) as mock_as_completed,
            ):
                mock_executor = Mock()
                mock_executor.__enter__ = Mock(return_value=mock_executor)
                mock_executor.__exit__ = Mock(return_value=None)

                futures_list = []

                def mock_submit(func):
                    """Track submit() calls."""
                    submit_calls.append(time.time())
                    future = Mock()
                    future.result = Mock(return_value=None)
                    futures_list.append(future)
                    return future

                mock_executor.submit = Mock(side_effect=mock_submit)
                mock_executor_class.return_value = mock_executor

                # as_completed should just return the futures immediately
                mock_as_completed.side_effect = lambda futures: futures

                # Run parallel processing
                indexer._process_commits_parallel(
                    commits=commits,
                    embedding_provider=Mock(),
                    vector_manager=Mock(),
                    progress_callback=None,
                )

                # CRITICAL ASSERTION: Exactly thread_count workers should be submitted
                self.assertEqual(
                    len(submit_calls),
                    thread_count,
                    f"Expected exactly {thread_count} workers submitted, "
                    f"but got {len(submit_calls)}",
                )

                # All submits should happen within 10ms (immediate submission)
                if len(submit_calls) > 1:
                    time_delta = (submit_calls[-1] - submit_calls[0]) * 1000
                    self.assertLess(
                        time_delta,
                        10,  # 10ms threshold
                        f"All workers should be submitted within 10ms, but took {time_delta:.1f}ms",
                    )

    def test_filename_set_correctly_from_slot_acquisition(self):
        """Test that workers acquire slots with placeholder, then update with actual filename.

        CORRECT PATTERN (NEW - for temporal indexing):
        1. Acquire slot IMMEDIATELY with placeholder ("Analyzing commit")
        2. Get diffs (potentially slow git operation)
        3. Update slot with ACTUAL filename during diff processing

        This ensures all threads are visible immediately (not blocked on git operations).
        This test verifies that:
        1. Slots are acquired with placeholder initially
        2. Then updated with actual filename during diff processing
        """
        # Setup
        test_dir = Path("/tmp/test-repo-filename-acquisition")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 4
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        # Track FileData passed to acquire_slot
        acquired_file_data = []
        timeline_lock = threading.Lock()

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
            patch(
                "src.code_indexer.services.clean_slot_tracker.CleanSlotTracker"
            ) as mock_slot_tracker_class,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create mock slot tracker
            mock_slot_tracker = Mock()
            slot_counter = [0]

            def mock_acquire_slot(file_data):
                """Capture FileData passed to acquire_slot."""
                slot_id = slot_counter[0]
                slot_counter[0] += 1

                # Store the FileData for inspection
                with timeline_lock:
                    acquired_file_data.append(
                        {
                            "slot_id": slot_id,
                            "filename": file_data.filename,
                            "file_size": file_data.file_size,
                            "status": file_data.status,
                        }
                    )

                return slot_id

            mock_slot_tracker.acquire_slot = Mock(side_effect=mock_acquire_slot)
            mock_slot_tracker.release_slot = Mock()
            mock_slot_tracker.update_slot = Mock()
            mock_slot_tracker.get_concurrent_files_data = Mock(return_value=[])
            mock_slot_tracker_class.return_value = mock_slot_tracker

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock diff scanner to return multiple diffs per commit
            indexer.diff_scanner = Mock()

            def get_diffs_side_effect(commit_hash):
                # Return 3 diffs per commit with different filenames
                return [
                    Mock(
                        file_path=f"src/module_{commit_hash[:8]}_file1.py",
                        diff_content=f"diff content 1 for {commit_hash}"
                        * 100,  # ~3500 bytes
                        diff_type="modified",
                        blob_hash=None,
                    ),
                    Mock(
                        file_path=f"tests/test_{commit_hash[:8]}_file2.py",
                        diff_content=f"diff content 2 for {commit_hash}"
                        * 80,  # ~2800 bytes
                        diff_type="added",
                        blob_hash=None,
                    ),
                    Mock(
                        file_path=f"docs/{commit_hash[:8]}_readme.md",
                        diff_content=f"diff content 3 for {commit_hash}"
                        * 60,  # ~2100 bytes
                        diff_type="modified",
                        blob_hash=None,
                    ),
                ]

            indexer.diff_scanner.get_diffs_for_commit = Mock(
                side_effect=get_diffs_side_effect
            )

            # Mock chunker
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = []

            # Create commits
            commits = [
                CommitInfo(
                    hash=f"commit{i:03d}abcd1234",
                    timestamp=1700000000 + i,
                    author_name="Test",
                    author_email="test@example.com",
                    message=f"Commit {i}",
                    parent_hashes="",
                )
                for i in range(8)  # 8 commits for 4 threads
            ]

            # Create proper vector_manager mock with required attributes
            vector_manager = Mock()
            vector_manager.cancellation_event = threading.Event()
            vector_manager.embedding_provider = Mock()
            vector_manager.embedding_provider.get_current_model = Mock(
                return_value="voyage-code-2"
            )
            vector_manager.embedding_provider._get_model_token_limit = Mock(
                return_value=120000
            )
            vector_manager.submit_batch_task = Mock(
                return_value=Mock(result=Mock(return_value=[]))
            )

            # Run parallel processing
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=vector_manager,
                progress_callback=None,
            )

            # CRITICAL ASSERTIONS: Slots acquired with placeholder, updated with actual filename
            self.assertGreater(
                len(acquired_file_data), 0, "Should have acquired at least one slot"
            )

            # Check that slots ARE acquired with placeholder filenames (NEW PATTERN)
            placeholder_slots = [
                fd
                for fd in acquired_file_data
                if "analyzing commit" in fd["filename"].lower()
            ]
            self.assertGreater(
                len(placeholder_slots),
                0,
                f"Should have slots acquired with placeholder 'Analyzing commit'. "
                f"Found {len(placeholder_slots)} placeholder slots. "
                f"This is CORRECT - slots should be acquired immediately with placeholder.",
            )

            # Check that ALL slots have meaningful filenames (even placeholders have commit hash)
            for fd in acquired_file_data:
                self.assertIsNotNone(
                    fd["filename"], f"Slot {fd['slot_id']} has None filename"
                )
                self.assertNotEqual(
                    fd["filename"], "", f"Slot {fd['slot_id']} has empty filename"
                )
                # Should have pattern "commitXXX - ..." (either placeholder or actual file)
                self.assertIn(
                    " - ",
                    fd["filename"],
                    f"Slot {fd['slot_id']} filename '{fd['filename']}' should follow pattern 'commitXXX - ...'",
                )

            # File sizes for initial acquisition with placeholder are zero (CORRECT)
            # They get updated later during diff processing
            for fd in placeholder_slots:
                self.assertEqual(
                    fd["file_size"],
                    0,
                    f"Placeholder slot {fd['slot_id']} should have zero file_size initially. "
                    f"File sizes are updated later during diff processing.",
                )

    def test_update_slot_called_with_filename_and_size(self):
        """Test that update_slot() is called with filename and diff_size during diff processing.

        CRITICAL DISPLAY BUG: Lines 414-417 calculate current_filename but don't pass it
        to update_slot(), causing display to show "starting" instead of actual filename.

        FIX: Pass filename and diff_size to update_slot() call.
        """
        # Setup
        test_dir = Path("/tmp/test-update-slot-filename")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 2
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        # Track update_slot calls
        update_slot_calls = []
        timeline_lock = threading.Lock()

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
            patch(
                "src.code_indexer.services.clean_slot_tracker.CleanSlotTracker"
            ) as mock_slot_tracker_class,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create mock slot tracker
            mock_slot_tracker = Mock()
            slot_counter = [0]

            def mock_acquire_slot(file_data):
                slot_id = slot_counter[0]
                slot_counter[0] += 1
                return slot_id

            def mock_update_slot(slot_id, status, filename=None, file_size=None):
                """Capture update_slot calls with all parameters."""
                with timeline_lock:
                    update_slot_calls.append(
                        {
                            "slot_id": slot_id,
                            "status": status,
                            "filename": filename,
                            "file_size": file_size,
                        }
                    )

            mock_slot_tracker.acquire_slot = Mock(side_effect=mock_acquire_slot)
            mock_slot_tracker.release_slot = Mock()
            mock_slot_tracker.update_slot = Mock(side_effect=mock_update_slot)
            mock_slot_tracker.get_concurrent_files_data = Mock(return_value=[])
            mock_slot_tracker_class.return_value = mock_slot_tracker

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock progressive metadata to return empty set (no completed commits)
            indexer.progressive_metadata = Mock()
            indexer.progressive_metadata.load_completed.return_value = set()
            indexer.progressive_metadata.save_completed = Mock()

            # Mock diff scanner to return diffs with known content
            indexer.diff_scanner = Mock()

            def get_diffs_side_effect(commit_hash):
                return [
                    Mock(
                        file_path="src/auth/login_handler.py",
                        diff_content="def login(user): pass" * 50,  # ~1100 bytes
                        diff_type="modified",
                        blob_hash=None,
                    ),
                    Mock(
                        file_path="tests/test_auth.py",
                        diff_content="def test_login(): assert True" * 30,  # ~900 bytes
                        diff_type="added",
                        blob_hash=None,
                    ),
                ]

            indexer.diff_scanner.get_diffs_for_commit = Mock(
                side_effect=get_diffs_side_effect
            )

            # Mock chunker
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = []

            # Create single commit for focused test
            commits = [
                CommitInfo(
                    hash="abc123def456",
                    timestamp=1700000000,
                    author_name="Test",
                    author_email="test@example.com",
                    message="Test commit",
                    parent_hashes="",
                )
            ]

            # Create proper vector_manager mock with required attributes
            vector_manager = Mock()
            vector_manager.cancellation_event = threading.Event()
            vector_manager.embedding_provider = Mock()
            vector_manager.embedding_provider.get_current_model = Mock(
                return_value="voyage-code-2"
            )
            vector_manager.embedding_provider._get_model_token_limit = Mock(
                return_value=120000
            )
            vector_manager.submit_batch_task = Mock(
                return_value=Mock(result=Mock(return_value=[]))
            )

            # Run parallel processing
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=vector_manager,
                progress_callback=None,
            )

            # CRITICAL ASSERTIONS: update_slot must be called with filename and file_size

            # Filter for CHUNKING status updates (during diff processing)
            from src.code_indexer.services.clean_slot_tracker import FileStatus

            chunking_updates = [
                call
                for call in update_slot_calls
                if call["status"] == FileStatus.CHUNKING
            ]

            self.assertGreater(
                len(chunking_updates),
                0,
                "Should have update_slot calls with CHUNKING status during diff processing",
            )

            # Check that ALL CHUNKING updates have filename and file_size
            for update in chunking_updates:
                self.assertIsNotNone(
                    update["filename"],
                    f"update_slot(slot_id={update['slot_id']}, status=CHUNKING) called without filename parameter. "
                    f"Must pass calculated current_filename (e.g., 'abc123de - login_handler.py')",
                )
                self.assertIsNotNone(
                    update["file_size"],
                    f"update_slot(slot_id={update['slot_id']}, status=CHUNKING) called without file_size parameter. "
                    f"Must pass diff_size calculated from diff_info.diff_content",
                )

                # Verify filename format
                self.assertIn(
                    " - ",
                    update["filename"],
                    f"Filename '{update['filename']}' should follow pattern 'commitXXX - filename.ext'",
                )

                # Verify filename contains actual file from diffs
                filename_only = (
                    update["filename"].split(" - ", 1)[1]
                    if " - " in update["filename"]
                    else ""
                )
                self.assertIn(
                    filename_only,
                    ["login_handler.py", "test_auth.py"],
                    f"Filename '{filename_only}' should be from actual diffs (login_handler.py or test_auth.py)",
                )

                # Verify file_size is positive
                self.assertGreater(
                    update["file_size"],
                    0,
                    f"file_size should be positive, got {update['file_size']}",
                )

    def test_commits_filtered_before_queue_population(self):
        """Test that progressive metadata filtering happens BEFORE queue population.

        CRITICAL ARCHITECTURE REQUIREMENT:
        1. Load completed commits from progressive metadata
        2. Filter commits list to only unindexed commits
        3. THEN populate queue with filtered list
        4. THEN create threadpool

        WRONG PATTERN (current):
        - Filtering happens inside worker threads (per-commit check)
        - Queue populated with ALL commits
        - Workers do redundant completed checks

        CORRECT PATTERN:
        - Filter commits ONCE upfront (not per-thread)
        - Queue populated with ONLY unindexed commits
        - Workers never see completed commits
        """
        # Setup
        test_dir = Path("/tmp/test-repo-filtering")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 4
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock progressive metadata to return some completed commits
            indexer.progressive_metadata = Mock()
            completed_commits = {
                f"commit00{i}" for i in range(5)
            }  # commits 0-4 completed
            indexer.progressive_metadata.load_completed = Mock(
                return_value=completed_commits
            )
            indexer.progressive_metadata.save_completed = Mock()

            # Mock diff scanner
            indexer.diff_scanner = Mock()
            indexer.diff_scanner.get_diffs_for_commit.return_value = []

            # Create 10 commits (5 completed, 5 unindexed)
            all_commits = [
                CommitInfo(
                    hash=f"commit00{i}",
                    timestamp=1700000000 + i,
                    author_name="Test",
                    author_email="test@example.com",
                    message=f"Commit {i}",
                    parent_hashes="",
                )
                for i in range(10)
            ]

            # Track which commits reach worker threads
            commits_seen_by_workers = []
            commits_lock = threading.Lock()

            # Patch worker to track which commits it sees
            original_get_diffs = indexer.diff_scanner.get_diffs_for_commit

            def track_commits(commit_hash):
                with commits_lock:
                    commits_seen_by_workers.append(commit_hash)
                return original_get_diffs(commit_hash)

            indexer.diff_scanner.get_diffs_for_commit = Mock(side_effect=track_commits)

            # Create proper vector_manager mock with required attributes
            vector_manager = Mock()
            vector_manager.cancellation_event = (
                threading.Event()
            )  # Not set, so workers can run
            vector_manager.embedding_provider = Mock()
            vector_manager.embedding_provider.get_current_model = Mock(
                return_value="voyage-code-2"
            )
            vector_manager.embedding_provider._get_model_token_limit = Mock(
                return_value=120000
            )
            vector_manager.submit_batch_task = Mock(
                return_value=Mock(result=Mock(return_value=[]))
            )

            # Run parallel processing with ALL commits (including completed)
            # Pass reconcile=False to enable progressive metadata filtering
            indexer._process_commits_parallel(
                commits=all_commits,
                embedding_provider=Mock(),
                vector_manager=vector_manager,
                progress_callback=None,
                reconcile=False,  # Enable filtering of completed commits
            )

            # CRITICAL ASSERTIONS: Workers should ONLY see unindexed commits
            # Commits 0-4 are completed, so workers should only see commits 5-9

            # Wait for all workers to complete
            time.sleep(0.1)

            with commits_lock:
                seen_hashes = set(commits_seen_by_workers)

            # Should only see commits 5-9 (NOT 0-4)
            expected_unindexed = {f"commit00{i}" for i in range(5, 10)}

            self.assertEqual(
                seen_hashes,
                expected_unindexed,
                f"Workers should only process unindexed commits {expected_unindexed}, "
                f"but saw {seen_hashes}. "
                f"This means filtering happened inside workers (WRONG) instead of upfront (CORRECT).",
            )

            # Verify NO completed commits were processed
            completed_seen = seen_hashes & completed_commits
            self.assertEqual(
                len(completed_seen),
                0,
                f"Workers should NEVER see completed commits, but processed: {completed_seen}. "
                f"Filtering must happen BEFORE queue population, not inside workers.",
            )

    def test_slot_updated_with_analyzing_commit_before_diffs(self):
        """Test that slot is updated with 'Analyzing commit' status BEFORE get_diffs().

        CRITICAL FIX: Slot must be acquired immediately with placeholder, then UPDATED
        to "Analyzing commit" status BEFORE calling get_diffs_for_commit().

        This ensures all 8 threads are visible immediately, even while waiting for git.
        """
        # Setup
        test_dir = Path("/tmp/test-analyzing-commit-status")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 4
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        # Track update_slot calls and get_diffs timing
        update_slot_timeline = []
        get_diffs_timeline = []
        timeline_lock = threading.Lock()
        start_time = [None]

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
            patch(
                "src.code_indexer.services.clean_slot_tracker.CleanSlotTracker"
            ) as mock_slot_tracker_class,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create mock slot tracker
            mock_slot_tracker = Mock()
            slot_counter = [0]

            def mock_acquire_slot(file_data):
                if start_time[0] is None:
                    start_time[0] = time.time()
                slot_id = slot_counter[0]
                slot_counter[0] += 1
                return slot_id

            def mock_update_slot(slot_id, status, filename=None, file_size=None):
                """Capture update_slot calls with timing."""
                elapsed_ms = (time.time() - start_time[0]) * 1000
                with timeline_lock:
                    update_slot_timeline.append(
                        {
                            "elapsed_ms": elapsed_ms,
                            "slot_id": slot_id,
                            "status": status,
                            "filename": filename,
                            "file_size": file_size,
                        }
                    )

            mock_slot_tracker.acquire_slot = Mock(side_effect=mock_acquire_slot)
            mock_slot_tracker.release_slot = Mock()
            mock_slot_tracker.update_slot = Mock(side_effect=mock_update_slot)
            mock_slot_tracker.get_concurrent_files_data = Mock(return_value=[])
            mock_slot_tracker_class.return_value = mock_slot_tracker

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock progressive metadata
            indexer.progressive_metadata = Mock()
            indexer.progressive_metadata.load_completed.return_value = set()
            indexer.progressive_metadata.save_completed = Mock()

            # Mock diff scanner with SLOW get_diffs (simulates git operations)
            indexer.diff_scanner = Mock()

            def get_diffs_side_effect(commit_hash):
                # Initialize start_time if not set (in case get_diffs called before acquire_slot)
                if start_time[0] is None:
                    start_time[0] = time.time()

                # Record timing of get_diffs call
                elapsed_ms = (time.time() - start_time[0]) * 1000
                with timeline_lock:
                    get_diffs_timeline.append(
                        {"elapsed_ms": elapsed_ms, "commit_hash": commit_hash}
                    )

                # Simulate slow git operation (50ms)
                time.sleep(0.05)
                return [
                    Mock(
                        file_path="test.py",
                        diff_content="test diff",
                        diff_type="modified",
                        blob_hash=None,
                    )
                ]

            indexer.diff_scanner.get_diffs_for_commit = Mock(
                side_effect=get_diffs_side_effect
            )

            # Mock chunker
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = []

            # Create commits
            commits = [
                CommitInfo(
                    hash=f"commit{i:03d}",
                    timestamp=1700000000 + i,
                    author_name="Test",
                    author_email="test@example.com",
                    message=f"Commit {i}",
                    parent_hashes="",
                )
                for i in range(8)
            ]

            # Create proper vector_manager mock with required attributes
            vector_manager = Mock()
            vector_manager.cancellation_event = threading.Event()
            vector_manager.embedding_provider = Mock()
            vector_manager.embedding_provider.get_current_model = Mock(
                return_value="voyage-code-2"
            )
            vector_manager.embedding_provider._get_model_token_limit = Mock(
                return_value=120000
            )
            vector_manager.submit_batch_task = Mock(
                return_value=Mock(result=Mock(return_value=[]))
            )

            # Run parallel processing
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=vector_manager,
                progress_callback=None,
            )

            # CRITICAL ASSERTIONS: Slot updates should happen BEFORE get_diffs
            # (This indicates slot was acquired immediately, not after get_diffs)

            # Group updates by slot_id to find FIRST update for each slot
            first_updates_by_slot = {}
            for update in update_slot_timeline:
                slot_id = update["slot_id"]
                if slot_id not in first_updates_by_slot:
                    first_updates_by_slot[slot_id] = update

            # Should have first updates for 8 slots (one per thread/commit)
            self.assertEqual(
                len(first_updates_by_slot),
                8,
                f"Should have first updates for 8 slots, got {len(first_updates_by_slot)}",
            )

            # Each first update should happen BEFORE any get_diffs call for that commit
            for slot_id, first_update in first_updates_by_slot.items():
                update_time = first_update["elapsed_ms"]

                # Find get_diffs calls that happened BEFORE this update
                # (This would be WRONG - update should come first)
                [d for d in get_diffs_timeline if d["elapsed_ms"] < update_time]

                # For THIS slot, we expect the update to happen BEFORE get_diffs
                # So there should be NO get_diffs calls before the first update for this slot
                # However, since threads run in parallel, we need to be more specific:
                # We need to check that THIS slot's update happened before its corresponding get_diffs

                # Since we can't easily correlate slots to specific commits in parallel execution,
                # we'll check that ALL first updates happened within a reasonable time
                # (indicating immediate slot acquisition, not delayed until after get_diffs)

            # Verify all 8 first updates happened within 100ms (immediate slot acquisition)
            if first_updates_by_slot:
                max_time = max(u["elapsed_ms"] for u in first_updates_by_slot.values())
                self.assertLess(
                    max_time,
                    100,
                    f"All 8 first slot updates should happen within 100ms (immediate acquisition), "
                    f"but took {max_time:.1f}ms (indicates gradual ramp-up or delayed acquisition)",
                )

            # ALSO verify that update_slot was called AT LEAST once before get_diffs completes
            # Check: All get_diffs calls should have at least ONE update_slot call before them
            for diff_call in get_diffs_timeline:
                diff_time = diff_call["elapsed_ms"]

                # Find updates that happened before this get_diffs call
                updates_before_diff = [
                    u for u in update_slot_timeline if u["elapsed_ms"] < diff_time
                ]

                self.assertGreater(
                    len(updates_before_diff),
                    0,
                    f"get_diffs at {diff_time:.1f}ms should have AT LEAST ONE update_slot call before it, "
                    f"but found none. This means slots are NOT being updated before get_diffs (WRONG PATTERN).",
                )

    def test_slot_updated_with_filename_during_diff_processing(self):
        """Test that slot is updated with actual filename during each diff's processing.

        CRITICAL DISPLAY FIX: During diff loop, slot must be updated with:
        - Actual filename (commit[:8] - filename.ext)
        - Actual file size (diff content length)
        - Processing status (CHUNKING, VECTORIZING, FINALIZING)

        This ensures display shows what file is being processed, not "Analyzing commit".
        """
        # Setup
        test_dir = Path("/tmp/test-filename-updates")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 2
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        # Track ALL update_slot calls
        all_updates = []
        timeline_lock = threading.Lock()

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
            patch(
                "src.code_indexer.services.clean_slot_tracker.CleanSlotTracker"
            ) as mock_slot_tracker_class,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create mock slot tracker
            mock_slot_tracker = Mock()
            slot_counter = [0]

            def mock_acquire_slot(file_data):
                slot_id = slot_counter[0]
                slot_counter[0] += 1
                return slot_id

            def mock_update_slot(slot_id, status, filename=None, file_size=None):
                """Capture ALL update_slot calls."""
                with timeline_lock:
                    all_updates.append(
                        {
                            "slot_id": slot_id,
                            "status": status,
                            "filename": filename,
                            "file_size": file_size,
                        }
                    )

            mock_slot_tracker.acquire_slot = Mock(side_effect=mock_acquire_slot)
            mock_slot_tracker.release_slot = Mock()
            mock_slot_tracker.update_slot = Mock(side_effect=mock_update_slot)
            mock_slot_tracker.get_concurrent_files_data = Mock(return_value=[])
            mock_slot_tracker_class.return_value = mock_slot_tracker

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock progressive metadata
            indexer.progressive_metadata = Mock()
            indexer.progressive_metadata.load_completed.return_value = set()
            indexer.progressive_metadata.save_completed = Mock()

            # Mock diff scanner - return 3 files per commit
            indexer.diff_scanner = Mock()

            def get_diffs_side_effect(commit_hash):
                return [
                    Mock(
                        file_path="src/auth/login.py",
                        diff_content="def login(): pass" * 50,  # ~900 bytes
                        diff_type="modified",
                        blob_hash=None,
                    ),
                    Mock(
                        file_path="src/db/connection.py",
                        diff_content="class DB: pass" * 40,  # ~560 bytes
                        diff_type="added",
                        blob_hash=None,
                    ),
                    Mock(
                        file_path="tests/test_auth.py",
                        diff_content="def test(): assert True" * 30,  # ~690 bytes
                        diff_type="modified",
                        blob_hash=None,
                    ),
                ]

            indexer.diff_scanner.get_diffs_for_commit = Mock(
                side_effect=get_diffs_side_effect
            )

            # Mock chunker
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = []

            # Create single commit
            commits = [
                CommitInfo(
                    hash="abc123def456",
                    timestamp=1700000000,
                    author_name="Test",
                    author_email="test@example.com",
                    message="Test commit",
                    parent_hashes="",
                )
            ]

            # Create proper vector_manager mock with required attributes
            vector_manager = Mock()
            vector_manager.cancellation_event = threading.Event()
            vector_manager.embedding_provider = Mock()
            vector_manager.embedding_provider.get_current_model = Mock(
                return_value="voyage-code-2"
            )
            vector_manager.embedding_provider._get_model_token_limit = Mock(
                return_value=120000
            )
            vector_manager.submit_batch_task = Mock(
                return_value=Mock(result=Mock(return_value=[]))
            )

            # Run parallel processing
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=vector_manager,
                progress_callback=None,
            )

            # CRITICAL ASSERTIONS: Verify filename updates during diff processing
            from src.code_indexer.services.clean_slot_tracker import FileStatus

            # Find CHUNKING status updates (indicates diff processing started)
            chunking_updates = [
                u for u in all_updates if u["status"] == FileStatus.CHUNKING
            ]

            # Should have CHUNKING updates for all 3 files
            self.assertGreaterEqual(
                len(chunking_updates),
                3,
                f"Should have at least 3 CHUNKING updates (one per diff file), got {len(chunking_updates)}",
            )

            # ALL CHUNKING updates must have filename and file_size
            for update in chunking_updates:
                self.assertIsNotNone(
                    update["filename"],
                    f"CHUNKING update for slot {update['slot_id']} missing filename. "
                    f"Must pass filename='abc123de - filename.ext' to update_slot()",
                )
                self.assertIsNotNone(
                    update["file_size"],
                    f"CHUNKING update for slot {update['slot_id']} missing file_size. "
                    f"Must pass file_size=len(diff_content) to update_slot()",
                )

                # Verify filename format
                self.assertIn(
                    " - ",
                    update["filename"],
                    f"Filename '{update['filename']}' should follow pattern 'abc123de - filename.ext'",
                )

                # Verify file_size is positive
                self.assertGreater(
                    update["file_size"],
                    0,
                    f"file_size should be positive, got {update['file_size']}",
                )

            # Verify actual filenames appear in updates
            filenames_seen = set()
            for update in chunking_updates:
                if update["filename"] and " - " in update["filename"]:
                    # Extract filename part after " - "
                    filename_part = update["filename"].split(" - ", 1)[1]
                    filenames_seen.add(filename_part)

            expected_files = {"login.py", "connection.py", "test_auth.py"}
            self.assertTrue(
                expected_files.issubset(filenames_seen),
                f"Expected to see filenames {expected_files} in CHUNKING updates, "
                f"but only saw {filenames_seen}",
            )

    def test_kbs_throughput_reporting_in_progress_callback(self):
        """Test that KB/s throughput is calculated and reported in progress callback.

        CRITICAL REQUIREMENT: Progress info must include KB/s metric calculated from
        accumulated diff sizes, following HighThroughputProcessor pattern (line 403-405):
        1. Track total_bytes_processed with thread-safe accumulation
        2. Calculate: kb_per_sec = (total_bytes_processed / 1024) / max(elapsed, 0.1)
        3. Add to info string: "{commits/s} | {kb_per_sec:.1f} KB/s | {threads} threads"
        """
        # Setup
        test_dir = Path("/tmp/test-repo-kbs-reporting")
        thread_count = 4

        # Track progress callback info strings
        progress_info_strings = []
        info_lock = threading.Lock()

        def track_progress(current, total, file, info=None, **kwargs):
            """Capture progress info strings for KB/s verification."""
            if info:
                with info_lock:
                    progress_info_strings.append(info)

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = thread_count
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
        ):
            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock progressive metadata
            indexer.progressive_metadata = Mock()
            indexer.progressive_metadata.load_completed.return_value = set()
            indexer.progressive_metadata.save_completed = Mock()

            # Mock diff scanner to return diffs with KNOWN byte sizes
            indexer.diff_scanner = Mock()

            def get_diffs_side_effect(commit_hash):
                # Each commit has 2 diffs with known sizes
                return [
                    Mock(
                        file_path=f"src/file1_{commit_hash[:8]}.py",
                        diff_content="x" * 10000,  # 10 KB
                        diff_type="modified",
                        blob_hash=None,
                    ),
                    Mock(
                        file_path=f"src/file2_{commit_hash[:8]}.py",
                        diff_content="x" * 5000,  # 5 KB
                        diff_type="added",
                        blob_hash=None,
                    ),
                ]

            indexer.diff_scanner.get_diffs_for_commit = Mock(
                side_effect=get_diffs_side_effect
            )

            # Mock chunker
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = []

            # Create commits (10 commits × 15 KB each = 150 KB total)
            commits = [
                CommitInfo(
                    hash=f"commit{i:03d}abcd1234",
                    timestamp=1700000000 + i,
                    author_name="Test",
                    author_email="test@example.com",
                    message=f"Commit {i}",
                    parent_hashes="",
                )
                for i in range(10)
            ]

            # Create proper vector_manager mock with required attributes
            vector_manager = Mock()
            vector_manager.cancellation_event = threading.Event()
            vector_manager.embedding_provider = Mock()
            vector_manager.embedding_provider.get_current_model = Mock(
                return_value="voyage-code-2"
            )
            vector_manager.embedding_provider._get_model_token_limit = Mock(
                return_value=120000
            )
            vector_manager.submit_batch_task = Mock(
                return_value=Mock(result=Mock(return_value=[]))
            )

            # Run parallel processing with progress callback
            indexer._process_commits_parallel(
                commits=commits,
                embedding_provider=Mock(),
                vector_manager=vector_manager,
                progress_callback=track_progress,
            )

            # CRITICAL ASSERTIONS: KB/s must appear in progress info

            with info_lock:
                all_info_strings = list(progress_info_strings)

            # Should have progress updates
            self.assertGreater(
                len(all_info_strings),
                0,
                "Should have progress callback invocations with info strings",
            )

            # Filter for non-zero progress (skip initialization)
            non_zero_progress = [
                info for info in all_info_strings if not info.startswith("0/")
            ]

            self.assertGreater(
                len(non_zero_progress), 0, "Should have non-zero progress updates"
            )

            # Check that KB/s appears in progress strings
            kbs_found = any("KB/s" in info for info in non_zero_progress)
            self.assertTrue(
                kbs_found,
                f"KB/s metric must appear in progress info strings. "
                f"Expected format: '{{commits/s}} | {{KB/s}} | {{threads}} threads'. "
                f"Sample info strings: {non_zero_progress[:5]}",
            )

            # Verify KB/s values are non-zero (actual throughput calculated)
            kbs_values = []
            for info in non_zero_progress:
                if "KB/s" in info:
                    # Extract KB/s value from info string
                    # Expected format: "... | {value} KB/s | ..."
                    parts = info.split(" | ")
                    for part in parts:
                        if "KB/s" in part:
                            try:
                                # Extract numeric value before "KB/s"
                                kbs_str = part.replace("KB/s", "").strip()
                                kbs_value = float(kbs_str)
                                kbs_values.append(kbs_value)
                            except ValueError:
                                pass

            self.assertGreater(
                len(kbs_values),
                0,
                "Should have extracted KB/s values from progress strings",
            )

            # At least one KB/s value should be positive (actual throughput)
            positive_kbs = [v for v in kbs_values if v > 0]
            self.assertGreater(
                len(positive_kbs),
                0,
                f"KB/s values should be positive (actual throughput calculated). "
                f"Found KB/s values: {kbs_values}. "
                f"Expected: total_bytes_processed accumulated from diff sizes, "
                f"calculated as (total_bytes / 1024) / elapsed_time",
            )


if __name__ == "__main__":
    unittest.main()
