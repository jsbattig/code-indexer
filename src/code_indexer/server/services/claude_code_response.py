"""
Claude Code Response Protocol for SCIP Self-Healing.

Defines response structure and validation for Claude Code integration.
Ensures pr_description field meets requirements for PR creation.

Story #659: Git State Management for SCIP Self-Healing with PR Workflow
AC4: Enhanced Claude Code Response Protocol
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


class ResponseValidationError(Exception):
    """Raised when Claude Code response fails validation."""

    pass


@dataclass
class ClaudeCodeResponse:
    """
    Response from Claude Code after SCIP fix attempt.

    Attributes:
        success: Whether the fix was successful
        message: Human-readable status message
        files_modified: List of file paths that were modified
        pr_description: Concise summary for PR title (max 100 chars)
    """

    success: bool
    message: str
    files_modified: List[Path] = field(default_factory=list)
    pr_description: str = ""

    MAX_PR_DESCRIPTION_LENGTH = 100

    def __post_init__(self):
        """Validate response after initialization."""
        # Validate pr_description length
        if len(self.pr_description) > self.MAX_PR_DESCRIPTION_LENGTH:
            raise ResponseValidationError(
                f"pr_description exceeds maximum length of {self.MAX_PR_DESCRIPTION_LENGTH} chars: "
                f"got {len(self.pr_description)} chars"
            )

        # Convert strings to Path objects if needed
        if self.files_modified:
            self.files_modified = [
                Path(f) if isinstance(f, str) else f for f in self.files_modified
            ]

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize response to dictionary.

        Returns:
            Dictionary representation with Path objects converted to strings
        """
        return {
            "success": self.success,
            "message": self.message,
            "files_modified": [str(f) for f in self.files_modified],
            "pr_description": self.pr_description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClaudeCodeResponse":
        """
        Deserialize response from dictionary.

        Args:
            data: Dictionary with response fields

        Returns:
            ClaudeCodeResponse instance

        Raises:
            ResponseValidationError: If validation fails
        """
        # Convert file paths from strings to Path objects
        files_modified = [Path(f) for f in data.get("files_modified", [])]

        return cls(
            success=data["success"],
            message=data["message"],
            files_modified=files_modified,
            pr_description=data.get("pr_description", ""),
        )
