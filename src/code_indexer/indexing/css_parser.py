"""
CSS semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Handles selectors, rules, declarations, media queries, at-rules, and comments.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class CssSemanticParser(BaseTreeSitterParser):
    """Semantic parser for CSS files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "css")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (@import, @charset, etc.)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "import_statement":
                    self._handle_import_statement(child, constructs, lines, scope_stack)
                elif child.type == "charset_statement":
                    self._handle_charset_statement(
                        child, constructs, lines, scope_stack
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
        """Handle CSS-specific AST node types."""
        if node_type == "rule_set":
            self._handle_rule_set(node, constructs, lines, scope_stack, content)
        elif node_type == "media_statement":
            self._handle_media_statement(node, constructs, lines, scope_stack, content)
        elif node_type == "keyframes_statement":
            self._handle_keyframes_statement(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "at_rule":
            self._handle_at_rule(node, constructs, lines, scope_stack, content)
        elif node_type == "comment":
            self._handle_comment(node, constructs, lines, scope_stack)
        elif node_type == "declaration":
            self._handle_declaration(node, constructs, lines, scope_stack)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped."""
        # Skip children for leaf nodes that don't contain other constructs
        return node_type in ["comment", "string_value", "integer_value", "float_value"]

    def _handle_import_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle @import statements."""
        import_text = self._get_node_text(node, lines)

        # Extract the imported file/URL
        import_match = re.search(
            r'@import\s+(?:url\()?["\']?([^"\'()]+)["\']?(?:\))?', import_text
        )
        import_name = import_match.group(1) if import_match else "unknown"

        constructs.append(
            {
                "type": "import",
                "name": import_name,
                "path": f"@import.{import_name}",
                "signature": import_text.strip(),
                "parent": None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": import_text,
                "context": {
                    "import_target": import_name,
                    "declaration_type": "import",
                },
                "features": ["at_import", "external_dependency"],
            }
        )

    def _handle_charset_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle @charset statements."""
        charset_text = self._get_node_text(node, lines)

        # Extract charset value
        charset_match = re.search(r'@charset\s+["\']([^"\']+)["\']', charset_text)
        charset_value = charset_match.group(1) if charset_match else "unknown"

        constructs.append(
            {
                "type": "charset",
                "name": charset_value,
                "path": f"@charset.{charset_value}",
                "signature": charset_text.strip(),
                "parent": None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": charset_text,
                "context": {
                    "charset_value": charset_value,
                    "declaration_type": "charset",
                },
                "features": ["at_charset"],
            }
        )

    def _handle_rule_set(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CSS rule sets (selector + declarations)."""
        rule_text = self._get_node_text(node, lines)

        # Extract selectors
        selectors = self._extract_selectors(node, lines)
        selector_text = ", ".join(selectors) if selectors else "unknown"

        # Extract declarations
        declarations = self._extract_declarations(node, lines)

        # Analyze selector type
        selector_types = self._analyze_selector_types(selectors)

        features = []
        features.extend(selector_types)
        if len(selectors) > 1:
            features.append("multiple_selectors")
        if any(":" in sel for sel in selectors):
            features.append("pseudo_selector")
        if any("@media" in sel for sel in selectors):
            features.append("media_query")

        parent_path = ".".join(scope_stack) if scope_stack else None
        rule_name = self._create_rule_name(selectors)
        current_path = f"{parent_path}.{rule_name}" if parent_path else rule_name

        constructs.append(
            {
                "type": "rule",
                "name": rule_name,
                "path": current_path,
                "signature": f"{selector_text} {{ ... }}",
                "parent": parent_path,
                "scope": "stylesheet" if not scope_stack else "nested",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": rule_text,
                "context": {
                    "selectors": selectors,
                    "declarations": declarations,
                    "declaration_count": len(declarations),
                    "selector_types": selector_types,
                },
                "features": features,
            }
        )

        # Add rule to scope for nested rules
        scope_stack.append(rule_name)

    def _handle_media_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle @media statements."""
        media_text = self._get_node_text(node, lines)

        # Extract media query
        media_query = self._extract_media_query(node, lines)

        features = ["at_media", "media_query", "responsive"]
        if "screen" in media_query:
            features.append("screen_media")
        if "print" in media_query:
            features.append("print_media")
        if "max-width" in media_query or "min-width" in media_query:
            features.append("width_based")

        parent_path = ".".join(scope_stack) if scope_stack else None
        media_name = f"media_{hash(media_query) % 10000}"
        current_path = f"{parent_path}.{media_name}" if parent_path else media_name

        constructs.append(
            {
                "type": "media",
                "name": media_name,
                "path": current_path,
                "signature": f"@media {media_query} {{ ... }}",
                "parent": parent_path,
                "scope": "stylesheet",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": media_text,
                "context": {
                    "media_query": media_query,
                    "query_type": "media",
                },
                "features": features,
            }
        )

        # Add media query to scope
        scope_stack.append(media_name)

    def _handle_keyframes_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle @keyframes statements."""
        keyframes_text = self._get_node_text(node, lines)

        # Extract keyframes name
        keyframes_name = self._extract_keyframes_name(node, lines)

        # Extract keyframe steps
        keyframe_steps = self._extract_keyframe_steps(node, lines)

        features = ["at_keyframes", "animation", "css_animation"]
        if keyframe_steps:
            features.append("has_keyframes")

        parent_path = ".".join(scope_stack) if scope_stack else None
        current_path = (
            f"{parent_path}.{keyframes_name}" if parent_path else keyframes_name
        )

        constructs.append(
            {
                "type": "keyframes",
                "name": keyframes_name,
                "path": current_path,
                "signature": f"@keyframes {keyframes_name} {{ ... }}",
                "parent": parent_path,
                "scope": "stylesheet",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": keyframes_text,
                "context": {
                    "keyframes_name": keyframes_name,
                    "keyframe_steps": keyframe_steps,
                    "step_count": len(keyframe_steps),
                },
                "features": features,
            }
        )

    def _handle_at_rule(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle generic @-rules."""
        at_rule_text = self._get_node_text(node, lines)

        # Extract at-rule name
        at_rule_match = re.search(r"@(\w+)", at_rule_text)
        at_rule_name = at_rule_match.group(1) if at_rule_match else "unknown"

        features = [f"at_{at_rule_name}", "at_rule"]

        parent_path = ".".join(scope_stack) if scope_stack else None
        current_path = (
            f"{parent_path}.@{at_rule_name}" if parent_path else f"@{at_rule_name}"
        )

        constructs.append(
            {
                "type": "at_rule",
                "name": f"@{at_rule_name}",
                "path": current_path,
                "signature": (
                    at_rule_text.split("{")[0].strip()
                    if "{" in at_rule_text
                    else at_rule_text.strip()
                ),
                "parent": parent_path,
                "scope": "stylesheet",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": at_rule_text,
                "context": {
                    "at_rule_name": at_rule_name,
                    "rule_type": "at_rule",
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
        """Handle CSS comments."""
        comment_text = self._get_node_text(node, lines)
        comment_content = comment_text.strip("/*").strip("*/").strip()

        # Only process significant comments
        if len(comment_content.strip()) > 10:
            parent_path = ".".join(scope_stack) if scope_stack else None

            constructs.append(
                {
                    "type": "comment",
                    "name": "comment",
                    "path": f"{parent_path}.comment" if parent_path else "comment",
                    "signature": f"/* {comment_content[:50]}{'...' if len(comment_content) > 50 else ''} */",
                    "parent": parent_path,
                    "scope": "stylesheet" if not scope_stack else "nested",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": comment_text,
                    "context": {
                        "comment_content": comment_content,
                    },
                    "features": ["css_comment"],
                }
            )

    def _handle_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle CSS declarations (property: value pairs)."""
        declaration_text = self._get_node_text(node, lines)

        # Extract property and value
        property_name, property_value = self._parse_declaration(node, lines)

        if property_name:
            features = [f"property_{property_name}"]
            if property_value:
                if "var(" in property_value:
                    features.append("css_variable")
                if "calc(" in property_value:
                    features.append("css_calc")
                if property_value.startswith("#") or "rgb" in property_value:
                    features.append("color_value")
                if (
                    "px" in property_value
                    or "em" in property_value
                    or "rem" in property_value
                ):
                    features.append("size_value")

            parent_path = ".".join(scope_stack) if scope_stack else None

            constructs.append(
                {
                    "type": "declaration",
                    "name": property_name,
                    "path": (
                        f"{parent_path}.{property_name}"
                        if parent_path
                        else property_name
                    ),
                    "signature": f"{property_name}: {property_value};",
                    "parent": parent_path,
                    "scope": "rule" if scope_stack else "stylesheet",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": declaration_text,
                    "context": {
                        "property": property_name,
                        "value": property_value,
                    },
                    "features": features,
                }
            )

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract CSS constructs from ERROR node text using regex fallback."""
        constructs = []
        error_text.split("\n")

        # CSS-specific regex patterns
        patterns = {
            "rule": r"([^{]+)\s*\{([^}]*)\}",
            "at_rule": r"(@\w+[^{;]*(?:\{[^}]*\}|;))",
            "declaration": r"([a-zA-Z-]+)\s*:\s*([^;]+);",
            "comment": r"/\*(.*?)\*/",
            "media": r"(@media[^{]+)\s*\{([^}]*)\}",
            "keyframes": r"(@keyframes\s+\w+[^{]*)\s*\{([^}]*)\}",
        }

        parent_path = ".".join(scope_stack) if scope_stack else None

        for pattern_type, pattern in patterns.items():
            for match in re.finditer(pattern, error_text, re.MULTILINE | re.DOTALL):
                line_offset = error_text[: match.start()].count("\n")
                line_num = start_line + line_offset

                if pattern_type == "rule":
                    selector = match.group(1).strip()
                    declarations_text = match.group(2).strip()

                    rule_name = self._create_rule_name([selector])

                    constructs.append(
                        {
                            "type": "rule",
                            "name": rule_name,
                            "path": (
                                f"{parent_path}.{rule_name}"
                                if parent_path
                                else rule_name
                            ),
                            "signature": f"{selector} {{ ... }}",
                            "parent": parent_path,
                            "scope": "stylesheet",
                            "line_start": line_num + 1,
                            "line_end": line_num + match.group(0).count("\n") + 1,
                            "text": match.group(0),
                            "context": {
                                "selector": selector,
                                "declarations_text": declarations_text,
                                "extracted_from_error": True,
                            },
                            "features": ["rule_fallback"],
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
                            "signature": f"/* {comment_content[:50]}{'...' if len(comment_content) > 50 else ''} */",
                            "parent": parent_path,
                            "scope": "stylesheet",
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
                "rule": r"([^{]+)\s*\{([^}]*)\}",
                "at_rule": r"(@\w+[^{;]*(?:\{[^}]*\}|;))",
                "comment": r"/\*(.*?)\*/",
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
                semantic_scope=construct.get("scope", "stylesheet"),
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
                semantic_type="stylesheet",
                semantic_name=Path(file_path).stem,
                semantic_path=Path(file_path).stem,
                semantic_signature=f"CSS stylesheet {Path(file_path).stem}",
                semantic_parent=None,
                semantic_context={"fallback_parsing": True},
                semantic_scope="stylesheet",
                semantic_language_features=["fallback_chunk"],
            )
        ]

    # Utility methods for CSS parsing

    def _extract_selectors(self, rule_node: Any, lines: List[str]) -> List[str]:
        """Extract selectors from a rule set node."""
        selectors = []

        for child in rule_node.children:
            if hasattr(child, "type") and child.type == "selectors":
                selector_text = self._get_node_text(child, lines).strip()
                # Split multiple selectors by comma
                selectors.extend(
                    [sel.strip() for sel in selector_text.split(",") if sel.strip()]
                )
                break

        return selectors

    def _extract_declarations(
        self, rule_node: Any, lines: List[str]
    ) -> List[Dict[str, str]]:
        """Extract declarations from a rule set node."""
        declarations = []

        for child in rule_node.children:
            if hasattr(child, "type") and child.type == "block":
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "declaration":
                        prop, value = self._parse_declaration(grandchild, lines)
                        if prop:
                            declarations.append(
                                {"property": prop, "value": value or ""}
                            )

        return declarations

    def _parse_declaration(
        self, decl_node: Any, lines: List[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Parse a declaration node to extract property and value."""
        property_name = None
        property_value = None

        for child in decl_node.children:
            if hasattr(child, "type"):
                if child.type == "property_name":
                    property_name = self._get_node_text(child, lines)
                elif child.type in [
                    "property_value",
                    "value",
                    "color_value",
                    "integer_value",
                    "float_value",
                    "string_value",
                    "call_expression",
                    "binary_expression",
                    "plain_value",
                    "identifier",
                ]:
                    property_value = self._get_node_text(child, lines).strip()

        return property_name, property_value

    def _analyze_selector_types(self, selectors: List[str]) -> List[str]:
        """Analyze selector types for features."""
        types = []

        for selector in selectors:
            # Use individual if statements instead of elif to detect multiple features
            if selector.startswith("#"):
                types.append("id_selector")
            if selector.startswith("."):
                types.append("class_selector")
            if ":" in selector:
                types.append("pseudo_selector")
            if "[" in selector and "]" in selector:
                types.append("attribute_selector")
            if (
                selector.strip()
                and selector.strip()[0].islower()
                and not any(char in selector for char in [".", "#", ":", "["])
            ):
                types.append("element_selector")

        return list(set(types))  # Remove duplicates

    def _create_rule_name(self, selectors: List[str]) -> str:
        """Create a readable name for a CSS rule based on its selectors."""
        if not selectors:
            return "unknown_rule"

        # Use the first selector, clean it up
        main_selector = selectors[0].strip()

        # Replace special characters for path compatibility
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", main_selector)
        clean_name = re.sub(r"_+", "_", clean_name).strip("_")

        return clean_name[:50] if clean_name else "rule"

    def _extract_media_query(self, media_node: Any, lines: List[str]) -> str:
        """Extract media query from a media statement node."""
        media_text = self._get_node_text(media_node, lines)

        # Extract the query part
        media_match = re.search(r"@media\s+([^{]+)", media_text)
        return media_match.group(1).strip() if media_match else "all"

    def _extract_keyframes_name(self, keyframes_node: Any, lines: List[str]) -> str:
        """Extract keyframes name from a keyframes statement node."""
        keyframes_text = self._get_node_text(keyframes_node, lines)

        # Extract the name
        name_match = re.search(r"@keyframes\s+(\w+)", keyframes_text)
        return name_match.group(1) if name_match else "unnamed"

    def _extract_keyframe_steps(
        self, keyframes_node: Any, lines: List[str]
    ) -> List[str]:
        """Extract keyframe steps from a keyframes statement node."""
        steps = []
        keyframes_text = self._get_node_text(keyframes_node, lines)

        # Find percentage steps
        step_matches = re.findall(r"(\d+%|from|to)\s*\{[^}]*\}", keyframes_text)
        steps = [match for match in step_matches]

        return steps
