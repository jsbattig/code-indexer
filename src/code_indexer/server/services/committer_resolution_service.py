"""
Committer Resolution Service (Story #641).

Resolves git committer email by testing SSH keys against remote hostnames.
Implements automatic email discovery with fallback to default email.
"""

import logging
from typing import Optional, Tuple

from .ssh_key_manager import SSHKeyManager
from .key_to_remote_tester import KeyToRemoteTester
from .remote_discovery_service import RemoteDiscoveryService


class CommitterResolutionService:
    """
    Service for resolving git committer email based on SSH key authentication.

    Implements the algorithm:
    1. Extract hostname from golden repo URL
    2. Get all managed SSH keys
    3. Test each key against hostname until one succeeds
    4. Return working key's email, or default email if none work
    """

    def __init__(
        self,
        ssh_key_manager: Optional[SSHKeyManager] = None,
        key_to_remote_tester: Optional[KeyToRemoteTester] = None,
        remote_discovery_service: Optional[RemoteDiscoveryService] = None,
    ):
        """
        Initialize CommitterResolutionService.

        Args:
            ssh_key_manager: SSH key manager instance (creates default if None)
            key_to_remote_tester: Key tester instance (creates default if None)
            remote_discovery_service: Remote discovery instance (creates default if None)
        """
        self.logger = logging.getLogger(__name__)

        # Initialize dependencies with defaults if not provided
        self.ssh_key_manager = ssh_key_manager or SSHKeyManager()
        self.key_to_remote_tester = key_to_remote_tester or KeyToRemoteTester()
        self.remote_discovery_service = remote_discovery_service or RemoteDiscoveryService()

    def resolve_committer_email(
        self,
        golden_repo_url: str,
        default_email: str,
    ) -> Tuple[str, Optional[str]]:
        """
        Resolve committer email by testing SSH keys against remote hostname.

        Implements the algorithm from Story #641:
        1. Extract hostname from golden repo's push remote URL
        2. Get all managed SSH keys with their metadata
        3. Test each key against hostname until one succeeds
        4. Return working key's email, or default if none work

        Args:
            golden_repo_url: Golden repository push URL (e.g., git@github.com:user/repo.git)
            default_email: Fallback email to use if no SSH key works

        Returns:
            Tuple of (email, key_name) where:
            - email: Resolved email (from SSH key or default)
            - key_name: Name of working SSH key, or None if using default
        """
        # Step 1: Extract hostname from golden repo's push remote URL
        hostname = self.remote_discovery_service.extract_hostname(golden_repo_url)
        if hostname is None:
            self.logger.warning(
                f"Cannot extract hostname from URL '{golden_repo_url}', using default email"
            )
            return default_email, None

        self.logger.debug(f"Extracted hostname '{hostname}' from golden repo URL")

        # Step 2: Get all managed SSH keys with their metadata
        key_list_result = self.ssh_key_manager.list_keys()
        managed_keys = key_list_result.managed

        if not managed_keys:
            self.logger.warning("No managed SSH keys found, using default email")
            return default_email, None

        self.logger.debug(f"Found {len(managed_keys)} managed SSH keys to test")

        # Step 3: Test each key against hostname until one succeeds
        for key_metadata in managed_keys:
            self.logger.debug(
                f"Testing SSH key '{key_metadata.name}' against hostname '{hostname}'"
            )

            test_result = self.key_to_remote_tester.test_key_against_host(
                key_path=key_metadata.private_path,
                hostname=hostname,
            )

            if test_result.success:
                # Key authenticated successfully
                if key_metadata.email:
                    self.logger.info(
                        f"SSH key '{key_metadata.name}' authenticated successfully, "
                        f"using email '{key_metadata.email}'"
                    )
                    return key_metadata.email, key_metadata.name
                else:
                    self.logger.warning(
                        f"Working key '{key_metadata.name}' has no email configured, "
                        f"using default email"
                    )
                    return default_email, key_metadata.name

        # Step 4: No key worked, use default
        self.logger.warning(
            f"No SSH key authenticated to {hostname}, using default email '{default_email}'"
        )
        return default_email, None
