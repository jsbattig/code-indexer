"""Tests for SCIP index loader."""

import pytest
from pathlib import Path
from src.code_indexer.scip.query.loader import SCIPLoader
from src.code_indexer.scip.protobuf import Index


class TestSCIPLoader:
    """Test SCIP index loading functionality."""

    def test_load_scip_index_from_file(self):
        """Should load a .scip file and return an Index protobuf object."""
        # Arrange
        test_file = Path("tests/scip/fixtures/test_index.scip")
        loader = SCIPLoader()

        # Act
        result = loader.load(test_file)

        # Assert
        assert isinstance(result, Index)
        assert len(result.documents) > 0
        assert result.metadata.tool_info.name == "test"

    def test_loader_caches_indexes(self):
        """Should cache loaded indexes for faster subsequent access."""
        # Arrange
        test_file = Path("tests/scip/fixtures/test_index.scip")
        loader = SCIPLoader(cache_size=10)

        # Act
        result1 = loader.load(test_file)
        cache_info_after_first = loader.cache_info()
        result2 = loader.load(test_file)
        cache_info_after_second = loader.cache_info()

        # Assert
        assert cache_info_after_first["misses"] == 1
        assert cache_info_after_first["hits"] == 0
        assert cache_info_after_second["hits"] == 1
        assert result1 is result2  # Same object from cache

    def test_loader_file_not_found_raises_error(self):
        """Should raise FileNotFoundError for non-existent files."""
        # Arrange
        loader = SCIPLoader()
        non_existent = Path("does_not_exist.scip")

        # Act & Assert
        with pytest.raises(FileNotFoundError, match="SCIP file not found"):
            loader.load(non_existent)

    def test_loader_clear_cache(self):
        """Should clear all cached indexes."""
        # Arrange
        test_file = Path("tests/scip/fixtures/test_index.scip")
        loader = SCIPLoader()
        loader.load(test_file)
        assert loader.cache_info()["size"] == 1

        # Act
        loader.clear_cache()

        # Assert
        assert loader.cache_info()["size"] == 0
        assert loader.cache_info()["hits"] == 0
        assert loader.cache_info()["misses"] == 0
