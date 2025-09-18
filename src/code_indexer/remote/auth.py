"""Authentication and credential validation for remote servers."""

from typing import Dict, Any

from code_indexer.api_clients.base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
)
from .exceptions import CredentialValidationError


async def validate_credentials(
    server_url: str, username: str, password: str
) -> Dict[str, Any]:
    """Validate credentials with a remote CIDX server.

    Args:
        server_url: The server URL to authenticate against
        username: The username for authentication
        password: The password for authentication

    Returns:
        Dict containing user information on successful authentication

    Raises:
        CredentialValidationError: If credential validation fails
    """
    if not server_url:
        raise CredentialValidationError("Server URL cannot be empty")
    if not username:
        raise CredentialValidationError("Username cannot be empty")
    if not password:
        raise CredentialValidationError("Password cannot be empty")

    # Create temporary credentials dict for the API client
    temp_credentials = {
        "username": username,
        "password": password,
        "server_url": server_url,
    }

    try:
        # Create API client and attempt authentication
        async with CIDXRemoteAPIClient(
            server_url=server_url, credentials=temp_credentials
        ) as client:
            # Attempt to authenticate - this will raise AuthenticationError if invalid
            token = await client._authenticate()

            if not token:
                raise CredentialValidationError(
                    "Authentication succeeded but no token received"
                )

            # If we get here, authentication was successful
            # Return user info (in a real implementation, we'd decode the JWT token)
            # For now, return basic user info
            user_info = {
                "username": username,
                "authenticated": True,
                "server_url": server_url,
                # In a real implementation, we'd extract permissions from the JWT token
                "permissions": ["read", "write"],  # Placeholder
            }

            return user_info

    except AuthenticationError as e:
        raise CredentialValidationError(f"Invalid credentials: {str(e)}")

    except APIClientError as e:
        if e.status_code == 401:
            raise CredentialValidationError("Invalid username or password")
        else:
            raise CredentialValidationError(
                f"Server error during authentication: {str(e)}"
            )

    except Exception as e:
        raise CredentialValidationError(
            f"Unexpected error during credential validation: {str(e)}"
        )
