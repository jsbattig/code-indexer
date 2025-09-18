"""Exception classes for remote functionality."""

from typing import Optional


class RemoteInitializationError(Exception):
    """Base exception for remote initialization errors."""

    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class URLValidationError(RemoteInitializationError):
    """Exception raised when URL validation fails."""

    pass


class ServerConnectivityError(RemoteInitializationError):
    """Exception raised when server connectivity test fails."""

    pass


class CredentialValidationError(RemoteInitializationError):
    """Exception raised when credential validation fails."""

    pass


class RemoteConfigurationError(RemoteInitializationError):
    """Exception raised when remote configuration creation fails."""

    pass
