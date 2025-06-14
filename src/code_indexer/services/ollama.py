"""Ollama API client for embeddings generation."""

import asyncio
from typing import List, Dict, Any, Optional
import httpx
from rich.console import Console

from ..config import OllamaConfig


class OllamaClient:
    """Client for interacting with Ollama API."""
    
    def __init__(self, config: OllamaConfig, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()
        self.client = httpx.Client(
            base_url=config.host,
            timeout=config.timeout
        )
    
    def health_check(self) -> bool:
        """Check if Ollama service is accessible."""
        try:
            response = self.client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        try:
            response = self.client.get("/api/tags")
            response.raise_for_status()
            return response.json().get("models", [])
        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to Ollama: {e}")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama API error: {e}")
    
    def model_exists(self, model_name: str) -> bool:
        """Check if a specific model exists."""
        models = self.list_models()
        return any(model["name"] == model_name for model in models)
    
    def pull_model(self, model_name: str) -> bool:
        """Pull a model if it doesn't exist."""
        if self.model_exists(model_name):
            return True
        
        try:
            with self.console.status(f"Pulling model {model_name}..."):
                response = self.client.post(
                    "/api/pull",
                    json={"name": model_name},
                    timeout=300  # 5 minutes for model download
                )
                response.raise_for_status()
                return True
        except Exception as e:
            self.console.print(f"Failed to pull model {model_name}: {e}", style="red")
            return False
    
    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Generate embedding for given text."""
        model_name = model or self.config.model
        
        try:
            response = self.client.post(
                "/api/embeddings",
                json={
                    "model": model_name,
                    "prompt": text
                }
            )
            response.raise_for_status()
            
            result = response.json()
            embedding = result.get("embedding")
            
            if not embedding:
                raise ValueError("No embedding returned from Ollama")
            
            return embedding
            
        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to Ollama: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Model {model_name} not found. Try pulling it first.")
            raise RuntimeError(f"Ollama API error: {e}")
    
    async def get_embedding_async(self, text: str, model: Optional[str] = None) -> List[float]:
        """Async version of get_embedding."""
        model_name = model or self.config.model
        
        async with httpx.AsyncClient(base_url=self.config.host, timeout=self.config.timeout) as client:
            try:
                response = await client.post(
                    "/api/embeddings",
                    json={
                        "model": model_name,
                        "prompt": text
                    }
                )
                response.raise_for_status()
                
                result = response.json()
                embedding = result.get("embedding")
                
                if not embedding:
                    raise ValueError("No embedding returned from Ollama")
                
                return embedding
                
            except httpx.RequestError as e:
                raise ConnectionError(f"Failed to connect to Ollama: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise ValueError(f"Model {model_name} not found. Try pulling it first.")
                raise RuntimeError(f"Ollama API error: {e}")
    
    async def get_embeddings_batch(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """Get embeddings for multiple texts in parallel."""
        tasks = [self.get_embedding_async(text, model) for text in texts]
        return await asyncio.gather(*tasks)
    
    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()