"""
Pydantic models for Git Operations REST API.

Request and response models for all git operation endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


# Git Status/Inspection Models


class GitStatusResponse(BaseModel):
    """Response model for git status."""

    success: bool = Field(..., description="Operation success status")
    staged: List[str] = Field(..., description="List of staged files")
    unstaged: List[str] = Field(..., description="List of unstaged files")
    untracked: List[str] = Field(..., description="List of untracked files")


class GitDiffResponse(BaseModel):
    """Response model for git diff."""

    success: bool = Field(..., description="Operation success status")
    diff_text: str = Field(..., description="Diff output")
    files_changed: int = Field(..., description="Number of files changed")


class GitCommitInfo(BaseModel):
    """Model for a single git commit."""

    commit_hash: str = Field(..., description="Commit SHA hash")
    author: str = Field(..., description="Commit author name and email")
    date: str = Field(..., description="Commit date (ISO 8601)")
    message: str = Field(..., description="Commit message")


class GitLogResponse(BaseModel):
    """Response model for git log."""

    success: bool = Field(..., description="Operation success status")
    commits: List[GitCommitInfo] = Field(..., description="List of commits")


# Git Staging/Commit Models


class GitStageRequest(BaseModel):
    """Request model for staging files."""

    file_paths: List[str] = Field(..., description="List of file paths to stage")


class GitStageResponse(BaseModel):
    """Response model for git stage."""

    success: bool = Field(..., description="Operation success status")
    staged_files: List[str] = Field(..., description="Files that were staged")


class GitUnstageRequest(BaseModel):
    """Request model for unstaging files."""

    file_paths: List[str] = Field(..., description="List of file paths to unstage")


class GitUnstageResponse(BaseModel):
    """Response model for git unstage."""

    success: bool = Field(..., description="Operation success status")
    unstaged_files: List[str] = Field(..., description="Files that were unstaged")


class GitCommitRequest(BaseModel):
    """Request model for creating a commit."""

    message: str = Field(..., description="Commit message")
    author_name: Optional[str] = Field(None, description="Author name (optional)")
    author_email: Optional[str] = Field(None, description="Author email (optional)")


class GitCommitResponse(BaseModel):
    """Response model for git commit."""

    success: bool = Field(..., description="Operation success status")
    commit_hash: str = Field(..., description="SHA hash of created commit")
    short_hash: str = Field(..., description="Short SHA hash (first 7 characters)")
    message: str = Field(..., description="Commit message")
    author: str = Field(..., description="Author email address")
    files_committed: int = Field(..., description="Number of files committed")


# Git Remote Models


class GitPushRequest(BaseModel):
    """Request model for git push."""

    remote: str = Field("origin", description="Remote name")
    branch: Optional[str] = Field(None, description="Branch name (optional)")


class GitPushResponse(BaseModel):
    """Response model for git push."""

    success: bool = Field(..., description="Operation success status")
    branch: str = Field(..., description="Branch that was pushed")
    remote: str = Field(..., description="Remote name")
    commits_pushed: int = Field(..., description="Number of commits pushed")


class GitPullRequest(BaseModel):
    """Request model for git pull."""

    remote: str = Field("origin", description="Remote name")
    branch: Optional[str] = Field(None, description="Branch name (optional)")


class GitPullResponse(BaseModel):
    """Response model for git pull."""

    success: bool = Field(..., description="Operation success status")
    updated_files: int = Field(..., description="Number of files updated")
    conflicts: List[str] = Field(..., description="List of conflicted files")


class GitFetchRequest(BaseModel):
    """Request model for git fetch."""

    remote: str = Field("origin", description="Remote name")


class GitFetchResponse(BaseModel):
    """Response model for git fetch."""

    success: bool = Field(..., description="Operation success status")
    fetched_refs: List[str] = Field(..., description="List of fetched refs")


# Git Recovery Models


class GitResetRequest(BaseModel):
    """Request model for git reset."""

    mode: str = Field(..., description="Reset mode (soft/mixed/hard)")
    commit_hash: Optional[str] = Field(
        None, description="Target commit hash (optional)"
    )
    confirmation_token: Optional[str] = Field(
        None, description="Confirmation token for destructive operations"
    )


class GitResetResponse(BaseModel):
    """Response model for git reset."""

    success: Optional[bool] = Field(None, description="Operation success status")
    reset_mode: Optional[str] = Field(None, description="Reset mode used")
    target_commit: Optional[str] = Field(None, description="Target commit hash")
    requires_confirmation: Optional[bool] = Field(
        None, description="Whether confirmation is required"
    )
    token: Optional[str] = Field(None, description="Confirmation token if required")


class GitCleanRequest(BaseModel):
    """Request model for git clean."""

    confirmation_token: Optional[str] = Field(None, description="Confirmation token")


class GitCleanResponse(BaseModel):
    """Response model for git clean."""

    success: Optional[bool] = Field(None, description="Operation success status")
    removed_files: Optional[List[str]] = Field(
        None, description="List of removed files"
    )
    requires_confirmation: Optional[bool] = Field(
        None, description="Whether confirmation is required"
    )
    token: Optional[str] = Field(None, description="Confirmation token if required")


class GitMergeAbortResponse(BaseModel):
    """Response model for git merge abort."""

    success: bool = Field(..., description="Operation success status")
    aborted: bool = Field(..., description="Whether merge was aborted")


class GitCheckoutFileRequest(BaseModel):
    """Request model for checking out a file."""

    file_path: str = Field(..., description="File path to restore")


class GitCheckoutFileResponse(BaseModel):
    """Response model for git checkout file."""

    success: bool = Field(..., description="Operation success status")
    restored_file: str = Field(..., description="Path of restored file")


# Git Branch Models


class GitBranchListResponse(BaseModel):
    """Response model for listing branches."""

    success: bool = Field(..., description="Operation success status")
    current: str = Field(..., description="Current branch name")
    local: List[str] = Field(..., description="List of local branches")
    remote: List[str] = Field(..., description="List of remote branches")


class GitBranchCreateRequest(BaseModel):
    """Request model for creating a branch."""

    branch_name: str = Field(..., description="New branch name")


class GitBranchCreateResponse(BaseModel):
    """Response model for creating a branch."""

    success: bool = Field(..., description="Operation success status")
    created_branch: str = Field(..., description="Name of created branch")


class GitBranchSwitchResponse(BaseModel):
    """Response model for switching branches."""

    success: bool = Field(..., description="Operation success status")
    current_branch: str = Field(..., description="Current branch after switch")
    previous_branch: str = Field(..., description="Previous branch")


class GitBranchDeleteResponse(BaseModel):
    """Response model for deleting a branch."""

    success: Optional[bool] = Field(None, description="Operation success status")
    deleted_branch: Optional[str] = Field(None, description="Name of deleted branch")
    requires_confirmation: Optional[bool] = Field(
        None, description="Whether confirmation is required"
    )
    token: Optional[str] = Field(None, description="Confirmation token if required")
