"""
Git operations service for history exploration.

Provides operations for browsing git commit history and retrieving
file contents at specific revisions without requiring temporal indexing.
Uses run_git_command() from git_runner for all git operations.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from code_indexer.utils.git_runner import run_git_command


logger = logging.getLogger(__name__)


@dataclass
class CommitInfo:
    """Information about a single commit."""

    hash: str
    short_hash: str
    author_name: str
    author_email: str
    author_date: str
    committer_name: str
    committer_email: str
    committer_date: str
    subject: str
    body: str


@dataclass
class GitLogResult:
    """Result of a git log query."""

    commits: List[CommitInfo]
    total_count: int
    truncated: bool


@dataclass
class FileChangeStats:
    """Statistics for a file change in a commit."""

    path: str
    insertions: int
    deletions: int
    status: str  # "added", "modified", "deleted", "renamed"


@dataclass
class CommitDetail:
    """Detailed information about a commit."""

    commit: CommitInfo
    stats: Optional[List[FileChangeStats]]
    diff: Optional[str]
    parents: List[str]


@dataclass
class FileRevisionResult:
    """Result of retrieving a file at a specific revision."""

    path: str
    revision: str
    resolved_revision: str
    content: str
    size_bytes: int


@dataclass
class DiffHunk:
    """A single hunk in a diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    content: str


@dataclass
class FileDiff:
    """Diff information for a single file."""

    path: str
    old_path: Optional[str]  # If renamed
    status: str  # "added", "modified", "deleted", "renamed"
    insertions: int
    deletions: int
    hunks: List[DiffHunk]


@dataclass
class GitDiffResult:
    """Result of a git diff operation."""

    from_revision: str
    to_revision: Optional[str]
    files: List[FileDiff]
    total_insertions: int
    total_deletions: int
    stat_summary: str


@dataclass
class BlameLine:
    """Blame information for a single line."""

    line_number: int
    commit_hash: str
    short_hash: str
    author_name: str
    author_email: str
    author_date: str
    original_line_number: int
    content: str


@dataclass
class BlameResult:
    """Result of a git blame operation."""

    path: str
    revision: str
    lines: List[BlameLine]
    unique_commits: int


@dataclass
class FileHistoryCommit:
    """Commit information for file history."""

    hash: str
    short_hash: str
    author_name: str
    author_date: str
    subject: str
    insertions: int
    deletions: int
    old_path: Optional[str]  # Previous path if renamed


@dataclass
class FileHistoryResult:
    """Result of a file history query."""

    path: str
    commits: List[FileHistoryCommit]
    total_count: int
    truncated: bool
    renamed_from: Optional[str]


@dataclass
class CommitSearchMatch:
    """A single commit matching a search query."""

    hash: str
    short_hash: str
    author_name: str
    author_email: str
    author_date: str
    subject: str
    body: str
    match_highlights: List[str]  # Lines containing matches


@dataclass
class CommitSearchResult:
    """Result of a commit message search."""

    query: str
    is_regex: bool
    matches: List[CommitSearchMatch]
    total_matches: int
    truncated: bool
    search_time_ms: float


@dataclass
class DiffSearchMatch:
    """A commit that introduced or removed matching content."""

    hash: str
    short_hash: str
    author_name: str
    author_date: str
    subject: str
    files_changed: List[str]
    diff_snippet: Optional[str]  # Relevant portion of diff


@dataclass
class DiffSearchResult:
    """Result of a diff content search (pickaxe)."""

    search_term: str
    is_regex: bool
    matches: List[DiffSearchMatch]
    total_matches: int
    truncated: bool
    search_time_ms: float


class GitOperationsService:
    """Service for git history exploration operations."""

    # Format string for git log output parsing
    # Fields separated by NUL character (\x00) for reliable parsing
    LOG_FORMAT = "%H%x00%h%x00%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI%x00%s%x00%b%x00"

    def __init__(self, repo_path: Path):
        """Initialize GitOperationsService.

        Args:
            repo_path: Path to the git repository

        Raises:
            ValueError: If the path is not a git repository
        """
        self.repo_path = repo_path
        self._verify_git_repository()

    def _verify_git_repository(self) -> None:
        """Verify the path is a git repository.

        Raises:
            ValueError: If not a git repository
        """
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def get_log(
        self,
        limit: int = 50,
        path: Optional[str] = None,
        author: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> GitLogResult:
        """Get commit log with optional filters.

        Args:
            limit: Maximum number of commits to return (default 50)
            path: Filter commits to only those affecting this path
            author: Filter commits by author (name or email)
            since: Include only commits after this date (YYYY-MM-DD)
            until: Include only commits before this date (YYYY-MM-DD)
            branch: Branch to get log from (default: current HEAD)

        Returns:
            GitLogResult with commits and metadata
        """
        # Build git log command
        cmd = ["git", "log", f"--format={self.LOG_FORMAT}"]

        # Add limit (request one more to detect truncation)
        cmd.append(f"-{limit + 1}")

        # Add filters
        if author:
            cmd.append(f"--author={author}")
        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")
        if branch:
            cmd.append(branch)

        # Path must come last after --
        if path:
            cmd.extend(["--", path])

        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
            output = result.stdout
        except subprocess.CalledProcessError:
            # Empty repository or no matching commits
            return GitLogResult(commits=[], total_count=0, truncated=False)

        # Parse output
        commits = self._parse_log_output(output)

        # Check if truncated
        truncated = len(commits) > limit
        if truncated:
            commits = commits[:limit]

        return GitLogResult(
            commits=commits,
            total_count=len(commits),
            truncated=truncated,
        )

    def _parse_log_output(self, output: str) -> List[CommitInfo]:
        """Parse git log output into CommitInfo objects.

        Args:
            output: Raw output from git log command

        Returns:
            List of CommitInfo objects
        """
        commits = []

        # Split by double NUL (end of each record)
        # Each record ends with body\x00 (body followed by NUL)
        records = output.strip().split("\x00\n")

        for record in records:
            if not record.strip():
                continue

            # Split fields by NUL character
            fields = record.split("\x00")

            if len(fields) < 10:
                continue

            commits.append(
                CommitInfo(
                    hash=fields[0],
                    short_hash=fields[1],
                    author_name=fields[2],
                    author_email=fields[3],
                    author_date=fields[4],
                    committer_name=fields[5],
                    committer_email=fields[6],
                    committer_date=fields[7],
                    subject=fields[8],
                    body=fields[9].strip() if len(fields) > 9 else "",
                )
            )

        return commits

    def show_commit(
        self,
        commit_hash: str,
        include_diff: bool = False,
        include_stats: bool = True,
    ) -> CommitDetail:
        """Get detailed information about a specific commit.

        Args:
            commit_hash: The commit to show (full SHA, abbreviated, or ref)
            include_diff: Whether to include the full diff
            include_stats: Whether to include file change statistics

        Returns:
            CommitDetail with commit info, stats, and optionally diff

        Raises:
            ValueError: If commit is not found
        """
        # First, resolve the commit hash to full SHA
        try:
            resolve_result = run_git_command(
                ["git", "rev-parse", commit_hash],
                cwd=self.repo_path,
                check=True,
            )
            full_hash = resolve_result.stdout.strip()
        except subprocess.CalledProcessError:
            raise ValueError(f"Commit not found: {commit_hash}")

        # Get commit info using log format
        cmd = ["git", "log", "-1", f"--format={self.LOG_FORMAT}", full_hash]
        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
            commits = self._parse_log_output(result.stdout)
            if not commits:
                raise ValueError(f"Commit not found: {commit_hash}")
            commit_info = commits[0]
        except subprocess.CalledProcessError:
            raise ValueError(f"Commit not found: {commit_hash}")

        # Get parent commits
        parent_cmd = ["git", "rev-parse", f"{full_hash}^@"]
        try:
            parent_result = run_git_command(parent_cmd, cwd=self.repo_path, check=False)
            parents = [
                p.strip() for p in parent_result.stdout.strip().split("\n") if p.strip()
            ]
        except subprocess.CalledProcessError:
            parents = []

        # Get file stats if requested
        stats = None
        if include_stats:
            stats = self._get_commit_stats(full_hash)

        # Get diff if requested
        diff = None
        if include_diff:
            diff = self._get_commit_diff(full_hash)

        return CommitDetail(
            commit=commit_info,
            stats=stats,
            diff=diff,
            parents=parents,
        )

    def _get_commit_stats(self, commit_hash: str) -> List[FileChangeStats]:
        """Get file change statistics for a commit.

        Args:
            commit_hash: Full commit SHA

        Returns:
            List of FileChangeStats
        """
        # Use numstat and name-status together
        cmd = [
            "git",
            "show",
            commit_hash,
            "--numstat",
            "--name-status",
            "--format=",  # No commit info, just file stats
        ]

        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
        except subprocess.CalledProcessError:
            return []

        # Parse output - numstat gives insertions/deletions, name-status gives status
        stats_dict = {}
        lines = result.stdout.strip().split("\n")

        # First pass: numstat lines (insertions, deletions, path)
        for line in lines:
            if not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) == 3:
                insertions_str, deletions_str, path = parts
                # Binary files show - for insertions/deletions
                insertions = 0 if insertions_str == "-" else int(insertions_str)
                deletions = 0 if deletions_str == "-" else int(deletions_str)
                stats_dict[path] = FileChangeStats(
                    path=path,
                    insertions=insertions,
                    deletions=deletions,
                    status="modified",  # Default, will be updated
                )
            elif len(parts) == 2:
                # name-status line: status\tpath
                status_char, path = parts
                if path in stats_dict:
                    stats_dict[path].status = self._map_status_char(status_char)
                else:
                    stats_dict[path] = FileChangeStats(
                        path=path,
                        insertions=0,
                        deletions=0,
                        status=self._map_status_char(status_char),
                    )

        return list(stats_dict.values())

    def _map_status_char(self, status: str) -> str:
        """Map git status character to human-readable status.

        Args:
            status: Git status character (A, M, D, R, etc.)

        Returns:
            Human-readable status string
        """
        status_map = {
            "A": "added",
            "M": "modified",
            "D": "deleted",
            "R": "renamed",
            "C": "copied",
            "T": "type_changed",
            "U": "unmerged",
        }
        return status_map.get(status[0] if status else "M", "modified")

    def _get_commit_diff(self, commit_hash: str) -> str:
        """Get the full diff for a commit.

        Args:
            commit_hash: Full commit SHA

        Returns:
            Diff as string
        """
        cmd = ["git", "show", commit_hash, "--format=", "-p"]

        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
            return result.stdout
        except subprocess.CalledProcessError:
            return ""

    def get_file_at_revision(
        self,
        path: str,
        revision: str,
    ) -> FileRevisionResult:
        """Get file contents at a specific revision.

        Args:
            path: Path to the file (relative to repo root)
            revision: The revision to get the file from (commit SHA, branch, tag, etc.)

        Returns:
            FileRevisionResult with file content and metadata

        Raises:
            ValueError: If file or revision not found
        """
        # First resolve the revision to full SHA and verify it exists
        try:
            # Use rev-parse --verify to check the revision actually exists
            resolve_result = run_git_command(
                ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
                cwd=self.repo_path,
                check=True,
            )
            resolved_revision = resolve_result.stdout.strip()
        except subprocess.CalledProcessError:
            raise ValueError(f"Invalid revision: {revision}")

        # Get file content using git show
        cmd = ["git", "show", f"{resolved_revision}:{path}"]

        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
            content = result.stdout
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            # Check for invalid revision errors (bad object, not a commit object)
            if "bad revision" in stderr or "unknown revision" in stderr:
                raise ValueError(f"Invalid revision: {revision}")
            # All other errors are file not found
            raise ValueError(f"File not found: {path} at revision {revision}")

        return FileRevisionResult(
            path=path,
            revision=revision,
            resolved_revision=resolved_revision,
            content=content,
            size_bytes=len(content.encode("utf-8")),
        )

    def get_diff(
        self,
        from_revision: str,
        to_revision: Optional[str] = None,
        path: Optional[str] = None,
        context_lines: int = 3,
        stat_only: bool = False,
    ) -> GitDiffResult:
        """Get diff between revisions or working directory.

        Args:
            from_revision: Starting revision for the diff
            to_revision: Ending revision (None for working directory)
            path: Limit diff to specific file or directory
            context_lines: Number of context lines around changes
            stat_only: Only return statistics without hunks

        Returns:
            GitDiffResult with file diffs and statistics
        """
        # Build base args for git diff commands
        base_args = [from_revision]
        if to_revision:
            base_args.append(to_revision)
        path_args = ["--", path] if path else []

        # Run numstat separately (git ignores numstat when combined with name-status)
        numstat_cmd = ["git", "diff", "--numstat"] + base_args + path_args
        try:
            numstat_result = run_git_command(
                numstat_cmd, cwd=self.repo_path, check=True
            )
            numstat_output = numstat_result.stdout
        except subprocess.CalledProcessError as e:
            logger.debug(f"numstat command returned no output: {e}")
            numstat_output = ""

        # Run name-status separately
        status_cmd = ["git", "diff", "--name-status"] + base_args + path_args
        try:
            status_result = run_git_command(status_cmd, cwd=self.repo_path, check=True)
            status_output = status_result.stdout
        except subprocess.CalledProcessError as e:
            logger.debug(f"name-status command returned no output: {e}")
            status_output = ""

        if not numstat_output and not status_output:
            return GitDiffResult(
                from_revision=from_revision,
                to_revision=to_revision,
                files=[],
                total_insertions=0,
                total_deletions=0,
                stat_summary="",
            )

        # Parse statistics from separate outputs
        files_dict = self._parse_diff_stat_separate(numstat_output, status_output)

        # Get hunks if not stat_only
        if not stat_only:
            diff_cmd = ["git", "diff", f"-U{context_lines}", from_revision]
            if to_revision:
                diff_cmd.append(to_revision)
            if path:
                diff_cmd.extend(["--", path])

            try:
                diff_result = run_git_command(diff_cmd, cwd=self.repo_path, check=True)
                self._parse_diff_hunks(diff_result.stdout, files_dict)
            except subprocess.CalledProcessError:
                pass

        # Build file list
        files = list(files_dict.values())

        # Calculate totals
        total_insertions = sum(f.insertions for f in files)
        total_deletions = sum(f.deletions for f in files)

        # Build stat summary
        stat_summary = f"{len(files)} file(s) changed"
        if total_insertions:
            stat_summary += f", {total_insertions} insertion(s)"
        if total_deletions:
            stat_summary += f", {total_deletions} deletion(s)"

        return GitDiffResult(
            from_revision=from_revision,
            to_revision=to_revision,
            files=files,
            total_insertions=total_insertions,
            total_deletions=total_deletions,
            stat_summary=stat_summary,
        )

    def _parse_diff_stat(self, output: str) -> dict:
        """Parse git diff --numstat --name-status output.

        Args:
            output: Raw output from git diff

        Returns:
            Dictionary mapping path to FileDiff
        """
        files_dict = {}
        lines = output.strip().split("\n")

        for line in lines:
            if not line.strip():
                continue

            parts = line.split("\t")

            # numstat format: insertions\tdeletions\tpath
            if len(parts) == 3 and parts[0].replace("-", "").isdigit():
                insertions_str, deletions_str, file_path = parts
                insertions = 0 if insertions_str == "-" else int(insertions_str)
                deletions = 0 if deletions_str == "-" else int(deletions_str)

                files_dict[file_path] = FileDiff(
                    path=file_path,
                    old_path=None,
                    status="modified",
                    insertions=insertions,
                    deletions=deletions,
                    hunks=[],
                )

            # name-status format: status\tpath or status\told_path\tnew_path
            elif len(parts) >= 2:
                status_char = parts[0]
                if len(parts) == 3:  # Rename
                    old_path, new_path = parts[1], parts[2]
                    if new_path in files_dict:
                        files_dict[new_path].old_path = old_path
                        files_dict[new_path].status = self._map_status_char(status_char)
                else:
                    file_path = parts[1]
                    if file_path in files_dict:
                        files_dict[file_path].status = self._map_status_char(
                            status_char
                        )
                    else:
                        files_dict[file_path] = FileDiff(
                            path=file_path,
                            old_path=None,
                            status=self._map_status_char(status_char),
                            insertions=0,
                            deletions=0,
                            hunks=[],
                        )

        return files_dict

    def _parse_diff_stat_separate(
        self, numstat_output: str, status_output: str
    ) -> dict:
        """Parse separate numstat and name-status outputs.

        Args:
            numstat_output: Raw output from git diff --numstat
            status_output: Raw output from git diff --name-status

        Returns:
            Dictionary mapping path to FileDiff
        """
        files_dict = {}

        # Parse numstat output first (insertions, deletions, path)
        for line in numstat_output.strip().split("\n"):
            if not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) >= 3:
                insertions_str, deletions_str = parts[0], parts[1]
                # Handle renames: old_path -> new_path format
                file_path = parts[2] if len(parts) == 3 else parts[-1]

                insertions = 0 if insertions_str == "-" else int(insertions_str)
                deletions = 0 if deletions_str == "-" else int(deletions_str)

                files_dict[file_path] = FileDiff(
                    path=file_path,
                    old_path=None,
                    status="modified",
                    insertions=insertions,
                    deletions=deletions,
                    hunks=[],
                )

        # Parse name-status output (status, path)
        for line in status_output.strip().split("\n"):
            if not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) >= 2:
                status_char = parts[0]
                if len(parts) == 3:
                    # Rename: status old_path new_path
                    old_path, new_path = parts[1], parts[2]
                    if new_path in files_dict:
                        files_dict[new_path].old_path = old_path
                        files_dict[new_path].status = self._map_status_char(status_char)
                    else:
                        files_dict[new_path] = FileDiff(
                            path=new_path,
                            old_path=old_path,
                            status=self._map_status_char(status_char),
                            insertions=0,
                            deletions=0,
                            hunks=[],
                        )
                else:
                    file_path = parts[1]
                    if file_path in files_dict:
                        files_dict[file_path].status = self._map_status_char(
                            status_char
                        )
                    else:
                        files_dict[file_path] = FileDiff(
                            path=file_path,
                            old_path=None,
                            status=self._map_status_char(status_char),
                            insertions=0,
                            deletions=0,
                            hunks=[],
                        )

        return files_dict

    def _parse_diff_hunks(self, output: str, files_dict: dict) -> None:
        """Parse git diff output and add hunks to files.

        Args:
            output: Raw diff output
            files_dict: Dictionary to update with hunks
        """
        import re

        current_file = None
        current_hunk = None
        hunk_content = []

        for line in output.split("\n"):
            # File header
            if line.startswith("diff --git"):
                if current_hunk and current_file:
                    current_hunk.content = "\n".join(hunk_content)
                current_file = None
                current_hunk = None
                hunk_content = []

            # New file path
            elif line.startswith("+++ b/"):
                current_file = line[6:]

            # Hunk header
            elif line.startswith("@@"):
                if current_hunk and current_file and current_file in files_dict:
                    current_hunk.content = "\n".join(hunk_content)

                hunk_content = []
                match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
                if match and current_file:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2) or 1)
                    new_start = int(match.group(3))
                    new_count = int(match.group(4) or 1)

                    current_hunk = DiffHunk(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        content="",
                    )

                    if current_file in files_dict:
                        files_dict[current_file].hunks.append(current_hunk)

            # Hunk content
            elif current_hunk:
                hunk_content.append(line)

        # Finalize last hunk
        if current_hunk and current_file and current_file in files_dict:
            current_hunk.content = "\n".join(hunk_content)

    def get_blame(
        self,
        path: str,
        revision: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> BlameResult:
        """Get line-by-line blame annotations for a file.

        Args:
            path: Path to file (relative to repo root)
            revision: Revision to blame (None for HEAD)
            start_line: First line to include (1-indexed)
            end_line: Last line to include (1-indexed)

        Returns:
            BlameResult with blame annotations

        Raises:
            ValueError: If file not found
        """
        # Build git blame command with porcelain format
        cmd = ["git", "blame", "--porcelain"]

        if start_line and end_line:
            cmd.extend(["-L", f"{start_line},{end_line}"])
        elif start_line:
            cmd.extend(["-L", f"{start_line},"])

        if revision:
            cmd.append(revision)

        cmd.extend(["--", path])

        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
        except subprocess.CalledProcessError:
            raise ValueError(f"File not found: {path}")

        # Parse porcelain output
        lines = self._parse_blame_output(result.stdout, start_line or 1)

        unique_commits = len(set(line.commit_hash for line in lines))

        return BlameResult(
            path=path,
            revision=revision or "HEAD",
            lines=lines,
            unique_commits=unique_commits,
        )

    def _parse_blame_output(self, output: str, start_line: int) -> List[BlameLine]:
        """Parse git blame --porcelain output.

        Args:
            output: Raw porcelain output
            start_line: Starting line number for output

        Returns:
            List of BlameLine objects
        """
        import re

        lines = []
        current_commit = None
        commit_info = {}
        line_number = start_line
        original_line = 1

        # Regex to match commit header: 40 hex chars followed by space and numbers
        commit_header_pattern = re.compile(r"^([0-9a-f]{40}) (\d+) (\d+)")

        for line in output.split("\n"):
            if not line:
                continue

            # New commit header: <hash> <original_line> <final_line> [<group_lines>]
            match = commit_header_pattern.match(line)
            if match:
                current_commit = match.group(1)
                original_line = int(match.group(2))
                if current_commit not in commit_info:
                    commit_info[current_commit] = {
                        "author": "",
                        "author-mail": "",
                        "author-time": "",
                    }

            # Author info
            elif line.startswith("author "):
                if current_commit:
                    commit_info[current_commit]["author"] = line[7:]
            elif line.startswith("author-mail "):
                if current_commit:
                    email = line[12:].strip("<>")
                    commit_info[current_commit]["author-mail"] = email
            elif line.startswith("author-time "):
                if current_commit:
                    commit_info[current_commit]["author-time"] = line[12:]

            # Content line (starts with tab)
            elif line.startswith("\t"):
                if current_commit:
                    info = commit_info.get(current_commit, {})
                    lines.append(
                        BlameLine(
                            line_number=line_number,
                            commit_hash=current_commit,
                            short_hash=current_commit[:7],
                            author_name=info.get("author", ""),
                            author_email=info.get("author-mail", ""),
                            author_date=info.get("author-time", ""),
                            original_line_number=original_line,
                            content=line[1:],
                        )
                    )
                    line_number += 1

        return lines

    def get_file_history(
        self,
        path: str,
        limit: int = 50,
        follow_renames: bool = True,
    ) -> FileHistoryResult:
        """Get commit history for a specific file.

        Args:
            path: Path to file (relative to repo root)
            limit: Maximum commits to return
            follow_renames: Whether to follow file renames

        Returns:
            FileHistoryResult with file commit history
        """
        # Build git log command
        cmd = [
            "git",
            "log",
            "--format=%H%x00%h%x00%an%x00%aI%x00%s%x00",
            "--numstat",
            f"-{limit + 1}",
        ]

        if follow_renames:
            cmd.append("--follow")

        cmd.extend(["--", path])

        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
        except subprocess.CalledProcessError:
            return FileHistoryResult(
                path=path,
                commits=[],
                total_count=0,
                truncated=False,
                renamed_from=None,
            )

        commits = self._parse_file_history_output(result.stdout)

        truncated = len(commits) > limit
        if truncated:
            commits = commits[:limit]

        return FileHistoryResult(
            path=path,
            commits=commits,
            total_count=len(commits),
            truncated=truncated,
            renamed_from=None,
        )

    def _parse_file_history_output(self, output: str) -> List[FileHistoryCommit]:
        """Parse git log output for file history.

        Args:
            output: Raw git log output

        Returns:
            List of FileHistoryCommit objects
        """
        commits = []
        current_commit = None

        for line in output.split("\n"):
            if not line.strip():
                continue

            # Check if this is a commit line (contains NUL characters)
            if "\x00" in line:
                parts = line.split("\x00")
                if len(parts) >= 5:
                    current_commit = FileHistoryCommit(
                        hash=parts[0],
                        short_hash=parts[1],
                        author_name=parts[2],
                        author_date=parts[3],
                        subject=parts[4],
                        insertions=0,
                        deletions=0,
                        old_path=None,
                    )
                    commits.append(current_commit)

            # numstat line: insertions\tdeletions\tpath
            elif "\t" in line and current_commit:
                parts = line.split("\t")
                if len(parts) >= 2:
                    insertions_str = parts[0]
                    deletions_str = parts[1]
                    if insertions_str != "-":
                        current_commit.insertions = int(insertions_str)
                    if deletions_str != "-":
                        current_commit.deletions = int(deletions_str)

        return commits

    def search_commits(
        self,
        query: str,
        is_regex: bool = False,
        author: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 50,
    ) -> CommitSearchResult:
        """Search commit messages for matching text or pattern.

        Uses git log --grep for searching commit messages.

        Args:
            query: Text or pattern to search for in commit messages
            is_regex: Treat query as extended regex (default: literal text)
            author: Filter to commits by this author
            since: Search only commits after this date
            until: Search only commits before this date
            limit: Maximum number of matching commits to return

        Returns:
            CommitSearchResult with matching commits
        """
        import time

        start_time = time.time()

        # Build git log command
        cmd = ["git", "log", f"--format={self.LOG_FORMAT}"]

        # Add grep pattern
        cmd.append(f"--grep={query}")

        # Regex or literal search
        if is_regex:
            cmd.append("--extended-regexp")

        # Case insensitive by default
        cmd.append("--regexp-ignore-case")

        # Add limit (request one more to detect truncation)
        cmd.append(f"-{limit + 1}")

        # Add filters
        if author:
            cmd.append(f"--author={author}")
        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")

        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
            output = result.stdout
        except subprocess.CalledProcessError:
            # No matching commits
            elapsed = (time.time() - start_time) * 1000
            return CommitSearchResult(
                query=query,
                is_regex=is_regex,
                matches=[],
                total_matches=0,
                truncated=False,
                search_time_ms=elapsed,
            )

        # Parse output
        commits = self._parse_log_output(output)

        # Check if truncated
        truncated = len(commits) > limit
        if truncated:
            commits = commits[:limit]

        # Convert CommitInfo to CommitSearchMatch
        matches = []
        for commit in commits:
            # Extract match highlights from subject and body
            highlights = []
            if query.lower() in commit.subject.lower():
                highlights.append(commit.subject)
            for line in commit.body.split("\n"):
                if query.lower() in line.lower():
                    highlights.append(line)

            matches.append(
                CommitSearchMatch(
                    hash=commit.hash,
                    short_hash=commit.short_hash,
                    author_name=commit.author_name,
                    author_email=commit.author_email,
                    author_date=commit.author_date,
                    subject=commit.subject,
                    body=commit.body,
                    match_highlights=highlights,
                )
            )

        elapsed = (time.time() - start_time) * 1000

        return CommitSearchResult(
            query=query,
            is_regex=is_regex,
            matches=matches,
            total_matches=len(matches),
            truncated=truncated,
            search_time_ms=elapsed,
        )

    def search_diffs(
        self,
        search_string: Optional[str] = None,
        search_pattern: Optional[str] = None,
        is_regex: bool = False,
        path: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 50,
    ) -> DiffSearchResult:
        """Search for commits that added/removed matching content (pickaxe).

        Uses git log -S for literal string search or -G for regex pattern.

        Args:
            search_string: Exact string to search for (-S flag)
            search_pattern: Regex pattern to search for (-G flag)
            is_regex: Whether to use regex matching (requires search_pattern)
            path: Limit search to this path (file or directory)
            since: Search only commits after this date
            until: Search only commits before this date
            limit: Maximum number of matching commits to return

        Returns:
            DiffSearchResult with matching commits

        Raises:
            ValueError: If both or neither search_string and search_pattern
        """
        import time

        start_time = time.time()

        # Validate parameters
        if search_string and search_pattern:
            raise ValueError("search_string and search_pattern are mutually exclusive")
        if not search_string and not search_pattern:
            raise ValueError("Must provide either search_string or search_pattern")

        # Determine search term for result
        search_term = search_pattern if search_pattern else search_string

        # Build git log command
        # Format: hash, short_hash, author_name, author_date, subject
        cmd = [
            "git",
            "log",
            "--format=%H%x00%h%x00%an%x00%aI%x00%s%x00",
            "--name-only",
        ]

        # Add pickaxe search (-S for literal, -G for regex)
        if search_pattern or is_regex:
            cmd.append(f"-G{search_term}")
        else:
            cmd.append(f"-S{search_term}")

        # Add limit (request one more to detect truncation)
        cmd.append(f"-{limit + 1}")

        # Add filters
        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")

        # Path must come last after --
        if path:
            cmd.extend(["--", path])

        try:
            result = run_git_command(cmd, cwd=self.repo_path, check=True)
            output = result.stdout
        except subprocess.CalledProcessError:
            # No matching commits
            elapsed = (time.time() - start_time) * 1000
            return DiffSearchResult(
                search_term=search_term,
                is_regex=is_regex or bool(search_pattern),
                matches=[],
                total_matches=0,
                truncated=False,
                search_time_ms=elapsed,
            )

        # Parse output into matches
        matches = self._parse_diff_search_output(output)

        # Check if truncated
        truncated = len(matches) > limit
        if truncated:
            matches = matches[:limit]

        elapsed = (time.time() - start_time) * 1000

        return DiffSearchResult(
            search_term=search_term,
            is_regex=is_regex or bool(search_pattern),
            matches=matches,
            total_matches=len(matches),
            truncated=truncated,
            search_time_ms=elapsed,
        )

    def _parse_diff_search_output(self, output: str) -> List[DiffSearchMatch]:
        """Parse git log output for diff search results.

        Args:
            output: Raw git log output with --name-only

        Returns:
            List of DiffSearchMatch objects
        """
        matches = []
        current_match = None
        files_changed = []

        for line in output.split("\n"):
            # Check if this is a commit line (contains NUL characters)
            if "\x00" in line:
                # Save previous match if any
                if current_match:
                    current_match.files_changed = files_changed
                    matches.append(current_match)

                parts = line.split("\x00")
                if len(parts) >= 5:
                    current_match = DiffSearchMatch(
                        hash=parts[0],
                        short_hash=parts[1],
                        author_name=parts[2],
                        author_date=parts[3],
                        subject=parts[4],
                        files_changed=[],
                        diff_snippet=None,
                    )
                    files_changed = []

            # File name line (not empty, no NUL)
            elif line.strip() and current_match:
                files_changed.append(line.strip())

        # Don't forget the last match
        if current_match:
            current_match.files_changed = files_changed
            matches.append(current_match)

        return matches
