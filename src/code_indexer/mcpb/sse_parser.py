"""SSE (Server-Sent Events) parser for streaming responses.

This module handles parsing SSE event streams, buffering chunks,
and assembling final results from streamed data.
"""

import json
from typing import Any


class SseParseError(Exception):
    """SSE event parsing error."""

    pass


class SseStreamError(Exception):
    """SSE stream processing error."""

    pass


class SseParser:
    """Parser for SSE (Server-Sent Events) format.

    Handles parsing individual SSE events, buffering chunks,
    and assembling final results.
    """

    def __init__(self) -> None:
        """Initialize SSE parser with empty buffer."""
        self._buffer: list[dict[str, Any]] = []
        self._completed: bool = False

    def parse_event(self, line: str) -> dict[str, Any]:
        """Parse a single SSE event line.

        Args:
            line: SSE event line (format: "data: {json}")

        Returns:
            Parsed event as dictionary

        Raises:
            SseParseError: If line format is invalid or JSON is malformed
        """
        # Validate line starts with "data: "
        if not line.strip().startswith("data:"):
            raise SseParseError("Event line must start with 'data: '")

        # Extract JSON part after "data: " prefix
        json_part = line.strip()[5:].strip()

        # Parse JSON
        try:
            event = json.loads(json_part)
        except json.JSONDecodeError as e:
            raise SseParseError(f"Invalid JSON in SSE event: {e}") from e

        # Validate event has type field
        if "type" not in event:
            raise SseParseError("SSE event missing 'type' field")

        # Type narrowing for mypy
        parsed_event: dict[str, Any] = event
        return parsed_event

    def buffer_chunk(self, chunk: dict[str, Any]) -> None:
        """Buffer a chunk from a chunk event.

        Args:
            chunk: Chunk data to buffer

        Raises:
            ValueError: If chunk is None
        """
        if chunk is None:
            raise ValueError("Cannot buffer None chunk")

        self._buffer.append(chunk)

    def get_buffered_chunks(self) -> list[dict[str, Any]]:
        """Get all buffered chunks.

        Returns:
            List of buffered chunks
        """
        return self._buffer.copy()

    def assemble_results(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Assemble final result from buffered chunks and metadata.

        Args:
            metadata: Metadata from complete event

        Returns:
            Final result dictionary with chunks and metadata
        """
        result = {"chunks": self._buffer.copy()}
        result.update(metadata)
        self._completed = True
        return result

    def clear_buffer(self) -> None:
        """Clear all buffered chunks."""
        self._buffer.clear()
        self._completed = False

    def validate_stream_completed(self) -> None:
        """Validate that stream completed successfully.

        Raises:
            SseStreamError: If stream did not complete
        """
        if not self._completed:
            raise SseStreamError("Stream terminated unexpectedly")
