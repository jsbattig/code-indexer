"""Filesystem-based vector storage components."""

from .vector_quantizer import VectorQuantizer
from .projection_matrix_manager import ProjectionMatrixManager
from .filesystem_vector_store import FilesystemVectorStore

__all__ = [
    'VectorQuantizer',
    'ProjectionMatrixManager',
    'FilesystemVectorStore',
]
