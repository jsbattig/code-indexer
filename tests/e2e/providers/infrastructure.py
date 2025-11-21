"""
E2E test infrastructure for providers tests.

Provides shared infrastructure components for end-to-end testing of provider functionality
including embedding providers and test project inventory systems.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any

from tests.unit.infrastructure.infrastructure import EmbeddingProvider

# Re-export EmbeddingProvider for test files
__all__ = [
    "EmbeddingProvider",
    "TestProjectInventory",
    "create_test_project_with_inventory",
]


class TestProjectInventory(Enum):
    """Enumeration of predefined test project configurations for provider tests."""

    VOYAGE_AI_E2E = "voyage_ai_e2e"


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
        "ignore_patterns": ["*.log", "__pycache__", ".git", "*.pyc"],
    }

    # Inventory-specific configurations
    inventory_configs = {
        TestProjectInventory.VOYAGE_AI_E2E: {
            **base_config,
            "embedding_provider": "voyage",
            "voyage_ai_testing": True,
            "api_validation": True,
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
    print("Hello from providers test project!")
    return "success"

if __name__ == "__main__":
    main()
"""
    )

    (src_path / "provider_features.py").write_text(
        """
def voyage_ai_function():
    \"\"\"Function for Voyage AI testing.\"\"\"
    return "voyage_ai_data"

class ProviderManager:
    def configure_voyage(self):
        return "voyage_configured"
    
    def validate_api_access(self):
        return "api_validated"
    
    def test_embedding_generation(self):
        return "embeddings_generated"

def process_voyage_requests():
    \"\"\"Function for processing Voyage AI requests.\"\"\"
    return "voyage_requests_processed"
"""
    )
