"""
Generic file identification service that works with or without git.

This service provides a unified interface for file identification and metadata
extraction, automatically detecting git repositories and providing enhanced
metadata when available, while gracefully falling back to filesystem-based
identification when git is not available.
"""

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from ..config import Config
from ..utils.git_runner import run_git_command, is_git_repository


class FileIdentifier:
    """
    Provides git-aware file identification with fallback to filesystem-based identification.

    This class automatically detects whether the project is in a git repository and
    provides enhanced metadata when git is available, while ensuring compatibility
    with non-git projects.
    """

    def __init__(self, project_dir: Path, config: Optional[Config] = None):
        """
        Initialize FileIdentifier with project directory and optional configuration.

        Args:
            project_dir: Path to the project directory
            config: Optional project configuration for file filtering
        """
        self.project_dir = project_dir
        self.config = config
        self.git_available = self._detect_git()
        self._project_id: Optional[str] = None

    def _detect_git(self) -> bool:
        """
        Detect if this project is in a git repository.

        Returns:
            True if git repository is detected, False otherwise
        """
        return is_git_repository(self.project_dir)

    def _get_project_id(self) -> str:
        """
        Get a unique project identifier.

        Returns:
            Project identifier string (git repo name or directory name)
        """
        if self._project_id is not None:
            return self._project_id

        if self.git_available:
            try:
                # Try to get git remote origin URL
                result = run_git_command(
                    ["git", "remote", "get-url", "origin"],
                    cwd=self.project_dir,
                )
                origin_url = result.stdout.strip()

                # Extract repository name from URL
                if origin_url:
                    # Handle various URL formats (https, ssh, etc.)
                    repo_name = origin_url.split("/")[-1]
                    if repo_name.endswith(".git"):
                        repo_name = repo_name[:-4]
                    self._project_id = repo_name.lower().replace("_", "-")
                    assert self._project_id is not None
                    return self._project_id
            except subprocess.CalledProcessError:
                pass

        # Fallback to directory name
        self._project_id = self.project_dir.name.lower().replace("_", "-")
        assert self._project_id is not None
        return self._project_id

    def _get_file_content_hash(self, file_path: Path) -> str:
        """
        Generate SHA256 hash of file content.

        Args:
            file_path: Path to the file

        Returns:
            SHA256 hash of file content with 'sha256:' prefix
        """
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return f"sha256:{hasher.hexdigest()}"
        except (IOError, OSError):
            # Fallback hash for unreadable files
            return f"sha256:error-{abs(hash(str(file_path)))}"

    def _should_index_file(self, file_path: str) -> bool:
        """
        Check if a file should be indexed based on configuration.

        Args:
            file_path: Relative path to the file

        Returns:
            True if file should be indexed, False otherwise
        """
        if not self.config:
            # Default behavior without config - common code extensions
            common_extensions = {
                "py",
                "js",
                "ts",
                "tsx",
                "java",
                "c",
                "cpp",
                "go",
                "rs",
                "rb",
                "php",
                "pl",
                "pm",
                "pod",
                "t",
                "psgi",
                "sh",
                "bash",
                "html",
                "css",
                "md",
                "json",
                "yaml",
                "yml",
            }
            return any(file_path.endswith(f".{ext}") for ext in common_extensions)

        # Use configuration if available
        file_extension = Path(file_path).suffix.lstrip(".")

        # Check if extension is allowed
        if file_extension not in self.config.file_extensions:
            return False

        # Check if path should be excluded
        path_parts = Path(file_path).parts
        for exclude_dir in self.config.exclude_dirs:
            if exclude_dir in path_parts:
                return False

        return True

    def get_file_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Get comprehensive file metadata (git-aware or fallback).

        Args:
            file_path: Path to the file

        Returns:
            Dictionary containing file metadata
        """
        rel_path = str(file_path.relative_to(self.project_dir))

        metadata = {
            "project_id": self._get_project_id(),
            "file_path": rel_path,
            "file_hash": self._get_file_content_hash(file_path),
            "indexed_at": datetime.now(timezone.utc).isoformat() + "Z",
            "git_available": self.git_available,
        }

        if self.git_available:
            metadata.update(self._get_git_metadata(file_path))
        else:
            metadata.update(self._get_filesystem_metadata(file_path))

        return metadata

    def _get_git_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Get git-specific metadata for a file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary containing git metadata
        """
        git_metadata: Dict[str, Optional[str]] = {
            "git_hash": None,
            "branch": None,
            "commit_hash": None,
        }

        try:
            # Get git blob hash for the file
            result = run_git_command(
                ["git", "hash-object", str(file_path)],
                cwd=self.project_dir,
            )
            git_metadata["git_hash"] = result.stdout.strip()
        except subprocess.CalledProcessError:
            pass

        try:
            # Get current branch
            result = run_git_command(
                ["git", "branch", "--show-current"],
                cwd=self.project_dir,
            )
            branch_name = result.stdout.strip()

            # Check if empty (detached HEAD returns empty string, not error)
            if branch_name:
                git_metadata["branch"] = branch_name
            else:
                # Empty means detached HEAD - create synthetic name
                raise subprocess.CalledProcessError(1, "git branch")  # Trigger fallback
        except subprocess.CalledProcessError:
            # Fallback to HEAD for detached HEAD state
            try:
                result = run_git_command(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=self.project_dir,
                )
                git_metadata["branch"] = f"detached-{result.stdout.strip()}"
            except subprocess.CalledProcessError:
                git_metadata["branch"] = "unknown"

        try:
            # Get current commit hash
            result = run_git_command(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_dir,
            )
            git_metadata["commit_hash"] = result.stdout.strip()
        except subprocess.CalledProcessError:
            pass

        return git_metadata

    def _get_filesystem_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Get filesystem-based metadata when git is not available.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary containing filesystem metadata
        """
        try:
            stat = file_path.stat()
            return {"file_mtime": int(stat.st_mtime), "file_size": stat.st_size}
        except (OSError, IOError):
            return {"file_mtime": 0, "file_size": 0}

    def get_current_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all files that should be indexed in the current context.

        For git repositories, this returns files tracked by git in the current branch.
        For non-git projects, this returns all eligible files in the directory tree.

        Returns:
            Dictionary mapping file paths to their metadata
        """
        if self.git_available:
            return self._get_git_tracked_files()
        else:
            return self._get_filesystem_files()

    def _get_git_tracked_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Get files tracked by git in the current HEAD.

        Returns:
            Dictionary mapping file paths to their metadata
        """
        files = {}

        try:
            result = run_git_command(
                ["git", "ls-tree", "-r", "--name-only", "--full-tree", "HEAD"],
                cwd=self.project_dir,
            )

            for file_path_str in result.stdout.strip().split("\n"):
                if file_path_str and self._should_index_file(file_path_str):
                    file_path = self.project_dir / file_path_str
                    if file_path.exists():
                        files[file_path_str] = self.get_file_metadata(file_path)

        except subprocess.CalledProcessError:
            # Fallback to filesystem if git command fails
            return self._get_filesystem_files()

        return files

    def _get_filesystem_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all indexable files from the filesystem recursively.

        Returns:
            Dictionary mapping file paths to their metadata
        """
        files = {}

        for file_path in self.project_dir.rglob("*"):
            if file_path.is_file():
                try:
                    rel_path = str(file_path.relative_to(self.project_dir))
                    if self._should_index_file(rel_path):
                        files[rel_path] = self.get_file_metadata(file_path)
                except (ValueError, OSError):
                    # Skip files that can't be processed
                    continue

        return files

    def get_file_signature(self, metadata: Dict[str, Any]) -> str:
        """
        Get a unique signature for a file based on its content.

        Args:
            metadata: File metadata dictionary

        Returns:
            Unique signature string for the file content
        """
        if metadata.get("git_available") and metadata.get("git_hash"):
            return str(metadata["git_hash"])
        else:
            return str(metadata["file_hash"])

    def create_point_id(self, metadata: Dict[str, Any], chunk_index: int = 0) -> str:
        """
        Create a unique point ID for vector storage.

        Args:
            metadata: File metadata dictionary
            chunk_index: Index of the chunk within the file

        Returns:
            Unique point ID string
        """
        signature = self.get_file_signature(metadata)
        project_id = metadata["project_id"]

        return f"{project_id}:{signature}:{chunk_index}"
