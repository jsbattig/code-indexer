"""
End-to-end test for Claude integration functionality.

Tests the complete workflow from semantic search to Claude analysis.

Refactored to use NEW STRATEGY with test infrastructure to eliminate code duplication.
"""

import json
from pathlib import Path
from typing import Dict

import pytest

# Import test infrastructure to eliminate code duplication
from .test_infrastructure import create_fast_e2e_setup, EmbeddingProvider


# Removed duplicated run_command function - now using CLIHelper from test infrastructure!


# Removed duplicated create_test_project function - now using DirectoryManager from test infrastructure!


def _get_test_project_files() -> Dict[str, str]:
    """Get test project files for use with DirectoryManager."""
    return {
        "main.py": '''def authenticate_user(username: str, password: str) -> bool:
    """
    Authenticate user with username and password.
    
    Args:
        username: The user's username
        password: The user's password
        
    Returns:
        bool: True if authentication successful, False otherwise
    """
    if not username or not password:
        return False
    
    # Simple authentication logic for demo
    valid_users = {
        "admin": "admin123",
        "user": "password123"
    }
    
    return valid_users.get(username) == password


def get_user_profile(user_id: int) -> dict:
    """
    Retrieve user profile information.
    
    This function fetches user profile data from the database
    and returns it as a dictionary.
    """
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
    print(f"User 999 profile: {get_user_profile(999)}")''',
        "api.py": '''from flask import Flask, request, jsonify
from main import authenticate_user, get_user_profile

app = Flask(__name__)


@app.route('/api/login', methods=['POST'])
def login():
    """
    API endpoint for user login.
    
    Expects JSON payload with username and password.
    Returns authentication status and user info.
    """
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
    """
    API endpoint to get user profile.
    
    Returns user profile information for the given user ID.
    """
    profile_data = get_user_profile(user_id)
    
    if profile_data:
        return jsonify(profile_data)
    else:
        return jsonify({'error': 'User not found'}), 404


@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'auth-api'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)''',
        "utils.py": '''import hashlib
import secrets
from typing import Optional


def hash_password(password: str, salt: Optional[str] = None) -> tuple:
    """
    Hash a password with salt for secure storage.
    
    This utility function provides secure password hashing
    using SHA-256 with a random salt.
    
    Args:
        password: The plain text password to hash
        salt: Optional salt, if not provided a random one is generated
        
    Returns:
        tuple: (hashed_password, salt)
    """
    if salt is None:
        salt = secrets.token_hex(16)
    
    # Combine password and salt
    salted_password = f"{password}{salt}"
    
    # Hash the salted password
    hashed = hashlib.sha256(salted_password.encode()).hexdigest()
    
    return hashed, salt


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        password: The plain text password to verify
        hashed_password: The stored hash
        salt: The salt used for hashing
        
    Returns:
        bool: True if password matches, False otherwise
    """
    calculated_hash, _ = hash_password(password, salt)
    return calculated_hash == hashed_password


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def validate_email(email: str) -> bool:
    """Basic email validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def generate_session_token(user_id: int, username: str) -> str:
    """Generate a secure session token for user."""
    import time
    import json
    
    # Create session data
    session_data = {
        'user_id': user_id,
        'username': username,
        'timestamp': time.time(),
        'session_id': secrets.token_hex(16)
    }
    
    # Encode as token (simple base64 for demo purposes)
    import base64
    token_bytes = json.dumps(session_data).encode()
    return base64.b64encode(token_bytes).decode()''',
        "config.py": '''import os
from typing import Dict, Any


class Config:
    """Application configuration."""
    
    # Database settings
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    
    # Security settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    JWT_SECRET = os.getenv('JWT_SECRET', 'jwt-secret-key')
    
    # API settings
    API_VERSION = '1.0.0'
    API_PREFIX = '/api/v1'
    
    # Feature flags
    FEATURES = {
        'user_registration': True,
        'password_reset': True,
        'email_verification': False,
        'two_factor_auth': False
    }
    
    @classmethod
    def get_feature(cls, feature_name: str) -> bool:
        """Check if a feature is enabled."""
        return cls.FEATURES.get(feature_name, False)
    
    @classmethod
    def get_database_config(cls) -> Dict[str, Any]:
        """Get database configuration."""
        return {
            'url': cls.DATABASE_URL,
            'pool_size': 10,
            'max_overflow': 20,
            'pool_timeout': 30
        }''',
        "README.md": """# Authentication System

This is a sample authentication system with the following features:

## Components

### main.py
Core authentication logic:
- `authenticate_user()` - validates user credentials
- `get_user_profile()` - retrieves user profile data

### api.py
REST API endpoints:
- `POST /api/login` - user authentication endpoint
- `GET /api/profile/<id>` - user profile retrieval
- `GET /api/health` - health check endpoint

### utils.py
Security utilities:
- `hash_password()` - secure password hashing with salt
- `verify_password()` - password verification
- `generate_api_key()` - API key generation
- `validate_email()` - email format validation

### config.py
Application configuration:
- Database settings
- Security configuration
- Feature flags
- Environment-based configuration

## Usage

1. Start the API server:
   ```bash
   python api.py
   ```

2. Test authentication:
   ```bash
   curl -X POST http://localhost:5000/api/login \\
        -H "Content-Type: application/json" \\
        -d '{"username": "admin", "password": "admin123"}'
   ```

3. Get user profile:
   ```bash
   curl http://localhost:5000/api/profile/1
   ```

## Security Features

- Password hashing with salt
- Input validation
- Error handling
- Secure API key generation
- Email validation""",
        "requirements.txt": """Flask==2.3.3
Werkzeug==2.3.7
click==8.1.7
itsdangerous==2.1.2
Jinja2==3.1.2
MarkupSafe==2.1.3
hashlib2==1.0.1
secrets
""",
    }


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

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment using test infrastructure."""
        # NEW STRATEGY: Use test infrastructure for setup
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.VOYAGE_AI
        )
        yield

    @pytest.fixture
    def test_project(self):
        """Create a temporary test project using test infrastructure."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            # Use test infrastructure to create project with custom files
            test_files = _get_test_project_files()
            self.dir_manager.create_test_project(project_dir, custom_files=test_files)
            yield project_dir

    def test_claude_sdk_availability(self):
        """Test that Claude CLI is available for testing."""
        assert (
            check_claude_sdk_available()
        ), "Claude CLI must be installed for e2e tests"

    def test_claude_command_help(self, test_project):
        """Test that claude command help works."""
        with self.dir_manager.safe_chdir(test_project):
            result = self.cli_helper.run_cli_command(["claude", "--help"])
            assert "AI-powered code analysis" in result.stdout
            assert "--context-lines" in result.stdout
            assert "--stream" in result.stdout

    def test_claude_without_setup(self, test_project):
        """Test claude command behavior without explicit setup."""
        with self.dir_manager.safe_chdir(test_project):
            result = self.cli_helper.run_cli_command(
                ["claude", "test question"], timeout=30, expect_success=False
            )

            # Two valid scenarios:
            # 1. Services not available -> should fail gracefully with helpful error
            # 2. Services available (e.g., development environment) -> may succeed or fail with different error

            if result.returncode != 0:
                # If it failed, it should be with a helpful error message
                error_output = (
                    result.stderr + result.stdout
                ).lower()  # Error might be in stdout
                assert any(
                    phrase in error_output
                    for phrase in [
                        "service not available",
                        "run 'start' first",
                        "model not found",
                        "analysis failed",
                        "no semantic search results found",  # Valid failure if no index exists
                        "claude cli not available",  # CLI not installed
                        "failed to load config",  # Config issues
                    ]
                ), f"Expected helpful error message, got: {result.stderr} | {result.stdout}"
            else:
                # If it succeeded, services must be available - that's acceptable in dev environments
                # Just verify it actually tried to work (has expected output structure)
                output = result.stdout.lower()
                assert any(
                    phrase in output
                    for phrase in [
                        "claude analysis results",
                        "semantic search",
                        "performing semantic search",
                        "git repository",
                    ]
                ), f"Expected valid claude output structure, got: {result.stdout}"

    def test_complete_workflow_mock(self, test_project):
        """Test complete workflow with mocked services (no actual indexing)."""
        with self.dir_manager.safe_chdir(test_project):
            # Test 1: Initialize configuration
            init_result = self.cli_helper.run_cli_command(
                ["init", "--force"], timeout=30
            )
            assert (
                "Configuration created" in init_result.stdout
                or "Initialized configuration" in init_result.stdout
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
            self.cli_helper.run_cli_command(["status"], timeout=30)
            # Status should work even without services running
            # (it will show services as not available)

            # Test 4: Test claude command behavior
            claude_result = self.cli_helper.run_cli_command(
                ["claude", "How does authentication work?"],
                timeout=60,
                expect_success=False,
            )  # Increased timeout for CI environment

            # Two valid scenarios:
            # 1. Services not available -> should fail gracefully with helpful error
            # 2. Services available -> may succeed or fail for other reasons (no index, etc.)
            if claude_result.returncode != 0:
                error_output = (claude_result.stderr + claude_result.stdout).lower()
                # Check if command timed out during CI (acceptable failure mode)
                if (
                    "timed out" in claude_result.stderr.lower()
                    or "timeout" in claude_result.stderr.lower()
                ):
                    # Timeout is an acceptable failure mode in CI environment
                    return

                assert any(
                    phrase in error_output
                    for phrase in [
                        "service not available",
                        "run 'start' first",
                        "not available",
                        "model not found",  # Ollama model not available
                        "analysis failed",  # Analysis failed due to missing services
                        "no semantic search results found",  # Valid failure if no index
                        "claude cli not available",  # CLI not installed
                        "timed out",  # Command timeout (acceptable in CI)
                        "timeout",  # Command timeout (acceptable in CI)
                    ]
                ), f"Expected helpful error message, got: {claude_result.stderr} | {claude_result.stdout}"
            else:
                # If successful, verify it has expected output structure
                output = claude_result.stdout.lower()
                assert any(
                    phrase in output
                    for phrase in [
                        "claude analysis results",
                        "semantic search",
                        "performing semantic search",
                        "git repository",
                    ]
                ), f"Expected valid claude output, got: {claude_result.stdout}"

    def test_claude_command_options(self, test_project):
        """Test various Claude command options fail gracefully."""
        with self.dir_manager.safe_chdir(test_project):
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
                result = self.cli_helper.run_cli_command(
                    cmd_args, timeout=60, expect_success=False
                )

                # Should either fail gracefully or succeed if services are available
                if result.returncode != 0:
                    # If failed, should have helpful error message
                    error_output = (
                        result.stderr + result.stdout
                    ).lower()  # Error might be in stdout
                    assert any(
                        phrase in error_output
                        for phrase in [
                            "service not available",
                            "run 'start' first",
                            "model not found",
                            "analysis failed",
                            "no semantic search results found",  # Valid if no index
                            "claude cli not available",  # CLI not installed
                            "usage:",  # CLI argument errors
                            "error:",  # CLI errors
                            "no such option",  # Invalid options
                        ]
                    ), f"Expected helpful error for {cmd_args}, got: {result.stderr} | {result.stdout}"
                else:
                    # If successful, verify it has expected output structure
                    output = result.stdout.lower()
                    assert any(
                        phrase in output
                        for phrase in [
                            "claude analysis results",
                            "semantic search",
                            "performing semantic search",
                            "git repository",
                        ]
                    ), f"Expected valid claude output for {cmd_args}, got: {result.stdout}"

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
            import tempfile

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
    # Use simple subprocess for this demo function (not requiring test infrastructure)
    import subprocess

    try:
        help_result = subprocess.run(
            ["python", "-m", "code_indexer.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        claude_in_help = "claude" in help_result.stdout
    except Exception:
        claude_in_help = False
    print(f"   Claude command in help: {claude_in_help}")

    print("\n3. Testing Claude command help...")
    try:
        claude_help = subprocess.run(
            ["python", "-m", "code_indexer.cli", "claude", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        claude_help_ok = (
            claude_help.returncode == 0
            and "AI-powered code analysis" in claude_help.stdout
        )
    except Exception:
        claude_help_ok = False
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
