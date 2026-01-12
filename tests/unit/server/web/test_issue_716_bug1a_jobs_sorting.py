"""
Unit tests for Issue #716 Bug 1a: Jobs sorting by started_at.

Jobs dashboard should sort by started_at (not created_at) to show most recently
started jobs first. Falls back to created_at when started_at is not available.

Tests are written FIRST following TDD methodology.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestJobsSortingByStartedAt:
    """Tests for Bug 1a: Jobs should be sorted by started_at."""

    def test_jobs_sorted_by_started_at_when_available(self):
        """
        Bug 1a: Jobs should be sorted by started_at when available.

        Given jobs with different started_at times
        When _get_all_jobs is called
        Then jobs are sorted by started_at (most recently started first)
        """
        from src.code_indexer.server.web.routes import _get_all_jobs

        # Job1: created early, started early
        mock_job1 = MagicMock()
        mock_job1.job_id = "job1"
        mock_job1.operation_type = "index"
        mock_job1.status = MagicMock(value="running")
        mock_job1.progress = 50
        mock_job1.created_at = datetime(2026, 1, 12, 10, 0, 0)
        mock_job1.started_at = datetime(2026, 1, 12, 10, 5, 0)
        mock_job1.completed_at = None
        mock_job1.error = None
        mock_job1.username = "user1"
        mock_job1.result = None

        # Job2: created earlier, but started later (should appear first)
        mock_job2 = MagicMock()
        mock_job2.job_id = "job2"
        mock_job2.operation_type = "index"
        mock_job2.status = MagicMock(value="running")
        mock_job2.progress = 75
        mock_job2.created_at = datetime(2026, 1, 12, 9, 0, 0)
        mock_job2.started_at = datetime(2026, 1, 12, 11, 0, 0)
        mock_job2.completed_at = None
        mock_job2.error = None
        mock_job2.username = "user2"
        mock_job2.result = None

        mock_job_manager = MagicMock()
        mock_job_manager.jobs = {"job1": mock_job1, "job2": mock_job2}
        mock_job_manager._lock = MagicMock()
        mock_job_manager._lock.__enter__ = MagicMock(return_value=None)
        mock_job_manager._lock.__exit__ = MagicMock(return_value=None)

        with patch(
            "src.code_indexer.server.web.routes._get_background_job_manager",
            return_value=mock_job_manager
        ):
            jobs, total, pages = _get_all_jobs()

        assert len(jobs) == 2
        # job2 started later (11:00), should be first
        assert jobs[0]["job_id"] == "job2"
        assert jobs[1]["job_id"] == "job1"

    def test_jobs_fallback_to_created_at_when_no_started_at(self):
        """
        Bug 1a: Jobs without started_at should use created_at for sorting.

        Given jobs where some have no started_at
        When _get_all_jobs is called
        Then those jobs use created_at for sorting
        """
        from src.code_indexer.server.web.routes import _get_all_jobs

        # Job1: queued (no started_at), created at 10:00
        mock_job1 = MagicMock()
        mock_job1.job_id = "job1"
        mock_job1.operation_type = "index"
        mock_job1.status = MagicMock(value="queued")
        mock_job1.progress = 0
        mock_job1.created_at = datetime(2026, 1, 12, 10, 0, 0)
        mock_job1.started_at = None
        mock_job1.completed_at = None
        mock_job1.error = None
        mock_job1.username = "user1"
        mock_job1.result = None

        # Job2: queued (no started_at), created at 11:00 (should be first)
        mock_job2 = MagicMock()
        mock_job2.job_id = "job2"
        mock_job2.operation_type = "index"
        mock_job2.status = MagicMock(value="queued")
        mock_job2.progress = 0
        mock_job2.created_at = datetime(2026, 1, 12, 11, 0, 0)
        mock_job2.started_at = None
        mock_job2.completed_at = None
        mock_job2.error = None
        mock_job2.username = "user2"
        mock_job2.result = None

        mock_job_manager = MagicMock()
        mock_job_manager.jobs = {"job1": mock_job1, "job2": mock_job2}
        mock_job_manager._lock = MagicMock()
        mock_job_manager._lock.__enter__ = MagicMock(return_value=None)
        mock_job_manager._lock.__exit__ = MagicMock(return_value=None)

        with patch(
            "src.code_indexer.server.web.routes._get_background_job_manager",
            return_value=mock_job_manager
        ):
            jobs, total, pages = _get_all_jobs()

        assert len(jobs) == 2
        # job2 created later (11:00), should be first
        assert jobs[0]["job_id"] == "job2"
        assert jobs[1]["job_id"] == "job1"
