"""
Server lifecycle test helpers for multi-user CIDX server testing.

This module provides utilities for managing server instances during E2E testing,
including server startup/shutdown, configuration, and health monitoring.
"""

import json
import time
import socket
import subprocess
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import requests
from passlib.context import CryptContext

logger = logging.getLogger(__name__)


class ServerTestHelper:
    """Helper class for managing a single test server instance."""

    def __init__(
        self,
        server_dir: Path = None,
        port: int = 8080,
        timeout: int = 30,
        config_override: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize server test helper.

        Args:
            server_dir: Directory for server files (optional)
            port: Port number for server
            timeout: Timeout for server operations
            config_override: Optional configuration overrides
        """
        self.server_dir = server_dir or Path.home() / ".tmp" / "cidx-test-server"
        self.port = port
        self.timeout = timeout
        self.config_override = config_override or {}

        self.server_process: Optional[subprocess.Popen] = None
        self.server_url = f"http://localhost:{self.port}"

        self._pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.logger = logging.getLogger(f"{__name__}.ServerTestHelper")

    def is_server_running(self) -> bool:
        """
        Check if server is running and responding.

        Returns:
            True if server is responding to health checks
        """
        try:
            response = requests.get(f"{self.server_url}/health", timeout=2)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def wait_for_server_ready(self, max_attempts: Optional[int] = None) -> bool:
        """
        Wait for server to become ready.

        Args:
            max_attempts: Maximum number of attempts (calculated from timeout if None)

        Returns:
            True if server becomes ready, False if timeout
        """
        if max_attempts is None:
            max_attempts = self.timeout

        for attempt in range(max_attempts):
            if self.is_server_running():
                self.logger.info(f"Server ready after {attempt + 1} attempts")
                return True

            time.sleep(1)

        self.logger.warning(f"Server not ready after {max_attempts} attempts")
        return False

    def start_server(self, wait_for_ready: bool = True) -> bool:
        """
        Start the test server.

        Args:
            wait_for_ready: Whether to wait for server to be ready

        Returns:
            True if server started successfully
        """
        if self.is_server_running():
            self.logger.info(f"Server already running on port {self.port}")
            return True

        try:
            # Create server directory and files
            self.create_test_server_directory()

            # Start server process
            self.server_process = subprocess.Popen(
                [
                    "python",
                    "-m",
                    "src.code_indexer.server.main",
                    "--port",
                    str(self.port),
                    "--host",
                    "localhost",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=Path.cwd(),
                env=self._get_server_environment(),
            )

            self.logger.info(f"Started server process (PID: {self.server_process.pid})")

            if wait_for_ready:
                if not self.wait_for_server_ready():
                    self.stop_server()
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            return False

    def stop_server(self) -> bool:
        """
        Stop the test server.

        Returns:
            True if server stopped successfully
        """
        if not self.server_process:
            return True

        try:
            # Try graceful shutdown first
            self.server_process.terminate()

            try:
                self.server_process.wait(timeout=10)
                self.logger.info("Server process terminated gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                self.server_process.kill()
                self.server_process.wait()
                self.logger.warning("Server process force killed")

            self.server_process = None
            return True

        except Exception as e:
            self.logger.error(f"Failed to stop server: {e}")
            return False

    def restart_server(self) -> bool:
        """
        Restart the test server.

        Returns:
            True if restart was successful
        """
        self.stop_server()
        time.sleep(1)  # Brief pause
        return self.start_server()

    def generate_server_config(self) -> Dict[str, Any]:
        """
        Generate server configuration for testing.

        Returns:
            Configuration dictionary
        """
        config = {
            "port": self.port,
            "host": "localhost",
            "debug_mode": True,
            "jwt_secret": "test-jwt-secret-key",
            "jwt_expiry_minutes": 60,
            "database_url": f"sqlite:///{self.server_dir}/test.db",
            "users_file": str(self.server_dir / "users.json"),
            "log_level": "DEBUG",
            "log_file": str(self.server_dir / "logs" / "server.log"),
            "cors_origins": ["*"],
            "rate_limiting": {"enabled": False},  # Disable for testing
        }

        # Apply any overrides
        config.update(self.config_override)

        return config

    def create_test_server_directory(self) -> None:
        """Create server directory structure with test configuration."""
        # Create directory structure
        self.server_dir.mkdir(parents=True, exist_ok=True)
        (self.server_dir / "logs").mkdir(exist_ok=True)

        # Create configuration file
        config = self.generate_server_config()
        with open(self.server_dir / "config.json", "w") as f:
            json.dump(config, f, indent=2)

        # Create users file with test users
        self.create_test_users_file()

        self.logger.info(f"Created test server directory: {self.server_dir}")

    def create_test_users_file(self) -> Path:
        """
        Create users.json file with test users.

        Returns:
            Path to created users file
        """
        users_data = {}

        # Default test users
        test_users = [
            {"username": "admin", "role": "admin", "password": "admin"},
            {"username": "poweruser", "role": "power_user", "password": "password"},
            {"username": "normaluser", "role": "normal_user", "password": "password"},
            {"username": "testuser", "role": "normal_user", "password": "password"},
        ]

        current_time = datetime.now(timezone.utc).isoformat()

        for user_spec in test_users:
            password_hash = self._pwd_context.hash(user_spec["password"])

            users_data[user_spec["username"]] = {
                "role": user_spec["role"],
                "password_hash": password_hash,
                "created_at": current_time,
                "is_active": True,
            }

        users_file = self.server_dir / "users.json"
        with open(users_file, "w") as f:
            json.dump(users_data, f, indent=2)

        self.logger.debug(f"Created users file with {len(users_data)} test users")
        return users_file

    def cleanup_server_files(self) -> None:
        """Clean up server-related files and directories."""
        import shutil

        if self.server_dir.exists():
            try:
                shutil.rmtree(self.server_dir)
                self.logger.info(f"Cleaned up server directory: {self.server_dir}")
            except Exception as e:
                self.logger.warning(f"Failed to clean up server directory: {e}")

    def get_server_info(self) -> Dict[str, Any]:
        """
        Get information about the server instance.

        Returns:
            Dictionary with server information
        """
        info = {
            "port": self.port,
            "server_url": self.server_url,
            "server_dir": str(self.server_dir),
            "running": self.is_server_running(),
            "process_id": self.server_process.pid if self.server_process else None,
            "timeout": self.timeout,
        }

        # Add health status if server is running
        if info["running"]:
            try:
                response = requests.get(f"{self.server_url}/health", timeout=2)
                if response.status_code == 200:
                    info["health_status"] = response.json()
                else:
                    info["health_status"] = {
                        "status": "unhealthy",
                        "status_code": response.status_code,
                    }
            except requests.exceptions.RequestException as e:
                info["health_status"] = {"status": "unreachable", "error": str(e)}
        else:
            info["health_status"] = None

        return info

    def make_api_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
    ) -> requests.Response:
        """
        Make API request to the test server.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/api/users")
            headers: Optional request headers
            json_data: Optional JSON data for request body
            timeout: Request timeout

        Returns:
            Response object
        """
        url = f"{self.server_url}{endpoint}"

        return requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=json_data,
            timeout=timeout,
        )

    def _get_server_environment(self) -> Dict[str, str]:
        """Get environment variables for server process."""
        env = os.environ.copy()

        # Add test-specific environment variables
        env.update(
            {
                "CIDX_TESTING": "true",
                "CIDX_SERVER_DIR": str(self.server_dir),
                "CIDX_LOG_LEVEL": "DEBUG",
            }
        )

        return env

    def __enter__(self):
        """Context manager entry."""
        self.start_server()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_server()
        self.cleanup_server_files()


class ServerLifecycleManager:
    """Manager for multiple test server instances."""

    def __init__(self, base_path: Path = None, port_range: tuple = (8000, 9999)):
        """
        Initialize server lifecycle manager.

        Args:
            base_path: Base path for server directories
            port_range: Range of ports to allocate from
        """
        self.base_path = base_path or Path.home() / ".tmp" / "cidx-test-servers"
        self.port_range = port_range

        self.active_servers: Dict[str, ServerTestHelper] = {}
        self.port_registry: set = set()

        self.logger = logging.getLogger(f"{__name__}.ServerLifecycleManager")

    def create_test_server(
        self,
        server_id: str,
        port: Optional[int] = None,
        config_override: Optional[Dict[str, Any]] = None,
        auto_start: bool = False,
    ) -> ServerTestHelper:
        """
        Create a new test server instance.

        Args:
            server_id: Unique identifier for the server
            port: Specific port (allocated automatically if None)
            config_override: Optional configuration overrides
            auto_start: Whether to start server immediately

        Returns:
            ServerTestHelper instance
        """
        if server_id in self.active_servers:
            raise ValueError(f"Server with ID '{server_id}' already exists")

        # Allocate port if not specified
        if port is None:
            port = self.allocate_port()
        else:
            if port in self.port_registry:
                raise ValueError(f"Port {port} is already allocated")
            self.port_registry.add(port)

        # Create server directory
        server_dir = self.base_path / server_id
        server_dir.mkdir(parents=True, exist_ok=True)

        # Create server helper
        helper = ServerTestHelper(
            server_dir=server_dir, port=port, config_override=config_override or {}
        )

        self.active_servers[server_id] = helper

        if auto_start:
            helper.start_server()

        self.logger.info(f"Created test server: {server_id} on port {port}")
        return helper

    def get_server(self, server_id: str) -> Optional[ServerTestHelper]:
        """
        Get server helper by ID.

        Args:
            server_id: Server identifier

        Returns:
            ServerTestHelper instance or None if not found
        """
        return self.active_servers.get(server_id)

    def cleanup_server(self, server_id: str) -> bool:
        """
        Clean up and remove a server instance.

        Args:
            server_id: Server identifier

        Returns:
            True if cleanup was successful
        """
        helper = self.active_servers.get(server_id)
        if not helper:
            return False

        try:
            # Stop server if running
            helper.stop_server()

            # Clean up files
            helper.cleanup_server_files()

            # Release port
            self.release_port(helper.port)

            # Remove from registry
            del self.active_servers[server_id]

            self.logger.info(f"Cleaned up server: {server_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to clean up server {server_id}: {e}")
            return False

    def cleanup_all_servers(self) -> None:
        """Clean up all server instances."""
        server_ids = list(self.active_servers.keys())

        for server_id in server_ids:
            self.cleanup_server(server_id)

        self.logger.info(f"Cleaned up {len(server_ids)} servers")

    def allocate_port(self) -> int:
        """
        Allocate an available port.

        Returns:
            Available port number
        """
        port = self._find_available_port()
        self.port_registry.add(port)
        return port

    def release_port(self, port: int) -> None:
        """Release a previously allocated port."""
        self.port_registry.discard(port)

    def list_active_servers(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all active servers.

        Returns:
            Dictionary mapping server IDs to server information
        """
        server_info = {}

        for server_id, helper in self.active_servers.items():
            server_info[server_id] = {
                "port": helper.port,
                "server_dir": str(helper.server_dir),
                "running": helper.is_server_running(),
                "process_id": (
                    helper.server_process.pid if helper.server_process else None
                ),
            }

        return server_info

    def start_all_servers(self, wait_for_ready: bool = True) -> Dict[str, bool]:
        """
        Start all registered servers.

        Args:
            wait_for_ready: Whether to wait for each server to be ready

        Returns:
            Dictionary mapping server IDs to success status
        """
        results = {}

        for server_id, helper in self.active_servers.items():
            try:
                success = helper.start_server(wait_for_ready=wait_for_ready)
                results[server_id] = success

                if success:
                    self.logger.info(f"Started server: {server_id}")
                else:
                    self.logger.error(f"Failed to start server: {server_id}")

            except Exception as e:
                self.logger.error(f"Error starting server {server_id}: {e}")
                results[server_id] = False

        return results

    def stop_all_servers(self) -> Dict[str, bool]:
        """
        Stop all running servers.

        Returns:
            Dictionary mapping server IDs to success status
        """
        results = {}

        for server_id, helper in self.active_servers.items():
            try:
                success = helper.stop_server()
                results[server_id] = success

                if success:
                    self.logger.info(f"Stopped server: {server_id}")
                else:
                    self.logger.error(f"Failed to stop server: {server_id}")

            except Exception as e:
                self.logger.error(f"Error stopping server {server_id}: {e}")
                results[server_id] = False

        return results

    def _find_available_port(self) -> int:
        """Find an available port in the specified range."""
        for port in range(self.port_range[0], self.port_range[1] + 1):
            if port in self.port_registry:
                continue

            # Check if port is actually available
            if self._is_port_available(port):
                return port

        raise RuntimeError("No available ports in the specified range")

    def _is_port_available(self, port: int) -> bool:
        """Check if a port is available for binding."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("localhost", port))
                return True
        except OSError:
            return False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup_all_servers()


# Convenience functions
def create_test_server_environment(
    server_count: int = 1, base_path: Path = None, auto_start: bool = True
) -> ServerLifecycleManager:
    """
    Create a complete test server environment with multiple servers.

    Args:
        server_count: Number of servers to create
        base_path: Base path for server directories
        auto_start: Whether to start servers automatically

    Returns:
        Configured ServerLifecycleManager
    """
    manager = ServerLifecycleManager(base_path=base_path)

    # Create servers
    for i in range(server_count):
        server_id = f"test_server_{i:02d}"
        manager.create_test_server(server_id, auto_start=auto_start)

    return manager


def wait_for_servers_ready(
    manager: ServerLifecycleManager, timeout: int = 60
) -> Dict[str, bool]:
    """
    Wait for all servers in manager to become ready.

    Args:
        manager: Server lifecycle manager
        timeout: Total timeout for all servers

    Returns:
        Dictionary mapping server IDs to ready status
    """
    results = {}
    start_time = time.time()

    for server_id, helper in manager.active_servers.items():
        remaining_timeout = max(1, timeout - int(time.time() - start_time))
        helper.timeout = remaining_timeout

        results[server_id] = helper.wait_for_server_ready()

        if time.time() - start_time >= timeout:
            # Timeout exceeded, mark remaining servers as not ready
            for remaining_id in manager.active_servers:
                if remaining_id not in results:
                    results[remaining_id] = False
            break

    return results
