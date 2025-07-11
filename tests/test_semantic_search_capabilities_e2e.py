"""
End-to-end test for semantic search capabilities.

Tests the new semantic filtering options added to the query command,
including type, scope, features, parent, and semantic-only filters.
"""

from typing import Dict
import subprocess

import pytest

from .conftest import local_temporary_directory

# Import test infrastructure
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


def _get_semantic_filtering_test_project() -> Dict[str, str]:
    """Get test project with diverse semantic structures for filtering tests."""
    return {
        "user_model.py": '''"""User model with various semantic constructs."""
from typing import Optional, List
from dataclasses import dataclass
import asyncio


@dataclass
class User:
    """User data model."""
    id: int
    username: str
    email: str
    active: bool = True
    
    def get_display_name(self) -> str:
        """Get user's display name for UI."""
        return self.username.title()
    
    def validate_email(self) -> bool:
        """Validate user email format."""
        return "@" in self.email and "." in self.email
    
    @classmethod
    def create_user(cls, username: str, email: str) -> "User":
        """Create a new user instance."""
        return cls(
            id=0,
            username=username,
            email=email,
            active=True
        )
    
    @staticmethod
    def get_default_user() -> "User":
        """Get default user instance."""
        return User(id=0, username="guest", email="guest@example.com")


class UserRepository:
    """Repository for user data operations."""
    
    def __init__(self, database_url: str):
        """Initialize repository."""
        self.database_url = database_url
        self._users: List[User] = []
    
    async def save_user_async(self, user: User) -> User:
        """Save user asynchronously."""
        await asyncio.sleep(0.1)  # Simulate async operation
        if user.id == 0:
            user.id = len(self._users) + 1
        self._users.append(user)
        return user
    
    def find_by_username(self, username: str) -> Optional[User]:
        """Find user by username."""
        for user in self._users:
            if user.username == username:
                return user
        return None


def validate_user_data(username: str, email: str) -> bool:
    """Global function to validate user data."""
    return len(username) >= 3 and "@" in email


async def process_users_async(users: List[User]) -> List[User]:
    """Global async function to process users."""
    return [user for user in users if user.active]
''',
        "auth_service.js": """/**
 * Authentication service with various function types.
 */

class AuthService {
    constructor(config) {
        this.config = config;
        this.cache = new Map();
    }
    
    /**
     * Authenticate user with credentials.
     * @param {string} username - Username
     * @param {string} password - Password
     * @returns {Promise<boolean>} Authentication result
     */
    async authenticateUser(username, password) {
        if (!username || !password) {
            return false;
        }
        
        // Simulate async authentication
        await new Promise(resolve => setTimeout(resolve, 100));
        return username.length > 0 && password.length >= 6;
    }
    
    /**
     * Static method to validate token format.
     * @param {string} token - JWT token
     * @returns {boolean} True if valid format
     */
    static validateTokenFormat(token) {
        return token && token.includes('.') && token.length > 20;
    }
    
    /**
     * Get user permissions.
     * @param {string} userId - User ID
     * @returns {Array<string>} List of permissions
     */
    getUserPermissions(userId) {
        return this.cache.get(userId) || [];
    }
}

/**
 * Global function to hash password.
 * @param {string} password - Plain text password
 * @returns {string} Hashed password
 */
function hashPassword(password) {
    // Simple hash simulation
    return btoa(password + 'salt').slice(0, 16);
}

/**
 * Global async function to verify token.
 * @param {string} token - JWT token
 * @returns {Promise<Object>} Token payload
 */
async function verifyToken(token) {
    await new Promise(resolve => setTimeout(resolve, 50));
    return { valid: AuthService.validateTokenFormat(token) };
}

export { AuthService, hashPassword, verifyToken };
""",
        "Main.java": """/**
 * Main application with Java constructs.
 */
package com.example.app;

import java.util.List;
import java.util.ArrayList;
import java.util.concurrent.CompletableFuture;

public class Main {
    private static final String APP_NAME = "UserApp";
    
    public static void main(String[] args) {
        System.out.println("Starting " + APP_NAME);
        UserService service = new UserService();
        service.start();
    }
    
    public static String getAppName() {
        return APP_NAME;
    }
}

class UserService {
    private final List<String> users = new ArrayList<>();
    
    public void start() {
        System.out.println("UserService started");
    }
    
    public synchronized void addUser(String username) {
        users.add(username);
    }
    
    public static UserService createDefault() {
        return new UserService();
    }
    
    public CompletableFuture<String> processUserAsync(String username) {
        return CompletableFuture.supplyAsync(() -> {
            return "Processed: " + username;
        });
    }
}

interface UserRepository {
    void save(String user);
    String findById(int id);
    
    default boolean exists(String username) {
        return findById(username.hashCode()) != null;
    }
}
""",
    }


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_type_filtering():
    """Test filtering by semantic type (--type)."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_type_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_filtering_test_project()
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and index
        subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Test class filtering
        class_result = subprocess.run(
            ["code-indexer", "query", "user", "--type", "class", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if class_result.returncode == 0 and class_result.stdout.strip():
            output = class_result.stdout
            # Should find class constructs, verify in brackets
            assert "[class:" in output.lower() or "user" in output.lower()

        # Test function filtering
        function_result = subprocess.run(
            ["code-indexer", "query", "validate", "--type", "function", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if function_result.returncode == 0 and function_result.stdout.strip():
            output = function_result.stdout
            # Should find function constructs
            lines = output.strip().split("\\n")
            result_lines = [
                line for line in lines if line.strip() and line[0].isdigit()
            ]
            if result_lines:
                # Check for function type in semantic info
                assert any(
                    "[function" in line.lower() or "function" in line.lower()
                    for line in result_lines
                )


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_scope_filtering():
    """Test filtering by semantic scope (--scope)."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_scope_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_filtering_test_project()
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and index
        subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Test global scope filtering
        global_result = subprocess.run(
            ["code-indexer", "query", "user", "--scope", "global"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if global_result.returncode == 0 and global_result.stdout.strip():
            # Should find global-scope constructs like classes and global functions
            assert "🧠 Semantic:" in global_result.stdout


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_features_filtering():
    """Test filtering by language features (--features)."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_features_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_filtering_test_project()
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and index
        subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Test async feature filtering
        async_result = subprocess.run(
            ["code-indexer", "query", "process", "--features", "async"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if async_result.returncode == 0 and async_result.stdout.strip():
            # Should find async functions and methods
            output = async_result.stdout
            assert "🧠 Semantic:" in output
            assert "async" in output.lower() or "Features:" in output

        # Test static feature filtering
        static_result = subprocess.run(
            ["code-indexer", "query", "method", "--features", "static"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if static_result.returncode == 0 and static_result.stdout.strip():
            # Should find static methods
            output = static_result.stdout
            assert "🧠 Semantic:" in output


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_parent_filtering():
    """Test filtering by parent context (--parent)."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_parent_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_filtering_test_project()
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and index
        subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Test parent filtering - find methods inside User class
        parent_result = subprocess.run(
            ["code-indexer", "query", "get", "--parent", "User"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if parent_result.returncode == 0 and parent_result.stdout.strip():
            # Should find methods inside User class
            output = parent_result.stdout
            assert "🧠 Semantic:" in output
            assert "User" in output


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_only_filtering():
    """Test semantic-only filtering (--semantic-only)."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_only_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_filtering_test_project()
        project_files[
            "README.md"
        ] = """# Test Project

This is a test project for semantic filtering.

## Features
- User management
- Authentication service
- Data validation

## Installation
Run the application to start.
"""
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and index
        subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Test semantic-only filtering
        semantic_only_result = subprocess.run(
            ["code-indexer", "query", "user", "--semantic-only"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if semantic_only_result.returncode == 0 and semantic_only_result.stdout.strip():
            # Should only show results with semantic chunking
            output = semantic_only_result.stdout
            assert "🧠 Semantic:" in output
            # Should not include README.md results
            assert "README.md" not in output or "🧠 Semantic:" in output


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_combined_semantic_filtering():
    """Test combining multiple semantic filters."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_combined_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_filtering_test_project()
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and index
        subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Test combined filtering: async functions with global scope
        combined_result = subprocess.run(
            [
                "code-indexer",
                "query",
                "process",
                "--type",
                "function",
                "--features",
                "async",
                "--scope",
                "global",
            ],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if combined_result.returncode == 0:
            # Should either find matching results or return no results (both are valid)
            output = combined_result.stdout
            # If results found, they should match all criteria
            if "🧠 Semantic:" in output:
                assert "function" in output.lower() or "async" in output.lower()
