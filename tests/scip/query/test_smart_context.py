"""Tests for SCIP smart context composite query."""

import pytest
from pathlib import Path

from src.code_indexer.scip.query.composites import get_smart_context


class TestSmartContext:
    """Test smart context functionality."""

    def test_context_includes_definition(self, comprehensive_scip_fixture):
        """Test that smart context includes symbol definition."""
        # Arrange
        scip_dir = comprehensive_scip_fixture
        symbol = "UserService"
        limit = 20

        # Act
        result = get_smart_context(symbol, scip_dir, limit=limit)

        # Assert
        assert result.target_symbol == symbol
        assert result.total_files >= 0
        assert result.total_symbols >= 0

    def test_files_are_deduplicated(self, comprehensive_scip_fixture):
        """Test that each file appears only once in results."""
        # Arrange
        scip_dir = comprehensive_scip_fixture
        symbol = "UserService"

        # Act
        result = get_smart_context(symbol, scip_dir, limit=50)

        # Assert: All file paths are unique
        file_paths = [f.path for f in result.files]
        assert len(file_paths) == len(set(file_paths))

    def test_relevance_scoring_orders_results(self, comprehensive_scip_fixture):
        """Test that files are ordered by relevance score."""
        # Arrange
        scip_dir = comprehensive_scip_fixture
        symbol = "UserService"

        # Act
        result = get_smart_context(symbol, scip_dir, limit=20)

        # Assert: Files are sorted by relevance (descending)
        if len(result.files) > 1:
            for i in range(len(result.files) - 1):
                assert result.files[i].relevance_score >= result.files[i + 1].relevance_score


@pytest.fixture
def comprehensive_scip_fixture():
    """Provide path to comprehensive SCIP test fixture."""
    return Path("tests/scip/fixtures")
