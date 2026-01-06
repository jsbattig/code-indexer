"""
Request and response models for multi-repository SCIP operations.

Provides Pydantic models for SCIP cross-repository intelligence API
request validation and response structure.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class SCIPMultiRequest(BaseModel):
    """
    Request model for multi-repository SCIP operations.

    Attributes:
        repositories: List of repository identifiers to search
        symbol: Symbol name to search for (for definition, references, dependencies, dependents)
        from_symbol: Starting symbol for call chain tracing (optional, for callchain only)
        to_symbol: Target symbol for call chain tracing (optional, for callchain only)
        limit: Maximum results per repository (optional)
        max_depth: Maximum traversal depth for dependencies/dependents/callchain (optional)
        timeout_seconds: Query timeout per repository in seconds (optional, overrides default)
    """

    repositories: List[str] = Field(
        ...,
        description="List of repository identifiers to search",
        min_length=1,
    )
    symbol: str = Field(..., description="Symbol name to search for")
    from_symbol: Optional[str] = Field(
        None, description="Starting symbol for call chain tracing"
    )
    to_symbol: Optional[str] = Field(
        None, description="Target symbol for call chain tracing"
    )
    limit: Optional[int] = Field(None, description="Maximum results per repository")
    max_depth: Optional[int] = Field(
        None,
        description="Maximum traversal depth for dependencies/dependents/callchain",
    )
    timeout_seconds: Optional[int] = Field(
        None, description="Query timeout per repository in seconds (overrides default)"
    )

    @field_validator("repositories")
    @classmethod
    def validate_repositories(cls, v: List[str]) -> List[str]:
        """Ensure at least one repository is specified."""
        if not v:
            raise ValueError("Must specify at least one repository")
        return v


class SCIPResult(BaseModel):
    """
    Model for a single SCIP query result.

    Attributes:
        repository: Repository identifier where result was found
        file_path: File path relative to repository root
        line: Line number (1-indexed)
        column: Column number (0-indexed)
        symbol: Symbol identifier
        kind: Result kind (definition, reference, dependency, dependent)
        context: Optional code context or additional information
    """

    repository: str = Field(..., description="Repository identifier")
    file_path: str = Field(..., description="File path relative to repository root")
    line: int = Field(..., description="Line number (1-indexed)")
    column: int = Field(..., description="Column number (0-indexed)")
    symbol: str = Field(..., description="Symbol identifier")
    kind: str = Field(
        ..., description="Result kind (definition, reference, dependency, dependent)"
    )
    context: Optional[str] = Field(
        None, description="Code context or additional information"
    )


class SCIPMultiMetadata(BaseModel):
    """
    Metadata for multi-repository SCIP response.

    Attributes:
        total_results: Total number of results across all repositories
        repos_searched: Number of repositories successfully searched
        repos_with_results: Number of repositories that returned results
        execution_time_ms: Total execution time in milliseconds
    """

    total_results: int = Field(..., description="Total number of results")
    repos_searched: int = Field(..., description="Repositories successfully searched")
    repos_with_results: int = Field(
        ..., description="Repositories that returned results"
    )
    execution_time_ms: int = Field(..., description="Execution time in milliseconds")


class SCIPMultiResponse(BaseModel):
    """
    Response model for multi-repository SCIP operations.

    Attributes:
        results: Dictionary mapping repository ID to list of SCIP results
        metadata: Search execution metadata
        skipped: Dictionary mapping repository ID to skip reason (e.g., no SCIP index)
        errors: Optional dictionary mapping repository ID to error message
    """

    results: Dict[str, List[SCIPResult]] = Field(
        ..., description="SCIP results grouped by repository"
    )
    metadata: SCIPMultiMetadata = Field(..., description="Search metadata")
    skipped: Dict[str, str] = Field(
        ..., description="Repositories skipped with reasons"
    )
    errors: Optional[Dict[str, str]] = Field(
        None, description="Errors encountered during search"
    )
