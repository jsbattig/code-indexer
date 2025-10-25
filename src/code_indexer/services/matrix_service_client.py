"""Matrix Service Client with retry logic and in-process fallback.

Story 9: Matrix Multiplication Resident Service
Implements AC: Client with exponential backoff, 6 attempts, 5s total timeout, in-process fallback
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import requests  # type: ignore[import-untyped]

from ..storage.yaml_matrix_format import load_matrix_yaml


class MatrixServiceClient:
    """Client for matrix multiplication service with retry and fallback.

    Features:
    - Exponential backoff retry logic
    - 5-second total timeout (per story requirements)
    - In-process fallback when service unavailable
    - Console feedback when using fallback
    - Auto-start service capability
    """

    def __init__(
        self,
        service_port: Optional[int] = None,
        timeout_seconds: int = 5,
        auto_start: bool = False
    ):
        """Initialize matrix service client.

        Args:
            service_port: Service port (auto-detected if None)
            timeout_seconds: Request timeout (default: 5 seconds per story)
            auto_start: Auto-start service if not running
        """
        self.service_port = service_port or self._get_default_service_port()
        self.timeout_seconds = timeout_seconds
        self.auto_start = auto_start
        self.service_url = f"http://127.0.0.1:{self.service_port}"

    def _get_default_service_port(self) -> int:
        """Get service port from port file or allocate new port.

        Returns:
            Port number for matrix multiplication service
        """
        port_file = Path("/tmp/matrix_multiplication_service.port")

        # If service is running, read port from file
        if port_file.exists():
            try:
                return int(port_file.read_text().strip())
            except (ValueError, IOError):
                # Corrupted port file, fall through to allocation
                pass

        # Service not running, allocate port from registry
        from .global_port_registry import GlobalPortRegistry

        registry = GlobalPortRegistry()

        # Add matrix-service to port ranges if not present
        if 'matrix-service' not in registry.port_ranges:
            registry.port_ranges['matrix-service'] = (9100, 9200)

        # Get the first available port for matrix-service
        return registry.find_available_port_for_service('matrix-service')

    def multiply(
        self,
        collection_path: Path,
        vector: np.ndarray
    ) -> np.ndarray:
        """Multiply vector by projection matrix with fallback.

        Attempts to use service, falls back to in-process if unavailable.
        Auto-starts service if auto_start=True and service not running.

        Args:
            collection_path: Path to collection containing projection matrix
            vector: Vector to multiply

        Returns:
            Result of matrix multiplication as numpy array
        """
        # Auto-start service if enabled and not running
        if self.auto_start and not self.is_service_running():
            self.start_service_with_retry()

        try:
            # Try service multiplication
            payload = {
                'collection_path': str(collection_path),
                'vector': vector.tolist()
            }

            response = requests.post(
                f"{self.service_url}/multiply",
                json=payload,
                timeout=self.timeout_seconds
            )

            if response.status_code == 200:
                result = response.json()['result']
                return np.array(result)
            else:
                # Service error, fall back
                print(f"⚠️ Matrix service error (status {response.status_code}), using in-process multiplication")
                return self._multiply_in_process(collection_path, vector)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # Service unavailable or timeout, fall back
            print("⚠️ Matrix service unavailable, using in-process multiplication")
            return self._multiply_in_process(collection_path, vector)

    def multiply_with_retry(
        self,
        collection_path: Path,
        vector: np.ndarray,
        max_retries: int = 6,
        initial_delay: float = 0.1
    ) -> np.ndarray:
        """Multiply with exponential backoff retry logic.

        Args:
            collection_path: Path to collection containing projection matrix
            vector: Vector to multiply
            max_retries: Maximum retry attempts (default: 6 per story)
            initial_delay: Initial retry delay in seconds

        Returns:
            Result of matrix multiplication as numpy array
        """
        delay = initial_delay

        for attempt in range(max_retries):
            try:
                payload = {
                    'collection_path': str(collection_path),
                    'vector': vector.tolist()
                }

                response = requests.post(
                    f"{self.service_url}/multiply",
                    json=payload,
                    timeout=self.timeout_seconds
                )

                if response.status_code == 200:
                    result = response.json()['result']
                    return np.array(result)

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if attempt < max_retries - 1:
                    # Exponential backoff
                    time.sleep(delay)
                    delay *= 2
                    continue

        # All retries exhausted, fall back to in-process
        print(f"⚠️ Matrix service unavailable after {max_retries} retries, using in-process multiplication")
        return self._multiply_in_process(collection_path, vector)

    def _multiply_in_process(
        self,
        collection_path: Path,
        vector: np.ndarray
    ) -> np.ndarray:
        """Perform matrix multiplication in-process (fallback).

        Args:
            collection_path: Path to collection containing projection matrix
            vector: Vector to multiply

        Returns:
            Result of matrix multiplication

        Raises:
            FileNotFoundError: If projection matrix not found
        """
        collection_path = Path(collection_path)
        matrix_file = collection_path / "projection_matrix.yaml"

        if not matrix_file.exists():
            raise FileNotFoundError(f"Projection matrix not found: {matrix_file}")

        # Load matrix and multiply
        matrix = load_matrix_yaml(matrix_file)
        result = matrix.T @ vector

        return result

    def is_service_running(self) -> bool:
        """Check if matrix multiplication service is running.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = requests.get(
                f"{self.service_url}/health",
                timeout=2
            )
            # Explicit type conversion to bool for type checker
            return bool(response.status_code == 200 and response.json().get('status') == 'healthy')
        except requests.exceptions.RequestException:
            return False

    def start_service(self) -> bool:
        """Start matrix multiplication service in background.

        Returns:
            True if service started successfully, False otherwise
        """
        try:
            # Import here to avoid circular dependency

            # Start service in background process with allocated port
            script = f"""
import sys
sys.path.insert(0, '{Path(__file__).parent.parent.parent}')
from code_indexer.services.matrix_multiplication_service import MatrixMultiplicationService, ServiceConfig

config = ServiceConfig(port={self.service_port})
service = MatrixMultiplicationService(config)
service.start()
"""

            # Run in background
            subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            # Wait for service to start
            for _ in range(10):
                time.sleep(0.5)
                if self.is_service_running():
                    # Update service_url after port is confirmed
                    self.service_url = f"http://127.0.0.1:{self.service_port}"
                    return True

            return False

        except Exception:
            return False

    def start_service_with_retry(self, max_retries: int = 3) -> bool:
        """Start matrix multiplication service with retry logic.

        Args:
            max_retries: Maximum number of start attempts

        Returns:
            True if service started successfully, False otherwise
        """
        for attempt in range(max_retries):
            if self.start_service():
                return True

            # Wait before retry
            if attempt < max_retries - 1:
                time.sleep(1)

        return False
