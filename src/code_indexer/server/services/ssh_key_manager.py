"""
SSH Key Manager Service (Core Orchestrator).

Provides unified interface for SSH key management, coordinating
key generation, metadata storage, and SSH config updates.

Supports both SQLite backend (Story #702) and JSON file storage (backward compatible).
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional
import filelock

from .ssh_key_generator import SSHKeyGenerator
from .ssh_config_manager import SSHConfigManager, HostEntry
from .key_discovery_service import KeyDiscoveryService, KeyInfo


class KeyNotFoundError(Exception):
    """Raised when requested key does not exist."""

    pass


class HostConflictError(Exception):
    """Raised when host already exists in user section of SSH config."""

    pass


class PublicKeyNotFoundError(Exception):
    """Raised when public key file is missing."""

    pass


@dataclass
class KeyMetadata:
    """Metadata for a managed SSH key."""

    name: str
    fingerprint: str
    key_type: str
    private_path: str
    public_path: str
    public_key: Optional[str] = None
    email: Optional[str] = None
    description: Optional[str] = None
    hosts: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    imported_at: Optional[str] = None
    is_imported: bool = False


@dataclass
class KeyListResult:
    """Result of listing SSH keys."""

    managed: List[KeyMetadata] = field(default_factory=list)
    unmanaged: List[KeyInfo] = field(default_factory=list)


class SSHKeyManager:
    """
    Core orchestrator for SSH key management.

    Coordinates key generation, metadata storage, SSH config updates,
    and key discovery operations.

    Supports both SQLite backend (Story #702) and JSON file storage (backward compatible).
    """

    def __init__(
        self,
        ssh_dir: Optional[Path] = None,
        metadata_dir: Optional[Path] = None,
        config_path: Optional[Path] = None,
        use_sqlite: bool = False,
        db_path: Optional[Path] = None,
    ):
        """
        Initialize the SSH key manager.

        Args:
            ssh_dir: Directory for SSH keys. Defaults to ~/.ssh/
            metadata_dir: Directory for key metadata. Defaults to
                          ~/.code-indexer-server/ssh_keys/
            config_path: Path to SSH config file. Defaults to ~/.ssh/config
            use_sqlite: If True, use SQLite backend instead of JSON files (Story #702)
            db_path: Path to SQLite database file (required when use_sqlite=True)
        """
        self._use_sqlite = use_sqlite
        self._sqlite_backend: Optional[Any] = None

        if ssh_dir is None:
            ssh_dir = Path.home() / ".ssh"
        if metadata_dir is None:
            metadata_dir = Path.home() / ".code-indexer-server" / "ssh_keys"
        if config_path is None:
            config_path = ssh_dir / "config"

        self.ssh_dir = ssh_dir
        self.metadata_dir = metadata_dir
        self.config_path = config_path

        # Initialize component services
        self.key_generator = SSHKeyGenerator(ssh_dir=ssh_dir)
        self.config_manager = SSHConfigManager()
        self.discovery_service = KeyDiscoveryService(ssh_dir=ssh_dir)

        # Lock file for concurrent operations
        self.lock_path = metadata_dir.parent / "ssh_keys.lock"

        if use_sqlite:
            if db_path is None:
                raise ValueError("db_path is required when use_sqlite=True")
            from code_indexer.server.storage.sqlite_backends import (
                SSHKeysSqliteBackend,
            )

            self._sqlite_backend = SSHKeysSqliteBackend(str(db_path))

    def _get_lock(self) -> filelock.FileLock:
        """Get file lock for concurrent operation protection."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        return filelock.FileLock(str(self.lock_path))

    def create_key(
        self,
        name: str,
        key_type: str = "ed25519",
        email: Optional[str] = None,
        description: Optional[str] = None,
    ) -> KeyMetadata:
        """
        Create a new SSH key pair with metadata.

        Args:
            name: Name for the key (used as filename)
            key_type: Type of key (ed25519, rsa)
            email: Comment/email to include in the key
            description: Human-readable description

        Returns:
            KeyMetadata for the created key
        """
        with self._get_lock():
            # Generate the key
            generated = self.key_generator.generate_key(
                key_name=name,
                key_type=key_type,
                email=email,
            )

            created_at = datetime.now().isoformat()

            # Create metadata
            metadata = KeyMetadata(
                name=name,
                fingerprint=generated.fingerprint,
                key_type=key_type,
                private_path=str(generated.private_path),
                public_path=str(generated.public_path),
                public_key=generated.public_key,
                email=email,
                description=description,
                hosts=[],
                created_at=created_at,
                is_imported=False,
            )

            # Save metadata - SQLite or JSON
            if self._use_sqlite and self._sqlite_backend is not None:
                self._sqlite_backend.create_key(
                    name=name,
                    fingerprint=generated.fingerprint,
                    key_type=key_type,
                    private_path=str(generated.private_path),
                    public_path=str(generated.public_path),
                    public_key=generated.public_key,
                    email=email,
                    description=description,
                    is_imported=False,
                )
            else:
                self._save_metadata(metadata)

            return metadata

    def assign_key_to_host(
        self,
        key_name: str,
        hostname: str,
        force: bool = False,
    ) -> KeyMetadata:
        """
        Assign a key to a hostname in SSH config.

        Args:
            key_name: Name of the key to assign
            hostname: Hostname to assign the key to
            force: If True, override user section conflicts

        Returns:
            Updated KeyMetadata
        """
        with self._get_lock():
            if self._use_sqlite and self._sqlite_backend is not None:
                # SQLite backend (Story #702)
                key_data = self._sqlite_backend.get_key(key_name)
                if key_data is None:
                    raise KeyNotFoundError(f"Key not found: {key_name}")

                # Check for conflicts in user section
                if not force:
                    conflict = self.config_manager.check_host_conflict(
                        self.config_path, hostname
                    )
                    if conflict.exists and conflict.in_user_section:
                        raise HostConflictError(
                            f"Host {hostname} exists in user section. "
                            "Use force=True or remove manually."
                        )

                # Add hostname if not already present
                if hostname not in key_data["hosts"]:
                    self._sqlite_backend.assign_host(key_name, hostname)

                # Update SSH config
                self._update_ssh_config()

                # Return updated metadata
                updated_data = self._sqlite_backend.get_key(key_name)
                if updated_data is None:
                    raise KeyNotFoundError(
                        f"Key '{key_name}' unexpectedly missing after assignment"
                    )
                return KeyMetadata(**updated_data)
            else:
                # JSON file storage (backward compatible)
                metadata = self._load_metadata(key_name)
                if metadata is None:
                    raise KeyNotFoundError(f"Key not found: {key_name}")

                # Check for conflicts in user section
                if not force:
                    conflict = self.config_manager.check_host_conflict(
                        self.config_path, hostname
                    )
                    if conflict.exists and conflict.in_user_section:
                        raise HostConflictError(
                            f"Host {hostname} exists in user section. "
                            "Use force=True or remove manually."
                        )

                # Add hostname to metadata if not already present
                if hostname not in metadata.hosts:
                    metadata.hosts.append(hostname)
                    self._save_metadata(metadata)

                # Update SSH config
                self._update_ssh_config()

                return metadata

    def delete_key(self, key_name: str) -> bool:
        """
        Delete an SSH key, its config entries, and metadata.

        Args:
            key_name: Name of the key to delete

        Returns:
            True (always succeeds, idempotent operation)
        """
        with self._get_lock():
            if self._use_sqlite and self._sqlite_backend is not None:
                # SQLite backend (Story #702)
                key_data = self._sqlite_backend.get_key(key_name)

                # Remove key files if they exist
                if key_data:
                    private_path = Path(key_data["private_path"])
                    public_path = Path(key_data["public_path"])
                    if private_path.exists():
                        private_path.unlink()
                    if public_path.exists():
                        public_path.unlink()
                else:
                    # Try standard location even without metadata
                    default_private = self.ssh_dir / key_name
                    default_public = self.ssh_dir / f"{key_name}.pub"
                    if default_private.exists():
                        default_private.unlink()
                    if default_public.exists():
                        default_public.unlink()

                # Remove from SQLite (cascade deletes hosts)
                self._sqlite_backend.delete_key(key_name)
            else:
                # JSON file storage (backward compatible)
                metadata = self._load_metadata(key_name)

                # Remove key files if they exist
                if metadata:
                    private_path = Path(metadata.private_path)
                    public_path = Path(metadata.public_path)
                    if private_path.exists():
                        private_path.unlink()
                    if public_path.exists():
                        public_path.unlink()
                else:
                    # Try standard location even without metadata
                    default_private = self.ssh_dir / key_name
                    default_public = self.ssh_dir / f"{key_name}.pub"
                    if default_private.exists():
                        default_private.unlink()
                    if default_public.exists():
                        default_public.unlink()

                # Remove metadata file
                metadata_path = self.metadata_dir / f"{key_name}.json"
                if metadata_path.exists():
                    metadata_path.unlink()

            # Update SSH config to remove entries
            self._update_ssh_config()

            return True

    def list_keys(self) -> KeyListResult:
        """
        List all managed and unmanaged SSH keys.

        Returns:
            KeyListResult with managed and unmanaged key lists
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            keys_data = self._sqlite_backend.list_keys()
            managed_keys = [KeyMetadata(**key_data) for key_data in keys_data]
        else:
            # JSON file storage (backward compatible)
            managed_keys = []
            if self.metadata_dir.exists():
                for metadata_file in self.metadata_dir.glob("*.json"):
                    try:
                        data = json.loads(metadata_file.read_text())
                        managed_keys.append(KeyMetadata(**data))
                    except (json.JSONDecodeError, TypeError):
                        continue

        # Discover all keys on filesystem
        all_discovered = self.discovery_service.discover_existing_keys()
        managed_paths = {k.private_path for k in managed_keys}

        # Find unmanaged keys
        unmanaged_keys: List[KeyInfo] = []
        for key_info in all_discovered:
            if str(key_info.private_path) not in managed_paths:
                unmanaged_keys.append(key_info)

        return KeyListResult(managed=managed_keys, unmanaged=unmanaged_keys)

    def get_public_key(self, key_name: str) -> str:
        """
        Get the public key content for copy/paste.

        Args:
            key_name: Name of the key

        Returns:
            Public key string
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            key_data = self._sqlite_backend.get_key(key_name)
            if key_data is None:
                raise KeyNotFoundError(f"Key not found: {key_name}")

            public_path = Path(key_data["public_path"])
            if public_path.exists():
                return public_path.read_text().strip()

            raise PublicKeyNotFoundError(
                f"Public key file missing: {key_data['public_path']}"
            )
        else:
            # JSON file storage (backward compatible)
            metadata = self._load_metadata(key_name)
            if metadata is None:
                raise KeyNotFoundError(f"Key not found: {key_name}")

            public_path = Path(metadata.public_path)
            if public_path.exists():
                return public_path.read_text().strip()

            raise PublicKeyNotFoundError(
                f"Public key file missing: {metadata.public_path}"
            )

    def _update_ssh_config(self) -> None:
        """Update SSH config with all managed key-host mappings."""
        all_keys = self.list_keys()

        entries: List[HostEntry] = []
        for metadata in all_keys.managed:
            for hostname in metadata.hosts:
                entries.append(
                    HostEntry(
                        host=hostname,
                        hostname=hostname,
                        key_path=metadata.private_path,
                    )
                )

        # Parse existing config to preserve user section
        parsed = self.config_manager.parse_config(self.config_path)

        # Write updated config
        self.config_manager.write_config(self.config_path, parsed, entries)

    def _save_metadata(self, metadata: KeyMetadata) -> None:
        """Save key metadata to JSON file."""
        if not self.metadata_dir.exists():
            self.metadata_dir.mkdir(parents=True, mode=0o700)

        metadata_path = self.metadata_dir / f"{metadata.name}.json"
        data = asdict(metadata)
        metadata_path.write_text(json.dumps(data, indent=2))
        os.chmod(metadata_path, 0o600)

    def _load_metadata(self, key_name: str) -> Optional[KeyMetadata]:
        """Load key metadata from JSON file."""
        metadata_path = self.metadata_dir / f"{key_name}.json"
        if not metadata_path.exists():
            return None

        try:
            data = json.loads(metadata_path.read_text())
            return KeyMetadata(**data)
        except (json.JSONDecodeError, TypeError):
            return None
