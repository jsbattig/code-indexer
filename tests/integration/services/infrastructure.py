"""
Integration test infrastructure for services tests.

Provides shared infrastructure components for integration testing of service functionality
including embedding providers and test project inventory systems.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any

# Import EmbeddingProvider enum from unit test infrastructure


class TestProjectInventory(Enum):
    """Enumeration of predefined test project configurations for services integration tests."""

    DRY_RUN_INTEGRATION = "dry_run_integration"


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
        TestProjectInventory.DRY_RUN_INTEGRATION: {
            **base_config,
            "dry_run_enabled": True,
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
    print("Hello from services integration test project!")
    return "success"

if __name__ == "__main__":
    main()
"""
    )

    (src_path / "service_features.py").write_text(
        """
def dry_run_function():
    \"\"\"Function for dry run testing.\"\"\"
    return "dry_run_data"

class ServiceManager:
    def configure_dry_run(self):
        return "dry_run_configured"
    
    def validate_service_integration(self):
        return "service_integration_validated"

def process_dry_run_operations():
    \"\"\"Function for processing dry run operations.\"\"\"
    return "dry_run_operations_processed"
"""
    )
