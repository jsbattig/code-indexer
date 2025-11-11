"""
E2E tests for daemon mode filter functionality.

Tests verify that daemon mode correctly applies filters when querying,
ensuring exclude-path, language, and other filters work as expected.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import subprocess
import time


class TestDaemonFilterE2E:
    """E2E tests for daemon filter functionality."""

    def test_daemon_applies_exclude_path_filter(self, tmp_path):
        """E2E: Daemon mode correctly excludes files matching --exclude-path pattern.

        This test verifies that the fix for daemon filter building works end-to-end.
        Before fix: Daemon ignored exclude-path, returning test files in results.
        After fix: Daemon applies exclude-path filter, excluding test files.
        """
        # Setup test repository with src and test files
        test_repo = tmp_path / "test_repo"
        test_repo.mkdir()

        # Create src file (should be included)
        src_dir = test_repo / "src"
        src_dir.mkdir()
        src_file = src_dir / "main.py"
        src_file.write_text(
            """
def authenticate_user(username, password):
    \"\"\"Authenticate user with credentials.\"\"\"
    return validate_credentials(username, password)
"""
        )

        # Create test file (should be excluded)
        test_dir = test_repo / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_auth.py"
        test_file.write_text(
            """
def test_authenticate_user():
    \"\"\"Test user authentication function.\"\"\"
    result = authenticate_user("user", "pass")
    assert result is True
"""
        )

        # Initialize CIDX
        result = subprocess.run(
            ["cidx", "init"], cwd=test_repo, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Enable daemon mode
        result = subprocess.run(
            ["cidx", "config", "--daemon"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Daemon enable failed: {result.stderr}"

        # Index repository
        result = subprocess.run(
            ["cidx", "index"], cwd=test_repo, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Indexing failed: {result.stderr}"

        # Verify daemon is enabled
        result = subprocess.run(
            ["cidx", "config", "--show"], cwd=test_repo, capture_output=True, text=True
        )
        print("=== Config output ===")
        print(result.stdout)
        print(result.stderr)
        assert "daemon" in result.stdout.lower(), "Daemon should be shown in config"

        # Explicitly start daemon
        result = subprocess.run(
            ["cidx", "start"], cwd=test_repo, capture_output=True, text=True
        )
        print("=== Daemon start output ===")
        print(result.stdout)
        print(result.stderr)

        # Wait for daemon to be ready
        time.sleep(2)

        try:
            # Query with exclude-path filter (daemon mode) - remove --quiet to see mode indicator
            result = subprocess.run(
                ["cidx", "query", "authenticate", "--exclude-path", "*test*"],
                cwd=test_repo,
                capture_output=True,
                text=True,
            )

            print("=== Query output ===")
            print(result.stdout)
            print(result.stderr)

            # Should succeed
            assert result.returncode == 0, f"Query failed: {result.stderr}"

            # Parse results
            output = result.stdout

            # CRITICAL ASSERTION: No test files in results
            assert (
                "test_auth.py" not in output
            ), "test_auth.py should be excluded by --exclude-path filter"

            # Verify src file IS included
            assert (
                "main.py" in output or "src" in output
            ), "main.py should be included in results"

        finally:
            # Cleanup: stop daemon
            subprocess.run(["cidx", "stop"], cwd=test_repo, capture_output=True)
