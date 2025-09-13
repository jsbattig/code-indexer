"""
Semantic Search Service.

Provides real semantic search operations following CLAUDE.md Foundation #1: No mocks.
All operations use real vector embeddings and Qdrant searches.
"""

import os
from pathlib import Path
from typing import List, Optional
import logging

from ..models.api_models import (
    SemanticSearchRequest,
    SemanticSearchResponse,
    SearchResultItem,
)
from ...config import ConfigManager
from ...services.qdrant import QdrantClient
from ...services.embedding_factory import EmbeddingProviderFactory

logger = logging.getLogger(__name__)

# Language detection for search results
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".vue": "vue",
    ".jsx": "jsx",
    ".tsx": "tsx",
}


class SemanticSearchService:
    """Service for semantic code search."""

    def __init__(self):
        """Initialize the semantic search service with real dependencies."""
        # CLAUDE.md Foundation #1: Direct instantiation of real services only
        # NO dependency injection parameters that enable mocking
        try:
            config_manager = ConfigManager.create_with_backtrack()
            self.config = config_manager.get_config()

            # Real QdrantClient integration - not injectable, not mockable
            self.qdrant_client = QdrantClient(
                config=self.config.qdrant, project_root=Path.cwd()
            )

            # Real embedding service - not injectable, not mockable
            self.embedding_service = EmbeddingProviderFactory.create(config=self.config)

        except Exception as e:
            logger.error(f"Failed to initialize real dependencies: {e}")
            raise RuntimeError(f"Cannot initialize semantic search service: {e}")

    def search_repository(
        self, repo_id: str, search_request: SemanticSearchRequest
    ) -> SemanticSearchResponse:
        """
        Perform semantic search in repository.

        Args:
            repo_id: Repository identifier
            search_request: Search request parameters

        Returns:
            Semantic search response with ranked results

        Raises:
            FileNotFoundError: If repository doesn't exist
            ValueError: If search request is invalid
        """
        repo_path = self._get_repository_path(repo_id)

        if not os.path.exists(repo_path):
            raise FileNotFoundError(f"Repository {repo_id} not found")

        # CLAUDE.md Foundation #1: Real semantic search with vector embeddings
        # 1. Generate embeddings for the query
        # 2. Search Qdrant vector database
        # 3. Rank results by semantic similarity

        search_results = self._perform_semantic_search(
            repo_id,
            search_request.query,
            search_request.limit,
            search_request.include_source,
        )

        return SemanticSearchResponse(
            query=search_request.query,
            results=search_results,
            total=len(search_results),
        )

    def _perform_semantic_search(
        self, repo_id: str, query: str, limit: int, include_source: bool
    ) -> List[SearchResultItem]:
        """
        Perform real semantic search using vector embeddings.

        CLAUDE.md Foundation #1: Real vector search, no text search fallbacks.

        Args:
            repo_id: Repository identifier
            query: Search query
            limit: Maximum number of results
            include_source: Whether to include source code in results

        Returns:
            List of search results ranked by semantic similarity

        Raises:
            RuntimeError: If embedding generation or Qdrant search fails
        """
        try:
            # Generate real embedding for query
            query_embedding = self.embedding_service.get_embedding(query)

            # Search Qdrant with vector similarity
            collection_name = f"repo_{repo_id}"

            # Real vector search in Qdrant
            search_results = self.qdrant_client.search(
                query_vector=query_embedding,
                limit=limit,
                collection_name=collection_name,
            )

            # Format results for response
            formatted_results = []
            for result in search_results:
                payload = result.get("payload", {})
                score = result.get("score", 0.0)

                # Extract source code if requested
                source_content = None
                if include_source and "content" in payload:
                    source_content = payload["content"]

                search_item = SearchResultItem(
                    file_path=payload.get("path", ""),
                    start_line=payload.get("start_line", 0),
                    end_line=payload.get("end_line", 0),
                    relevance_score=score,
                    snippet=payload.get("snippet", ""),
                    language=self._detect_language_from_path(payload.get("path", "")),
                    source_code=source_content,
                )
                formatted_results.append(search_item)

            return formatted_results

        except Exception as e:
            logger.error(f"Semantic search failed for repo {repo_id}: {e}")
            raise RuntimeError(f"Semantic search failed: {e}")

    def _detect_language_from_path(self, file_path: str) -> Optional[str]:
        """
        Detect programming language from file extension.

        Args:
            file_path: Path to file

        Returns:
            Programming language name or None if unknown
        """
        if not file_path:
            return None

        path = Path(file_path)
        extension = path.suffix.lower()
        return LANGUAGE_EXTENSIONS.get(extension)

    def _get_repository_path(self, repo_id: str) -> str:
        """
        Get file system path for repository from real database.

        CLAUDE.md Foundation #1: Real database lookup, no placeholders.

        Args:
            repo_id: Repository identifier

        Returns:
            Real file system path to repository

        Raises:
            RuntimeError: If database lookup fails
            FileNotFoundError: If repository not found
        """
        try:
            # Use existing repository manager patterns from the codebase
            from ..repositories.golden_repo_manager import GoldenRepoManager

            repo_manager = GoldenRepoManager()

            # Search for repository by alias (repo_id)
            golden_repos = repo_manager.list_golden_repos()
            for repo_data in golden_repos:
                if repo_data.get("alias") == repo_id:
                    clone_path = repo_data.get("clone_path")
                    if clone_path and Path(clone_path).exists():
                        return clone_path
                    else:
                        raise FileNotFoundError(
                            f"Repository path {clone_path} does not exist"
                        )

            # Repository not found
            raise FileNotFoundError(
                f"Repository {repo_id} not found in golden repositories"
            )

        except Exception as e:
            logger.error(f"Failed to get repository path for {repo_id}: {e}")
            if isinstance(e, FileNotFoundError):
                raise
            raise RuntimeError(f"Unable to access repository {repo_id}: {e}")


# Global service instance
search_service = SemanticSearchService()
