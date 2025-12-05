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
        Check if repository has remote changes using git fetch and log.

        Fetches latest refs from remote and checks if there are commits
        on the remote branch that are not in the local branch.

        Returns:
            True if remote changes detected, False if up-to-date

        Raises:
            RuntimeError: If git command fails
        """
        try:
            # First, fetch latest refs from remote
            fetch_result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if fetch_result.returncode != 0:
                # If fetch fails, log warning and return False (can't determine changes)
                logger.warning(
                    f"Git fetch failed for {self.repo_path}: {fetch_result.stderr}. "
                    "Cannot detect remote changes, skipping this refresh cycle."
                )
                return False

            # Check for commits on remote not in local using HEAD..@{upstream}
            log_result = subprocess.run(
                ["git", "log", "HEAD..@{upstream}", "--oneline"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if log_result.returncode != 0:
                raise RuntimeError(
                    f"Git log command failed for {self.repo_path}: {log_result.stderr}"
                )

            # If there's any output, there are remote commits to pull
            has_remote_changes = bool(log_result.stdout.strip())

            if has_remote_changes:
                logger.info(
                    f"Remote changes detected for {self.repo_path}: "
                    f"{len(log_result.stdout.strip().splitlines())} commit(s) to pull"
                )

            return has_remote_changes

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git command timed out for {self.repo_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to check for remote changes: {e}")

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
