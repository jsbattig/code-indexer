"""
Global Port Registry for coordinating port allocation across all cidx projects.

This module provides centralized port allocation to prevent conflicts between
multiple cidx projects running on the same system. It uses a global registry
with soft links to track active projects and automatically cleans up broken
links when projects are deleted.

Key Features:
- Global port coordination across all users and projects
- Automatic broken softlink cleanup
- No file locking - uses atomic operations
- Cross-filesystem softlink support
- Self-healing registry maintenance
"""

import hashlib
import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Dict, Set, Any, Optional

logger = logging.getLogger(__name__)


class PortRegistryError(Exception):
    """Base exception for port registry errors."""

    pass


class PortExhaustionError(PortRegistryError):
    """Raised when no ports are available in the specified range."""

    pass


class GlobalPortRegistry:
    """
    Global port registry for coordinating port allocation across cidx projects.

    This class manages a system-wide registry of port allocations using soft links
    to track active projects. It automatically cleans up broken links when projects
    are deleted and ensures no port conflicts between concurrent cidx instances.
    """

    def __init__(self):
        """Initialize the global port registry."""
        self.registry_path = self._get_registry_path()
        self.active_projects_path = self.registry_path / "active-projects"
        self.port_allocations_file = self.registry_path / "port-allocations.json"
        self.registry_log_file = self.registry_path / "registry.log"

        # Port ranges for each service
        self.port_ranges = {
            "qdrant": (6333, 7333),
            "ollama": (11434, 12434),
            "data_cleaner": (8091, 9091),
        }

        # Ensure registry structure exists
        self._ensure_registry_structure()

    def _get_registry_path(self) -> Path:
        """Get registry path - SINGLE LOCATION ONLY, NO FALLBACKS."""
        registry_location = Path("/var/lib/code-indexer/port-registry")

        try:
            registry_location.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = registry_location / f"test-access-{os.getpid()}"
            test_file.write_text("test")
            test_file.unlink()
            logger.debug(f"Using port registry: {registry_location}")
            return registry_location
        except (OSError, PermissionError) as e:
            raise PortRegistryError(
                f"Global port registry not accessible at {registry_location}. "
                f"Run 'cidx init --setup-global-registry' or 'cidx setup-global-registry' to configure proper permissions. "
                f"Error: {e}"
            )

    def _ensure_registry_structure(self):
        """Ensure registry directory structure exists."""
        try:
            self.active_projects_path.mkdir(parents=True, exist_ok=True)

            # Create files if they don't exist
            if not self.port_allocations_file.exists():
                self.port_allocations_file.write_text("{}")

            if not self.registry_log_file.exists():
                self.registry_log_file.touch()

        except (OSError, PermissionError) as e:
            raise PortRegistryError(f"Failed to create registry structure: {e}")

    def find_available_port_for_service(
        self, service: str, exclude_ports: Optional[Set[int]] = None
    ) -> int:
        """
        Find an available port for the specified service.

        Args:
            service: Service name ("qdrant", "ollama", "data_cleaner")
            exclude_ports: Set of ports to exclude from allocation

        Returns:
            Available port number

        Raises:
            PortExhaustionError: If no ports are available in the service range
        """
        # Clean registry and get current allocations
        cleanup_result = self.scan_and_cleanup_registry()
        if cleanup_result["cleaned"] > 0:
            logger.info(
                f"Freed {len(cleanup_result['freed_ports'])} ports from {cleanup_result['cleaned']} deleted projects"
            )

        # Load current port allocations
        allocated_ports = self._load_current_allocations()

        # Get port range for service
        if service not in self.port_ranges:
            raise PortRegistryError(f"Unknown service: {service}")

        start_port, end_port = self.port_ranges[service]
        exclude_ports = exclude_ports or set()

        # Find first available port
        all_busy_ports = allocated_ports | exclude_ports

        for port in range(start_port, end_port + 1):
            if port not in all_busy_ports:
                if self._is_port_bindable(port):
                    return port
                else:
                    # Port is busy by external process
                    all_busy_ports.add(port)

        raise PortExhaustionError(
            f"No available ports for {service} in range {start_port}-{end_port}"
        )

    def register_project_allocation(self, project_root: Path, ports: Dict[str, int]):
        """
        Register project port allocation in global registry.

        Args:
            project_root: Root directory of the project
            ports: Dictionary mapping service names to port numbers
        """
        # Clean registry first
        self.scan_and_cleanup_registry()

        # Verify project has .code-indexer directory
        config_dir = project_root / ".code-indexer"
        if not config_dir.exists():
            raise PortRegistryError(f"Project config directory not found: {config_dir}")

        # Calculate project hash for link naming
        project_hash = self._calculate_project_hash(project_root)
        link_name = f"proj-{project_hash}"
        link_path = self.active_projects_path / link_name

        # Remove old link if exists
        if link_path.exists() or link_path.is_symlink():
            try:
                link_path.unlink()
            except OSError:
                pass  # Ignore errors removing old links

        # Create new soft link to project's .code-indexer directory
        try:
            link_path.symlink_to(config_dir.resolve())
            logger.debug(f"Registered project: {link_name} -> {config_dir}")
        except OSError as e:
            raise PortRegistryError(f"Failed to create project link: {e}")

        # Update port allocations file
        self._update_port_allocations_file(project_hash, ports)

    def scan_and_cleanup_registry(self) -> Dict[str, Any]:
        """
        Scan registry and immediately cleanup any broken softlinks found.

        Returns:
            Dictionary with cleanup results: {cleaned, active, freed_ports}
        """
        if not self.active_projects_path.exists():
            return {"cleaned": 0, "active": 0, "freed_ports": []}

        broken_links = []
        active_projects = {}
        freed_ports = set()

        # Scan all softlinks
        for link_path in self.active_projects_path.iterdir():
            if not link_path.is_symlink():
                continue

            try:
                # Check if target exists and has valid config
                target = link_path.resolve(strict=True)  # Throws if broken
                config_file = target / "config.json"

                if target.exists() and config_file.exists():
                    # Valid project - keep it
                    try:
                        with open(config_file) as f:
                            config_data = json.load(f)
                            project_ports = config_data.get("project_ports", {})
                            project_containers = config_data.get(
                                "project_containers", {}
                            )
                            project_hash = project_containers.get("project_hash")

                            if project_hash:
                                active_projects[project_hash] = {
                                    "config_path": str(target),
                                    "ports": project_ports,
                                }
                    except (json.JSONDecodeError, KeyError):
                        # Invalid config - mark for removal
                        broken_links.append(link_path)
                else:
                    # No config file - mark for removal
                    broken_links.append(link_path)

            except (OSError, RuntimeError):
                # Broken symlink - mark for removal
                broken_links.append(link_path)

        # Remove broken links immediately
        for broken_link in broken_links:
            try:
                # Extract ports that will be freed
                link_name = broken_link.name
                if link_name.startswith("proj-"):
                    project_hash = link_name[5:]  # Remove "proj-" prefix
                    freed_ports.update(self._get_ports_for_project_hash(project_hash))

                # Remove the broken link
                broken_link.unlink()
                logger.info(f"Removed broken registry link: {link_name}")

            except OSError as e:
                logger.warning(f"Failed to remove broken link {broken_link}: {e}")

        # Rebuild port allocations if we removed any links
        if broken_links:
            self._rebuild_port_allocations(active_projects)
            logger.info(
                f"Registry cleaned: removed {len(broken_links)} broken links, freed {len(freed_ports)} ports"
            )

        return {
            "cleaned": len(broken_links),
            "active": len(active_projects),
            "freed_ports": list(freed_ports),
        }

    def get_all_allocated_ports(self) -> Dict[int, str]:
        """
        Get all allocated ports with their project hashes.

        Returns:
            Dictionary mapping port numbers to project hashes
        """
        # Clean registry first
        self.scan_and_cleanup_registry()

        if not self.port_allocations_file.exists():
            return {}

        try:
            with open(self.port_allocations_file) as f:
                allocations = json.load(f)
                return {
                    int(port): info.get("project_hash", "unknown")
                    for port, info in allocations.items()
                    if port.isdigit()
                }
        except (OSError, json.JSONDecodeError):
            return {}

    def _load_current_allocations(self) -> Set[int]:
        """Load current port allocations from file."""
        if not self.port_allocations_file.exists():
            return set()

        try:
            with open(self.port_allocations_file) as f:
                allocations = json.load(f)
                return {int(port) for port in allocations.keys() if port.isdigit()}
        except (OSError, json.JSONDecodeError):
            return set()

    def _is_port_bindable(self, port: int) -> bool:
        """Check if a port can be bound (is not in use)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return True
        except OSError:
            return False

    def _calculate_project_hash(self, project_root: Path) -> str:
        """Calculate deterministic hash from project root path."""
        canonical_path = str(project_root.resolve())
        hash_object = hashlib.sha256(canonical_path.encode())
        return hash_object.hexdigest()[:8]

    def _get_ports_for_project_hash(self, project_hash: str) -> Set[int]:
        """Get ports currently allocated to a project hash."""
        ports = set()

        try:
            if self.port_allocations_file.exists():
                with open(self.port_allocations_file) as f:
                    allocations = json.load(f)

                for port_str, allocation_info in allocations.items():
                    if allocation_info.get("project_hash") == project_hash:
                        try:
                            ports.add(int(port_str))
                        except ValueError:
                            pass
        except (OSError, json.JSONDecodeError):
            pass

        return ports

    def _update_port_allocations_file(self, project_hash: str, ports: Dict[str, int]):
        """Atomically update port allocations file."""
        # Load current allocations
        if self.port_allocations_file.exists():
            try:
                with open(self.port_allocations_file) as f:
                    allocations = json.load(f)
            except (OSError, json.JSONDecodeError):
                allocations = {}
        else:
            allocations = {}

        # Remove old allocations for this project
        allocations = {
            port: info
            for port, info in allocations.items()
            if info.get("project_hash") != project_hash
        }

        # Add new allocations
        for service_key, port in ports.items():
            if isinstance(port, int):
                allocations[str(port)] = {
                    "project_hash": project_hash,
                    "service": service_key,
                    "timestamp": time.time(),
                }

        # Atomic write using temp file + rename
        temp_file = self.port_allocations_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(allocations, f, indent=2)

            temp_file.replace(self.port_allocations_file)
        except OSError as e:
            if temp_file.exists():
                temp_file.unlink()
            raise PortRegistryError(f"Failed to update port allocations: {e}")

    def _rebuild_port_allocations(self, active_projects: Dict[str, Dict]):
        """Rebuild port allocations from active projects only."""
        port_allocations = {}

        for project_hash, project_info in active_projects.items():
            ports = project_info["ports"]
            for service_key, port in ports.items():
                if isinstance(port, int):
                    port_allocations[str(port)] = {
                        "project_hash": project_hash,
                        "service": service_key,
                        "config_path": project_info["config_path"],
                        "timestamp": time.time(),
                    }

        # Write updated allocations atomically
        temp_file = self.port_allocations_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(port_allocations, f, indent=2)

            temp_file.replace(self.port_allocations_file)
        except OSError as e:
            if temp_file.exists():
                temp_file.unlink()
            logger.error(f"Failed to rebuild port allocations: {e}")
