"""Parser for CIDX query output in proxy mode.

This module provides parsing functionality for real CIDX query output format:
    <score> <absolute_path>:<start_line>-<end_line>
      <line_num>: <code_content>
      <line_num>: <code_content>
      ...
"""

import re
import logging
from typing import List

from .query_result import QueryResult


logger = logging.getLogger(__name__)


class QueryResultParser:
    """Parse CIDX query output into structured QueryResult objects.

    Handles the real CIDX query output format with proper error recovery
    and malformed input handling.
    """

    # Regex pattern for result header line: <score> <path>:<start>-<end>
    # Supports scores like: 0.613, .789
    # Supports paths with spaces
    RESULT_PATTERN = re.compile(r"^([\d.]+)\s+(.+?):(\d+)-(\d+)$")

    # Regex pattern for content lines: "<line_num>: <code>"
    CONTENT_PATTERN = re.compile(r"^(\d+):\s*(.*)$")

    def parse_repository_output(self, output: str, repo_path: str) -> List[QueryResult]:
        """Parse query output from a single repository.

        Args:
            output: Raw stdout from cidx query command
            repo_path: Absolute path to repository (for result association)

        Returns:
            List of parsed QueryResult objects

        Examples:
            >>> output = '''0.613 /home/user/repo/src/auth.py:1-115
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
            line = lines[i]

            # Try to match result header line
            match = self.RESULT_PATTERN.match(line)
            if match:
                try:
                    score = float(match.group(1))
                    file_path = match.group(2)
                    start_line = int(match.group(3))
                    end_line = int(match.group(4))

                    # Validate line range
                    if not self._validate_line_range(start_line, end_line):
                        logger.warning(
                            f"Invalid line range {start_line}-{end_line}, skipping result"
                        )
                        i += 1
                        continue

                    # Collect content lines (including wrapped continuations)
                    content_lines = []
                    j = i + 1
                    while j < len(lines):
                        # Stop if we hit another result header
                        if self.RESULT_PATTERN.match(lines[j]):
                            break

                        # Stop if we hit empty line (end of this result's content)
                        if not lines[j].strip():
                            j += 1  # Skip the blank line
                            break

                        # Collect this line (either numbered line or wrapped continuation)
                        content_lines.append(lines[j])
                        j += 1

                    # Create QueryResult
                    result = QueryResult(
                        score=score,
                        file_path=file_path,
                        line_range=(start_line, end_line),
                        content="\n".join(content_lines),
                        repository=repo_path,
                    )
                    results.append(result)

                    # Continue from where content ended
                    i = j

                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse result line '{line}': {e}")
                    i += 1
            else:
                # Not a result header, skip line
                i += 1

        return results

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
