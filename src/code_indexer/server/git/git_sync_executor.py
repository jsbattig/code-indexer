"""
Git Pull Operations Implementation for CIDX Server Repository Sync.

This module implements Story 4: Git Pull Operations with comprehensive support for:
- Clean working directory git pull operations
- Error detection and detailed reporting
- Multiple merge strategies (fast-forward, merge, rebase)
- Repository state validation
- Progress reporting integration
- Authentication for private repositories
- Backup/snapshot creation before pulls
- Comprehensive error handling and logging
"""

from code_indexer.server.middleware.correlation import get_correlation_id
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from ...utils.git_runner import (
    run_git_command,
    is_git_repository,
    get_current_branch,
    get_current_commit,
)
from ..services.git_state_manager import GitStateManager
from ..utils.config_manager import ServerConfigManager


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class GitSyncResult:
    """Result of a git pull/sync operation."""

    success: bool
    changes_detected: bool
    merge_strategy: str
    backup_created: bool
    indexing_triggered: bool = False
    backup_path: Optional[str] = None
    execution_time: float = 0.0
    files_changed: List[str] = field(default_factory=list)
    commits_pulled: int = 0
    before_commit: Optional[str] = None
    after_commit: Optional[str] = None


@dataclass
class RepositoryValidationResult:
    """Result of repository state validation."""

    is_valid: bool
    can_pull: bool
    has_uncommitted_changes: bool = False
    is_detached_head: bool = False
    is_behind_remote: bool = False
    validation_errors: List[str] = field(default_factory=list)
    branch_name: Optional[str] = None
    commit_hash: Optional[str] = None


@dataclass
class BackupResult:
    """Result of backup operation."""

    success: bool
    backup_path: Optional[str] = None
    error_message: Optional[str] = None
    backup_size_mb: float = 0.0
    files_backed_up: int = 0


class GitSyncError(Exception):
    """Exception raised during git sync operations."""

    def __init__(
        self,
        message: str,
        error_code: str,
        conflicted_files: Optional[List[str]] = None,
        recovery_suggestions: Optional[List[str]] = None,
        git_output: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.conflicted_files = conflicted_files or []
        self.recovery_suggestions = recovery_suggestions or []
        self.git_output = git_output


class GitSyncExecutor:
    """
    Comprehensive git pull operations executor.
    Handles reliable git pull operations with authentication, backup,
    progress reporting, and comprehensive error handling.
    """

    # Class-level lock for concurrent operation protection
    _repository_locks: Dict[str, threading.Lock] = {}
    _locks_lock = threading.Lock()

    def __init__(
        self,
        repository_path: Path,
        backup_dir: Optional[Path] = None,
        auto_index_on_changes: bool = True,
    ):
        """
        Initialize GitSyncExecutor.

        Args:
            repository_path: Path to the git repository
            backup_dir: Optional directory for backups (defaults to repo/.git/cidx_backups)
            auto_index_on_changes: Automatically trigger cidx index when changes detected
        """
        self.repository_path = Path(repository_path).resolve()
        self.backup_dir = backup_dir or self.repository_path / ".git" / "cidx_backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.auto_index_on_changes = auto_index_on_changes

        # Authentication configuration
        self.auth_config: Dict[str, Dict[str, Any]] = {"ssh": {}, "https": {}}

        # Validate repository
        if not is_git_repository(self.repository_path):
            raise GitSyncError(
                f"Path is not a git repository: {self.repository_path}",
                "INVALID_REPOSITORY",
            )

        logger.info(
            f"GitSyncExecutor initialized for repository: {self.repository_path}",
            extra={"correlation_id": get_correlation_id()},
        )

    def execute_pull(
        self,
        merge_strategy: str = "fast-forward",
        progress_callback: Optional[Callable[[int, int, Path, str], None]] = None,
    ) -> GitSyncResult:
        """
        Execute git pull operation with comprehensive handling.

        Args:
            merge_strategy: Merge strategy ('fast-forward', 'merge', 'rebase')
            progress_callback: Optional callback for progress reporting

        Returns:
            GitSyncResult with operation details

        Raises:
            GitSyncError: If pull operation fails
        """
        start_time = time.time()

        # Validate repository state
        if progress_callback:
            progress_callback(0, 0, Path(""), "Validating repository state")

        validation = self.validate_repository_state()

        # Story #659 Priority 5: Clear dirty repo before pull if behind remote
        if (
            validation.has_uncommitted_changes
            and validation.is_behind_remote
            and not validation.can_pull
        ):
            logger.info(
                "Repository is dirty and behind remote - triggering pre-pull clearing",
                extra={"correlation_id": get_correlation_id()},
            )
            try:
                config = ServerConfigManager().load_config()
                git_manager = GitStateManager(config=config)
                git_manager.clear_repo_before_refresh(repo_path=self.repository_path)
                logger.info(
                    "Pre-pull clearing completed - re-validating repository",
                    extra={"correlation_id": get_correlation_id()},
                )

                # Re-validate after clearing
                validation = self.validate_repository_state()

            except Exception as e:
                # Clearing errors are logged but not propagated
                # Validation will still fail if repo remains dirty
                logger.error(
                    f"Pre-pull clearing failed (non-blocking): {e}",
                    exc_info=True,
                    extra={"correlation_id": get_correlation_id()},
                )

        if not validation.can_pull:
            raise GitSyncError(
                f"Repository not ready for pull: {', '.join(validation.validation_errors)}",
                "VALIDATION_FAILED",
                recovery_suggestions=[
                    "Commit or stash uncommitted changes",
                    "Check repository state with 'git status'",
                ],
            )

        # Create backup before pull
        if progress_callback:
            progress_callback(0, 0, Path(""), "Creating pre-pull backup")

        backup_result = self.create_backup()

        # Get initial state
        before_commit = get_current_commit(self.repository_path)

        # Acquire repository lock
        repo_key = str(self.repository_path)
        with self._locks_lock:
            if repo_key not in self._repository_locks:
                self._repository_locks[repo_key] = threading.Lock()
            repo_lock = self._repository_locks[repo_key]

        if not repo_lock.acquire(blocking=False):
            raise GitSyncError(
                f"Another git operation is in progress on repository: {self.repository_path}",
                "CONCURRENT_OPERATION",
                recovery_suggestions=["Wait for other operation to complete"],
            )

        try:
            # Execute git pull with strategy
            if progress_callback:
                progress_callback(
                    1, 4, Path(""), f"Executing git pull ({merge_strategy})"
                )

            self._execute_git_pull(merge_strategy)

            if progress_callback:
                progress_callback(2, 4, Path(""), "Analyzing changes")

            # Get final state
            after_commit = get_current_commit(self.repository_path)

            # Simple change detection: did anything change?
            if before_commit is None or after_commit is None:
                # Can't determine changes without commit info
                changes_detected = False
                files_changed = []
                commits_pulled = 0
            else:
                changes_detected = before_commit != after_commit
                files_changed = (
                    self._get_changed_files(before_commit, after_commit)
                    if changes_detected
                    else []
                )
                commits_pulled = (
                    self._count_commits_pulled(before_commit, after_commit)
                    if changes_detected
                    else 0
                )

            # Auto-trigger indexing if changes detected
            indexing_triggered = False
            if changes_detected and self.auto_index_on_changes:
                if progress_callback:
                    progress_callback(
                        3, 4, Path(""), "Changes detected - triggering cidx index"
                    )
                indexing_triggered = self._trigger_cidx_index()

            if progress_callback:
                progress_callback(4, 4, Path(""), "Pull completed successfully")

            execution_time = time.time() - start_time

            return GitSyncResult(
                success=True,
                changes_detected=changes_detected,
                merge_strategy=merge_strategy,
                backup_created=backup_result.success,
                indexing_triggered=indexing_triggered,
                backup_path=backup_result.backup_path,
                execution_time=execution_time,
                files_changed=files_changed,
                commits_pulled=commits_pulled,
                before_commit=before_commit,
                after_commit=after_commit,
            )

        except subprocess.CalledProcessError as e:
            # Handle git pull failures
            error_code, recovery_suggestions = self._analyze_git_error(e)

            raise GitSyncError(
                f"Git pull failed: {e.stderr or e.stdout}",
                error_code,
                recovery_suggestions=recovery_suggestions,
                git_output=e.stderr or e.stdout,
            )
        finally:
            repo_lock.release()

    def validate_repository_state(self) -> RepositoryValidationResult:
        """
        Validate repository state before pull operation.

        Returns:
            RepositoryValidationResult with validation details
        """
        validation_errors = []

        try:
            # Check if repository is valid
            if not is_git_repository(self.repository_path):
                validation_errors.append("Not a valid git repository")
                return RepositoryValidationResult(
                    is_valid=False, can_pull=False, validation_errors=validation_errors
                )

            # Get current branch and commit
            branch_name = get_current_branch(self.repository_path)
            commit_hash = get_current_commit(self.repository_path)

            # Check for uncommitted changes
            status_result = run_git_command(
                ["git", "status", "--porcelain"], cwd=self.repository_path
            )
            has_uncommitted_changes = bool(status_result.stdout.strip())

            # Check if HEAD is detached
            try:
                run_git_command(
                    ["git", "symbolic-ref", "HEAD"], cwd=self.repository_path
                )
                is_detached_head = False
            except subprocess.CalledProcessError:
                is_detached_head = True
                validation_errors.append("Repository is in detached HEAD state")

            # Check if behind remote (if remote exists)
            is_behind_remote = False
            try:
                # Check if remote tracking branch exists
                run_git_command(
                    [
                        "git",
                        "rev-parse",
                        "--abbrev-ref",
                        "--symbolic-full-name",
                        "@{u}",
                    ],
                    cwd=self.repository_path,
                )

                # Fetch to get latest remote state
                run_git_command(["git", "fetch"], cwd=self.repository_path)

                # Check if behind remote
                behind_result = run_git_command(
                    ["git", "rev-list", "--count", "HEAD..@{u}"],
                    cwd=self.repository_path,
                )
                is_behind_remote = int(behind_result.stdout.strip()) > 0

            except subprocess.CalledProcessError:
                # No remote tracking branch
                pass

            # Determine if can pull
            can_pull = not validation_errors and not (
                has_uncommitted_changes and is_behind_remote
            )

            if has_uncommitted_changes and is_behind_remote:
                validation_errors.append(
                    "Cannot pull with uncommitted changes when behind remote"
                )

            return RepositoryValidationResult(
                is_valid=len(validation_errors) == 0,
                can_pull=can_pull,
                has_uncommitted_changes=has_uncommitted_changes,
                is_detached_head=is_detached_head,
                is_behind_remote=is_behind_remote,
                validation_errors=validation_errors,
                branch_name=branch_name,
                commit_hash=commit_hash,
            )

        except Exception as e:
            logger.error(
                f"Repository validation failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            validation_errors.append(f"Validation error: {str(e)}")
            return RepositoryValidationResult(
                is_valid=False, can_pull=False, validation_errors=validation_errors
            )

    def create_backup(self) -> BackupResult:
        """
        Create backup of current repository state.

        Returns:
            BackupResult with backup details
        """
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"backup_{timestamp}"
            backup_path.mkdir(parents=True, exist_ok=True)

            # Backup working directory (excluding .git)
            files_backed_up = 0
            total_size = 0

            for item in self.repository_path.iterdir():
                if item.name == ".git":
                    continue

                dest = backup_path / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                    files_backed_up += 1
                    total_size += item.stat().st_size
                elif item.is_dir():
                    shutil.copytree(item, dest, ignore=shutil.ignore_patterns(".git"))
                    for root, dirs, files in os.walk(dest):
                        files_backed_up += len(files)
                        for file in files:
                            total_size += Path(root, file).stat().st_size

            # Create backup metadata
            metadata = {
                "timestamp": timestamp,
                "repository_path": str(self.repository_path),
                "branch": get_current_branch(self.repository_path),
                "commit": get_current_commit(self.repository_path),
                "files_count": files_backed_up,
                "size_bytes": total_size,
            }

            with open(backup_path / "backup_metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            logger.info(
                f"Backup created: {backup_path} ({files_backed_up} files)",
                extra={"correlation_id": get_correlation_id()},
            )

            return BackupResult(
                success=True,
                backup_path=str(backup_path),
                backup_size_mb=total_size / (1024 * 1024),
                files_backed_up=files_backed_up,
            )

        except Exception as e:
            logger.error(
                f"Backup creation failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return BackupResult(
                success=False,
                error_message=str(e),
            )

    def configure_ssh_auth(self, ssh_key_path: str, passphrase: Optional[str] = None):
        """Configure SSH authentication for git operations."""
        self.auth_config["ssh"] = {
            "key_path": ssh_key_path,
            "passphrase": passphrase,
        }
        logger.info(
            f"SSH authentication configured with key: {ssh_key_path}",
            extra={"correlation_id": get_correlation_id()},
        )

    def configure_https_auth(self, token: str):
        """Configure HTTPS token authentication for git operations."""
        self.auth_config["https"] = {
            "token": token,
        }
        logger.info(
            "HTTPS token authentication configured",
            extra={"correlation_id": get_correlation_id()},
        )

    def _execute_git_pull(self, merge_strategy: str) -> str:
        """Execute git pull with specified merge strategy."""
        # Build git pull command based on strategy
        if merge_strategy == "fast-forward":
            cmd = ["git", "pull", "--ff-only"]
        elif merge_strategy == "merge":
            cmd = ["git", "pull", "--no-ff"]
        elif merge_strategy == "rebase":
            cmd = ["git", "pull", "--rebase"]
        else:
            raise GitSyncError(
                f"Unsupported merge strategy: {merge_strategy}",
                "INVALID_MERGE_STRATEGY",
                recovery_suggestions=[
                    "Use 'fast-forward', 'merge', or 'rebase'",
                ],
            )

        # Set up authentication environment if configured
        env = os.environ.copy()

        # SSH authentication
        if self.auth_config["ssh"].get("key_path"):
            env["GIT_SSH_COMMAND"] = f'ssh -i {self.auth_config["ssh"]["key_path"]}'
            if self.auth_config["ssh"].get("passphrase"):
                # Note: In production, use a proper SSH agent or credential manager
                logger.warning(
                    "SSH passphrase support requires proper credential management",
                    extra={"correlation_id": get_correlation_id()},
                )

        # HTTPS authentication
        if self.auth_config["https"].get("token"):
            # Note: In production, use proper credential manager
            logger.info(
                "HTTPS authentication configured (credential manager integration needed)",
                extra={"correlation_id": get_correlation_id()},
            )

        # Execute git command
        try:
            result = run_git_command(cmd, cwd=self.repository_path, env=env)
            logger.info(
                f"Git pull completed successfully: {result.stdout[:200]}...",
                extra={"correlation_id": get_correlation_id()},
            )
            return str(result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Git pull failed: {e}", extra={"correlation_id": get_correlation_id()}
            )
            raise

    def _analyze_git_error(
        self, error: subprocess.CalledProcessError
    ) -> tuple[str, List[str]]:
        """Analyze git error and provide recovery suggestions."""
        error_output = (error.stderr or error.stdout or "").lower()

        if "merge conflict" in error_output:
            return "MERGE_CONFLICT", [
                "Resolve merge conflicts manually",
                "Use git status to see conflicted files",
                "Use git mergetool for conflict resolution",
                "After resolving, commit with git commit",
            ]
        elif "authentication" in error_output or "permission denied" in error_output:
            return "AUTH_FAILED", [
                "Check SSH key configuration",
                "Verify repository access permissions",
                "Update authentication credentials",
            ]
        elif "network" in error_output or "could not resolve host" in error_output:
            return "NETWORK_ERROR", [
                "Check internet connection",
                "Verify repository URL is correct",
                "Try again after network issues are resolved",
            ]
        elif "not a git repository" in error_output:
            return "INVALID_REPOSITORY", [
                "Ensure you're in a git repository",
                "Run 'git init' if this should be a git repository",
            ]
        else:
            return "UNKNOWN_ERROR", [
                "Check git output for specific error details",
                "Verify repository state with 'git status'",
                "Consult git documentation for error resolution",
            ]

    def _get_changed_files(self, before_commit: str, after_commit: str) -> List[str]:
        """Get list of files changed between commits."""
        if before_commit == after_commit:
            return []

        try:
            result = run_git_command(
                ["git", "diff", "--name-only", before_commit, after_commit],
                cwd=self.repository_path,
            )
            return [line.strip() for line in result.stdout.split("\n") if line.strip()]
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Could not get changed files: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return []

    def _count_commits_pulled(self, before_commit: str, after_commit: str) -> int:
        """Count commits pulled between before and after states."""
        if before_commit == after_commit:
            return 0

        try:
            result = run_git_command(
                ["git", "rev-list", "--count", f"{before_commit}..{after_commit}"],
                cwd=self.repository_path,
            )
            return int(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Could not count commits: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return 0

    def _trigger_cidx_index(self) -> bool:
        """
        Trigger internal CIDX indexing using SmartIndexer.
        No external subprocess calls - we're already inside the CIDX application.

        Returns:
            True if indexing triggered successfully, False otherwise
        """
        try:
            from ...services.smart_indexer import SmartIndexer
            from ...services.embedding_factory import EmbeddingProviderFactory
            from ...storage.filesystem_vector_store import FilesystemVectorStore
            from ...config import ConfigManager
            from pathlib import Path

            logger.info(
                f"Starting internal CIDX indexing for {self.repository_path}",
                extra={"correlation_id": get_correlation_id()},
            )

            # Get configuration for this repository
            config_manager = ConfigManager.create_with_backtrack(self.repository_path)
            config = config_manager.load()

            # Initialize required services (similar to CLI approach)
            embedding_provider = EmbeddingProviderFactory.create(config)
            # Initialize vector store (Story #505 - FilesystemVectorStore)
            index_dir = Path(config.codebase_dir) / ".code-indexer" / "index"
            vector_store_client = FilesystemVectorStore(
                base_path=index_dir, project_root=Path(config.codebase_dir)
            )

            # Health checks
            if not embedding_provider.health_check():
                logger.error(
                    "Embedding provider health check failed",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

            if not vector_store_client.health_check():
                logger.error(
                    "Vector store client health check failed",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

            # Create SmartIndexer
            metadata_path = (
                Path(config.codebase_dir) / ".code-indexer" / "metadata.json"
            )
            smart_indexer = SmartIndexer(
                config=config,
                embedding_provider=embedding_provider,
                vector_store_client=vector_store_client,
                metadata_path=metadata_path,
            )

            # Execute incremental smart indexing
            stats = smart_indexer.smart_index(
                force_full=False,  # Incremental indexing after git changes
                reconcile_with_database=False,
                batch_size=50,
                progress_callback=None,  # No progress callback for simple git sync
                safety_buffer_seconds=60,
                vector_thread_count=config.voyage_ai.parallel_requests,
                detect_deletions=False,
            )

            # Check if indexing was successful
            if stats and not getattr(stats, "cancelled", False):
                logger.info(
                    f"Internal CIDX indexing completed successfully: {stats.files_processed} files, {stats.chunks_created} chunks",
                    extra={"correlation_id": get_correlation_id()},
                )
                return True
            else:
                logger.warning(
                    "Internal CIDX indexing was cancelled or failed",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

        except Exception as e:
            logger.error(
                f"Internal CIDX indexing failed: {e}",
                exc_info=True,
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def restore_from_backup(self, backup_path: str) -> bool:
        """
        Restore repository from backup.

        Args:
            backup_path: Path to backup directory

        Returns:
            True if restore successful, False otherwise
        """
        try:
            backup_dir = Path(backup_path)
            if not backup_dir.exists():
                logger.error(
                    f"Backup path does not exist: {backup_path}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

            # Load backup metadata
            metadata_file = backup_dir / "backup_metadata.json"
            if metadata_file.exists():
                with open(metadata_file) as f:
                    metadata = json.load(f)
                logger.info(
                    f"Restoring backup from {metadata['timestamp']}",
                    extra={"correlation_id": get_correlation_id()},
                )

            # Remove current working directory contents (except .git)
            for item in self.repository_path.iterdir():
                if item.name == ".git":
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

            # Restore from backup
            for item in backup_dir.iterdir():
                if item.name == "backup_metadata.json":
                    continue

                dest = self.repository_path / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                elif item.is_dir():
                    shutil.copytree(item, dest)

            logger.info(
                f"Repository restored from backup: {backup_path}",
                extra={"correlation_id": get_correlation_id()},
            )
            return True

        except Exception as e:
            logger.error(
                f"Backup restoration failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False
