"""
TDD Tests for SystemMetricsCollector singleton (Story #696).

These tests define the expected behavior for the SystemMetricsCollector class
which provides system metrics (CPU, memory, disk, network) for both health
endpoint and OTEL observable gauges.

Following TDD methodology - tests written FIRST before implementation.
All tests use REAL psutil calls following MESSI Rule #1: No mocks.
"""

import threading


# =============================================================================
# SystemMetricsCollector Import Tests
# =============================================================================


class TestSystemMetricsCollectorImport:
    """Tests for SystemMetricsCollector import behavior."""

    def test_system_metrics_collector_can_be_imported(self):
        """
        SystemMetricsCollector can be imported from services module.

        Given the services module exists
        When I import SystemMetricsCollector
        Then the import succeeds
        """
        from code_indexer.server.services.system_metrics_collector import (
            SystemMetricsCollector,
        )

        assert SystemMetricsCollector is not None

    def test_get_system_metrics_collector_function_exists(self):
        """
        get_system_metrics_collector() function is exported.

        Given the services module exists
        When I import get_system_metrics_collector
        Then the import succeeds
        """
        from code_indexer.server.services.system_metrics_collector import (
            get_system_metrics_collector,
        )

        assert callable(get_system_metrics_collector)

    def test_reset_system_metrics_collector_function_exists(self):
        """
        reset_system_metrics_collector() function is exported for testing.

        Given the services module exists
        When I import reset_system_metrics_collector
        Then the import succeeds
        """
        from code_indexer.server.services.system_metrics_collector import (
            reset_system_metrics_collector,
        )

        assert callable(reset_system_metrics_collector)


# =============================================================================
# Singleton Pattern Tests
# =============================================================================


class TestSystemMetricsCollectorSingleton:
    """Tests for SystemMetricsCollector singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        from code_indexer.server.services.system_metrics_collector import (
            reset_system_metrics_collector,
        )

        reset_system_metrics_collector()

    def teardown_method(self):
        """Reset singleton after each test."""
        from code_indexer.server.services.system_metrics_collector import (
            reset_system_metrics_collector,
        )

        reset_system_metrics_collector()

    def test_singleton_returns_same_instance(self):
        """
        Singleton: get_system_metrics_collector returns same instance.

        Given I call get_system_metrics_collector() multiple times
        When I compare the returned instances
        Then they should be the same object
        """
        from code_indexer.server.services.system_metrics_collector import (
            get_system_metrics_collector,
        )

        collector1 = get_system_metrics_collector()
        collector2 = get_system_metrics_collector()

        assert collector1 is collector2

    def test_reset_clears_singleton(self):
        """
        reset_system_metrics_collector() clears the singleton.

        Given a SystemMetricsCollector singleton exists
        When reset_system_metrics_collector() is called
        Then get_system_metrics_collector() returns a new instance
        """
        from code_indexer.server.services.system_metrics_collector import (
            get_system_metrics_collector,
            reset_system_metrics_collector,
        )

        collector1 = get_system_metrics_collector()
        reset_system_metrics_collector()
        collector2 = get_system_metrics_collector()

        assert collector1 is not collector2

    def test_concurrent_access_returns_same_singleton(self):
        """
        Concurrent access returns same singleton instance.

        Given multiple threads calling get_system_metrics_collector()
        When all calls complete
        Then all threads got the same instance
        """
        from code_indexer.server.services.system_metrics_collector import (
            get_system_metrics_collector,
        )

        instances = []
        errors = []

        def get_instance():
            try:
                instance = get_system_metrics_collector()
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_instance) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)
