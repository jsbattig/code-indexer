"""Factory for creating embedding providers based on configuration."""

import re
from typing import Optional, List, Dict, Any
from rich.console import Console

from ..config import Config
from .embedding_provider import EmbeddingProvider
from .ollama import OllamaClient
from .voyage_ai import VoyageAIClient


class EmbeddingProviderFactory:
    """Factory for creating embedding providers."""

    @staticmethod
    def generate_model_slug(provider_name: str, model_name: str) -> str:
        """Convert model names to filesystem-safe collection name components.

        Args:
            provider_name: Name of the embedding provider (e.g., 'ollama', 'voyage-ai')
            model_name: Name of the model (e.g., 'nomic-embed-text', 'voyage-code-3')

        Returns:
            Filesystem-safe slug for use in collection names

        Examples:
            generate_model_slug('ollama', 'nomic-embed-text') -> 'ollama_nomic_embed_text'
            generate_model_slug('voyage-ai', 'voyage-code-3') -> 'voyage_ai_voyage_code_3'
        """
        # Normalize provider name (replace hyphens with underscores)
        provider_slug = re.sub(r"[^a-zA-Z0-9_]", "_", provider_name.lower())

        # Normalize model name (replace hyphens and special chars with underscores)
        model_slug = re.sub(r"[^a-zA-Z0-9_]", "_", model_name.lower())

        # Remove consecutive underscores and strip leading/trailing underscores
        provider_slug = re.sub(r"_+", "_", provider_slug).strip("_")
        model_slug = re.sub(r"_+", "_", model_slug).strip("_")

        return f"{provider_slug}_{model_slug}"

    @staticmethod
    def generate_collection_name(
        base_name: str, provider_name: str, model_name: str
    ) -> str:
        """Generate collection name based on provider and model.

        Args:
            base_name: Base collection name (e.g., 'code_index')
            provider_name: Name of the embedding provider
            model_name: Name of the model

        Returns:
            Full collection name for the provider and model

        Examples:
            generate_collection_name('code_index', 'ollama', 'nomic-embed-text')
            -> 'code_index_ollama_nomic_embed_text'
        """
        model_slug = EmbeddingProviderFactory.generate_model_slug(
            provider_name, model_name
        )
        return f"{base_name}_{model_slug}"

    @staticmethod
    def get_provider_model_info(config: Config) -> Dict[str, Any]:
        """Get current provider and model information.

        Args:
            config: Main configuration object

        Returns:
            Dictionary containing provider name, model name, and model info
        """
        provider_name = config.embedding_provider

        # Create provider instance to get model info
        provider: EmbeddingProvider
        if provider_name == "ollama":
            provider = OllamaClient(config.ollama, None)
        elif provider_name == "voyage-ai":
            provider = VoyageAIClient(config.voyage_ai, None)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider_name}")

        model_name = provider.get_current_model()
        model_info = provider.get_model_info()

        return {
            "provider_name": provider_name,
            "model_name": model_name,
            "model_info": model_info,
            "dimensions": model_info["dimensions"],
            "slug": EmbeddingProviderFactory.generate_model_slug(
                provider_name, model_name
            ),
        }

    @staticmethod
    def create(config: Config, console: Optional[Console] = None) -> EmbeddingProvider:
        """Create an embedding provider based on configuration.

        Args:
            config: Main configuration object
            console: Optional console for output

        Returns:
            Configured embedding provider

        Raises:
            ValueError: If provider is not supported
        """
        provider_name = config.embedding_provider

        if provider_name == "ollama":
            return OllamaClient(config.ollama, console)
        elif provider_name == "voyage-ai":
            return VoyageAIClient(config.voyage_ai, console)
        else:
            raise ValueError(
                f"Unsupported embedding provider: {provider_name}. "
                f"Supported providers: ollama, voyage-ai"
            )

    @staticmethod
    def get_available_providers() -> List[str]:
        """Get list of available embedding providers."""
        return ["ollama", "voyage-ai"]

    @staticmethod
    def get_provider_info() -> Dict[str, Dict[str, Any]]:
        """Get information about available providers."""
        return {
            "ollama": {
                "name": "Ollama",
                "description": "Local AI models via Ollama",
                "type": "local",
                "requires_api_key": False,
                "supports_batch": False,
                "parallel_capable": False,
            },
            "voyage-ai": {
                "name": "VoyageAI",
                "description": "High-quality embeddings via VoyageAI API",
                "type": "cloud",
                "requires_api_key": True,
                "api_key_env": "VOYAGE_API_KEY",
                "supports_batch": True,
                "parallel_capable": True,
                "default_model": "voyage-code-3",
            },
        }
