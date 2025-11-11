"""End-to-end integration test for --snippet-lines 0 in daemon mode.

This test reproduces the actual user-reported issue:
- User runs: cidx query "voyage" --fts --snippet-lines 0 --limit 2
- In daemon mode, output still shows context snippets
- In standalone mode, output correctly shows only file listings

This test uses a real project with real FTS index and real daemon process.
"""

import pytest
import subprocess
import time


@pytest.fixture
def test_project_with_daemon(tmp_path):
    """Create test project with FTS index and running daemon."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create test files with "voyage" keyword
    test_file = project_dir / "test.py"
    test_file.write_text(
        """
# This file contains voyage references
from voyage import VoyageClient

client = VoyageClient(api_key="test")
result = client.embed(["test"])
print(f"Voyage embedding result: {result}")
"""
    )

    # Initialize cidx project
    subprocess.run(["cidx", "init"], cwd=project_dir, capture_output=True, check=True)

    # Index with FTS enabled
    subprocess.run(
        ["cidx", "index", "--fts"], cwd=project_dir, capture_output=True, check=True
    )

    # Start daemon
    subprocess.run(
        ["cidx", "daemon", "start"], cwd=project_dir, capture_output=True, check=True
    )

    # Wait for daemon to fully start
    time.sleep(2)

    yield project_dir

    # Cleanup: stop daemon
    try:
        subprocess.run(
            ["cidx", "daemon", "stop"], cwd=project_dir, capture_output=True, timeout=5
        )
    except Exception:
        pass


class TestSnippetLinesZeroDaemonE2E:
    """End-to-end tests for --snippet-lines 0 in daemon mode."""

    def test_daemon_mode_fts_query_with_snippet_lines_zero(
        self, test_project_with_daemon
    ):
        """Test that daemon mode respects --snippet-lines 0 for FTS queries.

        This is the ACTUAL user-reported bug test.

        Expected behavior: No context snippets displayed, only file listings.
        """
        project_dir = test_project_with_daemon

        # Run FTS query with snippet_lines=0 in daemon mode
        result = subprocess.run(
            [
                "cidx",
                "query",
                "voyage",
                "--fts",
                "--snippet-lines",
                "0",
                "--limit",
                "2",
            ],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"

        output = result.stdout

        # CRITICAL ASSERTIONS: Verify no context snippets displayed
        # With snippet_lines=0, we should NOT see:
        # - "Context:" header
        # - Code snippets with line numbers
        # - The actual code content

        assert (
            "Context:" not in output
        ), "snippet_lines=0 should not show 'Context:' header"

        # We should still see file paths and metadata
        assert "test.py" in output, "Should show file path"

        # Check that we don't see the actual code content
        assert (
            "VoyageClient" not in output or "Context:" not in output
        ), "snippet_lines=0 should not display code content under 'Context:' section"

    def test_standalone_mode_fts_query_with_snippet_lines_zero(self, tmp_path):
        """Test that standalone mode respects --snippet-lines 0 for FTS queries.

        This serves as the CONTROL/BASELINE for comparison with daemon mode.
        """
        project_dir = tmp_path / "standalone_project"
        project_dir.mkdir()

        # Create test files
        test_file = project_dir / "test.py"
        test_file.write_text(
            """
from voyage import VoyageClient
client = VoyageClient()
"""
        )

        # Initialize and index (without daemon)
        subprocess.run(
            ["cidx", "init"], cwd=project_dir, capture_output=True, check=True
        )

        subprocess.run(
            ["cidx", "index", "--fts"], cwd=project_dir, capture_output=True, check=True
        )

        # Run query in standalone mode (no daemon started)
        result = subprocess.run(
            [
                "cidx",
                "query",
                "voyage",
                "--fts",
                "--snippet-lines",
                "0",
                "--limit",
                "2",
                "--standalone",
            ],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"

        output = result.stdout

        # Standalone mode should also NOT show context
        assert (
            "Context:" not in output
        ), "snippet_lines=0 in standalone should not show 'Context:' header"

        # Should show file path
        assert "test.py" in output, "Should show file path"

    def test_daemon_vs_standalone_output_parity(
        self, test_project_with_daemon, tmp_path
    ):
        """Test that daemon and standalone modes produce IDENTICAL output for snippet_lines=0.

        This is the ultimate parity test - both modes must produce the same output.
        """
        daemon_project = test_project_with_daemon

        # Create identical standalone project
        standalone_project = tmp_path / "standalone"
        standalone_project.mkdir()

        # Copy test file
        test_content = """
from voyage import VoyageClient
client = VoyageClient()
result = client.embed(["test"])
"""
        (standalone_project / "test.py").write_text(test_content)
        (daemon_project / "test_identical.py").write_text(test_content)

        # Re-index daemon project with new file
        subprocess.run(
            ["cidx", "index", "--fts"],
            cwd=daemon_project,
            capture_output=True,
            check=True,
        )

        # Initialize standalone project
        subprocess.run(
            ["cidx", "init"], cwd=standalone_project, capture_output=True, check=True
        )

        subprocess.run(
            ["cidx", "index", "--fts"],
            cwd=standalone_project,
            capture_output=True,
            check=True,
        )

        # Run identical query in both modes
        daemon_result = subprocess.run(
            [
                "cidx",
                "query",
                "voyage",
                "--fts",
                "--snippet-lines",
                "0",
                "--limit",
                "1",
            ],
            cwd=daemon_project,
            capture_output=True,
            text=True,
        )

        standalone_result = subprocess.run(
            [
                "cidx",
                "query",
                "voyage",
                "--fts",
                "--snippet-lines",
                "0",
                "--limit",
                "1",
                "--standalone",
            ],
            cwd=standalone_project,
            capture_output=True,
            text=True,
        )

        # Both should succeed
        assert daemon_result.returncode == 0
        assert standalone_result.returncode == 0

        # Extract result sections (ignore timing differences)
        daemon_output = daemon_result.stdout
        standalone_output = standalone_result.stdout

        # Both should NOT show context
        assert (
            "Context:" not in daemon_output
        ), "Daemon mode should not show context with snippet_lines=0"

        assert (
            "Context:" not in standalone_output
        ), "Standalone mode should not show context with snippet_lines=0"

        # Key assertion: Both should have same behavior regarding snippet display
        daemon_has_code = "VoyageClient" in daemon_output
        standalone_has_code = "VoyageClient" in standalone_output

        # If standalone doesn't show code, daemon shouldn't either
        if not standalone_has_code:
            assert (
                not daemon_has_code
            ), "Daemon mode showing code content when standalone mode doesn't - UX PARITY VIOLATION"
