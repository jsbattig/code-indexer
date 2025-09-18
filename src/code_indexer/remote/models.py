"""
Remote status data models.

Provides Pydantic models for remote status functionality.
Following MESSI Rule #1: No mocks - these represent real data structures.
"""

from typing import Optional
from pydantic import BaseModel, Field


class RepositoryStatus(BaseModel):
    """Real repository status data model."""

    repository_alias: str = Field(..., description="Repository alias")
    status: str = Field(..., description="Repository status")
    last_updated: str = Field(..., description="Last update timestamp")
    branch: Optional[str] = Field(None, description="Branch name")
    commit_count: Optional[int] = Field(None, description="Commit count")
    last_commit_sha: Optional[str] = Field(None, description="Last commit SHA")
    indexing_progress: Optional[int] = Field(
        None, description="Indexing progress percentage"
    )


class StalenessInfo(BaseModel):
    """Real staleness information data model."""

    is_stale: bool = Field(..., description="Whether local is stale compared to remote")
    local_timestamp: str = Field(..., description="Local timestamp")
    remote_timestamp: str = Field(..., description="Remote timestamp")
    repository_alias: str = Field(..., description="Repository alias")
    last_commit_sha: Optional[str] = Field(None, description="Last commit SHA")
    branch: Optional[str] = Field(None, description="Branch name")
