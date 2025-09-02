"""
Server Lifecycle Management for CIDX Server.

Manages server startup, shutdown, status monitoring, and graceful shutdown
with proper signal handling and resource cleanup.
"""

import json
import logging
import os
import psutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

import requests  # type: ignore


class ServerStatus(str, Enum):
    """Server status enumeration."""

    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    STOPPING = "stopping"


@dataclass
class ServerStatusInfo:
    """Server status information."""

    status: ServerStatus
    pid: Optional[int] = None
    uptime: Optional[int] = None  # seconds
    port: Optional[int] = None
    active_jobs: int = 0
    host: Optional[str] = None
    errors: Optional[list] = None


class ServerLifecycleError(Exception):
    """Exception raised by server lifecycle operations."""

    pass


class ServerLifecycleManager:
    """
    Manages CIDX server lifecycle operations.

    Provides server start/stop/restart functionality with graceful shutdown,
    status monitoring, health checks, and proper signal handling.
    """

    def __init__(self, server_dir: Optional[str] = None):
        """
        Initialize server lifecycle manager.

        Args:
            server_dir: Server directory path (defaults to ~/.cidx-server)
        """
        if server_dir:
            self.server_dir = server_dir
        else:
            self.server_dir = str(Path.home() / ".cidx-server")

        self.server_dir_path = Path(self.server_dir)
        self.pidfile_path = self.server_dir_path / "server.pid"
        self.state_file_path = self.server_dir_path / "server.state"
        self.config_file_path = self.server_dir_path / "config.json"

        # Ensure server directory exists
        self.server_dir_path.mkdir(parents=True, exist_ok=True)

        # Graceful shutdown timeout settings
        self.graceful_timeout = 30  # seconds
        self.force_timeout = 10  # seconds

    def get_status(self) -> ServerStatusInfo:
        """Get current server status."""
        is_running = self._check_server_running()

        if not is_running:
            return ServerStatusInfo(
                status=ServerStatus.STOPPED,
                pid=None,
                uptime=None,
                port=None,
                active_jobs=0,
            )

        pid = self._get_server_pid()
        uptime = self._get_server_uptime()
        port = self._get_server_port()
        active_jobs = self._get_active_jobs_count()
        host = self._get_server_host()

        return ServerStatusInfo(
            status=ServerStatus.RUNNING,
            pid=pid,
            uptime=uptime,
            port=port,
            active_jobs=active_jobs,
            host=host,
        )

    def start_server(self) -> Dict[str, Any]:
        """Start the server."""
        # Check if server is already running
        if self._check_server_running():
            raise ServerLifecycleError("Server is already running")

        # Validate configuration
        try:
            self._validate_config()
        except Exception as e:
            raise ServerLifecycleError(f"Invalid server configuration: {str(e)}")

        # Load configuration
        config = self._load_config()

        # Start server process
        try:
            process = self._start_server_process(config)

            # Create pidfile
            self._create_pidfile(process.pid)

            # Save server state
            state = {
                "pid": process.pid,
                "port": config["port"],
                "host": config["host"],
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_server_state(state)

            return {
                "message": "Server started successfully",
                "server_url": f"http://{config['host']}:{config['port']}",
                "pid": process.pid,
            }

        except Exception as e:
            raise ServerLifecycleError(f"Failed to start server: {str(e)}")

    def stop_server(self, force: bool = False) -> Dict[str, Any]:
        """Stop the server gracefully."""
        if not self._check_server_running():
            raise ServerLifecycleError("No server is currently running")

        pid = self._get_server_pid()
        if pid is None:
            raise ServerLifecycleError("Cannot determine server PID")

        try:
            if force:
                success = self._force_shutdown(pid)
                message = "Server stopped forcefully" if success else "Server stopped"
                return {"message": message, "forced": force}
            else:
                # Try graceful shutdown first
                success = self._graceful_shutdown(pid)
                if not success:
                    # Fall back to forced shutdown
                    success = self._force_shutdown(pid)

                return {
                    "message": (
                        "Server stopped gracefully" if success else "Server stopped"
                    ),
                    "shutdown_time": (
                        self.graceful_timeout if success else self.force_timeout
                    ),
                }
        finally:
            # Clean up pidfile and state
            self._remove_pidfile()
            if self.state_file_path.exists():
                self.state_file_path.unlink()

    def restart_server(self) -> Dict[str, Any]:
        """Restart the server."""
        is_running = self._check_server_running()

        if is_running:
            # Stop server first
            self.stop_server()

            # Wait a moment for cleanup
            time.sleep(1)

        # Start server
        result = self.start_server()

        if is_running:
            result["message"] = "Server restarted successfully"
            result["restart_time"] = 5.0  # Approximate restart time
        else:
            result["message"] = "Server started successfully (was not running)"

        return result

    def install_signal_handlers(self):
        """Install signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def get_server_health(self) -> Dict[str, Any]:
        """Get server health information."""
        if not self._check_server_running():
            return {"status": "unhealthy", "error": "Server is not running"}

        try:
            # Get health from server endpoint
            return self._get_health_endpoint_response()
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Failed to get health information: {str(e)}",
            }

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logging.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._graceful_shutdown_async()

    def _graceful_shutdown_async(self):
        """Perform graceful shutdown in background thread."""

        def shutdown():
            pid = self._get_server_pid()
            if pid:
                self._graceful_shutdown(pid)

        thread = threading.Thread(target=shutdown)
        thread.daemon = True
        thread.start()

    def _graceful_shutdown(self, pid: int) -> bool:
        """Perform graceful shutdown."""
        try:
            # Send SIGTERM to allow graceful shutdown
            os.kill(pid, signal.SIGTERM)

            # Wait for process to stop
            timeout = float(self.graceful_timeout)
            while timeout > 0 and self._check_process_exists(pid):
                time.sleep(0.5)
                timeout -= 0.5

            # Check if process stopped
            return not self._check_process_exists(pid)

        except (OSError, ProcessLookupError):
            # Process doesn't exist or permission denied
            return True

    def _force_shutdown(self, pid: int) -> bool:
        """Perform forced shutdown."""
        try:
            # Send SIGKILL for forced shutdown
            os.kill(pid, signal.SIGKILL)

            # Wait briefly for process to die
            timeout = float(self.force_timeout)
            while timeout > 0 and self._check_process_exists(pid):
                time.sleep(0.1)
                timeout -= 0.1

            return not self._check_process_exists(pid)

        except (OSError, ProcessLookupError):
            # Process doesn't exist or permission denied
            return True

    def _check_server_running(self) -> bool:
        """Check if server is currently running."""
        pid = self._get_server_pid()
        if pid is None:
            return False

        return self._check_process_exists(pid)

    def _check_process_exists(self, pid: int) -> bool:
        """Check if process with given PID exists."""
        try:
            # Check if process exists and is a Python process
            process = psutil.Process(pid)
            if process.is_running() and "python" in process.name().lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    def _validate_config(self):
        """Validate server configuration."""
        if not self.config_file_path.exists():
            raise ServerLifecycleError("Server configuration not found")

        try:
            config = self._load_config()

            # Validate required fields
            required_fields = ["server_dir", "host", "port"]
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required field: {field}")

            # Validate port range
            port = config["port"]
            if not isinstance(port, int) or not (1 <= port <= 65535):
                raise ValueError(f"Port must be between 1 and 65535, got {port}")

        except (json.JSONDecodeError, ValueError) as e:
            raise ServerLifecycleError(f"Invalid server configuration: {str(e)}")

    def _load_config(self) -> Dict[str, Any]:
        """Load server configuration."""
        with open(self.config_file_path, "r") as f:
            result = json.load(f)
            return dict(result)

    def _get_server_pid(self) -> Optional[int]:
        """Get server PID from pidfile."""
        if not self.pidfile_path.exists():
            return None

        try:
            with open(self.pidfile_path, "r") as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            return None

    def _create_pidfile(self, pid: int):
        """Create pidfile with server PID."""
        with open(self.pidfile_path, "w") as f:
            f.write(str(pid))

    def _remove_pidfile(self):
        """Remove server pidfile."""
        if self.pidfile_path.exists():
            self.pidfile_path.unlink()

    def _save_server_state(self, state: Dict[str, Any]):
        """Save server state information."""
        with open(self.state_file_path, "w") as f:
            json.dump(state, f, indent=2)

    def _load_server_state(self) -> Optional[Dict[str, Any]]:
        """Load server state information."""
        if not self.state_file_path.exists():
            return None

        try:
            with open(self.state_file_path, "r") as f:
                result = json.load(f)
                return dict(result) if result is not None else None
        except (json.JSONDecodeError, OSError):
            return None

    def _start_server_process(self, config: Dict[str, Any]) -> subprocess.Popen:
        """Start the server process."""
        cmd = [
            sys.executable,
            "-m",
            "code_indexer.server.main",
            "--host",
            config["host"],
            "--port",
            str(config["port"]),
        ]

        # Start process in background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # Create new process group
        )

        # Give server time to start
        time.sleep(2)

        # Check if process started successfully
        if process.poll() is not None:
            raise Exception("Server process failed to start")

        return process

    def _get_server_uptime(self) -> Optional[int]:
        """Get server uptime in seconds."""
        state = self._load_server_state()
        if not state or "started_at" not in state:
            return None

        try:
            started_at = datetime.fromisoformat(state["started_at"])
            uptime = datetime.now(timezone.utc) - started_at
            return int(uptime.total_seconds())
        except (ValueError, TypeError):
            return None

    def _get_server_port(self) -> Optional[int]:
        """Get server port from state."""
        state = self._load_server_state()
        return state.get("port") if state else None

    def _get_server_host(self) -> Optional[str]:
        """Get server host from state."""
        state = self._load_server_state()
        return state.get("host") if state else None

    def _get_active_jobs_count(self) -> int:
        """Get active jobs count from health endpoint."""
        try:
            health = self._get_health_endpoint_response()
            active_jobs = health.get("active_jobs", 0)
            return int(active_jobs) if active_jobs is not None else 0
        except Exception:
            return 0

    def _get_health_endpoint_response(self) -> Dict[str, Any]:
        """Get response from health endpoint."""
        config = self._load_config()
        health_url = f"http://{config['host']}:{config['port']}/health"

        response = requests.get(health_url, timeout=5)
        response.raise_for_status()

        result = response.json()
        return dict(result) if result is not None else {}
