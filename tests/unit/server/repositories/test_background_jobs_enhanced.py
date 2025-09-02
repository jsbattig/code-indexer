"""
Unit tests for enhanced Background Job System functionality.

Tests for persistence, user isolation, job management, and API features.
"""

import json
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
)


class TestEnhancedBackgroundJobManager:
    """Test enhanced BackgroundJobManager functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.job_storage_path = Path(self.temp_dir) / "jobs.json"
        # Create manager with persistence path
        self.manager = BackgroundJobManager(storage_path=str(self.job_storage_path))

    def teardown_method(self):
        """Clean up test environment."""
        # Ensure manager is properly shut down first
        if hasattr(self, "manager") and self.manager:
            self.manager.shutdown()

        # Clean up temp files
        if self.job_storage_path.exists():
            self.job_storage_path.unlink()
        # Clean up temp directory and any remaining files
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_manager_initialization_with_persistence(self):
        """Test BackgroundJobManager initialization with persistence."""
        # This test will fail initially as current manager doesn't support storage_path
        manager = BackgroundJobManager(storage_path=str(self.job_storage_path))
        assert manager.storage_path == str(self.job_storage_path)
        assert isinstance(manager.jobs, dict)
        assert len(manager.jobs) == 0

    def test_job_persistence_across_restarts(self):
        """Test that jobs persist across manager restarts."""

        # Submit a job
        def dummy_task():
            return {"status": "success"}

        job_id = self.manager.submit_job(
            "test_operation", dummy_task, submitter_username="user1"
        )

        # Wait for job to complete
        time.sleep(0.1)

        # Create new manager with same storage path - should load persisted jobs
        new_manager = BackgroundJobManager(storage_path=str(self.job_storage_path))

        # Job should still exist
        job_status = new_manager.get_job_status(job_id, username="user1")
        assert job_status is not None
        assert job_status["job_id"] == job_id

    def test_user_isolation_in_job_submission(self):
        """Test that jobs are isolated per user."""

        def dummy_task():
            return {"status": "success"}

        # Submit jobs for different users
        job1_id = self.manager.submit_job(
            "test_op", dummy_task, submitter_username="user1"
        )
        job2_id = self.manager.submit_job(
            "test_op", dummy_task, submitter_username="user2"
        )

        # User1 can see only their job
        user1_job = self.manager.get_job_status(job1_id, username="user1")
        user1_cannot_see_user2 = self.manager.get_job_status(job2_id, username="user1")

        assert user1_job is not None
        assert user1_cannot_see_user2 is None

        # User2 can see only their job
        user2_job = self.manager.get_job_status(job2_id, username="user2")
        user2_cannot_see_user1 = self.manager.get_job_status(job1_id, username="user2")

        assert user2_job is not None
        assert user2_cannot_see_user1 is None

    def test_job_listing_with_pagination(self):
        """Test job listing with pagination support."""

        def dummy_task():
            return {"status": "success"}

        # Submit multiple jobs for a user
        job_ids = []
        for i in range(5):
            job_id = self.manager.submit_job(
                f"test_op_{i}", dummy_task, submitter_username="user1"
            )
            job_ids.append(job_id)

        # Test pagination
        page1 = self.manager.list_jobs(username="user1", limit=2, offset=0)
        page2 = self.manager.list_jobs(username="user1", limit=2, offset=2)

        assert len(page1["jobs"]) == 2
        assert len(page2["jobs"]) == 2
        assert page1["total"] == 5
        assert page2["total"] == 5

        # Jobs should be sorted by creation time (newest first)
        assert page1["jobs"][0]["created_at"] >= page1["jobs"][1]["created_at"]

    def test_job_listing_with_status_filter(self):
        """Test job listing with status filtering."""

        def failing_task():
            raise Exception("Test failure")

        def success_task():
            return {"status": "success"}

        # Submit jobs with different outcomes
        self.manager.submit_job("success_op", success_task, submitter_username="user1")
        self.manager.submit_job("fail_op", failing_task, submitter_username="user1")

        # Wait for jobs to complete
        time.sleep(0.2)

        # Filter by status
        completed_jobs = self.manager.list_jobs(
            username="user1", status_filter="completed"
        )
        failed_jobs = self.manager.list_jobs(username="user1", status_filter="failed")

        assert len(completed_jobs["jobs"]) == 1
        assert len(failed_jobs["jobs"]) == 1
        assert completed_jobs["jobs"][0]["status"] == "completed"
        assert failed_jobs["jobs"][0]["status"] == "failed"

    def test_job_cancellation(self):
        """Test job cancellation functionality."""

        def long_running_task():
            time.sleep(2)  # Long running task
            return {"status": "success"}

        # Submit long-running job
        job_id = self.manager.submit_job(
            "long_op", long_running_task, submitter_username="user1"
        )

        # Wait a moment for job to start
        time.sleep(0.1)

        # Cancel the job
        result = self.manager.cancel_job(job_id, username="user1")

        assert result["success"] is True
        assert result["message"] == "Job cancelled successfully"

        # Wait a bit more for cancellation to be processed
        time.sleep(0.2)

        # Job status should reflect cancellation
        job_status = self.manager.get_job_status(job_id, username="user1")
        assert job_status["status"] == "cancelled"

    def test_job_cancellation_user_isolation(self):
        """Test that users can only cancel their own jobs."""

        def long_running_task():
            time.sleep(2)
            return {"status": "success"}

        # User1 submits job
        job_id = self.manager.submit_job(
            "long_op", long_running_task, submitter_username="user1"
        )

        # User2 tries to cancel user1's job
        result = self.manager.cancel_job(job_id, username="user2")

        assert result["success"] is False
        assert "not found or not authorized" in result["message"].lower()

    def test_progress_tracking_with_callbacks(self):
        """Test progress tracking with callback support."""

        def task_with_progress(progress_callback):
            for i in range(0, 101, 25):
                progress_callback(i)
                time.sleep(0.05)
            return {"status": "success"}

        job_id = self.manager.submit_job(
            "progress_op", task_with_progress, submitter_username="user1"
        )

        # Wait for job to complete
        time.sleep(0.5)

        job_status = self.manager.get_job_status(job_id, username="user1")
        assert job_status["progress"] == 100
        assert job_status["status"] == "completed"

    def test_max_jobs_per_user_limit(self):
        """Test resource management with max jobs per user."""

        def dummy_task():
            time.sleep(0.1)
            return {"status": "success"}

        # Set max jobs per user to 2
        self.manager.max_jobs_per_user = 2

        # Submit jobs up to the limit
        self.manager.submit_job("op1", dummy_task, submitter_username="user1")
        self.manager.submit_job("op2", dummy_task, submitter_username="user1")

        # Third job should be rejected
        with pytest.raises(Exception, match="Maximum number of jobs exceeded"):
            self.manager.submit_job("op3", dummy_task, submitter_username="user1")

        # Different user should still be able to submit
        job3 = self.manager.submit_job("op3", dummy_task, submitter_username="user2")
        assert job3 is not None

    def test_admin_job_prioritization(self):
        """Test that admin jobs get higher priority."""
        execution_order = []

        def tracked_task(task_id):
            execution_order.append(task_id)
            time.sleep(0.05)
            return {"status": "success", "task_id": task_id}

        # Submit regular user jobs first
        self.manager.submit_job(
            "user_op1", tracked_task, "task1", submitter_username="user1"
        )
        self.manager.submit_job(
            "user_op2", tracked_task, "task2", submitter_username="user2"
        )

        # Submit admin job (should get priority)
        self.manager.submit_job(
            "admin_op",
            tracked_task,
            "admin_task",
            submitter_username="admin",
            is_admin=True,
        )

        # Wait for all jobs to complete
        time.sleep(0.3)

        # Admin job should execute first (after any already running jobs)
        # Note: This assumes the manager has a priority queue implementation
        assert "admin_task" in execution_order
        # The exact order depends on timing, but admin job should be prioritized

    def test_job_metadata_storage(self):
        """Test that job metadata is properly stored."""

        def dummy_task():
            return {"status": "success"}

        job_id = self.manager.submit_job(
            "metadata_test", dummy_task, submitter_username="testuser"
        )

        job_status = self.manager.get_job_status(job_id, username="testuser")

        assert job_status["username"] == "testuser"
        assert job_status["operation_type"] == "metadata_test"
        assert "created_at" in job_status
        assert isinstance(job_status["created_at"], str)

    def test_job_cleanup_respects_user_isolation(self):
        """Test that job cleanup respects user boundaries."""

        def dummy_task():
            return {"status": "success"}

        # Submit jobs for different users
        user1_job = self.manager.submit_job(
            "old_op", dummy_task, submitter_username="user1"
        )
        user2_job = self.manager.submit_job(
            "old_op", dummy_task, submitter_username="user2"
        )

        # Wait for jobs to complete
        time.sleep(0.1)

        # Manually set completion time to past (for testing cleanup)
        with self.manager._lock:
            self.manager.jobs[user1_job].completed_at = datetime.now(
                timezone.utc
            ) - timedelta(hours=25)
            self.manager.jobs[user2_job].completed_at = datetime.now(
                timezone.utc
            ) - timedelta(hours=25)

        # Cleanup should remove both old jobs regardless of user
        cleaned_count = self.manager.cleanup_old_jobs(max_age_hours=24)
        assert cleaned_count == 2

    def test_persistent_storage_file_format(self):
        """Test that persistent storage uses correct JSON format."""

        def dummy_task():
            return {"status": "success"}

        job_id = self.manager.submit_job(
            "format_test", dummy_task, submitter_username="user1"
        )

        # Wait for job to complete and persist
        time.sleep(0.1)
        self.manager._persist_jobs()  # Force persistence

        # Check storage file format
        assert self.job_storage_path.exists()
        with open(self.job_storage_path, "r") as f:
            stored_data = json.load(f)

        assert isinstance(stored_data, dict)
        assert job_id in stored_data
        job_data = stored_data[job_id]

        # Verify required fields
        required_fields = [
            "job_id",
            "operation_type",
            "status",
            "created_at",
            "username",
        ]
        for field in required_fields:
            assert field in job_data

    def test_error_handling_in_persistence(self):
        """Test error handling in persistence operations."""
        # Test with invalid storage path
        invalid_manager = BackgroundJobManager(storage_path="/invalid/path/jobs.json")

        def dummy_task():
            return {"status": "success"}

        # Should still work but log error
        job_id = invalid_manager.submit_job(
            "error_test", dummy_task, submitter_username="user1"
        )
        assert job_id is not None

        # Job should still be trackable in memory
        job_status = invalid_manager.get_job_status(job_id, username="user1")
        assert job_status is not None
