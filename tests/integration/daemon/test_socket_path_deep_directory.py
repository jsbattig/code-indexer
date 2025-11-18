"""Integration test for socket path in deep directory structures."""

import os
import tempfile
from pathlib import Path

import pytest

from code_indexer.config import ConfigManager
from code_indexer.daemon.socket_helper import generate_socket_path, get_repo_from_mapping


class TestDeepDirectorySocketPath:
    """Test daemon socket path works in very deep directory structures."""

    def test_daemon_starts_in_deep_directory_structure(self):
        """Daemon should start successfully even in 126+ char paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a very deep directory structure (over 126 chars)
            deep_path = Path(tmpdir)
            for i in range(30):
                deep_path = deep_path / f"very_long_directory_name_{i:03d}"

            deep_path.mkdir(parents=True)

            # Verify the path would exceed 108 chars with old method
            old_socket_path = deep_path / ".code-indexer" / "daemon.sock"
            assert len(str(old_socket_path)) > 108, f"Test path not deep enough: {len(str(old_socket_path))}"

            # Initialize config in deep directory
            config_path = deep_path / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"daemon": {"enabled": true}}')

            # Create config manager and get socket path
            manager = ConfigManager(config_path)
            socket_path = manager.get_socket_path()

            # Verify socket path is under 108 chars
            assert len(str(socket_path)) < 108, f"Socket path too long: {len(str(socket_path))} chars"

            # Verify socket is in /tmp/cidx/
            assert str(socket_path).startswith("/tmp/cidx/")

            # Verify mapping file was created
            mapping_path = socket_path.with_suffix('.repo-path')
            assert mapping_path.exists()

            # Verify we can retrieve repo path from mapping
            retrieved_repo = get_repo_from_mapping(socket_path)
            assert retrieved_repo == deep_path

    def test_socket_path_accessible_to_multiple_users(self):
        """Socket in /tmp/cidx should be accessible to different users."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"daemon": {"enabled": true}}')

            manager = ConfigManager(config_path)
            socket_path = manager.get_socket_path()

            # Verify socket directory exists
            socket_dir = socket_path.parent
            assert socket_dir.exists()

            # Verify directory has sticky bit and world writable permissions (0o1777)
            stat_info = socket_dir.stat()
            mode = stat_info.st_mode & 0o7777

            # Check for sticky bit (0o1000) and world writable (0o007)
            assert mode & 0o1000 != 0, "Sticky bit not set"
            assert mode & 0o007 == 0o007, "Not world writable"

    def test_multiple_repos_get_unique_sockets(self):
        """Different repositories should get unique socket paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two different repositories
            repo1 = Path(tmpdir) / "repo1"
            repo2 = Path(tmpdir) / "repo2"

            for repo in [repo1, repo2]:
                repo.mkdir(parents=True)
                config_path = repo / ".code-indexer" / "config.yaml"
                config_path.parent.mkdir(parents=True)
                config_path.write_text('{"daemon": {"enabled": true}}')

            # Get socket paths for both
            manager1 = ConfigManager(repo1 / ".code-indexer" / "config.yaml")
            socket1 = manager1.get_socket_path()

            manager2 = ConfigManager(repo2 / ".code-indexer" / "config.yaml")
            socket2 = manager2.get_socket_path()

            # Verify they are different
            assert socket1 != socket2

            # Verify both are in /tmp/cidx/
            assert socket1.parent == Path("/tmp/cidx")
            assert socket2.parent == Path("/tmp/cidx")

            # Verify both have mapping files
            assert get_repo_from_mapping(socket1) == repo1
            assert get_repo_from_mapping(socket2) == repo2

    def test_socket_path_deterministic_across_runs(self):
        """Same repository should always get the same socket path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"daemon": {"enabled": true}}')

            # Get socket path multiple times
            paths = []
            for _ in range(5):
                manager = ConfigManager(config_path)
                paths.append(manager.get_socket_path())

            # All paths should be identical
            assert all(p == paths[0] for p in paths)