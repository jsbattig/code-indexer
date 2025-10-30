"""Integration tests for daemon lifecycle.

Tests daemon startup, socket binding, client connections, and shutdown.
"""

import subprocess
import time
import pytest
import rpyc
import signal
import json


class TestDaemonStartup:
    """Test daemon startup and socket binding."""

    @pytest.fixture
    def test_project(self, tmp_path):
        """Create a test project with config."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create .code-indexer directory
        config_dir = project_path / ".code-indexer"
        config_dir.mkdir()

        # Create minimal config.json
        config_file = config_dir / "config.json"
        config = {
            "embedding_provider": "voyageai",
            "api_key": "test-key"
        }
        config_file.write_text(json.dumps(config))

        return config_file

    def test_daemon_starts_successfully(self, test_project):
        """Daemon should start and bind to socket."""
        socket_path = test_project.parent / "daemon.sock"

        # Start daemon in background
        proc = subprocess.Popen(
            ["python3", "-m", "code_indexer.daemon", str(test_project)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Wait for socket to appear
            for _ in range(50):  # 5 seconds total
                if socket_path.exists():
                    break
                time.sleep(0.1)

            # Socket should exist
            assert socket_path.exists(), "Daemon socket not created"

            # Should be able to connect
            conn = rpyc.utils.factory.unix_connect(str(socket_path))
            conn.close()

        finally:
            # Cleanup
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
            if socket_path.exists():
                socket_path.unlink()

    def test_socket_binding_prevents_second_daemon(self, test_project):
        """Second daemon should fail to start when socket already bound."""
        socket_path = test_project.parent / "daemon.sock"

        # Start first daemon
        proc1 = subprocess.Popen(
            ["python3", "-m", "code_indexer.daemon", str(test_project)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Wait for socket
            for _ in range(50):
                if socket_path.exists():
                    break
                time.sleep(0.1)

            assert socket_path.exists()

            # Try to start second daemon
            proc2 = subprocess.Popen(
                ["python3", "-m", "code_indexer.daemon", str(test_project)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Second daemon should exit with error
            stdout, stderr = proc2.communicate(timeout=5)
            assert proc2.returncode != 0, "Second daemon should fail to start"
            assert b"already running" in stderr.lower(), "Should indicate daemon already running"

        finally:
            # Cleanup
            proc1.send_signal(signal.SIGTERM)
            proc1.wait(timeout=5)
            if socket_path.exists():
                socket_path.unlink()

    def test_daemon_cleans_stale_socket(self, test_project):
        """Daemon should remove stale socket and start successfully."""
        socket_path = test_project.parent / "daemon.sock"

        # Create stale socket file
        socket_path.touch()

        # Start daemon (should clean stale socket)
        proc = subprocess.Popen(
            ["python3", "-m", "code_indexer.daemon", str(test_project)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Wait for daemon to start
            for _ in range(50):
                if socket_path.exists():
                    try:
                        # Try to connect
                        conn = rpyc.utils.factory.unix_connect(str(socket_path))
                        conn.close()
                        break
                    except Exception:
                        pass
                time.sleep(0.1)

            # Should be able to connect
            conn = rpyc.utils.factory.unix_connect(str(socket_path))
            conn.close()

        finally:
            # Cleanup
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
            if socket_path.exists():
                socket_path.unlink()


class TestClientConnections:
    """Test client connections to daemon."""

    @pytest.fixture
    def running_daemon(self, tmp_path):
        """Start a daemon and yield connection details."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        config_dir = project_path / ".code-indexer"
        config_dir.mkdir()

        config_file = config_dir / "config.json"
        config = {
            "embedding_provider": "voyageai",
            "api_key": "test-key"
        }
        config_file.write_text(json.dumps(config))

        socket_path = config_dir / "daemon.sock"

        # Start daemon
        proc = subprocess.Popen(
            ["python3", "-m", "code_indexer.daemon", str(config_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for socket
        for _ in range(50):
            if socket_path.exists():
                try:
                    conn = rpyc.utils.factory.unix_connect(str(socket_path))
                    conn.close()
                    break
                except Exception:
                    pass
            time.sleep(0.1)

        yield socket_path, proc

        # Cleanup
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        if socket_path.exists():
            socket_path.unlink()

    def test_client_can_connect_to_daemon(self, running_daemon):
        """Client should be able to connect to running daemon."""
        socket_path, proc = running_daemon

        # Connect to daemon
        conn = rpyc.utils.factory.unix_connect(str(socket_path))

        try:
            # Should be able to ping
            result = conn.root.exposed_ping()
            assert result["status"] == "ok"

        finally:
            conn.close()

    def test_multiple_clients_can_connect_concurrently(self, running_daemon):
        """Multiple clients should be able to connect simultaneously."""
        socket_path, proc = running_daemon

        # Connect multiple clients
        connections = []
        try:
            for _ in range(3):
                conn = rpyc.utils.factory.unix_connect(str(socket_path))
                connections.append(conn)

            # All should be able to ping
            for conn in connections:
                result = conn.root.exposed_ping()
                assert result["status"] == "ok"

        finally:
            for conn in connections:
                conn.close()

    def test_client_disconnect_cleanup(self, running_daemon):
        """Client disconnection should not affect daemon."""
        socket_path, proc = running_daemon

        # Connect and disconnect
        conn1 = rpyc.utils.factory.unix_connect(str(socket_path))
        conn1.close()

        # Should be able to connect again
        conn2 = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            result = conn2.root.exposed_ping()
            assert result["status"] == "ok"
        finally:
            conn2.close()


class TestDaemonShutdown:
    """Test daemon shutdown and cleanup."""

    @pytest.fixture
    def test_project(self, tmp_path):
        """Create test project."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        config_dir = project_path / ".code-indexer"
        config_dir.mkdir()

        config_file = config_dir / "config.json"
        config = {
            "embedding_provider": "voyageai",
            "api_key": "test-key"
        }
        config_file.write_text(json.dumps(config))

        return config_file

    def test_daemon_cleans_socket_on_sigterm(self, test_project):
        """Daemon should clean up socket when receiving SIGTERM."""
        socket_path = test_project.parent / "daemon.sock"

        # Start daemon
        proc = subprocess.Popen(
            ["python3", "-m", "code_indexer.daemon", str(test_project)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for socket
        for _ in range(50):
            if socket_path.exists():
                break
            time.sleep(0.1)

        assert socket_path.exists()

        # Send SIGTERM
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)

        # Socket should be cleaned up
        # Note: Might take a moment for cleanup
        time.sleep(0.5)
        assert not socket_path.exists(), "Socket should be cleaned up"

    def test_daemon_shutdown_via_exposed_method(self, test_project):
        """Daemon should shutdown gracefully via exposed_shutdown."""
        socket_path = test_project.parent / "daemon.sock"

        # Start daemon
        proc = subprocess.Popen(
            ["python3", "-m", "code_indexer.daemon", str(test_project)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for socket
        for _ in range(50):
            if socket_path.exists():
                try:
                    conn = rpyc.utils.factory.unix_connect(str(socket_path))
                    conn.close()
                    break
                except Exception:
                    pass
            time.sleep(0.1)

        # Connect and shutdown
        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Call shutdown - this will exit the process
            conn.root.exposed_shutdown()
        except Exception:
            # Connection will be closed by shutdown
            pass

        # Wait for process to exit
        proc.wait(timeout=5)

        # Process should have exited
        assert proc.poll() is not None, "Daemon should have exited"
