"""Unit tests for KeyDiscoveryService."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from code_indexer.server.services.key_discovery_service import (
    KeyDiscoveryService,
)


class TestKeyDiscoveryServiceDiscoverKeys:
    """Tests for KeyDiscoveryService.discover_existing_keys()."""

    def test_discover_keys_empty_when_dir_not_exists(self, tmp_path):
        """Should return empty list when SSH directory doesn't exist."""
        non_existent = tmp_path / "nonexistent_ssh"
        service = KeyDiscoveryService(ssh_dir=non_existent)

        keys = service.discover_existing_keys()

        assert keys == []

    def test_discover_keys_finds_key_pairs(self, tmp_path):
        """Should discover keys that have both private and public files."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create a key pair
        (ssh_dir / "id_ed25519").write_text("PRIVATE KEY CONTENT")
        (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA... test@example.com")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)
        keys = service.discover_existing_keys()

        assert len(keys) == 1
        assert keys[0].name == "id_ed25519"
        assert keys[0].private_path == ssh_dir / "id_ed25519"
        assert keys[0].public_path == ssh_dir / "id_ed25519.pub"

    def test_discover_keys_ignores_pub_only_files(self, tmp_path):
        """Should ignore .pub files without corresponding private key."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create only public key file
        (ssh_dir / "orphan.pub").write_text("ssh-ed25519 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)
        keys = service.discover_existing_keys()

        assert len(keys) == 0

    def test_discover_keys_ignores_config_files(self, tmp_path):
        """Should ignore config, known_hosts, and other non-key files."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create non-key files
        (ssh_dir / "config").write_text("Host github.com")
        (ssh_dir / "known_hosts").write_text("github.com ssh-rsa AAAA...")
        (ssh_dir / "authorized_keys").write_text("ssh-rsa AAAA...")
        (ssh_dir / "environment").write_text("PATH=/usr/bin")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)
        keys = service.discover_existing_keys()

        assert len(keys) == 0

    def test_discover_keys_multiple_keys(self, tmp_path):
        """Should discover multiple key pairs."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create multiple key pairs
        for key_name in ["id_rsa", "id_ed25519", "work_key"]:
            (ssh_dir / key_name).write_text("PRIVATE KEY")
            (ssh_dir / f"{key_name}.pub").write_text(f"ssh-rsa AAAA... {key_name}")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)
        keys = service.discover_existing_keys()

        assert len(keys) == 3
        key_names = {k.name for k in keys}
        assert key_names == {"id_rsa", "id_ed25519", "work_key"}


class TestKeyDiscoveryServiceParseConfigMappings:
    """Tests for KeyDiscoveryService.parse_existing_config_mappings()."""

    def test_parse_mappings_empty_when_no_config(self, tmp_path):
        """Should return empty dict when config file doesn't exist."""
        config_path = tmp_path / "config"
        service = KeyDiscoveryService(ssh_dir=tmp_path)

        mappings = service.parse_existing_config_mappings(config_path)

        assert mappings == {}

    def test_parse_mappings_extracts_identity_files(self, tmp_path):
        """Should extract key-to-host mappings from config."""
        config_path = tmp_path / "config"
        config_content = """Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_key

Host gitlab.com
  HostName gitlab.com
  User git
  IdentityFile ~/.ssh/work_key
"""
        config_path.write_text(config_content)

        service = KeyDiscoveryService(ssh_dir=tmp_path)
        mappings = service.parse_existing_config_mappings(config_path)

        # Expand ~ in expected paths
        home = str(Path.home())
        github_key_path = f"{home}/.ssh/github_key"
        work_key_path = f"{home}/.ssh/work_key"

        assert github_key_path in mappings
        assert "github.com" in mappings[github_key_path]

        assert work_key_path in mappings
        assert "gitlab.com" in mappings[work_key_path]


class TestKeyDiscoveryServiceFingerprint:
    """Tests for fingerprint computation in discover_existing_keys()."""

    def test_discover_keys_computes_fingerprint(self, tmp_path):
        """Should compute fingerprint for discovered keys."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create a key pair
        (ssh_dir / "id_ed25519").write_text("PRIVATE KEY CONTENT")
        (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA... test@example.com")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # Mock _compute_fingerprint to return a known fingerprint
        with patch.object(
            service, "_compute_fingerprint", return_value="SHA256:abcdef123456"
        ) as mock_compute:
            keys = service.discover_existing_keys()

            # Verify _compute_fingerprint was called with the public key path
            mock_compute.assert_called_once()
            call_args = mock_compute.call_args
            assert call_args[0][0] == ssh_dir / "id_ed25519.pub"

            assert len(keys) == 1
            assert keys[0].fingerprint == "SHA256:abcdef123456"

    def test_discover_keys_handles_fingerprint_failure_gracefully(self, tmp_path):
        """Should leave fingerprint as None if computation fails."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create a key pair
        (ssh_dir / "id_rsa").write_text("PRIVATE KEY CONTENT")
        (ssh_dir / "id_rsa.pub").write_text("ssh-rsa AAAA... test@example.com")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # Mock _compute_fingerprint to return None (failure case)
        with patch.object(service, "_compute_fingerprint", return_value=None):
            keys = service.discover_existing_keys()

        assert len(keys) == 1
        assert keys[0].fingerprint is None

    def test_compute_fingerprint_parses_ssh_keygen_output(self, tmp_path):
        """Should correctly parse fingerprint from ssh-keygen output."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create a valid public key file
        pub_key_path = ssh_dir / "id_ed25519.pub"
        pub_key_path.write_text("ssh-ed25519 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # Mock subprocess.run at the module level where it's imported
        mock_result = MagicMock()
        mock_result.stdout = "3072 SHA256:xyzPQR789abc user@host (RSA)\n"
        mock_result.returncode = 0

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint = service._compute_fingerprint(pub_key_path)

        assert fingerprint == "SHA256:xyzPQR789abc"
