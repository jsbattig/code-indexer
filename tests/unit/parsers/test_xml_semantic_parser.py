"""
Tests for XML semantic parser.
Following TDD - writing comprehensive tests first.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestXMLSemanticParser:
    """Test XML-specific semantic parsing."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create an XML parser directly."""
        from code_indexer.indexing.xml_parser import XmlSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return XmlSemanticParser(config)

    def test_basic_xml_structure(self, chunker):
        """Test parsing of basic XML document structure."""
        content = dedent(
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <root>
                <title>Sample Document</title>
                <author>John Doe</author>
                <content>
                    <paragraph>This is the first paragraph.</paragraph>
                    <paragraph>This is the second paragraph.</paragraph>
                </content>
            </root>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "test.xml")

        # Should have chunks for major elements
        assert len(chunks) >= 4

        # Check XML declaration
        decl_chunks = [c for c in chunks if c["semantic_type"] == "xml_declaration"]
        assert len(decl_chunks) >= 1
        decl_chunk = decl_chunks[0]
        assert "xml_declaration" in decl_chunk["semantic_language_features"]
        assert "document_metadata" in decl_chunk["semantic_language_features"]
        assert decl_chunk["semantic_context"]["attributes"]["version"] == "1.0"
        assert decl_chunk["semantic_context"]["attributes"]["encoding"] == "UTF-8"

        # Check root element
        root_chunks = [c for c in chunks if c["semantic_name"] == "root"]
        assert len(root_chunks) >= 1
        root_chunk = root_chunks[0]
        assert root_chunk["semantic_type"] == "element"
        assert "xml_element" in root_chunk["semantic_language_features"]

        # Check nested elements
        paragraph_chunks = [c for c in chunks if c["semantic_name"] == "paragraph"]
        assert len(paragraph_chunks) >= 2

    def test_xml_elements_with_attributes(self, chunker):
        """Test parsing of XML elements with various attributes."""
        content = dedent(
            """
            <document id="doc1" version="2.0" lang="en">
                <section class="intro" data-level="1">
                    <title>Introduction</title>
                    <link href="https://example.com" target="_blank" rel="external"/>
                    <image src="image.jpg" alt="Description" width="100" height="200"/>
                </section>
            </document>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "attributes.xml")

        # Check document element with multiple attributes
        doc_chunks = [c for c in chunks if c["semantic_name"] == "document"]
        assert len(doc_chunks) >= 1
        doc_chunk = doc_chunks[0]
        assert doc_chunk["semantic_type"] == "element"
        assert "has_attributes" in doc_chunk["semantic_language_features"]
        assert doc_chunk["semantic_context"]["attributes"]["id"] == "doc1"
        assert doc_chunk["semantic_context"]["attributes"]["version"] == "2.0"
        assert doc_chunk["semantic_context"]["attributes"]["lang"] == "en"

        # Check self-closing elements
        self_closing_chunks = [
            c for c in chunks if c["semantic_type"] == "self_closing_element"
        ]
        assert len(self_closing_chunks) >= 2  # link and image

        link_chunks = [c for c in self_closing_chunks if c["semantic_name"] == "link"]
        assert len(link_chunks) >= 1
        link_chunk = link_chunks[0]
        assert "self_closing" in link_chunk["semantic_language_features"]
        assert link_chunk["semantic_context"]["is_self_closing"] is True

    def test_xml_namespaces(self, chunker):
        """Test parsing of XML with namespaces."""
        content = dedent(
            """
            <root xmlns="http://example.com/default" 
                  xmlns:custom="http://example.com/custom"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                <title>Default namespace element</title>
                <custom:metadata>
                    <custom:author>Jane Smith</custom:author>
                    <custom:created>2023-01-01</custom:created>
                </custom:metadata>
                <data xsi:type="string">Some data</data>
            </root>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "namespaces.xml")

        # Check root element with namespace declarations
        root_chunks = [c for c in chunks if c["semantic_name"] == "root"]
        assert len(root_chunks) >= 1
        root_chunk = root_chunks[0]
        assert "has_attributes" in root_chunk["semantic_language_features"]
        assert "xmlns" in root_chunk["semantic_context"]["attributes"]

        # Check namespaced elements
        namespaced_chunks = [
            c for c in chunks if "namespaced" in c["semantic_language_features"]
        ]
        assert (
            len(namespaced_chunks) >= 2
        )  # custom:metadata, custom:author, custom:created

        # Check custom namespace elements
        custom_elements = [
            c for c in chunks if c["semantic_name"] in ["metadata", "author", "created"]
        ]
        if custom_elements:
            custom_chunk = custom_elements[0]
            assert custom_chunk["semantic_context"]["namespace"] in [
                "custom",
                "http://example.com/custom",
            ]

    def test_xml_cdata_sections(self, chunker):
        """Test parsing of XML CDATA sections."""
        content = dedent(
            """
            <document>
                <script>
                    <![CDATA[
                    function example() {
                        if (x < 5 && y > 10) {
                            console.log("Hello <world>");
                        }
                    }
                    ]]>
                </script>
                <description>
                    <![CDATA[
                    This text contains <special> characters & symbols
                    that would normally need to be escaped in XML.
                    ]]>
                </description>
            </document>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "cdata.xml")

        # Check for CDATA chunks
        cdata_chunks = [c for c in chunks if c["semantic_type"] == "cdata"]
        assert len(cdata_chunks) >= 2

        # Check CDATA content
        script_cdata = [
            c
            for c in cdata_chunks
            if "function example" in c["semantic_context"]["cdata_content"]
        ]
        assert len(script_cdata) >= 1
        script_chunk = script_cdata[0]
        assert "cdata_section" in script_chunk["semantic_language_features"]
        assert "raw_content" in script_chunk["semantic_language_features"]
        assert script_chunk["semantic_context"]["content_length"] > 50

    def test_xml_processing_instructions(self, chunker):
        """Test parsing of XML processing instructions."""
        content = dedent(
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <?xml-stylesheet type="text/xsl" href="style.xsl"?>
            <?custom-pi target="value" option="test"?>
            <root>
                <?php echo "Hello World"; ?>
                <content>Some content</content>
            </root>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "processing.xml")

        # Check for processing instruction chunks
        pi_chunks = [
            c for c in chunks if c["semantic_type"] == "processing_instruction"
        ]
        assert (
            len(pi_chunks) >= 2
        )  # xml-stylesheet and custom-pi (xml declaration handled separately)

        # Check stylesheet PI
        stylesheet_pi = [c for c in pi_chunks if c["semantic_name"] == "xml-stylesheet"]
        assert len(stylesheet_pi) >= 1
        stylesheet_chunk = stylesheet_pi[0]
        assert (
            "processing_instruction" in stylesheet_chunk["semantic_language_features"]
        )
        assert "xml_metadata" in stylesheet_chunk["semantic_language_features"]
        assert 'type="text/xsl"' in stylesheet_chunk["semantic_context"]["pi_data"]

        # Check custom PI
        custom_pi = [c for c in pi_chunks if c["semantic_name"] == "custom-pi"]
        assert len(custom_pi) >= 1

        # Check PHP PI
        php_pi = [c for c in pi_chunks if c["semantic_name"] == "php"]
        assert len(php_pi) >= 1

    def test_xml_comments(self, chunker):
        """Test parsing of XML comments."""
        content = dedent(
            """
            <!-- Main document structure -->
            <document>
                <!-- Header section -->
                <header>
                    <title>Document Title</title>
                </header>
                
                <!-- Content body with multiple sections -->
                <body>
                    <section id="intro">
                        <!-- TODO: Add introduction text -->
                        <p>Introduction paragraph</p>
                    </section>
                </body>
                
                <!-- Footer information -->
                <footer>
                    <copyright>2023 Example Corp</copyright>
                </footer>
            </document>
            <!-- End of document -->
            """
        ).strip()

        chunks = chunker.chunk_content(content, "comments.xml")

        # Check for comment chunks
        comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
        assert len(comment_chunks) >= 4

        # Check main comment
        main_comments = [
            c
            for c in comment_chunks
            if "Main document" in c["semantic_context"]["comment_content"]
        ]
        assert len(main_comments) >= 1
        main_comment = main_comments[0]
        assert "xml_comment" in main_comment["semantic_language_features"]

        # Check nested comments
        todo_comments = [
            c
            for c in comment_chunks
            if "TODO" in c["semantic_context"]["comment_content"]
        ]
        assert len(todo_comments) >= 1

    def test_xml_mixed_content(self, chunker):
        """Test parsing of XML with mixed content (text and elements)."""
        content = dedent(
            """
            <article>
                <title>Mixed Content Example</title>
                <p>This paragraph contains <em>emphasized text</em> and <strong>strong text</strong>.</p>
                <p>It also has a <a href="http://example.com">link</a> and some plain text.</p>
                <div>
                    Some text before the list:
                    <ul>
                        <li>First item</li>
                        <li>Second item with <code>inline code</code></li>
                    </ul>
                    And some text after the list.
                </div>
            </article>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "mixed.xml")

        # Check for text content chunks
        text_chunks = [c for c in chunks if c["semantic_type"] == "text"]
        assert len(text_chunks) >= 2  # Should capture meaningful text content

        # Check inline elements
        inline_elements = [
            c for c in chunks if c["semantic_name"] in ["em", "strong", "a", "code"]
        ]
        assert len(inline_elements) >= 4

        # Check that mixed content is handled properly
        p_chunks = [c for c in chunks if c["semantic_name"] == "p"]
        assert len(p_chunks) >= 2

        # Check content context
        text_content_chunks = [
            c for c in chunks if "has_text_content" in c["semantic_language_features"]
        ]
        assert len(text_content_chunks) >= 3

    def test_xml_nested_structure(self, chunker):
        """Test parsing of deeply nested XML structures."""
        content = dedent(
            """
            <library>
                <books>
                    <book id="1" isbn="978-0123456789">
                        <title>The Great Book</title>
                        <authors>
                            <author role="primary">
                                <name>John Doe</name>
                                <bio>
                                    <education>
                                        <degree>PhD</degree>
                                        <institution>University</institution>
                                    </education>
                                </bio>
                            </author>
                        </authors>
                        <chapters>
                            <chapter number="1" title="Introduction">
                                <sections>
                                    <section id="1.1" title="Overview"/>
                                    <section id="1.2" title="Objectives"/>
                                </sections>
                            </chapter>
                        </chapters>
                    </book>
                </books>
            </library>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "nested.xml")

        # Check deep nesting relationships
        assert len(chunks) >= 10

        # Check that parent-child relationships are maintained
        library_chunks = [c for c in chunks if c["semantic_name"] == "library"]
        assert len(library_chunks) >= 1
        library_path = library_chunks[0]["semantic_path"]

        # Check nested elements have correct parent paths
        nested_chunks = [
            c
            for c in chunks
            if c["semantic_parent"] and library_path in str(c["semantic_parent"])
        ]
        assert len(nested_chunks) >= 5

        # Check deeply nested elements
        degree_chunks = [c for c in chunks if c["semantic_name"] == "degree"]
        assert len(degree_chunks) >= 1
        degree_chunk = degree_chunks[0]
        # Should have multiple levels in the path
        path_parts = degree_chunk["semantic_path"].split(".")
        assert (
            len(path_parts) >= 6
        )  # library.books.book.authors.author.bio.education.degree

    def test_xml_dtd_and_prolog(self, chunker):
        """Test parsing of XML with DTD and prolog."""
        content = dedent(
            """
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" 
                "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
            <?xml-stylesheet type="text/css" href="style.css"?>
            <html xmlns="http://www.w3.org/1999/xhtml">
                <head>
                    <title>XHTML Document</title>
                </head>
                <body>
                    <p>Content here</p>
                </body>
            </html>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "dtd.xml")

        # Check XML declaration with all attributes
        decl_chunks = [c for c in chunks if c["semantic_type"] == "xml_declaration"]
        assert len(decl_chunks) >= 1
        decl_chunk = decl_chunks[0]
        assert decl_chunk["semantic_context"]["attributes"]["standalone"] == "yes"

        # Check for prolog or DTD handling
        prolog_chunks = [c for c in chunks if c["semantic_type"] == "prolog"]
        if prolog_chunks:
            assert len(prolog_chunks) >= 1
            prolog_chunk = prolog_chunks[0]
            assert "xml_prolog" in prolog_chunk["semantic_language_features"]
            assert "document_structure" in prolog_chunk["semantic_language_features"]

    def test_error_node_fallback(self, chunker):
        """Test ERROR node handling with regex fallback."""
        # Malformed XML that might create ERROR nodes
        content = dedent(
            """
            <root>
                <good-element>Good content</good-element>
                <broken-element attr=unquoted value>
                    Some content
                </broken-element>
                <!-- Good comment -->
                <another-good>More content</another-good>
                <unclosed-element>Content
                <!-- Missing closing tag -->
            </root>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "broken.xml")

        # Should still extract meaningful content even with errors
        assert len(chunks) >= 3

        # Check that good elements are still parsed
        good_chunks = [c for c in chunks if "good" in c["semantic_name"]]
        assert len(good_chunks) >= 2

        # Check that comments are preserved
        comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
        assert len(comment_chunks) >= 2

    def test_xml_special_characters_and_entities(self, chunker):
        """Test parsing XML with entities and special characters."""
        content = dedent(
            """
            <document>
                <text>Price: $99.99 &amp; free shipping!</text>
                <formula>x &lt; 5 &amp;&amp; y &gt; 10</formula>
                <copyright>&copy; 2023 Company &trade;</copyright>
                <unicode>Café résumé naïve</unicode>
                <custom>&custom-entity; &unknown;</custom>
            </document>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "entities.xml")

        # Should handle special characters without breaking
        assert len(chunks) >= 5

        # Check that content with entities is preserved
        text_chunks = [
            c for c in chunks if c["semantic_name"] in ["text", "formula", "copyright"]
        ]
        assert len(text_chunks) >= 3

        # Check that entities are preserved in content
        entity_content = [
            c for c in chunks if "&amp;" in c["text"] or "&lt;" in c["text"]
        ]
        assert len(entity_content) >= 1

    def test_xml_large_document(self, chunker):
        """Test parsing of a larger XML document."""
        content = dedent(
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <catalog xmlns="http://example.com/catalog">
                <metadata>
                    <title>Product Catalog</title>
                    <version>2.1</version>
                    <created>2023-01-01T00:00:00Z</created>
                </metadata>
                
                <categories>
                    <category id="electronics" name="Electronics">
                        <subcategories>
                            <subcategory id="phones" name="Mobile Phones"/>
                            <subcategory id="laptops" name="Laptops"/>
                        </subcategories>
                    </category>
                    <category id="books" name="Books">
                        <subcategories>
                            <subcategory id="fiction" name="Fiction"/>
                            <subcategory id="technical" name="Technical"/>
                        </subcategories>
                    </category>
                </categories>
                
                <products>
                    <product id="p001" category="electronics" subcategory="phones">
                        <name>Smartphone Pro</name>
                        <price currency="USD">899.99</price>
                        <description>
                            <![CDATA[
                            Latest smartphone with advanced features:
                            - 6.7" OLED display
                            - 128GB storage
                            - 5G connectivity
                            ]]>
                        </description>
                        <specifications>
                            <spec name="screen_size" value="6.7 inches"/>
                            <spec name="storage" value="128GB"/>
                            <spec name="connectivity" value="5G"/>
                        </specifications>
                    </product>
                </products>
            </catalog>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "catalog.xml")

        # Should handle large documents with complex structure
        assert len(chunks) >= 15

        # Check main sections
        catalog_chunks = [c for c in chunks if c["semantic_name"] == "catalog"]
        assert len(catalog_chunks) >= 1

        # Check namespace handling
        namespaced_chunks = [
            c for c in chunks if "namespaced" in c["semantic_language_features"]
        ]
        if namespaced_chunks:
            assert len(namespaced_chunks) >= 1

        # Check CDATA handling
        cdata_chunks = [c for c in chunks if c["semantic_type"] == "cdata"]
        assert len(cdata_chunks) >= 1

        # Check self-closing elements
        self_closing_chunks = [
            c for c in chunks if c["semantic_type"] == "self_closing_element"
        ]
        assert len(self_closing_chunks) >= 4  # subcategory and spec elements

    def test_fallback_parsing(self, chunker):
        """Test complete fallback parsing when tree-sitter fails."""
        # Extremely malformed XML
        content = dedent(
            """
            <root>
                <good>content</good>
                << broken >> syntax
                <!-- comment -->
                <another>element</another>
            </root>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "broken.xml")

        # Should create at least a fallback chunk
        assert len(chunks) >= 1

        # If fallback chunk is created, it should have document type
        if len(chunks) == 1 and chunks[0]["semantic_type"] == "document":
            assert chunks[0]["semantic_name"] == "broken"
            assert "fallback_chunk" in chunks[0]["semantic_language_features"]
        else:
            # Or should extract what it can
            element_chunks = [
                c
                for c in chunks
                if c["semantic_type"] in ["element", "self_closing_element"]
            ]
            comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
            assert len(element_chunks) >= 1 or len(comment_chunks) >= 1

    def test_xml_soap_envelope(self, chunker):
        """Test parsing of a SOAP XML envelope."""
        content = dedent(
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
                           xmlns:tns="http://example.com/service">
                <soap:Header>
                    <tns:Authentication>
                        <tns:Username>user123</tns:Username>
                        <tns:Password>secret</tns:Password>
                    </tns:Authentication>
                </soap:Header>
                <soap:Body>
                    <tns:GetUserRequest>
                        <tns:UserId>12345</tns:UserId>
                        <tns:IncludeDetails>true</tns:IncludeDetails>
                    </tns:GetUserRequest>
                </soap:Body>
            </soap:Envelope>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "soap.xml")

        # Check SOAP structure
        envelope_chunks = [c for c in chunks if c["semantic_name"] == "Envelope"]
        assert len(envelope_chunks) >= 1
        envelope_chunk = envelope_chunks[0]
        assert "namespaced" in envelope_chunk["semantic_language_features"]
        assert envelope_chunk["semantic_context"]["namespace"] in [
            "soap",
            "http://schemas.xmlsoap.org/soap/envelope/",
        ]

        # Check Header and Body
        header_chunks = [c for c in chunks if c["semantic_name"] == "Header"]
        body_chunks = [c for c in chunks if c["semantic_name"] == "Body"]
        assert len(header_chunks) >= 1
        assert len(body_chunks) >= 1

        # Check nested namespaced elements
        tns_elements = [
            c
            for c in chunks
            if c["semantic_context"].get("namespace")
            in ["tns", "http://example.com/service"]
        ]
        assert (
            len(tns_elements) >= 4
        )  # Authentication, Username, Password, GetUserRequest, etc.

    def test_xml_rss_feed(self, chunker):
        """Test parsing of an RSS XML feed."""
        content = dedent(
            """
            <?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
                <channel>
                    <title>Example News Feed</title>
                    <link>https://example.com</link>
                    <description>Latest news and updates</description>
                    <language>en-us</language>
                    
                    <item>
                        <title>Breaking News: Important Update</title>
                        <link>https://example.com/news/1</link>
                        <description>This is a summary of the news article.</description>
                        <pubDate>Mon, 01 Jan 2023 12:00:00 GMT</pubDate>
                        <guid isPermaLink="false">news-1-2023</guid>
                        <content:encoded>
                            <![CDATA[
                            <p>This is the full article content with <strong>HTML</strong> formatting.</p>
                            <p>It includes multiple paragraphs and can contain any HTML.</p>
                            ]]>
                        </content:encoded>
                    </item>
                    
                    <item>
                        <title>Another News Item</title>
                        <description>Brief description of the second news item.</description>
                        <pubDate>Sun, 31 Dec 2022 18:00:00 GMT</pubDate>
                    </item>
                </channel>
            </rss>
            """
        ).strip()

        chunks = chunker.chunk_content(content, "rss.xml")

        # Check RSS structure
        rss_chunks = [c for c in chunks if c["semantic_name"] == "rss"]
        assert len(rss_chunks) >= 1
        rss_chunk = rss_chunks[0]
        assert "has_attributes" in rss_chunk["semantic_language_features"]
        assert rss_chunk["semantic_context"]["attributes"]["version"] == "2.0"

        # Check channel information
        channel_chunks = [c for c in chunks if c["semantic_name"] == "channel"]
        assert len(channel_chunks) >= 1

        # Check items
        item_chunks = [c for c in chunks if c["semantic_name"] == "item"]
        assert len(item_chunks) >= 2

        # Check CDATA in content:encoded
        cdata_chunks = [c for c in chunks if c["semantic_type"] == "cdata"]
        assert len(cdata_chunks) >= 1
        cdata_chunk = cdata_chunks[0]
        assert "HTML" in cdata_chunk["semantic_context"]["cdata_content"]

        # Check namespaced elements
        content_encoded = [c for c in chunks if c["semantic_name"] == "encoded"]
        assert len(content_encoded) >= 1
