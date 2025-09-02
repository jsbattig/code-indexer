"""
Search functionality implementation for semantic code search.

This module provides vector-based semantic search capabilities,
query processing, result ranking, and search history management.
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """Search mode options."""

    SEMANTIC = "semantic"
    EXACT = "exact"
    FUZZY = "fuzzy"
    HYBRID = "hybrid"


@dataclass
class SearchQuery:
    """Search query data structure."""

    text: str
    mode: SearchMode = SearchMode.SEMANTIC
    limit: int = 10
    min_score: float = 0.1
    filters: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    repository_id: Optional[str] = None


@dataclass
class SearchResult:
    """Search result data structure."""

    file_path: str
    content: str
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    line_number: int = 0
    score: float = 0.0
    snippet: str = ""
    language: str = "unknown"
    metadata: Optional[Dict[str, Any]] = None


class VectorStore:
    """Vector storage and similarity search functionality."""

    def __init__(self, dimension: int = 1024):
        """
        Initialize vector store.

        Args:
            dimension: Vector dimension size
        """
        self.dimension = dimension
        self.vectors: Dict[str, np.ndarray] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(f"{__name__}.VectorStore")

    def add_vector(
        self, doc_id: str, vector: np.ndarray, metadata: Dict[str, Any] = None
    ) -> None:
        """
        Add vector to store.

        Args:
            doc_id: Document identifier
            vector: Document vector embedding
            metadata: Optional metadata
        """
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, got {vector.shape[0]}"
            )

        self.vectors[doc_id] = vector
        self.metadata[doc_id] = metadata or {}

        self.logger.debug(f"Added vector for document: {doc_id}")

    def search_similar(
        self, query_vector: np.ndarray, limit: int = 10, min_score: float = 0.1
    ) -> List[Tuple[str, float]]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query vector
            limit: Maximum results to return
            min_score: Minimum similarity score

        Returns:
            List of (doc_id, score) tuples
        """
        if not self.vectors:
            return []

        if query_vector.shape[0] != self.dimension:
            raise ValueError(
                f"Query vector dimension mismatch: expected {self.dimension}"
            )

        # Calculate cosine similarity with all vectors
        doc_ids = list(self.vectors.keys())
        doc_vectors = np.array([self.vectors[doc_id] for doc_id in doc_ids])

        # Reshape query vector for sklearn
        query_vector_reshaped = query_vector.reshape(1, -1)

        # Calculate similarities
        similarities = cosine_similarity(query_vector_reshaped, doc_vectors)[0]

        # Create results with scores
        results = []
        for doc_id, similarity in zip(doc_ids, similarities):
            if similarity >= min_score:
                results.append((doc_id, float(similarity)))

        # Sort by similarity score (descending) and limit results
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_metadata(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for document."""
        return self.metadata.get(doc_id)

    def remove_vector(self, doc_id: str) -> bool:
        """Remove vector from store."""
        if doc_id in self.vectors:
            del self.vectors[doc_id]
            self.metadata.pop(doc_id, None)
            return True
        return False

    def clear(self) -> None:
        """Clear all vectors and metadata."""
        self.vectors.clear()
        self.metadata.clear()

    @property
    def size(self) -> int:
        """Get number of stored vectors."""
        return len(self.vectors)


class QueryProcessor:
    """Query processing and enhancement functionality."""

    def __init__(self):
        """Initialize query processor."""
        self.logger = logging.getLogger(f"{__name__}.QueryProcessor")

    def process_query(self, query: SearchQuery) -> SearchQuery:
        """
        Process and enhance search query.

        Args:
            query: Original search query

        Returns:
            Processed search query
        """
        # Clean and normalize query text
        processed_text = self._clean_query_text(query.text)

        # Expand query with synonyms/related terms
        expanded_text = self._expand_query(processed_text)

        # Apply mode-specific processing
        if query.mode == SearchMode.FUZZY:
            expanded_text = self._add_fuzzy_terms(expanded_text)

        # Create processed query
        processed_query = SearchQuery(
            text=expanded_text,
            mode=query.mode,
            limit=query.limit,
            min_score=query.min_score,
            filters=query.filters,
            user_id=query.user_id,
            repository_id=query.repository_id,
        )

        self.logger.debug(f"Processed query: '{query.text}' -> '{expanded_text}'")
        return processed_query

    def _clean_query_text(self, text: str) -> str:
        """Clean and normalize query text."""
        # Remove extra whitespace
        cleaned = " ".join(text.split())

        # Convert to lowercase for better matching
        cleaned = cleaned.lower()

        # Remove special characters that might interfere
        import re

        cleaned = re.sub(r"[^\w\s\-_.]", " ", cleaned)

        return cleaned.strip()

    def _expand_query(self, text: str) -> str:
        """Expand query with related terms."""
        # Simple keyword expansion (in real implementation, use NLP models)
        expansions = {
            "auth": ["authentication", "login", "credential", "token"],
            "api": ["endpoint", "route", "handler", "rest"],
            "database": ["db", "sql", "query", "connection"],
            "error": ["exception", "fail", "bug", "issue"],
            "user": ["account", "profile", "identity"],
            "config": ["configuration", "setting", "option"],
            "search": ["query", "find", "lookup", "retrieve"],
            "function": ["method", "def", "procedure"],
            "class": ["object", "type", "model"],
            "test": ["unit", "integration", "spec", "verify"],
        }

        words = text.split()
        expanded_words = []

        for word in words:
            expanded_words.append(word)
            # Add related terms if available
            if word in expansions:
                # Add first related term to avoid over-expansion
                expanded_words.append(expansions[word][0])

        return " ".join(expanded_words)

    def _add_fuzzy_terms(self, text: str) -> str:
        """Add fuzzy matching terms."""
        # For fuzzy search, we might add partial terms or common typos
        words = text.split()
        fuzzy_terms = []

        for word in words:
            fuzzy_terms.append(word)
            if len(word) > 4:  # Add partial matches for longer words
                fuzzy_terms.append(word[: len(word) // 2])

        return " ".join(fuzzy_terms)


class ResultRanker:
    """Result ranking and scoring functionality."""

    def __init__(self):
        """Initialize result ranker."""
        self.logger = logging.getLogger(f"{__name__}.ResultRanker")

    def rank_results(
        self, results: List[SearchResult], query: SearchQuery
    ) -> List[SearchResult]:
        """
        Rank search results by relevance.

        Args:
            results: List of search results
            query: Original search query

        Returns:
            Ranked list of results
        """
        # Apply scoring factors
        scored_results = []
        for result in results:
            total_score = self._calculate_relevance_score(result, query)
            result.score = total_score
            scored_results.append(result)

        # Sort by score (descending)
        ranked_results = sorted(scored_results, key=lambda r: r.score, reverse=True)

        self.logger.debug(f"Ranked {len(results)} results")
        return ranked_results

    def _calculate_relevance_score(
        self, result: SearchResult, query: SearchQuery
    ) -> float:
        """Calculate relevance score for a result."""
        base_score = result.score  # Vector similarity score

        # Boost scores based on various factors
        boosts = []

        # File type boost (prefer certain languages)
        language_boosts = {"python": 0.1, "javascript": 0.08, "java": 0.06, "cpp": 0.05}
        if result.language in language_boosts:
            boosts.append(language_boosts[result.language])

        # Function name match boost
        if result.function_name and any(
            term in result.function_name.lower() for term in query.text.lower().split()
        ):
            boosts.append(0.15)

        # Exact phrase match boost
        if query.text.lower() in result.content.lower():
            boosts.append(0.2)

        # File path relevance boost
        if any(term in result.file_path.lower() for term in query.text.lower().split()):
            boosts.append(0.1)

        # Apply boosts
        total_boost = sum(boosts)
        final_score = min(base_score + total_boost, 1.0)  # Cap at 1.0

        return final_score


class SearchEngine:
    """Main search engine coordinating all search components."""

    def __init__(self, vector_store: VectorStore = None):
        """
        Initialize search engine.

        Args:
            vector_store: Vector store instance
        """
        self.vector_store = vector_store or VectorStore()
        self.query_processor = QueryProcessor()
        self.result_ranker = ResultRanker()
        self.search_history: List[Dict[str, Any]] = []

        self.logger = logging.getLogger(f"{__name__}.SearchEngine")

    async def search(self, query: SearchQuery) -> List[SearchResult]:
        """
        Perform semantic search.

        Args:
            query: Search query

        Returns:
            List of ranked search results
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Process query
            processed_query = self.query_processor.process_query(query)

            # Generate query vector (mock implementation)
            query_vector = await self._generate_query_vector(processed_query.text)

            # Search similar vectors
            similar_docs = self.vector_store.search_similar(
                query_vector,
                processed_query.limit * 2,  # Get more candidates for ranking
                processed_query.min_score,
            )

            # Convert to SearchResult objects
            results = []
            for doc_id, score in similar_docs:
                metadata = self.vector_store.get_metadata(doc_id)
                if metadata:
                    result = self._create_search_result(doc_id, score, metadata)
                    if self._apply_filters(result, processed_query.filters):
                        results.append(result)

            # Rank results
            ranked_results = self.result_ranker.rank_results(results, processed_query)

            # Limit final results
            final_results = ranked_results[: processed_query.limit]

            # Log search
            execution_time = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000
            self._log_search(query, len(final_results), execution_time)

            return final_results

        except Exception as e:
            self.logger.error(f"Search error: {e}")
            raise

    async def _generate_query_vector(self, query_text: str) -> np.ndarray:
        """
        Generate vector embedding for query text.

        Args:
            query_text: Query text

        Returns:
            Query vector embedding
        """
        # Mock vector generation (in real implementation, use embedding model)
        # Create a simple hash-based vector for demonstration
        import hashlib

        # Create deterministic vector based on query text
        hash_obj = hashlib.sha256(query_text.encode())
        hash_bytes = hash_obj.digest()

        # Convert to vector (repeat pattern to fill dimension)
        vector_data = []
        for i in range(self.vector_store.dimension):
            byte_index = i % len(hash_bytes)
            vector_data.append(hash_bytes[byte_index] / 255.0)  # Normalize to 0-1

        return np.array(vector_data, dtype=np.float32)

    def _create_search_result(
        self, doc_id: str, score: float, metadata: Dict[str, Any]
    ) -> SearchResult:
        """Create SearchResult from document metadata."""
        return SearchResult(
            file_path=metadata.get("file_path", doc_id),
            content=metadata.get("content", ""),
            function_name=metadata.get("function_name"),
            class_name=metadata.get("class_name"),
            line_number=metadata.get("line_number", 0),
            score=score,
            snippet=metadata.get("snippet", "")[:200],  # Limit snippet length
            language=metadata.get("language", "unknown"),
            metadata=metadata,
        )

    def _apply_filters(
        self, result: SearchResult, filters: Optional[Dict[str, Any]]
    ) -> bool:
        """Apply filters to search result."""
        if not filters:
            return True

        # Language filter
        if "language" in filters and result.language not in filters["language"]:
            return False

        # File path filter
        if "file_path" in filters:
            path_patterns = filters["file_path"]
            if not any(pattern in result.file_path for pattern in path_patterns):
                return False

        # Minimum score filter
        if "min_score" in filters and result.score < filters["min_score"]:
            return False

        return True

    def _log_search(
        self, query: SearchQuery, results_count: int, execution_time_ms: float
    ) -> None:
        """Log search query for analytics."""
        search_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query.text,
            "mode": query.mode.value,
            "user_id": query.user_id,
            "repository_id": query.repository_id,
            "results_count": results_count,
            "execution_time_ms": int(execution_time_ms),
            "filters": query.filters,
        }

        self.search_history.append(search_log)

        # Keep only recent history (last 1000 searches)
        if len(self.search_history) > 1000:
            self.search_history = self.search_history[-1000:]

        self.logger.info(
            f"Search: '{query.text}' -> {results_count} results ({int(execution_time_ms)}ms)"
        )

    def get_search_stats(self) -> Dict[str, Any]:
        """Get search engine statistics."""
        if not self.search_history:
            return {"total_searches": 0, "vector_store_size": self.vector_store.size}

        total_searches = len(self.search_history)
        avg_execution_time = (
            sum(log["execution_time_ms"] for log in self.search_history)
            / total_searches
        )
        avg_results = (
            sum(log["results_count"] for log in self.search_history) / total_searches
        )

        # Most common queries
        from collections import Counter

        query_counts = Counter(
            log["query"] for log in self.search_history[-100:]
        )  # Last 100 searches

        return {
            "total_searches": total_searches,
            "vector_store_size": self.vector_store.size,
            "average_execution_time_ms": round(avg_execution_time, 2),
            "average_results_per_query": round(avg_results, 2),
            "most_common_queries": query_counts.most_common(5),
        }

    def index_document(
        self, doc_id: str, content: str, metadata: Dict[str, Any] = None
    ) -> None:
        """
        Index document for search.

        Args:
            doc_id: Document identifier
            content: Document content
            metadata: Document metadata
        """
        # Generate vector for document content
        # This is a mock implementation - in real scenario, use proper embedding model
        vector = asyncio.run(self._generate_query_vector(content))

        # Add to vector store
        full_metadata = metadata or {}
        full_metadata["content"] = content
        full_metadata["indexed_at"] = datetime.now(timezone.utc).isoformat()

        self.vector_store.add_vector(doc_id, vector, full_metadata)

        self.logger.info(f"Indexed document: {doc_id}")

    def remove_document(self, doc_id: str) -> bool:
        """Remove document from search index."""
        return self.vector_store.remove_vector(doc_id)

    def clear_index(self) -> None:
        """Clear entire search index."""
        self.vector_store.clear()
        self.logger.info("Search index cleared")


# Factory function for creating search engine
def create_search_engine(vector_dimension: int = 1024) -> SearchEngine:
    """
    Create configured search engine.

    Args:
        vector_dimension: Vector dimension for embeddings

    Returns:
        Configured SearchEngine instance
    """
    vector_store = VectorStore(dimension=vector_dimension)
    engine = SearchEngine(vector_store)

    # Pre-populate with some test data for demonstration
    test_docs = [
        (
            "auth_module",
            "Authentication and authorization functionality",
            {
                "file_path": "auth.py",
                "function_name": "authenticate_user",
                "language": "python",
                "line_number": 42,
            },
        ),
        (
            "api_handler",
            "REST API endpoint handlers and routing",
            {
                "file_path": "api.py",
                "function_name": "create_app",
                "language": "python",
                "line_number": 15,
            },
        ),
        (
            "database_model",
            "Database models and ORM functionality",
            {
                "file_path": "database.py",
                "class_name": "User",
                "language": "python",
                "line_number": 28,
            },
        ),
    ]

    for doc_id, content, metadata in test_docs:
        engine.index_document(doc_id, content, metadata)

    return engine
