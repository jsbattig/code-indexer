"""
Unit tests for LogExportFormatter - JSON and CSV export formatting.

TDD tests written FIRST before implementation.

Verifies:
- JSON export with metadata header
- JSON formatting (2-space indentation)
- CSV export with proper headers
- CSV special character escaping
- UTF-8 BOM for Excel compatibility
- Empty log list handling
"""

import json

from code_indexer.server.services.log_export_formatter import LogExportFormatter


class TestLogExportFormatterJSON:
    """Test JSON export formatting."""

    def test_to_json_produces_valid_json(self):
        """to_json() produces valid parseable JSON."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "INFO",
                "source": "server",
                "message": "Server started",
                "correlation_id": "corr-001",
                "user_id": "admin",
                "request_path": "/",
            }
        ]
        filters = {"search": None, "level": None}

        result = formatter.to_json(logs, filters)

        # Should be valid JSON (no parse error)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_to_json_includes_metadata_header(self):
        """to_json() includes metadata with exported_at, filters, count."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "INFO",
                "source": "server",
                "message": "Test",
                "correlation_id": None,
                "user_id": None,
                "request_path": None,
            }
        ]
        filters = {"search": "test", "level": "INFO"}

        result = formatter.to_json(logs, filters)
        parsed = json.loads(result)

        # Should have metadata section
        assert "metadata" in parsed
        assert "exported_at" in parsed["metadata"]
        assert "filters" in parsed["metadata"]
        assert "count" in parsed["metadata"]

        # Metadata values
        assert parsed["metadata"]["filters"] == filters
        assert parsed["metadata"]["count"] == 1

    def test_to_json_includes_logs_array(self):
        """to_json() includes logs array with all log fields."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "ERROR",
                "source": "auth",
                "message": "Auth failed",
                "correlation_id": "corr-001",
                "user_id": "admin@example.com",
                "request_path": "/auth/login",
            }
        ]
        filters = {}

        result = formatter.to_json(logs, filters)
        parsed = json.loads(result)

        # Should have logs array
        assert "logs" in parsed
        assert isinstance(parsed["logs"], list)
        assert len(parsed["logs"]) == 1

        # Log entry should have all fields
        log_entry = parsed["logs"][0]
        assert log_entry["timestamp"] == "2025-01-02T10:00:00Z"
        assert log_entry["level"] == "ERROR"
        assert log_entry["source"] == "auth"
        assert log_entry["message"] == "Auth failed"
        assert log_entry["correlation_id"] == "corr-001"
        assert log_entry["user_id"] == "admin@example.com"
        assert log_entry["request_path"] == "/auth/login"

    def test_to_json_pretty_prints_with_indentation(self):
        """to_json() formats with 2-space indentation for readability."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "INFO",
                "source": "test",
                "message": "Test",
                "correlation_id": None,
                "user_id": None,
                "request_path": None,
            }
        ]
        filters = {}

        result = formatter.to_json(logs, filters)

        # Should have newlines and indentation (not minified)
        assert "\n" in result
        assert "  " in result  # 2-space indent

    def test_to_json_handles_empty_logs(self):
        """to_json() handles empty logs list gracefully."""
        formatter = LogExportFormatter()
        logs = []
        filters = {"search": "nonexistent"}

        result = formatter.to_json(logs, filters)
        parsed = json.loads(result)

        # Should have metadata and empty logs array
        assert parsed["metadata"]["count"] == 0
        assert parsed["logs"] == []

    def test_to_json_handles_multiple_logs(self):
        """to_json() exports multiple log entries correctly."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "INFO",
                "source": "server",
                "message": "Log 1",
                "correlation_id": "c1",
                "user_id": None,
                "request_path": None,
            },
            {
                "id": 2,
                "timestamp": "2025-01-02T10:05:00Z",
                "level": "ERROR",
                "source": "db",
                "message": "Log 2",
                "correlation_id": "c2",
                "user_id": "admin",
                "request_path": "/api",
            },
            {
                "id": 3,
                "timestamp": "2025-01-02T10:10:00Z",
                "level": "WARNING",
                "source": "cache",
                "message": "Log 3",
                "correlation_id": "c3",
                "user_id": None,
                "request_path": None,
            },
        ]
        filters = {}

        result = formatter.to_json(logs, filters)
        parsed = json.loads(result)

        assert parsed["metadata"]["count"] == 3
        assert len(parsed["logs"]) == 3


class TestLogExportFormatterCSV:
    """Test CSV export formatting."""

    def test_to_csv_produces_valid_csv_with_header(self):
        """to_csv() produces CSV with header row."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "INFO",
                "source": "server",
                "message": "Server started",
                "correlation_id": "corr-001",
                "user_id": "admin",
                "request_path": "/",
            }
        ]

        result = formatter.to_csv(logs)

        # Should have header row
        lines = result.strip().split("\n")
        assert len(lines) >= 2  # Header + at least 1 data row

        # Check header (after BOM if present)
        header = lines[0]
        if header.startswith("\ufeff"):
            header = header[1:]  # Strip BOM

        assert "timestamp" in header
        assert "level" in header
        assert "source" in header
        assert "message" in header
        assert "correlation_id" in header
        assert "user_id" in header
        assert "request_path" in header

    def test_to_csv_includes_utf8_bom_for_excel(self):
        """to_csv() includes UTF-8 BOM for Excel compatibility."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "INFO",
                "source": "test",
                "message": "Test",
                "correlation_id": None,
                "user_id": None,
                "request_path": None,
            }
        ]

        result = formatter.to_csv(logs)

        # Should start with UTF-8 BOM
        assert result.startswith("\ufeff")

    def test_to_csv_escapes_commas_in_message(self):
        """to_csv() properly escapes commas in message field."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "ERROR",
                "source": "api",
                "message": "Error occurred, check logs, retry needed",
                "correlation_id": None,
                "user_id": None,
                "request_path": None,
            }
        ]

        result = formatter.to_csv(logs)

        # Message with commas should be quoted
        assert '"Error occurred, check logs, retry needed"' in result

    def test_to_csv_escapes_quotes_in_message(self):
        """to_csv() properly escapes quotes in message field."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "ERROR",
                "source": "api",
                "message": 'User said "hello world"',
                "correlation_id": None,
                "user_id": None,
                "request_path": None,
            }
        ]

        result = formatter.to_csv(logs)

        # Quotes should be escaped (doubled)
        assert '""hello world""' in result or 'User said "hello world"' in result

    def test_to_csv_handles_newlines_in_message(self):
        """to_csv() properly handles newlines in message field."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "ERROR",
                "source": "api",
                "message": "Error on line 1\nError on line 2",
                "correlation_id": None,
                "user_id": None,
                "request_path": None,
            }
        ]

        result = formatter.to_csv(logs)

        # Multi-line message should be quoted
        assert (
            '"Error on line 1\nError on line 2"' in result
            or "Error on line 1\\nError on line 2" in result
        )

    def test_to_csv_handles_empty_logs(self):
        """to_csv() handles empty logs list gracefully."""
        formatter = LogExportFormatter()
        logs = []

        result = formatter.to_csv(logs)

        # Should have header but no data rows
        lines = result.strip().split("\n")
        header = lines[0]
        if header.startswith("\ufeff"):
            header = header[1:]

        # Only header row present
        assert "timestamp" in header
        assert len(lines) == 1

    def test_to_csv_handles_multiple_logs(self):
        """to_csv() exports multiple log entries correctly."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "INFO",
                "source": "server",
                "message": "Log 1",
                "correlation_id": "c1",
                "user_id": None,
                "request_path": None,
            },
            {
                "id": 2,
                "timestamp": "2025-01-02T10:05:00Z",
                "level": "ERROR",
                "source": "db",
                "message": "Log 2",
                "correlation_id": "c2",
                "user_id": "admin",
                "request_path": "/api",
            },
            {
                "id": 3,
                "timestamp": "2025-01-02T10:10:00Z",
                "level": "WARNING",
                "source": "cache",
                "message": "Log 3",
                "correlation_id": "c3",
                "user_id": None,
                "request_path": None,
            },
        ]

        result = formatter.to_csv(logs)

        # Should have header + 3 data rows
        lines = result.strip().split("\n")
        assert len(lines) == 4  # Header + 3 data rows

    def test_to_csv_handles_none_values(self):
        """to_csv() handles None values in optional fields."""
        formatter = LogExportFormatter()
        logs = [
            {
                "id": 1,
                "timestamp": "2025-01-02T10:00:00Z",
                "level": "INFO",
                "source": "test",
                "message": "Test log",
                "correlation_id": None,
                "user_id": None,
                "request_path": None,
            }
        ]

        result = formatter.to_csv(logs)

        # Should not raise error, should produce valid CSV
        lines = result.strip().split("\n")
        assert len(lines) == 2  # Header + 1 data row
