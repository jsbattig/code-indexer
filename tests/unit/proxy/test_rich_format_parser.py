"""Unit tests for RichFormatParser.

Tests parsing of CIDX rich query output format (non-quiet mode) into QueryResult
objects with full metadata preservation.

Rich format includes:
- File path, language, score
- Size, timestamp, branch, commit, project
- Content with line numbers
"""

import pytest
from code_indexer.proxy.rich_format_parser import RichFormatParser


class TestRichFormatParser:
    """Test RichFormatParser with rich (non-quiet) CIDX output format."""

    def test_parse_single_result_rich_format(self):
        """Test parsing a single result in rich format with full metadata."""
        output = """📄 File: /home/user/repo/src/auth.py:1-115 | 🏷️  Language: py | 📊 Score: 0.613
📏 Size: 5432 bytes | 🕒 Indexed: 2025-09-29T20:03:20.489657+00:00Z | 🌿 Branch: master | 📦 Commit: b99efecc... | 🏗️  Project: backend

📖 Content (Lines 1-115):
──────────────────────────────────────────────────
  1: def authenticate(username, password):
  2:     return True"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/home/user/repo")

        assert len(results) == 1
        result = results[0]

        # Core attributes
        assert result.score == pytest.approx(0.613)
        assert result.file_path == "/home/user/repo/src/auth.py"
        assert result.line_range == (1, 115)
        assert result.repository == "/home/user/repo"

        # Rich metadata
        assert result.language == "py"
        assert result.size == 5432
        assert result.indexed_timestamp == "2025-09-29T20:03:20.489657+00:00Z"
        assert result.branch == "master"
        assert result.commit == "b99efecc..."
        assert result.project_name == "backend"

        # Content
        assert "def authenticate" in result.content

    def test_parse_multiple_results_rich_format(self):
        """Test parsing multiple results in rich format."""
        output = """📄 File: /home/user/repo/src/auth.py:10-50 | 🏷️  Language: py | 📊 Score: 0.95
📏 Size: 2000 bytes | 🕒 Indexed: 2025-09-29T20:03:20Z | 🌿 Branch: master | 📦 Commit: abc123... | 🏗️  Project: backend

📖 Content (Lines 10-50):
──────────────────────────────────────────────────
  10: def login(user):
  11:     pass

================================================================================

📄 File: /home/user/repo/tests/test_auth.py:5-20 | 🏷️  Language: py | 📊 Score: 0.85
📏 Size: 1500 bytes | 🕒 Indexed: 2025-09-29T19:00:00Z | 🌿 Branch: develop | 📦 Commit: def456... | 🏗️  Project: backend

📖 Content (Lines 5-20):
──────────────────────────────────────────────────
  5: def test_login():
  6:     assert True"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/home/user/repo")

        assert len(results) == 2

        # First result
        assert results[0].score == pytest.approx(0.95)
        assert results[0].file_path == "/home/user/repo/src/auth.py"
        assert results[0].branch == "master"
        assert results[0].commit == "abc123..."

        # Second result
        assert results[1].score == pytest.approx(0.85)
        assert results[1].file_path == "/home/user/repo/tests/test_auth.py"
        assert results[1].branch == "develop"
        assert results[1].commit == "def456..."

    def test_parse_preserves_repository_context(self):
        """Test that repository path is preserved in results."""
        output = """📄 File: /home/dev/backend/src/login.py:50-75 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 3000 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: main | 📦 Commit: xyz789... | 🏗️  Project: auth

📖 Content (Lines 50-75):
──────────────────────────────────────────────────
  50: def authenticate():
  51:     pass"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/home/dev/backend")

        assert len(results) == 1
        assert results[0].repository == "/home/dev/backend"

    def test_parse_empty_output(self):
        """Test parsing empty output returns empty list."""
        parser = RichFormatParser()
        results = parser.parse_repository_output("", "/repo")

        assert results == []

    def test_parse_malformed_line_skips_gracefully(self):
        """Test that malformed lines are skipped without crashing."""
        output = """📄 File: /file.py:1-10 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 1000 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: good code

this is malformed garbage
not a valid result line

📄 File: /other.py:5-15 | 🏷️  Language: py | 📊 Score: 0.8
📏 Size: 2000 bytes | 🕒 Indexed: 2025-09-29T19:00:00Z | 🌿 Branch: dev | 📦 Commit: def... | 🏗️  Project: test

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: more good code"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/repo")

        # Should parse the 2 valid results, skip malformed lines
        assert len(results) == 2
        assert results[0].score == pytest.approx(0.9)
        assert results[1].score == pytest.approx(0.8)

    def test_parse_with_unicode_content(self):
        """Test parsing code content with Unicode characters."""
        output = """📄 File: /file.py:1-3 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 500 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-3):
──────────────────────────────────────────────────
  1: # Comment with émojis 🎉
  2: def función():
  3:     return "Hëllö"
"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert "🎉" in results[0].content
        assert "función" in results[0].content
        assert "Hëllö" in results[0].content

    def test_parse_file_path_with_spaces(self):
        """Test parsing file paths containing spaces."""
        output = """📄 File: /home/user/my project/src/auth.py:1-10 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 1000 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: code here"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/home/user/my project")

        assert len(results) == 1
        assert results[0].file_path == "/home/user/my project/src/auth.py"

    def test_parse_different_languages(self):
        """Test parsing results with different programming languages."""
        output = """📄 File: /repo/script.js:1-10 | 🏷️  Language: js | 📊 Score: 0.9
📏 Size: 1000 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: function test() {}

================================================================================

📄 File: /repo/util.rs:5-15 | 🏷️  Language: rust | 📊 Score: 0.8
📏 Size: 2000 bytes | 🕒 Indexed: 2025-09-29T19:00:00Z | 🌿 Branch: master | 📦 Commit: def... | 🏗️  Project: test

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: fn main() {}"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 2
        assert results[0].language == "js"
        assert results[1].language == "rust"

    def test_parse_large_file_sizes(self):
        """Test parsing results with large file sizes."""
        output = """📄 File: /repo/big.py:1-10000 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 1234567 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-10000):
──────────────────────────────────────────────────
  1: code"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert results[0].size == 1234567
        assert results[0].line_range == (1, 10000)

    def test_parse_preserves_indentation(self):
        """Test that code indentation is preserved."""
        output = """📄 File: /file.py:1-5 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 500 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-5):
──────────────────────────────────────────────────
  1: def outer():
  2:     def inner():
  3:         return True
  4:     return inner()"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        # Verify indentation preserved in content
        assert "    def inner():" in results[0].content
        assert "        return True" in results[0].content

    def test_parse_result_separator(self):
        """Test that result separator line is handled correctly."""
        output = """📄 File: /file1.py:1-5 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 500 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-5):
──────────────────────────────────────────────────
  1: code1

================================================================================

📄 File: /file2.py:10-15 | 🏷️  Language: py | 📊 Score: 0.8
📏 Size: 600 bytes | 🕒 Indexed: 2025-09-29T19:00:00Z | 🌿 Branch: dev | 📦 Commit: def... | 🏗️  Project: test

📖 Content (Lines 10-15):
──────────────────────────────────────────────────
  10: code2"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 2
        assert results[0].score == pytest.approx(0.9)
        assert results[1].score == pytest.approx(0.8)

    def test_parse_missing_optional_metadata(self):
        """Test handling results with missing optional metadata fields."""
        # Some fields might be missing in edge cases
        output = """📄 File: /file.py:1-10 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 1000 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: code"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/repo")

        # Should parse successfully even if some metadata missing
        assert len(results) == 1
        assert results[0].score == pytest.approx(0.9)

    def test_parse_long_content(self):
        """Test parsing result with many lines of content."""
        content_lines = "\n".join([f"  {i}: line {i}" for i in range(1, 101)])
        output = f"""📄 File: /file.py:1-100 | 🏷️  Language: py | 📊 Score: 0.9
📏 Size: 5000 bytes | 🕒 Indexed: 2025-09-29T20:00:00Z | 🌿 Branch: master | 📦 Commit: abc... | 🏗️  Project: test

📖 Content (Lines 1-100):
──────────────────────────────────────────────────
{content_lines}"""

        parser = RichFormatParser()
        results = parser.parse_repository_output(output, "/repo")

        assert len(results) == 1
        assert results[0].line_range == (1, 100)
        assert results[0].content.count("\n") >= 99  # 100 lines = 99 newlines minimum
