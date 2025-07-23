"""
HTML semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Handles HTML elements, attributes, script/style blocks, comments, and document structure.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class HtmlSemanticParser(BaseTreeSitterParser):
    """Semantic parser for HTML files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "html")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (DOCTYPE, html root)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "doctype":
                    doctype_text = self._get_node_text(child, lines)
                    constructs.append(
                        {
                            "type": "doctype",
                            "name": "DOCTYPE",
                            "path": "DOCTYPE",
                            "signature": doctype_text.strip(),
                            "parent": None,
                            "scope": "document",
                            "line_start": child.start_point[0] + 1,
                            "line_end": child.end_point[0] + 1,
                            "text": doctype_text,
                            "context": {"declaration_type": "doctype"},
                            "features": ["document_type"],
                        }
                    )
                elif (
                    child.type == "element"
                    and self._get_element_tag(child, lines) == "html"
                ):
                    scope_stack.append("html")
                    html_text = self._get_node_text(child, lines)
                    constructs.append(
                        {
                            "type": "element",
                            "name": "html",
                            "path": "html",
                            "signature": "<html>",
                            "parent": None,
                            "scope": "document",
                            "line_start": child.start_point[0] + 1,
                            "line_end": child.end_point[0] + 1,
                            "text": html_text,
                            "context": {
                                "tag_name": "html",
                                "attributes": self._extract_attributes(child, lines),
                                "is_root": True,
                            },
                            "features": ["root_element", "document_structure"],
                        }
                    )

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle HTML-specific AST node types."""
        if node_type == "element":
            self._handle_element(node, constructs, lines, scope_stack, content)
        elif node_type == "script_element":
            self._handle_script_element(node, constructs, lines, scope_stack, content)
        elif node_type == "style_element":
            self._handle_style_element(node, constructs, lines, scope_stack, content)
        elif node_type == "comment":
            self._handle_comment(node, constructs, lines, scope_stack)
        elif node_type == "text":
            self._handle_text_node(node, constructs, lines, scope_stack)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped."""
        # Don't skip children for most HTML nodes as we need to traverse the tree
        return node_type in ["text", "comment"]

    def _handle_element(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle HTML element nodes."""
        tag_name = self._get_element_tag(node, lines)
        if not tag_name:
            return

        # Skip if already handled as root html element
        if tag_name == "html" and not scope_stack:
            return

        attributes = self._extract_attributes(node, lines)
        element_text = self._get_node_text(node, lines)

        # Determine if this is a structural element
        structural_tags = {
            "head",
            "body",
            "header",
            "nav",
            "main",
            "section",
            "article",
            "aside",
            "footer",
        }
        semantic_tags = {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "div",
            "span",
            "form",
            "table",
        }

        features = []
        if tag_name in structural_tags:
            features.append("structural")
        if tag_name in semantic_tags:
            features.append("semantic")
        if attributes.get("id"):
            features.append("has_id")
        if attributes.get("class"):
            features.append("has_class")
        if self._is_self_closing_tag(tag_name):
            features.append("self_closing")

        # Build path
        parent_path = ".".join(scope_stack) if scope_stack else None
        current_path = f"{parent_path}.{tag_name}" if parent_path else tag_name

        constructs.append(
            {
                "type": "element",
                "name": tag_name,
                "path": current_path,
                "signature": self._build_element_signature(tag_name, attributes),
                "parent": parent_path,
                "scope": "element" if scope_stack else "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": element_text,
                "context": {
                    "tag_name": tag_name,
                    "attributes": attributes,
                    "is_structural": tag_name in structural_tags,
                    "is_semantic": tag_name in semantic_tags,
                },
                "features": features,
            }
        )

        # Add to scope stack for children
        scope_stack.append(tag_name)

    def _handle_script_element(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle script elements specially."""
        attributes = self._extract_attributes(node, lines)
        script_text = self._get_node_text(node, lines)

        # Extract script content
        script_content = self._extract_script_content(node, lines)

        features = ["script_block"]
        if attributes.get("src"):
            features.append("external_script")
        else:
            features.append("inline_script")
        if attributes.get("type"):
            features.append(f"type_{attributes['type']}")

        parent_path = ".".join(scope_stack) if scope_stack else None
        current_path = f"{parent_path}.script" if parent_path else "script"

        constructs.append(
            {
                "type": "script",
                "name": "script",
                "path": current_path,
                "signature": self._build_element_signature("script", attributes),
                "parent": parent_path,
                "scope": "element",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": script_text,
                "context": {
                    "tag_name": "script",
                    "attributes": attributes,
                    "script_content": script_content,
                    "is_external": bool(attributes.get("src")),
                },
                "features": features,
            }
        )

    def _handle_style_element(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle style elements specially."""
        attributes = self._extract_attributes(node, lines)
        style_text = self._get_node_text(node, lines)

        # Extract CSS content
        css_content = self._extract_style_content(node, lines)

        features = ["style_block", "inline_css"]
        if attributes.get("type"):
            features.append(f"type_{attributes['type']}")

        parent_path = ".".join(scope_stack) if scope_stack else None
        current_path = f"{parent_path}.style" if parent_path else "style"

        constructs.append(
            {
                "type": "style",
                "name": "style",
                "path": current_path,
                "signature": self._build_element_signature("style", attributes),
                "parent": parent_path,
                "scope": "element",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": style_text,
                "context": {
                    "tag_name": "style",
                    "attributes": attributes,
                    "css_content": css_content,
                },
                "features": features,
            }
        )

    def _handle_comment(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle HTML comments."""
        comment_text = self._get_node_text(node, lines)
        comment_content = comment_text.strip("<!--").strip("-->").strip()

        parent_path = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "comment",
                "name": "comment",
                "path": f"{parent_path}.comment" if parent_path else "comment",
                "signature": f"<!-- {comment_content[:50]}{'...' if len(comment_content) > 50 else ''} -->",
                "parent": parent_path,
                "scope": "element" if scope_stack else "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": comment_text,
                "context": {
                    "comment_content": comment_content,
                },
                "features": ["html_comment"],
            }
        )

    def _handle_text_node(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle text nodes (only if they contain significant content)."""
        text_content = self._get_node_text(node, lines).strip()

        # Only process text nodes with meaningful content
        if len(text_content) > 20 and not text_content.isspace():
            parent_path = ".".join(scope_stack) if scope_stack else None

            constructs.append(
                {
                    "type": "text",
                    "name": "text_content",
                    "path": f"{parent_path}.text" if parent_path else "text",
                    "signature": f"Text: {text_content[:50]}{'...' if len(text_content) > 50 else ''}",
                    "parent": parent_path,
                    "scope": "element" if scope_stack else "document",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": text_content,
                    "context": {
                        "content_length": len(text_content),
                    },
                    "features": ["text_content"],
                }
            )

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract HTML constructs from ERROR node text using regex fallback."""
        constructs = []
        error_text.split("\n")

        # HTML-specific regex patterns
        patterns = {
            "element": r"<(\w+)([^>]*)>",
            "self_closing": r"<(\w+)([^>]*)/\s*>",
            "closing_tag": r"</(\w+)>",
            "comment": r"<!--(.*?)-->",
            "doctype": r"<!DOCTYPE\s+[^>]+>",
        }

        parent_path = ".".join(scope_stack) if scope_stack else None

        for pattern_type, pattern in patterns.items():
            for match in re.finditer(pattern, error_text, re.MULTILINE | re.DOTALL):
                line_offset = error_text[: match.start()].count("\n")
                line_num = start_line + line_offset

                if pattern_type == "element":
                    tag_name = match.group(1)
                    attributes_text = match.group(2).strip()

                    constructs.append(
                        {
                            "type": "element",
                            "name": tag_name,
                            "path": (
                                f"{parent_path}.{tag_name}" if parent_path else tag_name
                            ),
                            "signature": f"<{tag_name}{' ' + attributes_text if attributes_text else ''}>",
                            "parent": parent_path,
                            "scope": "element" if scope_stack else "document",
                            "line_start": line_num + 1,
                            "line_end": line_num + match.group(0).count("\n") + 1,
                            "text": match.group(0),
                            "context": {
                                "tag_name": tag_name,
                                "attributes_text": attributes_text,
                                "extracted_from_error": True,
                            },
                            "features": ["element_fallback"],
                        }
                    )
                elif pattern_type == "comment":
                    comment_content = match.group(1).strip()

                    constructs.append(
                        {
                            "type": "comment",
                            "name": "comment",
                            "path": (
                                f"{parent_path}.comment" if parent_path else "comment"
                            ),
                            "signature": f"<!-- {comment_content[:50]}{'...' if len(comment_content) > 50 else ''} -->",
                            "parent": parent_path,
                            "scope": "element" if scope_stack else "document",
                            "line_start": line_num + 1,
                            "line_end": line_num + match.group(0).count("\n") + 1,
                            "text": match.group(0),
                            "context": {
                                "comment_content": comment_content,
                                "extracted_from_error": True,
                            },
                            "features": ["comment_fallback"],
                        }
                    )

        return constructs

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        chunks = []
        content.split("\n")
        file_ext = Path(file_path).suffix

        # Extract constructs using regex patterns
        constructs = self._find_constructs_with_regex(
            content,
            {
                "element": r"<(\w+)([^>]*)>.*?</\1>",
                "self_closing": r"<(\w+)([^>]*)/\s*>",
                "comment": r"<!--(.*?)-->",
                "doctype": r"<!DOCTYPE\s+[^>]+>",
            },
            file_path,
        )

        # Create semantic chunks
        for i, construct in enumerate(constructs):
            chunk = SemanticChunk(
                text=construct["text"],
                chunk_index=i,
                total_chunks=len(constructs),
                size=len(construct["text"]),
                file_path=file_path,
                file_extension=file_ext,
                line_start=construct["line_start"],
                line_end=construct["line_end"],
                semantic_chunking=False,
                semantic_type=construct["type"],
                semantic_name=construct["name"],
                semantic_path=construct.get("path", construct["name"]),
                semantic_signature=construct.get("signature", ""),
                semantic_parent=construct.get("parent"),
                semantic_context=construct.get("context", {}),
                semantic_scope=construct.get("scope", "document"),
                semantic_language_features=construct.get("features", []),
            )
            chunks.append(chunk)

        return chunks if chunks else self._create_fallback_chunk(content, file_path)

    def _create_fallback_chunk(
        self, content: str, file_path: str
    ) -> List[SemanticChunk]:
        """Create a single fallback chunk when no constructs are found."""
        lines = content.split("\n")
        return [
            SemanticChunk(
                text=content,
                chunk_index=0,
                total_chunks=1,
                size=len(content),
                file_path=file_path,
                file_extension=Path(file_path).suffix,
                line_start=1,
                line_end=len(lines),
                semantic_chunking=False,
                semantic_type="document",
                semantic_name=Path(file_path).stem,
                semantic_path=Path(file_path).stem,
                semantic_signature=f"HTML document {Path(file_path).stem}",
                semantic_parent=None,
                semantic_context={"fallback_parsing": True},
                semantic_scope="document",
                semantic_language_features=["fallback_chunk"],
            )
        ]

    # Utility methods for HTML parsing

    def _get_element_tag(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract tag name from an element node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "start_tag":
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "tag_name":
                        return self._get_node_text(grandchild, lines)
        return None

    def _extract_attributes(self, node: Any, lines: List[str]) -> Dict[str, str]:
        """Extract attributes from an element node."""
        attributes = {}

        for child in node.children:
            if hasattr(child, "type") and child.type == "start_tag":
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "attribute":
                        attr_name, attr_value = self._parse_attribute(grandchild, lines)
                        if attr_name:
                            attributes[attr_name] = attr_value or ""

        return attributes

    def _parse_attribute(
        self, attr_node: Any, lines: List[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Parse an attribute node to extract name and value."""
        name = None
        value = None

        for child in attr_node.children:
            if hasattr(child, "type"):
                if child.type == "attribute_name":
                    name = self._get_node_text(child, lines)
                elif child.type == "attribute_value":
                    value = self._get_node_text(child, lines).strip("\"'")
                elif child.type == "quoted_attribute_value":
                    # Look for attribute_value inside quoted_attribute_value
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "attribute_value"
                        ):
                            value = self._get_node_text(grandchild, lines)
                            break

        return name, value

    def _build_element_signature(
        self, tag_name: str, attributes: Dict[str, str]
    ) -> str:
        """Build a signature string for an HTML element."""
        if not attributes:
            return f"<{tag_name}>"

        attr_parts = []
        for key, value in attributes.items():
            if value:
                attr_parts.append(f'{key}="{value}"')
            else:
                attr_parts.append(key)

        return f"<{tag_name} {' '.join(attr_parts)}>"

    def _is_self_closing_tag(self, tag_name: str) -> bool:
        """Check if a tag is self-closing."""
        self_closing_tags = {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
        return tag_name.lower() in self_closing_tags

    def _extract_script_content(self, node: Any, lines: List[str]) -> str:
        """Extract JavaScript content from a script element."""
        # Look for raw_text content within the script element
        for child in node.children:
            if hasattr(child, "type") and child.type == "raw_text":
                return self._get_node_text(child, lines).strip()
        return ""

    def _extract_style_content(self, node: Any, lines: List[str]) -> str:
        """Extract CSS content from a style element."""
        # Look for raw_text content within the style element
        for child in node.children:
            if hasattr(child, "type") and child.type == "raw_text":
                return self._get_node_text(child, lines).strip()
        return ""
