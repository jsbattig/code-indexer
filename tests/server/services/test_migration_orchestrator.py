"""Unit tests for MigrationOrchestrator service."""

import json
from unittest.mock import patch

from code_indexer.server.services.migration_orchestrator import (
    MigrationOrchestrator,
)


class TestMigrationOrchestratorShouldRun:
    """Tests for MigrationOrchestrator.should_run_migration()."""

    def test_should_run_when_no_metadata(self, tmp_path):
        """Should return True when migration metadata doesn't exist."""
        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"

        orchestrator = MigrationOrchestrator(
            ssh_dir=tmp_path / ".ssh",
            metadata_dir=tmp_path / ".code-indexer-server" / "ssh_keys",
            migration_metadata_path=metadata_path,
        )

        assert orchestrator.should_run_migration() is True

    def test_should_not_run_when_completed(self, tmp_path):
        """Should return False when migration is marked as completed."""
        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_path.parent.mkdir(parents=True)
        metadata_path.write_text('{"completed": true}')

        orchestrator = MigrationOrchestrator(
            ssh_dir=tmp_path / ".ssh",
            metadata_dir=tmp_path / ".code-indexer-server" / "ssh_keys",
            migration_metadata_path=metadata_path,
        )

        assert orchestrator.should_run_migration() is False


class TestMigrationOrchestratorRunMigration:
    """Tests for MigrationOrchestrator.run_migration()."""

    def test_run_migration_skipped_when_already_completed(self, tmp_path):
        """Should skip migration if already completed."""
        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_path.parent.mkdir(parents=True)
        metadata_path.write_text('{"completed": true}')

        orchestrator = MigrationOrchestrator(
            ssh_dir=tmp_path / ".ssh",
            metadata_dir=tmp_path / ".code-indexer-server" / "ssh_keys",
            migration_metadata_path=metadata_path,
        )

        result = orchestrator.run_migration()

        assert result.skipped is True
        assert "already completed" in result.reason.lower()

    def test_run_migration_no_keys_found(self, tmp_path):
        """Should complete successfully with zero keys discovered."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        # Create config and known_hosts but no key files
        (ssh_dir / "config").write_text("# Empty config")
        (ssh_dir / "known_hosts").write_text("github.com ssh-rsa AAAA...")

        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        orchestrator = MigrationOrchestrator(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            migration_metadata_path=metadata_path,
        )

        result = orchestrator.run_migration()

        assert result.skipped is False
        assert result.completed is True
        assert result.keys_discovered == 0
        assert result.keys_imported == 0
        # Verify metadata was saved to prevent re-running
        assert metadata_path.exists()

    def test_run_migration_discovers_existing_keys(self, tmp_path):
        """Should discover and import existing SSH keys."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create a key pair
        (ssh_dir / "id_ed25519").write_text("PRIVATE KEY")
        (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA... test@example.com")

        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        orchestrator = MigrationOrchestrator(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            migration_metadata_path=metadata_path,
        )

        result = orchestrator.run_migration()

        assert result.keys_discovered == 1
        assert result.keys_imported == 1
        # Verify key metadata was saved
        assert (metadata_dir / "id_ed25519.json").exists()

    def test_run_migration_imports_existing_config_mappings(self, tmp_path):
        """Should import host mappings from existing SSH config."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create a key pair
        (ssh_dir / "github_key").write_text("PRIVATE KEY")
        (ssh_dir / "github_key.pub").write_text("ssh-ed25519 AAAA... github")

        # Create config with mapping
        config_content = f"""Host github.com
  HostName github.com
  User git
  IdentityFile {ssh_dir}/github_key
"""
        (ssh_dir / "config").write_text(config_content)

        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        orchestrator = MigrationOrchestrator(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            migration_metadata_path=metadata_path,
        )

        result = orchestrator.run_migration()

        assert result.keys_discovered == 1
        assert result.mappings_imported >= 1

        # Verify mapping was imported into metadata
        metadata_file = metadata_dir / "github_key.json"
        metadata = json.loads(metadata_file.read_text())
        assert "github.com" in metadata["hosts"]


class TestMigrationOrchestratorKeyTesting:
    """Tests for MigrationOrchestrator key testing functionality."""

    def test_run_migration_tests_unmapped_keys(self, tmp_path):
        """Should test unmapped keys against discovered remotes."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create a key pair without config mapping
        (ssh_dir / "test_key").write_text("PRIVATE KEY")
        (ssh_dir / "test_key.pub").write_text("ssh-ed25519 AAAA... test")

        # Create CIDX config with activated repo
        cidx_config_path = tmp_path / ".code-indexer-server" / "config.json"
        cidx_config_path.parent.mkdir(parents=True)
        cidx_config_path.write_text(json.dumps({
            "activated_repositories": [
                {"path": "/repo", "remote_url": "git@github.com:user/repo.git"}
            ]
        }))

        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        orchestrator = MigrationOrchestrator(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            migration_metadata_path=metadata_path,
            cidx_config_path=cidx_config_path,
            skip_key_testing=True,  # Skip actual SSH testing in unit tests
        )

        result = orchestrator.run_migration()

        assert result.keys_discovered == 1
        assert result.completed is True

    def test_run_migration_timeout_handling(self, tmp_path):
        """Scenario 13: SSH key testing timeout should be recorded in failed_hosts."""
        from code_indexer.server.services.key_to_remote_tester import TestResult

        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create a key pair without config mapping
        (ssh_dir / "timeout_key").write_text("PRIVATE KEY")
        (ssh_dir / "timeout_key.pub").write_text("ssh-ed25519 AAAA... timeout")

        # Create CIDX config with activated repo
        cidx_config_path = tmp_path / ".code-indexer-server" / "config.json"
        cidx_config_path.parent.mkdir(parents=True)
        cidx_config_path.write_text(json.dumps({
            "activated_repositories": [
                {"path": "/repo", "remote_url": "git@slow-host.example.com:user/repo.git"}
            ]
        }))

        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        orchestrator = MigrationOrchestrator(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            migration_metadata_path=metadata_path,
            cidx_config_path=cidx_config_path,
            skip_key_testing=False,
        )

        # Mock the key tester to return a timeout result
        with patch.object(
            orchestrator.key_tester,
            'test_key_against_host',
            return_value=TestResult(
                success=False,
                message="Connection timed out",
                timed_out=True,
            )
        ):
            result = orchestrator.run_migration()

        assert result.completed is True
        assert result.keys_discovered == 1
        # Should have recorded the timeout in failed_hosts
        assert len(result.failed_hosts) >= 1
        # Check that the failed host tuple contains timeout indication
        failed_entry = result.failed_hosts[0]
        assert failed_entry[0] == "timeout_key"
        assert failed_entry[1] == "slow-host.example.com"
        assert failed_entry[2] == "timeout"

        # Verify migration metadata records the failure
        migration_data = json.loads(metadata_path.read_text())
        assert migration_data["completed"] is True
        assert len(migration_data["failed_hosts"]) >= 1


class TestMigrationOrchestratorNoRemotes:
    """Tests for Scenario 15: No remotes discovered."""

    def test_run_migration_no_remotes_discovered(self, tmp_path):
        """Scenario 15: Keys imported without host mappings when no remotes exist."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create SSH keys
        (ssh_dir / "personal_key").write_text("PRIVATE KEY")
        (ssh_dir / "personal_key.pub").write_text("ssh-ed25519 AAAA... personal")
        (ssh_dir / "work_key").write_text("PRIVATE KEY")
        (ssh_dir / "work_key.pub").write_text("ssh-ed25519 AAAA... work")

        # Create CIDX config with NO activated repos (no remotes)
        cidx_config_path = tmp_path / ".code-indexer-server" / "config.json"
        cidx_config_path.parent.mkdir(parents=True)
        cidx_config_path.write_text(json.dumps({
            "activated_repositories": []
        }))

        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        orchestrator = MigrationOrchestrator(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            migration_metadata_path=metadata_path,
            cidx_config_path=cidx_config_path,
        )

        result = orchestrator.run_migration()

        # Migration completes successfully
        assert result.completed is True
        assert result.skipped is False

        # Keys should be discovered and imported
        assert result.keys_discovered == 2
        assert result.keys_imported == 2

        # No host mappings since no remotes exist
        assert result.mappings_imported == 0
        assert result.mappings_tested == 0

        # Keys should be available for manual host assignment
        personal_metadata = json.loads((metadata_dir / "personal_key.json").read_text())
        work_metadata = json.loads((metadata_dir / "work_key.json").read_text())

        # Keys have empty hosts list (available for manual assignment later)
        assert personal_metadata["hosts"] == []
        assert work_metadata["hosts"] == []
        assert personal_metadata["is_imported"] is True
        assert work_metadata["is_imported"] is True

    def test_run_migration_no_remotes_config_missing(self, tmp_path):
        """Should handle case where CIDX config file doesn't exist."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)

        # Create a key pair
        (ssh_dir / "orphan_key").write_text("PRIVATE KEY")
        (ssh_dir / "orphan_key.pub").write_text("ssh-ed25519 AAAA... orphan")

        # Don't create CIDX config at all
        cidx_config_path = tmp_path / ".code-indexer-server" / "config.json"
        metadata_path = tmp_path / ".code-indexer-server" / "ssh_migration.json"
        metadata_dir = tmp_path / ".code-indexer-server" / "ssh_keys"

        orchestrator = MigrationOrchestrator(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            migration_metadata_path=metadata_path,
            cidx_config_path=cidx_config_path,
        )

        result = orchestrator.run_migration()

        # Migration still completes
        assert result.completed is True
        assert result.keys_discovered == 1
        assert result.keys_imported == 1
        assert result.mappings_tested == 0
