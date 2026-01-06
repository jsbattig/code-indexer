"""
Integration tests for admin API endpoints for SCIP audit logs.

Tests:
- GET /api/admin/scip-pr-history - Query PR creation audit logs
- GET /api/admin/scip-git-cleanup-history - Query git cleanup audit logs
- Authentication requirements
- Filtering and pagination

Story #659: Git State Management for SCIP Self-Healing with PR Workflow
Priority 6: Admin API Endpoints
"""

import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


class TestAdminSCIPAuditAPI:
    """Integration tests for SCIP audit log admin endpoints."""

    @pytest.fixture
    def test_client(self):
        """Create FastAPI test client."""
        from code_indexer.server.app import create_app

        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_admin_user(self, test_client):
        """Create mock admin user and override FastAPI dependency."""
        from code_indexer.server.auth.dependencies import get_current_admin_user

        mock_admin = Mock()
        mock_admin.username = "admin"
        mock_admin.role = "admin"
        mock_admin.to_dict.return_value = {
            "username": "admin",
            "role": "admin",
        }

        # Override the dependency so endpoints return our mock admin
        test_client.app.dependency_overrides[get_current_admin_user] = (
            lambda: mock_admin
        )

        yield mock_admin

        # Cleanup - remove override after test
        test_client.app.dependency_overrides.clear()

    def test_get_pr_history_returns_audit_logs(
        self, test_client, mock_admin_user, tmp_path
    ):
        """Test GET /api/admin/scip-pr-history returns PR creation audit logs."""
        # ARRANGE - Create mock audit logs
        audit_log_file = tmp_path / "pr_audit.log"

        # Write test audit log entries
        test_entries = [
            {
                "event_type": "pr_creation_success",
                "job_id": "job-123",
                "repo_alias": "test-repo",
                "branch_name": "scip-fix-branch",
                "pr_url": "https://github.com/test/repo/pull/1",
                "commit_hash": "abc123",
                "files_modified": ["file1.py", "file2.py"],
                "timestamp": "2026-01-01T12:00:00Z",
            },
            {
                "event_type": "pr_creation_failure",
                "job_id": "job-456",
                "repo_alias": "test-repo",
                "branch_name": "scip-fix-branch2",
                "reason": "git push failed",
                "timestamp": "2026-01-01T13:00:00Z",
            },
        ]

        for entry in test_entries:
            audit_log_file.write_text(
                audit_log_file.read_text() + "PR_CREATION " + json.dumps(entry) + "\n"
                if audit_log_file.exists()
                else "PR_CREATION " + json.dumps(entry) + "\n"
            )

        # Mock audit logger to use test file
        with patch(
            "code_indexer.server.auth.audit_logger.PasswordChangeAuditLogger.get_pr_logs"
        ) as mock_get_logs:
            mock_get_logs.return_value = test_entries

            # ACT - No auth header needed, dependency override handles it
            response = test_client.get("/api/admin/scip-pr-history")

            # ASSERT
            assert response.status_code == 200
            data = response.json()

            assert "logs" in data
            assert "total" in data
            assert data["total"] == 2
            assert len(data["logs"]) == 2

            # Verify first log entry structure
            first_log = data["logs"][0]
            assert first_log["event_type"] == "pr_creation_success"
            assert first_log["job_id"] == "job-123"
            assert first_log["repo_alias"] == "test-repo"
            assert first_log["pr_url"] == "https://github.com/test/repo/pull/1"

    def test_get_pr_history_filters_by_repo(self, test_client, mock_admin_user):
        """Test GET /api/admin/scip-pr-history filters by repo_alias."""
        # ARRANGE
        test_entries = [
            {
                "event_type": "pr_creation_success",
                "job_id": "job-1",
                "repo_alias": "repo-a",
                "timestamp": "2026-01-01T12:00:00Z",
            },
            {
                "event_type": "pr_creation_success",
                "job_id": "job-2",
                "repo_alias": "repo-b",
                "timestamp": "2026-01-01T13:00:00Z",
            },
        ]

        with patch(
            "code_indexer.server.auth.audit_logger.PasswordChangeAuditLogger.get_pr_logs"
        ) as mock_get_logs:
            # Return filtered results
            mock_get_logs.return_value = [test_entries[0]]

            # ACT
            response = test_client.get("/api/admin/scip-pr-history?repo_alias=repo-a")

            # ASSERT
            assert response.status_code == 200
            data = response.json()

            assert data["total"] == 1
            assert data["logs"][0]["repo_alias"] == "repo-a"

            # Verify filter was passed to audit logger
            mock_get_logs.assert_called_once_with(
                repo_alias="repo-a", limit=100, offset=0
            )

    def test_get_pr_history_requires_admin_auth(self, test_client):
        """Test GET /api/admin/scip-pr-history requires admin authentication."""
        # ACT - No token
        response = test_client.get("/api/admin/scip-pr-history")

        # ASSERT
        assert response.status_code == 401

        # ACT - Invalid token
        response = test_client.get(
            "/api/admin/scip-pr-history",
            headers={"Authorization": "Bearer invalid_token"},
        )

        # ASSERT
        assert response.status_code in [401, 403]

    def test_get_cleanup_history_returns_audit_logs(
        self, test_client, mock_admin_user, tmp_path
    ):
        """Test GET /api/admin/scip-git-cleanup-history returns cleanup audit logs."""
        # ARRANGE
        test_entries = [
            {
                "event_type": "git_cleanup",
                "repo_path": "/path/to/repo",
                "files_cleared": ["file1.py", "file2.py"],
                "timestamp": "2026-01-01T14:00:00Z",
            },
            {
                "event_type": "git_cleanup",
                "repo_path": "/path/to/another",
                "files_cleared": ["file3.py"],
                "timestamp": "2026-01-01T15:00:00Z",
            },
        ]

        with patch(
            "code_indexer.server.auth.audit_logger.PasswordChangeAuditLogger.get_cleanup_logs"
        ) as mock_get_logs:
            mock_get_logs.return_value = test_entries

            # ACT
            response = test_client.get("/api/admin/scip-git-cleanup-history")

            # ASSERT
            assert response.status_code == 200
            data = response.json()

            assert "logs" in data
            assert "total" in data
            assert data["total"] == 2
            assert len(data["logs"]) == 2

            # Verify structure
            first_log = data["logs"][0]
            assert first_log["event_type"] == "git_cleanup"
            assert first_log["repo_path"] == "/path/to/repo"
            assert len(first_log["files_cleared"]) == 2

    def test_get_cleanup_history_filters_by_repo_path(
        self, test_client, mock_admin_user
    ):
        """Test GET /api/admin/scip-git-cleanup-history filters by repo_path."""
        # ARRANGE
        test_entries = [
            {
                "event_type": "git_cleanup",
                "repo_path": "/path/to/repo",
                "files_cleared": ["file1.py"],
                "timestamp": "2026-01-01T14:00:00Z",
            }
        ]

        with patch(
            "code_indexer.server.auth.audit_logger.PasswordChangeAuditLogger.get_cleanup_logs"
        ) as mock_get_logs:
            mock_get_logs.return_value = test_entries

            # ACT
            response = test_client.get(
                "/api/admin/scip-git-cleanup-history?repo_path=/path/to/repo"
            )

            # ASSERT
            assert response.status_code == 200
            data = response.json()

            assert data["total"] == 1
            assert data["logs"][0]["repo_path"] == "/path/to/repo"

            # Verify filter was passed
            mock_get_logs.assert_called_once_with(
                repo_path="/path/to/repo", limit=100, offset=0
            )

    def test_get_cleanup_history_requires_admin_auth(self, test_client):
        """Test GET /api/admin/scip-git-cleanup-history requires admin auth."""
        # ACT - No token
        response = test_client.get("/api/admin/scip-git-cleanup-history")

        # ASSERT
        assert response.status_code == 401

    def test_pr_history_pagination_works(self, test_client, mock_admin_user):
        """Test GET /api/admin/scip-pr-history supports pagination."""
        # ARRANGE
        test_entries = [
            {"event_type": "pr_creation_success", "job_id": f"job-{i}"}
            for i in range(150)
        ]

        with patch(
            "code_indexer.server.auth.audit_logger.PasswordChangeAuditLogger.get_pr_logs"
        ) as mock_get_logs:
            # Return first page
            mock_get_logs.return_value = test_entries[:50]

            # ACT
            response = test_client.get("/api/admin/scip-pr-history?limit=50&offset=0")

            # ASSERT
            assert response.status_code == 200
            data = response.json()
            assert len(data["logs"]) == 50

            # Verify pagination params were passed
            mock_get_logs.assert_called_once_with(repo_alias=None, limit=50, offset=0)

    def test_cleanup_history_pagination_works(self, test_client, mock_admin_user):
        """Test GET /api/admin/scip-git-cleanup-history supports pagination."""
        # ARRANGE
        test_entries = [
            {"event_type": "git_cleanup", "repo_path": f"/path/{i}"} for i in range(150)
        ]

        with patch(
            "code_indexer.server.auth.audit_logger.PasswordChangeAuditLogger.get_cleanup_logs"
        ) as mock_get_logs:
            # Return first page
            mock_get_logs.return_value = test_entries[:50]

            # ACT
            response = test_client.get(
                "/api/admin/scip-git-cleanup-history?limit=50&offset=0"
            )

            # ASSERT
            assert response.status_code == 200
            data = response.json()
            assert len(data["logs"]) == 50

            # Verify pagination params were passed
            mock_get_logs.assert_called_once_with(repo_path=None, limit=50, offset=0)
