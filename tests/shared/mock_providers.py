"""
Shared mock providers for testing.

This module contains reusable mock implementations for testing different components
of the code indexer without requiring actual external services.
"""

import time
import threading
from typing import List, Optional, Dict, Any

from code_indexer.services.embedding_provider import (
    EmbeddingProvider,
    EmbeddingResult,
    BatchEmbeddingResult,
)


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding provider for testing."""

    def __init__(
        self,
        provider_name: str = "test-provider",
        delay: float = 0.1,
        dimensions: int = 768,
    ):
        super().__init__()
        self.provider_name = provider_name
        self.delay = delay
        self.dimensions = dimensions
        self.call_count = 0
        self.call_lock = threading.Lock()

    def get_provider_name(self) -> str:
        return self.provider_name

    def get_current_model(self) -> str:
        return "test-model"

    def get_model_info(self) -> Dict[str, Any]:
        return {"name": "test-model", "dimensions": self.dimensions}

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Mock embedding generation with configurable delay."""
        with self.call_lock:
            self.call_count += 1

        if self.delay > 0:
            time.sleep(self.delay)

        # Generate a simple mock embedding based on text length
        return [float(len(text) % 100) / 100.0] * self.dimensions

    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Mock batch embedding generation."""
        return [self.get_embedding(text, model) for text in texts]

    def get_embedding_with_metadata(
        self, text: str, model: Optional[str] = None
    ) -> EmbeddingResult:
        """Mock embedding generation with metadata."""
        embedding = self.get_embedding(text, model)
        return EmbeddingResult(
            embedding=embedding,
            model=model or self.get_current_model(),
            tokens_used=len(text.split()),
            provider=self.provider_name,
        )

    def get_embeddings_batch_with_metadata(
        self, texts: List[str], model: Optional[str] = None
    ) -> BatchEmbeddingResult:
        """Mock batch embedding generation with metadata."""
        embeddings = self.get_embeddings_batch(texts, model)
        total_tokens = sum(len(text.split()) for text in texts)
        return BatchEmbeddingResult(
            embeddings=embeddings,
            model=model or self.get_current_model(),
            total_tokens_used=total_tokens,
            provider=self.provider_name,
        )

    def supports_batch_processing(self) -> bool:
        """Mock batch processing support."""
        return True

    def health_check(self) -> bool:
        return True

    def reset_call_count(self):
        """Reset the call count for testing purposes."""
        with self.call_lock:
            self.call_count = 0
