"""Tests for Docker Compose configuration validation and service detection."""

import os
import pytest

import json
from unittest.mock import patch

# Import new test infrastructure
from ...conftest import local_temporary_directory
from .infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def docker_compose_test_repo():
    """Create a test repository for Docker Compose validation tests."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.DOCKER_COMPOSE_VALIDATION
        )

        yield temp_dir


class TestDockerComposeValidation:
    """Test Docker Compose configuration generation and validation."""

    def create_config(self, test_dir, embedding_provider="ollama"):
        """Create configuration for specified embedding provider."""
        config_dir = test_dir / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        base_config = {
            "codebase_dir": str(test_dir),
            "embedding_provider": embedding_provider,
            "qdrant": {
                "host": "http://localhost:6333",
                "collection": "test_collection",
            },
            "exclude_patterns": ["*.git*", "__pycache__", "node_modules"],
        }

        if embedding_provider == "ollama":
            base_config["ollama"] = {
                "host": "http://localhost:11434",
                "model": "nomic-embed-text",
                "num_parallel": 1,
                "max_loaded_models": 1,
                "max_queue": 512,
            }
        elif embedding_provider == "voyage-ai":
            base_config["voyage_ai"] = {
                "model": "voyage-code-3",
                "api_key_env": "VOYAGE_API_KEY",
                "batch_size": 32,
                "max_retries": 3,
                "timeout": 30,
            }

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(base_config, f, indent=2)

        return config_file

    def test_required_services_ollama_provider(self, docker_compose_test_repo):
        """Test required services detection for Ollama provider."""
        test_dir = docker_compose_test_repo

        # Create Ollama configuration
        self.create_config(test_dir, "ollama")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Docker is available"

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(test_dir)
            config = config_manager.load()

            project_config_dir = test_dir / ".code-indexer"
            docker_manager = DockerManager(
                console=None, force_docker=True, project_config_dir=project_config_dir
            )

            # Test required services
            required_services = docker_manager.get_required_services(
                config.model_dump()
            )

            assert "qdrant" in required_services
            assert "data-cleaner" in required_services
            assert "ollama" in required_services
            assert len(required_services) == 3

    def test_required_services_voyage_ai_provider(self, docker_compose_test_repo):
        """Test required services detection for VoyageAI provider."""
        test_dir = docker_compose_test_repo

        # Set API key
        os.environ["VOYAGE_API_KEY"] = "test_key"

        # Create VoyageAI configuration
        self.create_config(test_dir, "voyage-ai")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Docker is available"

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(test_dir)
            config = config_manager.load()

            project_config_dir = test_dir / ".code-indexer"
            docker_manager = DockerManager(
                console=None, force_docker=True, project_config_dir=project_config_dir
            )

            # Test required services
            required_services = docker_manager.get_required_services(
                config.model_dump()
            )

            assert "qdrant" in required_services
            assert "data-cleaner" in required_services
            assert "ollama" not in required_services
            assert len(required_services) == 2

    def test_compose_config_ollama_provider(self, docker_compose_test_repo):
        """Test Docker Compose configuration generation for Ollama provider."""
        test_dir = docker_compose_test_repo

        # Create Ollama configuration
        self.create_config(test_dir, "ollama")

        # Mock Docker operations and ConfigManager to return ollama provider
        with (
            patch("code_indexer.services.docker_manager.subprocess.run") as mock_run,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            mock_run.return_value.returncode = 0

            # Mock the ConfigManager to return ollama as embedding provider
            mock_config = (
                mock_config_manager.create_with_backtrack.return_value.load.return_value
            )
            mock_config.embedding_provider = "ollama"
            mock_config.model_dump.return_value = {"embedding_provider": "ollama"}

            from code_indexer.services.docker_manager import DockerManager

            project_config_dir = test_dir / ".code-indexer"
            docker_manager = DockerManager(
                console=None,
                force_docker=True,
                project_config_dir=project_config_dir,
            )

            # Generate compose config with proper port allocation
            container_names = docker_manager._generate_container_names(test_dir)

            # Container names are generated dynamically by the DockerManager

            # Pass ollama as provider to ensure all ports are allocated
            config_dict = {"embedding_provider": "ollama"}
            ports = docker_manager.allocate_project_ports(test_dir, config_dict)

            # Build project config with all allocated ports
            project_config = {**container_names}
            for port_key in ports:
                project_config[port_key] = str(ports[port_key])
            compose_config = docker_manager.generate_compose_config(
                test_dir, project_config
            )

            # Validate structure
            assert "services" in compose_config
            assert "volumes" in compose_config

            services = compose_config["services"]

            # Should contain all required services
            assert "qdrant" in services
            assert "data-cleaner" in services
            assert "ollama" in services

            # Validate Ollama service configuration
            ollama_service = services["ollama"]
            assert "build" in ollama_service
            assert any(":11434" in port for port in ollama_service["ports"])
            assert "OLLAMA_NUM_PARALLEL=1" in ollama_service["environment"]
            assert "OLLAMA_MAX_LOADED_MODELS=1" in ollama_service["environment"]
            assert "OLLAMA_MAX_QUEUE=512" in ollama_service["environment"]

            # Validate Qdrant service configuration
            qdrant_service = services["qdrant"]
            assert "build" in qdrant_service
            assert any(":6333" in port for port in qdrant_service["ports"])

            # Validate data-cleaner service configuration
            cleaner_service = services["data-cleaner"]
            assert "build" in cleaner_service

    def test_compose_config_voyage_ai_provider(self, docker_compose_test_repo):
        """Test Docker Compose configuration generation for VoyageAI provider."""
        test_dir = docker_compose_test_repo

        # Set API key
        os.environ["VOYAGE_API_KEY"] = "test_key"

        # Create VoyageAI configuration
        self.create_config(test_dir, "voyage-ai")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            from code_indexer.services.docker_manager import DockerManager

            project_config_dir = test_dir / ".code-indexer"
            docker_manager = DockerManager(
                console=None,
                force_docker=True,
                project_config_dir=project_config_dir,
            )

            # Generate compose config with proper port allocation
            container_names = docker_manager._generate_container_names(test_dir)

            # Container names are generated dynamically by the DockerManager

            # VoyageAI doesn't need ollama, pass config to allocate_project_ports
            config_dict = {"embedding_provider": "voyage-ai"}
            ports = docker_manager.allocate_project_ports(test_dir, config_dict)

            # Build project config with only the ports that were allocated
            project_config = {**container_names}
            for port_key in ports:
                project_config[port_key] = str(ports[port_key])

            # Add ollama_port with a dummy value if not present (for generate_compose_config compatibility)
            if "ollama_port" not in project_config:
                project_config["ollama_port"] = "11434"  # Default ollama port
            compose_config = docker_manager.generate_compose_config(
                test_dir, project_config
            )

            # Validate structure
            assert "services" in compose_config
            assert "volumes" in compose_config

            services = compose_config["services"]

            # Should contain only required services (no Ollama)
            assert "qdrant" in services
            assert "data-cleaner" in services
            assert "ollama" not in services

            # Should have exactly 2 services
            assert len(services) == 2

    def test_service_state_detection_methods(self, docker_compose_test_repo):
        """Test service state detection methods."""
        test_dir = docker_compose_test_repo

        # Create configuration
        self.create_config(test_dir, "ollama")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            from code_indexer.services.docker_manager import DockerManager

            project_config_dir = test_dir / ".code-indexer"
            docker_manager = DockerManager(
                console=None,
                force_docker=True,
                project_config_dir=project_config_dir,
            )

            # Mock individual state check methods
            with (
                patch.object(docker_manager, "_container_exists") as mock_exists,
                patch.object(docker_manager, "_container_running") as mock_running,
                patch.object(docker_manager, "_container_healthy") as mock_healthy,
                patch.object(
                    docker_manager, "_container_up_to_date"
                ) as mock_up_to_date,
            ):
                # Test different scenarios
                test_cases = [
                    # exists, running, healthy, up_to_date
                    (True, True, True, True),  # Fully healthy
                    (True, True, False, True),  # Running but unhealthy
                    (True, False, False, True),  # Exists but not running
                    (False, False, False, False),  # Doesn't exist
                ]

                for exists, running, healthy, up_to_date in test_cases:
                    mock_exists.return_value = exists
                    mock_running.return_value = running
                    mock_healthy.return_value = healthy
                    mock_up_to_date.return_value = up_to_date

                    container_names = docker_manager._generate_container_names(test_dir)

                    # Container names are generated dynamically by the DockerManager

                    # Pass ollama as provider to ensure all ports are allocated
                    config_dict = {"embedding_provider": "ollama"}
                    ports = docker_manager.allocate_project_ports(test_dir, config_dict)

                    # Build project config with all allocated ports
                    project_config = {**container_names}
                    for port_key in ports:
                        project_config[port_key] = str(ports[port_key])
                    state = docker_manager.get_service_state(
                        "test_service", project_config
                    )

                    assert state["exists"] == exists
                    assert state["running"] == running
                    assert state["healthy"] == healthy
                    assert state["up_to_date"] == up_to_date

    def test_compose_config_with_different_providers(self, docker_compose_test_repo):
        """Test that compose config changes based on provider configuration."""
        test_dir = docker_compose_test_repo

        # Test with different embedding providers
        providers = ["ollama", "voyage-ai"]

        for provider in providers:
            if provider == "voyage-ai":
                os.environ["VOYAGE_API_KEY"] = "test_key"

            self.create_config(test_dir, provider)

            with (
                patch(
                    "code_indexer.services.docker_manager.subprocess.run"
                ) as mock_run,
                patch("code_indexer.config.ConfigManager") as mock_config_manager,
            ):
                mock_run.return_value.returncode = 0

                # Mock the ConfigManager to return the current provider
                mock_config = (
                    mock_config_manager.create_with_backtrack.return_value.load.return_value
                )
                mock_config.embedding_provider = provider
                mock_config.model_dump.return_value = {"embedding_provider": provider}

                from code_indexer.services.docker_manager import DockerManager

                docker_manager = DockerManager(
                    console=None,
                    force_docker=True,
                )

                # Generate compose config with proper port allocation
                container_names = docker_manager._generate_container_names(test_dir)

                # Container names are generated dynamically by the DockerManager

                # Pass the current provider config
                config_dict = {"embedding_provider": provider}
                ports = docker_manager.allocate_project_ports(test_dir, config_dict)

                # Build project config with only the ports that were allocated
                project_config = {**container_names}
                for port_key in ports:
                    project_config[port_key] = str(ports[port_key])

                # Add ollama_port with a dummy value if not present (for generate_compose_config compatibility)
                if "ollama_port" not in project_config:
                    project_config["ollama_port"] = "11434"  # Default ollama port
                compose_config = docker_manager.generate_compose_config(
                    test_dir, project_config
                )
                services = compose_config["services"]

                if provider == "ollama":
                    assert "ollama" in services
                    assert len(services) == 3  # qdrant, data-cleaner, ollama
                elif provider == "voyage-ai":
                    assert "ollama" not in services
                    assert len(services) == 2  # qdrant, data-cleaner

                # Always should have these
                assert "qdrant" in services
                assert "data-cleaner" in services

    def test_compose_config_volumes_and_networks(self, docker_compose_test_repo):
        """Test that compose config includes proper volumes and networks."""
        test_dir = docker_compose_test_repo

        self.create_config(test_dir, "ollama")

        with (
            patch("code_indexer.services.docker_manager.subprocess.run") as mock_run,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            mock_run.return_value.returncode = 0

            # Mock the ConfigManager to return ollama as embedding provider
            mock_config = (
                mock_config_manager.create_with_backtrack.return_value.load.return_value
            )
            mock_config.embedding_provider = "ollama"
            mock_config.model_dump.return_value = {"embedding_provider": "ollama"}

            from code_indexer.services.docker_manager import DockerManager

            project_config_dir = test_dir / ".code-indexer"
            docker_manager = DockerManager(
                console=None,
                force_docker=True,
                project_config_dir=project_config_dir,
            )

            # Generate compose config with proper port allocation
            container_names = docker_manager._generate_container_names(test_dir)

            # Container names are generated dynamically by the DockerManager

            # Pass ollama as provider to ensure all ports are allocated
            config_dict = {"embedding_provider": "ollama"}
            ports = docker_manager.allocate_project_ports(test_dir, config_dict)

            # Build project config with all allocated ports
            project_config = {**container_names}
            for port_key in ports:
                project_config[port_key] = str(ports[port_key])
            compose_config = docker_manager.generate_compose_config(
                test_dir, project_config
            )

            # Check volumes (CoW architecture uses project-specific paths for qdrant, named volumes for ollama)
            assert "volumes" in compose_config
            volumes = compose_config["volumes"]
            # Qdrant uses project-specific bind mounts, Ollama uses named volumes
            assert "ollama_data" in volumes

            # Check that services use the appropriate volume configurations
            services = compose_config["services"]
            qdrant_volumes = services["qdrant"]["volumes"]
            ollama_volumes = services["ollama"]["volumes"]

            # Qdrant should use project-specific bind mount (CoW architecture)
            # The volume should be relative path from project root: ./qdrant:/qdrant/storage
            assert any("./qdrant:/qdrant/storage" in vol for vol in qdrant_volumes)
            # Ollama should use named volume
            assert any("ollama_data" in vol for vol in ollama_volumes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
