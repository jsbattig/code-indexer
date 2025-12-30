"""
File Content Limits Configuration Model.

Defines configuration for file content token limits and character-to-token ratios.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any


class FileContentLimitsConfig(BaseModel):
    """
    Configuration for file content token limits.

    Attributes:
        max_tokens_per_request: Maximum tokens per request (1000-20000)
        chars_per_token: Average characters per token ratio (3-5)
    """

    max_tokens_per_request: int = Field(
        default=5000,
        ge=1000,
        le=20000,
        description="Maximum tokens per request",
    )

    chars_per_token: int = Field(
        default=4,
        ge=3,
        le=5,
        description="Average characters per token ratio",
    )

    @property
    def max_chars_per_request(self) -> int:
        """
        Get maximum characters per request.

        Returns:
            Maximum characters calculated from tokens * chars_per_token
        """
        return self.max_tokens_per_request * self.chars_per_token

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary representation.

        Returns:
            Dictionary with configuration fields
        """
        return {
            "max_tokens_per_request": self.max_tokens_per_request,
            "chars_per_token": self.chars_per_token,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileContentLimitsConfig":
        """
        Create instance from dictionary.

        Args:
            data: Dictionary with configuration fields

        Returns:
            FileContentLimitsConfig instance
        """
        return cls(**data)
