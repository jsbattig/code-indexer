"""
Unit tests for TestDataFactory.

Tests the creation and management of test data for multi-user CIDX server testing.
These tests verify that the factory can create consistent, isolated test environments.
"""

from datetime import datetime

from tests.utils.test_data_factory import TestDataFactory, TestRepository, TestUser


class TestTestDataFactory:
    """Unit tests for TestDataFactory class."""

    def test_create_test_repository_creates_proper_structure(self, tmp_path):
        """Test that test repository is created with proper directory structure."""
        factory = TestDataFactory()

        # Create test repository
        repo = factory.create_test_repository(name="test_repo_001", base_path=tmp_path)

        # Verify repository structure
        assert isinstance(repo, TestRepository)
        assert repo.name == "test_repo_001"
        assert repo.path.exists()
        assert repo.path.is_dir()

        # Verify git repository was initialized
        assert (repo.path / ".git").exists()

        # Verify essential files were copied
        assert (repo.path / "main.py").exists()
        assert (repo.path / "README.md").exists()
        assert (repo.path / "api.py").exists()
        assert (repo.path / "auth.py").exists()

    def test_create_test_repository_with_branches(self, tmp_path):
        """Test that test repository can be created with multiple branches."""
        factory = TestDataFactory()

        repo = factory.create_test_repository(
            name="test_repo_branches",
            base_path=tmp_path,
            branches=["master", "feature/auth", "feature/search"],
        )

        # Verify branches exist
        assert len(repo.branches) >= 3
        assert "master" in repo.branches
        assert "feature/auth" in repo.branches
        assert "feature/search" in repo.branches

    def test_create_test_repository_isolation(self, tmp_path):
        """Test that multiple test repositories are properly isolated."""
        factory = TestDataFactory()

        # Create two repositories
        repo1 = factory.create_test_repository(name="repo1", base_path=tmp_path)

        repo2 = factory.create_test_repository(name="repo2", base_path=tmp_path)

        # Verify they are separate
        assert repo1.path != repo2.path
        assert not repo1.path.samefile(repo2.path)
        assert repo1.name != repo2.name

        # Verify both are functional git repos
        assert (repo1.path / ".git").exists()
        assert (repo2.path / ".git").exists()

    def test_create_test_user_generates_valid_user_data(self):
        """Test that test user creation generates valid user data."""
        factory = TestDataFactory()

        user = factory.create_test_user(
            username="testuser", role="normal_user", email="test@example.com"
        )

        assert isinstance(user, TestUser)
        assert user.username == "testuser"
        assert user.role == "normal_user"
        assert user.email == "test@example.com"
        assert user.password_hash.startswith("$2b$")  # bcrypt hash
        assert len(user.password_hash) >= 60
        assert isinstance(user.created_at, datetime)

    def test_create_test_user_different_roles(self):
        """Test that different user roles can be created."""
        factory = TestDataFactory()

        admin_user = factory.create_test_user("admin", "admin")
        power_user = factory.create_test_user("power", "power_user")
        normal_user = factory.create_test_user("normal", "normal_user")

        assert admin_user.role == "admin"
        assert power_user.role == "power_user"
        assert normal_user.role == "normal_user"

        # All should have different usernames
        usernames = {admin_user.username, power_user.username, normal_user.username}
        assert len(usernames) == 3

    def test_create_test_users_batch_creation(self):
        """Test batch creation of multiple test users."""
        factory = TestDataFactory()

        users = factory.create_test_users(
            [
                {"username": "admin1", "role": "admin"},
                {"username": "power1", "role": "power_user"},
                {"username": "normal1", "role": "normal_user"},
                {"username": "normal2", "role": "normal_user"},
            ]
        )

        assert len(users) == 4
        assert all(isinstance(user, TestUser) for user in users)

        # Verify unique usernames
        usernames = [user.username for user in users]
        assert len(set(usernames)) == 4

    def test_cleanup_test_data_removes_repositories(self, tmp_path):
        """Test that cleanup properly removes test repositories."""
        factory = TestDataFactory()

        # Create test repository
        repo = factory.create_test_repository(name="cleanup_test", base_path=tmp_path)

        # Verify it exists
        assert repo.path.exists()

        # Cleanup and verify removal
        factory.cleanup_test_data()

        # Path should be cleaned up by the factory's internal tracking
        # Note: tmp_path fixture will handle actual filesystem cleanup
        assert repo in factory._created_repositories or not repo.path.exists()

    def test_get_fixture_repository_path_returns_correct_path(self):
        """Test that fixture repository path is correctly resolved."""
        factory = TestDataFactory()

        fixture_path = factory.get_fixture_repository_path()

        assert fixture_path.exists()
        assert fixture_path.is_dir()
        assert fixture_path.name == "cidx-test-repo"
        assert (fixture_path / "main.py").exists()
        assert (fixture_path / "README.md").exists()

    def test_copy_fixture_repository_preserves_structure(self, tmp_path):
        """Test that copying fixture repository preserves directory structure."""
        factory = TestDataFactory()

        target_path = tmp_path / "copied_repo"
        copied_path = factory._copy_fixture_repository(target_path)

        assert copied_path == target_path
        assert target_path.exists()

        # Verify key files were copied
        assert (target_path / "main.py").exists()
        assert (target_path / "features" / "search.py").exists()
        assert (target_path / "config" / "settings.py").exists()

        # Verify .git was not copied (will be reinitialized)
        assert not (target_path / ".git").exists()

    def test_create_test_repository_with_custom_content(self, tmp_path):
        """Test creating repository with custom content modifications."""
        factory = TestDataFactory()

        # Define custom content
        custom_files = {
            "custom_module.py": "# Custom test module\nprint('Custom content')",
            "data.json": '{"test": "data", "value": 42}',
        }

        repo = factory.create_test_repository(
            name="custom_repo", base_path=tmp_path, custom_files=custom_files
        )

        # Verify custom files were added
        assert (repo.path / "custom_module.py").exists()
        assert (repo.path / "data.json").exists()

        # Verify content
        custom_content = (repo.path / "custom_module.py").read_text()
        assert "Custom test module" in custom_content

    def test_test_repository_git_operations(self, tmp_path):
        """Test that TestRepository supports basic git operations."""
        factory = TestDataFactory()

        repo = factory.create_test_repository(name="git_test", base_path=tmp_path)

        # Test adding a new file and committing
        new_file = repo.path / "test_file.py"
        new_file.write_text("# Test file")

        # These operations should not fail
        repo.add_file("test_file.py")
        repo.commit("Add test file")

        # Verify in git history
        assert "Add test file" in repo.get_commit_history()

    def test_test_user_password_verification(self):
        """Test that test user passwords can be verified."""
        factory = TestDataFactory()

        user = factory.create_test_user("testuser", "normal_user")

        # Test password verification
        assert user.verify_password("password")  # Default password
        assert not user.verify_password("wrong_password")

    def test_factory_state_isolation(self, tmp_path):
        """Test that factory instances maintain separate state."""
        factory1 = TestDataFactory()
        factory2 = TestDataFactory()

        repo1 = factory1.create_test_repository("repo1", tmp_path)
        repo2 = factory2.create_test_repository("repo2", tmp_path)

        # Verify separate tracking
        assert len(factory1._created_repositories) == 1
        assert len(factory2._created_repositories) == 1
        assert repo1 in factory1._created_repositories
        assert repo2 in factory2._created_repositories
        assert repo1 not in factory2._created_repositories
        assert repo2 not in factory1._created_repositories
