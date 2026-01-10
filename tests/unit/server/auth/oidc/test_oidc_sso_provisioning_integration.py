"""
Integration tests for OIDC Manager with SSO Provisioning Hook.

Story #708: SSO Auto-Provisioning with Default Group Assignment

Tests for verifying OIDCManager integrates with SSOProvisioningHook:
- AC5: Provisioning occurs before first query (during match_or_create_user)
- Integration between OIDC authentication and group-based access control

TDD: These tests are written to verify the integration is in place.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock

from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.utils.config_manager import OIDCProviderConfig
from code_indexer.server.services.group_access_manager import GroupAccessManager


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for OIDC."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def group_db_path():
    """Create a temporary database file for groups."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def group_manager(group_db_path):
    """Create a GroupAccessManager instance."""
    return GroupAccessManager(group_db_path)


@pytest.fixture
def jit_config():
    """OIDC config with JIT provisioning enabled."""
    return OIDCProviderConfig(
        enabled=True,
        enable_jit_provisioning=True,
        default_role="normal_user",
    )


@pytest.fixture
def mock_user_manager_for_new_user():
    """Mock user_manager that returns None (new user scenario)."""
    user_manager = Mock()
    user_manager.get_user.return_value = None
    user_manager.get_user_by_email.return_value = None
    return user_manager


def create_test_user(username: str, role: UserRole = UserRole.NORMAL_USER) -> User:
    """Helper to create a test User object."""
    return User(
        username=username,
        password_hash="",
        role=role,
        created_at=datetime.now(timezone.utc),
    )


def create_user_info(subject: str, email: str, username: str = None) -> OIDCUserInfo:
    """Helper to create OIDCUserInfo for tests."""
    return OIDCUserInfo(
        subject=subject,
        email=email,
        email_verified=True,
        username=username,
    )


class TestOIDCManagerSSOProvisioningIntegration:
    """Tests for OIDCManager integration with SSO provisioning."""

    @pytest.mark.asyncio
    async def test_new_jit_user_gets_group_assignment(
        self, temp_db_path, group_manager, jit_config, mock_user_manager_for_new_user
    ):
        """Test that a new JIT-provisioned user is assigned to users group."""
        new_user = create_test_user("jit-newuser")
        mock_user_manager_for_new_user.create_oidc_user.return_value = new_user

        manager = OIDCManager(jit_config, mock_user_manager_for_new_user, None)
        manager.db_path = str(temp_db_path)
        manager.group_manager = group_manager

        await manager._init_db()

        user_info = create_user_info(
            "new-subject-123", "jit-newuser@example.com", "jit-newuser"
        )
        user = await manager.match_or_create_user(user_info)

        assert user.username == "jit-newuser"

        user_group = group_manager.get_user_group("jit-newuser")
        assert user_group is not None
        assert user_group.name == "users"

        membership = group_manager.get_user_membership("jit-newuser")
        assert membership.assigned_by == "system:sso-provisioning"

    @pytest.mark.asyncio
    async def test_existing_linked_user_group_not_changed(
        self, temp_db_path, group_manager
    ):
        """Test that existing user's group is not changed on re-login."""
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group("existing-admin", admins.id, "manual-admin")

        config = OIDCProviderConfig(enabled=True)
        existing_user = create_test_user("existing-admin", UserRole.ADMIN)
        user_manager = Mock()
        user_manager.get_user.return_value = existing_user

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(temp_db_path)
        manager.group_manager = group_manager

        await manager._init_db()
        await manager.link_oidc_identity(
            "existing-admin", "existing-subject-456", "admin@example.com"
        )

        user_info = create_user_info("existing-subject-456", "admin@example.com")
        user = await manager.match_or_create_user(user_info)

        assert user.username == "existing-admin"

        user_group = group_manager.get_user_group("existing-admin")
        assert user_group.name == "admins"

        membership = group_manager.get_user_membership("existing-admin")
        assert membership.assigned_by == "manual-admin"
