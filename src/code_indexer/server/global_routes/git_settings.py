"""
REST API routes for Git service settings management.

Provides REST endpoints for:
- Getting current git service configuration
- Updating git service configuration (default_committer_email)

Story #641 AC #6: Web UI & REST API for default_committer_email configuration.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from code_indexer.config import ConfigManager
from code_indexer.server.auth.dependencies import get_current_user_web_or_api
from code_indexer.server.auth.user_manager import User


# Router with /settings prefix under /api
router = APIRouter(prefix="/settings", tags=["settings"])


# Request/response models
class GitServiceConfigResponse(BaseModel):
    """Response model for git service configuration."""

    service_committer_name: str = Field(
        description="Service account name for Git committer"
    )
    service_committer_email: str = Field(
        description="Service account email (must match SSH key owner)"
    )
    default_committer_email: Optional[str] = Field(
        description="Fallback email used when no SSH key authenticates to remote"
    )


class GitServiceConfigUpdate(BaseModel):
    """Request model for updating git service configuration."""

    default_committer_email: Optional[str] = Field(
        description="Fallback email used when no SSH key authenticates to remote"
    )

    @field_validator("default_committer_email")
    @classmethod
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        # Allow None
        if v is None:
            return v

        # Whitespace-only treated as invalid
        if isinstance(v, str) and v.strip() == "":
            raise ValueError("Email cannot be empty or whitespace-only")

        import re

        # RFC 5322 compliant basic validation
        email_pattern = re.compile(
            r"^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@"
            r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
            r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
        )

        if not email_pattern.match(v):
            raise ValueError(
                f"Invalid email format: {v}. "
                "Must be valid RFC 5322 email address (e.g., user@example.com)"
            )

        return v


def _get_config_manager() -> ConfigManager:
    """
    Get ConfigManager instance for accessing CIDX config.

    Returns:
        ConfigManager configured with default .code-indexer/config.json path

    Note: This looks for config in the current working directory's .code-indexer/
    directory. For server context, this should be the golden repos directory or
    a configured server data directory.
    """
    # Use default config path (.code-indexer/config.json)
    # In server context, cwd should be set appropriately
    return ConfigManager()


@router.get("/git", response_model=GitServiceConfigResponse)
def get_git_settings(
    current_user: User = Depends(get_current_user_web_or_api),
) -> GitServiceConfigResponse:
    """
    Get current git service configuration.

    Requires authentication. Returns current git service settings including
    service_committer_name, service_committer_email, and default_committer_email.

    Args:
        current_user: Authenticated user (injected by dependency)

    Returns:
        GitServiceConfigResponse with current settings

    Raises:
        HTTPException: 401 if not authenticated (handled by dependency)
    """
    config_manager = _get_config_manager()
    config = config_manager.load()

    return GitServiceConfigResponse(
        service_committer_name=config.git_service.service_committer_name,
        service_committer_email=config.git_service.service_committer_email,
        default_committer_email=config.git_service.default_committer_email,
    )


@router.put("/git", response_model=GitServiceConfigResponse)
def update_git_settings(
    updates: GitServiceConfigUpdate,
    current_user: User = Depends(get_current_user_web_or_api),
) -> GitServiceConfigResponse:
    """
    Update git service configuration.

    Requires authentication. Updates default_committer_email and persists to
    config.json. Other fields (service_committer_name, service_committer_email)
    remain unchanged.

    Args:
        updates: Git service configuration updates
        current_user: Authenticated user (injected by dependency)

    Returns:
        GitServiceConfigResponse with updated settings

    Raises:
        HTTPException: 401 if not authenticated (handled by dependency)
        HTTPException: 422 if email validation fails (handled by Pydantic)
    """
    config_manager = _get_config_manager()
    config = config_manager.load()

    # Update only the default_committer_email field
    config.git_service.default_committer_email = updates.default_committer_email

    # Save the updated config
    config_manager.save(config)

    return GitServiceConfigResponse(
        service_committer_name=config.git_service.service_committer_name,
        service_committer_email=config.git_service.service_committer_email,
        default_committer_email=config.git_service.default_committer_email,
    )
