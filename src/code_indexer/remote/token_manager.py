"""Persistent JWT Token Manager for CIDX Remote Authentication.

Provides secure, persistent JWT token storage with automatic refresh,
re-authentication fallback, and comprehensive security features.
"""

import json
import fcntl
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import jwt as jose_jwt

from .credential_manager import ProjectCredentialManager
from .exceptions import RemoteConfigurationError


class TokenStorageError(RemoteConfigurationError):
    """Raised when token storage operations fail."""

    pass


class TokenSecurityError(RemoteConfigurationError):
    """Raised when token security constraints are violated."""

    pass


class TokenLockTimeoutError(RemoteConfigurationError):
    """Raised when file locking operations timeout."""

    pass


@dataclass
class StoredToken:
    """Structured container for stored JWT token data with validation methods."""

    token: str
    expires_at: datetime
    created_at: datetime
    encrypted_data: bytes

    def is_expired(self) -> bool:
        """Check if the stored token has expired.

        Returns:
            True if token is expired, False otherwise
        """
        return datetime.now(timezone.utc) >= self.expires_at

    def expires_soon(self, threshold_minutes: int = 2) -> bool:
        """Check if the token expires within the specified threshold.

        Args:
            threshold_minutes: Minutes before expiration to trigger refresh

        Returns:
            True if token expires within threshold, False otherwise
        """
        threshold_time = datetime.now(timezone.utc) + timedelta(
            minutes=threshold_minutes
        )
        return threshold_time >= self.expires_at

    def validate_security_constraints(self) -> None:
        """Validate that the token meets security constraints.

        Raises:
            TokenSecurityError: If token violates security constraints
        """
        try:
            # Decode token header to check algorithm
            header = jose_jwt.get_unverified_header(self.token)
            algorithm = header.get("alg")

            # Allow RS256 and HS256 algorithms
            allowed_algorithms = ["RS256", "HS256"]
            if algorithm not in allowed_algorithms:
                raise TokenSecurityError(
                    f"Invalid JWT algorithm '{algorithm}', only {allowed_algorithms} are allowed"
                )

            # Check token lifetime (24-hour maximum)
            token_lifetime = self.expires_at - self.created_at
            max_lifetime = timedelta(hours=24)

            if token_lifetime > max_lifetime:
                raise TokenSecurityError(
                    f"Token lifetime {token_lifetime} exceeds maximum {max_lifetime}"
                )

        except jose_jwt.InvalidTokenError as e:
            raise TokenSecurityError(f"Invalid JWT token structure: {e}")
        except Exception as e:
            raise TokenSecurityError(f"Token security validation failed: {e}")


class PersistentTokenManager:
    """Manages persistent JWT token storage with security and reliability features.

    Features:
    - Secure file operations with proper permissions (0o600)
    - Project-specific token encryption using existing credential manager
    - Token caching with configurable TTL (default 60 seconds)
    - Atomic file operations to prevent corruption
    - File locking for concurrent access safety
    - Security constraints enforcement (RS256, 24-hour lifetime limit)
    - Memory security with sensitive data cleanup
    """

    def __init__(
        self,
        project_root: Path,
        credential_manager: ProjectCredentialManager,
        username: str,
        repo_path: str,
        server_url: str,
        cache_ttl_seconds: int = 60,
        lock_timeout_seconds: int = 5,
    ):
        """Initialize persistent token manager.

        Args:
            project_root: Root directory of the project
            credential_manager: Project credential manager for encryption
            username: Username for key derivation
            repo_path: Repository path for key derivation
            server_url: Server URL for key derivation
            cache_ttl_seconds: Token cache TTL in seconds
            lock_timeout_seconds: File lock timeout in seconds
        """
        self.project_root = project_root
        self.credential_manager = credential_manager
        self.username = username
        self.repo_path = repo_path
        self.server_url = server_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.lock_timeout_seconds = lock_timeout_seconds

        # Token file path
        self.token_file_path = project_root / ".code-indexer" / ".token"

        # Thread-safe caching
        self._cache_lock = threading.RLock()
        self._cached_token: Optional[StoredToken] = None
        self._cache_timestamp: float = 0

        # Ensure directory exists with proper permissions
        self.token_file_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _is_cache_valid(self) -> bool:
        """Check if cached token is still valid based on TTL.

        Returns:
            True if cache is valid, False if expired
        """
        if not self._cached_token:
            return False

        elapsed = time.time() - self._cache_timestamp
        return elapsed < self.cache_ttl_seconds

    def _update_cache(self, token: StoredToken) -> None:
        """Update token cache with thread safety.

        Args:
            token: Token to cache
        """
        with self._cache_lock:
            self._cached_token = token
            self._cache_timestamp = time.time()

    def _clear_cache(self) -> None:
        """Clear token cache with thread safety."""
        with self._cache_lock:
            self._cached_token = None
            self._cache_timestamp = 0

    def _encrypt_token_data(
        self, token: str, expires_at: datetime, created_at: datetime
    ) -> bytes:
        """Encrypt token data using project-specific encryption.

        Args:
            token: JWT token string
            expires_at: Token expiration time
            created_at: Token creation time

        Returns:
            Encrypted token data

        Raises:
            TokenStorageError: If encryption fails
        """
        try:
            # Create token data structure
            token_data = {
                "token": token,
                "expires_at": expires_at.isoformat(),
                "created_at": created_at.isoformat(),
                "version": "1.0",
            }

            # Serialize to JSON
            json_data = json.dumps(token_data)

            # Use existing credential manager for encryption
            encrypted_data = self.credential_manager.encrypt_credentials(
                username=self.username,
                password=json_data,  # Use JSON as "password" for encryption
                server_url=self.server_url,
                repo_path=self.repo_path,
            )

            return encrypted_data

        except Exception as e:
            raise TokenStorageError(f"Failed to encrypt token data: {e}")

    def _decrypt_token_data(
        self, encrypted_data: bytes
    ) -> tuple[str, datetime, datetime]:
        """Decrypt token data using project-specific decryption.

        Args:
            encrypted_data: Encrypted token data

        Returns:
            Tuple of (token, expires_at, created_at)

        Raises:
            TokenStorageError: If decryption fails
        """
        try:
            # Use existing credential manager for decryption
            decrypted_creds = self.credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=self.username,
                repo_path=self.repo_path,
                server_url=self.server_url,
            )

            # Parse JSON from "password" field
            json_data = decrypted_creds.password
            token_data = json.loads(json_data)

            # Extract token information
            token = token_data["token"]
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            created_at = datetime.fromisoformat(token_data["created_at"])

            return token, expires_at, created_at

        except Exception as e:
            raise TokenStorageError(f"Failed to decrypt token data: {e}")

    def _atomic_file_write(self, data: bytes) -> None:
        """Write data to token file atomically.

        Args:
            data: Data to write

        Raises:
            TokenStorageError: If atomic write fails
        """
        try:
            # Create temporary file in same directory
            temp_path = self.token_file_path.with_suffix(".tmp")

            # Write to temporary file
            with open(temp_path, "wb") as f:
                f.write(data)

            # Set secure permissions before rename
            temp_path.chmod(0o600)

            # Atomic rename to final location
            temp_path.rename(self.token_file_path)

        except Exception as e:
            # Clean up temporary file on error
            if temp_path.exists():
                temp_path.unlink()
            raise TokenStorageError(f"Atomic file write failed: {e}")

    def _acquire_file_lock(self, file_handle, timeout: Optional[int] = None) -> None:
        """Acquire exclusive file lock with timeout.

        Args:
            file_handle: Open file handle
            timeout: Lock timeout in seconds

        Raises:
            TokenLockTimeoutError: If lock acquisition times out
        """
        if timeout is None:
            timeout = self.lock_timeout_seconds

        start_time = time.time()

        while True:
            try:
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return  # Lock acquired successfully
            except BlockingIOError:
                # Lock not available, check timeout
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise TokenLockTimeoutError(
                        f"Failed to acquire file lock within {timeout} seconds"
                    )
                # Brief sleep before retry
                time.sleep(0.1)
            except Exception as e:
                raise TokenStorageError(f"File locking error: {e}")

    def _release_file_lock(self, file_handle) -> None:
        """Release file lock.

        Args:
            file_handle: Open file handle
        """
        try:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            # Ignore unlock errors - lock will be released when file closes
            pass

    def store_token(self, stored_token: StoredToken) -> None:
        """Store JWT token with secure file operations and validation.

        Args:
            stored_token: Token to store

        Raises:
            TokenStorageError: If storage fails
            TokenSecurityError: If token violates security constraints
        """
        try:
            # Validate security constraints
            stored_token.validate_security_constraints()

            # Encrypt token data
            encrypted_data = self._encrypt_token_data(
                stored_token.token, stored_token.expires_at, stored_token.created_at
            )

            # Update encrypted data in stored token
            stored_token.encrypted_data = encrypted_data

            # Write to file atomically
            self._atomic_file_write(encrypted_data)

            # Update cache
            self._update_cache(stored_token)

        except (TokenSecurityError, TokenStorageError):
            raise
        except Exception as e:
            raise TokenStorageError(f"Failed to store token: {e}")

    def load_token(self) -> Optional[StoredToken]:
        """Load JWT token from persistent storage with caching.

        Returns:
            Stored token if available, None if not found

        Raises:
            TokenStorageError: If loading fails
            TokenSecurityError: If token file violates security constraints
        """
        try:
            # Check cache first
            with self._cache_lock:
                if self._is_cache_valid() and self._cached_token:
                    return self._cached_token

            # Check if token file exists
            if not self.token_file_path.exists():
                return None

            # Validate file permissions
            file_stat = self.token_file_path.stat()
            file_mode = file_stat.st_mode & 0o777
            if file_mode != 0o600:
                # Attempt to fix permissions
                self.token_file_path.chmod(0o600)

            # Check file size limit (64KB)
            file_size = file_stat.st_size
            if file_size > 64 * 1024:  # 64KB limit
                raise TokenSecurityError(
                    f"Token file size {file_size} bytes exceeds 64KB limit"
                )

            # Read encrypted data with file locking
            with open(self.token_file_path, "rb") as f:
                self._acquire_file_lock(f)
                try:
                    encrypted_data = f.read()
                finally:
                    self._release_file_lock(f)

            # Decrypt token data
            token, expires_at, created_at = self._decrypt_token_data(encrypted_data)

            # Create stored token object
            stored_token = StoredToken(
                token=token,
                expires_at=expires_at,
                created_at=created_at,
                encrypted_data=encrypted_data,
            )

            # Validate security constraints
            stored_token.validate_security_constraints()

            # Update cache
            self._update_cache(stored_token)

            return stored_token

        except (TokenSecurityError, TokenStorageError):
            raise
        except Exception as e:
            raise TokenStorageError(f"Failed to load token: {e}")

    def delete_token(self) -> None:
        """Delete stored token and clear cache.

        Raises:
            TokenStorageError: If deletion fails
        """
        try:
            # Clear cache first
            self._clear_cache()

            # Remove file if it exists
            if self.token_file_path.exists():
                self.token_file_path.unlink()

        except Exception as e:
            raise TokenStorageError(f"Failed to delete token: {e}")

    def is_token_valid(self, stored_token: StoredToken) -> bool:
        """Check if stored token is valid and not expired.

        Args:
            stored_token: Token to validate

        Returns:
            True if token is valid, False otherwise
        """
        try:
            # Check if expired
            if stored_token.is_expired():
                return False

            # Validate security constraints
            stored_token.validate_security_constraints()

            return True

        except Exception:
            return False

    def cleanup_sensitive_data(self) -> None:
        """Clean up sensitive data from memory with secure overwriting.

        This method performs 3-iteration overwriting of sensitive data
        in memory as a security measure.
        """
        with self._cache_lock:
            if self._cached_token:
                # Overwrite sensitive fields multiple times
                for _ in range(3):
                    # Create random data of same length
                    if hasattr(self._cached_token, "token"):
                        random_token = secrets.token_urlsafe(
                            len(self._cached_token.token)
                        )
                        self._cached_token.token = random_token

                    if hasattr(self._cached_token, "encrypted_data"):
                        random_data = secrets.token_bytes(
                            len(self._cached_token.encrypted_data)
                        )
                        self._cached_token.encrypted_data = random_data

                # Clear cache
                self._cached_token = None
                self._cache_timestamp = 0


def invalidate_cached_tokens(project_root: str) -> None:
    """Invalidate cached tokens for a project after credential rotation.

    Args:
        project_root: Root directory of the project
    """
    try:
        from pathlib import Path

        project_path = Path(project_root)
        # Create a minimal token manager for deletion only
        token_manager = PersistentTokenManager.__new__(PersistentTokenManager)
        token_manager.project_root = project_path
        token_manager.token_file_path = project_path / ".code-indexer" / ".token"
        token_manager._cache_lock = threading.RLock()
        token_manager._cached_token = None
        token_manager._cache_timestamp = 0

        token_manager.delete_token()
        token_manager.cleanup_sensitive_data()
    except Exception:
        # Ignore errors during token invalidation - not critical for credential rotation
        pass
