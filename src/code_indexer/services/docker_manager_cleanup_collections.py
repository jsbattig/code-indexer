"""
Extension methods for DockerManager to clean collections before shutdown.
This can be integrated into the DockerManager class.

Note: These are example methods that would need to be added to the DockerManager class.
They are not standalone functions.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .docker_manager import DockerManager


def cleanup_collections_before_shutdown(
    self: "DockerManager", verbose: bool = False
) -> bool:
    """Clean all collections from Qdrant before shutting down containers.

    This ensures a clean state when containers are restarted.

    Args:
        verbose: Whether to print detailed output

    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        from ..config import ConfigManager
        from .qdrant import QdrantClient

        if verbose:
            self.console.print("🔍 Checking if Qdrant is running...", style="cyan")

        # Load configuration
        config_manager = ConfigManager.create_with_backtrack()
        config = config_manager.load()

        # Try to connect to Qdrant
        qdrant_client = QdrantClient(config.qdrant)

        # Check if Qdrant is healthy
        if not qdrant_client.health_check():
            if verbose:
                self.console.print(
                    "ℹ️  Qdrant is not running, skipping collection cleanup",
                    style="blue",
                )
            return True  # Not an error if Qdrant isn't running

        if verbose:
            self.console.print(
                "✅ Qdrant is running, listing collections...", style="green"
            )

        # Get all collections
        collections = qdrant_client.list_collections()

        if not collections:
            if verbose:
                self.console.print("ℹ️  No collections found", style="blue")
            return True

        if verbose:
            self.console.print(
                f"📦 Found {len(collections)} collections to remove", style="cyan"
            )

        # Delete all collections
        deleted_count = 0
        failed_count = 0

        for collection in collections:
            try:
                if qdrant_client.delete_collection(collection):
                    if verbose:
                        self.console.print(
                            f"   ✅ Deleted: {collection}", style="green"
                        )
                    deleted_count += 1
                else:
                    if verbose:
                        self.console.print(
                            f"   ❌ Failed to delete: {collection}", style="red"
                        )
                    failed_count += 1
            except Exception as e:
                if verbose:
                    self.console.print(
                        f"   ❌ Error deleting {collection}: {e}", style="red"
                    )
                failed_count += 1

        if verbose:
            self.console.print("\n📊 Collection cleanup summary:", style="cyan")
            self.console.print(
                f"   ✅ Deleted: {deleted_count} collections", style="green"
            )
            if failed_count > 0:
                self.console.print(
                    f"   ❌ Failed: {failed_count} collections", style="red"
                )

        return failed_count == 0

    except Exception as e:
        if verbose:
            self.console.print(f"❌ Error during collection cleanup: {e}", style="red")
        return False


def cleanup_with_collection_removal(
    self: "DockerManager",
    remove_data: bool = False,
    force: bool = False,
    verbose: bool = False,
    validate: bool = False,
    clean_collections: bool = True,
) -> bool:
    """Enhanced cleanup that optionally removes all collections before shutdown.

    Args:
        remove_data: Whether to remove data directories
        force: Whether to force cleanup even on errors
        verbose: Whether to print detailed output
        validate: Whether to validate cleanup
        clean_collections: Whether to remove all collections before shutdown

    Returns:
        True if cleanup was successful, False otherwise
    """
    cleanup_success = True

    try:
        if verbose:
            self.console.print("🔍 Starting enhanced cleanup process...", style="cyan")

        # Step 1: Clean collections if requested and Qdrant is running
        if clean_collections:
            if verbose:
                self.console.print(
                    "🗑️  Cleaning collections before shutdown...", style="cyan"
                )

            collection_cleanup_success = self.cleanup_collections_before_shutdown(  # type: ignore[attr-defined]
                verbose
            )

            if not collection_cleanup_success and not force:
                self.console.print("❌ Collection cleanup failed", style="red")
                return False
            elif not collection_cleanup_success:
                self.console.print(
                    "⚠️  Collection cleanup failed (continuing with force)",
                    style="yellow",
                )
                cleanup_success = False

        # Step 2: Run the original cleanup
        original_cleanup_success = self.cleanup(
            remove_data=remove_data, force=force, verbose=verbose, validate=validate
        )

        cleanup_success &= original_cleanup_success

        return cleanup_success

    except Exception as e:
        if verbose:
            self.console.print(f"❌ Error during enhanced cleanup: {e}", style="red")
        return False
