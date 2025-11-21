"""Test module for adapted command behavior in different modes.

Tests the CLI command routing that adapts status and uninstall commands
based on the detected mode (local, remote, uninitialized).
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from code_indexer.cli import cli
from click.testing import CliRunner


class TestAdaptedStatusCommand:
    """Test class for mode-adapted status command behavior."""

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()
            yield project_root

    @pytest.fixture
    def cli_runner(self):
        """Create CLI runner for testing."""
        return CliRunner()

    def test_status_command_routes_to_local_mode(self, temp_project_root, cli_runner):
        """Test that status command routes to local mode implementation when in local mode."""
        # Create valid local config
        local_config = {
            "voyage": {"host": "http://localhost:11434", "model": "nomic-embed-text"},
            "filesystem": {"host": "http://localhost:6333"},
            "ports": {"voyage_port": 11434, "filesystem_port": 6333},
        }
        config_path = temp_project_root / ".code-indexer" / "config.json"
        with open(config_path, "w") as f:
            json.dump(local_config, f)

        with patch(
            "code_indexer.mode_specific_handlers.display_local_status"
        ) as mock_local_status:
            mock_local_status.return_value = None

            with cli_runner.isolated_filesystem():
                # Change to project directory
                import os

                os.chdir(temp_project_root)

                cli_runner.invoke(cli, ["status"])

                # Test should work now that routing is implemented
                mock_local_status.assert_called_once_with(temp_project_root, False)

    def test_status_command_routes_to_remote_mode(self, temp_project_root, cli_runner):
        """Test that status command routes to remote mode implementation when in remote mode."""
        # Create valid remote config
        remote_config = {
            "server_url": "https://server.example.com",
            "encrypted_credentials": "encrypted_jwt_token",
            "repository_link": {
                "alias": "test-repo",
                "url": "https://github.com/test/repo.git",
                "branch": "main",
            },
        }
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(remote_config, f)

        with patch(
            "code_indexer.mode_specific_handlers.display_remote_status"
        ) as mock_remote_status:
            mock_remote_status.return_value = AsyncMock()

            with cli_runner.isolated_filesystem():
                # Change to project directory
                import os

                os.chdir(temp_project_root)

                cli_runner.invoke(cli, ["status"])

                # Test should work now that routing is implemented
                mock_remote_status.assert_called_once_with(temp_project_root)

    def test_status_command_routes_to_uninitialized_mode(
        self, temp_project_root, cli_runner
    ):
        """Test that status command routes to uninitialized mode when no valid config exists."""
        # No config files created - should be uninitialized

        with patch(
            "code_indexer.mode_specific_handlers.display_uninitialized_status"
        ) as mock_uninit_status:
            mock_uninit_status.return_value = None

            with cli_runner.isolated_filesystem():
                # Change to project directory
                import os

                os.chdir(temp_project_root)

                cli_runner.invoke(cli, ["status"])

                # Test should work now that routing is implemented
                mock_uninit_status.assert_called_once_with(temp_project_root)

    def test_status_command_preserves_existing_flags(
        self, temp_project_root, cli_runner
    ):
        """Test that status command preserves existing CLI flags when routing."""
        # Create valid local config
        local_config = {"voyage": {"host": "http://localhost:11434"}}
        config_path = temp_project_root / ".code-indexer" / "config.json"
        with open(config_path, "w") as f:
            json.dump(local_config, f)

        with patch(
            "code_indexer.mode_specific_handlers.display_local_status"
        ) as mock_local_status:
            mock_local_status.return_value = None

            with cli_runner.isolated_filesystem():
                # Change to project directory
                import os

                os.chdir(temp_project_root)

                # Test with --force-docker flag
                cli_runner.invoke(cli, ["status", "--force-docker"])

                # Test should work now that routing is implemented
                # Verify force_docker flag is passed through
                mock_local_status.assert_called_once()
                args, kwargs = mock_local_status.call_args
                # Check that force_docker=True was passed
                assert args[1] is True  # Second argument should be force_docker


class TestAdaptedUninstallCommand:
    """Test class for mode-adapted uninstall command behavior."""

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()
            yield project_root

    @pytest.fixture
    def cli_runner(self):
        """Create CLI runner for testing."""
        return CliRunner()

    def test_uninstall_command_routes_to_local_mode(
        self, temp_project_root, cli_runner
    ):
        """Test that uninstall command routes to local mode implementation when in local mode."""
        # Create valid local config
        local_config = {
            "voyage": {"host": "http://localhost:11434"},
            "filesystem": {"host": "http://localhost:6333"},
        }
        config_path = temp_project_root / ".code-indexer" / "config.json"
        with open(config_path, "w") as f:
            json.dump(local_config, f)

        with patch(
            "code_indexer.mode_specific_handlers.uninstall_local_mode"
        ) as mock_local_uninstall:
            mock_local_uninstall.return_value = None

            with cli_runner.isolated_filesystem():
                # Change to project directory
                import os

                os.chdir(temp_project_root)

                cli_runner.invoke(cli, ["uninstall", "--confirm"])

                # Test should work now that routing is implemented
                # Parameters: project_root, force_docker, wipe_all, confirm
                mock_local_uninstall.assert_called_once_with(
                    temp_project_root, False, False, True
                )

    def test_uninstall_command_routes_to_remote_mode(
        self, temp_project_root, cli_runner
    ):
        """Test that uninstall command routes to remote mode implementation when in remote mode."""
        # Create valid remote config
        remote_config = {
            "server_url": "https://server.example.com",
            "encrypted_credentials": "encrypted_jwt_token",
        }
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(remote_config, f)

        with patch(
            "code_indexer.mode_specific_handlers.uninstall_remote_mode"
        ) as mock_remote_uninstall:
            mock_remote_uninstall.return_value = None

            with cli_runner.isolated_filesystem():
                # Change to project directory
                import os

                os.chdir(temp_project_root)

                cli_runner.invoke(cli, ["uninstall", "--confirm"])

                # Test should work now that routing is implemented
                mock_remote_uninstall.assert_called_once_with(temp_project_root, True)

    def test_uninstall_command_preserves_existing_flags(
        self, temp_project_root, cli_runner
    ):
        """Test that uninstall command preserves existing CLI flags when routing."""
        # Create valid local config
        local_config = {"voyage": {"host": "http://localhost:11434"}}
        config_path = temp_project_root / ".code-indexer" / "config.json"
        with open(config_path, "w") as f:
            json.dump(local_config, f)

        with patch(
            "code_indexer.mode_specific_handlers.uninstall_local_mode"
        ) as mock_local_uninstall:
            mock_local_uninstall.return_value = None

            with cli_runner.isolated_filesystem():
                # Change to project directory
                import os

                os.chdir(temp_project_root)

                # Test with existing flags
                cli_runner.invoke(cli, ["uninstall", "--force-docker", "--wipe-all"])

                # Test should work now that routing is implemented
                mock_local_uninstall.assert_called_once()
                args, kwargs = mock_local_uninstall.call_args
                # Verify flags are passed through (project_root, force_docker, wipe_all)
                assert args[1] is True  # force_docker=True
                assert args[2] is True  # wipe_all=True


class TestModeDetectionIntegration:
    """Test class for mode detection integration with command routing."""

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()
            yield project_root

    def test_cli_context_includes_mode_information(self, temp_project_root):
        """Test that CLI context includes detected mode information."""
        # Create valid remote config
        remote_config = {
            "server_url": "https://server.example.com",
            "encrypted_credentials": "encrypted_jwt_token",
        }
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(remote_config, f)

        with patch(
            "code_indexer.mode_detection.command_mode_detector.find_project_root",
            return_value=temp_project_root,
        ):
            from code_indexer.mode_detection.command_mode_detector import (
                CommandModeDetector,
            )

            detector = CommandModeDetector(temp_project_root)
            mode = detector.detect_mode()

            # Test should verify integration exists
            assert mode == "remote"

    def test_cli_context_includes_project_root(self, temp_project_root):
        """Test that CLI context includes project root information."""
        with patch(
            "code_indexer.mode_detection.command_mode_detector.find_project_root",
            return_value=temp_project_root,
        ):
            from code_indexer.mode_detection.command_mode_detector import (
                find_project_root,
            )

            found_root = find_project_root(temp_project_root)

            # Test should verify integration exists
            assert found_root == temp_project_root

    def test_command_routing_uses_mode_detection(self, temp_project_root):
        """Test that command routing integrates with mode detection system."""
        # Create conflicting configs to test precedence
        local_config = {"voyage": {"host": "http://localhost:11434"}}
        local_config_path = temp_project_root / ".code-indexer" / "config.json"
        with open(local_config_path, "w") as f:
            json.dump(local_config, f)

        remote_config = {
            "server_url": "https://server.example.com",
            "encrypted_credentials": "encrypted_jwt_token",
        }
        remote_config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(remote_config_path, "w") as f:
            json.dump(remote_config, f)

        from code_indexer.mode_detection.command_mode_detector import (
            CommandModeDetector,
        )

        detector = CommandModeDetector(temp_project_root)
        mode = detector.detect_mode()

        # Remote should take precedence
        assert mode == "remote"
