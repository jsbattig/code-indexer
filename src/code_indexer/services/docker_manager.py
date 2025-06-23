"""Docker container management for Ollama and Qdrant services."""

import os
import subprocess
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
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

    def get_required_services(
        self, config: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Determine which services are required based on configuration.

        Args:
            config: Optional configuration dict. If None, uses self.main_config

        Returns:
            List of required service names
        """
        required_services = ["qdrant", "data-cleaner"]  # Always needed

        # Use provided config or fall back to main_config
        config_to_use = config or self.main_config or {}

        # Check embedding provider
        embedding_provider = config_to_use.get("embedding_provider", "ollama")

        if embedding_provider == "ollama":
            required_services.append("ollama")

        return required_services

    def _container_exists(self, service_name: str) -> bool:
        """Check if a container exists using direct container engine commands."""
        container_name = self.get_container_name(service_name)
        container_engine = "docker" if self.force_docker else "podman"

        try:
            # Use direct container engine command to check existence
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
            return result.returncode == 0 and container_name in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _container_running(self, service_name: str) -> bool:
        """Check if a container is running using direct container engine commands."""
        container_name = self.get_container_name(service_name)
        container_engine = "docker" if self.force_docker else "podman"

        try:
            # Use direct container engine command to check if running
            result = subprocess.run(
                [
                    container_engine,
                    "ps",
                    "--filter",
                    f"name={container_name}",
                    "--filter",
                    "status=running",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and container_name in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _container_healthy(self, service_name: str) -> bool:
        """Check if a container is healthy."""
        if not self._container_running(service_name):
            return False

        # For services with health checks, verify health status
        if service_name == "ollama":
            return bool(
                self.health_checker.is_service_healthy("http://localhost:11434")
            )
        elif service_name == "qdrant":
            return bool(self.health_checker.is_service_healthy("http://localhost:6333"))
        elif service_name == "data-cleaner":
            return bool(self.health_checker.is_service_healthy("http://localhost:8091"))

        return True

    def _container_up_to_date(self, service_name: str) -> bool:
        """Check if a container is up to date with current configuration."""
        # For now, assume containers are up to date if they exist
        # In the future, this could check image versions, environment variables, etc.
        return self._container_exists(service_name)

    def get_service_state(self, service_name: str) -> Dict[str, Any]:
        """Get current state of a specific service."""
        return {
            "exists": self._container_exists(service_name),
            "running": self._container_running(service_name),
            "healthy": self._container_healthy(service_name),
            "up_to_date": self._container_up_to_date(service_name),
        }

    def get_services_state(self) -> Dict[str, Dict[str, Any]]:
        """Get state of all required services."""
        required_services = self.get_required_services()
        return {
            service: self.get_service_state(service) for service in required_services
        }

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

    def _get_preferred_runtime(self) -> str:
        """Get the preferred container runtime, matching compose command selection logic."""
        if self.force_docker:
            return "docker"

        # Same priority as get_compose_command: Podman first unless forced
        try:
            result = subprocess.run(
                ["podman", "version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return "podman"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fall back to docker
        try:
            result = subprocess.run(
                ["docker", "version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return "docker"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Default fallback
        return "docker"

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
        """Start Docker services with intelligent state detection and idempotent behavior."""
        # Determine required services based on configuration
        required_services = self.get_required_services(self.main_config)

        self.console.print(f"🔍 Required services: {', '.join(required_services)}")

        # Check current state of all required services
        service_states = {}
        for service in required_services:
            service_states[service] = self.get_service_state(service)
            state = service_states[service]

            if state["running"] and state["healthy"]:
                self.console.print(f"✅ {service}: already running and healthy")
            elif state["exists"] and state["running"] and not state["healthy"]:
                self.console.print(f"⚠️  {service}: running but unhealthy")
            elif state["exists"] and not state["running"]:
                self.console.print(f"🔄 {service}: exists but not running")
            elif not state["exists"]:
                self.console.print(f"📥 {service}: needs to be created")

        # Determine if we need to regenerate compose config
        needs_compose_update = (
            recreate
            or self.main_config is not None
            or not self.compose_file.exists()
            or not all(state["up_to_date"] for state in service_states.values())
        )

        if needs_compose_update:
            self.console.print("📝 Updating Docker Compose configuration...")
            compose_config = self.generate_compose_config()
            with open(self.compose_file, "w") as f:
                yaml.dump(compose_config, f, default_flow_style=False)

        # Check if any services need to be started
        services_needing_start = [
            service
            for service, state in service_states.items()
            if not (state["running"] and state["healthy"])
        ]

        if not services_needing_start and not recreate:
            self.console.print(
                "✅ All required services are already running and healthy"
            )
            return True

        compose_cmd = self.get_compose_command()

        # Check if we need to download images
        any_missing = any(not state["exists"] for state in service_states.values())
        if any_missing:
            self.console.print(
                "📥 Some services need to be created. This may take several minutes to download Docker images..."
            )

        try:
            # Determine which services need to be created vs started
            services_to_create = [
                service
                for service, state in service_states.items()
                if not state["exists"] and service in services_needing_start
            ]
            services_to_start = [
                service
                for service, state in service_states.items()
                if state["exists"]
                and not state["running"]
                and service in services_needing_start
            ]

            # If force recreate, treat all required services as needing creation
            if recreate:
                services_to_create = list(required_services)
                services_to_start = []

            services_to_show = required_services if recreate else services_needing_start
            self.console.print(f"🚀 Starting services: {' '.join(services_to_show)}")

            # First, start existing stopped containers using direct container commands
            if services_to_start:
                # Determine runtime
                runtime = "docker"
                try:
                    subprocess.run(
                        ["docker", "version"],
                        capture_output=True,
                        timeout=5,
                        check=True,
                    )
                except (
                    subprocess.TimeoutExpired,
                    FileNotFoundError,
                    subprocess.CalledProcessError,
                ):
                    runtime = "podman"

                self.console.print(
                    f"🔄 Starting existing containers: {' '.join(services_to_start)}"
                )

                started_containers = []
                failed_containers = []

                for service in services_to_start:
                    container_name = f"code-indexer-{service}"
                    try:
                        start_result = subprocess.run(
                            [runtime, "start", container_name],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                        if start_result.returncode == 0:
                            started_containers.append(service)
                        else:
                            failed_containers.append(
                                f"{service}: {start_result.stderr}"
                            )
                    except Exception as e:
                        failed_containers.append(f"{service}: {str(e)}")

                if failed_containers:
                    self.console.print(
                        f"❌ Failed to start some containers: {'; '.join(failed_containers)}",
                        style="red",
                    )
                    return False
                else:
                    self.console.print(
                        f"✅ Started existing containers: {' '.join(started_containers)}"
                    )
                    if start_result.stdout.strip():
                        self.console.print(
                            f"Output: {start_result.stdout.strip()}", style="dim"
                        )

            # Then, create new containers if needed
            if services_to_create:
                cmd = (
                    compose_cmd
                    + [
                        "-f",
                        str(self.compose_file),
                        "-p",
                        self.project_name,
                        "up",
                        "-d",
                    ]
                    + services_to_create
                )

                if recreate:
                    cmd.append("--force-recreate")
            else:
                # No services to create, we're done
                if services_to_start:
                    self.console.print("✅ Services started successfully in 0s")
                    return True
                cmd = None

            # Execute with real-time output (only if we have containers to create)
            import time

            start_time = time.time()

            if cmd is not None:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )
            else:
                process = None

            if process is not None:
                output_lines = []
                last_progress_time = time.time()

                while True:
                    if process.stdout is None:
                        break
                    line = process.stdout.readline()
                    if line:
                        clean_line = line.strip()
                        if clean_line:
                            if any(
                                keyword in clean_line.lower()
                                for keyword in ["pulling", "downloading", "extracting"]
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
                        current_time = time.time()
                        if current_time - last_progress_time > 30:
                            elapsed = int(current_time - start_time)
                            self.console.print(
                                f"⏱️  Still working... ({elapsed}s elapsed)",
                                style="blue",
                            )
                            last_progress_time = current_time
                        time.sleep(0.1)

                return_code = process.wait(timeout=600)
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
            else:
                # No containers to create, just started existing ones
                elapsed = int(time.time() - start_time)
                self.console.print(
                    f"✅ Services started successfully in {elapsed}s", style="green"
                )
                return True

        except subprocess.TimeoutExpired:
            self.console.print("❌ Timeout starting services (10 minutes)", style="red")
            if process is not None:
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
        """Stop Docker services using deterministic container names."""
        expected_containers = [
            "code-indexer-qdrant",
            "code-indexer-ollama",
            "code-indexer-data-cleaner",
        ]

        # Determine runtime: use same logic as compose command selection
        runtime = self._get_preferred_runtime()

        stopped_count = 0
        errors = []

        try:
            with self.console.status("Stopping services..."):
                for container_name in expected_containers:
                    try:
                        result = subprocess.run(
                            [runtime, "stop", container_name],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )

                        if result.returncode == 0:
                            stopped_count += 1
                        else:
                            # Check if container doesn't exist (not an error in this context)
                            if "no such container" in result.stderr.lower():
                                stopped_count += 1  # Consider it "stopped"
                            else:
                                errors.append(f"{container_name}: {result.stderr}")

                    except subprocess.TimeoutExpired:
                        errors.append(f"{container_name}: timeout")
                    except Exception as e:
                        errors.append(f"{container_name}: {str(e)}")

            if stopped_count == len(expected_containers):
                self.console.print("✅ Services stopped successfully", style="green")
                return True
            else:
                error_msg = "; ".join(errors) if errors else "Unknown error"
                self.console.print(
                    f"❌ Failed to stop some services: {error_msg}", style="red"
                )
                return False

        except Exception as e:
            self.console.print(f"❌ Error stopping services: {e}", style="red")
            return False

    def remove_containers(self, remove_volumes: bool = False) -> bool:
        """Remove Docker containers and optionally volumes."""
        if not self.compose_file.exists():
            return True

        compose_cmd = self.get_compose_command()
        cmd_args = compose_cmd + [
            "-f",
            str(self.compose_file),
            "-p",
            self.project_name,
            "down",
        ]

        if remove_volumes:
            cmd_args.append("-v")

        try:
            action = (
                "Removing containers and volumes"
                if remove_volumes
                else "Removing containers"
            )
            with self.console.status(f"{action}..."):
                result = subprocess.run(
                    cmd_args,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            if result.returncode == 0:
                self.console.print(f"✅ {action} completed successfully", style="green")
                return True
            else:
                self.console.print(
                    f"❌ Failed to remove containers: {result.stderr}", style="red"
                )
                return False

        except subprocess.TimeoutExpired:
            self.console.print("❌ Timeout removing containers", style="red")
            return False
        except Exception as e:
            self.console.print(f"❌ Error removing containers: {e}", style="red")
            return False

    def clean_data_only(self, all_projects: bool = False) -> bool:
        """Clean project data without stopping containers."""
        try:
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            config = config_manager.load()

            # Initialize QdrantClient to clean collections
            from .qdrant import QdrantClient

            qdrant_client = QdrantClient(config.qdrant, self.console)

            # Try to clear collections, but don't fail if services aren't running
            try:
                if all_projects:
                    # Clear all collections
                    if (
                        qdrant_client.health_check()
                        and qdrant_client.clear_all_collections()
                    ):
                        self.console.print("✅ All project data cleared", style="green")
                    else:
                        self.console.print(
                            "⚠️  Qdrant not accessible, skipping collection cleanup",
                            style="yellow",
                        )
                else:
                    # Clear current project collection only
                    from .embedding_factory import EmbeddingProviderFactory

                    embedding_provider = EmbeddingProviderFactory.create(config)
                    collection_name = qdrant_client.resolve_collection_name(
                        config, embedding_provider
                    )

                    if qdrant_client.health_check() and qdrant_client.clear_collection(
                        collection_name
                    ):
                        self.console.print(
                            f"✅ Project data cleared (collection: {collection_name})",
                            style="green",
                        )
                    else:
                        self.console.print(
                            "⚠️  Qdrant not accessible, skipping collection cleanup",
                            style="yellow",
                        )
            except Exception as e:
                self.console.print(
                    f"⚠️  Could not clear collections: {e}", style="yellow"
                )

            # NOTE: clean-data should NOT remove local config directory
            # The config directory contains the configuration needed to stop services
            # Only `uninstall` should remove the config directory for complete cleanup
            # This ensures users can still run `stop` after `clean-data`

            return True

        except Exception as e:
            self.console.print(f"❌ Error cleaning data: {e}", style="red")
            return False

    def restart_services(self) -> bool:
        """Restart Docker services."""
        self.console.print("Restarting services...")
        return self.stop_services() and self.start_services()

    def get_service_status(self) -> Dict[str, Any]:
        """Get status of required services using deterministic container names."""
        services = {}
        # Only check required services based on current configuration
        required_services = self.get_required_services(self.main_config)
        expected_containers = [
            f"code-indexer-{service}" for service in required_services
        ]

        # Determine runtime: use same logic as compose command selection
        runtime = self._get_preferred_runtime()

        try:
            for container_name in expected_containers:
                result = subprocess.run(
                    [
                        runtime,
                        "inspect",
                        container_name,
                        "--format",
                        "{{.State.Status}}|{{.State.Health.Status}}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    output = result.stdout.strip()
                    parts = output.split("|")
                    state = parts[0] if len(parts) > 0 else "unknown"
                    health = (
                        parts[1]
                        if len(parts) > 1 and parts[1] != "<no value>"
                        else "unknown"
                    )

                    services[container_name] = {
                        "state": state,
                        "health": health,
                    }

        except Exception:
            return {"status": "unavailable", "services": {}}

        # Determine overall status based on container states
        if not services:
            overall_status = "stopped"
        else:
            running_count = sum(
                1 for service in services.values() if service["state"] == "running"
            )
            if running_count == len(services):
                overall_status = "running"
            elif running_count == 0:
                overall_status = "stopped"
            else:
                overall_status = "partial"

        return {
            "status": overall_status,
            "services": services,
        }

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

    def _monitor_qdrant_recovery(self) -> Dict[str, Any]:
        """Monitor Qdrant's collection recovery progress by parsing logs."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", "50", "code-indexer-qdrant"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return {"status": "log_error", "progress": None}

            logs = result.stdout

            # Parse recovery progress from logs
            loading_collections = []
            recovered_collections = []
            current_operation = None

            for line in logs.split("\n"):
                if "Loading collection:" in line:
                    # Extract collection name from log line
                    collection_name = line.split("Loading collection:")[-1].strip()
                    loading_collections.append(collection_name)
                    current_operation = f"Loading {collection_name}"
                elif "Recovered collection" in line and "100%" in line:
                    # Extract collection name from log line
                    collection_name = (
                        line.split("Recovered collection")[-1].split(":")[0].strip()
                    )
                    recovered_collections.append(collection_name)
                elif "Qdrant HTTP listening on" in line:
                    current_operation = "HTTP server ready"
                elif "starting service:" in line and "actix-web-service" in line:
                    current_operation = "Starting HTTP service"

            # Determine status based on log analysis
            if "Qdrant HTTP listening on" in logs:
                status = "ready"
                progress = {
                    "loading": len(loading_collections),
                    "recovered": len(recovered_collections),
                }
            elif loading_collections:
                status = "recovering"
                progress = {
                    "loading": len(loading_collections),
                    "recovered": len(recovered_collections),
                }
            else:
                status = "starting"
                progress = None

            return {
                "status": status,
                "progress": progress,
                "current_operation": current_operation,
                "loading_collections": (
                    loading_collections[-3:] if loading_collections else []
                ),  # Last 3
                "recovered_count": len(recovered_collections),
            }

        except Exception as e:
            return {"status": "monitor_error", "error": str(e), "progress": None}

    def _check_qdrant_with_recovery_monitoring(self) -> Tuple[bool, str]:
        """Check Qdrant status with intelligent recovery monitoring."""
        import requests  # type: ignore

        # First try direct HTTP connection
        try:
            qdrant_url = self._get_service_url("qdrant")
            response = requests.get(f"{qdrant_url}/", timeout=2)
            if response.status_code == 200:
                return True, "ready"
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass

        # If HTTP fails, check recovery progress
        recovery_info = self._monitor_qdrant_recovery()

        if recovery_info["status"] == "ready":
            return True, "ready"
        elif recovery_info["status"] == "recovering":
            if recovery_info["progress"]:
                recovered = recovery_info["recovered_count"]
                current_op = recovery_info.get("current_operation", "unknown")
                return False, f"recovering_collections_{recovered}|{current_op}"
            else:
                return False, "recovering_unknown"
        elif recovery_info["status"] == "starting":
            return False, "starting_up"
        else:
            return False, f"connection_refused_{recovery_info['status']}"

    def wait_for_services(self, timeout: int = 120, retry_interval: int = 2) -> bool:
        """Wait for services to be healthy using retry logic with exponential backoff and intelligent Qdrant monitoring."""
        import requests  # type: ignore

        # Get list of required services dynamically
        required_services = self.get_required_services()

        # Use adaptive timeout if default timeout is requested
        if timeout == 120:  # Default timeout
            timeout = self.get_adaptive_timeout(timeout)

        self.console.print(f"Waiting for services to be ready (timeout: {timeout}s)...")

        import time

        start_time = time.time()
        attempt = 1
        last_status = {service: "unknown" for service in required_services}
        last_qdrant_progress = {
            "recovered": 0,
            "last_check": start_time,
            "last_operation": None,
        }
        stuck_threshold = 120  # Consider stuck if no progress for 2 minutes

        # Dynamic timeout extension for recovery scenarios
        effective_timeout: float = float(timeout)

        while time.time() - start_time < effective_timeout:
            current_status = {}
            services_healthy = {}

            # Check each required service
            for service_name in required_services:
                services_healthy[service_name] = False

                if service_name == "ollama":
                    # Check ollama service with detailed error reporting
                    try:
                        ollama_url = self._get_service_url("ollama")
                        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
                        if response.status_code == 200:
                            services_healthy[service_name] = True
                            current_status[service_name] = "ready"
                        else:
                            current_status[service_name] = (
                                f"http_{response.status_code}"
                            )
                    except requests.exceptions.ConnectionError:
                        current_status[service_name] = "connection_refused"
                    except requests.exceptions.Timeout:
                        current_status[service_name] = "timeout"
                    except Exception as e:
                        current_status[service_name] = f"error_{type(e).__name__}"

                elif service_name == "qdrant":
                    # Check qdrant service with intelligent recovery monitoring
                    is_healthy, status_detail = (
                        self._check_qdrant_with_recovery_monitoring()
                    )
                    services_healthy[service_name] = is_healthy
                    current_status[service_name] = status_detail

                elif service_name == "data-cleaner":
                    # Check data-cleaner service with HTTP health check on port 8091
                    try:
                        response = requests.get("http://localhost:8091/", timeout=5)
                        if response.status_code == 200:
                            services_healthy[service_name] = True
                            current_status[service_name] = "ready"
                        else:
                            current_status[service_name] = (
                                f"http_{response.status_code}"
                            )
                    except requests.exceptions.ConnectionError:
                        current_status[service_name] = "connection_refused"
                    except requests.exceptions.Timeout:
                        current_status[service_name] = "timeout"
                    except Exception as e:
                        current_status[service_name] = f"error_{type(e).__name__}"

            # Log status changes with enhanced Qdrant feedback
            if current_status != last_status:
                elapsed = int(time.time() - start_time)
                status_parts = []

                for service, status in current_status.items():
                    if service == "qdrant" and "recovering_collections_" in status:
                        # Parse Qdrant recovery info for user-friendly display
                        parts = status.split("|")
                        recovered_info = parts[0].replace("recovering_collections_", "")

                        # Get additional progress info and track progress
                        recovery_info = self._monitor_qdrant_recovery()
                        if recovery_info.get("progress"):
                            loaded = recovery_info["progress"].get("loading", 0)
                            recovered_count = recovery_info.get("recovered_count", 0)

                            # Track progress to detect stuck situations and extend timeout
                            current_time = time.time()

                            # Check for progress in recovered count OR current operation change
                            if recovered_count > last_qdrant_progress[
                                "recovered"
                            ] or recovery_info.get(
                                "current_operation"
                            ) != last_qdrant_progress.get(
                                "last_operation"
                            ):
                                last_qdrant_progress["recovered"] = recovered_count
                                last_qdrant_progress["last_check"] = current_time
                                last_qdrant_progress["last_operation"] = (
                                    recovery_info.get("current_operation")
                                )
                                # Progress made - reset timeout extension

                                # Extend timeout if making progress and many collections remain
                                if loaded > 50:  # Lots of collections to recover
                                    new_timeout = max(
                                        effective_timeout,
                                        current_time - start_time + 180,
                                    )  # Add 3 minutes
                                    if new_timeout > effective_timeout:
                                        effective_timeout = new_timeout
                                        self.console.print(
                                            f"⏱️  Extended timeout to {int(effective_timeout - (current_time - start_time))}s due to collection recovery progress",
                                            style="blue",
                                        )

                            # Check if stuck (no progress for too long)
                            last_check_time = last_qdrant_progress["last_check"]
                            assert isinstance(
                                last_check_time, (int, float)
                            ), "last_check should be numeric"
                            time_since_progress = current_time - last_check_time
                            if time_since_progress > stuck_threshold:
                                self.console.print(
                                    f"⚠️  Qdrant appears stuck: no progress for {int(time_since_progress)}s",
                                    style="red",
                                )
                            else:
                                self.console.print(
                                    f"🔄 Qdrant recovering collections: {recovered_count} recovered, {loaded} total found",
                                    style="yellow",
                                )
                                if recovery_info.get("current_operation"):
                                    self.console.print(
                                        f"   Current: {recovery_info['current_operation']}",
                                        style="dim yellow",
                                    )
                        status_parts.append(f"{service}=recovering({recovered_info})")
                    else:
                        status_parts.append(f"{service}={status}")

                self.console.print(
                    f"[{elapsed:3d}s] Attempt {attempt:2d}: {', '.join(status_parts)}",
                    style="dim",
                )
                last_status = current_status.copy()

            # Check if all required services are healthy
            if all(services_healthy.values()):
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

        # Show final status for all required services
        final_status_parts = [
            f"{service}={current_status.get(service, 'unknown')}"
            for service in required_services
        ]
        self.console.print(
            f"Final status: {', '.join(final_status_parts)}",
            style="red",
        )

        # Show container logs for debugging
        for service in required_services:
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
        return self.remove_containers(remove_volumes=False)

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

                # Only validate if we actually had something to clean up
                if not self.compose_file.exists():
                    if verbose:
                        self.console.print(
                            "✅ No compose file exists, nothing to validate"
                        )
                    validation_success = True
                else:
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
                        self.get_container_name("ollama"),
                        self.get_container_name("qdrant"),
                        self.get_container_name("data-cleaner"),
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
                    validation_success = (
                        validation_success and legacy_validation_success
                    )

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
            ports_to_check,
            timeout=10,  # Shorter timeout for validation
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

    def _build_ollama_service(
        self, local_docker_dir: Path, network_name: str
    ) -> Dict[str, Any]:
        """Build Ollama service configuration."""
        ollama_port = self._get_service_port("ollama", 11434)

        return {
            "build": {
                "context": str(local_docker_dir.absolute()),
                "dockerfile": "Dockerfile.ollama",
            },
            "container_name": self.get_container_name("ollama"),
            "ports": [f"0.0.0.0:{ollama_port}:11434"],
            "volumes": ["ollama_data:/home/ollama/.ollama"],
            "restart": "unless-stopped",
            "networks": [network_name],
            "environment": self._get_ollama_environment(),
            "healthcheck": {
                "test": ["CMD", "curl", "-f", "http://localhost:11434/api/tags"],
                "interval": "30s",
                "timeout": "10s",
                "retries": 3,
                "start_period": "30s",
            },
        }

    def _build_qdrant_service(
        self, local_docker_dir: Path, network_name: str
    ) -> Dict[str, Any]:
        """Build Qdrant service configuration."""
        qdrant_port = self._get_service_port("qdrant", 6333)

        return {
            "build": {
                "context": str(local_docker_dir.absolute()),
                "dockerfile": "Dockerfile.qdrant",
            },
            "container_name": self.get_container_name("qdrant"),
            "ports": [f"0.0.0.0:{qdrant_port}:6333"],
            "volumes": ["qdrant_data:/qdrant/storage"],
            "environment": [
                "QDRANT_ALLOW_ANONYMOUS_READ=true",
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
        }

    def _build_cleaner_service(
        self,
        local_docker_dir: Path,
        network_name: str,
        include_ollama_volumes: bool = True,
    ) -> Dict[str, Any]:
        """Build data cleaner service configuration."""
        volumes = ["qdrant_data:/data/qdrant"]
        if include_ollama_volumes:
            volumes.append("ollama_data:/data/ollama")

        return {
            "build": {
                "context": str(local_docker_dir.absolute()),
                "dockerfile": "Dockerfile.cleaner",
            },
            "container_name": self.get_container_name("data-cleaner"),
            "ports": ["0.0.0.0:8091:8091"],
            "volumes": volumes,
            "privileged": True,
            "restart": "unless-stopped",
            "networks": [network_name],
            "healthcheck": {
                "test": ["CMD", "curl", "-f", "http://localhost:8091/"],
                "interval": "30s",
                "timeout": "10s",
                "retries": 3,
                "start_period": "10s",
            },
        }

    def generate_compose_config(
        self, data_dir: Path = Path(".code-indexer")
    ) -> Dict[str, Any]:
        """Generate Docker Compose configuration for required services only."""
        # Determine which services are required
        required_services = self.get_required_services()

        # Single global network for all services
        network_name = "code-indexer-global"

        # Prepare Dockerfiles
        import shutil

        local_docker_dir = data_dir / "docker"
        local_docker_dir.mkdir(parents=True, exist_ok=True)

        # Copy required Dockerfiles
        dockerfile_map = {
            "ollama": "Dockerfile.ollama",
            "qdrant": "Dockerfile.qdrant",
            "data-cleaner": "Dockerfile.cleaner",
        }

        for service in required_services:
            if service in dockerfile_map:
                source_dockerfile = self._find_dockerfile(dockerfile_map[service])
                target_dockerfile = local_docker_dir / dockerfile_map[service]
                shutil.copy2(source_dockerfile, target_dockerfile)

        # Copy cleanup script for data cleaner
        if "data-cleaner" in required_services:
            cleanup_script = Path(__file__).parent.parent / "docker" / "cleanup.sh"
            local_cleanup_script = local_docker_dir / "cleanup.sh"
            shutil.copy2(cleanup_script, local_cleanup_script)

        # Build compose configuration
        compose_config = {
            "services": {},
            "networks": {network_name: {"name": network_name}},
            "volumes": {"qdrant_data": {"driver": "local"}},
        }

        # Add services based on requirements
        if "qdrant" in required_services:
            compose_config["services"]["qdrant"] = self._build_qdrant_service(
                local_docker_dir, network_name
            )

        if "ollama" in required_services:
            compose_config["services"]["ollama"] = self._build_ollama_service(
                local_docker_dir, network_name
            )
            # Only include ollama volumes if ollama is required
            compose_config["volumes"]["ollama_data"] = {"driver": "local"}

        if "data-cleaner" in required_services:
            # Include ollama volumes in data-cleaner only if ollama service is required
            include_ollama_volumes = "ollama" in required_services
            compose_config["services"]["data-cleaner"] = self._build_cleaner_service(
                local_docker_dir, network_name, include_ollama_volumes
            )

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
