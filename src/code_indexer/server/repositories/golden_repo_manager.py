"""
Golden Repository Manager for CIDX Server.

Manages golden repositories that can be activated by users for semantic search.
Golden repositories are stored in ~/.cidx-server/data/golden-repos/ with metadata tracking.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import errno
import json
import os
import shutil
import subprocess
import logging
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from code_indexer.server.models.golden_repo_branch_models import (
        GoldenRepoBranchInfo,
    )
    from code_indexer.server.utils.config_manager import ServerResourceConfig
    from code_indexer.server.services.background_job_manager import BackgroundJobManager
    from code_indexer.server.repositories.activated_repo_manager import (
        ActivatedRepoManager,
    )

from pydantic import BaseModel


class GoldenRepoError(Exception):
    """Base exception for golden repository operations."""

    pass


class GitOperationError(GoldenRepoError):
    """Exception raised when git operations fail."""

    pass


class GoldenRepoNotFoundError(GoldenRepoError):
    """Exception raised when golden repository cannot be found on filesystem."""

    pass


class GoldenRepo(BaseModel):
    """Model representing a golden repository."""

    alias: str
    repo_url: str
    default_branch: str
    clone_path: str
    created_at: str
    enable_temporal: bool = False
    temporal_options: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert golden repository to dictionary."""
        return {
            "alias": self.alias,
            "repo_url": self.repo_url,
            "default_branch": self.default_branch,
            "clone_path": self.clone_path,
            "created_at": self.created_at,
            "enable_temporal": self.enable_temporal,
            "temporal_options": self.temporal_options,
        }


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class GoldenRepoManager:
    """
    Manages golden repositories for the CIDX server.

    Golden repositories are admin-managed, globally unique namespaced repositories
    that support git operations with Copy-on-Write (CoW) cloning.
    """

    # Dynamically injected by app.py at runtime
    background_job_manager: "BackgroundJobManager"
    activated_repo_manager: "ActivatedRepoManager"

    def __init__(
        self,
        data_dir: str,
        resource_config: Optional["ServerResourceConfig"] = None,
    ):
        """
        Initialize golden repository manager.

        Args:
            data_dir: Data directory path (REQUIRED - no default)
            resource_config: Resource configuration (timeouts, limits)

        Raises:
            ValueError: If data_dir is None or empty
        """
        if not data_dir or not data_dir.strip():
            raise ValueError("data_dir is required and cannot be None or empty")

        self.data_dir = data_dir
        self.golden_repos_dir = os.path.join(self.data_dir, "golden-repos")
        self.metadata_file = os.path.join(self.golden_repos_dir, "metadata.json")

        # Resource configuration (import here to avoid circular dependency)
        if resource_config is None:
            from code_indexer.server.utils.config_manager import ServerResourceConfig

            resource_config = ServerResourceConfig()
        self.resource_config = resource_config

        # Ensure directory structure exists
        os.makedirs(self.golden_repos_dir, exist_ok=True)

        # Thread safety for concurrent operations (Story #620 Priority 2A)
        self._operation_lock = threading.Lock()

        # Storage for golden repositories
        self.golden_repos: Dict[str, GoldenRepo] = {}

        # Load existing metadata
        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load golden repository metadata from file.

        Thread-safe: Uses _operation_lock to prevent concurrent access (Story #620 Priority 2A).
        """
        with self._operation_lock:
            if os.path.exists(self.metadata_file):
                try:
                    with open(self.metadata_file, "r") as f:
                        data = json.load(f)
                        for alias, repo_data in data.items():
                            self.golden_repos[alias] = GoldenRepo(**repo_data)
                except (json.JSONDecodeError, TypeError, KeyError):
                    # If metadata file is corrupted, start fresh
                    self.golden_repos = {}
            else:
                # Create empty metadata file
                # NOTE: Cannot call _save_metadata() here as it also acquires _operation_lock,
                # which would cause deadlock (threading.Lock is NOT reentrant). Inline the save logic.
                self.golden_repos = {}
                data = {}
                with open(self.metadata_file, "w") as f:
                    json.dump(data, f, indent=2)

    def _save_metadata(self) -> None:
        """Save golden repository metadata to file.

        Thread-safe: Uses _operation_lock to prevent concurrent access (Story #620 Priority 2A).
        """
        with self._operation_lock:
            data = {}
            for alias, repo in self.golden_repos.items():
                data[alias] = repo.to_dict()

            with open(self.metadata_file, "w") as f:
                json.dump(data, f, indent=2)

    def add_golden_repo(
        self,
        repo_url: str,
        alias: str,
        default_branch: str = "main",
        description: Optional[str] = None,
        enable_temporal: bool = False,
        temporal_options: Optional[Dict] = None,
        submitter_username: str = "admin",
    ) -> str:
        """
        Add a golden repository.

        This method submits a background job and returns immediately with a job_id.
        Use BackgroundJobManager to track progress and results.

        Args:
            repo_url: Git repository URL
            alias: Unique alias for the repository
            default_branch: Default branch to clone (default: main)
            description: Optional description for the repository
            enable_temporal: Enable temporal git history indexing
            temporal_options: Temporal indexing configuration options
            submitter_username: Username of the user submitting the job (default: "admin")

        Returns:
            Job ID for tracking add operation progress

        Raises:
            ValueError: If alias contains path traversal characters
            GoldenRepoError: If alias already exists
            GitOperationError: If git repository is invalid or inaccessible
        """
        # SECURITY: Validate alias BEFORE any operations (defense-in-depth)
        # Reject path traversal characters to prevent escaping golden repos directory
        if ".." in alias:
            raise ValueError(
                f"Invalid alias '{alias}': cannot contain path traversal characters (..)"
            )
        if "/" in alias:
            raise ValueError(
                f"Invalid alias '{alias}': cannot contain path traversal characters (/)"
            )
        if "\\" in alias:
            raise ValueError(
                f"Invalid alias '{alias}': cannot contain path traversal characters (\\)"
            )

        # Validate BEFORE submitting job
        if alias in self.golden_repos:
            raise GoldenRepoError(f"Golden repository alias '{alias}' already exists")

        # Skip git validation for local:// URLs (Story #538)
        if not repo_url.startswith("local://"):
            if not self._validate_git_repository(repo_url):
                raise GitOperationError(
                    f"Invalid or inaccessible git repository: {repo_url}"
                )

        # Create no-args wrapper for background execution
        def background_worker() -> Dict[str, Any]:
            """Execute add operation in background thread."""
            try:
                # Clone repository
                clone_path = self._clone_repository(repo_url, alias, default_branch)

                # Execute post-clone workflow
                self._execute_post_clone_workflow(
                    clone_path,
                    force_init=False,
                    enable_temporal=enable_temporal,
                    temporal_options=temporal_options,
                )

                # Create golden repository record
                created_at = datetime.now(timezone.utc).isoformat()
                golden_repo = GoldenRepo(
                    alias=alias,
                    repo_url=repo_url,
                    default_branch=default_branch,
                    clone_path=clone_path,
                    created_at=created_at,
                    enable_temporal=enable_temporal,
                    temporal_options=temporal_options,
                )

                # Store and persist
                self.golden_repos[alias] = golden_repo
                self._save_metadata()

                # Automatic global activation (AC1 from Story #521)
                # This is a non-blocking post-registration step (AC4)
                try:
                    from code_indexer.global_repos.global_activation import (
                        GlobalActivator,
                    )

                    global_activator = GlobalActivator(self.golden_repos_dir)
                    global_activator.activate_golden_repo(
                        repo_name=alias,
                        repo_url=repo_url,
                        clone_path=clone_path,
                        enable_temporal=enable_temporal,
                        temporal_options=temporal_options,
                    )
                    logging.info(
                        f"Golden repository '{alias}' automatically activated globally as '{alias}-global'"
                    )
                except Exception as activation_error:
                    # Log error but don't fail the golden repo registration (AC4)
                    logging.error(
                        f"Global activation failed for '{alias}': {activation_error}. "
                        f"Golden repository is registered but not globally accessible. "
                        f"Manual global activation can be retried later."
                    )
                    # Continue with successful registration response

                # Lifecycle hook: Create .md file in cidx-meta (Story #538)
                try:
                    from code_indexer.global_repos.meta_description_hook import (
                        on_repo_added,
                    )

                    on_repo_added(
                        repo_name=alias,
                        repo_url=repo_url,
                        clone_path=clone_path,
                        golden_repos_dir=self.golden_repos_dir,
                    )
                except Exception as hook_error:
                    # Log error but don't fail the golden repo registration
                    logging.error(
                        f"Meta description hook failed for '{alias}': {hook_error}. "
                        f"Golden repository added but meta description not created."
                    )

                return {
                    "success": True,
                    "alias": alias,
                    "message": f"Golden repository '{alias}' added successfully",
                }

            except subprocess.CalledProcessError as e:
                raise GitOperationError(
                    f"Failed to clone repository: Git process failed with exit code {e.returncode}: {e.stderr}"
                )
            except subprocess.TimeoutExpired as e:
                raise GitOperationError(
                    f"Failed to clone repository: Git operation timed out after {e.timeout} seconds"
                )
            except (OSError, IOError) as e:
                raise GitOperationError(
                    f"Failed to clone repository: File system error: {str(e)}"
                )
            except GitOperationError:
                # Re-raise GitOperationError from sub-methods without modification
                raise

        # Submit to BackgroundJobManager
        job_id = self.background_job_manager.submit_job(
            operation_type="add_golden_repo",
            func=background_worker,
            submitter_username=submitter_username,
            is_admin=True,
            repo_alias=alias,  # AC5: Fix unknown repo bug
        )
        return cast(str, job_id)

    def list_golden_repos(self) -> List[Dict[str, str]]:
        """
        List all golden repositories.

        Returns:
            List of golden repository dictionaries
        """
        return [repo.to_dict() for repo in self.golden_repos.values()]

    def remove_golden_repo(self, alias: str, submitter_username: str = "admin") -> str:
        """
        Remove a golden repository.

        This method submits a background job and returns immediately with a job_id.
        Use BackgroundJobManager to track progress and results.

        Args:
            alias: Alias of the repository to remove
            submitter_username: Username of the user submitting the job (default: "admin")

        Returns:
            Job ID for tracking removal progress

        Raises:
            GoldenRepoError: If repository not found
        """
        # Validate repository exists BEFORE submitting job
        if alias not in self.golden_repos:
            raise GoldenRepoError(f"Golden repository '{alias}' not found")

        # Create no-args wrapper for background execution
        def background_worker() -> Dict[str, Any]:
            """Execute removal in background thread."""
            # Initialize cascade results tracking
            cascade_results: Dict[str, Any] = {
                "activated_repos_deleted": [],
                "activated_repos_failed": [],
                "global_alias_deleted": False,
                "golden_repo_deleted": False,
            }

            # Step 1: Cascade delete all activated repos
            if hasattr(self, "activated_repo_manager") and self.activated_repo_manager:
                try:
                    activated_repos = (
                        self.activated_repo_manager.find_repos_by_golden_alias(alias)
                    )

                    for repo_info in activated_repos:
                        username = repo_info["username"]
                        user_alias = repo_info["user_alias"]

                        try:
                            # Direct deletion (not background job) for cascade
                            self.activated_repo_manager._do_deactivate_repository(
                                username=username,
                                user_alias=user_alias,
                            )
                            cascade_results["activated_repos_deleted"].append(
                                f"{username}/{user_alias}"
                            )
                            logging.info(
                                f"Cascade deleted activated repo: {username}/{user_alias}"
                            )
                        except Exception as e:
                            cascade_results["activated_repos_failed"].append(
                                {
                                    "repo": f"{username}/{user_alias}",
                                    "error": str(e),
                                }
                            )
                            logging.error(
                                f"Failed to cascade delete {username}/{user_alias}: {e}"
                            )

                except Exception as e:
                    logging.error(
                        f"Failed to find activated repos for cascade deletion: {e}"
                    )

            # Get repository info before removal
            golden_repo = self.golden_repos[alias]

            # Perform cleanup BEFORE removing from memory
            # Use canonical path resolution to handle versioned structure repos
            try:
                actual_path = self.get_actual_repo_path(alias)
                cleanup_successful = self._cleanup_repository_files(actual_path)
            except GoldenRepoNotFoundError:
                # If repository doesn't exist on filesystem, nothing to clean up
                # This can happen in test scenarios or if repo was manually deleted
                logging.info(
                    f"Repository '{alias}' not found on filesystem during removal - skipping cleanup"
                )
                cleanup_successful = True
            except GitOperationError as cleanup_error:
                # Critical cleanup failures should prevent deletion
                logging.error(
                    f"Critical cleanup failure prevents repository deletion: {cleanup_error}"
                )
                raise  # Re-raise to prevent deletion

            # Only remove from storage after cleanup is complete
            del self.golden_repos[alias]

            try:
                self._save_metadata()
            except Exception as save_error:
                # If metadata save fails, rollback the deletion
                logging.error(
                    f"Failed to save metadata after deletion, rolling back: {save_error}"
                )
                self.golden_repos[alias] = golden_repo  # Restore repository
                raise GitOperationError(
                    f"Repository deletion rollback due to metadata save failure: {save_error}"
                )

            # ANTI-FALLBACK RULE: Fail operation when cleanup is incomplete
            # Per MESSI Rule 2: "Graceful failure over forced success"
            # Don't report "success with warnings" - either succeed or fail clearly
            if cleanup_successful:
                # Deactivate global activation (Story #532)
                # Remove GlobalRegistry entry, alias pointer file, meta-directory .md file
                try:
                    from code_indexer.global_repos.global_activation import (
                        GlobalActivator,
                    )

                    global_activator = GlobalActivator(self.golden_repos_dir)
                    global_activator.deactivate_golden_repo(alias)
                    logging.info(f"Golden repository '{alias}' deactivated globally")
                    cascade_results["global_alias_deleted"] = True
                except Exception as deactivation_error:
                    # Log error but don't fail removal - the repo files are already deleted
                    # This is consistent with add_golden_repo() behavior (AC4)
                    logging.error(
                        f"Global deactivation failed for '{alias}': {deactivation_error}. "
                        f"Golden repository removed but some global resources may remain."
                    )

                # Lifecycle hook: Delete .md file from cidx-meta (Story #538)
                try:
                    from code_indexer.global_repos.meta_description_hook import (
                        on_repo_removed,
                    )

                    on_repo_removed(
                        repo_name=alias, golden_repos_dir=self.golden_repos_dir
                    )
                except Exception as hook_error:
                    # Log error but don't fail removal - the repo is already removed
                    logging.error(
                        f"Meta description hook failed for '{alias}': {hook_error}. "
                        f"Golden repository removed but meta description not deleted."
                    )

                # Mark golden repo as deleted
                cascade_results["golden_repo_deleted"] = True

                # Build enhanced message with cascade deletion counts
                activated_count = len(cascade_results["activated_repos_deleted"])
                failed_count = len(cascade_results["activated_repos_failed"])

                message = f"Golden repository '{alias}' removed successfully"
                if activated_count > 0:
                    message += f" (cascade deleted {activated_count} activated repos)"
                if failed_count > 0:
                    message += (
                        f" (WARNING: {failed_count} activated repos failed to delete)"
                    )

                return {
                    "success": True,
                    "alias": alias,
                    "message": message,
                    "cascade_results": cascade_results,
                }
            else:
                # FAIL the operation - don't mask cleanup failures
                raise GitOperationError(
                    "Repository metadata removed but cleanup incomplete. "
                    "Resource leak detected: some cleanup operations did not complete fully."
                )

        # Submit to BackgroundJobManager
        job_id = self.background_job_manager.submit_job(
            operation_type="remove_golden_repo",
            func=background_worker,
            submitter_username=submitter_username,
            is_admin=True,
            repo_alias=alias,  # AC5: Fix unknown repo bug
        )
        return cast(str, job_id)

    def _validate_git_repository(self, repo_url: str) -> bool:
        """
        Validate that a git repository URL is accessible.

        Args:
            repo_url: Git repository URL to validate

        Returns:
            True if repository is valid and accessible, False otherwise
        """
        try:
            # Use git ls-remote to check if repository is accessible
            result = subprocess.run(
                ["git", "ls-remote", repo_url],
                capture_output=True,
                text=True,
                timeout=self.resource_config.git_clone_timeout,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False

    def _clone_repository(self, repo_url: str, alias: str, branch: str) -> str:
        """
        Clone a git repository to the golden repos directory.

        Golden repository registration should always use regular copying/cloning,
        NOT Copy-on-Write (CoW) cloning, as it may involve cross-device operations.

        Args:
            repo_url: Git repository URL
            alias: Repository alias for directory name
            branch: Branch to clone

        Returns:
            Path to cloned repository

        Raises:
            GitOperationError: If cloning fails
        """
        clone_path = os.path.join(self.golden_repos_dir, alias)

        # For local repositories, use regular copying (NO CoW for golden repo registration)
        if self._is_local_path(repo_url):
            return self._clone_local_repository_with_regular_copy(repo_url, clone_path)

        # For remote repositories, use regular git clone
        return self._clone_remote_repository(repo_url, clone_path, branch)

    def _is_local_path(self, repo_url: str) -> bool:
        """
        Check if the repository URL is a local filesystem path.

        Args:
            repo_url: Repository URL to check

        Returns:
            True if it's a local path, False if remote
        """
        return (
            repo_url.startswith("/")
            or repo_url.startswith("file://")
            or repo_url.startswith("local://")
        )

    def _clone_local_repository_with_regular_copy(
        self, repo_url: str, clone_path: str
    ) -> str:
        """
        Clone a local repository using regular copying (NO CoW).

        This method is used for golden repository registration to avoid
        cross-device link issues when copying from arbitrary local paths
        (like /tmp) to the golden repository storage directory.

        Args:
            repo_url: Local repository path
            clone_path: Destination path

        Returns:
            Path to cloned repository

        Raises:
            GitOperationError: If cloning fails
        """
        # Normalize file:// and local:// URLs
        if repo_url.startswith("file://"):
            source_path = repo_url.replace("file://", "")
        elif repo_url.startswith("local://"):
            # local://cidx-meta -> Use the target directory directly (no source to copy)
            # The directory should already exist (created by bootstrap_cidx_meta)
            source_path = None
        else:
            source_path = repo_url

        try:
            # For local:// URLs, the directory should already exist (no copy needed)
            if source_path is None:
                if not os.path.exists(clone_path):
                    raise GitOperationError(
                        f"Local repository directory does not exist: {clone_path}"
                    )
                logging.info(
                    f"Using existing local directory for {repo_url}: {clone_path}"
                )
                return clone_path

            # Always use regular copy for golden repository registration
            # This avoids cross-device link issues that occur with CoW cloning
            shutil.copytree(source_path, clone_path, symlinks=True)
            logging.info(
                f"Golden repository registered using regular copy: {source_path} -> {clone_path}"
            )
            return clone_path
        except FileNotFoundError as e:
            raise GitOperationError(
                f"Failed to copy local repository: Source directory not found: {str(e)}"
            )
        except PermissionError as e:
            raise GitOperationError(
                f"Failed to copy local repository: Permission denied: {str(e)}"
            )
        except OSError as e:
            raise GitOperationError(
                f"Failed to copy local repository: File system error: {str(e)}"
            )
        except shutil.Error as e:
            raise GitOperationError(
                f"Failed to copy local repository: Copy operation failed: {str(e)}"
            )

    def _clone_remote_repository(
        self, repo_url: str, clone_path: str, branch: str
    ) -> str:
        """
        Clone a remote git repository using git clone.

        Args:
            repo_url: Remote git repository URL
            clone_path: Destination path
            branch: Branch to clone

        Returns:
            Path to cloned repository

        Raises:
            GitOperationError: If cloning fails
        """
        try:
            # Clone full repository with complete history for semantic search
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "--branch",
                    branch,
                    repo_url,
                    clone_path,
                ],
                capture_output=True,
                text=True,
                timeout=self.resource_config.git_pull_timeout,
            )

            if result.returncode != 0:
                raise GitOperationError(
                    f"Git clone failed with code {result.returncode}: {result.stderr}"
                )

            return clone_path

        except subprocess.TimeoutExpired:
            raise GitOperationError("Git clone operation timed out")
        except subprocess.SubprocessError as e:
            raise GitOperationError(f"Git clone subprocess error: {str(e)}")

    def _cleanup_repository_files(self, clone_path: str) -> bool:
        """
        Clean up repository files and directories using orchestrated cleanup.

        Uses the same approach as 'cidx uninstall' to properly handle root-owned files
        created by previous infrastructure (removed in v8.0).

        Args:
            clone_path: Path to repository directory to clean up

        Returns:
            bool: True if cleanup was successful, False if there were issues
                  (but the repository deletion can still be considered successful)

        Raises:
            GitOperationError: Only for critical failures that should prevent deletion
        """
        if not os.path.exists(clone_path):
            return True  # Already cleaned up

        try:
            from pathlib import Path

            clone_path_obj = Path(clone_path)
            project_config_dir = clone_path_obj / ".code-indexer"
            overall_cleanup_successful = True

            # Phase 1: Docker cleanup if project has cidx services
            if project_config_dir.exists():
                docker_success = self._perform_docker_cleanup(
                    clone_path, project_config_dir
                )
                if not docker_success:
                    overall_cleanup_successful = False

            # Phase 2: Final filesystem cleanup
            filesystem_success = self._cleanup_filesystem(clone_path_obj)
            if filesystem_success is None:
                return overall_cleanup_successful  # Directory already removed
            return filesystem_success and overall_cleanup_successful

        except (
            ImportError,
            PermissionError,
            OSError,
            subprocess.CalledProcessError,
            RuntimeError,
        ) as e:
            return self._handle_cleanup_errors(e, clone_path)

    def _perform_docker_cleanup(
        self, clone_path: str, project_config_dir: Path
    ) -> bool:
        """
        Docker cleanup is no longer performed (Story #506: container management deprecated).

        Container-based backends are deprecated. Repositories should use filesystem backend.
        This method now returns True to allow cleanup to proceed.

        Args:
            clone_path: Path to repository directory
            project_config_dir: Path to .code-indexer config directory

        Returns:
            bool: Always returns True (no-op)

        Raises:
            GitOperationError: Not raised (legacy compatibility)
        """
        logging.info(
            f"Docker cleanup skipped for {clone_path} (container management deprecated)"
        )
        return True

    def _cleanup_filesystem(self, clone_path_obj: Path) -> Optional[bool]:
        """
        Clean up remaining filesystem structure after Docker cleanup.

        Args:
            clone_path_obj: Path object for repository directory

        Returns:
            bool: True if successful, False if issues occurred
            None: If directory already removed
        """
        if not clone_path_obj.exists():
            return None  # Directory already removed

        try:
            shutil.rmtree(str(clone_path_obj))
            logging.info(f"Successfully cleaned up repository files: {clone_path_obj}")
            return True
        except (PermissionError, OSError) as fs_error:
            # File system cleanup failed - log but don't prevent deletion
            logging.warning(
                f"File system cleanup incomplete for {clone_path_obj}: "
                f"{type(fs_error).__name__}: {fs_error}. "
                "Some files may remain but repository deletion was successful."
            )
            return False

    def _handle_cleanup_errors(self, error: Exception, clone_path: str) -> bool:
        """
        Handle specific cleanup errors with appropriate logging and error translation.

        Args:
            error: The exception that occurred during cleanup
            clone_path: Path to repository being cleaned

        Returns:
            bool: For non-critical errors that allow deletion to proceed

        Raises:
            GitOperationError: For critical failures that should prevent deletion
        """
        if isinstance(error, ImportError):
            # Import errors during cleanup are no longer critical (container management deprecated)
            logging.warning(
                f"Import error during cleanup of {clone_path} (non-critical): {error}"
            )
            return True  # Non-critical, allow cleanup to proceed
        elif isinstance(error, PermissionError):
            logging.error(
                f"Permission denied during cleanup of {clone_path}: "
                f"Insufficient access to: {error.filename or 'unknown file'}"
            )
            raise GitOperationError(
                f"Insufficient permissions for cleanup: {str(error)}"
            )
        elif isinstance(error, OSError):
            if error.errno == errno.ENOENT:  # File not found
                return True  # Already cleaned
            elif error.errno == errno.EACCES:  # Permission denied
                logging.error(
                    f"Access denied during cleanup of {clone_path}: "
                    f"Cannot access: {error.filename or 'unknown file'}"
                )
                raise GitOperationError(f"Access denied for cleanup: {str(error)}")
            else:
                logging.error(
                    f"OS error during cleanup of {clone_path}: "
                    f"Error {error.errno}: {error}"
                )
                raise GitOperationError(
                    f"File system error during cleanup: {str(error)}"
                )
        elif isinstance(error, subprocess.CalledProcessError):
            if error.returncode == 126:  # Permission denied
                logging.error(
                    f"Command permission error during cleanup of {clone_path}: "
                    f"Command: {' '.join(error.cmd) if error.cmd else 'unknown'}"
                )
                raise GitOperationError(f"Command permission denied: {str(error)}")
            else:
                logging.error(
                    f"Process error during cleanup of {clone_path}: "
                    f"Command failed with exit code {error.returncode}"
                )
                raise GitOperationError(
                    f"Process failed with exit code {error.returncode}: {str(error)}"
                )
        elif isinstance(error, RuntimeError):
            # Critical system errors that prevent cleanup
            logging.error(
                f"Critical system error during cleanup of {clone_path}: {error}"
            )
            raise GitOperationError(f"Critical cleanup failure: {str(error)}")
        else:
            # Shouldn't reach here, but handle unexpected errors
            logging.error(
                f"Unexpected error during cleanup of {clone_path}: "
                f"{type(error).__name__}: {error}"
            )
            raise GitOperationError(f"Unexpected cleanup failure: {str(error)}")

    def _execute_post_clone_workflow(
        self,
        clone_path: str,
        force_init: bool = False,
        enable_temporal: bool = False,
        temporal_options: Optional[Dict] = None,
    ) -> None:
        """
        Execute the required workflow after successful repository cloning.

        The workflow includes:
        1. cidx init with voyage-ai embedding provider (with optional --force for refresh)
        2. cidx index (with optional temporal indexing parameters)

        Note: FilesystemVectorStore is container-free, so no start/stop/status commands needed.

        Args:
            clone_path: Path to the cloned repository
            force_init: Whether to use --force flag with cidx init (for refresh operations)
            enable_temporal: Whether to enable temporal indexing (git history)
            temporal_options: Optional temporal indexing parameters (time_range, include/exclude paths, diff_context)

        Raises:
            GitOperationError: If any workflow step fails
        """
        logging.info(
            f"Executing post-clone workflow for {clone_path} (force_init={force_init})"
        )

        # Build init command with optional --force flag
        init_command = ["cidx", "init", "--embedding-provider", "voyage-ai"]
        if force_init:
            init_command.append("--force")

        # Build index command for semantic + FTS (always required)
        index_command = ["cidx", "index", "--fts"]

        # Build workflow commands list
        workflow_commands = [
            init_command,
            index_command,
        ]

        # If temporal indexing is enabled, add a SEPARATE command for temporal index
        # Note: --index-commits ONLY does temporal indexing, not semantic+FTS
        # So we need two separate cidx index calls: one for semantic+FTS, one for temporal
        if enable_temporal:
            temporal_command = ["cidx", "index", "--index-commits"]

            if temporal_options:
                if temporal_options.get("max_commits"):
                    temporal_command.extend(
                        ["--max-commits", str(temporal_options["max_commits"])]
                    )

                if temporal_options.get("since_date"):
                    temporal_command.extend(
                        ["--since-date", temporal_options["since_date"]]
                    )

                # Add diff-context parameter (default: 5 from model)
                diff_context = temporal_options.get("diff_context", 5)
                temporal_command.extend(["--diff-context", str(diff_context)])

                # Log warning for large context values
                if diff_context > 20:
                    logging.warning(
                        f"Large diff context ({diff_context} lines) will significantly "
                        f"increase storage. Recommended range: 3-10 lines."
                    )

            workflow_commands.append(temporal_command)

        try:
            for i, command in enumerate(workflow_commands, 1):
                logging.info(
                    f"Executing workflow step {i}/{len(workflow_commands)}: {' '.join(command)}"
                )

                result = subprocess.run(
                    command,
                    cwd=clone_path,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    # Analyze command failure and determine if it's recoverable
                    command_name = command[1] if len(command) > 1 else command[0]
                    combined_output = result.stdout + result.stderr

                    # Special handling for cidx index command when no files are found to index
                    # Check if this is the index command (regardless of step number)
                    if (
                        command_name == "index"
                        and "No files found to index" in combined_output
                    ):
                        logging.warning(
                            f"Workflow step {i}: Repository has no indexable files - this is acceptable for golden repository registration"
                        )
                        logging.info(
                            f"Workflow step {i} completed with acceptable condition (no indexable files)"
                        )
                        continue  # This is acceptable, continue to next step

                    # Check for recoverable configuration conflicts
                    if command_name == "init" and self._is_recoverable_init_error(
                        combined_output
                    ):
                        logging.warning(
                            f"Workflow step {i}: Recoverable configuration conflict detected. "
                            f"Attempting to resolve: {combined_output}"
                        )
                        # Try to resolve the conflict and retry
                        if self._attempt_init_conflict_resolution(
                            clone_path, force_init
                        ):
                            logging.info(
                                f"Workflow step {i}: Configuration conflict resolved, continuing"
                            )
                            continue

                    # Check for recoverable service conflicts
                    if command_name == "start" and self._is_recoverable_service_error(
                        combined_output
                    ):
                        logging.warning(
                            f"Workflow step {i}: Recoverable service conflict detected. "
                            f"Attempting to resolve: {combined_output}"
                        )
                        # Try to resolve service conflicts
                        if self._attempt_service_conflict_resolution(clone_path):
                            logging.info(
                                f"Workflow step {i}: Service conflict resolved, continuing"
                            )
                            continue

                    # Unrecoverable error - fail the workflow
                    error_msg = f"Workflow step {i} failed: {' '.join(command)}\nStdout: {result.stdout}\nStderr: {result.stderr}"
                    logging.error(error_msg)
                    raise GitOperationError(error_msg)

                logging.info(f"Workflow step {i} completed successfully")

            logging.info(f"Post-clone workflow completed successfully for {clone_path}")

        except subprocess.TimeoutExpired:
            raise GitOperationError("Post-clone workflow timed out")
        except subprocess.CalledProcessError as e:
            raise GitOperationError(
                f"Post-clone workflow failed: Command '{' '.join(e.cmd)}' failed with exit code {e.returncode}"
            )
        except FileNotFoundError as e:
            raise GitOperationError(
                f"Post-clone workflow failed: Required command not found: {str(e)}"
            )
        except PermissionError as e:
            raise GitOperationError(
                f"Post-clone workflow failed: Permission denied: {str(e)}"
            )
        except OSError as e:
            raise GitOperationError(
                f"Post-clone workflow failed: System error: {str(e)}"
            )

    def refresh_golden_repo(self, alias: str, submitter_username: str = "admin") -> str:
        """
        Refresh a golden repository by pulling latest changes and re-indexing.

        This method submits a background job and returns immediately with a job_id.
        Use BackgroundJobManager to track progress and results.

        Args:
            alias: Alias of the repository to refresh
            submitter_username: Username of the user submitting the job (default: "admin")

        Returns:
            Job ID for tracking refresh progress

        Raises:
            GoldenRepoError: If repository not found
        """
        # Validate repository exists BEFORE submitting job
        if alias not in self.golden_repos:
            raise GoldenRepoError(f"Golden repository '{alias}' not found")

        # Create no-args wrapper for background execution
        def background_worker() -> Dict[str, Any]:
            """Execute refresh in background thread."""
            golden_repo = self.golden_repos[alias]
            # Use canonical path resolution to handle versioned structure repos
            clone_path = self.get_actual_repo_path(alias)

            # Read temporal configuration from existing golden repo
            enable_temporal = golden_repo.enable_temporal
            temporal_options = golden_repo.temporal_options

            try:
                # For local repositories, we can't do git pull, so just re-run workflow
                if self._is_local_path(golden_repo.repo_url):
                    logging.info(
                        f"Refreshing local repository {alias} by re-running workflow"
                    )
                    self._execute_post_clone_workflow(
                        clone_path,
                        force_init=True,
                        enable_temporal=enable_temporal,
                        temporal_options=temporal_options,
                    )
                else:
                    # For remote repositories, do git pull first
                    logging.info(f"Pulling latest changes for {alias}")
                    result = subprocess.run(
                        ["git", "pull", "origin", golden_repo.default_branch],
                        cwd=clone_path,
                        capture_output=True,
                        text=True,
                        timeout=self.resource_config.git_refresh_timeout,
                    )

                    if result.returncode != 0:
                        raise GitOperationError(f"Git pull failed: {result.stderr}")

                    logging.info(f"Git pull successful for {alias}")

                    # Re-run the indexing workflow with force flag for refresh
                    self._execute_post_clone_workflow(
                        clone_path,
                        force_init=True,
                        enable_temporal=enable_temporal,
                        temporal_options=temporal_options,
                    )

                return {
                    "success": True,
                    "alias": alias,
                    "message": f"Golden repository '{alias}' refreshed successfully",
                }

            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to refresh repository '{alias}': Git command failed with exit code {e.returncode}: {e.stderr}"
                logging.error(error_msg)
                raise GitOperationError(error_msg)
            except subprocess.TimeoutExpired as e:
                error_msg = f"Failed to refresh repository '{alias}': Git operation timed out after {e.timeout} seconds"
                logging.error(error_msg)
                raise GitOperationError(error_msg)
            except FileNotFoundError as e:
                error_msg = f"Failed to refresh repository '{alias}': Required file or command not found: {str(e)}"
                logging.error(error_msg)
                raise GitOperationError(error_msg)
            except PermissionError as e:
                error_msg = f"Failed to refresh repository '{alias}': Permission denied: {str(e)}"
                logging.error(error_msg)
                raise GitOperationError(error_msg)
            except GitOperationError:
                # Re-raise GitOperationError from sub-methods without modification
                raise

        # Submit to BackgroundJobManager
        job_id = self.background_job_manager.submit_job(
            operation_type="refresh_golden_repo",
            func=background_worker,
            submitter_username=submitter_username,
            is_admin=True,
            repo_alias=alias,  # AC5: Fix unknown repo bug
        )
        return cast(str, job_id)

    def _is_recoverable_init_error(self, error_output: str) -> bool:
        """
        Check if an init command error is recoverable.

        Args:
            error_output: Combined stdout/stderr from failed init command

        Returns:
            bool: True if error appears recoverable
        """
        error_lower = error_output.lower()
        recoverable_patterns = [
            "configuration conflict",
            "already initialized",
            "config file exists",
            "already in use",
            "service already running",
        ]
        return any(pattern in error_lower for pattern in recoverable_patterns)

    def _is_recoverable_service_error(self, error_output: str) -> bool:
        """
        Check if a service start command error is recoverable.

        Args:
            error_output: Combined stdout/stderr from failed start command

        Returns:
            bool: True if error appears recoverable
        """
        error_lower = error_output.lower()
        recoverable_patterns = [
            "already in use",
            "service already running",
            "container already exists",
            "already exists",
        ]
        return any(pattern in error_lower for pattern in recoverable_patterns)

    def _attempt_init_conflict_resolution(
        self, clone_path: str, force_init: bool
    ) -> bool:
        """
        Attempt to resolve initialization conflicts.

        Args:
            clone_path: Path to repository
            force_init: Whether force flag was already used

        Returns:
            bool: True if conflict was resolved
        """
        try:
            if not force_init:
                # Try init with force flag if it wasn't already used
                logging.info("Attempting init conflict resolution with --force flag")
                result = subprocess.run(
                    ["cidx", "init", "--embedding-provider", "voyage-ai", "--force"],
                    cwd=clone_path,
                    capture_output=True,
                    text=True,
                    timeout=self.resource_config.git_init_conflict_timeout,
                )
                return result.returncode == 0
            else:
                # Force was already used, try cleanup and retry
                logging.info("Attempting init conflict resolution with cleanup")
                config_dir = os.path.join(clone_path, ".code-indexer")
                if os.path.exists(config_dir):
                    import shutil

                    shutil.rmtree(config_dir)

                result = subprocess.run(
                    ["cidx", "init", "--embedding-provider", "voyage-ai"],
                    cwd=clone_path,
                    capture_output=True,
                    text=True,
                    timeout=self.resource_config.git_init_conflict_timeout,
                )
                return result.returncode == 0

        except subprocess.CalledProcessError as e:
            logging.warning(
                f"Init conflict resolution failed: Command failed with exit code {e.returncode}: {e.stderr}"
            )
            return False
        except subprocess.TimeoutExpired as e:
            logging.warning(
                f"Init conflict resolution failed: Command timed out after {e.timeout} seconds"
            )
            return False
        except FileNotFoundError as e:
            logging.warning(
                f"Init conflict resolution failed: Required command not found: {str(e)}"
            )
            return False
        except PermissionError as e:
            logging.warning(
                f"Init conflict resolution failed: Permission denied: {str(e)}"
            )
            return False
        except OSError as e:
            logging.warning(f"Init conflict resolution failed: System error: {str(e)}")
            return False

    def _attempt_service_conflict_resolution(self, clone_path: str) -> bool:
        """
        Attempt to resolve service conflicts.

        Args:
            clone_path: Path to repository

        Returns:
            bool: True if conflict was resolved
        """
        try:
            # Try stopping any existing services first
            logging.info(
                "Attempting service conflict resolution by stopping existing services"
            )
            subprocess.run(
                ["cidx", "stop"],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=self.resource_config.git_service_cleanup_timeout,
            )

            # Wait for service cleanup using proper event-based waiting
            if not self._wait_for_service_cleanup(
                clone_path, timeout=self.resource_config.git_service_wait_timeout
            ):
                logging.warning(
                    "Service cleanup wait timed out, proceeding with start attempt"
                )

            # Try starting again
            result = subprocess.run(
                ["cidx", "start"],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=self.resource_config.git_service_conflict_timeout,
            )
            return result.returncode == 0

        except subprocess.CalledProcessError as e:
            logging.warning(
                f"Service conflict resolution failed: Command failed with exit code {e.returncode}: {e.stderr}"
            )
            return False
        except subprocess.TimeoutExpired as e:
            logging.warning(
                f"Service conflict resolution failed: Command timed out after {e.timeout} seconds"
            )
            return False
        except FileNotFoundError as e:
            logging.warning(
                f"Service conflict resolution failed: Required command not found: {str(e)}"
            )
            return False
        except PermissionError as e:
            logging.warning(
                f"Service conflict resolution failed: Permission denied: {str(e)}"
            )
            return False
        except OSError as e:
            logging.warning(
                f"Service conflict resolution failed: System error: {str(e)}"
            )
            return False

    def _wait_for_service_cleanup(self, clone_path: str, timeout: int = 30) -> bool:
        """
        Wait for service cleanup using polling without artificial sleep delays.

        Args:
            clone_path: Path to repository
            timeout: Maximum time to wait in seconds

        Returns:
            bool: True if services are cleaned up, False if timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if services are stopped by attempting status check
            try:
                result = subprocess.run(
                    ["cidx", "status"],
                    cwd=clone_path,
                    capture_output=True,
                    text=True,
                    timeout=self.resource_config.git_process_check_timeout,
                )
                # If status shows no services or fails with "not running", cleanup is complete
                if result.returncode != 0 or "not running" in result.stdout.lower():
                    return True
            except subprocess.CalledProcessError:
                # Status check failed, assume services are down
                return True
            except subprocess.TimeoutExpired:
                # Status check timed out, assume services are down
                return True
            except FileNotFoundError:
                # Status command not found, assume services are down
                return True
            except PermissionError:
                # Permission denied for status check, assume services are down
                return True
            except OSError:
                # System error during status check, assume services are down
                return True

            # Yield control without sleep - just let the loop continue
            pass

        return False

    def find_by_canonical_url(self, canonical_url: str) -> List[Dict[str, Any]]:
        """
        Find golden repositories by canonical git URL.

        Args:
            canonical_url: Canonical form of git URL (e.g., "github.com/user/repo")

        Returns:
            List of matching golden repository dictionaries
        """
        from ..services.git_url_normalizer import GitUrlNormalizer

        normalizer = GitUrlNormalizer()
        matching_repos = []

        for repo in self.golden_repos.values():
            try:
                # Normalize the repository's URL
                normalized = normalizer.normalize(repo.repo_url)

                # Check if it matches the target canonical URL
                if normalized.canonical_form == canonical_url:
                    repo_dict = repo.to_dict()

                    # Add canonical URL and branch information - need to cast to Dict[str, Any]
                    repo_dict_any: Dict[str, Any] = dict(
                        repo_dict
                    )  # Convert to Dict[str, Any]
                    repo_dict_any["canonical_url"] = canonical_url
                    # Use canonical path resolution to handle versioned structure repos
                    actual_path = self.get_actual_repo_path(repo.alias)
                    repo_dict_any["branches"] = self._get_repository_branches(
                        actual_path
                    )

                    matching_repos.append(repo_dict_any)

            except Exception as e:
                logging.warning(
                    f"Failed to normalize URL for repo {repo.alias}: {str(e)}"
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

            # Get branches using git command
            result = subprocess.run(
                ["git", "branch", "-r"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.resource_config.git_untracked_file_timeout,
            )

            if result.returncode == 0:
                branches = []
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        # Clean up branch name (remove origin/ prefix)
                        branch = line.strip().replace("origin/", "")
                        if branch and branch != "HEAD":
                            branches.append(branch)

                return branches if branches else ["main"]
            else:
                return ["main"]

        except Exception as e:
            logging.warning(f"Failed to get branches for {repo_path}: {str(e)}")
            return ["main"]

    def get_golden_repo(self, alias: str) -> Optional[GoldenRepo]:
        """
        Get a golden repository by alias.

        Args:
            alias: Repository alias

        Returns:
            GoldenRepo object if found, None otherwise
        """
        return self.golden_repos.get(alias)

    def golden_repo_exists(self, alias: str) -> bool:
        """
        Check if a golden repository exists.

        Args:
            alias: Repository alias

        Returns:
            True if repository exists, False otherwise
        """
        return alias in self.golden_repos

    def get_actual_repo_path(self, alias: str) -> str:
        """
        Resolve actual filesystem path for golden/global repo.

        Resolves the canonical filesystem path for a golden repository,
        handling mixed topology (flat structure + versioned structure).

        This method is critical for fixing Bug #3, Bug #4, Topology Bug 2.1,
        and Topology Bug 3.1 where metadata paths become stale when repos
        are stored in .versioned/ structure but metadata still points to
        flat structure paths.

        Checks in priority order:
        1. Metadata clone_path (legacy flat structure)
        2. .versioned/{alias}/v_*/ (versioned structure, latest version)
        3. Raise GoldenRepoNotFoundError if not found

        Security: Validates alias and paths to prevent path traversal attacks.

        Args:
            alias: Repository alias

        Returns:
            str: Actual filesystem path to repository

        Raises:
            ValueError: If alias contains path traversal characters or resolved path escapes sandbox
            GoldenRepoNotFoundError: If repo doesn't exist in metadata or filesystem
        """
        # SECURITY: Reject dangerous characters in alias (path traversal protection)
        if ".." in alias:
            raise ValueError(
                f"Invalid alias '{alias}': cannot contain path traversal characters (..)"
            )
        if "/" in alias:
            raise ValueError(
                f"Invalid alias '{alias}': cannot contain path traversal characters (/)"
            )
        if "\\" in alias:
            raise ValueError(
                f"Invalid alias '{alias}': cannot contain path traversal characters (\\)"
            )

        # Check if alias exists in metadata
        if alias not in self.golden_repos:
            raise GoldenRepoNotFoundError(
                f"Golden repository '{alias}' not found in metadata"
            )

        golden_repo = self.golden_repos[alias]
        metadata_path = golden_repo.clone_path

        # Get logger for this module
        logger = logging.getLogger(__name__)

        # Priority 1: Check if metadata path exists on filesystem
        if os.path.exists(metadata_path):
            # SECURITY: Verify resolved path stays within golden_repos_dir (symlink protection)
            # Only validate paths that actually exist to avoid blocking test fixtures
            resolved_metadata = os.path.realpath(metadata_path)
            golden_repos_realpath = os.path.realpath(self.golden_repos_dir)
            if not resolved_metadata.startswith(golden_repos_realpath):
                raise ValueError(
                    f"Security violation: resolved path '{resolved_metadata}' "
                    f"outside golden repos directory '{self.golden_repos_dir}'"
                )
            return metadata_path

        # Priority 2: Check .versioned/{alias}/ structure
        versioned_base = os.path.join(self.golden_repos_dir, ".versioned", alias)

        if os.path.exists(versioned_base):
            # SECURITY: Verify versioned path also stays within bounds
            # Only validate paths that actually exist to avoid blocking test fixtures
            resolved_versioned_base = os.path.realpath(versioned_base)
            golden_repos_realpath = os.path.realpath(self.golden_repos_dir)
            if not resolved_versioned_base.startswith(golden_repos_realpath):
                raise ValueError(
                    f"Security violation: versioned path '{resolved_versioned_base}' "
                    f"outside golden repos directory"
                )

            # Find all v_* subdirectories
            version_dirs = []
            for entry in os.listdir(versioned_base):
                if entry.startswith("v_") and os.path.isdir(
                    os.path.join(versioned_base, entry)
                ):
                    version_dirs.append(entry)

            # SECURITY: Filter valid version directories and skip malformed ones
            if version_dirs:
                valid_versions = []
                for v_dir in version_dirs:
                    try:
                        # Extract timestamp from v_TIMESTAMP format
                        timestamp = int(v_dir.split("_")[1])
                        valid_versions.append((v_dir, timestamp))
                    except (ValueError, IndexError) as e:
                        # Skip malformed version directories gracefully
                        logger.warning(
                            f"Skipping malformed version directory: {v_dir} "
                            f"(expected format: v_TIMESTAMP, error: {e})",
                            extra={"correlation_id": get_correlation_id()},
                        )
                        continue

                if valid_versions:
                    # Sort by timestamp (highest = latest)
                    valid_versions.sort(key=lambda x: x[1], reverse=True)
                    latest_version = valid_versions[0][0]
                    versioned_path = os.path.join(versioned_base, latest_version)
                    return versioned_path

        # Not found in either location
        raise GoldenRepoNotFoundError(
            f"Golden repository '{alias}' not found on filesystem.\n"
            f"Attempted paths:\n"
            f"  1. Metadata path: {metadata_path}\n"
            f"  2. Versioned path: {versioned_base}/v_*/"
        )

    def user_can_access_golden_repo(self, alias: str, user: Any) -> bool:
        """
        Check if a user can access a golden repository.

        For now, all authenticated users can access all golden repositories.
        This method exists for future permission system expansion.

        Args:
            alias: Repository alias
            user: User object (can be None for unauthenticated)

        Returns:
            True if user can access repository, False otherwise
        """
        # Golden repositories are accessible to all authenticated users
        return user is not None

    async def get_golden_repo_branches(
        self, alias: str
    ) -> List["GoldenRepoBranchInfo"]:
        """
        Get branches for a golden repository.

        This method delegates to the branch service for actual branch retrieval.
        Kept here for compatibility and future enhancement.

        Args:
            alias: Repository alias

        Returns:
            List of GoldenRepoBranchInfo objects

        Raises:
            GoldenRepoError: If repository not found or operation fails
        """
        # Import here to avoid circular imports
        from code_indexer.server.services.golden_repo_branch_service import (
            GoldenRepoBranchService,
        )

        if not self.golden_repo_exists(alias):
            raise GoldenRepoError(f"Golden repository '{alias}' not found")

        branch_service = GoldenRepoBranchService(self)
        branches: List[
            "GoldenRepoBranchInfo"
        ] = await branch_service.get_golden_repo_branches(alias)
        return branches

    def add_index_to_golden_repo(
        self,
        alias: str,
        index_type: str,
        submitter_username: str = "admin",
    ) -> str:
        """
        Add an index type to an existing golden repository.

        This method submits a background job and returns immediately with a job_id.
        Use BackgroundJobManager to track progress and results.

        Args:
            alias: The golden repo alias
            index_type: One of "semantic_fts", "temporal", "scip"
            submitter_username: Username for audit logging

        Returns:
            job_id: The background job ID for tracking

        Raises:
            ValueError: If alias not found, index_type invalid, or index already exists
        """
        # AC4: Validate alias exists
        if alias not in self.golden_repos:
            raise ValueError(f"Golden repository '{alias}' not found")

        # AC2: Validate index_type
        valid_index_types = ["semantic_fts", "temporal", "scip"]
        if index_type not in valid_index_types:
            raise ValueError(
                f"Invalid index_type: {index_type}. Must be one of: {', '.join(valid_index_types)}"
            )

        # AC3: Check if index already exists (idempotent behavior)
        golden_repo = self.golden_repos[alias]
        if self._index_exists(golden_repo, index_type):
            raise ValueError(
                f"Index type '{index_type}' already exists for golden repo '{alias}'"
            )

        # AC1: Create background job and return job_id
        def background_worker() -> Dict[str, Any]:
            """Execute add index operation in background thread."""
            try:
                # Get repository details
                repo = self.golden_repos[alias]
                # Use canonical path resolution to handle versioned structure repos
                repo_path = self.get_actual_repo_path(alias)

                # Initialize stdout/stderr tracking (AC5, AC6, AC7)
                captured_stdout = ""
                captured_stderr = ""

                # AC5: semantic_fts - execute cidx index --fts
                if index_type == "semantic_fts":
                    command = ["cidx", "index", "--fts"]
                    result = subprocess.run(
                        command,
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                    )
                    captured_stdout = result.stdout
                    captured_stderr = result.stderr
                    if result.returncode != 0:
                        raise GoldenRepoError(
                            f"Failed to create semantic_fts index: {result.stderr}"
                        )

                # AC6: temporal - execute cidx index --index-commits with options
                elif index_type == "temporal":
                    command = ["cidx", "index", "--index-commits"]

                    # Read temporal options from GoldenRepo
                    temporal_options = repo.temporal_options or {}

                    # Apply temporal options or use defaults
                    max_commits = temporal_options.get("max_commits", 1000)
                    command.extend(["--max-commits", str(max_commits)])

                    if "since_date" in temporal_options:
                        command.extend(["--since-date", temporal_options["since_date"]])

                    diff_context = temporal_options.get("diff_context", 5)
                    command.extend(["--diff-context", str(diff_context)])

                    if temporal_options.get("all_branches"):
                        command.append("--all-branches")

                    result = subprocess.run(
                        command,
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                    )
                    captured_stdout = result.stdout
                    captured_stderr = result.stderr
                    if result.returncode != 0:
                        raise GoldenRepoError(
                            f"Failed to create temporal index: {result.stderr}"
                        )

                # AC7: scip - execute cidx scip generate
                elif index_type == "scip":
                    command = ["cidx", "scip", "generate"]
                    result = subprocess.run(
                        command,
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                    )
                    captured_stdout = result.stdout
                    captured_stderr = result.stderr
                    if result.returncode != 0:
                        raise GoldenRepoError(
                            f"Failed to create SCIP index: {result.stderr}"
                        )

                return {
                    "success": True,
                    "alias": alias,
                    "message": f"Index type '{index_type}' added successfully to '{alias}'",
                    "stdout": captured_stdout,
                    "stderr": captured_stderr,
                }
            except subprocess.CalledProcessError as e:
                raise GoldenRepoError(
                    f"Failed to add index: Command failed with exit code {e.returncode}: {e.stderr}"
                )
            except Exception as e:
                raise GoldenRepoError(f"Failed to add index: {str(e)}")

        # Submit to BackgroundJobManager
        job_id = self.background_job_manager.submit_job(
            operation_type="add_index",
            func=background_worker,
            submitter_username=submitter_username,
            is_admin=True,
            repo_alias=alias,  # AC5: Fix unknown repo bug
        )
        return cast(str, job_id)

    def _index_exists(self, golden_repo: GoldenRepo, index_type: str) -> bool:
        """
        Check if an index type already exists for a golden repository.

        Args:
            golden_repo: The golden repository object
            index_type: The index type to check ("semantic_fts", "temporal", "scip")

        Returns:
            True if the index exists, False otherwise
        """
        # Use canonical path resolution to handle versioned structure repos
        actual_path = self.get_actual_repo_path(golden_repo.alias)
        repo_dir = Path(actual_path)

        if index_type == "semantic_fts":
            # AC3: semantic_fts requires BOTH vector index AND FTS index with actual files
            vector_index = repo_dir / ".code-indexer" / "index"
            fts_index = repo_dir / ".code-indexer" / "tantivy_index"

            # Check for actual index files, not just directories
            has_vector_files = False
            has_fts_files = False

            if vector_index.exists():
                # Check for any .json files in index subdirectories (collection folders)
                has_vector_files = any(vector_index.rglob("*.json"))

            if fts_index.exists():
                # Check for meta.json or any index files
                has_fts_files = (fts_index / "meta.json").exists() or any(
                    fts_index.rglob("*.json")
                )

            return has_vector_files and has_fts_files

        elif index_type == "temporal":
            # Temporal index detection is not yet implemented - always allow creation
            # TODO: Implement proper detection by checking chunk metadata for commit hashes
            return False

        elif index_type == "scip":
            # AC3: scip requires .code-indexer/scip/ directory with valid .scip.db files containing data
            scip_dir = repo_dir / ".code-indexer" / "scip"
            if not scip_dir.exists():
                return False

            # Find all .scip.db files
            scip_db_files = list(scip_dir.glob("**/*.scip.db"))
            if not scip_db_files:
                return False

            # Validate at least one .scip.db file has data
            sqlite3_module = None
            try:
                import sqlite3

                sqlite3_module = sqlite3
            except ImportError:
                try:
                    from pysqlite3 import dbapi2 as pysqlite3_compat

                    sqlite3_module = pysqlite3_compat
                except ImportError:
                    pass

            if sqlite3_module is None:
                # If sqlite3 not available, fall back to file size check
                return any(f.stat().st_size > 0 for f in scip_db_files)

            # Check if any database has symbols
            for db_file in scip_db_files:
                if db_file.stat().st_size == 0:
                    continue
                try:
                    conn = sqlite3_module.connect(str(db_file))
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM symbols")
                    count = cursor.fetchone()[0]
                    conn.close()
                    if count > 0:
                        return True
                except Exception:
                    # Database corruption or schema issue - treat as not existing
                    continue

            return False

        return False

    def get_golden_repo_indexes(self, alias: str) -> Dict[str, Any]:
        """
        Get structured status of all index types for a golden repository.

        This method examines the filesystem to determine which index types exist
        for the specified golden repository and returns their current status.

        Args:
            alias: The golden repo alias

        Returns:
            Dictionary with structure:
            {
                "alias": str,
                "indexes": {
                    "semantic_fts": {"exists": bool, "path": str|None, "last_updated": str|None},
                    "temporal": {"exists": bool, "path": str|None, "last_updated": str|None},
                    "scip": {"exists": bool, "path": str|None, "last_updated": str|None}
                }
            }

        Raises:
            ValueError: If alias not found
        """
        # Validate alias exists
        if alias not in self.golden_repos:
            raise ValueError(f"Golden repository '{alias}' not found")

        golden_repo = self.golden_repos[alias]
        # Use canonical path resolution to handle versioned structure repos
        actual_path = self.get_actual_repo_path(alias)
        repo_dir = Path(actual_path)

        # Check each index type using helper method
        indexes = {
            "semantic_fts": self._get_index_status(
                repo_dir, "semantic_fts", golden_repo
            ),
            "temporal": self._get_index_status(repo_dir, "temporal", golden_repo),
            "scip": self._get_index_status(repo_dir, "scip", golden_repo),
        }

        return {"alias": alias, "indexes": indexes}

    def _get_index_status(
        self, repo_dir: Path, index_type: str, golden_repo: GoldenRepo
    ) -> Dict[str, Any]:
        """
        Get status dictionary for a single index type.

        Args:
            repo_dir: Repository directory path
            index_type: Index type ("semantic_fts", "temporal", "scip")
            golden_repo: Golden repository object

        Returns:
            Status dict with exists, path, last_updated keys
        """
        path_map = {
            "semantic_fts": "tantivy_index",
            "temporal": "index",
            "scip": "scip",
        }

        exists = self._index_exists(golden_repo, index_type)
        if exists:
            index_path = repo_dir / ".code-indexer" / path_map[index_type]
            return {
                "exists": True,
                "path": str(index_path),
                "last_updated": self._get_directory_last_modified(index_path),
            }
        return {"exists": False, "path": None, "last_updated": None}

    def _get_directory_last_modified(self, dir_path: Path) -> Optional[str]:
        """
        Get the last modified timestamp of a directory in ISO 8601 format.

        Args:
            dir_path: Path to directory

        Returns:
            ISO 8601 timestamp string or None if directory doesn't exist
        """
        if not dir_path.exists():
            return None

        try:
            mtime = dir_path.stat().st_mtime
            dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            return dt.isoformat()
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Failed to get last modified time for {dir_path}: {e}"
            )
            return None
