"""
SCIP Multi-Repository Intelligence REST API Routes (Story #677).

Provides endpoints for SCIP operations across multiple repositories:
- /api/scip/multi/definition - Symbol definition lookup (AC1)
- /api/scip/multi/references - Symbol references lookup (AC2)
- /api/scip/multi/dependencies - Dependency analysis (AC3)
- /api/scip/multi/dependents - Dependents analysis (AC4)
- /api/scip/multi/callchain - Call chain tracing (AC5)

All endpoints require JWT authentication and support:
- Parallel execution across repositories
- Timeout enforcement (30s default per repo) - AC7
- Partial failure handling - AC8
- Result aggregation with repository attribution - AC6
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, List, Any

from ..auth.dependencies import get_current_user
from ..auth.user_manager import User
from ..multi.scip_models import SCIPMultiRequest, SCIPMultiResponse, SCIPResult
from ..multi.scip_multi_service import SCIPMultiService

logger = logging.getLogger(__name__)

# Create router with /api/scip/multi prefix
router = APIRouter(prefix="/api/scip/multi", tags=["scip-multi"])

# Initialize SCIP multi-service
_scip_multi_service: Optional[SCIPMultiService] = None


def get_scip_multi_service() -> SCIPMultiService:
    """
    Get or create SCIPMultiService instance.

    Returns:
        SCIPMultiService instance
    """
    global _scip_multi_service
    if _scip_multi_service is None:
        _scip_multi_service = SCIPMultiService()
    return _scip_multi_service


async def _apply_multi_scip_truncation(
    response: SCIPMultiResponse,
) -> Dict[str, Any]:
    """Apply SCIP payload truncation to multi-repo response results (Story #685).

    Converts SCIPMultiResponse to dict and applies truncation to each
    repository's results list, handling the context field truncation.

    Args:
        response: SCIPMultiResponse with results grouped by repository

    Returns:
        Dict representation with truncated context fields
    """
    # Lazy import to avoid circular dependency with handlers.py
    from ..mcp.handlers import _apply_scip_payload_truncation

    # Convert response to dict for modification
    response_dict = response.model_dump()

    # Apply truncation to each repository's results
    for repo_id, results_list in response_dict["results"].items():
        if results_list:
            # Apply truncation (converts SCIPResult dicts with context field)
            truncated_results = await _apply_scip_payload_truncation(results_list)
            response_dict["results"][repo_id] = truncated_results

    return response_dict


@router.post("/definition", response_model=SCIPMultiResponse)
async def multi_repository_definition(
    request: SCIPMultiRequest,
    user: User = Depends(get_current_user),
) -> SCIPMultiResponse:
    """
    Find symbol definition across multiple repositories (AC1: Multi-Repository Definition Lookup).

    Performs parallel definition lookup across specified repositories with:
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
        "symbol": "com.example.User",
        "timeout_seconds": 30
    }
    ```

    **Response Structure**:
    ```json
    {
        "results": {
            "repo1": [
                {
                    "symbol": "com.example.User",
                    "file_path": "src/User.java",
                    "line": 10,
                    "repository": "repo1"
                }
            ],
            "repo2": []
        },
        "metadata": {
            "total_results": 1,
            "repos_searched": 2,
            "execution_time_ms": 150
        },
        "errors": {}
    }
    ```

    **Timeout Behavior** (AC7):
    - Each repository has 30s timeout (configurable via timeout_seconds)
    - Timed out repos return error in `errors` field
    - Successful repos return results even if others time out

    **SCIP Index Availability** (AC8):
    - Repos without SCIP index return error in `errors` field
    - Repos with SCIP index return results
    - Empty results when symbol not found (no error)

    **Error Handling**:
    - Repository not found → error in `errors` field, other repos succeed
    - No SCIP index → error in `errors` field, other repos succeed
    - Invalid symbol → 422 Unprocessable Entity
    - Authentication failure → 401 Unauthorized
    - Unexpected error → 500 Internal Server Error

    Args:
        request: SCIP multi-request with repositories and symbol
        user: Authenticated user (injected by dependency)

    Returns:
        SCIPMultiResponse with results grouped by repository, metadata, and errors

    Raises:
        HTTPException: 401 if authentication fails
        HTTPException: 422 if request validation fails
        HTTPException: 500 if unexpected error occurs
    """
    try:
        # Log request
        logger.info(
            f"SCIP multi-definition request from user {user.username}: "
            f"{len(request.repositories)} repos, symbol={request.symbol}"
        )

        # Get service instance
        service = get_scip_multi_service()

        # Execute definition lookup
        response = await service.definition(request)

        # Log response summary
        logger.info(
            f"SCIP multi-definition completed: {response.metadata.total_results} results "
            f"from {response.metadata.repos_searched} repos "
            f"in {response.metadata.execution_time_ms}ms"
        )

        # Story #685: Apply SCIP payload truncation to context fields
        return await _apply_multi_scip_truncation(response)

    except ValueError as e:
        # Validation error from service
        logger.error(f"SCIP multi-definition validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected error
        logger.error(f"SCIP multi-definition failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"SCIP multi-definition failed: {str(e)}"
        )


@router.post("/references", response_model=SCIPMultiResponse)
async def multi_repository_references(
    request: SCIPMultiRequest,
    user: User = Depends(get_current_user),
) -> SCIPMultiResponse:
    """
    Find symbol references across multiple repositories (AC2: Multi-Repository Reference Lookup).

    Performs parallel references lookup across specified repositories with:
    - Authentication enforcement (JWT token required)
    - Request validation (Pydantic models)
    - Timeout handling (30s default per repo)
    - Partial failure support (some repos succeed, others fail)
    - Result aggregation with repository attribution
    - Limit parameter to control results per repository

    **Authentication**: Requires valid JWT token in Authorization header.

    **Request Body**:
    ```json
    {
        "repositories": ["repo1", "repo2"],
        "symbol": "com.example.User",
        "limit": 100,
        "timeout_seconds": 30
    }
    ```

    Args:
        request: SCIP multi-request with repositories, symbol, and optional limit
        user: Authenticated user (injected by dependency)

    Returns:
        SCIPMultiResponse with references grouped by repository, metadata, and errors

    Raises:
        HTTPException: 401 if authentication fails
        HTTPException: 422 if request validation fails
        HTTPException: 500 if unexpected error occurs
    """
    try:
        # Log request
        logger.info(
            f"SCIP multi-references request from user {user.username}: "
            f"{len(request.repositories)} repos, symbol={request.symbol}, limit={request.limit}"
        )

        # Get service instance
        service = get_scip_multi_service()

        # Execute references lookup
        response = await service.references(request)

        # Log response summary
        logger.info(
            f"SCIP multi-references completed: {response.metadata.total_results} results "
            f"from {response.metadata.repos_searched} repos "
            f"in {response.metadata.execution_time_ms}ms"
        )

        # Story #685: Apply SCIP payload truncation to context fields
        return await _apply_multi_scip_truncation(response)

    except ValueError as e:
        # Validation error from service
        logger.error(f"SCIP multi-references validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected error
        logger.error(f"SCIP multi-references failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"SCIP multi-references failed: {str(e)}"
        )


@router.post("/dependencies", response_model=SCIPMultiResponse)
async def multi_repository_dependencies(
    request: SCIPMultiRequest,
    user: User = Depends(get_current_user),
) -> SCIPMultiResponse:
    """
    Analyze symbol dependencies across multiple repositories (AC3: Multi-Repository Dependency Analysis).

    Performs parallel dependency analysis across specified repositories with:
    - Authentication enforcement (JWT token required)
    - Request validation (Pydantic models)
    - Timeout handling (30s default per repo)
    - Partial failure support (some repos succeed, others fail)
    - Result aggregation with repository attribution
    - Max depth parameter to control traversal depth

    **Authentication**: Requires valid JWT token in Authorization header.

    **Request Body**:
    ```json
    {
        "repositories": ["repo1", "repo2"],
        "symbol": "com.example.Service",
        "max_depth": 3,
        "timeout_seconds": 30
    }
    ```

    Args:
        request: SCIP multi-request with repositories, symbol, and optional max_depth
        user: Authenticated user (injected by dependency)

    Returns:
        SCIPMultiResponse with dependencies grouped by repository, metadata, and errors

    Raises:
        HTTPException: 401 if authentication fails
        HTTPException: 422 if request validation fails
        HTTPException: 500 if unexpected error occurs
    """
    try:
        # Log request
        logger.info(
            f"SCIP multi-dependencies request from user {user.username}: "
            f"{len(request.repositories)} repos, symbol={request.symbol}, max_depth={request.max_depth}"
        )

        # Get service instance
        service = get_scip_multi_service()

        # Execute dependencies analysis
        response = await service.dependencies(request)

        # Log response summary
        logger.info(
            f"SCIP multi-dependencies completed: {response.metadata.total_results} results "
            f"from {response.metadata.repos_searched} repos "
            f"in {response.metadata.execution_time_ms}ms"
        )

        # Story #685: Apply SCIP payload truncation to context fields
        return await _apply_multi_scip_truncation(response)

    except ValueError as e:
        # Validation error from service
        logger.error(f"SCIP multi-dependencies validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected error
        logger.error(f"SCIP multi-dependencies failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"SCIP multi-dependencies failed: {str(e)}"
        )


@router.post("/dependents", response_model=SCIPMultiResponse)
async def multi_repository_dependents(
    request: SCIPMultiRequest,
    user: User = Depends(get_current_user),
) -> SCIPMultiResponse:
    """
    Analyze symbol dependents across multiple repositories (AC4: Multi-Repository Dependents Analysis).

    Performs parallel dependents analysis across specified repositories with:
    - Authentication enforcement (JWT token required)
    - Request validation (Pydantic models)
    - Timeout handling (30s default per repo)
    - Partial failure support (some repos succeed, others fail)
    - Result aggregation with repository attribution
    - Max depth parameter to control traversal depth

    **Authentication**: Requires valid JWT token in Authorization header.

    **Request Body**:
    ```json
    {
        "repositories": ["repo1", "repo2"],
        "symbol": "com.example.Database",
        "max_depth": 3,
        "timeout_seconds": 30
    }
    ```

    Args:
        request: SCIP multi-request with repositories, symbol, and optional max_depth
        user: Authenticated user (injected by dependency)

    Returns:
        SCIPMultiResponse with dependents grouped by repository, metadata, and errors

    Raises:
        HTTPException: 401 if authentication fails
        HTTPException: 422 if request validation fails
        HTTPException: 500 if unexpected error occurs
    """
    try:
        # Log request
        logger.info(
            f"SCIP multi-dependents request from user {user.username}: "
            f"{len(request.repositories)} repos, symbol={request.symbol}, max_depth={request.max_depth}"
        )

        # Get service instance
        service = get_scip_multi_service()

        # Execute dependents analysis
        response = await service.dependents(request)

        # Log response summary
        logger.info(
            f"SCIP multi-dependents completed: {response.metadata.total_results} results "
            f"from {response.metadata.repos_searched} repos "
            f"in {response.metadata.execution_time_ms}ms"
        )

        # Story #685: Apply SCIP payload truncation to context fields
        return await _apply_multi_scip_truncation(response)

    except ValueError as e:
        # Validation error from service
        logger.error(f"SCIP multi-dependents validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected error
        logger.error(f"SCIP multi-dependents failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"SCIP multi-dependents failed: {str(e)}"
        )


@router.post("/callchain", response_model=SCIPMultiResponse)
async def multi_repository_callchain(
    request: SCIPMultiRequest,
    user: User = Depends(get_current_user),
) -> SCIPMultiResponse:
    """
    Trace call chains across multiple repositories (AC5: Per-Repository Call Chain Tracing).

    Performs parallel call chain tracing across specified repositories with:
    - Authentication enforcement (JWT token required)
    - Request validation (Pydantic models)
    - Timeout handling (30s default per repo)
    - Partial failure support (some repos succeed, others fail)
    - Result aggregation with repository attribution
    - Per-repository call chain tracing (no cross-repo stitching)

    **Authentication**: Requires valid JWT token in Authorization header.

    **Request Body**:
    ```json
    {
        "repositories": ["repo1", "repo2"],
        "from_symbol": "com.example.main",
        "to_symbol": "com.example.saveData",
        "timeout_seconds": 30
    }
    ```

    **Note**: Call chains are traced within each repository independently.
    No cross-repository call chain stitching is performed (AC5).

    Args:
        request: SCIP multi-request with repositories, from_symbol, and to_symbol
        user: Authenticated user (injected by dependency)

    Returns:
        SCIPMultiResponse with call chains grouped by repository, metadata, and errors

    Raises:
        HTTPException: 401 if authentication fails
        HTTPException: 422 if request validation fails
        HTTPException: 500 if unexpected error occurs
    """
    try:
        # Log request
        logger.info(
            f"SCIP multi-callchain request from user {user.username}: "
            f"{len(request.repositories)} repos, from={request.from_symbol}, to={request.to_symbol}"
        )

        # Get service instance
        service = get_scip_multi_service()

        # Execute callchain tracing
        response = await service.callchain(request)

        # Log response summary
        logger.info(
            f"SCIP multi-callchain completed: {response.metadata.total_results} results "
            f"from {response.metadata.repos_searched} repos "
            f"in {response.metadata.execution_time_ms}ms"
        )

        return response

    except ValueError as e:
        # Validation error from service
        logger.error(f"SCIP multi-callchain validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected error
        logger.error(f"SCIP multi-callchain failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"SCIP multi-callchain failed: {str(e)}"
        )
