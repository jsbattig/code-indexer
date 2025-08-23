"""
YAML semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Handles key-value mappings, sequences, nested structures, anchors, and aliases.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class YamlSemanticParser(BaseTreeSitterParser):
    """Semantic parser for YAML files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "yaml")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (document markers, directives)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "document":
                    # Handle YAML document
                    self._handle_document(child, constructs, lines, scope_stack)
                elif child.type == "directive":
                    # Handle YAML directives like %YAML 1.2
                    self._handle_directive(child, constructs, lines, scope_stack)

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle YAML-specific AST node types."""
        if node_type == "block_mapping":
            self._handle_block_mapping(node, constructs, lines, scope_stack, content)
        elif node_type == "flow_mapping":
            self._handle_flow_mapping(node, constructs, lines, scope_stack, content)
        elif node_type == "block_sequence":
            self._handle_block_sequence(node, constructs, lines, scope_stack, content)
        elif node_type == "flow_sequence":
            self._handle_flow_sequence(node, constructs, lines, scope_stack, content)
        elif node_type in ["pair", "block_mapping_pair", "flow_pair"]:
            self._handle_pair(node, constructs, lines, scope_stack, content)
        elif node_type == "anchor":
            self._handle_anchor(node, constructs, lines, scope_stack)
        elif node_type == "alias":
            self._handle_alias(node, constructs, lines, scope_stack)
        elif node_type == "comment":
            self._handle_comment(node, constructs, lines, scope_stack)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped."""
        # Skip children for leaf nodes that don't contain other structures
        return node_type in [
            "plain_scalar",
            "double_quote_scalar",
            "single_quote_scalar",
            "literal_scalar",
            "folded_scalar",
            "comment",
            "alias",
        ]

    def _handle_document(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle YAML document."""
        document_text = self._get_node_text(node, lines)

        # Check if this document starts with directives and extract them first
        document_lines = document_text.split("\n")

        for i, line in enumerate(document_lines):
            line = line.strip()
            if line.startswith("%"):
                # Found a directive, extract it
                if line.startswith("%YAML"):
                    match = re.match(r"%YAML\s+(.+)", line)
                    if match:
                        version = match.group(1)
                        constructs.append(
                            {
                                "type": "directive",
                                "name": "YAML",
                                "path": "%YAML",
                                "signature": line,
                                "parent": None,
                                "scope": "global",
                                "line_start": node.start_point[0] + i + 1,
                                "line_end": node.start_point[0] + i + 1,
                                "text": line,
                                "context": {
                                    "directive_name": "YAML",
                                    "directive_value": version,
                                },
                                "features": ["yaml_directive"],
                            }
                        )
                elif line.startswith("%TAG"):
                    match = re.match(r"%TAG\s+(.+)", line)
                    if match:
                        tag_info = match.group(1)
                        constructs.append(
                            {
                                "type": "directive",
                                "name": "TAG",
                                "path": "%TAG",
                                "signature": line,
                                "parent": None,
                                "scope": "global",
                                "line_start": node.start_point[0] + i + 1,
                                "line_end": node.start_point[0] + i + 1,
                                "text": line,
                                "context": {
                                    "directive_name": "TAG",
                                    "directive_value": tag_info,
                                },
                                "features": ["yaml_directive"],
                            }
                        )
            elif line.startswith("---") or (line and not line.startswith("%")):
                # Found actual document content, stop looking for directives
                break

        constructs.append(
            {
                "type": "document",
                "name": "document",
                "path": "document",
                "signature": "YAML Document",
                "parent": None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": document_text,
                "context": {
                    "document_type": "yaml",
                },
                "features": ["yaml_document"],
            }
        )

        scope_stack.append("document")

    def _handle_directive(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle YAML directives."""
        directive_text = self._get_node_text(node, lines)

        # Extract directive name and value
        directive_match = re.search(r"%(\w+)\s+(.*)", directive_text)
        if directive_match:
            directive_name = directive_match.group(1)
            directive_value = directive_match.group(2)
        else:
            directive_name = "unknown"
            directive_value = directive_text

        constructs.append(
            {
                "type": "directive",
                "name": directive_name,
                "path": f"%{directive_name}",
                "signature": directive_text.strip(),
                "parent": None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": directive_text,
                "context": {
                    "directive_name": directive_name,
                    "directive_value": directive_value,
                },
                "features": ["yaml_directive"],
            }
        )

    def _handle_block_mapping(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle YAML block mappings (key-value pairs)."""
        mapping_text = self._get_node_text(node, lines)

        # Extract keys from the mapping
        keys = self._extract_mapping_keys(node, lines)

        # Determine if this is a root-level mapping or nested
        is_root = len(scope_stack) <= 1

        features = ["block_mapping"]
        if is_root:
            features.append("root_mapping")
        if len(keys) > 5:
            features.append("large_mapping")

        parent_path = ".".join(scope_stack) if scope_stack else None
        # Use more descriptive naming that includes key information
        if len(keys) > 0:
            if len(keys) == 1:
                mapping_name = f"{keys[0]}_mapping"
            else:
                # Use first key as primary identifier with count
                mapping_name = f"{keys[0]}_and_{len(keys) - 1}_more"
        else:
            mapping_name = "mapping"
        current_path = f"{parent_path}.{mapping_name}" if parent_path else mapping_name

        constructs.append(
            {
                "type": "mapping",
                "name": mapping_name,
                "path": current_path,
                "signature": f"{{ {', '.join(keys[:3])}{'...' if len(keys) > 3 else ''} }}",
                "parent": parent_path,
                "scope": "mapping" if scope_stack else "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": mapping_text,
                "context": {
                    "keys": keys,
                    "key_count": len(keys),
                    "mapping_type": "block",
                },
                "features": features,
            }
        )

        # Add mapping to scope
        scope_stack.append(mapping_name)

    def _handle_flow_mapping(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle YAML flow mappings ({key: value})."""
        mapping_text = self._get_node_text(node, lines)

        # Extract keys from the mapping
        keys = self._extract_mapping_keys(node, lines)

        features = ["flow_mapping", "inline_mapping"]
        if len(keys) > 3:
            features.append("complex_mapping")

        parent_path = ".".join(scope_stack) if scope_stack else None
        # Use more descriptive naming for flow mappings
        if len(keys) > 0:
            if len(keys) == 1:
                mapping_name = f"{keys[0]}_flow"
            elif len(keys) <= 3:
                mapping_name = f"flow_{len(keys)}_keys"
            else:
                # Use first key as primary identifier for large mappings
                mapping_name = f"{keys[0]}_flow_mapping"
        else:
            mapping_name = "flow_mapping"
        current_path = f"{parent_path}.{mapping_name}" if parent_path else mapping_name

        constructs.append(
            {
                "type": "flow_mapping",
                "name": mapping_name,
                "path": current_path,
                "signature": f"{{{', '.join(keys[:3])}{'...' if len(keys) > 3 else ''}}}",
                "parent": parent_path,
                "scope": "mapping",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": mapping_text,
                "context": {
                    "keys": keys,
                    "key_count": len(keys),
                    "mapping_type": "flow",
                },
                "features": features,
            }
        )

    def _handle_block_sequence(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle YAML block sequences (arrays)."""
        sequence_text = self._get_node_text(node, lines)

        # Count sequence items
        item_count = self._count_sequence_items(node, lines)

        features = ["block_sequence", "array"]
        if item_count > 10:
            features.append("large_sequence")

        parent_path = ".".join(scope_stack) if scope_stack else None
        sequence_name = f"sequence_{item_count}_items"
        current_path = (
            f"{parent_path}.{sequence_name}" if parent_path else sequence_name
        )

        constructs.append(
            {
                "type": "sequence",
                "name": sequence_name,
                "path": current_path,
                "signature": f"[{item_count} items]",
                "parent": parent_path,
                "scope": "sequence",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": sequence_text,
                "context": {
                    "item_count": item_count,
                    "sequence_type": "block",
                },
                "features": features,
            }
        )

        # Add sequence to scope
        scope_stack.append(sequence_name)

    def _handle_flow_sequence(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle YAML flow sequences ([item1, item2])."""
        sequence_text = self._get_node_text(node, lines)

        # Count sequence items
        item_count = self._count_sequence_items(node, lines)

        features = ["flow_sequence", "inline_array"]
        if item_count > 5:
            features.append("complex_sequence")

        parent_path = ".".join(scope_stack) if scope_stack else None
        sequence_name = f"flow_sequence_{item_count}_items"
        current_path = (
            f"{parent_path}.{sequence_name}" if parent_path else sequence_name
        )

        constructs.append(
            {
                "type": "flow_sequence",
                "name": sequence_name,
                "path": current_path,
                "signature": f"[{item_count} items]",
                "parent": parent_path,
                "scope": "sequence",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": sequence_text,
                "context": {
                    "item_count": item_count,
                    "sequence_type": "flow",
                },
                "features": features,
            }
        )

    def _handle_pair(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle YAML key-value pairs."""
        pair_text = self._get_node_text(node, lines)

        # Extract key and value
        key, value = self._extract_key_value(node, lines)

        if not key:
            return

        # Determine value type
        value_type = self._determine_value_type(value)

        features = ["key_value_pair"]
        features.append(f"value_type_{value_type}")

        if self._is_config_key(key):
            features.append("configuration")
        if key.startswith("_") or key.endswith("_"):
            features.append("special_key")

        parent_path = ".".join(scope_stack) if scope_stack else None
        current_path = f"{parent_path}.{key}" if parent_path else key

        constructs.append(
            {
                "type": "pair",
                "name": key,
                "path": current_path,
                "signature": f"{key}: {self._truncate_value(value)}",
                "parent": parent_path,
                "scope": "mapping" if scope_stack else "document",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": pair_text,
                "context": {
                    "key": key,
                    "value": value,
                    "value_type": value_type,
                },
                "features": features,
            }
        )

        # Add key to scope if it contains nested structures
        if value_type in ["mapping", "sequence"]:
            scope_stack.append(key)

    def _handle_anchor(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle YAML anchors (&anchor)."""
        anchor_text = self._get_node_text(node, lines)
        anchor_name = anchor_text.lstrip("&")

        parent_path = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "anchor",
                "name": anchor_name,
                "path": (
                    f"{parent_path}.&{anchor_name}"
                    if parent_path
                    else f"&{anchor_name}"
                ),
                "signature": f"&{anchor_name}",
                "parent": parent_path,
                "scope": "reference",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": anchor_text,
                "context": {
                    "anchor_name": anchor_name,
                },
                "features": ["yaml_anchor", "reference_definition"],
            }
        )

    def _handle_alias(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle YAML aliases (*alias)."""
        alias_text = self._get_node_text(node, lines)
        alias_name = alias_text.lstrip("*")

        parent_path = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "alias",
                "name": alias_name,
                "path": (
                    f"{parent_path}.*{alias_name}" if parent_path else f"*{alias_name}"
                ),
                "signature": f"*{alias_name}",
                "parent": parent_path,
                "scope": "reference",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": alias_text,
                "context": {
                    "alias_name": alias_name,
                },
                "features": ["yaml_alias", "reference_usage"],
            }
        )

    def _handle_comment(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle YAML comments."""
        comment_text = self._get_node_text(node, lines)
        comment_content = comment_text.lstrip("#").strip()

        # Only process significant comments
        if len(comment_content.strip()) > 5:
            parent_path = ".".join(scope_stack) if scope_stack else None

            constructs.append(
                {
                    "type": "comment",
                    "name": "comment",
                    "path": f"{parent_path}.comment" if parent_path else "comment",
                    "signature": f"# {comment_content[:50]}{'...' if len(comment_content) > 50 else ''}",
                    "parent": parent_path,
                    "scope": "document" if not scope_stack else "nested",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": comment_text,
                    "context": {
                        "comment_content": comment_content,
                    },
                    "features": ["yaml_comment"],
                }
            )

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract YAML constructs from ERROR node text using regex fallback."""
        constructs = []
        lines = error_text.split("\n")

        # YAML-specific regex patterns
        patterns = {
            "yaml_directive": r"^%YAML\s+(.+)$",
            "tag_directive": r"^%TAG\s+(.+)$",
            "key_value": r"^(\s*)([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$",
            "sequence_item": r"^(\s*)-\s+(.+)$",
            "anchor": r"(&[a-zA-Z_][a-zA-Z0-9_-]*)",
            "alias": r"(\*[a-zA-Z_][a-zA-Z0-9_-]*)",
            "comment": r"#(.*)$",
        }

        parent_path = ".".join(scope_stack) if scope_stack else None

        for line_num, line in enumerate(lines):
            for pattern_type, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    line_offset = start_line + line_num

                    if pattern_type == "yaml_directive":
                        version = match.group(1)
                        constructs.append(
                            {
                                "type": "directive",
                                "name": "YAML",
                                "path": "%YAML",
                                "signature": f"%YAML {version}",
                                "parent": None,
                                "scope": "global",
                                "line_start": line_offset + 1,
                                "line_end": line_offset + 1,
                                "text": line,
                                "context": {
                                    "directive_name": "YAML",
                                    "directive_value": version,
                                    "extracted_from_error": True,
                                },
                                "features": ["yaml_directive"],
                            }
                        )
                    elif pattern_type == "tag_directive":
                        tag_info = match.group(1)
                        constructs.append(
                            {
                                "type": "directive",
                                "name": "TAG",
                                "path": "%TAG",
                                "signature": f"%TAG {tag_info}",
                                "parent": None,
                                "scope": "global",
                                "line_start": line_offset + 1,
                                "line_end": line_offset + 1,
                                "text": line,
                                "context": {
                                    "directive_name": "TAG",
                                    "directive_value": tag_info,
                                    "extracted_from_error": True,
                                },
                                "features": ["yaml_directive"],
                            }
                        )
                    elif pattern_type == "key_value":
                        indent = match.group(1)
                        key = match.group(2)
                        value = match.group(3).strip()

                        constructs.append(
                            {
                                "type": "pair",
                                "name": key,
                                "path": f"{parent_path}.{key}" if parent_path else key,
                                "signature": f"{key}: {self._truncate_value(value)}",
                                "parent": parent_path,
                                "scope": "mapping",
                                "line_start": line_offset + 1,
                                "line_end": line_offset + 1,
                                "text": line,
                                "context": {
                                    "key": key,
                                    "value": value,
                                    "indent": len(indent),
                                    "extracted_from_error": True,
                                },
                                "features": ["pair_fallback"],
                            }
                        )
                    elif pattern_type == "comment":
                        comment_content = match.group(1).strip()

                        constructs.append(
                            {
                                "type": "comment",
                                "name": "comment",
                                "path": (
                                    f"{parent_path}.comment"
                                    if parent_path
                                    else "comment"
                                ),
                                "signature": f"# {comment_content[:50]}{'...' if len(comment_content) > 50 else ''}",
                                "parent": parent_path,
                                "scope": "document",
                                "line_start": line_offset + 1,
                                "line_end": line_offset + 1,
                                "text": line,
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
                "key_value": r"^(\s*)([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$",
                "sequence_item": r"^(\s*)-\s+(.+)$",
                "comment": r"#(.*)$",
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
                semantic_signature=f"YAML document {Path(file_path).stem}",
                semantic_parent=None,
                semantic_context={"fallback_parsing": True},
                semantic_scope="document",
                semantic_language_features=["fallback_chunk"],
            )
        ]

    # Utility methods for YAML parsing

    def _extract_mapping_keys(self, mapping_node: Any, lines: List[str]) -> List[str]:
        """Extract keys from a mapping node."""
        keys = []

        for child in mapping_node.children:
            if hasattr(child, "type") and child.type in [
                "pair",
                "block_mapping_pair",
                "flow_pair",
            ]:
                key, _ = self._extract_key_value(child, lines)
                if key:
                    keys.append(key)

        return keys

    def _count_sequence_items(self, sequence_node: Any, lines: List[str]) -> int:
        """Count items in a sequence node."""
        count = 0

        for child in sequence_node.children:
            if hasattr(child, "type"):
                if child.type in ["block_sequence_item", "flow_sequence_item"]:
                    count += 1
                elif child.type == "flow_node":
                    # Flow sequences have flow_node children for each item
                    count += 1
                # Skip structural nodes like "[", "]", ","
                elif child.type in ["[", "]", ","]:
                    continue

        return count

    def _extract_key_value(
        self, pair_node: Any, lines: List[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract key and value from a pair node."""
        key = None
        value = None

        for child in pair_node.children:
            if hasattr(child, "type"):
                # Handle flow_node which contains scalars in YAML tree-sitter
                if child.type == "flow_node" and key is None:
                    # First flow_node is the key
                    key = self._get_node_text(child, lines).strip().strip("\"'")
                elif child.type in ["flow_node", "block_node"] and key is not None:
                    # Second node is the value
                    value = self._get_node_text(child, lines).strip()
                elif (
                    child.type
                    in ["plain_scalar", "double_quote_scalar", "single_quote_scalar"]
                    and key is None
                ):
                    # First scalar is the key (fallback)
                    key = self._get_node_text(child, lines).strip().strip("\"'")
                elif (
                    child.type
                    in [
                        "plain_scalar",
                        "double_quote_scalar",
                        "single_quote_scalar",
                        "block_mapping",
                        "flow_mapping",
                        "block_sequence",
                        "flow_sequence",
                    ]
                    and key is not None
                ):
                    # Second value is the value (fallback)
                    value = self._get_node_text(child, lines).strip()

        return key, value

    def _determine_value_type(self, value: Optional[str]) -> str:
        """Determine the type of a YAML value."""
        if value is None:
            return "null"

        value = value.strip()

        if not value:
            return "empty"
        elif value.lower() in ["true", "false"]:
            return "boolean"
        elif value.startswith("[") and value.endswith("]"):
            return "flow_sequence"
        elif value.startswith("{") and value.endswith("}"):
            return "flow_mapping"
        elif value.startswith("|") or value.startswith(">"):
            return "block_scalar"
        elif value.startswith("*"):
            return "alias"
        elif value.startswith("&"):
            return "anchor"
        elif "\n" in value and (":" in value or "-" in value):
            # Multi-line content with YAML structure indicators
            return "mapping"
        elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return "integer"
        elif "." in value and value.replace(".", "").replace("-", "").isdigit():
            return "float"
        else:
            return "string"

    def _truncate_value(self, value: Optional[str], max_length: int = 50) -> str:
        """Truncate a value for display purposes."""
        if not value:
            return ""

        if len(value) <= max_length:
            return value

        return value[: max_length - 3] + "..."

    def _is_config_key(self, key: str) -> bool:
        """Check if a key looks like a configuration key."""
        config_patterns = [
            "config",
            "settings",
            "options",
            "params",
            "parameters",
            "env",
            "environment",
            "port",
            "host",
            "url",
            "path",
            "version",
            "name",
            "title",
            "description",
        ]

        key_lower = key.lower()
        return any(pattern in key_lower for pattern in config_patterns)
