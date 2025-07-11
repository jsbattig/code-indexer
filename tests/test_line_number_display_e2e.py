"""
End-to-end test for line number display in query results.

Tests that line numbers are properly shown in query output with actual line prefixes.
Uses TDD approach to drive implementation of enhanced line number display.
"""

from typing import Dict, List
import json
import subprocess
import os

import pytest

from .conftest import local_temporary_directory

# Import test infrastructure
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


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


@pytest.fixture
def line_number_test_repo():
    """Create a test repository for line number display tests."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.LINE_NUMBER_DISPLAY
        )

        yield temp_dir


def create_line_number_config(test_dir):
    """Create configuration for line number test."""
    config_dir = test_dir / ".code-indexer"
    config_file = config_dir / "config.json"

    # Load existing config if it exists (preserves container ports)
    if config_file.exists():
        with open(config_file, "r") as f:
            config = json.load(f)
    else:
        config = {
            "codebase_dir": str(test_dir),
            "qdrant": {
                "host": "http://localhost:6333",
                "collection": "line_number_test_collection",
                "vector_size": 1024,
            },
        }

    # Only modify test-specific settings, preserve container configuration
    config["embedding_provider"] = "voyage-ai"
    config["voyage_ai"] = {
        "model": "voyage-code-3",
        "api_key_env": "VOYAGE_API_KEY",
        "batch_size": 32,
        "max_retries": 3,
        "timeout": 30,
    }

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    return config_file


def create_test_project_with_line_numbers(test_dir):
    """Create test files in the test directory for line number testing."""
    test_files = _get_test_project_with_line_numbers()

    for filename, content in test_files.items():
        file_path = test_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_line_numbers_in_quiet_query_results(line_number_test_repo):
    """Test that line numbers appear in quiet mode query results."""
    test_dir = line_number_test_repo

    # Create test files
    create_test_project_with_line_numbers(test_dir)

    # Create configuration
    create_line_number_config(test_dir)

    # Initialize this specific project
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
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

    # Index the project
    index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"
    assert (
        "Indexing complete!" in index_result.stdout
        or "Processing complete" in index_result.stdout
    )

    # Query for specific content that should have line numbers
    query_result = subprocess.run(
        ["code-indexer", "query", "validate_credentials function", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert query_result.returncode == 0, f"Query failed: {query_result.stderr}"

    # FAILING TEST: Check that line numbers are displayed in quiet mode
    # Expected format: 0.85 authentication.py:6-26
    lines = query_result.stdout.strip().split("\n")

    # Find result lines (score + file path)
    result_lines = [line for line in lines if line.strip() and line[0].isdigit()]

    assert len(result_lines) > 0, "Should have at least one query result"

    # Check that at least one result shows line numbers
    has_line_numbers = False
    for line in result_lines:
        # Expected format: "0.85 authentication.py:6-26 " or "0.85 authentication.py:6 "
        if ":" in line and (".py:" in line or ".js:" in line):
            file_part = line.split(" ", 1)[
                1
            ].strip()  # Get everything after score and strip trailing space
            if ":" in file_part:
                line_part = file_part.split(":")[1].strip()
                # Check if it's a line number or range (digits, possibly with dash)
                if line_part and line_part.replace("-", "").replace(" ", "").isdigit():
                    has_line_numbers = True
                    break

    assert (
        has_line_numbers
    ), f"Query results should include line numbers. Got: {result_lines}"


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_line_numbers_in_verbose_query_results(line_number_test_repo):
    """Test that line numbers appear in verbose mode query results."""
    test_dir = line_number_test_repo

    # Create test files
    create_test_project_with_line_numbers(test_dir)

    # Create configuration
    create_line_number_config(test_dir)

    # Initialize this specific project
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
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

    # Index the project
    index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

    # Query in verbose mode
    query_result = subprocess.run(
        ["code-indexer", "query", "create_user_session function"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert query_result.returncode == 0, f"Query failed: {query_result.stderr}"

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


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_line_numbers_with_actual_line_prefixes(line_number_test_repo):
    """Test that query results show actual line numbers as prefixes in content."""
    test_dir = line_number_test_repo

    # Create test files
    create_test_project_with_line_numbers(test_dir)

    # Create configuration
    create_line_number_config(test_dir)

    # Initialize this specific project
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
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

    # Index the project
    index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

    # Query for specific function
    query_result = subprocess.run(
        ["code-indexer", "query", "hash_password_secure"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert query_result.returncode == 0, f"Query failed: {query_result.stderr}"

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


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_line_numbers_match_file_structure(line_number_test_repo):
    """Test that displayed line numbers accurately match the actual file structure."""
    test_dir = line_number_test_repo

    # Create test files
    create_test_project_with_line_numbers(test_dir)

    # Read the actual file to understand its structure
    auth_file = test_dir / "authentication.py"
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

    # Create configuration
    create_line_number_config(test_dir)

    # Initialize this specific project
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
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

    index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

    # Query for the specific function
    query_result = subprocess.run(
        ["code-indexer", "query", "validate_credentials function"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert query_result.returncode == 0, f"Query failed: {query_result.stderr}"

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
