"""
Unit tests for JWT authentication system.

Tests JWT token creation, validation, role-based access control,
and configurable token expiration with activity-based extension.
"""

import pytest
from datetime import datetime, timedelta, timezone
import json
import tempfile
import os

# These imports will fail initially - that's the TDD approach
from code_indexer.server.auth.jwt_manager import (
    JWTManager,
    TokenExpiredError,
    InvalidTokenError,
)
from code_indexer.server.auth.user_manager import UserManager, User, UserRole
from code_indexer.server.auth.password_manager import PasswordManager


class TestJWTManager:
    """Test JWT token creation, validation, and expiration logic."""

    @pytest.fixture
    def jwt_manager(self):
        """Create JWT manager instance with test secret."""
        return JWTManager(
            secret_key="test-secret-key-for-jwt-signing",
            token_expiration_minutes=10,
            algorithm="HS256",
        )

    def test_create_jwt_token_for_admin_user(self, jwt_manager):
        """Test creating JWT token for admin user."""
        user_data = {
            "username": "admin",
            "role": "admin",
            "created_at": "2024-08-30T10:00:00Z",
        }

        token = jwt_manager.create_token(user_data)

        # Token should be a non-empty string
        assert isinstance(token, str)
        assert len(token) > 0
        assert "." in token  # JWT format has dots

    def test_create_jwt_token_for_power_user(self, jwt_manager):
        """Test creating JWT token for power user."""
        user_data = {
            "username": "poweruser",
            "role": "power_user",
            "created_at": "2024-08-30T10:00:00Z",
        }

        token = jwt_manager.create_token(user_data)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_jwt_token_for_normal_user(self, jwt_manager):
        """Test creating JWT token for normal user."""
        user_data = {
            "username": "normaluser",
            "role": "normal_user",
            "created_at": "2024-08-30T10:00:00Z",
        }

        token = jwt_manager.create_token(user_data)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_validate_valid_jwt_token(self, jwt_manager):
        """Test validating a valid JWT token."""
        user_data = {
            "username": "testuser",
            "role": "admin",
            "created_at": "2024-08-30T10:00:00Z",
        }

        token = jwt_manager.create_token(user_data)
        decoded_data = jwt_manager.validate_token(token)

        assert decoded_data["username"] == "testuser"
        assert decoded_data["role"] == "admin"
        assert "exp" in decoded_data
        assert "iat" in decoded_data

    def test_validate_expired_jwt_token(self, jwt_manager):
        """Test validating an expired JWT token raises TokenExpiredError."""
        # Create a token with -1 minute expiration (already expired)
        expired_jwt_manager = JWTManager(
            secret_key="test-secret-key-for-jwt-signing",
            token_expiration_minutes=-1,
            algorithm="HS256",
        )

        user_data = {
            "username": "testuser",
            "role": "admin",
            "created_at": "2024-08-30T10:00:00Z",
        }

        token = expired_jwt_manager.create_token(user_data)

        with pytest.raises(TokenExpiredError):
            jwt_manager.validate_token(token)

    def test_validate_invalid_jwt_token(self, jwt_manager):
        """Test validating an invalid JWT token raises InvalidTokenError."""
        invalid_token = "invalid.jwt.token"

        with pytest.raises(InvalidTokenError):
            jwt_manager.validate_token(invalid_token)

    def test_validate_token_with_wrong_secret(self, jwt_manager):
        """Test validating token created with different secret fails."""
        user_data = {
            "username": "testuser",
            "role": "admin",
            "created_at": "2024-08-30T10:00:00Z",
        }

        # Create token with one secret
        token = jwt_manager.create_token(user_data)

        # Try to validate with different secret
        different_jwt_manager = JWTManager(
            secret_key="different-secret-key",
            token_expiration_minutes=10,
            algorithm="HS256",
        )

        with pytest.raises(InvalidTokenError):
            different_jwt_manager.validate_token(token)

    def test_token_contains_expiration_time(self, jwt_manager):
        """Test that JWT token contains proper expiration time."""
        user_data = {
            "username": "testuser",
            "role": "admin",
            "created_at": "2024-08-30T10:00:00Z",
        }

        before_creation = datetime.now(timezone.utc)
        token = jwt_manager.create_token(user_data)
        after_creation = datetime.now(timezone.utc)

        decoded_data = jwt_manager.validate_token(token)

        # Check expiration time is roughly 10 minutes from now
        exp_time = datetime.fromtimestamp(decoded_data["exp"], timezone.utc)
        expected_min = (
            before_creation + timedelta(minutes=10) - timedelta(seconds=1)
        )  # Add 1 second tolerance
        expected_max = (
            after_creation + timedelta(minutes=10) + timedelta(seconds=1)
        )  # Add 1 second tolerance

        assert expected_min <= exp_time <= expected_max

    def test_configurable_token_expiration(self):
        """Test that token expiration time is configurable."""
        # Test with 5 minute expiration
        jwt_manager_5min = JWTManager(
            secret_key="test-secret", token_expiration_minutes=5, algorithm="HS256"
        )

        user_data = {
            "username": "testuser",
            "role": "admin",
            "created_at": "2024-08-30T10:00:00Z",
        }

        before_creation = datetime.now(timezone.utc)
        token = jwt_manager_5min.create_token(user_data)

        decoded_data = jwt_manager_5min.validate_token(token)
        exp_time = datetime.fromtimestamp(decoded_data["exp"], timezone.utc)

        # Should expire in approximately 5 minutes
        expected_exp = before_creation + timedelta(minutes=5)
        time_diff = abs((exp_time - expected_exp).total_seconds())
        assert time_diff < 10  # Within 10 seconds tolerance

    def test_extend_token_expiration_on_activity(self, jwt_manager):
        """Test extending token expiration on API activity."""
        user_data = {
            "username": "testuser",
            "role": "admin",
            "created_at": "2024-08-30T10:00:00Z",
        }

        # Create initial token
        original_token = jwt_manager.create_token(user_data)
        original_decoded = jwt_manager.validate_token(original_token)
        original_exp = original_decoded["exp"]

        # Wait a moment to ensure different timestamp (JWT uses second precision)
        import time

        time.sleep(1)

        # Extend token (simulates API activity)
        extended_token = jwt_manager.extend_token_expiration(original_token)
        extended_decoded = jwt_manager.validate_token(extended_token)
        extended_exp = extended_decoded["exp"]

        # Extended expiration should be later than original
        assert extended_exp > original_exp

        # Should preserve all original claims except exp and iat
        assert extended_decoded["username"] == original_decoded["username"]
        assert extended_decoded["role"] == original_decoded["role"]

    def test_extend_expired_token_fails(self, jwt_manager):
        """Test that extending an expired token raises TokenExpiredError."""
        # Create expired token
        expired_jwt_manager = JWTManager(
            secret_key="test-secret-key-for-jwt-signing",
            token_expiration_minutes=-1,
            algorithm="HS256",
        )

        user_data = {
            "username": "testuser",
            "role": "admin",
            "created_at": "2024-08-30T10:00:00Z",
        }

        expired_token = expired_jwt_manager.create_token(user_data)

        with pytest.raises(TokenExpiredError):
            jwt_manager.extend_token_expiration(expired_token)


class TestUserRole:
    """Test user role enum and validation."""

    def test_user_role_enum_values(self):
        """Test that UserRole enum has correct values."""
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.POWER_USER.value == "power_user"
        assert UserRole.NORMAL_USER.value == "normal_user"

    def test_user_role_from_string(self):
        """Test creating UserRole from string values."""
        assert UserRole("admin") == UserRole.ADMIN
        assert UserRole("power_user") == UserRole.POWER_USER
        assert UserRole("normal_user") == UserRole.NORMAL_USER

    def test_invalid_user_role_raises_error(self):
        """Test that invalid role string raises ValueError."""
        with pytest.raises(ValueError):
            UserRole("invalid_role")


class TestUser:
    """Test User data model."""

    def test_create_admin_user(self):
        """Test creating admin user instance."""
        user = User(
            username="admin",
            password_hash="$2b$12$test_hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

        assert user.username == "admin"
        assert user.role == UserRole.ADMIN
        assert user.password_hash == "$2b$12$test_hash"
        assert isinstance(user.created_at, datetime)

    def test_create_power_user(self):
        """Test creating power user instance."""
        user = User(
            username="poweruser",
            password_hash="$2b$12$test_hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )

        assert user.username == "poweruser"
        assert user.role == UserRole.POWER_USER

    def test_create_normal_user(self):
        """Test creating normal user instance."""
        user = User(
            username="normaluser",
            password_hash="$2b$12$test_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        assert user.username == "normaluser"
        assert user.role == UserRole.NORMAL_USER

    def test_user_to_dict(self):
        """Test converting user to dictionary."""
        created_time = datetime.now(timezone.utc)
        user = User(
            username="testuser",
            password_hash="$2b$12$test_hash",
            role=UserRole.ADMIN,
            created_at=created_time,
        )

        user_dict = user.to_dict()

        assert user_dict["username"] == "testuser"
        assert user_dict["role"] == "admin"
        assert user_dict["created_at"] == created_time.isoformat()
        # Password hash should NOT be included in dict
        assert "password_hash" not in user_dict

    def test_user_has_permission_admin(self):
        """Test that admin user has all permissions."""
        admin = User(
            username="admin",
            password_hash="hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

        assert admin.has_permission("manage_users")
        assert admin.has_permission("manage_golden_repos")
        assert admin.has_permission("activate_repos")
        assert admin.has_permission("query_repos")

    def test_user_has_permission_power_user(self):
        """Test that power user has activate and query permissions."""
        power_user = User(
            username="poweruser",
            password_hash="hash",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )

        assert not power_user.has_permission("manage_users")
        assert not power_user.has_permission("manage_golden_repos")
        assert power_user.has_permission("activate_repos")
        assert power_user.has_permission("query_repos")

    def test_user_has_permission_normal_user(self):
        """Test that normal user has only query permission."""
        normal_user = User(
            username="normaluser",
            password_hash="hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        assert not normal_user.has_permission("manage_users")
        assert not normal_user.has_permission("manage_golden_repos")
        assert not normal_user.has_permission("activate_repos")
        assert normal_user.has_permission("query_repos")


class TestPasswordManager:
    """Test password hashing and verification."""

    @pytest.fixture
    def password_manager(self):
        """Create password manager instance."""
        return PasswordManager()

    def test_hash_password(self, password_manager):
        """Test password hashing produces secure hash."""
        password = "secure_password123"

        password_hash = password_manager.hash_password(password)

        assert isinstance(password_hash, str)
        assert len(password_hash) > 0
        assert password_hash != password  # Should be hashed, not plaintext
        assert password_hash.startswith("$2b$")  # bcrypt format

    def test_verify_correct_password(self, password_manager):
        """Test verifying correct password returns True."""
        password = "correct_password"
        password_hash = password_manager.hash_password(password)

        is_valid = password_manager.verify_password(password, password_hash)

        assert is_valid

    def test_verify_incorrect_password(self, password_manager):
        """Test verifying incorrect password returns False."""
        correct_password = "correct_password"
        incorrect_password = "wrong_password"
        password_hash = password_manager.hash_password(correct_password)

        is_valid = password_manager.verify_password(incorrect_password, password_hash)

        assert not is_valid

    def test_hash_same_password_twice_different_hashes(self, password_manager):
        """Test that hashing same password twice produces different hashes (salt)."""
        password = "same_password"

        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)

        assert hash1 != hash2  # Different due to random salt

        # But both should verify correctly
        assert password_manager.verify_password(password, hash1)
        assert password_manager.verify_password(password, hash2)


class TestUserManager:
    """Test user management with ~/.cidx-server/users.json storage."""

    @pytest.fixture
    def temp_users_file(self):
        """Create temporary users.json file."""
        temp_dir = tempfile.mkdtemp()
        users_file = os.path.join(temp_dir, "users.json")
        return users_file

    @pytest.fixture
    def user_manager(self, temp_users_file):
        """Create user manager with temporary users file."""
        return UserManager(users_file_path=temp_users_file)

    def test_create_initial_admin_user_on_empty_file(
        self, user_manager, temp_users_file
    ):
        """Test creating initial admin user when users.json doesn't exist."""
        # Ensure initial admin user is created
        user_manager.seed_initial_admin()

        # Verify file exists and contains admin user
        assert os.path.exists(temp_users_file)

        with open(temp_users_file, "r") as f:
            users_data = json.load(f)

        assert "admin" in users_data
        admin_data = users_data["admin"]
        assert admin_data["role"] == "admin"
        assert "password_hash" in admin_data
        assert "created_at" in admin_data

    def test_verify_initial_admin_credentials(self, user_manager):
        """Test that initial admin user has correct credentials (admin/admin)."""
        user_manager.seed_initial_admin()

        # Should be able to authenticate with admin/admin
        user = user_manager.authenticate_user("admin", "admin")

        assert user is not None
        assert user.username == "admin"
        assert user.role == UserRole.ADMIN

    def test_create_new_user(self, user_manager):
        """Test creating new user and persisting to users.json."""
        user = user_manager.create_user(
            username="testuser", password="TestPassword123!", role=UserRole.POWER_USER
        )

        assert user.username == "testuser"
        assert user.role == UserRole.POWER_USER

        # Verify user persisted to file
        loaded_user = user_manager.get_user("testuser")
        assert loaded_user is not None
        assert loaded_user.username == "testuser"
        assert loaded_user.role == UserRole.POWER_USER

    def test_create_duplicate_user_raises_error(self, user_manager):
        """Test that creating user with existing username raises error."""
        user_manager.create_user("testuser", "TestPassword123!", UserRole.NORMAL_USER)

        with pytest.raises(ValueError, match="User already exists"):
            user_manager.create_user("testuser", "Password2Strong!", UserRole.ADMIN)

    def test_authenticate_user_valid_credentials(self, user_manager):
        """Test authenticating user with valid credentials."""
        user_manager.create_user("testuser", "TestPassword123!", UserRole.NORMAL_USER)

        authenticated_user = user_manager.authenticate_user(
            "testuser", "TestPassword123!"
        )

        assert authenticated_user is not None
        assert authenticated_user.username == "testuser"
        assert authenticated_user.role == UserRole.NORMAL_USER

    def test_authenticate_user_invalid_password(self, user_manager):
        """Test authenticating user with invalid password returns None."""
        user_manager.create_user(
            "testuser", "CorrectPassword123!", UserRole.NORMAL_USER
        )

        authenticated_user = user_manager.authenticate_user(
            "testuser", "WrongPassword123!"
        )

        assert authenticated_user is None

    def test_authenticate_user_nonexistent_user(self, user_manager):
        """Test authenticating nonexistent user returns None."""
        authenticated_user = user_manager.authenticate_user(
            "nonexistent", "TestPassword123!"
        )

        assert authenticated_user is None

    def test_get_all_users(self, user_manager):
        """Test getting all users from storage."""
        user_manager.create_user("user1", "Unique1Passphrase!", UserRole.ADMIN)
        user_manager.create_user("user2", "Unique2Passphrase!", UserRole.POWER_USER)
        user_manager.create_user("user3", "Unique3Passphrase!", UserRole.NORMAL_USER)

        all_users = user_manager.get_all_users()

        assert len(all_users) == 3
        usernames = [user.username for user in all_users]
        assert "user1" in usernames
        assert "user2" in usernames
        assert "user3" in usernames

    def test_delete_user(self, user_manager):
        """Test deleting user from storage."""
        user_manager.create_user("testuser", "TestPassword123!", UserRole.NORMAL_USER)

        # Verify user exists
        user = user_manager.get_user("testuser")
        assert user is not None

        # Delete user
        success = user_manager.delete_user("testuser")
        assert success

        # Verify user no longer exists
        user = user_manager.get_user("testuser")
        assert user is None

    def test_delete_nonexistent_user(self, user_manager):
        """Test deleting nonexistent user returns False."""
        success = user_manager.delete_user("nonexistent")
        assert not success

    def test_update_user_role(self, user_manager):
        """Test updating user role."""
        user_manager.create_user("testuser", "TestPassword123!", UserRole.NORMAL_USER)

        success = user_manager.update_user_role("testuser", UserRole.POWER_USER)
        assert success

        # Verify role updated
        updated_user = user_manager.get_user("testuser")
        assert updated_user.role == UserRole.POWER_USER

    def test_change_user_password(self, user_manager):
        """Test changing user password."""
        user_manager.create_user("testuser", "OldPassword123!", UserRole.NORMAL_USER)

        success = user_manager.change_password("testuser", "NewPassword123!")
        assert success

        # Verify old password no longer works
        user = user_manager.authenticate_user("testuser", "OldPassword123!")
        assert user is None

        # Verify new password works
        user = user_manager.authenticate_user("testuser", "NewPassword123!")
        assert user is not None
        assert user.username == "testuser"

    def test_users_json_file_format(self, user_manager, temp_users_file):
        """Test that users.json file has correct format."""
        user_manager.create_user("testuser", "TestPassword123!", UserRole.POWER_USER)

        with open(temp_users_file, "r") as f:
            users_data = json.load(f)

        assert isinstance(users_data, dict)
        assert "testuser" in users_data

        user_data = users_data["testuser"]
        assert "role" in user_data
        assert "password_hash" in user_data
        assert "created_at" in user_data

        assert user_data["role"] == "power_user"
        assert user_data["password_hash"].startswith("$2b$")  # bcrypt format

        # Verify created_at is valid ISO format
        from datetime import datetime

        created_at = datetime.fromisoformat(
            user_data["created_at"].replace("Z", "+00:00")
        )
        assert isinstance(created_at, datetime)
