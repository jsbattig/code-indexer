"""
Unit tests for AC5: Fix "Unknown" Repo Bug.

Tests that BackgroundJobManager.submit_job() correctly handles repo_alias parameter
and validates against "unknown" values.
"""

import logging

from src.code_indexer.server.repositories.background_jobs import (
    BackgroundJobManager,
)


class TestUnknownRepoBugFix:
    """Test suite for unknown repo bug fix (Story #646 AC5)."""

    def test_submit_job_accepts_repo_alias_parameter(self, tmp_path):
        """Test that submit_job accepts repo_alias parameter."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        # Act
        job_id = manager.submit_job(
            operation_type="test_operation",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="test-repo",  # NEW parameter
        )

        # Assert
        job = manager.jobs[job_id]
        assert job.repo_alias == "test-repo"

    def test_submit_job_without_repo_alias_defaults_to_none(self, tmp_path):
        """Test that submit_job without repo_alias defaults to None (backward compatibility)."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        # Act
        job_id = manager.submit_job(
            operation_type="test_operation",
            func=dummy_func,
            submitter_username="test_user",
            # No repo_alias provided
        )

        # Assert
        job = manager.jobs[job_id]
        assert job.repo_alias is None

    def test_submit_job_warns_when_repo_alias_is_unknown(self, tmp_path, caplog):
        """Test that submit_job logs warning when repo_alias is 'unknown'."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        # Act
        with caplog.at_level(logging.WARNING):
            job_id = manager.submit_job(
                operation_type="test_operation",
                func=dummy_func,
                submitter_username="test_user",
                repo_alias="unknown",  # Should trigger warning
            )

        # Assert
        assert job_id in manager.jobs
        job = manager.jobs[job_id]
        assert job.repo_alias == "unknown"  # Still accepted for backward compatibility

        # Check that warning was logged
        assert any(
            "repo_alias='unknown'" in record.message.lower()
            for record in caplog.records
            if record.levelname == "WARNING"
        )

    def test_submit_job_warns_when_repo_alias_is_missing(self, tmp_path, caplog):
        """Test that submit_job logs warning when repo_alias is None."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        # Act
        with caplog.at_level(logging.WARNING):
            job_id = manager.submit_job(
                operation_type="test_operation",
                func=dummy_func,
                submitter_username="test_user",
                # No repo_alias
            )

        # Assert
        assert job_id in manager.jobs
        job = manager.jobs[job_id]
        assert job.repo_alias is None

        # Check that warning was logged
        assert any(
            "without repo_alias" in record.message.lower()
            for record in caplog.records
            if record.levelname == "WARNING"
        )

    def test_submit_job_accepts_valid_repo_alias_without_warning(
        self, tmp_path, caplog
    ):
        """Test that submit_job with valid repo_alias does NOT log warning."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        # Act
        with caplog.at_level(logging.WARNING):
            job_id = manager.submit_job(
                operation_type="test_operation",
                func=dummy_func,
                submitter_username="test_user",
                repo_alias="valid-repo-alias",
            )

        # Assert
        assert job_id in manager.jobs
        job = manager.jobs[job_id]
        assert job.repo_alias == "valid-repo-alias"

        # Check that NO warning was logged
        assert not any(
            "repo_alias" in record.message.lower()
            for record in caplog.records
            if record.levelname == "WARNING"
        )

    def test_get_job_status_includes_repo_alias(self, tmp_path):
        """Test that get_job_status returns repo_alias in response."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        job_id = manager.submit_job(
            operation_type="test_operation",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="test-repo",
        )

        # Act
        status = manager.get_job_status(job_id, "test_user")

        # Assert
        assert status is not None
        assert status["repo_alias"] == "test-repo"

    def test_list_jobs_includes_repo_alias(self, tmp_path):
        """Test that list_jobs returns repo_alias for each job."""
        # Arrange
        storage_path = str(tmp_path / "jobs.json")
        manager = BackgroundJobManager(storage_path=storage_path)

        def dummy_func():
            return {"status": "completed"}

        # Create two jobs with different repo aliases
        job_id_1 = manager.submit_job(
            operation_type="test_operation_1",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="repo-one",
        )

        job_id_2 = manager.submit_job(
            operation_type="test_operation_2",
            func=dummy_func,
            submitter_username="test_user",
            repo_alias="repo-two",
        )

        # Act
        result = manager.list_jobs("test_user", limit=10)

        # Assert
        assert result["total"] == 2
        jobs = result["jobs"]
        assert len(jobs) == 2

        # Find jobs by ID and check repo_alias
        job_1_data = next(j for j in jobs if j["job_id"] == job_id_1)
        job_2_data = next(j for j in jobs if j["job_id"] == job_id_2)

        assert job_1_data["repo_alias"] == "repo-one"
        assert job_2_data["repo_alias"] == "repo-two"
