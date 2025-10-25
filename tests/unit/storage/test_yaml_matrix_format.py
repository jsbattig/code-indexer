"""Tests for YAML matrix format serialization/deserialization.

Story 9: Matrix Multiplication Resident Service
Tests AC: Projection matrices stored in YAML format (git-friendly)
"""

import numpy as np
import pytest
from pathlib import Path
import tempfile
import shutil

from code_indexer.storage.yaml_matrix_format import (
    save_matrix_yaml,
    load_matrix_yaml,
    convert_npy_to_yaml
)


class TestYAMLMatrixFormat:
    """Test YAML matrix format operations."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_save_matrix_yaml_creates_file(self):
        """Test saving matrix creates YAML file."""
        matrix = np.random.randn(10, 5)
        matrix_path = self.temp_dir / "test_matrix.yaml"

        save_matrix_yaml(matrix, matrix_path)

        assert matrix_path.exists()
        assert matrix_path.suffix == '.yaml'

    def test_save_and_load_matrix_yaml_roundtrip(self):
        """Test saving and loading matrix preserves data."""
        original_matrix = np.random.randn(1024, 64)
        matrix_path = self.temp_dir / "projection_matrix.yaml"

        save_matrix_yaml(original_matrix, matrix_path)
        loaded_matrix = load_matrix_yaml(matrix_path)

        assert loaded_matrix.shape == original_matrix.shape
        np.testing.assert_array_almost_equal(loaded_matrix, original_matrix, decimal=6)

    def test_load_matrix_yaml_preserves_dtype(self):
        """Test loading matrix preserves float64 dtype."""
        matrix = np.random.randn(10, 5).astype(np.float64)
        matrix_path = self.temp_dir / "test_matrix.yaml"

        save_matrix_yaml(matrix, matrix_path)
        loaded = load_matrix_yaml(matrix_path)

        assert loaded.dtype == np.float64

    def test_save_matrix_yaml_includes_metadata(self):
        """Test saved YAML includes shape and dtype metadata."""
        matrix = np.random.randn(1024, 64)
        matrix_path = self.temp_dir / "test_matrix.yaml"

        save_matrix_yaml(matrix, matrix_path)

        # Read raw YAML to check structure
        with open(matrix_path, 'r') as f:
            content = f.read()

        assert 'shape:' in content
        assert '1024' in content
        assert '64' in content
        assert 'dtype:' in content
        assert 'data:' in content

    def test_load_matrix_yaml_raises_on_missing_file(self):
        """Test loading non-existent file raises FileNotFoundError."""
        matrix_path = self.temp_dir / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            load_matrix_yaml(matrix_path)

    def test_save_matrix_yaml_handles_small_matrix(self):
        """Test saving small matrix works correctly."""
        matrix = np.array([[1.0, 2.0], [3.0, 4.0]])
        matrix_path = self.temp_dir / "small_matrix.yaml"

        save_matrix_yaml(matrix, matrix_path)
        loaded = load_matrix_yaml(matrix_path)

        np.testing.assert_array_equal(loaded, matrix)

    def test_save_matrix_yaml_handles_large_matrix(self):
        """Test saving large matrix (1536x64) works correctly."""
        matrix = np.random.randn(1536, 64)
        matrix_path = self.temp_dir / "large_matrix.yaml"

        save_matrix_yaml(matrix, matrix_path)
        loaded = load_matrix_yaml(matrix_path)

        assert loaded.shape == (1536, 64)
        np.testing.assert_array_almost_equal(loaded, matrix, decimal=6)

    def test_convert_npy_to_yaml_creates_yaml_file(self):
        """Test converting .npy to .yaml creates new file."""
        matrix = np.random.randn(100, 50)
        npy_path = self.temp_dir / "matrix.npy"
        yaml_path = self.temp_dir / "matrix.yaml"

        np.save(npy_path, matrix)
        convert_npy_to_yaml(npy_path, yaml_path)

        assert yaml_path.exists()
        loaded = load_matrix_yaml(yaml_path)
        np.testing.assert_array_almost_equal(loaded, matrix, decimal=6)

    def test_convert_npy_to_yaml_preserves_original(self):
        """Test conversion keeps original .npy file."""
        matrix = np.random.randn(10, 5)
        npy_path = self.temp_dir / "matrix.npy"
        yaml_path = self.temp_dir / "matrix.yaml"

        np.save(npy_path, matrix)
        convert_npy_to_yaml(npy_path, yaml_path)

        assert npy_path.exists()
        assert yaml_path.exists()

    def test_convert_npy_to_yaml_auto_determines_output_path(self):
        """Test conversion auto-creates .yaml path from .npy path."""
        matrix = np.random.randn(10, 5)
        npy_path = self.temp_dir / "projection_matrix.npy"

        np.save(npy_path, matrix)
        yaml_path = convert_npy_to_yaml(npy_path)

        assert yaml_path == self.temp_dir / "projection_matrix.yaml"
        assert yaml_path.exists()

    def test_yaml_format_is_human_readable(self):
        """Test YAML file is human-readable text format."""
        matrix = np.array([[1.5, 2.5], [3.5, 4.5]])
        matrix_path = self.temp_dir / "readable.yaml"

        save_matrix_yaml(matrix, matrix_path)

        with open(matrix_path, 'r') as f:
            content = f.read()

        # Should contain human-readable numbers
        assert '1.5' in content
        assert '2.5' in content
        assert '3.5' in content
        assert '4.5' in content

    def test_yaml_format_is_git_friendly(self):
        """Test YAML format produces consistent line-based diffs."""
        matrix1 = np.array([[1.0, 2.0], [3.0, 4.0]])
        matrix2 = np.array([[1.0, 2.0], [3.0, 5.0]])  # Only last element changed

        path1 = self.temp_dir / "matrix1.yaml"
        path2 = self.temp_dir / "matrix2.yaml"

        save_matrix_yaml(matrix1, path1)
        save_matrix_yaml(matrix2, path2)

        with open(path1, 'r') as f:
            lines1 = f.readlines()
        with open(path2, 'r') as f:
            lines2 = f.readlines()

        # Lines should be mostly identical except for changed value
        diff_count = sum(1 for a, b in zip(lines1, lines2) if a != b)
        assert diff_count <= 2  # Only row with changed value should differ

    def test_load_matrix_yaml_validates_shape(self):
        """Test loading validates shape metadata matches data."""
        matrix_path = self.temp_dir / "invalid.yaml"

        # Create YAML with mismatched shape
        with open(matrix_path, 'w') as f:
            f.write("shape: [2, 3]\n")
            f.write("dtype: float64\n")
            f.write("data:\n")
            f.write("  - [1.0, 2.0]\n")  # Only 2 elements, not 3
            f.write("  - [3.0, 4.0]\n")

        with pytest.raises(ValueError, match="[Ss]hape"):
            load_matrix_yaml(matrix_path)

    def test_save_matrix_yaml_creates_parent_directories(self):
        """Test saving matrix creates parent directories if needed."""
        matrix = np.random.randn(5, 3)
        nested_path = self.temp_dir / "subdir1" / "subdir2" / "matrix.yaml"

        save_matrix_yaml(matrix, nested_path)

        assert nested_path.exists()
        loaded = load_matrix_yaml(nested_path)
        np.testing.assert_array_almost_equal(loaded, matrix, decimal=6)
