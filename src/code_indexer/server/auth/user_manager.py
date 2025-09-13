"""
User management and role-based access control for CIDX Server.

Handles user storage, authentication, and permission checking.
Users stored in ~/.cidx-server/users.json with hashed passwords.
"""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

from .password_manager import PasswordManager
from .password_strength_validator import PasswordStrengthValidator
from ..utils.datetime_parser import DateTimeParser


class UserRole(str, Enum):
    """User roles with different permission levels."""

    ADMIN = "admin"  # Full access: manage users + golden repos + activate repos + query
    POWER_USER = "power_user"  # Activate repos + query + list repos
    NORMAL_USER = "normal_user"  # Query + list repos only


class User(BaseModel):
    """User data model."""

    username: str
    password_hash: str
    role: UserRole
    created_at: datetime

    def to_dict(self) -> Dict[str, str]:
        """Convert user to dictionary (excludes password_hash)."""
        return {
            "username": self.username,
            "role": self.role.value,
            "created_at": self.created_at.isoformat(),
        }

    def has_permission(self, permission: str) -> bool:
        """
        Check if user has specific permission.

        Args:
            permission: Permission to check

        Returns:
            True if user has permission, False otherwise
        """
        # Define permission mapping
        role_permissions = {
            UserRole.ADMIN: {
                "manage_users",
                "manage_golden_repos",
                "activate_repos",
                "query_repos",
            },
            UserRole.POWER_USER: {"activate_repos", "query_repos"},
            UserRole.NORMAL_USER: {"query_repos"},
        }

        user_permissions = role_permissions.get(self.role, set())
        return permission in user_permissions


class UserManager:
    """
    Manages user storage, authentication, and CRUD operations.

    Users are stored in ~/.cidx-server/users.json with hashed passwords.
    """

    def __init__(self, users_file_path: Optional[str] = None):
        """
        Initialize user manager.

        Args:
            users_file_path: Path to users.json file (defaults to ~/.cidx-server/users.json)
        """
        if users_file_path:
            self.users_file_path = users_file_path
        else:
            home_dir = Path.home()
            server_dir = home_dir / ".cidx-server"
            server_dir.mkdir(exist_ok=True)
            self.users_file_path = str(server_dir / "users.json")

        self.password_manager = PasswordManager()
        self.password_strength_validator = PasswordStrengthValidator()
        self._ensure_users_file_exists()

    def _ensure_users_file_exists(self):
        """Ensure users.json file exists, create empty dict if not."""
        if not os.path.exists(self.users_file_path):
            with open(self.users_file_path, "w") as f:
                json.dump({}, f)

    def _load_users(self) -> Dict[str, Dict[str, Any]]:
        """Load users from JSON file."""
        with open(self.users_file_path, "r") as f:
            return dict(json.load(f))

    def _save_users(self, users_data: Dict[str, Dict[str, Any]]):
        """Save users to JSON file."""
        with open(self.users_file_path, "w") as f:
            json.dump(users_data, f, indent=2)

    def seed_initial_admin(self):
        """Create initial admin user (admin/admin) if no users exist."""
        users_data = self._load_users()

        if "admin" not in users_data:
            # Create initial admin user
            admin_password_hash = self.password_manager.hash_password("admin")

            users_data["admin"] = {
                "role": "admin",
                "password_hash": admin_password_hash,
                "created_at": DateTimeParser.format_for_storage(
                    datetime.now(timezone.utc)
                ),
            }

            self._save_users(users_data)

    def create_user(self, username: str, password: str, role: UserRole) -> User:
        """
        Create new user.

        Args:
            username: Username
            password: Plain text password (will be hashed)
            role: User role

        Returns:
            Created User object

        Raises:
            ValueError: If user already exists or password is too weak
        """
        users_data = self._load_users()

        if username in users_data:
            raise ValueError(f"User already exists: {username}")

        # Validate password strength
        is_valid, validation_result = self.password_strength_validator.validate(
            password, username
        )
        if not is_valid:
            error_msg = "Password does not meet security requirements:\n"
            for issue in validation_result.issues:
                error_msg += f"- {issue}\n"
            if validation_result.suggestions:
                error_msg += "Suggestions:\n"
                for suggestion in validation_result.suggestions:
                    error_msg += f"- {suggestion}\n"
            raise ValueError(error_msg.strip())

        # Hash password and create user
        password_hash = self.password_manager.hash_password(password)
        created_at = datetime.now(timezone.utc)

        users_data[username] = {
            "role": role.value,
            "password_hash": password_hash,
            "created_at": DateTimeParser.format_for_storage(created_at),
        }

        self._save_users(users_data)

        return User(
            username=username,
            password_hash=password_hash,
            role=role,
            created_at=created_at,
        )

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user with username and password.

        Args:
            username: Username
            password: Plain text password

        Returns:
            User object if authentication successful, None otherwise
        """
        users_data = self._load_users()

        if username not in users_data:
            return None

        user_data = users_data[username]

        # Verify password
        if not self.password_manager.verify_password(
            password, user_data["password_hash"]
        ):
            return None

        # Create and return User object
        return User(
            username=username,
            password_hash=user_data["password_hash"],
            role=UserRole(user_data["role"]),
            created_at=DateTimeParser.parse_user_datetime(user_data["created_at"]),
        )

    def get_user(self, username: str) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Username to find

        Returns:
            User object if found, None otherwise
        """
        users_data = self._load_users()

        if username not in users_data:
            return None

        user_data = users_data[username]

        return User(
            username=username,
            password_hash=user_data["password_hash"],
            role=UserRole(user_data["role"]),
            created_at=DateTimeParser.parse_user_datetime(user_data["created_at"]),
        )

    def get_all_users(self) -> List[User]:
        """
        Get all users.

        Returns:
            List of User objects
        """
        users_data = self._load_users()

        users = []
        for username, user_data in users_data.items():
            user = User(
                username=username,
                password_hash=user_data["password_hash"],
                role=UserRole(user_data["role"]),
                created_at=DateTimeParser.parse_user_datetime(user_data["created_at"]),
            )
            users.append(user)

        return users

    def delete_user(self, username: str) -> bool:
        """
        Delete user.

        Args:
            username: Username to delete

        Returns:
            True if user deleted, False if user not found
        """
        users_data = self._load_users()

        if username not in users_data:
            return False

        del users_data[username]
        self._save_users(users_data)
        return True

    def update_user_role(self, username: str, new_role: UserRole) -> bool:
        """
        Update user role.

        Args:
            username: Username to update
            new_role: New role for user

        Returns:
            True if updated, False if user not found
        """
        users_data = self._load_users()

        if username not in users_data:
            return False

        users_data[username]["role"] = new_role.value
        self._save_users(users_data)
        return True

    def change_password(self, username: str, new_password: str) -> bool:
        """
        Change user password.

        Args:
            username: Username
            new_password: New plain text password

        Returns:
            True if changed, False if user not found

        Raises:
            ValueError: If password does not meet security requirements
        """
        users_data = self._load_users()

        if username not in users_data:
            return False

        # Validate password strength
        is_valid, validation_result = self.password_strength_validator.validate(
            new_password, username
        )
        if not is_valid:
            error_msg = "Password does not meet security requirements:\n"
            for issue in validation_result.issues:
                error_msg += f"- {issue}\n"
            if validation_result.suggestions:
                error_msg += "Suggestions:\n"
                for suggestion in validation_result.suggestions:
                    error_msg += f"- {suggestion}\n"
            raise ValueError(error_msg.strip())

        new_password_hash = self.password_manager.hash_password(new_password)
        users_data[username]["password_hash"] = new_password_hash

        self._save_users(users_data)
        return True

    def validate_password_strength(
        self, password: str, username: Optional[str] = None, email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate password strength without changing anything.

        Args:
            password: Password to validate
            username: Optional username for personal info check
            email: Optional email for personal info check

        Returns:
            Dictionary with validation results
        """
        is_valid, result = self.password_strength_validator.validate(
            password, username, email
        )

        return {
            "valid": is_valid,
            "score": result.score,
            "strength": result.strength,
            "issues": result.issues,
            "suggestions": result.suggestions,
            "entropy": result.entropy,
            "requirements": self.password_strength_validator.get_requirements(),
        }
