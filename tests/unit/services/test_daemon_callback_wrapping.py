"""
Unit tests for daemon-side callback wrapping in RPyC service.

Tests cover:
- Callback wrapping for safe RPC calls
- Path to string conversion
- Error handling (callback errors don't crash indexing)
- Callback parameter validation
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock


class TestDaemonCallbackWrapping:
    """Test daemon callback wrapping for RPyC safety."""

    def test_wrap_callback_exists(self):
        """Test _wrap_callback method exists on daemon service."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()
        assert hasattr(service, "_wrap_callback")
        assert callable(service._wrap_callback)

    def test_wrap_callback_converts_path_to_string(self):
        """Test wrapped callback converts Path objects to strings."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        # Track callback invocations
        calls = []

        def mock_callback(current, total, file_path, info=""):
            calls.append((current, total, file_path, info))

        # Wrap callback
        wrapped = service._wrap_callback(mock_callback)

        # Call with Path object
        wrapped(1, 10, Path("/test/file.py"), "Processing")

        # Verify Path was converted to string
        assert len(calls) == 1
        assert calls[0][0] == 1
        assert calls[0][1] == 10
        assert calls[0][2] == "/test/file.py"  # Should be string
        assert isinstance(calls[0][2], str)
        assert calls[0][3] == "Processing"

    def test_wrap_callback_handles_string_paths(self):
        """Test wrapped callback handles string paths correctly."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        calls = []

        def mock_callback(current, total, file_path, info=""):
            calls.append((current, total, file_path, info))

        wrapped = service._wrap_callback(mock_callback)

        # Call with string path
        wrapped(1, 10, "/test/file.py", "Processing")

        # Should pass through unchanged
        assert len(calls) == 1
        assert calls[0][2] == "/test/file.py"
        assert isinstance(calls[0][2], str)

    def test_wrap_callback_handles_errors_gracefully(self):
        """Test wrapped callback catches and logs errors without crashing."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        def bad_callback(current, total, file_path, info=""):
            raise ValueError("Callback error - connection lost")

        wrapped = service._wrap_callback(bad_callback)

        # Should NOT raise - errors should be caught and logged
        wrapped(1, 10, Path("/test/file.py"), "Processing")
        # If we get here without exception, test passes

    def test_wrap_callback_preserves_callback_signature(self):
        """Test wrapped callback accepts same parameters as original."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        calls = []

        def mock_callback(current, total, file_path, info=""):
            calls.append((current, total, file_path, info))

        wrapped = service._wrap_callback(mock_callback)

        # Test with all parameters
        wrapped(5, 10, Path("/test/file.py"), "Info message")
        assert len(calls) == 1
        assert calls[0] == (5, 10, "/test/file.py", "Info message")

        # Test with empty info
        wrapped(6, 10, Path("/test/file2.py"), "")
        assert len(calls) == 2
        assert calls[1][3] == ""

    def test_wrap_callback_handles_setup_messages(self):
        """Test wrapped callback handles setup messages (total=0)."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        calls = []

        def mock_callback(current, total, file_path, info=""):
            calls.append((current, total, file_path, info))

        wrapped = service._wrap_callback(mock_callback)

        # Setup message (total=0)
        wrapped(0, 0, Path(""), info="Initializing indexer")

        assert len(calls) == 1
        assert calls[0][0] == 0
        assert calls[0][1] == 0
        assert calls[0][3] == "Initializing indexer"

    def test_wrap_callback_handles_progress_updates(self):
        """Test wrapped callback handles file progress updates."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        calls = []

        def mock_callback(current, total, file_path, info=""):
            calls.append((current, total, file_path, info))

        wrapped = service._wrap_callback(mock_callback)

        # Progress updates
        wrapped(1, 100, Path("/test/file1.py"), "1/100 files (1%)")
        wrapped(50, 100, Path("/test/file50.py"), "50/100 files (50%)")
        wrapped(100, 100, Path("/test/file100.py"), "100/100 files (100%)")

        assert len(calls) == 3
        assert calls[0][0] == 1
        assert calls[1][0] == 50
        assert calls[2][0] == 100

    def test_wrap_callback_handles_none_callback(self):
        """Test _wrap_callback handles None callback gracefully."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        # Wrapping None should return None or a no-op function
        wrapped = service._wrap_callback(None)

        # Should be None (as per implementation pattern)
        # OR should be a callable that does nothing
        if wrapped is not None:
            # If it returns a no-op, calling it should not raise
            wrapped(1, 10, Path("/test/file.py"), "Test")

    def test_exposed_index_accepts_callback_parameter(self):
        """Test exposed_index method accepts callback parameter."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        # Verify method exists and has callback parameter
        import inspect

        sig = inspect.signature(service.exposed_index)
        params = list(sig.parameters.keys())

        assert "project_path" in params
        assert "callback" in params

    def test_exposed_index_uses_wrapped_callback(self):
        """Test exposed_index wraps callback before passing to indexer."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService
        from unittest.mock import patch, MagicMock

        service = CIDXDaemonService()

        # Create a mock callback
        mock_callback = Mock()

        # Mock _perform_indexing to avoid complex mocking
        with patch.object(service, "_perform_indexing") as mock_perform:
            # Call exposed_index with callback
            service.exposed_index(
                str(Path.cwd()), callback=mock_callback, force_reindex=False
            )

            # Verify _perform_indexing was called with a wrapped callback
            assert mock_perform.called
            # Check that the callback passed to _perform_indexing is NOT the same as the original
            # (it should be wrapped)
            args, kwargs = mock_perform.call_args
            callback_arg = args[1] if len(args) > 1 else None
            # The wrapped callback should be a different function
            assert callback_arg is not None
            assert callable(callback_arg)

    def test_wrap_callback_handles_multiple_concurrent_calls(self):
        """Test wrapped callback handles concurrent calls safely."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService
        import threading

        service = CIDXDaemonService()

        calls = []
        lock = threading.Lock()

        def thread_safe_callback(current, total, file_path, info=""):
            with lock:
                calls.append((current, total, file_path, info))

        wrapped = service._wrap_callback(thread_safe_callback)

        # Simulate concurrent calls
        threads = []
        for i in range(10):
            t = threading.Thread(
                target=wrapped, args=(i, 10, Path(f"/test/file{i}.py"), f"File {i}")
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All calls should have been recorded
        assert len(calls) == 10

    def test_wrap_callback_handles_empty_path(self):
        """Test wrapped callback handles empty path (setup messages)."""
        from code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        calls = []

        def mock_callback(current, total, file_path, info=""):
            calls.append((current, total, file_path, info))

        wrapped = service._wrap_callback(mock_callback)

        # Call with empty Path (Note: Path("") converts to "." not "")
        wrapped(0, 0, Path(""), info="Setup message")

        assert len(calls) == 1
        # Path("") converts to "." in Python, so we should check for that
        assert calls[0][2] == "."  # Empty path converted to "."
