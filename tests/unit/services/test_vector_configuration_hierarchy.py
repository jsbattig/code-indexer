"""
Unit tests for VectorCalculationManager configuration hierarchy.

Tests the configuration precedence: CLI option → config.json → provider defaults.
This test demonstrates the current bug where config.json is completely ignored.
"""

from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    get_default_thread_count,
)
from code_indexer.config import Config, VoyageAIConfig, OllamaConfig
from code_indexer.services.embedding_provider import (
    EmbeddingProvider,
    EmbeddingResult,
    BatchEmbeddingResult,
)


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding provider for testing."""

    def __init__(self, provider_name: str = "voyage-ai"):
        super().__init__()
        self.provider_name = provider_name

    def get_provider_name(self) -> str:
        return self.provider_name

    def get_current_model(self) -> str:
        return "test-model"

    def get_model_info(self) -> dict:
        return {"name": "test-model", "dimensions": 768}

    def get_embedding(self, text: str, model=None) -> list:
        return [1.0] * 768

    def get_embeddings_batch(self, texts: list, model=None) -> list:
        return [[1.0] * 768 for _ in texts]

    def get_embedding_with_metadata(self, text: str, model=None) -> EmbeddingResult:
        """Mock embedding generation with metadata."""
        embedding = self.get_embedding(text, model)
        return EmbeddingResult(
            embedding=embedding,
            model=model or self.get_current_model(),
            tokens_used=len(text.split()),
            provider=self.provider_name,
        )

    def get_embeddings_batch_with_metadata(
        self, texts: list, model=None
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


class TestVectorConfigurationHierarchy:
    """Test cases for thread configuration hierarchy in VectorCalculationManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_provider = MockEmbeddingProvider()

    def test_config_json_parallel_requests_respected_voyage_ai(self):
        """
        PASSING TEST: VectorCalculationManager now respects config.json parallel_requests for VoyageAI.

        User sets parallel_requests: 12 in config.json and system uses it correctly.
        This demonstrates the fix for the configuration hierarchy.
        """
        # Create mock config with VoyageAI settings
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig(parallel_requests=12)  # User wants 12 threads
        config.embedding_provider = "voyage-ai"

        # Demonstrate old behavior still exists for comparison
        actual_from_defaults = get_default_thread_count(
            self.mock_provider
        )  # Returns 8 (hardcoded)
        assert actual_from_defaults == 8, "Default behavior unchanged"

        # NEW: VectorCalculationManager now respects configuration hierarchy
        manager = VectorCalculationManager(
            self.mock_provider, thread_count=actual_from_defaults
        )

        # Configuration hierarchy now works!
        resolved_thread_count = manager.get_resolved_thread_count(config)
        assert (
            resolved_thread_count == 12
        ), "Should use config.json value (12) instead of default (8)"

        # Verify thread info provides accurate source information
        thread_info = manager.get_thread_count_with_source(config)
        assert thread_info["count"] == 12, "Thread count should be from config.json"
        assert (
            thread_info["source"] == "config.json"
        ), "Source should be accurately identified"
        assert (
            thread_info["message"] == "12 (from config.json)"
        ), "Message should be accurate"

    def test_config_json_num_parallel_respected_ollama(self):
        """
        PASSING TEST: VectorCalculationManager now respects config.json num_parallel for Ollama.

        User sets num_parallel: 2 in config.json and system uses it correctly.
        """
        # Create mock Ollama provider
        ollama_provider = MockEmbeddingProvider(provider_name="ollama")

        # Create mock config with Ollama settings
        config = Mock(spec=Config)
        config.ollama = OllamaConfig(num_parallel=2)  # User wants 2 threads
        config.embedding_provider = "ollama"

        # Verify defaults still work as expected
        actual_from_defaults = get_default_thread_count(
            ollama_provider
        )  # Returns 1 (hardcoded)
        assert actual_from_defaults == 1, "Default behavior unchanged"

        # NEW: VectorCalculationManager now respects configuration hierarchy for Ollama
        manager = VectorCalculationManager(
            ollama_provider, thread_count=actual_from_defaults
        )

        # Configuration hierarchy now works for Ollama!
        resolved_thread_count = manager.get_resolved_thread_count(config)
        assert (
            resolved_thread_count == 2
        ), "Should use config.json value (2) instead of default (1)"

        # Verify thread info provides accurate source information
        thread_info = manager.get_thread_count_with_source(config)
        assert thread_info["count"] == 2, "Thread count should be from config.json"
        assert (
            thread_info["source"] == "config.json"
        ), "Source should be accurately identified"
        assert (
            thread_info["message"] == "2 (from config.json)"
        ), "Message should be accurate for Ollama"

    def test_cli_option_overrides_config_json(self):
        """
        PASSING TEST: CLI option has highest priority over config.json.

        Priority: CLI option (15) → config.json (12) → provider default (8)
        """
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig(parallel_requests=12)  # config.json setting
        config.embedding_provider = "voyage-ai"

        cli_thread_count = 15  # CLI option has highest priority

        # Configuration hierarchy supports CLI precedence
        manager = VectorCalculationManager(
            self.mock_provider, thread_count=8
        )  # Constructor param not used in hierarchy

        # CLI option has highest priority
        thread_info = manager.resolve_thread_count_with_precedence(
            cli_thread_count=cli_thread_count, config=config
        )
        assert (
            thread_info["count"] == cli_thread_count
        ), "CLI option should have highest priority"
        assert thread_info["source"] == "cli", "Source should be identified as CLI"
        assert (
            thread_info["message"] == "15 (from CLI option)"
        ), "Message should indicate CLI source"

    def test_fallback_to_provider_defaults_when_no_config(self):
        """
        PASSING TEST: Falls back to provider defaults when no config provided.

        Priority: CLI option (None) → config.json (default=8) → provider default (8)
        """
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig()  # Uses default parallel_requests=8
        config.embedding_provider = "voyage-ai"

        cli_thread_count = None  # No CLI option provided

        # Configuration hierarchy falls back appropriately
        manager = VectorCalculationManager(self.mock_provider, thread_count=8)

        # Should resolve to config default (which matches provider default)
        thread_info = manager.resolve_thread_count_with_precedence(
            cli_thread_count=cli_thread_count, config=config
        )
        assert thread_info["count"] == 8, "Should use config default value"
        assert (
            thread_info["source"] == "config.json"
        ), "Source should be config.json even when using default"
        assert (
            thread_info["message"] == "8 (from config.json)"
        ), "Message should indicate config.json source"

    def test_configuration_source_messaging_implemented(self):
        """
        PASSING TEST: Provides accurate source messaging, not misleading 'auto-detected'.

        OLD: "8 (auto-detected for voyage-ai)" - MISLEADING!
        NEW: "12 (from config.json)" - ACCURATE!
        """
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig(parallel_requests=12)
        config.embedding_provider = "voyage-ai"

        # Configuration source messaging is now implemented
        manager = VectorCalculationManager(self.mock_provider, thread_count=8)

        # Accurate source tracking for messaging
        thread_info = manager.get_thread_count_with_source(config)
        assert thread_info["count"] == 12, "Should use config.json value"
        assert thread_info["source"] == "config.json", "Should accurately report source"
        assert (
            "auto-detected" not in thread_info["message"]
        ), "Should not use misleading 'auto-detected' message"
        assert (
            thread_info["message"] == "12 (from config.json)"
        ), "Should provide accurate source message"

        # Verify the old misleading behavior is replaced
        assert (
            "auto-detected" not in thread_info["message"]
        ), "No more misleading auto-detected messages!"

    def test_consistency_across_http_and_vector_components(self):
        """
        PASSING TEST: HTTP and vector components now use same thread count.

        OLD Split Brain:
        - HTTP threads: config.json parallel_requests (12) ✅
        - Vector threads: hardcoded default (8) ❌

        NEW Unified:
        - Both components: config.json parallel_requests (12) ✅
        """
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig(parallel_requests=12)
        config.embedding_provider = "voyage-ai"

        # Simulate HTTP component (works correctly)
        http_threads = config.voyage_ai.parallel_requests  # Uses config.json ✅
        assert http_threads == 12, "HTTP component correctly uses config.json"

        # OLD vector component behavior (for comparison)
        old_vector_threads = get_default_thread_count(
            self.mock_provider
        )  # Ignores config.json ❌
        assert (
            old_vector_threads == 8
        ), "Old behavior: Vector component ignored config.json"

        # FIXED: Unified configuration is now implemented
        manager = VectorCalculationManager(
            self.mock_provider, thread_count=old_vector_threads
        )

        # NEW: Both components use same config source
        unified_thread_count = manager.get_unified_thread_count(config)
        assert unified_thread_count == http_threads, "Should match HTTP component"
        assert unified_thread_count == 12, "Both components should use config.json"

        # SPLIT BRAIN FIXED: No more inconsistency!
        assert unified_thread_count == http_threads, "Split brain fixed: HTTP=Vector=12"
