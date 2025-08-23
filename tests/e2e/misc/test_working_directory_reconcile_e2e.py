"""
End-to-end tests for working directory awareness in reconcile functionality.

These tests validate the complete workflow of detecting, indexing, and querying
working directory changes through the reconcile system.
"""

import os
import subprocess
import time
from pathlib import Path
import pytest

from ...conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


def run_cidx_command(test_dir: Path, command: list, timeout: int = 60):
    """Run a code-indexer command with proper error handling."""
    result = subprocess.run(
        command,
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


def setup_git_repository(project_path: Path):
    """Setup git repository with proper configuration."""
    subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=project_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=project_path, check=True
    )

    # Create .gitignore to exclude .code-indexer directory (prevents git stat errors on cleanup)
    gitignore_content = """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
    (project_path / ".gitignore").write_text(gitignore_content)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_working_directory_reconcile_workflow_e2e():
    """
    End-to-end test: Working directory changes workflow using shared containers
    1. Index initial committed files
    2. Modify files without committing
    3. Run reconcile
    4. Query should find only new content, not old content
    """
    with shared_container_test_environment(
        "test_working_directory_reconcile_workflow_e2e", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create initial files and commit them
        print("=== PHASE 1: Create and commit initial files ===")

        file1 = project_path / "file1.py"
        file1.write_text(
            """def original_function():
    '''This is the original function'''
    return "original content from commit"

class OriginalClass:
    def original_method(self):
        return "original method"
"""
        )

        file2 = project_path / "file2.py"
        file2.write_text(
            """def helper_function():
    '''Original helper function'''
    return "original helper content"
"""
        )

        # Initialize git repository and commit files
        setup_git_repository(project_path)
        subprocess.run(["git", "add", "."], cwd=project_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=project_path, check=True
        )

        # Initialize and index with VoyageAI
        init_result = run_cidx_command(
            project_path,
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services (should already be running in shared environment)
        start_result = run_cidx_command(
            project_path, ["code-indexer", "start", "--quiet"], timeout=120
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        initial_index_result = run_cidx_command(
            project_path, ["code-indexer", "index", "--clear"], timeout=180
        )
        assert (
            initial_index_result.returncode == 0
        ), f"Initial index failed: {initial_index_result.stderr}"
        assert "✅ Indexing complete!" in initial_index_result.stdout

        # Verify initial committed content is searchable
        committed_query = run_cidx_command(
            project_path,
            ["code-indexer", "query", "original content from commit", "--quiet"],
        )
        assert committed_query.returncode == 0
        assert (
            "file1.py" in committed_query.stdout
        ), "Should find committed content in file1.py"

        print("✅ Initial committed content indexed and searchable")

        # === PHASE 2: Modify files without committing ===
        print("=== PHASE 2: Modify files in working directory ===")

        time.sleep(1)  # Ensure different mtime

        # Modify file1.py without committing
        file1.write_text(
            """def modified_function():
    '''This is the MODIFIED function with working directory changes'''
    return "MODIFIED content from working directory"

class ModifiedClass:
    def modified_method(self):
        return "modified method from working dir"
    
    def new_working_dir_method(self):
        return "this method only exists in working directory"
"""
        )

        # Modify file2.py without committing
        file2.write_text(
            """def modified_helper_function():
    '''Modified helper function in working directory'''
    return "MODIFIED helper content from working dir"

def new_working_dir_function():
    return "this function only exists in working directory"
"""
        )

        print("✅ Files modified in working directory (not committed)")

        # Verify git shows uncommitted changes
        git_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
        )
        assert "M file1.py" in git_status.stdout
        assert "M file2.py" in git_status.stdout
        print("✅ Git confirms files have uncommitted changes")

        # === PHASE 3: Run reconcile to detect working directory changes ===
        print("=== PHASE 3: Reconcile working directory changes ===")

        reconcile_result = run_cidx_command(
            project_path, ["code-indexer", "index", "--reconcile"], timeout=180
        )
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"
        assert "✅ Indexing complete!" in reconcile_result.stdout

        print(f"📋 RECONCILE OUTPUT:\n{reconcile_result.stdout}")

        # Reconcile should have detected the working directory changes
        assert any(
            keyword in reconcile_result.stdout.lower()
            for keyword in ["files processed", "missing", "modified", "working"]
        ), f"Reconcile should have detected working directory changes: {reconcile_result.stdout}"

        print("✅ Reconcile completed and detected working directory changes")

        # === PHASE 4: Verify working directory content is searchable ===
        print("=== PHASE 4: Verify working directory content queries ===")

        # Query for working directory content - should be found
        working_dir_query = run_cidx_command(
            project_path,
            [
                "code-indexer",
                "query",
                "MODIFIED content from working directory",
                "--quiet",
            ],
        )
        assert (
            working_dir_query.returncode == 0
        ), f"Working dir query failed: {working_dir_query.stderr}"
        assert (
            "file1.py" in working_dir_query.stdout
        ), "Should find working directory content in file1.py"

        # Query for working directory only functions
        new_method_query = run_cidx_command(
            project_path, ["code-indexer", "query", "new_working_dir_method", "--quiet"]
        )
        assert new_method_query.returncode == 0
        assert (
            "file1.py" in new_method_query.stdout
        ), "Should find working dir only methods"

        new_function_query = run_cidx_command(
            project_path,
            ["code-indexer", "query", "new_working_dir_function", "--quiet"],
        )
        assert new_function_query.returncode == 0
        assert (
            "file2.py" in new_function_query.stdout
        ), "Should find working dir only functions"

        print("✅ Working directory content is searchable")

        # === PHASE 5: CRITICAL TEST - Old committed content should not be found ===
        print("=== PHASE 5: CRITICAL TEST - Old content elimination ===")

        old_committed_query = run_cidx_command(
            project_path,
            ["code-indexer", "query", "original content from commit", "--quiet"],
        )
        assert (
            old_committed_query.returncode == 0
        ), f"Old content query failed: {old_committed_query.stderr}"

        print(f"🔍 OLD COMMITTED CONTENT QUERY RESULT:\n{old_committed_query.stdout}")

        # CRITICAL: Old committed content text should NOT be found
        # Check that the actual old content is not in the results
        if "original content from commit" in old_committed_query.stdout:
            pytest.fail(
                "CRITICAL FAILURE: Old committed content text should not be found after working directory modification"
            )

        if "original function" in old_committed_query.stdout.lower():
            pytest.fail(
                "CRITICAL FAILURE: Old committed function should not be found after working directory modification"
            )

        if "original helper content" in old_committed_query.stdout:
            pytest.fail(
                "CRITICAL FAILURE: Old committed helper content should not be found after working directory modification"
            )

        print(
            "✅ CRITICAL SUCCESS: Old committed content properly hidden after working directory changes"
        )

        print("🎉 Working directory reconcile workflow test PASSED!")


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests",
)
def test_git_restore_reconcile_workflow_e2e():
    """
    End-to-end test: Git restore workflow using shared containers
    1. Index committed files
    2. Modify files (creates working_dir content)
    3. Git restore files to committed state
    4. Run reconcile
    5. Query should find committed content, not working_dir content
    """
    with shared_container_test_environment(
        "test_git_restore_reconcile_workflow_e2e", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Setup: Create, commit, and index initial files
        print("=== PHASE 1: Setup committed and indexed files ===")

        file1 = project_path / "restore_test.py"
        committed_content = """def committed_function():
    '''This content is committed to git'''
    return "committed content that should be restored"
"""
        file1.write_text(committed_content)

        # Initialize git repository and commit
        setup_git_repository(project_path)
        subprocess.run(["git", "add", "."], cwd=project_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=project_path, check=True
        )

        # Index committed content
        init_result = run_cidx_command(
            project_path,
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
        )
        assert init_result.returncode == 0

        # Start services (should already be running in shared environment)
        start_result = run_cidx_command(
            project_path, ["code-indexer", "start", "--quiet"], timeout=120
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        index_result = run_cidx_command(
            project_path, ["code-indexer", "index", "--clear"], timeout=180
        )
        assert index_result.returncode == 0
        assert "✅ Indexing complete!" in index_result.stdout

        print("✅ Initial committed content indexed")

        # === PHASE 2: Modify file and reconcile (creates working_dir content) ===
        print("=== PHASE 2: Create working directory changes ===")

        time.sleep(1)  # Ensure different mtime
        working_dir_content = """def working_dir_function():
    '''This content only exists in working directory'''
    return "working directory content that will be restored away"

def temporary_function():
    return "this will disappear after git restore"
"""
        file1.write_text(working_dir_content)

        # Reconcile to index working directory changes
        working_reconcile = run_cidx_command(
            project_path, ["code-indexer", "index", "--reconcile"], timeout=180
        )
        assert working_reconcile.returncode == 0

        # Verify working directory content is searchable
        working_query = run_cidx_command(
            project_path,
            ["code-indexer", "query", "working directory content", "--quiet"],
        )
        assert working_query.returncode == 0
        assert "restore_test.py" in working_query.stdout

        print("✅ Working directory changes indexed and searchable")

        # === PHASE 3: Git restore to committed state ===
        print("=== PHASE 3: Git restore to committed state ===")

        subprocess.run(
            ["git", "checkout", "--", "restore_test.py"], cwd=project_path, check=True
        )

        # Verify file content is restored
        restored_content = file1.read_text()
        assert "committed content that should be restored" in restored_content
        assert "working directory content" not in restored_content

        print("✅ File restored to committed state")

        # === PHASE 4: Reconcile after restore ===
        print("=== PHASE 4: Reconcile after git restore ===")

        restore_reconcile = run_cidx_command(
            project_path, ["code-indexer", "index", "--reconcile"], timeout=180
        )
        assert restore_reconcile.returncode == 0
        assert "✅ Indexing complete!" in restore_reconcile.stdout

        print("✅ Reconcile completed after git restore")

        # === PHASE 5: Verify committed content is searchable again ===
        print("=== PHASE 5: Verify committed content restored ===")

        committed_query = run_cidx_command(
            project_path,
            [
                "code-indexer",
                "query",
                "committed content that should be restored",
                "--quiet",
            ],
        )
        assert committed_query.returncode == 0
        assert (
            "restore_test.py" in committed_query.stdout
        ), "Should find restored committed content"

        # === PHASE 6: Verify working directory content is no longer searchable ===
        print("=== PHASE 6: Verify working directory content eliminated ===")

        old_working_query = run_cidx_command(
            project_path,
            ["code-indexer", "query", "working directory content", "--quiet"],
        )
        assert old_working_query.returncode == 0

        print(f"🔍 OLD WORKING DIR QUERY RESULT:\n{old_working_query.stdout}")

        # CRITICAL: Old working directory content text should not be found
        # Check that the actual old working directory content is not in the results
        if (
            "working directory content that will be restored away"
            in old_working_query.stdout
        ):
            pytest.fail(
                "CRITICAL FAILURE: Old working directory content text should not be found after git restore"
            )

        if "temporary_function" in old_working_query.stdout:
            pytest.fail(
                "CRITICAL FAILURE: Temporary function should not be found after git restore"
            )

        print(
            "✅ CRITICAL SUCCESS: Working directory content properly eliminated after git restore"
        )

        print("🎉 Git restore reconcile workflow test PASSED!")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
