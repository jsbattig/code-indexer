"""
XML semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Handles XML elements, attributes, namespaces, CDATA, processing instructions, and comments.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class XmlSemanticParser(BaseTreeSitterParser):
    """Semantic parser for XML files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "xml")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (XML declaration, DTD, root element)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "prolog":
                    self._handle_prolog(child, constructs, lines, scope_stack)
                # Let the regular traversal handle elements

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle XML-specific AST node types."""
        if node_type == "element":
            self._handle_element(node, constructs, lines, scope_stack, content)
        elif node_type == "self_closing_tag":
            self._handle_self_closing_element(
                node, constructs, lines, scope_stack, content
            )
        elif node_type in [
            "PI",
            "StyleSheetPI",
        ]:  # Tree-sitter uses PI and StyleSheetPI for processing instructions
            self._handle_processing_instruction(node, constructs, lines, scope_stack)
        elif node_type == "Comment":  # Tree-sitter uses Comment for XML comments
            self._handle_comment(node, constructs, lines, scope_stack)
        elif node_type == "CDSect":  # Tree-sitter uses CDSect for CDATA sections
            self._handle_cdata(node, constructs, lines, scope_stack)
        elif node_type == "CharData":  # Tree-sitter uses CharData for text content
            self._handle_text_content(node, constructs, lines, scope_stack)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped."""
        # Skip children for elements since we handle traversal manually
        # Don't skip children for nodes that don't need scope management
        return node_type in [
            "element",  # We handle element children manually for proper scope management
            "CharData",  # Character data doesn't need child traversal
            "Comment",  # Comments don't need child traversal
            "CDSect",  # CDATA sections don't need child traversal
            "PI",  # Processing instructions don't need child traversal
            "StyleSheetPI",  # Stylesheet processing instructions don't need child traversal
        ]

    def _handle_xml_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle XML declaration."""
        decl_text = self._get_node_text(node, lines)

        # Extract version, encoding, standalone by looking at child nodes
        attributes = {}

        # Extract attributes from XMLDecl node structure
        for i, child in enumerate(node.children):
            if hasattr(child, "type"):
                if child.type == "version" and i + 3 < len(node.children):
                    # Pattern: version = " VersionNum "
                    version_node = node.children[i + 3]
                    if (
                        hasattr(version_node, "type")
                        and version_node.type == "VersionNum"
                    ):
                        attributes["version"] = self._get_node_text(version_node, lines)
                elif child.type == "encoding" and i + 3 < len(node.children):
                    # Pattern: encoding = " EncName "
                    enc_node = node.children[i + 3]
                    if hasattr(enc_node, "type") and enc_node.type == "EncName":
                        attributes["encoding"] = self._get_node_text(enc_node, lines)
                elif child.type == "standalone" and i + 3 < len(node.children):
                    # Pattern: standalone = " value "
                    standalone_node = node.children[i + 3]
                    if hasattr(standalone_node, "type"):
                        attributes["standalone"] = self._get_node_text(
                            standalone_node, lines
                        )

        constructs.append(
            {
                "type": "xml_declaration",
                "name": "xml_declaration",
                "path": "xml_declaration",
                "signature": decl_text.strip(),
                "parent": None,
                "scope": "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": decl_text,
                "context": {
                    "declaration_type": "xml",
                    "attributes": attributes,
                },
                "features": ["xml_declaration", "document_metadata"],
            }
        )

    def _handle_prolog(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle XML prolog (DTD, processing instructions, XML declaration)."""
        # Look for XMLDecl inside prolog
        for child in node.children:
            if hasattr(child, "type") and child.type == "XMLDecl":
                self._handle_xml_declaration(child, constructs, lines, scope_stack)

        # If prolog contains more than just XMLDecl, create a prolog chunk
        prolog_text = self._get_node_text(node, lines)
        if any(
            child.type != "XMLDecl" for child in node.children if hasattr(child, "type")
        ):
            constructs.append(
                {
                    "type": "prolog",
                    "name": "prolog",
                    "path": "prolog",
                    "signature": "XML Prolog",
                    "parent": None,
                    "scope": "document",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": prolog_text,
                    "context": {
                        "declaration_type": "prolog",
                    },
                    "features": ["xml_prolog", "document_structure"],
                }
            )

    def _handle_element(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle XML element nodes."""
        element_name = self._get_element_name(node, lines)
        if not element_name:
            return

        attributes = self._extract_element_attributes(node, lines)
        element_text = self._get_node_text(node, lines)

        # Check if this is a self-closing element
        is_self_closing = self._is_self_closing_element(node)

        if is_self_closing:
            # Handle as self-closing element
            self._handle_self_closing_element(
                node, constructs, lines, scope_stack, content
            )
            return

        # Check for namespace information using full element name
        full_element_name = self._get_full_element_name(node, lines)
        namespace = self._extract_namespace(
            full_element_name or element_name, attributes
        )

        # Determine element characteristics
        features = ["xml_element"]
        if namespace:
            features.append("namespaced")
        if attributes:
            features.append("has_attributes")
        if self._has_text_content(node, lines):
            features.append("has_text_content")
        if self._has_child_elements(node):
            features.append("has_child_elements")
        if element_name in ["root", "document"]:
            features.append("root_element")

        # Build path
        parent_path = ".".join(scope_stack) if scope_stack else None
        current_path = f"{parent_path}.{element_name}" if parent_path else element_name

        constructs.append(
            {
                "type": "element",
                "name": element_name,
                "path": current_path,
                "signature": self._build_element_signature(element_name, attributes),
                "parent": parent_path,
                "scope": "element" if scope_stack else "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": element_text,
                "context": {
                    "element_name": element_name,
                    "attributes": attributes,
                    "namespace": namespace,
                    "has_content": self._has_text_content(node, lines),
                },
                "features": features,
            }
        )

        # Add to scope stack, process children, then pop
        scope_stack.append(element_name)

        # Manually traverse children to ensure proper scope management
        for child in node.children:
            self._traverse_node(child, constructs, lines, scope_stack, content)

        scope_stack.pop()

    def _handle_self_closing_element(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle self-closing XML elements."""
        element_name = self._get_element_name(node, lines)
        if not element_name:
            return

        attributes = self._extract_element_attributes(node, lines)
        element_text = self._get_node_text(node, lines)

        # Check for namespace information using full element name
        full_element_name = self._get_full_element_name(node, lines)
        namespace = self._extract_namespace(
            full_element_name or element_name, attributes
        )

        features = ["xml_element", "self_closing"]
        if namespace:
            features.append("namespaced")
        if attributes:
            features.append("has_attributes")

        parent_path = ".".join(scope_stack) if scope_stack else None
        current_path = f"{parent_path}.{element_name}" if parent_path else element_name

        constructs.append(
            {
                "type": "self_closing_element",
                "name": element_name,
                "path": current_path,
                "signature": self._build_element_signature(
                    element_name, attributes, self_closing=True
                ),
                "parent": parent_path,
                "scope": "element" if scope_stack else "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": element_text,
                "context": {
                    "element_name": element_name,
                    "attributes": attributes,
                    "namespace": namespace,
                    "is_self_closing": True,
                },
                "features": features,
            }
        )

        # Note: Self-closing elements don't have children, so no scope management needed

    def _handle_processing_instruction(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle XML processing instructions."""
        pi_text = self._get_node_text(node, lines)

        # Extract PI target and data based on node type
        pi_target = "unknown"
        pi_data = ""

        if node.type == "PI":
            # Regular PI: <?target data?>
            for child in node.children:
                if hasattr(child, "type") and child.type == "PITarget":
                    pi_target = self._get_node_text(child, lines)
                    break
            # Extract data part (everything after target)
            pi_match = re.search(
                r"<\?" + re.escape(pi_target) + r"\s*(.*?)\?>", pi_text
            )
            if pi_match:
                pi_data = pi_match.group(1).strip()
        elif node.type == "StyleSheetPI":
            # StyleSheet PI: <?xml-stylesheet attr="value"?>
            pi_target = "xml-stylesheet"
            # Extract pseudo attributes as data
            pseudo_attrs = []
            for child in node.children:
                if hasattr(child, "type") and child.type == "PseudoAtt":
                    pseudo_attrs.append(self._get_node_text(child, lines))
            pi_data = " ".join(pseudo_attrs)
        else:
            # Fallback to regex extraction
            pi_match = re.search(r"<\?(\w+|\w+-\w+)\s*(.*?)\?>", pi_text)
            if pi_match:
                pi_target = pi_match.group(1)
                pi_data = pi_match.group(2).strip()

        parent_path = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "processing_instruction",
                "name": pi_target,
                "path": (
                    f"{parent_path}.?{pi_target}" if parent_path else f"?{pi_target}"
                ),
                "signature": f"<?{pi_target} {pi_data[:50]}{'...' if len(pi_data) > 50 else ''} ?>",
                "parent": parent_path,
                "scope": "element" if scope_stack else "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": pi_text,
                "context": {
                    "pi_target": pi_target,
                    "pi_data": pi_data,
                },
                "features": ["processing_instruction", "xml_metadata"],
            }
        )

    def _handle_comment(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle XML comments."""
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
                "features": ["xml_comment"],
            }
        )

    def _handle_cdata(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle CDATA sections."""
        cdata_text = self._get_node_text(node, lines)

        # Extract actual content from CData child node
        cdata_content = ""
        for child in node.children:
            if hasattr(child, "type") and child.type == "CData":
                cdata_content = self._get_node_text(child, lines).strip()
                break

        # Fallback to regex extraction if tree-sitter structure doesn't work
        if not cdata_content:
            cdata_content = (
                cdata_text.replace("<![CDATA[", "").replace("]]>", "").strip()
            )

        parent_path = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "cdata",
                "name": "cdata",
                "path": f"{parent_path}.cdata" if parent_path else "cdata",
                "signature": f"<![CDATA[{cdata_content[:50]}{'...' if len(cdata_content) > 50 else ''}]]>",
                "parent": parent_path,
                "scope": "element" if scope_stack else "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": cdata_text,
                "context": {
                    "cdata_content": cdata_content,
                    "content_length": len(cdata_content),
                },
                "features": ["cdata_section", "raw_content"],
            }
        )

    def _handle_text_content(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle text content (only if significant)."""
        text_content = self._get_node_text(node, lines).strip()

        # Only process text nodes with meaningful content
        if len(text_content) > 15 and not text_content.isspace():
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
        """Extract XML constructs from ERROR node text using regex fallback."""
        constructs = []
        error_text.split("\n")

        # XML-specific regex patterns
        patterns = {
            "element": r"<(\w+(?::\w+)?)([^>]*)>(.*?)</\1>",
            "self_closing": r"<(\w+(?::\w+)?)([^>]*)/\s*>",
            "processing_instruction": r"<\?(\w+)([^?]*)\?>",
            "comment": r"<!--(.*?)-->",
            "cdata": r"<!\[CDATA\[(.*?)\]\]>",
            "xml_declaration": r"<\?xml\s+([^?]+)\?>",
        }

        parent_path = ".".join(scope_stack) if scope_stack else None

        for pattern_type, pattern in patterns.items():
            for match in re.finditer(pattern, error_text, re.MULTILINE | re.DOTALL):
                line_offset = error_text[: match.start()].count("\n")
                line_num = start_line + line_offset

                if pattern_type == "element":
                    element_name = match.group(1)
                    attributes_text = match.group(2).strip()
                    content = match.group(3)

                    constructs.append(
                        {
                            "type": "element",
                            "name": element_name,
                            "path": (
                                f"{parent_path}.{element_name}"
                                if parent_path
                                else element_name
                            ),
                            "signature": f"<{element_name}{' ' + attributes_text if attributes_text else ''}>",
                            "parent": parent_path,
                            "scope": "element" if scope_stack else "document",
                            "line_start": line_num + 1,
                            "line_end": line_num + match.group(0).count("\n") + 1,
                            "text": match.group(0),
                            "context": {
                                "element_name": element_name,
                                "attributes_text": attributes_text,
                                "content": content,
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
                "element": r"<(\w+(?::\w+)?)([^>]*)>.*?</\1>",
                "self_closing": r"<(\w+(?::\w+)?)([^>]*)/\s*>",
                "comment": r"<!--(.*?)-->",
                "processing_instruction": r"<\?(\w+)([^?]*)\?>",
                "cdata": r"<!\[CDATA\[(.*?)\]\]>",
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
                semantic_signature=f"XML document {Path(file_path).stem}",
                semantic_parent=None,
                semantic_context={"fallback_parsing": True},
                semantic_scope="document",
                semantic_language_features=["fallback_chunk"],
            )
        ]

    # Utility methods for XML parsing

    def _get_element_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract element name from an element node (local name only)."""
        full_name = self._get_full_element_name(node, lines)
        if full_name and ":" in full_name:
            return full_name.split(":", 1)[1]
        return full_name

    def _get_full_element_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract full element name from an element node (including namespace prefix)."""
        # Look for STag (start tag) or EmptyElemTag (self-closing)
        for child in node.children:
            if hasattr(child, "type") and child.type in ["STag", "EmptyElemTag"]:
                # Look for Name child node
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "Name":
                        return self._get_node_text(grandchild, lines)
        return None

    def _extract_element_attributes(
        self, node: Any, lines: List[str]
    ) -> Dict[str, str]:
        """Extract attributes from an element node."""
        attributes = {}

        # Look for STag (start tag) or EmptyElemTag (self-closing)
        for child in node.children:
            if hasattr(child, "type") and child.type in ["STag", "EmptyElemTag"]:
                # Look for Attribute nodes
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "Attribute":
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
                if child.type == "Name":
                    name = self._get_node_text(child, lines)
                elif child.type == "AttValue":
                    # AttValue contains quoted strings, extract the inner content
                    att_value_text = self._get_node_text(child, lines)
                    # Remove surrounding quotes
                    if att_value_text.startswith('"') and att_value_text.endswith('"'):
                        value = att_value_text[1:-1]
                    elif att_value_text.startswith("'") and att_value_text.endswith(
                        "'"
                    ):
                        value = att_value_text[1:-1]
                    else:
                        value = att_value_text

        return name, value

    def _build_element_signature(
        self, element_name: str, attributes: Dict[str, str], self_closing: bool = False
    ) -> str:
        """Build a signature string for an XML element."""
        if not attributes:
            return f"<{element_name}{'/' if self_closing else ''}>"

        attr_parts = []
        for key, value in attributes.items():
            if value:
                attr_parts.append(f'{key}="{value}"')
            else:
                attr_parts.append(key)

        return f"<{element_name} {' '.join(attr_parts)}{'/' if self_closing else ''}>"

    def _extract_namespace(
        self, element_name: str, attributes: Dict[str, str]
    ) -> Optional[str]:
        """Extract namespace information from element name and attributes."""
        if ":" in element_name:
            return element_name.split(":")[0]

        # Check for default namespace
        if "xmlns" in attributes:
            return attributes["xmlns"]

        # Check for prefixed namespaces
        for attr_name, attr_value in attributes.items():
            if attr_name.startswith("xmlns:"):
                prefix = attr_name.split(":")[1]
                if element_name.startswith(f"{prefix}:"):
                    return attr_value

        return None

    def _is_root_element(self, node: Any) -> bool:
        """Check if this is the root element of the document."""
        # This is a simplified check - in a real implementation,
        # you'd check the node's position in the document
        return True

    def _is_self_closing_element(self, node: Any) -> bool:
        """Check if this element is self-closing by looking for EmptyElemTag."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "EmptyElemTag":
                return True
        return False

    def _has_text_content(self, node: Any, lines: List[str]) -> bool:
        """Check if element has meaningful text content."""
        # Look for CharData nodes in the content child
        for child in node.children:
            if hasattr(child, "type") and child.type == "content":
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "CharData":
                        text = self._get_node_text(grandchild, lines).strip()
                        if text and not text.isspace():
                            return True
        return False

    def _has_child_elements(self, node: Any) -> bool:
        """Check if element has child elements."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "element":
                return True
        return False

    def _extract_xml_decl_attributes(self, decl_text: str) -> Dict[str, str]:
        """Extract attributes from XML declaration."""
        attributes = {}

        # Extract version
        version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', decl_text)
        if version_match:
            attributes["version"] = version_match.group(1)

        # Extract encoding
        encoding_match = re.search(r'encoding\s*=\s*["\']([^"\']+)["\']', decl_text)
        if encoding_match:
            attributes["encoding"] = encoding_match.group(1)

        # Extract standalone
        standalone_match = re.search(r'standalone\s*=\s*["\']([^"\']+)["\']', decl_text)
        if standalone_match:
            attributes["standalone"] = standalone_match.group(1)

        return attributes
