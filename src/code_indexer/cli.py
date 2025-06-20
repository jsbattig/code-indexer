"""Command line interface for Code Indexer."""

import os
import sys
import signal
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
from rich.syntax import Syntax
from rich.table import Column
from rich.markdown import Markdown

from .config import ConfigManager, Config
from .services import QdrantClient, DockerManager, EmbeddingProviderFactory
from .services.git_aware_processor import GitAwareDocumentProcessor
from .services.smart_indexer import SmartIndexer
from .services.generic_query_service import GenericQueryService
from .services.claude_integration import (
    ClaudeIntegrationService,
    check_claude_sdk_availability,
)
from . import __version__


def _format_claude_response(response: str) -> str:
    """Format Claude response for better terminal display."""
    if not response:
        return response

    # Check if response contains Claude structured objects (list format)
    if response.startswith("[") and "TextBlock" in response:
        # Parse the structured response from Claude
        formatted_text = _parse_claude_sdk_response(response)
        if formatted_text:
            response = formatted_text

    # Ensure proper line breaks are preserved
    formatted = response.replace("\r\n", "\n").replace("\r", "\n")

    # Handle multiple consecutive newlines (preserve paragraph breaks)
    lines = formatted.split("\n")
    formatted_lines = []

    for line in lines:
        # Strip only trailing whitespace, preserve indentation
        formatted_lines.append(line.rstrip())

    # Join with newlines and ensure we don't have excessive empty lines at start/end
    result = "\n".join(formatted_lines).strip()

    # Ensure the response ends with a newline for better formatting
    if result and not result.endswith("\n"):
        result += "\n"

    return result


def _parse_claude_sdk_response(response: str) -> str:
    """Parse Claude structured response to extract text content."""
    try:
        import re

        # Extract TextBlock content
        text_blocks = []

        # Find all TextBlock(text='...') patterns
        text_pattern = r"TextBlock\(text='(.*?)'\)"
        matches = re.findall(text_pattern, response, re.DOTALL)

        for match in matches:
            # Unescape the text content
            text = match.replace("\\'", "'").replace("\\n", "\n").replace("\\\\", "\\")
            text_blocks.append(text)

        # Join all text blocks
        if text_blocks:
            return "\n\n".join(text_blocks)

        # Fallback: try to extract any text content between quotes
        fallback_pattern = r"'([^']*(?:\\'[^']*)*)'"
        fallback_matches = re.findall(fallback_pattern, response)

        # Find the longest match (likely the main content)
        if fallback_matches:
            longest_match = max(fallback_matches, key=len)
            if len(longest_match) > 100:  # Only use if it seems substantial
                return str(
                    longest_match.replace("\\'", "'")
                    .replace("\\n", "\n")
                    .replace("\\\\", "\\")
                )

        return response  # Return original if parsing fails

    except Exception as e:
        console = Console()
        console.print(f"Warning: Failed to parse Claude response: {e}", style="yellow")
        return response  # Return original if parsing fails


def _is_markdown_content(text: str) -> bool:
    """Detect if text content is likely markdown."""
    if not text or len(text.strip()) < 10:
        return False

    # Check for common markdown patterns
    markdown_indicators = [
        "# ",  # Headers
        "## ",  # Headers
        "### ",  # Headers
        "**",  # Bold
        "*",  # Italic/Bold
        "`",  # Code
        "```",  # Code blocks
        "- ",  # Lists
        "* ",  # Lists
        "1. ",  # Numbered lists
        "[",  # Links
        "> ",  # Blockquotes
    ]

    # Count markdown indicators
    indicator_count = sum(1 for indicator in markdown_indicators if indicator in text)

    # If we have multiple markdown patterns or it looks structured, treat as markdown
    return indicator_count >= 2 or "```" in text or text.count("#") >= 2


class GracefulInterruptHandler:
    """Handler for graceful interruption of long-running operations."""

    def __init__(self, console: Console, operation_name: str = "Operation"):
        self.console = console
        self.operation_name = operation_name
        self.interrupted = False
        self.original_sigint_handler = None
        self.progress_bar = None

    def __enter__(self):
        self.original_sigint_handler = signal.signal(
            signal.SIGINT, self._signal_handler
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original signal handler
        signal.signal(signal.SIGINT, self.original_sigint_handler)

        # If we were interrupted, show final message
        if self.interrupted:
            if self.progress_bar:
                self.progress_bar.stop()
            self.console.print()  # New line
            self.console.print(
                f"🛑 {self.operation_name} interrupted by user", style="yellow"
            )
            self.console.print(
                "📊 Progress has been saved and can be resumed later", style="cyan"
            )
            return True  # Suppress the KeyboardInterrupt exception

    def _signal_handler(self, signum, frame):
        """Handle SIGINT (Ctrl-C) gracefully."""
        self.interrupted = True
        if self.progress_bar:
            self.progress_bar.stop()
        self.console.print()  # New line
        self.console.print(
            f"🛑 Interrupting {self.operation_name.lower()}...", style="yellow"
        )
        self.console.print(
            "⏳ Finishing current file and saving progress...", style="cyan"
        )

    def set_progress_bar(self, progress_bar):
        """Set the progress bar to stop when interrupted."""
        self.progress_bar = progress_bar


# Global console for rich output
console = Console()


@click.group()
@click.option("--config", "-c", type=click.Path(exists=False), help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True),
    help="Start directory for config discovery (walks up to find .code-indexer/)",
)
@click.version_option(version=__version__, prog_name="code-indexer")
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool, path: Optional[str]):
    """AI-powered semantic code search with local models.

    \b
    TIP: Use 'cidx' as a short alias for 'code-indexer' (e.g., 'cidx start')

    \b
    GETTING STARTED:
      1. code-indexer start     # Start services (creates default config if needed)
      2. code-indexer index     # Smart incremental indexing
      3. code-indexer query "search term"  # Search your code

      OR for custom configuration (init is optional):
      1. code-indexer init      # OPTIONAL: Initialize with custom settings
      2. code-indexer start     # Start services (Ollama + Qdrant)
      3. code-indexer index     # Smart incremental indexing
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

      # Using --path to work with different project locations:
      code-indexer --path /home/user/myproject index
      code-indexer --path ../other-project query "search term"
      code-indexer -p ./nested/folder status

    For detailed help on any command, use: code-indexer COMMAND --help
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # Use path for config discovery, leveraging existing backtracking logic
    if path:
        start_dir = Path(path).resolve()
        ctx.obj["config_manager"] = ConfigManager.create_with_backtrack(start_dir)
    elif config:
        ctx.obj["config_manager"] = ConfigManager(Path(config))
    else:
        # Always use backtracking by default to find config in parent directories
        ctx.obj["config_manager"] = ConfigManager.create_with_backtrack()


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
@click.option(
    "--embedding-provider",
    type=click.Choice(["ollama", "voyage-ai"]),
    default="ollama",
    help="Embedding provider to use (default: ollama)",
)
@click.option(
    "--voyage-model",
    type=str,
    default="voyage-code-3",
    help="VoyageAI model name (default: voyage-code-3)",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive configuration prompt",
)
@click.pass_context
def init(
    ctx,
    codebase_dir: Optional[str],
    force: bool,
    max_file_size: Optional[int],
    chunk_size: Optional[int],
    embedding_provider: str,
    voyage_model: str,
    interactive: bool,
):
    """Initialize code indexing in current directory (OPTIONAL).

    \b
    Creates .code-indexer/config.json with project configuration.

    \b
    NOTE: This command is optional. If you skip init and run 'start' directly,
    a default configuration will be created automatically with Ollama provider
    and standard settings. Only use init if you want to customize settings.

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
    EMBEDDING PROVIDERS:
      • ollama: Local AI models (default, no API key required)
      • voyage-ai: VoyageAI API (requires VOYAGE_API_KEY environment variable)

    \b
    EXAMPLES:
      code-indexer init                                    # Basic initialization with Ollama
      code-indexer init --interactive                     # Interactive configuration
      code-indexer init --embedding-provider voyage-ai    # Use VoyageAI
      code-indexer init --voyage-model voyage-large-2     # Specify VoyageAI model
      code-indexer init --max-file-size 2000000          # 2MB file limit
      code-indexer init --force                          # Overwrite existing config

    \b
    VOYAGEAI SETUP:
      To use VoyageAI, set your API key first:
      export VOYAGE_API_KEY=your_api_key_here

      Then persist it (add to ~/.bashrc, ~/.zshrc, or ~/.profile):
      echo 'export VOYAGE_API_KEY=your_api_key_here' >> ~/.bashrc

    After initialization, edit .code-indexer/config.json to customize:
    • embedding_provider: "ollama" or "voyage-ai"
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
        # Interactive configuration if requested
        if interactive:
            console.print("🔧 Interactive configuration setup")
            console.print("=" * 50)

            # Provider selection
            from .services.embedding_factory import EmbeddingProviderFactory

            provider_info = EmbeddingProviderFactory.get_provider_info()

            console.print("\n📡 Available embedding providers:")
            for provider, info in provider_info.items():
                console.print(f"  • {provider}: {info['description']}")
                if info.get("requires_api_key"):
                    console.print(
                        f"    Requires API key: {info.get('api_key_env', 'N/A')}"
                    )

            # Prompt for provider selection
            if click.confirm(
                "\nUse VoyageAI instead of local Ollama? (requires VOYAGE_API_KEY)",
                default=False,
            ):
                embedding_provider = "voyage-ai"
                if not os.getenv("VOYAGE_API_KEY"):
                    console.print(
                        "⚠️  Warning: VOYAGE_API_KEY environment variable not set!",
                        style="yellow",
                    )
                    console.print("You'll need to set it before using VoyageAI:")
                    console.print("export VOYAGE_API_KEY=your_api_key_here")

                # Prompt for VoyageAI model
                voyage_model = click.prompt("VoyageAI model", default="voyage-code-3")
            else:
                embedding_provider = "ollama"

        # Create default config
        target_dir = Path(codebase_dir) if codebase_dir else Path.cwd()
        config = Config(codebase_dir=target_dir.resolve())
        config_manager._config = config

        # Update config with provided options
        updates = {}

        # Set embedding provider
        updates["embedding_provider"] = embedding_provider

        # Provider-specific configuration
        if embedding_provider == "voyage-ai":
            voyage_ai_config = config.voyage_ai.model_dump()
            voyage_ai_config["model"] = voyage_model
            voyage_ai_config["tokens_per_minute"] = (
                1000000  # Set default to avoid rate limiting
            )
            updates["voyage_ai"] = voyage_ai_config

            # Set correct vector size for VoyageAI (1024 dimensions)
            qdrant_config = config.qdrant.model_dump()
            qdrant_config["vector_size"] = 1024
            updates["qdrant"] = qdrant_config
        elif embedding_provider == "ollama":
            # Set correct vector size for Ollama (768 dimensions)
            qdrant_config = config.qdrant.model_dump()
            qdrant_config["vector_size"] = 768
            updates["qdrant"] = qdrant_config

        # Indexing configuration updates
        if max_file_size is not None or chunk_size is not None:
            indexing_config = config.indexing.model_dump()
            if max_file_size is not None:
                indexing_config["max_file_size"] = max_file_size
            if chunk_size is not None:
                indexing_config["chunk_size"] = chunk_size
            updates["indexing"] = indexing_config

        # Apply updates if any
        if updates:
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

        # Show configured embedding provider
        provider_name = config.embedding_provider
        if provider_name == "voyage-ai":
            console.print(
                f"🤖 Embedding provider: VoyageAI (model: {config.voyage_ai.model})"
            )
            if not os.getenv("VOYAGE_API_KEY"):
                console.print(
                    "⚠️  Remember to set VOYAGE_API_KEY environment variable!",
                    style="yellow",
                )
        else:
            console.print(
                f"🤖 Embedding provider: Ollama (model: {config.ollama.model})"
            )

        console.print("🔧 Run 'code-indexer start' to start services")

    except Exception as e:
        console.print(f"❌ Failed to initialize: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option("--model", "-m", help="Ollama model to use (default: nomic-embed-text)")
@click.option("--force-recreate", "-f", is_flag=True, help="Force recreate containers")
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.option(
    "--parallel-requests",
    type=int,
    default=1,
    help="Number of concurrent requests Ollama server accepts (default: 1)",
)
@click.option(
    "--max-models",
    type=int,
    default=1,
    help="Maximum models to keep loaded in memory (default: 1)",
)
@click.option(
    "--queue-size",
    type=int,
    default=512,
    help="Maximum request queue size (default: 512)",
)
@click.pass_context
def start(
    ctx,
    model: Optional[str],
    force_recreate: bool,
    force_docker: bool,
    quiet: bool,
    parallel_requests: int,
    max_models: int,
    queue_size: int,
):
    """Intelligently start required services, performing setup if needed.

    \b
    SMART BEHAVIOR - automatically handles different scenarios:
    • If containers don't exist: performs full setup + start
    • If containers exist but stopped: starts existing containers
    • If containers already running: verifies health and reports status

    \b
    SERVICES (started based on embedding provider):
    • Qdrant: Vector database (always required)
    • Ollama: Local embedding models (only if using ollama provider)
    • Data Cleaner: Text processing service (always required)

    \b
    WHAT HAPPENS (when full setup is needed):
      1. Creates default configuration (.code-indexer/config.json + README.md)
      2. Detects required services based on embedding provider
      3. Creates Docker Compose configuration for only required services
      4. Pulls required container images (idempotent)
      5. Starts only required services (Qdrant always, Ollama only if needed)
      6. Downloads embedding model (only for Ollama provider)
      7. Waits for services to be ready
      8. Creates vector database collection

    \b
    REQUIREMENTS:
      • Docker or Podman installed and running
      • Sufficient disk space (~4GB for models/images)
      • Network access to download images/models

    \b
    SERVICE ENDPOINTS (provider-dependent):
      • Qdrant: http://localhost:6333 (vector database, always started)
      • Ollama: http://localhost:11434 (local AI embeddings, only if provider=ollama)
      • Data Cleaner: Text processing service (always started)
      • Data: ~/.code-indexer/global/ (persistent storage)

    \b
    PERFORMANCE OPTIONS (Ollama Environment Variables):
      --parallel-requests N   Number of concurrent requests Ollama server accepts (default: 1)
                             Maps to OLLAMA_NUM_PARALLEL (Ollama default: 4 or 1 based on memory)
      --max-models N         Maximum models kept in memory (default: 1)
                             Maps to OLLAMA_MAX_LOADED_MODELS (Ollama default: 3×GPU count or 3 for CPU)
      --queue-size N         Maximum request queue size (default: 512)
                             Maps to OLLAMA_MAX_QUEUE (Ollama default: 512)

    Reference: https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server

    \b
    EXAMPLES:
      code-indexer start                     # Smart start (detects what's needed)
      code-indexer start --quiet            # Silent mode
      code-indexer start --force-recreate   # Force recreate containers
      code-indexer start --force-docker     # Force use Docker instead of Podman
      code-indexer start -m all-minilm-l6-v2  # Different Ollama model
      code-indexer start --parallel-requests 2 --max-models 1  # Multi-client Ollama setup
      code-indexer start --queue-size 1024  # Larger Ollama request queue

    \b
    The command is fully idempotent - running it multiple times is safe and will only
    start missing services or perform setup if needed.
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

        # Provider-specific configuration and validation
        if config.embedding_provider == "ollama":
            # Update model if specified (only valid for Ollama)
            if model:
                config.ollama.model = model

            # Update performance settings from command line parameters
            config.ollama.num_parallel = parallel_requests
            config.ollama.max_loaded_models = max_models
            config.ollama.max_queue = queue_size

            setup_console.print(
                f"🤖 Ollama provider selected with model: {config.ollama.model}"
            )

        elif config.embedding_provider == "voyage-ai":
            # Validate API key for VoyageAI
            import os

            if not os.getenv("VOYAGE_API_KEY"):
                setup_console.print(
                    "❌ VoyageAI provider requires VOYAGE_API_KEY environment variable",
                    style="red",
                )
                setup_console.print(
                    "💡 Get your API key at: https://www.voyageai.com/", style="yellow"
                )
                sys.exit(1)

            # Model parameter not applicable for VoyageAI
            if model:
                setup_console.print(
                    "⚠️ --model parameter is ignored for VoyageAI provider",
                    style="yellow",
                )

            # Performance parameters not applicable for cloud providers
            if parallel_requests != 1 or max_models != 1 or queue_size != 512:
                setup_console.print(
                    "⚠️ Performance parameters (--parallel-requests, --max-models, --queue-size) are ignored for cloud providers",
                    style="yellow",
                )

            setup_console.print(
                f"🌐 VoyageAI provider selected with model: {config.voyage_ai.model}"
            )

        else:
            setup_console.print(
                f"❌ Unsupported embedding provider: {config.embedding_provider}",
                style="red",
            )
            sys.exit(1)

        # Save updated configuration
        config_manager.save(config)

        # Check Docker availability (auto-detect project name)
        docker_manager = DockerManager(
            setup_console, force_docker=force_docker, main_config=config.model_dump()
        )

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

        # Check current service states for intelligent startup
        required_services = docker_manager.get_required_services(config.model_dump())
        setup_console.print(
            f"🔍 Checking required services: {', '.join(required_services)}"
        )

        # Get current service states
        all_healthy = True
        for service in required_services:
            state = docker_manager.get_service_state(service)
            if not (state["running"] and state["healthy"]):
                all_healthy = False
                break

        if all_healthy and not force_recreate:
            setup_console.print(
                "✅ All required services are already running and healthy"
            )
        else:
            # Start only required services
            if not docker_manager.start_services(recreate=force_recreate):
                sys.exit(1)

            # Wait for services to be ready (only required ones)
            if not docker_manager.wait_for_services():
                setup_console.print("❌ Services failed to start properly", style="red")
                sys.exit(1)

        # Test connections and setup based on provider
        with setup_console.status("Testing service connections..."):
            embedding_provider = EmbeddingProviderFactory.create(config, setup_console)
            qdrant_client = QdrantClient(config.qdrant, setup_console)

            # Test embedding provider (only if required)
            if config.embedding_provider == "ollama":
                if not embedding_provider.health_check():
                    setup_console.print(
                        f"❌ {embedding_provider.get_provider_name().title()} service is not accessible",
                        style="red",
                    )
                    sys.exit(1)
            elif config.embedding_provider == "voyage-ai":
                # For cloud providers, test connectivity without starting Docker services
                try:
                    if not embedding_provider.health_check():
                        setup_console.print(
                            f"❌ {embedding_provider.get_provider_name().title()} API is not accessible. Check your API key.",
                            style="red",
                        )
                        sys.exit(1)
                except Exception as e:
                    setup_console.print(
                        f"❌ Failed to connect to {embedding_provider.get_provider_name().title()}: {e}",
                        style="red",
                    )
                    sys.exit(1)

            # Always test Qdrant (required for all providers)
            if not qdrant_client.health_check():
                setup_console.print("❌ Qdrant service is not accessible", style="red")
                sys.exit(1)

        # Provider-specific model setup
        if config.embedding_provider == "ollama":
            setup_console.print(f"🤖 Checking Ollama model: {config.ollama.model}")
            if hasattr(embedding_provider, "model_exists") and hasattr(
                embedding_provider, "pull_model"
            ):
                if not embedding_provider.model_exists(config.ollama.model):
                    if not embedding_provider.pull_model(config.ollama.model):
                        setup_console.print(
                            f"❌ Failed to pull model {config.ollama.model}",
                            style="red",
                        )
                        sys.exit(1)
        elif config.embedding_provider == "voyage-ai":
            setup_console.print(
                f"🤖 Using {embedding_provider.get_provider_name()} with model: {embedding_provider.get_current_model()}"
            )
            setup_console.print(
                "💡 No local model download required for cloud provider"
            )
        else:
            setup_console.print(
                f"🤖 Using {embedding_provider.get_provider_name()} provider with model: {embedding_provider.get_current_model()}"
            )

        # Ensure collection exists
        if not qdrant_client.ensure_collection():
            setup_console.print("❌ Failed to create Qdrant collection", style="red")
            sys.exit(1)

        setup_console.print("✅ Services started successfully!", style="green")
        setup_console.print(f"🔧 Ready to index codebase at: {config.codebase_dir}")

    except Exception as e:
        setup_console.print(f"❌ Start failed: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option(
    "--clear", "-c", is_flag=True, help="Clear existing index and perform full reindex"
)
@click.option(
    "--reconcile",
    "-r",
    is_flag=True,
    help="Reconcile disk files with database and index missing files + timestamp-based changes",
)
@click.option(
    "--batch-size", "-b", default=50, help="Batch size for processing (default: 50)"
)
@click.option(
    "--files-count-to-process",
    type=int,
    default=None,
    hidden=True,
    help="Internal: Stop after processing N files (for testing)",
)
@click.pass_context
def index(
    ctx,
    clear: bool,
    reconcile: bool,
    batch_size: int,
    files_count_to_process: Optional[int],
):
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
    SMART INDEXING:
      • Automatically detects previous indexing state
      • Performs incremental updates for modified files only
      • Includes 1-minute safety buffer for reliability
      • Handles provider/model changes intelligently

    \b
    RECONCILIATION:
      • Automatically saves progress during indexing
      • Can resume interrupted operations from where they left off
      • Use --reconcile to compare disk files with database and index missing/modified files
      • For non-git projects: compares file modification timestamps
      • For git projects: primarily detects missing files and uses indexing timestamps as fallback
      • Shows remaining files count in status command

    \b
    EXAMPLES:
      code-indexer index                 # Smart incremental indexing (default)
      code-indexer index --clear         # Force full reindex (clears existing data)
      code-indexer index --reconcile     # Reconcile disk vs database and index missing/modified files
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
        embedding_provider = EmbeddingProviderFactory.create(config, console)
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health checks
        if not embedding_provider.health_check():
            console.print(
                f"❌ {embedding_provider.get_provider_name().title()} service not available. Run 'start' first.",
                style="red",
            )
            sys.exit(1)

        if not qdrant_client.health_check():
            console.print(
                "❌ Qdrant service not available. Run 'start' first.", style="red"
            )
            sys.exit(1)

        # Initialize smart indexer with progressive metadata
        metadata_path = config_manager.config_path.parent / "metadata.json"
        smart_indexer = SmartIndexer(
            config, embedding_provider, qdrant_client, metadata_path
        )

        # Get git status and display
        git_status = smart_indexer.get_git_status()
        if git_status["git_available"]:
            console.print("📂 Git repository detected")
            console.print(f"🌿 Current branch: {git_status['current_branch']}")
            console.print(f"📦 Project ID: {git_status['project_id']}")
        else:
            console.print(f"📁 Non-git project: {git_status['project_id']}")

        # Show indexing strategy
        if clear:
            console.print("🧹 Force full reindex requested")
        elif reconcile:
            console.print("🔄 Reconciling disk files with database index...")
        else:
            indexing_status = smart_indexer.get_indexing_status()
            if indexing_status["can_resume"]:
                console.print("🔄 Resuming incremental indexing...")
                console.print(
                    f"📊 Previous progress: {indexing_status['files_processed']} files, {indexing_status['chunks_indexed']} chunks"
                )
            else:
                console.print("🆕 No previous index found, performing full index")

        # Create progress tracking with graceful interrupt handling
        progress_bar = None
        task_id = None
        interrupt_handler = None

        def progress_callback(current, total, file_path, error=None, info=None):
            nonlocal progress_bar, task_id, interrupt_handler

            # Check if we've been interrupted and signal to stop processing
            if interrupt_handler and interrupt_handler.interrupted:
                # Signal to the smart indexer that we should stop
                return "INTERRUPT"

            # Handle info messages (like strategy selection)
            if info and not progress_bar:
                console.print(f"ℹ️  {info}", style="cyan")
                return

            # Handle info-only updates (for status messages during processing)
            if file_path == Path("") and info and progress_bar:
                progress_bar.update(task_id, description=f"ℹ️  {info}")
                return

            # Initialize progress bar on first call
            if progress_bar is None:
                progress_bar = Progress(
                    TextColumn("[bold blue]Indexing", justify="right"),
                    BarColumn(bar_width=30),
                    TaskProgressColumn(),
                    "•",
                    TimeElapsedColumn(),
                    "•",
                    TimeRemainingColumn(),
                    "•",
                    TextColumn(
                        "[cyan]{task.description}",
                        table_column=Column(no_wrap=False, overflow="fold"),
                    ),
                    console=console,
                )
                progress_bar.start()
                task_id = progress_bar.add_task("Starting...", total=total)

                # Register progress bar with interrupt handler
                if interrupt_handler:
                    interrupt_handler.set_progress_bar(progress_bar)

            task = task_id

            # Update progress with current file name
            try:
                # Try to get path relative to project codebase directory
                relative_path = str(file_path.relative_to(config.codebase_dir))
            except (Exception, ValueError):
                # Fallback to current directory relative path
                try:
                    relative_path = str(file_path.relative_to(Path.cwd()))
                except ValueError:
                    relative_path = file_path.name

            # Create description with file and throughput info
            # Use two lines: file path on top, metrics below
            if info:
                description = f"{relative_path}\n{info}"
            else:
                description = relative_path

            progress_bar.update(task, advance=1, description=description)

            # Show errors
            if error:
                if ctx.obj["verbose"]:
                    progress_bar.console.print(
                        f"❌ Failed to process {file_path}: {error}", style="red"
                    )

        # Check for conflicting flags
        if clear and reconcile:
            console.print("❌ Cannot use --clear and --reconcile together", style="red")
            sys.exit(1)

        # Use graceful interrupt handling for the indexing operation
        operation_name = "Indexing"
        if reconcile:
            operation_name = "Reconciliation"
        elif clear:
            operation_name = "Full reindexing"

        try:
            with GracefulInterruptHandler(console, operation_name) as handler:
                interrupt_handler = handler

                stats = smart_indexer.smart_index(
                    force_full=clear,
                    reconcile_with_database=reconcile,
                    batch_size=batch_size,
                    progress_callback=progress_callback,
                    safety_buffer_seconds=60,  # 1-minute safety buffer
                    files_count_to_process=files_count_to_process,
                )

                # Stop progress bar with completion message (if not interrupted)
                if progress_bar and task_id is not None and not handler.interrupted:
                    # Update final status
                    progress_bar.update(task_id, description="✅ Completed")
                    progress_bar.stop()

        except Exception as e:
            console.print(f"❌ Indexing failed: {e}", style="red")
            sys.exit(1)

        # Show completion summary with throughput
        console.print("✅ Indexing complete!", style="green")
        console.print(f"📄 Files processed: {stats.files_processed}")
        console.print(f"📦 Chunks indexed: {stats.chunks_created}")
        console.print(f"⏱️  Duration: {stats.duration:.2f}s")

        # Calculate final throughput
        if stats.duration > 0:
            files_per_min = (stats.files_processed / stats.duration) * 60
            chunks_per_min = (stats.chunks_created / stats.duration) * 60
            console.print(
                f"🚀 Throughput: {files_per_min:.1f} files/min, {chunks_per_min:.1f} chunks/min"
            )

        if stats.failed_files > 0:
            console.print(f"⚠️  Failed files: {stats.failed_files}", style="yellow")

        # Show final indexing status
        final_status = smart_indexer.get_indexing_status()
        if final_status["status"] == "completed":
            console.print(
                "💾 Progress saved for future incremental updates", style="dim"
            )

    except Exception as e:
        console.print(f"❌ Indexing failed: {e}", style="red")
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
        embedding_provider = EmbeddingProviderFactory.create(config, console)
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health checks
        if not embedding_provider.health_check():
            console.print(
                f"❌ {embedding_provider.get_provider_name().title()} service not available",
                style="red",
            )
            sys.exit(1)

        if not qdrant_client.health_check():
            console.print("❌ Qdrant service not available", style="red")
            sys.exit(1)

        # Initialize git-aware processor for smart updates
        _ = GitAwareDocumentProcessor(config, embedding_provider, qdrant_client)

        # Perform smart update (will be fast if nothing to do)
        metadata_path = config_manager.config_path.parent / "metadata.json"
        smart_indexer = SmartIndexer(
            config, embedding_provider, qdrant_client, metadata_path
        )

        console.print("🔄 Checking for changes before starting file watcher...")

        # Run smart indexing to catch up on any changes
        try:
            stats = smart_indexer.smart_index(batch_size=batch_size)

            if stats.files_processed > 0:
                console.print(
                    f"✅ Updated {stats.files_processed} files before watching"
                )
            else:
                console.print("✅ Index is up to date")

        except Exception as e:
            console.print(f"⚠️  Initial update failed: {e}", style="yellow")
            console.print("Continuing with file watching...", style="yellow")

        # Initialize progress bar variables for later use
        progress_bar = None
        task_id = None

        def progress_callback(
            current: int, total: int, filename: str, error: Optional[str] = None
        ):
            """Progress callback for watch updates"""
            nonlocal progress_bar, task_id

            # Initialize progress bar on first call
            if progress_bar is None and total > 0:
                progress_bar = Progress(
                    TextColumn("[bold green]Watch Update", justify="right"),
                    BarColumn(bar_width=30),
                    TaskProgressColumn(),
                    "•",
                    TimeElapsedColumn(),
                    "•",
                    TimeRemainingColumn(),
                    "•",
                    TextColumn(
                        "[cyan]{task.description}",
                        table_column=Column(no_wrap=False, overflow="fold"),
                    ),
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

                # No truncation - allow full path display
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
                        BarColumn(bar_width=30),
                        TaskProgressColumn(),
                        "•",
                        TimeElapsedColumn(),
                        "•",
                        TextColumn(
                            "[cyan]{task.description}",
                            table_column=Column(no_wrap=False, overflow="fold"),
                        ),
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
                            # No truncation - allow full path display
                            batch_progress.update(
                                batch_task_id,
                                advance=1,
                                description=f"🗑️ {deleted_file}",
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
                                # No truncation - allow full path display
                                batch_progress.update(
                                    batch_task_id,
                                    advance=1,
                                    description=f"📝 {relative_path}",
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
                                embedding = embedding_provider.get_embedding(
                                    chunk["text"]
                                )

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
            with GracefulInterruptHandler(console, "File watching") as handler:
                console.print(
                    "👀 Watching for file changes... (Press Ctrl-C to stop)",
                    style="dim",
                )
                while not handler.interrupted:
                    time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n👋 Stopping file watcher...")
        finally:
            observer.stop()
            observer.join()

    except Exception as e:
        console.print(f"❌ Watch failed: {e}", style="red")
        import traceback

        console.print(traceback.format_exc())
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
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Quiet mode - only show results, no headers or metadata",
)
@click.pass_context
def query(
    ctx,
    query: str,
    limit: int,
    language: Optional[str],
    path: Optional[str],
    min_score: Optional[float],
    quiet: bool,
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
      code-indexer query "function" --quiet  # Just score, path, and content

    Results show file paths, matched content, and similarity scores.
    """
    config_manager = ctx.obj["config_manager"]

    try:
        config = config_manager.load()

        # Initialize services
        embedding_provider = EmbeddingProviderFactory.create(config, console)
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health checks
        if not embedding_provider.health_check():
            console.print(
                f"❌ {embedding_provider.get_provider_name().title()} service not available",
                style="red",
            )
            sys.exit(1)

        if not qdrant_client.health_check():
            console.print("❌ Qdrant service not available", style="red")
            sys.exit(1)

        # Ensure provider-aware collection is set for search
        collection_name = qdrant_client.resolve_collection_name(
            config, embedding_provider
        )
        qdrant_client._current_collection_name = collection_name

        # Get query embedding
        if not quiet:
            with console.status("Generating query embedding..."):
                query_embedding = embedding_provider.get_embedding(query)
        else:
            query_embedding = embedding_provider.get_embedding(query)

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

        # Apply embedding provider's model filtering when searching
        provider_info = embedding_provider.get_model_info()
        if not quiet:
            console.print(
                f"🤖 Using {embedding_provider.get_provider_name()} with model: {provider_info.get('name', 'unknown')}"
            )

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
        else:
            # Get current branch context for git-aware filtering
            branch_context = query_service.get_current_branch_context()

        # Get current embedding model for filtering
        current_model = embedding_provider.get_current_model()
        if not quiet:
            console.print(f"🤖 Filtering by model: {current_model}")

        # Use model-specific search to ensure we only get results from the current model
        raw_results = qdrant_client.search_with_model_filter(
            query_vector=query_embedding,
            embedding_model=current_model,
            limit=limit * 2,  # Get more results to allow for git filtering
            score_threshold=min_score,
            additional_filters=filter_conditions,
        )

        # Apply git-aware filtering
        if not quiet:
            console.print("🔍 Applying git-aware filtering...")
        results = query_service.filter_results_by_current_branch(raw_results)

        # Limit to requested number after filtering
        results = results[:limit]

        if not results:
            if not quiet:
                console.print("❌ No results found", style="yellow")
            return

        if not quiet:
            console.print(f"\n✅ Found {len(results)} results:")
            console.print("=" * 80)

        for i, result in enumerate(results, 1):
            payload = result["payload"]
            score = result["score"]

            # File info
            file_path = payload.get("path", "unknown")
            language = payload.get("language", "unknown")
            content = payload.get("content", "")

            if quiet:
                # Quiet mode - minimal output: score, path, content
                console.print(f"{score:.3f} {file_path}")
                if content:
                    # Show content without syntax highlighting in quiet mode
                    console.print(content[:500])
                    if len(content) > 500:
                        console.print("... [truncated]")
                console.print()  # Empty line between results
            else:
                # Normal verbose mode
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
                if content:
                    console.print("\n📖 Content:")
                    console.print("─" * 50)

                    # Syntax highlighting if possible
                    if language and language != "unknown":
                        try:
                            syntax = Syntax(
                                content[:500],
                                language,
                                theme="monokai",
                                line_numbers=False,
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
@click.argument("question")
@click.option(
    "--limit",
    "-l",
    default=10,
    help="Number of semantic search results to include (default: 10)",
)
@click.option(
    "--context-lines",
    "-c",
    default=500,
    help="Lines of context around each match (default: 500)",
)
@click.option(
    "--language", help="Filter by programming language (e.g., python, javascript)"
)
@click.option("--path", help="Filter by file path pattern (e.g., */tests/*)")
@click.option("--min-score", type=float, help="Minimum similarity score (0.0-1.0)")
@click.option(
    "--max-turns", default=5, help="Maximum Claude conversation turns (default: 5)"
)
@click.option(
    "--no-explore", is_flag=True, help="Disable file exploration hints in Claude prompt"
)
@click.option(
    "--no-stream", is_flag=True, help="Disable streaming (show results all at once)"
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Quiet mode - only show results, no headers or metadata",
)
@click.option(
    "--dry-run-show-claude-prompt",
    is_flag=True,
    help="Show the prompt that would be sent to Claude instead of executing the query",
)
@click.pass_context
def claude(
    ctx,
    question: str,
    limit: int,
    context_lines: int,
    language: Optional[str],
    path: Optional[str],
    min_score: Optional[float],
    max_turns: int,
    no_explore: bool,
    no_stream: bool,
    quiet: bool,
    dry_run_show_claude_prompt: bool,
):
    """AI-powered code analysis using Claude with semantic search.

    \b
    Combines semantic search with Claude AI to provide intelligent analysis
    of your codebase. Performs RAG (Retrieval-Augmented Generation) by:

    1. Running semantic search to find relevant code
    2. Extracting context around matches
    3. Sending context + question to Claude for analysis

    \b
    CAPABILITIES:
      • Natural language code questions and explanations
      • Architecture analysis and recommendations
      • Code pattern identification and best practices
      • Debugging assistance and error analysis
      • Implementation guidance and examples
      • Cross-file relationship analysis

    \b
    SEARCH INTEGRATION:
      Uses your existing semantic search index to find relevant code context.
      Claude can also perform additional searches during analysis to explore
      related concepts and provide comprehensive answers.

    \b
    FILTERING OPTIONS:
      Same as regular search - filter by language, path, and similarity score
      to focus Claude's analysis on specific parts of your codebase.

    \b
    EXAMPLES:
      code-indexer claude "How does authentication work in this app?"
      code-indexer claude "Show me the database schema design" --language sql
      code-indexer claude "Find security vulnerabilities" --min-score 0.8
      code-indexer claude "Explain the API routing logic" --path */api/*
      code-indexer claude "How to add a new feature?" --context-lines 300
      code-indexer claude "Debug this error pattern" --no-stream
      code-indexer claude "Quick analysis" --quiet  # Just the response, no headers
      code-indexer claude "Test prompt" --dry-run-show-claude-prompt  # Show prompt without executing

    \b
    STREAMING:
      Use --stream to see Claude's analysis as it's generated, helpful for
      longer analyses or when you want immediate feedback.

    \b
    PROMPT DEBUGGING:
      Use --dry-run-show-claude-prompt to see the exact prompt that would be
      sent to Claude without actually executing the query. This is helpful for:
      • Iterating on prompt improvements
      • Understanding what context is being provided
      • Debugging issues with prompt generation
      • Optimizing context size and relevance

    \b
    REQUIREMENTS:
      • Claude CLI must be installed: https://docs.anthropic.com/en/docs/claude-code
      • Services must be running: code-indexer start
      • Codebase must be indexed: code-indexer index

    Results include Claude's analysis plus metadata about contexts used.
    """
    config_manager = ctx.obj["config_manager"]

    try:
        # Check Claude CLI availability
        if (
            not check_claude_sdk_availability()
        ):  # This function now checks CLI availability
            console.print(
                "❌ Claude CLI not available. Install it following:", style="red"
            )
            console.print("   https://docs.anthropic.com/en/docs/claude-code")
            sys.exit(1)

        config = config_manager.load()

        # Initialize services
        embedding_provider = EmbeddingProviderFactory.create(config, console)
        qdrant_client = QdrantClient(config.qdrant, console)

        # Health checks
        if not embedding_provider.health_check():
            console.print(
                f"❌ {embedding_provider.get_provider_name().title()} service not available. Run 'start' first.",
                style="red",
            )
            sys.exit(1)

        if not qdrant_client.health_check():
            console.print(
                "❌ Qdrant service not available. Run 'start' first.", style="red"
            )
            sys.exit(1)

        # Ensure provider-aware collection is set for search
        collection_name = qdrant_client.resolve_collection_name(
            config, embedding_provider
        )
        qdrant_client._current_collection_name = collection_name

        # Initialize query service for git-aware filtering
        query_service = GenericQueryService(config.codebase_dir, config)

        # Get project context
        branch_context = query_service.get_current_branch_context()
        if not quiet:
            if branch_context["git_available"]:
                console.print(f"📂 Git repository: {branch_context['project_id']}")
                console.print(f"🌿 Current branch: {branch_context['current_branch']}")
            else:
                console.print(f"📁 Non-git project: {branch_context['project_id']}")

            # Perform semantic search
            console.print(f"🔍 Performing semantic search: '{question}'")
            console.print(f"📊 Limit: {limit} | Context: {context_lines} lines")

        if not quiet:
            with console.status("Generating query embedding..."):
                query_embedding = embedding_provider.get_embedding(question)
        else:
            query_embedding = embedding_provider.get_embedding(question)

        # Build filter conditions
        filter_conditions = {}
        if language:
            filter_conditions["must"] = [
                {"key": "language", "match": {"value": language}}
            ]
            console.print(f"🏷️  Language filter: {language}")
        if path:
            filter_conditions.setdefault("must", []).append(
                {"key": "path", "match": {"text": path}}
            )
            console.print(f"📁 Path filter: {path}")
        if min_score:
            console.print(f"⭐ Min score: {min_score}")

        # Get current embedding model for filtering
        current_model = embedding_provider.get_current_model()
        if not quiet:
            console.print(f"🤖 Using model: {current_model}")

        # Perform search with model filtering
        raw_results = qdrant_client.search_with_model_filter(
            query_vector=query_embedding,
            embedding_model=current_model,
            limit=limit * 2,  # Get more results to allow for git filtering
            score_threshold=min_score,
            additional_filters=filter_conditions,
        )

        # Apply git-aware filtering
        if not quiet:
            with console.status("Applying git-aware filtering..."):
                results = query_service.filter_results_by_current_branch(raw_results)
        else:
            results = query_service.filter_results_by_current_branch(raw_results)

        # Limit to requested number after filtering
        results = results[:limit]

        if not results:
            if not quiet:
                console.print("❌ No semantic search results found", style="yellow")
                console.print("💡 Try a broader search query or adjust filters")
            sys.exit(1)

        if not quiet:
            console.print(f"✅ Found {len(results)} relevant code contexts")

        # Initialize Claude integration
        claude_service = ClaudeIntegrationService(
            codebase_dir=config.codebase_dir, project_name=branch_context["project_id"]
        )

        # Handle dry-run mode - show prompt instead of executing
        if dry_run_show_claude_prompt:
            if not quiet:
                console.print("🔍 Dry Run Mode: Generating Claude prompt...")
                console.print("=" * 80)

            # Extract contexts from search results (same as would be done in analysis)
            contexts = claude_service.context_extractor.extract_context_from_results(
                results,
                context_lines=context_lines,
                ensure_all_files=True,
            )

            # Create the analysis prompt (same as would be sent to Claude)
            prompt = claude_service.create_analysis_prompt(
                user_query=question,
                contexts=contexts,
                project_info=branch_context,
                enable_exploration=not no_explore,
            )

            # Add the cidx tool capability enhancement (same as in actual analysis)
            prompt += """

ADDITIONAL SEMANTIC SEARCH CAPABILITY:
This codebase includes a built-in semantic search tool accessible via Bash:
- `cidx query "search terms"` - Find semantically similar code
- `cidx query "search terms" --limit 5` - Limit results  
- `cidx query "search terms" --language python` - Filter by language
- `cidx --help` - See all available commands

Use this when you need to find related code that might not be in the initial context."""

            if not quiet:
                console.print("\n📋 Claude Prompt Preview:")
                console.print("=" * 80)
                console.print(f"📊 Prompt length: {len(prompt):,} characters")
                console.print(f"📄 Contexts used: {len(contexts)}")
                console.print(
                    f"📏 Total context lines: {sum(ctx.line_end - ctx.line_start + 1 for ctx in contexts):,}"
                )
                console.print("=" * 80)
                console.print()

            # Display the actual prompt that would be sent to Claude
            # Use syntax highlighting to make it more readable
            from rich.syntax import Syntax

            try:
                syntax = Syntax(
                    prompt,
                    "markdown",
                    theme="monokai",
                    line_numbers=True,
                    word_wrap=True,
                )
                console.print(syntax)
            except Exception:
                # Fallback to plain text if syntax highlighting fails
                console.print(prompt)

            if not quiet:
                console.print()
                console.print("=" * 80)
                console.print(
                    "🎯 This is the exact prompt that would be sent to Claude Code CLI"
                )
                console.print(
                    "💡 Use this to iterate on prompt improvements before actual execution"
                )

            return  # Exit early without running Claude analysis

        # Stream by default, unless --no-stream is specified
        use_streaming = not no_stream

        if use_streaming:
            # Use streaming mode - no status spinner needed
            analysis_result = claude_service.run_analysis(
                user_query=question,
                search_results=results,
                context_lines=context_lines,
                max_turns=max_turns,
                project_info=branch_context,
                enable_exploration=not no_explore,
                stream=True,
                quiet=quiet,
            )
        else:
            # Non-streaming mode with status spinner
            if not quiet:
                with console.status("🤖 Analyzing with Claude AI..."):
                    analysis_result = claude_service.run_analysis(
                        user_query=question,
                        search_results=results,
                        context_lines=context_lines,
                        max_turns=max_turns,
                        project_info=branch_context,
                        enable_exploration=not no_explore,
                        stream=False,
                        quiet=quiet,
                    )
            else:
                analysis_result = claude_service.run_analysis(
                    user_query=question,
                    search_results=results,
                    context_lines=context_lines,
                    max_turns=max_turns,
                    project_info=branch_context,
                    enable_exploration=not no_explore,
                    stream=False,
                    quiet=quiet,
                )

        # Handle results (common for both streaming and non-streaming)
        if not analysis_result.success:
            if not quiet:
                console.print(
                    f"❌ Claude analysis failed: {analysis_result.error}", style="red"
                )
            sys.exit(1)

        # For non-streaming mode, show formatted results
        if not use_streaming:
            if quiet:
                # Quiet mode - just show the response content
                formatted_response = _format_claude_response(analysis_result.response)
                console.print(formatted_response)
            else:
                # Display results with proper formatting
                console.print("\n🤖 Claude Analysis Results")
                console.print("─" * 80)
                console.print()

                # Format the response for better readability
                formatted_response = _format_claude_response(analysis_result.response)

                # Render as markdown for beautiful formatting
                if _is_markdown_content(formatted_response):
                    markdown = Markdown(formatted_response)
                    console.print(markdown)
                else:
                    console.print(formatted_response)

                console.print()
                console.print("─" * 80)

        # Show metadata (for both modes)
        if not quiet:
            console.print("\n📊 Analysis Summary:")
            console.print(f"   • Code contexts used: {analysis_result.contexts_used}")
            console.print(
                f"   • Total context lines: {analysis_result.total_context_lines:,}"
            )

            if analysis_result.contexts_used > 0:
                avg_lines = (
                    analysis_result.total_context_lines // analysis_result.contexts_used
                )
                console.print(f"   • Average lines per context: {avg_lines}")

        # Clear cache to free memory
        claude_service.clear_cache()

    except Exception as e:
        console.print(f"❌ Claude analysis failed: {e}", style="red")
        if ctx.obj["verbose"]:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.pass_context
def status(ctx, force_docker: bool):
    """Show status of services and index.

    \b
    Displays comprehensive information about your code-indexer installation:

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

    Use this command to verify your installation and troubleshoot issues.
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
        docker_manager = DockerManager(
            force_docker=force_docker, main_config=config.model_dump()
        )
        service_status = docker_manager.get_service_status()

        docker_status = (
            "✅ Running" if service_status["status"] == "running" else "❌ Not Running"
        )
        table.add_row(
            "Docker Services",
            docker_status,
            f"{len(service_status['services'])} services",
        )

        # Check embedding provider
        try:
            embedding_provider = EmbeddingProviderFactory.create(config, console)
            provider_ok = embedding_provider.health_check()
            provider_name = embedding_provider.get_provider_name().title()
            provider_status = "✅ Ready" if provider_ok else "❌ Not Available"
            provider_details = (
                f"Model: {embedding_provider.get_current_model()}"
                if provider_ok
                else "Service down"
            )
            table.add_row(
                f"{provider_name} Provider", provider_status, provider_details
            )
        except Exception as e:
            table.add_row("Embedding Provider", "❌ Error", str(e))

        # Check Qdrant
        qdrant_client = QdrantClient(config.qdrant)
        qdrant_ok = qdrant_client.health_check()
        qdrant_status = "✅ Ready" if qdrant_ok else "❌ Not Available"
        qdrant_details = ""
        if qdrant_ok:
            try:
                # Get the correct collection name using the current embedding provider
                embedding_provider = EmbeddingProviderFactory.create(config, console)
                collection_name = qdrant_client.resolve_collection_name(
                    config, embedding_provider
                )
                count = qdrant_client.count_points(collection_name)
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

                # Build enhanced details with git info and resume capability
                last_indexed = metadata.get("indexed_at", "unknown")
                git_available = metadata.get("git_available", False)
                project_id = metadata.get("project_id", "unknown")

                # Check resume capability
                can_resume_interrupted = (
                    metadata.get("status") == "in_progress"
                    and len(metadata.get("files_to_index", [])) > 0
                    and metadata.get("current_file_index", 0)
                    < len(metadata.get("files_to_index", []))
                )

                index_details = f"Last indexed: {last_indexed}"
                if git_available:
                    current_branch = metadata.get("current_branch", "unknown")
                    index_details += f" | Branch: {current_branch}"
                index_details += f" | Project: {project_id}"

                if can_resume_interrupted:
                    remaining = len(metadata.get("files_to_index", [])) - metadata.get(
                        "current_file_index", 0
                    )
                    index_details += f" | ⏸️ Resumable ({remaining} files remaining)"

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
                config,
                EmbeddingProviderFactory.create(config, console),
                QdrantClient(config.qdrant),
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
                # Use the correct collection name for storage info too
                embedding_provider = EmbeddingProviderFactory.create(config, console)
                collection_name = qdrant_client.resolve_collection_name(
                    config, embedding_provider
                )
                size_info = qdrant_client.get_collection_size(collection_name)
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
@click.option("--verbose", "-v", is_flag=True, help="Verbose output for debugging")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force cleanup even if containers are unresponsive",
)
@click.option("--validate", is_flag=True, help="Validate cleanup worked properly")
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.pass_context
def clean(
    ctx,
    remove_data: bool,
    all_projects: bool,
    quiet: bool,
    verbose: bool,
    force: bool,
    validate: bool,
    force_docker: bool,
):
    """Stop services and optionally remove data.

    \b
    BASIC USAGE:
      code-indexer clean                        # Stop services
      code-indexer clean --remove-data          # Stop and remove current project data
      code-indexer clean --remove-data --all-projects  # Remove all project data

    \b
    ENHANCED CLEANUP:
      code-indexer clean --force                # Force stop unresponsive containers
      code-indexer clean --validate             # Validate cleanup worked
      code-indexer clean --verbose              # Show detailed cleanup steps
      code-indexer clean --remove-data --force --validate  # Robust cleanup

    \b
    TROUBLESHOOTING:
      If containers are stuck or won't stop properly, use --force
      If cleanup seems incomplete, use --validate to check
      For debugging cleanup issues, use --verbose

    By default, --remove-data only removes the current project's data.
    Use --all-projects with --remove-data to remove data for all projects.
    """
    try:
        # Handle verbose vs quiet conflict
        if verbose and quiet:
            console.print("❌ Cannot use both --verbose and --quiet", style="red")
            sys.exit(1)

        # Use appropriate console
        if verbose:
            clean_console = console  # Always show verbose output
        elif quiet:
            clean_console = Console(quiet=True)
        else:
            clean_console = console

        # Validate options
        if all_projects and not remove_data:
            clean_console.print(
                "❌ --all-projects can only be used with --remove-data", style="red"
            )
            sys.exit(1)

        # Load config to get port configuration
        config_manager = ctx.obj["config_manager"]
        try:
            config = config_manager.load()
            main_config = config.model_dump()
        except Exception:
            main_config = None

        docker_manager = DockerManager(
            clean_console, force_docker=force_docker, main_config=main_config
        )

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

        if docker_manager.cleanup(
            remove_data=remove_data and all_projects,
            force=force,
            verbose=verbose,
            validate=validate,
        ):
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


@cli.command()
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.pass_context
def stop(ctx, force_docker: bool):
    """Stop code indexing services while preserving all data.

    \b
    Gracefully stops Docker containers for Ollama and Qdrant services
    without removing any data or configuration. Can be run from any
    subfolder of an indexed project.

    \b
    WHAT IT DOES:
      • Finds project configuration by walking up directory tree
      • Gracefully stops Docker containers (Ollama + Qdrant)
      • Preserves all indexed data and configuration
      • Works from any subfolder within the indexed project

    \b
    DATA PRESERVATION:
      • All indexed code vectors remain intact
      • Project configuration is preserved
      • Docker containers remain available for restart
      • Models and databases are preserved

    \b
    GRACEFUL SHUTDOWN:
      • Waits for active operations to complete
      • Properly closes database connections
      • Saves any pending data to disk
      • Releases network ports cleanly

    \b
    EXAMPLES:
      cd /path/to/my/project/src/components
      code-indexer stop                     # Works from any subfolder
      code-indexer stop --force-docker      # Force Docker instead of Podman

    \b
    USE CASES:
      • Free up system resources when not coding
      • Prepare for machine shutdown or restart
      • Stop services before system maintenance
      • Temporarily disable indexing services

    \b
    RESTARTING:
      Use 'code-indexer start' to resume services with all data intact.
      Much faster than running 'start' again.
    """
    try:
        # Use configuration from CLI context
        config_manager = ctx.obj["config_manager"]
        config_path = config_manager.config_path

        if not config_path or not config_path.exists():
            console.print(
                "❌ No .code-indexer/config.json found in current directory tree",
                style="red",
            )
            console.print(
                "💡 Services may not be configured for this project", style="yellow"
            )
            sys.exit(1)

        # Load configuration
        config = config_manager.load()
        console.print(f"📁 Found configuration: {config_path}")
        console.print(f"🏗️  Project directory: {config.codebase_dir}")

        # Initialize Docker manager
        docker_manager = DockerManager(
            console, force_docker=force_docker, main_config=config.model_dump()
        )

        # Check current status
        status = docker_manager.get_service_status()
        if status["status"] == "not_configured":
            console.print("ℹ️  Services not configured - nothing to stop", style="blue")
            return

        running_services = [
            svc
            for svc in status["services"].values()
            if svc.get("state", "").lower() == "running"
        ]

        if not running_services:
            console.print("ℹ️  No services currently running", style="blue")
            return

        # Stop services
        console.print("🛑 Stopping code indexing services...")
        console.print("💾 All data will be preserved for restart")

        if docker_manager.stop_services():
            console.print("✅ Services stopped successfully!", style="green")
            console.print("💡 Use 'code-indexer start' to resume with all data intact")
        else:
            console.print("❌ Failed to stop some services", style="red")
            sys.exit(1)

    except Exception as e:
        console.print(f"❌ Stop failed: {e}", style="red")
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
