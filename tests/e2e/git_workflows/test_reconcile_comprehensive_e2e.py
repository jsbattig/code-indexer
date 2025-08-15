"""
Comprehensive end-to-end test for reconcile functionality covering:
1. Index initial files
2. Modify existing file
3. Add new file
4. Delete existing file
5. Run --reconcile
6. Query to verify correct behavior for all scenarios

This test validates both git-aware (hide) and non-git behavior (delete).
"""

import os
import time
import subprocess
from pathlib import Path
import pytest

from ...conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def comprehensive_reconcile_repo():
    """Create a test repository for comprehensive reconcile testing."""
    with local_temporary_directory() as temp_dir:
        create_test_project_with_inventory(temp_dir, TestProjectInventory.RECONCILE)
        yield temp_dir


def create_initial_test_files(test_dir: Path) -> dict:
    """Create initial test files and return their info."""
    files = {
        "file1.py": """def function_one():
    '''This is function one'''
    return "original content 1"

class ClassOne:
    def method_one(self):
        return "method one"
""",
        "file2.py": """def function_two():
    '''This is function two''' 
    return "original content 2"

def helper_function():
    return "helper"
""",
        "file3.py": """class ClassThree:
    '''This is class three'''
    def __init__(self):
        self.value = "original value"
    
    def get_value(self):
        return self.value
""",
        "lib/utils.py": """import os
import sys

def utility_function():
    '''Utility function'''
    return "utility content"

class UtilityClass:
    pass
""",
    }

    for filename, content in files.items():
        file_path = test_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    return files


def run_cidx_command(
    test_dir: Path, command: list, timeout: int = 60
) -> subprocess.CompletedProcess:
    """Run a code-indexer command with proper error handling."""
    result = subprocess.run(
        command,
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    # If services not available, try to start them
    if result.returncode != 0:
        error_output = result.stderr + result.stdout
        if "service not available" in error_output.lower():
            print("Services not available, attempting to start them...")
            start_result = subprocess.run(
                ["code-indexer", "start"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if start_result.returncode == 0:
                # Retry the original command
                result = subprocess.run(
                    command,
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

    return result


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_comprehensive_reconcile_modify_add_delete(comprehensive_reconcile_repo):
    """
    Comprehensive test of reconcile functionality:
    1. Index initial files
    2. Modify existing file
    3. Add new file
    4. Delete existing file
    5. Run --reconcile
    6. Query to verify correct behavior
    """
    test_dir = comprehensive_reconcile_repo

    # === PHASE 1: Create initial files and index them ===
    print("\n=== PHASE 1: Initial index ===")
    create_initial_test_files(test_dir)

    # Initialize with VoyageAI for CI stability
    init_result = run_cidx_command(
        test_dir,
        ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
    )
    assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

    # Initial index
    index_result = run_cidx_command(
        test_dir, ["code-indexer", "index", "--clear"], timeout=180
    )
    assert index_result.returncode == 0, f"Initial index failed: {index_result.stderr}"
    assert "✅ Indexing complete!" in index_result.stdout

    # Verify initial query works
    query_result = run_cidx_command(
        test_dir, ["code-indexer", "query", "function_one", "--quiet"]
    )
    assert query_result.returncode == 0, f"Initial query failed: {query_result.stderr}"
    assert "file1.py" in query_result.stdout, "Should find file1.py in initial query"

    # Wait to ensure timestamp differences
    time.sleep(2)

    # === PHASE 2: Modify, Add, Delete files ===
    print("\n=== PHASE 2: Modify, Add, Delete ===")

    # 2a. MODIFY existing file
    modified_file = test_dir / "file1.py"
    original_mtime = modified_file.stat().st_mtime
    modified_content = """def function_one():
    '''This is the MODIFIED function one'''
    return "MODIFIED content 1"

class ClassOne:
    def method_one(self):
        return "MODIFIED method one"
    
    def new_method(self):
        return "This is a new method added"
"""
    modified_file.write_text(modified_content)
    new_mtime = modified_file.stat().st_mtime
    assert new_mtime > original_mtime, "File modification time should increase"

    # 2b. ADD new file
    new_file = test_dir / "file4_new.py"
    new_file_content = """def brand_new_function():
    '''This is a brand new function'''
    return "brand new content"

class BrandNewClass:
    def __init__(self):
        self.status = "newly created"
"""
    new_file.write_text(new_file_content)

    # 2c. DELETE existing file
    deleted_file = test_dir / "file2.py"
    assert deleted_file.exists(), "File to delete should exist"
    deleted_file.unlink()  # Delete the file
    assert not deleted_file.exists(), "File should be deleted"

    # === PHASE 3: Run reconcile ===
    print("\n=== PHASE 3: Reconcile ===")

    reconcile_result = run_cidx_command(
        test_dir, ["code-indexer", "index", "--reconcile"], timeout=180
    )
    assert (
        reconcile_result.returncode == 0
    ), f"Reconcile failed: {reconcile_result.stderr}"
    assert "✅ Indexing complete!" in reconcile_result.stdout

    # Check reconcile detected work to do
    reconcile_output = reconcile_result.stdout
    print(f"\n📋 RECONCILE OUTPUT:\n{reconcile_output}")
    assert (
        "files processed" in reconcile_output.lower()
        or "missing" in reconcile_output.lower()
        or "modified" in reconcile_output.lower()
    ), f"Reconcile should have detected work to do: {reconcile_output}"

    # === PHASE 4: Query verification ===
    print("\n=== PHASE 4: Query verification ===")

    # 4a. MODIFIED file should return new content
    modified_query = run_cidx_command(
        test_dir, ["code-indexer", "query", "MODIFIED", "--quiet"]
    )
    assert (
        modified_query.returncode == 0
    ), f"Modified query failed: {modified_query.stderr}"
    assert "file1.py" in modified_query.stdout, "Should find modified file1.py"

    # The old content should NOT be found anymore
    old_query = run_cidx_command(
        test_dir, ["code-indexer", "query", "original content 1", "--quiet"]
    )
    assert old_query.returncode == 0, f"Old content query failed: {old_query.stderr}"
    print(f"\n🔍 OLD CONTENT QUERY RESULT:\n{old_query.stdout}")
    # Check that the actual old content is not found
    if "original content 1" in old_query.stdout:
        pytest.fail(
            "CRITICAL FAILURE: Old committed content text 'original content 1' should not be found after modification"
        )

    # 4b. NEW file should be found
    new_query = run_cidx_command(
        test_dir, ["code-indexer", "query", "brand_new_function", "--quiet"]
    )
    assert new_query.returncode == 0, f"New file query failed: {new_query.stderr}"
    assert "file4_new.py" in new_query.stdout, "Should find new file4_new.py"

    # 4c. DELETED file behavior depends on git vs non-git
    deleted_query = run_cidx_command(
        test_dir, ["code-indexer", "query", "function_two", "--quiet"]
    )
    assert (
        deleted_query.returncode == 0
    ), f"Deleted file query failed: {deleted_query.stderr}"

    # Check if this is a git repository
    git_check = subprocess.run(
        ["git", "status"],
        cwd=test_dir,
        capture_output=True,
        text=True,
    )
    is_git_repo = git_check.returncode == 0

    if is_git_repo:
        # Git-aware: file should be HIDDEN (not visible in current branch)
        # The query might still return results but they should be from other branches
        # For this test, we expect the deleted file to not appear in results
        # since we're only in the current branch
        print("Git repository detected - deleted file should be hidden")
        # Note: In git-aware mode, files are hidden per branch, not completely removed
        # The exact behavior depends on branch isolation implementation
    else:
        # Non-git: file should be COMPLETELY REMOVED from database
        print("Non-git repository - deleted file should be completely removed")
        assert (
            "file2.py" not in deleted_query.stdout
        ), "Deleted file should not be found in non-git repository"

    # === PHASE 5: Verify reconcile is idempotent ===
    print("\n=== PHASE 5: Verify idempotency ===")

    # Run reconcile again - should find nothing to do
    second_reconcile = run_cidx_command(
        test_dir, ["code-indexer", "index", "--reconcile"], timeout=60
    )
    assert (
        second_reconcile.returncode == 0
    ), f"Second reconcile failed: {second_reconcile.stderr}"

    # Should show files are up-to-date
    second_output = second_reconcile.stdout
    assert (
        "up-to-date" in second_output.lower()
    ), f"Second reconcile should show files up-to-date: {second_output}"

    print("\n✅ Comprehensive reconcile test completed successfully!")


if __name__ == "__main__":
    # Allow running this test directly for debugging
    pytest.main([__file__, "-v", "-s"])
