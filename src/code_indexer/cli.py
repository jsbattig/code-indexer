"""Command line interface for Code Indexer."""

import asyncio
import getpass
import json
import logging
import os
import subprocess
import sys
import signal
import time
import threading
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any, List

import click
from rich.console import Console
from rich.table import Table

# Rich progress imports removed - using MultiThreadedProgressManager instead

from .config import ConfigManager, Config
from .disabled_commands import get_command_mode_icons
from .utils.enhanced_messaging import (
    get_conflicting_flags_message,
    get_service_unavailable_message,
)
from .utils.exception_logger import ExceptionLogger
from .mode_detection.command_mode_detector import CommandModeDetector, find_project_root
from .disabled_commands import require_mode
from . import __version__

# Module-level imports for test mocking (noqa: F401 = intentionally unused for test patching)
from .api_clients.admin_client import AdminAPIClient  # noqa: F401
from .api_clients.repos_client import ReposAPIClient  # noqa: F401
from .backends.backend_factory import BackendFactory  # noqa: F401
from .services.embedding_factory import EmbeddingProviderFactory  # noqa: F401
from .services.docker_manager import DockerManager  # noqa: F401
from .services.qdrant import QdrantClient  # noqa: F401
from .remote.credential_manager import ProjectCredentialManager  # noqa: F401

# Daemon delegation imports (lazy loaded when daemon enabled)
from . import cli_daemon_delegation  # noqa: F401
from . import cli_daemon_lifecycle  # noqa: F401


def run_async(coro):
    """
    Run an async coroutine, handling both new event loops and existing ones.

    This utility is crucial for CLI commands that need to work both:
    1. In normal CLI usage (no event loop running)
    2. In test environments (event loop already running)

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        # Try to get the current event loop
        asyncio.get_running_loop()
        # If we get here, there's already a running loop
        # Create a new thread to run the coroutine

        result = None
        exception = None

        def run_in_new_loop():
            nonlocal result, exception
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result = new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            except Exception as e:
                exception = e

        thread = threading.Thread(target=run_in_new_loop)
        thread.start()
        thread.join()

        if exception:
            raise exception
        return result

    except RuntimeError:
        # No event loop running, we can use asyncio.run()
        return asyncio.run(coro)


# MultiThreadedProgressManager imported locally where needed

# CoW-related imports removed as part of CoW cleanup Epic

logger = logging.getLogger(__name__)


def _generate_language_help_text() -> str:
    """Generate dynamic help text for language option based on LanguageMapper."""
    try:
        from .services.language_mapper import LanguageMapper

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


def _needs_docker_manager(config):
    """Determine if DockerManager is needed based on backend type."""
    if hasattr(config, "vector_store") and config.vector_store:
        if hasattr(config.vector_store, "provider"):
            return config.vector_store.provider != "filesystem"
    return True  # Default to True for backward compatibility


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


def _display_query_timing(console: Console, timing_info: Dict[str, Any]) -> None:
    """Display query execution timing telemetry.

    Args:
        console: Rich console for output
        timing_info: Dictionary with timing data in milliseconds and metadata
    """
    if not timing_info:
        return

    console.print("\n⏱️  Query Timing:")
    console.print("-" * 60)

    # Calculate total time from high-level steps only (not breakdown components)
    # For parallel execution, use parallel_load_ms instead of embedding_ms + index_load_ms
    if "parallel_load_ms" in timing_info:
        # Parallel execution path (FilesystemVectorStore)
        high_level_steps = {
            "parallel_load_ms": "Parallel load (embedding + index)",
            "hnsw_search_ms": "Vector search",
            "git_filter_ms": "Git-aware filtering",
        }
    else:
        # Sequential execution path (QdrantClient or legacy)
        high_level_steps = {
            "embedding_ms": "Embedding generation",
            "vector_search_ms": "Vector search (total)",
            "git_filter_ms": "Git-aware filtering",
        }

    total_ms = sum(timing_info.get(key, 0) for key in high_level_steps.keys())

    # Prepare breakdown keys and labels (shown under parallel_load_ms or vector_search_ms)
    parallel_breakdown_keys = [
        "embedding_ms",  # Concurrent with index loading
        "index_load_ms",  # Concurrent with embedding
        "id_index_load_ms",  # Part of index loading
        "parallel_overhead_ms",  # Threading coordination overhead
    ]

    parallel_breakdown_labels = {
        "embedding_ms": "    ├─ Embedding generation (concurrent)",
        "index_load_ms": "    ├─ HNSW index load (concurrent)",
        "id_index_load_ms": "    ├─ ID index load (concurrent)",
        "parallel_overhead_ms": "    └─ Threading overhead",
    }

    search_breakdown_keys = [
        "matrix_load_ms",
        "index_load_ms",
        "hnsw_search_ms",
        "id_index_load_ms",
        "staleness_detection_ms",
    ]

    search_breakdown_labels = {
        "matrix_load_ms": "    ├─ Matrix load",
        "index_load_ms": "    ├─ HNSW index load",
        "hnsw_search_ms": "    ├─ HNSW search",
        "id_index_load_ms": "    ├─ ID index load",
        "staleness_detection_ms": "    └─ Content & staleness detection",
    }

    has_parallel_breakdown = "parallel_load_ms" in timing_info
    has_search_breakdown = any(key in timing_info for key in search_breakdown_keys)

    # Display each high-level step, with breakdown inserted appropriately
    for key, label in high_level_steps.items():
        if key in timing_info:
            ms = timing_info[key]
            percentage = (ms / total_ms * 100) if total_ms > 0 else 0

            # Format time
            if ms < 1:
                time_str = f"{ms:.2f}ms"
            elif ms < 1000:
                time_str = f"{ms:.0f}ms"
            else:
                time_str = f"{ms/1000:.2f}s"

            console.print(f"  • {label:<30} {time_str:>10} ({percentage:>5.1f}%)")

            # Insert parallel breakdown immediately after parallel_load_ms
            if key == "parallel_load_ms" and has_parallel_breakdown:
                console.print("")
                for breakdown_key in parallel_breakdown_keys:
                    if breakdown_key in timing_info and timing_info[breakdown_key] > 0:
                        breakdown_ms = timing_info[breakdown_key]
                        # Note: Don't calculate percentage from total_ms - these are concurrent!
                        # Exception: For overhead, show percentage of parallel load time

                        # Format time
                        if breakdown_ms < 1:
                            breakdown_time_str = f"{breakdown_ms:.2f}ms"
                        elif breakdown_ms < 1000:
                            breakdown_time_str = f"{breakdown_ms:.0f}ms"
                        else:
                            breakdown_time_str = f"{breakdown_ms/1000:.2f}s"

                        breakdown_label = parallel_breakdown_labels.get(
                            breakdown_key, breakdown_key
                        )

                        # For overhead, show percentage of parallel load time
                        if (
                            breakdown_key == "parallel_overhead_ms"
                            and "parallel_load_ms" in timing_info
                        ):
                            parallel_load_ms = timing_info["parallel_load_ms"]
                            overhead_pct = (
                                (breakdown_ms / parallel_load_ms * 100)
                                if parallel_load_ms > 0
                                else 0
                            )
                            console.print(
                                f"  {breakdown_label:<30} {breakdown_time_str:>10} ({overhead_pct:>4.1f}% overhead)"
                            )
                        else:
                            console.print(
                                f"  {breakdown_label:<30} {breakdown_time_str:>10}"
                            )
                console.print("")

            # Insert search breakdown immediately after vector_search_ms (for non-parallel path)
            elif key == "vector_search_ms" and has_search_breakdown:
                console.print("")
                for breakdown_key in search_breakdown_keys:
                    if breakdown_key in timing_info and timing_info[breakdown_key] > 0:
                        breakdown_ms = timing_info[breakdown_key]
                        breakdown_percentage = (
                            (breakdown_ms / total_ms * 100) if total_ms > 0 else 0
                        )

                        # Format time
                        if breakdown_ms < 1:
                            breakdown_time_str = f"{breakdown_ms:.2f}ms"
                        elif breakdown_ms < 1000:
                            breakdown_time_str = f"{breakdown_ms:.0f}ms"
                        else:
                            breakdown_time_str = f"{breakdown_ms/1000:.2f}s"

                        breakdown_label = search_breakdown_labels.get(
                            breakdown_key, breakdown_key
                        )
                        console.print(
                            f"  {breakdown_label:<30} {breakdown_time_str:>10} ({breakdown_percentage:>5.1f}%)"
                        )
                console.print("")

    # Display search path indicator
    if "search_path" in timing_info:
        search_path = timing_info["search_path"]
        path_emoji = {
            "hnsw_index": "⚡",  # Lightning bolt for fast HNSW
            "none": "❌",
        }
        emoji = path_emoji.get(search_path, "❓")
        console.print(f"\n  Search path: {emoji} {search_path}")

    console.print("-" * 60)

    # Total
    if total_ms < 1000:
        total_str = f"{total_ms:.0f}ms"
    else:
        total_str = f"{total_ms/1000:.2f}s"
    console.print(f"  {'Total query time':<30} {total_str:>10} (100.0%)")
    console.print()


def _display_fts_results(
    results: List[Dict[str, Any]],
    quiet: bool = False,
    console: Optional[Console] = None,
) -> None:
    """Display full-text search results with Rich formatting.

    Args:
        results: List of FTS search results from TantivyIndexManager
        quiet: If True, show minimal output (file:line:col only)
        console: Rich console for output (creates new if None)
    """
    if console is None:
        console = Console()

    if not quiet:
        console.print("[bold cyan]Full-Text Search Results[/bold cyan]\n")

    if not results:
        if not quiet:
            console.print("[yellow]No matches found[/yellow]")
        return

    for i, result in enumerate(results, 1):
        # Extract result fields
        path = result.get("path", "unknown")
        line = result.get("line", 0)
        column = result.get("column", 0)

        # Quiet mode: print match number with file:line:column
        if quiet:
            console.print(f"{i}. {path}:{line}:{column}")
            continue

        # Full mode: rich formatting with readable position
        console.print(
            f"[cyan]{i}.[/cyan] [green]{path}[/green] [yellow](Line {line}, Col {column})[/yellow]"
        )

        # Show language if available
        language = result.get("language")
        if language:
            console.print(f"   Language: [blue]{language}[/blue]")

        # Show matched text
        match_text = result.get("match_text", "")
        if match_text:
            console.print(f"   Match: [red]{match_text}[/red]")

        # Show snippet with syntax highlighting if available
        # snippet_lines=0 returns empty string, so we skip display
        snippet = result.get("snippet", "")
        if snippet and snippet.strip():  # Only show if snippet is non-empty
            console.print("   Context:")
            try:
                from rich.syntax import Syntax

                syntax = Syntax(
                    snippet,
                    language or "text",
                    theme="monokai",
                    line_numbers=True,
                    start_line=result.get("snippet_start_line", 1),
                )
                console.print(syntax)
            except Exception:
                # Fallback: just print the snippet without highlighting
                console.print(f"   {snippet}")

        console.print()


def _display_semantic_results(
    results: List[Dict[str, Any]],
    console: Console,
    quiet: bool = False,
    timing_info: Optional[Dict[str, Any]] = None,
    current_display_branch: Optional[str] = None,
) -> None:
    """Display semantic search results (shared by standalone and daemon modes).

    This function contains the complete display logic for semantic search results
    and is used by both:
    - cli.py query command (standalone mode)
    - cli_daemon_fast.py (daemon mode)

    Args:
        results: List of search results with 'score' and 'payload' keys
        console: Rich console for output
        quiet: If True, minimal output (score + path + content only)
        timing_info: Optional timing information for performance display
        current_display_branch: Optional current git branch name for display
    """
    if not results:
        if not quiet:
            console.print("❌ No results found", style="yellow")
            # Display timing summary even when no results
            if timing_info:
                _display_query_timing(console, timing_info)
        return

    if not quiet:
        console.print(f"\n✅ Found {len(results)} results:")
        console.print("=" * 80)
        # Display timing summary
        if timing_info:
            _display_query_timing(console, timing_info)

    # Auto-detect current branch if not provided
    if current_display_branch is None and not quiet:
        import subprocess

        try:
            git_result = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                timeout=5,
            )
            current_display_branch = (
                git_result.stdout.strip() if git_result.returncode == 0 else "unknown"
            )
        except Exception:
            current_display_branch = "unknown"

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
            # Quiet mode - minimal output: match number, score, staleness, path with line numbers
            if staleness_indicator:
                console.print(
                    f"{i}. {score:.3f} {staleness_indicator} {file_path_with_lines}"
                )
            else:
                console.print(f"{i}. {score:.3f} {file_path_with_lines}")
            if content:
                # Show full content with line numbers in quiet mode (no truncation)
                content_lines = content.split("\n")

                # Add line number prefixes if we have line start info
                if line_start is not None:
                    numbered_lines = []
                    for j, line in enumerate(content_lines):
                        line_num = line_start + j
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

            # Create header with match number, git info and line numbers
            header = f"{i}. 📄 File: {file_path_with_lines}"
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
                        content_header = f"📖 Content (Lines {line_start}-{line_end}):"
                else:
                    content_header = "📖 Content:"

                console.print(f"\n{content_header}")
                console.print("─" * 50)

                # Add line number prefixes to full content (no truncation)
                content_lines = content.split("\n")

                # Add line number prefixes if we have line start info
                if line_start is not None:
                    numbered_lines = []
                    for j, line in enumerate(content_lines):
                        line_num = line_start + j
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


def _execute_semantic_search(
    query: str,
    limit: int,
    languages: tuple,
    exclude_languages: tuple,
    path_filter: tuple,
    exclude_paths: tuple,
    min_score: Optional[float],
    accuracy: str,
    quiet: bool,
    project_root: Path,
    config_manager,
    console: Console,
) -> List[Dict[str, Any]]:
    """Execute semantic search - extracted for parallel execution in hybrid mode.

    This function contains the complete semantic search logic extracted from the main
    query command to enable true parallel execution with FTS search.

    Args:
        query: Search query text
        limit: Maximum number of results
        languages: Tuple of language filters
        exclude_languages: Tuple of languages to exclude
        path_filter: Tuple of path filter patterns
        exclude_paths: Tuple of path patterns to exclude
        min_score: Minimum similarity score threshold
        accuracy: Search accuracy mode
        quiet: If True, minimal output
        project_root: Project root directory
        config_manager: Configuration manager instance
        console: Rich console for output

    Returns:
        List of semantic search results
    """
    import time
    from typing import Any, Dict

    try:
        config = config_manager.load()

        # Initialize services - lazy imports for query path
        from .services.generic_query_service import GenericQueryService
        from .services.language_validator import LanguageValidator
        from .services.language_mapper import LanguageMapper

        embedding_provider = EmbeddingProviderFactory.create(config, console)
        backend = BackendFactory.create(
            config=config, project_root=Path(config.codebase_dir)
        )
        vector_store_client = backend.get_vector_store_client()

        # Health checks
        if not embedding_provider.health_check():
            if not quiet:
                console.print(
                    f"[yellow]⚠️  {embedding_provider.get_provider_name().title()} service not available[/yellow]"
                )
            return []

        if not vector_store_client.health_check():
            if not quiet:
                console.print("[yellow]⚠️  Vector store service not available[/yellow]")
            return []

        # Ensure provider-aware collection is set for search
        collection_name = vector_store_client.resolve_collection_name(
            config, embedding_provider
        )
        vector_store_client._current_collection_name = collection_name

        # Ensure payload indexes exist (read-only check for query operations)
        vector_store_client.ensure_payload_indexes(collection_name, context="query")

        # Initialize timing dictionary for telemetry
        timing_info = {}

        # Build filter conditions
        filter_conditions: Dict[str, Any] = {}
        if languages:
            # Validate language parameters
            language_validator = LanguageValidator()
            language_mapper = LanguageMapper()
            must_conditions = []

            for lang in languages:
                # Validate each language
                validation_result = language_validator.validate_language(lang)

                if not validation_result.is_valid:
                    if not quiet:
                        console.print(f"[yellow]⚠️  Invalid language: {lang}[/yellow]")
                    continue

                # Build language filter
                language_filter = language_mapper.build_language_filter(lang)
                must_conditions.append(language_filter)

            if must_conditions:
                filter_conditions["must"] = must_conditions
        if path_filter:
            for pf in path_filter:
                filter_conditions.setdefault("must", []).append(
                    {"key": "path", "match": {"text": pf}}
                )

        # Build exclusion filters (must_not conditions)
        if exclude_languages:
            language_validator = LanguageValidator()
            language_mapper = LanguageMapper()
            must_not_conditions = []

            for exclude_lang in exclude_languages:
                # Validate each exclusion language
                validation_result = language_validator.validate_language(exclude_lang)

                if not validation_result.is_valid:
                    if not quiet:
                        console.print(
                            f"[yellow]⚠️  Invalid exclusion language: {exclude_lang}[/yellow]"
                        )
                    continue

                # Get all extensions for this language
                extensions = language_mapper.get_extensions(exclude_lang)

                # Add must_not condition for each extension
                for ext in extensions:
                    must_not_conditions.append(
                        {"key": "language", "match": {"value": ext}}
                    )

            if must_not_conditions:
                filter_conditions["must_not"] = must_not_conditions

        # Build path exclusion filters (must_not conditions for paths)
        if exclude_paths:
            from .services.path_filter_builder import PathFilterBuilder

            path_filter_builder = PathFilterBuilder()

            # Build path exclusion filters
            path_exclusion_filters = path_filter_builder.build_exclusion_filter(
                list(exclude_paths)
            )

            # Add to existing must_not conditions
            if path_exclusion_filters.get("must_not"):
                if "must_not" in filter_conditions:
                    filter_conditions["must_not"].extend(
                        path_exclusion_filters["must_not"]
                    )
                else:
                    filter_conditions["must_not"] = path_exclusion_filters["must_not"]

        # Check if project uses git-aware indexing
        from .services.git_topology_service import GitTopologyService

        git_topology_service = GitTopologyService(config.codebase_dir)
        is_git_aware = git_topology_service.is_git_available()

        # Initialize query service for git-aware filtering
        query_service = GenericQueryService(config.codebase_dir, config)

        # Determine if we should use branch-aware querying
        if is_git_aware:
            # Use git-aware filtering for git projects
            use_branch_aware_query = True
        else:
            # Use generic query service for non-git projects
            use_branch_aware_query = False

        # Get current embedding model for filtering
        current_model = embedding_provider.get_current_model()

        # Use appropriate search method based on project type
        if use_branch_aware_query:
            # Build filter conditions (NO git_branch filter - let post-filtering handle it)
            filter_conditions_list = []

            # Only filter by git_available to exclude non-git content
            filter_conditions_list.append(
                {"key": "git_available", "match": {"value": True}}
            )

            # Add user-specified filters
            if languages:
                language_mapper = LanguageMapper()
                # Handle multiple languages by building OR conditions
                for language in languages:
                    language_filter = language_mapper.build_language_filter(language)
                    filter_conditions_list.append(language_filter)
            if path_filter:
                for pf in path_filter:
                    filter_conditions_list.append(
                        {"key": "path", "match": {"text": pf}}
                    )

            # Build filter conditions preserving both must and must_not conditions
            query_filter_conditions = (
                {"must": filter_conditions_list} if filter_conditions_list else {}
            )
            # Preserve must_not conditions (exclusion filters)
            if filter_conditions.get("must_not"):
                query_filter_conditions["must_not"] = filter_conditions["must_not"]

            # Query vector store
            from .storage.filesystem_vector_store import (
                FilesystemVectorStore,
            )

            if isinstance(vector_store_client, FilesystemVectorStore):
                # Parallel execution: embedding generation + index loading happen concurrently
                raw_results, search_timing = vector_store_client.search(
                    query=query,
                    embedding_provider=embedding_provider,
                    filter_conditions=query_filter_conditions,
                    limit=limit * 2,
                    collection_name=collection_name,
                    return_timing=True,
                )
            else:
                # QdrantClient: pre-compute embedding
                query_embedding = embedding_provider.get_embedding(query)
                raw_results_list = vector_store_client.search(
                    query_vector=query_embedding,
                    filter_conditions=query_filter_conditions,
                    limit=limit * 2,
                    collection_name=collection_name,
                )
                raw_results = raw_results_list
                search_timing = {}
            timing_info.update(search_timing)

            # Calculate vector_search_ms
            breakdown_keys = [
                "matrix_load_ms",
                "index_load_ms",
                "hnsw_search_ms",
                "id_index_load_ms",
                "staleness_detection_ms",
            ]
            timing_info["vector_search_ms"] = sum(
                search_timing.get(k, 0) for k in breakdown_keys
            )

            # Apply git-aware post-filtering
            git_filter_start = time.time()
            # Type hint: raw_results is always List[Dict[str, Any]] here
            git_results = query_service.filter_results_by_current_branch(
                raw_results  # type: ignore[arg-type]
            )
            timing_info["git_filter_ms"] = (time.time() - git_filter_start) * 1000

            # Apply minimum score filtering
            if min_score:
                filtered_results = []
                for result in git_results:
                    if result.get("score", 0) >= min_score:
                        filtered_results.append(result)
                git_results = filtered_results
        else:
            # Use model-specific search for non-git projects
            from .storage.filesystem_vector_store import (
                FilesystemVectorStore,
            )

            if isinstance(vector_store_client, FilesystemVectorStore):
                # Filesystem backend: parallel execution
                raw_results, search_timing = vector_store_client.search(
                    query=query,
                    embedding_provider=embedding_provider,
                    filter_conditions=filter_conditions if filter_conditions else None,
                    limit=limit * 2,
                    score_threshold=min_score,
                    collection_name=collection_name,
                    return_timing=True,
                )
                timing_info.update(search_timing)
            else:
                # Qdrant backend: pre-compute embedding
                search_start = time.time()
                query_embedding = embedding_provider.get_embedding(query)
                raw_results_list = vector_store_client.search_with_model_filter(
                    query_vector=query_embedding,
                    embedding_model=current_model,
                    limit=limit * 2,
                    score_threshold=min_score,
                    additional_filters=filter_conditions,
                    accuracy=accuracy,
                )
                raw_results = raw_results_list
                timing_info["vector_search_ms"] = (time.time() - search_start) * 1000

            # Apply git-aware filtering
            git_filter_start = time.time()
            # Type hint: raw_results is always List[Dict[str, Any]] here
            git_results = query_service.filter_results_by_current_branch(
                raw_results  # type: ignore[arg-type]
            )
            timing_info["git_filter_ms"] = (time.time() - git_filter_start) * 1000

        # Limit to requested number after filtering
        results = git_results[:limit]

        # Apply staleness detection to local query results
        if results:
            try:
                staleness_start = time.time()
                from .api_clients.remote_query_client import QueryResultItem
                from .remote.staleness_detector import StalenessDetector

                query_result_items = []
                for result in results:
                    payload = result["payload"]

                    # Extract file metadata for staleness comparison
                    file_last_modified = payload.get("file_last_modified")
                    indexed_at = payload.get("indexed_at")

                    # Convert indexed_at ISO timestamp to Unix timestamp float
                    indexed_timestamp = None
                    if indexed_at:
                        try:
                            from datetime import datetime

                            dt = datetime.fromisoformat(indexed_at.rstrip("Z"))
                            indexed_timestamp = dt.timestamp()
                        except (ValueError, AttributeError):
                            indexed_timestamp = None

                    query_item = QueryResultItem(
                        similarity_score=result["score"],
                        file_path=payload.get("path", "unknown"),
                        line_number=payload.get("line_start", 1),
                        code_snippet=payload.get("content", ""),
                        repository_alias=project_root.name,
                        file_last_modified=file_last_modified,
                        indexed_timestamp=indexed_timestamp,
                    )
                    query_result_items.append(query_item)

                # Apply staleness detection in local mode
                staleness_detector = StalenessDetector()
                enhanced_results = staleness_detector.apply_staleness_detection(
                    query_result_items, project_root, mode="local"
                )
                timing_info["staleness_detection_ms"] = (
                    time.time() - staleness_start
                ) * 1000

                # Convert enhanced results back to local format
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

            except Exception:
                # Graceful fallback - continue with original results
                pass

        return results

    except Exception as e:
        if not quiet:
            console.print(f"[yellow]⚠️  Semantic search failed: {e}[/yellow]")
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Semantic search error: {e}", exc_info=True)
        return []


def _display_hybrid_results(
    fts_results: List[Dict[str, Any]],
    semantic_results: List[Dict[str, Any]],
    quiet: bool = False,
    console: Optional[Console] = None,
) -> None:
    """Display hybrid search results (FTS + Semantic) with clear separation.

    Args:
        fts_results: List of FTS search results from TantivyIndexManager
        semantic_results: List of semantic search results
        quiet: If True, show minimal output
        console: Rich console for output (creates new if None)
    """
    if console is None:
        console = Console()

    # FTS Results First
    if not quiet:
        console.print("[bold cyan]━━━ FULL-TEXT SEARCH RESULTS ━━━[/bold cyan]\n")

    if fts_results:
        _display_fts_results(fts_results, quiet=quiet, console=console)
    else:
        if not quiet:
            console.print("[yellow]No text matches found[/yellow]\n")

    # Clear Separator
    if not quiet:
        console.print("[bold]" + "─" * 60 + "[/bold]\n")

    # Semantic Results Second
    if not quiet:
        console.print("[bold magenta]━━━ SEMANTIC SEARCH RESULTS ━━━[/bold magenta]\n")

    if semantic_results:
        # Display semantic results (reuse logic from existing semantic display)
        for i, result in enumerate(semantic_results, 1):
            payload = result.get("payload", {})
            score = result.get("score", 0.0)

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
                # Quiet mode - minimal output with match number
                console.print(f"{i}. {score:.3f} {file_path_with_lines}")
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
                console.print(f"\n[magenta]{i}.[/magenta] Score: {score:.3f}")
                console.print(f"File: [green]{file_path_with_lines}[/green]")
                if language != "unknown":
                    console.print(f"Language: [blue]{language}[/blue]")

                if content:
                    console.print("Content:")
                    console.print("-" * 40)
                    console.print(content)
                    console.print("-" * 40)
    else:
        if not quiet:
            console.print("[yellow]No semantic matches found[/yellow]\n")


def _check_authentication_state(ctx) -> bool:
    """Check if user is authenticated and session is valid.

    Args:
        ctx: Click context

    Returns:
        bool: True if authenticated, False otherwise
    """
    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .api_clients.auth_client import create_auth_client
        from .remote.credential_manager import CredentialNotFoundError

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ Authentication required: Please login first", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
            return False

        # Load remote configuration
        try:
            remote_config = load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
        except Exception:
            console.print("❌ Authentication required: Please login first", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
            return False

        # Try to load stored credentials
        try:
            # Attempt to create authenticated client
            auth_client = create_auth_client(server_url, project_root)
            if not auth_client.credentials:
                console.print(
                    "❌ Authentication required: Please login first", style="red"
                )
                console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
                return False

            # Basic validation - we assume if credentials exist, they're valid
            # The actual API call will validate the session
            return True

        except CredentialNotFoundError:
            console.print("❌ Authentication required: Please login first", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
            return False
        except Exception as e:
            # Handle expired sessions or invalid credentials
            if "expired" in str(e).lower() or "invalid" in str(e).lower():
                console.print("❌ Session expired: Please login again", style="red")
                console.print(
                    "💡 Use 'cidx auth login' to re-authenticate", style="dim"
                )
                return False
            else:
                console.print(
                    "❌ Authentication required: Please login first", style="red"
                )
                console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
                return False

    except Exception as e:
        console.print("❌ Authentication check failed", style="red")
        if ctx.obj.get("verbose"):
            console.print(f"Error: {e}", style="dim red")
        return False


def _validate_password_strength(password: str) -> tuple:
    """Validate password strength using project password policy.

    Args:
        password: Password to validate

    Returns:
        tuple: (is_valid, message) - validation result and message
    """
    from .password_policy import validate_password_strength

    return validate_password_strength(password)


def create_auth_client(server_url: str, project_root: Path):
    """Create authentication client with proper configuration.

    Args:
        server_url: Server URL for authentication
        project_root: Project root directory

    Returns:
        AuthAPIClient: Configured authentication client
    """
    from .api_clients.auth_client import create_auth_client as _create_auth_client
    from .remote.config import load_remote_configuration

    # Try to get username from remote configuration for credential loading
    username = None
    try:
        remote_config = load_remote_configuration(project_root)
        username = remote_config.get("username")
    except Exception:
        # If we can't load remote config, proceed without username
        pass

    return _create_auth_client(server_url, project_root, username)


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
                emoji_count = icons.count("🌐") + icons.count("🐳") + icons.count("🔗")
                visual_width = len(icons) + emoji_count

                # Target total width for command part is 26 chars (increased for 3 icons)
                padding_needed = max(0, 26 - visual_width - len(cmd_name))

                formatted_line = (
                    f"  {icons} {cmd_name}{' ' * padding_needed} {help_text}"
                )
                formatter.write(formatted_line + "\n")

            formatter.write("\n")
            formatter.write("Legend: 🌐 Remote | 🐳 Local | 🔗 Proxy\n")


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

    # Initialize ExceptionLogger VERY EARLY for error tracking
    exception_logger = ExceptionLogger.initialize(project_root=Path.cwd(), mode="cli")
    exception_logger.install_thread_exception_hook()

    # Configure logging at WARNING level for clean CLI output
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s"
    )

    # Configure logging to suppress noisy third-party messages
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("root").setLevel(logging.WARNING)

    # Handle --use-cidx-prompt flag (early return)
    if use_cidx_prompt:
        try:
            # Lazy import for prompt generation
            from .services.cidx_prompt_generator import create_cidx_ai_prompt

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
@click.argument(
    "codebase_dir",
    required=False,
    type=click.Path(exists=True),
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
    default="voyage-ai",
    help="Embedding provider to use (default: voyage-ai)",
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
@click.option(
    "--proxy-mode",
    is_flag=True,
    help="Initialize as proxy directory for managing multiple indexed repositories",
)
@click.option(
    "--vector-store",
    type=click.Choice(["filesystem", "qdrant"], case_sensitive=False),
    default="filesystem",
    help="Vector storage backend: 'filesystem' (container-free) or 'qdrant' (containers required)",
)
@click.option(
    "--daemon",
    is_flag=True,
    help="Enable daemon mode for performance optimization",
)
@click.option(
    "--daemon-ttl",
    type=int,
    default=10,
    help="Cache TTL in minutes for daemon mode (default: 10)",
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
    proxy_mode: bool,
    vector_store: str,
    daemon: bool,
    daemon_ttl: int,
):
    """Initialize code indexing in current directory (OPTIONAL).

    \b
    Creates .code-indexer/config.json with project configuration.

    \b
    NOTE: This command is optional. If you skip init and run 'start' directly,
    a default configuration will be created automatically with VoyageAI provider
    and standard settings. Only use init if you want to customize settings.

    \b
    INITIALIZATION MODES:
      🏠 Local Mode (default): Creates local configuration with VoyageAI embeddings
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
      • voyage-ai: VoyageAI API (default, requires VOYAGE_API_KEY environment variable)
      • ollama: Local AI models (experimental, no API key required)

    \b
    QDRANT SEGMENT SIZE:
      Controls Qdrant storage segment size (default: 100MB for optimal performance):
      • 10MB: Git-friendly for small projects, faster indexing, more files
      • 50MB: Balanced approach for medium projects
      • 100MB: Default - optimal performance while staying Git-compatible
      • 200MB: Large repositories prioritizing search performance

    \b
    EXAMPLES:
      code-indexer init                                    # Basic initialization with VoyageAI
      code-indexer init --interactive                     # Interactive configuration
      code-indexer init --embedding-provider ollama       # Use Ollama (experimental)
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

    # Handle proxy mode initialization
    if proxy_mode:
        from .proxy.proxy_initializer import (
            ProxyInitializer,
            ProxyInitializationError,
            NestedProxyError,
        )

        # Determine target directory
        target_dir = Path(codebase_dir) if codebase_dir else Path.cwd()

        try:
            # Create ProxyInitializer instance
            initializer = ProxyInitializer(target_dir=target_dir)

            # Run initialization
            initializer.initialize(force=force)

            # Get discovered repositories for user feedback
            config_file = target_dir / ".code-indexer" / "config.json"
            with open(config_file) as f:
                config_data = json.load(f)

            discovered_repos = config_data.get("discovered_repos", [])

            # Display success message
            console.print("✅ Proxy mode initialized successfully", style="green")
            console.print(
                f"📂 Configuration saved to: {target_dir / '.code-indexer' / 'config.json'}",
                style="dim",
            )
            console.print()

            # Show discovered repositories
            console.print(
                f"📚 Discovered {len(discovered_repos)} repositories", style="cyan"
            )
            if discovered_repos:
                for repo in discovered_repos:
                    console.print(f"   • {repo}", style="dim")
            else:
                console.print()
                console.print(
                    "📭 No repositories found in this directory", style="yellow"
                )
                console.print(
                    "   Add indexed repositories as subdirectories and re-run with --force",
                    style="dim",
                )

            sys.exit(0)

        except NestedProxyError as e:
            console.print("❌ Cannot create nested proxy configuration", style="red")
            console.print(f"   {str(e)}", style="red")
            sys.exit(1)

        except ProxyInitializationError as e:
            console.print("❌ Proxy initialization failed", style="red")
            console.print(f"   {str(e)}", style="red")
            console.print()
            console.print(
                "💡 Use --force to overwrite existing configuration", style="dim"
            )
            sys.exit(1)

        except Exception as e:
            console.print(
                "❌ Unexpected error during proxy initialization", style="red"
            )
            console.print(f"   {str(e)}", style="red")
            sys.exit(1)

    # For init command, always create config in current directory (or specified codebase_dir)
    # Don't use the CLI context's config_manager which may have found a parent config
    target_dir = Path(codebase_dir) if codebase_dir else Path.cwd()
    project_config_path = target_dir / ".code-indexer" / "config.json"
    config_manager = ConfigManager(project_config_path)

    # CRITICAL: Check global port registry writeability before proceeding
    # But ONLY for backends that need containers (qdrant)
    if vector_store != "filesystem":
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
                    console.print(
                        "   cidx init --setup-global-registry", style="bold cyan"
                    )
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
    if config_manager.config_path.exists():
        # Load existing config to check for backend changes
        existing_config = config_manager.load()
        existing_backend = (
            existing_config.vector_store.provider
            if existing_config.vector_store
            else "qdrant"  # Default if not set
        )

        # Check if switching backends with --force
        if force and existing_backend != vector_store:
            console.print(
                "⚠️  Backend switch detected: {} → {}".format(
                    existing_backend, vector_store
                ),
                style="yellow bold",
            )
            console.print()
            console.print(
                "🔄 Switching vector storage backends requires:", style="yellow"
            )
            console.print("   • Removing existing vector index data", style="blue")
            console.print("   • Re-indexing your entire codebase", style="blue")
            console.print("   • Your source code files are preserved", style="green")
            console.print()
            console.print(
                "💡 Recommended workflow for backend switching:", style="cyan"
            )
            console.print("   1. cidx stop", style="dim")
            console.print("   2. cidx uninstall --confirm", style="dim")
            console.print(f"   3. cidx init --vector-store {vector_store}", style="dim")
            console.print("   4. cidx start", style="dim")
            console.print("   5. cidx index", style="dim")
            console.print()

            from rich.prompt import Confirm

            if not Confirm.ask(
                "Proceed with backend switch (will overwrite config)?", default=False
            ):
                console.print("❌ Backend switch cancelled", style="yellow")
                sys.exit(0)

        # Special case: if only --create-override-file is requested, allow it
        if not force and create_override_file:
            # Load existing config and create override file
            config = existing_config
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
        elif not force:
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
                "\nUse Ollama instead of VoyageAI? (experimental, slower)",
                default=False,
            ):
                embedding_provider = "ollama"
            else:
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

        # Create default config with target_dir for proper initialization
        # target_dir respects --codebase-dir parameter
        config = Config(codebase_dir=target_dir)
        config_manager._config = config

        # Update config with provided options
        updates: Dict[str, Any] = {}

        # Set embedding provider
        updates["embedding_provider"] = embedding_provider

        # Set vector store backend
        from .config import VectorStoreConfig

        updates["vector_store"] = VectorStoreConfig(provider=vector_store).model_dump()

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

        # Conditionally allocate ports based on vector store backend
        # Filesystem backend doesn't need containers, so no port allocation
        if vector_store == "filesystem":
            # Create ProjectPortsConfig with all None values for filesystem backend
            # Don't set to None directly as that causes Pydantic validation errors
            from .config import ProjectPortsConfig

            updates["project_ports"] = ProjectPortsConfig(
                qdrant_port=None, ollama_port=None, data_cleaner_port=None
            )

        # Apply updates if any
        if updates:
            config = config_manager.update_config(**updates)

        # Save with documentation
        config_manager.save_with_documentation(config)

        # Initialize vector storage backend

        backend = BackendFactory.create(config=config, project_root=config.codebase_dir)
        try:
            backend.initialize()
            console.print(
                f"✅ Initialized {config.vector_store.provider} vector storage backend"  # type: ignore
            )
        except Exception as e:
            console.print(
                f"⚠️  Warning: Failed to initialize backend: {e}", style="yellow"
            )

        # Create qdrant storage directory proactively during init to prevent race condition
        # Only needed for qdrant backend
        if config.vector_store and config.vector_store.provider == "qdrant":  # type: ignore
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

        # Enable daemon mode if requested
        if daemon:
            try:
                config_manager.enable_daemon(ttl_minutes=daemon_ttl)
                console.print(
                    f"✅ Daemon mode enabled (Cache TTL: {daemon_ttl} minutes)",
                    style="green",
                )
                console.print("ℹ️  Daemon will auto-start on first query", style="dim")
            except ValueError as e:
                console.print(f"❌ Invalid daemon TTL: {e}", style="red")
                sys.exit(1)

    except Exception as e:
        console.print(f"❌ Failed to initialize: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.option(
    "--show",
    is_flag=True,
    help="Display current configuration",
)
@click.option(
    "--daemon/--no-daemon",
    default=None,
    help="Enable or disable daemon mode",
)
@click.option(
    "--daemon-ttl",
    type=int,
    help="Update cache TTL in minutes for daemon mode",
)
@click.option(
    "--set-diff-context",
    type=int,
    help="Set default diff context lines for temporal indexing (0-50, default: 5)",
)
@click.pass_context
def config(
    ctx,
    show: bool,
    daemon: Optional[bool],
    daemon_ttl: Optional[int],
    set_diff_context: Optional[int],
):
    """Manage repository configuration.

    \b
    Configure daemon mode and other repository settings.

    \b
    EXAMPLES:
      cidx config --show                    # Display current config
      cidx config --daemon                  # Enable daemon mode
      cidx config --no-daemon               # Disable daemon mode
      cidx config --daemon-ttl 20           # Set TTL to 20 minutes
      cidx config --daemon --daemon-ttl 30  # Enable daemon with 30min TTL

    \b
    DAEMON MODE:
      Daemon mode optimizes performance by keeping indexed data in memory
      and providing faster query responses. The daemon auto-starts on
      first query and auto-shuts down after idle timeout.
    """
    # Get config_manager from context (set by main CLI function with backtracking)
    config_manager = ctx.obj.get("config_manager")

    # If no config_manager in context, fall back to backtracking from cwd
    if not config_manager:
        config_manager = ConfigManager.create_with_backtrack(Path.cwd())

    # Check if config exists
    if not config_manager.config_path.exists():
        console.print("❌ No CIDX configuration found", style="red")
        console.print()
        console.print("Initialize a repository first:")
        console.print("  cidx init", style="cyan")
        console.print()
        console.print("Or navigate to an initialized repository directory")
        sys.exit(1)

    # Handle --show
    if show:
        try:
            config = config_manager.load()
            daemon_config = config_manager.get_daemon_config()

            console.print()
            console.print("[bold cyan]Repository Configuration[/bold cyan]")
            console.print("─" * 50)
            console.print()

            # Daemon mode status
            daemon_status = "Enabled" if daemon_config["enabled"] else "Disabled"
            status_style = "green" if daemon_config["enabled"] else "yellow"
            console.print(
                f"  Daemon Mode:    [{status_style}]{daemon_status}[/{status_style}]"
            )

            if daemon_config["enabled"]:
                console.print(
                    f"  Cache TTL:      {daemon_config['ttl_minutes']} minutes"
                )
                auto_start = daemon_config.get("auto_start", True)
                console.print(f"  Auto-start:     {'Yes' if auto_start else 'No'}")
                auto_shutdown = daemon_config["auto_shutdown_on_idle"]
                console.print(f"  Auto-shutdown:  {'Yes' if auto_shutdown else 'No'}")

                # Show socket path
                socket_path = config_manager.get_socket_path()
                console.print(f"  Socket Path:    {socket_path}")

            console.print()

            # Temporal indexing configuration
            console.print("[bold cyan]Temporal Indexing[/bold cyan]")
            console.print("─" * 50)
            console.print()

            if hasattr(config, "temporal") and config.temporal:
                diff_context = config.temporal.diff_context_lines
                console.print(f"  Diff Context:   {diff_context} lines", end="")
                if diff_context == 5:
                    console.print(" (default)", style="dim")
                else:
                    console.print(" (custom)", style="yellow")
            else:
                console.print("  Diff Context:   5 lines (default)", style="dim")

            console.print()
            return 0

        except Exception as e:
            console.print(f"❌ Failed to load configuration: {e}", style="red")
            sys.exit(1)

    # Handle configuration updates
    update_performed = False

    if daemon is not None:
        try:
            if daemon:
                config_manager.enable_daemon()
                console.print("✅ Daemon mode enabled", style="green")
                console.print("ℹ️  Daemon will auto-start on first query", style="dim")
            else:
                config_manager.disable_daemon()
                console.print("✅ Daemon mode disabled", style="green")
                console.print("ℹ️  Queries will run in standalone mode", style="dim")
            update_performed = True
        except Exception as e:
            console.print(f"❌ Failed to update daemon mode: {e}", style="red")
            sys.exit(1)

    if daemon_ttl is not None:
        try:
            config_manager.update_daemon_ttl(daemon_ttl)
            console.print(
                f"✅ Cache TTL updated to {daemon_ttl} minutes", style="green"
            )
            update_performed = True
        except ValueError as e:
            console.print(f"❌ Invalid daemon TTL: {e}", style="red")
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Failed to update daemon TTL: {e}", style="red")
            sys.exit(1)

    if set_diff_context is not None:
        try:
            # Validate range
            if set_diff_context < 0 or set_diff_context > 50:
                console.print(
                    f"❌ Invalid diff-context {set_diff_context}. Valid range: 0-50",
                    style="red",
                )
                sys.exit(1)

            # Load config, update temporal settings, and save
            from .config import TemporalConfig

            config = config_manager.load()
            if not hasattr(config, "temporal") or config.temporal is None:
                config.temporal = TemporalConfig(diff_context_lines=set_diff_context)
            else:
                config.temporal.diff_context_lines = set_diff_context
            config_manager.save(config)

            console.print(
                f"✅ Diff context set to {set_diff_context} lines", style="green"
            )
            update_performed = True
        except Exception as e:
            console.print(f"❌ Failed to update diff-context: {e}", style="red")
            sys.exit(1)

    # If no operations performed, show help message
    if not update_performed and not show:
        console.print("ℹ️  No configuration changes requested", style="yellow")
        console.print()
        console.print("Use --show to display current configuration")
        console.print("Use --daemon or --no-daemon to toggle daemon mode")
        console.print("Use --daemon-ttl <minutes> to update cache TTL")
        console.print()
        console.print("Run 'cidx config --help' for more information")
        return 0

    return 0


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
@require_mode("local", "proxy")
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

    In proxy mode, starts services sequentially across all configured repositories.

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
    # Handle proxy mode (Story 2.3 - Sequential Execution)
    project_root, mode = ctx.obj["project_root"], ctx.obj["mode"]
    if mode == "proxy":
        from .proxy import execute_proxy_command

        # Build args list from options
        args = []
        if force_docker:
            args.append("--force-docker")
        if force_recreate:
            args.append("--force-recreate")
        if quiet:
            args.append("--quiet")

        exit_code = execute_proxy_command(project_root, "start", args)
        sys.exit(exit_code)

    config_manager = ctx.obj["config_manager"]

    try:
        # Lazy imports for start command

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

        # Create backend based on configuration
        backend = BackendFactory.create(config, Path(config.codebase_dir))
        backend_info = backend.get_service_info()

        # Check if backend requires containers
        requires_containers = backend_info.get("requires_containers", False)

        if requires_containers:
            # Qdrant backend - use existing Docker flow
            setup_console.print("🔧 Using Qdrant vector store (containers required)")

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
                port_display.append(
                    f"DataCleaner={project_config['data_cleaner_port']}"
                )

            if port_display:
                setup_console.print(
                    f"🔌 Assigned ports: {', '.join(port_display)}",
                    style="dim",
                )
        else:
            # Filesystem backend - no containers needed
            setup_console.print("📁 Using filesystem vector store (container-free)")
            setup_console.print(
                f"💾 Index directory: {backend_info.get('vectors_dir', 'N/A')}"
            )

            # Call backend start (no-op for filesystem)
            if backend.start():
                setup_console.print("✅ Filesystem backend ready")
                return
            else:
                setup_console.print(
                    "❌ Failed to start filesystem backend", style="red"
                )
                sys.exit(1)

        # Continue with Docker checks only for Qdrant backend
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


def validate_index_flags(ctx, param, value):
    """Validate flag combinations for the index command before execution."""
    if not value:
        return value

    # Access all params - they're stored in ctx.params as options are processed
    params = ctx.params

    # Check for --detect-deletions + --reconcile conflict
    if param.name == "detect_deletions" and value:
        if params.get("reconcile"):
            console.print(
                "❌ Cannot use --detect-deletions with --reconcile", style="red"
            )
            console.print(
                "💡 --reconcile mode includes deletion detection automatically",
                style="yellow",
            )
            ctx.exit(1)

    if param.name == "reconcile" and value:
        if params.get("detect_deletions"):
            console.print(
                "❌ Cannot use --detect-deletions with --reconcile", style="red"
            )
            console.print(
                "💡 --reconcile mode includes deletion detection automatically",
                style="yellow",
            )
            ctx.exit(1)

    return value


@cli.command()
@click.option(
    "--clear", "-c", is_flag=True, help="Clear existing index and perform full reindex"
)
@click.option(
    "--reconcile",
    "-r",
    is_flag=True,
    callback=validate_index_flags,
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
    callback=validate_index_flags,
    help="Detect and handle files deleted from filesystem but still in database (for standard indexing only; --reconcile includes this automatically)",
)
@click.option(
    "--rebuild-indexes",
    is_flag=True,
    help="Rebuild payload indexes for optimal performance",
)
@click.option(
    "--rebuild-index",
    is_flag=True,
    help="Rebuild HNSW index from existing vector files (filesystem backend only)",
)
@click.option(
    "--fts",
    is_flag=True,
    help="Build full-text search index alongside semantic index (requires tantivy)",
)
@click.option(
    "--rebuild-fts-index",
    is_flag=True,
    help="Rebuild ONLY the FTS index from already-indexed files (does not touch semantic vectors)",
)
@click.option(
    "--index-commits",
    is_flag=True,
    help="Index git commit history for temporal search (current branch only by default)",
)
@click.option(
    "--all-branches",
    is_flag=True,
    help="Index all branches (requires --index-commits, may increase storage significantly)",
)
@click.option(
    "--max-commits",
    type=int,
    help="Maximum number of commits to index per branch (default: all)",
)
@click.option(
    "--since-date",
    type=str,
    help="Index commits since date (YYYY-MM-DD format)",
)
@click.option(
    "--diff-context",
    type=int,
    default=None,
    help="Number of context lines for git diffs (0-50, default: 5). "
    "Higher values improve search quality but increase storage.",
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
    rebuild_index: bool,
    fts: bool,
    rebuild_fts_index: bool,
    index_commits: bool,
    all_branches: bool,
    max_commits: Optional[int],
    since_date: Optional[str],
    diff_context: Optional[int],
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
      code-indexer index                 # Smart incremental indexing
      code-indexer index --clear         # Force full reindex (clears existing data)
      code-indexer index --rebuild-index    # Rebuild HNSW index from vectors
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

    # Validate --diff-context flag (must happen before daemon delegation)
    if diff_context is not None and not index_commits:
        console.print(
            "❌ Cannot use --diff-context without --index-commits",
            style="red",
        )
        sys.exit(1)

    if diff_context is not None:
        # Validate diff context value
        if diff_context < 0 or diff_context > 50:
            console.print(
                f"❌ Invalid diff-context {diff_context}. Valid range: 0-50",
                style="red",
            )
            console.print(
                "💡 Recommended values: 0 (minimal), 5 (default), 10 (maximum quality)",
                style="yellow",
            )
            sys.exit(1)

        if diff_context > 20:
            console.print(
                f"⚠️  Large diff context ({diff_context} lines) will significantly increase storage",
                style="yellow",
            )
            console.print(
                "💡 Recommended range: 3-10 lines for best balance", style="dim"
            )

    # Check if daemon mode is enabled and delegate accordingly
    config = config_manager.load()
    daemon_enabled = config.daemon and config.daemon.enabled

    # Handle --rebuild-fts-index BEFORE general daemon delegation
    if rebuild_fts_index and daemon_enabled:
        from .cli_daemon_delegation import rebuild_fts_via_daemon

        exit_code = rebuild_fts_via_daemon(config_manager, console)
        sys.exit(exit_code)

    if daemon_enabled:
        # Check for unsupported flags in daemon mode
        # Note: rebuild_fts_index is now supported via RPC endpoint
        if rebuild_indexes or rebuild_index:
            console.print(
                "❌ Rebuild flags (--rebuild-indexes, --rebuild-index) "
                "are not yet supported in daemon mode",
                style="red",
            )
            console.print(
                "💡 Use local mode for rebuild operations: cidx config --no-daemon",
                style="yellow",
            )
            sys.exit(1)

        # Delegate to daemon with all parameters
        from .cli_daemon_delegation import _index_via_daemon

        exit_code = _index_via_daemon(
            force_reindex=clear,
            daemon_config=config.daemon.model_dump(),  # config.daemon is guaranteed to exist here
            enable_fts=fts,
            batch_size=batch_size,
            reconcile=reconcile,
            files_count_to_process=files_count_to_process,
            detect_deletions=detect_deletions,
            index_commits=index_commits,
            all_branches=all_branches,
            max_commits=max_commits,
            since_date=since_date,
            diff_context=diff_context,
        )
        sys.exit(exit_code)
    else:
        # Display mode indicator
        console.print("🔧 Running in local mode", style="blue")

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

        # Validate temporal indexing flags
        if all_branches and not index_commits:
            console.print(
                "❌ Cannot use --all-branches without --index-commits",
                style="red",
            )
            console.print(
                "💡 Use: cidx index --index-commits --all-branches",
                style="yellow",
            )
            sys.exit(1)

        if max_commits and not index_commits:
            console.print(
                "❌ Cannot use --max-commits without --index-commits",
                style="red",
            )
            sys.exit(1)

        if since_date and not index_commits:
            console.print(
                "❌ Cannot use --since-date without --index-commits",
                style="red",
            )
            sys.exit(1)

        # Validate --diff-context flag
        if diff_context is not None and not index_commits:
            console.print(
                "❌ Cannot use --diff-context without --index-commits",
                style="red",
            )
            sys.exit(1)

        if diff_context is not None:
            # Validate diff context value
            if diff_context < 0 or diff_context > 50:
                console.print(
                    f"❌ Invalid diff-context {diff_context}. Valid range: 0-50",
                    style="red",
                )
                console.print(
                    "💡 Recommended values: 0 (minimal), 5 (default), 10 (maximum quality)",
                    style="yellow",
                )
                sys.exit(1)

            if diff_context > 20:
                console.print(
                    f"⚠️  Large diff context ({diff_context} lines) will significantly increase storage",
                    style="yellow",
                )
                console.print(
                    "💡 Recommended range: 3-10 lines for best balance", style="dim"
                )

        # Handle --index-commits flag (standalone mode only - daemon delegates above)
        if index_commits:
            try:
                # Lazy import temporal indexing components
                from .services.temporal.temporal_indexer import TemporalIndexer
                from .storage.filesystem_vector_store import FilesystemVectorStore

                config = config_manager.load()

                # Apply diff_context override if provided
                if diff_context is not None:
                    from .config import TemporalConfig

                    if not hasattr(config, "temporal") or config.temporal is None:
                        config.temporal = TemporalConfig(
                            diff_context_lines=diff_context
                        )
                    else:
                        config.temporal.diff_context_lines = diff_context
                    # Update config manager so TemporalIndexer sees the override
                    config_manager._config = config

                # Initialize vector store
                index_dir = config.codebase_dir / ".code-indexer" / "index"
                vector_store = FilesystemVectorStore(
                    base_path=index_dir, project_root=config.codebase_dir
                )

                # Check if --clear flag is set for temporal collection
                if clear:
                    console.print("🧹 Clearing temporal index...", style="cyan")
                    collection_name = "code-indexer-temporal"
                    vector_store.clear_collection(
                        collection_name=collection_name,
                        remove_projection_matrix=False,
                    )
                    # Also remove temporal metadata so indexing starts fresh
                    # Use collection path to consolidate all temporal data
                    collection_path = (
                        config.codebase_dir / ".code-indexer/index" / collection_name
                    )
                    temporal_meta_path = collection_path / "temporal_meta.json"
                    if temporal_meta_path.exists():
                        temporal_meta_path.unlink()

                    # Also remove progressive tracking file (Bug #8 fix)
                    temporal_progress_path = collection_path / "temporal_progress.json"
                    if temporal_progress_path.exists():
                        temporal_progress_path.unlink()

                    console.print("✅ Temporal index cleared", style="green")

                # Initialize temporal indexer
                temporal_indexer = TemporalIndexer(config_manager, vector_store)

                # Cost estimation warning for all-branches (no confirmation prompt)
                if all_branches:
                    # Get branch count for cost warning
                    try:
                        import subprocess

                        result = subprocess.run(
                            ["git", "branch", "-a"],
                            cwd=config.codebase_dir,
                            capture_output=True,
                            text=True,
                            check=True,
                        )
                        branch_count = len(
                            [
                                line
                                for line in result.stdout.split("\n")
                                if line.strip() and not line.strip().startswith("*")
                            ]
                        )

                        if branch_count > 50:
                            console.print(
                                f"⚠️  [yellow]Indexing all branches will process {branch_count} branches[/yellow]",
                                markup=True,
                            )
                            console.print(
                                "   This may significantly increase storage and API costs.",
                                style="yellow",
                            )
                            console.print()
                            # NOTE: Removed confirmation prompt to enable batch/automated usage
                            # Proceeding directly with indexing as requested by user
                    except subprocess.CalledProcessError:
                        pass  # Ignore git command failures

                # Initialize progress managers for rich slot-based display
                from .progress import MultiThreadedProgressManager
                from .progress.progress_display import RichLiveProgressManager

                # Get parallel processing thread count for display slots
                parallel_threads = (
                    getattr(config.voyage_ai, "parallel_requests", 8)
                    if hasattr(config, "voyage_ai")
                    else 8
                )

                # Create Rich Live progress manager for bottom-anchored display
                rich_live_manager = RichLiveProgressManager(console=console)
                progress_manager = MultiThreadedProgressManager(
                    console=console,
                    live_manager=rich_live_manager,
                    max_slots=parallel_threads,  # FIX Issue 1: Match TemporalIndexer's CleanSlotTracker slot count
                )

                display_initialized = False

                def show_setup_message(message: str):
                    """Display setup/informational messages as scrolling cyan text."""
                    rich_live_manager.handle_setup_message(message)

                def update_commit_progress(
                    current: int,
                    total: int,
                    info: str,
                    concurrent_files=None,
                    slot_tracker=None,
                ):
                    """Update commit processing progress with slot-based display."""
                    nonlocal display_initialized

                    # Initialize Rich Live display on first call
                    if not display_initialized:
                        rich_live_manager.start_bottom_display()
                        display_initialized = True

                    # Parse progress info for metrics if available
                    try:
                        # FIX Issue 2: Extract rate from info (handles both "files/s" and "commits/s")
                        # Info format: "current/total commits (%) | X.X commits/s | Y.Y KB/s | ..."
                        parts = info.split(" | ")
                        if len(parts) >= 2:
                            rate_str = parts[1].strip()
                            # Extract numeric value from "X.X commits/s" or "X.X files/s"
                            rate_parts = rate_str.split()
                            if len(rate_parts) >= 1:
                                files_per_second = float(rate_parts[0])
                            else:
                                files_per_second = 0.0
                        else:
                            files_per_second = 0.0

                        # Parse KB/s from parts[2] if available
                        if len(parts) >= 3:
                            kb_str = parts[2].strip()
                            kb_parts = kb_str.split()
                            if len(kb_parts) >= 1:
                                kb_per_second = float(kb_parts[0])
                            else:
                                kb_per_second = 0.0
                        else:
                            kb_per_second = 0.0
                    except (ValueError, IndexError):
                        files_per_second = 0.0
                        kb_per_second = 0.0

                    # Update MultiThreadedProgressManager with rich display
                    progress_manager.update_complete_state(
                        current=current,
                        total=total,
                        files_per_second=files_per_second,
                        kb_per_second=kb_per_second,  # Parsed from info string
                        active_threads=parallel_threads,
                        concurrent_files=concurrent_files or [],
                        slot_tracker=slot_tracker,
                        info=info,
                        item_type="commits",
                    )

                    # Get integrated display content (Rich Table) and update Rich Live bottom-anchored display
                    rich_table = progress_manager.get_integrated_display()
                    rich_live_manager.async_handle_progress_update(rich_table)

                def progress_callback(
                    current: int,
                    total: int,
                    path: Path,
                    info: str = "",
                    concurrent_files=None,
                    slot_tracker=None,
                    item_type: str = "commits",
                ):
                    """Multi-threaded progress callback - uses Rich Live progress display."""
                    # Handle setup messages (total=0)
                    if info and total == 0:
                        show_setup_message(info)
                        return

                    # Handle commit progress (total>0)
                    if total and total > 0:
                        update_commit_progress(
                            current, total, info, concurrent_files, slot_tracker
                        )
                        return

                # Run temporal indexing
                console.print(
                    "🕒 Starting temporal git history indexing...", style="cyan"
                )
                if all_branches:
                    console.print("   Mode: All branches", style="cyan")
                else:
                    console.print("   Mode: Current branch only", style="cyan")

                indexing_result = temporal_indexer.index_commits(
                    all_branches=all_branches,
                    max_commits=max_commits,
                    since_date=since_date,
                    progress_callback=progress_callback,
                    reconcile=reconcile,
                )

                # Stop Rich Live display before showing results
                if display_initialized:
                    rich_live_manager.stop_display()

                # Display results
                console.print()
                console.print("✅ Temporal indexing completed!", style="green bold")
                console.print(
                    f"   Total commits processed: {indexing_result.total_commits}",
                    style="green",
                )
                console.print(
                    f"   Files changed: {indexing_result.files_processed}",
                    style="green",
                )
                console.print(
                    f"   Vectors created (approx): ~{indexing_result.approximate_vectors_created}",
                    style="green",
                )
                console.print(
                    f"   Skip ratio: {indexing_result.skip_ratio:.1%}",
                    style="green",
                )
                console.print(
                    f"   Branches indexed: {', '.join(indexing_result.branches_indexed)}",
                    style="green",
                )
                console.print()

                temporal_indexer.close()
                sys.exit(0)

            except Exception as e:
                # Enhanced error logging for diagnosing Errno 7 and other failures
                import traceback

                error_details = {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "stack_trace": traceback.format_exc(),
                    "errno": getattr(e, "errno", None),
                    "working_directory": str(Path.cwd()),
                }

                # Log to file for debugging
                error_log = (
                    Path.cwd()
                    / ".code-indexer"
                    / f"temporal_error_{int(time.time())}.log"
                )
                error_log.parent.mkdir(parents=True, exist_ok=True)
                with open(error_log, "w") as f:
                    import json

                    json.dump(error_details, f, indent=2)

                console.print(f"❌ Temporal indexing failed: {e}", style="red")
                console.print(f"💾 Error details saved to: {error_log}", style="yellow")

                if (
                    ctx.obj.get("verbose") or True
                ):  # Always show stack trace for debugging
                    console.print(traceback.format_exc())
                sys.exit(1)

    # Handle --rebuild-fts-index flag (early exit path)
    if rebuild_fts_index:
        try:
            config = config_manager.load()

            # Check if indexing progress file exists
            progress_file = config_manager.config_path.parent / "indexing_progress.json"
            if not progress_file.exists():
                console.print("❌ No indexing progress found", style="red")
                console.print(
                    "💡 Run 'cidx index' first to create the semantic index",
                    style="yellow",
                )
                sys.exit(1)

            # Lazy import FTS components
            from .services.tantivy_index_manager import TantivyIndexManager
            from .indexing.file_finder import FileFinder

            console.print("🔍 Discovering files...")

            # Use FileFinder to discover files from disk (respects gitignore, base + override config)
            # This is 60-180x faster than scanning vector JSONs for large codebases
            file_finder = FileFinder(config)
            discovered_files = list(file_finder.find_files())

            if not discovered_files:
                console.print("❌ No files found to index", style="red")
                console.print(
                    "💡 Check your file_extensions and exclude_dirs configuration",
                    style="yellow",
                )
                sys.exit(1)

            console.print("🔧 Rebuilding FTS index...")
            console.print(f"📄 Found {len(discovered_files)} files")

            # Initialize Tantivy manager
            fts_index_dir = config.codebase_dir / ".code-indexer" / "tantivy_index"
            tantivy_manager = TantivyIndexManager(fts_index_dir)

            # Clear and recreate FTS index
            import shutil

            if fts_index_dir.exists():
                console.print("🧹 Clearing existing FTS index...")
                shutil.rmtree(fts_index_dir)

            tantivy_manager.initialize_index(create_new=True)
            console.print("✅ FTS index initialized")

            # Re-index all completed files to FTS
            from rich.progress import (
                Progress,
                BarColumn,
                TextColumn,
                TimeRemainingColumn,
            )

            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Rebuilding FTS index...", total=len(discovered_files)
                )

                indexed_count = 0
                failed_count = 0

                for file_path in discovered_files:
                    try:
                        # Read file content (file_path is already a Path object from FileFinder)
                        if not file_path.exists():
                            failed_count += 1
                            progress.advance(task)
                            continue

                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            content = f.read()

                        # Detect language from file extension
                        extension = file_path.suffix.lstrip(".")
                        language = extension if extension else "unknown"

                        # Create FTS document
                        doc = {
                            "path": str(file_path),
                            "content": content,
                            "content_raw": content,
                            "identifiers": [],  # Empty for now
                            "line_start": 1,
                            "line_end": len(content.splitlines()),
                            "language": language,
                        }

                        # Add to FTS index
                        tantivy_manager.add_document(doc)
                        indexed_count += 1

                    except Exception as e:
                        failed_count += 1
                        console.print(
                            f"⚠️  Failed to index {file_path}: {e}", style="yellow"
                        )

                    progress.advance(task)

                # Commit all documents
                tantivy_manager.commit()

            # Show completion summary
            console.print("\n✅ FTS index rebuilt successfully")
            console.print(f"📄 Files indexed: {indexed_count}")
            if failed_count > 0:
                console.print(f"⚠️  Failed files: {failed_count}", style="yellow")

            sys.exit(0)

        except Exception as e:
            console.print(f"❌ FTS rebuild failed: {e}", style="red")
            import traceback

            if ctx.obj.get("verbose"):
                console.print(traceback.format_exc(), style="dim")
            sys.exit(1)

    try:
        config = config_manager.load()

        # Initialize services - lazy imports for index path
        from .services.smart_indexer import SmartIndexer

        embedding_provider = EmbeddingProviderFactory.create(config, console)
        backend = BackendFactory.create(
            config=config, project_root=Path(config.codebase_dir)
        )
        vector_store_client = backend.get_vector_store_client()

        # Health checks
        if not embedding_provider.health_check():
            provider_name = embedding_provider.get_provider_name().title()
            error_message = get_service_unavailable_message(provider_name, "cidx start")
            console.print(error_message, style="red")
            sys.exit(1)

        if not backend.health_check():
            provider = config.vector_store.provider if config.vector_store else "Qdrant"
            error_message = get_service_unavailable_message(
                provider.title(), "cidx start"
            )
            console.print(error_message, style="red")
            sys.exit(1)

        # Initialize smart indexer with progressive metadata
        metadata_path = config_manager.config_path.parent / "metadata.json"
        smart_indexer = SmartIndexer(
            config, embedding_provider, vector_store_client, metadata_path
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
            rich_live_manager.async_handle_progress_update(
                rich_table
            )  # Bug #470 fix - async queue

        def check_for_interruption():
            """Check if operation was interrupted and return signal."""
            if interrupt_handler and interrupt_handler.interrupted:
                return "INTERRUPT"
            return None

        def progress_callback(  # type: ignore[misc]
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
                collection_name = vector_store_client.resolve_collection_name(
                    config, embedding_provider
                )

                # Handle rebuild index flag
                if rebuild_index:
                    # Check if filesystem backend is being used
                    from .storage.filesystem_vector_store import (
                        FilesystemVectorStore,
                    )

                    if not isinstance(vector_store_client, FilesystemVectorStore):
                        console.print(
                            "❌ --rebuild-index only works with filesystem vector storage",
                            style="red",
                        )
                        console.print(
                            "💡 Current backend does not support index rebuilding",
                            style="yellow",
                        )
                        sys.exit(1)

                    # Get collection path
                    collection_path = vector_store_client.base_path / collection_name
                    if not collection_path.exists():
                        console.print(
                            f"❌ Collection '{collection_name}' not found",
                            style="red",
                        )
                        sys.exit(1)

                    # Load metadata to determine current index type
                    import json

                    metadata_file = collection_path / "collection_meta.json"
                    if not metadata_file.exists():
                        console.print(
                            "❌ Collection metadata not found - collection may be corrupted",
                            style="red",
                        )
                        sys.exit(1)

                    with open(metadata_file) as f:
                        metadata = json.load(f)

                    # Rebuild HNSW index
                    console.print(
                        "🔄 Rebuilding HNSW index from existing vector files..."
                    )
                    from .storage.hnsw_index_manager import (
                        HNSWIndexManager,
                    )

                    try:
                        hnsw_manager = HNSWIndexManager(
                            vector_dim=metadata.get("vector_size", 1536)
                        )
                        vectors_rebuilt = hnsw_manager.rebuild_from_vectors(
                            collection_path
                        )
                        console.print(
                            f"\n✅ HNSW index rebuilt successfully - {vectors_rebuilt} vectors processed"
                        )
                    except Exception as e:
                        console.print(
                            f"\n❌ Failed to rebuild HNSW index: {e}", style="red"
                        )
                        sys.exit(1)
                    return

                # Handle rebuild indexes flag
                if rebuild_indexes:
                    if vector_store_client.rebuild_payload_indexes(collection_name):
                        console.print("Index rebuild completed successfully")
                    else:
                        console.print("Index rebuild failed - check logs for details")
                        sys.exit(1)
                    return

                # For non-clear operations, ensure payload indexes exist before indexing
                # For --clear operations, skip this since collection will be recreated fresh
                if not clear:
                    vector_store_client.ensure_payload_indexes(
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
                    enable_fts=fts,
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
@click.option(
    "--fts",
    is_flag=True,
    help="Enable FTS index updates alongside semantic index (requires tantivy)",
)
@click.pass_context
@require_mode("local", "proxy")
def watch(ctx, debounce: float, batch_size: int, initial_sync: bool, fts: bool):
    """Git-aware watch for file changes with branch support."""
    # Story #472: Re-enabled daemon delegation with non-blocking RPC
    # Watch now runs in background thread in daemon, allowing CLI to return immediately

    # Handle proxy mode (Story 2.2)
    mode = ctx.obj.get("mode")
    if mode == "proxy":
        from .proxy import execute_proxy_command

        project_root = ctx.obj["project_root"]

        # Build args list for watch command
        args = ["--debounce", str(debounce), "--batch-size", str(batch_size)]
        if initial_sync:
            args.append("--initial-sync")
        if fts:
            args.append("--fts")

        exit_code = execute_proxy_command(project_root, "watch", args)
        sys.exit(exit_code)

    config_manager = ctx.obj["config_manager"]
    project_root = ctx.obj.get("project_root", Path.cwd())

    # Try daemon delegation first (Story #472)
    if mode == "local":
        from .cli_daemon_delegation import start_watch_via_daemon

        # Attempt to delegate to daemon (non-blocking mode)
        if start_watch_via_daemon(
            project_root,
            debounce_seconds=debounce,
            batch_size=batch_size,
            initial_sync=initial_sync,
            fts=fts,
        ):
            # Successfully delegated to daemon - exit immediately
            sys.exit(0)

    # Fall back to standalone mode if daemon delegation failed

    # Deprecation warning for --fts flag (auto-detection replaces it)
    if fts:
        console.print(
            "⚠️ --fts flag is deprecated. Auto-detection is now used.",
            style="yellow",
        )

    # Auto-detect existing indexes
    from .cli_watch_helpers import detect_existing_indexes

    available_indexes = detect_existing_indexes(project_root)
    detected_count = sum(available_indexes.values())

    if detected_count == 0:
        console.print("⚠️ No indexes found. Run 'cidx index' first.", style="yellow")
        sys.exit(1)

    console.print(f"🔍 Detected {detected_count} index(es) to watch:", style="blue")

    try:
        from watchdog.observers import Observer

        # Import git-aware components
        from .services.git_topology_service import GitTopologyService
        from .services.watch_metadata import WatchMetadata
        from .services.git_aware_watch_handler import GitAwareWatchHandler

        config = config_manager.load()

        # Lazy imports for watch services
        from .services.smart_indexer import SmartIndexer

        # Display detected indexes
        if available_indexes["semantic"]:
            console.print("  ✅ Semantic index (HEAD collection)", style="green")
        if available_indexes["fts"]:
            console.print("  ✅ FTS index (full-text search)", style="green")
        if available_indexes["temporal"]:
            console.print("  ✅ Temporal index (git history commits)", style="green")

        # Initialize services only if semantic index exists (primary index)
        semantic_handler = None
        fts_watch_handler = None
        temporal_watch_handler = None
        git_topology_service = None
        git_state = None
        watch_metadata = None
        watch_metadata_path = None

        if available_indexes["semantic"]:
            # Initialize services (same as index command)
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
            watch_metadata_path = (
                config_manager.config_path.parent / "watch_metadata.json"
            )
            watch_metadata = WatchMetadata.load_from_disk(watch_metadata_path)

        # Initialize semantic watch handler
        if available_indexes["semantic"]:
            # Ensure all required variables are initialized
            assert (
                git_topology_service is not None
            ), "git_topology_service not initialized"
            assert watch_metadata is not None, "watch_metadata not initialized"

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
                    # Auto-enable FTS if index exists
                    enable_fts_sync = fts or available_indexes["fts"]
                    stats = smart_indexer.smart_index(
                        batch_size=batch_size, quiet=True, enable_fts=enable_fts_sync
                    )
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
            semantic_handler = GitAwareWatchHandler(
                config=config,
                smart_indexer=smart_indexer,
                git_topology_service=git_topology_service,
                watch_metadata=watch_metadata,
                debounce_seconds=debounce,
            )

        # Initialize FTS watch handler if auto-detected or requested
        if available_indexes["fts"] or fts:
            # Lazy import FTS components
            from .services.fts_watch_handler import FTSWatchHandler
            from .services.tantivy_index_manager import TantivyIndexManager

            fts_index_dir = config.codebase_dir / ".code-indexer" / "tantivy_index"
            tantivy_manager = TantivyIndexManager(fts_index_dir)

            # Initialize or open existing index
            if fts_index_dir.exists():
                tantivy_manager.initialize_index(create_new=False)
            else:
                tantivy_manager.initialize_index(create_new=True)

            fts_watch_handler = FTSWatchHandler(
                tantivy_index_manager=tantivy_manager,
                config=config,
            )

        # Initialize temporal watch handler if auto-detected
        if available_indexes["temporal"]:
            # Lazy import temporal components
            from .cli_temporal_watch_handler import TemporalWatchHandler
            from .services.temporal.temporal_indexer import TemporalIndexer
            from .services.temporal.temporal_progressive_metadata import (
                TemporalProgressiveMetadata,
            )
            from .storage.filesystem_vector_store import FilesystemVectorStore

            # Initialize vector store with base_path (not collection path)
            # This allows temporal_indexer to create the correct temporal_dir
            index_dir = project_root / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(
                base_path=index_dir, project_root=project_root
            )

            # Create temporal indexer (using new API)
            temporal_indexer = TemporalIndexer(config_manager, vector_store)

            # Create progressive metadata using temporal_indexer's consolidated dir
            progressive_metadata = TemporalProgressiveMetadata(
                temporal_indexer.temporal_dir
            )

            # Create TemporalWatchHandler
            temporal_watch_handler = TemporalWatchHandler(
                project_root,
                temporal_indexer=temporal_indexer,
                progressive_metadata=progressive_metadata,
            )

            # Show temporal handler status
            if temporal_watch_handler.use_polling:
                console.print(
                    "  ⚠️  Temporal: Using polling fallback (refs file not found)"
                )
            else:
                console.print(
                    f"  ✅ Temporal: Monitoring {temporal_watch_handler.git_refs_file.name}"
                )

        console.print(f"\n👀 Starting watch on {config.codebase_dir}")
        console.print(f"⏱️  Debounce: {debounce}s")
        if (
            available_indexes["semantic"]
            and git_topology_service is not None
            and git_topology_service.is_git_available()
            and git_state is not None
        ):
            console.print(
                f"🌿 Git branch: {git_state.get('current_branch', 'unknown')}"
            )
        console.print("Press Ctrl+C to stop")

        # Start git-aware file watching (semantic handler)
        if semantic_handler:
            semantic_handler.start_watching()

        # Setup watchdog observer
        observer = Observer()

        # Register semantic handler
        if semantic_handler:
            observer.schedule(
                semantic_handler, str(config.codebase_dir), recursive=True
            )

        # Register FTS handler if enabled
        if fts_watch_handler:
            observer.schedule(
                fts_watch_handler, str(config.codebase_dir), recursive=True
            )

        # Register temporal handler if enabled
        if temporal_watch_handler:
            observer.schedule(temporal_watch_handler, str(project_root), recursive=True)

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
            console.print("\n👋 Stopping watch mode...")
        finally:
            # Stop semantic handler if present
            if semantic_handler:
                semantic_handler.stop_watching()

            observer.stop()
            observer.join()

            # Save final metadata if semantic handler was active
            if available_indexes["semantic"] and watch_metadata and watch_metadata_path:
                watch_metadata.save_to_disk(watch_metadata_path)

                if semantic_handler:
                    # Show final statistics
                    watch_stats = semantic_handler.get_statistics()
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


# Story 2.1 Display Helper Functions


def _display_file_chunk_match(result, index, temporal_service):
    """Display a file chunk temporal match with diff."""
    file_path = result.metadata.get("path") or result.metadata.get(
        "file_path", "unknown"
    )
    line_start = result.metadata.get("line_start", 0)
    line_end = result.metadata.get("line_end", 0)
    commit_hash = result.metadata.get("commit_hash", "")

    # Get diff_type from metadata to display marker
    diff_type = result.metadata.get("diff_type", "unknown")

    # Get commit details from result.temporal_context (Story 2: no SQLite)
    # The temporal_context is populated from payload data by temporal_search_service
    temporal_ctx = getattr(result, "temporal_context", {})
    commit_date = temporal_ctx.get("commit_date", "Unknown")
    author_name = temporal_ctx.get("author_name", "Unknown")
    commit_message = temporal_ctx.get("commit_message", "[No message available]")

    # For backward compatibility, check metadata too
    if author_name == "Unknown" and "author_name" in result.metadata:
        author_name = result.metadata.get("author_name", "Unknown")
    if commit_date == "Unknown" and "commit_date" in result.metadata:
        commit_date = result.metadata.get("commit_date", "Unknown")
    if (
        commit_message == "[No message available]"
        and "commit_message" in result.metadata
    ):
        commit_message = result.metadata.get("commit_message", "[No message available]")

    # Get author email from metadata
    author_email = result.metadata.get("author_email", "unknown@example.com")

    # Smart line number display: suppress :0-0 for temporal diffs
    if line_start == 0 and line_end == 0:
        # Temporal diffs have no specific line range - suppress :0-0
        file_location = file_path
    else:
        # Regular results or temporal with specific lines - show range
        file_location = f"{file_path}:{line_start}-{line_end}"

    # Display header with diff-type marker (Story 2 requirement)
    diff_markers = {
        "added": "[ADDED]",
        "deleted": "[DELETED]",
        "modified": "[MODIFIED]",
        "renamed": "[RENAMED]",
        "binary": "[BINARY]",
    }
    marker = diff_markers.get(diff_type, "")

    if marker:
        console.print(f"\n[bold cyan]{index}. {file_location}[/bold cyan] {marker}")
    else:
        console.print(f"\n[bold cyan]{index}. {file_location}[/bold cyan]")
    console.print(f"   Score: {result.score:.3f}")
    console.print(f"   Commit: {commit_hash[:7]} ({commit_date})")
    console.print(f"   Author: {author_name} <{author_email}>")

    # Display full commit message (NOT truncated)
    # Bug #4 fix: Use markup=False to prevent Rich from interpreting special chars
    message_lines = commit_message.split("\n")
    console.print(f"   Message: {message_lines[0]}", markup=False)
    for msg_line in message_lines[1:]:
        console.print(f"            {msg_line}", markup=False)

    console.print()

    # Display rename indicator if present
    if "display_note" in result.metadata:
        console.print(f"   {result.metadata['display_note']}", style="yellow")
        console.print()

    # Display content (Story 2: No diff generation, just show content)
    # All results in temporal index are changes by definition
    console.print()
    content = result.content
    lines = content.split("\n")

    # Modified diffs are self-documenting with @@ markers and +/- prefixes
    # Suppress line numbers for them to avoid confusion
    show_line_numbers = diff_type != "modified"

    # Bug #4 fix: Use markup=False to prevent Rich from interpreting special chars in diff content
    if show_line_numbers:
        for i, line in enumerate(lines):
            line_num = line_start + i
            console.print(f"{line_num:4d}  {line}", markup=False)
    else:
        # Modified diff - no line numbers (diff markers are self-documenting)
        for line in lines:
            console.print(f"  {line}", markup=False)


def _display_commit_message_match(result, index, temporal_service):
    """Display a commit message temporal match."""
    commit_hash = result.metadata.get("commit_hash", "")

    # Get commit details from result.temporal_context (Story 2: no SQLite)
    temporal_ctx = getattr(result, "temporal_context", {})
    commit_date = temporal_ctx.get(
        "commit_date", result.metadata.get("commit_date", "Unknown")
    )
    author_name = temporal_ctx.get(
        "author_name", result.metadata.get("author_name", "Unknown")
    )
    author_email = result.metadata.get("author_email", "unknown@example.com")

    # Display header
    console.print(f"\n[bold cyan]{index}. [COMMIT MESSAGE MATCH][/bold cyan]")
    console.print(f"   Score: {result.score:.3f}")
    console.print(f"   Commit: {commit_hash[:7]} ({commit_date})")
    console.print(f"   Author: {author_name} <{author_email}>")
    console.print()

    # Display matching section of commit message
    # Bug #4 fix: Use markup=False to prevent Rich from interpreting special chars
    console.print("   Message (matching section):")
    for line in result.content.split("\n"):
        console.print(f"   {line}", markup=False)
    console.print()

    # Story 2: No file changes available from diff-based indexing
    # The temporal index only tracks what changed, not full file lists
    console.print("   [dim]File changes tracked in diff-based index[/dim]")


def display_temporal_results(results, temporal_service):
    """Display temporal search results with proper ordering."""
    # Separate results by type
    commit_msg_matches = []
    file_chunk_matches = []

    for result in results.results:
        match_type = result.metadata.get("type", "file_chunk")
        if match_type == "commit_message":
            commit_msg_matches.append(result)
        else:
            file_chunk_matches.append(result)

    # Display commit messages first, then file chunks
    index = 1

    for result in commit_msg_matches:
        _display_commit_message_match(result, index, temporal_service)
        index += 1

    for result in file_chunk_matches:
        _display_file_chunk_match(result, index, temporal_service)
        index += 1


@cli.command()
@click.argument("query")
@click.option(
    "--limit",
    "-l",
    default=10,
    help="Number of results to return (default: 10, use 0 for unlimited grep-like output)",
)
@click.option(
    "--language",
    "languages",
    multiple=True,
    help=_generate_language_help_text()
    + " Can be specified multiple times to include multiple languages. Example: --language python --language go",
)
@click.option(
    "--exclude-language",
    "exclude_languages",
    multiple=True,
    help="Exclude files of specified language(s). Can be specified multiple times to exclude multiple languages. Example: --exclude-language javascript --exclude-language typescript",
)
@click.option(
    "--path-filter",
    "path_filter",
    multiple=True,
    help="Filter by file path pattern (e.g., */tests/*). Can be specified multiple times for OR logic.",
)
@click.option(
    "--exclude-path",
    "exclude_paths",
    multiple=True,
    help="Exclude files matching path pattern(s). Supports glob patterns (*, **, ?, [seq]). Can be specified multiple times. Example: --exclude-path '*/tests/*' --exclude-path '*.min.js'",
)
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
@click.option(
    "--fts",
    is_flag=True,
    help="Use full-text search instead of semantic search (requires Tantivy index)",
)
@click.option(
    "--semantic",
    is_flag=True,
    help="Use semantic search (default). Combine with --fts for hybrid search.",
)
@click.option(
    "--case-sensitive",
    is_flag=True,
    help="Enable case-sensitive matching for FTS queries",
)
@click.option(
    "--case-insensitive",
    is_flag=True,
    help="Force case-insensitive matching for FTS queries (default behavior)",
)
@click.option(
    "--fuzzy",
    is_flag=True,
    help="Enable fuzzy matching with edit distance of 1 (typo tolerance)",
)
@click.option(
    "--edit-distance",
    type=int,
    default=0,
    help="Fuzzy match tolerance (0-3): 0=exact, 1=1 typo, 2=2 typos, 3=3 typos",
)
@click.option(
    "--snippet-lines",
    type=int,
    default=5,
    help="Context lines to show around matches (0=list only, 1-50=show context)",
)
@click.option(
    "--regex",
    is_flag=True,
    help="Interpret query as regex pattern (FTS only, incompatible with --semantic or --fuzzy)",
)
@click.option(
    "--time-range",
    type=str,
    help="Filter results by time range in format YYYY-MM-DD..YYYY-MM-DD (requires temporal index)",
)
@click.option(
    "--time-range-all",
    is_flag=True,
    help="Query entire temporal history (shortcut for full date range)",
)
@click.option(
    "--diff-type",
    "diff_types",
    multiple=True,
    help="Filter by diff type: added, modified, deleted, renamed, binary (requires temporal index). Can be specified multiple times. Example: --diff-type added --diff-type modified",
)
@click.option(
    "--author",
    type=str,
    help="Filter by commit author name or email (requires temporal index). Example: --author 'John Doe'",
)
@click.option(
    "--chunk-type",
    type=click.Choice(["commit_message", "commit_diff"], case_sensitive=False),
    help="Filter by chunk type: commit_message (commit descriptions) or commit_diff (code changes). Requires --time-range or --time-range-all.",
)
# --show-unchanged removed: Story 2 - all temporal results are changes now
@click.pass_context
@require_mode("local", "remote", "proxy")
def query(
    ctx,
    query: str,
    limit: int,
    languages: tuple,
    exclude_languages: tuple,
    path_filter: tuple,
    exclude_paths: tuple,
    min_score: Optional[float],
    accuracy: str,
    quiet: bool,
    fts: bool,
    semantic: bool,
    case_sensitive: bool,
    case_insensitive: bool,
    fuzzy: bool,
    edit_distance: int,
    snippet_lines: int,
    regex: bool,
    time_range: Optional[str],
    time_range_all: bool,
    diff_types: tuple,
    author: Optional[str],
    chunk_type: Optional[str],
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
      • Exclude: --exclude-language javascript (exclude JavaScript files)
      • Path: --path-filter */tests/* (searches only test directories)
      • Exclude Path: --exclude-path '*/tests/*' (exclude test directories)
      • Score: --min-score 0.8 (only high-confidence matches)
      • Limit: --limit 20 (more results)
      • Accuracy: --accuracy high (higher accuracy, slower search)

    \b
    FILTER COMBINATIONS (Story 3.1):
      • Combine inclusions and exclusions for precise targeting
      • Multiple filters are supported and work together
      • Exclusions always override inclusions
      • Automatic conflict detection warns about contradictions

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
      code-indexer query "test" --path-filter */tests/* --limit 5
      code-indexer query "async" --min-score 0.8
      code-indexer query "auth" --exclude-language javascript
      code-indexer query "config" --exclude-language js --exclude-language ts
      code-indexer query "api" --exclude-path '*/tests/*' --exclude-path '*.min.js'
      code-indexer query "function" --quiet  # Just score, path, and content

    \b
    ADVANCED FILTER COMBINATIONS:
      # Python files, excluding tests
      code-indexer query "database" --language python --exclude-path '*/tests/*'

      # Source files only, excluding JavaScript and TypeScript
      code-indexer query "api" --path-filter '*/src/*' --exclude-language js --exclude-language ts

      # Complex targeting with multiple filters
      code-indexer query "handler" --language python --language go --exclude-path '*/vendor/*' --exclude-path '*/node_modules/*'

    Results show file paths, matched content, and similarity scores.
    Filter conflicts are automatically detected and warnings are displayed.
    """
    # AC5: Validate --chunk-type requires temporal flags (Story #476)
    if chunk_type and not (time_range or time_range_all):
        console = Console()
        console.print(
            "[red]❌ Error: --chunk-type requires --time-range or --time-range-all[/red]"
        )
        console.print()
        console.print("Usage examples:")
        console.print(
            "  [cyan]cidx query 'bug fix' --time-range-all --chunk-type commit_message[/cyan]"
        )
        console.print(
            "  [cyan]cidx query 'refactor' --time-range 2024-01-01..2024-12-31 --chunk-type commit_diff[/cyan]"
        )
        sys.exit(1)

    # Get mode information from context
    mode = ctx.obj.get("mode", "uninitialized")
    project_root = ctx.obj.get("project_root")

    # Import Path - needed by all query modes
    from pathlib import Path

    # Initialize console for output (needed by multiple code paths)
    console = Console()

    # Check daemon delegation for local mode (Story 2.3 + Story 1: Temporal Support)
    # CRITICAL: Skip daemon delegation if standalone flag is set (prevents recursive loop)
    standalone_mode = ctx.obj.get("standalone", False)

    # Handle --time-range-all flag BEFORE daemon delegation check
    if time_range_all:
        # Set time_range to "all" internally
        time_range = "all"

    if mode == "local" and not standalone_mode:
        try:
            config_manager = ctx.obj.get("config_manager")
            if config_manager:
                daemon_config = config_manager.get_daemon_config()
                if daemon_config and daemon_config.get("enabled"):
                    # Display mode indicator (unless --quiet flag is set)
                    if not quiet:
                        console.print("🔧 Running in daemon mode", style="blue")

                    # Delegate based on query type
                    if time_range:
                        # Story 1: Delegate temporal query to daemon
                        exit_code = cli_daemon_delegation._query_temporal_via_daemon(
                            query_text=query,
                            time_range=time_range,
                            daemon_config=daemon_config,
                            project_root=project_root,
                            limit=limit,
                            languages=languages,
                            exclude_languages=exclude_languages,
                            path_filter=path_filter,
                            exclude_path=exclude_paths,
                            min_score=min_score,
                            accuracy=accuracy,
                            chunk_type=chunk_type,
                            quiet=quiet,
                        )
                        sys.exit(exit_code)
                    else:
                        # Existing: Delegate HEAD query to daemon
                        exit_code = cli_daemon_delegation._query_via_daemon(
                            query_text=query,
                            daemon_config=daemon_config,
                            fts=fts,
                            semantic=semantic,
                            limit=limit,
                            languages=languages,
                            exclude_languages=exclude_languages,
                            path_filter=path_filter,
                            exclude_paths=exclude_paths,
                            min_score=min_score,
                            accuracy=accuracy,
                            quiet=quiet,
                            case_sensitive=case_sensitive,
                            edit_distance=edit_distance,
                            snippet_lines=snippet_lines,
                            regex=regex,
                        )
                        sys.exit(exit_code)
        except Exception:
            # Daemon delegation failed, continue with standalone mode
            pass

    # Handle temporal search with time-range filtering (Story 2.1)
    if time_range:
        # Temporal search only supported in local mode
        if mode != "local":
            console.print(
                "[yellow]⚠️  Temporal search is only supported in local mode[/yellow]"
            )
            sys.exit(1)

        # Lazy import temporal search service
        from .services.temporal.temporal_search_service import (
            TemporalSearchService,
        )

        # Initialize config manager and temporal service
        config_manager = ctx.obj.get("config_manager")
        if not config_manager:
            console.print("[red]❌ Configuration manager not available[/red]")
            sys.exit(1)

        # Initialize vector store client for temporal service
        config = config_manager.get_config()
        index_dir = config.codebase_dir / ".code-indexer" / "index"

        # Import FilesystemVectorStore lazily
        from .storage.filesystem_vector_store import FilesystemVectorStore

        vector_store_client = FilesystemVectorStore(
            base_path=index_dir, project_root=config.codebase_dir
        )

        temporal_service = TemporalSearchService(
            config_manager=config_manager,
            project_root=Path(project_root),
            vector_store_client=vector_store_client,
        )

        # Check if temporal index exists
        if not temporal_service.has_temporal_index():
            console.print("[yellow]⚠️  Temporal index not found[/yellow]")
            console.print()
            console.print("Time-range filtering requires a temporal index.")
            console.print(
                "Falling back to space-only search (current code state only)."
            )
            console.print()
            console.print("To enable temporal queries, build the temporal index:")
            console.print("  [cyan]cidx index --index-commits[/cyan]")
            console.print()
            # Fall through to regular search without time-range filtering
            time_range = None
        else:
            # Handle time_range="all" from --time-range-all flag
            if time_range == "all":
                # Query entire temporal history - get min and max dates from commits.db
                # For now, use a very wide range (will be improved in future)
                start_date = "1970-01-01"
                end_date = "2100-12-31"
                if not quiet:
                    console.print("🕒 Searching entire temporal history...")
            else:
                # Validate date range format
                try:
                    start_date, end_date = temporal_service._validate_date_range(
                        time_range
                    )
                except ValueError as e:
                    console.print(f"[red]❌ Invalid time range: {e}[/red]")
                    console.print()
                    console.print("Use format: YYYY-MM-DD..YYYY-MM-DD")
                    console.print(
                        "Example: [cyan]cidx query 'auth' --time-range 2023-01-01..2024-01-01[/cyan]"
                    )
                    sys.exit(1)

            # Initialize vector store and embedding provider for temporal queries
            # Use the same pattern as regular query command
            config = config_manager.load()
            embedding_provider = EmbeddingProviderFactory.create(config, console)
            backend = BackendFactory.create(
                config=config, project_root=Path(config.codebase_dir)
            )
            vector_store_client = backend.get_vector_store_client()

            # Health checks
            if not embedding_provider.health_check():
                if not quiet:
                    console.print(
                        f"[yellow]⚠️  {embedding_provider.get_provider_name().title()} service not available[/yellow]"
                    )
                sys.exit(1)

            if not vector_store_client.health_check():
                if not quiet:
                    console.print(
                        "[yellow]⚠️  Vector store service not available[/yellow]"
                    )
                sys.exit(1)

            # Use TEMPORAL collection name (not HEAD collection)
            # Import here to get constant
            from .services.temporal.temporal_search_service import (
                TemporalSearchService as TSS,
            )

            collection_name = TSS.TEMPORAL_COLLECTION_NAME

            # Re-initialize temporal service with vector store dependencies
            temporal_service = TemporalSearchService(
                config_manager=config_manager,
                project_root=Path(project_root),
                vector_store_client=vector_store_client,
                embedding_provider=embedding_provider,
                collection_name=collection_name,
            )

            # Execute temporal query
            if not quiet:
                if time_range != "all":
                    console.print(
                        f"🕒 Searching code from {start_date} to {end_date}..."
                    )
                # Story 2: All temporal results are changes now
                console.print("   Showing changed chunks only (diff-based indexing)")

            temporal_results = temporal_service.query_temporal(
                query=query,
                time_range=(start_date, end_date),
                limit=limit,
                min_score=min_score,
                # show_unchanged removed: Story 2
                language=list(languages) if languages else None,
                exclude_language=list(exclude_languages) if exclude_languages else None,
                path_filter=list(path_filter) if path_filter else None,
                exclude_path=list(exclude_paths) if exclude_paths else None,
                diff_types=list(diff_types) if diff_types else None,
                author=author,
                chunk_type=chunk_type,  # AC3/AC4: Filter by chunk type (Story #476)
            )

            # Display results
            if not quiet:
                console.print()
                if temporal_results.performance:
                    perf = temporal_results.performance
                    console.print(
                        f"⚡ Search completed in {perf['total_ms']:.1f}ms "
                        f"(semantic: {perf['semantic_search_ms']:.1f}ms, "
                        f"temporal filter: {perf['temporal_filter_ms']:.1f}ms)"
                    )
                console.print(
                    f"📊 Found {len(temporal_results.results)} results (total matches: {temporal_results.total_found})"
                )
                console.print()

            # Display results using new Story 2.1 implementation
            if not quiet:
                display_temporal_results(temporal_results, temporal_service)
            else:
                # Quiet mode: show match numbers and commit hash (not placeholder)
                # Bug #4 fix: Use markup=False to prevent Rich from interpreting special chars
                for index, temporal_result in enumerate(
                    temporal_results.results, start=1
                ):
                    # Use type field to determine display (Bug #3 fix)
                    # Commit messages have type="commit_message", diffs have type="commit_diff"
                    match_type = temporal_result.metadata.get("type", "commit_diff")
                    if match_type == "commit_message":
                        # Extract ALL commit metadata
                        commit_hash = temporal_result.metadata.get(
                            "commit_hash", "unknown"
                        )
                        temporal_ctx = getattr(temporal_result, "temporal_context", {})
                        commit_date = temporal_ctx.get(
                            "commit_date",
                            temporal_result.metadata.get("commit_date", "Unknown"),
                        )
                        author_name = temporal_ctx.get(
                            "author_name",
                            temporal_result.metadata.get("author_name", "Unknown"),
                        )
                        author_email = temporal_result.metadata.get(
                            "author_email", "unknown@example.com"
                        )

                        # Header line with ALL metadata
                        console.print(
                            f"{index}. {temporal_result.score:.3f} [Commit {commit_hash[:7]}] ({commit_date}) {author_name} <{author_email}>",
                            markup=False,
                        )

                        # Display ENTIRE commit message content (all lines, indented)
                        for line in temporal_result.content.split("\n"):
                            console.print(f"   {line}", markup=False)

                        # Blank line between results
                        console.print()
                    else:
                        # For commit_diff, use the file_path attribute (populated from "path" field)
                        console.print(
                            f"{index}. {temporal_result.score:.3f} {temporal_result.file_path}",
                            markup=False,
                        )

            sys.exit(0)

    # Determine search mode based on flags (Story 4)
    if fts and semantic:
        search_mode = "hybrid"
    elif fts:
        search_mode = "fts"
    else:
        search_mode = "semantic"  # Default behavior

    # Validate --regex flag compatibility
    if regex:
        # Regex requires FTS mode
        if not fts:
            console.print(
                "[red]❌ --regex requires --fts flag (regex is only available for full-text search)[/red]"
            )
            console.print()
            console.print("Use:")
            console.print(
                "  [cyan]cidx query 'pattern' --fts --regex[/cyan]     # Regex search"
            )
            console.print()
            console.print(
                "For semantic search, remove --regex and use natural language:"
            )
            console.print("  [cyan]cidx query 'function definition'[/cyan]")
            sys.exit(1)

        # Regex incompatible with semantic (hybrid mode)
        if semantic:
            console.print("[red]❌ Cannot combine --regex with --semantic[/red]")
            console.print()
            console.print("Regex matching only works with FTS (--fts).")
            console.print("Remove --semantic or --regex flag.")
            console.print()
            console.print("Use one of:")
            console.print(
                "  [cyan]cidx query 'pattern' --fts --regex[/cyan]      # Regex search only"
            )
            console.print(
                "  [cyan]cidx query 'text' --fts --semantic[/cyan]      # Hybrid search"
            )
            sys.exit(1)

        # Regex incompatible with fuzzy matching
        if fuzzy or edit_distance > 0:
            console.print(
                "[red]❌ Cannot combine --regex with --fuzzy or --edit-distance[/red]"
            )
            console.print()
            console.print("Regex provides its own pattern matching capabilities.")
            console.print("Remove --fuzzy/--edit-distance or --regex flag.")
            console.print()
            console.print("Use one of:")
            console.print(
                "  [cyan]cidx query 'pattern' --fts --regex[/cyan]      # Regex matching"
            )
            console.print(
                "  [cyan]cidx query 'term' --fts --fuzzy[/cyan]         # Fuzzy matching"
            )
            sys.exit(1)

    # Handle FTS/Hybrid query (Stories 3 & 4)
    if search_mode in ["fts", "hybrid"]:
        # FTS only supported in local mode currently
        if mode != "local":
            console.print(
                "[yellow]⚠️  Full-text search is only supported in local mode[/yellow]"
            )
            sys.exit(1)

        # Lazy import - only load when --fts used
        from .services.tantivy_index_manager import TantivyIndexManager

        # Check if FTS index exists
        config_dir = Path(project_root) / ".code-indexer"
        fts_index_dir = config_dir / "tantivy_index"

        # Graceful degradation for hybrid mode (Story 4 AC#4)
        if not fts_index_dir.exists():
            if search_mode == "hybrid":
                console.print(
                    "[yellow]⚠️  FTS index not available, falling back to semantic-only search[/yellow]"
                )
                console.print(
                    "[dim]   To enable hybrid search, build the FTS index first: cidx index --fts[/dim]"
                )
                search_mode = "semantic"
            else:
                console.print("[red]❌ FTS index not found[/red]")
                console.print()
                console.print("To use full-text search, first build the FTS index:")
                console.print()
                console.print("  [cyan]cidx index --fts[/cyan]")
                console.print()
                console.print("This will create both semantic and FTS indexes.")
                console.print("For more info: [cyan]cidx index --help[/cyan]")
                sys.exit(1)

        # Only validate FTS-specific flags if we're actually using FTS
        if search_mode in ["fts", "hybrid"]:
            # Validate conflicting flags
            if case_sensitive and case_insensitive:
                console.print(
                    "[red]❌ Cannot use both --case-sensitive and --case-insensitive[/red]"
                )
                console.print()
                console.print("Use one of:")
                console.print(
                    "  [cyan]cidx query 'term' --fts[/cyan]                      # Case-insensitive (default)"
                )
                console.print(
                    "  [cyan]cidx query 'term' --fts --case-sensitive[/cyan]     # Case-sensitive"
                )
                sys.exit(1)

            # Validate edit_distance range
            if not (0 <= edit_distance <= 3):
                console.print(
                    f"[red]❌ --edit-distance must be between 0 and 3 (got {edit_distance})[/red]"
                )
                console.print()
                console.print("Valid values:")
                console.print("  0 = Exact match (default)")
                console.print("  1 = Allow 1 character difference")
                console.print("  2 = Allow 2 character differences")
                console.print("  3 = Allow 3 character differences")
                sys.exit(1)

            # Validate snippet_lines range
            if not (0 <= snippet_lines <= 50):
                console.print(
                    f"[red]❌ --snippet-lines must be between 0 and 50 (got {snippet_lines})[/red]"
                )
                console.print()
                console.print("Valid values:")
                console.print("  0  = List files only (no content snippets)")
                console.print("  5  = Show 5 lines of context (default)")
                console.print("  10 = Show 10 lines of context")
                sys.exit(1)

            # Handle --fuzzy flag as shorthand for --edit-distance 1
            if fuzzy and edit_distance == 0:
                edit_distance = 1

        # Execute hybrid search (Story 4 AC#1 & AC#5 - TRUE PARALLEL EXECUTION)
        if search_mode == "hybrid":
            from concurrent.futures import ThreadPoolExecutor

            # Convert languages tuple to single language (FTS uses first language if multiple)
            language_filter = languages[0] if languages else None

            # Define FTS search function for parallel execution
            def execute_fts():
                try:
                    tantivy_manager = TantivyIndexManager(fts_index_dir)
                    tantivy_manager.initialize_index(create_new=False)
                    return tantivy_manager.search(
                        query_text=query,
                        case_sensitive=case_sensitive,
                        edit_distance=edit_distance,
                        snippet_lines=snippet_lines,
                        limit=limit,
                        language_filter=language_filter,
                        path_filters=list(path_filter) if path_filter else None,
                        exclude_paths=list(exclude_paths) if exclude_paths else None,
                        use_regex=regex,  # Pass regex flag
                    )
                except Exception as e:
                    console.print(f"[yellow]⚠️  FTS search failed: {e}[/yellow]")
                    return []

            # Execute BOTH searches in parallel (AC#5 - CRITICAL: Not sequential!)
            # Both FTS and semantic run simultaneously, not one after the other
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Submit BOTH searches simultaneously
                fts_future = executor.submit(execute_fts)
                semantic_future = executor.submit(
                    _execute_semantic_search,
                    query=query,
                    limit=limit,
                    languages=languages,
                    exclude_languages=exclude_languages,
                    path_filter=path_filter,
                    exclude_paths=exclude_paths,
                    min_score=min_score,
                    accuracy=accuracy,
                    quiet=quiet,
                    project_root=project_root,
                    config_manager=ctx.obj["config_manager"],
                    console=console,
                )

                # Wait for BOTH to complete (parallel execution)
                try:
                    fts_results = fts_future.result()
                except Exception as e:
                    console.print(f"[yellow]⚠️  FTS search failed: {e}[/yellow]")
                    fts_results = []

                try:
                    semantic_results = semantic_future.result()
                except Exception as e:
                    console.print(f"[yellow]⚠️  Semantic search failed: {e}[/yellow]")
                    semantic_results = []

            # Display hybrid results with clear separation (AC#2)
            _display_hybrid_results(
                fts_results=fts_results,
                semantic_results=semantic_results,
                quiet=quiet,
                console=console,
            )
            sys.exit(0)  # Exit after hybrid display (no fall-through to semantic logic)

        # Execute FTS-only search (Story 3)
        elif search_mode == "fts":
            # Convert friendly language names to file extensions using LanguageMapper
            language_extensions = None
            if languages:
                from .services.language_mapper import LanguageMapper

                mapper = LanguageMapper()
                # Expand all languages to their extensions
                all_extensions = set()
                for lang in languages:
                    all_extensions.update(mapper.get_extensions(lang))
                language_extensions = list(all_extensions) if all_extensions else None

            try:
                tantivy_manager = TantivyIndexManager(fts_index_dir)
                tantivy_manager.initialize_index(create_new=False)
                fts_results = tantivy_manager.search(
                    query_text=query,
                    case_sensitive=case_sensitive,
                    edit_distance=edit_distance,
                    snippet_lines=snippet_lines,
                    limit=limit,
                    languages=language_extensions,
                    path_filters=list(path_filter) if path_filter else None,
                    exclude_paths=list(exclude_paths) if exclude_paths else None,
                    exclude_languages=(
                        list(exclude_languages) if exclude_languages else None
                    ),
                    use_regex=regex,  # Pass regex flag
                )

                # Display results
                _display_fts_results(fts_results, quiet=quiet, console=console)
                sys.exit(0)

            except Exception as e:
                console.print(f"[red]❌ FTS query failed: {e}[/red]")
                import traceback

                console.print(traceback.format_exc())
                sys.exit(1)
    # Handle proxy mode (Story 2.2)
    if mode == "proxy":
        from .proxy import execute_proxy_command

        # Build args list from command parameters
        args = [query, "--limit", str(limit)]
        for lang in languages:
            args.extend(["--language", lang])
        if path_filter:
            for pf in path_filter:
                args.extend(["--path-filter", pf])
        for exclude_path in exclude_paths:
            args.extend(["--exclude-path", exclude_path])
        if min_score is not None:
            args.extend(["--min-score", str(min_score)])
        if accuracy != "balanced":
            args.extend(["--accuracy", accuracy])
        if quiet:
            args.append("--quiet")

        exit_code = execute_proxy_command(project_root, "query", args)
        sys.exit(exit_code)

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
            from typing import cast

            from .remote.query_execution import execute_remote_query
            from .server.models.api_models import QueryResultItem

            # NOTE: Remote query API currently supports single language only
            # Use first language from tuple, ignore additional languages for remote mode
            # NOTE: Remote query API currently supports single path only
            # Use first path from tuple, ignore additional paths for remote mode
            results_raw = asyncio.run(
                execute_remote_query(
                    query_text=query,
                    limit=limit,
                    project_root=project_root,
                    language=languages[0] if languages else None,
                    path=path_filter[0] if path_filter else None,
                    min_score=min_score,
                    include_source=True,
                    accuracy=accuracy,
                )
            )

            # Cast to help MyPy understand the actual return type
            remote_results: List[QueryResultItem] = cast(
                List[QueryResultItem], results_raw
            )

            if not remote_results:
                console.print("No results found.", style="yellow")
                sys.exit(0)

            # Convert API client results to local format for display
            converted_results: List[Dict[str, Any]] = []
            for result_item in remote_results:
                converted_result = {
                    "score": getattr(
                        result_item,
                        "score",
                        getattr(result_item, "similarity_score", 0.0),
                    ),
                    "payload": {
                        "path": result_item.file_path,
                        "language": getattr(result_item, "language", None),
                        "content": getattr(
                            result_item,
                            "content",
                            getattr(result_item, "code_snippet", ""),
                        ),
                        "line_start": getattr(
                            result_item, "line_start", result_item.line_number
                        ),
                        "line_end": getattr(
                            result_item, "line_end", result_item.line_number + 1
                        ),
                    },
                }

                # Add staleness info if available (EnhancedQueryResultItem)
                if hasattr(result_item, "staleness_indicator"):
                    converted_result["staleness"] = {
                        "is_stale": result_item.is_stale,
                        "staleness_indicator": result_item.staleness_indicator,
                        "staleness_delta_seconds": result_item.staleness_delta_seconds,
                    }

                converted_results.append(converted_result)

            # Use existing display logic for local queries
            if not quiet:
                console.print(f"\n✅ Found {len(converted_results)} results:")
                console.print("=" * 80)

            # Display each result using existing logic
            for i, result in enumerate(converted_results, 1):
                # Type hint: result is Dict[str, Any] here (converted from QueryResultItem)
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

        # Initialize services - lazy imports for query path
        from .services.generic_query_service import GenericQueryService
        from .services.language_validator import LanguageValidator
        from .services.language_mapper import LanguageMapper

        embedding_provider = EmbeddingProviderFactory.create(config, console)
        backend = BackendFactory.create(
            config=config, project_root=Path(config.codebase_dir)
        )
        vector_store_client = backend.get_vector_store_client()

        # Health checks
        if not embedding_provider.health_check():
            console.print(
                f"❌ {embedding_provider.get_provider_name().title()} service not available",
                style="red",
            )
            sys.exit(1)

        if not vector_store_client.health_check():
            console.print("❌ Vector store service not available", style="red")
            sys.exit(1)

        # Ensure provider-aware collection is set for search
        collection_name = vector_store_client.resolve_collection_name(
            config, embedding_provider
        )
        vector_store_client._current_collection_name = collection_name

        # Ensure payload indexes exist (read-only check for query operations)
        vector_store_client.ensure_payload_indexes(collection_name, context="query")

        # Initialize timing dictionary for telemetry
        timing_info = {}

        # NOTE: Embedding generation now happens in parallel with index loading
        # inside vector_store_client.search() - do NOT pre-compute embedding here

        # Build filter conditions for non-git path only
        filter_conditions: Dict[str, Any] = {}
        if languages:
            # Validate language parameters
            language_validator = LanguageValidator()
            language_mapper = LanguageMapper()
            must_conditions = []

            for lang in languages:
                # Validate each language
                validation_result = language_validator.validate_language(lang)

                if not validation_result.is_valid:
                    click.echo(f"Error: {validation_result.error_message}", err=True)
                    if validation_result.suggestions:
                        click.echo(
                            f"Suggestions: {', '.join(validation_result.suggestions)}",
                            err=True,
                        )
                    raise click.ClickException(f"Invalid language: {lang}")

                # For non-git path, handle language mapping
                language_filter = language_mapper.build_language_filter(lang)
                must_conditions.append(language_filter)

            if must_conditions:
                filter_conditions["must"] = must_conditions
        if path_filter:
            for pf in path_filter:
                filter_conditions.setdefault("must", []).append(
                    {"key": "path", "match": {"text": pf}}
                )

        # Build exclusion filters (must_not conditions)
        if exclude_languages:
            language_validator = LanguageValidator()
            language_mapper = LanguageMapper()
            must_not_conditions = []

            for exclude_lang in exclude_languages:
                # Validate each exclusion language
                validation_result = language_validator.validate_language(exclude_lang)

                if not validation_result.is_valid:
                    click.echo(f"Error: {validation_result.error_message}", err=True)
                    if validation_result.suggestions:
                        click.echo(
                            f"Suggestions: {', '.join(validation_result.suggestions)}",
                            err=True,
                        )
                    raise click.ClickException(
                        f"Invalid exclusion language: {exclude_lang}"
                    )

                # Get all extensions for this language
                extensions = language_mapper.get_extensions(exclude_lang)

                # Add must_not condition for each extension
                for ext in extensions:
                    must_not_conditions.append(
                        {"key": "language", "match": {"value": ext}}
                    )

            if must_not_conditions:
                filter_conditions["must_not"] = must_not_conditions

        # Build path exclusion filters (must_not conditions for paths)
        if exclude_paths:
            from .services.path_filter_builder import PathFilterBuilder

            path_filter_builder = PathFilterBuilder()

            # Build path exclusion filters
            path_exclusion_filters = path_filter_builder.build_exclusion_filter(
                list(exclude_paths)
            )

            # Add to existing must_not conditions
            if path_exclusion_filters.get("must_not"):
                if "must_not" in filter_conditions:
                    filter_conditions["must_not"].extend(
                        path_exclusion_filters["must_not"]
                    )
                else:
                    filter_conditions["must_not"] = path_exclusion_filters["must_not"]

        # Detect and warn about filter conflicts (Story 3.1)
        from .services.filter_conflict_detector import FilterConflictDetector

        conflict_detector = FilterConflictDetector()

        # Prepare filter arguments for conflict detection
        include_languages = list(languages) if languages else []
        include_paths = list(path_filter) if path_filter else []

        conflicts = conflict_detector.detect_conflicts(
            include_languages=include_languages,
            exclude_languages=list(exclude_languages) if exclude_languages else [],
            include_paths=include_paths,
            exclude_paths=list(exclude_paths) if exclude_paths else [],
        )

        # Display warnings/errors for conflicts
        if conflicts:
            error_conflicts = [c for c in conflicts if c.severity == "error"]
            warning_conflicts = [c for c in conflicts if c.severity == "warning"]

            if error_conflicts:
                console.print("\n[bold red]🚫 Filter Conflicts (Errors):[/bold red]")
                for conflict in error_conflicts:
                    console.print(f"  [red]• {conflict.message}[/red]")
                console.print()

            if warning_conflicts:
                console.print("\n[bold yellow]⚠️  Filter Warnings:[/bold yellow]")
                for conflict in warning_conflicts:
                    console.print(f"  [yellow]• {conflict.message}[/yellow]")
                console.print()

        # Log filter structure for debugging (Story 3.1 AC #12)
        import logging

        logger = logging.getLogger(__name__)
        if filter_conditions:
            import json

            logger.debug(f"Query filters: {json.dumps(filter_conditions, indent=2)}")

        # Check if project uses git-aware indexing
        from .services.git_topology_service import GitTopologyService

        # BranchAwareIndexer removed - using HighThroughputProcessor git-aware methods

        git_topology_service = GitTopologyService(config.codebase_dir)
        is_git_aware = git_topology_service.is_git_available()

        # Initialize query service for git-aware filtering
        query_service = GenericQueryService(config.codebase_dir, config)

        # Determine if we should use branch-aware querying
        if is_git_aware:
            # Use git-aware filtering for git projects
            current_branch = git_topology_service.get_current_branch() or "master"
            use_branch_aware_query = True
        else:
            # Use generic query service for non-git projects
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
            if languages:
                console.print(f"🏷️  Language filter: {', '.join(languages)}")
            if path_filter:
                console.print(f"📁 Path filter: {', '.join(path_filter)}")
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
                    from .services.progressive_metadata import (
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

            # Build filter conditions (NO git_branch filter - let post-filtering handle it)
            filter_conditions_list = []

            # Only filter by git_available to exclude non-git content
            filter_conditions_list.append(
                {"key": "git_available", "match": {"value": True}}
            )

            # Add user-specified filters
            if languages:
                language_mapper = LanguageMapper()
                # Handle multiple languages by building OR conditions
                for language in languages:
                    language_filter = language_mapper.build_language_filter(language)
                    filter_conditions_list.append(language_filter)
            if path_filter:
                for pf in path_filter:
                    filter_conditions_list.append(
                        {"key": "path", "match": {"text": pf}}
                    )

            # Build filter conditions preserving both must and must_not conditions
            query_filter_conditions = (
                {"must": filter_conditions_list} if filter_conditions_list else {}
            )
            # CRITICAL: Preserve must_not conditions (exclusion filters) from earlier filter_conditions
            # This ensures --exclude-language and --exclude-path work in git-aware repositories
            if filter_conditions.get("must_not"):
                query_filter_conditions["must_not"] = filter_conditions["must_not"]

            # Query vector store (get more results to allow for git filtering)
            # FilesystemVectorStore: parallel execution (query + embedding_provider)
            # QdrantClient: requires pre-computed query_vector
            from .storage.filesystem_vector_store import (
                FilesystemVectorStore,
            )

            if isinstance(vector_store_client, FilesystemVectorStore):
                # Parallel execution: embedding generation + index loading happen concurrently
                raw_results, search_timing = vector_store_client.search(
                    query=query,  # Pass query text for parallel embedding
                    embedding_provider=embedding_provider,  # Provider for parallel execution
                    filter_conditions=query_filter_conditions,
                    limit=limit * 2,  # Get more to account for post-filtering
                    collection_name=collection_name,
                    return_timing=True,
                )
            else:
                # QdrantClient: pre-compute embedding (no parallel support yet)
                query_embedding = embedding_provider.get_embedding(query)
                raw_results_list = vector_store_client.search(
                    query_vector=query_embedding,
                    filter_conditions=query_filter_conditions,
                    limit=limit * 2,
                    collection_name=collection_name,
                )
                raw_results = raw_results_list  # Type compatibility
                search_timing = {}  # Qdrant doesn't return timing yet
            # Merge detailed search timing into main timing info
            timing_info.update(search_timing)

            # Calculate vector_search_ms as sum of breakdown components for accurate reporting
            breakdown_keys = [
                "matrix_load_ms",
                "index_load_ms",
                "hnsw_search_ms",
                "id_index_load_ms",
                "staleness_detection_ms",
            ]
            timing_info["vector_search_ms"] = sum(
                search_timing.get(k, 0) for k in breakdown_keys
            )

            # Apply git-aware post-filtering (checks file existence in current branch)
            git_filter_start = time.time()
            # Type hint: raw_results is always List[Dict[str, Any]] here
            git_results = query_service.filter_results_by_current_branch(raw_results)  # type: ignore[arg-type]
            timing_info["git_filter_ms"] = (time.time() - git_filter_start) * 1000

            # Apply minimum score filtering (language and path already handled by Qdrant filters)
            if min_score:
                filtered_results: List[Dict[str, Any]] = []
                for result in git_results:
                    # Filter by minimum score
                    if result.get("score", 0) >= min_score:
                        filtered_results.append(result)
                git_results = filtered_results
        else:
            # Use model-specific search for non-git projects
            # FilesystemVectorStore: Use regular search (no model filter needed - single provider)
            # QdrantClient: Use search_with_model_filter for multi-provider support
            from .storage.filesystem_vector_store import (
                FilesystemVectorStore,
            )

            if isinstance(vector_store_client, FilesystemVectorStore):
                # Filesystem backend: parallel execution
                raw_results, search_timing = vector_store_client.search(
                    query=query,
                    embedding_provider=embedding_provider,
                    filter_conditions=filter_conditions if filter_conditions else None,
                    limit=limit * 2,
                    score_threshold=min_score,
                    collection_name=collection_name,
                    return_timing=True,
                )
                timing_info.update(search_timing)
            else:
                # Qdrant backend: pre-compute embedding
                search_start = time.time()
                query_embedding = embedding_provider.get_embedding(query)
                raw_results_list = vector_store_client.search_with_model_filter(
                    query_vector=query_embedding,
                    embedding_model=current_model,
                    limit=limit * 2,
                    score_threshold=min_score,
                    additional_filters=filter_conditions,
                    accuracy=accuracy,
                )
                raw_results = raw_results_list  # Type compatibility
                timing_info["vector_search_ms"] = (time.time() - search_start) * 1000

            # Apply git-aware filtering
            if not quiet:
                console.print("🔍 Applying git-aware filtering...")
            git_filter_start = time.time()
            # Type hint: raw_results is always List[Dict[str, Any]] here
            git_results = query_service.filter_results_by_current_branch(raw_results)  # type: ignore[arg-type]
            timing_info["git_filter_ms"] = (time.time() - git_filter_start) * 1000

        # Limit to requested number after filtering
        results = git_results[:limit]

        # Apply staleness detection to local query results
        if results:
            try:
                staleness_start = time.time()
                # Convert local results to QueryResultItem format for staleness detection
                from .api_clients.remote_query_client import QueryResultItem
                from .remote.staleness_detector import StalenessDetector

                query_result_items = []
                for result in results:
                    payload = result["payload"]

                    # Extract file metadata for staleness comparison
                    file_last_modified = payload.get("file_last_modified")
                    indexed_at = payload.get("indexed_at")

                    # Convert indexed_at ISO timestamp to Unix timestamp float
                    indexed_timestamp = None
                    if indexed_at:
                        try:
                            from datetime import datetime

                            dt = datetime.fromisoformat(indexed_at.rstrip("Z"))
                            indexed_timestamp = dt.timestamp()
                        except (ValueError, AttributeError):
                            indexed_timestamp = None

                    query_item = QueryResultItem(
                        similarity_score=result["score"],
                        file_path=payload.get("path", "unknown"),
                        line_number=payload.get("line_start", 1),
                        code_snippet=payload.get("content", ""),
                        repository_alias=project_root.name,
                        file_last_modified=file_last_modified,
                        indexed_timestamp=indexed_timestamp,
                    )
                    query_result_items.append(query_item)

                # Apply staleness detection in local mode
                staleness_detector = StalenessDetector()
                enhanced_results = staleness_detector.apply_staleness_detection(
                    query_result_items, project_root, mode="local"
                )
                timing_info["staleness_detection_ms"] = (
                    time.time() - staleness_start
                ) * 1000

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

        # Display results using shared display function (DRY principle)
        _display_semantic_results(
            results=results,
            console=console,
            quiet=quiet,
            timing_info=timing_info,
            current_display_branch=current_display_branch,
        )

    except Exception as e:
        console.print(f"❌ Search failed: {e}", style="red")
        sys.exit(1)


@cli.command(name="teach-ai")
@click.option(
    "--claude",
    "platform_claude",
    is_flag=True,
    help="Generate instructions for Claude Code platform",
)
@click.option(
    "--codex",
    "platform_codex",
    is_flag=True,
    help="Generate instructions for OpenAI Codex platform",
)
@click.option(
    "--gemini",
    "platform_gemini",
    is_flag=True,
    help="Generate instructions for Google Gemini platform",
)
@click.option(
    "--opencode",
    "platform_opencode",
    is_flag=True,
    help="Generate instructions for OpenCode platform",
)
@click.option(
    "--q", "platform_q", is_flag=True, help="Generate instructions for Q platform"
)
@click.option(
    "--junie",
    "platform_junie",
    is_flag=True,
    help="Generate instructions for Junie platform",
)
@click.option(
    "--project",
    "scope_project",
    is_flag=True,
    help="Install instructions in project root (./CLAUDE.md)",
)
@click.option(
    "--global",
    "scope_global",
    is_flag=True,
    help="Install instructions globally (~/.claude/CLAUDE.md)",
)
@click.option(
    "--show-only",
    is_flag=True,
    help="Preview instruction content without writing files",
)
def teach_ai(
    platform_claude: bool,
    platform_codex: bool,
    platform_gemini: bool,
    platform_opencode: bool,
    platform_q: bool,
    platform_junie: bool,
    scope_project: bool,
    scope_global: bool,
    show_only: bool,
):
    """Generate AI platform instructions for semantic code search.

    Creates instruction files (like CLAUDE.md) that teach AI assistants how to use
    cidx for semantic code search. Instructions are loaded from template files in
    prompts/ai_instructions/, allowing non-developers to update content without
    code changes.

    \b
    USAGE EXAMPLES:
      # Install Claude instructions in project
      cidx teach-ai --claude --project

      # Install Claude instructions globally
      cidx teach-ai --claude --global

      # Preview instruction content
      cidx teach-ai --claude --show-only

    \b
    PLATFORMS:
      --claude      Claude Code platform
      --codex       OpenAI Codex platform
      --gemini      Google Gemini platform
      --opencode    OpenCode platform
      --q           Q platform
      --junie       Junie platform

    \b
    SCOPE:
      --project     Install in project root (./CLAUDE.md)
      --global      Install globally (~/.claude/CLAUDE.md)
      --show-only   Preview without writing files
    """
    console = Console()

    # Validate platform flag (exactly one required)
    platforms = [
        platform_claude,
        platform_codex,
        platform_gemini,
        platform_opencode,
        platform_q,
        platform_junie,
    ]
    platform_count = sum(platforms)

    if platform_count == 0:
        console.print(
            "❌ Platform required: --claude, --codex, --gemini, --opencode, --q, or --junie",
            style="red",
        )
        sys.exit(1)

    if platform_count > 1:
        console.print("❌ Only one platform flag allowed at a time", style="red")
        sys.exit(1)

    # Validate scope flag (required unless --show-only)
    if not show_only:
        scopes = [scope_project, scope_global]
        scope_count = sum(scopes)

        if scope_count == 0:
            console.print("❌ Scope required: --project or --global", style="red")
            sys.exit(1)

        if scope_count > 1:
            console.print("❌ Only one scope flag allowed at a time", style="red")
            sys.exit(1)

    # Determine platform name for template lookup
    if platform_claude:
        platform_name = "claude"
    elif platform_codex:
        platform_name = "codex"
    elif platform_gemini:
        platform_name = "gemini"
    elif platform_opencode:
        platform_name = "opencode"
    elif platform_q:
        platform_name = "q"
    elif platform_junie:
        platform_name = "junie"
    else:
        console.print("❌ Internal error: No platform selected", style="red")
        sys.exit(1)

    # Load template content
    try:
        # Find template file relative to this CLI module
        cli_dir = Path(__file__).parent
        project_root = cli_dir.parent.parent
        template_path = (
            project_root / "prompts" / "ai_instructions" / "cidx_instructions.md"
        )

        if not template_path.exists():
            console.print(
                f"❌ Template not found: {template_path}",
                style="red",
            )
            console.print(
                "   Expected template at: prompts/ai_instructions/cidx_instructions.md"
            )
            sys.exit(1)

        template_content = template_path.read_text()

    except Exception as e:
        console.print(f"❌ Failed to load template: {e}", style="red")
        sys.exit(1)

    # Handle --show-only mode
    if show_only:
        console.print(f"📄 {platform_name.title()} Platform Instructions:\n")
        console.print(template_content)
        return

    # Platform-specific validation: Gemini and Junie only support project-level
    if platform_name == "gemini" and scope_global:
        console.print(
            "❌ Gemini platform only supports project-level instructions (--project)",
            style="red",
        )
        console.print(
            "   Gemini does not have a global configuration directory per research."
        )
        sys.exit(1)

    if platform_name == "junie" and scope_global:
        console.print(
            "❌ Junie platform only supports project-level instructions (--project)",
            style="red",
        )
        console.print(
            "   Junie does not have a global configuration directory per research."
        )
        sys.exit(1)

    # Determine target file path based on platform conventions
    if scope_project:
        if platform_name == "claude":
            # Claude: CLAUDE.md in project root
            target_path = Path.cwd() / "CLAUDE.md"
            scope_desc = "project root"
        elif platform_name == "codex":
            # Codex: CODEX.md in project root (project-specific instructions)
            target_path = Path.cwd() / "CODEX.md"
            scope_desc = "project root"
        elif platform_name == "gemini":
            # Gemini: styleguide.md in .gemini subdirectory
            gemini_dir = Path.cwd() / ".gemini"
            gemini_dir.mkdir(parents=True, exist_ok=True)
            target_path = gemini_dir / "styleguide.md"
            scope_desc = ".gemini/"
        elif platform_name == "opencode":
            # OpenCode: AGENTS.md in project root (AGENTS.md open standard)
            target_path = Path.cwd() / "AGENTS.md"
            scope_desc = "project root"
        elif platform_name == "q":
            # Amazon Q: cidx.md in .amazonq/rules/ subdirectory
            q_dir = Path.cwd() / ".amazonq" / "rules"
            q_dir.mkdir(parents=True, exist_ok=True)
            target_path = q_dir / "cidx.md"
            scope_desc = ".amazonq/rules/"
        elif platform_name == "junie":
            # JetBrains Junie: guidelines.md in .junie subdirectory
            junie_dir = Path.cwd() / ".junie"
            junie_dir.mkdir(parents=True, exist_ok=True)
            target_path = junie_dir / "guidelines.md"
            scope_desc = ".junie/"
        else:
            # Default for other platforms
            target_path = Path.cwd() / f"{platform_name.upper()}.md"
            scope_desc = "project root"
    else:  # scope_global
        home_dir = Path.home()
        if platform_name == "claude":
            # Claude: ~/.claude/CLAUDE.md
            platform_dir = home_dir / ".claude"
            platform_dir.mkdir(parents=True, exist_ok=True)
            target_path = platform_dir / "CLAUDE.md"
            scope_desc = "~/.claude/"
        elif platform_name == "codex":
            # Codex: ~/.codex/instructions.md (global behavioral instructions)
            platform_dir = home_dir / ".codex"
            platform_dir.mkdir(parents=True, exist_ok=True)
            target_path = platform_dir / "instructions.md"
            scope_desc = "~/.codex/"
        elif platform_name == "opencode":
            # OpenCode: ~/.config/opencode/AGENTS.md (AGENTS.md open standard)
            platform_dir = home_dir / ".config" / "opencode"
            platform_dir.mkdir(parents=True, exist_ok=True)
            target_path = platform_dir / "AGENTS.md"
            scope_desc = "~/.config/opencode/"
        elif platform_name == "q":
            # Amazon Q: ~/.aws/amazonq/Q.md
            platform_dir = home_dir / ".aws" / "amazonq"
            platform_dir.mkdir(parents=True, exist_ok=True)
            target_path = platform_dir / "Q.md"
            scope_desc = "~/.aws/amazonq/"
        else:
            # Default for other platforms
            platform_dir = home_dir / f".{platform_name}"
            platform_dir.mkdir(parents=True, exist_ok=True)
            target_path = platform_dir / f"{platform_name.upper()}.md"
            scope_desc = f"~/.{platform_name}/"

    # Smart update: preserve existing content and update only CIDX section
    if target_path.exists():
        # File exists - use Claude CLI to intelligently merge content
        console.print("📝 Updating existing file with Claude CLI...", style="dim")

        try:
            existing_content = target_path.read_text()

            # Create prompt for Claude to intelligently merge
            merge_prompt = f"""You are updating an AI instruction file. Your task is to intelligently merge new CIDX semantic search instructions into an existing file while preserving ALL existing content.

EXISTING FILE CONTENT:
{existing_content}

NEW CIDX SECTION TO ADD/UPDATE:
{template_content}

INSTRUCTIONS:
1. If the file already has a CIDX/semantic search section (look for headers like "SEMANTIC SEARCH", "CIDX SEMANTIC SEARCH", etc.), UPDATE that section with the new content
2. If the file does NOT have a CIDX section, ADD the new section at the end
3. Preserve ALL other existing content exactly as-is
4. Maintain the file's existing formatting style
5. Output ONLY the raw merged file content with NO markdown code fences, NO explanations, NO commentary
6. Start output immediately with the first line of the merged file

OUTPUT THE COMPLETE MERGED FILE (raw content only, no markdown wrappers):"""

            # Call Claude CLI with explicit text output format
            result = subprocess.run(
                [
                    "claude",
                    "-p",
                    "--output-format",
                    "text",
                    "--dangerously-skip-permissions",
                    merge_prompt,
                ],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minutes for large files
            )

            if result.returncode != 0:
                console.print(
                    f"❌ Claude CLI failed: {result.stderr or 'Unknown error'}",
                    style="red",
                )
                sys.exit(1)

            merged_content = result.stdout.strip()

            # Strip markdown code fences if Claude added them despite instructions
            if merged_content.startswith("```"):
                lines = merged_content.split("\n")
                # Remove first line (```markdown or similar) and last line (```)
                if lines[-1].strip() == "```":
                    merged_content = "\n".join(lines[1:-1])

            # Write merged content
            target_path.write_text(merged_content)

            console.print(
                f"✅ {platform_name.title()} instructions updated in {scope_desc}",
                style="green",
            )
            console.print(f"   File: {target_path}", style="dim")
            console.print(
                "   ℹ️  Existing content preserved, CIDX section updated",
                style="blue dim",
            )

        except subprocess.TimeoutExpired:
            console.print("❌ Claude CLI timed out", style="red")
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Failed to update instruction file: {e}", style="red")
            sys.exit(1)
    else:
        # New file - create with template content
        try:
            target_path.write_text(template_content)
            console.print(
                f"✅ {platform_name.title()} instructions installed to {scope_desc}",
                style="green",
            )
            console.print(f"   File: {target_path}", style="dim")
        except Exception as e:
            console.print(f"❌ Failed to write instruction file: {e}", style="red")
            sys.exit(1)


@cli.command()
@click.option(
    "--force-docker", is_flag=True, help="Force use Docker even if Podman is available"
)
@click.pass_context
@require_mode("local", "remote", "proxy", "uninitialized")
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

    # Status command always uses full CLI for Rich table display
    # (Daemon delegation would lose the beautiful formatted table)
    # CRITICAL: Skip daemon delegation if standalone flag is set (prevents recursive loop)

    # Handle proxy mode (Story 2.2)
    if mode == "proxy":
        from .proxy import execute_proxy_command

        # Build args list for status command
        args = []
        if force_docker:
            args.append("--force-docker")

        exit_code = execute_proxy_command(project_root, "status", args)
        sys.exit(exit_code)

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

        # Add daemon mode indicator (requested by user)
        try:
            daemon_config = config.daemon if hasattr(config, "daemon") else None
            socket_path = config_manager.config_path.parent / "daemon.sock"
            daemon_running = socket_path.exists()

            if daemon_config and daemon_config.enabled:
                if daemon_running:
                    table.add_row(
                        "Daemon Mode",
                        "✅ Active",
                        f"Socket: {socket_path.name} | TTL: {daemon_config.ttl_minutes}min | Queries use daemon",
                    )
                else:
                    table.add_row(
                        "Daemon Mode",
                        "⚠️ Configured",
                        "Enabled but stopped (auto-starts on first query)",
                    )
            else:
                table.add_row(
                    "Daemon Mode",
                    "❌ Disabled",
                    "Standalone mode (enable: cidx config --daemon)",
                )
        except Exception:
            # If daemon config check fails, just skip the row
            pass

        # Check backend provider first to determine if containers are needed
        backend_provider = getattr(config, "vector_store", None)
        backend_provider = (
            backend_provider.provider if backend_provider else "qdrant"
        )  # Default to qdrant for backward compatibility

        # Only check Docker services if using Qdrant backend (containers required)
        service_status: Dict[str, Any] = {"status": "not_configured", "services": {}}
        if backend_provider != "filesystem":
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

        # Check embedding provider - ALWAYS attempt health check via HTTP
        try:
            embedding_provider = EmbeddingProviderFactory.create(config, console)
            provider_name = embedding_provider.get_provider_name().title()

            # Always try health check via HTTP (works across containers)
            provider_ok = embedding_provider.health_check()
            provider_status = "✅ Ready" if provider_ok else "❌ Not Available"

            if provider_ok:
                provider_details = f"Model: {embedding_provider.get_current_model()}"
            else:
                # Check if container exists for debugging info
                if config.embedding_provider == "ollama":
                    ollama_container_found = any(
                        "ollama" in name and info["state"] == "running"
                        for name, info in service_status.get("services", {}).items()
                    )
                    provider_details = (
                        f"Service unreachable at {config.ollama.host}"
                        if ollama_container_found
                        else "Service down (container stopped)"
                    )
                else:
                    provider_details = "Service unreachable"

            table.add_row(
                f"{provider_name} Provider", provider_status, provider_details
            )
        except Exception as e:
            table.add_row("Embedding Provider", "❌ Error", str(e))

        # Check Vector Storage Backend (Qdrant or Filesystem)
        # backend_provider already determined above
        qdrant_ok = False  # Initialize to False
        qdrant_client = None  # Initialize to None

        # Initialize variables for recovery guidance (both backends need these defined)
        missing_components: List[str] = []
        fs_index_files_display: Optional[str] = None

        if backend_provider == "filesystem":
            # Filesystem backend - no containers required
            from .storage.filesystem_vector_store import FilesystemVectorStore

            try:
                # Get filesystem storage path
                index_path = Path(config.codebase_dir) / ".code-indexer" / "index"
                fs_store = FilesystemVectorStore(
                    base_path=index_path, project_root=Path(config.codebase_dir)
                )

                # Health check - verify filesystem accessibility
                fs_ok = fs_store.health_check()
                fs_status = "✅ Ready" if fs_ok else "❌ Not Accessible"

                if fs_ok:
                    # Get collection info
                    try:
                        embedding_provider = EmbeddingProviderFactory.create(
                            config, console
                        )
                        collection_name = fs_store.resolve_collection_name(
                            config, embedding_provider
                        )

                        if fs_store.collection_exists(collection_name):
                            vector_count = fs_store.count_points(collection_name)
                            # Use fast file count (accurate from metadata, instant lookup)
                            file_count = fs_store.get_indexed_file_count_fast(
                                collection_name
                            )

                            # Validate dimensions
                            expected_dims = embedding_provider.get_model_info()[
                                "dimensions"
                            ]
                            dims_ok = fs_store.validate_embedding_dimensions(
                                collection_name, expected_dims
                            )
                            dims_status = "✅" if dims_ok else "⚠️"

                            fs_details = f"Collection: {collection_name}\nVectors: {vector_count:,} | Files: {file_count} | Dims: {dims_status}{expected_dims}"

                            # Check critical index files for filesystem backend
                            collection_path = index_path / collection_name
                            proj_matrix = collection_path / "projection_matrix.npy"
                            hnsw_index = collection_path / "hnsw_index.bin"

                            # Build index files status
                            index_files_status = []

                            # Projection matrix (CRITICAL - queries fail without it)
                            if proj_matrix.exists():
                                size_kb = proj_matrix.stat().st_size / 1024
                                if size_kb < 1024:
                                    index_files_status.append(
                                        f"Projection Matrix: ✅ {size_kb:.0f} KB"
                                    )
                                else:
                                    size_mb = size_kb / 1024
                                    index_files_status.append(
                                        f"Projection Matrix: ✅ {size_mb:.1f} MB"
                                    )
                            else:
                                index_files_status.append(
                                    "Projection Matrix: ❌ MISSING (index unrecoverable!)"
                                )

                            # HNSW index (IMPORTANT - queries slow without it)
                            if hnsw_index.exists():
                                size_mb = hnsw_index.stat().st_size / (1024 * 1024)
                                index_files_status.append(
                                    f"HNSW Index: ✅ {size_mb:.0f} MB"
                                )
                            else:
                                index_files_status.append(
                                    "HNSW Index: ⚠️ Missing (queries will be slow)"
                                )

                            # ID index check (binary file that persists to disk)
                            id_index_file = collection_path / "id_index.bin"
                            if id_index_file.exists():
                                size_kb = id_index_file.stat().st_size / 1024
                                index_files_status.append(
                                    f"ID Index: ✅ {size_kb:.0f} KB"
                                )
                            else:
                                index_files_status.append(
                                    "ID Index: ⚠️ Missing (rebuilds automatically)"
                                )

                            # FTS (Full-Text Search) index check
                            fts_index_path = (
                                config_manager.config_path.parent / "tantivy_index"
                            )
                            if fts_index_path.exists() and fts_index_path.is_dir():
                                # Check for tantivy meta files to verify it's a valid index
                                meta_file = fts_index_path / "meta.json"
                                managed_file = fts_index_path / ".managed.json"

                                if meta_file.exists() or managed_file.exists():
                                    # Valid FTS index exists - get size
                                    total_size = sum(
                                        f.stat().st_size
                                        for f in fts_index_path.rglob("*")
                                        if f.is_file()
                                    )
                                    size_mb = total_size / (1024 * 1024)
                                    # Count index segments (*.idx files indicate indexed data)
                                    segment_count = len(
                                        list(fts_index_path.glob("*.idx"))
                                    )
                                    index_files_status.append(
                                        f"FTS Index: ✅ {size_mb:.1f} MB ({segment_count} segments)"
                                    )
                                else:
                                    index_files_status.append(
                                        "FTS Index: ⚠️ Invalid (missing meta files)"
                                    )
                            else:
                                index_files_status.append(
                                    "FTS Index: ❌ Not created (use --fts flag)"
                                )

                            # Track missing components for recovery guidance
                            has_projection_matrix = proj_matrix.exists()
                            has_hnsw_index = hnsw_index.exists()
                            has_id_index = id_index_file.exists()

                            if not has_projection_matrix:
                                missing_components.append("projection_matrix")
                            if not has_hnsw_index:
                                missing_components.append("hnsw")
                            if not has_id_index:
                                missing_components.append("id_index")

                            # Store for later display
                            fs_index_files_display = "\n".join(index_files_status)
                        else:
                            fs_details = f"Collection: {collection_name}\nStatus: Not created - run 'cidx index'"
                            fs_index_files_display = None
                    except Exception as e:
                        fs_details = f"Error checking collection: {str(e)[:50]}"
                        fs_index_files_display = None
                else:
                    fs_details = f"Storage path: {index_path}\nStatus: Not accessible"
                    fs_index_files_display = None

                table.add_row("Vector Storage", fs_status, fs_details)
                table.add_row("Storage Path", "📁", str(index_path))

                # Add index files status if available
                if fs_index_files_display:
                    table.add_row("Index Files", "", fs_index_files_display)

                # Check for temporal index and display if exists
                try:
                    temporal_collection_name = "code-indexer-temporal"
                    if fs_store.collection_exists(temporal_collection_name):
                        # Read temporal metadata
                        temporal_dir = index_path / temporal_collection_name
                        temporal_meta_path = temporal_dir / "temporal_meta.json"

                        if temporal_meta_path.exists():
                            import json

                            with open(temporal_meta_path) as f:
                                temporal_meta = json.load(f)

                            # Extract metadata
                            total_commits = temporal_meta.get("total_commits", 0)
                            files_processed = temporal_meta.get("files_processed", 0)
                            indexed_branches = temporal_meta.get("indexed_branches", [])
                            indexed_at = temporal_meta.get("indexed_at", "")

                            # Get vector count from collection
                            vector_count = fs_store.count_points(
                                temporal_collection_name
                            )

                            # Calculate storage size - include ALL files in temporal directory
                            # Use du command for performance (30x faster than iterating files)
                            import subprocess

                            total_size_bytes = 0
                            if temporal_dir.exists():
                                try:
                                    result = subprocess.run(
                                        ["du", "-sb", str(temporal_dir)],
                                        capture_output=True,
                                        text=True,
                                        timeout=5,
                                    )
                                    total_size_bytes = int(result.stdout.split()[0])
                                except FileNotFoundError:
                                    # Fallback to iteration if du command unavailable
                                    for file_path in temporal_dir.rglob("*"):
                                        if file_path.is_file():
                                            total_size_bytes += file_path.stat().st_size
                            total_size_mb = total_size_bytes / (1024 * 1024)

                            # Format date
                            if indexed_at:
                                from datetime import datetime

                                dt = datetime.fromisoformat(
                                    indexed_at.replace("Z", "+00:00")
                                )
                                formatted_date = dt.strftime("%Y-%m-%d %H:%M")
                            else:
                                formatted_date = "Unknown"

                            # Format branch list
                            branch_list = (
                                ", ".join(indexed_branches)
                                if indexed_branches
                                else "None"
                            )

                            # Build details string
                            temporal_status = "✅ Available"
                            temporal_details = (
                                f"{total_commits} commits | {files_processed:,} files changed | {vector_count:,} vectors\n"
                                f"Branches: {branch_list}\n"
                                f"Storage: {total_size_mb:.1f} MB | Last indexed: {formatted_date}"
                            )
                            table.add_row(
                                "Temporal Index", temporal_status, temporal_details
                            )
                        else:
                            # Temporal collection exists but no metadata file
                            temporal_status = "⚠️ Incomplete"
                            temporal_details = "Collection exists but missing metadata"
                            table.add_row(
                                "Temporal Index", temporal_status, temporal_details
                            )
                except Exception as e:
                    # Don't fail status command if temporal check fails, but log the error
                    logger.warning(f"Failed to check temporal index status: {e}")
                    table.add_row(
                        "Temporal Index",
                        "⚠️ Error",
                        f"Failed to read temporal index information: {str(e)[:100]}",
                    )

            except Exception as e:
                table.add_row("Vector Storage", "❌ Error", str(e))

        else:
            # Qdrant backend - original container-based logic
            try:
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
                                error_msg = optimizer_status.get(
                                    "error", "Unknown error"
                                )

                                # Translate common errors to user-friendly messages
                                if "No such file or directory" in error_msg:
                                    friendly_error = "Storage corruption detected - collection data is damaged"
                                elif "Permission denied" in error_msg:
                                    friendly_error = "Storage permission error - check file permissions"
                                elif "disk space" in error_msg.lower():
                                    friendly_error = "Insufficient disk space for collection operations"
                                else:
                                    friendly_error = f"Collection error: {error_msg}"

                                qdrant_status = "❌ Collection Error"
                                qdrant_details = f"🚨 {friendly_error}"
                            elif collection_status == "yellow":
                                qdrant_status = "⚠️ Collection Warning"
                                qdrant_details = (
                                    "Collection has warnings but is functional"
                                )
                            else:
                                # Collection is healthy, proceed with normal status
                                project_count = qdrant_client.count_points(
                                    collection_name
                                )

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
                                        config_manager.config_path.parent
                                        / "metadata.json"
                                    )
                                    if metadata_path.exists():
                                        import json

                                        with open(metadata_path) as f:
                                            metadata = json.load(f)
                                        files_processed = metadata.get(
                                            "files_processed", 0
                                        )
                                        chunks_indexed = metadata.get(
                                            "chunks_indexed", 0
                                        )
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
                    # Check if container exists for debugging info
                    qdrant_container_found = any(
                        "qdrant" in name and info["state"] == "running"
                        for name, info in service_status.get("services", {}).items()
                    )
                    qdrant_details = (
                        f"Service unreachable at {config.qdrant.host}"
                        if qdrant_container_found
                        else "Service down (container stopped)"
                    )

                table.add_row("Qdrant", qdrant_status, qdrant_details)
            except Exception as e:
                table.add_row("Qdrant", "❌ Error", str(e))

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

        # Add Qdrant storage and collection information - only for Qdrant backend
        if backend_provider != "filesystem":
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
                        collection_exists = qdrant_client.collection_exists(
                            collection_name
                        )
                        if collection_exists:
                            collection_count = qdrant_client.count_points(
                                collection_name
                            )
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
                            "Project Collection",
                            "⚠️  Error",
                            f"Check failed: {str(e)[:50]}",
                        )
                else:
                    table.add_row(
                        "Project Collection", "❌ Unavailable", "Qdrant service down"
                    )

            except Exception as e:
                table.add_row(
                    "Qdrant Storage", "⚠️  Error", f"Inspection failed: {str(e)[:30]}"
                )

        # Check Data Cleaner (Qdrant-only service)
        # Only show Data Cleaner status for Qdrant backends, not filesystem
        if backend_provider != "filesystem":
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

        table.add_row("Semantic Index", index_status, index_details)

        # Add git repository status if available
        try:
            from .services.git_aware_processor import GitAwareDocumentProcessor

            processor = GitAwareDocumentProcessor(
                config,
                EmbeddingProviderFactory.create(config, console),
                QdrantClient(config.qdrant),
            )
            # Use fast git status (no file scanning) for status display performance
            git_status = processor.get_git_status_fast()

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

        # Display recovery guidance if indexes are missing (filesystem backend only)
        if (
            backend_provider == "filesystem"
            and fs_index_files_display
            and missing_components
        ):
            console.print("\n" + "━" * 80, style="yellow")
            console.print("⚠️  INDEX RECOVERY GUIDANCE", style="bold yellow")
            console.print()

            if "projection_matrix" in missing_components:
                console.print(
                    "🚨 CRITICAL: Projection Matrix Missing", style="red bold"
                )
                console.print(
                    "   The projection matrix cannot be recovered and all existing vectors are invalid."
                )
                console.print()
                console.print("   Recovery Required:", style="yellow")
                console.print("   cidx index --clear")
                console.print()
                console.print("   This will:", style="dim")
                console.print("   • Delete all vectors and indexes")
                console.print("   • Re-process all code files from scratch")
                console.print("   • Generate new embeddings via VoyageAI API")
                console.print("   • Create a new projection matrix")
                console.print()
                console.print("   ⏱️  Estimated time: 10-30 minutes")
                console.print("   💵 Cost: VoyageAI API usage charges apply")
                console.print()

            if "hnsw" in missing_components or "id_index" in missing_components:
                console.print("🔧 Recoverable Indexes:", style="yellow bold")
                console.print(
                    "   These indexes can be rebuilt from existing vector files without re-embedding."
                )
                console.print()

                if "hnsw" in missing_components:
                    console.print(
                        "   • HNSW Index (affects query performance):", style="cyan"
                    )
                    console.print("     cidx index --rebuild-index")
                    console.print("     Takes ~2-5 minutes, restores fast queries")
                    console.print()

                if "id_index" in missing_components:
                    console.print(
                        "   • ID Index (affects point lookups):", style="cyan"
                    )
                    console.print("     Rebuilds automatically on next query")
                    console.print("     No manual action required")
                    console.print()

            console.print("━" * 80, style="yellow")

    except Exception as e:
        console.print(f"❌ Failed to get status: {e}", style="red")
        sys.exit(1)


@cli.command()
@click.pass_context
def optimize(ctx):
    """Optimize vector database storage and performance."""
    config_manager = ctx.obj["config_manager"]

    try:
        # Lazy imports for optimize command

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
        # Lazy imports for force_flush command

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
@require_mode("local", "proxy")
def stop(ctx, force_docker: bool):
    """Stop code indexing services while preserving all data.

    In proxy mode, stops services sequentially across all configured repositories.

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
    # Handle proxy mode (Story 2.3 - Sequential Execution)
    project_root, mode = ctx.obj["project_root"], ctx.obj["mode"]
    if mode == "proxy":
        from .proxy import execute_proxy_command

        # Build args list from options
        args = []
        if force_docker:
            args.append("--force-docker")

        exit_code = execute_proxy_command(project_root, "stop", args)
        sys.exit(exit_code)

    try:
        # Lazy imports for stop command

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

        # Create backend based on configuration
        backend = BackendFactory.create(config, Path(config.codebase_dir))
        backend_info = backend.get_service_info()

        # Check if backend requires containers
        requires_containers = backend_info.get("requires_containers", False)

        if requires_containers:
            # Qdrant backend - use existing Docker flow
            console.print("🔧 Stopping Qdrant vector store containers...")

            # Initialize Docker manager
            project_config_dir = config_path.parent
            docker_manager = DockerManager(
                console,
                force_docker=force_docker,
                project_config_dir=project_config_dir,
            )

            # Check current status
            status = docker_manager.get_service_status()
            if status["status"] == "not_configured":
                console.print(
                    "ℹ️  Services not configured - nothing to stop", style="blue"
                )
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
                console.print(
                    "💡 Use 'code-indexer start' to resume with all data intact"
                )
            else:
                console.print("❌ Failed to stop some services", style="red")
                sys.exit(1)
        else:
            # Filesystem backend - no containers to stop
            console.print("📁 Using filesystem vector store (container-free)")
            console.print(
                "💾 No containers to stop - filesystem backend is always available"
            )

            # Call backend stop (no-op for filesystem)
            if backend.stop():
                console.print("✅ Filesystem backend stop complete (no-op)")
            else:
                console.print("❌ Failed to stop filesystem backend", style="red")
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
    # Check daemon delegation (Story 2.3)
    # CRITICAL: Skip daemon delegation if standalone flag is set (prevents recursive loop)
    standalone_mode = ctx.obj.get("standalone", False)
    if not standalone_mode:
        try:
            config_manager = ctx.obj.get("config_manager")
            if config_manager:
                daemon_config = config_manager.get_daemon_config()
                if daemon_config and daemon_config.get("enabled"):
                    # Delegate to daemon
                    exit_code = cli_daemon_delegation._clean_data_via_daemon(
                        all_projects=all_projects,
                        force_docker=force_docker,
                        all_containers=all_containers,
                        container_type=container_type,
                        json_output=json_output,
                        verify=verify,
                    )
                    sys.exit(exit_code)
        except Exception:
            # Daemon delegation failed, continue with standalone mode
            pass

    try:
        # Lazy imports for clean_data command

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
            # Use legacy DockerManager approach - but check if containers needed first
            config = (
                config_manager.load() if config_manager.config_path.exists() else None
            )
            if config and _needs_docker_manager(config):
                docker_manager = DockerManager(
                    force_docker=force_docker, project_config_dir=project_config_dir
                )

                success = docker_manager.clean_data_only(all_projects=all_projects)
            else:
                # Filesystem backend - no containers to clean
                console.print("ℹ️ Filesystem backend - no containers to clean")
                success = True
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


@cli.command("clean")
@click.option(
    "--collection",
    help="Specific collection to clean (if not specified, cleans default collection)",
)
@click.option(
    "--remove-projection-matrix",
    is_flag=True,
    help="Also remove projection matrix (requires re-indexing to restore)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.option(
    "--show-recommendations",
    is_flag=True,
    help="Show git-aware cleanup recommendations",
)
@click.pass_context
@require_mode("local", "remote")
def clean(
    ctx,
    collection: Optional[str],
    remove_projection_matrix: bool,
    force: bool,
    show_recommendations: bool,
):
    """Clear vectors from collection without removing structure.

    \b
    Removes all indexed vectors from a collection while preserving:
      • Collection metadata
      • Projection matrix (unless --remove-projection-matrix is specified)
      • Collection directory structure

    \b
    This is faster than full uninstall and allows quick re-indexing
    without recreating the collection structure.

    \b
    OPTIONS:
      --collection NAME              Clean specific collection
      --remove-projection-matrix     Also remove projection matrix
      --force                        Skip confirmation prompt
      --show-recommendations         Show git-aware cleanup recommendations
    """
    # Check daemon delegation (Story 2.3)
    # CRITICAL: Skip daemon delegation if standalone flag is set (prevents recursive loop)
    standalone_mode = ctx.obj.get("standalone", False)
    if not standalone_mode:
        try:
            config_manager = ctx.obj.get("config_manager")
            if config_manager:
                daemon_config = config_manager.get_daemon_config()
                if daemon_config and daemon_config.get("enabled"):
                    # Delegate to daemon
                    exit_code = cli_daemon_delegation._clean_via_daemon(
                        collection=collection,
                        remove_projection_matrix=remove_projection_matrix,
                        force=force,
                        show_recommendations=show_recommendations,
                    )
                    sys.exit(exit_code)
        except Exception:
            # Daemon delegation failed, continue with standalone mode
            pass

    try:
        config_manager = ctx.obj.get("config_manager")
        project_root = ctx.obj.get("project_root")

        if not config_manager or not project_root:
            console.print("❌ Configuration not found", style="red")
            sys.exit(1)

        config = config_manager.get_config()

        # Create backend

        backend = BackendFactory.create(config, project_root)

        # Get vector store client
        vector_store = backend.get_vector_store_client()

        # Determine collection to clean
        if collection is None:
            collections = vector_store.list_collections()
            if len(collections) == 0:
                console.print("ℹ️  No collections found to clean", style="blue")
                return
            elif len(collections) == 1:
                collection = collections[0]
            else:
                console.print(
                    "❌ Multiple collections exist. Please specify --collection",
                    style="red",
                )
                console.print(f"\nAvailable collections: {', '.join(collections)}")
                sys.exit(1)

        # Check if collection exists
        if not vector_store.collection_exists(collection):
            console.print(f"❌ Collection '{collection}' does not exist", style="red")
            sys.exit(1)

        # Get impact information
        vector_count = vector_store.count_points(collection)
        collection_size = 0
        if hasattr(vector_store, "get_collection_size"):
            collection_size = vector_store.get_collection_size(collection)

        # Show git-aware recommendations if requested
        if show_recommendations:
            console.print("\n📋 [bold]Git-Aware Cleanup Recommendations:[/bold]")
            try:
                import subprocess

                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0 and result.stdout.strip():
                    console.print("⚠️  You have uncommitted changes:")
                    console.print(
                        "💡 Consider committing changes before cleanup to avoid losing indexed data for modified files"
                    )
                else:
                    console.print("✅ No uncommitted changes detected")
            except Exception:
                pass  # Silently ignore git errors

        # Show impact and confirmation
        if not force:
            console.print(
                f"\n⚠️  [bold yellow]About to clean collection '{collection}'[/bold yellow]"
            )
            console.print(f"   • Vectors to remove: {vector_count}")
            if collection_size > 0:
                size_mb = collection_size / (1024 * 1024)
                console.print(f"   • Storage to reclaim: {size_mb:.2f} MB")
            if remove_projection_matrix:
                console.print(
                    "   • Projection matrix will be REMOVED (requires full re-indexing)"
                )
            else:
                console.print("   • Projection matrix will be PRESERVED")

            if not click.confirm("\nProceed with cleanup?"):
                console.print("❌ Cleanup cancelled", style="yellow")
                return

        # Record size before cleanup
        size_before = collection_size if collection_size > 0 else 0

        # Perform cleanup
        success = vector_store.clear_collection(
            collection, remove_projection_matrix=remove_projection_matrix
        )

        if success:
            console.print(
                f"✅ Collection '{collection}' cleaned successfully", style="green"
            )

            # Report space reclaimed
            if size_before > 0:
                size_mb = size_before / (1024 * 1024)
                console.print(f"💾 Storage reclaimed: {size_mb:.2f} MB")
        else:
            console.print(f"❌ Failed to clean collection '{collection}'", style="red")
            sys.exit(1)

    except Exception as e:
        console.print(f"❌ Clean failed: {e}", style="red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("list-collections")
@click.pass_context
@require_mode("local", "remote")
def list_collections_cmd(ctx):
    """List all collections with metadata and statistics.

    \b
    Shows collection information including:
      • Collection name
      • Vector count
      • Vector dimensions
      • Storage size
      • Creation date
    """
    try:
        config_manager = ctx.obj.get("config_manager")
        project_root = ctx.obj.get("project_root")

        if not config_manager or not project_root:
            console.print("❌ Configuration not found", style="red")
            sys.exit(1)

        config = config_manager.get_config()

        # Create backend

        backend = BackendFactory.create(config, project_root)

        # Get vector store client
        vector_store = backend.get_vector_store_client()

        # Get all collections
        collections = vector_store.list_collections()

        if not collections:
            console.print("ℹ️  No collections found", style="blue")
            return

        # Create table
        table = Table(title="Collections")
        table.add_column("Name", style="cyan")
        table.add_column("Vectors", justify="right", style="green")
        table.add_column("Dimensions", justify="right", style="yellow")
        table.add_column("Size", justify="right", style="magenta")
        table.add_column("Created", style="blue")

        # Populate table
        for coll_name in collections:
            # Get vector count
            vector_count = vector_store.count_points(coll_name)

            # Get metadata
            try:
                metadata = vector_store.get_collection_info(coll_name)
                vector_size = metadata.get("vector_size", "N/A")
                created_at = metadata.get("created_at", "N/A")
                if created_at != "N/A":
                    # Format datetime
                    from datetime import datetime

                    dt = datetime.fromisoformat(created_at)
                    created_at = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                vector_size = "N/A"
                created_at = "N/A"

            # Get collection size
            collection_size = 0
            if hasattr(vector_store, "get_collection_size"):
                collection_size = vector_store.get_collection_size(coll_name)

            size_str = "N/A"
            if collection_size > 0:
                size_mb = collection_size / (1024 * 1024)
                if size_mb >= 1.0:
                    size_str = f"{size_mb:.2f} MB"
                else:
                    size_kb = collection_size / 1024
                    size_str = f"{size_kb:.2f} KB"

            table.add_row(
                coll_name, str(vector_count), str(vector_size), size_str, created_at
            )

        console.print(table)

    except Exception as e:
        console.print(f"❌ Failed to list collections: {e}", style="red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("uninstall")
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
@require_mode("local", "remote", "proxy")
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
    PROXY MODE (Story 2.3):
      • Uninstalls services sequentially across all configured repositories
      • Prevents resource contention during cleanup
      • Shows progress for each repository

    \b
    The uninstall behavior automatically adapts based on your current configuration.
    """
    mode = ctx.obj["mode"]
    project_root = ctx.obj["project_root"]

    if mode == "proxy":
        # Handle proxy mode (Story 2.3 - Sequential Execution)
        from .proxy import execute_proxy_command

        # Build args list from options
        args = []
        if force_docker:
            args.append("--force-docker")
        if wipe_all:
            args.append("--wipe-all")
        if confirm:
            args.append("--confirm")

        exit_code = execute_proxy_command(project_root, "uninstall", args)
        sys.exit(exit_code)
    elif mode == "local":
        from .mode_specific_handlers import uninstall_local_mode

        uninstall_local_mode(project_root, force_docker, wipe_all, confirm)
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
@require_mode("local", "remote", "proxy")
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
    # Handle proxy mode (Story 2.2)
    mode = ctx.obj.get("mode")
    if mode == "proxy":
        from .proxy import execute_proxy_command

        project_root = ctx.obj["project_root"]

        # Build args list for fix-config command
        args = []
        if dry_run:
            args.append("--dry-run")
        if verbose:
            args.append("--verbose")
        if force:
            args.append("--force")

        exit_code = execute_proxy_command(project_root, "fix-config", args)
        sys.exit(exit_code)

    try:
        # Lazy imports for fix_config command
        from .services.config_fixer import ConfigurationRepairer, generate_fix_report

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
        from .sync.repository_context_detector import (
            RepositoryContextDetector,
            RepositoryContextError,
        )

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print(
                "   Run 'cidx init --remote <server-url> --username <user> --password <pass>' to set up remote mode",
                style="dim",
            )
            sys.exit(1)

        # Detect repository context for enhanced sync functionality
        repository_context = None
        try:
            detector = RepositoryContextDetector()
            repository_context = detector.detect_repository_context(Path.cwd())
        except RepositoryContextError as e:
            # Context detection failed, but continue with legacy behavior
            logger.debug(f"Repository context detection failed: {e}")
        except Exception as e:
            # Unexpected error, log but continue with legacy behavior
            logger.debug(f"Unexpected error during repository context detection: {e}")

        # Show sync operation details with repository context awareness
        if repository_context:
            # Repository-aware messaging
            if dry_run:
                console.print(
                    "🔍 Dry run mode - showing what would be synced:", style="blue"
                )
            else:
                console.print("🔄 Starting repository synchronization...", style="blue")
                console.print(
                    f"   Syncing repository '{repository_context.user_alias}' with golden repository '{repository_context.golden_repo_alias}'",
                    style="cyan",
                )
        else:
            # Legacy messaging
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
            if repository_context:
                console.print(
                    f"   Target: {repository_context.user_alias} (detected from current directory)",
                    style="dim",
                )
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
        from .remote.credential_rotation import CredentialRotationManager
        from .mode_detection.command_mode_detector import find_project_root

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


@auth_group.command("login")
@click.option("--username", "-u", help="Username for authentication")
@click.option("--password", "-p", help="Password for authentication")
@click.pass_context
@require_mode("remote")
def auth_login(ctx, username: Optional[str], password: Optional[str]):
    """Login to CIDX server with credentials.

    Authenticates with the CIDX server and stores encrypted credentials
    locally for subsequent authenticated operations.

    Examples:
        cidx auth login --username myuser --password mypass
        cidx auth login  # Interactive prompts for credentials
    """
    try:
        from .api_clients.auth_client import AuthAPIClient
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration to get server URL
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Interactive credential collection if not provided
        if not username:
            username = click.prompt("Username", type=str)

        if not password:
            password = getpass.getpass("Password: ")

        # Validate inputs
        if not username.strip():
            console.print("❌ Username cannot be empty", style="red")
            sys.exit(1)

        if not password.strip():
            console.print("❌ Password cannot be empty", style="red")
            sys.exit(1)

        # Create auth client and login
        auth_client = AuthAPIClient(server_url, project_root)

        with console.status("🔐 Authenticating..."):
            auth_response = asyncio.run(
                auth_client.login(username.strip(), password.strip())
            )

        console.print(f"✅ Successfully logged in as {username}", style="green")
        console.print("🔑 Credentials stored securely", style="cyan")

        if auth_response.get("user_id"):
            console.print(f"👤 User ID: {auth_response['user_id']}", style="dim")

        # Close the client
        asyncio.run(auth_client.close())

    except Exception as e:
        console.print(f"❌ Login failed: {e}", style="red")

        # Provide helpful error guidance
        error_str = str(e).lower()
        if "authentication failed" in error_str or "invalid" in error_str:
            console.print(
                "💡 Check your username and password are correct", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("💡 Check server connectivity and try again", style="dim")
        elif "server" in error_str:
            console.print(
                "💡 Server may be unreachable or experiencing issues", style="dim"
            )
        elif "too many" in error_str:
            console.print("💡 Wait a moment before trying again", style="dim")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@auth_group.command("register")
@click.option("--username", "-u", help="Username for new account")
@click.option("--password", "-p", help="Password for new account")
@click.option(
    "--role",
    default="user",
    type=click.Choice(["user", "admin"]),
    help="User role (default: user)",
)
@click.pass_context
@require_mode("remote")
def auth_register(ctx, username: Optional[str], password: Optional[str], role: str):
    """Register new user account and login.

    Creates a new user account on the CIDX server and automatically
    logs in with the new credentials.

    Examples:
        cidx auth register --username newuser --password newpass
        cidx auth register --username admin --role admin
        cidx auth register  # Interactive prompts for credentials
    """
    try:
        from .api_clients.auth_client import AuthAPIClient
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration to get server URL
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Interactive credential collection if not provided
        if not username:
            username = click.prompt("Username", type=str)

        if not password:
            password = getpass.getpass("Password: ")

        # Validate inputs
        if not username.strip():
            console.print("❌ Username cannot be empty", style="red")
            sys.exit(1)

        if not password.strip():
            console.print("❌ Password cannot be empty", style="red")
            sys.exit(1)

        # Create auth client and register
        auth_client = AuthAPIClient(server_url, project_root)

        with console.status("📝 Creating account..."):
            auth_response = asyncio.run(
                auth_client.register(username.strip(), password.strip(), role)
            )

        console.print(
            f"✅ Successfully registered and logged in as {username}", style="green"
        )
        console.print(f"👤 Account role: {role}", style="cyan")
        console.print("🔑 Credentials stored securely", style="cyan")

        if auth_response.get("user_id"):
            console.print(f"🆔 User ID: {auth_response['user_id']}", style="dim")

        # Close the client
        asyncio.run(auth_client.close())

    except Exception as e:
        console.print(f"❌ Registration failed: {e}", style="red")

        # Provide helpful error guidance
        error_str = str(e).lower()
        if "username already exists" in error_str or "conflict" in error_str:
            console.print(
                "💡 Try a different username or login with existing account",
                style="dim",
            )
        elif "password" in error_str and ("weak" in error_str or "policy" in error_str):
            console.print(
                "💡 Use a stronger password with numbers and symbols", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("💡 Check server connectivity and try again", style="dim")
        elif "server" in error_str:
            console.print(
                "💡 Server may be unreachable or experiencing issues", style="dim"
            )

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@auth_group.command("logout")
@click.pass_context
@require_mode("remote")
def auth_logout(ctx):
    """Logout and clear stored credentials.

    Clears all stored authentication credentials and resets
    authentication state for the current project.

    Example:
        cidx auth logout
    """
    try:
        from .api_clients.auth_client import AuthAPIClient
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration to get server URL
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Create auth client for logout
        auth_client = AuthAPIClient(server_url, project_root)

        with console.status("🚪 Logging out..."):
            auth_client.logout()

        console.print("✅ Successfully logged out", style="green")
        console.print("🔐 All credentials cleared", style="cyan")

        # Close the client
        asyncio.run(auth_client.close())

    except Exception as e:
        console.print(f"❌ Logout failed: {e}", style="red")

        # Provide helpful error guidance
        error_str = str(e).lower()
        if "not authenticated" in error_str or "no credentials" in error_str:
            console.print("💡 No stored credentials found to clear", style="dim")
        else:
            console.print("💡 Credentials may have been partially cleared", style="dim")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@auth_group.command("change-password")
@click.pass_context
@require_mode("remote")
def auth_change_password(ctx):
    """Change current user password with validation.

    Interactively prompts for current password, new password, and confirmation.
    Validates password strength and handles secure credential updates.

    Example:
        cidx auth change-password
    """
    try:
        from .api_clients.auth_client import create_auth_client
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .password_policy import validate_password_strength

        # Check authentication state first
        if not _check_authentication_state(ctx):
            return

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        console.print("🔐 Change Password", style="bold cyan")
        console.print("Enter your passwords (input will be hidden)", style="dim")

        # Interactive password collection with validation
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Get current password
                current_password = getpass.getpass("Current Password: ")
                if not current_password.strip():
                    console.print("❌ Current password cannot be empty", style="red")
                    continue

                # Get new password with validation loop
                while True:
                    new_password = getpass.getpass("New Password: ")
                    if not new_password.strip():
                        console.print("❌ New password cannot be empty", style="red")
                        continue

                    # Validate password strength
                    is_valid, message = validate_password_strength(new_password)
                    if not is_valid:
                        console.print(f"❌ {message}", style="red")
                        from .password_policy import get_password_policy_help

                        console.print("\n" + get_password_policy_help(), style="dim")
                        continue
                    break

                # Get password confirmation
                confirm_password = getpass.getpass("Confirm New Password: ")

                # Validate confirmation
                if new_password != confirm_password:
                    console.print(
                        "❌ Password confirmation does not match", style="red"
                    )
                    console.print("Please enter both passwords again", style="dim")
                    continue

                # All validations passed, proceed to server
                break

            except KeyboardInterrupt:
                console.print("\n❌ Password change cancelled", style="yellow")
                sys.exit(1)
        else:
            console.print("❌ Too many invalid attempts", style="red")
            sys.exit(1)

        # Create auth client and change password
        auth_client = create_auth_client(server_url, project_root)
        with console.status("🔒 Changing password..."):
            asyncio.run(
                auth_client.change_password(
                    current_password.strip(), new_password.strip()
                )
            )

        console.print("✅ Password changed successfully", style="green")
        console.print("🔐 Credentials updated securely", style="cyan")

        # Close the client
        asyncio.run(auth_client.close())

    except Exception as e:
        console.print(f"❌ Password change failed: {e}", style="red")
        # Provide helpful error guidance
        error_str = str(e).lower()
        if "current password is incorrect" in error_str or "invalid" in error_str:
            console.print("💡 Check your current password is correct", style="dim")
        elif "password does not meet" in error_str or "too weak" in error_str:
            console.print(
                "💡 Ensure new password meets security requirements", style="dim"
            )
        elif "authentication" in error_str:
            console.print("💡 Please login first with 'cidx auth login'", style="dim")
        else:
            console.print("💡 Check server connectivity and try again", style="dim")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@auth_group.command("reset-password")
@click.option("--username", "-u", help="Username for password reset")
@click.pass_context
@require_mode("remote")
def auth_reset_password(ctx, username: Optional[str]):
    """Initiate password reset for specified user.

    Sends password reset request to server. Username can be provided
    as parameter or entered interactively.

    Examples:
        cidx auth reset-password --username myuser
        cidx auth reset-password  # Interactive username prompt
    """
    try:
        from .api_clients.auth_client import create_auth_client
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Get username if not provided
        if not username:
            username = click.prompt("Username", type=str)

        # Validate username
        if not username.strip():
            console.print("❌ Username cannot be empty", style="red")
            sys.exit(1)

        console.print("📧 Password Reset Request", style="bold cyan")

        # Create auth client and initiate reset
        auth_client = create_auth_client(server_url, project_root)
        with console.status("📤 Sending reset request..."):
            asyncio.run(auth_client.reset_password(username.strip()))

        console.print(f"✅ Password reset request sent for {username}", style="green")
        console.print("📧 Check your email for reset instructions", style="blue")
        console.print(
            "🔗 Follow the link in the email to complete password reset", style="cyan"
        )

        # Close the client
        asyncio.run(auth_client.close())

    except Exception as e:
        console.print(f"❌ Password reset failed: {e}", style="red")
        # Provide helpful error guidance
        error_str = str(e).lower()
        if "user not found" in error_str or "username" in error_str:
            console.print("💡 Check the username is correct", style="dim")
        elif "too many" in error_str or "rate" in error_str:
            console.print("💡 Wait a few minutes before trying again", style="dim")
        else:
            console.print("💡 Check server connectivity and try again", style="dim")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@auth_group.command("status")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.option("--health", is_flag=True, help="Check credential health")
@click.pass_context
@require_mode("remote")
def auth_status(ctx, verbose: bool, health: bool):
    """Display current authentication status.

    Shows authentication state, username, role, token expiration,
    and server connectivity. Use --verbose for detailed information
    or --health for comprehensive credential diagnostics.

    Examples:
        cidx auth status                    # Basic status
        cidx auth status --verbose          # Detailed information
        cidx auth status --health           # Health diagnostics
    """
    try:
        import asyncio
        from .api_clients.auth_client import create_auth_client
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        try:
            remote_config = load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
        except FileNotFoundError:
            console.print("❌ Remote mode not configured", style="red")
            console.print(
                "This command requires remote mode to be configured.", style="yellow"
            )
            console.print("\nTo configure remote mode:", style="dim")
            console.print(
                "  1. Run 'cidx init --mode remote --server <server-url>'", style="dim"
            )
            console.print(
                "  2. Or connect to an existing server with 'cidx auth login'",
                style="dim",
            )
            sys.exit(1)
        except (KeyError, json.JSONDecodeError) as e:
            console.print("❌ Remote configuration is corrupted", style="red")
            console.print(f"Error: {str(e)}", style="red")
            console.print(
                "\nTry re-initializing with 'cidx init --mode remote --server <server-url>'",
                style="dim",
            )
            sys.exit(1)

        # Try to load existing credentials
        username = remote_config.get("username")

        # Create auth client
        auth_client = create_auth_client(
            server_url=server_url, project_root=project_root, username=username
        )

        async def run_status_check():
            if health:
                # Comprehensive health check
                health_result = await auth_client.check_credential_health()
                _display_health_status(health_result)
            else:
                # Regular status check
                status = await auth_client.get_auth_status()
                _display_auth_status(status, verbose)

        # Run async status check
        asyncio.run(run_status_check())

    except Exception as e:
        console.print(f"❌ Error checking authentication status: {e}", style="red")
        if verbose:
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@auth_group.command("refresh")
@click.pass_context
@require_mode("remote")
def auth_refresh(ctx):
    """Manually refresh authentication token.

    Attempts to refresh the current authentication token using the
    stored refresh token. Updates stored credentials on success.

    Examples:
        cidx auth refresh                   # Refresh current token
    """
    try:
        import asyncio
        from .api_clients.auth_client import create_auth_client
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Try to load existing credentials
        username = remote_config.get("username")
        if not username:
            console.print("❌ No stored credentials found", style="red")
            console.print("Use 'cidx auth login' to authenticate first", style="dim")
            sys.exit(1)

        # Create auth client
        auth_client = create_auth_client(
            server_url=server_url, project_root=project_root, username=username
        )

        async def run_refresh():
            try:
                console.print("🔄 Refreshing authentication token...", style="blue")

                refresh_response = await auth_client.refresh_token()

                console.print("✅ Token refreshed successfully", style="green")

                # Display new expiration time if available
                if refresh_response.get("access_token"):
                    from .api_clients.jwt_token_manager import JWTTokenManager

                    jwt_manager = JWTTokenManager()
                    expiry_time = jwt_manager.get_token_expiry_time(
                        refresh_response["access_token"]
                    )
                    if expiry_time:
                        console.print(
                            f"🕒 New token expires: {expiry_time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                            style="dim",
                        )

            except Exception as e:
                console.print(f"❌ Token refresh failed: {e}", style="red")
                if "expired" in str(e).lower() or "invalid" in str(e).lower():
                    console.print(
                        "💡 Use 'cidx auth login' to re-authenticate",
                        style="dim yellow",
                    )
                else:
                    console.print(
                        "💡 Check server connectivity and try again", style="dim yellow"
                    )
                raise

        # Run async refresh
        asyncio.run(run_refresh())

    except Exception:
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@auth_group.command("validate")
@click.option("--verbose", "-v", is_flag=True, help="Show validation details")
@click.pass_context
@require_mode("remote")
def auth_validate(ctx, verbose: bool):
    """Validate current credentials (silent by default).

    Silently validates current credentials and returns appropriate
    exit codes for automation use. Use --verbose for output.

    Exit codes:
        0 - Credentials are valid
        1 - Credentials are invalid or validation failed

    Examples:
        cidx auth validate                  # Silent validation
        cidx auth validate --verbose        # Show validation details
    """
    try:
        import asyncio
        from .api_clients.auth_client import create_auth_client
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            if verbose:
                console.print("❌ No project configuration found", style="red")
                console.print(
                    "Run 'cidx init' to initialize project first", style="dim"
                )
            sys.exit(1)

        # Load remote configuration
        try:
            remote_config = load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
        except FileNotFoundError:
            if verbose:
                console.print("❌ Remote mode not configured", style="red")
                console.print(
                    "This command requires remote mode to be configured.",
                    style="yellow",
                )
                console.print("\nTo configure remote mode:", style="dim")
                console.print(
                    "  1. Run 'cidx init --mode remote --server <server-url>'",
                    style="dim",
                )
                console.print(
                    "  2. Or connect to an existing server with 'cidx auth login'",
                    style="dim",
                )
            sys.exit(1)
        except (KeyError, json.JSONDecodeError) as e:
            if verbose:
                console.print("❌ Remote configuration is corrupted", style="red")
                console.print(f"Error: {str(e)}", style="red")
                console.print(
                    "\nTry re-initializing with 'cidx init --mode remote --server <server-url>'",
                    style="dim",
                )
            sys.exit(1)

        # Try to load existing credentials
        username = remote_config.get("username")
        if not username:
            if verbose:
                console.print("❌ No stored credentials found", style="red")
                console.print(
                    "Use 'cidx auth login' to authenticate first", style="dim"
                )
            sys.exit(1)

        # Create auth client
        auth_client = create_auth_client(
            server_url=server_url, project_root=project_root, username=username
        )

        async def run_validation():
            if verbose:
                console.print("🔍 Validating credentials...", style="blue")

            is_valid = await auth_client.validate_credentials()

            if verbose:
                if is_valid:
                    console.print("✅ Credentials are valid", style="green")
                else:
                    console.print("❌ Credentials are invalid", style="red")
                    console.print(
                        "💡 Use 'cidx auth login' to re-authenticate",
                        style="dim yellow",
                    )

            return is_valid

        # Run async validation
        is_valid = asyncio.run(run_validation())

        # Exit with appropriate code for automation
        sys.exit(0 if is_valid else 1)

    except Exception as e:
        if verbose:
            console.print(f"❌ Error validating credentials: {e}", style="red")
            if ctx.obj.get("verbose"):
                import traceback

                console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


def _display_auth_status(status, verbose: bool = False):
    """Display authentication status with Rich formatting."""
    console.print("\n[bold blue]CIDX Authentication Status[/bold blue]")
    console.print("=" * 30)

    # Defensive type checking to handle error propagation issues
    if status is None:
        console.print("❌ [red]Error: No status information available[/red]")
        console.print(
            "💡 [yellow]Try running 'cidx auth login' to authenticate[/yellow]"
        )
        return

    # Check if we received an error string instead of AuthStatus object
    if isinstance(status, str):
        console.print(f"❌ [red]Error: {status}[/red]")
        console.print(
            "💡 [yellow]Try running 'cidx auth login' to authenticate[/yellow]"
        )
        return

    # Check if we have a dict instead of AuthStatus (shouldn't happen but be defensive)
    if isinstance(status, dict):
        console.print("❌ [red]Error: Invalid status format received[/red]")
        if "error" in status:
            console.print(f"Details: {status['error']}")
        console.print(
            "💡 [yellow]Try running 'cidx auth login' to authenticate[/yellow]"
        )
        return

    # Validate we have the expected AuthStatus object with required attributes
    if not hasattr(status, "authenticated"):
        console.print("❌ [red]Error: Invalid authentication status object[/red]")
        console.print(
            "💡 [yellow]Try running 'cidx auth login' to authenticate[/yellow]"
        )
        return

    # Basic status
    if status.authenticated:
        console.print("✅ [green]Authenticated: Yes[/green]")
        console.print(f"👤 Username: {status.username}")
        console.print(f"🔑 Role: {status.role or 'unknown'}")

        # Token status
        if status.token_valid:
            console.print("🟢 [green]Token Status: Valid[/green]")
        else:
            console.print("🔴 [red]Token Status: Invalid/Expired[/red]")

        # Token expiration
        if status.token_expires:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            time_remaining = status.token_expires - now

            if time_remaining.total_seconds() > 0:
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)
                console.print(
                    f"🕒 Token expires: {status.token_expires.strftime('%Y-%m-%d %H:%M:%S UTC')} (in {hours}h {minutes}m)"
                )
            else:
                console.print(
                    f"⏰ [red]Token expired: {status.token_expires.strftime('%Y-%m-%d %H:%M:%S UTC')}[/red]"
                )

        # Server connectivity
        if status.server_reachable is not None:
            if status.server_reachable:
                console.print("🌐 [green]Server: Online[/green]")
            else:
                console.print("🌐 [red]Server: Unreachable[/red]")
    else:
        console.print("❌ [red]Authenticated: No[/red]")
        console.print("❓ Status: Not logged in")
        console.print("\n💡 [yellow]Use 'cidx auth login' to authenticate[/yellow]")

    console.print(f"🔗 Server: {status.server_url}")

    # Verbose information
    if verbose and status.authenticated:
        console.print("\n[bold]Detailed Information[/bold]")
        console.print("-" * 25)

        if status.last_refreshed:
            console.print(
                f"🔄 Last refreshed: {status.last_refreshed.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        if status.permissions:
            console.print(f"🛡️  Permissions: {', '.join(status.permissions)}")

        if status.server_version:
            console.print(f"📦 Server version: {status.server_version}")

        if status.server_reachable is not None:
            connectivity_status = "Online" if status.server_reachable else "Offline"
            console.print(f"🔌 Connection status: {connectivity_status}")


def _display_health_status(health):
    """Display credential health status with Rich formatting."""
    console.print("\n[bold blue]CIDX Credential Health Check[/bold blue]")
    console.print("=" * 35)

    # Defensive type checking to handle error propagation issues
    if health is None:
        console.print("❌ [red]Error: No health information available[/red]")
        console.print("💡 [yellow]Unable to perform credential health check[/yellow]")
        return

    # Check if we received an error string instead of CredentialHealth object
    if isinstance(health, str):
        console.print(f"❌ [red]Error: {health}[/red]")
        console.print("💡 [yellow]Check your network connection and try again[/yellow]")
        return

    # Validate we have the expected CredentialHealth object with required attributes
    if not hasattr(health, "healthy"):
        console.print("❌ [red]Error: Invalid health check response[/red]")
        console.print("💡 [yellow]Unable to verify credential health status[/yellow]")
        return

    # Overall health
    if health.healthy:
        console.print("✅ [green]Overall Health: Healthy[/green] ✓")
    else:
        console.print("❌ [red]Overall Health: Issues Found[/red] ✗")

    console.print("\n[bold]Checks Performed[/bold]")
    console.print("-" * 20)

    # Individual checks
    checks = [
        ("Credential file encryption", health.encryption_valid),
        ("Token signature validation", health.token_signature_valid),
        ("Server connectivity", health.server_reachable),
        ("File permissions", health.file_permissions_correct),
    ]

    for check_name, passed in checks:
        status_icon = "✓" if passed else "✗"
        status_color = "green" if passed else "red"
        console.print(f"  [{status_color}]{status_icon}[/{status_color}] {check_name}")

    # Issues and suggestions
    if health.issues:
        console.print("\n[bold red]Issues Found[/bold red]")
        console.print("-" * 15)
        for issue in health.issues:
            console.print(f"  ❗ {issue}")

    if health.recovery_suggestions:
        console.print("\n[bold yellow]Recovery Suggestions[/bold yellow]")
        console.print("-" * 25)
        for suggestion in health.recovery_suggestions:
            console.print(f"  💡 {suggestion}")

    if health.healthy:
        console.print(
            "\n🎉 [green]All credential components are functioning properly.[/green]"
        )


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
        from .server.lifecycle.server_lifecycle_manager import (
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
        from .server.lifecycle.server_lifecycle_manager import (
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
        from .server.lifecycle.server_lifecycle_manager import (
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
        from .server.lifecycle.server_lifecycle_manager import (
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


# System monitoring commands
@cli.group("system")
@click.pass_context
@require_mode("remote")
def system_group(ctx):
    """System monitoring and health check commands.

    Monitor CIDX server health, check system status, and view performance metrics.
    Provides access to server health endpoints for system diagnostics.

    Available commands:
      health         - Check system health status
    """
    pass


@system_group.command("health")
@click.option(
    "--detailed",
    "-d",
    is_flag=True,
    help="Show detailed health information including component status",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show verbose health information with additional details",
)
@click.pass_context
@require_mode("remote")
def system_health(ctx, detailed: bool, verbose: bool):
    """Check system health status.

    Performs health checks on the CIDX server to monitor system status,
    component health, and performance metrics. Provides both basic and
    detailed health information with response time measurement.

    Examples:
        cidx system health                    # Basic health check
        cidx system health --detailed         # Detailed component status
        cidx system health --verbose          # Verbose information
        cidx system health --detailed --verbose  # Combined detailed and verbose
    """
    try:
        import asyncio
        from .api_clients.system_client import create_system_client
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        try:
            remote_config = load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
        except FileNotFoundError:
            console.print("❌ Remote mode not configured", style="red")
            console.print(
                "This command requires remote mode to be configured.", style="yellow"
            )
            console.print("\nTo configure remote mode:", style="dim")
            console.print(
                "  1. Run 'cidx init --mode remote --server <server-url>'", style="dim"
            )
            console.print(
                "  2. Or connect to an existing server with 'cidx auth login'",
                style="dim",
            )
            sys.exit(1)
        except (KeyError, json.JSONDecodeError) as e:
            console.print("❌ Remote configuration is corrupted", style="red")
            console.print(f"Error: {str(e)}", style="red")
            console.print(
                "\nTry re-initializing with 'cidx init --mode remote --server <server-url>'",
                style="dim",
            )
            sys.exit(1)

        # Try to load existing credentials
        username = remote_config.get("username")

        # Create system client
        system_client = create_system_client(
            server_url=server_url, project_root=project_root, username=username
        )

        async def run_health_check():
            try:
                if detailed or verbose:
                    # Use detailed health endpoint for rich information
                    health_result = await system_client.check_detailed_health()
                    _display_detailed_health_status(health_result, verbose)
                else:
                    # Use basic health endpoint for simple check
                    health_result = await system_client.check_basic_health()
                    _display_basic_health_status(health_result)

            except Exception as e:
                from .api_clients.base_client import AuthenticationError, APIClientError

                if isinstance(e, AuthenticationError):
                    console.print("❌ Authentication failed", style="red")
                    console.print(f"Error: {str(e)}", style="red")
                    console.print("Try running 'cidx auth login' first", style="dim")
                    sys.exit(1)
                elif isinstance(e, APIClientError):
                    console.print("❌ Health check failed", style="red")
                    console.print(f"Error: {str(e)}", style="red")
                    sys.exit(1)
                else:
                    console.print(
                        "❌ Unexpected error during health check", style="red"
                    )
                    console.print(f"Error: {str(e)}", style="red")
                    sys.exit(1)

        # Run async health check
        asyncio.run(run_health_check())

    except KeyboardInterrupt:
        console.print("\n❌ Operation cancelled by user", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")
        sys.exit(1)


def _display_basic_health_status(health_result: dict):
    """Display basic health status in a clean format."""
    # Defensive type checking to handle error propagation issues
    if health_result is None:
        console.print("❌ [red]Error: No health information available[/red]")
        console.print(
            "💡 [yellow]Server may be unreachable. Check your connection[/yellow]"
        )
        return

    # Check if we received an error string instead of dict
    if isinstance(health_result, str):
        console.print(f"❌ [red]Health Check Error: {health_result}[/red]")
        console.print(
            "💡 [yellow]Server may be experiencing issues. Try again later[/yellow]"
        )
        return

    # Ensure we have a dict-like object with get method
    if not hasattr(health_result, "get"):
        console.print("❌ [red]Error: Invalid health check response format[/red]")
        console.print(f"Received type: {type(health_result).__name__}")
        return

    status = health_result.get("status", "unknown")
    message = health_result.get("message", "No status message")
    response_time = health_result.get("response_time_ms", 0)

    # Convert status to display format
    status_display = status.upper() if status == "ok" else status.title()

    console.print(
        f"System Health: {status_display}", style="green" if status == "ok" else "red"
    )
    console.print(f"Response Time: {response_time}ms", style="cyan")
    console.print(f"Status: {message}", style="dim")


def _display_detailed_health_status(health_result: dict, verbose: bool = False):
    """Display detailed health status with rich formatting."""
    # Defensive type checking to handle error propagation issues
    if health_result is None:
        console.print("❌ [red]Error: No detailed health information available[/red]")
        console.print(
            "💡 [yellow]Server may be unreachable. Check your connection[/yellow]"
        )
        return

    # Check if we received an error string instead of dict
    if isinstance(health_result, str):
        console.print(f"❌ [red]Detailed Health Check Error: {health_result}[/red]")
        console.print(
            "💡 [yellow]Server may be experiencing issues. Try again later[/yellow]"
        )
        return

    # Ensure we have a dict-like object with get method
    if not hasattr(health_result, "get"):
        console.print("❌ [red]Error: Invalid detailed health response format[/red]")
        console.print(f"Received type: {type(health_result).__name__}")
        return

    status = health_result.get("status", "unknown")
    response_time = health_result.get("response_time_ms", 0)
    services = health_result.get("services", {})
    system_info = health_result.get("system", {})
    timestamp = health_result.get("timestamp", "")

    # Overall status section
    console.print("=== System Health Status ===", style="bold blue")
    status_display = status.upper() if status in ["ok", "healthy"] else status.title()
    console.print(
        f"Overall Status: {status_display}",
        style="green" if status in ["ok", "healthy"] else "red",
    )
    console.print(f"Response Time: {response_time}ms", style="cyan")

    # Detailed component status
    if services:
        console.print("\n=== Detailed Component Status ===", style="bold blue")
        for service_name, service_info in services.items():
            service_status = service_info.get("status", "unknown")
            service_name_display = service_name.replace("_", " ").title()

            status_color = "green" if service_status in ["ok", "healthy"] else "red"
            console.print(
                f"{service_name_display}: {service_status}", style=status_color
            )

            if verbose and service_info.get("response_time_ms") is not None:
                console.print(
                    f"  Response Time: {service_info['response_time_ms']}ms",
                    style="dim",
                )

            if service_info.get("error_message"):
                console.print(f"  Error: {service_info['error_message']}", style="red")

    # System information
    if system_info:
        console.print("\n=== System Information ===", style="bold blue")
        if "memory_usage_percent" in system_info:
            console.print(
                f"Memory Usage: {system_info['memory_usage_percent']}%", style="yellow"
            )
        if "cpu_usage_percent" in system_info:
            console.print(
                f"CPU Usage: {system_info['cpu_usage_percent']}%", style="yellow"
            )
        if "active_jobs" in system_info:
            console.print(f"Active Jobs: {system_info['active_jobs']}", style="cyan")
        if "disk_free_space_gb" in system_info:
            console.print(
                f"Disk Free Space: {system_info['disk_free_space_gb']} GB", style="cyan"
            )

    # Verbose information
    if verbose:
        console.print("\n=== Verbose Health Information ===", style="bold blue")
        if timestamp:
            console.print(f"Timestamp: {timestamp}", style="dim")

        # Show individual service response times
        if services:
            for service_name, service_info in services.items():
                if service_info.get("response_time_ms") is not None:
                    service_name_display = service_name.replace("_", " ").title()
                    console.print(
                        f"{service_name_display} Response Time: {service_info['response_time_ms']}ms",
                        style="dim",
                    )


# Repository management commands
@cli.group("repos")
@click.pass_context
@require_mode("remote")
def repos_group(ctx):
    """Repository management commands.

    Browse, discover, and manage your repositories in the CIDX system.

    Available commands:
      list           - List your activated repositories
      available      - Browse available golden repositories
      discover       - Discover repositories from remote sources
      status         - Show comprehensive repository status overview
      info           - Show detailed repository information
      switch-branch  - Switch branch in activated repository
      activate       - Activate a golden repository for personal use
      deactivate     - Deactivate a personal repository
    """
    pass


@repos_group.command(name="list")
@click.option("--filter", help="Filter repositories by pattern")
@click.pass_context
def list_repos(ctx, filter: Optional[str]):
    """List activated repositories.

    Shows your currently activated repositories with their sync status,
    current branch, and last sync information.

    EXAMPLES:
      cidx repos list                     # List all activated repositories
      cidx repos list --filter web        # Filter repositories containing 'web'
    """
    try:
        from pathlib import Path
        import asyncio
        from .mode_detection.command_mode_detector import find_project_root

        # Get project root and credentials
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ Not in a CIDX project directory", style="red")
            sys.exit(1)

        # Load remote configuration and credentials
        try:
            from .remote.sync_execution import (
                _load_remote_configuration,
                _load_and_decrypt_credentials,
            )

            remote_config = _load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
            credentials = _load_and_decrypt_credentials(project_root)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "   Please run 'cidx init --remote' to configure authentication.",
                style="dim",
            )
            sys.exit(1)

        # Create client and fetch repositories with proper cleanup

        async def fetch_repositories():
            client = ReposAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            )
            try:
                return await client.list_activated_repositories(filter_pattern=filter)
            finally:
                # Ensure client is properly closed to avoid resource warnings
                await client.close()

        repositories = asyncio.run(fetch_repositories())

        # Display results
        if not repositories:
            console.print("📦 No repositories activated", style="yellow")
            console.print("\n💡 To activate repositories:", style="blue")
            console.print(
                "   cidx repos available    # Browse available repositories",
                style="dim",
            )
            return

        # Format and display repository table
        table = Table(title="Activated Repositories", show_header=True)
        table.add_column("Alias", style="cyan")
        table.add_column("Branch", style="green")
        table.add_column("Sync Status", style="yellow")
        table.add_column("Last Sync", style="magenta")
        table.add_column("Actions", style="white")

        for repo in repositories:
            # Format sync status with icons
            if repo.sync_status == "synced":
                status = "✓ Synced"
                status_style = "green"
            elif repo.sync_status == "needs_sync":
                status = "⚠ Needs sync"
                status_style = "yellow"
            elif repo.sync_status == "conflict":
                status = "✗ Conflict"
                status_style = "red"
            else:
                status = repo.sync_status
                status_style = "white"

            # Format last sync time
            from datetime import datetime, timezone

            try:
                last_sync = datetime.fromisoformat(
                    repo.last_sync.replace("Z", "+00:00")
                )
                now = datetime.now(timezone.utc)
                diff = now - last_sync

                if diff.days > 0:
                    time_str = f"{diff.days}d ago"
                elif diff.seconds > 3600:
                    time_str = f"{diff.seconds // 3600}h ago"
                else:
                    time_str = f"{diff.seconds // 60}m ago"
            except (ValueError, TypeError, AttributeError):
                time_str = "Unknown"

            # Suggest actions
            actions = ""
            if repo.sync_status == "needs_sync":
                actions = "sync"
            elif repo.sync_status == "conflict":
                actions = "resolve"

            table.add_row(
                repo.alias,
                repo.current_branch,
                f"[{status_style}]{status}[/{status_style}]",
                time_str,
                actions,
            )

        console.print(table)
        console.print(f"\n📊 Total: {len(repositories)} repositories", style="blue")

    except ImportError as e:
        console.print(f"❌ Missing dependency: {e}", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Error listing repositories: {e}", style="red")
        sys.exit(1)


@repos_group.command(name="available")
@click.option("--search", help="Search available repositories")
@click.pass_context
def available(ctx, search: Optional[str]):
    """Show available golden repositories.

    Browse golden repositories available for activation, showing which
    ones you already have activated.

    EXAMPLES:
      cidx repos available                  # List all available repositories
      cidx repos available --search web     # Search for repositories containing 'web'
    """
    try:
        from pathlib import Path
        import asyncio
        from .mode_detection.command_mode_detector import find_project_root

        # Get project root and credentials
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ Not in a CIDX project directory", style="red")
            sys.exit(1)

        # Load remote configuration and credentials
        try:
            from .remote.sync_execution import (
                _load_remote_configuration,
                _load_and_decrypt_credentials,
            )

            remote_config = _load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
            credentials = _load_and_decrypt_credentials(project_root)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "   Please run 'cidx init --remote' to configure authentication.",
                style="dim",
            )
            sys.exit(1)

        # Create client and fetch repositories
        async def fetch_repositories():
            client = ReposAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            )
            try:
                return await client.list_available_repositories(search_term=search)
            finally:
                await client.close()

        repositories = asyncio.run(fetch_repositories())

        # Display results
        if not repositories:
            console.print("📦 No repositories available", style="yellow")
            return

        # Format and display repository table
        table = Table(title="Available Golden Repositories", show_header=True)
        table.add_column("Alias", style="cyan")
        table.add_column("Description", style="white", max_width=50)
        table.add_column("Default Branch", style="green")
        table.add_column("Branches", style="yellow")
        table.add_column("Status", style="magenta")

        for repo in repositories:
            # Format activation status
            if repo.is_activated:
                status = "✓ Already activated"
                status_style = "green"
            else:
                status = "Available"
                status_style = "yellow"

            # Format branches (show first few)
            branches = repo.indexed_branches[:3]
            if len(repo.indexed_branches) > 3:
                branches_str = (
                    ", ".join(branches) + f" (+{len(repo.indexed_branches) - 3} more)"
                )
            else:
                branches_str = ", ".join(branches)

            table.add_row(
                repo.alias,
                (
                    repo.description[:47] + "..."
                    if len(repo.description) > 50
                    else repo.description
                ),
                repo.default_branch,
                branches_str,
                f"[{status_style}]{status}[/{status_style}]",
            )

        console.print(table)
        console.print(f"\n📊 Total: {len(repositories)} repositories", style="blue")

        # Show activation guidance
        available_count = sum(1 for repo in repositories if not repo.is_activated)
        if available_count > 0:
            console.print(
                f"\n💡 {available_count} repositories available for activation",
                style="blue",
            )
            console.print(
                "   Use: cidx activate <alias>     # Activate a repository", style="dim"
            )

    except ImportError as e:
        console.print(f"❌ Missing dependency: {e}", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Error listing available repositories: {e}", style="red")
        sys.exit(1)


@repos_group.command(name="discover")
@click.option("--source", required=True, help="Repository source to discover")
@click.pass_context
def discover(ctx, source: str):
    """Discover repositories from remote sources.

    Search for repositories in GitHub organizations, GitLab groups,
    or specific Git URLs to see what's available for addition.

    EXAMPLES:
      cidx repos discover --source github.com/myorg      # GitHub organization
      cidx repos discover --source gitlab.com/mygroup    # GitLab group
      cidx repos discover --source https://git.example.com/repo.git  # Direct URL
    """
    try:
        from pathlib import Path
        import asyncio
        from .mode_detection.command_mode_detector import find_project_root

        # Get project root and credentials
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ Not in a CIDX project directory", style="red")
            sys.exit(1)

        # Load remote configuration and credentials
        try:
            from .remote.sync_execution import (
                _load_remote_configuration,
                _load_and_decrypt_credentials,
            )

            remote_config = _load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
            credentials = _load_and_decrypt_credentials(project_root)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "   Please run 'cidx init --remote' to configure authentication.",
                style="dim",
            )
            sys.exit(1)

        # Create client and discover repositories
        console.print(f"🔍 Discovering repositories from: {source}", style="blue")

        async def discover_repositories():
            client = ReposAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            )
            try:
                return await client.discover_repositories(source)
            finally:
                await client.close()

        result = asyncio.run(discover_repositories())

        # Display results
        if not result.discovered_repositories:
            console.print("📦 No repositories discovered", style="yellow")
            return

        # Format and display discovery results
        table = Table(
            title=f"Discovered Repositories from {result.source}", show_header=True
        )
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white", max_width=40)
        table.add_column("Default Branch", style="green")
        table.add_column("Availability", style="magenta")
        table.add_column("Accessibility", style="yellow")

        for repo in result.discovered_repositories:
            # Format availability status
            if repo.is_available:
                availability = "✓ Already available"
                availability_style = "green"
            else:
                availability = "Not available"
                availability_style = "yellow"

            # Format accessibility
            accessibility = "✓ Accessible" if repo.is_accessible else "✗ Not accessible"
            accessibility_style = "green" if repo.is_accessible else "red"

            table.add_row(
                repo.name,
                (
                    repo.description[:37] + "..."
                    if len(repo.description) > 40
                    else repo.description
                ),
                repo.default_branch,
                f"[{availability_style}]{availability}[/{availability_style}]",
                f"[{accessibility_style}]{accessibility}[/{accessibility_style}]",
            )

        console.print(table)
        console.print(f"\n📊 Total discovered: {result.total_discovered}", style="blue")

        # Show access errors if any
        if result.access_errors:
            console.print(
                f"\n⚠️ Access errors ({len(result.access_errors)}):", style="yellow"
            )
            for error in result.access_errors:
                console.print(f"   • {error}", style="dim")

        # Show next steps
        available_count = sum(
            1
            for repo in result.discovered_repositories
            if not repo.is_available and repo.is_accessible
        )
        if available_count > 0:
            console.print(
                f"\n💡 {available_count} repositories can be requested for addition",
                style="blue",
            )
            console.print(
                "   Contact your administrator to add these repositories to the system",
                style="dim",
            )

    except ImportError as e:
        console.print(f"❌ Missing dependency: {e}", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Error discovering repositories: {e}", style="red")
        sys.exit(1)


@repos_group.command("status")
@click.pass_context
def repos_status(ctx):
    """Show comprehensive repository status overview.

    Displays a dashboard-style summary of all repository information
    including activated repositories, available repositories, sync status,
    and personalized recommendations.
    """
    try:
        from pathlib import Path
        import asyncio
        from .mode_detection.command_mode_detector import find_project_root

        # Get project root and credentials
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ Not in a CIDX project directory", style="red")
            sys.exit(1)

        # Load remote configuration and credentials
        try:
            from .remote.sync_execution import (
                _load_remote_configuration,
                _load_and_decrypt_credentials,
            )

            remote_config = _load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
            credentials = _load_and_decrypt_credentials(project_root)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "   Please run 'cidx init --remote' to configure authentication.",
                style="dim",
            )
            sys.exit(1)

        # Create client and fetch status

        async def fetch_status():
            client = ReposAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            )
            try:
                return await client.get_repository_status_summary()
            finally:
                await client.close()

        summary = asyncio.run(fetch_status())

        # Display comprehensive status
        console.print("📊 Repository Status Overview", style="bold blue")
        console.print()

        # Activated repositories summary
        activated = summary.activated_repositories
        console.print("🔗 Activated Repositories", style="bold cyan")
        console.print(f"   Total: {activated.total_count}", style="white")
        console.print(f"   ✓ Synced: {activated.synced_count}", style="green")
        console.print(f"   ⚠ Need sync: {activated.needs_sync_count}", style="yellow")
        console.print(f"   ✗ Conflicts: {activated.conflict_count}", style="red")
        console.print()

        # Available repositories summary
        available = summary.available_repositories
        console.print("📦 Available Repositories", style="bold cyan")
        console.print(f"   Total available: {available.total_count}", style="white")
        console.print(
            f"   Not activated: {available.not_activated_count}", style="yellow"
        )
        console.print()

        # Recent activity
        if summary.recent_activity.recent_syncs:
            console.print("📈 Recent Activity", style="bold cyan")
            for sync in summary.recent_activity.recent_syncs[:3]:  # Show last 3
                try:
                    from datetime import datetime, timezone

                    sync_time = datetime.fromisoformat(
                        sync.get("sync_date", "").replace("Z", "+00:00")
                    )
                    now = datetime.now(timezone.utc)
                    diff = now - sync_time

                    if diff.days > 0:
                        time_str = f"{diff.days}d ago"
                    elif diff.seconds > 3600:
                        time_str = f"{diff.seconds // 3600}h ago"
                    else:
                        time_str = f"{diff.seconds // 60}m ago"
                except (ValueError, TypeError, AttributeError):
                    time_str = "recently"

                status_icon = "✓" if sync.get("status") == "success" else "⚠"
                console.print(
                    f"   {status_icon} {sync.get('alias', 'unknown')} synced {time_str}",
                    style="white",
                )
            console.print()

        # Recent activations
        if activated.recent_activations:
            console.print("🆕 Recent Activations", style="bold cyan")
            for activation in activated.recent_activations[:3]:  # Show last 3
                console.print(
                    f"   ✓ {activation.get('alias', 'unknown')}", style="green"
                )
            console.print()

        # Recommendations
        if summary.recommendations:
            console.print("💡 Recommendations", style="bold cyan")
            for rec in summary.recommendations:
                console.print(f"   • {rec}", style="white")
            console.print()

        # Quick actions
        console.print("🚀 Quick Actions", style="bold cyan")
        console.print(
            "   cidx repos list         # View your repositories", style="dim"
        )
        console.print(
            "   cidx repos available    # Browse new repositories", style="dim"
        )
        console.print("   cidx sync --all         # Sync all repositories", style="dim")

    except ImportError as e:
        console.print(f"❌ Missing dependency: {e}", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Error getting repository status: {e}", style="red")
        sys.exit(1)


@repos_group.command(name="activate")
@click.argument("golden_alias")
@click.option("--as", "user_alias", help="Alias for activated repository")
@click.option("--branch", help="Initial branch to activate")
@click.pass_context
def activate(ctx, golden_alias: str, user_alias: str, branch: str):
    """Activate a golden repository for personal use.

    Creates a personal instance of a golden repository with CoW cloning
    for efficient storage sharing while providing independent access.

    Examples:
      cidx repos activate web-service                        # Use same alias
      cidx repos activate web-service --as my-web-app        # Custom alias
      cidx repos activate web-service --branch feature-v2    # Specific branch
    """
    try:
        # Default user_alias to golden_alias if not provided
        if not user_alias:
            user_alias = golden_alias

        execute_repository_activation(
            golden_alias=golden_alias, user_alias=user_alias, target_branch=branch
        )
    except Exception as e:
        console.print(f"❌ Error activating repository: {e}", style="red")
        sys.exit(1)


@repos_group.command(name="deactivate")
@click.argument("user_alias")
@click.option(
    "--force", is_flag=True, help="Force deactivation of problematic repositories"
)
@click.confirmation_option(
    prompt="Deactivate repository? This will remove all local data."
)
@click.pass_context
def deactivate(ctx, user_alias: str, force: bool):
    """Deactivate a personal repository.

    Removes the activated repository and cleans up associated resources
    including containers, configuration, and local data.

    Examples:
      cidx repos deactivate my-repo                # Normal deactivation
      cidx repos deactivate broken-repo --force    # Force cleanup
    """
    try:
        execute_repository_deactivation(
            user_alias=user_alias,
            force=force,
            confirmed=True,  # Already confirmed by click.confirmation_option
        )
    except Exception as e:
        console.print(f"❌ Error deactivating repository: {e}", style="red")
        sys.exit(1)


@repos_group.command(name="info")
@click.argument("user_alias")
@click.option("--branches", is_flag=True, help="Show detailed branch information")
@click.option("--health", is_flag=True, help="Show repository health status")
@click.option("--activity", is_flag=True, help="Show recent repository activity")
@click.pass_context
def info(ctx, user_alias: str, branches: bool, health: bool, activity: bool):
    """Show detailed repository information.

    Displays comprehensive information about an activated repository including
    basic metadata, branch information, health status, and recent activity.

    EXAMPLES:
      cidx repos info my-project                    # Basic repository information
      cidx repos info my-project --branches        # Include branch details
      cidx repos info my-project --health          # Include health monitoring
      cidx repos info my-project --activity        # Include activity tracking
      cidx repos info my-project --branches --health --activity  # Show everything
    """
    try:
        import asyncio
        from pathlib import Path
        from .mode_detection.command_mode_detector import find_project_root

        # Get project root and credentials
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ Not in a CIDX project directory", style="red")
            sys.exit(1)

        # Load remote configuration and credentials
        try:
            from .remote.sync_execution import (
                _load_remote_configuration,
                _load_and_decrypt_credentials,
            )

            remote_config = _load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
            credentials = _load_and_decrypt_credentials(project_root)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "   Please run 'cidx init --remote' to configure authentication.",
                style="dim",
            )
            sys.exit(1)

        # Execute repository info retrieval
        asyncio.run(
            _execute_repository_info(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
                user_alias=user_alias,
                branches=branches,
                health=health,
                activity=activity,
            )
        )
    except Exception as e:
        console.print(f"❌ Error retrieving repository information: {e}", style="red")
        sys.exit(1)


@repos_group.command(name="switch-branch")
@click.argument("user_alias")
@click.argument("branch_name")
@click.option("--create", is_flag=True, help="Create branch if it doesn't exist")
@click.pass_context
def switch_branch(ctx, user_alias: str, branch_name: str, create: bool):
    """Switch branch in activated repository.

    Switches the specified repository to a different branch, with support
    for creating new branches and handling remote tracking branches.

    EXAMPLES:
      cidx repos switch-branch my-project develop           # Switch to existing branch
      cidx repos switch-branch my-project feature/new --create  # Create and switch
    """
    try:
        import asyncio
        from pathlib import Path
        from .mode_detection.command_mode_detector import find_project_root

        # Get project root and credentials
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ Not in a CIDX project directory", style="red")
            sys.exit(1)

        # Load remote configuration and credentials
        try:
            from .remote.sync_execution import (
                _load_remote_configuration,
                _load_and_decrypt_credentials,
            )

            remote_config = _load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
            credentials = _load_and_decrypt_credentials(project_root)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "   Please run 'cidx init --remote' to configure authentication.",
                style="dim",
            )
            sys.exit(1)

        # Execute branch switching
        asyncio.run(
            _execute_branch_switch(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
                user_alias=user_alias,
                branch_name=branch_name,
                create=create,
            )
        )
    except Exception as e:
        console.print(f"❌ Error switching repository branch: {e}", style="red")
        sys.exit(1)


@repos_group.command("sync")
@click.argument("user_alias", required=False)
@click.option("--all", is_flag=True, help="Sync all activated repositories")
@click.option("--force", is_flag=True, help="Force sync by cancelling existing jobs")
@click.option(
    "--full-reindex", is_flag=True, help="Force full re-indexing instead of incremental"
)
@click.option("--no-pull", is_flag=True, help="Skip git pull, only perform indexing")
@click.option("--timeout", type=int, default=300, help="Job timeout in seconds")
@click.pass_context
def repos_sync(
    ctx,
    user_alias: Optional[str],
    all: bool,
    force: bool,
    full_reindex: bool,
    no_pull: bool,
    timeout: int,
):
    """Sync repositories with golden repositories.

    \b
    Synchronize activated repositories with their corresponding golden repositories.
    Supports both individual repository sync and bulk sync operations.

    \b
    SYNC MODES:
      • Individual: cidx repos sync my-project        # Sync specific repository
      • All repos:  cidx repos sync --all             # Sync all activated repositories

    \b
    SYNC OPTIONS:
      • --force           Cancel existing jobs and force new sync
      • --full-reindex    Force complete re-indexing (slower but thorough)
      • --no-pull         Skip git pull, only index existing files
      • --timeout 600     Set job timeout (default: 300 seconds)

    \b
    EXAMPLES:
      cidx repos sync my-project              # Sync specific repository
      cidx repos sync --all                   # Sync all repositories
      cidx repos sync --all --force           # Force sync all repositories
      cidx repos sync my-project --no-pull    # Sync without git pull
    """
    try:
        # Import here to avoid circular imports
        from .mode_detection.command_mode_detector import find_project_root
        from .api_clients.base_client import (
            AuthenticationError,
            NetworkError,
            APIClientError,
        )

        # Validate arguments
        if user_alias and all:
            console.print(
                "❌ Error: Cannot specify both repository alias and --all flag",
                style="red",
            )
            console.print(
                "   Use either 'cidx repos sync <alias>' or 'cidx repos sync --all'",
                style="dim",
            )
            sys.exit(1)

        if timeout <= 0:
            console.print("❌ Error: Timeout must be a positive number", style="red")
            sys.exit(1)

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print(
                "   Run 'cidx init --remote' to set up remote mode", style="dim"
            )
            sys.exit(1)

        # Create repos client - use synchronous wrapper
        from .api_clients.repos_client import SyncReposAPIClient

        repos_client = SyncReposAPIClient(project_root)

        # Show sync operation details
        if all:
            console.print("🔄 Syncing all activated repositories...", style="blue")
        elif user_alias:
            console.print(f"🔄 Syncing repository '{user_alias}'...", style="blue")
        else:
            console.print(
                "❌ Error: Must specify repository alias or use --all flag", style="red"
            )
            console.print(
                "   Use 'cidx repos sync <alias>' or 'cidx repos sync --all'",
                style="dim",
            )
            sys.exit(1)

        # Execute sync operation
        if all:
            results = repos_client.sync_all_repositories(
                force_sync=force,
                incremental=not full_reindex,
                pull_remote=not no_pull,
                timeout=timeout,
            )
        else:
            # Type guard - we've already validated user_alias is not None above
            assert user_alias is not None
            result = repos_client.sync_repository(
                user_alias,
                force_sync=force,
                incremental=not full_reindex,
                pull_remote=not no_pull,
                timeout=timeout,
            )
            results = [result]

        # Display results
        console.print()
        console.print("✅ Sync operation results:", style="green bold")

        successful_count = 0
        failed_count = 0

        for result in results:
            if result.status in ["completed", "success"]:
                console.print(
                    f"   ✅ {result.repository}: {result.message}", style="green"
                )
                successful_count += 1
            elif result.status in ["failed", "error"]:
                console.print(
                    f"   ❌ {result.repository}: {result.message}", style="red"
                )
                failed_count += 1
            elif result.status == "conflict":
                console.print(
                    f"   ⚠️  {result.repository}: Sync conflicts detected",
                    style="yellow",
                )
                console.print(f"      {result.message}", style="dim")
                console.print("      Manual resolution required", style="yellow")
                failed_count += 1
            else:
                console.print(
                    f"   ℹ️ {result.repository}: {result.message}", style="blue"
                )

        if len(results) > 1:
            console.print()
            console.print(
                f"📊 Summary: {successful_count} successful, {failed_count} failed",
                style="cyan",
            )

        if failed_count > 0:
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
    except APIClientError as e:
        console.print(f"❌ API error: {e}", style="red")
        if e.status_code == 404:
            console.print(
                "   💡 Repository not found - check repository alias", style="dim"
            )
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Failed to sync repository: {e}", style="red")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@repos_group.command("sync-status")
@click.argument("user_alias", required=False)
@click.option("--detailed", is_flag=True, help="Show detailed sync history")
@click.pass_context
def repos_sync_status(ctx, user_alias: Optional[str], detailed: bool):
    """Show repository sync status.

    \b
    Display synchronization status for activated repositories including
    last sync time, current status, and conflict information.

    \b
    STATUS MODES:
      • All repos:  cidx repos sync-status              # Show status for all repositories
      • Individual: cidx repos sync-status my-project   # Show status for specific repository

    \b
    STATUS OPTIONS:
      • --detailed    Show comprehensive sync history and details

    \b
    EXAMPLES:
      cidx repos sync-status                    # Show status for all repositories
      cidx repos sync-status my-project        # Show status for specific repository
      cidx repos sync-status --detailed        # Show detailed status for all repositories
    """
    try:
        # Import here to avoid circular imports
        from .mode_detection.command_mode_detector import find_project_root
        from .api_clients.base_client import (
            AuthenticationError,
            NetworkError,
            APIClientError,
        )
        from rich.table import Table

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print(
                "   Run 'cidx init --remote' to set up remote mode", style="dim"
            )
            sys.exit(1)

        # Create repos client - use synchronous wrapper
        from .api_clients.repos_client import SyncReposAPIClient

        repos_client = SyncReposAPIClient(project_root)

        # Get sync status
        if user_alias:
            # Get status for specific repository
            console.print(f"🔍 Sync Status for '{user_alias}'", style="blue bold")

            status = repos_client.get_sync_status(user_alias)

            # Display repository status
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Property", style="dim")
            table.add_column("Value")

            # Basic status information
            status_style = (
                "green"
                if status["sync_status"] == "synced"
                else "yellow" if status["sync_status"] == "needs_sync" else "red"
            )
            table.add_row(
                "Status", f"[{status_style}]{status['sync_status']}[/{status_style}]"
            )
            table.add_row("Current Branch", status["current_branch"])
            table.add_row("Last Sync", status.get("last_sync_time", "Never"))
            table.add_row(
                "Has Conflicts", "Yes" if status.get("has_conflicts", False) else "No"
            )

            console.print(table)

            # Show detailed history if requested
            if detailed and "sync_history" in status:
                console.print("\n📋 Detailed Sync History", style="blue bold")

                history_table = Table(show_header=True, header_style="bold cyan")
                history_table.add_column("Timestamp")
                history_table.add_column("Status")
                history_table.add_column("Message")
                history_table.add_column("Files", justify="right")
                history_table.add_column("Duration", justify="right")

                for entry in status["sync_history"][:10]:  # Show last 10 entries
                    status_style = "green" if entry["status"] == "completed" else "red"
                    history_table.add_row(
                        entry["timestamp"],
                        f"[{status_style}]{entry['status']}[/{status_style}]",
                        entry["message"],
                        str(entry.get("files_synced", "N/A")),
                        f"{entry.get('duration', 0):.1f}s",
                    )

                console.print(history_table)
        else:
            # Get status for all repositories
            console.print("📊 Repository Sync Status", style="blue bold")

            status_data = repos_client.get_sync_status_all()

            if not status_data:
                console.print("ℹ️ No activated repositories found", style="yellow")
                return

            # Create status table
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Repository", style="bold")
            table.add_column("Status")
            table.add_column("Branch")
            table.add_column("Last Sync")
            table.add_column("Conflicts")

            for repo_alias, repo_status in status_data.items():
                status_style = (
                    "green"
                    if repo_status["sync_status"] == "synced"
                    else (
                        "yellow"
                        if repo_status["sync_status"] == "needs_sync"
                        else "red"
                    )
                )
                conflicts_indicator = (
                    "⚠️" if repo_status.get("has_conflicts", False) else "✅"
                )

                table.add_row(
                    repo_alias,
                    f"[{status_style}]{repo_status['sync_status']}[/{status_style}]",
                    repo_status["current_branch"],
                    repo_status.get("last_sync_time", "Never"),
                    conflicts_indicator,
                )

            console.print(table)

            # Show summary
            total_repos = len(status_data)
            synced_repos = sum(
                1
                for status in status_data.values()
                if status["sync_status"] == "synced"
            )
            conflict_repos = sum(
                1
                for status in status_data.values()
                if status.get("has_conflicts", False)
            )

            console.print()
            console.print(
                f"📈 Summary: {synced_repos}/{total_repos} repositories synced",
                style="cyan",
            )
            if conflict_repos > 0:
                console.print(
                    f"⚠️  {conflict_repos} repositories have conflicts requiring attention",
                    style="yellow",
                )

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
    except APIClientError as e:
        console.print(f"❌ API error: {e}", style="red")
        if e.status_code == 404:
            console.print(
                "   💡 Repository not found - check repository alias", style="dim"
            )
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Failed to get sync status: {e}", style="red")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@repos_group.command("files")
@click.argument("user_alias")
@click.option("--path", default="", help="Directory path to list")
@click.pass_context
def repos_files(ctx, user_alias: str, path: str):
    """Browse repository files and directories.

    \b
    Display files and directories in your activated repositories. Navigate
    through the file tree to explore repository content.

    \b
    EXAMPLES:
      cidx repos files my-project                    # List files in root
      cidx repos files my-project --path src         # List files in src/
      cidx repos files my-project --limit 50         # Show max 50 files
    """
    try:
        from pathlib import Path
        import asyncio
        from .mode_detection.command_mode_detector import find_project_root
        from .cli_repos_files import get_repo_id_from_alias_sync, display_file_tree
        from .remote.sync_execution import (
            _load_remote_configuration,
            _load_and_decrypt_credentials,
        )

        # Get project root and credentials
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ Not in a CIDX project directory", style="red")
            sys.exit(1)

        # Load remote configuration and credentials
        try:
            remote_config = _load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
            credentials = _load_and_decrypt_credentials(project_root)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "   Please run 'cidx init --remote' to configure authentication.",
                style="dim",
            )
            sys.exit(1)

        # Verify repository exists
        try:
            _ = get_repo_id_from_alias_sync(
                server_url, credentials, user_alias, project_root
            )
        except ValueError as e:
            console.print(f"❌ {e}", style="red")
            sys.exit(1)

        # Fetch files from API
        from .api_clients.repos_client import ReposAPIClient

        async def fetch_files():
            client = ReposAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            )
            try:
                return await client.list_repository_files(
                    repo_alias=user_alias, path=path
                )
            finally:
                await client.close()

        files = asyncio.run(fetch_files())

        # Display results
        display_file_tree(files.get("files", []), path if path else "/")

    except Exception as e:
        console.print(f"❌ Failed to list files: {e}", style="red")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@repos_group.command("cat")
@click.argument("user_alias")
@click.argument("file_path")
@click.option("--no-highlight", is_flag=True, help="Disable syntax highlighting")
@click.pass_context
def repos_cat(ctx, user_alias: str, file_path: str, no_highlight: bool):
    """View repository file contents.

    \b
    Display the contents of a file from your activated repository with
    optional syntax highlighting and line numbers.

    \b
    EXAMPLES:
      cidx repos cat my-project README.md              # View README
      cidx repos cat my-project src/main.py           # View Python file
      cidx repos cat my-project config.json --no-highlight  # Plain text
    """
    try:
        from pathlib import Path
        import asyncio
        from .mode_detection.command_mode_detector import find_project_root
        from .cli_repos_files import (
            get_repo_id_from_alias_sync,
            display_with_line_numbers,
            apply_syntax_highlighting,
            format_file_size,
        )
        from .remote.sync_execution import (
            _load_remote_configuration,
            _load_and_decrypt_credentials,
        )

        # Get project root and credentials
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ Not in a CIDX project directory", style="red")
            sys.exit(1)

        # Load remote configuration and credentials
        try:
            remote_config = _load_remote_configuration(project_root)
            server_url = remote_config["server_url"]
            credentials = _load_and_decrypt_credentials(project_root)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "   Please run 'cidx init --remote' to configure authentication.",
                style="dim",
            )
            sys.exit(1)

        # Verify repository exists
        try:
            _ = get_repo_id_from_alias_sync(
                server_url, credentials, user_alias, project_root
            )
        except ValueError as e:
            console.print(f"❌ {e}", style="red")
            sys.exit(1)

        # Fetch file content from API
        from .api_clients.repos_client import ReposAPIClient

        async def fetch_file_content():
            client = ReposAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            )
            try:
                return await client.get_file_content(
                    repo_alias=user_alias, file_path=file_path
                )
            finally:
                await client.close()

        file_data = asyncio.run(fetch_file_content())

        # Check if binary file
        if file_data.get("is_binary"):
            size = file_data.get("size", 0)
            console.print(
                f"📦 Binary file (size: {format_file_size(size)})", style="yellow"
            )
            return

        # Get content
        content = file_data.get("content", "")

        # Apply syntax highlighting unless disabled
        if not no_highlight:
            content = apply_syntax_highlighting(content, file_path)

        # Display with line numbers
        display_with_line_numbers(content)

    except Exception as e:
        console.print(f"❌ Failed to view file: {e}", style="red")
        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


class ActivationProgressDisplay:
    """Display class for repository activation progress."""

    def __init__(self):
        """Initialize progress display."""
        from rich.progress import (
            Progress,
            SpinnerColumn,
            TextColumn,
            BarColumn,
            TaskProgressColumn,
        )
        from rich.console import Console

        self.console = Console()
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        )

    def show_activation_progress(self, golden_alias: str, user_alias: str):
        """Display activation progress with real-time updates."""
        self.console.print(
            f"🚀 Activating repository '{golden_alias}' as '{user_alias}'",
            style="bold blue",
        )
        self.console.print(
            "   This may take a moment for large repositories...", style="dim"
        )

    def show_activation_complete(self, user_alias: str, next_steps: List[str]):
        """Display completion message with next steps."""
        self.console.print(
            f"✅ Repository '{user_alias}' activated successfully!", style="bold green"
        )

        if next_steps:
            self.console.print("\n💡 Next Steps:", style="bold cyan")
            for step in next_steps:
                self.console.print(f"   • {step}", style="dim")


def execute_repository_activation(
    golden_alias: str, user_alias: str, target_branch: Optional[str] = None
):
    """Execute repository activation with progress monitoring."""
    import asyncio
    from pathlib import Path
    from .mode_detection.command_mode_detector import find_project_root

    # Get project root and credentials
    project_root = find_project_root(Path.cwd())
    if not project_root:
        raise Exception("Not in a CIDX project directory")

    from .remote.sync_execution import _load_and_decrypt_credentials

    credentials = _load_and_decrypt_credentials(project_root)

    if not credentials:
        raise Exception("No remote credentials found. Use 'cidx init-remote' first.")

    # Initialize progress display
    progress_display = ActivationProgressDisplay()
    progress_display.show_activation_progress(golden_alias, user_alias)

    # Create client and execute activation

    async def do_activation():
        client = ReposAPIClient(
            server_url=credentials["server_url"],
            credentials=credentials,
            project_root=project_root,
        )
        try:
            return await client.activate_repository(
                golden_alias=golden_alias,
                user_alias=user_alias,
                target_branch=target_branch,
            )
        finally:
            await client.close()

    asyncio.run(do_activation())

    # Show completion with next steps
    next_steps = [
        'Query the repository: cidx query "your search terms"',
        "Check repository status: cidx repos list",
        f"Switch branches: cidx repos branch {user_alias} <branch-name>",
    ]

    progress_display.show_activation_complete(user_alias, next_steps)


def execute_repository_deactivation(
    user_alias: str, force: bool = False, confirmed: bool = False
):
    """Execute repository deactivation with cleanup."""
    import asyncio
    from pathlib import Path
    from .mode_detection.command_mode_detector import find_project_root

    # Get project root and credentials
    project_root = find_project_root(Path.cwd())
    if not project_root:
        raise Exception("Not in a CIDX project directory")

    from .remote.sync_execution import _load_and_decrypt_credentials

    credentials = _load_and_decrypt_credentials(project_root)

    if not credentials:
        raise Exception("No remote credentials found. Use 'cidx init-remote' first.")

    if not confirmed:
        raise Exception("Deactivation not confirmed")

    # Create client and execute deactivation
    console.print(f"🗑️  Deactivating repository '{user_alias}'...", style="yellow")

    async def do_deactivation():
        client = ReposAPIClient(
            server_url=credentials["server_url"],
            credentials=credentials,
            project_root=project_root,
        )
        try:
            return await client.deactivate_repository(
                user_alias=user_alias, force=force
            )
        finally:
            await client.close()

    result = asyncio.run(do_deactivation())

    # Show completion message
    console.print(
        f"✅ Repository '{user_alias}' deactivated successfully", style="bold green"
    )

    if "cleanup_summary" in result:
        summary = result["cleanup_summary"]
        console.print("📊 Cleanup Summary:", style="bold cyan")
        if "containers_stopped" in summary:
            console.print(
                f"   • Containers stopped: {summary['containers_stopped']}", style="dim"
            )
        if "storage_freed" in summary:
            console.print(
                f"   • Storage freed: {summary['storage_freed']}", style="dim"
            )

    if "warnings" in result:
        for warning in result["warnings"]:
            console.print(f"⚠️  {warning}", style="yellow")


async def _execute_repository_info(
    server_url: str,
    credentials: Dict[str, Any],
    project_root: Path,
    user_alias: str,
    branches: bool = False,
    health: bool = False,
    activity: bool = False,
):
    """Execute repository information retrieval with rich formatting."""

    # Create client and fetch repository information
    client = ReposAPIClient(
        server_url=server_url, credentials=credentials, project_root=project_root
    )

    try:
        repo_info = await client.get_repository_info(
            user_alias=user_alias, branches=branches, health=health, activity=activity
        )

        # Display repository information with rich formatting
        _display_repository_info(repo_info, branches, health, activity)

    except Exception as e:
        console.print(f"❌ Failed to get repository info: {e}", style="red")
        raise
    finally:
        await client.close()


async def _execute_branch_switch(
    server_url: str,
    credentials: Dict[str, Any],
    project_root: Path,
    user_alias: str,
    branch_name: str,
    create: bool = False,
):
    """Execute repository branch switching."""

    # Create client and switch branch
    client = ReposAPIClient(
        server_url=server_url, credentials=credentials, project_root=project_root
    )

    try:
        result = await client.switch_repository_branch(
            user_alias=user_alias, branch_name=branch_name, create=create
        )

        # Display switch result
        _display_branch_switch_result(result)

    except Exception as e:
        console.print(f"❌ Failed to switch branch: {e}", style="red")
        raise
    finally:
        await client.close()


def _display_repository_info(
    repo_info: Dict[str, Any], branches: bool, health: bool, activity: bool
):
    """Display repository information with rich formatting."""

    alias = repo_info.get("alias", "Unknown")
    console.print(f"\n[bold cyan]Repository Information: {alias}[/bold cyan]")
    console.print("=" * (25 + len(alias)))

    # Basic Information Section
    console.print("\n[bold]Basic Information:[/bold]")
    basic_info = [
        f"  Alias: {repo_info.get('alias', 'N/A')}",
        f"  Golden Repository: {repo_info.get('golden_repository', 'N/A')}",
        f"  Git URL: {repo_info.get('git_url', 'N/A')}",
        f"  Current Branch: {repo_info.get('current_branch', 'N/A')}",
        f"  Activated: {repo_info.get('activation_date', 'N/A')}",
    ]
    for info in basic_info:
        console.print(info)

    # Branch Information Section
    if branches and "branches" in repo_info:
        console.print("\n[bold]Branch Information:[/bold]")
        for branch in repo_info["branches"]:
            if branch.get("is_current", False):
                console.print(
                    f"  * [green]{branch['name']} (current)[/green]",
                    style="bold",
                )
            else:
                console.print(f"    {branch['name']}")

            if "last_commit" in branch:
                commit = branch["last_commit"]
                console.print(
                    f"    └── Last commit: {commit.get('message', 'N/A')} "
                    f"({commit.get('timestamp', 'N/A')})",
                    style="dim",
                )

    # Status Section
    console.print("\n[bold]Status:[/bold]")
    sync_status = repo_info.get("sync_status", "unknown")
    if sync_status == "up_to_date":
        console.print("  Sync Status: ✓ Up to date with golden repository")
    else:
        console.print(f"  Sync Status: ⚠️  {sync_status}")

    console.print(f"  Last Sync: {repo_info.get('last_sync', 'N/A')}")

    container_status = repo_info.get("container_status", "unknown")
    if container_status == "running":
        console.print("  Container Status: ✓ Running and ready for queries")
    else:
        console.print(f"  Container Status: ⚠️  {container_status}")

    index_status = repo_info.get("index_status", "unknown")
    if index_status == "complete":
        console.print("  Index Status: ✓ Fully indexed")
    else:
        console.print(f"  Index Status: ⚠️  {index_status}")

    query_ready = repo_info.get("query_ready", False)
    if query_ready:
        console.print("  Query Readiness: ✓ Ready")
    else:
        console.print("  Query Readiness: ❌ Not ready")

    # Health Information Section
    if health and "health" in repo_info:
        console.print("\n[bold]Health Information:[/bold]")
        health_info = repo_info["health"]

        console.print(
            f"  Container Status: ✓ {health_info.get('container_status', 'N/A')}"
        )

        if "services" in health_info:
            console.print("  Services:")
            for service, details in health_info["services"].items():
                status = details.get("status", "unknown")
                port = details.get("port", "N/A")
                if status == "healthy":
                    console.print(f"    {service}: ✓ Healthy (port {port})")
                else:
                    console.print(f"    {service}: ❌ {status} (port {port})")

        # Storage Information
        if "storage" in health_info:
            console.print("\n[bold]Storage Information:[/bold]")
            storage = health_info["storage"]
            console.print(f"  Disk Usage: {storage.get('disk_usage_mb', 'N/A')} MB")
            console.print(
                f"  Available Space: {storage.get('available_space_gb', 'N/A')} GB"
            )
            console.print(f"  Index Size: {storage.get('index_size_mb', 'N/A')} MB")

        # Recommendations
        if "recommendations" in health_info and health_info["recommendations"]:
            console.print("\n[bold]Recommendations:[/bold]")
            for rec in health_info["recommendations"]:
                console.print(f"  • {rec}", style="dim")

    # Activity Information Section
    if activity and "activity" in repo_info:
        console.print("\n[bold]Activity Information:[/bold]")
        activity_info = repo_info["activity"]

        if "recent_commits" in activity_info:
            console.print("  Recent Commits:")
            for commit in activity_info["recent_commits"][:5]:  # Show last 5
                console.print(
                    f"    {commit.get('commit_hash', 'N/A')[:7]}: "
                    f"{commit.get('message', 'N/A')}",
                    style="dim",
                )

        if "sync_history" in activity_info:
            console.print("  Sync History:")
            for sync in activity_info["sync_history"][:3]:  # Show last 3
                console.print(
                    f"    {sync.get('timestamp', 'N/A')}: "
                    f"{sync.get('status', 'N/A')} - {sync.get('changes', 'N/A')}",
                    style="dim",
                )

        if "query_activity" in activity_info:
            query_activity = activity_info["query_activity"]
            console.print("  Query Activity:")
            console.print(
                f"    Recent queries: {query_activity.get('recent_queries', 'N/A')}"
            )
            console.print(f"    Last query: {query_activity.get('last_query', 'N/A')}")

        if "branch_operations" in activity_info:
            console.print("  Branch Operations:")
            for op in activity_info["branch_operations"][:3]:  # Show last 3
                console.print(
                    f"    {op.get('operation', 'N/A')}: "
                    f"{op.get('from_branch', 'N/A')} → {op.get('to_branch', 'N/A')}",
                    style="dim",
                )

    console.print()  # Add spacing


def _display_branch_switch_result(result: Dict[str, Any]):
    """Display branch switch operation result."""
    status = result.get("status", "unknown")
    message = result.get("message", "Branch switch completed")

    if status == "success":
        console.print(f"✅ {message}", style="bold green")
    else:
        console.print(f"❌ {message}", style="red")

    # Show additional details
    if "previous_branch" in result:
        console.print(f"   Previous branch: {result['previous_branch']}", style="dim")

    if "new_branch" in result:
        console.print(f"   New branch: {result['new_branch']}", style="dim")

    if result.get("branch_created", False):
        console.print("   ✨ New branch created", style="green")

    if result.get("tracking_branch_created", False):
        console.print(
            f"   🔗 Created local tracking branch for {result.get('remote_origin', 'remote')}",
            style="green",
        )

    if result.get("uncommitted_changes_preserved", False):
        console.print("   💾 Uncommitted changes preserved", style="yellow")
        if "preserved_files" in result:
            console.print("   Preserved files:", style="dim")
            for file in result["preserved_files"][:5]:  # Show first 5
                console.print(f"     • {file}", style="dim")

    if result.get("container_updated", False):
        console.print("   🔄 Container configuration updated", style="blue")

    if result.get("container_restart_required", False):
        console.print(
            "   ⚠️  Container restart may be required for full functionality",
            style="yellow",
        )


# Repository formatting functions for table display
def format_repository_list(repositories):
    """Format activated repository list as a rich table.

    Args:
        repositories: List of ActivatedRepository objects

    Returns:
        str: Formatted table output
    """
    from rich.table import Table
    from rich.console import Console
    from datetime import datetime, timezone
    from io import StringIO

    # Create table
    table = Table(title="Activated Repositories", show_header=True)
    table.add_column("Alias", style="cyan")
    table.add_column("Branch", style="green")
    table.add_column("Sync Status", style="yellow")
    table.add_column("Last Sync", style="magenta")
    table.add_column("Actions", style="white")

    for repo in repositories:
        # Format sync status with icons
        if repo.sync_status == "synced":
            status = "✓ Synced"
            status_style = "green"
        elif repo.sync_status == "needs_sync":
            status = "⚠ Needs sync"
            status_style = "yellow"
        elif repo.sync_status == "conflict":
            status = "✗ Conflict"
            status_style = "red"
        else:
            status = repo.sync_status
            status_style = "white"

        # Format last sync time
        try:
            last_sync = datetime.fromisoformat(repo.last_sync.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            diff = now - last_sync

            if diff.days > 0:
                time_str = f"{diff.days}d ago"
            elif diff.seconds > 3600:
                time_str = f"{diff.seconds // 3600}h ago"
            else:
                time_str = f"{diff.seconds // 60}m ago"
        except (ValueError, TypeError, AttributeError):
            time_str = "Unknown"

        # Suggest actions
        actions = ""
        if repo.sync_status == "needs_sync":
            actions = "sync"
        elif repo.sync_status == "conflict":
            actions = "resolve"

        table.add_row(
            repo.alias,
            repo.current_branch,
            f"[{status_style}]{status}[/{status_style}]",
            time_str,
            actions,
        )

    # Capture table output
    console = Console(file=StringIO(), width=120)
    console.print(table)
    output = console.file.getvalue()
    console.file.close()
    return output


def format_available_repositories(repositories):
    """Format available repository list as a rich table.

    Args:
        repositories: List of GoldenRepository objects

    Returns:
        str: Formatted table output
    """
    from rich.table import Table
    from rich.console import Console
    from io import StringIO

    # Create table
    table = Table(title="Available Golden Repositories", show_header=True)
    table.add_column("Alias", style="cyan")
    table.add_column("Description", style="white", max_width=50)
    table.add_column("Default Branch", style="green")
    table.add_column("Branches", style="yellow")
    table.add_column("Status", style="magenta")

    for repo in repositories:
        # Format activation status
        if repo.is_activated:
            status = "✓ Already activated"
            status_style = "green"
        else:
            status = "Available"
            status_style = "yellow"

        # Format branches (show first few)
        branches = repo.indexed_branches[:3]
        if len(repo.indexed_branches) > 3:
            branches_str = (
                ", ".join(branches) + f" (+{len(repo.indexed_branches) - 3} more)"
            )
        else:
            branches_str = ", ".join(branches)

        table.add_row(
            repo.alias,
            repo.description,
            repo.default_branch,
            branches_str,
            f"[{status_style}]{status}[/{status_style}]",
        )

    # Capture table output
    console = Console(file=StringIO(), width=120)
    console.print(table)
    output = console.file.getvalue()
    console.file.close()
    return output


def format_discovery_results(discovery_result):
    """Format repository discovery results.

    Args:
        discovery_result: RepositoryDiscoveryResult object

    Returns:
        str: Formatted discovery output
    """
    from rich.table import Table
    from rich.console import Console
    from io import StringIO

    output_lines = []

    # Header
    output_lines.append("🔍 Repository Discovery Results")
    output_lines.append(f"Source: {discovery_result.source}")
    output_lines.append(f"Total discovered: {discovery_result.total_discovered}")
    output_lines.append("")

    if discovery_result.discovered_repositories:
        # Create table for discovered repositories
        table = Table(title="Discovered Repositories", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white", max_width=40)
        table.add_column("URL", style="blue", max_width=50)
        table.add_column("Status", style="yellow")

        for repo in discovery_result.discovered_repositories:
            # Format status
            if repo.is_available:
                status = "✓ Available"
                status_style = "green"
            elif repo.is_accessible:
                status = "⚠ Accessible"
                status_style = "yellow"
            else:
                status = "✗ Inaccessible"
                status_style = "red"

            table.add_row(
                repo.name,
                repo.description,
                repo.url,
                f"[{status_style}]{status}[/{status_style}]",
            )

        # Capture table output
        console = Console(file=StringIO(), width=120)
        console.print(table)
        table_output = console.file.getvalue()
        console.file.close()
        output_lines.append(table_output)

    # Access errors
    if discovery_result.access_errors:
        output_lines.append("\n⚠️ Access Errors:")
        for error in discovery_result.access_errors:
            output_lines.append(f"   • {error}")

    return "\n".join(output_lines)


def format_status_summary(summary):
    """Format repository status summary in dashboard-style layout.

    Args:
        summary: RepositoryStatusSummary object

    Returns:
        str: Formatted dashboard output
    """

    output_lines = []

    # Title
    output_lines.append("📊 Repository Status Dashboard")
    output_lines.append("")

    # Activated repositories summary
    activated = summary.activated_repositories
    output_lines.append("📦 Activated Repositories:")
    output_lines.append(f"   Total: {activated.total_count}")
    output_lines.append(f"   ✓ Synced: {activated.synced_count}")
    output_lines.append(f"   ⚠ Need sync: {activated.needs_sync_count}")
    output_lines.append(f"   ✗ Conflicts: {activated.conflict_count}")
    output_lines.append("")

    # Available repositories summary
    available = summary.available_repositories
    output_lines.append("🏛️ Available Repositories:")
    output_lines.append(f"   Total: {available.total_count}")
    output_lines.append(f"   Not activated: {available.not_activated_count}")
    output_lines.append("")

    # Recent activity
    if summary.recent_activity.recent_syncs:
        output_lines.append("🔄 Recent Activity:")
        for sync in summary.recent_activity.recent_syncs:
            status_icon = "✓" if sync["status"] == "success" else "✗"
            output_lines.append(
                f"   {status_icon} {sync['alias']} - {sync['sync_date']}"
            )
        output_lines.append("")

    # Recent activations
    if activated.recent_activations:
        output_lines.append("🆕 Recent Activations:")
        for activation in activated.recent_activations:
            output_lines.append(
                f"   • {activation['alias']} - {activation['activation_date']}"
            )
        output_lines.append("")

    # Recommendations
    if summary.recommendations:
        output_lines.append("💡 Recommendations:")
        for rec in summary.recommendations:
            output_lines.append(f"   • {rec}")

    return "\n".join(output_lines)


# Jobs command group
@cli.group()
def jobs():
    """Manage background jobs and monitor their status."""
    pass


@jobs.command("list")
@click.option(
    "--status",
    type=click.Choice(["running", "completed", "failed", "cancelled"]),
    help="Filter jobs by status",
)
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of jobs to display (default: 10)",
)
@click.pass_context
@require_mode("remote")
def list_jobs(ctx, status: Optional[str], limit: int):
    """List background jobs with their current status.

    \b
    Shows running, completed, failed, and cancelled jobs with details including:
    • Job ID and operation type
    • Current status and progress
    • Started time and completion time
    • Associated repository

    \b
    EXAMPLES:
      cidx jobs list                    # Show all recent jobs
      cidx jobs list --status running  # Show only running jobs
      cidx jobs list --limit 20        # Show up to 20 jobs
    """
    import asyncio
    from pathlib import Path
    from .api_clients.jobs_client import JobsAPIClient
    from .remote.credential_manager import load_encrypted_credentials
    from .remote.config import load_remote_configuration

    try:
        # Find project root
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Load remote configuration
        try:
            remote_config = load_remote_configuration(project_root)
        except FileNotFoundError:
            console.print("❌ No remote configuration found", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()
            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=remote_config["username"],
                repo_path=str(project_root),
                server_url=remote_config["server_url"],
            )

            # Create credentials dict for JobsAPIClient
            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
                "server_url": decrypted_creds.server_url,
            }
            server_url = decrypted_creds.server_url

        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Create jobs client and list jobs
        async def _list_jobs():
            async with JobsAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            ) as client:
                jobs_response = await client.list_jobs(
                    status=status,
                    limit=limit,
                )
                return jobs_response

        # Run async function
        jobs_response = asyncio.run(_list_jobs())

        # Display results
        _display_jobs_table(jobs_response, status)

    except Exception as e:
        console.print(f"❌ Failed to list jobs: {e}", style="red")
        sys.exit(1)


@jobs.command("cancel")
@click.argument("job_id", required=True)
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation prompt and cancel immediately",
)
@click.pass_context
@require_mode("remote")
def cancel_job(ctx, job_id: str, force: bool):
    """Cancel a background job.

    \b
    Cancels a running or queued background job. By default, prompts for
    confirmation before cancelling. Use --force to skip confirmation.

    \b
    EXAMPLES:
      cidx jobs cancel job-123-abc            # Cancel with confirmation
      cidx jobs cancel job-456-def --force    # Cancel without confirmation
    """
    import asyncio
    from pathlib import Path
    from .api_clients.jobs_client import JobsAPIClient
    from .remote.credential_manager import load_encrypted_credentials
    from .remote.config import load_remote_configuration

    try:
        # Find project root
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Load remote configuration
        try:
            remote_config = load_remote_configuration(project_root)
        except FileNotFoundError:
            console.print("❌ No remote configuration found", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()
            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=remote_config["username"],
                repo_path=str(project_root),
                server_url=remote_config["server_url"],
            )

            # Create credentials dict for JobsAPIClient
            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
                "server_url": decrypted_creds.server_url,
            }
            server_url = decrypted_creds.server_url

        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Confirmation prompt unless --force is used
        if not force:
            console.print(
                f"⚠️  You are about to cancel job: [bold]{job_id}[/bold]", style="yellow"
            )
            confirmation = (
                input("Are you sure you want to cancel this job? (y/N): ")
                .lower()
                .strip()
            )
            if confirmation not in ["y", "yes"]:
                console.print("Operation cancelled", style="yellow")
                return

        # Cancel the job
        async def _cancel_job():
            async with JobsAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            ) as client:
                result = await client.cancel_job(job_id)
                return result

        # Run async function
        result = asyncio.run(_cancel_job())

        # Display success
        console.print(f"✅ Job {job_id} cancelled successfully", style="green")
        if "message" in result:
            console.print(f"   {result['message']}", style="dim")

    except Exception as e:
        console.print(f"❌ Failed to cancel job: {e}", style="red")
        sys.exit(1)


@jobs.command("status")
@click.argument("job_id", required=True)
@click.pass_context
@require_mode("remote")
def job_status(ctx, job_id: str):
    """Show detailed status of a specific job.

    \b
    Displays comprehensive information about a background job including:
    • Job ID and operation type
    • Current status and progress percentage
    • Timestamps (created, started, completed)
    • Associated repository and user
    • Error details (if failed)

    \b
    EXAMPLES:
      cidx jobs status job-123-abc     # Show detailed job status
    """
    import asyncio
    from pathlib import Path
    from .api_clients.jobs_client import JobsAPIClient
    from .remote.credential_manager import load_encrypted_credentials
    from .remote.config import load_remote_configuration

    try:
        # Find project root
        project_root = find_project_root(Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Load remote configuration
        try:
            remote_config = load_remote_configuration(project_root)
        except FileNotFoundError:
            console.print("❌ No remote configuration found", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()
            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=remote_config["username"],
                repo_path=str(project_root),
                server_url=remote_config["server_url"],
            )

            # Create credentials dict for JobsAPIClient
            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
                "server_url": decrypted_creds.server_url,
            }
            server_url = decrypted_creds.server_url

        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            console.print(
                "Run 'cidx init --remote <server-url> --username <user> --password <pass>' first"
            )
            sys.exit(1)

        # Get job status
        async def _get_job_status():
            async with JobsAPIClient(
                server_url=server_url,
                credentials=credentials,
                project_root=project_root,
            ) as client:
                status = await client.get_job_status(job_id)
                return status

        # Run async function
        job_data = asyncio.run(_get_job_status())

        # Display detailed status
        _display_job_details(job_data)

    except Exception as e:
        console.print(f"❌ Failed to get job status: {e}", style="red")
        sys.exit(1)


def _display_job_details(job_data: dict):
    """Display detailed job information in a formatted way."""
    from rich.table import Table
    from rich.panel import Panel
    from datetime import datetime

    job_id = job_data.get("id") or job_data.get("job_id", "unknown")
    operation_type = job_data.get("operation_type", "unknown")
    status = job_data.get("status", "unknown")
    progress = job_data.get("progress", 0)

    # Create header with job ID and status
    if status == "running":
        status_emoji = "🔄"
        status_style = "blue"
    elif status == "completed":
        status_emoji = "✅"
        status_style = "green"
    elif status == "failed":
        status_emoji = "❌"
        status_style = "red"
    elif status == "cancelled":
        status_emoji = "⏹️"
        status_style = "yellow"
    else:
        status_emoji = "❓"
        status_style = "white"

    title = f"{status_emoji} Job {job_id[:12]}{'...' if len(job_id) > 12 else ''}"

    # Create details table
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Field", style="bold cyan", width=15)
    table.add_column("Value", style="white")

    # Basic info
    table.add_row("Job ID", job_id)
    table.add_row("Operation", operation_type.replace("operation_", "").title())
    table.add_row(
        "Status", f"[{status_style}]{status_emoji} {status.title()}[/{status_style}]"
    )
    table.add_row("Progress", f"{progress}%")

    # Timestamps
    for field, label in [
        ("created_at", "Created"),
        ("started_at", "Started"),
        ("completed_at", "Completed"),
        ("updated_at", "Last Update"),
    ]:
        timestamp = job_data.get(field, "")
        if timestamp:
            try:
                # Parse ISO format and display in readable format
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                table.add_row(label, formatted_time)
            except Exception:
                table.add_row(label, timestamp)

    # Additional info
    if "repository_id" in job_data:
        table.add_row("Repository", job_data["repository_id"])
    if "username" in job_data:
        table.add_row("User", job_data["username"])

    # Error details for failed jobs
    if status == "failed" and "error_details" in job_data:
        table.add_row("Error", f"[red]{job_data['error_details']}[/red]")

    # Display in panel
    panel = Panel(table, title=title, title_align="left", border_style=status_style)
    console.print(panel)


def _display_jobs_table(jobs_response: dict, status_filter: Optional[str]):
    """Display jobs in a formatted table."""
    from rich.table import Table
    from datetime import datetime
    import re

    jobs = jobs_response.get("jobs", [])
    total = jobs_response.get("total", 0)

    if not jobs:
        if status_filter:
            console.print(
                f"No jobs found with status '{status_filter}'", style="yellow"
            )
        else:
            console.print("No jobs found", style="yellow")
        return

    # Create table
    table = Table(title=f"Background Jobs ({total} total)")
    table.add_column("Job ID", style="cyan", no_wrap=True)
    table.add_column("Type", style="blue")
    table.add_column("Status", style="green")
    table.add_column("Progress", style="yellow", justify="right")
    table.add_column("Started", style="magenta")
    table.add_column("Username", style="dim")

    for job in jobs:
        # Format job ID (show first 8 characters)
        job_id = job.get("id") or job.get("job_id", "")
        job_id_short = job_id[:8]

        # Format operation type
        operation_type = job.get("operation_type", "unknown")
        operation_type = re.sub(r"operation_", "", operation_type)

        # Format status with appropriate styling
        status = job.get("status", "unknown")
        if status == "running":
            status_display = f"🔄 {status}"
        elif status == "completed":
            status_display = f"✅ {status}"
        elif status == "failed":
            status_display = f"❌ {status}"
        elif status == "cancelled":
            status_display = f"⏹️ {status}"
        else:
            status_display = f"❓ {status}"

        # Format progress
        progress = job.get("progress", 0)
        progress_display = f"{progress}%"

        # Format started time
        started_at = job.get("started_at", "")
        if started_at:
            try:
                # Parse ISO format and display relative time
                started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                now = datetime.now(started_dt.tzinfo)
                diff = now - started_dt

                if diff.days > 0:
                    time_display = f"{diff.days}d ago"
                elif diff.seconds > 3600:
                    hours = diff.seconds // 3600
                    time_display = f"{hours}h ago"
                elif diff.seconds > 60:
                    minutes = diff.seconds // 60
                    time_display = f"{minutes}m ago"
                else:
                    time_display = "just now"
            except Exception:
                time_display = started_at[:16]  # fallback
        else:
            time_display = "unknown"

        # Get username
        username = job.get("username", "unknown")

        table.add_row(
            job_id_short,
            operation_type,
            status_display,
            progress_display,
            time_display,
            username,
        )

    console.print(table)

    # Show filter info if applied
    if status_filter:
        console.print(f"\nFiltered by status: {status_filter}", style="dim")


# Administrative commands
@cli.group("admin")
@click.pass_context
@require_mode("remote")
def admin_group(ctx):
    """Administrative commands for CIDX server management.

    Provides administrative functionality including user management,
    system monitoring, and server configuration. Requires admin privileges.
    """
    pass


@admin_group.group("users")
@click.pass_context
def admin_users_group(ctx):
    """User management commands.

    Administrative commands for creating, listing, and managing
    user accounts on the CIDX server.
    """
    pass


@admin_users_group.command("create")
@click.argument("username", required=True)
@click.option(
    "--email", help="Email address for the new user (optional but recommended)"
)
@click.option(
    "--password", help="Password for the new user (will be prompted if not provided)"
)
@click.option(
    "--role",
    default="normal_user",
    type=click.Choice(["admin", "power_user", "normal_user"]),
    help="Role for the new user (default: normal_user)",
)
@click.pass_context
def admin_users_create(
    ctx, username: str, email: Optional[str], password: Optional[str], role: str
):
    """Create a new user account with specified role.

    Creates a new user account on the CIDX server with the specified
    username, role, and optionally email. Requires admin privileges.

    Examples:
        cidx admin users create johndoe --email john@example.com --role power_user
        cidx admin users create admin_user --role admin
        cidx admin users create regular_user  # Uses normal_user role by default
    """
    try:
        from .validation.user_validation import (
            validate_username,
            validate_email,
            validate_password,
            validate_role,
            UserValidationError,
        )
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
            load_encrypted_credentials,
            ProjectCredentialManager,
        )

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()

            # We need username from remote config for decryption
            username_for_creds = remote_config.get("username")
            if not username_for_creds:
                console.print(
                    "❌ No username found in remote configuration", style="red"
                )
                console.print(
                    "Run 'cidx auth login' to authenticate first", style="dim"
                )
                sys.exit(1)

            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username_for_creds,
                repo_path=str(project_root),
                server_url=server_url,
            )

            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }
        except (CredentialNotFoundError, Exception):
            console.print("❌ No credentials found", style="red")
            console.print("Run 'cidx auth login' to authenticate first", style="dim")
            sys.exit(1)

        # Validate input parameters
        try:
            username = validate_username(username)
            role = validate_role(role)

            if email:
                email = validate_email(email)

        except UserValidationError as e:
            console.print(f"❌ Validation error: {e}", style="red")
            sys.exit(1)

        # Get password if not provided
        if not password:
            password = getpass.getpass("Password for new user: ")
            if not password:
                console.print("❌ Password cannot be empty", style="red")
                sys.exit(1)

            # Confirm password
            password_confirm = getpass.getpass("Confirm password: ")
            if password != password_confirm:
                console.print("❌ Passwords do not match", style="red")
                sys.exit(1)

        # Validate password
        try:
            password = validate_password(password)
        except UserValidationError as e:
            console.print(f"❌ Password validation error: {e}", style="red")
            sys.exit(1)

        # Create admin client and create user
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url, credentials=credentials, project_root=project_root
        )

        with console.status("👤 Creating user account..."):
            user_response = run_async(
                admin_client.create_user(
                    username=username, password=password, role=role
                )
            )

        console.print(f"✅ Successfully created user: {username}", style="green")
        console.print(f"👤 Role: {role}", style="cyan")
        if email:
            console.print(f"📧 Email: {email}", style="cyan")

        # Display user details if available
        if "user" in user_response:
            user_info = user_response["user"]
            if "username" in user_info:
                console.print(f"🆔 Username: {user_info['username']}", style="dim")
            if "created_at" in user_info:
                console.print(f"📅 Created: {user_info['created_at']}", style="dim")

        # Close the client
        run_async(admin_client.close())

    except Exception as e:
        console.print(f"❌ User creation failed: {e}", style="red")

        # Provide helpful error guidance
        error_str = str(e).lower()
        if "insufficient privileges" in error_str or "admin role required" in error_str:
            console.print("💡 You need admin privileges to create users", style="dim")
        elif "authentication failed" in error_str:
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "already exists" in error_str or "conflict" in error_str:
            console.print(
                "💡 User already exists, try a different username", style="dim"
            )
        elif "validation" in error_str:
            console.print("💡 Check username format and password strength", style="dim")
        elif "connection" in error_str or "network" in error_str:
            console.print("💡 Check server connectivity and try again", style="dim")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_users_group.command("list")
@click.option(
    "--limit",
    default=10,
    type=int,
    help="Maximum number of users to display (default: 10)",
)
@click.option(
    "--offset",
    default=0,
    type=int,
    help="Number of users to skip for pagination (default: 0)",
)
@click.pass_context
def admin_users_list(ctx, limit: int, offset: int):
    """List all users in the system.

    Lists all user accounts registered on the CIDX server with their
    roles and creation information. Requires admin privileges.

    Examples:
        cidx admin users list
        cidx admin users list --limit 20
        cidx admin users list --limit 5 --offset 10
    """
    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
            load_encrypted_credentials,
            ProjectCredentialManager,
        )

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()

            # We need username from remote config for decryption
            username_for_creds = remote_config.get("username")
            if not username_for_creds:
                console.print(
                    "❌ No username found in remote configuration", style="red"
                )
                console.print(
                    "Run 'cidx auth login' to authenticate first", style="dim"
                )
                sys.exit(1)

            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username_for_creds,
                repo_path=str(project_root),
                server_url=server_url,
            )

            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }
        except (CredentialNotFoundError, Exception):
            console.print("❌ No credentials found", style="red")
            console.print("Run 'cidx auth login' to authenticate first", style="dim")
            sys.exit(1)

        # Create admin client and list users
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url, credentials=credentials, project_root=project_root
        )

        with console.status("👥 Retrieving user list..."):
            users_response = run_async(
                admin_client.list_users(limit=limit, offset=offset)
            )

        # Display users in a table
        table = Table(title="CIDX Server Users")
        table.add_column("Username", style="cyan")
        table.add_column("Role", style="green")
        table.add_column("Created", style="dim")

        users = users_response.get("users", [])

        if not users:
            console.print("ℹ️ No users found", style="yellow")
        else:
            for user in users:
                username = user.get("username", "unknown")
                role = user.get("role", "unknown")
                created_at = user.get("created_at", "unknown")

                # Format created date
                if created_at != "unknown":
                    try:
                        # Just show the date part for readability
                        created_display = created_at[:10]
                    except Exception:
                        created_display = created_at
                else:
                    created_display = "unknown"

                table.add_row(username, role, created_display)

            console.print(table)

            # Show pagination info
            total = users_response.get("total", len(users))
            if total > limit:
                showing_start = offset + 1
                showing_end = min(offset + limit, total)
                console.print(
                    f"\nShowing {showing_start}-{showing_end} of {total} users",
                    style="dim",
                )

        # Close the client
        run_async(admin_client.close())

    except Exception as e:
        console.print(f"❌ Failed to list users: {e}", style="red")

        # Provide helpful error guidance
        error_str = str(e).lower()
        if "insufficient privileges" in error_str or "admin role required" in error_str:
            console.print("💡 You need admin privileges to list users", style="dim")
        elif "authentication failed" in error_str:
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("💡 Check server connectivity and try again", style="dim")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


def _validate_username(username: str) -> bool:
    """Validate username format.

    Args:
        username: Username to validate

    Returns:
        True if valid, False otherwise
    """
    if not username or len(username.strip()) == 0:
        return False
    if len(username) < 3 or len(username) > 50:
        return False
    # Allow alphanumeric, underscore, hyphen
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        return False
    return True


@admin_users_group.command("show")
@click.argument("username", required=True)
@click.pass_context
def admin_users_show(ctx, username: str):
    """Show detailed information for a specific user.

    Displays detailed information for the specified user including
    username, role, and creation date. Requires admin privileges.

    Examples:
        cidx admin users show johndoe
        cidx admin users show admin_user
    """
    # Validate username format
    if not _validate_username(username):
        console.print("❌ Invalid username format", style="red")
        console.print(
            "💡 Username must be 3-50 characters, alphanumeric, underscore, or hyphen only",
            style="dim",
        )
        sys.exit(1)

    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
            load_encrypted_credentials,
            ProjectCredentialManager,
        )

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()
            username_for_creds = remote_config.get("username")
            if not username_for_creds:
                console.print(
                    "❌ No username found in remote configuration", style="red"
                )
                console.print(
                    "Run 'cidx auth login' to authenticate first", style="dim"
                )
                sys.exit(1)

            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username_for_creds,
                repo_path=str(project_root),
                server_url=server_url,
            )
            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }
        except (CredentialNotFoundError, Exception):
            console.print("❌ No credentials found", style="red")
            console.print("Run 'cidx auth login' to authenticate first", style="dim")
            sys.exit(1)

        # Create admin client and get user
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url, credentials=credentials, project_root=project_root
        )

        with console.status(f"👤 Retrieving user '{username}'..."):
            user_response = run_async(admin_client.get_user(username))

        # Display user details
        user = user_response.get("user", {})

        # Create a simple details display
        console.print(f"\n[bold cyan]User Details: {username}[/bold cyan]")
        console.print(f"Username: [green]{user.get('username', 'unknown')}[/green]")
        console.print(f"Role: [yellow]{user.get('role', 'unknown')}[/yellow]")

        created_at = user.get("created_at", "unknown")
        if created_at != "unknown":
            try:
                # Format the date for better readability
                created_display = created_at[:19].replace("T", " ")
            except Exception:
                created_display = created_at
        else:
            created_display = "unknown"
        console.print(f"Created: [dim]{created_display}[/dim]")

        # Close the client
        run_async(admin_client.close())

    except Exception as e:
        console.print(f"❌ Failed to show user: {e}", style="red")

        # Provide helpful error guidance
        error_str = str(e).lower()
        if "not found" in error_str:
            console.print(f"💡 User '{username}' does not exist", style="dim")
        elif (
            "insufficient privileges" in error_str or "admin role required" in error_str
        ):
            console.print(
                "💡 You need admin privileges to view user details", style="dim"
            )
        elif "authentication failed" in error_str:
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("💡 Check server connectivity and try again", style="dim")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_users_group.command("update")
@click.argument("username", required=True)
@click.option(
    "--role",
    required=True,
    type=click.Choice(["admin", "power_user", "normal_user"]),
    help="New role for the user",
)
@click.pass_context
def admin_users_update(ctx, username: str, role: str):
    """Update a user's role.

    Updates the role of an existing user. Requires admin privileges.
    Available roles: admin, power_user, normal_user.

    Examples:
        cidx admin users update johndoe --role power_user
        cidx admin users update testuser --role admin
    """
    # Validate username format
    if not _validate_username(username):
        console.print("❌ Invalid username format", style="red")
        console.print(
            "💡 Username must be 3-50 characters, alphanumeric, underscore, or hyphen only",
            style="dim",
        )
        sys.exit(1)

    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
            load_encrypted_credentials,
            ProjectCredentialManager,
        )

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()
            username_for_creds = remote_config.get("username")
            if not username_for_creds:
                console.print(
                    "❌ No username found in remote configuration", style="red"
                )
                console.print(
                    "Run 'cidx auth login' to authenticate first", style="dim"
                )
                sys.exit(1)

            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username_for_creds,
                repo_path=str(project_root),
                server_url=server_url,
            )
            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }
        except (CredentialNotFoundError, Exception):
            console.print("❌ No credentials found", style="red")
            console.print("Run 'cidx auth login' to authenticate first", style="dim")
            sys.exit(1)

        # Create admin client
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url, credentials=credentials, project_root=project_root
        )

        # Check current user role for warnings
        try:
            current_user_info = run_async(admin_client.get_user(username))
            current_role = current_user_info.get("user", {}).get("role", "unknown")

            # Warn about role downgrades for admins
            if current_role == "admin" and role != "admin":
                console.print(
                    f"⚠️  [bold yellow]WARNING:[/bold yellow] Downgrading admin '{username}' to '{role}'",
                    style="yellow",
                )
                console.print("This will remove admin privileges!", style="dim yellow")

                confirm = click.confirm("Are you sure you want to continue?")
                if not confirm:
                    run_async(admin_client.close())
                    console.print("❌ Role update cancelled", style="yellow")
                    sys.exit(0)

            # Warn about admin promotion
            elif role == "admin" and current_role != "admin":
                console.print(
                    f"⚠️  [bold yellow]INFO:[/bold yellow] Promoting '{username}' to admin role",
                    style="yellow",
                )
                console.print(
                    "This will grant full administrative privileges!",
                    style="dim yellow",
                )

        except Exception:
            # If we can't get current role, continue without warning
            pass

        with console.status(f"🔄 Updating user '{username}' role to '{role}'..."):
            run_async(admin_client.update_user(username, role))

        console.print(
            f"✅ Successfully updated user '{username}' role to '{role}'", style="green"
        )

        # Close the client
        run_async(admin_client.close())

    except Exception as e:
        console.print(f"❌ Failed to update user: {e}", style="red")

        # Provide helpful error guidance
        error_str = str(e).lower()
        if "not found" in error_str:
            console.print(f"💡 User '{username}' does not exist", style="dim")
        elif (
            "insufficient privileges" in error_str or "admin role required" in error_str
        ):
            console.print("💡 You need admin privileges to update users", style="dim")
        elif "authentication failed" in error_str:
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("💡 Check server connectivity and try again", style="dim")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_users_group.command("delete")
@click.argument("username", required=True)
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.pass_context
def admin_users_delete(ctx, username: str, force: bool):
    """Delete a user account.

    Deletes the specified user account from the server. This action
    cannot be undone. Requires admin privileges and confirmation.
    Last admin user cannot be deleted.

    Examples:
        cidx admin users delete testuser
        cidx admin users delete olduser --force
    """
    # Validate username format
    if not _validate_username(username):
        console.print("❌ Invalid username format", style="red")
        console.print(
            "💡 Username must be 3-50 characters, alphanumeric, underscore, or hyphen only",
            style="dim",
        )
        sys.exit(1)

    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
            load_encrypted_credentials,
            ProjectCredentialManager,
        )

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()
            username_for_creds = remote_config.get("username")
            if not username_for_creds:
                console.print(
                    "❌ No username found in remote configuration", style="red"
                )
                console.print(
                    "Run 'cidx auth login' to authenticate first", style="dim"
                )
                sys.exit(1)

            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username_for_creds,
                repo_path=str(project_root),
                server_url=server_url,
            )
            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }
        except (CredentialNotFoundError, Exception):
            console.print("❌ No credentials found", style="red")
            console.print("Run 'cidx auth login' to authenticate first", style="dim")
            sys.exit(1)

        # Self-deletion prevention check
        if username_for_creds == username:
            console.print(
                f"❌ Cannot delete your own account '{username}'", style="red"
            )
            console.print(
                "💡 Ask another admin to delete your account if needed", style="dim"
            )
            sys.exit(1)

        # Confirmation prompt (unless --force is used)
        if not force:
            console.print(
                f"⚠️  [bold red]WARNING:[/bold red] You are about to delete user '[yellow]{username}[/yellow]'"
            )
            console.print("This action cannot be undone!")

            # Lazy import for admin client (needed for confirmation display)
            from .api_clients.admin_client import AdminAPIClient as TempAdminAPIClient

            # Show user details before deletion for confirmation
            try:
                temp_client = TempAdminAPIClient(
                    server_url=server_url,
                    credentials=credentials,
                    project_root=project_root,
                )
                user_info = asyncio.run(temp_client.get_user(username))
                user = user_info.get("user", {})
                console.print(
                    f"User role: [yellow]{user.get('role', 'unknown')}[/yellow]"
                )
                console.print(
                    f"Created: [dim]{user.get('created_at', 'unknown')[:10]}[/dim]"
                )
                asyncio.run(temp_client.close())
            except Exception:
                # If we can't get user info, continue with deletion prompt
                pass

            confirm = click.confirm("Are you sure you want to proceed?")
            if not confirm:
                console.print("❌ User deletion cancelled", style="yellow")
                sys.exit(0)

        # Create admin client and delete user
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url, credentials=credentials, project_root=project_root
        )

        with console.status(f"🗑️  Deleting user '{username}'..."):
            run_async(admin_client.delete_user(username))

        console.print(f"✅ Successfully deleted user '{username}'", style="green")

        # Close the client
        run_async(admin_client.close())

    except Exception as e:
        console.print(f"❌ Failed to delete user: {e}", style="red")

        # Provide helpful error guidance
        error_str = str(e).lower()
        if "not found" in error_str:
            console.print(f"💡 User '{username}' does not exist", style="dim")
        elif "last admin" in error_str or "cannot delete" in error_str:
            console.print("💡 Cannot delete the last admin user", style="dim")
        elif (
            "insufficient privileges" in error_str or "admin role required" in error_str
        ):
            console.print("💡 You need admin privileges to delete users", style="dim")
        elif "authentication failed" in error_str:
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("💡 Check server connectivity and try again", style="dim")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_users_group.command("change-password")
@click.argument("username", required=True)
@click.option(
    "--password",
    help="New password for the user (will be prompted securely if not provided)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.pass_context
def admin_users_change_password(ctx, username: str, password: str, force: bool):
    """Change a user's password (admin only).

    Changes the password for the specified user account. This operation
    requires admin privileges and can change any user's password without
    knowing the old password. Use with caution.

    Examples:
        cidx admin users change-password johndoe
        cidx admin users change-password testuser --password NewPass123!
        cidx admin users change-password olduser --force
    """
    import getpass

    # Validate username format
    if not _validate_username(username):
        console.print("❌ Invalid username format", style="red")
        console.print(
            "💡 Username must be 3-50 characters, alphanumeric, underscore, or hyphen only",
            style="dim",
        )
        sys.exit(1)

    # Get password if not provided
    if not password:
        console.print(
            f"📝 Enter new password for user '{username}':", style="bold blue"
        )
        password = getpass.getpass("New password: ")

        if not password:
            console.print("❌ Password cannot be empty", style="red")
            sys.exit(1)

        # Confirm password
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            console.print("❌ Passwords do not match", style="red")
            sys.exit(1)

    # Validate password strength using existing validation
    is_valid, validation_message = _validate_password_strength(password)
    if not is_valid:
        console.print(f"❌ {validation_message}", style="red")
        from .password_policy import get_password_policy_help

        console.print("\n💡 Password Requirements:", style="dim yellow")
        console.print(get_password_policy_help(), style="dim")
        sys.exit(1)

    # Confirmation prompt (unless --force)
    if not force:
        console.print(
            f"⚠️  [bold yellow]WARNING:[/bold yellow] You are about to change the password for user '{username}'",
            style="yellow",
        )
        console.print("This action cannot be undone.", style="dim yellow")

        if not click.confirm("Do you want to continue?"):
            console.print("❌ Password change cancelled", style="yellow")
            sys.exit(0)

    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
        )

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print(
                "💡 Run 'cidx remote init' to set up remote mode", style="dim"
            )
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        if not remote_config:
            console.print("❌ No remote configuration found", style="red")
            console.print(
                "💡 Run 'cidx remote init' to set up remote access", style="dim"
            )
            sys.exit(1)

        # Load credentials
        try:
            from .remote.sync_execution import _load_and_decrypt_credentials

            credentials = _load_and_decrypt_credentials(project_root)
        except CredentialNotFoundError:
            console.print("❌ No stored credentials found", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate first", style="dim")
            sys.exit(1)

        # Create admin client
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=remote_config["server_url"],
            credentials=credentials,
            project_root=project_root,
        )

        try:
            # First verify the user exists by getting user info
            user_info = run_async(admin_client.get_user(username))
            current_role = user_info["user"]["role"]

            # Extra warning when changing admin password
            if current_role == "admin" and not force:
                console.print(
                    f"⚠️  [bold yellow]NOTICE:[/bold yellow] User '{username}' has admin role",
                    style="yellow",
                )
                console.print(
                    "Changing admin password will affect their access!",
                    style="dim yellow",
                )
                if not click.confirm("Are you sure you want to continue?"):
                    run_async(admin_client.close())
                    console.print("❌ Password change cancelled", style="yellow")
                    sys.exit(0)

            # Change the password
            run_async(admin_client.change_user_password(username, password))

            console.print(
                f"✅ Password changed successfully for user '{username}'", style="green"
            )
            console.print("💡 User should log in with the new password", style="dim")

        finally:
            run_async(admin_client.close())

    except ImportError as e:
        console.print(f"❌ Import error: {e}", style="red")
        console.print("💡 Required dependencies not available", style="dim")
        sys.exit(1)
    except Exception as e:
        error_str = str(e).lower()

        if "not found" in error_str:
            console.print(f"❌ User '{username}' not found", style="red")
            console.print(
                "💡 Use 'cidx admin users list' to see available users", style="dim"
            )
        elif (
            "insufficient privileges" in error_str or "admin role required" in error_str
        ):
            console.print("❌ Insufficient privileges for password change", style="red")
            console.print(
                "💡 You need admin privileges to change user passwords", style="dim"
            )
        elif "invalid password" in error_str or "password" in error_str:
            console.print("❌ Password validation failed", style="red")
            console.print("💡 Password must meet security requirements", style="dim")
        elif "authentication" in error_str or "unauthorized" in error_str:
            console.print("❌ Authentication failed", style="red")
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("❌ Connection error", style="red")
            console.print("💡 Check server connectivity and try again", style="dim")
        else:
            console.print(f"❌ Failed to change password: {e}", style="red")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


# =============================================================================
# Admin Jobs Commands
# =============================================================================


@admin_group.group("jobs")
@click.pass_context
def admin_jobs_group(ctx):
    """Background job management commands."""
    pass


@admin_jobs_group.command("cleanup")
@click.option(
    "--older-than", default=30, type=int, help="Delete jobs older than N days"
)
@click.option(
    "--status",
    type=click.Choice(["completed", "failed", "cancelled"]),
    help="Only cleanup jobs with this status",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be deleted without deleting"
)
@click.pass_context
def admin_jobs_cleanup(ctx, older_than: int, status: Optional[str], dry_run: bool):
    """Cleanup old jobs from the system."""
    from .mode_detection.command_mode_detector import find_project_root
    from .remote.config import load_remote_configuration
    from pathlib import Path
    import json

    project_root = find_project_root(Path.cwd())
    remote_config = load_remote_configuration(project_root)

    # Simple credential loading for now - just read the file
    creds_file = project_root / ".code-indexer" / ".credentials"
    if creds_file.exists():
        credentials = json.loads(creds_file.read_text())
    else:
        credentials = {}

    server_url = remote_config.get("server_url")
    token = credentials.get("token")

    from typing import Dict, Union

    params: Dict[str, Union[str, int]] = {"max_age_hours": older_than * 24}
    if status:
        params["status"] = status
    if dry_run:
        params["dry_run"] = "true"

    import requests
    import json

    try:
        response = requests.delete(
            f"{server_url}/api/admin/jobs/cleanup",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

        if response.status_code == 401:
            console.print("❌ Authentication failed", style="red")
            sys.exit(1)
        elif response.status_code == 403:
            console.print("❌ Admin privileges required", style="red")
            sys.exit(1)
        elif response.status_code != 200:
            console.print(f"❌ Server error (HTTP {response.status_code})", style="red")
            sys.exit(1)

        result = response.json()
        cleaned_count = result.get("cleaned_count", 0)
        console.print(f"✅ Cleaned up {cleaned_count} jobs", style="green")
    except requests.exceptions.Timeout:
        console.print("❌ Request timed out", style="red")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        console.print(f"❌ Network error: {e}", style="red")
        sys.exit(1)
    except json.JSONDecodeError:
        console.print("❌ Invalid response from server", style="red")
        sys.exit(1)


@admin_jobs_group.command("stats")
@click.option("--start", help="Start date (YYYY-MM-DD)")
@click.option("--end", help="End date (YYYY-MM-DD)")
@click.pass_context
def admin_jobs_stats(ctx, start: Optional[str], end: Optional[str]):
    """View job statistics and analytics."""
    from .mode_detection.command_mode_detector import find_project_root
    from .remote.config import load_remote_configuration
    from pathlib import Path
    import json

    project_root = find_project_root(Path.cwd())
    remote_config = load_remote_configuration(project_root)

    # Simple credential loading
    creds_file = project_root / ".code-indexer" / ".credentials"
    if creds_file.exists():
        credentials = json.loads(creds_file.read_text())
    else:
        credentials = {}

    server_url = remote_config.get("server_url")
    token = credentials.get("token")

    params = {}
    if start:
        params["start_date"] = start
    if end:
        params["end_date"] = end

    import requests

    response = requests.get(
        f"{server_url}/api/admin/jobs/stats",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )

    if response.status_code == 401:
        console.print("❌ Authentication failed", style="red")
        sys.exit(1)
    elif response.status_code == 403:
        console.print("❌ Admin privileges required", style="red")
        sys.exit(1)

    stats = response.json()
    console.print(f"Total Jobs: {stats['total_jobs']}")

    # Display status breakdown
    if stats.get("by_status"):
        for status_name, count in stats["by_status"].items():
            console.print(f"{status_name.title()}: {count}")

    # Display type breakdown
    if stats.get("by_type"):
        for job_type, count in stats["by_type"].items():
            formatted = job_type.replace("_", " ").title()
            console.print(f"{formatted}: {count}")

    # Display success rate
    if "success_rate" in stats:
        console.print(f"Success Rate: {stats['success_rate']:.1f}%")

    # Display average duration
    if "average_duration" in stats:
        console.print(f"Average Duration: {stats['average_duration']:.1f}s")


# =============================================================================
# Admin Repos Commands
# =============================================================================


@admin_group.group("repos")
@click.pass_context
def admin_repos_group(ctx):
    """Repository management commands.

    Administrative commands for adding, managing, and configuring
    golden repositories on the CIDX server.
    """
    pass


@admin_repos_group.command("add")
@click.argument("git_url")
@click.argument("alias")
@click.option(
    "--description", default=None, help="Optional description for the repository"
)
@click.option(
    "--default-branch", default="main", help="Default branch name (default: main)"
)
@click.pass_context
def admin_repos_add(
    ctx, git_url: str, alias: str, description: str, default_branch: str
):
    """Add a new golden repository from Git URL.

    Adds a new golden repository to the CIDX server from the specified
    Git URL. The repository will be cloned and indexed automatically.
    Requires admin privileges.

    Args:
        git_url: Git repository URL (https, ssh, or git protocol)
        alias: Unique alias for the repository

    Examples:
        cidx admin repos add https://github.com/example/repo.git example-repo
        cidx admin repos add git@github.com:example/repo.git example-repo --description "Example repository"
        cidx admin repos add https://github.com/example/repo.git example-repo --default-branch develop
    """
    import re

    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
            load_encrypted_credentials,
            ProjectCredentialManager,
        )

        # Basic validation
        if not git_url or not git_url.strip():
            console.print("❌ Git URL cannot be empty", style="red")
            sys.exit(1)

        if not alias or not alias.strip():
            console.print("❌ Alias cannot be empty", style="red")
            sys.exit(1)

        # Validate Git URL format
        git_url_pattern = re.compile(
            r"^(https?://|git@|git://)"
            r"([a-zA-Z0-9.-]+)"
            r"[:/]"
            r"([a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)"
            r"(\.git)?/?$"
        )

        if not git_url_pattern.match(git_url):
            console.print("❌ Invalid Git URL format", style="red")
            console.print("💡 Supported formats: https://, git@, git://", style="dim")
            sys.exit(1)

        # Validate alias format
        alias_pattern = re.compile(r"^[a-zA-Z0-9._-]+$")
        if not alias_pattern.match(alias):
            console.print("❌ Invalid alias format", style="red")
            console.print(
                "💡 Alias must contain only alphanumeric characters, dots, underscores, and hyphens",
                style="dim",
            )
            sys.exit(1)

        # Find project root
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project configuration found", style="red")
            console.print("💡 Run 'cidx init' to initialize project first", style="dim")
            sys.exit(1)

        # Load remote configuration
        remote_config = load_remote_configuration(project_root)
        server_url = remote_config["server_url"]

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()

            # We need username from remote config for decryption
            username_for_creds = remote_config.get("username")
            if not username_for_creds:
                console.print(
                    "❌ No username found in remote configuration", style="red"
                )
                console.print(
                    "💡 Use 'cidx auth login' to authenticate first", style="dim"
                )
                sys.exit(1)

            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username_for_creds,
                repo_path=str(project_root),
                server_url=server_url,
            )

            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }
        except (CredentialNotFoundError, Exception):
            console.print("❌ No credentials found", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate first", style="dim")
            sys.exit(1)

        # Create admin client
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root,
        )

        try:
            console.print(
                f"📁 Adding golden repository '{alias}' from {git_url}...", style="blue"
            )

            # Add golden repository
            result = run_async(
                admin_client.add_golden_repository(
                    git_url=git_url,
                    alias=alias,
                    description=description,
                    default_branch=default_branch,
                )
            )

            # Display success with job information
            console.print(
                "✅ Golden repository addition job submitted successfully",
                style="green",
            )
            console.print(f"📋 Job ID: {result['job_id']}", style="cyan")
            console.print(f"📝 Status: {result['status']}", style="dim")

            if "message" in result:
                console.print(f"💬 {result['message']}", style="dim")

            console.print(
                "\n💡 Use 'cidx jobs status' to monitor the addition progress",
                style="dim",
            )

        finally:
            run_async(admin_client.close())

    except ImportError as e:
        console.print(f"❌ Import error: {e}", style="red")
        console.print("💡 Required dependencies not available", style="dim")
        sys.exit(1)
    except Exception as e:
        error_str = str(e).lower()

        if "invalid request data" in error_str or "invalid" in error_str:
            console.print("❌ Invalid repository data", style="red")
            console.print(
                "💡 Check Git URL format and repository accessibility", style="dim"
            )
        elif "repository conflict" in error_str or "already exists" in error_str:
            console.print(f"❌ Repository alias '{alias}' already exists", style="red")
            console.print(
                "💡 Choose a different alias or check existing repositories",
                style="dim",
            )
        elif (
            "insufficient privileges" in error_str or "admin role required" in error_str
        ):
            console.print(
                "❌ Insufficient privileges for repository addition", style="red"
            )
            console.print(
                "💡 You need admin privileges to add golden repositories", style="dim"
            )
        elif "authentication" in error_str or "unauthorized" in error_str:
            console.print("❌ Authentication failed", style="red")
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("❌ Connection error", style="red")
            console.print("💡 Check server connectivity and try again", style="dim")
        else:
            console.print(f"❌ Failed to add golden repository: {e}", style="red")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_repos_group.command("list")
@click.pass_context
def admin_repos_list(ctx):
    """List all golden repositories.

    Displays a formatted table of all golden repositories with their
    status, last refresh information, and repository details.
    Requires admin privileges.

    Examples:
        cidx admin repos list
    """
    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
            load_encrypted_credentials,
            ProjectCredentialManager,
        )
        from rich.table import Table
        from datetime import datetime
        from dateutil import parser as dateutil_parser  # type: ignore[import-untyped]

        console = Console()

        # Find project root for configuration and credentials
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project root found", style="red")
            console.print(
                "💡 Run this command from within a project directory", style="dim"
            )
            sys.exit(1)

        # Check command mode and load configuration
        try:
            config = load_remote_configuration(project_root)
            if not config:
                console.print("❌ No remote configuration found", style="red")
                console.print(
                    "💡 Use 'cidx remote init' to configure remote access", style="dim"
                )
                sys.exit(1)

            server_url = config.get("server_url")
            if not server_url:
                console.print("❌ Server URL not found in configuration", style="red")
                sys.exit(1)

        except Exception as e:
            console.print(f"❌ Failed to load configuration: {e}", style="red")
            sys.exit(1)

        # Load and decrypt credentials
        try:
            encrypted_data = load_encrypted_credentials(project_root)
            from .remote.credential_manager import ProjectCredentialManager

            credential_manager = ProjectCredentialManager()

            # We need username from remote config for decryption
            username_for_creds = config.get("username")
            if not username_for_creds:
                console.print(
                    "❌ No username found in remote configuration", style="red"
                )
                console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
                sys.exit(1)

            decrypted_creds = credential_manager.decrypt_credentials(
                encrypted_data=encrypted_data,
                username=username_for_creds,
                repo_path=str(project_root),
                server_url=server_url,
            )

            credentials = {
                "username": decrypted_creds.username,
                "password": decrypted_creds.password,
            }
        except CredentialNotFoundError:
            console.print("❌ No credentials found", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            sys.exit(1)

        # Create admin client and list repositories with proper cleanup
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root,
        )

        try:

            async def fetch_admin_data():
                try:
                    return await admin_client.list_golden_repositories()
                finally:
                    # Ensure client is properly closed to avoid resource warnings
                    await admin_client.close()

            result = run_async(fetch_admin_data())
            repositories = result.get("golden_repositories", [])
            total = result.get("total", 0)

            if total == 0:
                console.print("📂 No golden repositories found", style="yellow")
                console.print(
                    "💡 Use 'cidx admin repos add' to add repositories", style="dim"
                )
                return

            # Create rich table
            table = Table(title=f"Golden Repositories ({total})")
            table.add_column("Alias", style="cyan", no_wrap=True)
            table.add_column("Repository URL", style="blue")
            table.add_column("Last Refresh", style="green")
            table.add_column("Status", style="white")

            for repo in repositories:
                alias = repo.get("alias", "N/A")
                repo_url = repo.get("repo_url", "N/A")
                last_refresh = repo.get("last_refresh")
                status = repo.get("status", "unknown")

                # Format last refresh time
                if last_refresh:
                    try:
                        refresh_time = dateutil_parser.parse(last_refresh)
                        now = datetime.now(refresh_time.tzinfo)
                        time_diff = now - refresh_time

                        if time_diff.days > 0:
                            refresh_str = f"{time_diff.days} days ago"
                        elif time_diff.seconds > 3600:
                            hours = time_diff.seconds // 3600
                            refresh_str = f"{hours} hours ago"
                        elif time_diff.seconds > 60:
                            minutes = time_diff.seconds // 60
                            refresh_str = f"{minutes} minutes ago"
                        else:
                            refresh_str = "Just now"
                    except Exception:
                        refresh_str = str(last_refresh)
                else:
                    refresh_str = "Never"

                # Format status with indicators
                if status.lower() == "ready":
                    status_display = "✓ Ready"
                elif status.lower() == "indexing":
                    status_display = "⚡ Indexing"
                elif status.lower() == "failed":
                    status_display = "✗ Failed"
                elif status.lower() == "stale":
                    status_display = "⚠ Stale"
                else:
                    status_display = f"? {status}"

                table.add_row(alias, repo_url, refresh_str, status_display)

            console.print(table)

        finally:
            run_async(admin_client.close())

    except Exception as e:
        error_str = str(e).lower()
        if "insufficient privileges" in error_str or "admin role required" in error_str:
            console.print(
                "❌ Insufficient privileges for repository listing", style="red"
            )
            console.print(
                "💡 You need admin privileges to list golden repositories", style="dim"
            )
        elif "authentication" in error_str or "unauthorized" in error_str:
            console.print("❌ Authentication failed", style="red")
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("❌ Connection error", style="red")
            console.print("💡 Check server connectivity and try again", style="dim")
        else:
            console.print(f"❌ Failed to list golden repositories: {e}", style="red")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_repos_group.command("show")
@click.argument("alias")
@click.pass_context
def admin_repos_show(ctx, alias: str):
    """Show detailed information for a golden repository.

    Displays comprehensive details about a specific golden repository
    including status, branch information, indexing details, and metadata.
    Requires admin privileges.

    Args:
        alias: Repository alias to show details for

    Examples:
        cidx admin repos show web-app
        cidx admin repos show api-service
    """
    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
        )
        from datetime import datetime
        from dateutil import parser as dateutil_parser  # type: ignore[import-untyped]

        console = Console()

        # Find project root for configuration and credentials
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project root found", style="red")
            console.print(
                "💡 Run this command from within a project directory", style="dim"
            )
            sys.exit(1)

        # Check command mode and load configuration
        try:
            config = load_remote_configuration(project_root)
            if not config:
                console.print("❌ No remote configuration found", style="red")
                console.print(
                    "💡 Use 'cidx remote init' to configure remote access", style="dim"
                )
                sys.exit(1)

            server_url = config.get("server_url")
            if not server_url:
                console.print("❌ Server URL not found in configuration", style="red")
                sys.exit(1)

        except Exception as e:
            console.print(f"❌ Failed to load configuration: {e}", style="red")
            sys.exit(1)

        # Load credentials
        try:
            from .remote.sync_execution import _load_and_decrypt_credentials

            credentials = _load_and_decrypt_credentials(project_root)
            if not credentials:
                console.print("❌ No credentials found", style="red")
                console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
                sys.exit(1)

        except CredentialNotFoundError:
            console.print("❌ No credentials found", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            sys.exit(1)

        # Create admin client and find repository
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root,
        )

        try:
            # List all repositories and find the specific one
            result = run_async(admin_client.list_golden_repositories())
            repositories = result.get("golden_repositories", [])

            target_repo = None
            for repo in repositories:
                if repo.get("alias") == alias:
                    target_repo = repo
                    break

            if not target_repo:
                console.print(f"❌ Repository '{alias}' not found", style="red")
                console.print(
                    "💡 Use 'cidx admin repos list' to see available repositories",
                    style="dim",
                )
                sys.exit(1)

            # Display detailed repository information
            console.print(f"\n[bold cyan]Repository Details: {alias}[/bold cyan]")
            console.print("=" * 60)

            # Basic information
            console.print(f"[bold]Alias:[/bold] {target_repo.get('alias', 'N/A')}")
            console.print(
                f"[bold]Repository URL:[/bold] {target_repo.get('repo_url', 'N/A')}"
            )
            console.print(
                f"[bold]Default Branch:[/bold] {target_repo.get('default_branch', 'N/A')}"
            )

            description = target_repo.get("description")
            if description:
                console.print(f"[bold]Description:[/bold] {description}")

            # Status information
            status = target_repo.get("status", "unknown")
            if status.lower() == "ready":
                status_display = "[green]✓ Ready[/green]"
            elif status.lower() == "indexing":
                status_display = "[yellow]⚡ Indexing[/yellow]"
            elif status.lower() == "failed":
                status_display = "[red]✗ Failed[/red]"
            elif status.lower() == "stale":
                status_display = "[yellow]⚠ Stale[/yellow]"
            else:
                status_display = f"[white]? {status}[/white]"

            console.print(f"[bold]Status:[/bold] {status_display}")

            # Timestamp information
            last_refresh = target_repo.get("last_refresh")
            if last_refresh:
                try:
                    refresh_time = dateutil_parser.parse(last_refresh)
                    console.print(
                        f"[bold]Last Refresh:[/bold] {refresh_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    )

                    now = datetime.now(refresh_time.tzinfo)
                    time_diff = now - refresh_time

                    if time_diff.days > 0:
                        refresh_str = f"{time_diff.days} days ago"
                    elif time_diff.seconds > 3600:
                        hours = time_diff.seconds // 3600
                        refresh_str = f"{hours} hours ago"
                    elif time_diff.seconds > 60:
                        minutes = time_diff.seconds // 60
                        refresh_str = f"{minutes} minutes ago"
                    else:
                        refresh_str = "Just now"

                    console.print(f"[bold]Time Since Refresh:[/bold] {refresh_str}")
                except Exception:
                    console.print(f"[bold]Last Refresh:[/bold] {last_refresh}")
            else:
                console.print("[bold]Last Refresh:[/bold] [yellow]Never[/yellow]")

            # Additional metadata if available
            created_at = target_repo.get("created_at")
            if created_at:
                try:
                    create_time = dateutil_parser.parse(created_at)
                    console.print(
                        f"[bold]Created:[/bold] {create_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                    )
                except Exception:
                    console.print(f"[bold]Created:[/bold] {created_at}")

            # Indexing statistics if available
            file_count = target_repo.get("indexed_files")
            if file_count is not None:
                console.print(f"[bold]Indexed Files:[/bold] {file_count:,}")

            branch_count = target_repo.get("indexed_branches")
            if branch_count is not None:
                console.print(f"[bold]Indexed Branches:[/bold] {branch_count}")

            # Current job information if available
            current_job = target_repo.get("current_job_id")
            if current_job:
                console.print(f"[bold]Current Job:[/bold] {current_job}")

            console.print(
                "\n💡 Use 'cidx admin repos refresh {}' to update this repository".format(
                    alias
                ),
                style="dim",
            )

        finally:
            run_async(admin_client.close())

    except Exception as e:
        error_str = str(e).lower()
        if "insufficient privileges" in error_str or "admin role required" in error_str:
            console.print(
                "❌ Insufficient privileges for repository details", style="red"
            )
            console.print(
                "💡 You need admin privileges to view repository details", style="dim"
            )
        elif "authentication" in error_str or "unauthorized" in error_str:
            console.print("❌ Authentication failed", style="red")
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("❌ Connection error", style="red")
            console.print("💡 Check server connectivity and try again", style="dim")
        else:
            console.print(f"❌ Failed to show repository details: {e}", style="red")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_repos_group.command("refresh")
@click.argument("alias")
@click.pass_context
def admin_repos_refresh(ctx, alias: str):
    """Refresh a golden repository.

    Triggers a refresh and re-indexing of the specified golden repository.
    This will pull the latest changes from the Git repository and update
    the search index. The operation runs asynchronously in the background.
    Requires admin privileges.

    Args:
        alias: Repository alias to refresh

    Examples:
        cidx admin repos refresh web-app
        cidx admin repos refresh api-service
    """
    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
        )

        console = Console()

        # Find project root for configuration and credentials
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project root found", style="red")
            console.print(
                "💡 Run this command from within a project directory", style="dim"
            )
            sys.exit(1)

        # Check command mode and load configuration
        try:
            config = load_remote_configuration(project_root)
            if not config:
                console.print("❌ No remote configuration found", style="red")
                console.print(
                    "💡 Use 'cidx remote init' to configure remote access", style="dim"
                )
                sys.exit(1)

            server_url = config.get("server_url")
            if not server_url:
                console.print("❌ Server URL not found in configuration", style="red")
                sys.exit(1)

        except Exception as e:
            console.print(f"❌ Failed to load configuration: {e}", style="red")
            sys.exit(1)

        # Load credentials
        try:
            from .remote.sync_execution import _load_and_decrypt_credentials

            credentials = _load_and_decrypt_credentials(project_root)
            if not credentials:
                console.print("❌ No credentials found", style="red")
                console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
                sys.exit(1)

        except CredentialNotFoundError:
            console.print("❌ No credentials found", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            sys.exit(1)

        # Create admin client and refresh repository
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root,
        )

        try:
            console.print(
                f"🔄 Initiating refresh for repository '{alias}'...", style="yellow"
            )

            result = run_async(admin_client.refresh_golden_repository(alias))

            # Validate response type
            if not isinstance(result, dict):
                console.print("❌ Invalid response from server", style="red")
                sys.exit(1)

            job_id = result.get("job_id")
            if not job_id:
                console.print(
                    "⚠️  Refresh completed but no job ID returned", style="yellow"
                )

            message = result.get("message", "Refresh job submitted successfully")

            console.print(f"✅ {message}", style="green")

            if job_id:
                console.print(f"📋 Job ID: {job_id}", style="cyan")
                console.print(
                    "💡 Use 'cidx jobs show {}' to track progress".format(job_id),
                    style="dim",
                )
                console.print(
                    "💡 Use 'cidx admin repos show {}' to check repository status".format(
                        alias
                    ),
                    style="dim",
                )
            else:
                console.print(
                    "💡 Use 'cidx admin repos list' to check repository status",
                    style="dim",
                )

        finally:
            run_async(admin_client.close())

    except Exception as e:
        error_str = str(e).lower()
        if "repository" in error_str and "not found" in error_str:
            console.print(f"❌ Repository '{alias}' not found", style="red")
            console.print(
                "💡 Use 'cidx admin repos list' to see available repositories",
                style="dim",
            )
        elif (
            "insufficient privileges" in error_str or "admin role required" in error_str
        ):
            console.print(
                "❌ Insufficient privileges for repository refresh", style="red"
            )
            console.print(
                "💡 You need admin privileges to refresh golden repositories",
                style="dim",
            )
        elif "authentication" in error_str or "unauthorized" in error_str:
            console.print("❌ Authentication failed", style="red")
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("❌ Connection error", style="red")
            console.print("💡 Check server connectivity and try again", style="dim")
        else:
            console.print(f"❌ Failed to refresh repository: {e}", style="red")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_repos_group.command("branches")
@click.argument("alias")
@click.option("--detailed", is_flag=True, help="Show detailed branch information")
@click.pass_context
def admin_repos_branches(ctx, alias: str, detailed: bool):
    """List branches in a golden repository.

    Displays all available branches in the specified golden repository
    with commit information and active user counts. Use --detailed flag
    for additional health and status information.
    Requires admin privileges.

    Args:
        alias: Repository alias to list branches for

    Examples:
        cidx admin repos branches web-app
        cidx admin repos branches api-service --detailed
    """
    try:
        from rich.console import Console
        from rich.table import Table
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import CredentialNotFoundError

        console = Console()

        # Find project root for configuration and credentials
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project root found", style="red")
            console.print(
                "💡 Run this command from within a project directory", style="dim"
            )
            sys.exit(1)

        # Check command mode and load configuration
        try:
            config = load_remote_configuration(project_root)
            if not config:
                console.print("❌ No remote configuration found", style="red")
                console.print(
                    "💡 Use 'cidx remote init' to configure remote access", style="dim"
                )
                sys.exit(1)

            server_url = config.get("server_url")
            if not server_url:
                console.print("❌ Server URL not found in configuration", style="red")
                sys.exit(1)

        except Exception as e:
            console.print(f"❌ Failed to load configuration: {e}", style="red")
            sys.exit(1)

        # Load credentials
        try:
            from .remote.sync_execution import _load_and_decrypt_credentials

            credentials = _load_and_decrypt_credentials(project_root)
            if not credentials:
                console.print("❌ No credentials found", style="red")
                console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
                sys.exit(1)

        except CredentialNotFoundError:
            console.print("❌ No credentials found", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            sys.exit(1)

        # Create admin client and fetch branches
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root,
        )

        try:
            result = run_async(admin_client.get_golden_repository_branches(alias))

            # Validate response type
            if not isinstance(result, dict):
                console.print("❌ Invalid response from server", style="red")
                sys.exit(1)

            branches = result.get("branches")
            if branches is None:
                console.print("❌ Server response missing branch data", style="red")
                sys.exit(1)

            # Display Rich table
            table = Table(title=f"Golden Repository Branches: {alias}")
            table.add_column("Branch", style="cyan", no_wrap=True)
            table.add_column("Commit", style="yellow", no_wrap=True)
            table.add_column("Date", style="green")
            table.add_column("Active Users", justify="right", style="magenta")

            if detailed:
                table.add_column("Health", style="blue")

            if not branches:
                console.print(
                    f"ℹ️ No branches found for repository '{alias}'", style="yellow"
                )
            else:
                for branch in branches:
                    name = branch.get("name", branch.get("branch_name", "unknown"))
                    commit_hash = branch.get("commit_hash", "N/A")
                    commit_date = branch.get(
                        "commit_date", branch.get("last_commit_date", "N/A")
                    )
                    active_users = str(branch.get("active_users", 0))

                    # Truncate commit hash to 8 characters
                    short_hash = commit_hash[:8] if commit_hash != "N/A" else "N/A"

                    row = [name, short_hash, commit_date, active_users]

                    if detailed:
                        health = branch.get("health", "unknown")
                        if health == "healthy":
                            health_display = "✅ healthy"
                        elif health == "warning":
                            health_display = "⚠️ warning"
                        elif health == "error":
                            health_display = "❌ error"
                        else:
                            health_display = "❓ unknown"
                        row.append(health_display)

                    table.add_row(*row)

                console.print(table)
                console.print(
                    f"\n{len(branches)} branch{'es' if len(branches) != 1 else ''} total\n"
                )

        finally:
            run_async(admin_client.close())

    except Exception as e:
        error_str = str(e).lower()
        if "repository" in error_str and "not found" in error_str:
            console.print(f"❌ Repository '{alias}' not found", style="red")
            console.print(
                "💡 Use 'cidx admin repos list' to see available repositories",
                style="dim",
            )
        elif (
            "insufficient privileges" in error_str or "admin role required" in error_str
        ):
            console.print(
                "❌ Insufficient privileges for viewing repository branches",
                style="red",
            )
            console.print(
                "💡 You need admin privileges to view golden repository branches",
                style="dim",
            )
        elif "authentication" in error_str or "unauthorized" in error_str:
            console.print("❌ Authentication failed", style="red")
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("❌ Connection error", style="red")
            console.print("💡 Check server connectivity and try again", style="dim")
        else:
            console.print(f"❌ Failed to fetch branches: {e}", style="red")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


@admin_repos_group.command("delete")
@click.argument("alias")
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation prompt (for automation scenarios)",
)
@click.pass_context
def admin_repos_delete(ctx, alias: str, force: bool):
    """Delete a golden repository (admin only).

    ⚠️  DESTRUCTIVE OPERATION: This will permanently delete the specified
    golden repository and all its associated data. This action cannot be undone.

    Deletes a golden repository from the CIDX server including:
    • Repository metadata and configuration
    • All indexed content and vector embeddings
    • Background job history for this repository
    • All user activations of this repository

    Requires admin privileges for execution.

    SAFETY FEATURES:
    • Confirmation prompt with repository details (unless --force used)
    • Repository existence validation before deletion
    • Warning if repository has active user instances
    • Comprehensive error handling and rollback on failures

    Args:
        alias: Repository alias to delete

    Options:
        --force: Skip confirmation prompt for automation scenarios

    Examples:
        # Delete with confirmation prompt
        cidx admin repos delete web-app

        # Force delete without prompts (for automation)
        cidx admin repos delete web-app --force

        # Show repository details before deciding
        cidx admin repos show web-app
        cidx admin repos delete web-app
    """
    try:
        from .mode_detection.command_mode_detector import find_project_root
        from .remote.config import load_remote_configuration
        from .remote.credential_manager import (
            CredentialNotFoundError,
        )

        console = Console()

        # Find project root for configuration and credentials
        project_root = find_project_root(start_path=Path.cwd())
        if not project_root:
            console.print("❌ No project root found", style="red")
            console.print(
                "💡 Run this command from within a project directory", style="dim"
            )
            sys.exit(1)

        # Check command mode and load configuration
        try:
            config = load_remote_configuration(project_root)
            if not config:
                console.print("❌ No remote configuration found", style="red")
                console.print(
                    "💡 Use 'cidx remote init' to configure remote access", style="dim"
                )
                sys.exit(1)

            server_url = config.get("server_url")
            if not server_url:
                console.print("❌ Server URL not found in configuration", style="red")
                sys.exit(1)
        except Exception as e:
            console.print(f"❌ Failed to load configuration: {e}", style="red")
            sys.exit(1)

        # Load credentials
        try:
            from .remote.sync_execution import _load_and_decrypt_credentials

            credentials = _load_and_decrypt_credentials(project_root)
            if not credentials:
                console.print("❌ No credentials found", style="red")
                console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
                sys.exit(1)
        except CredentialNotFoundError:
            console.print("❌ No credentials found", style="red")
            console.print("💡 Use 'cidx auth login' to authenticate", style="dim")
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Failed to load credentials: {e}", style="red")
            sys.exit(1)

        # Create admin client
        from .api_clients.admin_client import AdminAPIClient

        admin_client = AdminAPIClient(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root,
        )

        try:
            # If not force, show confirmation prompt
            if not force:
                # Get repository details for confirmation
                try:
                    repos_result = run_async(admin_client.list_golden_repositories())
                    repositories = repos_result.get("golden_repositories", [])
                    target_repo = None

                    for repo in repositories:
                        if repo.get("alias") == alias:
                            target_repo = repo
                            break

                    if not target_repo:
                        console.print(f"❌ Repository '{alias}' not found", style="red")
                        console.print(
                            "💡 Use 'cidx admin repos list' to see available repositories",
                            style="dim",
                        )
                        sys.exit(1)

                    # Show confirmation prompt with repository details
                    console.print(
                        f"\n⚠️  This will permanently delete the golden repository '{alias}'.",
                        style="yellow bold",
                    )
                    console.print(
                        f"📍 Repository: {target_repo.get('repo_url', 'N/A')}"
                    )
                    console.print(
                        f"📂 Description: {target_repo.get('description', 'No description')}"
                    )
                    console.print(
                        f"🌿 Default branch: {target_repo.get('default_branch', 'N/A')}"
                    )

                    status = target_repo.get("status", "Unknown")
                    if status == "ready":
                        console.print("✅ Status: Ready (indexed and available)")
                    elif status == "indexing":
                        console.print("🔄 Status: Currently indexing")
                    else:
                        console.print(f"📊 Status: {status}")

                    console.print(
                        "\n🔄 This action cannot be undone.", style="red bold"
                    )

                    # Prompt for confirmation
                    confirmation = click.confirm(
                        f"\nAre you sure you want to delete '{alias}'?", default=False
                    )

                    if not confirmation:
                        console.print("❌ Deletion cancelled", style="yellow")
                        sys.exit(0)

                except Exception:
                    # If we can't get repository details, still prompt for basic confirmation
                    console.print(
                        f"\n⚠️  This will permanently delete the golden repository '{alias}'.",
                        style="yellow bold",
                    )
                    console.print("🔄 This action cannot be undone.", style="red bold")

                    confirmation = click.confirm(
                        f"\nAre you sure you want to delete '{alias}'?", default=False
                    )

                    if not confirmation:
                        console.print("❌ Deletion cancelled", style="yellow")
                        sys.exit(0)

            # Perform deletion
            console.print(f"🗑️  Deleting golden repository '{alias}'...", style="red")
            run_async(admin_client.delete_golden_repository(alias, force=force))

            console.print(
                f"✅ Golden repository '{alias}' deleted successfully", style="green"
            )
            console.print(
                "💡 Use 'cidx admin repos list' to see remaining repositories",
                style="dim",
            )

        finally:
            run_async(admin_client.close())

    except Exception as e:
        error_str = str(e).lower()

        if "repository not found" in error_str or "not found" in error_str:
            console.print(f"❌ Repository '{alias}' not found", style="red")
            console.print(
                "💡 Use 'cidx admin repos list' to see available repositories",
                style="dim",
            )
        elif (
            "repository deletion conflict" in error_str
            or "active instances" in error_str
        ):
            console.print(
                f"❌ Cannot delete repository '{alias}' - it has active instances",
                style="red",
            )
            console.print(
                "💡 Deactivate all user instances before deleting the golden repository",
                style="dim",
            )
        elif (
            "insufficient privileges" in error_str or "admin role required" in error_str
        ):
            console.print(
                "❌ Insufficient privileges for repository deletion", style="red"
            )
            console.print(
                "💡 You need admin privileges to delete golden repositories",
                style="dim",
            )
        elif "authentication" in error_str or "unauthorized" in error_str:
            console.print("❌ Authentication failed", style="red")
            console.print(
                "💡 Check your authentication with 'cidx auth login'", style="dim"
            )
        elif "service unavailable" in error_str:
            console.print("❌ Service temporarily unavailable", style="red")
            console.print(
                "💡 Repository deletion failed due to service issues - please try again later",
                style="dim",
            )
        elif "connection" in error_str or "network" in error_str:
            console.print("❌ Connection error", style="red")
            console.print("💡 Check server connectivity and try again", style="dim")
        else:
            console.print(f"❌ Failed to delete repository: {e}", style="red")

        if ctx.obj.get("verbose"):
            import traceback

            console.print(traceback.format_exc(), style="dim red")
        sys.exit(1)


def main():
    """Main entry point."""
    try:
        cli(obj={})
    except KeyboardInterrupt:
        console.print("\n❌ Interrupted by user", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Unexpected error: {str(e)}", style="red", markup=False)
        sys.exit(1)


@cli.command("start")
@click.pass_context
@require_mode("local")
def start_command(ctx):
    """Start CIDX daemon manually.

    Only available when daemon.enabled: true in config.
    Normally daemon auto-starts on first query, but this allows
    explicit control for debugging or pre-loading.
    """
    exit_code = cli_daemon_lifecycle.start_daemon_command()
    sys.exit(exit_code)


@cli.command("stop")
@click.pass_context
@require_mode("local")
def stop_command(ctx):
    """Stop CIDX daemon gracefully.

    Gracefully shuts down daemon:
    - Stops any active watch
    - Clears cache
    - Closes connections
    - Exits daemon process
    """
    exit_code = cli_daemon_lifecycle.stop_daemon_command()
    sys.exit(exit_code)


@cli.command("watch-stop")
@click.pass_context
@require_mode("local")
def watch_stop_command(ctx):
    """Stop watch mode running in daemon.

    Only available in daemon mode. Use this to stop watch
    without stopping the entire daemon. Queries continue to work.
    """
    exit_code = cli_daemon_lifecycle.watch_stop_command()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
