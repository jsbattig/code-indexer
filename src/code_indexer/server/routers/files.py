"""
File CRUD REST API Router.

Provides REST endpoints for file create, edit, and delete operations
with OAuth authentication and service layer integration.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.auth.user_manager import User
from code_indexer.server.services.file_crud_service import (
    FileCRUDService,
    HashMismatchError,
    CRUDOperationError
)

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(
    prefix="/api/v1/repos/{alias}",
    tags=["files"]
)


# Request/Response Models

class CreateFileRequest(BaseModel):
    """Request model for creating a file."""
    file_path: str = Field(..., description="Path to the file within repository")
    content: str = Field(..., description="File content")


class CreateFileResponse(BaseModel):
    """Response model for file creation."""
    success: bool = Field(..., description="Operation success status")
    file_path: str = Field(..., description="Created file path")
    content_hash: str = Field(..., description="SHA-256 hash of file content")
    size_bytes: int = Field(..., description="File size in bytes")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")


class EditFileRequest(BaseModel):
    """Request model for editing a file."""
    old_string: str = Field(..., description="String to search for in file")
    new_string: str = Field(..., description="String to replace with")
    content_hash: str = Field(..., description="Expected content hash for verification")
    replace_all: bool = Field(False, description="Replace all occurrences (default: first only)")


class EditFileResponse(BaseModel):
    """Response model for file edit."""
    success: bool = Field(..., description="Operation success status")
    file_path: str = Field(..., description="Edited file path")
    content_hash: str = Field(..., description="SHA-256 hash of new content")
    modified_at: str = Field(..., description="Modification timestamp (ISO 8601)")
    changes_made: int = Field(..., description="Number of replacements made")


class DeleteFileResponse(BaseModel):
    """Response model for file deletion."""
    success: bool = Field(..., description="Operation success status")
    file_path: str = Field(..., description="Deleted file path")
    deleted_at: str = Field(..., description="Deletion timestamp (ISO 8601)")


# Endpoints

@router.post(
    "/files",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateFileResponse,
    responses={
        201: {"description": "File created successfully"},
        400: {"description": "Invalid parameters"},
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Permission denied (.git/ access blocked)"},
        404: {"description": "Repository not found"},
        409: {"description": "File already exists"}
    },
    summary="Create a new file",
    description="Create a new file in the activated repository with specified content"
)
async def create_file(
    alias: str,
    request: CreateFileRequest,
    user: User = Depends(get_current_user)
) -> CreateFileResponse:
    """
    Create a new file in the repository.

    Args:
        alias: Repository alias
        request: File creation request with path and content
        user: Authenticated user (from OAuth/JWT)

    Returns:
        CreateFileResponse with file metadata

    Raises:
        HTTPException: On various error conditions
    """
    try:
        service = FileCRUDService()
        result = service.create_file(
            repo_alias=alias,
            file_path=request.file_path,
            content=request.content,
            username=user.username
        )
        return CreateFileResponse(**result)

    except FileExistsError as e:
        logger.warning(f"File already exists: {alias}/{request.file_path}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for {alias}/{request.file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except FileNotFoundError as e:
        logger.warning(f"Repository not found: {alias}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValueError as e:
        logger.warning(f"Invalid request for {alias}/{request.file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Create file failed for {alias}/{request.file_path}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.patch(
    "/files/{file_path:path}",
    status_code=status.HTTP_200_OK,
    response_model=EditFileResponse,
    responses={
        200: {"description": "File edited successfully"},
        400: {"description": "Invalid parameters"},
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Permission denied (.git/ access blocked)"},
        404: {"description": "Repository or file not found"},
        409: {"description": "Hash mismatch - file was modified"}
    },
    summary="Edit an existing file",
    description="Edit an existing file in the activated repository using string replacement"
)
async def edit_file(
    alias: str,
    file_path: str,
    request: EditFileRequest,
    user: User = Depends(get_current_user)
) -> EditFileResponse:
    """
    Edit an existing file in the repository.

    Args:
        alias: Repository alias
        file_path: Path to the file within repository (can contain slashes)
        request: File edit request with old_string, new_string, content_hash, replace_all
        user: Authenticated user (from OAuth/JWT)

    Returns:
        EditFileResponse with updated file metadata and changes_made count

    Raises:
        HTTPException: On various error conditions
    """
    try:
        service = FileCRUDService()
        result = service.edit_file(
            repo_alias=alias,
            file_path=file_path,
            old_string=request.old_string,
            new_string=request.new_string,
            content_hash=request.content_hash,
            replace_all=request.replace_all,
            username=user.username
        )
        return EditFileResponse(**result)

    except HashMismatchError as e:
        logger.warning(f"Hash mismatch for {alias}/{file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission denied for {alias}/{file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except FileNotFoundError as e:
        logger.warning(f"File or repository not found: {alias}/{file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValueError as e:
        logger.warning(f"Invalid request for {alias}/{file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Edit file failed for {alias}/{file_path}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.delete(
    "/files/{file_path:path}",
    status_code=status.HTTP_200_OK,
    response_model=DeleteFileResponse,
    responses={
        200: {"description": "File deleted successfully"},
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Permission denied (.git/ access blocked)"},
        404: {"description": "Repository or file not found"}
    },
    summary="Delete a file",
    description="Delete a file from the activated repository"
)
async def delete_file(
    alias: str,
    file_path: str,
    content_hash: Optional[str] = Query(None, description="Expected content hash for verification"),
    user: User = Depends(get_current_user)
) -> DeleteFileResponse:
    """
    Delete a file from the repository.

    Args:
        alias: Repository alias
        file_path: Path to the file within repository (can contain slashes)
        content_hash: Optional content hash for verification
        user: Authenticated user (from OAuth/JWT)

    Returns:
        DeleteFileResponse with deletion confirmation

    Raises:
        HTTPException: On various error conditions
    """
    try:
        service = FileCRUDService()
        result = service.delete_file(
            repo_alias=alias,
            file_path=file_path,
            content_hash=content_hash,
            username=user.username
        )
        return DeleteFileResponse(**result)

    except PermissionError as e:
        logger.warning(f"Permission denied for {alias}/{file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except FileNotFoundError as e:
        logger.warning(f"File or repository not found: {alias}/{file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Delete file failed for {alias}/{file_path}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
