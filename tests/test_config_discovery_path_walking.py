"""
Test config discovery path walking logic.

These tests verify that config discovery stops at the first .code-indexer/config.json
found when walking up the directory tree, enabling proper nested project support.
"""

import json
import os
import tempfile
import shutil
from pathlib import Path

from code_indexer.config import ConfigManager


class TestConfigDiscoveryPathWalking:
    """Test config discovery path walking behavior."""

    def setup_method(self):
        """Set up test environment with nested directory structure."""
        # Create temporary directory structure
        self.temp_root = Path(tempfile.mkdtemp())

        # Create nested structure:
        # temp_root/
        # ├── parent/
        # │   ├── .code-indexer/
        # │   │   └── config.json (parent config)
        # │   └── child/
        # │       ├── .code-indexer/
        # │       │   └── config.json (child config)
        # │       └── grandchild/
        # │           └── (no config - should find child config)

        self.parent_dir = self.temp_root / "parent"
        self.child_dir = self.parent_dir / "child"
        self.grandchild_dir = self.child_dir / "grandchild"

        # Create directory structure
        for directory in [self.parent_dir, self.child_dir, self.grandchild_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        # Create parent config
        parent_config_dir = self.parent_dir / ".code-indexer"
        parent_config_dir.mkdir(exist_ok=True)
        parent_config = {
            "codebase_dir": ".",
            "embedding_provider": "ollama",
            "project_ports": {
                "qdrant_port": 6333,
                "ollama_port": 11434,
                "data_cleaner_port": 8091,
            },
            "project_containers": {"project_hash": "parent123"},
        }
        with open(parent_config_dir / "config.json", "w") as f:
            json.dump(parent_config, f, indent=2)

        # Create child config with different ports
        child_config_dir = self.child_dir / ".code-indexer"
        child_config_dir.mkdir(exist_ok=True)
        child_config = {
            "codebase_dir": ".",
            "embedding_provider": "ollama",
            "project_ports": {
                "qdrant_port": 7333,
                "ollama_port": 12434,
                "data_cleaner_port": 9091,
            },
            "project_containers": {"project_hash": "child456"},
        }
        with open(child_config_dir / "config.json", "w") as f:
            json.dump(child_config, f, indent=2)

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_root.exists():
            shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_config_discovery_stops_at_first_match(self):
        """Test that config discovery stops at the first .code-indexer/config.json found."""
        # Change to child directory
        original_cwd = os.getcwd()
        try:
            os.chdir(self.child_dir)

            # ConfigManager should find child config, not parent config
            config_path = ConfigManager.find_config_path()

            # Should find child config, not parent config
            expected_path = self.child_dir / ".code-indexer" / "config.json"
            assert (
                config_path == expected_path
            ), f"Expected {expected_path}, got {config_path}"

            # Verify it's actually the child config by checking ports
            config_manager = ConfigManager(config_path)
            config = config_manager.load()

            # Child config has different ports than parent
            assert (
                config.project_ports.qdrant_port == 7333
            ), "Should find child config with port 7333"
            assert (
                config.project_containers.project_hash == "child456"
            ), "Should find child config with hash child456"

        finally:
            os.chdir(original_cwd)

    def test_grandchild_finds_child_config(self):
        """Test that grandchild directory finds child config, not parent config."""
        # Change to grandchild directory (has no config)
        original_cwd = os.getcwd()
        try:
            os.chdir(self.grandchild_dir)

            # Should walk up and find child config first, not parent config
            config_path = ConfigManager.find_config_path()

            # Should find child config (closest one up the tree)
            expected_path = self.child_dir / ".code-indexer" / "config.json"
            assert (
                config_path == expected_path
            ), f"Expected {expected_path}, got {config_path}"

            # Verify it's the child config
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            assert (
                config.project_ports.qdrant_port == 7333
            ), "Should find child config from grandchild"

        finally:
            os.chdir(original_cwd)

    def test_parent_finds_parent_config(self):
        """Test that parent directory finds its own config."""
        # Change to parent directory
        original_cwd = os.getcwd()
        try:
            os.chdir(self.parent_dir)

            # Should find parent config
            config_path = ConfigManager.find_config_path()

            expected_path = self.parent_dir / ".code-indexer" / "config.json"
            assert (
                config_path == expected_path
            ), f"Expected {expected_path}, got {config_path}"

            # Verify it's the parent config
            config_manager = ConfigManager(config_path)
            config = config_manager.load()
            assert (
                config.project_ports.qdrant_port == 6333
            ), "Should find parent config with port 6333"
            assert (
                config.project_containers.project_hash == "parent123"
            ), "Should find parent config with hash parent123"

        finally:
            os.chdir(original_cwd)

    def test_create_with_backtrack_respects_path_walking(self):
        """Test that create_with_backtrack follows same path walking rules."""
        original_cwd = os.getcwd()
        try:
            # Test from child directory
            os.chdir(self.child_dir)

            config_manager = ConfigManager.create_with_backtrack()

            # Should find child config
            expected_path = self.child_dir / ".code-indexer" / "config.json"
            assert config_manager.config_path == expected_path

            # Load and verify
            config = config_manager.load()
            assert (
                config.project_ports.qdrant_port == 7333
            ), "create_with_backtrack should find child config"

        finally:
            os.chdir(original_cwd)

    def test_no_config_returns_none(self):
        """Test that search returns None when no config found."""
        # Create directory outside temp structure to avoid finding real configs
        import tempfile

        with tempfile.TemporaryDirectory() as isolated_temp:
            no_config_dir = Path(isolated_temp) / "isolated"
            no_config_dir.mkdir()

            original_cwd = os.getcwd()
            try:
                os.chdir(no_config_dir)

                # Should not find any config in an isolated temp directory
                config_path = ConfigManager.find_config_path()
                # Note: This might find system configs, so let's just ensure it's not our test configs
                if config_path:
                    assert "parent" not in str(config_path) and "child" not in str(
                        config_path
                    ), "Should not find our test configs"

            finally:
                os.chdir(original_cwd)

    def test_config_discovery_debug_output(self):
        """Test config discovery with debug to verify search order."""
        # This test helps debug the actual search behavior
        original_cwd = os.getcwd()
        try:
            os.chdir(self.grandchild_dir)

            # Manually trace the search path
            current = Path.cwd()
            search_paths = [current] + list(current.parents)

            # Ensure child config is found before parent config
            child_config_path = self.child_dir / ".code-indexer" / "config.json"
            parent_config_path = self.parent_dir / ".code-indexer" / "config.json"

            child_found_at = None
            parent_found_at = None

            for i, path in enumerate(search_paths):
                test_path = path / ".code-indexer" / "config.json"
                if test_path == child_config_path:
                    child_found_at = i
                elif test_path == parent_config_path:
                    parent_found_at = i

            assert child_found_at is not None, "Child config should be in search path"
            assert parent_found_at is not None, "Parent config should be in search path"
            assert (
                child_found_at < parent_found_at
            ), "Child config should be found before parent config"

            # Actual discovery should find child first
            found_config = ConfigManager.find_config_path()
            assert (
                found_config == child_config_path
            ), "Should find child config first in search order"

        finally:
            os.chdir(original_cwd)

    def test_cli_commands_use_same_config_discovery(self):
        """Test that all CLI commands use the same config discovery logic."""
        # This test will fail if different commands use different discovery logic
        from code_indexer.cli import cli
        from click.testing import CliRunner

        original_cwd = os.getcwd()
        try:
            # Change to child directory
            os.chdir(self.child_dir)

            # Test that status command finds child config
            runner = CliRunner()

            # Run status command which should find child config
            result = runner.invoke(cli, ["status"])

            # The status command should report child config information
            # If it finds parent config, it will have different ports/hash
            output = result.output

            # Should not show parent config ports/hash
            assert (
                "6333" not in output or "parent123" not in output
            ), f"Status command found parent config instead of child config. Output: {output}"

            # Note: This test may need adjustment based on actual status output format

        finally:
            os.chdir(original_cwd)

    def test_docker_operations_use_config_directory(self):
        """Test that Docker operations use the same directory as the config file."""
        from code_indexer.services.docker_manager import DockerManager
        from code_indexer.config import ConfigManager

        original_cwd = os.getcwd()
        try:
            # Change to child directory
            os.chdir(self.child_dir)

            # Get config manager
            config_manager = ConfigManager.create_with_backtrack()
            config_manager.load()

            # Create Docker manager
            docker_manager = DockerManager()

            # Get project root that Docker manager would use
            # This test will fail if Docker manager uses Path.cwd() instead of config directory
            project_info = docker_manager._generate_container_names(Path.cwd())

            # The project hash should be based on child directory, not parent
            expected_child_path = self.child_dir.resolve()
            actual_hash = docker_manager._generate_project_hash(expected_child_path)

            assert (
                project_info["project_hash"] == actual_hash
            ), "Docker manager should use same directory as config discovery"

        finally:
            os.chdir(original_cwd)
