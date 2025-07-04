"""
End-to-end test for line number display in query results.

Tests that line numbers are properly shown in query output with actual line prefixes.
Uses TDD approach to drive implementation of enhanced line number display.
"""

from pathlib import Path
from typing import Dict, List

import pytest

# Import test infrastructure
from .test_infrastructure import (
    create_fast_e2e_setup,
    EmbeddingProvider,
    auto_register_project_collections,
)


def _get_test_project_with_line_numbers() -> Dict[str, str]:
    """Get test project files designed to test line number display."""
    return {
        "authentication.py": '''# Authentication module for user management
import hashlib
import secrets
from typing import Optional


def validate_credentials(username: str, password: str) -> bool:
    """
    Validate user credentials against the database.
    
    This function checks if the provided username and password
    combination is valid by comparing against stored hashes.
    
    Args:
        username: The user's login name
        password: The user's password
        
    Returns:
        bool: True if credentials are valid, False otherwise
    """
    if not username or not password:
        return False
    
    # Simulate database lookup
    stored_users = {
        "admin": "hashed_admin_password",
        "user1": "hashed_user1_password",
        "user2": "hashed_user2_password"
    }
    
    # In real implementation, this would hash the password
    # and compare with stored hash
    return username in stored_users


def create_user_session(user_id: int, username: str) -> str:
    """
    Create a new user session with secure token.
    
    This function generates a session token that includes
    user information and expiration timestamp.
    """
    session_data = {
        "user_id": user_id,
        "username": username,
        "created_at": "2024-01-01T00:00:00Z",
        "expires_at": "2024-01-02T00:00:00Z"
    }
    
    # Generate secure session token
    token = secrets.token_urlsafe(32)
    return f"session_{token}"


def hash_password_secure(password: str) -> tuple:
    """
    Hash password with salt for secure storage.
    
    Uses SHA-256 with random salt for password security.
    """
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    return hashed, salt
''',
        "database.py": '''# Database operations for user management
from typing import Dict, List, Optional


class UserDatabase:
    """
    Simple user database implementation.
    
    This class provides basic CRUD operations for user management
    with in-memory storage for testing purposes.
    """
    
    def __init__(self):
        """Initialize empty user database."""
        self.users = {}
        self.next_id = 1
    
    def create_user(self, username: str, email: str, password_hash: str) -> int:
        """
        Create a new user in the database.
        
        Args:
            username: Unique username for the user
            email: User's email address
            password_hash: Hashed password for security
            
        Returns:
            int: The new user's ID
        """
        user_id = self.next_id
        self.users[user_id] = {
            "id": user_id,
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "created_at": "2024-01-01T00:00:00Z",
            "active": True
        }
        self.next_id += 1
        return user_id
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user by their ID."""
        return self.users.get(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user by their username."""
        for user in self.users.values():
            if user["username"] == username:
                return user
        return None
    
    def update_user(self, user_id: int, updates: Dict) -> bool:
        """Update user information."""
        if user_id in self.users:
            self.users[user_id].update(updates)
            return True
        return False
    
    def delete_user(self, user_id: int) -> bool:
        """Delete user from database."""
        if user_id in self.users:
            del self.users[user_id]
            return True
        return False
    
    def list_users(self) -> List[Dict]:
        """Get all users from database."""
        return list(self.users.values())
''',
        "api_handlers.py": '''# API request handlers
from flask import request, jsonify
from authentication import validate_credentials, create_user_session
from database import UserDatabase


# Global database instance
db = UserDatabase()


def handle_login_request():
    """
    Handle user login API request.
    
    Validates credentials and creates user session if successful.
    Expected JSON payload: {"username": "...", "password": "..."}
    """
    data = request.get_json()
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({
            'error': 'Missing username or password',
            'status': 'error'
        }), 400
    
    username = data['username']
    password = data['password']
    
    if validate_credentials(username, password):
        user = db.get_user_by_username(username)
        if user:
            session_token = create_user_session(user['id'], username)
            return jsonify({
                'status': 'success',
                'message': 'Login successful',
                'session_token': session_token,
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'email': user['email']
                }
            })
    
    return jsonify({
        'status': 'error',
        'message': 'Invalid credentials'
    }), 401


def handle_user_profile_request(user_id: int):
    """
    Handle user profile retrieval request.
    
    Returns user profile information for the specified user ID.
    """
    user = db.get_user_by_id(user_id)
    
    if not user:
        return jsonify({
            'error': 'User not found',
            'status': 'error'
        }), 404
    
    return jsonify({
        'status': 'success',
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'created_at': user['created_at'],
            'active': user['active']
        }
    })


def handle_create_user_request():
    """Handle user creation API request."""
    data = request.get_json()
    
    required_fields = ['username', 'email', 'password']
    if not data or not all(field in data for field in required_fields):
        return jsonify({
            'error': 'Missing required fields',
            'required': required_fields,
            'status': 'error'
        }), 400
    
    # Check if username already exists
    existing_user = db.get_user_by_username(data['username'])
    if existing_user:
        return jsonify({
            'error': 'Username already exists',
            'status': 'error'
        }), 409
    
    # Create new user
    user_id = db.create_user(
        username=data['username'],
        email=data['email'],
        password_hash=f"hashed_{data['password']}"  # Simplified for demo
    )
    
    return jsonify({
        'status': 'success',
        'message': 'User created successfully',
        'user_id': user_id
    }), 201
''',
    }


class TestLineNumberDisplayE2E:
    """End-to-end tests for line number display in query results."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment using aggressive setup strategy."""
        # AGGRESSIVE SETUP: Use test infrastructure for consistent setup
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.VOYAGE_AI
        )

        # AGGRESSIVE SETUP: Ensure services and clean state
        print("🔧 Aggressive setup: Ensuring services and clean state...")
        services_ready = self.service_manager.ensure_services_ready()
        if not services_ready:
            pytest.skip("Could not ensure services are ready for E2E testing")

        # AGGRESSIVE SETUP: Clean all existing data first
        print("🧹 Aggressive setup: Cleaning all existing project data...")
        self._cleanup_all_data()

        # AGGRESSIVE SETUP: Verify services are actually working after cleanup
        print("🔍 Aggressive setup: Verifying services are functional...")
        try:
            # Test with a minimal project directory to verify services work
            test_setup_dir = Path(__file__).parent / "line_numbers_setup_verification"
            test_setup_dir.mkdir(exist_ok=True)
            (test_setup_dir / "test.py").write_text("def test(): pass")

            # Initialize and verify basic functionality works
            init_result = self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"],
                cwd=test_setup_dir,
                timeout=60,
            )
            if init_result.returncode != 0:
                print(f"Setup verification failed during init: {init_result.stderr}")
                pytest.skip("Services not functioning properly for E2E testing")

            # Start services
            start_result = self.cli_helper.run_cli_command(
                ["start", "--quiet"], cwd=test_setup_dir, timeout=120
            )
            if start_result.returncode != 0:
                print(f"Setup verification failed during start: {start_result.stderr}")
                pytest.skip("Could not start services for E2E testing")

            # Clean up verification directory
            try:
                import shutil

                shutil.rmtree(test_setup_dir, ignore_errors=True)
            except Exception:
                pass

            print("✅ Aggressive setup complete - services verified functional")

        except Exception as e:
            print(f"Setup verification failed: {e}")
            pytest.skip("Could not verify service functionality for E2E testing")

        yield

        # Cleanup after test - only clean project data, keep services running
        try:
            self._cleanup_all_data()
        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")

    def _cleanup_all_data(self):
        """Clean all project data to ensure clean test state."""
        try:
            # Use clean-data command to clean all projects
            cleanup_result = self.cli_helper.run_cli_command(
                ["clean-data", "--all-projects"], timeout=60, expect_success=False
            )
            if cleanup_result.returncode != 0:
                print(f"Cleanup warning (non-fatal): {cleanup_result.stderr}")
        except Exception as e:
            print(f"Cleanup warning (non-fatal): {e}")

    @pytest.fixture
    def test_project_with_line_numbers(self):
        """Create a test project designed for line number testing."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            # Auto-register collections for this project
            auto_register_project_collections(project_dir)
            test_files = _get_test_project_with_line_numbers()
            self.dir_manager.create_test_project(project_dir, custom_files=test_files)
            yield project_dir

    def test_line_numbers_in_quiet_query_results(self, test_project_with_line_numbers):
        """Test that line numbers appear in quiet mode query results."""
        with self.dir_manager.safe_chdir(test_project_with_line_numbers):
            # Services are already verified as working in aggressive setup
            # Initialize this specific project
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"], timeout=30
            )

            # Index the project
            index_result = self.cli_helper.run_cli_command(["index"], timeout=300)
            assert "Indexing complete!" in index_result.stdout

            # Query for specific content that should have line numbers
            query_result = self.cli_helper.run_cli_command(
                ["query", "validate_credentials function", "--quiet"], timeout=60
            )

            # FAILING TEST: Check that line numbers are displayed in quiet mode
            # Expected format: 0.85 authentication.py:6-26
            lines = query_result.stdout.strip().split("\n")

            # Find result lines (score + file path)
            result_lines = [
                line for line in lines if line.strip() and line[0].isdigit()
            ]

            assert len(result_lines) > 0, "Should have at least one query result"

            # Check that at least one result shows line numbers
            has_line_numbers = False
            for line in result_lines:
                # Expected format: "0.85 authentication.py:6-26" or "0.85 authentication.py:6"
                if ":" in line and (".py:" in line or ".js:" in line):
                    file_part = line.split(" ", 1)[1]  # Get everything after score
                    if ":" in file_part:
                        line_part = file_part.split(":")[1]
                        # Check if it's a line number or range (digits, possibly with dash)
                        if line_part.replace("-", "").isdigit():
                            has_line_numbers = True
                            break

            assert (
                has_line_numbers
            ), f"Query results should include line numbers. Got: {result_lines}"

    def test_line_numbers_in_verbose_query_results(
        self, test_project_with_line_numbers
    ):
        """Test that line numbers appear in verbose mode query results."""
        with self.dir_manager.safe_chdir(test_project_with_line_numbers):
            # Services are already verified as working in aggressive setup
            # Initialize this specific project
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"], timeout=30
            )

            # Index the project
            self.cli_helper.run_cli_command(["index"], timeout=300)

            # Query in verbose mode
            query_result = self.cli_helper.run_cli_command(
                ["query", "create_user_session function"], timeout=60
            )

            # FAILING TEST: Check that line numbers are displayed in verbose mode
            # Expected: File header should include line range like "authentication.py:28-45"
            output = query_result.stdout

            # Look for file headers with line numbers
            file_headers = [line for line in output.split("\n") if "📄 File:" in line]
            assert len(file_headers) > 0, "Should have at least one file result"

            # Check that at least one file header includes line numbers
            has_line_numbers = False
            for header in file_headers:
                if ":" in header and (".py:" in header or ".js:" in header):
                    # Extract the file path part
                    file_part = header.split("📄 File:")[1].split("|")[0].strip()
                    if ":" in file_part:
                        line_part = file_part.split(":")[1]
                        # Check if it's a line number or range
                        if line_part.replace("-", "").isdigit():
                            has_line_numbers = True
                            break

            assert (
                has_line_numbers
            ), f"Verbose query results should include line numbers in file headers. Got headers: {file_headers}"

    def test_line_numbers_with_actual_line_prefixes(
        self, test_project_with_line_numbers
    ):
        """Test that query results show actual line numbers as prefixes in content."""
        with self.dir_manager.safe_chdir(test_project_with_line_numbers):
            # Services are already verified as working in aggressive setup
            # Initialize this specific project
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"], timeout=30
            )

            # Index the project
            self.cli_helper.run_cli_command(["index"], timeout=300)

            # Query for specific function
            query_result = self.cli_helper.run_cli_command(
                ["query", "hash_password_secure"], timeout=60
            )

            # FAILING TEST: Check that content shows actual line numbers as prefixes
            # Expected format in content section:
            # 48: def hash_password_secure(password: str) -> tuple:
            # 49:     """
            # 50:     Hash password with salt for secure storage.
            # 51:
            # 52:     Uses SHA-256 with random salt for password security.
            # 53:     """
            output = query_result.stdout

            # Look for content sections (between separator lines)
            content_sections = []
            lines = output.split("\n")
            in_content = False
            current_content: List[str] = []

            for line in lines:
                if "──────────────────────────────────────────────────" in line:
                    if in_content:
                        # End of content section
                        content_sections.append("\n".join(current_content))
                        current_content = []
                        in_content = False
                    else:
                        # Start of content section
                        in_content = True
                elif in_content:
                    current_content.append(line)

            # Check that at least one content section has line number prefixes
            has_line_prefixes = False
            for content in content_sections:
                content_lines = content.strip().split("\n")
                line_prefixed_count = 0

                for content_line in content_lines:
                    if content_line.strip():  # Non-empty lines
                        # Check if line starts with "number:"
                        parts = content_line.split(":", 1)
                        if len(parts) == 2 and parts[0].strip().isdigit():
                            line_prefixed_count += 1

                # If more than half the lines have number prefixes, consider it valid
                if (
                    line_prefixed_count > 0
                    and line_prefixed_count
                    >= len([line for line in content_lines if line.strip()]) * 0.5
                ):
                    has_line_prefixes = True
                    break

            assert (
                has_line_prefixes
            ), f"Query results should show line number prefixes in content. Content sections found: {len(content_sections)}"

    def test_line_numbers_match_file_structure(self, test_project_with_line_numbers):
        """Test that displayed line numbers accurately match the actual file structure."""
        with self.dir_manager.safe_chdir(test_project_with_line_numbers):
            # Read the actual file to understand its structure
            auth_file = test_project_with_line_numbers / "authentication.py"
            auth_content = auth_file.read_text().split("\n")

            # Find the validate_credentials function
            func_start_line = None
            for i, line in enumerate(auth_content):
                if "def validate_credentials" in line:
                    func_start_line = i + 1  # Line numbers are 1-based
                    break

            assert (
                func_start_line is not None
            ), "Should find validate_credentials function in test file"

            # Services are already verified as working in aggressive setup
            # Initialize this specific project
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"], timeout=30
            )

            self.cli_helper.run_cli_command(["index"], timeout=300)

            # Query for the specific function
            query_result = self.cli_helper.run_cli_command(
                ["query", "validate_credentials function"], timeout=60
            )

            # FAILING TEST: Verify that the line numbers shown match the actual file
            output = query_result.stdout

            # Extract line range from results (either quiet or verbose mode)
            found_line_range = None

            # Check quiet mode results first
            lines = output.split("\n")
            for line in lines:
                if "authentication.py:" in line:
                    line_part = line.split("authentication.py:")[1].split()[0]
                    if line_part.replace("-", "").isdigit():
                        found_line_range = line_part
                        break

            # If not found in quiet format, check verbose format
            if not found_line_range:
                for line in lines:
                    if "📄 File:" in line and "authentication.py:" in line:
                        file_part = line.split("📄 File:")[1].split("|")[0].strip()
                        if ":" in file_part:
                            line_part = file_part.split(":")[1]
                            if line_part.replace("-", "").isdigit():
                                found_line_range = line_part
                                break

            assert (
                found_line_range is not None
            ), f"Should find line numbers in query results. Output: {output[:500]}"

            # Parse the line range
            if "-" in found_line_range:
                start_line, end_line = map(int, found_line_range.split("-"))
            else:
                start_line = end_line = int(found_line_range)

            # Verify the line range makes sense for the function location
            # Allow some flexibility (function could be in a chunk that starts before or after the exact function)
            assert (
                start_line <= func_start_line + 10
            ), f"Start line {start_line} should be close to function start {func_start_line}"
            assert (
                end_line >= func_start_line
            ), f"End line {end_line} should be after function start {func_start_line}"
            assert (
                end_line > start_line or start_line == end_line
            ), f"Line range {start_line}-{end_line} should be valid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
