"""
Integration tests for authentication endpoint security measures.

Tests the real authentication endpoints with standardized error responses,
timing attack prevention, and information leakage prevention.

Following CLAUDE.md Foundation #1: NO MOCKS - Real authentication testing.
"""

import pytest
import time
import json
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
from datetime import datetime, timezone

from code_indexer.server.app import create_app

# UserManager imports removed - using app-level user manager
from code_indexer.server.auth.password_manager import PasswordManager


class TestAuthenticationEndpointSecurity:
    """Integration tests for authentication security measures."""

    @pytest.fixture
    def temp_users_file(self):
        """Create temporary users file for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        users_file = temp_dir / "users.json"

        # Create test user data
        password_manager = PasswordManager()
        test_users = {
            "alice": {
                "username": "alice",
                "password_hash": password_manager.hash_password("correct_password"),
                "role": "normal_user",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            "locked_user": {
                "username": "locked_user",
                "password_hash": password_manager.hash_password("password123"),
                "role": "normal_user",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "account_locked": True,
                "failed_attempts": 5,
            },
        }

        users_file.write_text(json.dumps(test_users, indent=2))

        yield str(users_file)

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def client(self, temp_users_file):
        """Create FastAPI test client with real user manager."""
        app = create_app()

        # Override user manager to use test file
        from code_indexer.server.app import user_manager

        user_manager.users_file_path = temp_users_file
        user_manager._load_users()  # Reload users from test file

        return TestClient(app)

    def test_login_with_nonexistent_username_generic_response(self, client):
        """
        Scenario 1: Login with invalid username returns generic error message.

        ACCEPTANCE CRITERIA:
        - Response status should be 401 Unauthorized
        - Response should contain generic message "Invalid credentials"
        - Response time should be ~100ms (same as valid username)
        - No information about user existence should be revealed
        """
        start_time = time.time()

        response = client.post(
            "/auth/login",
            json={"username": "nonexistent_user", "password": "any_password"},
        )

        elapsed_time = time.time() - start_time

        # Security assertions
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

        # Timing attack prevention - should take minimum response time
        assert elapsed_time >= 0.09, f"Response too fast: {elapsed_time}s"
        assert elapsed_time <= 0.5, f"Response too slow: {elapsed_time}s"

        # Should not reveal user existence information
        response_text = response.text.lower()
        assert "not found" not in response_text
        assert "does not exist" not in response_text
        assert "nonexistent" not in response_text

    def test_login_with_valid_username_wrong_password_generic_response(self, client):
        """
        Scenario 2: Login with valid username but wrong password returns generic error.

        ACCEPTANCE CRITERIA:
        - Response status should be 401 Unauthorized
        - Response should contain identical generic message
        - Response time should be ~100ms (constant time)
        """
        start_time = time.time()

        response = client.post(
            "/auth/login", json={"username": "alice", "password": "wrong_password"}
        )

        elapsed_time = time.time() - start_time

        # Security assertions
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

        # Timing consistency
        assert elapsed_time >= 0.09, f"Response too fast: {elapsed_time}s"
        assert elapsed_time <= 0.5, f"Response too slow: {elapsed_time}s"

    # TODO: Implement account locking functionality
    # def test_login_with_locked_account_generic_response(self, client):
    #     """
    #     Scenario 3: Login with locked account returns generic error.
    #
    #     ACCEPTANCE CRITERIA:
    #     - Response status should be 401 Unauthorized
    #     - Response should contain generic message "Invalid credentials"
    #     - Detailed lock reason should only be in secure logs
    #     """
    #     start_time = time.time()
    #
    #     response = client.post(
    #         "/auth/login",
    #         json={"username": "locked_user", "password": "password123"}
    #     )
    #
    #     elapsed_time = time.time() - start_time
    #
    #     # Security assertions
    #     assert response.status_code == 401
    #     assert response.json()["detail"] == "Invalid credentials"
    #
    #     # Should not reveal account lock information
    #     response_text = response.text.lower()
    #     assert "locked" not in response_text
    #     assert "disabled" not in response_text
    #     assert "attempts" not in response_text
    #
    #     # Timing consistency
    #     assert elapsed_time >= 0.09, f"Response too fast: {elapsed_time}s"

    def test_timing_attack_prevention_across_different_scenarios(self, client):
        """Test that all authentication failure scenarios take similar time."""
        test_scenarios = [
            # Nonexistent user
            {"username": "nonexistent", "password": "any_password"},
            # Valid user, wrong password
            {"username": "alice", "password": "wrong_password"},
            # Another nonexistent user scenario
            {"username": "another_fake_user", "password": "different_password"},
        ]

        response_times = []

        for scenario in test_scenarios:
            start_time = time.time()

            response = client.post("/auth/login", json=scenario)

            elapsed_time = time.time() - start_time
            response_times.append(elapsed_time)

            # All should return 401 with generic message
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid credentials"

        # Timing consistency check
        min_time = min(response_times)
        max_time = max(response_times)
        time_variance = max_time - min_time

        # Response times should be consistent (within 300ms variance for integration testing)
        # Note: This is more lenient than production requirements due to test environment variability
        assert time_variance < 0.3, f"Time variance too high: {time_variance}s"

        # All responses should take at least minimum time
        for response_time in response_times:
            assert response_time >= 0.09, f"Response too fast: {response_time}s"

    def test_successful_login_does_not_leak_timing_info(self, client):
        """Test that successful logins also maintain timing consistency."""
        # Successful login timing
        start_time = time.time()

        response = client.post(
            "/auth/login", json={"username": "alice", "password": "correct_password"}
        )

        success_time = time.time() - start_time

        # Failed login timing
        start_time = time.time()

        failed_response = client.post(
            "/auth/login", json={"username": "alice", "password": "wrong_password"}
        )

        failed_time = time.time() - start_time

        # Verify responses
        assert response.status_code == 200  # Success
        assert failed_response.status_code == 401  # Failure

        # Timing should be similar (within 200ms for integration test tolerance)
        # Note: Successful login has additional JWT creation overhead
        time_difference = abs(success_time - failed_time)
        assert time_difference < 0.2, f"Timing difference too high: {time_difference}s"

    def test_login_response_headers_security(self, client):
        """Test that login responses don't leak sensitive information in headers."""
        response = client.post(
            "/auth/login", json={"username": "nonexistent", "password": "test"}
        )

        # Check headers don't leak info
        headers = response.headers

        # Should not contain debugging information
        assert "X-Debug" not in headers
        assert "X-User-Status" not in headers
        assert "X-Auth-Reason" not in headers

        # Should contain proper WWW-Authenticate header for 401 responses
        assert response.status_code == 401
        assert "WWW-Authenticate" in headers

    def test_multiple_failed_attempts_rate_limiting_behavior(self, client):
        """Test that rate limiting maintains security response patterns."""
        # Perform multiple failed attempts
        for i in range(3):
            response = client.post(
                "/auth/login", json={"username": "alice", "password": "wrong_password"}
            )

            # Even with rate limiting, should maintain generic responses
            assert response.status_code in [
                401,
                429,
            ]  # Either auth failure or rate limit

            if response.status_code == 429:
                # Rate limit response should not leak user info
                assert "alice" not in response.text.lower()
            else:
                # Auth failure should be generic
                assert response.json()["detail"] == "Invalid credentials"


class TestRegistrationEndpointSecurity:
    """Test registration endpoint security (if implemented)."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app()
        return TestClient(app)

    def test_registration_with_existing_email_generic_response(self, client):
        """
        Scenario 4: Registration with existing email returns generic success message.

        ACCEPTANCE CRITERIA:
        - Response status should be 200 OK
        - Response should indicate "Registration initiated"
        - No immediate indication of existing account should be given
        """
        # This test will initially fail as registration endpoint may not exist
        # This drives the implementation of the registration endpoint

        response = client.post(
            "/auth/register",
            json={
                "email": "existing@example.com",
                "password": "NewPassword123!",  # Meets complexity requirements
                "username": "newuser",
            },
        )

        # Should return success regardless of account existence
        assert response.status_code == 200
        assert "Registration initiated" in response.json()["message"]

        # Should not indicate account already exists
        response_text = response.text.lower()
        assert "already exists" not in response_text
        assert "duplicate" not in response_text

    def test_registration_timing_consistency(self, client):
        """Test registration timing is consistent for new vs existing accounts."""
        new_account_data = {
            "email": "new_user@example.com",
            "password": "NewPassword123!",  # Meets complexity requirements
            "username": "newuser",
        }

        existing_account_data = {
            "email": "existing@example.com",
            "password": "NewPassword123!",
            "username": "existinguser",
        }

        # Time new account registration
        start_time = time.time()
        new_response = client.post("/auth/register", json=new_account_data)
        new_account_time = time.time() - start_time

        # Time existing account registration
        start_time = time.time()
        existing_response = client.post("/auth/register", json=existing_account_data)
        existing_account_time = time.time() - start_time

        # Both should return 200 with generic message
        assert new_response.status_code == 200
        assert existing_response.status_code == 200

        # Timing should be similar
        time_difference = abs(new_account_time - existing_account_time)
        assert (
            time_difference < 0.1
        ), f"Registration timing variance too high: {time_difference}s"


class TestPasswordResetEndpointSecurity:
    """Test password reset endpoint security (if implemented)."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app()
        return TestClient(app)

    def test_password_reset_nonexistent_email_generic_response(self, client):
        """
        Scenario 5: Password reset for non-existent email returns generic success.

        ACCEPTANCE CRITERIA:
        - Response status should be 200 OK
        - Response should indicate "Password reset email sent if account exists"
        - Response time should match existing email response time
        """
        response = client.post(
            "/auth/reset-password", json={"email": "nonexistent@example.com"}
        )

        # Should return generic success message
        assert response.status_code == 200
        expected_message = "Password reset email sent if account exists"
        assert expected_message in response.json()["message"]

    def test_password_reset_timing_consistency(self, client):
        """Test password reset timing is consistent regardless of email existence."""
        # Test with non-existent email
        start_time = time.time()
        nonexistent_response = client.post(
            "/auth/reset-password", json={"email": "fake@example.com"}
        )
        nonexistent_time = time.time() - start_time

        # Test with existing email (if any test users exist)
        start_time = time.time()
        existing_response = client.post(
            "/auth/reset-password", json={"email": "test@example.com"}
        )
        existing_time = time.time() - start_time

        # Both should return 200
        assert nonexistent_response.status_code == 200
        assert existing_response.status_code == 200

        # Timing should be similar
        time_difference = abs(nonexistent_time - existing_time)
        assert (
            time_difference < 0.1
        ), f"Password reset timing variance too high: {time_difference}s"
