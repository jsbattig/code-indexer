"""
TDD Test Suite for User Role Preservation Fix.

MESSI RULE #1 COMPLIANCE: ZERO MOCKS - REAL SYSTEMS ONLY

This test suite reproduces the bug where user roles are not preserved
through the refresh token flow, always defaulting to 'normal_user'.

RED-GREEN-REFACTOR: Writing failing tests first to reproduce the exact issue.
"""

import tempfile
import shutil
from pathlib import Path

from code_indexer.server.auth.jwt_manager import JWTManager
from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth.refresh_token_manager import RefreshTokenManager
from code_indexer.server.utils.config_manager import PasswordSecurityConfig
from code_indexer.server.utils.jwt_secret_manager import JWTSecretManager


class TestUserRolePreservationFix:
    """
    TDD test suite for user role preservation through refresh token flow.

    RED PHASE: These tests should FAIL until the hardcoded role is fixed.
    """

    def setup_method(self):
        """Set up real test environment with actual components."""
        # Create temporary directory for test data
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Initialize REAL components
        self.jwt_secret_manager = JWTSecretManager(
            str(self.temp_path / "jwt_secret.key")
        )
        self.jwt_manager = JWTManager(
            secret_key=self.jwt_secret_manager.get_or_create_secret(),
            algorithm="HS256",
            token_expiration_minutes=15,
        )

        # Create REAL user manager with weak password config for testing
        self.users_file_path = self.temp_path / "users.json"
        weak_password_config = PasswordSecurityConfig(
            min_length=1,
            max_length=128,
            required_char_classes=0,
            min_entropy_bits=0,
            check_common_passwords=False,
            check_personal_info=False,
            check_keyboard_patterns=False,
            check_sequential_chars=False,
        )
        self.user_manager = UserManager(
            users_file_path=str(self.users_file_path),
            password_security_config=weak_password_config,
        )

        # Create REAL refresh token manager
        self.refresh_db_path = self.temp_path / "refresh_tokens.db"
        self.refresh_token_manager = RefreshTokenManager(
            jwt_manager=self.jwt_manager,
            db_path=str(self.refresh_db_path),
            refresh_token_lifetime_days=7,
        )

        # Create test users with different roles
        self.user_manager.create_user(
            username="normal_user", password="NormalUser123!", role=UserRole.NORMAL_USER
        )
        self.user_manager.create_user(
            username="admin_user", password="AdminUser456!", role=UserRole.ADMIN
        )
        self.user_manager.create_user(
            username="power_user", password="PowerUser789!", role=UserRole.POWER_USER
        )

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_admin_role_preserved_through_refresh(self):
        """
        RED TEST: This should FAIL showing admin role becoming normal_user.

        When an admin user's token is refreshed, the role should remain 'admin',
        not default to 'normal_user'.
        """
        # Create initial tokens for admin user
        family_id = self.refresh_token_manager.create_token_family("admin_user")

        # Get the actual user data from user manager
        admin_user = self.user_manager.get_user("admin_user")
        assert admin_user.role == UserRole.ADMIN  # Verify test setup

        # Create initial token with correct role
        initial_user_data = {"username": "admin_user", "role": "admin"}
        token_response = self.refresh_token_manager.create_initial_refresh_token(
            family_id=family_id, username="admin_user", user_data=initial_user_data
        )

        # Refresh the token - this is where the bug occurs
        refresh_result = self.refresh_token_manager.validate_and_rotate_refresh_token(
            refresh_token=token_response["refresh_token"],
            user_manager=self.user_manager,
        )

        # CRITICAL BUG: Role should be 'admin' but becomes 'normal_user'
        assert refresh_result["valid"], "Token refresh should succeed"
        refreshed_user_data = refresh_result["user_data"]

        assert refreshed_user_data["role"] == "admin", (
            f"Admin user role should be preserved as 'admin', "
            f"but got '{refreshed_user_data['role']}'. This indicates "
            f"the refresh token manager is using hardcoded 'normal_user' role."
        )

    def test_power_user_role_preserved_through_refresh(self):
        """
        RED TEST: Test power user role preservation.

        Power user role should be preserved through refresh, not default to normal_user.
        """
        # Create initial tokens for power user
        family_id = self.refresh_token_manager.create_token_family("power_user")

        # Verify user has correct role
        power_user = self.user_manager.get_user("power_user")
        assert power_user.role == UserRole.POWER_USER

        # Create initial token
        initial_user_data = {"username": "power_user", "role": "power_user"}
        token_response = self.refresh_token_manager.create_initial_refresh_token(
            family_id=family_id, username="power_user", user_data=initial_user_data
        )

        # Refresh the token
        refresh_result = self.refresh_token_manager.validate_and_rotate_refresh_token(
            refresh_token=token_response["refresh_token"],
            user_manager=self.user_manager,
        )

        # Role should be preserved
        assert refresh_result["valid"], "Token refresh should succeed"
        refreshed_user_data = refresh_result["user_data"]

        assert refreshed_user_data["role"] == "power_user", (
            f"Power user role should be preserved as 'power_user', "
            f"but got '{refreshed_user_data['role']}'."
        )

    def test_normal_user_role_correctly_maintained(self):
        """
        GREEN TEST: Normal user role should work correctly.

        Normal users should maintain their role through refresh.
        """
        # Create initial tokens for normal user
        family_id = self.refresh_token_manager.create_token_family("normal_user")

        # Verify user has correct role
        normal_user = self.user_manager.get_user("normal_user")
        assert normal_user.role == UserRole.NORMAL_USER

        # Create initial token
        initial_user_data = {"username": "normal_user", "role": "normal_user"}
        token_response = self.refresh_token_manager.create_initial_refresh_token(
            family_id=family_id, username="normal_user", user_data=initial_user_data
        )

        # Refresh the token
        refresh_result = self.refresh_token_manager.validate_and_rotate_refresh_token(
            refresh_token=token_response["refresh_token"],
            user_manager=self.user_manager,
        )

        # Role should be preserved (this might pass even with the bug)
        assert refresh_result["valid"], "Token refresh should succeed"
        refreshed_user_data = refresh_result["user_data"]

        assert refreshed_user_data["role"] == "normal_user", (
            f"Normal user role should be preserved as 'normal_user', "
            f"but got '{refreshed_user_data['role']}'."
        )

    def test_all_role_types_preserved_systematically(self):
        """
        GREEN TEST: Comprehensive test of all role types.

        All user roles should be preserved through refresh token flow
        without any hardcoded defaults.
        """
        test_cases = [
            ("normal_user", "normal_user", UserRole.NORMAL_USER),
            ("admin_user", "admin", UserRole.ADMIN),
            ("power_user", "power_user", UserRole.POWER_USER),
        ]

        for username, expected_role_str, expected_role_enum in test_cases:
            # Create token family
            family_id = self.refresh_token_manager.create_token_family(username)

            # Verify user has correct role in database
            user = self.user_manager.get_user(username)
            assert user.role == expected_role_enum

            # Create initial token with correct role
            initial_user_data = {"username": username, "role": expected_role_str}
            token_response = self.refresh_token_manager.create_initial_refresh_token(
                family_id=family_id, username=username, user_data=initial_user_data
            )

            # Refresh the token
            refresh_result = (
                self.refresh_token_manager.validate_and_rotate_refresh_token(
                    refresh_token=token_response["refresh_token"],
                    user_manager=self.user_manager,
                )
            )

            # Verify role preservation
            assert refresh_result[
                "valid"
            ], f"Token refresh should succeed for {username}"
            refreshed_user_data = refresh_result["user_data"]

            assert refreshed_user_data["role"] == expected_role_str, (
                f"User {username} role should be preserved as '{expected_role_str}', "
                f"but got '{refreshed_user_data['role']}'. This indicates hardcoded role issue."
            )


# TDD VERDICT: 🔴 RED PHASE
# These tests should FAIL until the hardcoded 'normal_user' role in
# RefreshTokenManager.validate_and_rotate_refresh_token() is fixed to
# retrieve the actual user role from the user manager.
