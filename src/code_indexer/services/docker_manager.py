"""Docker container management for Ollama and Qdrant services."""

import subprocess
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
        self._config = self._load_service_config()

    def _detect_project_name(self) -> str:
        """Detect project name from current folder name for qdrant collection naming."""
        try:
            # Use current directory name as project name
            project_name = Path.cwd().name
            return self._sanitize_project_name(project_name)
        except (FileNotFoundError, OSError):
            # Fallback to default project name if current directory is invalid
            return self._sanitize_project_name("default")

    def _sanitize_project_name(self, name: str) -> str:
        """Sanitize project name for use as qdrant collection name."""
        # Handle empty string - fallback to "default"
        if not name:
            return "default"

        # Convert to lowercase first
        sanitized = name.lower()

        # Replace all invalid chars with underscores for qdrant collection naming
        # Collection names must be valid identifiers (letters, numbers, underscores)
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", sanitized)

        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")

        # Ensure it's not empty after sanitization
        if not sanitized:
            sanitized = "default"
        elif len(sanitized) > 50:
            sanitized = sanitized[:50].rstrip("_")

        return sanitized

    def _load_service_config(self) -> Dict[str, Any]:
        """Load service configuration from code-indexer.yaml if it exists."""
        config_paths = [
            Path("code-indexer.yaml"),
            Path(".code-indexer/config.yaml"),
            Path("~/.code-indexer/config.yaml").expanduser(),
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, "r") as f:
                        config = yaml.safe_load(f) or {}
                    return dict(config.get("services", {}))
                except Exception as e:
                    self.console.print(
                        f"Warning: Failed to load config from {config_path}: {e}",
                        style="yellow",
                    )

        # Return default configuration if no config file found
        return {
            "ollama": {
                "external": False,
                "url": "http://localhost:11434",
                "docker": {"port": 11434},
            },
            "qdrant": {
                "external": False,
                "url": "http://localhost:6333",
                "docker": {"port": 6333},
            },
        }

    def _get_service_url(self, service: str) -> str:
        """Get the URL for a service based on configuration."""
        service_config = self._config.get(service, {})

        # If external service is configured, use external URL
        if service_config.get("external", False):
            return str(service_config.get("url", ""))

        # Otherwise, use localhost with configured port
        default_ports = {"ollama": 11434, "qdrant": 6333}
        port = service_config.get("docker", {}).get(
            "port", default_ports.get(service, 0)
        )
        return f"http://localhost:{port}"

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

    def _find_project_root(self) -> Path:
        """Find the project root directory containing Dockerfiles."""
        current = Path.cwd()

        # First check current directory and walk up to find Dockerfiles directly
        for path in [current] + list(current.parents):
            if (path / "Dockerfile.ollama").exists() and (
                path / "Dockerfile.qdrant"
            ).exists():
                return path

        # If not found, look for common project structure indicators that indicate code-indexer root
        for path in [current] + list(current.parents):
            # Check for our specific project structure: src/code_indexer + pyproject.toml
            if (path / "src" / "code_indexer").exists() and (
                path / "pyproject.toml"
            ).exists():
                return path
            # Check for pyproject.toml with code-indexer name
            if (path / "pyproject.toml").exists():
                try:
                    content = (path / "pyproject.toml").read_text()
                    if "code-indexer" in content or "code_indexer" in content:
                        return path
                except Exception:
                    pass

        # Last resort: return current directory
        return current

    def _find_dockerfile(self, dockerfile_name: str) -> Path:
        """Find Dockerfile in package location first, then project root."""
        # Try package location first (for pip/pipx installations)
        package_dockerfile = Path(__file__).parent.parent / "docker" / dockerfile_name
        if package_dockerfile.exists():
            return package_dockerfile

        # Fall back to project root (for development)
        project_root = self._find_project_root()
        project_dockerfile = project_root / dockerfile_name
        return project_dockerfile  # Return this even if it doesn't exist for error messages

    def create_compose_file(self, data_dir: Path = Path(".code-indexer")) -> None:
        """Create docker-compose.yml file."""
        # Find Dockerfiles (package location first, then project root)
        ollama_dockerfile = self._find_dockerfile("Dockerfile.ollama")
        qdrant_dockerfile = self._find_dockerfile("Dockerfile.qdrant")

        compose_config = {
            "version": "3.8",
            "services": {
                "ollama": {
                    "build": {
                        "context": str(ollama_dockerfile.parent),
                        "dockerfile": str(ollama_dockerfile.name),
                    },
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
                    "build": {
                        "context": str(qdrant_dockerfile.parent),
                        "dockerfile": str(qdrant_dockerfile.name),
                    },
                    "container_name": f"code-qdrant-{self.project_name}",
                    "volumes": [f"{data_dir}/qdrant:/qdrant/storage"],
                    "environment": ["QDRANT_ALLOW_ANONYMOUS_READ=true"],
                    "restart": "unless-stopped",
                    "healthcheck": {
                        "test": [
                            "CMD",
                            "curl",
                            "-f",
                            "http://localhost:6333/",
                        ],
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
            compose_config = self.generate_compose_config()
            with open(self.compose_file, "w") as f:
                yaml.dump(compose_config, f, default_flow_style=False)

        compose_cmd = self.get_compose_command()

        try:
            cmd = compose_cmd + ["-p", self.project_name, "up", "-d"]
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
                    compose_cmd + ["-p", self.project_name, "down"],
                    capture_output=True,
                    text=True,
                    timeout=60,
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
                compose_cmd + ["-p", self.project_name, "ps", "--format", "json"],
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
                        # Handle both "Names" (array) and "Name"/"name" (string) fields
                        names = service.get("Names", [])
                        if names and isinstance(names, list) and len(names) > 0:
                            name = names[0]  # Take first name from array
                        else:
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

    def ollama_request(
        self, endpoint: str, method: str = "GET", data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a direct HTTP request to Ollama service."""
        import requests  # type: ignore
        import json

        base_url = self._get_service_url("ollama")
        url = f"{base_url}{endpoint}"

        try:
            if method == "GET":
                response = requests.get(url, timeout=30)
            elif method == "POST":
                headers = {"Content-Type": "application/json"}
                response = requests.post(url, headers=headers, json=data, timeout=30)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}

            if response.status_code == 200:
                try:
                    return {
                        "success": True,
                        "data": response.json() if response.text else None,
                    }
                except json.JSONDecodeError:
                    return {"success": True, "data": response.text}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                }

        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}

    def qdrant_request(
        self, endpoint: str, method: str = "GET", data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a direct HTTP request to Qdrant service."""
        import requests  # type: ignore
        import json

        base_url = self._get_service_url("qdrant")
        url = f"{base_url}{endpoint}"

        try:
            headers = {"Content-Type": "application/json"}

            if method == "GET":
                response = requests.get(url, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=30)
            elif method == "DELETE":
                response = requests.delete(url, timeout=30)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}

            if response.status_code in [200, 201, 204]:
                try:
                    return {
                        "success": True,
                        "data": response.json() if response.text else None,
                    }
                except json.JSONDecodeError:
                    return {"success": True, "data": response.text}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                }

        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}

    def wait_for_services(self, timeout: int = 120, retry_interval: int = 2) -> bool:
        """Wait for services to be healthy using robust retry logic with exponential backoff."""
        import requests  # type: ignore

        self.console.print(f"Waiting for services to be ready (timeout: {timeout}s)...")

        import time

        start_time = time.time()
        attempt = 1
        last_status = {"ollama": "unknown", "qdrant": "unknown"}

        while time.time() - start_time < timeout:
            ollama_healthy = False
            qdrant_healthy = False
            current_status = {}

            # Check ollama service with detailed error reporting
            try:
                ollama_url = self._get_service_url("ollama")
                response = requests.get(f"{ollama_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    ollama_healthy = True
                    current_status["ollama"] = "ready"
                else:
                    current_status["ollama"] = f"http_{response.status_code}"
            except requests.exceptions.ConnectionError:
                current_status["ollama"] = "connection_refused"
            except requests.exceptions.Timeout:
                current_status["ollama"] = "timeout"
            except Exception as e:
                current_status["ollama"] = f"error_{type(e).__name__}"

            # Check qdrant service with detailed error reporting
            try:
                qdrant_url = self._get_service_url("qdrant")
                response = requests.get(f"{qdrant_url}/", timeout=5)
                if response.status_code == 200:
                    qdrant_healthy = True
                    current_status["qdrant"] = "ready"
                else:
                    current_status["qdrant"] = f"http_{response.status_code}"
            except requests.exceptions.ConnectionError:
                current_status["qdrant"] = "connection_refused"
            except requests.exceptions.Timeout:
                current_status["qdrant"] = "timeout"
            except Exception as e:
                current_status["qdrant"] = f"error_{type(e).__name__}"

            # Log status changes for debugging
            if current_status != last_status:
                elapsed = int(time.time() - start_time)
                self.console.print(
                    f"[{elapsed:3d}s] Attempt {attempt:2d}: ollama={current_status['ollama']}, qdrant={current_status['qdrant']}",
                    style="dim",
                )
                last_status = current_status.copy()

            if ollama_healthy and qdrant_healthy:
                elapsed = int(time.time() - start_time)
                self.console.print(
                    f"✅ All services ready after {elapsed}s ({attempt} attempts)",
                    style="green",
                )
                return True

            # Exponential backoff with max 10 seconds
            sleep_time = min(retry_interval * (1.5 ** (attempt // 5)), 10)
            time.sleep(sleep_time)
            attempt += 1

        elapsed = int(time.time() - start_time)
        self.console.print(
            f"❌ Services did not become ready within {elapsed}s timeout (after {attempt} attempts)",
            style="red",
        )
        self.console.print(
            f"Final status: ollama={current_status.get('ollama', 'unknown')}, qdrant={current_status.get('qdrant', 'unknown')}",
            style="red",
        )

        # Show container logs for debugging
        for service in ["ollama", "qdrant"]:
            if current_status.get(service) != "ready":
                logs = self.get_container_logs(service, lines=10)
                if logs.strip():
                    self.console.print(
                        f"\n{service} container logs (last 10 lines):", style="red"
                    )
                    self.console.print(logs, style="dim")

        return False

    def get_container_logs(self, service: str, lines: int = 50) -> str:
        """Get recent container logs for debugging startup issues."""
        import subprocess

        container_name = self.get_container_name(service)

        # Detect container engine (podman or docker)
        container_engine = (
            "podman"
            if subprocess.run(["which", "podman"], capture_output=True).returncode == 0
            else "docker"
        )

        try:
            result = subprocess.run(
                [container_engine, "logs", "--tail", str(lines), container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return result.stdout
            else:
                return f"Failed to get logs: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "Log retrieval timed out"
        except Exception as e:
            return f"Error getting logs: {e}"

    def get_container_name(self, service: str) -> str:
        """Get the global container name for a given service."""
        return f"code-indexer-{service}"

    def get_network_name(self) -> str:
        """Get the global network name."""
        return "code-indexer-global"

    def stop(self) -> bool:
        """Stop all services."""
        return self.stop_services()

    def start(self) -> bool:
        """Start all services."""
        return self.start_services()

    def status(self) -> Dict[str, Any]:
        """Get status of services using direct HTTP calls."""
        import requests  # type: ignore

        # Check ollama service availability
        ollama_running = False
        try:
            ollama_url = self._get_service_url("ollama")
            response = requests.get(f"{ollama_url}/api/tags", timeout=5)
            ollama_running = response.status_code == 200
        except (requests.exceptions.RequestException, Exception):
            ollama_running = False

        # Check qdrant service availability
        qdrant_running = False
        try:
            qdrant_url = self._get_service_url("qdrant")
            response = requests.get(f"{qdrant_url}/", timeout=5)
            qdrant_running = response.status_code == 200
        except (requests.exceptions.RequestException, Exception):
            qdrant_running = False

        # Return status in format expected by tests (using global container names)
        return {
            "ollama": {
                "running": ollama_running,
                "name": "code-indexer-ollama",  # Global container name
            },
            "qdrant": {
                "running": qdrant_running,
                "name": "code-indexer-qdrant",  # Global container name
            },
        }

    def clean(self) -> bool:
        """Clean up all resources without removing data."""
        return self.cleanup(remove_data=False)

    def cleanup(self, remove_data: bool = False) -> bool:
        """Clean up Docker resources."""
        compose_cmd = self.get_compose_command()

        try:
            # Stop and remove containers
            result = subprocess.run(
                (
                    compose_cmd + ["-p", self.project_name, "down", "-v"]
                    if remove_data
                    else compose_cmd + ["-p", self.project_name, "down"]
                ),
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

    def generate_compose_config(
        self, data_dir: Path = Path(".code-indexer")
    ) -> Dict[str, Any]:
        """Generate Docker Compose configuration for single global instances."""
        # Single global network for all services
        network_name = "code-indexer-global"

        # Find Dockerfiles (package location first, then project root)
        ollama_dockerfile = self._find_dockerfile("Dockerfile.ollama")
        qdrant_dockerfile = self._find_dockerfile("Dockerfile.qdrant")

        # Get global configuration directory
        global_config_dir = Path.home() / ".code-indexer" / "global"

        # Current working directory for project-specific qdrant storage
        # current_project_dir = Path.cwd()  # Currently unused but may be needed for future features

        compose_config = {
            "version": "3.8",
            "services": {
                "ollama": {
                    "build": {
                        "context": str(ollama_dockerfile.parent),
                        "dockerfile": str(ollama_dockerfile.name),
                    },
                    "container_name": "code-indexer-ollama",
                    "ports": ["11434:11434"],  # External port mapping
                    "volumes": [f"{global_config_dir}/ollama:/root/.ollama"],
                    "restart": "unless-stopped",
                    "networks": [network_name],
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
                    "build": {
                        "context": str(qdrant_dockerfile.parent),
                        "dockerfile": str(qdrant_dockerfile.name),
                    },
                    "container_name": "code-indexer-qdrant",
                    "ports": ["6333:6333"],  # External port mapping
                    "volumes": [
                        # Mount global qdrant storage that contains all project databases
                        f"{global_config_dir}/qdrant:/qdrant/storage"
                    ],
                    "environment": [
                        "QDRANT_ALLOW_ANONYMOUS_READ=true",
                        # Enable collection management via API
                        "QDRANT_CLUSTER__ENABLED=false",
                    ],
                    "restart": "unless-stopped",
                    "networks": [network_name],
                    "healthcheck": {
                        "test": ["CMD", "curl", "-f", "http://localhost:6333/"],
                        "interval": "30s",
                        "timeout": "10s",
                        "retries": 3,
                        "start_period": "40s",
                    },
                },
            },
            "networks": {network_name: {"name": network_name}},
        }

        return compose_config
