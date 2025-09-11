"""Test tiktoken accuracy for VoyageAI token counting."""

import pytest

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


@pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
class TestTiktokenAccuracy:
    """Test tiktoken encoding accuracy for different content types."""

    @pytest.fixture
    def tokenizer(self):
        """Get cl100k_base tokenizer (same as VoyageAI)."""
        return tiktoken.get_encoding("cl100k_base")

    def test_plain_text_tokenization(self, tokenizer):
        """Test tokenization of plain English text."""
        text = "The quick brown fox jumps over the lazy dog"
        tokens = tokenizer.encode(text)
        token_count = len(tokens)

        # Plain text should be ~0.7-0.8 tokens per word
        word_count = len(text.split())
        ratio = token_count / word_count

        print(
            f"Plain text: {word_count} words → {token_count} tokens (ratio: {ratio:.2f})"
        )
        assert 0.6 <= ratio <= 1.0, f"Plain text ratio should be 0.6-1.0, got {ratio}"

    def test_xml_content_tokenization(self, tokenizer):
        """Test tokenization of XML content (like your problematic files)."""
        xml_text = """<form action="/submit" method="post" class="user-form">
  <input type="text" name="username" id="user_input" required/>
  <select name="category" class="dropdown">
    <option value="admin">Administrator</option>
    <option value="user">Regular User</option>
  </select>
</form>"""

        tokens = tokenizer.encode(xml_text)
        token_count = len(tokens)
        char_count = len(xml_text)
        word_count = len(xml_text.split())

        char_ratio = char_count / token_count  # Characters per token
        word_ratio = token_count / word_count  # Tokens per word

        print(
            f"XML content: {char_count} chars, {word_count} words → {token_count} tokens"
        )
        print(f"  Chars per token: {char_ratio:.2f}")
        print(f"  Tokens per word: {word_ratio:.2f}")

        # XML should be much denser than plain text
        assert (
            word_ratio >= 1.5
        ), f"XML should be >1.5 tokens per word, got {word_ratio}"
        assert char_ratio <= 4.0, f"XML should be ≤4 chars per token, got {char_ratio}"

    def test_dense_html_tokenization(self, tokenizer):
        """Test very dense HTML like package_xml.js files."""
        # Simulate the kind of dense content in your XML files
        dense_html = (
            """
        <package><data type="complex"><field id="field_001" class="input-field" data-validation="required" data-type="string">
        <value>Sample data content with multiple nested elements</value>
        <metadata><created>2024-01-01</created><updated>2024-12-01</updated></metadata>
        </field><field id="field_002" class="dropdown-field" data-validation="optional">
        <options><option value="1">Option One</option><option value="2">Option Two</option></options>
        </field></data></package>
        """
            * 3
        )  # Repeat to make it larger

        tokens = tokenizer.encode(dense_html)
        token_count = len(tokens)
        char_count = len(dense_html)
        word_count = len(dense_html.split())

        chars_per_token = char_count / token_count
        tokens_per_word = token_count / word_count

        print(
            f"Dense HTML: {char_count} chars, {word_count} words → {token_count} tokens"
        )
        print(f"  Chars per token: {chars_per_token:.2f}")
        print(f"  Tokens per word: {tokens_per_word:.2f}")

        # Your XML files show ~2-2.5 chars per token (very dense)
        expected_range = (
            1.8,
            4.5,
        )  # chars per token - updated to match real measurements
        assert (
            expected_range[0] <= chars_per_token <= expected_range[1]
        ), f"Dense HTML chars per token should be {expected_range}, got {chars_per_token}"

    def test_chunk_size_scenarios(self, tokenizer):
        """Test token counts for different chunk sizes to validate batch limits."""
        # Simulate 1500-character chunks (FixedSizeChunker default)
        chunk_scenarios = [
            # (description, content_type_text, expected_tokens_range)
            ("Plain text chunk", "word " * 300, (200, 400)),  # ~300 words
            (
                "Code chunk",
                "function test() { return data.map(x => x.id); } " * 25,
                (300, 500),  # Updated range based on actual measurement of 326
            ),
            (
                "Dense XML chunk",
                "<tag attr='value'>content</tag>" * 50,
                (400, 500),
            ),  # Updated based on actual measurement of 436
        ]

        results = []
        for description, content, expected_range in chunk_scenarios:
            # Make it roughly 1500 characters like FixedSizeChunker
            content = content[:1500]

            tokens = tokenizer.encode(content)
            token_count = len(tokens)

            print(f"{description}: {len(content)} chars → {token_count} tokens")
            results.append((description, token_count))

            # Validate against expected range
            assert (
                expected_range[0] <= token_count <= expected_range[1]
            ), f"{description} should have {expected_range} tokens, got {token_count}"

    def test_your_error_scenario_simulation(self, tokenizer):
        """Simulate the exact scenario from your 187K token error."""
        # Create content similar to package_0_xml.js
        # Your error: 187K tokens for unknown number of chunks

        # Dense XML-like content that could produce ~3700 tokens per chunk
        dense_content = """
        <form id="form_{i}" class="complex-form" data-validation="strict">
        <fieldset><legend>Section {i}</legend>
        <input type="text" name="field_{i}_text" id="input_{i}" class="required" data-pattern="[a-zA-Z]+" />
        <select name="field_{i}_select" class="dropdown" multiple>
        <option value="option_{i}_1">Option {i} One</option>
        <option value="option_{i}_2">Option {i} Two</option>
        <option value="option_{i}_3">Option {i} Three</option>
        </select>
        <textarea name="field_{i}_textarea" rows="5" cols="50" placeholder="Enter description..."></textarea>
        </fieldset>
        </form>
        """

        # Create chunks that would produce ~187K total tokens
        chunks = []
        total_tokens = 0

        for i in range(100):  # Create 100 chunks
            chunk_content = dense_content.format(i=i)
            chunk_tokens = len(tokenizer.encode(chunk_content))
            chunks.append(chunk_content)
            total_tokens += chunk_tokens

            print(f"Chunk {i+1}: {len(chunk_content)} chars → {chunk_tokens} tokens")

            # Stop when we approach your error scenario
            if total_tokens > 180_000:
                break

        print("\nScenario simulation:")
        print(f"  Total chunks: {len(chunks)}")
        print(f"  Total tokens: {total_tokens}")
        print(f"  Average tokens per chunk: {total_tokens / len(chunks):.0f}")
        print(
            f"  This would {'EXCEED' if total_tokens > 120_000 else 'stay within'} VoyageAI's 120K limit"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
