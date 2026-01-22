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

        # Mock _extract_key_info to return known fingerprint and key_type
        # (discover_existing_keys now calls _extract_key_info directly)
        with patch.object(
            service,
            "_extract_key_info",
            return_value=("SHA256:abcdef123456", "ed25519"),
        ) as mock_extract:
            keys = service.discover_existing_keys()

            # Verify _extract_key_info was called with the public key path
            mock_extract.assert_called_once()
            call_args = mock_extract.call_args
            assert call_args[0][0] == ssh_dir / "id_ed25519.pub"

            assert len(keys) == 1
            assert keys[0].fingerprint == "SHA256:abcdef123456"
            assert keys[0].key_type == "ed25519"

    def test_discover_keys_handles_fingerprint_failure_gracefully(self, tmp_path):
        """Should leave fingerprint and key_type as None if extraction fails."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create a key pair
        (ssh_dir / "id_rsa").write_text("PRIVATE KEY CONTENT")
        (ssh_dir / "id_rsa.pub").write_text("ssh-rsa AAAA... test@example.com")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # Mock _extract_key_info to return (None, None) (failure case)
        # (discover_existing_keys now calls _extract_key_info directly)
        with patch.object(service, "_extract_key_info", return_value=(None, None)):
            keys = service.discover_existing_keys()

        assert len(keys) == 1
        assert keys[0].fingerprint is None
        assert keys[0].key_type is None

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


class TestKeyDiscoveryServiceKeyTypeExtraction:
    """Tests for key_type extraction from ssh-keygen output (Story #728)."""

    def test_extract_key_info_ed25519_key_type(self, tmp_path):
        """Should extract ED25519 key type from ssh-keygen output."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_ed25519.pub"
        pub_key_path.write_text("ssh-ed25519 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # ssh-keygen output: "256 SHA256:fingerprint comment (ED25519)"
        mock_result = MagicMock()
        mock_result.stdout = "256 SHA256:abcdef123456 user@host (ED25519)\n"
        mock_result.returncode = 0

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint == "SHA256:abcdef123456"
        assert key_type == "ed25519"

    def test_extract_key_info_rsa_key_type(self, tmp_path):
        """Should extract RSA key type from ssh-keygen output."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_rsa.pub"
        pub_key_path.write_text("ssh-rsa AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # ssh-keygen output: "3072 SHA256:fingerprint comment (RSA)"
        mock_result = MagicMock()
        mock_result.stdout = "3072 SHA256:xyzPQR789abc user@host (RSA)\n"
        mock_result.returncode = 0

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint == "SHA256:xyzPQR789abc"
        assert key_type == "rsa"

    def test_extract_key_info_ecdsa_key_type(self, tmp_path):
        """Should extract ECDSA key type from ssh-keygen output."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_ecdsa.pub"
        pub_key_path.write_text("ecdsa-sha2-nistp256 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # ssh-keygen output: "256 SHA256:fingerprint comment (ECDSA)"
        mock_result = MagicMock()
        mock_result.stdout = "256 SHA256:ecdsa123456 user@host (ECDSA)\n"
        mock_result.returncode = 0

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint == "SHA256:ecdsa123456"
        assert key_type == "ecdsa"

    def test_extract_key_info_key_without_comment(self, tmp_path):
        """Should extract key type when comment is absent."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_ed25519.pub"
        pub_key_path.write_text("ssh-ed25519 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # ssh-keygen output without comment: "256 SHA256:fingerprint (ED25519)"
        mock_result = MagicMock()
        mock_result.stdout = "256 SHA256:nocomment123 (ED25519)\n"
        mock_result.returncode = 0

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint == "SHA256:nocomment123"
        assert key_type == "ed25519"

    def test_extract_key_info_key_with_long_comment(self, tmp_path):
        """Should extract key type when comment has multiple parts."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_rsa.pub"
        pub_key_path.write_text("ssh-rsa AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # ssh-keygen output with multi-word comment
        mock_result = MagicMock()
        mock_result.stdout = "4096 SHA256:longcomment123 My Work Laptop Key (RSA)\n"
        mock_result.returncode = 0

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint == "SHA256:longcomment123"
        assert key_type == "rsa"

    def test_extract_key_info_malformed_output_no_parens(self, tmp_path):
        """Should gracefully handle malformed output without parentheses."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_ed25519.pub"
        pub_key_path.write_text("ssh-ed25519 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # Malformed output without key type in parentheses
        mock_result = MagicMock()
        mock_result.stdout = "256 SHA256:malformed123 user@host\n"
        mock_result.returncode = 0

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint == "SHA256:malformed123"
        assert key_type is None

    def test_extract_key_info_empty_output(self, tmp_path):
        """Should return (None, None) for empty output."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_ed25519.pub"
        pub_key_path.write_text("ssh-ed25519 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint is None
        assert key_type is None

    def test_extract_key_info_nonzero_return_code(self, tmp_path):
        """Should return (None, None) for non-zero return code."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_ed25519.pub"
        pub_key_path.write_text("ssh-ed25519 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        mock_result = MagicMock()
        mock_result.stdout = "256 SHA256:abc (ED25519)\n"
        mock_result.returncode = 1

        with patch.object(kds_module.subprocess, "run", return_value=mock_result):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint is None
        assert key_type is None

    def test_extract_key_info_subprocess_exception(self, tmp_path):
        """Should return (None, None) when subprocess raises exception."""
        import code_indexer.server.services.key_discovery_service as kds_module

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        pub_key_path = ssh_dir / "id_ed25519.pub"
        pub_key_path.write_text("ssh-ed25519 AAAA...")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        with patch.object(
            kds_module.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("cmd", 5),
        ):
            fingerprint, key_type = service._extract_key_info(pub_key_path)

        assert fingerprint is None
        assert key_type is None

    def test_discover_keys_populates_key_type(self, tmp_path):
        """Should populate key_type in discovered keys via _extract_key_info."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create a key pair
        (ssh_dir / "id_ed25519").write_text("PRIVATE KEY CONTENT")
        (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA... test@example.com")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # Mock _extract_key_info to return both fingerprint and key_type
        with patch.object(
            service,
            "_extract_key_info",
            return_value=("SHA256:abcdef123456", "ed25519"),
        ) as mock_extract:
            keys = service.discover_existing_keys()

            mock_extract.assert_called_once()
            call_args = mock_extract.call_args
            assert call_args[0][0] == ssh_dir / "id_ed25519.pub"

            assert len(keys) == 1
            assert keys[0].fingerprint == "SHA256:abcdef123456"
            assert keys[0].key_type == "ed25519"

    def test_discover_keys_handles_extract_failure_gracefully(self, tmp_path):
        """Should leave fingerprint and key_type as None if extraction fails."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        # Create a key pair
        (ssh_dir / "id_rsa").write_text("PRIVATE KEY CONTENT")
        (ssh_dir / "id_rsa.pub").write_text("ssh-rsa AAAA... test@example.com")

        service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # Mock _extract_key_info to return (None, None) (failure case)
        with patch.object(service, "_extract_key_info", return_value=(None, None)):
            keys = service.discover_existing_keys()

        assert len(keys) == 1
        assert keys[0].fingerprint is None
        assert keys[0].key_type is None
