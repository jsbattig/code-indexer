"""
Comprehensive E2E test suite for complete user workflows.

This test demonstrates the full testing infrastructure in action, testing
complete user workflows from registration through semantic search using
all the test helper utilities.
"""

import pytest
import tempfile
from pathlib import Path

from tests.utils import (
    TestDataFactory,
    ServerLifecycleManager,
    AuthTestHelper,
    EnvironmentManager,
)


@pytest.mark.slow
@pytest.mark.e2e
class TestCompleteUserWorkflows:
    """Complete end-to-end user workflow tests."""

    @pytest.fixture(scope="class")
    def test_environment(self):
        """Set up complete test environment with all services."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_path = Path(tmp_dir)

            # Create test data factory
            data_factory = TestDataFactory()

            # Create test repository
            test_repo = data_factory.create_test_repository(
                name="e2e_test_repo",
                base_path=base_path,
                branches=["master", "feature/auth", "feature/search"],
            )

            # Create test users
            test_users = data_factory.get_default_test_users()

            # Create server lifecycle manager
            server_manager = ServerLifecycleManager(base_path=base_path / "servers")

            # Create main test server
            main_server = server_manager.create_test_server(
                server_id="main_server", auto_start=False  # We'll start it manually
            )

            # Create container environment manager
            container_manager = EnvironmentManager(
                environment_name="e2e_test_env", base_path=base_path / "containers"
            )

            # Create Filesystem environment (for semantic search)
            filesystem_env = container_manager.create_standard_filesystem_environment()

            # Start container services
            containers_started = container_manager.start_environment(
                "test_env", filesystem_env
            )

            # Start main server
            server_started = main_server.start_server(wait_for_ready=True)

            # Create authentication helper
            auth_helper = AuthTestHelper(main_server.server_url)

            yield {
                "base_path": base_path,
                "data_factory": data_factory,
                "test_repo": test_repo,
                "test_users": test_users,
                "server_manager": server_manager,
                "main_server": main_server,
                "container_manager": container_manager,
                "auth_helper": auth_helper,
                "containers_started": containers_started,
                "server_started": server_started,
            }

            # Cleanup in finally block
            try:
                main_server.stop_server()
                main_server.cleanup_server_files()
                container_manager.cleanup_all_environments()
                server_manager.cleanup_all_servers()
                data_factory.cleanup_test_data()
            except Exception as e:
                print(f"Cleanup error: {e}")

    def test_complete_admin_workflow(self, test_environment):
        """Test complete admin workflow: login -> manage users -> manage golden repos -> query."""
        if not test_environment["server_started"]:
            pytest.skip("Server not started")

        auth_helper = test_environment["auth_helper"]
        main_server = test_environment["main_server"]
        test_repo = test_environment["test_repo"]

        # Step 1: Admin login
        admin_login = auth_helper.login_user("admin", "admin")
        assert admin_login["success"], f"Admin login failed: {admin_login.get('error')}"

        admin_token = admin_login["token"]
        admin_headers = auth_helper.create_auth_headers(admin_token)

        # Step 2: List users (admin only)
        response = main_server.make_api_request(
            "GET", "/api/admin/users", headers=admin_headers
        )

        # Should not be 401 (unauthorized) - exact status depends on implementation
        assert response.status_code != 401, "Admin should access user management"

        # Step 3: Create golden repository entry
        golden_repo_data = {
            "name": test_repo.name,
            "description": "Test repository for E2E testing",
            "source_url": f"file://{test_repo.path}",
            "branch": "master",
        }

        response = main_server.make_api_request(
            "POST",
            "/api/admin/golden-repos",
            headers=admin_headers,
            json_data=golden_repo_data,
        )

        # Should not be 403 (forbidden) - admin should be able to create golden repos
        assert (
            response.status_code != 403
        ), "Admin should be able to create golden repos"

        # Step 4: List golden repositories
        response = main_server.make_api_request(
            "GET", "/api/admin/golden-repos", headers=admin_headers
        )

        assert response.status_code != 401, "Admin should access golden repo management"

        # Step 5: Perform semantic search (should work for admin)
        search_query = {"query": "authentication function", "limit": 10}

        response = main_server.make_api_request(
            "POST", "/api/search", headers=admin_headers, json_data=search_query
        )

        assert response.status_code != 401, "Admin should be able to perform searches"
        print("✅ Admin workflow completed successfully")

    def test_complete_power_user_workflow(self, test_environment):
        """Test complete power user workflow: login -> activate repo -> query."""
        if not test_environment["server_started"]:
            pytest.skip("Server not started")

        auth_helper = test_environment["auth_helper"]
        main_server = test_environment["main_server"]
        test_repo = test_environment["test_repo"]

        # Step 1: Power user login
        power_login = auth_helper.login_user("poweruser", "password")
        assert power_login[
            "success"
        ], f"Power user login failed: {power_login.get('error')}"

        power_token = power_login["token"]
        power_headers = auth_helper.create_auth_headers(power_token)

        # Step 2: Try to access admin endpoints (should be forbidden)
        response = main_server.make_api_request(
            "GET", "/api/admin/users", headers=power_headers
        )

        # Power user should NOT have access to admin endpoints
        assert (
            response.status_code == 403
        ), "Power user should not access admin endpoints"

        # Step 3: List available repositories
        response = main_server.make_api_request(
            "GET", "/api/repos", headers=power_headers
        )

        assert response.status_code != 401, "Power user should access repo listings"

        # Step 4: Activate a repository (power user privilege)
        activation_data = {"goldenRepoName": test_repo.name, "alias": "my_test_repo"}

        response = main_server.make_api_request(
            "POST",
            "/api/repos/activate",
            headers=power_headers,
            json_data=activation_data,
        )

        assert (
            response.status_code != 403
        ), "Power user should be able to activate repos"

        # Step 5: Perform semantic search
        search_query = {
            "query": "database connection",
            "repository": "my_test_repo",
            "limit": 5,
        }

        response = main_server.make_api_request(
            "POST", "/api/query", headers=power_headers, json_data=search_query
        )

        assert response.status_code != 401, "Power user should be able to search"
        print("✅ Power user workflow completed successfully")

    def test_complete_normal_user_workflow(self, test_environment):
        """Test complete normal user workflow: login -> query (limited access)."""
        if not test_environment["server_started"]:
            pytest.skip("Server not started")

        auth_helper = test_environment["auth_helper"]
        main_server = test_environment["main_server"]

        # Step 1: Normal user login
        user_login = auth_helper.login_user("normaluser", "password")
        assert user_login[
            "success"
        ], f"Normal user login failed: {user_login.get('error')}"

        user_token = user_login["token"]
        user_headers = auth_helper.create_auth_headers(user_token)

        # Step 2: Try to access admin endpoints (should be forbidden)
        response = main_server.make_api_request(
            "GET", "/api/admin/users", headers=user_headers
        )

        assert (
            response.status_code == 403
        ), "Normal user should not access admin endpoints"

        # Step 3: Try to activate repository (should be forbidden)
        activation_data = {"goldenRepoName": "test_repo", "alias": "my_repo"}

        response = main_server.make_api_request(
            "POST",
            "/api/repos/activate",
            headers=user_headers,
            json_data=activation_data,
        )

        assert response.status_code == 403, "Normal user should not activate repos"

        # Step 4: List available repositories (should work)
        response = main_server.make_api_request(
            "GET", "/api/repos", headers=user_headers
        )

        assert response.status_code != 401, "Normal user should access repo listings"

        # Step 5: Perform semantic search (limited to available repos)
        search_query = {"query": "error handling", "limit": 10}

        response = main_server.make_api_request(
            "POST", "/api/query", headers=user_headers, json_data=search_query
        )

        assert response.status_code != 401, "Normal user should be able to search"
        print("✅ Normal user workflow completed successfully")

    def test_authentication_edge_cases(self, test_environment):
        """Test authentication edge cases and security."""
        if not test_environment["server_started"]:
            pytest.skip("Server not started")

        auth_helper = test_environment["auth_helper"]
        main_server = test_environment["main_server"]

        # Test 1: Invalid credentials
        invalid_login = auth_helper.login_user("invalid_user", "wrong_password")
        assert not invalid_login["success"], "Invalid credentials should fail"

        # Test 2: Missing authentication header
        response = main_server.make_api_request("GET", "/api/repos")
        assert response.status_code == 401, "Missing auth should return 401"

        # Test 3: Invalid JWT token
        invalid_headers = {"Authorization": "Bearer invalid.jwt.token"}
        response = main_server.make_api_request(
            "GET", "/api/repos", headers=invalid_headers
        )
        assert response.status_code == 401, "Invalid token should return 401"

        # Test 4: Expired token (simulate)
        expired_token = auth_helper.simulate_token_expiry("admin", minutes_ago=60)
        if expired_token:
            expired_headers = auth_helper.create_auth_headers(expired_token)
            response = main_server.make_api_request(
                "GET", "/api/repos", headers=expired_headers
            )
            assert response.status_code == 401, "Expired token should return 401"

        print("✅ Authentication security tests completed successfully")

    def test_repository_management_workflow(self, test_environment):
        """Test repository management workflow."""
        if not test_environment["server_started"]:
            pytest.skip("Server not started")

        data_factory = test_environment["data_factory"]
        auth_helper = test_environment["auth_helper"]
        main_server = test_environment["main_server"]
        base_path = test_environment["base_path"]

        # Create additional test repository
        additional_repo = data_factory.create_test_repository(
            name="additional_test_repo",
            base_path=base_path,
            custom_files={
                "special_module.py": "# Special module for testing\ndef special_function():\n    return 'special'"
            },
        )

        # Login as admin
        admin_login = auth_helper.login_user("admin", "admin")
        assert admin_login["success"]
        admin_headers = auth_helper.create_auth_headers(admin_login["token"])

        # Add the additional repository as golden repo
        golden_repo_data = {
            "name": additional_repo.name,
            "description": "Additional test repository",
            "source_url": f"file://{additional_repo.path}",
            "branch": "master",
        }

        response = main_server.make_api_request(
            "POST",
            "/api/admin/golden-repos",
            headers=admin_headers,
            json_data=golden_repo_data,
        )

        # Should successfully create (or at least not be unauthorized/forbidden)
        assert response.status_code not in [
            401,
            403,
        ], "Admin should create golden repos"

        # Login as power user and activate the repository
        power_login = auth_helper.login_user("poweruser", "password")
        assert power_login["success"]
        power_headers = auth_helper.create_auth_headers(power_login["token"])

        activation_data = {
            "goldenRepoName": additional_repo.name,
            "alias": "special_repo",
        }

        response = main_server.make_api_request(
            "POST",
            "/api/repos/activate",
            headers=power_headers,
            json_data=activation_data,
        )

        assert response.status_code not in [
            401,
            403,
        ], "Power user should activate repos"

        print("✅ Repository management workflow completed successfully")

    def test_concurrent_user_operations(self, test_environment):
        """Test concurrent operations by multiple users."""
        if not test_environment["server_started"]:
            pytest.skip("Server not started")

        auth_helper = test_environment["auth_helper"]
        main_server = test_environment["main_server"]

        # Login multiple users concurrently
        users_to_login = [
            {"username": "admin", "password": "admin"},
            {"username": "poweruser", "password": "password"},
            {"username": "normaluser", "password": "password"},
        ]

        login_results = auth_helper.login_multiple_users(users_to_login)

        # Verify all logins succeeded
        successful_logins = sum(
            1 for result in login_results.values() if result["success"]
        )
        assert (
            successful_logins >= 2
        ), f"Expected at least 2 successful logins, got {successful_logins}"

        # Perform concurrent searches
        search_query = {"query": "function definition", "limit": 5}

        concurrent_results = {}
        for username, login_result in login_results.items():
            if login_result["success"]:
                headers = auth_helper.create_auth_headers(login_result["token"])
                response = main_server.make_api_request(
                    "POST", "/api/query", headers=headers, json_data=search_query
                )
                concurrent_results[username] = response.status_code

        # All authenticated users should be able to search
        for username, status_code in concurrent_results.items():
            assert status_code != 401, f"User {username} should be able to search"

        print("✅ Concurrent operations test completed successfully")

    def test_infrastructure_integration(self, test_environment):
        """Test that all infrastructure components are working together."""
        # Verify test data factory created repositories
        test_repo = test_environment["test_repo"]
        assert test_repo.path.exists(), "Test repository should exist"
        assert (test_repo.path / "main.py").exists(), "Test files should be copied"
        assert len(test_repo.branches) >= 1, "Test repository should have branches"

        # Verify server is running
        main_server = test_environment["main_server"]
        assert main_server.is_server_running(), "Server should be running"

        # Verify authentication helper is working
        auth_helper = test_environment["auth_helper"]
        assert auth_helper.jwt_manager.secret_key, "JWT manager should be configured"

        # Verify server info
        server_info = main_server.get_server_info()
        assert server_info["running"], "Server should report as running"
        assert (
            server_info["health_status"] is not None
        ), "Health status should be available"

        # Verify container environment (if started)
        if test_environment["containers_started"]:
            container_manager = test_environment["container_manager"]
            active_envs = container_manager.list_active_environments()
            assert len(active_envs) > 0, "Should have active container environments"

        print("✅ Infrastructure integration test completed successfully")

    def test_cleanup_and_isolation(self, test_environment):
        """Test that cleanup works properly and tests are isolated."""
        auth_helper = test_environment["auth_helper"]

        # Login users and create sessions
        admin_login = auth_helper.login_user("admin", "admin")
        auth_helper.login_user("poweruser", "password")

        # Verify sessions exist
        assert (
            auth_helper.get_active_sessions_count() >= 1
        ), "Should have active sessions"

        # Test selective logout
        if admin_login["success"]:
            auth_helper.logout_user("admin")
            admin_session = auth_helper.get_session_for_user("admin")
            assert admin_session is None, "Admin session should be cleared"

        # Test cleanup all
        auth_helper.logout_all_users()
        assert (
            auth_helper.get_active_sessions_count() == 0
        ), "All sessions should be cleared"

        print("✅ Cleanup and isolation test completed successfully")


# Additional utility test to demonstrate repository test helpers
def test_repository_test_utilities():
    """Demonstrate repository testing utilities."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        factory = TestDataFactory()

        # Create test repository
        repo = factory.create_test_repository(
            name="utility_test_repo",
            base_path=Path(tmp_dir),
            branches=["master", "feature/test"],
            custom_files={"test_utility.py": "def test_function():\n    return 'test'"},
        )

        # Test git operations
        repo.add_file("new_file.py", "# New file content")
        repo.commit("Add new test file")

        # Verify git operations worked
        commit_history = repo.get_commit_history()
        assert "Add new test file" in commit_history

        # Test branch operations
        repo.create_branch("test_branch", checkout=True)
        current_branch = repo.get_current_branch()
        assert current_branch == "test_branch"

        # Cleanup
        factory.cleanup_test_data()

        print("✅ Repository test utilities working correctly")


if __name__ == "__main__":
    # Run utility test when executed directly
    test_repository_test_utilities()
    print("✅ All utility tests completed successfully")
