"""VoyageAI API client for embeddings generation."""

import os
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import httpx
from rich.console import Console

from ..config import VoyageAIConfig
from .embedding_provider import EmbeddingProvider, EmbeddingResult, BatchEmbeddingResult


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

        # HTTP client will be created per request to avoid threading issues

        # Thread pool for parallel processing
        self.executor = ThreadPoolExecutor(max_workers=config.parallel_requests)

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

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation)."""
        # VoyageAI typically uses ~0.75 tokens per word for English text
        # This is a rough estimate for rate limiting purposes
        words = len(text.split())
        return max(1, int(words * 0.75))

    def _make_sync_request(
        self, texts: List[str], model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make synchronous request to VoyageAI API."""
        model_name = model or self.config.model

        # Prepare request payload
        payload = {"input": texts, "model": model_name}

        # Retry logic
        last_exception = None
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
        result = self._make_sync_request([text], model)

        if not result.get("data") or len(result["data"]) == 0:
            raise ValueError("No embedding returned from VoyageAI")

        return list(result["data"][0]["embedding"])

    def get_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch with parallel processing."""
        if not texts:
            return []

        # If texts fit in one batch, process directly
        if len(texts) <= self.config.batch_size:
            result = self._make_sync_request(texts, model)
            return [list(item["embedding"]) for item in result["data"]]

        # Split into batches and process in parallel
        batches = [
            texts[i : i + self.config.batch_size]
            for i in range(0, len(texts), self.config.batch_size)
        ]

        all_embeddings = []
        futures = []

        # Submit all batch requests to thread pool
        for batch in batches:
            future = self.executor.submit(self._make_sync_request, batch, model)
            futures.append(future)

        # Collect results in order
        for future in futures:
            try:
                result = future.result(timeout=self.config.timeout * 2)
                batch_embeddings = [list(item["embedding"]) for item in result["data"]]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                raise RuntimeError(f"Batch embedding request failed: {e}")

        return all_embeddings

    def get_embedding_with_metadata(
        self, text: str, model: Optional[str] = None
    ) -> EmbeddingResult:
        """Generate embedding with metadata."""
        result = self._make_sync_request([text], model)

        if not result.get("data") or len(result["data"]) == 0:
            raise ValueError("No embedding returned from VoyageAI")

        model_name = model or self.config.model
        usage = result.get("usage", {})

        return EmbeddingResult(
            embedding=list(result["data"][0]["embedding"]),
            model=model_name,
            tokens_used=usage.get("total_tokens"),
            provider="voyage-ai",
        )

    def get_embeddings_batch_with_metadata(
        self, texts: List[str], model: Optional[str] = None
    ) -> BatchEmbeddingResult:
        """Generate batch embeddings with metadata."""
        if not texts:
            return BatchEmbeddingResult(
                embeddings=[], model=model or self.config.model, provider="voyage-ai"
            )

        result = self._make_sync_request(texts, model)
        model_name = model or self.config.model
        usage = result.get("usage", {})

        embeddings = [list(item["embedding"]) for item in result["data"]]

        return BatchEmbeddingResult(
            embeddings=embeddings,
            model=model_name,
            total_tokens_used=usage.get("total_tokens"),
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
        """Close the executor."""
        self.executor.shutdown(wait=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
