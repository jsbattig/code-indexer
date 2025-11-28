"""
Git Pull Updater - update strategy for git-based repositories.

Implements UpdateStrategy interface using git pull for updates
and git diff-index for change detection.
"""

import logging
import subprocess
from pathlib import Path

from .update_strategy import UpdateStrategy


logger = logging.getLogger(__name__)


class GitPullUpdater(UpdateStrategy):
    """
    Update strategy for git repositories using git pull.

    Uses git diff-index for change detection and git pull for updates.
    """

    def __init__(self, repo_path: str):
        """
        Initialize git pull updater.

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)

        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

    def has_changes(self) -> bool:
        """
        Check if repository has changes using git diff-index.

        Returns:
            True if changes detected, False if up-to-date

        Raises:
            RuntimeError: If git command fails
        """
        try:
            # Use git diff-index to detect changes
            # Returns non-zero if there are differences, zero if identical
            result = subprocess.run(
                ["git", "diff-index", "--quiet", "HEAD"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Non-zero return code means changes detected
            return result.returncode != 0

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git diff-index timed out for {self.repo_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to check for changes: {e}")

    def update(self) -> None:
        """
        Update repository using git pull.

        Raises:
            RuntimeError: If git pull fails
        """
        try:
            logger.info(f"Executing git pull for {self.repo_path}")

            result = subprocess.run(
                ["git", "pull"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Git pull failed for {self.repo_path}: {result.stderr}"
                )

            logger.info(f"Git pull successful: {result.stdout.strip()}")

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git pull timed out for {self.repo_path}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Git pull operation failed: {e}")

    def get_source_path(self) -> str:
        """
        Get the source repository path.

        Returns:
            Absolute path to git repository
        """
        return str(self.repo_path)
