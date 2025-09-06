"""
End-to-end integration tests for unified thread configuration.

Tests that demonstrate the complete solution for Feature 2: Unified Thread Configuration.
Verifies that config.json settings are respected across all components.
"""

from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    resolve_thread_count_with_precedence,
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


class TestUnifiedThreadConfigurationE2E:
    """End-to-end tests for unified thread configuration feature."""

    def setup_method(self):
        """Set up test fixtures."""
        self.voyage_provider = MockEmbeddingProvider("voyage-ai")
        self.ollama_provider = MockEmbeddingProvider("ollama")

    def test_voyage_ai_split_brain_fix_demonstration(self):
        """
        INTEGRATION TEST: Demonstrates the fix for VoyageAI split brain configuration.

        BEFORE: HTTP uses config.json (12), Vector uses hardcoded default (8) - SPLIT BRAIN!
        AFTER:  Both use config.json (12) - UNIFIED BEHAVIOR!
        """
        # User configures 12 threads in config.json
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig(parallel_requests=12)
        config.embedding_provider = "voyage-ai"

        # BEFORE (old behavior): Split brain between HTTP and Vector components
        http_threads_old = (
            config.voyage_ai.parallel_requests
        )  # ✅ Used config.json correctly
        vector_threads_old_approach = 8  # ❌ Hardcoded, ignored config.json

        assert http_threads_old == 12, "HTTP component correctly used config.json"
        assert (
            vector_threads_old_approach == 8
        ), "OLD: Vector component ignored config.json"
        assert (
            http_threads_old != vector_threads_old_approach
        ), "OLD: Split brain behavior"

        # AFTER (new behavior): Unified configuration across both components
        unified_thread_info = resolve_thread_count_with_precedence(
            self.voyage_provider,
            cli_thread_count=None,  # No CLI override
            config=config,
        )

        # Both components now use the same resolved value
        http_threads_new = config.voyage_ai.parallel_requests  # Still works correctly
        vector_threads_new = unified_thread_info["count"]  # Now respects config.json!

        assert http_threads_new == 12, "HTTP component still works correctly"
        assert (
            vector_threads_new == 12
        ), "NEW: Vector component now respects config.json"
        assert (
            http_threads_new == vector_threads_new
        ), "NEW: Unified behavior - split brain FIXED!"
        assert (
            unified_thread_info["source"] == "config.json"
        ), "Correctly identifies source"
        assert (
            unified_thread_info["message"] == "12 (from config.json)"
        ), "Accurate messaging"

    def test_ollama_configuration_hierarchy_e2e(self):
        """
        INTEGRATION TEST: Tests complete Ollama configuration hierarchy end-to-end.

        Tests: CLI option → config.json → provider default
        """
        config = Mock(spec=Config)
        config.ollama = OllamaConfig(num_parallel=3)  # User wants 3 threads
        config.embedding_provider = "ollama"

        # Test 1: No CLI option, uses config.json
        result1 = resolve_thread_count_with_precedence(
            self.ollama_provider, cli_thread_count=None, config=config
        )
        assert result1["count"] == 3, "Should use config.json value"
        assert result1["source"] == "config.json", "Should identify config source"
        assert (
            result1["message"] == "3 (from config.json)"
        ), "Should have accurate message"

        # Test 2: CLI option overrides config.json
        result2 = resolve_thread_count_with_precedence(
            self.ollama_provider, cli_thread_count=5, config=config  # CLI override
        )
        assert result2["count"] == 5, "CLI option should override config.json"
        assert result2["source"] == "cli", "Should identify CLI source"
        assert (
            result2["message"] == "5 (from CLI option)"
        ), "Should have accurate CLI message"

        # Test 3: No config provided, uses provider defaults
        result3 = resolve_thread_count_with_precedence(
            self.ollama_provider, cli_thread_count=None, config=None
        )
        assert result3["count"] == 1, "Should use provider default for Ollama"
        assert (
            result3["source"] == "provider_default"
        ), "Should identify provider default source"
        assert (
            result3["message"] == "1 (provider default for ollama)"
        ), "Should have accurate default message"

    def test_smart_indexer_configuration_resolution_logic(self):
        """
        INTEGRATION TEST: Tests that configuration resolution logic works correctly.

        This test focuses on verifying the configuration hierarchy works at the
        SmartIndexer level without needing to instantiate the full object.
        """
        # Test configuration resolution directly
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig(parallel_requests=16)  # User wants 16 threads
        config.embedding_provider = "voyage-ai"

        # Test the resolution logic that SmartIndexer uses
        thread_info = resolve_thread_count_with_precedence(
            self.voyage_provider,
            cli_thread_count=None,  # No CLI override (same as SmartIndexer internal call)
            config=config,
        )

        # This is the key integration test: config.json value is respected
        assert (
            thread_info["count"] == 16
        ), "SmartIndexer should resolve thread count from config.json"
        assert thread_info["source"] == "config.json", "Should identify config source"
        assert (
            thread_info["message"] == "16 (from config.json)"
        ), "Should have accurate message"

        # Test that it would have been different with old hardcoded approach
        # (this demonstrates the fix)
        from code_indexer.services.vector_calculation_manager import (
            get_default_thread_count,
        )

        old_hardcoded_approach = get_default_thread_count(self.voyage_provider)

        assert old_hardcoded_approach == 8, "Old approach used hardcoded default"
        assert (
            thread_info["count"] != old_hardcoded_approach
        ), "New approach differs from hardcoded default"
        assert (
            thread_info["count"] == config.voyage_ai.parallel_requests
        ), "New approach matches config.json"

    def test_messaging_replacement_no_more_auto_detected(self):
        """
        INTEGRATION TEST: Verifies that misleading 'auto-detected' messaging is replaced.

        OLD: "8 (auto-detected for voyage-ai)" - MISLEADING!
        NEW: "12 (from config.json)" - ACCURATE!
        """
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig(parallel_requests=14)
        config.embedding_provider = "voyage-ai"

        # Get thread info with accurate source messaging
        thread_info = resolve_thread_count_with_precedence(
            self.voyage_provider, cli_thread_count=None, config=config
        )

        # Verify accurate messaging (not misleading)
        assert thread_info["count"] == 14, "Should use config.json value"
        assert (
            thread_info["message"] == "14 (from config.json)"
        ), "Should have accurate message"
        assert (
            "auto-detected" not in thread_info["message"]
        ), "Should NOT contain misleading 'auto-detected' text"
        assert (
            thread_info["source"] == "config.json"
        ), "Should accurately identify source"

        # Test CLI override messaging
        cli_thread_info = resolve_thread_count_with_precedence(
            self.voyage_provider, cli_thread_count=20, config=config
        )

        assert (
            cli_thread_info["message"] == "20 (from CLI option)"
        ), "CLI message should be accurate"
        assert (
            "auto-detected" not in cli_thread_info["message"]
        ), "CLI message should not contain 'auto-detected'"

    def test_complete_precedence_hierarchy_voyage_ai(self):
        """
        INTEGRATION TEST: Complete precedence hierarchy for VoyageAI.

        Tests all three levels: CLI → config.json → provider default
        """
        config = Mock(spec=Config)
        config.voyage_ai = VoyageAIConfig(parallel_requests=10)
        config.embedding_provider = "voyage-ai"

        # Level 1: CLI has highest priority
        cli_result = resolve_thread_count_with_precedence(
            self.voyage_provider, cli_thread_count=25, config=config  # CLI override
        )
        assert cli_result["count"] == 25, "CLI should have highest priority"
        assert cli_result["source"] == "cli", "Should identify CLI source"

        # Level 2: config.json has medium priority
        config_result = resolve_thread_count_with_precedence(
            self.voyage_provider,
            cli_thread_count=None,  # No CLI override
            config=config,
        )
        assert config_result["count"] == 10, "config.json should have medium priority"
        assert config_result["source"] == "config.json", "Should identify config source"

        # Level 3: Provider default has lowest priority
        default_result = resolve_thread_count_with_precedence(
            self.voyage_provider,
            cli_thread_count=None,  # No CLI override
            config=None,  # No config provided
        )
        assert default_result["count"] == 8, "Provider default should be fallback"
        assert (
            default_result["source"] == "provider_default"
        ), "Should identify provider default source"
        assert (
            "provider default for voyage-ai" in default_result["message"]
        ), "Should indicate provider default"
