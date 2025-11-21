"""
E2E test infrastructure for git workflows tests.

Provides shared infrastructure components for end-to-end testing of git workflow functionality
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
    """Enumeration of predefined test project configurations for git workflow tests."""

    GIT_AWARE_WATCH_E2E = "git_aware_watch_e2e"
    GIT_INDEXING_CONSISTENCY_E2E = "git_indexing_consistency_e2e"
    GIT_PULL_INCREMENTAL_E2E = "git_pull_incremental_e2e"
    RECONCILE_COMPREHENSIVE_E2E = "reconcile_comprehensive_e2e"
    RECONCILE_E2E = "reconcile_e2e"


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
        TestProjectInventory.GIT_AWARE_WATCH_E2E: {
            **base_config,
            "git_aware": True,
            "watch_enabled": True,
            "branch_tracking": True,
        },
        TestProjectInventory.GIT_INDEXING_CONSISTENCY_E2E: {
            **base_config,
            "git_aware": True,
            "consistency_checks": True,
        },
        TestProjectInventory.GIT_PULL_INCREMENTAL_E2E: {
            **base_config,
            "git_aware": True,
            "incremental_updates": True,
            "pull_tracking": True,
        },
        TestProjectInventory.RECONCILE_COMPREHENSIVE_E2E: {
            **base_config,
            "git_aware": True,
            "reconcile_enabled": True,
            "comprehensive_reconcile": True,
        },
        TestProjectInventory.RECONCILE_E2E: {
            **base_config,
            "git_aware": True,
            "reconcile_enabled": True,
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
    print("Hello from git workflow test project!")
    return "success"

if __name__ == "__main__":
    main()
"""
    )

    (src_path / "git_features.py").write_text(
        """
def git_aware_function():
    \"\"\"Function for git-aware testing.\"\"\"
    return "git_aware_data"

class GitWorkflowManager:
    def track_changes(self):
        return "changes_tracked"
    
    def process_incremental_updates(self):
        return "incremental_processed"
    
    def reconcile_branches(self):
        return "branches_reconciled"

def watch_git_changes():
    \"\"\"Function for git watch functionality.\"\"\"
    return "git_changes_watched"

def handle_pull_updates():
    \"\"\"Function for handling git pull updates.\"\"\"
    return "pull_updates_handled"
"""
    )
