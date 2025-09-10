"""
E2E test infrastructure for misc tests.

Provides shared infrastructure components for end-to-end testing including
embedding providers and test project inventory systems.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any

# Import EmbeddingProvider from shared test infrastructure
from ...shared.mock_providers import MockEmbeddingProvider

# Re-export for compatibility with existing imports
EmbeddingProvider = MockEmbeddingProvider


class TestProjectInventory(Enum):
    """Enumeration of predefined test project configurations."""

    TIMESTAMP_COMPARISON = "timestamp_comparison"
    END_TO_END_DUAL_ENGINE = "end_to_end_dual_engine"
    FILTER_E2E_SUCCESS = "filter_e2e_success"
    SETUP_GLOBAL_REGISTRY = "setup_global_registry"
    START_STOP = "start_stop"
    WATCH_TIMESTAMP_UPDATE = "watch_timestamp_update"
    WORKING_DIRECTORY_RECONCILE = "working_directory_reconcile"
    BRANCH_TOPOLOGY = "branch_topology"
    DELETION_HANDLING = "deletion_handling"
    E2E_EMBEDDING_PROVIDERS = "e2e_embedding_providers"
    END_TO_END_COMPLETE = "end_to_end_complete"
    PAYLOAD_INDEXES_COMPLETE_VALIDATION = "payload_indexes_complete_validation"


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
        TestProjectInventory.TIMESTAMP_COMPARISON: {
            **base_config,
            "reconcile_enabled": True,
            "watch_enabled": False,
        },
        TestProjectInventory.END_TO_END_DUAL_ENGINE: {
            **base_config,
            "embedding_provider": "voyage",
            "fallback_provider": "ollama",
        },
        TestProjectInventory.FILTER_E2E_SUCCESS: {
            **base_config,
            "ignore_patterns": base_config["ignore_patterns"] + ["*.tmp", "temp_*"],  # type: ignore[operator]
        },
        TestProjectInventory.SETUP_GLOBAL_REGISTRY: {
            **base_config,
            "global_registry_enabled": True,
        },
        TestProjectInventory.START_STOP: base_config,
        TestProjectInventory.WATCH_TIMESTAMP_UPDATE: {
            **base_config,
            "watch_enabled": True,
        },
        TestProjectInventory.WORKING_DIRECTORY_RECONCILE: {
            **base_config,
            "reconcile_enabled": True,
        },
        TestProjectInventory.BRANCH_TOPOLOGY: {
            **base_config,
            "git_aware": True,
            "branch_tracking": True,
        },
        TestProjectInventory.DELETION_HANDLING: {
            **base_config,
            "deletion_handling": True,
        },
        TestProjectInventory.E2E_EMBEDDING_PROVIDERS: {
            **base_config,
            "provider_comparison_enabled": True,
        },
        TestProjectInventory.END_TO_END_COMPLETE: {
            **base_config,
            "comprehensive_test": True,
        },
        TestProjectInventory.PAYLOAD_INDEXES_COMPLETE_VALIDATION: {
            **base_config,
            "payload_index_validation": True,
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
    print("Hello from test project!")
    return "success"

if __name__ == "__main__":
    main()
"""
    )

    (src_path / "utils.py").write_text(
        """
def helper_function():
    \"\"\"A helper function for testing.\"\"\"
    return "helper_result"

class UtilityClass:
    def method_one(self):
        return "method_one_result"
    
    def method_two(self):
        return "method_two_result"
"""
    )

    # Create inventory-specific files
    if inventory in [
        TestProjectInventory.TIMESTAMP_COMPARISON,
        TestProjectInventory.WORKING_DIRECTORY_RECONCILE,
    ]:
        (src_path / "reconcile_test.py").write_text(
            """
def reconcile_specific_function():
    \"\"\"Function specific to reconcile testing.\"\"\"
    return "reconcile_data"

class ReconcileClass:
    def process_changes(self):
        return "processed"
"""
        )

    if inventory == TestProjectInventory.END_TO_END_DUAL_ENGINE:
        (src_path / "dual_engine.py").write_text(
            """
def dual_engine_function():
    \"\"\"Function for dual engine testing.\"\"\"
    return "dual_engine_data"

def voyage_specific():
    return "voyage_result"

def ollama_specific():
    return "ollama_result"
"""
        )

    if inventory == TestProjectInventory.BRANCH_TOPOLOGY:
        (src_path / "git_features.py").write_text(
            """
def git_aware_function():
    \"\"\"Function for git-aware testing.\"\"\"
    return "git_data"

class BranchManager:
    def track_branches(self):
        return "branch_tracking"
"""
        )

    # Create test files
    tests_path = project_path / "tests"
    (tests_path / "test_basic.py").write_text(
        """
import unittest

class TestBasic(unittest.TestCase):
    def test_example(self):
        self.assertTrue(True)
"""
    )
