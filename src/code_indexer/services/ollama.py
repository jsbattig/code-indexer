"""Ollama API client for embeddings generation."""

from typing import List, Dict, Any, Optional
import httpx
from rich.console import Console

from ..config import OllamaConfig
from .embedding_provider import EmbeddingProvider, EmbeddingResult, BatchEmbeddingResult


class OllamaClient(EmbeddingProvider):
    """Client for interacting with Ollama API."""

    def __init__(self, config: OllamaConfig, console: Optional[Console] = None):
        super().__init__(console)
        self.config = config
        self.console = console or Console()
        self.client = httpx.Client(base_url=config.host, timeout=config.timeout)

    def health_check(self) -> bool:
        """Check if Ollama service is accessible."""
        try:
            response = self.client.get("/api/tags")
            return bool(response.status_code == 200)
        except Exception:
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        try:
            response = self.client.get("/api/tags")
            response.raise_for_status()
            return list(response.json().get("models", []))
        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to Ollama: {e}")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama API error: {e}")

    def model_exists(self, model_name: str) -> bool:
        """Check if a specific model exists."""
        models = self.list_models()
        return any(model["name"] == model_name for model in models)

    def pull_model(self, model_name: str) -> bool:
        """Pull a model if it doesn't exist."""
        if self.model_exists(model_name):
            return True

        try:
            with self.console.status(f"Pulling model {model_name}..."):
                response = self.client.post(
                    "/api/pull",
                    json={"name": model_name},
                    timeout=300,  # 5 minutes for model download
                )
                response.raise_for_status()
                return True
        except Exception as e:
            self.console.print(f"Failed to pull model {model_name}: {e}", style="red")
            return False

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Generate embedding for given text."""
        model_name = model or self.config.model

        try:
            response = self.client.post(
                "/api/embeddings", json={"model": model_name, "prompt": text}
            )
            response.raise_for_status()

            result = response.json()
            embedding = result.get("embedding")

            if not embedding:
                raise ValueError("No embedding returned from Ollama")

            return list(embedding)

        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to Ollama: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Model {model_name} not found. Try pulling it first.")
            raise RuntimeError(f"Ollama API error: {e}")

    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch.

        Note: Ollama doesn't support native batch processing, so we process sequentially.
        """
        embeddings = []
        for text in texts:
            embedding = self.get_embedding(text, model)
            embeddings.append(embedding)
        return embeddings

    def get_embedding_with_metadata(
        self, text: str, model: Optional[str] = None
    ) -> EmbeddingResult:
        """Generate embedding with metadata."""
        embedding = self.get_embedding(text, model)
        model_name = model or self.config.model
        return EmbeddingResult(
            embedding=embedding,
            model=model_name,
            tokens_used=None,  # Ollama doesn't provide token usage
            provider="ollama",
        )

    def get_embeddings_batch_with_metadata(
        self, texts: List[str], model: Optional[str] = None
    ) -> BatchEmbeddingResult:
        """Generate batch embeddings with metadata."""
        embeddings = self.get_embeddings_batch(texts, model)
        model_name = model or self.config.model
        return BatchEmbeddingResult(
            embeddings=embeddings,
            model=model_name,
            total_tokens_used=None,  # Ollama doesn't provide token usage
            provider="ollama",
        )

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        model_name = self.config.model
        # Try to get model info from Ollama
        try:
            models = self.list_models()
            for model in models:
                if model["name"] == model_name:
                    return {
                        "name": model_name,
                        "provider": "ollama",
                        "dimensions": 768,  # Default for nomic-embed-text
                        "max_tokens": None,
                        "details": model,
                    }
        except Exception:
            pass

        # Fallback info
        return {
            "name": model_name,
            "provider": "ollama",
            "dimensions": 768,  # Default assumption
            "max_tokens": None,
        }

    def get_provider_name(self) -> str:
        """Get the name of this embedding provider."""
        return "ollama"

    def get_current_model(self) -> str:
        """Get the current active model name."""
        return self.config.model

    def supports_batch_processing(self) -> bool:
        """Check if provider supports efficient batch processing."""
        return False  # Ollama processes sequentially

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
