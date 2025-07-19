"""
End-to-end test for watch timestamp update functionality.

This test verifies that files indexed by watch mode have their timestamps
properly updated in the database, preventing re-indexing during incremental operations.
"""

import os
import time
import subprocess
import pytest

from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)
from .conftest import local_temporary_directory

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = [pytest.mark.e2e]


@pytest.fixture
def watch_timestamp_test_repo():
    """Create a test repository for watch timestamp tests."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.WATCH_TIMESTAMP_UPDATE
        )
        yield temp_dir


def create_test_files(test_dir):
    """Create test files for the timestamp test."""
    # Create main.py
    (test_dir / "main.py").write_text(
        """def main():
    '''Main application entry point'''
    print("Hello World")
    return 0

if __name__ == "__main__":
    main()
"""
    )

    # Create utils.py
    (test_dir / "utils.py").write_text(
        """def utility_function(data):
    '''Utility function for data processing'''
    return data.upper()

class Helper:
    '''Helper class for common operations'''
    def process(self, item):
        return item * 2
"""
    )

    # Create README.md
    (test_dir / "README.md").write_text(
        """# Test Project

This is a test project for watch timestamp functionality.

## Features

- Watch for file changes
- Proper timestamp tracking
- No redundant re-indexing
"""
    )


def init_git_repo(test_dir):
    """Initialize git repository."""
    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )

    # Create .gitignore
    (test_dir / ".gitignore").write_text(
        """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
"""
    )

    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=test_dir,
        check=True,
        capture_output=True,
    )


class TestWatchTimestampUpdateE2E:
    """End-to-end tests for watch timestamp update functionality."""

    @pytest.mark.skipif(
        not os.getenv("VOYAGE_API_KEY"),
        reason="VoyageAI API key required for E2E tests",
    )
    @pytest.mark.skipif(
        os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
        reason="E2E tests require Docker services which are not available in CI",
    )
    def test_watch_timestamp_prevents_reindexing(self, watch_timestamp_test_repo):
        """Test that files indexed by watch are not re-indexed by incremental indexing."""
        test_dir = watch_timestamp_test_repo

        # Create test files
        create_test_files(test_dir)

        # Initialize git repository
        init_git_repo(test_dir)

        # Initialize code-indexer
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        try:
            # Perform initial index
            index_result = subprocess.run(
                ["code-indexer", "index"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert (
                index_result.returncode == 0
            ), f"Initial index failed: {index_result.stderr}"

            # Extract initial indexing stats
            initial_files_indexed = 0
            for line in index_result.stdout.split("\n"):
                if "files processed" in line:
                    # Extract number from line like "3 files processed"
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        initial_files_indexed = int(parts[0])
                        break

            assert initial_files_indexed > 0, "Should have indexed some files initially"

            # Start watch process in background
            watch_process = subprocess.Popen(
                ["code-indexer", "watch", "--debounce", "0.5"],
                cwd=test_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                # Wait for watch to start
                time.sleep(3)

                # Modify a file while watch is running
                utils_file = test_dir / "utils.py"
                original_content = utils_file.read_text()
                modified_content = (
                    original_content
                    + """

def new_function():
    '''Function added during watch'''
    return "watch test"
"""
                )
                utils_file.write_text(modified_content)

                # Wait for watch to process the change
                time.sleep(3)

                # Stop watch
                watch_process.terminate()
                watch_process.wait(timeout=5)

            except Exception as e:
                watch_process.kill()
                raise e

            # Now run incremental index with reconcile
            reconcile_result = subprocess.run(
                ["code-indexer", "index", "--reconcile"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert (
                reconcile_result.returncode == 0
            ), f"Reconcile failed: {reconcile_result.stderr}"

            # Check reconcile output for re-indexing
            reconcile_output = reconcile_result.stdout
            print(f"Reconcile output:\n{reconcile_output}")

            # Look for evidence of re-indexing
            files_to_index_found = False
            reindexed_count = 0
            for line in reconcile_output.split("\n"):
                if "files to index" in line.lower() and "0 files to index" not in line:
                    files_to_index_found = True
                if "files processed" in line:
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        reindexed_count = int(parts[0])

            # The key assertion: reconcile should NOT find files to re-index
            # because watch should have properly updated timestamps
            assert not files_to_index_found or reindexed_count == 0, (
                f"Reconcile should not re-index files that were just indexed by watch. "
                f"Found {reindexed_count} files to re-index in output:\n{reconcile_output}"
            )

            # Verify by checking for "already up-to-date" or similar messages
            up_to_date_indicators = [
                "0 files to index",
                "already up-to-date",
                "no changes detected",
                "nothing to index",
            ]
            found_up_to_date = any(
                indicator in reconcile_output.lower()
                for indicator in up_to_date_indicators
            )

            assert found_up_to_date or reindexed_count == 0, (
                "Reconcile should report that files are up-to-date after watch indexing. "
                f"Output:\n{reconcile_output}"
            )

        finally:
            # Clean up
            subprocess.run(
                ["code-indexer", "clean", "--remove-data", "--quiet"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

    @pytest.mark.skipif(
        not os.getenv("VOYAGE_API_KEY"),
        reason="VoyageAI API key required for E2E tests",
    )
    @pytest.mark.skipif(
        os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
        reason="E2E tests require Docker services which are not available in CI",
    )
    def test_watch_timestamp_with_multiple_files(self, watch_timestamp_test_repo):
        """Test timestamp update with multiple file changes during watch."""
        test_dir = watch_timestamp_test_repo

        # Create test files
        create_test_files(test_dir)

        # Initialize git repository
        init_git_repo(test_dir)

        # Initialize and start services
        subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=test_dir,
            check=True,
            capture_output=True,
            timeout=120,
        )

        try:
            # Initial index
            subprocess.run(
                ["code-indexer", "index"],
                cwd=test_dir,
                check=True,
                capture_output=True,
                timeout=120,
            )

            # Start watch
            watch_process = subprocess.Popen(
                ["code-indexer", "watch", "--debounce", "0.5"],
                cwd=test_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                # Wait for watch to start
                time.sleep(3)

                # Create multiple new files while watch is running
                for i in range(3):
                    new_file = test_dir / f"module_{i}.py"
                    new_file.write_text(
                        f"""def module_{i}_function():
    '''Function in module {i}'''
    return "module {i} result"

class Module{i}Class:
    '''Class in module {i}'''
    def method(self):
        return {i}
"""
                    )
                    # Small delay between file creations
                    time.sleep(0.5)

                # Modify existing files
                (test_dir / "main.py").write_text(
                    """def main():
    '''Modified main function'''
    print("Hello Modified World")
    return 1

def additional_function():
    '''Added by watch test'''
    return "test"

if __name__ == "__main__":
    main()
"""
                )

                # Wait for watch to process all changes
                time.sleep(5)

                # Stop watch
                watch_process.terminate()
                watch_process.wait(timeout=5)

            except Exception as e:
                watch_process.kill()
                raise e

            # Run reconcile
            reconcile_result = subprocess.run(
                ["code-indexer", "index", "--reconcile"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert (
                reconcile_result.returncode == 0
            ), f"Reconcile failed: {reconcile_result.stderr}"

            # Check that no files were re-indexed
            reconcile_output = reconcile_result.stdout
            print(f"Reconcile output after multiple file changes:\n{reconcile_output}")

            # Extract stats
            reindexed_count = 0
            for line in reconcile_output.split("\n"):
                if "files processed" in line:
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        reindexed_count = int(parts[0])
                        break

            assert reindexed_count == 0, (
                f"Reconcile should not re-index any files after watch. "
                f"Found {reindexed_count} files re-indexed."
            )

        finally:
            # Clean up
            subprocess.run(
                ["code-indexer", "clean", "--remove-data", "--quiet"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
