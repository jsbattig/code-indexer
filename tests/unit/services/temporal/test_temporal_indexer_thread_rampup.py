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
from unittest.mock import Mock, patch, call

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

        # Track active threads over time
        active_threads_timeline = []
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
        vector_store.load_id_index.return_value = set()  # No existing points

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner") as mock_diff_scanner_class, \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536}
            }

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
            )

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
                        blob_hash=None
                    )
                ]
            indexer.diff_scanner.get_diffs_for_commit = Mock(side_effect=get_diffs_side_effect)

            # Mock chunker to avoid real chunking
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = []  # No chunks = fast path

            # Create monitor thread to track active thread count every 10ms
            start_time = time.time()
            stop_monitoring = threading.Event()

            def monitor_threads():
                """Monitor active threads count every 10ms."""
                while not stop_monitoring.is_set():
                    elapsed_ms = (time.time() - start_time) * 1000

                    # Count active worker threads
                    active_count = sum(
                        1 for t in threading.enumerate()
                        if t.name and "CommitWorker" in t.name
                    )

                    with timeline_lock:
                        active_threads_timeline.append((elapsed_ms, active_count))

                    time.sleep(0.01)  # 10ms sampling

            monitor_thread = threading.Thread(target=monitor_threads, daemon=True)
            monitor_thread.start()

            # Create test commits
            commits = [
                CommitInfo(
                    hash=f"commit{i:03d}abcd1234",
                    timestamp=1700000000 + i,
                    author_name="Test Author",
                    author_email="test@example.com",
                    message=f"Test commit {i}",
                    parent_hashes=""
                )
                for i in range(commit_count)
            ]

            # Mock embedding provider and vector manager
            mock_embedding_provider = Mock()
            mock_vector_manager = Mock()

            # Run parallel processing
            try:
                indexer._process_commits_parallel(
                    commits=commits,
                    embedding_provider=mock_embedding_provider,
                    vector_manager=mock_vector_manager,
                    progress_callback=None
                )
            finally:
                # Stop monitoring
                stop_monitoring.set()
                monitor_thread.join(timeout=1)

            # CRITICAL ASSERTION: All threads should be active within 100ms
            # Filter timeline for first 100ms
            early_timeline = [(t, c) for t, c in active_threads_timeline if t <= 100]

            # At least one sample should show all 8 threads active within 100ms
            max_threads_early = max((c for t, c in early_timeline), default=0)

            self.assertEqual(
                max_threads_early,
                thread_count,
                f"Expected all {thread_count} threads active within 100ms, "
                f"but only saw {max_threads_early} threads. "
                f"Timeline (first 100ms): {early_timeline[:10]}"
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
        vector_store.load_id_index.return_value = set()

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"), \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info, \
             patch("src.code_indexer.services.clean_slot_tracker.CleanSlotTracker") as mock_slot_tracker_class:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536}
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
                config_manager=config_manager,
                vector_store=vector_store
            )

            # Mock diff scanner
            indexer.diff_scanner = Mock()
            indexer.diff_scanner.get_diffs_for_commit.return_value = [
                Mock(
                    file_path="test.py",
                    diff_content="test diff",
                    diff_type="modified",
                    blob_hash=None
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
                    parent_hashes=""
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
                progress_callback=None
            )

            # CRITICAL ASSERTION: First 8 slot acquisitions should happen within 50ms
            # (indicating all threads start processing immediately)
            first_8_acquisitions = slot_acquisition_timeline[:8]

            # All 8 should happen within 50ms
            max_time_for_8_threads = max((t for t, _ in first_8_acquisitions), default=0)

            self.assertLess(
                max_time_for_8_threads,
                50,  # 50ms threshold for all 8 threads to acquire slots
                f"First 8 slot acquisitions should happen within 50ms, but took {max_time_for_8_threads:.1f}ms. "
                f"Timeline: {first_8_acquisitions}"
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
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.load_id_index.return_value = set()

        # Track Queue.put() calls vs ThreadPoolExecutor creation
        queue_put_count = [0]
        executor_created = [False]

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"), \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info, \
             patch("src.code_indexer.services.temporal.temporal_indexer.Queue") as mock_queue_class, \
             patch("src.code_indexer.services.temporal.temporal_indexer.ThreadPoolExecutor") as mock_executor_class:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536}
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
            mock_executor.submit = Mock(return_value=Mock())

            def mock_executor_init(*args, **kwargs):
                """Track ThreadPoolExecutor creation."""
                executor_created[0] = True
                return mock_executor

            mock_executor_class.side_effect = mock_executor_init

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
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
                progress_callback=None
            )

            # CRITICAL ASSERTION: All commits should be added to queue BEFORE executor
            self.assertEqual(
                queue_put_count[0],
                10,
                f"Expected all 10 commits in queue before executor creation, "
                f"but only {queue_put_count[0]} were added"
            )
            self.assertTrue(
                executor_created[0],
                "ThreadPoolExecutor should have been created"
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
        vector_store.load_id_index.return_value = set()

        with patch("src.code_indexer.services.file_identifier.FileIdentifier"), \
             patch("src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"), \
             patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"), \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info") as mock_provider_info:

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536}
            }

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
            )

            # Mock diff scanner
            indexer.diff_scanner = Mock()
            indexer.diff_scanner.get_diffs_for_commit.return_value = []

            # Create commits
            commits = [Mock(hash=f"commit{i}") for i in range(20)]

            # Mock the ThreadPoolExecutor.submit() to count calls
            original_process = indexer._process_commits_parallel

            submit_calls = []

            with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
                mock_executor = Mock()
                mock_executor.__enter__ = Mock(return_value=mock_executor)
                mock_executor.__exit__ = Mock(return_value=None)

                def mock_submit(func):
                    """Track submit() calls."""
                    submit_calls.append(time.time())
                    future = Mock()
                    future.result = Mock()
                    return future

                mock_executor.submit = Mock(side_effect=mock_submit)
                mock_executor_class.return_value = mock_executor

                # Run parallel processing
                indexer._process_commits_parallel(
                    commits=commits,
                    embedding_provider=Mock(),
                    vector_manager=Mock(),
                    progress_callback=None
                )

                # CRITICAL ASSERTION: Exactly thread_count workers should be submitted
                self.assertEqual(
                    len(submit_calls),
                    thread_count,
                    f"Expected exactly {thread_count} workers submitted, "
                    f"but got {len(submit_calls)}"
                )

                # All submits should happen within 10ms (immediate submission)
                if len(submit_calls) > 1:
                    time_delta = (submit_calls[-1] - submit_calls[0]) * 1000
                    self.assertLess(
                        time_delta,
                        10,  # 10ms threshold
                        f"All workers should be submitted within 10ms, but took {time_delta:.1f}ms"
                    )


if __name__ == "__main__":
    unittest.main()
