"""
Activated Repository model for CIDX Server.

Represents metadata for user-activated repositories, supporting both single
and composite repository configurations.
"""

from typing import List
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field


class ActivatedRepository(BaseModel):
    """
    Model representing an activated repository's metadata.

    Supports both single repository activation and composite repository
    activation with proper tracking of state and configuration.
    """

    user_alias: str = Field(..., description="User's alias for the repository")
    username: str = Field(..., description="Username who activated the repository")
    path: Path = Field(..., description="Filesystem path to activated repository")
    activated_at: datetime = Field(
        ..., description="Timestamp when repository was activated"
    )
    last_accessed: datetime = Field(..., description="Timestamp of last access")

    # Single repository fields (optional for composite repos)
    golden_repo_alias: str = Field(
        default="", description="Golden repository alias (single repo only)"
    )
    current_branch: str = Field(
        default="main", description="Current branch (single repo only)"
    )

    # Composite repository fields (NEW in Story 1.3)
    is_composite: bool = Field(
        default=False, description="Whether this is a composite repository"
    )
    golden_repo_aliases: List[str] = Field(
        default_factory=list, description="List of golden repo aliases (composite only)"
    )
    discovered_repos: List[str] = Field(
        default_factory=list,
        description="List of discovered repository paths (composite only)",
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat(), Path: lambda v: str(v)}

    def to_dict(self) -> dict:
        """
        Convert to dictionary representation.

        Returns:
            Dictionary with all fields serialized
        """
        return {
            "user_alias": self.user_alias,
            "username": self.username,
            "path": str(self.path),
            "activated_at": self.activated_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "golden_repo_alias": self.golden_repo_alias,
            "current_branch": self.current_branch,
            "is_composite": self.is_composite,
            "golden_repo_aliases": self.golden_repo_aliases,
            "discovered_repos": self.discovered_repos,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActivatedRepository":
        """
        Create instance from dictionary.

        Args:
            data: Dictionary with model fields

        Returns:
            ActivatedRepository instance
        """
        # Parse datetime fields
        if isinstance(data.get("activated_at"), str):
            data["activated_at"] = datetime.fromisoformat(data["activated_at"])
        if isinstance(data.get("last_accessed"), str):
            data["last_accessed"] = datetime.fromisoformat(data["last_accessed"])

        # Parse Path field
        if isinstance(data.get("path"), str):
            data["path"] = Path(data["path"])

        return cls(**data)
