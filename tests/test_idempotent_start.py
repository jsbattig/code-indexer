"""Tests for idempotent start behavior."""

import os
import tempfile
import shutil
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestIdempotentStart:
    """Test that start operations are idempotent and don't duplicate work."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment for each test."""
        # Create temporary directory for test
        self.test_dir = Path(tempfile.mkdtemp())
        try:
            self.original_cwd = os.getcwd()
        except (FileNotFoundError, OSError):
            # If current directory doesn't exist, use a safe default
            self.original_cwd = str(Path.home())
        os.chdir(self.test_dir)

        # Store original environment
        self.original_env = dict(os.environ)

        yield

        # Cleanup
        try:
            os.chdir(self.original_cwd)
        except (FileNotFoundError, OSError):
            # If original directory doesn't exist, go to home
            os.chdir(Path.home())
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

    def test_idempotent_start_services_all_healthy(self):
        """Test that start_services is idempotent when all services are healthy."""
        self.create_config("ollama")

        # Mock Docker operations
        with patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run, patch(
            "code_indexer.services.docker_manager.subprocess.Popen"
        ) as mock_popen:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Docker is available"

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Mock all services as healthy
            with patch.object(docker_manager, "get_service_state") as mock_state:
                mock_state.return_value = {
                    "exists": True,
                    "running": True,
                    "healthy": True,
                    "up_to_date": True,
                }

                # Call start_services - should be idempotent
                result = docker_manager.start_services(recreate=False)

                # Should return True but not actually start anything
                assert result is True

                # Docker compose up should not be called since all services are healthy
                mock_popen.assert_not_called()

    def test_idempotent_start_command_first_run(self):
        """Test start command behavior on first run."""
        # Mock the CLI command
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with patch("code_indexer.cli.DockerManager") as mock_docker_class, patch(
            "code_indexer.cli.EmbeddingProviderFactory"
        ) as mock_factory, patch("code_indexer.cli.QdrantClient") as mock_qdrant_class:
            # Setup mocks
            mock_docker = MagicMock()
            mock_docker.is_docker_available.return_value = True
            mock_docker.is_compose_available.return_value = True
            mock_docker.get_required_services.return_value = [
                "qdrant",
                "ollama",
                "data-cleaner",
            ]
            mock_docker.get_service_state.return_value = {
                "exists": False,
                "running": False,
                "healthy": False,
                "up_to_date": False,
            }
            mock_docker.start_services.return_value = True
            mock_docker.wait_for_services.return_value = True
            mock_docker_class.return_value = mock_docker

            mock_provider = MagicMock()
            mock_provider.health_check.return_value = True
            mock_provider.get_provider_name.return_value = "ollama"
            mock_provider.model_exists.return_value = True
            mock_factory.create.return_value = mock_provider

            mock_qdrant = MagicMock()
            mock_qdrant.health_check.return_value = True
            mock_qdrant.ensure_collection.return_value = True
            mock_qdrant_class.return_value = mock_qdrant

            # Run start command
            result = runner.invoke(cli, ["start", "--quiet"])

            assert result.exit_code == 0

            # Verify setup was called
            mock_docker.start_services.assert_called_once_with(recreate=False)
            mock_docker.wait_for_services.assert_called_once()
            mock_provider.health_check.assert_called_once()
            mock_qdrant.health_check.assert_called_once()
            mock_qdrant.ensure_collection.assert_called_once()

    def test_idempotent_start_voyage_ai_no_ollama(self):
        """Test that VoyageAI setup doesn't involve Ollama at all."""
        os.environ["VOYAGE_API_KEY"] = "test_key"
        self.create_config("voyage-ai")

        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with patch("code_indexer.cli.DockerManager") as mock_docker_class, patch(
            "code_indexer.cli.EmbeddingProviderFactory"
        ) as mock_factory, patch("code_indexer.cli.QdrantClient") as mock_qdrant_class:
            # Setup mocks
            mock_docker = MagicMock()
            mock_docker.is_docker_available.return_value = True
            mock_docker.is_compose_available.return_value = True
            mock_docker.get_required_services.return_value = [
                "qdrant",
                "data-cleaner",
            ]  # No Ollama
            mock_docker.get_service_state.return_value = {
                "exists": True,
                "running": True,
                "healthy": True,
                "up_to_date": True,
            }
            mock_docker.start_services.return_value = True
            mock_docker.wait_for_services.return_value = True
            mock_docker_class.return_value = mock_docker

            mock_provider = MagicMock()
            mock_provider.health_check.return_value = True
            mock_provider.get_provider_name.return_value = "VoyageAI"
            mock_provider.get_current_model.return_value = "voyage-code-3"
            mock_factory.create.return_value = mock_provider

            mock_qdrant = MagicMock()
            mock_qdrant.health_check.return_value = True
            mock_qdrant.ensure_collection.return_value = True
            mock_qdrant_class.return_value = mock_qdrant

            # Run start command
            result = runner.invoke(cli, ["start", "--quiet"])

            assert result.exit_code == 0

            # Verify only required services were requested
            mock_docker.get_required_services.assert_called_once()
            required_services = mock_docker.get_required_services.call_args[0][0]
            assert required_services["embedding_provider"] == "voyage-ai"

            # Verify Ollama-specific methods weren't called
            assert (
                not hasattr(mock_provider, "model_exists")
                or not mock_provider.model_exists.called
            )
            assert (
                not hasattr(mock_provider, "pull_model")
                or not mock_provider.pull_model.called
            )

    def test_force_recreate_overrides_idempotent_behavior(self):
        """Test that --force-recreate overrides idempotent behavior."""
        self.create_config("ollama")

        with patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run, patch(
            "code_indexer.services.docker_manager.subprocess.Popen"
        ) as mock_popen:
            mock_run.return_value.returncode = 0

            # Mock Popen for Docker Compose up
            mock_process = MagicMock()
            mock_process.stdout.readline.return_value = ""
            mock_process.poll.return_value = 0
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Mock all services as healthy
            with patch.object(docker_manager, "get_service_state") as mock_state:
                mock_state.return_value = {
                    "exists": True,
                    "running": True,
                    "healthy": True,
                    "up_to_date": True,
                }

                # Call start_services with recreate=True - should force recreation
                result = docker_manager.start_services(recreate=True)

                assert result is True

                # With recreate=True, should NOT call docker-compose start (subprocess.run)
                # Should only call docker-compose up --force-recreate (Popen)
                mock_popen.assert_called_once()

                # Verify --force-recreate flag is passed and it's docker-compose up
                call_args = mock_popen.call_args[0][0]
                assert "--force-recreate" in call_args
                assert "up" in call_args
                assert "-d" in call_args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
