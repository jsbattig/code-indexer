"""
Global Registry for managing global repo metadata.

Provides persistent storage of global repo information with atomic writes
to prevent corruption. Registry data persists across system restarts.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union


logger = logging.getLogger(__name__)


# Reserved names for well-known endpoints
RESERVED_GLOBAL_NAMES = {
    "cidx-meta-global": "meta-directory for repository discovery",
    "cidx-meta": "alias for cidx-meta-global",
}


class ReservedNameError(ValueError):
    """Raised when attempting to register a repo with a reserved name."""

    pass


class GlobalRegistry:
    """
    Manages the global repository registry.

    The registry tracks all globally-activated repositories with their metadata,
    stored in a JSON file with atomic writes for corruption prevention.
    """

    def __init__(self, golden_repos_dir: str):
        """
        Initialize the global registry.

        Args:
            golden_repos_dir: Path to golden repos directory
        """
        self.golden_repos_dir = Path(golden_repos_dir)
        self.aliases_dir = self.golden_repos_dir / "aliases"
        self.registry_file = self.golden_repos_dir / "global_registry.json"

        # Ensure directory structure exists
        self.golden_repos_dir.mkdir(parents=True, exist_ok=True)
        self.aliases_dir.mkdir(exist_ok=True)

        # Load or initialize registry
        self._registry_data: Dict[str, Dict[str, Any]] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load registry from disk or create empty if doesn't exist."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r") as f:
                    self._registry_data = json.load(f)
                logger.info(
                    f"Loaded global registry with {len(self._registry_data)} repos"
                )
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load global registry, starting fresh: {e}")
                self._registry_data = {}
                self._save_registry()
        else:
            # Create empty registry
            self._save_registry()

    def _save_registry(self) -> None:
        """
        Save registry to disk with atomic write.

        Uses atomic write pattern to prevent corruption:
        1. Write to temporary file
        2. Sync to disk
        3. Atomic rename over existing file
        """
        # Write to temporary file first
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self.golden_repos_dir), prefix=".global_registry_", suffix=".tmp"
        )

        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(self._registry_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename
            os.replace(tmp_path, str(self.registry_file))
            logger.debug("Global registry saved atomically")

        except Exception as e:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise RuntimeError(f"Failed to save global registry: {e}")

    def register_global_repo(
        self,
        repo_name: str,
        alias_name: str,
        repo_url: Optional[str],
        index_path: str,
        allow_reserved: bool = False,
        enable_temporal: bool = False,
        temporal_options: Optional[Dict[str, Union[int, str]]] = None,
    ) -> None:
        """
        Register a global repository.

        Args:
            repo_name: Repository name (e.g., "my-repo")
            alias_name: Global alias name (e.g., "my-repo-global")
            repo_url: Git repository URL (None for meta-directory)
            index_path: Path to the indexed repository
            allow_reserved: If True, allow reserved names (internal use only)
            enable_temporal: Whether to enable temporal indexing (git history search)
            temporal_options: Temporal indexing options (max_commits, since_date, diff_context)

        Raises:
            ReservedNameError: If alias_name is a reserved name and allow_reserved=False
            ValueError: If alias_name doesn't end with '-global' suffix
            RuntimeError: If save fails
        """
        # Validate alias_name is not reserved (unless explicitly allowed)
        if not allow_reserved and alias_name in RESERVED_GLOBAL_NAMES:
            purpose = RESERVED_GLOBAL_NAMES[alias_name]
            raise ReservedNameError(
                f"Cannot register repo with name '{alias_name}': "
                f"This name is reserved for {purpose}. "
                f"Choose a different alias name for your repository."
            )

        # Enforce -global suffix convention (Epic #520 requirement)
        # Case-insensitive check to allow UPPERCASE-GLOBAL, lowercase-global, etc.
        if not alias_name.lower().endswith("-global"):
            raise ValueError(
                f"Global repo alias must end with '-global' suffix (case-insensitive). "
                f"Got: '{alias_name}', expected: '{repo_name}-global'"
            )

        now = datetime.now(timezone.utc).isoformat()

        self._registry_data[alias_name] = {
            "repo_name": repo_name,
            "alias_name": alias_name,
            "repo_url": repo_url,
            "index_path": index_path,
            "created_at": now,
            "last_refresh": now,
            # Temporal indexing settings (Story #527)
            "enable_temporal": enable_temporal,
            "temporal_options": temporal_options,
        }

        self._save_registry()
        logger.info(f"Registered global repo: {alias_name}")

    def unregister_global_repo(self, alias_name: str) -> None:
        """
        Unregister a global repository.

        Args:
            alias_name: Global alias name to unregister

        Raises:
            RuntimeError: If save fails
        """
        if alias_name in self._registry_data:
            del self._registry_data[alias_name]
            self._save_registry()
            logger.info(f"Unregistered global repo: {alias_name}")

    def get_global_repo(self, alias_name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a global repository.

        Args:
            alias_name: Global alias name

        Returns:
            Repository metadata dict or None if not found
        """
        return self._registry_data.get(alias_name)

    def list_global_repos(self) -> List[Dict[str, Any]]:
        """
        List all global repositories.

        Returns:
            List of repository metadata dicts
        """
        return list(self._registry_data.values())

    def update_refresh_timestamp(self, alias_name: str) -> None:
        """
        Update the last refresh timestamp for a global repo.

        Args:
            alias_name: Global alias name

        Raises:
            RuntimeError: If save fails
        """
        if alias_name in self._registry_data:
            self._registry_data[alias_name]["last_refresh"] = datetime.now(
                timezone.utc
            ).isoformat()
            self._save_registry()
