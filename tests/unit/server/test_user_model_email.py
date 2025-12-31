"""Unit tests for User model email field."""

import tempfile
import json
import os
from datetime import datetime, timezone
from src.code_indexer.server.auth.user_manager import UserManager, User, UserRole
from src.code_indexer.server.utils.datetime_parser import DateTimeParser


def test_user_model_has_email_field():
    """Test that User model has email field."""
    user = User(
        username="testuser",
        password_hash="hashed",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(timezone.utc),
        email="test@example.com",
    )

    assert hasattr(user, "email")
    assert user.email == "test@example.com"


def test_user_model_email_is_optional():
    """Test that email field is optional (defaults to None)."""
    user = User(
        username="testuser",
        password_hash="hashed",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(timezone.utc),
    )

    assert user.email is None


def test_user_to_dict_includes_email_when_present():
    """Test that to_dict() includes email when set."""
    user = User(
        username="testuser",
        password_hash="hashed",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(timezone.utc),
        email="test@example.com",
    )

    user_dict = user.to_dict()
    assert "email" in user_dict
    assert user_dict["email"] == "test@example.com"


def test_user_to_dict_excludes_email_when_none():
    """Test that to_dict() excludes email when None."""
    user = User(
        username="testuser",
        password_hash="hashed",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(timezone.utc),
        email=None,
    )

    user_dict = user.to_dict()
    assert "email" not in user_dict


def test_get_user_loads_email_from_database():
    """Test that get_user() loads email field from database."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    test_users = {
        "john": {
            "role": "normal_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
            "email": "john@example.com",
        }
    }
    json.dump(test_users, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)
        user = user_manager.get_user("john")

        assert user is not None
        assert user.email == "john@example.com"
    finally:
        os.unlink(temp_file.name)


def test_get_user_loads_none_when_email_missing():
    """Test that get_user() sets email to None when not in database."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    test_users = {
        "john": {
            "role": "normal_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
            # No email field
        }
    }
    json.dump(test_users, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)
        user = user_manager.get_user("john")

        assert user is not None
        assert user.email is None
    finally:
        os.unlink(temp_file.name)


def test_get_all_users_loads_email_for_all():
    """Test that get_all_users() loads email for all users."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    test_users = {
        "john": {
            "role": "normal_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
            "email": "john@example.com",
        },
        "jane": {
            "role": "power_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
            "email": "jane@example.com",
        },
        "bob": {
            "role": "admin",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
            # No email
        },
    }
    json.dump(test_users, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)
        users = user_manager.get_all_users()

        assert len(users) == 3

        john = next(u for u in users if u.username == "john")
        assert john.email == "john@example.com"

        jane = next(u for u in users if u.username == "jane")
        assert jane.email == "jane@example.com"

        bob = next(u for u in users if u.username == "bob")
        assert bob.email is None
    finally:
        os.unlink(temp_file.name)


def test_authenticate_user_loads_email():
    """Test that authenticate_user() loads email field."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({}, temp_file)
    temp_file.close()

    user_manager = UserManager(users_file_path=temp_file.name)

    # Create user with email
    user_manager.create_user("john", "SecurePass123!", UserRole.NORMAL_USER)
    user_manager.update_user("john", new_email="john@example.com")

    try:
        # Authenticate and check email is loaded
        authenticated_user = user_manager.authenticate_user("john", "SecurePass123!")

        assert authenticated_user is not None
        assert authenticated_user.email == "john@example.com"
    finally:
        os.unlink(temp_file.name)


def test_create_oidc_user_includes_email():
    """Test that create_oidc_user() creates user with email."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({}, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)

        oidc_identity = {
            "subject": "oidc-subject-123",
            "email": "oidc@example.com",
            "linked_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat(),
        }

        user = user_manager.create_oidc_user(
            username="oidcuser",
            role=UserRole.NORMAL_USER,
            email="oidc@example.com",
            oidc_identity=oidc_identity,
        )

        assert user.email == "oidc@example.com"

        # Verify it's persisted
        loaded_user = user_manager.get_user("oidcuser")
        assert loaded_user.email == "oidc@example.com"
    finally:
        os.unlink(temp_file.name)


def test_get_user_by_email_returns_user_with_email():
    """Test that get_user_by_email() returns user with email populated."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    test_users = {
        "john": {
            "role": "normal_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
            "email": "john@example.com",
        }
    }
    json.dump(test_users, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)
        user = user_manager.get_user_by_email("john@example.com")

        assert user is not None
        assert user.email == "john@example.com"
        assert user.username == "john"
    finally:
        os.unlink(temp_file.name)


def test_validate_user_api_key_returns_user_with_email():
    """Test that validate_user_api_key() returns user with email populated."""
    import secrets
    from src.code_indexer.server.auth.password_manager import PasswordManager

    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({}, temp_file)
    temp_file.close()

    user_manager = UserManager(users_file_path=temp_file.name)

    # Create user with email
    user_manager.create_user("john", "SecurePass123!", UserRole.NORMAL_USER)
    user_manager.update_user("john", new_email="john@example.com")

    # Manually create API key data
    raw_key = f"cidx_sk_{secrets.token_hex(32)}"
    key_id = "test-key-id"
    password_manager = PasswordManager()
    key_hash = password_manager.hash_password(raw_key)

    user_manager.add_api_key(
        username="john",
        key_id=key_id,
        key_hash=key_hash,
        key_prefix=raw_key[:12],
        name="test-key",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        # Validate API key and check email is loaded
        user = user_manager.validate_user_api_key("john", raw_key)

        assert user is not None
        assert user.email == "john@example.com"
    finally:
        os.unlink(temp_file.name)
