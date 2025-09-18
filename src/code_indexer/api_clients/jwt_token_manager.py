"""JWT Token Manager for API Client Authentication.

Handles JWT token validation, expiration detection, and refresh logic
without depending on external secrets or server implementations.
"""

import json
import base64
from datetime import datetime, timezone
from typing import Dict, Any, Optional, cast


class TokenValidationError(Exception):
    """Exception raised when JWT token validation fails."""

    pass


class JWTTokenManager:
    """Manages JWT token validation and expiration detection for API clients."""

    def __init__(self, refresh_threshold_minutes: int = 2):
        """Initialize JWT token manager.

        Args:
            refresh_threshold_minutes: Number of minutes before expiration to trigger refresh
        """
        self.refresh_threshold_minutes = refresh_threshold_minutes

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode JWT token without signature verification.

        This method extracts the payload for expiration checking without
        validating the signature (signature validation is handled by the server).

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            TokenValidationError: If token format is invalid
        """
        if not token or not isinstance(token, str):
            raise TokenValidationError("Token must be a non-empty string")

        try:
            # Split JWT token into parts
            parts = token.split(".")
            if len(parts) != 3:
                raise TokenValidationError(
                    f"Invalid JWT format: expected 3 parts, got {len(parts)}"
                )

            # Decode the payload (second part)
            payload_part = parts[1]

            # Add padding if needed for base64 decoding
            padding = 4 - (len(payload_part) % 4)
            if padding != 4:
                payload_part += "=" * padding

            # Decode base64 payload
            try:
                payload_bytes = base64.urlsafe_b64decode(payload_part)
                payload = json.loads(payload_bytes.decode("utf-8"))
            except (ValueError, json.JSONDecodeError) as e:
                raise TokenValidationError(f"Failed to decode JWT payload: {e}")

            return cast(Dict[str, Any], payload)

        except Exception as e:
            if isinstance(e, TokenValidationError):
                raise
            raise TokenValidationError(f"Invalid JWT token: {e}")

    def is_token_expired(self, token: str) -> bool:
        """Check if JWT token has expired.

        Args:
            token: JWT token string

        Returns:
            True if token is expired, False otherwise

        Raises:
            TokenValidationError: If token format is invalid
        """
        try:
            payload = self.decode_token(token)

            # Check if expiration claim exists
            exp_claim = payload.get("exp")
            if exp_claim is None:
                # No expiration claim - treat as suspicious but not expired
                return False

            # Convert expiration to timestamp
            try:
                if isinstance(exp_claim, str):
                    exp_timestamp = float(exp_claim)
                else:
                    exp_timestamp = float(exp_claim)
            except (ValueError, TypeError):
                raise TokenValidationError(
                    f"Invalid expiration timestamp format: {exp_claim}"
                )

            # Compare with current time
            current_timestamp = datetime.now(timezone.utc).timestamp()
            return current_timestamp >= exp_timestamp

        except TokenValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            raise TokenValidationError(f"Failed to check token expiration: {e}")

    def is_token_near_expiry(self, token: str) -> bool:
        """Check if JWT token is near expiration and should be refreshed.

        Args:
            token: JWT token string

        Returns:
            True if token should be refreshed, False otherwise

        Raises:
            TokenValidationError: If token format is invalid
        """
        try:
            payload = self.decode_token(token)

            # Check if expiration claim exists
            exp_claim = payload.get("exp")
            if exp_claim is None:
                # No expiration claim - cannot determine proximity
                return False

            # Convert expiration to timestamp
            try:
                if isinstance(exp_claim, str):
                    exp_timestamp = float(exp_claim)
                else:
                    exp_timestamp = float(exp_claim)
            except (ValueError, TypeError):
                raise TokenValidationError(
                    f"Invalid expiration timestamp format: {exp_claim}"
                )

            # Calculate refresh threshold
            refresh_threshold_seconds = self.refresh_threshold_minutes * 60
            current_timestamp = datetime.now(timezone.utc).timestamp()
            time_until_expiry = exp_timestamp - current_timestamp

            # Token should be refreshed if time until expiry is less than threshold
            return time_until_expiry <= refresh_threshold_seconds

        except TokenValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            raise TokenValidationError(f"Failed to check token expiry proximity: {e}")

    def get_token_expiry_time(self, token: str) -> Optional[datetime]:
        """Get the expiration time of a JWT token.

        Args:
            token: JWT token string

        Returns:
            Expiration datetime in UTC, or None if no expiration claim

        Raises:
            TokenValidationError: If token format is invalid
        """
        try:
            payload = self.decode_token(token)

            exp_claim = payload.get("exp")
            if exp_claim is None:
                return None

            # Convert to datetime
            try:
                if isinstance(exp_claim, str):
                    exp_timestamp = float(exp_claim)
                else:
                    exp_timestamp = float(exp_claim)

                return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

            except (ValueError, TypeError):
                raise TokenValidationError(
                    f"Invalid expiration timestamp format: {exp_claim}"
                )

        except TokenValidationError:
            raise
        except Exception as e:
            raise TokenValidationError(f"Failed to get token expiry time: {e}")

    def get_token_username(self, token: str) -> Optional[str]:
        """Extract username from JWT token payload.

        Args:
            token: JWT token string

        Returns:
            Username from token, or None if not present

        Raises:
            TokenValidationError: If token format is invalid
        """
        try:
            payload = self.decode_token(token)
            return payload.get("username")
        except TokenValidationError:
            raise
        except Exception as e:
            raise TokenValidationError(f"Failed to extract username from token: {e}")

    def get_token_claims(self, token: str) -> Dict[str, Any]:
        """Get all claims from JWT token payload.

        Args:
            token: JWT token string

        Returns:
            Dictionary of all token claims

        Raises:
            TokenValidationError: If token format is invalid
        """
        return self.decode_token(token)
