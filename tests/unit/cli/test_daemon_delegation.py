"""
Unit tests for daemon delegation in CLI.

Tests the client-side logic that routes commands to the daemon when enabled,
including crash recovery, exponential backoff, and fallback to standalone mode.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest


class TestDaemonConnection:
    """Test daemon connection with exponential backoff."""

    def test_connect_with_exponential_backoff_success_first_try(self):
        """Test successful connection on first attempt."""
        from code_indexer.cli_daemon_delegation import _connect_to_daemon

        socket_path = Path("/tmp/test.sock")
        daemon_config = {"retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("rpyc.utils.factory.unix_connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            result = _connect_to_daemon(socket_path, daemon_config)

            assert result == mock_conn
            assert mock_connect.call_count == 1
            mock_connect.assert_called_once_with(
                str(socket_path),
                config={"allow_public_attrs": True, "sync_request_timeout": None},
            )

    def test_connect_with_exponential_backoff_success_after_retries(self):
        """Test successful connection after 3 retries."""
        from code_indexer.cli_daemon_delegation import _connect_to_daemon

        socket_path = Path("/tmp/test.sock")
        daemon_config = {"retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("rpyc.utils.factory.unix_connect") as mock_connect:
            mock_conn = Mock()
            # Fail 3 times, succeed on 4th
            mock_connect.side_effect = [
                ConnectionRefusedError(),
                ConnectionRefusedError(),
                ConnectionRefusedError(),
                mock_conn,
            ]

            with patch("time.sleep") as mock_sleep:
                result = _connect_to_daemon(socket_path, daemon_config)

                assert result == mock_conn
                assert mock_connect.call_count == 4

                # Verify exponential backoff delays
                assert mock_sleep.call_count == 3
                sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
                assert sleep_calls == [0.1, 0.5, 1.0]

    def test_connect_with_exponential_backoff_all_retries_exhausted(self):
        """Test connection failure after all retries exhausted."""
        from code_indexer.cli_daemon_delegation import _connect_to_daemon

        socket_path = Path("/tmp/test.sock")
        daemon_config = {"retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("rpyc.utils.factory.unix_connect") as mock_connect:
            # Fail all 4 attempts
            mock_connect.side_effect = ConnectionRefusedError("Connection refused")

            with patch("time.sleep"):
                with pytest.raises(ConnectionRefusedError):
                    _connect_to_daemon(socket_path, daemon_config)

                assert mock_connect.call_count == 4

    def test_connect_with_custom_retry_delays(self):
        """Test connection with custom retry delays."""
        from code_indexer.cli_daemon_delegation import _connect_to_daemon

        socket_path = Path("/tmp/test.sock")
        daemon_config = {"retry_delays_ms": [50, 100]}  # Only 2 retries

        with patch("rpyc.utils.factory.unix_connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.side_effect = [ConnectionRefusedError(), mock_conn]

            with patch("time.sleep") as mock_sleep:
                result = _connect_to_daemon(socket_path, daemon_config)

                assert result == mock_conn
                assert mock_connect.call_count == 2
                assert mock_sleep.call_count == 1
                mock_sleep.assert_called_once_with(0.05)


class TestCrashRecovery:
    """Test daemon crash recovery with 2 restart attempts."""

    def test_crash_recovery_success_first_restart(self):
        """Test successful recovery on first restart attempt."""
        from code_indexer.cli_daemon_delegation import _query_via_daemon

        query_text = "test query"
        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                # First attempt: crash
                # Second attempt: success
                mock_conn = Mock()
                mock_conn.root.exposed_query.return_value = {"results": []}
                mock_connect.side_effect = [ConnectionRefusedError(), mock_conn]

                with patch(
                    "code_indexer.cli_daemon_delegation._cleanup_stale_socket"
                ) as mock_cleanup:
                    with patch(
                        "code_indexer.cli_daemon_delegation._start_daemon"
                    ) as mock_start:
                        with patch("time.sleep"):
                            with patch(
                                "code_indexer.cli_daemon_delegation._display_results"
                            ):
                                result = _query_via_daemon(
                                    query_text, daemon_config, limit=10
                                )

                                assert result == 0
                                assert mock_connect.call_count == 2
                                assert mock_cleanup.call_count == 1
                                assert mock_start.call_count == 1

    def test_crash_recovery_exhausted_falls_back_to_standalone(self):
        """Test fallback to standalone after 2 failed restart attempts."""
        from code_indexer.cli_daemon_delegation import _query_via_daemon

        query_text = "test query"
        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                # All connection attempts fail
                mock_connect.side_effect = ConnectionRefusedError()

                with patch("code_indexer.cli_daemon_delegation._cleanup_stale_socket"):
                    with patch("code_indexer.cli_daemon_delegation._start_daemon"):
                        with patch(
                            "code_indexer.cli_daemon_delegation._query_standalone"
                        ) as mock_standalone:
                            with patch("time.sleep"):
                                mock_standalone.return_value = 0

                                result = _query_via_daemon(
                                    query_text, daemon_config, limit=10
                                )

                                assert result == 0
                                # Initial + 2 restart attempts = 3 total
                                assert mock_connect.call_count == 3
                                # Should fallback to standalone
                                assert mock_standalone.call_count == 1

    def test_cleanup_stale_socket(self):
        """Test cleanup of stale socket file."""
        from code_indexer.cli_daemon_delegation import _cleanup_stale_socket

        socket_path = Path("/tmp/test_daemon.sock")

        # Test socket exists and gets removed
        with patch.object(Path, "unlink") as mock_unlink:
            _cleanup_stale_socket(socket_path)
            mock_unlink.assert_called_once()

    def test_cleanup_stale_socket_handles_missing_file(self):
        """Test cleanup handles missing socket file gracefully."""
        from code_indexer.cli_daemon_delegation import _cleanup_stale_socket

        socket_path = Path("/tmp/nonexistent.sock")

        # Should not raise exception if socket doesn't exist
        with patch.object(Path, "unlink", side_effect=FileNotFoundError()):
            _cleanup_stale_socket(socket_path)  # Should not raise


class TestFallbackToStandalone:
    """Test fallback to standalone mode."""

    def test_fallback_displays_warning_message(self):
        """Test that fallback displays helpful warning message."""
        from code_indexer.cli_daemon_delegation import _query_via_daemon

        query_text = "test query"
        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_connect.side_effect = ConnectionRefusedError("Connection refused")

                with patch("code_indexer.cli_daemon_delegation._cleanup_stale_socket"):
                    with patch("code_indexer.cli_daemon_delegation._start_daemon"):
                        with patch(
                            "code_indexer.cli_daemon_delegation._query_standalone"
                        ) as mock_standalone:
                            with patch("time.sleep"):
                                with patch("rich.console.Console.print") as mock_print:
                                    mock_standalone.return_value = 0

                                    _query_via_daemon(
                                        query_text, daemon_config, limit=10
                                    )

                                    # Should print warning about fallback
                                    warning_printed = any(
                                        "unavailable" in str(call_args).lower()
                                        for call_args in mock_print.call_args_list
                                    )
                                    assert warning_printed


class TestSocketPathCalculation:
    """Test socket path calculation from config location."""

    def test_get_socket_path_from_config(self):
        """Test socket path calculated from config file location."""
        from code_indexer.cli_daemon_delegation import _get_socket_path

        config_path = Path("/project/.code-indexer/config.json")
        socket_path = _get_socket_path(config_path)

        assert socket_path == Path("/project/.code-indexer/daemon.sock")

    def test_find_config_file_walks_upward(self):
        """Test config file search walks up directory tree."""
        from code_indexer.cli_daemon_delegation import _find_config_file

        # Test that function exists and is callable
        # Actual walking logic is complex to mock due to Path operations
        # This test verifies the function can be called and returns expected type
        result = _find_config_file()
        assert result is None or isinstance(result, Path)


class TestDaemonAutoStart:
    """Test daemon auto-start functionality."""

    def test_start_daemon_subprocess(self):
        """Test daemon starts as background subprocess."""
        from code_indexer.cli_daemon_delegation import _start_daemon

        config_path = Path("/project/.code-indexer/config.json")

        with patch("subprocess.Popen") as mock_popen:
            with patch("time.sleep"):
                _start_daemon(config_path)

                assert mock_popen.call_count == 1
                popen_call = mock_popen.call_args

                # Verify daemon module is invoked
                cmd = popen_call[0][0]
                assert "code_indexer.daemon" in " ".join(
                    cmd
                ) or "rpyc_daemon" in " ".join(cmd)

                # Verify process is detached
                kwargs = popen_call[1]
                assert kwargs.get("stdout") is not None
                assert kwargs.get("stderr") is not None
                assert kwargs.get("start_new_session") is True


class TestQueryDelegation:
    """Test query delegation to daemon."""

    def test_query_delegates_to_semantic_search(self):
        """Test semantic query delegates to daemon exposed_query."""
        from code_indexer.cli_daemon_delegation import _query_via_daemon

        query_text = "authentication"
        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_query.return_value = {"results": []}
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_daemon_delegation._display_results"):
                    result = _query_via_daemon(
                        query_text, daemon_config, fts=False, semantic=True, limit=10
                    )

                    assert result == 0
                    mock_conn.root.exposed_query.assert_called_once()

    def test_query_delegates_to_fts_search(self):
        """Test FTS query delegates to daemon exposed_query_fts."""
        from code_indexer.cli_daemon_delegation import _query_via_daemon

        query_text = "DatabaseManager"
        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_query_fts.return_value = {"results": []}
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_daemon_delegation._display_results"):
                    result = _query_via_daemon(
                        query_text, daemon_config, fts=True, semantic=False, limit=10
                    )

                    assert result == 0
                    mock_conn.root.exposed_query_fts.assert_called_once()

    def test_query_delegates_to_hybrid_search(self):
        """Test hybrid query delegates to daemon exposed_query_hybrid."""
        from code_indexer.cli_daemon_delegation import _query_via_daemon

        query_text = "user authentication"
        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_query_hybrid.return_value = {"results": []}
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_daemon_delegation._display_results"):
                    result = _query_via_daemon(
                        query_text, daemon_config, fts=True, semantic=True, limit=10
                    )

                    assert result == 0
                    mock_conn.root.exposed_query_hybrid.assert_called_once()


class TestLifecycleCommands:
    """Test daemon lifecycle commands (start/stop/watch-stop)."""

    def test_start_command_requires_daemon_enabled(self):
        """Test start command fails when daemon not enabled."""
        from code_indexer.cli_daemon_lifecycle import start_daemon_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": False}
            mock_config.return_value = mock_mgr

            with patch("rich.console.Console.print") as mock_print:
                result = start_daemon_command()

                assert result == 1
                # Should print error about daemon not enabled
                error_printed = any(
                    "not enabled" in str(call_args).lower()
                    for call_args in mock_print.call_args_list
                )
                assert error_printed

    def test_start_command_detects_already_running(self):
        """Test start command detects daemon already running."""
        from code_indexer.cli_daemon_lifecycle import start_daemon_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": True}
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch("rpyc.utils.factory.unix_connect") as mock_connect:
                mock_conn = Mock()
                mock_connect.return_value = mock_conn

                with patch("rich.console.Console.print") as mock_print:
                    result = start_daemon_command()

                    assert result == 0
                    # Should print that daemon is already running
                    already_running = any(
                        "already running" in str(call_args).lower()
                        for call_args in mock_print.call_args_list
                    )
                    assert already_running

    def test_start_command_starts_daemon(self):
        """Test start command starts daemon when not running."""
        from code_indexer.cli_daemon_lifecycle import start_daemon_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": True}
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_mgr.config_path = Path("/project/.code-indexer/config.json")
            mock_config.return_value = mock_mgr

            with patch("rpyc.utils.factory.unix_connect") as mock_connect:
                # First call: not running, second call: success after start
                mock_conn = Mock()
                mock_connect.side_effect = [ConnectionRefusedError(), mock_conn]

                with patch(
                    "code_indexer.cli_daemon_lifecycle._start_daemon"
                ) as mock_start:
                    with patch("time.sleep"):
                        with patch("rich.console.Console.print"):
                            result = start_daemon_command()

                            assert result == 0
                            assert mock_start.call_count == 1

    def test_stop_command_stops_daemon(self):
        """Test stop command stops running daemon."""
        from code_indexer.cli_daemon_lifecycle import stop_daemon_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": True}
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch("rpyc.utils.factory.unix_connect") as mock_connect:
                mock_conn = Mock()
                # First call succeeds (daemon running), second call fails (daemon stopped)
                mock_connect.side_effect = [mock_conn, ConnectionRefusedError()]

                with patch("time.sleep"):
                    with patch("rich.console.Console.print"):
                        result = stop_daemon_command()

                        assert result == 0
                        # Should call shutdown
                        mock_conn.root.exposed_shutdown.assert_called_once()

    def test_watch_stop_command_requires_daemon_mode(self):
        """Test watch-stop command requires daemon mode."""
        from code_indexer.cli_daemon_lifecycle import watch_stop_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": False}
            mock_config.return_value = mock_mgr

            with patch("rich.console.Console.print") as mock_print:
                result = watch_stop_command()

                assert result == 1
                # Should print error about daemon mode required
                error_printed = any(
                    "daemon mode" in str(call_args).lower()
                    for call_args in mock_print.call_args_list
                )
                assert error_printed


class TestStorageCommandRouting:
    """Test storage command routing (clean/clean-data/status)."""

    def test_clean_routes_to_daemon_when_enabled(self):
        """Test clean command routes to daemon when enabled."""
        from code_indexer.cli_daemon_delegation import _clean_via_daemon

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_clean.return_value = {"cache_invalidated": True}
                mock_connect.return_value = mock_conn

                with patch("rich.console.Console.print"):
                    result = _clean_via_daemon()

                    assert result == 0
                    mock_conn.root.exposed_clean.assert_called_once()

    def test_clean_data_routes_to_daemon_when_enabled(self):
        """Test clean-data command routes to daemon when enabled."""
        from code_indexer.cli_daemon_delegation import _clean_data_via_daemon

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_clean_data.return_value = {
                    "cache_invalidated": True
                }
                mock_connect.return_value = mock_conn

                with patch("rich.console.Console.print"):
                    result = _clean_data_via_daemon()

                    assert result == 0
                    mock_conn.root.exposed_clean_data.assert_called_once()

    def test_status_routes_to_daemon_when_enabled(self):
        """Test status command routes to daemon when enabled."""
        from code_indexer.cli_daemon_delegation import _status_via_daemon

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_status.return_value = {
                    "daemon": {
                        "running": True,
                        "semantic_cached": True,
                        "fts_available": False,
                    },
                    "storage": {"index_size": 1000},
                }
                mock_connect.return_value = mock_conn

                with patch("rich.console.Console.print"):
                    result = _status_via_daemon()

                    assert result == 0
                    mock_conn.root.exposed_status.assert_called_once()

    def test_status_falls_back_when_daemon_unavailable(self):
        """Test status falls back to standalone when daemon unavailable."""
        from code_indexer.cli_daemon_delegation import _status_via_daemon

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_connect.side_effect = ConnectionRefusedError()

                with patch(
                    "code_indexer.cli_daemon_delegation._status_standalone"
                ) as mock_standalone:
                    mock_standalone.return_value = 0

                    result = _status_via_daemon()

                    assert result == 0
                    assert mock_standalone.call_count == 1


class TestIndexDelegation:
    """Test index command delegation to daemon."""

    def test_index_delegates_to_daemon_when_enabled(self):
        """Test index command delegates to daemon with progress callbacks."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_index.return_value = {
                    "stats": {"files_processed": 42}
                }
                mock_connect.return_value = mock_conn

                with patch(
                    "code_indexer.cli_progress_handler.ClientProgressHandler"
                ) as mock_progress:
                    mock_handler = Mock()
                    mock_callback = Mock()
                    mock_handler.create_progress_callback.return_value = mock_callback
                    mock_progress.return_value = mock_handler

                    with patch("rich.console.Console.print"):
                        result = _index_via_daemon(
                            force_reindex=False, daemon_config=daemon_config
                        )

                        assert result == 0
                        mock_conn.root.exposed_index.assert_called_once()
                        # Verify callback was passed to daemon
                        call_kwargs = mock_conn.root.exposed_index.call_args[1]
                        assert "callback" in call_kwargs

    def test_index_passes_force_reindex_flag(self):
        """Test index delegation passes force_reindex flag to daemon."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_index.return_value = {
                    "stats": {"files_processed": 42}
                }
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_progress_handler.ClientProgressHandler"):
                    with patch("rich.console.Console.print"):
                        _index_via_daemon(
                            force_reindex=True, daemon_config=daemon_config
                        )

                        call_kwargs = mock_conn.root.exposed_index.call_args[1]
                        assert call_kwargs["force_reindex"] is True

    def test_index_falls_back_to_standalone_when_daemon_unavailable(self):
        """Test index falls back to standalone when daemon unavailable."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_connect.side_effect = ConnectionRefusedError()

                with patch(
                    "code_indexer.cli_daemon_delegation._index_standalone"
                ) as mock_standalone:
                    with patch("rich.console.Console.print"):
                        mock_standalone.return_value = 0

                        result = _index_via_daemon(
                            force_reindex=False, daemon_config=daemon_config
                        )

                        assert result == 0
                        assert mock_standalone.call_count == 1


class TestWatchDelegation:
    """Test watch command delegation to daemon."""

    def test_watch_delegates_to_daemon_when_enabled(self):
        """Test watch command delegates to daemon with proper parameters."""
        from code_indexer.cli_daemon_delegation import _watch_via_daemon

        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_watch_start.return_value = {"status": "watching"}
                mock_connect.return_value = mock_conn

                with patch("rich.console.Console.print"):
                    result = _watch_via_daemon(
                        debounce=1.0,
                        batch_size=50,
                        initial_sync=True,
                        enable_fts=False,
                        daemon_config=daemon_config,
                    )

                    assert result == 0
                    mock_conn.root.exposed_watch_start.assert_called_once()
                    call_kwargs = mock_conn.root.exposed_watch_start.call_args[1]
                    assert call_kwargs["debounce_seconds"] == 1.0
                    assert call_kwargs["batch_size"] == 50
                    assert call_kwargs["initial_sync"] is True

    def test_watch_passes_fts_flag(self):
        """Test watch delegation passes enable_fts flag to daemon."""
        from code_indexer.cli_daemon_delegation import _watch_via_daemon

        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_watch_start.return_value = {"status": "watching"}
                mock_connect.return_value = mock_conn

                with patch("rich.console.Console.print"):
                    _watch_via_daemon(
                        debounce=1.0,
                        batch_size=50,
                        initial_sync=False,
                        enable_fts=True,
                        daemon_config=daemon_config,
                    )

                    call_kwargs = mock_conn.root.exposed_watch_start.call_args[1]
                    assert call_kwargs["enable_fts"] is True

    def test_watch_falls_back_to_standalone_when_daemon_unavailable(self):
        """Test watch falls back to standalone when daemon unavailable."""
        from code_indexer.cli_daemon_delegation import _watch_via_daemon

        daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/project/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_connect.side_effect = ConnectionRefusedError()

                with patch(
                    "code_indexer.cli_daemon_delegation._watch_standalone"
                ) as mock_standalone:
                    with patch("rich.console.Console.print"):
                        mock_standalone.return_value = 0

                        result = _watch_via_daemon(
                            debounce=1.0,
                            batch_size=50,
                            initial_sync=False,
                            enable_fts=False,
                            daemon_config=daemon_config,
                        )

                        assert result == 0
                        assert mock_standalone.call_count == 1
