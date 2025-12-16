"""Unit tests for SSHConfigManager service."""

import pytest
from pathlib import Path

from code_indexer.server.services.ssh_config_manager import (
    SSHConfigManager,
    ParsedConfig,
    CorruptedConfigError,
    HostEntry,
)


class TestSSHConfigManagerParseConfig:
    """Tests for SSHConfigManager.ParseConfig()."""

    def test_parse_config_empty_when_file_not_exists(self):
        """Should return empty ParsedConfig when config file doesn't exist."""
        manager = SSHConfigManager()
        non_existent = Path("/tmp/nonexistent_ssh_config_12345.conf")

        parsed = manager.parse_config(non_existent)

        assert parsed.cidx_section == []
        assert parsed.user_section == []
        assert parsed.include_directives == []

    def test_parse_config_user_section_only(self, tmp_path):
        """Should populate user_section when config has no CIDX markers."""
        config_file = tmp_path / "config"
        config_content = """Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_rsa

Host gitlab.com
  HostName gitlab.com
  User git
  IdentityFile ~/.ssh/id_ed25519
"""
        config_file.write_text(config_content)

        manager = SSHConfigManager()
        parsed = manager.parse_config(config_file)

        assert parsed.cidx_section == []
        assert len(parsed.user_section) > 0
        assert "Host github.com" in parsed.user_section[0]
        assert parsed.include_directives == []

    def test_parse_config_with_cidx_section(self, tmp_path):
        """Should separate CIDX section from user section."""
        config_file = tmp_path / "config"
        config_content = """# BEGIN CIDX-MANAGED SSH KEYS - DO NOT EDIT
Host cidx-managed.com
  HostName cidx-managed.com
  User git
  IdentityFile ~/.ssh/cidx_key
# END CIDX-MANAGED SSH KEYS

Host user-defined.com
  HostName user-defined.com
  User git
  IdentityFile ~/.ssh/user_key
"""
        config_file.write_text(config_content)

        manager = SSHConfigManager()
        parsed = manager.parse_config(config_file)

        # CIDX section should contain the managed entry
        assert len(parsed.cidx_section) > 0
        cidx_joined = "\n".join(parsed.cidx_section)
        assert "cidx-managed.com" in cidx_joined

        # User section should contain the user entry
        assert len(parsed.user_section) > 0
        user_joined = "\n".join(parsed.user_section)
        assert "user-defined.com" in user_joined
        assert "cidx-managed.com" not in user_joined

    def test_parse_config_with_include_directive(self, tmp_path):
        """Should extract Include directives with positions."""
        config_file = tmp_path / "config"
        config_content = """Include ~/.ssh/config.d/*

Host myhost.com
  HostName myhost.com
  User git
"""
        config_file.write_text(config_content)

        manager = SSHConfigManager()
        parsed = manager.parse_config(config_file)

        assert len(parsed.include_directives) == 1
        directive, position = parsed.include_directives[0]
        assert "Include" in directive
        assert "~/.ssh/config.d/*" in directive
        assert position == 0  # First line

    def test_parse_config_corrupted_missing_end_marker(self, tmp_path):
        """Should raise CorruptedConfigError when end marker is missing."""
        config_file = tmp_path / "config"
        config_content = """# BEGIN CIDX-MANAGED SSH KEYS - DO NOT EDIT
Host cidx-managed.com
  HostName cidx-managed.com
  User git
  IdentityFile ~/.ssh/cidx_key

Host user-defined.com
  HostName user-defined.com
  User git
"""
        config_file.write_text(config_content)

        manager = SSHConfigManager()

        with pytest.raises(CorruptedConfigError) as exc_info:
            manager.parse_config(config_file)

        assert "end marker" in str(exc_info.value).lower()

        # Verify backup was created
        backup_files = list(tmp_path.glob("config.cidx-backup-*"))
        assert len(backup_files) == 1


class TestSSHConfigManagerWriteConfig:
    """Tests for SSHConfigManager.WriteConfig()."""

    def test_write_config_creates_new_file(self, tmp_path):
        """Should create new config file with CIDX section when file doesn't exist."""
        config_file = tmp_path / "config"
        manager = SSHConfigManager()

        # Create a host entry
        entries = [
            HostEntry(host="github.com", hostname="github.com", key_path="~/.ssh/my-key")
        ]

        # Write to non-existent file
        manager.write_config(config_file, ParsedConfig(), entries)

        # Verify file was created
        assert config_file.exists()
        content = config_file.read_text()

        # Verify CIDX markers present
        assert "# BEGIN CIDX-MANAGED SSH KEYS - DO NOT EDIT" in content
        assert "# END CIDX-MANAGED SSH KEYS" in content

        # Verify host entry
        assert "Host github.com" in content
        assert "HostName github.com" in content
        assert "IdentityFile ~/.ssh/my-key" in content

    def test_write_config_preserves_user_section(self, tmp_path):
        """Should preserve user section byte-for-byte."""
        config_file = tmp_path / "config"
        # Create config with user entries first
        user_content = """Host myserver.com
  HostName myserver.com
  User admin
  IdentityFile ~/.ssh/admin_key
"""
        config_file.write_text(user_content)

        manager = SSHConfigManager()
        parsed = manager.parse_config(config_file)

        # Add CIDX entries
        entries = [
            HostEntry(host="github.com", hostname="github.com", key_path="~/.ssh/cidx-key")
        ]

        manager.write_config(config_file, parsed, entries)

        # Verify user content preserved
        new_content = config_file.read_text()
        assert "Host myserver.com" in new_content
        assert "HostName myserver.com" in new_content
        assert "User admin" in new_content
        assert "IdentityFile ~/.ssh/admin_key" in new_content

        # Verify CIDX section added
        assert "# BEGIN CIDX-MANAGED SSH KEYS" in new_content
        assert "Host github.com" in new_content

    def test_write_config_preserves_include_directives(self, tmp_path):
        """Should preserve Include directives at top of file."""
        config_file = tmp_path / "config"
        # Create config with Include directive first
        original_content = """Include ~/.ssh/config.d/*

Host myserver.com
  HostName myserver.com
  User admin
"""
        config_file.write_text(original_content)

        manager = SSHConfigManager()
        parsed = manager.parse_config(config_file)

        # Add CIDX entries
        entries = [
            HostEntry(host="github.com", hostname="github.com", key_path="~/.ssh/cidx-key")
        ]

        manager.write_config(config_file, parsed, entries)

        # Verify Include directive is at top
        new_content = config_file.read_text()
        lines = new_content.split("\n")
        assert lines[0].strip().startswith("Include")

        # Verify CIDX section comes after Include
        include_pos = new_content.find("Include")
        cidx_start_pos = new_content.find("# BEGIN CIDX-MANAGED")
        assert include_pos < cidx_start_pos


class TestSSHConfigManagerCheckHostConflict:
    """Tests for SSHConfigManager.CheckHostConflict()."""

    def test_check_host_conflict_no_conflict(self, tmp_path):
        """Should return no conflict when hostname not in user section."""
        config_file = tmp_path / "config"
        config_content = """Host myserver.com
  HostName myserver.com
  User admin
"""
        config_file.write_text(config_content)

        manager = SSHConfigManager()
        conflict = manager.check_host_conflict(config_file, "github.com")

        assert conflict.exists is False

    def test_check_host_conflict_found_in_user_section(self, tmp_path):
        """Should return conflict when hostname exists in user section."""
        config_file = tmp_path / "config"
        config_content = """Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/user_key
"""
        config_file.write_text(config_content)

        manager = SSHConfigManager()
        conflict = manager.check_host_conflict(config_file, "github.com")

        assert conflict.exists is True
        assert conflict.in_user_section is True
