"""Service clients for external APIs."""

from .ollama import OllamaClient
from .qdrant import QdrantClient
from .docker_manager import DockerManager, get_project_compose_file_path
from .embedding_factory import EmbeddingProviderFactory
from .rag_context_extractor import RAGContextExtractor
from .claude_integration import ClaudeIntegrationService, check_claude_sdk_availability

__all__ = [
    "OllamaClient",
    "QdrantClient",
    "DockerManager",
    "get_project_compose_file_path",
    "EmbeddingProviderFactory",
    "RAGContextExtractor",
    "ClaudeIntegrationService",
    "check_claude_sdk_availability",
]
