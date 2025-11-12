"""
Test temporal indexer progress lock contention and deadlock prevention.

This test verifies that the temporal indexer does not hold the progress lock
during expensive operations like deep copying data structures, acquiring nested
locks, or performing I/O operations with progress callbacks.

Bug Context:
- Large-scale operations (82K+ files) lock up due to progress_lock being held
  during expensive operations
- Deep copy of nested data structures while holding lock
- Nested lock acquisition (slot_tracker._lock) while holding progress_lock
- Progress callbacks with Rich terminal I/O while holding lock
- 8 worker threads competing for the same lock

Root Cause Location:
- src/code_indexer/services/temporal/temporal_indexer.py:583-646
"""

import copy
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.services.temporal.models import CommitInfo


class TestTemporalIndexerLockContention:
    """Test cases for temporal indexer progress lock contention."""

    @patch("code_indexer.services.embedding_factory.EmbeddingProviderFactory")
    def test_deepcopy_not_called_under_progress_lock(self, mock_factory) -> None:
        """
        Test that copy.deepcopy is NOT called while progress_lock is held.

        This test verifies the critical section is minimal and does not
        include expensive operations like deep copying data structures.

        Current bug (line 620-622 in temporal_indexer.py):
            with progress_lock:
                ...
                concurrent_files = copy.deepcopy(...)  # BAD!
                ...
                progress_callback(...)  # BAD!

        Expected behavior after fix:
            concurrent_files = copy.deepcopy(...)  # Get data FIRST
            with progress_lock:
                # Only simple value updates
                completed_count[0] += 1
                ...
            progress_callback(...)  # Call AFTER lock released
        """
        # Setup mock config and vector store
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.voyage_ai.parallel_requests = 2
        mock_config.voyage_ai.max_concurrent_batches_per_commit = 10
        mock_config.voyage_ai.model = "voyage-3"
        mock_config.embedding_provider = "voyage-ai"
        mock_config_manager.get_config.return_value = mock_config

        mock_vector_store = MagicMock()
        mock_vector_store.project_root = Path("/tmp/test_project")

        mock_factory.get_provider_model_info.return_value = {
            "provider": "voyage-ai",
            "model": "voyage-3",
            "dimensions": 1536,
        }

        # Track whether deepcopy is called while lock is held
        deepcopy_called_with_lock = []
        callback_called_with_lock = []
        locks_held = threading.local()  # Track locks per thread

        # Wrap copy.deepcopy to detect if called with lock
        original_deepcopy = copy.deepcopy

        def instrumented_deepcopy(obj, memo=None):
            """Detect if deepcopy is called while holding a lock."""
            # Check if any lock is held by inspecting the current thread's state
            # We detect this by seeing if we're inside a 'with lock' block
            # A simple heuristic: if deepcopy is called, mark it
            deepcopy_called_with_lock.append(True)
            return original_deepcopy(obj, memo)

        # Instrument progress callback
        def instrumented_callback(*args, **kwargs):
            """Track if callback is invoked."""
            callback_called_with_lock.append(True)

        with patch("copy.deepcopy", side_effect=instrumented_deepcopy):
            indexer = TemporalIndexer(
                config_manager=mock_config_manager, vector_store=mock_vector_store
            )

            # Mock diff scanner to return minimal diff
            mock_diff_scanner = MagicMock()
            indexer.diff_scanner = mock_diff_scanner

            test_commits = [
                CommitInfo(
                    hash="abc123",
                    timestamp=1704067200,
                    author_name="Test Author",
                    author_email="test@example.com",
                    message="Test commit",
                    parent_hashes="",
                )
            ]

            # Mock get_commits
            mock_diff_scanner.get_commits.return_value = test_commits

            # Mock get_diff_for_commit_range to return empty (no files changed)
            mock_diff_scanner.get_diff_for_commit_range.return_value = []

            try:
                indexer.temporal_index(
                    branch="HEAD",
                    num_commits=1,
                    progress_callback=instrumented_callback,
                )
            except Exception:
                # Ignore errors, we're only testing lock behavior
                pass

        # ASSERTION: This documents the BUG
        # With current implementation, deepcopy IS called (we detect it)
        # After fix, deepcopy should be called BEFORE lock acquisition

        # For now, we verify that IF deepcopy was called AND callback was called,
        # then the pattern is buggy. The fix will move deepcopy outside the lock.

        # This test will PASS with the bug (documenting current behavior)
        # and PASS with the fix (because the order changes but both still happen)
        # So we need a better detection mechanism...

        # Actually, let's use code inspection as the test
        # Read the source code and verify the pattern
        import inspect

        source = inspect.getsource(indexer._process_commits_parallel)

        # Check if deepcopy appears AFTER "with progress_lock:" in the source
        # This is a simple heuristic but effective for this specific bug

        # Find the critical section
        lines = source.split("\n")
        in_progress_lock_block = False
        deepcopy_in_lock = False
        callback_in_lock = False

        for i, line in enumerate(lines):
            if "with progress_lock:" in line:
                in_progress_lock_block = True
                indent_level = len(line) - len(line.lstrip())
            elif in_progress_lock_block:
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_level and line.strip():
                    # Exited the with block
                    in_progress_lock_block = False
                elif "copy.deepcopy" in line:
                    deepcopy_in_lock = True
                elif "progress_callback(" in line:
                    callback_in_lock = True

        # ASSERTION: These should be FALSE after fix
        assert not deepcopy_in_lock, (
            "BUG: copy.deepcopy() is called inside 'with progress_lock:' block. "
            "This causes lock contention. Move deepcopy BEFORE acquiring lock."
        )

        assert not callback_in_lock, (
            "BUG: progress_callback() is called inside 'with progress_lock:' block. "
            "This causes lock contention with I/O. Move callback AFTER releasing lock."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
