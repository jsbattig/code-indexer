"""
Unit tests for LogAggregatorService - backend service for querying logs.

TDD Red Phase: These tests will fail until LogAggregatorService is implemented.

Test Coverage:
- AC6: LogAggregatorService Backend
  - Query method with pagination support
  - Count method for total records
  - Consistent response format across Web UI, REST, and MCP
  - Handles empty database gracefully
  - Filtering and sorting capabilities
"""

import logging
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from code_indexer.server.services.log_aggregator_service import LogAggregatorService
from code_indexer.server.services.sqlite_log_handler import SQLiteLogHandler


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_logs.db"
        yield db_path


@pytest.fixture
def populated_db_path(temp_db_path: Path) -> Generator[Path, None, None]:
    """Create a database populated with test log records."""
    # Create handler and logger
    handler = SQLiteLogHandler(temp_db_path)
    logger = logging.getLogger("test.populated")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    # Insert test log records with varying levels and timestamps
    logger.debug("Debug message 1")
    logger.info(
        "Info message 1", extra={"correlation_id": "corr-1", "user_id": "user1"}
    )
    logger.warning("Warning message 1")
    logger.error("Error message 1", extra={"correlation_id": "corr-2"})
    logger.critical("Critical message 1")

    logger.debug(
        "Debug message 2", extra={"user_id": "user2", "request_path": "/api/test"}
    )
    logger.info("Info message 2")
    logger.warning("Warning message 2", extra={"correlation_id": "corr-3"})
    logger.error("Error message 2")
    logger.critical("Critical message 2", extra={"user_id": "user3"})

    handler.close()

    yield temp_db_path


@pytest.fixture
def aggregator_service(
    temp_db_path: Path,
) -> Generator[LogAggregatorService, None, None]:
    """Create a LogAggregatorService instance for testing."""
    service = LogAggregatorService(temp_db_path)
    yield service
    service.close()


@pytest.fixture
def populated_aggregator_service(
    populated_db_path: Path,
) -> Generator[LogAggregatorService, None, None]:
    """Create a LogAggregatorService with populated database."""
    service = LogAggregatorService(populated_db_path)
    yield service
    service.close()


class TestLogAggregatorServiceBasics:
    """Test basic LogAggregatorService functionality."""

    def test_service_initializes_with_db_path(self, temp_db_path: Path):
        """Test that service initializes correctly with database path."""
        service = LogAggregatorService(temp_db_path)
        assert service is not None
        service.close()

    def test_service_handles_nonexistent_database(self):
        """Test that service handles nonexistent database gracefully."""
        nonexistent_path = Path("/tmp/nonexistent_dir_12345/logs.db")

        # Should not raise exception during initialization
        service = LogAggregatorService(nonexistent_path)

        # Should return empty results
        result = service.query(page=1, page_size=10)
        assert result["logs"] == []
        assert result["pagination"]["total"] == 0

        service.close()


class TestLogAggregatorServiceQuery:
    """Test query method with pagination."""

    def test_query_returns_correct_structure(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query returns correct response structure."""
        result = populated_aggregator_service.query(page=1, page_size=10)

        # Verify structure matches API format from issue #664
        assert "logs" in result
        assert "pagination" in result
        assert isinstance(result["logs"], list)
        assert isinstance(result["pagination"], dict)

        # Verify pagination metadata
        pagination = result["pagination"]
        assert "page" in pagination
        assert "page_size" in pagination
        assert "total" in pagination
        assert "total_pages" in pagination

    def test_query_returns_all_required_fields(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query returns all required fields for each log entry."""
        result = populated_aggregator_service.query(page=1, page_size=10)

        assert len(result["logs"]) > 0

        # Check first log entry has all required fields (AC3/AC4)
        log_entry = result["logs"][0]
        assert "id" in log_entry
        assert "timestamp" in log_entry
        assert "level" in log_entry
        assert "source" in log_entry
        assert "message" in log_entry
        assert "correlation_id" in log_entry  # Can be None
        assert "user_id" in log_entry  # Can be None
        assert "request_path" in log_entry  # Can be None

    def test_query_pagination_works(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that pagination correctly splits results."""
        # Get first page with page_size=3
        page1 = populated_aggregator_service.query(page=1, page_size=3)
        page2 = populated_aggregator_service.query(page=2, page_size=3)

        # Should have different logs
        assert len(page1["logs"]) == 3
        assert len(page2["logs"]) <= 3  # May be less on last page

        # Logs should be different
        page1_ids = {log["id"] for log in page1["logs"]}
        page2_ids = {log["id"] for log in page2["logs"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_query_defaults_to_newest_first(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query returns logs in reverse chronological order by default (AC1)."""
        result = populated_aggregator_service.query(page=1, page_size=10)

        # Verify timestamps are in descending order
        timestamps = [log["timestamp"] for log in result["logs"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_query_handles_empty_database(
        self, aggregator_service: LogAggregatorService
    ):
        """Test that query handles empty database gracefully (AC6)."""
        result = aggregator_service.query(page=1, page_size=10)

        assert result["logs"] == []
        assert result["pagination"]["total"] == 0
        assert result["pagination"]["total_pages"] == 0

    def test_query_respects_page_size(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query respects page_size parameter."""
        result = populated_aggregator_service.query(page=1, page_size=5)

        assert len(result["logs"]) <= 5
        assert result["pagination"]["page_size"] == 5

    def test_query_handles_page_beyond_range(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query handles page number beyond available pages."""
        result = populated_aggregator_service.query(page=100, page_size=10)

        # Should return empty logs but valid pagination
        assert result["logs"] == []
        assert result["pagination"]["page"] == 100


class TestLogAggregatorServiceCount:
    """Test count method for total records."""

    def test_count_returns_total_records(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that count returns correct total number of log records."""
        count = populated_aggregator_service.count()

        # Should match the number of logs inserted in fixture (10 logs)
        assert count == 10
        assert isinstance(count, int)

    def test_count_returns_zero_for_empty_database(
        self, aggregator_service: LogAggregatorService
    ):
        """Test that count returns 0 for empty database."""
        count = aggregator_service.count()
        assert count == 0


class TestLogAggregatorServiceFiltering:
    """Test filtering capabilities."""

    def test_query_filters_by_level(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query can filter by log level."""
        result = populated_aggregator_service.query(page=1, page_size=10, level="ERROR")

        # Should only return ERROR level logs
        for log in result["logs"]:
            assert log["level"] == "ERROR"

        # Should have 2 ERROR logs from fixture
        assert len(result["logs"]) == 2

    def test_query_filters_by_source(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query can filter by source (logger name)."""
        result = populated_aggregator_service.query(
            page=1, page_size=10, source="test.populated"
        )

        # Should only return logs from test.populated logger
        for log in result["logs"]:
            assert log["source"] == "test.populated"

    def test_query_filters_by_correlation_id(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query can filter by correlation_id."""
        result = populated_aggregator_service.query(
            page=1, page_size=10, correlation_id="corr-1"
        )

        # Should only return log with correlation_id="corr-1"
        assert len(result["logs"]) == 1
        assert result["logs"][0]["correlation_id"] == "corr-1"


class TestLogAggregatorServiceSorting:
    """Test sorting capabilities."""

    def test_query_supports_ascending_sort(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query supports ascending sort order."""
        result = populated_aggregator_service.query(
            page=1, page_size=10, sort_order="asc"
        )

        # Verify timestamps are in ascending order
        timestamps = [log["timestamp"] for log in result["logs"]]
        assert timestamps == sorted(timestamps)

    def test_query_supports_descending_sort(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query supports descending sort order (default)."""
        result = populated_aggregator_service.query(
            page=1, page_size=10, sort_order="desc"
        )

        # Verify timestamps are in descending order
        timestamps = [log["timestamp"] for log in result["logs"]]
        assert timestamps == sorted(timestamps, reverse=True)


class TestLogAggregatorServicePaginationMetadata:
    """Test pagination metadata calculation."""

    def test_pagination_calculates_total_pages_correctly(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that pagination correctly calculates total_pages."""
        result = populated_aggregator_service.query(page=1, page_size=3)

        # With 10 logs and page_size=3, should have 4 pages (10 / 3 = 3.33 => 4)
        assert result["pagination"]["total"] == 10
        assert result["pagination"]["total_pages"] == 4

    def test_pagination_metadata_matches_query_params(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that pagination metadata reflects query parameters."""
        result = populated_aggregator_service.query(page=2, page_size=5)

        assert result["pagination"]["page"] == 2
        assert result["pagination"]["page_size"] == 5


class TestLogAggregatorServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_service_handles_page_zero(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that service handles page=0 gracefully (treats as page=1)."""
        result = populated_aggregator_service.query(page=0, page_size=10)

        # Should treat page=0 as page=1
        assert result["pagination"]["page"] == 1

    def test_service_handles_negative_page(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that service handles negative page gracefully."""
        result = populated_aggregator_service.query(page=-1, page_size=10)

        # Should treat negative page as page=1
        assert result["pagination"]["page"] == 1

    def test_service_handles_page_size_exceeding_max(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that service enforces max page_size limit (1000 from AC3)."""
        result = populated_aggregator_service.query(page=1, page_size=2000)

        # Should cap at max page_size (1000)
        assert result["pagination"]["page_size"] == 1000

    def test_service_handles_zero_page_size(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that service handles page_size=0 gracefully."""
        result = populated_aggregator_service.query(page=1, page_size=0)

        # Should default to default page_size (50 from AC3)
        assert result["pagination"]["page_size"] == 50


class TestLogAggregatorServiceResponseFormat:
    """Test response format consistency (AC6)."""

    def test_response_format_matches_api_spec(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that response format matches API spec from issue #664."""
        result = populated_aggregator_service.query(page=1, page_size=10)

        # Structure from API Response Format in issue #664
        assert isinstance(result, dict)
        assert set(result.keys()) == {"logs", "pagination"}

        # Logs array
        assert isinstance(result["logs"], list)
        if result["logs"]:
            log_entry = result["logs"][0]
            expected_keys = {
                "id",
                "timestamp",
                "level",
                "source",
                "message",
                "correlation_id",
                "user_id",
                "request_path",
            }
            assert expected_keys.issubset(set(log_entry.keys()))

        # Pagination metadata
        pagination = result["pagination"]
        assert isinstance(pagination, dict)
        assert set(pagination.keys()) == {"page", "page_size", "total", "total_pages"}
        assert isinstance(pagination["page"], int)
        assert isinstance(pagination["page_size"], int)
        assert isinstance(pagination["total"], int)
        assert isinstance(pagination["total_pages"], int)


class TestLogAggregatorServiceSearch:
    """Test search functionality (Story #665 AC1, AC6)."""

    def test_search_filters_by_message_content(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that search matches against message content."""
        # Search for "Debug" - should match Debug message 1 and Debug message 2
        result = populated_aggregator_service.query(
            page=1, page_size=10, search="Debug"
        )

        # Should find logs with "Debug" in message
        assert len(result["logs"]) == 2
        for log in result["logs"]:
            assert "Debug" in log["message"] or "debug" in log["message"].lower()

    def test_search_filters_by_correlation_id(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that search matches against correlation_id."""
        # Search for "corr-1" - should match the log with correlation_id="corr-1"
        result = populated_aggregator_service.query(
            page=1, page_size=10, search="corr-1"
        )

        # Should find the log with correlation_id containing "corr-1"
        assert len(result["logs"]) == 1
        assert "corr-1" in (result["logs"][0]["correlation_id"] or "")

    def test_search_is_case_insensitive(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that search is case-insensitive (AC1)."""
        # Search with uppercase
        result_upper = populated_aggregator_service.query(
            page=1, page_size=10, search="DEBUG"
        )
        # Search with lowercase
        result_lower = populated_aggregator_service.query(
            page=1, page_size=10, search="debug"
        )

        # Should return same results regardless of case
        assert len(result_upper["logs"]) == len(result_lower["logs"])
        assert len(result_upper["logs"]) == 2  # 2 debug messages in fixture

    def test_search_matches_partial_strings(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that search matches partial strings (substring search)."""
        # Search for "message" - should match all logs (all have "message" in text)
        result = populated_aggregator_service.query(
            page=1, page_size=20, search="message"
        )

        # Should find multiple logs containing "message"
        assert len(result["logs"]) >= 10  # All 10 logs have "message" in their text

    def test_search_returns_empty_for_no_matches(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that search returns empty results when no matches found."""
        # Search for something that doesn't exist
        result = populated_aggregator_service.query(
            page=1, page_size=10, search="nonexistent_term_xyz"
        )

        # Should return empty results
        assert len(result["logs"]) == 0
        assert result["pagination"]["total"] == 0

    def test_search_combines_with_level_filter(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that search can be combined with level filter (AC3)."""
        # Search for "message" AND filter by ERROR level
        result = populated_aggregator_service.query(
            page=1, page_size=10, search="Error", level="ERROR"
        )

        # Should only return ERROR logs containing "Error"
        assert len(result["logs"]) == 2  # 2 error messages in fixture
        for log in result["logs"]:
            assert log["level"] == "ERROR"
            assert "Error" in log["message"] or "error" in log["message"].lower()

    def test_search_empty_string_returns_all(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that empty search string returns all logs."""
        # Search with empty string
        result = populated_aggregator_service.query(page=1, page_size=20, search="")

        # Should return all logs
        assert len(result["logs"]) == 10


class TestLogAggregatorServiceMultipleLevelFiltering:
    """Test multiple level filtering functionality (Story #665 AC2)."""

    def test_filter_by_multiple_levels(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that can filter by multiple log levels (AC2)."""
        # Filter by ERROR and WARNING levels
        result = populated_aggregator_service.query(
            page=1, page_size=10, levels=["ERROR", "WARNING"]
        )

        # Should return logs matching either ERROR or WARNING
        assert len(result["logs"]) == 4  # 2 ERROR + 2 WARNING from fixture
        for log in result["logs"]:
            assert log["level"] in ["ERROR", "WARNING"]

    def test_filter_by_single_level_in_list(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that filtering with single level in list works."""
        # Filter by single level in list format
        result = populated_aggregator_service.query(
            page=1, page_size=10, levels=["ERROR"]
        )

        # Should return only ERROR logs
        assert len(result["logs"]) == 2
        for log in result["logs"]:
            assert log["level"] == "ERROR"

    def test_filter_by_all_levels(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that can filter by all available levels."""
        # Filter by all levels
        result = populated_aggregator_service.query(
            page=1,
            page_size=20,
            levels=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        )

        # Should return all logs
        assert len(result["logs"]) == 10

    def test_multiple_levels_combines_with_search(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that multiple levels can be combined with search (AC3)."""
        # Search for "message" AND filter by ERROR and WARNING
        result = populated_aggregator_service.query(
            page=1, page_size=10, search="message", levels=["ERROR", "WARNING"]
        )

        # Should return ERROR and WARNING logs containing "message"
        assert len(result["logs"]) == 4
        for log in result["logs"]:
            assert log["level"] in ["ERROR", "WARNING"]
            assert "message" in log["message"].lower()

    def test_empty_levels_list_returns_all(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that empty levels list returns all logs."""
        # Filter with empty levels list
        result = populated_aggregator_service.query(page=1, page_size=20, levels=[])

        # Should return all logs (no filtering)
        assert len(result["logs"]) == 10

    def test_backward_compatibility_with_single_level_param(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that old 'level' parameter still works for backward compatibility."""
        # Use old 'level' parameter (single string)
        result = populated_aggregator_service.query(page=1, page_size=10, level="ERROR")

        # Should return only ERROR logs
        assert len(result["logs"]) == 2
        for log in result["logs"]:
            assert log["level"] == "ERROR"


class TestLogAggregatorServiceQueryAll:
    """Test query_all() method for export functionality (Story #667)."""

    def test_query_all_returns_all_logs_without_pagination(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() returns all logs without pagination."""
        result = populated_aggregator_service.query_all()

        # Should return all 10 logs from fixture
        assert len(result) == 10
        assert isinstance(result, list)

    def test_query_all_returns_log_dicts_with_all_fields(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() returns log dicts with all required fields."""
        result = populated_aggregator_service.query_all()

        assert len(result) > 0

        # Check first log entry has all required fields
        log_entry = result[0]
        expected_keys = {
            "id",
            "timestamp",
            "level",
            "source",
            "message",
            "correlation_id",
            "user_id",
            "request_path",
        }
        assert expected_keys.issubset(set(log_entry.keys()))

    def test_query_all_respects_search_filter(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() respects search filter."""
        # Search for "Debug" - should match 2 debug messages
        result = populated_aggregator_service.query_all(search="Debug")

        assert len(result) == 2
        for log in result:
            assert "Debug" in log["message"] or "debug" in log["message"].lower()

    def test_query_all_respects_level_filter(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() respects level filter."""
        # Filter by ERROR level
        result = populated_aggregator_service.query_all(level="ERROR")

        assert len(result) == 2
        for log in result:
            assert log["level"] == "ERROR"

    def test_query_all_respects_levels_filter(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() respects multiple levels filter."""
        # Filter by ERROR and WARNING levels
        result = populated_aggregator_service.query_all(levels=["ERROR", "WARNING"])

        assert len(result) == 4  # 2 ERROR + 2 WARNING
        for log in result:
            assert log["level"] in ["ERROR", "WARNING"]

    def test_query_all_respects_correlation_id_filter(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() respects correlation_id filter."""
        result = populated_aggregator_service.query_all(correlation_id="corr-1")

        assert len(result) == 1
        assert result[0]["correlation_id"] == "corr-1"

    def test_query_all_respects_source_filter(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() respects source filter."""
        result = populated_aggregator_service.query_all(source="test.populated")

        # All logs in fixture have same source
        assert len(result) == 10
        for log in result:
            assert log["source"] == "test.populated"

    def test_query_all_combines_multiple_filters(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() combines multiple filters with AND logic."""
        # Search for "Error" AND filter by ERROR level
        result = populated_aggregator_service.query_all(search="Error", level="ERROR")

        assert len(result) == 2
        for log in result:
            assert log["level"] == "ERROR"
            assert "Error" in log["message"] or "error" in log["message"].lower()

    def test_query_all_returns_empty_list_for_empty_database(
        self, aggregator_service: LogAggregatorService
    ):
        """Test that query_all() handles empty database gracefully."""
        result = aggregator_service.query_all()

        assert result == []
        assert isinstance(result, list)

    def test_query_all_returns_empty_list_for_no_matches(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() returns empty list when no logs match filters."""
        result = populated_aggregator_service.query_all(search="nonexistent_xyz")

        assert result == []

    def test_query_all_respects_sort_order_desc(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() returns logs in descending order by default."""
        result = populated_aggregator_service.query_all()

        # Verify timestamps are in descending order (newest first)
        timestamps = [log["timestamp"] for log in result]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_query_all_respects_sort_order_asc(
        self, populated_aggregator_service: LogAggregatorService
    ):
        """Test that query_all() can return logs in ascending order."""
        result = populated_aggregator_service.query_all(sort_order="asc")

        # Verify timestamps are in ascending order (oldest first)
        timestamps = [log["timestamp"] for log in result]
        assert timestamps == sorted(timestamps)
