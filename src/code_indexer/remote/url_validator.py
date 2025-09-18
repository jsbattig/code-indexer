"""URL validation and normalization for remote servers."""

from urllib.parse import urlparse, urlunparse
from typing import Optional

from .exceptions import URLValidationError


def validate_and_normalize_server_url(server_url: Optional[str]) -> str:
    """Validate and normalize a server URL for remote connections.

    Args:
        server_url: The server URL to validate and normalize

    Returns:
        str: The normalized URL

    Raises:
        URLValidationError: If the URL is invalid or unsupported
    """
    if not server_url:
        raise URLValidationError("Server URL cannot be empty or None")

    server_url = server_url.strip()
    if not server_url:
        raise URLValidationError("Server URL cannot be empty")

    # First parse to check if there's already a protocol
    initial_parsed = urlparse(server_url)

    # If no scheme, add https://
    # BUT: urlparse treats "domain:port" as "scheme:path", so check for this case
    if not initial_parsed.scheme or (
        initial_parsed.scheme and not initial_parsed.netloc and ":" in server_url
    ):
        server_url = f"https://{server_url}"

    try:
        parsed = urlparse(server_url)
    except Exception as e:
        raise URLValidationError(f"Invalid URL format: {server_url}", str(e))

    # Validate that it's actually a valid URL structure
    if not parsed.netloc:
        raise URLValidationError(f"Invalid URL format: {server_url}")

    # Only allow HTTP and HTTPS protocols
    if parsed.scheme not in ("http", "https"):
        raise URLValidationError(
            f"Unsupported protocol '{parsed.scheme}'. Only HTTP and HTTPS are supported"
        )

    # Basic validation for malformed URLs - check if netloc looks reasonable
    if not parsed.netloc or "://" in parsed.netloc or parsed.netloc.startswith("."):
        raise URLValidationError(f"Invalid URL format: {server_url}")

    # Additional validation: netloc should have at least a domain-like structure
    # Simple check: should contain at least one dot or be "localhost" (with or without port)
    netloc_host = parsed.netloc.split(":")[0]  # Extract hostname from netloc:port
    if netloc_host != "localhost" and "." not in netloc_host:
        raise URLValidationError(f"Invalid URL format: {server_url}")

    # Remove trailing slashes from path
    path = parsed.path.rstrip("/")

    # Reconstruct the normalized URL
    normalized = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )

    return normalized
