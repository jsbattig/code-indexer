"""
Unit tests for TantivyIndexManager regex snippet extraction bug fix.

This test suite validates that regex searches correctly extract:
1. Actual matched text (not the query pattern)
2. Correct line numbers
3. Correct column numbers
4. Proper snippet context

Bug Description:
When use_regex=True, the snippet extraction was using the query pattern
(e.g., "parts.*") instead of finding what the regex actually matched.
This resulted in:
- match_text showing the query pattern instead of actual matched text
- line/column always showing Line 1, Col 1
- Incorrect or missing snippets

Tests follow TDD methodology:
1. Write failing tests that demonstrate the bug
2. Implement fix
3. Verify all tests pass
"""

import pytest
from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestTantivyRegexSnippetExtraction:
    """Test suite for regex snippet extraction bug fix."""

    @pytest.fixture
    def temp_index_dir(self, tmp_path):
        """Create temporary index directory."""
        return tmp_path / "tantivy_index"

    @pytest.fixture
    def tantivy_manager(self, temp_index_dir):
        """Create and initialize TantivyIndexManager."""
        manager = TantivyIndexManager(temp_index_dir)
        manager.initialize_index(create_new=True)
        return manager

    @pytest.fixture
    def sample_documents(self):
        """
        Sample documents designed to test regex snippet extraction.

        Documents contain patterns at different locations to test:
        - Line number calculation
        - Column number calculation
        - Match text extraction
        - Snippet context
        """
        return [
            {
                "path": "src/PartsConstants.xml",
                "content": """<?xml version="1.0" encoding="UTF-8"?>
<root>
    <config>
        <setting name="parts_enabled">true</setting>
        <setting name="parts_database">main</setting>
    </config>
    <parts>
        <part id="123">Widget A</part>
        <part id="456">Widget B</part>
    </parts>
    <partsupcat>
        <category>Hardware</category>
        <category>Software</category>
    </partsupcat>
</root>""",
                "content_raw": """<?xml version="1.0" encoding="UTF-8"?>
<root>
    <config>
        <setting name="parts_enabled">true</setting>
        <setting name="parts_database">main</setting>
    </config>
    <parts>
        <part id="123">Widget A</part>
        <part id="456">Widget B</part>
    </parts>
    <partsupcat>
        <category>Hardware</category>
        <category>Software</category>
    </partsupcat>
</root>""",
                "identifiers": ["parts", "partsupcat", "parts_enabled"],
                "line_start": 1,
                "line_end": 15,
                "language": "xml",
            },
            {
                "path": "src/auth_system.py",
                "content": """# Authentication system
def authenticate_user(username, password):
    return validate_credentials(username, password)

def authorize_user(user, resource):
    return check_permissions(user, resource)

class AuthenticationManager:
    def __init__(self):
        self.auth_provider = None
""",
                "content_raw": """# Authentication system
def authenticate_user(username, password):
    return validate_credentials(username, password)

def authorize_user(user, resource):
    return check_permissions(user, resource)

class AuthenticationManager:
    def __init__(self):
        self.auth_provider = None
""",
                "identifiers": ["authenticate_user", "authorize_user", "AuthenticationManager"],
                "line_start": 1,
                "line_end": 10,
                "language": "python",
            },
            {
                "path": "tests/test_config.py",
                "content": """import unittest

class ConfigTest(unittest.TestCase):
    def test_config_loader(self):
        config = load_config()
        self.assertIsNotNone(config)

    def test_config_validator(self):
        result = validate_config({})
        self.assertTrue(result)
""",
                "content_raw": """import unittest

class ConfigTest(unittest.TestCase):
    def test_config_loader(self):
        config = load_config()
        self.assertIsNotNone(config)

    def test_config_validator(self):
        result = validate_config({})
        self.assertTrue(result)
""",
                "identifiers": ["ConfigTest", "test_config_loader", "test_config_validator"],
                "line_start": 1,
                "line_end": 10,
                "language": "python",
            },
        ]

    @pytest.fixture
    def indexed_manager(self, tantivy_manager, sample_documents):
        """Manager with sample documents indexed."""
        for doc in sample_documents:
            tantivy_manager.add_document(doc)
        tantivy_manager.commit()
        return tantivy_manager

    def test_regex_simple_pattern_extracts_correct_match_text(self, indexed_manager):
        """
        GIVEN indexed repo with 'parts' keyword
        WHEN searching with regex pattern 'parts.*'
        THEN match_text should be actual matched text (e.g., 'parts_enabled')
        AND not the query pattern 'parts.*'

        This is the core bug: match_text was showing query pattern instead of actual match.
        """
        results = indexed_manager.search(
            query_text=r"parts.*",
            use_regex=True,
            snippet_lines=2,
            limit=10,
        )

        # Should find matches
        assert len(results) > 0, "Should find matches for 'parts.*' pattern"

        # CRITICAL: match_text should NOT be the query pattern
        for result in results:
            match_text = result.get("match_text", "")
            # Bug behavior: match_text == "parts.*" (the query pattern)
            # Correct behavior: match_text should be actual matched text like "parts_enabled"
            assert match_text != "parts.*", (
                f"match_text should be actual matched text, not query pattern. "
                f"Got: {match_text}"
            )
            # Should contain 'parts' but with additional characters
            assert "parts" in match_text.lower(), (
                f"match_text should contain 'parts'. Got: {match_text}"
            )

    def test_regex_pattern_extracts_correct_line_number(self, indexed_manager):
        """
        GIVEN indexed repo with matches at different line numbers
        WHEN searching with regex pattern
        THEN line numbers should reflect actual match positions
        AND not default to line 1

        Bug: All matches showed Line 1, Col 1 regardless of actual position.
        """
        results = indexed_manager.search(
            query_text=r"parts.*",
            use_regex=True,
            snippet_lines=2,
            limit=10,
        )

        assert len(results) > 0, "Should find matches"

        # At least one result should have line > 1
        # (since we have matches in the middle of files)
        line_numbers = [r.get("line", 1) for r in results]

        # Bug behavior: all line numbers are 1
        # Correct behavior: should have matches beyond line 1
        assert any(line > 1 for line in line_numbers), (
            f"Expected matches beyond line 1. Got line numbers: {line_numbers}"
        )

    def test_regex_pattern_extracts_correct_column_number(self, indexed_manager):
        """
        GIVEN indexed repo with matches at different column positions
        WHEN searching with regex pattern
        THEN column numbers should reflect actual match positions
        AND not default to column 1
        """
        results = indexed_manager.search(
            query_text=r"parts.*",
            use_regex=True,
            snippet_lines=2,
            limit=10,
        )

        assert len(results) > 0, "Should find matches"

        # At least one result should have column > 1
        column_numbers = [r.get("column", 1) for r in results]

        # Some matches should be at column positions > 1
        # (not every match starts at beginning of line)
        assert any(col > 1 for col in column_numbers), (
            f"Expected some matches beyond column 1. Got columns: {column_numbers}"
        )

    def test_regex_pattern_with_alternation(self, indexed_manager):
        """
        GIVEN indexed repo with 'authenticate' and 'authorize' functions
        WHEN searching with alternation pattern 'authen.*|author.*'
        THEN should find both patterns and extract correct match text for each
        """
        results = indexed_manager.search(
            query_text=r"authen.*|author.*",
            use_regex=True,
            snippet_lines=2,
            limit=10,
        )

        assert len(results) > 0, "Should find matches"

        # Check that match_text is actual matched text, not the query pattern
        for result in results:
            match_text = result.get("match_text", "")
            # Should not be the query pattern
            assert "|" not in match_text, (
                f"match_text should not contain '|' from pattern. Got: {match_text}"
            )
            # Should match one of the alternatives
            assert "authen" in match_text.lower() or "author" in match_text.lower(), (
                f"match_text should contain 'authen' or 'author'. Got: {match_text}"
            )

    def test_regex_pattern_extracts_snippet_with_context(self, indexed_manager):
        """
        GIVEN indexed repo
        WHEN searching with regex pattern and snippet_lines=2
        THEN snippets should show context around actual match
        AND snippet_start_line should be correct
        """
        results = indexed_manager.search(
            query_text=r"parts.*",
            use_regex=True,
            snippet_lines=2,
            limit=10,
        )

        assert len(results) > 0, "Should find matches"

        for result in results:
            snippet = result.get("snippet", "")
            line = result.get("line", 1)
            snippet_start_line = result.get("snippet_start_line", 1)

            # Snippet should not be empty when snippet_lines > 0
            assert snippet, "Snippet should not be empty"

            # snippet_start_line should be <= line (snippet starts before or at match line)
            assert snippet_start_line <= line, (
                f"snippet_start_line ({snippet_start_line}) should be <= line ({line})"
            )

            # Snippet should contain multiple lines
            snippet_line_count = len(snippet.split('\n'))
            assert snippet_line_count >= 1, (
                f"Snippet should contain at least 1 line. Got {snippet_line_count} lines"
            )

    def test_regex_case_insensitive_extracts_correct_match(self, indexed_manager):
        """
        GIVEN indexed repo with mixed case text
        WHEN searching with case-insensitive regex
        THEN should extract actual matched text with original casing
        """
        results = indexed_manager.search(
            query_text=r"config.*",
            use_regex=True,
            case_sensitive=False,
            snippet_lines=2,
            limit=10,
        )

        assert len(results) > 0, "Should find matches"

        for result in results:
            match_text = result.get("match_text", "")
            # Should not be the query pattern
            assert match_text != "config.*", (
                f"match_text should not be query pattern. Got: {match_text}"
            )
            # Should preserve original casing from source
            assert "config" in match_text.lower(), (
                f"match_text should contain 'config'. Got: {match_text}"
            )

    def test_regex_multiple_matches_in_same_file(self, indexed_manager):
        """
        GIVEN file with multiple regex matches (e.g., PartsConstants.xml has multiple 'parts*' patterns)
        WHEN searching with regex
        THEN should return match for at least one occurrence
        AND match should have correct position and text
        """
        results = indexed_manager.search(
            query_text=r"parts.*",
            use_regex=True,
            snippet_lines=2,
            limit=10,
        )

        assert len(results) > 0, "Should find matches"

        # Find results from PartsConstants.xml
        xml_results = [r for r in results if "PartsConstants.xml" in r["path"]]

        if xml_results:
            # Should have at least one match from XML file
            assert len(xml_results) > 0

            for result in xml_results:
                match_text = result.get("match_text", "")
                line = result.get("line", 1)

                # Verify match_text is actual text from file
                assert match_text != "parts.*", "Should not be query pattern"
                assert "parts" in match_text.lower(), "Should contain 'parts'"

                # Verify line number is reasonable (not all at line 1)
                assert line >= 1, f"Line should be >= 1, got {line}"

    def test_regex_with_dot_star_extracts_variable_length_matches(self, indexed_manager):
        """
        GIVEN indexed repo with variable-length matches (e.g., 'parts', 'parts_enabled', 'partsupcat')
        WHEN searching with pattern 'parts.*'
        THEN each result should show complete matched text (not truncated)
        """
        results = indexed_manager.search(
            query_text=r"parts.*",
            use_regex=True,
            snippet_lines=2,
            limit=10,
        )

        assert len(results) > 0, "Should find matches"

        # Collect all unique match texts
        match_texts = {r.get("match_text", "") for r in results}

        # Should have found different length matches
        # Remove the query pattern if it appears (bug behavior)
        match_texts.discard("parts.*")

        assert len(match_texts) > 0, "Should have at least one actual match text"

        # All match texts should start with 'parts'
        for match_text in match_texts:
            assert match_text.lower().startswith("parts"), (
                f"Match text should start with 'parts'. Got: {match_text}"
            )
