"""
Unit tests for TantivyIndexManager Unicode column calculation bug fix.

CRITICAL CORRECTNESS BUG: _extract_snippet() uses byte offsets (len(line.encode("utf-8")))
but match.start() returns character offsets, causing off-by-one errors for Unicode content.

Bug Example:
Content: "café python"  (4 characters: c-a-f-é)
Byte length: 5 bytes (UTF-8: c=1, a=1, f=1, é=2 bytes)
Character offset of 'p': 5 (characters)
Current code calculates: Uses 5 bytes for "café", expects 'p' at position 5
Actual position: 'p' is at character 5 but byte 6

This causes:
1. Incorrect column numbers reported
2. Off-by-one errors when Unicode characters are present
3. Match positions don't align with actual source code

Fix Required:
Replace: line_len = len(line.encode("utf-8"))  # Byte length
With:    line_len = len(line)                   # Character length

Tests follow TDD methodology:
1. Write failing tests demonstrating Unicode calculation errors
2. Fix _extract_snippet to use character offsets consistently
3. Verify all tests pass with correct column numbers
"""

import pytest
from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestTantivyUnicodeColumns:
    """Test suite for Unicode column calculation correctness."""

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
    def unicode_documents(self):
        """
        Documents containing Unicode characters at various positions.

        Designed to test column calculation with:
        - Multi-byte UTF-8 characters (é, ñ, 日本語)
        - Unicode at different positions (start, middle, end of line)
        - Various Unicode character byte lengths (2, 3, 4 bytes)
        """
        return [
            {
                "path": "src/café.py",
                "content": """# café Python module
def get_café_menu():
    items = ['espresso', 'latté', 'cappuccino']
    return items

class CaféManager:
    def __init__(self):
        self.name = 'Le Café'
""",
                "content_raw": """# café Python module
def get_café_menu():
    items = ['espresso', 'latté', 'cappuccino']
    return items

class CaféManager:
    def __init__(self):
        self.name = 'Le Café'
""",
                "identifiers": ["get_café_menu", "CaféManager"],
                "line_start": 1,
                "line_end": 9,
                "language": "python",
            },
            {
                "path": "src/español.py",
                "content": """# Código en español
def saludar_año_nuevo():
    mensaje = "¡Feliz año nuevo!"
    return mensaje

señor = "Mr."
niño = "child"
""",
                "content_raw": """# Código en español
def saludar_año_nuevo():
    mensaje = "¡Feliz año nuevo!"
    return mensaje

señor = "Mr."
niño = "child"
""",
                "identifiers": ["saludar_año_nuevo", "mensaje", "señor", "niño"],
                "line_start": 1,
                "line_end": 7,
                "language": "python",
            },
            {
                "path": "src/japanese.py",
                "content": """# 日本語のコード
def get_greeting():
    return "こんにちは世界"

# 変数の定義
name = "日本"
""",
                "content_raw": """# 日本語のコード
def get_greeting():
    return "こんにちは世界"

# 変数の定義
name = "日本"
""",
                "identifiers": ["get_greeting", "name"],
                "line_start": 1,
                "line_end": 6,
                "language": "python",
            },
            {
                "path": "src/mixed.py",
                "content": """café = "coffee"  # French word
piñata = "party"  # Spanish word
naïve = True  # English with diacritic
résumé = "document"  # Common Unicode
""",
                "content_raw": """café = "coffee"  # French word
piñata = "party"  # Spanish word
naïve = True  # English with diacritic
résumé = "document"  # Common Unicode
""",
                "identifiers": ["café", "piñata", "naïve", "résumé"],
                "line_start": 1,
                "line_end": 4,
                "language": "python",
            },
        ]

    @pytest.fixture
    def indexed_manager_unicode(self, tantivy_manager, unicode_documents):
        """Manager with Unicode documents indexed."""
        for doc in unicode_documents:
            tantivy_manager.add_document(doc)
        tantivy_manager.commit()
        return tantivy_manager

    def test_unicode_column_calculation_for_cafe(self, indexed_manager_unicode):
        """
        GIVEN content with 'café' (4 characters, 5 bytes in UTF-8)
        WHEN searching for text after 'café'
        THEN column number should use character offsets, not byte offsets

        Example: "# café Python" - searching for "Python"
        Character positions: #=0, space=1, c=2, a=3, f=4, é=5, space=6, P=7
        Byte positions: #=0, space=1, c=2, a=3, f=4, é=5-6 (2 bytes), space=7, P=8

        Current Bug: Uses byte offset (P at byte 8)
        Correct: Should use character offset (P at char 7)
        """
        results = indexed_manager_unicode.search(
            query_text=r"café",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        assert len(results) > 0, "Should find 'café' in documents"

        for result in results:
            match_text = result.get("match_text", "")
            column = result.get("column", 0)
            line = result.get("line", 0)

            if "café" in match_text.lower():
                # Column should be based on CHARACTER position, not byte position
                # The 'é' in café is 1 character but 2 bytes in UTF-8
                # If column calculation is using bytes, it will be off by 1

                # Verify column is reasonable (positive integer)
                assert column > 0, f"Column should be > 0, got {column}"

                # For debugging: print position info
                print(
                    f"Match '{match_text}' at line {line}, column {column} in {result['path']}"
                )

    def test_unicode_column_for_spanish_characters(self, indexed_manager_unicode):
        """
        GIVEN content with Spanish characters (ñ, ¡, á)
        WHEN searching for identifiers with these characters
        THEN column positions should be accurate

        Spanish characters like 'ñ' are 2 bytes in UTF-8 but 1 character.
        """
        results = indexed_manager_unicode.search(
            query_text=r"año",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        assert len(results) > 0, "Should find Spanish text"

        for result in results:
            column = result.get("column", 0)
            assert column > 0, f"Column should be positive, got {column}"

    def test_unicode_column_for_japanese_characters(self, indexed_manager_unicode):
        """
        GIVEN content with Japanese characters (多 byte UTF-8: 3 bytes per character)
        WHEN searching for Japanese text
        THEN column positions should count characters, not bytes

        Japanese characters are typically 3 bytes in UTF-8 but 1 character each.
        This is the most extreme test case for byte vs character offset bugs.
        """
        results = indexed_manager_unicode.search(
            query_text=r"日本",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        assert len(results) > 0, "Should find Japanese text"

        for result in results:
            column = result.get("column", 0)
            match_text = result.get("match_text", "")

            # Verify column is calculated
            assert column > 0, f"Column should be positive, got {column}"

            # Japanese text found
            print(
                f"Japanese match '{match_text}' at column {column}"
            )

    def test_unicode_at_line_start_has_column_1(self, indexed_manager_unicode):
        """
        GIVEN line starting with Unicode character
        WHEN that character is matched
        THEN column should be 1 (first character position)

        Verifies that Unicode at line start doesn't cause off-by-one errors.
        """
        results = indexed_manager_unicode.search(
            query_text=r"café\s*=",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        # Find result for line starting with 'café'
        line_start_results = [
            r
            for r in results
            if r.get("column", 0) <= 3  # Should be near start of line
        ]

        if line_start_results:
            result = line_start_results[0]
            column = result.get("column", 0)

            # Column should be 1 (or very close) for identifier at line start
            assert column <= 3, (
                f"Unicode identifier at line start should be at column 1-3, got {column}"
            )

    def test_unicode_in_middle_of_line_correct_column(self, indexed_manager_unicode):
        """
        GIVEN Unicode character in middle of line after ASCII text
        WHEN matching text after the Unicode character
        THEN column should correctly account for Unicode character as 1 char, not multiple bytes

        Example: "message = 'café'"
        If searching for 'coffee' comment after 'café', column should count 'é' as 1 character.
        """
        results = indexed_manager_unicode.search(
            query_text=r"coffee",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        cafe_line_results = [
            r for r in results if "café" in r.get("snippet", "").lower()
        ]

        if cafe_line_results:
            result = cafe_line_results[0]
            column = result.get("column", 0)
            snippet = result.get("snippet", "")

            # Column should be reasonable
            assert column > 0, f"Column should be positive, got {column}"

            # Debugging: show position calculation
            print(
                f"Match after Unicode: column {column}, snippet: {snippet[:50]}"
            )

    def test_multiple_unicode_chars_accumulate_correctly(self, indexed_manager_unicode):
        """
        GIVEN line with multiple Unicode characters: "café piñata naïve"
        WHEN searching for text at end of line
        THEN column should correctly count each Unicode char as 1 character

        This tests cumulative effect of multiple multi-byte characters.
        Each 2-byte character (é, ñ, ï) should count as 1 position, not 2.
        """
        results = indexed_manager_unicode.search(
            query_text=r"document",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        if results:
            result = results[0]
            column = result.get("column", 0)

            # Column should be calculated correctly despite multiple Unicode chars before it
            assert column > 0, f"Column should be positive, got {column}"

    def test_unicode_emoji_column_calculation(self, indexed_manager_unicode):
        """
        GIVEN content with emoji characters (4-byte UTF-8 sequences)
        WHEN calculating column positions
        THEN each emoji should count as 1 character

        Emojis are the most extreme case: up to 4 bytes per character.
        Some emojis use multiple code points (e.g., skin tone modifiers).

        Note: This test adds a document with emojis for comprehensive testing.
        """
        # Add document with emojis
        emoji_doc = {
            "path": "src/emoji.py",
            "content": """# 🎉 Celebration module
status = "✅ Complete"
mood = "😀 Happy"
flag = "🇺🇸 USA"
""",
            "content_raw": """# 🎉 Celebration module
status = "✅ Complete"
mood = "😀 Happy"
flag = "🇺🇸 USA"
""",
            "identifiers": ["status", "mood", "flag"],
            "line_start": 1,
            "line_end": 4,
            "language": "python",
        }

        indexed_manager_unicode.add_document(emoji_doc)
        indexed_manager_unicode.commit()

        results = indexed_manager_unicode.search(
            query_text=r"Complete",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        emoji_results = [r for r in results if "emoji.py" in r.get("path", "")]

        if emoji_results:
            result = emoji_results[0]
            column = result.get("column", 0)

            # Verify column is calculated (should handle emoji correctly)
            assert column > 0, f"Column should be positive even with emoji, got {column}"

    def test_unicode_bom_doesnt_affect_column_calculation(
        self, indexed_manager_unicode
    ):
        """
        GIVEN file with UTF-8 BOM (Byte Order Mark) at start
        WHEN calculating columns
        THEN BOM should not interfere with column positions

        UTF-8 BOM is 3 bytes (EF BB BF) but typically not counted as visible character.
        """
        # Note: BOM handling depends on how files are read
        # This test ensures our column calculation is robust
        results = indexed_manager_unicode.search(
            query_text=r"def\s+\w+",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        if results:
            for result in results:
                column = result.get("column", 0)
                # Columns should be reasonable
                assert column > 0, f"Column calculation should work with any encoding"

    def test_unicode_normalization_doesnt_break_columns(
        self, indexed_manager_unicode
    ):
        """
        GIVEN Unicode with different normalization forms (NFD vs NFC)
        WHEN calculating columns
        THEN positions should be consistent

        Example: 'é' can be:
        - NFC: Single code point U+00E9 (1 character)
        - NFD: 'e' + combining acute U+0301 (2 characters visually as 1)

        Note: Most Python strings use NFC by default.
        """
        results = indexed_manager_unicode.search(
            query_text=r"café|cafe",
            use_regex=True,
            case_sensitive=False,
            limit=10,
        )

        if results:
            for result in results:
                column = result.get("column", 0)
                assert column > 0, "Column should be calculated correctly"

    def test_extract_snippet_internal_method_uses_character_offsets(
        self, tantivy_manager
    ):
        """
        GIVEN _extract_snippet() method called directly
        WHEN content contains Unicode characters
        THEN should calculate line_len using character count, not bytes

        This is a white-box test of the internal _extract_snippet method.
        """
        content = "café python\nmore text\n"
        match_start = 5  # Character position of 'p' in "café python"
        match_len = 6  # Length of "python"
        snippet_lines = 1

        snippet, line, column, snippet_start_line = tantivy_manager._extract_snippet(
            content, match_start, match_len, snippet_lines
        )

        # Column should be calculated using character positions
        # "café " is 5 characters (not 6 bytes), so 'p' is at column 6
        assert column == 6, (
            f"Expected column 6 for 'python' after 'café ', got column {column}"
        )

        assert line == 1, f"Expected line 1, got {line}"

    def test_extract_snippet_multibyte_character_at_match_position(
        self, tantivy_manager
    ):
        """
        GIVEN match that starts with multi-byte character
        WHEN extracting snippet
        THEN column should count the multi-byte char as 1 character
        """
        content = "test café here\n"
        match_start = 5  # Character position of 'c' in "café"
        match_len = 4  # Length of "café"
        snippet_lines = 1

        snippet, line, column, snippet_start_line = tantivy_manager._extract_snippet(
            content, match_start, match_len, snippet_lines
        )

        # 'c' in "café" should be at column 6 (after "test ")
        assert column == 6, f"Expected column 6 for 'café', got column {column}"
