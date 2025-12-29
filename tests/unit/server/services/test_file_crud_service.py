"""
Unit tests for FileCRUDService.

Tests file CRUD operations following TDD methodology with:
- Real file system operations (no mocks per CLAUDE.md Foundation #1)
- Security validation (path traversal, .git directory blocking)
- Optimistic concurrency control (hash-based locking)
- Atomic file operations

Test coverage targets:
- Custom exception classes
- Hash computation
- Path validation
- create_file method
- edit_file method
- delete_file method
"""

import hashlib
import tempfile
from pathlib import Path

import pytest

# Import will fail initially (TDD red phase)
try:
    from src.code_indexer.server.services.file_crud_service import (
        FileCRUDService,
        HashMismatchError,
        CRUDOperationError,
    )
except ImportError:
    # Expected during TDD red phase
    FileCRUDService = None  # type: ignore
    HashMismatchError = None  # type: ignore
    CRUDOperationError = None  # type: ignore


@pytest.fixture
def test_repo_dir():
    """Create a temporary test repository directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "test-repo"
        repo_dir.mkdir()

        # Create a mock activated repository setup
        # This simulates the structure created by ActivatedRepoManager
        test_file = repo_dir / "example.py"
        test_file.write_text("print('hello')")

        yield str(repo_dir)


@pytest.fixture
def service_with_mock_repo(test_repo_dir, monkeypatch):
    """Create FileCRUDService with mocked ActivatedRepoManager."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    # Mock get_activated_repo_path to return our test repo
    def mock_get_path(username, user_alias):
        return test_repo_dir

    monkeypatch.setattr(
        service.activated_repo_manager, "get_activated_repo_path", mock_get_path
    )

    return service


# ============================================================================
# TEST GROUP 1: Custom Exception Classes
# ============================================================================


def test_hash_mismatch_error_is_exception():
    """HashMismatchError should be a subclass of Exception."""
    if HashMismatchError is None:
        pytest.skip("HashMismatchError not yet implemented (TDD red phase)")

    assert issubclass(HashMismatchError, Exception)


def test_crud_operation_error_is_exception():
    """CRUDOperationError should be a subclass of Exception."""
    if CRUDOperationError is None:
        pytest.skip("CRUDOperationError not yet implemented (TDD red phase)")

    assert issubclass(CRUDOperationError, Exception)


def test_hash_mismatch_error_can_be_raised():
    """HashMismatchError can be raised and caught."""
    if HashMismatchError is None:
        pytest.skip("HashMismatchError not yet implemented (TDD red phase)")

    with pytest.raises(HashMismatchError) as exc_info:
        raise HashMismatchError("Hash validation failed")

    assert "Hash validation failed" in str(exc_info.value)


# ============================================================================
# TEST GROUP 2: Hash Computation (_compute_hash)
# ============================================================================


def test_compute_hash_returns_sha256_hex():
    """_compute_hash should return SHA-256 hex digest."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()
    content = b"test content"

    result = service._compute_hash(content)
    expected = hashlib.sha256(content).hexdigest()

    assert result == expected


def test_compute_hash_consistent_for_same_content():
    """_compute_hash should produce consistent results."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()
    content = b"hello world"

    hash1 = service._compute_hash(content)
    hash2 = service._compute_hash(content)

    assert hash1 == hash2


def test_compute_hash_different_for_different_content():
    """_compute_hash should produce different hashes for different content."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    hash1 = service._compute_hash(b"content1")
    hash2 = service._compute_hash(b"content2")

    assert hash1 != hash2


# ============================================================================
# TEST GROUP 3: Path Validation (_validate_crud_path)
# ============================================================================


def test_validate_crud_path_blocks_git_directory():
    """_validate_crud_path should block .git/ directory access."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    with pytest.raises(PermissionError) as exc_info:
        service._validate_crud_path(".git/config", "test_operation")

    assert ".git" in str(exc_info.value).lower()


def test_validate_crud_path_blocks_git_subdirectory():
    """_validate_crud_path should block .git/ subdirectory access."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    with pytest.raises(PermissionError) as exc_info:
        service._validate_crud_path(".git/objects/abc123", "test_operation")

    assert ".git" in str(exc_info.value).lower()


def test_validate_crud_path_blocks_path_traversal():
    """_validate_crud_path should block path traversal attempts."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    with pytest.raises(PermissionError) as exc_info:
        service._validate_crud_path("../../etc/passwd", "test_operation")

    assert "traversal" in str(exc_info.value).lower()


def test_validate_crud_path_blocks_parent_reference():
    """_validate_crud_path should block parent directory references."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    with pytest.raises(PermissionError) as exc_info:
        service._validate_crud_path("foo/../bar/../../etc/passwd", "test_operation")

    assert "traversal" in str(exc_info.value).lower()


def test_validate_crud_path_allows_normal_paths():
    """_validate_crud_path should allow normal relative paths."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    # Should not raise
    service._validate_crud_path("src/main.py", "test_operation")
    service._validate_crud_path("tests/test_foo.py", "test_operation")
    service._validate_crud_path("README.md", "test_operation")


def test_validate_crud_path_allows_gitignore():
    """_validate_crud_path should allow .gitignore files (not .git/ directory)."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    # Should not raise - .gitignore is a legitimate file
    service._validate_crud_path(".gitignore", "test_operation")
    service._validate_crud_path("src/.gitignore", "test_operation")
    service._validate_crud_path(".gitattributes", "test_operation")


def test_validate_crud_path_allows_github_directory():
    """_validate_crud_path should allow .github/ directory files (not .git/ directory)."""
    if FileCRUDService is None:
        pytest.skip("FileCRUDService not yet implemented (TDD red phase)")

    service = FileCRUDService()

    # Should not raise - .github/ is for GitHub Actions/config
    service._validate_crud_path(".github/workflows/ci.yml", "test_operation")
    service._validate_crud_path(".github/dependabot.yml", "test_operation")
    service._validate_crud_path(".github/ISSUE_TEMPLATE/bug.md", "test_operation")


# ============================================================================
# TEST GROUP 4: create_file Method
# ============================================================================


def test_create_file_success(service_with_mock_repo, test_repo_dir):
    """create_file should successfully create a new file."""
    service = service_with_mock_repo

    result = service.create_file(
        repo_alias="test-repo",
        file_path="new_file.py",
        content="def hello():\n    pass",
        username="testuser",
    )

    # Verify result structure
    assert result["success"] is True
    assert result["file_path"] == "new_file.py"
    assert "content_hash" in result
    assert "size_bytes" in result
    assert "created_at" in result

    # Verify file was actually created
    created_file = Path(test_repo_dir) / "new_file.py"
    assert created_file.exists()
    assert created_file.read_text() == "def hello():\n    pass"


def test_create_file_creates_parent_directories(service_with_mock_repo, test_repo_dir):
    """create_file should create parent directories if they don't exist."""
    service = service_with_mock_repo

    result = service.create_file(
        repo_alias="test-repo",
        file_path="deep/nested/path/file.py",
        content="# nested file",
        username="testuser",
    )

    assert result["success"] is True

    # Verify nested file was created
    nested_file = Path(test_repo_dir) / "deep" / "nested" / "path" / "file.py"
    assert nested_file.exists()
    assert nested_file.read_text() == "# nested file"


def test_create_file_raises_for_existing_file(service_with_mock_repo, test_repo_dir):
    """create_file should raise FileExistsError if file already exists."""
    service = service_with_mock_repo

    # Create file first time
    service.create_file(
        repo_alias="test-repo",
        file_path="existing.py",
        content="original content",
        username="testuser",
    )

    # Attempt to create same file again
    with pytest.raises(FileExistsError) as exc_info:
        service.create_file(
            repo_alias="test-repo",
            file_path="existing.py",
            content="new content",
            username="testuser",
        )

    assert "existing.py" in str(exc_info.value)


def test_create_file_blocks_git_directory(service_with_mock_repo):
    """create_file should block attempts to create files in .git/ directory."""
    service = service_with_mock_repo

    with pytest.raises(PermissionError) as exc_info:
        service.create_file(
            repo_alias="test-repo",
            file_path=".git/malicious.txt",
            content="bad content",
            username="testuser",
        )

    assert ".git" in str(exc_info.value).lower()


def test_create_file_blocks_path_traversal(service_with_mock_repo):
    """create_file should block path traversal attempts."""
    service = service_with_mock_repo

    with pytest.raises(PermissionError) as exc_info:
        service.create_file(
            repo_alias="test-repo",
            file_path="../../etc/passwd",
            content="malicious",
            username="testuser",
        )

    assert "traversal" in str(exc_info.value).lower()


def test_create_file_atomic_write(service_with_mock_repo, test_repo_dir):
    """create_file should use atomic write operations (temp file + rename)."""
    service = service_with_mock_repo

    # Create a file with substantial content
    content = "x" * 10000

    service.create_file(
        repo_alias="test-repo",
        file_path="atomic_test.txt",
        content=content,
        username="testuser",
    )

    # Verify file exists with correct content
    test_file = Path(test_repo_dir) / "atomic_test.txt"
    assert test_file.exists()
    assert test_file.read_text() == content

    # Verify no temp files left behind
    temp_files = list(Path(test_repo_dir).rglob("*.tmp"))
    assert len(temp_files) == 0


def test_create_file_returns_correct_hash(service_with_mock_repo):
    """create_file should return correct SHA-256 hash of content."""
    service = service_with_mock_repo

    content = "test content for hashing"
    expected_hash = hashlib.sha256(content.encode()).hexdigest()

    result = service.create_file(
        repo_alias="test-repo",
        file_path="hash_test.txt",
        content=content,
        username="testuser",
    )

    assert result["content_hash"] == expected_hash


# ============================================================================
# TEST GROUP 5: edit_file Method
# ============================================================================


def test_edit_file_single_replace_success(service_with_mock_repo, test_repo_dir):
    """edit_file should successfully replace a unique string occurrence."""
    service = service_with_mock_repo

    # Create initial file
    initial_content = "def foo():\n    return 42"
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="edit_test.py",
        content=initial_content,
        username="testuser",
    )

    # Edit the file
    result = service.edit_file(
        repo_alias="test-repo",
        file_path="edit_test.py",
        old_string="return 42",
        new_string="return 100",
        content_hash=create_result["content_hash"],
        replace_all=False,
        username="testuser",
    )

    assert result["success"] is True
    assert result["changes_made"] == 1
    assert "content_hash" in result
    assert "modified_at" in result

    # Verify file content changed
    edited_file = Path(test_repo_dir) / "edit_test.py"
    assert "return 100" in edited_file.read_text()
    assert "return 42" not in edited_file.read_text()


def test_edit_file_replace_all_success(service_with_mock_repo, test_repo_dir):
    """edit_file should replace all occurrences when replace_all=True."""
    service = service_with_mock_repo

    # Create file with multiple occurrences
    initial_content = "foo\nfoo\nfoo"
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="multi_replace.txt",
        content=initial_content,
        username="testuser",
    )

    # Edit with replace_all=True
    result = service.edit_file(
        repo_alias="test-repo",
        file_path="multi_replace.txt",
        old_string="foo",
        new_string="bar",
        content_hash=create_result["content_hash"],
        replace_all=True,
        username="testuser",
    )

    assert result["success"] is True
    assert result["changes_made"] == 3

    # Verify all occurrences replaced
    edited_file = Path(test_repo_dir) / "multi_replace.txt"
    content = edited_file.read_text()
    assert content == "bar\nbar\nbar"


def test_edit_file_hash_mismatch_raises_error(service_with_mock_repo):
    """edit_file should raise HashMismatchError for invalid content_hash."""
    service = service_with_mock_repo

    # Create initial file
    service.create_file(
        repo_alias="test-repo",
        file_path="hash_test.py",
        content="original content",
        username="testuser",
    )

    # Attempt edit with wrong hash
    with pytest.raises(HashMismatchError) as exc_info:
        service.edit_file(
            repo_alias="test-repo",
            file_path="hash_test.py",
            old_string="original",
            new_string="modified",
            content_hash="invalid_hash_12345",
            replace_all=False,
            username="testuser",
        )

    assert "hash mismatch" in str(exc_info.value).lower()


def test_edit_file_non_unique_match_raises_error(service_with_mock_repo):
    """edit_file should raise ValueError for non-unique match without replace_all."""
    service = service_with_mock_repo

    # Create file with duplicate strings
    initial_content = "test\ntest\ntest"
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="duplicate.txt",
        content=initial_content,
        username="testuser",
    )

    # Attempt single replace on non-unique string
    with pytest.raises(ValueError) as exc_info:
        service.edit_file(
            repo_alias="test-repo",
            file_path="duplicate.txt",
            old_string="test",
            new_string="modified",
            content_hash=create_result["content_hash"],
            replace_all=False,
            username="testuser",
        )

    assert (
        "not unique" in str(exc_info.value).lower()
        or "multiple" in str(exc_info.value).lower()
    )


def test_edit_file_updates_hash(service_with_mock_repo):
    """edit_file should return new hash after modification."""
    service = service_with_mock_repo

    # Create initial file
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="hash_update.txt",
        content="before",
        username="testuser",
    )

    initial_hash = create_result["content_hash"]

    # Edit file
    edit_result = service.edit_file(
        repo_alias="test-repo",
        file_path="hash_update.txt",
        old_string="before",
        new_string="after",
        content_hash=initial_hash,
        replace_all=False,
        username="testuser",
    )

    new_hash = edit_result["content_hash"]

    # Hash should be different
    assert new_hash != initial_hash

    # New hash should match actual file content
    expected_hash = hashlib.sha256(b"after").hexdigest()
    assert new_hash == expected_hash


def test_edit_file_atomic_write(service_with_mock_repo, test_repo_dir):
    """edit_file should use atomic write operations."""
    service = service_with_mock_repo

    # Create initial file
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="atomic_edit.txt",
        content="x" * 5000,
        username="testuser",
    )

    # Edit with large content
    service.edit_file(
        repo_alias="test-repo",
        file_path="atomic_edit.txt",
        old_string="x" * 5000,
        new_string="y" * 5000,
        content_hash=create_result["content_hash"],
        replace_all=False,
        username="testuser",
    )

    # Verify no temp files left behind
    temp_files = list(Path(test_repo_dir).rglob("*.tmp"))
    assert len(temp_files) == 0


# ============================================================================
# TEST GROUP 6: delete_file Method
# ============================================================================


def test_delete_file_success(service_with_mock_repo, test_repo_dir):
    """delete_file should successfully delete a file."""
    service = service_with_mock_repo

    # Create file to delete
    service.create_file(
        repo_alias="test-repo",
        file_path="to_delete.txt",
        content="delete me",
        username="testuser",
    )

    # Delete file
    result = service.delete_file(
        repo_alias="test-repo",
        file_path="to_delete.txt",
        content_hash=None,
        username="testuser",
    )

    assert result["success"] is True
    assert result["file_path"] == "to_delete.txt"
    assert "deleted_at" in result

    # Verify file was deleted
    deleted_file = Path(test_repo_dir) / "to_delete.txt"
    assert not deleted_file.exists()


def test_delete_file_with_hash_validation(service_with_mock_repo, test_repo_dir):
    """delete_file should validate hash before deletion when provided."""
    service = service_with_mock_repo

    # Create file
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="hash_delete.txt",
        content="validate before delete",
        username="testuser",
    )

    # Delete with correct hash
    result = service.delete_file(
        repo_alias="test-repo",
        file_path="hash_delete.txt",
        content_hash=create_result["content_hash"],
        username="testuser",
    )

    assert result["success"] is True

    # Verify file deleted
    deleted_file = Path(test_repo_dir) / "hash_delete.txt"
    assert not deleted_file.exists()


def test_delete_file_hash_mismatch_raises_error(service_with_mock_repo, test_repo_dir):
    """delete_file should raise HashMismatchError for invalid hash."""
    service = service_with_mock_repo

    # Create file
    service.create_file(
        repo_alias="test-repo",
        file_path="protected.txt",
        content="protected content",
        username="testuser",
    )

    # Attempt delete with wrong hash
    with pytest.raises(HashMismatchError) as exc_info:
        service.delete_file(
            repo_alias="test-repo",
            file_path="protected.txt",
            content_hash="wrong_hash_abc123",
            username="testuser",
        )

    assert "hash mismatch" in str(exc_info.value).lower()

    # Verify file still exists
    protected_file = Path(test_repo_dir) / "protected.txt"
    assert protected_file.exists()


def test_delete_file_not_found_raises_error(service_with_mock_repo):
    """delete_file should raise FileNotFoundError for non-existent file."""
    service = service_with_mock_repo

    with pytest.raises(FileNotFoundError) as exc_info:
        service.delete_file(
            repo_alias="test-repo",
            file_path="nonexistent.txt",
            content_hash=None,
            username="testuser",
        )

    assert "nonexistent.txt" in str(exc_info.value)


def test_delete_file_blocks_git_directory(service_with_mock_repo):
    """delete_file should block deletion of files in .git/ directory."""
    service = service_with_mock_repo

    with pytest.raises(PermissionError) as exc_info:
        service.delete_file(
            repo_alias="test-repo",
            file_path=".git/config",
            content_hash=None,
            username="testuser",
        )

    assert ".git" in str(exc_info.value).lower()


def test_delete_file_blocks_path_traversal(service_with_mock_repo):
    """delete_file should block path traversal attempts."""
    service = service_with_mock_repo

    with pytest.raises(PermissionError) as exc_info:
        service.delete_file(
            repo_alias="test-repo",
            file_path="../../etc/passwd",
            content_hash=None,
            username="testuser",
        )

    assert "traversal" in str(exc_info.value).lower()


# ============================================================================
# TEST GROUP 7: Integration Tests - Full CRUD Lifecycle
# ============================================================================


def test_crud_lifecycle_integration(service_with_mock_repo, test_repo_dir):
    """Test complete create -> edit -> delete lifecycle."""
    service = service_with_mock_repo

    # Step 1: Create file
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="lifecycle.py",
        content="def original():\n    return 1",
        username="testuser",
    )

    assert create_result["success"] is True
    lifecycle_file = Path(test_repo_dir) / "lifecycle.py"
    assert lifecycle_file.exists()

    # Step 2: Edit file
    edit_result = service.edit_file(
        repo_alias="test-repo",
        file_path="lifecycle.py",
        old_string="return 1",
        new_string="return 2",
        content_hash=create_result["content_hash"],
        replace_all=False,
        username="testuser",
    )

    assert edit_result["success"] is True
    assert "return 2" in lifecycle_file.read_text()

    # Step 3: Delete file
    delete_result = service.delete_file(
        repo_alias="test-repo",
        file_path="lifecycle.py",
        content_hash=edit_result["content_hash"],
        username="testuser",
    )

    assert delete_result["success"] is True
    assert not lifecycle_file.exists()


def test_concurrent_edit_conflict_simulation(service_with_mock_repo):
    """Simulate concurrent edit conflict via hash mismatch."""
    service = service_with_mock_repo

    # User A creates file
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="concurrent.txt",
        content="version 1",
        username="userA",
    )

    hash_v1 = create_result["content_hash"]

    # User A edits file
    edit_a_result = service.edit_file(
        repo_alias="test-repo",
        file_path="concurrent.txt",
        old_string="version 1",
        new_string="version 2 by A",
        content_hash=hash_v1,
        replace_all=False,
        username="userA",
    )

    hash_v2 = edit_a_result["content_hash"]

    # User B attempts edit with stale hash (v1)
    # This simulates B reading the file before A's edit
    with pytest.raises(HashMismatchError):
        service.edit_file(
            repo_alias="test-repo",
            file_path="concurrent.txt",
            old_string="version 1",
            new_string="version 2 by B",
            content_hash=hash_v1,  # Stale hash
            replace_all=False,
            username="userB",
        )

    # User B must use current hash (v2)
    edit_b_result = service.edit_file(
        repo_alias="test-repo",
        file_path="concurrent.txt",
        old_string="version 2 by A",
        new_string="version 3 by B",
        content_hash=hash_v2,  # Current hash
        replace_all=False,
        username="userB",
    )

    assert edit_b_result["success"] is True


# ============================================================================
# TEST GROUP 8: Edge Cases for Coverage
# ============================================================================


def test_validate_crud_path_blocks_absolute_paths(service_with_mock_repo):
    """_validate_crud_path should block absolute paths."""
    service = service_with_mock_repo

    with pytest.raises(PermissionError) as exc_info:
        service._validate_crud_path("/etc/passwd", "test_operation")

    assert "absolute" in str(exc_info.value).lower()


def test_edit_file_string_not_found_raises_error(service_with_mock_repo):
    """edit_file should raise ValueError if old_string not found."""
    service = service_with_mock_repo

    # Create file
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path="search_test.txt",
        content="hello world",
        username="testuser",
    )

    # Attempt to replace non-existent string
    with pytest.raises(ValueError) as exc_info:
        service.edit_file(
            repo_alias="test-repo",
            file_path="search_test.txt",
            old_string="goodbye",
            new_string="farewell",
            content_hash=create_result["content_hash"],
            replace_all=False,
            username="testuser",
        )

    assert "not found" in str(exc_info.value).lower()


# ============================================================================
# TEST GROUP 9: Comprehensive Edge Cases for Path Validation Fix
# ============================================================================


def test_validate_crud_path_blocks_nested_git_directory(service_with_mock_repo):
    """_validate_crud_path should block .git/ directory even when nested."""
    service = service_with_mock_repo

    # Test various nested .git paths
    with pytest.raises(PermissionError) as exc_info:
        service._validate_crud_path("docs/.git/config", "test_operation")
    assert ".git" in str(exc_info.value).lower()

    with pytest.raises(PermissionError) as exc_info:
        service._validate_crud_path("src/project/.git/HEAD", "test_operation")
    assert ".git" in str(exc_info.value).lower()


def test_create_file_gitignore_allowed(service_with_mock_repo, test_repo_dir):
    """create_file should allow creating .gitignore files (not .git/ directory)."""
    service = service_with_mock_repo

    # Root .gitignore
    result = service.create_file(
        repo_alias="test-repo",
        file_path=".gitignore",
        content="*.pyc\n__pycache__/",
        username="testuser",
    )
    assert result["success"] is True
    gitignore_file = Path(test_repo_dir) / ".gitignore"
    assert gitignore_file.exists()

    # Nested .gitignore
    result = service.create_file(
        repo_alias="test-repo",
        file_path="src/.gitignore",
        content="*.log",
        username="testuser",
    )
    assert result["success"] is True
    nested_gitignore = Path(test_repo_dir) / "src" / ".gitignore"
    assert nested_gitignore.exists()


def test_create_file_github_directory_allowed(service_with_mock_repo, test_repo_dir):
    """create_file should allow creating files in .github/ directory."""
    service = service_with_mock_repo

    # GitHub Actions workflow
    result = service.create_file(
        repo_alias="test-repo",
        file_path=".github/workflows/ci.yml",
        content="name: CI\non: [push]",
        username="testuser",
    )
    assert result["success"] is True
    workflow_file = Path(test_repo_dir) / ".github" / "workflows" / "ci.yml"
    assert workflow_file.exists()

    # Dependabot config
    result = service.create_file(
        repo_alias="test-repo",
        file_path=".github/dependabot.yml",
        content="version: 2",
        username="testuser",
    )
    assert result["success"] is True
    dependabot_file = Path(test_repo_dir) / ".github" / "dependabot.yml"
    assert dependabot_file.exists()


def test_edit_file_gitattributes_allowed(service_with_mock_repo, test_repo_dir):
    """edit_file should allow editing .gitattributes files."""
    service = service_with_mock_repo

    # Create .gitattributes
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path=".gitattributes",
        content="*.py text eol=lf",
        username="testuser",
    )

    # Edit .gitattributes
    edit_result = service.edit_file(
        repo_alias="test-repo",
        file_path=".gitattributes",
        old_string="*.py text eol=lf",
        new_string="*.py text eol=lf\n*.sh text eol=lf",
        content_hash=create_result["content_hash"],
        replace_all=False,
        username="testuser",
    )
    assert edit_result["success"] is True
    gitattributes_file = Path(test_repo_dir) / ".gitattributes"
    assert "*.sh text eol=lf" in gitattributes_file.read_text()


def test_delete_file_nested_git_directory_blocked(service_with_mock_repo):
    """delete_file should block deletion in nested .git/ directories."""
    service = service_with_mock_repo

    with pytest.raises(PermissionError) as exc_info:
        service.delete_file(
            repo_alias="test-repo",
            file_path="docs/.git/config",
            content_hash=None,
            username="testuser",
        )
    assert ".git" in str(exc_info.value).lower()

    with pytest.raises(PermissionError) as exc_info:
        service.delete_file(
            repo_alias="test-repo",
            file_path="subproject/.git/HEAD",
            content_hash=None,
            username="testuser",
        )
    assert ".git" in str(exc_info.value).lower()


def test_create_edit_delete_github_workflow_e2e(service_with_mock_repo, test_repo_dir):
    """End-to-end test: create, edit, delete .github/workflows file."""
    service = service_with_mock_repo

    # Create workflow
    create_result = service.create_file(
        repo_alias="test-repo",
        file_path=".github/workflows/test.yml",
        content="name: Test\non: [push]",
        username="testuser",
    )
    assert create_result["success"] is True

    # Edit workflow
    edit_result = service.edit_file(
        repo_alias="test-repo",
        file_path=".github/workflows/test.yml",
        old_string="on: [push]",
        new_string="on: [push, pull_request]",
        content_hash=create_result["content_hash"],
        replace_all=False,
        username="testuser",
    )
    assert edit_result["success"] is True

    # Delete workflow
    delete_result = service.delete_file(
        repo_alias="test-repo",
        file_path=".github/workflows/test.yml",
        content_hash=edit_result["content_hash"],
        username="testuser",
    )
    assert delete_result["success"] is True

    workflow_file = Path(test_repo_dir) / ".github" / "workflows" / "test.yml"
    assert not workflow_file.exists()
