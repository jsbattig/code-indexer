"""Unit tests for error formatter JSON serialization helpers.

Tests _serialize_value_for_json function to ensure all common Python types
are properly converted to JSON-serializable values.
"""

import json
from pathlib import Path
from datetime import datetime

from src.code_indexer.server.middleware.error_formatters import (
    _serialize_value_for_json,
)


def test_serialize_path_object():
    """_serialize_value_for_json should handle Path objects"""
    path = Path("/home/user/test.txt")
    result = _serialize_value_for_json(path)

    assert isinstance(result, str)
    assert result == "/home/user/test.txt"


def test_serialize_nested_structure_with_path_and_datetime():
    """Handle complex structures with both Path and datetime"""
    data = {
        "file_path": Path("/tmp/test.txt"),
        "created_at": datetime(2025, 11, 13, 12, 0, 0),
        "nested": {
            "paths": [Path("/a"), Path("/b")],
            "timestamp": datetime(2025, 11, 13, 13, 0, 0),
        },
    }

    result = _serialize_value_for_json(data)

    # All should be serializable
    _ = json.dumps(result)  # Should not raise TypeError

    # Verify conversions
    assert result["file_path"] == "/tmp/test.txt"
    assert result["created_at"] == "2025-11-13T12:00:00"
    assert result["nested"]["paths"] == ["/a", "/b"]
    assert result["nested"]["timestamp"] == "2025-11-13T13:00:00"
