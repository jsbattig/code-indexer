"""
Test the specific fix-config port bug.

This test targets the exact conditional logic bug in config_fixer.py
that only updates existing ports instead of ensuring all required ports exist.
"""

import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any

from code_indexer.config import ConfigManager
from code_indexer.services.config_fixer import ConfigurationRepairer


class TestFixConfigPortBugSpecific:
    """Test the specific port update bug in fix-config."""

    def setup_method(self):
        """Set up test with config missing data_cleaner_port."""
        self.temp_root = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_root / ".code-indexer"
        self.config_dir.mkdir(parents=True)

        # Create config with missing data_cleaner_port - the exact bug scenario
        self.config_data = {
            "codebase_dir": ".",
            "embedding_provider": "ollama",
            "ollama": {
                "host": "http://localhost:11434",
                "model": "nomic-embed-text",
                "timeout": 30,
                "num_parallel": 1,
                "max_loaded_models": 1,
                "max_queue": 512,
            },
            "qdrant": {
                "host": "http://localhost:6333",
                "collection_base_name": "code_index",
                "vector_size": 768,
                "hnsw_ef": 64,
                "hnsw_ef_construct": 200,
                "hnsw_m": 32,
            },
            "project_ports": {
                "qdrant_port": 6333,
                "ollama_port": 11434,
                # CRITICAL: data_cleaner_port is missing!
            },
            "project_containers": {
                "project_hash": "abc12345",
                "qdrant_name": "cidx-abc12345-qdrant",
                "ollama_name": "cidx-abc12345-ollama",
                # CRITICAL: data_cleaner_name is missing!
            },
        }

        with open(self.config_dir / "config.json", "w") as f:
            json.dump(self.config_data, f, indent=2)

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_root.exists():
            shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_fix_config_adds_missing_data_cleaner_port(self):
        """Test that fix-config adds missing data_cleaner_port (not just updates existing ones)."""
        # Verify initial state - data_cleaner_port is missing
        config_manager = ConfigManager(self.config_dir / "config.json")
        config = config_manager.load()

        # Confirm the bug condition - data_cleaner_port should be None (missing from JSON)
        assert (
            config.project_ports.data_cleaner_port is None
        ), "Test setup error: data_cleaner_port should be None initially"

        # Run fix-config
        repairer = ConfigurationRepairer(self.config_dir, dry_run=False)
        repairer.fix_configuration()

        # Reload config after fix
        config_manager_after = ConfigManager(self.config_dir / "config.json")
        config_after = config_manager_after.load()

        # FIXED: This should now pass - fix-config should set missing data_cleaner_port
        assert (
            config_after.project_ports.data_cleaner_port is not None
        ), "CRITICAL BUG: fix-config failed to add missing data_cleaner_port"

        # Should have a valid port number
        data_cleaner_port = config_after.project_ports.data_cleaner_port
        assert isinstance(data_cleaner_port, int), "data_cleaner_port should be integer"
        assert (
            1024 <= data_cleaner_port <= 65535
        ), "data_cleaner_port should be valid port"

    def test_fix_config_adds_missing_data_cleaner_container_name(self):
        """Test that fix-config adds missing data_cleaner_name."""
        # Run fix-config
        repairer = ConfigurationRepairer(self.config_dir, dry_run=False)
        repairer.fix_configuration()

        # Load fixed config
        config_manager = ConfigManager(self.config_dir / "config.json")
        config = config_manager.load()

        # Should have data_cleaner_name (not None)
        assert (
            config.project_containers.data_cleaner_name is not None
        ), "CRITICAL BUG: fix-config failed to add missing data_cleaner_name"

        # Should be properly formatted
        data_cleaner_name = config.project_containers.data_cleaner_name
        project_hash = config.project_containers.project_hash
        expected_name = f"cidx-{project_hash}-data-cleaner"

        assert (
            data_cleaner_name == expected_name
        ), f"data_cleaner_name should be {expected_name}, got {data_cleaner_name}"

    def test_conditional_port_update_bug_reproduction(self):
        """Test that reproduces the exact conditional update bug."""
        # This test directly targets the buggy code:
        # if hasattr(config.project_ports, service):
        #     setattr(config.project_ports, service, port)

        config_manager = ConfigManager(self.config_dir / "config.json")
        config = config_manager.load()

        # Simulate what _apply_project_config_fixes does
        from code_indexer.services.docker_manager import DockerManager

        docker_manager = DockerManager()
        project_root = self.config_dir.parent.absolute()
        project_hash = docker_manager._generate_project_hash(project_root)
        new_ports = docker_manager._calculate_project_ports(project_hash)

        # Check original state before applying the buggy logic
        original_data_cleaner_port = config.project_ports.data_cleaner_port
        assert (
            original_data_cleaner_port is None
        ), "Original data_cleaner_port should be None"

        # This is the buggy logic from config_fixer.py:962-964
        ports_updated = []
        ports_skipped = []

        for service, port in new_ports.items():
            if hasattr(config.project_ports, service):
                setattr(config.project_ports, service, port)
                ports_updated.append(service)
            else:
                ports_skipped.append(service)

        # With Pydantic models, hasattr() returns True even for None values
        # So the old conditional logic actually works (the real bug was elsewhere)
        assert (
            "data_cleaner_port" in ports_updated
        ), "data_cleaner_port gets updated because hasattr() is True even for None values"

        assert "qdrant_port" in ports_updated, "qdrant_port should get updated (exists)"
        assert "ollama_port" in ports_updated, "ollama_port should get updated (exists)"

        # All ports get updated with the current Pydantic model approach
        assert len(ports_skipped) == 0, "No ports get skipped with Pydantic models"

        # After the update, data_cleaner_port should have a valid value
        updated_data_cleaner_port = config.project_ports.data_cleaner_port
        assert (
            updated_data_cleaner_port is not None
        ), "data_cleaner_port should be updated"
        assert isinstance(
            updated_data_cleaner_port, int
        ), "data_cleaner_port should be integer"

    def test_fix_demonstrates_all_or_nothing_requirement(self):
        """Test that demonstrates why fix-config must update ALL ports, not just existing ones."""
        # Create two configs - one missing different ports
        config1_dir = self.temp_root / "config1" / ".code-indexer"
        config2_dir = self.temp_root / "config2" / ".code-indexer"

        config1_dir.mkdir(parents=True)
        config2_dir.mkdir(parents=True)

        # Config 1: Missing data_cleaner_port
        config1_data = self.config_data.copy()
        with open(config1_dir / "config.json", "w") as f:
            json.dump(config1_data, f, indent=2)

        # Config 2: Missing ollama_port
        config2_data: Dict[str, Any] = dict(self.config_data)
        project_ports: Dict[str, int] = dict(config2_data["project_ports"])
        del project_ports["ollama_port"]
        project_ports["data_cleaner_port"] = 8091  # Has this one
        config2_data["project_ports"] = project_ports
        with open(config2_dir / "config.json", "w") as f:
            json.dump(config2_data, f, indent=2)

        # Run fix-config on both
        repairer1 = ConfigurationRepairer(config1_dir, dry_run=False)
        repairer2 = ConfigurationRepairer(config2_dir, dry_run=False)

        repairer1.fix_configuration()
        repairer2.fix_configuration()

        # Load both configs after fix
        config_manager1 = ConfigManager(config1_dir / "config.json")
        config_manager2 = ConfigManager(config2_dir / "config.json")

        config1_after = config_manager1.load()
        config2_after = config_manager2.load()

        # Both configs should have ALL three ports after fix-config
        required_ports = ["qdrant_port", "ollama_port", "data_cleaner_port"]

        for port_name in required_ports:
            assert hasattr(
                config1_after.project_ports, port_name
            ), f"Config1 missing {port_name} after fix-config"
            assert hasattr(
                config2_after.project_ports, port_name
            ), f"Config2 missing {port_name} after fix-config"

        # All ports should be valid values allocated by GlobalPortRegistry
        for config_after, config_dir in [
            (config1_after, config1_dir),
            (config2_after, config2_dir),
        ]:
            actual_ports = {
                "qdrant_port": config_after.project_ports.qdrant_port,
                "ollama_port": config_after.project_ports.ollama_port,
                "data_cleaner_port": config_after.project_ports.data_cleaner_port,
            }

            # Verify ports are in the correct ranges (allocated by GlobalPortRegistry)
            assert (
                6333 <= actual_ports["qdrant_port"] <= 7333
            ), f"qdrant_port {actual_ports['qdrant_port']} not in valid range"
            assert (
                11434 <= actual_ports["ollama_port"] <= 12434
            ), f"ollama_port {actual_ports['ollama_port']} not in valid range"
            assert (
                8091 <= actual_ports["data_cleaner_port"] <= 9091
            ), f"data_cleaner_port {actual_ports['data_cleaner_port']} not in valid range"

            # Verify all ports are valid integers
            for port_name, port_value in actual_ports.items():
                assert isinstance(port_value, int), f"{port_name} should be integer"
                assert (
                    1024 <= port_value <= 65535
                ), f"{port_name} {port_value} should be valid port number"
