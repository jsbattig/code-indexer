"""Unit tests for VectorQuantizer.

Test Strategy: Use real filesystem operations with deterministic test data (NO mocking).
Following Story 2 requirements for 1536→64→2-bit→path quantization pipeline.
"""

import numpy as np
import pytest
from pathlib import Path


class TestVectorQuantizer:
    """Test vector quantization pipeline: 1536-dim → 64-dim → 2-bit → path."""

    @pytest.fixture
    def test_vectors(self):
        """Generate deterministic test vectors."""
        np.random.seed(42)
        return {
            'small': np.random.randn(10, 1536),
            'medium': np.random.randn(100, 1536),
            'large': np.random.randn(1000, 1536)
        }

    def test_deterministic_quantization_same_vector_same_path(self, test_vectors):
        """GIVEN the same vector quantized twice
        WHEN using the same projection matrix
        THEN it produces the same filesystem path

        AC: Deterministic quantization (same vector → same path)
        """
        from code_indexer.storage.vector_quantizer import VectorQuantizer

        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)

        # Create deterministic projection matrix
        np.random.seed(42)
        projection_matrix = np.random.randn(1536, 64) / np.sqrt(64)

        vector = test_vectors['small'][0]
        path1 = quantizer.quantize_vector(vector, projection_matrix)
        path2 = quantizer.quantize_vector(vector, projection_matrix)

        assert path1 == path2, "Quantization must be deterministic"
        assert isinstance(path1, str), "Path must be string"
        assert len(path1) == 32, "32 hex characters expected (64 dims * 2 bits / 4 bits per hex)"

    def test_quantize_to_2bit_quartile_mapping(self):
        """GIVEN a float vector
        WHEN quantizing to 2-bit representation
        THEN each value maps to correct quartile (00, 01, 10, 11)

        AC: 2-bit quantization using quartiles
        """
        from code_indexer.storage.vector_quantizer import VectorQuantizer

        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)

        # Test vector with known quartiles
        vector = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])

        quantized = quantizer._quantize_to_2bit(vector)

        # Verify quantized values are in {0, 1, 2, 3}
        assert np.all((quantized >= 0) & (quantized <= 3)), "Values must be 0-3"
        assert len(quantized) == len(vector), "Length must match"

        # Verify quartile distribution
        unique_values = set(quantized)
        assert len(unique_values) <= 4, "Maximum 4 unique values"

    def test_bits_to_hex_conversion(self):
        """GIVEN 2-bit quantized values
        WHEN converting to hex string
        THEN produces correct hex representation

        AC: Bit-to-hex conversion for path generation
        """
        from code_indexer.storage.vector_quantizer import VectorQuantizer

        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)

        # 64 values in {0,1,2,3} = 128 bits = 32 hex chars
        quantized = np.array([0, 1, 2, 3] * 16, dtype=np.uint8)  # 64 values

        hex_string = quantizer._bits_to_hex(quantized)

        assert isinstance(hex_string, str), "Must return string"
        assert len(hex_string) == 32, "Must be 32 hex characters"
        assert all(c in '0123456789abcdef' for c in hex_string), "Must be valid hex"

    def test_path_segments_with_depth_factor_4(self):
        """GIVEN 32-character hex string
        WHEN splitting with depth factor 4
        THEN creates correct directory structure (2/2/2/2/24)

        AC: Directory structure uses depth factor 4
        """
        from code_indexer.storage.vector_quantizer import VectorQuantizer

        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)

        hex_path = "a3b72fc9d8e4f1a2b5c3e7f0d4a8c1e9"  # 32 chars

        segments = quantizer._split_hex_path(hex_path)

        # Depth factor 4: split into 4 segments of 2 chars each, remainder
        assert len(segments) == 5, "Should have 5 segments (4 x 2-char + remainder)"
        assert segments[0] == "a3", "First segment should be 2 chars"
        assert segments[1] == "b7", "Second segment should be 2 chars"
        assert segments[2] == "2f", "Third segment should be 2 chars"
        assert segments[3] == "c9", "Fourth segment should be 2 chars"
        assert len(segments[4]) == 24, "Remainder should be 24 chars"

    def test_full_quantization_pipeline(self, test_vectors):
        """GIVEN high-dimensional vector
        WHEN running full quantization pipeline
        THEN produces valid hex path for filesystem storage

        AC: Complete 1536→64→2-bit→path pipeline
        """
        from code_indexer.storage.vector_quantizer import VectorQuantizer

        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)

        # Create projection matrix
        np.random.seed(42)
        projection_matrix = np.random.randn(1536, 64) / np.sqrt(64)

        vector = test_vectors['small'][0]

        hex_path = quantizer.quantize_vector(vector, projection_matrix)

        # Verify output
        assert isinstance(hex_path, str)
        assert len(hex_path) == 32
        assert all(c in '0123456789abcdef' for c in hex_path)

        # Verify determinism
        hex_path2 = quantizer.quantize_vector(vector, projection_matrix)
        assert hex_path == hex_path2

    def test_different_vectors_different_paths(self, test_vectors):
        """GIVEN two different vectors
        WHEN quantizing both
        THEN they produce different paths (with high probability)

        AC: Quantization provides good distribution
        """
        from code_indexer.storage.vector_quantizer import VectorQuantizer

        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)

        np.random.seed(42)
        projection_matrix = np.random.randn(1536, 64) / np.sqrt(64)

        vector1 = test_vectors['small'][0]
        vector2 = test_vectors['small'][1]

        path1 = quantizer.quantize_vector(vector1, projection_matrix)
        path2 = quantizer.quantize_vector(vector2, projection_matrix)

        assert path1 != path2, "Different vectors should produce different paths"

    def test_batch_quantization_performance(self, test_vectors):
        """GIVEN 1000 vectors to quantize
        WHEN quantizing in batch
        THEN completes in reasonable time (<2s)

        AC: Performance requirement for batch operations
        """
        import time
        from code_indexer.storage.vector_quantizer import VectorQuantizer

        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)

        np.random.seed(42)
        projection_matrix = np.random.randn(1536, 64) / np.sqrt(64)

        vectors = test_vectors['large']  # 1000 vectors

        start = time.time()
        paths = [quantizer.quantize_vector(v, projection_matrix) for v in vectors]
        duration = time.time() - start

        assert len(paths) == 1000
        assert duration < 2.0, f"Quantization too slow: {duration:.2f}s"

        # Verify all paths are unique (with high probability)
        unique_paths = len(set(paths))
        assert unique_paths >= 990, "Should have mostly unique paths"
