"""Unit tests for QueryResultParser.

Tests parsing of real CIDX query output format into QueryResult objects.
The REAL format is: <score> <absolute_path>:<start>-<end>
Followed by indented code lines.
"""

import pytest
from code_indexer.proxy.query_parser import QueryResultParser


class TestQueryResultParser:
    """Test QueryResultParser with real CIDX output format."""

    def test_parse_single_result_real_format(self):
        """Test parsing a single result in real CIDX format."""
        output = """0.613 /home/user/repo/src/auth.py:1-115
  1: def authenticate(username, password):
  2:     return True"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/home/user/repo")

        assert len(results) == 1
        assert results[0].score == pytest.approx(0.613)
        assert results[0].file_path == "/home/user/repo/src/auth.py"
        assert results[0].line_range == (1, 115)
        assert results[0].repository == "/home/user/repo"
        assert "def authenticate" in results[0].content

    def test_parse_multiple_results_real_format(self):
        """Test parsing multiple results in real format."""
        output = """0.95 /home/user/repo/src/auth.py:10-50
  10: def login(user):
  11:     pass

0.85 /home/user/repo/tests/test_auth.py:5-20
  5: def test_login():
  6:     assert True"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/home/user/repo")

        assert len(results) == 2

        # First result
        assert results[0].score == pytest.approx(0.95)
        assert results[0].file_path == "/home/user/repo/src/auth.py"
        assert results[0].line_range == (10, 50)

        # Second result
        assert results[1].score == pytest.approx(0.85)
        assert results[1].file_path == "/home/user/repo/tests/test_auth.py"
        assert results[1].line_range == (5, 20)

    def test_parse_with_long_code_snippet(self):
        """Test parsing result with multi-line code content."""
        output = """0.88 /path/to/file.py:100-120
  100: class Authentication:
  101:     def __init__(self):
  102:         self.users = {}
  103:
  104:     def validate(self, token):
  105:         return token in self.users"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/path/to")

        assert len(results) == 1
        assert results[0].score == pytest.approx(0.88)
        assert "class Authentication:" in results[0].content
        assert "def validate" in results[0].content
        assert results[0].content.count("\n") >= 5

    def test_parse_score_with_leading_zero(self):
        """Test parsing scores like 0.XXX correctly."""
        output = """0.123 /file.py:1-10
  1: code"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert results[0].score == pytest.approx(0.123)

    def test_parse_score_without_leading_zero(self):
        """Test parsing scores like .XXX (no leading zero)."""
        output = """.789 /file.py:1-10
  1: code"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert results[0].score == pytest.approx(0.789)

    def test_parse_preserves_repository_context(self):
        """Test that repository path is preserved in results."""
        output = """0.9 /home/dev/backend/auth/src/login.py:50-75
  50: def authenticate():
  51:     pass"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/home/dev/backend/auth")

        assert len(results) == 1
        assert results[0].repository == "/home/dev/backend/auth"

    def test_parse_empty_output(self):
        """Test parsing empty output returns empty list."""
        parser = QueryResultParser()
        results = parser.parse_repository_output("", "/repo")

        assert results == []

    def test_parse_whitespace_only_output(self):
        """Test parsing whitespace-only output returns empty list."""
        parser = QueryResultParser()
        results = parser.parse_repository_output("   \n\n  ", "/repo")

        assert results == []

    def test_parse_malformed_line_skips_gracefully(self):
        """Test that malformed lines are skipped without crashing."""
        output = """0.9 /file.py:1-10
  1: good code
this is malformed garbage
not a valid result line
0.8 /other.py:5-15
  5: more good code"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        # Should parse the 2 valid results, skip malformed lines
        assert len(results) == 2
        assert results[0].score == pytest.approx(0.9)
        assert results[1].score == pytest.approx(0.8)

    def test_parse_missing_line_range(self):
        """Test handling output with missing line range (malformed)."""
        output = """0.9 /file.py
  1: code"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        # Should skip malformed result
        assert len(results) == 0

    def test_parse_invalid_score(self):
        """Test handling invalid score values."""
        output = """invalid /file.py:1-10
  1: code"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        # Should skip result with invalid score
        assert len(results) == 0

    def test_parse_negative_line_numbers(self):
        """Test handling negative line numbers (malformed)."""
        output = """0.9 /file.py:-5-10
  1: code"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        # Should skip result with invalid line numbers
        assert len(results) == 0

    def test_parse_reversed_line_range(self):
        """Test handling reversed line range (end < start)."""
        output = """0.9 /file.py:50-10
  1: code"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        # Should skip result with invalid range
        assert len(results) == 0

    def test_parse_code_with_special_characters(self):
        """Test parsing code content with special characters."""
        output = """0.9 /file.py:1-5
  1: def test():
  2:     x = "string with 'quotes'"
  3:     y = r"raw\\path\\here"
  4:     return True"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert "'quotes'" in results[0].content
        assert "raw\\path" in results[0].content

    def test_parse_code_with_unicode(self):
        """Test parsing code content with Unicode characters."""
        output = """0.9 /file.py:1-3
  1: # Comment with émojis 🎉
  2: def función():
  3:     return "Hëllö"
"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert "🎉" in results[0].content
        assert "función" in results[0].content
        assert "Hëllö" in results[0].content

    def test_parse_preserves_indentation(self):
        """Test that code indentation is preserved."""
        output = """0.9 /file.py:1-5
  1: def outer():
  2:     def inner():
  3:         return True
  4:     return inner()"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        # Verify indentation preserved in content
        assert "    def inner():" in results[0].content
        assert "        return True" in results[0].content

    def test_parse_file_path_with_spaces(self):
        """Test parsing file paths containing spaces."""
        output = """0.9 /home/user/my project/src/auth.py:1-10
  1: code here"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/home/user/my project")

        assert len(results) == 1
        assert results[0].file_path == "/home/user/my project/src/auth.py"

    def test_parse_large_line_numbers(self):
        """Test parsing large line numbers (e.g., files with 10000+ lines)."""
        output = """0.9 /file.py:9999-10050
  9999: def function():
  10000:     pass"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert results[0].line_range == (9999, 10050)

    def test_parse_single_line_result(self):
        """Test parsing result spanning single line."""
        output = """0.9 /file.py:42-42
  42: return True"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert results[0].line_range == (42, 42)

    def test_parse_result_without_content_lines(self):
        """Test parsing result header without content lines."""
        output = """0.9 /file.py:1-10"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        # Should still parse result, content may be empty
        assert len(results) == 1
        assert results[0].score == pytest.approx(0.9)
        assert results[0].file_path == "/file.py"

    def test_parse_consecutive_results_no_blank_lines(self):
        """Test parsing consecutive results without blank line separators."""
        output = """0.9 /file1.py:1-5
  1: code1
0.8 /file2.py:10-15
  10: code2"""

        parser = QueryResultParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 2
        assert results[0].score == pytest.approx(0.9)
        assert results[1].score == pytest.approx(0.8)
