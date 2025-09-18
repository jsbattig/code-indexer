"""
API models for CIDX Server endpoints.

Provides Pydantic models for new endpoint requests and responses.
Following CLAUDE.md Foundation #1: No mocks - these represent real data structures.
"""

from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class HealthStatus(str, Enum):
    """System health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ServiceHealthInfo(BaseModel):
    """Health information for individual services."""

    status: HealthStatus
    response_time_ms: int = Field(..., description="Response time in milliseconds")
    error_message: Optional[str] = Field(
        None, description="Error message if service is unhealthy"
    )


class SystemHealthInfo(BaseModel):
    """System resource health information."""

    memory_usage_percent: float = Field(..., description="Memory usage as percentage")
    cpu_usage_percent: float = Field(..., description="CPU usage as percentage")
    active_jobs: int = Field(..., description="Number of active background jobs")
    disk_free_space_gb: float = Field(..., description="Free disk space in GB")


class HealthCheckResponse(BaseModel):
    """Health check endpoint response."""

    status: HealthStatus = Field(..., description="Overall system health status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    services: Dict[str, ServiceHealthInfo] = Field(
        ..., description="Individual service health"
    )
    system: SystemHealthInfo = Field(..., description="System resource information")


class RepositoryFilesInfo(BaseModel):
    """Repository file statistics."""

    total: int = Field(..., description="Total number of files in repository")
    indexed: int = Field(..., description="Number of indexed files")
    by_language: Dict[str, int] = Field(
        ..., description="File counts by programming language"
    )


class RepositoryStorageInfo(BaseModel):
    """Repository storage statistics."""

    repository_size_bytes: int = Field(
        ..., description="Total repository size in bytes"
    )
    index_size_bytes: int = Field(..., description="Index size in bytes")
    embedding_count: int = Field(..., description="Number of embeddings stored")


class RepositoryActivityInfo(BaseModel):
    """Repository activity statistics."""

    created_at: datetime = Field(..., description="Repository creation timestamp")
    last_sync_at: Optional[datetime] = Field(
        None, description="Last synchronization timestamp"
    )
    last_accessed_at: Optional[datetime] = Field(
        None, description="Last access timestamp"
    )
    sync_count: int = Field(default=0, description="Number of successful syncs")


class RepositoryHealthInfo(BaseModel):
    """Repository health assessment."""

    score: float = Field(..., description="Health score between 0.0 and 1.0")
    issues: List[str] = Field(
        default_factory=list, description="List of identified health issues"
    )


class RepositoryStatsResponse(BaseModel):
    """Repository statistics endpoint response."""

    repository_id: str = Field(..., description="Repository identifier")
    files: RepositoryFilesInfo = Field(..., description="File statistics")
    storage: RepositoryStorageInfo = Field(..., description="Storage statistics")
    activity: RepositoryActivityInfo = Field(..., description="Activity statistics")
    health: RepositoryHealthInfo = Field(..., description="Health assessment")


class FileInfo(BaseModel):
    """Individual file information."""

    path: str = Field(..., description="Relative file path within repository")
    size_bytes: int = Field(..., description="File size in bytes")
    modified_at: datetime = Field(..., description="Last modification timestamp")
    language: Optional[str] = Field(None, description="Detected programming language")
    is_indexed: bool = Field(..., description="Whether file is currently indexed")


class PaginationInfo(BaseModel):
    """Pagination metadata."""

    page: int = Field(..., description="Current page number (1-based)")
    limit: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of items")
    has_next: bool = Field(..., description="Whether more pages are available")


class FileListResponse(BaseModel):
    """File listing endpoint response."""

    files: List[FileInfo] = Field(..., description="List of files")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class SemanticSearchRequest(BaseModel):
    """Semantic search request."""

    query: str = Field(
        ..., min_length=1, max_length=1000, description="Search query text"
    )
    limit: int = Field(
        default=10, ge=1, le=100, description="Maximum number of results"
    )
    include_source: bool = Field(
        default=True, description="Whether to include source code in results"
    )


class SearchResultItem(BaseModel):
    """Individual search result."""

    score: float = Field(..., description="Relevance score between 0.0 and 1.0")
    file_path: str = Field(..., description="Path to the file containing the result")
    line_start: int = Field(..., description="Starting line number")
    line_end: int = Field(..., description="Ending line number")
    content: str = Field(..., description="Source code content")
    language: Optional[str] = Field(None, description="Programming language")

    # Universal timestamp fields for staleness detection
    file_last_modified: Optional[float] = Field(
        None,
        description="Unix timestamp when file was last modified (None if stat failed)",
    )
    indexed_timestamp: Optional[float] = Field(
        None, description="Unix timestamp when file was indexed"
    )


class SemanticSearchResponse(BaseModel):
    """Semantic search endpoint response."""

    query: str = Field(..., description="Original search query")
    results: List[SearchResultItem] = Field(..., description="Search results")
    total: int = Field(..., description="Total number of results found")


# File listing query parameters model
class FileListQueryParams(BaseModel):
    """Query parameters for file listing endpoint."""

    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    limit: int = Field(default=50, ge=1, le=500, description="Items per page")
    path_pattern: Optional[str] = Field(None, description="File path pattern filter")
    language: Optional[str] = Field(None, description="Programming language filter")
    sort_by: Optional[str] = Field(
        default="path", description="Sort field: path, size, modified_at"
    )
