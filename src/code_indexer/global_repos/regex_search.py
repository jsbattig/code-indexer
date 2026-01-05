"""
Regex search service for global repository file pattern matching.

Provides ripgrep-style regex search with grep fallback for searching
directly against files on disk in global repositories.
"""

import json
import logging
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default timeout for search operations (5 minutes)
DEFAULT_SEARCH_TIMEOUT_SECONDS = 300


@dataclass
class RegexMatch:
    """A single regex match result."""

    file_path: str
    line_number: int
    column: int
    line_content: str
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)


@dataclass
class RegexSearchResult:
    """Result of a regex search operation."""

    matches: List[RegexMatch]
    total_matches: int
    truncated: bool
    search_engine: str
    search_time_ms: float


class RegexSearchService:
    """Service for performing regex searches on repository files."""

    def __init__(self, repo_path: Path):
        """Initialize the regex search service.

        Args:
            repo_path: Path to the repository root

        Raises:
            RuntimeError: If neither ripgrep nor grep is available
        """
        self.repo_path = repo_path
        self._search_engine = self._detect_search_engine()

    def _detect_search_engine(self) -> str:
        """Detect available search engine (ripgrep preferred).

        Returns:
            String identifying the search engine ("ripgrep" or "grep")

        Raises:
            RuntimeError: If neither ripgrep nor grep is found
        """
        if shutil.which("rg"):
            return "ripgrep"
        elif shutil.which("grep"):
            return "grep"
        else:
            raise RuntimeError("Neither ripgrep nor grep found on system")

    async def search(
        self,
        pattern: str,
        path: Optional[str] = None,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        case_sensitive: bool = True,
        context_lines: int = 0,
        max_results: int = 100,
        timeout_seconds: Optional[int] = None,
    ) -> RegexSearchResult:
        """Execute regex search and return structured results.

        Args:
            pattern: Regular expression pattern to search for
            path: Subdirectory to search within (relative to repo root)
            include_patterns: Glob patterns for files to include
            exclude_patterns: Glob patterns for files to exclude
            case_sensitive: Whether search is case-sensitive
            context_lines: Number of context lines before/after match
            max_results: Maximum number of matches to return
            timeout_seconds: Maximum execution time in seconds (optional)

        Returns:
            RegexSearchResult with matches and metadata

        Raises:
            ValueError: If path doesn't exist
            TimeoutError: If search exceeds timeout_seconds
        """
        start_time = time.time()

        search_path = self.repo_path / path if path else self.repo_path
        if not search_path.exists():
            raise ValueError(f"Path does not exist: {path}")

        if self._search_engine == "ripgrep":
            matches, total = await self._search_ripgrep(
                pattern,
                search_path,
                include_patterns,
                exclude_patterns,
                case_sensitive,
                context_lines,
                max_results,
                timeout_seconds,
            )
        else:
            matches, total = await self._search_grep(
                pattern,
                search_path,
                include_patterns,
                exclude_patterns,
                case_sensitive,
                context_lines,
                max_results,
                timeout_seconds,
            )

        elapsed_ms = (time.time() - start_time) * 1000
        return RegexSearchResult(
            matches=matches,
            total_matches=total,
            truncated=total > max_results,
            search_engine=self._search_engine,
            search_time_ms=elapsed_ms,
        )

    def _parse_ripgrep_json_output(
        self,
        output: str,
        max_results: int,
        context_lines: int,
    ) -> tuple:
        """Parse ripgrep JSON output into RegexMatch objects.

        Args:
            output: JSON output from ripgrep command
            max_results: Maximum number of matches to return
            context_lines: Number of context lines (used for context parsing)

        Returns:
            Tuple of (matches list, total count)
        """
        matches: List[RegexMatch] = []
        total = 0
        context_before: List[str] = []

        for line in output.splitlines():
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    total += 1
                    if len(matches) < max_results:
                        match_data = data["data"]
                        abs_path = match_data["path"]["text"]
                        try:
                            rel_path = str(Path(abs_path).relative_to(self.repo_path))
                        except ValueError:
                            rel_path = abs_path

                        submatches = match_data.get("submatches", [])
                        column = submatches[0]["start"] + 1 if submatches else 1

                        matches.append(
                            RegexMatch(
                                file_path=rel_path,
                                line_number=match_data["line_number"],
                                column=column,
                                line_content=match_data["lines"]["text"].rstrip("\n"),
                                context_before=context_before.copy(),
                                context_after=[],
                            )
                        )
                        context_before = []
                elif data.get("type") == "context" and context_lines > 0:
                    ctx = data["data"]["lines"]["text"].rstrip("\n")
                    if (
                        matches
                        and data["data"]["line_number"] > matches[-1].line_number
                    ):
                        matches[-1].context_after.append(ctx)
                    else:
                        context_before.append(ctx)
            except json.JSONDecodeError:
                logger.debug(
                    f"Skipping non-JSON line from ripgrep output: {line[:100]}"
                )
                continue

        return matches, total

    async def _search_ripgrep(
        self,
        pattern: str,
        search_path: Path,
        include_patterns: Optional[List[str]],
        exclude_patterns: Optional[List[str]],
        case_sensitive: bool,
        context_lines: int,
        max_results: int,
        timeout_seconds: Optional[int],
    ) -> tuple:
        """Search using ripgrep with JSON output and timeout protection."""
        from code_indexer.server.services.subprocess_executor import (
            SubprocessExecutor,
            ExecutionStatus,
        )

        cmd = ["rg", "--json", pattern]

        if not case_sensitive:
            cmd.append("-i")
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])

        if include_patterns:
            for pat in include_patterns:
                cmd.extend(["-g", pat])
        if exclude_patterns:
            for pat in exclude_patterns:
                cmd.extend(["-g", f"!{pat}"])

        cmd.append(str(search_path))

        # Create temp file for output
        temp_fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="rg_search_")
        os.close(temp_fd)

        try:
            # Execute with SubprocessExecutor for async + timeout protection
            executor = SubprocessExecutor(max_workers=1)
            try:
                result = await executor.execute_with_limits(
                    command=cmd,
                    working_dir=str(self.repo_path),
                    timeout_seconds=timeout_seconds or DEFAULT_SEARCH_TIMEOUT_SECONDS,
                    output_file_path=temp_path,
                )

                if result.timed_out:
                    raise TimeoutError(
                        f"Search timed out after {result.timeout_seconds} seconds"
                    )

                if result.status == ExecutionStatus.ERROR:
                    logger.warning(f"ripgrep command failed: {result.error_message}")
                    # Return empty results on error (ripgrep returns non-zero when no matches)
                    return [], 0

                # Read output from temp file
                with open(temp_path, "r") as f:
                    output = f.read()

            finally:
                executor.shutdown(wait=True)
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return self._parse_ripgrep_json_output(output, max_results, context_lines)

    async def _find_files_by_patterns(
        self,
        search_path: Path,
        include_patterns: List[str],
        exclude_patterns: Optional[List[str]],
        timeout_seconds: int,
    ) -> List[str]:
        """Use Python pathlib glob to get files matching patterns (like ripgrep -g).

        Supports the following pattern types to match ripgrep's -g flag behavior:
        - "**/file.java" - Recursive search from search_path
        - "code/**/file.java" - Recursive search from search_path/code
        - "code/src/file.java" - Explicit path (non-recursive)
        - "*.java" - Simple pattern (recursive from search_path)

        Args:
            search_path: Base directory to search from. All patterns resolved relative to this path.
            include_patterns: List of glob patterns following ripgrep -g flag syntax.
            exclude_patterns: Optional list of patterns to exclude from results.
            timeout_seconds: Maximum time to spend searching (currently unused in glob implementation).

        Returns:
            List of relative file paths as strings for all files matching include patterns
            and not matching exclude patterns. Empty list if no matches found.

        Raises:
            ValueError: If pattern contains invalid glob syntax (e.g., unclosed brackets).
            PermissionError: If directories are not readable during traversal.
        """
        import fnmatch

        matched_files = set()

        for pattern in include_patterns:
            # Handle different pattern types to match ripgrep -g behavior
            if pattern.startswith("**/"):
                # Pattern like **/filename.ext or **/dir/*.ext
                # Use rglob for recursive matching from search_path
                sub_pattern = pattern[3:]  # Remove **/ prefix
                for file_path in search_path.rglob(sub_pattern):
                    if file_path.is_file():
                        matched_files.add(file_path)

            elif "**" in pattern:
                # Pattern like dir/**/filename.ext (** in middle)
                # Split on /** and use rglob for the recursive part
                parts = pattern.split("/**/")
                if len(parts) == 2:
                    prefix, suffix = parts
                    # Find all directories matching prefix
                    prefix_path = search_path / prefix if prefix else search_path
                    if prefix_path.exists() and prefix_path.is_dir():
                        # Use rglob from prefix_path for suffix pattern
                        for file_path in prefix_path.rglob(suffix):
                            if file_path.is_file():
                                matched_files.add(file_path)
                else:
                    # Multiple ** in pattern - fall back to walking entire tree
                    for file_path in search_path.rglob("*"):
                        if file_path.is_file():
                            rel_path = str(file_path.relative_to(search_path))
                            if fnmatch.fnmatch(rel_path, pattern):
                                matched_files.add(file_path)

            elif "/" in pattern:
                # Explicit path pattern like code/src/Main.java
                # Use glob for non-recursive matching
                for file_path in search_path.glob(pattern):
                    if file_path.is_file():
                        matched_files.add(file_path)

            else:
                # Simple filename pattern like *.java
                # Use rglob to find at any depth
                for file_path in search_path.rglob(pattern):
                    if file_path.is_file():
                        matched_files.add(file_path)

        # Apply exclude patterns
        if exclude_patterns:
            filtered_files = set()
            for file_path in matched_files:
                rel_path = str(file_path.relative_to(search_path))
                excluded = False
                for exclude_pattern in exclude_patterns:
                    # Match exclude pattern anywhere in path
                    if fnmatch.fnmatch(rel_path, f"*{exclude_pattern}*"):
                        excluded = True
                        break
                if not excluded:
                    filtered_files.add(file_path)
            matched_files = filtered_files

        # Convert to relative paths as strings (like find output)
        return [
            str(file_path.relative_to(search_path))
            for file_path in sorted(matched_files)
        ]

    def _build_grep_command(
        self,
        pattern: str,
        case_sensitive: bool,
        context_lines: int,
        recursive: bool,
        file_list: Optional[List[str]] = None,
    ) -> List[str]:
        """Build grep command with common flags.

        Always includes -H flag to force filename output even when searching
        a single file. This ensures consistent parsing of grep output where
        the regex expects 'filename:line:content' format.
        """
        cmd = ["grep", "-E", "-H"]
        if recursive:
            cmd.append("-rn")
        else:
            cmd.append("-n")
        if not case_sensitive:
            cmd.append("-i")
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])
        cmd.append(pattern)
        if file_list:
            cmd.extend(file_list)
        return cmd

    async def _search_grep(
        self,
        pattern: str,
        search_path: Path,
        include_patterns: Optional[List[str]],
        exclude_patterns: Optional[List[str]],
        case_sensitive: bool,
        context_lines: int,
        max_results: int,
        timeout_seconds: Optional[int],
    ) -> tuple:
        """Fallback search using grep with timeout protection."""
        from code_indexer.server.services.subprocess_executor import (
            SubprocessExecutor,
            ExecutionStatus,
        )

        timeout = timeout_seconds or DEFAULT_SEARCH_TIMEOUT_SECONDS
        has_path_patterns = include_patterns and any('/' in pat for pat in include_patterns)

        if has_path_patterns:
            # Use find to get files matching all patterns (both path and simple)
            # Type assertion: has_path_patterns ensures include_patterns is not None
            assert include_patterns is not None
            file_list = await self._find_files_by_patterns(
                search_path, include_patterns, exclude_patterns, timeout
            )
            if not file_list:
                return [], 0

            cmd = self._build_grep_command(pattern, case_sensitive, context_lines, False, file_list)
        else:
            # Original behavior: recursive grep with --include/--exclude
            cmd = self._build_grep_command(pattern, case_sensitive, context_lines, True)
            if include_patterns:
                for pat in include_patterns:
                    cmd.extend(["--include", pat])
            if exclude_patterns:
                for pat in exclude_patterns:
                    cmd.extend(["--exclude", pat])
            cmd.append(str(search_path))

        # Create temp file for output
        temp_fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="grep_search_")
        os.close(temp_fd)

        try:
            # Execute with SubprocessExecutor for async + timeout protection
            executor = SubprocessExecutor(max_workers=1)
            try:
                result = await executor.execute_with_limits(
                    command=cmd,
                    working_dir=str(self.repo_path),
                    timeout_seconds=timeout,
                    output_file_path=temp_path,
                )

                if result.timed_out:
                    raise TimeoutError(
                        f"Search timed out after {result.timeout_seconds} seconds"
                    )

                if result.status == ExecutionStatus.ERROR:
                    logger.warning(f"grep command failed: {result.error_message}")
                    # Return empty results on error (grep returns non-zero when no matches)
                    return [], 0

                # Read output from temp file
                with open(temp_path, "r") as f:
                    output = f.read()

            finally:
                executor.shutdown(wait=True)
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

        matches: List[RegexMatch] = []
        total = 0

        for line in output.splitlines():
            match = re.match(r"^(.+?):(\d+):(.*)$", line)
            if match:
                total += 1
                if len(matches) < max_results:
                    file_path = match.group(1)
                    try:
                        rel_path = str(Path(file_path).relative_to(self.repo_path))
                    except ValueError:
                        rel_path = file_path

                    matches.append(
                        RegexMatch(
                            file_path=rel_path,
                            line_number=int(match.group(2)),
                            column=1,
                            line_content=match.group(3),
                            context_before=[],
                            context_after=[],
                        )
                    )

        return matches, total
