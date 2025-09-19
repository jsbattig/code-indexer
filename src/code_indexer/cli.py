"""Command line interface for Code Indexer."""

import asyncio
import logging
import os
import subprocess
import sys
import signal
import time
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any, List

import click
from rich.console import Console
from rich.table import Table

# Rich progress imports removed - using MultiThreadedProgressManager instead

from .config import ConfigManager, Config
from .services import QdrantClient, DockerManager, EmbeddingProviderFactory
from .services.smart_indexer import SmartIndexer
from .services.generic_query_service import GenericQueryService
from .services.language_mapper import LanguageMapper
from .services.language_validator import LanguageValidator
from .services.claude_integration import (
    ClaudeIntegrationService,
    check_claude_sdk_availability,
)
from .services.config_fixer import ConfigurationRepairer, generate_fix_report
from .disabled_commands import get_command_mode_icons
from .utils.enhanced_messaging import (
    get_conflicting_flags_message,
    get_service_unavailable_message,
)
from .services.cidx_prompt_generator import create_cidx_ai_prompt
from .mode_detection.command_mode_detector import CommandModeDetector, find_project_root
from .disabled_commands import require_mode

# MultiThreadedProgressManager imported locally where needed

# CoW-related imports removed as part of CoW cleanup Epic
from . import __version__

logger = logging.getLogger(__name__)


def _generate_language_help_text() -> str:
    """Generate dynamic help text for language option based on LanguageMapper."""
    try:
        language_mapper = LanguageMapper()
        supported_languages = sorted(language_mapper.get_supported_languages())

        # Group languages for better readability
        programming = [
            lang
            for lang in supported_languages
            if lang
            in [
                "python",
                "javascript",
                "typescript",
                "java",
                "csharp",
                "cpp",
                "c",
                "go",
                "rust",
                "php",
                "ruby",
                "swift",
                "kotlin",
                "scala",
                "dart",
            ]
        ]
        web = [lang for lang in supported_languages if lang in ["html", "css", "vue"]]
        markup = [
            lang
            for lang in supported_languages
            if lang in ["markdown", "xml", "latex", "rst"]
        ]
        data = [
            lang
            for lang in supported_languages
            if lang in ["json", "yaml", "toml", "ini", "sql", "csv"]
        ]
        shell = [
            lang
            for lang in supported_languages
            if lang in ["shell", "bash", "powershell", "batch"]
        ]
        other = [
            lang
            for lang in supported_languages
            if lang not in programming + web + markup + data + shell
        ]

        help_parts = []
        help_parts.append("Filter by programming language or file extension.")
        help_parts.append("Supported friendly names:")

        if programming:
            help_parts.append(f"Programming: {', '.join(programming)}")
        if web:
            help_parts.append(f"Web: {', '.join(web)}")
        if markup:
            help_parts.append(f"Markup: {', '.join(markup)}")
        if data:
            help_parts.append(f"Data: {', '.join(data)}")
        if shell:
            help_parts.append(f"Shell: {', '.join(shell)}")
        if other:
            help_parts.append(f"Other: {', '.join(other)}")

        help_parts.append(
            "You can also use file extensions directly (py, js, ts, etc.)"
        )

        return " ".join(help_parts)
    except Exception:
        # Fallback to static text if dynamic generation fails
        return "Filter by programming language. Supports both friendly names (python, javascript, etc.) and file extensions (py, js, etc.)"


def _create_default_override_file(project_dir: Path, force: bool = False) -> bool:
    """Create default .code-indexer-override.yaml file.

    Args:
        project_dir: Project root directory
        force: Overwrite existing file if True

    Returns:
        True if file was created, False if skipped
    """
    override_path = project_dir / ".code-indexer-override.yaml"

    # Don't overwrite existing file unless force is True
    if override_path.exists() and not force:
        return False

    default_content = """# Code-indexer override file
#
# This file allows you to override file inclusion/exclusion rules
# at the project level, with highest precedence over gitignore and config.
#
# Rules are applied in this order:
# 1. force_exclude_patterns (absolute exclusion, overrides everything)
# 2. force_include_patterns (overrides base exclusion)
# 3. Extension filtering (add_extensions, remove_extensions)
# 4. Directory filtering (add_exclude_dirs, add_include_dirs)
# 5. Base config and gitignore rules (lowest precedence)
#
# Patterns use gitignore syntax:
#   *.log        - matches all .log files
#   temp/        - matches temp directory
#   **/*.cache   - matches .cache files in any subdirectory
#   !important/  - negation (force include)

# Additional file extensions to index (beyond config defaults)
add_extensions: []

# File extensions to exclude (overrides config whitelist)  
remove_extensions: []

# Additional directories to exclude from indexing
add_exclude_dirs: []

# Additional directories to force include
add_include_dirs: []

# Force include files matching these patterns (overrides gitignore/config)
force_include_patterns: []

# Force exclude files matching these patterns (absolute exclusion)
force_exclude_patterns: []
"""

    override_path.write_text(default_content)
    return True


def _setup_global_registry(quiet: bool = False, test_access: bool = False) -> None:
    """Setup the global port registry with proper permissions.

    Args:
        quiet: Suppress non-essential output
        test_access: Also test registry access after setup

    Raises:
        SystemExit: If setup fails or access test fails
    """
    if not quiet:
        console.print("🔧 Setting up Code Indexer Global Port Registry", style="blue")

    registry_dir = "/var/lib/code-indexer/port-registry"
    if not quiet:
        console.print(f"Location: {registry_dir}")
        console.print()

    try:

        def setup_registry():
            """Setup the global port registry with proper permissions."""
            if not quiet:
                console.print("🔧 Using sudo for system-wide setup", style="blue")

            # Create the directory
            result = subprocess.run(
                ["sudo", "mkdir", "-p", registry_dir],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise Exception(
                    f"Cannot create directory {registry_dir}: {result.stderr}"
                )

            # Set permissions for multi-user access (world-writable without sticky bit)
            # The sticky bit can interfere with atomic file operations across users
            subprocess.run(["sudo", "chmod", "777", registry_dir], check=True)

            # Test write access (without sudo to verify regular users can access)
            test_file = Path(registry_dir) / "test-access"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except Exception:
                raise Exception(f"Cannot write to {registry_dir} (even after setup)")

            # Create subdirectories
            active_projects_dir = Path(registry_dir) / "active-projects"
            subprocess.run(
                ["sudo", "mkdir", "-p", str(active_projects_dir)],
                check=True,
            )

            # Set permissions on subdirectories (no sticky bit for atomic operations)
            subprocess.run(
                ["sudo", "chmod", "777", str(active_projects_dir)],
                check=True,
            )

            # Create initial files with proper ownership
            port_alloc_file = Path(registry_dir) / "port-allocations.json"
            registry_log_file = Path(registry_dir) / "registry.log"

            # Create files as root but with world-writable permissions
            subprocess.run(["sudo", "touch", str(port_alloc_file)], check=True)
            subprocess.run(["sudo", "touch", str(registry_log_file)], check=True)

            # Set permissions for multi-user access
            subprocess.run(["sudo", "chmod", "666", str(port_alloc_file)], check=True)
            subprocess.run(["sudo", "chmod", "666", str(registry_log_file)], check=True)

            # Initialize with empty JSON object
            subprocess.run(
                ["sudo", "tee", str(port_alloc_file)],
                input="{}",
                text=True,
                capture_output=True,
                check=True,
            )

            if not quiet:
                console.print("✅ Global port registry setup complete", style="green")

        # Run the setup
        setup_registry()

        # Test registry access if requested or if not quiet
        if test_access or not quiet:
            if not quiet:
                console.print("🔍 Testing registry access...", style="blue")
            test_file = Path(registry_dir) / "test-access-final"
            try:
                test_file.write_text("test")
                test_file.unlink()
                if not quiet:
                    console.print("✅ Registry access test passed", style="green")
            except Exception:
                console.print("❌ Registry access test failed", style="red")
                sys.exit(1)

        # Test registry functionality
        try:
            from .services.global_port_registry import GlobalPortRegistry

            GlobalPortRegistry()
            if not quiet:
                console.print(
                    "✅ Global port registry setup successful!", style="green"
                )
                console.print()
                console.print("Usage Instructions:", style="bold")
                console.print("==================")
                console.print("The global port registry is now configured for cidx.")
                console.print(
                    "All cidx commands will automatically coordinate port allocation."
                )
                console.print()
                console.print(f"Registry Location: {registry_dir}")
                console.print()
                console.print("Location Details:")
                console.print(
                    "  ✅ System location - optimal for multi-user access, persistent across reboots"
                )
                console.print()
                console.print(
                    "No further action required - cidx will handle everything automatically."
                )
        except Exception as setup_ex:
            console.print(
                f"❌ Registry still not accessible after setup: {setup_ex}",
                style="red",
            )
            sys.exit(1)

    except Exception as setup_ex:
        console.print(f"❌ Failed to setup global registry: {setup_ex}", style="red")
        console.print(
            "This command MUST be run with sudo access for proper system-wide setup",
            style="red",
        )
        sys.exit(1)


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

        return (time.time() - self.interrupt_time) >= self.cancellation_timeout

    def get_time_since_cancellation(self) -> float:
        """Get seconds since cancellation was requested."""
        if not self.interrupt_time:
            return 0.0

        return time.time() - self.interrupt_time


# Global console for rich output
console = Console()


class ModeAwareGroup(click.Group):
    """Custom Click Group that adds mode compatibility icons to command help."""

    def format_commands(self, ctx, formatter):
        """Format commands with mode compatibility icons."""
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None:
                continue

            # Get mode icons for this command
            icons = get_command_mode_icons(subcommand)

            # Get help text with much longer limit to avoid early truncation
            help_text = cmd.get_short_help_str(limit=120)

            commands.append((subcommand, icons, help_text))

        if commands:
            formatter.write_heading("Commands")

            # Custom formatting with fixed-width columns accounting for emoji width
            for cmd_name, icons, help_text in sorted(commands):
                # Emojis take 2 visual columns each, so adjust padding
                # Calculate visual width: each emoji = 2 chars, regular chars = 1 char
                emoji_count = icons.count("🌐") + icons.count("🐳")
                visual_width = len(icons) + emoji_count

                # Target total width for command part is 24 chars
                padding_needed = max(0, 24 - visual_width - len(cmd_name))

                formatted_line = (
                    f"  {icons} {cmd_name}{' ' * padding_needed} {help_text}"
                )
                formatter.write(formatted_line + "\n")

            formatter.write("\n")
            formatter.write("Legend: 🌐 Remote | 🐳 Local\n")


@click.group(invoke_without_command=True, cls=ModeAwareGroup)
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
      • chunking: Model-aware chunk sizes (voyage-code-3: 4096, nomic-embed-text: 2048)

      Exclusions also respect .gitignore patterns automatically.

    \b
    DATA MANAGEMENT:
      • Git-aware: Tracks branches, commits, and file changes
      • Project isolation: Each project gets its own collection
      • Storage: Vector data stored in .code-indexer/qdrant/ (per-project)
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

    # Configure logging to suppress noisy third-party messages
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("root").setLevel(logging.WARNING)

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
        project_root = find_project_root(start_dir)
    elif config:
        ctx.obj["config_manager"] = ConfigManager(Path(config))
        project_root = Path(
            config
        ).parent.parent  # Assume config is in .code-indexer/config.json
    else:
        # Always use backtracking by default to find config in parent directories
        ctx.obj["config_manager"] = ConfigManager.create_with_backtrack()
        project_root = find_project_root(Path.cwd())

    # Detect operational mode for command routing
    mode_detector = CommandModeDetector(project_root)
    detected_mode = mode_detector.detect_mode()

    # Store mode information in Click context for command routing
    ctx.obj["mode"] = detected_mode
    ctx.obj["project_root"] = project_root
    ctx.obj["mode_detector"] = mode_detector

    if verbose:
        console.print(f"🔍 Detected mode: {detected_mode}", style="dim")
        console.print(f"📁 Project root: {project_root}", style="dim")


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
@click.option(
    "--setup-global-registry",
    is_flag=True,
    help="Setup global port registry (requires sudo)",
)
@click.option(
    "--create-override-file",
    is_flag=True,
    help="Create .code-indexer-override.yaml file for project-level file filtering rules",
)
@click.option(
    "--qdrant-segment-size",
    type=int,
    default=100,
    help="Qdrant segment size in MB (default: 100MB for optimal performance)",
)
@click.option(
    "--remote",
    type=str,
    help="Initialize remote mode with server URL (e.g., https://cidx.example.com)",
)
@click.option(
    "--username",
    type=str,
    help="Username for remote server authentication",
)
@click.option(
    "--password",
    type=str,
    help="Password for remote server authentication",
)
@click.pass_context
def init(
    ctx,
    codebase_dir: Optional[str],
    force: bool,
    max_file_size: Optional[int],
    embedding_provider: str,
    voyage_model: str,
    interactive: bool,
    setup_global_registry: bool,
    create_override_file: bool,
    qdrant_segment_size: int,
    remote: Optional[str],
    username: Optional[str],
    password: Optional[str],
):
    """Initialize code indexing in current directory (OPTIONAL).

    \b
    Creates .code-indexer/config.json with project configuration.

    \b
    NOTE: This command is optional. If you skip init and run 'start' directly,
    a default configuration will be created automatically with Ollama provider
    and standard settings. Only use init if you want to customize settings.

    \b
    INITIALIZATION MODES:
      🏠 Local Mode (default): Creates local configuration with Ollama + Qdrant
      ☁️  Remote Mode: Connects to existing CIDX server (--remote option)

    \b
    CONFIGURATION OPTIONS:
      • Exclude directories: Edit exclude_dirs in config.json
      • File types: Modify file_extensions array
      • Size limits: Use --max-file-size or edit config.json
      • Chunking: Model-aware sizing (voyage-code-3: 4096, nomic-embed-text: 2048)

    \b
    DEFAULT EXCLUSIONS:
      node_modules, venv, __pycache__, .git, dist, build, target,
      .idea, .vscode, .gradle, bin, obj, coverage, .next, .nuxt

    \b
    EMBEDDING PROVIDERS:
      • ollama: Local AI models (default, no API key required)
      • voyage-ai: VoyageAI API (requires VOYAGE_API_KEY environment variable)

    \b
    QDRANT SEGMENT SIZE:
      Controls Qdrant storage segment size (default: 100MB for optimal performance):
      • 10MB: Git-friendly for small projects, faster indexing, more files
      • 50MB: Balanced approach for medium projects
      • 100MB: Default - optimal performance while staying Git-compatible
      • 200MB: Large repositories prioritizing search performance

    \b
    EXAMPLES:
      code-indexer init                                    # Basic initialization with Ollama
      code-indexer init --interactive                     # Interactive configuration
      code-indexer init --embedding-provider voyage-ai    # Use VoyageAI
      code-indexer init --voyage-model voyage-large-2     # Specify VoyageAI model
      code-indexer init --max-file-size 2000000          # 2MB file limit
      code-indexer init --qdrant-segment-size 50         # Git-friendly 50MB segments
      code-indexer init --qdrant-segment-size 200        # Large repos 200MB segments
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
    # Handle remote mode initialization
    if remote:
        if not username or not password:
            console.print(
                "❌ Remote initialization requires --username and --password",
                style="red",
            )
            console.print()
            console.print(
                "Usage: cidx init --remote <server-url> --username <user> --password <pass>"
            )
            console.print()
            console.print("Example:")
            console.print(
                "  cidx init --remote https://cidx.example.com --username john --password secret123"
            )
            sys.exit(1)

        # Import remote initialization functionality
        try:
            from .remote.initialization import initialize_remote_mode
            from .remote.exceptions import RemoteInitializationError

            # Determine target directory
            target_dir = Path(codebase_dir) if codebase_dir else Path.cwd()

            # Run remote initialization asynchronously
            try:
                asyncio.run(
                    initialize_remote_mode(
                        project_root=target_dir,
                        server_url=remote,
                        username=username,
                        password=password,
                        console=console,
                    )
                )
                sys.exit(0)

            except RemoteInitializationError as e:
                console.print(
                    f"❌ Remote initialization failed: {e.message}", style="red"
                )
                if e.details:
                    console.print(f"   Details: {e.details}", style="red")
                console.print()
                console.print(
                    "Please check your server URL, credentials, and network connectivity."
                )
                sys.exit(1)

        except ImportError as e:
            console.print("❌ Remote functionality not available", style="red")
            console.print(f"Import error: {e}")
            sys.exit(1)

    # For init command, always create config in current directory (or specified codebase_dir)
    # Don't use the CLI context's config_manager which may have found a parent config
    target_dir = Path(codebase_dir) if codebase_dir else Path.cwd()
    project_config_path = target_dir / ".code-indexer" / "config.json"
    config_manager = ConfigManager(project_config_path)

    # CRITICAL: Check global port registry writeability before proceeding
    try:
        from .services.global_port_registry import GlobalPortRegistry

        # This will test registry writeability during initialization
        GlobalPortRegistry()
        console.print("✅ Global port registry accessible")
    except Exception as e:
        if "Global port registry not accessible" in str(e):
            if setup_global_registry:
                _setup_global_registry(quiet=False, test_access=True)
            else:
                console.print("❌ Global port registry not accessible", style="red")
                console.print(
                    "📋 The global port registry requires write access to system directories.",
                    style="yellow",
                )
                console.print(
                    "🔧 Setup options (choose one):",
                    style="yellow",
                )
                console.print("")
                console.print("   cidx init --setup-global-registry", style="bold cyan")
                console.print("   cidx setup-global-registry", style="bold cyan")
                console.print("")
                console.print(
                    "   No manual setup required - use either command above.",
                    style="yellow",
                )
                console.print("")
                console.print(
                    "💡 This creates /var/lib/code-indexer/port-registry with proper permissions",
                    style="yellow",
                )
                console.print(
                    "   for multi-user port coordination across projects.",
                    style="yellow",
                )
                sys.exit(1)
        else:
            # Re-raise other registry errors
            raise

    # Check if config already exists
    if config_manager.config_path.exists() and not force:
        # Special case: if only --create-override-file is requested, allow it
        if create_override_file:
            # Load existing config and create override file
            config = config_manager.load()
            project_root = config.codebase_dir
            if _create_default_override_file(project_root, force=False):
                console.print(
                    "📝 Created .code-indexer-override.yaml for project-level file filtering"
                )
                console.print("✅ Override file created successfully")
            else:
                console.print("📝 Override file already exists, not overwriting")
                console.print("Use --force to overwrite existing override file")
            return
        else:
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

        # Create default config with relative path for CoW clone compatibility
        # Use "." for current directory to ensure CoW clones work without intervention
        config = Config(codebase_dir=Path("."))
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
        if max_file_size is not None:
            indexing_config = config.indexing.model_dump()
            indexing_config["max_file_size"] = max_file_size
            updates["indexing"] = indexing_config

        # Validate and process Qdrant segment size
        if qdrant_segment_size <= 0:
            console.print("❌ Qdrant segment size must be positive", style="red")
            sys.exit(1)

        # Convert MB to KB for internal storage and apply to configuration
        segment_size_kb = qdrant_segment_size * 1024
        if "qdrant" not in updates:
            updates["qdrant"] = config.qdrant.model_dump()

        # Ensure we have a dict type for mypy
        qdrant_config = updates["qdrant"]
        if isinstance(qdrant_config, dict):
            qdrant_config["max_segment_size_kb"] = segment_size_kb

        # Apply updates if any
        if updates:
            config = config_manager.update_config(**updates)

        # Save with documentation
        config_manager.save_with_documentation(config)

        # Create qdrant storage directory proactively during init to prevent race condition
        project_qdrant_dir = config.codebase_dir / ".code-indexer" / "qdrant"
        project_qdrant_dir.mkdir(parents=True, exist_ok=True)

        # Create override file (by default or if explicitly requested)
        project_root = config.codebase_dir
        if (
            create_override_file
            or not (project_root / ".code-indexer-override.yaml").exists()
        ):
            if _create_default_override_file(project_root, force=force):
                console.print(
                    "📝 Created .code-indexer-override.yaml for project-level file filtering"
                )

        # Create language mappings file (proactive creation during init)
        from .utils.yaml_utils import create_language_mappings_yaml

        language_mappings_created = create_language_mappings_yaml(
            config_manager.config_path.parent, force=force
        )

        if language_mappings_created:
            console.print(
                "📚 Created language-mappings.yaml for query language filtering"
            )

        console.print(f"✅ Initialized configuration at {config_manager.config_path}")
        console.print(
            f"📖 Documentation created at {config_manager.config_path.parent / 'README.md'}"
        )
        console.print(f"📁 Codebase directory: {config.codebase_dir}")
        console.print(f"📏 Max file size: {config.indexing.max_file_size:,} bytes")
        console.print(
            "📦 Chunking: Model-aware sizing (voyage-code-3: 4096, nomic-embed-text: 2048)"
        )

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
@require_mode("local")
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
      • Data: .code-indexer/ (per-project persistent storage)

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
            # Use relative path for CoW clone compatibility
            config = config_manager.create_default_config(Path("."))
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
        project_config_dir = config_manager.config_path.parent
        docker_manager = DockerManager(
            setup_console,
            force_docker=force_docker,
            project_config_dir=project_config_dir,
        )

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
    "--detect-deletions",
    is_flag=True,
    help="Detect and handle files deleted from filesystem but still in database (for standard indexing only; --reconcile includes this automatically)",
)
@click.option(
    "--rebuild-indexes",
    is_flag=True,
    help="Rebuild payload indexes for optimal performance",
)
@click.pass_context
@require_mode("local")
def index(
    ctx,
    clear: bool,
    reconcile: bool,
    batch_size: int,
    files_count_to_process: Optional[int],
    detect_deletions: bool,
    rebuild_indexes: bool,
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
        🔴 Server throttling - API rate limits detected, backing off automatically

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
      • Configure thread count in config.json: voyage_ai.parallel_requests

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
      Vector data stored in: .code-indexer/qdrant/ (per-project)
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
            provider_name = embedding_provider.get_provider_name().title()
            error_message = get_service_unavailable_message(provider_name, "cidx start")
            console.print(error_message, style="red")
            sys.exit(1)

        if not qdrant_client.health_check():
            error_message = get_service_unavailable_message("Qdrant", "cidx start")
            console.print(error_message, style="red")
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

        # Use config.json setting directly
        thread_count = config.voyage_ai.parallel_requests
        console.print(
            f"🧵 Vector calculation threads: {thread_count} (from config.json)"
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
        interrupt_handler = None

        # Initialize progress managers for rich display
        from .progress import MultiThreadedProgressManager
        from .progress.progress_display import RichLiveProgressManager

        # Create Rich Live progress manager for bottom-anchored display
        rich_live_manager = RichLiveProgressManager(console=console)
        progress_manager = MultiThreadedProgressManager(
            console=console,
            live_manager=rich_live_manager,
            max_slots=thread_count + 2,
        )

        # Connect slot tracker to progress manager for real-time slot display
        if hasattr(smart_indexer, "slot_tracker") and smart_indexer.slot_tracker:
            progress_manager.set_slot_tracker(smart_indexer.slot_tracker)

        display_initialized = False

        def show_setup_message(message: str):
            """Display setup/informational messages as scrolling cyan text."""
            rich_live_manager.handle_setup_message(message)

        def show_error_message(file_path, error_msg: str):
            """Display error messages appropriately based on context."""
            if ctx.obj["verbose"]:
                rich_live_manager.handle_error_message(file_path, error_msg)

        def update_file_progress_with_concurrent_files(
            current: int, total: int, info: str, concurrent_files=None
        ):
            """Update file processing with concurrent file tracking."""
            nonlocal display_initialized

            # Initialize Rich Live display on first call
            if not display_initialized:
                rich_live_manager.start_bottom_display()
                display_initialized = True

            # ALWAYS use MultiThreadedProgressManager - NO FALLBACKS
            # Parse progress info for metrics if available
            try:
                parts = info.split(" | ")
                if len(parts) >= 4:
                    files_per_second = float(parts[1].replace(" files/s", ""))
                    kb_per_second = float(parts[2].replace(" KB/s", ""))
                    threads_text = parts[3]
                    active_threads = (
                        int(threads_text.split()[0])
                        if threads_text.split()
                        else thread_count
                    )
                else:
                    files_per_second = 0.0
                    kb_per_second = 0.0
                    active_threads = thread_count
            except (ValueError, IndexError):
                files_per_second = 0.0
                kb_per_second = 0.0
                active_threads = thread_count

            # Get slot tracker from smart_indexer
            slot_tracker = None
            if hasattr(smart_indexer, "slot_tracker"):
                slot_tracker = smart_indexer.slot_tracker

            # Update MultiThreadedProgressManager with rich display
            # Use empty list for concurrent_files if not provided - display will handle it gracefully
            progress_manager.update_complete_state(
                current=current,
                total=total,
                files_per_second=files_per_second,
                kb_per_second=kb_per_second,
                active_threads=active_threads,
                concurrent_files=concurrent_files or [],
                slot_tracker=slot_tracker,
                info=info,  # Pass info for phase detection
            )

            # Get integrated display content (Rich Table) and update Rich Live bottom-anchored display
            rich_table = progress_manager.get_integrated_display()
            rich_live_manager.handle_progress_update(rich_table)

        def check_for_interruption():
            """Check if operation was interrupted and return signal."""
            if interrupt_handler and interrupt_handler.interrupted:
                return "INTERRUPT"
            return None

        def progress_callback(
            current,
            total,
            file_path,
            error=None,
            info=None,
            concurrent_files=None,
            slot_tracker=None,
        ):
            """Multi-threaded progress callback - uses Rich Live progress display."""
            # Check for interruption first
            interrupt_result = check_for_interruption()
            if interrupt_result:
                return interrupt_result

            # Handle setup messages (total=0)
            if info and total == 0:
                show_setup_message(info)
                return

            # Handle file progress (total>0) with cancellation status
            if total and total > 0 and info:
                # Add cancellation indicator to progress info if interrupted
                if interrupt_handler and interrupt_handler.interrupted:
                    cancellation_info = f"🛑 CANCELLING - {info}"
                    update_file_progress_with_concurrent_files(
                        current, total, cancellation_info, concurrent_files
                    )
                else:
                    update_file_progress_with_concurrent_files(
                        current, total, info, concurrent_files
                    )
                return

            # Show errors
            if error:
                show_error_message(file_path, error)
                return

            # Fallback: if somehow no display exists, just print info (should rarely happen)
            if info:
                show_setup_message(info)

        # Clean API for components to use directly (no magic parameters!)
        # Note: mypy doesn't like adding attributes to functions, but this works at runtime
        progress_callback.show_setup_message = show_setup_message  # type: ignore[attr-defined]
        progress_callback.update_file_progress = lambda current, total, info: (  # type: ignore[attr-defined]
            check_for_interruption()
            or update_file_progress_with_concurrent_files(current, total, info)
        )
        progress_callback.show_error_message = show_error_message  # type: ignore[attr-defined]
        progress_callback.check_for_interruption = check_for_interruption  # type: ignore[attr-defined]
        progress_callback.reset_progress_timers = (  # type: ignore[attr-defined]
            lambda: progress_manager.reset_progress_timers()
        )

        # Check for conflicting flags
        if clear and reconcile:
            error_message = get_conflicting_flags_message("--clear", "--reconcile")
            console.print(error_message, style="red")
            sys.exit(1)

        # Use graceful interrupt handling for the indexing operation
        operation_name = "Indexing"
        if reconcile:
            operation_name = "Reconciliation"
        elif clear:
            operation_name = "Full reindexing"

        # Initialize stats with default values to handle early cancellation
        stats = None

        try:
            with GracefulInterruptHandler(console, operation_name) as handler:
                interrupt_handler = handler

                # Get collection name for operations
                collection_name = qdrant_client.resolve_collection_name(
                    config, embedding_provider
                )

                # Handle rebuild indexes flag
                if rebuild_indexes:
                    if qdrant_client.rebuild_payload_indexes(collection_name):
                        console.print("Index rebuild completed successfully")
                    else:
                        console.print("Index rebuild failed - check logs for details")
                        sys.exit(1)
                    return

                # For non-clear operations, ensure payload indexes exist before indexing
                # For --clear operations, skip this since collection will be recreated fresh
                if not clear:
                    qdrant_client.ensure_payload_indexes(
                        collection_name, context="index"
                    )

                stats = smart_indexer.smart_index(
                    force_full=clear,
                    reconcile_with_database=reconcile,
                    batch_size=batch_size,
                    progress_callback=progress_callback,
                    safety_buffer_seconds=60,  # 1-minute safety buffer
                    files_count_to_process=files_count_to_process,
                    vector_thread_count=config.voyage_ai.parallel_requests,
                    detect_deletions=detect_deletions,
                )

                # Show final completion state (if not interrupted)
                if display_initialized and not handler.interrupted:
                    # Stop progress manager and Rich Live display before showing completion message
                    progress_manager.stop_progress()
                    rich_live_manager.stop_display()
                    console.print("\n✅ Completed")

        except Exception as e:
            # Clean up progress manager and Rich Live display before error message
            if display_initialized:
                progress_manager.stop_progress()
                rich_live_manager.stop_display()
            console.print(f"❌ Indexing failed: {e}", style="red")
            sys.exit(1)

        # Clean up progress manager and Rich Live display before completion summary
        if display_initialized:
            progress_manager.stop_progress()
            rich_live_manager.stop_display()

        # Show completion summary with throughput (if stats available)
        if stats is None:
            # Early cancellation before stats were initialized
            console.print("🛑 Operation cancelled before completion", style="yellow")
            return

        if getattr(stats, "cancelled", False):
            console.print("🛑 Indexing cancelled!", style="yellow")
            console.print("📄 Files processed before cancellation: ", end="")
            console.print(f"{stats.files_processed}", style="yellow")
            console.print("📦 Chunks indexed before cancellation: ", end="")
            console.print(f"{stats.chunks_created}", style="yellow")
            console.print(
                "💾 Progress saved - you can resume indexing later", style="blue"
            )
        else:
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
@click.pass_context
@require_mode("local")
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
        # Ensure payload indexes exist for watch indexing operations
        qdrant_client.ensure_payload_indexes(collection_name, context="index")

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
    "--language",
    help=_generate_language_help_text(),
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
@click.pass_context
@require_mode("local", "remote")
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
    REMOTE MODE REPOSITORY LINKING:
      • Remote mode requires git repository context
      • Uses repository linking to match local repository with remote server
      • Queries run against your specific repository and branch

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
    BASIC EXAMPLES:
      code-indexer query "user login"
      code-indexer query "database" --language python
      code-indexer query "test" --path */tests/* --limit 5
      code-indexer query "async" --min-score 0.8
      code-indexer query "function" --quiet  # Just score, path, and content

    Results show file paths, matched content, and similarity scores.
    """
    # Get mode information from context
    mode = ctx.obj.get("mode", "uninitialized")
    project_root = ctx.obj.get("project_root")

    # Handle uninitialized mode
    if mode == "uninitialized":
        console.print("❌ Repository not initialized for CIDX", style="red")
        console.print()
        console.print("To get started, choose one of these initialization options:")
        console.print()
        console.print("🏠 Local Mode (recommended for getting started):")
        console.print("   cidx init          # Initialize with local Ollama + Qdrant")
        console.print("   cidx start         # Start local services")
        console.print("   cidx index         # Index your codebase")
        console.print()
        console.print("☁️  Remote Mode (connect to existing CIDX server):")
        console.print(
            "   cidx init --remote <server-url> --username <user> --password <pass>"
        )
        console.print()
        console.print("For more help: cidx init --help")
        sys.exit(1)

    # Handle remote mode
    if mode == "remote":
        console.print(
            "🔗 Remote mode detected - executing query on remote server...",
            style="blue",
        )

        try:
            # Execute remote query with transparent repository linking
            from .remote.query_execution import execute_remote_query

            results = asyncio.run(
                execute_remote_query(
                    query_text=query,
                    limit=limit,
                    project_root=project_root,
                    language=language,
                    path=path,
                    min_score=min_score,
                    include_source=True,
                    accuracy=accuracy,
                )
            )

            if not results:
                console.print("No results found.", style="yellow")
                sys.exit(0)

            # Convert API client results to local format for display
            converted_results: List[Dict[str, Any]] = []
            for result in results:
                converted_result = {
                    "score": getattr(
                        result, "score", getattr(result, "similarity_score", 0.0)
                    ),
                    "payload": {
                        "path": result.file_path,
                        "language": getattr(result, "language", None),
                        "content": getattr(
                            result, "content", getattr(result, "code_snippet", "")
                        ),
                        "line_start": getattr(result, "line_start", result.line_number),
                        "line_end": getattr(result, "line_end", result.line_number + 1),
                    },
                }

                # Add staleness info if available (EnhancedQueryResultItem)
                if hasattr(result, "staleness_indicator"):
                    converted_result["staleness"] = {
                        "is_stale": result.is_stale,
                        "staleness_indicator": result.staleness_indicator,
                        "staleness_delta_seconds": result.staleness_delta_seconds,
                    }

                converted_results.append(converted_result)

            # Use existing display logic for local queries
            if not quiet:
                console.print(f"\n✅ Found {len(converted_results)} results:")
                console.print("=" * 80)

            # Display each result using existing logic
            for i, result in enumerate(converted_results, 1):
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

                # Get staleness info if available
                staleness_info = result.get("staleness", {})
                staleness_indicator = staleness_info.get("staleness_indicator", "")

                if quiet:
                    # Quiet mode - minimal output: score, staleness indicator, path with line numbers
                    if staleness_indicator:
                        console.print(
                            f"{score:.3f} {staleness_indicator} {file_path_with_lines}"
                        )
                    else:
                        console.print(f"{score:.3f} {file_path_with_lines}")
                    if content:
                        # Show content with line numbers
                        content_lines = content.split("\n")
                        if line_start is not None:
                            numbered_lines = []
                            for j, line in enumerate(content_lines):
                                line_num = line_start + j
                                numbered_lines.append(f"{line_num:3}: {line}")
                            content_with_line_numbers = "\n".join(numbered_lines)
                            console.print(content_with_line_numbers)
                        else:
                            console.print(content)
                else:
                    # Full display mode
                    header = f"[{i}] Score: {score:.3f}"
                    if staleness_indicator:
                        header += f" | {staleness_indicator}"
                    console.print(f"\n{header}")

                    console.print(f"File: {file_path_with_lines}")
                    if language != "unknown":
                        console.print(f"Language: {language}")

                    # Add staleness details in verbose mode
                    if staleness_info.get("staleness_delta_seconds") is not None:
                        delta_seconds = staleness_info["staleness_delta_seconds"]
                        if delta_seconds > 0:
                            delta_hours = delta_seconds / 3600
                            if delta_hours < 1:
                                delta_minutes = int(delta_seconds / 60)
                                staleness_detail = (
                                    f"Local file newer by {delta_minutes}m"
                                )
                            elif delta_hours < 24:
                                delta_hours_int = int(delta_hours)
                                staleness_detail = (
                                    f"Local file newer by {delta_hours_int}h"
                                )
                            else:
                                delta_days = int(delta_hours / 24)
                                staleness_detail = f"Local file newer by {delta_days}d"
                            console.print(f"Staleness: {staleness_detail}")

                    if content:
                        if not quiet:
                            console.print(f"Relevance: {score:.3f}/1.0")
                        console.print("Content:")
                        console.print("-" * 40)
                        console.print(content)
                        console.print("-" * 40)

        except Exception as e:
            import traceback

            traceback.print_exc()
            # Check for repository linking related errors and provide helpful guidance
            error_message = str(e).lower()

            if (
                "git repository" in error_message
                or "repository linking" in error_message
            ):
                console.print(
                    "❌ Remote query requires git repository context", style="red"
                )
                console.print()
                console.print(
                    "🔗 Remote mode uses repository linking to match your local repository"
                )
                console.print("   with indexed repositories on the remote CIDX server.")
                console.print()
                console.print("📋 To resolve this, choose one of these options:")
                console.print()
                console.print("1️⃣  Initialize git repository in current directory:")
                console.print("   git init")
                console.print("   git remote add origin <your-repository-url>")
                console.print()
                console.print(
                    "2️⃣  Clone existing repository that's indexed on remote server:"
                )
                console.print("   git clone <repository-url>")
                console.print("   cd <repository-name>")
                console.print('   cidx query "your search"')
                console.print()
                console.print(
                    "💡 Repository linking ensures you get results relevant to your"
                )
                console.print("   current codebase context and branch.")
            else:
                console.print(f"❌ Remote query failed: {e}", style="red")

            sys.exit(1)

        # Return early to avoid falling through to local mode execution
        return

    # Continue with local mode execution
    if not quiet:
        console.print(f"🔍 Executing local query in: {project_root}", style="dim")

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

        # Ensure payload indexes exist (read-only check for query operations)
        qdrant_client.ensure_payload_indexes(collection_name, context="query")

        # Get query embedding
        if not quiet:
            with console.status("Generating query embedding..."):
                query_embedding = embedding_provider.get_embedding(query)
        else:
            query_embedding = embedding_provider.get_embedding(query)

        # Build filter conditions for non-git path only
        filter_conditions: Dict[str, Any] = {}
        if language:
            # Validate language parameter
            language_validator = LanguageValidator()
            validation_result = language_validator.validate_language(language)

            if not validation_result.is_valid:
                click.echo(f"Error: {validation_result.error_message}", err=True)
                if validation_result.suggestions:
                    click.echo(
                        f"Suggestions: {', '.join(validation_result.suggestions)}",
                        err=True,
                    )
                raise click.ClickException(f"Invalid language: {language}")

            # For non-git path, handle language mapping
            language_mapper = LanguageMapper()
            language_filter = language_mapper.build_language_filter(language)
            filter_conditions["must"] = [language_filter]
        if path:
            filter_conditions.setdefault("must", []).append(
                {"key": "path", "match": {"text": path}}
            )

        # Check if project uses git-aware indexing
        from .services.git_topology_service import GitTopologyService

        # BranchAwareIndexer removed - using HighThroughputProcessor git-aware methods

        git_topology_service = GitTopologyService(config.codebase_dir)
        is_git_aware = git_topology_service.is_git_available()

        # Initialize query service based on project type
        if is_git_aware:
            # Use git-aware filtering for git projects
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
            # Try to get branch from git directly since we're in a git repository
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
            else:
                # Fallback to metadata if available
                try:
                    from code_indexer.services.progressive_metadata import (
                        ProgressiveMetadata,
                    )

                    metadata = ProgressiveMetadata(config.codebase_dir)
                    current_display_branch = metadata.get_current_branch_with_retry(
                        fallback="unknown"
                    )
                except Exception:
                    pass
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

            # Use branch-aware search with git filtering
            # Content is visible if it was indexed from current branch
            git_filter_conditions = {
                "must": [
                    # Match content from the current branch
                    {"key": "git_branch", "match": {"value": current_branch}},
                    # Ensure git is available (exclude non-git content)
                    {"key": "git_available", "match": {"value": True}},
                ],
            }

            # Add additional filters
            if language:
                language_mapper = LanguageMapper()
                language_filter = language_mapper.build_language_filter(language)
                git_filter_conditions["must"].append(language_filter)
            if path:
                git_filter_conditions["must"].append(
                    {"key": "path", "match": {"text": path}}
                )

            git_results: List[Dict[str, Any]] = qdrant_client.search(
                query_vector=query_embedding,
                filter_conditions=git_filter_conditions,
                limit=limit,
                collection_name=collection_name,
            )

            # Apply minimum score filtering (language and path already handled by Qdrant filters)
            if min_score:
                filtered_results = []
                for result in git_results:
                    # Filter by minimum score
                    if result.get("score", 0) >= min_score:
                        filtered_results.append(result)
                git_results = filtered_results
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
            git_results = query_service.filter_results_by_current_branch(raw_results)

        # Limit to requested number after filtering
        results = git_results[:limit]

        # Apply staleness detection to local query results
        if results:
            try:
                # Convert local results to QueryResultItem format for staleness detection
                from .api_clients.remote_query_client import QueryResultItem
                from .remote.staleness_detector import StalenessDetector

                query_result_items = []
                for result in results:
                    payload = result["payload"]

                    # Extract file metadata for staleness comparison
                    file_last_modified = payload.get("file_last_modified")
                    indexed_at = payload.get("indexed_at")

                    query_item = QueryResultItem(
                        score=result["score"],
                        file_path=payload.get("path", "unknown"),
                        line_start=payload.get("line_start", 1),
                        line_end=payload.get("line_end", 1),
                        content=payload.get("content", ""),
                        language=payload.get("language"),
                        file_last_modified=file_last_modified,
                        indexed_timestamp=indexed_at,
                    )
                    query_result_items.append(query_item)

                # Apply staleness detection in local mode
                staleness_detector = StalenessDetector()
                enhanced_results = staleness_detector.apply_staleness_detection(
                    query_result_items, project_root, mode="local"
                )

                # Convert enhanced results back to local format but preserve staleness info
                enhanced_local_results = []
                for enhanced in enhanced_results:
                    # Find corresponding original result
                    original = next(
                        r
                        for r in results
                        if r["payload"].get("path") == enhanced.file_path
                    )

                    # Add staleness metadata to the result
                    enhanced_result = original.copy()
                    enhanced_result["staleness"] = {
                        "is_stale": enhanced.is_stale,
                        "staleness_indicator": enhanced.staleness_indicator,
                        "staleness_delta_seconds": enhanced.staleness_delta_seconds,
                    }
                    enhanced_local_results.append(enhanced_result)

                # Replace results with staleness-enhanced results
                results = enhanced_local_results

            except Exception as e:
                # Graceful fallback - continue with original results if staleness detection fails
                if not quiet:
                    console.print(
                        f"⚠️  Staleness detection unavailable: {e}", style="dim yellow"
                    )

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

            # Staleness info (if available)
            staleness_info = result.get("staleness", {})
            staleness_indicator = staleness_info.get("staleness_indicator", "")

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
                # Quiet mode - minimal output: score, staleness, path with line numbers
                if staleness_indicator:
                    console.print(
                        f"{score:.3f} {staleness_indicator} {file_path_with_lines}"
                    )
                else:
                    console.print(f"{score:.3f} {file_path_with_lines}")
                if content:
                    # Show full content with line numbers in quiet mode (no truncation)
                    content_lines = content.split("\n")

                    # Add line number prefixes if we have line start info
                    if line_start is not None:
                        numbered_lines = []
                        for i, line in enumerate(content_lines):
                            line_num = line_start + i
                            numbered_lines.append(f"{line_num:3}: {line}")
                        content_with_line_numbers = "\n".join(numbered_lines)
                        console.print(content_with_line_numbers)
                    else:
                        console.print(content)
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

                # Add staleness indicator to header if available
                if staleness_indicator:
                    header += f" | {staleness_indicator}"

                console.print(f"\n[bold cyan]{header}[/bold cyan]")

                # Enhanced metadata display
                metadata_info = f"📏 Size: {file_size} bytes | 🕒 Indexed: {indexed_at}"

                # Add staleness details in verbose mode
                if staleness_info.get("staleness_delta_seconds") is not None:
                    delta_seconds = staleness_info["staleness_delta_seconds"]
                    if delta_seconds > 0:
                        delta_hours = delta_seconds / 3600
                        if delta_hours < 1:
                            delta_minutes = int(delta_seconds / 60)
                            staleness_detail = f"Local file newer by {delta_minutes}m"
                        elif delta_hours < 24:
                            delta_hours_int = int(delta_hours)
                            staleness_detail = f"Local file newer by {delta_hours_int}h"
                        else:
                            delta_days = int(delta_hours / 24)
                            staleness_detail = f"Local file newer by {delta_days}d"
                        metadata_info += f" | ⏰ Staleness: {staleness_detail}"

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

                # Note: Fixed-size chunking no longer provides semantic metadata

                # Content display with line numbers (full chunk, no truncation)
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

                    # Add line number prefixes to full content (no truncation)
                    content_lines = content.split("\n")

                    # Add line number prefixes if we have line start info
                    if line_start is not None:
                        numbered_lines = []
                        for i, line in enumerate(content_lines):
                            line_num = line_start + i
                            numbered_lines.append(f"{line_num:3}: {line}")
                        content_with_line_numbers = "\n".join(numbered_lines)
                    else:
                        content_with_line_numbers = content

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
    help=f"[RAG-first only] Filter initial search by programming language. {_generate_language_help_text()}",
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

            # Ensure payload indexes exist (read-only check for query operations)
            qdrant_client.ensure_payload_indexes(collection_name, context="query")

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
                # Apply language mapping for friendly names
                language_mapper = LanguageMapper()
                language_filter = language_mapper.build_language_filter(language)
                filter_conditions["must"] = [language_filter]
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
    """Show status of services and index (adapted for current mode).
    \b
    Displays comprehensive information about your code-indexer installation:
    \b
    LOCAL MODE:
      • Ollama: AI embedding service status
      • Qdrant: Vector database status
      • Docker containers: Running/stopped state
      • Project configuration details
      • Git repository information (if applicable)
      • Vector collection statistics
    \b
    REMOTE MODE:
      • Remote server connection status
      • Repository linking information
      • Connection health monitoring
      • Repository staleness analysis
      • Authentication status
    \b
    UNINITIALIZED MODE:
      • Configuration status
      • Getting started guidance
      • Initialization options
    \b
    The status display automatically adapts based on your current configuration."""
    mode = ctx.obj["mode"]
    project_root = ctx.obj["project_root"]

    if mode == "local":
        from .mode_specific_handlers import display_local_status

        display_local_status(project_root, force_docker)
    elif mode == "remote":
        from .mode_specific_handlers import display_remote_status

        asyncio.run(display_remote_status(project_root))
    else:  # uninitialized
        from .mode_specific_handlers import display_uninitialized_status

        display_uninitialized_status(project_root)


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
        project_config_dir = config_manager.config_path.parent
        docker_manager = DockerManager(
            force_docker=force_docker, project_config_dir=project_config_dir
        )
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

                    # Check collection health before counting points
                    try:
                        collection_info = qdrant_client.get_collection_info(
                            collection_name
                        )
                        collection_status = collection_info.get("status", "unknown")

                        if collection_status == "red":
                            # Collection has errors - show error details
                            optimizer_status = collection_info.get(
                                "optimizer_status", {}
                            )
                            error_msg = optimizer_status.get("error", "Unknown error")

                            # Translate common errors to user-friendly messages
                            if "No such file or directory" in error_msg:
                                friendly_error = "Storage corruption detected - collection data is damaged"
                            elif "Permission denied" in error_msg:
                                friendly_error = (
                                    "Storage permission error - check file permissions"
                                )
                            elif "disk space" in error_msg.lower():
                                friendly_error = (
                                    "Insufficient disk space for collection operations"
                                )
                            else:
                                friendly_error = f"Collection error: {error_msg}"

                            qdrant_status = "❌ Collection Error"
                            qdrant_details = f"🚨 {friendly_error}"
                        elif collection_status == "yellow":
                            qdrant_status = "⚠️ Collection Warning"
                            qdrant_details = "Collection has warnings but is functional"
                        else:
                            # Collection is healthy, proceed with normal status
                            project_count = qdrant_client.count_points(collection_name)

                            # Get total documents across all collections for context
                            try:
                                import requests  # type: ignore[import-untyped]

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
                                        coll_count = qdrant_client.count_points(
                                            coll_name
                                        )
                                        total_count += coll_count
                                    qdrant_details = f"Project: {project_count} docs | Total: {total_count} docs"
                                else:
                                    qdrant_details = f"Documents: {project_count}"
                            except Exception:
                                qdrant_details = f"Documents: {project_count}"

                            # Add progressive metadata info if available and different from Qdrant count
                            try:
                                metadata_path = (
                                    config_manager.config_path.parent / "metadata.json"
                                )
                                if metadata_path.exists():
                                    import json

                                    with open(metadata_path) as f:
                                        metadata = json.load(f)
                                    files_processed = metadata.get("files_processed", 0)
                                    chunks_indexed = metadata.get("chunks_indexed", 0)
                                    status = metadata.get("status", "unknown")

                                    # Show progressive info if recent activity or if counts differ
                                    if files_processed > 0 and (
                                        status == "in_progress"
                                        or chunks_indexed != project_count
                                    ):
                                        qdrant_details += f" | Progress: {files_processed} files, {chunks_indexed} chunks"
                                        if status == "in_progress":
                                            qdrant_details += " (🔄 not complete)"
                            except Exception:
                                pass  # Don't fail status display if metadata reading fails
                    except Exception as e:
                        if "doesn't exist" in str(e):
                            qdrant_details = (
                                "Collection not found - run 'cidx index' to create"
                            )
                        else:
                            qdrant_details = (
                                f"Error checking collection: {str(e)[:50]}..."
                            )
                except Exception as e:
                    if "doesn't exist" in str(e):
                        qdrant_details = (
                            "Collection not found - run 'cidx index' to create"
                        )
                    else:
                        qdrant_details = f"Error: {str(e)[:50]}..."
            else:
                qdrant_details = "Service down"
        else:
            qdrant_status = "❌ Container not running"
            qdrant_details = "Qdrant container is not running"

        table.add_row("Qdrant", qdrant_status, qdrant_details)

        # Add payload index status - only if Qdrant is running and healthy
        if qdrant_ok and qdrant_client:
            try:
                embedding_provider = EmbeddingProviderFactory.create(config, console)
                collection_name = qdrant_client.resolve_collection_name(
                    config, embedding_provider
                )
                # Ensure payload indexes exist (silent for status operations)
                qdrant_client.ensure_payload_indexes(collection_name, context="status")
                payload_index_status = qdrant_client.get_payload_index_status(
                    collection_name
                )

                if payload_index_status.get("healthy", False):
                    payload_status = "✅ Healthy"
                    payload_details = (
                        f"{payload_index_status['total_indexes']} indexes active"
                    )
                else:
                    if "error" in payload_index_status:
                        payload_status = "❌ Error"
                        payload_details = (
                            f"Error: {payload_index_status['error'][:50]}..."
                        )
                    else:
                        payload_status = "⚠️ Issues"
                        missing = payload_index_status.get("missing_indexes", [])
                        if missing:
                            payload_details = f"Missing: {', '.join(missing)}"
                        else:
                            payload_details = f"{payload_index_status.get('total_indexes', 0)}/{payload_index_status.get('expected_indexes', 0)} indexes"

                table.add_row("Payload Indexes", payload_status, payload_details)
            except Exception as e:
                # Don't fail the entire status command if payload index check fails
                table.add_row(
                    "Payload Indexes", "❌ Error", f"Check failed: {str(e)[:40]}..."
                )

        # Add Qdrant storage and collection information
        try:
            # Get storage path from configuration instead of container inspection
            # Use the actual project-specific storage path from config
            project_qdrant_dir = (
                Path(config.codebase_dir).resolve() / ".code-indexer" / "qdrant"
            )
            table.add_row("Qdrant Storage", "📁", f"Host:\n{project_qdrant_dir}")

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

                        # Get local collection path - should be in project's .code-indexer/qdrant_collection/
                        project_root = config.codebase_dir
                        local_collection_path = (
                            project_root
                            / ".code-indexer"
                            / "qdrant_collection"
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
            import requests
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

                # Check if indexing is incomplete (regardless of whether it's running or stopped)
                has_incomplete_indexing = (
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

                if has_incomplete_indexing:
                    total_files = metadata.get(
                        "total_files_to_index", len(metadata.get("files_to_index", []))
                    )
                    files_processed = metadata.get("files_processed", 0)
                    remaining = max(
                        0, total_files - files_processed
                    )  # Ensure non-negative

                    if remaining > 0:
                        index_details += (
                            f" | 🔄 Not complete ({remaining} files remaining)"
                        )
                    else:
                        # Edge case: files_processed >= total files but status still in_progress
                        index_details += " | 🔄 Not complete (finishing up)"

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
        codebase_value = str(config.codebase_dir)
        config_value = str(config_manager.config_path)

        table.add_row("Codebase", "📁", codebase_value)
        table.add_row("Config", "⚙️", config_value)
        table.add_row(
            "File Limits",
            "📏",
            f"Max size: {config.indexing.max_file_size:,} bytes | Model-aware chunk sizing",
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
@require_mode("local")
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
        project_config_dir = config_path.parent
        docker_manager = DockerManager(
            console, force_docker=force_docker, project_config_dir=project_config_dir
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


@cli.command("clean-data")
@click.option(
    "--all-projects",
    is_flag=True,
    help="Clear data for all projects, not just current project",
)
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.option(
    "--all-containers",
    is_flag=True,
    help="Reset both Docker and Podman container sets",
)
@click.option(
    "--container-type",
    type=click.Choice(["docker", "podman"], case_sensitive=False),
    help="Target specific container type (docker|podman)",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output results in JSON format for automation",
)
@click.option(
    "--verify",
    is_flag=True,
    help="Verify reset operations succeeded",
)
@click.pass_context
def clean_data(
    ctx,
    all_projects: bool,
    force_docker: bool,
    all_containers: bool,
    container_type: str,
    json_output: bool,
    verify: bool,
):
    """Clear project data without stopping containers.

    \b
    Removes indexed data and configuration while keeping containers
    running for fast restart. Use this between tests or when switching projects.
    Supports dual-container architecture with Docker and Podman.

    \b
    WHAT IT DOES:
      • Clears Qdrant collections (current project or all projects)
      • Removes local cache directories
      • Keeps containers running for fast restart
      • Preserves container state and networks
      • Supports targeting specific container types

    \b
    CONTAINER OPTIONS:
      --all-containers       Reset both Docker and Podman sets
      --container-type TYPE  Target specific container type (docker|podman)
      (default)              Use legacy DockerManager behavior

    \b
    DATA OPTIONS:
      --all-projects         Clear data for all projects
      --verify               Verify reset operations succeeded
      --json                 Output results in JSON format

    \b
    PERFORMANCE:
      This is much faster than 'uninstall' since containers stay running.
      Perfect for test cleanup and project switching.
    """
    try:
        # Validate mutually exclusive options
        if all_containers and container_type:
            console.print(
                "❌ Cannot use --all-containers with --container-type", style="red"
            )
            console.print(
                "💡 Use either --all-containers OR --container-type", style="yellow"
            )
            sys.exit(1)

        # Use configuration from CLI context
        config_manager = ctx.obj["config_manager"]
        project_config_dir = config_manager.config_path.parent

        # Initialize result structure for JSON output
        from typing import Dict, Any

        result: Dict[str, Any] = {
            "success": False,
            "containers_processed": [],
            "collections_reset": [],
            "cache_cleared": False,
            "errors": [],
        }

        # Use dual-container mode if new options are specified
        if all_containers or container_type:
            from .services.container_manager import ContainerManager, ContainerType

            container_manager = ContainerManager(
                dual_container_mode=True, console=console
            )

            # Determine which container types to reset
            if all_containers:
                target_types = [ContainerType.DOCKER, ContainerType.PODMAN]
                console.print(
                    "🔄 Resetting both Docker and Podman container sets", style="blue"
                )
            else:
                target_type = (
                    ContainerType.DOCKER
                    if container_type.lower() == "docker"
                    else ContainerType.PODMAN
                )
                target_types = [target_type]
                console.print(
                    f"🔄 Resetting {container_type} container set", style="blue"
                )

            # Process each container type
            success = True
            for container_type_enum in target_types:
                try:
                    # Check if containers are available (graceful handling)
                    is_available = container_manager.verify_container_health(
                        container_type_enum
                    )
                    if not is_available:
                        console.print(
                            f"⚠️  {container_type_enum.value} containers not running, skipping",
                            style="yellow",
                        )
                        result["containers_processed"].append(
                            {
                                "type": container_type_enum.value,
                                "status": "skipped",
                                "reason": "containers not running",
                            }
                        )
                        continue

                    # Reset collections with verification if requested
                    if verify:
                        # This method doesn't exist yet - will be implemented
                        reset_success = (
                            container_manager.reset_collections_with_verification(
                                container_type_enum
                            )
                        )
                    else:
                        reset_success = container_manager.reset_collections(
                            container_type_enum
                        )

                    if reset_success:
                        console.print(
                            f"✅ {container_type_enum.value} container data reset successfully",
                            style="green",
                        )
                        result["containers_processed"].append(
                            {"type": container_type_enum.value, "status": "success"}
                        )
                    else:
                        console.print(
                            f"❌ Failed to reset {container_type_enum.value} container data",
                            style="red",
                        )
                        result["errors"].append(
                            f"Failed to reset {container_type_enum.value} containers"
                        )
                        success = False

                except Exception as e:
                    console.print(
                        f"❌ Error processing {container_type_enum.value}: {e}",
                        style="red",
                    )
                    result["errors"].append(
                        f"Error processing {container_type_enum.value}: {str(e)}"
                    )
                    success = False

            result["success"] = success

        else:
            # Use legacy DockerManager approach
            docker_manager = DockerManager(
                force_docker=force_docker, project_config_dir=project_config_dir
            )

            success = docker_manager.clean_data_only(all_projects=all_projects)
            result["success"] = success
            result["containers_processed"].append(
                {
                    "type": "docker" if force_docker else "auto-detected",
                    "status": "success" if success else "failed",
                }
            )

            if not success:
                result["errors"].append("Legacy DockerManager clean_data_only failed")

        # Output results
        if json_output:
            import json

            console.print(json.dumps(result, indent=2))
        elif not result["success"]:
            sys.exit(1)

    except Exception as e:
        if json_output:
            import json

            error_result = {
                "success": False,
                "error": str(e),
                "containers_processed": [],
                "collections_reset": [],
                "cache_cleared": False,
                "errors": [str(e)],
            }
            console.print(json.dumps(error_result, indent=2))
        else:
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

    # Step 1: Enhanced cleanup first
    console.print("\n🔧 [bold]Step 1: Enhanced container cleanup[/bold]")
    try:
        # System wipe operates on current working directory
        project_config_dir = Path(".code-indexer")
        docker_manager = DockerManager(
            force_docker=force_docker, project_config_dir=project_config_dir
        )
        if not docker_manager.cleanup(remove_data=True, verbose=True):
            console.print(
                "⚠️  Enhanced cleanup had issues, continuing with wipe...",
                style="yellow",
            )
        docker_manager.clean_data_only(all_projects=True)
        console.print("✅ Enhanced cleanup completed")
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
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def uninstall(ctx, force_docker: bool, wipe_all: bool, confirm: bool):
    """Uninstall CIDX configuration (mode-specific behavior).

    \b
    LOCAL MODE - STANDARD CLEANUP:
      • Uses data-cleaner container to remove root-owned files
      • Orchestrated shutdown: stops qdrant/ollama → cleans data → removes containers
      • Removes current project's .code-indexer directory and qdrant storage
      • Removes ollama model cache when applicable
      • Removes project-specific Docker volumes and networks
      • Complete cleanup for fresh start with proper permission handling

    \b
    LOCAL MODE - WITH --wipe-all (DANGEROUS):
      • All standard cleanup operations above
      • Removes ALL container images (including cached builds)
      • Cleans container engine cache and build cache
      • Removes ~/.qdrant_collections directory (shared CoW collections)
      • Removes ~/.code-indexer-data global directory (if exists)
      • Removes any remaining global storage directories
      • Performs aggressive system prune
      • May require sudo for permission-protected files

    \b
    REMOTE MODE:
      • Safely removes remote configuration and encrypted credentials
      • Preserves local project files and directory structure
      • Clears repository linking information
      • Provides guidance for re-initialization

    \b
    The uninstall behavior automatically adapts based on your current configuration.
    """
    mode = ctx.obj["mode"]
    project_root = ctx.obj["project_root"]

    if mode == "local":
        from .mode_specific_handlers import uninstall_local_mode

        uninstall_local_mode(project_root, force_docker, wipe_all)
    elif mode == "remote":
        from .mode_specific_handlers import uninstall_remote_mode

        uninstall_remote_mode(project_root, confirm)
    else:  # uninitialized
        console.print("⚠️  No configuration found to uninstall.", style="yellow")
        console.print(
            "💡 Use 'cidx init' to initialize a new configuration.", style="blue"
        )


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
        # Use configuration from CLI context
        config_manager = ctx.obj["config_manager"]
        if not config_manager or not config_manager.config_path.exists():
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


@cli.command("set-claude-prompt")
@click.option(
    "--user-prompt",
    is_flag=True,
    help="Set prompt in user's global ~/.claude/CLAUDE.md file instead of project file",
)
@click.option(
    "--show-only",
    is_flag=True,
    help="Display the generated prompt content without modifying any files",
)
@click.pass_context
def set_claude_prompt(ctx, user_prompt: bool, show_only: bool):
    """Set CIDX semantic search instructions in CLAUDE.md files.

    This command injects comprehensive CIDX semantic search instructions into
    CLAUDE.md files to improve Claude Code integration with code-indexer.

    \b
    BEHAVIOR:
    • --user-prompt: Sets prompt in ~/.claude/CLAUDE.md (global for all projects)
    • --show-only: Displays prompt content without modifying files
    • Default: Sets prompt in project CLAUDE.md (walks up directory tree to find it)

    \b
    FEATURES:
    • Detects existing CIDX sections and replaces them (no duplicates)
    • Preserves existing file content and formatting
    • Normalizes line endings to LF (Unix style)
    • Uses current project context to generate relevant instructions

    \b
    EXAMPLES:
      cidx set-claude-prompt                 # Set in project CLAUDE.md
      cidx set-claude-prompt --user-prompt  # Set in user's global CLAUDE.md
      cidx set-claude-prompt --show-only    # Display content without writing files

    \b
    REQUIREMENTS:
    • For project mode: CLAUDE.md must exist in current directory or parent directories
    • For user mode: ~/.claude/ directory will be created if needed
    • For show-only mode: No file requirements
    """
    from .services.claude_prompt_setter import ClaudePromptSetter

    try:
        # Check for conflicting flags
        if show_only and user_prompt:
            console.print("❌ Cannot use --show-only with --user-prompt", style="red")
            console.print(
                "   --show-only displays content without specifying target file",
                style="dim",
            )
            sys.exit(1)

        # Get current directory for codebase context
        current_dir = Path.cwd()
        setter = ClaudePromptSetter(current_dir)

        # Handle --show-only mode
        if show_only:
            console.print("📖 Generated CIDX prompt content:\n", style="blue")
            prompt_content = setter._generate_cidx_prompt()

            # Add section header as it would appear in CLAUDE.md
            section_header = "- CIDX SEMANTIC CODE SEARCH INTEGRATION\n\n"
            full_content = section_header + prompt_content

            # Display with syntax highlighting for better readability
            from rich.syntax import Syntax

            syntax = Syntax(
                full_content, "markdown", theme="github-dark", line_numbers=False
            )
            console.print(syntax)
            return

        if user_prompt:
            # Set in user's global CLAUDE.md
            console.print("🔧 Setting CIDX prompt in user's global CLAUDE.md...")
            success = setter.set_user_prompt()

            if success:
                user_file = Path.home() / ".claude" / "CLAUDE.md"
                console.print(f"✅ CIDX prompt set in: {user_file}", style="green")
                console.print(
                    "   This will apply to all your Claude Code sessions globally.",
                    style="dim",
                )
            else:
                console.print("❌ Failed to set user prompt", style="red")
                sys.exit(1)
        else:
            # Set in project CLAUDE.md
            console.print("🔧 Searching for project CLAUDE.md file...")
            success = setter.set_project_prompt(current_dir)

            if success:
                # Find which file was updated for user feedback
                project_file = setter._find_project_claude_file(current_dir)
                console.print(f"✅ CIDX prompt set in: {project_file}", style="green")
                console.print(
                    "   This will apply to Claude Code sessions in this project.",
                    style="dim",
                )
            else:
                console.print("❌ No project CLAUDE.md file found", style="red")
                console.print(
                    "   Searched up directory tree from current location.", style="dim"
                )
                console.print(
                    "   Create a CLAUDE.md file first, or use --user-prompt for global setting.",
                    style="dim",
                )
                sys.exit(1)

        # Show next steps
        console.print("\n💡 Next steps:", style="blue")
        console.print(
            "   • The CIDX semantic search instructions are now available to Claude"
        )
        console.print(
            "   • Claude will use 'cidx query' for intelligent code discovery"
        )
        console.print(
            "   • Test with: claude 'How does authentication work in this codebase?'"
        )

    except Exception as e:
        console.print(f"❌ Error setting Claude prompt: {e}", style="red")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@cli.command("setup-global-registry")
@click.option(
    "--test-access",
    is_flag=True,
    help="Test registry access after setup",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Suppress non-essential output",
)
@click.pass_context
def setup_global_registry(ctx, test_access: bool, quiet: bool):
    """Setup global port registry (requires sudo).

    Sets up the global port registry at /var/lib/code-indexer/port-registry
    with proper permissions for multi-user access. This is a standalone
    command that only sets up the registry without initializing any project.

    \b
    REQUIREMENTS:
    • Must be run with sudo access for proper system-wide setup
    • Creates /var/lib/code-indexer/port-registry directory structure
    • Sets appropriate permissions for multi-user access

    \b
    WHAT IT CREATES:
    • /var/lib/code-indexer/port-registry/ (main directory)
    • /var/lib/code-indexer/port-registry/port-allocations.json
    • /var/lib/code-indexer/port-registry/registry.log
    • /var/lib/code-indexer/port-registry/active-projects/

    \b
    EXAMPLES:
      sudo cidx setup-global-registry                    # Setup with full output
      sudo cidx setup-global-registry --quiet            # Setup with minimal output
      sudo cidx setup-global-registry --test-access      # Setup and test access

    \b
    NOTE:
    This command does NOT initialize any project. Use 'cidx init' if you
    need to set up a project configuration. The registry setup is global
    and only needs to be done once per system.
    """
    try:
        # Clean up any accidentally created project directories since this is a global command
        current_dir = Path.cwd()
        accidental_config = current_dir / ".code-indexer"
        if accidental_config.exists():
            # Only remove if it's empty (likely created accidentally by ConfigManager)
            try:
                accidental_config.rmdir()  # Only works if directory is empty
            except OSError:
                pass  # Directory not empty, leave it alone

        _setup_global_registry(quiet=quiet, test_access=test_access)
    except Exception as e:
        if not quiet:
            console.print(f"❌ Setup failed: {e}", style="red")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@cli.command("install-server")
@click.option(
    "--port",
    type=int,
    help="Preferred port for server (will find next available if busy)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Reinstall even if already installed",
)
@click.pass_context
def install_server(ctx, port: Optional[int], force: bool):
    """Install and configure CIDX multi-user server.

    Sets up the CIDX multi-user server with JWT authentication, role-based
    access control, and creates the necessary directory structure and startup scripts.

    \b
    INSTALLATION PROCESS:
    • Creates ~/.cidx-server/ directory structure
    • Finds available port starting from 8090 (or --port if specified)
    • Generates server configuration (config.json)
    • Creates executable startup script (start-server.sh)
    • Seeds initial admin user (admin/admin)
    • Displays startup instructions

    \b
    WHAT IT CREATES:
    • ~/.cidx-server/config.json           # Server configuration
    • ~/.cidx-server/users.json            # User database with hashed passwords
    • ~/.cidx-server/logs/                 # Server logs directory
    • ~/.cidx-server/start-server.sh       # Executable startup script

    \b
    DEFAULT CONFIGURATION:
    • JWT tokens: 10-minute expiration, extend on API activity
    • User roles: admin, power_user, normal_user
    • Max golden repos: 20 system-wide
    • Max concurrent queries: 5 per repository
    • Repository idle timeout: 10 minutes

    \b
    INITIAL CREDENTIALS:
    Username: admin
    Password: admin
    Role: admin (full access to all features)

    \b
    STARTING THE SERVER:
    After installation, start the server with:
      ~/.cidx-server/start-server.sh

    Or manually:
      python -m code_indexer.server.main --port <allocated-port>

    \b
    API DOCUMENTATION:
    Once running, access Swagger UI at: http://localhost:<port>/docs

    \b
    EXAMPLES:
      cidx install-server                    # Install with auto port allocation
      cidx install-server --port 8080       # Try specific port first
      cidx install-server --force           # Reinstall over existing installation

    \b
    NOTE:
    The server runs in console mode (blocking) and requires Ctrl+C to stop.
    All user passwords are securely hashed using bcrypt.
    """
    from .server.installer import ServerInstaller

    try:
        # Initialize installer
        base_port = port if port else 8090
        installer = ServerInstaller(base_port=base_port)

        # Check existing installation
        install_info = installer.get_installation_info()

        if install_info.get("installed") and not force:
            console.print("🔍 Checking existing installation...", style="cyan")

            if install_info.get("configured"):
                existing_port = install_info.get("port")
                console.print(
                    "✅ CIDX Server is already installed!", style="green bold"
                )
                console.print(
                    f"📂 Server directory: {installer.server_dir}", style="dim"
                )
                console.print(f"🌐 Configured port: {existing_port}", style="dim")
                console.print(
                    f"⏰ Installed: {install_info.get('installation_time', 'Unknown')}",
                    style="dim",
                )
                console.print()
                console.print("🚀 To start the server:", style="cyan bold")
                console.print(
                    f"   {installer.server_dir / 'start-server.sh'}", style="white"
                )
                console.print()
                console.print(
                    "📚 API Documentation will be available at:", style="cyan bold"
                )
                console.print(
                    f"   http://127.0.0.1:{existing_port}/docs", style="white"
                )
                console.print()
                console.print("💡 Use --force to reinstall", style="dim yellow")
                return
            else:
                console.print(
                    "⚠️  Installation directory exists but is incomplete", style="yellow"
                )
                console.print(
                    "🔧 Proceeding with installation to fix configuration...",
                    style="cyan",
                )

        if force and install_info.get("installed"):
            console.print(
                "🔄 Reinstalling CIDX Server (--force specified)...", style="yellow"
            )
        else:
            console.print("🚀 Installing CIDX Server...", style="cyan bold")

        console.print()

        # Perform installation
        with console.status("⚙️  Setting up server installation..."):
            allocated_port, config_path, script_path, is_new = installer.install()

        # Display success message
        console.print("✅ CIDX Server installed successfully!", style="green bold")
        console.print()

        # Installation details
        console.print("📋 Installation Details:", style="cyan bold")
        console.print(f"   📂 Server directory: {installer.server_dir}", style="white")
        console.print(f"   🌐 Allocated port: {allocated_port}", style="white")
        console.print(f"   ⚙️  Configuration: {config_path.name}", style="white")
        console.print(f"   🚀 Startup script: {script_path.name}", style="white")
        console.print()

        # Initial credentials
        console.print("🔑 Initial Admin Credentials:", style="cyan bold")
        console.print("   Username: admin", style="white")
        console.print("   Password: admin", style="white")
        console.print("   Role: admin (full access)", style="white")
        console.print()

        # Startup instructions
        console.print("🚀 Starting the Server:", style="cyan bold")
        console.print("   Run the startup script:", style="white")
        console.print(f"   {script_path}", style="green")
        console.print()
        console.print("   Or start manually:", style="white")
        console.print(
            f"   python -m code_indexer.server.main --port {allocated_port}",
            style="dim",
        )
        console.print()

        # API documentation
        console.print("📚 API Documentation:", style="cyan bold")
        console.print(
            f"   Swagger UI: http://127.0.0.1:{allocated_port}/docs", style="green"
        )
        console.print(
            f"   OpenAPI spec: http://127.0.0.1:{allocated_port}/openapi.json",
            style="dim",
        )
        console.print()

        # Security notes
        console.print("🔒 Security Notes:", style="yellow bold")
        console.print("   • Change admin password after first login", style="yellow")
        console.print(
            "   • JWT tokens expire in 10 minutes (extend on API activity)",
            style="yellow",
        )
        console.print(
            "   • All passwords are securely hashed with bcrypt", style="yellow"
        )
        console.print("   • Server runs on localhost only (127.0.0.1)", style="yellow")
        console.print()

        console.print(
            "🎉 Installation complete! Start the server to begin using CIDX multi-user features.",
            style="green bold",
        )

    except Exception as e:
        console.print(f"❌ Server installation failed: {e}", style="red")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@cli.command()
@click.argument("repository", required=False)
@click.option("--all", is_flag=True, help="Sync all activated repositories")
@click.option(
    "--full-reindex",
    is_flag=True,
    help="Force full re-indexing instead of incremental sync",
)
@click.option("--no-pull", is_flag=True, help="Skip git pull, only perform indexing")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be synced without executing"
)
@click.option(
    "--timeout", type=int, default=300, help="Job timeout in seconds (default: 300)"
)
@click.pass_context
@require_mode("remote")
def sync(
    ctx,
    repository: Optional[str],
    all: bool,
    full_reindex: bool,
    no_pull: bool,
    dry_run: bool,
    timeout: int,
):
    """Synchronize repositories with the remote CIDX server.

    \b
    Submits repository synchronization jobs to the remote server for processing.
    Supports both individual repository sync and bulk sync of all activated repositories.

    \b
    SYNC MODES:
      • Individual: cidx sync [repository-alias]     # Sync specific repository
      • Current:    cidx sync                        # Sync current repository
      • All repos:  cidx sync --all                  # Sync all activated repositories

    \b
    SYNC OPTIONS:
      • --full-reindex    Force complete re-indexing (slower but thorough)
      • --no-pull         Skip git pull, only index existing files
      • --dry-run         Preview what would be synced without execution
      • --timeout 600     Set job timeout (default: 300 seconds)

    \b
    EXAMPLES:
      cidx sync                           # Sync current repository
      cidx sync my-project               # Sync specific repository
      cidx sync --all                    # Sync all repositories
      cidx sync --full-reindex           # Force full re-indexing
      cidx sync --no-pull --dry-run      # Preview indexing without git pull
      cidx sync --all --timeout 600     # Sync all with extended timeout

    \b
    The sync command submits jobs to the server and tracks their progress.
    Use 'cidx query' after sync completion to search the updated index.
    """
    try:
        # Validate command line arguments
        if repository and all:
            console.print(
                "❌ Error: Cannot specify both repository and --all flag", style="red"
            )
            console.print(
                "   Use either 'cidx sync <repository>' or 'cidx sync --all'",
                style="dim",
            )
            sys.exit(1)

        if timeout <= 0:
            console.print("❌ Error: Timeout must be a positive number", style="red")
            sys.exit(1)

        # Import here to avoid circular imports
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.sync_execution import (
            execute_repository_sync,
            RemoteSyncExecutionError,
            RepositoryNotLinkedException,
        )
        from .remote.credential_manager import CredentialNotFoundError
        from .api_clients.base_client import AuthenticationError, NetworkError

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print(
                "   Run 'cidx init --remote <server-url> --username <user> --password <pass>' to set up remote mode",
                style="dim",
            )
            sys.exit(1)

        # Show sync operation details
        if dry_run:
            console.print(
                "🔍 Dry run mode - showing what would be synced:", style="blue"
            )
        else:
            console.print("🔄 Starting repository synchronization...", style="blue")

        if all:
            console.print("   Target: All activated repositories", style="dim")
        elif repository:
            console.print(f"   Target: {repository}", style="dim")
        else:
            console.print("   Target: Current repository", style="dim")

        sync_options = []
        if full_reindex:
            sync_options.append("full re-index")
        else:
            sync_options.append("incremental")

        if no_pull:
            sync_options.append("no git pull")
        else:
            sync_options.append("with git pull")

        console.print(f"   Options: {', '.join(sync_options)}", style="dim")
        console.print(f"   Timeout: {timeout} seconds", style="dim")

        # Setup progress display for polling if not in dry run mode
        progress_callback = None
        if not dry_run:
            from .progress.progress_display import RichLiveProgressManager

            # Create rich live manager for progress display
            rich_live_manager = RichLiveProgressManager(console=console)

            # Start progress display
            rich_live_manager.start_bottom_display()

            def sync_progress_callback(
                current, total, file_path, error=None, info=None, **kwargs
            ):
                """Progress callback for sync job polling."""
                try:
                    # Handle setup messages (total=0)
                    if total == 0 and info:
                        console.print(f"ℹ️ {info}", style="blue")
                        return

                    # Handle progress updates (total > 0)
                    if total and total > 0 and info:
                        console.print(info, style="cyan")

                except Exception as e:
                    # Don't let progress display errors break sync
                    logger.warning(f"Progress display error: {e}")

            progress_callback = sync_progress_callback

        try:
            # Execute sync
            results = asyncio.run(
                execute_repository_sync(
                    repository_alias=repository,
                    project_root=project_root,
                    sync_all=all,
                    full_reindex=full_reindex,
                    no_pull=no_pull,
                    dry_run=dry_run,
                    timeout=timeout,
                    enable_polling=not dry_run,
                    progress_callback=progress_callback,
                )
            )

        finally:
            # Clean up progress display
            if progress_callback:
                try:
                    rich_live_manager.stop_display()
                except Exception as e:
                    logger.warning(f"Error stopping progress display: {e}")

        # Display results
        if not results:
            console.print("ℹ️ No repositories to sync", style="yellow")
            sys.exit(0)

        console.print()
        if dry_run:
            console.print("📋 Dry run results:", style="blue bold")
        else:
            console.print("✅ Sync jobs submitted:", style="green bold")

        for result in results:
            if result.status == "would_sync":
                console.print(
                    f"   🔍 {result.repository}: {result.message}", style="blue"
                )
            elif result.status == "error":
                console.print(
                    f"   ❌ {result.repository}: {result.message}", style="red"
                )
            else:
                console.print(
                    f"   ✅ {result.repository}: {result.message}", style="green"
                )
                if result.job_id and not dry_run:
                    console.print(f"      Job ID: {result.job_id}", style="dim")
                if result.estimated_duration:
                    console.print(
                        f"      Estimated duration: {result.estimated_duration:.1f}s",
                        style="dim",
                    )

        if not dry_run:
            console.print()
            console.print("🔔 Sync jobs are processing on the server.", style="cyan")
            console.print(
                "   Use 'cidx query' to search the updated index after completion.",
                style="dim",
            )

    except RepositoryNotLinkedException as e:
        console.print(f"❌ Repository not linked: {e}", style="red")
        console.print(
            "   💡 Use 'cidx link' to link this repository to the remote server",
            style="dim",
        )
        sys.exit(1)
    except CredentialNotFoundError as e:
        console.print(f"❌ Authentication error: {e}", style="red")
        console.print(
            "   💡 Run 'cidx init --remote' to configure remote authentication",
            style="dim",
        )
        sys.exit(1)
    except AuthenticationError as e:
        console.print(f"❌ Authentication failed: {e}", style="red")
        console.print(
            "   💡 Check your credentials with 'cidx auth update'", style="dim"
        )
        sys.exit(1)
    except NetworkError as e:
        console.print(f"❌ Network error: {e}", style="red")
        console.print(
            "   💡 Check your internet connection and server URL", style="dim"
        )
        sys.exit(1)
    except RemoteSyncExecutionError as e:
        console.print(f"❌ Sync failed: {e}", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Unexpected error: {e}", style="red")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


# Authentication management commands
@cli.group("auth")
@click.pass_context
def auth_group(ctx):
    """Authentication commands for remote mode.

    Manage credentials and authentication for CIDX remote mode operations.
    """
    pass


@auth_group.command("update")
@click.option(
    "--username", required=True, help="New username for remote authentication"
)
@click.option(
    "--password", required=True, help="New password for remote authentication"
)
@click.pass_context
def auth_update(ctx, username: str, password: str):
    """Update remote credentials while preserving repository configuration.

    Updates authentication credentials for remote mode while preserving
    server URL, repository links, and all other settings.

    Example:
        cidx auth update --username newuser --password newpass
    """
    try:
        from code_indexer.remote.credential_rotation import CredentialRotationManager
        from code_indexer.mode_detection.command_mode_detector import find_project_root

        # Find project root and initialize rotation manager
        from pathlib import Path

        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        rotation_manager = CredentialRotationManager(project_root)

        with console.status("🔄 Updating credentials..."):
            success_message = rotation_manager.update_credentials(username, password)

        console.print(f"✅ {success_message}", style="green")
        console.print("🔑 Credentials have been updated and verified", style="cyan")

    except Exception as e:
        console.print(f"❌ Credential update failed: {e}", style="red")
        if "not in remote mode" in str(e):
            console.print(
                "💡 This command only works with remote mode projects", style="dim"
            )
        elif "Invalid credentials" in str(e):
            console.print(
                "💡 Check your username and password are correct", style="dim"
            )
        elif "No remote configuration" in str(e):
            console.print(
                "💡 Initialize remote mode first with appropriate setup", style="dim"
            )

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


# Server lifecycle management commands
@cli.group("server")
@click.pass_context
def server_group(ctx):
    """Manage CIDX multi-user server lifecycle.

    Control server start, stop, status, and restart operations with
    proper graceful shutdown and health monitoring.
    """
    pass


@server_group.command("start")
@click.option(
    "--server-dir",
    type=click.Path(),
    help="Server directory path (default: ~/.cidx-server)",
)
@click.pass_context
def server_start(ctx, server_dir: Optional[str]):
    """Start the CIDX multi-user server.

    Validates configuration, starts the FastAPI server process, and
    returns success confirmation with server URL.
    """
    try:
        from code_indexer.server.lifecycle.server_lifecycle_manager import (
            ServerLifecycleManager,
        )

        manager = ServerLifecycleManager(server_dir)
        result = manager.start_server()

        console.print("✅ " + result["message"], style="green bold")
        console.print(f"🌐 Server URL: {result['server_url']}", style="cyan")
        console.print(f"🔢 Process ID: {result['pid']}", style="dim")
        console.print()
        console.print("📚 API Documentation:", style="cyan")
        console.print(f"   {result['server_url']}/docs", style="white")

    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")
        if "already running" in str(e).lower():
            console.print(
                "💡 Use 'cidx server status' to check current status", style="dim"
            )
        elif "configuration" in str(e).lower():
            console.print(
                "💡 Use 'cidx install-server' to set up configuration", style="dim"
            )
        sys.exit(1)


@server_group.command("stop")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force shutdown (send SIGKILL instead of graceful SIGTERM)",
)
@click.option(
    "--server-dir",
    type=click.Path(),
    help="Server directory path (default: ~/.cidx-server)",
)
@click.pass_context
def server_stop(ctx, force: bool, server_dir: Optional[str]):
    """Stop the CIDX multi-user server gracefully.

    Performs graceful shutdown by default, waiting for background jobs
    to complete and saving pending data. Use --force for immediate shutdown.
    """
    try:
        from code_indexer.server.lifecycle.server_lifecycle_manager import (
            ServerLifecycleManager,
        )

        manager = ServerLifecycleManager(server_dir)
        result = manager.stop_server(force=force)

        console.print("✅ " + result["message"], style="green bold")
        if "shutdown_time" in result:
            console.print(
                f"⏱️ Shutdown time: {result['shutdown_time']:.1f}s", style="dim"
            )

    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")
        if "not running" in str(e).lower():
            console.print(
                "💡 Use 'cidx server status' to check current status", style="dim"
            )
        sys.exit(1)


@server_group.command("status")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed health information")
@click.option(
    "--server-dir",
    type=click.Path(),
    help="Server directory path (default: ~/.cidx-server)",
)
@click.pass_context
def server_status(ctx, verbose: bool, server_dir: Optional[str]):
    """Check CIDX multi-user server status and health.

    Shows server status, uptime, port, active jobs, and recent errors.
    Use --verbose for detailed health information including resource usage.
    """
    try:
        from code_indexer.server.lifecycle.server_lifecycle_manager import (
            ServerLifecycleManager,
        )

        manager = ServerLifecycleManager(server_dir)
        status = manager.get_status()

        # Status display
        status_color = "green" if status.status.value == "running" else "red"
        console.print(
            f"Status: {status.status.value.upper()}", style=f"{status_color} bold"
        )

        if status.status.value == "running":
            console.print(f"PID: {status.pid}", style="dim")
            if status.uptime:
                hours = status.uptime // 3600
                minutes = (status.uptime % 3600) // 60
                if hours > 0:
                    uptime_str = f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''}"
                else:
                    uptime_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                console.print(f"Uptime: {uptime_str}", style="dim")
            if status.port:
                console.print(f"Port: {status.port}", style="dim")
                console.print(f"Host: {status.host or '127.0.0.1'}", style="dim")
            console.print(f"Active Jobs: {status.active_jobs}", style="dim")

            # Verbose health information
            if verbose:
                try:
                    health = manager.get_server_health()
                    console.print()
                    console.print("📊 Health Information:", style="cyan bold")
                    console.print(
                        f"Health: {health.get('status', 'unknown')}", style="dim"
                    )
                    if "memory_usage" in health:
                        console.print(
                            f"Memory Usage: {health['memory_usage']}", style="dim"
                        )
                    if "recent_errors" in health:
                        errors = health["recent_errors"]
                        if errors:
                            console.print(
                                f"Recent Errors: {len(errors)}", style="yellow"
                            )
                        else:
                            console.print("Recent Errors: None", style="dim")
                except Exception:
                    console.print(
                        "Health: Unable to retrieve detailed health info",
                        style="yellow",
                    )

            sys.exit(0)  # Running = exit code 0
        else:
            console.print("The server is not currently running.", style="dim")
            sys.exit(1)  # Stopped = exit code 1

    except Exception as e:
        console.print(f"❌ Error checking server status: {str(e)}", style="red")
        sys.exit(1)


@server_group.command("restart")
@click.option(
    "--server-dir",
    type=click.Path(),
    help="Server directory path (default: ~/.cidx-server)",
)
@click.pass_context
def server_restart(ctx, server_dir: Optional[str]):
    """Restart the CIDX multi-user server.

    Gracefully stops the server if running, waits for proper shutdown,
    then starts with updated configuration. If not running, simply starts.
    """
    try:
        from code_indexer.server.lifecycle.server_lifecycle_manager import (
            ServerLifecycleManager,
        )

        manager = ServerLifecycleManager(server_dir)
        result = manager.restart_server()

        console.print("✅ " + result["message"], style="green bold")
        console.print(f"🌐 Server URL: {result['server_url']}", style="cyan")
        if "restart_time" in result:
            console.print(f"⏱️ Restart time: {result['restart_time']:.1f}s", style="dim")
        console.print()
        console.print("📚 API Documentation:", style="cyan")
        console.print(f"   {result['server_url']}/docs", style="white")

    except KeyboardInterrupt:
        console.print("\n❌ Operation cancelled by user", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")
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
