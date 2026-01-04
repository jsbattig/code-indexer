"""
Re-indexing REST API Router.

Provides REST endpoints for triggering re-indexing and querying index status
with OAuth authentication and service layer integration.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.auth.user_manager import User

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(prefix="/api/v1/repos/{alias}", tags=["indexing"])


# Request/Response Models


class TriggerReindexRequest(BaseModel):
    """Request model for triggering re-indexing."""

    index_types: List[str] = Field(
        ...,
        description="List of index types to rebuild (semantic, fts, temporal, scip)",
    )
    clear: bool = Field(False, description="Clear existing indexes before rebuilding")


class TriggerReindexResponse(BaseModel):
    """Response model for trigger re-index."""

    success: bool = Field(..., description="Operation success status")
    job_id: str = Field(..., description="Background job ID for tracking")
    status: str = Field(..., description="Initial job status")
    index_types: List[str] = Field(..., description="Index types being rebuilt")
    started_at: str = Field(..., description="Job start time (ISO 8601)")
    estimated_duration_minutes: Optional[int] = Field(
        None, description="Estimated completion time in minutes"
    )


class IndexTypeStatus(BaseModel):
    """Status information for a single index type."""

    exists: bool = Field(..., description="Whether index exists")
    last_updated: Optional[str] = Field(None, description="Last update time (ISO 8601)")
    document_count: int = Field(0, description="Number of indexed documents")
    size_bytes: Optional[int] = Field(None, description="Index size in bytes")


class GetIndexStatusResponse(BaseModel):
    """Response model for index status query."""

    success: bool = Field(..., description="Operation success status")
    repository_alias: str = Field(..., description="Repository alias")
    semantic: IndexTypeStatus = Field(..., description="Semantic index status")
    fts: IndexTypeStatus = Field(..., description="Full-text search index status")
    temporal: IndexTypeStatus = Field(
        ..., description="Temporal (git history) index status"
    )
    scip: IndexTypeStatus = Field(..., description="SCIP (call graph) index status")


# Endpoints


@router.post(
    "/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TriggerReindexResponse,
    responses={
        202: {"description": "Re-indexing job accepted"},
        400: {"description": "Invalid parameters"},
        401: {"description": "Missing or invalid authentication"},
        404: {"description": "Repository not found"},
    },
    summary="Trigger re-indexing",
    description="Trigger a background re-indexing job for specified index types",
)
async def trigger_reindex(
    alias: str, request: TriggerReindexRequest, user: User = Depends(get_current_user)
) -> TriggerReindexResponse:
    """Trigger re-indexing for specified index types."""
    try:
        # Import here to avoid circular dependencies
        from code_indexer.server.services.activated_repo_index_manager import (
            ActivatedRepoIndexManager,
        )

        service = ActivatedRepoIndexManager()
        result = service.trigger_reindex(
            repo_alias=alias,
            index_types=request.index_types,
            clear=request.clear,
            username=user.username,
        )
        return TriggerReindexResponse(**result)
    except FileNotFoundError as e:
        logger.warning(f"Repository not found: {alias}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        logger.warning(f"Invalid request for {alias}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Trigger reindex failed for {alias}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get(
    "/index-status",
    status_code=status.HTTP_200_OK,
    response_model=GetIndexStatusResponse,
    responses={
        200: {"description": "Index status retrieved successfully"},
        401: {"description": "Missing or invalid authentication"},
        404: {"description": "Repository not found"},
    },
    summary="Get index status",
    description="Get the status of all index types for the repository",
)
async def get_index_status(
    alias: str, user: User = Depends(get_current_user)
) -> GetIndexStatusResponse:
    """Get index status for all index types."""
    try:
        # Import here to avoid circular dependencies
        from code_indexer.server.services.activated_repo_index_manager import (
            ActivatedRepoIndexManager,
        )

        service = ActivatedRepoIndexManager()
        result = service.get_index_status(repo_alias=alias, username=user.username)

        # Transform service output to match response model
        # Service returns {"status": "not_indexed"} or {"status": "up_to_date", ...}
        # Model expects {"exists": bool, "last_updated": str, "document_count": int, "size_bytes": int}
        def get_first_valid(*values, default=0):
            """Return first non-None value, or default."""
            for v in values:
                if v is not None:
                    return v
            return default

        def transform_index_status(status_data: Dict[str, Any]) -> IndexTypeStatus:
            """Transform service status to IndexTypeStatus model."""
            exists = status_data.get("status") != "not_indexed"

            # Get last updated timestamp (try different field names)
            last_updated = (
                status_data.get("last_updated")
                or status_data.get("last_indexed")
                or status_data.get("last_generated")
            )

            # Get document count (try different field names, handle zero correctly)
            document_count = get_first_valid(
                status_data.get("document_count"),
                status_data.get("file_count"),
                status_data.get("commit_count"),
                status_data.get("project_count"),
                default=0,
            )

            # Calculate size in bytes (handle zero correctly)
            index_size_mb = status_data.get("index_size_mb")
            size_bytes = (
                int(index_size_mb * 1024 * 1024) if index_size_mb is not None else None
            )

            return IndexTypeStatus(
                exists=exists,
                last_updated=last_updated,
                document_count=document_count,
                size_bytes=size_bytes,
            )

        return GetIndexStatusResponse(
            success=True,
            repository_alias=alias,
            semantic=transform_index_status(result["semantic"]),
            fts=transform_index_status(result["fts"]),
            temporal=transform_index_status(result["temporal"]),
            scip=transform_index_status(result["scip"]),
        )
    except FileNotFoundError as e:
        logger.warning(f"Repository not found: {alias}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Get index status failed for {alias}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get(
    "/temporal-status",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Temporal status retrieved successfully"},
        401: {"description": "Missing or invalid authentication"},
        404: {"description": "Repository not found"},
    },
    summary="Get temporal indexing status",
    description="Get the temporal indexing status (format version, file count, reindex requirement)",
)
async def get_temporal_status(
    alias: str, user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get temporal indexing status for repository.

    Returns:
        {
            "format": "v1"|"v2"|"none",
            "file_count": int,
            "needs_reindex": bool,
            "message": str
        }
    """
    try:
        # Import here to avoid circular dependencies
        from code_indexer.server.services.dashboard_service import DashboardService

        service = DashboardService()
        result = service.get_temporal_index_status(username=user.username, repo_alias=alias)
        return result
    except FileNotFoundError as e:
        logger.warning(f"Repository not found: {alias}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Get temporal status failed for {alias}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )
