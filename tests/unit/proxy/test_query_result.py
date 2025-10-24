"""Unit tests for QueryResult dataclass.

Tests the QueryResult structure used to represent semantic search results
from individual repositories with proper metadata preservation.
"""

import pytest
from dataclasses import asdict

from code_indexer.proxy.query_result import QueryResult


class TestQueryResultDataclass:
    """Test QueryResult dataclass structure and properties."""

    def test_create_query_result(self):
        """Test creating a basic QueryResult instance."""
        result = QueryResult(
            score=0.85,
            file_path="/home/user/repo/src/auth.py",
            line_range=(10, 50),
            content="def authenticate(user):\n    pass",
            repository="/home/user/repo"
        )

        assert result.score == 0.85
        assert result.file_path == "/home/user/repo/src/auth.py"
        assert result.line_range == (10, 50)
        assert result.content == "def authenticate(user):\n    pass"
        assert result.repository == "/home/user/repo"

    def test_query_result_with_minimal_fields(self):
        """Test QueryResult with only required fields."""
        result = QueryResult(
            score=0.95,
            file_path="/path/to/file.py",
            line_range=(1, 10),
            content="code here",
            repository="/path/to/repo"
        )

        assert result.score == 0.95
        assert result.file_path == "/path/to/file.py"

    def test_query_result_score_precision(self):
        """Test that score maintains float precision."""
        result = QueryResult(
            score=0.123456,
            file_path="/file.py",
            line_range=(1, 5),
            content="x",
            repository="/repo"
        )

        assert result.score == pytest.approx(0.123456)

    def test_query_result_line_range_tuple(self):
        """Test that line_range is stored as tuple."""
        result = QueryResult(
            score=0.9,
            file_path="/file.py",
            line_range=(100, 200),
            content="code",
            repository="/repo"
        )

        assert isinstance(result.line_range, tuple)
        assert result.line_range[0] == 100
        assert result.line_range[1] == 200

    def test_query_result_multiline_content(self):
        """Test QueryResult with multi-line code content."""
        content = """  1: def function():
  2:     return True
  3: """

        result = QueryResult(
            score=0.88,
            file_path="/code.py",
            line_range=(1, 3),
            content=content,
            repository="/repo"
        )

        assert "\n" in result.content
        assert result.content == content

    def test_query_result_equality(self):
        """Test QueryResult equality comparison."""
        result1 = QueryResult(
            score=0.9,
            file_path="/file.py",
            line_range=(1, 10),
            content="code",
            repository="/repo"
        )

        result2 = QueryResult(
            score=0.9,
            file_path="/file.py",
            line_range=(1, 10),
            content="code",
            repository="/repo"
        )

        assert result1 == result2

    def test_query_result_inequality_different_score(self):
        """Test QueryResult inequality when scores differ."""
        result1 = QueryResult(
            score=0.9,
            file_path="/file.py",
            line_range=(1, 10),
            content="code",
            repository="/repo"
        )

        result2 = QueryResult(
            score=0.8,
            file_path="/file.py",
            line_range=(1, 10),
            content="code",
            repository="/repo"
        )

        assert result1 != result2

    def test_query_result_inequality_different_repository(self):
        """Test QueryResult inequality when repositories differ."""
        result1 = QueryResult(
            score=0.9,
            file_path="/file.py",
            line_range=(1, 10),
            content="code",
            repository="/repo1"
        )

        result2 = QueryResult(
            score=0.9,
            file_path="/file.py",
            line_range=(1, 10),
            content="code",
            repository="/repo2"
        )

        assert result1 != result2

    def test_query_result_to_dict(self):
        """Test converting QueryResult to dictionary."""
        result = QueryResult(
            score=0.75,
            file_path="/src/test.py",
            line_range=(5, 15),
            content="test code",
            repository="/test/repo"
        )

        result_dict = asdict(result)

        assert result_dict['score'] == 0.75
        assert result_dict['file_path'] == "/src/test.py"
        assert result_dict['line_range'] == (5, 15)
        assert result_dict['content'] == "test code"
        assert result_dict['repository'] == "/test/repo"

    def test_query_result_repr(self):
        """Test QueryResult string representation."""
        result = QueryResult(
            score=0.92,
            file_path="/path/file.py",
            line_range=(10, 20),
            content="x",
            repository="/repo"
        )

        repr_str = repr(result)

        assert "QueryResult" in repr_str
        assert "0.92" in repr_str
        assert "/path/file.py" in repr_str
