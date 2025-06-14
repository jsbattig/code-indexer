"""Search engine for querying indexed code."""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from ..config import Config
from ..services import OllamaClient, QdrantClient


@dataclass
class SearchResult:
    """A single search result."""
    file_path: str
    content: str
    language: str
    score: float
    file_size: int
    chunk_index: int
    total_chunks: int
    indexed_at: str
    
    @classmethod
    def from_qdrant_result(cls, result: Dict[str, Any]) -> "SearchResult":
        """Create SearchResult from Qdrant search result."""
        payload = result["payload"]
        return cls(
            file_path=payload.get("path", "unknown"),
            content=payload.get("content", ""),
            language=payload.get("language", "unknown"),
            score=result["score"],
            file_size=payload.get("file_size", 0),
            chunk_index=payload.get("chunk_index", 0),
            total_chunks=payload.get("total_chunks", 1),
            indexed_at=payload.get("indexed_at", "unknown")
        )


class SearchEngine:
    """High-level search interface for code queries."""
    
    def __init__(
        self,
        config: Config,
        ollama_client: OllamaClient,
        qdrant_client: QdrantClient
    ):
        self.config = config
        self.ollama_client = ollama_client
        self.qdrant_client = qdrant_client
    
    def search(
        self,
        query: str,
        limit: int = 10,
        language: Optional[str] = None,
        file_path_pattern: Optional[str] = None,
        min_score: Optional[float] = None
    ) -> List[SearchResult]:
        """Search for code matching the query."""
        # Generate query embedding
        query_embedding = self.ollama_client.get_embedding(query)
        
        # Build filter conditions
        filter_conditions = None
        if language or file_path_pattern:
            filter_conditions = {"must": []}
            
            if language:
                filter_conditions["must"].append({
                    "key": "language",
                    "match": {"value": language}
                })
            
            if file_path_pattern:
                filter_conditions["must"].append({
                    "key": "path",
                    "match": {"text": file_path_pattern}
                })
        
        # Perform search
        results = self.qdrant_client.search(
            query_vector=query_embedding,
            limit=limit,
            score_threshold=min_score,
            filter_conditions=filter_conditions
        )
        
        # Convert to SearchResult objects
        return [SearchResult.from_qdrant_result(result) for result in results]
    
    def search_by_file(
        self,
        file_path: str,
        limit: int = 10
    ) -> List[SearchResult]:
        """Search for content within a specific file."""
        filter_conditions = {
            "must": [{"key": "path", "match": {"value": file_path}}]
        }
        
        # Use empty embedding for file-based search (we just want all chunks from the file)
        # This is a simplified approach - could be improved with better file chunking queries
        results = self.qdrant_client.search(
            query_vector=[0.0] * self.config.qdrant.vector_size,  # Dummy vector
            limit=limit,
            filter_conditions=filter_conditions
        )
        
        return [SearchResult.from_qdrant_result(result) for result in results]
    
    def get_similar_code(
        self,
        reference_file: str,
        reference_content: str,
        limit: int = 10,
        exclude_same_file: bool = True
    ) -> List[SearchResult]:
        """Find code similar to the given reference content."""
        # Generate embedding for reference content
        reference_embedding = self.ollama_client.get_embedding(reference_content)
        
        # Build filter to exclude same file if requested
        filter_conditions = None
        if exclude_same_file:
            filter_conditions = {
                "must_not": [{"key": "path", "match": {"value": reference_file}}]
            }
        
        # Search for similar content
        results = self.qdrant_client.search(
            query_vector=reference_embedding,
            limit=limit,
            filter_conditions=filter_conditions
        )
        
        return [SearchResult.from_qdrant_result(result) for result in results]
    
    def search_by_language(
        self,
        language: str,
        query: Optional[str] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """Search within a specific programming language."""
        if query:
            return self.search(
                query=query,
                limit=limit,
                language=language
            )
        else:
            # Return random samples from the language
            filter_conditions = {
                "must": [{"key": "language", "match": {"value": language}}]
            }
            
            # Use empty vector for language browsing
            results = self.qdrant_client.search(
                query_vector=[0.0] * self.config.qdrant.vector_size,
                limit=limit,
                filter_conditions=filter_conditions
            )
            
            return [SearchResult.from_qdrant_result(result) for result in results]
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the search index."""
        try:
            total_points = self.qdrant_client.count_points()
            collection_info = self.qdrant_client.get_collection_info()
            
            return {
                "total_documents": total_points,
                "collection_status": collection_info.get("status", "unknown"),
                "vector_size": collection_info.get("config", {}).get("params", {}).get("vectors", {}).get("size", 0)
            }
        except Exception as e:
            return {
                "error": str(e),
                "total_documents": 0
            }