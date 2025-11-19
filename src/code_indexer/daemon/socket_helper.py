"""Socket path management for daemon mode.

This module provides utilities for generating and managing daemon socket paths
that avoid Unix socket path length limitations (108 chars) by using a hash-based
naming scheme in /tmp/cidx/.
"""

import hashlib
import os
from pathlib import Path
from typing import Literal, Optional

SocketMode = Literal["shared", "user"]


def generate_repo_hash(repo_path: Path) -> str:
    """Generate deterministic 16-char hash from repository path.

    Args:
        repo_path: Path to repository

    Returns:
        16-character hexadecimal hash string
    """
    resolved = str(repo_path.resolve())
    hash_obj = hashlib.sha256(resolved.encode())
    return hash_obj.hexdigest()[:16]


def get_socket_directory(mode: SocketMode = "shared") -> Path:
    """Get base directory for daemon sockets.

    Args:
        mode: "shared" for multi-user (/tmp/cidx) or "user" for single-user

    Returns:
        Path to socket directory
    """
    if mode == "shared":
        return Path("/tmp/cidx")
    else:  # user mode
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if runtime_dir:
            return Path(runtime_dir) / "cidx"
        return Path("/tmp/cidx")  # fallback


def ensure_socket_directory(socket_dir: Path, mode: SocketMode = "shared") -> None:
    """Create socket directory with proper permissions.

    Args:
        socket_dir: Directory to create
        mode: "shared" (1777 permissions) or "user" (700 permissions)
    """
    permissions = 0o1777 if mode == "shared" else 0o700

    # Try to create directory (only works if doesn't exist or we own it)
    try:
        socket_dir.mkdir(mode=permissions, parents=True, exist_ok=True)
    except FileExistsError:
        pass  # Directory exists, that's fine

    # Only chmod if we own the directory (avoid EPERM errors)
    if socket_dir.exists():
        try:
            socket_dir.chmod(permissions)
        except PermissionError:
            # Can't chmod (don't own directory), but that's fine if permissions are already correct
            # In shared mode with sticky bit, users can still create sockets even if they don't own the dir
            pass


def generate_socket_path(repo_path: Path, mode: SocketMode = "shared") -> Path:
    """Generate deterministic socket path for repository.

    This generates a socket path that is guaranteed to be under 108 characters
    by using a hash-based naming scheme in /tmp/cidx/.

    Args:
        repo_path: Path to repository
        mode: Socket mode ("shared" or "user")

    Returns:
        Path to socket file (e.g., /tmp/cidx/{hash}.sock)
    """
    repo_hash = generate_repo_hash(repo_path)
    socket_dir = get_socket_directory(mode)
    ensure_socket_directory(socket_dir, mode)
    return socket_dir / f"{repo_hash}.sock"


def create_mapping_file(repo_path: Path, socket_path: Path) -> None:
    """Create mapping file linking socket to repository.

    Creates a .repo-path file alongside the socket that contains
    the full path to the repository for debugging purposes.

    CRITICAL: Sets mode 664 (group writable) for multi-user /tmp/cidx/ with setgid.
    When /tmp/cidx has setgid bit, new files inherit the directory's group,
    and mode 664 allows group members to read/write the file.

    Args:
        repo_path: Path to repository
        socket_path: Path to socket file
    """
    mapping_path = socket_path.with_suffix(".repo-path")
    try:
        # CRITICAL: Set umask to 002 so files are created with group-write by default
        # This ensures write_text() creates the file as 664 (rw-rw-r--) instead of 644
        old_umask = os.umask(0o002)
        try:
            mapping_path.write_text(str(repo_path.resolve()))
            # Explicitly set permissions to be sure (in case umask didn't work)
            mapping_path.chmod(0o664)
        finally:
            # Always restore original umask
            os.umask(old_umask)
    except (PermissionError, OSError):
        # Mapping file write/chmod failed (may exist from different user with restrictive perms)
        # This is non-critical - mapping is only for debugging
        pass


def get_repo_from_mapping(socket_path: Path) -> Optional[Path]:
    """Retrieve repository path from mapping file.

    Args:
        socket_path: Path to socket file

    Returns:
        Path to repository if mapping exists, None otherwise
    """
    mapping_path = socket_path.with_suffix(".repo-path")
    if mapping_path.exists():
        return Path(mapping_path.read_text().strip())
    return None


def cleanup_old_socket(repo_path: Path) -> None:
    """Remove old socket from .code-indexer/ directory.

    This cleans up the legacy socket location used before the
    migration to /tmp/cidx/.

    Args:
        repo_path: Path to repository
    """
    old_socket = repo_path / ".code-indexer" / "daemon.sock"
    if old_socket.exists():
        old_socket.unlink()
