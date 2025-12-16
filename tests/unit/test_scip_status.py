"""Unit tests for SCIP status tracking."""

from datetime import datetime
from code_indexer.scip.status import (
    StatusTracker,
    ProjectStatus,
    GenerationStatus,
    OverallStatus,
)


class TestStatusTracker:
    """Test SCIP status tracking and persistence."""

    def test_create_status_file(self, tmp_path):
        """Test creating initial status file."""
        scip_dir = tmp_path / ".code-indexer" / "scip"
        tracker = StatusTracker(scip_dir)

        status = GenerationStatus(
            overall_status=OverallStatus.PENDING,
            total_projects=0,
            successful_projects=0,
            failed_projects=0,
            projects={},
        )

        tracker.save(status)

        status_file = scip_dir / "status.json"
        assert status_file.exists()

    def test_save_and_load_status(self, tmp_path):
        """Test round-trip save and load."""
        scip_dir = tmp_path / ".code-indexer" / "scip"
        tracker = StatusTracker(scip_dir)

        status = GenerationStatus(
            overall_status=OverallStatus.SUCCESS,
            total_projects=2,
            successful_projects=2,
            failed_projects=0,
            projects={
                "backend": ProjectStatus(
                    status=OverallStatus.SUCCESS,
                    language="java",
                    build_system="maven",
                    duration_seconds=2.5,
                    output_file="backend/index.scip",
                    timestamp=datetime.now().isoformat(),
                ),
                "frontend": ProjectStatus(
                    status=OverallStatus.SUCCESS,
                    language="typescript",
                    build_system="npm",
                    duration_seconds=1.8,
                    output_file="frontend/index.scip",
                    timestamp=datetime.now().isoformat(),
                ),
            },
        )

        tracker.save(status)
        loaded = tracker.load()

        assert loaded.overall_status == OverallStatus.SUCCESS
        assert loaded.total_projects == 2
        assert loaded.successful_projects == 2
        assert "backend" in loaded.projects
        assert "frontend" in loaded.projects

    def test_limbo_state_status(self, tmp_path):
        """Test limbo state (partial success)."""
        scip_dir = tmp_path / ".code-indexer" / "scip"
        tracker = StatusTracker(scip_dir)

        status = GenerationStatus(
            overall_status=OverallStatus.LIMBO,
            total_projects=3,
            successful_projects=2,
            failed_projects=1,
            projects={
                "backend": ProjectStatus(
                    status=OverallStatus.SUCCESS,
                    language="java",
                    build_system="maven",
                    duration_seconds=2.5,
                    output_file="backend/index.scip",
                    timestamp=datetime.now().isoformat(),
                ),
                "frontend": ProjectStatus(
                    status=OverallStatus.SUCCESS,
                    language="typescript",
                    build_system="npm",
                    duration_seconds=1.8,
                    output_file="frontend/index.scip",
                    timestamp=datetime.now().isoformat(),
                ),
                "python-lib": ProjectStatus(
                    status=OverallStatus.FAILED,
                    language="python",
                    build_system="poetry",
                    duration_seconds=0.5,
                    error_message="Error: pip install failed",
                    exit_code=1,
                    timestamp=datetime.now().isoformat(),
                ),
            },
        )

        tracker.save(status)
        loaded = tracker.load()

        assert loaded.overall_status == OverallStatus.LIMBO
        assert loaded.is_limbo()
        assert loaded.successful_projects == 2
        assert loaded.failed_projects == 1

        # Verify failed project has error details
        failed_project = loaded.projects["python-lib"]
        assert failed_project.status == OverallStatus.FAILED
        assert failed_project.error_message is not None
        assert "pip install failed" in failed_project.error_message

    def test_load_nonexistent_status(self, tmp_path):
        """Test loading when no status file exists."""
        scip_dir = tmp_path / ".code-indexer" / "scip"
        tracker = StatusTracker(scip_dir)

        status = tracker.load()

        assert status.overall_status == OverallStatus.PENDING
        assert status.total_projects == 0

    def test_update_project_status(self, tmp_path):
        """Test updating individual project status."""
        scip_dir = tmp_path / ".code-indexer" / "scip"
        tracker = StatusTracker(scip_dir)

        # Initial status
        status = GenerationStatus(
            overall_status=OverallStatus.PENDING,
            total_projects=1,
            successful_projects=0,
            failed_projects=0,
            projects={
                "backend": ProjectStatus(
                    status=OverallStatus.PENDING,
                    language="java",
                    build_system="maven",
                    timestamp=datetime.now().isoformat(),
                )
            },
        )
        tracker.save(status)

        # Update to success
        status.projects["backend"].status = OverallStatus.SUCCESS
        status.projects["backend"].duration_seconds = 3.2
        status.projects["backend"].output_file = "backend/index.scip"
        status.successful_projects = 1
        status.overall_status = OverallStatus.SUCCESS

        tracker.save(status)
        loaded = tracker.load()

        assert loaded.projects["backend"].status == OverallStatus.SUCCESS
        assert loaded.projects["backend"].duration_seconds == 3.2
