"""
End-to-end tests for language and path filtering functionality.

These tests are designed to FAIL and expose the filtering bugs.
They test against a real repository with known file types and paths.

These tests are EXCLUDED from CI/GitHub Actions as they are e2e tests that require:
- Real repository setup
- Real embedding provider (Voyage AI)
- Full indexing and search workflow
"""

import pytest
import subprocess
import tempfile
import shutil
from pathlib import Path


# Mark as e2e test to exclude from fast CI
pytestmark = pytest.mark.e2e


class TestFilteringE2EFailing:
    """End-to-end tests that expose filtering bugs."""

    def setup_method(self):
        """Set up test repository with known files for filtering tests."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = Path.cwd()

        # Create test repository structure with known file types
        self._create_test_repository()

        # Initialize code-indexer
        self._initialize_code_indexer()

        # Index the test repository
        self._index_repository()

    def teardown_method(self):
        """Clean up test repository."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_repository(self):
        """Create a test repository with files that expose filtering bugs."""
        # Create directory structure
        (self.test_dir / "src" / "main" / "java" / "com" / "test").mkdir(parents=True)
        (self.test_dir / "src" / "main" / "groovy" / "com" / "test").mkdir(parents=True)
        (self.test_dir / "src" / "test" / "java" / "com" / "test").mkdir(parents=True)
        (self.test_dir / "src" / "test" / "kotlin" / "com" / "test").mkdir(parents=True)
        (self.test_dir / "backend" / "services").mkdir(parents=True)
        (self.test_dir / "frontend" / "components").mkdir(parents=True)

        # Create Java files
        java_dao = """package com.test.dao;

public interface UserDAO {
    User findByEmail(String email) throws DataAccessException;
    void saveUser(User user) throws DataAccessException;
    void deleteUser(Long userId) throws DataAccessException;
}"""
        (
            self.test_dir / "src" / "main" / "java" / "com" / "test" / "UserDAO.java"
        ).write_text(java_dao)

        java_service = """package com.test.service;

public class AuthenticationService {
    public boolean authenticateUser(String email, String password) {
        // Authentication logic here
        return validateCredentials(email, password);
    }
    
    private boolean validateCredentials(String email, String password) {
        return email != null && password != null;
    }
}"""
        (
            self.test_dir
            / "src"
            / "main"
            / "java"
            / "com"
            / "test"
            / "AuthenticationService.java"
        ).write_text(java_service)

        # Create Groovy files (these should be detected as groovy but will be marked as unknown)
        groovy_test = """package com.test

class UserDAOTest {
    void testFindByEmail() {
        // Test logic
        assert userDAO.findByEmail("test@example.com") != null
    }
    
    void testAuthenticationFlow() {
        // Authentication test
        def result = authService.authenticateUser("user", "pass")
        assert result == true
    }
}"""
        (
            self.test_dir
            / "src"
            / "main"
            / "groovy"
            / "com"
            / "test"
            / "UserDAOTest.groovy"
        ).write_text(groovy_test)

        groovy_controller = """package com.test.controller

class AuthController {
    def login() {
        // Login endpoint
        return "redirect:/dashboard"
    }
    
    def logout() {
        // Logout endpoint  
        return "redirect:/login"
    }
}"""
        (
            self.test_dir
            / "src"
            / "main"
            / "groovy"
            / "com"
            / "test"
            / "AuthController.groovy"
        ).write_text(groovy_controller)

        # Create Kotlin files
        kotlin_test = """package com.test

class AuthenticationServiceTest {
    fun testAuthenticateUser() {
        // Kotlin authentication test
        val result = authService.authenticateUser("test@example.com", "password")
        assert(result)
    }
}"""
        (
            self.test_dir
            / "src"
            / "test"
            / "kotlin"
            / "com"
            / "test"
            / "AuthServiceTest.kt"
        ).write_text(kotlin_test)

        # Create files in backend directory
        backend_config = """package backend.config;

public class DatabaseConfig {
    public DataSource dataSource() {
        // Database configuration
        return new DataSource();
    }
}"""
        (self.test_dir / "backend" / "services" / "DatabaseConfig.java").write_text(
            backend_config
        )

        # Create files in frontend directory
        frontend_component = """class LoginComponent {
    constructor() {
        this.authService = new AuthenticationService();
    }
    
    login(email, password) {
        return this.authService.authenticate(email, password);
    }
}"""
        (self.test_dir / "frontend" / "components" / "LoginComponent.js").write_text(
            frontend_component
        )

        # Initialize git repository
        subprocess.run(
            ["git", "init"], cwd=self.test_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.test_dir,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=self.test_dir, check=True
        )
        subprocess.run(["git", "add", "."], cwd=self.test_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=self.test_dir, check=True
        )

    def _initialize_code_indexer(self):
        """Initialize code-indexer in test repository."""
        result = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=self.test_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Failed to initialize: {result.stderr}"

        # Start services
        result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=self.test_dir,
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert result.returncode == 0, f"Failed to start services: {result.stderr}"

    def _index_repository(self):
        """Index the test repository."""
        result = subprocess.run(
            ["cidx", "index"],
            cwd=self.test_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, f"Failed to index: {result.stderr}"

    def _run_query(self, query: str, **kwargs) -> subprocess.CompletedProcess:
        """Run a cidx query command."""
        cmd = ["cidx", "query", query, "--quiet"]

        # Add optional parameters
        if "language" in kwargs:
            cmd.extend(["--language", kwargs["language"]])
        if "path" in kwargs:
            cmd.extend(["--path", kwargs["path"]])
        if "limit" in kwargs:
            cmd.extend(["--limit", str(kwargs["limit"])])

        return subprocess.run(
            cmd, cwd=self.test_dir, capture_output=True, text=True, timeout=30
        )

    def test_java_language_filtering_fails(self):
        """Test that Java language filtering should work but currently fails."""
        # Search without language filter - should find Java files
        result_all = self._run_query("authenticateUser", limit=10)
        assert result_all.returncode == 0
        assert (
            "AuthenticationService.java" in result_all.stdout
        ), "Should find Java authentication file"

        # Search with Java language filter - CURRENTLY FAILS but should work
        result_java = self._run_query("authenticateUser", language="java", limit=10)
        assert result_java.returncode == 0

        # This assertion WILL FAIL, exposing the bug
        assert (
            "AuthenticationService.java" in result_java.stdout
        ), "EXPECTED FAILURE: Java language filtering should find Java files but doesn't"

    def test_groovy_language_filtering_fails(self):
        """Test that Groovy language filtering fails due to unknown language detection."""
        # Search without language filter - should find Groovy files
        result_all = self._run_query("login", limit=10)
        assert result_all.returncode == 0
        assert (
            "AuthController.groovy" in result_all.stdout
        ), "Should find Groovy controller file"

        # Search with Groovy language filter - FAILS because groovy files are marked as 'unknown'
        result_groovy = self._run_query("login", language="groovy", limit=10)
        assert result_groovy.returncode == 0

        # This assertion WILL FAIL, exposing the language detection bug
        assert (
            "AuthController.groovy" in result_groovy.stdout
        ), "EXPECTED FAILURE: Groovy files are marked as 'unknown' instead of 'groovy'"

    def test_kotlin_language_filtering_fails(self):
        """Test that Kotlin language filtering may fail."""
        # Search without language filter - should find Kotlin files
        result_all = self._run_query("authenticateUser", limit=10)
        assert result_all.returncode == 0
        assert "AuthServiceTest.kt" in result_all.stdout, "Should find Kotlin test file"

        # Search with Kotlin language filter
        result_kotlin = self._run_query("authenticateUser", language="kotlin", limit=10)
        assert result_kotlin.returncode == 0

        # This may fail depending on language detection
        assert (
            "AuthServiceTest.kt" in result_kotlin.stdout
        ), "EXPECTED FAILURE: Kotlin language filtering may not work"

    def test_path_filtering_fails(self):
        """Test that path filtering should work but currently fails."""
        # Search without path filter - should find files in backend
        result_all = self._run_query("DataSource", limit=10)
        assert result_all.returncode == 0
        assert (
            "DatabaseConfig.java" in result_all.stdout
        ), "Should find backend config file"

        # Search with backend path filter - CURRENTLY FAILS but should work
        result_backend = self._run_query("DataSource", path="*/backend/*", limit=10)
        assert result_backend.returncode == 0

        # This assertion WILL FAIL, exposing the path filtering bug
        assert (
            "DatabaseConfig.java" in result_backend.stdout
        ), "EXPECTED FAILURE: Path filtering should find files in backend directory but doesn't"

    def test_frontend_path_filtering_fails(self):
        """Test that frontend path filtering fails."""
        # Search without path filter - should find files in frontend
        result_all = self._run_query("LoginComponent", limit=10)
        assert result_all.returncode == 0
        assert (
            "LoginComponent.js" in result_all.stdout
        ), "Should find frontend component file"

        # Search with frontend path filter - CURRENTLY FAILS
        result_frontend = self._run_query(
            "LoginComponent", path="*/frontend/*", limit=10
        )
        assert result_frontend.returncode == 0

        # This assertion WILL FAIL, exposing the path filtering bug
        assert (
            "LoginComponent.js" in result_frontend.stdout
        ), "EXPECTED FAILURE: Path filtering should find files in frontend directory but doesn't"

    def test_combined_language_and_path_filtering_fails(self):
        """Test that combined language and path filtering fails."""
        # Search without filters - should find Java files in src directory
        result_all = self._run_query("findByEmail", limit=10)
        assert result_all.returncode == 0
        assert "UserDAO.java" in result_all.stdout, "Should find Java DAO file"

        # Search with both Java language and src path filter - CURRENTLY FAILS
        result_combined = self._run_query(
            "findByEmail", language="java", path="*/src/*", limit=10
        )
        assert result_combined.returncode == 0

        # This assertion WILL FAIL, exposing the combined filtering bug
        assert (
            "UserDAO.java" in result_combined.stdout
        ), "EXPECTED FAILURE: Combined language and path filtering should work but doesn't"

    def test_nonexistent_language_filtering(self):
        """Test filtering by non-existent language returns no results."""
        result = self._run_query("authentication", language="python", limit=10)
        assert result.returncode == 0

        # This should correctly return no results (there are no Python files)
        assert (
            result.stdout.strip() == ""
        ), "Should return no results for non-existent language"

    def test_nonexistent_path_filtering(self):
        """Test filtering by non-existent path returns no results."""
        result = self._run_query("authentication", path="*/nonexistent/*", limit=10)
        assert result.returncode == 0

        # This should correctly return no results
        assert (
            result.stdout.strip() == ""
        ), "Should return no results for non-existent path"


if __name__ == "__main__":
    # Allow running individual tests for debugging
    pytest.main([__file__, "-v", "--tb=short"])
