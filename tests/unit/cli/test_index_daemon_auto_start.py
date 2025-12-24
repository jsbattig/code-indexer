"""Unit tests for index command daemon auto-start and fallback logic.

This module tests the critical auto-start retry loop and standalone fallback
that were missing from _index_via_daemon, causing infinite loops when the
daemon socket doesn't exist.

Tests written following TDD methodology - these tests FAIL until the fix is implemented.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import errno


class TestIndexDaemonAutoStart:
    """Test that _index_via_daemon has proper auto-start retry logic."""

    def test_index_auto_starts_daemon_on_socket_error(self):
        """
        FAILING TEST: Index should auto-start daemon when socket doesn't exist.

        Current behavior: No auto-start, immediate fallback to nonexistent _index_standalone
        Expected behavior: Call _start_daemon() and retry connection (like query command)

        This is the PRIMARY bug causing the infinite loop.
        """
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with (
            patch(
                "code_indexer.cli_daemon_delegation._find_config_file"
            ) as mock_find_config,
            patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect,
            patch(
                "code_indexer.cli_daemon_delegation._start_daemon"
            ) as mock_start_daemon,
            patch("code_indexer.cli_daemon_delegation._cleanup_stale_socket"),
            patch(
                "code_indexer.cli_daemon_delegation._index_standalone"
            ) as mock_standalone,
        ):
            # Setup: Socket doesn't exist (first attempt)
            config_path = Path("/fake/project/.code-indexer/config.json")
            mock_find_config.return_value = config_path

            # First call fails (no socket), second call succeeds (daemon started)
            socket_error = OSError(errno.ENOENT, "No such file or directory")
            mock_connect.side_effect = [
                socket_error,  # First attempt fails
                MagicMock(),  # Second attempt succeeds after auto-start
            ]

            mock_standalone.return_value = 0

            # Execute
            try:
                _index_via_daemon(
                    force_reindex=True,
                    daemon_config={"enabled": True, "socket_path": "/tmp/cidx.sock"},
                )
            except OSError:
                pass  # Expected until fix is implemented

            # CRITICAL ASSERTION: _start_daemon should have been called
            # This will FAIL because current implementation has no auto-start logic
            assert mock_start_daemon.called, (
                "Expected _start_daemon() to be called when socket doesn't exist. "
                "This is the PRIMARY bug - no auto-start retry loop exists!"
            )

    def test_index_retries_connection_three_times(self):
        """
        FAILING TEST: Index should retry connection 3 times with auto-start.

        Current behavior: No retry loop
        Expected behavior: for restart_attempt in range(3): try/except with auto-start
        """
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with (
            patch(
                "code_indexer.cli_daemon_delegation._find_config_file"
            ) as mock_find_config,
            patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect,
            patch(
                "code_indexer.cli_daemon_delegation._start_daemon"
            ) as mock_start_daemon,
            patch("code_indexer.cli_daemon_delegation._cleanup_stale_socket"),
            patch(
                "code_indexer.cli_daemon_delegation._index_standalone"
            ) as mock_standalone,
        ):
            # Setup
            config_path = Path("/fake/project/.code-indexer/config.json")
            mock_find_config.return_value = config_path

            # All connection attempts fail
            socket_error = OSError(errno.ENOENT, "No such file or directory")
            mock_connect.side_effect = socket_error

            mock_standalone.return_value = 0

            # Execute
            try:
                _index_via_daemon(
                    force_reindex=True,
                    daemon_config={"enabled": True, "socket_path": "/tmp/cidx.sock"},
                )
            except Exception:
                pass  # Expected until fix is implemented

            # CRITICAL ASSERTION: Should attempt to start daemon 2 times
            # (restart attempts 0 and 1, give up on attempt 2)
            # This will FAIL because no retry loop exists
            assert mock_start_daemon.call_count == 2, (
                f"Expected 2 daemon start attempts, got {mock_start_daemon.call_count}. "
                "No retry loop exists in current implementation!"
            )

    def test_index_cleans_up_progress_display_before_retry(self):
        """
        FAILING TEST: Index should stop progress display before retrying.

        Current behavior: No retry, no cleanup
        Expected behavior: Call rich_live_manager.stop_display() before retry
        """
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with (
            patch(
                "code_indexer.cli_daemon_delegation._find_config_file"
            ) as mock_find_config,
            patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect,
            patch("code_indexer.cli_daemon_delegation._start_daemon"),
            patch("code_indexer.cli_daemon_delegation._cleanup_stale_socket"),
            patch(
                "code_indexer.cli_daemon_delegation._index_standalone"
            ) as mock_standalone,
            patch("code_indexer.cli_daemon_delegation.console") as mock_console,
        ):
            # Setup
            config_path = Path("/fake/project/.code-indexer/config.json")
            mock_find_config.return_value = config_path

            # Connection fails, then succeeds
            socket_error = OSError(errno.ENOENT, "No such file or directory")
            mock_conn = MagicMock()
            mock_conn.root.exposed_index_blocking.return_value = {
                "status": "completed",
                "message": "",
                "stats": {
                    "files_processed": 0,
                    "chunks_created": 0,
                    "duration_seconds": 0.1,
                    "cancelled": False,
                    "failed_files": 0,
                },
            }
            mock_connect.side_effect = [socket_error, mock_conn]

            mock_standalone.return_value = 0

            # Execute
            try:
                _index_via_daemon(
                    force_reindex=True,
                    daemon_config={"enabled": True, "socket_path": "/tmp/cidx.sock"},
                )
            except Exception:
                pass  # Expected until fix is implemented

            # CRITICAL: Should print retry message
            # This will FAIL because no retry loop exists
            retry_message_found = any(
                "attempting restart" in str(call_args).lower()
                for call_args in mock_console.print.call_args_list
            )
            assert retry_message_found, (
                "Expected retry message '⚠️  Daemon connection failed, attempting restart'. "
                "No retry loop exists!"
            )

    def test_index_falls_back_to_actual_standalone_after_retries_exhausted(self):
        """
        FAILING TEST: Index should call actual _index_standalone after 2 failed retries.

        Current behavior: Calls nonexistent _index_standalone() function
        Expected behavior: Import and call cli.index with standalone=True context
        """
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with (
            patch(
                "code_indexer.cli_daemon_delegation._find_config_file"
            ) as mock_find_config,
            patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect,
            patch("code_indexer.cli_daemon_delegation._start_daemon"),
            patch(
                "code_indexer.cli_daemon_delegation._index_standalone"
            ) as mock_standalone,
        ):
            # Setup
            config_path = Path("/fake/project/.code-indexer/config.json")
            mock_find_config.return_value = config_path

            # All connection attempts fail
            socket_error = OSError(errno.ENOENT, "No such file or directory")
            mock_connect.side_effect = socket_error

            mock_standalone.return_value = 0

            # Execute
            try:
                result = _index_via_daemon(
                    force_reindex=True,
                    daemon_config={"enabled": True, "socket_path": "/tmp/cidx.sock"},
                )
            except Exception as e:
                # Current implementation will raise because _index_standalone doesn't exist
                assert (
                    "_index_standalone" in str(e).lower()
                    or "has no attribute" in str(e).lower()
                ), f"Expected NameError for nonexistent _index_standalone, got: {e}"
            else:
                # If we get here, the fix is implemented
                assert result == 0, "Expected successful fallback to standalone"

    def test_index_no_infinite_loop_when_daemon_unavailable(self):
        """
        FAILING TEST: Index should NOT loop infinitely when daemon unavailable.

        Current behavior: Infinite "Falling back to standalone" loop
        Expected behavior: Max 3 attempts, then actual standalone fallback, exit

        This is the USER-VISIBLE symptom of the bug.
        """
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with (
            patch(
                "code_indexer.cli_daemon_delegation._find_config_file"
            ) as mock_find_config,
            patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect,
            patch("code_indexer.cli_daemon_delegation._start_daemon"),
            patch(
                "code_indexer.cli_daemon_delegation._index_standalone"
            ) as mock_standalone,
        ):
            # Setup
            config_path = Path("/fake/project/.code-indexer/config.json")
            mock_find_config.return_value = config_path

            # All connection attempts fail
            socket_error = OSError(errno.ENOENT, "No such file or directory")
            mock_connect.side_effect = socket_error

            mock_standalone.return_value = 0

            # Track number of connection attempts to detect infinite loop
            connection_attempts = []

            def track_connect(*args, **kwargs):
                connection_attempts.append(1)
                # Safety: Prevent actual infinite loop in test
                if len(connection_attempts) > 10:
                    raise RuntimeError(
                        "INFINITE LOOP DETECTED: >10 connection attempts!"
                    )
                raise socket_error

            mock_connect.side_effect = track_connect

            # Execute
            try:
                _index_via_daemon(
                    force_reindex=True,
                    daemon_config={"enabled": True, "socket_path": "/tmp/cidx.sock"},
                )
            except RuntimeError as e:
                if "INFINITE LOOP" in str(e):
                    pytest.fail(
                        "INFINITE LOOP DETECTED! Current implementation keeps retrying forever. "
                        "Need to add max retry limit of 3 attempts."
                    )
            except Exception:
                pass  # Other errors expected until fix is implemented

            # CRITICAL: Should make exactly 3 connection attempts (0, 1, 2)
            # This will FAIL because current implementation either:
            # 1. Makes only 1 attempt (no retry), OR
            # 2. Loops infinitely
            assert len(connection_attempts) == 3, (
                f"Expected exactly 3 connection attempts, got {len(connection_attempts)}. "
                "Need retry loop with max 3 attempts to prevent infinite loop!"
            )


class TestIndexStandaloneFallback:
    """Test that standalone fallback actually works."""

    def test_index_standalone_function_exists(self):
        """
        FAILING TEST: _index_standalone function should exist.

        Current behavior: Function doesn't exist, causes NameError
        Expected behavior: Function exists and properly invokes cli.index in standalone mode
        """
        from code_indexer import cli_daemon_delegation

        # This will FAIL because _index_standalone doesn't exist
        assert hasattr(cli_daemon_delegation, "_index_standalone"), (
            "_index_standalone function doesn't exist! "
            "Need to create it similar to _query_standalone pattern."
        )

    def test_index_standalone_calls_cli_index_with_click_context(self):
        """
        FAILING TEST: _index_standalone should invoke cli.index with proper Click context.

        Expected behavior: Create Click context with standalone=True, call ctx.invoke()
        """
        # Can't test until _index_standalone exists
        pytest.skip("Need to implement _index_standalone first")

    def test_index_standalone_prevents_recursive_daemon_delegation(self):
        """
        FAILING TEST: _index_standalone should pass standalone=True to prevent recursion.

        Expected behavior: ctx.obj["standalone"] = True prevents recursive daemon check
        """
        # Can't test until _index_standalone exists
        pytest.skip("Need to implement _index_standalone first")


class TestIndexDaemonAutoStartIntegration:
    """Integration tests for complete auto-start workflow."""

    def test_index_full_workflow_socket_missing_to_success(self):
        """
        FAILING TEST: Test complete workflow: socket missing → auto-start → retry → success.

        This is the IDEAL happy path after the fix.
        """
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with (
            patch(
                "code_indexer.cli_daemon_delegation._find_config_file"
            ) as mock_find_config,
            patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect,
            patch(
                "code_indexer.cli_daemon_delegation._start_daemon"
            ) as mock_start_daemon,
            patch(
                "code_indexer.cli_daemon_delegation._cleanup_stale_socket"
            ) as mock_cleanup,
        ):
            # Setup
            config_path = Path("/fake/project/.code-indexer/config.json")
            mock_find_config.return_value = config_path

            # First attempt fails (no socket), second succeeds (daemon started)
            socket_error = OSError(errno.ENOENT, "No such file or directory")
            mock_conn = MagicMock()
            mock_conn.root.exposed_index_blocking.return_value = {
                "status": "completed",
                "message": "Indexing completed successfully",
                "stats": {
                    "files_processed": 42,
                    "chunks_created": 100,
                    "duration_seconds": 5.5,
                    "cancelled": False,
                    "failed_files": 0,
                },
            }
            mock_connect.side_effect = [socket_error, mock_conn]

            # Execute
            try:
                result = _index_via_daemon(
                    force_reindex=True,
                    daemon_config={"enabled": True, "socket_path": "/tmp/cidx.sock"},
                )
            except Exception as e:
                pytest.fail(
                    f"Auto-start workflow failed: {e}\n"
                    "Expected: socket error → cleanup → start daemon → retry → success"
                )

            # ASSERTIONS: Complete workflow executed correctly
            assert mock_cleanup.called, "Expected socket cleanup before restart"
            assert mock_start_daemon.called, "Expected daemon auto-start"
            assert (
                mock_connect.call_count == 2
            ), "Expected 2 connection attempts (fail, then succeed)"
            assert result == 0, "Expected successful indexing after auto-start"

    def test_index_full_workflow_all_retries_fail_to_standalone(self):
        """
        FAILING TEST: Test complete workflow: all retries fail → standalone fallback.

        This is the unhappy path - daemon completely unavailable.
        """
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with (
            patch(
                "code_indexer.cli_daemon_delegation._find_config_file"
            ) as mock_find_config,
            patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect,
            patch(
                "code_indexer.cli_daemon_delegation._start_daemon"
            ) as mock_start_daemon,
            patch("code_indexer.cli_daemon_delegation._cleanup_stale_socket"),
            patch(
                "code_indexer.cli_daemon_delegation._index_standalone"
            ) as mock_standalone,
        ):
            # Setup
            config_path = Path("/fake/project/.code-indexer/config.json")
            mock_find_config.return_value = config_path

            # All connection attempts fail
            socket_error = OSError(errno.ENOENT, "No such file or directory")
            mock_connect.side_effect = socket_error

            mock_standalone.return_value = 0

            # Execute
            try:
                _index_via_daemon(
                    force_reindex=True,
                    daemon_config={"enabled": True, "socket_path": "/tmp/cidx.sock"},
                )
            except Exception:
                pass  # Expected until _index_standalone exists

            # ASSERTIONS: Retry sequence, then fallback
            assert mock_start_daemon.call_count == 2, "Expected 2 daemon start attempts"
            assert mock_connect.call_count == 3, "Expected 3 connection attempts"
            assert (
                mock_standalone.called
            ), "Expected fallback to standalone after retries exhausted"
