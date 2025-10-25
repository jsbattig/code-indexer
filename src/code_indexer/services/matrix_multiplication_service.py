"""Matrix Multiplication Service - HTTP daemon for resident matrix operations.

Story 9: Matrix Multiplication Resident Service
Implements AC: Single global service per machine with matrix caching and auto-shutdown
"""

import os
import signal
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, List

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..storage.yaml_matrix_format import load_matrix_yaml
from .global_port_registry import GlobalPortRegistry


@dataclass
class ServiceConfig:
    """Configuration for matrix multiplication service."""

    pid_file: Path = Path("/tmp/matrix_multiplication_service.pid")
    port_file: Path = Path("/tmp/matrix_multiplication_service.port")
    ttl_seconds: int = 3600  # 60 minutes
    idle_timeout_seconds: int = 3600  # 60 minutes
    port: Optional[int] = None


class MatrixCache:
    """Matrix cache with TTL and memory management."""

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize matrix cache.

        Args:
            ttl_seconds: Time-to-live for cached matrices (default: 3600 = 60 minutes)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[np.ndarray, float]] = {}
        self._lock = threading.Lock()
        self._last_access_time = time.time()

    def store(self, collection_path: str, matrix: np.ndarray) -> None:
        """Store matrix with current timestamp.

        Args:
            collection_path: Unique identifier for collection
            matrix: Projection matrix to cache
        """
        with self._lock:
            self._cache[collection_path] = (matrix, time.time())
            self._last_access_time = time.time()

    def get(self, collection_path: str) -> Optional[np.ndarray]:
        """Retrieve matrix if not expired.

        Args:
            collection_path: Collection identifier

        Returns:
            Cached matrix or None if expired/missing
        """
        with self._lock:
            self._last_access_time = time.time()

            if collection_path not in self._cache:
                return None

            matrix, timestamp = self._cache[collection_path]

            # Check TTL
            if time.time() - timestamp > self.ttl_seconds:
                del self._cache[collection_path]
                return None

            return matrix

    def get_last_access_time(self) -> float:
        """Get timestamp of last cache access.

        Returns:
            Unix timestamp of last access
        """
        with self._lock:
            return self._last_access_time

    def clear(self) -> None:
        """Clear all cached matrices."""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        with self._lock:
            total_memory = sum(
                matrix.nbytes for matrix, _ in self._cache.values()
            )
            return {
                'total_matrices': len(self._cache),
                'total_memory_mb': total_memory / (1024 * 1024),
                'last_access_time': self._last_access_time
            }


class MultiplyRequest(BaseModel):
    """Request model for matrix multiplication."""
    collection_path: str
    vector: List[float]


class MultiplyResponse(BaseModel):
    """Response model for matrix multiplication."""
    result: List[float]


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str


class StatsResponse(BaseModel):
    """Response model for service stats."""
    uptime_seconds: float
    total_requests: int
    cache: Dict
    port: int


class MatrixMultiplicationService:
    """HTTP service for matrix multiplication with caching.

    Single global service per machine that:
    - Loads projection matrices on demand
    - Caches matrices with 60-minute TTL
    - Auto-shuts down after 60 minutes idle
    - Uses GlobalPortRegistry for port allocation
    - Manages PID file for collision detection
    """

    def __init__(self, config: ServiceConfig):
        """Initialize matrix multiplication service.

        Args:
            config: Service configuration
        """
        self.config = config
        self.cache = MatrixCache(ttl_seconds=config.ttl_seconds)
        self.start_time = time.time()
        self.total_requests = 0
        self._shutdown_event = threading.Event()

        # Allocate port from registry or find available port
        if config.port is None:
            try:
                registry = GlobalPortRegistry()
                self.port = self._allocate_port_from_registry(registry)
            except Exception:
                # Fallback for test environments where registry is not available
                self.port = self._find_available_port_without_registry()
        else:
            self.port = config.port

        # Create FastAPI app
        self.app = FastAPI(title="Matrix Multiplication Service")
        self._setup_routes()

    def _allocate_port_from_registry(self, registry: GlobalPortRegistry) -> int:
        """Allocate port for matrix service using GlobalPortRegistry.

        Uses dedicated 'matrix-service' port range via GlobalPortRegistry.

        Args:
            registry: GlobalPortRegistry instance

        Returns:
            Allocated port number

        Raises:
            RuntimeError: If no ports available
        """
        # Add matrix-service to port ranges if not present
        if 'matrix-service' not in registry.port_ranges:
            registry.port_ranges['matrix-service'] = (9100, 9200)

        try:
            return registry.find_available_port_for_service('matrix-service')
        except Exception as e:
            raise RuntimeError(f"Failed to allocate port for matrix service: {e}")

    def _find_available_port_without_registry(self) -> int:
        """Find available port without using GlobalPortRegistry (fallback for tests).

        Returns:
            Available port number in matrix-service range

        Raises:
            RuntimeError: If no ports available
        """
        import socket

        # Try ports in matrix-service range
        for port in range(9100, 9200):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(('127.0.0.1', port))
                    return port
            except OSError:
                continue

        raise RuntimeError("No available ports in matrix-service range (9100-9200)")

    def _setup_routes(self) -> None:
        """Set up FastAPI routes."""

        @self.app.get("/health", response_model=HealthResponse)
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy"}

        @self.app.post("/multiply", response_model=MultiplyResponse)
        async def multiply_vector(request: MultiplyRequest):
            """Multiply vector by projection matrix.

            Args:
                request: Contains collection_path and vector

            Returns:
                Result of matrix multiplication

            Raises:
                HTTPException: If matrix file not found or dimension mismatch
            """
            self.total_requests += 1
            collection_path = Path(request.collection_path)

            # Try cache first
            matrix = self.cache.get(str(collection_path))

            if matrix is None:
                # Load from disk
                matrix_file = collection_path / "projection_matrix.yaml"

                if not matrix_file.exists():
                    raise HTTPException(
                        status_code=404,
                        detail=f"Matrix file not found: {matrix_file}"
                    )

                try:
                    matrix = load_matrix_yaml(matrix_file)
                    self.cache.store(str(collection_path), matrix)
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to load matrix: {str(e)}"
                    )

            # Perform multiplication
            vector = np.array(request.vector)

            if vector.shape[0] != matrix.shape[0]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Dimension mismatch: vector {vector.shape[0]}, matrix {matrix.shape[0]}"
                )

            result = matrix.T @ vector
            return {"result": result.tolist()}

        @self.app.get("/stats", response_model=StatsResponse)
        async def get_stats():
            """Get service statistics."""
            uptime = time.time() - self.start_time
            cache_stats = self.cache.get_stats()

            return {
                "uptime_seconds": uptime,
                "total_requests": self.total_requests,
                "cache": cache_stats,
                "port": self.port
            }

        @self.app.post("/shutdown")
        async def shutdown():
            """Gracefully shutdown service."""
            self._shutdown_event.set()
            return {"status": "shutting down"}

    def _check_collision(self) -> None:
        """Check if another service instance is already running.

        Raises:
            RuntimeError: If service is already running
        """
        pid_file = Path(self.config.pid_file)

        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())

                # Check if process is running
                try:
                    os.kill(pid, 0)
                    raise RuntimeError(f"Matrix multiplication service already running (PID {pid})")
                except ProcessLookupError:
                    # Stale PID file, remove it
                    pid_file.unlink()
            except (ValueError, IOError):
                # Corrupted PID file, remove it
                pid_file.unlink()

    def _write_pid_file(self) -> None:
        """Write current process PID to file."""
        pid_file = Path(self.config.pid_file)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

    def _cleanup_pid_file(self) -> None:
        """Remove PID file on shutdown."""
        pid_file = Path(self.config.pid_file)
        if pid_file.exists():
            pid_file.unlink()

    def _write_port_file(self) -> None:
        """Write service port to file for client discovery."""
        port_file = Path(self.config.port_file)
        port_file.parent.mkdir(parents=True, exist_ok=True)
        port_file.write_text(str(self.port))

    def _cleanup_port_file(self) -> None:
        """Remove port file on shutdown."""
        port_file = Path(self.config.port_file)
        if port_file.exists():
            port_file.unlink()

    def _idle_timeout_monitor(self) -> None:
        """Monitor for idle timeout and shutdown if exceeded."""
        while not self._shutdown_event.is_set():
            time.sleep(10)  # Check every 10 seconds

            last_access = self.cache.get_last_access_time()
            idle_time = time.time() - last_access

            if idle_time > self.config.idle_timeout_seconds:
                print(f"Idle timeout exceeded ({idle_time:.1f}s), shutting down")
                self._shutdown_event.set()
                break

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown.

        Signal handlers can only be set in the main thread.
        Silently skip if called from a background thread (e.g., in tests).
        """
        try:
            def signal_handler(signum: int, frame: Any) -> None:
                """Handle SIGTERM and SIGINT for graceful shutdown."""
                print(f"Received signal {signum}, shutting down gracefully...")
                self._shutdown_event.set()

            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except ValueError:
            # Signal handlers can only be set in main thread
            # This is expected in test environments where service runs in background thread
            pass

    def start(self) -> None:
        """Start the matrix multiplication service.

        Raises:
            RuntimeError: If service is already running
        """
        # Check for collision
        self._check_collision()

        # Write PID file
        self._write_pid_file()

        # Write port file for client discovery
        self._write_port_file()

        # Set up signal handlers
        self._setup_signal_handlers()

        # Start idle timeout monitor in background
        monitor_thread = threading.Thread(target=self._idle_timeout_monitor, daemon=True)
        monitor_thread.start()

        try:
            # Run uvicorn server
            config = uvicorn.Config(
                self.app,
                host="127.0.0.1",
                port=self.port,
                log_level="error",
                access_log=False
            )
            server = uvicorn.Server(config)

            # Run in thread to allow shutdown monitoring
            server_thread = threading.Thread(target=server.run, daemon=False)
            server_thread.start()

            # Wait for shutdown event
            while not self._shutdown_event.is_set():
                time.sleep(0.5)

            # Trigger server shutdown
            server.should_exit = True
            server_thread.join(timeout=5)

        finally:
            self._cleanup_pid_file()
            self._cleanup_port_file()
