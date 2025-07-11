"""Command line interface for Code Indexer."""

import asyncio
import os
import sys
import signal
from pathlib import Path
from typing import Optional, Union, Callable

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

from .config import ConfigManager, Config
from .services import QdrantClient, DockerManager, EmbeddingProviderFactory
from .services.smart_indexer import SmartIndexer
from .services.generic_query_service import GenericQueryService
from .services.claude_integration import (
    ClaudeIntegrationService,
    check_claude_sdk_availability,
)
from .services.config_fixer import ConfigurationRepairer, generate_fix_report
from .services.vector_calculation_manager import get_default_thread_count
from .services.cidx_prompt_generator import create_cidx_ai_prompt
from .services.migration_decorator import requires_qdrant_access
from .services.legacy_detector import legacy_detector
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
    """Handler for graceful interruption of long-running operations with timeout protection."""

    def __init__(
        self,
        console: Console,
        operation_name: str = "Operation",
        cancellation_timeout: float = 30.0,
    ):
        self.console = console
        self.operation_name = operation_name
        self.interrupted = False
        self.force_quit = False
        self.cancellation_timeout = cancellation_timeout
        self.interrupt_time: Optional[float] = None
        self.original_sigint_handler: Optional[Union[Callable, int]] = None
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
        """Handle SIGINT (Ctrl-C) gracefully with immediate feedback and timeout protection."""
        import time

        current_time = time.time()

        # First interrupt - graceful cancellation
        if not self.interrupted:
            self.interrupted = True
            self.interrupt_time = current_time

            # Provide immediate visual feedback
            if self.progress_bar:
                self.progress_bar.stop()

            # Clear line and show immediate cancellation notice
            self.console.print()  # New line
            self.console.print(
                f"🛑 CANCELLATION REQUESTED - Interrupting {self.operation_name.lower()}...",
                style="bold yellow",
            )
            self.console.print(
                "⏳ Safely finishing current operations and saving progress...",
                style="cyan",
            )
            self.console.print(
                f"💡 Press Ctrl-C again within {self.cancellation_timeout}s to force quit (may lose progress)",
                style="dim yellow",
            )

        # Second interrupt - check timeout
        elif (
            self.interrupt_time
            and (current_time - self.interrupt_time) < self.cancellation_timeout
        ):
            self.force_quit = True
            self.console.print()  # New line
            self.console.print(
                "🚨 FORCE QUIT REQUESTED - Terminating immediately...", style="bold red"
            )
            self.console.print("⚠️  Progress may be lost!", style="red")
            # Force exit immediately
            import sys

            sys.exit(1)

        # Timeout exceeded - force quit automatically
        elif (
            self.interrupt_time
            and (current_time - self.interrupt_time) >= self.cancellation_timeout
        ):
            self.force_quit = True
            self.console.print()  # New line
            self.console.print(
                f"⏰ CANCELLATION TIMEOUT ({self.cancellation_timeout}s) - Force quitting...",
                style="bold red",
            )
            self.console.print("⚠️  Progress may be lost due to timeout!", style="red")
            # Force exit due to timeout
            import sys

            sys.exit(2)

    def set_progress_bar(self, progress_bar):
        """Set the progress bar to stop when interrupted."""
        self.progress_bar = progress_bar

    def is_cancellation_overdue(self) -> bool:
        """Check if cancellation has timed out and should be forced."""
        if not self.interrupted or not self.interrupt_time:
            return False

        import time

        return (time.time() - self.interrupt_time) >= self.cancellation_timeout

    def get_time_since_cancellation(self) -> float:
        """Get seconds since cancellation was requested."""
        if not self.interrupt_time:
            return 0.0

        import time

        return time.time() - self.interrupt_time


# Global console for rich output
console = Console()


@click.group(invoke_without_command=True)
@click.option("--config", "-c", type=click.Path(exists=False), help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True),
    help="Start directory for config discovery (walks up to find .code-indexer/)",
)
@click.option(
    "--use-cidx-prompt",
    is_flag=True,
    help="Generate and display a comprehensive prompt for AI systems to use cidx semantic search",
)
@click.option(
    "--format",
    type=click.Choice(["text", "markdown", "compact", "comprehensive"]),
    default="text",
    help="Output format for the cidx prompt (default: text)",
)
@click.option(
    "--output",
    type=click.Path(),
    help="Save cidx prompt to file instead of displaying",
)
@click.option(
    "--compact",
    is_flag=True,
    help="Generate compact version of cidx prompt (overrides --format)",
)
@click.version_option(version=__version__, prog_name="code-indexer")
@click.pass_context
def cli(
    ctx,
    config: Optional[str],
    verbose: bool,
    path: Optional[str],
    use_cidx_prompt: bool,
    format: str,
    output: Optional[str],
    compact: bool,
):
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
      • chunk_size: Text chunk size for processing (default: 1500)

      Exclusions also respect .gitignore patterns automatically.

    \b
    DATA MANAGEMENT:
      • Git-aware: Tracks branches, commits, and file changes
      • Project isolation: Each project gets its own collection
      • Storage: Vector data stored in ~/.code-indexer/global/qdrant/
      • Cleanup: Use 'clean-data' (fast) or 'uninstall' (complete removal)

    \b
    EXAMPLES:
      code-indexer init --max-file-size 2000000  # 2MB limit
      code-indexer index --clear                 # Fresh index
      code-indexer query "function authentication"
      code-indexer clean-data --all-projects  # Clear all project data

      # Generate AI integration prompt:
      code-indexer --use-cidx-prompt                    # Display prompt
      code-indexer --use-cidx-prompt --format markdown  # Markdown format
      code-indexer --use-cidx-prompt --compact          # Compact version
      code-indexer --use-cidx-prompt --output ai-prompt.txt  # Save to file

      # Using --path to work with different project locations:
      code-indexer --path /home/user/myproject index
      code-indexer --path ../other-project query "search term"
      code-indexer -p ./nested/folder status

    For detailed help on any command, use: code-indexer COMMAND --help
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # Handle --use-cidx-prompt flag (early return)
    if use_cidx_prompt:
        try:
            # Determine format (compact overrides format option)
            prompt_format = "compact" if compact else format

            # Generate the prompt
            prompt = create_cidx_ai_prompt(format=prompt_format)

            # Output to file or console
            if output:
                output_path = Path(output)
                output_path.write_text(prompt, encoding="utf-8")
                console.print(
                    f"✅ Cidx AI prompt saved to: {output_path}", style="green"
                )
            else:
                console.print(prompt)

            return
        except Exception as e:
            console.print(f"❌ Failed to generate cidx prompt: {e}", style="red")
            if verbose:
                import traceback

                console.print(traceback.format_exc())
            sys.exit(1)

    # If no command is provided and --use-cidx-prompt was not used, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        return

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
    "--chunk-size", type=int, help="Text chunk size in characters (default: 1500)"
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
    # For init command, always create config in current directory (or specified codebase_dir)
    # Don't use the CLI context's config_manager which may have found a parent config
    target_dir = Path(codebase_dir) if codebase_dir else Path.cwd()
    project_config_path = target_dir / ".code-indexer" / "config.json"
    config_manager = ConfigManager(project_config_path)

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
@requires_qdrant_access("start")
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

        # Only create a local config if NO config exists anywhere in the directory tree
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
            # Load existing config (found via backtracking)
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
        docker_manager = DockerManager(setup_console, force_docker=force_docker)

        # Ensure project has container names and ports configured
        project_root = config.codebase_dir
        project_config = docker_manager.ensure_project_configuration(
            config_manager, project_root
        )

        setup_console.print(
            f"📋 Project containers: {project_config['qdrant_name'][:12]}...",
            style="dim",
        )
        # Display assigned ports for active services only
        port_display = []
        if "qdrant_port" in project_config:
            port_display.append(f"Qdrant={project_config['qdrant_port']}")
        if "ollama_port" in project_config:
            port_display.append(f"Ollama={project_config['ollama_port']}")
        if "data_cleaner_port" in project_config:
            port_display.append(f"DataCleaner={project_config['data_cleaner_port']}")

        if port_display:
            setup_console.print(
                f"🔌 Assigned ports: {', '.join(port_display)}",
                style="dim",
            )

        if not docker_manager.is_docker_available():
            if force_docker:
                setup_console.print(
                    "❌ Docker is not available but --force-docker was specified. Please install Docker first.",
                    style="red",
                )
            else:
                setup_console.print(
                    "❌ Neither Podman nor Docker is available. Please install either Podman or Docker first.",
                    style="red",
                )
            sys.exit(1)

        if not docker_manager.is_compose_available():
            if force_docker:
                setup_console.print(
                    "❌ Docker Compose is not available but --force-docker was specified. Please install Docker Compose first.",
                    style="red",
                )
            else:
                setup_console.print(
                    "❌ Neither Podman Compose nor Docker Compose is available. Please install either Podman or Docker Compose first.",
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
            state = docker_manager.get_service_state(service, project_config)
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
            if not docker_manager.wait_for_services(project_config=project_config):
                setup_console.print("❌ Services failed to start properly", style="red")
                sys.exit(1)

        # Reload config to get updated ports after service startup
        config = config_manager.load()

        # Small delay to ensure port updates are fully written to config file
        import time

        time.sleep(0.5)

        # Test connections and setup based on provider
        with setup_console.status("Testing service connections..."):
            embedding_provider = EmbeddingProviderFactory.create(config, setup_console)
            qdrant_client = QdrantClient(
                config.qdrant, setup_console, Path(config.codebase_dir)
            )

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
            # Retry mechanism for Qdrant accessibility to handle port configuration propagation
            qdrant_accessible = False
            max_retries = 3
            for retry in range(max_retries):
                if qdrant_client.health_check():
                    qdrant_accessible = True
                    break
                if retry < max_retries - 1:  # Don't sleep on last retry
                    setup_console.print(
                        f"⏳ Qdrant not yet accessible, retrying in 2s... (attempt {retry + 1}/{max_retries})",
                        style="yellow",
                    )
                    time.sleep(2)
                    # Force config reload for next retry
                    config = config_manager.load()
                    qdrant_client = QdrantClient(
                        config.qdrant, setup_console, Path(config.codebase_dir)
                    )

            if not qdrant_accessible:
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

        # Ensure collection exists - use new fixed collection naming (base_name + model_slug)
        provider_info = EmbeddingProviderFactory.get_provider_model_info(config)
        model_slug = EmbeddingProviderFactory.generate_model_slug(
            "", provider_info["model_name"]
        )
        collection_name = f"{config.qdrant.collection_base_name}_{model_slug}"
        if not qdrant_client.ensure_collection(collection_name):
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
@click.option(
    "--parallel-vector-worker-thread-count",
    "-p",
    type=int,
    help="Number of parallel threads for vector calculations (default: 8 for VoyageAI, 1 for Ollama)",
)
@click.option(
    "--detect-deletions",
    is_flag=True,
    help="Detect and handle files deleted from filesystem but still in database (for standard indexing only; --reconcile includes this automatically)",
)
@requires_qdrant_access("index")
@click.pass_context
def index(
    ctx,
    clear: bool,
    reconcile: bool,
    batch_size: int,
    files_count_to_process: Optional[int],
    parallel_vector_worker_thread_count: Optional[int],
    detect_deletions: bool,
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
      • Throttling status indicators (VoyageAI only):
        ⚡ Full speed - no throttling detected
        🟡 CIDX throttling - our rate limiter is slowing requests
        🔴 Server throttling - API rate limits or slowness detected

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
      • --reconcile mode ALWAYS includes deletion detection automatically

    \b
    DELETION DETECTION:
      • Standard indexing ignores deleted files (leaves stale database entries)
      • Use --detect-deletions with standard indexing to clean up deleted files
      • Git projects: soft delete (hides files in current branch, preserves history)
      • Non-git projects: hard delete (removes files completely from database)
      • NOT needed with --reconcile (deletion detection always included)
      • NOT useful with --clear (collection is emptied and rebuilt anyway)

    \b
    PERFORMANCE TUNING:
      • Vector calculations can be parallelized for faster indexing
      • VoyageAI default: 8 threads (API supports parallel requests)
      • Ollama default: 1 thread (local model, avoid resource contention)
      • Use -p/--parallel-vector-worker-thread-count to customize

    \b
    EXAMPLES:
      code-indexer index                 # Smart incremental indexing (default)
      code-indexer index --clear         # Force full reindex (clears existing data)
      code-indexer index --reconcile     # Reconcile disk vs database and index missing/modified files
      code-indexer index --detect-deletions  # Standard indexing + cleanup deleted files
      code-indexer index -b 100          # Larger batch size for speed
      code-indexer index -p 4           # Use 4 parallel threads for vector calculations
      code-indexer index -p 1           # Force single-threaded for debugging

    \b
    STORAGE:
      Vector data stored in: ~/.code-indexer/global/qdrant/
      Each project gets its own collection for isolation.
    """
    config_manager = ctx.obj["config_manager"]

    # Validate flag combinations
    if detect_deletions and reconcile:
        console.print(
            "❌ Cannot use --detect-deletions with --reconcile",
            style="red",
        )
        console.print(
            "💡 --reconcile mode includes deletion detection automatically",
            style="yellow",
        )
        sys.exit(1)

    if detect_deletions and clear:
        console.print(
            "⚠️  Warning: --detect-deletions is redundant with --clear",
            style="yellow",
        )
        console.print(
            "💡 --clear empties the collection completely, making deletion detection unnecessary",
            style="yellow",
        )

    try:
        config = config_manager.load()

        # Initialize services
        embedding_provider = EmbeddingProviderFactory.create(config, console)
        qdrant_client = QdrantClient(config.qdrant, console, Path(config.codebase_dir))

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

        # Determine and display thread count for vector calculations
        if parallel_vector_worker_thread_count is None:
            thread_count = get_default_thread_count(embedding_provider)
            console.print(
                f"🧵 Vector calculation threads: {thread_count} (auto-detected for {embedding_provider.get_provider_name()})"
            )
        else:
            thread_count = parallel_vector_worker_thread_count
            console.print(
                f"🧵 Vector calculation threads: {thread_count} (user specified)"
            )

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

        def show_setup_message(message: str):
            """Display setup/informational messages as scrolling cyan text."""
            console.print(f"ℹ️  {message}", style="cyan")

        def show_error_message(file_path, error_msg: str):
            """Display error messages appropriately based on context."""
            if ctx.obj["verbose"]:
                if progress_bar is not None:
                    progress_bar.console.print(
                        f"❌ Failed to process {file_path}: {error_msg}", style="red"
                    )
                else:
                    console.print(
                        f"❌ Failed to process {file_path}: {error_msg}", style="red"
                    )

        def update_file_progress(current: int, total: int, info: str):
            """Update file processing progress bar with current status."""
            nonlocal progress_bar, task_id

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

            # Update progress bar with current info
            progress_bar.update(task_id, completed=current, description=info)

        def check_for_interruption():
            """Check if operation was interrupted and return signal."""
            if interrupt_handler and interrupt_handler.interrupted:
                return "INTERRUPT"
            return None

        def progress_callback(current, total, file_path, error=None, info=None):
            """Legacy progress callback - delegates to appropriate method based on parameters."""
            # Check for interruption first
            interrupt_result = check_for_interruption()
            if interrupt_result:
                return interrupt_result

            # Handle setup messages (total=0)
            if info and total == 0:
                show_setup_message(info)
                return

            # Handle file progress (total>0) with cancellation status
            if total > 0 and info:
                # Add cancellation indicator to progress info if interrupted
                if interrupt_handler and interrupt_handler.interrupted:
                    # Modify info to show cancellation status
                    cancellation_info = f"🛑 CANCELLING - {info}"
                    update_file_progress(current, total, cancellation_info)
                else:
                    update_file_progress(current, total, info)
                return

            # Show errors
            if error:
                show_error_message(file_path, error)
                return

            # Fallback: if somehow no progress bar exists, just print info (should rarely happen)
            if info:
                show_setup_message(info)

        # Clean API for components to use directly (no magic parameters!)
        # Note: mypy doesn't like adding attributes to functions, but this works at runtime
        progress_callback.show_setup_message = show_setup_message  # type: ignore
        progress_callback.update_file_progress = lambda current, total, info: (  # type: ignore
            check_for_interruption() or update_file_progress(current, total, info)
        )
        progress_callback.show_error_message = show_error_message  # type: ignore
        progress_callback.check_for_interruption = check_for_interruption  # type: ignore

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
                    vector_thread_count=thread_count,
                    detect_deletions=detect_deletions,
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
@click.option("--initial-sync", is_flag=True, help="Perform full sync before watching")
@requires_qdrant_access("watch")
@click.pass_context
def watch(ctx, debounce: float, batch_size: int, initial_sync: bool):
    """Git-aware watch for file changes with branch support."""
    config_manager = ctx.obj["config_manager"]

    try:
        from watchdog.observers import Observer

        # Import git-aware components
        from .services.git_topology_service import GitTopologyService
        from .services.watch_metadata import WatchMetadata
        from .services.git_aware_watch_handler import GitAwareWatchHandler

        config = config_manager.load()

        # Initialize services (same as index command)
        embedding_provider = EmbeddingProviderFactory.create(config, console)
        qdrant_client = QdrantClient(config.qdrant, console, Path(config.codebase_dir))

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

        # Initialize SmartIndexer (same as index command)
        metadata_path = config_manager.config_path.parent / "metadata.json"
        smart_indexer = SmartIndexer(
            config, embedding_provider, qdrant_client, metadata_path
        )

        # Initialize git topology service
        git_topology_service = GitTopologyService(config.codebase_dir)

        # Initialize watch metadata
        watch_metadata_path = config_manager.config_path.parent / "watch_metadata.json"
        watch_metadata = WatchMetadata.load_from_disk(watch_metadata_path)

        # Get git state for metadata
        git_state = (
            git_topology_service.get_current_state()
            if git_topology_service.is_git_available()
            else {
                "git_available": False,
                "current_branch": None,
                "current_commit": None,
            }
        )

        # Start watch session
        collection_name = qdrant_client.resolve_collection_name(
            config, embedding_provider
        )
        watch_metadata.start_watch_session(
            provider_name=embedding_provider.get_provider_name(),
            model_name=embedding_provider.get_current_model(),
            git_status=git_state,
            collection_name=collection_name,
        )

        # Perform initial sync if requested or if first run
        if initial_sync or watch_metadata.last_sync_timestamp == 0:
            console.print("🔄 Performing initial git-aware sync...")
            try:
                stats = smart_indexer.smart_index(batch_size=batch_size, quiet=True)
                console.print(
                    f"✅ Initial sync complete: {stats.files_processed} files processed"
                )
                watch_metadata.update_after_sync_cycle(
                    files_processed=stats.files_processed
                )
            except Exception as e:
                console.print(f"⚠️  Initial sync failed: {e}", style="yellow")
                console.print("Continuing with file watching...", style="yellow")

        # Initialize git-aware watch handler
        git_aware_handler = GitAwareWatchHandler(
            config=config,
            smart_indexer=smart_indexer,
            git_topology_service=git_topology_service,
            watch_metadata=watch_metadata,
            debounce_seconds=debounce,
        )

        console.print(f"\n👀 Starting git-aware watch on {config.codebase_dir}")
        console.print(f"⏱️  Debounce: {debounce}s")
        if git_topology_service.is_git_available():
            console.print(
                f"🌿 Git branch: {git_state.get('current_branch', 'unknown')}"
            )
        console.print("Press Ctrl+C to stop")

        # Start git-aware file watching
        git_aware_handler.start_watching()

        # Setup watchdog observer
        observer = Observer()
        observer.schedule(git_aware_handler, str(config.codebase_dir), recursive=True)
        observer.start()
        console.print(f"🔍 Watchdog observer started monitoring: {config.codebase_dir}")

        try:
            with GracefulInterruptHandler(
                console, "Git-aware file watching"
            ) as handler:
                console.print(
                    "👀 Watching for file changes and git operations... (Press Ctrl-C to stop)",
                    style="dim",
                )
                while not handler.interrupted:
                    import time

                    time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n👋 Stopping git-aware file watcher...")
        finally:
            git_aware_handler.stop_watching()
            observer.stop()
            observer.join()

            # Save final metadata
            watch_metadata.save_to_disk(watch_metadata_path)

            # Show final statistics
            watch_stats = git_aware_handler.get_statistics()
            console.print("\n📊 Watch session complete:")
            console.print(
                f"   • Files processed: {watch_stats['handler_files_processed']}"
            )
            console.print(
                f"   • Indexing cycles: {watch_stats['handler_indexing_cycles']}"
            )
            if watch_stats["total_branch_changes"] > 0:
                console.print(
                    f"   • Branch changes handled: {watch_stats['total_branch_changes']}"
                )

    except Exception as e:
        console.print(f"❌ Git-aware watch failed: {e}", style="red")
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
    "--accuracy",
    type=click.Choice(["fast", "balanced", "high"]),
    default="balanced",
    help="Search accuracy profile: fast (lower accuracy, faster), balanced (default), high (higher accuracy, slower)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Quiet mode - only show results, no headers or metadata",
)
@requires_qdrant_access("query")
@click.pass_context
def query(
    ctx,
    query: str,
    limit: int,
    language: Optional[str],
    path: Optional[str],
    min_score: Optional[float],
    accuracy: str,
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
      • Accuracy: --accuracy high (higher accuracy, slower search)

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
        qdrant_client = QdrantClient(config.qdrant, console, Path(config.codebase_dir))

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

        # Check if project uses git-aware indexing
        from .services.git_topology_service import GitTopologyService
        from .services.branch_aware_indexer import BranchAwareIndexer
        from .indexing.chunker import TextChunker

        git_topology_service = GitTopologyService(config.codebase_dir)
        is_git_aware = git_topology_service.is_git_available()

        # Initialize query service based on project type
        if is_git_aware:
            # Use branch-aware indexer for git projects
            text_chunker = TextChunker(config.indexing)
            branch_aware_indexer = BranchAwareIndexer(
                qdrant_client, embedding_provider, text_chunker, config
            )
            current_branch = git_topology_service.get_current_branch() or "master"
            use_branch_aware_query = True
        else:
            # Use generic query service for non-git projects
            query_service = GenericQueryService(config.codebase_dir, config)
            use_branch_aware_query = False

        # Apply embedding provider's model filtering when searching
        provider_info = embedding_provider.get_model_info()
        if not quiet:
            console.print(
                f"🤖 Using {embedding_provider.get_provider_name()} with model: {provider_info.get('name', 'unknown')}"
            )

            # Get current branch context for git-aware filtering
            if is_git_aware:
                console.print(f"📂 Git repository: {config.codebase_dir.name}")
                console.print(f"🌿 Current branch: {current_branch}")
            else:
                branch_context = query_service.get_current_branch_context()
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
            # Get current branch context for git-aware filtering (for non-git projects)
            if not is_git_aware:
                branch_context = query_service.get_current_branch_context()

        # Get current branch for display
        current_display_branch = "unknown"
        try:
            if (
                hasattr(query_service, "file_identifier")
                and query_service.file_identifier.git_available
            ):
                import subprocess

                git_result = subprocess.run(
                    ["git", "symbolic-ref", "--short", "HEAD"],
                    cwd=config.codebase_dir,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if git_result.returncode == 0:
                    current_display_branch = git_result.stdout.strip()
        except Exception:
            pass

        # Get current embedding model for filtering
        current_model = embedding_provider.get_current_model()
        if not quiet:
            console.print(f"🤖 Filtering by model: {current_model}")

        # Use appropriate search method based on project type
        if use_branch_aware_query:
            # Use branch-aware search for git projects
            if not quiet:
                console.print("🔍 Applying git-aware filtering...")

            # Build additional filters for branch-aware search
            additional_filters = {}
            if language:
                additional_filters["must"] = [
                    {"key": "language", "match": {"value": language}}
                ]
            if path:
                additional_filters.setdefault("must", []).append(
                    {"key": "path", "match": {"text": path}}
                )

            # Use branch-aware search
            results = branch_aware_indexer.search_with_branch_context(
                query_vector=query_embedding,
                branch=current_branch,
                limit=limit,
                collection_name=collection_name,
            )

            # Apply additional filters manually for now
            if language or path or min_score:
                filtered_results = []
                for result in results:
                    payload = result.get("payload", {})

                    # Filter by language
                    if language and payload.get("language") != language:
                        continue

                    # Filter by path
                    if path and path not in payload.get("path", ""):
                        continue

                    # Filter by minimum score
                    if min_score and result.get("score", 0) < min_score:
                        continue

                    filtered_results.append(result)

                results = filtered_results
        else:
            # Use model-specific search for non-git projects
            raw_results = qdrant_client.search_with_model_filter(
                query_vector=query_embedding,
                embedding_model=current_model,
                limit=limit * 2,  # Get more results to allow for git filtering
                score_threshold=min_score,
                additional_filters=filter_conditions,
                accuracy=accuracy,
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

            # Line number info
            line_start = payload.get("line_start")
            line_end = payload.get("line_end")

            # Create file path with line numbers
            if line_start is not None and line_end is not None:
                if line_start == line_end:
                    file_path_with_lines = f"{file_path}:{line_start}"
                else:
                    file_path_with_lines = f"{file_path}:{line_start}-{line_end}"
            else:
                file_path_with_lines = file_path

            if quiet:
                # Quiet mode - minimal output: score, path with line numbers, content
                console.print(f"{score:.3f} {file_path_with_lines}")
                if content:
                    # Show content with line numbers in quiet mode
                    content_to_display = content[:500]
                    content_lines = content_to_display.split("\n")

                    # Add line number prefixes if we have line start info
                    if line_start is not None:
                        numbered_lines = []
                        for i, line in enumerate(content_lines):
                            line_num = line_start + i
                            numbered_lines.append(f"{line_num:3}: {line}")
                        content_with_line_numbers = "\n".join(numbered_lines)
                        console.print(content_with_line_numbers)
                    else:
                        console.print(content_to_display)

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

                # Create header with git info and line numbers
                header = f"📄 File: {file_path_with_lines}"
                if language != "unknown":
                    header += f" | 🏷️  Language: {language}"
                header += f" | 📊 Score: {score:.3f}"

                console.print(f"\n[bold cyan]{header}[/bold cyan]")

                # Enhanced metadata display
                metadata_info = f"📏 Size: {file_size} bytes | 🕒 Indexed: {indexed_at}"

                if git_available:
                    # Use current branch for display (content points are branch-agnostic)
                    git_branch = current_display_branch
                    git_commit = payload.get("git_commit_hash", "unknown")
                    if git_commit != "unknown" and len(git_commit) > 8:
                        git_commit = git_commit[:8] + "..."
                    metadata_info += f" | 🌿 Branch: {git_branch}"
                    if git_commit != "unknown":
                        metadata_info += f" | 📦 Commit: {git_commit}"

                metadata_info += f" | 🏗️  Project: {project_id}"
                console.print(metadata_info)

                # Content preview with line numbers
                if content:
                    # Create content header with line range
                    if line_start is not None and line_end is not None:
                        if line_start == line_end:
                            content_header = f"📖 Content (Line {line_start}):"
                        else:
                            content_header = (
                                f"📖 Content (Lines {line_start}-{line_end}):"
                            )
                    else:
                        content_header = "📖 Content:"

                    console.print(f"\n{content_header}")
                    console.print("─" * 50)

                    # Add line number prefixes to content
                    content_to_display = content[:500]
                    content_lines = content_to_display.split("\n")

                    # Add line number prefixes if we have line start info
                    if line_start is not None:
                        numbered_lines = []
                        for i, line in enumerate(content_lines):
                            line_num = line_start + i
                            numbered_lines.append(f"{line_num:3}: {line}")
                        content_with_line_numbers = "\n".join(numbered_lines)
                    else:
                        content_with_line_numbers = content_to_display

                    # Syntax highlighting if possible (note: syntax highlighting with line numbers is complex)
                    if language and language != "unknown":
                        try:
                            # For now, use plain text with line numbers for better readability
                            # Rich's Syntax with line_numbers=True uses its own numbering system
                            console.print(content_with_line_numbers)
                        except Exception:
                            console.print(content_with_line_numbers)
                    else:
                        console.print(content_with_line_numbers)

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
    help="[RAG-first only] Number of semantic search results to include in initial prompt (default: 10)",
)
@click.option(
    "--context-lines",
    "-c",
    default=500,
    help="[RAG-first only] Lines of context around each match in initial prompt (default: 500)",
)
@click.option(
    "--language",
    help="[RAG-first only] Filter initial search by programming language (e.g., python, javascript)",
)
@click.option(
    "--path",
    help="[RAG-first only] Filter initial search by file path pattern (e.g., */tests/*)",
)
@click.option(
    "--min-score",
    type=float,
    help="[RAG-first only] Minimum similarity score for initial search (0.0-1.0)",
)
@click.option(
    "--max-turns",
    default=5,
    help="Maximum Claude conversation turns for multi-turn analysis (default: 5)",
)
@click.option(
    "--no-explore",
    is_flag=True,
    help="Disable file exploration hints in Claude prompt (limits Claude's search capabilities)",
)
@click.option(
    "--no-stream",
    is_flag=True,
    help="Disable streaming output - show complete results at once",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Quiet mode - minimal output, only show Claude's analysis results",
)
@click.option(
    "--dry-run-show-claude-prompt",
    is_flag=True,
    help="Debug mode: show the full prompt sent to Claude without executing analysis",
)
@click.option(
    "--show-claude-plan",
    is_flag=True,
    help="Show real-time tool usage tracking and generate summary of Claude's analysis strategy",
)
@click.option(
    "--rag-first",
    is_flag=True,
    help="Use legacy RAG-first approach: run semantic search upfront, then send all results to Claude. Default is claude-first: Claude uses search on-demand.",
)
@click.option(
    "--include-file-list",
    is_flag=True,
    help="Include full project directory listing in Claude prompt for better project understanding (increases prompt size)",
)
@requires_qdrant_access("claude")
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
    show_claude_plan: bool,
    rag_first: bool,
    include_file_list: bool,
):
    """AI-powered code analysis using Claude with semantic search.

    \b
    Two analysis approaches available:

    DEFAULT (Claude-First):
    1. Send question directly to Claude with project context
    2. Claude uses semantic search on-demand via cidx query tool
    3. More interactive, adaptive analysis

    LEGACY (--rag-first):
    1. Run semantic search to find relevant code upfront
    2. Extract context around matches
    3. Send all context + question to Claude for analysis

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
      code-indexer claude "Analyze the codebase" --show-claude-plan  # Real-time tool usage tracking

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
    TOOL USAGE TRACKING:
      Use --show-claude-plan to see real-time feedback on Claude's tool usage
      and get a comprehensive summary of the problem-solving approach:
      • 🔍✨ Visual cues for semantic search (cidx) usage (preferred)
      • 😞 Visual cues for text-based search (grep) usage (discouraged)
      • 📖 File reading and exploration activities
      • Real-time status line showing current tool activity
      • Final summary narrative of Claude's approach and statistics

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

        # If in dry-run mode, skip service health checks
        if not dry_run_show_claude_prompt:
            # Quick health checks with shorter timeout for better UX in Claude command
            # Create temporary clients with 3-second timeout for health checks
            import httpx

            try:
                # Quick embedding service check
                if config.embedding_provider == "ollama":
                    quick_client = httpx.Client(
                        base_url=config.ollama.host, timeout=3.0
                    )
                    response = quick_client.get("/api/tags")
                    quick_client.close()
                    if response.status_code != 200:
                        raise Exception("Ollama not responding")

                # Quick Qdrant check
                quick_qdrant = httpx.Client(base_url=config.qdrant.host, timeout=3.0)
                response = quick_qdrant.get("/healthz")
                quick_qdrant.close()
                if response.status_code != 200:
                    raise Exception("Qdrant not responding")

            except Exception:
                console.print(
                    "❌ Services not available. Run 'code-indexer start' first.",
                    style="red",
                )
                sys.exit(1)

        # For dry-run mode, we only need minimal initialization
        if dry_run_show_claude_prompt:
            # Initialize only what's needed for prompt generation
            # Initialize query service for git-aware filtering (doesn't need services)
            query_service = GenericQueryService(config.codebase_dir, config)

            # Get project context
            branch_context = query_service.get_current_branch_context()
            if not quiet:
                if branch_context["git_available"]:
                    console.print(f"📂 Git repository: {branch_context['project_id']}")
                    console.print(
                        f"🌿 Current branch: {branch_context['current_branch']}"
                    )
                else:
                    console.print(f"📁 Non-git project: {branch_context['project_id']}")

            # Initialize Claude integration service (needed for prompt generation)
            claude_service = ClaudeIntegrationService(
                codebase_dir=config.codebase_dir,
                project_name=branch_context["project_id"],
            )

            # Skip to dry-run handling without initializing other services
            embedding_provider = None
            qdrant_client = None
        else:
            # Initialize services (after health checks pass)
            embedding_provider = EmbeddingProviderFactory.create(config, console)
            qdrant_client = QdrantClient(
                config.qdrant, console, Path(config.codebase_dir)
            )

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
                    console.print(
                        f"🌿 Current branch: {branch_context['current_branch']}"
                    )
                else:
                    console.print(f"📁 Non-git project: {branch_context['project_id']}")

            # Initialize Claude integration service (needed for both approaches)
            claude_service = ClaudeIntegrationService(
                codebase_dir=config.codebase_dir,
                project_name=branch_context["project_id"],
            )

        # Branch based on approach: claude-first (default) or RAG-first (legacy)
        if rag_first and not dry_run_show_claude_prompt:
            # LEGACY RAG-FIRST APPROACH
            if not quiet:
                console.print("🔄 Using legacy RAG-first approach")
                console.print(f"🔍 Performing semantic search: '{question}'")
                console.print(
                    f"📊 Limit: {limit}  < /dev/null |  Context: {context_lines} lines"
                )

            # Ensure we have required services for RAG-first approach
            if embedding_provider is None or qdrant_client is None:
                console.print(
                    "❌ Services not initialized for RAG-first approach", style="red"
                )
                sys.exit(1)

            if not quiet:
                with console.status("Generating query embedding..."):
                    embedding_provider.get_embedding(question)
            else:
                embedding_provider.get_embedding(question)

            # Get query embedding
            query_embedding = embedding_provider.get_embedding(question)

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

            # Get current embedding model for filtering
            current_model = embedding_provider.get_current_model()

            # Perform semantic search using model-specific filter
            raw_results = qdrant_client.search_with_model_filter(
                query_vector=query_embedding,
                embedding_model=current_model,
                limit=limit * 2,  # Get more results to allow for git filtering
                score_threshold=min_score,
                additional_filters=filter_conditions,
            )

            # Apply git-aware filtering
            search_results = query_service.filter_results_by_current_branch(raw_results)

            # Limit to requested number after filtering
            search_results = search_results[:limit]

            # Handle dry-run mode for RAG-first: show the prompt that would be sent to Claude
            if dry_run_show_claude_prompt:
                if not quiet:
                    console.print("🔍 Generating RAG-first Claude prompt...")

                # Extract contexts from search results for prompt generation
                contexts = (
                    claude_service.context_extractor.extract_context_from_results(
                        search_results, context_lines
                    )
                )

                # Generate the prompt that would be sent to Claude
                prompt = claude_service.create_analysis_prompt(
                    user_query=question,
                    contexts=contexts,
                    project_info=branch_context,
                    enable_exploration=not no_explore,
                )

                if not quiet:
                    console.print("\n📄 Generated Claude Prompt (RAG-first):")
                    console.print("-" * 80)

                # Display the prompt without Rich formatting to preserve exact line breaks
                print(prompt, end="")

                if not quiet:
                    console.print("\n" + "-" * 80)
                    console.print(
                        "💡 This is the RAG-first prompt that would be sent to Claude."
                    )
                    console.print(f"   Based on {len(search_results)} search results.")
                    console.print(
                        "   Use without --dry-run-show-claude-prompt to execute the analysis."
                    )

                return  # Exit early without running Claude

            # Run RAG-based analysis
            analysis_result = claude_service.run_analysis(
                user_query=question,
                search_results=search_results,
                context_lines=context_lines,
                project_info=branch_context,
                enable_exploration=not no_explore,
                stream=not no_stream,
                quiet=quiet,
                show_claude_plan=show_claude_plan,
            )

            # Handle results
            if not analysis_result.success:
                if not quiet:
                    console.print(
                        f"❌ Claude analysis failed: {analysis_result.error}",
                        style="red",
                    )
                sys.exit(1)

        else:
            # NEW CLAUDE-FIRST APPROACH
            if not quiet:
                console.print("✨ Using new claude-first approach")
                console.print("🧠 Claude will use semantic search on-demand")

            # Handle dry-run mode: just show the prompt without executing
            if dry_run_show_claude_prompt:
                if not quiet:
                    console.print("🔍 Generating Claude prompt...")

                # Generate the prompt that would be sent to Claude
                prompt = claude_service.create_claude_first_prompt(
                    user_query=question,
                    project_info=branch_context,
                    include_project_structure=include_file_list,
                )

                if not quiet:
                    console.print("\n📄 Generated Claude Prompt:")
                    console.print("-" * 80)

                # Display the prompt without Rich formatting to preserve exact line breaks
                print(prompt, end="")

                if not quiet:
                    console.print("\n" + "-" * 80)
                    console.print("💡 This is the prompt that would be sent to Claude.")
                    console.print(
                        "   Use without --dry-run-show-claude-prompt to execute the analysis."
                    )

                return  # Exit early without running Claude

            # Run claude-first analysis directly
            use_streaming = not no_stream

            analysis_result = claude_service.run_claude_first_analysis(
                user_query=question,
                project_info=branch_context,
                max_turns=max_turns,
                stream=use_streaming,
                quiet=quiet,
                show_claude_plan=show_claude_plan,
                include_project_structure=include_file_list,
            )

            # Handle results
            if not analysis_result.success:
                if not quiet:
                    console.print(
                        f"❌ Claude analysis failed: {analysis_result.error}",
                        style="red",
                    )
                sys.exit(1)

            # Show results (simplified for claude-first)
            if not use_streaming and not quiet:
                console.print("\n🤖 Claude Analysis Results")
                console.print("─" * 80)

            # Show metadata
            if not quiet and not (show_claude_plan and use_streaming):
                console.print("\n📊 Analysis Summary:")
                console.print("   • Claude-first approach used (no upfront RAG)")
                console.print("   • Semantic search performed on-demand by Claude")

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
    _status_impl(ctx, force_docker)


def _status_impl(ctx, force_docker: bool):
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
        docker_manager = DockerManager(force_docker=force_docker)
        try:
            service_status = docker_manager.get_service_status()
            docker_status = (
                "✅ Running"
                if service_status["status"] == "running"
                else "❌ Not Running"
            )
            table.add_row(
                "Docker Services",
                docker_status,
                f"{len(service_status['services'])} services",
            )
        except Exception:
            # Handle case where containers haven't been created yet
            table.add_row(
                "Docker Services",
                "❌ Not Configured",
                "Run 'code-indexer start' to create containers",
            )
            service_status = {"status": "not_configured", "services": {}}

        # Check embedding provider - only if container is running
        try:
            embedding_provider = EmbeddingProviderFactory.create(config, console)
            provider_name = embedding_provider.get_provider_name().title()

            # Check if embedding provider needs a container (Ollama)
            if config.embedding_provider == "ollama":
                # Check if ollama container is running first
                ollama_container_running = False
                if service_status["services"]:  # Only check if services dict exists
                    for container_name, container_info in service_status[
                        "services"
                    ].items():
                        if (
                            "ollama" in container_name
                            and container_info["state"] == "running"
                        ):
                            ollama_container_running = True
                            break

                if ollama_container_running:
                    provider_ok = embedding_provider.health_check()
                    provider_status = "✅ Ready" if provider_ok else "❌ Not Available"
                    provider_details = (
                        f"Model: {embedding_provider.get_current_model()}"
                        if provider_ok
                        else "Service down"
                    )
                else:
                    provider_status = "❌ Container not running"
                    provider_details = "Ollama container is not running"
            else:
                # For non-container providers (VoyageAI), do health check
                provider_ok = embedding_provider.health_check()
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

        # Check Ollama status specifically
        if config.embedding_provider == "ollama":
            # Ollama is required, status already shown above
            pass
        else:
            # Ollama is not needed with this configuration
            table.add_row(
                "Ollama", "✅ Not needed", f"Using {config.embedding_provider}"
            )

        # Check Qdrant - only if container is running
        qdrant_container_running = False
        qdrant_ok = False  # Initialize to False
        qdrant_client = None  # Initialize to None
        if service_status["services"]:  # Only check if services dict exists
            for container_name, container_info in service_status["services"].items():
                if "qdrant" in container_name and container_info["state"] == "running":
                    qdrant_container_running = True
                    break

        if qdrant_container_running:
            qdrant_client = QdrantClient(config.qdrant)
            qdrant_ok = qdrant_client.health_check()
            qdrant_status = "✅ Ready" if qdrant_ok else "❌ Not Available"
            qdrant_details = ""
            if qdrant_ok:
                try:
                    # Get the correct collection name using the current embedding provider
                    embedding_provider = EmbeddingProviderFactory.create(
                        config, console
                    )
                    collection_name = qdrant_client.resolve_collection_name(
                        config, embedding_provider
                    )
                    project_count = qdrant_client.count_points(collection_name)

                    # Get total documents across all collections for context
                    try:
                        import requests  # type: ignore

                        response = requests.get(
                            f"{config.qdrant.host}/collections", timeout=5
                        )
                        if response.status_code == 200:
                            collections_data = response.json()
                            total_count = 0
                            for collection_info in collections_data.get(
                                "result", {}
                            ).get("collections", []):
                                coll_name = collection_info["name"]
                                coll_count = qdrant_client.count_points(coll_name)
                                total_count += coll_count
                            qdrant_details = f"Project: {project_count} docs | Total: {total_count} docs"
                        else:
                            qdrant_details = f"Documents: {project_count}"
                    except Exception:
                        qdrant_details = f"Documents: {project_count}"
                except Exception:
                    qdrant_details = "Collection ready"
            else:
                qdrant_details = "Service down"
        else:
            qdrant_status = "❌ Container not running"
            qdrant_details = "Qdrant container is not running"

        table.add_row("Qdrant", qdrant_status, qdrant_details)

        # Add Qdrant storage and collection information
        try:
            import os

            # Get storage path from configuration instead of container inspection
            # Use the project-specific storage path
            project_storage_path = (
                f"/home/{os.getenv('USER', 'user')}/Dev/code-indexer/.qdrant-storage"
            )
            table.add_row("Qdrant Storage", "📁", f"Host:\n{project_storage_path}")

            # Add current project collection information
            if qdrant_ok and qdrant_client:
                try:
                    embedding_provider = EmbeddingProviderFactory.create(
                        config, console
                    )
                    collection_name = qdrant_client.resolve_collection_name(
                        config, embedding_provider
                    )

                    # Check if collection exists and get basic info
                    collection_exists = qdrant_client.collection_exists(collection_name)
                    if collection_exists:
                        collection_count = qdrant_client.count_points(collection_name)
                        collection_status = "✅ Active"

                        # Get local collection path if using symlink system
                        local_collection_path = (
                            config_manager.config_path.parent
                            / "~"
                            / "Dev"
                            / "code-indexer"
                            / ".code-indexer"
                            / "collections"
                            / collection_name
                        )

                        symlink_status = (
                            "Local symlinked"
                            if local_collection_path.exists()
                            else "Global storage"
                        )
                        # Show full collection name and details
                        collection_details = f"Name:\n{collection_name}\nPoints: {collection_count:,} | Storage: {symlink_status}"
                    else:
                        collection_status = "❌ Missing"
                        # Show full collection name for missing collections too
                        collection_details = f"Name:\n{collection_name}\nStatus: Not created yet - run 'index' command"

                    table.add_row(
                        "Project Collection", collection_status, collection_details
                    )
                except Exception as e:
                    table.add_row(
                        "Project Collection", "⚠️  Error", f"Check failed: {str(e)[:50]}"
                    )
            else:
                table.add_row(
                    "Project Collection", "❌ Unavailable", "Qdrant service down"
                )

        except Exception as e:
            table.add_row(
                "Qdrant Storage", "⚠️  Error", f"Inspection failed: {str(e)[:30]}"
            )

        # Check Data Cleaner
        #
        # CRITICAL IMPLEMENTATION NOTE: This status check was debugged and fixed to handle
        # the data-cleaner's netcat-based HTTP implementation which has specific limitations:
        #
        # PROBLEM DISCOVERED: The data-cleaner container runs a simple bash script that uses
        # `nc -l -p 8091` (netcat) to simulate an HTTP server. This implementation:
        # 1. Only handles ONE connection at a time
        # 2. Resets the connection immediately after responding
        # 3. Cycles every 10 seconds (sleep 10 in the loop)
        # 4. Causes ConnectionResetError with Python requests library
        # 5. Works fine with curl (which handles connection resets gracefully)
        #
        # SYMPTOMS OF BREAKAGE:
        # - curl http://localhost:8091/ returns "Cleanup service ready" ✅
        # - Python requests.get() throws ConnectionResetError ❌
        # - Status shows "❌ Not Available" despite container running
        # - docker ps shows container as healthy
        #
        # DEBUGGING NOTES:
        # - The netcat server responds once per cycle and immediately closes
        # - HTTP/1.1 keep-alive connections fail due to immediate connection termination
        # - Connection: close header helps but doesn't fully solve timing issues
        # - Port availability check works when netcat is between cycles
        #
        # SOLUTION IMPLEMENTED:
        # Multi-layered approach to handle netcat server limitations robustly
        # DO NOT simplify this logic without understanding the netcat behavior!
        #
        data_cleaner_available = False
        data_cleaner_details = "Service down"

        try:
            import requests  # type: ignore
            import subprocess
            import socket

            # APPROACH 1: HTTP request with Connection: close header
            # This works when netcat is actively listening and handles the request immediately
            # The Connection: close header prevents HTTP/1.1 keep-alive issues with netcat
            try:
                # Use project-specific calculated data cleaner port
                data_cleaner_port = getattr(
                    config.project_ports, "data_cleaner_port", 8091
                )
                data_cleaner_url = f"http://localhost:{data_cleaner_port}/"
                response = requests.get(
                    data_cleaner_url,
                    timeout=3,
                    headers={
                        "Connection": "close"
                    },  # Critical: prevents keep-alive issues
                )
                if response.status_code == 200:
                    data_cleaner_available = True
                    data_cleaner_details = "Cleanup service active"
            except (requests.exceptions.ConnectionError, ConnectionResetError):
                # Expected behavior: netcat closes connection immediately after responding
                # This exception is NORMAL and indicates we need to try other approaches

                # APPROACH 2: Raw socket connection test
                # This works when netcat is between cycles (during the sleep 10 period)
                # We just check if something is listening on the data cleaner port
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(1)  # Quick check to avoid delays
                        connect_result = sock.connect_ex(
                            ("localhost", data_cleaner_port)
                        )
                        if connect_result == 0:  # Port is listening
                            data_cleaner_available = True
                            data_cleaner_details = "Cleanup service active (netcat)"
                except Exception:
                    # Socket connection failed - port not listening or refused
                    pass

            # APPROACH 3: Container status fallback
            # If both HTTP and socket checks fail, verify the container is at least running
            # This catches cases where the service is starting up or having issues
            if not data_cleaner_available:
                try:
                    result = subprocess.run(
                        [
                            "docker",
                            "ps",
                            "--filter",
                            "name=data-cleaner",
                            "--format",
                            "{{.Names}}",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if "data-cleaner" in result.stdout:
                        data_cleaner_available = True
                        data_cleaner_details = (
                            "Container running (service may be cycling)"
                        )
                        # Note: This indicates container is up but netcat might be restarting
                except Exception:
                    # Docker command failed - container likely not running
                    pass

        except Exception as e:
            data_cleaner_details = f"Check failed: {str(e)[:50]}"

        # FINAL STATUS DETERMINATION
        # If ANY of the three approaches succeeded, consider the service available
        # This robust approach handles the netcat server's unpredictable timing
        data_cleaner_status = (
            "✅ Ready" if data_cleaner_available else "❌ Not Available"
        )

        # WARNING FOR FUTURE DEVELOPERS:
        # - Do NOT simplify this to just requests.get() - it will break randomly
        # - Do NOT remove the multi-approach logic - netcat is unpredictable
        # - If changing data-cleaner implementation, update these comments
        # - Test thoroughly with `cidx status` command multiple times in succession
        # - Consider replacing netcat with proper HTTP server if reliability issues persist

        table.add_row("Data Cleaner", data_cleaner_status, data_cleaner_details)

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
        if qdrant_ok and qdrant_client:
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
@requires_qdrant_access("optimize")
@click.pass_context
def optimize(ctx):
    """Optimize vector database storage and performance."""
    config_manager = ctx.obj["config_manager"]

    try:
        config = config_manager.load()

        # Initialize Qdrant client
        qdrant_client = QdrantClient(config.qdrant, console, Path(config.codebase_dir))

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
    "--collection",
    help="Specific collection to flush (flushes all collections if not specified)",
)
@requires_qdrant_access("force-flush")
@click.pass_context
def force_flush(ctx, collection: Optional[str]):
    """Force flush collection data from RAM to disk for CoW operations.

    \b
    ⚠️  DEPRECATED: This command is no longer needed with modern Qdrant and
    per-project container architecture. Qdrant now handles data persistence
    automatically without manual flush operations.

    \b
    Forces Qdrant to flush all collection data from memory to disk
    using the snapshot API. This ensures data consistency before
    copy-on-write (CoW) cloning operations.

    \b
    USAGE SCENARIOS:
      • Before CoW cloning indexed projects
      • Ensuring data persistence before system maintenance
      • Debugging collection data consistency issues

    \b
    TECHNICAL DETAILS:
      • Creates temporary snapshots to trigger flush
      • Automatically cleans up temporary snapshots
      • Works with both global and local storage modes
      • Safe to run on active collections

    \b
    COW CLONING EXAMPLES:
      # Complete workflow for CoW cloning:
      code-indexer force-flush              # Flush before cloning

      # BTRFS filesystem (most common):
      cp --reflink=always -r /path/to/project /path/to/clone

      # ZFS filesystem:
      zfs snapshot tank/project@clone
      zfs clone tank/project@clone tank/clone

      # XFS filesystem (requires reflink support):
      cp --reflink=always -r /path/to/project /path/to/clone

      # After cloning, fix config in clone:
      cd /path/to/clone && code-indexer fix-config --force
    """
    config_manager = ctx.obj["config_manager"]

    # Show deprecation warning
    console.print(
        "⚠️  DEPRECATION WARNING: The 'force-flush' command is deprecated and no longer needed.",
        style="yellow",
    )
    console.print(
        "   Modern Qdrant handles data persistence automatically. Consider removing this from your workflows.",
        style="yellow",
    )
    console.print()

    try:
        config = config_manager.load()

        # Initialize Qdrant client
        qdrant_client = QdrantClient(config.qdrant, console, Path(config.codebase_dir))

        # Health check
        if not qdrant_client.health_check():
            console.print("❌ Qdrant service not available", style="red")
            sys.exit(1)

        if collection:
            # Flush specific collection
            console.print(f"💾 Force flushing collection '{collection}' to disk...")
            success = qdrant_client.force_flush_to_disk(collection)

            if success:
                console.print(
                    f"✅ Successfully flushed collection '{collection}' to disk",
                    style="green",
                )
            else:
                console.print(
                    f"❌ Failed to flush collection '{collection}'", style="red"
                )
                sys.exit(1)
        else:
            # Flush all collections
            console.print("💾 Force flushing all collections to disk...")

            # Get list of existing collections
            collections = qdrant_client.list_collections()
            if not collections:
                console.print("ℹ️  No collections found to flush", style="yellow")
                return

            console.print(f"Found {len(collections)} collections to flush...")

            failed_collections = []
            for coll_name in collections:
                console.print(f"  💾 Flushing '{coll_name}'...")
                success = qdrant_client.force_flush_to_disk(coll_name)

                if success:
                    console.print(
                        f"  ✅ '{coll_name}' flushed successfully", style="green"
                    )
                else:
                    console.print(f"  ❌ Failed to flush '{coll_name}'", style="red")
                    failed_collections.append(coll_name)

            if failed_collections:
                console.print(
                    f"❌ Failed to flush {len(failed_collections)} collections: {', '.join(failed_collections)}",
                    style="red",
                )
                sys.exit(1)
            else:
                console.print(
                    f"✅ Successfully flushed all {len(collections)} collections to disk",
                    style="green",
                )

    except Exception as e:
        console.print(f"❌ Force flush failed: {e}", style="red")
        sys.exit(1)


# DEPRECATED: The 'clean' command was removed because it was semantically confusing.
#
# DO NOT RE-ADD THE 'clean' COMMAND - it created confusion between:
# - clean (stop services + optionally remove data)
# - clean-data (remove data, keep services running)
# - stop (stop services, keep data)
# - uninstall (remove everything)
#
# Instead, use these specific commands:
# - Use 'stop' to stop services while preserving data
# - Use 'clean-data' to clear data while keeping containers running (fast for tests)
# - Use 'uninstall' to completely remove everything
#
# The old 'clean' command functionality is now split between 'stop' and 'uninstall'
# to provide clearer semantics and avoid user confusion.
#
# DEPRECATED: The 'setup' command was also removed for similar clarity reasons.
#
# DO NOT RE-ADD THE 'setup' COMMAND - it was replaced by the combination of:
# - 'init' (optional configuration initialization)
# - 'start' (intelligent service startup with auto-configuration)
#
# The 'start' command now handles all setup functionality intelligently:
# - Creates default config if none exists
# - Starts only required services for the chosen embedding provider
# - Handles model downloads and service health checks
# - Works from any directory (walks up to find .code-indexer)
#
# This provides clearer separation of concerns and better user experience.


@cli.command()
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.pass_context
def stop(ctx, force_docker: bool):
    """Stop code indexing services while preserving all data.

    \b
    Stops Docker containers for Ollama and Qdrant services without
    removing any data or configuration. Can be run from any subfolder
    of an indexed project.

    \b
    WHAT IT DOES:
      • Finds project configuration by walking up directory tree
      • Stops Docker containers (Ollama + Qdrant)
      • Preserves all indexed data and configuration
      • Works from any subfolder within the indexed project

    \b
    DATA PRESERVATION:
      • All indexed code vectors remain intact
      • Project configuration is preserved
      • Docker volumes and networks are preserved
      • Models and databases are preserved

    \b
    PERFORMANCE:
      • Containers are stopped, not removed
      • Fast restart with 'start' command (5-10 seconds)
      • Much faster than 'uninstall' followed by 'start'
      • Ideal for freeing resources without full cleanup

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
        docker_manager = DockerManager(console, force_docker=force_docker)

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


@cli.command("clean-data")
@click.option(
    "--all-projects",
    is_flag=True,
    help="Clear data for all projects, not just current project",
)
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.pass_context
def clean_data(ctx, all_projects: bool, force_docker: bool):
    """Clear project data without stopping containers.

    \b
    Removes indexed data and configuration while keeping Docker containers
    running for fast restart. Use this between tests or when switching projects.

    \b
    WHAT IT DOES:
      • Clears Qdrant collections (current project or all projects)
      • Removes local .code-indexer directory
      • Keeps Docker containers running for fast restart
      • Preserves container state and networks

    \b
    OPTIONS:
      --all-projects     Clear data for all projects
      (default)          Clear only current project data

    \b
    PERFORMANCE:
      This is much faster than 'uninstall' since containers stay running.
      Perfect for test cleanup and project switching.
    """
    try:
        docker_manager = DockerManager(force_docker=force_docker)

        if not docker_manager.clean_data_only(all_projects=all_projects):
            sys.exit(1)

    except Exception as e:
        console.print(f"❌ Data cleanup failed: {e}", style="red")
        sys.exit(1)


def _perform_complete_system_wipe(force_docker: bool, console: Console):
    """Perform complete system wipe including all containers, images, cache, and storage directories.

    This is the nuclear option that removes everything related to code-indexer
    and container engines, including cached data that might persist between runs.
    """

    console.print(
        "⚠️  [bold red]PERFORMING COMPLETE SYSTEM WIPE[/bold red]", style="red"
    )
    console.print(
        "This will remove ALL containers, images, cache, and storage directories!",
        style="yellow",
    )

    # Step 1: Standard cleanup first
    console.print("\n🔧 [bold]Step 1: Standard container cleanup[/bold]")
    try:
        docker_manager = DockerManager(force_docker=force_docker)
        if not docker_manager.remove_containers(remove_volumes=True):
            console.print(
                "⚠️  Standard cleanup had issues, continuing with wipe...",
                style="yellow",
            )
        docker_manager.clean_data_only(all_projects=True)
        console.print("✅ Standard cleanup completed")
    except Exception as e:
        console.print(
            f"⚠️  Standard cleanup failed: {e}, continuing with wipe...", style="yellow"
        )

    # Step 2: Detect container engine
    console.print("\n🔧 [bold]Step 2: Detecting container engine[/bold]")
    container_engine = _detect_container_engine(force_docker)
    console.print(f"📦 Using container engine: {container_engine}")

    # Step 3: Remove ALL container images
    console.print("\n🔧 [bold]Step 3: Removing ALL container images[/bold]")
    _wipe_container_images(container_engine, console)

    # Step 4: Aggressive system prune
    console.print("\n🔧 [bold]Step 4: Aggressive system prune[/bold]")
    _aggressive_system_prune(container_engine, console)

    # Step 5: Remove storage directories
    console.print("\n🔧 [bold]Step 5: Removing storage directories[/bold]")
    _wipe_storage_directories(console)

    # Step 6: Check for remaining root-owned files in current project
    console.print("\n🔧 [bold]Step 6: Checking for remaining root-owned files[/bold]")
    _check_remaining_root_files(console)

    console.print("\n🎯 [bold green]COMPLETE SYSTEM WIPE FINISHED[/bold green]")
    console.print("💡 Run 'code-indexer start' to reinstall from scratch", style="blue")


def _detect_container_engine(force_docker: bool) -> str:
    """Detect which container engine to use."""
    import subprocess

    if force_docker:
        return "docker"

    # Try podman first (preferred)
    try:
        subprocess.run(
            ["podman", "--version"], capture_output=True, check=True, timeout=5
        )
        return "podman"
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        pass

    # Fall back to docker
    try:
        subprocess.run(
            ["docker", "--version"], capture_output=True, check=True, timeout=5
        )
        return "docker"
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        raise RuntimeError("Neither podman nor docker is available")


def _wipe_container_images(container_engine: str, console: Console):
    """Remove all container images, including code-indexer and cached images."""
    import subprocess

    try:
        # First, get list of all images
        result = subprocess.run(
            [container_engine, "images", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and result.stdout.strip():
            image_ids = result.stdout.strip().split("\n")
            console.print(f"🗑️  Found {len(image_ids)} images to remove")

            # Remove images in batches to avoid command line length limits
            batch_size = 50
            removed_count = 0
            for i in range(0, len(image_ids), batch_size):
                batch = image_ids[i : i + batch_size]
                try:
                    cleanup_result = subprocess.run(
                        [container_engine, "rmi", "-f"] + batch,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if cleanup_result.returncode == 0:
                        removed_count += len(batch)
                    else:
                        # Some images might be in use, continue with next batch
                        console.print(
                            "⚠️  Some images in batch could not be removed",
                            style="yellow",
                        )
                except subprocess.TimeoutExpired:
                    console.print(
                        "⚠️  Timeout removing image batch, continuing...", style="yellow"
                    )

            console.print(f"✅ Removed {removed_count} container images")
        else:
            console.print("ℹ️  No container images found to remove")

    except Exception as e:
        console.print(f"⚠️  Image removal failed: {e}", style="yellow")


def _aggressive_system_prune(container_engine: str, console: Console):
    """Perform aggressive system prune to remove all cached data."""
    import subprocess

    commands = [
        (
            f"{container_engine} system prune -a -f --volumes",
            "Remove all unused data and volumes",
        ),
        (
            (f"{container_engine} builder prune -a -f", "Remove build cache")
            if container_engine == "docker"
            else None
        ),
        (f"{container_engine} network prune -f", "Remove unused networks"),
    ]

    for cmd_info in commands:
        if cmd_info is None:
            continue

        cmd, description = cmd_info
        try:
            console.print(f"🧹 {description}...")
            result = subprocess.run(
                cmd.split(), capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                console.print(f"✅ {description} completed")
            else:
                console.print(
                    f"⚠️  {description} had issues: {result.stderr[:100]}",
                    style="yellow",
                )
        except subprocess.TimeoutExpired:
            console.print(f"⚠️  {description} timed out", style="yellow")
        except Exception as e:
            console.print(f"⚠️  {description} failed: {e}", style="yellow")


def _wipe_storage_directories(console: Console):
    """Remove all code-indexer related storage directories."""
    import shutil
    from pathlib import Path

    # Directories to remove
    directories = [
        (Path.home() / ".qdrant_collections", "Qdrant collections directory"),
        (Path.home() / ".code-indexer-data", "Global data directory"),
        (Path.home() / ".code-indexer-compose", "Docker compose directory"),
        (Path.home() / ".ollama_storage", "Ollama storage directory (if exists)"),
    ]

    sudo_needed = []

    for dir_path, description in directories:
        if not dir_path.exists():
            console.print(f"ℹ️  {description}: not found, skipping")
            continue

        try:
            console.print(f"🗑️  Removing {description}...")
            shutil.rmtree(dir_path)
            console.print(f"✅ Removed {description}")
        except PermissionError:
            console.print(
                f"🔒 {description}: permission denied, needs sudo", style="yellow"
            )
            sudo_needed.append((dir_path, description))
        except Exception as e:
            console.print(f"⚠️  Failed to remove {description}: {e}", style="yellow")

    # Handle directories that need sudo
    if sudo_needed:
        console.print("\n🔒 [bold yellow]SUDO REQUIRED[/bold yellow]")
        console.print(
            "The following directories need sudo to remove (root-owned files):"
        )

        for dir_path, description in sudo_needed:
            console.print(f"📁 {description}: {dir_path}")

        console.print("\n💡 [bold]Run this command to complete the cleanup:[/bold]")
        for dir_path, description in sudo_needed:
            console.print(f"sudo rm -rf {dir_path}")


def _check_remaining_root_files(console: Console):
    """Check for remaining root-owned files that need manual cleanup."""
    from pathlib import Path

    # Check current project's .code-indexer directory
    project_config_dir = Path(".code-indexer")
    sudo_needed = []

    if project_config_dir.exists():
        try:
            # Try to list and check ownership of files in the directory
            for item in project_config_dir.rglob("*"):
                try:
                    item_stat = item.stat()
                    if item_stat.st_uid == 0:  # Root owned
                        sudo_needed.append(item)
                except (OSError, PermissionError):
                    # If we can't stat it, it might be root-owned
                    sudo_needed.append(item)
        except (OSError, PermissionError):
            # If we can't access the directory at all, it's likely root-owned
            sudo_needed.append(project_config_dir)

    # Check for any other suspicious directories that might be root-owned
    suspicious_paths = [
        Path("~/.tmp").expanduser(),
        Path("/tmp").glob("code-indexer*"),
        Path("/var/tmp").glob("code-indexer*") if Path("/var/tmp").exists() else [],
    ]

    for path_or_glob in suspicious_paths:
        if hasattr(path_or_glob, "__iter__") and not isinstance(path_or_glob, Path):
            # It's a glob result
            for path in path_or_glob:
                if path.exists():
                    try:
                        path_stat = path.stat()
                        if path_stat.st_uid == 0:
                            sudo_needed.append(path)
                    except (OSError, PermissionError):
                        sudo_needed.append(path)
        elif isinstance(path_or_glob, Path) and path_or_glob.exists():
            try:
                path_stat = path_or_glob.stat()
                if path_stat.st_uid == 0:
                    sudo_needed.append(path_or_glob)
            except (OSError, PermissionError):
                sudo_needed.append(path_or_glob)

    if sudo_needed:
        console.print("🔒 [bold yellow]FOUND ROOT-OWNED FILES[/bold yellow]")
        console.print("The following files/directories need sudo to remove:")

        unique_paths = list(set(str(p) for p in sudo_needed))
        for path in unique_paths:
            console.print(f"📁 {path}")

        console.print("\n💡 [bold]Run these commands to complete the cleanup:[/bold]")
        for path in unique_paths:
            console.print(f"sudo rm -rf {path}")
    else:
        console.print("✅ No root-owned files found")


@cli.command()
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.option(
    "--wipe-all",
    is_flag=True,
    help="DANGEROUS: Perform complete system wipe including all containers, images, cache, and storage directories",
)
@click.pass_context
def uninstall(ctx, force_docker: bool, wipe_all: bool):
    """Completely remove all containers and data.

    \b
    STANDARD CLEANUP:
      • Stops and removes all Docker containers
      • Removes Docker volumes and networks
      • Clears all project data and configurations
      • Complete cleanup for fresh start

    \b
    WITH --wipe-all (DANGEROUS):
      • All standard cleanup operations above
      • Removes ALL container images (including cached builds)
      • Cleans container engine cache and build cache
      • Removes ~/.qdrant_collections directory
      • Removes ~/.code-indexer-data global directory
      • Removes ~/.code-indexer-compose directory
      • Performs aggressive system prune
      • May require sudo for permission-protected files

    \b
    WARNING:
      Standard: Removes all containers and data, requires restart.
      --wipe-all: NUCLEAR OPTION - removes everything including
      cached images, may affect other projects using same engine!

    \b
    USE CASES:
      • Standard: Normal uninstallation, switching providers
      • --wipe-all: Test environment cleanup, fixing deep corruption,
        resolving persistent container/permission issues
    """
    try:
        if wipe_all:
            _perform_complete_system_wipe(force_docker, console)
        else:
            # Standard uninstall
            docker_manager = DockerManager(force_docker=force_docker)

            # Remove containers and volumes completely
            if not docker_manager.remove_containers(remove_volumes=True):
                sys.exit(1)

            # Also clean data
            docker_manager.clean_data_only(all_projects=True)

            console.print("✅ Complete uninstallation finished", style="green")
            console.print("💡 Run 'code-indexer start' to reinstall", style="blue")

    except Exception as e:
        console.print(f"❌ Uninstall failed: {e}", style="red")
        sys.exit(1)


@cli.command("fix-config")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be fixed without making changes"
)
@click.option("--verbose", is_flag=True, help="Show detailed information about fixes")
@click.option("--force", is_flag=True, help="Apply fixes without confirmation prompts")
@click.pass_context
def fix_config(ctx, dry_run: bool, verbose: bool, force: bool):
    """Fix corrupted configuration files.

    \b
    Analyzes and repairs common configuration issues including:
      • JSON syntax errors (trailing commas, unquoted keys, etc.)
      • Incorrect paths pointing to temporary test directories
      • Wrong project names (e.g., "test-codebase" instead of actual name)
      • Outdated git information (branch, commit, availability)
      • Invalid file references from test data
      • Inconsistencies between config.json and metadata.json

    \b
    VALIDATION CHECKS:
      • Verifies codebase_dir points to parent of .code-indexer folder
      • Ensures project name matches actual directory name
      • Updates git state to match actual repository
      • Derives indexing statistics from Qdrant collections
      • Removes invalid file paths from metadata

    \b
    SAFETY FEATURES:
      • Creates backups before making changes
      • Validates JSON syntax before semantic fixes
      • Uses --dry-run to preview changes
      • Intelligent detection from actual file system state

    \b
    EXAMPLES:
      code-indexer fix-config --dry-run     # Preview fixes
      code-indexer fix-config --verbose     # Show detailed fix information
      code-indexer fix-config --force       # Apply without prompts

    \b
    COMMON USE CASES:
      • After running tests that corrupt configuration
      • When config points to wrong directories
      • When git information is outdated
      • When metadata contains test data
    """
    try:
        # Find configuration directory
        config_manager = ConfigManager.create_with_backtrack()
        if not config_manager:
            console.print(
                "❌ No configuration found. Run 'code-indexer init' first.", style="red"
            )
            sys.exit(1)

        config_dir = config_manager.config_path.parent

        console.print(
            f"🔧 {'Analyzing' if dry_run else 'Fixing'} configuration in {config_dir}"
        )

        if verbose:
            console.print(f"  📁 Config file: {config_manager.config_path}")
            console.print(f"  📄 Metadata file: {config_dir / 'metadata.json'}")

        # Initialize repairer
        repairer = ConfigurationRepairer(config_dir, dry_run=dry_run)

        # Run the fix process
        result = repairer.fix_configuration()

        # Generate and display report
        report = generate_fix_report(result, dry_run=dry_run)
        console.print(report)

        # Handle user confirmation for non-dry-run mode
        if not dry_run and result.fixes_applied and not force:
            if not click.confirm("\nDo you want to apply these fixes?"):
                console.print("❌ Configuration fix cancelled", style="yellow")
                sys.exit(0)

        # Show recommendations
        if result.success and result.fixes_applied and not dry_run:
            console.print("\n💡 Recommendations:")
            console.print("  • Run 'code-indexer status' to verify fixes")
            console.print(
                "  • Consider running 'code-indexer index' to rebuild with correct config"
            )

            if result.warnings:
                console.print(
                    "  • Review warnings above and consider cleaning up old collections"
                )

        if result.success:
            if dry_run:
                console.print(
                    "\n✨ Run without --dry-run to apply these fixes", style="blue"
                )
            else:
                console.print(
                    "\n✅ Configuration has been successfully fixed!", style="green"
                )
        else:
            sys.exit(1)

    except Exception as e:
        console.print(f"❌ Configuration fix failed: {e}", style="red")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def clean_legacy(ctx, force_docker: bool, yes: bool):
    """Migrate from legacy containers to Copy-on-Write architecture.

    This command performs a complete migration from legacy container setup
    to the new Copy-on-Write (CoW) architecture:

    \b
    1. Stops all containers
    2. Uses data-cleaner to completely wipe storage
    3. Starts containers with proper home directory mounting
    4. Enables CoW functionality for collections

    ⚠️  WARNING: This will remove all existing collections and require re-indexing.
    """
    console = Console()

    try:
        console.print("🔍 Checking legacy container status...", style="blue")

        # Check if we're in legacy mode
        is_legacy = asyncio.run(legacy_detector.check_legacy_container())

        if not is_legacy:
            console.print(
                "✅ No legacy containers detected - CoW architecture already active",
                style="green",
            )
            console.print(
                "\nℹ️  Your containers are already running with proper home directory mounting."
            )
            console.print(
                "   Collections will be stored locally with CoW functionality."
            )
            return

        console.print("⚠️  Legacy container detected", style="yellow")
        console.print("\nThis will:")
        console.print("  • Stop all containers")
        console.print("  • Completely wipe existing collection storage")
        console.print("  • Start containers with CoW architecture")
        console.print("  • Require re-indexing all projects")

        if not yes:
            console.print("\n❗ All existing collections will be lost!", style="red")
            if not click.confirm("Do you want to proceed with the migration?"):
                console.print("❌ Migration cancelled", style="yellow")
                return

        # Step 1: Stop containers
        console.print("\n🛑 Stopping containers...", style="blue")
        docker_manager = DockerManager(force_docker=force_docker)
        docker_manager.stop_services()
        console.print("✅ Containers stopped", style="green")

        # Step 2: Clean storage using existing clean functionality
        console.print("\n🧹 Cleaning legacy storage...", style="blue")

        # Use the existing clean_data_only functionality
        success = docker_manager.clean_data_only(all_projects=True)
        if not success:
            raise RuntimeError("Failed to clean legacy storage")

        console.print("✅ Legacy storage cleaned", style="green")

        # Step 3: Force remove containers and compose file
        console.print("\n🔧 Removing old containers and compose file...", style="blue")

        # Remove containers to force recreation with new mounts
        try:
            import subprocess

            subprocess.run(
                ["docker", "rm", "-f", "code-indexer-qdrant"],
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                ["docker", "rm", "-f", "code-indexer-data-cleaner"],
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                ["docker", "rm", "-f", "code-indexer-ollama"],
                capture_output=True,
                timeout=30,
            )
            console.print("✅ Old containers removed", style="green")
        except Exception as e:
            console.print(f"⚠️  Container removal had issues: {e}", style="yellow")

        # Remove old compose file to force regeneration
        if (
            hasattr(docker_manager, "compose_file")
            and docker_manager.compose_file.exists()
        ):
            docker_manager.compose_file.unlink()
            console.print("✅ Old compose file removed", style="green")

        # Step 4: Start containers with proper home mounting
        console.print("\n🚀 Creating containers with CoW architecture...", style="blue")

        # Start services - this will regenerate containers with home directory mounting
        docker_manager.start_services()

        # Verify services are running
        console.print("⏳ Waiting for services to be ready...", style="blue")

        # Give services time to start
        import time

        time.sleep(10)

        # Check if services are healthy - legacy function checking old container names
        # This should be removed in new mode only
        try:
            # Try to get project config if available
            if hasattr(docker_manager, "main_config") and docker_manager.main_config:
                project_config = docker_manager.main_config.get(
                    "project_containers", {}
                )
                if project_config:
                    qdrant_healthy = docker_manager._container_exists(
                        "qdrant", project_config
                    )
                else:
                    # Legacy container check - use legacy name directly
                    import subprocess

                    result = subprocess.run(
                        ["docker", "container", "inspect", "code-indexer-qdrant"],
                        capture_output=True,
                        timeout=5,
                    )
                    qdrant_healthy = result.returncode == 0
            else:
                # Legacy container check - use legacy name directly
                import subprocess

                result = subprocess.run(
                    ["docker", "container", "inspect", "code-indexer-qdrant"],
                    capture_output=True,
                    timeout=5,
                )
                qdrant_healthy = result.returncode == 0
        except Exception:
            qdrant_healthy = False
        if qdrant_healthy:
            console.print("✅ Qdrant service started successfully", style="green")
        else:
            console.print("⚠️  Qdrant service may still be starting", style="yellow")

        # Verify CoW architecture is active
        console.print("\n🔍 Verifying CoW architecture...", style="blue")
        is_legacy_after = asyncio.run(legacy_detector.check_legacy_container())

        if not is_legacy_after:
            console.print("✅ CoW architecture successfully activated!", style="green")
        else:
            console.print(
                "⚠️  CoW architecture verification failed - manual restart may be needed",
                style="yellow",
            )

        console.print("\n🎉 Migration completed successfully!", style="green")
        console.print("\nNext steps:")
        console.print(
            "  1. Run 'cidx index' in your projects to create local collections"
        )
        console.print("  2. Collections will be stored locally with CoW functionality")
        console.print("  3. Use 'cidx status' to verify local collection setup")

    except Exception as e:
        console.print(f"❌ Migration failed: {e}", style="red")
        console.print("\nYou may need to manually restart containers:")
        console.print("  cidx stop")
        console.print("  cidx start")
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
