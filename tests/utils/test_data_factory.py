"""
Test data factory for creating consistent test environments.

This module provides factories for creating test repositories, users, and other
test data needed for comprehensive E2E testing of the multi-user CIDX server.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
import logging

from passlib.context import CryptContext

logger = logging.getLogger(__name__)


@dataclass
class TestUser:
    """Test user data structure."""

    __test__ = False

    username: str
    role: str
    email: str
    password_hash: str
    created_at: datetime
    is_active: bool = True
    user_id: Optional[str] = None

    def __post_init__(self):
        """Initialize password context after creation."""
        self._pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def verify_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return self._pwd_context.verify(password, self.password_hash)

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for API requests."""
        return {
            "username": self.username,
            "role": self.role,
            "email": self.email,
            "password_hash": self.password_hash,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "user_id": self.user_id,
        }


@dataclass
class TestRepository:
    """Test repository data structure."""

    __test__ = False

    name: str
    path: Path
    description: str
    branches: List[str]
    primary_language: str = "python"

    def add_file(self, filename: str, content: str = "") -> None:
        """Add a file to the repository."""
        file_path = self.path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if content:
            file_path.write_text(content)

        # Git add the file
        subprocess.run(
            ["git", "add", filename], cwd=self.path, check=True, capture_output=True
        )

    def commit(self, message: str) -> str:
        """Commit changes to repository."""
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.path,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def create_branch(self, branch_name: str, checkout: bool = True) -> None:
        """Create and optionally checkout a new branch."""
        subprocess.run(
            ["git", "branch", branch_name],
            cwd=self.path,
            check=True,
            capture_output=True,
        )

        if checkout:
            subprocess.run(
                ["git", "checkout", branch_name],
                cwd=self.path,
                check=True,
                capture_output=True,
            )

        if branch_name not in self.branches:
            self.branches.append(branch_name)

    def checkout_branch(self, branch_name: str) -> None:
        """Checkout existing branch."""
        subprocess.run(
            ["git", "checkout", branch_name],
            cwd=self.path,
            check=True,
            capture_output=True,
        )

    def get_commit_history(self) -> str:
        """Get git commit history."""
        result = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def get_current_branch(self) -> str:
        """Get current branch name."""
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def to_dict(self) -> Dict[str, Any]:
        """Convert repository to dictionary for API requests."""
        return {
            "name": self.name,
            "path": str(self.path),
            "description": self.description,
            "branches": self.branches,
            "primary_language": self.primary_language,
        }


class TestDataFactory:
    """Factory for creating test data and environments."""

    __test__ = False

    def __init__(self):
        """Initialize test data factory."""
        self._pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self._created_repositories: List[TestRepository] = []
        self._created_users: List[TestUser] = []
        self.logger = logging.getLogger(f"{__name__}.TestDataFactory")

    def create_test_repository(
        self,
        name: str,
        base_path: Path,
        branches: Optional[List[str]] = None,
        description: Optional[str] = None,
        custom_files: Optional[Dict[str, str]] = None,
    ) -> TestRepository:
        """
        Create a test repository with sample code and git history.

        Args:
            name: Repository name
            base_path: Base directory where to create the repository
            branches: List of branches to create (defaults to ["master"])
            description: Repository description
            custom_files: Additional files to create {filename: content}

        Returns:
            TestRepository instance
        """
        if branches is None:
            branches = ["master"]

        if description is None:
            description = f"Test repository '{name}' for CIDX server testing"

        # Create repository directory
        repo_path = base_path / name
        repo_path.mkdir(parents=True, exist_ok=True)

        # Copy fixture repository content
        self._copy_fixture_repository(repo_path)

        # Initialize git repository
        self._initialize_git_repository(repo_path, name)

        # Add custom files if provided
        if custom_files:
            for filename, content in custom_files.items():
                file_path = repo_path / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)

        # Create additional branches if requested
        actual_branches = ["master"]  # Start with master
        if len(branches) > 1:
            for branch_name in branches[1:]:
                try:
                    subprocess.run(
                        ["git", "branch", branch_name],
                        cwd=repo_path,
                        check=True,
                        capture_output=True,
                    )
                    actual_branches.append(branch_name)
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Failed to create branch {branch_name}: {e}")

        # Create test repository object
        test_repo = TestRepository(
            name=name,
            path=repo_path,
            description=description,
            branches=actual_branches,
            primary_language="python",
        )

        # Track created repository
        self._created_repositories.append(test_repo)

        self.logger.info(f"Created test repository: {name} at {repo_path}")
        return test_repo

    def create_test_user(
        self,
        username: str,
        role: str,
        email: Optional[str] = None,
        password: str = "password",
        is_active: bool = True,
    ) -> TestUser:
        """
        Create a test user with hashed password.

        Args:
            username: Username
            role: User role (admin, power_user, normal_user)
            email: Email address (optional)
            password: Plain text password (defaults to "password")
            is_active: Whether user is active

        Returns:
            TestUser instance
        """
        if email is None:
            email = f"{username}@example.com"

        # Hash password
        password_hash = self._pwd_context.hash(password)

        # Create user object
        test_user = TestUser(
            username=username,
            role=role,
            email=email,
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc),
            is_active=is_active,
        )

        # Track created user
        self._created_users.append(test_user)

        self.logger.info(f"Created test user: {username} ({role})")
        return test_user

    def create_test_users(self, user_specs: List[Dict[str, Any]]) -> List[TestUser]:
        """
        Create multiple test users from specifications.

        Args:
            user_specs: List of user specification dictionaries

        Returns:
            List of TestUser instances
        """
        users = []

        for spec in user_specs:
            user = self.create_test_user(
                username=spec["username"],
                role=spec["role"],
                email=spec.get("email"),
                password=spec.get("password", "password"),
                is_active=spec.get("is_active", True),
            )
            users.append(user)

        return users

    def get_default_test_users(self) -> List[TestUser]:
        """
        Get a set of default test users for common testing scenarios.

        Returns:
            List of default test users
        """
        return self.create_test_users(
            [
                {"username": "admin", "role": "admin"},
                {"username": "poweruser", "role": "power_user"},
                {"username": "normaluser", "role": "normal_user"},
                {"username": "testuser", "role": "normal_user"},
            ]
        )

    def get_fixture_repository_path(self) -> Path:
        """
        Get the path to the fixture repository.

        Returns:
            Path to the cidx-test-repo fixture
        """
        # Find the fixture repository relative to this file
        current_file = Path(__file__)
        tests_dir = current_file.parent.parent
        fixture_path = tests_dir / "fixtures" / "cidx-test-repo"

        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture repository not found at: {fixture_path}")

        return fixture_path

    def cleanup_test_data(self) -> None:
        """Clean up all created test data."""
        # Clean up repositories
        for repo in self._created_repositories:
            if repo.path.exists():
                try:
                    shutil.rmtree(repo.path)
                    self.logger.info(f"Cleaned up repository: {repo.name}")
                except Exception as e:
                    self.logger.warning(
                        f"Failed to clean up repository {repo.name}: {e}"
                    )

        # Clear tracking lists
        self._created_repositories.clear()
        self._created_users.clear()

        self.logger.info("Test data cleanup completed")

    def _copy_fixture_repository(self, target_path: Path) -> Path:
        """
        Copy the fixture repository to target path.

        Args:
            target_path: Target directory path

        Returns:
            Path to copied repository
        """
        fixture_path = self.get_fixture_repository_path()

        # Ensure target directory exists
        target_path.mkdir(parents=True, exist_ok=True)

        # Copy all files except .git directory
        for item in fixture_path.iterdir():
            if item.name == ".git":
                continue  # Skip .git directory - we'll initialize fresh

            target_item = target_path / item.name

            if item.is_dir():
                shutil.copytree(item, target_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target_item)

        return target_path

    def _initialize_git_repository(self, repo_path: Path, repo_name: str) -> None:
        """
        Initialize git repository with initial commit.

        Args:
            repo_path: Path to repository directory
            repo_name: Repository name for commit messages
        """
        try:
            # Initialize git repository
            subprocess.run(
                ["git", "init"], cwd=repo_path, check=True, capture_output=True
            )

            # Configure git user for this repository
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            subprocess.run(
                ["git", "config", "user.email", "test@cidx.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Add all files
            subprocess.run(
                ["git", "add", "."], cwd=repo_path, check=True, capture_output=True
            )

            # Initial commit
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"Initial commit for test repository: {repo_name}",
                ],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            self.logger.debug(f"Initialized git repository at: {repo_path}")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to initialize git repository: {e}")
            raise

    def create_golden_repository_data(self, repo_name: str) -> Dict[str, Any]:
        """
        Create golden repository metadata for testing.

        Args:
            repo_name: Name of the golden repository

        Returns:
            Golden repository metadata dictionary
        """
        return {
            "name": repo_name,
            "description": f"Golden test repository: {repo_name}",
            "source_type": "git",
            "source_url": f"https://github.com/test/{repo_name}.git",
            "branch": "master",
            "indexing_enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "metadata": {
                "primary_language": "python",
                "estimated_files": 50,
                "estimated_size_mb": 2.5,
                "tags": ["test", "python", "api"],
            },
        }

    def create_search_query_data(
        self, user_id: str, repository_id: str = None
    ) -> Dict[str, Any]:
        """
        Create sample search query data for testing.

        Args:
            user_id: User identifier
            repository_id: Repository identifier (optional)

        Returns:
            Search query data dictionary
        """
        queries = [
            "authentication function",
            "database connection",
            "error handling",
            "API endpoint",
            "user management",
            "search functionality",
            "configuration settings",
            "logging utility",
        ]

        import random

        query = random.choice(queries)

        return {
            "user_id": user_id,
            "repository_id": repository_id,
            "query": query,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results_count": random.randint(1, 10),
            "execution_time_ms": random.randint(50, 500),
        }

    def create_test_search_results(
        self, query: str, count: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Create realistic test search results for testing purposes.

        Args:
            query: Search query string
            count: Number of results to generate

        Returns:
            List of test search results
        """
        results = []

        for i in range(count):
            results.append(
                {
                    "file_path": f"src/{query.replace(' ', '_')}_module_{i}.py",
                    "function_name": f"{query.replace(' ', '_')}_function_{i}",
                    "line_number": (i + 1) * 10,
                    "code_snippet": f"def {query.replace(' ', '_')}_function_{i}():\n    return '{query} implementation'",
                    "relevance_score": 1.0 - (i * 0.1),
                    "description": f"Implementation of {query} - result {i + 1}",
                    "language": "python",
                    "metadata": {
                        "class_name": f"{query.replace(' ', '_').title()}Handler",
                        "docstring": f"Handles {query} operations",
                        "complexity": "medium",
                    },
                }
            )

        return results

    @property
    def created_repositories(self) -> List[TestRepository]:
        """Get list of created repositories."""
        return self._created_repositories.copy()

    @property
    def created_users(self) -> List[TestUser]:
        """Get list of created users."""
        return self._created_users.copy()


# Convenience functions for common test data creation
def create_test_environment(
    base_path: Path, env_name: str = "test_env"
) -> Dict[str, Any]:
    """
    Create a complete test environment with repositories and users.

    Args:
        base_path: Base path for creating test data
        env_name: Environment name

    Returns:
        Dictionary containing all created test data
    """
    factory = TestDataFactory()

    # Create test repositories
    main_repo = factory.create_test_repository(
        name=f"{env_name}_main_repo",
        base_path=base_path,
        branches=["master", "feature/auth", "feature/search"],
    )

    secondary_repo = factory.create_test_repository(
        name=f"{env_name}_secondary_repo", base_path=base_path
    )

    # Create test users
    users = factory.get_default_test_users()

    return {
        "factory": factory,
        "repositories": [main_repo, secondary_repo],
        "users": users,
        "admin_user": next(u for u in users if u.role == "admin"),
        "normal_user": next(u for u in users if u.role == "normal_user"),
        "power_user": next(u for u in users if u.role == "power_user"),
    }


def cleanup_test_environment(test_env: Dict[str, Any]) -> None:
    """
    Clean up a test environment.

    Args:
        test_env: Test environment dictionary from create_test_environment
    """
    factory = test_env.get("factory")
    if factory:
        factory.cleanup_test_data()
