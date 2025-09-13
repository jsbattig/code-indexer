"""
Pydantic models for branch-related API responses.

Contains all data models for branch listing functionality following
CLAUDE.md principles - simple, direct models without over-engineering.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class CommitInfo(BaseModel):
    """Information about a git commit."""

    sha: str = Field(description="Commit SHA hash")
    message: str = Field(description="Commit message")
    author: str = Field(description="Commit author name")
    date: str = Field(description="Commit date in ISO format")


class IndexStatus(BaseModel):
    """Index status information for a branch."""

    status: str = Field(
        description="Index status: indexed, indexing, not_indexed, error"
    )
    files_indexed: Optional[int] = Field(None, description="Number of files indexed")
    total_files: Optional[int] = Field(None, description="Total files in branch")
    last_indexed: Optional[str] = Field(
        None, description="Last indexed timestamp in ISO format"
    )
    progress_percentage: Optional[float] = Field(
        None, description="Indexing progress 0-100"
    )


class RemoteTrackingInfo(BaseModel):
    """Remote tracking information for a branch."""

    remote: Optional[str] = Field(
        None, description="Remote branch name (e.g., 'origin/main')"
    )
    ahead: int = Field(0, description="Number of commits ahead of remote")
    behind: int = Field(0, description="Number of commits behind remote")


class BranchInfo(BaseModel):
    """Information about a git branch."""

    name: str = Field(description="Branch name")
    is_current: bool = Field(description="Whether this is the current active branch")
    last_commit: CommitInfo = Field(description="Last commit information")
    index_status: IndexStatus = Field(description="Index status for this branch")
    remote_tracking: Optional[RemoteTrackingInfo] = Field(
        None, description="Remote tracking information"
    )


class BranchListResponse(BaseModel):
    """Response model for branch listing API endpoint."""

    branches: List[BranchInfo] = Field(description="List of branches in the repository")
    total: int = Field(description="Total number of branches")
    current_branch: str = Field(description="Name of the currently active branch")
