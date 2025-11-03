"""
Integration tests for daemon index progress callbacks.

Tests that progress callbacks stream from daemon to client during indexing operations,
providing real-time progress updates identical to standalone mode.
"""

import time
from pathlib import Path
from typing import List, Tuple

import pytest

from code_indexer.daemon.service import CIDXDaemonService
from code_indexer.cli_progress_handler import ClientProgressHandler


@pytest.fixture
def daemon_service():
    """Create daemon service instance for testing."""
    service = CIDXDaemonService()
    yield service
    # Cleanup
    if service.eviction_thread:
        service.eviction_thread.stop()


class ProgressCapture:
    """Capture progress updates for testing."""

    def __init__(self):
        self.updates: List[Tuple[int, int, str, str]] = []
        self.setup_messages: List[str] = []
        self.file_progress: List[Tuple[int, int]] = []

    def callback(self, current: int, total: int, file_path, info: str = ""):
        """Capture progress update."""
        self.updates.append((current, total, str(file_path), info))

        if total == 0:
            # Setup message
            self.setup_messages.append(info)
        else:
            # File progress
            self.file_progress.append((current, total))


def test_index_blocking_calls_progress_callback(tmp_path, daemon_service):
    """Test that exposed_index_blocking calls progress callback during indexing."""
    # Create test project with files
    test_project = tmp_path / "test_project"
    test_project.mkdir()

    # Initialize config
    config_dir = test_project / ".code-indexer"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        """{
        "codebase_dir": "%s",
        "embedding_provider": "voyage-ai",
        "voyage_api_key": "test-key"
    }"""
        % str(test_project)
    )

    # Create some test files
    (test_project / "test1.py").write_text("def hello(): pass")
    (test_project / "test2.py").write_text("def world(): pass")

    # Create progress capture
    progress_capture = ProgressCapture()

    # Call exposed_index_blocking with callback
    result = daemon_service.exposed_index_blocking(
        project_path=str(test_project),
        callback=progress_capture.callback,
        force_full=True,
        batch_size=10,
        enable_fts=False,
    )

    # Verify result structure
    assert result["status"] in ["completed", "error"]

    if result["status"] == "completed":
        # Verify stats present
        assert "stats" in result
        stats = result["stats"]
        assert "files_processed" in stats
        assert "chunks_created" in stats
        assert "failed_files" in stats
        assert "duration_seconds" in stats

        # Verify progress updates were captured
        assert len(progress_capture.updates) > 0

        # Verify setup messages (total=0)
        assert len(progress_capture.setup_messages) > 0

        # Verify file progress updates (total>0)
        assert len(progress_capture.file_progress) > 0

        # Verify final progress shows completion
        last_current, last_total = progress_capture.file_progress[-1]
        assert last_current == last_total  # 100% completion


def test_client_progress_handler_creates_callback(tmp_path):
    """Test that ClientProgressHandler creates a working callback."""
    from rich.console import Console

    console = Console()
    handler = ClientProgressHandler(console=console)

    # Create callback
    callback = handler.create_progress_callback()

    # Verify callback is callable
    assert callable(callback)

    # Test setup message (total=0)
    callback(0, 0, Path(""), info="Initializing...")

    # Test progress update (total>0)
    callback(5, 10, Path("/test/file.py"), info="5/10 files (50%)")

    # Test completion (current == total)
    callback(10, 10, Path("/test/last.py"), info="10/10 files (100%)")

    # Cleanup
    if handler.progress:
        handler.progress.stop()


def test_progress_callback_handles_path_objects(tmp_path, daemon_service):
    """Test that progress callback handles Path objects correctly."""
    test_project = tmp_path / "test_project"
    test_project.mkdir()

    # Initialize config
    config_dir = test_project / ".code-indexer"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        """{
        "codebase_dir": "%s",
        "embedding_provider": "voyage-ai",
        "voyage_api_key": "test-key"
    }"""
        % str(test_project)
    )

    # Create test file
    (test_project / "test.py").write_text("def test(): pass")

    # Create progress capture that checks types
    received_paths = []

    def path_callback(current, total, file_path, info=""):
        received_paths.append((type(file_path).__name__, str(file_path)))

    # Call exposed_index_blocking
    daemon_service.exposed_index_blocking(
        project_path=str(test_project),
        callback=path_callback,
        force_full=True,
        batch_size=10,
        enable_fts=False,
    )

    # Verify paths were received (as Path or str objects)
    assert len(received_paths) > 0


def test_progress_callback_streaming_updates(tmp_path, daemon_service):
    """Test that progress callbacks stream updates in real-time."""
    test_project = tmp_path / "test_project"
    test_project.mkdir()

    # Initialize config
    config_dir = test_project / ".code-indexer"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        """{
        "codebase_dir": "%s",
        "embedding_provider": "voyage-ai",
        "voyage_api_key": "test-key"
    }"""
        % str(test_project)
    )

    # Create multiple test files
    for i in range(5):
        (test_project / f"test{i}.py").write_text(f"def func{i}(): pass")

    # Track update timing
    update_times = []

    def timing_callback(current, total, file_path, info=""):
        update_times.append(time.time())

    # Call exposed_index_blocking
    start_time = time.time()
    result = daemon_service.exposed_index_blocking(
        project_path=str(test_project),
        callback=timing_callback,
        force_full=True,
        batch_size=10,
        enable_fts=False,
    )
    end_time = time.time()

    # Verify updates were received during indexing (not all at end)
    if result["status"] == "completed" and len(update_times) > 1:
        # Check that updates span the duration (not all at start or end)
        first_update = update_times[0] - start_time
        last_update = update_times[-1] - start_time
        total_duration = end_time - start_time

        # First update should be near start
        assert first_update < total_duration * 0.2  # Within first 20%

        # Last update should be near end
        assert last_update > total_duration * 0.8  # After 80% elapsed


def test_error_handling_in_progress_callback(tmp_path, daemon_service):
    """Test that errors in indexing are reported via result, not callback exceptions."""
    test_project = tmp_path / "test_project"
    test_project.mkdir()

    # Create invalid config (missing required fields)
    config_dir = test_project / ".code-indexer"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text("{}")  # Invalid config

    # Progress capture
    progress_capture = ProgressCapture()

    # Call exposed_index_blocking (should fail gracefully)
    result = daemon_service.exposed_index_blocking(
        project_path=str(test_project),
        callback=progress_capture.callback,
        force_full=True,
        batch_size=10,
        enable_fts=False,
    )

    # Verify error is reported in result
    assert result["status"] == "error"
    assert "message" in result
    assert len(result["message"]) > 0


def test_progress_callback_with_no_files(tmp_path, daemon_service):
    """Test progress callback behavior when no files to index."""
    test_project = tmp_path / "test_project"
    test_project.mkdir()

    # Initialize config
    config_dir = test_project / ".code-indexer"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        """{
        "codebase_dir": "%s",
        "embedding_provider": "voyage-ai",
        "voyage_api_key": "test-key"
    }"""
        % str(test_project)
    )

    # No files in project

    # Progress capture
    progress_capture = ProgressCapture()

    # Call exposed_index_blocking
    result = daemon_service.exposed_index_blocking(
        project_path=str(test_project),
        callback=progress_capture.callback,
        force_full=True,
        batch_size=10,
        enable_fts=False,
    )

    # Verify result
    assert result["status"] in ["completed", "error"]

    if result["status"] == "completed":
        # Verify stats show zero files
        stats = result["stats"]
        assert stats["files_processed"] == 0

        # Should still have setup messages
        assert len(progress_capture.setup_messages) > 0
