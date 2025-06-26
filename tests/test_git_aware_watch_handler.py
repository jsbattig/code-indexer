"""
Unit tests for GitAwareWatchHandler.

Tests the git-aware file watching functionality including branch change handling,
file change detection, and integration with SmartIndexer.
"""

import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.services.git_aware_watch_handler import GitAwareWatchHandler
from code_indexer.services.watch_metadata import WatchMetadata


class TestGitAwareWatchHandler:
    """Unit tests for GitAwareWatchHandler class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_config = Mock()
        self.mock_config.codebase_dir = Path("/test/codebase")
        self.mock_config.file_extensions = [
            "py",
            "js",
            "ts",
        ]  # Mock file extensions for testing

        self.mock_smart_indexer = Mock()
        self.mock_git_topology_service = Mock()
        self.mock_watch_metadata = Mock(spec=WatchMetadata)

        with patch(
            "code_indexer.services.git_aware_watch_handler.GitStateMonitor"
        ) as mock_git_monitor_class:
            self.mock_git_monitor = Mock()
            mock_git_monitor_class.return_value = self.mock_git_monitor

            self.handler = GitAwareWatchHandler(
                config=self.mock_config,
                smart_indexer=self.mock_smart_indexer,
                git_topology_service=self.mock_git_topology_service,
                watch_metadata=self.mock_watch_metadata,
                debounce_seconds=0.1,  # Short debounce for testing
            )

    def test_handler_initialization(self):
        """Test GitAwareWatchHandler initialization."""
        assert self.handler.config == self.mock_config
        assert self.handler.smart_indexer == self.mock_smart_indexer
        assert self.handler.git_topology_service == self.mock_git_topology_service
        assert self.handler.watch_metadata == self.mock_watch_metadata
        assert self.handler.debounce_seconds == 0.1
        assert self.handler.pending_changes == set()
        assert not self.handler.processing_in_progress
        assert self.handler.files_processed_count == 0
        assert self.handler.indexing_cycles_count == 0

    @patch("code_indexer.services.git_aware_watch_handler.GitStateMonitor")
    def test_start_watching_with_git(self, mock_git_monitor_class):
        """Test starting watch with git available."""
        mock_git_monitor = Mock()
        mock_git_monitor.start_monitoring.return_value = True
        mock_git_monitor.current_branch = "main"
        mock_git_monitor_class.return_value = mock_git_monitor

        handler = GitAwareWatchHandler(
            self.mock_config,
            self.mock_smart_indexer,
            self.mock_git_topology_service,
            self.mock_watch_metadata,
        )

        with patch.object(handler, "_process_changes_loop"):
            handler.start_watching()

        mock_git_monitor.start_monitoring.assert_called_once()
        assert handler.processing_thread is not None

    @patch("code_indexer.services.git_aware_watch_handler.GitStateMonitor")
    def test_start_watching_without_git(self, mock_git_monitor_class):
        """Test starting watch with git unavailable."""
        mock_git_monitor = Mock()
        mock_git_monitor.start_monitoring.return_value = False
        mock_git_monitor_class.return_value = mock_git_monitor

        handler = GitAwareWatchHandler(
            self.mock_config,
            self.mock_smart_indexer,
            self.mock_git_topology_service,
            self.mock_watch_metadata,
        )

        with patch.object(handler, "_process_changes_loop"):
            handler.start_watching()

        mock_git_monitor.start_monitoring.assert_called_once()
        assert handler.processing_thread is not None

    def test_stop_watching(self):
        """Test stopping watch process."""
        with patch.object(self.handler, "_process_pending_changes") as mock_process:
            self.handler.stop_watching()

        self.mock_git_monitor.stop_monitoring.assert_called_once()
        mock_process.assert_called_once_with(final_cleanup=True)

    def test_on_modified_file(self):
        """Test handling file modification events."""
        mock_event = Mock()
        mock_event.is_directory = False
        mock_event.src_path = "/test/codebase/file.py"

        with patch.object(self.handler, "_should_include_file", return_value=True):
            self.handler.on_modified(mock_event)

        assert Path("/test/codebase/file.py") in self.handler.pending_changes

    def test_on_modified_directory_ignored(self):
        """Test that directory modification events are ignored."""
        mock_event = Mock()
        mock_event.is_directory = True
        mock_event.src_path = "/test/codebase/directory"

        self.handler.on_modified(mock_event)

        assert len(self.handler.pending_changes) == 0

    def test_on_deleted_file(self):
        """Test handling file deletion events."""
        mock_event = Mock()
        mock_event.is_directory = False
        mock_event.src_path = "/test/codebase/file.py"

        with patch.object(self.handler, "_should_include_file", return_value=True):
            self.handler.on_deleted(mock_event)

        assert Path("/test/codebase/file.py") in self.handler.pending_changes

    def test_on_created_file(self):
        """Test handling file creation events."""
        mock_event = Mock()
        mock_event.is_directory = False
        mock_event.src_path = "/test/codebase/newfile.py"

        with patch.object(self.handler, "_should_include_file", return_value=True):
            self.handler.on_created(mock_event)

        assert Path("/test/codebase/newfile.py") in self.handler.pending_changes

    def test_on_moved_file(self):
        """Test handling file move events."""
        mock_event = Mock()
        mock_event.is_directory = False
        mock_event.src_path = "/test/codebase/oldfile.py"
        mock_event.dest_path = "/test/codebase/newfile.py"

        with patch.object(self.handler, "_should_include_file", return_value=True):
            self.handler.on_moved(mock_event)

        # Should treat as delete + create
        assert Path("/test/codebase/oldfile.py") in self.handler.pending_changes
        assert Path("/test/codebase/newfile.py") in self.handler.pending_changes

    def test_should_include_file_excluded(self):
        """Test file exclusion logic."""
        test_file = Path("/test/codebase/file.txt")

        with patch("code_indexer.indexing.FileFinder") as mock_finder_class:
            mock_finder = Mock()
            mock_finder._should_include_file.return_value = False
            mock_finder_class.return_value = mock_finder

            result = self.handler._should_include_file(test_file)

        assert result is False

    def test_should_include_file_included(self):
        """Test file inclusion logic."""
        test_file = Path("/test/codebase/file.py")

        with patch("code_indexer.indexing.FileFinder") as mock_finder_class:
            mock_finder = Mock()
            mock_finder._should_include_file.return_value = True
            mock_finder_class.return_value = mock_finder

            result = self.handler._should_include_file(test_file)

        assert result is True

    def test_should_include_file_exception(self):
        """Test file inclusion with exception handling."""
        test_file = Path("/test/codebase/file.py")

        with patch(
            "code_indexer.indexing.FileFinder", side_effect=Exception("Test error")
        ):
            result = self.handler._should_include_file(test_file)

        assert result is False

    def test_add_pending_change_thread_safety(self):
        """Test thread safety of pending change tracking."""
        test_file = Path("/test/codebase/file.py")

        with patch.object(self.handler, "_should_include_file", return_value=True):
            # Simulate concurrent additions
            threads = []
            for i in range(10):
                thread = threading.Thread(
                    target=self.handler._add_pending_change,
                    args=(test_file, "modified"),
                )
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

        # Should only be added once due to set semantics
        assert len(self.handler.pending_changes) == 1
        assert test_file in self.handler.pending_changes

    def test_process_pending_changes_empty(self):
        """Test processing when no changes are pending."""
        # Should return early without processing
        self.handler._process_pending_changes()

        self.mock_smart_indexer.process_files_incrementally.assert_not_called()

    def test_process_pending_changes_already_processing(self):
        """Test handling of concurrent processing attempts."""
        self.handler.processing_in_progress = True
        self.handler.pending_changes.add(Path("/test/file.py"))

        self.handler._process_pending_changes()

        # Should re-add changes back to queue
        assert Path("/test/file.py") in self.handler.pending_changes
        self.mock_smart_indexer.process_files_incrementally.assert_not_called()

    def test_process_pending_changes_success(self):
        """Test successful processing of pending changes."""
        test_file = Path("/test/codebase/file.py")
        self.handler.pending_changes.add(test_file)

        # Mock successful processing
        mock_stats = Mock()
        mock_stats.files_processed = 1
        self.mock_smart_indexer.process_files_incrementally.return_value = mock_stats

        self.handler._process_pending_changes()

        # Verify SmartIndexer was called with correct parameters
        self.mock_smart_indexer.process_files_incrementally.assert_called_once_with(
            ["file.py"],
            force_reprocess=True,
            quiet=False,  # Relative path, quiet=False for debugging
            watch_mode=True,  # Enable verified deletion for reliability
        )

        # Verify metadata updates
        self.mock_watch_metadata.mark_processing_start.assert_called_once()
        self.mock_watch_metadata.update_after_sync_cycle.assert_called_once_with(
            files_processed=1
        )

        # Verify statistics
        assert self.handler.files_processed_count == 1
        assert self.handler.indexing_cycles_count == 1

        # Verify pending changes cleared
        assert len(self.handler.pending_changes) == 0

    def test_process_pending_changes_exception(self):
        """Test handling of processing exceptions."""
        test_file = Path("/test/codebase/file.py")
        self.handler.pending_changes.add(test_file)

        # Mock processing failure
        self.mock_smart_indexer.process_files_incrementally.side_effect = Exception(
            "Processing failed"
        )

        self.handler._process_pending_changes()

        # Verify error handling
        self.mock_watch_metadata.mark_processing_interrupted.assert_called_once_with(
            "Processing failed"
        )

        # Verify changes re-added to queue for retry
        assert test_file in self.handler.pending_changes

    def test_handle_branch_change(self):
        """Test handling of git branch change events."""
        change_event = {
            "old_branch": "main",
            "new_branch": "feature",
            "old_commit": "abc123",
            "new_commit": "def456",
            "timestamp": time.time(),
        }

        # Mock git topology analysis
        mock_analysis = Mock()
        mock_analysis.files_to_reindex = ["changed.py"]
        mock_analysis.files_to_update_metadata = ["unchanged.py"]
        self.mock_git_topology_service.analyze_branch_change.return_value = (
            mock_analysis
        )

        # Mock branch indexer result
        mock_branch_result = Mock()
        mock_branch_result.content_points_created = 5
        mock_branch_result.content_points_reused = 0
        mock_branch_result.processing_time = 1.0
        mock_branch_result.files_processed = 2
        self.mock_smart_indexer.branch_aware_indexer.index_branch_changes.return_value = (
            mock_branch_result
        )

        # Mock collection name resolution
        self.mock_smart_indexer.qdrant_client.resolve_collection_name.return_value = (
            "test_collection"
        )

        # Add some pending changes that should be cleared
        self.handler.pending_changes.add(Path("/test/file.py"))

        with patch.object(self.handler.watch_metadata, "save_to_disk"):
            self.handler._handle_branch_change(change_event)

        # Verify git topology analysis
        self.mock_git_topology_service.analyze_branch_change.assert_called_once_with(
            "main", "feature"
        )

        # Verify branch indexer was called
        self.mock_smart_indexer.branch_aware_indexer.index_branch_changes.assert_called_once_with(
            old_branch="main",
            new_branch="feature",
            changed_files=["changed.py"],
            unchanged_files=["unchanged.py"],
            collection_name="test_collection",
        )

        # Verify metadata updates
        self.mock_watch_metadata.update_git_state.assert_called_once_with(
            "feature", "def456"
        )

        # Verify pending changes cleared
        assert len(self.handler.pending_changes) == 0

    def test_handle_branch_change_exception(self):
        """Test handling of branch change exceptions."""
        change_event = {
            "old_branch": "main",
            "new_branch": "feature",
            "old_commit": "abc123",
            "new_commit": "def456",
            "timestamp": time.time(),
        }

        # Mock failure in git topology analysis
        self.mock_git_topology_service.analyze_branch_change.side_effect = Exception(
            "Git error"
        )

        self.handler._handle_branch_change(change_event)

        # Verify error handling
        self.mock_watch_metadata.mark_processing_interrupted.assert_called_once()
        error_message = self.mock_watch_metadata.mark_processing_interrupted.call_args[
            0
        ][0]
        assert "Branch change error" in error_message

    def test_get_statistics(self):
        """Test getting watch handler statistics."""
        # Set up handler state
        self.handler.files_processed_count = 42
        self.handler.indexing_cycles_count = 5
        self.handler.pending_changes.add(Path("/test/file.py"))
        self.handler.processing_in_progress = True

        # Mock git monitor state
        self.mock_git_monitor._monitoring = True
        self.mock_git_monitor.current_branch = "main"

        # Mock base statistics from metadata
        base_stats = {
            "total_files_processed": 100,
            "total_indexing_cycles": 10,
        }
        self.mock_watch_metadata.get_statistics.return_value = base_stats

        stats = self.handler.get_statistics()

        # Verify base stats included
        assert stats["total_files_processed"] == 100
        assert stats["total_indexing_cycles"] == 10

        # Verify handler-specific stats
        assert stats["handler_files_processed"] == 42
        assert stats["handler_indexing_cycles"] == 5
        assert stats["pending_changes"] == 1
        assert stats["processing_in_progress"] is True
        assert stats["git_monitoring_active"] is True
        assert stats["current_git_branch"] == "main"

    def test_process_changes_loop_git_change_detected(self):
        """Test that git changes interrupt file processing loop."""
        # Mock git change detection
        git_change_event = {"type": "git_state_change"}
        self.mock_git_monitor.check_for_changes.return_value = git_change_event

        # Add pending changes
        self.handler.pending_changes.add(Path("/test/file.py"))

        with patch.object(self.handler, "_process_pending_changes") as mock_process:
            with patch("time.sleep", side_effect=Exception("Break loop")):
                try:
                    self.handler._process_changes_loop()
                except Exception:
                    pass  # Expected to break the loop

        # Should not process file changes when git change detected
        mock_process.assert_not_called()

    def test_process_changes_loop_no_git_change(self):
        """Test normal file processing when no git changes."""
        # Mock no git changes
        self.mock_git_monitor.check_for_changes.return_value = None

        with patch.object(self.handler, "_process_pending_changes") as mock_process:
            # Use a counter to break the loop after one iteration
            call_count = [0]

            def mock_sleep(duration):
                call_count[0] += 1
                if call_count[0] >= 2:  # Exit after processing once
                    raise Exception("Break loop")

            with patch("time.sleep", side_effect=mock_sleep):
                try:
                    self.handler._process_changes_loop()
                except Exception:
                    pass  # Expected to break the loop

        # Should process file changes normally
        mock_process.assert_called()

    def test_relative_path_conversion(self):
        """Test conversion of absolute paths to relative paths."""
        # File inside codebase
        inside_file = Path("/test/codebase/subdir/file.py")
        self.handler.pending_changes.add(inside_file)

        # File outside codebase
        outside_file = Path("/other/location/file.py")
        self.handler.pending_changes.add(outside_file)

        # Mock successful processing
        mock_stats = Mock()
        mock_stats.files_processed = 1
        self.mock_smart_indexer.process_files_incrementally.return_value = mock_stats

        self.handler._process_pending_changes()

        # Should only process the file inside codebase
        args = self.mock_smart_indexer.process_files_incrementally.call_args[0]
        relative_paths = args[0]

        assert relative_paths == ["subdir/file.py"]
