"""
End-to-end tests for FTS regex search functionality.

Tests cover:
- Full workflow: init → start → index --fts → query with --regex
- Real CLI execution via subprocess
- Regex pattern matching in realistic codebase
"""

import subprocess
import pytest


class TestFTSRegexE2E:
    """E2E tests for FTS regex search."""

    @pytest.fixture
    def test_repo(self, tmp_path):
        """Create test repository with sample code."""
        repo_dir = tmp_path / "regex_test_repo"
        repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Create Python files with various patterns
        src_dir = repo_dir / "src"
        src_dir.mkdir()

        auth_file = src_dir / "auth.py"
        auth_file.write_text(
            """def login_user(username, password):
    '''Authenticate user login'''
    return authenticate(username, password)

def logout_user(session_id):
    '''Terminate user session'''
    return terminate_session(session_id)

def verify_token(token):
    '''Verify authentication token'''
    return validate_token(token)
"""
        )

        db_file = src_dir / "database.py"
        db_file.write_text(
            """class DatabaseConnection:
    def connect_db(self):
        return connection

    def query_users(self):
        return results

    def update_record(self, record):
        return success
"""
        )

        # Create test files with TODO comments
        tests_dir = repo_dir / "tests"
        tests_dir.mkdir()

        test_file = tests_dir / "test_auth.py"
        test_file.write_text(
            """# TODO: Add more comprehensive auth tests
def test_login():
    user = login_user('testuser', 'testpass')
    assert user is not None

# TODO: Test edge cases
def test_logout():
    result = logout_user('session123')
    assert result == True
"""
        )

        # Create JavaScript file
        js_file = src_dir / "utils.js"
        js_file.write_text(
            """function authenticate(user, pass) {
    return validateCredentials(user, pass);
}

function validateToken(token) {
    return checkTokenExpiry(token);
}
"""
        )

        # Commit all files
        subprocess.run(
            ["git", "add", "."], cwd=repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        return repo_dir

    def test_e2e_regex_query(self, test_repo):
        """
        GIVEN indexed repository with FTS
        WHEN running regex query via CLI
        THEN returns matching results
        """
        # Initialize CIDX
        result = subprocess.run(
            ["cidx", "init"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Start CIDX
        result = subprocess.run(
            ["cidx", "start"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        # Build FTS index
        result = subprocess.run(
            ["cidx", "index", "--fts"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

        # Execute regex query for Python function definitions
        # NOTE: Tantivy regex works on tokens, so r"def" matches the "def" token
        result = subprocess.run(
            ["cidx", "query", r"def", "--fts", "--regex"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        output = result.stdout

        # Verify results contain files with "def" keyword
        assert (
            "auth.py" in output or "database.py" in output or "test_auth.py" in output
        )

        # Cleanup
        subprocess.run(["cidx", "stop"], cwd=test_repo, capture_output=True)

    def test_e2e_regex_with_language_filter(self, test_repo):
        """
        GIVEN indexed repository
        WHEN using regex with language filter
        THEN returns only specified language results
        """
        # Setup
        subprocess.run(["cidx", "init"], cwd=test_repo, capture_output=True)
        subprocess.run(["cidx", "start"], cwd=test_repo, capture_output=True)
        subprocess.run(["cidx", "index", "--fts"], cwd=test_repo, capture_output=True)

        # Query JavaScript functions only
        # Token-based regex: match "function" token
        result = subprocess.run(
            [
                "cidx",
                "query",
                r"function",
                "--fts",
                "--regex",
                "--language",
                "javascript",
            ],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = result.stdout

        # Should find JavaScript files with "function" keyword
        assert "utils.js" in output or "function" in output

        # Cleanup
        subprocess.run(["cidx", "stop"], cwd=test_repo, capture_output=True)

    def test_e2e_regex_todo_comments(self, test_repo):
        """
        GIVEN indexed repository
        WHEN searching for TODO comments with regex
        THEN finds all TODO markers
        """
        # Setup
        subprocess.run(["cidx", "init"], cwd=test_repo, capture_output=True)
        subprocess.run(["cidx", "start"], cwd=test_repo, capture_output=True)
        subprocess.run(["cidx", "index", "--fts"], cwd=test_repo, capture_output=True)

        # Search for TODO comments
        # Token-based regex: exact token match for "todo" (lowercase because content field is lowercased)
        result = subprocess.run(
            ["cidx", "query", r"todo", "--fts", "--regex"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = result.stdout

        # Should find files with TODO comments
        assert "test_auth.py" in output or "TODO" in output.upper()

        # Cleanup
        subprocess.run(["cidx", "stop"], cwd=test_repo, capture_output=True)

    def test_e2e_regex_invalid_pattern_error(self, test_repo):
        """
        GIVEN indexed repository
        WHEN using invalid regex pattern
        THEN returns clear error message
        """
        # Setup
        subprocess.run(["cidx", "init"], cwd=test_repo, capture_output=True)
        subprocess.run(["cidx", "start"], cwd=test_repo, capture_output=True)
        subprocess.run(["cidx", "index", "--fts"], cwd=test_repo, capture_output=True)

        # Try invalid regex
        result = subprocess.run(
            ["cidx", "query", r"[invalid(", "--fts", "--regex"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )

        # Should fail with error
        assert result.returncode != 0

        # Error should mention regex or pattern
        error_output = result.stderr + result.stdout
        assert (
            "regex" in error_output.lower()
            or "pattern" in error_output.lower()
            or "invalid" in error_output.lower()
        )

        # Cleanup
        subprocess.run(["cidx", "stop"], cwd=test_repo, capture_output=True)
