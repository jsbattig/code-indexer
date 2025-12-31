"""
SSH Config Manager Service.

Manages ~/.ssh/config file with CIDX-managed sections that preserve user entries.
Provides atomic write operations and conflict detection.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import shutil
from typing import List, Tuple


class CorruptedConfigError(Exception):
    """Raised when SSH config has CIDX start marker but missing end marker."""

    pass


@dataclass
class ParsedConfig:
    """Parsed SSH config file contents."""

    cidx_section: List[str] = field(default_factory=list)
    user_section: List[str] = field(default_factory=list)
    include_directives: List[Tuple[str, int]] = field(default_factory=list)


@dataclass
class HostEntry:
    """SSH Host entry for CIDX-managed section."""

    host: str
    hostname: str
    key_path: str


@dataclass
class ConflictInfo:
    """Information about a host conflict in SSH config."""

    exists: bool = False
    in_user_section: bool = False


class SSHConfigManager:
    """
    Manager for SSH config file with CIDX-managed sections.

    Maintains isolation between CIDX-managed Host blocks and user-defined entries.
    Preserves user formatting byte-for-byte while managing CIDX section atomically.
    """

    CIDX_START_MARKER = "# BEGIN CIDX-MANAGED SSH KEYS - DO NOT EDIT"
    CIDX_END_MARKER = "# END CIDX-MANAGED SSH KEYS"

    def parse_config(self, config_path: Path) -> ParsedConfig:
        """
        Parse SSH config file into CIDX and user sections.

        Args:
            config_path: Path to SSH config file

        Returns:
            ParsedConfig with cidx_section, user_section, and include_directives
        """
        if not config_path.exists():
            return ParsedConfig()

        content = config_path.read_text()
        lines = content.split("\n")

        cidx_section: List[str] = []
        user_section: List[str] = []
        include_directives: List[Tuple[str, int]] = []
        in_cidx_section = False
        cidx_start_found = False
        cidx_end_found = False

        for position, line in enumerate(lines):
            # Check for Include directive
            stripped = line.strip()
            if stripped.lower().startswith("include "):
                include_directives.append((line, position))
                continue

            # Check for CIDX markers
            if stripped == self.CIDX_START_MARKER:
                cidx_start_found = True
                in_cidx_section = True
                continue

            if stripped == self.CIDX_END_MARKER:
                cidx_end_found = True
                in_cidx_section = False
                continue

            # Add to appropriate section
            if in_cidx_section:
                cidx_section.append(line)
            else:
                user_section.append(line)

        # Check for corrupted config (start marker without end marker)
        if cidx_start_found and not cidx_end_found:
            # Create backup before raising error
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = (
                config_path.parent / f"{config_path.name}.cidx-backup-{timestamp}"
            )
            shutil.copy2(config_path, backup_path)
            raise CorruptedConfigError(
                f"Missing end marker in CIDX section. Backup created at {backup_path}"
            )

        return ParsedConfig(
            cidx_section=cidx_section,
            user_section=user_section,
            include_directives=include_directives,
        )

    def write_config(
        self,
        config_path: Path,
        parsed_config: ParsedConfig,
        new_cidx_entries: List[HostEntry],
    ) -> None:
        """
        Write SSH config file with CIDX-managed section.

        Args:
            config_path: Path to SSH config file
            parsed_config: Previously parsed config to preserve user section
            new_cidx_entries: List of HostEntry to write in CIDX section
        """
        import os

        content = ""

        # Add Include directives first (must be at top per OpenSSH spec)
        for directive, _ in parsed_config.include_directives:
            content += directive + "\n"

        if parsed_config.include_directives:
            content += "\n"

        # Add CIDX-managed section
        content += self.CIDX_START_MARKER + "\n"
        for entry in new_cidx_entries:
            content += self._format_host_block(entry)
        content += self.CIDX_END_MARKER + "\n"
        content += "\n"

        # Preserve user section (excluding Include directives already written)
        user_lines = parsed_config.user_section
        content += "\n".join(user_lines)

        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file, then rename
        temp_path = config_path.parent / f"{config_path.name}.tmp"
        temp_path.write_text(content)
        os.chmod(temp_path, 0o600)
        temp_path.rename(config_path)

    def _format_host_block(self, entry: HostEntry) -> str:
        """
        Format a single Host block for SSH config.

        Args:
            entry: HostEntry with host, hostname, and key_path

        Returns:
            Formatted Host block string
        """
        block = f"Host {entry.host}\n"
        block += f"  HostName {entry.hostname}\n"
        block += "  User git\n"
        block += f"  IdentityFile {entry.key_path}\n"
        block += "  IdentitiesOnly yes\n"
        block += "\n"
        return block

    def check_host_conflict(self, config_path: Path, hostname: str) -> ConflictInfo:
        """
        Check if a hostname exists in the user section of SSH config.

        Args:
            config_path: Path to SSH config file
            hostname: Hostname to check for conflicts

        Returns:
            ConflictInfo with exists and in_user_section flags
        """
        parsed = self.parse_config(config_path)

        for line in parsed.user_section:
            stripped = line.strip()
            if stripped.lower().startswith("host "):
                # Extract host pattern from "Host hostname" line
                host_part = stripped[5:].strip()
                if hostname in host_part.split():
                    return ConflictInfo(exists=True, in_user_section=True)

        return ConflictInfo(exists=False, in_user_section=False)
