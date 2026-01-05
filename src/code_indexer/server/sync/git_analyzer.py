"""
Git Change Analyzer for CIDX Server - Story 8 Implementation.

Analyzes git repository changes to provide detailed change statistics
for intelligent re-indexing decisions.
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import List, Set, Dict, Tuple, Any

from code_indexer.server.middleware.correlation import get_correlation_id
from .reindexing_models import ChangeSet
from ...utils.git_runner import run_git_command, is_git_repository


# Configure logging
logger = logging.getLogger(__name__)


class GitChangeAnalyzer:
    """
    Analyzes git repository changes for re-indexing decisions.

    Provides comprehensive analysis of:
    - File change statistics (added, modified, deleted)
    - Structural changes (directory moves, package restructuring)
    - Configuration file modifications
    - Repository evolution patterns
    """

    def __init__(self, repository_path: Path):
        """
        Initialize GitChangeAnalyzer.

        Args:
            repository_path: Path to the git repository

        Raises:
            ValueError: If path is not a valid git repository
        """
        self.repository_path = Path(repository_path).resolve()

        if not is_git_repository(self.repository_path):
            raise ValueError(f"Path is not a git repository: {self.repository_path}")

        logger.info(
            f"GitChangeAnalyzer initialized for repository: {self.repository_path}"
        , extra={"correlation_id": get_correlation_id()})

    def analyze_recent_changes(self, commits_back: int = 1) -> ChangeSet:
        """
        Analyze changes in recent commits.

        Args:
            commits_back: Number of commits to analyze (default: 1 for most recent)

        Returns:
            ChangeSet with comprehensive change analysis

        Raises:
            RuntimeError: If git commands fail
        """
        try:
            logger.debug(f"Analyzing changes for last {commits_back} commits", extra={"correlation_id": get_correlation_id()})

            # Get commit range for analysis
            if commits_back == 1:
                commit_range = "HEAD~1..HEAD"
            else:
                commit_range = f"HEAD~{commits_back}..HEAD"

            return self._analyze_commit_range(commit_range)

        except subprocess.CalledProcessError as e:
            logger.error(
                f"Git command failed during change analysis: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            raise RuntimeError(f"Failed to analyze git changes: {e}")

    def analyze_changes_since(self, commits_back: int) -> ChangeSet:
        """
        Analyze cumulative changes since N commits ago.

        Args:
            commits_back: Number of commits back to start analysis from

        Returns:
            ChangeSet with cumulative change analysis
        """
        try:
            commit_range = f"HEAD~{commits_back}..HEAD"
            return self._analyze_commit_range(commit_range)

        except subprocess.CalledProcessError as e:
            logger.error(
                f"Git command failed during historical analysis: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            raise RuntimeError(f"Failed to analyze historical changes: {e}")

    def analyze_changes_between_commits(
        self, from_commit: str, to_commit: str = "HEAD"
    ) -> ChangeSet:
        """
        Analyze changes between specific commits.

        Args:
            from_commit: Starting commit hash or reference
            to_commit: Ending commit hash or reference (default: HEAD)

        Returns:
            ChangeSet with change analysis between commits
        """
        try:
            commit_range = f"{from_commit}..{to_commit}"
            return self._analyze_commit_range(commit_range)

        except subprocess.CalledProcessError as e:
            logger.error(
                f"Git command failed during commit range analysis: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            raise RuntimeError(f"Failed to analyze changes between commits: {e}")

    def _analyze_commit_range(self, commit_range: str) -> ChangeSet:
        """
        Analyze changes in a specific commit range.

        Args:
            commit_range: Git commit range specification (e.g., "HEAD~1..HEAD")

        Returns:
            ChangeSet with detailed analysis
        """
        logger.debug(f"Analyzing commit range: {commit_range}", extra={"correlation_id": get_correlation_id()})

        # Get file change statistics
        files_changed, files_added, files_deleted = self._get_file_changes(commit_range)

        # Get total repository file count
        total_files = self._count_total_files()

        # Analyze structural changes
        directories_added, directories_removed = self._analyze_directory_changes(
            files_added, files_deleted
        )

        file_moves = self._analyze_file_moves(commit_range)

        # Create change set
        change_set = ChangeSet(
            files_changed=files_changed,
            files_added=files_added,
            files_deleted=files_deleted,
            total_files=total_files,
            directories_added=directories_added,
            directories_removed=directories_removed,
            file_moves=file_moves,
        )

        # Analyze change types
        self._detect_config_changes(change_set)
        self._detect_structural_changes(change_set)
        self._detect_schema_changes(change_set)

        logger.info(
            f"Change analysis complete: {change_set.change_count} changes "
            f"({change_set.percentage_changed:.1%} of {total_files} files)"
        , extra={"correlation_id": get_correlation_id()})

        return change_set

    def _get_file_changes(
        self, commit_range: str
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Get file change lists from git diff.

        Args:
            commit_range: Git commit range specification

        Returns:
            Tuple of (changed_files, added_files, deleted_files)
        """
        try:
            # Use git diff with name-status to get change types
            result = run_git_command(
                ["git", "diff", "--name-status", commit_range], cwd=self.repository_path
            )

            files_changed = []
            files_added = []
            files_deleted = []

            if result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue

                    parts = line.split("\t", 1)
                    if len(parts) != 2:
                        continue

                    status, file_path = parts
                    status = status.strip()
                    file_path = file_path.strip()

                    if status == "A":
                        files_added.append(file_path)
                    elif status == "D":
                        files_deleted.append(file_path)
                    elif status == "M":
                        files_changed.append(file_path)
                    elif status.startswith("R"):
                        # Rename - treat as add + delete
                        if "\t" in file_path:
                            old_path, new_path = file_path.split("\t", 1)
                            files_deleted.append(old_path)
                            files_added.append(new_path)
                    elif status.startswith("C"):
                        # Copy - treat as add
                        if "\t" in file_path:
                            _, new_path = file_path.split("\t", 1)
                            files_added.append(new_path)

            logger.debug(
                f"File changes: {len(files_changed)} modified, "
                f"{len(files_added)} added, {len(files_deleted)} deleted"
            , extra={"correlation_id": get_correlation_id()})

            return files_changed, files_added, files_deleted

        except subprocess.CalledProcessError as e:
            logger.error(
                f"Failed to get file changes: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return [], [], []

    def _count_total_files(self) -> int:
        """
        Count total files in the repository.

        Returns:
            Total number of tracked files
        """
        try:
            result = run_git_command(
                ["git", "ls-files", "--cached"], cwd=self.repository_path
            )

            if result.stdout.strip():
                return len(result.stdout.strip().split("\n"))
            else:
                return 0

        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Failed to count total files: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return 1000  # Default estimate to avoid division by zero

    def _analyze_directory_changes(
        self, files_added: List[str], files_deleted: List[str]
    ) -> Tuple[Set[str], Set[str]]:
        """
        Analyze directory-level changes.

        Args:
            files_added: List of added files
            files_deleted: List of deleted files

        Returns:
            Tuple of (directories_added, directories_removed)
        """
        # Get directories from added files
        directories_added = set()
        for file_path in files_added:
            parent_dir = str(Path(file_path).parent)
            if parent_dir != ".":
                directories_added.add(parent_dir)

        # Get directories that might be removed (all files deleted from them)
        directories_removed = set()
        deleted_dirs = set()
        for file_path in files_deleted:
            parent_dir = str(Path(file_path).parent)
            if parent_dir != ".":
                deleted_dirs.add(parent_dir)

        # Check if entire directories were removed
        for dir_path in deleted_dirs:
            try:
                result = run_git_command(
                    ["git", "ls-files", "--", dir_path], cwd=self.repository_path
                )
                # If no files remain in directory, it was removed
                if not result.stdout.strip():
                    directories_removed.add(dir_path)
            except subprocess.CalledProcessError:
                pass

        logger.debug(
            f"Directory changes: {len(directories_added)} added, "
            f"{len(directories_removed)} removed"
        , extra={"correlation_id": get_correlation_id()})

        return directories_added, directories_removed

    def _analyze_file_moves(self, commit_range: str) -> List[Tuple[str, str]]:
        """
        Analyze file moves/renames.

        Args:
            commit_range: Git commit range specification

        Returns:
            List of (old_path, new_path) tuples
        """
        try:
            # Use git diff with rename detection
            result = run_git_command(
                ["git", "diff", "--name-status", "-M", commit_range],
                cwd=self.repository_path,
            )

            file_moves = []

            if result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue

                    parts = line.split("\t")
                    if len(parts) >= 2 and parts[0].startswith("R"):
                        if len(parts) == 3:
                            # R<similarity>    old_path    new_path
                            old_path, new_path = parts[1], parts[2]
                            file_moves.append((old_path, new_path))

            logger.debug(f"File moves detected: {len(file_moves)}", extra={"correlation_id": get_correlation_id()})
            return file_moves

        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Failed to analyze file moves: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return []

    def _detect_config_changes(self, change_set: ChangeSet) -> None:
        """
        Detect configuration file changes.

        Args:
            change_set: ChangeSet to update with config change detection
        """
        config_patterns = {
            ".cidx-config",
            ".gitignore",
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "Dockerfile",
            "docker-compose.yml",
            "package.json",
            "tsconfig.json",
            "Makefile",
            "CMakeLists.txt",
        }

        config_extensions = {".cfg", ".ini", ".conf", ".config", ".yml", ".yaml"}

        all_changed_files = (
            change_set.files_changed + change_set.files_added + change_set.files_deleted
        )

        for file_path in all_changed_files:
            file_name = Path(file_path).name
            file_suffix = Path(file_path).suffix.lower()

            if file_name in config_patterns or file_suffix in config_extensions:
                change_set.has_config_changes = True
                logger.debug(f"Configuration change detected: {file_path}", extra={"correlation_id": get_correlation_id()})
                break

    def _detect_structural_changes(self, change_set: ChangeSet) -> None:
        """
        Detect structural repository changes.

        Args:
            change_set: ChangeSet to update with structural change detection
        """
        structural_indicators = {
            "__init__.py",
            "index.js",
            "main.py",
            "app.py",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "pom.xml",
        }

        # Check for structural indicator files
        all_changed_files = (
            change_set.files_changed + change_set.files_added + change_set.files_deleted
        )

        for file_path in all_changed_files:
            file_name = Path(file_path).name
            if file_name in structural_indicators:
                change_set.has_structural_changes = True
                logger.debug(f"Structural indicator changed: {file_path}", extra={"correlation_id": get_correlation_id()})
                break

        # Check for significant directory changes
        dir_changes = len(change_set.directories_added) + len(
            change_set.directories_removed
        )
        if dir_changes >= 3:  # Threshold for significant structural change
            change_set.has_structural_changes = True
            logger.debug(f"Significant directory changes: {dir_changes}", extra={"correlation_id": get_correlation_id()})

        # Check for many file moves (suggests restructuring)
        if len(change_set.file_moves) >= 5:
            change_set.has_structural_changes = True
            logger.debug(f"Many file moves detected: {len(change_set.file_moves)}", extra={"correlation_id": get_correlation_id()})

    def _detect_schema_changes(self, change_set: ChangeSet) -> None:
        """
        Detect schema or data structure changes.

        Args:
            change_set: ChangeSet to update with schema change detection
        """
        schema_patterns = {
            "schema.sql",
            "migrations",
            "alembic",
            "schema.json",
            "schema.yaml",
            "models.py",
            "entities.py",
        }

        schema_extensions = {".sql", ".migration", ".schema"}

        all_changed_files = (
            change_set.files_changed + change_set.files_added + change_set.files_deleted
        )

        for file_path in all_changed_files:
            file_name = Path(file_path).name
            file_suffix = Path(file_path).suffix.lower()
            file_path_lower = file_path.lower()

            # Check filename patterns
            if any(pattern in file_name.lower() for pattern in schema_patterns):
                change_set.has_schema_changes = True
                logger.debug(f"Schema change detected: {file_path}", extra={"correlation_id": get_correlation_id()})
                break

            # Check file extensions
            if file_suffix in schema_extensions:
                change_set.has_schema_changes = True
                logger.debug(f"Schema file changed: {file_path}", extra={"correlation_id": get_correlation_id()})
                break

            # Check path patterns
            if any(
                pattern in file_path_lower
                for pattern in ["migration", "schema", "model"]
            ):
                change_set.has_schema_changes = True
                logger.debug(f"Schema-related path changed: {file_path}", extra={"correlation_id": get_correlation_id()})
                break

    def get_commit_details(self, commit_range: str) -> Dict[str, Any]:
        """
        Get detailed commit information for analysis context.

        Args:
            commit_range: Git commit range specification

        Returns:
            Dictionary with commit details
        """
        try:
            # Get commit log with details
            result = run_git_command(
                ["git", "log", "--oneline", "--stat", commit_range],
                cwd=self.repository_path,
            )

            commit_info = {
                "commit_range": commit_range,
                "log_output": result.stdout,
                "commit_count": len(
                    [
                        line
                        for line in result.stdout.split("\n")
                        if re.match(r"^[a-f0-9]+\s", line)
                    ]
                ),
            }

            return commit_info

        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Failed to get commit details: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return {"commit_range": commit_range, "error": str(e)}

    def analyze_repository_health(self) -> Dict[str, Any]:
        """
        Analyze overall repository health for context.

        Returns:
            Dictionary with repository health metrics
        """
        try:
            health = {
                "total_commits": 0,
                "recent_activity": False,
                "branch_count": 0,
                "repository_size": 0,
            }

            # Count total commits
            try:
                result = run_git_command(
                    ["git", "rev-list", "--count", "HEAD"], cwd=self.repository_path
                )
                health["total_commits"] = int(result.stdout.strip())
            except (subprocess.CalledProcessError, ValueError):
                pass

            # Check recent activity (commits in last 30 days)
            try:
                result = run_git_command(
                    ["git", "log", "--since=30.days.ago", "--oneline"],
                    cwd=self.repository_path,
                )
                health["recent_activity"] = bool(result.stdout.strip())
            except subprocess.CalledProcessError:
                pass

            # Count branches
            try:
                result = run_git_command(
                    ["git", "branch", "-a"], cwd=self.repository_path
                )
                health["branch_count"] = len(
                    [
                        line
                        for line in result.stdout.split("\n")
                        if line.strip() and not line.strip().startswith("*")
                    ]
                )
            except subprocess.CalledProcessError:
                pass

            return health

        except Exception as e:
            logger.warning(
                f"Failed to analyze repository health: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return {"error": str(e)}
