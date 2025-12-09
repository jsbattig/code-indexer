"""Unit tests for SSHKeyManager service (core orchestrator)."""

import pytest
from pathlib import Path
import json
import os

from code_indexer.server.services.ssh_key_manager import (
    SSHKeyManager,
    KeyMetadata,
    KeyListResult,
    KeyNotFoundError,
    HostConflictError,
    PublicKeyNotFoundError,
)


class TestSSHKeyManagerCreateKey:
    """Tests for SSHKeyManager.create_key()."""

    def test_create_key_generates_key_and_metadata(self, tmp_path):
        """Should generate SSH key and create metadata file."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        manager = SSHKeyManager(ssh_dir=ssh_dir, metadata_dir=metadata_dir)
        result = manager.create_key("test-key", email="test@example.com")

        # Verify key files created
        assert (ssh_dir / "test-key").exists()
        assert (ssh_dir / "test-key.pub").exists()

        # Verify metadata created
        assert (metadata_dir / "test-key.json").exists()

        # Verify result structure
        assert result.name == "test-key"
        assert result.email == "test@example.com"
        assert result.fingerprint is not None
        assert result.public_key is not None

    def test_create_key_with_description(self, tmp_path):
        """Should store description in metadata."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        manager = SSHKeyManager(ssh_dir=ssh_dir, metadata_dir=metadata_dir)
        result = manager.create_key("desc-key", description="Work GitHub key")

        assert result.description == "Work GitHub key"

        # Verify in saved metadata
        metadata_path = metadata_dir / "desc-key.json"
        saved = json.loads(metadata_path.read_text())
        assert saved["description"] == "Work GitHub key"


class TestSSHKeyManagerAssignKeyToHost:
    """Tests for SSHKeyManager.assign_key_to_host()."""

    def test_assign_key_updates_metadata(self, tmp_path):
        """Should add hostname to key's hosts list."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"
        config_path = ssh_dir / "config"

        manager = SSHKeyManager(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            config_path=config_path,
        )

        # Create a key first
        manager.create_key("assign-test-key")

        # Assign to host
        result = manager.assign_key_to_host("assign-test-key", "github.com")

        assert "github.com" in result.hosts

    def test_assign_key_updates_ssh_config(self, tmp_path):
        """Should add host entry to SSH config."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"
        config_path = ssh_dir / "config"

        manager = SSHKeyManager(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            config_path=config_path,
        )

        # Create a key first
        manager.create_key("config-test-key")

        # Assign to host
        manager.assign_key_to_host("config-test-key", "github.com")

        # Verify SSH config updated
        assert config_path.exists()
        config_content = config_path.read_text()
        assert "Host github.com" in config_content
        assert "config-test-key" in config_content

    def test_assign_key_not_found(self, tmp_path):
        """Should raise KeyNotFoundError for non-existent key."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        manager = SSHKeyManager(ssh_dir=ssh_dir, metadata_dir=metadata_dir)

        with pytest.raises(KeyNotFoundError):
            manager.assign_key_to_host("nonexistent-key", "github.com")

    def test_assign_key_host_conflict(self, tmp_path):
        """Should raise HostConflictError when host exists in user section."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"
        config_path = ssh_dir / "config"

        # Create user-defined host entry
        config_path.write_text("""Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/user_key
""")

        manager = SSHKeyManager(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            config_path=config_path,
        )

        # Create a key
        manager.create_key("conflict-test-key")

        # Should fail due to conflict
        with pytest.raises(HostConflictError):
            manager.assign_key_to_host("conflict-test-key", "github.com")


class TestSSHKeyManagerDeleteKey:
    """Tests for SSHKeyManager.delete_key()."""

    def test_delete_key_removes_files_and_metadata(self, tmp_path):
        """Should remove key files, config entries, and metadata."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"
        config_path = ssh_dir / "config"

        manager = SSHKeyManager(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            config_path=config_path,
        )

        # Create and assign key
        manager.create_key("delete-test-key")
        manager.assign_key_to_host("delete-test-key", "github.com")

        # Delete key
        manager.delete_key("delete-test-key")

        # Verify files removed
        assert not (ssh_dir / "delete-test-key").exists()
        assert not (ssh_dir / "delete-test-key.pub").exists()
        assert not (metadata_dir / "delete-test-key.json").exists()

    def test_delete_key_idempotent(self, tmp_path):
        """Should succeed even if key doesn't exist (idempotent)."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        manager = SSHKeyManager(ssh_dir=ssh_dir, metadata_dir=metadata_dir)

        # Should not raise
        result = manager.delete_key("nonexistent-key")
        assert result is True


class TestSSHKeyManagerListKeys:
    """Tests for SSHKeyManager.list_keys()."""

    def test_list_keys_returns_managed_keys(self, tmp_path):
        """Should return managed keys from metadata."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        manager = SSHKeyManager(ssh_dir=ssh_dir, metadata_dir=metadata_dir)

        # Create some keys
        manager.create_key("key1")
        manager.create_key("key2")

        result = manager.list_keys()

        assert len(result.managed) == 2
        names = {k.name for k in result.managed}
        assert names == {"key1", "key2"}

    def test_list_keys_identifies_unmanaged_keys(self, tmp_path):
        """Should identify keys not tracked in metadata."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        # Create unmanaged key manually
        (ssh_dir / "unmanaged_key").write_text("PRIVATE")
        (ssh_dir / "unmanaged_key.pub").write_text("ssh-ed25519 AAAA...")

        manager = SSHKeyManager(ssh_dir=ssh_dir, metadata_dir=metadata_dir)

        # Create one managed key
        manager.create_key("managed_key")

        result = manager.list_keys()

        assert len(result.managed) == 1
        assert len(result.unmanaged) == 1
        assert result.unmanaged[0].name == "unmanaged_key"


class TestSSHKeyManagerGetPublicKey:
    """Tests for SSHKeyManager.get_public_key()."""

    def test_get_public_key_returns_content(self, tmp_path):
        """Should return public key file content."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        manager = SSHKeyManager(ssh_dir=ssh_dir, metadata_dir=metadata_dir)
        manager.create_key("pubkey-test")

        public_key = manager.get_public_key("pubkey-test")

        assert public_key is not None
        assert public_key.startswith("ssh-ed25519") or public_key.startswith("ssh-rsa")

    def test_get_public_key_not_found(self, tmp_path):
        """Should raise KeyNotFoundError for non-existent key."""
        ssh_dir = tmp_path / ".ssh"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        manager = SSHKeyManager(ssh_dir=ssh_dir, metadata_dir=metadata_dir)

        with pytest.raises(KeyNotFoundError):
            manager.get_public_key("nonexistent")
