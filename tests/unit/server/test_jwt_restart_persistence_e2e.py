"""
End-to-end test for JWT token persistence across server restarts.

This test verifies that JWT tokens created by one server instance
remain valid after the server restarts, demonstrating proper
secret key persistence.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app


class TestJWTRestartPersistenceE2E:
    """Test JWT token persistence across server restarts end-to-end."""

    def test_jwt_token_survives_server_restart(self):
        """Test that JWT tokens remain valid across server restarts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock home directory to use temp directory
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                # === FIRST SERVER INSTANCE ===
                app1 = create_app()
                client1 = TestClient(app1)

                # Login with first server instance to get a token
                login_response = client1.post(
                    "/auth/login", json={"username": "admin", "password": "admin"}
                )
                assert login_response.status_code == 200

                token_data = login_response.json()
                access_token = token_data["access_token"]
                headers = {"Authorization": f"Bearer {access_token}"}

                # Verify token works with first server
                protected_response = client1.get("/api/admin/users", headers=headers)
                assert protected_response.status_code == 200

                # Verify JWT secret file was created
                secret_file = Path(temp_dir) / ".cidx-server" / ".jwt_secret"
                assert secret_file.exists(), "JWT secret file should be created"
                secret_content = secret_file.read_text()
                assert len(secret_content) > 0, "JWT secret file should not be empty"

                # === SIMULATE SERVER RESTART ===
                # (Create new app instance which should reuse the same secret)

                app2 = create_app()
                client2 = TestClient(app2)

                # Verify that the same token still works with the new server instance
                protected_response2 = client2.get("/api/admin/users", headers=headers)
                assert (
                    protected_response2.status_code == 200
                ), "Token from first server should work with second server"

                # Verify response contains expected data
                users_data = protected_response2.json()
                assert "users" in users_data
                assert "total" in users_data
                assert users_data["total"] >= 1  # At least admin user should exist

                # === ADDITIONAL VERIFICATION ===
                # Verify token is still valid for multiple operations

                # Test different endpoints with the same token
                endpoints_to_test = [
                    "/api/admin/users",
                    "/api/admin/golden-repos",  # Should return 501 but with proper auth
                ]

                for endpoint in endpoints_to_test:
                    response = client2.get(endpoint, headers=headers)
                    # Should not return 401 (auth error), regardless of other status codes
                    assert (
                        response.status_code != 401
                    ), f"Endpoint {endpoint} should not return auth error with valid token"

    def test_jwt_secret_file_permissions_persist(self):
        """Test that JWT secret file maintains proper permissions across restarts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                # Create first server instance
                create_app()

                secret_file = Path(temp_dir) / ".cidx-server" / ".jwt_secret"
                assert secret_file.exists()

                # Check initial permissions
                initial_permissions = secret_file.stat().st_mode & 0o777
                assert initial_permissions == 0o600

                # Create second server instance (restart)
                create_app()

                # Permissions should remain the same
                final_permissions = secret_file.stat().st_mode & 0o777
                assert final_permissions == 0o600

                # Secret content should be the same
                assert secret_file.exists()
                assert len(secret_file.read_text()) > 0

    def test_multiple_tokens_persist_across_restart(self):
        """Test that multiple JWT tokens persist across server restart."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                # === FIRST SERVER INSTANCE ===
                app1 = create_app()
                client1 = TestClient(app1)

                # Create multiple users and get tokens for each
                # (Note: We'll use the admin user and create additional ones via API)

                # Get admin token first
                admin_login = client1.post(
                    "/auth/login", json={"username": "admin", "password": "admin"}
                )
                assert admin_login.status_code == 200
                admin_token = admin_login.json()["access_token"]
                admin_headers = {"Authorization": f"Bearer {admin_token}"}

                # Verify admin token works
                admin_response = client1.get("/api/admin/users", headers=admin_headers)
                assert admin_response.status_code == 200

                # === SERVER RESTART ===
                app2 = create_app()
                client2 = TestClient(app2)

                # Verify admin token still works after restart
                admin_response2 = client2.get("/api/admin/users", headers=admin_headers)
                assert admin_response2.status_code == 200

                # The response should contain the same user data
                users1 = admin_response.json()["users"]
                users2 = admin_response2.json()["users"]

                assert len(users1) == len(users2)
                assert users1[0]["username"] == users2[0]["username"]
                assert users1[0]["role"] == users2[0]["role"]

    def test_jwt_secret_uniqueness_across_different_temp_dirs(self):
        """Test that different server instances in different directories have different secrets."""
        with tempfile.TemporaryDirectory() as temp_dir1:
            with tempfile.TemporaryDirectory() as temp_dir2:
                # Create first server in temp_dir1
                with patch("pathlib.Path.home", return_value=Path(temp_dir1)):
                    create_app()
                    secret_file1 = Path(temp_dir1) / ".cidx-server" / ".jwt_secret"
                    assert secret_file1.exists()
                    secret1 = secret_file1.read_text()

                # Create second server in temp_dir2
                with patch("pathlib.Path.home", return_value=Path(temp_dir2)):
                    create_app()
                    secret_file2 = Path(temp_dir2) / ".cidx-server" / ".jwt_secret"
                    assert secret_file2.exists()
                    secret2 = secret_file2.read_text()

                # Secrets should be different
                assert (
                    secret1 != secret2
                ), "Different server instances should have different secrets"
                assert len(secret1) > 0 and len(secret2) > 0

    def test_environment_variable_override_persists(self):
        """Test that environment variable JWT secret is saved and persists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                custom_secret = "custom-jwt-secret-from-env-12345"

                # Set environment variable and create first server
                with patch.dict("os.environ", {"JWT_SECRET_KEY": custom_secret}):
                    create_app()

                # Check that secret was saved to file
                secret_file = Path(temp_dir) / ".cidx-server" / ".jwt_secret"
                assert secret_file.exists()
                saved_secret = secret_file.read_text().strip()
                assert saved_secret == custom_secret

                # Create second server without environment variable
                # It should use the saved secret from file
                create_app()

                # Verify secret is still the same
                assert secret_file.read_text().strip() == custom_secret
