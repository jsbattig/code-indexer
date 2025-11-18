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
# yaml import removed - using json for config files
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
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
        golden_repo_alias: Optional[str] = None,
        golden_repo_aliases: Optional[List[str]] = None,
        branch_name: Optional[str] = None,
        user_alias: Optional[str] = None,
    ) -> str:
        """
        Activate a repository for a user (background job).

        Supports both single repository and composite repository activation.

        Args:
            username: Username requesting activation
            golden_repo_alias: Golden repository alias to activate (single repo)
            golden_repo_aliases: Golden repository aliases for composite activation
            branch_name: Branch to activate (defaults to golden repo's default branch)
            user_alias: User's alias for the repo (defaults to golden_repo_alias)

        Returns:
            Job ID for tracking activation progress

        Raises:
            ValueError: If both or neither golden_repo parameters provided, or invalid list
            ActivatedRepoError: If golden repo not found or already activated
        """
        # Validate mutual exclusivity and requirements
        if golden_repo_alias and golden_repo_aliases:
            raise ValueError(
                "Cannot specify both golden_repo_alias and golden_repo_aliases"
            )

        # Validate composite repository requirements BEFORE checking if at least one is provided
        # This ensures empty lists get the correct error message
        if golden_repo_aliases is not None:
            if len(golden_repo_aliases) < 2:
                raise ValueError(
                    "Composite activation requires at least 2 repositories"
                )

        if not golden_repo_alias and not golden_repo_aliases:
            raise ValueError(
                "Must specify either golden_repo_alias or golden_repo_aliases"
            )

        # Route to appropriate activation method
        if golden_repo_aliases:
            return self._activate_composite_repository(
                username=username,
                golden_repo_aliases=golden_repo_aliases,
                user_alias=user_alias,
            )

        # Single repository activation (existing logic)
        return self._activate_single_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,  # type: ignore[arg-type]
            branch_name=branch_name,
            user_alias=user_alias,
        )

    def _activate_single_repository(
        self,
        username: str,
        golden_repo_alias: str,
        branch_name: Optional[str] = None,
        user_alias: Optional[str] = None,
    ) -> str:
        """
        Activate a single repository for a user (internal method).

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

    def _activate_composite_repository(
        self,
        username: str,
        golden_repo_aliases: List[str],
        user_alias: Optional[str] = None,
    ) -> str:
        """
        Activate a composite repository for a user (internal method).

        This is a stub implementation that will be completed in Story 1.2.

        Args:
            username: Username requesting activation
            golden_repo_aliases: List of golden repository aliases to combine
            user_alias: User's alias for the composite repo

        Returns:
            Job ID for tracking activation progress

        Raises:
            ActivatedRepoError: If validation or activation fails
        """
        # Submit background job for composite activation
        job_id = self.background_job_manager.submit_job(
            "activate_composite_repository",
            self._do_activate_composite_repository,  # type: ignore[arg-type]
            # Function arguments as keyword args
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            # Job submitter
            submitter_username=username,
        )

        return job_id

    def _do_activate_composite_repository(
        self,
        username: str,
        golden_repo_aliases: List[str],
        user_alias: Optional[str] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Perform actual composite repository activation.

        Creates a composite repository structure using ProxyInitializer and
        CoW clones of each golden repository.

        Args:
            username: Username requesting activation
            golden_repo_aliases: List of golden repository aliases to combine
            user_alias: User's alias for the composite repo
            progress_callback: Optional callback for progress updates

        Returns:
            Result dictionary with success status and message

        Raises:
            ActivatedRepoError: If validation or activation fails
        """

        def update_progress(percent: int, message: str = "") -> None:
            """Helper to update progress with logging."""
            if progress_callback:
                progress_callback(percent)
            if message:
                self.logger.info(
                    f"Composite activation progress ({percent}%): {message}"
                )

        try:
            # Step 0: Validate golden repositories exist
            update_progress(
                5, f"Validating {len(golden_repo_aliases)} golden repositories"
            )
            for alias in golden_repo_aliases:
                if alias not in self.golden_repo_manager.golden_repos:
                    raise ActivatedRepoError(f"Golden repository '{alias}' not found")

            # Step 1: Determine user_alias (default to joined names if not provided)
            if user_alias is None:
                user_alias = "_".join(golden_repo_aliases)
                self.logger.info(
                    f"User alias not provided, defaulting to: {user_alias}"
                )

            update_progress(
                10,
                f"Starting composite activation '{user_alias}' for user '{username}'",
            )

            # Step 2: Create base directory structure
            user_dir = os.path.join(self.activated_repos_dir, username)
            os.makedirs(user_dir, exist_ok=True)

            composite_path = Path(user_dir) / user_alias

            # Check if already exists
            if composite_path.exists():
                raise ActivatedRepoError(
                    f"Composite repository '{user_alias}' already exists for user '{username}'"
                )

            composite_path.mkdir(parents=True, exist_ok=True)
            update_progress(20, f"Created composite directory at {composite_path}")

            # Step 3: Use ProxyInitializer to create proxy configuration
            update_progress(25, "Initializing proxy configuration")
            try:
                from ...proxy.proxy_initializer import ProxyInitializer

                proxy_init = ProxyInitializer(composite_path)
                proxy_init.initialize(force=True)
                update_progress(30, "Proxy configuration initialized")

                # Add FilesystemVectorStore and VoyageAI config for composite repos
                self._update_composite_config(composite_path)

            except Exception as e:
                # Clean up on failure
                if composite_path.exists():
                    shutil.rmtree(composite_path, ignore_errors=True)
                raise ActivatedRepoError(
                    f"Failed to initialize proxy configuration: {str(e)}"
                )

            # Step 4: CoW clone each golden repository as subdirectory
            total_repos = len(golden_repo_aliases)
            cloned_count = 0

            for idx, alias in enumerate(golden_repo_aliases):
                progress_percent = 30 + int((idx / total_repos) * 50)
                update_progress(
                    progress_percent,
                    f"Cloning repository {idx + 1}/{total_repos}: {alias}",
                )

                golden_repo = self.golden_repo_manager.golden_repos[alias]
                subrepo_path = composite_path / alias

                try:
                    # Reuse existing CoW clone method
                    success = self._clone_with_copy_on_write(
                        str(golden_repo.clone_path), str(subrepo_path)
                    )

                    if not success:
                        raise ActivatedRepoError(
                            f"Failed to clone repository '{alias}'"
                        )

                    cloned_count += 1
                    self.logger.info(
                        f"Successfully cloned {alias} ({cloned_count}/{total_repos})"
                    )

                except Exception as e:
                    # Clean up on failure
                    self.logger.error(f"Failed to clone repository '{alias}': {str(e)}")
                    if composite_path.exists():
                        shutil.rmtree(composite_path, ignore_errors=True)
                    raise ActivatedRepoError(
                        f"Failed to clone repository '{alias}': {str(e)}"
                    )

            update_progress(80, f"All {total_repos} repositories cloned successfully")

            # Step 5: Refresh discovered repositories using ProxyConfigManager
            update_progress(85, "Discovering cloned repositories")
            try:
                from ...proxy.config_manager import ProxyConfigManager

                proxy_config = ProxyConfigManager(composite_path)
                proxy_config.refresh_repositories()
                update_progress(90, "Repository discovery completed")
            except Exception as e:
                # Clean up on failure
                self.logger.error(f"Failed to refresh repositories: {str(e)}")
                if composite_path.exists():
                    shutil.rmtree(composite_path, ignore_errors=True)
                raise ActivatedRepoError(
                    f"Failed to refresh repository configuration: {str(e)}"
                )

            # Step 6: Create metadata file with discovered repos
            update_progress(95, "Creating composite repository metadata")
            activated_at = datetime.now(timezone.utc).isoformat()

            # Get discovered repos from proxy config
            discovered_repos = proxy_config.get_repositories()

            metadata = {
                "user_alias": user_alias,
                "username": username,
                "path": str(composite_path),
                "is_composite": True,
                "golden_repo_aliases": golden_repo_aliases,
                "discovered_repos": discovered_repos,
                "activated_at": activated_at,
                "last_accessed": activated_at,
            }

            metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")
            try:
                with open(metadata_file, "w") as f:
                    json.dump(metadata, f, indent=2)
            except Exception as e:
                # Clean up on failure
                self.logger.error(f"Failed to create metadata file: {str(e)}")
                if composite_path.exists():
                    shutil.rmtree(composite_path, ignore_errors=True)
                raise ActivatedRepoError(f"Failed to create metadata: {str(e)}")

            update_progress(
                100, f"Composite repository '{user_alias}' activated successfully"
            )

            self.logger.info(
                f"Successfully activated composite repository '{user_alias}' for user '{username}' "
                f"with {len(golden_repo_aliases)} component repositories"
            )

            return {
                "success": True,
                "message": f"Composite repository '{user_alias}' activated successfully",
                "user_alias": user_alias,
                "is_composite": True,
                "component_count": len(golden_repo_aliases),
                "component_aliases": golden_repo_aliases,
                "activation_timestamp": activated_at,
                "details": {
                    "composite_path": str(composite_path),
                    "repositories_cloned": cloned_count,
                    "proxy_mode_enabled": True,
                },
            }

        except Exception as e:
            error_msg = f"Failed to activate composite repository '{user_alias}' for user '{username}': {str(e)}"
            self.logger.error(error_msg)

            # Report failure through progress callback
            if progress_callback:
                progress_callback(0)  # Reset progress to indicate failure

            # Re-raise ActivatedRepoError, wrap other exceptions
            if isinstance(e, ActivatedRepoError):
                raise
            raise ActivatedRepoError(error_msg)

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
        self, username: str, user_alias: str, branch_name: str, create: bool = False
    ) -> Dict[str, Any]:
        """
        Switch branch for an activated repository with optional branch creation.

        Handles both local and remote repositories gracefully by:
        1. Attempting to fetch from origin if remote is accessible
        2. Falling back to local branch switching if fetch fails
        3. Creating new branches when create=True
        4. Setting up remote tracking branches
        5. Preserving uncommitted changes when possible
        6. Providing clear error messages for different failure scenarios

        Args:
            username: Username
            user_alias: User's alias for the repository
            branch_name: Branch to switch to
            create: Whether to create the branch if it doesn't exist

        Returns:
            Result dictionary with success status, message, and operation details

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

            # Step 3: Check for uncommitted changes
            uncommitted_changes = []
            git_status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if git_status.returncode == 0 and git_status.stdout.strip():
                uncommitted_changes = [
                    line.strip()[3:]
                    for line in git_status.stdout.strip().split("\n")
                    if line.strip()
                ]

            # Step 4: Attempt branch switching with appropriate strategy
            branch_switch_success = False
            branch_created = False
            tracking_branch_created = False
            remote_origin = None

            if fetch_successful:
                # Try with remote tracking branch first
                branch_switch_success = self._switch_to_remote_tracking_branch(
                    repo_dir, branch_name, user_alias
                )
                if branch_switch_success:
                    # Check if we created a tracking branch
                    remote_branch = f"origin/{branch_name}"
                    check_remote = subprocess.run(
                        ["git", "branch", "-r", "--list", remote_branch],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if check_remote.returncode == 0 and check_remote.stdout.strip():
                        tracking_branch_created = True
                        remote_origin = remote_branch

            if not branch_switch_success:
                # Fallback to local branch switching
                branch_switch_success = self._switch_to_local_branch(
                    repo_dir, branch_name, user_alias
                )

            if not branch_switch_success and create:
                # Try to create new branch
                try:
                    create_result = subprocess.run(
                        ["git", "checkout", "-b", branch_name],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if create_result.returncode == 0:
                        branch_switch_success = True
                        branch_created = True
                        self.logger.info(
                            f"Created new branch '{branch_name}' in repository '{user_alias}'"
                        )
                    else:
                        self.logger.warning(
                            f"Failed to create branch '{branch_name}': {create_result.stderr}"
                        )

                except subprocess.TimeoutExpired:
                    self.logger.warning(
                        f"Timeout while creating branch '{branch_name}'"
                    )

            if not branch_switch_success:
                # Final error - neither remote nor local branch switching worked
                error_msg = (
                    f"Branch '{branch_name}' not found in repository '{user_alias}'"
                )
                if create:
                    error_msg += " and could not be created"
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

            # Step 5: Return success with detailed operation information
            message = f"Successfully switched to branch '{branch_name}' in repository '{user_alias}'"

            if branch_created:
                message = f"Created and switched to new branch '{branch_name}' in repository '{user_alias}'"
            elif tracking_branch_created:
                message = f"Created local tracking branch for '{remote_origin}' in repository '{user_alias}'"

            if uncommitted_changes:
                message += " with uncommitted changes preserved"

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
                "created_new_branch": branch_created,
                "tracking_branch_created": tracking_branch_created,
                "remote_origin": remote_origin,
                "uncommitted_changes": bool(uncommitted_changes),
                "preserved_files": uncommitted_changes,
            }

        except subprocess.TimeoutExpired:
            raise GitOperationError("Git operation timed out")
        except Exception as e:
            if isinstance(e, (ActivatedRepoError, GitOperationError)):
                raise
            raise GitOperationError(f"Failed to switch branch: {str(e)}")

    def get_current_branch(self, username: str, user_alias: str) -> str:
        """
        Get the current branch name for an activated repository.

        Args:
            username: Username
            user_alias: User's alias for the repository

        Returns:
            Current branch name

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

        try:
            # First try to get current branch from git directly
            result = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return result.stdout.strip()

            # Fallback to metadata if git command fails
            with open(metadata_file, "r") as f:
                repo_data = json.load(f)

            return str(repo_data.get("current_branch", "main"))

        except subprocess.TimeoutExpired:
            raise GitOperationError("Git operation timed out")
        except Exception as e:
            # Final fallback to metadata
            try:
                with open(metadata_file, "r") as f:
                    repo_data = json.load(f)
                return str(repo_data.get("current_branch", "main"))
            except Exception:
                raise GitOperationError(f"Failed to get current branch: {str(e)}")

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

    def get_repository(
        self, username: str, user_alias: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get repository metadata with fresh discovered_repos for composite repos.

        For composite repositories, refreshes the discovered_repos list from
        the proxy configuration to ensure it reflects current state.

        Args:
            username: Username
            user_alias: User's alias for the repository

        Returns:
            Repository metadata dictionary or None if not found

        Raises:
            ActivatedRepoError: If metadata loading or refresh fails
        """
        user_dir = os.path.join(self.activated_repos_dir, username)
        repo_path = os.path.join(user_dir, user_alias)
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

        # Check if repository exists
        if not os.path.exists(repo_path) or not os.path.exists(metadata_file):
            return None

        try:
            # Load metadata from file
            with open(metadata_file, "r") as f:
                metadata: Dict[str, Any] = json.load(f)

            # For composite repos, refresh discovered_repos from config
            if metadata.get("is_composite", False):
                try:
                    from ...proxy.config_manager import ProxyConfigManager

                    proxy_config = ProxyConfigManager(Path(repo_path))
                    metadata["discovered_repos"] = proxy_config.get_repositories()
                except Exception as e:
                    # Log warning but don't fail - use existing discovered_repos
                    self.logger.warning(
                        f"Failed to refresh discovered_repos for '{user_alias}': {str(e)}. "
                        f"Using cached list."
                    )

            # Update last_accessed timestamp
            metadata["last_accessed"] = datetime.now(timezone.utc).isoformat()

            # Save updated metadata
            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

            return metadata

        except (json.JSONDecodeError, KeyError, IOError) as e:
            raise ActivatedRepoError(
                f"Failed to load metadata for repository '{user_alias}': {str(e)}"
            )

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
        self,
        username: str,
        golden_repo_alias: str,
        branch_name: str,
        user_alias: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Perform actual repository activation (called by background job).

        Args:
            username: Username requesting activation
            golden_repo_alias: Golden repository alias to activate
            branch_name: Branch to activate
            user_alias: User's alias for the repo
            progress_callback: Optional callback for progress updates (0-100)

        Returns:
            Result dictionary with success status and message
        """

        def update_progress(percent: int, message: str = "") -> None:
            """Helper to update progress with logging."""
            if progress_callback:
                progress_callback(percent)
            if message:
                self.logger.info(f"Activation progress ({percent}%): {message}")

        try:
            update_progress(
                10,
                f"Starting activation of '{golden_repo_alias}' as '{user_alias}' for user '{username}'",
            )

            golden_repo = self.golden_repo_manager.golden_repos[golden_repo_alias]

            update_progress(20, "Validating golden repository")

            # Create user directory structure
            user_dir = os.path.join(self.activated_repos_dir, username)
            os.makedirs(user_dir, exist_ok=True)

            update_progress(30, "Creating user directory structure")

            activated_repo_path = os.path.join(user_dir, user_alias)

            # Clone repository with CoW
            update_progress(40, f"Cloning repository from {golden_repo.clone_path}")
            success = self._clone_with_copy_on_write(
                golden_repo.clone_path, activated_repo_path
            )

            if not success:
                raise ActivatedRepoError("Failed to clone repository")

            update_progress(60, "Repository clone completed successfully")

            # Switch to requested branch if different from default
            if branch_name != golden_repo.default_branch:
                update_progress(70, f"Switching to branch '{branch_name}'")
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
                update_progress(80, f"Successfully switched to branch '{branch_name}'")
            else:
                update_progress(75, f"Using default branch '{branch_name}'")

            # Create .code-indexer/config.yml for FilesystemVectorStore and VoyageAI
            update_progress(80, "Creating repository configuration")
            self._create_repo_config(activated_repo_path)

            # Create metadata file
            update_progress(85, "Creating repository metadata")
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

            update_progress(95, "Finalizing activation")

            self.logger.info(
                f"Successfully activated repository '{user_alias}' for user '{username}'"
            )

            update_progress(100, f"Repository '{user_alias}' activated successfully")

            return {
                "success": True,
                "message": f"Repository '{user_alias}' activated successfully",
                "user_alias": user_alias,
                "branch": branch_name,
                "activation_timestamp": activated_at,
                "details": {
                    "cloned_from": golden_repo.clone_path,
                    "current_branch": branch_name,
                    "is_default_branch": branch_name == golden_repo.default_branch,
                },
            }

        except Exception as e:
            error_msg = f"Failed to activate repository '{user_alias}' for user '{username}': {str(e)}"
            self.logger.error(error_msg)

            # Report failure through progress callback
            if progress_callback:
                progress_callback(0)  # Reset progress to indicate failure

            raise ActivatedRepoError(error_msg)

    def _do_deactivate_repository(
        self, username: str, user_alias: str
    ) -> Dict[str, Any]:
        """
        Perform actual repository deactivation (called by background job).

        Handles both single and composite repository deactivation by detecting
        repository type and routing to appropriate cleanup method.

        Args:
            username: Username requesting deactivation
            user_alias: User's alias for the repository

        Returns:
            Result dictionary with success status and message including resource cleanup details
        """
        try:
            # Load metadata to determine repository type
            user_dir = os.path.join(self.activated_repos_dir, username)
            metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

            if not os.path.exists(metadata_file):
                raise ActivatedRepoError(
                    f"Metadata file not found for repository '{user_alias}'"
                )

            with open(metadata_file, "r") as f:
                metadata = json.load(f)

            # Route to appropriate deactivation method
            if metadata.get("is_composite", False):
                return self._do_deactivate_composite(username, user_alias, metadata)
            else:
                return self._do_deactivate_single(username, user_alias, metadata)

        except Exception as e:
            error_msg = f"Failed to deactivate repository '{user_alias}' for user '{username}': {str(e)}"

            # Critical administrative logging for deactivation failures
            self.logger.error(
                "CRITICAL: Repository deactivation failed",
                extra={
                    "username": username,
                    "user_alias": user_alias,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "requires_immediate_admin_attention": True,
                    "potential_resource_leak": True,
                },
            )

            raise ActivatedRepoError(error_msg)

    def _do_deactivate_single(
        self, username: str, user_alias: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform deactivation for single repository.

        Args:
            username: Username requesting deactivation
            user_alias: User's alias for the repository
            metadata: Repository metadata dictionary

        Returns:
            Result dictionary with success status and cleanup details
        """
        cleanup_warnings = []
        resource_summary = {
            "directories_removed": 0,
            "files_removed": 0,
            "size_freed_mb": 0,
            "potential_leaks": [],
        }

        try:
            user_dir = os.path.join(self.activated_repos_dir, username)
            repo_dir = os.path.join(user_dir, user_alias)
            metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

            # Pre-deactivation resource analysis
            initial_size = 0
            file_count = 0

            if os.path.exists(repo_dir):
                try:
                    for root, dirs, files in os.walk(repo_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                file_size = os.path.getsize(file_path)
                                initial_size += file_size
                                file_count += 1
                            except (OSError, IOError):
                                cleanup_warnings.append(
                                    f"Unable to analyze file: {file_path}"
                                )
                except (OSError, IOError) as e:
                    cleanup_warnings.append(f"Directory analysis failed: {str(e)}")

            # Check for potential resource leaks before cleanup
            potential_leaks = self._detect_resource_leaks(repo_dir, user_alias)
            if potential_leaks:
                resource_summary["potential_leaks"] = potential_leaks
                cleanup_warnings.extend(
                    [f"Resource leak detected: {leak}" for leak in potential_leaks]
                )

            # Administrative logging before cleanup
            self.logger.warning(
                "Repository deactivation initiated",
                extra={
                    "username": username,
                    "user_alias": user_alias,
                    "repo_size_mb": round(initial_size / 1024 / 1024, 2),
                    "file_count": file_count,
                    "potential_leaks": len(potential_leaks),
                    "operation": "deactivation_start",
                },
            )

            # Remove repository directory with detailed tracking
            if os.path.exists(repo_dir):
                try:
                    shutil.rmtree(repo_dir)
                    resource_summary["directories_removed"] = 1
                    resource_summary["files_removed"] = file_count
                    resource_summary["size_freed_mb"] = round(
                        initial_size / 1024 / 1024, 2
                    )
                except (OSError, IOError) as e:
                    cleanup_warnings.append(
                        f"Failed to remove repository directory: {str(e)}"
                    )
                    # Log as potential resource leak
                    self.logger.error(
                        "RESOURCE LEAK WARNING: Failed to remove repository directory",
                        extra={
                            "username": username,
                            "user_alias": user_alias,
                            "directory": repo_dir,
                            "error": str(e),
                            "requires_admin_cleanup": True,
                        },
                    )

            # Remove metadata file with error handling
            if os.path.exists(metadata_file):
                try:
                    os.remove(metadata_file)
                except (OSError, IOError) as e:
                    cleanup_warnings.append(f"Failed to remove metadata file: {str(e)}")
                    # Log as administrative issue
                    self.logger.warning(
                        "Metadata cleanup issue",
                        extra={
                            "username": username,
                            "user_alias": user_alias,
                            "metadata_file": metadata_file,
                            "error": str(e),
                            "impact": "minor",
                        },
                    )

            # Post-cleanup verification
            cleanup_success = not os.path.exists(repo_dir) and not os.path.exists(
                metadata_file
            )

            if not cleanup_success:
                cleanup_warnings.append(
                    "Cleanup verification failed - some resources may remain"
                )

            # Administrative logging for successful cleanup
            self.logger.info(
                "Repository deactivation completed",
                extra={
                    "username": username,
                    "user_alias": user_alias,
                    "cleanup_success": cleanup_success,
                    "warnings_count": len(cleanup_warnings),
                    "size_freed_mb": resource_summary["size_freed_mb"],
                    "operation": "deactivation_complete",
                },
            )

            result = {
                "success": True,
                "message": f"Repository '{user_alias}' deactivated successfully",
                "user_alias": user_alias,
                "resource_summary": resource_summary,
                "cleanup_warnings": cleanup_warnings if cleanup_warnings else None,
                "administrative_notes": {
                    "cleanup_verified": cleanup_success,
                    "requires_attention": len(cleanup_warnings) > 0
                    or len(potential_leaks) > 0,
                },
            }

            # Add warnings to result if any exist
            if cleanup_warnings:
                result["warnings"] = cleanup_warnings

            return result

        except Exception as e:
            error_msg = (
                f"Failed to deactivate single repository '{user_alias}': {str(e)}"
            )
            self.logger.error(error_msg)
            raise ActivatedRepoError(error_msg)

    def _do_deactivate_composite(
        self, username: str, user_alias: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform deactivation for composite repository.

        Handles complete cleanup of composite repository including:
        - Stopping any running services
        - Removing all component repositories
        - Removing proxy configuration
        - Removing composite directory
        - Removing metadata file

        Args:
            username: Username requesting deactivation
            user_alias: User's alias for the repository
            metadata: Repository metadata dictionary

        Returns:
            Result dictionary with success status and cleanup details
        """
        cleanup_warnings = []
        components_removed = 0

        try:
            user_dir = os.path.join(self.activated_repos_dir, username)
            repo_path = Path(metadata["path"])
            metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")

            self.logger.info(
                f"Starting composite repository deactivation for '{user_alias}'"
            )

            # Step 1: Stop any running services (non-fatal if fails)
            self._stop_composite_services(repo_path)

            # Step 2: Clean up component repositories
            if repo_path.exists():
                try:
                    from ...proxy.config_manager import ProxyConfigManager

                    proxy_config = ProxyConfigManager(repo_path)
                    discovered_repos = proxy_config.get_repositories()

                    for repo_name in discovered_repos:
                        subrepo_path = repo_path / repo_name
                        if subrepo_path.exists():
                            try:
                                shutil.rmtree(subrepo_path)
                                components_removed += 1
                                self.logger.info(f"Removed component: {repo_name}")
                            except (OSError, IOError) as e:
                                cleanup_warnings.append(
                                    f"Failed to remove component '{repo_name}': {str(e)}"
                                )
                except Exception as e:
                    # Non-fatal - we'll still remove the entire directory
                    cleanup_warnings.append(f"Failed to enumerate components: {str(e)}")
                    self.logger.warning(
                        f"Component enumeration failed, will remove entire directory: {str(e)}"
                    )

            # Step 3: Remove entire composite repository directory
            # This includes .code-indexer config and any remaining components
            if repo_path.exists():
                try:
                    shutil.rmtree(repo_path)
                    self.logger.info(
                        f"Removed composite repository directory: {repo_path}"
                    )
                except (OSError, IOError) as e:
                    cleanup_warnings.append(
                        f"Failed to remove composite directory: {str(e)}"
                    )
                    self.logger.error(
                        "RESOURCE LEAK WARNING: Failed to remove composite directory",
                        extra={
                            "username": username,
                            "user_alias": user_alias,
                            "directory": str(repo_path),
                            "error": str(e),
                            "requires_admin_cleanup": True,
                        },
                    )

            # Step 4: Remove metadata file
            if os.path.exists(metadata_file):
                try:
                    os.remove(metadata_file)
                    self.logger.info(f"Removed metadata file: {metadata_file}")
                except (OSError, IOError) as e:
                    cleanup_warnings.append(f"Failed to remove metadata file: {str(e)}")
                    self.logger.warning(
                        "Metadata cleanup issue",
                        extra={
                            "username": username,
                            "user_alias": user_alias,
                            "metadata_file": metadata_file,
                            "error": str(e),
                            "impact": "minor",
                        },
                    )

            # Post-cleanup verification
            cleanup_success = not repo_path.exists() and not os.path.exists(
                metadata_file
            )

            if not cleanup_success:
                cleanup_warnings.append(
                    "Cleanup verification failed - some resources may remain"
                )

            self.logger.info(
                f"Composite repository '{user_alias}' deactivated successfully"
            )

            result = {
                "success": True,
                "message": f"Composite repository '{user_alias}' deactivated successfully",
                "user_alias": user_alias,
                "is_composite": True,
                "components_removed": components_removed,
                "cleanup_warnings": cleanup_warnings if cleanup_warnings else None,
                "administrative_notes": {
                    "cleanup_verified": cleanup_success,
                    "requires_attention": len(cleanup_warnings) > 0,
                },
            }

            if cleanup_warnings:
                result["warnings"] = cleanup_warnings

            return result

        except Exception as e:
            error_msg = (
                f"Failed to deactivate composite repository '{user_alias}': {str(e)}"
            )
            self.logger.error(error_msg)
            raise ActivatedRepoError(error_msg)

    def _stop_composite_services(self, repo_path: Path) -> None:
        """
        Stop any services running for composite repository.

        Attempts to stop containers gracefully. This is non-fatal - if services
        aren't running or stop fails, deactivation continues.

        Args:
            repo_path: Path to composite repository
        """
        try:
            self.logger.debug(f"Attempting to stop services for {repo_path}")

            # Check if .code-indexer directory exists (has configuration)
            config_dir = repo_path / ".code-indexer"
            if not config_dir.exists():
                self.logger.debug("No .code-indexer directory, skipping service stop")
                return

            # Attempt to stop services using cidx stop command
            # This is the safest way to ensure containers are properly stopped
            result = subprocess.run(
                ["cidx", "stop"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                self.logger.info(
                    f"Successfully stopped services for composite repository at {repo_path}"
                )
            else:
                # Non-fatal - services might not be running
                self.logger.debug(
                    f"Service stop returned non-zero exit code (likely not running): {result.stderr}"
                )

        except subprocess.TimeoutExpired:
            # Non-fatal - continue with cleanup
            self.logger.warning(
                f"Timeout while stopping services for {repo_path}, continuing with cleanup"
            )
        except FileNotFoundError:
            # cidx command not found - non-fatal
            self.logger.debug("cidx command not found, skipping service stop")
        except Exception as e:
            # Non-fatal - services might not be running
            self.logger.debug(f"Service stop attempted but failed: {str(e)}")

    def _detect_resource_leaks(self, repo_dir: str, user_alias: str) -> List[str]:
        """
        Detect potential resource leaks before repository cleanup.

        Args:
            repo_dir: Repository directory path
            user_alias: User alias for the repository

        Returns:
            List of potential resource leak descriptions
        """
        leaks: List[str] = []

        if not os.path.exists(repo_dir):
            return leaks

        try:
            # Check for large .git directories that might indicate incomplete cleanup
            git_dir = os.path.join(repo_dir, ".git")
            if os.path.exists(git_dir):
                git_size = 0
                for root, dirs, files in os.walk(git_dir):
                    for file in files:
                        try:
                            git_size += os.path.getsize(os.path.join(root, file))
                        except (OSError, IOError):
                            pass

                # Flag if .git directory is unusually large (>100MB)
                if git_size > 100 * 1024 * 1024:
                    leaks.append(
                        f"Large .git directory ({git_size // 1024 // 1024}MB) - may indicate repository bloat"
                    )

            # Check for lock files that might indicate incomplete operations
            for root, dirs, files in os.walk(repo_dir):
                for file in files:
                    if file.endswith((".lock", ".tmp")) or file.startswith("~"):
                        leaks.append(
                            f"Temporary file detected: {os.path.join(root, file)}"
                        )

            # Check for very large files that might be accidentally committed
            for root, dirs, files in os.walk(repo_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        # Flag files larger than 50MB
                        if file_size > 50 * 1024 * 1024:
                            leaks.append(
                                f"Large file ({file_size // 1024 // 1024}MB): {file_path}"
                            )
                    except (OSError, IOError):
                        pass

        except Exception as e:
            leaks.append(f"Resource leak detection failed: {str(e)}")

        return leaks

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

    def find_by_canonical_url(self, canonical_url: str) -> List[Dict[str, Any]]:
        """
        Find activated repositories by canonical git URL.

        Args:
            canonical_url: Canonical form of git URL (e.g., "github.com/user/repo")

        Returns:
            List of matching activated repository dictionaries
        """
        from ..services.git_url_normalizer import GitUrlNormalizer

        normalizer = GitUrlNormalizer()
        matching_repos: List[Dict[str, Any]] = []

        # Get all users who have activated repositories
        if not os.path.exists(self.activated_repos_dir):
            return matching_repos

        for user_dir_name in os.listdir(self.activated_repos_dir):
            user_repos_dir = os.path.join(self.activated_repos_dir, user_dir_name)
            if not os.path.isdir(user_repos_dir):
                continue

            # List activated repositories for this user
            user_repos = self.list_activated_repositories(user_dir_name)

            for repo_data in user_repos:
                try:
                    golden_repo_alias = repo_data.get("golden_repo_alias")
                    if not golden_repo_alias:
                        continue

                    # Get the golden repository URL from the golden repo manager
                    golden_repo = self.golden_repo_manager.golden_repos.get(
                        golden_repo_alias
                    )
                    if not golden_repo:
                        continue

                    # Normalize the golden repository's URL
                    normalized = normalizer.normalize(golden_repo.repo_url)

                    # Check if it matches the target canonical URL
                    if normalized.canonical_form == canonical_url:
                        # Add canonical URL and branch information
                        repo_dict_any = dict(repo_data)  # Convert to Dict[str, Any]
                        repo_dict_any["canonical_url"] = canonical_url
                        repo_dict_any["git_url"] = golden_repo.repo_url

                        # Get branch information from the activated repository
                        repo_path = self.get_activated_repo_path(
                            user_dir_name, golden_repo_alias
                        )
                        repo_dict_any["branches"] = self._get_repository_branches(
                            repo_path
                        )

                        matching_repos.append(repo_dict_any)

                except Exception as e:
                    self.logger.warning(
                        f"Failed to normalize URL for activated repo {user_dir_name}/{golden_repo_alias}: {str(e)}"
                    )
                    continue

        return matching_repos

    def _get_repository_branches(self, repo_path: str) -> List[str]:
        """
        Get list of branches for a repository.

        Args:
            repo_path: Path to the repository

        Returns:
            List of branch names
        """
        try:
            if not os.path.exists(repo_path):
                return ["main"]  # Default fallback

            # Get all branches (local and remote)
            result = subprocess.run(
                ["git", "branch", "-a"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                branches = []
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        # Clean up branch name (remove prefixes and current marker)
                        branch = line.strip().replace("*", "").strip()

                        # Skip remote tracking references in favor of clean names
                        if branch.startswith("remotes/origin/"):
                            branch = branch.replace("remotes/origin/", "")

                        if (
                            branch
                            and branch not in ["HEAD", "HEAD -> origin/main"]
                            and not branch.startswith("remotes/")
                        ):
                            if branch not in branches:  # Avoid duplicates
                                branches.append(branch)

                return branches if branches else ["main"]
            else:
                return ["main"]

        except Exception as e:
            self.logger.warning(f"Failed to get branches for {repo_path}: {str(e)}")
            return ["main"]

    def _create_repo_config(self, repo_path: str) -> None:
        """
        Create .code-indexer/config.json for activated repository.

        Creates configuration with FilesystemVectorStore and VoyageAI settings
        to ensure search works correctly in server mode (Issue #499).

        Args:
            repo_path: Path to the activated repository

        Raises:
            ActivatedRepoError: If config creation fails
        """
        try:
            config_dir = Path(repo_path) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)

            # Create config with FilesystemVectorStore and VoyageAI
            config_data = {
                "vector_store": {
                    "provider": "filesystem"
                },
                "embedding_provider": "voyage-ai",
                "voyage_ai": {
                    "model": "voyage-code-3"
                }
            }

            config_path = config_dir / "config.json"
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)

            self.logger.info(
                f"Created .code-indexer/config.json with FilesystemVectorStore for {repo_path}"
            )

        except Exception as e:
            raise ActivatedRepoError(
                f"Failed to create .code-indexer/config.json: {str(e)}"
            )

    def _update_composite_config(self, composite_path: Path) -> None:
        """
        Update composite repository config with FilesystemVectorStore and VoyageAI.

        ProxyInitializer creates config.json with proxy_mode settings, but we need
        to add vector_store and embedding_provider settings for Issue #499.

        Args:
            composite_path: Path to the composite repository

        Raises:
            ActivatedRepoError: If config update fails
        """
        try:
            config_file = composite_path / ".code-indexer" / "config.json"

            if not config_file.exists():
                raise ActivatedRepoError(
                    f"Config file not found at {config_file}. ProxyInitializer should have created it."
                )

            # Read existing config
            with open(config_file, 'r') as f:
                config_data = json.load(f)

            # Add FilesystemVectorStore and VoyageAI settings
            config_data["vector_store"] = {
                "provider": "filesystem"
            }
            config_data["embedding_provider"] = "voyage-ai"
            config_data["voyage_ai"] = {
                "model": "voyage-code-3"
            }

            # Write updated config
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)

            self.logger.info(
                f"Updated composite config with FilesystemVectorStore for {composite_path}"
            )

        except Exception as e:
            raise ActivatedRepoError(
                f"Failed to update composite repository config: {str(e)}"
            )
