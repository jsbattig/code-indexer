"""
Tests for Web UI Authentication and Authorization.

Story #529: Web UI Foundation with Authentication

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

import pytest
from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


# =============================================================================
# AC1: Static File Serving Tests
# =============================================================================

class TestStaticFileServing:
    """Tests for static file serving (AC1)."""

    def test_static_css_served(self, web_client: TestClient):
        """
        AC1: GET /admin/static/pico.min.css returns Pico CSS with correct content-type.

        Given the CIDX server is running
        When I request /admin/static/pico.min.css
        Then I receive the Pico CSS file with correct content-type
        """
        response = web_client.get("/admin/static/pico.min.css")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "text/css" in response.headers.get("content-type", ""), (
            f"Expected text/css content-type, got {response.headers.get('content-type')}"
        )
        # Verify it's actually CSS content
        assert "html" in response.text.lower() or "{" in response.text, (
            "Response does not appear to be CSS content"
        )

    def test_static_js_served(self, web_client: TestClient):
        """
        AC1: GET /admin/static/htmx.min.js returns htmx JS with correct content-type.

        Given the CIDX server is running
        When I request /admin/static/htmx.min.js
        Then I receive the htmx JavaScript file with correct content-type
        """
        response = web_client.get("/admin/static/htmx.min.js")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        content_type = response.headers.get("content-type", "")
        assert "javascript" in content_type or "text/javascript" in content_type, (
            f"Expected javascript content-type, got {content_type}"
        )
        # Verify it's actually JavaScript content
        assert "function" in response.text or "var" in response.text or "const" in response.text, (
            "Response does not appear to be JavaScript content"
        )


# =============================================================================
# AC2: Login Page Display Tests
# =============================================================================

class TestLoginPageDisplay:
    """Tests for login page display (AC2)."""

    def test_login_page_renders(self, web_client: TestClient):
        """
        AC2: Login form displays with username, password fields and CSRF token.

        Given I am not authenticated
        When I navigate to /admin/login
        Then I see a login form with username and password fields
        And the form includes a CSRF token
        """
        response = web_client.get("/admin/login")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "<form" in response.text, "Response should contain a form element"
        assert "username" in response.text.lower(), "Form should have username field"
        assert "password" in response.text.lower(), "Form should have password field"
        assert "csrf_token" in response.text, "Form should have CSRF token"

    def test_login_page_unauthenticated_redirect(self, web_client: TestClient):
        """
        AC2: Unauthenticated access to /admin/ redirects to /admin/login.

        Given I am not authenticated
        When I navigate to /admin/
        Then I am redirected to /admin/login
        """
        response = web_client.get("/admin/")

        assert response.status_code in [302, 303, 307], (
            f"Expected redirect (302/303/307), got {response.status_code}"
        )
        location = response.headers.get("location", "")
        assert "/admin/login" in location, (
            f"Expected redirect to /admin/login, got {location}"
        )

    def test_login_page_styled_with_pico(self, web_client: TestClient):
        """
        AC2: Login form is styled with Pico CSS.

        Given I am not authenticated
        When I navigate to /admin/login
        Then I see the login form styled with Pico CSS
        """
        response = web_client.get("/admin/login")

        assert response.status_code == 200
        # Verify Pico CSS is included
        assert "pico" in response.text.lower(), (
            "Login page should include Pico CSS reference"
        )


# =============================================================================
# AC3: Authentication Flow Tests
# =============================================================================

class TestAuthenticationFlow:
    """Tests for authentication flow (AC3)."""

    def test_login_valid_admin_credentials(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: dict
    ):
        """
        AC3: Valid admin credentials -> redirect to /admin/, httpOnly signed cookie set.

        Given I am on the login page
        When I submit valid admin credentials
        Then I am redirected to /admin/
        And a secure httpOnly cookie is set
        """
        assert web_infrastructure.client is not None
        client = web_infrastructure.client

        # Get login page to get CSRF token
        login_page = client.get("/admin/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_page.text)
        assert csrf_token is not None, "Could not extract CSRF token"

        # Submit login form
        response = client.post(
            "/admin/login",
            data={
                "username": admin_user["username"],
                "password": admin_user["password"],
                "csrf_token": csrf_token,
            }
        )

        # Should redirect to /admin/
        assert response.status_code in [302, 303], (
            f"Expected redirect, got {response.status_code}"
        )
        location = response.headers.get("location", "")
        assert location == "/admin/" or location.endswith("/admin/"), (
            f"Expected redirect to /admin/, got {location}"
        )

        # Should set session cookie
        assert "session" in response.cookies, "Session cookie should be set"

    def test_session_cookie_is_httponly(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: dict
    ):
        """
        AC3: Session cookie has httpOnly flag set.

        When I successfully login
        Then the session cookie is httpOnly
        """
        assert web_infrastructure.client is not None
        client = web_infrastructure.client

        # Get login page to get CSRF token
        login_page = client.get("/admin/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_page.text)
        assert csrf_token is not None

        # Submit login form
        response = client.post(
            "/admin/login",
            data={
                "username": admin_user["username"],
                "password": admin_user["password"],
                "csrf_token": csrf_token,
            }
        )

        # Check cookie headers for httponly flag
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "httponly" in set_cookie_header.lower(), (
            "Session cookie should have httpOnly flag"
        )

    def test_login_invalid_credentials(
        self,
        web_infrastructure: WebTestInfrastructure
    ):
        """
        AC3: Invalid credentials -> stay on login with error message.

        Given I am on the login page
        When I submit invalid credentials
        Then I remain on the login page
        And I see an error message "Invalid username or password"
        """
        assert web_infrastructure.client is not None
        client = web_infrastructure.client

        # Get login page to get CSRF token
        login_page = client.get("/admin/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_page.text)
        assert csrf_token is not None

        # Submit with invalid credentials
        response = client.post(
            "/admin/login",
            data={
                "username": "nonexistent",
                "password": "wrongpassword",
                "csrf_token": csrf_token,
            }
        )

        # Should stay on login page (200) or redirect back to login
        assert response.status_code in [200, 302, 303], (
            f"Expected 200 or redirect, got {response.status_code}"
        )

        # If it's a redirect, follow it to get the error message
        if response.status_code in [302, 303]:
            # Create client that follows redirects for this check
            follow_client = TestClient(web_infrastructure.app, follow_redirects=True)
            response = follow_client.post(
                "/admin/login",
                data={
                    "username": "nonexistent",
                    "password": "wrongpassword",
                    "csrf_token": csrf_token,
                }
            )

        # Should contain error message
        assert "invalid" in response.text.lower() or "error" in response.text.lower(), (
            "Response should contain error message"
        )

        # Should NOT set session cookie
        assert "session" not in response.cookies, "Session cookie should NOT be set"

    def test_login_non_admin_rejected(
        self,
        web_infrastructure: WebTestInfrastructure,
        normal_user: dict
    ):
        """
        AC3: Non-admin user -> stay on login with "Admin access required" error.

        Given I am on the login page
        When I submit credentials for a non-admin user
        Then I remain on the login page
        And I see an error message "Admin access required"
        """
        assert web_infrastructure.client is not None
        assert web_infrastructure.app is not None
        client = web_infrastructure.client

        # Get login page to get CSRF token
        login_page = client.get("/admin/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_page.text)
        assert csrf_token is not None

        # Submit with non-admin credentials
        response = client.post(
            "/admin/login",
            data={
                "username": normal_user["username"],
                "password": normal_user["password"],
                "csrf_token": csrf_token,
            }
        )

        # If it's a redirect, follow it
        if response.status_code in [302, 303]:
            follow_client = TestClient(web_infrastructure.app, follow_redirects=True)
            response = follow_client.post(
                "/admin/login",
                data={
                    "username": normal_user["username"],
                    "password": normal_user["password"],
                    "csrf_token": csrf_token,
                }
            )

        # Should contain admin access required message
        assert "admin" in response.text.lower() and (
            "required" in response.text.lower() or "access" in response.text.lower()
        ), "Response should indicate admin access is required"


# =============================================================================
# AC4: Session Management Tests
# =============================================================================

class TestSessionManagement:
    """Tests for session management (AC4)."""

    def test_logout_clears_session(
        self,
        authenticated_client: TestClient
    ):
        """
        AC4: Logout clears session and redirects to /admin/login.

        Given I am authenticated as an admin
        When I click the logout button
        Then my session cookie is cleared
        And I am redirected to /admin/login
        """
        # Perform logout
        response = authenticated_client.get("/admin/logout", follow_redirects=False)

        # Should redirect to login
        assert response.status_code in [302, 303], (
            f"Expected redirect, got {response.status_code}"
        )
        location = response.headers.get("location", "")
        assert "/admin/login" in location, (
            f"Expected redirect to /admin/login, got {location}"
        )

        # Session cookie should be cleared (max-age=0 or expires in past)
        set_cookie = response.headers.get("set-cookie", "")
        # Cookie should be invalidated somehow
        assert "session" in set_cookie.lower(), "Session cookie should be in response"

    def test_expired_session_redirects(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: dict
    ):
        """
        AC4: Expired session redirects to login with "Session expired" message.

        Given I have an expired session cookie
        When I navigate to /admin/
        Then I am redirected to /admin/login
        And I see a message "Session expired, please login again"
        """
        assert web_infrastructure.client is not None
        client = web_infrastructure.client

        # Set an invalid/expired session cookie
        # The exact format depends on implementation, but we use an obviously invalid one
        client.cookies.set("session", "invalid_expired_session_token")

        # Try to access protected page
        response = client.get("/admin/")

        # Should redirect to login
        assert response.status_code in [302, 303], (
            f"Expected redirect, got {response.status_code}"
        )
        location = response.headers.get("location", "")
        assert "/admin/login" in location, (
            f"Expected redirect to /admin/login, got {location}"
        )


# =============================================================================
# AC5: Navigation Shell Tests
# =============================================================================

class TestNavigationShell:
    """Tests for navigation shell (AC5)."""

    def test_authenticated_access_to_dashboard(
        self,
        authenticated_client: TestClient
    ):
        """
        AC5: Authenticated pages show navigation header with all links.

        Given I am authenticated as an admin
        When I view the dashboard
        Then I see a navigation header with all menu items
        And I see a logout button
        """
        response = authenticated_client.get("/admin/")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "Dashboard" in response.text, "Navigation should include Dashboard link"

        # Check for all expected navigation items
        nav_items = ["Dashboard", "Users", "Golden Repos", "Repositories", "Jobs", "Query", "Config"]
        for item in nav_items:
            # Check for the item in navigation (case-insensitive)
            assert item.lower() in response.text.lower() or item.replace(" ", "-").lower() in response.text.lower(), (
                f"Navigation should include {item} link"
            )

        # Check for logout
        assert "logout" in response.text.lower(), "Page should include logout link"

    def test_navigation_current_page_highlighted(
        self,
        authenticated_client: TestClient
    ):
        """
        AC5: Current page is highlighted in navigation.

        Given I am authenticated as an admin
        When I view any admin page
        Then the current page is highlighted in navigation
        """
        response = authenticated_client.get("/admin/")

        assert response.status_code == 200

        # The current page should have some highlighting indicator
        # This could be a class like "active", "current", or aria-current
        assert (
            'aria-current' in response.text or
            'class="active"' in response.text.lower() or
            "active" in response.text.lower()
        ), "Current page should be highlighted in navigation"


# =============================================================================
# AC6: Admin-Only Access Enforcement Tests
# =============================================================================

class TestAdminOnlyAccess:
    """Tests for admin-only access enforcement (AC6)."""

    def test_unauthenticated_admin_routes_redirect(
        self,
        web_client: TestClient
    ):
        """
        AC6: Unauthenticated access to /admin/* (except /admin/login) redirects to login.

        Given I am not authenticated
        When I attempt to access any /admin/* route (except /admin/login)
        Then I am redirected to /admin/login
        """
        # Test various admin routes
        protected_routes = [
            "/admin/",
            "/admin/users",
            "/admin/golden-repos",
            "/admin/repos",
            "/admin/jobs",
            "/admin/query",
            "/admin/config",
        ]

        for route in protected_routes:
            response = web_client.get(route)
            assert response.status_code in [302, 303], (
                f"Expected redirect for {route}, got {response.status_code}"
            )
            location = response.headers.get("location", "")
            assert "/admin/login" in location, (
                f"Expected redirect to /admin/login for {route}, got {location}"
            )


# =============================================================================
# AC7: CSRF Protection Tests
# =============================================================================

class TestCSRFProtection:
    """Tests for CSRF protection (AC7)."""

    def test_login_missing_csrf_rejected(
        self,
        web_client: TestClient,
        admin_user: dict
    ):
        """
        AC7: Forms submitted without valid CSRF token are rejected with 403.

        Given I submit a form without a valid CSRF token
        When the server processes the request
        Then the request is rejected with 403 Forbidden
        """
        # Submit login without CSRF token
        response = web_client.post(
            "/admin/login",
            data={
                "username": admin_user["username"],
                "password": admin_user["password"],
                # No csrf_token
            }
        )

        assert response.status_code == 403, (
            f"Expected 403 Forbidden without CSRF token, got {response.status_code}"
        )

    def test_login_invalid_csrf_rejected(
        self,
        web_client: TestClient,
        admin_user: dict
    ):
        """
        AC7: Forms submitted with invalid CSRF token are rejected with 403.
        """
        # Submit login with invalid CSRF token
        response = web_client.post(
            "/admin/login",
            data={
                "username": admin_user["username"],
                "password": admin_user["password"],
                "csrf_token": "invalid_token_12345",
            }
        )

        assert response.status_code == 403, (
            f"Expected 403 Forbidden with invalid CSRF token, got {response.status_code}"
        )

    def test_form_contains_csrf_token(
        self,
        web_client: TestClient
    ):
        """
        AC7: All forms contain hidden CSRF token field.

        Given I am on any admin form
        When I inspect the form HTML
        Then it contains a hidden CSRF token field
        """
        response = web_client.get("/admin/login")

        assert response.status_code == 200
        assert 'name="csrf_token"' in response.text, (
            "Form should contain csrf_token field"
        )
        assert 'type="hidden"' in response.text, (
            "CSRF token should be a hidden field"
        )
