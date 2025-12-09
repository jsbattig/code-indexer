"""Tests for SSH Key CLI commands (Scenario 25)."""

import pytest
import json
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, MagicMock


class TestSSHKeyCLICommands:
    """Tests for Scenario 25: CLI Full Workflow for SSH key management."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    def test_ssh_key_create_command(self, runner, tmp_path):
        """CLI should create SSH key and display public key."""
        from code_indexer.cli import cli
        from code_indexer.server.services.ssh_key_manager import KeyMetadata

        mock_metadata = KeyMetadata(
            name="test-key",
            fingerprint="SHA256:abc123",
            key_type="ed25519",
            private_path=str(tmp_path / ".ssh" / "test-key"),
            public_path=str(tmp_path / ".ssh" / "test-key.pub"),
            public_key="ssh-ed25519 AAAAC3... user@example.com",
        )

        with patch(
            "code_indexer.server.services.ssh_key_manager.SSHKeyManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.create_key.return_value = mock_metadata
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                cli,
                ["ssh-key", "create", "test-key", "--email", "user@example.com"],
            )

            # Should succeed and show output
            assert result.exit_code == 0
            assert "test-key" in result.output
            assert "ssh-ed25519" in result.output

    def test_ssh_key_list_command(self, runner, tmp_path):
        """CLI should list managed and unmanaged keys."""
        from code_indexer.cli import cli
        from code_indexer.server.services.ssh_key_manager import (
            KeyMetadata,
            KeyListResult,
        )

        mock_result = KeyListResult(
            managed=[
                KeyMetadata(
                    name="my-key",
                    fingerprint="SHA256:abc123",
                    key_type="ed25519",
                    private_path="/home/user/.ssh/my-key",
                    public_path="/home/user/.ssh/my-key.pub",
                    hosts=["github.com"],
                )
            ],
            unmanaged=[],
        )

        with patch(
            "code_indexer.server.services.ssh_key_manager.SSHKeyManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.list_keys.return_value = mock_result
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli, ["ssh-key", "list"])

            # Should succeed and show key info
            assert result.exit_code == 0
            assert "my-key" in result.output

    def test_ssh_key_delete_command(self, runner, tmp_path):
        """CLI should delete key and mappings."""
        from code_indexer.cli import cli

        with patch(
            "code_indexer.server.services.ssh_key_manager.SSHKeyManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.delete_key.return_value = True
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                cli, ["ssh-key", "delete", "test-key", "--force"]
            )

            # Should succeed
            assert result.exit_code == 0
            assert "deleted" in result.output.lower()

    def test_ssh_key_show_public_command(self, runner, tmp_path):
        """CLI should display public key for copying."""
        from code_indexer.cli import cli

        public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKvN... user@example.com"

        with patch(
            "code_indexer.server.services.ssh_key_manager.SSHKeyManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_public_key.return_value = public_key
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli, ["ssh-key", "show-public", "test-key"])

            # Should succeed and show public key
            assert result.exit_code == 0
            assert "ssh-ed25519" in result.output

    def test_ssh_key_assign_command(self, runner, tmp_path):
        """CLI should assign host to key."""
        from code_indexer.cli import cli
        from code_indexer.server.services.ssh_key_manager import KeyMetadata

        mock_metadata = KeyMetadata(
            name="my-key",
            fingerprint="SHA256:abc123",
            key_type="ed25519",
            private_path="/home/user/.ssh/my-key",
            public_path="/home/user/.ssh/my-key.pub",
            hosts=["github.com"],
        )

        with patch(
            "code_indexer.server.services.ssh_key_manager.SSHKeyManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.assign_key_to_host.return_value = mock_metadata
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                cli,
                ["ssh-key", "assign", "my-key", "--host", "github.com"],
            )

            # Should succeed
            assert result.exit_code == 0
            assert "github.com" in result.output
