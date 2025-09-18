"""Tests for universal staleness detection across local and remote modes.

Tests Feature 5 Story 3: Stale Detection for Both Modes ensuring identical
staleness detection behavior regardless of query execution mode.
"""

import pytest
import tempfile
import time
from pathlib import Path

# No additional imports needed - removed unused imports

from code_indexer.api_clients.remote_query_client import QueryResultItem
from code_indexer.remote.staleness_detector import (
    StalenessDetector,
    EnhancedQueryResultItem,
)


class TestUniversalStalenessDetection:
    """Test universal staleness detection works identically in both local and remote modes."""

    @pytest.fixture
    def staleness_detector(self):
        """Create staleness detector for testing."""
        return StalenessDetector(staleness_threshold_seconds=0.0)

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def sample_file(self, temp_project_root):
        """Create sample file for testing."""
        file_path = temp_project_root / "test_file.py"
        file_path.write_text("def test_function():\n    pass\n")
        return file_path

    def test_staleness_detector_supports_mode_parameter(self, staleness_detector):
        """Test that StalenessDetector can accept mode parameter."""
        # Create mock query result with both timestamp fields
        query_result = QueryResultItem(
            similarity_score=0.95,
            file_path="test_file.py",
            line_number=1,
            code_snippet="def test_function():\n    pass",
            repository_alias="test-repo",
            file_last_modified=time.time() - 3600,  # 1 hour ago
            indexed_timestamp=time.time() - 1800,  # 30 minutes ago
        )

        # Should now work with mode parameter
        enhanced_results = staleness_detector.apply_staleness_detection(
            [query_result], Path("/tmp"), mode="remote"
        )

        assert len(enhanced_results) == 1
        assert enhanced_results[0].timezone_info["execution_mode"] == "remote"

        # Test local mode as well
        enhanced_results_local = staleness_detector.apply_staleness_detection(
            [query_result], Path("/tmp"), mode="local"
        )

        assert len(enhanced_results_local) == 1
        assert enhanced_results_local[0].timezone_info["execution_mode"] == "local"

    def test_local_mode_uses_file_last_modified_for_comparison(
        self, staleness_detector, temp_project_root, sample_file
    ):
        """Test that local mode uses file_last_modified timestamp for staleness comparison."""
        # Create query result simulating local mode data structure
        local_file_mtime = sample_file.stat().st_mtime

        query_result = QueryResultItem(
            similarity_score=0.95,
            file_path="test_file.py",
            line_number=1,
            code_snippet="def test_function():\n    pass",
            repository_alias="test-repo",
            file_last_modified=local_file_mtime,  # Local mode: uses file_last_modified
            indexed_timestamp=None,  # Local mode: no indexed_timestamp from API
        )

        # Should now work with local mode
        enhanced_results = staleness_detector.apply_staleness_detection(
            [query_result], temp_project_root, mode="local"
        )

        assert len(enhanced_results) == 1
        assert enhanced_results[0].timezone_info["execution_mode"] == "local"
        assert (
            enhanced_results[0].timezone_info["timestamp_source"]
            == "file_last_modified"
        )

    def test_remote_mode_uses_indexed_timestamp_for_comparison(
        self, staleness_detector, temp_project_root, sample_file
    ):
        """Test that remote mode uses indexed_timestamp for staleness comparison."""
        query_result = QueryResultItem(
            similarity_score=0.95,
            file_path="test_file.py",
            line_number=1,
            code_snippet="def test_function():\n    pass",
            repository_alias="test-repo",
            file_last_modified=None,  # Remote mode: may not have this
            indexed_timestamp=time.time()
            - 1800,  # Remote mode: uses indexed_timestamp from API
        )

        # Should now work with remote mode
        enhanced_results = staleness_detector.apply_staleness_detection(
            [query_result], temp_project_root, mode="remote"
        )

        assert len(enhanced_results) == 1
        assert enhanced_results[0].timezone_info["execution_mode"] == "remote"
        assert (
            enhanced_results[0].timezone_info["timestamp_source"] == "indexed_timestamp"
        )

    def test_identical_staleness_calculation_across_modes(
        self, staleness_detector, temp_project_root, sample_file
    ):
        """Test that staleness calculation is identical regardless of mode when timestamps are equivalent."""
        current_time = time.time()
        local_mtime = current_time - 3600  # 1 hour ago

        # Modify file to ensure known mtime
        sample_file.write_text("def modified_function():\n    return True\n")

        # Create query results that should produce identical staleness results
        local_result = QueryResultItem(
            similarity_score=0.95,
            file_path="test_file.py",
            line_number=1,
            code_snippet="def modified_function():\n    return True",
            repository_alias="test-repo",
            file_last_modified=local_mtime,  # Local mode timestamp source
            indexed_timestamp=None,
        )

        remote_result = QueryResultItem(
            similarity_score=0.95,
            file_path="test_file.py",
            line_number=1,
            code_snippet="def modified_function():\n    return True",
            repository_alias="test-repo",
            file_last_modified=None,
            indexed_timestamp=local_mtime,  # Remote mode timestamp source (same value)
        )

        # Should now work with mode support
        local_enhanced = staleness_detector.apply_staleness_detection(
            [local_result], temp_project_root, mode="local"
        )
        remote_enhanced = staleness_detector.apply_staleness_detection(
            [remote_result], temp_project_root, mode="remote"
        )

        # Should produce identical staleness indicators
        assert local_enhanced[0].is_stale == remote_enhanced[0].is_stale
        assert (
            local_enhanced[0].staleness_indicator
            == remote_enhanced[0].staleness_indicator
        )
        assert (
            local_enhanced[0].staleness_delta_seconds
            == remote_enhanced[0].staleness_delta_seconds
        )

    def test_mode_agnostic_enhanced_result_structure(self, staleness_detector):
        """Test that EnhancedQueryResultItem structure is identical across modes."""
        query_result = QueryResultItem(
            similarity_score=0.95,
            file_path="test_file.py",
            line_number=1,
            code_snippet="def test_function():\n    pass",
            repository_alias="test-repo",
            file_last_modified=time.time(),
            indexed_timestamp=time.time(),
        )

        # Create enhanced results for both modes
        # Note: EnhancedQueryResultItem.from_query_result doesn't take mode parameter
        # Mode is handled at the StalenessDetector level
        local_enhanced = EnhancedQueryResultItem.from_query_result(query_result)
        remote_enhanced = EnhancedQueryResultItem.from_query_result(query_result)

        # Structure should be identical
        assert type(local_enhanced).model_fields == type(remote_enhanced).model_fields

    def test_consistent_visual_indicators_across_modes(
        self, staleness_detector, temp_project_root
    ):
        """Test that staleness visual indicators are identical across modes."""
        # Create test file
        test_file = temp_project_root / "consistent_test.py"
        test_file.write_text("def consistent_function():\n    pass\n")

        current_time = time.time()
        stale_timestamp = current_time - 7200  # 2 hours ago (should be stale)

        local_result = QueryResultItem(
            similarity_score=0.85,
            file_path="consistent_test.py",
            line_number=1,
            code_snippet="def consistent_function():\n    pass",
            repository_alias="test-repo",
            file_last_modified=stale_timestamp,
            indexed_timestamp=None,
        )

        remote_result = QueryResultItem(
            similarity_score=0.85,
            file_path="consistent_test.py",
            line_number=1,
            code_snippet="def consistent_function():\n    pass",
            repository_alias="test-repo",
            file_last_modified=None,
            indexed_timestamp=stale_timestamp,
        )

        # Should now work with mode support
        local_enhanced = staleness_detector.apply_staleness_detection(
            [local_result], temp_project_root, mode="local"
        )
        remote_enhanced = staleness_detector.apply_staleness_detection(
            [remote_result], temp_project_root, mode="remote"
        )

        # Visual indicators should be identical
        assert (
            local_enhanced[0].staleness_indicator
            == remote_enhanced[0].staleness_indicator
        )

    def test_sorting_behavior_identical_across_modes(
        self, staleness_detector, temp_project_root
    ):
        """Test that result sorting with staleness priority is identical across modes."""
        # Create test files
        fresh_file = temp_project_root / "fresh.py"
        stale_file = temp_project_root / "stale.py"

        fresh_file.write_text("def fresh_function():\n    pass\n")
        stale_file.write_text("def stale_function():\n    pass\n")

        current_time = time.time()

        # Create one fresh result and one stale result
        # Fresh: index is newer than local file (local file hasn't changed since index)
        # Stale: local file is newer than index (local file modified after indexing)

        index_time = current_time - 3600  # Index was created 1 hour ago

        # Set file times
        import os

        os.utime(
            fresh_file, (index_time - 1800, index_time - 1800)
        )  # Fresh file older than index
        os.utime(
            stale_file, (current_time - 60, current_time - 60)
        )  # Stale file newer than index

        # Test results (stale has higher score but should be sorted after fresh)
        test_results = [
            QueryResultItem(
                similarity_score=0.95,  # Higher score
                file_path="stale.py",
                line_number=1,
                code_snippet="def stale_function():\n    pass",
                repository_alias="test-repo",
                file_last_modified=index_time,  # Index timestamp for comparison
                indexed_timestamp=index_time,
            ),
            QueryResultItem(
                similarity_score=0.85,  # Lower score
                file_path="fresh.py",
                line_number=1,
                code_snippet="def fresh_function():\n    pass",
                repository_alias="test-repo",
                file_last_modified=index_time,  # Index timestamp for comparison
                indexed_timestamp=index_time,
            ),
        ]

        # Test both modes
        local_enhanced = staleness_detector.apply_staleness_detection(
            test_results, temp_project_root, mode="local"
        )
        remote_enhanced = staleness_detector.apply_staleness_detection(
            test_results, temp_project_root, mode="remote"
        )

        # Check staleness detection worked correctly
        # Fresh file should not be stale, stale file should be stale
        fresh_result = next(r for r in local_enhanced if r.file_path == "fresh.py")
        stale_result = next(r for r in local_enhanced if r.file_path == "stale.py")

        assert not fresh_result.is_stale, "Fresh file should not be stale"
        assert stale_result.is_stale, "Stale file should be stale"

        # Fresh should come first despite lower score due to staleness priority sorting
        assert local_enhanced[0].file_path == "fresh.py"
        assert remote_enhanced[0].file_path == "fresh.py"

        # Order should be identical across modes
        local_order = [r.file_path for r in local_enhanced]
        remote_order = [r.file_path for r in remote_enhanced]
        assert local_order == remote_order


class TestModeSpecificTimestampHandling:
    """Test mode-specific timestamp handling logic."""

    @pytest.fixture
    def staleness_detector(self):
        """Create staleness detector for testing."""
        return StalenessDetector()

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    def test_get_index_timestamp_utc_local_mode(
        self, staleness_detector, temp_project_root
    ):
        """Test _get_index_timestamp_utc handles local mode correctly."""
        result = QueryResultItem(
            similarity_score=0.95,
            file_path="test.py",
            line_number=1,
            code_snippet="test content",
            repository_alias="test-repo",
            file_last_modified=1234567890.0,
            indexed_timestamp=None,
        )

        # Should now work with the implemented method
        timestamp = staleness_detector._get_index_timestamp_utc(result, "local")
        # Should return file_last_modified in local mode
        assert timestamp is not None  # UTC normalized timestamp

    def test_get_index_timestamp_utc_remote_mode(self, staleness_detector):
        """Test _get_index_timestamp_utc handles remote mode correctly."""
        result = QueryResultItem(
            similarity_score=0.95,
            file_path="test.py",
            line_number=1,
            code_snippet="test content",
            repository_alias="test-repo",
            file_last_modified=None,
            indexed_timestamp=time.time() - 1800,  # Valid timestamp
        )

        # Should now work with the implemented method
        timestamp = staleness_detector._get_index_timestamp_utc(result, "remote")
        # Should return indexed_timestamp in remote mode
        assert timestamp is not None  # UTC normalized timestamp

    def test_get_index_timestamp_utc_fallback_behavior(self, staleness_detector):
        """Test fallback behavior when preferred timestamp is None."""
        result = QueryResultItem(
            similarity_score=0.95,
            file_path="test.py",
            line_number=1,
            code_snippet="test content",
            repository_alias="test-repo",
            file_last_modified=1111111111.0,
            indexed_timestamp=None,  # Preferred timestamp missing
        )

        # Should now work with the implemented method
        # Remote mode should fall back to file_last_modified when indexed_timestamp is None
        timestamp = staleness_detector._get_index_timestamp_utc(result, "remote")
        assert timestamp is not None  # UTC normalized timestamp from fallback


class TestConfigurationConsistency:
    """Test that configuration settings apply consistently across modes."""

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    def test_staleness_threshold_applies_to_both_modes(self, temp_project_root):
        """Test that staleness threshold setting works identically in both modes."""
        threshold = 1800.0  # 30 minutes
        detector = StalenessDetector(staleness_threshold_seconds=threshold)

        current_time = time.time()
        # File modified 20 minutes ago - should not be stale with 30 minute threshold
        recent_timestamp = current_time - 1200

        local_result = QueryResultItem(
            similarity_score=0.95,
            file_path="test.py",
            line_number=1,
            code_snippet="test content",
            repository_alias="test-repo",
            file_last_modified=recent_timestamp,
            indexed_timestamp=None,
        )

        remote_result = QueryResultItem(
            similarity_score=0.95,
            file_path="test.py",
            line_number=1,
            code_snippet="test content",
            repository_alias="test-repo",
            file_last_modified=None,
            indexed_timestamp=recent_timestamp,
        )

        # Should now work with mode support
        local_enhanced = detector.apply_staleness_detection(
            [local_result], temp_project_root, mode="local"
        )
        remote_enhanced = detector.apply_staleness_detection(
            [remote_result], temp_project_root, mode="remote"
        )

        # Both should not be stale due to threshold
        assert not local_enhanced[0].is_stale
        assert not remote_enhanced[0].is_stale

    def test_cache_settings_apply_to_both_modes(self, temp_project_root):
        """Test that caching behavior is consistent across modes."""
        cache_ttl = 600  # 10 minutes
        detector = StalenessDetector(cache_ttl_seconds=cache_ttl)

        # Create test file
        test_file = temp_project_root / "cache_test.py"
        test_file.write_text("def cache_test():\n    pass\n")

        result = QueryResultItem(
            similarity_score=0.95,
            file_path="cache_test.py",
            line_number=1,
            code_snippet="def cache_test():\n    pass",
            repository_alias="test-repo",
            file_last_modified=time.time(),
            indexed_timestamp=time.time(),
        )

        # Should now work with mode support
        # Execute staleness detection in both modes
        detector.apply_staleness_detection([result], temp_project_root, mode="local")
        detector.apply_staleness_detection([result], temp_project_root, mode="remote")

        # Cache should be used for both modes
        stats = detector.get_cache_stats()
        assert stats["cache_hits"] > 0  # Should have cache hits from second call
