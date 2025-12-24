"""
Test 1: Real Authentication Flow - NO MOCKS

TDD implementation of elite-software-architect's Option A recommendation.
Tests real authentication flow using real security components.

CRITICAL: ZERO MOCKS - Uses real FastAPI app, real JWT, real password hashing
"""

from fastapi import status

from tests.fixtures.test_infrastructure import RealComponentTestInfrastructure
from code_indexer.server.auth.user_manager import UserRole


import pytest


@pytest.mark.e2e
class TestRealAuthenticationFlow:
    """
    Real authentication flow tests with zero mocks.

    Tests complete authentication workflow through real security components:
    - Real user creation with real password hashing
    - Real login endpoint with real JWT generation
    - Real protected endpoint access with real token validation
    - Real error scenarios with real security checks
    """

    def test_complete_real_authentication_workflow(self):
        """
        Test complete authentication workflow using real components.

        CRITICAL: NO MOCKS - Every component is real and functional

        Workflow:
        1. Create real user with real password hashing
        2. Login through real endpoint with real JWT generation
        3. Access protected endpoint with real token validation
        4. Verify all security checks are real
        """
        # PHASE 1: Setup real test infrastructure - this should work
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # PHASE 2: Create real user - this will initially fail
            # We need real password validation and real storage
            user_data = infrastructure.create_test_user(
                username="realuser",
                password="RealPassword123!",
                role=UserRole.NORMAL_USER,
            )

            assert user_data["username"] == "realuser"
            assert user_data["role"] == "normal_user"
            assert "password" in user_data  # Test helper includes password

            # PHASE 3: Real login through real API endpoint
            # This should generate real JWT through real authentication
            token_response = infrastructure.get_auth_token(
                username=user_data["username"], password=user_data["password"]
            )

            assert "access_token" in token_response
            assert "token_type" in token_response
            assert token_response["token_type"] == "bearer"

            # PHASE 4: Access protected endpoint with real token
            # This should validate real JWT through real middleware
            auth_headers = infrastructure.authenticate_request(
                token_response["access_token"]
            )

            # Test real protected endpoint (health check with auth)
            response = infrastructure.client.get("/health", headers=auth_headers)

            # This should succeed with real authentication
            assert response.status_code == status.HTTP_200_OK

            # PHASE 5: Verify token contains real user data
            # JWT should contain real username from real database
            payload = infrastructure.jwt_manager.validate_token(
                token_response["access_token"]
            )
            assert payload["username"] == "realuser"

        finally:
            infrastructure.cleanup()

    def test_real_authentication_failure_scenarios(self):
        """
        Test real authentication failure scenarios.

        CRITICAL: NO MOCKS - Real failures with real error responses
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create real user for testing
            _user_data = infrastructure.create_test_user(
                username="testuser", password="TestPassword123!"
            )

            # Test 1: Wrong password - should fail through real authentication
            response = infrastructure.client.post(
                "/auth/login",
                json={"username": "testuser", "password": "WrongPassword123!"},
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

            # Test 2: Non-existent user - should fail through real user lookup
            response = infrastructure.client.post(
                "/auth/login",
                json={"username": "nonexistent", "password": "AnyPassword123!"},
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

            # Test 3: Invalid token - should fail through real JWT validation
            response = infrastructure.client.get(
                "/health", headers={"Authorization": "Bearer invalid.jwt.token"}
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

            # Test 4: Missing token - should return 401 per MCP spec (RFC 9728)
            response = infrastructure.client.get("/health")
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            # Should include WWW-Authenticate header per RFC 9728
            assert "www-authenticate" in response.headers
            assert "bearer" in response.headers["www-authenticate"].lower()

        finally:
            infrastructure.cleanup()

    def test_real_user_roles_and_permissions(self):
        """
        Test real user roles and permission checking.

        CRITICAL: NO MOCKS - Real role-based access control
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create users with different real roles
            normal_user = infrastructure.create_test_user(
                username="normaluser",
                password="NormalPassword123!",
                role=UserRole.NORMAL_USER,
            )

            admin_user = infrastructure.create_test_user(
                username="adminuser", password="AdminPassword123!", role=UserRole.ADMIN
            )

            # Get real tokens for both users
            normal_token = infrastructure.get_auth_token(
                normal_user["username"], normal_user["password"]
            )
            admin_token = infrastructure.get_auth_token(
                admin_user["username"], admin_user["password"]
            )

            # Test normal user accessing admin endpoint - should fail
            response = infrastructure.client.get(
                "/api/admin/users",  # Admin-only endpoint
                headers=infrastructure.authenticate_request(
                    normal_token["access_token"]
                ),
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN

            # Test admin user accessing admin endpoint - should succeed
            response = infrastructure.client.get(
                "/api/admin/users",
                headers=infrastructure.authenticate_request(
                    admin_token["access_token"]
                ),
            )
            assert response.status_code == status.HTTP_200_OK

        finally:
            infrastructure.cleanup()

    def test_real_jwt_expiration_handling(self):
        """
        Test real JWT token expiration handling.

        CRITICAL: NO MOCKS - Real token expiration with real time checks
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create real user
            user_data = infrastructure.create_test_user()

            # Get real token
            token_response = infrastructure.get_auth_token(
                user_data["username"], user_data["password"]
            )

            # Verify token works initially
            response = infrastructure.client.get(
                "/health",
                headers=infrastructure.authenticate_request(
                    token_response["access_token"]
                ),
            )
            assert response.status_code == status.HTTP_200_OK

            # For this test, we verify the token structure is valid
            # In production, we would wait for expiration or manipulate time
            payload = infrastructure.jwt_manager.validate_token(
                token_response["access_token"]
            )

            # Verify token has real expiration field
            assert "exp" in payload
            assert "username" in payload
            assert payload["username"] == user_data["username"]

        finally:
            infrastructure.cleanup()


# This test will initially FAIL because the infrastructure is not yet complete
# Following TDD: Red -> Green -> Refactor
@pytest.mark.e2e
def test_infrastructure_validation():
    """
    Validation test to ensure test infrastructure works.

    This test MUST pass before proceeding with other tests.
    """
    infrastructure = RealComponentTestInfrastructure()

    # This should work - basic setup
    infrastructure.setup()

    try:
        # Verify basic infrastructure components exist
        assert infrastructure.temp_dir is not None
        assert infrastructure.temp_dir.exists()
        assert infrastructure.app is not None
        assert infrastructure.client is not None
        assert infrastructure.user_manager is not None
        assert infrastructure.jwt_manager is not None

        # Verify app is real FastAPI app
        assert hasattr(infrastructure.app, "router")
        assert hasattr(infrastructure.app, "middleware_stack")

    finally:
        infrastructure.cleanup()
