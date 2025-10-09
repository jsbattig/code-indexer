"""Output multiplexer for unified watch process streaming (Story 5.2).

This module provides output multiplexing functionality to combine output
from multiple watch processes into a single unified stdout stream.
"""

import threading
import queue
from typing import Dict, List, Tuple
import subprocess


class OutputMultiplexer:
    """Multiplex output from multiple watch processes into single stream.

    Combines output from multiple concurrent watch processes into a single
    unified output stream, maintaining line integrity and chronological order.
    Uses threading to read from each process independently and queue output
    for unified display.
    """

    def __init__(self, processes: Dict[str, subprocess.Popen]):
        """Initialize output multiplexer.

        Args:
            processes: Dictionary mapping repository paths to Popen process objects
        """
        self.processes = processes
        self.output_queue: queue.Queue[Tuple[str, str]] = queue.Queue()
        self.reader_threads: List[threading.Thread] = []
        self.running = True

    def start_multiplexing(self):
        """Start multiplexing output from all processes.

        Creates reader thread for each process that feeds into
        central output queue for unified display.
        """
        # Start reader thread for each process
        for repo, process in self.processes.items():
            thread = threading.Thread(
                target=self._read_process_output,
                args=(repo, process),
                daemon=True
            )
            thread.start()
            self.reader_threads.append(thread)

        # Start writer thread to display multiplexed output
        writer_thread = threading.Thread(
            target=self._write_multiplexed_output,
            daemon=True
        )
        writer_thread.start()

    def _read_process_output(
        self,
        repo: str,
        process: subprocess.Popen[str]
    ) -> None:
        """Read output from single process and queue it.

        Runs in dedicated thread per repository.

        Args:
            repo: Repository identifier
            process: Process to read from
        """
        try:
            if process.stdout:
                for line in process.stdout:
                    if line and self.running:
                        # Queue line with repository identifier
                        # Strip trailing newline for consistent formatting
                        self.output_queue.put((repo, line.rstrip('\n')))
        except Exception as e:
            # Log error but don't crash thread
            self.output_queue.put((repo, f"ERROR reading output: {e}"))

    def _write_multiplexed_output(self):
        """Write multiplexed output to stdout.

        Runs in single writer thread to prevent stdout corruption.
        """
        while self.running:
            try:
                # Wait for output with timeout to allow checking running flag
                repo, line = self.output_queue.get(timeout=0.5)
                print(f"[{repo}] {line}")
            except queue.Empty:
                continue
            except Exception as e:
                print(f"ERROR in output multiplexer: {e}")

    def stop_multiplexing(self):
        """Stop multiplexing and clean up threads.

        Ensures proper shutdown sequence:
        1. Stop the running flag to terminate threads
        2. Wait for reader threads to finish
        3. Drain remaining output queue with timeout
        """
        self.running = False

        # Wait for reader threads to finish
        for thread in self.reader_threads:
            thread.join(timeout=1.0)

        # Drain remaining output queue with timeout to prevent hanging
        import time
        drain_timeout = time.time() + 2.0  # 2 second timeout for draining

        while time.time() < drain_timeout:
            try:
                repo, line = self.output_queue.get_nowait()
                print(f"[{repo}] {line}")
            except queue.Empty:
                # Queue is empty, we're done
                break
