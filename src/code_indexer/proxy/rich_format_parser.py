"""Parser for CIDX rich query output (non-quiet mode) in proxy mode.

This module provides parsing functionality for rich CIDX query output format
that includes full metadata:

    📄 File: <path>:<lines> | 🏷️  Language: <lang> | 📊 Score: <score>
    📏 Size: <size> bytes | 🕒 Indexed: <timestamp> | 🌿 Branch: <branch> | 📦 Commit: <commit> | 🏗️  Project: <project>

    📖 Content (Lines <start>-<end>):
    ──────────────────────────────────────────────────
      <line_num>: <code_content>
      <line_num>: <code_content>
      ...

    ================================================================================
"""

import re
import logging
from typing import List, Optional

from .query_result import QueryResult


logger = logging.getLogger(__name__)


class RichFormatParser:
    """Parse rich CIDX query output into structured QueryResult objects.

    Handles the rich (non-quiet) CIDX query output format with full metadata
    including file info, language, size, timestamp, branch, commit, project.
    """

    # Regex pattern for first line: 📄 File: <path>:<start>-<end> | 🏷️  Language: <lang> | 📊 Score: <score>
    FILE_HEADER_PATTERN = re.compile(
        r"^📄 File:\s+(.+?):(\d+)-(\d+)\s+\|\s+🏷️\s+Language:\s+(\S+)\s+\|\s+📊 Score:\s+([\d.]+)$"
    )

    # Regex pattern for second line: 📏 Size: <size> bytes | 🕒 Indexed: <timestamp> | 🌿 Branch: <branch> | 📦 Commit: <commit> | 🏗️  Project: <project>
    METADATA_PATTERN = re.compile(
        r"^📏 Size:\s+(\d+)\s+bytes\s+\|\s+🕒 Indexed:\s+(.+?)\s+\|\s+🌿 Branch:\s+(.+?)\s+\|\s+📦 Commit:\s+(.+?)\s+\|\s+🏗️\s+Project:\s+(.+)$"
    )

    # Regex pattern for content header: 📖 Content (Lines <start>-<end>):
    CONTENT_HEADER_PATTERN = re.compile(r"^📖 Content \(Lines \d+-\d+\):$")

    # Regex pattern for separator line
    SEPARATOR_PATTERN = re.compile(r"^─+$")

    # Regex pattern for result separator
    RESULT_SEPARATOR_PATTERN = re.compile(r"^=+$")

    # Regex pattern for content lines: "<line_num>: <code>"
    CONTENT_LINE_PATTERN = re.compile(r"^  (\d+):\s*(.*)$")

    def parse_repository_output(self, output: str, repo_path: str) -> List[QueryResult]:
        """Parse rich query output from a single repository.

        Args:
            output: Raw stdout from cidx query command (rich format)
            repo_path: Absolute path to repository (for result association)

        Returns:
            List of parsed QueryResult objects with full metadata

        Examples:
            >>> output = '''📄 File: /home/user/repo/src/auth.py:1-115 | 🏷️  Language: py | 📊 Score: 0.613
            ... 📏 Size: 5432 bytes | 🕒 Indexed: 2025-09-29T20:03:20Z | 🌿 Branch: master | 📦 Commit: abc123... | 🏗️  Project: backend
            ...
            ... 📖 Content (Lines 1-115):
            ... ──────────────────────────────────────────────────
            ...   1: def authenticate(username, password):
            ...   2:     return True'''
            >>> parser.parse_repository_output(output, "/home/user/repo")
            [QueryResult(score=0.613, file_path='/home/user/repo/src/auth.py', ...)]
        """
        if not output or not output.strip():
            return []

        results = []
        lines = output.strip().split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Try to match file header line
            file_match = self.FILE_HEADER_PATTERN.match(line)
            if file_match:
                try:
                    # Extract file header info
                    file_path = file_match.group(1).strip()
                    start_line = int(file_match.group(2))
                    end_line = int(file_match.group(3))
                    language = file_match.group(4).strip()
                    score = float(file_match.group(5))

                    # Validate line range
                    if not self._validate_line_range(start_line, end_line):
                        logger.warning(
                            f"Invalid line range {start_line}-{end_line}, skipping result"
                        )
                        i += 1
                        continue

                    # Parse metadata line (next line)
                    metadata = self._parse_metadata_line(lines, i + 1)
                    if not metadata:
                        logger.warning("Failed to parse metadata line, skipping result")
                        i += 1
                        continue

                    # Skip to content section
                    content_start = self._find_content_start(lines, i + 2)
                    if content_start == -1:
                        logger.warning("Failed to find content section, skipping result")
                        i += 1
                        continue

                    # Collect content lines
                    content_lines = self._collect_content_lines(lines, content_start)

                    # Create QueryResult with full metadata
                    result = QueryResult(
                        score=score,
                        file_path=file_path,
                        line_range=(start_line, end_line),
                        content="\n".join(content_lines),
                        repository=repo_path,
                        language=language,
                        size=metadata.get("size"),
                        indexed_timestamp=metadata.get("timestamp"),
                        branch=metadata.get("branch"),
                        commit=metadata.get("commit"),
                        project_name=metadata.get("project"),
                    )
                    results.append(result)

                    # Move to next result (skip past content and separator)
                    i = content_start + len(content_lines)
                    # Skip separator line and blank lines
                    while i < len(lines) and (
                        not lines[i].strip()
                        or self.RESULT_SEPARATOR_PATTERN.match(lines[i].strip())
                    ):
                        i += 1

                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse result line '{line}': {e}")
                    i += 1
            else:
                # Not a file header, skip line
                i += 1

        return results

    def _parse_metadata_line(self, lines: List[str], index: int) -> Optional[dict]:
        """Parse metadata line (second line of result).

        Args:
            lines: All output lines
            index: Index of metadata line

        Returns:
            Dict with metadata fields, or None if parsing fails
        """
        if index >= len(lines):
            return None

        line = lines[index].strip()
        match = self.METADATA_PATTERN.match(line)

        if not match:
            return None

        return {
            "size": int(match.group(1)),
            "timestamp": match.group(2).strip(),
            "branch": match.group(3).strip(),
            "commit": match.group(4).strip(),
            "project": match.group(5).strip(),
        }

    def _find_content_start(self, lines: List[str], start_index: int) -> int:
        """Find the start of content lines (after separator).

        Args:
            lines: All output lines
            start_index: Index to start searching from

        Returns:
            Index of first content line, or -1 if not found
        """
        i = start_index

        # Skip blank lines and content header
        while i < len(lines):
            line = lines[i].strip()

            # Skip blank lines
            if not line:
                i += 1
                continue

            # Skip content header
            if self.CONTENT_HEADER_PATTERN.match(line):
                i += 1
                continue

            # Skip separator line
            if self.SEPARATOR_PATTERN.match(line):
                i += 1
                continue

            # Found first content line
            return i

        return -1

    def _collect_content_lines(self, lines: List[str], start_index: int) -> List[str]:
        """Collect content lines from result.

        Args:
            lines: All output lines
            start_index: Index of first content line

        Returns:
            List of content lines (formatted with line numbers)
        """
        content_lines = []
        i = start_index

        while i < len(lines):
            line = lines[i]

            # Stop if we hit result separator
            if self.RESULT_SEPARATOR_PATTERN.match(line.strip()):
                break

            # Stop if we hit next result's file header
            if self.FILE_HEADER_PATTERN.match(line.strip()):
                break

            # Stop if we hit a blank line (end of content)
            if not line.strip():
                break

            # Collect this line (preserve original formatting including indentation)
            content_lines.append(line)
            i += 1

        return content_lines

    def _validate_line_range(self, start: int, end: int) -> bool:
        """Validate that line range is valid.

        Args:
            start: Starting line number
            end: Ending line number

        Returns:
            True if valid, False otherwise
        """
        # Line numbers must be positive
        if start < 1 or end < 1:
            return False

        # End must be >= start
        if end < start:
            return False

        return True
