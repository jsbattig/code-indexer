#!/usr/bin/env python3
"""
cleanup-all-collections.py
Remove ALL collections from Qdrant before shutdown.
This is useful for complete cleanup when you want to start fresh.
"""

import sys
import os
from pathlib import Path

# Add project paths
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir / "src"))
sys.path.insert(0, str(script_dir / "tests"))


def cleanup_all_collections(project_root: Path = None) -> bool:
    """Remove ALL collections from Qdrant instance(s).

    Args:
        project_root: Optional project root. If not provided, uses current directory.

    Returns:
        True if cleanup was successful, False otherwise.
    """
    try:
        from code_indexer.services.qdrant import QdrantClient
        from code_indexer.config import ConfigManager
        from rich.console import Console

        console = Console()

        # If no project root provided, use current directory
        if project_root is None:
            project_root = Path.cwd()

        # Try to load config from project root
        config_path = project_root / ".code-indexer" / "config.json"
        if not config_path.exists():
            console.print(f"⚠️  No config found at {config_path}", style="yellow")
            return False

        try:
            config_manager = ConfigManager(config_path)
            config = config_manager.load()

            # Connect to Qdrant
            qdrant_client = QdrantClient(config.qdrant, project_root=project_root)

            # Check if Qdrant is healthy
            if not qdrant_client.health_check():
                console.print("❌ Qdrant is not running or not healthy", style="red")
                return False

            console.print(
                "🔍 Connected to Qdrant, listing all collections...", style="cyan"
            )

            # Get all collections
            all_collections = qdrant_client.list_collections()

            if not all_collections:
                console.print("ℹ️  No collections found in Qdrant", style="blue")
                return True

            console.print(f"📦 Found {len(all_collections)} collections:", style="cyan")
            for collection in all_collections:
                console.print(f"   • {collection}")

            # Ask for confirmation
            console.print(
                "\n⚠️  WARNING: This will delete ALL collections!", style="yellow bold"
            )
            console.print("This action cannot be undone.", style="yellow")

            if os.getenv("FORCE_CLEANUP") != "1":
                response = console.input(
                    "\nAre you sure you want to continue? (yes/no): "
                )
                if response.lower() != "yes":
                    console.print("❌ Cleanup cancelled", style="red")
                    return False
            else:
                console.print(
                    "🤖 FORCE_CLEANUP=1 detected, proceeding without confirmation",
                    style="cyan",
                )

            # Delete all collections
            console.print("\n🗑️  Deleting collections...", style="cyan")
            deleted_count = 0
            failed_count = 0

            for collection in all_collections:
                try:
                    if qdrant_client.delete_collection(collection):
                        console.print(f"   ✅ Deleted: {collection}", style="green")
                        deleted_count += 1
                    else:
                        console.print(
                            f"   ❌ Failed to delete: {collection}", style="red"
                        )
                        failed_count += 1
                except Exception as e:
                    console.print(
                        f"   ❌ Error deleting {collection}: {e}", style="red"
                    )
                    failed_count += 1

            # Summary
            console.print("\n📊 Cleanup complete:", style="cyan")
            console.print(
                f"   ✅ Successfully deleted: {deleted_count} collections",
                style="green",
            )
            if failed_count > 0:
                console.print(
                    f"   ❌ Failed to delete: {failed_count} collections", style="red"
                )

            return failed_count == 0

        except Exception as e:
            console.print(f"❌ Error during cleanup: {e}", style="red")
            import traceback

            traceback.print_exc()
            return False

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running this from the project root")
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Remove ALL collections from Qdrant")
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Project root directory (defaults to current directory)",
    )
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    # Set environment variable if force flag is used
    if args.force:
        os.environ["FORCE_CLEANUP"] = "1"

    # Run cleanup
    success = cleanup_all_collections(args.project_root)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
