"""YAML matrix format for git-friendly projection matrix storage.

Story 9: Matrix Multiplication Resident Service
Implements AC: Projection matrices stored in YAML format (git-friendly)
"""

import numpy as np
import yaml  # type: ignore
from pathlib import Path
from typing import Optional


def save_matrix_yaml(matrix: np.ndarray, matrix_path: Path) -> None:
    """Save projection matrix in YAML format.

    Converts numpy matrix to YAML with metadata for git-friendly storage.
    Format is human-readable and produces clean line-based diffs.

    Args:
        matrix: Numpy array to save
        matrix_path: Target YAML file path

    Raises:
        IOError: If file cannot be written
    """
    matrix_path = Path(matrix_path)

    # Create parent directories if needed
    matrix_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare YAML structure
    yaml_data = {
        'shape': list(matrix.shape),
        'dtype': str(matrix.dtype),
        'data': matrix.tolist()
    }

    # Write YAML with proper formatting
    with open(matrix_path, 'w') as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)


def load_matrix_yaml(matrix_path: Path) -> np.ndarray:
    """Load projection matrix from YAML format.

    Args:
        matrix_path: Path to YAML matrix file

    Returns:
        Loaded numpy array

    Raises:
        FileNotFoundError: If matrix file doesn't exist
        ValueError: If YAML structure is invalid or shape mismatch
    """
    matrix_path = Path(matrix_path)

    if not matrix_path.exists():
        raise FileNotFoundError(f"Matrix file not found: {matrix_path}")

    # Load YAML
    with open(matrix_path, 'r') as f:
        yaml_data = yaml.safe_load(f)

    # Extract metadata
    shape = tuple(yaml_data['shape'])
    dtype = yaml_data['dtype']
    data = yaml_data['data']

    # Convert to numpy array
    matrix = np.array(data, dtype=dtype)

    # Validate shape
    if matrix.shape != shape:
        raise ValueError(
            f"Shape mismatch: expected {shape}, got {matrix.shape}"
        )

    return matrix


def convert_npy_to_yaml(npy_path: Path, yaml_path: Optional[Path] = None) -> Path:
    """Convert .npy matrix file to YAML format.

    Keeps original .npy file intact. Auto-determines output path if not specified.

    Args:
        npy_path: Path to existing .npy file
        yaml_path: Optional target YAML path (auto-determined if None)

    Returns:
        Path to created YAML file

    Raises:
        FileNotFoundError: If npy_path doesn't exist
    """
    npy_path = Path(npy_path)

    if not npy_path.exists():
        raise FileNotFoundError(f"NPY file not found: {npy_path}")

    # Auto-determine YAML path
    if yaml_path is None:
        yaml_path = npy_path.with_suffix('.yaml')
    else:
        yaml_path = Path(yaml_path)

    # Load .npy matrix
    matrix = np.load(npy_path)

    # Save as YAML
    save_matrix_yaml(matrix, yaml_path)

    return yaml_path
