"""Parallel watch process manager for multi-repository monitoring (Story 5.1).

This module manages multiple watch processes running in parallel across
different repositories, providing process lifecycle management and health
monitoring.
"""

import subprocess
from typing import Dict, List, Tuple


class ParallelWatchManager:
    """Manage multiple parallel watch processes.

    Spawns and manages watch processes for multiple repositories simultaneously,
    maintaining process handles for lifecycle management and providing health
    monitoring to detect failed processes.
    """

    def __init__(self, repositories: List[str]):
        """Initialize watch manager.

        Args:
            repositories: List of repository paths to watch
        """
        self.repositories = repositories
        self.processes: Dict[str, subprocess.Popen] = {}
        self.running = True

    def start_all_watchers(self):
        """Start watch process for each repository in parallel.

        Spawns all processes before entering monitoring loop.
        Failed processes are logged but don't prevent other repositories
        from starting.

        Raises:
            RuntimeError: If all watch processes fail to start
        """
        print(f"Starting watch mode for {len(self.repositories)} repositories...")

        # Spawn all processes
        for repo in self.repositories:
            try:
                process = self._start_watch_process(repo)
                self.processes[repo] = process
                print(f"[{repo}] Watch started - monitoring for changes")
            except Exception as e:
                print(f"[{repo}] Failed to start watch: {e}")
                # Continue with other repositories
                continue

        if not self.processes:
            raise RuntimeError("Failed to start any watch processes")

        print("\nPress Ctrl-C to stop all watchers...\n")

    def _start_watch_process(self, repo_path: str) -> subprocess.Popen:
        """Start single watch process for repository.

        Args:
            repo_path: Path to repository to watch

        Returns:
            Popen object for process management
        """
        cmd = ["cidx", "watch"]

        process = subprocess.Popen(
            cmd,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )

        return process

    def stop_all_watchers(self) -> Tuple[int, int, int]:
        """Stop all watch processes gracefully.

        Attempts to terminate processes gracefully first, then kills
        processes that don't terminate within timeout.

        Returns:
            Tuple of (terminated_count, forced_kill_count, error_count)
        """
        print("\nStopping all watch processes...")

        terminated_count = 0
        forced_kill_count = 0
        error_count = 0

        for repo, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"[{repo}] Watch terminated")
                terminated_count += 1
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"[{repo}] Watch forcefully killed")
                forced_kill_count += 1
            except Exception as e:
                print(f"[{repo}] Error stopping watch: {e}")
                error_count += 1

        self.processes.clear()
        return terminated_count, forced_kill_count, error_count

    def check_process_health(self) -> List[str]:
        """Check if all processes are still running.

        Returns:
            List of repository paths with terminated processes
        """
        dead_processes = []

        for repo, process in self.processes.items():
            if process.poll() is not None:
                # Process has terminated
                dead_processes.append(repo)

        return dead_processes
