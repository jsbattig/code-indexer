"""
Remote Discovery Service.

Discovers remote hostnames from activated repositories.
"""

import json
import re
from pathlib import Path
from typing import Optional, Set


class RemoteDiscoveryService:
    """
    Service for discovering remote hostnames from activated repositories.

    Extracts hostnames from git remote URLs to identify which hosts
    need SSH key authentication.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the remote discovery service.

        Args:
            config_path: Path to CIDX server config. Defaults to
                         ~/.code-indexer-server/config.json
        """
        if config_path is None:
            config_path = Path.home() / ".code-indexer-server" / "config.json"
        self.config_path = config_path

    def extract_hostname(self, remote_url: str) -> Optional[str]:
        """
        Extract hostname from a git remote URL.

        Supports formats:
        - git@github.com:user/repo.git (SSH shorthand)
        - ssh://git@github.com/user/repo.git (SSH URL)
        - https://github.com/user/repo.git (HTTPS URL)

        Args:
            remote_url: Git remote URL

        Returns:
            Hostname or None if URL format not recognized
        """
        # SSH shorthand format: git@github.com:user/repo.git
        match = re.match(r"^git@([^:]+):", remote_url)
        if match:
            return match.group(1)

        # SSH URL format: ssh://git@github.com/user/repo.git
        # May include port: ssh://git@host:port/path
        match = re.match(r"^ssh://[^@]+@([^/:]+)", remote_url)
        if match:
            return match.group(1)

        # HTTPS format: https://github.com/user/repo.git
        match = re.match(r"^https?://([^/]+)/", remote_url)
        if match:
            return match.group(1)

        return None

    def discover_remote_hostnames(self) -> Set[str]:
        """
        Discover unique hostnames from activated repositories.

        Returns:
            Set of unique hostnames that require SSH authentication
        """
        if not self.config_path.exists():
            return set()

        try:
            content = self.config_path.read_text()
            config = json.loads(content)
        except (json.JSONDecodeError, IOError):
            return set()

        activated_repos = config.get("activated_repositories", [])
        hostnames: Set[str] = set()

        for repo in activated_repos:
            remote_url = repo.get("remote_url", "")
            if not remote_url:
                continue

            hostname = self.extract_hostname(remote_url)
            if hostname:
                hostnames.add(hostname)

        return hostnames
