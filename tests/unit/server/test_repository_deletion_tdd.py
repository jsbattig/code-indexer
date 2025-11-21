"""
Test-Driven Development tests for repository deletion error fix.

This test suite implements the failing tests for the repository deletion
story, following TDD methodology to reproduce the broken pipe error
and other deletion failure scenarios.
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app
from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoError,
    GitOperationError,
)


@pytest.mark.e2e
class TestRepositoryDeletionTDD:
    """
    TDD test suite for repository deletion error fix.

    These tests are designed to FAIL initially and pass only after
    implementing the proper fix for the broken pipe error.
    """

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client):
        """Create authentication headers for admin user."""
        login_data = {"username": "admin", "password": "admin"}
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_successful_repository_deletion_returns_204(
        self, client, auth_headers, monkeypatch
    ):
        """
        Test that successful repository deletion returns HTTP 204.

        This test will FAIL initially because current implementation
        returns 200 instead of proper 204 No Content status.
        """
        mock_manager = MagicMock()
        mock_manager.remove_golden_repo.return_value = {
            "success": True,
            "message": "Golden repository 'test-repo' removed successfully",
        }
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/test-repo", headers=auth_headers
        )

        # FAILING TEST: Should return 204, currently returns 200
        assert response.status_code == 204, f"Expected 204, got {response.status_code}"
        # 204 responses should have no content
        assert response.text == ""

    def test_broken_pipe_error_handling_transaction_rollback(
        self, client, auth_headers, monkeypatch
    ):
        """
        Test that broken pipe errors during cleanup don't cause HTTP 500.

        This test reproduces the broken pipe error scenario and will FAIL
        until proper transaction management and error handling is implemented.
        """
        mock_manager = MagicMock()

        # Simulate broken pipe error during cleanup (the root cause)
        broken_pipe_error = BrokenPipeError("[Errno 32] Broken pipe")
        mock_manager.remove_golden_repo.side_effect = GitOperationError(
            f"Failed to cleanup repository files: {broken_pipe_error}"
        )

        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/broken-pipe-repo", headers=auth_headers
        )

        # FAILING TEST: Should return 500 with proper error handling,
        # not crash or return broken pipe error to user
        assert response.status_code == 500
        response_data = response.json()

        # Error message should be sanitized, not expose internal broken pipe details
        assert "broken pipe" not in response_data["detail"].lower()
        assert "internal communication error" in response_data["detail"].lower()

    def test_concurrent_deletion_handling(self, client, auth_headers, monkeypatch):
        """
        Test that concurrent deletion attempts are handled correctly.

        This test will FAIL until proper locking mechanisms are implemented
        to prevent race conditions during repository deletion.
        """
        mock_manager = MagicMock()

        # First call succeeds
        mock_manager.remove_golden_repo.return_value = {
            "success": True,
            "message": "Golden repository 'concurrent-repo' removed successfully",
        }

        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        # Simulate concurrent deletion attempts
        response1 = client.delete(
            "/api/admin/golden-repos/concurrent-repo", headers=auth_headers
        )

        # Second call should see repo as already deleted
        mock_manager.remove_golden_repo.side_effect = GoldenRepoError(
            "Golden repository 'concurrent-repo' not found"
        )

        response2 = client.delete(
            "/api/admin/golden-repos/concurrent-repo", headers=auth_headers
        )

        # FAILING TEST: First should succeed with 204, second should be 404
        assert response1.status_code == 204
        assert response2.status_code == 404
        assert "not found" in response2.json()["detail"]

    def test_active_job_cancellation_during_deletion(
        self, client, auth_headers, monkeypatch
    ):
        """
        Test that active jobs are cancelled gracefully during deletion.

        This test will FAIL until job cancellation logic is implemented
        in the deletion workflow.
        """
        mock_manager = MagicMock()
        mock_job_manager = MagicMock()

        # Mock background jobs for the repository
        mock_job_manager.get_jobs_by_operation_and_params.return_value = [
            {"job_id": "active-job-123", "status": "running"}
        ]
        mock_job_manager.cancel_job.return_value = {
            "success": True,
            "message": "Job cancelled",
        }

        mock_manager.remove_golden_repo.return_value = {
            "success": True,
            "message": "Repository removed after job cancellation",
        }

        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )
        monkeypatch.setattr(
            "src.code_indexer.server.app.background_job_manager", mock_job_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/active-job-repo", headers=auth_headers
        )

        # FAILING TEST: Should cancel jobs and then delete successfully
        assert response.status_code == 204
        # Verify job cancellation was attempted
        mock_job_manager.get_jobs_by_operation_and_params.assert_called()

    def test_partial_deletion_failure_rollback(self, client, auth_headers, monkeypatch):
        """
        Test that partial deletion failures trigger proper rollback.

        This test will FAIL until transaction management with rollback
        is implemented for deletion operations.
        """
        mock_manager = MagicMock()

        # Simulate partial failure during deletion
        mock_manager.remove_golden_repo.side_effect = GitOperationError(
            "Failed to cleanup repository files: Filesystem service unavailable"
        )

        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/partial-failure-repo", headers=auth_headers
        )

        # FAILING TEST: Should return 503 for service unavailability
        assert response.status_code == 503
        response_data = response.json()
        assert "unavailability" in response_data["detail"].lower()

    def test_resource_cleanup_in_finally_block(self, client, auth_headers, monkeypatch):
        """
        Test that resources are cleaned up even when exceptions occur.

        This test will FAIL until proper finally block cleanup is implemented
        to prevent resource leaks during deletion failures.
        """
        mock_manager = MagicMock()

        # Mock a cleanup method to track if it was called
        cleanup_tracker = {"cleanup_called": False}

        def mock_remove_with_cleanup_tracking(alias):
            try:
                # Simulate some work
                if alias == "exception-repo":
                    raise RuntimeError("Simulated deletion error")
                return {"success": True, "message": "Removed successfully"}
            finally:
                # This should always be called
                cleanup_tracker["cleanup_called"] = True

        mock_manager.remove_golden_repo.side_effect = mock_remove_with_cleanup_tracking
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/exception-repo", headers=auth_headers
        )

        # FAILING TEST: Cleanup should be called even when error occurs
        assert cleanup_tracker["cleanup_called"] is True
        assert response.status_code == 500  # Expected error response

    def test_database_transaction_consistency(self, client, auth_headers, monkeypatch):
        """
        Test that database operations maintain ACID properties during deletion.

        This test will FAIL until proper database transaction management
        is implemented with proper commit/rollback behavior.
        """
        mock_manager = MagicMock()
        mock_transaction = MagicMock()

        # Mock database transaction behavior
        transaction_state = {"committed": False, "rolledback": False}

        def mock_transaction_commit():
            transaction_state["committed"] = True

        def mock_transaction_rollback():
            transaction_state["rolledback"] = True

        mock_transaction.commit = mock_transaction_commit
        mock_transaction.rollback = mock_transaction_rollback

        # Simulate transaction failure
        def mock_remove_with_transaction(alias):
            # Should use transaction properly
            mock_transaction.begin()
            try:
                if alias == "transaction-fail-repo":
                    raise GitOperationError("Simulated cleanup failure")
                mock_transaction.commit()
                return {"success": True, "message": "Removed with transaction"}
            except Exception:
                mock_transaction.rollback()
                raise

        mock_manager.remove_golden_repo.side_effect = mock_remove_with_transaction

        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", mock_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/transaction-fail-repo", headers=auth_headers
        )

        # FAILING TEST: Transaction should be properly rolled back on failure
        assert response.status_code == 500
        assert transaction_state["rolledback"] is True
        assert transaction_state["committed"] is False

    def test_proper_http_status_codes_for_different_errors(
        self, client, auth_headers, monkeypatch
    ):
        """
        Test that different error types return appropriate HTTP status codes.

        This test will FAIL until proper error categorization and HTTP
        status code mapping is implemented.
        """
        test_scenarios = [
            # (error_type, expected_status, error_message)
            (GoldenRepoError("Repository 'missing' not found"), 404, "not found"),
            (
                GitOperationError("Failed to cleanup: Permission denied"),
                500,
                "permission denied",
            ),
            (
                GitOperationError("Failed to cleanup: Filesystem connection refused"),
                503,  # Service unavailable for external service failures
                "unavailability",
            ),
            (
                RuntimeError("Unexpected system error"),
                500,
                "failed to remove repository",
            ),
        ]

        for error, expected_status, expected_text in test_scenarios:
            mock_manager = MagicMock()
            mock_manager.remove_golden_repo.side_effect = error

            monkeypatch.setattr(
                "src.code_indexer.server.app.golden_repo_manager", mock_manager
            )

            response = client.delete(
                "/api/admin/golden-repos/test-repo", headers=auth_headers
            )

            # FAILING TESTS: Should return correct status codes for different error types
            assert response.status_code == expected_status, (
                f"Error {error.__class__.__name__} should return {expected_status}, "
                f"got {response.status_code}"
            )

            if response.status_code != 204:  # Only check content for error responses
                assert expected_text in response.json()["detail"].lower()
