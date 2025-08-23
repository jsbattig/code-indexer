"""Tests for idempotent start behavior."""

import pytest

import json
from unittest.mock import patch, MagicMock

# Import new test infrastructure
from ...conftest import local_temporary_directory
from .infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def idempotent_start_test_repo():
    """Create a test repository for idempotent start tests."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.IDEMPOTENT_START
        )

        yield temp_dir


class TestIdempotentStart:
    """Test that start operations are idempotent and don't duplicate work."""

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

    def test_idempotent_start_services_all_healthy(self, idempotent_start_test_repo):
        """Test that start_services is idempotent when all services are healthy."""
        test_dir = idempotent_start_test_repo

        self.create_config(test_dir, "ollama")

        # Mock Docker operations
        with (
            patch("code_indexer.services.docker_manager.subprocess.run") as mock_run,
            patch(
                "code_indexer.services.docker_manager.subprocess.Popen"
            ) as mock_popen,
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Docker is available"

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(test_dir)
            config = config_manager.load()

            # Set up project containers configuration for idempotent behavior
            from code_indexer.config import ProjectContainersConfig

            config.project_containers = ProjectContainersConfig(
                project_hash="abc12345",
                qdrant_name="cidx-abc12345-qdrant",
                ollama_name="cidx-abc12345-ollama",
                data_cleaner_name="cidx-abc12345-data-cleaner",
            )

            # Save the updated config back to the config manager
            config_manager.save(config)

            project_config_dir = test_dir / ".code-indexer"
            docker_manager = DockerManager(
                console=None, force_docker=True, project_config_dir=project_config_dir
            )

            # Mock all services as healthy
            with (
                patch.object(docker_manager, "get_service_state") as mock_state,
                patch.object(docker_manager, "wait_for_services") as mock_wait,
            ):
                mock_state.return_value = {
                    "exists": True,
                    "running": True,
                    "healthy": True,
                    "up_to_date": True,
                }
                mock_wait.return_value = True

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

        with (
            patch("code_indexer.cli.DockerManager") as mock_docker_class,
            patch("code_indexer.cli.EmbeddingProviderFactory") as mock_factory,
            patch("code_indexer.cli.QdrantClient") as mock_qdrant_class,
        ):
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

    def test_idempotent_start_voyage_ai_no_ollama(self, idempotent_start_test_repo):
        """Test that VoyageAI setup doesn't involve Ollama at all."""
        import os

        test_dir = idempotent_start_test_repo

        os.environ["VOYAGE_API_KEY"] = "test_key"
        self.create_config(test_dir, "voyage-ai")

        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            patch("code_indexer.cli.DockerManager") as mock_docker_class,
            patch("code_indexer.cli.EmbeddingProviderFactory") as mock_factory,
            patch("code_indexer.cli.QdrantClient") as mock_qdrant_class,
        ):
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

            # Run start command in test directory context
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(test_dir)
                result = runner.invoke(cli, ["start", "--quiet"])
            finally:
                os.chdir(original_cwd)

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

    def test_force_recreate_overrides_idempotent_behavior(
        self, idempotent_start_test_repo
    ):
        """Test that --force-recreate overrides idempotent behavior."""
        test_dir = idempotent_start_test_repo

        self.create_config(test_dir, "ollama")

        with (
            patch("code_indexer.services.docker_manager.subprocess.run") as mock_run,
            patch(
                "code_indexer.services.docker_manager.subprocess.Popen"
            ) as mock_popen,
        ):
            mock_run.return_value.returncode = 0

            # Mock Popen for Docker Compose up
            mock_process = MagicMock()
            mock_process.stdout.readline.return_value = ""
            mock_process.poll.return_value = 0
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process

            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(test_dir)
            config = config_manager.load()

            # Set up project containers configuration for recreate test
            from code_indexer.config import ProjectContainersConfig

            config.project_containers = ProjectContainersConfig(
                project_hash="def56789",
                qdrant_name="cidx-def56789-qdrant",
                ollama_name="cidx-def56789-ollama",
                data_cleaner_name="cidx-def56789-data-cleaner",
            )

            # Save the updated config back to the config manager
            config_manager.save(config)

            project_config_dir = test_dir / ".code-indexer"
            docker_manager = DockerManager(
                console=None, force_docker=True, project_config_dir=project_config_dir
            )

            # Mock additional methods to prevent hanging
            with (
                patch.object(docker_manager, "get_service_state") as mock_state,
                patch.object(docker_manager, "_update_config_with_ports"),
                patch.object(docker_manager, "wait_for_services", return_value=True),
            ):
                mock_state.return_value = {
                    "exists": True,
                    "running": True,
                    "healthy": True,
                    "up_to_date": True,
                }

                # Call start_services with recreate=True - should force recreation
                result = docker_manager.start_services(recreate=True)

                assert result is True

                # With recreate=True, should call docker-compose up --force-recreate (subprocess.run)
                mock_run.assert_called()

                # Verify --force-recreate flag is passed and it's docker-compose up
                # Find the call that includes --force-recreate
                force_recreate_call = None
                for call in mock_run.call_args_list:
                    call_args = call[0][0]
                    if "--force-recreate" in call_args:
                        force_recreate_call = call_args
                        break

                assert (
                    force_recreate_call is not None
                ), "Expected --force-recreate call not found"
                assert "up" in force_recreate_call
                assert "-d" in force_recreate_call


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
