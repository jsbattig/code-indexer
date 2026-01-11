"""
Groups API Router for CIDX Server.

Provides API endpoints for group management:
- GET /api/v1/groups - List all groups
- GET /api/v1/groups/{id} - Get group details
- POST /api/v1/groups/{id}/members - Assign user to group (admin only)
- DELETE /api/v1/groups/{id} - Delete group (fails for default groups)

Story #705: Default Group Bootstrap and User Assignment Infrastructure
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator

from ..auth.dependencies import get_current_user, get_current_admin_user
from ..auth.user_manager import User
from ..services.constants import CIDX_META_REPO
from ..services.group_access_manager import (
    GroupAccessManager,
    Group,
    DefaultGroupCannotBeDeletedError,
    GroupHasUsersError,
    CidxMetaCannotBeRevokedError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])

# Global reference to group manager (set during app initialization)
_group_manager: Optional[GroupAccessManager] = None


def get_group_manager() -> GroupAccessManager:
    """Get the GroupAccessManager instance."""
    if _group_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Group manager not initialized",
        )
    return _group_manager


def set_group_manager(manager: GroupAccessManager) -> None:
    """Set the GroupAccessManager instance (called during app startup)."""
    global _group_manager
    _group_manager = manager


# Response models
class GroupResponse(BaseModel):
    """Response model for a group."""

    id: int
    name: str
    description: str
    is_default: bool
    created_at: str


class GroupDetailResponse(BaseModel):
    """Detailed response model for a group including membership info."""

    id: int
    name: str
    description: str
    is_default: bool
    created_at: str
    user_count: int
    user_ids: List[str]
    accessible_repos: List[str]
    repo_count: int


class AssignUserRequest(BaseModel):
    """Request model for assigning a user to a group."""

    user_id: str = Field(..., min_length=1, description="User ID to assign")


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class AddRepoRequest(BaseModel):
    """Request model for adding repository/repositories to a group.

    Supports both single repo (legacy) and bulk repos (new).
    If both repo_name and repos are provided, repos takes priority.
    """

    repo_name: Optional[str] = Field(
        default=None, min_length=1, description="Single repository name (legacy)"
    )
    repos: Optional[List[str]] = Field(
        default=None, description="List of repository names (bulk operation)"
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "AddRepoRequest":
        """Ensure at least one of repo_name or repos is provided with valid content."""
        if self.repo_name is None and self.repos is None:
            raise ValueError("Either 'repo_name' or 'repos' must be provided")
        if self.repos is not None:
            self.repos = [r.strip() for r in self.repos if r and r.strip()]
            if not self.repos:
                raise ValueError(
                    "'repos' list must contain at least one non-empty name"
                )
        return self

    @property
    def get_repos_list(self) -> List[str]:
        """Get list of repos to add. repos takes priority over repo_name."""
        if self.repos is not None:
            return self.repos
        elif self.repo_name is not None:
            return [self.repo_name]
        raise ValueError("Invalid state: no repos specified")


class BulkAddReposResponse(BaseModel):
    """Response model for bulk add repos operation."""

    added: int
    message: str


class BulkRemoveReposRequest(BaseModel):
    """Request model for bulk removing repos from a group."""

    repos: List[str] = Field(..., description="List of repository names to remove")


class BulkRemoveReposResponse(BaseModel):
    """Response model for bulk remove repos operation."""

    removed: int
    message: str


class CreateGroupRequest(BaseModel):
    """Request model for creating a custom group."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Group name (1-100 chars, alphanumeric with hyphens/underscores)",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Group description",
    )


class AuditLogResponse(BaseModel):
    """Response model for a single audit log entry."""

    id: int
    timestamp: str
    admin_id: str
    action_type: str
    target_type: str
    target_id: str
    details: Optional[str] = None


class AuditLogsListResponse(BaseModel):
    """Response model for paginated audit logs list."""

    logs: List[AuditLogResponse]
    total: int


class UpdateGroupRequest(BaseModel):
    """Request model for updating a custom group."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New group name (optional)",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="New group description (optional)",
    )


def _group_to_response(group: Group) -> GroupResponse:
    """Convert a Group object to API response."""
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        is_default=group.is_default,
        created_at=group.created_at.isoformat(),
    )


@router.get("", response_model=List[GroupResponse])
async def list_groups(
    current_user: User = Depends(get_current_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> List[GroupResponse]:
    """
    List all groups.

    Returns a list of all groups with their basic information.
    Accessible by all authenticated users.
    """
    groups = group_manager.get_all_groups()
    return [_group_to_response(g) for g in groups]


@router.post(
    "",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Custom group created successfully"},
        409: {"description": "Group name already exists"},
    },
)
async def create_group(
    request: CreateGroupRequest,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> GroupResponse:
    """
    Create a custom group.

    Story #709: Custom Group Management (AC1)
    Requires admin role. Creates a new group with is_default=FALSE.
    """
    try:
        group = group_manager.create_group(
            name=request.name,
            description=request.description,
        )
        # AC7: Log group creation
        group_manager.log_audit(
            admin_id=current_user.username,
            action_type="group_create",
            target_type="group",
            target_id=str(group.id),
            details=f"Created group '{group.name}'",
        )
        return _group_to_response(group)
    except ValueError:
        # ValueError raised for duplicate name
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Group name already exists",
        )


@router.get("/{group_id}", response_model=GroupDetailResponse)
async def get_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> GroupDetailResponse:
    """
    Get detailed information about a specific group.

    Returns group details including user count and accessible repositories.
    """
    group = group_manager.get_group(group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with ID {group_id} not found",
        )

    user_count = group_manager.get_user_count_in_group(group_id)
    user_ids = group_manager.get_users_in_group(group_id)

    # Get accessible repos based on group (Story #706)
    accessible_repos = group_manager.get_group_repos(group_id)

    return GroupDetailResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        is_default=group.is_default,
        created_at=group.created_at.isoformat(),
        user_count=user_count,
        user_ids=user_ids,
        accessible_repos=accessible_repos,
        repo_count=len(accessible_repos),
    )


@router.put(
    "/{group_id}",
    response_model=GroupResponse,
    responses={
        200: {"description": "Group updated successfully"},
        404: {"description": "Group not found"},
        409: {"description": "Group name already exists"},
    },
)
async def update_group(
    group_id: int,
    request: UpdateGroupRequest,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> GroupResponse:
    """
    Update a custom group.

    Story #709: Custom Group Management (AC4)
    Requires admin role. Updates name and/or description of a custom group.
    is_default cannot be changed and remains FALSE.
    """
    try:
        updated_group = group_manager.update_group(
            group_id=group_id,
            name=request.name,
            description=request.description,
        )
        if updated_group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group with ID {group_id} not found",
            )
        # AC7: Log group update
        group_manager.log_audit(
            admin_id=current_user.username,
            action_type="group_update",
            target_type="group",
            target_id=str(group_id),
            details=f"Updated group '{updated_group.name}'",
        )
        return _group_to_response(updated_group)
    except ValueError as e:
        # ValueError raised for duplicate name or default group
        if "already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Group name already exists",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{group_id}/members", response_model=MessageResponse)
async def assign_user_to_group(
    group_id: int,
    request: AssignUserRequest,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> MessageResponse:
    """
    Assign a user to a group.

    Requires admin role. Replaces any existing group assignment for the user.
    """
    # Verify group exists
    group = group_manager.get_group(group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with ID {group_id} not found",
        )

    group_manager.assign_user_to_group(
        user_id=request.user_id,
        group_id=group_id,
        assigned_by=current_user.username,
    )

    return MessageResponse(
        message=f"User '{request.user_id}' assigned to group '{group.name}'"
    )


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Group deleted successfully"},
        400: {"description": "Cannot delete default group or group with users"},
        404: {"description": "Group not found"},
    },
)
async def delete_group(
    group_id: int,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
):
    """
    Delete a custom group.

    Story #709: Custom Group Management (AC5, AC6, AC7)
    Requires admin role. Default groups cannot be deleted (AC5).
    Groups with users cannot be deleted (AC6).
    Successful deletion returns 204 No Content (AC7).
    """
    try:
        # Get group info before deletion for audit log
        group = group_manager.get_group(group_id)
        group_name = group.name if group else f"ID:{group_id}"

        result = group_manager.delete_group(group_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group with ID {group_id} not found",
            )
        # AC7: Log group deletion
        group_manager.log_audit(
            admin_id=current_user.username,
            action_type="group_delete",
            target_type="group",
            target_id=str(group_id),
            details=f"Deleted group '{group_name}'",
        )
        # AC7: Return 204 No Content on success
        return None

    except DefaultGroupCannotBeDeletedError as e:
        # AC5: Cannot delete default groups
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except GroupHasUsersError as e:
        # AC6: Cannot delete groups with users
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =========================================================================
# Repository Access Endpoints (Story #706)
# =========================================================================


@router.post(
    "/{group_id}/repos",
    response_model=BulkAddReposResponse,
    responses={
        201: {"description": "New repositories added to group"},
        200: {"description": "No new repositories added (idempotent)"},
        404: {"description": "Group not found"},
    },
)
async def add_repo_to_group(
    group_id: int,
    request: AddRepoRequest,
    response: Response,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> BulkAddReposResponse:
    """
    Add repository/repositories to a group's access list.

    Story #710: AC4 - Bulk Add Repos to Group
    Requires admin role. Supports both single repo (legacy) and bulk repos.
    Returns count of newly added repos. Already-accessible repos are skipped.
    Returns 201 Created for new grants, 200 OK for idempotent (no new grants).
    """
    group = group_manager.get_group(group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with ID {group_id} not found",
        )

    repos_to_add = request.get_repos_list
    added_count = 0
    added_repos = []

    for repo_name in repos_to_add:
        newly_granted = group_manager.grant_repo_access(
            repo_name=repo_name,
            group_id=group_id,
            granted_by=current_user.username,
        )
        if newly_granted:
            added_count += 1
            added_repos.append(repo_name)

    # AC7: Log repo access grant for each newly added repo
    for repo_name in added_repos:
        group_manager.log_audit(
            admin_id=current_user.username,
            action_type="repo_access_grant",
            target_type="repo",
            target_id=repo_name,
            details=f"Granted access to '{repo_name}' for group '{group.name}'",
        )

    # Return 201 for new grants, 200 for idempotent (no new grants)
    if added_count > 0:
        response.status_code = status.HTTP_201_CREATED

    return BulkAddReposResponse(
        added=added_count,
        message=f"Added {added_count} repo(s) to group '{group.name}'",
    )


@router.delete(
    "/{group_id}/repos/{repo_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Repository access revoked"},
        400: {"description": "Cannot revoke cidx-meta access"},
        404: {"description": "Group or repository access not found"},
    },
)
async def remove_repo_from_group(
    group_id: int,
    repo_name: str,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
):
    """
    Remove a repository from a group's access list.

    Requires admin role. Revokes the group's access to the repository.
    cidx-meta access cannot be revoked (returns 400).
    """
    # Verify group exists
    group = group_manager.get_group(group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with ID {group_id} not found",
        )

    try:
        revoked = group_manager.revoke_repo_access(
            repo_name=repo_name,
            group_id=group_id,
        )

        if not revoked:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository '{repo_name}' not found in group '{group.name}' access list",
            )

        # Return 204 No Content on success
        return None

    except CidxMetaCannotBeRevokedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cidx-meta access cannot be revoked from any group",
        )


@router.delete(
    "/{group_id}/repos",
    response_model=BulkRemoveReposResponse,
    responses={
        200: {"description": "Repositories removed from group"},
        404: {"description": "Group not found"},
    },
)
async def bulk_remove_repos_from_group(
    group_id: int,
    request: BulkRemoveReposRequest,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> BulkRemoveReposResponse:
    """
    Remove multiple repositories from a group's access list.

    Story #710: AC5 - Bulk Remove Repos from Group
    Requires admin role. cidx-meta is silently skipped (cannot be removed).
    Returns count of repos actually removed.
    """
    group = group_manager.get_group(group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with ID {group_id} not found",
        )

    removed_count = 0
    removed_repos = []

    for repo_name in request.repos:
        # Silently skip cidx-meta (AC5 requirement)
        if repo_name == CIDX_META_REPO:
            continue
        try:
            revoked = group_manager.revoke_repo_access(
                repo_name=repo_name,
                group_id=group_id,
            )
            if revoked:
                removed_count += 1
                removed_repos.append(repo_name)
        except CidxMetaCannotBeRevokedError:
            # Should not happen since we skip cidx-meta above, but be safe
            continue

    # AC7: Log repo access revoke for each removed repo
    for repo_name in removed_repos:
        group_manager.log_audit(
            admin_id=current_user.username,
            action_type="repo_access_revoke",
            target_type="repo",
            target_id=repo_name,
            details=f"Revoked access to '{repo_name}' from group '{group.name}'",
        )

    return BulkRemoveReposResponse(
        removed=removed_count,
        message=f"Removed {removed_count} repo(s) from group '{group.name}'",
    )


# =========================================================================
# Users Router (Story #710: Admin User and Group Management Interface)
# =========================================================================

users_router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UserWithGroupResponse(BaseModel):
    """Response model for a user with group information."""

    user_id: str
    group_id: int
    group_name: str
    assigned_at: str
    assigned_by: str


class UsersListResponse(BaseModel):
    """Response model for paginated users list."""

    users: List[UserWithGroupResponse]
    total: int


@users_router.get("", response_model=UsersListResponse)
async def list_users(
    limit: Optional[int] = None,
    offset: int = 0,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> UsersListResponse:
    """
    List all users with their group membership information.

    Story #710: AC1 - List Users with Group Information
    Requires admin role. Returns paginated list sorted alphabetically by user_id.
    """
    users, total = group_manager.get_all_users_with_groups(limit=limit, offset=offset)

    return UsersListResponse(
        users=[UserWithGroupResponse(**u) for u in users],
        total=total,
    )


class MoveUserToGroupRequest(BaseModel):
    """Request model for moving a user to a different group."""

    group_id: int = Field(..., description="Target group ID")


@users_router.put(
    "/{user_id}/group",
    response_model=MessageResponse,
    responses={
        200: {"description": "User moved to group successfully"},
        404: {"description": "User or group not found"},
    },
)
async def move_user_to_group(
    user_id: str,
    request: MoveUserToGroupRequest,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> MessageResponse:
    """
    Move a user to a different group.

    Story #710: AC2 - Move User Between Groups
    Requires admin role. Updates membership, sets assigned_by to current admin.
    """
    # Check if user exists
    if not group_manager.user_exists(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )

    # Check if target group exists
    target_group = group_manager.get_group(request.group_id)
    if target_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with ID {request.group_id} not found",
        )

    # Get previous group for audit log
    previous_group = group_manager.get_user_group(user_id)
    previous_group_name = previous_group.name if previous_group else "none"

    # Perform the move
    group_manager.assign_user_to_group(
        user_id=user_id,
        group_id=request.group_id,
        assigned_by=current_user.username,
    )

    # AC7: Log user group change
    group_manager.log_audit(
        admin_id=current_user.username,
        action_type="user_group_change",
        target_type="user",
        target_id=user_id,
        details=f"Moved user '{user_id}' from '{previous_group_name}' to '{target_group.name}'",
    )

    return MessageResponse(
        message=f"User '{user_id}' moved to group '{target_group.name}'"
    )


# =========================================================================
# Audit Logs Router (Story #710: AC8)
# =========================================================================

audit_router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])


@audit_router.get("", response_model=AuditLogsListResponse)
async def get_audit_logs(
    action_type: Optional[str] = None,
    target_type: Optional[str] = None,
    admin_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    current_user: User = Depends(get_current_admin_user),
    group_manager: GroupAccessManager = Depends(get_group_manager),
) -> AuditLogsListResponse:
    """
    Get audit log entries with optional filters.

    Story #710: AC8 - Get Audit Logs
    Requires admin role. Returns paginated list sorted by timestamp descending.

    Filters:
    - action_type: Filter by action type (user_group_change, repo_access_grant, etc.)
    - target_type: Filter by target type (user, group, repo)
    - admin_id: Filter by admin who performed the action
    - date_from: Filter logs from this date (YYYY-MM-DD)
    - date_to: Filter logs up to this date (YYYY-MM-DD)
    """
    logs, total = group_manager.get_audit_logs(
        action_type=action_type,
        target_type=target_type,
        admin_id=admin_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    return AuditLogsListResponse(
        logs=[AuditLogResponse(**log) for log in logs],
        total=total,
    )
