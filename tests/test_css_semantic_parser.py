"""
Tests for CSS semantic parser.
Following TDD - writing comprehensive tests first.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestCSSSemanticParser:
    """Test CSS-specific semantic parsing."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a CSS parser directly."""
        from code_indexer.indexing.css_parser import CssSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return CssSemanticParser(config)

    def test_basic_css_rules(self, chunker):
        """Test parsing of basic CSS rules."""
        content = dedent(
            """
            body {
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
            }
            
            .container {
                width: 100%;
                max-width: 1200px;
                margin: 0 auto;
            }
            
            #header {
                background-color: #333;
                color: white;
                padding: 20px;
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.css")

        # Should have chunks for each rule
        assert len(chunks) >= 3

        # Check body rule
        body_chunks = [c for c in chunks if "body" in c["semantic_name"]]
        assert len(body_chunks) >= 1
        body_chunk = body_chunks[0]
        assert body_chunk["semantic_type"] == "rule"
        assert "element_selector" in body_chunk["semantic_language_features"]
        assert len(body_chunk["semantic_context"]["declarations"]) >= 3

        # Check class selector
        container_chunks = [c for c in chunks if "container" in c["semantic_name"]]
        assert len(container_chunks) >= 1
        container_chunk = container_chunks[0]
        assert "class_selector" in container_chunk["semantic_language_features"]

        # Check ID selector
        header_chunks = [c for c in chunks if "header" in c["semantic_name"]]
        assert len(header_chunks) >= 1
        header_chunk = header_chunks[0]
        assert "id_selector" in header_chunk["semantic_language_features"]

    def test_css_at_rules(self, chunker):
        """Test parsing of CSS @-rules."""
        content = dedent(
            """
            @charset "UTF-8";
            @import url("reset.css");
            @import "typography.css";
            
            @media screen and (max-width: 768px) {
                .container {
                    width: 100%;
                }
            }
            
            @keyframes fadeIn {
                0% { opacity: 0; }
                100% { opacity: 1; }
            }
            
            @font-face {
                font-family: 'CustomFont';
                src: url('font.woff2') format('woff2');
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "atrules.css")

        # Check @charset
        charset_chunks = [c for c in chunks if c["semantic_type"] == "charset"]
        assert len(charset_chunks) >= 1
        charset_chunk = charset_chunks[0]
        assert "at_charset" in charset_chunk["semantic_language_features"]
        assert charset_chunk["semantic_context"]["charset_value"] == "UTF-8"

        # Check @import
        import_chunks = [c for c in chunks if c["semantic_type"] == "import"]
        assert len(import_chunks) >= 2
        import_chunk = import_chunks[0]
        assert "at_import" in import_chunk["semantic_language_features"]
        assert "external_dependency" in import_chunk["semantic_language_features"]

        # Check @media
        media_chunks = [c for c in chunks if c["semantic_type"] == "media"]
        assert len(media_chunks) >= 1
        media_chunk = media_chunks[0]
        assert "at_media" in media_chunk["semantic_language_features"]
        assert "responsive" in media_chunk["semantic_language_features"]
        assert "width_based" in media_chunk["semantic_language_features"]

        # Check @keyframes
        keyframes_chunks = [c for c in chunks if c["semantic_type"] == "keyframes"]
        assert len(keyframes_chunks) >= 1
        keyframes_chunk = keyframes_chunks[0]
        assert "at_keyframes" in keyframes_chunk["semantic_language_features"]
        assert "animation" in keyframes_chunk["semantic_language_features"]
        assert keyframes_chunk["semantic_name"] == "fadeIn"

    def test_complex_selectors(self, chunker):
        """Test parsing of complex CSS selectors."""
        content = dedent(
            """
            .nav ul li a:hover {
                color: #007bff;
                text-decoration: underline;
            }
            
            input[type="text"]:focus {
                border-color: #007bff;
                outline: none;
            }
            
            .card:nth-child(odd) .title {
                background-color: #f8f9fa;
            }
            
            h1, h2, h3 {
                font-weight: bold;
                margin-bottom: 1rem;
            }
            
            @media (min-width: 768px) {
                .responsive-grid {
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                }
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "complex.css")

        # Check pseudo selectors
        pseudo_chunks = [
            c for c in chunks if "pseudo_selector" in c["semantic_language_features"]
        ]
        assert len(pseudo_chunks) >= 2  # :hover and :focus

        # Check attribute selectors
        attr_chunks = [
            c for c in chunks if "attribute_selector" in c["semantic_language_features"]
        ]
        assert len(attr_chunks) >= 1

        # Check multiple selectors
        multi_chunks = [
            c for c in chunks if "multiple_selectors" in c["semantic_language_features"]
        ]
        assert len(multi_chunks) >= 1  # h1, h2, h3 rule

        # Check that multi-selector rule has correct context
        h_rule = [
            c for c in multi_chunks if "h1" in str(c["semantic_context"]["selectors"])
        ]
        assert len(h_rule) >= 1
        assert len(h_rule[0]["semantic_context"]["selectors"]) == 3

    def test_css_comments(self, chunker):
        """Test parsing of CSS comments."""
        content = dedent(
            """
            /* Main stylesheet for the application */
            
            body {
                margin: 0;
            }
            
            /* 
             * Navigation styles
             * Updated: 2023-01-01
             */
            .nav {
                background: #333;
            }
            
            .footer { color: gray; } /* Inline comment */
            """
        ).strip()

        chunks = chunker.chunk_content(content, "comments.css")

        # Check for comment chunks
        comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
        assert len(comment_chunks) >= 2  # Multi-line and single-line comments

        # Check comment content
        main_comment = [
            c
            for c in comment_chunks
            if "Main stylesheet" in c["semantic_context"]["comment_content"]
        ]
        assert len(main_comment) >= 1
        assert "css_comment" in main_comment[0]["semantic_language_features"]

        # Check multi-line comment
        nav_comment = [
            c
            for c in comment_chunks
            if "Navigation styles" in c["semantic_context"]["comment_content"]
        ]
        assert len(nav_comment) >= 1

    def test_css_properties_and_values(self, chunker):
        """Test parsing of CSS property-value pairs."""
        content = dedent(
            """
            .test {
                color: #ff0000;
                background: linear-gradient(to right, #fff, #000);
                font-size: 16px;
                margin: 10px 20px;
                border: 1px solid var(--primary-color);
                transform: translateX(calc(100% - 50px));
                display: flex;
                justify-content: center;
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "properties.css")

        # Should have rule chunk and possibly declaration chunks
        rule_chunks = [c for c in chunks if c["semantic_type"] == "rule"]
        assert len(rule_chunks) >= 1

        rule_chunk = rule_chunks[0]
        declarations = rule_chunk["semantic_context"]["declarations"]
        assert len(declarations) >= 6

        # Check for various property types
        color_props = [d for d in declarations if d["property"] == "color"]
        assert len(color_props) >= 1

        # Check if individual declarations are extracted
        decl_chunks = [c for c in chunks if c["semantic_type"] == "declaration"]
        if decl_chunks:
            # Check CSS variable usage
            var_decls = [
                c
                for c in decl_chunks
                if "css_variable" in c["semantic_language_features"]
            ]
            calc_decls = [
                c for c in decl_chunks if "css_calc" in c["semantic_language_features"]
            ]
            color_decls = [
                c
                for c in decl_chunks
                if "color_value" in c["semantic_language_features"]
            ]
            size_decls = [
                c
                for c in decl_chunks
                if "size_value" in c["semantic_language_features"]
            ]

            # Should have at least one of each type
            assert (
                len(var_decls) >= 1
                or len(calc_decls) >= 1
                or len(color_decls) >= 1
                or len(size_decls) >= 1
            )

    def test_nested_css_media_queries(self, chunker):
        """Test parsing of nested CSS within media queries."""
        content = dedent(
            """
            @media screen and (max-width: 768px) {
                .container {
                    width: 100%;
                    padding: 0 15px;
                }
                
                .nav ul {
                    flex-direction: column;
                }
                
                .btn {
                    width: 100%;
                    margin-bottom: 10px;
                }
            }
            
            @media print {
                .no-print {
                    display: none;
                }
                
                body {
                    font-size: 12pt;
                }
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "media.css")

        # Check media queries
        media_chunks = [c for c in chunks if c["semantic_type"] == "media"]
        assert len(media_chunks) >= 2

        # Check screen media
        screen_media = [
            c for c in media_chunks if "screen_media" in c["semantic_language_features"]
        ]
        assert len(screen_media) >= 1

        # Check print media
        print_media = [
            c for c in media_chunks if "print_media" in c["semantic_language_features"]
        ]
        assert len(print_media) >= 1

        # Check nested rules within media queries
        # Rules should have media context in their parent path
        rule_chunks = [c for c in chunks if c["semantic_type"] == "rule"]
        media_nested_rules = [
            c
            for c in rule_chunks
            if c["semantic_parent"] and "media" in c["semantic_parent"]
        ]
        assert len(media_nested_rules) >= 3  # At least 3 rules inside media queries

    def test_css_animations_and_transitions(self, chunker):
        """Test parsing of CSS animations and keyframes."""
        content = dedent(
            """
            @keyframes slideIn {
                from {
                    transform: translateX(-100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            
            @keyframes bounce {
                0%, 20%, 50%, 80%, 100% {
                    transform: translateY(0);
                }
                40% {
                    transform: translateY(-30px);
                }
                60% {
                    transform: translateY(-15px);
                }
            }
            
            .animated {
                animation: slideIn 0.3s ease-in-out;
                transition: all 0.2s ease;
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "animations.css")

        # Check keyframes
        keyframes_chunks = [c for c in chunks if c["semantic_type"] == "keyframes"]
        assert len(keyframes_chunks) >= 2

        # Check slideIn keyframes
        slideIn_chunks = [
            c for c in keyframes_chunks if c["semantic_name"] == "slideIn"
        ]
        assert len(slideIn_chunks) >= 1
        slideIn_chunk = slideIn_chunks[0]
        assert "css_animation" in slideIn_chunk["semantic_language_features"]
        assert "has_keyframes" in slideIn_chunk["semantic_language_features"]

        # Check bounce keyframes with percentage steps
        bounce_chunks = [c for c in keyframes_chunks if c["semantic_name"] == "bounce"]
        assert len(bounce_chunks) >= 1
        bounce_chunk = bounce_chunks[0]
        assert bounce_chunk["semantic_context"]["step_count"] >= 3

    def test_error_node_fallback(self, chunker):
        """Test ERROR node handling with regex fallback."""
        # Malformed CSS that might create ERROR nodes
        content = dedent(
            """
            .good-rule {
                color: red;
                margin: 10px;
            }
            
            .broken-rule {
                color: red
                margin 10px;  // Missing colon and semicolon
                background: url(unclosed.jpg;
            }
            
            /* Good comment */
            
            .another-good {
                padding: 5px;
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "broken.css")

        # Should still extract meaningful content even with errors
        assert len(chunks) >= 2

        # Check that good rules are still parsed
        good_chunks = [c for c in chunks if "good" in c["semantic_name"]]
        comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]

        assert len(good_chunks) >= 2
        assert len(comment_chunks) >= 1

    def test_css_custom_properties(self, chunker):
        """Test parsing of CSS custom properties (CSS variables)."""
        content = dedent(
            """
            :root {
                --primary-color: #007bff;
                --secondary-color: #6c757d;
                --font-size-base: 16px;
                --spacing-unit: 8px;
            }
            
            .component {
                color: var(--primary-color);
                font-size: var(--font-size-base);
                margin: calc(var(--spacing-unit) * 2);
                background: var(--secondary-color, #gray);
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "variables.css")

        # Check root pseudo-class
        root_chunks = [c for c in chunks if "root" in c["semantic_name"]]
        assert len(root_chunks) >= 1
        root_chunk = root_chunks[0]
        assert "pseudo_selector" in root_chunk["semantic_language_features"]

        # Check CSS variable usage
        component_chunks = [c for c in chunks if "component" in c["semantic_name"]]
        assert len(component_chunks) >= 1

        # If declarations are extracted separately, check for CSS variable features
        decl_chunks = [c for c in chunks if c["semantic_type"] == "declaration"]
        if decl_chunks:
            var_decls = [
                c
                for c in decl_chunks
                if "css_variable" in c["semantic_language_features"]
            ]
            calc_decls = [
                c for c in decl_chunks if "css_calc" in c["semantic_language_features"]
            ]
            assert len(var_decls) >= 1 or len(calc_decls) >= 1

    def test_css_grid_and_flexbox(self, chunker):
        """Test parsing of CSS Grid and Flexbox properties."""
        content = dedent(
            """
            .grid-container {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                grid-gap: 20px;
                grid-template-areas: 
                    "header header header"
                    "sidebar main main"
                    "footer footer footer";
            }
            
            .flex-container {
                display: flex;
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
            }
            
            .flex-item {
                flex: 1 1 auto;
                flex-basis: 200px;
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "layout.css")

        # Check grid container
        grid_chunks = [c for c in chunks if "grid-container" in c["semantic_name"]]
        assert len(grid_chunks) >= 1
        grid_chunk = grid_chunks[0]
        declarations = grid_chunk["semantic_context"]["declarations"]

        # Should have grid-related properties
        grid_props = [d for d in declarations if "grid" in d["property"]]
        assert len(grid_props) >= 3

        # Check flex container
        flex_chunks = [c for c in chunks if "flex-container" in c["semantic_name"]]
        assert len(flex_chunks) >= 1
        flex_chunk = flex_chunks[0]
        flex_declarations = flex_chunk["semantic_context"]["declarations"]

        # Should have flex-related properties
        flex_props = [
            d
            for d in flex_declarations
            if "flex" in d["property"] or "justify" in d["property"]
        ]
        assert len(flex_props) >= 2

    def test_fallback_parsing(self, chunker):
        """Test complete fallback parsing when tree-sitter fails."""
        # Extremely malformed CSS
        content = dedent(
            """
            .test {
                color: red;
                margin: 10px;
            }
            
            << broken syntax >>
            
            /* comment */
            
            .another { padding: 5px; }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "broken.css")

        # Should create at least a fallback chunk
        assert len(chunks) >= 1

        # If fallback chunk is created, it should have stylesheet type
        if len(chunks) == 1 and chunks[0]["semantic_type"] == "stylesheet":
            assert chunks[0]["semantic_name"] == "broken"
            assert "fallback_chunk" in chunks[0]["semantic_language_features"]
        else:
            # Or should extract what it can
            rule_chunks = [c for c in chunks if c["semantic_type"] == "rule"]
            comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
            assert len(rule_chunks) >= 1 or len(comment_chunks) >= 1

    def test_css_specificity_and_combinators(self, chunker):
        """Test parsing of CSS with various combinators and specificity."""
        content = dedent(
            """
            /* Child combinator */
            .parent > .child {
                margin: 0;
            }
            
            /* Descendant combinator */
            .ancestor .descendant {
                color: blue;
            }
            
            /* Adjacent sibling */
            h1 + p {
                margin-top: 0;
            }
            
            /* General sibling */
            h1 ~ p {
                color: gray;
            }
            
            /* High specificity */
            div.container#main.active[data-state="loaded"] {
                visibility: visible;
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "combinators.css")

        # Should parse all the rules
        rule_chunks = [c for c in chunks if c["semantic_type"] == "rule"]
        assert len(rule_chunks) >= 5

        # Check complex selector
        complex_chunks = [
            c for c in rule_chunks if len(c["semantic_context"]["selectors"][0]) > 20
        ]
        assert len(complex_chunks) >= 1

        # Check that various selector types are detected
        all_features = []
        for chunk in rule_chunks:
            all_features.extend(chunk["semantic_language_features"])

        assert "element_selector" in all_features
        assert "class_selector" in all_features
        assert "id_selector" in all_features or "attribute_selector" in all_features
