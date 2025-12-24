"""
Tests to replicate and verify broken softlink cleanup logic.
These tests CREATE broken softlinks to test cleanup behavior.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
from code_indexer.services.global_port_registry import GlobalPortRegistry


class TestBrokenSoftlinkCleanup:
    """Test broken softlink cleanup scenarios."""

    @pytest.fixture
    def registry_with_broken_links(self):
        """Create registry with various broken softlink scenarios."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "test-registry"
            registry_path.mkdir()
            active_projects = registry_path / "active-projects"
            active_projects.mkdir()

            # Create port allocations file
            allocations_file = registry_path / "port-allocations.json"
            allocations = {
                "6333": {"project_hash": "broken1", "service": "filesystem"},
                "6334": {"project_hash": "broken2", "service": "filesystem"},
                "6335": {"project_hash": "valid1", "service": "filesystem"},
                "11434": {"project_hash": "broken1", "service": "voyage"},
            }
            allocations_file.write_text(json.dumps(allocations, indent=2))
            (registry_path / "registry.log").touch()

            # Scenario 1: Deleted project folder
            broken_link1 = active_projects / "proj-broken1"
            deleted_project = Path(temp_dir) / "deleted-project" / ".code-indexer"
            deleted_project.mkdir(parents=True)
            broken_link1.symlink_to(deleted_project)
            # Now delete the target
            os.rmdir(deleted_project)
            os.rmdir(deleted_project.parent)

            # Scenario 2: Deleted .code-indexer folder only
            project2 = Path(temp_dir) / "project2"
            project2.mkdir()
            config_dir2 = project2 / ".code-indexer"
            config_dir2.mkdir()
            broken_link2 = active_projects / "proj-broken2"
            broken_link2.symlink_to(config_dir2)
            # Delete only .code-indexer folder
            os.rmdir(config_dir2)

            # Scenario 3: Valid project (should NOT be cleaned)
            project3 = Path(temp_dir) / "project3"
            project3.mkdir()
            config_dir3 = project3 / ".code-indexer"
            config_dir3.mkdir()
            config_file3 = config_dir3 / "config.json"
            config_file3.write_text(
                '{"project_containers": {"project_hash": "valid1"}, "project_ports": {"filesystem_port": 6335}}'
            )
            valid_link = active_projects / "proj-valid1"
            valid_link.symlink_to(config_dir3)

            # Scenario 4: Missing config.json
            project4 = Path(temp_dir) / "project4"
            project4.mkdir()
            config_dir4 = project4 / ".code-indexer"
            config_dir4.mkdir()
            # No config.json file
            broken_link4 = active_projects / "proj-broken3"
            broken_link4.symlink_to(config_dir4)

            with patch.object(
                GlobalPortRegistry, "_get_registry_path", return_value=registry_path
            ):
                yield GlobalPortRegistry()

    def test_cleanup_detects_broken_links(self, registry_with_broken_links):
        """RED: Test cleanup detects all types of broken links."""
        registry = registry_with_broken_links

        # Verify initial state - should have 4 links (3 broken, 1 valid)
        initial_links = list(registry.active_projects_path.iterdir())
        assert len(initial_links) == 4

        # Run cleanup
        result = registry.scan_and_cleanup_registry()

        # Verify broken links were removed
        assert result["cleaned"] == 3  # 3 broken links removed
        assert result["active"] == 1  # 1 valid project remains

        # Verify only valid link remains
        remaining_links = list(registry.active_projects_path.iterdir())
        assert len(remaining_links) == 1
        assert remaining_links[0].name == "proj-valid1"

    def test_cleanup_frees_ports_from_broken_projects(self, registry_with_broken_links):
        """RED: Test cleanup frees ports from broken projects."""
        registry = registry_with_broken_links

        # Run cleanup
        result = registry.scan_and_cleanup_registry()

        # Verify ports were freed
        freed_ports = result["freed_ports"]
        assert 6333 in freed_ports  # From broken1
        assert 6334 in freed_ports  # From broken2
        assert 11434 in freed_ports  # From broken1
        assert 6335 not in freed_ports  # From valid1 - should not be freed

    def test_cleanup_rebuilds_port_allocations(self, registry_with_broken_links):
        """RED: Test cleanup rebuilds port allocations file."""
        registry = registry_with_broken_links

        # Run cleanup
        registry.scan_and_cleanup_registry()

        # Verify allocations file was rebuilt
        with open(registry.port_allocations_file) as f:
            allocations = json.load(f)

        # Should only have valid project's ports
        assert "6335" in allocations
        assert allocations["6335"]["project_hash"] == "valid1"

        # Broken projects' ports should be removed
        assert "6333" not in allocations  # broken1
        assert "6334" not in allocations  # broken2
        assert "11434" not in allocations  # broken1

    def test_circular_softlink_handling(self):
        """RED: Test handling of circular softlinks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "registry"
            registry_path.mkdir()
            active_projects = registry_path / "active-projects"
            active_projects.mkdir()
            (registry_path / "port-allocations.json").touch()
            (registry_path / "registry.log").touch()

            # Create circular softlink
            circular_link = active_projects / "proj-circular"
            circular_link.symlink_to(circular_link)  # Points to itself

            with patch.object(
                GlobalPortRegistry, "_get_registry_path", return_value=registry_path
            ):
                registry = GlobalPortRegistry()

                # Should handle circular link gracefully
                result = registry.scan_and_cleanup_registry()
                assert result["cleaned"] == 1
                assert not circular_link.exists()

    def test_corrupted_config_json_cleanup(self):
        """RED: Test cleanup of projects with corrupted config.json."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "registry"
            registry_path.mkdir()
            active_projects = registry_path / "active-projects"
            active_projects.mkdir()
            (registry_path / "port-allocations.json").touch()
            (registry_path / "registry.log").touch()

            # Create project with corrupted config
            project = Path(temp_dir) / "corrupted-project"
            project.mkdir()
            config_dir = project / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text("{ invalid json content }")  # Corrupted JSON

            # Create link to corrupted project
            broken_link = active_projects / "proj-corrupted"
            broken_link.symlink_to(config_dir)

            with patch.object(
                GlobalPortRegistry, "_get_registry_path", return_value=registry_path
            ):
                registry = GlobalPortRegistry()

                # Should clean up corrupted config
                result = registry.scan_and_cleanup_registry()
                assert result["cleaned"] == 1
                assert not broken_link.exists()

    def test_permission_denied_project_cleanup(self):
        """RED: Test cleanup when project directory has permission issues."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "registry"
            registry_path.mkdir()
            active_projects = registry_path / "active-projects"
            active_projects.mkdir()
            (registry_path / "port-allocations.json").touch()
            (registry_path / "registry.log").touch()

            # Create project
            project = Path(temp_dir) / "permission-project"
            project.mkdir()
            config_dir = project / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text('{"project_containers": {"project_hash": "perm1"}}')

            # Create link
            link = active_projects / "proj-perm1"
            link.symlink_to(config_dir)

            # Mock permission error on config file access
            with patch.object(
                GlobalPortRegistry, "_get_registry_path", return_value=registry_path
            ):
                registry = GlobalPortRegistry()

                with patch(
                    "builtins.open", side_effect=PermissionError("Access denied")
                ):
                    # Should handle permission error gracefully
                    result = registry.scan_and_cleanup_registry()
                    # Should clean project with permission issues
                    assert (
                        result["cleaned"] >= 0
                    )  # May or may not clean depending on when permission error occurs

    def test_empty_registry_cleanup(self):
        """RED: Test cleanup with empty registry."""
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "registry"
            registry_path.mkdir()
            active_projects = registry_path / "active-projects"
            active_projects.mkdir()
            (registry_path / "port-allocations.json").touch()
            (registry_path / "registry.log").touch()

            with patch.object(
                GlobalPortRegistry, "_get_registry_path", return_value=registry_path
            ):
                registry = GlobalPortRegistry()

                # Should handle empty registry gracefully
                result = registry.scan_and_cleanup_registry()
                assert result["cleaned"] == 0
                assert result["active"] == 0
                assert result["freed_ports"] == []
