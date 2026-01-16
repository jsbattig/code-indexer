"""
Request and response models for multi-repository search.

Provides Pydantic models for API request validation and response structure.
"""

from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, field_validator


class MultiSearchRequest(BaseModel):
    """
    Request model for multi-repository search.

    Attributes:
        repositories: List of repository identifiers to search
        query: Search query string
        search_type: Type of search (semantic, fts, regex, temporal)
        limit: Maximum results per repository (default: 10)
        min_score: Minimum similarity score (optional, for semantic/FTS)
        language: Filter by programming language (optional)
        path_filter: Filter by file path pattern (optional)
    """

    repositories: List[str] = Field(
        ...,
        description="List of repository identifiers to search",
        min_length=1,
    )
    query: str = Field(..., description="Search query string")
    search_type: Literal["semantic", "fts", "regex", "temporal"] = Field(
        ..., description="Type of search to perform"
    )
    limit: int = Field(10, description="Maximum results per repository", ge=1)
    min_score: Optional[float] = Field(
        None, description="Minimum similarity score (semantic/FTS)", ge=0.0, le=1.0
    )
    language: Optional[str] = Field(None, description="Filter by programming language")
    path_filter: Optional[str] = Field(None, description="Filter by file path pattern")

    @field_validator("repositories")
    @classmethod
    def validate_repositories(cls, v: List[str]) -> List[str]:
        """Ensure at least one repository is specified."""
        if not v:
            raise ValueError("Must specify at least one repository")
        return v


class MultiSearchMetadata(BaseModel):
    """
    Metadata for multi-repository search response.

    Attributes:
        total_results: Total number of results across all repositories
        total_repos_searched: Number of repositories successfully searched
        execution_time_ms: Total execution time in milliseconds
    """

    total_results: int = Field(..., description="Total number of results")
    total_repos_searched: int = Field(
        ..., description="Repositories successfully searched"
    )
    execution_time_ms: int = Field(..., description="Execution time in milliseconds")


class MultiSearchResponse(BaseModel):
    """
    Response model for multi-repository search.

    Attributes:
        results: Dictionary mapping repository ID to list of search results
        metadata: Search execution metadata
        errors: Optional dictionary mapping repository ID to error message
    """

    results: Dict[str, List[Dict[str, Any]]] = Field(
        ..., description="Search results grouped by repository"
    )
    metadata: MultiSearchMetadata = Field(..., description="Search metadata")
    errors: Optional[Dict[str, str]] = Field(
        None, description="Errors encountered during search"
    )
