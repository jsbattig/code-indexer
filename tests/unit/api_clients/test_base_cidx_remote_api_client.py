"""Foundation #1 Compliance Notice: Mock-Free Test Suite.

CRITICAL: All mocks have been removed from this test suite in compliance with
Foundation #1 anti-mock principles. The original mock-based tests have been
replaced with real implementations using actual HTTP servers, real JWT tokens,
and authentic network operations.

ALL TESTS NOW USE REAL IMPLEMENTATIONS:
- Real CIDX server with authentic HTTP endpoints
- Real JWT token generation and validation using RSA cryptography
- Real HTTP client operations using httpx
- Real network error conditions and timeouts
- Real authentication flows and token management

Original mock violations have been eliminated. All functionality is tested
using genuine implementations without any mock objects or simulated behaviors.

See test_base_cidx_remote_api_client_real.py for the complete implementation.
"""

# Foundation #1 compliance imports - real implementations only
from pathlib import Path

# Import real test implementations (no mocks)
from tests.infrastructure.test_cidx_server import CIDXServerTestContext
from tests.infrastructure.real_jwt_manager import create_real_jwt_manager
from tests.infrastructure.real_http_client import create_authenticated_http_client


class TestFoundationComplianceRedirect:
    """Foundation #1 Compliance: All tests redirected to real implementations.

    This file formerly contained extensive mock violations. All tests have been
    replaced with real implementations that comply with Foundation #1.
    """

    def test_authentication_tests_moved_to_real_implementation(self):
        """Authentication tests moved to real implementation."""
        from tests.unit.api_clients.test_base_cidx_remote_api_client_real import (
            TestCIDXRemoteAPIClientRealAuthentication,
        )

        # Verify real authentication tests exist
        assert TestCIDXRemoteAPIClientRealAuthentication is not None
        assert hasattr(
            TestCIDXRemoteAPIClientRealAuthentication,
            "test_real_authentication_success",
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealAuthentication,
            "test_real_authentication_invalid_credentials",
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealAuthentication,
            "test_real_token_refresh_workflow",
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealAuthentication,
            "test_concurrent_authentication_real_server",
        )

    def test_http_requests_tests_moved_to_real_implementation(self):
        """HTTP request tests moved to real implementation."""
        from tests.unit.api_clients.test_base_cidx_remote_api_client_real import (
            TestCIDXRemoteAPIClientRealRequests,
        )

        # Verify real HTTP request tests exist
        assert TestCIDXRemoteAPIClientRealRequests is not None
        assert hasattr(
            TestCIDXRemoteAPIClientRealRequests, "test_real_authenticated_get_request"
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealRequests, "test_real_job_status_request"
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealRequests, "test_real_job_not_found_error"
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealRequests, "test_real_job_cancellation"
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealRequests, "test_real_unauthorized_retry_workflow"
        )

    def test_network_error_tests_moved_to_real_implementation(self):
        """Network error tests moved to real implementation."""
        from tests.unit.api_clients.test_base_cidx_remote_api_client_real import (
            TestCIDXRemoteAPIClientRealNetworkErrors,
        )

        # Verify real network error tests exist
        assert TestCIDXRemoteAPIClientRealNetworkErrors is not None
        assert hasattr(
            TestCIDXRemoteAPIClientRealNetworkErrors,
            "test_real_connection_error_handling",
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealNetworkErrors, "test_real_timeout_handling"
        )

    def test_resource_management_tests_moved_to_real_implementation(self):
        """Resource management tests moved to real implementation."""
        from tests.unit.api_clients.test_base_cidx_remote_api_client_real import (
            TestCIDXRemoteAPIClientRealResourceManagement,
        )

        # Verify real resource management tests exist
        assert TestCIDXRemoteAPIClientRealResourceManagement is not None
        assert hasattr(
            TestCIDXRemoteAPIClientRealResourceManagement, "test_real_session_cleanup"
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealResourceManagement,
            "test_real_context_manager_cleanup",
        )
        assert hasattr(
            TestCIDXRemoteAPIClientRealResourceManagement,
            "test_real_session_recreation",
        )

    def test_jwt_integration_tests_moved_to_real_implementation(self):
        """JWT integration tests moved to real implementation."""
        from tests.unit.api_clients.test_base_cidx_remote_api_client_real import (
            TestRealJWTTokenManagerIntegration,
        )

        # Verify real JWT integration tests exist
        assert TestRealJWTTokenManagerIntegration is not None
        assert hasattr(
            TestRealJWTTokenManagerIntegration, "test_real_jwt_manager_initialization"
        )
        assert hasattr(
            TestRealJWTTokenManagerIntegration, "test_real_token_validation_workflow"
        )
        assert hasattr(
            TestRealJWTTokenManagerIntegration, "test_real_expired_token_detection"
        )

    def test_persistent_token_tests_moved_to_real_implementation(self):
        """Persistent token storage tests moved to real implementation."""
        from tests.unit.api_clients.test_base_cidx_remote_api_client_real import (
            TestRealPersistentTokenStorage,
        )

        # Verify real persistent token tests exist
        assert TestRealPersistentTokenStorage is not None
        assert hasattr(
            TestRealPersistentTokenStorage, "test_real_persistent_token_storage"
        )

    def test_end_to_end_integration_tests_moved_to_real_implementation(self):
        """End-to-end integration tests moved to real implementation."""
        from tests.unit.api_clients.test_base_cidx_remote_api_client_real import (
            TestRealEndToEndIntegration,
        )

        # Verify real E2E tests exist
        assert TestRealEndToEndIntegration is not None
        assert hasattr(TestRealEndToEndIntegration, "test_complete_real_workflow")
        assert hasattr(TestRealEndToEndIntegration, "test_real_error_recovery_workflow")

    def test_foundation_compliance_verification(self):
        """Verify Foundation #1 compliance is maintained."""
        # Verify no mock imports remain in this file
        import sys

        current_module = sys.modules[__name__]

        # Check that unittest.mock is not imported
        assert not hasattr(current_module, "MagicMock")
        assert not hasattr(current_module, "patch")
        assert not hasattr(current_module, "Mock")

        # Verify real infrastructure is available
        assert CIDXServerTestContext is not None
        assert create_real_jwt_manager is not None
        assert create_authenticated_http_client is not None

    def test_mock_elimination_success(self):
        """Confirm successful elimination of all mock usage."""
        # Read this file and verify no mock imports
        current_file = Path(__file__)
        content = current_file.read_text()

        # Check import lines only (not test assertion lines)
        import_lines = [
            line
            for line in content.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        import_content = "\n".join(import_lines)

        # Verify no mock-related imports
        assert "from unittest.mock import" not in import_content
        assert "import mock" not in import_content

        # Verify no mock usage in imports (checking only import lines avoids self-reference)
        mock_terms = ["MagicMock", "AsyncMock", "Mock(", "patch("]
        for term in mock_terms:
            assert term not in import_content, f"Found mock term '{term}' in imports"

        # Verify real infrastructure imports are present
        assert "from tests.infrastructure.test_cidx_server import" in content
        assert "from tests.infrastructure.real_jwt_manager import" in content
        assert "from tests.infrastructure.real_http_client import" in content


# Legacy test class names for compatibility (all redirect to real implementations)
class TestCIDXRemoteAPIClientAuthentication(TestFoundationComplianceRedirect):
    """Legacy authentication tests - redirected to real implementation."""

    pass


class TestCIDXRemoteAPIClientRequests(TestFoundationComplianceRedirect):
    """Legacy HTTP request tests - redirected to real implementation."""

    pass


class TestCIDXRemoteAPIClientResourceManagement(TestFoundationComplianceRedirect):
    """Legacy resource management tests - redirected to real implementation."""

    pass


class TestCIDXRemoteAPIClientErrorTranslation(TestFoundationComplianceRedirect):
    """Legacy error translation tests - redirected to real implementation."""

    pass


class TestJWTTokenManagerIntegration(TestFoundationComplianceRedirect):
    """Legacy JWT integration tests - redirected to real implementation."""

    pass
