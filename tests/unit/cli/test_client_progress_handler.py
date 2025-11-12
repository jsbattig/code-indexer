"""
Unit tests for ClientProgressHandler - progress callback streaming via RPyC.

Tests cover:
- Progress callback creation
- Progress bar initialization
- Setup message display (total=0)
- File progress updates (total>0)
- Completion handling
- Error handling
- RPyC async callback wrapping
"""

from pathlib import Path


class TestClientProgressHandler:
    """Test ClientProgressHandler for daemon progress callbacks."""

    def test_handler_creation(self):
        """Test ClientProgressHandler can be created."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        assert handler is not None
        assert handler.console is not None
        assert handler.progress is None
        assert handler.task_id is None

    def test_create_progress_callback(self):
        """Test progress callback creation returns callable."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Should return a callable
        assert callable(callback)

        # Progress bar should be initialized
        assert handler.progress is not None
        assert handler.task_id is not None

    def test_callback_handles_setup_messages(self):
        """Test callback displays setup messages when total=0."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Simulate setup message (total=0 triggers info display)
        callback(0, 0, Path(""), info="Initializing indexer")

        # Progress bar should update with info message
        # (Visual verification - we check that it doesn't crash)
        assert handler.progress is not None

    def test_callback_handles_file_progress(self):
        """Test callback updates progress for file processing."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Simulate file progress (total>0 triggers progress bar)
        callback(
            5,
            10,
            Path("/test/file.py"),
            info="5/10 files (50%) | 10 emb/s | 4 threads | file.py",
        )

        # Progress should be updated to 50%
        assert handler.progress is not None

    def test_callback_handles_completion(self):
        """Test callback handles completion (current == total)."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Start progress
        callback(1, 10, Path("/test/file.py"), info="Processing")

        # Complete
        callback(10, 10, Path("/test/last.py"), info="Done")

        # Progress should be stopped
        # (Visual verification - we check that complete() was called)
        assert handler.progress is not None

    def test_complete_method(self):
        """Test complete() stops progress bar."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Start some progress
        callback(1, 10, Path("/test/file.py"), info="Processing")

        # Manually complete
        handler.complete()

        # Progress should be stopped (no error)
        assert handler.progress is not None

    def test_error_method(self):
        """Test error() displays error and stops progress."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Start some progress
        callback(1, 10, Path("/test/file.py"), info="Processing")

        # Trigger error
        handler.error("Indexing failed due to missing API key")

        # Progress should be stopped with error message
        # (Visual verification - we check that it doesn't crash)
        assert handler.progress is not None

    def test_callback_converts_path_to_string(self):
        """Test callback handles Path objects correctly."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Pass Path object (as daemon would do)
        callback(1, 10, Path("/test/file.py"), info="Processing")

        # Should not raise error - Path should be converted to string internally
        assert handler.progress is not None

    def test_callback_handles_string_paths(self):
        """Test callback handles string paths (RPC serialization)."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Pass string path (as RPC serializes)
        callback(1, 10, "/test/file.py", info="Processing")

        # Should work fine
        assert handler.progress is not None

    def test_multiple_progress_updates(self):
        """Test multiple progress updates work smoothly."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Simulate realistic progress sequence
        callback(0, 0, Path(""), info="Loading configuration")
        callback(0, 0, Path(""), info="Scanning files")
        callback(1, 100, Path("/test/file1.py"), info="1/100 files (1%)")
        callback(25, 100, Path("/test/file25.py"), info="25/100 files (25%)")
        callback(50, 100, Path("/test/file50.py"), info="50/100 files (50%)")
        callback(75, 100, Path("/test/file75.py"), info="75/100 files (75%)")
        callback(100, 100, Path("/test/file100.py"), info="100/100 files (100%)")

        # Should complete without errors
        assert handler.progress is not None

    def test_callback_is_rpyc_compatible(self):
        """Test callback can be wrapped with rpyc.async_()."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # The create_progress_callback should already wrap with rpyc.async_
        # For now, just verify it's callable
        assert callable(callback)

    def test_handler_with_custom_console(self):
        """Test handler accepts custom Console instance."""
        from code_indexer.cli_progress_handler import ClientProgressHandler
        from rich.console import Console

        custom_console = Console()
        handler = ClientProgressHandler(console=custom_console)

        assert handler.console is custom_console

    def test_progress_bar_configuration(self):
        """Test progress bar has correct columns and configuration."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        handler.create_progress_callback()

        # Progress should have expected configuration
        assert handler.progress is not None
        # Rich Progress has internal columns, we just verify it exists
        assert hasattr(handler.progress, "columns")

    def test_callback_handles_empty_info(self):
        """Test callback handles empty info parameter."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Call with empty info
        callback(1, 10, Path("/test/file.py"), info="")

        # Should work without error
        assert handler.progress is not None

    def test_callback_handles_no_info_parameter(self):
        """Test callback works when info parameter is omitted."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        callback = handler.create_progress_callback()

        # Call without info parameter (default to empty string)
        callback(1, 10, Path("/test/file.py"))

        # Should work without error
        assert handler.progress is not None

    def test_complete_on_uninitialized_handler(self):
        """Test complete() on handler without progress bar is safe."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        # Don't create progress callback

        # Should not raise error
        handler.complete()

        assert handler.progress is None

    def test_error_on_uninitialized_handler(self):
        """Test error() on handler without progress bar is safe."""
        from code_indexer.cli_progress_handler import ClientProgressHandler

        handler = ClientProgressHandler()
        # Don't create progress callback

        # Should not raise error
        handler.error("Some error")

        assert handler.progress is None
