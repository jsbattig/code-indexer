"""VoyageAI API client for embeddings generation."""

import os
import time
from typing import List, Dict, Any, Optional
import httpx
from rich.console import Console
import yaml  # type: ignore[import-untyped]
from pathlib import Path

# Suppress tokenizers parallelism warning
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from ..config import VoyageAIConfig
from .embedding_provider import EmbeddingProvider, EmbeddingResult, BatchEmbeddingResult

# NOTE: VoyageTokenizer is imported lazily inside _count_tokens_accurately()
# to avoid triggering the import chain at module load time


class VoyageAIClient(EmbeddingProvider):
    """Client for interacting with VoyageAI API."""

    def __init__(self, config: VoyageAIConfig, console: Optional[Console] = None):
        super().__init__(console)
        self.config = config
        self.console = console or Console()

        # Get API key from environment
        self.api_key = os.getenv("VOYAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "VOYAGE_API_KEY environment variable is required for VoyageAI. "
                "Set it with: export VOYAGE_API_KEY=your_api_key_here"
            )

        # Load model specifications from YAML
        self._load_model_specs()

        # HTTP client will be created per request to avoid threading issues
        # ThreadPoolExecutor removed - parallel processing handled by VectorCalculationManager

    def _load_model_specs(self):
        """Load model specifications from YAML file."""
        try:
            # Get path to YAML file relative to this module
            module_dir = Path(__file__).parent.parent
            yaml_path = module_dir / "data" / "voyage_models.yaml"

            with open(yaml_path, "r", encoding="utf-8") as f:
                self.model_specs = yaml.safe_load(f)

        except Exception as e:
            # Fallback to basic specs if YAML loading fails
            self.console.print(
                f"[yellow]Warning: Could not load model specs: {e}[/yellow]"
            )
            self.model_specs = {
                "voyage_models": {
                    "voyage-code-3": {"token_limit": 120000},
                    "voyage-large-2": {"token_limit": 120000},
                    "voyage-2": {"token_limit": 320000},
                }
            }

    def _count_tokens_accurately(self, text: str) -> int:
        """Count tokens accurately using VoyageAI's embedded tokenizer."""
        # Lazy import to avoid loading tokenizer at module import time
        from .embedded_voyage_tokenizer import VoyageTokenizer

        return VoyageTokenizer.count_tokens([text], model=self.config.model)

    def _get_model_token_limit(self) -> int:
        """Get token limit for current model."""
        try:
            limit = self.model_specs["voyage_models"][self.config.model]["token_limit"]
            return int(limit)  # Ensure integer return type
        except (KeyError, TypeError):
            # Fallback for unknown models
            return 120000  # Conservative default

    def health_check(self, test_api: bool = False) -> bool:
        """Check if VoyageAI service is configured correctly.

        Args:
            test_api: If True, make an actual API call to test connectivity.
                     If False, only check configuration validity.
        """
        try:
            # First check configuration validity
            config_valid = bool(
                self.api_key  # API key is available
                and self.config.model  # Model is configured
                and self.config.api_endpoint  # Endpoint is configured
            )

            if not config_valid:
                return False

            # If API testing is requested, make a simple API call
            if test_api:
                try:
                    # Make a minimal API call with a single character
                    self._make_sync_request(["test"])
                    return True
                except Exception:
                    return False

            # For normal health checks, only verify configuration
            # Making actual API calls during startup causes hanging due to rate limits/timeouts
            return True
        except Exception:
            return False

    def _make_sync_request(
        self, texts: List[str], model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make synchronous request to VoyageAI API."""
        model_name = model or self.config.model

        # Prepare request payload
        payload = {"input": texts, "model": model_name}

        # Retry logic
        last_exception: Optional[Exception] = None
        for attempt in range(self.config.max_retries + 1):
            try:
                with httpx.Client(
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=self.config.timeout,
                ) as client:
                    response = client.post(self.config.api_endpoint, json=payload)
                response.raise_for_status()

                result = response.json()

                if isinstance(result, dict):
                    return result
                else:
                    raise ValueError(f"Unexpected response format: {type(result)}")

            except httpx.HTTPStatusError as e:
                last_exception = e
                if (
                    e.response.status_code == 429
                ):  # Rate limit - use server-driven backoff
                    # Check for Retry-After header from server
                    retry_after = e.response.headers.get("retry-after")
                    if retry_after:
                        wait_time = float(retry_after)
                    else:
                        # Fall back to exponential backoff
                        wait_time = self.config.retry_delay * (
                            2**attempt if self.config.exponential_backoff else 1
                        )

                    # Cap maximum wait time to 5 minutes to prevent excessive delays
                    wait_time = min(wait_time, 300.0)

                    if attempt < self.config.max_retries:
                        time.sleep(wait_time)
                        continue
                elif e.response.status_code >= 500:  # Server error
                    wait_time = self.config.retry_delay * (
                        2**attempt if self.config.exponential_backoff else 1
                    )
                    if attempt < self.config.max_retries:
                        time.sleep(wait_time)
                        continue
                else:
                    # Client error, don't retry
                    break
            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay)
                    continue
                else:
                    break

        # All retries exhausted
        if isinstance(last_exception, httpx.HTTPStatusError):
            if last_exception.response.status_code == 401:
                raise ValueError(
                    "Invalid VoyageAI API key. Check VOYAGE_API_KEY environment variable."
                )
            elif last_exception.response.status_code == 429:
                raise RuntimeError(
                    "VoyageAI rate limit exceeded. Try reducing parallel_requests or requests_per_minute."
                )
            else:
                # Include more detailed error information for debugging
                try:
                    response_text = last_exception.response.text
                except Exception:
                    response_text = "Unable to read response"
                raise RuntimeError(
                    f"VoyageAI API error (HTTP {last_exception.response.status_code}): {last_exception}. "
                    f"Response: {response_text}"
                )
        else:
            raise ConnectionError(f"Failed to connect to VoyageAI: {last_exception}")

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Generate embedding for given text."""
        # Use get_embeddings_batch internally with single-item array
        batch_result = self.get_embeddings_batch([text], model)

        # Extract first result from batch response
        return batch_result[0]

    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Generate embeddings with dynamic token-aware batching (90% safety margin)."""
        if not texts:
            return []

        # Get model-specific token limit with 90% safety margin
        model_token_limit = self._get_model_token_limit()
        safety_limit = int(model_token_limit * 0.9)  # 90% safety margin as requested

        # Dynamic batching: process chunks until approaching token limit
        all_embeddings: List[List[float]] = []
        current_batch: List[str] = []
        current_tokens: int = 0

        for text in texts:
            # Count tokens accurately for this chunk
            chunk_tokens = self._count_tokens_accurately(text)

            # Check if adding this chunk would exceed 90% safety limit
            if current_tokens + chunk_tokens > safety_limit and current_batch:
                # Submit current batch before it gets too large
                try:
                    result = self._make_sync_request(current_batch, model)

                    # LAYER 3 VALIDATION: Validate all embeddings from API before processing
                    for idx, item in enumerate(result["data"]):
                        emb = item["embedding"]
                        if emb is None:
                            raise RuntimeError(
                                f"VoyageAI returned None embedding at index {idx} in batch. "
                                f"API response is corrupt."
                            )
                        if not emb:  # Empty list
                            raise RuntimeError(
                                f"VoyageAI returned empty embedding at index {idx} in batch"
                            )
                        # Check for None values inside embedding
                        if any(v is None for v in emb):
                            raise RuntimeError(
                                f"VoyageAI returned embedding with None values at index {idx}: {emb[:10]}..."
                            )

                    batch_embeddings = [
                        list(item["embedding"]) for item in result["data"]
                    ]

                    # VALIDATION: Ensure embeddings match input count
                    if len(batch_embeddings) != len(current_batch):
                        raise RuntimeError(
                            f"VoyageAI returned {len(batch_embeddings)} embeddings "
                            f"but expected {len(current_batch)}. Partial response detected."
                        )

                    all_embeddings.extend(batch_embeddings)
                except Exception as e:
                    raise RuntimeError(f"Batch embedding request failed: {e}")

                # Reset for next batch
                current_batch = []
                current_tokens = 0

            # Add chunk to current batch
            current_batch.append(text)
            current_tokens += chunk_tokens

        # Process final batch if not empty
        if current_batch:
            try:
                result = self._make_sync_request(current_batch, model)

                # LAYER 3 VALIDATION: Validate all embeddings from API before processing
                for idx, item in enumerate(result["data"]):
                    emb = item["embedding"]
                    if emb is None:
                        raise RuntimeError(
                            f"VoyageAI returned None embedding at index {idx} in batch. "
                            f"API response is corrupt."
                        )
                    if not emb:  # Empty list
                        raise RuntimeError(
                            f"VoyageAI returned empty embedding at index {idx} in batch"
                        )
                    # Check for None values inside embedding
                    if any(v is None for v in emb):
                        raise RuntimeError(
                            f"VoyageAI returned embedding with None values at index {idx}: {emb[:10]}..."
                        )

                batch_embeddings = [list(item["embedding"]) for item in result["data"]]

                # VALIDATION: Ensure embeddings match input count
                if len(batch_embeddings) != len(current_batch):
                    raise RuntimeError(
                        f"VoyageAI returned {len(batch_embeddings)} embeddings "
                        f"but expected {len(current_batch)}. Partial response detected."
                    )

                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                raise RuntimeError(f"Batch embedding request failed: {e}")

        return all_embeddings

    def get_embedding_with_metadata(
        self, text: str, model: Optional[str] = None
    ) -> EmbeddingResult:
        """Generate embedding with metadata."""
        # Use batch processing internally for consistency
        batch_result = self.get_embeddings_batch_with_metadata([text], model)

        if not batch_result.embeddings:
            raise ValueError("No embedding returned from batch processing")

        # Extract single embedding from batch result
        return EmbeddingResult(
            embedding=batch_result.embeddings[0],
            model=batch_result.model,
            tokens_used=batch_result.total_tokens_used,
            provider=batch_result.provider,
        )

    def get_embeddings_batch_with_metadata(
        self, texts: List[str], model: Optional[str] = None
    ) -> BatchEmbeddingResult:
        """Generate batch embeddings with metadata."""
        if not texts:
            return BatchEmbeddingResult(
                embeddings=[], model=model or self.config.model, provider="voyage-ai"
            )

        # Use conservative sub-batching by delegating to get_embeddings_batch()
        embeddings = self.get_embeddings_batch(texts, model)

        # Create metadata result (note: token usage not available from batched calls)
        model_name = model or self.config.model

        return BatchEmbeddingResult(
            embeddings=embeddings,
            model=model_name,
            total_tokens_used=None,  # Token usage not available from batched processing
            provider="voyage-ai",
        )

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        model_name = self.config.model

        # VoyageAI model dimensions (as of API documentation)
        model_dimensions = {
            "voyage-code-3": 1024,
            "voyage-large-2": 1536,
            "voyage-2": 1024,
            "voyage-code-2": 1536,
            "voyage-law-2": 1024,
        }

        return {
            "name": model_name,
            "provider": "voyage-ai",
            "dimensions": model_dimensions.get(model_name, 1024),  # Default to 1024
            "max_tokens": 16000,  # VoyageAI typical context limit
            "supports_batch": True,
            "api_endpoint": self.config.api_endpoint,
        }

    def get_provider_name(self) -> str:
        """Get the name of this embedding provider."""
        return "voyage-ai"

    def get_current_model(self) -> str:
        """Get the current active model name."""
        return self.config.model

    def supports_batch_processing(self) -> bool:
        """Check if provider supports efficient batch processing."""
        return True

    def close(self) -> None:
        """Clean up resources (no executor to close after refactoring)."""
        # ThreadPoolExecutor removed - no cleanup needed
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
