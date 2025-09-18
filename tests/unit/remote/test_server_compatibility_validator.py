"""Tests for Server Compatibility Validator.

Following TDD principles - these tests define the expected behavior
for comprehensive server compatibility validation including API version
compatibility, server health verification, network connectivity validation,
and authentication system verification.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from code_indexer.api_clients.base_client import (
    AuthenticationError,
    APIClientError,
)


class TestCompatibilityResult:
    """Test CompatibilityResult dataclass structure and behavior."""

    def test_compatibility_result_structure(self):
        """Test that CompatibilityResult has correct structure."""
        # Import will fail until we implement it
        from code_indexer.remote.server_compatibility import CompatibilityResult

        result = CompatibilityResult(
            compatible=True,
            issues=[],
            warnings=["Minor version mismatch"],
            server_info={"version": "v1.1", "health": "ok"},
            recommendations=["Consider upgrading to latest version"],
        )

        assert result.compatible is True
        assert result.issues == []
        assert result.warnings == ["Minor version mismatch"]
        assert result.server_info == {"version": "v1.1", "health": "ok"}
        assert result.recommendations == ["Consider upgrading to latest version"]

    def test_compatibility_result_incompatible_case(self):
        """Test CompatibilityResult for incompatible server."""
        from code_indexer.remote.server_compatibility import CompatibilityResult

        result = CompatibilityResult(
            compatible=False,
            issues=["API version v2.0 is not compatible", "Server health check failed"],
            warnings=[],
            server_info={"version": "v2.0", "health": "degraded"},
            recommendations=[
                "Upgrade client to support v2.0",
                "Contact server administrator",
            ],
        )

        assert result.compatible is False
        assert len(result.issues) == 2
        assert "API version v2.0 is not compatible" in result.issues
        assert "Server health check failed" in result.issues
        assert result.warnings == []
        assert result.recommendations == [
            "Upgrade client to support v2.0",
            "Contact server administrator",
        ]


class TestServerCompatibilityValidator:
    """Test ServerCompatibilityValidator class and its methods."""

    def test_validator_constants(self):
        """Test ServerCompatibilityValidator has correct constants."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        assert ServerCompatibilityValidator.REQUIRED_API_VERSION == "v1"
        assert ServerCompatibilityValidator.COMPATIBLE_VERSIONS == [
            "v1",
            "v1.1",
            "v1.2",
        ]
        assert ServerCompatibilityValidator.REQUIRED_ENDPOINTS == [
            "/api/health",
            "/api/auth/login",
            "/api/repos/discover",
            "/api/user/info",
        ]

    def test_validator_initialization(self):
        """Test ServerCompatibilityValidator initialization."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        assert validator.server_url == "https://cidx.example.com"
        assert validator._session is None  # Session is created lazily
        assert validator.session is not None  # Property creates the session


class TestConnectivityValidation:
    """Test network connectivity validation methods."""

    @pytest.mark.asyncio
    async def test_connectivity_success(self):
        """Test successful connectivity validation."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_get.return_value = mock_response

            result = await validator._test_connectivity()

            assert result["success"] is True
            assert result["error"] is None
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_connectivity_network_error(self):
        """Test connectivity validation with network error."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.NetworkError("Connection refused")

            result = await validator._test_connectivity()

            assert result["success"] is False
            assert "Connection refused" in result["error"]
            assert any(
                "network connectivity" in rec.lower()
                for rec in result["recommendations"]
            )

    @pytest.mark.asyncio
    async def test_connectivity_timeout_error(self):
        """Test connectivity validation with timeout error."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Request timeout")

            result = await validator._test_connectivity()

            assert result["success"] is False
            assert "timeout" in result["error"].lower()
            assert any(
                "firewall" in rec.lower() or "proxy" in rec.lower()
                for rec in result["recommendations"]
            )

    @pytest.mark.asyncio
    async def test_connectivity_ssl_certificate_error(self):
        """Test connectivity validation with SSL certificate error."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.RequestError(
                "SSL certificate verification failed"
            )

            result = await validator._test_connectivity()

            assert result["success"] is False
            assert "SSL certificate" in result["error"]
            assert any(
                "certificate" in rec.lower() for rec in result["recommendations"]
            )


class TestServerHealthValidation:
    """Test server health check validation methods."""

    @pytest.mark.asyncio
    async def test_server_health_success(self):
        """Test successful server health check."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "healthy",
                "version": "v1.1",
                "uptime": "24h",
                "services": ["auth", "query", "discovery"],
            }
            mock_get.return_value = mock_response

            result = await validator._check_server_health()

            assert result["success"] is True
            assert result["server_version"] == "v1.1"
            assert result["server_status"] == "healthy"
            assert "auth" in result["available_services"]

    @pytest.mark.asyncio
    async def test_server_health_degraded_status(self):
        """Test server health check with degraded status."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "degraded",
                "version": "v1.1",
                "issues": ["High load", "Some services unavailable"],
            }
            mock_get.return_value = mock_response

            result = await validator._check_server_health()

            assert result["success"] is False
            assert result["server_status"] == "degraded"
            assert "High load" in result["health_issues"]
            assert any(
                "server administrator" in rec.lower()
                for rec in result["recommendations"]
            )

    @pytest.mark.asyncio
    async def test_server_health_endpoint_not_found(self):
        """Test server health check when endpoint is not found."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_get.return_value = mock_response

            result = await validator._check_server_health()

            assert result["success"] is False
            assert "health endpoint not available" in result["error"]
            assert any(
                "server version" in rec.lower() for rec in result["recommendations"]
            )


class TestAPIVersionValidation:
    """Test API version compatibility validation methods."""

    @pytest.mark.asyncio
    async def test_api_version_compatible(self):
        """Test API version validation with compatible version."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "api_version": "v1.2",  # Latest version, should have no warning
                "supported_versions": ["v1", "v1.1", "v1.2"],
            }
            mock_get.return_value = mock_response

            result = await validator._check_api_version()

            assert result["compatible"] is True
            assert result["server_version"] == "v1.2"
            assert result["warning"] is None

    @pytest.mark.asyncio
    async def test_api_version_compatible_with_warning(self):
        """Test API version validation with warning for non-optimal version."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "api_version": "v1.1",  # Compatible but older than latest (v1.2)
                "supported_versions": ["v1", "v1.1", "v1.2"],
            }
            mock_get.return_value = mock_response

            result = await validator._check_api_version()

            assert result["compatible"] is True
            assert result["server_version"] == "v1.1"
            assert "older version" in result["warning"]
            assert any(
                "consider upgrading" in rec.lower() for rec in result["recommendations"]
            )

    @pytest.mark.asyncio
    async def test_api_version_incompatible(self):
        """Test API version validation with incompatible version."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "api_version": "v2.0",  # Incompatible future version
                "supported_versions": ["v2.0", "v2.1"],
            }
            mock_get.return_value = mock_response

            result = await validator._check_api_version()

            assert result["compatible"] is False
            assert result["server_version"] == "v2.0"
            assert "API version v2.0 is not compatible" in result["error"]
            assert any(
                "upgrade client" in rec.lower() for rec in result["recommendations"]
            )

    @pytest.mark.asyncio
    async def test_api_version_endpoint_missing(self):
        """Test API version validation when version endpoint is missing."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_get.return_value = mock_response

            result = await validator._check_api_version()

            assert result["compatible"] is False
            assert "version endpoint not available" in result["error"]
            assert any(
                "server may be too old" in rec.lower()
                for rec in result["recommendations"]
            )


class TestAuthenticationValidation:
    """Test authentication system validation methods."""

    @pytest.mark.asyncio
    async def test_authentication_validation_success(self):
        """Test successful authentication validation."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch(
            "code_indexer.remote.server_compatibility.CIDXRemoteAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_client._authenticate.return_value = "valid.jwt.token"

            # Mock user info endpoint
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "username": "testuser",
                "permissions": ["read", "write"],
                "token_expiry": "1h",
            }
            mock_client._authenticated_request.return_value = mock_response

            result = await validator._validate_authentication("testuser", "testpass")

            assert result["success"] is True
            assert result["username"] == "testuser"
            assert "read" in result["permissions"]
            assert result["auth_working"] is True

    @pytest.mark.asyncio
    async def test_authentication_validation_invalid_credentials(self):
        """Test authentication validation with invalid credentials."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch(
            "code_indexer.remote.server_compatibility.CIDXRemoteAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_client._authenticate.side_effect = AuthenticationError(
                "Invalid credentials"
            )

            result = await validator._validate_authentication("baduser", "badpass")

            assert result["success"] is False
            assert "Invalid credentials" in result["error"]
            assert any(
                "check username and password" in rec.lower()
                for rec in result["recommendations"]
            )

    @pytest.mark.asyncio
    async def test_authentication_validation_server_error(self):
        """Test authentication validation with server error."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch(
            "code_indexer.remote.server_compatibility.CIDXRemoteAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_client._authenticate.side_effect = APIClientError(
                "Server error", status_code=500
            )

            result = await validator._validate_authentication("testuser", "testpass")

            assert result["success"] is False
            assert "Server error during authentication" in result["error"]
            assert any(
                "server administrator" in rec.lower()
                for rec in result["recommendations"]
            )


class TestRequiredEndpointsValidation:
    """Test required endpoints availability validation methods."""

    @pytest.mark.asyncio
    async def test_required_endpoints_all_available(self):
        """Test required endpoints validation when all are available."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch("httpx.AsyncClient.get") as mock_get:
            # All endpoints return 200
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await validator._check_required_endpoints()

            assert result["success"] is True
            assert len(result["available_endpoints"]) == 4
            assert len(result["missing_endpoints"]) == 0

    @pytest.mark.asyncio
    async def test_required_endpoints_some_missing(self):
        """Test required endpoints validation with some missing endpoints."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        def mock_get_side_effect(url, **kwargs):
            mock_response = MagicMock()
            if "/api/user/info" in url:
                mock_response.status_code = 404
            else:
                mock_response.status_code = 200
            return mock_response

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = mock_get_side_effect

            result = await validator._check_required_endpoints()

            assert result["success"] is False
            assert len(result["available_endpoints"]) == 3
            assert len(result["missing_endpoints"]) == 1
            assert "/api/user/info" in result["missing_endpoints"]
            assert any(
                "incomplete server setup" in rec.lower()
                for rec in result["recommendations"]
            )

    @pytest.mark.asyncio
    async def test_required_endpoints_authentication_required(self):
        """Test required endpoints validation with authentication requirements."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        def mock_get_side_effect(url, **kwargs):
            mock_response = MagicMock()
            if "/api/user/info" in url or "/api/repos/discover" in url:
                # These endpoints require authentication
                mock_response.status_code = 401
            else:
                mock_response.status_code = 200
            return mock_response

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = mock_get_side_effect

            result = await validator._check_required_endpoints()

            assert (
                result["success"] is True
            )  # 401 is expected for auth-required endpoints
            assert len(result["auth_required_endpoints"]) == 2
            assert "/api/user/info" in result["auth_required_endpoints"]
            assert "/api/repos/discover" in result["auth_required_endpoints"]


class TestComprehensiveCompatibilityValidation:
    """Test the main validate_compatibility method with comprehensive scenarios."""

    @pytest.mark.asyncio
    async def test_validate_compatibility_all_checks_pass(self):
        """Test comprehensive validation when all checks pass."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        # Mock all validation methods to return success
        with (
            patch.object(validator, "_test_connectivity") as mock_connectivity,
            patch.object(validator, "_check_server_health") as mock_health,
            patch.object(validator, "_check_api_version") as mock_version,
            patch.object(validator, "_validate_authentication") as mock_auth,
            patch.object(validator, "_check_required_endpoints") as mock_endpoints,
        ):
            mock_connectivity.return_value = {"success": True, "error": None}
            mock_health.return_value = {
                "success": True,
                "server_version": "v1.1",
                "server_status": "healthy",
            }
            mock_version.return_value = {
                "compatible": True,
                "server_version": "v1.1",
                "warning": None,
            }
            mock_auth.return_value = {
                "success": True,
                "username": "testuser",
                "permissions": ["read", "write"],
            }
            mock_endpoints.return_value = {
                "success": True,
                "available_endpoints": [
                    "/api/health",
                    "/api/auth/login",
                    "/api/repos/discover",
                    "/api/user/info",
                ],
                "missing_endpoints": [],
            }

            result = await validator.validate_compatibility("testuser", "testpass")

            assert result.compatible is True
            assert len(result.issues) == 0
            assert len(result.warnings) == 0
            assert result.server_info["version"] == "v1.1"
            assert result.server_info["health"] == "healthy"

    @pytest.mark.asyncio
    async def test_validate_compatibility_connectivity_failure(self):
        """Test comprehensive validation with connectivity failure."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with patch.object(validator, "_test_connectivity") as mock_connectivity:
            mock_connectivity.return_value = {
                "success": False,
                "error": "Connection refused",
                "recommendations": [
                    "Check network connectivity",
                    "Verify server is running",
                ],
            }

            result = await validator.validate_compatibility("testuser", "testpass")

            assert result.compatible is False
            assert len(result.issues) > 0
            assert "Connection refused" in result.issues[0]
            assert "Check network connectivity" in result.recommendations

    @pytest.mark.asyncio
    async def test_validate_compatibility_version_incompatible(self):
        """Test comprehensive validation with incompatible API version."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with (
            patch.object(validator, "_test_connectivity") as mock_connectivity,
            patch.object(validator, "_check_server_health") as mock_health,
            patch.object(validator, "_check_api_version") as mock_version,
        ):
            mock_connectivity.return_value = {"success": True, "error": None}
            mock_health.return_value = {
                "success": True,
                "server_version": "v2.0",
                "server_status": "healthy",
            }
            mock_version.return_value = {
                "compatible": False,
                "server_version": "v2.0",
                "error": "API version v2.0 is not compatible with client",
                "recommendations": ["Upgrade client to support v2.0"],
            }

            result = await validator.validate_compatibility("testuser", "testpass")

            assert result.compatible is False
            assert "API version v2.0 is not compatible" in result.issues[0]
            assert "Upgrade client" in result.recommendations[0]

    @pytest.mark.asyncio
    async def test_validate_compatibility_with_warnings(self):
        """Test comprehensive validation that succeeds with warnings."""
        from code_indexer.remote.server_compatibility import (
            ServerCompatibilityValidator,
        )

        validator = ServerCompatibilityValidator("https://cidx.example.com")

        with (
            patch.object(validator, "_test_connectivity") as mock_connectivity,
            patch.object(validator, "_check_server_health") as mock_health,
            patch.object(validator, "_check_api_version") as mock_version,
            patch.object(validator, "_validate_authentication") as mock_auth,
            patch.object(validator, "_check_required_endpoints") as mock_endpoints,
        ):
            mock_connectivity.return_value = {"success": True, "error": None}
            mock_health.return_value = {
                "success": True,
                "server_version": "v1.0",
                "server_status": "healthy",
            }
            mock_version.return_value = {
                "compatible": True,
                "server_version": "v1.0",
                "warning": "Server is running older version v1.0",
                "recommendations": ["Consider upgrading server to latest version"],
            }
            mock_auth.return_value = {
                "success": True,
                "username": "testuser",
                "permissions": ["read"],
            }
            mock_endpoints.return_value = {
                "success": True,
                "available_endpoints": [
                    "/api/health",
                    "/api/auth/login",
                    "/api/repos/discover",
                    "/api/user/info",
                ],
                "missing_endpoints": [],
            }

            result = await validator.validate_compatibility("testuser", "testpass")

            assert result.compatible is True
            assert len(result.issues) == 0
            assert len(result.warnings) == 1
            assert "older version v1.0" in result.warnings[0]
            assert "Consider upgrading" in result.recommendations[0]


class TestIntegrationWithRemoteInitialization:
    """Test integration of compatibility validation with remote initialization."""

    @pytest.mark.asyncio
    async def test_remote_initialization_with_compatibility_check_success(self):
        """Test remote initialization includes compatibility validation and succeeds."""
        from code_indexer.remote.initialization import (
            initialize_remote_mode_with_validation,
        )
        from rich.console import Console
        import io
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            console_output = io.StringIO()
            test_console = Console(file=console_output, width=80, legacy_windows=False)

            with (
                patch(
                    "code_indexer.remote.initialization.ServerCompatibilityValidator"
                ) as mock_validator_class,
                patch(
                    "code_indexer.remote.initialization.validate_and_normalize_server_url"
                ) as mock_url_validate,
                patch(
                    "code_indexer.remote.initialization.create_remote_configuration"
                ) as mock_create_config,
                patch(
                    "code_indexer.remote.initialization.RemoteConfig"
                ) as mock_remote_config_class,
            ):
                # Mock successful compatibility validation
                mock_validator = AsyncMock()
                mock_validator_class.return_value = mock_validator

                from code_indexer.remote.server_compatibility import CompatibilityResult

                mock_validator.validate_compatibility.return_value = (
                    CompatibilityResult(
                        compatible=True,
                        issues=[],
                        warnings=["Minor version mismatch"],
                        server_info={"version": "v1.1", "health": "healthy"},
                        recommendations=[],
                    )
                )

                mock_url_validate.return_value = "https://cidx.example.com"
                mock_create_config.return_value = None

                # Mock RemoteConfig
                mock_remote_config = MagicMock()
                mock_remote_config_class.return_value = mock_remote_config
                mock_remote_config.store_credentials.return_value = None

                # Should complete successfully
                await initialize_remote_mode_with_validation(
                    project_root=test_dir,
                    server_url="https://cidx.example.com",
                    username="testuser",
                    password="testpass123",
                    console=test_console,
                )

                # Verify compatibility validation was called
                mock_validator.validate_compatibility.assert_called_once_with(
                    "testuser", "testpass123"
                )

                # Verify configuration was created after validation
                mock_create_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_remote_initialization_with_compatibility_check_failure(self):
        """Test remote initialization fails when compatibility check fails."""
        from code_indexer.remote.initialization import (
            initialize_remote_mode_with_validation,
        )
        from code_indexer.remote.exceptions import RemoteInitializationError
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            with (
                patch(
                    "code_indexer.remote.initialization.ServerCompatibilityValidator"
                ) as mock_validator_class,
                patch(
                    "code_indexer.remote.initialization.validate_and_normalize_server_url"
                ) as mock_url_validate,
            ):
                # Mock failed compatibility validation
                mock_validator = AsyncMock()
                mock_validator_class.return_value = mock_validator

                from code_indexer.remote.server_compatibility import CompatibilityResult

                mock_validator.validate_compatibility.return_value = (
                    CompatibilityResult(
                        compatible=False,
                        issues=[
                            "API version v2.0 is not compatible",
                            "Server health check failed",
                        ],
                        warnings=[],
                        server_info={"version": "v2.0", "health": "degraded"},
                        recommendations=[
                            "Upgrade client to support v2.0",
                            "Contact server administrator",
                        ],
                    )
                )

                mock_url_validate.return_value = "https://cidx.example.com"

                # Should fail with detailed compatibility error
                with pytest.raises(RemoteInitializationError) as exc_info:
                    await initialize_remote_mode_with_validation(
                        project_root=test_dir,
                        server_url="https://cidx.example.com",
                        username="testuser",
                        password="testpass123",
                    )

                error_message = str(exc_info.value)
                assert "Server compatibility validation failed" in error_message
                assert "API version v2.0 is not compatible" in error_message
                assert "Server health check failed" in error_message
                assert "Upgrade client to support v2.0" in error_message
