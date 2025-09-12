"""
E2E test infrastructure for payload indexes tests.

Provides shared infrastructure components for end-to-end testing of payload index functionality
including embedding providers and test project inventory systems.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any

# Import EmbeddingProvider enum from unit test infrastructure


class TestProjectInventory(Enum):
    """Enumeration of predefined test project configurations for payload indexes tests."""

    PAYLOAD_INDEXES_COMPLETE_VALIDATION_E2E = "payload_indexes_complete_validation_e2e"


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
        TestProjectInventory.PAYLOAD_INDEXES_COMPLETE_VALIDATION_E2E: {
            **base_config,
            "payload_index_validation": True,
            "comprehensive_indexing": True,
            "validation_enabled": True,
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
    print("Hello from payload indexes test project!")
    return "success"

if __name__ == "__main__":
    main()
"""
    )

    (src_path / "payload_features.py").write_text(
        """
def payload_index_function():
    \"\"\"Function for payload index testing.\"\"\"
    return "payload_index_data"

class PayloadIndexManager:
    def create_indexes(self):
        return "indexes_created"
    
    def validate_payload_structure(self):
        return "payload_validated"
    
    def comprehensive_indexing(self):
        return "comprehensive_indexing_complete"

def process_payload_validation():
    \"\"\"Function for payload validation processing.\"\"\"
    return "payload_validation_processed"
"""
    )
