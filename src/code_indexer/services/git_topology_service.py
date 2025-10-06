"""
Git Topology Service for branch-aware smart incremental indexing.

Provides advanced git topology analysis to enable efficient incremental indexing
that understands branch relationships, file changes, and working directory state.
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class BranchChangeAnalysis:
    """Analysis of changes between branches for smart incremental indexing."""

    old_branch: str
    new_branch: str
    merge_base: Optional[str]
    files_to_reindex: List[str]  # Files that changed between branches
    files_to_update_metadata: List[str]  # Files that need branch metadata updates only
    staged_files: List[str]  # Staged working directory files
    unstaged_files: List[str]  # Unstaged working directory files
    branch_ancestry: List[str]  # Parent commits for topology filtering
    performance_stats: Dict[str, Any]  # Performance metrics


@dataclass
class FileAnalysis:
    """Analysis result for individual file."""

    content_hash: Optional[str]
    last_modified: Optional[str]
    git_status: Optional[str]
    working_directory_status: Optional[str]  # staged, unstaged, committed


class GitTopologyService:
    """Advanced git topology analysis for smart incremental indexing."""

    def __init__(self, codebase_dir: Path):
        """Initialize the git topology service.

        Args:
            codebase_dir: Root directory of the git repository
        """
        self.codebase_dir = Path(codebase_dir)
        self._git_available: Optional[bool] = None
        self._current_branch_cache: Optional[str] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: int = 5  # Cache for 5 seconds to avoid redundant git calls

    def is_git_available(self) -> bool:
        """Check if git is available and this is a git repository."""
        if self._git_available is not None:
            return self._git_available

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._git_available = result.returncode == 0
            return self._git_available
        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            subprocess.SubprocessError,
        ):
            self._git_available = False
            return self._git_available

    def get_current_branch(self) -> Optional[str]:
        """Get current git branch with caching."""
        current_time = time.time()
        if (
            self._current_branch_cache is not None
            and current_time - self._cache_timestamp < self._cache_ttl
        ):
            return self._current_branch_cache

        if not self.is_git_available():
            return None

        try:
            # Try to get current branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                branch: Optional[str] = result.stdout.strip()
            else:
                # Handle detached HEAD
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=self.codebase_dir,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                branch = (
                    f"detached-{result.stdout.strip()}"
                    if result.returncode == 0
                    else None
                )

            self._current_branch_cache = branch
            self._cache_timestamp = current_time
            return branch

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to get current branch: {e}")
            return None

    def get_current_state(self) -> Dict[str, Any]:
        """Get current git state for metadata."""
        if not self.is_git_available():
            return {
                "git_available": False,
                "current_branch": None,
                "current_commit": None,
            }

        current_branch = self.get_current_branch()
        current_commit = self._get_current_commit()

        return {
            "git_available": True,
            "current_branch": current_branch,
            "current_commit": current_commit,
        }

    def _get_current_commit(self) -> Optional[str]:
        """Get current commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def analyze_branch_change(
        self, old_branch: str, new_branch: str
    ) -> BranchChangeAnalysis:
        """Analyze what needs indexing when switching branches."""
        start_time = time.time()

        if not self.is_git_available():
            # Non-git repository - return empty analysis
            return BranchChangeAnalysis(
                old_branch=old_branch,
                new_branch=new_branch,
                merge_base=None,
                files_to_reindex=[],
                files_to_update_metadata=[],
                staged_files=[],
                unstaged_files=[],
                branch_ancestry=[],
                performance_stats={"analysis_time": time.time() - start_time},
            )

        logger.info(f"Analyzing branch change: {old_branch} -> {new_branch}")

        # Find merge base between branches
        merge_base = self._get_merge_base(old_branch, new_branch)

        # Get files that changed between branches
        raw_changed_files = self._get_changed_files(old_branch, new_branch)

        # Get all files in target branch for metadata updates
        all_files = self._get_all_tracked_files(new_branch)

        # Filter changed files to only include files that exist in the target branch
        # Files that don't exist in target branch should be hidden, not processed as "changed"
        changed_files = [f for f in raw_changed_files if f in all_files]
        unchanged_files = [f for f in all_files if f not in changed_files]

        # Get working directory changes
        staged_files = self._get_staged_files()
        unstaged_files = self._get_unstaged_files()

        # Get branch ancestry for topology filtering
        branch_ancestry = self._get_branch_ancestry(new_branch)

        analysis_time = time.time() - start_time
        logger.info(
            f"Branch analysis completed in {analysis_time:.3f}s: "
            f"{len(changed_files)} changed files, {len(unchanged_files)} metadata updates"
        )

        return BranchChangeAnalysis(
            old_branch=old_branch,
            new_branch=new_branch,
            merge_base=merge_base,
            files_to_reindex=changed_files,
            files_to_update_metadata=unchanged_files,
            staged_files=staged_files,
            unstaged_files=unstaged_files,
            branch_ancestry=branch_ancestry,
            performance_stats={
                "analysis_time": analysis_time,
                "changed_files_count": len(changed_files),
                "metadata_update_files_count": len(unchanged_files),
                "staged_files_count": len(staged_files),
                "unstaged_files_count": len(unstaged_files),
            },
        )

    def _get_merge_base(self, branch1: str, branch2: str) -> Optional[str]:
        """Find common ancestor between branches."""
        try:
            result = subprocess.run(
                ["git", "merge-base", branch1, branch2],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to get merge base for {branch1}..{branch2}: {e}")
            return None

    def _get_changed_files(self, old_branch: str, new_branch: str) -> List[str]:
        """Get files that changed between branches using efficient git diff.

        CRITICAL: Handles synthetic branch names like "detached-6a649690" by using HEAD.
        These synthetic names are not valid git references and would cause git diff to fail.
        """
        try:
            # If old_branch is not a valid git reference (e.g., "unknown"),
            # treat this as a new branch scenario and return all tracked files
            if old_branch == "unknown" or not self._is_valid_git_ref(old_branch):
                logger.info(
                    f"Old_branch '{old_branch}' is not a valid git reference, treating as new branch scenario"
                )
                return self._get_all_tracked_files()

            # Handle synthetic branch names (detached-*) by using HEAD
            # These are created by get_current_branch() for detached HEAD states
            old_git_ref = "HEAD" if old_branch.startswith("detached-") else old_branch
            new_git_ref = "HEAD" if new_branch.startswith("detached-") else new_branch

            # Use git diff with name-only to get just the file names
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{old_git_ref}..{new_git_ref}"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                files = [
                    f.strip() for f in result.stdout.strip().split("\n") if f.strip()
                ]
                logger.debug(
                    f"Found {len(files)} changed files between {old_branch}..{new_branch}"
                )
                return files
            else:
                logger.warning(f"Git diff failed: {result.stderr}")
                # If git diff fails, fall back to returning all tracked files
                return self._get_all_tracked_files()

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to get changed files: {e}")
            return []

    def _is_valid_git_ref(self, ref: str) -> bool:
        """Check if a string is a valid git reference."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", ref],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False

    def _get_all_tracked_files(self, branch: str = "HEAD") -> List[str]:
        """Get all files tracked by git in specified branch.

        CRITICAL: Handles synthetic branch names like "detached-6a649690" by using HEAD.
        These synthetic names are not valid git references and would cause git ls-tree to fail.
        """
        try:
            # Handle synthetic branch names (detached-*) by using HEAD
            # These are created by get_current_branch() for detached HEAD states
            # and are not valid git references
            git_ref = "HEAD" if branch.startswith("detached-") else branch

            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", "--full-tree", git_ref],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                files = [
                    f.strip() for f in result.stdout.strip().split("\n") if f.strip()
                ]
                logger.debug(
                    f"Found {len(files)} tracked files in {branch} (git ref: {git_ref})"
                )
                return files
            else:
                logger.warning(
                    f"git ls-tree failed for branch '{branch}' (git ref: {git_ref}): {result.stderr}"
                )
                return []

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to get tracked files: {e}")
            return []

    def _get_staged_files(self) -> List[str]:
        """Get files that are staged in the working directory."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                files = [
                    f.strip() for f in result.stdout.strip().split("\n") if f.strip()
                ]
                return files
            else:
                return []

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to get staged files: {e}")
            return []

    def _get_unstaged_files(self) -> List[str]:
        """Get files that have unstaged changes in the working directory."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                files = [
                    f.strip() for f in result.stdout.strip().split("\n") if f.strip()
                ]
                return files
            else:
                return []

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to get unstaged files: {e}")
            return []

    def _get_branch_ancestry(self, branch: str) -> List[str]:
        """Get all parent commits for branch topology filtering."""
        try:
            # Use git log --first-parent to get linear ancestry
            # Limit to reasonable number of commits for performance
            result = subprocess.run(
                ["git", "log", "--first-parent", "--format=%H", branch, "-n", "100"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 0:
                commits = [
                    c.strip() for c in result.stdout.strip().split("\n") if c.strip()
                ]
                return commits
            else:
                return []

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to get branch ancestry for {branch}: {e}")
            return []

    def batch_file_analysis(self, files: List[str]) -> Dict[str, FileAnalysis]:
        """Analyze multiple files in batched git operations for performance."""
        if not self.is_git_available() or not files:
            return {}

        start_time = time.time()
        analysis = {}

        # Batch git hash-object for all files
        hashes = self._batch_git_hash_object(files)

        # Batch git log for last modified info
        modifications = self._batch_git_log_analysis(files)

        # Batch file status checks
        statuses = self._batch_git_status_analysis(files)

        # Combine results
        for file_path in files:
            analysis[file_path] = FileAnalysis(
                content_hash=hashes.get(file_path),
                last_modified=modifications.get(file_path),
                git_status=statuses.get(file_path),
                working_directory_status=self._determine_working_dir_status(file_path),
            )

        analysis_time = time.time() - start_time
        logger.debug(
            f"Batch file analysis for {len(files)} files completed in {analysis_time:.3f}s"
        )

        return analysis

    def _batch_git_hash_object(self, files: List[str]) -> Dict[str, str]:
        """Batch git hash-object operation for performance."""
        if not files:
            return {}

        try:
            # Filter files that actually exist
            existing_files = []
            for file_path in files:
                full_path = self.codebase_dir / file_path
                if full_path.exists() and full_path.is_file():
                    existing_files.append(file_path)

            if not existing_files:
                return {}

            # Use --stdin-paths for batch processing
            process = subprocess.run(
                ["git", "hash-object", "--stdin-paths"],
                input="\n".join(existing_files),
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if process.returncode == 0:
                hashes = process.stdout.strip().split("\n")
                if len(hashes) == len(existing_files):
                    return dict(zip(existing_files, hashes))

            return {}

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Batch git hash-object failed: {e}")
            return {}

    def _batch_git_log_analysis(self, files: List[str]) -> Dict[str, str]:
        """Batch git log analysis for last modification times."""
        if not files:
            return {}

        try:
            # Get last commit for each file in batch
            result = subprocess.run(
                ["git", "log", "--format=%H %ct", "--name-only", "-n", "1", "--"]
                + files,
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            modifications = {}
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                current_commit_time = None

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Check if this is a commit line (hash + timestamp)
                    parts = line.split()
                    if len(parts) == 2 and all(
                        c in "0123456789abcdef" for c in parts[0]
                    ):
                        current_commit_time = parts[1]
                    elif current_commit_time and line in files:
                        modifications[line] = current_commit_time

            return modifications

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Batch git log analysis failed: {e}")
            return {}

    def _batch_git_status_analysis(self, files: List[str]) -> Dict[str, str]:
        """Batch git status analysis for file states."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"] + files,
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )

            statuses = {}
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line and len(line) > 3:
                        status_code = line[:2]
                        file_path = line[3:]
                        statuses[file_path] = status_code.strip()

            return statuses

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Batch git status analysis failed: {e}")
            return {}

    def _determine_working_dir_status(self, file_path: str) -> Optional[str]:
        """Determine working directory status for a file."""
        # This would be populated by the batch status analysis
        # For now, return basic detection
        staged_files = self._get_staged_files()
        unstaged_files = self._get_unstaged_files()

        if file_path in staged_files:
            return "staged"
        elif file_path in unstaged_files:
            return "unstaged"
        else:
            return "committed"

    def invalidate_cache(self):
        """Invalidate internal caches to force fresh git operations."""
        self._current_branch_cache = None
        self._cache_timestamp = 0
        self._git_available = None
