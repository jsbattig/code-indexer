"""
Integration tests for correlation ID end-to-end behavior (Story #666 AC6 & AC7).

Tests correlation ID propagation through middleware, logging, and searchability
using real FastAPI TestClient, SQLiteLogHandler, and LogAggregatorService.

AC6: Correlation ID Searchability
- Test that log entries with correlation IDs can be searched via LogAggregatorService

AC7: Correlation ID Consistency
- Test that the same request maintains the same correlation ID throughout the call chain
- Test async context preservation across multiple async operations
"""

import asyncio
import logging
import pytest
import tempfile
import uuid
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_indexer.server.middleware.correlation import (
    CorrelationContextMiddleware,
    get_correlation_id,
)
from code_indexer.server.services.sqlite_log_handler import SQLiteLogHandler
from code_indexer.server.services.log_aggregator_service import LogAggregatorService


# Test fixtures


@pytest.fixture
def temp_log_db():
    """Create temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_logs.db"
        yield db_path


@pytest.fixture
def log_handler(temp_log_db):
    """Create SQLiteLogHandler with temporary database."""
    handler = SQLiteLogHandler(temp_log_db)
    yield handler
    handler.close()


@pytest.fixture
def log_aggregator(temp_log_db):
    """Create LogAggregatorService with temporary database."""
    service = LogAggregatorService(temp_log_db)
    yield service
    service.close()


@pytest.fixture
def test_logger(log_handler):
    """Create test logger with SQLiteLogHandler attached."""
    logger = logging.getLogger("test_correlation_integration")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # Remove any existing handlers
    logger.addHandler(log_handler)
    logger.propagate = False  # Don't propagate to root logger
    yield logger
    logger.handlers.clear()


@pytest.fixture
def test_app(test_logger):
    """Create minimal FastAPI app with CorrelationContextMiddleware."""
    app = FastAPI()
    app.add_middleware(CorrelationContextMiddleware)

    @app.get("/test/simple")
    async def simple_endpoint():
        """Simple endpoint that logs with correlation ID."""
        correlation_id = get_correlation_id()
        test_logger.info(
            "Simple endpoint called",
            extra={"correlation_id": correlation_id}
        )
        return {"status": "ok", "correlation_id": correlation_id}

    @app.get("/test/error")
    async def error_endpoint():
        """Endpoint that logs an error with correlation ID."""
        correlation_id = get_correlation_id()
        test_logger.error(
            "Test error occurred",
            extra={"correlation_id": correlation_id}
        )
        return {"status": "error", "correlation_id": correlation_id}

    @app.get("/test/multiple-logs")
    async def multiple_logs_endpoint():
        """Endpoint that creates multiple log entries."""
        correlation_id = get_correlation_id()

        # Log multiple times with same correlation ID
        test_logger.debug(
            "Debug log entry",
            extra={"correlation_id": correlation_id}
        )
        test_logger.info(
            "Info log entry",
            extra={"correlation_id": correlation_id}
        )
        test_logger.warning(
            "Warning log entry",
            extra={"correlation_id": correlation_id}
        )

        return {"status": "ok", "correlation_id": correlation_id}

    @app.get("/test/nested-calls")
    async def nested_calls_endpoint():
        """Endpoint that tests correlation ID in nested function calls."""

        async def level_3():
            correlation_id = get_correlation_id()
            test_logger.info(
                "Level 3 function",
                extra={"correlation_id": correlation_id}
            )
            return correlation_id

        async def level_2():
            correlation_id = get_correlation_id()
            test_logger.info(
                "Level 2 function",
                extra={"correlation_id": correlation_id}
            )
            return await level_3()

        async def level_1():
            correlation_id = get_correlation_id()
            test_logger.info(
                "Level 1 function",
                extra={"correlation_id": correlation_id}
            )
            return await level_2()

        correlation_id = await level_1()
        return {"status": "ok", "correlation_id": correlation_id}

    @app.get("/test/parallel-async")
    async def parallel_async_endpoint():
        """Endpoint that tests correlation ID across parallel async operations."""
        correlation_id = get_correlation_id()

        async def async_task(task_id: int):
            """Simulate async task that logs with correlation ID."""
            await asyncio.sleep(0.01)  # Simulate async work
            task_correlation_id = get_correlation_id()
            test_logger.info(
                f"Async task {task_id} completed",
                extra={"correlation_id": task_correlation_id, "task_id": task_id}
            )
            return task_correlation_id

        # Run multiple async tasks in parallel
        task_correlation_ids = await asyncio.gather(
            async_task(1),
            async_task(2),
            async_task(3),
        )

        return {
            "status": "ok",
            "correlation_id": correlation_id,
            "task_correlation_ids": task_correlation_ids,
        }

    yield app


@pytest.fixture
def client(test_app):
    """Create TestClient for FastAPI app."""
    return TestClient(test_app)


# AC6: Correlation ID Searchability Tests


class TestCorrelationIDSearchability:
    """Test that log entries with correlation IDs can be searched via LogAggregatorService (AC6)."""

    def test_search_logs_by_correlation_id_single_entry(
        self, client, log_aggregator
    ):
        """Test searching for a single log entry by correlation ID."""
        # Arrange: Create a request with specific correlation ID
        test_correlation_id = str(uuid.uuid4())

        # Act: Make request with correlation ID
        response = client.get(
            "/test/simple",
            headers={"X-Correlation-ID": test_correlation_id}
        )

        # Assert: Request succeeded
        assert response.status_code == 200
        assert response.json()["correlation_id"] == test_correlation_id

        # Act: Search logs by correlation ID
        result = log_aggregator.query(correlation_id=test_correlation_id)

        # Assert: Log entry found with correct correlation ID
        assert "logs" in result, "Expected 'logs' key in query result"
        assert len(result["logs"]) == 1, f"Expected 1 log entry, got {len(result['logs'])}"

        log_entry = result["logs"][0]
        assert log_entry["correlation_id"] == test_correlation_id
        assert "Simple endpoint called" in log_entry["message"]
        assert log_entry["level"] == "INFO"

    def test_search_logs_by_correlation_id_error_entry(
        self, client, log_aggregator
    ):
        """Test searching for error log entry by correlation ID."""
        # Arrange: Create a request with specific correlation ID
        test_correlation_id = str(uuid.uuid4())

        # Act: Make request to error endpoint
        response = client.get(
            "/test/error",
            headers={"X-Correlation-ID": test_correlation_id}
        )

        # Assert: Request succeeded
        assert response.status_code == 200
        assert response.json()["correlation_id"] == test_correlation_id

        # Act: Search logs by correlation ID
        result = log_aggregator.query(correlation_id=test_correlation_id)

        # Assert: Error log entry found
        assert len(result["logs"]) == 1
        log_entry = result["logs"][0]
        assert log_entry["correlation_id"] == test_correlation_id
        assert "Test error occurred" in log_entry["message"]
        assert log_entry["level"] == "ERROR"

    def test_search_logs_by_correlation_id_multiple_entries(
        self, client, log_aggregator
    ):
        """Test searching for multiple log entries with same correlation ID."""
        # Arrange: Create a request with specific correlation ID
        test_correlation_id = str(uuid.uuid4())

        # Act: Make request to endpoint that creates multiple logs
        response = client.get(
            "/test/multiple-logs",
            headers={"X-Correlation-ID": test_correlation_id}
        )

        # Assert: Request succeeded
        assert response.status_code == 200

        # Act: Search logs by correlation ID
        result = log_aggregator.query(correlation_id=test_correlation_id)

        # Assert: All log entries found with same correlation ID
        assert len(result["logs"]) == 3, f"Expected 3 log entries, got {len(result['logs'])}"

        # Verify all entries have the same correlation ID
        for log_entry in result["logs"]:
            assert log_entry["correlation_id"] == test_correlation_id

        # Verify log levels (DEBUG, INFO, WARNING)
        log_levels = {log["level"] for log in result["logs"]}
        assert log_levels == {"DEBUG", "INFO", "WARNING"}

    def test_search_logs_by_nonexistent_correlation_id(self, log_aggregator):
        """Test searching for correlation ID that doesn't exist returns empty results."""
        # Arrange: Use a correlation ID that was never logged
        nonexistent_id = str(uuid.uuid4())

        # Act: Search for nonexistent correlation ID
        result = log_aggregator.query(correlation_id=nonexistent_id)

        # Assert: No results found
        assert len(result["logs"]) == 0
        assert result["pagination"]["total"] == 0

    def test_search_logs_filters_by_correlation_id_correctly(
        self, client, log_aggregator
    ):
        """Test that correlation ID filter only returns matching entries."""
        # Arrange: Create multiple requests with different correlation IDs
        correlation_id_1 = str(uuid.uuid4())
        correlation_id_2 = str(uuid.uuid4())

        # Act: Make requests with different correlation IDs
        client.get("/test/simple", headers={"X-Correlation-ID": correlation_id_1})
        client.get("/test/error", headers={"X-Correlation-ID": correlation_id_2})

        # Act: Search for first correlation ID
        result_1 = log_aggregator.query(correlation_id=correlation_id_1)

        # Assert: Only first correlation ID's logs returned
        assert len(result_1["logs"]) == 1
        assert result_1["logs"][0]["correlation_id"] == correlation_id_1
        assert "Simple endpoint called" in result_1["logs"][0]["message"]

        # Act: Search for second correlation ID
        result_2 = log_aggregator.query(correlation_id=correlation_id_2)

        # Assert: Only second correlation ID's logs returned
        assert len(result_2["logs"]) == 1
        assert result_2["logs"][0]["correlation_id"] == correlation_id_2
        assert "Test error occurred" in result_2["logs"][0]["message"]


# AC7: Correlation ID Consistency Tests


class TestCorrelationIDConsistency:
    """Test that the same request maintains the same correlation ID throughout the call chain (AC7)."""

    def test_correlation_id_consistent_across_multiple_logs(
        self, client, log_aggregator
    ):
        """Test that multiple log entries in same request have identical correlation ID."""
        # Arrange: Create request with specific correlation ID
        test_correlation_id = str(uuid.uuid4())

        # Act: Make request that creates multiple log entries
        response = client.get(
            "/test/multiple-logs",
            headers={"X-Correlation-ID": test_correlation_id}
        )

        # Assert: Request succeeded
        assert response.status_code == 200

        # Act: Retrieve all logs for this correlation ID
        result = log_aggregator.query(correlation_id=test_correlation_id)

        # Assert: All log entries have the SAME correlation ID
        correlation_ids = {log["correlation_id"] for log in result["logs"]}
        assert len(correlation_ids) == 1, "Expected only one unique correlation ID"
        assert correlation_ids.pop() == test_correlation_id

    def test_correlation_id_consistent_in_nested_function_calls(
        self, client, log_aggregator
    ):
        """Test correlation ID consistency through nested async function calls."""
        # Arrange: Create request with specific correlation ID
        test_correlation_id = str(uuid.uuid4())

        # Act: Make request to nested calls endpoint
        response = client.get(
            "/test/nested-calls",
            headers={"X-Correlation-ID": test_correlation_id}
        )

        # Assert: Request succeeded
        assert response.status_code == 200
        assert response.json()["correlation_id"] == test_correlation_id

        # Act: Retrieve logs for this correlation ID
        result = log_aggregator.query(correlation_id=test_correlation_id)

        # Assert: All nested function logs have same correlation ID
        assert len(result["logs"]) == 3, "Expected 3 log entries from nested calls"

        for log_entry in result["logs"]:
            assert log_entry["correlation_id"] == test_correlation_id

        # Verify all three levels logged
        messages = {log["message"] for log in result["logs"]}
        assert any("Level 1 function" in msg for msg in messages)
        assert any("Level 2 function" in msg for msg in messages)
        assert any("Level 3 function" in msg for msg in messages)

    def test_correlation_id_preserved_across_parallel_async_operations(
        self, client, log_aggregator
    ):
        """Test correlation ID preserved in parallel async operations (async context safety)."""
        # Arrange: Create request with specific correlation ID
        test_correlation_id = str(uuid.uuid4())

        # Act: Make request that spawns parallel async tasks
        response = client.get(
            "/test/parallel-async",
            headers={"X-Correlation-ID": test_correlation_id}
        )

        # Assert: Request succeeded
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["correlation_id"] == test_correlation_id

        # All parallel tasks should have the SAME correlation ID
        assert all(
            cid == test_correlation_id
            for cid in response_data["task_correlation_ids"]
        ), "Parallel async tasks should preserve correlation ID"

        # Act: Retrieve logs for this correlation ID
        result = log_aggregator.query(correlation_id=test_correlation_id)

        # Assert: All parallel task logs have same correlation ID
        assert len(result["logs"]) == 3, "Expected 3 log entries from parallel tasks"

        for log_entry in result["logs"]:
            assert log_entry["correlation_id"] == test_correlation_id

        # Verify all tasks logged
        messages = [log["message"] for log in result["logs"]]
        assert any("task 1 completed" in msg for msg in messages)
        assert any("task 2 completed" in msg for msg in messages)
        assert any("task 3 completed" in msg for msg in messages)

    def test_different_requests_have_different_correlation_ids(
        self, client, log_aggregator
    ):
        """Test that different requests maintain separate correlation IDs (no leakage)."""
        # Act: Make multiple requests WITHOUT specifying correlation IDs (auto-generated)
        response_1 = client.get("/test/simple")
        response_2 = client.get("/test/simple")
        response_3 = client.get("/test/simple")

        # Assert: Each request got a different auto-generated correlation ID
        correlation_id_1 = response_1.json()["correlation_id"]
        correlation_id_2 = response_2.json()["correlation_id"]
        correlation_id_3 = response_3.json()["correlation_id"]

        assert correlation_id_1 != correlation_id_2
        assert correlation_id_2 != correlation_id_3
        assert correlation_id_1 != correlation_id_3

        # Act: Query logs for each correlation ID
        result_1 = log_aggregator.query(correlation_id=correlation_id_1)
        result_2 = log_aggregator.query(correlation_id=correlation_id_2)
        result_3 = log_aggregator.query(correlation_id=correlation_id_3)

        # Assert: Each correlation ID has exactly one log entry (no cross-contamination)
        assert len(result_1["logs"]) == 1
        assert len(result_2["logs"]) == 1
        assert len(result_3["logs"]) == 1

        assert result_1["logs"][0]["correlation_id"] == correlation_id_1
        assert result_2["logs"][0]["correlation_id"] == correlation_id_2
        assert result_3["logs"][0]["correlation_id"] == correlation_id_3

    def test_correlation_id_in_response_matches_logged_correlation_id(
        self, client, log_aggregator
    ):
        """Test that correlation ID in response header matches logged correlation ID."""
        # Arrange: Create request with specific correlation ID
        test_correlation_id = str(uuid.uuid4())

        # Act: Make request
        response = client.get(
            "/test/simple",
            headers={"X-Correlation-ID": test_correlation_id}
        )

        # Assert: Response has correlation ID header
        assert "x-correlation-id" in response.headers
        response_correlation_id = response.headers["x-correlation-id"]
        assert response_correlation_id == test_correlation_id

        # Act: Retrieve logged entry
        result = log_aggregator.query(correlation_id=test_correlation_id)

        # Assert: Logged correlation ID matches response header
        assert len(result["logs"]) == 1
        logged_correlation_id = result["logs"][0]["correlation_id"]
        assert logged_correlation_id == response_correlation_id


# Edge Case Tests


class TestCorrelationIDEdgeCases:
    """Test edge cases and error scenarios for correlation ID handling."""

    def test_auto_generated_correlation_id_is_valid_uuid(
        self, client, log_aggregator
    ):
        """Test that auto-generated correlation IDs are valid UUIDs."""
        # Act: Make request without correlation ID header (auto-generate)
        response = client.get("/test/simple")

        # Assert: Response has correlation ID
        assert response.status_code == 200
        correlation_id = response.json()["correlation_id"]

        # Validate it's a valid UUID
        try:
            parsed_uuid = uuid.UUID(correlation_id, version=4)
            assert str(parsed_uuid) == correlation_id
        except ValueError:
            pytest.fail(f"Auto-generated correlation ID '{correlation_id}' is not a valid UUID")

        # Act: Verify it's searchable
        result = log_aggregator.query(correlation_id=correlation_id)

        # Assert: Log entry found
        assert len(result["logs"]) == 1
        assert result["logs"][0]["correlation_id"] == correlation_id

    def test_custom_correlation_id_format_preserved(
        self, client, log_aggregator
    ):
        """Test that custom correlation ID format is preserved (not just UUID)."""
        # Arrange: Use custom format correlation ID (not UUID)
        custom_correlation_id = "custom-trace-2025-01-02-abc123"

        # Act: Make request with custom correlation ID
        response = client.get(
            "/test/simple",
            headers={"X-Correlation-ID": custom_correlation_id}
        )

        # Assert: Custom correlation ID preserved in response
        assert response.status_code == 200
        assert response.json()["correlation_id"] == custom_correlation_id

        # Act: Search logs
        result = log_aggregator.query(correlation_id=custom_correlation_id)

        # Assert: Custom correlation ID preserved in logs
        assert len(result["logs"]) == 1
        assert result["logs"][0]["correlation_id"] == custom_correlation_id

    def test_correlation_id_pagination_with_filter(
        self, client, log_aggregator
    ):
        """Test that correlation ID filter works with pagination."""
        # Arrange: Create multiple log entries with same correlation ID
        test_correlation_id = str(uuid.uuid4())

        # Act: Make request that creates multiple logs
        client.get(
            "/test/multiple-logs",
            headers={"X-Correlation-ID": test_correlation_id}
        )

        # Act: Query with small page size
        result = log_aggregator.query(
            correlation_id=test_correlation_id,
            page=1,
            page_size=2
        )

        # Assert: Pagination works with correlation ID filter
        assert len(result["logs"]) == 2, "Expected 2 logs (page_size=2)"
        assert result["pagination"]["total"] == 3, "Expected total=3"
        assert result["pagination"]["total_pages"] == 2, "Expected 2 pages"

        # All returned logs should have the correct correlation ID
        for log_entry in result["logs"]:
            assert log_entry["correlation_id"] == test_correlation_id
