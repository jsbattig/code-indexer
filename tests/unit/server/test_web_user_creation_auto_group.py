"""
Unit tests for Web UI User Creation with Auto Group Assignment.

Story #710: Admin User and Group Management Interface

This file covers:
- When creating users via web UI, they are auto-assigned to appropriate groups
- Admin role users -> admins group
- Non-admin role users -> users group

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from code_indexer.server.services.group_access_manager import GroupAccessManager
from code_indexer.server.auth.user_manager import UserRole


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def group_manager(temp_db_path):
    """Create a GroupAccessManager instance."""
    return GroupAccessManager(temp_db_path)


@pytest.fixture
def mock_user_manager():
    """Create a mock user manager."""
    user_manager = MagicMock()
    user_manager.create_user = MagicMock()
    return user_manager


@pytest.fixture
def mock_admin_session():
    """Create a mock admin session."""
    session = MagicMock()
    session.username = "admin_user"
    session.role = "admin"
    return session


class TestWebUserCreationAutoGroupAssignment:
    """
    Test that users created via web UI are auto-assigned to groups.

    - Admin users -> admins group
    - Non-admin users -> users group
    """

    def test_create_admin_user_assigns_to_admins_group(
        self, group_manager, mock_user_manager, mock_admin_session
    ):
        """Test creating an admin user via web UI assigns them to admins group."""
        from code_indexer.server.web import routes
        from code_indexer.server.auth import dependencies

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(routes.web_router)

        app.state.group_manager = group_manager

        original_user_manager = dependencies.user_manager
        dependencies.user_manager = mock_user_manager

        with patch.object(
            routes, "_require_admin_session", return_value=mock_admin_session
        ):
            with patch.object(routes, "validate_login_csrf_token", return_value=True):
                with patch.object(
                    routes, "_create_users_page_response"
                ) as mock_response:
                    mock_response.return_value = HTMLResponse(content="OK")

                    with patch.object(
                        routes, "_get_group_manager", return_value=group_manager
                    ):
                        client = TestClient(app)

                        client.post(
                            "/users/create",
                            data={
                                "new_username": "new_admin",
                                "new_password": "password123",
                                "confirm_password": "password123",
                                "role": "admin",
                                "csrf_token": "valid_token",
                            },
                        )

        dependencies.user_manager = original_user_manager

        mock_user_manager.create_user.assert_called_once_with(
            "new_admin", "password123", UserRole.ADMIN
        )

        admins_group = group_manager.get_group_by_name("admins")
        membership = group_manager.get_user_membership("new_admin")
        assert membership is not None, "User should be assigned to a group"
        assert membership.group_id == admins_group.id

    def test_create_regular_user_assigns_to_users_group(
        self, group_manager, mock_user_manager, mock_admin_session
    ):
        """Test creating a regular user via web UI assigns them to users group."""
        from code_indexer.server.web import routes
        from code_indexer.server.auth import dependencies

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.include_router(routes.web_router)

        app.state.group_manager = group_manager

        original_user_manager = dependencies.user_manager
        dependencies.user_manager = mock_user_manager

        with patch.object(
            routes, "_require_admin_session", return_value=mock_admin_session
        ):
            with patch.object(routes, "validate_login_csrf_token", return_value=True):
                with patch.object(
                    routes, "_create_users_page_response"
                ) as mock_response:
                    mock_response.return_value = HTMLResponse(content="OK")

                    with patch.object(
                        routes, "_get_group_manager", return_value=group_manager
                    ):
                        client = TestClient(app)

                        client.post(
                            "/users/create",
                            data={
                                "new_username": "new_user",
                                "new_password": "password123",
                                "confirm_password": "password123",
                                "role": "normal_user",
                                "csrf_token": "valid_token",
                            },
                        )

        dependencies.user_manager = original_user_manager

        mock_user_manager.create_user.assert_called_once_with(
            "new_user", "password123", UserRole.NORMAL_USER
        )

        users_group = group_manager.get_group_by_name("users")
        membership = group_manager.get_user_membership("new_user")
        assert membership is not None, "User should be assigned to a group"
        assert membership.group_id == users_group.id
