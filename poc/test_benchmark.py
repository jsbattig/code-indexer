"""Unit tests for benchmark logic and GO/NO-GO criteria."""

import pytest

from poc.benchmark import BenchmarkResults


class TestBenchmarkResults:
    """Test BenchmarkResults class and criteria calculations."""

    def test_benchmark_results_initialization(self):
        """Test BenchmarkResults initializes with default values."""
        results = BenchmarkResults()

        assert results.baseline_semantic_ms == 0.0
        assert results.baseline_fts_ms == 0.0
        assert results.baseline_hybrid_ms == 0.0

        assert results.daemon_cold_semantic_ms == 0.0
        assert results.daemon_cold_fts_ms == 0.0
        assert results.daemon_cold_hybrid_ms == 0.0

        assert results.daemon_warm_semantic_ms == 0.0
        assert results.daemon_warm_fts_ms == 0.0
        assert results.daemon_warm_hybrid_ms == 0.0

        assert results.rpc_overhead_ms == 0.0
        assert results.connection_time_ms == 0.0

        assert results.stability_success_count == 0
        assert results.stability_failure_count == 0
        assert results.stability_errors == []

        assert results.memory_start_mb == 0.0
        assert results.memory_end_mb == 0.0
        assert results.memory_growth_mb == 0.0

    def test_calculate_improvements_semantic(self):
        """Test calculate_improvements for semantic queries."""
        results = BenchmarkResults()
        results.baseline_semantic_ms = 3000.0
        results.daemon_warm_semantic_ms = 100.0

        improvements = results.calculate_improvements()

        # (3000 - 100) / 3000 * 100 = 96.67%
        assert improvements["semantic"] == pytest.approx(96.67, rel=0.01)

    def test_calculate_improvements_fts(self):
        """Test calculate_improvements for FTS queries."""
        results = BenchmarkResults()
        results.baseline_fts_ms = 2200.0
        results.daemon_warm_fts_ms = 50.0

        improvements = results.calculate_improvements()

        # (2200 - 50) / 2200 * 100 = 97.73%
        assert improvements["fts"] == pytest.approx(97.73, rel=0.01)

    def test_calculate_improvements_hybrid(self):
        """Test calculate_improvements for hybrid queries."""
        results = BenchmarkResults()
        results.baseline_hybrid_ms = 3500.0
        results.daemon_warm_hybrid_ms = 150.0

        improvements = results.calculate_improvements()

        # (3500 - 150) / 3500 * 100 = 95.71%
        assert improvements["hybrid"] == pytest.approx(95.71, rel=0.01)

    def test_calculate_improvements_zero_baseline(self):
        """Test calculate_improvements with zero baseline (edge case)."""
        results = BenchmarkResults()
        results.baseline_semantic_ms = 0.0
        results.daemon_warm_semantic_ms = 100.0

        improvements = results.calculate_improvements()

        # Zero baseline should result in 0% improvement (not division by zero)
        assert improvements["semantic"] == 0.0

    def test_calculate_improvements_slower_than_baseline(self):
        """Test calculate_improvements when daemon is slower (negative improvement)."""
        results = BenchmarkResults()
        results.baseline_semantic_ms = 100.0
        results.daemon_warm_semantic_ms = 200.0

        improvements = results.calculate_improvements()

        # (100 - 200) / 100 * 100 = -100% (slower)
        assert improvements["semantic"] == -100.0

    def test_meets_go_criteria_semantic_30pct(self):
        """Test GO criteria: semantic ≥30% speedup."""
        results = BenchmarkResults()
        results.baseline_semantic_ms = 3000.0

        # Exactly 30% improvement
        results.daemon_warm_semantic_ms = 2100.0  # 30% improvement
        criteria = results.meets_go_criteria()
        assert criteria["semantic_30pct"] is True

        # Below 30% improvement
        results.daemon_warm_semantic_ms = 2200.0  # 26.67% improvement
        criteria = results.meets_go_criteria()
        assert criteria["semantic_30pct"] is False

        # Above 30% improvement
        results.daemon_warm_semantic_ms = 2000.0  # 33.33% improvement
        criteria = results.meets_go_criteria()
        assert criteria["semantic_30pct"] is True

    def test_meets_go_criteria_fts_90pct(self):
        """Test GO criteria: FTS ≥90% speedup."""
        results = BenchmarkResults()
        results.baseline_fts_ms = 2200.0

        # Exactly 90% improvement
        results.daemon_warm_fts_ms = 220.0  # 90% improvement
        criteria = results.meets_go_criteria()
        assert criteria["fts_90pct"] is True

        # Below 90% improvement
        results.daemon_warm_fts_ms = 250.0  # 88.64% improvement
        criteria = results.meets_go_criteria()
        assert criteria["fts_90pct"] is False

        # Above 90% improvement
        results.daemon_warm_fts_ms = 100.0  # 95.45% improvement
        criteria = results.meets_go_criteria()
        assert criteria["fts_90pct"] is True

    def test_meets_go_criteria_rpc_overhead_100ms(self):
        """Test GO criteria: RPC overhead <100ms."""
        results = BenchmarkResults()

        # Below 100ms
        results.rpc_overhead_ms = 50.0
        criteria = results.meets_go_criteria()
        assert criteria["rpc_overhead_100ms"] is True

        # Exactly 100ms (should fail, must be strictly less than)
        results.rpc_overhead_ms = 100.0
        criteria = results.meets_go_criteria()
        assert criteria["rpc_overhead_100ms"] is False

        # Above 100ms
        results.rpc_overhead_ms = 150.0
        criteria = results.meets_go_criteria()
        assert criteria["rpc_overhead_100ms"] is False

    def test_meets_go_criteria_stability_99pct(self):
        """Test GO criteria: stability ≥99% (100 consecutive queries)."""
        results = BenchmarkResults()

        # Exactly 99% success (99/100)
        results.stability_success_count = 99
        results.stability_failure_count = 1
        criteria = results.meets_go_criteria()
        assert criteria["stability_99pct"] is True

        # Below 99% success (98/100)
        results.stability_success_count = 98
        results.stability_failure_count = 2
        criteria = results.meets_go_criteria()
        assert criteria["stability_99pct"] is False

        # 100% success
        results.stability_success_count = 100
        results.stability_failure_count = 0
        criteria = results.meets_go_criteria()
        assert criteria["stability_99pct"] is True

    def test_meets_go_criteria_stability_incomplete(self):
        """Test GO criteria: stability fails if not 100 queries."""
        results = BenchmarkResults()

        # Only 50 queries (incomplete)
        results.stability_success_count = 50
        results.stability_failure_count = 0
        criteria = results.meets_go_criteria()
        assert criteria["stability_99pct"] is False

    def test_meets_go_criteria_connection_100ms(self):
        """Test GO criteria: connection time <100ms."""
        results = BenchmarkResults()

        # Below 100ms
        results.connection_time_ms = 50.0
        criteria = results.meets_go_criteria()
        assert criteria["connection_100ms"] is True

        # Exactly 100ms (should fail)
        results.connection_time_ms = 100.0
        criteria = results.meets_go_criteria()
        assert criteria["connection_100ms"] is False

        # Above 100ms
        results.connection_time_ms = 150.0
        criteria = results.meets_go_criteria()
        assert criteria["connection_100ms"] is False

    def test_meets_go_criteria_hybrid_working(self):
        """Test GO criteria: hybrid search shows improvement."""
        results = BenchmarkResults()
        results.baseline_hybrid_ms = 3500.0

        # Positive improvement
        results.daemon_warm_hybrid_ms = 100.0
        criteria = results.meets_go_criteria()
        assert criteria["hybrid_working"] is True

        # Zero improvement
        results.daemon_warm_hybrid_ms = 3500.0
        criteria = results.meets_go_criteria()
        assert criteria["hybrid_working"] is False

        # Negative improvement (slower)
        results.daemon_warm_hybrid_ms = 4000.0
        criteria = results.meets_go_criteria()
        assert criteria["hybrid_working"] is False

    def test_meets_go_criteria_memory_100mb(self):
        """Test GO criteria: memory growth <100MB."""
        results = BenchmarkResults()

        # Below 100MB
        results.memory_growth_mb = 50.0
        criteria = results.meets_go_criteria()
        assert criteria["memory_100mb"] is True

        # Exactly 100MB (should fail)
        results.memory_growth_mb = 100.0
        criteria = results.meets_go_criteria()
        assert criteria["memory_100mb"] is False

        # Above 100MB
        results.memory_growth_mb = 150.0
        criteria = results.meets_go_criteria()
        assert criteria["memory_100mb"] is False

    def test_is_go_all_criteria_pass(self):
        """Test is_go returns True when all criteria pass."""
        results = BenchmarkResults()

        # Set all values to pass criteria
        results.baseline_semantic_ms = 3000.0
        results.daemon_warm_semantic_ms = 100.0  # 96.67% improvement (>30%)

        results.baseline_fts_ms = 2200.0
        results.daemon_warm_fts_ms = 50.0  # 97.73% improvement (>90%)

        results.baseline_hybrid_ms = 3500.0
        results.daemon_warm_hybrid_ms = 150.0  # 95.71% improvement (>0%)

        results.rpc_overhead_ms = 5.0  # <100ms
        results.connection_time_ms = 30.0  # <100ms

        results.stability_success_count = 100
        results.stability_failure_count = 0  # 100% success (>99%)

        results.memory_growth_mb = 20.0  # <100MB

        assert results.is_go() is True

    def test_is_go_one_criterion_fails(self):
        """Test is_go returns False when any criterion fails."""
        results = BenchmarkResults()

        # Set all values to pass criteria
        results.baseline_semantic_ms = 3000.0
        results.daemon_warm_semantic_ms = 100.0
        results.baseline_fts_ms = 2200.0
        results.daemon_warm_fts_ms = 50.0
        results.baseline_hybrid_ms = 3500.0
        results.daemon_warm_hybrid_ms = 150.0
        results.rpc_overhead_ms = 5.0
        results.connection_time_ms = 30.0
        results.stability_success_count = 100
        results.stability_failure_count = 0
        results.memory_growth_mb = 20.0

        # Verify it's GO
        assert results.is_go() is True

        # Fail RPC overhead criterion
        results.rpc_overhead_ms = 150.0
        assert results.is_go() is False

    def test_is_go_all_criteria_fail(self):
        """Test is_go returns False when all criteria fail."""
        results = BenchmarkResults()

        # Set all values to fail criteria
        results.baseline_semantic_ms = 3000.0
        results.daemon_warm_semantic_ms = 2500.0  # Only 16.67% improvement

        results.baseline_fts_ms = 2200.0
        results.daemon_warm_fts_ms = 1000.0  # Only 54.55% improvement

        results.baseline_hybrid_ms = 3500.0
        results.daemon_warm_hybrid_ms = 4000.0  # Negative improvement

        results.rpc_overhead_ms = 150.0  # >100ms
        results.connection_time_ms = 200.0  # >100ms

        results.stability_success_count = 90
        results.stability_failure_count = 10  # Only 90% success

        results.memory_growth_mb = 200.0  # >100MB

        assert results.is_go() is False
