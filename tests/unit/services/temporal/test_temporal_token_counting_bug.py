"""Test for temporal indexing token counting bug causing freeze at commit 202.

ROOT CAUSE: temporal_indexer.py line 145 uses len(text) // 4 approximation
instead of VoyageTokenizer, causing batches 4-8x larger than 120k token limit.

SYMPTOM: VoyageAI API calls hang/timeout when batch exceeds token limit.
"""

from unittest.mock import Mock, patch

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.services.voyage_ai import VoyageAIClient


class TestTemporalTokenCountingBug:
    """Test accurate token counting in temporal indexing."""

    def test_count_tokens_uses_accurate_tokenizer_not_approximation(self, tmp_path):
        """Test that _count_tokens uses VoyageTokenizer, not len(text) // 4.

        BUG: temporal_indexer.py line 145 uses len(text) // 4 approximation.
        This causes batches 4-8x larger than 120k token limit, causing API timeouts.
        """
        # Setup: Create minimal indexer with mocked factory
        mock_config = Mock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = Mock(parallel_requests=1, model="voyage-code-3")
        mock_config.codebase_dir = tmp_path

        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = mock_config

        mock_vector_store = Mock()
        mock_vector_store.project_root = tmp_path
        mock_vector_store.base_path = tmp_path / ".code-indexer" / "index"
        mock_vector_store.collection_exists.return_value = True

        # Patch the factory to avoid real initialization
        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as MockFactory:
            MockFactory.get_provider_model_info.return_value = {"dimensions": 1024}
            MockFactory.create.return_value = Mock()

            indexer = TemporalIndexer(
                config_manager=mock_config_manager,
                vector_store=mock_vector_store,
            )

        # Create mock vector_manager with VoyageAI provider
        mock_vector_manager = Mock()
        mock_embedding_provider = Mock(spec=VoyageAIClient)
        mock_embedding_provider.model = "voyage-code-3"

        # The accurate tokenizer should be called and return 1000
        mock_embedding_provider._count_tokens_accurately = Mock(return_value=1000)
        mock_vector_manager.embedding_provider = mock_embedding_provider

        # Test: Count tokens for a code snippet
        test_text = "def authenticate_user(username, password):\n    # This is test code\n    return True"

        # Call _count_tokens
        token_count = indexer._count_tokens(test_text, mock_vector_manager)

        # EXPECTED: Should use accurate tokenizer (returns 1000)
        # ACTUAL (BUG): Uses len(text) // 4 = 85 // 4 = 21

        # This test will FAIL with current implementation
        # because it uses len(text) // 4 instead of calling the accurate tokenizer
        assert token_count == 1000, (
            f"Expected accurate token count (1000), "
            f"but got approximation ({token_count}). "
            f"Should call vector_manager.embedding_provider._count_tokens_accurately()"
        )

        # Verify accurate tokenizer was called
        mock_embedding_provider._count_tokens_accurately.assert_called_once_with(
            test_text
        )
