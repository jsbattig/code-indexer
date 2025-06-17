"""Command line interface for Code Indexer."""

import datetime
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Column
from rich.syntax import Syntax

from .config import ConfigManager, Config
from .services import OllamaClient, QdrantClient, DockerManager
from .services.git_aware_processor import GitAwareDocumentProcessor
from .services.generic_query_service import GenericQueryService
from . import __version__


# Global console for rich output
console = Console()


@click.group()
@click.option("--config", "-c", type=click.Path(exists=False), help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.version_option(version=__version__, prog_name="code-indexer")
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool):
    """🔍 AI-powered semantic code search with local models.

    \b
    GETTING STARTED:
      1. code-indexer init      # Initialize project
      2. code-indexer setup     # Start services (Ollama + Qdrant)
      3. code-indexer index     # Index your codebase
      4. code-indexer query "search term"  # Search your code

    \b
    CONFIGURATION:
      Config file: .code-indexer/config.json

      Key settings:
      • exclude_dirs: Folders to skip (e.g., ["node_modules", "dist"])
      • file_extensions: File types to index (e.g., ["py", "js", "ts"])
      • max_file_size: Maximum file size in bytes (default: 1MB)
      • chunk_size: Text chunk size for processing (default: 1000)

      Exclusions also respect .gitignore patterns automatically.

    \b
    DATA MANAGEMENT:
      • Git-aware: Tracks branches, commits, and file changes
      • Project isolation: Each project gets its own collection
      • Storage: Vector data stored in ~/.code-indexer/global/qdrant/
      • Cleanup: Use 'clean --remove-data' for current project only

    \b
    EXAMPLES:
      code-indexer init --max-file-size 2000000  # 2MB limit
      code-indexer index --clear                 # Fresh index
      code-indexer query "function authentication"
      code-indexer clean --remove-data --all-projects  # Remove all data

    For detailed help on any command, use: code-indexer COMMAND --help
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config_manager"] = ConfigManager(Path(config) if config else None)


@cli.command()
@click.option(
    "--codebase-dir",
    "-d",
    type=click.Path(exists=True),
    help="Directory to index (default: current directory)",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite existing configuration")
@click.option(
    "--max-file-size",
    type=int,
    help="Maximum file size to index (bytes, default: 1048576)",
)
@click.option(
    "--chunk-size", type=int, help="Text chunk size in characters (default: 1000)"
)
@click.pass_context
def init(
    ctx,
    codebase_dir: Optional[str],
    force: bool,
    max_file_size: Optional[int],
    chunk_size: Optional[int],
):
    """Initialize code indexing in current directory.

    \b
    Creates .code-indexer/config.json with project configuration.

    \b
    CONFIGURATION OPTIONS:
      • Exclude directories: Edit exclude_dirs in config.json
      • File types: Modify file_extensions array
      • Size limits: Use --max-file-size or edit config.json
      • Chunking: Use --chunk-size for text processing

    \b
    DEFAULT EXCLUSIONS:
      node_modules, venv, __pycache__, .git, dist, build, target,
      .idea, .vscode, .gradle, bin, obj, coverage, .next, .nuxt

    \b
    EXAMPLES:
      code-indexer init                          # Basic setup
      code-indexer init --max-file-size 2000000 # 2MB file limit
      code-indexer init --force                 # Overwrite existing config
      code-indexer init -d /path/to/project     # Index different directory

    After initialization, edit .code-indexer/config.json to customize:
    • exclude_dirs: ["node_modules", "dist", "my_temp_folder"]
    • file_extensions: ["py", "js", "ts", "java", "cpp"]
    """
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
        config = Config(codebase_dir=target_dir.resolve())
        config_manager._config = config

        # Update config with provided options
        if max_file_size is not None or chunk_size is not None:
            updates = {}
            if max_file_size is not None:
                updates["indexing"] = config.indexing.model_dump()
                updates["indexing"]["max_file_size"] = max_file_size
            if chunk_size is not None:
                if "indexing" not in updates:
                    updates["indexing"] = config.indexing.model_dump()
                updates["indexing"]["chunk_size"] = chunk_size
            config = config_manager.update_config(**updates)

        # Save with documentation
        config_manager.save_with_documentation(config)

        console.print(f"✅ Initialized configuration at {config_manager.config_path}")
        console.print(
            f"📖 Documentation created at {config_manager.config_path.parent / 'README.md'}"
        )
        console.print(f"📁 Codebase directory: {config.codebase_dir}")
        console.print(f"📏 Max file size: {config.indexing.max_file_size:,} bytes")
        console.print(f"📦 Chunk size: {config.indexing.chunk_size:,} characters")
        console.print("🔧 Run 'code-indexer setup' to start services")

    except Exception as e:
        console.print(f"❌ Failed to initialize: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option("--model", "-m", help="Ollama model to use (default: nomic-embed-text)")
@click.option("--force-recreate", "-f", is_flag=True, help="Force recreate containers")
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.pass_context
def setup(ctx, model: Optional[str], force_recreate: bool, quiet: bool):
    """Setup and start required services (Ollama + Qdrant).

    \b
    Starts Docker containers for AI-powered code search:
    • Ollama: Runs embedding models locally
    • Qdrant: Vector database for similarity search

    \b
    WHAT HAPPENS:
      1. Creates default configuration (.code-indexer/config.json + README.md)
      2. Creates Docker Compose configuration
      3. Pulls required container images
      4. Starts Ollama and Qdrant services
      5. Downloads embedding model (nomic-embed-text)
      6. Waits for services to be ready
      7. Creates vector database collection

    \b
    REQUIREMENTS:
      • Docker or Podman installed and running
      • Sufficient disk space (~4GB for models/images)
      • Network access to download images/models

    \b
    SERVICES:
      • Ollama: http://localhost:11434 (AI embeddings)
      • Qdrant: http://localhost:6333 (vector database)
      • Data: ~/.code-indexer/global/ (persistent storage)

    \b
    EXAMPLES:
      code-indexer setup                    # Basic setup
      code-indexer setup --quiet           # Silent mode
      code-indexer setup --force-recreate  # Reset containers
      code-indexer setup -m all-minilm-l6-v2  # Different model

    Run this command once per machine, services persist between sessions.
    """
    config_manager = ctx.obj["config_manager"]

    try:
        # Use quiet console if requested
        setup_console = Console(quiet=quiet) if quiet else console

        # Create default config if it doesn't exist
        if not config_manager.config_path.exists():
            setup_console.print("📝 Creating default configuration...")
            config = config_manager.create_default_config(Path.cwd().resolve())
            config_manager.save_with_documentation(config)
            setup_console.print(
                f"✅ Configuration created at {config_manager.config_path}"
            )
            setup_console.print(
                f"📖 Documentation created at {config_manager.config_path.parent / 'README.md'}"
            )
            setup_console.print(
                "💡 You can edit .code-indexer/config.json to customize exclusions before indexing"
            )
        else:
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
@click.option(
    "--clear", "-c", is_flag=True, help="Clear existing index before indexing"
)
@click.option(
    "--batch-size", "-b", default=50, help="Batch size for processing (default: 50)"
)
@click.pass_context
def index(ctx, clear: bool, batch_size: int):
    """Index the codebase for semantic search.

    \b
    Processes all files in your codebase and creates vector embeddings
    for semantic search. Uses git-aware processing to track changes.

    \b
    WHAT GETS INDEXED:
      • Files matching configured file_extensions
      • Excludes directories in exclude_dirs configuration
      • Respects .gitignore patterns automatically
      • Files under max_file_size limit

    \b
    GIT INTEGRATION:
      • Tracks current branch and commit
      • Associates code with git metadata
      • Enables branch-aware search
      • Detects file changes and modifications

    \b
    PROGRESS TRACKING:
      • Real-time progress bar with file names
      • Processing speed and time estimates
      • Error reporting for failed files

    \b
    EXAMPLES:
      code-indexer index                 # Index with existing data
      code-indexer index --clear         # Fresh start, clear old data
      code-indexer index -b 100          # Larger batch size for speed

    \b
    STORAGE:
      Vector data stored in: ~/.code-indexer/global/qdrant/
      Each project gets its own collection for isolation.
    """
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

        # Initialize git-aware document processor
        processor = GitAwareDocumentProcessor(config, ollama_client, qdrant_client)

        # Get git status and display
        git_status = processor.get_git_status()
        if git_status["git_available"]:
            console.print("📂 Git repository detected")
            console.print(f"🌿 Current branch: {git_status['current_branch']}")
            console.print(f"📦 Project ID: {git_status['project_id']}")
        else:
            console.print(f"📁 Non-git project: {git_status['project_id']}")

        # Index codebase using git-aware processor
        console.print("🔍 Indexing codebase with git-aware processing...")

        # Create progress tracking
        progress_bar = None
        task_id = None

        def progress_callback(current, total, file_path, error=None):
            nonlocal progress_bar, task_id

            # Initialize progress bar on first call
            if progress_bar is None:
                progress_bar = Progress(
                    TextColumn("[bold blue]Indexing", justify="right"),
                    BarColumn(bar_width=None),
                    "•",
                    TaskProgressColumn(),
                    "•",
                    TimeElapsedColumn(),
                    "•",
                    TimeRemainingColumn(),
                    "•",
                    TextColumn(
                        "[cyan]{task.description}",
                        table_column=Column(min_width=30, max_width=50, no_wrap=True),
                    ),
                    console=console,
                )
                progress_bar.start()
                task_id = progress_bar.add_task("Starting...", total=total)

            task = task_id

            # Update progress with current file name
            try:
                # Try to get path relative to project codebase directory
                config = ctx.obj["config_manager"].load()
                relative_path = str(file_path.relative_to(config.codebase_dir))
            except (Exception, ValueError):
                # Fallback to current directory relative path
                try:
                    relative_path = str(file_path.relative_to(Path.cwd()))
                except ValueError:
                    relative_path = file_path.name

            # Truncate long paths to fit display
            if len(relative_path) > 47:
                relative_path = "..." + relative_path[-44:]

            progress_bar.update(task, advance=1, description=relative_path)

            # Show errors
            if error:
                if ctx.obj["verbose"]:
                    progress_bar.console.print(
                        f"❌ Failed to process {file_path}: {error}", style="red"
                    )

        try:
            stats = processor.index_codebase(
                clear_existing=clear,
                batch_size=batch_size,
                progress_callback=progress_callback,
            )

            # Stop progress bar with completion message
            if progress_bar and task_id is not None:
                # Update final status
                progress_bar.update(task_id, description="✅ Completed")
                progress_bar.stop()
        except Exception as e:
            console.print(f"❌ Indexing failed: {e}", style="red")
            sys.exit(1)

        # Save indexing metadata with git-aware information
        index_metadata = {
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files_processed": stats.files_processed,
            "chunks_indexed": stats.chunks_created,
            "failed_files": stats.failed_files,
            "git_available": git_status["git_available"],
            "project_id": git_status["project_id"],
        }

        if git_status["git_available"]:
            index_metadata.update(
                {
                    "current_branch": git_status["current_branch"],
                    "current_commit": git_status["current_commit"],
                }
            )

        metadata_path = config_manager.config_path.parent / "metadata.json"
        with open(metadata_path, "w") as f:
            import json

            json.dump(index_metadata, f, indent=2)

        console.print("✅ Indexing complete!", style="green")
        console.print(f"📄 Files processed: {stats.files_processed}")
        console.print(f"📦 Chunks indexed: {stats.chunks_created}")
        console.print(f"⏱️  Duration: {stats.duration:.2f}s")

        if stats.failed_files > 0:
            console.print(f"⚠️  Failed files: {stats.failed_files}", style="yellow")

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

        # Initialize git-aware document processor
        processor = GitAwareDocumentProcessor(config, ollama_client, qdrant_client)

        # Get git status for context
        git_status = processor.get_git_status()
        if git_status["git_available"]:
            console.print(f"📂 Git repository: {git_status['project_id']}")
            console.print(f"🌿 Current branch: {git_status['current_branch']}")
        else:
            console.print(f"📁 Non-git project: {git_status['project_id']}")

        # Use smart update that handles git-aware incremental updates
        console.print("🔍 Checking for changes with git-aware detection...")

        # Create progress tracking for updates
        progress_bar = None
        task_id = None

        def progress_callback(current, total, file_path, error=None):
            nonlocal progress_bar, task_id

            # Initialize progress bar on first call (only if there are files to process)
            if progress_bar is None and total > 0:
                progress_bar = Progress(
                    TextColumn("[bold green]Updating", justify="right"),
                    BarColumn(bar_width=None),
                    "•",
                    TaskProgressColumn(),
                    "•",
                    TimeElapsedColumn(),
                    "•",
                    TimeRemainingColumn(),
                    "•",
                    TextColumn(
                        "[cyan]{task.description}",
                        table_column=Column(min_width=30, max_width=50, no_wrap=True),
                    ),
                    console=console,
                )
                progress_bar.start()
                task_id = progress_bar.add_task("Starting...", total=total)

            task = task_id

            # Update progress if we have a progress bar
            if progress_bar and task_id is not None:
                # Update with current file name
                try:
                    # Try to get path relative to project codebase directory
                    config = ctx.obj["config_manager"].load()
                    relative_path = str(file_path.relative_to(config.codebase_dir))
                except (Exception, ValueError):
                    # Fallback to current directory relative path
                    try:
                        relative_path = str(file_path.relative_to(Path.cwd()))
                    except ValueError:
                        relative_path = file_path.name

                # Truncate long paths to fit display
                if len(relative_path) > 47:
                    relative_path = "..." + relative_path[-44:]

                progress_bar.update(task, advance=1, description=relative_path)

            # Show errors
            if error and ctx.obj["verbose"]:
                if progress_bar:
                    progress_bar.console.print(
                        f"❌ Failed to process {file_path}: {error}", style="red"
                    )
                else:
                    console.print(
                        f"❌ Failed to process {file_path}: {error}", style="red"
                    )

        try:
            stats = processor.update_index_smart(
                batch_size=batch_size, progress_callback=progress_callback
            )

            # Stop progress bar with completion message
            if progress_bar and task_id is not None:
                # Update final status
                progress_bar.update(task_id, description="✅ Completed")
                progress_bar.stop()
        except Exception as e:
            console.print(f"❌ Update failed: {e}", style="red")
            sys.exit(1)

        if stats.files_processed == 0:
            console.print("✅ No changes since last index", style="green")
            return

        console.print(
            f"📄 Processing {stats.files_processed} updated files with git-aware metadata..."
        )

        # Update metadata with git-aware information
        import json

        update_metadata = {
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files_updated": stats.files_processed,
            "chunks_updated": stats.chunks_created,
            "failed_files": stats.failed_files,
            "git_available": git_status["git_available"],
            "project_id": git_status["project_id"],
        }

        if git_status["git_available"]:
            update_metadata.update(
                {
                    "current_branch": git_status["current_branch"],
                    "current_commit": git_status["current_commit"],
                }
            )

        metadata_path = config_manager.config_path.parent / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                existing_metadata = json.load(f)
            existing_metadata.update(update_metadata)
            update_metadata = existing_metadata

        with open(metadata_path, "w") as f:
            json.dump(update_metadata, f, indent=2)

        console.print("✅ Index update complete!", style="green")
        console.print(f"📄 Files updated: {stats.files_processed}")
        console.print(f"📦 Chunks updated: {stats.chunks_created}")
        console.print(f"⏱️  Duration: {stats.duration:.2f}s")

        if stats.failed_files > 0:
            console.print(f"⚠️  Failed files: {stats.failed_files}", style="yellow")

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

        # Perform initial update to catch up on any missed changes
        console.print("🔄 Performing initial update to catch up on changes...")

        # Initialize git-aware processor for smart updates
        processor = GitAwareDocumentProcessor(config, ollama_client, qdrant_client)

        # Set up progress tracking using Rich Progress (consistent with update/index commands)
        progress_bar = None
        task_id = None

        def progress_callback(
            current: int, total: int, filename: str, error: Optional[str] = None
        ):
            """Progress callback for initial update - consistent with update command"""
            nonlocal progress_bar, task_id

            # Initialize progress bar on first call
            if progress_bar is None and total > 0:
                progress_bar = Progress(
                    TextColumn("[bold green]Watch Update", justify="right"),
                    BarColumn(bar_width=None),
                    "•",
                    TaskProgressColumn(),
                    "•",
                    TimeElapsedColumn(),
                    "•",
                    TimeRemainingColumn(),
                    "•",
                    TextColumn("[cyan]{task.description}"),
                    console=console,
                )
                progress_bar.start()
                task_id = progress_bar.add_task("Starting...", total=total)

            if progress_bar and task_id is not None and total > 0:
                # Get relative path for display
                file_path = Path(filename)
                try:
                    relative_path = str(file_path.relative_to(config.codebase_dir))
                except (Exception, ValueError):
                    try:
                        relative_path = str(file_path.relative_to(Path.cwd()))
                    except ValueError:
                        relative_path = file_path.name

                # Truncate long paths to fit display
                if len(relative_path) > 47:
                    relative_path = "..." + relative_path[-44:]

                progress_bar.update(task_id, advance=1, description=relative_path)

            # Show errors
            if error and ctx.obj["verbose"]:
                if progress_bar:
                    progress_bar.console.print(
                        f"❌ Failed to process {filename}: {error}", style="red"
                    )
                else:
                    console.print(
                        f"❌ Failed to process {filename}: {error}", style="red"
                    )

        # Run smart update with progress tracking
        try:
            stats = processor.update_index_smart(
                batch_size=batch_size, progress_callback=progress_callback
            )

            # Stop progress bar with completion message
            if progress_bar and task_id is not None:
                progress_bar.update(task_id, description="✅ Completed")
                progress_bar.stop()

            if stats.files_processed > 0:
                console.print(
                    f"✅ Initial update complete: {stats.files_processed} files processed"
                )
            else:
                console.print("✅ Index is up to date - no changes detected")

        except Exception as e:
            if progress_bar:
                progress_bar.stop()
            console.print(f"⚠️  Initial update failed: {e}", style="yellow")
            console.print("Continuing with file watching...", style="yellow")

        console.print(f"\n👀 Now watching {config.codebase_dir} for changes...")
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

                # Start progress tracking for this batch using Rich Progress
                total_files = len(changes_to_process)
                console.print(f"\n📁 Processing {total_files} changed files...")

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

                # Create progress bar for batch processing
                total_operations = len(deleted_files) + len(modified_files)
                batch_progress = None
                batch_task_id = None

                if total_operations > 0:
                    batch_progress = Progress(
                        TextColumn("[bold orange1]Processing", justify="right"),
                        BarColumn(bar_width=None),
                        "•",
                        TaskProgressColumn(),
                        "•",
                        TimeElapsedColumn(),
                        "•",
                        TextColumn("[cyan]{task.description}"),
                        console=console,
                    )
                    batch_progress.start()
                    batch_task_id = batch_progress.add_task(
                        "Starting batch...", total=total_operations
                    )

                # Process deletions
                if deleted_files:
                    for deleted_file in deleted_files:
                        if batch_progress and batch_task_id is not None:
                            # Truncate path for display
                            display_path = deleted_file
                            if len(display_path) > 47:
                                display_path = "..." + display_path[-44:]
                            batch_progress.update(
                                batch_task_id,
                                advance=1,
                                description=f"🗑️ {display_path}",
                            )

                        qdrant_client.delete_by_filter(
                            {
                                "must": [
                                    {"key": "path", "match": {"value": deleted_file}}
                                ]
                            }
                        )

                # Process modifications with progress tracking
                if modified_files:
                    batch_points = []
                    total_chunks = 0

                    for file_path in modified_files:
                        try:
                            relative_path = str(
                                file_path.relative_to(config.codebase_dir)
                            )

                            # Update progress bar
                            if batch_progress and batch_task_id is not None:
                                display_path = relative_path
                                if len(display_path) > 47:
                                    display_path = "..." + display_path[-44:]
                                batch_progress.update(
                                    batch_task_id,
                                    advance=1,
                                    description=f"📝 {display_path}",
                                )

                            # Delete existing points for this file first
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
                                    f"\n❌ Failed to process {file_path}: {e}",
                                    style="red",
                                )

                    # Process remaining points
                    if batch_points:
                        qdrant_client.upsert_points(batch_points)

                # Stop progress bar and show completion
                if batch_progress and batch_task_id is not None:
                    batch_progress.update(
                        batch_task_id, description="✅ Batch completed"
                    )
                    batch_progress.stop()

                # Final status update
                if modified_files or deleted_files:
                    console.print(
                        f"✅ Batch complete: {len(modified_files)} modified, {len(deleted_files)} deleted",
                        style="green",
                    )
                    console.print("👀 Watching for new changes...", style="dim")

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
@click.option(
    "--limit", "-l", default=10, help="Number of results to return (default: 10)"
)
@click.option(
    "--language", help="Filter by programming language (e.g., python, javascript)"
)
@click.option("--path", help="Filter by file path pattern (e.g., */tests/*)")
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
    """Search the indexed codebase using semantic similarity.

    \b
    Performs AI-powered semantic search across your indexed code.
    Uses vector embeddings to find conceptually similar code.

    \b
    SEARCH CAPABILITIES:
      • Semantic search: Finds conceptually similar code
      • Natural language: Describe what you're looking for
      • Code patterns: Search for specific implementations
      • Git-aware: Searches within current project/branch context

    \b
    FILTERING OPTIONS:
      • Language: --language python (searches only Python files)
      • Path: --path */tests/* (searches only test directories)
      • Score: --min-score 0.8 (only high-confidence matches)
      • Limit: --limit 20 (more results)

    \b
    QUERY EXAMPLES:
      "authentication function"           # Find auth-related code
      "database connection setup"        # Find DB setup code
      "error handling try catch"         # Find error handling patterns
      "REST API endpoint POST"           # Find POST API endpoints
      "unit test mock"                   # Find mocking in tests

    \b
    EXAMPLES:
      code-indexer query "user login"
      code-indexer query "database" --language python
      code-indexer query "test" --path */tests/* --limit 5
      code-indexer query "async" --min-score 0.8

    Results show file paths, matched content, and similarity scores.
    """
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

        # Initialize git-aware query service
        query_service = GenericQueryService(config.codebase_dir, config)

        # Get current branch context for git-aware filtering
        branch_context = query_service.get_current_branch_context()
        if branch_context["git_available"]:
            console.print(f"📂 Git repository: {branch_context['project_id']}")
            console.print(f"🌿 Current branch: {branch_context['current_branch']}")
        else:
            console.print(f"📁 Non-git project: {branch_context['project_id']}")

        # Search
        console.print(f"🔍 Searching for: '{query}'")
        if language:
            console.print(f"🏷️  Language filter: {language}")
        if path:
            console.print(f"📁 Path filter: {path}")
        console.print(f"📊 Limit: {limit}")
        if min_score:
            console.print(f"⭐ Min score: {min_score}")

        raw_results = qdrant_client.search(
            query_vector=query_embedding,
            limit=limit * 2,  # Get more results to allow for git filtering
            score_threshold=min_score,
            filter_conditions=filter_conditions if filter_conditions else None,
        )

        # Apply git-aware filtering
        console.print("🔍 Applying git-aware filtering...")
        results = query_service.filter_results_by_current_branch(raw_results)

        # Limit to requested number after filtering
        results = results[:limit]

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

            # Git-aware metadata
            git_available = payload.get("git_available", False)
            project_id = payload.get("project_id", "unknown")

            # Create header with git info
            header = f"📄 File: {file_path}"
            if language != "unknown":
                header += f" | 🏷️  Language: {language}"
            header += f" | 📊 Score: {score:.3f}"

            console.print(f"\n[bold cyan]{header}[/bold cyan]")

            # Enhanced metadata display
            metadata_info = f"📏 Size: {file_size} bytes | 🕒 Indexed: {indexed_at}"

            if git_available:
                git_branch = payload.get("git_branch", "unknown")
                git_commit = payload.get("git_commit_hash", "unknown")
                if git_commit != "unknown" and len(git_commit) > 8:
                    git_commit = git_commit[:8] + "..."
                metadata_info += f" | 🌿 Branch: {git_branch}"
                if git_commit != "unknown":
                    metadata_info += f" | 📦 Commit: {git_commit}"

            metadata_info += f" | 🏗️  Project: {project_id}"
            console.print(metadata_info)

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
    """Show status of services and index.

    \b
    Displays comprehensive information about your code-indexer setup:

    \b
    SERVICE STATUS:
      • Ollama: AI embedding service status
      • Qdrant: Vector database status
      • Docker containers: Running/stopped state

    \b
    INDEX INFORMATION:
      • Project configuration details
      • Git repository information (if applicable)
      • Vector collection statistics
      • Storage usage and optimization status
      • Number of indexed files and chunks

    \b
    CONFIGURATION SUMMARY:
      • File extensions being indexed
      • Excluded directories
      • File size and chunk limits
      • Model and collection settings

    \b
    EXAMPLE OUTPUT:
      ✅ Services: Ollama (ready), Qdrant (ready)
      📂 Project: my-app (Git: feature-branch)
      📊 Index: 1,234 files, 5,678 chunks
      💾 Storage: 45.2MB, optimized

    Use this command to verify your setup and troubleshoot issues.
    """
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

        # Check index with git-aware information
        metadata_path = config_manager.config_path.parent / "metadata.json"
        if metadata_path.exists():
            try:
                import json

                with open(metadata_path) as f:
                    metadata = json.load(f)
                index_status = "✅ Available"

                # Build enhanced details with git info
                last_indexed = metadata.get("indexed_at", "unknown")
                git_available = metadata.get("git_available", False)
                project_id = metadata.get("project_id", "unknown")

                index_details = f"Last indexed: {last_indexed}"
                if git_available:
                    current_branch = metadata.get("current_branch", "unknown")
                    index_details += f" | Branch: {current_branch}"
                index_details += f" | Project: {project_id}"

            except Exception:
                index_status = "⚠️  Corrupted"
                index_details = "Metadata file corrupted"
        else:
            index_status = "❌ Not Found"
            index_details = "Run 'index' command"

        table.add_row("Index", index_status, index_details)

        # Add git repository status if available
        try:
            from .services.git_aware_processor import GitAwareDocumentProcessor

            processor = GitAwareDocumentProcessor(
                config, OllamaClient(config.ollama), QdrantClient(config.qdrant)
            )
            git_status = processor.get_git_status()

            if git_status["git_available"]:
                git_info = f"Branch: {git_status['current_branch']}"
                commit_hash = git_status.get("current_commit", "unknown")
                if commit_hash != "unknown" and len(commit_hash) > 8:
                    commit_hash = commit_hash[:8] + "..."
                git_info += f" | Commit: {commit_hash}"

                table.add_row("Git Repository", "✅ Available", git_info)
            else:
                table.add_row("Git Repository", "❌ Not Found", "Non-git project")
        except Exception:
            table.add_row("Git Repository", "⚠️  Error", "Could not check git status")

        # Storage information
        if qdrant_ok:
            try:
                size_info = qdrant_client.get_collection_size()
                if "error" not in size_info:
                    storage_details = f"Size: ~{size_info['estimated_vector_size_mb']}MB | Points: {size_info['points_count']:,}"
                    table.add_row("Storage", "📊", storage_details)
            except Exception:
                pass

        # Configuration info
        table.add_row("Codebase", "📁", str(config.codebase_dir))
        table.add_row("Config", "⚙️", str(config_manager.config_path))
        table.add_row(
            "File Limits",
            "📏",
            f"Max size: {config.indexing.max_file_size:,} bytes | Chunk: {config.indexing.chunk_size:,} chars",
        )

        console.print(table)

    except Exception as e:
        console.print(f"❌ Failed to get status: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.pass_context
def optimize(ctx):
    """Optimize vector database storage and performance."""
    config_manager = ctx.obj["config_manager"]

    try:
        config = config_manager.load()

        # Initialize Qdrant client
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health check
        if not qdrant_client.health_check():
            console.print("❌ Qdrant service not available", style="red")
            sys.exit(1)

        console.print("🔧 Optimizing vector database...")

        # Get current size information
        size_info = qdrant_client.get_collection_size()
        if "error" not in size_info:
            console.print(
                f"📊 Current size: ~{size_info['estimated_vector_size_mb']}MB"
            )
            console.print(f"📦 Points: {size_info['points_count']:,}")

        # Optimize collection
        if qdrant_client.optimize_collection():
            console.print("✅ Database optimization completed!", style="green")

            # Show new size information
            new_size_info = qdrant_client.get_collection_size()
            if "error" not in new_size_info:
                console.print(
                    f"📊 Optimized size: ~{new_size_info['estimated_vector_size_mb']}MB"
                )
        else:
            console.print(
                "⚠️  Optimization may not have completed successfully", style="yellow"
            )

    except Exception as e:
        console.print(f"❌ Optimization failed: {e}", style="red")
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
    "--remove-data",
    "-d",
    is_flag=True,
    help="Remove current project's data and configuration",
)
@click.option(
    "--all-projects",
    is_flag=True,
    help="Remove data for ALL projects (use with --remove-data)",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.pass_context
def clean(ctx, remove_data: bool, all_projects: bool, quiet: bool):
    """Stop services and optionally remove data.

    By default, --remove-data only removes the current project's data.
    Use --all-projects with --remove-data to remove data for all projects.
    """
    try:
        # Use quiet console if requested
        clean_console = Console(quiet=quiet) if quiet else console

        # Validate options
        if all_projects and not remove_data:
            clean_console.print(
                "❌ --all-projects can only be used with --remove-data", style="red"
            )
            sys.exit(1)

        docker_manager = DockerManager(clean_console)

        if remove_data:
            if all_projects:
                clean_console.print(
                    "🧹 Cleaning up services and removing ALL project data..."
                )
            else:
                clean_console.print(
                    "🧹 Cleaning up services and removing current project data..."
                )
        else:
            clean_console.print("🛑 Stopping services...")

        if docker_manager.cleanup(remove_data=remove_data and all_projects):
            if remove_data:
                config_manager = ctx.obj["config_manager"]

                if all_projects:
                    # Remove all project data (old behavior)
                    if config_manager.config_path.exists():
                        config_manager.config_path.unlink()

                    config_dir = config_manager.config_path.parent
                    if config_dir.exists() and config_dir.name == ".code-indexer":
                        import shutil

                        shutil.rmtree(config_dir)

                    clean_console.print(
                        "✅ All project data and configuration removed", style="green"
                    )
                else:
                    # Remove only current project data (new default behavior)
                    try:
                        # Load config to get project info
                        config = config_manager.load()

                        # Initialize services to clear project-specific data
                        qdrant_client = QdrantClient(config.qdrant, clean_console)

                        # Clear the current project's collection from Qdrant
                        if (
                            qdrant_client.health_check()
                            and qdrant_client.collection_exists()
                        ):
                            clean_console.print(
                                f"🗑️  Clearing collection: {config.qdrant.collection}"
                            )
                            qdrant_client.clear_collection()

                        # Remove local project config
                        if config_manager.config_path.exists():
                            config_manager.config_path.unlink()

                        config_dir = config_manager.config_path.parent
                        if config_dir.exists() and config_dir.name == ".code-indexer":
                            import shutil

                            shutil.rmtree(config_dir)

                        clean_console.print(
                            "✅ Current project data and configuration removed",
                            style="green",
                        )

                    except Exception as e:
                        # If we can't load config, fall back to basic cleanup
                        clean_console.print(
                            f"⚠️  Could not clear project collection: {e}",
                            style="yellow",
                        )

                        # Still remove local config files
                        if config_manager.config_path.exists():
                            config_manager.config_path.unlink()

                        config_dir = config_manager.config_path.parent
                        if config_dir.exists() and config_dir.name == ".code-indexer":
                            import shutil

                            shutil.rmtree(config_dir)

                        clean_console.print(
                            "✅ Local configuration removed", style="green"
                        )
            else:
                clean_console.print("✅ Services stopped", style="green")
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
