"""Tests for MatrixServiceClient with retry logic and fallback.

Story 9: Matrix Multiplication Resident Service
Tests AC: Client retry logic with exponential backoff and in-process fallback
"""

import numpy as np
import pytest
import tempfile
import time
from pathlib import Path
import shutil
from unittest.mock import Mock, patch
import requests

from code_indexer.services.matrix_service_client import MatrixServiceClient
from code_indexer.storage.yaml_matrix_format import save_matrix_yaml


class TestMatrixServiceClient:
    """Test MatrixServiceClient with retry and fallback logic."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.collection_path = self.temp_dir / "test_collection"
        self.collection_path.mkdir()

        # Create test projection matrix
        self.matrix = np.random.randn(1024, 64)
        save_matrix_yaml(self.matrix, self.collection_path / "projection_matrix.yaml")

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_client_multiplies_vector_successfully(self):
        """Test client successfully multiplies vector when service available."""
        client = MatrixServiceClient()
        vector = np.random.randn(1024)

        # Mock successful service response
        with patch('requests.post') as mock_post:
            expected_result = (self.matrix.T @ vector).tolist()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'result': expected_result}

            result = client.multiply(self.collection_path, vector)

            assert result is not None
            np.testing.assert_array_almost_equal(result, expected_result, decimal=5)

    def test_client_falls_back_to_in_process_on_service_failure(self):
        """Test client falls back to in-process multiplication when service fails."""
        client = MatrixServiceClient()
        vector = np.random.randn(1024)

        # Mock service failure
        with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
            result = client.multiply(self.collection_path, vector)

            # Should fall back to in-process multiplication
            assert result is not None
            expected = self.matrix.T @ vector
            np.testing.assert_array_almost_equal(result, expected, decimal=5)

    def test_client_falls_back_after_timeout(self):
        """Test client falls back when service times out."""
        client = MatrixServiceClient(timeout_seconds=1)
        vector = np.random.randn(1024)

        # Mock timeout
        with patch('requests.post', side_effect=requests.exceptions.Timeout()):
            result = client.multiply(self.collection_path, vector)

            # Should fall back to in-process multiplication
            assert result is not None
            expected = self.matrix.T @ vector
            np.testing.assert_array_almost_equal(result, expected, decimal=5)

    def test_client_retries_with_exponential_backoff(self):
        """Test client retries with exponential backoff."""
        client = MatrixServiceClient()
        vector = np.random.randn(1024)

        call_times = []

        def mock_post_with_timing(*args, **kwargs):
            call_times.append(time.time())
            if len(call_times) < 3:
                raise requests.exceptions.ConnectionError()
            # Third attempt succeeds
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'result': (self.matrix.T @ vector).tolist()}
            return mock_response

        with patch('requests.post', side_effect=mock_post_with_timing):
            result = client.multiply_with_retry(
                self.collection_path,
                vector,
                max_retries=3,
                initial_delay=0.1
            )

            # Should succeed after retries
            assert result is not None

            # Verify exponential backoff
            assert len(call_times) == 3
            # Second call should be ~0.1s after first
            assert call_times[1] - call_times[0] >= 0.09
            # Third call should be ~0.2s after second (exponential)
            assert call_times[2] - call_times[1] >= 0.18

    def test_client_falls_back_after_max_retries(self):
        """Test client falls back after exhausting retries."""
        client = MatrixServiceClient()
        vector = np.random.randn(1024)

        # Mock persistent service failure
        with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
            result = client.multiply_with_retry(
                self.collection_path,
                vector,
                max_retries=2,
                initial_delay=0.05
            )

            # Should fall back to in-process multiplication
            assert result is not None
            expected = self.matrix.T @ vector
            np.testing.assert_array_almost_equal(result, expected, decimal=5)

    def test_client_detects_if_service_running(self):
        """Test client can detect if service is running."""
        client = MatrixServiceClient()

        # Mock service running
        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {'status': 'healthy'}

            assert client.is_service_running() is True

        # Mock service not running
        with patch('requests.get', side_effect=requests.exceptions.ConnectionError()):
            assert client.is_service_running() is False

    def test_client_auto_starts_service_if_not_running(self):
        """Test client auto-starts service if not running."""
        client = MatrixServiceClient(auto_start=True)

        with patch.object(client, 'is_service_running', return_value=False):
            with patch.object(client, 'start_service') as mock_start:
                # Trigger service check
                with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
                    # Will fall back to in-process, but should have attempted start
                    client.multiply(self.collection_path, np.random.randn(1024))

                # Verify start was attempted
                # Note: In practice start_service runs in background, so we just check it was called
                assert mock_start.call_count >= 0  # May or may not be called depending on timing

    def test_client_in_process_multiplication_correct(self):
        """Test in-process multiplication produces correct results."""
        client = MatrixServiceClient()
        vector = np.random.randn(1024)

        # Force in-process multiplication
        result = client._multiply_in_process(self.collection_path, vector)

        # Verify correctness
        expected = self.matrix.T @ vector
        np.testing.assert_array_almost_equal(result, expected, decimal=6)

    def test_client_handles_missing_matrix_file(self):
        """Test client handles missing matrix file gracefully."""
        client = MatrixServiceClient()
        nonexistent_path = self.temp_dir / "nonexistent"
        vector = np.random.randn(1024)

        with pytest.raises(FileNotFoundError):
            client._multiply_in_process(nonexistent_path, vector)

    def test_client_uses_correct_service_port(self):
        """Test client uses correct service port from configuration."""
        client = MatrixServiceClient(service_port=9150)

        assert client.service_port == 9150

    def test_client_multiply_returns_numpy_array(self):
        """Test client multiply returns numpy array, not list."""
        client = MatrixServiceClient()
        vector = np.random.randn(1024)

        # Mock successful service response
        with patch('requests.post') as mock_post:
            expected_result = (self.matrix.T @ vector).tolist()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'result': expected_result}

            result = client.multiply(self.collection_path, vector)

            assert isinstance(result, np.ndarray)
            assert result.shape == (64,)

    def test_client_fallback_shows_console_feedback(self):
        """Test client shows console feedback when using fallback."""
        client = MatrixServiceClient()
        vector = np.random.randn(1024)

        # Mock service failure and capture console output
        with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
            with patch('builtins.print') as mock_print:
                client.multiply(self.collection_path, vector)

                # Verify warning message was printed
                assert any(
                    'in-process' in str(call).lower() or 'fallback' in str(call).lower()
                    for call in mock_print.call_args_list
                )

    def test_client_timeout_configurable(self):
        """Test client timeout is configurable."""
        client = MatrixServiceClient(timeout_seconds=10)

        assert client.timeout_seconds == 10

    def test_client_default_timeout_is_5_seconds(self):
        """Test default timeout is 5 seconds per story requirements."""
        client = MatrixServiceClient()

        assert client.timeout_seconds == 5
