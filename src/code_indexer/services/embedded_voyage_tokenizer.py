"""Embedded VoyageAI tokenizer - minimal extraction from voyageai library.

This module provides token counting functionality for VoyageAI models without
requiring the full voyageai library import (which adds 440ms+ import overhead).

We only need the tokenizer for accurate token counting before sending batches
to VoyageAI API. This implementation:
- Uses the tokenizers library directly (11ms import vs 440ms+ for voyageai)
- Loads official VoyageAI tokenizers from HuggingFace
- Caches tokenizers per model for performance
- Provides identical token counts to voyageai.Client.count_tokens()
- Zero imports at module level for maximum performance

Original voyageai implementation:
https://github.com/voyage-ai/voyageai-python/blob/main/voyageai/_base.py
"""

# NO IMPORTS AT MODULE LEVEL - All imports happen lazily inside functions
# This keeps module import time near zero (<1ms)


class VoyageTokenizer:
    """Minimal VoyageAI tokenizer for token counting.

    This is a direct extraction of the tokenization logic from voyageai._base._BaseClient,
    avoiding the overhead of importing the entire voyageai library.
    """

    # Cache for loaded tokenizers (model_name -> tokenizer instance)
    _tokenizer_cache: dict[str, object] = {}

    @staticmethod
    def _get_tokenizer(model: str):
        """Load and cache tokenizer for a specific model.

        Args:
            model: VoyageAI model name (e.g., 'voyage-code-3')

        Returns:
            Tokenizer instance from HuggingFace

        Raises:
            ImportError: If tokenizers package is not installed
            Exception: If model tokenizer cannot be loaded
        """
        # Check cache first
        if model in VoyageTokenizer._tokenizer_cache:
            return VoyageTokenizer._tokenizer_cache[model]

        # Lazy import - only load when first needed
        try:
            from tokenizers import Tokenizer  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "The package `tokenizers` is required for VoyageAI token counting. "
                "Please run `pip install tokenizers` to install the dependency."
            )

        try:
            import warnings

            # Load official VoyageAI tokenizer from HuggingFace
            tokenizer = Tokenizer.from_pretrained(f"voyageai/{model}")
            tokenizer.no_truncation()

            # Cache for future use
            VoyageTokenizer._tokenizer_cache[model] = tokenizer

            return tokenizer
        except Exception:
            warnings.warn(
                f"Failed to load the tokenizer for `{model}`. "
                "Please ensure that it is a valid VoyageAI model name."
            )
            raise

    @staticmethod
    def count_tokens(texts, model):  # type: (list[str], str) -> int
        """Count tokens accurately using VoyageAI's official tokenizer.

        Args:
            texts: List of text strings to tokenize
            model: VoyageAI model name (e.g., 'voyage-code-3')

        Returns:
            Total token count across all texts

        Examples:
            >>> tokenizer = VoyageTokenizer()
            >>> tokenizer.count_tokens(["Hello world"], "voyage-code-3")
            2
            >>> tokenizer.count_tokens(["Hello", "world"], "voyage-code-3")
            2
        """
        if not texts:
            return 0

        # Get cached tokenizer for this model
        tokenizer = VoyageTokenizer._get_tokenizer(model)

        # Tokenize all texts in batch
        encodings = tokenizer.encode_batch(texts)

        # Count total tokens
        return sum(len(encoding.ids) for encoding in encodings)

    @staticmethod
    def tokenize(texts, model):  # type: (list[str], str) -> list[list[int]]
        """Tokenize texts and return token IDs.

        Args:
            texts: List of text strings to tokenize
            model: VoyageAI model name (e.g., 'voyage-code-3')

        Returns:
            List of token ID lists, one per input text

        Examples:
            >>> tokenizer = VoyageTokenizer()
            >>> tokenizer.tokenize(["Hello world"], "voyage-code-3")
            [[9707, 1879]]
        """
        if not texts:
            return []

        # Get cached tokenizer for this model
        tokenizer = VoyageTokenizer._get_tokenizer(model)

        # Tokenize all texts in batch
        encodings = tokenizer.encode_batch(texts)

        # Return token IDs
        return [encoding.ids for encoding in encodings]
