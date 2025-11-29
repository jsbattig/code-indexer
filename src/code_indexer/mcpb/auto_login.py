"""Automatic login functionality for MCPB.

This module provides automatic re-authentication when tokens expire
by using stored encrypted credentials to perform a full login.
"""

import sys
from typing import Tuple

import httpx

from .credential_storage import credentials_exist, load_credentials
from .http_client import HttpError


async def attempt_auto_login(server_url: str, timeout: int) -> Tuple[str, str]:
    """Attempt automatic login using stored credentials.

    Loads encrypted credentials and performs HTTP POST to /auth/login endpoint.
    Returns new access_token and refresh_token on success.

    Args:
        server_url: Base URL of CIDX server
        timeout: Request timeout in seconds

    Returns:
        Tuple of (access_token, refresh_token)

    Raises:
        ValueError: If no credentials are available
        HttpError: If login fails (authentication error, server error, network error)
    """
    # Check if credentials exist
    if not credentials_exist():
        raise ValueError("No credentials available for auto-login")

    # Load credentials
    try:
        username, password = load_credentials()
    except Exception as e:
        raise HttpError(f"Failed to load credentials: {str(e)}") from e

    # Prepare login request
    login_url = f"{server_url}/auth/login"
    login_data = {"username": username, "password": password}

    # Attempt login
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                login_url,
                json=login_data,
                headers={"Content-Type": "application/json"},
            )

            # Handle 401 (invalid credentials)
            if response.status_code == 401:
                raise HttpError(
                    f"Auto-login failed: Invalid credentials (401) - {response.text}"
                )

            # Handle server errors
            if response.status_code >= 500:
                raise HttpError(
                    f"Auto-login failed: Server error ({response.status_code}) - {response.text}"
                )

            # Handle other non-200 responses
            if response.status_code != 200:
                raise HttpError(
                    f"Auto-login failed: HTTP {response.status_code} - {response.text}"
                )

            # Parse response
            try:
                result = response.json()
            except Exception as e:
                raise HttpError(
                    f"Auto-login failed: Invalid JSON response: {str(e)}"
                ) from e

            # Validate response has required fields
            if "access_token" not in result:
                raise HttpError("Invalid login response: missing access_token")

            if "refresh_token" not in result:
                raise HttpError("Invalid login response: missing refresh_token")

            # Extract tokens
            access_token = result["access_token"]
            refresh_token = result["refresh_token"]

            # Log success to stderr (for debugging)
            # Only log first 20 chars of token for security
            print(f"Auto-login successful: {access_token[:20]}...", file=sys.stderr)

            return access_token, refresh_token

    except httpx.TimeoutException as e:
        raise HttpError(
            f"Auto-login failed: Request timeout after {timeout} seconds: {str(e)}"
        ) from e

    except httpx.ConnectError as e:
        raise HttpError(
            f"Auto-login failed: Connection error to {server_url}: {str(e)}"
        ) from e

    except httpx.NetworkError as e:
        raise HttpError(
            f"Auto-login failed: Network error connecting to {server_url}: {str(e)}"
        ) from e

    except httpx.HTTPError as e:
        # Catch any other httpx errors
        raise HttpError(f"Auto-login failed: HTTP error: {str(e)}") from e
