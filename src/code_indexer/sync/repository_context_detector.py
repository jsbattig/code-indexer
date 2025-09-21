"""Repository Context Detection for Enhanced Sync Integration.

Detects when the current directory is within an activated repository
and provides repository context information for sync operations.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


class RepositoryContextError(Exception):
    """Exception raised when repository context detection fails."""

    pass


@dataclass
class RepositoryContext:
    """Repository context information for sync operations."""

    user_alias: str
    golden_repo_alias: str
    repository_path: Path
    current_branch: str
    sync_status: str
    last_sync_time: Optional[str] = None
    has_uncommitted_changes: bool = False
    has_conflicts: bool = False


class RepositoryContextDetector:
    """Detects repository context from current working directory."""

    def detect_repository_context(self, cwd: Path) -> Optional[RepositoryContext]:
        """Detect if current directory is in an activated repository.

        Args:
            cwd: Current working directory to check

        Returns:
            RepositoryContext if in activated repository, None otherwise

        Raises:
            RepositoryContextError: If context detection fails
        """
        # Find repository root by walking up directory tree
        repo_root = self.find_repository_root(cwd)

        if not repo_root:
            return None

        # Check if this is an activated repository path
        if not self.is_activated_repository_path(repo_root):
            return None

        # Load repository metadata
        try:
            metadata = self.load_repository_metadata(repo_root)

            # Get current branch and sync status
            current_branch = self.get_current_branch(repo_root)
            sync_status = self.get_repository_sync_status(repo_root)

            # Check for uncommitted changes and conflicts
            has_uncommitted = self._has_uncommitted_changes(repo_root)
            has_conflicts = self._has_merge_conflicts(repo_root)

            return RepositoryContext(
                user_alias=metadata["user_alias"],
                golden_repo_alias=metadata["golden_repo_alias"],
                repository_path=repo_root,
                current_branch=current_branch,
                sync_status=sync_status,
                last_sync_time=metadata.get("last_sync_time"),
                has_uncommitted_changes=has_uncommitted,
                has_conflicts=has_conflicts,
            )

        except Exception as e:
            if isinstance(e, RepositoryContextError):
                raise
            raise RepositoryContextError(f"Failed to detect repository context: {e}")

    def find_repository_root(self, path: Path) -> Optional[Path]:
        """Find repository root directory walking up from path.

        Args:
            path: Starting path to search from

        Returns:
            Path to repository root if found, None otherwise
        """
        current_path = path.resolve()

        while current_path != current_path.parent:
            metadata_file = current_path / ".repository-metadata.json"
            if metadata_file.exists():
                return current_path
            current_path = current_path.parent

        return None

    def is_activated_repository_path(self, path: Path) -> bool:
        """Check if path is in activated repository directory structure.

        Args:
            path: Path to check

        Returns:
            True if path is in activated repository structure
        """
        path_str = str(path.resolve())
        return "activated-repos" in path_str

    def load_repository_metadata(self, repo_path: Path) -> Dict[str, Any]:
        """Load repository metadata from metadata file.

        Args:
            repo_path: Path to repository root

        Returns:
            Repository metadata dictionary

        Raises:
            RepositoryContextError: If metadata cannot be loaded
        """
        metadata_file = repo_path / ".repository-metadata.json"

        if not metadata_file.exists():
            raise RepositoryContextError(
                f"Repository metadata not found at {metadata_file}"
            )

        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)

            # Validate required fields
            required_fields = ["user_alias", "golden_repo_alias"]
            for field in required_fields:
                if field not in metadata:
                    raise RepositoryContextError(
                        f"Repository metadata missing required field: {field}"
                    )

            result: Dict[str, Any] = metadata
            return result

        except json.JSONDecodeError as e:
            raise RepositoryContextError(f"Invalid repository metadata JSON: {e}")
        except Exception as e:
            raise RepositoryContextError(f"Failed to load repository metadata: {e}")

    def get_current_branch(self, repo_path: Path) -> str:
        """Get current git branch for repository.

        Args:
            repo_path: Path to repository root

        Returns:
            Current branch name or "unknown" if detection fails
        """
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return "unknown"

        except Exception:
            return "unknown"

    def get_repository_sync_status(self, repo_path: Path) -> str:
        """Get repository synchronization status.

        Args:
            repo_path: Path to repository root

        Returns:
            Sync status: "synced", "needs_sync", or "conflict"
        """
        try:
            # Check git status for uncommitted changes and conflicts
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return "needs_sync"

            status_output = result.stdout.strip()

            if not status_output:
                return "synced"

            # Check for merge conflicts (UU status)
            lines = status_output.split("\n")
            for line in lines:
                if line.startswith("UU "):
                    return "conflict"

            # Has changes but no conflicts
            return "needs_sync"

        except Exception:
            return "needs_sync"

    def _has_uncommitted_changes(self, repo_path: Path) -> bool:
        """Check if repository has uncommitted changes.

        Args:
            repo_path: Path to repository root

        Returns:
            True if repository has uncommitted changes
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            return result.returncode == 0 and bool(result.stdout.strip())

        except Exception:
            return False

    def _has_merge_conflicts(self, repo_path: Path) -> bool:
        """Check if repository has merge conflicts.

        Args:
            repo_path: Path to repository root

        Returns:
            True if repository has merge conflicts
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return False

            # Check for conflict markers (UU status)
            status_output = result.stdout.strip()
            return any(line.startswith("UU ") for line in status_output.split("\n"))

        except Exception:
            return False
