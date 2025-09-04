"""
Generic query service that filters results based on current branch context.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from code_indexer.config import Config
from code_indexer.services.file_identifier import FileIdentifier
from code_indexer.utils.git_runner import run_git_command

logger = logging.getLogger(__name__)


class GenericQueryService:
    """Service for performing branch-aware queries on indexed content."""

    def __init__(self, project_dir: Path, config: Optional[Config] = None):
        """Initialize the query service.

        Args:
            project_dir: The project directory path
            config: Optional configuration object
        """
        self.project_dir = project_dir
        self.config = config
        self.file_identifier = FileIdentifier(project_dir, config)

    def filter_results_by_branch(
        self, search_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter search results to only include files from the current branch.

        Args:
            search_results: List of search results from vector database

        Returns:
            Filtered list containing only current branch results
        """
        if not self.file_identifier.git_available:
            # No git, return all results
            return search_results

        current_branch_context = self._get_current_branch_context()
        filtered_results = []

        for result in search_results:
            if self._is_result_current_branch(result, current_branch_context):
                filtered_results.append(result)
        logger.info(
            f"Filtered {len(search_results)} to {len(filtered_results)} results for current branch"
        )
        return filtered_results

    def _get_current_branch_context(self) -> Dict[str, Any]:
        """Get current branch context for filtering.

        Returns:
            Dictionary with current branch information
        """
        try:
            import subprocess

            # First check if this is actually a git repository using the proper git runner
            check_result = run_git_command(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.project_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            # If not a git repository, return empty context silently
            if check_result.returncode != 0:
                return {"branch": "unknown", "commit": "unknown", "files": set()}

            # Get current branch using git runner
            result = run_git_command(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            current_branch = result.stdout.strip()

            # Get current commit hash using git runner
            result = run_git_command(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            current_commit = result.stdout.strip()

            # Get list of files in current branch using git runner
            result = run_git_command(
                ["git", "ls-tree", "-r", "--name-only", "HEAD"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            current_files = (
                set(result.stdout.strip().split("\n"))
                if result.stdout.strip()
                else set()
            )

            return {
                "branch": current_branch,
                "commit": current_commit,
                "files": current_files,
            }

        except subprocess.CalledProcessError as e:
            # Git command failed - provide more helpful error message
            if "dubious ownership" in str(e.stderr):
                logger.warning(
                    f"Git repository ownership issue detected at {self.project_dir}. "
                    "This typically occurs when running as a different user than the repository owner. "
                    "Consider adding the directory to Git's safe directories with: "
                    f"git config --global --add safe.directory {self.project_dir}"
                )
            else:
                # Not a git repository or no commits yet - this is expected in test environments
                logger.debug(f"Git command failed: {e}")
            return {"branch": "unknown", "commit": "unknown", "files": set()}
        except Exception as e:
            # Only log unexpected errors
            logger.debug(f"Unexpected error getting branch context: {e}")
            return {"branch": "unknown", "commit": "unknown", "files": set()}

    def _is_result_current_branch(
        self, result: Dict[str, Any], branch_context: Dict[str, Any]
    ) -> bool:
        """Check if a search result belongs to the current branch.

        Args:
            result: Search result with metadata
            branch_context: Current branch context

        Returns:
            True if result is from current branch
        """
        try:
            # Extract metadata from result
            metadata = result.get("payload", {}) if "payload" in result else result

            # If no git metadata, include it (filesystem-based result)
            if not metadata.get("git_available", False):
                return True

            # Check if file exists in current branch
            file_path = metadata.get("file_path", "")
            if file_path in branch_context["files"]:
                return True

            # For git-based results, also check if the commit is reachable
            result_commit = metadata.get("git_commit_hash", "")
            if result_commit and self._is_commit_reachable(result_commit):
                return True

            return False

        except Exception as e:
            logger.warning(f"Error checking result branch compatibility: {e}")
            # Default to including the result if we can't determine
            return True

    def _is_commit_reachable(self, commit_hash: str) -> bool:
        """Check if a commit is reachable from current HEAD.

        Args:
            commit_hash: Git commit hash to check

        Returns:
            True if commit is reachable from current HEAD
        """
        try:
            result = run_git_command(
                ["git", "merge-base", "--is-ancestor", commit_hash, "HEAD"],
                cwd=self.project_dir,
                capture_output=True,
                check=False,
            )

            # Return code 0 means commit is ancestor (reachable)
            return bool(result.returncode == 0)

        except Exception as e:
            logger.warning(f"Error checking commit reachability: {e}")
            return True  # Default to allowing if we can't check

    def enhance_query_metadata(self, query: str) -> Dict[str, Any]:
        """Enhance query with current branch metadata.

        Args:
            query: The search query

        Returns:
            Dictionary with enhanced query metadata
        """
        query_metadata = {
            "query": query,
            "project_id": self.file_identifier._get_project_id(),
            "git_available": self.file_identifier.git_available,
        }

        if self.file_identifier.git_available:
            branch_context = self._get_current_branch_context()
            query_metadata.update(
                {
                    "branch": branch_context["branch"],
                    "commit": branch_context["commit"],
                    "file_count": len(branch_context["files"]),
                }
            )

        return query_metadata

    def get_current_branch_context(self) -> Dict[str, Any]:
        """Get current branch context including git status.

        Returns:
            Dictionary with git status and branch information
        """
        branch_context = self._get_current_branch_context()

        # Add additional context that CLI expects
        result = {
            "git_available": self.file_identifier.git_available,
            "project_id": self.file_identifier._get_project_id(),
            "current_branch": branch_context.get("branch", "unknown"),
            "current_commit": branch_context.get("commit", "unknown"),
            "file_count": len(branch_context.get("files", set())),
        }

        return result

    def filter_results_by_current_branch(
        self, search_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter search results to only include files from the current branch.

        This is an alias for filter_results_by_branch for CLI compatibility.

        Args:
            search_results: List of search results from vector database

        Returns:
            Filtered list containing only current branch results
        """
        return self.filter_results_by_branch(search_results)
