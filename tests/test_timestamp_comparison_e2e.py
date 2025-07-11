"""
E2E tests for timestamp comparison accuracy in reconcile operations.

These tests verify that:
1. Reconcile correctly identifies files that need reindexing based on timestamps
2. Reconcile doesn't reindex files that are already up-to-date
3. New architecture points have proper timestamp fields for comparison

Marked as e2e tests to exclude from CI due to dependency on real services.
"""

import pytest

import shutil
import time

# Import test infrastructure for proper isolation
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
    create_isolated_project_dir,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with test files."""
    # Use isolated project directory for this test to avoid pollution
    temp_dir = create_isolated_project_dir("timestamp_comparison")

    # Register the test in inventory
    create_test_project_with_inventory(
        temp_dir, TestProjectInventory.TIMESTAMP_COMPARISON
    )

    # Create a simple test project structure
    (temp_dir / "src").mkdir()

    # Add test files
    test_files = {
        "src/unchanged.py": "def unchanged():\n    return 'unchanged'\n",
        "src/modified.py": "def original():\n    return 'original'\n",
        "src/new_file.py": "def new_function():\n    return 'new'\n",
    }

    for file_path, content in test_files.items():
        full_path = temp_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    yield temp_dir

    # Clean up the test directory after test
    # Since we're using isolated directory, we can safely clean it
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def setup_timestamp_test_environment(test_dir):
    """Set up test environment for timestamp tests using simple working pattern."""
    import subprocess

    # Simple, direct setup that actually works (like debug script)
    # Initialize code-indexer
    init_result = subprocess.run(
        ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if init_result.returncode != 0:
        raise RuntimeError(f"Init failed: {init_result.stderr}")

    # Start services directly
    start_result = subprocess.run(
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if start_result.returncode != 0:
        raise RuntimeError(f"Start failed: {start_result.stderr}")

    # Verify services are actually ready
    status_result = subprocess.run(
        ["code-indexer", "status"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if status_result.returncode != 0 or "✅ Ready" not in status_result.stdout:
        raise RuntimeError(f"Services not ready: {status_result.stdout}")

    print("✅ Services confirmed ready with simple setup")
    return test_dir / ".code-indexer"


# smart_indexer fixture removed - all tests now use CLI commands instead of direct function calls


# get_all_points_with_payload helper removed - tests now use CLI commands instead of direct Qdrant access


class TestTimestampComparison:
    """Test timestamp comparison accuracy in reconcile operations."""

    def test_reconcile_correctly_identifies_modified_files(self, temp_project_dir):
        """Test that reconcile identifies files that have been modified since indexing."""
        # Set up test environment with services
        setup_timestamp_test_environment(temp_project_dir)

        self._test_reconcile_correctly_identifies_modified_files(temp_project_dir)

    def _test_reconcile_correctly_identifies_modified_files(self, temp_project_dir):
        import subprocess

        # ✅ Use CLI commands instead of direct function calls (no cheating!)
        # Perform initial index via CLI
        initial_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            initial_result.returncode == 0
        ), f"Initial index failed: {initial_result.stderr}"
        assert "✅ Indexing complete!" in initial_result.stdout

        # Extract files processed from CLI output
        initial_files_processed = 0
        for line in initial_result.stdout.split("\n"):
            if "Files processed:" in line:
                initial_files_processed = int(line.split(":")[-1].strip())
                break
        assert initial_files_processed > 0, "Should process some files initially"

        # Wait to ensure timestamp differences
        time.sleep(1.2)

        # Modify one file
        modified_file = temp_project_dir / "src" / "modified.py"
        original_mtime = modified_file.stat().st_mtime

        modified_file.write_text("def modified():\n    return 'modified content'\n")
        new_mtime = modified_file.stat().st_mtime

        assert new_mtime > original_mtime, "File modification time should increase"

        # Add a completely new file
        new_file = temp_project_dir / "src" / "brand_new.py"
        new_file.write_text("def brand_new():\n    return 'brand new'\n")

        # ✅ Perform reconcile via CLI (no cheating!)
        reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"
        assert "✅ Indexing complete!" in reconcile_result.stdout

        # Extract files processed from CLI output
        reconcile_files_processed = 0
        for line in reconcile_result.stdout.split("\n"):
            if "Files processed:" in line:
                reconcile_files_processed = int(line.split(":")[-1].strip())
                break

        # Should have processed at least the modified and new files
        assert reconcile_files_processed >= 2, (
            f"Should have processed at least 2 files (modified + new), "
            f"but processed {reconcile_files_processed}"
        )

    def test_reconcile_skips_unchanged_files(self, temp_project_dir):
        """Test that reconcile skips files that haven't been modified."""
        # Set up test environment with services
        setup_timestamp_test_environment(temp_project_dir)

        self._test_reconcile_skips_unchanged_files(temp_project_dir)

    def _test_reconcile_skips_unchanged_files(self, temp_project_dir):
        import subprocess

        # ✅ Use CLI commands instead of direct function calls (no cheating!)
        # Perform initial index via CLI
        initial_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            initial_result.returncode == 0
        ), f"Initial index failed: {initial_result.stderr}"

        # Extract files processed from CLI output
        initial_files_processed = 0
        for line in initial_result.stdout.split("\n"):
            if "Files processed:" in line:
                initial_files_processed = int(line.split(":")[-1].strip())
                break
        assert initial_files_processed > 0, "Should process some files initially"

        # Wait to ensure timestamp differences
        time.sleep(1.2)

        # Don't modify any files, just perform reconcile via CLI
        reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"

        # Extract files processed from CLI output
        reconcile_files_processed = 0
        for line in reconcile_result.stdout.split("\n"):
            if "Files processed:" in line:
                reconcile_files_processed = int(line.split(":")[-1].strip())
                break

        # Should not process any files since nothing changed
        assert reconcile_files_processed == 0, (
            f"Should have processed 0 files since nothing changed, "
            f"but processed {reconcile_files_processed}"
        )

    def test_reconcile_handles_timestamp_edge_cases(self, temp_project_dir):
        """Test reconcile handles edge cases in timestamp comparison."""
        # Set up test environment with services
        setup_timestamp_test_environment(temp_project_dir)

        self._test_reconcile_handles_timestamp_edge_cases(temp_project_dir)

    def _test_reconcile_handles_timestamp_edge_cases(self, temp_project_dir):
        import subprocess

        # ✅ Use CLI commands instead of direct function calls (no cheating!)
        # Perform initial index via CLI
        initial_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            initial_result.returncode == 0
        ), f"Initial index failed: {initial_result.stderr}"
        assert "✅ Indexing complete!" in initial_result.stdout

        # Extract files processed from CLI output
        initial_files_processed = 0
        for line in initial_result.stdout.split("\n"):
            if "Files processed:" in line:
                initial_files_processed = int(line.split(":")[-1].strip())
                break
        assert initial_files_processed > 0, "Should process some files initially"

        # Wait a short time
        time.sleep(1.2)

        # Modify a file with a very recent timestamp (edge case)
        test_file = temp_project_dir / "src" / "unchanged.py"
        test_file.write_text("def unchanged():\n    return 'slightly changed'\n")

        # ✅ Perform reconcile via CLI (no cheating!)
        reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"
        assert "✅ Indexing complete!" in reconcile_result.stdout

        # Extract files processed from CLI output
        reconcile_files_processed = 0
        for line in reconcile_result.stdout.split("\n"):
            if "Files processed:" in line:
                reconcile_files_processed = int(line.split(":")[-1].strip())
                break

        # Should detect the change despite small time difference
        assert (
            reconcile_files_processed >= 1
        ), "Should have detected the modified file despite small timestamp difference"

    def test_new_architecture_points_have_comparable_timestamps(self, temp_project_dir):
        """Test that new architecture points have timestamps that can be compared."""
        # Set up test environment with services
        setup_timestamp_test_environment(temp_project_dir)

        self._test_new_architecture_points_have_comparable_timestamps(temp_project_dir)

    def _test_new_architecture_points_have_comparable_timestamps(
        self, temp_project_dir
    ):
        import subprocess

        # ✅ Use CLI commands instead of direct function calls (no cheating!)
        # Perform initial index via CLI
        initial_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            initial_result.returncode == 0
        ), f"Initial index failed: {initial_result.stderr}"
        assert "✅ Indexing complete!" in initial_result.stdout

        # Extract files processed from CLI output
        initial_files_processed = 0
        for line in initial_result.stdout.split("\n"):
            if "Files processed:" in line:
                initial_files_processed = int(line.split(":")[-1].strip())
                break
        assert initial_files_processed > 0, "Should process some files initially"

        # Test that reconcile works (indicating timestamps are comparable)
        # This is an indirect test - if timestamps weren't comparable, reconcile would fail
        reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"
        assert "✅ Indexing complete!" in reconcile_result.stdout

        # Extract files processed from CLI output
        reconcile_files_processed = 0
        for line in reconcile_result.stdout.split("\n"):
            if "Files processed:" in line:
                reconcile_files_processed = int(line.split(":")[-1].strip())
                break

        # Should not process any files since nothing changed, but reconcile should succeed
        # This confirms that timestamps are comparable and working correctly
        assert reconcile_files_processed == 0, (
            f"Should have processed 0 files since nothing changed, "
            f"but processed {reconcile_files_processed}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
