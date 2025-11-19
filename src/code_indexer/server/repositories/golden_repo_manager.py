"""
Golden Repository Manager for CIDX Server.

Manages golden repositories that can be activated by users for semantic search.
Golden repositories are stored in ~/.cidx-server/data/golden-repos/ with metadata tracking.
"""

import errno
import json
import os
import shutil
import subprocess
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from code_indexer.server.models.golden_repo_branch_models import (
        GoldenRepoBranchInfo,
    )
from pydantic import BaseModel


class GoldenRepoError(Exception):
    """Base exception for golden repository operations."""

    pass


class ResourceLimitError(GoldenRepoError):
    """Exception raised when resource limits are exceeded."""

    pass


class GitOperationError(GoldenRepoError):
    """Exception raised when git operations fail."""

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

    MAX_GOLDEN_REPOS = 20
    MAX_REPO_SIZE_BYTES = 1 * 1024 * 1024 * 1024  # 1GB

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize golden repository manager.

        Args:
            data_dir: Data directory path (defaults to ~/.cidx-server/data)
        """
        if data_dir:
            self.data_dir = data_dir
        else:
            home_dir = Path.home()
            self.data_dir = str(home_dir / ".cidx-server" / "data")

        self.golden_repos_dir = os.path.join(self.data_dir, "golden-repos")
        self.metadata_file = os.path.join(self.golden_repos_dir, "metadata.json")

        # Ensure directory structure exists
        os.makedirs(self.golden_repos_dir, exist_ok=True)

        # Storage for golden repositories
        self.golden_repos: Dict[str, GoldenRepo] = {}

        # Load existing metadata
        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load golden repository metadata from file."""
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
            self._save_metadata()

    def _save_metadata(self) -> None:
        """Save golden repository metadata to file."""
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
            GoldenRepoError: If alias already exists
            GitOperationError: If git repository is invalid or inaccessible
            ResourceLimitError: If resource limits are exceeded
        """
        # Validate BEFORE submitting job
        if len(self.golden_repos) >= self.MAX_GOLDEN_REPOS:
            raise ResourceLimitError(
                f"Maximum of {self.MAX_GOLDEN_REPOS} golden repositories allowed"
            )

        if alias in self.golden_repos:
            raise GoldenRepoError(f"Golden repository alias '{alias}' already exists")

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

                # Check repository size
                repo_size = self._get_repository_size(clone_path)
                if repo_size > self.MAX_REPO_SIZE_BYTES:
                    # Clean up cloned repository
                    self._cleanup_repository_files(clone_path)
                    size_gb = repo_size / (1024 * 1024 * 1024)
                    limit_gb = self.MAX_REPO_SIZE_BYTES / (1024 * 1024 * 1024)
                    raise ResourceLimitError(
                        f"Repository size ({size_gb:.1f}GB) exceeds limit ({limit_gb:.1f}GB)"
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

                return {
                    "success": True,
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
        )
        return job_id

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
            # Get repository info before removal
            golden_repo = self.golden_repos[alias]

            # Perform cleanup BEFORE removing from memory
            try:
                cleanup_successful = self._cleanup_repository_files(golden_repo.clone_path)
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
                message = f"Golden repository '{alias}' removed successfully"
                return {
                    "success": True,
                    "message": message,
                }
            else:
                # FAIL the operation - don't mask cleanup failures
                raise GitOperationError(
                    f"Repository metadata removed but cleanup incomplete. "
                    f"Resource leak detected: some cleanup operations did not complete fully."
                )

        # Submit to BackgroundJobManager
        job_id = self.background_job_manager.submit_job(
            operation_type="remove_golden_repo",
            func=background_worker,
            submitter_username=submitter_username,
            is_admin=True,
        )
        return job_id

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
                timeout=30,
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
        return repo_url.startswith("/") or repo_url.startswith("file://")

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
        # Normalize file:// URLs
        source_path = (
            repo_url.replace("file://", "")
            if repo_url.startswith("file://")
            else repo_url
        )

        try:
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
            # Use shallow clone to save space and time
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "--branch",
                    branch,
                    repo_url,
                    clone_path,
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
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
        created by Qdrant containers through the data-cleaner service.

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
        Perform Docker orchestrated cleanup for repository with cidx services.

        Args:
            clone_path: Path to repository directory
            project_config_dir: Path to .code-indexer config directory

        Returns:
            bool: True if Docker cleanup successful, False if issues occurred

        Raises:
            GitOperationError: For critical failures that should prevent deletion
        """
        from ...services.docker_manager import DockerManager

        try:
            # Use context manager for proper resource management
            with DockerManager(
                force_docker=True,  # Use Docker for server operations
                project_config_dir=project_config_dir,
            ) as docker_manager:
                # Perform orchestrated cleanup with data removal (same as uninstall)
                cleanup_success = docker_manager.cleanup(
                    remove_data=True, verbose=False
                )
                if not cleanup_success:
                    logging.warning(
                        f"Docker cleanup reported issues for {clone_path}. "
                        f"Containers or volumes may still exist but cleanup can proceed."
                    )
                    return False

                logging.info(f"Completed orchestrated cleanup for: {clone_path}")
                return True

        except PermissionError as e:
            logging.error(f"Permission denied during Docker cleanup: {e}")
            raise GitOperationError(
                f"Insufficient permissions for Docker cleanup: {str(e)}"
            )
        except OSError as e:
            if e.errno == errno.ENOENT:  # File not found
                logging.info(f"Docker resources already cleaned for {clone_path}")
                return True
            else:
                logging.error(f"OS error during Docker cleanup: {e}")
                raise GitOperationError(
                    f"File system error during Docker cleanup: {str(e)}"
                )
        except ImportError as e:
            logging.error(f"Missing Docker dependency: {e}")
            raise GitOperationError(f"Docker system dependency unavailable: {str(e)}")
        except subprocess.CalledProcessError as e:
            error_output = getattr(e, "stderr", "") or str(e)

            # Handle broken pipe errors gracefully - these are communication issues, not critical failures
            if "broken pipe" in error_output.lower() or "pipe" in error_output.lower():
                logging.warning(
                    f"Docker cleanup had communication issues but deletion can proceed: {error_output}"
                )
                return False  # Non-critical failure
            else:
                # Other subprocess errors are more serious
                logging.error(
                    f"Docker cleanup process failed for {clone_path}: "
                    f"Command failed with exit code {e.returncode}, stderr: {error_output}"
                )
                raise GitOperationError(
                    f"Docker cleanup failed with exit code {e.returncode}"
                )
        except (
            RuntimeError,
            ConnectionError,
            TimeoutError,
            ValueError,
            TypeError,
        ) as e:
            # Docker daemon issues that are non-critical for repository deletion
            logging.warning(
                f"Docker cleanup failed for {clone_path} but deletion can proceed: "
                f"Docker daemon error: {type(e).__name__}: {e}"
            )
            return False  # Non-critical failure

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
            # DockerManager import failed - this is a critical system issue
            logging.error(
                f"Critical system error during cleanup of {clone_path}: "
                f"Missing dependency: {error}"
            )
            raise GitOperationError(
                f"System dependency unavailable for cleanup: {str(error)}"
            )
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

    def _get_repository_size(self, repo_path: str) -> int:
        """
        Calculate total size of repository in bytes.

        Args:
            repo_path: Path to repository directory

        Returns:
            Total size in bytes
        """
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(repo_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except OSError:
                    # Skip files we can't access
                    pass
        return total_size

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

        # Build index command with optional temporal parameters
        index_command = ["cidx", "index"]
        if enable_temporal:
            index_command.append("--index-commits")

            if temporal_options:
                if temporal_options.get("max_commits"):
                    index_command.extend(
                        ["--max-commits", str(temporal_options["max_commits"])]
                    )

                if temporal_options.get("since_date"):
                    index_command.extend(
                        ["--since-date", temporal_options["since_date"]]
                    )

                # Add diff-context parameter (default: 5 from model)
                diff_context = temporal_options.get("diff_context", 5)
                index_command.extend(["--diff-context", str(diff_context)])

                # Log warning for large context values
                if diff_context > 20:
                    logging.warning(
                        f"Large diff context ({diff_context} lines) will significantly "
                        f"increase storage. Recommended range: 3-10 lines."
                    )

        workflow_commands = [
            init_command,
            index_command,
        ]

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
                    timeout=300,  # 5 minutes timeout per command
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
            clone_path = golden_repo.clone_path

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
                        timeout=300,
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
        )
        return job_id

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
                    timeout=300,
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
                    timeout=300,
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
                ["cidx", "stop", "--force-docker"],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Wait for service cleanup using proper event-based waiting
            if not self._wait_for_service_cleanup(clone_path, timeout=10):
                logging.warning(
                    "Service cleanup wait timed out, proceeding with start attempt"
                )

            # Try starting again
            result = subprocess.run(
                ["cidx", "start", "--force-docker"],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=300,
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
                    ["cidx", "status", "--force-docker"],
                    cwd=clone_path,
                    capture_output=True,
                    text=True,
                    timeout=5,
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
                    repo_dict_any["branches"] = self._get_repository_branches(
                        repo.clone_path
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
                timeout=10,
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
        branches: List["GoldenRepoBranchInfo"] = (
            await branch_service.get_golden_repo_branches(alias)
        )
        return branches
