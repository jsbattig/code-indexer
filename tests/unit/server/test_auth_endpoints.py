"""
Unit tests for authentication endpoints and middleware.

Tests /auth/login endpoint, global authentication middleware,
and Swagger/OpenAPI documentation endpoint.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import json
from datetime import datetime, timezone

# These imports will fail initially - that's the TDD approach
from code_indexer.server.app import create_app
from code_indexer.server.auth.dependencies import require_permission
from code_indexer.server.auth.user_manager import User, UserRole


class TestAuthLoginEndpoint:
    """Test /auth/login endpoint functionality."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_user_manager(self):
        """Create mock user manager."""
        with patch("code_indexer.server.app.user_manager") as mock:
            yield mock

    def test_login_with_valid_admin_credentials(self, client, mock_user_manager):
        """Test login with valid admin credentials returns JWT token."""
        # Mock successful authentication
        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = admin_user

        response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )

        assert response.status_code == 200
        response_data = response.json()

        assert "access_token" in response_data
        assert "token_type" in response_data
        assert response_data["token_type"] == "bearer"
        assert "user" in response_data
        assert response_data["user"]["username"] == "admin"
        assert response_data["user"]["role"] == "admin"

        # Verify authenticate_user was called correctly
        mock_user_manager.authenticate_user.assert_called_once_with("admin", "admin")

    def test_login_with_valid_power_user_credentials(self, client, mock_user_manager):
        """Test login with valid power user credentials returns JWT token."""
        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = power_user

        response = client.post(
            "/auth/login", json={"username": "poweruser", "password": "password123"}
        )

        assert response.status_code == 200
        response_data = response.json()

        assert "access_token" in response_data
        assert response_data["user"]["username"] == "poweruser"
        assert response_data["user"]["role"] == "power_user"

    def test_login_with_valid_normal_user_credentials(self, client, mock_user_manager):
        """Test login with valid normal user credentials returns JWT token."""
        normal_user = User(
            username="normaluser",
            password_hash="$2b$12$hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = normal_user

        response = client.post(
            "/auth/login", json={"username": "normaluser", "password": "mypassword"}
        )

        assert response.status_code == 200
        response_data = response.json()

        assert "access_token" in response_data
        assert response_data["user"]["username"] == "normaluser"
        assert response_data["user"]["role"] == "normal_user"

    def test_login_with_invalid_credentials(self, client, mock_user_manager):
        """Test login with invalid credentials returns 401."""
        # Mock failed authentication
        mock_user_manager.authenticate_user.return_value = None

        response = client.post(
            "/auth/login", json={"username": "admin", "password": "wrongpassword"}
        )

        assert response.status_code == 401
        response_data = response.json()

        assert "detail" in response_data
        assert "Invalid credentials" in response_data["detail"]

    def test_login_with_nonexistent_user(self, client, mock_user_manager):
        """Test login with nonexistent user returns 401."""
        mock_user_manager.authenticate_user.return_value = None

        response = client.post(
            "/auth/login", json={"username": "nonexistent", "password": "anypassword"}
        )

        assert response.status_code == 401

    def test_login_with_missing_username(self, client):
        """Test login with missing username returns 422."""
        response = client.post("/auth/login", json={"password": "password"})

        assert response.status_code == 422
        response_data = response.json()
        assert "details" in response_data or "detail" in response_data

    def test_login_with_missing_password(self, client):
        """Test login with missing password returns 422."""
        response = client.post("/auth/login", json={"username": "admin"})

        assert response.status_code == 422
        response_data = response.json()
        assert "details" in response_data or "detail" in response_data

    def test_login_with_empty_username(self, client, mock_user_manager):
        """Test login with empty username returns 422 (validation error)."""
        # No need to mock since validation happens before authentication

        response = client.post(
            "/auth/login", json={"username": "", "password": "password"}
        )

        assert response.status_code == 422  # Validation error, not auth error

    def test_login_with_empty_password(self, client, mock_user_manager):
        """Test login with empty password returns 422 (validation error)."""
        # No need to mock since validation happens before authentication

        response = client.post(
            "/auth/login", json={"username": "admin", "password": ""}
        )

        assert response.status_code == 422  # Validation error, not auth error

    def test_login_response_token_format(self, client, mock_user_manager):
        """Test that login response token has correct JWT format."""
        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.authenticate_user.return_value = admin_user

        response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )

        assert response.status_code == 200
        token = response.json()["access_token"]

        # JWT token should have 3 parts separated by dots
        token_parts = token.split(".")
        assert len(token_parts) == 3

        # Each part should be base64-encoded (non-empty strings)
        for part in token_parts:
            assert len(part) > 0

    def test_login_endpoint_content_type(self, client):
        """Test that login endpoint only accepts JSON content type."""
        response = client.post("/auth/login", content="username=admin&password=admin")

        # Should return 422 for invalid JSON
        assert response.status_code == 422


class TestGlobalAuthenticationMiddleware:
    """Test global authentication middleware for all API endpoints."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def valid_jwt_token(self):
        """Create valid JWT token for testing."""
        # This would be created by the actual JWT manager
        return "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test.token"

    def test_protected_endpoint_without_token(self, client):
        """Test accessing protected endpoint without token returns 401."""
        response = client.get("/api/repos")

        assert response.status_code == 401
        response_data = response.json()
        assert "detail" in response_data
        assert "Missing authentication credentials" in response_data["detail"]

    def test_protected_endpoint_with_invalid_token(self, client):
        """Test accessing protected endpoint with invalid token returns 401."""
        headers = {"Authorization": "Bearer invalid.jwt.token"}
        response = client.get("/api/repos", headers=headers)

        assert response.status_code == 401

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    def test_protected_endpoint_with_valid_token(self, mock_jwt_manager, client):
        """Test accessing protected endpoint with valid token succeeds."""
        # Mock JWT validation
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        # Mock user retrieval
        with patch(
            "code_indexer.server.auth.dependencies.user_manager"
        ) as mock_user_manager:
            admin_user = User(
                username="testuser",
                password_hash="$2b$12$hash",
                role=UserRole.ADMIN,
                created_at=datetime.now(timezone.utc),
            )
            mock_user_manager.get_user.return_value = admin_user

            headers = {"Authorization": "Bearer valid.jwt.token"}
            response = client.get("/api/repos", headers=headers)

            # Should not return 401 (actual endpoint may return other status codes)
            assert response.status_code != 401

    def test_protected_endpoint_with_malformed_auth_header(self, client):
        """Test accessing protected endpoint with malformed Authorization header."""
        # Missing "Bearer" prefix
        headers = {"Authorization": "jwt.token.here"}
        response = client.get("/api/repos", headers=headers)

        assert response.status_code == 401

    def test_protected_endpoint_with_expired_token(self, client):
        """Test accessing protected endpoint with expired token returns 401."""
        with patch(
            "code_indexer.server.auth.dependencies.jwt_manager"
        ) as mock_jwt_manager:
            # Mock expired token validation
            from code_indexer.server.auth.jwt_manager import TokenExpiredError

            mock_jwt_manager.validate_token.side_effect = TokenExpiredError(
                "Token expired"
            )

            headers = {"Authorization": "Bearer expired.jwt.token"}
            response = client.get("/api/repos", headers=headers)

            assert response.status_code == 401
            response_data = response.json()
            assert "expired" in response_data["detail"].lower()

    def test_public_endpoints_dont_require_auth(self, client):
        """Test that public endpoints don't require authentication."""
        # Docs endpoint should be public
        response = client.get("/docs")
        assert response.status_code != 401

        # OpenAPI spec should be public
        response = client.get("/openapi.json")
        assert response.status_code != 401

    def test_auth_login_endpoint_is_public(self, client):
        """Test that /auth/login endpoint doesn't require authentication."""
        # Should return 422 for missing body, not 401 for missing auth
        response = client.post("/auth/login")
        assert response.status_code == 422  # Not 401


class TestRoleBasedAccessControl:
    """Test role-based access control for different user types."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    def create_authenticated_headers(self, user_role: str):
        """Helper to create headers with JWT token for specific role."""
        with patch(
            "code_indexer.server.auth.dependencies.jwt_manager"
        ) as mock_jwt_manager:
            mock_jwt_manager.validate_token.return_value = {
                "username": f"{user_role}_user",
                "role": user_role,
                "exp": 9999999999,
                "iat": 1234567890,
            }

            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_user_manager:
                user = User(
                    username=f"{user_role}_user",
                    password_hash="$2b$12$hash",
                    role=UserRole(user_role),
                    created_at=datetime.now(timezone.utc),
                )
                mock_user_manager.get_user.return_value = user

        return {"Authorization": "Bearer valid.jwt.token"}

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_admin_user_access_to_admin_endpoints(
        self, mock_user_manager, mock_jwt_manager, client
    ):
        """Test that admin user can access admin-only endpoints."""
        # Setup admin user authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.get_user.return_value = admin_user

        headers = {"Authorization": "Bearer admin.jwt.token"}

        # Admin should be able to access user management endpoints
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code != 403  # Not forbidden

        # Admin should be able to access golden repo management
        response = client.get("/api/admin/golden-repos", headers=headers)
        assert response.status_code != 403  # Not forbidden

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_power_user_access_permissions(
        self, mock_user_manager, mock_jwt_manager, client
    ):
        """Test that power user can access appropriate endpoints."""
        mock_jwt_manager.validate_token.return_value = {
            "username": "poweruser",
            "role": "power_user",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.get_user.return_value = power_user

        headers = {"Authorization": "Bearer power.jwt.token"}

        # Power user should NOT access admin endpoints
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 403  # Forbidden

        response = client.get("/api/admin/golden-repos", headers=headers)
        assert response.status_code == 403  # Forbidden

        # Power user should access query and activation endpoints
        response = client.get("/api/repos", headers=headers)
        assert response.status_code != 403  # Not forbidden

    @patch("code_indexer.server.auth.dependencies.jwt_manager")
    @patch("code_indexer.server.auth.dependencies.user_manager")
    def test_normal_user_access_permissions(
        self, mock_user_manager, mock_jwt_manager, client
    ):
        """Test that normal user can only access query endpoints."""
        mock_jwt_manager.validate_token.return_value = {
            "username": "normaluser",
            "role": "normal_user",
            "exp": 9999999999,
            "iat": 1234567890,
        }

        normal_user = User(
            username="normaluser",
            password_hash="$2b$12$hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_manager.get_user.return_value = normal_user

        headers = {"Authorization": "Bearer normal.jwt.token"}

        # Normal user should NOT access admin endpoints
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 403

        response = client.get("/api/admin/golden-repos", headers=headers)
        assert response.status_code == 403

        # Normal user should NOT access activation endpoints
        response = client.post(
            "/api/repos/activate",
            headers=headers,
            json={"goldenRepoName": "test-repo", "alias": "my-repo"},
        )
        assert response.status_code == 403

        # Normal user should access query endpoints
        response = client.get("/api/repos", headers=headers)
        assert response.status_code != 403  # Not forbidden (can list repos)

    def test_require_permission_decorator_admin_only(self):
        """Test require_permission decorator for admin-only operations."""
        from fastapi import HTTPException

        # Mock current user as power user
        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Create a test function that requires admin permission
        @require_permission("manage_users")
        def test_admin_function(current_user):
            return "admin_success"

        # Should raise HTTPException for admin-only permission
        with pytest.raises(HTTPException) as exc_info:
            test_admin_function(power_user)

        assert exc_info.value.status_code == 403

    def test_require_permission_decorator_allowed_permission(self):
        """Test require_permission decorator for allowed operations."""

        # Mock current user as power user
        power_user = User(
            username="poweruser",
            password_hash="$2b$12$hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Create a test function that requires power user permission
        @require_permission("activate_repos")
        def test_power_function(current_user):
            return "power_success"

        # Should not raise exception for allowed permission
        result = test_power_function(power_user)
        assert result == "power_success"


class TestSwaggerDocumentation:
    """Test Swagger/OpenAPI documentation endpoint."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    def test_docs_endpoint_accessible(self, client):
        """Test that /docs endpoint is accessible."""
        response = client.get("/docs")

        assert response.status_code == 200

        # Should return HTML content
        assert response.headers["content-type"].startswith("text/html")

        # Should contain Swagger UI elements
        content = response.text
        assert "swagger" in content.lower() or "openapi" in content.lower()

    def test_openapi_json_endpoint_accessible(self, client):
        """Test that OpenAPI JSON spec is accessible."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        # Should be valid JSON
        openapi_spec = response.json()
        assert isinstance(openapi_spec, dict)

    def test_openapi_spec_contains_auth_endpoints(self, client):
        """Test that OpenAPI spec includes authentication endpoints."""
        response = client.get("/openapi.json")
        openapi_spec = response.json()

        # Should have paths section
        assert "paths" in openapi_spec
        paths = openapi_spec["paths"]

        # Should include /auth/login endpoint
        assert "/auth/login" in paths
        assert "post" in paths["/auth/login"]

    def test_openapi_spec_contains_security_schemes(self, client):
        """Test that OpenAPI spec includes JWT security scheme."""
        response = client.get("/openapi.json")
        openapi_spec = response.json()

        # Should have components section with security schemes
        assert "components" in openapi_spec
        assert "securitySchemes" in openapi_spec["components"]

        security_schemes = openapi_spec["components"]["securitySchemes"]

        # Should include bearer token authentication (FastAPI uses HTTPBearer)
        assert "HTTPBearer" in security_schemes or "bearerAuth" in security_schemes

    def test_openapi_spec_contains_user_roles_documentation(self, client):
        """Test that OpenAPI spec documents user roles and permissions."""
        response = client.get("/openapi.json")
        openapi_spec = response.json()

        # Should document role-based access in some way
        spec_content = json.dumps(openapi_spec).lower()
        assert "admin" in spec_content
        # Look for role-related terms in the API documentation
        role_terms = ["role", "permission", "admin", "user", "power", "access"]
        found_terms = sum(1 for term in role_terms if term in spec_content)
        assert found_terms >= 3  # Should contain multiple role-related terms

    def test_swagger_ui_allows_authentication(self, client):
        """Test that Swagger UI includes authentication capability."""
        response = client.get("/docs")
        content = response.text.lower()

        # Should include authorization/authentication elements
        assert "auth" in content or "bearer" in content or "token" in content
