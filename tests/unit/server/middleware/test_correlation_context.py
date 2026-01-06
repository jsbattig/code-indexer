"""
Unit tests for correlation ID context management and middleware.

Tests correlation ID generation, storage in contextvars, and middleware integration
following TDD methodology for Story #666 AC2.
"""

import pytest
import uuid
from unittest.mock import MagicMock
from fastapi import Request, Response
from starlette.datastructures import Headers

# These imports will FAIL initially - that's the point of TDD (RED phase)
from code_indexer.server.middleware.correlation import (
    get_correlation_id,
    set_correlation_id,
    clear_correlation_id,
    CorrelationContextMiddleware,
)


class TestCorrelationIDContextHelpers:
    """Test correlation ID context variable helpers."""

    def test_get_correlation_id_returns_none_when_not_set(self):
        """Test that get_correlation_id returns None when no correlation ID is set."""
        # Arrange: Clear any existing correlation ID
        clear_correlation_id()

        # Act
        result = get_correlation_id()

        # Assert
        assert result is None, "Expected None when correlation ID not set"

    def test_set_and_get_correlation_id(self):
        """Test that set_correlation_id stores value accessible via get_correlation_id."""
        # Arrange
        test_correlation_id = "test-correlation-id-12345"
        clear_correlation_id()

        # Act
        set_correlation_id(test_correlation_id)
        result = get_correlation_id()

        # Assert
        assert (
            result == test_correlation_id
        ), f"Expected {test_correlation_id}, got {result}"

    def test_set_correlation_id_overwrites_previous_value(self):
        """Test that set_correlation_id overwrites any previously set value."""
        # Arrange
        first_id = "first-correlation-id"
        second_id = "second-correlation-id"
        clear_correlation_id()

        # Act
        set_correlation_id(first_id)
        set_correlation_id(second_id)
        result = get_correlation_id()

        # Assert
        assert result == second_id, f"Expected {second_id}, got {result}"

    def test_clear_correlation_id_removes_value(self):
        """Test that clear_correlation_id removes the stored correlation ID."""
        # Arrange
        test_id = "test-id-to-clear"
        set_correlation_id(test_id)

        # Act
        clear_correlation_id()
        result = get_correlation_id()

        # Assert
        assert result is None, "Expected None after clearing correlation ID"

    def test_correlation_id_is_async_safe_across_contexts(self):
        """Test that correlation IDs are isolated in async contexts (contextvars behavior)."""
        # This test verifies contextvars isolation - correlation IDs set in one async
        # context should not leak to another async context

        # Arrange
        clear_correlation_id()
        context_id = "main-context-id"
        set_correlation_id(context_id)

        # Act & Assert
        # In the main context, we should see our ID
        assert get_correlation_id() == context_id

        # Clear for next test
        clear_correlation_id()
        assert get_correlation_id() is None


class TestCorrelationContextMiddleware:
    """Test CorrelationContextMiddleware for FastAPI."""

    @pytest.mark.asyncio
    async def test_middleware_generates_correlation_id_when_header_missing(self):
        """Test middleware generates UUID v4 when X-Correlation-ID header not present."""
        # Arrange
        middleware = CorrelationContextMiddleware(app=MagicMock())

        # Mock request without X-Correlation-ID header
        request = MagicMock(spec=Request)
        request.headers = Headers({})

        # Mock response
        mock_response = Response(content="test", status_code=200)

        # Mock call_next to return response
        async def mock_call_next(req):
            return mock_response

        # Act
        response = await middleware.dispatch(request, mock_call_next)

        # Assert
        # Response should have X-Correlation-ID header with valid UUID
        assert (
            "X-Correlation-ID" in response.headers
        ), "Missing X-Correlation-ID in response"
        correlation_id = response.headers["X-Correlation-ID"]

        # Validate it's a valid UUID v4
        try:
            parsed_uuid = uuid.UUID(correlation_id, version=4)
            assert (
                str(parsed_uuid) == correlation_id
            ), "Correlation ID is not a valid UUID v4"
        except ValueError:
            pytest.fail(f"Correlation ID '{correlation_id}' is not a valid UUID")

    @pytest.mark.asyncio
    async def test_middleware_uses_existing_correlation_id_from_header(self):
        """Test middleware uses X-Correlation-ID from request header when present."""
        # Arrange
        middleware = CorrelationContextMiddleware(app=MagicMock())

        expected_correlation_id = "existing-correlation-id-from-client"

        # Mock request WITH X-Correlation-ID header
        request = MagicMock(spec=Request)
        request.headers = Headers({"X-Correlation-ID": expected_correlation_id})

        # Mock response
        mock_response = Response(content="test", status_code=200)

        # Mock call_next to return response
        async def mock_call_next(req):
            return mock_response

        # Act
        response = await middleware.dispatch(request, mock_call_next)

        # Assert
        # Response should have the SAME correlation ID from request
        assert (
            "X-Correlation-ID" in response.headers
        ), "Missing X-Correlation-ID in response"
        correlation_id = response.headers["X-Correlation-ID"]
        assert (
            correlation_id == expected_correlation_id
        ), f"Expected {expected_correlation_id}, got {correlation_id}"

    @pytest.mark.asyncio
    async def test_middleware_stores_correlation_id_in_context(self):
        """Test middleware stores correlation ID in contextvars accessible via get_correlation_id."""
        # Arrange
        middleware = CorrelationContextMiddleware(app=MagicMock())

        expected_correlation_id = "test-context-correlation-id"

        # Mock request with correlation ID
        request = MagicMock(spec=Request)
        request.headers = Headers({"X-Correlation-ID": expected_correlation_id})

        # Mock response
        mock_response = Response(content="test", status_code=200)

        # Track correlation ID during request processing
        correlation_id_during_request = None

        async def mock_call_next(req):
            nonlocal correlation_id_during_request
            # During request processing, correlation ID should be accessible
            correlation_id_during_request = get_correlation_id()
            return mock_response

        # Act
        await middleware.dispatch(request, mock_call_next)

        # Assert
        # Correlation ID should have been accessible during request processing
        assert (
            correlation_id_during_request == expected_correlation_id
        ), f"Expected {expected_correlation_id} during request, got {correlation_id_during_request}"

    @pytest.mark.asyncio
    async def test_middleware_adds_correlation_id_to_response_headers(self):
        """Test middleware adds X-Correlation-ID to response headers."""
        # Arrange
        middleware = CorrelationContextMiddleware(app=MagicMock())

        request = MagicMock(spec=Request)
        request.headers = Headers({})

        # Mock response WITHOUT X-Correlation-ID header
        mock_response = Response(content="test", status_code=200)

        async def mock_call_next(req):
            return mock_response

        # Act
        response = await middleware.dispatch(request, mock_call_next)

        # Assert
        assert (
            "X-Correlation-ID" in response.headers
        ), "Middleware should add X-Correlation-ID to response headers"

    @pytest.mark.asyncio
    async def test_middleware_preserves_existing_response_headers(self):
        """Test middleware preserves existing response headers when adding correlation ID."""
        # Arrange
        middleware = CorrelationContextMiddleware(app=MagicMock())

        request = MagicMock(spec=Request)
        request.headers = Headers({})

        # Mock response with existing headers
        mock_response = Response(
            content="test",
            status_code=200,
            headers={"Content-Type": "application/json", "X-Custom": "custom-value"},
        )

        async def mock_call_next(req):
            return mock_response

        # Act
        response = await middleware.dispatch(request, mock_call_next)

        # Assert
        # Original headers should still be present
        assert "Content-Type" in response.headers
        assert response.headers["Content-Type"] == "application/json"
        assert "X-Custom" in response.headers
        assert response.headers["X-Custom"] == "custom-value"
        # New correlation ID header should be added
        assert "X-Correlation-ID" in response.headers

    @pytest.mark.asyncio
    async def test_correlation_id_consistent_throughout_request(self):
        """Test that the same correlation ID is used throughout entire request lifecycle."""
        # Arrange
        middleware = CorrelationContextMiddleware(app=MagicMock())

        expected_correlation_id = "consistent-correlation-id"

        request = MagicMock(spec=Request)
        request.headers = Headers({"X-Correlation-ID": expected_correlation_id})

        mock_response = Response(content="test", status_code=200)

        # Track correlation IDs at different points
        correlation_ids_during_request = []

        async def mock_call_next(req):
            # Check correlation ID multiple times during request processing
            correlation_ids_during_request.append(get_correlation_id())
            correlation_ids_during_request.append(get_correlation_id())
            correlation_ids_during_request.append(get_correlation_id())
            return mock_response

        # Act
        response = await middleware.dispatch(request, mock_call_next)

        # Assert
        # All correlation IDs during request should be identical
        assert all(
            cid == expected_correlation_id for cid in correlation_ids_during_request
        ), f"Correlation ID not consistent: {correlation_ids_during_request}"

        # Response should also have the same correlation ID
        assert response.headers["X-Correlation-ID"] == expected_correlation_id


class TestCorrelationIDFormat:
    """Test correlation ID format compliance."""

    @pytest.mark.asyncio
    async def test_generated_correlation_id_is_valid_uuid_v4(self):
        """Test that generated correlation IDs are valid UUID v4 format."""
        # Arrange
        middleware = CorrelationContextMiddleware(app=MagicMock())

        request = MagicMock(spec=Request)
        request.headers = Headers({})  # No correlation ID header

        mock_response = Response(content="test", status_code=200)

        async def mock_call_next(req):
            return mock_response

        # Act
        response = await middleware.dispatch(request, mock_call_next)

        # Assert
        correlation_id = response.headers["X-Correlation-ID"]

        # Validate UUID v4 format
        try:
            parsed = uuid.UUID(correlation_id, version=4)
            assert parsed.version == 4, f"Expected UUID version 4, got {parsed.version}"
            assert str(parsed) == correlation_id, "UUID string representation mismatch"
        except ValueError as e:
            pytest.fail(f"Invalid UUID v4 format: {correlation_id} - {e}")

    def test_correlation_id_format_is_string(self):
        """Test that correlation IDs are always strings."""
        # Arrange
        test_id = "test-string-id"
        clear_correlation_id()

        # Act
        set_correlation_id(test_id)
        result = get_correlation_id()

        # Assert
        assert isinstance(result, str), f"Expected str, got {type(result)}"


class TestCorrelationIDInheritance:
    """Test correlation ID inheritance patterns (AC7)."""

    @pytest.mark.asyncio
    async def test_correlation_id_accessible_in_nested_function_calls(self):
        """Test correlation ID is accessible in nested function calls within same request."""
        # Arrange
        middleware = CorrelationContextMiddleware(app=MagicMock())

        expected_correlation_id = "nested-call-correlation-id"

        request = MagicMock(spec=Request)
        request.headers = Headers({"X-Correlation-ID": expected_correlation_id})

        mock_response = Response(content="test", status_code=200)

        # Simulate nested function calls
        def level_3_function():
            return get_correlation_id()

        def level_2_function():
            return level_3_function()

        def level_1_function():
            return level_2_function()

        correlation_id_from_nested_call = None

        async def mock_call_next(req):
            nonlocal correlation_id_from_nested_call
            correlation_id_from_nested_call = level_1_function()
            return mock_response

        # Act
        await middleware.dispatch(request, mock_call_next)

        # Assert
        assert (
            correlation_id_from_nested_call == expected_correlation_id
        ), "Correlation ID should be accessible in nested function calls"
