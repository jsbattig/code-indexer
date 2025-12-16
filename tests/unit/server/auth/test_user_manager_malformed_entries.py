"""
TDD Test Suite for User Manager Malformed Entry Handling.

MESSI RULE #1 COMPLIANCE: ZERO MOCKS - REAL SYSTEMS ONLY

This test suite verifies that UserManager.get_all_users() gracefully handles
malformed user entries in users.json without crashing.

Bug reproduction: A user entry with only {"verified": null} (missing password_hash,
role, created_at) caused KeyError crash on /admin/users page.
"""

import json
import tempfile
import shutil
from pathlib import Path


from code_indexer.server.auth.user_manager import UserManager
from code_indexer.server.utils.config_manager import PasswordSecurityConfig


class TestUserManagerMalformedEntries:
    """
    TDD test suite for malformed user entry handling.

    Verifies get_all_users() doesn't crash on corrupted data.
    """

    def setup_method(self):
        """Set up real test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.users_file_path = self.temp_path / "users.json"

        # Weak password config for testing
        self.weak_password_config = PasswordSecurityConfig(
            min_length=1,
            max_length=128,
            required_char_classes=0,
            min_entropy_bits=0,
            check_common_passwords=False,
            check_personal_info=False,
            check_keyboard_patterns=False,
            check_sequential_chars=False,
        )

    def teardown_method(self):
        """Clean up temp directory."""
        if hasattr(self, "temp_dir"):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_user_manager(self) -> UserManager:
        """Create UserManager with test configuration."""
        return UserManager(
            users_file_path=str(self.users_file_path),
            password_security_config=self.weak_password_config,
        )

    def test_get_all_users_skips_entry_missing_password_hash(self):
        """
        Test that get_all_users skips entries missing password_hash.

        Bug reproduction: mcpb_mac entry had only {"verified": null}
        """
        # Arrange: Create users.json with one valid and one malformed entry
        users_data = {
            "valid_user": {
                "password_hash": "$2b$12$test_hash",
                "role": "admin",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            "malformed_user": {
                "verified": None,  # Missing password_hash, role, created_at
            },
        }
        with open(self.users_file_path, "w") as f:
            json.dump(users_data, f)

        user_manager = self._create_user_manager()

        # Act: Should not crash
        users = user_manager.get_all_users()

        # Assert: Only valid user returned
        assert len(users) == 1
        assert users[0].username == "valid_user"

    def test_get_all_users_skips_entry_missing_role(self):
        """Test that get_all_users skips entries missing role field."""
        users_data = {
            "valid_user": {
                "password_hash": "$2b$12$test_hash",
                "role": "admin",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            "no_role_user": {
                "password_hash": "$2b$12$another_hash",
                "created_at": "2025-01-01T00:00:00+00:00",
                # Missing role
            },
        }
        with open(self.users_file_path, "w") as f:
            json.dump(users_data, f)

        user_manager = self._create_user_manager()

        # Act
        users = user_manager.get_all_users()

        # Assert
        assert len(users) == 1
        assert users[0].username == "valid_user"

    def test_get_all_users_skips_entry_missing_created_at(self):
        """Test that get_all_users skips entries missing created_at field."""
        users_data = {
            "valid_user": {
                "password_hash": "$2b$12$test_hash",
                "role": "admin",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            "no_date_user": {
                "password_hash": "$2b$12$another_hash",
                "role": "normal_user",
                # Missing created_at
            },
        }
        with open(self.users_file_path, "w") as f:
            json.dump(users_data, f)

        user_manager = self._create_user_manager()

        # Act
        users = user_manager.get_all_users()

        # Assert
        assert len(users) == 1
        assert users[0].username == "valid_user"

    def test_get_all_users_skips_non_dict_entry(self):
        """Test that get_all_users skips entries that are not dictionaries."""
        users_data = {
            "valid_user": {
                "password_hash": "$2b$12$test_hash",
                "role": "admin",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            "string_entry": "not a dict",
            "list_entry": ["also", "not", "valid"],
            "null_entry": None,
        }
        with open(self.users_file_path, "w") as f:
            json.dump(users_data, f)

        user_manager = self._create_user_manager()

        # Act
        users = user_manager.get_all_users()

        # Assert
        assert len(users) == 1
        assert users[0].username == "valid_user"

    def test_get_all_users_skips_invalid_role(self):
        """Test that get_all_users skips entries with invalid role value."""
        users_data = {
            "valid_user": {
                "password_hash": "$2b$12$test_hash",
                "role": "admin",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            "bad_role_user": {
                "password_hash": "$2b$12$another_hash",
                "role": "superuser",  # Invalid role
                "created_at": "2025-01-01T00:00:00+00:00",
            },
        }
        with open(self.users_file_path, "w") as f:
            json.dump(users_data, f)

        user_manager = self._create_user_manager()

        # Act
        users = user_manager.get_all_users()

        # Assert
        assert len(users) == 1
        assert users[0].username == "valid_user"

    def test_get_all_users_returns_all_valid_users(self):
        """Test that get_all_users returns all valid users when no malformed entries."""
        users_data = {
            "admin_user": {
                "password_hash": "$2b$12$admin_hash",
                "role": "admin",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            "power_user": {
                "password_hash": "$2b$12$power_hash",
                "role": "power_user",
                "created_at": "2025-01-02T00:00:00+00:00",
            },
            "normal_user": {
                "password_hash": "$2b$12$normal_hash",
                "role": "normal_user",
                "created_at": "2025-01-03T00:00:00+00:00",
            },
        }
        with open(self.users_file_path, "w") as f:
            json.dump(users_data, f)

        user_manager = self._create_user_manager()

        # Act
        users = user_manager.get_all_users()

        # Assert
        assert len(users) == 3
        usernames = {u.username for u in users}
        assert usernames == {"admin_user", "power_user", "normal_user"}

    def test_get_all_users_empty_file(self):
        """Test that get_all_users handles empty users.json."""
        with open(self.users_file_path, "w") as f:
            json.dump({}, f)

        user_manager = self._create_user_manager()

        # Act
        users = user_manager.get_all_users()

        # Assert
        assert len(users) == 0

    def test_get_all_users_mixed_valid_and_invalid(self):
        """Test realistic scenario with mix of valid and various invalid entries."""
        users_data = {
            "admin": {
                "password_hash": "$2b$12$admin_hash",
                "role": "admin",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            "corrupted_1": {"verified": None},  # Original bug case
            "corrupted_2": "string_value",
            "corrupted_3": {"role": "admin"},  # Missing password_hash and created_at
            "normal": {
                "password_hash": "$2b$12$normal_hash",
                "role": "normal_user",
                "created_at": "2025-01-02T00:00:00+00:00",
            },
        }
        with open(self.users_file_path, "w") as f:
            json.dump(users_data, f)

        user_manager = self._create_user_manager()

        # Act
        users = user_manager.get_all_users()

        # Assert
        assert len(users) == 2
        usernames = {u.username for u in users}
        assert usernames == {"admin", "normal"}
