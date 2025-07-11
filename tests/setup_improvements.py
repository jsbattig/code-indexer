"""
Improved test setup utilities for faster, more reliable tests.
"""

import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple


def ensure_clean_test_state(
    project_path: Path, collection_name: Optional[str] = None, force_clean: bool = True
) -> Tuple[bool, str]:
    """
    Ensure a clean test state by checking and cleaning existing resources.

    Returns:
        Tuple of (success, message)
    """
    # 1. Check if services are already running
    status_result = subprocess.run(
        ["code-indexer", "status"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    services_running = status_result.returncode == 0

    if services_running and force_clean:
        # 2. Clean existing data without stopping services
        clean_result = subprocess.run(
            ["code-indexer", "clean", "--data-only"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if clean_result.returncode != 0:
            # If clean fails, we might need to clear specific collection
            if collection_name:
                clear_result = subprocess.run(
                    ["code-indexer", "clear", collection_name, "--force"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if clear_result.returncode != 0:
                    return False, f"Failed to clear collection: {clear_result.stderr}"

    return True, "Clean state ensured"


def fast_service_startup(
    project_path: Path, embedding_provider: str = "voyage-ai", max_wait: int = 30
) -> Tuple[bool, str]:
    """
    Fast service startup that reuses existing containers when possible.

    Args:
        project_path: Project directory
        embedding_provider: Embedding provider to use
        max_wait: Maximum seconds to wait for services

    Returns:
        Tuple of (success, message)
    """
    # 1. First check if services are already healthy
    status_result = subprocess.run(
        ["code-indexer", "status"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    if status_result.returncode == 0:
        stdout = status_result.stdout.lower()
        # Check if required services are healthy
        if "qdrant" in stdout and ("healthy" in stdout or "✅" in stdout):
            if embedding_provider == "voyage-ai":
                # For voyage-ai, we don't need ollama
                if "not needed" in stdout or "voyage" in stdout:
                    return True, "Services already running and healthy"
            else:
                # For ollama provider, check if ollama is healthy
                if "ollama" in stdout and ("healthy" in stdout or "✅" in stdout):
                    return True, "Services already running and healthy"

    # 2. Initialize if needed
    init_result = subprocess.run(
        ["code-indexer", "init", "--force", "--embedding-provider", embedding_provider],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    if init_result.returncode != 0:
        return False, f"Failed to initialize: {init_result.stderr}"

    # 3. Start services (or ensure they're running)
    start_result = subprocess.run(
        ["code-indexer", "start", "--quiet"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=max_wait,
    )

    if start_result.returncode != 0:
        # Check if it's just "already running"
        if (
            "already" in start_result.stdout.lower()
            or "already" in start_result.stderr.lower()
        ):
            # Services are running, just need to wait for health
            pass
        else:
            return False, f"Failed to start services: {start_result.stderr}"

    # 4. Wait for services to be healthy (with short polling)
    start_time = time.time()
    while time.time() - start_time < max_wait:
        health_result = subprocess.run(
            ["code-indexer", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if health_result.returncode == 0:
            stdout = health_result.stdout.lower()
            if "healthy" in stdout or "✅" in stdout:
                return True, "Services started and healthy"

        time.sleep(1)

    return False, f"Services did not become healthy within {max_wait} seconds"


def ensure_test_collection(
    project_path: Path, collection_name: str, clear_if_exists: bool = True
) -> Tuple[bool, str]:
    """
    Ensure a test collection is ready for use.

    Args:
        project_path: Project directory
        collection_name: Name of the collection
        clear_if_exists: Whether to clear existing collection

    Returns:
        Tuple of (success, message)
    """
    from code_indexer.config import ConfigManager
    from code_indexer.services.qdrant import QdrantClient
    from code_indexer.services.embedding_factory import EmbeddingProviderFactory

    try:
        # Load configuration
        config_manager = ConfigManager.create_with_backtrack(project_path)
        config = config_manager.load()

        # Create clients
        embedding_provider = EmbeddingProviderFactory.create(config)
        qdrant_client = QdrantClient(config.qdrant)

        # Check if collection exists
        resolved_name = qdrant_client.resolve_collection_name(
            config, embedding_provider
        )

        if qdrant_client.collection_exists(resolved_name):
            if clear_if_exists:
                # Clear the collection
                qdrant_client.clear_collection(resolved_name)
                return True, f"Collection {resolved_name} cleared"
            else:
                # Verify it's compatible
                info = qdrant_client.get_collection_info(resolved_name)
                expected_dim = embedding_provider.dimension
                actual_dim = info.config.params.vectors.size

                if actual_dim != expected_dim:
                    # Dimension mismatch - need to recreate
                    qdrant_client.delete_collection(resolved_name)
                    qdrant_client.ensure_collection(resolved_name, expected_dim)
                    return (
                        True,
                        f"Collection {resolved_name} recreated with correct dimensions",
                    )

                return True, f"Collection {resolved_name} exists and is compatible"
        else:
            # Create collection
            qdrant_client.ensure_collection(resolved_name, embedding_provider.dimension)
            return True, f"Collection {resolved_name} created"

    except Exception as e:
        return False, f"Failed to ensure collection: {str(e)}"


def improved_adaptive_setup(
    project_path: Path,
    embedding_provider: str = "voyage-ai",
    collection_name: Optional[str] = None,
    force_clean: bool = True,
    max_wait: int = 30,
) -> bool:
    """
    Improved adaptive setup that handles existing state properly.

    This replaces adaptive_service_setup with better state handling.
    """
    print(f"🔧 Setting up test environment in {project_path}")

    # 1. Ensure clean state
    success, msg = ensure_clean_test_state(project_path, collection_name, force_clean)
    if not success:
        print(f"❌ Failed to ensure clean state: {msg}")
        return False

    # 2. Fast service startup
    success, msg = fast_service_startup(project_path, embedding_provider, max_wait)
    if not success:
        print(f"❌ Failed to start services: {msg}")
        return False

    print(f"✅ {msg}")

    # 3. Ensure collection if specified
    if collection_name:
        success, msg = ensure_test_collection(project_path, collection_name, True)
        if not success:
            print(f"❌ Failed to ensure collection: {msg}")
            return False
        print(f"✅ {msg}")

    return True
