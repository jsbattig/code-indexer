"""
End-to-end test for semantic query display enhancement.

Tests that semantic information is properly shown in query output when using
AST-based semantic chunking. Verifies both quiet and verbose display modes.
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


def _get_semantic_test_project() -> Dict[str, str]:
    """Get test project files designed to test semantic display."""
    return {
        "models.py": '''"""User model definitions."""
from typing import Optional, List
from dataclasses import dataclass


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
            id=0,  # Will be set by database
            username=username,
            email=email,
            active=True
        )


class UserRepository:
    """Repository for user data operations."""
    
    def __init__(self, database_url: str):
        """Initialize repository with database connection."""
        self.database_url = database_url
        self._users: List[User] = []
    
    def save_user(self, user: User) -> User:
        """Save user to database."""
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
''',
        "services.py": '''"""Business logic services."""
from typing import List, Optional
from .models import User, UserRepository


class AuthenticationService:
    """Service for user authentication."""
    
    def __init__(self, user_repo: UserRepository):
        """Initialize with user repository."""
        self.user_repo = user_repo
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with credentials."""
        user = self.user_repo.find_by_username(username)
        if user and user.active:
            # In real implementation, verify password hash
            return user
        return None
    
    def register_user(self, username: str, email: str, password: str) -> User:
        """Register a new user."""
        new_user = User.create_user(username, email)
        return self.user_repo.save_user(new_user)


def validate_user_input(username: str, email: str) -> bool:
    """Validate user input for registration."""
    if not username or len(username) < 3:
        return False
    if not email or "@" not in email:
        return False
    return True
''',
        "utils.js": """/**
 * Utility functions for frontend.
 */

class StringUtils {
    /**
     * Format a username for display.
     * @param {string} username - The raw username
     * @returns {string} Formatted username
     */
    static formatUsername(username) {
        if (!username) return '';
        return username.charAt(0).toUpperCase() + username.slice(1).toLowerCase();
    }
    
    /**
     * Validate email format.
     * @param {string} email - Email to validate
     * @returns {boolean} True if email is valid
     */
    static isValidEmail(email) {
        const emailRegex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
        return emailRegex.test(email);
    }
}

/**
 * Generate a random ID.
 * @returns {string} Random ID string
 */
function generateId() {
    return Math.random().toString(36).substr(2, 9);
}

/**
 * Format a date for display.
 * @param {Date} date - Date to format
 * @returns {string} Formatted date string
 */
function formatDate(date) {
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

export { StringUtils, generateId, formatDate };
""",
        "Main.java": """/**
 * Main application class.
 */
package com.example.app;

import java.util.List;
import java.util.ArrayList;

public class Main {
    private static final String APP_NAME = "UserApp";
    private static final int DEFAULT_PORT = 8080;
    
    /**
     * Application entry point.
     * @param args Command line arguments
     */
    public static void main(String[] args) {
        System.out.println("Starting " + APP_NAME);
        
        UserService userService = new UserService();
        WebServer server = new WebServer(DEFAULT_PORT);
        
        server.start();
        System.out.println("Server started on port " + DEFAULT_PORT);
    }
    
    /**
     * Get application configuration.
     * @return Configuration object
     */
    public static Config getConfig() {
        return new Config(APP_NAME, DEFAULT_PORT);
    }
}

/**
 * Simple configuration class.
 */
class Config {
    private final String appName;
    private final int port;
    
    public Config(String appName, int port) {
        this.appName = appName;
        this.port = port;
    }
    
    public String getAppName() {
        return appName;
    }
    
    public int getPort() {
        return port;
    }
}
""",
    }


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_query_display_verbose_mode():
    """Test that semantic information is displayed in verbose query mode."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_display_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_test_project()
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize with semantic chunking enabled (default)
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Index the project
        index_result = subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Test semantic display with class query
        query_result = subprocess.run(
            ["code-indexer", "query", "User class model"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert query_result.returncode == 0, f"Query failed: {query_result.stderr}"

        output = query_result.stdout

        # Verify semantic information is displayed
        assert "🧠 Semantic:" in output, f"Semantic info not found in output: {output}"

        # Should show semantic type and name
        assert (
            "class" in output.lower() or "function" in output.lower()
        ), f"No semantic type found in output: {output}"

        # Should show signatures for methods/functions
        assert (
            "📝 Signature:" in output or "def " in output or "class " in output
        ), f"No signature information found in output: {output}"


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_query_display_quiet_mode():
    """Test that semantic information is displayed in quiet query mode."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_quiet_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_test_project()
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize with semantic chunking enabled (default)
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Index the project
        index_result = subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Test semantic display with method query in quiet mode
        query_result = subprocess.run(
            ["code-indexer", "query", "validate email method", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert query_result.returncode == 0, f"Query failed: {query_result.stderr}"

        output = query_result.stdout

        # In quiet mode, semantic info should appear in brackets after file path
        lines = output.strip().split("\\n")
        result_lines = [line for line in lines if line.strip() and line[0].isdigit()]

        assert len(result_lines) > 0, f"No query results found in output: {output}"

        # Check for semantic info in brackets format: [type: name] or [type]
        semantic_found = False
        for line in result_lines:
            if "[" in line and "]" in line:
                semantic_found = True
                # Should contain semantic type
                assert any(
                    sem_type in line.lower()
                    for sem_type in ["class", "method", "function"]
                ), f"No semantic type found in line: {line}"
                break

        assert semantic_found, f"No semantic info in brackets found in output: {output}"


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_display_different_languages():
    """Test semantic display works for different programming languages."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "semantic_multilang_test"
        test_dir.mkdir()

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom semantic test files
        project_files = _get_semantic_test_project()
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and start services
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0

        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert start_result.returncode == 0

        # Index the project
        index_result = subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0

        # Test JavaScript function query
        js_query_result = subprocess.run(
            ["code-indexer", "query", "formatUsername function"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if js_query_result.returncode == 0 and js_query_result.stdout.strip():
            js_output = js_query_result.stdout
            # Verify JavaScript semantic info is shown
            assert (
                "🧠 Semantic:" in js_output or "[" in js_output
            ), f"No semantic info for JavaScript: {js_output}"

        # Test Java class query
        java_query_result = subprocess.run(
            ["code-indexer", "query", "Main class application"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if java_query_result.returncode == 0 and java_query_result.stdout.strip():
            java_output = java_query_result.stdout
            # Verify Java semantic info is shown
            assert (
                "🧠 Semantic:" in java_output or "[" in java_output
            ), f"No semantic info for Java: {java_output}"


@pytest.mark.integration
@pytest.mark.voyage_ai
def test_fallback_display_for_text_chunks():
    """Test that non-semantic chunks still display properly."""
    with local_temporary_directory() as temp_dir:
        test_dir = temp_dir / "fallback_display_test"
        test_dir.mkdir()

        # Create project with text files (no semantic chunking)
        project_files = {
            "README.md": """# Test Project
            
This is a test project for validating query display.

## Features
- User authentication
- Data validation
- Configuration management

## Installation
1. Clone the repository
2. Install dependencies
3. Run the application
""",
            "config.yaml": """app:
  name: TestApp
  port: 8080
  debug: true

database:
  host: localhost
  port: 5432
  name: testdb
""",
        }

        # Create test project with inventory system
        create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

        # Add custom test files
        for filename, content in project_files.items():
            (test_dir / filename).write_text(content)

        # Initialize and start services
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0

        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert start_result.returncode == 0

        # Index the project
        index_result = subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0

        # Query for text content
        query_result = subprocess.run(
            ["code-indexer", "query", "authentication features"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert query_result.returncode == 0

        output = query_result.stdout

        # Should not show semantic information for text files
        assert (
            "🧠 Semantic:" not in output
        ), f"Unexpected semantic info for text files: {output}"

        # Should still show normal file and content information
        assert (
            "📄 File:" in output or "Found" in output
        ), f"No file information found: {output}"
