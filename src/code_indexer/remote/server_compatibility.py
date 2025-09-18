"""Server Compatibility Validator.

Comprehensive server compatibility validation for CIDX remote mode initialization.
Validates API version compatibility, server health, network connectivity, authentication,
and required endpoint availability.
"""

import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import httpx


logger = logging.getLogger(__name__)


@dataclass
class CompatibilityResult:
    """Result of comprehensive server compatibility validation."""

    compatible: bool
    issues: List[str]
    warnings: List[str]
    server_info: Dict[str, Any]
    recommendations: List[str]


class ServerCompatibilityValidator:
    """Comprehensive server compatibility validation."""

    REQUIRED_API_VERSION = "v1"
    COMPATIBLE_VERSIONS = ["v1", "v1.1", "v1.2"]
    REQUIRED_ENDPOINTS = [
        "/api/health",
        "/auth/login",
        "/api/repos/discover",
        "/api/user/info",
    ]

    def __init__(self, server_url: str):
        """Initialize server compatibility validator.

        Args:
            server_url: Base URL of the CIDX server
        """
        self.server_url = server_url.rstrip("/")
        self._session: Optional[httpx.AsyncClient] = None

    @property
    def session(self) -> httpx.AsyncClient:
        """Get or create HTTP session."""
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient(
                timeout=30.0,
                headers={"Content-Type": "application/json"},
                follow_redirects=True,
            )
        return self._session

    async def validate_compatibility(
        self, username: str, password: str
    ) -> CompatibilityResult:
        """Perform comprehensive server compatibility validation.

        Args:
            username: Username for authentication testing
            password: Password for authentication testing

        Returns:
            CompatibilityResult with validation details
        """
        try:
            issues: List[str] = []
            warnings: List[str] = []
            server_info: Dict[str, Any] = {}
            recommendations: List[str] = []

            # Step 1: Basic connectivity test
            connectivity_result = await self._test_connectivity()
            if not connectivity_result["success"]:
                issues.append(
                    f"Network connectivity failed: {connectivity_result['error']}"
                )
                if "recommendations" in connectivity_result:
                    recommendations.extend(connectivity_result["recommendations"])
                return CompatibilityResult(
                    compatible=False,
                    issues=issues,
                    warnings=warnings,
                    server_info=server_info,
                    recommendations=recommendations,
                )

            # Step 2: Server health check
            health_result = await self._check_server_health()
            if health_result["success"]:
                server_info.update(
                    {
                        "version": health_result.get("server_version", "unknown"),
                        "health": health_result.get("server_status", "unknown"),
                    }
                )
                if "available_services" in health_result:
                    server_info["services"] = health_result["available_services"]
            else:
                issues.append(f"Server health check failed: {health_result['error']}")
                if "recommendations" in health_result:
                    recommendations.extend(health_result["recommendations"])

            # Step 3: API version compatibility
            version_result = await self._check_api_version()
            if version_result["compatible"]:
                if "warning" in version_result and version_result["warning"]:
                    warnings.append(version_result["warning"])
                    if "recommendations" in version_result:
                        recommendations.extend(version_result["recommendations"])
            else:
                issues.append(version_result["error"])
                if "recommendations" in version_result:
                    recommendations.extend(version_result["recommendations"])
                return CompatibilityResult(
                    compatible=False,
                    issues=issues,
                    warnings=warnings,
                    server_info=server_info,
                    recommendations=recommendations,
                )

            # Step 4: Authentication system validation
            auth_result = await self._validate_authentication(username, password)
            if auth_result["success"]:
                server_info["auth_working"] = True
                if "username" in auth_result:
                    server_info["authenticated_user"] = auth_result["username"]
                if "permissions" in auth_result:
                    server_info["user_permissions"] = auth_result["permissions"]
            else:
                issues.append(
                    f"Authentication validation failed: {auth_result['error']}"
                )
                if "recommendations" in auth_result:
                    recommendations.extend(auth_result["recommendations"])
                return CompatibilityResult(
                    compatible=False,
                    issues=issues,
                    warnings=warnings,
                    server_info=server_info,
                    recommendations=recommendations,
                )

            # Step 5: Essential endpoint availability
            endpoints_result = await self._check_required_endpoints()
            if endpoints_result["success"]:
                server_info["endpoints_available"] = endpoints_result[
                    "available_endpoints"
                ]
                if "auth_required_endpoints" in endpoints_result:
                    server_info["auth_required"] = endpoints_result[
                        "auth_required_endpoints"
                    ]
            else:
                issues.append(
                    f"Required endpoints not available: {', '.join(endpoints_result['missing_endpoints'])}"
                )
                if "recommendations" in endpoints_result:
                    recommendations.extend(endpoints_result["recommendations"])
                return CompatibilityResult(
                    compatible=False,
                    issues=issues,
                    warnings=warnings,
                    server_info=server_info,
                    recommendations=recommendations,
                )

            # All checks passed
            return CompatibilityResult(
                compatible=True,
                issues=issues,
                warnings=warnings,
                server_info=server_info,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.exception("Unexpected error during compatibility validation")
            return CompatibilityResult(
                compatible=False,
                issues=[f"Unexpected validation error: {e}"],
                warnings=[],
                server_info={},
                recommendations=["Contact support with error details"],
            )
        finally:
            await self.close()

    async def _test_connectivity(self) -> Dict[str, Any]:
        """Test basic network connectivity to server.

        Returns:
            Dictionary with success status, error details, and recommendations
        """
        try:
            # Try to reach the server with a simple GET request
            await self.session.get(f"{self.server_url}/api/health")
            return {"success": True, "error": None}

        except httpx.NetworkError as e:
            error_msg = str(e)
            recommendations = ["Check network connectivity", "Verify server is running"]

            if "Connection refused" in error_msg:
                recommendations.append("Ensure server is accessible on specified port")
            elif "Name resolution" in error_msg:
                recommendations.append("Verify server hostname/IP address")

            return {
                "success": False,
                "error": f"Cannot connect to server: {error_msg}",
                "recommendations": recommendations,
            }

        except httpx.TimeoutException as e:
            recommendations = [
                "Check network latency and stability",
                "Verify firewall rules allow connection",
                "Check for proxy configuration issues",
            ]
            return {
                "success": False,
                "error": f"Connection timeout: {e}",
                "recommendations": recommendations,
            }

        except httpx.RequestError as e:
            error_msg = str(e)
            recommendations = ["Verify server URL format and protocol"]

            if "SSL certificate" in error_msg or "certificate" in error_msg.lower():
                recommendations = [
                    "Check SSL certificate validity",
                    "Verify certificate chain is complete",
                    "Consider using HTTP instead of HTTPS for testing",
                ]
                return {
                    "success": False,
                    "error": f"SSL certificate validation failed: {error_msg}",
                    "recommendations": recommendations,
                }

            return {
                "success": False,
                "error": f"Request error: {error_msg}",
                "recommendations": recommendations,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected connectivity error: {e}",
                "recommendations": ["Check server configuration and status"],
            }

    async def _check_server_health(self) -> Dict[str, Any]:
        """Check server health and basic operational status.

        Returns:
            Dictionary with health status, version info, and recommendations
        """
        try:
            response = await self.session.get(f"{self.server_url}/api/health")

            if response.status_code == 200:
                try:
                    health_data = response.json()
                    server_status = health_data.get("status", "unknown")
                    server_version = health_data.get("version", "unknown")

                    if server_status == "healthy":
                        return {
                            "success": True,
                            "server_status": server_status,
                            "server_version": server_version,
                            "available_services": health_data.get("services", []),
                        }
                    elif server_status == "degraded":
                        return {
                            "success": False,
                            "server_status": server_status,
                            "server_version": server_version,
                            "health_issues": health_data.get("issues", []),
                            "error": f"Server is in degraded state: {', '.join(health_data.get('issues', []))}",
                            "recommendations": [
                                "Contact server administrator",
                                "Wait for server issues to be resolved",
                            ],
                        }
                    else:
                        return {
                            "success": False,
                            "server_status": server_status,
                            "server_version": server_version,
                            "error": f"Server status is {server_status}",
                            "recommendations": ["Contact server administrator"],
                        }

                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "error": "Invalid JSON response from health endpoint",
                        "recommendations": ["Check server configuration"],
                    }

            elif response.status_code == 404:
                return {
                    "success": False,
                    "error": "Server health endpoint not available",
                    "recommendations": [
                        "Verify server version compatibility",
                        "Check if server is properly configured",
                    ],
                }

            else:
                return {
                    "success": False,
                    "error": f"Health endpoint returned status {response.status_code}",
                    "recommendations": ["Check server status and configuration"],
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Health check failed: {e}",
                "recommendations": ["Verify server is running and accessible"],
            }

    async def _check_api_version(self) -> Dict[str, Any]:
        """Validate API version compatibility.

        Returns:
            Dictionary with compatibility status and version details
        """
        try:
            response = await self.session.get(f"{self.server_url}/api/version")

            if response.status_code == 200:
                try:
                    version_data = response.json()
                    server_version = version_data.get("api_version", "unknown")

                    if server_version in self.COMPATIBLE_VERSIONS:
                        # Check if it's the optimal version
                        if server_version == self.COMPATIBLE_VERSIONS[-1]:
                            return {
                                "compatible": True,
                                "server_version": server_version,
                                "warning": None,
                            }
                        elif server_version == self.REQUIRED_API_VERSION:
                            # Required version is compatible but not optimal
                            return {
                                "compatible": True,
                                "server_version": server_version,
                                "warning": None,
                            }
                        else:
                            return {
                                "compatible": True,
                                "server_version": server_version,
                                "warning": f"Server is running older version {server_version}",
                                "recommendations": [
                                    "Consider upgrading server to latest version for optimal compatibility"
                                ],
                            }
                    else:
                        return {
                            "compatible": False,
                            "server_version": server_version,
                            "error": f"API version {server_version} is not compatible with client",
                            "recommendations": [
                                f"Upgrade client to support {server_version}",
                                f"Or downgrade server to compatible version: {', '.join(self.COMPATIBLE_VERSIONS)}",
                            ],
                        }

                except json.JSONDecodeError:
                    return {
                        "compatible": False,
                        "error": "Invalid JSON response from version endpoint",
                        "recommendations": ["Check server configuration"],
                    }

            elif response.status_code == 404:
                return {
                    "compatible": False,
                    "error": "API version endpoint not available",
                    "recommendations": [
                        "Server may be too old or incorrectly configured",
                        "Verify server supports version detection",
                    ],
                }

            else:
                return {
                    "compatible": False,
                    "error": f"Version endpoint returned status {response.status_code}",
                    "recommendations": ["Check server configuration"],
                }

        except Exception as e:
            return {
                "compatible": False,
                "error": f"Version check failed: {e}",
                "recommendations": ["Verify server supports API version detection"],
            }

    async def _validate_authentication(
        self, username: str, password: str
    ) -> Dict[str, Any]:
        """Validate authentication system functionality.

        Args:
            username: Username to test
            password: Password to test

        Returns:
            Dictionary with authentication validation results
        """
        try:
            # Direct authentication using correct /auth/login endpoint
            auth_payload = {
                "username": username,
                "password": password,
            }

            # Attempt authentication with direct endpoint call
            auth_response = await self.session.post(
                f"{self.server_url}/auth/login", json=auth_payload
            )

            if auth_response.status_code == 200:
                # Authentication successful
                try:
                    auth_data = auth_response.json()
                    token = auth_data.get("access_token") or auth_data.get("token")

                    # If we have a token, test the user info endpoint
                    if token:
                        headers = {"Authorization": f"Bearer {token}"}
                        try:
                            user_response = await self.session.get(
                                f"{self.server_url}/api/user/info", headers=headers
                            )

                            if user_response.status_code == 200:
                                user_info = user_response.json()
                                return {
                                    "success": True,
                                    "username": user_info.get("username", username),
                                    "permissions": user_info.get("permissions", []),
                                    "auth_working": True,
                                }
                            else:
                                # Auth worked but user info failed - still valid
                                return {
                                    "success": True,
                                    "username": username,
                                    "permissions": [],
                                    "auth_working": True,
                                }

                        except Exception as e:
                            # Auth worked but user info failed - still valid
                            logger.debug(
                                f"User info check failed but auth succeeded: {e}"
                            )
                            return {
                                "success": True,
                                "username": username,
                                "permissions": [],
                                "auth_working": True,
                            }
                    else:
                        # Authentication succeeded but no token - still valid
                        return {
                            "success": True,
                            "username": username,
                            "permissions": [],
                            "auth_working": True,
                        }

                except json.JSONDecodeError:
                    # Response not JSON but auth succeeded (status 200)
                    return {
                        "success": True,
                        "username": username,
                        "permissions": [],
                        "auth_working": True,
                    }

            elif auth_response.status_code == 401:
                # Authentication failed - invalid credentials
                return {
                    "success": False,
                    "error": "Invalid username or password",
                    "recommendations": [
                        "Check username and password",
                        "Verify account is not locked or disabled",
                    ],
                }

            else:
                # Other authentication errors
                return {
                    "success": False,
                    "error": f"Authentication failed with status {auth_response.status_code}",
                    "recommendations": [
                        "Contact server administrator",
                        "Check server authentication service status",
                    ],
                }

        except httpx.NetworkError as e:
            return {
                "success": False,
                "error": f"Network error during authentication: {e}",
                "recommendations": ["Check network connectivity", "Retry later"],
            }

        except httpx.TimeoutException as e:
            return {
                "success": False,
                "error": f"Authentication timeout: {e}",
                "recommendations": ["Check network connectivity", "Retry later"],
            }

        except httpx.RequestError as e:
            return {
                "success": False,
                "error": f"Request error during authentication: {e}",
                "recommendations": [
                    "Contact server administrator",
                    "Check server authentication service status",
                ],
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected authentication error: {e}",
                "recommendations": ["Contact support with error details"],
            }

    async def _check_required_endpoints(self) -> Dict[str, Any]:
        """Check availability of essential API endpoints.

        Returns:
            Dictionary with endpoint availability details
        """
        try:
            available_endpoints = []
            missing_endpoints = []
            auth_required_endpoints = []

            for endpoint in self.REQUIRED_ENDPOINTS:
                try:
                    response = await self.session.get(f"{self.server_url}{endpoint}")

                    if response.status_code == 200:
                        available_endpoints.append(endpoint)
                    elif response.status_code == 401:
                        # Authentication required but endpoint exists
                        available_endpoints.append(endpoint)
                        auth_required_endpoints.append(endpoint)
                    elif response.status_code == 404:
                        missing_endpoints.append(endpoint)
                    else:
                        # Assume available if it doesn't 404
                        available_endpoints.append(endpoint)

                except Exception as e:
                    logger.debug(f"Error checking endpoint {endpoint}: {e}")
                    missing_endpoints.append(endpoint)

            if len(missing_endpoints) == 0:
                return {
                    "success": True,
                    "available_endpoints": available_endpoints,
                    "missing_endpoints": missing_endpoints,
                    "auth_required_endpoints": auth_required_endpoints,
                }
            else:
                return {
                    "success": False,
                    "available_endpoints": available_endpoints,
                    "missing_endpoints": missing_endpoints,
                    "auth_required_endpoints": auth_required_endpoints,
                    "recommendations": [
                        "Contact server administrator about missing endpoints",
                        "Verify server has complete CIDX installation",
                        "Incomplete server setup detected - check configuration",
                    ],
                }

        except Exception as e:
            return {
                "success": False,
                "available_endpoints": [],
                "missing_endpoints": self.REQUIRED_ENDPOINTS,
                "error": f"Endpoint check failed: {e}",
                "recommendations": ["Verify server is accessible and configured"],
            }

    async def close(self) -> None:
        """Close HTTP session and clean up resources."""
        if self._session and not self._session.is_closed:
            await self._session.aclose()


def validate_remote_credentials(server_url: str, username: str, password: str) -> bool:
    """Validate remote credentials with server.

    Args:
        server_url: Server URL to validate against
        username: Username for authentication
        password: Password for authentication

    Returns:
        True if credentials are valid, False otherwise
    """
    import asyncio

    async def _async_validate():
        validator = ServerCompatibilityValidator(server_url)
        try:
            auth_result = await validator._validate_authentication(username, password)
            return auth_result.get("success", False)
        except Exception:
            return False
        finally:
            await validator.close()

    try:
        # Use asyncio.run() directly - simpler and more reliable
        result = asyncio.run(_async_validate())
        return bool(result)
    except Exception:
        return False
