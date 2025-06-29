"""Tests for Docker Compose configuration validation and service detection."""

import os
import tempfile
import shutil
import pytest
import json
from pathlib import Path
from unittest.mock import patch


class TestDockerComposeValidation:
    """Test Docker Compose configuration generation and validation."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment for each test."""
        # Create temporary directory for test
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Store original environment
        self.original_env = dict(os.environ)

        yield

        # Cleanup
        os.chdir(self.original_cwd)
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

        # Restore environment
        os.environ.clear()
        os.environ.update(self.original_env)

    def create_config(self, embedding_provider="ollama"):
        """Create configuration for specified embedding provider."""
        config_dir = self.test_dir / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        base_config = {
            "codebase_dir": str(self.test_dir),
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

    def test_required_services_ollama_provider(self):
        """Test required services detection for Ollama provider."""
        # Create Ollama configuration
        self.create_config("ollama")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Docker is available"

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Test required services
            required_services = docker_manager.get_required_services(
                config.model_dump()
            )

            assert "qdrant" in required_services
            assert "data-cleaner" in required_services
            assert "ollama" in required_services
            assert len(required_services) == 3

    def test_required_services_voyage_ai_provider(self):
        """Test required services detection for VoyageAI provider."""
        # Set API key
        os.environ["VOYAGE_API_KEY"] = "test_key"

        # Create VoyageAI configuration
        self.create_config("voyage-ai")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Docker is available"

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Test required services
            required_services = docker_manager.get_required_services(
                config.model_dump()
            )

            assert "qdrant" in required_services
            assert "data-cleaner" in required_services
            assert "ollama" not in required_services
            assert len(required_services) == 2

    def test_compose_config_ollama_provider(self):
        """Test Docker Compose configuration generation for Ollama provider."""
        # Create Ollama configuration
        self.create_config("ollama")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Generate compose config
            compose_config = docker_manager.generate_compose_config()

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

    def test_compose_config_voyage_ai_provider(self):
        """Test Docker Compose configuration generation for VoyageAI provider."""
        # Set API key
        os.environ["VOYAGE_API_KEY"] = "test_key"

        # Create VoyageAI configuration
        self.create_config("voyage-ai")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Generate compose config
            compose_config = docker_manager.generate_compose_config()

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

    def test_service_state_detection_methods(self):
        """Test service state detection methods."""
        # Create configuration
        self.create_config("ollama")

        # Mock Docker operations
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Mock individual state check methods
            with patch.object(
                docker_manager, "_container_exists"
            ) as mock_exists, patch.object(
                docker_manager, "_container_running"
            ) as mock_running, patch.object(
                docker_manager, "_container_healthy"
            ) as mock_healthy, patch.object(
                docker_manager, "_container_up_to_date"
            ) as mock_up_to_date:
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

                    state = docker_manager.get_service_state("test_service")

                    assert state["exists"] == exists
                    assert state["running"] == running
                    assert state["healthy"] == healthy
                    assert state["up_to_date"] == up_to_date

    def test_compose_config_with_different_providers(self):
        """Test that compose config changes based on provider configuration."""
        # Test with different embedding providers
        providers = ["ollama", "voyage-ai"]

        for provider in providers:
            if provider == "voyage-ai":
                os.environ["VOYAGE_API_KEY"] = "test_key"

            self.create_config(provider)

            with patch(
                "code_indexer.services.docker_manager.subprocess.run"
            ) as mock_run:
                mock_run.return_value.returncode = 0

                from code_indexer.services.docker_manager import DockerManager
                from code_indexer.config import ConfigManager

                config_manager = ConfigManager.create_with_backtrack(self.test_dir)
                config = config_manager.load()

                docker_manager = DockerManager(
                    console=None, force_docker=True, main_config=config.model_dump()
                )

                # Generate compose config
                compose_config = docker_manager.generate_compose_config()
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

    def test_compose_config_volumes_and_networks(self):
        """Test that compose config includes proper volumes and networks."""
        self.create_config("ollama")

        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Generate compose config
            compose_config = docker_manager.generate_compose_config()

            # Check volumes
            assert "volumes" in compose_config
            volumes = compose_config["volumes"]
            assert "qdrant_data" in volumes
            assert "ollama_data" in volumes

            # Check that services use the volumes
            services = compose_config["services"]
            qdrant_volumes = services["qdrant"]["volumes"]
            ollama_volumes = services["ollama"]["volumes"]

            # Should have persistent volume mounts
            assert any("qdrant_data" in vol for vol in qdrant_volumes)
            assert any("ollama_data" in vol for vol in ollama_volumes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
