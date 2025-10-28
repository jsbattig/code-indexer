"""CLI integration for proxy mode command execution.

This module provides helper functions for integrating command execution
(both parallel and sequential) into the CLI for proxy mode.
"""

import signal
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from .config_manager import ProxyConfigManager
from .parallel_executor import ParallelCommandExecutor
from .sequential_executor import SequentialCommandExecutor
from .result_aggregator import ParallelResultAggregator
from .query_aggregator import QueryResultAggregator
from .rich_format_aggregator import RichFormatAggregator
from .command_config import is_parallel_command
from .command_validator import validate_proxy_command, UnsupportedProxyCommandError
from .watch_manager import ParallelWatchManager
from .output_multiplexer import OutputMultiplexer


console = Console()


def execute_proxy_command(project_root: Path, command: str, args: List[str]) -> int:
    """Execute command in proxy mode (parallel or sequential).

    This function handles execution of commands in proxy mode by:
    1. Validating command is supported in proxy mode (Story 2.4)
    2. Loading discovered repositories from proxy config
    3. Determining if command should execute in parallel or sequential
    4. Executing command across all repositories
    5. Aggregating and displaying results

    Args:
        project_root: Path to proxy configuration root
        command: CIDX command to execute (e.g., 'query', 'status', 'start')
        args: Command arguments

    Returns:
        Exit code: 0 (all success), 1 (all failed), 2 (partial success), 3 (invalid command)
    """
    # Validate command is supported in proxy mode (Story 2.4)
    try:
        validate_proxy_command(command)
    except UnsupportedProxyCommandError as e:
        console.print(e.message, style="red")
        return 3  # Exit code 3: Invalid command/configuration

    # Load proxy configuration
    try:
        proxy_config_manager = ProxyConfigManager(project_root)
        config = proxy_config_manager.load_config()
        discovered_repos = config.discovered_repos
    except Exception as e:
        console.print(f"❌ Failed to load proxy configuration: {e}", style="red")
        return 1

    # Verify we have repositories
    if not discovered_repos:
        console.print(
            "⚠️  No repositories discovered in proxy configuration", style="yellow"
        )
        console.print("Run 'cidx repos refresh' to rediscover repositories")
        return 1

    # Convert relative paths to absolute paths
    repo_paths = [str(project_root / repo) for repo in discovered_repos]

    # Special handling for watch command (Stories 5.1, 5.2, 5.4)
    if command == "watch":
        return _execute_watch(args, repo_paths, project_root)

    # Determine if command should execute in parallel
    if is_parallel_command(command):
        console.print(
            f"🔄 Executing '{command}' in parallel across {len(repo_paths)} repositories...",
            style="blue",
        )
        return _execute_parallel(command, args, repo_paths)
    else:
        # Sequential execution for non-parallel commands (Story 2.3)
        console.print(
            f"⏭️  Executing '{command}' sequentially across {len(repo_paths)} repositories...",
            style="blue",
        )
        return _execute_sequential(command, args, repo_paths)


def _execute_parallel(command: str, args: List[str], repo_paths: List[str]) -> int:
    """Execute command in parallel across repositories.

    Args:
        command: CIDX command to execute
        args: Command arguments
        repo_paths: List of absolute repository paths

    Returns:
        Exit code: 0 (all success), 1 (all failed), 2 (partial success)
    """
    # Special handling for query command (Stories 3.1-3.4)
    if command == "query":
        return _execute_query(args, repo_paths)

    # Execute in parallel
    executor = ParallelCommandExecutor(repo_paths)
    results = executor.execute_parallel(command, args)

    # Aggregate results
    aggregator = ParallelResultAggregator()
    output, exit_code = aggregator.aggregate(results)

    # Display aggregated output
    if output:
        console.print(output)

    # Display summary
    success_count = sum(1 for _, (_, _, code) in results.items() if code == 0)
    fail_count = len(results) - success_count

    if exit_code == 0:
        console.print(
            f"\n✅ Command completed successfully across all {len(repo_paths)} repositories",
            style="green",
        )
    elif exit_code == 2:
        console.print(
            f"\n⚠️  Command completed with mixed results: {success_count} succeeded, {fail_count} failed",
            style="yellow",
        )
    else:
        console.print(
            f"\n❌ Command failed across all {len(repo_paths)} repositories",
            style="red",
        )

    return exit_code


def _execute_query(args: List[str], repo_paths: List[str]) -> int:
    """Execute query command with result aggregation (Stories 3.1-3.4).

    This function handles query commands specially by:
    1. Respecting user's --quiet preference (don't force --quiet)
    2. Executing queries in parallel across all repositories
    3. Aggregating and sorting results by score
    4. Applying global limit to final merged results
    5. Preserving repository context and metadata in output

    Args:
        args: Query command arguments (may include --limit, --language, --quiet, etc.)
        repo_paths: List of absolute repository paths

    Returns:
        Exit code: 0 (success with results), 1 (all failed), 2 (partial success)
    """
    # Extract limit parameter from args (Story 3.3)
    limit = _extract_limit_from_args(args)

    # Check if user explicitly requested quiet mode
    use_quiet_mode = "--quiet" in args or "-q" in args

    # Execute query in parallel across all repositories (use args as-is)
    query_args = args.copy()
    executor = ParallelCommandExecutor(repo_paths)
    results = executor.execute_parallel("query", query_args)

    # Convert results dict to format expected by aggregators
    # Results format: Dict[repo_path, (stdout, stderr, exit_code)]
    # We need: Dict[repo_path, stdout]
    repository_outputs = {}
    for repo_path, (stdout, stderr, exit_code) in results.items():
        if exit_code == 0:
            repository_outputs[repo_path] = stdout

    # Create mapping of absolute paths to repository names
    # Extract repo names from absolute paths relative to project_root
    repo_name_map = {}
    for repo_path in repository_outputs.keys():
        # repo_path is absolute like "/tmp/proxy-manual-test/repo1"
        # We need just "repo1"
        repo_name = Path(repo_path).name
        repo_name_map[repo_path] = repo_name

    # Choose aggregator based on quiet mode and aggregate results
    if use_quiet_mode:
        # Use quiet aggregator (simple format, no metadata)
        quiet_aggregator = QueryResultAggregator()
        aggregated_output = quiet_aggregator.aggregate_results(
            repository_outputs, limit=limit, repo_name_map=repo_name_map
        )
    else:
        # Use rich format aggregator (full metadata preservation)
        rich_aggregator = RichFormatAggregator()
        aggregated_output = rich_aggregator.aggregate_results(
            repository_outputs, limit=limit, repo_name_map=repo_name_map
        )

    # Display aggregated output
    if aggregated_output:
        console.print(aggregated_output, end="")
    else:
        console.print("No results found across all repositories", style="yellow")

    # Calculate exit code based on success/failure
    success_count = sum(1 for _, (_, _, code) in results.items() if code == 0)
    if success_count == len(results):
        return 0  # All success
    elif success_count == 0:
        return 1  # All failed
    else:
        return 2  # Partial success


def _extract_limit_from_args(args: List[str]) -> Optional[int]:
    """Extract --limit parameter from query arguments.

    Args:
        args: Command arguments that may contain --limit N

    Returns:
        Limit value if found, otherwise 10 (default)
    """
    try:
        if "--limit" in args:
            limit_index = args.index("--limit")
            if limit_index + 1 < len(args):
                return int(args[limit_index + 1])
        elif "-l" in args:
            limit_index = args.index("-l")
            if limit_index + 1 < len(args):
                return int(args[limit_index + 1])
    except (ValueError, IndexError):
        pass

    # Default limit
    return 10


def _execute_sequential(command: str, args: List[str], repo_paths: List[str]) -> int:
    """Execute command sequentially across repositories (Story 2.3).

    Sequential execution is used for container lifecycle commands (start, stop, uninstall)
    to prevent resource contention, port conflicts, and race conditions.

    Args:
        command: CIDX command to execute (start/stop/uninstall)
        args: Command arguments
        repo_paths: List of absolute repository paths

    Returns:
        Exit code: 0 (all success), 1 (all failed), 2 (partial success)
    """
    # Execute sequentially
    executor = SequentialCommandExecutor(repo_paths)
    result = executor.execute_sequential(command, args)

    # Determine exit code based on results
    if result.is_complete_success():
        exit_code = 0
    elif result.success_count == 0:
        exit_code = 1  # All failed
    else:
        exit_code = 2  # Partial success

    return exit_code


def _execute_watch(args: List[str], repo_paths: List[str], project_root: Path) -> int:
    """Execute watch command with multiplexed output (Stories 5.1, 5.2, 5.3, 5.4).

    This function implements parallel watch process management with:
    1. Parallel watch processes for all repositories (Story 5.1)
    2. Unified output stream multiplexing (Story 5.2)
    3. Clean process termination via Ctrl-C (Story 5.3)
    4. Repository identification in output (Story 5.4)

    Args:
        args: Watch command arguments (debounce, batch-size, etc.)
        repo_paths: List of absolute repository paths
        project_root: Proxy root directory

    Returns:
        Exit code: 0 (clean shutdown), 1 (forced kill), 2 (partial shutdown)
    """
    watch_manager = None
    multiplexer = None
    terminating = [False]  # Use list to allow modification in nested function

    def signal_handler(signum, frame):
        """Handle Ctrl-C signal for clean shutdown (Story 5.3)."""
        if terminating[0]:
            # Second Ctrl-C - force exit
            console.print("\n\nForce terminating...", style="red bold")
            sys.exit(1)

        terminating[0] = True
        # The actual shutdown will happen in the finally block
        # Just set the flag here to break the main loop

    try:
        # Register signal handler for Ctrl-C (Story 5.3)
        original_handler = signal.signal(signal.SIGINT, signal_handler)

        # Create watch manager for parallel process management (Story 5.1)
        watch_manager = ParallelWatchManager(repo_paths)

        # Start all watch processes
        watch_manager.start_all_watchers()

        # Create output multiplexer for unified streaming (Story 5.2)
        multiplexer = OutputMultiplexer(watch_manager.processes)

        # Start multiplexing output
        multiplexer.start_multiplexing()

        # Run until interrupted
        try:
            import time

            while not terminating[0]:
                # Check process health
                dead_processes = watch_manager.check_process_health()
                if dead_processes:
                    console.print(
                        f"\n⚠️  Watch processes terminated in {len(dead_processes)} repositories",
                        style="yellow",
                    )
                    for repo in dead_processes:
                        console.print(f"  • {repo}", style="yellow")

                time.sleep(1)
        except KeyboardInterrupt:
            # User pressed Ctrl-C
            terminating[0] = True

        # Restore original signal handler
        signal.signal(signal.SIGINT, original_handler)

        # If we got here via Ctrl-C, perform graceful shutdown
        if terminating[0]:
            return _perform_graceful_shutdown(
                watch_manager, multiplexer, len(repo_paths)
            )

        return 0

    except RuntimeError as e:
        console.print(f"❌ {e}", style="red")
        return 1
    except Exception as e:
        console.print(f"❌ Unexpected error in watch mode: {e}", style="red")
        return 1
    finally:
        # Ensure cleanup happens even if there's an exception
        if watch_manager and multiplexer and terminating[0]:
            _perform_graceful_shutdown(watch_manager, multiplexer, len(repo_paths))


def _perform_graceful_shutdown(
    watch_manager: ParallelWatchManager,
    multiplexer: OutputMultiplexer,
    total_repos: int,
) -> int:
    """Perform graceful shutdown sequence (Story 5.3).

    Steps:
    1. Stop output multiplexing
    2. Terminate all watch processes
    3. Drain remaining output queue
    4. Report final status
    5. Determine exit code

    Args:
        watch_manager: Watch manager with running processes
        multiplexer: Output multiplexer
        total_repos: Total number of repositories

    Returns:
        Exit code: 0 (clean), 1 (forced kills), 2 (partial shutdown)
    """
    console.print("\n\nStopping watch mode...", style="blue")

    # Stop multiplexing first
    multiplexer.stop_multiplexing()

    # Terminate all watch processes and get metrics
    terminated_count, forced_kill_count, error_count = watch_manager.stop_all_watchers()

    # Display final shutdown status
    all_stopped = (terminated_count + forced_kill_count + error_count) == total_repos

    if all_stopped and forced_kill_count == 0 and error_count == 0:
        console.print("\n✓ All watchers stopped successfully", style="green")
        return 0  # Clean shutdown
    elif all_stopped and forced_kill_count > 0:
        console.print(
            f"\n⚠️  All watchers stopped ({forced_kill_count} forcefully killed)",
            style="yellow",
        )
        return 1  # Forced kill required
    else:
        console.print(
            f"\n⚠️  Partial shutdown: {terminated_count + forced_kill_count}/{total_repos} stopped",
            style="yellow",
        )
        return 2  # Partial shutdown
