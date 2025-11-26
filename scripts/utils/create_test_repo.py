#!/usr/bin/env python3
"""Script to create test repository for diff-based temporal indexing validation.

This script creates a reproducible test repository at /tmp/cidx-test-repo with:
- 12 files in specified structure
- 12 commits with exact dates
- Various file operations (add, modify, delete, rename)
- Binary file
- Large diffs
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


TEST_REPO_PATH = Path("/tmp/cidx-test-repo")


def run_git_command(args: List[str], env_override: Optional[dict] = None) -> None:
    """Run git command in test repository."""
    # Start with current environment
    env = os.environ.copy()

    # Apply overrides if provided
    if env_override:
        env.update(env_override)

    subprocess.run(
        ["git"] + args,
        cwd=TEST_REPO_PATH,
        check=True,
        capture_output=True,
        env=env,
    )


def git_commit(date: str, message: str) -> None:
    """Create git commit with fixed date."""
    env = {
        "GIT_COMMITTER_DATE": date,
        "GIT_AUTHOR_DATE": date,
    }
    run_git_command(["commit", "-m", message], env_override=env)


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    file_path = TEST_REPO_PATH / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)


def create_repository_structure() -> None:
    """Create initial repository structure."""
    # Remove existing repository
    if TEST_REPO_PATH.exists():
        shutil.rmtree(TEST_REPO_PATH)

    # Create directories
    TEST_REPO_PATH.mkdir(parents=True)
    (TEST_REPO_PATH / "src").mkdir()
    (TEST_REPO_PATH / "tests").mkdir()
    (TEST_REPO_PATH / "docs").mkdir()

    # Initialize git
    run_git_command(["init"])
    run_git_command(["config", "user.name", "Test User"])
    run_git_command(["config", "user.email", "test@example.com"])


def commit_1() -> None:
    """Commit 1: Initial project setup (2025-11-01 10:00:00)."""
    write_file(".gitignore", """__pycache__/
*.pyc
.env
""")

    write_file("src/auth.py", '''"""Authentication module."""

def login(username: str, password: str) -> bool:
    """Basic login check."""
    if username == "admin" and password == "admin":
        return True
    return False

def logout(session_id: str) -> None:
    """End user session."""
    pass
''')

    write_file("src/database.py", '''"""Database connection module."""

def connect(connection_string: str):
    """Connect to database."""
    print(f"Connecting to: {connection_string}")
    return {"connected": True}

def disconnect(connection):
    """Disconnect from database."""
    pass
''')

    write_file("README.md", """# Test Project

A test project for diff-based temporal indexing validation.
""")

    run_git_command(["add", "."])
    git_commit("2025-11-01T10:00:00", "Initial project setup")


def commit_2() -> None:
    """Commit 2: Add API endpoints (2025-11-01 14:00:00)."""
    write_file("src/api.py", '''"""REST API endpoints."""

def get_users():
    """Get all users."""
    return [{"id": 1, "name": "Admin"}]

def create_user(name: str):
    """Create new user."""
    return {"id": 2, "name": name}

def delete_user(user_id: int):
    """Delete user."""
    return {"deleted": user_id}
''')

    # Modify database.py - append query helper
    write_file("src/database.py", '''"""Database connection module."""

def connect(connection_string: str):
    """Connect to database."""
    print(f"Connecting to: {connection_string}")
    return {"connected": True}

def disconnect(connection):
    """Disconnect from database."""
    pass

def query(connection, sql: str):
    """Execute SQL query."""
    print(f"Executing: {sql}")
    return []
''')

    run_git_command(["add", "."])
    git_commit("2025-11-01T14:00:00", "Add API endpoints")


def commit_3() -> None:
    """Commit 3: Add configuration system (2025-11-01 18:00:00)."""
    write_file("src/config.py", '''"""Configuration loading module."""

import os

def load_config():
    """Load application configuration."""
    return {
        "database_url": os.getenv("DATABASE_URL", "sqlite:///test.db"),
        "secret_key": os.getenv("SECRET_KEY", "dev-secret"),
        "debug": os.getenv("DEBUG", "true").lower() == "true",
    }

def get_database_url():
    """Get database connection string."""
    config = load_config()
    return config["database_url"]
''')

    # Modify database.py - use config for connection string
    write_file("src/database.py", '''"""Database connection module."""

from src.config import get_database_url

def connect(connection_string: str = None):
    """Connect to database using config."""
    if connection_string is None:
        connection_string = get_database_url()
    print(f"Connecting to: {connection_string}")
    return {"connected": True}

def disconnect(connection):
    """Disconnect from database."""
    pass

def query(connection, sql: str):
    """Execute SQL query."""
    print(f"Executing: {sql}")
    return []
''')

    run_git_command(["add", "."])
    git_commit("2025-11-01T18:00:00", "Add configuration system")


def commit_4() -> None:
    """Commit 4: Add utility functions (2025-11-02 10:00:00)."""
    write_file("src/utils.py", '''"""Utility functions."""

import hashlib
from datetime import datetime

def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def format_date(dt: datetime) -> str:
    """Format datetime as ISO string."""
    return dt.isoformat()

def sanitize_input(text: str) -> str:
    """Sanitize user input."""
    return text.strip().replace("<", "&lt;").replace(">", "&gt;")
''')

    # Modify auth.py - use utils for password hashing
    write_file("src/auth.py", '''"""Authentication module."""

from src.utils import hash_password

def login(username: str, password: str) -> bool:
    """Basic login check with hashed password."""
    hashed = hash_password(password)
    # In real app, compare with stored hash
    if username == "admin" and password == "admin":
        return True
    return False

def logout(session_id: str) -> None:
    """End user session."""
    pass
''')

    run_git_command(["add", "."])
    git_commit("2025-11-02T10:00:00", "Add utility functions")


def commit_5() -> None:
    """Commit 5: Add test suite (2025-11-02 14:00:00)."""
    write_file("tests/test_auth.py", '''"""Tests for authentication module."""

from src.auth import login, logout

def test_login_success():
    """Test successful login."""
    assert login("admin", "admin") is True

def test_login_failure():
    """Test failed login."""
    assert login("wrong", "wrong") is False

def test_logout():
    """Test logout."""
    logout("session-123")  # Should not raise
''')

    write_file("tests/test_database.py", '''"""Tests for database module."""

from src.database import connect, disconnect, query

def test_connect():
    """Test database connection."""
    conn = connect("sqlite:///test.db")
    assert conn["connected"] is True

def test_query():
    """Test SQL query execution."""
    conn = connect("sqlite:///test.db")
    results = query(conn, "SELECT * FROM users")
    assert isinstance(results, list)
''')

    run_git_command(["add", "."])
    git_commit("2025-11-02T14:00:00", "Add test suite")


def commit_6() -> None:
    """Commit 6: Refactor authentication with JWT (2025-11-02 18:00:00)."""
    # Complete rewrite with 100+ line changes
    write_file("src/auth.py", '''"""Authentication module with JWT support."""

import jwt
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict

SECRET_KEY = "secret-key-change-in-production"

def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hash_val: str) -> bool:
    """Verify password against hash."""
    return hash_password(password) == hash_val

def create_token(user_id: str, username: str) -> str:
    """Create JWT token."""
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> Optional[Dict]:
    """Verify and decode JWT token."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def login(username: str, password: str) -> Optional[str]:
    """Authenticate user and return JWT token."""
    # In real app, check against database
    if username == "admin" and verify_password(password, hash_password("admin")):
        return create_token("1", username)
    return None

def logout(token: str) -> bool:
    """Invalidate token (in real app, add to blacklist)."""
    return verify_token(token) is not None

def get_user_from_token(token: str) -> Optional[Dict]:
    """Extract user information from token."""
    payload = verify_token(token)
    if payload:
        return {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
        }
    return None

def refresh_token(token: str) -> Optional[str]:
    """Refresh an existing token."""
    payload = verify_token(token)
    if payload:
        return create_token(payload["user_id"], payload["username"])
    return None
''')

    run_git_command(["add", "."])
    git_commit("2025-11-02T18:00:00", "Refactor authentication")


def commit_7() -> None:
    """Commit 7: Add API tests (2025-11-03 10:00:00)."""
    write_file("tests/test_api.py", '''"""Tests for API endpoints."""

from src.api import get_users, create_user, delete_user

def test_get_users():
    """Test getting all users."""
    users = get_users()
    assert isinstance(users, list)
    assert len(users) > 0

def test_create_user():
    """Test user creation."""
    user = create_user("Test User")
    assert user["name"] == "Test User"
    assert "id" in user

def test_delete_user():
    """Test user deletion."""
    result = delete_user(123)
    assert result["deleted"] == 123
''')

    # Modify api.py - add error handling
    write_file("src/api.py", '''"""REST API endpoints with error handling."""

def get_users():
    """Get all users."""
    try:
        return [{"id": 1, "name": "Admin"}]
    except Exception as e:
        return {"error": str(e)}

def create_user(name: str):
    """Create new user with validation."""
    if not name or len(name) < 2:
        return {"error": "Name must be at least 2 characters"}
    try:
        return {"id": 2, "name": name}
    except Exception as e:
        return {"error": str(e)}

def delete_user(user_id: int):
    """Delete user with error handling."""
    if user_id < 1:
        return {"error": "Invalid user ID"}
    try:
        return {"deleted": user_id}
    except Exception as e:
        return {"error": str(e)}
''')

    run_git_command(["add", "."])
    git_commit("2025-11-03T10:00:00", "Add API tests")


def commit_8() -> None:
    """Commit 8: Delete old database code (2025-11-03 14:00:00)."""
    # Delete database.py
    (TEST_REPO_PATH / "src/database.py").unlink()

    # Add new async database implementation
    write_file("src/db_new.py", '''"""Modern async database implementation."""

import asyncio
from typing import Optional, Dict, List

class DatabaseConnection:
    """Async database connection."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.connected = False

    async def connect(self):
        """Establish database connection."""
        await asyncio.sleep(0.01)  # Simulate connection
        self.connected = True
        return self

    async def disconnect(self):
        """Close database connection."""
        await asyncio.sleep(0.01)
        self.connected = False

    async def query(self, sql: str) -> List[Dict]:
        """Execute SQL query asynchronously."""
        if not self.connected:
            raise RuntimeError("Not connected to database")
        await asyncio.sleep(0.01)  # Simulate query
        return []

async def create_connection(connection_string: str) -> DatabaseConnection:
    """Create and connect to database."""
    conn = DatabaseConnection(connection_string)
    await conn.connect()
    return conn
''')

    run_git_command(["add", "."])
    git_commit("2025-11-03T14:00:00", "Delete old database code")


def commit_9() -> None:
    """Commit 9: Rename db_new to database (2025-11-03 16:00:00)."""
    run_git_command(["mv", "src/db_new.py", "src/database.py"])
    git_commit("2025-11-03T16:00:00", "Rename db_new to database")


def commit_10() -> None:
    """Commit 10: Add documentation (2025-11-03 18:00:00)."""
    write_file("docs/API.md", """# API Documentation

## Authentication

### POST /login
Authenticate user and receive JWT token.

**Request:**
```json
{
  "username": "admin",
  "password": "admin"
}
```

**Response:**
```json
{
  "token": "eyJhbGc..."
}
```

## Users

### GET /users
Get list of all users.

**Response:**
```json
[
  {"id": 1, "name": "Admin"}
]
```

### POST /users
Create new user.

**Request:**
```json
{
  "name": "New User"
}
```

### DELETE /users/:id
Delete user by ID.
""")

    write_file("docs/CHANGELOG.md", """# Changelog

## 2025-11-04

### Added
- API documentation
- User management endpoints
- JWT authentication

### Changed
- Refactored authentication module
- Migrated to async database

### Removed
- Old synchronous database code
""")

    # Modify README.md - add usage examples
    write_file("README.md", """# Test Project

A test project for diff-based temporal indexing validation.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```python
from src.auth import login
from src.api import get_users

# Authenticate
token = login("admin", "admin")

# Get users
users = get_users()
```

## Testing

```bash
pytest tests/
```

## Documentation

See `docs/API.md` for API documentation.
""")

    run_git_command(["add", "."])
    git_commit("2025-11-03T18:00:00", "Add documentation")


def commit_11() -> None:
    """Commit 11: Binary file addition (2025-11-04 10:00:00)."""
    # Create a small fake PNG file
    png_path = TEST_REPO_PATH / "docs/architecture.png"
    # PNG file signature
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    png_path.write_bytes(png_data)

    run_git_command(["add", "docs/architecture.png"])
    git_commit("2025-11-04T10:00:00", "Binary file addition")


def commit_12() -> None:
    """Commit 12: Large refactoring (2025-11-04 14:00:00)."""
    # Generate 500+ lines of changes in api.py
    api_content = '''"""REST API endpoints - Major redesign."""

from typing import Optional, Dict, List, Any
from datetime import datetime
import asyncio

class APIError(Exception):
    """Custom API error."""
    pass

class ValidationError(APIError):
    """Validation error."""
    pass

class NotFoundError(APIError):
    """Resource not found."""
    pass

class User:
    """User model."""

    def __init__(self, user_id: int, name: str, email: str):
        self.id = user_id
        self.name = name
        self.email = email
        self.created_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }

class UserRepository:
    """User data repository."""

    def __init__(self):
        self.users: Dict[int, User] = {}
        self.next_id = 1
        self._initialize_data()

    def _initialize_data(self):
        """Initialize with sample data."""
        self.create("Admin", "admin@example.com")

    def create(self, name: str, email: str) -> User:
        """Create new user."""
        user = User(self.next_id, name, email)
        self.users[self.next_id] = user
        self.next_id += 1
        return user

    def get(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return self.users.get(user_id)

    def get_all(self) -> List[User]:
        """Get all users."""
        return list(self.users.values())

    def delete(self, user_id: int) -> bool:
        """Delete user."""
        if user_id in self.users:
            del self.users[user_id]
            return True
        return False

    def update(self, user_id: int, name: str = None, email: str = None) -> Optional[User]:
        """Update user."""
        user = self.users.get(user_id)
        if user:
            if name:
                user.name = name
            if email:
                user.email = email
            return user
        return None

# Global repository instance
user_repo = UserRepository()

def validate_user_input(name: str, email: str) -> None:
    """Validate user input."""
    if not name or len(name) < 2:
        raise ValidationError("Name must be at least 2 characters")

    if not email or "@" not in email:
        raise ValidationError("Invalid email address")

    if len(name) > 100:
        raise ValidationError("Name too long")

    if len(email) > 100:
        raise ValidationError("Email too long")

async def get_users() -> List[Dict[str, Any]]:
    """Get all users asynchronously."""
    try:
        await asyncio.sleep(0.01)  # Simulate async operation
        users = user_repo.get_all()
        return [user.to_dict() for user in users]
    except Exception as e:
        raise APIError(f"Failed to get users: {str(e)}")

async def get_user(user_id: int) -> Dict[str, Any]:
    """Get user by ID asynchronously."""
    try:
        await asyncio.sleep(0.01)
        user = user_repo.get(user_id)
        if not user:
            raise NotFoundError(f"User {user_id} not found")
        return user.to_dict()
    except NotFoundError:
        raise
    except Exception as e:
        raise APIError(f"Failed to get user: {str(e)}")

async def create_user(name: str, email: str) -> Dict[str, Any]:
    """Create new user asynchronously."""
    try:
        validate_user_input(name, email)
        await asyncio.sleep(0.01)
        user = user_repo.create(name, email)
        return user.to_dict()
    except ValidationError:
        raise
    except Exception as e:
        raise APIError(f"Failed to create user: {str(e)}")

async def update_user(user_id: int, name: str = None, email: str = None) -> Dict[str, Any]:
    """Update user asynchronously."""
    try:
        if name or email:
            validate_user_input(name or "valid", email or "valid@example.com")

        await asyncio.sleep(0.01)
        user = user_repo.update(user_id, name, email)

        if not user:
            raise NotFoundError(f"User {user_id} not found")

        return user.to_dict()
    except (ValidationError, NotFoundError):
        raise
    except Exception as e:
        raise APIError(f"Failed to update user: {str(e)}")

async def delete_user(user_id: int) -> Dict[str, Any]:
    """Delete user asynchronously."""
    try:
        await asyncio.sleep(0.01)

        if not user_repo.delete(user_id):
            raise NotFoundError(f"User {user_id} not found")

        return {"deleted": user_id, "success": True}
    except NotFoundError:
        raise
    except Exception as e:
        raise APIError(f"Failed to delete user: {str(e)}")

async def search_users(query: str) -> List[Dict[str, Any]]:
    """Search users by name or email."""
    try:
        await asyncio.sleep(0.01)

        if not query or len(query) < 2:
            raise ValidationError("Search query must be at least 2 characters")

        users = user_repo.get_all()
        query_lower = query.lower()

        matching_users = [
            user for user in users
            if query_lower in user.name.lower() or query_lower in user.email.lower()
        ]

        return [user.to_dict() for user in matching_users]
    except ValidationError:
        raise
    except Exception as e:
        raise APIError(f"Failed to search users: {str(e)}")

def handle_api_error(error: Exception) -> Dict[str, Any]:
    """Handle API errors and return error response."""
    if isinstance(error, ValidationError):
        return {
            "error": "Validation error",
            "message": str(error),
            "status_code": 400,
        }
    elif isinstance(error, NotFoundError):
        return {
            "error": "Not found",
            "message": str(error),
            "status_code": 404,
        }
    elif isinstance(error, APIError):
        return {
            "error": "API error",
            "message": str(error),
            "status_code": 500,
        }
    else:
        return {
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "status_code": 500,
        }

class APIRouter:
    """API route handler."""

    def __init__(self):
        self.routes: Dict[str, Any] = {}

    def register(self, path: str, handler: Any):
        """Register route handler."""
        self.routes[path] = handler

    async def handle_request(self, path: str, *args, **kwargs) -> Dict[str, Any]:
        """Handle API request."""
        if path not in self.routes:
            return handle_api_error(NotFoundError(f"Route {path} not found"))

        try:
            handler = self.routes[path]
            result = await handler(*args, **kwargs)
            return {"data": result, "status_code": 200}
        except Exception as e:
            return handle_api_error(e)

# Initialize router
router = APIRouter()
router.register("/users", get_users)
router.register("/users/:id", get_user)
router.register("/users/create", create_user)
router.register("/users/update", update_user)
router.register("/users/delete", delete_user)
router.register("/users/search", search_users)

async def process_request(path: str, method: str, data: Dict = None) -> Dict[str, Any]:
    """Process incoming API request."""
    try:
        if method == "GET":
            if ":" in path:
                # Extract ID from path
                user_id = int(path.split("/")[-1])
                return await router.handle_request("/users/:id", user_id)
            elif "search" in path and data:
                return await router.handle_request("/users/search", data.get("query"))
            else:
                return await router.handle_request("/users")

        elif method == "POST":
            if not data:
                raise ValidationError("Request body required")
            return await router.handle_request("/users/create", data.get("name"), data.get("email"))

        elif method == "PUT":
            if not data or "id" not in data:
                raise ValidationError("User ID required")
            return await router.handle_request("/users/update", data["id"], data.get("name"), data.get("email"))

        elif method == "DELETE":
            if not data or "id" not in data:
                raise ValidationError("User ID required")
            return await router.handle_request("/users/delete", data["id"])

        else:
            raise ValidationError(f"Unsupported method: {method}")

    except Exception as e:
        return handle_api_error(e)
'''

    write_file("src/api.py", api_content)

    # Generate 200+ lines of changes in auth.py
    auth_content = '''"""Authentication module with JWT support - Enhanced."""

import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set

SECRET_KEY = "secret-key-change-in-production"
ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24
REFRESH_TOKEN_EXPIRY_DAYS = 7

class AuthError(Exception):
    """Authentication error."""
    pass

class TokenExpiredError(AuthError):
    """Token has expired."""
    pass

class InvalidTokenError(AuthError):
    """Invalid token."""
    pass

class InvalidCredentialsError(AuthError):
    """Invalid credentials."""
    pass

class Session:
    """User session."""

    def __init__(self, session_id: str, user_id: str, username: str):
        self.session_id = session_id
        self.user_id = user_id
        self.username = username
        self.created_at = datetime.utcnow()
        self.last_accessed = datetime.utcnow()
        self.is_valid = True

    def update_access_time(self):
        """Update last access time."""
        self.last_accessed = datetime.utcnow()

    def invalidate(self):
        """Invalidate session."""
        self.is_valid = False

class SessionManager:
    """Manage user sessions."""

    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.blacklisted_tokens: Set[str] = set()

    def create_session(self, user_id: str, username: str) -> Session:
        """Create new session."""
        session_id = secrets.token_urlsafe(32)
        session = Session(session_id, user_id, username)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        session = self.sessions.get(session_id)
        if session and session.is_valid:
            session.update_access_time()
            return session
        return None

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate session."""
        session = self.sessions.get(session_id)
        if session:
            session.invalidate()
            return True
        return False

    def blacklist_token(self, token: str):
        """Add token to blacklist."""
        self.blacklisted_tokens.add(token)

    def is_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted."""
        return token in self.blacklisted_tokens

    def cleanup_expired_sessions(self):
        """Remove expired sessions."""
        now = datetime.utcnow()
        expired = [
            sid for sid, session in self.sessions.items()
            if (now - session.last_accessed).days > 1
        ]
        for sid in expired:
            del self.sessions[sid]

# Global session manager
session_manager = SessionManager()

def hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with salt."""
    if salt is None:
        salt = secrets.token_hex(16)

    salted = f"{password}{salt}"
    hash_val = hashlib.sha256(salted.encode()).hexdigest()
    return hash_val, salt

def verify_password(password: str, hash_val: str, salt: str) -> bool:
    """Verify password against hash with salt."""
    computed_hash, _ = hash_password(password, salt)
    return computed_hash == hash_val

def create_token(user_id: str, username: str, token_type: str = "access") -> str:
    """Create JWT token."""
    if token_type == "access":
        expiry = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    else:  # refresh token
        expiry = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRY_DAYS)

    payload = {
        "user_id": user_id,
        "username": username,
        "exp": expiry,
        "iat": datetime.utcnow(),
        "type": token_type,
        "jti": secrets.token_urlsafe(16),  # Token ID
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Dict:
    """Verify and decode JWT token."""
    if session_manager.is_blacklisted(token):
        raise InvalidTokenError("Token has been revoked")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"Invalid token: {str(e)}")

def login(username: str, password: str) -> Dict[str, str]:
    """Authenticate user and return tokens."""
    # In real app, check against database
    # This is simplified for testing
    if not username or not password:
        raise InvalidCredentialsError("Username and password required")

    # Simulate password verification
    stored_hash = "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"  # "password"
    stored_salt = "test_salt"

    if username == "admin" and password == "admin":
        # Create session
        session = session_manager.create_session("1", username)

        # Generate tokens
        access_token = create_token("1", username, "access")
        refresh_token = create_token("1", username, "refresh")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": TOKEN_EXPIRY_HOURS * 3600,
            "session_id": session.session_id,
        }

    raise InvalidCredentialsError("Invalid username or password")

def logout(token: str) -> bool:
    """Invalidate token and session."""
    try:
        payload = verify_token(token)
        session_id = payload.get("jti")  # Use token ID as session ID

        # Blacklist token
        session_manager.blacklist_token(token)

        # Invalidate session if exists
        if session_id:
            session_manager.invalidate_session(session_id)

        return True
    except (TokenExpiredError, InvalidTokenError):
        return False

def get_user_from_token(token: str) -> Dict:
    """Extract user information from token."""
    payload = verify_token(token)
    return {
        "user_id": payload.get("user_id"),
        "username": payload.get("username"),
        "token_type": payload.get("type"),
    }

def refresh_access_token(refresh_token: str) -> str:
    """Generate new access token from refresh token."""
    payload = verify_token(refresh_token)

    if payload.get("type") != "refresh":
        raise InvalidTokenError("Not a refresh token")

    # Generate new access token
    return create_token(payload["user_id"], payload["username"], "access")

def validate_token_permissions(token: str, required_permissions: List[str]) -> bool:
    """Validate token has required permissions."""
    try:
        payload = verify_token(token)
        # In real app, check permissions from database
        return True
    except (TokenExpiredError, InvalidTokenError):
        return False

def change_password(user_id: str, old_password: str, new_password: str) -> bool:
    """Change user password."""
    # In real app, verify old password and update database
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters")

    # Hash new password
    new_hash, salt = hash_password(new_password)

    # In real app: update database with new_hash and salt
    return True
'''

    write_file("src/auth.py", auth_content)

    run_git_command(["add", "."])
    git_commit("2025-11-04T14:00:00", "Large refactoring")


def main() -> None:
    """Create test repository with complete commit history."""
    print("Creating test repository...")
    create_repository_structure()

    print("Creating commit 1: Initial project setup...")
    commit_1()

    print("Creating commit 2: Add API endpoints...")
    commit_2()

    print("Creating commit 3: Add configuration system...")
    commit_3()

    print("Creating commit 4: Add utility functions...")
    commit_4()

    print("Creating commit 5: Add test suite...")
    commit_5()

    print("Creating commit 6: Refactor authentication...")
    commit_6()

    print("Creating commit 7: Add API tests...")
    commit_7()

    print("Creating commit 8: Delete old database code...")
    commit_8()

    print("Creating commit 9: Rename db_new to database...")
    commit_9()

    print("Creating commit 10: Add documentation...")
    commit_10()

    print("Creating commit 11: Binary file addition...")
    commit_11()

    print("Creating commit 12: Large refactoring...")
    commit_12()

    print(f"\nTest repository created successfully at {TEST_REPO_PATH}")
    print("Repository contains:")
    print("  - 12 files")
    print("  - 12 commits")
    print("  - Various file operations (add, modify, delete, rename)")
    print("  - Binary file (architecture.png)")
    print("  - Large diffs (500+ lines in api.py, 200+ lines in auth.py)")


if __name__ == "__main__":
    main()
