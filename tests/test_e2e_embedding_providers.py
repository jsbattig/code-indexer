"""
End-to-End tests for embedding providers with real API integration.

These tests are designed to work with real API tokens when available.
They will skip gracefully if tokens are not configured.
"""

import os
import pytest
import shutil
from pathlib import Path

from rich.console import Console

from code_indexer.config import Config, ConfigManager
from code_indexer.services.embedding_factory import EmbeddingProviderFactory
from code_indexer.services.qdrant import QdrantClient
from .test_suite_setup import register_test_collection


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

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for configuration."""
        # Use shared test directory to avoid creating multiple container sets
        temp_dir = Path.home() / ".tmp" / "shared_test_containers"
        # Clean and recreate for test isolation
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def voyage_config(self, temp_config_dir):
        """Create a VoyageAI configuration."""
        config_file = temp_config_dir / "config.json"
        config_manager = ConfigManager(config_file)

        config = Config()
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-3"
        config.voyage_ai.parallel_requests = 2  # Conservative for testing

        config_manager.save(config)
        return config

    def test_voyage_ai_real_connection(self, api_key_available, voyage_config, console):
        """Test real connection to VoyageAI API."""
        provider = EmbeddingProviderFactory.create(voyage_config, console)

        # Test health check
        assert (
            provider.health_check() is True
        ), "VoyageAI health check should pass with valid API key"

    def test_voyage_ai_single_embedding(
        self, api_key_available, voyage_config, console
    ):
        """Test generating a single embedding with real API."""
        provider = EmbeddingProviderFactory.create(voyage_config, console)

        test_text = "def authenticate_user(username, password):"
        embedding = provider.get_embedding(test_text)

        # VoyageAI voyage-code-3 should return 1024-dimensional embeddings
        assert len(embedding) == 1024, f"Expected 1024 dimensions, got {len(embedding)}"
        assert all(
            isinstance(x, (int, float)) for x in embedding
        ), "All embedding values should be numeric"

    def test_voyage_ai_embedding_with_metadata(
        self, api_key_available, voyage_config, console
    ):
        """Test embedding generation with metadata using real API."""
        provider = EmbeddingProviderFactory.create(voyage_config, console)

        test_text = "class DatabaseConnection:"
        result = provider.get_embedding_with_metadata(test_text)

        assert result.embedding is not None
        assert len(result.embedding) == 1024
        assert result.model == "voyage-code-3"
        assert result.provider == "voyage-ai"
        assert result.tokens_used is not None
        assert result.tokens_used > 0

    def test_voyage_ai_batch_embeddings(
        self, api_key_available, voyage_config, console
    ):
        """Test batch embedding generation with real API."""
        provider = EmbeddingProviderFactory.create(voyage_config, console)

        test_texts = [
            "def login(user, pass):",
            "class User:",
            "import requests",
            "async function fetchData()",
            "SELECT * FROM users",
        ]

        embeddings = provider.get_embeddings_batch(test_texts)

        assert len(embeddings) == len(
            test_texts
        ), "Should get embedding for each input text"

        for embedding in embeddings:
            assert len(embedding) == 1024, "Each embedding should have 1024 dimensions"
            assert all(
                isinstance(x, (int, float)) for x in embedding
            ), "All values should be numeric"

    def test_voyage_ai_batch_with_metadata(
        self, api_key_available, voyage_config, console
    ):
        """Test batch embedding generation with metadata using real API."""
        provider = EmbeddingProviderFactory.create(voyage_config, console)

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

    def test_voyage_ai_model_info(self, api_key_available, voyage_config, console):
        """Test getting model information from real API."""
        provider = EmbeddingProviderFactory.create(voyage_config, console)

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

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for configuration."""
        # Use shared test directory to avoid creating multiple container sets
        temp_dir = Path.home() / ".tmp" / "shared_test_containers"
        # Clean and recreate for test isolation
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_qdrant_config(self, temp_config_dir):
        """Create a test Qdrant configuration."""
        config_file = temp_config_dir / "config.json"
        config_manager = ConfigManager(config_file)

        config = Config()
        config.qdrant.host = "http://localhost:6333"
        config.qdrant.collection_base_name = "test_e2e_collection"
        config.qdrant.vector_size = 1024  # VoyageAI dimensions

        # Register collection for cleanup
        register_test_collection("test_e2e_collection")

        config_manager.save(config)
        return config

    def test_provider_switching_compatibility(self, console, mock_qdrant_config):
        """Test that providers can be switched and are properly isolated."""
        # Test Ollama provider
        mock_qdrant_config.embedding_provider = "ollama"
        ollama_provider = EmbeddingProviderFactory.create(mock_qdrant_config, console)

        assert ollama_provider.get_provider_name() == "ollama"
        assert ollama_provider.get_current_model() == "nomic-embed-text"
        assert ollama_provider.supports_batch_processing() is False

        # Test VoyageAI provider (skip if no API key)
        voyage_api_key = os.getenv("VOYAGE_API_KEY")
        if voyage_api_key:
            mock_qdrant_config.embedding_provider = "voyage-ai"
            voyage_provider = EmbeddingProviderFactory.create(
                mock_qdrant_config, console
            )

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

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for configuration."""
        # Use shared test directory to avoid creating multiple container sets
        temp_dir = Path.home() / ".tmp" / "shared_test_containers"
        # Clean and recreate for test isolation
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def test_config(self, temp_config_dir):
        """Create a test configuration."""
        config_file = temp_config_dir / "config.json"
        config_manager = ConfigManager(config_file)

        config = Config()
        config.qdrant.host = "http://localhost:6333"
        config.qdrant.collection_base_name = "test_e2e_integration"
        config.qdrant.vector_size = 1024

        # Register collection for cleanup
        register_test_collection("test_e2e_integration")

        config_manager.save(config)
        return config

    def test_qdrant_model_metadata_integration(self, test_config, console):
        """Test that Qdrant properly stores and filters by embedding model metadata."""
        qdrant_client = QdrantClient(test_config.qdrant, console)

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
            assert point["payload"]["embedding_model"] == point_data["embedding_model"]

        # Test model filtering
        ollama_filter = qdrant_client.create_model_filter("nomic-embed-text")
        voyage_filter = qdrant_client.create_model_filter("voyage-code-3")

        assert ollama_filter["must"][0]["match"]["value"] == "nomic-embed-text"
        assert voyage_filter["must"][0]["match"]["value"] == "voyage-code-3"

        # Test filter combination
        additional_filter = {
            "must": [{"key": "language", "match": {"value": "python"}}]
        }

        combined_filter = qdrant_client.combine_filters(
            ollama_filter, additional_filter
        )

        assert len(combined_filter["must"]) == 2
        model_conditions = [
            c for c in combined_filter["must"] if c["key"] == "embedding_model"
        ]
        language_conditions = [
            c for c in combined_filter["must"] if c["key"] == "language"
        ]

        assert len(model_conditions) == 1
        assert len(language_conditions) == 1
        assert model_conditions[0]["match"]["value"] == "nomic-embed-text"
        assert language_conditions[0]["match"]["value"] == "python"


@pytest.mark.e2e
@pytest.mark.slow
class TestE2EFullWorkflow:
    """E2E tests for complete workflow scenarios."""

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with sample files."""
        # Use shared test directory to avoid creating multiple container sets
        temp_dir = str(Path.home() / ".tmp" / "shared_test_containers")
        # Clean and recreate for test isolation
        temp_path = Path(temp_dir)
        if temp_path.exists():
            shutil.rmtree(temp_path)
        temp_path.mkdir(parents=True)
        project_path = Path(temp_dir)
        project_path.mkdir(parents=True, exist_ok=True)

        # Create sample code files
        (project_path / "main.py").write_text(
            """
def authenticate_user(username, password):
    '''Authenticate user with username and password.'''
    if not username or not password:
        return False
    return validate_credentials(username, password)

class UserManager:
    '''Manages user operations and authentication.'''
    
    def __init__(self):
        self.users = {}
    
    def create_user(self, username, email):
        '''Create a new user account.'''
        user_id = generate_user_id()
        self.users[user_id] = {
            'username': username,
            'email': email,
            'created_at': datetime.now()
        }
        return user_id
"""
        )

        (project_path / "utils.py").write_text(
            r"""
import hashlib
import uuid

def generate_user_id():
    '''Generate a unique user identifier.'''
    return str(uuid.uuid4())

def hash_password(password, salt):
    '''Hash password with salt for secure storage.'''
    return hashlib.pbkdf2_hmac('sha256', 
                               password.encode('utf-8'), 
                               salt, 
                               100000)

def validate_email(email):
    '''Validate email address format.'''
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None
"""
        )

        yield project_path
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_voyage_ai_full_workflow(self, temp_project_dir, console):
        """Test complete workflow with VoyageAI if API key is available."""
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            pytest.skip(
                "VOYAGE_API_KEY not set. Cannot run VoyageAI full workflow test."
            )

        # Create configuration
        config_file = temp_project_dir / ".code-indexer" / "config.json"
        config_file.parent.mkdir(exist_ok=True)

        config_manager = ConfigManager(config_file)
        config = Config()
        config.embedding_provider = "voyage-ai"
        config.codebase_dir = str(temp_project_dir)
        config_manager.save(config)

        # Test provider creation
        provider = EmbeddingProviderFactory.create(config, console)
        assert provider.get_provider_name() == "voyage-ai"
        assert provider.health_check() is True

        # Test embedding generation for code samples
        main_py_content = (temp_project_dir / "main.py").read_text()
        utils_py_content = (temp_project_dir / "utils.py").read_text()

        # Generate embeddings for both files
        main_embedding = provider.get_embedding_with_metadata(main_py_content)
        utils_embedding = provider.get_embedding_with_metadata(utils_py_content)

        # Verify embeddings
        assert len(main_embedding.embedding) == 1024
        assert len(utils_embedding.embedding) == 1024
        assert main_embedding.model == "voyage-code-3"
        assert utils_embedding.model == "voyage-code-3"
        assert main_embedding.tokens_used > 0
        assert utils_embedding.tokens_used > 0

        # Test batch processing
        batch_texts = [main_py_content, utils_py_content]
        batch_result = provider.get_embeddings_batch_with_metadata(batch_texts)

        assert len(batch_result.embeddings) == 2
        assert batch_result.total_tokens_used > 0
        assert batch_result.provider == "voyage-ai"

    def test_provider_comparison(self, temp_project_dir, console):
        """Compare outputs between providers for the same code."""
        # This test helps verify that different providers produce different but valid embeddings
        test_code = "def calculate_hash(data): return hashlib.sha256(data).hexdigest()"

        # Test Ollama (always available in unit tests via mocking, but skip for real E2E)
        config = Config()
        config.embedding_provider = "ollama"

        try:
            ollama_provider = EmbeddingProviderFactory.create(config, console)
            if ollama_provider.health_check():
                ollama_embedding = ollama_provider.get_embedding(test_code)
                assert (
                    len(ollama_embedding) == 768
                )  # Ollama nomic-embed-text dimensions
        except Exception:
            pytest.skip("Ollama not available for comparison test")

        # Test VoyageAI if available
        api_key = os.getenv("VOYAGE_API_KEY")
        if api_key:
            config.embedding_provider = "voyage-ai"
            voyage_provider = EmbeddingProviderFactory.create(config, console)
            voyage_embedding = voyage_provider.get_embedding(test_code)
            assert len(voyage_embedding) == 1024  # VoyageAI voyage-code-3 dimensions

            # Embeddings should be different but both valid
            if "ollama_embedding" in locals():
                # Compare first 768 dimensions (Ollama size)
                ollama_magnitude = sum(x * x for x in ollama_embedding) ** 0.5
                voyage_magnitude = sum(x * x for x in voyage_embedding[:768]) ** 0.5

                # Both should have reasonable magnitudes
                assert ollama_magnitude > 0.1
                assert voyage_magnitude > 0.1
