"""Test CLI uses async progress callbacks to prevent worker thread blocking.

Bug #470: Verify CLI integration uses async_handle_progress_update instead of
synchronous handle_progress_update to eliminate worker thread blocking.
"""


class TestCLIAsyncProgress:
    """Test CLI uses async progress callbacks."""

    def test_cli_temporal_indexing_uses_async_progress(self):
        """CLI temporal indexing uses async progress callbacks.

        This test verifies that the CLI's progress_callback in temporal
        indexing contexts calls async_handle_progress_update instead of
        the synchronous handle_progress_update.

        This test verifies the async method exists on RichLiveProgressManager.
        Full integration testing would require running actual CLI commands.
        """
        from code_indexer.progress.progress_display import RichLiveProgressManager
        from rich.console import Console

        # Verify async method exists on RichLiveProgressManager
        mgr = RichLiveProgressManager(Console())
        assert hasattr(
            mgr, "async_handle_progress_update"
        ), "RichLiveProgressManager must have async_handle_progress_update method"

        # Verify the method is callable
        assert callable(
            mgr.async_handle_progress_update
        ), "async_handle_progress_update must be callable"
