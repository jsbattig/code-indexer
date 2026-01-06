"""
Unit tests for WorkspaceCleanupService (Story #647 - AC2, AC6).

Tests automatic workspace cleanup:
- AC2: Periodic cleanup job (workspace scanning, deletion, age checking)
- AC6: Safety checks (active jobs, recent modifications, error handling)

TDD Approach: Tests written FIRST, service implemented to pass tests.
"""

import os
import shutil
import time
from datetime import datetime

import pytest

from code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
    JobStatus,
)
from code_indexer.server.utils.config_manager import ServerConfig


# Import will fail initially - that's expected in TDD
try:
    from code_indexer.server.services.workspace_cleanup_service import (
        WorkspaceCleanupService,
        CleanupResult,
    )
except ImportError:
    # Expected failure - service doesn't exist yet
    WorkspaceCleanupService = None
    CleanupResult = None


@pytest.fixture
def server_config(tmp_path):
    """Create test server configuration."""
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    config = ServerConfig(server_dir=str(server_dir))
    config.scip_workspace_retention_days = 7
    return config


@pytest.fixture
def job_manager(tmp_path):
    """Create test background job manager."""
    storage_path = str(tmp_path / "jobs.json")
    return BackgroundJobManager(storage_path=storage_path)


@pytest.fixture
def workspace_root(tmp_path):
    """Create test workspace root directory."""
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    return workspace_root


class TestWorkspaceCleanupServiceAC2:
    """AC2: Periodic Cleanup Job tests."""

    def test_cleanup_service_initializes_with_config(self, server_config, job_manager):
        """
        Given a ServerConfig and BackgroundJobManager
        When WorkspaceCleanupService is initialized
        Then it should store retention_days from config
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        service = WorkspaceCleanupService(config=server_config, job_manager=job_manager)

        assert service.retention_days == 7
        assert service.job_manager is job_manager

    def test_scan_workspaces_finds_all_workspace_directories(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given multiple workspace directories exist
        When scan_workspaces is called
        Then it should return list of all cidx-scip-* directories
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create workspace directories
        ws1 = workspace_root / "cidx-scip-job1"
        ws2 = workspace_root / "cidx-scip-job2"
        ws3 = workspace_root / "cidx-scip-job3"
        other = workspace_root / "other-directory"

        for ws in [ws1, ws2, ws3, other]:
            ws.mkdir()

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        workspaces = service.scan_workspaces()

        # Should find only cidx-scip-* directories
        assert len(workspaces) == 3
        workspace_names = [ws.name for ws in workspaces]
        assert "cidx-scip-job1" in workspace_names
        assert "cidx-scip-job2" in workspace_names
        assert "cidx-scip-job3" in workspace_names
        assert "other-directory" not in workspace_names

    def test_is_workspace_expired_checks_creation_time(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given workspace directories with different ages
        When checking if workspace is expired
        Then workspaces older than retention period should be marked expired
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create old workspace (10 days old)
        old_ws = workspace_root / "cidx-scip-old"
        old_ws.mkdir()
        old_time = time.time() - (10 * 24 * 3600)  # 10 days ago
        os.utime(old_ws, (old_time, old_time))

        # Create recent workspace (3 days old)
        recent_ws = workspace_root / "cidx-scip-recent"
        recent_ws.mkdir()
        recent_time = time.time() - (3 * 24 * 3600)  # 3 days ago
        os.utime(recent_ws, (recent_time, recent_time))

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        # 10-day old workspace should be expired (retention = 7 days)
        assert service.is_workspace_expired(old_ws) is True

        # 3-day old workspace should not be expired
        assert service.is_workspace_expired(recent_ws) is False

    def test_cleanup_workspaces_deletes_expired_workspaces(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given expired and non-expired workspaces exist
        When cleanup_workspaces is called
        Then only expired workspaces should be deleted
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create expired workspace (10 days old)
        expired_ws = workspace_root / "cidx-scip-expired"
        expired_ws.mkdir()
        expired_file = expired_ws / "file.txt"
        expired_file.write_text("test")
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(expired_ws, (old_time, old_time))
        os.utime(expired_file, (old_time, old_time))  # Set file time too

        # Create non-expired workspace (3 days old)
        kept_ws = workspace_root / "cidx-scip-kept"
        kept_ws.mkdir()
        kept_file = kept_ws / "file.txt"
        kept_file.write_text("test")
        recent_time = time.time() - (3 * 24 * 3600)
        os.utime(kept_ws, (recent_time, recent_time))
        os.utime(kept_file, (recent_time, recent_time))  # Set file time too

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        result = service.cleanup_workspaces()

        # Verify expired workspace deleted
        assert not expired_ws.exists()

        # Verify non-expired workspace kept
        assert kept_ws.exists()

        # Verify result summary
        assert result.workspaces_scanned == 2
        assert result.workspaces_deleted == 1
        assert result.workspaces_preserved == 1

    def test_cleanup_workspaces_calculates_space_reclaimed(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given workspace with known size
        When workspace is deleted
        Then space_reclaimed_bytes should reflect actual space freed
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create workspace with files of known size
        ws = workspace_root / "cidx-scip-sized"
        ws.mkdir()
        file1 = ws / "file1.txt"
        file2 = ws / "file2.txt"
        file1.write_text("x" * 1000)  # 1000 bytes
        file2.write_text("y" * 2000)  # 2000 bytes

        # Make it expired
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(ws, (old_time, old_time))
        os.utime(file1, (old_time, old_time))  # Set file times too
        os.utime(file2, (old_time, old_time))

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        result = service.cleanup_workspaces()

        # Should report approximate space reclaimed (at least the file sizes)
        assert result.space_reclaimed_bytes >= 3000

    def test_cleanup_workspaces_logs_operations(
        self, server_config, job_manager, workspace_root, caplog
    ):
        """
        Given workspaces to clean up
        When cleanup runs
        Then operations should be logged with summary
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create expired workspace
        ws = workspace_root / "cidx-scip-logged"
        ws.mkdir()
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(ws, (old_time, old_time))

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        with caplog.at_level("INFO"):
            service.cleanup_workspaces()

        # Should log cleanup summary
        assert "Workspace cleanup completed" in caplog.text
        assert "deleted: 1" in caplog.text or "deleted=1" in caplog.text


class TestWorkspaceCleanupServiceAC6:
    """AC6: Safe Cleanup Behavior tests."""

    def test_cleanup_skips_workspaces_for_active_jobs(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given workspace for job in RESOLVING_PREREQUISITES state
        When cleanup runs
        Then workspace should be skipped even if expired
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create expired workspace
        ws = workspace_root / "cidx-scip-job123"
        ws.mkdir()
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(ws, (old_time, old_time))

        # Submit job in RESOLVING_PREREQUISITES state
        def dummy_func():
            return {}

        job_id = job_manager.submit_job(
            operation_type="test_operation",
            func=dummy_func,
            submitter_username="testuser",
            repo_alias="test-repo",
        )

        # Manually set job to RESOLVING_PREREQUISITES (simulating active resolution)
        with job_manager._lock:
            job_manager.jobs[job_id].status = JobStatus.RESOLVING_PREREQUISITES
            job_manager.jobs[job_id].job_id = "job123"  # Match workspace name

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        result = service.cleanup_workspaces()

        # Workspace should be preserved
        assert ws.exists()
        assert result.workspaces_deleted == 0
        assert len(result.skipped) == 1
        assert result.skipped[0]["reason"] == "active_job"

    def test_cleanup_skips_recently_modified_workspaces(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given workspace modified in last 24 hours
        When cleanup runs
        Then workspace should be skipped regardless of creation date
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create old workspace but recently modified
        ws = workspace_root / "cidx-scip-recent-mod"
        ws.mkdir()

        # Set old creation time
        old_create = time.time() - (10 * 24 * 3600)
        os.utime(ws, (old_create, old_create))

        # Modify recently (touch a file)
        (ws / "recent.txt").write_text("modified")

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        result = service.cleanup_workspaces()

        # Should be skipped due to recent modification
        assert ws.exists()
        assert len(result.skipped) == 1
        assert "recent_modification" in result.skipped[0]["reason"]

    def test_cleanup_handles_deletion_errors_gracefully(
        self, server_config, job_manager, workspace_root, monkeypatch
    ):
        """
        Given workspace that fails to delete
        When cleanup runs
        Then error should be logged but cleanup continues
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create expired workspaces
        ws1 = workspace_root / "cidx-scip-error"
        ws1.mkdir()
        file1 = ws1 / "file.txt"
        file1.write_text("test")
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(ws1, (old_time, old_time))
        os.utime(file1, (old_time, old_time))

        ws2 = workspace_root / "cidx-scip-success"
        ws2.mkdir()
        file2 = ws2 / "file.txt"
        file2.write_text("test")
        os.utime(ws2, (old_time, old_time))
        os.utime(file2, (old_time, old_time))

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        # Mock shutil.rmtree to fail on first workspace only
        original_rmtree = shutil.rmtree
        call_count = [0]

        def mock_rmtree(path, *args, **kwargs):
            call_count[0] += 1
            if "cidx-scip-error" in str(path):
                raise PermissionError("Simulated deletion error")
            return original_rmtree(path, *args, **kwargs)

        monkeypatch.setattr(shutil, "rmtree", mock_rmtree)

        result = service.cleanup_workspaces()

        # Cleanup should continue despite error
        assert result.workspaces_scanned == 2
        assert len(result.errors) > 0
        assert any("cidx-scip-error" in error for error in result.errors)
        # Second workspace should succeed
        assert not ws2.exists()

    def test_cleanup_result_contains_all_required_fields(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given cleanup operation completes
        When result is returned
        Then it should contain all required fields per AC2
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        result = service.cleanup_workspaces()

        # Verify all required fields exist
        assert hasattr(result, "workspaces_scanned")
        assert hasattr(result, "workspaces_deleted")
        assert hasattr(result, "workspaces_preserved")
        assert hasattr(result, "space_reclaimed_bytes")
        assert hasattr(result, "errors")
        assert hasattr(result, "skipped")
        assert hasattr(result, "duration_seconds")

        # Verify types
        assert isinstance(result.workspaces_scanned, int)
        assert isinstance(result.workspaces_deleted, int)
        assert isinstance(result.workspaces_preserved, int)
        assert isinstance(result.space_reclaimed_bytes, int)
        assert isinstance(result.errors, list)
        assert isinstance(result.skipped, list)
        assert isinstance(result.duration_seconds, float)


class TestWorkspaceCleanupServiceAC5:
    """AC5: Cleanup Status Visibility tests."""

    def test_get_cleanup_status_returns_all_required_fields(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given WorkspaceCleanupService initialized
        When get_cleanup_status is called
        Then it should return status dict with all required fields
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        status = service.get_cleanup_status()

        # Verify all required fields exist
        assert "last_cleanup_time" in status
        assert "workspace_count" in status
        assert "oldest_workspace_age" in status
        assert "total_size_mb" in status

    def test_get_cleanup_status_shows_null_before_first_cleanup(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given cleanup has never run
        When get_cleanup_status is called
        Then last_cleanup_time should be None
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        status = service.get_cleanup_status()

        assert status["last_cleanup_time"] is None

    def test_get_cleanup_status_shows_time_after_cleanup(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given cleanup has been run
        When get_cleanup_status is called
        Then last_cleanup_time should be set with ISO format timestamp
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        # Run cleanup
        service.cleanup_workspaces()

        status = service.get_cleanup_status()

        assert status["last_cleanup_time"] is not None
        # Should be ISO format string
        assert isinstance(status["last_cleanup_time"], str)
        # Verify it can be parsed as datetime
        datetime.fromisoformat(status["last_cleanup_time"].replace("Z", "+00:00"))

    def test_get_cleanup_status_counts_workspaces(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given multiple workspace directories exist
        When get_cleanup_status is called
        Then workspace_count should reflect actual count
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create workspace directories
        ws1 = workspace_root / "cidx-scip-job1"
        ws2 = workspace_root / "cidx-scip-job2"
        ws3 = workspace_root / "cidx-scip-job3"

        for ws in [ws1, ws2, ws3]:
            ws.mkdir()

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        status = service.get_cleanup_status()

        assert status["workspace_count"] == 3

    def test_get_cleanup_status_calculates_oldest_workspace_age(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given workspaces with different ages
        When get_cleanup_status is called
        Then oldest_workspace_age should reflect the oldest workspace in days
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create old workspace (10 days old)
        old_ws = workspace_root / "cidx-scip-old"
        old_ws.mkdir()
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(old_ws, (old_time, old_time))

        # Create recent workspace (3 days old)
        recent_ws = workspace_root / "cidx-scip-recent"
        recent_ws.mkdir()
        recent_time = time.time() - (3 * 24 * 3600)
        os.utime(recent_ws, (recent_time, recent_time))

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        status = service.get_cleanup_status()

        # oldest_workspace_age should be approximately 10 days
        assert status["oldest_workspace_age"] >= 9.0
        assert status["oldest_workspace_age"] <= 11.0

    def test_get_cleanup_status_calculates_total_size(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given workspaces with known total size
        When get_cleanup_status is called
        Then total_size_mb should reflect total workspace size
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        # Create workspaces with files
        ws1 = workspace_root / "cidx-scip-sized1"
        ws1.mkdir()
        file1 = ws1 / "file1.txt"
        file1.write_text("x" * (1024 * 1024))  # 1 MB

        ws2 = workspace_root / "cidx-scip-sized2"
        ws2.mkdir()
        file2 = ws2 / "file2.txt"
        file2.write_text("y" * (2 * 1024 * 1024))  # 2 MB

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        status = service.get_cleanup_status()

        # Should report approximately 3 MB total
        assert status["total_size_mb"] >= 2.5
        assert status["total_size_mb"] <= 3.5

    def test_get_cleanup_status_handles_no_workspaces(
        self, server_config, job_manager, workspace_root
    ):
        """
        Given no workspace directories exist
        When get_cleanup_status is called
        Then status should show zero values gracefully
        """
        if WorkspaceCleanupService is None:
            pytest.skip("WorkspaceCleanupService not implemented yet (TDD red phase)")

        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )

        status = service.get_cleanup_status()

        assert status["workspace_count"] == 0
        assert status["oldest_workspace_age"] is None
        assert status["total_size_mb"] == 0.0
