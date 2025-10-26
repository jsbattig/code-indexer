"""Projection matrix management for dimensionality reduction.

Implements deterministic random projection for reducing vector dimensions
while preserving relative distances (Johnson-Lindenstrauss lemma).
Following Story 2 requirements for reusable projection matrices.
"""

import numpy as np
from pathlib import Path
from typing import Optional


class ProjectionMatrixManager:
    """Manage deterministic projection matrices for collections.

    Projection matrices enable dimensionality reduction via random projection,
    reducing 1536-dim vectors to 64-dim while preserving relative distances.

    Singleton cache: Matrix loaded once per collection and kept in memory
    for the lifetime of the process (no TTL, no expiry).
    """

    # Class-level cache: {collection_path: matrix}
    _matrix_cache: dict[str, np.ndarray] = {}

    def create_projection_matrix(
        self,
        input_dim: int,
        output_dim: int,
        seed: Optional[int] = None
    ) -> np.ndarray:
        """Create deterministic projection matrix.

        Uses random projection for dimensionality reduction with normalization
        for stable results. The projection matrix is normalized by sqrt(output_dim)
        to preserve expected distances.

        Args:
            input_dim: Input vector dimensions (e.g., 1536)
            output_dim: Output vector dimensions (e.g., 64)
            seed: Random seed for determinism (auto-generated if None)

        Returns:
            Normalized projection matrix (input_dim x output_dim)
        """
        if seed is None:
            # Use deterministic auto-seed based on dimensions
            seed = hash(f"projection_matrix_{input_dim}_{output_dim}") % (2**32)

        # Set seed for reproducibility
        np.random.seed(seed)

        # Create random Gaussian matrix
        matrix = np.random.randn(input_dim, output_dim)

        # Normalize for stable projection
        # Division by sqrt(output_dim) preserves expected distances
        matrix /= np.sqrt(output_dim)

        return matrix

    def save_matrix(self, matrix: np.ndarray, collection_path: Path) -> None:
        """Save projection matrix to collection directory in binary format.

        Args:
            matrix: Projection matrix to save
            collection_path: Path to collection directory
        """
        collection_path = Path(collection_path)
        collection_path.mkdir(parents=True, exist_ok=True)

        # Save in binary NPY format
        matrix_path = collection_path / "projection_matrix.npy"
        np.save(matrix_path, matrix)

    def load_matrix(self, collection_path: Path) -> np.ndarray:
        """Load projection matrix with singleton caching.

        Matrix is loaded once per collection and kept in memory for the
        lifetime of the process. No TTL, no expiry - simple singleton pattern.

        For cidx index: Matrix stays cached across all files
        For cidx query: Matrix loads on first query, stays until process ends

        Args:
            collection_path: Path to collection directory

        Returns:
            Loaded projection matrix (from cache or disk)

        Raises:
            FileNotFoundError: If matrix file does not exist
        """
        collection_path = Path(collection_path)
        cache_key = str(collection_path.absolute())

        # Check singleton cache first
        if cache_key in self._matrix_cache:
            return self._matrix_cache[cache_key]

        # Load from disk (binary NPY format)
        matrix_path = collection_path / "projection_matrix.npy"

        if not matrix_path.exists():
            raise FileNotFoundError(
                f"Projection matrix not found at {matrix_path}"
            )

        # Load and cache
        matrix = np.load(matrix_path)
        self._matrix_cache[cache_key] = matrix

        return matrix
