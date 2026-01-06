"""
Service for golden repository branch operations.

Provides branch listing functionality for golden repositories with proper
git operations and branch classification, following CLAUDE.md Anti-Mock principles.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from code_indexer.server.models.golden_repo_branch_models import GoldenRepoBranchInfo
from code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GitOperationError,
)

logger = logging.getLogger(__name__)


def classify_branch_type(branch_name: str) -> str:
    """
    Classify branch based on naming patterns for intelligent matching.

    Args:
        branch_name: Name of the branch to classify

    Returns:
        Branch type: 'main', 'feature', 'release', 'hotfix', or 'other'
    """
    if not branch_name or not branch_name.strip():
        return "other"

    branch_lower = branch_name.lower().strip()

    # Primary branches: main, master, develop, development, dev
    primary_patterns = ["main", "master", "develop", "development", "dev"]
    if branch_lower in primary_patterns:
        return "main"

    # Feature branches: feature/, feat/, features/
    if any(
        branch_lower.startswith(pattern)
        for pattern in ["feature/", "feat/", "features/"]
    ):
        return "feature"

    # Release branches: release/, rel/, v*
    if any(branch_lower.startswith(pattern) for pattern in ["release/", "rel/"]):
        return "release"

    # Version branches starting with 'v'
    if branch_lower.startswith("v") and len(branch_lower) > 1:
        # Check if it looks like a version (v1.0.0, v2.1, etc.)
        version_part = branch_lower[1:]  # Remove 'v' prefix
        if any(char.isdigit() for char in version_part):
            return "release"

    # Hotfix branches: hotfix/, fix/, patch/, bugfix/
    hotfix_patterns = ["hotfix/", "fix/", "patch/", "bugfix/"]
    if any(branch_lower.startswith(pattern) for pattern in hotfix_patterns):
        return "hotfix"

    # Everything else
    return "other"


class GoldenRepoBranchService:
    """Service for retrieving branch information from golden repositories."""

    def __init__(self, golden_repo_manager: GoldenRepoManager):
        """
        Initialize the golden repository branch service.

        Args:
            golden_repo_manager: Manager for golden repository operations
        """
        self.golden_repo_manager = golden_repo_manager

    async def get_golden_repo_branches(
        self, repo_alias: str
    ) -> List[GoldenRepoBranchInfo]:
        """
        Get list of branches for a golden repository.

        Args:
            repo_alias: Alias of the golden repository

        Returns:
            List of GoldenRepoBranchInfo objects containing branch details

        Raises:
            GitOperationError: If git operations fail
            ValueError: If repository doesn't exist
        """
        # Get golden repository info
        golden_repo = self.golden_repo_manager.get_golden_repo(repo_alias)
        if not golden_repo:
            raise ValueError(f"Golden repository '{repo_alias}' not found")

        # Use canonical path resolution to handle versioned structure repos
        actual_repo_path = self.golden_repo_manager.get_actual_repo_path(repo_alias)
        repo_path = Path(actual_repo_path)
        if not repo_path.exists():
            raise GitOperationError(f"Repository path does not exist: {repo_path}")

        try:
            # Get all branches using git for-each-ref for efficiency
            cmd = [
                "git",
                "for-each-ref",
                "--format=%(refname:short)|%(objectname)|%(committerdate:iso8601)|%(authorname)|%(subject)",
                "refs/heads/",
            ]

            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,  # 30 second timeout for large repositories
            )

            branches = []
            default_branch = self._get_default_branch(repo_path)

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                try:
                    parts = line.split("|")
                    if len(parts) >= 5:
                        branch_name = parts[0]
                        commit_hash = parts[1]
                        commit_date_str = parts[2]
                        author_name = parts[3]
                        # commit_message = parts[4]  # Not currently used

                        # Parse commit timestamp
                        commit_timestamp = None
                        try:
                            # ISO 8601 format: 2024-01-15 10:30:45 +0000
                            commit_timestamp = datetime.fromisoformat(
                                commit_date_str.replace(" +", "+").replace(" -", "-")
                            )
                            if commit_timestamp.tzinfo is None:
                                commit_timestamp = commit_timestamp.replace(
                                    tzinfo=timezone.utc
                                )
                        except (ValueError, AttributeError) as e:
                            logger.warning(
                                f"Failed to parse commit date '{commit_date_str}': {e}",
                                extra={"correlation_id": get_correlation_id()},
                            )

                        # Classify branch type
                        branch_type = classify_branch_type(branch_name)

                        branch_info = GoldenRepoBranchInfo(
                            name=branch_name,
                            is_default=(branch_name == default_branch),
                            last_commit_hash=commit_hash,
                            last_commit_timestamp=commit_timestamp,
                            last_commit_author=author_name,
                            branch_type=branch_type,
                        )
                        branches.append(branch_info)

                except (IndexError, ValueError) as e:
                    logger.warning(
                        f"Failed to parse git output line '{line}': {e}",
                        extra={"correlation_id": get_correlation_id()},
                    )
                    continue

            # Sort branches: default first, then by name
            branches.sort(key=lambda b: (not b.is_default, b.name))

            return branches

        except subprocess.CalledProcessError as e:
            error_msg = f"Git operation failed: {e.stderr or e.stdout or str(e)}"
            logger.error(error_msg, extra={"correlation_id": get_correlation_id()})
            raise GitOperationError(error_msg)
        except subprocess.TimeoutExpired:
            error_msg = "Git operation timed out - repository may be too large"
            logger.error(error_msg, extra={"correlation_id": get_correlation_id()})
            raise GitOperationError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during git operation: {e}"
            logger.error(
                error_msg, exc_info=True, extra={"correlation_id": get_correlation_id()}
            )
            raise GitOperationError(error_msg)

    def _get_default_branch(self, repo_path: Path) -> Optional[str]:
        """
        Get the default branch for the repository.

        Args:
            repo_path: Path to the git repository

        Returns:
            Name of the default branch, or None if cannot be determined
        """
        try:
            # Try to get the default branch from remote HEAD
            cmd = ["git", "symbolic-ref", "refs/remotes/origin/HEAD"]
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Extract branch name from refs/remotes/origin/main
                default_ref = result.stdout.strip()
                if default_ref.startswith("refs/remotes/origin/"):
                    return default_ref[len("refs/remotes/origin/") :]

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logger.debug(
                "Could not determine default branch from remote HEAD",
                extra={"correlation_id": get_correlation_id()},
            )

        # Fallback: try common default branch names
        try:
            cmd = ["git", "branch", "--list"]
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                branches = [
                    line.strip().lstrip("* ")
                    for line in result.stdout.strip().split("\n")
                ]

                # Check common default branch names in order of preference
                for candidate in ["main", "master", "develop", "development"]:
                    if candidate in branches:
                        return candidate

                # If no common default found, return the first branch
                if branches and branches[0]:
                    return branches[0]

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logger.debug(
                "Could not list branches to determine default",
                extra={"correlation_id": get_correlation_id()},
            )

        return None
