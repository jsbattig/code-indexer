"""
Unit tests for ContainerTestManager and EnvironmentManager.

Tests container management utilities for multi-user CIDX server E2E testing.
"""

from unittest.mock import patch, MagicMock

from tests.utils.container_test_helpers import (
    ContainerTestManager,
    EnvironmentManager,
    ContainerService,
)


class TestContainerTestManager:
    """Unit tests for ContainerTestManager class."""

    def test_container_test_manager_init(self, tmp_path):
        """Test that ContainerTestManager initializes properly."""
        manager = ContainerTestManager(
            base_path=tmp_path, project_name="test_project", force_docker=False
        )

        assert manager.base_path == tmp_path
        assert manager.project_name == "test_project"
        assert manager.force_docker is False
        assert manager.docker_manager is None
        assert manager.services == {}

    @patch("code_indexer.services.docker_manager.DockerManager")
    def test_initialize_docker_manager(self, mock_docker_class, tmp_path):
        """Test Docker manager initialization."""
        mock_docker_instance = MagicMock()
        mock_docker_class.return_value = mock_docker_instance

        manager = ContainerTestManager(base_path=tmp_path)
        manager.initialize_docker_manager()

        assert manager.docker_manager == mock_docker_instance
        mock_docker_class.assert_called_once()

    def test_create_service_definition(self, tmp_path):
        """Test creating service definition."""
        manager = ContainerTestManager(base_path=tmp_path)

        service = manager.create_service_definition(
            name="qdrant",
            image="qdrant/qdrant:latest",
            port=6333,
            environment={"QDRANT__SERVICE__HOST": "0.0.0.0"},
        )

        assert isinstance(service, ContainerService)
        assert service.name == "qdrant"
        assert service.image == "qdrant/qdrant:latest"
        assert service.port == 6333
        assert service.environment["QDRANT__SERVICE__HOST"] == "0.0.0.0"
        assert "qdrant" in manager.services

    def test_get_service_by_name(self, tmp_path):
        """Test retrieving service by name."""
        manager = ContainerTestManager(base_path=tmp_path)

        # Create service
        service = manager.create_service_definition("test_service", "test:latest", 8080)

        # Retrieve service
        retrieved = manager.get_service("test_service")
        assert retrieved == service

        # Non-existent service
        assert manager.get_service("nonexistent") is None

    def test_generate_docker_compose_config(self, tmp_path):
        """Test generating docker-compose configuration."""
        manager = ContainerTestManager(base_path=tmp_path)

        # Create services
        manager.create_service_definition(
            "qdrant",
            "qdrant/qdrant:latest",
            6333,
            environment={"QDRANT__SERVICE__HOST": "0.0.0.0"},
            volumes={"./qdrant_data": "/qdrant/storage"},
        )

        manager.create_service_definition(
            "redis", "redis:alpine", 6379, command="redis-server --appendonly yes"
        )

        config = manager.generate_docker_compose_config()

        assert "version" in config
        assert "services" in config
        assert "qdrant" in config["services"]
        assert "redis" in config["services"]

        qdrant_config = config["services"]["qdrant"]
        assert qdrant_config["image"] == "qdrant/qdrant:latest"
        assert qdrant_config["ports"] == ["6333:6333"]
        assert qdrant_config["environment"]["QDRANT__SERVICE__HOST"] == "0.0.0.0"

    def test_write_docker_compose_file(self, tmp_path):
        """Test writing docker-compose file."""
        manager = ContainerTestManager(base_path=tmp_path)
        manager.create_service_definition("test", "test:latest", 8080)

        compose_file = manager.write_docker_compose_file()

        assert compose_file.exists()
        assert compose_file.name == "docker-compose.yml"
        assert "services:" in compose_file.read_text()

    @patch("subprocess.run")
    def test_start_services_success(self, mock_run, tmp_path):
        """Test successful service startup."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = ContainerTestManager(base_path=tmp_path)
        manager.create_service_definition("test", "test:latest", 8080)
        manager.write_docker_compose_file()

        result = manager.start_services()

        assert result is True
        mock_run.assert_called()

    @patch("subprocess.run")
    def test_start_services_failure(self, mock_run, tmp_path):
        """Test failed service startup."""
        mock_run.return_value = MagicMock(returncode=1)

        manager = ContainerTestManager(base_path=tmp_path)
        manager.create_service_definition("test", "test:latest", 8080)
        manager.write_docker_compose_file()

        result = manager.start_services()

        assert result is False

    @patch("subprocess.run")
    def test_stop_services(self, mock_run, tmp_path):
        """Test stopping services."""
        mock_run.return_value = MagicMock(returncode=0)

        manager = ContainerTestManager(base_path=tmp_path)
        manager.create_service_definition("test", "test:latest", 8080)
        manager.write_docker_compose_file()

        result = manager.stop_services()

        assert result is True
        mock_run.assert_called()

    @patch("requests.get")
    def test_wait_for_service_ready_success(self, mock_get, tmp_path):
        """Test waiting for service to become ready."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        manager = ContainerTestManager(base_path=tmp_path)
        manager.create_service_definition("test", "test:latest", 8080)

        result = manager.wait_for_service_ready("test", timeout=1)

        assert result is True

    @patch("requests.get")
    def test_wait_for_service_ready_timeout(self, mock_get, tmp_path):
        """Test service ready timeout."""
        import requests  # type: ignore[import-untyped]

        mock_get.side_effect = requests.exceptions.RequestException("Connection failed")

        manager = ContainerTestManager(base_path=tmp_path)
        manager.create_service_definition("test", "test:latest", 8080)

        result = manager.wait_for_service_ready("test", timeout=1)

        assert result is False

    def test_get_service_url(self, tmp_path):
        """Test getting service URL."""
        manager = ContainerTestManager(base_path=tmp_path)
        manager.create_service_definition("test", "test:latest", 8080)

        url = manager.get_service_url("test")
        assert url == "http://localhost:8080"

        # Non-existent service
        assert manager.get_service_url("nonexistent") is None

    def test_cleanup_removes_compose_file(self, tmp_path):
        """Test cleanup removes docker-compose file."""
        manager = ContainerTestManager(base_path=tmp_path)
        manager.create_service_definition("test", "test:latest", 8080)

        compose_file = manager.write_docker_compose_file()
        assert compose_file.exists()

        manager.cleanup()
        assert not compose_file.exists()


class TestEnvironmentManager:
    """Unit tests for EnvironmentManager class."""

    def test_test_environment_manager_init(self, tmp_path):
        """Test that EnvironmentManager initializes properly."""
        manager = EnvironmentManager(environment_name="test_env", base_path=tmp_path)

        assert manager.environment_name == "test_env"
        assert manager.base_path == tmp_path
        assert manager.container_manager is not None
        assert manager.active_environments == {}

    def test_create_standard_qdrant_environment(self, tmp_path):
        """Test creating standard Qdrant test environment."""
        manager = EnvironmentManager(base_path=tmp_path)

        env_config = manager.create_standard_qdrant_environment()

        assert "qdrant" in env_config["services"]
        qdrant_config = env_config["services"]["qdrant"]
        assert qdrant_config.image == "qdrant/qdrant:latest"
        assert qdrant_config.port == 6333

    def test_create_standard_voyage_environment(self, tmp_path):
        """Test creating standard VoyageAI test environment."""
        manager = EnvironmentManager(base_path=tmp_path)

        # Mock environment variable for API key
        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test_key"}):
            env_config = manager.create_standard_voyage_environment()

        assert "services" in env_config
        # VoyageAI is external service, no container needed
        assert env_config["external_services"]["voyage_api"]["api_key"] == "test_key"

    def test_create_multi_service_environment(self, tmp_path):
        """Test creating environment with multiple services."""
        manager = EnvironmentManager(base_path=tmp_path)

        services = ["qdrant", "redis"]
        env_config = manager.create_multi_service_environment(services)

        assert len(env_config["services"]) == 2
        assert "qdrant" in env_config["services"]
        assert "redis" in env_config["services"]

    @patch("requests.get")
    @patch("subprocess.run")
    def test_start_environment(self, mock_run, mock_get, tmp_path):
        """Test starting complete test environment."""
        mock_run.return_value = MagicMock(returncode=0)

        # Mock successful health checks
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        manager = EnvironmentManager(base_path=tmp_path)
        env_config = manager.create_standard_qdrant_environment()

        result = manager.start_environment("test_env", env_config)

        assert result is True
        assert "test_env" in manager.active_environments

    def test_get_environment_info(self, tmp_path):
        """Test getting environment information."""
        manager = EnvironmentManager(base_path=tmp_path)

        # Create and register environment
        env_config = manager.create_standard_qdrant_environment()
        manager.active_environments["test_env"] = {
            "config": env_config,
            "status": "running",
            "services": env_config["services"],
        }

        info = manager.get_environment_info("test_env")

        assert info is not None
        assert info["status"] == "running"
        assert "qdrant" in info["services"]

    def test_cleanup_environment(self, tmp_path):
        """Test cleaning up test environment."""
        manager = EnvironmentManager(base_path=tmp_path)

        # Create environment
        env_config = manager.create_standard_qdrant_environment()
        manager.active_environments["test_env"] = {
            "config": env_config,
            "status": "running",
        }

        with patch.object(
            manager.container_manager, "stop_services", return_value=True
        ):
            with patch.object(manager.container_manager, "cleanup"):
                result = manager.cleanup_environment("test_env")

        assert result is True
        assert "test_env" not in manager.active_environments

    def test_cleanup_all_environments(self, tmp_path):
        """Test cleaning up all environments."""
        manager = EnvironmentManager(base_path=tmp_path)

        # Create multiple environments
        for i in range(3):
            env_name = f"test_env_{i}"
            manager.active_environments[env_name] = {"config": {}, "status": "running"}

        def cleanup_side_effect(env_id):
            if env_id in manager.active_environments:
                del manager.active_environments[env_id]
            return True

        with patch.object(
            manager, "cleanup_environment", side_effect=cleanup_side_effect
        ) as mock_cleanup:
            manager.cleanup_all_environments()

        assert len(manager.active_environments) == 0
        assert mock_cleanup.call_count == 3

    def test_list_active_environments(self, tmp_path):
        """Test listing active environments."""
        manager = EnvironmentManager(base_path=tmp_path)

        # Create environments
        for i in range(2):
            env_name = f"test_env_{i}"
            manager.active_environments[env_name] = {"config": {}, "status": "running"}

        environments = manager.list_active_environments()

        assert len(environments) == 2
        assert "test_env_0" in environments
        assert "test_env_1" in environments

    def test_context_manager_behavior(self, tmp_path):
        """Test context manager functionality."""
        manager = EnvironmentManager(base_path=tmp_path)

        with patch.object(manager, "cleanup_all_environments") as mock_cleanup:
            with manager:
                # Do something with manager
                pass

        mock_cleanup.assert_called_once()
