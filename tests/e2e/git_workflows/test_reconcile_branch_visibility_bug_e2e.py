"""
E2E test to reproduce and verify fix for reconcile branch visibility bug.

This test demonstrates the bug where reconcile properly hides files that don't exist
in the current branch (soft delete), but FAILS to unhide files that should be visible
in the current branch after switching branches.

Bug scenario:
1. Create git repo with master and feature branches having different files
2. Index both branches
3. Switch to master and run reconcile
4. Files that were hidden on feature but exist on master should become visible
5. Currently they remain hidden, causing incomplete search results
"""

import os
import subprocess

import pytest

from ...conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


@pytest.fixture
def reconcile_branch_test_repo():
    """Create a test repository for reconcile branch visibility testing."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.RECONCILE_BRANCH_VISIBILITY
        )

        # Create test git repository
        subprocess.run(["git", "init"], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=temp_dir,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True
        )

        # Create .gitignore FIRST to prevent committing .code-indexer directory
        (temp_dir / ".gitignore").write_text(
            """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
        )

        # Create master branch files
        (temp_dir / "README.md").write_text(
            "# Master Branch Project\nThis file exists on master branch."
        )
        (temp_dir / "common.py").write_text(
            "# Common file\ndef common_function():\n    return 'shared across branches'"
        )
        (temp_dir / "master_only.py").write_text(
            "# Master Only File\ndef master_feature():\n    return 'only on master branch'"
        )

        # Commit master files
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial master commit"], cwd=temp_dir, check=True
        )

        # Create feature branch with different files
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=temp_dir, check=True)

        # Remove master_only.py and add feature_only.py
        (temp_dir / "master_only.py").unlink()
        (temp_dir / "feature_only.py").write_text(
            "# Feature Only File\ndef feature_implementation():\n    return 'only on feature branch'"
        )

        # Commit feature changes
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature-specific files"],
            cwd=temp_dir,
            check=True,
        )

        # Go back to master for testing
        subprocess.run(["git", "checkout", "master"], cwd=temp_dir, check=True)

        yield temp_dir


def run_cli_command(command, cwd, expect_success=True):
    """Run a CLI command and return the result."""
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
    )

    if expect_success and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    return result


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_reconcile_branch_visibility_bug(reconcile_branch_test_repo):
    """
    Test that reproduces the reconcile branch visibility bug.

    This test will FAIL until the bug is fixed. The bug is that reconcile
    properly hides files that don't exist in the current branch, but fails
    to unhide files that should be visible in the current branch.
    """
    test_dir = reconcile_branch_test_repo

    try:
        original_cwd = os.getcwd()
        os.chdir(test_dir)

        # Initialize and start services - use the project isolation infrastructure
        print("🚀 Initializing services...")
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Force a clean start to avoid issues with corrupted shared services
        print("🧹 Cleaning up any existing broken services...")
        subprocess.run(
            ["code-indexer", "uninstall"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Start fresh services
        services_ready = False
        print("🚀 Starting services...")
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,  # Reduced timeout
        )

        if start_result.returncode != 0:
            stdout_text = start_result.stdout or ""
            stderr_text = start_result.stderr or ""

            # Check for common recoverable issues
            if any(
                phrase in (stdout_text + stderr_text)
                for phrase in [
                    "already in use",
                    "already running",
                    "already exists",
                    "Found existing containers",
                ]
            ):
                print("⚠️ Services may already be running, checking status...")
                # Re-check status after start attempt
                final_status = subprocess.run(
                    ["code-indexer", "status"],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if final_status.returncode == 0 and "✅" in final_status.stdout:
                    print("✅ Services are running after start attempt")
                    services_ready = True

            if not services_ready:
                # Skip test if services can't be started
                pytest.skip(f"Could not start services: {start_result.stdout[:200]}")
        else:
            services_ready = True

        # Final verification - actually test that indexing works
        print("🔍 Verifying services are truly ready for indexing...")

        # Create a minimal test file to verify indexing works
        test_verification_file = test_dir / "service_test.py"
        test_verification_file.write_text("# Test file for service verification")

        # Try a simple index operation to verify services work
        test_index = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if test_index.returncode != 0:
            error_msg = (
                f"Services report as healthy but indexing fails: {test_index.stdout}"
            )
            pytest.skip(error_msg)

        print("✅ Services verified working - indexing test successful")

        # Step 1: Index master branch (has master_only.py, common.py, README.md)
        print("📁 Step 1: Indexing master branch...")
        master_index = run_cli_command(["code-indexer", "index"], test_dir)
        assert "✅ Indexing complete!" in master_index.stdout
        print("✅ Master branch indexed")

        # Verify master content is searchable
        master_search = run_cli_command(
            ["code-indexer", "query", "master_feature"], test_dir
        )
        assert (
            "master_only.py" in master_search.stdout
        ), "Should find master-specific content"
        print("✅ Master content is searchable")

        # Step 2: Switch to feature branch and index
        print("🔄 Step 2: Switching to feature branch and indexing...")
        subprocess.run(["git", "checkout", "feature"], cwd=test_dir, check=True)

        feature_index = run_cli_command(["code-indexer", "index"], test_dir)
        assert "✅ Indexing complete!" in feature_index.stdout
        print("✅ Feature branch indexed")

        # Verify feature content is searchable and master content is hidden
        feature_search = run_cli_command(
            ["code-indexer", "query", "feature_implementation"], test_dir
        )
        assert (
            "feature_only.py" in feature_search.stdout
        ), "Should find feature-specific content"

        # Master content should be hidden on feature branch
        master_search_on_feature = run_cli_command(
            ["code-indexer", "query", "master_feature"], test_dir, expect_success=False
        )
        # The search should either fail or not contain master_only.py
        should_not_find_master = (
            master_search_on_feature.returncode != 0
            or "master_only.py" not in master_search_on_feature.stdout
        )
        assert (
            should_not_find_master
        ), "Master content should be hidden on feature branch"
        print("✅ Master content properly hidden on feature branch")

        # Step 3: Switch back to master and run reconcile (this is where the bug occurs)
        print("🔄 Step 3: Switching back to master and running reconcile...")
        subprocess.run(["git", "checkout", "master"], cwd=test_dir, check=True)

        reconcile_result = run_cli_command(
            ["code-indexer", "index", "--reconcile"], test_dir
        )
        assert "✅" in reconcile_result.stdout or reconcile_result.returncode == 0
        print("✅ Reconcile completed")

        # Step 4: THE BUG TEST - Master content should be visible again after reconcile
        print(
            "🐛 Step 4: Testing for the bug - checking if master content is visible..."
        )

        # This should work - master_only.py exists on master and should be visible
        master_search_after_reconcile = run_cli_command(
            ["code-indexer", "query", "master_feature"], test_dir
        )

        # BUG DETECTION: If master_only.py is not found, the bug exists
        if "master_only.py" not in master_search_after_reconcile.stdout:
            print(
                "🐛 BUG DETECTED: master_only.py is NOT visible on master branch after reconcile!"
            )
            print(f"Search result: {master_search_after_reconcile.stdout}")
            print(
                "This means reconcile failed to unhide files that should be visible in current branch"
            )

            # Make the test fail with a clear message
            pytest.fail(
                "RECONCILE BRANCH VISIBILITY BUG DETECTED!\n"
                "After switching from feature to master and running reconcile:\n"
                "- master_only.py exists on disk but is not visible in search results\n"
                "- This means reconcile failed to remove the current branch from the file's hidden_branches\n"
                "- Reconcile should unhide files that exist in the current branch"
            )

        print("✅ Master content is visible after reconcile - bug is fixed!")

        # Step 5: Verify feature content is properly hidden on master
        print("🔍 Step 5: Verifying feature content is hidden on master...")
        feature_search_on_master = run_cli_command(
            ["code-indexer", "query", "feature_implementation"],
            test_dir,
            expect_success=False,
        )

        # Feature content should be hidden on master
        should_not_find_feature = (
            feature_search_on_master.returncode != 0
            or "feature_only.py" not in feature_search_on_master.stdout
        )
        assert (
            should_not_find_feature
        ), "Feature content should be hidden on master branch"
        print("✅ Feature content properly hidden on master branch")

        print("✅ All tests passed - reconcile branch visibility is working correctly!")

    finally:
        try:
            os.chdir(original_cwd)
        except Exception:
            pass


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_manual_reconcile_branch_visibility_workflow(reconcile_branch_test_repo):
    """
    Manual test that documents the exact steps to reproduce the bug.
    This test serves as documentation for the bug reproduction workflow.
    """
    _ = reconcile_branch_test_repo  # Keep for fixture dependency

    print("📋 MANUAL REPRODUCTION STEPS:")
    print("1. Create git repo with master and feature branches having different files")
    print("2. Index both branches to populate database with branch-isolated content")
    print("3. Switch to master and run 'cidx index --reconcile'")
    print("4. Search for content that exists on master but was deleted on feature")
    print("5. BUG: Content should be visible but isn't (remains hidden)")
    print("")
    print("🔧 EXPECTED FIX:")
    print(
        "Reconcile should update hidden_branches to make files visible in current branch"
    )
    print("when they exist on disk but are hidden due to previous branch operations")

    # This test doesn't run the full workflow, just documents it
    pytest.skip("This is a documentation test for manual reproduction steps")
