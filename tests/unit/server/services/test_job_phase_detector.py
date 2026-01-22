"""
Unit tests for JobPhaseDetector.

Story #720: Poll Delegation Job with Progress Feedback

Tests follow TDD methodology - tests written FIRST before implementation.
"""

from code_indexer.server.services.job_phase_detector import (
    JobPhase,
    JobPhaseDetector,
    PhaseProgress,
)


class TestJobPhaseEnum:
    """Tests for JobPhase enum values."""

    def test_all_phases_have_string_values(self):
        """
        All JobPhase enum members should have string values.

        Given the JobPhase enum
        When I check all members
        Then each has a string value matching its purpose
        """
        assert JobPhase.REPO_REGISTRATION.value == "repo_registration"
        assert JobPhase.REPO_CLONING.value == "repo_cloning"
        assert JobPhase.CIDX_INDEXING.value == "cidx_indexing"
        assert JobPhase.JOB_RUNNING.value == "job_running"
        assert JobPhase.DONE.value == "done"


class TestJobPhaseDetection:
    """Tests for phase detection logic."""

    def test_detect_phase_repo_registration_when_repos_not_registered(self):
        """
        detect_phase() should return REPO_REGISTRATION when repos not all registered.

        Given a job state where not all repos are registered
        When I call detect_phase()
        Then JobPhase.REPO_REGISTRATION is returned
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [
                {"alias": "repo1", "registered": True},
                {"alias": "repo2", "registered": False},
            ],
        }

        phase = detector.detect_phase(job_state)

        assert phase == JobPhase.REPO_REGISTRATION

    def test_detect_phase_repo_cloning_when_registered_not_cloned(self):
        """
        detect_phase() should return REPO_CLONING when repos registered but not cloned.

        Given a job state where all repos registered but not all cloned
        When I call detect_phase()
        Then JobPhase.REPO_CLONING is returned
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [
                {"alias": "repo1", "registered": True, "cloned": True},
                {"alias": "repo2", "registered": True, "cloned": False},
            ],
        }

        phase = detector.detect_phase(job_state)

        assert phase == JobPhase.REPO_CLONING

    def test_detect_phase_cidx_indexing_when_cloned_not_indexed(self):
        """
        detect_phase() should return CIDX_INDEXING when cloned but not indexed.

        Given a job state where all repos cloned but not all indexed
        When I call detect_phase()
        Then JobPhase.CIDX_INDEXING is returned
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [
                {"alias": "repo1", "registered": True, "cloned": True, "indexed": True},
                {
                    "alias": "repo2",
                    "registered": True,
                    "cloned": True,
                    "indexed": False,
                },
            ],
        }

        phase = detector.detect_phase(job_state)

        assert phase == JobPhase.CIDX_INDEXING

    def test_detect_phase_job_running_when_repos_ready(self):
        """
        detect_phase() should return JOB_RUNNING when all repos ready.

        Given a job state where all repos are registered, cloned, indexed
        When I call detect_phase()
        Then JobPhase.JOB_RUNNING is returned
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [
                {"alias": "repo1", "registered": True, "cloned": True, "indexed": True},
                {"alias": "repo2", "registered": True, "cloned": True, "indexed": True},
            ],
        }

        phase = detector.detect_phase(job_state)

        assert phase == JobPhase.JOB_RUNNING

    def test_detect_phase_done_when_completed(self):
        """
        detect_phase() should return DONE when job is completed.

        Given a job state with status 'completed'
        When I call detect_phase()
        Then JobPhase.DONE is returned
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "completed",
            "result": "The authentication system uses...",
        }

        phase = detector.detect_phase(job_state)

        assert phase == JobPhase.DONE

    def test_detect_phase_done_when_failed(self):
        """
        detect_phase() should return DONE when job has failed.

        Given a job state with status 'failed'
        When I call detect_phase()
        Then JobPhase.DONE is returned
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "failed",
            "error": "Repository clone failed",
        }

        phase = detector.detect_phase(job_state)

        assert phase == JobPhase.DONE

    def test_detect_phase_handles_empty_repositories(self):
        """
        detect_phase() should handle job state with no repositories.

        Given a job state with empty repositories list
        When I call detect_phase()
        Then JobPhase.JOB_RUNNING is returned (assume ready)
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [],
        }

        phase = detector.detect_phase(job_state)

        assert phase == JobPhase.JOB_RUNNING

    def test_detect_phase_handles_missing_repositories_key(self):
        """
        detect_phase() should handle job state without repositories key.

        Given a job state without repositories key
        When I call detect_phase()
        Then JobPhase.JOB_RUNNING is returned (assume ready)
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
        }

        phase = detector.detect_phase(job_state)

        assert phase == JobPhase.JOB_RUNNING


class TestPhaseProgressExtraction:
    """Tests for extracting phase-specific progress."""

    def test_get_progress_repo_registration_shows_counts(self):
        """
        get_progress() for REPO_REGISTRATION should show registration counts.

        Given a job state in REPO_REGISTRATION phase
        When I call get_progress()
        Then progress contains repos_total and repos_registered
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [
                {"alias": "repo1", "registered": True},
                {"alias": "repo2", "registered": False},
                {"alias": "repo3", "registered": True},
            ],
        }

        progress = detector.get_progress(job_state, JobPhase.REPO_REGISTRATION)

        assert isinstance(progress, PhaseProgress)
        assert progress.phase == JobPhase.REPO_REGISTRATION
        assert progress.progress["repos_total"] == 3
        assert progress.progress["repos_registered"] == 2
        assert progress.is_terminal is False

    def test_get_progress_repo_cloning_shows_counts(self):
        """
        get_progress() for REPO_CLONING should show cloning counts.

        Given a job state in REPO_CLONING phase
        When I call get_progress()
        Then progress contains repos_total and repos_cloned
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [
                {"alias": "repo1", "registered": True, "cloned": True},
                {"alias": "repo2", "registered": True, "cloned": False},
            ],
        }

        progress = detector.get_progress(job_state, JobPhase.REPO_CLONING)

        assert progress.progress["repos_total"] == 2
        assert progress.progress["repos_cloned"] == 1
        assert progress.is_terminal is False

    def test_get_progress_cidx_indexing_shows_counts(self):
        """
        get_progress() for CIDX_INDEXING should show indexing counts.

        Given a job state in CIDX_INDEXING phase
        When I call get_progress()
        Then progress contains repos_total and repos_indexed
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [
                {"alias": "repo1", "registered": True, "cloned": True, "indexed": True},
                {
                    "alias": "repo2",
                    "registered": True,
                    "cloned": True,
                    "indexed": False,
                },
            ],
        }

        progress = detector.get_progress(job_state, JobPhase.CIDX_INDEXING)

        assert progress.progress["repos_total"] == 2
        assert progress.progress["repos_indexed"] == 1
        assert progress.is_terminal is False

    def test_get_progress_job_running_shows_exchange_counts(self):
        """
        get_progress() for JOB_RUNNING should show exchange/tool counts.

        Given a job state in JOB_RUNNING phase
        When I call get_progress()
        Then progress contains exchange_count and tool_use_count
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "in_progress",
            "repositories": [
                {"alias": "repo1", "registered": True, "cloned": True, "indexed": True},
            ],
            "exchange_count": 5,
            "tool_use_count": 12,
        }

        progress = detector.get_progress(job_state, JobPhase.JOB_RUNNING)

        assert progress.progress["exchange_count"] == 5
        assert progress.progress["tool_use_count"] == 12
        assert progress.is_terminal is False

    def test_get_progress_done_completed_includes_result(self):
        """
        get_progress() for DONE (completed) should include result.

        Given a completed job state
        When I call get_progress()
        Then progress includes result and is_terminal=True
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "completed",
            "result": "The authentication system uses JWT tokens...",
        }

        progress = detector.get_progress(job_state, JobPhase.DONE)

        assert (
            progress.progress.get("result")
            == "The authentication system uses JWT tokens..."
        )
        assert progress.is_terminal is True

    def test_get_progress_done_failed_includes_error(self):
        """
        get_progress() for DONE (failed) should include error.

        Given a failed job state
        When I call get_progress()
        Then progress includes error and is_terminal=True
        """
        detector = JobPhaseDetector()
        job_state = {
            "status": "failed",
            "error": "Repository clone failed",
        }

        progress = detector.get_progress(job_state, JobPhase.DONE)

        assert progress.progress.get("error") == "Repository clone failed"
        assert progress.is_terminal is True
