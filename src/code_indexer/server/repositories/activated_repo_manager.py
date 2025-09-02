"""
Activated Repository Manager for CIDX Server.

Manages user-specific activated repositories created from golden repositories.
Supports copy-on-write cloning, branch management, and integration with background jobs.
"""

import json
import os
import shutil
import subprocess
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

from .golden_repo_manager import GoldenRepoManager
from .background_jobs import BackgroundJobManager


class ActivatedRepoError(Exception):
    """Base exception for activated repository operations."""

    pass


class GitOperationError(ActivatedRepoError):
    """Exception raised when git operations fail."""

    pass


class ActivatedRepo(BaseModel):
    """Model representing an activated repository."""

    user_alias: str
    golden_repo_alias: str
    current_branch: str
    activated_at: str
    last_accessed: str

    def to_dict(self) -> Dict[str, str]:
        """Convert activated repository to dictionary."""
        return {
            "user_alias": self.user_alias,
            "golden_repo_alias": self.golden_repo_alias,
            "current_branch": self.current_branch,
            "activated_at": self.activated_at,
            "last_accessed": self.last_accessed,
        }


# Logger is configured at class level in __init__ method


class ActivatedRepoManager:
    """
    Manages activated repositories for CIDX server users.

    Activated repositories are user-specific instances of golden repositories
    that support branch switching and copy-on-write cloning.
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        golden_repo_manager: Optional[GoldenRepoManager] = None,
        background_job_manager: Optional[BackgroundJobManager] = None,
    ):
        """
        Initialize activated repository manager.

        Args:
            data_dir: Data directory path (defaults to ~/.cidx-server/data)
            golden_repo_manager: Golden repo manager instance
            background_job_manager: Background job manager instance
        """
        if data_dir:
            self.data_dir = data_dir
        else:
            home_dir = Path.home()
            self.data_dir = str(home_dir / ".cidx-server" / "data")

        self.activated_repos_dir = os.path.join(self.data_dir, "activated-repos")

        # Ensure directory structure exists
        os.makedirs(self.activated_repos_dir, exist_ok=True)

        # Set up class-level logger
        self.logger = logging.getLogger(__name__)

        # Set dependencies
        self.golden_repo_manager = golden_repo_manager or GoldenRepoManager(data_dir)
        self.background_job_manager = background_job_manager or BackgroundJobManager()

    def activate_repository(
        self,
        username: str,
        golden_repo_alias: str,
        branch_name: Optional[str] = None,
        user_alias: Optional[str] = None,
    ) -> str:
        """
        Activate a repository for a user (background job).

        Args:
            username: Username requesting activation
            golden_repo_alias: Golden repository alias to activate
            branch_name: Branch to activate (defaults to golden repo's default branch)
            user_alias: User's alias for the repo (defaults to golden_repo_alias)

        Returns:
            Job ID for tracking activation progress

        Raises:
            ActivatedRepoError: If golden repo not found or already activated
        """
        # Validate golden repository exists
        if golden_repo_alias not in self.golden_repo_manager.golden_repos:
            raise ActivatedRepoError(
                f"Golden repository '{golden_repo_alias}' not found"
            )

        # Set defaults
        if user_alias is None:
            user_alias = golden_repo_alias

        if branch_name is None:
            golden_repo = self.golden_repo_manager.golden_repos[golden_repo_alias]
            branch_name = golden_repo.default_branch

        # Check if repository already activated for this user
        user_dir = os.path.join(self.activated_repos_dir, username)
        repo_dir = os.path.join(user_dir, user_alias)
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

        if os.path.exists(repo_dir) and os.path.exists(metadata_file):
            raise ActivatedRepoError(
                f"Repository '{user_alias}' already activated for user '{username}'"
            )

        # Submit background job
        job_id = self.background_job_manager.submit_job(
            "activate_repository",
            self._do_activate_repository,  # type: ignore[arg-type]
            # Function arguments as keyword args
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name=branch_name,
            user_alias=user_alias,
            # Job submitter
            submitter_username=username,
        )

        return job_id

    def list_activated_repositories(self, username: str) -> List[Dict[str, Any]]:
        """
        List activated repositories for a user.

        Args:
            username: Username to list repositories for

        Returns:
            List of activated repository dictionaries
        """
        user_dir = os.path.join(self.activated_repos_dir, username)

        if not os.path.exists(user_dir):
            return []

        activated_repos = []

        # Find all metadata files
        for filename in os.listdir(user_dir):
            if filename.endswith("_metadata.json"):
                metadata_file = os.path.join(user_dir, filename)
                try:
                    with open(metadata_file, "r") as f:
                        repo_data = json.load(f)

                    # Verify corresponding directory exists
                    user_alias = repo_data["user_alias"]
                    repo_dir = os.path.join(user_dir, user_alias)

                    if os.path.exists(repo_dir):
                        activated_repos.append(repo_data)

                except (json.JSONDecodeError, KeyError, IOError):
                    # Skip corrupted metadata files
                    self.logger.warning(
                        f"Skipping corrupted metadata file: {metadata_file}"
                    )
                    continue

        return activated_repos

    def deactivate_repository(self, username: str, user_alias: str) -> str:
        """
        Deactivate a repository for a user (background job).

        Args:
            username: Username requesting deactivation
            user_alias: User's alias for the repository

        Returns:
            Job ID for tracking deactivation progress

        Raises:
            ActivatedRepoError: If repository not found
        """
        user_dir = os.path.join(self.activated_repos_dir, username)
        repo_dir = os.path.join(user_dir, user_alias)
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

        # Check if repository exists
        if not os.path.exists(repo_dir) or not os.path.exists(metadata_file):
            raise ActivatedRepoError(
                f"Activated repository '{user_alias}' not found for user '{username}'"
            )

        # Submit background job
        job_id = self.background_job_manager.submit_job(
            "deactivate_repository",
            self._do_deactivate_repository,  # type: ignore[arg-type]
            username=username,
            user_alias=user_alias,
            submitter_username=username,
        )

        return job_id

    def switch_branch(
        self, username: str, user_alias: str, branch_name: str
    ) -> Dict[str, Any]:
        """
        Switch branch for an activated repository.

        Handles both local and remote repositories gracefully by:
        1. Attempting to fetch from origin if remote is accessible
        2. Falling back to local branch switching if fetch fails
        3. Providing clear error messages for different failure scenarios

        Args:
            username: Username
            user_alias: User's alias for the repository
            branch_name: Branch to switch to

        Returns:
            Result dictionary with success status and message

        Raises:
            ActivatedRepoError: If repository not found
            GitOperationError: If git operations fail after all fallback attempts
        """
        # Validate branch name for security
        self._validate_branch_name(branch_name)

        user_dir = os.path.join(self.activated_repos_dir, username)
        repo_dir = os.path.join(user_dir, user_alias)
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

        # Check if repository exists
        if not os.path.exists(repo_dir) or not os.path.exists(metadata_file):
            raise ActivatedRepoError(
                f"Activated repository '{user_alias}' not found for user '{username}'"
            )

        try:
            # Step 1: Determine if we should attempt to fetch from remote
            should_fetch, remote_info = self._should_fetch_from_remote(repo_dir)
            fetch_attempted = False
            fetch_successful = False

            if should_fetch:
                # Step 2: Attempt to fetch latest changes from remote
                self.logger.info(
                    f"Attempting to fetch from remote for repository '{user_alias}'"
                )
                fetch_attempted = True
                fetch_result = subprocess.run(
                    ["git", "fetch", "origin"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if fetch_result.returncode == 0:
                    fetch_successful = True
                    self.logger.info(
                        f"Successfully fetched from remote for repository '{user_alias}'"
                    )
                else:
                    self.logger.warning(
                        f"Git fetch failed for repository '{user_alias}': {fetch_result.stderr}. "
                        f"Attempting local branch switching as fallback."
                    )

            # Step 3: Attempt branch switching with appropriate strategy
            branch_switch_success = False

            if fetch_successful:
                # Try with remote tracking branch first
                branch_switch_success = self._switch_to_remote_tracking_branch(
                    repo_dir, branch_name, user_alias
                )

            if not branch_switch_success:
                # Fallback to local branch switching
                branch_switch_success = self._switch_to_local_branch(
                    repo_dir, branch_name, user_alias
                )

            if not branch_switch_success:
                # Final error - neither remote nor local branch switching worked
                error_msg = (
                    f"Branch '{branch_name}' not found in repository '{user_alias}'"
                )
                if fetch_attempted and not fetch_successful:
                    error_msg += f" (fetch from remote failed: {remote_info})"
                raise GitOperationError(error_msg)

            # Step 4: Update metadata
            with open(metadata_file, "r") as f:
                repo_data = json.load(f)

            repo_data["current_branch"] = branch_name
            repo_data["last_accessed"] = datetime.now(timezone.utc).isoformat()

            with open(metadata_file, "w") as f:
                json.dump(repo_data, f, indent=2)

            # Step 5: Return success with appropriate message
            message = f"Successfully switched to branch '{branch_name}' in repository '{user_alias}'"
            if fetch_attempted:
                if fetch_successful:
                    message += " (with remote sync)"
                else:
                    message += " (local branch, remote fetch failed)"
            else:
                message += " (local branch)"

            return {
                "success": True,
                "message": message,
            }

        except subprocess.TimeoutExpired:
            raise GitOperationError("Git operation timed out")
        except Exception as e:
            if isinstance(e, (ActivatedRepoError, GitOperationError)):
                raise
            raise GitOperationError(f"Failed to switch branch: {str(e)}")

    def sync_with_golden_repository(
        self, username: str, user_alias: str
    ) -> Dict[str, Any]:
        """
        Sync activated repository with its golden repository.

        This operation:
        1. Fetches latest changes from the golden repository (origin remote)
        2. Merges changes into the current branch
        3. Updates last_accessed timestamp in metadata

        Args:
            username: Username
            user_alias: User's alias for the repository

        Returns:
            Result dictionary with success status and message

        Raises:
            ActivatedRepoError: If repository not found
            GitOperationError: If git sync operations fail
        """
        user_dir = os.path.join(self.activated_repos_dir, username)
        repo_dir = os.path.join(user_dir, user_alias)
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

        # Check if repository exists
        if not os.path.exists(repo_dir) or not os.path.exists(metadata_file):
            raise ActivatedRepoError(
                f"Activated repository '{user_alias}' not found for user '{username}'"
            )

        try:
            # Read current metadata to get branch information
            with open(metadata_file, "r") as f:
                repo_data = json.load(f)

            current_branch = repo_data.get("current_branch", "master")

            # Check if this is a git repository
            git_dir = os.path.join(repo_dir, ".git")
            if not os.path.exists(git_dir):
                raise GitOperationError(
                    f"Repository '{user_alias}' is not a git repository - sync not supported"
                )

            # Step 1: Fetch from origin (golden repository)
            self.logger.info(
                f"Syncing repository '{user_alias}' with golden repository"
            )

            fetch_result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if fetch_result.returncode != 0:
                # Check if this is a network/access error or missing remote
                if "not a git repository" in fetch_result.stderr.lower():
                    raise GitOperationError(
                        f"Golden repository not accessible for sync: {fetch_result.stderr}"
                    )
                else:
                    self.logger.warning(
                        f"Git fetch failed for repository '{user_alias}': {fetch_result.stderr}"
                    )
                    # Continue with local-only sync message
                    return {
                        "success": True,
                        "message": f"Repository '{user_alias}' is up to date (fetch failed, no changes applied)",
                        "changes_applied": False,
                    }

            # Step 2: Check if there are changes to merge
            # Compare current branch with origin branch
            diff_result = subprocess.run(
                ["git", "diff", f"HEAD..origin/{current_branch}", "--name-only"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            has_changes = diff_result.returncode == 0 and diff_result.stdout.strip()

            if not has_changes:
                # No changes to sync
                return {
                    "success": True,
                    "message": f"Repository '{user_alias}' is already up to date",
                    "changes_applied": False,
                }

            # Step 3: Merge changes from origin
            merge_result = subprocess.run(
                ["git", "merge", f"origin/{current_branch}"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if merge_result.returncode != 0:
                # Merge conflict or error
                if (
                    "conflict" in merge_result.stdout.lower()
                    or "conflict" in merge_result.stderr.lower()
                ):
                    raise GitOperationError(
                        f"Sync failed due to merge conflicts in repository '{user_alias}'. "
                        "Manual resolution required."
                    )
                else:
                    raise GitOperationError(
                        f"Sync failed for repository '{user_alias}': {merge_result.stderr}"
                    )

            # Step 4: Update metadata timestamp
            repo_data["last_accessed"] = datetime.now(timezone.utc).isoformat()

            with open(metadata_file, "w") as f:
                json.dump(repo_data, f, indent=2)

            # Step 5: Return success message with details
            changed_files = (
                diff_result.stdout.strip().split("\n")
                if diff_result.stdout.strip()
                else []
            )

            self.logger.info(
                f"Successfully synced repository '{user_alias}' with golden repository"
            )

            return {
                "success": True,
                "message": f"Successfully synced repository '{user_alias}' with golden repository",
                "changes_applied": True,
                "files_changed": len(changed_files),
                "changed_files": changed_files[
                    :10
                ],  # Limit to first 10 for response size
            }

        except subprocess.TimeoutExpired:
            raise GitOperationError("Git sync operation timed out")
        except (json.JSONDecodeError, KeyError, IOError) as e:
            raise ActivatedRepoError(f"Failed to read repository metadata: {str(e)}")
        except Exception as e:
            if isinstance(e, (ActivatedRepoError, GitOperationError)):
                raise
            raise GitOperationError(f"Failed to sync repository: {str(e)}")

    def list_repository_branches(
        self, username: str, user_alias: str
    ) -> Dict[str, Any]:
        """
        List all branches available in an activated repository.

        Returns both local and remote branches, indicating the current branch.

        Args:
            username: Username
            user_alias: User's alias for the repository

        Returns:
            Dictionary containing branch information

        Raises:
            ActivatedRepoError: If repository not found
            GitOperationError: If git operations fail
        """
        user_dir = os.path.join(self.activated_repos_dir, username)
        repo_dir = os.path.join(user_dir, user_alias)
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

        # Check if repository exists
        if not os.path.exists(repo_dir) or not os.path.exists(metadata_file):
            raise ActivatedRepoError(
                f"Activated repository '{user_alias}' not found for user '{username}'"
            )

        # Check if this is a git repository
        git_dir = os.path.join(repo_dir, ".git")
        if not os.path.exists(git_dir):
            raise GitOperationError(
                f"Repository '{user_alias}' is not a git repository - branch listing not supported"
            )

        try:
            # Read current metadata to get current branch
            with open(metadata_file, "r") as f:
                repo_data = json.load(f)

            current_branch = repo_data.get("current_branch", "master")

            # Get list of local branches
            local_branches_result = subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if local_branches_result.returncode != 0:
                raise GitOperationError(
                    f"Failed to list local branches: {local_branches_result.stderr}"
                )

            local_branches = [
                branch.strip()
                for branch in local_branches_result.stdout.strip().split("\n")
                if branch.strip()
            ]

            # Get list of remote branches
            remote_branches_result = subprocess.run(
                ["git", "branch", "-r", "--format=%(refname:short)"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            remote_branches = []
            if remote_branches_result.returncode == 0:
                remote_branches = [
                    branch.strip()
                    for branch in remote_branches_result.stdout.strip().split("\n")
                    if branch.strip() and not branch.strip().endswith("/HEAD")
                ]

            # Get detailed branch information
            all_branches = []

            for branch in local_branches:
                branch_info = {
                    "name": branch,
                    "type": "local",
                    "is_current": branch == current_branch,
                }

                # Try to get last commit info for this branch
                try:
                    commit_result = subprocess.run(
                        ["git", "log", "-1", "--format=%H|%s|%ai", branch],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if commit_result.returncode == 0 and commit_result.stdout.strip():
                        commit_info = commit_result.stdout.strip().split("|")
                        if len(commit_info) >= 3:
                            branch_info.update(
                                {
                                    "last_commit_hash": commit_info[0][
                                        :8
                                    ],  # Short hash
                                    "last_commit_message": commit_info[1],
                                    "last_commit_date": commit_info[2],
                                }
                            )
                except subprocess.TimeoutExpired:
                    pass  # Skip commit info if it times out

                all_branches.append(branch_info)

            # Add remote branches that don't have local counterparts
            for remote_branch in remote_branches:
                # Extract branch name without remote prefix (e.g., "origin/feature" -> "feature")
                if "/" in remote_branch:
                    remote_name = remote_branch.split("/", 1)[1]
                else:
                    remote_name = remote_branch

                # Skip if we already have this branch locally
                if remote_name not in local_branches:
                    branch_info = {
                        "name": remote_name,
                        "type": "remote",
                        "remote_ref": remote_branch,
                        "is_current": False,
                    }

                    # Try to get commit info for remote branch
                    try:
                        commit_result = subprocess.run(
                            ["git", "log", "-1", "--format=%H|%s|%ai", remote_branch],
                            cwd=repo_dir,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )

                        if (
                            commit_result.returncode == 0
                            and commit_result.stdout.strip()
                        ):
                            commit_info = commit_result.stdout.strip().split("|")
                            if len(commit_info) >= 3:
                                branch_info.update(
                                    {
                                        "last_commit_hash": commit_info[0][:8],
                                        "last_commit_message": commit_info[1],
                                        "last_commit_date": commit_info[2],
                                    }
                                )
                    except subprocess.TimeoutExpired:
                        pass

                    all_branches.append(branch_info)

            return {
                "branches": all_branches,
                "current_branch": current_branch,
                "total_branches": len(all_branches),
                "local_branches": len(local_branches),
                "remote_branches": len(
                    [b for b in all_branches if b["type"] == "remote"]
                ),
            }

        except subprocess.TimeoutExpired:
            raise GitOperationError("Branch listing operation timed out")
        except (json.JSONDecodeError, KeyError, IOError) as e:
            raise ActivatedRepoError(f"Failed to read repository metadata: {str(e)}")
        except Exception as e:
            if isinstance(e, (ActivatedRepoError, GitOperationError)):
                raise
            raise GitOperationError(f"Failed to list branches: {str(e)}")

    def get_activated_repo_path(self, username: str, user_alias: str) -> str:
        """
        Get the filesystem path to an activated repository.

        Args:
            username: Username
            user_alias: User's alias for the repository

        Returns:
            Absolute path to the activated repository directory
        """
        return os.path.join(self.activated_repos_dir, username, user_alias)

    def _do_activate_repository(
        self, username: str, golden_repo_alias: str, branch_name: str, user_alias: str
    ) -> Dict[str, Any]:
        """
        Perform actual repository activation (called by background job).

        Args:
            username: Username requesting activation
            golden_repo_alias: Golden repository alias to activate
            branch_name: Branch to activate
            user_alias: User's alias for the repo

        Returns:
            Result dictionary with success status and message
        """
        try:
            golden_repo = self.golden_repo_manager.golden_repos[golden_repo_alias]

            # Create user directory structure
            user_dir = os.path.join(self.activated_repos_dir, username)
            os.makedirs(user_dir, exist_ok=True)

            activated_repo_path = os.path.join(user_dir, user_alias)

            # Clone repository with CoW
            success = self._clone_with_copy_on_write(
                golden_repo.clone_path, activated_repo_path
            )

            if not success:
                raise ActivatedRepoError("Failed to clone repository")

            # Switch to requested branch if different from default
            if branch_name != golden_repo.default_branch:
                result = subprocess.run(
                    ["git", "checkout", "-B", branch_name, f"origin/{branch_name}"],
                    cwd=activated_repo_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode != 0:
                    # Clean up on failure
                    shutil.rmtree(activated_repo_path, ignore_errors=True)
                    raise GitOperationError(
                        f"Failed to switch to branch '{branch_name}': {result.stderr}"
                    )

            # Create metadata file
            activated_at = datetime.now(timezone.utc).isoformat()
            metadata = {
                "user_alias": user_alias,
                "golden_repo_alias": golden_repo_alias,
                "current_branch": branch_name,
                "activated_at": activated_at,
                "last_accessed": activated_at,
            }

            metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")
            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

            self.logger.info(
                f"Successfully activated repository '{user_alias}' for user '{username}'"
            )

            return {
                "success": True,
                "message": f"Repository '{user_alias}' activated successfully",
                "user_alias": user_alias,
                "branch": branch_name,
            }

        except Exception as e:
            error_msg = f"Failed to activate repository '{user_alias}' for user '{username}': {str(e)}"
            self.logger.error(error_msg)
            raise ActivatedRepoError(error_msg)

    def _do_deactivate_repository(
        self, username: str, user_alias: str
    ) -> Dict[str, Any]:
        """
        Perform actual repository deactivation (called by background job).

        Args:
            username: Username requesting deactivation
            user_alias: User's alias for the repository

        Returns:
            Result dictionary with success status and message
        """
        try:
            user_dir = os.path.join(self.activated_repos_dir, username)
            repo_dir = os.path.join(user_dir, user_alias)
            metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

            # Remove repository directory
            if os.path.exists(repo_dir):
                shutil.rmtree(repo_dir)

            # Remove metadata file
            if os.path.exists(metadata_file):
                os.remove(metadata_file)

            self.logger.info(
                f"Successfully deactivated repository '{user_alias}' for user '{username}'"
            )

            return {
                "success": True,
                "message": f"Repository '{user_alias}' deactivated successfully",
                "user_alias": user_alias,
            }

        except Exception as e:
            error_msg = f"Failed to deactivate repository '{user_alias}' for user '{username}': {str(e)}"
            self.logger.error(error_msg)
            raise ActivatedRepoError(error_msg)

    def _clone_with_copy_on_write(self, source_path: str, dest_path: str) -> bool:
        """
        Clone repository using copy-on-write and configure git structure properly.

        Creates a CoW clone that preserves git functionality by:
        1. Using git clone to preserve all branches and git structure
        2. Configuring proper git remote for branch operations
        3. Ensuring all branches are available for switching

        Args:
            source_path: Source repository path (golden repository)
            dest_path: Destination repository path (activated repository)

        Returns:
            True if cloning succeeded

        Raises:
            ActivatedRepoError: If CoW clone or git setup fails
        """
        try:
            # Check if source is a git repository
            git_dir = os.path.join(source_path, ".git")

            if os.path.exists(git_dir):
                # Step 1: Perform git clone to preserve all branches and git structure
                self.logger.info(
                    f"Git repository detected, using git clone: {source_path} -> {dest_path}"
                )
                result = subprocess.run(
                    ["git", "clone", "--local", source_path, dest_path],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                if result.returncode != 0:
                    # Fallback to CoW clone if git clone fails
                    self.logger.warning(
                        f"Git clone failed: {result.stderr}. Falling back to CoW clone."
                    )
                    return self._fallback_copy_on_write_clone(source_path, dest_path)

                self.logger.info(f"Git clone successful: {source_path} -> {dest_path}")

                # Step 2: Set up origin remote to point to golden repository for branch operations
                self._setup_origin_remote_for_local_repo(source_path, dest_path)

            else:
                # Step 1: Perform CoW clone for non-git directories
                self.logger.info(
                    f"Non-git directory detected, using CoW clone: {source_path} -> {dest_path}"
                )
                return self._fallback_copy_on_write_clone(source_path, dest_path)

            return True

        except subprocess.TimeoutExpired:
            raise ActivatedRepoError(
                f"Clone operation timed out: {source_path} -> {dest_path}"
            )
        except Exception as e:
            # Clean up on failure
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path, ignore_errors=True)
            raise ActivatedRepoError(f"Clone operation failed: {str(e)}")

    def _fallback_copy_on_write_clone(self, source_path: str, dest_path: str) -> bool:
        """
        Fallback CoW clone implementation.

        Args:
            source_path: Source repository path
            dest_path: Destination repository path

        Returns:
            True if cloning succeeded

        Raises:
            ActivatedRepoError: If CoW clone fails
        """
        result = subprocess.run(
            ["cp", "--reflink=always", "-r", source_path, dest_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise ActivatedRepoError(f"CoW clone failed: {result.stderr}")

        self.logger.info(f"CoW clone successful: {source_path} -> {dest_path}")

        # Configure git structure if destination is a git repository
        git_dir = os.path.join(dest_path, ".git")
        if os.path.exists(git_dir):
            self._configure_git_structure(source_path, dest_path)

        return True

    def _setup_origin_remote_for_local_repo(
        self, source_path: str, dest_path: str
    ) -> None:
        """
        Set up origin remote for local repository clones.

        For local git clones, the origin remote is automatically set to the source path.
        This method ensures it's configured correctly for branch operations.

        Args:
            source_path: Source golden repository path
            dest_path: Destination activated repository path

        Raises:
            ActivatedRepoError: If git remote configuration fails
        """
        try:
            # Verify remote configuration
            result = subprocess.run(
                ["git", "remote", "-v"],
                cwd=dest_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                self.logger.info(
                    f"Git remotes configured for {dest_path}: {result.stdout.strip()}"
                )
            else:
                self.logger.warning(
                    f"Could not verify git remotes for {dest_path}: {result.stderr}"
                )

            # Fetch from origin to ensure all remote branches are available
            result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=dest_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                self.logger.warning(
                    f"Could not fetch from origin in {dest_path}: {result.stderr}"
                )

        except subprocess.TimeoutExpired:
            self.logger.warning("Git remote setup operation timed out")
        except Exception as e:
            self.logger.warning(f"Error setting up git remote: {str(e)}")

    def _configure_git_structure(self, source_path: str, dest_path: str) -> None:
        """
        Configure git structure in CoW repository for proper branch operations.

        Sets up the activated repository to work correctly with git operations by:
        1. Adding the golden repository as 'origin' remote
        2. Ensuring proper git configuration
        3. Verifying git operations work

        Args:
            source_path: Source golden repository path
            dest_path: Destination activated repository path

        Raises:
            ActivatedRepoError: If git configuration fails
        """
        try:
            # Set up 'origin' remote pointing to golden repository
            # This is essential for git fetch/checkout operations to work
            result = subprocess.run(
                ["git", "remote", "add", "origin", source_path],
                cwd=dest_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # If remote already exists, update it
                if "already exists" in result.stderr:
                    result = subprocess.run(
                        ["git", "remote", "set-url", "origin", source_path],
                        cwd=dest_path,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode != 0:
                        raise ActivatedRepoError(
                            f"Failed to update git remote: {result.stderr}"
                        )
                else:
                    raise ActivatedRepoError(
                        f"Failed to add git remote: {result.stderr}"
                    )

            # Fetch from origin to ensure remote branches are available
            result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=dest_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise ActivatedRepoError(
                    f"Failed to fetch from origin: {result.stderr}"
                )

            # Verify git structure is working
            result = subprocess.run(
                ["git", "status"],
                cwd=dest_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise ActivatedRepoError(
                    f"Git repository structure invalid: {result.stderr}"
                )

            self.logger.info(f"Git structure configured successfully for: {dest_path}")

        except subprocess.TimeoutExpired:
            raise ActivatedRepoError("Git configuration operation timed out")
        except Exception as e:
            raise ActivatedRepoError(f"Failed to configure git structure: {str(e)}")

    def _validate_branch_name(self, branch_name: str) -> None:
        """
        Validate branch name for security.

        Args:
            branch_name: Branch name to validate

        Raises:
            GitOperationError: If branch name contains invalid characters
        """
        import re

        if not branch_name or not isinstance(branch_name, str):
            raise GitOperationError("Branch name must be a non-empty string")

        # Allow alphanumeric characters, underscores, hyphens, slashes, and dots
        # This follows git's branch naming conventions and prevents command injection
        if not re.match(r"^[a-zA-Z0-9/_.-]+$", branch_name):
            raise GitOperationError(
                f"Invalid branch name: {branch_name}. Branch names can only contain letters, numbers, underscores, hyphens, slashes, and dots"
            )

        # Prevent branch names that could be problematic
        if (
            branch_name.startswith("-")
            or branch_name.endswith(".lock")
            or ".." in branch_name
        ):
            raise GitOperationError(
                f"Invalid branch name: {branch_name}. Branch names cannot start with '-', end with '.lock', or contain '..'"
            )

    def _should_fetch_from_remote(self, repo_dir: str) -> tuple[bool, str]:
        """
        Determine if we should attempt to fetch from remote origin.

        Analyzes the git repository to decide whether fetching makes sense:
        1. Check if origin remote exists
        2. Check if origin remote is accessible (not file:// or local path)
        3. Return decision and remote info for error messages

        Args:
            repo_dir: Path to the git repository

        Returns:
            Tuple of (should_fetch: bool, remote_info: str)
        """
        try:
            # Check if origin remote exists
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                # No origin remote configured
                return False, "No origin remote configured"

            origin_url = result.stdout.strip()

            # Analyze remote URL to determine if fetching makes sense
            if not origin_url:
                return False, "Empty origin URL"

            # Local file paths - fetching not needed for CoW repos
            if origin_url.startswith("/") or origin_url.startswith("file://"):
                self.logger.debug(f"Origin is local path: {origin_url}, skipping fetch")
                return False, f"Local repository: {origin_url}"

            # Relative paths - also local
            if not origin_url.startswith(("http://", "https://", "git@", "ssh://")):
                self.logger.debug(
                    f"Origin appears to be local path: {origin_url}, skipping fetch"
                )
                return False, f"Local repository: {origin_url}"

            # Remote URLs - attempt fetch
            self.logger.debug(f"Origin is remote URL: {origin_url}, will attempt fetch")
            return True, f"Remote repository: {origin_url}"

        except subprocess.TimeoutExpired:
            return False, "Timeout checking remote URL"
        except Exception as e:
            self.logger.warning(f"Error checking remote URL: {e}")
            return False, f"Error checking remote: {str(e)}"

    def _switch_to_remote_tracking_branch(
        self, repo_dir: str, branch_name: str, user_alias: str
    ) -> bool:
        """
        Attempt to switch to a remote tracking branch.

        This is used when fetch was successful and we want to create/update
        a local branch that tracks the remote branch.

        Args:
            repo_dir: Path to the git repository
            branch_name: Branch name to switch to
            user_alias: User alias for logging

        Returns:
            True if successful, False if failed (caller should try fallback)
        """
        try:
            # Switch to branch (create tracking branch if needed)
            result = subprocess.run(
                ["git", "checkout", "-B", branch_name, f"origin/{branch_name}"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                self.logger.info(
                    f"Successfully switched to remote tracking branch '{branch_name}' in repository '{user_alias}'"
                )
                return True
            else:
                self.logger.debug(
                    f"Failed to switch to remote tracking branch '{branch_name}': {result.stderr}"
                )
                return False

        except subprocess.TimeoutExpired:
            self.logger.warning(
                f"Timeout switching to remote tracking branch '{branch_name}' in repository '{user_alias}'"
            )
            return False
        except Exception as e:
            self.logger.debug(
                f"Exception switching to remote tracking branch '{branch_name}': {e}"
            )
            return False

    def _switch_to_local_branch(
        self, repo_dir: str, branch_name: str, user_alias: str
    ) -> bool:
        """
        Attempt to switch to a local branch.

        This is used as a fallback when remote fetch fails or for purely local repositories.
        It tries different strategies to find and switch to the requested branch.

        Args:
            repo_dir: Path to the git repository
            branch_name: Branch name to switch to
            user_alias: User alias for logging

        Returns:
            True if successful, False if branch doesn't exist locally
        """
        try:
            # Strategy 1: Try direct checkout (branch already exists locally)
            result = subprocess.run(
                ["git", "checkout", branch_name],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                self.logger.info(
                    f"Successfully switched to local branch '{branch_name}' in repository '{user_alias}'"
                )
                return True

            # Strategy 2: Try to create branch from local origin branch (if it exists)
            result = subprocess.run(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    f"refs/remotes/origin/{branch_name}",
                ],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Origin branch exists locally, create tracking branch
                result = subprocess.run(
                    ["git", "checkout", "-b", branch_name, f"origin/{branch_name}"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode == 0:
                    self.logger.info(
                        f"Successfully created local branch '{branch_name}' from origin in repository '{user_alias}'"
                    )
                    return True

            # Strategy 3: Check if branch exists in any form we can switch to
            result = subprocess.run(
                ["git", "show-ref", branch_name],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Branch exists somewhere, try force checkout
                result = subprocess.run(
                    ["git", "checkout", "-B", branch_name],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode == 0:
                    self.logger.info(
                        f"Successfully force-switched to branch '{branch_name}' in repository '{user_alias}'"
                    )
                    return True

            # All strategies failed
            self.logger.info(
                f"Branch '{branch_name}' not found locally in repository '{user_alias}'"
            )
            return False

        except subprocess.TimeoutExpired:
            self.logger.warning(
                f"Timeout switching to local branch '{branch_name}' in repository '{user_alias}'"
            )
            return False
        except Exception as e:
            self.logger.debug(
                f"Exception switching to local branch '{branch_name}': {e}"
            )
            return False
