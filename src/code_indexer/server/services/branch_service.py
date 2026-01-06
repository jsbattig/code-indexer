"""
Branch service for retrieving git branch information.

Provides branch listing functionality using real GitPython operations
without mocking, following CLAUDE.md Foundation #1 (Anti-Mock).
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
from pathlib import Path
from typing import List, Optional, Protocol

from git import Repo, InvalidGitRepositoryError, GitCommandError
from code_indexer.services.git_topology_service import GitTopologyService
from code_indexer.server.models.branch_models import (
    BranchInfo,
    CommitInfo,
    IndexStatus,
    RemoteTrackingInfo,
)

logger = logging.getLogger(__name__)


class IndexStatusManager(Protocol):
    """Protocol for index status management to avoid tight coupling."""

    def get_branch_index_status(self, branch_name: str, repo_path: Path) -> IndexStatus:
        """Get index status for a specific branch."""
        ...


class BranchService:
    """Service for retrieving branch information using real git operations."""

    def __init__(
        self,
        git_topology_service: GitTopologyService,
        index_status_manager: Optional[IndexStatusManager] = None,
    ):
        """Initialize branch service.

        Args:
            git_topology_service: Service for git topology operations
            index_status_manager: Optional manager for index status (can be None for testing)
        """
        self.git_topology_service = git_topology_service
        self.index_status_manager = index_status_manager
        self._closed = False

        # Validate that this is a git repository
        if not self.git_topology_service.is_git_available():
            raise ValueError("Not a git repository")

        # Initialize git repo for branch operations
        try:
            self.repo = Repo(self.git_topology_service.codebase_dir)
        except InvalidGitRepositoryError as e:
            raise ValueError(f"Invalid git repository: {e}")

    def list_branches(self, include_remote: bool = False) -> List[BranchInfo]:
        """List all branches in the repository.

        Args:
            include_remote: Whether to include remote tracking information

        Returns:
            List of BranchInfo objects containing branch details

        Raises:
            ValueError: If not a git repository or git operations fail
        """
        try:
            branches = []
            current_branch_name = self.git_topology_service.get_current_branch()

            # Get all local branches
            for branch in self.repo.heads:
                branch_info = self._create_branch_info(
                    branch,
                    is_current=(branch.name == current_branch_name),
                    include_remote=include_remote,
                )
                branches.append(branch_info)

            # Sort branches with current branch first, then alphabetically
            branches.sort(key=lambda b: (not b.is_current, b.name))

            return branches

        except (GitCommandError, InvalidGitRepositoryError):
            logger.error(
                "Git operation failed listing branches",
                exc_info=True,
                extra={"correlation_id": get_correlation_id()},
            )
            raise  # Preserve original exception
        except Exception as e:
            logger.error(
                "Unexpected error listing branches",
                exc_info=True,
                extra={"correlation_id": get_correlation_id()},
            )
            raise RuntimeError("Failed to retrieve branch information") from e

    def get_branch_by_name(self, branch_name: str) -> Optional[BranchInfo]:
        """Get information for a specific branch.

        Args:
            branch_name: Name of the branch to retrieve

        Returns:
            BranchInfo object if branch exists, None otherwise
        """
        try:
            # Check if branch exists
            for branch in self.repo.heads:
                if branch.name == branch_name:
                    current_branch_name = self.git_topology_service.get_current_branch()
                    return self._create_branch_info(
                        branch, is_current=(branch.name == current_branch_name)
                    )
            return None

        except (GitCommandError, InvalidGitRepositoryError):
            logger.error(
                f"Git operation failed getting branch '{branch_name}'",
                exc_info=True,
                extra={"correlation_id": get_correlation_id()},
            )
            return None
        except Exception:
            logger.error(
                f"Unexpected error getting branch '{branch_name}'",
                exc_info=True,
                extra={"correlation_id": get_correlation_id()},
            )
            return None

    def _create_branch_info(
        self, branch, is_current: bool = False, include_remote: bool = False
    ) -> BranchInfo:
        """Create BranchInfo object from git branch.

        Args:
            branch: Git branch object
            is_current: Whether this is the current branch
            include_remote: Whether to include remote tracking info

        Returns:
            BranchInfo object with all branch details
        """
        # Get last commit information
        last_commit = branch.commit
        commit_info = CommitInfo(
            sha=last_commit.hexsha,
            message=last_commit.message.strip(),
            author=last_commit.author.name,
            date=last_commit.committed_datetime.isoformat(),
        )

        # Get index status
        index_status = self._get_index_status(branch.name)

        # Get remote tracking info if requested
        remote_tracking = None
        if include_remote:
            remote_tracking = self._get_remote_tracking_info(branch)

        return BranchInfo(
            name=branch.name,
            is_current=is_current,
            last_commit=commit_info,
            index_status=index_status,
            remote_tracking=remote_tracking,
        )

    def _get_index_status(self, branch_name: str) -> IndexStatus:
        """Get index status for a branch.

        Args:
            branch_name: Name of the branch

        Returns:
            IndexStatus object with current indexing information
        """
        if self.index_status_manager:
            try:
                return self.index_status_manager.get_branch_index_status(
                    branch_name, self.git_topology_service.codebase_dir
                )
            except Exception as e:
                logger.warning(
                    f"Failed to get index status for branch '{branch_name}': {e}",
                    extra={"correlation_id": get_correlation_id()},
                )

        # Default status when index manager not available or fails
        return IndexStatus(
            status="not_indexed",
            files_indexed=0,
            total_files=None,
            last_indexed=None,
            progress_percentage=0.0,
        )

    def _get_remote_tracking_info(self, branch) -> Optional[RemoteTrackingInfo]:
        """Get remote tracking information for a branch.

        Args:
            branch: Git branch object

        Returns:
            RemoteTrackingInfo object if branch has remote tracking, None otherwise
        """
        try:
            # Check if branch has tracking branch
            tracking_branch = branch.tracking_branch()
            if not tracking_branch:
                return None

            # Calculate ahead/behind counts using GitPython native methods
            try:
                # Use GitPython iter_commits to count ahead/behind - no subprocess needed
                commits_ahead = list(
                    self.repo.iter_commits(f"{tracking_branch}..{branch}")
                )
                commits_behind = list(
                    self.repo.iter_commits(f"{branch}..{tracking_branch}")
                )

                ahead = len(commits_ahead)
                behind = len(commits_behind)

            except (GitCommandError, ValueError) as e:
                logger.warning(
                    f"Failed to calculate ahead/behind for branch '{branch.name}': {e}",
                    extra={"correlation_id": get_correlation_id()},
                )
                behind = ahead = 0

            return RemoteTrackingInfo(
                remote=tracking_branch.name, ahead=ahead, behind=behind
            )

        except Exception as e:
            logger.warning(
                f"Failed to get remote tracking info for branch '{branch.name}': {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return None

    def close(self):
        """Clean up repository resources.

        Closes the GitPython repository object to release file handles
        and other system resources.
        """
        if not self._closed and hasattr(self, "repo"):
            try:
                self.repo.close()
            except Exception as e:
                logger.warning(
                    f"Error closing git repository: {e}",
                    extra={"correlation_id": get_correlation_id()},
                )
            finally:
                self._closed = True

    def __del__(self):
        """Ensure cleanup even if close() not called explicitly.

        This is a safety net for resource cleanup, following CLAUDE.md
        Foundation #8 correct pattern for resource management.
        """
        self.close()

    def __enter__(self):
        """Context manager entry.

        Returns:
            Self for use in with statement
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with guaranteed cleanup.

        Args:
            exc_type: Exception type if any
            exc_val: Exception value if any
            exc_tb: Exception traceback if any
        """
        self.close()

    def _validate_branch_name(self, branch_name: str) -> bool:
        """Validate branch name for security.

        Prevents command injection by validating branch names contain
        only safe characters. Follows CLAUDE.md security principles.

        Args:
            branch_name: Branch name to validate

        Returns:
            True if branch name is safe, False otherwise
        """
        if not branch_name or not branch_name.strip():
            return False
        if len(branch_name) > 255:  # Git ref name limit
            return False

        # Reject path traversal attempts
        if ".." in branch_name or branch_name.startswith("/"):
            return False

        # Reject command injection characters
        dangerous_chars = [";", "&", "|", "`", "$", "(", ")", "\\n", "\\x00"]
        if any(char in branch_name for char in dangerous_chars):
            return False

        # Only allow safe characters - alphanumeric, slash, dash, dot, underscore
        # Simple character check without regex to avoid import
        allowed_chars = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_.-"
        )
        return all(char in allowed_chars for char in branch_name)
