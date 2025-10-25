"""Projection matrix management for dimensionality reduction.

Implements deterministic random projection for reducing vector dimensions
while preserving relative distances (Johnson-Lindenstrauss lemma).
Following Story 2 requirements for reusable projection matrices.

Story 9: Updated to support YAML format for git-friendly storage.
"""

import numpy as np
from pathlib import Path
from typing import Optional

from .yaml_matrix_format import save_matrix_yaml, load_matrix_yaml, convert_npy_to_yaml


class ProjectionMatrixManager:
    """Manage deterministic projection matrices for collections.

    Projection matrices enable dimensionality reduction via random projection,
    reducing 1536-dim vectors to 64-dim while preserving relative distances.
    """

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
        """Save projection matrix to collection directory in YAML format.

        Args:
            matrix: Projection matrix to save
            collection_path: Path to collection directory
        """
        collection_path = Path(collection_path)
        collection_path.mkdir(parents=True, exist_ok=True)

        # Save in YAML format (git-friendly)
        matrix_path = collection_path / "projection_matrix.yaml"
        save_matrix_yaml(matrix, matrix_path)

        # Also convert old .npy files if they exist
        old_npy_path = collection_path / "projection_matrix.npy"
        if old_npy_path.exists() and not matrix_path.exists():
            convert_npy_to_yaml(old_npy_path)

    def load_matrix(self, collection_path: Path) -> np.ndarray:
        """Load existing projection matrix from collection.

        Supports both YAML (preferred) and legacy NPY formats.
        Automatically converts NPY to YAML when found.

        Args:
            collection_path: Path to collection directory

        Returns:
            Loaded projection matrix

        Raises:
            FileNotFoundError: If matrix file does not exist
        """
        collection_path = Path(collection_path)
        yaml_path = collection_path / "projection_matrix.yaml"
        npy_path = collection_path / "projection_matrix.npy"

        # Try YAML first (preferred format)
        if yaml_path.exists():
            return load_matrix_yaml(yaml_path)

        # Fall back to NPY and convert to YAML
        if npy_path.exists():
            matrix = np.load(npy_path)
            # Convert to YAML for future use
            save_matrix_yaml(matrix, yaml_path)
            return matrix

        raise FileNotFoundError(
            f"Projection matrix not found at {collection_path}"
        )
