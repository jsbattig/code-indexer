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
        """Extract namespace name from namespace declaration node using AST."""
        try:
            # Find the identifier node within the namespace declaration
            for child in node.children:
                if hasattr(child, "type") and child.type == "qualified_name":
                    return self._get_node_text(child, lines).strip()
                elif hasattr(child, "type") and child.type == "identifier":
                    return self._get_node_text(child, lines).strip()
        except Exception:
            # Only use text fallback if AST extraction completely fails
            node_text = self._get_node_text(node, lines)
            # Extract from first line only
            first_line = node_text.split("\n")[0]
            if "namespace" in first_line:
                # Simple extraction without regex
                parts = first_line.replace("{", "").strip().split()
                if len(parts) >= 2 and parts[0] == "namespace":
                    return parts[1]
        return None

    def _extract_using_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract using name from using directive node using AST."""
        try:
            # Find the qualified_name or identifier node within the using directive
            for child in node.children:
                if hasattr(child, "type") and child.type == "qualified_name":
                    return self._get_node_text(child, lines).strip()
                elif hasattr(child, "type") and child.type == "identifier":
                    return self._get_node_text(child, lines).strip()
        except Exception:
            # Only use text fallback if AST extraction completely fails
            node_text = self._get_node_text(node, lines)
            # Extract from first line only
            first_line = node_text.split("\n")[0]
            if "using" in first_line and ";" in first_line:
                # Simple extraction without regex
                using_part = first_line.replace(";", "").strip()
                parts = using_part.split()
                if len(parts) >= 2 and parts[0] == "using":
                    return parts[1]
        return None

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
        """Extract method signature including modifiers, return type, name, and parameters using AST."""
        try:
            return self._build_method_signature_from_ast(node, lines)
        except Exception:
            # Only fall back to text extraction if AST parsing fails
            return self._get_node_text(node, lines).split("{")[0].strip()

    def _build_method_signature_from_ast(self, node: Any, lines: List[str]) -> str:
        """Build method signature from AST nodes."""
        parts = []

        # Extract modifiers (public, private, static, async, etc.)
        modifiers = self._extract_modifiers(node, lines)
        if modifiers:
            parts.extend(modifiers)

        # For constructors, handle differently
        if node.type == "constructor_declaration":
            # Constructor name is the class name
            constructor_name = self._extract_identifier(node, lines)
            if constructor_name:
                parts.append(constructor_name)
                # Add parameters
                parameters = self._extract_parameter_list(node, lines)
                if parameters:
                    parts.append(parameters)
            return " ".join(parts)

        # For conversion operators
        if node.type == "conversion_operator_declaration":
            return self._extract_operator_signature(node, lines)

        # Extract return type for regular methods
        return_type = self._extract_return_type(node, lines)
        if return_type:
            parts.append(return_type)

        # Extract method name
        method_name = self._extract_identifier(node, lines)
        if method_name:
            parts.append(method_name)

        # Extract generic type parameters
        type_params = self._extract_type_parameter_list(node, lines)
        if type_params:
            parts.append(type_params)

        # Extract parameter list
        parameters = self._extract_parameter_list(node, lines)
        if parameters:
            parts.append(parameters)

        # Extract type constraints (where clauses)
        constraints = self._extract_type_constraints(node, lines)
        if constraints:
            parts.append(constraints)

        return " ".join(parts) if parts else "unknown method"

    def _extract_modifiers(self, node: Any, lines: List[str]) -> List[str]:
        """Extract all modifiers from AST node."""
        modifiers = []
        for child in node.children:
            if hasattr(child, "type") and child.type == "modifier":
                modifier_text = self._get_node_text(child, lines).strip()
                if modifier_text:
                    modifiers.append(modifier_text)
        return modifiers

    def _extract_return_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract return type from method declaration."""
        # Skip modifiers and find the return type
        for child in node.children:
            if hasattr(child, "type"):
                if child.type in [
                    "predefined_type",
                    "identifier",
                    "generic_name",
                    "nullable_type",
                    "array_type",
                ]:
                    return self._get_node_text(child, lines).strip()
                elif child.type == "qualified_name":
                    return self._get_node_text(child, lines).strip()
        return None

    def _extract_parameter_list(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract parameter list from method/constructor declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "parameter_list":
                return self._get_node_text(child, lines).strip()
        return None

    def _extract_type_parameter_list(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract generic type parameter list from method declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_parameter_list":
                return self._get_node_text(child, lines).strip()
        return None

    def _extract_type_constraints(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract type constraints (where clauses) from method declaration."""
        constraints = []
        for child in node.children:
            if (
                hasattr(child, "type")
                and child.type == "type_parameter_constraints_clause"
            ):
                constraint_text = self._get_node_text(child, lines).strip()
                if constraint_text:
                    constraints.append(constraint_text)
        return " ".join(constraints) if constraints else None

    def _extract_operator_signature(self, node: Any, lines: List[str]) -> str:
        """Extract operator signature from conversion operator declaration."""
        parts = []

        # Extract modifiers
        modifiers = self._extract_modifiers(node, lines)
        if modifiers:
            parts.extend(modifiers)

        # Find implicit/explicit keyword
        for child in node.children:
            if hasattr(child, "type") and child.type in ["implicit", "explicit"]:
                parts.append(self._get_node_text(child, lines).strip())
                break

        # Add operator keyword
        parts.append("operator")

        # Extract target type
        for child in node.children:
            if hasattr(child, "type") and child.type in [
                "predefined_type",
                "identifier",
                "generic_name",
            ]:
                parts.append(self._get_node_text(child, lines).strip())
                break

        # Extract parameter list
        parameters = self._extract_parameter_list(node, lines)
        if parameters:
            parts.append(parameters)

        return " ".join(parts)

    def _extract_signature(
        self, node: Any, lines: List[str], construct_type: str
    ) -> str:
        """Extract signature for various construct types using AST."""
        try:
            if construct_type == "property":
                return self._extract_property_signature(node, lines)
            elif construct_type == "event":
                return self._extract_event_signature(node, lines)
            else:
                # For other constructs, use improved text extraction
                return self._extract_declaration_signature(node, lines, construct_type)
        except Exception:
            return f"{construct_type} [unknown]"

    def _extract_property_signature(self, node: Any, lines: List[str]) -> str:
        """Extract property signature including modifiers, type, name, and accessors."""
        parts = []

        # Extract modifiers
        modifiers = self._extract_modifiers(node, lines)
        if modifiers:
            parts.extend(modifiers)

        # Extract property type
        prop_type = self._extract_property_type(node, lines)
        if prop_type:
            parts.append(prop_type)

        # Extract property name
        prop_name = self._extract_identifier(node, lines)
        if prop_name:
            parts.append(prop_name)

        # Check for expression-bodied property
        if self._has_expression_body(node):
            parts.append("=>")
            # Don't include the full expression, just indicate it's expression-bodied
        else:
            # Extract accessor information
            accessors = self._extract_property_accessors(node, lines)
            if accessors:
                parts.append(accessors)

        return " ".join(parts) if parts else "property [unknown]"

    def _extract_property_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract property type from property declaration."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type in [
                    "predefined_type",
                    "identifier",
                    "generic_name",
                    "nullable_type",
                    "array_type",
                ]:
                    return self._get_node_text(child, lines).strip()
                elif child.type == "qualified_name":
                    return self._get_node_text(child, lines).strip()
        return None

    def _extract_property_accessors(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract property accessor information (get/set)."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "accessor_list":
                # Extract accessor types
                accessors = []
                for accessor_child in child.children:
                    if (
                        hasattr(accessor_child, "type")
                        and accessor_child.type == "accessor_declaration"
                    ):
                        for acc_part in accessor_child.children:
                            if hasattr(acc_part, "type") and acc_part.type in [
                                "get",
                                "set",
                                "init",
                            ]:
                                accessor_text = self._get_node_text(
                                    acc_part, lines
                                ).strip()
                                # Check if it has a body or is auto-implemented
                                has_body = self._accessor_has_body(accessor_child)
                                if has_body:
                                    accessors.append(f"{accessor_text} {{ ... }}")
                                else:
                                    accessors.append(f"{accessor_text};")

                if accessors:
                    return "{ " + " ".join(accessors) + " }"
        return None

    def _accessor_has_body(self, accessor_node: Any) -> bool:
        """Check if accessor has a body block."""
        for child in accessor_node.children:
            if hasattr(child, "type") and child.type == "block":
                return True
        return False

    def _has_expression_body(self, node: Any) -> bool:
        """Check if node has an expression body (=>)."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "arrow_expression_clause":
                return True
        return False

    def _extract_event_signature(self, node: Any, lines: List[str]) -> str:
        """Extract event signature including modifiers, type, and name."""
        parts = []

        # Extract modifiers
        modifiers = self._extract_modifiers(node, lines)
        if modifiers:
            parts.extend(modifiers)

        # Add event keyword
        parts.append("event")

        # Extract event type from variable_declaration
        for child in node.children:
            if hasattr(child, "type") and child.type == "variable_declaration":
                # Find the type
                for var_child in child.children:
                    if hasattr(var_child, "type"):
                        if var_child.type in [
                            "predefined_type",
                            "identifier",
                            "generic_name",
                            "qualified_name",
                        ]:
                            parts.append(self._get_node_text(var_child, lines).strip())
                            break

                # Find the variable name
                for var_child in child.children:
                    if (
                        hasattr(var_child, "type")
                        and var_child.type == "variable_declarator"
                    ):
                        event_name = self._extract_identifier(var_child, lines)
                        if event_name:
                            parts.append(event_name)
                        break
                break

        return " ".join(parts) if parts else "event [unknown]"

    def _extract_declaration_signature(
        self, node: Any, lines: List[str], construct_type: str
    ) -> str:
        """Extract signature for general declarations using improved text extraction."""
        node_text = self._get_node_text(node, lines)

        # For expression-bodied members, include the => but not the full expression
        if "=>" in node_text:
            parts = node_text.split("=>")
            if len(parts) >= 2:
                return f"{parts[0].strip()} => ..."

        # For block-based constructs, extract just the declaration part
        lines_text = node_text.split("\n")
        if lines_text:
            first_line = lines_text[0].strip()
            # Clean up common patterns
            if "{" in first_line:
                first_line = first_line.split("{")[0].strip()
            return first_line

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
