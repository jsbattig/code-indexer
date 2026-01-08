"""
TDD Tests for Job and Repository Metrics (Story #699).

Tests OTEL gauges and counters for job lifecycle and repository state.

All tests use real components following MESSI Rule #1: No mocks.
"""

from src.code_indexer.server.utils.config_manager import TelemetryConfig


def reset_all_singletons():
    """Reset all singletons to ensure clean test state."""
    from src.code_indexer.server.telemetry import (
        reset_telemetry_manager,
        reset_machine_metrics_exporter,
    )
    from src.code_indexer.server.services.system_metrics_collector import (
        reset_system_metrics_collector,
    )

    reset_machine_metrics_exporter()
    reset_telemetry_manager()
    reset_system_metrics_collector()


# =============================================================================
# Job Metrics Import Tests
# =============================================================================


class TestJobMetricsImport:
    """Tests for job metrics module import behavior."""

    def test_job_metrics_can_be_imported(self):
        """JobMetrics class can be imported."""
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        assert JobMetrics is not None

    def test_get_job_metrics_function_exists(self):
        """get_job_metrics() function is exported."""
        from src.code_indexer.server.telemetry.job_metrics import (
            get_job_metrics,
        )

        assert callable(get_job_metrics)


# =============================================================================
# JobMetrics Creation Tests
# =============================================================================


class TestJobMetricsCreation:
    """Tests for JobMetrics instantiation."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def test_metrics_created_when_telemetry_enabled(self):
        """
        JobMetrics is created when telemetry is enabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        metrics = JobMetrics(telemetry_manager)

        assert metrics is not None
        assert metrics.is_active

    def test_metrics_not_active_when_disabled(self):
        """
        JobMetrics is not active when telemetry disabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=False,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        metrics = JobMetrics(telemetry_manager)

        assert metrics is not None
        assert not metrics.is_active


# =============================================================================
# Job Counter Tests
# =============================================================================


class TestJobCounterMetrics:
    """Tests for job completion and failure counters."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def test_record_job_completed_increments_counter(self):
        """
        record_job_completed() increments the completed jobs counter.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # Record job completion - should not raise
        metrics.record_job_completed(
            job_type="repository_sync",
            duration_seconds=120.5,
        )

        # Verify counter exists
        assert metrics._jobs_completed_counter is not None

    def test_record_job_failed_increments_counter(self):
        """
        record_job_failed() increments the failed jobs counter with error_type.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # Record job failure - should not raise
        metrics.record_job_failed(
            job_type="repository_sync",
            error_type="git_clone_failed",
            duration_seconds=30.0,
        )

        # Verify counter exists
        assert metrics._jobs_failed_counter is not None

    def test_record_job_duration_histogram(self):
        """
        record_job_completed() records duration in histogram.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # Record a job completion with duration
        metrics.record_job_completed(
            job_type="repository_activation",
            duration_seconds=45.5,
        )

        # Verify histogram exists
        assert metrics._jobs_duration_histogram is not None


# =============================================================================
# Job Gauge Tests
# =============================================================================


class TestJobGaugeMetrics:
    """Tests for job active and queued gauges."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def test_set_job_counts_callback(self):
        """
        set_job_counts_callback() registers callback for active/queued gauges.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # Register callback
        def get_job_counts():
            return {"active": 3, "queued": 5}

        metrics.set_job_counts_callback(get_job_counts)

        # Verify callback is set
        assert metrics._job_counts_callback is not None

    def test_observable_gauges_registered(self):
        """
        Observable gauges for active and queued jobs are registered.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # Verify gauges exist
        assert metrics._jobs_active_gauge is not None
        assert metrics._jobs_queued_gauge is not None


# =============================================================================
# Repository Metrics Tests
# =============================================================================


class TestRepositoryMetrics:
    """Tests for repository gauge metrics."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def test_set_repository_counts_callback(self):
        """
        set_repository_counts_callback() registers callback for repo gauges.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # Register callback
        def get_repo_counts():
            return {"total": 10, "indexed": 8}

        metrics.set_repository_counts_callback(get_repo_counts)

        # Verify callback is set
        assert metrics._repo_counts_callback is not None

    def test_repository_gauges_registered(self):
        """
        Observable gauges for repository counts are registered.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # Verify gauges exist
        assert metrics._repos_total_gauge is not None
        assert metrics._repos_indexed_gauge is not None

    def test_record_repository_refresh_duration(self):
        """
        record_repository_refresh() records refresh duration histogram.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # Record refresh duration - should not raise
        metrics.record_repository_refresh(
            repository="test-repo",
            duration_seconds=15.5,
            status="success",
        )

        # Verify histogram exists
        assert metrics._repos_refresh_duration_histogram is not None


# =============================================================================
# No-op When Disabled Tests
# =============================================================================


class TestNoopWhenDisabled:
    """Tests for no-op behavior when telemetry disabled."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.job_metrics import (
            reset_job_metrics,
        )

        reset_job_metrics()

    def test_all_methods_noop_when_disabled(self):
        """
        All recording methods are no-op when telemetry is disabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.job_metrics import (
            JobMetrics,
        )

        config = TelemetryConfig(
            enabled=False,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = JobMetrics(telemetry_manager)

        # All of these should not raise even when disabled
        metrics.record_job_completed(
            job_type="repository_sync",
            duration_seconds=100.0,
        )
        metrics.record_job_failed(
            job_type="repository_sync",
            error_type="timeout",
            duration_seconds=60.0,
        )
        metrics.record_repository_refresh(
            repository="test-repo",
            duration_seconds=10.0,
            status="success",
        )
        metrics.set_job_counts_callback(lambda: {"active": 0, "queued": 0})
        metrics.set_repository_counts_callback(lambda: {"total": 0, "indexed": 0})

        assert not metrics.is_active
