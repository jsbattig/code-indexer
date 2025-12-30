"""
Search Limits Configuration Model.

Defines configuration for search timeout and result size limits.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any


class SearchLimitsConfig(BaseModel):
    """
    Configuration for search operation limits.

    Attributes:
        max_result_size_mb: Maximum result size in megabytes (1-100)
        timeout_seconds: Maximum execution time in seconds (5-300)
    """

    max_result_size_mb: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Maximum result size in megabytes",
    )

    timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Maximum execution time in seconds",
    )

    @property
    def max_size_bytes(self) -> int:
        """
        Get maximum size in bytes.

        Returns:
            Maximum size in bytes
        """
        return self.max_result_size_mb * 1024 * 1024

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary representation.

        Returns:
            Dictionary with configuration fields
        """
        return {
            "max_result_size_mb": self.max_result_size_mb,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchLimitsConfig":
        """
        Create instance from dictionary.

        Args:
            data: Dictionary with configuration fields

        Returns:
            SearchLimitsConfig instance
        """
        return cls(**data)
