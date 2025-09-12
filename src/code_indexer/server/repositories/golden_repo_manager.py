"""
Golden Repository Manager for CIDX Server.

Manages golden repositories that can be activated by users for semantic search.
Golden repositories are stored in ~/.cidx-server/data/golden-repos/ with metadata tracking.
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

        except Exception as e:
            raise GitOperationError(f"Failed to clone repository: {str(e)}")

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

        # Clean up repository files
        self._cleanup_repository_files(golden_repo.clone_path)

        # Remove from storage
        del self.golden_repos[alias]
        self._save_metadata()

        return {
            "success": True,
            "message": f"Golden repository '{alias}' removed successfully",
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
        except Exception as e:
            raise GitOperationError(f"Failed to copy local repository: {str(e)}")

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

    def _cleanup_repository_files(self, clone_path: str) -> None:
        """
        Clean up repository files and directories using orchestrated cleanup.

        Uses the same approach as 'cidx uninstall' to properly handle root-owned files
        created by Qdrant containers through the data-cleaner service.

        Args:
            clone_path: Path to repository directory to clean up
        """
        if not os.path.exists(clone_path):
            return

        try:
            from pathlib import Path
            from ...services.docker_manager import DockerManager

            # Use the same orchestrated cleanup as 'cidx uninstall'
            clone_path_obj = Path(clone_path)
            project_config_dir = clone_path_obj / ".code-indexer"

            if project_config_dir.exists():
                # Repository has cidx services - use orchestrated cleanup
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

                logging.info(f"Completed orchestrated cleanup for: {clone_path}")

            # After orchestrated cleanup, remove the remaining directory structure
            # This should now work since root-owned files have been cleaned up
            if clone_path_obj.exists():
                shutil.rmtree(clone_path)
                logging.info(f"Successfully cleaned up repository files: {clone_path}")

        except Exception as e:
            # Log the error with more context about the cleanup approach
            logging.error(f"Failed to clean up repository files {clone_path}: {str(e)}")
            logging.info(
                "Note: Golden repo cleanup uses orchestrated approach like 'cidx uninstall'"
            )
            # Re-raise as GitOperationError to ensure proper HTTP status code (500)
            raise GitOperationError(f"Failed to cleanup repository files: {str(e)}")

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
                    # Special handling for cidx index command when no files are found to index
                    if i == 4 and "cidx index" in " ".join(command):
                        # Check both stdout and stderr for the "no files found" message
                        combined_output = result.stdout + result.stderr
                        if "No files found to index" in combined_output:
                            logging.warning(
                                f"Workflow step {i}: Repository has no indexable files - this is acceptable for golden repository registration"
                            )
                            logging.info(
                                f"Workflow step {i} completed with acceptable condition (no indexable files)"
                            )
                        else:
                            # Real indexing error - should fail
                            error_msg = f"Workflow step {i} failed: {' '.join(command)}\nStdout: {result.stdout}\nStderr: {result.stderr}"
                            logging.error(error_msg)
                            raise GitOperationError(error_msg)
                    else:
                        # All other workflow failures are real errors
                        error_msg = f"Workflow step {i} failed: {' '.join(command)}\nStdout: {result.stdout}\nStderr: {result.stderr}"
                        logging.error(error_msg)
                        raise GitOperationError(error_msg)

                logging.info(f"Workflow step {i} completed successfully")

            logging.info(f"Post-clone workflow completed successfully for {clone_path}")

        except subprocess.TimeoutExpired:
            raise GitOperationError("Post-clone workflow timed out")
        except Exception as e:
            raise GitOperationError(f"Post-clone workflow failed: {str(e)}")

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

        except Exception as e:
            error_msg = f"Failed to refresh repository '{alias}': {str(e)}"
            logging.error(error_msg)
            raise GitOperationError(error_msg)
