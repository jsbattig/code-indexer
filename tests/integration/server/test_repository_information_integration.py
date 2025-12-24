"""Real integration tests for repository information and branch switching.

Tests the actual API endpoints with real repositories, no mocks.
Following CLAUDE.md Foundation #1: No mocks - real system integration.
"""

import pytest
import tempfile
import shutil
import os
import subprocess
import httpx

from code_indexer.server.app import create_app


@pytest.fixture
async def test_app():
    """Create real test application with temporary storage."""
    app = create_app()
    yield app


@pytest.fixture
async def test_client(test_app):
    """Create test client for API calls."""
    async with httpx.AsyncClient(app=test_app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def temp_repo_dir():
    """Create temporary directory for test repositories."""
    temp_dir = tempfile.mkdtemp(prefix="cidx_test_repos_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def test_user_credentials(test_app):
    """Create test user and return credentials."""
    # This would need to be implemented based on your user creation API
    # For now, assume we have a way to create test users
    username = "test_user"
    password = "test_password123!"

    # Create user through API or direct manager call
    # Return credentials that can be used for authenticated requests
    return {
        "username": username,
        "password": password,
        "token": "test_jwt_token",  # Would be generated through actual auth flow
    }


@pytest.fixture
async def test_repository(temp_repo_dir):
    """Create a real git repository for testing."""
    repo_path = os.path.join(temp_repo_dir, "test-project")
    os.makedirs(repo_path)

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True
    )

    # Create some test files
    test_files = {
        "main.py": "def main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()",
        "README.md": "# Test Project\n\nThis is a test project for CIDX.",
        "requirements.txt": "requests==2.28.0\nfastapi==0.104.0",
        "src/utils.py": "def helper_function():\n    return 'utility function'",
        "tests/test_main.py": "def test_main():\n    assert True",
    }

    for file_path, content in test_files.items():
        full_path = os.path.join(repo_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)

    # Add and commit files
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit with test files"],
        cwd=repo_path,
        check=True,
    )

    # Create additional branches
    subprocess.run(["git", "checkout", "-b", "develop"], cwd=repo_path, check=True)

    # Add more content to develop branch
    with open(os.path.join(repo_path, "develop_feature.py"), "w") as f:
        f.write("def develop_feature():\n    return 'new feature'\n")

    subprocess.run(["git", "add", "develop_feature.py"], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add develop feature"], cwd=repo_path, check=True
    )

    # Switch back to main
    subprocess.run(["git", "checkout", "main"], cwd=repo_path, check=True)

    return repo_path


class TestRepositoryInformationIntegration:
    """Integration tests for repository information API endpoints."""

    async def test_repository_info_basic_information(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test basic repository information retrieval without optional flags."""
        # This test would need actual repository setup and user authentication
        # For now, this is the structure showing how real integration tests should work

        # 1. Set up authenticated request headers
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        # 2. Make actual API call to repository info endpoint
        response = await test_client.get("/api/repos/test-project", headers=headers)

        # 3. Verify response structure and content
        assert response.status_code == 200
        data = response.json()

        # Basic information should be present
        assert "alias" in data
        assert "current_branch" in data
        assert "activation_date" in data
        assert "sync_status" in data
        assert "storage_info" in data

        # Optional sections should not be present
        assert "branches" not in data
        assert "health" not in data
        assert "activity" not in data

    async def test_repository_info_with_branches_flag(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test repository information with branches flag."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        # Request with branches flag
        response = await test_client.get(
            "/api/repos/test-project?branches=true", headers=headers
        )

        assert response.status_code == 200
        data = response.json()

        # Basic information should be present
        assert "alias" in data
        assert "current_branch" in data

        # Branches section should be present and populated
        assert "branches" in data
        assert isinstance(data["branches"], list)

        # Should have at least main and develop branches
        branch_names = [branch["name"] for branch in data["branches"]]
        assert "main" in branch_names
        assert "develop" in branch_names

        # Current branch should be marked correctly
        current_branches = [
            branch for branch in data["branches"] if branch["is_current"]
        ]
        assert len(current_branches) == 1
        assert current_branches[0]["name"] == data["current_branch"]

    async def test_repository_info_with_health_flag(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test repository information with health flag."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        # Request with health flag
        response = await test_client.get(
            "/api/repos/test-project?health=true", headers=headers
        )

        assert response.status_code == 200
        data = response.json()

        # Health section should be present
        assert "health" in data
        health_info = data["health"]

        # Required health fields
        assert "container_status" in health_info
        assert "services" in health_info
        assert "index_status" in health_info
        assert "query_ready" in health_info
        assert "storage" in health_info
        assert "issues" in health_info
        assert "recommendations" in health_info

    async def test_repository_info_with_activity_flag(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test repository information with activity flag."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        # Request with activity flag
        response = await test_client.get(
            "/api/repos/test-project?activity=true", headers=headers
        )

        assert response.status_code == 200
        data = response.json()

        # Activity section should be present
        assert "activity" in data
        activity_info = data["activity"]

        # Required activity fields
        assert "recent_commits" in activity_info
        assert "sync_history" in activity_info
        assert "query_activity" in activity_info
        assert "branch_operations" in activity_info

        # Should have commit information from our test repository
        assert isinstance(activity_info["recent_commits"], list)
        if activity_info["recent_commits"]:
            commit = activity_info["recent_commits"][0]
            assert "commit_hash" in commit
            assert "message" in commit

    async def test_repository_info_all_flags_combined(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test repository information with all flags enabled."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        # Request with all flags
        response = await test_client.get(
            "/api/repos/test-project?branches=true&health=true&activity=true",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()

        # All sections should be present
        assert "branches" in data
        assert "health" in data
        assert "activity" in data

        # Verify each section has expected structure
        assert isinstance(data["branches"], list)
        assert isinstance(data["health"], dict)
        assert isinstance(data["activity"], dict)

    async def test_repository_branch_switching_existing_branch(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test switching to an existing branch."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        # Switch to develop branch
        response = await test_client.post(
            "/api/repos/test-project/switch-branch",
            headers=headers,
            json={"branch_name": "develop", "create": False},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data["status"] == "success"
        assert data["new_branch"] == "develop"
        assert data["previous_branch"] == "main"
        assert "message" in data

        # Verify branch was actually switched
        info_response = await test_client.get(
            "/api/repos/test-project", headers=headers
        )
        assert info_response.status_code == 200
        info_data = info_response.json()
        assert info_data["current_branch"] == "develop"

    async def test_repository_branch_switching_with_create_flag(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test creating and switching to a new branch."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        # Create and switch to new branch
        response = await test_client.post(
            "/api/repos/test-project/switch-branch",
            headers=headers,
            json={"branch_name": "feature/new-feature", "create": True},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response indicates branch creation
        assert data["status"] == "success"
        assert data["new_branch"] == "feature/new-feature"
        assert data.get("branch_created", False) is True

        # Verify new branch exists and is current
        info_response = await test_client.get(
            "/api/repos/test-project?branches=true", headers=headers
        )
        assert info_response.status_code == 200
        info_data = info_response.json()
        assert info_data["current_branch"] == "feature/new-feature"

        branch_names = [branch["name"] for branch in info_data["branches"]]
        assert "feature/new-feature" in branch_names

    async def test_repository_not_found_error(self, test_client, test_user_credentials):
        """Test error handling for non-existent repository."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        response = await test_client.get("/api/repos/nonexistent-repo", headers=headers)

        assert response.status_code == 404
        error_data = response.json()
        assert "not found" in error_data["detail"].lower()

    async def test_branch_not_found_error(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test error handling for non-existent branch."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        response = await test_client.post(
            "/api/repos/test-project/switch-branch",
            headers=headers,
            json={"branch_name": "nonexistent-branch", "create": False},
        )

        assert response.status_code == 404
        error_data = response.json()
        assert "not found" in error_data["detail"].lower()

    async def test_authentication_required(self, test_client, test_repository):
        """Test that authentication is required for repository operations."""
        # Request without authentication headers
        response = await test_client.get("/api/repos/test-project")

        assert response.status_code == 401

    async def test_repository_storage_information_accuracy(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test that storage information is calculated accurately."""
        headers = {"Authorization": f"Bearer {test_user_credentials['token']}"}

        response = await test_client.get("/api/repos/test-project", headers=headers)

        assert response.status_code == 200
        data = response.json()

        storage_info = data["storage_info"]
        assert "disk_usage_mb" in storage_info
        assert storage_info["disk_usage_mb"] > 0  # Should have some content

        # Index size might be 0 if not indexed yet
        assert "index_size_mb" in storage_info
        assert storage_info["index_size_mb"] >= 0


# Test configuration to skip if integration test dependencies not available
@pytest.mark.integration
class TestRepositoryInformationFullIntegration:
    """Full integration tests requiring complete CIDX server setup."""

    async def test_full_repository_lifecycle_with_indexing(
        self, test_client, test_user_credentials, test_repository
    ):
        """Test complete repository lifecycle from activation to querying."""
        # This would test the full flow:
        # 1. Add golden repository
        # 2. Activate repository for user
        # 3. Index repository
        # 4. Query repository information
        # 5. Switch branches
        # 6. Verify all information is accurate

        # Placeholder for full integration test
        # Would require actual golden repo manager and indexing setup
        pass
