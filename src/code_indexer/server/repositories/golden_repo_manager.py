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
from typing import Dict, List, Optional, Any
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

    def to_dict(self) -> Dict[str, str]:
        """Convert golden repository to dictionary."""
        return {
            "alias": self.alias,
            "repo_url": self.repo_url,
            "default_branch": self.default_branch,
            "clone_path": self.clone_path,
            "created_at": self.created_at,
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
        self, repo_url: str, alias: str, default_branch: str = "main"
    ) -> Dict[str, Any]:
        """
        Add a golden repository.

        Args:
            repo_url: Git repository URL
            alias: Unique alias for the repository
            default_branch: Default branch to clone (default: main)

        Returns:
            Result dictionary with success status and message

        Raises:
            GoldenRepoError: If alias already exists
            GitOperationError: If git repository is invalid or clone fails
            ResourceLimitError: If resource limits are exceeded
        """
        # Check if we've reached the maximum limit
        if len(self.golden_repos) >= self.MAX_GOLDEN_REPOS:
            raise ResourceLimitError(
                f"Maximum of {self.MAX_GOLDEN_REPOS} golden repositories allowed"
            )

        # Check if alias already exists
        if alias in self.golden_repos:
            raise GoldenRepoError(f"Golden repository alias '{alias}' already exists")

        # Validate git repository accessibility
        if not self._validate_git_repository(repo_url):
            raise GitOperationError(
                f"Invalid or inaccessible git repository: {repo_url}"
            )

        # Clone repository
        try:
            clone_path = self._clone_repository(repo_url, alias, default_branch)

            # Execute post-clone workflow if repository was successfully cloned
            self._execute_post_clone_workflow(clone_path, force_init=False)

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

        # Check repository size
        repo_size = self._get_repository_size(clone_path)
        if repo_size > self.MAX_REPO_SIZE_BYTES:
            # Clean up cloned repository (ignore cleanup result since we're rejecting anyway)
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
        )

        # Store and persist
        self.golden_repos[alias] = golden_repo
        self._save_metadata()

        return {
            "success": True,
            "message": f"Golden repository '{alias}' added successfully",
        }

    def list_golden_repos(self) -> List[Dict[str, str]]:
        """
        List all golden repositories.

        Returns:
            List of golden repository dictionaries
        """
        return [repo.to_dict() for repo in self.golden_repos.values()]

    def remove_golden_repo(self, alias: str) -> Dict[str, Any]:
        """
        Remove a golden repository.

        Args:
            alias: Alias of the repository to remove

        Returns:
            Result dictionary with success status and message

        Raises:
            GoldenRepoError: If repository not found
        """
        if alias not in self.golden_repos:
            raise GoldenRepoError(f"Golden repository '{alias}' not found")

        # Get repository info before removal
        golden_repo = self.golden_repos[alias]

        # Clean up repository files - this now returns bool indicating cleanup success
        cleanup_successful = self._cleanup_repository_files(golden_repo.clone_path)

        # Remove from storage - this is the critical operation for deletion success
        del self.golden_repos[alias]
        self._save_metadata()

        # Generate appropriate success message based on cleanup result
        if cleanup_successful:
            message = f"Golden repository '{alias}' removed successfully"
        else:
            message = f"Golden repository '{alias}' removed successfully (some cleanup issues occurred)"

        return {
            "success": True,
            "message": message,
        }

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
            from ...services.docker_manager import DockerManager

            # Use the same orchestrated cleanup as 'cidx uninstall'
            clone_path_obj = Path(clone_path)
            project_config_dir = clone_path_obj / ".code-indexer"

            if project_config_dir.exists():
                # Repository has cidx services - use orchestrated cleanup
                try:
                    docker_manager = None
                    try:
                        docker_manager = DockerManager(
                            force_docker=True,  # Use Docker for server operations
                            project_config_dir=project_config_dir,
                        )

                        # Perform orchestrated cleanup with data removal (same as uninstall)
                        cleanup_success = docker_manager.cleanup(
                            remove_data=True, verbose=False
                        )
                        if not cleanup_success:
                            logging.warning(
                                f"Docker cleanup reported some issues for {clone_path}"
                            )

                        logging.info(
                            f"Completed orchestrated cleanup for: {clone_path}"
                        )
                    finally:
                        # DockerManager doesn't require explicit closing
                        docker_manager = None

                except PermissionError as e:
                    logging.error(f"Permission denied during Docker cleanup: {e}")
                    raise GitOperationError(
                        f"Insufficient permissions for Docker cleanup: {str(e)}"
                    )
                except OSError as e:
                    if e.errno == errno.ENOENT:  # File not found
                        logging.info(
                            f"Docker resources already cleaned for {clone_path}"
                        )
                    else:
                        logging.error(f"OS error during Docker cleanup: {e}")
                        raise GitOperationError(
                            f"File system error during Docker cleanup: {str(e)}"
                        )
                except ImportError as e:
                    logging.error(f"Missing Docker dependency: {e}")
                    raise GitOperationError(
                        f"Docker system dependency unavailable: {str(e)}"
                    )
                except subprocess.CalledProcessError as e:
                    logging.error(f"Docker cleanup process failed: {e}")
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
                    # These specific Docker-related exceptions should not prevent repository deletion
                    logging.warning(
                        f"Docker cleanup failed but deletion can proceed: {e}"
                    )
                    # Don't raise - this allows deletion to continue
                finally:
                    # Ensure docker_manager is properly cleaned up if it was created
                    if "docker_manager" in locals():
                        docker_manager = None

            # After orchestrated cleanup, remove the remaining directory structure
            # This should now work since root-owned files have been cleaned up
            if clone_path_obj.exists():
                try:
                    shutil.rmtree(clone_path)
                    logging.info(
                        f"Successfully cleaned up repository files: {clone_path}"
                    )
                    return True
                except (PermissionError, OSError) as fs_error:
                    # File system cleanup failed - log but don't prevent deletion
                    logging.warning(
                        f"File system cleanup incomplete for {clone_path}: {fs_error}. "
                        "Some files may remain but repository deletion was successful."
                    )
                    return False
            else:
                return True  # Directory already removed

        except ImportError as import_error:
            # DockerManager import failed - this is a critical system issue
            logging.error(f"Critical system error during cleanup: {import_error}")
            raise GitOperationError(
                f"System dependency unavailable for cleanup: {str(import_error)}"
            )
        except PermissionError as e:
            logging.error(f"Permission denied during cleanup: {e}")
            raise GitOperationError(f"Insufficient permissions for cleanup: {str(e)}")
        except OSError as e:
            if e.errno == errno.ENOENT:  # File not found
                return True  # Already cleaned
            elif e.errno == errno.EACCES:  # Permission denied
                logging.error(f"Access denied during cleanup: {e}")
                raise GitOperationError(f"Access denied for cleanup: {str(e)}")
            else:
                logging.error(f"OS error during cleanup: {e}")
                raise GitOperationError(f"File system error during cleanup: {str(e)}")
        except subprocess.CalledProcessError as e:
            if e.returncode == 126:  # Permission denied
                logging.error(f"Command permission error during cleanup: {e}")
                raise GitOperationError(f"Command permission denied: {str(e)}")
            else:
                logging.error(f"Process error during cleanup: {e}")
                raise GitOperationError(
                    f"Process failed with exit code {e.returncode}: {str(e)}"
                )
        except RuntimeError as e:
            # Critical system errors that prevent cleanup
            logging.error(f"Critical system error during cleanup: {e}")
            raise GitOperationError(f"Critical cleanup failure: {str(e)}")
        # No generic Exception handler - all specific errors are handled above

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
        self, clone_path: str, force_init: bool = False
    ) -> None:
        """
        Execute the required workflow after successful repository cloning.

        The workflow includes:
        1. cidx init with voyage-ai embedding provider (with optional --force for refresh)
        2. cidx start --force-docker
        3. cidx status --force-docker (health check)
        4. cidx index --force-docker
        5. cidx stop --force-docker

        Args:
            clone_path: Path to the cloned repository
            force_init: Whether to use --force flag with cidx init (for refresh operations)

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

        workflow_commands = [
            init_command,
            ["cidx", "start", "--force-docker"],
            ["cidx", "status", "--force-docker"],
            ["cidx", "index"],  # index command does not support --force-docker
            ["cidx", "stop", "--force-docker"],
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
                    if i == 4 and "cidx index" in " ".join(command):
                        if "No files found to index" in combined_output:
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

    def refresh_golden_repo(self, alias: str) -> Dict[str, Any]:
        """
        Refresh a golden repository by pulling latest changes and re-indexing.

        Args:
            alias: Alias of the repository to refresh

        Returns:
            Result dictionary with success status and message

        Raises:
            GoldenRepoError: If repository not found
            GitOperationError: If git pull or re-index fails
        """
        if alias not in self.golden_repos:
            raise GoldenRepoError(f"Golden repository '{alias}' not found")

        golden_repo = self.golden_repos[alias]
        clone_path = golden_repo.clone_path

        try:
            # For local repositories, we can't do git pull, so just re-run workflow
            if self._is_local_path(golden_repo.repo_url):
                logging.info(
                    f"Refreshing local repository {alias} by re-running workflow"
                )
                self._execute_post_clone_workflow(clone_path, force_init=True)
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
                self._execute_post_clone_workflow(clone_path, force_init=True)

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
            error_msg = (
                f"Failed to refresh repository '{alias}': Permission denied: {str(e)}"
            )
            logging.error(error_msg)
            raise GitOperationError(error_msg)
        except GitOperationError:
            # Re-raise GitOperationError from sub-methods without modification
            raise

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
