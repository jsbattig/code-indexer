"""Unit tests for ConfigManager.get_socket_path() updates."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from code_indexer.config import ConfigManager, DaemonConfig
from code_indexer.daemon.socket_helper import generate_repo_hash


class TestConfigManagerSocketPath:
    """Tests for updated get_socket_path method."""

    @patch('code_indexer.daemon.socket_helper.generate_socket_path')
    @patch('code_indexer.daemon.socket_helper.create_mapping_file')
    def test_get_socket_path_uses_new_helper(self, mock_create_mapping, mock_generate):
        """get_socket_path should use socket_helper module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"daemon": {"enabled": true}}')

            mock_socket_path = Path("/tmp/cidx/abcd1234.sock")
            mock_generate.return_value = mock_socket_path

            manager = ConfigManager(config_path)
            socket_path = manager.get_socket_path()

            # Should call generate_socket_path with repo path and mode
            mock_generate.assert_called_once_with(config_path.parent.parent, "shared")
            # Should create mapping file
            mock_create_mapping.assert_called_once_with(config_path.parent.parent, mock_socket_path)
            assert socket_path == mock_socket_path

    @patch('code_indexer.daemon.socket_helper.generate_socket_path')
    @patch('code_indexer.daemon.socket_helper.create_mapping_file')
    def test_get_socket_path_respects_socket_mode(self, mock_create_mapping, mock_generate):
        """get_socket_path should honor daemon.socket_mode config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"daemon": {"enabled": true, "socket_mode": "user"}}')

            mock_socket_path = Path("/run/user/1000/cidx/abcd1234.sock")
            mock_generate.return_value = mock_socket_path

            manager = ConfigManager(config_path)
            socket_path = manager.get_socket_path()

            # Should use "user" mode from config
            mock_generate.assert_called_once_with(config_path.parent.parent, "user")
            assert socket_path == mock_socket_path

    @patch('code_indexer.daemon.socket_helper.ensure_socket_directory')
    @patch('code_indexer.daemon.socket_helper.generate_repo_hash')
    @patch('code_indexer.daemon.socket_helper.create_mapping_file')
    def test_get_socket_path_uses_custom_socket_base(self, mock_create_mapping, mock_hash, mock_ensure):
        """get_socket_path should use daemon.socket_base if provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"daemon": {"enabled": true, "socket_base": "/custom/socket/dir"}}')

            mock_hash.return_value = "customhash123456"

            manager = ConfigManager(config_path)
            socket_path = manager.get_socket_path()

            # Should use custom base
            assert socket_path == Path("/custom/socket/dir/customhash123456.sock")
            # Should ensure directory with shared mode (default)
            mock_ensure.assert_called_once_with(Path("/custom/socket/dir"), "shared")
            # Should create mapping
            mock_create_mapping.assert_called_once()

    @patch('code_indexer.daemon.socket_helper.generate_socket_path')
    @patch('code_indexer.daemon.socket_helper.create_mapping_file')
    def test_get_socket_path_creates_mapping_file(self, mock_create_mapping, mock_generate):
        """get_socket_path should create mapping file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"daemon": {"enabled": true}}')

            mock_socket_path = Path("/tmp/cidx/test123.sock")
            mock_generate.return_value = mock_socket_path

            manager = ConfigManager(config_path)
            socket_path = manager.get_socket_path()

            # Should create mapping file with repo path and socket path
            mock_create_mapping.assert_called_once_with(config_path.parent.parent, mock_socket_path)

    def test_get_socket_path_length_always_under_108(self):
        """Socket path must never exceed 108 chars, even in deep directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a very deep directory structure
            deep_path = Path(tmpdir)
            for i in range(30):
                deep_path = deep_path / f"very_long_directory_name_{i:03d}"

            deep_path.mkdir(parents=True)
            config_path = deep_path / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"daemon": {"enabled": true}}')

            # Verify the path would be too long with old method
            old_socket_path = config_path.parent / "daemon.sock"
            assert len(str(old_socket_path)) > 108

            manager = ConfigManager(config_path)
            new_socket_path = manager.get_socket_path()

            # New socket path should be short
            assert len(str(new_socket_path)) < 108
            # Should be in /tmp/cidx/
            assert str(new_socket_path).startswith("/tmp/cidx/")
            # Should end with .sock
            assert str(new_socket_path).endswith(".sock")

    @patch('code_indexer.daemon.socket_helper.ensure_socket_directory')
    @patch('code_indexer.daemon.socket_helper.generate_repo_hash')
    @patch('code_indexer.daemon.socket_helper.create_mapping_file')
    def test_socket_base_with_user_mode(self, mock_create_mapping, mock_hash, mock_ensure):
        """Custom socket_base with user mode should work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".code-indexer" / "config.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                '{"daemon": {"enabled": true, "socket_mode": "user", "socket_base": "/var/run/cidx"}}'
            )

            mock_hash.return_value = "userhash12345678"

            manager = ConfigManager(config_path)
            socket_path = manager.get_socket_path()

            # Should use custom base with user mode permissions
            assert socket_path == Path("/var/run/cidx/userhash12345678.sock")
            mock_ensure.assert_called_once_with(Path("/var/run/cidx"), "user")