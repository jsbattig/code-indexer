"""Watch mode helper functions for auto-detection and orchestration.

This module provides functions for:
1. Auto-detecting existing indexes (semantic, FTS, temporal)
2. Orchestrating watch mode with detected indexes

Story: 02_Feat_WatchModeAutoDetection/01_Story_WatchModeAutoUpdatesAllIndexes.md
"""

import logging
import time
from pathlib import Path
from typing import Dict
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def detect_existing_indexes(project_root: Path) -> Dict[str, bool]:
    """Detect which indexes exist and should be watched.

    Args:
        project_root: Path to project root directory

    Returns:
        Dict mapping index type to existence boolean:
        {
            "semantic": bool,  # code-indexer-HEAD collection
            "fts": bool,       # tantivy-fts index
            "temporal": bool,  # code-indexer-temporal collection
        }

    Examples:
        >>> result = detect_existing_indexes(Path("/project"))
        >>> result["semantic"]
        True
        >>> result["fts"]
        False
    """
    index_base = project_root / ".code-indexer" / "index"

    return {
        "semantic": (index_base / "code-indexer-HEAD").exists(),
        "fts": (index_base / "tantivy-fts").exists(),
        "temporal": (index_base / "code-indexer-temporal").exists(),
    }


def start_watch_mode(
    project_root: Path,
    config_manager,
    smart_indexer=None,
    git_topology_service=None,
    watch_metadata=None,
    debounce: float = 2.0,
    batch_size: int = 100,
    enable_fts: bool = False,
):
    """Start watch mode with auto-detected handlers.

    This function orchestrates watch mode by:
    1. Detecting existing indexes
    2. Initializing appropriate handlers
    3. Starting watchdog Observer
    4. Monitoring for Ctrl+C to stop

    Args:
        project_root: Path to project root directory
        config_manager: ConfigManager instance
        smart_indexer: Optional SmartIndexer for semantic indexing
        git_topology_service: Optional GitTopologyService for git-aware watching
        watch_metadata: Optional WatchMetadata for watch session tracking
        debounce: Debounce delay in seconds (default: 2.0)
        batch_size: Batch size for indexing (default: 100)
        enable_fts: Enable FTS watch (legacy flag, auto-detection overrides)

    Returns:
        None (blocks until Ctrl+C)
    """
    from watchdog.observers import Observer

    # Detect available indexes
    available_indexes = detect_existing_indexes(project_root)

    # Count detected indexes
    detected_count = sum(available_indexes.values())

    if detected_count == 0:
        console.print("⚠️ No indexes found. Run 'cidx index' first.", style="yellow")
        return

    console.print(f"🔍 Detected {detected_count} index(es) to watch:", style="blue")

    # Initialize handlers for detected indexes
    handlers = []

    # Semantic index handler (GitAwareWatchHandler)
    if available_indexes["semantic"]:
        console.print("  ✅ Semantic index (HEAD collection)", style="green")

        # Import semantic watch dependencies lazily
        if (
            smart_indexer is None
            or git_topology_service is None
            or watch_metadata is None
        ):
            from code_indexer.services.smart_indexer import SmartIndexer
            from code_indexer.services.git_topology_service import GitTopologyService
            from code_indexer.services.watch_metadata import WatchMetadata
            from code_indexer.services.embedding_factory import EmbeddingProviderFactory
            from code_indexer.services.qdrant import QdrantClient

            config = config_manager.load()

            # Initialize semantic indexing components
            embedding_provider = EmbeddingProviderFactory.create(config, console)
            qdrant_client = QdrantClient(
                config.qdrant, console, Path(config.codebase_dir)
            )

            # Health checks
            if not embedding_provider.health_check():
                console.print(
                    f"❌ {embedding_provider.get_provider_name().title()} service not available",
                    style="red",
                )
                return

            if not qdrant_client.health_check():
                console.print("❌ Qdrant service not available", style="red")
                return

            # Initialize SmartIndexer
            metadata_path = config_manager.config_path.parent / "metadata.json"
            smart_indexer = SmartIndexer(
                config, embedding_provider, qdrant_client, metadata_path
            )

            # Initialize git topology service
            git_topology_service = GitTopologyService(config.codebase_dir)

            # Initialize watch metadata
            watch_metadata_path = (
                config_manager.config_path.parent / "watch_metadata.json"
            )
            watch_metadata = WatchMetadata.load_from_disk(watch_metadata_path)

        # Create GitAwareWatchHandler
        from code_indexer.services.git_aware_watch_handler import GitAwareWatchHandler

        semantic_handler = GitAwareWatchHandler(
            config_manager.load(),
            smart_indexer,
            git_topology_service,
            watch_metadata,
            debounce_seconds=debounce,
        )
        handlers.append(semantic_handler)

        # Start git-aware monitoring
        semantic_handler.start_watching()

    # FTS index handler
    if available_indexes["fts"]:
        console.print("  ✅ FTS index (full-text search)", style="green")

        # Import FTS watch dependencies lazily
        from code_indexer.services.fts_watch_handler import FTSWatchHandler
        from code_indexer.services.tantivy_index_manager import TantivyIndexManager

        config = config_manager.load()
        fts_index_dir = project_root / ".code-indexer/index/tantivy-fts"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        fts_handler = FTSWatchHandler(tantivy_manager, config)
        handlers.append(fts_handler)

    # Temporal index handler
    if available_indexes["temporal"]:
        console.print("  ✅ Temporal index (git history commits)", style="green")

        # Import temporal watch dependencies lazily
        from code_indexer.cli_temporal_watch_handler import TemporalWatchHandler
        from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
        from code_indexer.services.temporal.temporal_progressive_metadata import (
            TemporalProgressiveMetadata,
        )
        from code_indexer.backends.filesystem_vector_store import FilesystemVectorStore

        temporal_index_dir = project_root / ".code-indexer/index/code-indexer-temporal"

        # Initialize vector store (FilesystemVectorStore)
        vector_store = FilesystemVectorStore(temporal_index_dir)

        # Create temporal indexer (using new API)
        temporal_indexer = TemporalIndexer(config_manager, vector_store)

        # Create progressive metadata
        progressive_metadata = TemporalProgressiveMetadata(temporal_index_dir)

        # Create TemporalWatchHandler
        temporal_handler = TemporalWatchHandler(
            project_root,
            temporal_indexer=temporal_indexer,
            progressive_metadata=progressive_metadata,
        )
        handlers.append(temporal_handler)

    # Start watchdog observer with all handlers
    observer = Observer()

    for handler in handlers:
        observer.schedule(handler, path=str(project_root), recursive=True)

    observer.start()

    console.print(
        f"👀 Watching {detected_count} index(es). Press Ctrl+C to stop.",
        style="blue",
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n🛑 Watch mode stopped", style="yellow")

    observer.stop()
    observer.join()

    # Stop semantic handler if present
    if available_indexes["semantic"] and handlers:
        semantic_handler = handlers[0]
        if hasattr(semantic_handler, "stop_watching"):
            semantic_handler.stop_watching()
