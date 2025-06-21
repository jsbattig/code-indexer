"""VoyageAI API client for embeddings generation."""

import os
import asyncio
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import httpx
from rich.console import Console

from ..config import VoyageAIConfig
from .embedding_provider import EmbeddingProvider, EmbeddingResult, BatchEmbeddingResult


class RateLimiter:
    """Rate limiter for API requests using token bucket algorithm."""

    def __init__(
        self, requests_per_minute: int, tokens_per_minute: Optional[int] = None
    ):
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute

        # Request rate limiting
        self.request_tokens = requests_per_minute
        self.request_last_refill = time.time()

        # Token rate limiting (if enabled)
        self.token_tokens: Optional[int] = None
        self.token_last_refill: Optional[float] = None

        if tokens_per_minute:
            self.token_tokens = tokens_per_minute
            self.token_last_refill = time.time()

    def _refill_tokens(self):
        """Refill tokens based on elapsed time."""
        now = time.time()

        # Refill request tokens
        elapsed = now - self.request_last_refill
        self.request_tokens = min(
            self.requests_per_minute,
            self.request_tokens + (elapsed * self.requests_per_minute / 60.0),
        )
        self.request_last_refill = now

        # Refill token tokens if enabled
        if self.tokens_per_minute and self.token_last_refill:
            self.token_tokens = min(
                self.tokens_per_minute,
                self.token_tokens + (elapsed * self.tokens_per_minute / 60.0),
            )
            self.token_last_refill = now

    def can_make_request(self, estimated_tokens: int = 1) -> bool:
        """Check if a request can be made without hitting rate limits."""
        self._refill_tokens()

        # Check request limit
        if self.request_tokens < 1:
            return False

        # Check token limit if enabled
        if self.token_tokens is not None and self.token_tokens < estimated_tokens:
            return False

        return True

    def consume_tokens(self, actual_tokens: int = 1):
        """Consume tokens after making a request."""
        self.request_tokens -= 1
        if self.token_tokens is not None:
            self.token_tokens -= actual_tokens

    def wait_time(self, estimated_tokens: int = 1) -> float:
        """Calculate how long to wait before making a request."""
        self._refill_tokens()

        wait_times = []

        # Request wait time
        if self.request_tokens < 1:
            wait_times.append(
                (1 - self.request_tokens) * 60.0 / self.requests_per_minute
            )

        # Token wait time if enabled
        if (
            self.token_tokens is not None
            and self.tokens_per_minute is not None
            and self.token_tokens < estimated_tokens
        ):
            needed_tokens = estimated_tokens - self.token_tokens
            wait_times.append(needed_tokens * 60.0 / self.tokens_per_minute)

        return max(wait_times) if wait_times else 0.0


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

        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            timeout=config.timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            requests_per_minute=config.requests_per_minute,
            tokens_per_minute=config.tokens_per_minute,
        )

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
        return asyncio.run(self._make_async_request(texts, model))

    async def _make_async_request(
        self, texts: List[str], model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make asynchronous request to VoyageAI API with rate limiting and retries."""
        model_name = model or self.config.model

        # Estimate tokens for rate limiting
        total_tokens = sum(self._estimate_tokens(text) for text in texts)

        # Wait for rate limits
        wait_time = self.rate_limiter.wait_time(total_tokens)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        # Prepare request payload
        payload = {"input": texts, "model": model_name}

        # Retry logic
        last_exception = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=self.config.timeout,
                ) as temp_client:
                    response = await temp_client.post(
                        self.config.api_endpoint, json=payload
                    )
                response.raise_for_status()

                result = response.json()

                # Consume rate limit tokens
                actual_tokens = result.get("usage", {}).get(
                    "total_tokens", total_tokens
                )
                self.rate_limiter.consume_tokens(actual_tokens)

                if isinstance(result, dict):
                    return result
                else:
                    raise ValueError(f"Unexpected response format: {type(result)}")

            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code == 429:  # Rate limit
                    wait_time = self.config.retry_delay * (
                        2**attempt if self.config.exponential_backoff else 1
                    )
                    if attempt < self.config.max_retries:
                        await asyncio.sleep(wait_time)
                        continue
                elif e.response.status_code >= 500:  # Server error
                    wait_time = self.config.retry_delay * (
                        2**attempt if self.config.exponential_backoff else 1
                    )
                    if attempt < self.config.max_retries:
                        await asyncio.sleep(wait_time)
                        continue
                else:
                    # Client error, don't retry
                    break
            except (httpx.RequestError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (
                        2**attempt if self.config.exponential_backoff else 1
                    )
                    await asyncio.sleep(wait_time)
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
                raise RuntimeError(f"VoyageAI API error: {last_exception}")
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

    async def close(self) -> None:
        """Close the HTTP client and executor."""
        await self.client.aclose()
        self.executor.shutdown(wait=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        asyncio.run(self.close())
