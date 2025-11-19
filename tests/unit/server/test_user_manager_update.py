"""Unit tests for UserManager.update_user() method following strict TDD."""

import tempfile
import json
import os
from datetime import datetime, timezone
from src.code_indexer.server.auth.user_manager import UserManager
from src.code_indexer.server.utils.datetime_parser import DateTimeParser


def test_update_user_method_exists():
    """Test that update_user method exists on UserManager."""
    # Create temporary users file
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({}, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)

        # This will fail because update_user doesn't exist yet
        result = user_manager.update_user("test_user", new_username="new_name")
        assert result is not None
    finally:
        os.unlink(temp_file.name)


def test_update_username_changes_username():
    """Test that updating username actually changes it."""
    # Create temporary users file with test user
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    test_users = {
        "john": {
            "role": "normal_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
        }
    }
    json.dump(test_users, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)

        # Update username
        result = user_manager.update_user("john", new_username="john_doe")
        assert result is True

        # Check old username doesn't exist
        assert user_manager.get_user("john") is None

        # Check new username exists
        user = user_manager.get_user("john_doe")
        assert user is not None
        assert user.username == "john_doe"
    finally:
        os.unlink(temp_file.name)


def test_update_duplicate_username_raises_error():
    """Test that updating to an existing username raises ValueError."""
    import pytest

    # Create temporary users file with test users
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    test_users = {
        "john": {
            "role": "normal_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
        },
        "jane": {
            "role": "power_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
        },
    }
    json.dump(test_users, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)

        # Try to update john's username to jane (already exists)
        with pytest.raises(ValueError) as exc_info:
            user_manager.update_user("john", new_username="jane")

        assert "Username already exists" in str(exc_info.value)
    finally:
        os.unlink(temp_file.name)


def test_update_nonexistent_user_returns_false():
    """Test that updating non-existent user returns False."""
    # Create temporary users file
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({}, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)

        # Try to update non-existent user
        result = user_manager.update_user("nonexistent", new_username="new_name")
        assert result is False
    finally:
        os.unlink(temp_file.name)


def test_update_email_changes_email():
    """Test that updating email actually changes it."""
    # Create temporary users file with test user
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

        # Update email
        result = user_manager.update_user("john", new_email="john.doe@example.com")
        assert result is True

        # Check email updated
        users_data = user_manager._load_users()
        assert users_data["john"]["email"] == "john.doe@example.com"
    finally:
        os.unlink(temp_file.name)


def test_update_duplicate_email_raises_error():
    """Test that updating to an existing email raises ValueError."""
    import pytest

    # Create temporary users file with test users
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
    }
    json.dump(test_users, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)

        # Try to update john's email to jane's email
        with pytest.raises(ValueError) as exc_info:
            user_manager.update_user("john", new_email="jane@example.com")

        assert "Email already exists" in str(exc_info.value)
    finally:
        os.unlink(temp_file.name)
