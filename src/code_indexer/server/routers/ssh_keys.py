"""
SSH Keys REST API Router.

Provides CRUD operations for SSH key management.
"""

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
import os

from ..services.ssh_key_manager import (
    SSHKeyManager,
    KeyMetadata,
    KeyListResult,
    KeyNotFoundError,
    HostConflictError,
)
from ..services.ssh_key_generator import (
    InvalidKeyNameError,
    KeyAlreadyExistsError,
)


# Request/Response Models
class CreateKeyRequest(BaseModel):
    """Request to create a new SSH key."""

    name: str = Field(..., description="Name for the key (used as filename)")
    key_type: str = Field(default="ed25519", description="Key type (ed25519, rsa)")
    email: Optional[str] = Field(None, description="Email comment for the key")
    description: Optional[str] = Field(None, description="Human-readable description")


class CreateKeyResponse(BaseModel):
    """Response after creating an SSH key."""

    name: str
    fingerprint: str
    key_type: str
    public_key: str
    email: Optional[str] = None
    description: Optional[str] = None


class KeyInfoResponse(BaseModel):
    """Information about a managed SSH key."""

    name: str
    fingerprint: str
    key_type: str
    hosts: List[str] = []
    email: Optional[str] = None
    description: Optional[str] = None
    is_imported: bool = False


class UnmanagedKeyResponse(BaseModel):
    """Information about an unmanaged SSH key."""

    name: str
    fingerprint: Optional[str] = None
    private_path: str


class KeyListResponse(BaseModel):
    """Response listing managed and unmanaged keys."""

    managed: List[KeyInfoResponse]
    unmanaged: List[UnmanagedKeyResponse]


class DeleteKeyResponse(BaseModel):
    """Response after deleting a key."""

    success: bool
    message: str = "Key deleted"


class AssignHostRequest(BaseModel):
    """Request to assign a host to a key."""

    hostname: str = Field(..., description="Hostname to assign (e.g., github.com)")
    force: bool = Field(default=False, description="Override user section conflicts")


class KeyWithHostsResponse(BaseModel):
    """Response with key information including hosts."""

    name: str
    fingerprint: str
    key_type: str
    hosts: List[str]
    email: Optional[str] = None
    description: Optional[str] = None


# Singleton manager instance (can be overridden for testing)
_ssh_key_manager: Optional[SSHKeyManager] = None


def get_ssh_key_manager() -> SSHKeyManager:
    """Get or create the SSH key manager instance."""
    global _ssh_key_manager
    if _ssh_key_manager is None:
        # Allow override via environment variables for testing
        ssh_dir = os.environ.get("CIDX_SSH_DIR")
        metadata_dir_env = os.environ.get("CIDX_SSH_METADATA_DIR")
        server_data_dir = os.environ.get("CIDX_SERVER_DATA_DIR", str(Path.home() / ".code-indexer-server"))

        # Use server data dir for metadata if not explicitly overridden
        if metadata_dir_env:
            metadata_dir = Path(metadata_dir_env)
        else:
            metadata_dir = Path(server_data_dir) / "ssh_keys"

        _ssh_key_manager = SSHKeyManager(
            ssh_dir=Path(ssh_dir) if ssh_dir else None,
            metadata_dir=metadata_dir,
        )
    return _ssh_key_manager


# Router
router = APIRouter(prefix="/api/ssh-keys", tags=["SSH Keys"])


def create_ssh_key(request: CreateKeyRequest) -> CreateKeyResponse:
    """
    Create a new SSH key pair.

    Returns the public key for copy/paste to git hosting providers.
    """
    manager = get_ssh_key_manager()

    try:
        metadata = manager.create_key(
            name=request.name,
            key_type=request.key_type,
            email=request.email,
            description=request.description,
        )

        return CreateKeyResponse(
            name=metadata.name,
            fingerprint=metadata.fingerprint,
            key_type=metadata.key_type,
            public_key=metadata.public_key or "",
            email=metadata.email,
            description=metadata.description,
        )

    except InvalidKeyNameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


def list_ssh_keys() -> KeyListResponse:
    """
    List all managed and unmanaged SSH keys.
    """
    manager = get_ssh_key_manager()
    result = manager.list_keys()

    managed = [
        KeyInfoResponse(
            name=k.name,
            fingerprint=k.fingerprint,
            key_type=k.key_type,
            hosts=k.hosts,
            email=k.email,
            description=k.description,
            is_imported=k.is_imported,
        )
        for k in result.managed
    ]

    unmanaged = [
        UnmanagedKeyResponse(
            name=k.name,
            fingerprint=k.fingerprint,
            private_path=str(k.private_path),
        )
        for k in result.unmanaged
    ]

    return KeyListResponse(managed=managed, unmanaged=unmanaged)


def delete_ssh_key(name: str) -> DeleteKeyResponse:
    """
    Delete an SSH key, its config entries, and metadata.

    This operation is idempotent - succeeds even if key doesn't exist.
    """
    manager = get_ssh_key_manager()
    manager.delete_key(name)
    return DeleteKeyResponse(success=True, message=f"Key '{name}' deleted")


def get_public_key(name: str) -> Response:
    """
    Get the public key content for copy/paste.

    Returns plain text suitable for adding to GitHub/GitLab.
    """
    manager = get_ssh_key_manager()

    try:
        public_key = manager.get_public_key(name)
        return Response(content=public_key, media_type="text/plain")
    except KeyNotFoundError:
        raise HTTPException(status_code=404, detail=f"Key not found: {name}")


def assign_host(name: str, request: AssignHostRequest) -> KeyWithHostsResponse:
    """
    Assign a host to an SSH key.

    Updates ~/.ssh/config with the new host mapping.
    """
    manager = get_ssh_key_manager()

    try:
        metadata = manager.assign_key_to_host(
            key_name=name,
            hostname=request.hostname,
            force=request.force,
        )

        return KeyWithHostsResponse(
            name=metadata.name,
            fingerprint=metadata.fingerprint,
            key_type=metadata.key_type,
            hosts=metadata.hosts,
            email=metadata.email,
            description=metadata.description,
        )

    except KeyNotFoundError:
        raise HTTPException(status_code=404, detail=f"Key not found: {name}")
    except HostConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


# Register routes with proper decorators
@router.post("", response_model=CreateKeyResponse, status_code=201)
async def api_create_ssh_key(request: CreateKeyRequest) -> CreateKeyResponse:
    """Create a new SSH key pair."""
    return create_ssh_key(request)


@router.get("", response_model=KeyListResponse)
async def api_list_ssh_keys() -> KeyListResponse:
    """List all managed and unmanaged SSH keys."""
    return list_ssh_keys()


@router.delete("/{name}", response_model=DeleteKeyResponse)
async def api_delete_ssh_key(name: str) -> DeleteKeyResponse:
    """Delete an SSH key."""
    return delete_ssh_key(name)


@router.get("/{name}/public")
async def api_get_public_key(name: str) -> Response:
    """Get public key content."""
    return get_public_key(name)


@router.post("/{name}/hosts", response_model=KeyWithHostsResponse)
async def api_assign_host(name: str, request: AssignHostRequest) -> KeyWithHostsResponse:
    """Assign a host to an SSH key."""
    return assign_host(name, request)
