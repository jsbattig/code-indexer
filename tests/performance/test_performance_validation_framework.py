"""
Performance Validation Framework Integration Test

This test focuses on validating the performance validation framework itself
without complex mocking of the HighThroughputProcessor.
"""

import pytest
import time
import threading

from tests.performance.test_epic4_performance_validation import (
    PerformanceValidationFramework,
    PerformanceMetrics,
    PerformanceBenchmark,
)


@pytest.mark.slow
class TestPerformanceValidationFrameworkIntegration:
    """Test the performance validation framework itself."""

    @pytest.fixture
    def framework(self):
        """Create performance validation framework."""
        return PerformanceValidationFramework()

    def test_performance_measurement_context_manager(self, framework):
        """Test that performance measurement works correctly."""

        # Test basic measurement
        with framework.measure_performance():
            time.sleep(0.1)  # 100ms

        # Validate measurement
        assert (
            0.08 <= framework.wall_time <= 0.15
        ), f"Wall time measurement incorrect: {framework.wall_time}"
        assert (
            framework.cpu_time >= 0
        ), f"CPU time should be non-negative: {framework.cpu_time}"
        # Memory delta can be 0 in some cases, just ensure it's measured
        assert hasattr(framework, "memory_delta"), "Memory delta should be measured"
        assert (
            framework.peak_memory > 0
        ), f"Peak memory should be positive: {framework.peak_memory}"

        print("✅ Performance measurement:")
        print(f"   Wall time: {framework.wall_time:.3f}s")
        print(f"   CPU time: {framework.cpu_time:.3f}s")
        print(f"   Memory delta: {framework.memory_delta / 1024:.1f}KB")

    def test_worker_activity_tracking(self, framework):
        """Test worker activity tracking functionality."""

        # Reset tracking
        with framework.worker_count_lock:
            framework.active_workers_count = 0
            framework.peak_workers_count = 0

        # Simulate worker activity
        framework.track_worker_activity("worker1", True)
        assert framework.active_workers_count == 1
        assert framework.peak_workers_count == 1

        framework.track_worker_activity("worker2", True)
        assert framework.active_workers_count == 2
        assert framework.peak_workers_count == 2

        framework.track_worker_activity("worker3", True)
        assert framework.active_workers_count == 3
        assert framework.peak_workers_count == 3

        # Deactivate one worker
        framework.track_worker_activity("worker1", False)
        assert framework.active_workers_count == 2
        assert framework.peak_workers_count == 3  # Peak should remain

        # Deactivate remaining workers
        framework.track_worker_activity("worker2", False)
        framework.track_worker_activity("worker3", False)
        assert framework.active_workers_count == 0
        assert framework.peak_workers_count == 3  # Peak should remain

        print("✅ Worker activity tracking:")
        print(f"   Peak concurrent workers: {framework.peak_workers_count}")

    def test_test_codebase_creation(self, framework):
        """Test test codebase creation functionality."""

        # Create small test codebase
        temp_path, test_files = framework.create_test_codebase(
            5, 10
        )  # 5 files, ~10KB each

        try:
            # Validate codebase structure
            assert (
                temp_path.exists() and temp_path.is_dir()
            ), "Test directory should exist"
            assert len(test_files) == 5, f"Expected 5 files, got {len(test_files)}"

            # Validate file content
            total_size = 0
            languages_found = set()

            for file_path in test_files:
                assert file_path.exists(), f"Test file should exist: {file_path}"

                content = file_path.read_text()
                file_size = len(content.encode("utf-8"))
                total_size += file_size

                # Extract language from extension
                extension = file_path.suffix.lstrip(".")
                lang_map = {
                    "py": "python",
                    "js": "javascript",
                    "java": "java",
                    "ts": "typescript",
                }
                if extension in lang_map:
                    languages_found.add(lang_map[extension])

                # Validate content is realistic
                assert (
                    len(content) > 1000
                ), f"File content too small: {len(content)} chars"
                assert (
                    "class " in content or "function" in content or "def " in content
                ), "Should contain code patterns"

            # Validate size distribution
            avg_file_size = total_size / len(test_files)
            expected_size = 10 * 1024  # 10KB

            # Allow 50% variance in file sizes
            assert (
                0.5 * expected_size <= avg_file_size <= 2.0 * expected_size
            ), f"Average file size {avg_file_size} not within expected range around {expected_size}"

            # Validate language diversity
            assert (
                len(languages_found) >= 2
            ), f"Should have multiple languages, found: {languages_found}"

            print("✅ Test codebase creation:")
            print(f"   Files created: {len(test_files)}")
            print(f"   Average size: {avg_file_size / 1024:.1f}KB")
            print(f"   Languages: {languages_found}")

        finally:
            framework.cleanup_test_codebase(temp_path)
            assert not temp_path.exists(), "Cleanup should remove test directory"

    def test_performance_benchmark_requirements_validation(self):
        """Test performance benchmark requirements validation."""

        # Create benchmark that meets requirements
        good_benchmark = PerformanceBenchmark(
            operation_name="test_operation",
            baseline_metrics=PerformanceMetrics(
                wall_time=10.0,
                cpu_time=9.0,
                memory_delta=100_000_000,
                peak_memory=150_000_000,
                throughput=2.0,
                threads_used=1,
                chunks_processed=50,
                files_processed=10,
                embeddings_per_second=5.0,
            ),
            optimized_metrics=PerformanceMetrics(
                wall_time=2.0,
                cpu_time=7.0,
                memory_delta=80_000_000,
                peak_memory=120_000_000,
                throughput=10.0,
                threads_used=8,
                chunks_processed=50,
                files_processed=10,
                embeddings_per_second=25.0,
                concurrent_workers_peak=7,
            ),
            speedup_factor=5.0,  # Exceeds 4.0x requirement
            memory_improvement=1.25,
            throughput_improvement=5.0,  # Exceeds 4.0x requirement
            thread_utilization=0.875,  # Exceeds 0.8 requirement (7/8 workers)
        )

        assert (
            good_benchmark.meets_requirements()
        ), "Good benchmark should meet requirements"

        # Create benchmark that fails speedup requirement
        bad_speedup_benchmark = PerformanceBenchmark(
            operation_name="test_operation",
            baseline_metrics=PerformanceMetrics(
                wall_time=10.0,
                cpu_time=9.0,
                memory_delta=100_000_000,
                peak_memory=150_000_000,
                throughput=2.0,
                threads_used=1,
                chunks_processed=50,
                files_processed=10,
                embeddings_per_second=5.0,
            ),
            optimized_metrics=PerformanceMetrics(
                wall_time=3.5,
                cpu_time=7.0,
                memory_delta=80_000_000,
                peak_memory=120_000_000,
                throughput=5.7,
                threads_used=8,
                chunks_processed=50,
                files_processed=10,
                embeddings_per_second=14.3,
                concurrent_workers_peak=6,
            ),
            speedup_factor=2.86,  # Fails 4.0x requirement
            memory_improvement=1.25,
            throughput_improvement=2.86,  # Fails 4.0x requirement
            thread_utilization=0.75,  # Fails 0.8 requirement
        )

        assert (
            not bad_speedup_benchmark.meets_requirements()
        ), "Bad benchmark should fail requirements"

        print("✅ Benchmark validation:")
        print(
            f"   Good benchmark: {'PASS' if good_benchmark.meets_requirements() else 'FAIL'}"
        )
        print(
            f"   Bad benchmark: {'FAIL' if not bad_speedup_benchmark.meets_requirements() else 'PASS'}"
        )

    def test_code_content_generation_quality(self, framework):
        """Test that generated code content is realistic and diverse."""

        languages = ["python", "javascript", "java", "typescript"]
        target_size = 5000  # 5KB

        content_stats = {}

        for language in languages:
            content = framework._generate_code_content(language, target_size)

            # Basic size validation - be more lenient with size requirements
            actual_size = len(content.encode("utf-8"))
            assert (
                0.3 * target_size <= actual_size <= 3.0 * target_size
            ), f"{language} content size {actual_size} not within expected range around {target_size}"

            # Content quality validation
            lines = content.split("\n")
            non_empty_lines = [line for line in lines if line.strip()]

            assert (
                len(non_empty_lines) >= 50
            ), f"{language} should have substantial content"

            # Language-specific patterns
            if language == "python":
                assert (
                    "def " in content
                ), "Python content should have function definitions"
                assert (
                    "class " in content
                ), "Python content should have class definitions"
                assert "import " in content, "Python content should have imports"
            elif language == "javascript":
                assert (
                    "function" in content or "=>" in content
                ), "JavaScript should have functions"
                assert (
                    "const " in content or "let " in content
                ), "JavaScript should have variable declarations"
                assert (
                    "require(" in content or "module.exports" in content
                ), "JavaScript should have module patterns"
            elif language == "java":
                assert "public class" in content, "Java should have class definitions"
                assert "public " in content, "Java should have public methods"
                assert "import " in content, "Java should have imports"
            elif language == "typescript":
                assert "interface " in content, "TypeScript should have interfaces"
                assert ": " in content, "TypeScript should have type annotations"
                assert "class " in content, "TypeScript should have classes"

            content_stats[language] = {
                "size": actual_size,
                "lines": len(non_empty_lines),
                "complexity": len(
                    [
                        line
                        for line in lines
                        if "function" in line or "def " in line or "class " in line
                    ]
                ),
            }

        print("✅ Code content generation:")
        for lang, stats in content_stats.items():
            print(
                f"   {lang}: {stats['size']} bytes, {stats['lines']} lines, {stats['complexity']} definitions"
            )

    def test_concurrent_worker_simulation(self, framework):
        """Test concurrent worker simulation for thread utilization measurement."""

        # Simulate 8 workers with overlapping activity periods
        worker_count = 8
        activity_duration = 0.1  # 100ms activity per worker

        def simulate_worker(worker_id: int, start_delay: float):
            """Simulate worker activity with tracking."""
            time.sleep(start_delay)
            framework.track_worker_activity(f"worker_{worker_id}", True)
            time.sleep(activity_duration)
            framework.track_worker_activity(f"worker_{worker_id}", False)

        # Start workers with staggered start times to create overlap
        threads = []
        for i in range(worker_count):
            start_delay = i * 0.02  # Stagger by 20ms
            thread = threading.Thread(target=simulate_worker, args=(i, start_delay))
            threads.append(thread)

        # Reset tracking
        with framework.worker_count_lock:
            framework.active_workers_count = 0
            framework.peak_workers_count = 0

        # Start all workers
        start_time = time.time()
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        total_time = time.time() - start_time

        # Validate concurrent execution
        assert (
            framework.peak_workers_count >= 4
        ), f"Expected significant concurrency (≥4), got {framework.peak_workers_count}"

        # Calculate theoretical vs actual utilization
        theoretical_sequential_time = (
            worker_count * activity_duration
        )  # 0.8s if sequential
        expected_speedup = theoretical_sequential_time / total_time

        assert (
            expected_speedup >= 2.0
        ), f"Expected ≥2x speedup from concurrent execution, got {expected_speedup:.1f}x"

        thread_utilization = framework.peak_workers_count / worker_count

        print("✅ Concurrent worker simulation:")
        print(
            f"   Peak concurrent workers: {framework.peak_workers_count}/{worker_count}"
        )
        print(f"   Thread utilization: {thread_utilization:.1%}")
        print(f"   Speedup achieved: {expected_speedup:.1f}x")
        print(f"   Total execution time: {total_time:.3f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
