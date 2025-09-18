"""Server connectivity testing for remote servers."""

import httpx

from .exceptions import ServerConnectivityError


async def test_server_connectivity(server_url: str, timeout: float = 10.0) -> None:
    """Test basic connectivity to a remote CIDX server.

    Args:
        server_url: The server URL to test connectivity to
        timeout: Timeout in seconds for the connection test

    Raises:
        ServerConnectivityError: If the server cannot be reached or returns an error
    """
    if not server_url:
        raise ServerConnectivityError("Server URL cannot be empty")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try to reach a basic health endpoint or root
            # Most servers will respond to GET / even if they don't have a health endpoint
            response = await client.get(server_url)

            # Accept any response that indicates the server is reachable
            # Even 404 is fine - it means the server is responding
            if response.status_code >= 500:
                raise ServerConnectivityError(
                    f"Server returned unexpected status: {response.status_code}",
                    details=(
                        response.text[:200] if response.text else "No response body"
                    ),
                )

    except httpx.NetworkError as e:
        raise ServerConnectivityError("Cannot connect to server", details=str(e))
    except httpx.TimeoutException as e:
        raise ServerConnectivityError("Cannot connect to server", details=str(e))
    except Exception as e:
        raise ServerConnectivityError(
            "Unexpected error during connectivity test", details=str(e)
        )
