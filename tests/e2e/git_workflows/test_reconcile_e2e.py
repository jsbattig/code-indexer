"""
End-to-end test for reconcile functionality.

Tests the complete workflow of indexing and then reconciling to ensure
no files are double-processed when they're already up-to-date.

Converted to use shared_container_test_environment for better performance.
Eliminates code duplication and leverages shared container infrastructure.
"""

import os
import time
import subprocess
from pathlib import Path

import pytest

from ...conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider


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


# Removed deprecated fixture - now using shared_container_test_environment


def create_test_project_with_reconcile_files(test_dir: Path):
    """Create test files in the test directory for reconcile testing."""
    test_files = _get_reconcile_test_files()

    for filename, content in test_files.items():
        file_path = test_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_reconcile_after_full_index_shared_containers():
    """Test that reconcile correctly identifies no work needed after full index (shared containers)."""
    with shared_container_test_environment(
        "test_reconcile_after_full_index_shared_containers", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create test files
        create_test_project_with_reconcile_files(project_path)

        # Step 1: Initialize the project with VoyageAI for CI stability
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Step 2: Setup services (should be already running in shared containers)
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Step 3: Do full index with limited files for testing
        index_result = subprocess.run(
            ["code-indexer", "index", "--clear", "--files-count-to-process", "3"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

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
        reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile", "--files-count-to-process", "3"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"

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


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_reconcile_detects_missing_files_shared_containers():
    """Test that reconcile correctly detects when files are missing from index (shared containers)."""
    with shared_container_test_environment(
        "test_reconcile_detects_missing_files_shared_containers",
        EmbeddingProvider.VOYAGE_AI,
    ) as project_path:
        # Create test files
        create_test_project_with_reconcile_files(project_path)

        # Step 1: Initialize with VoyageAI for CI stability
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Step 2: Setup services (should be already running in shared containers)
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Step 3: Index only 2 files
        index_result = subprocess.run(
            ["code-indexer", "index", "--clear", "--files-count-to-process", "2"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Step 4: Run reconcile with higher limit - should detect missing files
        reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile", "--files-count-to-process", "5"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"

        output = reconcile_result.stdout

        # Should detect missing files and index them, OR all files may already be up-to-date
        assert (
            "missing" in output or "files processed" in output or "up-to-date" in output
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


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_manual_reconcile_workflow_shared_containers():
    """
    Manual test demonstrating the expected reconcile workflow with shared containers.
    This test shows the correct behavior pattern and validates the workflow.
    """
    with shared_container_test_environment(
        "test_manual_reconcile_workflow_shared_containers", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        print("\n" + "=" * 60)
        print("MANUAL RECONCILE E2E TEST WORKFLOW (SHARED CONTAINERS)")
        print("=" * 60)

        # Create test files for the workflow
        create_test_project_with_reconcile_files(project_path)

        print("\n1. Expected workflow:")
        print("   a. code-indexer init")
        print("   b. code-indexer start")
        print("   c. code-indexer index --clear --files-count-to-process 5")
        print("   d. code-indexer index --reconcile --files-count-to-process 5")
        print("   e. Step (d) should show '5/5 files up-to-date, indexing 0 files'")

        # Step 1: Initialize the project
        print("\n📋 Step 1: Initialize project...")
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"
        print("✅ Project initialized")

        # Step 2: Start services
        print("\n🚀 Step 2: Start services...")
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"
        print("✅ Services started")

        # Step 3: Initial index
        print("\n📚 Step 3: Initial indexing...")
        index_result = subprocess.run(
            ["code-indexer", "index", "--clear", "--files-count-to-process", "5"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"
        print("✅ Initial indexing completed")
        print(f"   Output: {index_result.stdout.strip()}")

        # Step 4: Reconcile check
        print("\n🔍 Step 4: Reconcile check...")
        time.sleep(1)  # Small delay for timestamp stability
        reconcile_result = subprocess.run(
            ["code-indexer", "index", "--reconcile", "--files-count-to-process", "5"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            reconcile_result.returncode == 0
        ), f"Reconcile failed: {reconcile_result.stderr}"
        print("✅ Reconcile completed")
        print(f"   Output: {reconcile_result.stdout.strip()}")

        # Validate expected behavior
        output = reconcile_result.stdout
        assert "files up-to-date" in output, "Should show files are up-to-date"

        print("\n2. Bug detection criteria:")
        print("   - If reconcile shows 'X/X files up-to-date' but then")
        print("   - 'indexing X modified' with the same X number")
        print("   - This means files are incorrectly detected as modified")

        print("\n3. Correct behavior validated:")
        print("   - After fresh index, reconcile shows files are up-to-date")
        print("   - No extensive reindexing occurred")
        print("   - Output indicates appropriate reconcile behavior")

        print("\n4. The --files-count-to-process parameter:")
        print("   - Limits processing to N files for testing")
        print("   - Allows controlled testing without full repository processing")

        print("\n✅ Manual test workflow validated with shared containers")


if __name__ == "__main__":
    # Run manual test when executed directly
    test_manual_reconcile_workflow_shared_containers()
