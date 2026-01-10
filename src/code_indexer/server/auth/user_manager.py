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
    email: Optional[str] = None

    def to_dict(self) -> Dict[str, str]:
        """Convert user to dictionary (excludes password_hash)."""
        result = {
            "username": self.username,
            "role": self.role.value,
            "created_at": self.created_at.isoformat(),
        }
        if self.email:
            result["email"] = self.email
        return result

    def has_permission(self, permission: Optional[str]) -> bool:
        """
        Check if user has specific permission.

        Permission model uses inheritance:
        - ADMIN inherits all POWER_USER + NORMAL_USER permissions + admin-specific
        - POWER_USER inherits all NORMAL_USER permissions + power-user-specific
        - NORMAL_USER has base permissions

        Args:
            permission: Permission to check (can be None for public tools)

        Returns:
            True if user has permission, False otherwise
        """
        # Handle None permission (public tools) and "public" permission
        if permission is None or permission == "public":
            return True

        # Define base permissions for each role (without inheritance)
        base_permissions = {
            UserRole.NORMAL_USER: {
                "query_repos",
                "repository:read",  # Can read repo status, list branches, etc.
            },
            UserRole.POWER_USER: {
                "activate_repos",
                "repository:write",  # Can modify files, commit, push, etc.
            },
            UserRole.ADMIN: {
                "manage_users",
                "manage_golden_repos",
                "repository:admin",  # Can perform destructive operations
            },
        }

        # Build inherited permissions based on role hierarchy
        if self.role == UserRole.ADMIN:
            # ADMIN inherits from POWER_USER and NORMAL_USER
            user_permissions = (
                base_permissions[UserRole.NORMAL_USER]
                | base_permissions[UserRole.POWER_USER]
                | base_permissions[UserRole.ADMIN]
            )
        elif self.role == UserRole.POWER_USER:
            # POWER_USER inherits from NORMAL_USER
            user_permissions = (
                base_permissions[UserRole.NORMAL_USER]
                | base_permissions[UserRole.POWER_USER]
            )
        else:  # NORMAL_USER
            user_permissions = base_permissions[UserRole.NORMAL_USER]

        return permission in user_permissions


class UserManager:
    """
    Manages user storage, authentication, and CRUD operations.

    Users are stored in ~/.cidx-server/users.json with hashed passwords.
    Supports both SQLite backend (Story #702) and JSON file storage (backward compatible).
    """

    def __init__(
        self,
        users_file_path: Optional[str] = None,
        password_security_config=None,
        use_sqlite: bool = False,
        db_path: Optional[str] = None,
    ):
        """
        Initialize user manager.

        Args:
            users_file_path: Path to users.json file (defaults to ~/.cidx-server/users.json)
            password_security_config: PasswordSecurityConfig for password validation settings
            use_sqlite: If True, use SQLite backend instead of JSON file (Story #702)
            db_path: Path to SQLite database file (required when use_sqlite=True)
        """
        self._use_sqlite = use_sqlite
        self._sqlite_backend: Optional[Any] = None

        self.password_manager = PasswordManager()
        self.password_strength_validator = PasswordStrengthValidator(
            password_security_config
        )

        if use_sqlite:
            if db_path is None:
                raise ValueError("db_path is required when use_sqlite=True")
            from code_indexer.server.storage.sqlite_backends import (
                UsersSqliteBackend,
            )

            self._sqlite_backend = UsersSqliteBackend(db_path)
        else:
            # JSON file storage (backward compatible)
            if users_file_path:
                self.users_file_path = users_file_path
            else:
                home_dir = Path.home()
                server_dir = home_dir / ".cidx-server"
                server_dir.mkdir(exist_ok=True)
                self.users_file_path = str(server_dir / "users.json")

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
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            existing = self._sqlite_backend.get_user("admin")
            if existing is None:
                # Create initial admin user
                admin_password_hash = self.password_manager.hash_password("admin")
                self._sqlite_backend.create_user(
                    username="admin",
                    password_hash=admin_password_hash,
                    role="admin",
                )
        else:
            # JSON file storage (backward compatible)
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
        # Validate password strength (applies to both backends)
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

        # Hash password
        password_hash = self.password_manager.hash_password(password)
        created_at = datetime.now(timezone.utc)

        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            # Check if user exists
            existing = self._sqlite_backend.get_user(username)
            if existing is not None:
                raise ValueError(f"User already exists: {username}")

            self._sqlite_backend.create_user(
                username=username,
                password_hash=password_hash,
                role=role.value,
                email=None,
                created_at=DateTimeParser.format_for_storage(created_at),
            )
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()

            if username in users_data:
                raise ValueError(f"User already exists: {username}")

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
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            user_data = self._sqlite_backend.get_user(username)
            if user_data is None:
                return None

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
                email=user_data.get("email"),
            )
        else:
            # JSON file storage (backward compatible)
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
                email=user_data.get("email"),
            )

    def get_user(self, username: str) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Username to find

        Returns:
            User object if found, None otherwise
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            user_data = self._sqlite_backend.get_user(username)
            if user_data is None:
                return None

            return User(
                username=username,
                password_hash=user_data["password_hash"],
                role=UserRole(user_data["role"]),
                created_at=DateTimeParser.parse_user_datetime(user_data["created_at"]),
                email=user_data.get("email"),
            )
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()

            if username not in users_data:
                return None

            user_data = users_data[username]

            return User(
                username=username,
                password_hash=user_data["password_hash"],
                role=UserRole(user_data["role"]),
                created_at=DateTimeParser.parse_user_datetime(user_data["created_at"]),
                email=user_data.get("email"),
            )

    def get_all_users(self) -> List[User]:
        """
        Get all users.

        Returns:
            List of User objects (skips malformed entries)
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            users_data_list = self._sqlite_backend.list_users()
            users = []
            for user_data in users_data_list:
                try:
                    user = User(
                        username=user_data["username"],
                        password_hash=user_data["password_hash"],
                        role=UserRole(user_data["role"]),
                        created_at=DateTimeParser.parse_user_datetime(
                            user_data["created_at"]
                        ),
                        email=user_data.get("email"),
                    )
                    users.append(user)
                except (KeyError, ValueError) as e:
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Skipping invalid user entry '{user_data.get('username', 'unknown')}': {e}"
                    )
                    continue
            return users
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()

            users = []
            required_fields = {"password_hash", "role", "created_at"}
            for username, user_data in users_data.items():
                # Skip malformed entries that are missing required fields
                if not isinstance(user_data, dict):
                    continue
                missing_fields = required_fields - set(user_data.keys())
                if missing_fields:
                    # Log warning but don't crash - data corruption shouldn't break the UI
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Skipping malformed user entry '{username}': missing {missing_fields}"
                    )
                    continue

                try:
                    user = User(
                        username=username,
                        password_hash=user_data["password_hash"],
                        role=UserRole(user_data["role"]),
                        created_at=DateTimeParser.parse_user_datetime(
                            user_data["created_at"]
                        ),
                        email=user_data.get("email"),
                    )
                    users.append(user)
                except (KeyError, ValueError) as e:
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Skipping invalid user entry '{username}': {e}"
                    )
                    continue

            return users

    def delete_user(self, username: str) -> bool:
        """
        Delete user.

        Args:
            username: Username to delete

        Returns:
            True if user deleted, False if user not found
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            return self._sqlite_backend.delete_user(username)
        else:
            # JSON file storage (backward compatible)
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
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            existing = self._sqlite_backend.get_user(username)
            if existing is None:
                return False
            self._sqlite_backend.update_user_role(username, new_role.value)
            return True
        else:
            # JSON file storage (backward compatible)
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
        # Validate password strength (applies to both backends)
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

        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            existing = self._sqlite_backend.get_user(username)
            if existing is None:
                return False
            return self._sqlite_backend.update_password_hash(username, new_password_hash)
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return False
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

    def update_user(
        self, username: str, new_username: Optional[str] = None, **kwargs
    ) -> bool:
        """
        Update user's username or email.

        Args:
            username: Current username
            new_username: New username (if changing)
            **kwargs: Optional new_email to update or clear (None clears it)

        Returns:
            True if successful, False if user not found

        Raises:
            ValueError: If username/email already exists
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            existing = self._sqlite_backend.get_user(username)
            if existing is None:
                return False
            new_email = kwargs.get("new_email")
            return self._sqlite_backend.update_user(
                username=username, new_username=new_username, email=new_email
            )
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return False
            current_username = username
            if new_username and new_username != username:
                if new_username in users_data:
                    raise ValueError(f"Username already exists: {new_username}")
                users_data[new_username] = users_data[username]
                del users_data[username]
                current_username = new_username
            if "new_email" in kwargs:
                new_email = kwargs["new_email"]
                if new_email:
                    for user, data in users_data.items():
                        if user != current_username and data.get("email") == new_email:
                            raise ValueError(f"Email already exists: {new_email}")
                    users_data[current_username]["email"] = new_email
                else:
                    users_data[current_username].pop("email", None)
            self._save_users(users_data)
            return True

    def add_api_key(
        self,
        username: str,
        key_id: str,
        key_hash: str,
        key_prefix: str,
        name: Optional[str],
        created_at: str,
    ) -> bool:
        """
        Add an API key to user's api_keys array.

        Args:
            username: Username
            key_id: Unique key ID
            key_hash: Hashed API key
            key_prefix: Key prefix for display (e.g., "cidx_sk_a1b2")
            name: Optional name for the key
            created_at: ISO format timestamp

        Returns:
            True if added, False if user not found
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            # Note: SQLite backend generates created_at internally for consistency
            existing = self._sqlite_backend.get_user(username)
            if existing is None:
                return False
            self._sqlite_backend.add_api_key(
                username=username, key_id=key_id, key_hash=key_hash,
                key_prefix=key_prefix, name=name,
            )
            return True
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return False
            if "api_keys" not in users_data[username]:
                users_data[username]["api_keys"] = []
            users_data[username]["api_keys"].append({
                "key_id": key_id, "name": name, "hash": key_hash,
                "key_prefix": key_prefix, "created_at": created_at,
            })
            self._save_users(users_data)
            return True

    def get_api_keys(self, username: str) -> List[Dict[str, Any]]:
        """
        Get list of API keys for user (without hashes).

        Args:
            username: Username

        Returns:
            List of API key metadata (without hashes)
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            user_data = self._sqlite_backend.get_user(username)
            if user_data is None:
                return []
            api_keys = user_data.get("api_keys", [])
            return [
                {"key_id": key["key_id"], "name": key.get("name"),
                 "created_at": key["created_at"],
                 "key_prefix": key.get("key_prefix", "cidx_sk_****...")}
                for key in api_keys
            ]
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return []
            api_keys = users_data[username].get("api_keys", [])
            return [
                {"key_id": key["key_id"], "name": key.get("name"),
                 "created_at": key["created_at"],
                 "key_prefix": key.get("key_prefix", "cidx_sk_****...")}
                for key in api_keys
            ]

    def delete_api_key(self, username: str, key_id: str) -> bool:
        """
        Delete an API key from user's api_keys array.

        Args:
            username: Username
            key_id: Key ID to delete

        Returns:
            True if deleted, False if not found
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            return self._sqlite_backend.delete_api_key(username, key_id)
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return False
            api_keys = users_data[username].get("api_keys", [])
            original_count = len(api_keys)
            users_data[username]["api_keys"] = [
                k for k in api_keys if k["key_id"] != key_id
            ]
            if len(users_data[username]["api_keys"]) == original_count:
                return False  # Key not found
            self._save_users(users_data)
            return True

    def validate_user_api_key(self, username: str, raw_key: str) -> Optional[User]:
        """
        Validate API key for a user.

        Args:
            username: Username
            raw_key: Raw API key (cidx_sk_...)

        Returns:
            User object if valid, None otherwise
        """
        from .api_key_manager import ApiKeyManager

        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            user_data = self._sqlite_backend.get_user(username)
            if user_data is None:
                return None
            api_keys = user_data.get("api_keys", [])
            api_key_manager = ApiKeyManager()
            for key_entry in api_keys:
                stored_hash = key_entry.get("key_hash")
                if stored_hash and api_key_manager.validate_key(raw_key, stored_hash):
                    return User(
                        username=username, password_hash=user_data["password_hash"],
                        role=UserRole(user_data["role"]),
                        created_at=DateTimeParser.parse_user_datetime(user_data["created_at"]),
                        email=user_data.get("email"),
                    )
            return None
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return None
            user_data = users_data[username]
            api_keys = user_data.get("api_keys", [])
            api_key_manager = ApiKeyManager()
            for key_entry in api_keys:
                stored_hash = key_entry.get("hash")
                if stored_hash and api_key_manager.validate_key(raw_key, stored_hash):
                    return User(
                        username=username, password_hash=user_data["password_hash"],
                        role=UserRole(user_data["role"]),
                        created_at=DateTimeParser.parse_user_datetime(user_data["created_at"]),
                        email=user_data.get("email"),
                    )
            return None

    def add_mcp_credential(
        self,
        username: str,
        credential_id: str,
        client_id: str,
        client_secret_hash: str,
        client_id_prefix: str,
        name: Optional[str],
        created_at: str,
    ) -> bool:
        """
        Add an MCP credential to user's mcp_credentials array.

        Args:
            username: Username
            credential_id: Unique credential ID (UUID)
            client_id: Full client_id
            client_secret_hash: Hashed client_secret
            client_id_prefix: First 8 characters of client_id for display
            name: Optional name for the credential
            created_at: ISO format timestamp

        Returns:
            True if added, False if user not found
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            # Note: SQLite backend generates created_at internally for consistency
            existing = self._sqlite_backend.get_user(username)
            if existing is None:
                return False
            self._sqlite_backend.add_mcp_credential(
                username=username, credential_id=credential_id, client_id=client_id,
                client_secret_hash=client_secret_hash, client_id_prefix=client_id_prefix,
                name=name,
            )
            return True
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return False
            if "mcp_credentials" not in users_data[username]:
                users_data[username]["mcp_credentials"] = []
            users_data[username]["mcp_credentials"].append({
                "credential_id": credential_id, "client_id": client_id,
                "client_secret_hash": client_secret_hash, "client_id_prefix": client_id_prefix,
                "name": name, "created_at": created_at, "last_used_at": None,
            })
            self._save_users(users_data)
            return True

    def get_mcp_credentials_with_secrets(self, username: str) -> List[Dict[str, Any]]:
        """
        Get list of MCP credentials for user INCLUDING hashes.

        WARNING: This method returns sensitive data (client_secret_hash).
        Only use for internal credential verification, never expose to API.

        Story #702 SQLite migration: Added to allow MCPCredentialManager
        to verify credentials without calling internal _load_users().

        Args:
            username: Username

        Returns:
            List of full MCP credentials including client_secret_hash
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            user_data = self._sqlite_backend.get_user(username)
            if user_data is None:
                return []
            return user_data.get("mcp_credentials", [])
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return []
            return users_data[username].get("mcp_credentials", [])

    def get_mcp_credentials(self, username: str) -> List[Dict[str, Any]]:
        """
        Get list of MCP credentials for user (without hashes).

        Args:
            username: Username

        Returns:
            List of MCP credential metadata (without hashes or secrets), sorted by created_at descending (newest first)
        """
        if self._use_sqlite and self._sqlite_backend is not None:
            # SQLite backend (Story #702)
            user_data = self._sqlite_backend.get_user(username)
            if user_data is None:
                return []
            mcp_credentials = user_data.get("mcp_credentials", [])
        else:
            # JSON file storage (backward compatible)
            users_data = self._load_users()
            if username not in users_data:
                return []
            mcp_credentials = users_data[username].get("mcp_credentials", [])

        # Build metadata list without hashes or secrets
        credentials_metadata = [
            {
                "credential_id": cred["credential_id"],
                "client_id": cred["client_id"],
                "client_id_prefix": cred.get("client_id_prefix", cred["client_id"][:8]),
                "name": cred.get("name"),
                "created_at": cred["created_at"],
                "last_used_at": cred.get("last_used_at"),
            }
            for cred in mcp_credentials
        ]

        # Sort by created_at descending (newest first)
        credentials_metadata.sort(key=lambda x: x["created_at"], reverse=True)

        return credentials_metadata

    def delete_mcp_credential(self, username: str, credential_id: str) -> bool:
        """
        Delete an MCP credential from user's mcp_credentials array.

        Args:
            username: Username
            credential_id: Credential ID to delete

        Returns:
            True if deleted, False if not found
        """
        # Story #702 SQLite migration: Add SQLite backend support
        if self._use_sqlite and self._sqlite_backend is not None:
            return self._sqlite_backend.delete_mcp_credential(username, credential_id)

        # JSON file storage (backward compatible)
        users_data = self._load_users()
        if username not in users_data:
            return False

        mcp_credentials = users_data[username].get("mcp_credentials", [])
        original_count = len(mcp_credentials)
        users_data[username]["mcp_credentials"] = [
            c for c in mcp_credentials if c["credential_id"] != credential_id
        ]

        if len(users_data[username]["mcp_credentials"]) == original_count:
            return False  # Credential not found

        self._save_users(users_data)
        return True

    def update_mcp_credential_last_used(
        self, username: str, credential_id: str
    ) -> bool:
        """
        Update last_used_at timestamp for an MCP credential.

        Args:
            username: Username
            credential_id: Credential ID to update

        Returns:
            True if updated, False if not found
        """
        # Story #702 SQLite migration: Add SQLite backend support
        if self._use_sqlite and self._sqlite_backend is not None:
            return self._sqlite_backend.update_mcp_credential_last_used(
                username, credential_id
            )

        # JSON file storage (backward compatible)
        users_data = self._load_users()
        if username not in users_data:
            return False

        mcp_credentials = users_data[username].get("mcp_credentials", [])
        for cred in mcp_credentials:
            if cred["credential_id"] == credential_id:
                cred["last_used_at"] = datetime.now(timezone.utc).isoformat()
                self._save_users(users_data)
                return True

        return False

    def list_all_mcp_credentials(
        self, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List MCP credentials across all users with pagination.

        Args:
            limit: Maximum number of credentials to return
            offset: Number of credentials to skip

        Returns:
            List of credential metadata with username information
        """
        # Story #702 SQLite migration: Add SQLite backend support
        if self._use_sqlite and self._sqlite_backend is not None:
            return self._sqlite_backend.list_all_mcp_credentials(limit, offset)

        # JSON file storage (backward compatible)
        all_credentials = []
        users_data = self._load_users()

        # Sort users by username for consistent pagination
        sorted_usernames = sorted(users_data.keys())

        count = 0
        for username in sorted_usernames:
            if count >= limit + offset:
                break

            user_data = users_data[username]
            credentials = user_data.get("mcp_credentials", [])

            for cred in credentials:
                if count < offset:
                    count += 1
                    continue

                if count >= limit + offset:
                    break

                all_credentials.append(
                    {
                        "username": username,
                        "credential_id": cred["credential_id"],
                        "name": cred.get("name"),
                        "client_id_prefix": cred.get(
                            "client_id_prefix", cred.get("client_id", "")[:8]
                        ),
                        "created_at": cred["created_at"],
                        "last_used_at": cred.get("last_used_at"),
                    }
                )
                count += 1

        return all_credentials

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address (case-insensitive).

        Args:
            email: Email address to search for

        Returns:
            User object if found, None otherwise
        """
        # Story #702 SSO fix: Add SQLite backend support
        if self._use_sqlite and self._sqlite_backend is not None:
            user_data = self._sqlite_backend.get_user_by_email(email)
            if user_data is None:
                return None
            return User(
                username=user_data["username"],
                password_hash=user_data["password_hash"],
                role=UserRole(user_data["role"]),
                created_at=DateTimeParser.parse_user_datetime(user_data["created_at"]),
                email=user_data.get("email"),
            )

        # JSON file storage (backward compatible)
        users_data = self._load_users()
        email_lower = email.lower().strip()

        for username, user_data in users_data.items():
            user_email = user_data.get("email")
            if user_email and user_email.lower().strip() == email_lower:
                return User(
                    username=username,
                    password_hash=user_data["password_hash"],
                    role=UserRole(user_data["role"]),
                    created_at=DateTimeParser.parse_user_datetime(
                        user_data["created_at"]
                    ),
                    email=user_email,
                )

        return None

    def set_oidc_identity(self, username: str, identity: Dict[str, Any]) -> bool:
        """Set OIDC identity for user.

        Args:
            username: Username
            identity: OIDC identity data (subject, email, linked_at, last_login)

        Returns:
            True if successful, False if user not found
        """
        # Story #702 SSO fix: Add SQLite backend support
        if self._use_sqlite and self._sqlite_backend is not None:
            return self._sqlite_backend.set_oidc_identity(username, identity)

        # JSON file storage (backward compatible)
        users_data = self._load_users()

        if username not in users_data:
            return False

        users_data[username]["oidc_identity"] = identity
        self._save_users(users_data)
        return True

    def remove_oidc_identity(self, username: str) -> bool:
        """Remove OIDC identity from user.

        Args:
            username: Username

        Returns:
            True if removed, False if user not found
        """
        # Story #702 SQLite migration: Add SQLite backend support
        if self._use_sqlite and self._sqlite_backend is not None:
            return self._sqlite_backend.remove_oidc_identity(username)

        # JSON file storage (backward compatible)
        users_data = self._load_users()

        if username not in users_data:
            return False

        # Remove oidc_identity if it exists
        if "oidc_identity" in users_data[username]:
            del users_data[username]["oidc_identity"]

        self._save_users(users_data)
        return True

    def create_oidc_user(self, username, role, email, oidc_identity):
        """Create user via JIT provisioning (without user-known password).

        Args:
            username: Username
            role: User role
            email: User email (optional)
            oidc_identity: OIDC identity data

        Returns:
            Created User object

        Raises:
            ValueError: If user already exists
        """
        import secrets

        # Story #702 SQLite migration: Add SQLite backend support
        if self._use_sqlite and self._sqlite_backend is not None:
            # Check if user already exists
            existing_user = self._sqlite_backend.get_user(username)
            if existing_user is not None:
                raise ValueError(f"User already exists: {username}")

            # Generate random password that user will never know (for password_hash field)
            random_password = secrets.token_urlsafe(32)
            password_hash = self.password_manager.hash_password(random_password)
            created_at = datetime.now(timezone.utc)

            # Create user via SQLite backend
            self._sqlite_backend.create_user(
                username=username,
                password_hash=password_hash,
                role=role.value if hasattr(role, "value") else role,
                email=email,
                created_at=DateTimeParser.format_for_storage(created_at),
            )

            # Set OIDC identity
            if oidc_identity:
                self._sqlite_backend.set_oidc_identity(username, oidc_identity)

            return User(
                username=username,
                password_hash=password_hash,
                role=role if isinstance(role, UserRole) else UserRole(role),
                created_at=created_at,
                email=email,
            )

        # JSON file storage (backward compatible)
        users_data = self._load_users()

        if username in users_data:
            raise ValueError(f"User already exists: {username}")

        # Generate random password that user will never know (for password_hash field)
        random_password = secrets.token_urlsafe(32)
        password_hash = self.password_manager.hash_password(random_password)
        created_at = datetime.now(timezone.utc)

        users_data[username] = {
            "role": role.value,
            "password_hash": password_hash,
            "created_at": DateTimeParser.format_for_storage(created_at),
            "oidc_identity": oidc_identity,
        }

        if email:
            users_data[username]["email"] = email

        self._save_users(users_data)

        return User(
            username=username,
            password_hash=password_hash,
            role=role,
            created_at=created_at,
            email=email,
        )
