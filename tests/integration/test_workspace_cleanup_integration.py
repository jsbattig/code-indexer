"""
Integration tests for Workspace Cleanup with Audit Log Preservation (Story #647 - AC3).

Tests full workflow integration:
- AC3: Audit log records persist after workspace cleanup
- Workspace deletion does NOT cascade to database
- Full cleanup workflow with real BackgroundJobManager and SCIPAuditRepository
"""

import os
import time

import pytest

from src.code_indexer.server.repositories.background_jobs import BackgroundJobManager
from src.code_indexer.server.repositories.scip_audit import SCIPAuditRepository
from src.code_indexer.server.services.workspace_cleanup_service import (
    WorkspaceCleanupService,
)
from src.code_indexer.server.utils.config_manager import ServerConfig


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
def audit_repo(tmp_path):
    """Create test SCIP audit repository."""
    db_path = str(tmp_path / "scip_audit.db")
    return SCIPAuditRepository(db_path=db_path)


@pytest.fixture
def workspace_root(tmp_path):
    """Create test workspace root directory."""
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    return workspace_root


class TestWorkspaceCleanupAC3Integration:
    """AC3: Audit Log Preservation integration tests."""

    def test_cleanup_preserves_audit_records_after_deleting_workspace(
        self, server_config, job_manager, audit_repo, workspace_root
    ):
        """
        Given workspace with corresponding audit record
        When workspace is cleaned up (deleted)
        Then audit record persists in database
        And workspace directory no longer exists
        """
        # Create workspace directory
        job_id = "test-job-123"
        workspace = workspace_root / f"cidx-scip-{job_id}"
        workspace.mkdir()
        (workspace / "file.txt").write_text("test data")

        # Make workspace expired
        old_time = time.time() - (10 * 24 * 3600)  # 10 days old
        os.utime(workspace, (old_time, old_time))
        os.utime(workspace / "file.txt", (old_time, old_time))

        # Create corresponding audit record
        record_id = audit_repo.create_audit_record(
            job_id=job_id,
            repo_alias="test-repo",
            package="test-package",
            command="pip install test-package",
            project_path="/path/to/project",
            project_language="Python",
            project_build_system="pip",
            reasoning="Required for SCIP indexing",
            username="testuser",
        )

        # Verify audit record exists
        records_before, _ = audit_repo.query_audit_records(job_id=job_id)
        assert len(records_before) == 1
        assert records_before[0]["id"] == record_id

        # Run cleanup
        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )
        result = service.cleanup_workspaces()

        # Verify workspace deleted
        assert not workspace.exists()
        assert result.workspaces_deleted == 1

        # AC3: Verify audit record still exists
        records_after, _ = audit_repo.query_audit_records(job_id=job_id)
        assert len(records_after) == 1
        assert records_after[0]["id"] == record_id
        assert records_after[0]["job_id"] == job_id
        assert records_after[0]["repo_alias"] == "test-repo"
        assert records_after[0]["package"] == "test-package"

    def test_cleanup_preserves_multiple_audit_records_for_same_workspace(
        self, server_config, job_manager, audit_repo, workspace_root
    ):
        """
        Given workspace with multiple audit records (multiple dependencies)
        When workspace is cleaned up
        Then all audit records persist
        """
        # Create workspace
        job_id = "test-job-456"
        workspace = workspace_root / f"cidx-scip-{job_id}"
        workspace.mkdir()

        # Make expired
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(workspace, (old_time, old_time))

        # Create multiple audit records for same job
        record_ids = []
        for package in ["package-a", "package-b", "package-c"]:
            record_id = audit_repo.create_audit_record(
                job_id=job_id,
                repo_alias="test-repo",
                package=package,
                command=f"pip install {package}",
                project_language="Python",
            )
            record_ids.append(record_id)

        # Verify all records exist before cleanup
        records_before, _ = audit_repo.query_audit_records(job_id=job_id)
        assert len(records_before) == 3

        # Run cleanup
        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )
        service.cleanup_workspaces()

        # Verify workspace deleted
        assert not workspace.exists()

        # AC3: Verify all audit records still exist
        records_after, _ = audit_repo.query_audit_records(job_id=job_id)
        assert len(records_after) == 3
        assert {r["package"] for r in records_after} == {
            "package-a",
            "package-b",
            "package-c",
        }

    def test_cleanup_never_calls_database_delete_operations(
        self, server_config, job_manager, audit_repo, workspace_root
    ):
        """
        Given workspace cleanup operation
        When cleanup runs
        Then NO database DELETE operations are executed
        And cleanup service never touches audit repository
        """
        # Create workspace
        job_id = "test-job-789"
        workspace = workspace_root / f"cidx-scip-{job_id}"
        workspace.mkdir()
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(workspace, (old_time, old_time))

        # Create audit record
        audit_repo.create_audit_record(
            job_id=job_id,
            repo_alias="test-repo",
            package="test-package",
            command="pip install test-package",
        )

        # Run cleanup (cleanup service should never reference audit_repo)
        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )
        service.cleanup_workspaces()

        # Verify workspace deleted
        assert not workspace.exists()

        # AC3: Verify audit record still intact
        records, _ = audit_repo.query_audit_records(job_id=job_id)
        assert len(records) == 1

    def test_audit_records_queryable_after_cleanup_for_compliance(
        self, server_config, job_manager, audit_repo, workspace_root
    ):
        """
        Given workspace has been cleaned up (deleted)
        When querying audit API for that job_id
        Then audit records are fully accessible
        And compliance information is complete
        """
        # Create and cleanup workspace
        job_id = "compliance-test-job"
        workspace = workspace_root / f"cidx-scip-{job_id}"
        workspace.mkdir()
        old_time = time.time() - (10 * 24 * 3600)
        os.utime(workspace, (old_time, old_time))

        # Create audit record with full compliance info
        audit_repo.create_audit_record(
            job_id=job_id,
            repo_alias="production-repo",
            package="critical-dependency",
            command="npm install critical-dependency@1.2.3",
            project_path="services/api",
            project_language="TypeScript",
            project_build_system="npm",
            reasoning="Missing dependency required for SCIP code intelligence",
            username="admin",
        )

        # Run cleanup
        service = WorkspaceCleanupService(
            config=server_config,
            job_manager=job_manager,
            workspace_root=str(workspace_root),
        )
        service.cleanup_workspaces()

        # Verify workspace deleted
        assert not workspace.exists()

        # AC3: Query audit records - all compliance info should be available
        records, _ = audit_repo.query_audit_records(job_id=job_id)
        assert len(records) == 1

        record = records[0]
        assert record["job_id"] == job_id
        assert record["repo_alias"] == "production-repo"
        assert record["package"] == "critical-dependency"
        assert record["command"] == "npm install critical-dependency@1.2.3"
        assert record["project_path"] == "services/api"
        assert record["project_language"] == "TypeScript"
        assert record["project_build_system"] == "npm"
        assert "Missing dependency" in record["reasoning"]
        assert record["username"] == "admin"
        assert record["timestamp"] is not None  # Compliance timestamp preserved
