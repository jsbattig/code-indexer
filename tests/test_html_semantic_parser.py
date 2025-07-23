"""
Tests for HTML semantic parser.
Following TDD - writing comprehensive tests first.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestHTMLSemanticParser:
    """Test HTML-specific semantic parsing."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create an HTML parser directly."""
        from code_indexer.indexing.html_parser import HtmlSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return HtmlSemanticParser(config)

    def test_basic_html_structure(self, chunker):
        """Test parsing of basic HTML document structure."""
        content = dedent(
            """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <title>Test Page</title>
                <meta charset="UTF-8">
            </head>
            <body>
                <h1>Welcome</h1>
                <p>Hello world!</p>
            </body>
            </html>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Should have chunks for major structural elements
        assert len(chunks) >= 3

        # Check DOCTYPE
        doctype_chunks = [c for c in chunks if c["semantic_type"] == "doctype"]
        assert len(doctype_chunks) == 1
        assert doctype_chunks[0]["semantic_name"] == "DOCTYPE"
        assert "html" in doctype_chunks[0]["text"].lower()

        # Check HTML root element
        html_chunks = [c for c in chunks if c["semantic_name"] == "html"]
        assert len(html_chunks) >= 1
        assert html_chunks[0]["semantic_type"] == "element"
        assert "root_element" in html_chunks[0]["semantic_language_features"]

    def test_html_elements_with_attributes(self, chunker):
        """Test parsing of HTML elements with various attributes."""
        content = dedent(
            """
            <div id="main" class="container large" data-test="value">
                <a href="https://example.com" target="_blank">Link</a>
                <img src="image.jpg" alt="Description" width="100" height="200">
                <input type="text" name="username" placeholder="Enter name" required>
            </div>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Check div element with multiple attributes
        div_chunks = [c for c in chunks if c["semantic_name"] == "div"]
        assert len(div_chunks) >= 1
        div_chunk = div_chunks[0]
        assert div_chunk["semantic_type"] == "element"
        assert "has_id" in div_chunk["semantic_language_features"]
        assert "has_class" in div_chunk["semantic_language_features"]
        assert div_chunk["semantic_context"]["attributes"]["id"] == "main"
        assert div_chunk["semantic_context"]["attributes"]["class"] == "container large"

        # Check self-closing elements
        img_chunks = [c for c in chunks if c["semantic_name"] == "img"]
        if img_chunks:
            assert "self_closing" in img_chunks[0]["semantic_language_features"]

    def test_script_and_style_elements(self, chunker):
        """Test parsing of script and style elements."""
        content = dedent(
            """
            <head>
                <style type="text/css">
                    body { margin: 0; }
                    .container { padding: 20px; }
                </style>
                <script type="text/javascript">
                    function greet() {
                        alert('Hello!');
                    }
                </script>
            </head>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Check style element
        style_chunks = [c for c in chunks if c["semantic_type"] == "style"]
        assert len(style_chunks) >= 1
        style_chunk = style_chunks[0]
        assert "style_block" in style_chunk["semantic_language_features"]
        assert "inline_css" in style_chunk["semantic_language_features"]
        assert style_chunk["semantic_context"]["css_content"]

        # Check script element
        script_chunks = [c for c in chunks if c["semantic_type"] == "script"]
        assert len(script_chunks) >= 1
        script_chunk = script_chunks[0]
        assert "script_block" in script_chunk["semantic_language_features"]
        assert "inline_script" in script_chunk["semantic_language_features"]
        assert script_chunk["semantic_context"]["script_content"]

    def test_html_comments(self, chunker):
        """Test parsing of HTML comments."""
        content = dedent(
            """
            <!-- Main navigation section -->
            <nav>
                <ul>
                    <!-- TODO: Add more menu items -->
                    <li><a href="/">Home</a></li>
                </ul>
            </nav>
            <!-- End navigation -->
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Check for comment chunks
        comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
        assert len(comment_chunks) >= 2

        # Check comment content
        main_comment = [
            c
            for c in comment_chunks
            if "navigation" in c["semantic_context"]["comment_content"].lower()
        ]
        assert len(main_comment) >= 1
        assert "html_comment" in main_comment[0]["semantic_language_features"]

    def test_nested_html_structure(self, chunker):
        """Test parsing of deeply nested HTML structures."""
        content = dedent(
            """
            <article class="post">
                <header>
                    <h1>Article Title</h1>
                    <div class="meta">
                        <span class="author">John Doe</span>
                        <time datetime="2023-01-01">January 1, 2023</time>
                    </div>
                </header>
                <section class="content">
                    <p>First paragraph.</p>
                    <div class="highlight">
                        <p>Important note in a box.</p>
                    </div>
                </section>
            </article>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Check semantic element classification
        semantic_chunks = [
            c for c in chunks if "semantic" in c["semantic_language_features"]
        ]
        structural_chunks = [
            c for c in chunks if "structural" in c["semantic_language_features"]
        ]

        assert len(semantic_chunks) >= 3  # h1, p elements
        assert len(structural_chunks) >= 3  # article, header, section

        # Check nesting relationships
        article_chunks = [c for c in chunks if c["semantic_name"] == "article"]
        assert len(article_chunks) >= 1
        article_path = article_chunks[0]["semantic_path"]

        # Check that nested elements have correct parent paths
        nested_chunks = [
            c
            for c in chunks
            if c["semantic_parent"] and article_path in c["semantic_parent"]
        ]
        assert len(nested_chunks) >= 2

    def test_html_forms(self, chunker):
        """Test parsing of HTML form elements."""
        content = dedent(
            """
            <form action="/submit" method="post" enctype="multipart/form-data">
                <fieldset>
                    <legend>User Information</legend>
                    <label for="name">Name:</label>
                    <input type="text" id="name" name="name" required>
                    
                    <label for="email">Email:</label>
                    <input type="email" id="email" name="email" required>
                    
                    <select name="country">
                        <option value="us">United States</option>
                        <option value="ca">Canada</option>
                    </select>
                    
                    <textarea name="message" rows="4" cols="50"></textarea>
                    <button type="submit">Submit</button>
                </fieldset>
            </form>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Check form element
        form_chunks = [c for c in chunks if c["semantic_name"] == "form"]
        assert len(form_chunks) >= 1
        form_chunk = form_chunks[0]
        assert form_chunk["semantic_type"] == "element"
        assert form_chunk["semantic_context"]["attributes"]["method"] == "post"

        # Check input elements
        input_chunks = [c for c in chunks if c["semantic_name"] == "input"]
        assert len(input_chunks) >= 2

        # Check for required attributes
        required_inputs = [
            c for c in input_chunks if "required" in c["semantic_context"]["attributes"]
        ]
        assert len(required_inputs) >= 2

    def test_error_node_fallback(self, chunker):
        """Test ERROR node handling with regex fallback."""
        # Malformed HTML that might create ERROR nodes
        content = dedent(
            """
            <div class="container">
                <p>Good paragraph</p>
                <broken-tag attr=unquoted value>
                    Some content
                </broken-tag>
                <!-- Good comment -->
                <span>Another good element</span>
            </div>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Should still extract meaningful content even with errors
        assert len(chunks) >= 3

        # Check that good elements are still parsed
        p_chunks = [c for c in chunks if c["semantic_name"] == "p"]
        span_chunks = [c for c in chunks if c["semantic_name"] == "span"]
        comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]

        assert len(p_chunks) >= 1
        assert len(span_chunks) >= 1
        assert len(comment_chunks) >= 1

    def test_html_with_special_characters(self, chunker):
        """Test parsing HTML with entities and special characters."""
        content = dedent(
            """
            <div>
                <p>Price: &dollar;99.99 &amp; free shipping!</p>
                <p>Math: 2 &lt; 3 &gt; 1 &amp;&amp; true</p>
                <p lang="fr">Café &eacute; résumé</p>
            </div>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Should handle special characters without breaking
        assert len(chunks) >= 3

        # Check that content with entities is preserved
        p_chunks = [c for c in chunks if c["semantic_name"] == "p"]
        assert len(p_chunks) >= 3

        # Check language attribute
        lang_chunks = [
            c
            for c in p_chunks
            if c["semantic_context"]["attributes"].get("lang") == "fr"
        ]
        assert len(lang_chunks) >= 1

    def test_html_semantic_elements(self, chunker):
        """Test parsing of HTML5 semantic elements."""
        content = dedent(
            """
            <main>
                <header>
                    <nav>
                        <ul>
                            <li><a href="/">Home</a></li>
                        </ul>
                    </nav>
                </header>
                <article>
                    <section>
                        <h2>Section Title</h2>
                        <p>Content here.</p>
                    </section>
                    <aside>
                        <p>Sidebar content</p>
                    </aside>
                </article>
                <footer>
                    <p>&copy; 2023</p>
                </footer>
            </main>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.html")

        # Check for HTML5 semantic elements
        semantic_element_names = [
            "main",
            "header",
            "nav",
            "article",
            "section",
            "aside",
            "footer",
        ]

        for element_name in semantic_element_names:
            element_chunks = [c for c in chunks if c["semantic_name"] == element_name]
            assert len(element_chunks) >= 1, f"Missing {element_name} element"

            # Check that semantic elements are marked as structural
            if element_name in [
                "header",
                "nav",
                "main",
                "section",
                "article",
                "aside",
                "footer",
            ]:
                structural_chunks = [
                    c
                    for c in element_chunks
                    if "structural" in c["semantic_language_features"]
                ]
                assert (
                    len(structural_chunks) >= 1
                ), f"{element_name} should be marked as structural"

    def test_fallback_parsing(self, chunker):
        """Test complete fallback parsing when tree-sitter fails."""
        # Extremely malformed HTML
        content = dedent(
            """
            <html>
            <body>
                <div class="test">
                    <p>Some text</p>
                    < broken >> tag
                <!-- comment -->
                </div>
            </body>
            </html>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "broken.html")

        # Should create at least a fallback chunk
        assert len(chunks) >= 1

        # If fallback chunk is created, it should have document type
        if len(chunks) == 1 and chunks[0]["semantic_type"] == "document":
            assert chunks[0]["semantic_name"] == "broken"
            assert "fallback_chunk" in chunks[0]["semantic_language_features"]
        else:
            # Or should extract what it can
            div_chunks = [c for c in chunks if c["semantic_name"] == "div"]
            p_chunks = [c for c in chunks if c["semantic_name"] == "p"]
            assert len(div_chunks) >= 1 or len(p_chunks) >= 1

    def test_html_tables(self, chunker):
        """Test parsing of HTML table structures."""
        content = dedent(
            """
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Age</th>
                        <th>City</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>John</td>
                        <td>25</td>
                        <td>NYC</td>
                    </tr>
                    <tr>
                        <td>Jane</td>
                        <td>30</td>
                        <td>LA</td>
                    </tr>
                </tbody>
            </table>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "table.html")

        # Check table structure
        table_chunks = [c for c in chunks if c["semantic_name"] == "table"]
        assert len(table_chunks) >= 1

        thead_chunks = [c for c in chunks if c["semantic_name"] == "thead"]
        tbody_chunks = [c for c in chunks if c["semantic_name"] == "tbody"]
        th_chunks = [c for c in chunks if c["semantic_name"] == "th"]
        td_chunks = [c for c in chunks if c["semantic_name"] == "td"]

        assert len(thead_chunks) >= 1
        assert len(tbody_chunks) >= 1
        assert len(th_chunks) >= 3  # Three header cells
        assert len(td_chunks) >= 6  # Six data cells

    def test_text_content_extraction(self, chunker):
        """Test extraction of significant text content."""
        content = dedent(
            """
            <div>
                <p>This is a meaningful paragraph with substantial content that should be extracted.</p>
                <span>Short</span>
                <div>This is another piece of significant text content that provides value.</div>
            </div>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "text.html")

        # Check that meaningful text content is extracted
        text_chunks = [c for c in chunks if c["semantic_type"] == "text"]

        # Should have text chunks for substantial content
        meaningful_text = [c for c in text_chunks if len(c["text"]) > 20]
        assert len(meaningful_text) >= 1

    def test_mixed_content_with_entities_and_cdata(self, chunker):
        """Test parsing of mixed content including entities."""
        content = dedent(
            """
            <div>
                <p>Regular text &amp; entities like &lt;script&gt;</p>
                <script>
                    // JavaScript code
                    if (x < 5 && y > 10) {
                        console.log("Test");
                    }
                </script>
                <style>
                    /* CSS code */
                    .class { color: red; }
                </style>
            </div>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "mixed.html")

        # Should handle mixed content types
        assert len(chunks) >= 3

        # Check different content types
        p_chunks = [c for c in chunks if c["semantic_name"] == "p"]
        script_chunks = [c for c in chunks if c["semantic_type"] == "script"]
        style_chunks = [c for c in chunks if c["semantic_type"] == "style"]

        assert len(p_chunks) >= 1
        assert len(script_chunks) >= 1 or len(style_chunks) >= 1
