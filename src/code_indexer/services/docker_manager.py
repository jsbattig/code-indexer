"""Docker container management for Ollama and Qdrant services."""

import os
import subprocess
import re
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import yaml  # type: ignore

from rich.console import Console
from .health_checker import HealthChecker
from .global_port_registry import GlobalPortRegistry, PortRegistryError

logger = logging.getLogger(__name__)


class DockerManager:
    """Manages Docker containers for Code Indexer services."""

    def __init__(
        self,
        console: Optional[Console] = None,
        project_name: Optional[str] = None,
        force_docker: bool = False,
        project_config_dir: Optional[Path] = None,
    ):
        self.console = console or Console()
        self.force_docker = force_docker
        self.project_name = project_name or self._detect_project_name()
        self.project_config_dir = project_config_dir or Path(".code-indexer")
        self.compose_file = self._get_project_compose_file_path()
        self._config = self._load_service_config()
        self.health_checker = HealthChecker()
        self.port_registry = GlobalPortRegistry()
        self.indexing_root: Optional[Path] = (
            None  # Will be set via set_indexing_root() for first-time setup
        )

    def _detect_project_name(self) -> str:
        """Detect project name from current folder name for qdrant collection naming."""
        try:
            # Use current directory name as project name
            project_name = Path.cwd().name
            return self._sanitize_project_name(project_name)
        except (FileNotFoundError, OSError):
            # Fallback to default project name if current directory is invalid
            return self._sanitize_project_name("default")

    def _generate_container_names(self, project_root: Path) -> Dict[str, str]:
        """Generate project-specific container names based on project path hash."""
        project_hash = self.port_registry._calculate_project_hash(project_root)

        return {
            "project_hash": project_hash,
            "qdrant_name": f"cidx-{project_hash}-qdrant",
            "ollama_name": f"cidx-{project_hash}-ollama",
            "data_cleaner_name": f"cidx-{project_hash}-data-cleaner",
        }

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

    def _get_project_compose_file_path(self) -> Path:
        """Get the path to the project-specific compose file stored in the project directory."""
        return get_project_compose_file_path(self.project_config_dir, self.force_docker)

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

    def _get_service_url(self, service: str) -> Optional[str]:
        """Get the URL for a service based on configuration."""
        service_config = self._config.get(service, {})

        # If external service is configured, use external URL
        if service_config.get("external", False):
            return str(service_config.get("url", ""))

        # ===============================================================================
        # STEP 5: HEALTH CHECK PORT RESOLUTION - CRITICAL FOR SYNCHRONIZATION
        # ===============================================================================
        # This method is called by health checks and MUST use the exact same ports
        # that containers are running on. The port synchronization flow ensures this:
        #
        # 1. Port allocation calculates ports and stores in project config
        # 2. Containers start with those exact ports
        # 3. Health checks call this method → reads from project config
        # 4. Perfect synchronization: health checks use container ports!
        #
        # Previous bug: This method read stale config while containers used new ports
        # ===============================================================================

        # PRIMARY: Use project-specific calculated ports (updated during port allocation)
        try:
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            config = config_manager.load()

            # Get project ports from current project configuration
            project_ports = getattr(config, "project_ports", None)
            if project_ports:
                # Normalize service name for config key lookup (data-cleaner -> data_cleaner)
                normalized_service = service.replace("-", "_")
                service_port_key = f"{normalized_service}_port"
                # project_ports is a Pydantic object, use getattr instead of dict access
                port_value = getattr(project_ports, service_port_key, 0)
                if port_value and port_value != 0:
                    port = int(port_value)
                    return f"http://localhost:{port}"
        except Exception:
            # If config loading fails, fall back to other methods
            pass

        # NO FALLBACK PORTS! If we can't get the actual port from project config, return None
        # This will cause health checks to fail, which is correct behavior
        return None

    def get_required_services(
        self, config: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Determine which services are required based on configuration.

        Args:
            config: Optional configuration dict. If None, loads from project config

        Returns:
            List of required service names
        """
        required_services = ["qdrant", "data-cleaner"]  # Always needed

        # Use provided config or load from project configuration
        if config:
            config_to_use = config
        else:
            try:
                from ..config import ConfigManager

                config_manager = ConfigManager.create_with_backtrack()
                project_config = config_manager.load()
                config_to_use = {
                    "embedding_provider": project_config.embedding_provider
                }
            except Exception:
                # If config loading fails, use default
                config_to_use = {"embedding_provider": "ollama"}

        # Check embedding provider
        embedding_provider = config_to_use.get("embedding_provider", "ollama")

        if embedding_provider == "ollama":
            required_services.append("ollama")

        return required_services

    def _container_exists(
        self, service_name: str, project_config: Dict[str, str]
    ) -> bool:
        """Check if a container exists using direct container engine commands."""
        container_name = self.get_container_name(service_name, project_config)
        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")

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

    def _container_running(
        self, service_name: str, project_config: Dict[str, str]
    ) -> bool:
        """Check if a container is running using direct container engine commands."""
        container_name = self.get_container_name(service_name, project_config)
        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")

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

    def _container_healthy(
        self, service_name: str, project_config: Dict[str, str]
    ) -> bool:
        """Check if a container is healthy."""
        if not self._container_running(service_name, project_config):
            return False

        # For services with health checks, verify health status using ACTUAL container ports
        # This is critical for idempotent behavior - we must check the actual running containers
        actual_port = self._get_actual_container_port(service_name, project_config)
        if actual_port:
            service_url = f"http://localhost:{actual_port}"
            return bool(self.health_checker.is_service_healthy(service_url))

        # NO FALLBACK! If we can't get the actual port, the container is not healthy
        return False

    def _get_actual_container_port(
        self, service_name: str, project_config: Dict[str, str]
    ) -> Optional[int]:
        """Extract the actual port from a running container."""
        container_name = self.get_container_name(service_name, project_config)

        # Use the appropriate runtime based on force_docker flag
        runtime = self._get_available_runtime()
        if not runtime:
            return None

        # Try the selected runtime
        try:
            # Get port mapping from docker/podman ps
            cmd = [
                runtime,
                "ps",
                "--filter",
                f"name={container_name}",
                "--format",
                "{{.Ports}}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0 and result.stdout.strip():
                ports_output = result.stdout.strip()
                # Parse port mapping like "0.0.0.0:7264->6333/tcp"
                for port_mapping in ports_output.split(", "):
                    if "->" in port_mapping:
                        # Extract the external port
                        external_part = port_mapping.split("->")[0]
                        if ":" in external_part:
                            port_str = external_part.split(":")[-1]
                            try:
                                return int(port_str)
                            except ValueError:
                                continue

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def _container_up_to_date(
        self, service_name: str, project_config: Dict[str, str]
    ) -> bool:
        """Check if a container is up to date with current configuration."""
        # Container must exist first
        if not self._container_exists(service_name, project_config):
            return False

        # For qdrant and data-cleaner services, verify required host directories exist
        if service_name in ["qdrant", "data-cleaner"]:
            project_root = Path.cwd()
            project_qdrant_dir = project_root / ".code-indexer" / "qdrant"
            if not project_qdrant_dir.exists():
                return False

        # In the future, this could check image versions, environment variables, etc.
        return True

    def get_service_state(
        self, service_name: str, project_config: Dict[str, str]
    ) -> Dict[str, Any]:
        """Get current state of a specific service."""
        return {
            "exists": self._container_exists(service_name, project_config),
            "running": self._container_running(service_name, project_config),
            "healthy": self._container_healthy(service_name, project_config),
            "up_to_date": self._container_up_to_date(service_name, project_config),
        }

    def get_services_state(
        self, project_config: Dict[str, str]
    ) -> Dict[str, Dict[str, Any]]:
        """Get state of all required services."""
        required_services = self.get_required_services()
        return {
            service: self.get_service_state(service, project_config)
            for service in required_services
        }

    def is_docker_available(self) -> bool:
        """Check if Podman or Docker is available, prioritizing Podman unless force_docker is True."""

        if self.force_docker:
            # Force Docker mode - only check Docker
            try:
                result = subprocess.run(
                    ["docker", "--version"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    logger.debug("Docker is available (forced mode)")
                    return True
                else:
                    logger.warning(
                        f"Docker command failed in forced mode: {result.stderr}"
                    )
                    return False
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"Docker not found in forced mode: {e}")
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

    def _get_available_runtime(self) -> Optional[str]:
        """Get the available container runtime (podman or docker)."""
        if self.force_docker:
            try:
                # Fast check: just see if docker binary exists and is executable
                result = subprocess.run(
                    ["docker", "--version"],
                    capture_output=True,
                )
                return "docker" if result.returncode == 0 else None
            except FileNotFoundError:
                return None
        else:
            # Try podman first - fast binary check
            try:
                result = subprocess.run(
                    ["podman", "--version"],
                    capture_output=True,
                )
                if result.returncode == 0:
                    return "podman"
            except FileNotFoundError:
                pass

            # Fallback to docker - fast binary check
            try:
                result = subprocess.run(
                    ["docker", "--version"],
                    capture_output=True,
                )
                return "docker" if result.returncode == 0 else None
            except FileNotFoundError:
                return None

    def containers_exist(self, project_config: Dict[str, str]) -> bool:
        """Check if project-specific containers exist (not necessarily running)."""
        try:
            runtime = "docker" if self.force_docker else self._get_available_runtime()
            if not runtime:
                return False

            # Use project-specific container names
            container_names = [
                project_config["qdrant_name"],
                project_config["ollama_name"],
                project_config["data_cleaner_name"],
            ]

            for name in container_names:
                try:
                    cmd = [runtime, "container", "inspect", name]
                    result = subprocess.run(cmd, capture_output=True, timeout=5)
                    if result.returncode == 0:
                        return True  # At least one container exists
                except subprocess.TimeoutExpired:
                    continue
            return False
        except Exception:
            return False

    def set_indexing_root(self, indexing_root: Path) -> None:
        """Set the indexing root directory for mount configuration."""
        self.indexing_root = indexing_root.resolve()

    def ensure_project_configuration(
        self, config_manager, project_root: Path
    ) -> Dict[str, str]:
        """Ensure project has container names and ports configured."""
        config = config_manager.load()

        # Generate container names if not present
        if not config.project_containers.project_hash:
            container_names = self._generate_container_names(project_root)
            config.project_containers.project_hash = container_names["project_hash"]
            config.project_containers.qdrant_name = container_names["qdrant_name"]
            config.project_containers.ollama_name = container_names["ollama_name"]
            config.project_containers.data_cleaner_name = container_names[
                "data_cleaner_name"
            ]

            # Container names generated - no need to update shared config

        # Generate port assignments: CHECK CONTAINERS FIRST, then config
        container_names = self._generate_container_names(project_root)

        # Check if any containers exist for this project (permanent ports)
        existing_ports = {}
        containers_exist = False

        for service in ["qdrant", "data-cleaner", "ollama"]:
            if self._container_exists(service, container_names):
                containers_exist = True
                actual_port = self._get_actual_container_port(service, container_names)
                if actual_port:
                    port_key = f"{service.replace('-', '_')}_port"
                    existing_ports[port_key] = actual_port

        if containers_exist and existing_ports:
            # Containers exist - use their ports as permanent (same logic as start_services)
            self.console.print(
                "🏃 Found existing containers - using their ports as permanent"
            )
            ports = existing_ports
            # Update config to match actual container ports
            config.project_ports.qdrant_port = ports.get(
                "qdrant_port", config.project_ports.qdrant_port
            )
            config.project_ports.ollama_port = ports.get(
                "ollama_port", config.project_ports.ollama_port
            )
            config.project_ports.data_cleaner_port = ports.get(
                "data_cleaner_port", config.project_ports.data_cleaner_port
            )
        elif not config.project_ports.qdrant_port:
            # No containers and no config - allocate new ports using global registry
            ports = self.get_project_ports(project_root)
            config.project_ports.qdrant_port = ports["qdrant_port"]
            config.project_ports.data_cleaner_port = ports["data_cleaner_port"]
            # Only set ollama_port if it was allocated (VoyageAI doesn't need ollama)
            if "ollama_port" in ports:
                config.project_ports.ollama_port = ports["ollama_port"]
        else:
            # No containers but config exists - use config ports
            ports = {
                "qdrant_port": config.project_ports.qdrant_port,
                "data_cleaner_port": config.project_ports.data_cleaner_port,
            }
            # Only include ollama_port if it exists (VoyageAI doesn't need it)
            if config.project_ports.ollama_port is not None:
                ports["ollama_port"] = config.project_ports.ollama_port

        # Always ensure service URLs match calculated ports
        config.qdrant.host = f"http://localhost:{ports.get('qdrant_port', config.project_ports.qdrant_port)}"
        config.ollama.host = f"http://localhost:{ports.get('ollama_port', config.project_ports.ollama_port)}"

        # Save updated configuration
        config_manager.save(config)

        # Only return configuration for required services
        loaded_config = config_manager.load()
        config_dict = {
            "embedding_provider": loaded_config.embedding_provider,
            "ollama": (
                loaded_config.ollama.__dict__
                if hasattr(loaded_config, "ollama")
                else {}
            ),
            "qdrant": (
                loaded_config.qdrant.__dict__
                if hasattr(loaded_config, "qdrant")
                else {}
            ),
        }
        required_services = self.get_required_services(config_dict)
        result = {}

        # Always include project identifiers
        if hasattr(config.project_containers, "project_hash"):
            result["project_hash"] = config.project_containers.project_hash

        # Add container names and ports only for required services
        if "qdrant" in required_services:
            result["qdrant_name"] = config.project_containers.qdrant_name
            result["qdrant_port"] = config.project_ports.qdrant_port
        if "ollama" in required_services:
            result["ollama_name"] = config.project_containers.ollama_name
            result["ollama_port"] = config.project_ports.ollama_port
        if "data-cleaner" in required_services:
            result["data_cleaner_name"] = config.project_containers.data_cleaner_name
            result["data_cleaner_port"] = config.project_ports.data_cleaner_port

        return result

    def allocate_project_ports(
        self, project_root: Path, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, int]:
        """
        NEW: Allocate ports using global registry coordination.

        Replaces the old _allocate_free_ports method with global registry-based allocation.

        Args:
            project_root: Root directory of the project
            config: Optional configuration dict with embedding_provider info

        Returns:
            Dictionary mapping service names to port numbers

        Raises:
            PortRegistryError: If port allocation fails
        """
        try:
            # Clean registry and allocate ports for all required services
            ports = {}
            exclude_ports: set[int] = set()

            # Determine required services based on configuration
            required_services = self.get_required_services(config)

            # Map service names to registry service names
            service_mapping = {
                "qdrant": "qdrant",
                "ollama": "ollama",
                "data-cleaner": "data_cleaner",
            }

            # Allocate ports for each required service
            for service in required_services:
                registry_service = service_mapping.get(service, service)
                port = self.port_registry.find_available_port_for_service(
                    registry_service, exclude_ports
                )
                ports[f"{registry_service}_port"] = port
                exclude_ports.add(port)

            # Register allocation in global registry
            self.port_registry.register_project_allocation(project_root, ports)

            logger.info(f"Allocated ports for project {project_root}: {ports}")
            return ports

        except Exception as e:
            raise PortRegistryError(
                f"Failed to allocate ports for project {project_root}: {e}"
            )

    def get_project_ports(self, project_root: Path) -> Dict[str, int]:
        """
        NEW: Get existing ports from config or allocate new ones using global registry.

        Args:
            project_root: Root directory of the project

        Returns:
            Dictionary mapping service names to port numbers
        """
        # Try to load from existing config first
        config_dir = project_root / ".code-indexer"
        config_file = config_dir / "config.json"

        if config_file.exists():
            try:
                with open(config_file) as f:
                    config_data = json.load(f)
                    existing_ports = config_data.get("project_ports", {})

                if existing_ports and all(
                    isinstance(port, int) and port > 0
                    for port in existing_ports.values()
                ):
                    # Verify ports are still valid (not in use by other projects)
                    all_allocated = self.port_registry.get_all_allocated_ports()

                    # Check if any of our ports are allocated to different projects
                    conflicts = False
                    for port in existing_ports.values():
                        if port in all_allocated:
                            allocated_project = all_allocated[port]
                            current_project_hash = (
                                self.port_registry._calculate_project_hash(project_root)
                            )
                            if allocated_project != current_project_hash:
                                conflicts = True
                                break

                    if not conflicts:
                        # Re-register to ensure consistency
                        self.port_registry.register_project_allocation(
                            project_root, existing_ports
                        )
                        return existing_ports  # type: ignore[no-any-return]

            except (json.JSONDecodeError, KeyError, OSError):
                pass

        # Allocate new ports if none exist or existing ones are invalid
        return self.allocate_project_ports(project_root)

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
        """Start Docker services with permanent port allocation."""
        # Force remove any problematic containers before starting
        if recreate:
            self._force_remove_problematic_containers()

        # Load project configuration using backtracking
        from ..config import ConfigManager
        from pathlib import Path

        config_manager = ConfigManager.create_with_backtrack()
        config = config_manager.load()

        # Convert config to dict for required services detection
        config_dict = {
            "embedding_provider": config.embedding_provider,
            "ollama": config.ollama.__dict__ if hasattr(config, "ollama") else {},
            "qdrant": config.qdrant.__dict__ if hasattr(config, "qdrant") else {},
        }

        # Determine required services based on configuration
        required_services = self.get_required_services(config_dict)
        self.console.print(f"🔍 Required services: {', '.join(required_services)}")

        # Get project root from config
        project_root = Path(config.codebase_dir)

        # PERMANENT PORT LOGIC: Check if CONTAINERS exist (not config file)
        # If containers exist → their ports are permanent
        # If no containers → allocate new ports
        container_names = self._generate_container_names(project_root)

        # Check if any required service containers actually exist
        containers_exist = False
        actual_ports = {}

        for service in required_services:
            if self._container_exists(service, container_names):
                containers_exist = True
                # Extract actual port from existing container
                actual_port = self._get_actual_container_port(service, container_names)
                if actual_port:
                    port_key = f"{service.replace('-', '_')}_port"
                    actual_ports[port_key] = actual_port
                    self.console.print(
                        f"🔍 Found existing container: {service} on port {actual_port}"
                    )

        if containers_exist:
            # Containers exist - their ports are PERMANENT. Sync config with actual ports.
            self.console.print(
                "🏃 Found existing containers - using their ports as permanent"
            )

            # Ensure all required services have port assignments
            # Some services might not have containers yet, so we need to allocate ports for them
            missing_services = []
            for service in required_services:
                port_key = f"{service.replace('-', '_')}_port"
                if port_key not in actual_ports:
                    missing_services.append(service)

            if missing_services:
                self.console.print(
                    f"🔍 Missing containers for services: {missing_services}, allocating ports..."
                )
                # Allocate ports for missing services using global port registry
                all_calculated_ports = self.get_project_ports(project_root)

                # Only use the ports for missing services, preserve existing container ports
                for service in missing_services:
                    port_key = f"{service.replace('-', '_')}_port"
                    if port_key in all_calculated_ports:
                        actual_ports[port_key] = all_calculated_ports[port_key]
                        self.console.print(
                            f"🔌 Allocated port for {service}: {all_calculated_ports[port_key]}"
                        )

            # Update config to match actual container ports (synchronization)
            if actual_ports:
                self._update_config_with_ports(project_root, actual_ports)
                self.console.print(
                    f"💾 Synchronized config with container ports: {actual_ports}"
                )

            # Check if services are healthy with their actual ports

            # Check if all required services are healthy
            all_healthy = True
            for service in required_services:
                try:
                    # Get service URL using the permanent ports from config
                    service_url = self._get_service_url(service)
                    if service_url is None:
                        self.console.print(
                            f"🔍 {service} health check: No URL (port not found)"
                        )
                        all_healthy = False
                        break
                    is_healthy = self.health_checker.is_service_healthy(service_url)
                    self.console.print(f"🔍 {service} health check: {is_healthy}")
                    if not is_healthy:
                        all_healthy = False
                        break
                except Exception as e:
                    self.console.print(f"🔍 {service} health check failed: {e}")
                    all_healthy = False
                    break

            if all_healthy:
                self.console.print(
                    "✅ All required services are healthy with permanent ports"
                )
                return True
            else:
                self.console.print(
                    "⚠️  Some services not healthy - will restart with same ports"
                )
                # Ensure ALL mount directories exist before restarting containers
                self._ensure_all_mount_paths_exist(project_root, required_services)

                # Create proper project_config combining container names and ports
                restart_project_config = {
                    **container_names,  # Contains qdrant_name, ollama_name, etc.
                    **{
                        k: str(v) for k, v in actual_ports.items()
                    },  # Convert ports to strings
                }

                return self._attempt_start_with_ports(
                    required_services,
                    restart_project_config,
                    project_root,
                    recreate,
                    actual_ports,
                )

        # No existing containers - allocate new permanent ports
        self.console.print(
            "🆕 No existing containers - allocating new permanent ports..."
        )

        # Allocate new permanent ports using global port registry
        allocated_ports = self.allocate_project_ports(project_root)

        # Save ports to config RIGHT AWAY - these are now our permanent ports
        self._update_config_with_ports(project_root, allocated_ports)
        self.console.print(f"💾 Saved permanent ports to config: {allocated_ports}")

        # Ensure ALL mount directories exist before starting containers
        self._ensure_all_mount_paths_exist(project_root, required_services)

        # Now start containers with these permanent ports
        # Create proper project_config combining container names and ports
        new_start_project_config = {
            **container_names,  # Contains qdrant_name, ollama_name, etc.
            **{
                k: str(v) for k, v in allocated_ports.items()
            },  # Convert ports to strings
        }

        return self._attempt_start_with_ports(
            required_services,
            new_start_project_config,
            project_root,
            recreate,
            allocated_ports,
        )

        # Load project configuration using backtracking
        from ..config import ConfigManager

        config_manager = ConfigManager.create_with_backtrack()
        config = config_manager.load()

        # Convert config to dict for required services detection
        config_dict = {
            "embedding_provider": config.embedding_provider,
            "ollama": config.ollama.__dict__ if hasattr(config, "ollama") else {},
            "qdrant": config.qdrant.__dict__ if hasattr(config, "qdrant") else {},
        }

        # Determine required services based on configuration
        required_services = self.get_required_services(config_dict)
        self.console.print(f"🔍 Required services: {', '.join(required_services)}")

        # Get project root from config
        project_root = Path(config.codebase_dir)

        # Check if containers exist and try to reuse existing configuration (idempotent behavior)
        # CRITICAL: Only check for existing containers based on project root, not shared config
        if not recreate:
            project_config = None

            # Generate container names for this specific project only
            container_names = self._generate_container_names(project_root)

            # Check if containers with these names actually exist
            containers_exist = self.containers_exist(container_names)
            self.console.print(
                f"🔍 Checking for existing containers: {containers_exist}"
            )

            if containers_exist:
                # Extract actual ports from existing containers
                actual_ports = {}
                for service in required_services:
                    actual_port = self._get_actual_container_port(
                        service, container_names
                    )
                    if actual_port:
                        if service == "qdrant":
                            actual_ports["qdrant_port"] = str(actual_port)
                        elif service == "ollama":
                            actual_ports["ollama_port"] = str(actual_port)
                        elif service == "data-cleaner":
                            actual_ports["data_cleaner_port"] = str(actual_port)

                # Create complete project config with both names and ports
                project_config = container_names.copy()

                # Add extracted ports if available
                if actual_ports:
                    # Convert port values to strings for consistency
                    string_ports = {k: str(v) for k, v in actual_ports.items()}
                    project_config.update(string_ports)
                    self.console.print(
                        "🔍 Detected existing containers - reusing configuration"
                    )
                else:
                    self.console.print(
                        "🔍 Detected existing containers but couldn't extract ports - will check if running"
                    )

                # Ensure all required services have port configuration
                # Generate missing ports for services that need them but don't have ports
                missing_ports = {}
                for service in required_services:
                    port_key = f"{service.replace('-', '_')}_port"
                    if port_key not in project_config:
                        # Get ports from project registry (will allocate if missing)
                        all_ports = self.get_project_ports(project_root)
                        if port_key in all_ports:
                            missing_ports[port_key] = str(all_ports[port_key])
                            self.console.print(
                                f"🔧 Retrieved port for {service}: {all_ports[port_key]}"
                            )
                        else:
                            self.console.print(
                                f"⚠️  Could not retrieve port for {service}"
                            )

                if missing_ports:
                    project_config.update(missing_ports)

            # NEW LOGIC: If we have existing containers, check if they're already running
            # If they are, return success immediately (true idempotency)
            # If they're not, try to start them with existing ports
            if project_config:
                self.console.print(
                    "♻️  Using existing container configuration (idempotent behavior)"
                )

                # Check if containers are already running
                all_running = True
                for service in required_services:
                    try:
                        state = self.get_service_state(service, project_config)
                        if not (
                            state.get("exists", False)
                            and state.get("running", False)
                            and state.get("healthy", False)
                        ):
                            all_running = False
                            break
                    except Exception:
                        all_running = False
                        break

                if all_running:
                    # Update config with actual container ports to ensure synchronization
                    # This ensures config file matches actual running containers
                    if actual_ports:
                        extracted_ports = {k: int(v) for k, v in actual_ports.items()}
                        self._update_config_with_ports(project_root, extracted_ports)
                        self.console.print(
                            f"🔄 Updated config with actual container ports: {extracted_ports}"
                        )

                    self.console.print(
                        "✅ All required services are already running with existing configuration"
                    )
                    return True
                else:
                    # Some containers are not running, try to start them with extracted ports from running containers
                    # Use the ports we extracted from the actual running containers (actual_ports)
                    # instead of loading potentially stale config from file
                    extracted_ports = (
                        {k: int(v) for k, v in actual_ports.items()}
                        if actual_ports
                        else {}
                    )

                    return self._attempt_start_with_ports(
                        required_services,
                        project_config,
                        project_root,
                        recreate,
                        extracted_ports,
                    )

        # ===============================================================================
        # DYNAMIC PORT ALLOCATION SYSTEM - CRITICAL INFRASTRUCTURE
        # ===============================================================================
        # This system ensures each project gets unique, deterministic ports while
        # handling conflicts gracefully. The key principle: SAME PROJECT = SAME HASH = SAME PORTS
        #
        # Flow:
        # 1. Generate project hash ONCE (deterministic based on project path)
        # 2. Calculate ports from hash (same hash always = same ports)
        # 3. Handle conflicts by retrying with different available ports
        # 4. Update BOTH file config AND in-memory config with final ports
        # 5. Start containers with those exact ports
        # 6. Health checks use same in-memory ports -> guaranteed consistency
        # ===============================================================================

        # STEP 1: Generate project containers for this project only
        # Hash is deterministic: same project path = same hash = same base ports
        container_names = self._generate_container_names(project_root)
        self.console.print(
            f"📋 Project containers: {container_names['project_hash'][:8]}..."
        )

        # STEP 2: Smart port allocation with conflict detection and retry
        # Each retry uses the SAME project hash but finds different available ports
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.console.print(
                    f"🔌 Port allocation attempt {attempt + 1}/{max_retries}..."
                )

                # Allocate ports using global port registry
                # Registry ensures no conflicts and maintains project consistency
                allocated_ports = self.allocate_project_ports(project_root)

                # Create the merged project configuration with both containers and ports
                project_config = {
                    "qdrant_name": container_names["qdrant_name"],
                    "ollama_name": container_names["ollama_name"],
                    "data_cleaner_name": container_names["data_cleaner_name"],
                    "qdrant_port": str(allocated_ports["qdrant_port"]),
                    "data_cleaner_port": str(allocated_ports["data_cleaner_port"]),
                }

                # Only add ollama_port if it was allocated (VoyageAI doesn't need ollama)
                if "ollama_port" in allocated_ports:
                    project_config["ollama_port"] = str(allocated_ports["ollama_port"])

                # Create port allocation message
                port_info = [
                    f"Qdrant={project_config['qdrant_port']}",
                    f"DataCleaner={project_config['data_cleaner_port']}",
                ]
                if "ollama_port" in project_config:
                    port_info.insert(1, f"Ollama={project_config['ollama_port']}")

                self.console.print(f"🔌 Allocated ports: {', '.join(port_info)}")

                # Try to start services with these ports
                success = self._attempt_start_with_ports(
                    required_services, project_config, project_root, recreate
                )

                if success:
                    self.console.print(
                        "✅ Services started successfully with port configuration saved"
                    )
                    return True
                else:
                    self.console.print(
                        f"⚠️  Attempt {attempt + 1} failed, trying with different ports..."
                    )
                    continue

            except Exception as e:
                self.console.print(f"❌ Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                continue

        raise RuntimeError(
            f"Failed to start services after {max_retries} attempts due to port conflicts"
        )

        # Check current state of all required services
        service_states = {}
        for service in required_services:
            service_states[service] = self.get_service_state(service, project_config)
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
            or not self.compose_file.exists()
            or not all(state["up_to_date"] for state in service_states.values())
        )

        if needs_compose_update:
            self.console.print("📝 Updating Docker Compose configuration...")
            # Get project root from current working directory
            project_root = Path.cwd()
            compose_config = self.generate_compose_config(
                project_root=project_root, project_config=project_config
            )
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
                    try:
                        # Get project configuration from config manager
                        from ..config import ConfigManager

                        config_manager = ConfigManager.create_with_backtrack()
                        project_config = config_manager.load()

                        # Get container configuration if available
                        if (
                            hasattr(project_config, "project_containers")
                            and project_config.project_containers
                            and project_config.project_containers.project_hash  # Ensure it's not empty
                        ):
                            container_name = self.get_container_name(
                                service, project_config.project_containers
                            )
                        else:
                            # Generate project configuration from current working directory
                            from pathlib import Path

                            project_root = Path.cwd()
                            project_container_names = self._generate_container_names(
                                project_root
                            )
                            container_name = project_container_names.get(
                                f"{service.replace('-', '_')}_name",
                                f"unknown-{service}",
                            )
                    except Exception:
                        # Generate project configuration from current working directory as fallback
                        from pathlib import Path

                        project_root = Path.cwd()
                        project_container_names = self._generate_container_names(
                            project_root
                        )
                        container_name = project_container_names.get(
                            f"{service.replace('-', '_')}_name", f"unknown-{service}"
                        )
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
        """Stop Docker services using project-specific container names with enhanced timeout handling."""
        try:
            # Get project configuration from config manager
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            project_config = config_manager.load()

            # Get container configuration if available
            if (
                hasattr(project_config, "project_containers")
                and project_config.project_containers
                and project_config.project_containers.project_hash  # Ensure it's not empty
            ):
                project_containers = project_config.project_containers
                expected_containers = [
                    getattr(project_containers, "qdrant_name", "unknown"),
                    getattr(project_containers, "ollama_name", "unknown"),
                    getattr(project_containers, "data_cleaner_name", "unknown"),
                ]
            else:
                # Generate project configuration from current working directory
                from pathlib import Path

                project_root = Path.cwd()
                project_container_names = self._generate_container_names(project_root)
                expected_containers = [
                    project_container_names.get("qdrant_name", "unknown"),
                    project_container_names.get("ollama_name", "unknown"),
                    project_container_names.get("data_cleaner_name", "unknown"),
                ]
        except Exception:
            # Generate project configuration from current working directory
            from pathlib import Path

            project_root = Path.cwd()
            project_container_names = self._generate_container_names(project_root)
            expected_containers = [
                project_container_names.get("qdrant_name", "unknown"),
                project_container_names.get("ollama_name", "unknown"),
                project_container_names.get("data_cleaner_name", "unknown"),
            ]

        # Determine runtime: use same logic as compose command selection
        runtime = self._get_preferred_runtime()

        stopped_count = 0
        errors = []

        try:
            with self.console.status("Stopping services..."):
                for container_name in expected_containers:
                    if self._smart_stop_container(runtime, container_name):
                        stopped_count += 1
                    else:
                        errors.append(f"{container_name}: failed to stop gracefully")

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

    def _smart_stop_container(self, runtime: str, container_name: str) -> bool:
        """Smart container stop with progressive timeout handling and forced removal.

        Args:
            runtime: Docker/Podman runtime command
            container_name: Name of container to stop

        Returns:
            True if container was stopped successfully
        """
        import time

        try:
            # Check if container exists and is running
            inspect_result = subprocess.run(
                [runtime, "inspect", container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if inspect_result.returncode != 0:
                # Container doesn't exist - consider it stopped
                return True

            # Try graceful stop first (30 seconds)
            try:
                result = subprocess.run(
                    [runtime, "stop", container_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    return True

                # Check if it's already stopped
                if "no such container" in result.stderr.lower():
                    return True

            except subprocess.TimeoutExpired:
                pass  # Continue to force kill

            # For Qdrant specifically, check if it's doing background work
            if "qdrant" in container_name:
                if self._wait_for_qdrant_idle(runtime, container_name, max_wait=30):
                    # Try graceful stop again after Qdrant is idle
                    try:
                        result = subprocess.run(
                            [runtime, "stop", container_name],
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        if result.returncode == 0:
                            return True
                    except subprocess.TimeoutExpired:
                        pass

            # Force kill if graceful stop failed
            try:
                result = subprocess.run(
                    [runtime, "kill", container_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if (
                    result.returncode == 0
                    or "no such container" in result.stderr.lower()
                ):
                    # Wait a moment for cleanup
                    time.sleep(1)
                    return True

            except subprocess.TimeoutExpired:
                pass

            # Force remove if kill failed
            try:
                result = subprocess.run(
                    [runtime, "rm", "-f", container_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if (
                    result.returncode == 0
                    or "no such container" in result.stderr.lower()
                ):
                    return True

            except subprocess.TimeoutExpired:
                pass

            return False

        except Exception:
            # Last resort: try force remove
            try:
                subprocess.run(
                    [runtime, "rm", "-f", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return True
            except Exception:
                return False

    def _wait_for_qdrant_idle(
        self, runtime: str, container_name: str, max_wait: int = 30
    ) -> bool:
        """Wait for Qdrant to finish background operations before stopping.

        Args:
            runtime: Docker/Podman runtime command
            container_name: Qdrant container name
            max_wait: Maximum time to wait in seconds

        Returns:
            True if Qdrant appears idle or max_wait exceeded
        """
        import time

        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                # Check container logs for activity indicators
                result = subprocess.run(
                    [runtime, "logs", "--tail", "10", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    recent_logs = result.stdout.lower()

                    # Look for signs Qdrant is busy
                    busy_indicators = [
                        "indexing",
                        "optimization",
                        "writing",
                        "syncing",
                        "compacting",
                        "processing",
                    ]

                    if not any(
                        indicator in recent_logs for indicator in busy_indicators
                    ):
                        return True

                time.sleep(2)

            except subprocess.TimeoutExpired:
                break
            except Exception:
                break

        return True  # Return True after max_wait to proceed with stop

    def _force_remove_problematic_containers(self) -> None:
        """Force remove any problematic containers that might interfere with startup."""
        try:
            # Get project configuration from config manager
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            project_config = config_manager.load()

            # Get container configuration if available
            if (
                hasattr(project_config, "project_containers")
                and project_config.project_containers
            ):
                project_containers = project_config.project_containers
                expected_containers = [
                    getattr(project_containers, "qdrant_name", "unknown"),
                    getattr(project_containers, "ollama_name", "unknown"),
                    getattr(project_containers, "data_cleaner_name", "unknown"),
                ]
            else:
                expected_containers = [
                    "unknown-qdrant",
                    "unknown-ollama",
                    "unknown-data-cleaner",
                ]
        except Exception:
            expected_containers = [
                "unknown-qdrant",
                "unknown-ollama",
                "unknown-data-cleaner",
            ]

        runtime = self._get_preferred_runtime()

        for container_name in expected_containers:
            try:
                # Check if container exists
                inspect_result = subprocess.run(
                    [runtime, "inspect", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if inspect_result.returncode == 0:
                    # Container exists, check if it's in a problematic state
                    try:
                        # Try to get container status
                        ps_result = subprocess.run(
                            [
                                runtime,
                                "ps",
                                "-a",
                                "--filter",
                                f"name={container_name}",
                                "--format",
                                "{{{{.Status}}}}",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )

                        if ps_result.returncode == 0:
                            status = ps_result.stdout.strip().lower()

                            # Check for problematic states
                            problematic_states = [
                                "restarting",
                                "dead",
                                "removing",
                                "oomkilled",
                                "exited (",  # Any exit status
                            ]

                            is_problematic = any(
                                state in status for state in problematic_states
                            )

                            if is_problematic:
                                self.console.print(
                                    f"🧹 Removing problematic container {container_name} (status: {status})"
                                )

                                # Force remove
                                subprocess.run(
                                    [runtime, "rm", "-f", container_name],
                                    capture_output=True,
                                    text=True,
                                    timeout=10,
                                )

                    except subprocess.TimeoutExpired:
                        # If we can't check status, remove it to be safe
                        self.console.print(
                            f"🧹 Removing unresponsive container {container_name}"
                        )
                        subprocess.run(
                            [runtime, "rm", "-f", container_name],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )

            except Exception:
                # If anything fails, try to remove anyway
                try:
                    subprocess.run(
                        [runtime, "rm", "-f", container_name],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                except Exception:
                    pass  # Ignore final cleanup failures

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

            qdrant_client = QdrantClient(
                config.qdrant, self.console, Path(config.codebase_dir)
            )

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

            # Clean up corrupted WAL files that may prevent container startup
            self._cleanup_wal_files(config_manager)

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
        required_services = self.get_required_services()

        # Generate project configuration
        try:
            # Get project configuration from config manager
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            project_config = config_manager.load()

            # Get container configuration if available
            if (
                hasattr(project_config, "project_containers")
                and project_config.project_containers
                and project_config.project_containers.project_hash  # Ensure it's not empty
            ):
                # Convert ProjectContainersConfig to Dict[str, str]
                project_containers = project_config.project_containers.__dict__
            else:
                # Generate project configuration from current working directory
                from pathlib import Path

                project_root = Path.cwd()
                project_containers = self._generate_container_names(project_root)
        except Exception:
            # Generate project configuration from current working directory
            from pathlib import Path

            project_root = Path.cwd()
            project_containers = self._generate_container_names(project_root)

        expected_containers = [
            self.get_container_name(service, project_containers)
            for service in required_services
        ]

        # Check both runtimes to find where containers are actually running
        runtimes_to_check = (
            ["docker", "podman"] if not self.force_docker else ["docker"]
        )

        for container_name in expected_containers:
            best_status = None

            # Check all runtimes and pick the best status (prioritize running containers)
            for runtime in runtimes_to_check:
                try:
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
                        timeout=1,  # Quick timeout for status checks
                    )

                    if result.returncode == 0:
                        output = result.stdout.strip()
                        parts = output.split("|")
                        # Clean up state - podman sometimes includes extra text like "< /dev/null"
                        raw_state = parts[0].strip() if len(parts) > 0 else "unknown"
                        state = (
                            raw_state.split()[0] if raw_state else "unknown"
                        )  # Take first word only
                        # Clean up health status
                        raw_health = parts[1].strip() if len(parts) > 1 else "unknown"
                        health = (
                            raw_health.split()[0]
                            if raw_health and raw_health != "<no value>"
                            else "unknown"
                        )

                        current_status = {
                            "state": state,
                            "health": health,
                        }

                        # Prioritize running containers over stopped ones
                        if best_status is None or (
                            state == "running" and best_status["state"] != "running"
                        ):
                            best_status = current_status

                        # If we got a successful result, don't try other runtimes
                        break

                except Exception:
                    continue  # Try next runtime

            # Use best status found, or mark as not found
            if best_status is not None:
                services[container_name] = best_status
            else:
                services[container_name] = {
                    "state": "not_found",
                    "health": "unknown",
                }

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

    def get_adaptive_timeout(
        self,
        project_config: Dict[str, str],
        required_services: List[str],
        default_timeout: int = 180,
    ) -> int:
        """Get adaptive timeout based on whether containers and models exist."""
        # Check if containers exist
        containers_exist = self._check_containers_exist(
            project_config, required_services
        )

        # Check if Ollama model exists (only if ollama is required)
        model_exists = (
            "ollama" in required_services and self._check_ollama_model_exists()
        )

        # If both containers and model exist, use reasonable timeout for collection recovery
        if containers_exist and ("ollama" not in required_services or model_exists):
            adaptive_timeout = 120  # Allow time for collection recovery
            self.console.print("🚀 Containers ready, using recovery timeout (120s)")
            return adaptive_timeout
        elif containers_exist:
            adaptive_timeout = 120  # Allow time for container setup and recovery
            self.console.print(
                "📦 Containers exist but may need setup, using recovery timeout (120s)"
            )
            return adaptive_timeout
        else:
            # First time setup or containers missing
            self.console.print(
                f"⏰ Full setup required, using default timeout ({default_timeout}s)"
            )
            return default_timeout

    def _check_containers_exist(
        self, project_config: Dict[str, str], required_services: List[str]
    ) -> bool:
        """Check if required service containers exist."""
        import subprocess

        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")
        container_names = [
            self.get_container_name(service, project_config)
            for service in required_services
            if service in ["ollama", "qdrant", "data-cleaner"]
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
            try:
                # Get project configuration from config manager
                from ..config import ConfigManager

                config_manager = ConfigManager.create_with_backtrack()
                project_config = config_manager.load()

                # Get container configuration if available
                if (
                    hasattr(project_config, "project_containers")
                    and project_config.project_containers
                ):
                    project_containers = project_config.project_containers
                    qdrant_container_name = getattr(
                        project_containers, "qdrant_name", "unknown"
                    )
                else:
                    qdrant_container_name = "unknown-qdrant"
            except Exception:
                qdrant_container_name = "unknown-qdrant"
            result = subprocess.run(
                ["docker", "logs", "--tail", "50", qdrant_container_name],
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

    def wait_for_services(
        self,
        timeout: int = 180,
        retry_interval: int = 2,
        project_config: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Wait for services to be healthy using retry logic with exponential backoff and intelligent Qdrant monitoring."""
        import requests  # type: ignore

        # Get list of required services dynamically
        required_services = self.get_required_services()

        # Use provided project_config or try to get from project config as fallback
        if project_config is None:
            try:
                # Get project configuration from config manager
                from ..config import ConfigManager

                config_manager = ConfigManager.create_with_backtrack()
                config = config_manager.load()

                # Get container configuration if available
                if hasattr(config, "project_containers") and config.project_containers:
                    project_config = config.project_containers
                else:
                    # Generate project configuration from current working directory
                    from pathlib import Path

                    project_root = Path.cwd()
                    project_config = self._generate_container_names(project_root)
            except Exception:
                raise ValueError(
                    "Project configuration is required. Run project setup first."
                )

        if not project_config:
            raise ValueError(
                "Project containers not configured. Run project setup first."
            )

        # Use adaptive timeout if default timeout is requested
        if timeout == 180:  # Default timeout
            timeout = self.get_adaptive_timeout(
                project_config, required_services, timeout
            )

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
                    # Check data-cleaner service with HTTP health check using project-specific port
                    try:
                        data_cleaner_url = self._get_service_url("data-cleaner")
                        response = requests.get(f"{data_cleaner_url}/", timeout=5)
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
                logs = self.get_container_logs(service, project_config, lines=10)
                if logs.strip():
                    self.console.print(
                        f"\n{service} container logs (last 10 lines):", style="red"
                    )
                    self.console.print(logs, style="dim")

        return False

    def get_container_logs(
        self,
        service: str,
        project_config: Dict[str, str],
        lines: int = 50,
    ) -> str:
        """Get recent container logs for debugging startup issues."""
        import subprocess

        container_name = self.get_container_name(service, project_config)

        # Detect container engine (podman or docker)
        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")

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

    def get_container_name(self, service: str, project_config) -> str:
        """Get the project-specific container name for a given service."""
        # Handle both dictionary and Pydantic object inputs
        if hasattr(project_config, "__dict__"):  # Pydantic object
            service_name_map = {
                "qdrant": getattr(project_config, "qdrant_name", None),
                "ollama": getattr(project_config, "ollama_name", None),
                "data-cleaner": getattr(project_config, "data_cleaner_name", None),
            }
        else:  # Dictionary
            service_name_map = {
                "qdrant": project_config.get("qdrant_name"),
                "ollama": project_config.get("ollama_name"),
                "data-cleaner": project_config.get("data_cleaner_name"),
            }

        if service not in service_name_map:
            raise ValueError(f"Unknown service: {service}")

        container_name = service_name_map[service]
        if not container_name:
            raise ValueError(f"No container name configured for service: {service}")

        return str(container_name)

    def get_network_name(self) -> str:
        """Get the project-specific network name."""
        try:
            # Get project configuration from config manager
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            project_config = config_manager.load()

            # Get container configuration if available
            if (
                hasattr(project_config, "project_containers")
                and project_config.project_containers
            ):
                project_hash = getattr(
                    project_config.project_containers, "project_hash", "unknown"
                )
            else:
                # Generate project hash from current working directory
                from pathlib import Path

                project_root = Path.cwd()
                project_hash = self.port_registry._calculate_project_hash(project_root)
        except Exception:
            project_hash = "unknown"

        return f"cidx-{project_hash}-network"

    def get_network_config(self) -> Dict[str, Any]:
        """
        Generate network configuration with explicit subnet assignment to prevent Docker subnet exhaustion.

        Uses project hash to calculate deterministic subnet in private IP ranges.
        Supports both Docker and Podman with explicit IPAM configuration.

        Returns:
            Dict containing network configuration with explicit subnet assignment
        """
        network_name = self.get_network_name()

        try:
            # Extract project hash from network name
            project_hash = network_name.split("-")[1]  # cidx-{hash}-network

            # Convert first 4 characters of hash to integer for subnet calculation
            # This ensures deterministic, unique subnets per project
            subnet_id = int(project_hash[:4], 16) % 4000  # 0-3999 range

            # Calculate subnet in 172.16-83.x.x range (avoiding Docker defaults)
            # Docker typically uses 172.17-31.x.x, so we use 172.16.x.x and 172.32+
            base_second_octet = 16 + (subnet_id // 256)  # 16-31 range
            base_third_octet = subnet_id % 256  # 0-255 range

            # Ensure we don't conflict with common Docker ranges
            if base_second_octet >= 17 and base_second_octet <= 31:
                base_second_octet += 16  # Move to 32-47 range

            subnet = f"172.{base_second_octet}.{base_third_octet}.0/24"
            gateway = f"172.{base_second_octet}.{base_third_octet}.1"

            return {
                network_name: {
                    "name": network_name,
                    "driver": "bridge",
                    "ipam": {
                        "driver": "default",
                        "config": [{"subnet": subnet, "gateway": gateway}],
                    },
                }
            }

        except (ValueError, IndexError, Exception) as e:
            # Fallback to simple network configuration if hash calculation fails
            logging.warning(
                f"Failed to calculate explicit subnet for {network_name}, using default: {e}"
            )
            return {network_name: {"name": network_name, "driver": "bridge"}}

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

        # Return status using project-specific container names
        try:
            # Get project configuration from config manager
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            project_config = config_manager.load()

            # Get container configuration if available
            if (
                hasattr(project_config, "project_containers")
                and project_config.project_containers
            ):
                project_containers = project_config.project_containers
                ollama_name = getattr(project_containers, "ollama_name", "unknown")
                qdrant_name = getattr(project_containers, "qdrant_name", "unknown")
            else:
                ollama_name = "unknown"
                qdrant_name = "unknown"
        except Exception:
            ollama_name = "unknown"
            qdrant_name = "unknown"

        return {
            "ollama": {
                "running": ollama_running,
                "name": ollama_name,
            },
            "qdrant": {
                "running": qdrant_running,
                "name": qdrant_name,
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

        # Enhanced status tracking for comprehensive reporting
        status_tracker = {
            "container_orchestration": {"success": True, "error": ""},
            "data_cleaner": {"success": True, "error": ""},
            "container_removal": {"success": True, "error": ""},
            "data_directory_cleanup": {"success": True, "error": ""},
            "named_volume_cleanup": {"success": True, "error": ""},
            "cleanup_validation": {"success": True, "error": ""},
        }

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
                # Future-proof cleanup: blast entire contents of mounted directories
                cleanup_paths = [
                    "/data/ollama/*",  # All Ollama data
                    "/qdrant/*",  # ALL Qdrant files and directories
                ]

                # Load project configuration for data-cleaner identification
                try:
                    from ..config import ConfigManager

                    config_manager = ConfigManager.create_with_backtrack()
                    project_config = config_manager.load()

                    # Convert to dict format expected by clean_with_data_cleaner
                    if (
                        hasattr(project_config, "project_containers")
                        and project_config.project_containers
                    ):
                        project_config_dict = {
                            "qdrant_name": str(
                                project_config.project_containers.qdrant_name or ""
                            ),
                            "data_cleaner_name": str(
                                project_config.project_containers.data_cleaner_name
                                or ""
                            ),
                            "ollama_name": str(
                                getattr(
                                    project_config.project_containers, "ollama_name", ""
                                )
                                or ""
                            ),
                        }
                        if (
                            hasattr(project_config, "project_ports")
                            and project_config.project_ports
                        ):
                            project_config_dict.update(
                                {
                                    "qdrant_port": str(
                                        project_config.project_ports.qdrant_port
                                    ),
                                    "data_cleaner_port": str(
                                        project_config.project_ports.data_cleaner_port
                                    ),
                                    "ollama_port": str(
                                        getattr(
                                            project_config.project_ports,
                                            "ollama_port",
                                            "",
                                        )
                                    ),
                                }
                            )

                    else:
                        project_config_dict = None
                except Exception as e:
                    if verbose:
                        self.console.print(
                            f"⚠️  Could not load project config for data-cleaner: {e}",
                            style="yellow",
                        )
                    project_config_dict = None

                # Run data cleaner and track success
                cleaner_success = self.clean_with_data_cleaner(
                    cleanup_paths, project_config_dict
                )
                if not cleaner_success:
                    status_tracker["data_cleaner"]["success"] = False
                    status_tracker["data_cleaner"][
                        "error"
                    ] = "Data cleaner reported failures"
                    if verbose:
                        self.console.print(
                            "⚠️  Data cleaner reported some failures", style="yellow"
                        )
                    cleanup_success = False

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
                down_cmd.extend(["-v", "--remove-orphans"])
            if force:
                down_cmd.extend(["--timeout", "10"])

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
                    status_tracker["container_removal"]["success"] = False
                    status_tracker["container_removal"]["error"] = result.stderr
                    cleanup_success = False
                    if verbose:
                        self.console.print(
                            f"❌ Container removal failed: {result.stderr}", style="red"
                        )
                        # Provide specific guidance based on error type
                        if (
                            "network" in result.stderr.lower()
                            and "in use" in result.stderr.lower()
                        ):
                            runtime_engine = self._get_available_runtime() or "podman"
                            network_name = (
                                self.get_network_name()
                            )  # Get project-scoped network name
                            self.console.print(
                                f"💡 Manual network cleanup: {runtime_engine} network rm {network_name} --force",
                                style="blue",
                            )
                        elif "permission denied" in result.stderr.lower():
                            self.console.print(
                                "💡 Try running with sudo or check container engine permissions",
                                style="blue",
                            )
                        elif "device busy" in result.stderr.lower():
                            self.console.print(
                                "💡 Wait a moment and retry, or manually stop containers first",
                                style="blue",
                            )

            # MANDATORY: Always force cleanup for uninstall (remove_data=True)
            # This ensures containers are removed regardless of docker-compose down results
            if remove_data:
                if verbose:
                    self.console.print(
                        "🔧 Running mandatory force cleanup for uninstall..."
                    )
                cleanup_success &= self._force_cleanup_containers(verbose)

            # Step 4: Handle data removal ONLY when explicitly requested
            if remove_data:
                if verbose:
                    self.console.print("🗂️  Removing data volumes and directories...")

                # Clean up named volumes (new approach)
                volumes_success = self._cleanup_named_volumes(verbose)
                if not volumes_success:
                    status_tracker["named_volume_cleanup"]["success"] = False
                    status_tracker["named_volume_cleanup"][
                        "error"
                    ] = "Named volume cleanup failed"
                cleanup_success &= volumes_success

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
                    # Wait for containers to stop and ports to be released (PROJECT-SCOPED)
                    container_engine = self._get_available_runtime()
                    if not container_engine:
                        raise RuntimeError("Neither podman nor docker is available")

                    # Get project hash for current project to ensure project-scoped operations
                    project_root = Path.cwd()
                    project_hash = self.port_registry._calculate_project_hash(
                        project_root
                    )

                    # Find only containers for CURRENT PROJECT using project hash filtering
                    list_cmd = [
                        container_engine,
                        "ps",
                        "-a",
                        "--format",
                        "{{.Names}}",
                        "--filter",
                        f"name=cidx-{project_hash}-",  # PROJECT-SCOPED: Only current project
                    ]
                    try:
                        list_result = subprocess.run(
                            list_cmd, capture_output=True, text=True, timeout=10
                        )
                        if list_result.returncode == 0:
                            # Already filtered by project hash, just parse the names
                            container_names = [
                                name.strip()
                                for name in list_result.stdout.strip().split("\n")
                                if name.strip()
                                and name.strip().startswith(f"cidx-{project_hash}-")
                            ]
                        else:
                            container_names = []
                    except Exception:
                        container_names = []
                    # For general cleanup, we only validate container removal, not specific ports
                    # since different projects use different port ranges
                    validation_success = (
                        self.health_checker.wait_for_containers_stopped(
                            container_names=container_names,
                            container_engine=container_engine,
                            timeout=None,  # Use engine-optimized timeout
                        )
                    )

                    if not validation_success and verbose:
                        self.console.print(
                            "⚠️  Cleanup validation timed out, continuing anyway...",
                            style="yellow",
                        )

                    # Comprehensive cleanup validation for uninstall operations
                    if remove_data:  # Only for uninstall operations
                        complete_validation_success = self._validate_complete_cleanup(
                            verbose
                        )
                        if verbose and not complete_validation_success:
                            self.console.print(
                                "⚠️  Complete cleanup validation failed - some cidx containers may still exist",
                                style="yellow",
                            )
                        validation_success = (
                            validation_success and complete_validation_success
                        )

                if not validation_success:
                    status_tracker["cleanup_validation"]["success"] = False
                    status_tracker["cleanup_validation"][
                        "error"
                    ] = "Cleanup validation failed"
                cleanup_success &= validation_success

            # Enhanced status summary reporting for verbose mode
            if verbose:
                self._provide_comprehensive_status_summary(
                    status_tracker, cleanup_success
                )

            # Enhanced actionable guidance for failed cleanups
            if not cleanup_success and verbose:
                self._provide_actionable_cleanup_guidance(status_tracker)

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

    def cleanup_with_final_guidance(
        self,
        remove_data: bool = False,
        force: bool = False,
        verbose: bool = False,
        validate: bool = False,
    ) -> bool:
        """Enhanced cleanup with comprehensive final status reporting and manual guidance.

        This method extends the regular cleanup with detailed status tracking and
        provides actionable guidance for manual cleanup when automated cleanup fails.
        """
        # Track specific operation results
        operation_results = {
            "Container removal": False,
            "Volume cleanup": False,
            "Final validation": False,
        }

        # Perform individual operations to track their results
        try:
            # Container cleanup
            operation_results["Container removal"] = self._force_cleanup_containers(
                verbose
            )

            # Volume cleanup
            operation_results["Volume cleanup"] = self._cleanup_named_volumes(verbose)

            # Final validation
            if validate:
                operation_results["Final validation"] = self._validate_complete_cleanup(
                    verbose
                )
            else:
                operation_results["Final validation"] = True  # Skip validation

        except Exception as e:
            if verbose:
                self.console.print(
                    f"❌ Error during cleanup operations: {e}", style="red"
                )
            return False

        # Determine overall success
        overall_success = all(operation_results.values())

        # Provide comprehensive final status summary
        if verbose:
            self.console.print("📋 Final Cleanup Status Summary:", style="bold")

            # Report individual operation status
            for operation, success in operation_results.items():
                status_icon = "✅" if success else "❌"
                status_text = "SUCCESS" if success else "FAILED"
                self.console.print(f"{status_icon} {operation}: {status_text}")

            # Provide manual cleanup guidance if needed (PROJECT-SCOPED)
            if not overall_success:
                self.console.print(
                    "🔧 Manual cleanup may be required. Try these commands (Current Project Only):",
                    style="yellow",
                )

                # Get the container engine and project hash for the commands
                container_engine = self._get_available_runtime()
                engine_name = container_engine or "docker"
                project_root = Path.cwd()
                project_hash = self.port_registry._calculate_project_hash(project_root)

                self.console.print(
                    f"   {engine_name} ps -a | grep cidx-{project_hash}- | awk '{{print $1}}' | xargs {engine_name} rm -f"
                )
                self.console.print(
                    f"   {engine_name} volume ls | grep cidx-{project_hash}- | awk '{{print $2}}' | xargs {engine_name} volume rm"
                )

        return overall_success

    def _provide_comprehensive_status_summary(
        self, status_tracker: dict, overall_success: bool
    ) -> None:
        """Provide comprehensive status summary for cleanup operations."""
        self.console.print("📊 Cleanup Status Summary:", style="cyan")

        for operation, status in status_tracker.items():
            operation_name = operation.replace("_", " ").title()
            if status["success"]:
                self.console.print(f"  ✅ {operation_name}: Success", style="green")
            else:
                error_detail = f" - {status['error']}" if status["error"] else ""
                self.console.print(
                    f"  ❌ {operation_name}: Failed{error_detail}", style="red"
                )

    def _provide_actionable_cleanup_guidance(self, status_tracker: dict) -> None:
        """Provide actionable guidance when cleanup fails.

        CRITICAL: Uses project hash-based filtering to prevent cross-project operations.
        """
        container_engine = self._get_available_runtime() or "podman"

        # Get project hash for current project to ensure project-scoped guidance
        project_root = Path.cwd()
        project_hash = self.port_registry._calculate_project_hash(project_root)

        self.console.print(
            "🔧 Manual Cleanup Required (Current Project Only):", style="yellow"
        )
        self.console.print(
            f"1. Check for remaining containers: {container_engine} ps -a --filter name=cidx-{project_hash}-"
        )
        self.console.print(
            f"2. Manually remove containers: {container_engine} rm -f <container-name>"
        )
        self.console.print(
            f"3. Check for remaining volumes: {container_engine} volume ls --filter name=cidx-{project_hash}-"
        )
        self.console.print(
            f"4. Manually remove volumes: {container_engine} volume rm <volume-name>"
        )
        self.console.print(
            "5. Check for root-owned files: sudo find .code-indexer -user root"
        )
        self.console.print("6. Remove root files: sudo rm -rf .code-indexer/qdrant/")

    def _force_cleanup_containers(self, verbose: bool = False) -> bool:
        """Force cleanup containers for CURRENT PROJECT ONLY using comprehensive discovery.

        Uses project hash-based discovery to find ALL containers belonging to current project,
        not just the 3 predefined ones (qdrant, ollama, data-cleaner).
        Enhanced to handle ALL container states (Created, Running, Exited, Paused)
        and SCOPED to only affect containers belonging to the current project.
        """
        import subprocess

        success = True
        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")

        # Get project hash for comprehensive container discovery
        try:
            # Get project configuration to determine project hash
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            project_config = config_manager.load()

            # Determine project hash for comprehensive discovery
            if (
                hasattr(project_config, "project_containers")
                and project_config.project_containers
                and project_config.project_containers.project_hash  # Ensure it's not empty
            ):
                project_hash = project_config.project_containers.project_hash
            else:
                # Generate project hash from current working directory
                from pathlib import Path

                project_root = Path.cwd()
                project_hash = self.port_registry._calculate_project_hash(project_root)

            if verbose:
                self.console.print(
                    f"🎯 Discovering ALL containers for project hash: {project_hash}"
                )

        except Exception as e:
            if verbose:
                self.console.print(
                    f"❌ Error getting project configuration: {e}", style="red"
                )
            return False

        # Comprehensive discovery: Find ALL containers with current project hash pattern
        try:
            # Single discovery call to find all containers with project hash pattern
            discover_cmd = [
                container_engine,
                "ps",
                "-a",
                "--format",
                "{{.Names}}\t{{.State}}",
                "--filter",
                f"name=cidx-{project_hash}-",  # Match all containers with project hash
            ]
            result = subprocess.run(
                discover_cmd, capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                if verbose:
                    self.console.print(
                        f"❌ Failed to discover containers: {result.stderr}",
                        style="red",
                    )
                return False

            # Parse discovered containers
            container_info = []
            if result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    if line.strip() and "\t" in line:
                        parts = line.strip().split("\t")
                        if len(parts) >= 2:
                            container_name = parts[0]
                            container_state = parts[1]
                            # Verify container matches our project hash pattern (double-check)
                            if container_name.startswith(f"cidx-{project_hash}-"):
                                container_info.append((container_name, container_state))
                    elif line.strip() and line.strip().startswith(
                        f"cidx-{project_hash}-"
                    ):
                        # Fallback for lines without state info
                        container_info.append((line.strip(), "unknown"))

            if not container_info:
                if verbose:
                    self.console.print("ℹ️  No project containers found to cleanup")
                return True  # Success - nothing to clean up

            if verbose:
                self.console.print("🔍 Discovered project containers for cleanup:")
                for name, state in container_info:
                    self.console.print(f"  - {name} (state: {state})")
                self.console.print(
                    "🛑 Stopping and removing ALL discovered project containers..."
                )

            # Extract container names for processing
            container_names = [name for name, state in container_info]

        except Exception as e:
            if verbose:
                self.console.print(
                    f"❌ Error during container discovery: {e}", style="red"
                )
            return False

        # Process each container with comprehensive state handling
        for container_name in container_names:
            container_removed = False
            try:
                # Always attempt to kill first (handles Running/Paused states)
                # For Created/Exited states, kill will fail but that's expected
                try:
                    kill_result = subprocess.run(
                        [container_engine, "kill", container_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    # Enhanced error reporting for kill failures
                    if kill_result.returncode != 0 and verbose:
                        # Only report as error if it's not a benign "container not running" case
                        if (
                            "not running" not in kill_result.stderr.lower()
                            and "no such container" not in kill_result.stderr.lower()
                        ):
                            self.console.print(
                                f"❌ Failed to kill container {container_name}: {kill_result.stderr}",
                                style="red",
                            )
                except subprocess.TimeoutExpired:
                    # Handle timeout gracefully, continue to removal
                    if verbose:
                        self.console.print(
                            f"⚠️  Kill timeout for {container_name}, continuing to removal"
                        )

                # Force remove regardless of kill result (handles ALL states)
                try:
                    rm_result = subprocess.run(
                        [container_engine, "rm", "-f", container_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if rm_result.returncode == 0:
                        container_removed = True
                        if verbose:
                            self.console.print(
                                f"✅ Removed container: {container_name}"
                            )
                    else:
                        # Enhanced error reporting for remove failures
                        if verbose:
                            self.console.print(
                                f"❌ Failed to remove container {container_name}: {rm_result.stderr}",
                                style="red",
                            )

                except subprocess.TimeoutExpired:
                    # Handle removal timeout
                    success = False
                    if verbose:
                        self.console.print(f"❌ Removal timeout for {container_name}")

            except Exception as e:
                success = False
                if verbose:
                    self.console.print(
                        f"❌ Failed to remove {container_name}: {e}", style="red"
                    )

            # Track overall success - if any container fails to be removed completely
            if not container_removed:
                success = False

        return success

    def _force_cleanup_containers_with_guidance(self, verbose: bool = False) -> bool:
        """Force cleanup containers with enhanced error categorization and recovery guidance.

        This method extends the standard force cleanup with intelligent error analysis
        and actionable recovery suggestions based on error patterns.

        CRITICAL: Uses project hash-based filtering to prevent cross-project operations.
        """
        import subprocess

        success = True
        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")

        # Get project hash for current project to ensure project-scoped operations
        project_root = Path.cwd()
        project_hash = self.port_registry._calculate_project_hash(project_root)

        # Find ALL containers for CURRENT PROJECT ONLY using project hash filtering
        try:
            list_cmd = [
                container_engine,
                "ps",
                "-a",
                "--format",
                "{{.Names}}",
                "--filter",
                f"name=cidx-{project_hash}-",  # PROJECT-SCOPED: Only current project
            ]
            result = subprocess.run(
                list_cmd, capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                error_message = result.stderr.strip()
                if verbose:
                    self.console.print(
                        f"❌ Failed to list containers: {error_message}", style="red"
                    )
                    # Provide categorized guidance based on error type
                    self._provide_error_guidance(
                        error_message, "container_listing", verbose
                    )
                return False

            # Parse container names - already filtered by project hash
            container_names = [
                name.strip()
                for name in result.stdout.strip().split("\n")
                if name.strip() and name.strip().startswith(f"cidx-{project_hash}-")
            ]

            if verbose and container_names:
                self.console.print(f"🔍 Found project containers: {container_names}")

        except Exception as e:
            if verbose:
                self.console.print(f"❌ Error listing containers: {e}", style="red")
                self._provide_error_guidance(str(e), "general_error", verbose)
            return False

        # Process each container with comprehensive state handling
        for container_name in container_names:
            container_removed = False
            try:
                # Always attempt to kill first (handles Running/Paused states)
                # For Created/Exited states, kill will fail but that's expected
                try:
                    kill_result = subprocess.run(
                        [container_engine, "kill", container_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    # Check if kill failed with specific errors
                    if (
                        kill_result.returncode != 0
                        and "permission denied" in kill_result.stderr.lower()
                    ):
                        if verbose:
                            self._provide_error_guidance(
                                kill_result.stderr, "permission_denied", verbose
                            )
                    # Don't fail if kill doesn't work - continue to removal
                except subprocess.TimeoutExpired:
                    # Handle timeout gracefully, continue to removal
                    if verbose:
                        self.console.print(
                            f"⚠️  Kill timeout for {container_name}, continuing to removal"
                        )

                # Force remove regardless of kill result (handles ALL states)
                try:
                    rm_result = subprocess.run(
                        [container_engine, "rm", "-f", container_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if rm_result.returncode == 0:
                        container_removed = True
                        if verbose:
                            self.console.print(
                                f"✅ Removed container: {container_name}"
                            )
                    else:
                        if verbose:
                            self.console.print(
                                f"⚠️  Container removal warning for {container_name}: {rm_result.stderr}"
                            )
                            # Provide specific guidance based on removal error
                            self._provide_error_guidance(
                                rm_result.stderr, "container_removal", verbose
                            )

                except subprocess.TimeoutExpired:
                    # Handle removal timeout
                    success = False
                    if verbose:
                        self.console.print(f"❌ Removal timeout for {container_name}")

            except Exception as e:
                success = False
                if verbose:
                    self.console.print(
                        f"❌ Failed to remove {container_name}: {e}", style="red"
                    )
                    self._provide_error_guidance(str(e), "general_error", verbose)

            # Track overall success - if any container fails to be removed completely
            if not container_removed:
                success = False

        return success

    def _provide_error_guidance(
        self, error_message: str, error_category: str, verbose: bool = False
    ):
        """Provide categorized error guidance and recovery suggestions."""
        if not verbose:
            return

        error_lower = error_message.lower()

        if error_category == "permission_denied" or "permission denied" in error_lower:
            self.console.print(
                "💡 Permission denied errors can be resolved by:", style="blue"
            )
            self.console.print("   • Running with sudo (if using Docker)")
            self.console.print("   • Checking Docker daemon is running")
            self.console.print("   • Ensuring user is in docker group")

        elif "device or resource busy" in error_lower:
            self.console.print(
                "💡 Resource busy errors can be resolved by:", style="blue"
            )
            self.console.print("   • Stopping processes using the container")
            self.console.print("   • Waiting a few seconds and retrying")
            self.console.print("   • Using 'lsof' to find processes holding resources")

        elif "no space left" in error_lower:
            self.console.print("💡 Disk space errors can be resolved by:", style="blue")
            self.console.print("   • Freeing disk space with 'docker system prune'")
            self.console.print(
                "   • Removing unused volumes with 'docker volume prune'"
            )
            self.console.print("   • Checking disk usage with 'df -h'")

        elif error_category == "container_listing":
            self.console.print(
                "💡 Container listing issues can be resolved by:", style="blue"
            )
            self.console.print("   • Checking if Docker/Podman service is running")
            self.console.print("   • Verifying container engine installation")
            self.console.print("   • Checking user permissions for container access")

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

        # Check that containers are actually gone (PROJECT-SCOPED)
        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")

        # Get project hash for current project to ensure project-scoped operations
        project_root = Path.cwd()
        project_hash = self.port_registry._calculate_project_hash(project_root)

        # Find only containers for CURRENT PROJECT using project hash filtering
        list_cmd = [
            container_engine,
            "ps",
            "-a",
            "--format",
            "{{.Names}}",
            "--filter",
            f"name=cidx-{project_hash}-",  # PROJECT-SCOPED: Only current project
        ]
        try:
            list_result = subprocess.run(
                list_cmd, capture_output=True, text=True, timeout=10
            )
            if list_result.returncode == 0:
                # Already filtered by project hash, just parse the names
                container_names = [
                    name.strip()
                    for name in list_result.stdout.strip().split("\n")
                    if name.strip() and name.strip().startswith(f"cidx-{project_hash}-")
                ]
            else:
                container_names = []
        except Exception:
            container_names = []

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

    def _validate_complete_cleanup(self, verbose: bool = False) -> bool:
        """Validate that ALL project containers are removed after cleanup operations.

        This method provides comprehensive cleanup validation that checks for ANY
        remaining containers for the CURRENT PROJECT ONLY, regardless of their state.

        CRITICAL: Uses project hash-based filtering to prevent cross-project operations.

        Args:
            verbose: Whether to print detailed feedback about remaining containers

        Returns:
            bool: True if no project containers remain, False otherwise
        """
        import subprocess

        container_engine = self._get_available_runtime()
        if not container_engine:
            if verbose:
                self.console.print(
                    "❌ No container engine available for validation", style="red"
                )
            return False

        # Get project hash for current project to ensure project-scoped operations
        project_root = Path.cwd()
        project_hash = self.port_registry._calculate_project_hash(project_root)

        # Check for ANY remaining containers for CURRENT PROJECT ONLY
        list_cmd = [
            container_engine,
            "ps",
            "-a",
            "--format",
            "{{.Names}}\t{{.State}}",
            "--filter",
            f"name=cidx-{project_hash}-",  # PROJECT-SCOPED: Only current project
        ]

        try:
            result = subprocess.run(
                list_cmd, capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                if verbose:
                    self.console.print(
                        f"❌ Failed to list containers: {result.stderr}", style="red"
                    )
                return False

            if result.stdout.strip():
                # Parse remaining containers
                remaining_containers = result.stdout.strip().split("\n")
                if verbose:
                    self.console.print("❌ Remaining containers found after cleanup:")
                    for container in remaining_containers:
                        name, state = container.split("\t")
                        self.console.print(f"  - {name} (state: {state})")
                return False

            if verbose:
                self.console.print(
                    "✅ Complete cleanup validation passed - no containers remain"
                )
            return True

        except subprocess.TimeoutExpired:
            if verbose:
                self.console.print("❌ Container validation timeout", style="red")
            return False
        except subprocess.CalledProcessError as e:
            if verbose:
                self.console.print(f"❌ Container validation failed: {e}", style="red")
            return False
        except Exception as e:
            if verbose:
                self.console.print(
                    f"❌ Unexpected error during validation: {e}", style="red"
                )
            return False

    def _verify_no_root_owned_files(self, verbose: bool = False) -> bool:
        """Verify that no root-owned files remain that could cause container startup issues."""
        verification_success = True

        # Check named volumes for root-owned files
        verification_success &= self._verify_named_volumes_ownership(verbose)

        return verification_success

    def _verify_named_volumes_ownership(self, verbose: bool = False) -> bool:
        """Verify that named volumes don't contain root-owned files."""
        import subprocess

        verification_success = True
        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")

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
        """Clean up named volumes for CURRENT PROJECT ONLY with enhanced reporting."""
        import subprocess

        success = True
        container_engine = self._get_available_runtime()
        if not container_engine:
            raise RuntimeError("Neither podman nor docker is available")

        # Get project-specific volume names to target ONLY current project volumes
        try:
            # Get project configuration to determine which volumes belong to this project
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            project_config = config_manager.load()

            # Determine project-specific volume patterns
            if (
                hasattr(project_config, "project_containers")
                and project_config.project_containers
                and project_config.project_containers.project_hash  # Ensure it's not empty
            ):
                project_hash = project_config.project_containers.project_hash
            else:
                # Generate project hash from current working directory
                from pathlib import Path

                project_root = Path.cwd()
                project_hash = self.port_registry._calculate_project_hash(project_root)

            # Project-scoped volume patterns (these are the common volume naming patterns)
            target_volume_patterns = [
                f"cidx-{project_hash}-qdrant-data",
                f"cidx-{project_hash}-ollama-data",
                f"cidx-{project_hash}-data-cleaner-data",
                "ollama_data",  # Generic volume that might be shared, handle carefully
            ]

            if verbose:
                self.console.print(
                    f"🎯 Checking for project volumes (hash: {project_hash})"
                )

        except Exception as e:
            if verbose:
                self.console.print(
                    f"❌ Error getting project configuration: {e}", style="red"
                )
            return False

        # Check which target volumes actually exist
        try:
            volume_names = []
            for volume_pattern in target_volume_patterns:
                # For generic volumes like "ollama_data", we need to be more careful
                if volume_pattern == "ollama_data":
                    # Only remove generic volumes if no other containers are using them
                    # For now, we'll skip generic volumes to be safe
                    continue

                # Check if this specific volume exists
                check_cmd = [
                    container_engine,
                    "volume",
                    "ls",
                    "--format",
                    "{{.Name}}",
                    "--filter",
                    f"name=^{volume_pattern}$",  # Exact match to avoid partial matches
                ]
                result = subprocess.run(
                    check_cmd, capture_output=True, text=True, timeout=10
                )

                if result.returncode == 0 and result.stdout.strip():
                    found_volumes = [
                        name.strip()
                        for name in result.stdout.strip().split("\n")
                        if name.strip() == volume_pattern
                    ]
                    volume_names.extend(found_volumes)

            if not volume_names:
                if verbose:
                    self.console.print("ℹ️  No project volumes found to cleanup")
                return True  # Success - nothing to clean up

            if verbose:
                self.console.print("🗂️  Found project volumes to cleanup:")
                for volume_name in volume_names:
                    self.console.print(f"  - {volume_name}")

        except Exception as e:
            if verbose:
                self.console.print(f"❌ Error checking volumes: {e}", style="red")
            return False

        # Process each volume with enhanced error reporting
        for volume_name in volume_names:
            try:
                # Attempt volume removal
                remove_result = subprocess.run(
                    [container_engine, "volume", "rm", volume_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if remove_result.returncode == 0:
                    if verbose:
                        self.console.print(
                            f"✅ Removed volume: {volume_name}", style="green"
                        )
                else:
                    success = False
                    if verbose:
                        self.console.print(
                            f"❌ Failed to remove volume {volume_name}: {remove_result.stderr}",
                            style="red",
                        )

            except Exception as e:
                success = False
                if verbose:
                    self.console.print(
                        f"❌ Error handling volume {volume_name}: {e}", style="yellow"
                    )

        return success

    def _build_ollama_service(
        self, local_docker_dir: Path, network_name: str, project_config: Dict[str, str]
    ) -> Dict[str, Any]:
        """Build Ollama service configuration."""
        # Use dynamically allocated port from project_config
        if "ollama_port" not in project_config or not project_config["ollama_port"]:
            raise ValueError(
                "Dynamic port allocation required: ollama_port missing from project_config"
            )
        ollama_port = int(project_config["ollama_port"])

        return {
            "build": {
                "context": str(local_docker_dir.absolute()),
                "dockerfile": "Dockerfile.ollama",
            },
            "container_name": self.get_container_name("ollama", project_config),
            "ports": [f"0.0.0.0:{ollama_port}:11434"],
            "volumes": [
                "ollama_data:/home/ollama/.ollama",
            ],
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
        self,
        local_docker_dir: Path,
        network_name: str,
        project_root: Path,
        project_config: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Build Qdrant service configuration with project-local storage.

        Stores all Qdrant data within the project directory for true isolation.
        """
        # Use dynamically allocated port from project_config
        if "qdrant_port" not in project_config or not project_config["qdrant_port"]:
            raise ValueError(
                "Dynamic port allocation required: qdrant_port missing from project_config"
            )
        qdrant_port = int(project_config["qdrant_port"])

        # Project-local Qdrant storage - use relative path for CoW compatibility
        project_qdrant_dir = project_root / ".code-indexer" / "qdrant"

        # Ensure project Qdrant directory exists
        project_qdrant_dir.mkdir(parents=True, exist_ok=True)

        # Use relative path from compose file location for CoW clone compatibility
        # The compose file is in ~/.tmp/code-indexer/ so we need to calculate relative path
        compose_dir = self.compose_file.parent
        try:
            relative_qdrant_path = project_qdrant_dir.relative_to(compose_dir)
            volume_path = f"./{relative_qdrant_path}"  # Ensure it's treated as a path, not named volume
        except ValueError:
            # If relative path calculation fails, fall back to absolute
            volume_path = str(project_qdrant_dir.absolute())

        volumes = [
            f"{volume_path}:/qdrant/storage",  # Relative path for CoW clone support
        ]

        return {
            "build": {
                "context": str(local_docker_dir.absolute()),
                "dockerfile": "Dockerfile.qdrant",
            },
            "container_name": self.get_container_name("qdrant", project_config),
            "ports": [f"0.0.0.0:{qdrant_port}:6333"],
            "volumes": volumes,
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
        project_root: Path,
        project_config: Dict[str, str],
        include_ollama_volumes: bool = True,
    ) -> Dict[str, Any]:
        """Build data cleaner service configuration."""
        # Use dynamically allocated port from project_config
        if (
            "data_cleaner_port" not in project_config
            or not project_config["data_cleaner_port"]
        ):
            raise ValueError(
                "Dynamic port allocation required: data_cleaner_port missing from project_config"
            )
        data_cleaner_port = int(project_config["data_cleaner_port"])

        # Project-local data cleaner configuration - access project Qdrant storage directly
        project_qdrant_dir = project_root / ".code-indexer" / "qdrant"

        # Ensure project Qdrant directory exists
        project_qdrant_dir.mkdir(parents=True, exist_ok=True)

        # Use relative path from compose file location for CoW clone compatibility
        compose_dir = self.compose_file.parent
        try:
            relative_qdrant_path = project_qdrant_dir.relative_to(compose_dir)
            qdrant_volume_path = f"./{relative_qdrant_path}"  # Ensure it's treated as a path, not named volume
        except ValueError:
            # If relative path calculation fails, fall back to absolute
            qdrant_volume_path = str(project_qdrant_dir.absolute())

        volumes = [
            f"{qdrant_volume_path}:/qdrant/storage",  # Match qdrant service mount path
        ]

        if include_ollama_volumes:
            ollama_storage_dir = Path.home() / ".ollama_storage"
            ollama_storage_dir.mkdir(exist_ok=True)
            volumes.append(f"{ollama_storage_dir}:/data/ollama")

        return {
            "build": {
                "context": str(local_docker_dir.absolute()),
                "dockerfile": "Dockerfile.cleaner",
            },
            "container_name": self.get_container_name("data-cleaner", project_config),
            "ports": [f"0.0.0.0:{data_cleaner_port}:8091"],
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
        self,
        project_root: Path,
        project_config: Dict[str, str],
        data_dir: Path = Path(".code-indexer"),
    ) -> Dict[str, Any]:
        """Generate Docker Compose configuration for required services only."""
        # Determine which services are required by loading config from project directory
        try:
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(project_root)
            project_config_data = config_manager.load()
            config_dict = {"embedding_provider": project_config_data.embedding_provider}
            required_services = self.get_required_services(config_dict)
        except Exception:
            # Fallback to default service detection if config loading fails
            required_services = self.get_required_services()

        # Project-specific network
        network_name = self.get_network_name()

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

        # Build compose configuration with explicit subnet management
        network_config = self.get_network_config()
        compose_config = {
            "services": {},
            "networks": network_config,
            "volumes": {
                "qdrant_metadata": {"driver": "local"}
            },  # For qdrant metadata only
        }

        # Add services based on requirements
        if "qdrant" in required_services:
            compose_config["services"]["qdrant"] = self._build_qdrant_service(
                local_docker_dir, network_name, project_root, project_config
            )

        if "ollama" in required_services:
            compose_config["services"]["ollama"] = self._build_ollama_service(
                local_docker_dir, network_name, project_config
            )
            # Only include ollama volumes if ollama is required
            compose_config["volumes"]["ollama_data"] = {"driver": "local"}

        if "data-cleaner" in required_services:
            # Include ollama volumes in data-cleaner only if ollama service is required
            include_ollama_volumes = "ollama" in required_services
            compose_config["services"]["data-cleaner"] = self._build_cleaner_service(
                local_docker_dir,
                network_name,
                project_root,
                project_config,
                include_ollama_volumes,
            )

        return compose_config

    def start_data_cleaner(
        self, project_config: Optional[Dict[str, str]] = None
    ) -> bool:
        """Start only the data cleaner service for cleanup operations."""
        try:
            if not self.compose_file.exists():
                self.console.print("❌ Compose file not found. Run setup first.")
                return False

            # Determine project name - use from config if provided, otherwise fall back to self.project_name
            if project_config and "data_cleaner_name" in project_config:
                # Extract project name from data_cleaner_name (remove service suffix)
                data_cleaner_name = project_config["data_cleaner_name"]
                if data_cleaner_name.endswith("-data-cleaner"):
                    project_name = data_cleaner_name[:-13]  # Remove '-data-cleaner'
                else:
                    project_name = self.project_name
            else:
                project_name = self.project_name

            # Get the appropriate container runtime (respects --force-docker flag)
            runtime = self._get_preferred_runtime()

            # Get the project-specific data-cleaner container name
            container_name = self.get_container_name("data-cleaner", project_config)

            self.console.print("🧹 Starting data cleaner service...")

            # First, check if the container already exists
            inspect_cmd = [runtime, "inspect", container_name]
            inspect_result = subprocess.run(
                inspect_cmd, capture_output=True, text=True, timeout=10
            )

            if inspect_result.returncode == 0:
                # Container exists, check if it's running
                ps_cmd = [
                    runtime,
                    "ps",
                    "--filter",
                    f"name={container_name}",
                    "--format",
                    "{{.Names}}",
                ]
                ps_result = subprocess.run(
                    ps_cmd, capture_output=True, text=True, timeout=10
                )

                if container_name in ps_result.stdout:
                    self.console.print("✅ Data cleaner container already running")
                    return True
                else:
                    # Container exists but is stopped, just start it
                    self.console.print("🔄 Starting existing data cleaner container...")
                    start_cmd = [runtime, "start", container_name]
                    start_result = subprocess.run(
                        start_cmd, capture_output=True, text=True, timeout=60
                    )

                    if start_result.returncode == 0:
                        self.console.print(
                            "✅ Data cleaner container started successfully"
                        )
                        return True
                    else:
                        self.console.print(
                            f"❌ Failed to start existing container: {start_result.stderr}"
                        )
                        # If starting failed, fall through to create new container

            # Container doesn't exist or failed to start, create it with compose
            self.console.print("🆕 Creating new data cleaner container...")
            compose_cmd = self.get_compose_command()
            cmd = compose_cmd + [
                "-f",
                str(self.compose_file),
                "-p",
                project_name,
                "up",
                "-d",
                "data-cleaner",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

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

    def clean_with_data_cleaner(
        self, paths: List[str], project_config: Optional[Dict[str, str]] = None
    ) -> bool:
        """Use the data cleaner service to remove root-owned files."""
        try:
            # For new mode, require project configuration
            if project_config:
                container_name = self.get_container_name("data-cleaner", project_config)
            else:
                # Fallback: search for any cidx data-cleaner container
                pass  # subprocess is already imported at module level

                container_engine = self._get_available_runtime()
                if not container_engine:
                    raise RuntimeError("Neither podman nor docker is available")

                list_cmd = [container_engine, "ps", "--format", "{{.Names}}"]
                try:
                    list_result = subprocess.run(
                        list_cmd, capture_output=True, text=True, timeout=10
                    )
                    if list_result.returncode == 0:
                        all_containers = (
                            list_result.stdout.strip().split("\n")
                            if list_result.stdout.strip()
                            else []
                        )
                        data_cleaner_containers = [
                            name
                            for name in all_containers
                            if "data-cleaner" in name and name.startswith("cidx-")
                        ]
                        if data_cleaner_containers:
                            container_name = data_cleaner_containers[
                                0
                            ]  # Use first found
                        else:
                            self.console.print(
                                "❌ No data-cleaner container found", style="red"
                            )
                            return False
                    else:
                        self.console.print("❌ Failed to list containers", style="red")
                        return False
                except Exception as e:
                    self.console.print(
                        f"❌ Error finding data-cleaner container: {e}", style="red"
                    )
                    return False

            # Detect container engine (podman or docker)
            container_engine = self._get_available_runtime()
            if not container_engine:
                raise RuntimeError("Neither podman nor docker is available")

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
                if not self.start_data_cleaner(project_config):
                    return False

                # Wait a moment and verify container is actually running
                import time

                time.sleep(3)
                verify_result = subprocess.run(
                    check_cmd, capture_output=True, text=True
                )
                if container_name not in verify_result.stdout:
                    self.console.print(
                        f"❌ Expected container {container_name} not found after start. Available containers:",
                        style="red",
                    )
                    list_all_cmd = [container_engine, "ps", "--format", "{{.Names}}"]
                    all_containers_result = subprocess.run(
                        list_all_cmd, capture_output=True, text=True
                    )
                    self.console.print(f"Available: {all_containers_result.stdout}")
                    return False
                else:
                    self.console.print(f"✅ Container {container_name} is now running")

            # Always wait for the data cleaner service to be ready (for reliability)
            # Get data cleaner URL using the same method as health checks (NO FALLBACK PORTS!)
            data_cleaner_url = self._get_service_url("data-cleaner")
            if not data_cleaner_url:
                raise RuntimeError(
                    "Cannot determine data cleaner port - no project configuration found"
                )
            data_cleaner_ready = self.health_checker.wait_for_service_ready(
                data_cleaner_url,  # Data cleaner root endpoint
                timeout=self.health_checker.get_timeouts().get(
                    "data_cleaner_startup", 60
                ),
            )

            if not data_cleaner_ready:
                # Enhanced error reporting: Get container status and provide specific feedback
                try:
                    status_cmd = [
                        container_engine,
                        "ps",
                        "-a",
                        "--format",
                        "{{.Names}}\t{{.State}}",
                        "--filter",
                        f"name={container_name}",
                    ]
                    status_result = subprocess.run(
                        status_cmd, capture_output=True, text=True, timeout=10
                    )

                    if status_result.returncode == 0 and status_result.stdout.strip():
                        container_info = status_result.stdout.strip()
                        container_parts = container_info.split("\t")
                        if len(container_parts) >= 2:
                            name, state = container_parts[0], container_parts[1]
                            self.console.print(
                                f"❌ Data cleaner container failed: {name} (state: {state})",
                                style="red",
                            )
                            self.console.print(
                                f"💡 To debug: {container_engine} logs {name}",
                                style="blue",
                            )
                        else:
                            self.console.print(
                                f"❌ Data cleaner failed to become ready: {container_info}",
                                style="red",
                            )
                    else:
                        self.console.print(
                            "❌ Data cleaner failed to become ready", style="red"
                        )
                except Exception:
                    self.console.print(
                        "❌ Data cleaner failed to become ready", style="red"
                    )
                return False

            # Use container exec to run cleanup commands with shell expansion
            cleanup_success = True
            for path in paths:
                self.console.print(f"🗑️  Cleaning path: {path}")

                # First, check if path exists to avoid unnecessary errors
                check_cmd = [
                    container_engine,
                    "exec",
                    container_name,
                    "sh",
                    "-c",
                    f"ls -la {path} 2>/dev/null || echo 'PATH_NOT_EXISTS'",
                ]
                check_result = subprocess.run(
                    check_cmd, capture_output=True, text=True, timeout=30
                )

                if "PATH_NOT_EXISTS" in check_result.stdout:
                    self.console.print(f"ℹ️  Path {path} does not exist, skipping")
                    continue

                # Use sh -c to enable shell expansion for wildcards
                # Add force flag and ignore errors for thorough cleanup
                cmd = [
                    container_engine,
                    "exec",
                    container_name,
                    "sh",
                    "-c",
                    f"rm -rf {path} 2>/dev/null || true",
                ]
                subprocess.run(cmd, capture_output=True, text=True, timeout=120)

                # For critical paths like qdrant collections, verify cleanup
                if "/qdrant/" in path:
                    verify_cmd = [
                        container_engine,
                        "exec",
                        container_name,
                        "sh",
                        "-c",
                        f"find {path.replace('/*', '')} -type f 2>/dev/null | head -5 || echo 'CLEAN'",
                    ]
                    verify_result = subprocess.run(
                        verify_cmd, capture_output=True, text=True, timeout=30
                    )

                    if (
                        "CLEAN" in verify_result.stdout
                        or not verify_result.stdout.strip()
                    ):
                        self.console.print(f"✅ Verified clean: {path}")
                    else:
                        self.console.print(
                            f"⚠️  Some files may remain in {path}: {verify_result.stdout[:100]}"
                        )
                        cleanup_success = False
                else:
                    self.console.print(f"✅ Cleaned: {path}")

            return cleanup_success

        except Exception as e:
            self.console.print(f"❌ Error using data cleaner: {e}")
            return False

    def stop_main_services(self) -> bool:
        """Stop only the main services (ollama and qdrant), leaving data cleaner running.

        Ensures containers are fully stopped before data-cleaner cleanup begins.
        """
        try:
            if not self.compose_file.exists():
                return True  # Nothing to stop

            compose_cmd = self.get_compose_command()
            container_engine = self._get_available_runtime()

            if not container_engine:
                self.console.print("❌ No container engine available")
                return False

            # Load project configuration for accurate container name resolution
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            project_config = config_manager.load()

            # Get project container configuration
            if not (
                hasattr(project_config, "project_containers")
                and project_config.project_containers
            ):
                raise RuntimeError(
                    "Project container configuration not available in config"
                )

            project_config_dict = project_config.project_containers

            # Stop ollama and qdrant services individually with verification
            for service in ["ollama", "qdrant"]:
                self.console.print(f"🛑 Stopping {service} service...")

                # Stop the service
                cmd = compose_cmd + [
                    "-f",
                    str(self.compose_file),
                    "-p",
                    self.project_name,
                    "stop",
                    service,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                if result.returncode != 0:
                    self.console.print(
                        f"⚠️  Warning: Failed to stop {service}: {result.stderr}"
                    )

                # Verify the container is actually stopped using correct container name
                container_name = self.get_container_name(service, project_config_dict)
                verify_cmd = [
                    container_engine,
                    "ps",
                    "--filter",
                    f"name={container_name}",
                    "--format",
                    "{{.Names}}",
                ]

                # Wait up to 10 seconds for container to stop
                import time

                for attempt in range(10):
                    verify_result = subprocess.run(
                        verify_cmd, capture_output=True, text=True
                    )
                    if container_name not in verify_result.stdout:
                        self.console.print(f"✅ {service} container fully stopped")
                        break
                    time.sleep(1)
                else:
                    # Force kill if still running after 10 seconds
                    self.console.print(
                        f"⚠️  {service} container still running, force killing..."
                    )
                    kill_cmd = [container_engine, "kill", container_name]
                    subprocess.run(kill_cmd, capture_output=True, text=True, timeout=30)
                    self.console.print(f"🔥 Force killed {service} container")

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

    def _ensure_all_mount_paths_exist(
        self, project_root: Path, required_services: List[str]
    ) -> None:
        """Ensure ALL mount directories exist before starting containers.

        This prevents container startup failures due to missing mount paths.
        """
        mount_paths_to_create = []

        # Qdrant mount path (used by both qdrant and data-cleaner)
        qdrant_mount_path = project_root / ".code-indexer" / "qdrant"
        mount_paths_to_create.append(qdrant_mount_path)

        # Ollama mount path (global, used if ollama service is required)
        if "ollama" in required_services:
            ollama_mount_path = Path.home() / ".ollama_storage"
            mount_paths_to_create.append(ollama_mount_path)

        # Docker context directory (for Dockerfiles)
        docker_context_path = project_root / ".code-indexer" / "docker"
        mount_paths_to_create.append(docker_context_path)

        # Create all mount directories
        for mount_path in mount_paths_to_create:
            mount_path.mkdir(parents=True, exist_ok=True)
            self.console.print(f"📁 Ensured mount path exists: {mount_path}")

    def _attempt_start_with_ports(
        self,
        required_services: List[str],
        project_config: Dict[str, str],
        project_root: Path,
        recreate: bool,
        existing_ports: Optional[Dict[str, int]] = None,
    ) -> bool:
        """Attempt to start services with the given port configuration."""
        try:
            # ===============================================================================
            # STEP 3: PORT SYNCHRONIZATION - THE CRITICAL FIX
            # ===============================================================================
            # Problem: Previously config was updated AFTER containers started, causing
            # health checks to fail because they used stale ports while containers used new ones.
            #
            # Solution: Update config BEFORE containers start, ensuring perfect synchronization:
            # 1. Extract calculated ports from project_config
            # 2. Write ports to disk config file (for persistence)
            # 3. Update in-memory config (for immediate health checks)
            # 4. Start containers with same ports
            # 5. Health checks read from updated in-memory config -> SUCCESS!
            # ===============================================================================

            # Use existing ports if provided, otherwise extract from project_config
            if existing_ports:
                project_config_ports = existing_ports
            else:
                # Extract the allocated ports from project_config (calculated in previous step)
                project_config_ports = {}
                if "qdrant_port" in project_config:
                    project_config_ports["qdrant_port"] = int(
                        project_config["qdrant_port"]
                    )
                if "ollama_port" in project_config:
                    project_config_ports["ollama_port"] = int(
                        project_config["ollama_port"]
                    )
                if "data_cleaner_port" in project_config:
                    project_config_ports["data_cleaner_port"] = int(
                        project_config["data_cleaner_port"]
                    )

            # STEP 3A: Update configuration file on disk
            # This ensures persistence across restarts and allows external tools to see current ports
            self._update_config_with_ports(project_root, project_config_ports)

            # STEP 3B: Reload config to ensure health checks use updated ports
            # This ensures health checks read from the updated project configuration
            from ..config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(project_root)
            updated_config = config_manager.load()

            # Update health checker with new config
            self.health_checker = HealthChecker(config_manager=updated_config)

            # Generate compose configuration with the allocated ports
            # Use the fixed project_config_ports instead of original project_config
            # Convert ports to strings for compatibility
            string_ports = {k: str(v) for k, v in project_config_ports.items()}
            fixed_project_config = {**project_config, **string_ports}
            compose_config = self.generate_compose_config(
                project_root=project_root, project_config=fixed_project_config
            )

            # Write compose file
            with open(self.compose_file, "w") as f:
                yaml.dump(compose_config, f, default_flow_style=False)

            # Start services using docker compose
            compose_cmd = self.get_compose_command()

            start_cmd = compose_cmd + [
                "-f",
                str(self.compose_file),
                "-p",
                self.project_name,
                "up",
                "-d",
            ]

            if recreate:
                start_cmd.append("--force-recreate")

            # Only start required services
            start_cmd.extend(required_services)

            self.console.print("🚀 Starting Docker services...")
            result = subprocess.run(
                start_cmd, capture_output=True, text=True, timeout=180
            )

            if result.returncode != 0:
                # Check if failure is due to port conflicts
                if "bind: address already in use" in result.stderr:
                    self.console.print(
                        "⚠️  Port conflict detected, will retry with different ports"
                    )
                    return False
                else:
                    # Other error - re-raise
                    self.console.print(f"❌ Failed to start services: {result.stderr}")
                    raise RuntimeError(f"Service start failed: {result.stderr}")

            # Verify services are actually running and healthy
            return self.wait_for_services(
                timeout=180, project_config=fixed_project_config
            )

        except subprocess.TimeoutExpired:
            self.console.print("❌ Service startup timed out")
            return False
        except Exception as e:
            self.console.print(f"❌ Error starting services: {e}")
            return False

    def _update_config_with_ports(
        self, project_root: Path, allocated_ports: Dict[str, int]
    ) -> None:
        """Update the project configuration file with the allocated ports."""
        try:
            # First try the standard project config location
            config_path = project_root / ".code-indexer" / "config.json"

            # NOTE: Simplified config update without main_config dependency
            # Each project has its own isolated configuration

            if config_path.exists():
                # Read current config
                import json

                with open(config_path, "r") as f:
                    config_data = json.load(f)

                # Update ports section (only update ports that are provided)
                if "project_ports" not in config_data:
                    config_data["project_ports"] = {}

                # Update only the ports that are provided
                for port_key, port_value in allocated_ports.items():
                    config_data["project_ports"][port_key] = port_value

                # Also update the qdrant host URL to reflect the new port
                if "qdrant" in config_data:
                    config_data["qdrant"][
                        "host"
                    ] = f"http://localhost:{allocated_ports['qdrant_port']}"

                # Also update ollama host URL if present and if ollama port is allocated
                if "ollama" in config_data and "ollama_port" in allocated_ports:
                    config_data["ollama"][
                        "host"
                    ] = f"http://localhost:{allocated_ports['ollama_port']}"

                # Write updated config
                with open(config_path, "w") as f:
                    json.dump(config_data, f, indent=2)

                # NOTE: Config is now loaded per-project on-demand, eliminating need for in-memory updates

                self.console.print(
                    f"📝 Updated configuration with ports: {allocated_ports}"
                )
            else:
                self.console.print("⚠️  Configuration file not found, ports not saved")

        except Exception as e:
            self.console.print(f"⚠️  Failed to update configuration with ports: {e}")

    def _cleanup_wal_files(self, config_manager):
        """Clean up corrupted WAL files that may prevent Qdrant container startup.

        This method removes WAL files and related lock files that can become corrupted
        during concurrent access or improper shutdowns, preventing Qdrant from starting.
        """
        try:
            import shutil
            from pathlib import Path

            config = config_manager.load()
            project_root = Path(config.codebase_dir)
            qdrant_storage_path = project_root / ".code-indexer" / "qdrant"

            if not qdrant_storage_path.exists():
                return

            self.console.print(
                "🧹 Cleaning up corrupted Qdrant collections to prevent startup issues...",
                style="yellow",
            )

            # Find and remove entire collection directories that contain corrupted WAL files
            # This is more thorough than just removing WAL files and prevents metadata inconsistencies
            collections_removed = 0
            collections_dir = qdrant_storage_path / "collections"

            if collections_dir.exists():
                for collection_dir in collections_dir.iterdir():
                    if collection_dir.is_dir():
                        try:
                            shutil.rmtree(collection_dir)
                            collections_removed += 1
                            self.console.print(
                                f"   🗑️  Removed collection: {collection_dir.name}"
                            )
                        except Exception as e:
                            self.console.print(
                                f"   ⚠️  Could not remove collection {collection_dir.name}: {e}",
                                style="yellow",
                            )

            # Remove lock files
            lock_files_removed = 0
            for lock_file in qdrant_storage_path.rglob("*.lock"):
                try:
                    lock_file.unlink()
                    lock_files_removed += 1
                    self.console.print(
                        f"   🗑️  Removed lock file: {lock_file.relative_to(project_root)}"
                    )
                except Exception as e:
                    self.console.print(
                        f"   ⚠️  Could not remove {lock_file}: {e}", style="yellow"
                    )

            if collections_removed > 0 or lock_files_removed > 0:
                self.console.print(
                    f"✅ Qdrant cleanup complete: {collections_removed} collections, {lock_files_removed} lock files removed",
                    style="green",
                )
            else:
                self.console.print(
                    "✅ No corrupted collections or lock files found to clean",
                    style="green",
                )

        except Exception as e:
            self.console.print(f"⚠️  Could not clean WAL files: {e}", style="yellow")


def get_project_compose_file_path(
    project_config_dir: Path, force_docker: bool = False
) -> Path:
    """Get the path to the project-specific compose file stored in the project's .code-indexer directory.

    This is a standalone function that can be used anywhere in the codebase
    to get the consistent compose file location for a specific project.

    Args:
        project_config_dir: Path to the project's .code-indexer directory
        force_docker: Whether Docker is being forced (affects test mode directory)

    Returns:
        Path to the project-specific docker-compose.yml file
    """

    # Store compose file in the project's .code-indexer directory
    compose_dir = project_config_dir

    # Ensure the directory exists
    compose_dir.mkdir(parents=True, exist_ok=True)

    return compose_dir / "docker-compose.yml"
