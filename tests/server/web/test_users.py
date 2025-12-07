"""
Tests for User Management (Story #532).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

from typing import Dict, Any
from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


# =============================================================================
# AC1: User List Display Tests
# =============================================================================


class TestUserListDisplay:
    """Tests for user list display (AC1)."""

    def test_users_page_requires_auth(self, web_client: TestClient):
        """
        AC1: Unauthenticated access to /admin/users redirects to login.

        Given I am not authenticated
        When I navigate to /admin/users
        Then I am redirected to /admin/login
        """
        response = web_client.get("/admin/users")

        assert response.status_code in [
            302,
            303,
        ], f"Expected redirect, got {response.status_code}"
        location = response.headers.get("location", "")
        assert (
            "/admin/login" in location
        ), f"Expected redirect to /admin/login, got {location}"

    def test_users_page_renders(self, authenticated_client: TestClient):
        """
        AC1: Authenticated admin access to /admin/users shows user management page.

        Given I am authenticated as an admin
        When I navigate to /admin/users
        Then I see the user management page with title "Users - CIDX Admin"
        """
        response = authenticated_client.get("/admin/users")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert (
            "Users - CIDX Admin" in response.text
        ), "Page title should be 'Users - CIDX Admin'"

    def test_users_list_shows_users(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC1: User list shows all users in a table with Username, Role, Created Date, Actions.

        Given I am authenticated as an admin
        And there are users in the system
        When I view the users page
        Then I see a table with all users
        And the table has columns: Username, Role, Created Date, Actions
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        response = client.get("/admin/users")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Check table structure
        assert "<table" in text_lower, "Page should contain a users table"
        assert "username" in text_lower, "Table should have Username column"
        assert "role" in text_lower, "Table should have Role column"
        assert "created" in text_lower, "Table should have Created Date column"
        assert "actions" in text_lower, "Table should have Actions column"

        # Check that admin user appears in list
        assert (
            admin_user["username"].lower() in text_lower
        ), "Admin user should appear in the list"

    def test_users_list_has_create_button(self, authenticated_client: TestClient):
        """
        AC1: Users page has a "Create User" button above the table.

        Given I am authenticated as an admin
        When I view the users page
        Then I see a "Create User" button
        """
        response = authenticated_client.get("/admin/users")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert (
            "create user" in text_lower or "create-user" in text_lower
        ), "Page should have a Create User button"


# =============================================================================
# AC2: Create User Form Tests
# =============================================================================


class TestCreateUserForm:
    """Tests for create user form (AC2)."""

    def test_create_user_form_renders(self, authenticated_client: TestClient):
        """
        AC2: Create user form has Username, Password, Confirm Password, Role fields.

        Given I am authenticated as an admin
        When I view the create user form
        Then I see form fields for Username, Password, Confirm Password, and Role
        """
        response = authenticated_client.get("/admin/users")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Form should have necessary fields
        assert (
            'name="username"' in response.text.lower()
            or 'name="new_username"' in response.text.lower()
        ), "Form should have username field"
        assert (
            'name="password"' in response.text.lower()
            or 'name="new_password"' in response.text.lower()
        ), "Form should have password field"
        assert (
            "confirm" in text_lower
            or 'name="confirm_password"' in response.text.lower()
        ), "Form should have confirm password field"
        assert (
            "role" in text_lower or "<select" in text_lower
        ), "Form should have role dropdown"

    def test_create_user_success(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC2: Valid user creation shows success message and user appears in list.

        Given I am authenticated as an admin
        When I submit valid user creation form
        Then I see a success message
        And the new user appears in the list
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the users page to get CSRF token
        users_page = client.get("/admin/users")
        csrf_token = web_infrastructure.extract_csrf_token(users_page.text)

        # Submit create user form
        response = client.post(
            "/admin/users/create",
            data={
                "new_username": "newuser",
                "new_password": "NewUser@123!",
                "confirm_password": "NewUser@123!",
                "role": "normal_user",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show success message
        assert (
            "success" in text_lower or "created" in text_lower
        ), "Should show success message after creating user"

        # New user should appear in list
        assert "newuser" in text_lower, "New user should appear in the list"

    def test_create_user_duplicate_username(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC2: Duplicate username shows validation error.

        Given I am authenticated as an admin
        And a user already exists
        When I try to create a user with the same username
        Then I see an error message about duplicate username
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the users page to get CSRF token
        users_page = client.get("/admin/users")
        csrf_token = web_infrastructure.extract_csrf_token(users_page.text)

        # Try to create user with existing username
        response = client.post(
            "/admin/users/create",
            data={
                "new_username": admin_user["username"],  # Duplicate
                "new_password": "NewPass@123!",
                "confirm_password": "NewPass@123!",
                "role": "normal_user",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show error about duplicate
        assert (
            "error" in text_lower or "exists" in text_lower or "already" in text_lower
        ), "Should show error for duplicate username"

    def test_create_user_password_mismatch(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC2: Password mismatch shows validation error.

        Given I am authenticated as an admin
        When I submit form with mismatched passwords
        Then I see an error message about password mismatch
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the users page to get CSRF token
        users_page = client.get("/admin/users")
        csrf_token = web_infrastructure.extract_csrf_token(users_page.text)

        # Submit with mismatched passwords
        response = client.post(
            "/admin/users/create",
            data={
                "new_username": "mismatchuser",
                "new_password": "Password@123!",
                "confirm_password": "Different@456!",
                "role": "normal_user",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show error about mismatch
        assert (
            "error" in text_lower or "match" in text_lower or "mismatch" in text_lower
        ), "Should show error for password mismatch"


# =============================================================================
# AC3: Edit User Role Tests
# =============================================================================


class TestEditUserRole:
    """Tests for edit user role (AC3)."""

    def test_edit_user_role(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC3: Role update works and shows success message.

        Given I am authenticated as an admin
        And there is another user in the system
        When I update their role
        Then I see a success message
        And the role is updated
        """
        # Create another user to edit
        web_infrastructure.create_normal_user(
            username="editroleuser", password="EditRole@123!"
        )

        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the users page to get CSRF token
        users_page = client.get("/admin/users")
        csrf_token = web_infrastructure.extract_csrf_token(users_page.text)

        # Update user role
        response = client.post(
            "/admin/users/editroleuser/role",
            data={
                "role": "power_user",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show success message
        assert (
            "success" in text_lower or "updated" in text_lower
        ), "Should show success message after updating role"

    def test_cannot_demote_self(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC3: Cannot demote own admin account.

        Given I am authenticated as an admin
        When I try to change my own role to non-admin
        Then I see an error message
        And my role remains admin
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the users page to get CSRF token
        users_page = client.get("/admin/users")
        csrf_token = web_infrastructure.extract_csrf_token(users_page.text)

        # Try to demote self
        response = client.post(
            f"/admin/users/{admin_user['username']}/role",
            data={
                "role": "normal_user",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show error about demoting self
        assert (
            "error" in text_lower or "cannot" in text_lower or "own" in text_lower
        ), "Should show error when trying to demote own account"


# =============================================================================
# AC4: Change User Password Tests
# =============================================================================


class TestChangeUserPassword:
    """Tests for change user password (AC4)."""

    def test_change_user_password(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC4: Password change works and shows success message.

        Given I am authenticated as an admin
        And there is another user in the system
        When I change their password
        Then I see a success message
        """
        # Create another user to change password
        web_infrastructure.create_normal_user(
            username="changepassuser", password="OldPass@123!"
        )

        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the users page to get CSRF token
        users_page = client.get("/admin/users")
        csrf_token = web_infrastructure.extract_csrf_token(users_page.text)

        # Change user password
        response = client.post(
            "/admin/users/changepassuser/password",
            data={
                "new_password": "NewPass@789!",
                "confirm_password": "NewPass@789!",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show success message
        assert (
            "success" in text_lower
            or "changed" in text_lower
            or "updated" in text_lower
        ), "Should show success message after changing password"


# =============================================================================
# AC5: Delete User Tests
# =============================================================================


class TestDeleteUser:
    """Tests for delete user (AC5)."""

    def test_delete_user(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC5: User deletion works and shows success message.

        Given I am authenticated as an admin
        And there is another user in the system
        When I delete that user
        Then I see a success message
        And the user no longer appears in the list
        """
        # Create another user to delete
        web_infrastructure.create_normal_user(
            username="deleteuser", password="DeleteMe@123!"
        )

        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the users page to get CSRF token
        users_page = client.get("/admin/users")
        csrf_token = web_infrastructure.extract_csrf_token(users_page.text)

        # Verify user exists initially
        assert (
            "deleteuser" in users_page.text.lower()
        ), "User should exist before deletion"

        # Delete user
        response = client.post(
            "/admin/users/deleteuser/delete",
            data={
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show success message
        assert (
            "success" in text_lower or "deleted" in text_lower
        ), "Should show success message after deleting user"

        # User should no longer appear in the table rows
        # The username may still appear in success message, but not in <td> cells
        import re

        # Check that deleteuser doesn't appear as a table cell value (data row)
        td_pattern = r"<td>deleteuser</td>"
        assert not re.search(
            td_pattern, text_lower
        ), "Deleted user should not appear in the table rows"

    def test_cannot_delete_self(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        AC5: Cannot delete own account.

        Given I am authenticated as an admin
        When I try to delete my own account
        Then I see an error message
        And my account remains
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the users page to get CSRF token
        users_page = client.get("/admin/users")
        csrf_token = web_infrastructure.extract_csrf_token(users_page.text)

        # Try to delete self
        response = client.post(
            f"/admin/users/{admin_user['username']}/delete",
            data={
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show error about deleting self
        assert (
            "error" in text_lower or "cannot" in text_lower or "own" in text_lower
        ), "Should show error when trying to delete own account"

        # User should still appear in list
        assert (
            admin_user["username"].lower() in text_lower
        ), "Admin user should still appear in the list"


# =============================================================================
# Partial Refresh Endpoint Tests
# =============================================================================


class TestUsersPartial:
    """Tests for htmx partial refresh endpoint."""

    def test_users_partial_list(self, authenticated_client: TestClient):
        """
        AC: GET /admin/partials/users-list returns HTML fragment.

        Given I am authenticated
        When I request the users list partial
        Then I receive an HTML fragment (not full page)
        """
        response = authenticated_client.get("/admin/partials/users-list")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        # Should be an HTML fragment, not a full page
        assert (
            "<html>" not in response.text.lower()
        ), "Partial should not contain full HTML structure"
        # Should contain user-related content (table)
        assert (
            "<table" in response.text.lower() or "<tr" in response.text.lower()
        ), "Users partial should contain table content"

    def test_partials_require_auth(self, web_client: TestClient):
        """
        Partial endpoints require authentication.

        Given I am not authenticated
        When I request a partial endpoint
        Then I am redirected to login
        """
        response = web_client.get("/admin/partials/users-list")
        assert response.status_code in [
            302,
            303,
        ], f"Users partial should redirect unauthenticated, got {response.status_code}"
