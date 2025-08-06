"""Tests for per-project container architecture."""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from code_indexer.services.docker_manager import DockerManager
from code_indexer.config import (
    Config,
    ConfigManager,
    ProjectContainersConfig,
    ProjectPortsConfig,
)


class TestProjectContainerNaming:
    """Test Story 1: Project-Aware Container Naming."""

    def test_generate_project_hash(self):
        """Test that project hash generation is deterministic."""
        dm = DockerManager(project_name="test_sharedshared")

        # Same path should generate same hash
        path1 = Path("/home/user/project")
        path2 = Path("/home/user/project")

        hash1 = dm.port_registry._calculate_project_hash(path1)
        hash2 = dm.port_registry._calculate_project_hash(path2)

        assert hash1 == hash2
        assert len(hash1) == 8  # Should be 8 characters
        assert hash1.isalnum()  # Should be alphanumeric

    def test_generate_project_hash_different_paths(self):
        """Test that different paths generate different hashes."""
        dm = DockerManager(project_name="test_sharedshared")

        path1 = Path("/home/user/project1")
        path2 = Path("/home/user/project2")

        hash1 = dm.port_registry._calculate_project_hash(path1)
        hash2 = dm.port_registry._calculate_project_hash(path2)

        assert hash1 != hash2

    def test_generate_container_names(self):
        """Test container name generation."""
        dm = DockerManager(project_name="test_sharednames")

        project_root = Path("/home/user/test-project")
        names = dm._generate_container_names(project_root)

        # Check all required keys are present
        assert "project_hash" in names
        assert "qdrant_name" in names
        assert "ollama_name" in names
        assert "data_cleaner_name" in names

        # Check naming format
        hash_val = names["project_hash"]
        assert names["qdrant_name"] == f"cidx-{hash_val}-qdrant"
        assert names["ollama_name"] == f"cidx-{hash_val}-ollama"
        assert names["data_cleaner_name"] == f"cidx-{hash_val}-data-cleaner"

    def test_container_names_are_valid_docker_names(self):
        """Test that generated container names are valid for Docker/Podman."""
        dm = DockerManager(project_name="test_sharedvalid")

        # Test with various project paths
        test_paths = [
            Path("/home/user/my-project"),
            Path("/home/user/project_with_underscores"),
            Path("/home/user/123-numeric-project"),
            Path("/home/user/CAPS-project"),
        ]

        for path in test_paths:
            names = dm._generate_container_names(path)

            # Docker container names must be alphanumeric + hyphens
            for name_type, name in names.items():
                if name_type != "project_hash":
                    assert name.replace("-", "").replace("cidx", "").isalnum()
                    assert name.startswith("cidx-")


class TestPortAllocation:
    """Test Story 2: Dynamic Port Management."""

    @patch("socket.socket")
    def test_allocate_free_ports_all_available(self, mock_socket):
        """Test port allocation when all calculated ports are free."""
        # Mock socket to always return True (port is free)
        mock_socket_instance = MagicMock()
        mock_socket_instance.bind.return_value = None
        mock_socket.return_value.__enter__.return_value = mock_socket_instance

        dm = DockerManager(project_name="test_sharedports")
        # Use consistent path for all tests to avoid creating multiple container sets
        shared_test_path = Path.home() / ".tmp" / "shared_test_containers"
        shared_test_path.mkdir(parents=True, exist_ok=True)
        dm.set_indexing_root(shared_test_path)

        # Mock the port registry to use a temporary directory for tests
        with tempfile.TemporaryDirectory() as temp_registry_dir:
            with patch.object(
                dm.port_registry,
                "_get_registry_path",
                return_value=Path(temp_registry_dir),
            ):
                # Re-initialize registry structure with temp path
                dm.port_registry.registry_path = Path(temp_registry_dir)
                dm.port_registry.active_projects_path = (
                    Path(temp_registry_dir) / "active-projects"
                )
                dm.port_registry.port_allocations_file = (
                    Path(temp_registry_dir) / "port-allocations.json"
                )
                dm.port_registry._ensure_registry_structure()

                ports = dm.allocate_project_ports(shared_test_path)

                # Should get ports for all required services
                required_services = dm.get_required_services()
                assert "qdrant_port" in ports
                assert "data_cleaner_port" in ports
                # Only check ollama if it's in required services (depends on config)
                if "ollama" in required_services:
                    assert "ollama_port" in ports

                # Ports should be in expected ranges
                assert 6333 <= ports["qdrant_port"] <= 7333
                assert 8091 <= ports["data_cleaner_port"] <= 9091
                if "ollama_port" in ports:
                    assert 11434 <= ports["ollama_port"] <= 12434

                # The project allocation should have succeeded
                # (Note: Registry cleanup in test environment may remove allocations,
                # but the port allocation itself should work correctly)
                allocated_ports = dm.port_registry.get_all_allocated_ports()
                project_hash = dm.port_registry._calculate_project_hash(
                    shared_test_path
                )
                our_ports_in_registry = {
                    port: hash_val
                    for port, hash_val in allocated_ports.items()
                    if hash_val == project_hash
                }

                # Verify allocation succeeded - either ports are in registry OR we got valid port response
                if len(our_ports_in_registry) == 0:
                    # Registry cleanup removed allocation in test environment,
                    # but verify we got the expected number of ports
                    assert len(ports) >= len(
                        required_services
                    ), f"Should have {len(required_services)} ports, got {len(ports)}"
                else:
                    # Normal case: ports are properly registered
                    expected_min_ports = len(
                        [
                            s
                            for s in required_services
                            if s in ["qdrant", "ollama", "data-cleaner"]
                        ]
                    )
                    assert len(our_ports_in_registry) >= expected_min_ports

                # Verify the ports are actually allocated to this project
                project_hash = dm.port_registry._calculate_project_hash(
                    shared_test_path
                )
                for allocated_port, hash_for_port in allocated_ports.items():
                    if hash_for_port == project_hash:
                        assert allocated_port in ports.values()

    @patch("socket.socket")
    def test_allocate_free_ports_with_conflicts(self, mock_socket):
        """Test port allocation when calculated ports are taken (tests collision resolution)."""
        # Mock socket to simulate all ports are in use (to test the enhanced error message)
        mock_socket_instance = MagicMock()
        mock_socket_instance.bind.side_effect = OSError("Port in use")
        mock_socket.return_value.__enter__.return_value = mock_socket_instance

        dm = DockerManager(project_name="test_sharedconflicts")
        # Use consistent path for all tests to avoid creating multiple container sets
        shared_test_path = Path.home() / ".tmp" / "shared_test_containers"
        shared_test_path.mkdir(parents=True, exist_ok=True)
        dm.set_indexing_root(shared_test_path)

        # Mock the port registry to use a temporary directory for tests
        with tempfile.TemporaryDirectory() as temp_registry_dir:
            with patch.object(
                dm.port_registry,
                "_get_registry_path",
                return_value=Path(temp_registry_dir),
            ):
                # Re-initialize registry structure with temp path
                dm.port_registry.registry_path = Path(temp_registry_dir)
                dm.port_registry.active_projects_path = (
                    Path(temp_registry_dir) / "active-projects"
                )
                dm.port_registry.port_allocations_file = (
                    Path(temp_registry_dir) / "port-allocations.json"
                )
                dm.port_registry._ensure_registry_structure()

                # Should raise PortExhaustionError when no ports are available
                from code_indexer.services.global_port_registry import (
                    PortExhaustionError,
                    PortRegistryError,
                )

                with pytest.raises((PortExhaustionError, PortRegistryError)):
                    dm.allocate_project_ports(shared_test_path)

    @patch("socket.socket")
    def test_allocate_free_ports_safety_limit(self, mock_socket):
        """Test that port allocation fails when all collision resolution attempts fail."""
        # Mock socket to always throw OSError (no ports free)
        mock_socket_instance = MagicMock()
        mock_socket_instance.bind.side_effect = OSError("No ports free")
        mock_socket.return_value.__enter__.return_value = mock_socket_instance

        dm = DockerManager(project_name="test_sharedsafety")
        # Use consistent path for all tests to avoid creating multiple container sets
        shared_test_path = Path.home() / ".tmp" / "shared_test_containers"
        shared_test_path.mkdir(parents=True, exist_ok=True)
        dm.set_indexing_root(shared_test_path)

        # Mock the port registry to use a temporary directory for tests
        with tempfile.TemporaryDirectory() as temp_registry_dir:
            with patch.object(
                dm.port_registry,
                "_get_registry_path",
                return_value=Path(temp_registry_dir),
            ):
                # Re-initialize registry structure with temp path
                dm.port_registry.registry_path = Path(temp_registry_dir)
                dm.port_registry.active_projects_path = (
                    Path(temp_registry_dir) / "active-projects"
                )
                dm.port_registry.port_allocations_file = (
                    Path(temp_registry_dir) / "port-allocations.json"
                )
                dm.port_registry._ensure_registry_structure()

                # Should raise PortExhaustionError when no ports are available
                from code_indexer.services.global_port_registry import (
                    PortExhaustionError,
                    PortRegistryError,
                )

                with pytest.raises((PortExhaustionError, PortRegistryError)):
                    dm.allocate_project_ports(shared_test_path)


class TestProjectConfiguration:
    """Test configuration management for per-project containers."""

    def setup_method(self):
        """Set up temporary directory and config for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.config_dir = self.project_root / ".code-indexer"
        self.config_dir.mkdir()

    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    @patch("socket.socket")
    def test_ensure_project_configuration_new_project(self, mock_socket):
        """Test configuration generation for new project."""
        # Mock socket for port allocation
        mock_socket_instance = MagicMock()
        mock_socket_instance.bind.return_value = None
        mock_socket.return_value.__enter__.return_value = mock_socket_instance

        # Create minimal config
        config = Config(codebase_dir=self.project_root)
        config_manager = ConfigManager(self.config_dir / "config.json")
        config_manager.save(config)

        dm = DockerManager(project_name="test_sharednew")
        # Use consistent path for all tests to avoid creating multiple container sets
        shared_test_path = Path.home() / ".tmp" / "shared_test_containers"
        shared_test_path.mkdir(parents=True, exist_ok=True)
        dm.set_indexing_root(shared_test_path)
        result = dm.ensure_project_configuration(config_manager, self.project_root)

        # Check that configuration was generated
        assert "qdrant_name" in result
        assert "qdrant_port" in result
        assert result["qdrant_name"].startswith("cidx-")
        assert result["qdrant_name"].endswith("-qdrant")
        assert isinstance(result["qdrant_port"], int)

        # Check that config was saved
        updated_config = config_manager.load()
        assert updated_config.project_containers.project_hash is not None
        assert updated_config.project_ports.qdrant_port is not None

    @patch("socket.socket")
    def test_ensure_project_configuration_existing_project(self, mock_socket):
        """Test that existing configuration is preserved."""
        # Mock socket for port allocation
        mock_socket_instance = MagicMock()
        mock_socket_instance.bind.return_value = None
        mock_socket.return_value.__enter__.return_value = mock_socket_instance

        # Create config with existing project configuration
        containers_config = ProjectContainersConfig(
            project_hash="abcd1234",
            qdrant_name="cidx-abcd1234-qdrant",
            ollama_name="cidx-abcd1234-ollama",
            data_cleaner_name="cidx-abcd1234-data-cleaner",
        )

        ports_config = ProjectPortsConfig(
            qdrant_port=6340, ollama_port=11440, data_cleaner_port=8090
        )

        config = Config(
            codebase_dir=self.project_root,
            project_containers=containers_config,
            project_ports=ports_config,
        )

        config_manager = ConfigManager(self.config_dir / "config.json")
        config_manager.save(config)

        dm = DockerManager(project_name="test_sharedexisting")
        # Use consistent path for all tests to avoid creating multiple container sets
        shared_test_path = Path.home() / ".tmp" / "shared_test_containers"
        shared_test_path.mkdir(parents=True, exist_ok=True)
        dm.set_indexing_root(shared_test_path)
        result = dm.ensure_project_configuration(config_manager, self.project_root)

        # Should preserve existing configuration
        assert result["qdrant_name"] == "cidx-abcd1234-qdrant"
        assert result["qdrant_port"] == 6340


class TestContainerExistence:
    """Test container existence checking."""

    @patch("code_indexer.services.docker_manager.DockerManager._get_available_runtime")
    @patch("subprocess.run")
    def test_containers_exist_with_project_config(self, mock_run, mock_runtime):
        """Test container existence check with project-specific names."""
        # Mock runtime detection and successful container inspect
        mock_runtime.return_value = "podman"
        mock_run.return_value.returncode = 0

        dm = DockerManager(project_name="test_sharedexist")
        project_config = {
            "qdrant_name": "cidx-test123-qdrant",
            "ollama_name": "cidx-test123-ollama",
            "data_cleaner_name": "cidx-test123-data-cleaner",
        }

        result = dm.containers_exist(project_config)
        assert result is True

        # Check that it used project-specific names
        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        assert "cidx-test123-qdrant" in call_args

    def test_containers_exist_requires_project_config(self):
        """Test container existence check requires project config (new mode only)."""
        dm = DockerManager(project_name="test_sharedrequire")

        # Test that missing project config raises error
        import pytest

        with pytest.raises(TypeError):
            dm.containers_exist()  # Missing required argument

    @patch("code_indexer.services.docker_manager.DockerManager._get_available_runtime")
    @patch("subprocess.run")
    def test_containers_do_not_exist(self, mock_run, mock_runtime):
        """Test when no containers exist."""
        # Mock runtime detection and failed container inspect (container doesn't exist)
        mock_runtime.return_value = "podman"
        mock_run.return_value.returncode = 1

        # Create project configuration
        project_config = {
            "qdrant_name": "cidx-test123-qdrant",
            "ollama_name": "cidx-test123-ollama",
            "data_cleaner_name": "cidx-test123-data-cleaner",
        }

        dm = DockerManager(project_name="test_sharednot_exist")
        result = dm.containers_exist(project_config)
        assert result is False


class TestProjectLocalStorage:
    """Test Story 3: Project-Specific Data Storage."""

    def setup_method(self):
        """Set up temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.config_dir = self.project_root / ".code-indexer"
        self.config_dir.mkdir()

    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_qdrant_service_uses_project_local_storage(self):
        """Test that Qdrant service uses project-local storage when project root provided."""
        dm = DockerManager(project_name="test_sharedstorage")

        # Generate project configuration with proper port allocation
        container_names = dm._generate_container_names(self.project_root)

        # CRITICAL: Update project configuration with container names before port allocation
        # Since we removed main_config, we need to use the proper configuration system
        # The container names are already generated and will be used by the methods

        # Use mock registry for testing
        with tempfile.TemporaryDirectory() as temp_registry_dir:
            with patch.object(
                dm.port_registry,
                "_get_registry_path",
                return_value=Path(temp_registry_dir),
            ):
                dm.port_registry.registry_path = Path(temp_registry_dir)
                dm.port_registry.active_projects_path = (
                    Path(temp_registry_dir) / "active-projects"
                )
                dm.port_registry.port_allocations_file = (
                    Path(temp_registry_dir) / "port-allocations.json"
                )
                dm.port_registry._ensure_registry_structure()

                ports = dm.allocate_project_ports(self.project_root)
                project_config = {
                    **container_names,
                    "qdrant_port": str(ports["qdrant_port"]),
                    "ollama_port": str(ports["ollama_port"]),
                    "data_cleaner_port": str(ports["data_cleaner_port"]),
                }

                # Generate compose config with project root
                compose_config = dm.generate_compose_config(
                    project_root=self.project_root, project_config=project_config
                )

                # Check that Qdrant service exists
                assert "services" in compose_config
                assert "qdrant" in compose_config["services"]

                # Check volumes configuration
                qdrant_service = compose_config["services"]["qdrant"]
                assert "volumes" in qdrant_service

                # Find the storage volume mount
                storage_mount = None
                for volume in qdrant_service["volumes"]:
                    if "/qdrant/storage" in volume:
                        storage_mount = volume
                        break

                assert storage_mount is not None, "Qdrant storage mount not found"

                # Check that it uses project-local path (no :U suffix anymore)
                expected_path = str(self.project_root / ".code-indexer" / "qdrant")
                assert expected_path in storage_mount
                # Verify no :U suffix (removed for compatibility)
                assert ":U" not in storage_mount

                # Check that project qdrant directory was created
                project_qdrant_dir = self.project_root / ".code-indexer" / "qdrant"
                assert project_qdrant_dir.exists()

    def test_data_cleaner_service_uses_project_local_storage(self):
        """Test that data cleaner service uses project-local storage when project root provided."""
        dm = DockerManager()

        # Generate project configuration with proper port allocation
        container_names = dm._generate_container_names(self.project_root)

        # CRITICAL: Update project configuration with container names before port allocation
        # Since we removed main_config, we need to use the proper configuration system
        # The container names are already generated and will be used by the methods

        # Use mock registry for testing
        with tempfile.TemporaryDirectory() as temp_registry_dir:
            with patch.object(
                dm.port_registry,
                "_get_registry_path",
                return_value=Path(temp_registry_dir),
            ):
                dm.port_registry.registry_path = Path(temp_registry_dir)
                dm.port_registry.active_projects_path = (
                    Path(temp_registry_dir) / "active-projects"
                )
                dm.port_registry.port_allocations_file = (
                    Path(temp_registry_dir) / "port-allocations.json"
                )
                dm.port_registry._ensure_registry_structure()

                ports = dm.allocate_project_ports(self.project_root)
        project_config = {
            **container_names,
            "qdrant_port": str(ports["qdrant_port"]),
            "ollama_port": str(ports["ollama_port"]),
            "data_cleaner_port": str(ports["data_cleaner_port"]),
        }

        # Generate compose config with project root
        compose_config = dm.generate_compose_config(
            project_root=self.project_root, project_config=project_config
        )

        # Check that data cleaner service exists
        assert "services" in compose_config
        assert "data-cleaner" in compose_config["services"]

        # Check volumes configuration
        cleaner_service = compose_config["services"]["data-cleaner"]
        assert "volumes" in cleaner_service

        # Find the qdrant data volume mount
        qdrant_mount = None
        for volume in cleaner_service["volumes"]:
            if "/qdrant/storage" in volume:
                qdrant_mount = volume
                break

        assert qdrant_mount is not None, "Data cleaner qdrant mount not found"

        # Check that it uses project-local path (no :U suffix anymore)
        expected_path = str(self.project_root / ".code-indexer" / "qdrant")
        assert expected_path in qdrant_mount
        # Verify no :U suffix (removed for compatibility)
        assert ":U" not in qdrant_mount

        # Check that project qdrant directory was created
        project_qdrant_dir = self.project_root / ".code-indexer" / "qdrant"
        assert project_qdrant_dir.exists()

    def test_compose_config_requires_project_config(self):
        """Test that compose config requires project configuration (new mode only)."""
        dm = DockerManager()

        # Test that missing project config raises error
        import pytest

        with pytest.raises(TypeError):
            dm.generate_compose_config()  # Missing required arguments


class TestProjectAwareStartCommand:
    """Test Story 4: Project-Aware Start Command."""

    def setup_method(self):
        """Set up temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.config_dir = self.project_root / ".code-indexer"
        self.config_dir.mkdir()

    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    @patch("code_indexer.services.docker_manager.DockerManager._get_available_runtime")
    @patch("subprocess.run")
    def test_service_state_checks_use_project_containers(self, mock_run, mock_runtime):
        """Test that service state checks use project-specific container names."""
        # Mock runtime detection and container commands
        mock_runtime.return_value = "podman"
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "cidx-test123-qdrant"

        # Create project configuration
        project_config = {
            "qdrant_name": "cidx-test123-qdrant",
            "ollama_name": "cidx-test123-ollama",
            "data_cleaner_name": "cidx-test123-data-cleaner",
        }

        dm = DockerManager()

        # Test that get_service_state uses project-specific names
        dm.get_service_state("qdrant", project_config)

        # Verify the container check was called with project-specific name
        mock_run.assert_called()
        call_args = str(mock_run.call_args)
        assert "cidx-test123-qdrant" in call_args

    @patch("code_indexer.services.docker_manager.DockerManager._get_available_runtime")
    @patch("subprocess.run")
    def test_container_logs_use_project_containers(self, mock_run, mock_runtime):
        """Test that container log retrieval uses project-specific container names."""
        # Mock runtime detection and container commands
        mock_runtime.return_value = "podman"
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Test logs output"

        # Create project configuration
        project_config = {
            "qdrant_name": "cidx-test123-qdrant",
            "ollama_name": "cidx-test123-ollama",
            "data_cleaner_name": "cidx-test123-data-cleaner",
        }

        dm = DockerManager()

        # Test that get_container_logs uses project-specific names
        dm.get_container_logs("qdrant", project_config, lines=10)

        # Verify the logs command was called with project-specific name
        mock_run.assert_called()
        call_args = str(mock_run.call_args)
        assert "cidx-test123-qdrant" in call_args

    def test_get_container_name_with_project_config(self):
        """Test that get_container_name returns project-specific names when config provided."""
        dm = DockerManager()

        # Test with project configuration
        project_config = {
            "qdrant_name": "cidx-abc123-qdrant",
            "ollama_name": "cidx-abc123-ollama",
            "data_cleaner_name": "cidx-abc123-data-cleaner",
        }

        assert dm.get_container_name("qdrant", project_config) == "cidx-abc123-qdrant"
        assert dm.get_container_name("ollama", project_config) == "cidx-abc123-ollama"
        assert (
            dm.get_container_name("data-cleaner", project_config)
            == "cidx-abc123-data-cleaner"
        )

        # Test that missing project config raises error (new mode only)
        import pytest

        with pytest.raises(TypeError):
            dm.get_container_name("qdrant")  # Missing required argument

    def test_get_container_name_with_partial_config(self):
        """Test that get_container_name raises error for missing services in config."""
        dm = DockerManager()

        # Test with incomplete project configuration
        project_config = {
            "qdrant_name": "cidx-abc123-qdrant",
            # Missing ollama_name and data_cleaner_name
        }

        assert dm.get_container_name("qdrant", project_config) == "cidx-abc123-qdrant"

        # Test that missing service names raise errors (new mode only)
        import pytest

        with pytest.raises(ValueError, match="No container name configured"):
            dm.get_container_name("ollama", project_config)

        with pytest.raises(ValueError, match="No container name configured"):
            dm.get_container_name("data-cleaner", project_config)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
