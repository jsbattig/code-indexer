"""
Key Discovery Service.

Discovers existing SSH keys and parses config file mappings.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Files to ignore when discovering keys
IGNORED_FILES = {"config", "known_hosts", "authorized_keys", "environment"}


@dataclass
class KeyInfo:
    """Information about a discovered SSH key."""

    name: str
    private_path: Path
    public_path: Path
    fingerprint: Optional[str] = None
    key_type: Optional[str] = None
    is_cidx_managed: bool = False


class KeyDiscoveryService:
    """
    Service for discovering existing SSH keys and config mappings.

    Scans ~/.ssh/ directory for key pairs and parses SSH config for
    existing key-to-host mappings.
    """

    def __init__(self, ssh_dir: Optional[Path] = None):
        """
        Initialize the key discovery service.

        Args:
            ssh_dir: SSH directory to scan. Defaults to ~/.ssh/
        """
        if ssh_dir is None:
            ssh_dir = Path.home() / ".ssh"
        self.ssh_dir = ssh_dir

    def _extract_key_info(
        self, public_key_path: Path
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract fingerprint and key type from SSH public key using ssh-keygen.

        Args:
            public_key_path: Path to the public key file

        Returns:
            Tuple of (fingerprint, key_type) or (None, None) if extraction fails.
            fingerprint: String like "SHA256:xxxx..."
            key_type: Lowercase string like "ed25519", "rsa", "ecdsa"
        """
        try:
            result = subprocess.run(
                ["ssh-keygen", "-lf", str(public_key_path)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                # Output format: "256 SHA256:xxxx... comment (ED25519)"
                # parts[0] = "256" (bits)
                # parts[1] = "SHA256:xxx" (fingerprint)
                # parts[-1] = "(ED25519)" (key type in parens)
                # parts[2:-1] = comment (may be empty or multi-word)
                parts = result.stdout.strip().split()
                fingerprint = parts[1] if len(parts) >= 2 else None

                # Key type is in parentheses at the end
                key_type = None
                if parts and parts[-1].startswith("(") and parts[-1].endswith(")"):
                    key_type = parts[-1][1:-1].lower()  # Remove parens, lowercase

                return fingerprint, key_type
            return None, None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return None, None

    def _compute_fingerprint(self, public_key_path: Path) -> Optional[str]:
        """
        Compute fingerprint of an SSH public key using ssh-keygen.

        DEPRECATED: Use _extract_key_info instead which returns both fingerprint
        and key_type. This method is kept for backward compatibility with
        existing tests.

        Args:
            public_key_path: Path to the public key file

        Returns:
            Fingerprint string (e.g., "SHA256:xxxx...") or None if computation fails
        """
        fingerprint, _ = self._extract_key_info(public_key_path)
        return fingerprint

    def discover_existing_keys(self) -> List[KeyInfo]:
        """
        Discover existing SSH key pairs in the SSH directory.

        Returns:
            List of KeyInfo for discovered key pairs
        """
        if not self.ssh_dir.exists():
            return []

        discovered_keys: List[KeyInfo] = []

        # Find all potential private key files
        for file_path in self.ssh_dir.iterdir():
            # Skip directories
            if file_path.is_dir():
                continue

            # Skip .pub files (we'll find them via private key)
            if file_path.name.endswith(".pub"):
                continue

            # Skip known non-key files
            if file_path.name in IGNORED_FILES:
                continue

            # Check if corresponding .pub file exists
            pub_path = file_path.parent / f"{file_path.name}.pub"
            if pub_path.exists():
                fingerprint, key_type = self._extract_key_info(pub_path)
                discovered_keys.append(
                    KeyInfo(
                        name=file_path.name,
                        private_path=file_path,
                        public_path=pub_path,
                        fingerprint=fingerprint,
                        key_type=key_type,
                        is_cidx_managed=False,
                    )
                )

        return discovered_keys

    def parse_existing_config_mappings(self, config_path: Path) -> Dict[str, List[str]]:
        """
        Parse SSH config file to extract key-to-host mappings.

        Args:
            config_path: Path to SSH config file

        Returns:
            Dict mapping key paths to list of hostnames
        """
        if not config_path.exists():
            return {}

        mappings: Dict[str, List[str]] = {}
        current_host: Optional[str] = None
        current_identity: Optional[str] = None

        content = config_path.read_text()
        for line in content.split("\n"):
            stripped = line.strip()

            # Check for Host directive
            if stripped.lower().startswith("host "):
                # Save previous entry if exists
                if current_host and current_identity:
                    if current_identity not in mappings:
                        mappings[current_identity] = []
                    mappings[current_identity].append(current_host)

                current_host = stripped[5:].strip()
                current_identity = None

            # Check for IdentityFile directive
            elif stripped.lower().startswith("identityfile "):
                identity_path = stripped[13:].strip()
                # Expand ~ to home directory
                if identity_path.startswith("~"):
                    identity_path = str(Path.home()) + identity_path[1:]
                current_identity = identity_path

        # Handle last entry
        if current_host and current_identity:
            if current_identity not in mappings:
                mappings[current_identity] = []
            mappings[current_identity].append(current_host)

        return mappings
