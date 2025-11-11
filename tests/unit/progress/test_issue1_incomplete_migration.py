"""Test Issue #1: Incomplete async migration in production code paths.

Bug #470: Only 1 of 3 production code paths was updated to use async_handle_progress_update.
This test verifies all production paths use the async queue pattern.
"""

from unittest.mock import MagicMock, Mock, patch
import pytest


class TestIssue1IncompleteMigration:
    """Test Issue #1: All production code paths must use async_handle_progress_update."""

    def test_cli_regular_indexing_uses_async_progress_update(self):
        """cli.py regular indexing (line ~3885) must use async_handle_progress_update.

        Issue #1: cli.py line 3885 still uses synchronous handle_progress_update().
        This blocks worker threads on Rich terminal I/O.

        Expected to FAIL initially: Uses handle_progress_update (synchronous).
        """
        # This test uses code inspection to verify the correct method is called
        # Read the entire cli.py source file

        from pathlib import Path

        cli_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "cli.py"
        )
        source = cli_path.read_text()

        # Search for handle_progress_update calls (synchronous - BAD)
        sync_calls = source.count("rich_live_manager.handle_progress_update(")

        # Search for async_handle_progress_update calls (async - GOOD)
        async_calls = source.count("rich_live_manager.async_handle_progress_update(")

        # All calls should be async
        # The test expects at least 2 async calls (temporal + regular indexing)
        assert async_calls >= 2, (
            f"Expected at least 2 async_handle_progress_update calls in cli.py, found {async_calls}. "
            f"Found {sync_calls} synchronous handle_progress_update calls (should be 0)."
        )

        assert sync_calls == 0, (
            f"Found {sync_calls} synchronous handle_progress_update calls in cli.py. "
            "All calls should use async_handle_progress_update to prevent worker thread blocking."
        )

    def test_daemon_delegation_uses_async_progress_update(self):
        """cli_daemon_delegation.py (line ~851) must use async_handle_progress_update.

        Issue #1: cli_daemon_delegation.py line 851 still uses synchronous handle_progress_update().
        This blocks worker threads in daemon mode.

        Expected to FAIL initially: Uses handle_progress_update (synchronous).
        """
        from pathlib import Path

        daemon_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "cli_daemon_delegation.py"
        )
        source = daemon_path.read_text()

        # Search for handle_progress_update calls (synchronous - BAD)
        sync_calls = source.count("rich_live_manager.handle_progress_update(")

        # Search for async_handle_progress_update calls (async - GOOD)
        async_calls = source.count("rich_live_manager.async_handle_progress_update(")

        # All calls should be async
        assert async_calls >= 1, (
            f"Expected at least 1 async_handle_progress_update call in cli_daemon_delegation.py, found {async_calls}. "
            f"Found {sync_calls} synchronous handle_progress_update calls (should be 0)."
        )

        assert sync_calls == 0, (
            f"Found {sync_calls} synchronous handle_progress_update calls in cli_daemon_delegation.py. "
            "All calls should use async_handle_progress_update to prevent worker thread blocking."
        )
