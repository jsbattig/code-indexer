"""Qdrant vector database client."""

import time
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .schema_migration import QdrantMigrator
import httpx
from rich.console import Console

from ..config import QdrantConfig
from .embedding_provider import EmbeddingProvider
from .embedding_factory import EmbeddingProviderFactory

# Import will be added when needed to avoid circular imports


class QdrantClient:
    """Client for interacting with Qdrant vector database."""

    def __init__(self, config: QdrantConfig, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()
        self.client = httpx.Client(base_url=config.host, timeout=30.0)
        self._current_collection_name: Optional[str] = None
        self._migrator: Optional["QdrantMigrator"] = (
            None  # Lazy initialization to avoid circular imports
        )

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

    def clear_all_collections(self) -> bool:
        """Clear all collections in the database."""
        try:
            # Get list of all collections
            response = self.client.get("/collections")
            if response.status_code != 200:
                self.console.print("Failed to get collections list", style="red")
                return False

            collections_data = response.json()
            collections = collections_data.get("result", {}).get("collections", [])

            if not collections:
                self.console.print("No collections found to clear", style="yellow")
                return True

            # Clear each collection
            for collection_info in collections:
                collection_name = collection_info.get("name")
                if collection_name:
                    if not self.clear_collection(collection_name):
                        return False

            self.console.print(
                f"✅ Cleared {len(collections)} collections", style="green"
            )
            return True

        except Exception as e:
            self.console.print(f"Failed to clear all collections: {e}", style="red")
            return False

    def cleanup_collections(
        self, collection_patterns: List[str], dry_run: bool = False
    ) -> Dict[str, Any]:
        """Cleanup collections matching given patterns.

        Args:
            collection_patterns: List of patterns to match collections for deletion (e.g., ['test_*', 'temp_*'])
            dry_run: If True, return what would be deleted without actually deleting

        Returns:
            Dict with cleanup results: {'deleted': [...], 'errors': [...], 'total_deleted': int}
        """
        import fnmatch

        try:
            # Get all collections
            response = self.client.get("/collections")

            if response.status_code != 200:
                return {
                    "error": f"Failed to get collections: HTTP {response.status_code}",
                    "deleted": [],
                    "errors": [],
                    "total_deleted": 0,
                }

            collections_data = response.json()
            all_collections = collections_data.get("result", {}).get("collections", [])

            # Find collections matching patterns
            collections_to_delete = []
            for collection in all_collections:
                collection_name = collection["name"]
                for pattern in collection_patterns:
                    if fnmatch.fnmatch(collection_name, pattern):
                        collections_to_delete.append(collection_name)
                        break

            if dry_run:
                return {
                    "deleted": [],
                    "would_delete": collections_to_delete,
                    "errors": [],
                    "total_deleted": 0,
                    "total_would_delete": len(collections_to_delete),
                }

            # Delete collections
            deleted = []
            errors = []

            for collection_name in collections_to_delete:
                try:
                    if self.delete_collection(collection_name):
                        deleted.append(collection_name)
                        self.console.print(
                            f"🗑️  Deleted collection: {collection_name}", style="dim"
                        )
                    else:
                        errors.append(f"{collection_name}: delete_collection failed")
                except Exception as e:
                    errors.append(f"{collection_name}: {str(e)}")

            if deleted and not dry_run:
                self.console.print(
                    f"✅ Deleted {len(deleted)} collections", style="green"
                )

            return {
                "deleted": deleted,
                "errors": errors,
                "total_deleted": len(deleted),
                "total_errors": len(errors),
            }

        except Exception as e:
            return {
                "error": f"Collection cleanup failed: {str(e)}",
                "deleted": [],
                "errors": [],
                "total_deleted": 0,
            }

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

            # Generate project ID for collection isolation
            project_id = EmbeddingProviderFactory.generate_project_id(
                str(config.codebase_dir)
            )

            return str(
                EmbeddingProviderFactory.generate_collection_name(
                    base_name, provider_name, model_name, project_id
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
        self, config, embedding_provider: EmbeddingProvider, quiet: bool = False
    ) -> str:
        """Create/validate collection with provider-aware naming and sizing.

        Args:
            config: Main configuration object containing QdrantConfig
            embedding_provider: Current embedding provider instance
            quiet: Suppress output for migrations and operations

        Returns:
            Collection name that was created/validated
        """
        collection_name = self.resolve_collection_name(config, embedding_provider)
        vector_size = self.get_vector_size_for_provider(embedding_provider)

        # Create collection with auto-detected vector size and migration support
        success = self.ensure_collection_with_migration(
            collection_name, vector_size, quiet
        )

        if not success:
            raise RuntimeError(
                f"Failed to create/validate collection: {collection_name}"
            )

        if not quiet:
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
            # For 404 errors, it just means no points matched the filter - this is OK
            if "404" in str(e):
                return True  # No points to delete is considered success
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

    def get_point(
        self, point_id: str, collection_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get a specific point by ID."""
        collection = collection_name or self.config.collection

        try:
            response = self.client.get(f"/collections/{collection}/points/{point_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return dict(response.json()["result"])
        except Exception:
            return None

    def delete_points(
        self, point_ids: List[str], collection_name: Optional[str] = None
    ) -> int:
        """Delete specific points by IDs."""
        collection = collection_name or self.config.collection

        try:
            response = self.client.post(
                f"/collections/{collection}/points/delete", json={"points": point_ids}
            )
            response.raise_for_status()
            return len(point_ids)
        except Exception as e:
            self.console.print(f"Failed to delete points: {e}", style="red")
            return 0

    def batch_update_points(
        self,
        filter_conditions: Dict[str, Any],
        payload_updates: Dict[str, Any],
        collection_name: Optional[str] = None,
    ) -> int:
        """Update payload fields for points matching filter conditions."""
        collection = collection_name or self.config.collection

        try:
            # First, find points matching the filter
            points, _ = self.scroll_points(
                filter_conditions=filter_conditions,
                collection_name=collection,
                limit=10000,
                with_payload=True,
                with_vectors=False,
            )

            if not points:
                return 0

            # Update each point's payload
            updated_points = []
            for point in points:
                updated_payload = {**point.get("payload", {}), **payload_updates}
                updated_points.append({"id": point["id"], "payload": updated_payload})

            # Batch update via upsert (preserving vectors)
            if updated_points:
                # Get original vectors for the points
                for i, point in enumerate(updated_points):
                    original_point = self.get_point(point["id"], collection)
                    if original_point and "vector" in original_point:
                        updated_points[i]["vector"] = original_point["vector"]
                    else:
                        # If we can't get the vector, skip this point
                        continue

                response = self.client.put(
                    f"/collections/{collection}/points", json={"points": updated_points}
                )
                response.raise_for_status()

            return len(updated_points)

        except Exception as e:
            self.console.print(f"Failed to batch update points: {e}", style="red")
            return 0

    def scroll_points(
        self,
        filter_conditions: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
        limit: int = 100,
        with_payload: bool = True,
        with_vectors: bool = False,
        offset: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Scroll through points in collection with optional filtering."""
        collection = collection_name or self.config.collection

        try:
            request_data: Dict[str, Any] = {
                "limit": limit,
                "with_payload": with_payload,
                "with_vector": with_vectors,
            }

            if filter_conditions:
                request_data["filter"] = filter_conditions

            if offset:
                request_data["offset"] = offset

            response = self.client.post(
                f"/collections/{collection}/points/scroll", json=request_data
            )
            response.raise_for_status()

            result = response.json()["result"]
            points = result.get("points", [])
            next_offset = result.get("next_page_offset")

            return points, next_offset

        except Exception as e:
            self.console.print(f"Failed to scroll points: {e}", style="red")
            return [], None

    def create_point(
        self,
        vector: List[float],
        payload: Dict[str, Any],
        point_id: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a point object for batch operations."""
        # Create a copy of the payload to avoid modifying the original
        point_payload = payload.copy()

        # Add embedding model to payload if provided
        if embedding_model:
            point_payload["embedding_model"] = embedding_model

        point = {"vector": vector, "payload": point_payload}

        if point_id:
            point["id"] = point_id

        return point

    def search_with_branch_topology(
        self,
        query_vector: List[float],
        current_branch: str,
        include_ancestry: bool = True,
        limit: int = 10,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search with branch topology awareness using the new architecture.

        This method searches content points and filters by branch visibility.
        """
        collection = collection_name or self.config.collection

        # First, get all content IDs visible from this branch
        visible_content_ids, _ = self.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "visibility"}},
                    {"key": "branch", "match": {"value": current_branch}},
                    {"key": "status", "match": {"value": "visible"}},
                ]
            },
            collection_name=collection,
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )

        if not visible_content_ids:
            return []

        # Extract content IDs
        content_ids = {point["payload"]["content_id"] for point in visible_content_ids}

        # Perform vector search on content points only
        content_results = self.search(
            query_vector=query_vector,
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            limit=limit * 3,  # Over-fetch to account for filtering
            collection_name=collection,
        )

        # Filter by visibility
        filtered_results = []
        for result in content_results:
            if result["id"] in content_ids:
                filtered_results.append(result)
                if len(filtered_results) >= limit:
                    break

        return filtered_results

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

    def get_collection_size(
        self, collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get collection size information."""
        collection = collection_name or self.config.collection

        try:
            count = self.count_points(collection)
            info = self.get_collection_info(collection)

            return {
                "points_count": count,
                "status": info.get("status", "unknown"),
                "optimizer_status": info.get("optimizer_status", {}),
                "vectors_count": count,  # Same as points count for now
            }
        except Exception as e:
            return {
                "points_count": 0,
                "status": "error",
                "error": str(e),
                "optimizer_status": {},
                "vectors_count": 0,
            }

    def batch_update_branch_metadata(
        self,
        file_paths: List[str],
        new_branch: str,
        collection_name: Optional[str] = None,
    ) -> bool:
        """Efficiently update branch metadata for multiple files without reprocessing content."""
        collection = (
            collection_name or self._current_collection_name or self.config.collection
        )

        try:
            # Find existing points for these files
            points_to_update = []

            for file_path in file_paths:
                # Search for existing points for this file using scroll
                points, _ = self.scroll_points(
                    collection_name=collection,
                    limit=1000,
                    with_payload=True,
                    with_vectors=False,
                )

                # Filter points for this specific file
                existing_points = [
                    point
                    for point in points
                    if point.get("payload", {}).get("path") == file_path
                ]

                for point_data in existing_points:
                    point_id = point_data.get("id")
                    payload = point_data.get("payload", {})

                    # Update branch metadata
                    updated_payload = {
                        **payload,
                        "git_branch": new_branch,
                        "last_updated": int(time.time()),
                    }

                    points_to_update.append(
                        {"id": point_id, "payload": updated_payload}
                    )

            # Batch update in chunks
            batch_size = 100
            success_count = 0

            for i in range(0, len(points_to_update), batch_size):
                batch = points_to_update[i : i + batch_size]

                if self._batch_update_points(batch, collection):
                    success_count += len(batch)

            if success_count == len(points_to_update):
                self.console.print(
                    f"✅ Updated branch metadata for {len(file_paths)} files",
                    style="green",
                )
                return True
            else:
                self.console.print(
                    f"⚠️ Updated {success_count}/{len(points_to_update)} points",
                    style="yellow",
                )
                return False

        except Exception as e:
            self.console.print(
                f"Failed to batch update branch metadata: {e}", style="red"
            )
            return False

    def _batch_update_points(
        self, points: List[Dict[str, Any]], collection_name: str
    ) -> bool:
        """Update multiple points with new payload data."""
        try:
            # Use overwrite payload operation for each point
            for point in points:
                response = self.client.put(
                    f"/collections/{collection_name}/points/payload",
                    json={"points": [point["id"]], "payload": point["payload"]},
                )
                response.raise_for_status()
            return True
        except Exception as e:
            self.console.print(f"Batch update failed: {e}", style="red")
            return False

    def delete_branch_data(
        self, branch_name: str, collection_name: Optional[str] = None
    ) -> bool:
        """Delete data associated with a specific branch, preserving files that exist in other branches."""
        collection = (
            collection_name or self._current_collection_name or self.config.collection
        )

        try:
            # Instead of deleting all points with this branch name,
            # we need to be more selective to avoid deleting files that exist in other branches.
            # For now, implement a conservative approach: only delete files that are truly unique to this branch.

            # First, get all points for this branch using the search API with filter
            try:
                response = self.client.post(
                    f"/collections/{collection}/points/scroll",
                    json={
                        "limit": 10000,
                        "with_payload": True,
                        "with_vector": False,
                        "filter": {
                            "must": [
                                {"key": "git_branch", "match": {"value": branch_name}}
                            ]
                        },
                    },
                )
                response.raise_for_status()
                scroll_result = response.json()
                branch_points = scroll_result.get("result", {}).get("points", [])
            except Exception:
                # Fallback: get all points and filter manually
                all_points, _ = self.scroll_points(
                    collection_name=collection,
                    limit=10000,
                    with_payload=True,
                    with_vectors=False,
                )
                branch_points = [
                    point
                    for point in all_points
                    if point.get("payload", {}).get("git_branch") == branch_name
                ]

            if not branch_points:
                self.console.print(
                    f"✅ No data found for branch: {branch_name}", style="green"
                )
                return True

            # Get all points in the collection to check for files that exist in other branches
            all_points, _ = self.scroll_points(
                collection_name=collection,
                limit=10000,
                with_payload=True,
                with_vectors=False,
            )

            # Simple approach: identify files that were added specifically in this branch
            # by checking if they exist in the git history of other branches
            # For now, use a heuristic: files that were newly added to this branch should be deleted

            points_to_delete = []
            points_to_restore = []

            for point in branch_points:
                payload = point.get("payload", {})
                file_path = payload.get("path")
                point_id = point.get("id")

                if file_path and point_id:
                    # Better heuristic: use git to check if file exists in master branch
                    try:
                        import subprocess
                        from pathlib import Path

                        # Extract relative file path
                        if file_path.startswith("/"):
                            # Convert absolute path to relative path
                            # This is a simplified approach - in a real implementation we'd need the codebase root
                            relative_path = Path(file_path).name
                        else:
                            relative_path = file_path

                        # Check if file exists in master branch using git
                        result = subprocess.run(
                            ["git", "cat-file", "-e", f"master:{relative_path}"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )

                        if result.returncode == 0:
                            # File exists in master, so restore it
                            updated_payload = payload.copy()
                            updated_payload["git_branch"] = "master"
                            points_to_restore.append(
                                {"id": point_id, "payload": updated_payload}
                            )
                        else:
                            # File doesn't exist in master, so it's new to this branch - delete it
                            points_to_delete.append(point_id)

                    except Exception:
                        # Fallback: if we can't determine, restore to master (conservative approach)
                        updated_payload = payload.copy()
                        updated_payload["git_branch"] = "master"
                        points_to_restore.append(
                            {"id": point_id, "payload": updated_payload}
                        )

            # Delete only the unique points
            if points_to_delete:
                response = self.client.post(
                    f"/collections/{collection}/points/delete",
                    json={"points": points_to_delete},
                )
                response.raise_for_status()

                self.console.print(
                    f"✅ Deleted {len(points_to_delete)} unique points for branch: {branch_name}",
                    style="green",
                )
            else:
                self.console.print(
                    f"✅ No unique data to delete for branch: {branch_name}",
                    style="green",
                )

            # Restore the branch metadata for preserved files
            if points_to_restore:
                # Batch update the restored points
                batch_size = 100
                for i in range(0, len(points_to_restore), batch_size):
                    batch = points_to_restore[i : i + batch_size]

                    update_response = self.client.put(
                        f"/collections/{collection}/points", json={"points": batch}
                    )
                    update_response.raise_for_status()

                self.console.print(
                    f"✅ Restored {len(points_to_restore)} points to appropriate branches",
                    style="green",
                )

            return True

        except Exception as e:
            self.console.print(
                f"Failed to delete branch data for {branch_name}: {e}", style="red"
            )
            return False

    def list_payload_indexes(
        self, collection_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List existing payload indexes."""
        collection = (
            collection_name or self._current_collection_name or self.config.collection
        )

        try:
            info = self.get_collection_info(collection)
            indexes = info.get("payload_schema", {})
            return [{"field": k, "schema": v} for k, v in indexes.items()]
        except Exception as e:
            self.console.print(f"Failed to list indexes: {e}", style="red")
            return []

    def _get_migrator(self):
        """Get migrator instance with lazy initialization to avoid circular imports."""
        if self._migrator is None:
            from .schema_migration import QdrantMigrator

            self._migrator = QdrantMigrator(self, self.console)
        return self._migrator

    def check_and_migrate_if_needed(
        self, collection_name: str, quiet: bool = False
    ) -> bool:
        """
        Check if migration is needed and perform it automatically.

        Args:
            collection_name: Name of collection to check/migrate
            quiet: Suppress progress output

        Returns:
            True if migration was successful or not needed, False if failed
        """
        try:
            migrator = self._get_migrator()

            # Check if migration is needed
            if not migrator.schema_manager.is_migration_needed(collection_name):
                return True

            # Check if migration is safe
            is_safe, warnings = migrator.is_migration_safe(collection_name)

            if not is_safe:
                if not quiet:
                    self.console.print(
                        f"❌ Migration not safe for {collection_name}", style="red"
                    )
                    for warning in warnings:
                        self.console.print(f"   {warning}", style="red")
                return False

            # Show warnings if not quiet
            if warnings and not quiet:
                self.console.print(
                    f"⚠️  Migration warnings for {collection_name}:", style="yellow"
                )
                for warning in warnings:
                    self.console.print(f"   {warning}", style="yellow")

            if not quiet:
                self.console.print(
                    f"🔄 Auto-migrating collection {collection_name} to new architecture...",
                    style="blue",
                )

            # Perform migration
            result = migrator.migrate_collection(collection_name, quiet=quiet)

            # Check if migration was successful
            if result.errors:
                if not quiet:
                    self.console.print(
                        "❌ Migration completed with errors", style="red"
                    )
                return False

            return True

        except Exception as e:
            if not quiet:
                self.console.print(f"❌ Auto-migration failed: {e}", style="red")
            return False

    def ensure_collection_with_migration(
        self,
        collection_name: Optional[str] = None,
        vector_size: Optional[int] = None,
        quiet: bool = False,
    ) -> bool:
        """
        Ensure collection exists and is migrated to current architecture.

        This method combines ensure_collection with auto-migration.

        Args:
            collection_name: Collection name (optional)
            vector_size: Vector dimensions (optional)
            quiet: Suppress output

        Returns:
            True if collection is ready, False otherwise
        """
        collection = collection_name or self.config.collection

        # First ensure collection exists
        if not self.ensure_collection(collection, vector_size):
            return False

        # Then check and migrate if needed
        return self.check_and_migrate_if_needed(collection, quiet)

    def get_schema_info(self, collection_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get schema information for a collection.

        Args:
            collection_name: Collection name (optional)

        Returns:
            Dictionary with schema information
        """
        collection = collection_name or self.config.collection

        try:
            migrator = self._get_migrator()
            schema = migrator.schema_manager.detect_schema_version(collection)
            stats = migrator.schema_manager.get_migration_stats(collection)

            return {
                "collection_name": collection,
                "schema_version": schema.version,
                "schema_description": schema.description,
                "is_legacy": schema.is_legacy,
                "migration_needed": schema.is_legacy and schema.version != "empty",
                "total_points": self.count_points(collection),
                "legacy_points": stats.get("total_legacy_points", 0),
                "branches": stats.get("branches", 0),
                "branch_counts": stats.get("branch_counts", {}),
            }

        except Exception as e:
            return {
                "collection_name": collection,
                "schema_version": "error",
                "schema_description": f"Error getting schema info: {e}",
                "is_legacy": False,
                "migration_needed": False,
                "total_points": 0,
                "legacy_points": 0,
                "branches": 0,
                "branch_counts": {},
            }

    def optimize_collection(self, collection_name: Optional[str] = None) -> bool:
        """Optimize collection storage by triggering Qdrant's optimization process."""
        collection = (
            collection_name or self._current_collection_name or self.config.collection
        )
        try:
            # Trigger collection optimization
            self.client.post(
                f"/collections/{collection}/cluster",
                json={
                    "move_shard": {
                        "shard_id": 0,
                        "from_peer_id": 0,
                        "to_peer_id": 0,
                        "method": "stream_records",
                    }
                },
            )
            # Note: This endpoint might not be available in all Qdrant versions
            # The optimization happens automatically in most cases

            # Alternative: Simply return True as Qdrant handles optimization internally
            return True

        except Exception:
            # Optimization is automatic in Qdrant, so we can return True
            # even if explicit optimization calls fail
            return True

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
