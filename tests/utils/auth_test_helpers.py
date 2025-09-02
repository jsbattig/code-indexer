"""
Authentication test utilities for multi-user CIDX server testing.

This module provides utilities for authentication testing including JWT token
management, user session handling, and role-based access control testing.
"""

import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

import jwt

logger = logging.getLogger(__name__)


class JWTTokenManager:
    """Manager for JWT token operations in tests."""

    def __init__(
        self,
        secret_key: str = "test-jwt-secret",
        algorithm: str = "HS256",
        default_expiry_minutes: int = 60,
    ):
        """
        Initialize JWT token manager.

        Args:
            secret_key: Secret key for token signing
            algorithm: JWT algorithm to use
            default_expiry_minutes: Default token expiry time
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.default_expiry_minutes = default_expiry_minutes

        self.logger = logging.getLogger(f"{__name__}.JWTTokenManager")

    def generate_token(
        self, user_data: Dict[str, Any], expires_minutes: Optional[int] = None
    ) -> str:
        """
        Generate JWT token for test user.

        Args:
            user_data: User data to include in token
            expires_minutes: Token expiry time (uses default if None)

        Returns:
            JWT token string
        """
        if expires_minutes is None:
            expires_minutes = self.default_expiry_minutes

        now = datetime.now(timezone.utc)
        expiry = now + timedelta(minutes=expires_minutes)

        payload = {
            "sub": user_data["username"],
            "user_id": str(user_data.get("user_id", user_data["username"])),
            "role": user_data["role"],
            "iat": int(now.timestamp()),
            "exp": int(expiry.timestamp()),
            "jti": self._generate_jti(),
            "test_token": True,  # Mark as test token
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        self.logger.debug(f"Generated JWT token for user: {user_data['username']}")
        return token

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate and decode JWT token.

        Args:
            token: JWT token to validate

        Returns:
            Decoded token payload

        Raises:
            jwt.InvalidTokenError: If token is invalid
            jwt.ExpiredSignatureError: If token is expired
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            self.logger.debug(f"Validated token for user: {payload.get('sub')}")
            return payload

        except jwt.ExpiredSignatureError:
            self.logger.warning("Token validation failed: Token expired")
            raise
        except jwt.InvalidTokenError as e:
            self.logger.warning(f"Token validation failed: {e}")
            raise

    def refresh_token(
        self, current_token: str, extends_minutes: Optional[int] = None
    ) -> str:
        """
        Refresh JWT token with new expiry.

        Args:
            current_token: Current JWT token
            extends_minutes: New expiry time (uses default if None)

        Returns:
            New JWT token
        """
        # Decode current token (ignoring expiry for refresh)
        payload = jwt.decode(
            current_token,
            self.secret_key,
            algorithms=[self.algorithm],
            options={"verify_exp": False},
        )

        # Create new token with same user data
        user_data = {
            "username": payload["sub"],
            "user_id": payload["user_id"],
            "role": payload["role"],
        }

        new_token = self.generate_token(user_data, extends_minutes)

        self.logger.debug(f"Refreshed token for user: {user_data['username']}")
        return new_token

    def get_user_info_from_token(self, token: str) -> Dict[str, Any]:
        """
        Extract user information from token.

        Args:
            token: JWT token

        Returns:
            User information dictionary
        """
        payload = self.validate_token(token)

        return {
            "username": payload["sub"],
            "user_id": payload["user_id"],
            "role": payload["role"],
        }

    def is_token_expired(self, token: str) -> bool:
        """
        Check if token is expired.

        Args:
            token: JWT token to check

        Returns:
            True if token is expired
        """
        try:
            self.validate_token(token)
            return False
        except jwt.ExpiredSignatureError:
            return True
        except jwt.InvalidTokenError:
            return True  # Consider invalid tokens as expired

    def get_token_expiry(self, token: str) -> datetime:
        """
        Get token expiry time.

        Args:
            token: JWT token

        Returns:
            Expiry datetime
        """
        payload = jwt.decode(
            token,
            self.secret_key,
            algorithms=[self.algorithm],
            options={"verify_exp": False},
        )

        return datetime.fromtimestamp(payload["exp"], timezone.utc)

    def _generate_jti(self) -> str:
        """Generate unique token identifier."""
        import secrets

        return secrets.token_hex(16)


class AuthTestHelper:
    """Helper class for authentication testing operations."""

    def __init__(
        self,
        server_url: str,
        jwt_secret: str = "test-jwt-secret",
        default_timeout: int = 10,
    ):
        """
        Initialize authentication test helper.

        Args:
            server_url: Base URL of the server
            jwt_secret: JWT secret key for token operations
            default_timeout: Default request timeout
        """
        self.server_url = server_url.rstrip("/")
        self.default_timeout = default_timeout

        self.jwt_manager = JWTTokenManager(secret_key=jwt_secret)
        self.authenticated_sessions: Dict[str, Dict[str, Any]] = {}

        self.logger = logging.getLogger(f"{__name__}.AuthTestHelper")

    def login_user(
        self, username: str, password: str, timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Perform user login and store session.

        Args:
            username: Username
            password: Password
            timeout: Request timeout

        Returns:
            Login result dictionary
        """
        timeout = timeout or self.default_timeout

        try:
            response = requests.post(
                f"{self.server_url}/auth/login",
                json={"username": username, "password": password},
                timeout=timeout,
            )

            if response.status_code == 200:
                data = response.json()

                # Store session
                session_data = {
                    "token": data["access_token"],
                    "token_type": data.get("token_type", "bearer"),
                    "user": data["user"],
                    "login_time": datetime.now(timezone.utc).isoformat(),
                }

                self.authenticated_sessions[username] = session_data

                self.logger.info(f"User logged in successfully: {username}")

                return {
                    "success": True,
                    "token": data["access_token"],
                    "user": data["user"],
                    "session": session_data,
                }

            else:
                error_msg = "Login failed"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except ValueError:
                    error_msg = f"HTTP {response.status_code}"

                self.logger.warning(f"Login failed for {username}: {error_msg}")

                return {
                    "success": False,
                    "token": None,
                    "user": None,
                    "error": error_msg,
                    "status_code": response.status_code,
                }

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Login request failed for {username}: {e}")

            return {
                "success": False,
                "token": None,
                "user": None,
                "error": f"Request failed: {e}",
            }

    def create_auth_headers(
        self, token: str, additional_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        Create authentication headers for requests.

        Args:
            token: JWT token
            additional_headers: Additional headers to include

        Returns:
            Headers dictionary
        """
        headers = {"Authorization": f"Bearer {token}"}

        if additional_headers:
            headers.update(additional_headers)

        return headers

    def login_and_get_headers(
        self,
        username: str,
        password: str,
        additional_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, str]]:
        """
        Convenience method to login and get auth headers.

        Args:
            username: Username
            password: Password
            additional_headers: Additional headers to include

        Returns:
            Headers dictionary or None if login failed
        """
        result = self.login_user(username, password)

        if result["success"]:
            return self.create_auth_headers(result["token"], additional_headers)

        return None

    def get_session_for_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get stored session for user.

        Args:
            username: Username

        Returns:
            Session data or None if not found
        """
        return self.authenticated_sessions.get(username)

    def logout_user(self, username: str) -> bool:
        """
        Logout user and clear session.

        Args:
            username: Username to logout

        Returns:
            True if user was logged out
        """
        if username in self.authenticated_sessions:
            del self.authenticated_sessions[username]
            self.logger.info(f"User logged out: {username}")
            return True

        return False

    def logout_all_users(self) -> int:
        """
        Logout all users and clear all sessions.

        Returns:
            Number of users logged out
        """
        count = len(self.authenticated_sessions)
        self.authenticated_sessions.clear()

        self.logger.info(f"All users logged out: {count} sessions cleared")
        return count

    def create_test_users_with_roles(self) -> List[Dict[str, Any]]:
        """
        Create standard test users with different roles.

        Returns:
            List of user data dictionaries
        """
        return [
            {
                "username": "admin_test",
                "password": "admin_password",
                "role": "admin",
                "email": "admin@test.com",
            },
            {
                "username": "power_test",
                "password": "power_password",
                "role": "power_user",
                "email": "power@test.com",
            },
            {
                "username": "normal_test",
                "password": "normal_password",
                "role": "normal_user",
                "email": "normal@test.com",
            },
            {
                "username": "user_test",
                "password": "user_password",
                "role": "normal_user",
                "email": "user@test.com",
            },
        ]

    def login_multiple_users(
        self, users: List[Dict[str, str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Login multiple users.

        Args:
            users: List of user dictionaries with username/password

        Returns:
            Dictionary mapping usernames to login results
        """
        results = {}

        for user_spec in users:
            username = user_spec["username"]
            password = user_spec["password"]

            result = self.login_user(username, password)
            results[username] = result

        successful_logins = sum(1 for r in results.values() if r["success"])
        self.logger.info(f"Logged in {successful_logins}/{len(users)} users")

        return results

    def verify_role_hierarchy(self, higher_role: str, lower_role: str) -> bool:
        """
        Verify role hierarchy for testing role-based access control.

        Args:
            higher_role: Role that should have higher privileges
            lower_role: Role that should have lower privileges

        Returns:
            True if hierarchy is correct
        """
        role_levels = {"admin": 3, "power_user": 2, "normal_user": 1}

        higher_level = role_levels.get(higher_role, 0)
        lower_level = role_levels.get(lower_role, 0)

        return higher_level > lower_level

    def create_test_jwt_token(
        self, user_data: Dict[str, Any], expires_minutes: int = 60
    ) -> str:
        """
        Create a test JWT token for authentication testing.

        Args:
            user_data: User data to include in token
            expires_minutes: Token expiry time

        Returns:
            JWT token string
        """
        return self.jwt_manager.generate_token(user_data, expires_minutes)

    def simulate_token_expiry(
        self, username: str, minutes_ago: int = 60
    ) -> Optional[str]:
        """
        Create an expired token for testing token expiry scenarios.

        Args:
            username: Username for the token
            minutes_ago: How many minutes ago the token should have expired

        Returns:
            Expired JWT token or None if user session not found
        """
        session = self.get_session_for_user(username)
        if not session:
            return None

        user_data = session["user"].copy()
        user_data["username"] = username

        # Create token that expired in the past
        past_time = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago + 30)
        expiry_time = past_time + timedelta(minutes=30)  # Expired 'minutes_ago' ago

        payload = {
            "sub": username,
            "user_id": str(user_data.get("user_id", username)),
            "role": user_data["role"],
            "iat": int(past_time.timestamp()),
            "exp": int(expiry_time.timestamp()),
            "jti": self.jwt_manager._generate_jti(),
            "test_token": True,
        }

        expired_token = jwt.encode(
            payload, self.jwt_manager.secret_key, algorithm=self.jwt_manager.algorithm
        )

        self.logger.debug(f"Created expired token for user: {username}")
        return expired_token

    def make_authenticated_request(
        self,
        method: str,
        endpoint: str,
        username: str,
        json_data: Optional[Dict[str, Any]] = None,
        additional_headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """
        Make authenticated API request using stored session.

        Args:
            method: HTTP method
            endpoint: API endpoint
            username: Username for authentication
            json_data: Optional JSON data
            additional_headers: Additional headers
            timeout: Request timeout

        Returns:
            Response object

        Raises:
            ValueError: If user is not logged in
        """
        session = self.get_session_for_user(username)
        if not session:
            raise ValueError(f"User {username} is not logged in")

        headers = self.create_auth_headers(session["token"], additional_headers)
        url = f"{self.server_url}{endpoint}"

        timeout = timeout or self.default_timeout

        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=json_data,
            timeout=timeout,
        )

        self.logger.debug(
            f"Made {method} request to {endpoint} as {username}: {response.status_code}"
        )
        return response

    def test_endpoint_permissions(
        self,
        endpoint: str,
        method: str = "GET",
        expected_roles: Optional[List[str]] = None,
        forbidden_roles: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Test endpoint permissions for different user roles.

        Args:
            endpoint: API endpoint to test
            method: HTTP method
            expected_roles: Roles that should have access
            forbidden_roles: Roles that should be forbidden

        Returns:
            Dictionary mapping roles to test results
        """
        results = {}

        # Get test users for each role
        test_users = {
            "admin": "admin_test",
            "power_user": "power_test",
            "normal_user": "normal_test",
        }

        for role, username in test_users.items():
            if username not in self.authenticated_sessions:
                continue  # Skip if user not logged in

            try:
                response = self.make_authenticated_request(method, endpoint, username)

                results[role] = {
                    "status_code": response.status_code,
                    "allowed": response.status_code != 403,
                    "response_data": (
                        response.json()
                        if response.headers.get("content-type", "").startswith(
                            "application/json"
                        )
                        else None
                    ),
                }

            except Exception as e:
                results[role] = {"status_code": None, "allowed": False, "error": str(e)}

        # Verify expected permissions
        if expected_roles:
            for role in expected_roles:
                if role in results and not results[role]["allowed"]:
                    self.logger.warning(
                        f"Role {role} should have access to {endpoint} but was denied"
                    )

        if forbidden_roles:
            for role in forbidden_roles:
                if role in results and results[role]["allowed"]:
                    self.logger.warning(
                        f"Role {role} should not have access to {endpoint} but was allowed"
                    )

        return results

    def get_active_sessions_count(self) -> int:
        """Get number of active authenticated sessions."""
        return len(self.authenticated_sessions)

    def get_active_usernames(self) -> List[str]:
        """Get list of usernames with active sessions."""
        return list(self.authenticated_sessions.keys())

    def cleanup(self) -> None:
        """Clean up all sessions and data."""
        self.logout_all_users()
        self.logger.info("Authentication test helper cleaned up")


# Convenience functions
def create_test_auth_environment(server_url: str) -> AuthTestHelper:
    """
    Create complete authentication test environment.

    Args:
        server_url: Server URL for authentication

    Returns:
        Configured AuthTestHelper
    """
    helper = AuthTestHelper(server_url)

    # Create and login standard test users
    helper.create_test_users_with_roles()

    # Note: Actual login would happen in E2E tests when server is running
    # This function just creates the helper with standard user definitions

    return helper


def verify_jwt_token_structure(token: str) -> Dict[str, Any]:
    """
    Verify JWT token structure without validation.

    Args:
        token: JWT token to analyze

    Returns:
        Token analysis dictionary
    """
    parts = token.split(".")

    analysis = {"valid_structure": len(parts) == 3, "parts_count": len(parts)}

    if len(parts) >= 2:
        try:
            import base64
            import json

            # Decode header
            header_data = base64.b64decode(parts[0] + "==")
            header = json.loads(header_data)
            analysis["header"] = header

            # Decode payload (without verification)
            payload_data = base64.b64decode(parts[1] + "==")
            payload = json.loads(payload_data)
            analysis["payload"] = payload

        except Exception as e:
            analysis["decode_error"] = str(e)

    return analysis
