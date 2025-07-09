"""
Unit tests for Qdrant model filtering functionality.
"""

import pytest
from unittest.mock import Mock, patch

from code_indexer.config import QdrantConfig
from code_indexer.services.qdrant import QdrantClient
from rich.console import Console


class TestQdrantModelFiltering:
    """Test Qdrant model filtering functionality."""

    @pytest.fixture
    def qdrant_config(self):
        return QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=768,
        )

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def qdrant_client(self, qdrant_config, console):
        return QdrantClient(qdrant_config, console)

    def test_create_point_with_embedding_model(self, qdrant_client):
        """Test creating a point with embedding model metadata."""
        point = qdrant_client.create_point(
            point_id="test_id",
            vector=[0.1, 0.2, 0.3, 0.4],
            payload={"content": "test content", "path": "test.py"},
            embedding_model="voyage-code-3",
        )

        assert point["id"] == "test_id"
        assert point["vector"] == [0.1, 0.2, 0.3, 0.4]
        assert point["payload"]["content"] == "test content"
        assert point["payload"]["path"] == "test.py"
        assert point["payload"]["embedding_model"] == "voyage-code-3"

    def test_create_point_without_embedding_model(self, qdrant_client):
        """Test creating a point without embedding model metadata."""
        point = qdrant_client.create_point(
            point_id="test_id",
            vector=[0.1, 0.2, 0.3, 0.4],
            payload={"content": "test content", "path": "test.py"},
        )

        assert point["id"] == "test_id"
        assert point["vector"] == [0.1, 0.2, 0.3, 0.4]
        assert point["payload"]["content"] == "test content"
        assert point["payload"]["path"] == "test.py"
        assert "embedding_model" not in point["payload"]

    def test_create_model_filter(self, qdrant_client):
        """Test creating a model filter condition."""
        filter_condition = qdrant_client.create_model_filter("voyage-code-3")

        expected = {
            "must": [{"key": "embedding_model", "match": {"value": "voyage-code-3"}}]
        }

        assert filter_condition == expected

    def test_combine_filters_no_filters(self, qdrant_client):
        """Test combining filters when no filters are provided."""
        result = qdrant_client.combine_filters(None, None)
        assert result is None

    def test_combine_filters_model_filter_only(self, qdrant_client):
        """Test combining filters with only model filter."""
        model_filter = qdrant_client.create_model_filter("voyage-code-3")
        result = qdrant_client.combine_filters(model_filter, None)

        assert result == model_filter

    def test_combine_filters_additional_filter_only(self, qdrant_client):
        """Test combining filters with only additional filter."""
        additional_filter = {
            "must": [{"key": "language", "match": {"value": "python"}}]
        }
        result = qdrant_client.combine_filters(None, additional_filter)

        assert result == additional_filter

    def test_combine_filters_both_filters(self, qdrant_client):
        """Test combining model filter with additional filters."""
        model_filter = qdrant_client.create_model_filter("voyage-code-3")
        additional_filter = {
            "must": [{"key": "language", "match": {"value": "python"}}]
        }

        result = qdrant_client.combine_filters(model_filter, additional_filter)

        expected = {
            "must": [
                {"key": "embedding_model", "match": {"value": "voyage-code-3"}},
                {"key": "language", "match": {"value": "python"}},
            ]
        }

        assert result == expected

    def test_combine_filters_with_should_conditions(self, qdrant_client):
        """Test combining filters with should conditions."""
        model_filter = qdrant_client.create_model_filter("voyage-code-3")
        additional_filter = {
            "must": [{"key": "language", "match": {"value": "python"}}],
            "should": [{"key": "path", "match": {"text": "test"}}],
        }

        result = qdrant_client.combine_filters(model_filter, additional_filter)

        expected = {
            "must": [
                {"key": "embedding_model", "match": {"value": "voyage-code-3"}},
                {"key": "language", "match": {"value": "python"}},
            ],
            "should": [{"key": "path", "match": {"text": "test"}}],
        }

        assert result == expected

    @patch("httpx.Client.post")
    def test_search_with_model_filter(self, mock_post, qdrant_client):
        """Test searching with model filter."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                {
                    "id": "test_id",
                    "score": 0.95,
                    "payload": {
                        "content": "test content",
                        "embedding_model": "voyage-code-3",
                    },
                }
            ]
        }
        mock_post.return_value = mock_response

        results = qdrant_client.search_with_model_filter(
            query_vector=[0.1, 0.2, 0.3, 0.4], embedding_model="voyage-code-3", limit=10
        )

        assert len(results) == 1
        assert results[0]["id"] == "test_id"
        assert results[0]["score"] == 0.95

        # Verify the request was made with correct filter
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        request_data = call_args[1]["json"]

        assert "filter" in request_data
        assert request_data["filter"]["must"][0]["key"] == "embedding_model"
        assert request_data["filter"]["must"][0]["match"]["value"] == "voyage-code-3"

    @patch("httpx.Client.post")
    def test_search_with_model_filter_and_additional_filters(
        self, mock_post, qdrant_client
    ):
        """Test searching with model filter and additional filters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        additional_filters = {
            "must": [{"key": "language", "match": {"value": "python"}}]
        }

        qdrant_client.search_with_model_filter(
            query_vector=[0.1, 0.2, 0.3, 0.4],
            embedding_model="voyage-code-3",
            additional_filters=additional_filters,
            limit=10,
        )

        # Verify the request was made with combined filters
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        request_data = call_args[1]["json"]

        assert "filter" in request_data
        must_conditions = request_data["filter"]["must"]
        assert len(must_conditions) == 2

        # Check for both model and language filters
        model_filter_found = False
        language_filter_found = False

        for condition in must_conditions:
            if (
                condition["key"] == "embedding_model"
                and condition["match"]["value"] == "voyage-code-3"
            ):
                model_filter_found = True
            elif (
                condition["key"] == "language"
                and condition["match"]["value"] == "python"
            ):
                language_filter_found = True

        assert model_filter_found
        assert language_filter_found

    @patch("httpx.Client.post")
    def test_count_points_by_model(self, mock_post, qdrant_client):
        """Test counting points by embedding model."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"count": 42}}
        mock_post.return_value = mock_response

        count = qdrant_client.count_points_by_model("voyage-code-3")

        assert count == 42

        # Verify the request was made with correct filter
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        endpoint = call_args[0][0]
        request_data = call_args[1]["json"]

        assert endpoint == "/collections/test_collection/points/count"
        assert request_data["filter"]["must"][0]["key"] == "embedding_model"
        assert request_data["filter"]["must"][0]["match"]["value"] == "voyage-code-3"

    @patch("httpx.Client.post")
    def test_count_points_by_model_error(self, mock_post, qdrant_client):
        """Test counting points by model with error."""
        mock_post.side_effect = Exception("Connection error")

        count = qdrant_client.count_points_by_model("voyage-code-3")

        assert count == 0

    def test_create_point_preserves_existing_payload(self, qdrant_client):
        """Test that create_point preserves existing payload data."""
        existing_payload = {
            "content": "test content",
            "path": "test.py",
            "language": "python",
            "file_size": 1024,
        }

        point = qdrant_client.create_point(
            point_id="test_id",
            vector=[0.1, 0.2, 0.3, 0.4],
            payload=existing_payload,
            embedding_model="voyage-code-3",
        )

        # Verify all original payload data is preserved
        assert point["payload"]["content"] == "test content"
        assert point["payload"]["path"] == "test.py"
        assert point["payload"]["language"] == "python"
        assert point["payload"]["file_size"] == 1024

        # Verify embedding model was added
        assert point["payload"]["embedding_model"] == "voyage-code-3"

    def test_create_point_empty_payload(self, qdrant_client):
        """Test creating point with empty payload."""
        point = qdrant_client.create_point(
            point_id="test_id",
            vector=[0.1, 0.2, 0.3, 0.4],
            payload={},
            embedding_model="voyage-code-3",
        )

        assert point["payload"]["embedding_model"] == "voyage-code-3"
        assert len(point["payload"]) == 1  # Only embedding_model

    def test_model_filter_special_characters(self, qdrant_client):
        """Test model filter with special characters in model name."""
        model_name = "voyage-code-3.1-beta"
        filter_condition = qdrant_client.create_model_filter(model_name)

        expected = {
            "must": [
                {"key": "embedding_model", "match": {"value": "voyage-code-3.1-beta"}}
            ]
        }

        assert filter_condition == expected


class TestQdrantModelFilteringIntegration:
    """Integration tests for Qdrant model filtering with other components."""

    @pytest.fixture
    def qdrant_config(self):
        return QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=768,
        )

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def qdrant_client(self, qdrant_config, console):
        return QdrantClient(qdrant_config, console)

    def test_multiple_models_isolation(self, qdrant_client):
        """Test that multiple models are properly isolated."""
        # Create points for different models
        points = [
            qdrant_client.create_point(
                point_id="ollama_1",
                vector=[0.1, 0.2, 0.3, 0.4],
                payload={"content": "ollama content 1"},
                embedding_model="nomic-embed-text",
            ),
            qdrant_client.create_point(
                point_id="voyage_1",
                vector=[0.5, 0.6, 0.7, 0.8],
                payload={"content": "voyage content 1"},
                embedding_model="voyage-code-3",
            ),
            qdrant_client.create_point(
                point_id="ollama_2",
                vector=[0.9, 1.0, 1.1, 1.2],
                payload={"content": "ollama content 2"},
                embedding_model="nomic-embed-text",
            ),
        ]

        # Verify each point has correct embedding model
        for point in points:
            if point["id"].startswith("ollama"):
                assert point["payload"]["embedding_model"] == "nomic-embed-text"
            else:
                assert point["payload"]["embedding_model"] == "voyage-code-3"

    def test_backward_compatibility_no_model(self, qdrant_client):
        """Test backward compatibility with points that don't have embedding_model."""
        # Create point without embedding model (legacy data)
        point = qdrant_client.create_point(
            point_id="legacy_point",
            vector=[0.1, 0.2, 0.3, 0.4],
            payload={"content": "legacy content", "path": "legacy.py"},
        )

        # Verify no embedding_model is added
        assert "embedding_model" not in point["payload"]
        assert point["payload"]["content"] == "legacy content"
        assert point["payload"]["path"] == "legacy.py"

    @patch("httpx.Client.post")
    def test_search_performance_with_model_filter(self, mock_post, qdrant_client):
        """Test that model filtering doesn't impact search performance significantly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        # Perform search with model filter
        qdrant_client.search_with_model_filter(
            query_vector=[0.1] * 768,  # Full vector
            embedding_model="voyage-code-3",
            limit=100,
        )

        # Verify only one request was made (no additional filtering calls)
        assert mock_post.call_count == 1

        # Verify the request structure is efficient
        call_args = mock_post.call_args
        request_data = call_args[1]["json"]

        assert "vector" in request_data
        assert len(request_data["vector"]) == 768
        assert "filter" in request_data
        assert "limit" in request_data
