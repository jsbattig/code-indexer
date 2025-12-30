"""
GitOperationsService: Comprehensive git operations service.

Provides 17 git operations across 5 feature groups:
- F2: Status/Inspection (git_status, git_diff, git_log)
- F3: Staging/Commit (git_stage, git_unstage, git_commit)
- F4: Remote Operations (git_push, git_pull, git_fetch)
- F5: Recovery (git_reset, git_clean, git_merge_abort, git_checkout_file)
- F6: Branch Management (git_branch_list, git_branch_create, git_branch_switch, git_branch_delete)

Implements confirmation token system for destructive operations with:
- 6-character alphanumeric tokens
- 5-minute expiration
- Single-use validation
- In-memory storage
"""

import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from cachetools import TTLCache

from code_indexer.config import ConfigManager
from code_indexer.utils.git_runner import run_git_command

# Module logger
logger = logging.getLogger(__name__)

# Timeout constants
DEFAULT_TIMEOUT = 30  # seconds for local git operations
REMOTE_TIMEOUT = 300  # 5 minutes for remote operations (push/pull/fetch)
TOKEN_EXPIRY = 300  # 5 minutes for confirmation tokens


class GitCommandError(Exception):
    """Exception raised when a git command fails."""

    def __init__(
        self,
        message: str,
        stderr: str = "",
        returncode: int = 1,
        command: Optional[List[str]] = None,
        cwd: Optional[Path] = None
    ):
        """
        Initialize GitCommandError.

        Args:
            message: Error message
            stderr: Standard error output from git command
            returncode: Git command return code
            command: The git command that failed
            cwd: Working directory where command was executed
        """
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode
        self.command = command or []
        self.cwd = cwd

    def __str__(self) -> str:
        """Return detailed error message with full context."""
        parts = [super().__str__()]

        if self.command:
            parts.append(f"Command: {' '.join(self.command)}")

        if self.cwd:
            parts.append(f"Working directory: {self.cwd}")

        if self.returncode:
            parts.append(f"Return code: {self.returncode}")

        if self.stderr:
            parts.append(f"stderr: {self.stderr}")

        return " | ".join(parts)


class GitOperationsService:
    """Service for executing git operations with subprocess."""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """
        Initialize GitOperationsService with configuration.

        Args:
            config_manager: ConfigManager instance for loading git service config.
                          If None, creates a new ConfigManager internally.
        """
        # Thread-safe TTLCache for automatic token expiration (Issue #1, #2)
        # maxsize=10000: Reasonable limit for concurrent users
        # ttl=TOKEN_EXPIRY: Automatic cleanup after 5 minutes
        # timer=time.time: Use time.time() for testability (allows mocking)
        self._tokens: TTLCache = TTLCache(maxsize=10000, ttl=TOKEN_EXPIRY, timer=time.time)
        self._tokens_lock = threading.RLock()

        # Create ConfigManager internally if not provided (for REST router compatibility)
        if config_manager is None:
            config_manager = ConfigManager()

        self.config_manager = config_manager
        config = config_manager.load()
        self.git_config = config.git_service

        # Import ActivatedRepoManager for resolving repo aliases to paths
        # (import here to avoid circular imports)
        from ..repositories.activated_repo_manager import ActivatedRepoManager
        self.activated_repo_manager = ActivatedRepoManager()

    # REST API Wrapper Methods (resolve repo_alias to repo_path)

    def _trigger_migration_if_needed(self, repo_path: str, username: str, repo_alias: str) -> None:
        """
        Trigger legacy remote migration if needed (Story #636).

        Checks if the activated repo uses legacy single-remote setup and
        automatically migrates to dual remote setup (origin=GitHub, golden=local).

        Args:
            repo_path: Path to activated repository
            username: Username
            repo_alias: Repository alias

        Note:
            This method silently succeeds if migration is not needed or already done.
            Logs warnings if golden repo metadata is not available.
        """
        try:
            # Get activated repo metadata to find golden repo alias
            from pathlib import Path as PathLib

            user_dir = PathLib(repo_path).parent
            metadata_file = user_dir / f"{repo_alias}_metadata.json"

            if not metadata_file.exists():
                logger.warning(
                    f"Cannot trigger migration: metadata file not found for {username}/{repo_alias}"
                )
                return

            with open(metadata_file, "r") as f:
                repo_data = json.load(f)

            golden_repo_alias = repo_data.get("golden_repo_alias")
            if not golden_repo_alias:
                logger.warning(
                    f"Cannot trigger migration: golden_repo_alias not found in metadata for {username}/{repo_alias}"
                )
                return

            # Get golden repo path from golden repo manager
            if golden_repo_alias not in self.activated_repo_manager.golden_repo_manager.golden_repos:
                logger.warning(
                    f"Cannot trigger migration: golden repo '{golden_repo_alias}' not found for {username}/{repo_alias}"
                )
                return

            golden_repo = self.activated_repo_manager.golden_repo_manager.golden_repos[golden_repo_alias]

            # Use canonical path resolution to handle versioned repos (Bug #3, #4 fix)
            golden_repo_path = self.activated_repo_manager.golden_repo_manager.get_actual_repo_path(golden_repo_alias)

            # Trigger migration via ActivatedRepoManager
            migrated = self.activated_repo_manager._detect_and_migrate_legacy_remotes(
                repo_path, golden_repo_path
            )

            if migrated:
                logger.info(
                    f"Automatically migrated legacy remotes for {username}/{repo_alias}"
                )

        except Exception as e:
            # Don't fail the git operation if migration check fails
            logger.warning(
                f"Failed to check/trigger migration for {username}/{repo_alias}: {str(e)}"
            )

    def get_status(self, repo_alias: str, username: str) -> Dict[str, Any]:
        """
        Get git status for an activated repository (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup

        Returns:
            Git status dictionary with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git status fails
        """
        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_status(Path(repo_path))
        result["success"] = True
        return result

    def get_diff(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get git diff for an activated repository (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments passed to git_diff
                     (file_paths, context_lines, from_revision, to_revision, path, stat_only, etc.)

        Returns:
            Git diff dictionary with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git diff fails
        """
        # Extract file_paths if present
        file_paths = kwargs.pop("file_paths", None)

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_diff(Path(repo_path), file_paths=file_paths, **kwargs)
        result["success"] = True
        return result

    def get_log(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get git log for an activated repository (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments passed to git_log
                     (limit, since, until, path, author, branch, etc.)
                     Note: 'since' parameter is mapped to 'since_date' internally

        Returns:
            Git log dictionary with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git log fails
        """
        # Map REST parameter name to service method name
        if "since" in kwargs:
            kwargs["since_date"] = kwargs.pop("since")

        # Extract limit with default
        limit = kwargs.pop("limit", 10)

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_log(Path(repo_path), limit=limit, **kwargs)
        result["success"] = True
        return result

    # F3: Staging/Commit Wrapper Methods

    def stage_files(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Stage files for commit (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (file_paths)

        Returns:
            Git stage result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git add fails
        """
        file_paths = kwargs.get("file_paths", [])
        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_stage(Path(repo_path), file_paths=file_paths)
        result["success"] = True
        return result

    def unstage_files(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Unstage files (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (file_paths)

        Returns:
            Git unstage result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git reset fails
        """
        file_paths = kwargs.get("file_paths", [])
        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_unstage(Path(repo_path), file_paths=file_paths)
        result["success"] = True
        return result

    def create_commit(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a git commit (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (message, user_email, user_name)

        Returns:
            Git commit result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git commit fails
            ValueError: If user_email or user_name fail validation
        """
        message = kwargs.get("message", "")
        # Support both author_email (from REST API) and user_email (legacy MCP)
        user_email = kwargs.get("author_email") or kwargs.get("user_email") or None
        # Support both author_name (from REST API) and user_name (legacy MCP)
        user_name = kwargs.get("author_name") or kwargs.get("user_name") or None

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )

        # If email/name not provided, use git config as fallback
        if not user_email or not user_name:
            try:
                if not user_email:
                    user_email = subprocess.check_output(
                        ["git", "config", "user.email"],
                        cwd=repo_path,
                        text=True
                    ).strip()
                    logger.debug(f"Using git config user.email: {user_email}")
                if not user_name:
                    user_name = subprocess.check_output(
                        ["git", "config", "user.name"],
                        cwd=repo_path,
                        text=True
                    ).strip()
                    logger.debug(f"Using git config user.name: {user_name}")
            except subprocess.CalledProcessError as e:
                logger.debug(
                    f"Git config user.email/user.name not found: {e}. "
                    "Will use provided values (may fail validation if empty)."
                )

        result = self.git_commit(
            Path(repo_path),
            message=message,
            user_email=user_email or "",
            user_name=user_name
        )
        result["success"] = True
        return result

    # F4: Remote Operations Wrapper Methods

    def push_to_remote(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Push commits to remote repository (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (remote, branch)

        Returns:
            Git push result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git push fails
        """
        remote = kwargs.get("remote", "origin")
        branch = kwargs.get("branch")

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )

        # Story #636: Trigger migration before push if needed
        self._trigger_migration_if_needed(repo_path, username, repo_alias)

        result = self.git_push(Path(repo_path), remote=remote, branch=branch)
        result["success"] = True
        return result

    def pull_from_remote(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Pull updates from remote repository (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (remote, branch)

        Returns:
            Git pull result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git pull fails
        """
        remote = kwargs.get("remote", "origin")
        branch = kwargs.get("branch")

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )

        # Story #636: Trigger migration before pull if needed
        self._trigger_migration_if_needed(repo_path, username, repo_alias)

        result = self.git_pull(Path(repo_path), remote=remote, branch=branch)
        result["success"] = True
        return result

    def fetch_from_remote(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Fetch updates from remote repository (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (remote)

        Returns:
            Git fetch result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git fetch fails
        """
        remote = kwargs.get("remote", "origin")

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )

        # Story #636: Trigger migration before fetch if needed
        self._trigger_migration_if_needed(repo_path, username, repo_alias)

        result = self.git_fetch(Path(repo_path), remote=remote)
        result["success"] = True
        return result

    # F5: Recovery Operations Wrapper Methods

    def reset_repository(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Reset repository to a specific commit (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (mode, commit_hash, confirmation_token)

        Returns:
            Git reset result with success field OR requires_confirmation/token

        Raises:
            FileNotFoundError: If repository not found
            ValueError: If hard reset attempted without valid token
            GitCommandError: If git reset fails
        """
        mode = kwargs.get("mode", "mixed")
        commit_hash = kwargs.get("commit_hash")
        confirmation_token = kwargs.get("confirmation_token")

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_reset(
            Path(repo_path),
            mode=mode,
            commit_hash=commit_hash,
            confirmation_token=confirmation_token
        )
        # Note: result already contains success field from git_reset
        # or requires_confirmation/token for hard reset
        return result

    def clean_repository(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Remove untracked files and directories (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (confirmation_token)

        Returns:
            Git clean result with success field OR requires_confirmation/token

        Raises:
            FileNotFoundError: If repository not found
            ValueError: If attempted without valid token
            GitCommandError: If git clean fails
        """
        confirmation_token = kwargs.get("confirmation_token")

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_clean(
            Path(repo_path),
            confirmation_token=confirmation_token
        )
        # Note: result already contains success field from git_clean
        # or requires_confirmation/token
        return result

    def abort_merge(
        self,
        repo_alias: str,
        username: str
    ) -> Dict[str, Any]:
        """
        Abort an in-progress merge (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup

        Returns:
            Git merge abort result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git merge --abort fails
        """
        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_merge_abort(Path(repo_path))
        result["success"] = True
        return result

    def checkout_file(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Restore file(s) to HEAD state (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (file_paths)

        Returns:
            Git checkout result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git checkout fails
        """
        file_paths = kwargs.get("file_paths", [])

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )

        # git_checkout_file expects a single file_path string, not a list
        # For REST API compatibility, we accept file_paths list and process first file
        # TODO: Enhance git_checkout_file to support multiple files
        file_path = file_paths[0] if file_paths else ""

        result = self.git_checkout_file(Path(repo_path), file_path=file_path)
        result["success"] = True
        return result

    # F6: Branch Management Wrapper Methods

    def list_branches(
        self,
        repo_alias: str,
        username: str
    ) -> Dict[str, Any]:
        """
        List all branches (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup

        Returns:
            Git branch list with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git branch fails
        """
        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_branch_list(Path(repo_path))
        result["success"] = True
        return result

    def create_branch(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a new branch (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (branch_name)

        Returns:
            Git branch create result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git branch fails
        """
        branch_name = kwargs.get("branch_name", "")

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_branch_create(Path(repo_path), branch_name=branch_name)
        result["success"] = True
        return result

    def switch_branch(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Switch to a different branch (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (branch_name)

        Returns:
            Git branch switch result with success field

        Raises:
            FileNotFoundError: If repository not found
            GitCommandError: If git checkout/switch fails
        """
        branch_name = kwargs.get("branch_name", "")

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_branch_switch(Path(repo_path), branch_name=branch_name)
        result["success"] = True
        return result

    def delete_branch(
        self,
        repo_alias: str,
        username: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Delete a branch (REST API wrapper).

        Args:
            repo_alias: User's repository alias
            username: Username for repository lookup
            **kwargs: Additional arguments (branch_name, confirmation_token)

        Returns:
            Git branch delete result with success field OR requires_confirmation/token

        Raises:
            FileNotFoundError: If repository not found
            ValueError: If attempted without valid token
            GitCommandError: If git branch delete fails
        """
        branch_name = kwargs.get("branch_name", "")
        confirmation_token = kwargs.get("confirmation_token")

        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )
        result = self.git_branch_delete(
            Path(repo_path),
            branch_name=branch_name,
            confirmation_token=confirmation_token
        )
        # Note: result already contains success field from git_branch_delete
        # or requires_confirmation/token
        return result

    # F2: Status/Inspection Operations

    def git_status(self, repo_path: Path) -> Dict[str, Any]:
        """
        Get git repository status.

        Args:
            repo_path: Path to git repository

        Returns:
            Dict with staged, unstaged, and untracked file lists

        Raises:
            GitCommandError: If git status fails
        """
        try:
            cmd = ["git", "status", "--porcelain=v1"]
            result = run_git_command(
                cmd,
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            # Parse porcelain v1 format: XY PATH
            # X = staged status, Y = unstaged status
            staged = []
            unstaged = []
            untracked = []

            for line in result.stdout.splitlines():
                if not line:
                    continue

                status_code = line[:2]
                file_path = line[3:]

                # Staged files (first character)
                if status_code[0] in 'MADRC':
                    staged.append(file_path)

                # Unstaged files (second character)
                if status_code[1] in 'MADRC':
                    unstaged.append(file_path)

                # Untracked files
                if status_code == '??':
                    untracked.append(file_path)

            return {
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git status failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode,
                command=cmd,
                cwd=repo_path
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git status timed out after {e.timeout}s",
                stderr="",
                command=cmd,
                cwd=repo_path
            )

    def git_diff(
        self,
        repo_path: Path,
        file_paths: Optional[List[str]] = None,
        context_lines: Optional[int] = None,
        from_revision: Optional[str] = None,
        to_revision: Optional[str] = None,
        path: Optional[str] = None,
        stat_only: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Get git diff output.

        Args:
            repo_path: Path to git repository
            file_paths: Optional list of specific files to diff
            context_lines: Number of context lines to show (uses -U flag)
            from_revision: Starting revision for diff
            to_revision: Ending revision for diff (requires from_revision)
            path: Specific path to limit diff to
            stat_only: Show only file statistics (--stat flag)

        Returns:
            Dict with diff_text and files_changed count

        Raises:
            GitCommandError: If git diff fails
        """
        try:
            cmd = ["git", "diff"]

            # Add context lines flag
            if context_lines is not None:
                cmd.append(f"-U{context_lines}")

            # Add stat flag
            if stat_only:
                cmd.append("--stat")

            # Add revision range or single revision
            if from_revision and to_revision:
                cmd.append(f"{from_revision}..{to_revision}")
            elif from_revision:
                cmd.append(from_revision)

            # Add path filter with -- separator
            if path:
                cmd.append("--")
                cmd.append(path)
            elif file_paths:
                # Legacy file_paths parameter (kept for backward compatibility)
                cmd.extend(file_paths)

            result = run_git_command(
                cmd,
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            diff_text = result.stdout
            files_changed = diff_text.count("diff --git")

            return {
                "diff_text": diff_text,
                "files_changed": files_changed
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git diff failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode,
                command=["git", "diff"],
                cwd=repo_path
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git diff timed out after {e.timeout}s",
                stderr="",
                command=["git", "diff"],
                cwd=repo_path
            )

    def git_log(
        self,
        repo_path: Path,
        limit: int = 10,
        since_date: Optional[str] = None,
        until: Optional[str] = None,
        author: Optional[str] = None,
        branch: Optional[str] = None,
        path: Optional[str] = None,
        aggregation_mode: Optional[str] = None,
        response_format: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get git commit history.

        Args:
            repo_path: Path to git repository
            limit: Maximum number of commits to return
            since_date: Optional date filter for commits after this date (e.g., "2025-01-10")
            until: Optional date filter for commits before this date
            author: Optional author filter
            branch: Optional branch to get log from
            path: Optional path filter to show only commits affecting this path
            aggregation_mode: Optional MCP aggregation mode (affects response formatting)
            response_format: Optional MCP response format (affects response structure)

        Returns:
            Dict with commits list

        Raises:
            GitCommandError: If git log fails
        """
        try:
            format_str = '{"commit_hash": "%H", "author": "%an", "date": "%ai", "message": "%s"}'
            cmd = ["git", "log", f"--format={format_str}", f"-n{limit}"]

            # Add date filters
            if since_date:
                cmd.append(f"--since={since_date}")
            if until:
                cmd.append(f"--until={until}")

            # Add author filter
            if author:
                cmd.append(f"--author={author}")

            # Add branch specifier (must come before path separator)
            if branch:
                cmd.append(branch)

            # Add path filter with -- separator
            if path:
                cmd.append("--")
                cmd.append(path)

            result = run_git_command(
                cmd,
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            commits = []
            for line in result.stdout.splitlines():
                if line.strip():
                    try:
                        commit = json.loads(line)
                        commits.append(commit)
                    except json.JSONDecodeError:
                        continue

            # Note: aggregation_mode and response_format are accepted for MCP compatibility
            # but not implemented yet. They would affect post-processing of commits list.
            # For now, we return standard format regardless of these parameters.

            return {"commits": commits}

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git log failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode,
                command=["git", "log"],
                cwd=repo_path
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git log timed out after {e.timeout}s",
                stderr="",
                command=["git", "log"],
                cwd=repo_path
            )

    # F3: Staging/Commit Operations

    def git_stage(self, repo_path: Path, file_paths: List[str]) -> Dict[str, Any]:
        """
        Stage files for commit.

        Args:
            repo_path: Path to git repository
            file_paths: List of file paths to stage

        Returns:
            Dict with success flag and staged_files list

        Raises:
            GitCommandError: If git add fails
        """
        try:
            cmd = ["git", "add"] + file_paths

            run_git_command(
                cmd,
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            return {
                "success": True,
                "staged_files": file_paths
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git add failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git add timed out after {e.timeout}s",
                stderr=""
            )

    def git_unstage(self, repo_path: Path, file_paths: List[str]) -> Dict[str, Any]:
        """
        Unstage files.

        Args:
            repo_path: Path to git repository
            file_paths: List of file paths to unstage

        Returns:
            Dict with success flag and unstaged_files list

        Raises:
            GitCommandError: If git reset fails
        """
        try:
            cmd = ["git", "reset", "HEAD"] + file_paths

            run_git_command(
                cmd,
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            return {
                "success": True,
                "unstaged_files": file_paths
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git reset HEAD failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git reset timed out after {e.timeout}s",
                stderr=""
            )

    def git_commit(
        self,
        repo_path: Path,
        message: str,
        user_email: str,
        user_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a git commit with dual attribution.

        Uses dual attribution model:
        - Git Author: user_email parameter (actual Claude.ai user)
        - Git Committer: Service account from config (matches SSH key owner)
        - Commit message: Injects AUTHOR prefix for audit trail

        Args:
            repo_path: Path to git repository
            message: Commit message (user's actual message)
            user_email: Email of actual user (Claude.ai user) - becomes Git author
            user_name: Optional user name (derived from email if not provided)

        Returns:
            Dict with success, commit_hash, message, author, and committer

        Raises:
            GitCommandError: If git commit fails
            ValueError: If user_email or user_name fail validation
        """
        try:
            # Validate user_email (RFC 5322 basic format)
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, user_email):
                raise ValueError(f"Invalid email format: {user_email}")

            # Derive author name from email if not provided
            if not user_name:
                user_name = user_email.split("@")[0]

            # Validate user_name (alphanumeric + space, hyphen, underscore only)
            name_pattern = r'^[a-zA-Z0-9 _-]+$'
            if not re.match(name_pattern, user_name):
                raise ValueError(f"Invalid user name format: {user_name}")

            # Sanitize user message to prevent trailer injection
            # Remove any lines that look like our trailers to prevent forgery
            sanitized_lines = []
            for line in message.split("\n"):
                # Strip lines that start with our reserved trailer keys
                if not line.startswith("Actual-Author:") and not line.startswith("Committed-Via:"):
                    sanitized_lines.append(line)
            sanitized_message = "\n".join(sanitized_lines)

            # Use Git trailers format (injection-safe)
            # Git trailers: https://git-scm.com/docs/git-interpret-trailers
            # Format: Key: value (no prefix ambiguity, structured metadata)
            attributed_message = f"{sanitized_message}\n\nActual-Author: {user_email}\nCommitted-Via: CIDX API"

            # Set Git identity via environment variables
            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = user_name
            env["GIT_AUTHOR_EMAIL"] = user_email
            env["GIT_COMMITTER_NAME"] = self.git_config.service_committer_name
            env["GIT_COMMITTER_EMAIL"] = self.git_config.service_committer_email

            cmd = ["git", "commit", "-m", attributed_message]

            result = run_git_command(
                cmd,
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True,
                env=env
            )

            # Get full commit hash using git rev-parse HEAD
            # (git commit output only shows short hash)
            hash_result = run_git_command(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )
            commit_hash = hash_result.stdout.strip()

            return {
                "success": True,
                "commit_hash": commit_hash,
                "message": message,
                "author": user_email,
                "committer": self.git_config.service_committer_email
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git commit failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git commit timed out after {e.timeout}s",
                stderr=""
            )

    # F4: Remote Operations

    def git_push(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Push commits to remote repository.

        Args:
            repo_path: Path to git repository
            remote: Remote name (default: "origin")
            branch: Optional branch name

        Returns:
            Dict with success flag and pushed_commits count

        Raises:
            GitCommandError: If git push fails
        """
        try:
            cmd = ["git", "push", remote]
            if branch:
                cmd.append(branch)

            result = run_git_command(
                cmd,
                cwd=repo_path,
                timeout=REMOTE_TIMEOUT,
                check=True
            )

            pushed_commits = 0
            if ".." in result.stdout:
                pushed_commits = 1

            return {
                "success": True,
                "pushed_commits": pushed_commits
            }

        except subprocess.CalledProcessError as e:
            stderr = getattr(e, 'stderr', '')

            if "Authentication" in stderr or "Permission denied" in stderr:
                raise GitCommandError(
                    f"git push authentication failed: {stderr}",
                    stderr=stderr,
                    returncode=e.returncode
                )
            elif "Could not resolve host" in stderr or "Network" in stderr:
                raise GitCommandError(
                    f"git push network error: {stderr}",
                    stderr=stderr,
                    returncode=e.returncode
                )
            else:
                raise GitCommandError(
                    f"git push failed: {e}",
                    stderr=stderr,
                    returncode=e.returncode
                )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git push timed out after {e.timeout}s",
                stderr=""
            )

    def git_pull(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Pull updates from remote repository.

        Args:
            repo_path: Path to git repository
            remote: Remote name (default: "origin")
            branch: Optional branch name

        Returns:
            Dict with success, updated_files count, and conflicts list

        Raises:
            GitCommandError: If git pull fails
        """
        try:
            cmd = ["git", "pull", remote]
            if branch:
                cmd.append(branch)

            result = run_git_command(
                cmd,
                cwd=repo_path,
                timeout=REMOTE_TIMEOUT,
                check=False
            )

            conflicts = []
            if result.returncode != 0 or "CONFLICT" in result.stdout:
                for line in result.stdout.splitlines():
                    if "CONFLICT" in line:
                        match = re.search(r'Merge conflict in (.+)', line)
                        if match:
                            conflicts.append(match.group(1))

            updated_files = 0
            if "file changed" in result.stdout or "files changed" in result.stdout:
                match = re.search(r'(\d+) files? changed', result.stdout)
                if match:
                    updated_files = int(match.group(1))

            return {
                "success": result.returncode == 0 and not conflicts,
                "updated_files": updated_files,
                "conflicts": conflicts
            }

        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git pull timed out after {e.timeout}s",
                stderr=""
            )

    def git_fetch(
        self,
        repo_path: Path,
        remote: str = "origin"
    ) -> Dict[str, Any]:
        """
        Fetch updates from remote repository.

        Args:
            repo_path: Path to git repository
            remote: Remote name (default: "origin")

        Returns:
            Dict with success flag and fetched_refs list

        Raises:
            GitCommandError: If git fetch fails
        """
        try:
            result = run_git_command(
                ["git", "fetch", remote],
                cwd=repo_path,
                timeout=REMOTE_TIMEOUT,
                check=True
            )

            fetched_refs = []
            for line in result.stdout.splitlines():
                if " -> " in line or "FETCH_HEAD" in line:
                    fetched_refs.append(line.strip())

            return {
                "success": True,
                "fetched_refs": fetched_refs
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git fetch failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git fetch timed out after {e.timeout}s",
                stderr=""
            )

    # F5: Recovery Operations

    def git_reset(
        self,
        repo_path: Path,
        mode: str,
        commit_hash: Optional[str] = None,
        confirmation_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reset repository to a specific commit.

        Args:
            repo_path: Path to git repository
            mode: Reset mode ("soft", "mixed", "hard")
            commit_hash: Optional commit hash (default: HEAD)
            confirmation_token: Required for hard reset

        Returns:
            Dict with success/reset_mode/target_commit OR requires_confirmation/token

        Raises:
            ValueError: If hard reset attempted without valid token
            GitCommandError: If git reset fails
        """
        if mode == "hard":
            if not confirmation_token:
                token = self._generate_confirmation_token("git_reset_hard")
                return {
                    "requires_confirmation": True,
                    "token": token
                }

            if not self._validate_confirmation_token("git_reset_hard", confirmation_token):
                raise ValueError("Invalid or expired confirmation token")

        try:
            target = commit_hash or "HEAD"
            cmd = ["git", "reset", f"--{mode}", target]

            run_git_command(
                cmd,
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            return {
                "success": True,
                "reset_mode": mode,
                "target_commit": target
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git reset failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git reset timed out after {e.timeout}s",
                stderr=""
            )

    def git_clean(
        self,
        repo_path: Path,
        confirmation_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Remove untracked files and directories.

        Args:
            repo_path: Path to git repository
            confirmation_token: Required for this destructive operation

        Returns:
            Dict with success/removed_files OR requires_confirmation/token

        Raises:
            ValueError: If attempted without valid token
            GitCommandError: If git clean fails
        """
        if not confirmation_token:
            token = self._generate_confirmation_token("git_clean")
            return {
                "requires_confirmation": True,
                "token": token
            }

        if not self._validate_confirmation_token("git_clean", confirmation_token):
            raise ValueError("Invalid or expired confirmation token")

        try:
            result = run_git_command(
                ["git", "clean", "-fd"],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            removed_files = []
            for line in result.stdout.splitlines():
                if line.startswith("Removing "):
                    file_path = line.replace("Removing ", "").strip()
                    removed_files.append(file_path)

            return {
                "success": True,
                "removed_files": removed_files
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git clean failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git clean timed out after {e.timeout}s",
                stderr=""
            )

    def git_merge_abort(self, repo_path: Path) -> Dict[str, Any]:
        """
        Abort an in-progress merge.

        Args:
            repo_path: Path to git repository

        Returns:
            Dict with success flag and aborted flag

        Raises:
            GitCommandError: If git merge --abort fails
        """
        try:
            run_git_command(
                ["git", "merge", "--abort"],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            return {
                "success": True,
                "aborted": True
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git merge --abort failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git merge --abort timed out after {e.timeout}s",
                stderr=""
            )

    def git_checkout_file(
        self,
        repo_path: Path,
        file_path: str
    ) -> Dict[str, Any]:
        """
        Restore a file to its HEAD state.

        Args:
            repo_path: Path to git repository
            file_path: File to restore

        Returns:
            Dict with success flag and restored_file path

        Raises:
            GitCommandError: If git checkout fails
        """
        try:
            run_git_command(
                ["git", "checkout", "HEAD", "--", file_path],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            return {
                "success": True,
                "restored_file": file_path
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git checkout file failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git checkout timed out after {e.timeout}s",
                stderr=""
            )

    # F6: Branch Management Operations

    def git_branch_list(self, repo_path: Path) -> Dict[str, Any]:
        """
        List all branches (local and remote).

        Args:
            repo_path: Path to git repository

        Returns:
            Dict with current branch, local branches, and remote branches

        Raises:
            GitCommandError: If git branch fails
        """
        try:
            result = run_git_command(
                ["git", "branch", "-a"],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            current_branch = ""
            local_branches = []
            remote_branches = []

            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue

                if line.startswith("* "):
                    current_branch = line[2:].strip()
                    local_branches.append(current_branch)
                elif line.startswith("remotes/"):
                    remote_branch = line.replace("remotes/", "").strip()
                    remote_branches.append(remote_branch)
                else:
                    local_branches.append(line)

            return {
                "current": current_branch,
                "local": local_branches,
                "remote": remote_branches
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git branch list failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git branch list timed out after {e.timeout}s",
                stderr=""
            )

    def git_branch_create(
        self,
        repo_path: Path,
        branch_name: str
    ) -> Dict[str, Any]:
        """
        Create a new branch.

        Args:
            repo_path: Path to git repository
            branch_name: Name for new branch

        Returns:
            Dict with success flag and created_branch name

        Raises:
            GitCommandError: If git branch fails
        """
        try:
            run_git_command(
                ["git", "branch", branch_name],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            return {
                "success": True,
                "created_branch": branch_name
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git branch create failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git branch create timed out after {e.timeout}s",
                stderr=""
            )

    def git_branch_switch(
        self,
        repo_path: Path,
        branch_name: str
    ) -> Dict[str, Any]:
        """
        Switch to a different branch.

        Args:
            repo_path: Path to git repository
            branch_name: Branch to switch to

        Returns:
            Dict with success, current_branch, and previous_branch

        Raises:
            GitCommandError: If git checkout/switch fails
        """
        try:
            # Get current branch first
            current_result = run_git_command(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )
            previous_branch = current_result.stdout.strip()

            # Switch branch
            run_git_command(
                ["git", "checkout", branch_name],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            return {
                "success": True,
                "current_branch": branch_name,
                "previous_branch": previous_branch
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git branch switch failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git branch switch timed out after {e.timeout}s",
                stderr=""
            )

    def git_branch_delete(
        self,
        repo_path: Path,
        branch_name: str,
        confirmation_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete a branch.

        Args:
            repo_path: Path to git repository
            branch_name: Branch to delete
            confirmation_token: Required for this destructive operation

        Returns:
            Dict with success/deleted_branch OR requires_confirmation/token

        Raises:
            ValueError: If attempted without valid token
            GitCommandError: If git branch delete fails
        """
        if not confirmation_token:
            token = self._generate_confirmation_token("git_branch_delete")
            return {
                "requires_confirmation": True,
                "token": token
            }

        if not self._validate_confirmation_token("git_branch_delete", confirmation_token):
            raise ValueError("Invalid or expired confirmation token")

        try:
            run_git_command(
                ["git", "branch", "-d", branch_name],
                cwd=repo_path,
                timeout=DEFAULT_TIMEOUT,
                check=True
            )

            return {
                "success": True,
                "deleted_branch": branch_name
            }

        except subprocess.CalledProcessError as e:
            raise GitCommandError(
                f"git branch delete failed: {e}",
                stderr=getattr(e, 'stderr', ''),
                returncode=e.returncode
            )
        except subprocess.TimeoutExpired as e:
            raise GitCommandError(
                f"git branch delete timed out after {e.timeout}s",
                stderr=""
            )

    # Confirmation Token System

    def _generate_confirmation_token(self, operation: str) -> str:
        """
        Generate a 6-character confirmation token (thread-safe).

        Args:
            operation: Operation name for token validation

        Returns:
            6-character alphanumeric token
        """
        # Generate 6-character token using uppercase letters and digits
        # Excluding ambiguous characters: 0, O, I, 1
        chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        token = ''.join(secrets.choice(chars) for _ in range(6))

        # Thread-safe token storage (TTLCache handles expiration automatically)
        with self._tokens_lock:
            # Store only operation name - TTLCache handles expiry via its TTL parameter
            self._tokens[token] = operation

        return token

    def _validate_confirmation_token(self, operation: str, token: str) -> bool:
        """
        Validate a confirmation token (thread-safe, single-use).

        Args:
            operation: Expected operation name
            token: Token to validate

        Returns:
            True if token is valid and not expired, False otherwise
        """
        # Thread-safe token validation
        with self._tokens_lock:
            # TTLCache automatically removes expired entries on access
            if token not in self._tokens:
                return False

            stored_operation = self._tokens[token]

            # Check operation match
            if stored_operation != operation:
                return False

            # Token is valid - consume it (single-use)
            del self._tokens[token]
            return True


# Global service instance (lazy initialization to avoid circular imports)
_git_operations_service_instance = None


def _get_git_operations_service():
    """Get or create the global GitOperationsService instance."""
    global _git_operations_service_instance
    if _git_operations_service_instance is None:
        _git_operations_service_instance = GitOperationsService(ConfigManager())
    return _git_operations_service_instance


# Global service instance for easy import
git_operations_service = _get_git_operations_service()
