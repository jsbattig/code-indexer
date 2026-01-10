"""
Migration Orchestrator Service.

Handles first-startup auto-discovery and import of existing SSH keys.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .key_discovery_service import KeyDiscoveryService, KeyInfo
from .remote_discovery_service import RemoteDiscoveryService
from .key_to_remote_tester import KeyToRemoteTester
from .ssh_key_manager import SSHKeyManager, KeyMetadata


@dataclass
class MigrationResult:
    """Result of SSH key migration operation."""

    completed: bool = False
    skipped: bool = False
    reason: str = ""
    completed_at: Optional[str] = None
    keys_discovered: int = 0
    keys_imported: int = 0
    mappings_imported: int = 0
    mappings_tested: int = 0
    failed_hosts: List[Tuple[str, str, str]] = field(default_factory=list)


class MigrationOrchestrator:
    """
    Orchestrator for SSH key migration on first startup.

    Discovers existing SSH keys, imports metadata, tests keys against
    remote hosts, and creates mappings.
    """

    def __init__(
        self,
        ssh_dir: Optional[Path] = None,
        metadata_dir: Optional[Path] = None,
        migration_metadata_path: Optional[Path] = None,
        cidx_config_path: Optional[Path] = None,
        skip_key_testing: bool = False,
    ):
        """
        Initialize the migration orchestrator.

        Args:
            ssh_dir: Directory for SSH keys. Defaults to ~/.ssh/
            metadata_dir: Directory for key metadata.
            migration_metadata_path: Path to migration status file.
            cidx_config_path: Path to CIDX server config.
            skip_key_testing: If True, skip SSH authentication testing.
        """
        # Get server directory from config service for consistent paths
        from .config_service import get_config_service

        config_service = get_config_service()
        server_dir = config_service.config_manager.server_dir
        db_path = server_dir / "data" / "cidx_server.db"

        if ssh_dir is None:
            ssh_dir = Path.home() / ".ssh"
        if metadata_dir is None:
            metadata_dir = server_dir / "data" / "ssh_keys"
        if migration_metadata_path is None:
            migration_metadata_path = server_dir / "ssh_migration.json"
        if cidx_config_path is None:
            cidx_config_path = server_dir / "config.json"

        self.ssh_dir = ssh_dir
        self.metadata_dir = metadata_dir
        self.migration_metadata_path = migration_metadata_path
        self.cidx_config_path = cidx_config_path
        self.skip_key_testing = skip_key_testing

        # Initialize services
        self.discovery_service = KeyDiscoveryService(ssh_dir=ssh_dir)
        self.remote_discovery_service = RemoteDiscoveryService(
            config_path=cidx_config_path
        )
        self.key_tester = KeyToRemoteTester(timeout_seconds=10)
        self.key_manager = SSHKeyManager(
            ssh_dir=ssh_dir,
            metadata_dir=metadata_dir,
            use_sqlite=True,
            db_path=db_path,
        )

    def should_run_migration(self) -> bool:
        """
        Check if migration should run.

        Returns:
            True if migration has not been completed
        """
        if not self.migration_metadata_path.exists():
            return True

        try:
            data = json.loads(self.migration_metadata_path.read_text())
            return not data.get("completed", False)
        except (json.JSONDecodeError, IOError):
            return True

    def run_migration(self) -> MigrationResult:
        """
        Run the SSH key migration process.

        Returns:
            MigrationResult with details of the migration
        """
        if not self.should_run_migration():
            return MigrationResult(
                skipped=True,
                reason="Already completed",
            )

        # Step 1: Discover existing keys
        discovered_keys = self.discovery_service.discover_existing_keys()

        # Step 2: Parse existing config mappings
        config_path = self.ssh_dir / "config"
        existing_mappings = self.discovery_service.parse_existing_config_mappings(
            config_path
        )

        # Step 3: Discover remote hostnames from activated repos
        remote_hostnames = self.remote_discovery_service.discover_remote_hostnames()

        # Step 4: Import keys with existing mappings
        imported_keys: List[KeyMetadata] = []
        mappings_imported = 0

        for key_info in discovered_keys:
            # Get hosts from existing config
            key_path_str = str(key_info.private_path)
            hosts = existing_mappings.get(key_path_str, [])

            if hosts:
                mappings_imported += len(hosts)

            # Create metadata
            metadata = self._create_key_metadata(key_info, hosts)
            self._save_key_metadata(metadata)
            imported_keys.append(metadata)

        # Step 5: Test unmapped keys against discovered remotes (if not skipped)
        tested_mappings: List[Tuple[str, str]] = []
        failed_hosts: List[Tuple[str, str, str]] = []

        if not self.skip_key_testing:
            for metadata in imported_keys:
                if not metadata.hosts:
                    for hostname in remote_hostnames:
                        result = self.key_tester.test_key_against_host(
                            Path(metadata.private_path), hostname
                        )
                        if result.success:
                            metadata.hosts.append(hostname)
                            self._save_key_metadata(metadata)
                            tested_mappings.append((metadata.name, hostname))
                        elif result.timed_out:
                            failed_hosts.append((metadata.name, hostname, "timeout"))

        # Step 6: Save migration metadata
        migration_result = MigrationResult(
            completed=True,
            completed_at=datetime.now().isoformat(),
            keys_discovered=len(discovered_keys),
            keys_imported=len(imported_keys),
            mappings_imported=mappings_imported,
            mappings_tested=len(tested_mappings),
            failed_hosts=failed_hosts,
        )

        self._save_migration_metadata(migration_result)

        return migration_result

    def _create_key_metadata(
        self,
        key_info: KeyInfo,
        hosts: List[str],
    ) -> KeyMetadata:
        """Create KeyMetadata from discovered KeyInfo."""
        # Try to get fingerprint
        fingerprint = key_info.fingerprint or ""
        key_type = key_info.key_type or "unknown"

        # Read public key if exists
        public_key = None
        if key_info.public_path.exists():
            try:
                public_key = key_info.public_path.read_text().strip()
            except IOError:
                pass

        return KeyMetadata(
            name=key_info.name,
            fingerprint=fingerprint,
            key_type=key_type,
            private_path=str(key_info.private_path),
            public_path=str(key_info.public_path),
            public_key=public_key,
            hosts=hosts,
            imported_at=datetime.now().isoformat(),
            is_imported=True,
        )

    def _save_key_metadata(self, metadata: KeyMetadata) -> None:
        """Save key metadata to JSON file."""
        if not self.metadata_dir.exists():
            self.metadata_dir.mkdir(parents=True, mode=0o700)

        metadata_path = self.metadata_dir / f"{metadata.name}.json"
        data = asdict(metadata)
        metadata_path.write_text(json.dumps(data, indent=2))
        os.chmod(metadata_path, 0o600)

    def _save_migration_metadata(self, result: MigrationResult) -> None:
        """Save migration result to metadata file."""
        if not self.migration_metadata_path.parent.exists():
            self.migration_metadata_path.parent.mkdir(parents=True, mode=0o700)

        data = asdict(result)
        self.migration_metadata_path.write_text(json.dumps(data, indent=2))
