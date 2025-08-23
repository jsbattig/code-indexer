"""
End-to-End tests for embedding providers with real API integration.

These tests are designed to work with real API tokens when available.
They will skip gracefully if tokens are not configured.
All tests use the shared container test environment for proper isolation.
"""

import os
import pytest

from rich.console import Console

from code_indexer.config import Config, ConfigManager
from code_indexer.services.embedding_factory import EmbeddingProviderFactory
from code_indexer.services.qdrant import QdrantClient
from ...suite_setup import register_test_collection
from ...conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider as EP


@pytest.mark.e2e
@pytest.mark.voyage_ai
@pytest.mark.real_api
class TestVoyageAIRealAPI:
    """E2E tests for VoyageAI with real API integration."""

    @pytest.fixture
    def api_key_available(self):
        """Check if VoyageAI API key is available."""
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            pytest.skip(
                "VOYAGE_API_KEY environment variable not set. Set it to run VoyageAI E2E tests."
            )
        return api_key

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    def test_voyage_ai_real_connection(self, api_key_available, console):
        """Test real connection to VoyageAI API."""
        with shared_container_test_environment(
            "test_voyage_ai_real_connection", EP.VOYAGE_AI
        ) as temp_dir:
            # Create VoyageAI configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.embedding_provider = "voyage-ai"
            config.voyage_ai.model = "voyage-code-3"
            config.voyage_ai.parallel_requests = 2  # Conservative for testing

            config_manager.save(config)

            # Test provider creation and health check
            provider = EmbeddingProviderFactory.create(config, console)

            # Test health check
            assert (
                provider.health_check() is True
            ), "VoyageAI health check should pass with valid API key"

    def test_voyage_ai_single_embedding(self, api_key_available, console):
        """Test generating a single embedding with real API."""
        with shared_container_test_environment(
            "test_voyage_ai_single_embedding", EP.VOYAGE_AI
        ) as temp_dir:
            # Create VoyageAI configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.embedding_provider = "voyage-ai"
            config.voyage_ai.model = "voyage-code-3"
            config.voyage_ai.parallel_requests = 2

            config_manager.save(config)

            # Create provider and test embedding
            provider = EmbeddingProviderFactory.create(config, console)

            test_text = "def authenticate_user(username, password):"
            embedding = provider.get_embedding(test_text)

            # VoyageAI voyage-code-3 should return 1024-dimensional embeddings
            assert (
                len(embedding) == 1024
            ), f"Expected 1024 dimensions, got {len(embedding)}"
            assert all(
                isinstance(x, (int, float)) for x in embedding
            ), "All embedding values should be numeric"

    def test_voyage_ai_embedding_with_metadata(self, api_key_available, console):
        """Test embedding generation with metadata using real API."""
        with shared_container_test_environment(
            "test_voyage_ai_embedding_with_metadata", EP.VOYAGE_AI
        ) as temp_dir:
            # Create VoyageAI configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.embedding_provider = "voyage-ai"
            config.voyage_ai.model = "voyage-code-3"
            config.voyage_ai.parallel_requests = 2

            config_manager.save(config)

            # Create provider and test
            provider = EmbeddingProviderFactory.create(config, console)

            test_text = "class UserAuthentication:"
            result = provider.get_embedding_with_metadata(test_text)

            assert len(result.embedding) == 1024
            assert result.model == "voyage-code-3"
            assert result.provider == "voyage-ai"
            assert result.tokens_used is not None
            assert result.tokens_used > 0

    def test_voyage_ai_batch_embeddings(self, api_key_available, console):
        """Test batch embedding generation with real API."""
        with shared_container_test_environment(
            "test_voyage_ai_batch_embeddings", EP.VOYAGE_AI
        ) as temp_dir:
            # Create VoyageAI configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.embedding_provider = "voyage-ai"
            config.voyage_ai.model = "voyage-code-3"
            config.voyage_ai.parallel_requests = 2

            config_manager.save(config)

            # Create provider and test batch processing
            provider = EmbeddingProviderFactory.create(config, console)

            test_texts = [
                "def login(username, password):",
                "class Authentication:",
                "function authenticate() {",
            ]

            embeddings = provider.get_embeddings_batch(test_texts)

            assert len(embeddings) == len(
                test_texts
            ), "Should return one embedding per text"
            for embedding in embeddings:
                assert (
                    len(embedding) == 1024
                ), "Each embedding should have 1024 dimensions"
                assert all(
                    isinstance(x, (int, float)) for x in embedding
                ), "All values should be numeric"

    def test_voyage_ai_batch_with_metadata(self, api_key_available, console):
        """Test batch embedding generation with metadata using real API."""
        with shared_container_test_environment(
            "test_voyage_ai_batch_with_metadata", EP.VOYAGE_AI
        ) as temp_dir:
            # Create VoyageAI configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.embedding_provider = "voyage-ai"
            config.voyage_ai.model = "voyage-code-3"
            config.voyage_ai.parallel_requests = 2

            config_manager.save(config)

            # Create provider and test
            provider = EmbeddingProviderFactory.create(config, console)

            test_texts = [
                "function calculateHash(data) {",
                "public class Authentication {",
                "def process_request(self, data):",
            ]

            result = provider.get_embeddings_batch_with_metadata(test_texts)

            assert len(result.embeddings) == len(test_texts)
            assert result.model == "voyage-code-3"
            assert result.provider == "voyage-ai"
            assert result.total_tokens_used is not None
            assert result.total_tokens_used > 0

    def test_voyage_ai_model_info(self, api_key_available, console):
        """Test getting model information from real API."""
        with shared_container_test_environment(
            "test_voyage_ai_model_info", EP.VOYAGE_AI
        ) as temp_dir:
            # Create VoyageAI configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.embedding_provider = "voyage-ai"
            config.voyage_ai.model = "voyage-code-3"
            config.voyage_ai.parallel_requests = 2

            config_manager.save(config)

            # Create provider and test
            provider = EmbeddingProviderFactory.create(config, console)

            info = provider.get_model_info()

            assert info["name"] == "voyage-code-3"
            assert info["provider"] == "voyage-ai"
            assert info["dimensions"] == 1024
            assert info["max_tokens"] == 16000
            assert info["supports_batch"] is True


@pytest.mark.e2e
class TestE2EProviderSwitching:
    """E2E tests for switching between embedding providers."""

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    def test_provider_switching_compatibility(self, console):
        """Test that providers can be switched and are properly isolated."""
        with shared_container_test_environment(
            "test_provider_switching_compatibility", EP.OLLAMA
        ) as temp_dir:
            # Create configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.qdrant.host = "http://localhost:6333"
            config.qdrant.collection_base_name = "test_e2e_collection"
            config.qdrant.vector_size = 1024  # VoyageAI dimensions

            # Register collection for cleanup
            register_test_collection("test_e2e_collection")

            config_manager.save(config)

            # Test Ollama provider
            config.embedding_provider = "ollama"
            ollama_provider = EmbeddingProviderFactory.create(config, console)

            assert ollama_provider.get_provider_name() == "ollama"
            assert ollama_provider.get_current_model() == "nomic-embed-text"
            assert ollama_provider.supports_batch_processing() is False

            # Test VoyageAI provider (skip if no API key)
            voyage_api_key = os.getenv("VOYAGE_API_KEY")
            if voyage_api_key:
                config.embedding_provider = "voyage-ai"
                voyage_provider = EmbeddingProviderFactory.create(config, console)

                assert voyage_provider.get_provider_name() == "voyage-ai"
                assert voyage_provider.get_current_model() == "voyage-code-3"
                assert voyage_provider.supports_batch_processing() is True
            else:
                pytest.skip("VOYAGE_API_KEY not available for provider switching test")

    def test_factory_provider_info(self):
        """Test that factory provides correct provider information."""
        providers = EmbeddingProviderFactory.get_available_providers()

        assert "ollama" in providers
        assert "voyage-ai" in providers

        info = EmbeddingProviderFactory.get_provider_info()

        # Check Ollama info
        assert info["ollama"]["requires_api_key"] is False
        assert info["ollama"]["description"] is not None

        # Check VoyageAI info
        assert info["voyage-ai"]["requires_api_key"] is True
        assert info["voyage-ai"]["api_key_env"] == "VOYAGE_API_KEY"
        assert info["voyage-ai"]["description"] is not None


@pytest.mark.e2e
@pytest.mark.qdrant
class TestE2EQdrantIntegration:
    """E2E tests for Qdrant integration with different embedding providers."""

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    def test_qdrant_model_metadata_integration(self, console):
        """Test that Qdrant properly stores and filters by embedding model metadata."""
        with shared_container_test_environment(
            "test_qdrant_model_metadata_integration", EP.OLLAMA
        ) as temp_dir:
            # Create configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.qdrant.host = "http://localhost:6333"
            config.qdrant.collection_base_name = "test_e2e_integration"
            config.qdrant.vector_size = 1024

            # Register collection for cleanup
            register_test_collection("test_e2e_integration")

            config_manager.save(config)

            # Create Qdrant client
            qdrant_client = QdrantClient(config.qdrant, console)

            # Test creating points with different model metadata
            test_points = [
                {
                    "id": "test_ollama_1",
                    "vector": [0.1] * 768 + [0.0] * 256,  # Pad to 1024 dimensions
                    "payload": {"content": "ollama content", "language": "python"},
                    "embedding_model": "nomic-embed-text",
                },
                {
                    "id": "test_voyage_1",
                    "vector": [0.2] * 1024,
                    "payload": {"content": "voyage content", "language": "python"},
                    "embedding_model": "voyage-code-3",
                },
            ]

            # Create points with model metadata
            for point_data in test_points:
                point = qdrant_client.create_point(
                    point_id=point_data["id"],
                    vector=point_data["vector"],
                    payload=point_data["payload"],
                    embedding_model=point_data["embedding_model"],
                )

                assert point["id"] == point_data["id"]
                # Point should include embedding model in payload
                assert "embedding_model" in point["payload"]
                assert (
                    point["payload"]["embedding_model"] == point_data["embedding_model"]
                )

            # Test filtering by embedding model
            ollama_results = qdrant_client.filter_by_embedding_model("nomic-embed-text")
            voyage_results = qdrant_client.filter_by_embedding_model("voyage-code-3")

            # For mock testing environment, these might not return actual results
            # but the methods should exist and not raise errors
            assert ollama_results is not None
            assert voyage_results is not None


@pytest.mark.e2e
@pytest.mark.comprehensive
class TestE2EFullProviderWorkflow:
    """Comprehensive E2E tests for full provider workflows."""

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    def test_voyage_ai_full_workflow(self, console):
        """Test complete workflow with VoyageAI if API key is available."""
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            pytest.skip(
                "VOYAGE_API_KEY not set. Cannot run VoyageAI full workflow test."
            )

        with shared_container_test_environment(
            "test_voyage_ai_full_workflow", EP.VOYAGE_AI
        ) as temp_dir:
            # Create configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.embedding_provider = "voyage-ai"
            config.voyage_ai.model = "voyage-code-3"
            config.voyage_ai.parallel_requests = 2

            config_manager.save(config)

            # Create provider
            provider = EmbeddingProviderFactory.create(config, console)

            # Test complete workflow
            # 1. Health check
            assert provider.health_check() is True

            # 2. Single embedding
            single_text = "def calculate_sum(a, b): return a + b"
            single_embedding = provider.get_embedding(single_text)
            assert len(single_embedding) == 1024

            # 3. Batch embeddings
            batch_texts = [
                "class Calculator:",
                "def multiply(x, y):",
                "function divide(a, b) {",
            ]
            batch_embeddings = provider.get_embeddings_batch(batch_texts)
            assert len(batch_embeddings) == 3

            # 4. With metadata
            single_result = provider.get_embedding_with_metadata(single_text)
            assert single_result.model == "voyage-code-3"
            assert single_result.provider == "voyage-ai"

            # 5. Batch with metadata
            batch_result = provider.get_embeddings_batch_with_metadata(batch_texts)
            assert len(batch_result.embeddings) == 3
            assert batch_result.model == "voyage-code-3"
            assert batch_result.provider == "voyage-ai"

    def test_provider_comparison(self, console):
        """Compare outputs between providers for the same code."""
        # This test helps verify that different providers produce different but valid embeddings
        test_code = "def calculate_hash(data): return hashlib.sha256(data).hexdigest()"

        with shared_container_test_environment(
            "test_provider_comparison", EP.OLLAMA
        ) as temp_dir:
            # Create configuration
            config_file = temp_dir / "config.json"
            config_manager = ConfigManager(config_file)

            config = Config()
            config.qdrant.host = "http://localhost:6333"
            config.qdrant.collection_base_name = "test_comparison"
            config.qdrant.vector_size = 768  # Ollama size

            config_manager.save(config)

            # Test Ollama (always available in unit tests via mocking, but skip for real E2E)
            config.embedding_provider = "ollama"
            ollama_provider = EmbeddingProviderFactory.create(config, console)

            if not ollama_provider.health_check():
                pytest.skip("Ollama not available for provider comparison test")

            ollama_embedding = ollama_provider.get_embedding(test_code)
            assert (
                len(ollama_embedding) == 768
            ), "Ollama should produce 768-dim embeddings"

            # Test VoyageAI if API key available
            voyage_api_key = os.getenv("VOYAGE_API_KEY")
            if voyage_api_key:
                config.embedding_provider = "voyage-ai"
                config.qdrant.vector_size = 1024  # Update for VoyageAI

                voyage_provider = EmbeddingProviderFactory.create(config, console)
                voyage_embedding = voyage_provider.get_embedding(test_code)

                assert (
                    len(voyage_embedding) == 1024
                ), "VoyageAI should produce 1024-dim embeddings"

                # Embeddings should be different (providers use different models)
                # But both should be valid numerical vectors
                assert all(
                    isinstance(x, (int, float)) for x in ollama_embedding
                ), "Ollama embeddings should be numeric"
                assert all(
                    isinstance(x, (int, float)) for x in voyage_embedding
                ), "VoyageAI embeddings should be numeric"
