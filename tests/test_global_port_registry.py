"""
Comprehensive unit tests for GlobalPortRegistry.
Follows TDD approach - write tests first, then implement.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from code_indexer.services.global_port_registry import (
    GlobalPortRegistry,
    PortExhaustionError,
)


class TestGlobalPortRegistryTDD:
    """TDD tests for GlobalPortRegistry - write these FIRST."""

    @pytest.fixture
    def temp_registry(self):
        """Create temporary registry for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "test-registry"
            registry_path.mkdir()
            (registry_path / "active-projects").mkdir()
            (registry_path / "port-allocations.json").touch()
            (registry_path / "registry.log").touch()

            with patch.object(
                GlobalPortRegistry, "_get_registry_path", return_value=registry_path
            ):
                yield GlobalPortRegistry()

    def test_registry_initialization_creates_structure(self, temp_registry):
        """RED: Test registry creates proper directory structure."""
        registry = temp_registry
        assert registry.registry_path.exists()
        assert registry.active_projects_path.exists()
        assert registry.port_allocations_file.exists()

    def test_find_available_port_for_service_basic(self, temp_registry):
        """RED: Test basic port allocation for single service."""
        registry = temp_registry
        port = registry.find_available_port_for_service("qdrant")
        assert 6333 <= port <= 7333  # Within qdrant range

    def test_find_available_port_excludes_given_ports(self, temp_registry):
        """RED: Test port allocation excludes specified ports."""
        registry = temp_registry
        exclude_ports = {6333, 6334, 6335}
        port = registry.find_available_port_for_service("qdrant", exclude_ports)
        assert port not in exclude_ports
        assert 6333 <= port <= 7333

    def test_port_ranges_respected(self, temp_registry):
        """RED: Test each service gets ports in correct range."""
        registry = temp_registry

        qdrant_port = registry.find_available_port_for_service("qdrant")
        ollama_port = registry.find_available_port_for_service("ollama")
        cleaner_port = registry.find_available_port_for_service("data_cleaner")

        assert 6333 <= qdrant_port <= 7333
        assert 11434 <= ollama_port <= 12434
        assert 8091 <= cleaner_port <= 9091

    def test_register_project_allocation_creates_softlink(self, temp_registry):
        """RED: Test project registration creates soft link."""
        registry = temp_registry

        # Create mock project
        with tempfile.TemporaryDirectory() as project_dir:
            project_path = Path(project_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text('{"project_containers": {"project_hash": "abc123"}}')

            ports = {"qdrant_port": 6333, "ollama_port": 11434}
            registry.register_project_allocation(project_path, ports)

            # Verify soft link created
            links = list(registry.active_projects_path.iterdir())
            assert len(links) == 1
            assert links[0].is_symlink()
            assert links[0].resolve() == config_dir

    def test_port_allocation_updates_json_file(self, temp_registry):
        """RED: Test port allocation updates allocations file."""
        registry = temp_registry

        with tempfile.TemporaryDirectory() as project_dir:
            project_path = Path(project_dir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text('{"project_containers": {"project_hash": "abc123"}}')

            ports = {"qdrant_port": 6333, "ollama_port": 11434}
            registry.register_project_allocation(project_path, ports)

            # Calculate expected project hash from path
            expected_hash = registry._calculate_project_hash(project_path)

            # Verify JSON file updated
            with open(registry.port_allocations_file) as f:
                allocations = json.load(f)

            assert "6333" in allocations
            assert "11434" in allocations
            assert allocations["6333"]["project_hash"] == expected_hash
            assert allocations["11434"]["project_hash"] == expected_hash

    def test_port_exhaustion_raises_exception(self, temp_registry):
        """RED: Test port exhaustion scenario."""
        registry = temp_registry

        # Mock all ports as busy
        with patch.object(registry, "_is_port_bindable", return_value=False):
            with pytest.raises(PortExhaustionError):
                registry.find_available_port_for_service("qdrant")

    def test_sequential_allocation_avoids_conflicts(self, temp_registry):
        """RED: Test sequential allocations don't conflict."""
        registry = temp_registry

        # Allocate ports for multiple projects
        projects_ports: list[dict[str, int]] = []
        for i in range(3):
            exclude_ports: set[int] = set()
            for prev_ports in projects_ports:
                exclude_ports.update(prev_ports.values())

            ports = {
                "qdrant_port": registry.find_available_port_for_service(
                    "qdrant", exclude_ports
                ),
                "ollama_port": registry.find_available_port_for_service(
                    "ollama", exclude_ports
                ),
            }
            projects_ports.append(ports)

        # Verify no conflicts
        all_ports: list[int] = []
        for project_ports in projects_ports:
            all_ports.extend(project_ports.values())

        assert len(all_ports) == len(set(all_ports)), "Port conflicts found"

    @patch("socket.socket")
    def test_system_port_scanning(self, mock_socket, temp_registry):
        """RED: Test system port scanning detects busy ports."""
        registry = temp_registry

        # Mock socket to simulate port 6333 is busy
        mock_socket_instance = Mock()
        mock_socket.return_value.__enter__.return_value = mock_socket_instance

        def bind_side_effect(addr):
            if addr[1] == 6333:
                raise OSError("Port in use")
            return None

        mock_socket_instance.bind.side_effect = bind_side_effect

        # Should skip port 6333 and find next available
        port = registry.find_available_port_for_service("qdrant")
        assert port != 6333
        assert 6334 <= port <= 7333

    def test_load_current_allocations_empty_file(self, temp_registry):
        """RED: Test loading allocations from empty file."""
        registry = temp_registry
        allocated_ports = registry._load_current_allocations()
        assert allocated_ports == set()

    def test_load_current_allocations_with_data(self, temp_registry):
        """RED: Test loading allocations from file with data."""
        registry = temp_registry

        # Write test data to allocations file
        test_allocations = {
            "6333": {"project_hash": "test1", "service": "qdrant"},
            "11434": {"project_hash": "test2", "service": "ollama"},
        }

        with open(registry.port_allocations_file, "w") as f:
            json.dump(test_allocations, f)

        allocated_ports = registry._load_current_allocations()
        assert allocated_ports == {6333, 11434}

    def test_calculate_project_hash(self, temp_registry):
        """RED: Test project hash calculation from path."""
        registry = temp_registry

        with tempfile.TemporaryDirectory() as project_dir:
            project_path = Path(project_dir)
            hash1 = registry._calculate_project_hash(project_path)
            hash2 = registry._calculate_project_hash(project_path)

            # Should be deterministic
            assert hash1 == hash2
            assert len(hash1) == 8  # 8-character hash
            assert hash1.isalnum()  # Should be alphanumeric
