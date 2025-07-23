"""Test the CoW fix-config container isolation fix."""

import tempfile
from pathlib import Path

import pytest

from code_indexer.config import Config, ProjectContainersConfig, ProjectPortsConfig
from code_indexer.services.config_fixer import ConfigurationRepairer


class TestCoWFixConfig:
    """Test that fix-config properly isolates CoW clones."""

    def test_apply_project_config_fixes_updates_container_names(self):
        """Test that _apply_project_config_fixes updates container names properly."""

        # Create a temporary config directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)

            # Create a config with old container names and ports
            config = Config(
                codebase_dir=Path("."),
                project_containers=ProjectContainersConfig(
                    project_hash="old_hash_123",
                    qdrant_name="cidx-old_hash_123-qdrant",
                    ollama_name="cidx-old_hash_123-ollama",
                    data_cleaner_name="cidx-old_hash_123-data-cleaner",
                ),
                project_ports=ProjectPortsConfig(
                    qdrant_port=6000,
                    ollama_port=11000,
                    data_cleaner_port=8000,
                ),
            )

            # Create the repairer
            repairer = ConfigurationRepairer(config_dir, dry_run=False)

            # Create project info with new container names and ports
            project_info = {
                "container_names": {
                    "project_hash": "new_hash_456",
                    "qdrant_name": "cidx-new_hash_456-qdrant",
                    "ollama_name": "cidx-new_hash_456-ollama",
                    "data_cleaner_name": "cidx-new_hash_456-data-cleaner",
                },
                "port_assignments": {
                    "qdrant_port": 7000,
                    "ollama_port": 12000,
                    "data_cleaner_port": 9000,
                },
            }

            # Apply the fixes
            updated_config = repairer._apply_project_config_fixes(config, project_info)

            # Verify container names were updated
            assert updated_config.project_containers.project_hash == "new_hash_456"
            assert (
                updated_config.project_containers.qdrant_name
                == "cidx-new_hash_456-qdrant"
            )
            assert (
                updated_config.project_containers.ollama_name
                == "cidx-new_hash_456-ollama"
            )
            assert (
                updated_config.project_containers.data_cleaner_name
                == "cidx-new_hash_456-data-cleaner"
            )

            # Verify ports were updated
            assert updated_config.project_ports.qdrant_port == 7000
            assert updated_config.project_ports.ollama_port == 12000
            assert updated_config.project_ports.data_cleaner_port == 9000

    def test_apply_project_config_fixes_handles_missing_container_names(self):
        """Test that _apply_project_config_fixes handles missing container names gracefully."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)

            config = Config(
                codebase_dir=Path("."),
                project_containers=ProjectContainersConfig(
                    project_hash="old_hash_123",
                    qdrant_name="cidx-old_hash_123-qdrant",
                ),
                project_ports=ProjectPortsConfig(qdrant_port=6000),
            )

            repairer = ConfigurationRepairer(config_dir, dry_run=False)

            # Project info with only ports, no container names
            project_info = {
                "port_assignments": {
                    "qdrant_port": 7000,
                },
            }

            # Should not fail, should only update ports
            updated_config = repairer._apply_project_config_fixes(config, project_info)

            # Container names should be unchanged
            assert updated_config.project_containers.project_hash == "old_hash_123"
            assert (
                updated_config.project_containers.qdrant_name
                == "cidx-old_hash_123-qdrant"
            )

            # Ports should be updated
            assert updated_config.project_ports.qdrant_port == 7000

    def test_apply_project_config_fixes_handles_missing_ports(self):
        """Test that _apply_project_config_fixes handles missing ports gracefully."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)

            config = Config(
                codebase_dir=Path("."),
                project_containers=ProjectContainersConfig(
                    project_hash="old_hash_123",
                    qdrant_name="cidx-old_hash_123-qdrant",
                ),
                project_ports=ProjectPortsConfig(qdrant_port=6000),
            )

            repairer = ConfigurationRepairer(config_dir, dry_run=False)

            # Project info with only container names, no ports
            project_info = {
                "container_names": {
                    "project_hash": "new_hash_456",
                    "qdrant_name": "cidx-new_hash_456-qdrant",
                },
            }

            # Should not fail, should only update container names
            updated_config = repairer._apply_project_config_fixes(config, project_info)

            # Container names should be updated
            assert updated_config.project_containers.project_hash == "new_hash_456"
            assert (
                updated_config.project_containers.qdrant_name
                == "cidx-new_hash_456-qdrant"
            )

            # Ports should be unchanged
            assert updated_config.project_ports.qdrant_port == 6000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
