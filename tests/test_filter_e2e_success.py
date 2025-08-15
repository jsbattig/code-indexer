"""E2E tests to confirm that filtering works correctly after fixes."""

import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional
import pytest
import logging

logger = logging.getLogger(__name__)


@pytest.mark.e2e
class TestFilteringE2ESuccess:
    """End-to-end tests that confirm filtering functionality works correctly."""

    def setup_method(self):
        """Set up test repository with sample files."""
        # Create temporary directory for test repository
        self.test_dir = Path(tempfile.mkdtemp(prefix="filter_e2e_success_"))

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

        # Create directory structure
        (self.test_dir / "backend" / "services").mkdir(parents=True)
        (self.test_dir / "frontend" / "components").mkdir(parents=True)
        (self.test_dir / "src" / "main" / "java" / "com" / "test").mkdir(parents=True)
        (self.test_dir / "src" / "main" / "groovy" / "com" / "test").mkdir(parents=True)
        (self.test_dir / "src" / "test" / "kotlin" / "com" / "test").mkdir(parents=True)

        # Create test files with meaningful content
        test_files = {
            "backend/services/DatabaseConfig.java": """
package com.test.backend.services;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;

public class DatabaseConfig {
    @Bean
    public DataSource getDataSource() {
        return new HikariDataSource();
    }
}
""",
            "frontend/components/LoginComponent.js": """
import React from 'react';

const LoginComponent = () => {
    const handleLogin = () => {
        console.log('Login attempt');
    };
    
    return <div>Login Form</div>;
};

export default LoginComponent;
""",
            "src/main/java/com/test/UserDAO.java": """
package com.test;

import java.util.Optional;

public interface UserDAO {
    Optional<User> findByEmail(String email);
    void save(User user);
    void delete(Long id);
}
""",
            "src/main/java/com/test/AuthenticationService.java": """
package com.test;

public class AuthenticationService {
    private UserDAO userDAO;
    
    public boolean authenticate(String email, String password) {
        return userDAO.findByEmail(email).isPresent();
    }
}
""",
            "src/main/groovy/com/test/AuthController.groovy": """
package com.test

class AuthController {
    def authService
    
    def login() {
        return [success: true]
    }
    
    def logout() {
        return [success: true] 
    }
}
""",
            "src/main/groovy/com/test/UserDAOTest.groovy": """
package com.test

import spock.lang.Specification

class UserDAOTest extends Specification {
    def "should find user by email"() {
        when:
        def user = userDAO.findByEmail("test@example.com")
        
        then:
        user.isPresent()
    }
}
""",
            "src/test/kotlin/com/test/AuthServiceTest.kt": """
package com.test

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*

class AuthServiceTest {
    @Test
    fun testAuthentication() {
        val service = AuthenticationService()
        assertTrue(service.authenticate("test@test.com", "password"))
    }
}
""",
        }

        # Write test files
        for file_path, content in test_files.items():
            full_path = self.test_dir / file_path
            full_path.write_text(content.strip())

        # Commit files
        subprocess.run(["git", "add", "."], cwd=self.test_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=self.test_dir, check=True
        )

        # Initialize code-indexer
        subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=self.test_dir,
            check=True,
            capture_output=True,
        )

        # Start services
        subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=self.test_dir,
            check=True,
            capture_output=True,
        )

        # Index the repository
        subprocess.run(
            ["cidx", "index", "--clear"],
            cwd=self.test_dir,
            check=True,
            capture_output=True,
        )

        logger.info(f"Test repository created at {self.test_dir}")

    def teardown_method(self):
        """Clean up test repository."""
        try:
            # Stop services
            subprocess.run(["cidx", "stop"], cwd=self.test_dir, capture_output=True)
        except Exception:
            pass

        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run_query(
        self,
        query: str,
        language: Optional[str] = None,
        path: Optional[str] = None,
        limit: int = 5,
    ):
        """Run a cidx query command and return the result."""
        cmd = ["cidx", "query", query, "--quiet"]
        if language:
            cmd.extend(["--language", language])
        if path:
            cmd.extend(["--path", path])
        cmd.extend(["--limit", str(limit)])

        return subprocess.run(cmd, cwd=self.test_dir, capture_output=True, text=True)

    def test_java_language_filtering_works(self):
        """Test that Java language filtering works correctly."""
        # Search for Java files specifically
        result = self._run_query("findByEmail", language="java", limit=10)
        assert result.returncode == 0

        # Should find Java files but not Groovy or Kotlin files
        assert "UserDAO.java" in result.stdout, "Should find Java DAO file"
        assert (
            "AuthController.groovy" not in result.stdout
        ), "Should not find Groovy files when filtering by Java"

    def test_groovy_language_filtering_works(self):
        """Test that Groovy language filtering works correctly."""
        # Search for Groovy files specifically
        result = self._run_query("AuthController", language="groovy", limit=10)
        assert result.returncode == 0

        # Should find Groovy files but not Java or Kotlin files
        assert (
            "AuthController.groovy" in result.stdout
        ), "Should find Groovy controller file"
        assert (
            "AuthenticationService.java" not in result.stdout
        ), "Should not find Java files when filtering by Groovy"

    def test_kotlin_language_filtering_works(self):
        """Test that Kotlin language filtering works correctly."""
        # Search for Kotlin files specifically
        result = self._run_query("AuthServiceTest", language="kotlin", limit=10)
        assert result.returncode == 0

        # Should find Kotlin files but not Java or Groovy files
        assert "AuthServiceTest.kt" in result.stdout, "Should find Kotlin test file"
        assert (
            "UserDAO.java" not in result.stdout
        ), "Should not find Java files when filtering by Kotlin"

    def test_path_filtering_works(self):
        """Test that path filtering works correctly."""
        # Search for files in backend directory
        result = self._run_query("DataSource", path="*/backend/*", limit=10)
        assert result.returncode == 0
        assert (
            "DatabaseConfig.java" in result.stdout
        ), "Should find files in backend directory"

        # Verify it doesn't find files outside backend
        assert (
            "LoginComponent.js" not in result.stdout
        ), "Should not find frontend files when filtering by backend path"

    def test_frontend_path_filtering_works(self):
        """Test that frontend path filtering works correctly."""
        # Search for files in frontend directory
        result = self._run_query("LoginComponent", path="*/frontend/*", limit=10)
        assert result.returncode == 0
        assert (
            "LoginComponent.js" in result.stdout
        ), "Should find files in frontend directory"

        # Verify it doesn't find files outside frontend
        assert (
            "DatabaseConfig.java" not in result.stdout
        ), "Should not find backend files when filtering by frontend path"

    def test_combined_language_and_path_filtering_works(self):
        """Test that combined language and path filtering works correctly."""
        # Search for Java files in src directory
        result = self._run_query(
            "findByEmail", language="java", path="*/src/*", limit=10
        )
        assert result.returncode == 0
        assert (
            "UserDAO.java" in result.stdout
        ), "Should find Java files in src directory"

        # Should not find Groovy files even though they're in src
        assert (
            "AuthController.groovy" not in result.stdout
        ), "Should not find Groovy files when filtering by Java language"

        # Should not find Java files outside src
        assert (
            "DatabaseConfig.java" not in result.stdout
        ), "Should not find Java files outside src when filtering by path"

    def test_nonexistent_language_filtering(self):
        """Test filtering by non-existent language returns no results."""
        result = self._run_query("test", language="rust", limit=10)
        assert result.returncode == 0
        assert (
            result.stdout.strip() == ""
        ), "Should return no results for non-existent language"

    def test_nonexistent_path_filtering(self):
        """Test filtering by non-existent path returns no results."""
        result = self._run_query("test", path="*/nonexistent/*", limit=10)
        assert result.returncode == 0
        assert (
            result.stdout.strip() == ""
        ), "Should return no results for non-existent path"
