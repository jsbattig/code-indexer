"""Test cidx status timeout when daemon enabled but not running.

This test reproduces the issue where `cidx status` hangs indefinitely
when daemon.enabled=true but no daemon process is running.
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, Mock
import signal
import pytest


class TestStatusDaemonTimeout:
    """Test status command timeout handling when daemon unavailable."""

    def test_status_command_timeout_when_daemon_not_running(self):
        """Test that status doesn't hang when daemon enabled but not running.

        This test reproduces the evolution repository issue:
        - daemon.enabled=true in config
        - Stale socket file exists but daemon is not running
        - cidx status should timeout and fallback, not hang indefinitely

        CRITICAL: This simulates the exact condition where unix_connect
        hangs forever trying to connect to a stale socket.
        """
        from code_indexer.cli_daemon_delegation import _status_via_daemon

        # Create temporary project directory with config
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir(parents=True)

            # Config with daemon enabled but no actual daemon
            config_file = config_dir / "config.json"
            config = {
                "daemon": {
                    "enabled": True,
                    "ttl_minutes": 10,
                    "auto_shutdown_on_idle": True,
                },
                "embedding_provider": "voyageai",
                "qdrant": {"mode": "filesystem"},
            }
            config_file.write_text(json.dumps(config, indent=2))

            socket_path = config_dir / "daemon.sock"

            # Create STALE socket file (critical for reproducing the hang!)
            # This simulates a daemon that crashed or shutdown without cleanup
            import socket as socket_module

            sock = socket_module.socket(
                socket_module.AF_UNIX, socket_module.SOCK_STREAM
            )
            sock.bind(str(socket_path))
            sock.close()  # Close without listen() - creates stale socket

            assert socket_path.exists(), "Stale socket should exist for this test"

            # Mock ConfigManager to return our test config
            with patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config:
                mock_mgr = Mock()
                mock_mgr.get_socket_path.return_value = socket_path
                mock_mgr.get_daemon_config.return_value = config["daemon"]
                mock_config.return_value = mock_mgr

                # Mock _status_standalone to verify fallback is called
                with patch(
                    "code_indexer.cli_daemon_delegation._status_standalone"
                ) as mock_standalone:
                    mock_standalone.return_value = 0

                    # Execute status with timeout wrapper
                    start_time = time.time()

                    def timeout_handler(signum, frame):
                        raise TimeoutError(
                            f"Status command hung for {time.time() - start_time:.1f}s"
                        )

                    # Set 5-second timeout alarm
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(5)

                    try:
                        result = _status_via_daemon()
                        elapsed = time.time() - start_time

                        # Cancel alarm
                        signal.alarm(0)

                        # Should complete quickly (within 5 seconds)
                        assert (
                            elapsed < 5.0
                        ), f"Status took {elapsed:.1f}s, should be <5s"

                        # Should return success
                        assert result == 0, "Status should succeed with fallback"

                        # Should have fallen back to standalone
                        assert (
                            mock_standalone.call_count == 1
                        ), "Should fallback to standalone status"

                    except TimeoutError as e:
                        # Cancel alarm
                        signal.alarm(0)
                        pytest.fail(
                            f"TEST FAILURE: {e} - This reproduces the evolution hang bug!"
                        )

    def test_connect_to_daemon_timeout_on_missing_socket(self):
        """Test _connect_to_daemon raises error quickly when socket missing.

        The function should NOT hang indefinitely when trying to connect
        to a non-existent socket file.
        """
        from code_indexer.cli_daemon_delegation import _connect_to_daemon

        # Non-existent socket path
        socket_path = Path("/tmp/nonexistent-daemon-socket-12345.sock")
        assert not socket_path.exists(), "Socket should not exist for this test"

        daemon_config = {"retry_delays_ms": [100, 500]}  # Fast retries for testing

        # Should raise ConnectionError quickly, not hang
        start_time = time.time()

        with pytest.raises((ConnectionRefusedError, FileNotFoundError, OSError)):
            _connect_to_daemon(socket_path, daemon_config)

        elapsed = time.time() - start_time

        # Should fail quickly (retries + delays = ~0.6s max)
        assert elapsed < 2.0, f"Connection attempts took {elapsed:.1f}s, should be <2s"

    def test_connect_to_daemon_with_custom_timeout(self):
        """Test that connection timeout can be customized.

        The fix allows specifying a custom connection timeout to prevent
        indefinite hangs when daemon is not responding.
        """
        from code_indexer.cli_daemon_delegation import _connect_to_daemon

        # Non-existent socket path
        socket_path = Path("/tmp/nonexistent-timeout-test.sock")
        daemon_config = {"retry_delays_ms": [50]}  # Fast retry for testing

        # Custom timeout should be respected
        start_time = time.time()

        with pytest.raises((FileNotFoundError, ConnectionRefusedError, OSError)):
            # Use shorter timeout to verify it's respected
            _connect_to_daemon(socket_path, daemon_config, connection_timeout=0.5)

        elapsed = time.time() - start_time

        # Should fail quickly with custom timeout (~0.5s + retry delays)
        assert (
            elapsed < 1.5
        ), f"Connection with 0.5s timeout took {elapsed:.1f}s, should be <1.5s"
