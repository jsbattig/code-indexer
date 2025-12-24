"""
Test datetime parsing robustness in user_manager.py.

These tests verify that datetime parsing handles various ISO format variations
correctly and robustly without hardcoded string replacements.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.code_indexer.server.auth.user_manager import UserManager, UserRole
from src.code_indexer.server.utils.datetime_parser import DateTimeParseError


class TestDatetimeParsingFix:
    """Test robust datetime parsing in UserManager."""

    def test_datetime_parsing_with_z_suffix(self):
        """Test datetime parsing with Z suffix (Zulu time)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"

            # Create users data with Z suffix timestamp
            users_data = {
                "testuser": {
                    "role": "normal_user",
                    "password_hash": "hashed_password",
                    "created_at": "2024-01-01T12:30:45.123456Z",
                }
            }

            # Save to file
            with open(users_file, "w") as f:
                json.dump(users_data, f)

            # Create user manager and load user
            user_manager = UserManager(str(users_file))
            user = user_manager.get_user("testuser")

            assert user is not None
            assert user.username == "testuser"
            assert user.role == UserRole.NORMAL_USER
            assert user.created_at.tzinfo is not None  # Should have timezone info

    def test_datetime_parsing_with_offset_format(self):
        """Test datetime parsing with timezone offset format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"

            # Create users data with +00:00 timezone offset
            users_data = {
                "testuser": {
                    "role": "normal_user",
                    "password_hash": "hashed_password",
                    "created_at": "2024-01-01T12:30:45.123456+00:00",
                }
            }

            # Save to file
            with open(users_file, "w") as f:
                json.dump(users_data, f)

            # Create user manager and load user
            user_manager = UserManager(str(users_file))
            user = user_manager.get_user("testuser")

            assert user is not None
            assert user.created_at.tzinfo is not None  # Should have timezone info

    def test_datetime_parsing_with_different_timezone_offset(self):
        """Test datetime parsing with non-UTC timezone offset."""
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"

            # Create users data with non-UTC timezone offset
            users_data = {
                "testuser": {
                    "role": "normal_user",
                    "password_hash": "hashed_password",
                    "created_at": "2024-01-01T12:30:45+05:30",  # India Standard Time
                }
            }

            # Save to file
            with open(users_file, "w") as f:
                json.dump(users_data, f)

            # Create user manager and load user
            user_manager = UserManager(str(users_file))
            user = user_manager.get_user("testuser")

            assert user is not None
            assert user.created_at.tzinfo is not None  # Should have timezone info

    def test_datetime_parsing_without_microseconds(self):
        """Test datetime parsing without microseconds."""
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"

            # Create users data without microseconds
            users_data = {
                "testuser": {
                    "role": "normal_user",
                    "password_hash": "hashed_password",
                    "created_at": "2024-01-01T12:30:45Z",
                }
            }

            # Save to file
            with open(users_file, "w") as f:
                json.dump(users_data, f)

            # Create user manager and load user
            user_manager = UserManager(str(users_file))
            user = user_manager.get_user("testuser")

            assert user is not None
            assert user.created_at.tzinfo is not None

    def test_datetime_parsing_consistency_across_methods(self):
        """Test that all UserManager methods parse datetime consistently."""
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"

            # Create user manager first to get proper password hashes
            temp_user_manager = UserManager(str(users_file))
            hash1 = temp_user_manager.password_manager.hash_password("password1")
            hash2 = temp_user_manager.password_manager.hash_password("password2")
            hash3 = temp_user_manager.password_manager.hash_password("password3")

            # Create multiple users with different datetime formats
            users_data = {
                "user1": {
                    "role": "normal_user",
                    "password_hash": hash1,
                    "created_at": "2024-01-01T12:30:45.123456Z",
                },
                "user2": {
                    "role": "admin",
                    "password_hash": hash2,
                    "created_at": "2024-01-02T10:15:30+00:00",
                },
                "user3": {
                    "role": "power_user",
                    "password_hash": hash3,
                    "created_at": "2024-01-03T08:45:15-05:00",
                },
            }

            # Save to file
            with open(users_file, "w") as f:
                json.dump(users_data, f)

            user_manager = UserManager(str(users_file))

            # Test get_user method
            user1 = user_manager.get_user("user1")
            assert user1 is not None
            assert user1.created_at.tzinfo is not None

            # Test authenticate_user method (returns same user object)
            user_manager.authenticate_user(
                "user1", "password"
            )  # Will fail auth but test datetime parsing
            # Since auth will fail, test get_all_users instead

            # Test get_all_users method
            all_users = user_manager.get_all_users()
            assert len(all_users) == 3

            for user in all_users:
                assert user.created_at.tzinfo is not None
                assert isinstance(user.created_at, datetime)

    def test_datetime_parsing_preserves_timezone_info(self):
        """Test that datetime parsing preserves correct timezone information."""
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"

            # Use current UTC time for testing
            now_utc = datetime.now(timezone.utc)
            iso_string = now_utc.isoformat()

            users_data = {
                "testuser": {
                    "role": "normal_user",
                    "password_hash": "hashed_password",
                    "created_at": iso_string,
                }
            }

            # Save to file
            with open(users_file, "w") as f:
                json.dump(users_data, f)

            user_manager = UserManager(str(users_file))
            user = user_manager.get_user("testuser")

            assert user is not None

            # The parsed datetime should be equivalent to original
            # Allow small difference due to microsecond precision
            time_diff = abs((user.created_at - now_utc).total_seconds())
            assert time_diff < 1.0  # Less than 1 second difference

            # Should maintain timezone info
            assert user.created_at.tzinfo is not None

    def test_datetime_parsing_error_handling(self):
        """Test that malformed datetime strings are handled gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"

            # Create users data with malformed datetime
            users_data = {
                "testuser": {
                    "role": "normal_user",
                    "password_hash": "hashed_password",
                    "created_at": "invalid-datetime-string",
                }
            }

            # Save to file
            with open(users_file, "w") as f:
                json.dump(users_data, f)

            user_manager = UserManager(str(users_file))

            # Should handle malformed datetime gracefully
            with pytest.raises(DateTimeParseError):
                user_manager.get_user("testuser")
