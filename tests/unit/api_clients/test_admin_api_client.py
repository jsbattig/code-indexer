"""
Tests for AdminAPIClient with real CIDX server integration.

Following Foundation #1 compliance: Zero mocks, real server testing.
Tests admin user creation functionality with actual HTTP requests
and authentication flows using real CIDX server infrastructure.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from typing import Dict, Any

from code_indexer.api_clients.admin_client import AdminAPIClient
from code_indexer.api_clients.base_client import (
    APIClientError,
    AuthenticationError,
    NetworkError,
)
from tests.infrastructure.test_cidx_server import CIDXServerTestContext


class TestAdminAPIClientRealServer:
    """AdminAPIClient tests using real CIDX server - Foundation #1 compliant."""

    @pytest.fixture
    def test_server(self):
        """Start real CIDX server for testing."""

        async def _start_server():
            context = CIDXServerTestContext()
            server = await context.__aenter__()
            server.server_url = context.base_url  # Add server_url to server object
            return server, context

        async def _stop_server(context):
            await context.__aexit__(None, None, None)

        # Start server
        loop = asyncio.get_event_loop()
        server, context = loop.run_until_complete(_start_server())

        try:
            yield server
        finally:
            # Stop server
            loop.run_until_complete(_stop_server(context))

    @pytest.fixture
    def admin_credentials(self) -> Dict[str, Any]:
        """Admin credentials for testing."""
        return {
            "username": "admin",
            "password": "admin123",
        }

    @pytest.fixture
    def user_credentials(self) -> Dict[str, Any]:
        """Regular user credentials for testing."""
        return {
            "username": "testuser",
            "password": "testpass123",
        }

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    async def test_create_user_success_with_admin_credentials(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test successful user creation with admin credentials."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # Create a new user
            result = await admin_client.create_user(
                username="newuser",
                password="NewPass123!",
                role="normal_user",
            )

            # Verify response structure
            assert "user" in result
            user_info = result["user"]
            assert user_info["username"] == "newuser"
            assert user_info["role"] == "normal_user"
            assert "created_at" in user_info

        finally:
            await admin_client.close()

    async def test_create_user_insufficient_privileges_with_regular_user(
        self, test_server, user_credentials, temp_project_root
    ):
        """Test user creation fails with insufficient privileges."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=user_credentials,  # Non-admin user
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError) as exc_info:
                await admin_client.create_user(
                    username="unauthorizeduser",
                    password="Pass123!",
                    role="normal_user",
                )

            assert "admin role required" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_create_user_invalid_role(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test user creation fails with invalid role."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.create_user(
                    username="invalidroleuser",
                    password="Pass123!",
                    role="invalid_role",
                )

            assert exc_info.value.status_code == 400
            assert "invalid" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_create_user_duplicate_username(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test user creation fails when username already exists."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # Create first user
            await admin_client.create_user(
                username="duplicateuser",
                password="Pass123!",
                role="normal_user",
            )

            # Attempt to create user with same username
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.create_user(
                    username="duplicateuser",
                    password="AnotherPass123!",
                    role="normal_user",
                )

            assert exc_info.value.status_code == 409
            assert "conflict" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_create_user_with_admin_role(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test creating user with admin role."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            result = await admin_client.create_user(
                username="newadmin",
                password="AdminPass123!",
                role="admin",
            )

            # Verify admin role assignment
            assert result["user"]["role"] == "admin"
            assert result["user"]["username"] == "newadmin"

        finally:
            await admin_client.close()

    async def test_create_user_with_power_user_role(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test creating user with power_user role."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            result = await admin_client.create_user(
                username="poweruser",
                password="PowerPass123!",
                role="power_user",
            )

            # Verify power_user role assignment
            assert result["user"]["role"] == "power_user"
            assert result["user"]["username"] == "poweruser"

        finally:
            await admin_client.close()

    async def test_list_users_success_with_admin_credentials(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test successful user listing with admin credentials."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # Create some test users first
            await admin_client.create_user("listuser1", "Pass123!", "normal_user")
            await admin_client.create_user("listuser2", "Pass123!", "power_user")

            # List users
            result = await admin_client.list_users(limit=10, offset=0)

            # Verify response structure
            assert "users" in result
            assert isinstance(result["users"], list)
            assert len(result["users"]) >= 2

            # Check for our created users
            usernames = [user["username"] for user in result["users"]]
            assert "listuser1" in usernames
            assert "listuser2" in usernames

            # Verify user data structure
            for user in result["users"]:
                assert "username" in user
                assert "role" in user
                assert "created_at" in user

        finally:
            await admin_client.close()

    async def test_list_users_with_pagination(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test user listing with pagination parameters."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # Create multiple test users
            for i in range(5):
                await admin_client.create_user(
                    f"pageuser{i}", "Pass123!", "normal_user"
                )

            # Test pagination
            result = await admin_client.list_users(limit=2, offset=0)
            assert "users" in result
            assert len(result["users"]) <= 2

            # Test offset
            result2 = await admin_client.list_users(limit=2, offset=2)
            assert "users" in result2
            assert len(result2["users"]) <= 2

            # Verify different users returned
            usernames1 = [user["username"] for user in result["users"]]
            usernames2 = [user["username"] for user in result2["users"]]
            # Should have different users (though some overlap is possible)
            assert usernames1 != usernames2 or len(set(usernames1 + usernames2)) > 2

        finally:
            await admin_client.close()

    async def test_list_users_insufficient_privileges_with_regular_user(
        self, test_server, user_credentials, temp_project_root
    ):
        """Test user listing fails with insufficient privileges."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=user_credentials,  # Non-admin user
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError) as exc_info:
                await admin_client.list_users(limit=10, offset=0)

            assert "admin role required" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_authentication_error_with_invalid_credentials(
        self, test_server, temp_project_root
    ):
        """Test authentication fails with invalid credentials."""
        invalid_credentials = {
            "username": "nonexistent",
            "password": "wrongpass",
        }

        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=invalid_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError):
                await admin_client.create_user(
                    username="shouldfail",
                    password="Pass123!",
                    role="normal_user",
                )

        finally:
            await admin_client.close()

    async def test_network_error_with_invalid_server_url(
        self, admin_credentials, temp_project_root
    ):
        """Test network error handling with invalid server URL."""
        admin_client = AdminAPIClient(
            server_url="http://nonexistent.invalid:9999",
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises((NetworkError, APIClientError)):
                await admin_client.create_user(
                    username="networkfail",
                    password="Pass123!",
                    role="normal_user",
                )

        finally:
            await admin_client.close()

    def test_admin_client_initialization(self, admin_credentials, temp_project_root):
        """Test AdminAPIClient initialization."""
        admin_client = AdminAPIClient(
            server_url="https://test.example.com",
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        assert admin_client.server_url == "https://test.example.com"
        assert admin_client.credentials == admin_credentials
        assert admin_client.project_root == temp_project_root

    def test_admin_client_initialization_without_project_root(self, admin_credentials):
        """Test AdminAPIClient initialization without project root."""
        admin_client = AdminAPIClient(
            server_url="https://test.example.com",
            credentials=admin_credentials,
            project_root=None,
        )

        assert admin_client.server_url == "https://test.example.com"
        assert admin_client.credentials == admin_credentials
        assert admin_client.project_root is None

    # === User Management Operations Tests ===

    async def test_get_user_success_with_admin_credentials(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test successful user retrieval with admin credentials."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # First create a user to retrieve
            await admin_client.create_user(
                username="getuser",
                password="GetPass123!",
                role="power_user",
            )

            # Get the user details
            result = await admin_client.get_user("getuser")

            # Verify response structure
            assert "user" in result
            user_info = result["user"]
            assert user_info["username"] == "getuser"
            assert user_info["role"] == "power_user"
            assert "created_at" in user_info

        finally:
            await admin_client.close()

    async def test_get_user_not_found(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test get user fails when user doesn't exist."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.get_user("nonexistentuser")

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_get_user_insufficient_privileges_with_regular_user(
        self, test_server, user_credentials, temp_project_root
    ):
        """Test get user fails with insufficient privileges."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=user_credentials,  # Non-admin user
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError) as exc_info:
                await admin_client.get_user("someuser")

            assert "admin role required" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_update_user_success_with_admin_credentials(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test successful user update with admin credentials."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # First create a user to update
            await admin_client.create_user(
                username="updateuser",
                password="UpdatePass123!",
                role="normal_user",
            )

            # Update the user role
            result = await admin_client.update_user(
                username="updateuser",
                role="power_user",
            )

            # Verify update response
            assert "message" in result
            assert "updated" in result["message"].lower()

            # Verify the update worked by retrieving the user
            user_result = await admin_client.get_user("updateuser")
            assert user_result["user"]["role"] == "power_user"

        finally:
            await admin_client.close()

    async def test_update_user_not_found(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test update user fails when user doesn't exist."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.update_user(
                    username="nonexistentuser",
                    role="admin",
                )

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_update_user_invalid_role(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test update user fails with invalid role."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # First create a user to update
            await admin_client.create_user(
                username="invalidroleupdate",
                password="Pass123!",
                role="normal_user",
            )

            # Try to update with invalid role
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.update_user(
                    username="invalidroleupdate",
                    role="invalid_role",
                )

            assert exc_info.value.status_code == 400
            assert "invalid" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_update_user_insufficient_privileges_with_regular_user(
        self, test_server, user_credentials, temp_project_root
    ):
        """Test update user fails with insufficient privileges."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=user_credentials,  # Non-admin user
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError) as exc_info:
                await admin_client.update_user(
                    username="someuser",
                    role="admin",
                )

            assert "admin role required" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_delete_user_success_with_admin_credentials(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test successful user deletion with admin credentials."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # First create a user to delete
            await admin_client.create_user(
                username="deleteuser",
                password="DeletePass123!",
                role="normal_user",
            )

            # Delete the user
            result = await admin_client.delete_user("deleteuser")

            # Verify deletion response
            assert "message" in result
            assert "deleted" in result["message"].lower()

            # Verify the user is actually deleted
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.get_user("deleteuser")
            assert exc_info.value.status_code == 404

        finally:
            await admin_client.close()

    async def test_delete_user_not_found(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test delete user fails when user doesn't exist."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.delete_user("nonexistentuser")

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_delete_user_last_admin_prevention(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test deletion of last admin is prevented."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # Attempt to delete the admin user (should be prevented by server)
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.delete_user("admin")

            assert exc_info.value.status_code == 400
            assert "admin" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_delete_user_insufficient_privileges_with_regular_user(
        self, test_server, user_credentials, temp_project_root
    ):
        """Test delete user fails with insufficient privileges."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=user_credentials,  # Non-admin user
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError) as exc_info:
                await admin_client.delete_user("someuser")

            assert "admin role required" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    # === Password Management Operations Tests ===

    async def test_change_user_password_success_with_admin_credentials(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test successful user password change with admin credentials."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # First create a user whose password we'll change
            await admin_client.create_user(
                username="pwdchangeuser",
                password="OldPass123!",
                role="normal_user",
            )

            # Change the user's password
            result = await admin_client.change_user_password(
                username="pwdchangeuser",
                new_password="NewPass456!",
            )

            # Verify change response
            assert "message" in result
            assert "password changed successfully" in result["message"].lower()
            assert "pwdchangeuser" in result["message"]

        finally:
            await admin_client.close()

    async def test_change_user_password_user_not_found(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test change password fails when user doesn't exist."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.change_user_password(
                    username="nonexistentuser",
                    new_password="NewPass123!",
                )

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_change_user_password_insufficient_privileges_with_regular_user(
        self, test_server, user_credentials, temp_project_root
    ):
        """Test change password fails with insufficient privileges."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=user_credentials,  # Non-admin user
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError) as exc_info:
                await admin_client.change_user_password(
                    username="someuser",
                    new_password="NewPass123!",
                )

            assert "admin role required" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_change_user_password_invalid_password_validation(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test change password fails with invalid password."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # First create a user whose password we'll try to change
            await admin_client.create_user(
                username="pwdvalidationuser",
                password="ValidPass123!",
                role="normal_user",
            )

            # Try to change password to empty string
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.change_user_password(
                    username="pwdvalidationuser",
                    new_password="",
                )

            assert exc_info.value.status_code == 400
            assert "password" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    async def test_change_user_password_admin_user_allowed(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test admin can change another admin user's password."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # First create an admin user whose password we'll change
            await admin_client.create_user(
                username="pwdadminuser",
                password="AdminPass123!",
                role="admin",
            )

            # Change the admin user's password
            result = await admin_client.change_user_password(
                username="pwdadminuser",
                new_password="NewAdminPass456!",
            )

            # Verify change response
            assert "message" in result
            assert "password changed successfully" in result["message"].lower()
            assert "pwdadminuser" in result["message"]

        finally:
            await admin_client.close()
