"""
Regex search service for global repository file pattern matching.

Provides ripgrep-style regex search with grep fallback for searching
directly against files on disk in global repositories.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
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
                logger.debug(f"Skipping non-JSON line from ripgrep output: {line[:100]}")
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

        cmd = ["grep", "-rn", "-E"]

        if not case_sensitive:
            cmd.append("-i")
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])

        if include_patterns:
            for pat in include_patterns:
                cmd.extend(["--include", pat])
        if exclude_patterns:
            for pat in exclude_patterns:
                cmd.extend(["--exclude", pat])

        cmd.append(pattern)
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
                    timeout_seconds=timeout_seconds or DEFAULT_SEARCH_TIMEOUT_SECONDS,
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
