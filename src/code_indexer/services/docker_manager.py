"""Docker container management for Ollama and Qdrant services."""

import subprocess
import time
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml  # type: ignore

from rich.console import Console


class DockerManager:
    """Manages Docker containers for Code Indexer services."""

    def __init__(
        self, console: Optional[Console] = None, project_name: Optional[str] = None
    ):
        self.console = console or Console()
        self.project_name = project_name or self._detect_project_name()
        self.compose_file = Path("docker-compose.yml")

    def _detect_project_name(self) -> str:
        """Detect project name from current folder name."""
        # Use current directory name as project name
        project_name = Path.cwd().name
        return self._sanitize_project_name(project_name)

    def _sanitize_project_name(self, name: str) -> str:
        """Sanitize project name for use as Docker container name."""
        # Replace invalid characters (including underscores, dots, spaces, special chars) with hyphens
        sanitized = re.sub(r"[^a-zA-Z0-9-]", "-", name)
        # Remove consecutive hyphens
        sanitized = re.sub(r"-+", "-", sanitized)
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip("-")
        # Ensure it's not empty and has a reasonable length
        if not sanitized:
            sanitized = "default"
        elif len(sanitized) > 50:
            sanitized = sanitized[:50].rstrip("-")
        return sanitized.lower()

    def is_docker_available(self) -> bool:
        """Check if Docker or Podman is available."""
        # Try Docker first
        try:
            result = subprocess.run(
                ["docker", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try Podman as fallback
        try:
            result = subprocess.run(
                ["podman", "--version"], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def is_compose_available(self) -> bool:
        """Check if Docker Compose or Podman Compose is available."""
        # Try docker compose (new syntax)
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try docker-compose (old syntax)
        try:
            result = subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try podman-compose
        try:
            result = subprocess.run(
                ["podman-compose", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_compose_command(self) -> List[str]:
        """Get the appropriate docker compose command."""
        # Prefer docker compose (new syntax)
        try:
            result = subprocess.run(
                ["docker", "compose", "version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return ["docker", "compose"]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try docker-compose (old syntax)
        try:
            result = subprocess.run(
                ["docker-compose", "--version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return ["docker-compose"]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fall back to podman-compose
        return ["podman-compose"]

    def create_compose_file(self, data_dir: Path = Path(".code-indexer")) -> None:
        """Create docker-compose.yml file."""
        compose_config = {
            "version": "3.8",
            "services": {
                "ollama": {
                    "build": {"context": ".", "dockerfile": "Dockerfile.ollama"},
                    "container_name": f"code-ollama-{self.project_name}",
                    "volumes": [f"{data_dir}/ollama:/root/.ollama"],
                    "restart": "unless-stopped",
                    "healthcheck": {
                        "test": [
                            "CMD",
                            "curl",
                            "-f",
                            "http://localhost:11434/api/tags",
                        ],
                        "interval": "30s",
                        "timeout": "10s",
                        "retries": 3,
                        "start_period": "30s",
                    },
                },
                "qdrant": {
                    "build": {"context": ".", "dockerfile": "Dockerfile.qdrant"},
                    "container_name": f"code-qdrant-{self.project_name}",
                    "volumes": [f"{data_dir}/qdrant:/qdrant/storage"],
                    "environment": ["QDRANT_ALLOW_ANONYMOUS_READ=true"],
                    "restart": "unless-stopped",
                    "healthcheck": {
                        "test": ["CMD", "curl", "-f", "http://localhost:6333/"],
                        "interval": "30s",
                        "timeout": "10s",
                        "retries": 3,
                        "start_period": "40s",
                    },
                },
            },
            "networks": {"default": {"name": f"code-indexer-{self.project_name}"}},
        }

        # Ensure data directory exists
        data_dir.mkdir(parents=True, exist_ok=True)

        with open(self.compose_file, "w") as f:
            yaml.dump(compose_config, f, default_flow_style=False)

    def start_services(self, recreate: bool = False) -> bool:
        """Start Docker services."""
        if not self.compose_file.exists():
            self.create_compose_file()

        compose_cmd = self.get_compose_command()

        try:
            cmd = compose_cmd + ["up", "-d"]
            if recreate:
                cmd.append("--force-recreate")

            with self.console.status("Starting services..."):
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120
                )

            if result.returncode == 0:
                self.console.print("✅ Services started successfully", style="green")
                return True
            else:
                self.console.print(
                    f"❌ Failed to start services: {result.stderr}", style="red"
                )
                return False

        except subprocess.TimeoutExpired:
            self.console.print("❌ Timeout starting services", style="red")
            return False
        except Exception as e:
            self.console.print(f"❌ Error starting services: {e}", style="red")
            return False

    def stop_services(self) -> bool:
        """Stop Docker services."""
        if not self.compose_file.exists():
            return True

        compose_cmd = self.get_compose_command()

        try:
            with self.console.status("Stopping services..."):
                result = subprocess.run(
                    compose_cmd + ["down"], capture_output=True, text=True, timeout=60
                )

            if result.returncode == 0:
                self.console.print("✅ Services stopped successfully", style="green")
                return True
            else:
                self.console.print(
                    f"❌ Failed to stop services: {result.stderr}", style="red"
                )
                return False

        except subprocess.TimeoutExpired:
            self.console.print("❌ Timeout stopping services", style="red")
            return False
        except Exception as e:
            self.console.print(f"❌ Error stopping services: {e}", style="red")
            return False

    def restart_services(self) -> bool:
        """Restart Docker services."""
        self.console.print("Restarting services...")
        return self.stop_services() and self.start_services()

    def get_service_status(self) -> Dict[str, Any]:
        """Get status of all services."""
        if not self.compose_file.exists():
            return {"status": "not_configured", "services": {}}

        compose_cmd = self.get_compose_command()

        try:
            result = subprocess.run(
                compose_cmd + ["ps", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Parse JSON output (varies by compose version)
                import json

                try:
                    services = json.loads(result.stdout)
                    if not isinstance(services, list):
                        services = [services]

                    status: Dict[str, Any] = {
                        "status": "running" if services else "stopped",
                        "services": {},
                    }

                    for service in services:
                        name = service.get("Name", service.get("name", "unknown"))
                        state = service.get("State", service.get("state", "unknown"))
                        status["services"][name] = {
                            "state": state,
                            "health": service.get("Health", "unknown"),
                        }

                    return status
                except json.JSONDecodeError:
                    # Fallback for older compose versions
                    return {"status": "unknown", "services": {}}
            else:
                return {"status": "error", "services": {}}

        except Exception:
            return {"status": "unavailable", "services": {}}

    def execute_in_container(
        self, container_name: str, command: List[str]
    ) -> Dict[str, Any]:
        """Execute a command inside a container."""
        compose_cmd = self.get_compose_command()

        # Use docker/podman exec directly for better control
        if "docker" in compose_cmd[0]:
            exec_cmd = ["docker", "exec", container_name] + command
        else:
            exec_cmd = ["podman", "exec", container_name] + command

        try:
            result = subprocess.run(
                exec_cmd, capture_output=True, text=True, timeout=30
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Command timed out",
                "returncode": -1,
            }
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}

    def ollama_request(
        self, endpoint: str, method: str = "GET", data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a request to Ollama via container execution."""
        container_name = f"code-ollama-{self.project_name}"

        # Build curl command
        curl_cmd = ["curl", "-s", "-f"]

        if method == "POST":
            curl_cmd.extend(["-X", "POST"])
            if data:
                import json

                curl_cmd.extend(["-H", "Content-Type: application/json"])
                curl_cmd.extend(["-d", json.dumps(data)])

        url = f"http://localhost:11434{endpoint}"
        curl_cmd.append(url)

        result = self.execute_in_container(container_name, curl_cmd)

        if result["success"]:
            try:
                import json

                return {
                    "success": True,
                    "data": json.loads(result["stdout"]) if result["stdout"] else None,
                }
            except json.JSONDecodeError:
                return {"success": True, "data": result["stdout"]}
        else:
            return {"success": False, "error": result["stderr"] or "Request failed"}

    def qdrant_request(
        self, endpoint: str, method: str = "GET", data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a request to Qdrant via container execution."""
        container_name = f"code-qdrant-{self.project_name}"

        # Build curl command
        curl_cmd = ["curl", "-s", "-f"]

        if method == "POST":
            curl_cmd.extend(["-X", "POST"])
            if data:
                import json

                curl_cmd.extend(["-H", "Content-Type: application/json"])
                curl_cmd.extend(["-d", json.dumps(data)])
        elif method == "PUT":
            curl_cmd.extend(["-X", "PUT"])
            if data:
                import json

                curl_cmd.extend(["-H", "Content-Type: application/json"])
                curl_cmd.extend(["-d", json.dumps(data)])
        elif method == "DELETE":
            curl_cmd.extend(["-X", "DELETE"])

        url = f"http://localhost:6333{endpoint}"
        curl_cmd.append(url)

        result = self.execute_in_container(container_name, curl_cmd)

        if result["success"]:
            try:
                import json

                return {
                    "success": True,
                    "data": json.loads(result["stdout"]) if result["stdout"] else None,
                }
            except json.JSONDecodeError:
                return {"success": True, "data": result["stdout"]}
        else:
            return {"success": False, "error": result["stderr"] or "Request failed"}

    def wait_for_services(self, timeout: int = 60) -> bool:
        """Wait for services to be healthy."""
        self.console.print("Waiting for services to be ready...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_service_status()

            if status["status"] == "running":
                all_healthy = True
                for service_name, service_info in status["services"].items():
                    if service_info["state"] != "running":
                        all_healthy = False
                        break

                if all_healthy:
                    self.console.print("✅ All services are ready", style="green")
                    return True

            time.sleep(2)

        self.console.print("❌ Services did not become ready in time", style="red")
        return False

    def get_container_name(self, service: str) -> str:
        """Get the container name for a given service."""
        return f"code-{service}-{self.project_name}"

    def get_network_name(self) -> str:
        """Get the network name for this project."""
        return f"code-indexer-{self.project_name}"

    def stop(self) -> bool:
        """Stop all services."""
        return self.stop_services()

    def start(self) -> bool:
        """Start all services."""
        return self.start_services()

    def status(self) -> Dict[str, Any]:
        """Get status of all services in a format expected by tests."""
        service_status = self.get_service_status()

        # Transform to the format expected by tests
        result = {}
        if service_status.get("services"):
            for service_name, service_info in service_status["services"].items():
                # Extract service type from container name (e.g., "code-ollama-project" -> "ollama")
                service_type = None
                if "ollama" in service_name:
                    service_type = "ollama"
                elif "qdrant" in service_name:
                    service_type = "qdrant"

                if service_type:
                    result[service_type] = {
                        "running": service_info["state"] == "running",
                        "name": service_name,
                    }

        return result

    def clean(self) -> bool:
        """Clean up all resources without removing data."""
        return self.cleanup(remove_data=False)

    def cleanup(self, remove_data: bool = False) -> bool:
        """Clean up Docker resources."""
        compose_cmd = self.get_compose_command()

        try:
            # Stop and remove containers
            result = subprocess.run(
                compose_cmd + ["down", "-v"] if remove_data else compose_cmd + ["down"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            success = result.returncode == 0

            if remove_data:
                # Remove data directories
                data_dir = Path(".code-indexer")
                if data_dir.exists():
                    import shutil

                    shutil.rmtree(data_dir)

                # Remove compose file
                if self.compose_file.exists():
                    self.compose_file.unlink()

            if success:
                self.console.print("✅ Cleanup completed", style="green")
            else:
                self.console.print(f"❌ Cleanup failed: {result.stderr}", style="red")

            return success

        except Exception as e:
            self.console.print(f"❌ Error during cleanup: {e}", style="red")
            return False
