"""Tests for enhanced Qdrant batch safety during cancellation."""

from unittest.mock import Mock, patch

from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig


class TestQdrantBatchSafety:
    """Test enhanced batch safety for Qdrant operations."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection="test_collection",
            vector_size=384,
            hnsw_m=16,
            hnsw_ef_construct=100,
            hnsw_ef=64,
        )
        self.client = QdrantClient(self.config, self.mock_console)

    def test_upsert_points_atomic_small_batch(self):
        """Test atomic upsert with small batch (uses standard upsert)."""
        points = [
            {"id": "1", "vector": [0.1] * 384, "payload": {"text": "test1"}},
            {"id": "2", "vector": [0.2] * 384, "payload": {"text": "test2"}},
        ]

        with patch.object(
            self.client, "upsert_points", return_value=True
        ) as mock_upsert:
            result = self.client.upsert_points_atomic(points)

            assert result is True
            mock_upsert.assert_called_once_with(points, None)

    def test_upsert_points_atomic_large_batch_success(self):
        """Test atomic upsert with large batch that gets split."""
        # Create 250 points (will be split into 3 batches of 100, 100, 50)
        points = [
            {"id": f"point_{i}", "vector": [0.1] * 384, "payload": {"text": f"test{i}"}}
            for i in range(250)
        ]

        with patch.object(
            self.client, "upsert_points", return_value=True
        ) as mock_upsert:
            result = self.client.upsert_points_atomic(points, max_batch_size=100)

            assert result is True
            assert mock_upsert.call_count == 3

            # Verify batch sizes
            call_args = [call[0] for call in mock_upsert.call_args_list]
            assert len(call_args[0][0]) == 100  # First batch
            assert len(call_args[1][0]) == 100  # Second batch
            assert len(call_args[2][0]) == 50  # Third batch

    def test_upsert_points_atomic_partial_failure(self):
        """Test atomic upsert handles partial failure correctly."""
        points = [
            {"id": f"point_{i}", "vector": [0.1] * 384, "payload": {"text": f"test{i}"}}
            for i in range(250)
        ]

        # Mock upsert to fail on second batch
        with patch.object(
            self.client, "upsert_points", side_effect=[True, False, True]
        ) as mock_upsert:
            result = self.client.upsert_points_atomic(points, max_batch_size=100)

            assert result is False  # Should fail due to second batch failure
            assert mock_upsert.call_count == 2  # Should stop after failure

            # Verify error was logged
            self.mock_console.print.assert_called_with(
                "❌ Failed to upsert batch 2/3 (100 points)", style="red"
            )

    def test_upsert_points_atomic_exception_handling(self):
        """Test atomic upsert handles exceptions correctly."""
        points = [
            {"id": f"point_{i}", "vector": [0.1] * 384, "payload": {"text": f"test{i}"}}
            for i in range(150)
        ]

        # Mock upsert to raise exception on second batch
        def mock_upsert_side_effect(batch, collection=None):
            if len(batch) == 50:  # Second batch
                raise RuntimeError("Network error")
            return True

        with patch.object(
            self.client, "upsert_points", side_effect=mock_upsert_side_effect
        ) as mock_upsert:
            result = self.client.upsert_points_atomic(points, max_batch_size=100)

            assert result is False
            assert mock_upsert.call_count == 2

            # Verify exception was logged
            self.mock_console.print.assert_called_with(
                "❌ Exception in batch 2/2: Network error", style="red"
            )

    def test_upsert_points_atomic_empty_batch(self):
        """Test atomic upsert with empty batch."""
        result = self.client.upsert_points_atomic([])
        assert result is True

    def test_upsert_points_atomic_custom_max_batch_size(self):
        """Test atomic upsert with custom max batch size."""
        points = [
            {"id": f"point_{i}", "vector": [0.1] * 384, "payload": {"text": f"test{i}"}}
            for i in range(75)
        ]

        with patch.object(
            self.client, "upsert_points", return_value=True
        ) as mock_upsert:
            result = self.client.upsert_points_atomic(points, max_batch_size=25)

            assert result is True
            assert mock_upsert.call_count == 3  # 75 points / 25 = 3 batches

            # Verify all batches are size 25
            call_args = [call[0] for call in mock_upsert.call_args_list]
            assert all(len(args[0]) == 25 for args in call_args)

    def test_upsert_points_atomic_collection_name_passed(self):
        """Test that collection name is properly passed through."""
        points = [{"id": "1", "vector": [0.1] * 384, "payload": {"text": "test"}}]

        with patch.object(
            self.client, "upsert_points", return_value=True
        ) as mock_upsert:
            result = self.client.upsert_points_atomic(
                points, collection_name="custom_collection"
            )

            assert result is True
            mock_upsert.assert_called_once_with(points, "custom_collection")


class TestQdrantBatchSafetyIntegration:
    """Integration tests for batch safety functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection="test_collection",
            vector_size=384,
            hnsw_m=16,
            hnsw_ef_construct=100,
            hnsw_ef=64,
        )
        self.client = QdrantClient(self.config, self.mock_console)

    def test_cancellation_safe_batch_processing(self):
        """Test that batch processing is safe during cancellation scenarios."""
        # Simulate a scenario where cancellation occurs during batch processing
        large_batch = [
            {"id": f"point_{i}", "vector": [0.1] * 384, "payload": {"text": f"test{i}"}}
            for i in range(500)
        ]

        # Mock HTTP client to simulate different scenarios
        with patch.object(self.client.client, "put") as mock_put:
            # First few batches succeed, then network error simulates cancellation
            mock_responses = []

            # Create successful responses for first few batches
            for i in range(3):
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.raise_for_status.return_value = None
                mock_responses.append(mock_response)

            # Create failing response to simulate cancellation/network issue
            mock_error_response = Mock()
            mock_error_response.status_code = 500
            mock_error_response.reason_phrase = "Internal Server Error"
            mock_error_response.content = b'{"status": {"error": "Server overloaded"}}'
            mock_error_response.json.return_value = {
                "status": {"error": "Server overloaded"}
            }
            mock_error_response.raise_for_status.side_effect = Exception("HTTP 500")
            mock_responses.append(mock_error_response)

            mock_put.side_effect = mock_responses

            # This should fail safely after processing some batches
            result = self.client.upsert_points_atomic(large_batch, max_batch_size=100)

            assert result is False
            # Should have attempted 4 batches before failing
            assert mock_put.call_count == 4

    def test_progress_tracking_during_batch_operations(self):
        """Test that progress can be tracked during large batch operations."""
        points = [
            {"id": f"point_{i}", "vector": [0.1] * 384, "payload": {"text": f"test{i}"}}
            for i in range(300)
        ]

        successful_batches = []

        def track_batch_progress(batch, collection=None):
            successful_batches.append(len(batch))
            return True

        with patch.object(
            self.client, "upsert_points", side_effect=track_batch_progress
        ):
            result = self.client.upsert_points_atomic(points, max_batch_size=100)

            assert result is True
            assert len(successful_batches) == 3  # 300 points / 100 = 3 batches
            assert successful_batches == [100, 100, 100]  # All batches were size 100
