"""Cache retrieval REST API Router.

Story #679: S1 - Semantic Search with Payload Control (Foundation)
AC4: REST Cache Retrieval API

Provides GET /cache/{handle} endpoint for retrieving cached content with pagination.
"""

import logging
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from typing import Optional

from code_indexer.server.cache.payload_cache import CacheNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])


class CacheRetrievalResponse(BaseModel):
    """Response model for cache retrieval."""

    content: str = Field(..., description="Retrieved content for requested page")
    page: int = Field(..., description="Current page number (0-indexed)")
    total_pages: int = Field(..., description="Total number of pages available")
    has_more: bool = Field(..., description="Whether more pages are available")


class CacheErrorResponse(BaseModel):
    """Error response for cache retrieval failures."""

    error: str = Field(..., description="Error type (cache_expired)")
    message: str = Field(..., description="Human-readable error message")
    handle: str = Field(..., description="The requested cache handle")


@router.get(
    "/{handle}",
    response_model=CacheRetrievalResponse,
    responses={
        200: {"description": "Cache content retrieved successfully"},
        404: {
            "description": "Cache handle not found or expired",
            "model": CacheErrorResponse,
        },
    },
    summary="Retrieve cached content",
    description="Retrieve cached content by handle with pagination support",
)
async def get_cached_content(
    request: Request,
    handle: str,
    page: int = Query(default=0, ge=0, description="Page number (0-indexed)"),
) -> CacheRetrievalResponse:
    """Retrieve cached content by handle with pagination.

    Args:
        request: FastAPI request object
        handle: UUID4 cache handle
        page: Page number (0-indexed, default 0)

    Returns:
        CacheRetrievalResponse with content and pagination info

    Raises:
        HTTPException 404: If handle not found or expired
    """
    payload_cache = getattr(request.app.state, "payload_cache", None)

    if payload_cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache service not available",
        )

    try:
        result = await payload_cache.retrieve(handle, page=page)
        return CacheRetrievalResponse(
            content=result.content,
            page=result.page,
            total_pages=result.total_pages,
            has_more=result.has_more,
        )
    except CacheNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "cache_expired",
                "message": "Cache handle has expired or does not exist",
                "handle": handle,
            },
        )
