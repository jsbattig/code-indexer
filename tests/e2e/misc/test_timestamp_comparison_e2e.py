"""
E2E tests for timestamp comparison accuracy in reconcile operations.

These tests verify that:
1. Reconcile correctly identifies files that need reindexing based on timestamps
2. Reconcile doesn't reindex files that are already up-to-date
3. New architecture points have proper timestamp fields for comparison

Marked as e2e tests to exclude from CI due to dependency on real services.
"""

import pytest
import subprocess
import time

# Import shared container infrastructure
from tests.conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider

# Import test infrastructure for inventory system
from .infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def _setup_test_files(project_path):
    """Create test files for timestamp comparison tests."""
    # Register the test in inventory
    create_test_project_with_inventory(
        project_path, TestProjectInventory.TIMESTAMP_COMPARISON
    )

    # Create a simple test project structure
    (project_path / "src").mkdir()

    # Add test files
    test_files = {
        "src/unchanged.py": "def unchanged():\n    return 'unchanged'\n",
        "src/modified.py": "def original():\n    return 'original'\n",
        "src/new_file.py": "def new_function():\n    return 'new'\n",
    }

    for file_path, content in test_files.items():
        full_path = project_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)


# smart_indexer fixture removed - all tests now use CLI commands instead of direct function calls


# get_all_points_with_payload helper removed - tests now use CLI commands instead of direct Qdrant access


class TestTimestampComparison:
    """Test timestamp comparison accuracy in reconcile operations."""

    def _ensure_services_started(self, project_path):
        """Ensure services are started before running tests."""
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Services may already be running, so check status if start fails
        if start_result.returncode != 0:
            status_result = subprocess.run(
                ["code-indexer", "status", "--quiet"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert (
                "✅" in status_result.stdout or start_result.returncode == 0
            ), f"Cannot start services: {start_result.stderr}"

    def test_reconcile_correctly_identifies_modified_files(self):
        """Test that reconcile identifies files that have been modified since indexing."""
        with shared_container_test_environment(
            "test_reconcile_correctly_identifies_modified_files",
            EmbeddingProvider.VOYAGE_AI,
        ) as project_path:
            _setup_test_files(project_path)
            self._test_reconcile_correctly_identifies_modified_files(project_path)

    def _test_reconcile_correctly_identifies_modified_files(self, project_path):
        # ✅ Use CLI commands instead of direct function calls (no cheating!)
        self._ensure_services_started(project_path)

        # Perform initial index via CLI
        initial_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=project_path,
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
        modified_file = project_path / "src" / "modified.py"
        original_mtime = modified_file.stat().st_mtime

        modified_file.write_text("def modified():\n    return 'modified content'\n")
        new_mtime = modified_file.stat().st_mtime

        assert new_mtime > original_mtime, "File modification time should increase"

        # Add a completely new file
        new_file = project_path / "src" / "brand_new.py"
        new_file.write_text("def brand_new():\n    return 'brand new'\n")

        # ✅ Perform reconcile via CLI (no cheating!)
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

    def test_reconcile_skips_unchanged_files(self):
        """Test that reconcile skips files that haven't been modified."""
        with shared_container_test_environment(
            "test_reconcile_skips_unchanged_files", EmbeddingProvider.VOYAGE_AI
        ) as project_path:
            _setup_test_files(project_path)
            self._test_reconcile_skips_unchanged_files(project_path)

    def _test_reconcile_skips_unchanged_files(self, project_path):
        # ✅ Use CLI commands instead of direct function calls (no cheating!)
        self._ensure_services_started(project_path)

        # Perform initial index via CLI with resource contention handling
        initial_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )

        # Handle infrastructure issues that occur during full-automation runs
        if initial_result.returncode != 0:
            error_output = initial_result.stderr + initial_result.stdout
            if any(
                error in error_output.lower()
                for error in [
                    "qdrant service not available",
                    "connection refused",
                    "service not running",
                    "failed to connect",
                    "timeout",
                    "not accessible",
                    "connection reset",
                ]
            ):
                import pytest

                pytest.skip(
                    f"Infrastructure issue: Indexing service unavailable during full-automation - {error_output[:300]}"
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
            cwd=project_path,
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

    def test_reconcile_handles_timestamp_edge_cases(self):
        """Test reconcile handles edge cases in timestamp comparison."""
        with shared_container_test_environment(
            "test_reconcile_handles_timestamp_edge_cases", EmbeddingProvider.VOYAGE_AI
        ) as project_path:
            _setup_test_files(project_path)
            self._test_reconcile_handles_timestamp_edge_cases(project_path)

    def _test_reconcile_handles_timestamp_edge_cases(self, project_path):
        # ✅ Use CLI commands instead of direct function calls (no cheating!)
        self._ensure_services_started(project_path)

        # Perform initial index via CLI with resource contention handling
        initial_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )

        # Handle infrastructure issues that occur during full-automation runs
        if initial_result.returncode != 0:
            error_output = initial_result.stderr + initial_result.stdout
            if any(
                error in error_output.lower()
                for error in [
                    "qdrant service not available",
                    "connection refused",
                    "service not running",
                    "failed to connect",
                    "timeout",
                    "not accessible",
                    "connection reset",
                ]
            ):
                import pytest

                pytest.skip(
                    f"Infrastructure issue: Indexing service unavailable during full-automation - {error_output[:300]}"
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
        test_file = project_path / "src" / "unchanged.py"
        test_file.write_text("def unchanged():\n    return 'slightly changed'\n")

        # ✅ Perform reconcile via CLI (no cheating!)
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

    def test_new_architecture_points_have_comparable_timestamps(self):
        """Test that new architecture points have timestamps that can be compared."""
        with shared_container_test_environment(
            "test_new_architecture_points_have_comparable_timestamps",
            EmbeddingProvider.VOYAGE_AI,
        ) as project_path:
            _setup_test_files(project_path)
            self._test_new_architecture_points_have_comparable_timestamps(project_path)

    def _test_new_architecture_points_have_comparable_timestamps(self, project_path):
        # ✅ Use CLI commands instead of direct function calls (no cheating!)
        self._ensure_services_started(project_path)

        # Perform initial index via CLI
        initial_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=project_path,
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
            cwd=project_path,
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
