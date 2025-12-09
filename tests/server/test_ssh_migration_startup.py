"""Tests for SSH key migration at server startup (Scenario 12)."""

import pytest
from pathlib import Path
import json
import os
from unittest.mock import patch, MagicMock


class TestSSHMigrationStartup:
    """Tests for Scenario 12: First startup auto-discovery."""

    def test_run_ssh_migration_on_startup_first_time(self, tmp_path):
        """Migration should run automatically on first startup."""
        from code_indexer.server.services.ssh_startup_migration import (
            run_ssh_migration_on_startup,
        )

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create existing SSH keys
        (ssh_dir / "id_ed25519").write_text("PRIVATE KEY")
        (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA... test")
        (ssh_dir / "custom_key").write_text("PRIVATE KEY 2")
        (ssh_dir / "custom_key.pub").write_text("ssh-ed25519 BBBB... custom")

        # Create existing config with mappings
        (ssh_dir / "config").write_text(f"""Host github.com
  HostName github.com
  User git
  IdentityFile {ssh_dir}/id_ed25519
""")

        server_data_dir = tmp_path / ".code-indexer-server"
        server_data_dir.mkdir(parents=True)

        # Create CIDX config with activated repos
        config_path = server_data_dir / "config.json"
        config_path.write_text(json.dumps({
            "activated_repositories": [
                {"path": "/repo1", "remote_url": "git@github.com:user/repo1.git"},
                {"path": "/repo2", "remote_url": "git@gitlab.com:user/repo2.git"}
            ]
        }))

        result = run_ssh_migration_on_startup(
            server_data_dir=str(server_data_dir),
            ssh_dir=str(ssh_dir),
            skip_key_testing=True,  # Skip actual SSH testing
        )

        # Migration should run and complete
        assert result is not None
        assert result.completed is True
        assert result.skipped is False

        # Should have discovered both keys
        assert result.keys_discovered == 2
        assert result.keys_imported == 2

        # Should have imported existing mapping
        assert result.mappings_imported >= 1

        # Migration metadata should exist (prevents re-running)
        migration_metadata = server_data_dir / "ssh_migration.json"
        assert migration_metadata.exists()

        # Key metadata should exist
        ssh_keys_dir = server_data_dir / "ssh_keys"
        assert (ssh_keys_dir / "id_ed25519.json").exists()
        assert (ssh_keys_dir / "custom_key.json").exists()

    def test_run_ssh_migration_skips_if_already_done(self, tmp_path):
        """Migration should skip if already completed."""
        from code_indexer.server.services.ssh_startup_migration import (
            run_ssh_migration_on_startup,
        )

        server_data_dir = tmp_path / ".code-indexer-server"
        server_data_dir.mkdir(parents=True)

        # Mark migration as completed
        migration_metadata = server_data_dir / "ssh_migration.json"
        migration_metadata.write_text('{"completed": true}')

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        result = run_ssh_migration_on_startup(
            server_data_dir=str(server_data_dir),
            ssh_dir=str(ssh_dir),
        )

        # Migration should be skipped
        assert result is not None
        assert result.skipped is True
        assert "already completed" in result.reason.lower()

    def test_run_ssh_migration_handles_no_ssh_dir(self, tmp_path):
        """Migration should handle case where ~/.ssh doesn't exist."""
        from code_indexer.server.services.ssh_startup_migration import (
            run_ssh_migration_on_startup,
        )

        server_data_dir = tmp_path / ".code-indexer-server"
        server_data_dir.mkdir(parents=True)

        # No .ssh directory exists
        ssh_dir = tmp_path / ".ssh"

        result = run_ssh_migration_on_startup(
            server_data_dir=str(server_data_dir),
            ssh_dir=str(ssh_dir),
        )

        # Migration should complete with zero keys
        assert result is not None
        assert result.completed is True
        assert result.keys_discovered == 0
        assert result.keys_imported == 0

    def test_migration_timeout_handling(self, tmp_path):
        """Scenario 13: Migration should handle SSH connection timeouts gracefully."""
        from code_indexer.server.services.migration_orchestrator import (
            MigrationOrchestrator,
        )
        from code_indexer.server.services.key_to_remote_tester import TestResult

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create an SSH key without existing mappings
        (ssh_dir / "test_key").write_text("PRIVATE KEY")
        (ssh_dir / "test_key.pub").write_text("ssh-ed25519 CCCC... test")

        server_data_dir = tmp_path / ".code-indexer-server"
        server_data_dir.mkdir(parents=True)
        metadata_dir = server_data_dir / "ssh_keys"

        # Create CIDX config with activated repo
        config_path = server_data_dir / "config.json"
        config_path.write_text(json.dumps({
            "activated_repositories": [
                {"path": "/repo1", "remote_url": "git@timeout-host.example.com:user/repo.git"}
            ]
        }))

        orchestrator = MigrationOrchestrator(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            migration_metadata_path=server_data_dir / "ssh_migration.json",
            cidx_config_path=config_path,
            skip_key_testing=False,
        )

        # Mock the key tester to simulate timeout
        def mock_test_key_against_host(key_path, hostname):
            return TestResult(
                success=False,
                message="Connection timed out",
                timed_out=True,
            )

        orchestrator.key_tester.test_key_against_host = mock_test_key_against_host

        result = orchestrator.run_migration()

        # Migration should complete successfully
        assert result.completed is True
        assert result.keys_discovered == 1
        assert result.keys_imported == 1

        # Failed hosts should include the timeout
        assert len(result.failed_hosts) == 1
        key_name, hostname, reason = result.failed_hosts[0]
        assert key_name == "test_key"
        assert hostname == "timeout-host.example.com"
        assert reason == "timeout"

        # Migration metadata should be saved (prevents re-running)
        assert (server_data_dir / "ssh_migration.json").exists()

    def test_migration_no_remotes_discovered(self, tmp_path):
        """Scenario 15: Migration should handle case with no remote hostnames."""
        from code_indexer.server.services.ssh_startup_migration import (
            run_ssh_migration_on_startup,
        )

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create existing SSH key
        (ssh_dir / "my_key").write_text("PRIVATE KEY")
        (ssh_dir / "my_key.pub").write_text("ssh-ed25519 DDDD... mykey")

        server_data_dir = tmp_path / ".code-indexer-server"
        server_data_dir.mkdir(parents=True)

        # Create CIDX config with NO activated repositories (or local-only paths)
        config_path = server_data_dir / "config.json"
        config_path.write_text(json.dumps({
            "activated_repositories": []
        }))

        result = run_ssh_migration_on_startup(
            server_data_dir=str(server_data_dir),
            ssh_dir=str(ssh_dir),
            skip_key_testing=True,
        )

        # Migration should complete with imported keys but no mappings
        assert result.completed is True
        assert result.keys_discovered == 1
        assert result.keys_imported == 1
        assert result.mappings_imported == 0
        assert result.mappings_tested == 0

        # Key metadata should exist without host mappings
        ssh_keys_dir = server_data_dir / "ssh_keys"
        key_metadata_path = ssh_keys_dir / "my_key.json"
        assert key_metadata_path.exists()

        key_data = json.loads(key_metadata_path.read_text())
        assert key_data["hosts"] == []  # No host mappings


class TestServerStartupIntegration:
    """Tests for server startup integration with SSH key migration."""

    def test_app_contains_ssh_migration_startup_code(self):
        """Verify app.py contains the SSH migration startup code."""
        from pathlib import Path
        
        app_path = Path(__file__).parent.parent.parent / "src" / "code_indexer" / "server" / "app.py"
        app_content = app_path.read_text()
        
        # Verify the SSH migration code is present in app.py
        assert "run_ssh_migration_on_startup" in app_content
        assert "SSH key migration" in app_content
        assert "app.state.ssh_migration_result" in app_content
        
    def test_run_ssh_migration_function_exists_and_works(self, tmp_path):
        """Verify the run_ssh_migration_on_startup function works correctly."""
        from code_indexer.server.services.ssh_startup_migration import (
            run_ssh_migration_on_startup,
        )
        
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        
        # Create an SSH key
        (ssh_dir / "test_key").write_text("PRIVATE KEY")
        (ssh_dir / "test_key.pub").write_text("ssh-ed25519 TEST... test")
        
        server_data_dir = tmp_path / ".code-indexer-server"
        server_data_dir.mkdir(parents=True)
        
        result = run_ssh_migration_on_startup(
            server_data_dir=str(server_data_dir),
            ssh_dir=str(ssh_dir),
            skip_key_testing=True,
        )
        
        # Verify migration ran successfully
        assert result.completed is True
        assert result.keys_discovered == 1
        assert result.keys_imported == 1
