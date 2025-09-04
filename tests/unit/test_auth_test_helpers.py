"""
Unit tests for AuthTestHelper and JWTTokenManager.

Tests authentication testing utilities for multi-user CIDX server E2E testing.
"""

import pytest
import jwt
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from tests.utils.auth_test_helpers import AuthTestHelper, JWTTokenManager


class TestJWTTokenManager:
    """Unit tests for JWTTokenManager class."""

    def test_jwt_token_manager_init(self):
        """Test that JWTTokenManager initializes properly."""
        manager = JWTTokenManager(
            secret_key="test-secret", algorithm="HS256", default_expiry_minutes=30
        )

        assert manager.secret_key == "test-secret"
        assert manager.algorithm == "HS256"
        assert manager.default_expiry_minutes == 30

    def test_generate_token_creates_valid_jwt(self):
        """Test that generate_token creates a valid JWT token."""
        manager = JWTTokenManager(secret_key="test-secret")

        user_data = {"username": "testuser", "user_id": "123", "role": "normal_user"}

        token = manager.generate_token(user_data)

        # Verify token structure
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT has 3 parts

        # Decode and verify payload
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert payload["sub"] == "testuser"
        assert payload["user_id"] == "123"
        assert payload["role"] == "normal_user"
        assert "exp" in payload
        assert "iat" in payload

    def test_generate_token_with_custom_expiry(self):
        """Test generating token with custom expiry time."""
        manager = JWTTokenManager(secret_key="test-secret")

        user_data = {"username": "testuser", "user_id": "123", "role": "admin"}
        token = manager.generate_token(user_data, expires_minutes=120)

        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])

        # Verify expiry is approximately 120 minutes from now
        exp_time = datetime.fromtimestamp(payload["exp"], timezone.utc)
        iat_time = datetime.fromtimestamp(payload["iat"], timezone.utc)
        duration = exp_time - iat_time

        assert 119 <= duration.total_seconds() / 60 <= 121  # Allow 1 minute tolerance

    def test_validate_token_with_valid_token(self):
        """Test validating a valid JWT token."""
        manager = JWTTokenManager(secret_key="test-secret")

        user_data = {"username": "testuser", "user_id": "123", "role": "admin"}
        token = manager.generate_token(user_data)

        # Validate token
        payload = manager.validate_token(token)

        assert payload["sub"] == "testuser"
        assert payload["user_id"] == "123"
        assert payload["role"] == "admin"

    def test_validate_token_with_invalid_signature(self):
        """Test that validation fails with invalid signature."""
        manager = JWTTokenManager(secret_key="test-secret")

        # Create token with different secret
        other_manager = JWTTokenManager(secret_key="different-secret")
        user_data = {"username": "testuser", "user_id": "123", "role": "admin"}
        token = other_manager.generate_token(user_data)

        # Validation should fail
        with pytest.raises(jwt.InvalidTokenError):
            manager.validate_token(token)

    def test_validate_token_with_expired_token(self):
        """Test that validation fails with expired token."""
        manager = JWTTokenManager(secret_key="test-secret")

        # Create expired token
        user_data = {"username": "testuser", "user_id": "123", "role": "admin"}
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)

        payload = {
            "sub": user_data["username"],
            "user_id": user_data["user_id"],
            "role": user_data["role"],
            "iat": int(past_time.timestamp()),
            "exp": int((past_time + timedelta(minutes=30)).timestamp()),  # Expired
        }

        expired_token = jwt.encode(payload, "test-secret", algorithm="HS256")

        # Validation should fail
        with pytest.raises(jwt.ExpiredSignatureError):
            manager.validate_token(expired_token)

    def test_refresh_token_creates_new_token(self):
        """Test that refresh_token creates a new token with extended expiry."""
        manager = JWTTokenManager(secret_key="test-secret")

        user_data = {"username": "testuser", "user_id": "123", "role": "admin"}
        original_token = manager.generate_token(user_data, expires_minutes=30)

        # Wait a moment to ensure timestamps differ
        import time

        time.sleep(1)

        # Refresh token
        new_token = manager.refresh_token(original_token)

        # Tokens should be different
        assert new_token != original_token

        # Both should be valid
        original_payload = manager.validate_token(original_token)
        new_payload = manager.validate_token(new_token)

        # User data should be the same
        assert original_payload["sub"] == new_payload["sub"]
        assert original_payload["user_id"] == new_payload["user_id"]
        assert original_payload["role"] == new_payload["role"]

        # New token should have later timestamps
        assert new_payload["iat"] > original_payload["iat"]
        assert new_payload["exp"] > original_payload["exp"]

    def test_get_user_info_from_token(self):
        """Test extracting user information from token."""
        manager = JWTTokenManager(secret_key="test-secret")

        user_data = {"username": "poweruser", "user_id": "456", "role": "power_user"}

        token = manager.generate_token(user_data)
        user_info = manager.get_user_info_from_token(token)

        assert user_info["username"] == "poweruser"
        assert user_info["user_id"] == "456"
        assert user_info["role"] == "power_user"

    def test_is_token_expired_with_valid_token(self):
        """Test is_token_expired returns False for valid token."""
        manager = JWTTokenManager(secret_key="test-secret")

        user_data = {"username": "testuser", "user_id": "123", "role": "admin"}
        token = manager.generate_token(user_data, expires_minutes=60)

        assert not manager.is_token_expired(token)

    def test_is_token_expired_with_expired_token(self):
        """Test is_token_expired returns True for expired token."""
        manager = JWTTokenManager(secret_key="test-secret")

        # Create expired token
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        payload = {
            "sub": "testuser",
            "user_id": "123",
            "role": "admin",
            "iat": int(past_time.timestamp()),
            "exp": int((past_time + timedelta(minutes=30)).timestamp()),
        }

        expired_token = jwt.encode(payload, "test-secret", algorithm="HS256")

        assert manager.is_token_expired(expired_token)


class TestAuthTestHelper:
    """Unit tests for AuthTestHelper class."""

    def test_auth_test_helper_init(self):
        """Test that AuthTestHelper initializes properly."""
        helper = AuthTestHelper(server_url="http://localhost:8080", default_timeout=15)

        assert helper.server_url == "http://localhost:8080"
        assert helper.default_timeout == 15
        assert isinstance(helper.jwt_manager, JWTTokenManager)
        assert helper.authenticated_sessions == {}

    @patch("requests.post")
    def test_login_user_success(self, mock_post):
        """Test successful user login."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test.jwt.token",
            "token_type": "bearer",
            "user": {"username": "testuser", "role": "normal_user"},
        }
        mock_post.return_value = mock_response

        helper = AuthTestHelper("http://localhost:8080")
        result = helper.login_user("testuser", "password")

        assert result["success"] is True
        assert result["token"] == "test.jwt.token"
        assert result["user"]["username"] == "testuser"

        # Verify session was stored
        assert "testuser" in helper.authenticated_sessions

    @patch("requests.post")
    def test_login_user_failure(self, mock_post):
        """Test failed user login."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid username or password"}
        mock_post.return_value = mock_response

        helper = AuthTestHelper("http://localhost:8080")
        result = helper.login_user("testuser", "wrongpassword")

        assert result["success"] is False
        assert result["token"] is None
        assert "Invalid username or password" in result["error"]

    def test_create_auth_headers(self):
        """Test creating authentication headers."""
        helper = AuthTestHelper("http://localhost:8080")

        headers = helper.create_auth_headers("test.jwt.token")

        assert headers == {"Authorization": "Bearer test.jwt.token"}

    def test_create_auth_headers_with_additional_headers(self):
        """Test creating auth headers with additional headers."""
        helper = AuthTestHelper("http://localhost:8080")

        headers = helper.create_auth_headers(
            "test.jwt.token", additional_headers={"Content-Type": "application/json"}
        )

        expected = {
            "Authorization": "Bearer test.jwt.token",
            "Content-Type": "application/json",
        }

        assert headers == expected

    @patch("requests.post")
    def test_login_and_get_headers_convenience_method(self, mock_post):
        """Test the convenience method for login and getting headers."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test.jwt.token",
            "token_type": "bearer",
            "user": {"username": "testuser", "role": "normal_user"},
        }
        mock_post.return_value = mock_response

        helper = AuthTestHelper("http://localhost:8080")
        headers = helper.login_and_get_headers("testuser", "password")

        assert headers == {"Authorization": "Bearer test.jwt.token"}

    def test_get_session_for_user(self):
        """Test retrieving session for authenticated user."""
        helper = AuthTestHelper("http://localhost:8080")

        # Manually add session for testing
        session_data = {
            "token": "test.jwt.token",
            "user": {"username": "testuser", "role": "admin"},
        }
        helper.authenticated_sessions["testuser"] = session_data

        retrieved_session = helper.get_session_for_user("testuser")
        assert retrieved_session == session_data

        # Non-existent user should return None
        assert helper.get_session_for_user("nonexistent") is None

    def test_logout_user(self):
        """Test logging out a user."""
        helper = AuthTestHelper("http://localhost:8080")

        # Add session
        helper.authenticated_sessions["testuser"] = {
            "token": "test.jwt.token",
            "user": {"username": "testuser", "role": "admin"},
        }

        # Logout user
        result = helper.logout_user("testuser")

        assert result is True
        assert "testuser" not in helper.authenticated_sessions

        # Logout non-existent user should return False
        assert helper.logout_user("nonexistent") is False

    def test_logout_all_users(self):
        """Test logging out all users."""
        helper = AuthTestHelper("http://localhost:8080")

        # Add multiple sessions
        helper.authenticated_sessions.update(
            {
                "user1": {"token": "token1", "user": {"username": "user1"}},
                "user2": {"token": "token2", "user": {"username": "user2"}},
                "user3": {"token": "token3", "user": {"username": "user3"}},
            }
        )

        helper.logout_all_users()

        assert len(helper.authenticated_sessions) == 0

    def test_create_test_users_with_roles(self):
        """Test creating multiple test users with different roles."""
        helper = AuthTestHelper("http://localhost:8080")

        users = helper.create_test_users_with_roles()

        assert len(users) >= 3

        # Check that we have different roles
        roles = [user["role"] for user in users]
        assert "admin" in roles
        assert "power_user" in roles
        assert "normal_user" in roles

    @patch("requests.post")
    def test_login_multiple_users(self, mock_post):
        """Test logging in multiple users."""

        # Mock successful login responses
        def mock_login_response(url, **kwargs):
            username = kwargs["json"]["username"]
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": f"{username}.jwt.token",
                "token_type": "bearer",
                "user": {"username": username, "role": "normal_user"},
            }
            return mock_response

        mock_post.side_effect = mock_login_response

        helper = AuthTestHelper("http://localhost:8080")

        users = [
            {"username": "user1", "password": "pass1"},
            {"username": "user2", "password": "pass2"},
            {"username": "user3", "password": "pass3"},
        ]

        results = helper.login_multiple_users(users)

        assert len(results) == 3
        assert all(result["success"] for result in results.values())
        assert len(helper.authenticated_sessions) == 3

    def test_verify_role_based_access(self):
        """Test role-based access verification utilities."""
        helper = AuthTestHelper("http://localhost:8080")

        # Test role hierarchy
        assert helper.verify_role_hierarchy("admin", "power_user")
        assert helper.verify_role_hierarchy("power_user", "normal_user")
        assert not helper.verify_role_hierarchy("normal_user", "admin")
        assert not helper.verify_role_hierarchy("power_user", "admin")

    def test_create_test_jwt_token(self):
        """Test creating test JWT tokens for testing."""
        helper = AuthTestHelper("http://localhost:8080")

        user_data = {"username": "testuser", "user_id": "999", "role": "admin"}

        token = helper.create_test_jwt_token(user_data)

        # Verify token can be decoded
        payload = helper.jwt_manager.validate_token(token)
        assert payload["sub"] == "testuser"
        assert payload["user_id"] == "999"
        assert payload["role"] == "admin"

    def test_simulate_token_expiry(self):
        """Test token expiry simulation utilities."""
        helper = AuthTestHelper("http://localhost:8080")

        # Create an expired token manually using JWT library
        from datetime import datetime, timezone, timedelta
        import jwt

        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        payload = {
            "sub": "testuser",
            "user_id": "123",
            "role": "admin",
            "iat": int(past_time.timestamp()),
            "exp": int((past_time + timedelta(minutes=30)).timestamp()),
        }

        expired_token = jwt.encode(
            payload, helper.jwt_manager.secret_key, algorithm="HS256"
        )

        # Test that expired token is detected as expired
        assert helper.jwt_manager.is_token_expired(expired_token)

        # Test with a valid token for comparison
        user_data = {"username": "testuser", "user_id": "123", "role": "admin"}
        valid_token = helper.create_test_jwt_token(
            user_data, expires_minutes=60  # Valid for 60 minutes
        )

        assert not helper.jwt_manager.is_token_expired(valid_token)
