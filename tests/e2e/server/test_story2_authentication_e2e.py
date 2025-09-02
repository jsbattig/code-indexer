"""
E2E Test for Story 2: FastAPI Server Foundation with Authentication

Tests complete authentication flow including:
- JWT-based authentication with 10-minute default token expiration
- Role-based access control for admin, power_user, normal_user
- User storage in ~/.cidx-server/users.json with hashed passwords
- /auth/login endpoint functionality
- Global authentication requirement for all API endpoints
- Initial admin user seeding (admin/admin)
- Swagger/OpenAPI documentation at /docs endpoint
- User authentication via Swagger UI
"""

import pytest
import requests
import json
import os
import shutil
import time
import subprocess
import signal
from datetime import datetime, timezone
from typing import Generator


class TestStory2AuthenticationE2E:
    """E2E test for complete authentication flow."""

    @pytest.fixture(scope="class")
    def server_setup(self) -> Generator[dict, None, None]:
        """Set up CIDX server for E2E testing with complete cleanup."""
        # Create isolated test environment
        test_id = f"story2_{int(time.time())}"
        original_home = os.path.expanduser("~")
        test_home = f"/tmp/cidx-server-test-{test_id}"

        # Create test home directory
        os.makedirs(test_home, exist_ok=True)
        server_dir = f"{test_home}/.cidx-server"

        server_process = None
        server_port = None

        try:
            # Mock HOME environment to use test directory
            original_env = os.environ.copy()
            os.environ["HOME"] = test_home

            # Run cidx install-server to set up server
            result = subprocess.run(
                ["cidx", "install-server"], capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                pytest.fail(f"Failed to install server: {result.stderr}")

            # Parse server port from installation output
            output_lines = result.stdout.split("\n")
            for line in output_lines:
                if "port" in line.lower() and any(char.isdigit() for char in line):
                    # Extract port number from line
                    port_nums = [int(s) for s in line.split() if s.isdigit()]
                    if port_nums:
                        server_port = port_nums[0]
                        break

            if not server_port:
                server_port = 8090  # Default fallback

            # Verify server directory was created
            assert os.path.exists(
                server_dir
            ), f"Server directory not created: {server_dir}"
            assert os.path.exists(
                f"{server_dir}/config.json"
            ), "Config file not created"
            assert os.path.exists(f"{server_dir}/users.json"), "Users file not created"
            assert os.path.exists(
                f"{server_dir}/start-server.sh"
            ), "Startup script not created"

            # Verify initial admin user was seeded
            with open(f"{server_dir}/users.json", "r") as f:
                users_data = json.load(f)
                assert "admin" in users_data, "Initial admin user not seeded"
                admin_data = users_data["admin"]
                assert admin_data["role"] == "admin", "Admin user role incorrect"
                assert "password_hash" in admin_data, "Admin password not hashed"

            # Start the server
            server_process = subprocess.Popen(
                [
                    "python",
                    "-m",
                    "code_indexer.server.main",
                    "--port",
                    str(server_port),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=original_home,  # Run from original directory but use test HOME
            )

            # Wait for server to start (max 30 seconds)
            server_url = f"http://localhost:{server_port}"
            for attempt in range(30):
                try:
                    response = requests.get(f"{server_url}/health", timeout=2)
                    if response.status_code == 200:
                        break
                except requests.exceptions.RequestException:
                    pass
                time.sleep(1)
            else:
                pytest.fail("Server failed to start within 30 seconds")

            yield {
                "server_url": server_url,
                "server_port": server_port,
                "server_dir": server_dir,
                "test_home": test_home,
                "original_env": original_env,
            }

        finally:
            # Cleanup: Stop server process
            if server_process:
                server_process.terminate()
                try:
                    server_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server_process.kill()
                    server_process.wait()

            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

            # Remove test directories
            if os.path.exists(test_home):
                shutil.rmtree(test_home, ignore_errors=True)

            # Verify no dangling server processes
            try:
                result = subprocess.run(
                    ["pgrep", "-f", "cidx.*server"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Found dangling processes, try to clean them up
                    pids = result.stdout.strip().split("\n")
                    for pid in pids:
                        if pid.strip():
                            try:
                                os.kill(int(pid), signal.SIGTERM)
                            except (ProcessLookupError, ValueError):
                                pass
            except subprocess.TimeoutExpired:
                pass

    def test_initial_admin_user_seeding(self, server_setup):
        """Test that initial admin user (admin/admin) is seeded during installation."""
        server_dir = server_setup["server_dir"]

        # Verify users.json exists and contains admin user
        users_file = f"{server_dir}/users.json"
        assert os.path.exists(users_file), "Users file not created"

        with open(users_file, "r") as f:
            users_data = json.load(f)

        assert "admin" in users_data, "Admin user not found in users.json"
        admin_data = users_data["admin"]

        # Verify admin user structure
        assert admin_data["role"] == "admin", "Admin role incorrect"
        assert "password_hash" in admin_data, "Password hash missing"
        assert admin_data["password_hash"].startswith(
            "$2b$"
        ), "Password not properly hashed"
        assert "created_at" in admin_data, "Created timestamp missing"

        # Verify created_at is valid ISO format
        try:
            created_at = datetime.fromisoformat(
                admin_data["created_at"].replace("Z", "+00:00")
            )
            assert isinstance(created_at, datetime)
        except ValueError:
            pytest.fail("Invalid created_at timestamp format")

    def test_login_with_initial_admin_credentials(self, server_setup):
        """Test login with initial admin credentials (admin/admin) returns JWT token."""
        server_url = server_setup["server_url"]

        response = requests.post(
            f"{server_url}/auth/login", json={"username": "admin", "password": "admin"}
        )

        assert response.status_code == 200, f"Login failed: {response.text}"

        response_data = response.json()

        # Verify response structure
        assert "access_token" in response_data, "Access token missing from response"
        assert "token_type" in response_data, "Token type missing from response"
        assert "user" in response_data, "User info missing from response"

        # Verify token type
        assert response_data["token_type"] == "bearer", "Token type should be 'bearer'"

        # Verify user information
        user_info = response_data["user"]
        assert user_info["username"] == "admin", "Username incorrect in response"
        assert user_info["role"] == "admin", "Role incorrect in response"

        # Verify JWT token format (3 parts separated by dots)
        token = response_data["access_token"]
        token_parts = token.split(".")
        assert len(token_parts) == 3, "JWT token should have 3 parts"

        # Each part should be non-empty
        for part in token_parts:
            assert len(part) > 0, "JWT token parts should not be empty"

    def test_login_with_invalid_credentials(self, server_setup):
        """Test login with invalid credentials returns 401."""
        server_url = server_setup["server_url"]

        # Test wrong password
        response = requests.post(
            f"{server_url}/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )

        assert response.status_code == 401, "Should return 401 for wrong password"
        response_data = response.json()
        assert "detail" in response_data, "Error detail missing"
        assert "Invalid username or password" in response_data["detail"]

        # Test nonexistent user
        response = requests.post(
            f"{server_url}/auth/login",
            json={"username": "nonexistent", "password": "anypassword"},
        )

        assert response.status_code == 401, "Should return 401 for nonexistent user"

    def test_protected_endpoint_without_authentication(self, server_setup):
        """Test that protected API endpoints require authentication."""
        server_url = server_setup["server_url"]

        # Test various protected endpoints without authorization header
        protected_endpoints = [
            "/api/repos",
            "/api/admin/users",
            "/api/admin/golden-repos",
            "/api/query",
        ]

        for endpoint in protected_endpoints:
            response = requests.get(f"{server_url}{endpoint}")
            assert (
                response.status_code == 401
            ), f"Endpoint {endpoint} should require authentication"

            response_data = response.json()
            assert "detail" in response_data, f"Error detail missing for {endpoint}"
            assert "Not authenticated" in response_data["detail"]

    def test_protected_endpoint_with_invalid_token(self, server_setup):
        """Test that protected endpoints reject invalid JWT tokens."""
        server_url = server_setup["server_url"]

        # Test with invalid token format
        headers = {"Authorization": "Bearer invalid.jwt.token"}
        response = requests.get(f"{server_url}/api/repos", headers=headers)

        assert response.status_code == 401, "Should reject invalid token"

        # Test with malformed authorization header
        headers = {"Authorization": "InvalidFormat jwt.token.here"}
        response = requests.get(f"{server_url}/api/repos", headers=headers)

        assert response.status_code == 401, "Should reject malformed auth header"

    def test_protected_endpoint_with_valid_token(self, server_setup):
        """Test that protected endpoints accept valid JWT tokens."""
        server_url = server_setup["server_url"]

        # First, login to get valid token
        login_response = requests.post(
            f"{server_url}/auth/login", json={"username": "admin", "password": "admin"}
        )

        assert login_response.status_code == 200, "Login should succeed"
        token = login_response.json()["access_token"]

        # Use token to access protected endpoint
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{server_url}/api/repos", headers=headers)

        # Should not return 401 (may return other status codes based on endpoint logic)
        assert response.status_code != 401, "Valid token should not return 401"

    def test_jwt_token_expiration_functionality(self, server_setup):
        """Test JWT token expiration and activity-based extension."""
        server_url = server_setup["server_url"]

        # Login to get token
        login_response = requests.post(
            f"{server_url}/auth/login", json={"username": "admin", "password": "admin"}
        )

        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Decode token to check expiration (without verification for testing)
        import base64
        import json

        # Split token and decode payload (second part)
        token_parts = token.split(".")
        # Add padding if needed for base64 decoding
        payload = token_parts[1] + "=" * (4 - len(token_parts[1]) % 4)
        decoded_payload = json.loads(base64.b64decode(payload))

        # Verify token has expiration time
        assert "exp" in decoded_payload, "Token should contain expiration time"
        assert "iat" in decoded_payload, "Token should contain issued-at time"

        # Verify expiration is approximately 10 minutes from now
        import time

        int(time.time())
        token_exp = decoded_payload["exp"]
        token_iat = decoded_payload["iat"]

        # Should expire in roughly 10 minutes (600 seconds)
        exp_duration = token_exp - token_iat
        assert (
            590 <= exp_duration <= 610
        ), f"Token should expire in ~10 minutes, got {exp_duration} seconds"

        # Use token immediately - should work
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{server_url}/api/repos", headers=headers)
        assert response.status_code != 401, "Fresh token should be valid"

    def test_role_based_access_control(self, server_setup):
        """Test role-based access control for different user types."""
        server_url = server_setup["server_url"]
        server_dir = server_setup["server_dir"]

        # Create test users with different roles (by directly modifying users.json for testing)
        users_file = f"{server_dir}/users.json"
        with open(users_file, "r") as f:
            users_data = json.load(f)

        # Add test users (using bcrypt hash for "testpass")
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        test_password_hash = pwd_context.hash("testpass")
        current_time = datetime.now(timezone.utc).isoformat()

        users_data["poweruser"] = {
            "role": "power_user",
            "password_hash": test_password_hash,
            "created_at": current_time,
        }

        users_data["normaluser"] = {
            "role": "normal_user",
            "password_hash": test_password_hash,
            "created_at": current_time,
        }

        with open(users_file, "w") as f:
            json.dump(users_data, f, indent=2)

        # Test admin user access (already tested admin login)
        admin_login = requests.post(
            f"{server_url}/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Admin should access admin endpoints
        response = requests.get(f"{server_url}/api/admin/users", headers=admin_headers)
        assert response.status_code != 403, "Admin should access /api/admin/users"

        response = requests.get(
            f"{server_url}/api/admin/golden-repos", headers=admin_headers
        )
        assert (
            response.status_code != 403
        ), "Admin should access /api/admin/golden-repos"

        # Test power user access
        power_login = requests.post(
            f"{server_url}/auth/login",
            json={"username": "poweruser", "password": "testpass"},
        )
        assert power_login.status_code == 200
        power_token = power_login.json()["access_token"]
        power_headers = {"Authorization": f"Bearer {power_token}"}

        # Power user should NOT access admin endpoints
        response = requests.get(f"{server_url}/api/admin/users", headers=power_headers)
        assert (
            response.status_code == 403
        ), "Power user should not access admin endpoints"

        # Power user should access query and repo endpoints
        response = requests.get(f"{server_url}/api/repos", headers=power_headers)
        assert response.status_code != 403, "Power user should access /api/repos"

        # Test normal user access
        normal_login = requests.post(
            f"{server_url}/auth/login",
            json={"username": "normaluser", "password": "testpass"},
        )
        assert normal_login.status_code == 200
        normal_token = normal_login.json()["access_token"]
        normal_headers = {"Authorization": f"Bearer {normal_token}"}

        # Normal user should NOT access admin endpoints
        response = requests.get(f"{server_url}/api/admin/users", headers=normal_headers)
        assert (
            response.status_code == 403
        ), "Normal user should not access admin endpoints"

        # Normal user should NOT access activation endpoints
        response = requests.post(
            f"{server_url}/api/repos/activate",
            headers=normal_headers,
            json={"goldenRepoName": "test", "alias": "test"},
        )
        assert (
            response.status_code == 403
        ), "Normal user should not access activation endpoints"

        # Normal user should access query endpoints
        response = requests.get(f"{server_url}/api/repos", headers=normal_headers)
        assert response.status_code != 403, "Normal user should access query endpoints"

    def test_swagger_documentation_accessible(self, server_setup):
        """Test that Swagger/OpenAPI documentation is accessible."""
        server_url = server_setup["server_url"]

        # Test /docs endpoint
        response = requests.get(f"{server_url}/docs")
        assert response.status_code == 200, "/docs endpoint should be accessible"
        assert "text/html" in response.headers.get(
            "content-type", ""
        ), "/docs should return HTML"

        # Should contain Swagger UI elements
        content = response.text.lower()
        assert "swagger" in content or "openapi" in content, "Should contain Swagger UI"

        # Test OpenAPI JSON spec
        response = requests.get(f"{server_url}/openapi.json")
        assert response.status_code == 200, "OpenAPI spec should be accessible"
        assert (
            response.headers["content-type"] == "application/json"
        ), "Should return JSON"

        openapi_spec = response.json()
        assert isinstance(openapi_spec, dict), "Should be valid JSON object"

        # Verify spec contains authentication endpoints
        assert "paths" in openapi_spec, "OpenAPI spec should have paths"
        assert (
            "/auth/login" in openapi_spec["paths"]
        ), "Should document /auth/login endpoint"

        # Verify spec contains security schemes
        assert "components" in openapi_spec, "OpenAPI spec should have components"
        assert (
            "securitySchemes" in openapi_spec["components"]
        ), "Should have security schemes"

    def test_swagger_ui_authentication_capability(self, server_setup):
        """Test that users can authenticate via Swagger UI."""
        server_url = server_setup["server_url"]

        # Access Swagger UI
        response = requests.get(f"{server_url}/docs")
        assert response.status_code == 200

        content = response.text.lower()

        # Should include authentication elements for testing APIs
        auth_indicators = ["authorize", "authentication", "bearer", "token", "login"]

        found_auth_elements = sum(
            1 for indicator in auth_indicators if indicator in content
        )
        assert (
            found_auth_elements >= 2
        ), "Swagger UI should provide authentication capability"

        # Test that login endpoint is documented and accessible via Swagger
        openapi_response = requests.get(f"{server_url}/openapi.json")
        openapi_spec = openapi_response.json()

        login_endpoint = openapi_spec["paths"]["/auth/login"]["post"]
        assert (
            "requestBody" in login_endpoint
        ), "Login endpoint should document request body"
        assert "responses" in login_endpoint, "Login endpoint should document responses"

    def test_public_endpoints_dont_require_auth(self, server_setup):
        """Test that public endpoints don't require authentication."""
        server_url = server_setup["server_url"]

        public_endpoints = ["/health", "/docs", "/openapi.json", "/auth/login"]

        for endpoint in public_endpoints:
            if endpoint == "/auth/login":
                # POST to login without body should return 422, not 401
                response = requests.post(f"{server_url}{endpoint}")
                assert (
                    response.status_code == 422
                ), f"{endpoint} should not require auth (422 != 401)"
            else:
                response = requests.get(f"{server_url}{endpoint}")
                assert (
                    response.status_code != 401
                ), f"{endpoint} should not require authentication"

    def test_users_json_storage_format(self, server_setup):
        """Test that users are properly stored in ~/.cidx-server/users.json with hashed passwords."""
        server_dir = server_setup["server_dir"]
        users_file = f"{server_dir}/users.json"

        # Verify file exists and is valid JSON
        assert os.path.exists(users_file), "users.json should exist"

        with open(users_file, "r") as f:
            users_data = json.load(f)

        assert isinstance(users_data, dict), "users.json should contain a dictionary"
        assert "admin" in users_data, "Admin user should be in users.json"

        admin_data = users_data["admin"]

        # Verify required fields exist
        required_fields = ["role", "password_hash", "created_at"]
        for field in required_fields:
            assert field in admin_data, f"Admin user should have {field} field"

        # Verify password is hashed (bcrypt format)
        password_hash = admin_data["password_hash"]
        assert password_hash.startswith("$2b$"), "Password should be bcrypt hashed"
        assert len(password_hash) >= 60, "Bcrypt hash should be at least 60 characters"

        # Verify role is correct
        assert admin_data["role"] == "admin", "Admin user role should be 'admin'"

        # Verify created_at is valid ISO timestamp
        try:
            created_at = datetime.fromisoformat(
                admin_data["created_at"].replace("Z", "+00:00")
            )
            assert isinstance(
                created_at, datetime
            ), "created_at should be valid datetime"
        except ValueError:
            pytest.fail("created_at should be valid ISO format timestamp")

    def test_complete_authentication_workflow(self, server_setup):
        """Test complete authentication workflow from installation to API access."""
        server_url = server_setup["server_url"]

        # Step 1: Verify server installed correctly
        health_response = requests.get(f"{server_url}/health")
        assert health_response.status_code == 200, "Server should be healthy"

        # Step 2: Verify initial admin user exists and can login
        login_response = requests.post(
            f"{server_url}/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login_response.status_code == 200, "Initial admin login should work"

        token = login_response.json()["access_token"]
        user_info = login_response.json()["user"]

        assert user_info["username"] == "admin", "Login should return admin user info"
        assert user_info["role"] == "admin", "Admin should have admin role"

        # Step 3: Use token to access protected endpoints
        headers = {"Authorization": f"Bearer {token}"}

        # Should be able to access admin endpoints
        admin_response = requests.get(f"{server_url}/api/admin/users", headers=headers)
        assert admin_response.status_code != 401, "Admin should access admin endpoints"

        # Should be able to access general endpoints
        repos_response = requests.get(f"{server_url}/api/repos", headers=headers)
        assert repos_response.status_code != 401, "Admin should access repo endpoints"

        # Step 4: Verify token validation works
        # Remove one character from token to make it invalid
        invalid_token = token[:-1]
        invalid_headers = {"Authorization": f"Bearer {invalid_token}"}

        invalid_response = requests.get(
            f"{server_url}/api/repos", headers=invalid_headers
        )
        assert invalid_response.status_code == 401, "Invalid token should be rejected"

        # Step 5: Verify documentation is accessible
        docs_response = requests.get(f"{server_url}/docs")
        assert docs_response.status_code == 200, "Documentation should be accessible"

        openapi_response = requests.get(f"{server_url}/openapi.json")
        assert openapi_response.status_code == 200, "OpenAPI spec should be accessible"
