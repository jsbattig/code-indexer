"""
Unit tests for daemon lifecycle commands (start/stop/watch-stop).

Tests the CLI commands that control daemon lifecycle.
"""

from pathlib import Path
from unittest.mock import Mock, patch


class TestStartCommand:
    """Test 'cidx start' command."""

    def test_start_requires_daemon_enabled_in_config(self):
        """Test start fails with clear error when daemon not enabled."""
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

                # Verify error message printed
                print_calls = [str(call) for call in mock_print.call_args_list]
                assert any("not enabled" in call.lower() for call in print_calls)
                assert any("cidx config --daemon" in call for call in print_calls)

    def test_start_detects_already_running_daemon(self):
        """Test start detects daemon already running via socket connection."""
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
                    mock_conn.close.assert_called_once()

                    # Verify message about already running
                    print_calls = [str(call) for call in mock_print.call_args_list]
                    assert any(
                        "already running" in call.lower() for call in print_calls
                    )

    def test_start_launches_daemon_subprocess(self):
        """Test start launches daemon as background subprocess."""
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
                mock_conn = Mock()
                # First call: daemon not running, second: daemon started
                mock_connect.side_effect = [ConnectionRefusedError(), mock_conn]

                with patch("subprocess.Popen") as mock_popen:
                    with patch("time.sleep"):
                        with patch("rich.console.Console.print"):
                            result = start_daemon_command()

                            assert result == 0
                            assert mock_popen.call_count == 1

                            # Verify subprocess call
                            popen_call = mock_popen.call_args
                            cmd = popen_call[0][0]
                            assert any("daemon" in str(arg) for arg in cmd)

    def test_start_verifies_daemon_actually_started(self):
        """Test start verifies daemon is responsive after starting."""
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
                mock_conn = Mock()
                mock_conn.root.exposed_get_status.return_value = {"status": "running"}
                # Not running initially, then running after start
                mock_connect.side_effect = [ConnectionRefusedError(), mock_conn]

                with patch("subprocess.Popen"):
                    with patch("time.sleep"):
                        with patch("rich.console.Console.print"):
                            result = start_daemon_command()

                            assert result == 0
                            # Should call get_status to verify
                            mock_conn.root.exposed_get_status.assert_called_once()

    def test_start_fails_if_daemon_doesnt_start(self):
        """Test start reports failure if daemon doesn't become responsive."""
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
                # Never becomes responsive
                mock_connect.side_effect = ConnectionRefusedError()

                with patch("subprocess.Popen"):
                    with patch("time.sleep"):
                        with patch("rich.console.Console.print") as mock_print:
                            result = start_daemon_command()

                            assert result == 1

                            # Verify failure message
                            print_calls = [
                                str(call) for call in mock_print.call_args_list
                            ]
                            assert any("failed" in call.lower() for call in print_calls)


class TestStopCommand:
    """Test 'cidx stop' command."""

    def test_stop_reports_warning_when_daemon_not_enabled(self):
        """Test stop shows warning when daemon mode not enabled."""
        from code_indexer.cli_daemon_lifecycle import stop_daemon_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": False}
            mock_config.return_value = mock_mgr

            with patch("rich.console.Console.print") as mock_print:
                result = stop_daemon_command()

                assert result == 1

                # Should print warning
                print_calls = [str(call) for call in mock_print.call_args_list]
                assert any("not enabled" in call.lower() for call in print_calls)

    def test_stop_reports_success_when_daemon_not_running(self):
        """Test stop succeeds silently when daemon already stopped."""
        from code_indexer.cli_daemon_lifecycle import stop_daemon_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": True}
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch("rpyc.utils.factory.unix_connect") as mock_connect:
                mock_connect.side_effect = ConnectionRefusedError()

                with patch("rich.console.Console.print") as mock_print:
                    result = stop_daemon_command()

                    assert result == 0

                    # Should indicate not running
                    print_calls = [str(call) for call in mock_print.call_args_list]
                    assert any("not running" in call.lower() for call in print_calls)

    def test_stop_calls_shutdown_on_daemon(self):
        """Test stop calls exposed_shutdown on daemon."""
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
                # First call: daemon running, second: daemon stopped
                mock_connect.side_effect = [mock_conn, ConnectionRefusedError()]

                with patch("time.sleep"):
                    with patch("rich.console.Console.print"):
                        result = stop_daemon_command()

                        assert result == 0
                        mock_conn.root.exposed_shutdown.assert_called_once()

    def test_stop_stops_watch_before_shutdown(self):
        """Test stop stops active watch before shutting down daemon."""
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
                mock_conn.root.exposed_watch_status.return_value = {"watching": True}
                mock_connect.side_effect = [mock_conn, ConnectionRefusedError()]

                with patch("time.sleep"):
                    with patch("rich.console.Console.print"):
                        result = stop_daemon_command()

                        assert result == 0
                        # Should stop watch first
                        mock_conn.root.exposed_watch_stop.assert_called_once()
                        # Then shutdown
                        mock_conn.root.exposed_shutdown.assert_called_once()

    def test_stop_verifies_daemon_actually_stopped(self):
        """Test stop verifies daemon is no longer responsive."""
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
                # Daemon running, then not responsive after stop
                mock_connect.side_effect = [mock_conn, ConnectionRefusedError()]

                with patch("time.sleep"):
                    with patch("rich.console.Console.print") as mock_print:
                        result = stop_daemon_command()

                        assert result == 0

                        # Should verify stopped
                        assert mock_connect.call_count == 2

                        # Should print success message
                        print_calls = [str(call) for call in mock_print.call_args_list]
                        assert any("stopped" in call.lower() for call in print_calls)

    def test_stop_fails_if_daemon_still_responsive(self):
        """Test stop reports failure if daemon still responsive after shutdown."""
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
                # Daemon still responsive after shutdown
                mock_connect.return_value = mock_conn

                with patch("time.sleep"):
                    with patch("rich.console.Console.print") as mock_print:
                        result = stop_daemon_command()

                        assert result == 1

                        # Should print failure message
                        print_calls = [str(call) for call in mock_print.call_args_list]
                        assert any("failed" in call.lower() for call in print_calls)


class TestWatchStopCommand:
    """Test 'cidx watch-stop' command."""

    def test_watch_stop_requires_daemon_mode(self):
        """Test watch-stop fails when daemon mode not enabled."""
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

                # Should print error about daemon mode
                print_calls = [str(call) for call in mock_print.call_args_list]
                assert any("daemon mode" in call.lower() for call in print_calls)

    def test_watch_stop_reports_error_when_daemon_not_running(self):
        """Test watch-stop reports error when daemon not running."""
        from code_indexer.cli_daemon_lifecycle import watch_stop_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": True}
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch("rpyc.utils.factory.unix_connect") as mock_connect:
                mock_connect.side_effect = ConnectionRefusedError()

                with patch("rich.console.Console.print") as mock_print:
                    result = watch_stop_command()

                    assert result == 1

                    # Should indicate daemon not running
                    print_calls = [str(call) for call in mock_print.call_args_list]
                    assert any("not running" in call.lower() for call in print_calls)

    def test_watch_stop_calls_exposed_watch_stop(self):
        """Test watch-stop calls exposed_watch_stop on daemon."""
        from code_indexer.cli_daemon_lifecycle import watch_stop_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": True}
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch("rpyc.utils.factory.unix_connect") as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_watch_stop.return_value = {
                    "status": "stopped",
                    "files_processed": 42,
                    "updates_applied": 10,
                }
                mock_connect.return_value = mock_conn

                with patch("rich.console.Console.print") as mock_print:
                    result = watch_stop_command()

                    assert result == 0
                    mock_conn.root.exposed_watch_stop.assert_called_once()

                    # Should display stats
                    print_calls = [str(call) for call in mock_print.call_args_list]
                    assert any("42" in call for call in print_calls)  # files_processed
                    assert any("10" in call for call in print_calls)  # updates_applied

    def test_watch_stop_reports_when_watch_not_running(self):
        """Test watch-stop reports when watch not running."""
        from code_indexer.cli_daemon_lifecycle import watch_stop_command

        with patch(
            "code_indexer.config.ConfigManager.create_with_backtrack"
        ) as mock_config:
            mock_mgr = Mock()
            mock_mgr.get_daemon_config.return_value = {"enabled": True}
            mock_mgr.get_socket_path.return_value = Path("/tmp/test.sock")
            mock_config.return_value = mock_mgr

            with patch("rpyc.utils.factory.unix_connect") as mock_connect:
                mock_conn = Mock()
                mock_conn.root.exposed_watch_stop.return_value = {
                    "status": "not_running"
                }
                mock_connect.return_value = mock_conn

                with patch("rich.console.Console.print") as mock_print:
                    result = watch_stop_command()

                    assert result == 1

                    # Should indicate watch not running
                    print_calls = [str(call) for call in mock_print.call_args_list]
                    assert any("not running" in call.lower() for call in print_calls)
