"""
Semantic Search Service.

Provides real semantic search operations following CLAUDE.md Foundation #1: No mocks.
All operations use real vector embeddings and vector store searches.
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
from ...backends.backend_factory import BackendFactory
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
    """Service for semantic code search with repository-specific configuration."""

    def __init__(self):
        """Initialize the semantic search service."""
        # CLAUDE.md Foundation #1: Direct instantiation of real services only
        # NO dependency injection parameters that enable mocking

        # Note: We don't load any configuration here because each search operation
        # needs repository-specific configuration (different collection names)
        pass

    def search_repository(
        self, repo_id: str, search_request: SemanticSearchRequest
    ) -> SemanticSearchResponse:
        """
        Perform semantic search in repository using repository-specific configuration.

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

        return self.search_repository_path(repo_path, search_request)

    def search_repository_path(
        self, repo_path: str, search_request: SemanticSearchRequest
    ) -> SemanticSearchResponse:
        """
        Perform semantic search in repository using direct path.

        Args:
            repo_path: Direct path to repository directory
            search_request: Search request parameters

        Returns:
            Semantic search response with ranked results

        Raises:
            FileNotFoundError: If repository path doesn't exist
            ValueError: If search request is invalid
        """
        if not os.path.exists(repo_path):
            raise FileNotFoundError(f"Repository path {repo_path} not found")

        # CLAUDE.md Foundation #1: Real semantic search with vector embeddings
        # 1. Load repository-specific configuration
        # 2. Generate embeddings for the query
        # 3. Search vector store with correct collection name
        # 4. Rank results by semantic similarity

        search_results = self._perform_semantic_search(
            repo_path,
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
        self, repo_path: str, query: str, limit: int, include_source: bool
    ) -> List[SearchResultItem]:
        """
        Perform real semantic search using repository-specific configuration.

        CLAUDE.md Foundation #1: Real vector search, no text search fallbacks.
        Uses BackendFactory for vector storage.

        Args:
            repo_path: Path to repository directory
            query: Search query
            limit: Maximum number of results
            include_source: Whether to include source code in results

        Returns:
            List of search results ranked by semantic similarity

        Raises:
            RuntimeError: If embedding generation or vector search fails
        """
        try:
            # Load repository-specific configuration
            config_manager = ConfigManager.create_with_backtrack(Path(repo_path))
            config = config_manager.get_config()

            logger.info(f"Loaded repository config from {repo_path}")

            # Create backend using BackendFactory (Story #526: pass server cache)
            # Import here to avoid circular dependency
            from ..app import _server_hnsw_cache

            backend = BackendFactory.create(
                config=config,
                project_root=Path(repo_path),
                hnsw_cache=_server_hnsw_cache,
            )
            vector_store_client = backend.get_vector_store_client()

            logger.info(f"Using backend: {type(backend).__name__}")

            # Create repository-specific embedding service
            embedding_service = EmbeddingProviderFactory.create(config=config)

            # Resolve correct collection name based on repository configuration
            collection_name = vector_store_client.resolve_collection_name(
                config, embedding_service
            )

            logger.info(f"Using collection: {collection_name}")

            # Real vector search - different parameter patterns for different backends
            # FilesystemVectorStore: parallel execution (query + embedding_provider)
            # Backend: sequential execution (pre-computed query_vector)
            from ...storage.filesystem_vector_store import FilesystemVectorStore

            if isinstance(vector_store_client, FilesystemVectorStore):
                # FilesystemVectorStore: parallel execution with query string and provider
                # Embedding generation happens in parallel with index loading
                search_results, _ = vector_store_client.search(
                    query=query,
                    embedding_provider=embedding_service,
                    collection_name=collection_name,
                    limit=limit,
                    return_timing=True,
                )
            else:
                # Backend: sequential execution with pre-computed embedding
                query_embedding = embedding_service.get_embedding(query)
                search_results = vector_store_client.search(
                    query_vector=query_embedding,
                    limit=limit,
                    collection_name=collection_name,
                )

            logger.info(f"Found {len(search_results)} results")

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
                    line_start=payload.get("line_start", 0),
                    line_end=payload.get("line_end", 0),
                    score=score,
                    content=source_content or payload.get("snippet", ""),
                    language=self._detect_language_from_path(payload.get("path", "")),
                )
                formatted_results.append(search_item)

            return formatted_results

        except Exception as e:
            logger.error(f"Semantic search failed for repo {repo_path}: {e}")
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
            from pathlib import Path as PathLib

            home_dir = PathLib.home()
            data_dir = str(home_dir / ".cidx-server" / "data")
            repo_manager = GoldenRepoManager(data_dir=data_dir)

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
