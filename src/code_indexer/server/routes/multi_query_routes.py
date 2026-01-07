"""
Multi-Repository Query REST API Routes.

Provides /api/query/multi endpoint for executing searches across multiple
repositories in parallel with proper authentication and error handling.

Implements AC1: REST endpoint for multi-repository search.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, List, Any

from ..auth.dependencies import get_current_user
from ..auth.user_manager import User
from ..multi import (
    MultiSearchService,
    MultiSearchConfig,
    MultiSearchRequest,
    MultiSearchResponse,
)

logger = logging.getLogger(__name__)


async def _apply_multi_truncation(
    grouped_results: Dict[str, List[Dict[str, Any]]], search_type: str
) -> Dict[str, List[Dict[str, Any]]]:
    """Apply payload truncation to multi-repo grouped search results (Story #683).

    Args:
        grouped_results: Dict mapping repo_id to list of result dicts
        search_type: Search type ('semantic', 'fts', 'temporal')

    Returns:
        Modified grouped_results with truncation applied to each result
    """
    from ..mcp.handlers import (
        _apply_payload_truncation,
        _apply_fts_payload_truncation,
        _apply_temporal_payload_truncation,
    )

    for repo_id, results in grouped_results.items():
        if search_type == "fts":
            grouped_results[repo_id] = await _apply_fts_payload_truncation(results)
        elif search_type == "temporal":
            grouped_results[repo_id] = await _apply_temporal_payload_truncation(results)
        else:
            # Default to semantic truncation (handles both content and code_snippet)
            grouped_results[repo_id] = await _apply_payload_truncation(results)

    return grouped_results


# Create router with /api/query prefix
router = APIRouter(prefix="/api/query", tags=["multi-query"])

# Initialize multi-search service with default configuration
_multi_search_service: Optional[MultiSearchService] = None


def get_multi_search_service() -> MultiSearchService:
    """
    Get or create MultiSearchService instance.

    Returns:
        MultiSearchService instance
    """
    global _multi_search_service
    if _multi_search_service is None:
        config = MultiSearchConfig.from_env()
        _multi_search_service = MultiSearchService(config)
    return _multi_search_service


@router.post("/multi", response_model=MultiSearchResponse)
async def multi_repository_query(
    request: MultiSearchRequest,
    user: User = Depends(get_current_user),
) -> MultiSearchResponse:
    """
    Execute search across multiple repositories (AC1: REST Endpoint).

    Performs parallel search across specified repositories with:
    - Authentication enforcement (JWT token required)
    - Request validation (Pydantic models)
    - Timeout handling (30s default per repo)
    - Partial failure support (some repos succeed, others fail)
    - Result aggregation with repository attribution

    **Authentication**: Requires valid JWT token in Authorization header.

    **Request Body**:
    ```json
    {
        "repositories": ["repo1", "repo2"],
        "query": "authentication logic",
        "search_type": "semantic",
        "limit": 10,
        "min_score": 0.7,
        "language": "python",
        "path_filter": "*/src/*"
    }
    ```

    **Response Structure**:
    ```json
    {
        "results": {
            "repo1": [
                {
                    "file_path": "auth.py",
                    "line_start": 10,
                    "line_end": 20,
                    "score": 0.9,
                    "content": "def authenticate():",
                    "language": "python",
                    "repository": "repo1"
                }
            ],
            "repo2": [...]
        },
        "metadata": {
            "total_results": 15,
            "total_repos_searched": 2,
            "execution_time_ms": 250
        },
        "errors": {
            "repo3": "Query timeout after 30 seconds. Recommendations: ..."
        }
    }
    ```

    **Search Types**:
    - `semantic`: Vector similarity search (uses embeddings)
    - `fts`: Full-text search (Tantivy index)
    - `regex`: Regular expression search (subprocess isolation)
    - `temporal`: Git history search

    **Threading Strategy**:
    - Semantic/FTS/Temporal: ThreadPoolExecutor (max 10 workers)
    - Regex: Subprocess isolation (ReDoS protection)

    **Timeout Behavior**:
    - Each repository has 30s timeout (configurable via CIDX_MULTI_QUERY_TIMEOUT env var)
    - Timed out repos return error with actionable recommendations
    - Successful repos return results even if others time out

    **Error Handling**:
    - Repository not found → error in `errors` field, other repos succeed
    - Invalid query → 422 Unprocessable Entity
    - Authentication failure → 401 Unauthorized
    - Unexpected error → 500 Internal Server Error

    Args:
        request: Multi-search request with repositories, query, and filters
        user: Authenticated user (injected by dependency)

    Returns:
        MultiSearchResponse with results grouped by repository, metadata, and errors

    Raises:
        HTTPException: 401 if authentication fails
        HTTPException: 422 if request validation fails
        HTTPException: 500 if unexpected error occurs
    """
    try:
        # Log request
        logger.info(
            f"Multi-repo search request from user {user.username}: "
            f"{len(request.repositories)} repos, type={request.search_type}"
        )

        # Get service instance
        service = get_multi_search_service()

        # Execute search
        response = await service.search(request)

        # Story #683: Apply payload truncation to results
        response.results = await _apply_multi_truncation(
            response.results, request.search_type
        )

        # Log response summary
        logger.info(
            f"Multi-repo search completed: {response.metadata.total_results} results "
            f"from {response.metadata.total_repos_searched} repos "
            f"in {response.metadata.execution_time_ms}ms"
        )

        return response

    except ValueError as e:
        # Validation error from service
        logger.error(f"Multi-repo search validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected error
        logger.error(f"Multi-repo search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Multi-repository search failed: {str(e)}"
        )


# Cleanup function for service shutdown
def shutdown_multi_search_service():
    """Shutdown multi-search service and clean up resources."""
    global _multi_search_service
    if _multi_search_service:
        _multi_search_service.shutdown()
        _multi_search_service = None
        logger.info("Multi-search service shutdown complete")
