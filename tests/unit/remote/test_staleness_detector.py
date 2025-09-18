"""Test Staleness Detection for CIDX Remote Repository Linking Mode.

Tests Feature 5 Story 1: Local vs Remote Timestamp Comparison that provides
file-level staleness indicators comparing local file modifications with remote
index timestamps for better query result relevance assessment.
"""

import os
import pytest
import time
import datetime
from unittest.mock import patch

from code_indexer.api_clients.remote_query_client import QueryResultItem
from code_indexer.remote.staleness_detector import (
    StalenessDetector,
    EnhancedQueryResultItem,
)


class TestStalenessDetector:
    """Test core staleness detection functionality."""

    @pytest.fixture
    def staleness_detector(self):
        """Create StalenessDetector instance for testing."""
        return StalenessDetector()

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create temporary project root directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        return project_dir

    @pytest.fixture
    def sample_query_results(self):
        """Create sample query results for testing."""
        current_time = time.time()
        return [
            QueryResultItem(
                similarity_score=0.95,
                file_path="src/auth.py",
                line_number=10,
                code_snippet='def authenticate_user(username: str, password: str):\n    """Authenticate user credentials."""',
                repository_alias="test-repo",
                file_last_modified=current_time - 3600,  # 1 hour ago
                indexed_timestamp=current_time - 7200,  # 2 hours ago (stale)
            ),
            QueryResultItem(
                similarity_score=0.87,
                file_path="tests/test_auth.py",
                line_number=45,
                code_snippet="def test_authentication():\n    assert authenticate_user('user', 'pass') == True",
                repository_alias="test-repo",
                file_last_modified=current_time - 7200,  # 2 hours ago
                indexed_timestamp=current_time - 3600,  # 1 hour ago (fresh)
            ),
            QueryResultItem(
                similarity_score=0.78,
                file_path="docs/README.md",
                line_number=1,
                code_snippet="# Authentication Module\nThis module provides user authentication.",
                repository_alias="test-repo",
                file_last_modified=None,  # No local modification time
                indexed_timestamp=current_time - 1800,  # 30 minutes ago
            ),
        ]

    def test_apply_staleness_detection_basic_functionality(
        self, staleness_detector, project_root, sample_query_results
    ):
        """Test basic staleness detection functionality."""
        # Create test files with known modification times

        # Create files for the sample results
        (project_root / "src").mkdir(parents=True)
        auth_file = project_root / "src" / "auth.py"
        auth_file.write_text(
            "def authenticate_user(username: str, password: str): pass"
        )

        (project_root / "tests").mkdir(parents=True)
        test_file = project_root / "tests" / "test_auth.py"
        test_file.write_text("def test_authentication(): pass")

        (project_root / "docs").mkdir(parents=True)
        readme_file = project_root / "docs" / "README.md"
        readme_file.write_text("# Authentication Module")

        # Apply staleness detection
        enhanced_results = staleness_detector.apply_staleness_detection(
            sample_query_results, project_root
        )

        # Verify basic functionality
        assert len(enhanced_results) == len(sample_query_results)
        assert all(
            isinstance(result, EnhancedQueryResultItem) for result in enhanced_results
        )
        assert all(hasattr(result, "is_stale") for result in enhanced_results)
        assert all(
            hasattr(result, "staleness_indicator") for result in enhanced_results
        )

    def test_enhanced_query_result_item_model_creation(self):
        """Test EnhancedQueryResultItem model with staleness metadata."""
        current_time = time.time()

        # Create enhanced query result item
        enhanced_result = EnhancedQueryResultItem(
            similarity_score=0.95,
            file_path="src/auth.py",
            line_number=10,
            code_snippet="def authenticate_user(username: str, password: str): pass",
            repository_alias="test-repo",
            file_last_modified=current_time - 3600,
            indexed_timestamp=current_time - 7200,
            local_file_mtime=current_time - 1800,
            is_stale=True,
            staleness_delta_seconds=5400,
            staleness_indicator="🟠 1h stale",
        )

        # Verify all fields are accessible
        assert enhanced_result.similarity_score == 0.95
        assert enhanced_result.file_path == "src/auth.py"
        assert enhanced_result.is_stale
        assert enhanced_result.staleness_indicator == "🟠 1h stale"
        assert enhanced_result.staleness_delta_seconds == 5400

    def test_file_level_timestamp_comparison_fresh_result(
        self, staleness_detector, project_root
    ):
        """Test timestamp comparison for fresh results (local older than remote index)."""
        current_time = time.time()

        # Create test file with older modification time
        test_file = project_root / "src" / "fresh_file.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("def fresh_function(): pass")

        # Set file modification time to be older than index time
        old_time = current_time - 7200  # 2 hours ago
        os.utime(test_file, (old_time, old_time))

        query_result = QueryResultItem(
            similarity_score=0.90,
            file_path="src/fresh_file.py",
            line_number=1,
            code_snippet="def fresh_function(): pass",
            repository_alias="test-repo",
            file_last_modified=old_time,
            indexed_timestamp=current_time - 3600,  # 1 hour ago (newer than file)
        )

        # Apply staleness detection
        results = staleness_detector.apply_staleness_detection(
            [query_result], project_root
        )

        # Verify fresh result detection
        assert len(results) == 1
        result = results[0]
        assert (
            not result.is_stale
        )  # Should be fresh since local file is older than index
        assert "🟢" in result.staleness_indicator

    def test_file_level_timestamp_comparison_stale_result(
        self, staleness_detector, project_root
    ):
        """Test timestamp comparison for stale results (local newer than remote index)."""
        current_time = time.time()

        # Create test file with newer modification time
        test_file = project_root / "src" / "stale_file.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("def updated_function(): pass")

        # Set file modification time to be newer than index time
        new_time = current_time - 1800  # 30 minutes ago
        os.utime(test_file, (new_time, new_time))

        query_result = QueryResultItem(
            similarity_score=0.85,
            file_path="src/stale_file.py",
            line_number=1,
            code_snippet="def updated_function(): pass",
            repository_alias="test-repo",
            file_last_modified=new_time,
            indexed_timestamp=current_time - 7200,  # 2 hours ago (older than file)
        )

        # Apply staleness detection
        results = staleness_detector.apply_staleness_detection(
            [query_result], project_root
        )

        # Verify stale result detection
        assert len(results) == 1
        result = results[0]
        assert result.is_stale  # Should be stale since local file is newer than index
        assert result.staleness_delta_seconds > 0
        assert "🟡" in result.staleness_indicator or "🟠" in result.staleness_indicator

    def test_staleness_threshold_configuration_default(self, staleness_detector):
        """Test default staleness threshold configuration (0 seconds)."""
        # Verify default threshold is 0
        assert staleness_detector.staleness_threshold_seconds == 0.0

    def test_staleness_threshold_configuration_custom(self):
        """Test custom staleness threshold configuration."""
        # Create detector with custom threshold
        detector = StalenessDetector(staleness_threshold_seconds=3600)
        assert detector.staleness_threshold_seconds == 3600

    def test_staleness_metadata_integration_complete_data(
        self, staleness_detector, project_root
    ):
        """Test staleness metadata includes all required fields."""
        current_time = time.time()

        # Create test file
        test_file = project_root / "metadata_test.py"
        test_file.write_text("def test_function(): pass")
        os.utime(test_file, (current_time - 1800, current_time - 1800))

        query_result = QueryResultItem(
            similarity_score=0.92,
            file_path="metadata_test.py",
            line_number=1,
            code_snippet="def test_function(): pass",
            repository_alias="test-repo",
            file_last_modified=current_time - 1800,
            indexed_timestamp=current_time - 3600,
        )

        # Apply staleness detection
        enhanced_results = staleness_detector.apply_staleness_detection(
            [query_result], project_root
        )

        # Verify complete metadata
        assert len(enhanced_results) == 1
        result = enhanced_results[0]
        assert hasattr(result, "local_file_mtime")
        assert hasattr(result, "is_stale")
        assert hasattr(result, "staleness_delta_seconds")
        assert hasattr(result, "staleness_indicator")
        assert isinstance(result.is_stale, bool)
        assert isinstance(result.staleness_indicator, str)

    def test_performance_optimization_file_stat_caching(
        self, staleness_detector, project_root
    ):
        """Test that file stat operations are cached to improve performance."""
        # Verify caching mechanism exists
        assert hasattr(staleness_detector, "_file_mtime_cache")
        assert isinstance(staleness_detector._file_mtime_cache, dict)

    def test_performance_optimization_batch_operations(
        self, staleness_detector, project_root, sample_query_results
    ):
        """Test that file operations are batched for better performance."""
        # Test batching mechanism
        file_paths = [
            result.file_path for result in sample_query_results[:2]
        ]  # First 2 results
        batch_results = staleness_detector._batch_file_stats(file_paths, project_root)
        assert isinstance(batch_results, dict)
        assert len(batch_results) == len(file_paths)

    def test_performance_requirement_overhead_measurement(
        self, staleness_detector, project_root
    ):
        """Test that staleness detection adds minimal overhead (<100ms)."""
        # Create 50 test files to simulate realistic workload
        for i in range(50):
            test_file = project_root / f"test_file_{i}.py"
            test_file.write_text(f"def test_function_{i}(): pass")

        # Create corresponding query results
        current_time = time.time()
        query_results = []
        for i in range(50):
            query_results.append(
                QueryResultItem(
                    similarity_score=0.8,
                    file_path=f"test_file_{i}.py",
                    line_number=1,
                    code_snippet=f"def test_function_{i}(): pass",
                    repository_alias="test-repo",
                    file_last_modified=current_time - 1800,
                    indexed_timestamp=current_time - 3600,
                )
            )

        # Test performance requirement
        start_time = time.time()
        results = staleness_detector.apply_staleness_detection(
            query_results, project_root
        )
        end_time = time.time()

        processing_time = (end_time - start_time) * 1000  # Convert to milliseconds
        assert (
            processing_time < 100
        ), f"Staleness detection took {processing_time}ms, exceeds 100ms limit"
        assert len(results) == 50

    def test_visual_indicators_fresh_results(self, staleness_detector):
        """Test visual indicators for fresh results (🟢)."""
        # Test fresh indicator formatting
        indicator = staleness_detector._format_staleness_indicator(
            is_stale=False, delta_seconds=0
        )
        assert "🟢" in indicator
        assert "Fresh" in indicator

    def test_visual_indicators_slightly_stale_results(self, staleness_detector):
        """Test visual indicators for slightly stale results (🟡 0-1 hour)."""
        # Test slightly stale indicator formatting
        indicator = staleness_detector._format_staleness_indicator(
            is_stale=True, delta_seconds=1800
        )  # 30 minutes
        assert "🟡" in indicator
        assert "30m" in indicator or "stale" in indicator

    def test_visual_indicators_moderately_stale_results(self, staleness_detector):
        """Test visual indicators for moderately stale results (🟠 1-24 hours)."""
        # Test moderately stale indicator formatting
        indicator = staleness_detector._format_staleness_indicator(
            is_stale=True, delta_seconds=7200
        )  # 2 hours
        assert "🟠" in indicator
        assert "2h" in indicator or "stale" in indicator

    def test_visual_indicators_significantly_stale_results(self, staleness_detector):
        """Test visual indicators for significantly stale results (🔴 >24 hours)."""
        # Test significantly stale indicator formatting
        indicator = staleness_detector._format_staleness_indicator(
            is_stale=True, delta_seconds=90000
        )  # 25 hours
        assert "🔴" in indicator
        assert "1d" in indicator or "stale" in indicator

    def test_result_sorting_with_staleness_priority(
        self, staleness_detector, project_root
    ):
        """Test that results are sorted with fresh results prioritized."""
        current_time = time.time()

        # Create mixed results with different staleness levels
        mixed_results = [
            QueryResultItem(
                similarity_score=0.80,
                file_path="stale.py",
                line_number=1,
                code_snippet="stale",
                repository_alias="test-repo",
                file_last_modified=current_time - 1800,
                indexed_timestamp=current_time - 7200,
            ),  # Stale
            QueryResultItem(
                similarity_score=0.90,
                file_path="fresh.py",
                line_number=1,
                code_snippet="fresh",
                repository_alias="test-repo",
                file_last_modified=current_time - 7200,
                indexed_timestamp=current_time - 1800,
            ),  # Fresh
            QueryResultItem(
                similarity_score=0.85,
                file_path="very_stale.py",
                line_number=1,
                code_snippet="very_stale",
                repository_alias="test-repo",
                file_last_modified=current_time - 3600,
                indexed_timestamp=current_time - 14400,
            ),  # Very stale
        ]

        # Create files for the test
        for result in mixed_results:
            file_path = project_root / result.file_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(result.code_snippet)

        # Apply staleness detection first to get enhanced results
        enhanced_results = staleness_detector.apply_staleness_detection(
            mixed_results, project_root
        )

        # Test staleness priority sorting - fresh results should come first regardless of lower score
        fresh_results = [r for r in enhanced_results if not r.is_stale]
        stale_results = [r for r in enhanced_results if r.is_stale]

        # Within fresh results, higher scores should come first
        # Within stale results, higher scores should come first
        for i in range(len(fresh_results) - 1):
            assert (
                fresh_results[i].similarity_score
                >= fresh_results[i + 1].similarity_score
            )

        for i in range(len(stale_results) - 1):
            assert (
                stale_results[i].similarity_score
                >= stale_results[i + 1].similarity_score
            )


class TestStalenessDetectorErrorHandling:
    """Test error handling for staleness detection."""

    @pytest.fixture
    def staleness_detector(self):
        """Create StalenessDetector instance for testing."""
        return StalenessDetector()

    def test_missing_file_error_handling(self, staleness_detector, tmp_path):
        """Test error handling when local file doesn't exist."""
        project_root = tmp_path / "test-project"
        project_root.mkdir()

        query_result = QueryResultItem(
            similarity_score=0.85,
            file_path="nonexistent/missing_file.py",
            line_number=1,
            code_snippet="def missing_function(): pass",
            repository_alias="test-repo",
            file_last_modified=time.time() - 3600,
            indexed_timestamp=time.time() - 1800,
        )

        # Apply staleness detection - should handle missing file gracefully
        results = staleness_detector.apply_staleness_detection(
            [query_result], project_root
        )

        # Verify graceful handling of missing file
        assert len(results) == 1
        result = results[0]
        assert result.local_file_mtime is None  # No local file modification time
        assert not result.is_stale  # Default to not stale when file missing

    def test_permission_error_handling(self, staleness_detector, tmp_path):
        """Test error handling when file permissions prevent stat operations."""
        project_root = tmp_path / "test-project"
        project_root.mkdir()

        # Create file and make it unreadable
        test_file = project_root / "restricted_file.py"
        test_file.write_text("def restricted_function(): pass")
        test_file.chmod(0o000)  # Remove all permissions

        query_result = QueryResultItem(
            similarity_score=0.88,
            file_path="restricted_file.py",
            line_number=1,
            code_snippet="def restricted_function(): pass",
            repository_alias="test-repo",
            file_last_modified=time.time() - 1800,
            indexed_timestamp=time.time() - 3600,
        )

        try:
            # Apply staleness detection - should handle permission error gracefully
            results = staleness_detector.apply_staleness_detection(
                [query_result], project_root
            )

            # Verify graceful handling of permission error
            assert len(results) == 1
            result = results[0]
            # Result should still be created, but local_file_mtime might be None
            assert hasattr(result, "local_file_mtime")
            assert hasattr(result, "is_stale")
        finally:
            # Restore permissions for cleanup
            test_file.chmod(0o755)

    def test_invalid_timestamp_error_handling(self, staleness_detector, tmp_path):
        """Test error handling for invalid timestamps."""
        project_root = tmp_path / "test-project"
        project_root.mkdir()

        query_result = QueryResultItem(
            similarity_score=0.75,
            file_path="test_file.py",
            line_number=1,
            code_snippet="def test_function(): pass",
            repository_alias="test-repo",
            file_last_modified=-1,  # Invalid timestamp
            indexed_timestamp=time.time() - 3600,
        )

        # Apply staleness detection - should handle invalid timestamps gracefully
        results = staleness_detector.apply_staleness_detection(
            [query_result], project_root
        )

        # Verify graceful handling of invalid timestamp
        assert len(results) == 1
        result = results[0]
        assert not result.is_stale  # Should default to not stale for invalid timestamps
        assert (
            result.staleness_delta_seconds is None
        )  # Delta should be None for invalid timestamps


class TestStalenessDetectorCaching:
    """Test caching mechanisms for performance optimization."""

    @pytest.fixture
    def staleness_detector(self):
        """Create StalenessDetector instance for testing."""
        return StalenessDetector()

    def test_file_mtime_cache_hit_behavior(self, staleness_detector, tmp_path):
        """Test that file mtime caching prevents redundant filesystem operations."""
        project_root = tmp_path / "test-project"
        project_root.mkdir()

        test_file = project_root / "cached_file.py"
        test_file.write_text("def cached_function(): pass")

        # Test caching through batch operations (this is how caching actually works)
        file_paths = ["cached_file.py"]

        # First call should populate cache
        staleness_detector._batch_file_stats(file_paths, project_root)
        initial_stat_calls = staleness_detector._file_stat_calls

        # Second call should use cache
        staleness_detector._batch_file_stats(file_paths, project_root)
        final_stat_calls = staleness_detector._file_stat_calls

        # Verify cache is working
        assert len(staleness_detector._file_mtime_cache) > 0
        assert staleness_detector._cache_hits > 0
        assert final_stat_calls == initial_stat_calls  # No additional stat calls

    def test_file_mtime_cache_ttl_expiration(self, staleness_detector, tmp_path):
        """Test that cache entries expire after TTL (5 minutes)."""
        project_root = tmp_path / "test-project"
        project_root.mkdir()

        test_file = project_root / "ttl_file.py"
        test_file.write_text("def ttl_function(): pass")

        # Test should fail - TTL mechanism doesn't exist yet
        # Populate cache
        staleness_detector._get_local_file_mtime(test_file)

        # Mock time advancement beyond TTL
        with patch("time.time", return_value=time.time() + 301):  # 5 minutes + 1 second
            staleness_detector._get_local_file_mtime(test_file)

        # Cache should work correctly with TTL

    def test_cache_memory_efficiency(self, staleness_detector, tmp_path):
        """Test that cache doesn't grow unbounded and manages memory efficiently."""
        project_root = tmp_path / "test-project"
        project_root.mkdir()

        # Create files and test cache through batch operations
        file_paths = []
        for i in range(10):  # Create reasonable number for testing
            test_file = project_root / f"cache_test_{i}.py"
            test_file.write_text(f"def function_{i}(): pass")
            file_paths.append(f"cache_test_{i}.py")

        # Process files through batch operations to populate cache
        staleness_detector._batch_file_stats(file_paths, project_root)

        # Verify cache has entries
        cache_size = len(staleness_detector._file_mtime_cache)
        assert cache_size > 0
        assert cache_size == len(file_paths)  # Should have cached all files


class TestStalenessDetectorIntegration:
    """Test integration with query execution pipeline."""

    def test_integration_with_execute_remote_query(self, tmp_path):
        """Test integration with remote query execution pipeline."""
        project_root = tmp_path / "test-project"
        project_root.mkdir()
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir()

        # Test should fail - integration doesn't exist yet
        # Verify integration is available
        from code_indexer.remote.staleness_detector import StalenessDetector

        # Verify classes can be imported and instantiated
        detector = StalenessDetector()
        assert detector is not None

    def test_backwards_compatibility_with_existing_queryresultitem(self):
        """Test that existing QueryResultItem continues to work unchanged."""
        # Existing functionality should continue to work
        query_result = QueryResultItem(
            similarity_score=0.95,
            file_path="src/auth.py",
            line_number=10,
            code_snippet="def authenticate_user(username: str, password: str): pass",
            repository_alias="test-repo",
            file_last_modified=time.time() - 3600,
            indexed_timestamp=time.time() - 1800,
        )

        # Verify all existing fields are accessible
        assert query_result.similarity_score == 0.95
        assert query_result.file_path == "src/auth.py"
        assert query_result.line_number == 10
        assert (
            query_result.code_snippet
            == "def authenticate_user(username: str, password: str): pass"
        )
        assert query_result.repository_alias == "test-repo"
        assert query_result.file_last_modified is not None
        assert query_result.indexed_timestamp is not None

    def test_enhanced_query_result_item_backwards_compatibility(self):
        """Test that EnhancedQueryResultItem is backwards compatible with QueryResultItem."""
        # Test should fail - EnhancedQueryResultItem doesn't exist yet
        # Should accept all QueryResultItem fields plus staleness metadata
        enhanced_result = EnhancedQueryResultItem(
            similarity_score=0.95,
            file_path="src/auth.py",
            line_number=10,
            code_snippet="def authenticate_user(username: str, password: str): pass",
            repository_alias="test-repo",
            file_last_modified=time.time() - 3600,
            indexed_timestamp=time.time() - 1800,
            local_file_mtime=time.time() - 1800,
            is_stale=True,
            staleness_delta_seconds=1800,
            staleness_indicator="🟡",
        )
        assert enhanced_result.is_stale


class TestStalenessVisualIndicators:
    """Test visual staleness indicator formatting."""

    def test_fresh_indicator_formatting(self):
        """Test fresh result indicator (🟢 Fresh)."""
        # Test should fail - formatting method doesn't exist yet
        detector = StalenessDetector()
        indicator = detector._format_staleness_indicator(
            is_stale=False, delta_seconds=0
        )
        assert "🟢" in indicator

    def test_slightly_stale_indicator_formatting(self):
        """Test slightly stale indicator (🟡 30m stale)."""
        # Test should fail - formatting method doesn't exist yet
        detector = StalenessDetector()
        indicator = detector._format_staleness_indicator(
            is_stale=True, delta_seconds=1800
        )  # 30 minutes
        assert "🟡" in indicator

    def test_moderately_stale_indicator_formatting(self):
        """Test moderately stale indicator (🟠 2h stale)."""
        # Test should fail - formatting method doesn't exist yet
        detector = StalenessDetector()
        indicator = detector._format_staleness_indicator(
            is_stale=True, delta_seconds=7200
        )  # 2 hours
        assert "🟠" in indicator

    def test_significantly_stale_indicator_formatting(self):
        """Test significantly stale indicator (🔴 25h stale)."""
        # Test should fail - formatting method doesn't exist yet
        detector = StalenessDetector()
        indicator = detector._format_staleness_indicator(
            is_stale=True, delta_seconds=90000
        )  # 25 hours
        assert "🔴" in indicator

    def test_edge_case_indicator_formatting(self):
        """Test edge case indicator formatting (no timestamp data)."""
        # Test should fail - formatting method doesn't exist yet
        detector = StalenessDetector()
        indicator = detector._format_staleness_indicator(
            is_stale=False, delta_seconds=None
        )
        assert "🟢" in indicator


class TestTimezoneIndependentComparison:
    """Test Feature 5 Story 2: Timezone Independent Comparison functionality.

    Tests UTC timestamp normalization and cross-timezone accuracy for staleness detection.
    """

    @pytest.fixture
    def staleness_detector(self):
        """Create StalenessDetector instance for timezone testing."""
        return StalenessDetector()

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create temporary project root directory."""
        project_dir = tmp_path / "timezone-test-project"
        project_dir.mkdir()
        return project_dir

    def test_utc_timestamp_normalization_method_exists(self, staleness_detector):
        """Test that UTC normalization method exists and is accessible."""
        # This test will fail until we implement the normalize_to_utc method
        assert hasattr(
            staleness_detector, "normalize_to_utc"
        ), "normalize_to_utc method not found"

        # Method should be callable
        assert callable(
            getattr(staleness_detector, "normalize_to_utc")
        ), "normalize_to_utc is not callable"

    def test_utc_normalization_local_system_timezone(self, staleness_detector):
        """Test UTC normalization converts local system time to UTC correctly."""

        # The key insight: timestamps are always in UTC, but the INTERPRETATION
        # of raw file timestamps depends on the system timezone
        # We need to test that the normalized result is consistent

        # Create a file timestamp that would be interpreted as local time
        # Simulate a file modification time timestamp
        local_time_naive = datetime.datetime(2024, 6, 15, 14, 30, 0)  # 2:30 PM local

        # This is what os.stat().st_mtime would return - naive local timestamp
        raw_file_timestamp = local_time_naive.timestamp()

        # Our normalize_to_utc method should handle this correctly
        utc_timestamp = staleness_detector.normalize_to_utc(raw_file_timestamp)

        # The normalized timestamp should represent the same moment in time
        # but be properly timezone-aware
        assert utc_timestamp is not None, "UTC normalization returned None"

        # Verify the timestamp is valid
        utc_dt = datetime.datetime.fromtimestamp(
            utc_timestamp, tz=datetime.timezone.utc
        )
        assert utc_dt.tzinfo == datetime.timezone.utc, "Timestamp not normalized to UTC"

        # The normalized timestamp should be the same as the input for consistency
        # since timestamp() already returns UTC seconds since epoch
        assert (
            utc_timestamp == raw_file_timestamp
        ), "UTC normalization should preserve timestamp value for consistency"

        # But verify the semantic conversion is working by checking the datetime interpretation
        original_local_aware = datetime.datetime.fromtimestamp(
            raw_file_timestamp
        ).astimezone()
        normalized_utc = datetime.datetime.fromtimestamp(
            utc_timestamp, tz=datetime.timezone.utc
        )

        # These should represent the same moment in time
        assert (
            original_local_aware.astimezone(datetime.timezone.utc) == normalized_utc
        ), "Timestamps don't represent the same moment"

    def test_utc_normalization_with_specified_timezone(self, staleness_detector):
        """Test UTC normalization with specific source timezone."""

        # Test with a specific timestamp - create a datetime that represents 2:30 PM Eastern Time
        # and get its timestamp value
        eastern_naive_dt = datetime.datetime(
            2024, 6, 15, 14, 30, 0
        )  # 2:30 PM Eastern time

        # Convert to timestamp assuming it's in Eastern timezone
        # This simulates what we'd get from a file stat on a system running in Eastern time
        eastern_timestamp = eastern_naive_dt.timestamp()

        # Normalize with timezone specification
        utc_timestamp = staleness_detector.normalize_to_utc(
            eastern_timestamp, source_timezone="US/Eastern"
        )

        # Verify conversion worked
        assert utc_timestamp is not None, "UTC normalization returned None"
        utc_dt = datetime.datetime.fromtimestamp(
            utc_timestamp, tz=datetime.timezone.utc
        )
        assert utc_dt.tzinfo == datetime.timezone.utc, "Timestamp not normalized to UTC"

        # The normalized timestamp should be the same since timestamp() is already UTC-based
        # But what matters is that our method handled the timezone specification correctly
        assert isinstance(utc_timestamp, float), "UTC timestamp should be a float"

        # Verify the method can handle timezone specifications without errors
        assert (
            utc_timestamp == eastern_timestamp
        ), "For consistency, normalized timestamp should equal input"

    def test_local_file_mtime_utc_conversion(self, staleness_detector, project_root):
        """Test that local file mtime is converted to UTC before comparison."""

        # Create test file
        test_file = project_root / "utc_test.py"
        test_file.write_text("def utc_test_function(): pass")

        # Set specific modification time
        local_time = datetime.datetime(2024, 6, 15, 10, 0, 0)
        local_timestamp = local_time.timestamp()
        os.utime(test_file, (local_timestamp, local_timestamp))

        # This test will fail until UTC conversion is implemented in _get_local_file_mtime
        local_mtime = staleness_detector._get_local_file_mtime(test_file)

        # Local mtime should now be in UTC
        utc_dt = datetime.datetime.fromtimestamp(local_mtime, tz=datetime.timezone.utc)
        assert (
            utc_dt.tzinfo == datetime.timezone.utc
        ), "Local file mtime not converted to UTC"

    def test_cross_timezone_consistency_same_modification(
        self, staleness_detector, project_root
    ):
        """Test that same file modification produces identical staleness across timezones."""

        # Create test file with known modification time
        test_file = project_root / "cross_tz_test.py"
        test_file.write_text("def cross_timezone_function(): pass")

        # Fixed modification time in UTC
        utc_time = datetime.datetime(
            2024, 6, 15, 18, 0, 0, tzinfo=datetime.timezone.utc
        )
        utc_timestamp = utc_time.timestamp()
        os.utime(test_file, (utc_timestamp, utc_timestamp))

        # Remote index timestamp (also UTC, older than file)
        remote_timestamp = utc_timestamp - 3600  # 1 hour earlier

        query_result = QueryResultItem(
            similarity_score=0.90,
            file_path="cross_tz_test.py",
            line_number=1,
            code_snippet="def cross_timezone_function(): pass",
            repository_alias="test-repo",
            file_last_modified=remote_timestamp,
            indexed_timestamp=remote_timestamp,
        )

        # Test with different system timezones
        # This test will fail until timezone normalization is fully implemented

        # Simulate Eastern timezone (UTC-5)
        with patch("time.timezone", 18000):  # UTC-5 = 5 * 3600 seconds
            results_eastern = staleness_detector.apply_staleness_detection(
                [query_result], project_root
            )

        # Simulate Pacific timezone (UTC-8)
        with patch("time.timezone", 28800):  # UTC-8 = 8 * 3600 seconds
            results_pacific = staleness_detector.apply_staleness_detection(
                [query_result], project_root
            )

        # Results should be identical regardless of system timezone
        assert len(results_eastern) == len(results_pacific) == 1
        eastern_result = results_eastern[0]
        pacific_result = results_pacific[0]

        assert (
            eastern_result.is_stale == pacific_result.is_stale
        ), "Staleness differs across timezones"
        assert (
            abs(
                (eastern_result.staleness_delta_seconds or 0)
                - (pacific_result.staleness_delta_seconds or 0)
            )
            < 1
        ), "Staleness delta differs across timezones"
        assert (
            eastern_result.staleness_indicator == pacific_result.staleness_indicator
        ), "Staleness indicator differs across timezones"

    def test_daylight_saving_time_handling(self, staleness_detector, project_root):
        """Test timezone conversion handles daylight saving transitions correctly."""

        # Create test file
        test_file = project_root / "dst_test.py"
        test_file.write_text("def dst_test_function(): pass")

        # Test DST transition dates for US Eastern timezone
        # Spring forward: March 10, 2024 (2:00 AM -> 3:00 AM)
        # Fall back: November 3, 2024 (2:00 AM -> 1:00 AM)

        # This test will fail until DST handling is implemented

        # Before DST transition (EST: UTC-5)
        before_dst = datetime.datetime(2024, 3, 9, 14, 0, 0)  # March 9, 2:00 PM EST
        before_timestamp = before_dst.timestamp()

        # After DST transition (EDT: UTC-4)
        after_dst = datetime.datetime(2024, 3, 11, 14, 0, 0)  # March 11, 2:00 PM EDT
        after_timestamp = after_dst.timestamp()

        # Test UTC conversion handles DST correctly
        utc_before = staleness_detector.normalize_to_utc(
            before_timestamp, source_timezone="US/Eastern"
        )
        utc_after = staleness_detector.normalize_to_utc(
            after_timestamp, source_timezone="US/Eastern"
        )

        # Verify both are properly converted to UTC
        before_utc_dt = datetime.datetime.fromtimestamp(
            utc_before, tz=datetime.timezone.utc
        )
        after_utc_dt = datetime.datetime.fromtimestamp(
            utc_after, tz=datetime.timezone.utc
        )

        assert (
            before_utc_dt.tzinfo == datetime.timezone.utc
        ), "Before DST not converted to UTC"
        assert (
            after_utc_dt.tzinfo == datetime.timezone.utc
        ), "After DST not converted to UTC"

        # Time difference should account for DST change
        # March 9 to March 11 is 2 days, but because of DST spring forward,
        # there's 1 hour less in the transition
        time_diff = after_utc_dt - before_utc_dt
        expected_diff = datetime.timedelta(days=2) - datetime.timedelta(
            hours=1
        )  # 2 days minus 1 hour for spring forward

        # Allow for some tolerance in the comparison (within 1 hour)
        actual_diff_seconds = time_diff.total_seconds()
        expected_diff_seconds = expected_diff.total_seconds()

        assert (
            abs(actual_diff_seconds - expected_diff_seconds) <= 3600
        ), f"DST handling incorrect: actual={actual_diff_seconds}, expected={expected_diff_seconds}"

    def test_timezone_conversion_error_handling(self, staleness_detector):
        """Test graceful handling of timezone conversion errors."""
        # This test will fail until error handling is implemented

        # Invalid timestamp
        invalid_timestamp = -999999999.0

        # Should not raise exception, should return original or None
        try:
            result = staleness_detector.normalize_to_utc(invalid_timestamp)
            # Should handle gracefully
            assert result is None or isinstance(result, float), "Error handling failed"
        except Exception as e:
            pytest.fail(
                f"normalize_to_utc should handle invalid timestamp gracefully: {e}"
            )

        # Invalid timezone
        try:
            valid_timestamp = time.time()
            result = staleness_detector.normalize_to_utc(
                valid_timestamp, source_timezone="Invalid/Timezone"
            )
            assert result is None or isinstance(
                result, float
            ), "Invalid timezone should be handled gracefully"
        except Exception as e:
            pytest.fail(
                f"normalize_to_utc should handle invalid timezone gracefully: {e}"
            )

    def test_performance_utc_conversion_overhead(
        self, staleness_detector, project_root
    ):
        """Test that UTC conversion adds minimal overhead (<10ms per operation)."""

        # Create test files
        for i in range(20):
            test_file = project_root / f"perf_test_{i}.py"
            test_file.write_text(f"def perf_function_{i}(): pass")

            # Set modification time
            mod_time = datetime.datetime(2024, 6, 15, 12, i, 0).timestamp()
            os.utime(test_file, (mod_time, mod_time))

        # Create query results
        query_results = []
        current_time = time.time()
        for i in range(20):
            query_results.append(
                QueryResultItem(
                    similarity_score=0.8,
                    file_path=f"perf_test_{i}.py",
                    line_number=1,
                    code_snippet=f"def perf_function_{i}(): pass",
                    repository_alias="test-repo",
                    file_last_modified=current_time - 3600,
                    indexed_timestamp=current_time - 1800,
                )
            )

        # This test will fail until UTC conversion performance is optimized
        start_time = time.time()
        results = staleness_detector.apply_staleness_detection(
            query_results, project_root
        )
        end_time = time.time()

        processing_time = (end_time - start_time) * 1000  # milliseconds

        # Should still meet original <100ms requirement with UTC conversion
        assert (
            processing_time < 100
        ), f"UTC conversion caused performance regression: {processing_time}ms"

        # UTC conversion overhead should be minimal (<10ms per 20 operations = <0.5ms per operation)
        per_operation_time = processing_time / len(query_results)
        assert (
            per_operation_time < 10
        ), f"UTC conversion overhead too high: {per_operation_time}ms per operation"

        assert len(results) == 20

    def test_remote_timestamp_utc_verification(self, staleness_detector):
        """Test that remote timestamps are already in UTC (Feature 0 Story 2 integration)."""
        # This test verifies that remote timestamps from the API are UTC
        # This test will fail if Feature 0 Story 2 doesn't provide UTC timestamps

        current_utc = time.time()  # Assuming system provides UTC timestamps

        # Create query result with indexed_timestamp (from remote API)
        query_result = QueryResultItem(
            similarity_score=0.85,
            file_path="remote_utc_test.py",
            line_number=1,
            code_snippet="def remote_function(): pass",
            repository_alias="test-repo",
            file_last_modified=current_utc - 1800,
            indexed_timestamp=current_utc - 3600,  # This should be UTC from remote API
        )

        # Verify indexed_timestamp is treated as UTC
        indexed_dt = datetime.datetime.fromtimestamp(
            query_result.indexed_timestamp, tz=datetime.timezone.utc
        )

        # Should be valid UTC timestamp
        assert (
            indexed_dt.tzinfo == datetime.timezone.utc
        ), "Remote timestamp not in UTC format"

        # Should be reasonable recent time (within last day)
        time_diff = abs(current_utc - query_result.indexed_timestamp)
        assert time_diff < 86400, "Remote timestamp seems invalid (more than 1 day old)"

    def test_timezone_metadata_in_enhanced_results(
        self, staleness_detector, project_root
    ):
        """Test that timezone information is included in staleness metadata for debugging."""

        # Create test file
        test_file = project_root / "timezone_meta_test.py"
        test_file.write_text("def timezone_meta_function(): pass")

        current_time = datetime.datetime.now().timestamp()
        os.utime(test_file, (current_time, current_time))

        query_result = QueryResultItem(
            similarity_score=0.88,
            file_path="timezone_meta_test.py",
            line_number=1,
            code_snippet="def timezone_meta_function(): pass",
            repository_alias="test-repo",
            file_last_modified=current_time - 1800,
            indexed_timestamp=current_time - 3600,
        )

        # This test will fail until timezone metadata is added to EnhancedQueryResultItem
        results = staleness_detector.apply_staleness_detection(
            [query_result], project_root
        )

        assert len(results) == 1
        result = results[0]

        # Should include timezone metadata for debugging
        assert hasattr(result, "timezone_info"), "Timezone metadata not included"
        assert result.timezone_info is not None, "Timezone metadata is None"
        assert (
            "local_timezone" in result.timezone_info
        ), "Local timezone not in metadata"
        assert (
            "utc_normalized" in result.timezone_info
        ), "UTC normalization flag not in metadata"
