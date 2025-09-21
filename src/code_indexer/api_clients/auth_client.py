"""Authentication API Client for CIDX Remote Server.

Provides explicit authentication commands for login, register, and logout
operations with secure credential storage and comprehensive error handling.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, TypedDict, List

from .base_client import CIDXRemoteAPIClient, APIClientError, AuthenticationError
from ..remote.credential_manager import (
    ProjectCredentialManager,
    store_encrypted_credentials,
    load_encrypted_credentials,
    CredentialNotFoundError,
)

logger = logging.getLogger(__name__)


class AuthResponse(TypedDict):
    """Type definition for authentication response."""

    access_token: str
    token_type: str
    user_id: Optional[str]


@dataclass
class AuthStatus:
    """Structured container for authentication status information."""

    authenticated: bool
    username: Optional[str]
    role: Optional[str]
    token_valid: bool
    token_expires: Optional[datetime]
    refresh_expires: Optional[datetime]
    server_url: str
    last_refreshed: Optional[datetime]
    permissions: List[str]
    server_reachable: Optional[bool] = None
    server_version: Optional[str] = None


@dataclass
class CredentialHealth:
    """Structured container for credential health check results."""

    healthy: bool
    issues: List[str]
    encryption_valid: bool
    server_reachable: bool
    token_signature_valid: bool
    file_permissions_correct: bool
    recovery_suggestions: List[str]


class AuthAPIClient(CIDXRemoteAPIClient):
    """API client for authentication operations extending base functionality.

    Provides explicit login, register, and logout commands with:
    - Secure credential storage using AES-256 encryption
    - Integration with POST /auth/login and /auth/register endpoints
    - Comprehensive error handling with user-friendly messages
    - Project-specific credential isolation
    """

    def __init__(
        self,
        server_url: str,
        project_root: Optional[Path] = None,
        credentials: Optional[Dict[str, Any]] = None,
    ):
        """Initialize authentication API client.

        Args:
            server_url: Base URL of the CIDX server
            project_root: Project root directory for credential storage
            credentials: Optional existing credentials dictionary
        """
        # Initialize with empty credentials if none provided
        creds = credentials or {}
        super().__init__(server_url, creds, project_root)

        self.project_root = project_root
        self.credential_manager = ProjectCredentialManager()

    async def login(self, username: str, password: str) -> AuthResponse:
        """Authenticate user with server and store credentials securely.

        Args:
            username: Username for authentication
            password: Password for authentication

        Returns:
            AuthResponse: Authentication response with tokens

        Raises:
            AuthenticationError: If authentication fails
            APIClientError: If API request fails
            NetworkError: If network request fails
        """
        try:
            # Make login request to server
            auth_payload = {
                "username": username,
                "password": password,
            }

            # Use session directly for login (no auth header needed)
            auth_endpoint = f"{self.server_url}/auth/login"
            response = await self.session.post(auth_endpoint, json=auth_payload)

            if response.status_code == 200:
                auth_response = response.json()

                # Validate response format
                if not auth_response.get("access_token"):
                    raise AuthenticationError("No access token in response")

                # Store credentials securely if project root provided
                if self.project_root:
                    await self._store_credentials_securely(username, password)

                # Update internal credentials for future API calls
                self.credentials = {
                    "username": username,
                    "password": password,
                }

                return AuthResponse(
                    access_token=auth_response["access_token"],
                    token_type=auth_response.get("token_type", "bearer"),
                    user_id=auth_response.get("user_id"),
                )

            elif response.status_code == 401:
                try:
                    error_detail = response.json().get(
                        "detail", "Invalid username or password"
                    )
                except json.JSONDecodeError:
                    error_detail = "Invalid username or password"
                raise AuthenticationError(f"Authentication failed: {error_detail}")

            elif response.status_code == 429:
                raise APIClientError(
                    "Too many login attempts. Please wait before trying again.",
                    response.status_code,
                )

            else:
                try:
                    error_detail = response.json().get(
                        "detail", f"HTTP {response.status_code}"
                    )
                except json.JSONDecodeError:
                    error_detail = f"HTTP {response.status_code}"
                raise APIClientError(
                    f"Login failed: {error_detail}", response.status_code
                )

        except (AuthenticationError, APIClientError):
            raise
        except Exception as e:
            raise AuthenticationError(f"Unexpected error during login: {e}")

    async def register(
        self, username: str, password: str, role: str = "user"
    ) -> AuthResponse:
        """Register new user account and automatically login.

        Args:
            username: Username for new account
            password: Password for new account
            role: User role (user or admin), defaults to user

        Returns:
            AuthResponse: Authentication response with tokens

        Raises:
            APIClientError: If registration fails (username exists, validation errors)
            AuthenticationError: If auto-login after registration fails
            NetworkError: If network request fails
        """
        try:
            # Make registration request to server
            register_payload = {
                "username": username,
                "password": password,
                "role": role,
            }

            # Use session directly for registration (no auth header needed)
            register_endpoint = f"{self.server_url}/auth/register"
            response = await self.session.post(register_endpoint, json=register_payload)

            if response.status_code == 201 or response.status_code == 200:
                register_response = response.json()

                # Some servers auto-login on registration, others require explicit login
                if register_response.get("access_token"):
                    # Auto-login successful
                    if self.project_root:
                        await self._store_credentials_securely(username, password)

                    self.credentials = {
                        "username": username,
                        "password": password,
                    }

                    return AuthResponse(
                        access_token=register_response["access_token"],
                        token_type=register_response.get("token_type", "bearer"),
                        user_id=register_response.get("user_id"),
                    )
                else:
                    # Need to login explicitly after registration
                    return await self.login(username, password)

            elif response.status_code == 409:
                try:
                    error_detail = response.json().get(
                        "detail", "Username already exists"
                    )
                except json.JSONDecodeError:
                    error_detail = "Username already exists"
                raise APIClientError(
                    f"Registration failed: {error_detail}", response.status_code
                )

            elif response.status_code == 400:
                try:
                    error_detail = response.json().get(
                        "detail", "Invalid registration data"
                    )
                except json.JSONDecodeError:
                    error_detail = "Invalid registration data"
                raise APIClientError(
                    f"Registration failed: {error_detail}", response.status_code
                )

            else:
                try:
                    error_detail = response.json().get(
                        "detail", f"HTTP {response.status_code}"
                    )
                except json.JSONDecodeError:
                    error_detail = f"HTTP {response.status_code}"
                raise APIClientError(
                    f"Registration failed: {error_detail}", response.status_code
                )

        except (APIClientError, AuthenticationError):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error during registration: {e}")

    def logout(self) -> None:
        """Clear stored credentials and authentication state.

        This is a client-side operation that clears all stored credentials
        and resets authentication state. No server communication is required.
        """
        try:
            # Clear stored credential files
            if self.project_root:
                self._clear_stored_credentials()

            # Clear in-memory credentials
            self.credentials.clear()
            self._current_token = None

            # Clear persistent token if manager exists
            if self._persistent_token_manager:
                try:
                    self._persistent_token_manager.delete_token()
                except Exception as e:
                    logger.warning(f"Failed to clear persistent token: {e}")

            logger.info("Logout successful - all credentials cleared")

        except Exception as e:
            logger.warning(f"Error during logout: {e}")
            # Don't raise exception - logout should always succeed

    async def _store_credentials_securely(self, username: str, password: str) -> None:
        """Store credentials securely using AES-256 encryption.

        Args:
            username: Username to store
            password: Password to store

        Raises:
            Exception: If credential storage fails
        """
        if not self.project_root:
            return

        try:
            # Encrypt credentials using project-specific key derivation
            encrypted_data = self.credential_manager.encrypt_credentials(
                username=username,
                password=password,
                server_url=self.server_url,
                repo_path=str(self.project_root),
            )

            # Store encrypted credentials with secure file permissions
            store_encrypted_credentials(self.project_root, encrypted_data)

            logger.debug("Credentials stored securely")

        except Exception as e:
            logger.error(f"Failed to store credentials securely: {e}")
            raise

    def _clear_stored_credentials(self) -> None:
        """Clear stored credential files securely.

        Removes credential files and ensures secure cleanup.
        """
        if not self.project_root:
            return

        try:
            credentials_path = self.project_root / ".code-indexer" / ".creds"
            if credentials_path.exists():
                # Secure file deletion
                credentials_path.unlink()
                logger.debug("Stored credentials cleared")

        except Exception as e:
            logger.warning(f"Error clearing stored credentials: {e}")

    async def change_password(
        self, current_password: str, new_password: str
    ) -> Dict[str, Any]:
        """Change user password with current password validation.

        Args:
            current_password: Current password for verification
            new_password: New password to set

        Returns:
            dict: Server response with status and message

        Raises:
            AuthenticationError: If authentication fails or current password incorrect
            APIClientError: If API request fails or password policy violations
            NetworkError: If network request fails
        """
        try:
            # Prepare password change payload
            password_payload = {
                "old_password": current_password,
                "new_password": new_password,
            }

            # Make password change request using authenticated endpoint
            response = await self._authenticated_request(
                "PUT", "/api/users/change-password", json=password_payload
            )

            if response.status_code == 200:
                response_data: Dict[str, Any] = response.json()

                # Update stored credentials if successful and project root provided
                if self.project_root and response_data.get("status") == "success":
                    await self._store_credentials_securely(
                        self.credentials.get("username", ""), new_password
                    )
                    # Update in-memory credentials
                    self.credentials["password"] = new_password

                return response_data

            elif response.status_code == 400:
                try:
                    error_detail = response.json().get(
                        "detail", "Current password is incorrect"
                    )
                except json.JSONDecodeError:
                    error_detail = "Current password is incorrect"
                raise APIClientError(
                    f"Password change failed: {error_detail}", response.status_code
                )

            elif response.status_code == 401:
                try:
                    error_detail = response.json().get(
                        "detail", "Authentication required"
                    )
                except json.JSONDecodeError:
                    error_detail = "Authentication required"
                raise AuthenticationError(f"Password change failed: {error_detail}")

            else:
                try:
                    error_detail = response.json().get(
                        "detail", f"HTTP {response.status_code}"
                    )
                except json.JSONDecodeError:
                    error_detail = f"HTTP {response.status_code}"
                raise APIClientError(
                    f"Password change failed: {error_detail}", response.status_code
                )

        except (AuthenticationError, APIClientError):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error during password change: {e}")

    async def reset_password(self, username: str) -> Dict[str, Any]:
        """Initiate password reset for specified username.

        Args:
            username: Username for password reset

        Returns:
            dict: Server response with status and message

        Raises:
            APIClientError: If API request fails or username not found
            NetworkError: If network request fails
        """
        try:
            # Prepare reset request payload
            reset_payload = {
                "username": username,
            }

            # Use session directly for reset (no auth header needed)
            reset_endpoint = f"{self.server_url}/auth/reset-password"
            response = await self.session.post(reset_endpoint, json=reset_payload)

            if response.status_code == 200:
                reset_response: Dict[str, Any] = response.json()
                return reset_response

            elif response.status_code == 404:
                try:
                    error_detail = response.json().get("detail", "User not found")
                except json.JSONDecodeError:
                    error_detail = "User not found"
                raise APIClientError(
                    f"Password reset failed: {error_detail}", response.status_code
                )

            elif response.status_code == 429:
                try:
                    error_detail = response.json().get(
                        "detail", "Too many reset attempts"
                    )
                except json.JSONDecodeError:
                    error_detail = "Too many reset attempts"
                raise APIClientError(
                    f"Password reset failed: {error_detail}", response.status_code
                )

            else:
                try:
                    error_detail = response.json().get(
                        "detail", f"HTTP {response.status_code}"
                    )
                except json.JSONDecodeError:
                    error_detail = f"HTTP {response.status_code}"
                raise APIClientError(
                    f"Password reset failed: {error_detail}", response.status_code
                )

        except APIClientError:
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error during password reset: {e}")

    async def get_auth_status(self) -> AuthStatus:
        """Get current authentication status with token validation.

        Returns:
            AuthStatus: Comprehensive authentication status information

        Raises:
            AuthenticationError: If status check fails due to authentication issues
            APIClientError: If API request fails
            NetworkError: If network request fails
        """
        try:
            # Start with basic status from stored credentials
            is_authenticated = bool(self.credentials.get("username"))
            username = self.credentials.get("username")
            server_url = self.server_url

            # Initialize status with defaults
            status = AuthStatus(
                authenticated=is_authenticated,
                username=username,
                role=None,
                token_valid=False,
                token_expires=None,
                refresh_expires=None,
                server_url=server_url,
                last_refreshed=None,
                permissions=[],
                server_reachable=None,
                server_version=None,
            )

            if not is_authenticated:
                return status

            # Try to get current token and parse it
            try:
                current_token = await self._get_valid_token()
                if current_token:
                    # Parse token information using JWT manager
                    token_claims = self.jwt_manager.get_token_claims(current_token)
                    status.role = token_claims.get("role")
                    status.permissions = token_claims.get("permissions", [])
                    status.token_expires = self.jwt_manager.get_token_expiry_time(
                        current_token
                    )

                    # Check if token is valid (not expired)
                    status.token_valid = not self.jwt_manager.is_token_expired(
                        current_token
                    )

                    # If token is expired, try automatic refresh
                    if not status.token_valid:
                        try:
                            refresh_response = await self.refresh_token()
                            if refresh_response.get("access_token"):
                                status.token_valid = True
                                status.last_refreshed = datetime.now()
                                # Re-parse refreshed token
                                new_token = refresh_response["access_token"]
                                status.token_expires = (
                                    self.jwt_manager.get_token_expiry_time(new_token)
                                )
                        except Exception:
                            # Refresh failed - clear invalid credentials
                            self._clear_stored_credentials()
                            status.authenticated = False
                            status.token_valid = False

            except Exception:
                # Token parsing failed - token might be corrupted
                status.token_valid = False

            # Test server connectivity if we have valid credentials
            if status.authenticated and status.token_valid:
                try:
                    # Simple connectivity test using health endpoint
                    health_response = await self._authenticated_request(
                        "GET", "/health"
                    )
                    status.server_reachable = health_response.status_code == 200

                    # Try to get server version if available
                    try:
                        version_data = health_response.json()
                        status.server_version = version_data.get("version")
                    except Exception:
                        pass

                except Exception:
                    status.server_reachable = False

            return status

        except (AuthenticationError, APIClientError):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error getting auth status: {e}")

    async def refresh_token(self) -> Dict[str, Any]:
        """Manually refresh authentication token.

        Returns:
            dict: Server response with new token information

        Raises:
            AuthenticationError: If refresh fails due to expired/invalid refresh token
            APIClientError: If API request fails
            NetworkError: If network request fails
        """
        try:
            # Make refresh request using existing refresh token
            response = await self._authenticated_request("POST", "/auth/refresh")

            if response.status_code == 200:
                refresh_response: Dict[str, Any] = response.json()

                # Validate response format
                if not refresh_response.get("access_token"):
                    raise AuthenticationError("No access token in refresh response")

                # Update stored credentials with new token if project root provided
                if self.project_root:
                    await self._store_credentials_securely(
                        self.credentials.get("username", ""),
                        self.credentials.get("password", ""),
                    )

                # Update internal token
                self._current_token = refresh_response["access_token"]

                return refresh_response

            elif response.status_code == 401:
                # Refresh token expired or invalid
                error_detail = "Refresh token has expired"
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", error_detail)
                except Exception:
                    pass

                # Clear invalid credentials
                self._clear_stored_credentials()
                self.credentials.clear()
                self._current_token = None

                raise AuthenticationError(f"Token refresh failed: {error_detail}")

            else:
                try:
                    error_detail = response.json().get(
                        "detail", f"HTTP {response.status_code}"
                    )
                except Exception:
                    error_detail = f"HTTP {response.status_code}"
                raise APIClientError(
                    f"Token refresh failed: {error_detail}", response.status_code
                )

        except (AuthenticationError, APIClientError):
            raise
        except Exception as e:
            raise APIClientError(f"Unexpected error during token refresh: {e}")

    async def validate_credentials(self) -> bool:
        """Silently validate current credentials.

        Returns:
            bool: True if credentials are valid, False otherwise

        Note:
            This method is designed for silent operation and will not raise
            exceptions for authentication failures - only for unexpected errors.
        """
        try:
            # Check if we have stored credentials
            if not self.credentials.get("username"):
                return False

            # Try to get current token
            current_token = await self._get_valid_token()
            if not current_token:
                return False

            # Check if token is not expired
            if self.jwt_manager.is_token_expired(current_token):
                # Try to refresh
                try:
                    refresh_response = await self.refresh_token()
                    access_token = refresh_response.get("access_token")
                    return bool(access_token)
                except Exception:
                    return False

            # Token exists and is not expired - validate with server
            try:
                response = await self._authenticated_request("GET", "/auth/validate")
                result: bool = response.status_code == 200
                return result
            except Exception:
                # Server unreachable or validation failed
                return False

        except Exception:
            # Unexpected error during validation
            return False

    async def check_credential_health(self) -> CredentialHealth:
        """Comprehensive credential health check.

        Returns:
            CredentialHealth: Detailed health check results with specific diagnostics

        Raises:
            APIClientError: If health check encounters unexpected errors
        """
        try:
            issues = []
            recovery_suggestions = []
            encryption_valid = True
            server_reachable = False
            token_signature_valid = True
            file_permissions_correct = True

            # Check 1: Verify credential file exists and has correct permissions
            if self.project_root:
                creds_path = self.project_root / ".code-indexer" / ".creds"
                if creds_path.exists():
                    file_mode = creds_path.stat().st_mode
                    if file_mode & 0o077:  # Check if group/other permissions are set
                        file_permissions_correct = False
                        issues.append("Credential file has insecure permissions")
                        recovery_suggestions.append(
                            "Run 'chmod 600 .code-indexer/.creds' to fix permissions"
                        )
                else:
                    encryption_valid = False
                    issues.append("No credential file found")
                    recovery_suggestions.append("Use 'cidx auth login' to authenticate")

            # Check 2: Verify credential encryption/decryption
            if self.credentials.get("username"):
                try:
                    # Test that we can access stored credentials
                    username = self.credentials["username"]
                    if not username:
                        encryption_valid = False
                        issues.append("Credential decryption returned empty username")
                        recovery_suggestions.append(
                            "Use 'cidx auth logout' and 'cidx auth login' to recover"
                        )
                except Exception:
                    encryption_valid = False
                    issues.append("Credential file cannot be decrypted")
                    recovery_suggestions.append(
                        "Use 'cidx auth logout' and 'cidx auth login' to recover"
                    )

            # Check 3: Validate JWT token structure and signature
            try:
                current_token = await self._get_valid_token()
                if current_token:
                    # Try to parse token
                    self.jwt_manager.get_token_claims(current_token)
                else:
                    token_signature_valid = False
                    issues.append("No authentication token available")
                    recovery_suggestions.append(
                        "Use 'cidx auth login' to re-authenticate"
                    )
            except Exception:
                token_signature_valid = False
                issues.append("JWT token has invalid format or signature")
                recovery_suggestions.append(
                    "Use 'cidx auth logout' and 'cidx auth login' to recover"
                )

            # Check 4: Test server connectivity
            try:
                response = await self._authenticated_request("GET", "/health")
                server_reachable = response.status_code == 200
            except Exception:
                server_reachable = False
                issues.append("Server unreachable for token validation")
                recovery_suggestions.append(
                    "Check network connectivity and server status"
                )

            # Determine overall health
            healthy = (
                encryption_valid
                and server_reachable
                and token_signature_valid
                and file_permissions_correct
                and len(issues) == 0
            )

            return CredentialHealth(
                healthy=healthy,
                issues=issues,
                encryption_valid=encryption_valid,
                server_reachable=server_reachable,
                token_signature_valid=token_signature_valid,
                file_permissions_correct=file_permissions_correct,
                recovery_suggestions=recovery_suggestions,
            )

        except Exception as e:
            raise APIClientError(
                f"Unexpected error during credential health check: {e}"
            )

    @classmethod
    def load_from_stored_credentials(
        cls,
        server_url: str,
        project_root: Path,
        username: str,
    ) -> "AuthAPIClient":
        """Load AuthAPIClient with stored encrypted credentials.

        Args:
            server_url: Server URL for authentication
            project_root: Project root directory
            username: Username for credential decryption

        Returns:
            AuthAPIClient: Initialized client with stored credentials

        Raises:
            CredentialNotFoundError: If no stored credentials found
            Exception: If credential loading fails
        """
        try:
            # Load encrypted credential data
            encrypted_data = load_encrypted_credentials(project_root)

            # Decrypt credentials
            credential_manager = ProjectCredentialManager()
            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username,
                repo_path=str(project_root),
                server_url=server_url,
            )

            # Create client with decrypted credentials
            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }

            return cls(
                server_url=server_url,
                project_root=project_root,
                credentials=credentials,
            )

        except CredentialNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to load stored credentials: {e}")
            raise


def create_auth_client(
    server_url: str,
    project_root: Optional[Path] = None,
    username: Optional[str] = None,
) -> AuthAPIClient:
    """Factory function to create AuthAPIClient with optional credential loading.

    Args:
        server_url: Server URL for authentication
        project_root: Optional project root directory
        username: Optional username for loading stored credentials

    Returns:
        AuthAPIClient: Initialized authentication client

    Note:
        If project_root and username are provided, attempts to load stored
        credentials. Falls back to empty credentials if loading fails.
    """
    if project_root and username:
        try:
            return AuthAPIClient.load_from_stored_credentials(
                server_url=server_url,
                project_root=project_root,
                username=username,
            )
        except (CredentialNotFoundError, Exception) as e:
            logger.debug(f"Could not load stored credentials: {e}")
            # Fall back to empty client

    return AuthAPIClient(
        server_url=server_url,
        project_root=project_root,
    )
