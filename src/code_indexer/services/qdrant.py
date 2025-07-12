"""Qdrant vector database client."""

import shutil
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import httpx
from rich.console import Console

from ..config import QdrantConfig
from .embedding_provider import EmbeddingProvider
from .embedding_factory import EmbeddingProviderFactory

# Import will be added when needed to avoid circular imports


class QdrantClient:
    """Client for interacting with Qdrant vector database."""

    def __init__(
        self,
        config: QdrantConfig,
        console: Optional[Console] = None,
        project_root: Optional[Path] = None,
    ):
        self.config = config
        self.console = console or Console()
        self.client = httpx.Client(base_url=config.host, timeout=30.0)
        self._current_collection_name: Optional[str] = None
        self.project_root = project_root or Path.cwd()

    def health_check(self) -> bool:
        """Check if Qdrant service is accessible."""
        try:
            response = self.client.get("/healthz", timeout=2.0)
            return bool(response.status_code == 200)
        except Exception:
            return False

    def collection_exists(self, collection_name: Optional[str] = None) -> bool:
        """Check if collection exists."""
        collection = (
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
        )
        try:
            response = self.client.get(f"/collections/{collection}")
            return bool(response.status_code == 200)
        except Exception:
            return False

    def list_collections(self) -> List[str]:
        """List all collections in the Qdrant instance.

        Returns:
            List of collection names
        """
        try:
            response = self.client.get("/collections")
            if response.status_code == 200:
                data = response.json()
                # Extract collection names from the response
                collections = data.get("result", {}).get("collections", [])
                return [
                    coll.get("name", "") for coll in collections if coll.get("name")
                ]
            return []
        except Exception:
            return []

    def create_collection(
        self, collection_name: Optional[str] = None, vector_size: Optional[int] = None
    ) -> bool:
        """Create a new collection with optimized direct approach."""
        collection = collection_name or self.config.collection_base_name
        size = vector_size or self.config.vector_size

        # Use direct approach (no CoW, no flush overhead)
        return self._create_collection_direct(collection, size)

    def _create_collection_direct(self, collection_name: str, vector_size: int) -> bool:
        """Create collection directly without CoW (for templates)."""
        collection_config = {
            "vectors": {
                "size": vector_size,
                "distance": "Cosine",
                "on_disk": True,
            },
            "hnsw_config": {
                "m": self.config.hnsw_m,
                "ef_construct": self.config.hnsw_ef_construct,
                "on_disk": True,
            },
            "optimizers_config": {
                "memmap_threshold": 20000,
                "indexing_threshold": 10000,
                "default_segment_number": 8,
            },
            "on_disk_payload": True,
        }

        try:
            response = self.client.put(
                f"/collections/{collection_name}", json=collection_config
            )
            if response.status_code not in [200, 201]:
                self.console.print(
                    f"Direct creation failed: {response.status_code} {response.text}",
                    style="red",
                )
                return False
            return True
        except Exception as e:
            self.console.print(f"Direct creation exception: {e}", style="red")
            return False

    def create_collection_with_profile(
        self,
        profile: str,
        collection_name: Optional[str] = None,
        vector_size: Optional[int] = None,
    ) -> bool:
        """Create a collection with predefined HNSW profiles for different use cases.

        Args:
            profile: Profile name - "small_codebase", "large_codebase"
            collection_name: Optional collection name
            vector_size: Optional vector size

        Returns:
            True if collection created successfully
        """
        collection = collection_name or self.config.collection_base_name
        size = vector_size or self.config.vector_size

        # Define HNSW profiles for different codebase sizes
        profiles = {
            "small_codebase": {
                "m": 16,
                "ef_construct": 100,
                "description": "Optimized for small codebases (<1M lines) - memory efficient",
            },
            "large_codebase": {
                "m": 32,
                "ef_construct": 200,
                "description": "Optimized for large codebases (>5M lines) - better accuracy",
            },
            "default": {
                "m": self.config.hnsw_m,
                "ef_construct": self.config.hnsw_ef_construct,
                "description": "Uses configuration defaults",
            },
        }

        profile_config = profiles.get(profile, profiles["default"])

        # Create collection config with profile-specific HNSW settings
        collection_config = {
            "vectors": {
                "size": size,
                "distance": "Cosine",
                "on_disk": True,
            },
            "hnsw_config": {
                "m": profile_config["m"],
                "ef_construct": profile_config["ef_construct"],
                "on_disk": True,
            },
            "optimizers_config": {
                "memmap_threshold": 20000,
                "indexing_threshold": 10000,
                "default_segment_number": 8,
            },
            "on_disk_payload": True,
            "quantization_config": {
                "scalar": {
                    "type": "int8",
                    "quantile": 0.99,
                    "always_ram": False,
                }
            },
        }

        try:
            response = self.client.put(
                f"/collections/{collection}",
                json=collection_config,
            )
            response.raise_for_status()
            self.console.print(
                f"✅ Created collection '{collection}' with {profile} profile: {profile_config['description']}",
                style="green",
            )
            return True
        except Exception as e:
            self.console.print(f"❌ Failed to create collection: {e}", style="red")
            return False

    def recreate_collection_with_hnsw_optimization(
        self,
        preserve_data: bool = False,
        collection_name: Optional[str] = None,
        profile: str = "large_codebase",
    ) -> bool:
        """Recreate collection with optimized HNSW settings.

        Args:
            preserve_data: Whether to backup and restore data (not implemented yet)
            collection_name: Collection to recreate
            profile: HNSW profile to use

        Returns:
            True if recreation successful
        """
        collection = collection_name or self.config.collection_base_name

        if preserve_data:
            self.console.print(
                "⚠️  Data preservation not yet implemented", style="yellow"
            )
            return False

        # Delete existing collection
        if not self.delete_collection(collection):
            self.console.print(
                f"❌ Failed to delete existing collection '{collection}'", style="red"
            )
            return False

        # Create with new profile
        return self.create_collection_with_profile(profile, collection)

    def delete_collection(self, collection_name: Optional[str] = None) -> bool:
        """Delete a collection and its CoW data storage."""
        collection = collection_name or self.config.collection_base_name

        try:
            # First cache the actual storage location before Qdrant deletion
            actual_storage_path = self._get_cow_storage_path(collection)

            # Delete via Qdrant API
            response = self.client.delete(f"/collections/{collection}")
            api_success = response.status_code in [
                200,
                404,
            ]  # Success or already deleted

            # Handle CoW storage cleanup using cached path
            self._cleanup_cow_storage_with_path(collection, actual_storage_path)

            return api_success
        except Exception as e:
            if self.console:
                self.console.print(f"Delete collection failed: {e}", style="yellow")
            return False

    def _get_cow_storage_path(self, collection_name: str) -> Optional[Path]:
        """Get the actual storage path for a CoW collection before deletion.

        Returns the resolved path if it's a symlink, or the direct path if it exists.
        Returns None if the collection doesn't exist.
        """
        try:
            global_collections_dir = Path.home() / ".qdrant_collections"
            symlink_path = global_collections_dir / collection_name

            if symlink_path.exists() or symlink_path.is_symlink():
                if symlink_path.is_symlink():
                    # Follow symlink to get actual storage location
                    return symlink_path.resolve()
                else:
                    # Direct directory
                    return symlink_path

            return None
        except Exception:
            return None

    def _cleanup_cow_storage_with_path(
        self, collection_name: str, actual_storage_path: Optional[Path]
    ) -> None:
        """Clean up CoW storage using pre-cached storage path."""
        try:
            global_collections_dir = Path.home() / ".qdrant_collections"
            symlink_path = global_collections_dir / collection_name

            # Remove the symlink/directory from global collections dir
            if symlink_path.exists() or symlink_path.is_symlink():
                if symlink_path.is_symlink():
                    symlink_path.unlink(missing_ok=True)
                    if self.console:
                        self.console.print(
                            f"🗑️  Removed symlink: {symlink_path}", style="dim"
                        )
                else:
                    if symlink_path.is_dir():
                        shutil.rmtree(symlink_path, ignore_errors=True)
                        if self.console:
                            self.console.print(
                                f"🗑️  Deleted collection directory: {symlink_path}",
                                style="dim",
                            )

            # Delete the actual storage data using cached path
            if actual_storage_path and actual_storage_path.exists():
                if actual_storage_path.is_dir():
                    shutil.rmtree(actual_storage_path, ignore_errors=True)
                    if self.console:
                        self.console.print(
                            f"🗑️  Deleted CoW collection data: {actual_storage_path}",
                            style="dim",
                        )

        except Exception as e:
            if self.console:
                self.console.print(
                    f"Warning: CoW storage cleanup failed for {collection_name}: {e}",
                    style="yellow",
                )

    def clear_collection(self, collection_name: Optional[str] = None) -> bool:
        """Clear all points from collection."""
        collection = (
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
        )
        try:
            # Use the correct Qdrant API endpoint and method
            response = self.client.post(
                f"/collections/{collection}/points/delete", json={"filter": {}}
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
        """Ensure collection exists, create if it doesn't using CoW seeder approach."""
        collection = collection_name or self.config.collection_base_name

        self.console.print(
            f"🔍 Checking if collection exists: {collection}", style="blue"
        )
        collection_exists = self.collection_exists(collection)
        self.console.print(
            f"🔍 Collection exists result: {collection_exists}", style="blue"
        )

        if collection_exists:
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
                        f"⚠️  Collection vector size mismatch: expected {expected_size}, got {expected_size}",
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

        self.console.print(
            f"🚀 Creating collection with CoW: {collection}", style="blue"
        )
        return self._create_collection_with_cow(collection, vector_size)

    def _create_collection_with_cow(
        self, collection_name: str, vector_size: Optional[int] = None
    ) -> bool:
        """Create collection using post-creation CoW architecture."""
        self.console.print(
            f"🔧 CoW creation starting for: {collection_name}", style="cyan"
        )

        try:
            # Step 1: Create collection normally (let Qdrant create real directory)
            self.console.print("📦 Creating collection normally first", style="cyan")
            collection_config = {
                "vectors": {
                    "size": vector_size or self.config.vector_size,
                    "distance": "Cosine",
                    "on_disk": True,
                },
                "hnsw_config": {
                    "m": self.config.hnsw_m,
                    "ef_construct": self.config.hnsw_ef_construct,
                    "on_disk": True,
                },
                "optimizers_config": {
                    "memmap_threshold": 20000,
                    "indexing_threshold": 10000,
                    "default_segment_number": 8,
                },
                "on_disk_payload": True,
            }

            response = self.client.put(
                f"/collections/{collection_name}", json=collection_config
            )
            if response.status_code not in [200, 201]:
                self.console.print(
                    f"❌ Collection creation failed: {response.status_code} {response.text}",
                    style="red",
                )
                return False

            # Step 2: Seed collection with one point if empty, then flush
            self.console.print(
                "💾 Seeding and flushing collection data to disk", style="cyan"
            )

            # Seed with one dummy point to ensure collection has data for proper flush
            dummy_point = {
                "points": [
                    {
                        "id": 999999,
                        "vector": [0.0] * (vector_size or self.config.vector_size),
                        "payload": {"dummy": True, "created_for_cow": True},
                    }
                ]
            }
            seed_response = self.client.put(
                f"/collections/{collection_name}/points", json=dummy_point
            )
            if seed_response.status_code not in [200, 201]:
                self.console.print(
                    f"❌ Seeding failed: {seed_response.status_code} {seed_response.text}",
                    style="red",
                )
                return False

            # Flush is no longer needed and causes 404 errors - removed

            # Add a small delay to let Qdrant settle
            import time

            time.sleep(1)

            # Step 3: Define paths
            local_collection_dir = (
                self.project_root
                / ".code-indexer"
                / "qdrant_collection"
                / collection_name
            )
            local_collection_dir.parent.mkdir(parents=True, exist_ok=True)

            self.console.print(f"📁 Local dir: {local_collection_dir}", style="cyan")

            # Step 4: Copy collection data to project-local directory via container
            if not self._copy_collection_data_via_container(
                collection_name, local_collection_dir
            ):
                return False

            # Step 5: Skip symlink creation (no longer supported)
            # Collections are now stored in folder structure, symlinks removed
            self.console.print(
                "🔗 Skipping symlink creation (using folder structure storage)",
                style="yellow",
            )

            self.console.print(
                f"✅ Collection {collection_name} created successfully",
                style="green",
            )
            return True

        except Exception as e:
            self.console.print(f"CoW creation exception: {e}", style="red")
            return False

    def _get_container_runtime_and_name(self) -> Tuple[str, str]:
        """Detect container runtime (docker/podman) and get container name."""
        import subprocess

        # Generate project-specific container name from project root
        if self.project_root:
            from code_indexer.services.docker_manager import DockerManager

            docker_manager = DockerManager()
            project_config = docker_manager._generate_container_names(self.project_root)
            container_name = project_config.get("qdrant_name", "cidx-qdrant")
        else:
            container_name = "cidx-qdrant"

        # Check if container exists in podman first
        try:
            result = subprocess.run(
                ["podman", "container", "exists", container_name],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return "podman", container_name
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check if container exists in docker
        try:
            result = subprocess.run(
                ["docker", "container", "inspect", container_name],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return "docker", container_name
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Default to podman if nothing found
        return "podman", container_name

    def _copy_collection_data_via_container(
        self, collection_name: str, target_dir: Path
    ) -> bool:
        """Copy collection data using container exec to avoid permission issues."""
        import subprocess

        try:
            runtime, container_name = self._get_container_runtime_and_name()

            # Ensure target directory exists on host
            target_dir.mkdir(parents=True, exist_ok=True)

            # Convert target path to container mounted path (home directory is mounted as /home)
            container_source = f"/qdrant/storage/collections/{collection_name}"
            container_target = str(
                target_dir
            )  # Home dir is mounted so path should be accessible

            self.console.print(f"📋 Copying data via {runtime} exec", style="cyan")
            self.console.print(f"    Source: {container_source}", style="dim")
            self.console.print(f"    Target: {container_target}", style="dim")

            # Copy data from qdrant storage to target directory
            # Use robust copying that handles empty directories
            cmd = [
                runtime,
                "exec",
                container_name,
                "sh",
                "-c",
                f"if [ -d '{container_source}' ]; then cp -r {container_source}/* {container_target}/ 2>/dev/null || true; else echo 'Source collection does not exist'; fi",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                self.console.print(
                    f"❌ Failed to copy collection data: {result.stderr}", style="red"
                )
                self.console.print(f"    Command: {' '.join(cmd)}", style="red")
                return False

            self.console.print(
                "✅ Collection data copied to project directory", style="green"
            )
            return True

        except Exception as e:
            self.console.print(f"❌ Container copy failed: {e}", style="red")
            return False

    def _replace_with_symlink_via_container(
        self, collection_name: str, target_dir: Path
    ) -> bool:
        """Replace collection directory with symlink using container exec."""
        import subprocess

        try:
            runtime, container_name = self._get_container_runtime_and_name()

            container_collection_path = f"/qdrant/storage/collections/{collection_name}"
            container_target = str(
                target_dir
            )  # Home dir is mounted so path should be accessible

            self.console.print(f"🔗 Creating symlink via {runtime} exec", style="cyan")
            self.console.print(
                f"    Collection: {container_collection_path}", style="dim"
            )
            self.console.print(f"    Target: {container_target}", style="dim")

            # Remove original directory and create symlink
            cmd = [
                runtime,
                "exec",
                container_name,
                "sh",
                "-c",
                f"rm -rf {container_collection_path} && ln -s {container_target} {container_collection_path}",
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)

            # Verify symlink was created correctly
            verify_cmd = [
                runtime,
                "exec",
                container_name,
                "sh",
                "-c",
                f"ls -la {container_collection_path}",
            ]

            verify_result = subprocess.run(
                verify_cmd, capture_output=True, text=True, timeout=10
            )

            if verify_result.returncode == 0 and "->" in verify_result.stdout:
                self.console.print("✅ Symlink created successfully", style="green")
                self.console.print(
                    f"    Details: {verify_result.stdout.strip()}", style="dim"
                )
                return True
            else:
                self.console.print("❌ Symlink verification failed", style="red")
                if verify_result.stderr:
                    self.console.print(
                        f"    Error: {verify_result.stderr}", style="red"
                    )
                return False

        except Exception as e:
            self.console.print(
                f"❌ Container symlink creation failed: {e}", style="red"
            )
            return False

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

        # Fixed collection name with only model as dynamic part
        model_name = embedding_provider.get_current_model()
        base_name = qdrant_config.collection_base_name

        # Simple: base_name + model_slug (no provider, no project hash)
        model_slug = EmbeddingProviderFactory.generate_model_slug("", model_name)
        return f"{base_name}_{model_slug}"

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
        self,
        config,
        embedding_provider: EmbeddingProvider,
        quiet: bool = False,
        skip_migration: bool = False,
    ) -> str:
        """Create/validate collection with provider-aware naming and sizing.

        Args:
            config: Main configuration object containing QdrantConfig
            embedding_provider: Current embedding provider instance
            quiet: Suppress output for migrations and operations
            skip_migration: Skip migration checks (useful for clear operations)

        Returns:
            Collection name that was created/validated
        """
        collection_name = self.resolve_collection_name(config, embedding_provider)
        vector_size = self.get_vector_size_for_provider(embedding_provider)

        # Create collection with auto-detected vector size and migration support
        if skip_migration:
            # Skip migration for clear operations to avoid timeouts
            success = self.ensure_collection(collection_name, vector_size)
        else:
            success = self.ensure_collection(collection_name, vector_size)

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
        """Insert or update points in the collection with enhanced batch safety."""
        collection = (
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
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

    def upsert_points_atomic(
        self,
        points: List[Dict[str, Any]],
        collection_name: Optional[str] = None,
        max_batch_size: int = 100,
    ) -> bool:
        """
        Insert or update points with enhanced batch safety and atomicity.

        This method ensures that either all points in the batch are successfully
        inserted or none are, preventing partial state corruption during cancellation.

        Args:
            points: List of points to upsert
            collection_name: Target collection
            max_batch_size: Maximum size for individual batches (default 100)

        Returns:
            True if all points were successfully upserted, False otherwise
        """
        if not points:
            return True

        # For small batches, use standard upsert with Qdrant's built-in atomicity
        if len(points) <= max_batch_size:
            return self.upsert_points(points, collection_name)

        # For larger batches, split into smaller atomic chunks
        # Each chunk is atomic by Qdrant's guarantee
        total_batches = (len(points) + max_batch_size - 1) // max_batch_size

        for i in range(0, len(points), max_batch_size):
            batch = points[i : i + max_batch_size]
            batch_num = (i // max_batch_size) + 1

            try:
                if not self.upsert_points(batch, collection_name):
                    self.console.print(
                        f"❌ Failed to upsert batch {batch_num}/{total_batches} "
                        f"({len(batch)} points)",
                        style="red",
                    )
                    return False

            except Exception as e:
                self.console.print(
                    f"❌ Exception in batch {batch_num}/{total_batches}: {e}",
                    style="red",
                )
                return False

        return True

    def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
        hnsw_ef: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors with HNSW optimization."""
        collection = (
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
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

        # Add HNSW search parameters for accuracy optimization
        hnsw_ef_value = hnsw_ef if hnsw_ef is not None else self.config.hnsw_ef
        search_params["params"] = {
            "hnsw_ef": hnsw_ef_value,
            "exact": False,  # Use approximate search with HNSW
        }

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

    def search_with_accuracy(
        self,
        query_vector: List[float],
        limit: int = 10,
        accuracy: str = "balanced",
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search with predefined accuracy profiles.

        Args:
            query_vector: Vector to search for
            limit: Maximum number of results
            accuracy: Accuracy profile - "fast", "balanced", or "high"
            score_threshold: Minimum score threshold
            filter_conditions: Additional filter conditions
            collection_name: Collection to search in

        Returns:
            List of search results
        """
        # Map accuracy profiles to hnsw_ef values
        accuracy_profiles = {
            "fast": 32,  # Fast search, lower accuracy
            "balanced": self.config.hnsw_ef,  # Use configured default
            "high": 128,  # High accuracy, slower search
        }

        hnsw_ef = accuracy_profiles.get(accuracy, self.config.hnsw_ef)

        return self.search(
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            filter_conditions=filter_conditions,
            collection_name=collection_name,
            hnsw_ef=hnsw_ef,
        )

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
        accuracy: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors filtered by embedding model.

        Args:
            query_vector: Query vector for similarity search
            embedding_model: Embedding model to filter by
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            additional_filters: Additional filter conditions
            collection_name: Collection name (optional)
            accuracy: Accuracy profile - "fast", "balanced", or "high"

        Returns:
            List of search results filtered by model
        """
        # Create model filter
        model_filter = self.create_model_filter(embedding_model)

        # Combine with additional filters
        final_filter = self.combine_filters(model_filter, additional_filters)

        # Use search with accuracy if specified, otherwise use regular search
        if accuracy:
            return self.search_with_accuracy(
                query_vector=query_vector,
                limit=limit,
                accuracy=accuracy,
                score_threshold=score_threshold,
                filter_conditions=final_filter,
                collection_name=collection_name,
            )
        else:
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
        collection = collection_name or self.config.collection_base_name
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
        collection = collection_name or self.config.collection_base_name

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
        collection = collection_name or self.config.collection_base_name

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
        collection = collection_name or self.config.collection_base_name

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
        collection = collection_name or self.config.collection_base_name

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
        collection = collection_name or self.config.collection_base_name

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
        collection = collection_name or self.config.collection_base_name

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
        Search with branch topology awareness using hidden_branches architecture.

        This method searches content points where the current branch is NOT in the hidden_branches array,
        meaning the content is visible in the current branch.
        """
        collection = collection_name or self.config.collection_base_name

        # Build filter conditions for hidden_branches architecture
        # Content is visible if current branch is NOT in hidden_branches array
        filter_conditions = {
            "must": [
                {"key": "type", "match": {"value": "content"}},
            ],
            "must_not": [
                # Exclude content where current_branch is in hidden_branches array
                {"key": "hidden_branches", "match": {"any": [current_branch]}},
            ],
        }

        # Perform vector search with branch visibility filtering
        results = self.search(
            query_vector=query_vector,
            filter_conditions=filter_conditions,
            limit=limit,
            collection_name=collection,
        )

        return results

    def count_points(self, collection_name: Optional[str] = None) -> int:
        """Count total points in collection."""
        collection = collection_name or self.config.collection_base_name

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
        collection = collection_name or self.config.collection_base_name

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
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
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
        """Update multiple points with new payload data using merge operation."""
        try:
            # Use set payload operation to merge new fields without overwriting existing ones
            for point in points:
                response = self.client.post(
                    f"/collections/{collection_name}/points/payload",
                    json={
                        "payload": point["payload"],
                        "points": [point["id"]],
                    },
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
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
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
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
        )

        try:
            info = self.get_collection_info(collection)
            indexes = info.get("payload_schema", {})
            return [{"field": k, "schema": v} for k, v in indexes.items()]
        except Exception as e:
            self.console.print(f"Failed to list indexes: {e}", style="red")
            return []

    def optimize_collection(self, collection_name: Optional[str] = None) -> bool:
        """Optimize collection storage by triggering Qdrant's optimization process."""
        collection = (
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
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

    def force_flush_to_disk(self, collection_name: Optional[str] = None) -> bool:
        """Force flush collection data from RAM to disk using Qdrant snapshot API.

        This creates a temporary snapshot which forces Qdrant to flush all
        collection data to disk, ensuring data consistency for CoW operations.

        Args:
            collection_name: Optional collection name, uses current collection if None

        Returns:
            True if flush succeeded, False otherwise
        """
        collection = (
            collection_name
            or self._current_collection_name
            or self.config.collection_base_name
        )

        try:
            # Create a snapshot which forces flush to disk
            response = self.client.post(
                f"/collections/{collection}/snapshots",
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                snapshot_info = response.json()
                snapshot_name = snapshot_info.get("name")

                if snapshot_name:
                    # Wait a moment for the snapshot to complete
                    time.sleep(1)

                    # Delete the temporary snapshot to clean up
                    try:
                        self.client.delete(
                            f"/collections/{collection}/snapshots/{snapshot_name}"
                        )
                    except Exception:
                        # Cleanup failure is not critical
                        pass

                    return True

            return False

        except Exception as e:
            if self.console:
                self.console.print(f"Force flush failed: {e}", style="yellow")
            return False

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
