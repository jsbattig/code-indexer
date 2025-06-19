"""Qdrant vector database client."""

import uuid
from typing import List, Dict, Any, Optional
import httpx
from rich.console import Console

from ..config import QdrantConfig
from .embedding_provider import EmbeddingProvider
from .embedding_factory import EmbeddingProviderFactory


class QdrantClient:
    """Client for interacting with Qdrant vector database."""

    def __init__(self, config: QdrantConfig, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()
        self.client = httpx.Client(base_url=config.host, timeout=30.0)
        self._current_collection_name: Optional[str] = None

    def health_check(self) -> bool:
        """Check if Qdrant service is accessible."""
        try:
            response = self.client.get("/healthz")
            return bool(response.status_code == 200)
        except Exception:
            return False

    def collection_exists(self, collection_name: Optional[str] = None) -> bool:
        """Check if collection exists."""
        collection = (
            collection_name or self._current_collection_name or self.config.collection
        )
        try:
            response = self.client.get(f"/collections/{collection}")
            return bool(response.status_code == 200)
        except Exception:
            return False

    def create_collection(
        self, collection_name: Optional[str] = None, vector_size: Optional[int] = None
    ) -> bool:
        """Create a new collection with optimized storage settings."""
        collection = collection_name or self.config.collection
        size = vector_size or self.config.vector_size

        # Optimized collection configuration for storage efficiency
        collection_config = {
            "vectors": {
                "size": size,
                "distance": "Cosine",
                # Use disk-based storage for large datasets
                "on_disk": True,
            },
            # Optimize indexing parameters for storage and performance
            "hnsw_config": {
                # Lower M value reduces memory usage but slightly affects recall
                "m": 16,  # Default is 16, can go as low as 4
                # Higher ef_construct improves index quality but takes more time
                "ef_construct": 100,  # Default is 100
                # Store vectors on disk to save memory
                "on_disk": True,
            },
            # Optimize storage settings
            "optimizers_config": {
                # Lower memmap threshold to use disk sooner
                "memmap_threshold": 20000,  # Default is 20000
                # Enable indexing optimizations
                "indexing_threshold": 10000,  # Default is 20000
            },
            # Quantization to reduce storage size (optional - reduces precision)
            "quantization_config": {
                "scalar": {
                    "type": "int8",  # Use 8-bit integers instead of 32-bit floats
                    "quantile": 0.99,
                    "always_ram": False,  # Allow quantized vectors on disk
                }
            },
        }

        try:
            response = self.client.put(
                f"/collections/{collection}",
                json=collection_config,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.console.print(
                f"Failed to create collection {collection}: {e}", style="red"
            )
            # Fallback to basic collection if optimized creation fails
            try:
                basic_config = {"vectors": {"size": size, "distance": "Cosine"}}
                response = self.client.put(
                    f"/collections/{collection}",
                    json=basic_config,
                )
                response.raise_for_status()
                self.console.print(
                    "⚠️  Created basic collection (optimization failed)", style="yellow"
                )
                return True
            except Exception:
                return False

    def delete_collection(self, collection_name: Optional[str] = None) -> bool:
        """Delete a collection."""
        collection = collection_name or self.config.collection
        try:
            response = self.client.delete(f"/collections/{collection}")
            return response.status_code in [200, 404]  # Success or already deleted
        except Exception:
            return False

    def clear_collection(self, collection_name: Optional[str] = None) -> bool:
        """Clear all points from collection."""
        collection = (
            collection_name or self._current_collection_name or self.config.collection
        )
        try:
            response = self.client.delete(
                f"/collections/{collection}/points", params={"filter": "{}"}
            )
            return bool(response.status_code == 200)
        except Exception as e:
            self.console.print(
                f"Failed to clear collection {collection}: {e}", style="red"
            )
            return False

    def ensure_collection(
        self, collection_name: Optional[str] = None, vector_size: Optional[int] = None
    ) -> bool:
        """Ensure collection exists, create if it doesn't."""
        collection = collection_name or self.config.collection

        if self.collection_exists(collection):
            # Verify collection configuration matches expected settings
            try:
                info = self.get_collection_info(collection)
                actual_size = (
                    info.get("config", {})
                    .get("params", {})
                    .get("vectors", {})
                    .get("size")
                )
                expected_size = vector_size or self.config.vector_size

                if actual_size and actual_size != expected_size:
                    self.console.print(
                        f"⚠️  Collection vector size mismatch: expected {expected_size}, got {actual_size}",
                        style="yellow",
                    )
                    self.console.print(
                        "Consider deleting and recreating the collection: 'code-indexer clean'",
                        style="yellow",
                    )
            except Exception:
                # If we can't check, just continue
                pass
            return True

        return self.create_collection(collection, vector_size)

    def resolve_collection_name(
        self, config, embedding_provider: EmbeddingProvider
    ) -> str:
        """Generate collection name based on current provider and model.

        Args:
            config: Main configuration object containing QdrantConfig
            embedding_provider: Current embedding provider instance

        Returns:
            Collection name based on provider and model, or legacy name if configured
        """
        qdrant_config = config.qdrant

        # Use legacy naming if requested
        if qdrant_config.use_legacy_collection_naming:
            return str(qdrant_config.collection)

        # Use provider-aware naming
        if qdrant_config.use_provider_aware_collections:
            provider_name = embedding_provider.get_provider_name()
            model_name = embedding_provider.get_current_model()
            base_name = qdrant_config.collection_base_name

            return str(
                EmbeddingProviderFactory.generate_collection_name(
                    base_name, provider_name, model_name
                )
            )

        # Fallback to legacy collection name
        return str(qdrant_config.collection)

    def get_vector_size_for_provider(
        self, embedding_provider: EmbeddingProvider
    ) -> int:
        """Get vector dimensions from embedding provider model info.

        Args:
            embedding_provider: Current embedding provider instance

        Returns:
            Vector dimensions for the current provider's model
        """
        model_info = embedding_provider.get_model_info()
        return int(model_info["dimensions"])

    def ensure_provider_aware_collection(
        self, config, embedding_provider: EmbeddingProvider
    ) -> str:
        """Create/validate collection with provider-aware naming and sizing.

        Args:
            config: Main configuration object containing QdrantConfig
            embedding_provider: Current embedding provider instance

        Returns:
            Collection name that was created/validated
        """
        collection_name = self.resolve_collection_name(config, embedding_provider)
        vector_size = self.get_vector_size_for_provider(embedding_provider)

        # Create collection with auto-detected vector size
        success = self.ensure_collection(collection_name, vector_size)

        if not success:
            raise RuntimeError(
                f"Failed to create/validate collection: {collection_name}"
            )

        self.console.print(
            f"✅ Collection ready: {collection_name} (dimensions: {vector_size})",
            style="green",
        )

        # Store current collection name for use in subsequent operations
        self._current_collection_name = collection_name

        return collection_name

    def upsert_points(
        self, points: List[Dict[str, Any]], collection_name: Optional[str] = None
    ) -> bool:
        """Insert or update points in the collection."""
        collection = (
            collection_name or self._current_collection_name or self.config.collection
        )

        try:
            response = self.client.put(
                f"/collections/{collection}/points", json={"points": points}
            )
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            # Get detailed error information from Qdrant
            error_detail = "Unknown error"
            try:
                if e.response.content:
                    error_response = e.response.json()
                    error_detail = error_response.get("status", {}).get("error", str(e))
                    if isinstance(error_detail, dict):
                        error_detail = error_detail.get(
                            "description", str(error_detail)
                        )
            except Exception:
                error_detail = str(e)

            self.console.print(
                f"Failed to upsert points: {e.response.status_code} {e.response.reason_phrase}",
                style="red",
            )
            self.console.print(f"Error details: {error_detail}", style="red")

            # Log problematic point for debugging
            if points and len(points) > 0:
                sample_point = points[0]
                self.console.print("Sample point structure:", style="yellow")
                self.console.print(
                    f"  ID: {sample_point.get('id', 'missing')}", style="yellow"
                )
                self.console.print(
                    f"  Vector length: {len(sample_point.get('vector', []))}",
                    style="yellow",
                )
                self.console.print(
                    f"  Payload keys: {list(sample_point.get('payload', {}).keys())}",
                    style="yellow",
                )

            return False
        except Exception as e:
            self.console.print(f"Failed to upsert points: {e}", style="red")
            return False

    def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        collection = (
            collection_name or self._current_collection_name or self.config.collection
        )

        search_params = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }

        if score_threshold is not None:
            search_params["score_threshold"] = score_threshold

        if filter_conditions:
            search_params["filter"] = filter_conditions

        try:
            response = self.client.post(
                f"/collections/{collection}/points/search", json=search_params
            )
            response.raise_for_status()

            result = response.json()
            return list(result.get("result", []))

        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to Qdrant: {e}")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Qdrant API error: {e}")

    def create_model_filter(self, embedding_model: str) -> Dict[str, Any]:
        """Create a filter condition for a specific embedding model.

        Args:
            embedding_model: Name of the embedding model to filter by

        Returns:
            Filter condition for Qdrant queries
        """
        return {
            "must": [{"key": "embedding_model", "match": {"value": embedding_model}}]
        }

    def combine_filters(
        self,
        model_filter: Optional[Dict[str, Any]] = None,
        additional_filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Combine model filter with additional filter conditions.

        Args:
            model_filter: Filter for embedding model
            additional_filters: Additional filter conditions

        Returns:
            Combined filter condition, or None if no filters
        """
        if not model_filter and not additional_filters:
            return None

        if not additional_filters:
            return model_filter

        if not model_filter:
            return additional_filters

        # Combine filters - merge "must" conditions
        combined: Dict[str, List[Dict[str, Any]]] = {"must": []}

        # Add model filter conditions
        if "must" in model_filter:
            combined["must"].extend(model_filter["must"])

        # Add additional filter conditions
        if "must" in additional_filters:
            combined["must"].extend(additional_filters["must"])

        # Handle other filter types (should, must_not)
        for filter_type in ["should", "must_not"]:
            conditions = []
            if filter_type in model_filter:
                conditions.extend(model_filter[filter_type])
            if filter_type in additional_filters:
                conditions.extend(additional_filters[filter_type])
            if conditions:
                combined[filter_type] = conditions

        return combined

    def search_with_model_filter(
        self,
        query_vector: List[float],
        embedding_model: str,
        limit: int = 10,
        score_threshold: Optional[float] = None,
        additional_filters: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors filtered by embedding model.

        Args:
            query_vector: Query vector for similarity search
            embedding_model: Embedding model to filter by
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            additional_filters: Additional filter conditions
            collection_name: Collection name (optional)

        Returns:
            List of search results filtered by model
        """
        # Create model filter
        model_filter = self.create_model_filter(embedding_model)

        # Combine with additional filters
        final_filter = self.combine_filters(model_filter, additional_filters)

        # Use existing search method
        return self.search(
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            filter_conditions=final_filter,
            collection_name=collection_name,
        )

    def count_points_by_model(
        self, embedding_model: str, collection_name: Optional[str] = None
    ) -> int:
        """Count points for a specific embedding model.

        Args:
            embedding_model: Embedding model to count
            collection_name: Collection name (optional)

        Returns:
            Number of points with the specified embedding model
        """
        collection = collection_name or self.config.collection
        model_filter = self.create_model_filter(embedding_model)

        try:
            response = self.client.post(
                f"/collections/{collection}/points/count", json={"filter": model_filter}
            )
            response.raise_for_status()
            return int(response.json()["result"]["count"])
        except Exception:
            return 0

    def delete_by_filter(
        self, filter_conditions: Dict[str, Any], collection_name: Optional[str] = None
    ) -> bool:
        """Delete points matching filter conditions."""
        collection = collection_name or self.config.collection

        try:
            response = self.client.post(
                f"/collections/{collection}/points/delete",
                json={"filter": filter_conditions},
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.console.print(f"Failed to delete points: {e}", style="red")
            return False

    def get_collection_info(
        self, collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get information about the collection."""
        collection = collection_name or self.config.collection

        try:
            response = self.client.get(f"/collections/{collection}")
            response.raise_for_status()
            return dict(response.json()["result"])
        except Exception as e:
            raise RuntimeError(f"Failed to get collection info: {e}")

    def count_points(self, collection_name: Optional[str] = None) -> int:
        """Count total points in collection."""
        collection = collection_name or self.config.collection

        try:
            response = self.client.post(
                f"/collections/{collection}/points/count", json={}
            )
            response.raise_for_status()
            return int(response.json()["result"]["count"])
        except Exception:
            return 0

    def create_point(
        self,
        point_id: Optional[str] = None,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None,
        embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a point object for upserting with embedding model metadata.

        Args:
            point_id: Unique identifier for the point
            vector: Embedding vector
            payload: Metadata payload
            embedding_model: Name of the embedding model used

        Returns:
            Point object ready for upserting to Qdrant
        """
        final_payload = payload or {}

        # Always add embedding model to payload for filtering
        if embedding_model:
            final_payload["embedding_model"] = embedding_model

        return {
            "id": point_id or str(uuid.uuid4()),
            "vector": vector or [],
            "payload": final_payload,
        }

    def optimize_collection(self, collection_name: Optional[str] = None) -> bool:
        """Optimize collection storage and performance."""
        collection = collection_name or self.config.collection

        try:
            # Trigger collection optimization
            response = self.client.post(
                f"/collections/{collection}/index", json={"wait": True}
            )
            response.raise_for_status()

            self.console.print(f"✅ Optimized collection {collection}", style="green")
            return True
        except Exception as e:
            self.console.print(
                f"⚠️  Collection optimization failed: {e}", style="yellow"
            )
            return False

    def get_collection_size(
        self, collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get collection storage size information."""
        collection = collection_name or self.config.collection

        try:
            info = self.get_collection_info(collection)
            points_count = self.count_points(collection)

            # Estimate storage size (rough calculation)
            vector_size_mb = (points_count * self.config.vector_size * 4) / (
                1024 * 1024
            )  # 4 bytes per float

            return {
                "points_count": points_count,
                "estimated_vector_size_mb": round(vector_size_mb, 2),
                "status": info.get("status", "unknown"),
                "optimizer_status": info.get("optimizer_status", {}),
            }
        except Exception as e:
            return {"error": str(e)}

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
