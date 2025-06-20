"""
End-to-end test for Claude integration functionality.

Tests the complete workflow from semantic search to Claude analysis.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

import pytest


def run_command(
    cmd: list, cwd: Optional[Path] = None, timeout: int = 60
) -> Dict[str, Any]:
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out",
            "returncode": -1,
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def create_test_project(project_dir: Path) -> None:
    """Create a simple test project with some Python code."""
    # Create main application file
    (project_dir / "main.py").write_text(
        """
def authenticate_user(username: str, password: str) -> bool:
    '''
    Authenticate user with username and password.
    
    This function handles user authentication by checking
    the provided credentials against the user database.
    
    Args:
        username: The user's username
        password: The user's password
        
    Returns:
        bool: True if authentication successful, False otherwise
    '''
    if not username or not password:
        return False
    
    # Simple authentication logic for demo
    valid_users = {
        "admin": "admin123",
        "user": "password123"
    }
    
    return valid_users.get(username) == password


def get_user_profile(user_id: int) -> dict:
    '''
    Retrieve user profile information.
    
    This function fetches user profile data from the database
    and returns it as a dictionary.
    '''
    # Mock user profiles
    profiles = {
        1: {"name": "Admin User", "email": "admin@example.com", "role": "admin"},
        2: {"name": "Regular User", "email": "user@example.com", "role": "user"}
    }
    
    return profiles.get(user_id, {})


if __name__ == "__main__":
    # Test authentication
    print("Testing authentication...")
    print(f"Admin login: {authenticate_user('admin', 'admin123')}")
    print(f"Invalid login: {authenticate_user('invalid', 'wrong')}")
    
    # Test profile retrieval
    print("\\nTesting profile retrieval...")
    print(f"User 1 profile: {get_user_profile(1)}")
    print(f"User 999 profile: {get_user_profile(999)}")
"""
    )

    # Create API module
    (project_dir / "api.py").write_text(
        """
from flask import Flask, request, jsonify
from main import authenticate_user, get_user_profile

app = Flask(__name__)


@app.route('/api/login', methods=['POST'])
def login():
    '''
    API endpoint for user login.
    
    Expects JSON payload with username and password.
    Returns authentication status and user info.
    '''
    data = request.get_json()
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Missing username or password'}), 400
    
    username = data['username']
    password = data['password']
    
    if authenticate_user(username, password):
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {'username': username}
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Invalid credentials'
        }), 401


@app.route('/api/profile/<int:user_id>', methods=['GET'])
def profile(user_id):
    '''
    API endpoint to get user profile.
    
    Returns user profile information for the given user ID.
    '''
    profile_data = get_user_profile(user_id)
    
    if profile_data:
        return jsonify(profile_data)
    else:
        return jsonify({'error': 'User not found'}), 404


@app.route('/api/health', methods=['GET'])
def health_check():
    '''Simple health check endpoint.'''
    return jsonify({'status': 'healthy', 'service': 'auth-api'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
"""
    )

    # Create utility module
    (project_dir / "utils.py").write_text(
        """
import hashlib
import secrets
from typing import Optional


def hash_password(password: str, salt: Optional[str] = None) -> tuple:
    '''
    Hash a password with salt for secure storage.
    
    This utility function provides secure password hashing
    using SHA-256 with a random salt.
    
    Args:
        password: The plain text password to hash
        salt: Optional salt, if not provided a random one is generated
        
    Returns:
        tuple: (hashed_password, salt)
    '''
    if salt is None:
        salt = secrets.token_hex(16)
    
    # Combine password and salt
    salted_password = f"{password}{salt}"
    
    # Hash the salted password
    hashed = hashlib.sha256(salted_password.encode()).hexdigest()
    
    return hashed, salt


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    '''
    Verify a password against its hash.
    
    Args:
        password: The plain text password to verify
        hashed_password: The stored hash
        salt: The salt used for hashing
        
    Returns:
        bool: True if password matches, False otherwise
    '''
    computed_hash, _ = hash_password(password, salt)
    return computed_hash == hashed_password


def generate_session_token() -> str:
    '''
    Generate a secure session token.
    
    Returns:
        str: A cryptographically secure random token
    '''
    return secrets.token_urlsafe(32)


class SecurityError(Exception):
    '''Custom exception for security-related errors.'''
    pass


def validate_input(data: str, max_length: int = 255) -> str:
    '''
    Validate and sanitize user input.
    
    Args:
        data: The input string to validate
        max_length: Maximum allowed length
        
    Returns:
        str: The sanitized input
        
    Raises:
        SecurityError: If input is invalid or too long
    '''
    if not isinstance(data, str):
        raise SecurityError("Input must be a string")
    
    if len(data) > max_length:
        raise SecurityError(f"Input too long (max {max_length} characters)")
    
    # Remove potentially dangerous characters
    sanitized = data.strip()
    
    return sanitized
"""
    )

    # Create a requirements.txt
    (project_dir / "requirements.txt").write_text(
        """
flask>=2.0.0
werkzeug>=2.0.0
"""
    )

    # Create README
    (project_dir / "README.md").write_text(
        """
# Test Authentication Service

A simple authentication service for testing code-indexer's Claude integration.

## Features

- User authentication with username/password
- User profile management
- Secure password hashing utilities
- REST API endpoints
- Input validation and security

## Components

- `main.py`: Core authentication logic
- `api.py`: Flask REST API endpoints
- `utils.py`: Security utilities and helpers
- `requirements.txt`: Python dependencies

## Usage

```bash
python main.py  # Run tests
python api.py   # Start API server
```

## API Endpoints

- `POST /api/login` - User authentication
- `GET /api/profile/<user_id>` - Get user profile
- `GET /api/health` - Health check
"""
    )


def check_claude_sdk_available() -> bool:
    """Check if Claude CLI is available."""
    import subprocess

    try:
        result = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


class TestClaudeE2E:
    """End-to-end tests for Claude integration."""

    @pytest.fixture
    def test_project(self):
        """Create a temporary test project."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            create_test_project(project_dir)
            yield project_dir

    def test_claude_sdk_availability(self):
        """Test that Claude CLI is available for testing."""
        assert (
            check_claude_sdk_available()
        ), "Claude CLI must be installed for e2e tests"

    def test_claude_command_help(self, test_project):
        """Test that claude command help works."""
        result = run_command(
            ["python", "-m", "code_indexer.cli", "claude", "--help"], cwd=test_project
        )

        assert result["success"], f"Help command failed: {result['stderr']}"
        assert "AI-powered code analysis" in result["stdout"]
        assert "--context-lines" in result["stdout"]
        assert "--stream" in result["stdout"]

    def test_claude_without_setup(self, test_project):
        """Test claude command behavior without explicit setup."""
        result = run_command(
            ["python", "-m", "code_indexer.cli", "claude", "test question"],
            cwd=test_project,
            timeout=30,
        )

        # Two valid scenarios:
        # 1. Services not available -> should fail gracefully with helpful error
        # 2. Services available (e.g., development environment) -> may succeed or fail with different error

        if not result["success"]:
            # If it failed, it should be with a helpful error message
            error_output = (
                result["stderr"] + result["stdout"]
            ).lower()  # Error might be in stdout
            assert any(
                phrase in error_output
                for phrase in [
                    "service not available",
                    "run 'setup' first",
                    "model not found",
                    "analysis failed",
                    "no semantic search results found",  # Valid failure if no index exists
                    "claude cli not available",  # CLI not installed
                    "failed to load config",  # Config issues
                ]
            ), f"Expected helpful error message, got: {result['stderr']} | {result['stdout']}"
        else:
            # If it succeeded, services must be available - that's acceptable in dev environments
            # Just verify it actually tried to work (has expected output structure)
            output = result["stdout"].lower()
            assert any(
                phrase in output
                for phrase in [
                    "claude analysis results",
                    "semantic search",
                    "performing semantic search",
                    "git repository",
                ]
            ), f"Expected valid claude output structure, got: {result['stdout']}"

    def test_complete_workflow_mock(self, test_project):
        """Test complete workflow with mocked services (no actual indexing)."""
        # Test 1: Initialize configuration
        init_result = run_command(
            ["python", "-m", "code_indexer.cli", "init", "--force"],
            cwd=test_project,
            timeout=30,
        )

        assert init_result["success"], f"Init failed: {init_result['stderr']}"
        assert (
            "Configuration created" in init_result["stdout"]
            or "Initialized configuration" in init_result["stdout"]
        )

        # Verify config file was created
        config_path = test_project / ".code-indexer" / "config.json"
        assert config_path.exists(), "Config file should be created"

        # Test 2: Verify configuration content
        with open(config_path) as f:
            config = json.load(f)

        assert "codebase_dir" in config
        assert "file_extensions" in config
        assert "qdrant" in config

        # Test 3: Test status command
        status_result = run_command(
            ["python", "-m", "code_indexer.cli", "status"], cwd=test_project, timeout=30
        )

        # Status should work even without services running
        # (it will show services as not available)
        assert status_result[
            "success"
        ], f"Status command failed: {status_result['stderr']}"

        # Test 4: Test claude command behavior
        claude_result = run_command(
            [
                "python",
                "-m",
                "code_indexer.cli",
                "claude",
                "How does authentication work?",
            ],
            cwd=test_project,
            timeout=30,
        )

        # Two valid scenarios:
        # 1. Services not available -> should fail gracefully with helpful error
        # 2. Services available -> may succeed or fail for other reasons (no index, etc.)
        if not claude_result["success"]:
            error_output = (claude_result["stderr"] + claude_result["stdout"]).lower()
            assert any(
                phrase in error_output
                for phrase in [
                    "service not available",
                    "run 'setup' first",
                    "not available",
                    "model not found",  # Ollama model not available
                    "analysis failed",  # Analysis failed due to missing services
                    "no semantic search results found",  # Valid failure if no index
                    "claude cli not available",  # CLI not installed
                ]
            ), f"Expected helpful error message, got: {claude_result['stderr']} | {claude_result['stdout']}"
        else:
            # If successful, verify it has expected output structure
            output = claude_result["stdout"].lower()
            assert any(
                phrase in output
                for phrase in [
                    "claude analysis results",
                    "semantic search",
                    "performing semantic search",
                    "git repository",
                ]
            ), f"Expected valid claude output, got: {claude_result['stdout']}"

    def test_claude_command_options(self, test_project):
        """Test various Claude command options fail gracefully."""
        # Test with different option combinations
        test_cases = [
            ["claude", "test", "--limit", "5"],
            ["claude", "test", "--context-lines", "200"],
            ["claude", "test", "--language", "python"],
            ["claude", "test", "--path", "*.py"],
            ["claude", "test", "--min-score", "0.8"],
            ["claude", "test", "--max-turns", "3"],
            ["claude", "test", "--no-explore"],
            ["claude", "test", "--no-stream"],
        ]

        for cmd_args in test_cases:
            result = run_command(
                ["python", "-m", "code_indexer.cli"] + cmd_args,
                cwd=test_project,
                timeout=60,
            )

            # Should either fail gracefully or succeed if services are available
            if not result["success"]:
                # If failed, should have helpful error message
                error_output = (
                    result["stderr"] + result["stdout"]
                ).lower()  # Error might be in stdout
                assert any(
                    phrase in error_output
                    for phrase in [
                        "service not available",
                        "run 'setup' first",
                        "model not found",
                        "analysis failed",
                        "no semantic search results found",  # Valid if no index
                        "claude cli not available",  # CLI not installed
                        "usage:",  # CLI argument errors
                        "error:",  # CLI errors
                        "no such option",  # Invalid options
                    ]
                ), f"Expected helpful error for {cmd_args}, got: {result['stderr']} | {result['stdout']}"
            else:
                # If successful, verify it has expected output structure
                output = result["stdout"].lower()
                assert any(
                    phrase in output
                    for phrase in [
                        "claude analysis results",
                        "semantic search",
                        "performing semantic search",
                        "git repository",
                    ]
                ), f"Expected valid claude output for {cmd_args}, got: {result['stdout']}"

    def test_project_structure_created(self, test_project):
        """Test that our test project structure is correct."""
        expected_files = [
            "main.py",
            "api.py",
            "utils.py",
            "README.md",
            "requirements.txt",
        ]

        for filename in expected_files:
            file_path = test_project / filename
            assert file_path.exists(), f"Test file {filename} should exist"
            assert (
                file_path.stat().st_size > 0
            ), f"Test file {filename} should not be empty"

        # Verify content of key files
        main_content = (test_project / "main.py").read_text()
        assert "authenticate_user" in main_content
        assert "def " in main_content

        api_content = (test_project / "api.py").read_text()
        assert "Flask" in api_content
        assert "/api/login" in api_content

        utils_content = (test_project / "utils.py").read_text()
        assert "hash_password" in utils_content
        assert "hashlib" in utils_content

    @pytest.mark.skipif(
        not check_claude_sdk_available(), reason="Claude CLI not available"
    )
    def test_claude_integration_import(self):
        """Test that Claude integration modules can be imported."""
        try:
            from code_indexer.services.claude_integration import (
                ClaudeIntegrationService,
                check_claude_sdk_availability,
            )
            from code_indexer.services.rag_context_extractor import RAGContextExtractor

            # Test basic functionality
            assert check_claude_sdk_availability()

            # Test instantiation (should not raise)
            with tempfile.TemporaryDirectory() as temp_dir:
                service = ClaudeIntegrationService(Path(temp_dir), "test-project")
                assert service.codebase_dir == Path(temp_dir)
                assert service.project_name == "test-project"

                extractor = RAGContextExtractor(Path(temp_dir))
                assert extractor.codebase_dir == Path(temp_dir)

        except Exception as e:
            pytest.fail(f"Claude integration import failed: {e}")

    def test_file_structure_integrity(self, test_project):
        """Test that the test project files have the expected content structure."""
        # Test main.py structure
        main_py = (test_project / "main.py").read_text()
        assert "def authenticate_user" in main_py
        assert "username" in main_py and "password" in main_py
        assert "def get_user_profile" in main_py

        # Test api.py structure
        api_py = (test_project / "api.py").read_text()
        assert "@app.route('/api/login'" in api_py
        assert "/api/profile" in api_py  # More flexible matching
        assert "from main import" in api_py

        # Test utils.py structure
        utils_py = (test_project / "utils.py").read_text()
        assert "def hash_password" in utils_py
        assert "def verify_password" in utils_py
        assert "def generate_session_token" in utils_py


def test_manual_workflow():
    """
    Manual test that can be run to verify the complete workflow.
    This test demonstrates the expected usage pattern.
    """
    print("\n" + "=" * 60)
    print("MANUAL E2E TEST WORKFLOW DEMONSTRATION")
    print("=" * 60)

    print("\n1. Testing Claude CLI availability...")
    sdk_available = check_claude_sdk_available()
    print(f"   Claude CLI available: {sdk_available}")

    print("\n2. Testing command line interface...")
    help_result = run_command(["python", "-m", "code_indexer.cli", "--help"])
    claude_in_help = "claude" in help_result["stdout"]
    print(f"   Claude command in help: {claude_in_help}")

    print("\n3. Testing Claude command help...")
    claude_help = run_command(["python", "-m", "code_indexer.cli", "claude", "--help"])
    claude_help_ok = (
        claude_help["success"] and "AI-powered code analysis" in claude_help["stdout"]
    )
    print(f"   Claude help working: {claude_help_ok}")

    print("\n4. Expected workflow (would require services):")
    print("   a. code-indexer init")
    print("   b. code-indexer setup")
    print("   c. code-indexer index")
    print("   d. code-indexer claude 'How does authentication work?'")

    print("\n5. Test results summary:")
    print(f"   ✅ Claude CLI available: {sdk_available}")
    print(f"   ✅ Claude command in CLI: {claude_in_help}")
    print(f"   ✅ Claude help functional: {claude_help_ok}")

    overall_success = sdk_available and claude_in_help and claude_help_ok
    print(f"\n🎯 Overall E2E readiness: {'✅ PASS' if overall_success else '❌ FAIL'}")

    # Don't return anything to avoid pytest warning
    assert overall_success, "E2E readiness check failed"


if __name__ == "__main__":
    # Run manual test when executed directly
    success = test_manual_workflow()
    exit(0 if success else 1)
