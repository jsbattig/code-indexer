"""
Test suite setup utilities.

This module provides utilities for setting up the test environment,
including cleanup of dangling test collections to ensure fast startup.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
import threading

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from code_indexer.config import ConfigManager
from code_indexer.services.docker_manager import DockerManager
from rich.console import Console

# Global lock for thread-safe collection tracking
_collection_lock = threading.Lock()

# Test collection tracking file
TEST_COLLECTIONS_FILE = Path(__file__).parent.parent / "test_collections.txt"


def register_test_collection(collection_name: str) -> None:
    """
    Register a test collection for cleanup.

    This function should be called by e2e tests when they create collections
    that need to be cleaned up after the test suite completes.

    Args:
        collection_name: Name of the collection to register for cleanup
    """
    with _collection_lock:
        # Read existing collections
        existing_collections = set()
        if TEST_COLLECTIONS_FILE.exists():
            try:
                with open(TEST_COLLECTIONS_FILE, "r") as f:
                    existing_collections = set(
                        line.strip() for line in f if line.strip()
                    )
            except Exception:
                pass  # File might be corrupted, start fresh

        # Add new collection
        existing_collections.add(collection_name)

        # Write back to file
        try:
            with open(TEST_COLLECTIONS_FILE, "w") as f:
                for collection in sorted(existing_collections):
                    f.write(f"{collection}\n")
        except Exception as e:
            # Non-fatal error, just print warning
            print(f"Warning: Could not register test collection {collection_name}: {e}")


def get_tracked_test_collections() -> Set[str]:
    """
    Get all tracked test collections.

    Returns:
        Set of collection names that have been registered for cleanup
    """
    with _collection_lock:
        if not TEST_COLLECTIONS_FILE.exists():
            return set()

        try:
            with open(TEST_COLLECTIONS_FILE, "r") as f:
                return set(line.strip() for line in f if line.strip())
        except Exception:
            return set()


def clear_tracked_test_collections() -> None:
    """
    Clear the test collection tracking file.

    This should be called after cleanup is complete.
    """
    with _collection_lock:
        try:
            if TEST_COLLECTIONS_FILE.exists():
                TEST_COLLECTIONS_FILE.unlink()
        except Exception:
            pass  # Best effort cleanup


def with_collection_tracking(collection_name: str):
    """
    Decorator to automatically register test collections for cleanup.

    Args:
        collection_name: Name of the collection to register

    Usage:
        @with_collection_tracking("test_collection_name")
        def test_my_e2e_function():
            # Test code here
            pass
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            # Register collection before test
            register_test_collection(collection_name)
            try:
                return func(*args, **kwargs)
            finally:
                # Collection will be cleaned up during suite teardown
                pass

        return wrapper

    return decorator


def create_test_collection_context(base_name: str = "test_collection"):
    """
    Context manager for creating test collections with automatic cleanup registration.

    Args:
        base_name: Base name for the collection

    Returns:
        Context manager that yields a unique collection name

    Usage:
        with create_test_collection_context("my_test") as collection_name:
            # Use collection_name in your test
            # Collection will be automatically registered for cleanup
    """
    import uuid
    from contextlib import contextmanager

    @contextmanager
    def collection_context():
        # Generate unique collection name
        unique_id = str(uuid.uuid4())[:8]
        collection_name = f"{base_name}_{unique_id}"

        # Register for cleanup
        register_test_collection(collection_name)

        try:
            yield collection_name
        finally:
            # Collection will be cleaned up during suite teardown
            pass

    return collection_context()


def cleanup_test_collections(
    patterns: Optional[List[str]] = None,
    dry_run: bool = False,
    console: Optional[Console] = None,
    filesystem_port: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Clean up test collections that have been tracked by e2e tests.

    This function uses the test collection tracking file to identify collections
    that were created by e2e tests and need to be cleaned up, providing a safer
    alternative to pattern-based cleanup that could accidentally delete production collections.

    Args:
        patterns: DEPRECATED - ignored, kept for compatibility
        dry_run: If True, only show what would be deleted
        console: Rich console for output

    Returns:
        Dict with cleanup results
    """
    if console is None:
        console = Console()

    try:
        # Get tracked test collections
        tracked_collections = get_tracked_test_collections()

        if not tracked_collections:
            console.print("✨ No test collections found to clean up", style="green")
            return {"deleted": [], "errors": [], "total_deleted": 0, "total_errors": 0}

        console.print(
            f"🧹 Cleaning up {len(tracked_collections)} tracked test collections"
        )

        # Note: Filesystem container backend removed in Story #505
        # FilesystemVectorStore doesn't require external services
        console.print(
            "⚠️  Filesystem container backend removed - no cleanup needed",
            style="yellow",
        )
        return {"error": "Filesystem backend removed", "total_deleted": 0}

    except Exception as e:
        error_msg = f"Test collection cleanup failed: {str(e)}"
        if console:
            console.print(f"❌ {error_msg}", style="red")
        return {"error": error_msg, "total_deleted": 0}


def should_run_cleanup() -> bool:
    """
    Determine if cleanup should run based on environment.

    Only run cleanup for local full test suite execution, not CI/GitHub Actions.
    """
    import os

    # Skip if running in GitHub Actions
    if os.getenv("GITHUB_ACTIONS"):
        return False

    # Skip if running in CI environment
    if os.getenv("CI"):
        return False

    # Skip if explicitly disabled
    if os.getenv("SKIP_TEST_CLEANUP"):
        return False

    # Only run if explicitly enabled for full automation
    if os.getenv("FULL_AUTOMATION") or os.getenv("RUN_TEST_CLEANUP"):
        return True

    # Default: don't run unless explicitly requested
    return False


def start_services_for_test_suite(
    console: Optional[Console] = None,
) -> Tuple[bool, Optional[int]]:
    """
    Start Docker services as prerequisite for test suite execution.

    Args:
        console: Rich console for output

    Returns:
        Tuple of (success, filesystem_port) where success indicates if services started successfully
    """
    if console is None:
        console = Console()

    try:
        # Load configuration
        config_manager = ConfigManager.create_with_backtrack()
        config_manager.load()

        # Use a consistent path for all test containers to avoid creating multiple container sets
        shared_test_path = Path.home() / ".tmp" / "shared_test_containers"
        shared_test_path.mkdir(parents=True, exist_ok=True)

        # Create Docker manager with VoyageAI config for test stability
        voyage_config = {
            "embedding_provider": "voyage-ai",
            "codebase_dir": str(shared_test_path),  # Required by start_services method
        }
        # Use project-specific container model: pass project_name and ensure project setup
        docker_manager = DockerManager(
            console=console,
            project_name="test_shared",  # Fixed project name for test suite - consistent across all tests
        )
        docker_manager.set_indexing_root(shared_test_path)

        # Check current status intelligently
        status = docker_manager.get_service_status()
        required_services = docker_manager.get_required_services(voyage_config)

        # Check if all required services are running properly
        all_services_ready = status.get("status") == "running" and len(
            status.get("services", {})
        ) >= len(required_services)

        if all_services_ready:
            # All required Docker services are running, verify health
            # Note: Filesystem container backend removed in Story #505
            pass

        # Note: Filesystem container backend removed in Story #505
        # FilesystemVectorStore doesn't require external services
        pass

        console.print("🔧 Starting Docker services for test suite...", style="blue")

        # Start services
        success = docker_manager.start_services()
        if not success:
            console.print("❌ Failed to start Docker services", style="red")
            return False, None

        # Docker manager already validated services are running and healthy
        console.print("✅ Services are ready!", style="green")

        # Docker manager starts services successfully, so cleanup can proceed
        # Try the default port first since existing services might be available
        return True, 6333

    except Exception as e:
        console.print(f"❌ Error starting services: {str(e)}", style="red")
        return False, None


def setup_test_suite(console: Optional[Console] = None, force: bool = False) -> bool:
    """
    Complete test suite setup including service startup and collection cleanup.

    This should be called once at the beginning of full test suite execution.
    Only runs cleanup in appropriate environments (not CI/GitHub Actions).

    Args:
        console: Rich console for output
        force: Force cleanup regardless of environment checks

    Returns:
        True if setup was successful, False otherwise
    """
    if console is None:
        console = Console()

    # Check if cleanup should run
    if not force and not should_run_cleanup():
        console.print(
            "ℹ️  Skipping test collection cleanup (CI/fast test environment)",
            style="dim",
        )
        return True

    console.print("🚀 Setting up test suite environment...", style="bold blue")

    # Start services as prerequisite
    success, filesystem_port = start_services_for_test_suite(console=console)
    if not success:
        console.print(
            "❌ Failed to start services for test suite",
            style="red",
        )
        return False

    # Clean up test collections
    cleanup_result = cleanup_test_collections(
        console=console, filesystem_port=filesystem_port
    )

    if "error" in cleanup_result:
        console.print(
            f"⚠️  Collection cleanup had issues: {cleanup_result['error']}",
            style="yellow",
        )
        return False

    total_deleted = cleanup_result.get("total_deleted", 0)
    if total_deleted > 0:
        console.print(
            f"🎯 Cleaned up {total_deleted} test collections for faster startup",
            style="green",
        )
    else:
        console.print("✨ No test collections found to clean up", style="green")

    console.print("✅ Test suite setup complete!", style="bold green")
    return True


if __name__ == "__main__":
    """
    Command line interface for test suite setup.
    Usage: python tests/suite_setup.py [--dry-run]
    """
    import argparse

    parser = argparse.ArgumentParser(description="Test suite setup and cleanup")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be cleaned up without actually deleting",
    )
    args = parser.parse_args()

    console = Console()

    if args.dry_run:
        console.print(
            "🔍 Dry run mode - showing what would be cleaned up", style="blue"
        )
        cleanup_test_collections(dry_run=True, console=console)
    else:
        setup_test_suite(console=console)
