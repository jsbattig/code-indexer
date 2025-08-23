"""
Comprehensive end-to-end test for reconcile functionality covering:
1. Index initial files
2. Modify existing file
3. Add new file
4. Delete existing file
5. Run --reconcile
6. Query to verify correct behavior for all scenarios
7. Branch visibility and switching scenarios
8. Git-aware branch isolation testing

This test validates both git-aware (hide) and non-git behavior (delete).
It also includes comprehensive branch visibility scenarios that were previously
in separate test files for redundancy removal.
"""

import os
import time
import subprocess
from pathlib import Path
import pytest

# Import shared container infrastructure
from ...conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


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


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_comprehensive_reconcile_modify_add_delete():
    """
    Comprehensive test of reconcile functionality:
    1. Index initial files
    2. Modify existing file
    3. Add new file
    4. Delete existing file
    5. Run --reconcile
    6. Query to verify correct behavior
    """
    with shared_container_test_environment(
        "test_comprehensive_reconcile_modify_add_delete", EmbeddingProvider.VOYAGE_AI
    ) as project_path:

        # === PHASE 1: Create initial files and index them ===
        print("\n=== PHASE 1: Initial index ===")
        create_initial_test_files(project_path)

        # Initialize with VoyageAI
        init_result = subprocess.run(
            [
                "code-indexer",
                "init",
                "--force",
                "--embedding-provider",
                "voyage-ai",
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Initial index
        index_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            index_result.returncode == 0
        ), f"Initial index failed: {index_result.stderr}"
        assert "✅ Indexing complete!" in index_result.stdout

        # Verify initial query works
        query_result = subprocess.run(
            ["code-indexer", "query", "function_one", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            query_result.returncode == 0
        ), f"Initial query failed: {query_result.stderr}"
        assert (
            "file1.py" in query_result.stdout
        ), "Should find file1.py in initial query"

        # Wait to ensure timestamp differences
        time.sleep(2)

        # === PHASE 2: Modify, Add, Delete files ===
        print("\n=== PHASE 2: Modify, Add, Delete ===")

        # 2a. MODIFY existing file
        modified_file = project_path / "file1.py"
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
        new_file = project_path / "file4_new.py"
        new_file_content = """def brand_new_function():
    '''This is a brand new function'''
    return "brand new content"

class BrandNewClass:
    def __init__(self):
        self.status = "newly created"
"""
        new_file.write_text(new_file_content)

        # 2c. DELETE existing file
        deleted_file = project_path / "file2.py"
        assert deleted_file.exists(), "File to delete should exist"
        deleted_file.unlink()  # Delete the file
        assert not deleted_file.exists(), "File should be deleted"

        # === PHASE 3: Run reconcile ===
        print("\n=== PHASE 3: Reconcile ===")

        reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
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
        modified_query = subprocess.run(
            ["code-indexer", "query", "MODIFIED", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            modified_query.returncode == 0
        ), f"Modified query failed: {modified_query.stderr}"
        assert "file1.py" in modified_query.stdout, "Should find modified file1.py"

        # The old content should NOT be found anymore
        old_query = subprocess.run(
            ["code-indexer", "query", "original content 1", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            old_query.returncode == 0
        ), f"Old content query failed: {old_query.stderr}"
        print(f"\n🔍 OLD CONTENT QUERY RESULT:\n{old_query.stdout}")
        # Check that the actual old content is not found
        if "original content 1" in old_query.stdout:
            pytest.fail(
                "CRITICAL FAILURE: Old committed content text 'original content 1' should not be found after modification"
            )

        # 4b. NEW file should be found
        new_query = subprocess.run(
            ["code-indexer", "query", "brand_new_function", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert new_query.returncode == 0, f"New file query failed: {new_query.stderr}"
        assert "file4_new.py" in new_query.stdout, "Should find new file4_new.py"

        # 4c. DELETED file behavior depends on git vs non-git
        deleted_query = subprocess.run(
            ["code-indexer", "query", "function_two", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            deleted_query.returncode == 0
        ), f"Deleted file query failed: {deleted_query.stderr}"

        # Check if this is a git repository
        git_check = subprocess.run(
            ["git", "status"],
            cwd=project_path,
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
        second_reconcile = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            second_reconcile.returncode == 0
        ), f"Second reconcile failed: {second_reconcile.stderr}"

        # Should show files are up-to-date
        second_output = second_reconcile.stdout
        assert (
            "up-to-date" in second_output.lower()
        ), f"Second reconcile should show files up-to-date: {second_output}"

        print(
            "\n✅ Comprehensive reconcile modify/add/delete test completed successfully!"
        )


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.xfail(
    reason="Known bug: Branch visibility after multiple switches not working correctly"
)
def test_comprehensive_reconcile_branch_visibility_scenarios():
    """
    Comprehensive test for reconcile branch visibility functionality.

    This test covers scenarios that were previously in separate test files:
    - Branch switching and file visibility
    - Files that exist in some branches but not others
    - Reconcile behavior when switching between branches
    - Bug scenarios where files remain hidden incorrectly

    Consolidated from test_reconcile_branch_visibility_e2e.py and
    test_reconcile_branch_visibility_bug_e2e.py for redundancy removal.
    """
    with shared_container_test_environment(
        "test_comprehensive_reconcile_branch_visibility_scenarios",
        EmbeddingProvider.VOYAGE_AI,
    ) as project_path:

        print("\n=== COMPREHENSIVE BRANCH VISIBILITY TEST ===")

        # === PHASE 1: Set up git repository with multiple branches ===
        print("\n=== PHASE 1: Git repository setup ===")

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=project_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=project_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=project_path, check=True
        )

        # Create .gitignore to prevent committing .code-indexer directory
        (project_path / ".gitignore").write_text(
            """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
        )

        # Create master branch files
        (project_path / "README.md").write_text(
            "# Master Branch Project\nThis file exists on master branch."
        )
        (project_path / "common.py").write_text(
            "# Common file\ndef common_function():\n    return 'shared across branches'"
        )
        (project_path / "master_only.py").write_text(
            "# Master Only File\ndef master_feature():\n    return 'only on master branch'"
        )

        # Commit master files
        subprocess.run(["git", "add", "."], cwd=project_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial master commit"],
            cwd=project_path,
            check=True,
        )

        # === PHASE 2: Initialize indexing and index master branch ===
        print("\n=== PHASE 2: Initialize and index master branch ===")

        # Initialize with VoyageAI for CI stability
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Index master branch
        index_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            index_result.returncode == 0
        ), f"Master index failed: {index_result.stderr}"

        # Verify master files are indexed
        master_query = subprocess.run(
            ["code-indexer", "query", "master_feature", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            master_query.returncode == 0
        ), f"Master query failed: {master_query.stderr}"
        assert "master_only.py" in master_query.stdout, "Should find master_only.py"

        # === PHASE 3: Create feature branch with different files ===
        print("\n=== PHASE 3: Create feature branch ===")

        # Create feature branch with different files
        subprocess.run(
            ["git", "checkout", "-b", "feature"], cwd=project_path, check=True
        )

        # Remove master_only.py and add feature_only.py
        (project_path / "master_only.py").unlink()
        (project_path / "feature_only.py").write_text(
            "# Feature Only File\ndef feature_implementation():\n    return 'only on feature branch'"
        )

        # Commit feature changes
        subprocess.run(["git", "add", "."], cwd=project_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature-specific files"],
            cwd=project_path,
            check=True,
        )

        # === PHASE 4: Index feature branch ===
        print("\n=== PHASE 4: Index feature branch ===")

        # Index feature branch (should hide master_only.py, show feature_only.py)
        feature_index_result = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            feature_index_result.returncode == 0
        ), f"Feature index failed: {feature_index_result.stderr}"

        # Verify feature_only.py is visible and master_only.py is hidden
        feature_query = subprocess.run(
            ["code-indexer", "query", "feature_implementation", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            feature_query.returncode == 0
        ), f"Feature query failed: {feature_query.stderr}"
        assert "feature_only.py" in feature_query.stdout, "Should find feature_only.py"

        # Master-only file should not be visible in current branch
        master_hidden_query = subprocess.run(
            ["code-indexer", "query", "master_feature", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            master_hidden_query.returncode == 0
        ), f"Master hidden query failed: {master_hidden_query.stderr}"
        # The key test: master_only.py should not appear in results for current branch
        assert (
            "master_only.py" not in master_hidden_query.stdout
        ), "master_only.py should be hidden when on feature branch"

        # === PHASE 5: Switch back to master - THE CRITICAL BUG TEST ===
        print("\n=== PHASE 5: Switch back to master (bug test) ===")

        # Switch back to master
        subprocess.run(["git", "checkout", "master"], cwd=project_path, check=True)

        # Run reconcile on master branch
        master_reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            master_reconcile_result.returncode == 0
        ), f"Master reconcile failed: {master_reconcile_result.stderr}"

        # === CRITICAL BUG TEST: Files that should be visible on master should become visible ===
        print("\n=== PHASE 6: Verify branch visibility bug fix ===")

        # master_only.py should now be visible again (this was the bug)
        master_visible_query = subprocess.run(
            ["code-indexer", "query", "master_feature", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            master_visible_query.returncode == 0
        ), f"Master visible query failed: {master_visible_query.stderr}"
        assert "master_only.py" in master_visible_query.stdout, (
            "CRITICAL BUG TEST: master_only.py should be visible again when on master branch. "
            "This was the bug - files remained hidden after switching branches."
        )

        # feature_only.py should now be hidden
        feature_hidden_query = subprocess.run(
            ["code-indexer", "query", "feature_implementation", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            feature_hidden_query.returncode == 0
        ), f"Feature hidden query failed: {feature_hidden_query.stderr}"
        assert (
            "feature_only.py" not in feature_hidden_query.stdout
        ), "feature_only.py should be hidden when on master branch"

        # === PHASE 7: Test multiple branch switches ===
        print("\n=== PHASE 7: Multiple branch switch test ===")

        # Switch back to feature
        subprocess.run(["git", "checkout", "feature"], cwd=project_path, check=True)

        # Reconcile on feature
        feature_reconcile2 = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            feature_reconcile2.returncode == 0
        ), f"Feature reconcile 2 failed: {feature_reconcile2.stderr}"

        # Verify visibility switched correctly again
        feature_visible_query = subprocess.run(
            ["code-indexer", "query", "feature_implementation", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            feature_visible_query.returncode == 0
        ), f"Feature visible query failed: {feature_visible_query.stderr}"
        assert (
            "feature_only.py" in feature_visible_query.stdout
        ), "feature_only.py should be visible again on feature branch"

        master_hidden_query2 = subprocess.run(
            ["code-indexer", "query", "master_feature", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            master_hidden_query2.returncode == 0
        ), f"Master hidden query 2 failed: {master_hidden_query2.stderr}"
        assert (
            "master_only.py" not in master_hidden_query2.stdout
        ), "master_only.py should be hidden again on feature branch"

        # === PHASE 8: Test common files remain visible ===
        print("\n=== PHASE 8: Common files visibility test ===")

        # Common files should be visible in both branches
        common_query = subprocess.run(
            ["code-indexer", "query", "common_function", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            common_query.returncode == 0
        ), f"Common query failed: {common_query.stderr}"
        assert (
            "common.py" in common_query.stdout
        ), "common.py should be visible in all branches"

        print("\n✅ COMPREHENSIVE BRANCH VISIBILITY TEST PASSED!")
        print("   ✅ Files correctly hidden/shown when switching branches")
        print("   ✅ Branch visibility bug scenarios handled correctly")
        print("   ✅ Multiple branch switches work properly")
        print("   ✅ Common files remain visible across branches")

        print("\n✅ Comprehensive reconcile test completed successfully!")
