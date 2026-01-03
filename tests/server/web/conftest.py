"""
Pytest fixtures for web admin UI tests.

Provides real-component fixtures following MESSI Rule #1: No mocks.
All fixtures use real FastAPI app with real security components.
"""

import os
import re
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Generator, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth import dependencies
from code_indexer.server.utils.config_manager import PasswordSecurityConfig


class WebTestInfrastructure:
    """
    Real component test infrastructure for web admin UI tests.

    ZERO MOCKS - Uses real FastAPI app with real security components.
    """

    def __init__(self):
        """Initialize test infrastructure."""
        self.temp_dir: Optional[Path] = None
        self.app: Optional[FastAPI] = None
        self.client: Optional[TestClient] = None
        self.user_manager: Optional[UserManager] = None
        self._original_cidx_server_dir: Optional[str] = None
        self._original_dependencies: Optional[Dict[str, Any]] = None

    @staticmethod
    def create_weak_password_config() -> PasswordSecurityConfig:
        """Create weak password config for testing simple passwords."""
        return PasswordSecurityConfig(
            min_length=1,
            max_length=128,
            required_char_classes=0,
            min_entropy_bits=0,
            check_common_passwords=False,
            check_personal_info=False,
            check_keyboard_patterns=False,
            check_sequential_chars=False,
        )

    def setup(self) -> None:
        """Set up isolated test environment with real components."""
        # Create isolated temporary directory
        self.temp_dir = Path(tempfile.mkdtemp(prefix="cidx_web_test_"))

        # Override CIDX_SERVER_DATA_DIR to use our temp directory
        self._original_cidx_server_dir = os.environ.get("CIDX_SERVER_DATA_DIR")
        os.environ["CIDX_SERVER_DATA_DIR"] = str(self.temp_dir)

        # Create necessary subdirectories
        (self.temp_dir / "users").mkdir(exist_ok=True)
        (self.temp_dir / "audit").mkdir(exist_ok=True)
        (self.temp_dir / "tokens").mkdir(exist_ok=True)
        (self.temp_dir / "data" / "golden-repos").mkdir(parents=True, exist_ok=True)

        # Store original dependencies
        self._original_dependencies = {
            "jwt_manager": getattr(dependencies, "jwt_manager", None),
            "user_manager": getattr(dependencies, "user_manager", None),
        }

        # Create test user manager with weak password config BEFORE creating app
        weak_password_config = self.create_weak_password_config()
        users_file_path = str(self.temp_dir / "users.json")
        test_user_manager = UserManager(
            users_file_path=users_file_path,
            password_security_config=weak_password_config,
        )

        # Create real FastAPI app
        self.app = create_app()

        # Override the user manager in dependencies after app creation
        dependencies.user_manager = test_user_manager

        # Also override in app module since it imports directly
        import code_indexer.server.app as app_module

        app_module.user_manager = test_user_manager

        self.user_manager = test_user_manager

        # Initialize log database path for logs routes (Story #664, #665, #667)
        log_db_path = self.temp_dir / "logs.db"
        self.app.state.log_db_path = str(log_db_path)

        # Create test client - IMPORTANT: don't follow redirects by default
        # so we can test redirect behavior
        self.client = TestClient(self.app, follow_redirects=False)

    def create_admin_user(
        self, username: str = "testadmin", password: str = "TestAdmin@123!"
    ) -> Dict[str, Any]:
        """Create an admin user for testing.

        Uses a password that meets security requirements:
        - 12+ characters
        - Uppercase letters
        - Lowercase letters
        - Numbers
        - Special characters
        """
        if not self.user_manager:
            raise RuntimeError("Test infrastructure not initialized")

        user = self.user_manager.create_user(username, password, UserRole.ADMIN)
        return {
            "username": user.username,
            "password": password,
            "role": user.role.value,
        }

    def create_normal_user(
        self, username: str = "testuser", password: str = "TestUser@456!"
    ) -> Dict[str, Any]:
        """Create a normal (non-admin) user for testing.

        Uses a password that meets security requirements:
        - 12+ characters
        - Uppercase letters
        - Lowercase letters
        - Numbers
        - Special characters
        """
        if not self.user_manager:
            raise RuntimeError("Test infrastructure not initialized")

        user = self.user_manager.create_user(username, password, UserRole.NORMAL_USER)
        return {
            "username": user.username,
            "password": password,
            "role": user.role.value,
        }

    def create_power_user(
        self, username: str = "testpoweruser", password: str = "TestPower@789!"
    ) -> Dict[str, Any]:
        """Create a power user for testing.

        Uses a password that meets security requirements:
        - 12+ characters
        - Uppercase letters
        - Lowercase letters
        - Numbers
        - Special characters
        """
        if not self.user_manager:
            raise RuntimeError("Test infrastructure not initialized")

        user = self.user_manager.create_user(username, password, UserRole.POWER_USER)
        return {
            "username": user.username,
            "password": password,
            "role": user.role.value,
        }

    def _create_session_directly(
        self, client: TestClient, username: str, role: str
    ) -> None:
        """
        Directly create a session and inject it into the test client.

        Bypasses the login endpoint by using the session manager directly.
        Used for non-admin users since /admin/login rejects them.
        """
        from code_indexer.server.web.auth import get_session_manager
        from fastapi import Response

        # Create a dummy response to capture the session cookie
        dummy_response = Response()

        session_manager = get_session_manager()
        session_manager.create_session(
            dummy_response,
            username=username,
            role=role,
        )

        # Extract the session cookie and inject into client
        set_cookie_header = dummy_response.headers.get("set-cookie", "")
        if set_cookie_header:
            # Parse cookie: session_id=value; Path=/; HttpOnly; SameSite=lax
            cookie_parts = set_cookie_header.split(";")
            if cookie_parts:
                cookie_pair = cookie_parts[0].strip()
                if "=" in cookie_pair:
                    cookie_name, cookie_value = cookie_pair.split("=", 1)
                    client.cookies.set(cookie_name, cookie_value)

    def _authenticate_via_login(
        self, client: TestClient, username: str, password: str
    ) -> None:
        """
        Authenticate via unified /login flow (Issue #662 login consolidation).

        Used for admin users. Performs CSRF token extraction and login POST.
        """
        login_response = client.get("/login")
        csrf_token = self.extract_csrf_token(login_response.text)

        if not csrf_token:
            raise ValueError("Could not extract CSRF token from login page")

        # Perform login via unified /login endpoint
        login_data = {
            "username": username,
            "password": password,
            "csrf_token": csrf_token,
        }
        client.post("/login", data=login_data)

    def get_authenticated_client(self, username: str, password: str) -> TestClient:
        """
        Get a TestClient with an authenticated session.

        For non-admin users, creates session directly (bypass admin-only login).
        For admin users, uses normal /admin/login flow.
        """
        if not self.app or not self.user_manager:
            raise RuntimeError("Test infrastructure not initialized")

        # Authenticate to verify credentials and get user object
        user = self.user_manager.authenticate_user(username, password)
        if not user:
            raise ValueError(f"Authentication failed for user {username}")

        # Create client (follow redirects only for admin login flow)
        follow_redirects = user.role == UserRole.ADMIN
        client = TestClient(self.app, follow_redirects=follow_redirects)

        # Route based on role
        if user.role != UserRole.ADMIN:
            # Non-admin: directly create session (bypass admin-only endpoint)
            self._create_session_directly(client, user.username, user.role.value)
        else:
            # Admin: use normal login flow
            self._authenticate_via_login(client, username, password)

        return client

    @staticmethod
    def extract_csrf_token(html: str) -> Optional[str]:
        """Extract CSRF token from HTML form."""
        # Look for hidden input with name csrf_token
        match = re.search(
            r'<input[^>]*name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', html
        )
        if match:
            return match.group(1)

        # Also try reverse order (value before name)
        match = re.search(
            r'<input[^>]*value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']', html
        )
        if match:
            return match.group(1)

        return None

    def cleanup(self) -> None:
        """Clean up test environment and restore original state."""
        # Close test client
        if self.client:
            self.client.close()

        # Restore original dependencies
        if self._original_dependencies:
            for key, value in self._original_dependencies.items():
                if value is not None:
                    setattr(dependencies, key, value)

        # Restore original environment
        if self._original_cidx_server_dir is not None:
            os.environ["CIDX_SERVER_DATA_DIR"] = self._original_cidx_server_dir
        else:
            os.environ.pop("CIDX_SERVER_DATA_DIR", None)

        # Remove temporary directory
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass

        # Reset all references
        self.temp_dir = None
        self.app = None
        self.client = None
        self.user_manager = None
        self._original_cidx_server_dir = None


@pytest.fixture
def web_infrastructure() -> Generator[WebTestInfrastructure, None, None]:
    """
    Pytest fixture providing real component test infrastructure.

    Provides complete setup and cleanup for web admin UI tests.
    """
    infrastructure = WebTestInfrastructure()
    infrastructure.setup()

    try:
        yield infrastructure
    finally:
        infrastructure.cleanup()


@pytest.fixture
def web_client(web_infrastructure: WebTestInfrastructure) -> TestClient:
    """TestClient for web routes (unauthenticated)."""
    assert web_infrastructure.client is not None
    return web_infrastructure.client


@pytest.fixture
def admin_user(web_infrastructure: WebTestInfrastructure) -> Dict[str, Any]:
    """Test admin user credentials."""
    return web_infrastructure.create_admin_user()


@pytest.fixture
def normal_user(web_infrastructure: WebTestInfrastructure) -> Dict[str, Any]:
    """Test non-admin user credentials."""
    return web_infrastructure.create_normal_user()


@pytest.fixture
def power_user(web_infrastructure: WebTestInfrastructure) -> Dict[str, Any]:
    """Test power user credentials."""
    return web_infrastructure.create_power_user()


@pytest.fixture
def authenticated_client(
    web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
) -> TestClient:
    """TestClient with valid admin session."""
    return web_infrastructure.get_authenticated_client(
        admin_user["username"], admin_user["password"]
    )
