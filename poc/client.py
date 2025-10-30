"""Minimal RPyC client for performance PoC.

This client connects to the daemon service with exponential backoff
and measures timing for connection and query execution.
"""

import time
from typing import Any, Dict, Optional

from rpyc.utils.factory import unix_connect


SOCKET_PATH = "/tmp/cidx-poc-daemon.sock"


class ExponentialBackoff:
    """Exponential backoff for connection retries.

    Retry delays: [100, 500, 1000, 2000] milliseconds
    """

    DELAYS_MS = [100, 500, 1000, 2000]

    def __init__(self):
        self._attempt = 0

    def next_delay_ms(self) -> int:
        """Get next delay in milliseconds.

        Returns:
            Delay in milliseconds

        Raises:
            IndexError: If all retries exhausted
        """
        if self._attempt >= len(self.DELAYS_MS):
            raise IndexError("All retries exhausted")

        delay_ms: int = self.DELAYS_MS[self._attempt]
        self._attempt += 1
        return delay_ms

    def exhausted(self) -> bool:
        """Check if all retries have been exhausted."""
        result: bool = self._attempt >= len(self.DELAYS_MS)
        return result

    def reset(self):
        """Reset backoff to start."""
        self._attempt = 0


class CIDXClient:
    """Minimal CIDX client for PoC.

    Connects to daemon with exponential backoff and measures timing.
    """

    def __init__(self, socket_path: str = SOCKET_PATH):
        self.socket_path = socket_path
        self.connection: Optional[Any] = None
        self.connection_time_ms: float = 0.0
        self.query_time_ms: float = 0.0
        self.total_time_ms: float = 0.0

    def connect(self) -> bool:
        """Connect to daemon with exponential backoff.

        Returns:
            True if connected successfully, False if all retries exhausted

        Measures connection time in self.connection_time_ms
        """
        start_time = time.perf_counter()
        backoff = ExponentialBackoff()

        while not backoff.exhausted():
            try:
                # Try to connect via Unix socket
                self.connection = unix_connect(
                    self.socket_path,
                    config={
                        "allow_public_attrs": True,
                        "allow_pickle": True,
                    },
                )

                self.connection_time_ms = (time.perf_counter() - start_time) * 1000
                return True

            except (ConnectionRefusedError, FileNotFoundError):
                # Connection failed, wait and retry
                if not backoff.exhausted():
                    delay_ms = backoff.next_delay_ms()
                    time.sleep(delay_ms / 1000.0)

        self.connection_time_ms = (time.perf_counter() - start_time) * 1000
        return False

    def query(
        self,
        query_text: str,
        search_mode: str = "semantic",
        limit: int = 10,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute query via daemon.

        Args:
            query_text: Search query text
            search_mode: One of 'semantic', 'fts', 'hybrid'
            limit: Maximum results to return
            language: Optional language filter

        Returns:
            Query results with timing information

        Raises:
            RuntimeError: If not connected to daemon
        """
        if not self.connection:
            raise RuntimeError("Not connected to daemon. Call connect() first.")

        start_time = time.perf_counter()

        # Call remote query method
        results: Dict[str, Any] = dict(
            self.connection.root.exposed_query(query_text, search_mode, limit, language)
        )

        self.query_time_ms = (time.perf_counter() - start_time) * 1000
        self.total_time_ms = self.connection_time_ms + self.query_time_ms

        return results

    def ping(self) -> str:
        """Ping daemon for RPC overhead measurement.

        Returns:
            "pong" response

        Raises:
            RuntimeError: If not connected to daemon
        """
        if not self.connection:
            raise RuntimeError("Not connected to daemon. Call connect() first.")

        response: str = str(self.connection.root.exposed_ping())
        return response

    def get_stats(self) -> Dict[str, Any]:
        """Get daemon statistics.

        Returns:
            Daemon stats dict

        Raises:
            RuntimeError: If not connected to daemon
        """
        if not self.connection:
            raise RuntimeError("Not connected to daemon. Call connect() first.")

        stats: Dict[str, Any] = dict(self.connection.root.exposed_get_stats())
        return stats

    def close(self):
        """Close connection to daemon."""
        if self.connection:
            self.connection.close()
            self.connection = None


def find_config_socket_path() -> str:
    """Find socket path by backtracking to .code-indexer/config.json.

    For PoC simplicity, just returns /tmp/cidx-poc-daemon.sock.
    Production would walk up directory tree to find config.

    Returns:
        Path to Unix socket
    """
    # TODO: Implement config backtrack logic
    return SOCKET_PATH
