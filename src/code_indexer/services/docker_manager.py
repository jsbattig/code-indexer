"""Docker container management for Ollama and Qdrant services."""

import os
import subprocess
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml  # type: ignore

from rich.console import Console
from .health_checker import HealthChecker


class DockerManager:
    """Manages Docker containers for Code Indexer services."""

    def __init__(
        self,
        console: Optional[Console] = None,
        project_name: Optional[str] = None,
        force_docker: bool = False,
        main_config: Optional[Dict[str, Any]] = None,
    ):
        self.console = console or Console()
        self.force_docker = force_docker
        self.project_name = project_name or self._detect_project_name()
        self.compose_file = self._get_global_compose_file_path()
        self._config = self._load_service_config()
        self.main_config = main_config
        self.health_checker = HealthChecker(config_manager=main_config)

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

    def _get_global_compose_file_path(self) -> Path:
        """Get the path to the global compose file stored in the home directory."""
        return get_global_compose_file_path(self.force_docker)

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

    def _extract_port_from_url(self, url: str, default_port: int) -> int:
        """Extract port number from a URL string."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.port or default_port
        except Exception:
            return default_port

    def _get_service_port(self, service: str, default_port: int) -> int:
        """Get the port for a service from main config or service config."""
        # First try to extract from main configuration host URL (prioritize main config)
        if self.main_config:
            service_config = self.main_config.get(service, {})
            if "host" in service_config:
                return self._extract_port_from_url(service_config["host"], default_port)

        # Fall back to service-specific configuration (legacy)
        service_port = self._config.get(service, {}).get("docker", {}).get("port", None)
        if service_port is not None:
            return int(service_port)

        # Fall back to default
        return default_port

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
        """Check if Podman or Docker is available, prioritizing Podman unless force_docker is True."""

        if self.force_docker:
            # Force Docker mode - only check Docker
            try:
                result = subprocess.run(
                    ["docker", "--version"], capture_output=True, text=True, timeout=5
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False

        # Normal Podman-first mode
        # Try Podman first (Podman shop priority)
        try:
            result = subprocess.run(
                ["podman", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try Docker as fallback
        try:
            result = subprocess.run(
                ["docker", "--version"], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def is_compose_available(self) -> bool:
        """Check if Podman Compose or Docker Compose is available, prioritizing Podman unless force_docker is True."""

        if self.force_docker:
            # Force Docker mode - only check Docker Compose
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
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False

        # Normal Podman-first mode
        # Try podman-compose first (Podman shop priority)
        try:
            result = subprocess.run(
                ["podman-compose", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

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
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_compose_command(self) -> List[str]:
        """Get the appropriate compose command, prioritizing Podman unless force_docker is True."""

        if self.force_docker:
            # Force Docker mode - try Docker options only
            # Try docker compose (new syntax)
            try:
                result = subprocess.run(
                    ["docker", "compose", "version"], capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    return ["docker", "compose"]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            # Fall back to docker-compose (old syntax)
            try:
                result = subprocess.run(
                    ["docker-compose", "--version"], capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    return ["docker-compose"]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            # Force Docker was requested but not available
            raise RuntimeError(
                "Docker was forced but docker/docker-compose is not available"
            )

        # Normal Podman-first mode
        # Prefer podman-compose (Podman shop priority)
        try:
            result = subprocess.run(
                ["podman-compose", "--version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return ["podman-compose"]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try docker compose (new syntax)
        try:
            result = subprocess.run(
                ["docker", "compose", "version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return ["docker", "compose"]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fall back to docker-compose (old syntax)
        try:
            result = subprocess.run(
                ["docker-compose", "--version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return ["docker-compose"]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Last resort fallback
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
        """Find Dockerfile in package location."""
        package_dockerfile = Path(__file__).parent.parent / "docker" / dockerfile_name
        if not package_dockerfile.exists():
            raise FileNotFoundError(
                f"Required Dockerfile not found: {package_dockerfile}"
            )
        return package_dockerfile

    def start_services(self, recreate: bool = False) -> bool:
        """Start Docker services with real-time progress feedback."""
        # Always regenerate compose file if recreate=True, main_config is available, or if it doesn't exist
        if recreate or self.main_config is not None or not self.compose_file.exists():
            compose_config = self.generate_compose_config()
            with open(self.compose_file, "w") as f:
                yaml.dump(compose_config, f, default_flow_style=False)

        compose_cmd = self.get_compose_command()

        # Check if images exist to provide better user feedback
        containers_exist = self._check_containers_exist()
        if not containers_exist:
            self.console.print(
                "📥 First-time setup detected. This may take several minutes to download Docker images (~2GB)..."
            )
            self.console.print(
                "💡 Progress will be shown below. Please be patient during image downloads."
            )

        try:
            cmd = compose_cmd + [
                "-f",
                str(self.compose_file),
                "-p",
                self.project_name,
                "up",
                "-d",
            ]
            if recreate:
                cmd.append("--force-recreate")

            self.console.print(f"🚀 Running: {' '.join(cmd)}")

            # Use Popen to show real-time output
            import time

            start_time = time.time()

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Show real-time output with progress indicators
            output_lines = []
            last_progress_time = time.time()

            self.console.print("📊 Docker Compose Output:")
            self.console.print("─" * 60)

            while True:
                if process.stdout is None:
                    break
                line = process.stdout.readline()
                if line:
                    # Clean up the line and display it
                    clean_line = line.strip()
                    if clean_line:
                        # Show progress for long-running operations
                        if any(
                            keyword in clean_line.lower()
                            for keyword in [
                                "pulling",
                                "downloading",
                                "extracting",
                                "building",
                            ]
                        ):
                            self.console.print(f"⏳ {clean_line}", style="yellow")
                        elif (
                            "done" in clean_line.lower()
                            or "complete" in clean_line.lower()
                        ):
                            self.console.print(f"✅ {clean_line}", style="green")
                        elif (
                            "error" in clean_line.lower()
                            or "failed" in clean_line.lower()
                        ):
                            self.console.print(f"❌ {clean_line}", style="red")
                        else:
                            self.console.print(f"📋 {clean_line}")
                        output_lines.append(clean_line)
                    last_progress_time = time.time()
                elif process.poll() is not None:
                    break
                else:
                    # Show periodic time updates for long operations
                    current_time = time.time()
                    if current_time - last_progress_time > 30:  # Every 30 seconds
                        elapsed = int(current_time - start_time)
                        self.console.print(
                            f"⏱️  Still working... ({elapsed}s elapsed)", style="blue"
                        )
                        last_progress_time = current_time
                    time.sleep(0.1)

            # Wait for process to complete and get return code
            return_code = process.wait(timeout=600)  # 10 minute timeout

            self.console.print("─" * 60)
            elapsed = int(time.time() - start_time)

            if return_code == 0:
                self.console.print(
                    f"✅ Services started successfully in {elapsed}s", style="green"
                )
                return True
            else:
                self.console.print(
                    f"❌ Failed to start services (exit code: {return_code})",
                    style="red",
                )
                if output_lines:
                    self.console.print("Last few lines of output:", style="yellow")
                    for line in output_lines[-5:]:
                        self.console.print(f"  {line}", style="dim")
                return False

        except subprocess.TimeoutExpired:
            self.console.print("❌ Timeout starting services (10 minutes)", style="red")
            try:
                process.terminate()
                process.wait(timeout=10)
            except Exception:
                process.kill()
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
                    compose_cmd
                    + ["-f", str(self.compose_file), "-p", self.project_name, "down"],
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
                compose_cmd
                + [
                    "-f",
                    str(self.compose_file),
                    "-p",
                    self.project_name,
                    "ps",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Parse JSON output (varies by compose version)
                import json

                try:
                    # Handle both single JSON object and multiple JSON objects (one per line)
                    stdout = result.stdout.strip()
                    if not stdout:
                        services = []
                    elif stdout.startswith("["):
                        # JSON array format
                        services = json.loads(stdout)
                    else:
                        # Multiple JSON objects, one per line (Docker compose format)
                        services = []
                        for line in stdout.split("\n"):
                            if line.strip():
                                services.append(json.loads(line.strip()))

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

    def get_adaptive_timeout(self, default_timeout: int = 120) -> int:
        """Get adaptive timeout based on whether containers and models exist."""
        # Check if containers exist
        containers_exist = self._check_containers_exist()

        # Check if Ollama model exists
        model_exists = self._check_ollama_model_exists()

        # If both containers and model exist, use shorter timeout
        if containers_exist and model_exists:
            adaptive_timeout = 10  # Fast startup expected
            self.console.print(
                "🚀 Containers and model exist, using fast timeout (10s)"
            )
            return adaptive_timeout
        elif containers_exist:
            adaptive_timeout = 30  # Medium startup time
            self.console.print(
                "📦 Containers exist but model may need download, using medium timeout (30s)"
            )
            return adaptive_timeout
        else:
            # First time setup or containers missing
            self.console.print(
                f"⏰ Full setup required, using default timeout ({default_timeout}s)"
            )
            return default_timeout

    def _check_containers_exist(self) -> bool:
        """Check if both Ollama and Qdrant containers exist."""
        import subprocess

        container_engine = "docker" if self.force_docker else "podman"
        container_names = [
            self.get_container_name("ollama"),
            self.get_container_name("qdrant"),
        ]

        try:
            for container_name in container_names:
                result = subprocess.run(
                    [
                        container_engine,
                        "ps",
                        "-a",
                        "--filter",
                        f"name={container_name}",
                        "--format",
                        "{{.Names}}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0 or container_name not in result.stdout:
                    return False
            return True
        except Exception:
            return False

    def _check_ollama_model_exists(self) -> bool:
        """Check if Ollama model files exist in the data directory."""
        global_dir = Path.home() / ".code-indexer-data"

        ollama_models_dir = global_dir / "ollama" / "models"

        # Check if models directory exists and has content
        if ollama_models_dir.exists():
            # Check for any model files (blobs directory indicates downloaded models)
            blobs_dir = ollama_models_dir / "blobs"
            if blobs_dir.exists() and any(blobs_dir.iterdir()):
                return True

        return False

    def wait_for_services(self, timeout: int = 120, retry_interval: int = 2) -> bool:
        """Wait for services to be healthy using retry logic with exponential backoff."""
        import requests  # type: ignore

        # Use adaptive timeout if default timeout is requested
        if timeout == 120:  # Default timeout
            timeout = self.get_adaptive_timeout(timeout)

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

    def cleanup(
        self,
        remove_data: bool = False,
        force: bool = False,
        verbose: bool = False,
        validate: bool = False,
    ) -> bool:
        """Clean up Docker resources with enhanced options for reliability."""
        compose_cmd = self.get_compose_command()
        cleanup_success = True

        try:
            if verbose:
                self.console.print("🔍 Starting enhanced cleanup process...")

            # Step 2: Orchestrate container shutdown
            if verbose:
                self.console.print("🛑 Orchestrating container shutdown...")

            # For remove_data, use orchestrated shutdown with data cleaner
            if remove_data:
                if verbose:
                    self.console.print("🔄 Orchestrated shutdown for data removal...")

                # First, stop main services (ollama and qdrant) but keep data cleaner running
                self.stop_main_services()

                # Use data cleaner to clean named volume contents
                if verbose:
                    self.console.print("🧹 Using data cleaner for root-owned files...")
                cleanup_paths = ["/data/ollama/*", "/data/qdrant/*"]
                self.clean_with_data_cleaner(cleanup_paths)

                # Now stop the data cleaner too
                if verbose:
                    self.console.print("🛑 Stopping data cleaner...")
                self.stop_data_cleaner()
            else:
                # Regular stop for non-data-removal cleanup
                stop_result = subprocess.run(
                    compose_cmd
                    + ["-f", str(self.compose_file), "-p", self.project_name, "stop"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if stop_result.returncode != 0 and force:
                    if verbose:
                        self.console.print(
                            "⚠️  Graceful stop failed, force killing containers..."
                        )
                    # Force kill containers if graceful stop failed
                    self._force_cleanup_containers(verbose)

            # Step 3: Remove containers and volumes
            if verbose:
                self.console.print("🗑️  Removing containers and volumes...")

            down_cmd = compose_cmd + [
                "-f",
                str(self.compose_file),
                "-p",
                self.project_name,
                "down",
            ]
            if remove_data:
                down_cmd.append("-v")
            if force:
                down_cmd.extend(["--remove-orphans", "--timeout", "10"])

            result = subprocess.run(
                down_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                # If compose file doesn't exist, that's not a critical failure
                if "missing files" in result.stderr or "No such file" in result.stderr:
                    if verbose:
                        self.console.print(
                            "⚠️  Compose file already missing, skipping container down",
                            style="yellow",
                        )
                else:
                    cleanup_success = False
                    if verbose:
                        self.console.print(
                            f"❌ Container removal failed: {result.stderr}", style="red"
                        )

            # Step 4: Handle data removal ONLY when explicitly requested
            if remove_data:
                if verbose:
                    self.console.print("🗂️  Removing data volumes and directories...")

                # Clean up named volumes (new approach)
                cleanup_success &= self._cleanup_named_volumes(verbose)

                # Still clean up any old bind mount directories for backward compatibility
                cleanup_success &= self._cleanup_data_directories(verbose, force)

            # Step 5: Clean up compose file and networks
            if verbose:
                self.console.print("📄 Cleaning up compose files and networks...")

            if self.compose_file.exists():
                try:
                    self.compose_file.unlink()
                    if verbose:
                        self.console.print(
                            f"✅ Removed compose file: {self.compose_file}"
                        )
                except Exception as e:
                    cleanup_success = False
                    if verbose:
                        self.console.print(
                            f"❌ Failed to remove compose file: {e}", style="red"
                        )

            # Step 6: Validation if requested
            if validate:
                if verbose:
                    self.console.print("🔍 Validating cleanup...")

                # Wait for containers to stop and ports to be released
                container_engine = (
                    "docker"
                    if self.force_docker
                    else (
                        "podman"
                        if subprocess.run(
                            ["which", "podman"], capture_output=True
                        ).returncode
                        == 0
                        else "docker"
                    )
                )

                container_names = [
                    f"{self.project_name}-ollama",
                    f"{self.project_name}-qdrant",
                    f"{self.project_name}-data-cleaner",
                ]
                required_ports = [6333, 11434, 8091]  # Qdrant, Ollama, DataCleaner

                # Wait for complete cleanup with intelligent timeout
                validation_success = self.health_checker.wait_for_cleanup_complete(
                    container_names=container_names,
                    ports=required_ports,
                    container_engine=container_engine,
                    timeout=None,  # Use engine-optimized timeout
                )

                if not validation_success and verbose:
                    self.console.print(
                        "⚠️  Cleanup validation timed out, continuing anyway...",
                        style="yellow",
                    )

                # Additional validation check for legacy compatibility
                legacy_validation_success = self._validate_cleanup(verbose)
                validation_success = validation_success and legacy_validation_success

                cleanup_success &= validation_success

            # Final result
            if cleanup_success:
                self.console.print("✅ Cleanup completed successfully", style="green")
            else:
                self.console.print(
                    "❌ Cleanup completed with some failures", style="red"
                )

            return cleanup_success

        except Exception as e:
            self.console.print(f"❌ Error during cleanup: {e}", style="red")
            return False

    def _force_cleanup_containers(self, verbose: bool = False) -> bool:
        """Force cleanup containers that won't stop gracefully."""
        import subprocess

        success = True
        container_engine = "docker" if self.force_docker else "podman"

        # Get container names for this project
        container_names = [
            self.get_container_name("ollama"),
            self.get_container_name("qdrant"),
        ]

        for container_name in container_names:
            try:
                # Force kill container
                kill_result = subprocess.run(
                    [container_engine, "kill", container_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                # Force remove container
                rm_result = subprocess.run(
                    [container_engine, "rm", "-f", container_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if verbose:
                    if kill_result.returncode == 0 or rm_result.returncode == 0:
                        self.console.print(
                            f"✅ Force removed container: {container_name}"
                        )
                    else:
                        self.console.print(
                            f"⚠️  Container {container_name} may not have existed"
                        )

            except Exception as e:
                success = False
                if verbose:
                    self.console.print(
                        f"❌ Failed to force remove {container_name}: {e}", style="red"
                    )

        return success

    def _cleanup_data_directories(
        self, verbose: bool = False, force: bool = False
    ) -> bool:
        """Clean up data directories with enhanced permission handling."""
        import shutil

        success = True

        # Clean up local project data directory
        data_dir = Path(".code-indexer")
        if data_dir.exists():
            try:
                if force:
                    # Fix permissions before removal
                    self._fix_directory_permissions(data_dir, verbose)

                shutil.rmtree(data_dir, ignore_errors=not force)
                if verbose:
                    self.console.print(f"✅ Removed local data directory: {data_dir}")
            except Exception as e:
                success = False
                if verbose:
                    self.console.print(
                        f"❌ Failed to remove local data directory: {e}", style="red"
                    )

        # Clean up global directories
        success &= self._cleanup_global_directories(verbose, force)

        return success

    def _fix_directory_permissions(self, directory: Path, verbose: bool = False):
        """Fix permissions on directory and all contents to allow removal.

        This method has been enhanced to use the data cleaner for root-owned files
        that cannot be removed with standard permission fixes.
        """
        import stat

        try:
            # First try standard permission fixing for files we can access
            for root, dirs, files in os.walk(directory):
                # Fix directory permissions
                for d in dirs:
                    dir_path = os.path.join(root, d)
                    try:
                        os.chmod(dir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                    except Exception:
                        pass

                # Fix file permissions
                for f in files:
                    file_path = os.path.join(root, f)
                    try:
                        os.chmod(file_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                    except Exception:
                        pass

            if verbose:
                self.console.print(f"✅ Fixed permissions for: {directory}")

        except Exception as e:
            if verbose:
                self.console.print(
                    f"⚠️  Could not fix all permissions in {directory}: {e}",
                    style="yellow",
                )
                self.console.print(
                    "🧹 Note: Data cleaner will handle root-owned files during volume cleanup"
                )

    def _validate_cleanup(self, verbose: bool = False) -> bool:
        """Validate that cleanup worked properly."""
        import subprocess

        validation_success = True

        # Check that critical ports are free using HealthChecker
        ports_to_check = [11434, 6333]  # Ollama and Qdrant default ports

        # Use HealthChecker for intelligent port availability checking
        ports_available = self.health_checker.wait_for_ports_available(
            ports_to_check, timeout=10  # Shorter timeout for validation
        )

        if ports_available:
            if verbose:
                self.console.print(f"✅ All critical ports {ports_to_check} are free")
        else:
            if verbose:
                # Check individual ports for detailed reporting
                for port in ports_to_check:
                    if not self.health_checker.is_port_available(port):
                        self.console.print(
                            f"❌ Port {port} still in use after cleanup",
                            style="red",
                        )

        if not ports_available:
            # For podman, ports may take longer to be released due to rootless networking
            # This is not necessarily a cleanup failure, so we'll warn but not fail
            if verbose:
                self.console.print(
                    "⚠️  Port cleanup delayed (common with podman rootless)",
                    style="yellow",
                )
            # Don't fail validation for port issues alone
            # validation_success = False

        # Check that containers are actually gone
        container_engine = "docker" if self.force_docker else "podman"
        container_names = [
            self.get_container_name("ollama"),
            self.get_container_name("qdrant"),
        ]

        for container_name in container_names:
            try:
                result = subprocess.run(
                    [
                        container_engine,
                        "ps",
                        "-a",
                        "--filter",
                        f"name={container_name}",
                        "--format",
                        "{{.Names}}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0 and container_name in result.stdout:
                    validation_success = False
                    if verbose:
                        self.console.print(
                            f"❌ Container {container_name} still exists", style="red"
                        )
                elif verbose:
                    self.console.print(
                        f"✅ Container {container_name} properly removed"
                    )

            except Exception as e:
                if verbose:
                    self.console.print(
                        f"⚠️  Could not check container {container_name}: {e}",
                        style="yellow",
                    )

        # Check for root-owned files that might cause startup issues
        validation_success &= self._verify_no_root_owned_files(verbose)

        return validation_success

    def _verify_no_root_owned_files(self, verbose: bool = False) -> bool:
        """Verify that no root-owned files remain that could cause container startup issues."""
        import subprocess

        verification_success = True

        # Check named volumes for root-owned files
        verification_success &= self._verify_named_volumes_ownership(verbose)

        # Check legacy directories for backward compatibility
        directories_to_check = []

        # Local directory
        local_data_dir = Path(".code-indexer")
        if local_data_dir.exists():
            directories_to_check.append(local_data_dir)

        # Global directories
        global_dir = Path.home() / ".code-indexer-data"

        if global_dir.exists():
            directories_to_check.append(global_dir)

        # Also check old global directory structure
        old_global_dir = Path.home() / ".code-indexer" / "global"
        if old_global_dir.exists():
            directories_to_check.append(old_global_dir)

        for data_dir in directories_to_check:
            try:
                # Find all root-owned files/directories
                result = subprocess.run(
                    ["find", str(data_dir), "-user", "root", "-o", "-group", "root"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0 and result.stdout.strip():
                    verification_success = False
                    root_owned_files = result.stdout.strip().split("\n")
                    if verbose:
                        self.console.print(
                            f"❌ Found root-owned files in {data_dir}:", style="red"
                        )
                        for file_path in root_owned_files:
                            self.console.print(f"  {file_path}", style="red")
                    else:
                        self.console.print(
                            f"❌ Found {len(root_owned_files)} root-owned files in {data_dir}",
                            style="red",
                        )
                elif verbose:
                    self.console.print(f"✅ No root-owned files found in {data_dir}")

            except Exception as e:
                if verbose:
                    self.console.print(
                        f"⚠️  Could not check for root-owned files in {data_dir}: {e}",
                        style="yellow",
                    )

        return verification_success

    def _verify_named_volumes_ownership(self, verbose: bool = False) -> bool:
        """Verify that named volumes don't contain root-owned files."""
        import subprocess

        verification_success = True
        container_engine = "docker" if self.force_docker else "podman"

        # Volume names to check
        volume_names = ["ollama_data", "qdrant_data"]

        for volume_name in volume_names:
            try:
                # Get volume mount point
                result = subprocess.run(
                    [
                        container_engine,
                        "volume",
                        "inspect",
                        volume_name,
                        "--format",
                        "{{.Mountpoint}}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    mountpoint = result.stdout.strip()
                    if mountpoint and Path(mountpoint).exists():
                        # Check for root-owned files in the volume
                        find_result = subprocess.run(
                            [
                                "find",
                                mountpoint,
                                "-user",
                                "root",
                                "-o",
                                "-group",
                                "root",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )

                        if find_result.returncode == 0 and find_result.stdout.strip():
                            verification_success = False
                            root_owned_files = find_result.stdout.strip().split("\n")
                            if verbose:
                                self.console.print(
                                    f"❌ Found root-owned files in volume {volume_name}:",
                                    style="red",
                                )
                                for file_path in root_owned_files[:10]:  # Show first 10
                                    self.console.print(f"  {file_path}", style="red")
                                if len(root_owned_files) > 10:
                                    self.console.print(
                                        f"  ... and {len(root_owned_files) - 10} more files",
                                        style="red",
                                    )
                            else:
                                self.console.print(
                                    f"❌ Found {len(root_owned_files)} root-owned files in volume {volume_name}",
                                    style="red",
                                )
                        elif verbose:
                            self.console.print(
                                f"✅ No root-owned files found in volume {volume_name}"
                            )
                    elif verbose:
                        self.console.print(
                            f"ℹ️  Volume {volume_name} mountpoint not accessible"
                        )
                elif verbose:
                    self.console.print(f"ℹ️  Volume {volume_name} does not exist")

            except Exception as e:
                if verbose:
                    self.console.print(
                        f"⚠️  Could not check volume {volume_name}: {e}",
                        style="yellow",
                    )

        return verification_success

    def _cleanup_global_directories(
        self, verbose: bool = False, force: bool = False
    ) -> bool:
        """Clean up global directories with enhanced permission handling."""
        import shutil

        success = True

        global_dir = Path.home() / ".code-indexer-data"

        if global_dir.exists():
            try:
                if force:
                    # Fix permissions before removal
                    self._fix_directory_permissions(global_dir, verbose)

                shutil.rmtree(global_dir, ignore_errors=not force)
                if verbose:
                    self.console.print(f"✅ Cleaned up global directory: {global_dir}")
            except Exception as e:
                success = False
                if verbose:
                    self.console.print(
                        f"❌ Could not clean global directory: {e}", style="red"
                    )

        # Also clean up the old problematic directory structure if it exists
        old_global_dir = Path.home() / ".code-indexer" / "global"
        if old_global_dir.exists():
            try:
                if force:
                    self._fix_directory_permissions(old_global_dir, verbose)

                shutil.rmtree(old_global_dir, ignore_errors=not force)
                if verbose:
                    self.console.print(
                        f"✅ Cleaned up old global directory: {old_global_dir}"
                    )
            except Exception as e:
                success = False
                if verbose:
                    self.console.print(
                        f"❌ Could not clean old global directory: {e}", style="red"
                    )

        return success

    def _cleanup_named_volumes(self, verbose: bool = False) -> bool:
        """Clean up named volumes for Ollama and Qdrant data."""
        import subprocess

        success = True
        container_engine = "docker" if self.force_docker else "podman"

        # Volume names to clean up
        volume_names = ["ollama_data", "qdrant_data"]

        for volume_name in volume_names:
            try:
                # Check if volume exists
                result = subprocess.run(
                    [container_engine, "volume", "inspect", volume_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    # Volume exists, remove it
                    remove_result = subprocess.run(
                        [container_engine, "volume", "rm", volume_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if remove_result.returncode == 0:
                        if verbose:
                            self.console.print(f"✅ Removed volume: {volume_name}")
                    else:
                        success = False
                        if verbose:
                            self.console.print(
                                f"❌ Failed to remove volume {volume_name}: {remove_result.stderr}",
                                style="red",
                            )
                elif verbose:
                    self.console.print(f"ℹ️  Volume {volume_name} does not exist")

            except Exception as e:
                success = False
                if verbose:
                    self.console.print(
                        f"❌ Error handling volume {volume_name}: {e}", style="yellow"
                    )

        return success

    def generate_compose_config(
        self, data_dir: Path = Path(".code-indexer")
    ) -> Dict[str, Any]:
        """Generate Docker Compose configuration for single global instances."""
        # Single global network for all services
        network_name = "code-indexer-global"

        # Find Dockerfiles (package location first, then project root)
        ollama_dockerfile = self._find_dockerfile("Dockerfile.ollama")
        qdrant_dockerfile = self._find_dockerfile("Dockerfile.qdrant")
        cleaner_dockerfile = self._find_dockerfile("Dockerfile.cleaner")

        # Copy Dockerfiles to .code-indexer directory so Docker can find them
        import shutil

        # Use .code-indexer/docker directory for Dockerfiles
        local_docker_dir = data_dir / "docker"
        local_docker_dir.mkdir(parents=True, exist_ok=True)

        local_ollama_dockerfile = local_docker_dir / "Dockerfile.ollama"
        local_qdrant_dockerfile = local_docker_dir / "Dockerfile.qdrant"
        local_cleaner_dockerfile = local_docker_dir / "Dockerfile.cleaner"

        shutil.copy2(ollama_dockerfile, local_ollama_dockerfile)
        shutil.copy2(qdrant_dockerfile, local_qdrant_dockerfile)
        shutil.copy2(cleaner_dockerfile, local_cleaner_dockerfile)

        # Copy cleanup script for data cleaner
        cleanup_script = Path(__file__).parent.parent / "docker" / "cleanup.sh"
        local_cleanup_script = local_docker_dir / "cleanup.sh"
        shutil.copy2(cleanup_script, local_cleanup_script)

        # No longer need global config directories since we use named volumes

        # Current working directory for project-specific qdrant storage
        # current_project_dir = Path.cwd()  # Currently unused but may be needed for future features

        # Get configured ports for services
        default_ports = {"ollama": 11434, "qdrant": 6333}
        ollama_port = self._get_service_port("ollama", default_ports["ollama"])
        qdrant_port = self._get_service_port("qdrant", default_ports["qdrant"])

        compose_config = {
            "services": {
                "ollama": {
                    "build": {
                        "context": str(local_docker_dir.absolute()),
                        "dockerfile": str(local_ollama_dockerfile.name),
                    },
                    "container_name": self.get_container_name("ollama"),
                    "ports": [
                        f"0.0.0.0:{ollama_port}:11434"
                    ],  # Map external custom port to internal default port, IPv4 only
                    "volumes": ["ollama_data:/home/ollama/.ollama"],
                    "restart": "unless-stopped",
                    "networks": [network_name],
                    "environment": self._get_ollama_environment(),
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
                        "context": str(local_docker_dir.absolute()),
                        "dockerfile": str(local_qdrant_dockerfile.name),
                    },
                    "container_name": self.get_container_name("qdrant"),
                    "ports": [
                        f"0.0.0.0:{qdrant_port}:6333"
                    ],  # Map external custom port to internal default port, IPv4 only
                    "volumes": [
                        # Use named volume for qdrant storage
                        "qdrant_data:/qdrant/storage"
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
                "data-cleaner": {
                    "build": {
                        "context": str(local_docker_dir.absolute()),
                        "dockerfile": str(local_cleaner_dockerfile.name),
                    },
                    "container_name": self.get_container_name("data-cleaner"),
                    "ports": [
                        "0.0.0.0:8091:8091"
                    ],  # IPv4 only, consistent with other services
                    "volumes": [
                        # Mount all the same volumes as the main services so it can clean them
                        "ollama_data:/data/ollama",
                        "qdrant_data:/data/qdrant",
                    ],
                    "privileged": True,  # Run with root privileges for cleanup
                    "restart": "unless-stopped",
                    "networks": [network_name],
                    "healthcheck": {
                        "test": ["CMD", "curl", "-f", "http://localhost:8091/"],
                        "interval": "30s",
                        "timeout": "10s",
                        "retries": 3,
                        "start_period": "10s",
                    },
                },
            },
            "networks": {network_name: {"name": network_name}},
            "volumes": {
                "ollama_data": {"driver": "local"},
                "qdrant_data": {"driver": "local"},
            },
        }

        return compose_config

    def start_data_cleaner(self) -> bool:
        """Start only the data cleaner service for cleanup operations."""
        try:
            if not self.compose_file.exists():
                self.console.print("❌ Compose file not found. Run setup first.")
                return False

            # Use docker compose to start only the data cleaner service
            compose_cmd = self.get_compose_command()
            cmd = compose_cmd + [
                "-f",
                str(self.compose_file),
                "-p",
                self.project_name,
                "up",
                "-d",
                "data-cleaner",
            ]

            self.console.print("🧹 Starting data cleaner service...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                self.console.print("✅ Data cleaner service started successfully")
                return True
            else:
                self.console.print(f"❌ Failed to start data cleaner: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.console.print("❌ Data cleaner startup timed out")
            return False
        except Exception as e:
            self.console.print(f"❌ Error starting data cleaner: {e}")
            return False

    def stop_data_cleaner(self) -> bool:
        """Stop the data cleaner service."""
        try:
            compose_cmd = self.get_compose_command()
            cmd = compose_cmd + [
                "-f",
                str(self.compose_file),
                "-p",
                self.project_name,
                "stop",
                "data-cleaner",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0

        except Exception:
            return False

    def clean_with_data_cleaner(self, paths: List[str]) -> bool:
        """Use the data cleaner service to remove root-owned files."""
        try:
            container_name = self.get_container_name("data-cleaner")

            # Detect container engine (podman or docker)
            container_engine = (
                "docker"
                if self.force_docker
                else (
                    "podman"
                    if subprocess.run(
                        ["which", "podman"], capture_output=True
                    ).returncode
                    == 0
                    else "docker"
                )
            )

            # Check if data cleaner is running
            check_cmd = [
                container_engine,
                "ps",
                "--filter",
                f"name={container_name}",
                "--format",
                "{{.Names}}",
            ]
            check_result = subprocess.run(check_cmd, capture_output=True, text=True)

            if container_name not in check_result.stdout:
                self.console.print("🧹 Data cleaner not running, starting it...")
                if not self.start_data_cleaner():
                    return False

                # Wait for the data cleaner service to be ready
                data_cleaner_ready = self.health_checker.wait_for_service_ready(
                    "http://localhost:8091",  # Data cleaner root endpoint
                    timeout=self.health_checker.get_timeouts().get(
                        "data_cleaner_startup", 60
                    ),
                )

                if not data_cleaner_ready:
                    self.console.print(
                        "❌ Data cleaner failed to become ready", style="red"
                    )
                    return False

            # Use container exec to run cleanup commands with shell expansion
            for path in paths:
                self.console.print(f"🗑️  Cleaning path: {path}")
                # Use sh -c to enable shell expansion for wildcards
                cmd = [
                    container_engine,
                    "exec",
                    container_name,
                    "sh",
                    "-c",
                    f"rm -rf {path}",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                if result.returncode != 0:
                    self.console.print(
                        f"⚠️  Warning: Could not clean {path}: {result.stderr}"
                    )
                else:
                    self.console.print(f"✅ Cleaned: {path}")

            return True

        except Exception as e:
            self.console.print(f"❌ Error using data cleaner: {e}")
            return False

    def stop_main_services(self) -> bool:
        """Stop only the main services (ollama and qdrant), leaving data cleaner running."""
        try:
            if not self.compose_file.exists():
                return True  # Nothing to stop

            compose_cmd = self.get_compose_command()

            # Stop ollama and qdrant services individually
            for service in ["ollama", "qdrant"]:
                cmd = compose_cmd + [
                    "-f",
                    str(self.compose_file),
                    "-p",
                    self.project_name,
                    "stop",
                    service,
                ]

                self.console.print(f"🛑 Stopping {service} service...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                if result.returncode != 0:
                    self.console.print(
                        f"⚠️  Warning: Failed to stop {service}: {result.stderr}"
                    )

            return True

        except Exception as e:
            self.console.print(f"❌ Error stopping main services: {e}")
            return False

    def _get_ollama_environment(self) -> List[str]:
        """Get Ollama environment variables for performance control.

        References:
        - Ollama FAQ: https://github.com/ollama/ollama/blob/main/docs/faq.md
        - Environment variables documentation: https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server
        """
        env_vars = []

        ollama_config = self._config.get("ollama", {})

        # OLLAMA_NUM_PARALLEL: Maximum parallel requests each model processes simultaneously
        # Default: 4 or 1 based on available memory
        # Reference: https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server
        num_parallel = ollama_config.get("num_parallel", 1)
        env_vars.append(f"OLLAMA_NUM_PARALLEL={num_parallel}")

        # OLLAMA_MAX_LOADED_MODELS: Maximum number of models loaded concurrently
        # Default: 3×GPU count or 3 for CPU
        # Reference: https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server
        max_loaded = ollama_config.get("max_loaded_models", 1)
        env_vars.append(f"OLLAMA_MAX_LOADED_MODELS={max_loaded}")

        # OLLAMA_MAX_QUEUE: Maximum queued requests before rejecting with 503 error
        # Default: 512
        # Reference: https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server
        max_queue = ollama_config.get("max_queue", 512)
        env_vars.append(f"OLLAMA_MAX_QUEUE={max_queue}")

        return env_vars


def get_global_compose_file_path(force_docker: bool = False) -> Path:
    """Get the path to the global compose file stored in the home directory.

    This is a standalone function that can be used anywhere in the codebase
    to get the consistent compose file location.

    Args:
        force_docker: Whether Docker is being forced (affects test mode directory)

    Returns:
        Path to the global docker-compose.yml file
    """

    # Use a dedicated directory for compose files, separate from data
    # Now that we use named volumes, we don't need the data directory structure
    compose_dir = Path.home() / ".code-indexer-compose"

    # Ensure the directory exists
    compose_dir.mkdir(parents=True, exist_ok=True)

    return compose_dir / "docker-compose.yml"
