"""Unit tests for SSHKeyGenerator service."""

import pytest
from pathlib import Path
import os
import stat

from code_indexer.server.services.ssh_key_generator import (
    SSHKeyGenerator,
    GeneratedKey,
    InvalidKeyNameError,
    KeyAlreadyExistsError,
)


class TestSSHKeyGeneratorValidation:
    """Tests for SSHKeyGenerator key name validation."""

    def test_generate_key_rejects_path_traversal(self, tmp_path):
        """Should reject key names with path traversal attempts."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        with pytest.raises(InvalidKeyNameError):
            generator.generate_key("../../../etc/passwd")

    def test_generate_key_rejects_slashes(self, tmp_path):
        """Should reject key names with slashes."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        with pytest.raises(InvalidKeyNameError):
            generator.generate_key("key/with/slashes")

    def test_generate_key_rejects_semicolons(self, tmp_path):
        """Should reject key names with semicolons (command injection)."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        with pytest.raises(InvalidKeyNameError):
            generator.generate_key("key;rm -rf /")

    def test_generate_key_rejects_dash_prefix(self, tmp_path):
        """Should reject key names starting with dash."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        with pytest.raises(InvalidKeyNameError):
            generator.generate_key("-dangerous-key")


class TestSSHKeyGeneratorGenerate:
    """Tests for SSHKeyGenerator.generate_key()."""

    def test_generate_key_creates_files(self, tmp_path):
        """Should create private and public key files."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        result = generator.generate_key("test-key")

        assert result.name == "test-key"
        assert result.private_path.exists()
        assert result.public_path.exists()
        assert result.private_path == tmp_path / "test-key"
        assert result.public_path == tmp_path / "test-key.pub"

    def test_generate_key_sets_correct_permissions(self, tmp_path):
        """Should set 0600 on private key and 0644 on public key."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        result = generator.generate_key("perm-test-key")

        private_mode = stat.S_IMODE(result.private_path.stat().st_mode)
        public_mode = stat.S_IMODE(result.public_path.stat().st_mode)

        assert private_mode == 0o600
        assert public_mode == 0o644

    def test_generate_key_returns_public_key_content(self, tmp_path):
        """Should return the public key content."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        result = generator.generate_key("pubkey-test")

        assert result.public_key is not None
        assert len(result.public_key) > 0
        # Public key should start with key type
        assert result.public_key.startswith("ssh-ed25519") or result.public_key.startswith("ssh-rsa")

    def test_generate_key_returns_fingerprint(self, tmp_path):
        """Should return the key fingerprint."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        result = generator.generate_key("fingerprint-test")

        assert result.fingerprint is not None
        assert len(result.fingerprint) > 0
        # Fingerprint contains SHA256
        assert "SHA256" in result.fingerprint or ":" in result.fingerprint

    def test_generate_key_already_exists(self, tmp_path):
        """Should raise KeyAlreadyExistsError when key already exists."""
        generator = SSHKeyGenerator(ssh_dir=tmp_path)

        # Create first key
        generator.generate_key("existing-key")

        # Attempt to create second key with same name
        with pytest.raises(KeyAlreadyExistsError):
            generator.generate_key("existing-key")

    def test_generate_key_creates_ssh_dir(self, tmp_path):
        """Should create SSH directory if it doesn't exist."""
        ssh_dir = tmp_path / "nonexistent_ssh"
        generator = SSHKeyGenerator(ssh_dir=ssh_dir)

        generator.generate_key("new-dir-key")

        assert ssh_dir.exists()
        assert ssh_dir.is_dir()
