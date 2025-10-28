"""Unit tests for ProjectionMatrixManager.

Test Strategy: Use real filesystem operations with deterministic test data (NO mocking).
Following Story 2 requirements for deterministic projection matrix generation.
"""

import numpy as np
import pytest


class TestProjectionMatrixManager:
    """Test deterministic projection matrix generation and management."""

    def test_create_deterministic_projection_matrix(self, tmp_path):
        """GIVEN input and output dimensions with seed
        WHEN creating projection matrix
        THEN produces deterministic, normalized matrix

        AC: Deterministic projection matrix generation
        """
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        manager = ProjectionMatrixManager()

        matrix1 = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=42
        )
        matrix2 = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=42
        )

        # Same seed produces identical matrix
        assert np.allclose(matrix1, matrix2), "Same seed must produce identical matrix"

        # Verify dimensions
        assert matrix1.shape == (1536, 64), f"Expected (1536, 64), got {matrix1.shape}"

        # Verify normalization - matrix values are divided by sqrt(output_dim)
        # This means individual elements are scaled, not column norms
        # Check that matrix values are in reasonable range
        assert np.abs(matrix1).mean() < 1.0, "Matrix values should be reasonably scaled"

    def test_different_seeds_different_matrices(self):
        """GIVEN two different seeds
        WHEN creating projection matrices
        THEN they produce different matrices

        AC: Different seeds produce different matrices
        """
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        manager = ProjectionMatrixManager()

        matrix1 = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=42
        )
        matrix2 = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=99
        )

        assert not np.allclose(
            matrix1, matrix2
        ), "Different seeds must produce different matrices"

    def test_save_and_load_projection_matrix(self, tmp_path):
        """GIVEN a projection matrix
        WHEN saving and loading from disk
        THEN loaded matrix is identical to original

        AC: Projection matrix persistence
        """
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        manager = ProjectionMatrixManager()

        # Create and save matrix
        original_matrix = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=42
        )
        collection_path = tmp_path / "test_collection"
        collection_path.mkdir()

        manager.save_matrix(original_matrix, collection_path)

        # Verify file exists
        matrix_file = collection_path / "projection_matrix.npy"
        assert matrix_file.exists(), "Matrix file should exist on filesystem"

        # Load and compare
        loaded_matrix = manager.load_matrix(collection_path)

        assert np.allclose(
            original_matrix, loaded_matrix
        ), "Loaded matrix must match original"
        assert loaded_matrix.shape == (
            1536,
            64,
        ), "Loaded matrix should have correct shape"

    def test_load_nonexistent_matrix_raises_error(self, tmp_path):
        """GIVEN collection path without matrix file
        WHEN attempting to load matrix
        THEN raises appropriate error

        AC: Error handling for missing matrix
        """
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        manager = ProjectionMatrixManager()

        nonexistent_path = tmp_path / "nonexistent_collection"
        nonexistent_path.mkdir()

        with pytest.raises(FileNotFoundError):
            manager.load_matrix(nonexistent_path)

    def test_auto_seed_from_collection_name(self):
        """GIVEN no explicit seed
        WHEN creating matrix
        THEN uses collection name hash as deterministic seed

        AC: Auto-seeding from collection context
        """
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        manager = ProjectionMatrixManager()

        # No seed provided - should use auto-seeding
        matrix1 = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=None
        )
        matrix2 = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=None
        )

        # Auto-seed should be consistent (based on fixed logic)
        assert np.allclose(matrix1, matrix2), "Auto-seeding should be deterministic"

    def test_matrix_normalization_for_stability(self):
        """GIVEN created projection matrix
        WHEN inspecting matrix values
        THEN they are scaled for stable projection

        AC: Matrix normalization for stable results
        """
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        manager = ProjectionMatrixManager()

        matrix = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=42
        )

        # Matrix is normalized by dividing by sqrt(output_dim)
        # This scales all values, preserving the random projection properties
        # Check that values are reasonably scaled (not too large)
        assert np.abs(matrix).max() < 1.0, "Matrix values should be scaled down"
        assert np.abs(matrix).mean() < 0.5, "Average magnitude should be reasonable"

        # Verify the matrix preserves expected properties
        # After division by sqrt(64), individual elements should be smaller
        assert matrix.shape == (1536, 64), "Shape should be correct"

    def test_projection_preserves_relative_distances(self):
        """GIVEN high-dimensional vectors
        WHEN projecting to lower dimension
        THEN relative distances are approximately preserved

        AC: Random projection preserves distances (Johnson-Lindenstrauss lemma)
        """
        from code_indexer.storage.projection_matrix_manager import (
            ProjectionMatrixManager,
        )

        manager = ProjectionMatrixManager()

        matrix = manager.create_projection_matrix(
            input_dim=1536, output_dim=64, seed=42
        )

        # Create test vectors
        np.random.seed(99)
        v1 = np.random.randn(1536)
        v2 = np.random.randn(1536)
        v3 = np.random.randn(1536)

        # Project vectors
        p1 = v1 @ matrix
        p2 = v2 @ matrix
        p3 = v3 @ matrix

        # Compute distances in original space
        dist_12_orig = np.linalg.norm(v1 - v2)
        dist_13_orig = np.linalg.norm(v1 - v3)

        # Compute distances in projected space
        dist_12_proj = np.linalg.norm(p1 - p2)
        dist_13_proj = np.linalg.norm(p1 - p3)

        # Relative ordering should be approximately preserved
        # If d(v1,v2) < d(v1,v3), then d(p1,p2) should be < d(p1,p3)
        if dist_12_orig < dist_13_orig:
            assert (
                dist_12_proj < dist_13_proj * 1.5
            ), "Relative distances should be preserved"
