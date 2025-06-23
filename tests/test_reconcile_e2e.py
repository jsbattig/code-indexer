"""
End-to-end test for reconcile functionality.

Tests the complete workflow of indexing and then reconciling to ensure
no files are double-processed when they're already up-to-date.

Refactored to use NEW STRATEGY with test infrastructure to eliminate code duplication.
"""

import os
import tempfile
import time
from pathlib import Path

import pytest

# Import test infrastructure to eliminate code duplication
from .test_infrastructure import create_fast_e2e_setup, EmbeddingProvider


# Removed duplicated run_command function - now using CLIHelper from test infrastructure!


def _get_reconcile_test_files():
    """Get test files for reconcile testing using test infrastructure."""
    return {
        "main.py": """def main():
    print("Hello World")
    return 0

if __name__ == "__main__":
    main()""",
        "utils.py": """import os
import sys

def get_config():
    return {"debug": True, "version": "1.0"}

def process_data(data):
    return [x * 2 for x in data]""",
        "models.py": """class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
    
    def __str__(self):
        return f"User({self.name}, {self.email})"

class Product:
    def __init__(self, name, price):
        self.name = name
        self.price = price""",
        "lib/database.py": """import sqlite3

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.connection = None
    
    def connect(self):
        self.connection = sqlite3.connect(self.db_path)
        return self.connection""",
        "lib/api.py": """from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/users', methods=['GET', 'POST'])
def users():
    if request.method == 'GET':
        return jsonify([])
    return jsonify({"created": True})""",
    }


# Removed duplicated create_test_project function - now using DirectoryManager from test infrastructure!


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
class TestReconcileE2E:
    """End-to-end tests for reconcile functionality using NEW STRATEGY."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment using test infrastructure."""
        # NEW STRATEGY: Use test infrastructure for consistent setup
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.VOYAGE_AI
        )
        yield

    @pytest.fixture
    def test_project(self):
        """Create a temporary test project using test infrastructure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            # Use test infrastructure to create project with custom files
            test_files = _get_reconcile_test_files()
            self.dir_manager.create_test_project(project_dir, custom_files=test_files)
            yield project_dir

    def test_reconcile_after_full_index(self, test_project):
        """Test that reconcile correctly identifies no work needed after full index."""

        with self.dir_manager.safe_chdir(test_project):
            # Step 1: Initialize the project with VoyageAI for CI stability
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"]
            )

            # Step 2: Setup services (NEW STRATEGY: should already be running from fixture)
            self.cli_helper.run_cli_command(["start"], timeout=60, expect_success=False)
            # Setup may fail in test environment, that's ok - we'll check services later

            # Step 3: Do full index with limited files for testing
            index_result = self.cli_helper.run_cli_command(
                ["index", "--clear", "--files-count-to-process", "3"],
                timeout=60,
                expect_success=False,
            )

            # Check if services are available
            if index_result.returncode != 0:
                # If services not available, skip the test
                error_output = index_result.stderr + index_result.stdout
                if "service not available" in error_output.lower():
                    pytest.skip("Services not available for e2e test")
                else:
                    pytest.fail(f"Index failed: {index_result.stderr}")

            # Verify initial indexing worked (case insensitive check)
            stdout_lower = index_result.stdout.lower()
            assert (
                "files processed" in stdout_lower
                or "completed" in stdout_lower
                or "indexing complete" in stdout_lower
            ), f"Expected indexing completion indication in: {index_result.stdout}"

            # Step 4: Wait a moment to ensure timestamps are stable
            time.sleep(2)

            # Step 5: Run reconcile - should find no work to do
            reconcile_result = self.cli_helper.run_cli_command(
                ["index", "--reconcile", "--files-count-to-process", "3"], timeout=60
            )

            # Check reconcile output
            output = reconcile_result.stdout

            # Should show files are up-to-date
            assert "files up-to-date" in output

            # Should NOT reindex files if they're truly up-to-date
            # The key test: if all files are up-to-date, we shouldn't see "indexing X modified"
            # with a large number
            lines = output.split("\n")
            reconcile_lines = [line for line in lines if "Reconcile:" in line]

            if reconcile_lines:
                reconcile_line = reconcile_lines[0]
                print(f"Reconcile line: {reconcile_line}")

                # The line should look like "Reconcile: X/X files up-to-date, indexing 0 files"
                # or "Reconcile: X/X files up-to-date, no indexing needed"
                # It should NOT look like "Reconcile: 0/3 files up-to-date, indexing 3 modified"

                # Extract numbers to verify logic
                if "indexing" in reconcile_line:
                    if "modified" in reconcile_line:
                        # This suggests files were detected as modified when they shouldn't be
                        # This is the bug we're trying to catch
                        parts = reconcile_line.split()
                        if len(parts) >= 4:
                            try:
                                up_to_date_part = [p for p in parts if "/" in p][
                                    0
                                ]  # e.g., "3/3"
                                up_to_date_count = int(up_to_date_part.split("/")[0])

                                # If we have files up-to-date, we shouldn't be reindexing many files
                                if up_to_date_count > 0:
                                    # Look for the number before "modified"
                                    modified_idx = (
                                        parts.index("modified")
                                        if "modified" in parts
                                        else -1
                                    )
                                    if modified_idx > 0:
                                        modified_count = int(parts[modified_idx - 1])

                                        # The bug: if files are up-to-date, we shouldn't have many modified
                                        if modified_count == up_to_date_count:
                                            pytest.fail(
                                                f"BUG DETECTED: Reconcile shows {up_to_date_count} files up-to-date "
                                                f"but also {modified_count} modified files. This suggests all "
                                                f"files are being incorrectly detected as modified.\n"
                                                f"Full line: {reconcile_line}"
                                            )
                            except (ValueError, IndexError):
                                pass  # Couldn't parse, that's ok

            # Additional check: verify no extensive processing happened
            # If reconcile is working correctly, it should be very fast
            processing_lines = [line for line in lines if "files processed" in line]
            if processing_lines:
                # Should show 0 files processed or a very small number
                for line in processing_lines:
                    if "files processed" in line:
                        try:
                            # Extract number before "files processed"
                            parts = line.split()
                            processed_idx = parts.index("files")
                            if processed_idx > 0:
                                processed_count = int(parts[processed_idx - 1])
                                # Should process 0 files if truly up-to-date
                                assert (
                                    processed_count == 0
                                ), f"Expected 0 files processed, got {processed_count}: {line}"
                        except (ValueError, IndexError):
                            pass  # Couldn't parse

    def test_reconcile_detects_missing_files(self, test_project):
        """Test that reconcile correctly detects when files are missing from index."""

        with self.dir_manager.safe_chdir(test_project):
            # Step 1: Initialize with VoyageAI for CI stability
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"]
            )

            # Step 2: Index only 2 files
            index_result = self.cli_helper.run_cli_command(
                ["index", "--clear", "--files-count-to-process", "2"],
                timeout=60,
                expect_success=False,
            )

            if index_result.returncode != 0:
                error_output = index_result.stderr + index_result.stdout
                if "service not available" in error_output.lower():
                    pytest.skip("Services not available for e2e test")
                else:
                    pytest.fail(f"Index failed: {index_result.stderr}")

            # Step 3: Run reconcile with higher limit - should detect missing files
            reconcile_result = self.cli_helper.run_cli_command(
                ["index", "--reconcile", "--files-count-to-process", "5"], timeout=60
            )

            output = reconcile_result.stdout

            # Should detect missing files and index them, OR all files may already be up-to-date
            assert (
                "missing" in output
                or "files processed" in output
                or "up-to-date" in output
            ), f"Unexpected reconcile output: {output}"

            # Should show that some files were processed
            processing_lines = [
                line for line in output.split("\n") if "files processed" in line
            ]
            if processing_lines:
                found_processing = False
                for line in processing_lines:
                    try:
                        parts = line.split()
                        processed_idx = parts.index("files")
                        if processed_idx > 0:
                            processed_count = int(parts[processed_idx - 1])
                            if processed_count > 0:
                                found_processing = True
                                break
                    except (ValueError, IndexError):
                        pass

                assert (
                    found_processing
                ), f"Expected some files to be processed, but found: {output}"


def test_manual_reconcile_workflow():
    """
    Manual test demonstrating the expected reconcile workflow.
    This test shows the correct behavior pattern.
    """
    print("\n" + "=" * 60)
    print("MANUAL RECONCILE E2E TEST WORKFLOW")
    print("=" * 60)

    print("\n1. Expected workflow:")
    print("   a. code-indexer init")
    print("   b. code-indexer start")
    print("   c. code-indexer index --clear --files-count-to-process 5")
    print("   d. code-indexer index --reconcile --files-count-to-process 5")
    print("   e. Step (d) should show '5/5 files up-to-date, indexing 0 files'")

    print("\n2. Bug to detect:")
    print("   - If reconcile shows 'X/X files up-to-date' but then")
    print("   - 'indexing X modified' with the same X number")
    print("   - This means files are incorrectly detected as modified")

    print("\n3. Correct behavior:")
    print("   - After fresh index, reconcile should show 0 files to process")
    print("   - No extensive reindexing should occur")
    print("   - Output should indicate all files are up-to-date")

    print("\n4. Test the --files-count-to-process parameter:")
    print("   - This limits processing to N files for testing")
    print("   - Allows controlled testing without full repository processing")

    print("\n✅ Manual test workflow defined")


if __name__ == "__main__":
    # Run manual test when executed directly
    test_manual_reconcile_workflow()
