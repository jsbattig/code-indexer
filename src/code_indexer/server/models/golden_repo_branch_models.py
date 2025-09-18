"""
Pydantic models for golden repository branch listing functionality.

Contains data models specifically for the golden repository branch listing endpoint,
following CLAUDE.md principles - simple, direct models without over-engineering.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class GoldenRepoBranchInfo(BaseModel):
    """Information about a branch in a golden repository."""

    name: str = Field(description="Branch name")
    is_default: bool = Field(description="Whether this is the default/primary branch")
    last_commit_hash: Optional[str] = Field(None, description="Last commit SHA hash")
    last_commit_timestamp: Optional[datetime] = Field(
        None, description="Last commit timestamp"
    )
    last_commit_author: Optional[str] = Field(
        None, description="Last commit author name"
    )
    branch_type: Optional[str] = Field(
        None,
        description="Branch type classification: main, feature, release, hotfix, other",
    )


class GoldenRepositoryBranchesResponse(BaseModel):
    """Response model for golden repository branch listing API endpoint."""

    repository_alias: str = Field(description="Alias of the golden repository")
    total_branches: int = Field(description="Total number of branches")
    default_branch: Optional[str] = Field(
        None, description="Name of the default/primary branch"
    )
    branches: List[GoldenRepoBranchInfo] = Field(
        description="List of branches in the repository"
    )
    retrieved_at: datetime = Field(
        description="Timestamp when branch information was retrieved"
    )
