"""Unit tests for UserManager email update functionality with **kwargs."""

import tempfile
import json
import os
from datetime import datetime, timezone
from src.code_indexer.server.auth.user_manager import UserManager
from src.code_indexer.server.utils.datetime_parser import DateTimeParser


def test_update_user_with_new_email():
    """Test updating user email using **kwargs."""
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

        # Update email
        result = user_manager.update_user("john", new_email="john@example.com")
        assert result is True

        # Verify email was saved
        user = user_manager.get_user("john")
        assert user.email == "john@example.com"
    finally:
        os.unlink(temp_file.name)


def test_update_user_clear_email_with_none():
    """Test clearing user email by passing None."""
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

        # Clear email by passing None
        result = user_manager.update_user("john", new_email=None)
        assert result is True

        # Verify email was cleared
        user = user_manager.get_user("john")
        assert user.email is None
    finally:
        os.unlink(temp_file.name)


def test_update_user_no_email_parameter_does_not_change():
    """Test that not passing new_email doesn't change existing email."""
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

        # Update without email parameter
        result = user_manager.update_user("john")
        assert result is True

        # Verify email unchanged
        user = user_manager.get_user("john")
        assert user.email == "john@example.com"
    finally:
        os.unlink(temp_file.name)


def test_update_user_duplicate_email_raises_error():
    """Test that duplicate email raises ValueError."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    test_users = {
        "john": {
            "role": "normal_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
            "email": "john@example.com",
        },
        "jane": {
            "role": "normal_user",
            "password_hash": "hashed_password",
            "created_at": DateTimeParser.format_for_storage(datetime.now(timezone.utc)),
        },
    }
    json.dump(test_users, temp_file)
    temp_file.close()

    try:
        user_manager = UserManager(users_file_path=temp_file.name)

        # Try to set Jane's email to John's email
        try:
            user_manager.update_user("jane", new_email="john@example.com")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Email already exists" in str(e)
    finally:
        os.unlink(temp_file.name)


def test_update_user_same_email_on_same_user_succeeds():
    """Test that setting same email on same user succeeds (idempotent)."""
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

        # Set same email again
        result = user_manager.update_user("john", new_email="john@example.com")
        assert result is True

        # Verify email unchanged
        user = user_manager.get_user("john")
        assert user.email == "john@example.com"
    finally:
        os.unlink(temp_file.name)
