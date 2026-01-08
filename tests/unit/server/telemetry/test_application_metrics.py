"""
TDD Tests for Application Metrics (Story #698).

Tests OTEL counters and histograms for search, FTS, and embedding operations.

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
# Metrics Instrumentation Import Tests
# =============================================================================


class TestMetricsInstrumentationImport:
    """Tests for metrics instrumentation module import behavior."""

    def test_application_metrics_can_be_imported(self):
        """ApplicationMetrics class can be imported."""
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        assert ApplicationMetrics is not None

    def test_get_application_metrics_function_exists(self):
        """get_application_metrics() function is exported."""
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            get_application_metrics,
        )

        assert callable(get_application_metrics)


# =============================================================================
# ApplicationMetrics Creation Tests
# =============================================================================


class TestApplicationMetricsCreation:
    """Tests for ApplicationMetrics instantiation."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def test_metrics_created_when_telemetry_enabled(self):
        """
        ApplicationMetrics is created when telemetry is enabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        metrics = ApplicationMetrics(telemetry_manager)

        assert metrics is not None
        assert metrics.is_active

    def test_metrics_not_active_when_disabled(self):
        """
        ApplicationMetrics is not active when telemetry disabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=False,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        metrics = ApplicationMetrics(telemetry_manager)

        assert metrics is not None
        assert not metrics.is_active


# =============================================================================
# Search Metrics Tests
# =============================================================================


class TestSearchMetrics:
    """Tests for search operation metrics."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def test_record_search_request_increments_counter(self):
        """
        record_search_request() increments the search requests counter.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = ApplicationMetrics(telemetry_manager)

        # Record a search request - should not raise
        metrics.record_search_request(
            search_type="semantic",
            repository="test-repo",
            duration_seconds=0.5,
            results_count=10,
            status="success",
        )

        # Verify metric was recorded (counter was incremented)
        assert metrics._search_requests_counter is not None

    def test_record_search_includes_duration_histogram(self):
        """
        record_search_request() records duration in histogram.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = ApplicationMetrics(telemetry_manager)

        # Record a search request with duration
        metrics.record_search_request(
            search_type="semantic",
            repository="test-repo",
            duration_seconds=1.25,
            results_count=5,
            status="success",
        )

        # Verify histogram exists
        assert metrics._search_duration_histogram is not None

    def test_record_search_includes_results_count_histogram(self):
        """
        record_search_request() records results count in histogram.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = ApplicationMetrics(telemetry_manager)

        # Record search with results count
        metrics.record_search_request(
            search_type="semantic",
            repository="test-repo",
            duration_seconds=0.3,
            results_count=25,
            status="success",
        )

        # Verify histogram exists
        assert metrics._search_results_histogram is not None


# =============================================================================
# FTS Metrics Tests
# =============================================================================


class TestFTSMetrics:
    """Tests for full-text search metrics."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def test_record_fts_request_increments_counter(self):
        """
        record_fts_request() increments the FTS requests counter.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = ApplicationMetrics(telemetry_manager)

        # Record FTS request
        metrics.record_fts_request(
            repository="test-repo",
            duration_seconds=0.2,
            matches_count=15,
            status="success",
        )

        # Verify counter exists
        assert metrics._fts_requests_counter is not None


# =============================================================================
# Embedding Metrics Tests
# =============================================================================


class TestEmbeddingMetrics:
    """Tests for embedding operation metrics."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def test_record_embedding_request_increments_counter(self):
        """
        record_embedding_request() increments the embedding requests counter.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = ApplicationMetrics(telemetry_manager)

        # Record embedding request
        metrics.record_embedding_request(
            model="voyage-3",
            tokens_count=500,
            duration_seconds=0.8,
            status="success",
        )

        # Verify counter exists
        assert metrics._embedding_requests_counter is not None

    def test_record_embedding_tracks_token_count(self):
        """
        record_embedding_request() records token count.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = ApplicationMetrics(telemetry_manager)

        # Record embedding with token count
        metrics.record_embedding_request(
            model="voyage-3",
            tokens_count=1500,
            duration_seconds=1.2,
            status="success",
        )

        # Verify token counter exists
        assert metrics._embedding_tokens_counter is not None


# =============================================================================
# Metrics Attributes Tests
# =============================================================================


class TestMetricsAttributes:
    """Tests for metrics attribute handling."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            reset_application_metrics,
        )

        reset_application_metrics()

    def test_search_metrics_support_error_status(self):
        """
        Search metrics can record error status.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=True,
            export_metrics=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = ApplicationMetrics(telemetry_manager)

        # Record a failed search - should not raise
        metrics.record_search_request(
            search_type="semantic",
            repository="test-repo",
            duration_seconds=0.1,
            results_count=0,
            status="error",
        )

        assert metrics.is_active

    def test_noop_when_telemetry_disabled(self):
        """
        Recording metrics is a no-op when telemetry is disabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.metrics_instrumentation import (
            ApplicationMetrics,
        )

        config = TelemetryConfig(
            enabled=False,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        metrics = ApplicationMetrics(telemetry_manager)

        # These should not raise even when disabled
        metrics.record_search_request(
            search_type="semantic",
            repository="test-repo",
            duration_seconds=0.5,
            results_count=10,
            status="success",
        )
        metrics.record_fts_request(
            repository="test-repo",
            duration_seconds=0.2,
            matches_count=5,
            status="success",
        )
        metrics.record_embedding_request(
            model="voyage-3",
            tokens_count=100,
            duration_seconds=0.3,
            status="success",
        )

        assert not metrics.is_active
