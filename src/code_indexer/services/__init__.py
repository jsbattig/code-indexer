"""Service clients for external APIs."""

from .ollama import OllamaClient
from .qdrant import QdrantClient
from .docker_manager import DockerManager, get_global_compose_file_path

__all__ = [
    "OllamaClient",
    "QdrantClient",
    "DockerManager",
    "get_global_compose_file_path",
]
