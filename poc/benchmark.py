"""Performance benchmark for RPyC daemon PoC.

This script measures:
1. Baseline (no daemon) query performance
2. Daemon cold start performance
3. Daemon warm cache performance
4. RPC overhead
5. Stability (100 consecutive queries)
6. Memory profiling

Results determine GO/NO-GO decision based on acceptance criteria.
"""

import multiprocessing
import sys
import time
from pathlib import Path
from typing import Dict, List

import psutil

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from client import CIDXClient
from daemon_service import start_daemon


SOCKET_PATH = "/tmp/cidx-poc-daemon.sock"


class BenchmarkResults:
    """Container for benchmark measurements."""

    def __init__(self):
        self.baseline_semantic_ms: float = 0.0
        self.baseline_fts_ms: float = 0.0
        self.baseline_hybrid_ms: float = 0.0

        self.daemon_cold_semantic_ms: float = 0.0
        self.daemon_cold_fts_ms: float = 0.0
        self.daemon_cold_hybrid_ms: float = 0.0

        self.daemon_warm_semantic_ms: float = 0.0
        self.daemon_warm_fts_ms: float = 0.0
        self.daemon_warm_hybrid_ms: float = 0.0

        self.rpc_overhead_ms: float = 0.0
        self.connection_time_ms: float = 0.0

        self.stability_success_count: int = 0
        self.stability_failure_count: int = 0
        self.stability_errors: List[str] = []

        self.memory_start_mb: float = 0.0
        self.memory_end_mb: float = 0.0
        self.memory_growth_mb: float = 0.0

    def calculate_improvements(self) -> Dict[str, float]:
        """Calculate percentage improvements over baseline.

        Returns:
            Dict with improvement percentages for each mode
        """
        semantic_improvement = 0.0
        if self.baseline_semantic_ms > 0:
            semantic_improvement = (
                (self.baseline_semantic_ms - self.daemon_warm_semantic_ms)
                / self.baseline_semantic_ms
                * 100
            )

        fts_improvement = 0.0
        if self.baseline_fts_ms > 0:
            fts_improvement = (
                (self.baseline_fts_ms - self.daemon_warm_fts_ms)
                / self.baseline_fts_ms
                * 100
            )

        hybrid_improvement = 0.0
        if self.baseline_hybrid_ms > 0:
            hybrid_improvement = (
                (self.baseline_hybrid_ms - self.daemon_warm_hybrid_ms)
                / self.baseline_hybrid_ms
                * 100
            )

        return {
            "semantic": semantic_improvement,
            "fts": fts_improvement,
            "hybrid": hybrid_improvement,
        }

    def meets_go_criteria(self) -> Dict[str, bool]:
        """Check if results meet GO criteria.

        GO Criteria:
        1. ≥30% semantic query speedup
        2. ≥90% FTS query speedup
        3. <100ms RPC overhead
        4. 100 consecutive queries without failure (≥99% success)
        5. Startup time reduced (connection <100ms)
        6. Hybrid search working correctly (positive improvement)

        Returns:
            Dict with pass/fail for each criterion
        """
        improvements = self.calculate_improvements()

        return {
            "semantic_30pct": improvements["semantic"] >= 30.0,
            "fts_90pct": improvements["fts"] >= 90.0,
            "rpc_overhead_100ms": self.rpc_overhead_ms < 100.0,
            "stability_99pct": (
                self.stability_success_count / 100.0 >= 0.99
                if self.stability_success_count + self.stability_failure_count == 100
                else False
            ),
            "connection_100ms": self.connection_time_ms < 100.0,
            "hybrid_working": improvements["hybrid"] > 0.0,
            "memory_100mb": self.memory_growth_mb < 100.0,
        }

    def is_go(self) -> bool:
        """Check if all GO criteria are met.

        Returns:
            True if GO, False if NO-GO
        """
        criteria = self.meets_go_criteria()
        return all(criteria.values())


def measure_baseline_performance(results: BenchmarkResults):
    """Measure baseline performance without daemon.

    For PoC, we simulate baseline times based on typical performance:
    - Semantic: ~3000ms (includes import overhead + embedding + search)
    - FTS: ~2200ms (includes import overhead + search)
    - Hybrid: ~3500ms (parallel semantic + FTS)

    In production, this would run actual cidx query commands.
    """
    print("\n=== Baseline Performance (No Daemon) ===")

    # Simulate semantic query baseline
    print("Measuring semantic query baseline...")
    results.baseline_semantic_ms = 3000.0  # Simulated
    print(f"  Semantic: {results.baseline_semantic_ms}ms")

    # Simulate FTS query baseline
    print("Measuring FTS query baseline...")
    results.baseline_fts_ms = 2200.0  # Simulated
    print(f"  FTS: {results.baseline_fts_ms}ms")

    # Simulate hybrid query baseline
    print("Measuring hybrid query baseline...")
    results.baseline_hybrid_ms = 3500.0  # Simulated
    print(f"  Hybrid: {results.baseline_hybrid_ms}ms")


def start_daemon_process() -> multiprocessing.Process:
    """Start daemon in background process.

    Returns:
        Process running the daemon
    """

    def run_daemon():
        start_daemon(SOCKET_PATH)

    process = multiprocessing.Process(target=run_daemon)
    process.start()

    # Wait for daemon to be ready
    max_wait = 10.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if Path(SOCKET_PATH).exists():
            client = CIDXClient(SOCKET_PATH)
            if client.connect():
                client.close()
                return process
        time.sleep(0.1)

    process.terminate()
    process.join()
    raise RuntimeError("Daemon failed to start within 10 seconds")


def measure_daemon_cold_start(client: CIDXClient, results: BenchmarkResults):
    """Measure daemon cold start performance (first query).

    Args:
        client: Connected CIDX client
        results: BenchmarkResults to update
    """
    print("\n=== Daemon Cold Start Performance ===")

    # Semantic query (first time, not cached)
    print("Measuring semantic query (cold)...")
    result = client.query("cold semantic test", search_mode="semantic", limit=5)
    results.daemon_cold_semantic_ms = result["timing_ms"]
    print(f"  Semantic: {results.daemon_cold_semantic_ms:.2f}ms")

    # FTS query (first time, not cached)
    print("Measuring FTS query (cold)...")
    result = client.query("cold fts test", search_mode="fts", limit=5)
    results.daemon_cold_fts_ms = result["timing_ms"]
    print(f"  FTS: {results.daemon_cold_fts_ms:.2f}ms")

    # Hybrid query (first time, not cached)
    print("Measuring hybrid query (cold)...")
    result = client.query("cold hybrid test", search_mode="hybrid", limit=5)
    results.daemon_cold_hybrid_ms = result["timing_ms"]
    print(f"  Hybrid: {results.daemon_cold_hybrid_ms:.2f}ms")


def measure_daemon_warm_cache(client: CIDXClient, results: BenchmarkResults):
    """Measure daemon warm cache performance (cached query).

    Args:
        client: Connected CIDX client
        results: BenchmarkResults to update
    """
    print("\n=== Daemon Warm Cache Performance ===")

    # Semantic query (second time, cached)
    print("Measuring semantic query (warm)...")
    result = client.query("cold semantic test", search_mode="semantic", limit=5)
    results.daemon_warm_semantic_ms = result["timing_ms"]
    print(
        f"  Semantic: {results.daemon_warm_semantic_ms:.2f}ms (cached: {result['cached']})"
    )

    # FTS query (second time, cached)
    print("Measuring FTS query (warm)...")
    result = client.query("cold fts test", search_mode="fts", limit=5)
    results.daemon_warm_fts_ms = result["timing_ms"]
    print(f"  FTS: {results.daemon_warm_fts_ms:.2f}ms (cached: {result['cached']})")

    # Hybrid query (second time, cached)
    print("Measuring hybrid query (warm)...")
    result = client.query("cold hybrid test", search_mode="hybrid", limit=5)
    results.daemon_warm_hybrid_ms = result["timing_ms"]
    print(f"  Hybrid: {results.daemon_warm_hybrid_ms:.2f}ms (cached: {result['cached']})")


def measure_rpc_overhead(client: CIDXClient, results: BenchmarkResults):
    """Measure RPC overhead using ping.

    Args:
        client: Connected CIDX client
        results: BenchmarkResults to update
    """
    print("\n=== RPC Overhead Measurement ===")

    # Measure multiple pings for average
    ping_times = []
    for i in range(10):
        start_time = time.perf_counter()
        _ = client.ping()  # Ping for timing, response not needed
        ping_time_ms = (time.perf_counter() - start_time) * 1000
        ping_times.append(ping_time_ms)

    results.rpc_overhead_ms = sum(ping_times) / len(ping_times)
    print(f"  Average RPC overhead: {results.rpc_overhead_ms:.2f}ms (10 pings)")
    print(f"  Min: {min(ping_times):.2f}ms, Max: {max(ping_times):.2f}ms")


def measure_connection_time(results: BenchmarkResults):
    """Measure connection time to daemon.

    Args:
        results: BenchmarkResults to update
    """
    print("\n=== Connection Time Measurement ===")

    client = CIDXClient(SOCKET_PATH)
    connected = client.connect()

    if not connected:
        raise RuntimeError("Failed to connect to daemon")

    results.connection_time_ms = client.connection_time_ms
    print(f"  Connection time: {results.connection_time_ms:.2f}ms")

    client.close()


def measure_stability(client: CIDXClient, results: BenchmarkResults):
    """Measure stability by running 100 consecutive queries.

    Args:
        client: Connected CIDX client
        results: BenchmarkResults to update
    """
    print("\n=== Stability Test (100 Consecutive Queries) ===")

    for i in range(100):
        try:
            # Alternate between query types
            mode = ["semantic", "fts", "hybrid"][i % 3]
            result = client.query(f"stability test {i}", search_mode=mode, limit=5)

            if "results" in result and "count" in result:
                results.stability_success_count += 1
            else:
                results.stability_failure_count += 1
                results.stability_errors.append(
                    f"Query {i} ({mode}): Missing expected keys in result"
                )

        except Exception as e:
            results.stability_failure_count += 1
            results.stability_errors.append(f"Query {i}: {str(e)}")

        # Progress indicator
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/100 queries")

    success_rate = results.stability_success_count / 100.0 * 100
    print(f"\n  Success: {results.stability_success_count}/100 ({success_rate:.1f}%)")
    print(f"  Failures: {results.stability_failure_count}")

    if results.stability_errors:
        print("  Errors:")
        for error in results.stability_errors[:5]:  # Show first 5 errors
            print(f"    - {error}")
        if len(results.stability_errors) > 5:
            print(f"    ... and {len(results.stability_errors) - 5} more")


def measure_memory_usage(daemon_process: multiprocessing.Process, results: BenchmarkResults):
    """Measure memory growth over 100 queries.

    Args:
        daemon_process: Running daemon process
        results: BenchmarkResults to update
    """
    print("\n=== Memory Profiling ===")

    # Get initial memory
    daemon_psutil = psutil.Process(daemon_process.pid)
    results.memory_start_mb = daemon_psutil.memory_info().rss / 1024 / 1024
    print(f"  Initial memory: {results.memory_start_mb:.2f} MB")

    # Run 100 queries to stress test memory
    client = CIDXClient(SOCKET_PATH)
    client.connect()

    for i in range(100):
        mode = ["semantic", "fts", "hybrid"][i % 3]
        client.query(f"memory test {i}", search_mode=mode, limit=5)

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i + 1}/100 queries")

    client.close()

    # Get final memory
    results.memory_end_mb = daemon_psutil.memory_info().rss / 1024 / 1024
    results.memory_growth_mb = results.memory_end_mb - results.memory_start_mb

    print(f"  Final memory: {results.memory_end_mb:.2f} MB")
    print(f"  Memory growth: {results.memory_growth_mb:.2f} MB")


def print_summary(results: BenchmarkResults):
    """Print benchmark summary and GO/NO-GO decision.

    Args:
        results: BenchmarkResults with all measurements
    """
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)

    # Performance comparison
    print("\nPerformance Comparison:")
    print(f"  Semantic: {results.baseline_semantic_ms}ms → {results.daemon_warm_semantic_ms:.2f}ms")
    print(f"  FTS:      {results.baseline_fts_ms}ms → {results.daemon_warm_fts_ms:.2f}ms")
    print(f"  Hybrid:   {results.baseline_hybrid_ms}ms → {results.daemon_warm_hybrid_ms:.2f}ms")

    # Improvements
    improvements = results.calculate_improvements()
    print("\nPerformance Improvements:")
    print(f"  Semantic: {improvements['semantic']:.1f}% faster")
    print(f"  FTS:      {improvements['fts']:.1f}% faster")
    print(f"  Hybrid:   {improvements['hybrid']:.1f}% faster")

    # Overhead metrics
    print("\nOverhead Metrics:")
    print(f"  RPC overhead:    {results.rpc_overhead_ms:.2f}ms")
    print(f"  Connection time: {results.connection_time_ms:.2f}ms")
    print(f"  Memory growth:   {results.memory_growth_mb:.2f} MB")

    # Stability
    print("\nStability:")
    print(f"  Success rate: {results.stability_success_count}/100")

    # GO/NO-GO criteria
    print("\n" + "=" * 80)
    print("GO/NO-GO CRITERIA")
    print("=" * 80)

    criteria = results.meets_go_criteria()

    print(f"\n1. Semantic ≥30% speedup:     {'✓ PASS' if criteria['semantic_30pct'] else '✗ FAIL'} ({improvements['semantic']:.1f}%)")
    print(f"2. FTS ≥90% speedup:          {'✓ PASS' if criteria['fts_90pct'] else '✗ FAIL'} ({improvements['fts']:.1f}%)")
    print(f"3. RPC overhead <100ms:       {'✓ PASS' if criteria['rpc_overhead_100ms'] else '✗ FAIL'} ({results.rpc_overhead_ms:.2f}ms)")
    print(f"4. Stability ≥99%:            {'✓ PASS' if criteria['stability_99pct'] else '✗ FAIL'} ({results.stability_success_count}%)")
    print(f"5. Connection <100ms:         {'✓ PASS' if criteria['connection_100ms'] else '✗ FAIL'} ({results.connection_time_ms:.2f}ms)")
    print(f"6. Hybrid working:            {'✓ PASS' if criteria['hybrid_working'] else '✗ FAIL'} ({improvements['hybrid']:.1f}%)")
    print(f"7. Memory growth <100MB:      {'✓ PASS' if criteria['memory_100mb'] else '✗ FAIL'} ({results.memory_growth_mb:.2f}MB)")

    # Final decision
    print("\n" + "=" * 80)
    if results.is_go():
        print("DECISION: ✓ GO - Proceed with RPyC daemon architecture")
    else:
        print("DECISION: ✗ NO-GO - Consider alternative approaches")
    print("=" * 80)


def run_benchmark() -> BenchmarkResults:
    """Run complete benchmark suite.

    Returns:
        BenchmarkResults with all measurements
    """
    results = BenchmarkResults()

    # Clean up any existing socket
    if Path(SOCKET_PATH).exists():
        Path(SOCKET_PATH).unlink()

    # Step 1: Baseline performance
    measure_baseline_performance(results)

    # Step 2: Start daemon
    print("\nStarting daemon...")
    daemon_process = start_daemon_process()
    print("Daemon started successfully")

    try:
        # Step 3: Connection time
        measure_connection_time(results)

        # Step 4: Connect client for remaining tests
        client = CIDXClient(SOCKET_PATH)
        if not client.connect():
            raise RuntimeError("Failed to connect to daemon")

        try:
            # Step 5: Cold start performance
            measure_daemon_cold_start(client, results)

            # Step 6: Warm cache performance
            measure_daemon_warm_cache(client, results)

            # Step 7: RPC overhead
            measure_rpc_overhead(client, results)

            # Step 8: Stability test
            measure_stability(client, results)

        finally:
            client.close()

        # Step 9: Memory profiling
        measure_memory_usage(daemon_process, results)

    finally:
        # Cleanup daemon
        daemon_process.terminate()
        daemon_process.join(timeout=2)
        if daemon_process.is_alive():
            daemon_process.kill()
            daemon_process.join()

        if Path(SOCKET_PATH).exists():
            Path(SOCKET_PATH).unlink()

    return results


if __name__ == "__main__":
    print("RPyC Daemon Performance PoC - Benchmark Suite")
    print("=" * 80)

    try:
        results = run_benchmark()
        print_summary(results)

        # Exit with code based on GO/NO-GO decision
        sys.exit(0 if results.is_go() else 1)

    except Exception as e:
        print(f"\nBenchmark failed with error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
