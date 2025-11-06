# Story 0: Create Test Repository for Diff-Based Temporal Validation

## Context

Before rewriting temporal indexing to use diffs instead of full blobs, we need a controlled test repository with known file changes across commits. This repository will be used to validate indexing behavior and query results.

## User Story

**As a developer**, I want a small test repository with predictable changes across commits, **so that** I can validate diff-based temporal indexing produces correct results.

## Requirements

### Test Repository Structure

**Location**: `/tmp/cidx-test-repo/`

**Files** (12 total):
```
src/
  auth.py           - Authentication module
  database.py       - Database connection
  api.py           - REST API endpoints
  utils.py         - Utility functions
  config.py        - Configuration loading
tests/
  test_auth.py     - Auth tests
  test_database.py - Database tests
  test_api.py      - API tests
docs/
  README.md        - Project documentation
  CHANGELOG.md     - Change log
  API.md           - API documentation
.gitignore         - Git ignore file
```

### Commit History (12 commits)

**Commit 1**: Initial project setup
- Add: `src/auth.py`, `src/database.py`, `README.md`, `.gitignore`
- Content: Basic auth functions, db connection, minimal README
- Date: 2025-11-01 10:00:00

**Commit 2**: Add API endpoints
- Add: `src/api.py`
- Modify: `src/database.py` (add query helper)
- Content: 3 REST endpoints, enhanced db module
- Date: 2025-11-01 14:00:00

**Commit 3**: Add configuration system
- Add: `src/config.py`
- Modify: `src/database.py` (use config for connection string)
- Content: Config loader, refactored db connection
- Date: 2025-11-01 18:00:00

**Commit 4**: Add utility functions
- Add: `src/utils.py`
- Modify: `src/auth.py` (use utils for password hashing)
- Content: String utils, date utils, password utils
- Date: 2025-11-02 10:00:00

**Commit 5**: Add test suite
- Add: `tests/test_auth.py`, `tests/test_database.py`
- Content: Unit tests for auth and database modules
- Date: 2025-11-02 14:00:00

**Commit 6**: Refactor authentication
- Modify: `src/auth.py` (complete rewrite)
- Content: JWT tokens, session management (100+ line changes)
- Date: 2025-11-02 18:00:00

**Commit 7**: Add API tests
- Add: `tests/test_api.py`
- Modify: `src/api.py` (add error handling)
- Content: API test suite, enhanced error responses
- Date: 2025-11-03 10:00:00

**Commit 8**: Delete old database code
- Delete: `src/database.py`
- Add: `src/db_new.py` (replacement)
- Content: Modern async database implementation
- Date: 2025-11-03 14:00:00

**Commit 9**: Rename db_new to database
- Rename: `src/db_new.py` → `src/database.py`
- Content: File rename only, no changes
- Date: 2025-11-03 16:00:00

**Commit 10**: Add documentation
- Add: `docs/API.md`, `docs/CHANGELOG.md`
- Modify: `README.md` (add usage examples)
- Content: Full API docs, changelog, examples
- Date: 2025-11-03 18:00:00

**Commit 11**: Binary file addition
- Add: `docs/architecture.png` (fake binary)
- Content: Simulated binary file (text file marked as binary in git)
- Date: 2025-11-04 10:00:00

**Commit 12**: Large refactoring
- Modify: `src/api.py` (500+ line changes)
- Modify: `src/auth.py` (200+ line changes)
- Content: Major API redesign, auth improvements
- Date: 2025-11-04 14:00:00

### File Content Examples

**src/auth.py** (initial):
```python
"""Authentication module."""

def login(username: str, password: str) -> bool:
    """Basic login check."""
    if username == "admin" and password == "admin":
        return True
    return False

def logout(session_id: str) -> None:
    """End user session."""
    pass
```

**src/auth.py** (after commit 6 refactor):
```python
"""Authentication module with JWT support."""

import jwt
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict

SECRET_KEY = "secret-key-change-in-production"

def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hash: str) -> bool:
    """Verify password against hash."""
    return hash_password(password) == hash

def create_token(user_id: str, username: str) -> str:
    """Create JWT token."""
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=24)
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
```

## Acceptance Criteria

### Repository Structure
- [ ] Repository created at `/tmp/cidx-test-repo/`
- [ ] Contains exactly 12 files in specified structure
- [ ] All files have realistic code content
- [ ] `.git` directory initialized

### Commit History
- [ ] Exactly 12 commits in chronological order
- [ ] Commit dates match specification (Nov 1-4, 2025)
- [ ] Commit messages are descriptive
- [ ] Each commit has specified file changes (add/modify/delete/rename)

### File Changes Coverage
- [ ] At least 1 new file addition (commits 1, 2, 3, 4, 5, 7, 10, 11)
- [ ] At least 1 file modification (commits 2, 3, 4, 6, 7, 10, 12)
- [ ] At least 1 file deletion (commit 8)
- [ ] At least 1 file rename (commit 9)
- [ ] At least 1 binary file (commit 11)
- [ ] At least 1 large diff (commit 12 with 500+ lines)

### Verification Commands
```bash
# Repository exists
test -d /tmp/cidx-test-repo/.git

# Correct number of commits
cd /tmp/cidx-test-repo
git log --oneline | wc -l  # Should be 12

# Correct date range
git log --format="%ad" --date=short | sort -u
# Should show: 2025-11-01, 2025-11-02, 2025-11-03, 2025-11-04

# File count
find . -type f ! -path './.git/*' | wc -l  # Should be 12

# Verify specific commit contents
git show <commit-6-hash> --stat | grep "src/auth.py"  # Should show large changes
git show <commit-8-hash> --name-status | grep "D.*database.py"  # Should show deletion
git show <commit-9-hash> --name-status | grep "R.*db_new.py.*database.py"  # Should show rename
```

## Manual Test Plan

### Setup Test Repository

**Step 1**: Create and initialize repository
```bash
rm -rf /tmp/cidx-test-repo
mkdir -p /tmp/cidx-test-repo/{src,tests,docs}
cd /tmp/cidx-test-repo
git init
git config user.name "Test User"
git config user.email "test@example.com"
```

**Expected**: Repository initialized with proper structure

**Step 2**: Create initial files (Commit 1)
```bash
# Create .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.env
EOF

# Create src/auth.py
cat > src/auth.py << 'EOF'
"""Authentication module."""

def login(username: str, password: str) -> bool:
    """Basic login check."""
    if username == "admin" and password == "admin":
        return True
    return False

def logout(session_id: str) -> None:
    """End user session."""
    pass
EOF

# Create src/database.py
cat > src/database.py << 'EOF'
"""Database connection module."""

def connect(connection_string: str):
    """Connect to database."""
    print(f"Connecting to: {connection_string}")
    return {"connected": True}

def disconnect(connection):
    """Disconnect from database."""
    pass
EOF

# Create README.md
cat > README.md << 'EOF'
# Test Project

A test project for diff-based temporal indexing validation.
EOF

git add .
GIT_COMMITTER_DATE="2025-11-01T10:00:00" git commit --date="2025-11-01T10:00:00" -m "Initial project setup"
```

**Expected**: Commit 1 created with 4 files

**Step 3**: Add API endpoints (Commit 2)
```bash
# Create src/api.py
cat > src/api.py << 'EOF'
"""REST API endpoints."""

def get_users():
    """Get all users."""
    return [{"id": 1, "name": "Admin"}]

def create_user(name: str):
    """Create new user."""
    return {"id": 2, "name": name}

def delete_user(user_id: int):
    """Delete user."""
    return {"deleted": user_id}
EOF

# Modify src/database.py
cat >> src/database.py << 'EOF'

def query(connection, sql: str):
    """Execute SQL query."""
    print(f"Executing: {sql}")
    return []
EOF

git add .
GIT_COMMITTER_DATE="2025-11-01T14:00:00" git commit --date="2025-11-01T14:00:00" -m "Add API endpoints"
```

**Expected**: Commit 2 with 1 new file, 1 modified file

**Step 4**: Continue through all 12 commits following the pattern above

**Expected**: Complete commit history matching specification

### Validation

**Step 1**: Verify commit count
```bash
cd /tmp/cidx-test-repo
git log --oneline
```

**Expected**: 12 commits listed

**Step 2**: Verify file changes per commit
```bash
# Check commit 6 (refactor)
git show <commit-6-hash> --stat

# Should show:
# src/auth.py | 50 ++++++++++++++++++++++++++++++++++++++++++--------
```

**Expected**: Large changes in auth.py

**Step 3**: Verify deletion (commit 8)
```bash
git show <commit-8-hash> --name-status
```

**Expected**: Output shows `D src/database.py`

**Step 4**: Verify rename (commit 9)
```bash
git show <commit-9-hash> --name-status
```

**Expected**: Output shows `R100 src/db_new.py src/database.py`

**Step 5**: Verify binary file (commit 11)
```bash
git show <commit-11-hash> --stat
```

**Expected**: Shows `docs/architecture.png | Bin 0 -> XXX bytes`

## Implementation Notes

### Script to Create Repository

A shell script will be provided to automate repository creation with exact commit history and file contents.

### Git Configuration

All commits use fixed dates and committer information to ensure reproducibility:
```bash
GIT_COMMITTER_DATE="2025-11-0X THH:00:00"
git commit --date="2025-11-0X THH:00:00"
```

### Binary File Simulation

Since we need a binary file for testing, create a small PNG-like file:
```bash
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' > docs/architecture.png
git add docs/architecture.png
```

## Success Criteria

- [ ] Test repository created successfully
- [ ] All 12 commits present with correct dates
- [ ] File changes match specification
- [ ] Repository can be used for Story 1 and Story 2 testing
- [ ] Script provided for reproducible setup

## Dependencies

None - this is the foundation story for the diff-based temporal indexing epic.

## Estimated Effort

**1-2 hours**: Script creation and validation

## Notes

This test repository will be the **single source of truth** for validating diff-based indexing. Every behavior we implement in Story 1 and Story 2 must work correctly with this repository.
