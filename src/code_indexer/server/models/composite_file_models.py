"""
Composite repository file listing models.

Models for representing file information in composite repositories,
supporting Story 3.3 of the Server Composite Repository Activation epic.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """
    File information for composite repository listing.

    Represents a single file or directory entry with metadata,
    including which component repository it belongs to.
    """

    full_path: str = Field(
        ...,
        description="Full path including component repo (e.g., 'backend-api/src/main.py')",
    )
    name: str = Field(..., description="File or directory name (e.g., 'main.py')")
    size: int = Field(..., description="File size in bytes (0 for directories)")
    modified: datetime = Field(..., description="Last modification timestamp")
    is_directory: bool = Field(..., description="Whether this is a directory")
    component_repo: str = Field(
        ..., description="Which component repository this file belongs to"
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}
