"""Abstract base class for embedding providers."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""

    embedding: List[float]
    model: str
    tokens_used: Optional[int] = None
    provider: str = ""


@dataclass
class BatchEmbeddingResult:
    """Result from batch embedding generation."""

    embeddings: List[List[float]]
    model: str
    total_tokens_used: Optional[int] = None
    provider: str = ""


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    def __init__(self, console=None):
        self.console = console

    @abstractmethod
    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed
            model: Optional model override

        Returns:
            List of floats representing the embedding vector
        """
        pass

    @abstractmethod
    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch.

        Args:
            texts: List of texts to embed
            model: Optional model override

        Returns:
            List of embedding vectors (one per input text)
        """
        pass

    @abstractmethod
    def get_embedding_with_metadata(
        self, text: str, model: Optional[str] = None
    ) -> EmbeddingResult:
        """Generate embedding with metadata (tokens, model info, etc.).

        Args:
            text: Text to embed
            model: Optional model override

        Returns:
            EmbeddingResult with embedding and metadata
        """
        pass

    @abstractmethod
    def get_embeddings_batch_with_metadata(
        self, texts: List[str], model: Optional[str] = None
    ) -> BatchEmbeddingResult:
        """Generate batch embeddings with metadata.

        Args:
            texts: List of texts to embed
            model: Optional model override

        Returns:
            BatchEmbeddingResult with embeddings and metadata
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the embedding provider is healthy and accessible.

        Returns:
            True if provider is healthy, False otherwise
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model.

        Returns:
            Dictionary with model information (dimensions, max_tokens, etc.)
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of this embedding provider.

        Returns:
            Provider name (e.g., "ollama", "voyage-ai")
        """
        pass

    @abstractmethod
    def get_current_model(self) -> str:
        """Get the current active model name.

        Returns:
            Model name
        """
        pass

    @abstractmethod
    def supports_batch_processing(self) -> bool:
        """Check if provider supports efficient batch processing.

        Returns:
            True if batch processing is supported and efficient
        """
        pass
