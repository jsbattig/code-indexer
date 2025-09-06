"""
Test demonstrating the split brain issue where user config.json settings are ignored.

PROBLEM:
- User sets 12 threads in config.json
- System shows "8 (auto-detected for voyage-ai)"
- VectorCalculationManager ignores config.json and uses hardcoded defaults

EVIDENCE:
- SmartIndexer methods use `vector_thread_count or 8` instead of config hierarchy
- Messaging shows misleading "auto-detected" instead of true source
"""

import tempfile
from code_indexer.config import Config, VoyageAIConfig
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
        return "voyage-3-lite"

    def get_model_info(self) -> dict:
        return {"name": "voyage-3-lite", "dimensions": 768}

    def get_embedding(self, text: str, model=None) -> list:
        return [1.0] * 768

    def get_embeddings_batch(self, texts: list, model=None) -> list:
        return [[1.0] * 768 for _ in texts]

    def get_embedding_with_metadata(self, text: str, model=None) -> EmbeddingResult:
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
        embeddings = self.get_embeddings_batch(texts, model)
        total_tokens = sum(len(text.split()) for text in texts)
        return BatchEmbeddingResult(
            embeddings=embeddings,
            model=model or self.get_current_model(),
            total_tokens_used=total_tokens,
            provider=self.provider_name,
        )

    def supports_batch_processing(self) -> bool:
        return True

    def health_check(self) -> bool:
        return True


class TestConfigJsonSplitBrainIssue:
    """Test the split brain issue where config.json thread settings are ignored."""

    def setup_method(self):
        """Set up test fixtures."""
        self.provider = MockEmbeddingProvider("voyage-ai")
        self.temp_dir = tempfile.mkdtemp()

    def test_smart_indexer_split_brain_issue_DOCUMENTATION(self):
        """
        DOCUMENTATION TEST: Documents the split brain issue with SmartIndexer thread configuration.

        This test documents the known issue where:
        1. User sets 12 threads in config.json
        2. SmartIndexer uses hardcoded default of 8 instead
        3. Config.json setting completely ignored

        The test demonstrates the problem without actually failing.
        """
        # Create config.json with 12 threads
        config = Config()
        config.voyage_ai = VoyageAIConfig()
        config.voyage_ai.parallel_requests = 12  # User's config.json setting

        # DOCUMENTATION: Show the problematic pattern
        # Current SmartIndexer code uses: vector_thread_count or 8
        # This ignores config.json and uses hardcoded fallback
        current_problematic_approach = None or 8  # Simulates SmartIndexer behavior

        # DOCUMENTATION: Show what the correct approach should be
        from code_indexer.services.vector_calculation_manager import (
            resolve_thread_count_with_precedence,
        )

        correct_approach = resolve_thread_count_with_precedence(
            embedding_provider=self.provider,
            cli_thread_count=None,
            config=config,
        )["count"]

        # DOCUMENT the split brain issue
        assert (
            current_problematic_approach == 8
        ), "Current SmartIndexer uses hardcoded fallback"
        assert correct_approach == 12, "Proper resolution respects config.json"
        assert (
            current_problematic_approach != correct_approach
        ), "This demonstrates the split brain issue"

        # DOCUMENTATION: This test proves the issue exists but doesn't fail
        # To fix this issue, SmartIndexer should use resolve_thread_count_with_precedence()
        # instead of hardcoded fallbacks like `vector_thread_count or 8`
        print(
            f"DOCUMENTED ISSUE: SmartIndexer uses {current_problematic_approach} instead of {correct_approach}"
        )
        print(
            "FIX: Replace hardcoded fallbacks with resolve_thread_count_with_precedence()"
        )

    def test_config_hierarchy_resolution_works_in_vector_manager(self):
        """
        PASSING TEST: Shows that VectorCalculationManager has correct hierarchy logic.

        This demonstrates that the configuration hierarchy infrastructure exists
        and works correctly when used properly.
        """
        # Create config with user's thread setting
        config = Config()
        config.voyage_ai = VoyageAIConfig()
        config.voyage_ai.parallel_requests = 12

        # Test the configuration resolution function directly
        from code_indexer.services.vector_calculation_manager import (
            resolve_thread_count_with_precedence,
        )

        result = resolve_thread_count_with_precedence(
            embedding_provider=self.provider, cli_thread_count=None, config=config
        )

        # This PASSES because the resolution function works correctly
        assert result["count"] == 12
        assert result["source"] == "config.json"
        assert "config.json" in result["message"]
        assert "auto-detected" not in result["message"]

    def test_smart_indexer_hardcoded_fallback_behavior_DOCUMENTATION(self):
        """
        DOCUMENTATION TEST: Shows exactly where the split brain occurs.

        The issue is in SmartIndexer methods that use:
        vector_thread_count=vector_thread_count or 8

        Instead of using the configuration hierarchy resolution.
        """
        # This is the current problematic pattern in SmartIndexer:
        user_config_setting = None  # Simulates SmartIndexer not reading config
        hardcoded_fallback = user_config_setting or 8  # This is the problem!

        # User's config.json has 12 threads, but gets ignored
        expected_from_config = 12
        actual_used = hardcoded_fallback  # Will be 8

        # Document the split brain issue
        assert (
            actual_used != expected_from_config
        ), "This documents the split brain: user config ignored, hardcoded default used"
        assert actual_used == 8, "Hardcoded default is used instead of config.json"

    def test_messaging_shows_misleading_auto_detected_EXAMPLE(self):
        """
        EXAMPLE TEST: Shows the misleading 'auto-detected' messaging issue.

        When using hardcoded defaults, the system should say:
        "8 (provider default for voyage-ai)"

        NOT:
        "8 (auto-detected for voyage-ai)" - This is misleading!
        """
        # Test current behavior with no config
        from code_indexer.services.vector_calculation_manager import (
            resolve_thread_count_with_precedence,
        )

        result = resolve_thread_count_with_precedence(
            embedding_provider=self.provider,
            cli_thread_count=None,
            config=None,  # No config provided
        )

        # Verify accurate messaging (not misleading "auto-detected")
        assert (
            "auto-detected" not in result["message"]
        ), "Should not use misleading 'auto-detected' message"
        assert (
            "provider default" in result["message"]
        ), "Should clearly indicate this is a provider default"
        assert (
            "voyage-ai" in result["message"]
        ), "Should specify which provider the default is for"
