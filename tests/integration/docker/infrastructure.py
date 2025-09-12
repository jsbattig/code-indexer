"""
Integration test infrastructure for docker tests.

Provides shared infrastructure components for integration testing of docker functionality
including embedding providers and test project inventory systems.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any

# Import EmbeddingProvider from shared test infrastructure
from ...shared.mock_providers import MockEmbeddingProvider

# Re-export for compatibility with existing imports
EmbeddingProvider = MockEmbeddingProvider


class TestProjectInventory(Enum):
    """Enumeration of predefined test project configurations for docker integration tests."""

    DOCKER_COMPOSE_VALIDATION = "docker_compose_validation"


def create_test_project_with_inventory(
    project_path: Path, inventory: TestProjectInventory
) -> None:
    """
    Create a test project with predefined configuration based on inventory type.

    Args:
        project_path: Path where the test project should be created
        inventory: Type of test project to create from inventory
    """
    project_path = Path(project_path)
    project_path.mkdir(parents=True, exist_ok=True)

    # Create basic project structure
    (project_path / "src").mkdir(exist_ok=True)
    (project_path / "tests").mkdir(exist_ok=True)
    (project_path / "docs").mkdir(exist_ok=True)

    # Create basic configuration
    config_data = _get_inventory_config(inventory)

    # Write configuration file
    config_file = project_path / ".code-indexer" / "config.yaml"
    config_file.parent.mkdir(parents=True, exist_ok=True)

    with open(config_file, "w") as f:
        import yaml  # type: ignore[import-untyped]

        yaml.dump(config_data, f, default_flow_style=False)

    # Create sample source files based on inventory type
    _create_inventory_source_files(project_path, inventory)


def _get_inventory_config(inventory: TestProjectInventory) -> Dict[str, Any]:
    """Get configuration data for specific inventory type."""

    base_config = {
        "embedding_provider": "voyage",
        "embedding_model": "voyage-code-2",
        "segment_size": 100,
        "ollama_model": "all-minilm:l6-v2",
        "ignore_patterns": ["*.log", "__pycache__", ".git", "*.pyc"],
    }

    # Inventory-specific configurations
    inventory_configs = {
        TestProjectInventory.DOCKER_COMPOSE_VALIDATION: {
            **base_config,
            "docker_validation": True,
            "docker_compose_enabled": True,
            "integration_testing": True,
        }
    }

    return inventory_configs.get(inventory, base_config)


def _create_inventory_source_files(
    project_path: Path, inventory: TestProjectInventory
) -> None:
    """Create sample source files for specific inventory type."""

    src_path = project_path / "src"

    # Create common files
    (src_path / "main.py").write_text(
        """
def main():
    \"\"\"Main application entry point.\"\"\"
    print("Hello from docker integration test project!")
    return "success"

if __name__ == "__main__":
    main()
"""
    )

    (src_path / "docker_features.py").write_text(
        """
def docker_compose_function():
    \"\"\"Function for Docker Compose testing.\"\"\"
    return "docker_compose_data"

class DockerManager:
    def validate_compose_config(self):
        return "compose_config_validated"
    
    def check_service_health(self):
        return "service_health_checked"
    
    def manage_containers(self):
        return "containers_managed"

def process_docker_operations():
    \"\"\"Function for processing Docker operations.\"\"\"
    return "docker_operations_processed"

class ServiceValidator:
    \"\"\"Validator for Docker services.\"\"\"
    
    def validate_qdrant_service(self):
        return "qdrant_validated"
    
    def validate_ollama_service(self):
        return "ollama_validated"
"""
    )
