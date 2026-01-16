"""
Auto-Discovery Models for CIDX Server.

Provides Pydantic models for GitLab/GitHub repository auto-discovery:
- DiscoveredRepository: Model for a discovered repository from GitLab/GitHub
- RepositoryDiscoveryResult: Paginated response model for discovery endpoint
- DiscoveryProviderError: Error response model for discovery failures
"""

from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class DiscoveredRepository(BaseModel):
    """Model representing a discovered repository from GitLab or GitHub."""

    platform: Literal["gitlab", "github"] = Field(
        ..., description="Platform source (gitlab or github)"
    )
    name: str = Field(..., min_length=1, description="Full path (e.g., group/project)")
    description: Optional[str] = Field(None, description="Project description")
    clone_url_https: str = Field(..., description="HTTPS clone URL")
    clone_url_ssh: str = Field(..., description="SSH clone URL")
    default_branch: str = Field(..., description="Default branch (main/master/etc)")
    last_commit_hash: Optional[str] = Field(
        None, description="Short hash of last commit"
    )
    last_commit_author: Optional[str] = Field(None, description="Author of last commit")
    last_activity: Optional[datetime] = Field(
        None, description="Last activity timestamp"
    )
    is_private: bool = Field(..., description="Whether repository is private")

    @field_validator("clone_url_https")
    @classmethod
    def validate_https_url(cls, v: str) -> str:
        """Validate HTTPS clone URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("clone_url_https must be a valid HTTP/HTTPS URL")
        return v

    @field_validator("clone_url_ssh")
    @classmethod
    def validate_ssh_url(cls, v: str) -> str:
        """Validate SSH clone URL format."""
        if not (v.startswith("git@") or v.startswith("ssh://")):
            raise ValueError("clone_url_ssh must be a valid SSH URL")
        return v


class RepositoryDiscoveryResult(BaseModel):
    """Paginated response model for repository discovery endpoint."""

    repositories: List[DiscoveredRepository] = Field(
        ..., description="List of discovered repositories"
    )
    total_count: int = Field(
        ..., ge=0, description="Total number of repositories available"
    )
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    platform: Literal["gitlab", "github"] = Field(..., description="Platform source")


class DiscoveryProviderError(BaseModel):
    """Error response model for repository discovery failures."""

    platform: Literal["gitlab", "github"] = Field(
        ..., description="Platform that failed"
    )
    error_type: Literal["not_configured", "api_error", "auth_error", "timeout"] = Field(
        ..., description="Type of error"
    )
    message: str = Field(..., description="Human-readable error message")
    details: Optional[str] = Field(None, description="Additional error details")
