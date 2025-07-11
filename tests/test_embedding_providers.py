"""
Unit tests for embedding providers with mocked implementations.
"""

import os
import pytest
from unittest.mock import Mock, patch
import httpx
from rich.console import Console

from code_indexer.config import Config, OllamaConfig, VoyageAIConfig
from code_indexer.services.embedding_provider import EmbeddingProvider, EmbeddingResult
from code_indexer.services.ollama import OllamaClient
from code_indexer.services.voyage_ai import VoyageAIClient
from code_indexer.services.embedding_factory import EmbeddingProviderFactory


class TestEmbeddingProviderInterface:
    """Test the abstract embedding provider interface."""

    def test_abstract_interface(self):
        """Test that EmbeddingProvider is properly abstract."""
        with pytest.raises(TypeError):
            EmbeddingProvider()


class TestOllamaClient:
    """Test OllamaClient implementation."""

    @pytest.fixture
    def ollama_config(self):
        return OllamaConfig(
            host="http://localhost:11434", model="nomic-embed-text", timeout=30
        )

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def ollama_client(self, ollama_config, console):
        return OllamaClient(ollama_config, console)

    def test_initialization(self, ollama_client, ollama_config):
        """Test OllamaClient initialization."""
        assert ollama_client.config == ollama_config
        assert ollama_client.get_provider_name() == "ollama"
        assert ollama_client.get_current_model() == "nomic-embed-text"
        assert not ollama_client.supports_batch_processing()

    @patch("httpx.Client.get")
    def test_health_check_success(self, mock_get, ollama_client):
        """Test successful health check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        assert ollama_client.health_check() is True

    @patch("httpx.Client.get")
    def test_health_check_failure(self, mock_get, ollama_client):
        """Test failed health check."""
        mock_get.side_effect = Exception("Connection failed")

        assert ollama_client.health_check() is False

    @patch("httpx.Client.post")
    def test_get_embedding_success(self, mock_post, ollama_client):
        """Test successful embedding generation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3, 0.4]}
        mock_post.return_value = mock_response

        embedding = ollama_client.get_embedding("test text")

        assert embedding == [0.1, 0.2, 0.3, 0.4]
        mock_post.assert_called_once()

    @patch("httpx.Client.post")
    def test_get_embedding_with_metadata(self, mock_post, ollama_client):
        """Test embedding generation with metadata."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3, 0.4]}
        mock_post.return_value = mock_response

        result = ollama_client.get_embedding_with_metadata("test text")

        assert isinstance(result, EmbeddingResult)
        assert result.embedding == [0.1, 0.2, 0.3, 0.4]
        assert result.model == "nomic-embed-text"
        assert result.provider == "ollama"
        assert result.tokens_used is None  # Ollama doesn't provide token usage

    @patch("httpx.Client.post")
    def test_get_embeddings_batch(self, mock_post, ollama_client):
        """Test batch embedding generation (sequential for Ollama)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3, 0.4]}
        mock_post.return_value = mock_response

        texts = ["text1", "text2", "text3"]
        embeddings = ollama_client.get_embeddings_batch(texts)

        assert len(embeddings) == 3
        assert all(embedding == [0.1, 0.2, 0.3, 0.4] for embedding in embeddings)
        assert mock_post.call_count == 3  # Sequential calls

    @patch("httpx.Client.post")
    def test_get_embedding_model_not_found(self, mock_post, ollama_client):
        """Test embedding generation with model not found error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=Mock(), response=mock_response
        )
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="Model nomic-embed-text not found"):
            ollama_client.get_embedding("test text")

    def test_get_model_info(self, ollama_client):
        """Test getting model information."""
        info = ollama_client.get_model_info()

        assert info["name"] == "nomic-embed-text"
        assert info["provider"] == "ollama"
        assert info["dimensions"] == 768


class TestVoyageAIClient:
    """Test VoyageAIClient implementation with mocking."""

    @pytest.fixture
    def voyage_config(self):
        return VoyageAIConfig(
            model="voyage-code-3",
            parallel_requests=4,
            batch_size=64,
        )

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def mock_api_key(self):
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "test_api_key"}):
            yield "test_api_key"

    @pytest.fixture
    def voyage_client(self, voyage_config, console, mock_api_key):
        return VoyageAIClient(voyage_config, console)

    def test_initialization_no_api_key(self, voyage_config, console):
        """Test VoyageAIClient initialization without API key."""
        # Only remove the specific environment variable we're testing, don't clear everything
        # Use a context manager that temporarily removes just VOYAGE_API_KEY
        original_key = os.environ.get("VOYAGE_API_KEY")
        if "VOYAGE_API_KEY" in os.environ:
            del os.environ["VOYAGE_API_KEY"]
        try:
            with pytest.raises(
                ValueError, match="VOYAGE_API_KEY environment variable is required"
            ):
                VoyageAIClient(voyage_config, console)
        finally:
            # Restore the original value
            if original_key is not None:
                os.environ["VOYAGE_API_KEY"] = original_key

    def test_initialization_with_api_key(self, voyage_client, voyage_config):
        """Test VoyageAIClient initialization with API key."""
        assert voyage_client.config == voyage_config
        assert voyage_client.get_provider_name() == "voyage-ai"
        assert voyage_client.get_current_model() == "voyage-code-3"
        assert voyage_client.supports_batch_processing() is True

    @patch("code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request")
    def test_health_check_success(self, mock_request, voyage_client):
        """Test successful health check."""
        mock_request.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

        assert voyage_client.health_check() is True

    @patch("code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request")
    def test_health_check_failure(self, mock_request, voyage_client):
        """Test failed health check."""
        mock_request.side_effect = Exception("API error")

        assert voyage_client.health_check(test_api=True) is False

    @patch("code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request")
    def test_get_embedding_success(self, mock_request, voyage_client):
        """Test successful embedding generation."""
        mock_request.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
            "usage": {"total_tokens": 10},
        }

        embedding = voyage_client.get_embedding("test text")

        assert embedding == [0.1, 0.2, 0.3, 0.4]
        mock_request.assert_called_once_with(["test text"], None)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request")
    def test_get_embedding_with_metadata(self, mock_request, voyage_client):
        """Test embedding generation with metadata."""
        mock_request.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
            "usage": {"total_tokens": 10},
        }

        result = voyage_client.get_embedding_with_metadata("test text")

        assert isinstance(result, EmbeddingResult)
        assert result.embedding == [0.1, 0.2, 0.3, 0.4]
        assert result.model == "voyage-code-3"
        assert result.provider == "voyage-ai"
        assert result.tokens_used == 10

    @patch("code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request")
    def test_get_embeddings_batch_single_request(self, mock_request, voyage_client):
        """Test batch embedding generation in single request."""
        mock_request.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3, 0.4]},
                {"embedding": [0.5, 0.6, 0.7, 0.8]},
                {"embedding": [0.9, 1.0, 1.1, 1.2]},
            ],
            "usage": {"total_tokens": 30},
        }

        texts = ["text1", "text2", "text3"]
        embeddings = voyage_client.get_embeddings_batch(texts)

        assert len(embeddings) == 3
        assert embeddings[0] == [0.1, 0.2, 0.3, 0.4]
        assert embeddings[1] == [0.5, 0.6, 0.7, 0.8]
        assert embeddings[2] == [0.9, 1.0, 1.1, 1.2]
        mock_request.assert_called_once_with(texts, None)

    def test_get_model_info(self, voyage_client):
        """Test getting model information."""
        info = voyage_client.get_model_info()

        assert info["name"] == "voyage-code-3"
        assert info["provider"] == "voyage-ai"
        assert info["dimensions"] == 1024  # voyage-code-3 dimensions
        assert info["max_tokens"] == 16000
        assert info["supports_batch"] is True


class TestEmbeddingProviderFactory:
    """Test EmbeddingProviderFactory."""

    @pytest.fixture
    def config_ollama(self):
        config = Config()
        config.embedding_provider = "ollama"
        return config

    @pytest.fixture
    def config_voyage_ai(self):
        config = Config()
        config.embedding_provider = "voyage-ai"
        return config

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    def test_create_ollama_provider(self, config_ollama, console):
        """Test creating Ollama provider."""
        provider = EmbeddingProviderFactory.create(config_ollama, console)

        assert isinstance(provider, OllamaClient)
        assert provider.get_provider_name() == "ollama"

    def test_create_voyage_ai_provider(self, config_voyage_ai, console):
        """Test creating VoyageAI provider."""
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "test_key"}):
            provider = EmbeddingProviderFactory.create(config_voyage_ai, console)

            assert isinstance(provider, VoyageAIClient)
            assert provider.get_provider_name() == "voyage-ai"

    def test_create_unsupported_provider(self, console):
        """Test creating unsupported provider."""
        config = Config()
        config.embedding_provider = "unsupported"

        with pytest.raises(ValueError, match="Unsupported embedding provider"):
            EmbeddingProviderFactory.create(config, console)

    def test_get_available_providers(self):
        """Test getting available providers."""
        providers = EmbeddingProviderFactory.get_available_providers()

        assert "ollama" in providers
        assert "voyage-ai" in providers

    def test_get_provider_info(self):
        """Test getting provider information."""
        info = EmbeddingProviderFactory.get_provider_info()

        assert "ollama" in info
        assert "voyage-ai" in info
        assert info["ollama"]["requires_api_key"] is False
        assert info["voyage-ai"]["requires_api_key"] is True
        assert info["voyage-ai"]["api_key_env"] == "VOYAGE_API_KEY"


class TestEmbeddingProviderIntegration:
    """Integration tests for embedding providers."""

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    def test_ollama_provider_workflow(self, console):
        """Test complete Ollama provider workflow."""
        config = Config()
        config.embedding_provider = "ollama"

        with patch("httpx.Client.get") as mock_get, patch(
            "httpx.Client.post"
        ) as mock_post:
            # Mock health check
            mock_get.return_value.status_code = 200

            # Mock embedding generation
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "embedding": [0.1, 0.2, 0.3, 0.4]
            }

            provider = EmbeddingProviderFactory.create(config, console)

            # Test health check
            assert provider.health_check() is True

            # Test embedding generation
            embedding = provider.get_embedding("test text")
            assert embedding == [0.1, 0.2, 0.3, 0.4]

            # Test metadata generation
            result = provider.get_embedding_with_metadata("test text")
            assert result.embedding == [0.1, 0.2, 0.3, 0.4]
            assert result.model == "nomic-embed-text"
            assert result.provider == "ollama"

    def test_voyage_ai_provider_workflow(self, console):
        """Test complete VoyageAI provider workflow."""
        config = Config()
        config.embedding_provider = "voyage-ai"

        with patch.dict(os.environ, {"VOYAGE_API_KEY": "test_key"}), patch(
            "code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request"
        ) as mock_request:
            # Mock API responses
            mock_request.return_value = {
                "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
                "usage": {"total_tokens": 10},
            }

            provider = EmbeddingProviderFactory.create(config, console)

            # Test health check
            assert provider.health_check() is True

            # Test embedding generation
            embedding = provider.get_embedding("test text")
            assert embedding == [0.1, 0.2, 0.3, 0.4]

            # Test metadata generation
            result = provider.get_embedding_with_metadata("test text")
            assert result.embedding == [0.1, 0.2, 0.3, 0.4]
            assert result.model == "voyage-code-3"
            assert result.provider == "voyage-ai"
            assert result.tokens_used == 10
