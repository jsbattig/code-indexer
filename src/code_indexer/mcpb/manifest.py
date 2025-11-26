"""Manifest data models for binary distribution.

This module defines the data structures for describing cross-platform
binary distributions of the MCP Bridge.
"""

import hashlib
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Platform(str, Enum):
    """Supported platform identifiers."""

    DARWIN_X64 = "darwin-x64"
    DARWIN_ARM64 = "darwin-arm64"
    LINUX_X64 = "linux-x64"
    WINDOWS_X64 = "windows-x64"


class BinaryMetadata(BaseModel):
    """Metadata for a platform-specific binary.

    Attributes:
        binary: Binary filename (e.g., "mcpb-darwin-x64")
        sha256: SHA256 checksum (64 hex characters)
        size: File size in bytes
    """

    binary: str = Field(..., description="Binary filename")
    sha256: str = Field(..., description="SHA256 checksum (64 hex chars)")
    size: int = Field(..., ge=0, description="File size in bytes")

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        """Validate SHA256 is 64 hex characters."""
        if len(v) != 64:
            raise ValueError(f"SHA256 must be 64 hex characters, got {len(v)}")
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("SHA256 must contain only hex characters")
        return v.lower()


class PlatformManifest(BaseModel):
    """Manifest describing binaries for all platforms.

    Attributes:
        name: Package name
        version: Version string (semver)
        description: Package description
        mcp_version: MCP protocol version
        platforms: Platform-specific binary metadata
        configuration: MCP configuration template
    """

    name: str = Field(..., description="Package name")
    version: str = Field(..., description="Version string")
    description: str = Field(..., description="Package description")
    mcp_version: str = Field(default="2024-11-05", description="MCP protocol version")
    platforms: dict[Platform, BinaryMetadata] = Field(
        default_factory=dict, description="Platform-specific binaries"
    )
    configuration: dict[str, Any] = Field(
        default_factory=dict, description="MCP configuration template"
    )

    model_config = ConfigDict(use_enum_values=True)


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 checksum of a file.

    Args:
        file_path: Path to file

    Returns:
        SHA256 checksum as hex string (64 characters)

    Raises:
        FileNotFoundError: If file does not exist
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    sha256_hash = hashlib.sha256()

    # Read file in chunks to handle large files
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest()
