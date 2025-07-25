"""
Test fix-config port regeneration logic.

These tests verify that fix-config completely regenerates all required ports
for CoW clones, ensuring no port conflicts between projects.
"""

import json
import tempfile
import shutil
from pathlib import Path

from code_indexer.services.config_fixer import ConfigurationRepairer


class TestFixConfigPortRegeneration:
    """Test fix-config port regeneration behavior."""

    def setup_method(self):
        """Set up test environment with config files missing ports."""
        # Create temporary directory
        self.temp_root = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_root / ".code-indexer"
        self.config_dir.mkdir(parents=True)

        # Create config file missing some ports (common CoW clone scenario)
        self.incomplete_config = {
            "codebase_dir": ".",
            "embedding_provider": "ollama",
            "project_ports": {
                "qdrant_port": 6333,
                "ollama_port": 11434,
                # Missing data_cleaner_port - common issue!
            },
            "project_containers": {
                "project_hash": "old_hash_123",
                "qdrant_name": "cidx-old_hash_123-qdrant",
                "ollama_name": "cidx-old_hash_123-ollama",
                # Missing data_cleaner_name
            },
        }

        with open(self.config_dir / "config.json", "w") as f:
            json.dump(self.incomplete_config, f, indent=2)

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_root.exists():
            shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_fix_config_regenerates_all_required_ports(self):
        """Test that fix-config ensures all three required ports exist."""
        # Run fix-config
        repairer = ConfigurationRepairer(self.config_dir, dry_run=False)
        repairer.fix_configuration()

        # Load the fixed config
        with open(self.config_dir / "config.json", "r") as f:
            fixed_config = json.load(f)

        # All three ports must exist after fix
        project_ports = fixed_config.get("project_ports", {})

        assert "qdrant_port" in project_ports, "qdrant_port must exist after fix-config"
        assert "ollama_port" in project_ports, "ollama_port must exist after fix-config"
        assert (
            "data_cleaner_port" in project_ports
        ), "data_cleaner_port must exist after fix-config"

        # Ports should be valid port numbers
        for port_name, port_value in project_ports.items():
            assert isinstance(port_value, int), f"{port_name} should be integer"
            assert (
                1024 <= port_value <= 65535
            ), f"{port_name} should be valid port number"

    def test_fix_config_regenerates_all_container_names(self):
        """Test that fix-config ensures all container names exist."""
        # Run fix-config
        repairer = ConfigurationRepairer(self.config_dir, dry_run=False)
        repairer.fix_configuration()

        # Load the fixed config
        with open(self.config_dir / "config.json", "r") as f:
            fixed_config = json.load(f)

        # All container names must exist after fix
        project_containers = fixed_config.get("project_containers", {})

        assert "project_hash" in project_containers, "project_hash must exist"
        assert "qdrant_name" in project_containers, "qdrant_name must exist"
        assert "ollama_name" in project_containers, "ollama_name must exist"
        assert "data_cleaner_name" in project_containers, "data_cleaner_name must exist"

        # Container names should be properly formatted
        project_hash = project_containers["project_hash"]
        expected_qdrant = f"cidx-{project_hash}-qdrant"
        expected_ollama = f"cidx-{project_hash}-ollama"
        expected_cleaner = f"cidx-{project_hash}-data-cleaner"

        assert project_containers["qdrant_name"] == expected_qdrant
        assert project_containers["ollama_name"] == expected_ollama
        assert project_containers["data_cleaner_name"] == expected_cleaner

    def test_fix_config_regenerates_ports_based_on_filesystem_location(self):
        """Test that fix-config generates ports based on actual filesystem location."""
        # Get the expected project hash based on filesystem location
        from code_indexer.services.docker_manager import DockerManager

        docker_manager = DockerManager()

        project_root = self.config_dir.parent.absolute()
        expected_hash = docker_manager._generate_project_hash(project_root)
        expected_ports = docker_manager._calculate_project_ports(expected_hash)

        # Run fix-config
        repairer = ConfigurationRepairer(self.config_dir, dry_run=False)
        repairer.fix_configuration()

        # Load the fixed config
        with open(self.config_dir / "config.json", "r") as f:
            fixed_config = json.load(f)

        # Ports should match the calculated ports for this filesystem location
        project_ports = fixed_config["project_ports"]

        assert (
            project_ports["qdrant_port"] == expected_ports["qdrant_port"]
        ), "qdrant_port should be calculated from filesystem location"
        assert (
            project_ports["ollama_port"] == expected_ports["ollama_port"]
        ), "ollama_port should be calculated from filesystem location"
        assert (
            project_ports["data_cleaner_port"] == expected_ports["data_cleaner_port"]
        ), "data_cleaner_port should be calculated from filesystem location"

    def test_cow_clone_port_independence(self):
        """Test that different filesystem locations get different ports."""
        # Create two different project directories (simulating CoW clones)
        clone1_dir = self.temp_root / "clone1" / ".code-indexer"
        clone2_dir = self.temp_root / "clone2" / ".code-indexer"

        clone1_dir.mkdir(parents=True)
        clone2_dir.mkdir(parents=True)

        # Create identical configs in both locations
        for config_dir in [clone1_dir, clone2_dir]:
            with open(config_dir / "config.json", "w") as f:
                json.dump(self.incomplete_config.copy(), f, indent=2)

        # Run fix-config on both
        repairer1 = ConfigurationRepairer(clone1_dir, dry_run=False)
        repairer2 = ConfigurationRepairer(clone2_dir, dry_run=False)

        repairer1.fix_configuration()
        repairer2.fix_configuration()

        # Load both configs
        with open(clone1_dir / "config.json", "r") as f:
            config1 = json.load(f)
        with open(clone2_dir / "config.json", "r") as f:
            config2 = json.load(f)

        # Configs should have different ports (no conflicts)
        ports1 = config1["project_ports"]
        ports2 = config2["project_ports"]

        # All ports should be different between the clones
        assert (
            ports1["qdrant_port"] != ports2["qdrant_port"]
        ), "Clone ports must be different"
        assert (
            ports1["ollama_port"] != ports2["ollama_port"]
        ), "Clone ports must be different"
        assert (
            ports1["data_cleaner_port"] != ports2["data_cleaner_port"]
        ), "Clone ports must be different"

        # Container hashes should also be different
        hash1 = config1["project_containers"]["project_hash"]
        hash2 = config2["project_containers"]["project_hash"]
        assert hash1 != hash2, "Clone hashes must be different"

    def test_fix_config_handles_completely_missing_port_sections(self):
        """Test fix-config when entire port sections are missing from config."""
        # Create config missing entire sections
        minimal_config = {
            "codebase_dir": ".",
            "embedding_provider": "ollama",
            # Missing project_ports and project_containers entirely
        }

        with open(self.config_dir / "config.json", "w") as f:
            json.dump(minimal_config, f, indent=2)

        # Run fix-config
        repairer = ConfigurationRepairer(self.config_dir, dry_run=False)
        repairer.fix_configuration()

        # Load the fixed config
        with open(self.config_dir / "config.json", "r") as f:
            fixed_config = json.load(f)

        # Should now have complete port and container configuration
        assert "project_ports" in fixed_config, "project_ports section must be created"
        assert (
            "project_containers" in fixed_config
        ), "project_containers section must be created"

        # All required ports should exist
        project_ports = fixed_config["project_ports"]
        required_ports = ["qdrant_port", "ollama_port", "data_cleaner_port"]
        for port_name in required_ports:
            assert port_name in project_ports, f"{port_name} must be created"

    def test_fix_config_dry_run_shows_missing_ports(self):
        """Test that dry-run mode correctly identifies missing ports."""
        # Run fix-config in dry-run mode
        repairer = ConfigurationRepairer(self.config_dir, dry_run=True)
        result = repairer.fix_configuration()

        # Should report that data_cleaner_port needs to be added
        fix_descriptions = [fix.description for fix in result.fixes_applied]
        port_fixes = [desc for desc in fix_descriptions if "port" in desc.lower()]

        assert len(port_fixes) > 0, "Should report port-related fixes needed"

        # Original config should be unchanged in dry-run
        with open(self.config_dir / "config.json", "r") as f:
            config_after_dry_run = json.load(f)

        assert (
            config_after_dry_run == self.incomplete_config
        ), "Config should be unchanged after dry-run"

    def test_partial_port_update_never_happens(self):
        """Test that fix-config never does partial port updates - it's all or nothing."""
        # This test specifically checks for the bug where only existing ports get updated

        # Create config with some ports but wrong values and missing others
        partial_config = {
            "codebase_dir": ".",
            "embedding_provider": "ollama",
            "project_ports": {
                "qdrant_port": 9999,  # Wrong value that should be updated
                "ollama_port": 8888,  # Wrong value that should be updated
                # data_cleaner_port missing - should be added
            },
            "project_containers": {"project_hash": "wrong_hash"},
        }

        with open(self.config_dir / "config.json", "w") as f:
            json.dump(partial_config, f, indent=2)

        # Run fix-config
        repairer = ConfigurationRepairer(self.config_dir, dry_run=False)
        repairer.fix_configuration()

        # Load the fixed config
        with open(self.config_dir / "config.json", "r") as f:
            fixed_config = json.load(f)

        project_ports = fixed_config["project_ports"]

        # All three ports must exist
        assert "qdrant_port" in project_ports
        assert "ollama_port" in project_ports
        assert "data_cleaner_port" in project_ports

        # No port should have the old wrong values
        assert project_ports["qdrant_port"] != 9999, "Old wrong port should be updated"
        assert project_ports["ollama_port"] != 8888, "Old wrong port should be updated"

        # All ports should be properly calculated, not just the missing one
        from code_indexer.services.docker_manager import DockerManager

        docker_manager = DockerManager()
        project_root = self.config_dir.parent.absolute()
        expected_hash = docker_manager._generate_project_hash(project_root)
        expected_ports = docker_manager._calculate_project_ports(expected_hash)

        assert (
            project_ports == expected_ports
        ), "All ports should be completely regenerated, not partially updated"
