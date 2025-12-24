"""E2E tests for SCIP CLI commands."""

import pytest
import subprocess
import json


@pytest.fixture
def mock_java_repo(tmp_path):
    """Create a mock Java repository with cidx initialized."""
    (tmp_path / "pom.xml").write_text("<project></project>")
    (tmp_path / "src" / "main" / "java").mkdir(parents=True)
    (tmp_path / "src" / "main" / "java" / "Main.java").write_text(
        "public class Main { public static void main(String[] args) {} }"
    )
    # Initialize cidx
    subprocess.run(["cidx", "init"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


@pytest.fixture
def mock_multiproject_repo(tmp_path):
    """Create a mock repository with multiple projects."""
    # Backend (Java/Maven)
    (tmp_path / "backend" / "pom.xml").parent.mkdir(parents=True)
    (tmp_path / "backend" / "pom.xml").write_text("<project></project>")

    # Frontend (TypeScript/npm)
    (tmp_path / "frontend" / "package.json").parent.mkdir(parents=True)
    (tmp_path / "frontend" / "package.json").write_text('{"name": "test"}')

    # Initialize cidx
    subprocess.run(["cidx", "init"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


class TestSCIPCLI:
    """Test SCIP CLI commands."""

    def test_scip_generate_command_exists(self):
        """Test that cidx scip generate command exists."""
        result = subprocess.run(
            ["cidx", "scip", "generate", "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Generate SCIP indexes" in result.stdout

    def test_scip_status_command_exists(self):
        """Test that cidx scip status command exists."""
        result = subprocess.run(
            ["cidx", "scip", "status", "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Show SCIP generation status" in result.stdout

    def test_scip_generate_with_mock_repo(self, mock_java_repo):
        """Test scip generate in a mock repository."""
        # Change to mock repo directory
        result = subprocess.run(
            ["cidx", "scip", "generate"],
            cwd=str(mock_java_repo),
            capture_output=True,
            text=True,
        )

        # Should complete (may fail on actual indexing due to missing tools)
        # but command should execute without crash
        assert result.returncode in [0, 1]  # 0=success, 1=partial/fail

        # Status file should be created
        status_file = mock_java_repo / ".code-indexer" / "scip" / "status.json"
        assert status_file.exists()

    def test_scip_status_before_generation(self, mock_java_repo):
        """Test status command before any generation."""
        result = subprocess.run(
            ["cidx", "scip", "status"],
            cwd=str(mock_java_repo),
            capture_output=True,
            text=True,
        )

        # Should succeed even if no status exists
        assert result.returncode == 0
        assert "PENDING" in result.stdout

    def test_scip_status_after_generation(self, mock_java_repo):
        """Test status command after generation."""
        # Run generation first
        subprocess.run(
            ["cidx", "scip", "generate"], cwd=str(mock_java_repo), capture_output=True
        )

        # Check status
        result = subprocess.run(
            ["cidx", "scip", "status"],
            cwd=str(mock_java_repo),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should show some status information
        assert "project" in result.stdout.lower() or "status" in result.stdout.lower()

    def test_scip_generate_with_multiproject_repo(self, mock_multiproject_repo):
        """Test generation with multiple projects."""
        result = subprocess.run(
            ["cidx", "scip", "generate"],
            cwd=str(mock_multiproject_repo),
            capture_output=True,
            text=True,
        )

        # Should discover both projects
        assert result.returncode in [0, 1]

        # Check that status.json was created
        status_file = mock_multiproject_repo / ".code-indexer" / "scip" / "status.json"
        assert status_file.exists()

        # Verify status contains both projects
        with open(status_file) as f:
            status = json.load(f)
            assert status["total_projects"] == 2
            assert "backend" in status["projects"] or "frontend" in status["projects"]


def test_scip_rebuild_after_partial_failure(tmp_path, monkeypatch):
    """Test end-to-end rebuild workflow after partial generation failure."""
    monkeypatch.chdir(tmp_path)

    # Create a simple Python project
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "backend"
version = "0.1.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
"""
    )
    (tmp_path / "backend" / "main.py").write_text("def hello(): pass")

    # Initialize .code-indexer
    init_result = subprocess.run(
        ["cidx", "init"], cwd=tmp_path, capture_output=True, text=True
    )
    assert init_result.returncode == 0

    # First, manually create a status with partial failure
    scip_dir = tmp_path / ".code-indexer" / "scip"
    scip_dir.mkdir(parents=True, exist_ok=True)

    status_data = {
        "overall_status": "limbo",
        "total_projects": 2,
        "successful_projects": 1,
        "failed_projects": 1,
        "projects": {
            "backend": {
                "status": "failed",
                "language": "python",
                "build_system": "poetry",
                "timestamp": "2025-01-01T00:00:00",
                "error_message": "scip-python not found",
                "exit_code": 127,
            },
            "frontend": {
                "status": "success",
                "language": "typescript",
                "build_system": "npm",
                "timestamp": "2025-01-01T00:00:00",
                "duration_seconds": 2.0,
                "output_file": str(scip_dir / "frontend" / "index.scip"),
            },
        },
    }

    import json

    (scip_dir / "status.json").write_text(json.dumps(status_data, indent=2))

    # Test 1: Rebuild specific failed project (will still fail without scip-python)
    rebuild_result = subprocess.run(
        ["cidx", "scip", "rebuild", "backend"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    # Expect failure since scip-python not installed
    assert rebuild_result.returncode != 0
    assert "backend" in rebuild_result.stdout or "backend" in rebuild_result.stderr

    # Test 2: Try to rebuild unknown project
    rebuild_result = subprocess.run(
        ["cidx", "scip", "rebuild", "unknown"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert rebuild_result.returncode != 0
    assert (
        "Unknown project" in rebuild_result.stdout
        or "Unknown project" in rebuild_result.stderr
    )

    # Test 3: Rebuild --failed
    rebuild_result = subprocess.run(
        ["cidx", "scip", "rebuild", "--failed"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    # Will fail since scip-python not installed
    assert "backend" in rebuild_result.stdout or "backend" in rebuild_result.stderr


def test_scip_rebuild_validation_errors(tmp_path, monkeypatch):
    """Test rebuild command validation and error handling."""
    monkeypatch.chdir(tmp_path)

    # Initialize .code-indexer
    subprocess.run(["cidx", "init"], cwd=tmp_path, capture_output=True)

    # Test: No arguments and no --failed flag
    result = subprocess.run(
        ["cidx", "scip", "rebuild"], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "Must specify project paths or use --failed" in result.stdout

    # Test: Both arguments and --failed flag
    result = subprocess.run(
        ["cidx", "scip", "rebuild", "backend", "--failed"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Cannot use both" in result.stdout

    # Test: No status file exists
    result = subprocess.run(
        ["cidx", "scip", "rebuild", "backend"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert (
        "No SCIP generation status found" in result.stdout
        or "scip generate" in result.stdout
    )
