"""Unit tests for SSE (Server-Sent Events) parser.

Tests SSE event parsing, chunk buffering, and error handling for streaming responses.
"""

import pytest

from code_indexer.mcpb.sse_parser import (
    SseParser,
    SseParseError,
    SseStreamError,
)


class TestSseParser:
    """Test SSE parser functionality."""

    def test_parser_initialization(self):
        """Test SSE parser initialization."""
        parser = SseParser()
        assert parser is not None

    def test_parse_chunk_event(self):
        """Test parsing a chunk event."""
        parser = SseParser()
        event_line = 'data: {"type": "chunk", "content": {"text": "result1"}}'

        event = parser.parse_event(event_line)

        assert event["type"] == "chunk"
        assert event["content"]["text"] == "result1"

    def test_parse_complete_event(self):
        """Test parsing a complete event."""
        parser = SseParser()
        event_line = 'data: {"type": "complete", "content": {"total": 10}}'

        event = parser.parse_event(event_line)

        assert event["type"] == "complete"
        assert event["content"]["total"] == 10

    def test_parse_error_event(self):
        """Test parsing an error event."""
        parser = SseParser()
        event_line = 'data: {"type": "error", "error": {"code": -32000, "message": "Test error"}}'

        event = parser.parse_event(event_line)

        assert event["type"] == "error"
        assert event["error"]["code"] == -32000
        assert event["error"]["message"] == "Test error"

    def test_parse_event_without_data_prefix_raises_error(self):
        """Test that parsing event without 'data: ' prefix raises error."""
        parser = SseParser()
        invalid_line = '{"type": "chunk", "content": {}}'

        with pytest.raises(SseParseError, match="Event line must start with 'data: '"):
            parser.parse_event(invalid_line)

    def test_parse_event_with_invalid_json_raises_error(self):
        """Test that parsing event with invalid JSON raises error."""
        parser = SseParser()
        invalid_line = "data: {invalid json}"

        with pytest.raises(SseParseError, match="Invalid JSON in SSE event"):
            parser.parse_event(invalid_line)

    def test_parse_event_without_type_field_raises_error(self):
        """Test that parsing event without type field raises error."""
        parser = SseParser()
        invalid_line = 'data: {"content": {}}'

        with pytest.raises(SseParseError, match="SSE event missing 'type' field"):
            parser.parse_event(invalid_line)

    def test_buffer_chunks(self):
        """Test buffering multiple chunk events."""
        parser = SseParser()

        parser.buffer_chunk({"file": "test1.py", "score": 0.9})
        parser.buffer_chunk({"file": "test2.py", "score": 0.8})

        assert len(parser.get_buffered_chunks()) == 2
        assert parser.get_buffered_chunks()[0]["file"] == "test1.py"
        assert parser.get_buffered_chunks()[1]["file"] == "test2.py"

    def test_assemble_results_combines_chunks_with_metadata(self):
        """Test assembling final results from buffered chunks and metadata."""
        parser = SseParser()

        parser.buffer_chunk({"file": "test1.py", "score": 0.9})
        parser.buffer_chunk({"file": "test2.py", "score": 0.8})

        metadata = {"total_files": 2, "query_time_ms": 50}
        result = parser.assemble_results(metadata)

        assert "chunks" in result
        assert len(result["chunks"]) == 2
        assert result["total_files"] == 2
        assert result["query_time_ms"] == 50

    def test_clear_buffer_removes_all_chunks(self):
        """Test clearing buffer removes all buffered chunks."""
        parser = SseParser()

        parser.buffer_chunk({"file": "test1.py"})
        parser.buffer_chunk({"file": "test2.py"})
        assert len(parser.get_buffered_chunks()) == 2

        parser.clear_buffer()
        assert len(parser.get_buffered_chunks()) == 0


class TestSseEventProcessing:
    """Test SSE event processing workflow."""

    def test_process_stream_with_chunks_and_complete(self):
        """Test processing a complete SSE stream."""
        parser = SseParser()

        # Simulate stream of events
        events = [
            'data: {"type": "chunk", "content": {"file": "file1.py", "score": 0.9}}',
            'data: {"type": "chunk", "content": {"file": "file2.py", "score": 0.8}}',
            'data: {"type": "complete", "content": {"total": 2}}',
        ]

        result = None
        for event_line in events:
            event = parser.parse_event(event_line)

            if event["type"] == "chunk":
                parser.buffer_chunk(event["content"])
            elif event["type"] == "complete":
                result = parser.assemble_results(event["content"])
                break

        assert result is not None
        assert len(result["chunks"]) == 2
        assert result["total"] == 2
        assert result["chunks"][0]["file"] == "file1.py"

    def test_process_stream_with_error_event(self):
        """Test processing SSE stream that ends with error."""
        parser = SseParser()

        events = [
            'data: {"type": "chunk", "content": {"file": "file1.py"}}',
            'data: {"type": "error", "error": {"code": -32000, "message": "Query failed"}}',
        ]

        error = None
        for event_line in events:
            event = parser.parse_event(event_line)

            if event["type"] == "chunk":
                parser.buffer_chunk(event["content"])
            elif event["type"] == "error":
                error = event["error"]
                break

        assert error is not None
        assert error["code"] == -32000
        assert error["message"] == "Query failed"

    def test_empty_stream_raises_error(self):
        """Test that empty stream (no events) is handled."""
        parser = SseParser()

        # No events processed
        # Stream terminated without complete event

        with pytest.raises(SseStreamError, match="Stream terminated unexpectedly"):
            parser.validate_stream_completed()

    def test_stream_without_complete_event_raises_error(self):
        """Test that stream without complete event raises error."""
        parser = SseParser()

        events = [
            'data: {"type": "chunk", "content": {"file": "file1.py"}}',
            # Stream ends here without complete event
        ]

        for event_line in events:
            event = parser.parse_event(event_line)
            if event["type"] == "chunk":
                parser.buffer_chunk(event["content"])

        with pytest.raises(SseStreamError, match="Stream terminated unexpectedly"):
            parser.validate_stream_completed()


class TestSseParserEdgeCases:
    """Test SSE parser edge cases."""

    def test_parse_event_with_extra_whitespace(self):
        """Test parsing event with extra whitespace is handled."""
        parser = SseParser()
        event_line = 'data:   {"type": "chunk", "content": {}}  '

        event = parser.parse_event(event_line)
        assert event["type"] == "chunk"

    def test_parse_empty_line_raises_error(self):
        """Test that empty line raises error."""
        parser = SseParser()

        with pytest.raises(SseParseError, match="Event line must start with 'data: '"):
            parser.parse_event("")

    def test_parse_line_with_only_data_prefix_raises_error(self):
        """Test that line with only 'data: ' prefix raises error."""
        parser = SseParser()

        with pytest.raises(SseParseError, match="Invalid JSON in SSE event"):
            parser.parse_event("data: ")

    def test_buffer_none_chunk_raises_error(self):
        """Test that buffering None chunk raises error."""
        parser = SseParser()

        with pytest.raises(ValueError, match="Cannot buffer None chunk"):
            parser.buffer_chunk(None)  # type: ignore

    def test_assemble_results_with_empty_metadata(self):
        """Test assembling results with empty metadata."""
        parser = SseParser()

        parser.buffer_chunk({"file": "test.py"})
        result = parser.assemble_results({})

        assert "chunks" in result
        assert len(result["chunks"]) == 1
