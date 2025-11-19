"""
Rate limiters for OAuth endpoints to prevent abuse.

Following CLAUDE.md principles: NO MOCKS - Real rate limiting implementation.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from threading import Lock


class OAuthTokenRateLimiter:
    """
    Rate limiter for /oauth/token endpoint.
    
    Security requirements:
    - Maximum 10 failed attempts per client
    - 5-minute lockout period after exceeding limit
    - Thread-safe implementation
    """

    def __init__(self):
        self._attempts: Dict[str, Dict] = {}
        self._lock = Lock()
        self._max_attempts = 10
        self._lockout_duration_minutes = 5

    def check_rate_limit(self, client_id: str) -> Optional[str]:
        """
        Check if client is rate limited.
        
        Args:
            client_id: Client ID to check
            
        Returns:
            None if not rate limited, error message if rate limited
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            self._cleanup_expired_entries(now)

            if client_id not in self._attempts:
                return None

            client_data = self._attempts[client_id]

            if client_data.get("locked_until") and now < client_data["locked_until"]:
                remaining_time = client_data["locked_until"] - now
                remaining_minutes = int(remaining_time.total_seconds() / 60) + 1
                return f"Too many failed attempts. Try again in {remaining_minutes} minutes."

            return None

    def record_failed_attempt(self, client_id: str) -> bool:
        """
        Record a failed token request attempt.
        
        Args:
            client_id: Client ID that failed
            
        Returns:
            True if client should be locked out, False otherwise
        """
        with self._lock:
            now = datetime.now(timezone.utc)

            if client_id not in self._attempts:
                self._attempts[client_id] = {
                    "count": 0,
                    "first_attempt": now,
                    "locked_until": None,
                }

            client_data = self._attempts[client_id]

            if client_data.get("locked_until") and now >= client_data["locked_until"]:
                client_data["count"] = 0
                client_data["locked_until"] = None
                client_data["first_attempt"] = now

            client_data["count"] += 1

            if client_data["count"] >= self._max_attempts:
                lockout_until = now + timedelta(minutes=self._lockout_duration_minutes)
                client_data["locked_until"] = lockout_until
                return True

            return False

    def record_successful_attempt(self, client_id: str) -> None:
        """
        Record a successful token request (clears rate limiting).
        
        Args:
            client_id: Client ID that succeeded
        """
        with self._lock:
            if client_id in self._attempts:
                del self._attempts[client_id]

    def _cleanup_expired_entries(self, now: datetime) -> None:
        """Clean up expired rate limiting entries."""
        expired_clients = []

        for client_id, client_data in self._attempts.items():
            locked_until = client_data.get("locked_until")
            if locked_until and now > locked_until + timedelta(hours=1):
                expired_clients.append(client_id)

        for client_id in expired_clients:
            del self._attempts[client_id]


class OAuthRegisterRateLimiter:
    """
    Rate limiter for /oauth/register endpoint.
    
    Security requirements:
    - Maximum 5 failed attempts per IP
    - 15-minute lockout period after exceeding limit
    - Thread-safe implementation
    """

    def __init__(self):
        self._attempts: Dict[str, Dict] = {}
        self._lock = Lock()
        self._max_attempts = 5
        self._lockout_duration_minutes = 15

    def check_rate_limit(self, ip_address: str) -> Optional[str]:
        """
        Check if IP is rate limited.
        
        Args:
            ip_address: IP address to check
            
        Returns:
            None if not rate limited, error message if rate limited
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            self._cleanup_expired_entries(now)

            if ip_address not in self._attempts:
                return None

            ip_data = self._attempts[ip_address]

            if ip_data.get("locked_until") and now < ip_data["locked_until"]:
                remaining_time = ip_data["locked_until"] - now
                remaining_minutes = int(remaining_time.total_seconds() / 60) + 1
                return f"Too many failed attempts. Try again in {remaining_minutes} minutes."

            return None

    def record_failed_attempt(self, ip_address: str) -> bool:
        """
        Record a failed registration attempt.
        
        Args:
            ip_address: IP address that failed
            
        Returns:
            True if IP should be locked out, False otherwise
        """
        with self._lock:
            now = datetime.now(timezone.utc)

            if ip_address not in self._attempts:
                self._attempts[ip_address] = {
                    "count": 0,
                    "first_attempt": now,
                    "locked_until": None,
                }

            ip_data = self._attempts[ip_address]

            if ip_data.get("locked_until") and now >= ip_data["locked_until"]:
                ip_data["count"] = 0
                ip_data["locked_until"] = None
                ip_data["first_attempt"] = now

            ip_data["count"] += 1

            if ip_data["count"] >= self._max_attempts:
                lockout_until = now + timedelta(minutes=self._lockout_duration_minutes)
                ip_data["locked_until"] = lockout_until
                return True

            return False

    def record_successful_attempt(self, ip_address: str) -> None:
        """
        Record a successful registration (clears rate limiting).
        
        Args:
            ip_address: IP address that succeeded
        """
        with self._lock:
            if ip_address in self._attempts:
                del self._attempts[ip_address]

    def _cleanup_expired_entries(self, now: datetime) -> None:
        """Clean up expired rate limiting entries."""
        expired_ips = []

        for ip_address, ip_data in self._attempts.items():
            locked_until = ip_data.get("locked_until")
            if locked_until and now > locked_until + timedelta(hours=1):
                expired_ips.append(ip_address)

        for ip_address in expired_ips:
            del self._attempts[ip_address]


# Global rate limiter instances
oauth_token_rate_limiter = OAuthTokenRateLimiter()
oauth_register_rate_limiter = OAuthRegisterRateLimiter()
