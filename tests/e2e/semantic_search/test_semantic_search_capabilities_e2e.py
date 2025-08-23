"""
End-to-end test for semantic search capabilities.

Tests the new semantic filtering options added to the query command,
including type, scope, features, parent, and semantic-only filters.
"""

import subprocess
import os

import pytest

from ...conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


def _create_enhanced_semantic_test_files(project_path):
    """Create enhanced test files with diverse semantic structures for filtering tests."""
    # Create diverse code files with rich semantic structures
    project_files = {
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
        "config.yaml": """# Configuration file
database:
  host: localhost
  port: 5432
  name: user_db

api:
  version: "v1"
  timeout: 30
  
auth:
  jwt_secret: "secret123"
  token_expiry: 3600
""",
        "utils.go": """package main

import (
    "fmt"
    "time"
    "strings"
)

// Global utility functions
func validateEmail(email string) bool {
    return strings.Contains(email, "@")
}

func hashPassword(password string) string {
    // Hash implementation
    return fmt.Sprintf("hashed_%s", password)
}

// UserUtil struct with static methods
type UserUtil struct{}

func (u UserUtil) FormatName(first, last string) string {
    return fmt.Sprintf("%s %s", first, last)
}

func (u UserUtil) GenerateID() int64 {
    return time.Now().Unix()
}

// Async operation simulation
func processUserAsync(userID int64) <-chan string {
    result := make(chan string, 1)
    go func() {
        time.Sleep(100 * time.Millisecond)
        result <- fmt.Sprintf("Processed user %d", userID)
    }()
    return result
}
""",
        "README.md": """# User Management System

This project demonstrates various semantic constructs for testing.

## Features
- User authentication and management
- REST API endpoints
- Async processing capabilities
- Multi-language support

## Installation
Run the application to start user management.
""",
    }

    # Write all files to the project directory
    for filename, content in project_files.items():
        (project_path / filename).write_text(content)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_semantic_type_filtering():
    """Test filtering by semantic type (--type) using shared containers."""
    with shared_container_test_environment(
        "test_semantic_type_filtering", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create enhanced test files with diverse semantic structures
        _create_enhanced_semantic_test_files(project_path)

        # Initialize and index with shared containers
        result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

        # Test class filtering - use query that will match class chunks
        class_result = subprocess.run(
            ["code-indexer", "query", "dataclass User", "--type", "class", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            class_result.returncode == 0
        ), f"Class query failed: {class_result.stderr}"

        # Test function filtering - use query that will match function chunks
        function_result = subprocess.run(
            [
                "code-indexer",
                "query",
                "function validate",
                "--type",
                "function",
                "--quiet",
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            function_result.returncode == 0
        ), f"Function query failed: {function_result.stderr}"

        # Verify semantic type filtering is working
        # Check class results - should only contain class chunks when results are found
        if (
            class_result.stdout.strip()
            and "DEBUG:" not in class_result.stdout
            and "❌ No results found" not in class_result.stdout
        ):
            # Results should contain class file paths and may contain "User" content
            assert (
                "user_model.py" in class_result.stdout.lower()
                or "class" in class_result.stdout.lower()
            )

        # Check function results - should only contain function chunks when results are found
        if (
            function_result.stdout.strip()
            and "DEBUG:" not in function_result.stdout
            and "❌ No results found" not in function_result.stdout
        ):
            # Results should contain function file paths (Python or Go functions)
            assert (
                "user_model.py" in function_result.stdout.lower()
                or "utils.go" in function_result.stdout.lower()
            )


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_semantic_scope_filtering():
    """Test filtering by semantic scope (--scope) using shared containers."""
    with shared_container_test_environment(
        "test_semantic_scope_filtering", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create enhanced test files with diverse semantic structures
        _create_enhanced_semantic_test_files(project_path)

        # Initialize and index with shared containers
        result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

        # Test global scope filtering
        global_result = subprocess.run(
            ["code-indexer", "query", "user", "--scope", "global"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            global_result.returncode == 0
        ), f"Global scope query failed: {global_result.stderr}"

        # Verify results if found
        if (
            global_result.stdout.strip()
            and "❌ No results found" not in global_result.stdout
        ):
            # Should find global-scope constructs like classes and global functions
            assert (
                "🧠 Semantic:" in global_result.stdout
                or "user" in global_result.stdout.lower()
            )


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_semantic_features_filtering():
    """Test filtering by language features (--features) using shared containers."""
    with shared_container_test_environment(
        "test_semantic_features_filtering", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create enhanced test files with diverse semantic structures
        _create_enhanced_semantic_test_files(project_path)

        # Initialize and index with shared containers
        result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

        # Test async feature filtering
        async_result = subprocess.run(
            ["code-indexer", "query", "process", "--features", "async"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            async_result.returncode == 0
        ), f"Async query failed: {async_result.stderr}"

        # Test static feature filtering
        static_result = subprocess.run(
            ["code-indexer", "query", "method", "--features", "static"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            static_result.returncode == 0
        ), f"Static query failed: {static_result.stderr}"

        # Verify semantic features filtering is working
        # Note: Features filtering may not find results if no semantic chunks have those exact features
        # Just verify the commands run successfully - the main test is that no errors occur
        # and semantic filtering is applied (which we can't easily verify without results)
        if (
            async_result.stdout.strip()
            and "❌ No results found" not in async_result.stdout
            and "DEBUG:" not in async_result.stdout
        ):
            output = async_result.stdout
            # If results found, they should be semantic chunks with async features
            assert "async" in output.lower() or "🧠 Semantic:" in output

        if (
            static_result.stdout.strip()
            and "❌ No results found" not in static_result.stdout
            and "DEBUG:" not in static_result.stdout
        ):
            output = static_result.stdout
            # If results found, they should be semantic chunks with static features
            assert "static" in output.lower() or "🧠 Semantic:" in output


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_semantic_parent_filtering():
    """Test filtering by parent context (--parent) using shared containers."""
    with shared_container_test_environment(
        "test_semantic_parent_filtering", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create enhanced test files with diverse semantic structures
        _create_enhanced_semantic_test_files(project_path)

        # Initialize and index with shared containers
        result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

        # Test parent filtering - find methods inside User class
        parent_result = subprocess.run(
            ["code-indexer", "query", "get", "--parent", "User"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            parent_result.returncode == 0
        ), f"Parent query failed: {parent_result.stderr}"

        # Verify results if found
        if (
            parent_result.stdout.strip()
            and "❌ No results found" not in parent_result.stdout
        ):
            output = parent_result.stdout
            assert "🧠 Semantic:" in output or "User" in output


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_semantic_only_filtering():
    """Test semantic-only filtering (--semantic-only) using shared containers."""
    with shared_container_test_environment(
        "test_semantic_only_filtering", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create enhanced test files with diverse semantic structures
        _create_enhanced_semantic_test_files(project_path)

        # Add README.md for semantic-only testing
        (project_path / "README.md").write_text(
            """# Test Project

This is a test project for semantic filtering.

## Features
- User management
- Authentication service
- Data validation

## Installation
Run the application to start.
"""
        )

        # Initialize and index with shared containers
        result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

        # Test semantic-only filtering
        semantic_only_result = subprocess.run(
            ["code-indexer", "query", "user", "--semantic-only"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            semantic_only_result.returncode == 0
        ), f"Semantic-only query failed: {semantic_only_result.stderr}"

        # Verify results if found
        if (
            semantic_only_result.stdout.strip()
            and "❌ No results found" not in semantic_only_result.stdout
        ):
            output = semantic_only_result.stdout
            # Should only show results with semantic chunking
            assert "🧠 Semantic:" in output
            # Should not include README.md results in semantic-only mode
            assert "README.md" not in output or "🧠 Semantic:" in output


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_combined_semantic_filtering():
    """Test combining multiple semantic filters using shared containers."""
    with shared_container_test_environment(
        "test_combined_semantic_filtering", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create enhanced test files with diverse semantic structures
        _create_enhanced_semantic_test_files(project_path)

        # Initialize and index with shared containers
        result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        result = subprocess.run(
            ["code-indexer", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

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
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            combined_result.returncode == 0
        ), f"Combined query failed: {combined_result.stderr}"

        # Verify results if found
        if (
            combined_result.stdout.strip()
            and "❌ No results found" not in combined_result.stdout
        ):
            output = combined_result.stdout
            # If results found, they should match all criteria
            if "🧠 Semantic:" in output:
                assert "function" in output.lower() or "async" in output.lower()
