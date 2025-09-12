"""
E2E test infrastructure for display tests.

Provides shared infrastructure components for end-to-end testing of display functionality
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
    """Enumeration of predefined test project configurations for display tests."""

    CLI_PROGRESS_E2E = "cli_progress_e2e"
    LINE_NUMBER_DISPLAY_E2E = "line_number_display_e2e"


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
        TestProjectInventory.CLI_PROGRESS_E2E: {
            **base_config,
            "progress_display": True,
            "cli_feedback": True,
        },
        TestProjectInventory.LINE_NUMBER_DISPLAY_E2E: {
            **base_config,
            "line_number_tracking": True,
            "display_line_numbers": True,
        },
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
    print("Hello from display test project!")
    return "success"

if __name__ == "__main__":
    main()
"""
    )

    (src_path / "display_features.py").write_text(
        """
def progress_display_function():
    \"\"\"Function for progress display testing.\"\"\"
    return "progress_display_data"

class DisplayManager:
    def show_progress(self, current, total):
        return f"Progress: {current}/{total}"
    
    def format_line_numbers(self, content, start_line=1):
        lines = content.split('\\n')
        return '\\n'.join(f"{start_line + i:4d}: {line}" for i, line in enumerate(lines))
"""
    )
