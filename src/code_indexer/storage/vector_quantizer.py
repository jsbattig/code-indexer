"""Vector quantization for filesystem-based storage.

Implements the quantization pipeline: 1536-dim → Random Projection → 64-dim → 2-bit Quantization → Hex Path
Following Story 2 requirements for path-as-vector quantization.
"""

import numpy as np
from typing import List


class VectorQuantizer:
    """Quantize high-dimensional vectors to filesystem paths.

    Pipeline:
    1. Random Projection: 1536-dim → 64-dim (dimensionality reduction)
    2. 2-bit Quantization: 64 floats → 128 bits (compression)
    3. Hex Conversion: 128 bits → 32 hex characters (path representation)
    4. Path Segmentation: 32 chars → directory structure with depth factor
    """

    def __init__(self, depth_factor: int = 4, reduced_dimensions: int = 64):
        """Initialize quantizer with configuration.

        Args:
            depth_factor: Number of directory levels for path segmentation
            reduced_dimensions: Target dimensions after projection (must be 64 for 2-bit quantization)
        """
        self.depth_factor = depth_factor
        self.reduced_dimensions = reduced_dimensions

        # Validate reduced_dimensions for 2-bit quantization
        if reduced_dimensions != 64:
            raise ValueError(
                "reduced_dimensions must be 64 for 32-character hex output"
            )

    def quantize_vector(self, vector: np.ndarray, projection_matrix: np.ndarray) -> str:
        """Convert high-dimensional vector to hex path string.

        Args:
            vector: High-dimensional vector (e.g., 1536-dim)
            projection_matrix: Projection matrix for dimensionality reduction

        Returns:
            32-character hex string for filesystem path
        """
        # Step 1: Project to lower dimension
        reduced = self._project_vector(vector, projection_matrix)

        # Step 2: Quantize to 2-bit representation
        quantized_bits = self._quantize_to_2bit(reduced)

        # Step 3: Convert to hex string
        hex_string = self._bits_to_hex(quantized_bits)

        return hex_string

    def _project_vector(
        self, vector: np.ndarray, projection_matrix: np.ndarray
    ) -> np.ndarray:
        """Apply random projection for dimensionality reduction.

        Args:
            vector: High-dimensional input vector
            projection_matrix: Projection matrix (input_dim x reduced_dim)

        Returns:
            Reduced-dimension vector
        """
        return vector @ projection_matrix

    def _quantize_to_2bit(
        self, vector: np.ndarray, min_val: float = -2.0, max_val: float = 2.0
    ) -> np.ndarray:
        """Quantize float vector to 2-bit representation using fixed-range scalar quantization.

        LOCALITY-PRESERVING: Uses fixed thresholds for ALL vectors, ensuring similar
        vectors quantize to similar paths. This is critical for O(1) lookup performance.

        Each value is mapped to {0, 1, 2, 3} based on fixed range thresholds:
        - 00 (0): < min_val + 0.25 * range
        - 01 (1): >= min_val + 0.25 * range and < min_val + 0.5 * range
        - 10 (2): >= min_val + 0.5 * range and < min_val + 0.75 * range
        - 11 (3): >= min_val + 0.75 * range

        Args:
            vector: Float vector to quantize
            min_val: Minimum value for quantization range (default: -2.0)
            max_val: Maximum value for quantization range (default: 2.0)

        Returns:
            Array of uint8 values in {0, 1, 2, 3}
        """
        # Clip values to range
        clipped = np.clip(vector, min_val, max_val)

        # Map [min_val, max_val] → [0, 3.999] → int [0, 3]
        range_size = max_val - min_val
        normalized = (clipped - min_val) / range_size  # [0, 1]
        quantized = (normalized * 3.999).astype(np.uint8)  # [0, 3]

        # Ensure values are in valid range
        return np.clip(quantized, 0, 3)

    def _bits_to_hex(self, quantized: np.ndarray) -> str:
        """Convert 2-bit quantized values to hex string.

        Each pair of 2-bit values (4 bits total) becomes one hex character.
        64 values * 2 bits = 128 bits = 32 hex characters.

        Args:
            quantized: Array of 64 values in {0, 1, 2, 3}

        Returns:
            32-character hex string
        """
        if len(quantized) != 64:
            raise ValueError(f"Expected 64 values, got {len(quantized)}")

        # Pack pairs of 2-bit values into 4-bit nibbles
        hex_chars = []
        for i in range(0, 64, 2):
            # Combine two 2-bit values into one 4-bit nibble
            nibble = (quantized[i] << 2) | quantized[i + 1]
            hex_chars.append(f"{nibble:x}")

        return "".join(hex_chars)

    def _split_hex_path(self, hex_path: str) -> List[str]:
        """Split hex path into directory segments based on depth factor.

        For depth_factor=4 and 32-char hex:
        - First 4 segments: 2 characters each (a3, b7, 2f, c9)
        - Last segment: Remaining 24 characters

        Args:
            hex_path: 32-character hex string

        Returns:
            List of path segments
        """
        segments = []
        chars_per_segment = 2

        # Create depth_factor segments of 2 chars each
        for i in range(self.depth_factor):
            start = i * chars_per_segment
            end = start + chars_per_segment
            segments.append(hex_path[start:end])

        # Remaining characters go into final segment
        remainder_start = self.depth_factor * chars_per_segment
        segments.append(hex_path[remainder_start:])

        return segments
