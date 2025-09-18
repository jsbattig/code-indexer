"""
Repository Discovery Models for CIDX Server.

Provides Pydantic models for repository discovery endpoint requests and responses.
Following CLAUDE.md Foundation #1: No mocks - these represent real data structures.
"""

from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class RepositoryDiscoveryRequest(BaseModel):
    """Request model for repository discovery endpoint."""

    repo_url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Git repository URL to discover matching repositories for",
    )

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        """Validate repository URL is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError(
                "Repository URL cannot be empty or contain only whitespace"
            )

        v = v.strip()

        # Basic validation for URL-like format
        if not any(
            protocol in v.lower()
            for protocol in ["http://", "https://", "git@", "ssh://"]
        ):
            raise ValueError(
                "Repository URL must be a valid git URL (HTTP, HTTPS, or SSH)"
            )

        return v


class RepositoryMatch(BaseModel):
    """Model representing a matching repository."""

    alias: str = Field(..., description="Repository alias")
    repository_type: Literal["golden", "activated"] = Field(
        ..., description="Type of repository (golden or activated)"
    )
    git_url: str = Field(..., description="Original git URL")
    available_branches: List[str] = Field(..., description="List of available branches")
    default_branch: Optional[str] = Field(None, description="Default branch name")
    last_indexed: Optional[datetime] = Field(
        None, description="Last indexing timestamp"
    )
    display_name: str = Field(..., description="Human-readable repository display name")
    description: str = Field(..., description="Repository description")

    @field_validator("repository_type")
    @classmethod
    def validate_repository_type(cls, v: str) -> str:
        """Validate repository type."""
        if v not in ["golden", "activated"]:
            raise ValueError("Repository type must be 'golden' or 'activated'")
        return v

    @field_validator("available_branches")
    @classmethod
    def validate_available_branches(cls, v: List[str]) -> List[str]:
        """Validate available branches list."""
        if not v:
            raise ValueError("Repository must have at least one available branch")

        # Remove empty branch names and duplicates while preserving order
        seen = set()
        cleaned_branches = []
        for branch in v:
            if branch and branch.strip() and branch not in seen:
                cleaned_branches.append(branch.strip())
                seen.add(branch.strip())

        if not cleaned_branches:
            raise ValueError("Repository must have at least one valid branch name")

        return cleaned_branches


class RepositoryDiscoveryResponse(BaseModel):
    """Response model for repository discovery endpoint."""

    query_url: str = Field(..., description="Original query URL")
    normalized_url: str = Field(..., description="Normalized canonical URL")
    golden_repositories: List[RepositoryMatch] = Field(
        ..., description="Matching golden repositories"
    )
    activated_repositories: List[RepositoryMatch] = Field(
        ..., description="Matching activated repositories"
    )
    total_matches: int = Field(..., description="Total number of matching repositories")

    @field_validator("total_matches")
    @classmethod
    def validate_total_matches(cls, v: int, values) -> int:
        """Validate total matches consistency."""
        # Note: In Pydantic v2, we need to use info.data instead of values
        # This validation will be checked if both fields are present
        return v

    def model_post_init(self, __context) -> None:
        """Post-initialization validation."""
        # Verify total_matches matches actual count
        actual_total = len(self.golden_repositories) + len(self.activated_repositories)
        if self.total_matches != actual_total:
            raise ValueError(
                f"total_matches ({self.total_matches}) does not match actual count ({actual_total})"
            )


class RepositoryDiscoveryError(BaseModel):
    """Error response model for repository discovery endpoint."""

    error_type: str = Field(..., description="Type of error")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[str] = Field(None, description="Additional error details")
    query_url: Optional[str] = Field(
        None, description="Original query URL that caused the error"
    )


class RepositoryDiscoveryStats(BaseModel):
    """Statistics model for repository discovery operations."""

    total_queries: int = Field(..., description="Total number of discovery queries")
    successful_queries: int = Field(..., description="Number of successful queries")
    failed_queries: int = Field(..., description="Number of failed queries")
    average_response_time_ms: float = Field(
        ..., description="Average response time in milliseconds"
    )
    total_repositories_found: int = Field(
        ..., description="Total repositories found across all queries"
    )
    golden_repositories_found: int = Field(..., description="Golden repositories found")
    activated_repositories_found: int = Field(
        ..., description="Activated repositories found"
    )


class RepositoryAccessInfo(BaseModel):
    """Model for repository access information."""

    repository_alias: str = Field(..., description="Repository alias")
    repository_type: Literal["golden", "activated"] = Field(
        ..., description="Type of repository"
    )
    access_level: Literal["read", "write", "admin"] = Field(
        ..., description="User's access level"
    )
    can_read: bool = Field(..., description="Whether user can read repository")
    can_write: bool = Field(..., description="Whether user can write to repository")
    can_admin: bool = Field(..., description="Whether user can administer repository")

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, v: str) -> str:
        """Validate access level."""
        if v not in ["read", "write", "admin"]:
            raise ValueError("Access level must be 'read', 'write', or 'admin'")
        return v

    def model_post_init(self, __context) -> None:
        """Post-initialization validation."""
        # Verify access level consistency with boolean flags
        if self.access_level == "read":
            if not self.can_read or self.can_write or self.can_admin:
                raise ValueError("Read access level should only allow reading")
        elif self.access_level == "write":
            if not self.can_read or not self.can_write or self.can_admin:
                raise ValueError(
                    "Write access level should allow read and write but not admin"
                )
        elif self.access_level == "admin":
            if not self.can_read or not self.can_write or not self.can_admin:
                raise ValueError("Admin access level should allow all operations")


class RepositorySuggestion(BaseModel):
    """Model for repository suggestions."""

    repository_match: RepositoryMatch = Field(
        ..., description="Repository match information"
    )
    similarity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Similarity score between 0.0 and 1.0"
    )
    suggestion_reason: str = Field(
        ..., description="Reason why this repository was suggested"
    )

    @field_validator("similarity_score")
    @classmethod
    def validate_similarity_score(cls, v: float) -> float:
        """Validate similarity score range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Similarity score must be between 0.0 and 1.0")
        return v


class RepositorySuggestionsResponse(BaseModel):
    """Response model for repository suggestions endpoint."""

    query_url: str = Field(..., description="Original query URL")
    suggestions: List[RepositorySuggestion] = Field(
        ..., description="List of repository suggestions"
    )
    total_suggestions: int = Field(..., description="Total number of suggestions")

    def model_post_init(self, __context) -> None:
        """Post-initialization validation."""
        # Verify total_suggestions matches actual count
        if self.total_suggestions != len(self.suggestions):
            raise ValueError(
                f"total_suggestions ({self.total_suggestions}) does not match actual count ({len(self.suggestions)})"
            )
