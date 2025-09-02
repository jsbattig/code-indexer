"""
Unit tests for ServerTestHelper and ServerLifecycleManager.

Tests the server lifecycle management functionality needed for comprehensive
E2E testing of the multi-user CIDX server.
"""

import time
import requests
from unittest.mock import patch, MagicMock

from tests.utils.server_test_helpers import ServerTestHelper, ServerLifecycleManager


class TestServerTestHelper:
    """Unit tests for ServerTestHelper class."""

    def test_server_test_helper_init(self, tmp_path):
        """Test that ServerTestHelper initializes properly."""
        helper = ServerTestHelper(server_dir=tmp_path, port=8080, timeout=30)

        assert helper.server_dir == tmp_path
        assert helper.port == 8080
        assert helper.timeout == 30
        assert helper.server_process is None
        assert helper.server_url == "http://localhost:8080"

    def test_is_server_running_when_not_running(self):
        """Test is_server_running returns False when server not running."""
        helper = ServerTestHelper(port=9999)  # Unlikely to be used

        assert not helper.is_server_running()

    @patch("requests.get")
    def test_is_server_running_when_running(self, mock_get):
        """Test is_server_running returns True when server responds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        helper = ServerTestHelper(port=8080)

        assert helper.is_server_running()
        mock_get.assert_called_once_with("http://localhost:8080/health", timeout=2)

    @patch("requests.get")
    def test_is_server_running_handles_exceptions(self, mock_get):
        """Test is_server_running handles request exceptions gracefully."""
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")

        helper = ServerTestHelper(port=8080)

        assert not helper.is_server_running()

    def test_wait_for_server_ready_timeout(self):
        """Test wait_for_server_ready times out appropriately."""
        helper = ServerTestHelper(port=9999, timeout=1)  # 1 second timeout

        start_time = time.time()
        result = helper.wait_for_server_ready()
        elapsed_time = time.time() - start_time

        assert not result
        assert elapsed_time >= 1.0  # Should have waited at least 1 second
        assert elapsed_time < 2.0  # But not much longer

    @patch("requests.get")
    def test_wait_for_server_ready_success(self, mock_get):
        """Test wait_for_server_ready succeeds when server becomes ready."""
        # Mock server not ready first, then ready
        mock_response_not_ready = MagicMock()
        mock_response_not_ready.status_code = 503

        mock_response_ready = MagicMock()
        mock_response_ready.status_code = 200

        mock_get.side_effect = [
            requests.exceptions.RequestException(),  # First call fails
            mock_response_not_ready,  # Second call returns 503
            mock_response_ready,  # Third call succeeds
        ]

        helper = ServerTestHelper(port=8080, timeout=10)

        result = helper.wait_for_server_ready()
        assert result

    def test_generate_server_config_creates_valid_config(self, tmp_path):
        """Test that generate_server_config creates valid configuration."""
        helper = ServerTestHelper(server_dir=tmp_path, port=8080)

        config = helper.generate_server_config()

        assert isinstance(config, dict)
        assert config["port"] == 8080
        assert "jwt_secret" in config
        assert "database_url" in config
        assert "users_file" in config
        assert config["debug_mode"] is True  # Test mode

    def test_create_test_server_directory_structure(self, tmp_path):
        """Test that server directory structure is created properly."""
        helper = ServerTestHelper(server_dir=tmp_path)

        helper.create_test_server_directory()

        assert tmp_path.exists()
        assert (tmp_path / "config.json").exists()
        assert (tmp_path / "users.json").exists()
        assert (tmp_path / "logs").exists()
        assert (tmp_path / "logs").is_dir()

    def test_cleanup_server_files_removes_files(self, tmp_path):
        """Test that cleanup removes server-related files."""
        helper = ServerTestHelper(server_dir=tmp_path)

        # Create some test files
        (tmp_path / "config.json").touch()
        (tmp_path / "users.json").touch()
        (tmp_path / "server.log").touch()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "app.log").touch()

        helper.cleanup_server_files()

        # Files should be removed
        assert not (tmp_path / "config.json").exists()
        assert not (tmp_path / "users.json").exists()
        assert not (tmp_path / "server.log").exists()
        assert not logs_dir.exists()

    def test_create_test_users_file(self, tmp_path):
        """Test that test users file is created with valid content."""
        helper = ServerTestHelper(server_dir=tmp_path)

        users_file = helper.create_test_users_file()

        assert users_file.exists()

        # Load and verify content
        import json

        with open(users_file) as f:
            users_data = json.load(f)

        assert "admin" in users_data
        admin_user = users_data["admin"]
        assert admin_user["role"] == "admin"
        assert admin_user["password_hash"].startswith("$2b$")

    def test_get_server_info_when_not_running(self):
        """Test get_server_info when server is not running."""
        helper = ServerTestHelper(port=9999)

        info = helper.get_server_info()

        assert info["running"] is False
        assert info["port"] == 9999
        assert info["process_id"] is None
        assert info["health_status"] is None

    @patch("requests.get")
    def test_get_server_info_when_running(self, mock_get):
        """Test get_server_info when server is running."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_get.return_value = mock_response

        helper = ServerTestHelper(port=8080)
        helper.server_process = MagicMock()
        helper.server_process.pid = 12345

        info = helper.get_server_info()

        assert info["running"] is True
        assert info["port"] == 8080
        assert info["process_id"] == 12345
        assert info["health_status"] == {"status": "healthy"}


class TestServerLifecycleManager:
    """Unit tests for ServerLifecycleManager class."""

    def test_server_lifecycle_manager_init(self, tmp_path):
        """Test that ServerLifecycleManager initializes properly."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        assert manager.base_path == tmp_path
        assert manager.active_servers == {}
        assert manager.port_registry == set()

    def test_allocate_port_returns_unique_ports(self, tmp_path):
        """Test that port allocation returns unique, available ports."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        port1 = manager.allocate_port()
        port2 = manager.allocate_port()
        port3 = manager.allocate_port()

        # Should be unique
        ports = {port1, port2, port3}
        assert len(ports) == 3

        # Should be in valid range
        for port in ports:
            assert 8000 <= port <= 9999

    def test_release_port_removes_from_registry(self, tmp_path):
        """Test that releasing port removes it from registry."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        port = manager.allocate_port()
        assert port in manager.port_registry

        manager.release_port(port)
        assert port not in manager.port_registry

    def test_create_test_server_creates_helper(self, tmp_path):
        """Test that create_test_server creates ServerTestHelper."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        server_id = "test_server_1"
        helper = manager.create_test_server(server_id)

        assert isinstance(helper, ServerTestHelper)
        assert server_id in manager.active_servers
        assert manager.active_servers[server_id] == helper
        assert helper.port in manager.port_registry

    def test_create_test_server_with_specific_port(self, tmp_path):
        """Test creating server with specific port."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        server_id = "test_server_specific"
        helper = manager.create_test_server(server_id, port=8080)

        assert helper.port == 8080
        assert 8080 in manager.port_registry

    def test_get_server_returns_correct_helper(self, tmp_path):
        """Test that get_server returns the correct helper."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        server_id = "test_server_get"
        helper = manager.create_test_server(server_id)

        retrieved_helper = manager.get_server(server_id)
        assert retrieved_helper == helper

        # Non-existent server should return None
        assert manager.get_server("nonexistent") is None

    def test_cleanup_server_removes_from_registry(self, tmp_path):
        """Test that cleanup_server removes server from registries."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        server_id = "test_server_cleanup"
        helper = manager.create_test_server(server_id)
        port = helper.port

        # Verify server is registered
        assert server_id in manager.active_servers
        assert port in manager.port_registry

        # Cleanup server
        manager.cleanup_server(server_id)

        # Verify server is removed
        assert server_id not in manager.active_servers
        assert port not in manager.port_registry

    def test_cleanup_all_servers_removes_all(self, tmp_path):
        """Test that cleanup_all_servers removes all servers."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        # Create multiple servers
        for i in range(3):
            manager.create_test_server(f"test_server_{i}")

        assert len(manager.active_servers) == 3
        assert len(manager.port_registry) == 3

        # Cleanup all
        manager.cleanup_all_servers()

        assert len(manager.active_servers) == 0
        assert len(manager.port_registry) == 0

    def test_list_active_servers_returns_correct_info(self, tmp_path):
        """Test that list_active_servers returns correct information."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        # Create servers
        server_ids = ["server_1", "server_2"]
        for server_id in server_ids:
            manager.create_test_server(server_id)

        active_servers = manager.list_active_servers()

        assert len(active_servers) == 2
        assert all(server_id in active_servers for server_id in server_ids)

        # Check server info structure
        for server_id, info in active_servers.items():
            assert "port" in info
            assert "server_dir" in info
            assert "running" in info

    def test_find_available_port_avoids_used_ports(self, tmp_path):
        """Test that find_available_port avoids already used ports."""
        manager = ServerLifecycleManager(base_path=tmp_path)

        # Manually add some ports to registry
        used_ports = {8080, 8081, 8082}
        manager.port_registry.update(used_ports)

        # Find available port
        available_port = manager._find_available_port()

        assert available_port not in used_ports
        assert 8000 <= available_port <= 9999
