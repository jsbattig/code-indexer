"""Qdrant vector database client."""

import uuid
from typing import List, Dict, Any, Optional, Union
import httpx
from rich.console import Console

from ..config import QdrantConfig


class QdrantClient:
    """Client for interacting with Qdrant vector database."""
    
    def __init__(self, config: QdrantConfig, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()
        self.client = httpx.Client(
            base_url=config.host,
            timeout=30.0
        )
    
    def health_check(self) -> bool:
        """Check if Qdrant service is accessible."""
        try:
            response = self.client.get("/healthz")
            return response.status_code == 200
        except Exception:
            return False
    
    def collection_exists(self, collection_name: Optional[str] = None) -> bool:
        """Check if collection exists."""
        collection = collection_name or self.config.collection
        try:
            response = self.client.get(f"/collections/{collection}")
            return response.status_code == 200
        except Exception:
            return False
    
    def create_collection(self, collection_name: Optional[str] = None, vector_size: Optional[int] = None) -> bool:
        """Create a new collection."""
        collection = collection_name or self.config.collection
        size = vector_size or self.config.vector_size
        
        try:
            response = self.client.put(
                f"/collections/{collection}",
                json={
                    "vectors": {
                        "size": size,
                        "distance": "Cosine"
                    }
                }
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.console.print(f"Failed to create collection {collection}: {e}", style="red")
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
                f"/collections/{collection}/points",
                params={"filter": "{}"}
            )
            return response.status_code == 200
        except Exception as e:
            self.console.print(f"Failed to clear collection {collection}: {e}", style="red")
            return False
    
    def ensure_collection(self, collection_name: Optional[str] = None, vector_size: Optional[int] = None) -> bool:
        """Ensure collection exists, create if it doesn't."""
        collection = collection_name or self.config.collection
        
        if self.collection_exists(collection):
            return True
        
        return self.create_collection(collection, vector_size)
    
    def upsert_points(
        self,
        points: List[Dict[str, Any]],
        collection_name: Optional[str] = None
    ) -> bool:
        """Insert or update points in the collection."""
        collection = collection_name or self.config.collection
        
        try:
            response = self.client.put(
                f"/collections/{collection}/points",
                json={"points": points}
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.console.print(f"Failed to upsert points: {e}", style="red")
            return False
    
    def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        collection = collection_name or self.config.collection
        
        search_params = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False
        }
        
        if score_threshold is not None:
            search_params["score_threshold"] = score_threshold
        
        if filter_conditions:
            search_params["filter"] = filter_conditions
        
        try:
            response = self.client.post(
                f"/collections/{collection}/points/search",
                json=search_params
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get("result", [])
            
        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to Qdrant: {e}")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Qdrant API error: {e}")
    
    def delete_by_filter(
        self,
        filter_conditions: Dict[str, Any],
        collection_name: Optional[str] = None
    ) -> bool:
        """Delete points matching filter conditions."""
        collection = collection_name or self.config.collection
        
        try:
            response = self.client.post(
                f"/collections/{collection}/points/delete",
                json={"filter": filter_conditions}
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.console.print(f"Failed to delete points: {e}", style="red")
            return False
    
    def get_collection_info(self, collection_name: Optional[str] = None) -> Dict[str, Any]:
        """Get information about the collection."""
        collection = collection_name or self.config.collection
        
        try:
            response = self.client.get(f"/collections/{collection}")
            response.raise_for_status()
            return response.json()["result"]
        except Exception as e:
            raise RuntimeError(f"Failed to get collection info: {e}")
    
    def count_points(self, collection_name: Optional[str] = None) -> int:
        """Count total points in collection."""
        collection = collection_name or self.config.collection
        
        try:
            response = self.client.post(
                f"/collections/{collection}/points/count",
                json={}
            )
            response.raise_for_status()
            return response.json()["result"]["count"]
        except Exception:
            return 0
    
    def create_point(
        self,
        point_id: Optional[str] = None,
        vector: List[float] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a point object for upserting."""
        return {
            "id": point_id or str(uuid.uuid4()),
            "vector": vector or [],
            "payload": payload or {}
        }
    
    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()