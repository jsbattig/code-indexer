"""Command line interface for Code Indexer."""

import datetime
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from rich.syntax import Syntax

from .config import ConfigManager
from .services import OllamaClient, QdrantClient, DockerManager
from .indexing import FileFinder, TextChunker


# Global console for rich output
console = Console()


@click.group()
@click.option("--config", "-c", type=click.Path(exists=False), help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool):
    """🔍 AI-powered semantic code search with local models."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config_manager"] = ConfigManager(Path(config) if config else None)


@cli.command()
@click.option(
    "--codebase-dir", "-d", type=click.Path(exists=True), help="Directory to index"
)
@click.option("--force", "-f", is_flag=True, help="Overwrite existing configuration")
@click.pass_context
def init(ctx, codebase_dir: Optional[str], force: bool):
    """Initialize code indexing in current directory."""
    config_manager = ctx.obj["config_manager"]

    # Check if config already exists
    if config_manager.config_path.exists() and not force:
        console.print(
            f"❌ Configuration already exists at {config_manager.config_path}"
        )
        console.print("Use --force to overwrite")
        sys.exit(1)

    try:
        # Create default config
        target_dir = Path(codebase_dir) if codebase_dir else Path.cwd()
        config = config_manager.create_default_config(target_dir.resolve())

        console.print(f"✅ Initialized configuration at {config_manager.config_path}")
        console.print(f"📁 Codebase directory: {config.codebase_dir}")
        console.print("🔧 Run 'code-indexer setup' to start services")

    except Exception as e:
        console.print(f"❌ Failed to initialize: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option("--model", "-m", help="Ollama model to use")
@click.option("--force-recreate", "-f", is_flag=True, help="Force recreate containers")
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.pass_context
def setup(ctx, model: Optional[str], force_recreate: bool, quiet: bool):
    """Setup and start required services (Ollama + Qdrant)."""
    config_manager = ctx.obj["config_manager"]

    try:
        # Use quiet console if requested
        setup_console = Console(quiet=quiet) if quiet else console
        config = config_manager.load()

        # Update model if specified
        if model:
            config.ollama.model = model
            config_manager.save(config)

        # Check Docker availability (auto-detect project name)
        docker_manager = DockerManager(setup_console)

        if not docker_manager.is_docker_available():
            setup_console.print(
                "❌ Docker is not available. Please install Docker first.", style="red"
            )
            sys.exit(1)

        if not docker_manager.is_compose_available():
            setup_console.print(
                "❌ Docker Compose is not available. Please install Docker Compose first.",
                style="red",
            )
            sys.exit(1)

        # Start services
        if not docker_manager.start_services(recreate=force_recreate):
            sys.exit(1)

        # Wait for services to be ready
        if not docker_manager.wait_for_services():
            setup_console.print("❌ Services failed to start properly", style="red")
            sys.exit(1)

        # Test connections and pull model
        with setup_console.status("Testing service connections..."):
            ollama_client = OllamaClient(config.ollama, setup_console)
            qdrant_client = QdrantClient(config.qdrant, setup_console)

            if not ollama_client.health_check():
                setup_console.print("❌ Ollama service is not accessible", style="red")
                sys.exit(1)

            if not qdrant_client.health_check():
                setup_console.print("❌ Qdrant service is not accessible", style="red")
                sys.exit(1)

        # Pull model if needed
        setup_console.print(f"🤖 Checking model: {config.ollama.model}")
        if not ollama_client.model_exists(config.ollama.model):
            if not ollama_client.pull_model(config.ollama.model):
                setup_console.print(
                    f"❌ Failed to pull model {config.ollama.model}", style="red"
                )
                sys.exit(1)

        # Ensure collection exists
        if not qdrant_client.ensure_collection():
            setup_console.print("❌ Failed to create Qdrant collection", style="red")
            sys.exit(1)

        setup_console.print("✅ Setup completed successfully!", style="green")
        setup_console.print(f"🔧 Ready to index codebase at: {config.codebase_dir}")

    except Exception as e:
        setup_console.print(f"❌ Setup failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option("--clear", "-c", is_flag=True, help="Clear existing index")
@click.option("--batch-size", "-b", default=50, help="Batch size for processing")
@click.pass_context
def index(ctx, clear: bool, batch_size: int):
    """Index the codebase for semantic search."""
    config_manager = ctx.obj["config_manager"]

    try:
        config = config_manager.load()

        # Initialize services
        ollama_client = OllamaClient(config.ollama, console)
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health checks
        if not ollama_client.health_check():
            console.print(
                "❌ Ollama service not available. Run 'setup' first.", style="red"
            )
            sys.exit(1)

        if not qdrant_client.health_check():
            console.print(
                "❌ Qdrant service not available. Run 'setup' first.", style="red"
            )
            sys.exit(1)

        # Clear index if requested
        if clear:
            console.print("🧹 Clearing existing index...")
            qdrant_client.clear_collection()

        # Initialize components
        file_finder = FileFinder(config)
        text_chunker = TextChunker(config.indexing)

        # Find files to index
        console.print("🔍 Finding files to index...")
        files_to_index = list(file_finder.find_files())

        if not files_to_index:
            console.print("❌ No files found to index", style="red")
            sys.exit(1)

        console.print(f"📄 Found {len(files_to_index)} files to index")

        # Process files with progress bar
        total_chunks = 0
        failed_files = 0

        with Progress() as progress:
            task = progress.add_task("Indexing files...", total=len(files_to_index))
            batch_points = []

            for file_path in files_to_index:
                try:
                    # Read and chunk file
                    chunks = text_chunker.chunk_file(file_path)

                    if not chunks:
                        progress.advance(task)
                        continue

                    # Process each chunk
                    for chunk in chunks:
                        # Get embedding
                        embedding = ollama_client.get_embedding(chunk["text"])

                        # Create point for Qdrant
                        point = qdrant_client.create_point(
                            vector=embedding,
                            payload={
                                "path": str(file_path.relative_to(config.codebase_dir)),
                                "content": chunk["text"],
                                "language": chunk["file_extension"],
                                "file_size": file_path.stat().st_size,
                                "chunk_index": chunk["chunk_index"],
                                "total_chunks": chunk["total_chunks"],
                                "indexed_at": time.strftime(
                                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                                ),
                            },
                        )

                        batch_points.append(point)
                        total_chunks += 1

                        # Process batch when full
                        if len(batch_points) >= batch_size:
                            if not qdrant_client.upsert_points(batch_points):
                                console.print("❌ Failed to index batch", style="red")
                            batch_points = []

                except Exception as e:
                    if ctx.obj["verbose"]:
                        console.print(
                            f"❌ Failed to process {file_path}: {e}", style="red"
                        )
                    failed_files += 1

                progress.advance(task)

            # Process remaining points
            if batch_points:
                qdrant_client.upsert_points(batch_points)

        # Save indexing metadata
        index_metadata = {
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files_processed": len(files_to_index) - failed_files,
            "chunks_indexed": total_chunks,
            "failed_files": failed_files,
        }

        metadata_path = config_manager.config_path.parent / "metadata.json"
        with open(metadata_path, "w") as f:
            import json

            json.dump(index_metadata, f, indent=2)

        console.print("✅ Indexing complete!", style="green")
        console.print(f"📄 Files processed: {len(files_to_index) - failed_files}")
        console.print(f"📦 Chunks indexed: {total_chunks}")

        if failed_files > 0:
            console.print(f"⚠️  Failed files: {failed_files}", style="yellow")

    except Exception as e:
        console.print(f"❌ Indexing failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option(
    "--since", type=click.DateTime(), help="Update files modified since this time"
)
@click.option("--batch-size", default=50, help="Batch size for processing")
@click.pass_context
def update(ctx, since: Optional[datetime.datetime], batch_size: int):
    """Update the index with modified files."""
    config_manager = ctx.obj["config_manager"]

    try:
        config = config_manager.load()

        # Initialize services
        ollama_client = OllamaClient(config.ollama, console)
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health checks
        if not ollama_client.health_check():
            console.print("❌ Ollama service not available", style="red")
            sys.exit(1)

        if not qdrant_client.health_check():
            console.print("❌ Qdrant service not available", style="red")
            sys.exit(1)

        # Get last index time if not specified
        if not since:
            metadata_path = config_manager.config_path.parent / "metadata.json"
            if metadata_path.exists():
                import json

                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                    since_str = metadata.get("indexed_at")
                    if since_str:
                        import datetime

                        since = datetime.datetime.fromisoformat(
                            since_str.replace("Z", "+00:00")
                        )

            if not since:
                console.print(
                    "❌ No previous index found. Use 'code-indexer index' first.",
                    style="red",
                )
                sys.exit(1)

        # Find modified and deleted files
        from .indexing import FileFinder, TextChunker

        file_finder = FileFinder(config)
        text_chunker = TextChunker(config.indexing)

        modified_files = list(file_finder.find_modified_files(since.timestamp()))
        deleted_files = file_finder.find_deleted_files(qdrant_client)

        if not modified_files and not deleted_files:
            console.print("✅ No changes since last index", style="green")
            return

        if modified_files:
            console.print(f"📄 Found {len(modified_files)} modified files")
        if deleted_files:
            console.print(f"🗑️  Found {len(deleted_files)} deleted files")

        # First, handle deleted files
        deleted_count = 0
        if deleted_files:
            console.print("🗑️  Removing deleted files from index...")
            for deleted_file in deleted_files:
                try:
                    qdrant_client.delete_by_filter(
                        {"must": [{"key": "path", "match": {"value": deleted_file}}]}
                    )
                    deleted_count += 1
                except Exception as e:
                    if ctx.obj["verbose"]:
                        console.print(
                            f"❌ Failed to delete {deleted_file}: {e}", style="red"
                        )

        # Process modified files
        total_chunks = 0
        failed_files = 0

        if modified_files:
            with Progress(console=console) as progress:
                task = progress.add_task("Updating index...", total=len(modified_files))
                batch_points = []

                for file_path in modified_files:
                    try:
                        # Delete existing points for this file first
                        relative_path = str(file_path.relative_to(config.codebase_dir))
                        qdrant_client.delete_by_filter(
                            {
                                "must": [
                                    {"key": "path", "match": {"value": relative_path}}
                                ]
                            }
                        )

                        # Read and chunk file
                        chunks = text_chunker.chunk_file(file_path)

                        if not chunks:
                            progress.advance(task)
                            continue

                        # Process each chunk
                        for chunk in chunks:
                            # Get embedding
                            embedding = ollama_client.get_embedding(chunk["text"])

                            # Create point for Qdrant
                            point = qdrant_client.create_point(
                                vector=embedding,
                                payload={
                                    "path": relative_path,
                                    "content": chunk["text"],
                                    "language": chunk["file_extension"],
                                    "file_size": file_path.stat().st_size,
                                    "chunk_index": chunk["chunk_index"],
                                    "total_chunks": chunk["total_chunks"],
                                    "indexed_at": time.strftime(
                                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                                    ),
                                },
                            )

                            batch_points.append(point)
                            total_chunks += 1

                            # Process batch when full
                            if len(batch_points) >= batch_size:
                                if not qdrant_client.upsert_points(batch_points):
                                    console.print(
                                        "❌ Failed to update batch", style="red"
                                    )
                                batch_points = []

                    except Exception as e:
                        if ctx.obj["verbose"]:
                            console.print(
                                f"❌ Failed to process {file_path}: {e}", style="red"
                            )
                        failed_files += 1

                    progress.advance(task)

                # Process remaining points
                if batch_points:
                    qdrant_client.upsert_points(batch_points)

        # Update metadata
        import json

        index_metadata = {
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files_updated": (
                len(modified_files) - failed_files if modified_files else 0
            ),
            "files_deleted": deleted_count,
            "chunks_updated": total_chunks,
            "failed_files": failed_files,
        }

        metadata_path = config_manager.config_path.parent / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                existing_metadata = json.load(f)
            existing_metadata.update(index_metadata)
            index_metadata = existing_metadata

        with open(metadata_path, "w") as f:
            json.dump(index_metadata, f, indent=2)

        console.print("✅ Index update complete!", style="green")
        if modified_files:
            console.print(f"📄 Files updated: {len(modified_files) - failed_files}")
            console.print(f"📦 Chunks updated: {total_chunks}")
        if deleted_files:
            console.print(f"🗑️  Files deleted: {deleted_count}")

        if failed_files > 0:
            console.print(f"⚠️  Failed files: {failed_files}", style="yellow")

    except Exception as e:
        console.print(f"❌ Update failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option(
    "--debounce", default=2.0, help="Seconds to wait before processing changes"
)
@click.option("--batch-size", default=50, help="Batch size for processing")
@click.pass_context
def watch(ctx, debounce: float, batch_size: int):
    """Watch for file changes and update index automatically."""
    config_manager = ctx.obj["config_manager"]

    try:
        import threading
        import time
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        from pathlib import Path

        config = config_manager.load()

        # Initialize services
        ollama_client = OllamaClient(config.ollama, console)
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health checks
        if not ollama_client.health_check():
            console.print("❌ Ollama service not available", style="red")
            sys.exit(1)

        if not qdrant_client.health_check():
            console.print("❌ Qdrant service not available", style="red")
            sys.exit(1)

        console.print(f"👀 Watching {config.codebase_dir} for changes...")
        console.print(f"⏱️  Debounce: {debounce}s")
        console.print("Press Ctrl+C to stop")

        # Track pending changes
        pending_changes = set()
        change_lock = threading.Lock()

        class CodeChangeHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return

                file_path = Path(event.src_path)

                # Check if file should be indexed
                from .indexing import FileFinder

                file_finder = FileFinder(config)

                try:
                    if file_finder._should_include_file(file_path):
                        with change_lock:
                            pending_changes.add(file_path)
                except ValueError:
                    # File outside codebase directory
                    pass

            def on_deleted(self, event):
                if event.is_directory:
                    return

                file_path = Path(event.src_path)

                try:
                    with change_lock:
                        pending_changes.add(file_path)
                except ValueError:
                    pass

        def process_changes():
            """Process pending changes after debounce period."""
            while True:
                time.sleep(debounce)

                with change_lock:
                    if not pending_changes:
                        continue

                    changes_to_process = pending_changes.copy()
                    pending_changes.clear()

                console.print(
                    f"📁 Processing {len(changes_to_process)} changed files..."
                )

                # Import here to avoid circular imports
                from .indexing import TextChunker

                text_chunker = TextChunker(config.indexing)

                modified_files = []
                deleted_files = []

                for file_path in changes_to_process:
                    if file_path.exists():
                        modified_files.append(file_path)
                    else:
                        # File was deleted
                        try:
                            relative_path = str(
                                file_path.relative_to(config.codebase_dir)
                            )
                            deleted_files.append(relative_path)
                        except ValueError:
                            continue

                # Process deletions
                if deleted_files:
                    for deleted_file in deleted_files:
                        qdrant_client.delete_by_filter(
                            {
                                "must": [
                                    {"key": "path", "match": {"value": deleted_file}}
                                ]
                            }
                        )

                # Process modifications
                if modified_files:
                    batch_points = []
                    total_chunks = 0

                    for file_path in modified_files:
                        try:
                            # Delete existing points for this file first
                            relative_path = str(
                                file_path.relative_to(config.codebase_dir)
                            )
                            qdrant_client.delete_by_filter(
                                {
                                    "must": [
                                        {
                                            "key": "path",
                                            "match": {"value": relative_path},
                                        }
                                    ]
                                }
                            )

                            # Read and chunk file
                            chunks = text_chunker.chunk_file(file_path)

                            if not chunks:
                                continue

                            # Process each chunk
                            for chunk in chunks:
                                # Get embedding
                                embedding = ollama_client.get_embedding(chunk["text"])

                                # Create point for Qdrant
                                point = qdrant_client.create_point(
                                    vector=embedding,
                                    payload={
                                        "path": relative_path,
                                        "content": chunk["text"],
                                        "language": chunk["file_extension"],
                                        "file_size": file_path.stat().st_size,
                                        "chunk_index": chunk["chunk_index"],
                                        "total_chunks": chunk["total_chunks"],
                                        "indexed_at": time.strftime(
                                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                                        ),
                                    },
                                )

                                batch_points.append(point)
                                total_chunks += 1

                                # Process batch when full
                                if len(batch_points) >= batch_size:
                                    qdrant_client.upsert_points(batch_points)
                                    batch_points = []

                        except Exception as e:
                            if ctx.obj["verbose"]:
                                console.print(
                                    f"❌ Failed to process {file_path}: {e}",
                                    style="red",
                                )

                    # Process remaining points
                    if batch_points:
                        qdrant_client.upsert_points(batch_points)

                if modified_files or deleted_files:
                    console.print(
                        f"✅ Updated index: {len(modified_files)} modified, {len(deleted_files)} deleted",
                        style="green",
                    )

        # Start the change processor thread
        processor_thread = threading.Thread(target=process_changes, daemon=True)
        processor_thread.start()

        # Setup file system watching
        event_handler = CodeChangeHandler()
        observer = Observer()
        observer.schedule(event_handler, str(config.codebase_dir), recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n👋 Stopping file watcher...")
            observer.stop()

        observer.join()

    except Exception as e:
        console.print(f"❌ Watch failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.argument("query")
@click.option("--limit", "-l", default=10, help="Number of results to return")
@click.option("--language", help="Filter by programming language")
@click.option("--path", help="Filter by file path pattern")
@click.option("--min-score", type=float, help="Minimum similarity score (0.0-1.0)")
@click.pass_context
def query(
    ctx,
    query: str,
    limit: int,
    language: Optional[str],
    path: Optional[str],
    min_score: Optional[float],
):
    """Search the indexed codebase."""
    config_manager = ctx.obj["config_manager"]

    try:
        config = config_manager.load()

        # Initialize services
        ollama_client = OllamaClient(config.ollama, console)
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health checks
        if not ollama_client.health_check():
            console.print("❌ Ollama service not available", style="red")
            sys.exit(1)

        if not qdrant_client.health_check():
            console.print("❌ Qdrant service not available", style="red")
            sys.exit(1)

        # Get query embedding
        with console.status("Generating query embedding..."):
            query_embedding = ollama_client.get_embedding(query)

        # Build filter conditions
        filter_conditions = {}
        if language:
            filter_conditions["must"] = [
                {"key": "language", "match": {"value": language}}
            ]
        if path:
            filter_conditions.setdefault("must", []).append(
                {"key": "path", "match": {"text": path}}
            )

        # Search
        console.print(f"🔍 Searching for: '{query}'")
        if language:
            console.print(f"🏷️  Language filter: {language}")
        if path:
            console.print(f"📁 Path filter: {path}")
        console.print(f"📊 Limit: {limit}")
        if min_score:
            console.print(f"⭐ Min score: {min_score}")

        results = qdrant_client.search(
            query_vector=query_embedding,
            limit=limit,
            score_threshold=min_score,
            filter_conditions=filter_conditions if filter_conditions else None,
        )

        if not results:
            console.print("❌ No results found", style="yellow")
            return

        console.print(f"\n✅ Found {len(results)} results:")
        console.print("=" * 80)

        for i, result in enumerate(results, 1):
            payload = result["payload"]
            score = result["score"]

            # File info
            file_path = payload.get("path", "unknown")
            language = payload.get("language", "unknown")
            file_size = payload.get("file_size", 0)
            indexed_at = payload.get("indexed_at", "unknown")

            # Create header
            header = f"📄 File: {file_path}"
            if language != "unknown":
                header += f" | 🏷️  Language: {language}"
            header += f" | 📊 Score: {score:.3f}"

            console.print(f"\n[bold cyan]{header}[/bold cyan]")
            console.print(f"📏 Size: {file_size} bytes | 🕒 Indexed: {indexed_at}")

            # Content preview
            content = payload.get("content", "")
            if content:
                console.print("\n📖 Content:")
                console.print("─" * 50)

                # Syntax highlighting if possible
                if language and language != "unknown":
                    try:
                        syntax = Syntax(
                            content[:500], language, theme="monokai", line_numbers=False
                        )
                        console.print(syntax)
                    except Exception:
                        console.print(content[:500])
                else:
                    console.print(content[:500])

                if len(content) > 500:
                    console.print("\n... [truncated]")

            console.print("─" * 50)

    except Exception as e:
        console.print(f"❌ Search failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx):
    """Show status of services and index."""
    config_manager = ctx.obj["config_manager"]

    try:
        config = config_manager.load()

        # Create status table
        table = Table(title="🔍 Code Indexer Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Details", style="green")

        # Check Docker services (auto-detect project name)
        docker_manager = DockerManager()
        service_status = docker_manager.get_service_status()

        docker_status = (
            "✅ Running" if service_status["status"] == "running" else "❌ Not Running"
        )
        table.add_row(
            "Docker Services",
            docker_status,
            f"{len(service_status['services'])} services",
        )

        # Check Ollama
        ollama_client = OllamaClient(config.ollama)
        ollama_ok = ollama_client.health_check()
        ollama_status = "✅ Ready" if ollama_ok else "❌ Not Available"
        ollama_details = (
            f"Model: {config.ollama.model}" if ollama_ok else "Service down"
        )
        table.add_row("Ollama", ollama_status, ollama_details)

        # Check Qdrant
        qdrant_client = QdrantClient(config.qdrant)
        qdrant_ok = qdrant_client.health_check()
        qdrant_status = "✅ Ready" if qdrant_ok else "❌ Not Available"
        qdrant_details = ""
        if qdrant_ok:
            try:
                count = qdrant_client.count_points()
                qdrant_details = f"Documents: {count}"
            except Exception:
                qdrant_details = "Collection ready"
        else:
            qdrant_details = "Service down"
        table.add_row("Qdrant", qdrant_status, qdrant_details)

        # Check index
        metadata_path = config_manager.config_path.parent / "metadata.json"
        if metadata_path.exists():
            try:
                import json

                with open(metadata_path) as f:
                    metadata = json.load(f)
                index_status = "✅ Available"
                index_details = f"Last indexed: {metadata.get('indexed_at', 'unknown')}"
            except Exception:
                index_status = "⚠️  Corrupted"
                index_details = "Metadata file corrupted"
        else:
            index_status = "❌ Not Found"
            index_details = "Run 'index' command"

        table.add_row("Index", index_status, index_details)

        # Configuration info
        table.add_row("Codebase", "📁", str(config.codebase_dir))
        table.add_row("Config", "⚙️", str(config_manager.config_path))

        console.print(table)

    except Exception as e:
        console.print(f"❌ Failed to get status: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option("--install", is_flag=True, help="Install Git hooks")
@click.option("--uninstall", is_flag=True, help="Remove Git hooks")
@click.pass_context
def git_hooks(ctx, install: bool, uninstall: bool):
    """Manage Git hooks for clean database commits."""
    if not install and not uninstall:
        console.print("❌ Use --install or --uninstall", style="red")
        sys.exit(1)

    if install and uninstall:
        console.print("❌ Cannot use both --install and --uninstall", style="red")
        sys.exit(1)

    git_dir = Path(".git")
    if not git_dir.exists():
        console.print("❌ Not a Git repository", style="red")
        sys.exit(1)

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    hooks = {
        "pre-commit": """#!/bin/bash
# Code Indexer: Ensure clean database state before commit
if [ -f ".code-indexer/config.json" ]; then
    echo "🔄 Flushing Qdrant database before commit..."
    code-indexer clean --quiet 2>/dev/null || true
    sleep 2  # Allow time for graceful shutdown
    echo "🚀 Restarting Qdrant after flush..."
    code-indexer setup --quiet 2>/dev/null || true
fi
""",
        "pre-checkout": """#!/bin/bash
# Code Indexer: Stop Qdrant before branch changes
if [ -f ".code-indexer/config.json" ]; then
    echo "🛑 Stopping Qdrant for branch change..."
    code-indexer clean --quiet 2>/dev/null || true
fi
""",
        "post-checkout": """#!/bin/bash
# Code Indexer: Restart Qdrant after branch changes
if [ -f ".code-indexer/config.json" ]; then
    echo "🚀 Restarting Qdrant after branch change..."
    code-indexer setup --quiet 2>/dev/null || true
fi
""",
    }

    if install:
        console.print("📎 Installing Git hooks for Code Indexer...")
        for hook_name, hook_content in hooks.items():
            hook_path = hooks_dir / hook_name

            # Backup existing hook if it exists
            if hook_path.exists():
                backup_path = hooks_dir / f"{hook_name}.backup"
                import shutil

                shutil.copy2(hook_path, backup_path)
                console.print(
                    f"📦 Backed up existing {hook_name} to {hook_name}.backup"
                )

            # Write new hook
            with open(hook_path, "w") as f:
                f.write(hook_content)
            hook_path.chmod(0o755)  # Make executable

            console.print(f"✅ Installed {hook_name} hook")

        console.print("🎉 Git hooks installed successfully!")
        console.print("🔄 Commits will now flush Qdrant database automatically")
        console.print("🔀 Branch changes will stop/start Qdrant as needed")

    elif uninstall:
        console.print("🗑️  Removing Code Indexer Git hooks...")
        for hook_name in hooks.keys():
            hook_path = hooks_dir / hook_name
            backup_path = hooks_dir / f"{hook_name}.backup"

            if hook_path.exists():
                # Check if this is our hook by looking for our signature
                with open(hook_path, "r") as f:
                    content = f.read()

                if "Code Indexer:" in content:
                    hook_path.unlink()
                    console.print(f"🗑️  Removed {hook_name} hook")

                    # Restore backup if it exists
                    if backup_path.exists():
                        import shutil

                        shutil.copy2(backup_path, hook_path)
                        backup_path.unlink()
                        console.print(f"📦 Restored {hook_name} from backup")
                else:
                    console.print(
                        f"⚠️  {hook_name} exists but not from Code Indexer, skipping"
                    )

        console.print("✅ Git hooks removed successfully!")


@cli.command()
@click.option(
    "--remove-data", "-d", is_flag=True, help="Remove all data and configuration"
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.pass_context
def clean(ctx, remove_data: bool, quiet: bool):
    """Stop services and optionally remove data."""
    try:
        # Use quiet console if requested
        clean_console = Console(quiet=quiet) if quiet else console
        docker_manager = DockerManager(clean_console)

        if remove_data:
            clean_console.print("🧹 Cleaning up services and removing all data...")
        else:
            clean_console.print("🛑 Stopping services...")

        if docker_manager.cleanup(remove_data=remove_data):
            if remove_data:
                # Remove config files
                config_manager = ctx.obj["config_manager"]
                if config_manager.config_path.exists():
                    config_manager.config_path.unlink()

                config_dir = config_manager.config_path.parent
                if config_dir.exists() and config_dir.name == ".code-indexer":
                    import shutil

                    shutil.rmtree(config_dir)

                console.print("✅ All data and configuration removed", style="green")
            else:
                console.print("✅ Services stopped", style="green")
        else:
            sys.exit(1)

    except Exception as e:
        console.print(f"❌ Cleanup failed: {e}", style="red")
        sys.exit(1)


def main():
    """Main entry point."""
    try:
        cli(obj={})
    except KeyboardInterrupt:
        console.print("\n❌ Interrupted by user", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Unexpected error: {e}", style="red")
        sys.exit(1)


if __name__ == "__main__":
    main()
