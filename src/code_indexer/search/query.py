"""Search result data structures for querying indexed code."""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class SearchResult:
    """A single search result from vector store backend."""

    file_path: str
    content: str
    language: str
    score: float
    file_size: int
    chunk_index: int
    total_chunks: int
    indexed_at: str

    @classmethod
    def from_backend_result(cls, result: Dict[str, Any]) -> "SearchResult":
        """Create SearchResult from vector store backend search result."""
        payload = result["payload"]
        return cls(
            file_path=payload.get("path", "unknown"),
            content=payload.get("content", ""),
            language=payload.get("language", "unknown"),
            score=result["score"],
            file_size=payload.get("file_size", 0),
            chunk_index=payload.get("chunk_index", 0),
            total_chunks=payload.get("total_chunks", 1),
            indexed_at=payload.get("indexed_at", "unknown"),
        )
