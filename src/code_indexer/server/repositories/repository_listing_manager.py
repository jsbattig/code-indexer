"""
Repository Listing Manager for CIDX Server.

Provides repository listing functionality with search, filtering, and statistics.
Handles both golden repositories and user activated repositories.
"""

import os
import subprocess
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from .golden_repo_manager import GoldenRepoManager
from .activated_repo_manager import ActivatedRepoManager


class RepositoryListingError(Exception):
    """Base exception for repository listing operations."""

    pass


class RepositoryListingManager:
    """
    Manages repository listing functionality for the CIDX server.

    Provides search, filtering, and statistics for both
    golden repositories and user activated repositories.
    """

    def __init__(
        self,
        golden_repo_manager: Optional[GoldenRepoManager] = None,
        activated_repo_manager: Optional[ActivatedRepoManager] = None,
    ):
        """
        Initialize repository listing manager.

        Args:
            golden_repo_manager: Golden repository manager instance
            activated_repo_manager: Activated repository manager instance
        """
        self.golden_repo_manager = golden_repo_manager or GoldenRepoManager()
        self.activated_repo_manager = activated_repo_manager or ActivatedRepoManager()
        self.logger = logging.getLogger(__name__)

    def list_available_repositories(
        self,
        username: str,
        search_term: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List available golden repositories for a user.

        Args:
            username: Username to get available repositories for
            search_term: Optional search term to filter repositories
            status_filter: Optional status filter ("available" or "activated")

        Returns:
            Dictionary with repositories list and total count

        Raises:
            RepositoryListingError: If invalid parameters provided
        """

        # Validate status filter
        if status_filter and status_filter not in ["available", "activated"]:
            raise RepositoryListingError(
                "Invalid status filter. Must be 'available' or 'activated'"
            )

        # Get all golden repositories
        all_golden_repos = self.golden_repo_manager.list_golden_repos()

        # Get user's activated repositories
        activated_repos = self.activated_repo_manager.list_activated_repositories(
            username
        )
        activated_aliases = {repo["golden_repo_alias"] for repo in activated_repos}

        # Filter based on status
        if status_filter == "available":
            # Only show repositories not activated by user
            filtered_repos = [
                repo
                for repo in all_golden_repos
                if repo["alias"] not in activated_aliases
            ]
        elif status_filter == "activated":
            # Only show repositories activated by user
            filtered_repos = [
                repo for repo in all_golden_repos if repo["alias"] in activated_aliases
            ]
        else:
            # Show all repositories, but exclude activated ones by default (for available listing)
            filtered_repos = [
                repo
                for repo in all_golden_repos
                if repo["alias"] not in activated_aliases
            ]

        # Apply search filter if provided
        if search_term:
            search_lower = search_term.lower()
            filtered_repos = [
                repo
                for repo in filtered_repos
                if search_lower in repo["alias"].lower()
                or search_lower in repo.get("repo_url", "").lower()
            ]

        # Return all filtered repositories
        total_count = len(filtered_repos)

        return {
            "repositories": filtered_repos,
            "total": total_count,
        }

    def _find_golden_repository(self, alias: str) -> Optional[Dict[str, Any]]:
        """
        Find a golden repository by alias.

        Args:
            alias: Repository alias to find

        Returns:
            Repository data dictionary or None if not found
        """
        for repo_data in self.golden_repo_manager.list_golden_repos():
            if repo_data["alias"] == alias:
                return repo_data
        return None

    def get_repository_details(self, alias: str, username: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific golden repository.

        Args:
            alias: Repository alias to get details for
            username: Username to check activation status for

        Returns:
            Dictionary with detailed repository information

        Raises:
            RepositoryListingError: If repository not found
        """
        # Find the golden repository
        golden_repo = self._find_golden_repository(alias)

        if not golden_repo:
            raise RepositoryListingError(f"Repository '{alias}' not found")

        # Get user's activated repositories to check activation status
        activated_repos = self.activated_repo_manager.list_activated_repositories(
            username
        )
        activated_aliases = {repo["golden_repo_alias"] for repo in activated_repos}

        # Build detailed response
        details: Dict[str, Any] = {
            "alias": golden_repo["alias"],
            "repo_url": golden_repo["repo_url"],
            "default_branch": golden_repo["default_branch"],
            "clone_path": golden_repo["clone_path"],
            "created_at": golden_repo["created_at"],
            "activation_status": (
                "activated" if alias in activated_aliases else "available"
            ),
        }

        # Add branches list if we can get it
        try:
            details["branches_list"] = self.get_available_branches(alias)
        except Exception as e:
            self.logger.warning(f"Could not get branches for {alias}: {e}")
            details["branches_list"] = [golden_repo["default_branch"]]

        # Add repository statistics
        try:
            stats = self.get_repository_statistics(alias)
            details["file_count"] = stats["file_count"]
            details["index_size"] = stats["index_size"]
            details["last_updated"] = stats["last_updated"]
        except Exception as e:
            self.logger.warning(f"Could not get statistics for {alias}: {e}")
            details["file_count"] = 0
            details["index_size"] = 0
            details["last_updated"] = golden_repo["created_at"]

        return details

    def get_available_branches(self, alias: str) -> List[str]:
        """
        Get list of available branches for a repository.

        Args:
            alias: Repository alias

        Returns:
            List of branch names

        Raises:
            RepositoryListingError: If repository not found or git operation fails
        """
        # Find the golden repository
        golden_repo = self._find_golden_repository(alias)

        if not golden_repo:
            raise RepositoryListingError(f"Repository '{alias}' not found")

        clone_path = golden_repo["clone_path"]

        try:
            # Get remote branches using git ls-remote
            result = subprocess.run(
                ["git", "ls-remote", "--heads", clone_path],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise RepositoryListingError(
                    f"Failed to get branches for repository {alias}: {result.stderr}"
                )

            # Parse branch names from ls-remote output
            branches = []
            for line in result.stdout.strip().split("\n"):
                if line and "refs/heads/" in line:
                    branch_name = line.split("refs/heads/")[-1].strip()
                    if branch_name:
                        branches.append(branch_name)

            return branches or [golden_repo["default_branch"]]

        except subprocess.TimeoutExpired:
            self.logger.warning(f"Git ls-remote timed out for repository {alias}")
            return [golden_repo["default_branch"]]
        except Exception as e:
            self.logger.warning(f"Failed to get branches for repository {alias}: {e}")
            return [golden_repo["default_branch"]]

    def get_repository_statistics(self, alias: str) -> Dict[str, Any]:
        """
        Get repository statistics including file count and index size.

        Args:
            alias: Repository alias

        Returns:
            Dictionary with repository statistics

        Raises:
            RepositoryListingError: If repository not found
        """
        # Find the golden repository
        golden_repo = self._find_golden_repository(alias)

        if not golden_repo:
            raise RepositoryListingError(f"Repository '{alias}' not found")

        clone_path = golden_repo["clone_path"]

        # Calculate file count
        file_count = self._get_repository_file_count(clone_path)

        # Calculate index size (directory size)
        index_size = self._get_repository_index_size(clone_path)

        # Get last modified time
        try:
            last_updated = self._get_repository_last_modified(clone_path)
        except Exception:
            last_updated = golden_repo["created_at"]

        return {
            "file_count": file_count,
            "index_size": index_size,
            "last_updated": last_updated,
        }

    def get_activation_count(self, golden_repo_alias: str) -> int:
        """
        Get the number of users who have activated a specific golden repository.

        Args:
            golden_repo_alias: Golden repository alias

        Returns:
            Number of users who have activated this repository
        """
        activation_count = 0

        # Check all users' activated repositories
        activated_repos_dir = os.path.join(
            self.activated_repo_manager.data_dir, "activated-repos"
        )

        if not os.path.exists(activated_repos_dir):
            return 0

        for username in os.listdir(activated_repos_dir):
            user_dir = os.path.join(activated_repos_dir, username)
            if not os.path.isdir(user_dir):
                continue

            # Check user's activated repositories
            user_activated = self.activated_repo_manager.list_activated_repositories(
                username
            )
            for activated_repo in user_activated:
                if activated_repo["golden_repo_alias"] == golden_repo_alias:
                    activation_count += 1
                    break  # Each user can only activate once

        return activation_count

    def search_repositories(self, username: str, search_term: str) -> Dict[str, Any]:
        """
        Search repositories by term.

        Args:
            username: Username
            search_term: Search term

        Returns:
            Search results
        """
        return self.list_available_repositories(
            username=username, search_term=search_term
        )

    def filter_repositories(self, username: str, status_filter: str) -> Dict[str, Any]:
        """
        Filter repositories by status.

        Args:
            username: Username
            status_filter: Filter by status ("available" or "activated")

        Returns:
            Filtered results
        """
        return self.list_available_repositories(
            username=username, status_filter=status_filter
        )

    def _get_repository_file_count(self, repo_path: str) -> int:
        """
        Count files in repository (excluding .git directory).

        Args:
            repo_path: Path to repository

        Returns:
            Number of files
        """
        file_count = 0
        try:
            for root, dirs, files in os.walk(repo_path):
                # Skip .git directory
                if ".git" in root:
                    continue
                file_count += len(files)
        except Exception as e:
            self.logger.warning(f"Failed to count files in {repo_path}: {e}")

        return file_count

    def _get_repository_index_size(self, repo_path: str) -> int:
        """
        Get total size of repository in bytes.

        Args:
            repo_path: Path to repository

        Returns:
            Size in bytes
        """
        total_size = 0
        try:
            for root, dirs, files in os.walk(repo_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(file_path)
                    except OSError:
                        # Skip files we can't access
                        pass
        except Exception as e:
            self.logger.warning(f"Failed to calculate size for {repo_path}: {e}")

        return total_size

    def _get_repository_last_modified(self, repo_path: str) -> str:
        """
        Get last modified timestamp for repository.

        Args:
            repo_path: Path to repository

        Returns:
            ISO formatted timestamp
        """
        try:
            # Get the most recent modification time in the repository
            latest_mtime: float = 0.0
            for root, dirs, files in os.walk(repo_path):
                # Skip .git directory for performance
                if ".git" in root:
                    continue
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(file_path)
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                    except OSError:
                        # Skip files we can't access
                        pass

            if latest_mtime > 0:
                return datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()
            else:
                return datetime.now(timezone.utc).isoformat()

        except Exception as e:
            self.logger.warning(
                f"Failed to get last modified time for {repo_path}: {e}"
            )
            return datetime.now(timezone.utc).isoformat()
