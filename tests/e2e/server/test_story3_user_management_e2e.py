"""
E2E Test for Story 3: User Management APIs

Tests complete user lifecycle including:
- CRUD operations for users: POST /api/admin/users (create), GET /api/admin/users (list), PUT /api/admin/users/{username} (update), DELETE /api/admin/users/{username} (delete)
- PUT /api/users/change-password for current user password change
- PUT /api/admin/users/{username}/change-password for admin to change any user's password
- Password complexity validation
- User authentication via all endpoints
- Complete cleanup: remove all test users, restore original admin/admin user only
"""

import pytest
import requests  # type: ignore[import-untyped]
import os
import shutil
import time
import subprocess
import signal
from typing import Generator


class TestStory3UserManagementE2E:
    """E2E test for complete user management functionality."""

    @pytest.fixture(scope="class")
    def server_setup(self) -> Generator[dict, None, None]:
        """Set up CIDX server for E2E testing with complete cleanup."""
        # Create isolated test environment
        test_id = f"story3_{int(time.time())}"
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

            # Start the server
            server_process = subprocess.Popen(
                [
                    "python3",
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

    def login_as_admin(self, server_url: str) -> str:
        """Helper to login as admin and get JWT token."""
        response = requests.post(
            f"{server_url}/auth/login", json={"username": "admin", "password": "admin"}
        )

        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["access_token"]  # type: ignore[no-any-return]

    def get_auth_headers(self, token: str) -> dict:
        """Helper to create Authorization headers."""
        return {"Authorization": f"Bearer {token}"}

    def cleanup_test_users(self, server_url: str, admin_token: str):
        """Helper to cleanup all test users and restore original admin user only."""
        headers = self.get_auth_headers(admin_token)

        # Get all users
        response = requests.get(f"{server_url}/api/admin/users", headers=headers)
        assert response.status_code == 200

        users_data = response.json()
        all_users = users_data.get("users", [])

        # Delete all users except admin
        for user in all_users:
            if user["username"] != "admin":
                delete_response = requests.delete(
                    f"{server_url}/api/admin/users/{user['username']}", headers=headers
                )
                assert (
                    delete_response.status_code == 200
                ), f"Failed to delete user {user['username']}"

        # Verify only admin user remains
        final_response = requests.get(f"{server_url}/api/admin/users", headers=headers)
        assert final_response.status_code == 200

        final_users = final_response.json()["users"]
        assert len(final_users) == 1, f"Expected 1 user, found {len(final_users)}"
        assert final_users[0]["username"] == "admin", "Only admin user should remain"
        assert final_users[0]["role"] == "admin", "Admin user should have admin role"

    def test_complete_user_lifecycle(self, server_setup):
        """Test complete user lifecycle: create admin, power user, normal user, test CRUD operations, password changes, cleanup."""
        server_url = server_setup["server_url"]

        try:
            # Step 1: Login as initial admin
            admin_token = self.login_as_admin(server_url)
            admin_headers = self.get_auth_headers(admin_token)

            # Step 2: Create test users - admin user
            admin_user_response = requests.post(
                f"{server_url}/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "testadmin",
                    "password": "TestAdmin123!",
                    "role": "admin",
                },
            )

            assert (
                admin_user_response.status_code == 201
            ), f"Failed to create admin user: {admin_user_response.text}"
            admin_user_data = admin_user_response.json()

            assert "user" in admin_user_data
            assert admin_user_data["user"]["username"] == "testadmin"
            assert admin_user_data["user"]["role"] == "admin"
            assert "message" in admin_user_data
            assert "created successfully" in admin_user_data["message"]

            # Step 3: Create test users - power user
            power_user_response = requests.post(
                f"{server_url}/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "testpoweruser",
                    "password": "TestPower123!",
                    "role": "power_user",
                },
            )

            assert (
                power_user_response.status_code == 201
            ), f"Failed to create power user: {power_user_response.text}"
            power_user_data = power_user_response.json()

            assert power_user_data["user"]["username"] == "testpoweruser"
            assert power_user_data["user"]["role"] == "power_user"

            # Step 4: Create test users - normal user
            normal_user_response = requests.post(
                f"{server_url}/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "testnormaluser",
                    "password": "TestNormal123!",
                    "role": "normal_user",
                },
            )

            assert (
                normal_user_response.status_code == 201
            ), f"Failed to create normal user: {normal_user_response.text}"
            normal_user_data = normal_user_response.json()

            assert normal_user_data["user"]["username"] == "testnormaluser"
            assert normal_user_data["user"]["role"] == "normal_user"

            # Step 5: Test listing users (should now have 4 total: admin + 3 test users)
            list_response = requests.get(
                f"{server_url}/api/admin/users", headers=admin_headers
            )
            assert list_response.status_code == 200

            list_data = list_response.json()
            assert "users" in list_data
            assert "total" in list_data
            assert (
                list_data["total"] == 4
            )  # admin + testadmin + testpoweruser + testnormaluser

            usernames = [user["username"] for user in list_data["users"]]
            assert "admin" in usernames
            assert "testadmin" in usernames
            assert "testpoweruser" in usernames
            assert "testnormaluser" in usernames

            # Step 6: Test user authentication - power user should be able to login
            power_login_response = requests.post(
                f"{server_url}/auth/login",
                json={"username": "testpoweruser", "password": "TestPower123!"},
            )

            assert (
                power_login_response.status_code == 200
            ), f"Power user login failed: {power_login_response.text}"
            power_token = power_login_response.json()["access_token"]
            power_headers = self.get_auth_headers(power_token)

            # Step 7: Test user authentication - normal user should be able to login
            normal_login_response = requests.post(
                f"{server_url}/auth/login",
                json={"username": "testnormaluser", "password": "TestNormal123!"},
            )

            assert (
                normal_login_response.status_code == 200
            ), f"Normal user login failed: {normal_login_response.text}"
            normal_token = normal_login_response.json()["access_token"]
            normal_headers = self.get_auth_headers(normal_token)

            # Step 8: Test role-based access control - power user should NOT access admin endpoints
            power_user_admin_access = requests.get(
                f"{server_url}/api/admin/users", headers=power_headers
            )
            assert (
                power_user_admin_access.status_code == 403
            ), "Power user should not access admin endpoints"

            # Step 9: Test role-based access control - normal user should NOT access admin endpoints
            normal_user_admin_access = requests.get(
                f"{server_url}/api/admin/users", headers=normal_headers
            )
            assert (
                normal_user_admin_access.status_code == 403
            ), "Normal user should not access admin endpoints"

            # Step 10: Test updating user role
            update_response = requests.put(
                f"{server_url}/api/admin/users/testnormaluser",
                headers=admin_headers,
                json={"role": "power_user"},
            )

            assert (
                update_response.status_code == 200
            ), f"Failed to update user role: {update_response.text}"
            update_data = update_response.json()
            assert "message" in update_data
            assert "updated successfully" in update_data["message"]

            # Verify role was updated by listing users
            updated_list_response = requests.get(
                f"{server_url}/api/admin/users", headers=admin_headers
            )
            assert updated_list_response.status_code == 200

            updated_users = updated_list_response.json()["users"]
            updated_normal_user = next(
                u for u in updated_users if u["username"] == "testnormaluser"
            )
            assert (
                updated_normal_user["role"] == "power_user"
            ), "User role should be updated to power_user"

            # Step 11: Test current user password change
            password_change_response = requests.put(
                f"{server_url}/api/users/change-password",
                headers=power_headers,
                json={"new_password": "NewPowerPass456!"},
            )

            assert (
                password_change_response.status_code == 200
            ), f"Failed to change password: {password_change_response.text}"
            password_change_data = password_change_response.json()
            assert "message" in password_change_data
            assert "changed successfully" in password_change_data["message"]

            # Verify new password works
            new_password_login = requests.post(
                f"{server_url}/auth/login",
                json={"username": "testpoweruser", "password": "NewPowerPass456!"},
            )

            assert (
                new_password_login.status_code == 200
            ), "Login with new password should work"

            # Verify old password doesn't work
            old_password_login = requests.post(
                f"{server_url}/auth/login",
                json={"username": "testpoweruser", "password": "TestPower123!"},
            )

            assert (
                old_password_login.status_code == 401
            ), "Login with old password should fail"

            # Step 12: Test admin changing another user's password
            admin_change_password_response = requests.put(
                f"{server_url}/api/admin/users/testadmin/change-password",
                headers=admin_headers,
                json={"new_password": "AdminChangedPass789!"},
            )

            assert (
                admin_change_password_response.status_code == 200
            ), f"Admin failed to change user password: {admin_change_password_response.text}"
            admin_change_data = admin_change_password_response.json()
            assert "changed successfully" in admin_change_data["message"]

            # Verify admin-changed password works
            admin_changed_login = requests.post(
                f"{server_url}/auth/login",
                json={"username": "testadmin", "password": "AdminChangedPass789!"},
            )

            assert (
                admin_changed_login.status_code == 200
            ), "Login with admin-changed password should work"

            # Step 13: Test password complexity validation
            weak_password_response = requests.post(
                f"{server_url}/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "weakpassuser",
                    "password": "weak",
                    "role": "normal_user",
                },
            )

            assert (
                weak_password_response.status_code == 422
            ), "Weak password should be rejected"

            weak_password_change = requests.put(
                f"{server_url}/api/users/change-password",
                headers=power_headers,
                json={"new_password": "weak"},
            )

            assert (
                weak_password_change.status_code == 422
            ), "Weak password change should be rejected"

            # Step 14: Test duplicate username validation
            duplicate_user_response = requests.post(
                f"{server_url}/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "testadmin",  # Already exists
                    "password": "ValidPass123!",
                    "role": "normal_user",
                },
            )

            assert (
                duplicate_user_response.status_code == 400
            ), "Duplicate username should be rejected"
            duplicate_data = duplicate_user_response.json()
            assert "already exists" in duplicate_data["detail"]

            # Step 15: Test deleting users
            delete_response = requests.delete(
                f"{server_url}/api/admin/users/testnormaluser", headers=admin_headers
            )
            assert (
                delete_response.status_code == 200
            ), f"Failed to delete user: {delete_response.text}"
            delete_data = delete_response.json()
            assert "deleted successfully" in delete_data["message"]

            # Verify user was deleted
            post_delete_list = requests.get(
                f"{server_url}/api/admin/users", headers=admin_headers
            )
            assert post_delete_list.status_code == 200

            remaining_users = post_delete_list.json()["users"]
            remaining_usernames = [u["username"] for u in remaining_users]
            assert (
                "testnormaluser" not in remaining_usernames
            ), "Deleted user should not appear in list"
            assert (
                len(remaining_users) == 3
            ), "Should have 3 users after deletion"  # admin + testadmin + testpoweruser

            # Step 16: Test accessing non-existent user endpoints
            nonexistent_update = requests.put(
                f"{server_url}/api/admin/users/nonexistent",
                headers=admin_headers,
                json={"role": "admin"},
            )
            assert (
                nonexistent_update.status_code == 404
            ), "Update non-existent user should return 404"

            nonexistent_delete = requests.delete(
                f"{server_url}/api/admin/users/nonexistent", headers=admin_headers
            )
            assert (
                nonexistent_delete.status_code == 404
            ), "Delete non-existent user should return 404"

            nonexistent_password = requests.put(
                f"{server_url}/api/admin/users/nonexistent/change-password",
                headers=admin_headers,
                json={"new_password": "ValidPass123!"},
            )
            assert (
                nonexistent_password.status_code == 404
            ), "Change password for non-existent user should return 404"

        finally:
            # Step 17: Cleanup - remove all test users, restore original admin/admin user only
            try:
                final_admin_token = self.login_as_admin(server_url)
                self.cleanup_test_users(server_url, final_admin_token)
            except Exception as cleanup_error:
                print(
                    f"Cleanup warning: {cleanup_error}"
                )  # Don't fail test due to cleanup issues

    def test_password_complexity_validation(self, server_setup):
        """Test password complexity validation with various password scenarios."""
        server_url = server_setup["server_url"]

        try:
            admin_token = self.login_as_admin(server_url)
            admin_headers = self.get_auth_headers(admin_token)

            # Test various weak passwords
            weak_passwords = [
                "short",  # Too short
                "password",  # No uppercase, digits, or special chars
                "PASSWORD123",  # No lowercase or special chars
                "password123",  # No uppercase or special chars
                "Password",  # No digits or special chars
                "NoNumbers!",  # No digits
                "NoSpecial123",  # No special chars
            ]

            for weak_password in weak_passwords:
                response = requests.post(
                    f"{server_url}/api/admin/users",
                    headers=admin_headers,
                    json={
                        "username": f"user_{weak_password[:5]}",
                        "password": weak_password,
                        "role": "normal_user",
                    },
                )

                assert (
                    response.status_code == 422
                ), f"Weak password '{weak_password}' should be rejected"
                error_data = response.json()
                assert "detail" in error_data
                assert "password" in error_data["detail"][0]["msg"].lower()

            # Test strong passwords that should pass
            strong_passwords = [
                "StrongPass123!",
                "Complex@Pass456",
                "MySecure789#Pass",
                "Validation@2024Test!",
            ]

            created_users = []
            for i, strong_password in enumerate(strong_passwords):
                username = f"stronguser{i}"
                response = requests.post(
                    f"{server_url}/api/admin/users",
                    headers=admin_headers,
                    json={
                        "username": username,
                        "password": strong_password,
                        "role": "normal_user",
                    },
                )

                assert (
                    response.status_code == 201
                ), f"Strong password '{strong_password}' should be accepted: {response.text}"
                created_users.append(username)

                # Verify the user can login with the strong password
                login_response = requests.post(
                    f"{server_url}/auth/login",
                    json={"username": username, "password": strong_password},
                )

                assert (
                    login_response.status_code == 200
                ), f"Login with strong password should work for {username}"

        finally:
            # Cleanup
            try:
                final_admin_token = self.login_as_admin(server_url)
                self.cleanup_test_users(server_url, final_admin_token)
            except Exception as cleanup_error:
                print(f"Cleanup warning: {cleanup_error}")

    def test_role_based_access_control_comprehensive(self, server_setup):
        """Test comprehensive role-based access control scenarios."""
        server_url = server_setup["server_url"]

        try:
            admin_token = self.login_as_admin(server_url)
            admin_headers = self.get_auth_headers(admin_token)

            # Create test users for each role
            test_users = [
                {
                    "username": "testadmin2",
                    "password": "TestAdmin123!",
                    "role": "admin",
                },
                {
                    "username": "testpower2",
                    "password": "TestPower123!",
                    "role": "power_user",
                },
                {
                    "username": "testnormal2",
                    "password": "TestNormal123!",
                    "role": "normal_user",
                },
            ]

            user_tokens = {}

            for user_data in test_users:
                # Create user
                create_response = requests.post(
                    f"{server_url}/api/admin/users",
                    headers=admin_headers,
                    json=user_data,
                )
                assert (
                    create_response.status_code == 201
                ), f"Failed to create {user_data['role']} user"

                # Login as user to get token
                login_response = requests.post(
                    f"{server_url}/auth/login",
                    json={
                        "username": user_data["username"],
                        "password": user_data["password"],
                    },
                )
                assert (
                    login_response.status_code == 200
                ), f"Failed to login as {user_data['username']}"
                user_tokens[user_data["role"]] = login_response.json()["access_token"]

            # Test admin endpoints access
            admin_endpoints = [
                ("GET", "/api/admin/users"),
                (
                    "POST",
                    "/api/admin/users",
                    {
                        "username": "temp",
                        "password": "TempPass123!",
                        "role": "normal_user",
                    },
                ),
                ("PUT", "/api/admin/users/testnormal2", {"role": "power_user"}),
                ("DELETE", "/api/admin/users/temp"),
                (
                    "PUT",
                    "/api/admin/users/testnormal2/change-password",
                    {"new_password": "NewPass123!"},
                ),
            ]

            for method, endpoint, *json_data in admin_endpoints:
                json_payload = json_data[0] if json_data else None

                # Admin should have access
                admin_response = requests.request(
                    method,
                    f"{server_url}{endpoint}",
                    headers=self.get_auth_headers(user_tokens["admin"]),
                    json=json_payload,
                )
                assert admin_response.status_code not in [
                    401,
                    403,
                ], f"Admin should access {method} {endpoint}"

                # Power user should NOT have access to admin endpoints
                if isinstance(endpoint, str) and endpoint.startswith("/api/admin"):
                    power_response = requests.request(
                        method,
                        f"{server_url}{endpoint}",
                        headers=self.get_auth_headers(user_tokens["power_user"]),
                        json=json_payload,
                    )
                    assert (
                        power_response.status_code == 403
                    ), f"Power user should not access {method} {endpoint}"

                    # Normal user should NOT have access to admin endpoints
                    normal_response = requests.request(
                        method,
                        f"{server_url}{endpoint}",
                        headers=self.get_auth_headers(user_tokens["normal_user"]),
                        json=json_payload,
                    )
                    assert (
                        normal_response.status_code == 403
                    ), f"Normal user should not access {method} {endpoint}"

            # Test user endpoints that all roles should access
            user_endpoints = [
                ("GET", "/api/repos"),  # All users can list their repos
                (
                    "PUT",
                    "/api/users/change-password",
                    {"new_password": "NewUserPass123!"},
                ),  # All users can change their own password
            ]

            for role in ["admin", "power_user", "normal_user"]:
                for method, endpoint, *json_data in user_endpoints:
                    json_payload = json_data[0] if json_data else None

                    response = requests.request(
                        method,
                        f"{server_url}{endpoint}",
                        headers=self.get_auth_headers(user_tokens[role]),
                        json=json_payload,
                    )
                    # Should not be forbidden (may return other status codes based on implementation)
                    assert (
                        response.status_code != 403
                    ), f"{role} should access {method} {endpoint}"

        finally:
            # Cleanup
            try:
                final_admin_token = self.login_as_admin(server_url)
                self.cleanup_test_users(server_url, final_admin_token)
            except Exception as cleanup_error:
                print(f"Cleanup warning: {cleanup_error}")
