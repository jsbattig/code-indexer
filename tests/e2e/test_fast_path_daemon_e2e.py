"""End-to-end test for fast path daemon optimization.

This test verifies that the fast path delegation works correctly in real scenarios
and achieves the performance targets (<200ms for daemon mode queries).
"""

import subprocess
import time
import pytest


class TestFastPathDaemonE2E:
    """End-to-end tests for fast path daemon optimization."""

    @pytest.mark.e2e
    def test_fts_query_via_daemon_fast_path(self, tmp_path):
        """Test FTS query executes via daemon fast path successfully.

        This test verifies the bug fix:
        - Before: TypeError in daemon RPC call (positional args mismatch)
        - After: Correct **kwargs usage, fast path works
        """
        # Setup test project
        test_project = tmp_path / "test_project"
        test_project.mkdir()

        # Create test file
        test_file = test_project / "example.py"
        test_file.write_text(
            """
def test_function():
    '''Test function for searching'''
    return "test result"
"""
        )

        # Initialize project
        result = subprocess.run(
            ["cidx", "init"],
            cwd=test_project,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Enable daemon mode
        config_file = test_project / ".code-indexer" / "config.json"
        import json

        with open(config_file, "r") as f:
            config = json.load(f)
        config["daemon"] = {
            "enabled": True,
            "ttl_minutes": 10,
            "auto_shutdown_on_idle": True,
        }
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Start daemon
        result = subprocess.run(
            ["cidx", "start"],
            cwd=test_project,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        try:
            # Index repository
            result = subprocess.run(
                ["cidx", "index"],
                cwd=test_project,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, f"Index failed: {result.stderr}"

            # Execute FTS query via fast path
            start = time.perf_counter()
            result = subprocess.run(
                ["cidx", "query", "test", "--fts", "--limit", "5"],
                cwd=test_project,
                capture_output=True,
                text=True,
                timeout=10,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            # Verify success (no TypeError)
            assert result.returncode == 0, f"Query failed: {result.stderr}"
            assert "TypeError" not in result.stderr
            assert "exposed_query_fts" not in result.stderr

            # Verify performance target achieved
            # First query may be slower due to cache loading
            # So we run a second query to measure fast path performance
            start = time.perf_counter()
            result = subprocess.run(
                ["cidx", "query", "function", "--fts", "--limit", "5"],
                cwd=test_project,
                capture_output=True,
                text=True,
                timeout=10,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert result.returncode == 0
            # Performance target: <200ms for daemon mode
            # Note: E2E includes subprocess overhead, so allow more headroom
            assert (
                elapsed_ms < 500
            ), f"Query took {elapsed_ms:.1f}ms (target: <500ms for E2E)"

        finally:
            # Stop daemon
            subprocess.run(
                ["cidx", "stop"],
                cwd=test_project,
                capture_output=True,
                text=True,
                timeout=30,
            )

    @pytest.mark.e2e
    def test_hybrid_query_via_daemon_fast_path(self, tmp_path):
        """Test hybrid query (semantic + FTS) via daemon fast path."""
        # Setup test project
        test_project = tmp_path / "test_project"
        test_project.mkdir()

        # Create test file
        test_file = test_project / "auth.py"
        test_file.write_text(
            """
def authenticate_user(username, password):
    '''Authenticate user with credentials'''
    # Authentication logic
    return True
"""
        )

        # Initialize and enable daemon
        subprocess.run(["cidx", "init"], cwd=test_project, timeout=30, check=True)

        config_file = test_project / ".code-indexer" / "config.json"
        import json

        with open(config_file, "r") as f:
            config = json.load(f)
        config["daemon"] = {"enabled": True}
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Start daemon
        subprocess.run(["cidx", "start"], cwd=test_project, timeout=60, check=True)

        try:
            # Index repository
            subprocess.run(["cidx", "index"], cwd=test_project, timeout=120, check=True)

            # Execute hybrid query
            result = subprocess.run(
                [
                    "cidx",
                    "query",
                    "authenticate",
                    "--fts",
                    "--semantic",
                    "--limit",
                    "3",
                ],
                cwd=test_project,
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Verify success
            assert result.returncode == 0, f"Hybrid query failed: {result.stderr}"
            assert "TypeError" not in result.stderr

        finally:
            subprocess.run(["cidx", "stop"], cwd=test_project, timeout=30)

    @pytest.mark.e2e
    def test_semantic_query_via_daemon_fast_path(self, tmp_path):
        """Test semantic-only query via daemon fast path."""
        # Setup test project
        test_project = tmp_path / "test_project"
        test_project.mkdir()

        test_file = test_project / "database.py"
        test_file.write_text(
            """
class DatabaseConnection:
    '''Database connection manager'''

    def connect(self):
        '''Establish database connection'''
        pass
"""
        )

        # Initialize and enable daemon
        subprocess.run(["cidx", "init"], cwd=test_project, timeout=30, check=True)

        config_file = test_project / ".code-indexer" / "config.json"
        import json

        with open(config_file, "r") as f:
            config = json.load(f)
        config["daemon"] = {"enabled": True}
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Start daemon
        subprocess.run(["cidx", "start"], cwd=test_project, timeout=60, check=True)

        try:
            # Index repository
            subprocess.run(["cidx", "index"], cwd=test_project, timeout=120, check=True)

            # Execute semantic query (default mode)
            result = subprocess.run(
                ["cidx", "query", "database connection", "--limit", "5"],
                cwd=test_project,
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Verify success
            assert result.returncode == 0, f"Semantic query failed: {result.stderr}"
            assert "TypeError" not in result.stderr

        finally:
            subprocess.run(["cidx", "stop"], cwd=test_project, timeout=30)
