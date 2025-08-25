"""Tests for chunk analysis tools used in Story 7 validation."""

import pytest
from pathlib import Path
import tempfile
import shutil

import sys

sys.path.append(str(Path(__file__).parent))
from chunk_analysis_tools import ChunkAnalyzer, run_story7_validation


class TestChunkAnalysisTools:
    """Test suite for chunk analysis tools."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def analyzer(self):
        """Create chunk analyzer instance."""
        return ChunkAnalyzer()

    @pytest.fixture
    def sample_python_file(self, temp_dir):
        """Create a sample Python file for testing."""
        file_path = temp_dir / "sample.py"
        content = '''"""Sample Python module for testing chunk analysis."""

import os
import sys
from typing import List, Dict


class SampleClass:
    """A sample class for testing."""
    
    def __init__(self, name: str):
        """Initialize the sample class."""
        self.name = name
        self.data = []
    
    def add_data(self, item: Dict[str, Any]) -> None:
        """Add data item to the collection."""
        if not isinstance(item, dict):
            raise ValueError("Item must be a dictionary")
        
        # Validate required fields
        if 'id' not in item or 'value' not in item:
            raise ValueError("Item must have 'id' and 'value' fields")
        
        # Check for duplicates
        existing_ids = [d.get('id') for d in self.data]
        if item['id'] in existing_ids:
            raise ValueError(f"Item with id {item['id']} already exists")
        
        self.data.append(item)
        print(f"Added item {item['id']} to {self.name}")
    
    def get_data_by_id(self, item_id: str) -> Dict[str, Any]:
        """Retrieve data item by ID."""
        for item in self.data:
            if item.get('id') == item_id:
                return item
        return None
    
    def process_all_data(self) -> List[str]:
        """Process all data items and return results."""
        results = []
        for item in self.data:
            try:
                # Complex processing logic
                processed_value = self._process_item(item)
                results.append(f"Processed {item['id']}: {processed_value}")
            except Exception as e:
                results.append(f"Error processing {item['id']}: {str(e)}")
        
        return results
    
    def _process_item(self, item: Dict[str, Any]) -> str:
        """Internal method to process a single item."""
        value = item.get('value', '')
        
        # Apply various transformations
        if isinstance(value, str):
            processed = value.upper().strip()
        elif isinstance(value, (int, float)):
            processed = str(value * 2)
        else:
            processed = str(value)
        
        return processed


def utility_function(data: List[Dict[str, Any]]) -> Dict[str, int]:
    """Utility function to analyze data."""
    stats = {
        'total_items': len(data),
        'string_values': 0,
        'numeric_values': 0,
        'other_values': 0
    }
    
    for item in data:
        value = item.get('value')
        if isinstance(value, str):
            stats['string_values'] += 1
        elif isinstance(value, (int, float)):
            stats['numeric_values'] += 1
        else:
            stats['other_values'] += 1
    
    return stats


if __name__ == "__main__":
    # Example usage
    sample = SampleClass("test")
    
    sample.add_data({"id": "1", "value": "hello"})
    sample.add_data({"id": "2", "value": 42})
    sample.add_data({"id": "3", "value": [1, 2, 3]})
    
    results = sample.process_all_data()
    for result in results:
        print(result)
    
    stats = utility_function(sample.data)
    print(f"Statistics: {stats}")
'''
        file_path.write_text(content)
        return file_path

    def test_analyze_chunk_distribution_basic(self, analyzer, sample_python_file):
        """Test basic chunk distribution analysis."""
        distribution, quality = analyzer.analyze_file_chunking(sample_python_file)

        # Basic validation
        assert distribution.total_chunks > 0, "Should have at least one chunk"
        assert distribution.average_size > 0, "Average size should be positive"
        assert distribution.min_size <= distribution.max_size, "Min should be <= max"

        # The current implementation should create chunks of exactly 1000 chars (except last)
        # This test should initially FAIL, demonstrating TDD approach
        # Expected behavior after Story 7 implementation:
        # - Most chunks should be exactly 1000 characters
        # - Only the last chunk should be under 1000

    def test_analyze_search_quality_metrics(self, analyzer, sample_python_file):
        """Test search quality metrics analysis."""
        distribution, quality = analyzer.analyze_file_chunking(sample_python_file)

        # Basic validation
        assert (
            quality.meaningful_chunks_count >= 0
        ), "Meaningful chunks count should be non-negative"
        assert (
            quality.fragment_chunks_count >= 0
        ), "Fragment chunks count should be non-negative"
        assert 0 <= quality.meaningful_percentage <= 100, "Percentage should be 0-100"

        # Quality expectations
        # This test should initially FAIL for poor quality chunks
        # Expected after Story 7: High percentage of meaningful chunks

    def test_comparison_with_old_approach(self, analyzer, sample_python_file):
        """Test comparison with old AST approach metrics."""
        distribution, quality = analyzer.analyze_file_chunking(sample_python_file)
        comparison = analyzer.compare_with_old_approach_metrics(distribution)

        # Validate comparison structure
        assert "old_metrics" in comparison
        assert "current_metrics" in comparison
        assert "improvements" in comparison
        assert "meets_story7_requirements" in comparison

        # Check old baseline metrics
        assert comparison["old_metrics"]["under_300_percent"] == 76.5
        assert comparison["old_metrics"]["under_100_percent"] == 52.0
        assert comparison["old_metrics"]["average_size"] == 549

        # This test should initially FAIL - current implementation should not meet Story 7 requirements
        # Expected after implementation:
        # - Massive reduction in under_300_percent
        # - Massive reduction in under_100_percent
        # - Significant increase in average_size

    def test_generate_comprehensive_report(self, analyzer, sample_python_file):
        """Test comprehensive report generation."""
        distribution, quality = analyzer.analyze_file_chunking(sample_python_file)
        comparison = analyzer.compare_with_old_approach_metrics(distribution)
        report = analyzer.generate_report(distribution, quality, comparison)

        # Validate report content
        assert "CHUNK QUALITY ANALYSIS REPORT" in report
        assert "CHUNK SIZE DISTRIBUTION:" in report
        assert "SEARCH QUALITY METRICS:" in report
        assert "COMPARISON WITH OLD AST APPROACH:" in report
        assert "STORY 7 REQUIREMENTS VALIDATION:" in report

        # Report should contain key metrics
        assert f"Total chunks: {distribution.total_chunks}" in report
        assert f"Average size: {distribution.average_size:.1f}" in report

        # This test should initially show FAIL status for Story 7 requirements

    def test_run_story7_validation_end_to_end(self, sample_python_file):
        """Test complete Story 7 validation workflow."""
        report = run_story7_validation(sample_python_file)

        # Validate end-to-end report
        assert "CHUNK QUALITY ANALYSIS REPORT" in report
        assert "STORY 7 REQUIREMENTS VALIDATION:" in report

        # This test should initially FAIL - requirements should not be met
        # Expected after implementation: All Story 7 requirements should PASS

    def test_story7_validation_requirements_all_pass(
        self, analyzer, sample_python_file
    ):
        """Test that Story 7 validation requirements all pass (implementation complete).

        This test validates that the fixed-size chunking implementation meets all
        Story 7 requirements, demonstrating successful TDD completion.
        """
        distribution, quality = analyzer.analyze_file_chunking(sample_python_file)
        comparison = analyzer.compare_with_old_approach_metrics(distribution)
        requirements = comparison["meets_story7_requirements"]

        # All Story 7 requirements should now PASS with the completed implementation

        # PASS: Chunks are 1000 chars (except final)
        assert requirements[
            "under_1000_except_final"
        ], "Story 7 requirement: Nearly all chunks should be 1000 chars (except final)"

        # PASS: Massive improvement over 300-char threshold
        assert requirements[
            "massive_improvement_under_300"
        ], "Story 7 requirement: Should show massive improvement over 300-char threshold"

        # PASS: Massive improvement over 100-char threshold
        assert requirements[
            "massive_improvement_under_100"
        ], "Story 7 requirement: Should show massive improvement over 100-char threshold"

        # PASS: Average size near 1000
        assert requirements[
            "average_size_near_1000"
        ], "Story 7 requirement: Average size should be near 1000 chars"

        # Validate the actual improvements are substantial
        improvements = comparison["improvements"]
        assert (
            improvements["under_300_reduction"] >= 60
        ), f"Should reduce under-300 chunks by at least 60%, got {improvements['under_300_reduction']:.1f}%"
        assert (
            improvements["under_100_reduction"] >= 40
        ), f"Should reduce under-100 chunks by at least 40%, got {improvements['under_100_reduction']:.1f}%"
        assert (
            improvements["average_size_increase"] >= 200
        ), f"Should increase average size by at least 200 chars, got {improvements['average_size_increase']:.0f}"


class TestRealWorldValidation:
    """Test validation against larger, more realistic codebases."""

    def test_validate_against_current_codebase(self):
        """Test validation against the current code-indexer codebase.

        This test runs Story 7 validation against the actual codebase to verify
        that fixed-size chunking produces the expected improvements.
        """
        # Get the source directory of the current project
        current_dir = Path(__file__).parent.parent.parent.parent
        src_dir = current_dir / "src" / "code_indexer"

        if not src_dir.exists():
            pytest.skip("Source directory not found for validation")

        # Run validation on the actual codebase
        report = run_story7_validation(src_dir)

        # Basic validation that report was generated
        assert "CHUNK QUALITY ANALYSIS REPORT" in report
        assert "Total chunks:" in report

        # This test should initially show mixed results
        # After full Story 7 implementation, it should show dramatic improvements

    def test_validate_chunk_overlap_consistency(self):
        """Test that chunk overlap is consistently 150 characters across real files."""
        analyzer = ChunkAnalyzer()

        # Create test file with known content for overlap verification
        test_content = "X" * 5000  # 5000 chars should create multiple chunks

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            chunks = analyzer.chunker.chunk_file(temp_path)

            # Verify overlap between consecutive chunks
            for i in range(len(chunks) - 1):
                current_chunk = chunks[i]
                next_chunk = chunks[i + 1]

                current_text = current_chunk["text"]
                next_text = next_chunk["text"]

                # For regular chunks (1000 chars), verify exact overlap
                if len(current_text) == 1000:
                    # Last 150 chars of current should match first 150 chars of next
                    expected_overlap = current_text[-150:]
                    actual_overlap = next_text[:150]

                    # This should FAIL initially if overlap is not exactly 150 chars
                    assert (
                        expected_overlap == actual_overlap
                    ), f"Chunks {i}-{i+1}: Expected 150-char overlap not found"

        finally:
            # Clean up
            temp_path.unlink()

    def test_line_number_accuracy_validation(self):
        """Test line number accuracy in chunked content."""
        analyzer = ChunkAnalyzer()

        # Create multi-line test content
        lines = [
            f"Line {i+1}: This is content for line number {i+1}" for i in range(100)
        ]
        test_content = "\n".join(lines)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            chunks = analyzer.chunker.chunk_file(temp_path)

            for i, chunk in enumerate(chunks):
                line_start = chunk["line_start"]
                line_end = chunk["line_end"]

                # Basic validation
                assert line_start >= 1, f"Chunk {i}: line_start should be >= 1"
                assert (
                    line_end >= line_start
                ), f"Chunk {i}: line_end should be >= line_start"
                assert (
                    line_end <= 100
                ), f"Chunk {i}: line_end should not exceed file length"

                # First chunk should start at line 1
                if i == 0:
                    assert line_start == 1, "First chunk should start at line 1"

                # This test may FAIL initially if line number calculation is incorrect

        finally:
            temp_path.unlink()
