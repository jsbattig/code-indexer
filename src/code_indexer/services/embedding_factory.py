"""Factory for creating embedding providers based on configuration."""

import re
from typing import Optional, List, Dict, Any
from rich.console import Console

from ..config import Config
from .embedding_provider import EmbeddingProvider
from .voyage_ai import VoyageAIClient


class EmbeddingProviderFactory:
    """Factory for creating embedding providers."""

    @staticmethod
    def generate_model_slug(provider_name: str, model_name: str) -> str:
        """Convert model names to filesystem-safe collection name components.

        Args:
            provider_name: Name of the embedding provider (e.g., 'voyage-ai')
            model_name: Name of the model (e.g., 'voyage-code-2', 'voyage-code-3')

        Returns:
            Filesystem-safe slug for use in collection names

        Examples:
            generate_model_slug('voyage-ai', 'voyage-code-2') -> 'voyage_ai_voyage_code_2'
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
        base_name: str,
        provider_name: str,
        model_name: str,
        project_id: Optional[str] = None,
    ) -> str:
        """Generate collection name based on provider, model, and project.

        Args:
            base_name: Base collection name (e.g., 'code_index')
            provider_name: Name of the embedding provider
            model_name: Name of the model
            project_id: Optional project identifier for isolation

        Returns:
            Full collection name for the provider, model, and project

        Examples:
            generate_collection_name('code_index', 'voyage', 'nomic-embed-text')
            -> 'code_index_voyage_nomic_embed_text'

            generate_collection_name('code_index', 'voyage-ai', 'voyage-code-3', 'abc123')
            -> 'code_index_abc123_voyage_code_3'
        """
        model_slug = EmbeddingProviderFactory.generate_model_slug(
            provider_name, model_name
        )

        if project_id:
            return f"{base_name}_{project_id}_{model_slug}"
        else:
            return f"{base_name}_{model_slug}"

    @staticmethod
    def generate_project_id(codebase_dir: str) -> str:
        """Generate a project identifier from codebase directory.

        Args:
            codebase_dir: Path to the codebase directory

        Returns:
            Short hash-based project identifier for collection naming
        """
        import hashlib
        from pathlib import Path

        # Use absolute path for consistent hashing
        abs_path = str(Path(codebase_dir).resolve())

        # Generate short hash (8 characters should be sufficient for project isolation)
        hash_obj = hashlib.sha256(abs_path.encode())
        return hash_obj.hexdigest()[:8]

    @staticmethod
    def get_provider_model_info(config: Config) -> Dict[str, Any]:
        """Get current provider and model information.

        Args:
            config: Main configuration object

        Returns:
            Dictionary containing provider name, model name, and model info
        """
        provider_name = config.embedding_provider

        # Only VoyageAI is supported in v8.0+
        if provider_name != "voyage-ai":
            raise ValueError(
                f"Embedding provider '{provider_name}' is no longer supported.\n"
                "Code-indexer v8.0+ only supports VoyageAI embeddings.\n"
                "Please update your configuration to use VoyageAI."
            )

        provider = VoyageAIClient(config.voyage_ai, None)
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

        # Only VoyageAI is supported in v8.0+
        if provider_name != "voyage-ai":
            raise ValueError(
                f"Embedding provider '{provider_name}' is no longer supported.\n"
                "Code-indexer v8.0+ only supports VoyageAI embeddings.\n"
                "Please update your configuration to use VoyageAI."
            )

        return VoyageAIClient(config.voyage_ai, console)

    @staticmethod
    def get_available_providers() -> List[str]:
        """Get list of available embedding providers.

        As of v8.0+, only VoyageAI is supported.
        """
        return ["voyage-ai"]

    @staticmethod
    def get_provider_info() -> Dict[str, Dict[str, Any]]:
        """Get information about available providers.

        As of v8.0+, only VoyageAI is supported.
        """
        return {
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
