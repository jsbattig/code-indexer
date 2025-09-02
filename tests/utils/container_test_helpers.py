"""
Container test infrastructure helpers for multi-user CIDX server testing.

This module provides utilities for managing containers and services during E2E
testing, including Docker/Podman management, service health checking, and
test environment isolation.
"""

import os
import time
import subprocess
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager

import requests

logger = logging.getLogger(__name__)


@dataclass
class ContainerService:
    """Definition of a container service for testing."""

    name: str
    image: str
    port: int
    environment: Dict[str, str] = field(default_factory=dict)
    volumes: Dict[str, str] = field(default_factory=dict)
    command: Optional[str] = None
    healthcheck_path: str = "/"
    healthcheck_timeout: int = 30
    depends_on: List[str] = field(default_factory=list)
    restart_policy: str = "unless-stopped"


class ContainerTestManager:
    """Manager for container services in test environments."""

    def __init__(
        self,
        base_path: Path,
        project_name: str = "cidx_test",
        force_docker: bool = False,
    ):
        """
        Initialize container test manager.

        Args:
            base_path: Base directory for container files
            project_name: Docker Compose project name
            force_docker: Force use of Docker instead of detecting container runtime
        """
        self.base_path = Path(base_path)
        self.project_name = project_name
        self.force_docker = force_docker

        self.services: Dict[str, ContainerService] = {}
        self.docker_manager = None

        self.logger = logging.getLogger(f"{__name__}.ContainerTestManager")

        # Ensure base directory exists
        self.base_path.mkdir(parents=True, exist_ok=True)

    def initialize_docker_manager(self) -> None:
        """Initialize Docker manager from the main codebase."""
        try:
            from code_indexer.services.docker_manager import DockerManager

            self.docker_manager = DockerManager(
                project_name=self.project_name, force_docker=self.force_docker
            )

            # Set indexing root to our base path
            self.docker_manager.set_indexing_root(self.base_path)

            self.logger.info(
                f"Initialized Docker manager for project: {self.project_name}"
            )

        except ImportError as e:
            self.logger.error(f"Failed to import DockerManager: {e}")
            raise

    def create_service_definition(
        self,
        name: str,
        image: str,
        port: int,
        environment: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, str]] = None,
        command: Optional[str] = None,
        healthcheck_path: str = "/",
        depends_on: Optional[List[str]] = None,
    ) -> ContainerService:
        """
        Create a service definition for the test environment.

        Args:
            name: Service name
            image: Docker image
            port: Host port to bind to
            environment: Environment variables
            volumes: Volume mounts
            command: Container command
            healthcheck_path: Health check endpoint path
            depends_on: Service dependencies

        Returns:
            ContainerService instance
        """
        service = ContainerService(
            name=name,
            image=image,
            port=port,
            environment=environment or {},
            volumes=volumes or {},
            command=command,
            healthcheck_path=healthcheck_path,
            depends_on=depends_on or [],
        )

        self.services[name] = service

        self.logger.info(f"Created service definition: {name}")
        return service

    def get_service(self, name: str) -> Optional[ContainerService]:
        """
        Get service definition by name.

        Args:
            name: Service name

        Returns:
            ContainerService or None if not found
        """
        return self.services.get(name)

    def generate_docker_compose_config(self) -> Dict[str, Any]:
        """
        Generate Docker Compose configuration from service definitions.

        Returns:
            Docker Compose configuration dictionary
        """
        config = {
            "version": "3.8",
            "services": {},
            "networks": {"cidx_test_network": {"driver": "bridge"}},
        }

        for service in self.services.values():
            service_config = {
                "image": service.image,
                "container_name": f"{self.project_name}_{service.name}",
                "ports": [f"{service.port}:{service.port}"],
                "networks": ["cidx_test_network"],
                "restart": service.restart_policy,
            }

            if service.environment:
                service_config["environment"] = service.environment

            if service.volumes:
                service_config["volumes"] = [
                    f"{host_path}:{container_path}"
                    for host_path, container_path in service.volumes.items()
                ]

            if service.command:
                service_config["command"] = service.command

            if service.depends_on:
                service_config["depends_on"] = service.depends_on

            # Add health check
            service_config["healthcheck"] = {
                "test": f"curl -f http://localhost:{service.port}{service.healthcheck_path} || exit 1",
                "interval": "10s",
                "timeout": "5s",
                "retries": 3,
                "start_period": "30s",
            }

            config["services"][service.name] = service_config

        return config

    def write_docker_compose_file(self) -> Path:
        """
        Write Docker Compose configuration to file.

        Returns:
            Path to written compose file
        """
        config = self.generate_docker_compose_config()
        compose_file = self.base_path / "docker-compose.yml"

        with open(compose_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        self.logger.info(f"Wrote docker-compose.yml to: {compose_file}")
        return compose_file

    def start_services(self, timeout: int = 120) -> bool:
        """
        Start all services using Docker Compose.

        Args:
            timeout: Startup timeout in seconds

        Returns:
            True if services started successfully
        """
        try:
            # Ensure compose file exists
            compose_file = self.write_docker_compose_file()

            # Start services
            result = subprocess.run(
                [
                    "docker-compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    self.project_name,
                    "up",
                    "-d",
                ],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                self.logger.info(
                    f"Services started successfully for project: {self.project_name}"
                )
                return True
            else:
                self.logger.error(f"Failed to start services: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error(f"Service startup timed out after {timeout} seconds")
            return False
        except Exception as e:
            self.logger.error(f"Error starting services: {e}")
            return False

    def stop_services(self) -> bool:
        """
        Stop all services using Docker Compose.

        Returns:
            True if services stopped successfully
        """
        try:
            compose_file = self.base_path / "docker-compose.yml"

            if not compose_file.exists():
                return True  # Nothing to stop

            result = subprocess.run(
                [
                    "docker-compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    self.project_name,
                    "down",
                ],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                self.logger.info(
                    f"Services stopped successfully for project: {self.project_name}"
                )
                return True
            else:
                self.logger.warning(f"Service shutdown had warnings: {result.stderr}")
                return True  # Consider warnings as success

        except Exception as e:
            self.logger.error(f"Error stopping services: {e}")
            return False

    def wait_for_service_ready(
        self, service_name: str, timeout: int = 60, check_interval: float = 2.0
    ) -> bool:
        """
        Wait for a service to become ready.

        Args:
            service_name: Name of service to check
            timeout: Maximum wait time in seconds
            check_interval: Time between checks in seconds

        Returns:
            True if service becomes ready
        """
        service = self.services.get(service_name)
        if not service:
            self.logger.error(f"Service not found: {service_name}")
            return False

        url = f"http://localhost:{service.port}{service.healthcheck_path}"
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    self.logger.info(f"Service {service_name} is ready")
                    return True

            except requests.exceptions.RequestException:
                pass  # Service not ready yet

            time.sleep(check_interval)

        self.logger.error(f"Service {service_name} not ready after {timeout} seconds")
        return False

    def wait_for_all_services_ready(self, timeout: int = 120) -> Dict[str, bool]:
        """
        Wait for all services to become ready.

        Args:
            timeout: Total timeout for all services

        Returns:
            Dictionary mapping service names to ready status
        """
        results = {}
        start_time = time.time()

        for service_name in self.services.keys():
            remaining_timeout = max(10, timeout - int(time.time() - start_time))
            results[service_name] = self.wait_for_service_ready(
                service_name, timeout=remaining_timeout
            )

        return results

    def get_service_url(self, service_name: str) -> Optional[str]:
        """
        Get URL for a service.

        Args:
            service_name: Service name

        Returns:
            Service URL or None if service not found
        """
        service = self.services.get(service_name)
        if service:
            return f"http://localhost:{service.port}"
        return None

    def get_service_logs(self, service_name: str, lines: int = 50) -> Optional[str]:
        """
        Get logs for a service.

        Args:
            service_name: Service name
            lines: Number of log lines to retrieve

        Returns:
            Service logs or None if error
        """
        try:
            compose_file = self.base_path / "docker-compose.yml"

            result = subprocess.run(
                [
                    "docker-compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    self.project_name,
                    "logs",
                    "--tail",
                    str(lines),
                    service_name,
                ],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return result.stdout
            else:
                self.logger.error(
                    f"Failed to get logs for {service_name}: {result.stderr}"
                )
                return None

        except Exception as e:
            self.logger.error(f"Error getting logs for {service_name}: {e}")
            return None

    def cleanup(self) -> None:
        """Clean up container resources and files."""
        # Stop services first
        self.stop_services()

        # Remove compose file
        compose_file = self.base_path / "docker-compose.yml"
        if compose_file.exists():
            compose_file.unlink()

        # Clear services
        self.services.clear()

        self.logger.info("Container test manager cleaned up")


class EnvironmentManager:
    """Manager for complete test environments with multiple services."""

    def __init__(
        self, environment_name: str = "cidx_test_env", base_path: Optional[Path] = None
    ):
        """
        Initialize test environment manager.

        Args:
            environment_name: Name of the test environment
            base_path: Base path for environment files
        """
        self.environment_name = environment_name
        self.base_path = base_path or Path.home() / ".tmp" / "cidx_test_environments"

        self.container_manager = ContainerTestManager(
            base_path=self.base_path / environment_name, project_name=environment_name
        )

        self.active_environments: Dict[str, Dict[str, Any]] = {}

        self.logger = logging.getLogger(f"{__name__}.TestEnvironmentManager")

    def create_standard_qdrant_environment(self) -> Dict[str, Any]:
        """
        Create standard Qdrant test environment.

        Returns:
            Environment configuration
        """
        # Create Qdrant service
        self.container_manager.create_service_definition(
            name="qdrant",
            image="qdrant/qdrant:latest",
            port=6333,
            environment={
                "QDRANT__SERVICE__HOST": "0.0.0.0",
                "QDRANT__SERVICE__HTTP_PORT": "6333",
                "QDRANT__LOG_LEVEL": "INFO",
            },
            volumes={str(self.base_path / "qdrant_data"): "/qdrant/storage"},
            healthcheck_path="/collections",
        )

        return {
            "type": "qdrant",
            "services": {"qdrant": self.container_manager.get_service("qdrant")},
            "external_services": {},
            "environment_vars": {},
        }

    def create_standard_voyage_environment(self) -> Dict[str, Any]:
        """
        Create standard VoyageAI test environment.

        Returns:
            Environment configuration
        """
        # VoyageAI is external service, no containers needed
        voyage_api_key = os.getenv("VOYAGE_API_KEY")
        if not voyage_api_key:
            self.logger.warning("VOYAGE_API_KEY not set, VoyageAI tests may fail")

        return {
            "type": "voyage",
            "services": {},  # No containers needed
            "external_services": {
                "voyage_api": {
                    "api_key": voyage_api_key,
                    "base_url": "https://api.voyageai.com/v1",
                    "model": "voyage-code-2",
                }
            },
            "environment_vars": {"VOYAGE_API_KEY": voyage_api_key},
        }

    def create_multi_service_environment(self, services: List[str]) -> Dict[str, Any]:
        """
        Create environment with multiple services.

        Args:
            services: List of service names to include

        Returns:
            Environment configuration
        """
        env_services = {}

        for service_name in services:
            if service_name == "qdrant":
                self.container_manager.create_service_definition(
                    name="qdrant",
                    image="qdrant/qdrant:latest",
                    port=6333,
                    environment={"QDRANT__SERVICE__HOST": "0.0.0.0"},
                    healthcheck_path="/collections",
                )
                env_services["qdrant"] = self.container_manager.get_service("qdrant")

            elif service_name == "redis":
                self.container_manager.create_service_definition(
                    name="redis",
                    image="redis:alpine",
                    port=6379,
                    command="redis-server --appendonly yes",
                    healthcheck_path="/",
                )
                env_services["redis"] = self.container_manager.get_service("redis")

            elif service_name == "postgres":
                self.container_manager.create_service_definition(
                    name="postgres",
                    image="postgres:15-alpine",
                    port=5432,
                    environment={
                        "POSTGRES_DB": "cidx_test",
                        "POSTGRES_USER": "cidx_user",
                        "POSTGRES_PASSWORD": "cidx_password",
                    },
                    volumes={
                        str(
                            self.base_path / "postgres_data"
                        ): "/var/lib/postgresql/data"
                    },
                    healthcheck_path="/",
                )
                env_services["postgres"] = self.container_manager.get_service(
                    "postgres"
                )

        return {
            "type": "multi_service",
            "services": env_services,
            "external_services": {},
            "environment_vars": {},
        }

    def start_environment(
        self, environment_id: str, env_config: Dict[str, Any]
    ) -> bool:
        """
        Start a test environment.

        Args:
            environment_id: Unique environment identifier
            env_config: Environment configuration

        Returns:
            True if environment started successfully
        """
        try:
            # Start container services if any
            if env_config.get("services"):
                success = self.container_manager.start_services()
                if not success:
                    return False

                # Wait for services to be ready
                ready_status = self.container_manager.wait_for_all_services_ready()
                if not all(ready_status.values()):
                    self.logger.error(f"Not all services ready: {ready_status}")
                    return False

            # Register active environment
            self.active_environments[environment_id] = {
                "config": env_config,
                "status": "running",
                "services": env_config.get("services", {}),
                "container_manager": self.container_manager,
            }

            self.logger.info(f"Started environment: {environment_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start environment {environment_id}: {e}")
            return False

    def stop_environment(self, environment_id: str) -> bool:
        """
        Stop a test environment.

        Args:
            environment_id: Environment identifier

        Returns:
            True if environment stopped successfully
        """
        if environment_id not in self.active_environments:
            return True  # Already stopped

        try:
            # Stop container services
            success = self.container_manager.stop_services()

            # Update status
            if environment_id in self.active_environments:
                self.active_environments[environment_id]["status"] = "stopped"

            self.logger.info(f"Stopped environment: {environment_id}")
            return success

        except Exception as e:
            self.logger.error(f"Failed to stop environment {environment_id}: {e}")
            return False

    def cleanup_environment(self, environment_id: str) -> bool:
        """
        Clean up a test environment completely.

        Args:
            environment_id: Environment identifier

        Returns:
            True if cleanup was successful
        """
        if environment_id not in self.active_environments:
            return True

        try:
            # Stop environment first
            self.stop_environment(environment_id)

            # Clean up container resources
            self.container_manager.cleanup()

            # Remove from active environments
            del self.active_environments[environment_id]

            self.logger.info(f"Cleaned up environment: {environment_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to cleanup environment {environment_id}: {e}")
            return False

    def cleanup_all_environments(self) -> None:
        """Clean up all active environments."""
        environment_ids = list(self.active_environments.keys())

        for env_id in environment_ids:
            self.cleanup_environment(env_id)

        self.logger.info(f"Cleaned up {len(environment_ids)} environments")

    def get_environment_info(self, environment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an environment.

        Args:
            environment_id: Environment identifier

        Returns:
            Environment information or None if not found
        """
        return self.active_environments.get(environment_id)

    def list_active_environments(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all active environments.

        Returns:
            Dictionary mapping environment IDs to environment info
        """
        return self.active_environments.copy()

    def get_service_url_for_environment(
        self, environment_id: str, service_name: str
    ) -> Optional[str]:
        """
        Get service URL for a specific environment.

        Args:
            environment_id: Environment identifier
            service_name: Service name

        Returns:
            Service URL or None if not found
        """
        env_info = self.get_environment_info(environment_id)
        if not env_info:
            return None

        container_manager = env_info.get("container_manager")
        if container_manager:
            return container_manager.get_service_url(service_name)

        return None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup_all_environments()


# Convenience functions
def create_standard_test_environment(
    environment_type: str = "qdrant", environment_id: str = "default_test_env"
) -> EnvironmentManager:
    """
    Create and start a standard test environment.

    Args:
        environment_type: Type of environment (qdrant, voyage, multi)
        environment_id: Environment identifier

    Returns:
        Configured EnvironmentManager
    """
    manager = EnvironmentManager()

    if environment_type == "qdrant":
        env_config = manager.create_standard_qdrant_environment()
    elif environment_type == "voyage":
        env_config = manager.create_standard_voyage_environment()
    elif environment_type == "multi":
        env_config = manager.create_multi_service_environment(["qdrant", "redis"])
    else:
        raise ValueError(f"Unknown environment type: {environment_type}")

    success = manager.start_environment(environment_id, env_config)
    if not success:
        raise RuntimeError(f"Failed to start {environment_type} environment")

    return manager


@contextmanager
def temporary_test_environment(
    environment_type: str = "qdrant", cleanup_on_exit: bool = True
):
    """
    Context manager for temporary test environments.

    Args:
        environment_type: Type of environment to create
        cleanup_on_exit: Whether to cleanup on context exit

    Yields:
        TestEnvironmentManager instance
    """
    manager = None

    try:
        manager = create_standard_test_environment(environment_type)
        yield manager

    finally:
        if manager and cleanup_on_exit:
            manager.cleanup_all_environments()
