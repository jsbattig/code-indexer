"""
Manual E2E Testing Script for Story #629: REST API Endpoints

Tests REST endpoints with REAL services (NO MOCKING):
- File CRUD operations (verify delete_file bug fix)
- Git operations (sample endpoints)
- Re-indexing operations

CRITICAL: Tests the delete_file signature fix with real FileCRUDService integration.

Usage:
    python3 tests/manual/test_rest_api_e2e.py
"""

import sys
import os
import tempfile
import shutil
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from fastapi.testclient import TestClient
from code_indexer.server.app import app
from code_indexer.server.repositories.activated_repo_manager import ActivatedRepoManager
from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.auth.user_manager import User, UserRole


class RestAPIE2ETester:
    """Manual E2E tester for REST API endpoints."""

    def __init__(self):
        self.client = TestClient(app)
        self.test_repo_dir = None
        self.test_username = "test_user_rest_e2e"
        self.test_alias = "test_repo_rest_e2e"
        self.activated_repo_manager = ActivatedRepoManager()
        self.passed = []
        self.failed = []

    def setup(self):
        """Setup test environment with real repository."""
        print("\n" + "=" * 80)
        print("SETUP: Creating test repository and user")
        print("=" * 80)

        self.test_repo_dir = tempfile.mkdtemp(prefix="cidx_rest_e2e_")
        print(f"Test repo: {self.test_repo_dir}")

        self._initialize_git_repo()
        self._register_repository()
        self._setup_auth_bypass()
        print("Authentication bypass configured (using dependency override)")

    def _initialize_git_repo(self):
        """Initialize git repository with initial commit."""
        os.system(
            f"cd {self.test_repo_dir} && git init && "
            f"git config user.name 'Test' && "
            f"git config user.email 'test@example.com'"
        )

        test_file = Path(self.test_repo_dir) / "README.md"
        test_file.write_text("# Test Repository\n\nInitial content\n")
        os.system(
            f"cd {self.test_repo_dir} && "
            f"git add README.md && "
            f"git commit -m 'Initial commit'"
        )

    def _register_repository(self):
        """Register repository with ActivatedRepoManager manually."""
        # Create activated repository structure manually
        # This simulates what ActivatedRepoManager does internally
        import json
        from datetime import datetime, timezone

        # Create user directory in activated-repos
        user_dir = Path.home() / ".cidx-server" / "data" / "activated-repos" / self.test_username
        user_dir.mkdir(parents=True, exist_ok=True)

        # Create repository directory
        repo_dir = user_dir / self.test_alias
        if repo_dir.exists():
            shutil.rmtree(repo_dir)

        # Create symlink to test repository
        os.symlink(self.test_repo_dir, str(repo_dir))

        # Create metadata file
        metadata = {
            "user_alias": self.test_alias,
            "golden_repo_alias": "test_golden",
            "current_branch": "master",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat()
        }

        metadata_file = repo_dir.parent / f"{self.test_alias}.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        print(f"Registered repository: {self.test_username}/{self.test_alias}")

    def _setup_auth_bypass(self):
        """Setup authentication bypass using FastAPI dependency override."""
        # Create mock user
        mock_user = User(
            username=self.test_username,
            password_hash="not_used",
            role=UserRole.NORMAL_USER,
            created_at="2025-01-01T00:00:00Z"
        )

        # Override get_current_user dependency to return mock user
        def mock_get_current_user():
            return mock_user

        app.dependency_overrides[get_current_user] = mock_get_current_user

    def teardown(self):
        """Cleanup test environment."""
        print("\n" + "=" * 80)
        print("TEARDOWN: Cleaning up test environment")
        print("=" * 80)

        self._cleanup_auth_bypass()
        self._remove_repository()
        self._remove_test_directory()

    def _cleanup_auth_bypass(self):
        """Cleanup authentication override."""
        app.dependency_overrides.clear()
        print("Authentication override cleared")

    def _remove_repository(self):
        """Remove repository from ActivatedRepoManager manually."""
        try:
            # Remove activated repository structure
            user_dir = Path.home() / ".cidx-server" / "data" / "activated-repos" / self.test_username
            if user_dir.exists():
                # Remove symlink and metadata
                repo_link = user_dir / self.test_alias
                if repo_link.exists():
                    os.unlink(str(repo_link))

                metadata_file = user_dir / f"{self.test_alias}.json"
                if metadata_file.exists():
                    metadata_file.unlink()

                # Remove user directory if empty
                if not any(user_dir.iterdir()):
                    user_dir.rmdir()

            print(f"Removed repository: {self.test_username}/{self.test_alias}")
        except Exception as e:
            print(f"Warning: Failed to remove repository: {e}")

    def _remove_test_directory(self):
        """Remove temporary test directory."""
        if self.test_repo_dir and os.path.exists(self.test_repo_dir):
            shutil.rmtree(self.test_repo_dir)
            print(f"Removed test directory: {self.test_repo_dir}")

    def _auth_headers(self) -> Dict[str, str]:
        """Get authentication headers (not needed with dependency override, but kept for consistency)."""
        return {}

    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _format_hash(self, hash_value: Optional[str]) -> str:
        """Safely format hash for display."""
        if not hash_value:
            return "N/A"
        return hash_value[:16] + "..." if len(hash_value) > 16 else hash_value

    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test result."""
        status_symbol = "PASS" if status == "PASS" else "FAIL"
        print(f"\n{status_symbol} | {test_name}")
        if details:
            print(f"  Details: {details}")

        if status == "PASS":
            self.passed.append(test_name)
        else:
            self.failed.append(test_name)

    # ==========================================================================
    # FILE CRUD TESTS - HELPER METHODS
    # ==========================================================================

    def _test_create_file(self, file_path: str, content: str) -> Optional[str]:
        """Test file creation, return content hash if successful."""
        print(f"\nTesting POST /api/v1/repos/{{alias}}/files (create_file)")
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/files",
            json={"file_path": file_path, "content": content},
            headers=self._auth_headers()
        )

        if response.status_code == 201:
            data = response.json()
            content_hash = data.get("content_hash", "")
            self.log_test(
                "Create File (POST /files)",
                "PASS",
                f"File: {file_path}, hash: {self._format_hash(content_hash)}"
            )
            return content_hash
        else:
            self.log_test(
                "Create File (POST /files)",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return None

    def _verify_file_exists(self, file_path: str) -> bool:
        """Verify file exists on disk."""
        full_path = Path(self.test_repo_dir) / file_path
        exists = full_path.exists()

        self.log_test(
            "Create File - File Existence Check",
            "PASS" if exists else "FAIL",
            f"File {'exists' if exists else 'not found'}: {full_path}"
        )
        return exists

    def _test_edit_file(
        self, file_path: str, old_str: str, new_str: str, hash_val: str
    ) -> Optional[str]:
        """Test file editing, return new hash if successful."""
        print(f"\nTesting PATCH /api/v1/repos/{{alias}}/files/{{path}} (edit_file)")
        response = self.client.patch(
            f"/api/v1/repos/{self.test_alias}/files/{file_path}",
            json={
                "old_string": old_str,
                "new_string": new_str,
                "content_hash": hash_val,
                "replace_all": False
            },
            headers=self._auth_headers()
        )

        if response.status_code == 200:
            data = response.json()
            new_hash = data.get("content_hash", "")
            changes = data.get("changes_made", 0)
            self.log_test(
                "Edit File (PATCH /files/{path})",
                "PASS",
                f"{changes} changes, new hash: {self._format_hash(new_hash)}"
            )
            return new_hash
        else:
            self.log_test(
                "Edit File (PATCH /files/{path})",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return None

    def _verify_file_content(self, file_path: str, expected_substring: str) -> bool:
        """Verify file content contains expected substring."""
        full_path = Path(self.test_repo_dir) / file_path
        content = full_path.read_text()
        contains = expected_substring in content

        self.log_test(
            "Edit File - Content Verification",
            "PASS" if contains else "FAIL",
            f"Content {'updated correctly' if contains else 'not updated'}"
        )
        return contains

    def _test_delete_file(self, file_path: str) -> bool:
        """Test file deletion (CRITICAL - BUG FIX)."""
        print(f"\nTesting DELETE /api/v1/repos/{{alias}}/files/{{path}} (delete_file)")
        print("CRITICAL: This tests the delete_file signature fix")
        print("Service must accept content_hash=None parameter")

        response = self.client.delete(
            f"/api/v1/repos/{self.test_alias}/files/{file_path}",
            headers=self._auth_headers()
        )

        if response.status_code == 200:
            data = response.json()
            deleted_at = data.get("deleted_at", "N/A")
            self.log_test(
                "Delete File (DELETE /files/{path}) - BUG FIX VERIFIED",
                "PASS",
                f"File deleted at {deleted_at}"
            )
            return True
        else:
            self.log_test(
                "Delete File (DELETE /files/{path}) - BUG FIX FAILED",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return False

    def _verify_file_deleted(self, file_path: str) -> bool:
        """Verify file removed from disk."""
        full_path = Path(self.test_repo_dir) / file_path
        deleted = not full_path.exists()

        self.log_test(
            "Delete File - File Removal Verification",
            "PASS" if deleted else "FAIL",
            f"File {'removed' if deleted else 'still exists'}"
        )
        return deleted

    # ==========================================================================
    # FILE CRUD TESTS - MAIN TESTS
    # ==========================================================================

    def test_file_crud_lifecycle(self):
        """Test complete file CRUD lifecycle with REAL FileCRUDService."""
        print("\n" + "=" * 80)
        print("TEST 1: File CRUD Lifecycle (CREATE → EDIT → DELETE)")
        print("=" * 80)

        test_file_path = "test_crud/sample.txt"
        test_content = "Hello, World!\n"

        # Create file
        content_hash = self._test_create_file(test_file_path, test_content)
        if not content_hash:
            return

        if not self._verify_file_exists(test_file_path):
            return

        # Edit file
        new_hash = self._test_edit_file(
            test_file_path, "Hello", "Goodbye", content_hash
        )
        if not new_hash:
            return

        if not self._verify_file_content(test_file_path, "Goodbye"):
            return

        # Delete file (CRITICAL - BUG FIX TEST)
        if not self._test_delete_file(test_file_path):
            return

        self._verify_file_deleted(test_file_path)

    def test_file_crud_error_handling(self):
        """Test file CRUD error handling."""
        print("\n" + "=" * 80)
        print("TEST 2: File CRUD Error Handling")
        print("=" * 80)

        self._test_duplicate_file_error()
        self._test_edit_nonexistent_file_error()
        self._test_delete_nonexistent_file_error()
        self._test_git_directory_blocking()

    def _test_duplicate_file_error(self):
        """Test duplicate file creation returns 409 Conflict."""
        print("\n2.1 Testing duplicate file creation (409 Conflict)")
        duplicate_path = "duplicate.txt"

        self.client.post(
            f"/api/v1/repos/{self.test_alias}/files",
            json={"file_path": duplicate_path, "content": "First"},
            headers=self._auth_headers()
        )

        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/files",
            json={"file_path": duplicate_path, "content": "Second"},
            headers=self._auth_headers()
        )

        status = "PASS" if response.status_code == 409 else "FAIL"
        details = (
            f"Correctly rejected duplicate: {response.json()}"
            if status == "PASS"
            else f"Expected 409, got {response.status_code}"
        )
        self.log_test("File Already Exists (409 Conflict)", status, details)

    def _test_edit_nonexistent_file_error(self):
        """Test editing non-existent file returns 404."""
        print("\n2.2 Testing edit non-existent file (404 Not Found)")
        response = self.client.patch(
            f"/api/v1/repos/{self.test_alias}/files/nonexistent.txt",
            json={
                "old_string": "foo",
                "new_string": "bar",
                "content_hash": "fakehash",
                "replace_all": False
            },
            headers=self._auth_headers()
        )

        status = "PASS" if response.status_code == 404 else "FAIL"
        details = (
            f"Correctly rejected: {response.json()}"
            if status == "PASS"
            else f"Expected 404, got {response.status_code}"
        )
        self.log_test("Edit Non-Existent File (404 Not Found)", status, details)

    def _test_delete_nonexistent_file_error(self):
        """Test deleting non-existent file returns 404."""
        print("\n2.3 Testing delete non-existent file (404 Not Found)")
        response = self.client.delete(
            f"/api/v1/repos/{self.test_alias}/files/nonexistent_delete.txt",
            headers=self._auth_headers()
        )

        status = "PASS" if response.status_code == 404 else "FAIL"
        details = (
            f"Correctly rejected: {response.json()}"
            if status == "PASS"
            else f"Expected 404, got {response.status_code}"
        )
        self.log_test("Delete Non-Existent File (404 Not Found)", status, details)

    def _test_git_directory_blocking(self):
        """Test .git/ directory access is blocked with 403."""
        print("\n2.4 Testing .git/ directory blocking (403 Forbidden)")
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/files",
            json={"file_path": ".git/malicious.txt", "content": "Bad"},
            headers=self._auth_headers()
        )

        status = "PASS" if response.status_code == 403 else "FAIL"
        details = (
            f"Correctly blocked: {response.json()}"
            if status == "PASS"
            else f"Expected 403, got {response.status_code}"
        )
        self.log_test("Block .git/ Access (403 Forbidden)", status, details)

    # ==========================================================================
    # GIT OPERATIONS TESTS
    # ==========================================================================

    def test_git_operations_sample(self):
        """Test sample git operations with REAL GitOperationsService."""
        print("\n" + "=" * 80)
        print("TEST 3: Git Operations (Sample Endpoints)")
        print("=" * 80)

        self._test_git_status()
        self._prepare_git_test_file()
        self._test_git_stage()
        self._test_git_commit()

    def _test_git_status(self):
        """Test GET /api/v1/repos/{alias}/git/status."""
        print("\n3.1 Testing GET /api/v1/repos/{alias}/git/status")
        response = self.client.get(
            f"/api/v1/repos/{self.test_alias}/git/status",
            headers=self._auth_headers()
        )

        if response.status_code == 200:
            data = response.json()
            branch = data.get("branch", "N/A")
            is_clean = data.get("is_clean", "N/A")
            self.log_test(
                "Git Status (GET /git/status)",
                "PASS",
                f"Status: {branch}, Clean: {is_clean}"
            )
        else:
            self.log_test(
                "Git Status (GET /git/status)",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )

    def _prepare_git_test_file(self):
        """Create a test file for git operations."""
        test_git_file = Path(self.test_repo_dir) / "git_test.txt"
        test_git_file.write_text("Testing git operations\n")

    def _test_git_stage(self):
        """Test POST /api/v1/repos/{alias}/git/stage."""
        print("\n3.2 Testing POST /api/v1/repos/{alias}/git/stage")
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/stage",
            json={"file_paths": ["git_test.txt"]},
            headers=self._auth_headers()
        )

        if response.status_code == 200:
            data = response.json()
            files_staged = data.get("files_staged", [])
            self.log_test(
                "Git Stage (POST /git/stage)",
                "PASS",
                f"Files staged: {files_staged}"
            )
        else:
            self.log_test(
                "Git Stage (POST /git/stage)",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )

    def _test_git_commit(self):
        """Test POST /api/v1/repos/{alias}/git/commit."""
        print("\n3.3 Testing POST /api/v1/repos/{alias}/git/commit")
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/commit",
            json={"message": "Test commit from REST API E2E"},
            headers=self._auth_headers()
        )

        if response.status_code == 201:
            data = response.json()
            commit_hash = data.get("commit_hash", "N/A")
            message = data.get("message", "N/A")
            hash_short = commit_hash[:8] if commit_hash != "N/A" else "N/A"
            self.log_test(
                "Git Commit (POST /git/commit)",
                "PASS",
                f"Commit: {hash_short}, message: {message}"
            )
        else:
            self.log_test(
                "Git Commit (POST /git/commit)",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )

    # ==========================================================================
    # INDEXING TESTS
    # ==========================================================================

    def test_indexing_operations_sample(self):
        """Test sample indexing operations."""
        print("\n" + "=" * 80)
        print("TEST 4: Indexing Operations (Sample Endpoints)")
        print("=" * 80)

        self._test_index_status()

    def _test_index_status(self):
        """Test GET /api/v1/repos/{alias}/index-status."""
        print("\n4.1 Testing GET /api/v1/repos/{alias}/index-status")
        response = self.client.get(
            f"/api/v1/repos/{self.test_alias}/index-status",
            headers=self._auth_headers()
        )

        if response.status_code == 200:
            data = response.json()
            semantic = data.get("semantic", {}).get("exists", False)
            fts = data.get("fts", {}).get("exists", False)
            self.log_test(
                "Index Status (GET /index-status)",
                "PASS",
                f"Semantic: {semantic}, FTS: {fts}"
            )
        else:
            self.log_test(
                "Index Status (GET /index-status)",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )

    # ==========================================================================
    # AUTHENTICATION TESTS
    # ==========================================================================

    def test_authentication_enforcement(self):
        """Test that endpoints require authentication."""
        print("\n" + "=" * 80)
        print("TEST 5: Authentication Enforcement")
        print("=" * 80)

        print("\n5.1 Testing endpoints without authentication token")

        # Temporarily remove auth override to test 401 response
        saved_overrides = app.dependency_overrides.copy()
        app.dependency_overrides.clear()

        try:
            response = self.client.get(
                f"/api/v1/repos/{self.test_alias}/git/status"
            )

            status = "PASS" if response.status_code == 401 else "FAIL"
            details = (
                "Correctly rejected unauthenticated request"
                if status == "PASS"
                else f"Expected 401, got {response.status_code}"
            )
            self.log_test("Authentication Required (401 Unauthorized)", status, details)
        finally:
            # Restore auth override
            app.dependency_overrides = saved_overrides

    # ==========================================================================
    # GIT BRANCH OPERATIONS TESTS
    # ==========================================================================

    def test_git_branch_operations(self):
        """Test git branch operations (list, create, switch, delete)."""
        print("\n" + "=" * 80)
        print("TEST 6: Git Branch Operations")
        print("=" * 80)

        self._test_branch_list()
        branch_created = self._test_branch_create()
        if branch_created:
            self._test_branch_switch()
            self._test_branch_delete()

    def _test_branch_list(self):
        """Test GET /api/v1/repos/{alias}/git/branches."""
        print("\n6.1 Testing GET /api/v1/repos/{alias}/git/branches")
        response = self.client.get(
            f"/api/v1/repos/{self.test_alias}/git/branches",
            headers=self._auth_headers()
        )

        if response.status_code != 200:
            self.log_test(
                "Git Branch List (GET /git/branches)",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        current = data.get("current", "N/A")
        local_branches = data.get("local", [])
        self.log_test(
            "Git Branch List (GET /git/branches)",
            "PASS",
            f"Current: {current}, Branches: {len(local_branches)}"
        )

    def _test_branch_create(self) -> bool:
        """Test POST /api/v1/repos/{alias}/git/branches."""
        print("\n6.2 Testing POST /api/v1/repos/{alias}/git/branches")
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/branches",
            json={"branch_name": "feature-test-e2e"},
            headers=self._auth_headers()
        )

        if response.status_code != 201:
            self.log_test(
                "Git Branch Create (POST /git/branches)",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return False

        data = response.json()
        created_branch = data.get("created_branch", "N/A")
        self.log_test(
            "Git Branch Create (POST /git/branches)",
            "PASS",
            f"Created branch: {created_branch}"
        )
        return True

    def _test_branch_switch(self):
        """Test POST /api/v1/repos/{alias}/git/branches/{branch}/switch."""
        print("\n6.3 Testing POST /api/v1/repos/{alias}/git/branches/{branch}/switch")
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/branches/feature-test-e2e/switch",
            headers=self._auth_headers()
        )

        if response.status_code != 200:
            self.log_test(
                "Git Branch Switch (POST /git/branches/{branch}/switch)",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        current_branch = data.get("current_branch", "N/A")
        previous_branch = data.get("previous_branch", "N/A")
        self.log_test(
            "Git Branch Switch (POST /git/branches/{branch}/switch)",
            "PASS",
            f"Switched from {previous_branch} to {current_branch}"
        )

        # Switch back to master
        self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/branches/master/switch",
            headers=self._auth_headers()
        )

    def _test_branch_delete(self):
        """Test DELETE /api/v1/repos/{alias}/git/branches/{branch} with confirmation token."""
        print("\n6.4 Testing DELETE /api/v1/repos/{alias}/git/branches/{branch}")

        # First request - should return confirmation token
        response = self.client.delete(
            f"/api/v1/repos/{self.test_alias}/git/branches/feature-test-e2e",
            headers=self._auth_headers()
        )

        if response.status_code != 200:
            self.log_test(
                "Git Branch Delete (DELETE /git/branches/{branch})",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        requires_confirmation = data.get("requires_confirmation", False)
        token = data.get("token")

        if not requires_confirmation or not token:
            self.log_test(
                "Git Branch Delete (DELETE /git/branches/{branch})",
                "FAIL",
                "Expected confirmation token"
            )
            return

        # Second request with token
        response = self.client.delete(
            f"/api/v1/repos/{self.test_alias}/git/branches/feature-test-e2e?confirmation_token={token}",
            headers=self._auth_headers()
        )

        if response.status_code != 200:
            self.log_test(
                "Git Branch Delete (DELETE /git/branches/{branch})",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        deleted_branch = data.get("deleted_branch", "N/A")
        self.log_test(
            "Git Branch Delete (DELETE /git/branches/{branch})",
            "PASS",
            f"Deleted branch: {deleted_branch}"
        )

    # ==========================================================================
    # GIT RECOVERY OPERATIONS TESTS
    # ==========================================================================

    def test_git_recovery_operations(self):
        """Test git recovery operations with confirmation tokens."""
        print("\n" + "=" * 80)
        print("TEST 7: Git Recovery Operations")
        print("=" * 80)

        self._test_git_clean_with_token()
        self._test_git_reset_with_token()

    def _test_git_clean_with_token(self):
        """Test POST /api/v1/repos/{alias}/git/clean with confirmation token."""
        print("\n7.1 Testing POST /api/v1/repos/{alias}/git/clean (with confirmation)")

        # Create untracked file
        test_file = Path(self.test_repo_dir) / "untracked.txt"
        test_file.write_text("Untracked file for git clean test")

        # First request - should return confirmation token
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/clean",
            json={},
            headers=self._auth_headers()
        )

        if response.status_code != 200:
            self.log_test(
                "Git Clean (POST /git/clean) - request token",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        requires_confirmation = data.get("requires_confirmation", False)
        token = data.get("token")

        if not requires_confirmation or not token:
            self.log_test(
                "Git Clean (POST /git/clean) - request token",
                "FAIL",
                "Expected confirmation token"
            )
            return

        # Second request with confirmation token
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/clean",
            json={"confirmation_token": token},
            headers=self._auth_headers()
        )

        if response.status_code != 200:
            self.log_test(
                "Git Clean (POST /git/clean) - with token",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        removed_files = data.get("removed_files", [])
        self.log_test(
            "Git Clean (POST /git/clean) - with token",
            "PASS",
            f"Removed {len(removed_files)} untracked files"
        )

    def _test_git_reset_with_token(self):
        """Test POST /api/v1/repos/{alias}/git/reset with confirmation token."""
        print("\n7.2 Testing POST /api/v1/repos/{alias}/git/reset --hard (with confirmation)")

        # Make a dirty change to README.md
        readme_path = Path(self.test_repo_dir) / "README.md"
        if not readme_path.exists():
            self.log_test(
                "Git Reset --hard (POST /git/reset) - setup",
                "FAIL",
                "README.md not found for reset test"
            )
            return

        original_content = readme_path.read_text()
        readme_path.write_text(original_content + "\nDirty change for reset test\n")

        # First request - should return confirmation token
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/reset",
            json={"mode": "hard"},
            headers=self._auth_headers()
        )

        if response.status_code != 200:
            self.log_test(
                "Git Reset --hard (POST /git/reset) - request token",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        requires_confirmation = data.get("requires_confirmation", False)
        token = data.get("token")

        if not requires_confirmation or not token:
            self.log_test(
                "Git Reset --hard (POST /git/reset) - request token",
                "FAIL",
                "Expected confirmation token"
            )
            return

        # Second request with confirmation token
        response = self.client.post(
            f"/api/v1/repos/{self.test_alias}/git/reset",
            json={"mode": "hard", "confirmation_token": token},
            headers=self._auth_headers()
        )

        if response.status_code != 200:
            self.log_test(
                "Git Reset --hard (POST /git/reset) - with token",
                "FAIL",
                f"HTTP {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        reset_mode = data.get("reset_mode", "N/A")
        self.log_test(
            "Git Reset --hard (POST /git/reset) - with token",
            "PASS",
            f"Reset completed with mode: {reset_mode}"
        )

    # ==========================================================================
    # MAIN EXECUTION
    # ==========================================================================

    def run_all_tests(self):
        """Run all manual E2E tests."""
        print("\n" + "=" * 80)
        print("STORY #629 REST API E2E TESTING")
        print("Testing with REAL services (NO MOCKING)")
        print("=" * 80)

        try:
            self.setup()

            self.test_file_crud_lifecycle()
            self.test_file_crud_error_handling()
            self.test_git_operations_sample()
            self.test_indexing_operations_sample()
            self.test_authentication_enforcement()
            self.test_git_branch_operations()
            self.test_git_recovery_operations()

            return self._print_summary()

        finally:
            self.teardown()

    def _print_summary(self) -> int:
        """Print test summary and return exit code."""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"PASSED: {len(self.passed)}")
        print(f"FAILED: {len(self.failed)}")

        if self.failed:
            print("\nFailed tests:")
            for test_name in self.failed:
                print(f"  - {test_name}")
            print("\nOVERALL STATUS: FAILED")
            return 1
        else:
            print("\nOVERALL STATUS: ALL TESTS PASSED")
            return 0


if __name__ == "__main__":
    tester = RestAPIE2ETester()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)
