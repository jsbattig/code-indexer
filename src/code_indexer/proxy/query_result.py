"""Query result data structures for proxy mode.

This module defines the QueryResult dataclass used to represent semantic
search results from individual repositories with full metadata preservation.
"""

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class QueryResult:
    """Represents a single query result from a repository.

    This dataclass encapsulates all metadata from a semantic search result
    including the similarity score, file location, line range, code content,
    and source repository.

    Attributes:
        score: Semantic similarity score (0.0-1.0)
        file_path: Absolute path to the matched file
        line_range: Tuple of (start_line, end_line) for the match
        content: Code snippet content from the matched region
        repository: Absolute path to the source repository
        language: Programming language (e.g., 'py', 'js', 'rust')
        size: File size in bytes
        indexed_timestamp: ISO timestamp when file was indexed
        branch: Git branch name
        commit: Git commit hash (abbreviated)
        project_name: Project name
    """

    score: float
    file_path: str
    line_range: Tuple[int, int]
    content: str
    repository: str
    language: Optional[str] = None
    size: Optional[int] = None
    indexed_timestamp: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    project_name: Optional[str] = None

    def __repr__(self) -> str:
        """Return detailed string representation of QueryResult."""
        return (
            f"QueryResult(score={self.score:.2f}, "
            f"file_path='{self.file_path}', "
            f"line_range={self.line_range}, "
            f"repository='{self.repository}')"
        )
