"""
Unit tests for watch metadata management.

Tests the WatchMetadata and GitStateMonitor classes for proper state persistence
and git change detection.
"""

from .conftest import local_temporary_directory

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.services.watch_metadata import WatchMetadata, GitStateMonitor


class TestWatchMetadata:
    """Unit tests for WatchMetadata class."""

    def test_watch_metadata_creation(self):
        """Test WatchMetadata initialization with defaults."""
        metadata = WatchMetadata()

        assert metadata.last_sync_timestamp == 0.0
        assert metadata.watch_started_at is None
        assert metadata.current_branch is None
        assert metadata.current_commit is None
        assert metadata.git_available is False
        assert metadata.embedding_provider is None
        assert metadata.embedding_model is None
        assert metadata.collection_name is None
        assert metadata.files_being_processed == []
        assert metadata.processing_interrupted is False
        assert metadata.last_error is None
        assert metadata.total_files_processed == 0
        assert metadata.total_indexing_cycles == 0
        assert metadata.total_branch_changes_detected == 0

    def test_watch_metadata_persistence(self):
        """Test WatchMetadata save/load functionality."""
        with local_temporary_directory() as temp_dir:
            metadata_path = Path(temp_dir) / "watch_metadata.json"

            # Create metadata with test data
            original = WatchMetadata(
                last_sync_timestamp=1234567890.0,
                current_branch="main",
                current_commit="abc123",
                git_available=True,
                embedding_provider="voyage-ai",
                embedding_model="voyage-code-3",
                collection_name="test_collection",
                files_being_processed=["file1.py", "file2.py"],
                total_files_processed=42,
                total_indexing_cycles=5,
                total_branch_changes_detected=2,
            )

            # Save to disk
            original.save_to_disk(metadata_path)

            # Load from disk
            loaded = WatchMetadata.load_from_disk(metadata_path)

            # Verify all fields match
            assert loaded.last_sync_timestamp == 1234567890.0
            assert loaded.current_branch == "main"
            assert loaded.current_commit == "abc123"
            assert loaded.git_available is True
            assert loaded.embedding_provider == "voyage-ai"
            assert loaded.embedding_model == "voyage-code-3"
            assert loaded.collection_name == "test_collection"
            assert loaded.files_being_processed == ["file1.py", "file2.py"]
            assert loaded.total_files_processed == 42
            assert loaded.total_indexing_cycles == 5
            assert loaded.total_branch_changes_detected == 2

    def test_watch_metadata_load_nonexistent(self):
        """Test loading metadata from non-existent file creates new instance."""
        with local_temporary_directory() as temp_dir:
            metadata_path = Path(temp_dir) / "nonexistent.json"

            metadata = WatchMetadata.load_from_disk(metadata_path)

            # Should be a new instance with defaults
            assert metadata.last_sync_timestamp == 0.0
            assert metadata.current_branch is None

    def test_watch_metadata_load_corrupt_file(self):
        """Test loading corrupt metadata file creates new instance."""
        with local_temporary_directory() as temp_dir:
            metadata_path = Path(temp_dir) / "corrupt.json"

            # Write corrupt JSON
            metadata_path.write_text("{ invalid json content")

            metadata = WatchMetadata.load_from_disk(metadata_path)

            # Should be a new instance with defaults
            assert metadata.last_sync_timestamp == 0.0
            assert metadata.current_branch is None

    def test_start_watch_session(self):
        """Test starting a watch session updates metadata correctly."""
        metadata = WatchMetadata()

        git_status = {
            "git_available": True,
            "current_branch": "feature-branch",
            "current_commit": "def456",
        }

        metadata.start_watch_session(
            provider_name="voyage-ai",
            model_name="voyage-code-3",
            git_status=git_status,
            collection_name="test_collection",
        )

        assert metadata.embedding_provider == "voyage-ai"
        assert metadata.embedding_model == "voyage-code-3"
        assert metadata.collection_name == "test_collection"
        assert metadata.git_available is True
        assert metadata.current_branch == "feature-branch"
        assert metadata.current_commit == "def456"
        assert metadata.files_being_processed == []
        assert metadata.processing_interrupted is False
        assert metadata.last_error is None
        assert metadata.watch_started_at is not None

    def test_update_after_sync_cycle(self):
        """Test updating metadata after successful sync cycle."""
        metadata = WatchMetadata()
        metadata.files_being_processed = ["test.py"]
        metadata.processing_interrupted = True
        metadata.last_error = "some error"

        start_time = time.time()
        metadata.update_after_sync_cycle(files_processed=3)

        assert metadata.last_sync_timestamp >= start_time
        assert metadata.total_files_processed == 3
        assert metadata.total_indexing_cycles == 1
        assert metadata.files_being_processed == []
        assert metadata.processing_interrupted is False
        assert metadata.last_error is None

    def test_update_git_state(self):
        """Test updating git state tracks branch changes."""
        metadata = WatchMetadata()
        metadata.current_branch = "main"
        metadata.current_commit = "abc123"

        # Same branch, different commit - no branch change
        metadata.update_git_state("main", "def456")
        assert metadata.current_branch == "main"
        assert metadata.current_commit == "def456"
        assert metadata.total_branch_changes_detected == 0

        # Different branch - should count as branch change
        metadata.update_git_state("feature", "xyz789")
        assert metadata.current_branch == "feature"
        assert metadata.current_commit == "xyz789"
        assert metadata.total_branch_changes_detected == 1

    def test_mark_processing_states(self):
        """Test marking processing start and interruption."""
        metadata = WatchMetadata()

        files = ["file1.py", "file2.py"]
        metadata.mark_processing_start(files)

        assert metadata.files_being_processed == files
        assert metadata.processing_interrupted is False

        # Modify original list to ensure copy was made
        files.append("file3.py")
        assert metadata.files_being_processed == ["file1.py", "file2.py"]

        # Mark as interrupted
        metadata.mark_processing_interrupted("test error")

        assert metadata.processing_interrupted is True
        assert metadata.last_error == "test error"

    def test_should_reprocess_file(self):
        """Test file reprocessing logic based on timestamps."""
        metadata = WatchMetadata()
        metadata.last_sync_timestamp = time.time() - 10  # 10 seconds ago

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = Path(temp_file.name)

            try:
                # File is newer than last sync
                assert metadata.should_reprocess_file(temp_path) is True

                # Update sync timestamp to future
                metadata.last_sync_timestamp = time.time() + 10
                assert metadata.should_reprocess_file(temp_path) is False

            finally:
                temp_path.unlink(missing_ok=True)

    def test_should_reprocess_nonexistent_file(self):
        """Test reprocessing logic for non-existent files."""
        metadata = WatchMetadata()
        nonexistent = Path("/path/that/does/not/exist.py")

        assert metadata.should_reprocess_file(nonexistent) is False

    def test_get_recovery_files(self):
        """Test getting files that need recovery processing."""
        metadata = WatchMetadata()

        # No recovery needed when not interrupted
        assert metadata.get_recovery_files() == []

        # Set up interrupted state
        files = ["file1.py", "file2.py"]
        metadata.mark_processing_start(files)
        metadata.mark_processing_interrupted()

        recovery_files = metadata.get_recovery_files()
        assert recovery_files == files

        # Ensure copy is returned
        recovery_files.append("file3.py")
        assert metadata.files_being_processed == ["file1.py", "file2.py"]

    def test_is_provider_changed(self):
        """Test provider change detection."""
        metadata = WatchMetadata()
        metadata.embedding_provider = "voyage-ai"
        metadata.embedding_model = "voyage-code-3"

        # Same provider and model
        assert metadata.is_provider_changed("voyage-ai", "voyage-code-3") is False

        # Different provider
        assert metadata.is_provider_changed("ollama", "voyage-code-3") is True

        # Different model
        assert metadata.is_provider_changed("voyage-ai", "different-model") is True

    def test_get_statistics(self):
        """Test getting watch session statistics."""
        metadata = WatchMetadata()
        metadata.watch_started_at = "2024-01-01T00:00:00Z"
        metadata.total_files_processed = 100
        metadata.total_indexing_cycles = 10
        metadata.total_branch_changes_detected = 3
        metadata.current_branch = "main"
        metadata.last_sync_timestamp = 1234567890.0
        metadata.files_being_processed = ["file1.py"]

        stats = metadata.get_statistics()

        expected_stats = {
            "watch_started_at": "2024-01-01T00:00:00Z",
            "total_files_processed": 100,
            "total_indexing_cycles": 10,
            "total_branch_changes": 3,
            "current_branch": "main",
            "last_sync_timestamp": 1234567890.0,
            "processing_interrupted": False,
            "files_in_recovery": 1,
        }

        assert stats == expected_stats


class TestGitStateMonitor:
    """Unit tests for GitStateMonitor class."""

    def test_git_state_monitor_initialization(self):
        """Test GitStateMonitor initialization."""
        mock_git_service = Mock()

        monitor = GitStateMonitor(mock_git_service, check_interval=2.0)

        assert monitor.git_topology_service == mock_git_service
        assert monitor.check_interval == 2.0
        assert monitor.current_branch is None
        assert monitor.current_commit is None
        assert monitor.branch_change_callbacks == []
        assert monitor._monitoring is False

    def test_start_monitoring_git_unavailable(self):
        """Test starting monitoring when git is unavailable."""
        mock_git_service = Mock()
        mock_git_service.is_git_available.return_value = False

        monitor = GitStateMonitor(mock_git_service)
        result = monitor.start_monitoring()

        assert result is False
        assert monitor._monitoring is False

    @patch("subprocess.run")
    def test_start_monitoring_git_available(self, mock_subprocess):
        """Test starting monitoring when git is available."""
        mock_git_service = Mock()
        mock_git_service.is_git_available.return_value = True
        mock_git_service.get_current_branch.return_value = "main"
        mock_git_service.codebase_dir = Path("/test")

        # Mock git rev-parse command
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "abc123\n"

        monitor = GitStateMonitor(mock_git_service)
        result = monitor.start_monitoring()

        assert result is True
        assert monitor._monitoring is True
        assert monitor.current_branch == "main"
        assert monitor.current_commit == "abc123"

    def test_stop_monitoring(self):
        """Test stopping monitoring."""
        mock_git_service = Mock()

        monitor = GitStateMonitor(mock_git_service)
        monitor._monitoring = True

        monitor.stop_monitoring()

        assert monitor._monitoring is False

    @patch("subprocess.run")
    def test_check_for_changes_no_change(self, mock_subprocess):
        """Test checking for changes when no changes occurred."""
        mock_git_service = Mock()
        mock_git_service.is_git_available.return_value = True
        mock_git_service.get_current_branch.return_value = "main"
        mock_git_service.codebase_dir = Path("/test")

        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "abc123\n"

        monitor = GitStateMonitor(mock_git_service)
        monitor.start_monitoring()

        # No change
        change_event = monitor.check_for_changes()

        assert change_event is None

    @patch("subprocess.run")
    def test_check_for_changes_branch_change(self, mock_subprocess):
        """Test checking for changes when branch changes."""
        mock_git_service = Mock()
        mock_git_service.is_git_available.return_value = True
        mock_git_service.codebase_dir = Path("/test")

        # Initial state
        mock_git_service.get_current_branch.return_value = "main"
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "abc123\n"

        monitor = GitStateMonitor(mock_git_service)
        monitor.start_monitoring()

        # Change branch
        mock_git_service.get_current_branch.return_value = "feature"
        mock_subprocess.return_value.stdout = "def456\n"

        change_event = monitor.check_for_changes()

        assert change_event is not None
        assert change_event["type"] == "git_state_change"
        assert change_event["old_branch"] == "main"
        assert change_event["new_branch"] == "feature"
        assert change_event["old_commit"] == "abc123"
        assert change_event["new_commit"] == "def456"
        assert "timestamp" in change_event

    def test_register_branch_change_callback(self):
        """Test registering branch change callbacks."""
        mock_git_service = Mock()
        monitor = GitStateMonitor(mock_git_service)

        callback1 = Mock()
        callback2 = Mock()

        monitor.register_branch_change_callback(callback1)
        monitor.register_branch_change_callback(callback2)

        assert len(monitor.branch_change_callbacks) == 2
        assert callback1 in monitor.branch_change_callbacks
        assert callback2 in monitor.branch_change_callbacks

    @patch("subprocess.run")
    def test_callbacks_called_on_change(self, mock_subprocess):
        """Test that callbacks are called when changes occur."""
        mock_git_service = Mock()
        mock_git_service.is_git_available.return_value = True
        mock_git_service.codebase_dir = Path("/test")

        # Setup initial state
        mock_git_service.get_current_branch.return_value = "main"
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "abc123\n"

        monitor = GitStateMonitor(mock_git_service)
        monitor.start_monitoring()

        # Register callbacks
        callback1 = Mock()
        callback2 = Mock()
        monitor.register_branch_change_callback(callback1)
        monitor.register_branch_change_callback(callback2)

        # Trigger change
        mock_git_service.get_current_branch.return_value = "feature"
        mock_subprocess.return_value.stdout = "def456\n"

        change_event = monitor.check_for_changes()

        # Both callbacks should be called
        callback1.assert_called_once_with(change_event)
        callback2.assert_called_once_with(change_event)

    def test_callback_exception_handling(self):
        """Test that callback exceptions don't break monitoring."""
        mock_git_service = Mock()
        mock_git_service.is_git_available.return_value = True
        mock_git_service.get_current_branch.return_value = "main"

        monitor = GitStateMonitor(mock_git_service)
        monitor._monitoring = True
        monitor.current_branch = "main"
        monitor.current_commit = "abc123"

        # Register callback that raises exception
        failing_callback = Mock(side_effect=Exception("Test error"))
        working_callback = Mock()

        monitor.register_branch_change_callback(failing_callback)
        monitor.register_branch_change_callback(working_callback)

        # Trigger change
        mock_git_service.get_current_branch.return_value = "feature"

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = "def456\n"

            # Should not raise exception
            monitor.check_for_changes()

            # Working callback should still be called
            working_callback.assert_called_once()

    @patch("subprocess.run")
    def test_get_current_state(self, mock_subprocess):
        """Test getting current git state."""
        mock_git_service = Mock()
        mock_git_service.is_git_available.return_value = True
        mock_git_service.codebase_dir = Path("/test")

        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "abc123\n"

        monitor = GitStateMonitor(mock_git_service)
        monitor.current_branch = "main"
        monitor.current_commit = "abc123"

        state = monitor.get_current_state()

        expected_state = {
            "git_available": True,
            "current_branch": "main",
            "current_commit": "abc123",
        }

        assert state == expected_state
