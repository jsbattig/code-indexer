"""
C# semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class CSharpSemanticParser(BaseTreeSitterParser):
    """Semantic parser for C# files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "csharp")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (namespace, using statements)."""
        # Find namespace declaration
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "namespace_declaration":
                    namespace_name = self._extract_namespace_name(child, lines)
                    if namespace_name:
                        scope_stack.append(namespace_name)
                        constructs.append(
                            {
                                "type": "namespace",
                                "name": namespace_name,
                                "path": namespace_name,
                                "signature": f"namespace {namespace_name}",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "namespace"},
                                "features": ["namespace_declaration"],
                            }
                        )
                elif child.type == "using_directive":
                    using_name = self._extract_using_name(child, lines)
                    if using_name:
                        constructs.append(
                            {
                                "type": "using",
                                "name": using_name,
                                "path": using_name,
                                "signature": f"using {using_name};",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "using"},
                                "features": ["using_directive"],
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
        """Handle C#-specific AST node types."""
        if node_type == "class_declaration":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "interface_declaration":
            self._handle_interface_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "struct_declaration":
            self._handle_struct_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "enum_declaration":
            self._handle_enum_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "method_declaration":
            self._handle_method_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "constructor_declaration":
            self._handle_constructor_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "property_declaration":
            self._handle_property_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "field_declaration":
            self._handle_field_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "event_declaration":
            self._handle_event_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "delegate_declaration":
            self._handle_delegate_declaration(
                node, constructs, lines, scope_stack, content
            )

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        # Classes, interfaces, structs and enums handle their own members
        return node_type in [
            "class_declaration",
            "interface_declaration",
            "struct_declaration",
            "enum_declaration",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract C# constructs from ERROR node text using regex fallback."""
        constructs = []
        lines = error_text.split("\n")
        current_parent = ".".join(scope_stack) if scope_stack else None

        # C# namespace pattern
        namespace_pattern = r"^\s*namespace\s+([A-Za-z_][A-Za-z0-9_.]*)\s*[{;]"

        # C# class pattern
        class_pattern = r"^\s*(?:public|private|protected|internal|static|abstract|sealed)?\s*(?:partial\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"

        # C# interface pattern
        interface_pattern = r"^\s*(?:public|private|protected|internal)?\s*interface\s+([A-Za-z_][A-Za-z0-9_]*)"

        # C# struct pattern
        struct_pattern = r"^\s*(?:public|private|protected|internal)?\s*struct\s+([A-Za-z_][A-Za-z0-9_]*)"

        # C# enum pattern
        enum_pattern = r"^\s*(?:public|private|protected|internal)?\s*enum\s+([A-Za-z_][A-Za-z0-9_]*)"

        # C# method pattern
        method_pattern = r"^\s*(?:public|private|protected|internal|static|virtual|override|abstract|sealed|async)?\s*(?:\w+(?:\[\])?|\w+<.*?>)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("

        # C# property pattern
        property_pattern = r"^\s*(?:public|private|protected|internal|static|virtual|override|abstract)?\s*(?:\w+(?:\[\])?|\w+<.*?>)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{\s*(?:get|set)"

        # C# field pattern
        field_pattern = r"^\s*(?:public|private|protected|internal|static|readonly|const)?\s*(?:\w+(?:\[\])?|\w+<.*?>)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[=;]"

        patterns = [
            (namespace_pattern, "namespace"),
            (class_pattern, "class"),
            (interface_pattern, "interface"),
            (struct_pattern, "struct"),
            (enum_pattern, "enum"),
            (method_pattern, "method"),
            (property_pattern, "property"),
            (field_pattern, "field"),
        ]

        for i, line in enumerate(lines):
            line_num = start_line + i
            for pattern, construct_type in patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)
                    full_path = f"{current_parent}.{name}" if current_parent else name

                    constructs.append(
                        {
                            "type": construct_type,
                            "name": name,
                            "path": full_path,
                            "signature": line.strip(),
                            "parent": current_parent,
                            "scope": "class" if current_parent else "global",
                            "line_start": line_num,
                            "line_end": line_num,
                            "text": line,
                            "context": {"regex_fallback": True},
                            "features": [f"{construct_type}_declaration"],
                        }
                    )
                    break

        return constructs

    def _extract_namespace_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract namespace name from namespace declaration node."""
        try:
            # Find the identifier node within the namespace declaration
            for child in node.children:
                if hasattr(child, "type") and child.type == "qualified_name":
                    return self._get_node_text(child, lines).strip()
                elif hasattr(child, "type") and child.type == "identifier":
                    return self._get_node_text(child, lines).strip()
        except Exception:
            pass

        # Fallback to regex
        node_text = self._get_node_text(node, lines)
        match = re.search(r"namespace\s+([A-Za-z_][A-Za-z0-9_.]*)", node_text)
        return match.group(1) if match else None

    def _extract_using_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract using name from using directive node."""
        try:
            # Find the qualified_name node within the using directive
            for child in node.children:
                if hasattr(child, "type") and child.type == "qualified_name":
                    return self._get_node_text(child, lines).strip()
                elif hasattr(child, "type") and child.type == "identifier":
                    return self._get_node_text(child, lines).strip()
        except Exception:
            pass

        # Fallback to regex
        node_text = self._get_node_text(node, lines)
        match = re.search(r"using\s+([A-Za-z_][A-Za-z0-9_.]*)", node_text)
        return match.group(1) if match else None

    def _handle_class_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# class declaration."""
        class_name = self._extract_identifier(node, lines)
        if not class_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{class_name}" if current_scope else class_name

        # Get class signature (modifiers + class keyword + name)
        signature = self._extract_signature(node, lines, "class")

        constructs.append(
            {
                "type": "class",
                "name": class_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "namespace" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "class"},
                "features": ["class_declaration"],
            }
        )

        # Process class members
        scope_stack.append(class_name)
        self._process_class_members(node, constructs, lines, scope_stack, content)
        scope_stack.pop()

    def _handle_interface_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# interface declaration."""
        interface_name = self._extract_identifier(node, lines)
        if not interface_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{interface_name}" if current_scope else interface_name
        )

        signature = self._extract_signature(node, lines, "interface")

        constructs.append(
            {
                "type": "interface",
                "name": interface_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "namespace" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "interface"},
                "features": ["interface_declaration"],
            }
        )

        # Process interface members
        scope_stack.append(interface_name)
        self._process_class_members(node, constructs, lines, scope_stack, content)
        scope_stack.pop()

    def _handle_struct_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# struct declaration."""
        struct_name = self._extract_identifier(node, lines)
        if not struct_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{struct_name}" if current_scope else struct_name

        signature = self._extract_signature(node, lines, "struct")

        constructs.append(
            {
                "type": "struct",
                "name": struct_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "namespace" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "struct"},
                "features": ["struct_declaration"],
            }
        )

        # Process struct members
        scope_stack.append(struct_name)
        self._process_class_members(node, constructs, lines, scope_stack, content)
        scope_stack.pop()

    def _handle_enum_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# enum declaration."""
        enum_name = self._extract_identifier(node, lines)
        if not enum_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{enum_name}" if current_scope else enum_name

        signature = self._extract_signature(node, lines, "enum")

        constructs.append(
            {
                "type": "enum",
                "name": enum_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "namespace" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "enum"},
                "features": ["enum_declaration"],
            }
        )

    def _handle_method_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# method declaration."""
        method_name = self._extract_identifier(node, lines)
        if not method_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{method_name}" if current_scope else method_name

        signature = self._extract_method_signature(node, lines)

        constructs.append(
            {
                "type": "method",
                "name": method_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "class" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "method"},
                "features": ["method_declaration"],
            }
        )

    def _handle_constructor_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# constructor declaration."""
        constructor_name = self._extract_identifier(node, lines)
        if not constructor_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{constructor_name}" if current_scope else constructor_name
        )

        signature = self._extract_method_signature(node, lines)

        constructs.append(
            {
                "type": "constructor",
                "name": constructor_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "class" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "constructor"},
                "features": ["constructor_declaration"],
            }
        )

    def _handle_property_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# property declaration."""
        property_name = self._extract_identifier(node, lines)
        if not property_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{property_name}" if current_scope else property_name
        )

        signature = self._extract_signature(node, lines, "property")

        constructs.append(
            {
                "type": "property",
                "name": property_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "class" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "property"},
                "features": ["property_declaration"],
            }
        )

    def _handle_field_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# field declaration."""
        field_name = self._extract_identifier(node, lines)
        if not field_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{field_name}" if current_scope else field_name

        signature = self._extract_signature(node, lines, "field")

        constructs.append(
            {
                "type": "field",
                "name": field_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "class" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "field"},
                "features": ["field_declaration"],
            }
        )

    def _handle_event_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# event declaration."""
        event_name = self._extract_identifier(node, lines)
        if not event_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{event_name}" if current_scope else event_name

        signature = self._extract_signature(node, lines, "event")

        constructs.append(
            {
                "type": "event",
                "name": event_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "class" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "event"},
                "features": ["event_declaration"],
            }
        )

    def _handle_delegate_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C# delegate declaration."""
        delegate_name = self._extract_identifier(node, lines)
        if not delegate_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{delegate_name}" if current_scope else delegate_name
        )

        signature = self._extract_signature(node, lines, "delegate")

        constructs.append(
            {
                "type": "delegate",
                "name": delegate_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "namespace" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "delegate"},
                "features": ["delegate_declaration"],
            }
        )

    def _process_class_members(
        self,
        class_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process members within a class/interface/struct."""
        for child in class_node.children:
            if hasattr(child, "type"):
                self._handle_language_constructs(
                    child, child.type, constructs, lines, scope_stack, content
                )

    def _extract_method_signature(self, node: Any, lines: List[str]) -> str:
        """Extract method signature including modifiers, return type, name, and parameters."""
        try:
            node_text = self._get_node_text(node, lines)
            # Find the signature part (before the opening brace)
            signature_match = re.match(r"([^{]*)", node_text.strip())
            if signature_match:
                return signature_match.group(1).strip()
        except Exception:
            pass

        return self._get_node_text(node, lines).split("{")[0].strip()

    def _extract_signature(
        self, node: Any, lines: List[str], construct_type: str
    ) -> str:
        """Extract signature for various construct types."""
        try:
            node_text = self._get_node_text(node, lines)
            # For most constructs, the signature is the first line
            first_line = node_text.split("\n")[0].strip()

            # Clean up common patterns
            if "{" in first_line:
                first_line = first_line.split("{")[0].strip()

            return first_line
        except Exception:
            return f"{construct_type} [unknown]"

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        # Use the error text extraction as fallback
        constructs = self._extract_constructs_from_error_text(content, 1, [])

        # Convert constructs to SemanticChunk objects
        chunks = []
        file_ext = Path(file_path).suffix

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
                semantic_chunking=True,
                semantic_type=construct["type"],
                semantic_name=construct["name"],
                semantic_path=construct.get("path", construct["name"]),
                semantic_signature=construct.get("signature", ""),
                semantic_parent=construct.get("parent"),
                semantic_context=construct.get("context", {}),
                semantic_scope=construct.get("scope", "global"),
                semantic_language_features=construct.get("features", []),
            )
            chunks.append(chunk)

        return chunks

    def _extract_identifier(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a node."""
        return self._get_identifier_from_node(node, lines)
