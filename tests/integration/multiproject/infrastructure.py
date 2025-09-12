"""
Integration test infrastructure for multiproject tests.

Provides shared infrastructure components for integration testing of multiproject functionality
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
    """Enumeration of predefined test project configurations for multiproject integration tests."""

    INTEGRATION_MULTIPROJECT_1 = "integration_multiproject_1"
    INTEGRATION_MULTIPROJECT_2 = "integration_multiproject_2"


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

    # Project-specific configurations
    project1_config = {
        **base_config,
        "project_name": "multiproject_test_1",
        "multiproject_enabled": True,
        "project_id": "proj1",
    }

    project2_config = {
        **base_config,
        "project_name": "multiproject_test_2",
        "multiproject_enabled": True,
        "project_id": "proj2",
        "embedding_provider": "ollama",  # Use different provider for diversity
    }

    # Inventory-specific configurations
    inventory_configs = {
        TestProjectInventory.INTEGRATION_MULTIPROJECT_1: project1_config,
        TestProjectInventory.INTEGRATION_MULTIPROJECT_2: project2_config,
    }

    return inventory_configs.get(inventory, base_config)


def _create_inventory_source_files(
    project_path: Path, inventory: TestProjectInventory
) -> None:
    """Create sample source files for specific inventory type."""

    src_path = project_path / "src"

    project_id = (
        "1" if inventory == TestProjectInventory.INTEGRATION_MULTIPROJECT_1 else "2"
    )

    # Create project-specific files
    (src_path / "main.py").write_text(
        f"""
def main():
    \"\"\"Main application entry point for project {project_id}.\"\"\"
    print("Hello from multiproject integration test project {project_id}!")
    return "success_project_{project_id}"

if __name__ == "__main__":
    main()
"""
    )

    (src_path / f"project{project_id}_features.py").write_text(
        f"""
def multiproject_function_{project_id}():
    \"\"\"Function specific to project {project_id}.\"\"\"
    return "multiproject_data_{project_id}"

class MultiProjectManager{project_id}:
    def configure_project(self):
        return "project_{project_id}_configured"
    
    def validate_multiproject_setup(self):
        return "multiproject_setup_validated_{project_id}"

def process_project_{project_id}_operations():
    \"\"\"Function for processing project {project_id} operations.\"\"\"
    return "project_{project_id}_operations_processed"

class SharedUtilities:
    \"\"\"Utilities that might be shared across projects.\"\"\"
    
    def common_function(self):
        return f"common_result_from_project_{project_id}"
"""
    )
