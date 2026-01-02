"""Unit tests for SCIP CLI glob pattern bug fix.

This test file verifies that the CLI correctly globs for .scip.db files
instead of .scip files after the protobuf-to-SQLite conversion.
"""

import pytest
import subprocess
from pathlib import Path
import shutil


@pytest.fixture
def scip_test_repo(tmp_path):
    """Create a test repository with .scip.db files (no .scip files)."""
    import json

    # Initialize cidx first
    subprocess.run(["cidx", "init"], cwd=str(tmp_path), capture_output=True)

    # Create .code-indexer/scip structure
    code_indexer_dir = tmp_path / ".code-indexer"
    scip_dir = code_indexer_dir / "scip"
    scip_dir.mkdir(parents=True, exist_ok=True)

    # Copy test .scip.db fixture (simulating post-conversion state)
    fixture_src = (
        Path(__file__).parent.parent
        / "scip"
        / "fixtures"
        / "comprehensive_index.scip.db"
    )
    fixture_dst = scip_dir / "index.scip.db"
    shutil.copy(fixture_src, fixture_dst)

    # Create status.json to simulate successful generation
    status_data = {
        "overall_status": "success",
        "total_projects": 1,
        "successful_projects": 1,
        "failed_projects": 0,
        "projects": {
            "test_project": {
                "status": "success",
                "language": "csharp",
                "build_system": "dotnet",
                "timestamp": "2025-01-01T00:00:00",
                "duration_seconds": 1.0,
                "output_file": str(scip_dir / "index.scip.db"),
            }
        },
    }
    (scip_dir / "status.json").write_text(json.dumps(status_data, indent=2))

    # Ensure NO .scip file exists (only .scip.db)
    scip_file = scip_dir / "index.scip"
    assert not scip_file.exists(), "Test setup error: .scip file should not exist"
    assert fixture_dst.exists(), "Test setup error: .scip.db file must exist"

    return tmp_path


class TestSCIPCLIGlobPattern:
    """Test that CLI commands correctly glob for .scip.db files."""

    def test_cli_find_definition_finds_scip_db_files(self, scip_test_repo):
        """Test that definition command globs for .scip.db files."""
        # This test should FAIL before the fix (no .scip files found)
        # and PASS after the fix (finds .scip.db files)
        result = subprocess.run(
            ["cidx", "scip", "definition", "Calculator"],
            cwd=str(scip_test_repo),
            capture_output=True,
            text=True,
        )

        # Before fix: Will fail with "No SCIP indexes found" because glob doesn't find .scip.db files
        # After fix: Should NOT fail with index discovery errors
        assert "No SCIP indexes found" not in result.stdout
        assert "No .scip files found" not in result.stdout
        assert "No .scip files found" not in result.stderr

        # Should execute query successfully (may or may not find the symbol)
        assert result.returncode in [0, 1]  # 0=found, 1=not found is OK

    def test_cli_references_finds_scip_db_files(self, scip_test_repo):
        """Test that references command globs for .scip.db files."""
        result = subprocess.run(
            ["cidx", "scip", "references", "Calculator"],
            cwd=str(scip_test_repo),
            capture_output=True,
            text=True,
        )

        # Should NOT fail with index discovery errors
        assert "No SCIP indexes found" not in result.stdout
        assert "No .scip files found" not in result.stdout
        assert "No .scip files found" not in result.stderr
        assert result.returncode in [0, 1]

    def test_cli_dependencies_finds_scip_db_files(self, scip_test_repo):
        """Test that dependencies command globs for .scip.db files."""
        result = subprocess.run(
            ["cidx", "scip", "dependencies", "Calculator"],
            cwd=str(scip_test_repo),
            capture_output=True,
            text=True,
        )

        # Should NOT fail with index discovery errors
        assert "No SCIP indexes found" not in result.stdout
        assert "No .scip files found" not in result.stdout
        assert "No .scip files found" not in result.stderr
        assert result.returncode in [0, 1]

    def test_cli_dependents_finds_scip_db_files(self, scip_test_repo):
        """Test that dependents command globs for .scip.db files."""
        result = subprocess.run(
            ["cidx", "scip", "dependents", "Calculator"],
            cwd=str(scip_test_repo),
            capture_output=True,
            text=True,
        )

        # Should NOT fail with index discovery errors
        assert "No SCIP indexes found" not in result.stdout
        assert "No .scip files found" not in result.stdout
        assert "No .scip files found" not in result.stderr
        assert result.returncode in [0, 1]

    def test_cli_trace_call_chain_finds_scip_db_files(self, scip_test_repo):
        """Test that callchain command globs for .scip.db files."""
        result = subprocess.run(
            ["cidx", "scip", "callchain", "Calculator", "Add"],
            cwd=str(scip_test_repo),
            capture_output=True,
            text=True,
        )

        # Should NOT fail with index discovery errors
        assert "No SCIP indexes found" not in result.stdout
        assert "No SCIP files found" not in result.stdout
        assert "No .scip files found" not in result.stdout
        assert "No .scip files found" not in result.stderr
        assert result.returncode in [0, 1]
