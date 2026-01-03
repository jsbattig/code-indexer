"""
Admin API routes for CIDX server administration.

Provides REST API endpoints for:
- Log viewing and querying (AC3: /admin/api/logs)
- Log export (AC4: /admin/api/logs/export)
"""

from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.services.log_aggregator_service import LogAggregatorService
from code_indexer.server.services.log_export_formatter import LogExportFormatter


# Router with /admin/api prefix (set by app.include_router)
router = APIRouter()


class PaginationMetadata(BaseModel):
    """Pagination metadata for log query responses."""

    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of logs per page")
    total_count: int = Field(..., description="Total number of logs matching query")
    total_pages: int = Field(..., description="Total number of pages")


class LogEntry(BaseModel):
    """Log entry model for API responses."""

    timestamp: str = Field(..., description="ISO 8601 timestamp")
    level: str = Field(..., description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    message: str = Field(..., description="Log message")
    source: str = Field(..., description="Logger name/source")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for request tracking")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class LogsResponse(BaseModel):
    """Response model for /admin/api/logs endpoint."""

    logs: list[LogEntry] = Field(..., description="List of log entries")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")


def _require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require admin role.

    Args:
        user: Current authenticated user

    Returns:
        User if admin

    Raises:
        HTTPException: 403 if user is not admin
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin role required"
        )
    return user


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    sort_order: Literal["asc", "desc"] = "desc",
    search: Optional[str] = None,
    level: Optional[str] = None,
    user: User = Depends(_require_admin),
) -> LogsResponse:
    """
    Get logs with pagination and filtering (AC3, Story #665 AC4).

    Admin-only endpoint for viewing server logs with search and level filtering.

    Args:
        request: FastAPI request object (provides app.state.log_db_path)
        page: Page number (1-indexed, default: 1)
        page_size: Logs per page (default: 50)
        sort_order: Sort order by timestamp (default: desc = newest first)
        search: Text search across message and correlation_id (optional, case-insensitive)
        level: Filter by log level(s), comma-separated for multiple (e.g., "ERROR,WARNING")
        user: Authenticated admin user

    Returns:
        LogsResponse with logs array and pagination metadata

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    # Get log database path from app state
    log_db_path = request.app.state.log_db_path

    # Create LogAggregatorService instance
    service = LogAggregatorService(log_db_path)

    # Parse level parameter (comma-separated to list)
    levels = None
    if level:
        levels = [lv.strip() for lv in level.split(",") if lv.strip()]

    # Query logs
    result = service.query(
        page=page,
        page_size=page_size,
        sort_order=sort_order,
        search=search,
        levels=levels,
    )

    # Convert to API response format
    log_entries = [
        LogEntry(
            timestamp=log["timestamp"],
            level=log["level"],
            message=log["message"],
            source=log["source"],
            correlation_id=log.get("correlation_id"),
            metadata=log.get("metadata", {}),
        )
        for log in result["logs"]
    ]

    response = LogsResponse(
        logs=log_entries,
        pagination=PaginationMetadata(
            page=result["pagination"]["page"],
            page_size=result["pagination"]["page_size"],
            total_count=result["pagination"]["total"],
            total_pages=result["pagination"]["total_pages"],
        ),
    )

    return response


@router.get("/logs/export")
async def export_logs(
    request: Request,
    format: Literal["json", "csv"] = "json",
    search: Optional[str] = None,
    level: Optional[str] = None,
    correlation_id: Optional[str] = None,
    user: User = Depends(_require_admin),
) -> Response:
    """
    Export logs to file in JSON or CSV format (Story #667 AC4).

    Admin-only endpoint for exporting server logs with search and level filtering.

    Args:
        request: FastAPI request object (provides app.state.log_db_path)
        format: Export format - "json" or "csv" (default: json)
        search: Text search across message and correlation_id (optional, case-insensitive)
        level: Filter by log level(s), comma-separated for multiple (e.g., "ERROR,WARNING")
        correlation_id: Filter by correlation ID (optional)
        user: Authenticated admin user

    Returns:
        Response with file content, appropriate Content-Type, and Content-Disposition headers

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    # Get log database path from app state
    log_db_path = request.app.state.log_db_path

    # Create LogAggregatorService instance
    service = LogAggregatorService(log_db_path)

    # Parse level parameter (comma-separated to list)
    levels = None
    if level:
        levels = [lv.strip() for lv in level.split(",") if lv.strip()]

    # Query all logs (no pagination for export)
    logs = service.query_all(
        search=search,
        levels=levels,
        correlation_id=correlation_id,
    )

    # Format output based on requested format
    formatter = LogExportFormatter()

    if format == "json":
        # JSON export with metadata
        filters = {
            "search": search,
            "level": level,
            "correlation_id": correlation_id,
        }
        content = formatter.to_json(logs, filters)
        media_type = "application/json"
    else:
        # CSV export
        content = formatter.to_csv(logs)
        media_type = "text/csv"

    # Generate filename with timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"logs_{timestamp}.{format}"

    # Return response with file download headers
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
