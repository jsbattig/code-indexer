"""Qdrant vector database client."""

import uuid
from typing import List, Dict, Any, Optional
import httpx
from rich.console import Console

from ..config import QdrantConfig


class QdrantClient:
    """Client for interacting with Qdrant vector database."""

    def __init__(self, config: QdrantConfig, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()
        self.client = httpx.Client(base_url=config.host, timeout=30.0)

    def health_check(self) -> bool:
        """Check if Qdrant service is accessible."""
        try:
            response = self.client.get("/healthz")
            return bool(response.status_code == 200)
        except Exception:
            return False

    def collection_exists(self, collection_name: Optional[str] = None) -> bool:
        """Check if collection exists."""
        collection = collection_name or self.config.collection
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
        collection = collection_name or self.config.collection
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

    def upsert_points(
        self, points: List[Dict[str, Any]], collection_name: Optional[str] = None
    ) -> bool:
        """Insert or update points in the collection."""
        collection = collection_name or self.config.collection

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
        collection = collection_name or self.config.collection

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
    ) -> Dict[str, Any]:
        """Create a point object for upserting."""
        return {
            "id": point_id or str(uuid.uuid4()),
            "vector": vector or [],
            "payload": payload or {},
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
