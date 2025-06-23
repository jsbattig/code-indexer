"""
Test suite setup utilities.

This module provides utilities for setting up the test environment,
including cleanup of dangling test collections to ensure fast startup.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from code_indexer.config import ConfigManager
from code_indexer.services.qdrant import QdrantClient
from code_indexer.services.docker_manager import DockerManager
from rich.console import Console


def cleanup_test_collections(
    patterns: Optional[List[str]] = None,
    dry_run: bool = False,
    console: Optional[Console] = None,
) -> Dict[str, Any]:
    """
    Clean up test collections that may have been left from previous test runs.

    This should be called once at the beginning of the test suite execution
    to prevent accumulation of test collections that slow down Qdrant startup.

    Args:
        patterns: List of collection patterns to clean up (default: ['test_*'])
        dry_run: If True, only show what would be deleted
        console: Rich console for output

    Returns:
        Dict with cleanup results
    """
    if patterns is None:
        patterns = [
            "test_*",  # Explicit test collections
            "code_index_????????_*",  # Test collections with 8-char hash: code_index_<hash>_<provider>_<model>
        ]

    if console is None:
        console = Console()

    try:
        # Load configuration
        config_manager = ConfigManager.create_with_backtrack()
        config = config_manager.load()

        # Check if Qdrant is available directly (more reliable than Docker status)
        qdrant_client = QdrantClient(config.qdrant, console=console)
        if not qdrant_client.health_check():
            console.print(
                "⚠️  Qdrant service not accessible, skipping collection cleanup",
                style="yellow",
            )
            return {"error": "Qdrant not accessible", "total_deleted": 0}

        console.print(f"🧹 Cleaning up collections matching patterns: {patterns}")

        result: Dict[str, Any] = qdrant_client.cleanup_collections(
            patterns, dry_run=dry_run
        )

        if "error" in result:
            console.print(
                f"❌ Collection cleanup failed: {result['error']}", style="red"
            )
            return result

        if dry_run:
            total_would_delete = result.get("total_would_delete", 0)
            console.print(
                f"🔍 Would delete {total_would_delete} collections", style="blue"
            )
            return result
        else:
            total_deleted = result.get("total_deleted", 0)
            total_errors = result.get("total_errors", 0)

            if total_deleted > 0:
                console.print(
                    f"✅ Successfully deleted {total_deleted} test collections",
                    style="green",
                )

            if total_errors > 0:
                console.print(
                    f"⚠️  {total_errors} collections had errors during deletion",
                    style="yellow",
                )

            return result

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


def start_services_for_test_suite(console: Optional[Console] = None) -> bool:
    """
    Start Docker services as prerequisite for test suite execution.

    Args:
        console: Rich console for output

    Returns:
        True if services started successfully, False otherwise
    """
    if console is None:
        console = Console()

    try:
        # Load configuration
        config_manager = ConfigManager.create_with_backtrack()
        config = config_manager.load()

        # Create Docker manager with VoyageAI config for test stability
        voyage_config = {"embedding_provider": "voyage-ai"}
        docker_manager = DockerManager(console=console, main_config=voyage_config)

        # Check current status intelligently
        status = docker_manager.get_service_status()
        required_services = docker_manager.get_required_services(voyage_config)

        # Check if all required services are running properly
        all_services_ready = status.get("status") == "running" and len(
            status.get("services", {})
        ) >= len(required_services)

        if all_services_ready:
            # All required Docker services are running, verify health
            try:
                qdrant_client = QdrantClient(config.qdrant, console=console)
                if qdrant_client.health_check():
                    console.print(
                        "✅ All required services already running and ready!",
                        style="green",
                    )
                    return True
            except Exception:
                pass

        # Check if essential services are accessible even if Docker shows stopped
        # (This handles the case where services run outside Docker or via different setup)
        try:
            qdrant_client = QdrantClient(config.qdrant, console=console)
            if qdrant_client.health_check():
                console.print(
                    "✅ Essential services accessible, tests can proceed", style="green"
                )
                return True
        except Exception:
            pass

        console.print("🔧 Starting Docker services for test suite...", style="blue")

        # Start services
        success = docker_manager.start_services()
        if not success:
            console.print("❌ Failed to start Docker services", style="red")
            return False

        # Wait for services to be ready
        console.print("⏳ Waiting for services to be ready...", style="blue")
        import time

        start_time = time.time()
        timeout = 60  # Reduced timeout since we already know services started

        while time.time() - start_time < timeout:
            status = docker_manager.get_service_status()
            if status.get("status") == "running":
                # Also check Qdrant health
                try:
                    qdrant_client = QdrantClient(config.qdrant, console=console)
                    if qdrant_client.health_check():
                        console.print("✅ Services are ready!", style="green")
                        return True
                except Exception:
                    pass
            time.sleep(2)  # Reduced sleep time

        console.print("⚠️  Services startup timeout", style="yellow")
        return False

    except Exception as e:
        console.print(f"❌ Error starting services: {str(e)}", style="red")
        return False


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
    success = start_services_for_test_suite(console=console)
    if not success:
        console.print(
            "❌ Failed to start services for test suite",
            style="red",
        )
        return False

    # Clean up test collections
    cleanup_result = cleanup_test_collections(console=console)

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
    Usage: python tests/test_suite_setup.py [--dry-run]
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
