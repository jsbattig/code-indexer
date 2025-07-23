"""
Swift semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Handles Swift-specific constructs like classes, structs, protocols, extensions,
generics, access control modifiers, and more.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class SwiftSemanticParser(BaseTreeSitterParser):
    """Semantic parser for Swift files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "swift")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (imports, package declarations)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "import_declaration":
                    import_name = self._extract_import_name(child, lines)
                    if import_name:
                        constructs.append(
                            {
                                "type": "import",
                                "name": import_name,
                                "path": import_name,
                                "signature": f"import {import_name}",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "import"},
                                "features": ["import_statement"],
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
        """Handle Swift-specific AST node types."""
        if node_type == "class_declaration":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "struct_declaration":
            self._handle_struct_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "protocol_declaration":
            self._handle_protocol_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "extension_declaration":
            self._handle_extension_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "enum_declaration":
            self._handle_enum_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "function_declaration":
            self._handle_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "init_declaration":
            self._handle_init_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "deinit_declaration":
            self._handle_deinit_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "property_declaration":
            self._handle_property_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "subscript_declaration":
            self._handle_subscript_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "var_declaration" or node_type == "let_declaration":
            self._handle_variable_declaration(
                node, constructs, lines, scope_stack, content
            )

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped."""
        # Skip children for constructs we handle completely ourselves
        return node_type in [
            "class_declaration",
            "struct_declaration",
            "protocol_declaration",
            "extension_declaration",
            "enum_declaration",
            "function_declaration",
            "init_declaration",
            "deinit_declaration",
        ]

    def _handle_class_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift class/struct/extension/enum declaration (all use class_declaration node type)."""
        # Determine if this is a class, struct, extension, or enum by checking for keyword
        declaration_type = "class"  # default
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "struct":
                    declaration_type = "struct"
                    break
                elif child.type == "extension":
                    declaration_type = "extension"
                    break
                elif child.type == "enum":
                    declaration_type = "enum"
                    break
                elif child.type == "class":
                    declaration_type = "class"
                    break

        # Delegate to specific handler based on actual type
        if declaration_type == "struct":
            self._handle_struct_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif declaration_type == "extension":
            self._handle_extension_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif declaration_type == "enum":
            self._handle_enum_declaration(node, constructs, lines, scope_stack, content)
        else:
            self._handle_actual_class_declaration(
                node, constructs, lines, scope_stack, content
            )

    def _handle_actual_class_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle actual Swift class declaration."""
        class_name = self._get_identifier_from_node(node, lines)
        if not class_name:
            return

        # Extract inheritance and protocol conformance
        inheritance_clause = self._extract_inheritance_clause(node, lines)
        generics = self._extract_generics(node, lines)
        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("class")
        signature_parts.append(class_name)
        if generics:
            signature_parts.append(generics)
        if inheritance_clause:
            signature_parts.append(inheritance_clause)

        signature = " ".join(signature_parts)

        # Build path
        full_path = ".".join(scope_stack + [class_name])
        parent = ".".join(scope_stack) if scope_stack else None

        # Add class to scope stack for nested processing
        scope_stack.append(class_name)

        # Extract class body constructs
        class_members = self._extract_class_members(node, lines, scope_stack, content)

        # Remove from scope stack
        scope_stack.pop()

        # Create the class construct
        constructs.append(
            {
                "type": "class",
                "name": class_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": "class" if parent else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "class",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "generics": generics,
                    "inheritance": inheritance_clause,
                    "member_count": len(class_members),
                },
                "features": self._get_class_features(access_modifier, modifiers),
            }
        )

        # Add class members
        constructs.extend(class_members)

    def _handle_struct_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift struct declaration."""
        struct_name = self._get_identifier_from_node(node, lines)
        if not struct_name:
            return

        # Extract protocol conformance and generics
        inheritance_clause = self._extract_inheritance_clause(node, lines)
        generics = self._extract_generics(node, lines)
        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("struct")
        signature_parts.append(struct_name)
        if generics:
            signature_parts.append(generics)
        if inheritance_clause:
            signature_parts.append(inheritance_clause)

        signature = " ".join(signature_parts)

        # Build path
        full_path = ".".join(scope_stack + [struct_name])
        parent = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "struct",
                "name": struct_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": "struct" if parent else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "struct",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "generics": generics,
                    "protocols": inheritance_clause,
                },
                "features": self._get_struct_features(access_modifier, modifiers),
            }
        )

    def _handle_protocol_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift protocol declaration."""
        protocol_name = self._get_identifier_from_node(node, lines)
        if not protocol_name:
            return

        inheritance_clause = self._extract_inheritance_clause(node, lines)
        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("protocol")
        signature_parts.append(protocol_name)
        if inheritance_clause:
            signature_parts.append(inheritance_clause)

        signature = " ".join(signature_parts)

        # Build path
        full_path = ".".join(scope_stack + [protocol_name])
        parent = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "protocol",
                "name": protocol_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": "protocol" if parent else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "protocol",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "inheritance": inheritance_clause,
                },
                "features": self._get_protocol_features(access_modifier, modifiers),
            }
        )

    def _handle_extension_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift extension declaration."""
        extended_type = self._get_extended_type(node, lines)
        if not extended_type:
            return

        inheritance_clause = self._extract_inheritance_clause(node, lines)
        access_modifier = self._extract_access_modifier(node, lines)
        where_clause = self._extract_where_clause(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        signature_parts.extend(["extension", extended_type])
        if inheritance_clause:
            signature_parts.append(inheritance_clause)
        if where_clause:
            signature_parts.append(where_clause)

        signature = " ".join(signature_parts)

        # Build path
        extension_name = f"{extended_type}_extension"
        full_path = ".".join(scope_stack + [extension_name])
        parent = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "extension",
                "name": extension_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": "extension" if parent else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "extension",
                    "extended_type": extended_type,
                    "access_modifier": access_modifier,
                    "protocols": inheritance_clause,
                    "where_clause": where_clause,
                },
                "features": self._get_extension_features(access_modifier),
            }
        )

    def _handle_enum_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift enum declaration."""
        enum_name = self._get_identifier_from_node(node, lines)
        if not enum_name:
            return

        inheritance_clause = self._extract_inheritance_clause(node, lines)
        generics = self._extract_generics(node, lines)
        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)

        # Extract cases
        cases = self._extract_enum_cases(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("enum")
        signature_parts.append(enum_name)
        if generics:
            signature_parts.append(generics)
        if inheritance_clause:
            signature_parts.append(inheritance_clause)

        signature = " ".join(signature_parts)

        # Build path
        full_path = ".".join(scope_stack + [enum_name])
        parent = ".".join(scope_stack) if scope_stack else None

        constructs.append(
            {
                "type": "enum",
                "name": enum_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": "enum" if parent else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "enum",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "generics": generics,
                    "inheritance": inheritance_clause,
                    "cases": cases,
                    "case_count": len(cases),
                },
                "features": self._get_enum_features(access_modifier, modifiers, cases),
            }
        )

    def _handle_function_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift function declaration."""
        func_name = self._get_identifier_from_node(node, lines)
        if not func_name:
            return

        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)
        parameters = self._extract_function_parameters(node, lines)
        return_type = self._extract_return_type(node, lines)
        generics = self._extract_generics(node, lines)
        where_clause = self._extract_where_clause(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("func")
        signature_parts.append(func_name)
        if generics:
            signature_parts.append(generics)
        if parameters:
            signature_parts.append(parameters)
        if return_type:
            signature_parts.append(f"-> {return_type}")
        if where_clause:
            signature_parts.append(where_clause)

        signature = " ".join(signature_parts)

        # Build path
        full_path = ".".join(scope_stack + [func_name])
        parent = ".".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "function",
                "name": func_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "function",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "parameters": parameters,
                    "return_type": return_type,
                    "generics": generics,
                    "where_clause": where_clause,
                },
                "features": self._get_function_features(
                    access_modifier, modifiers, func_name
                ),
            }
        )

    def _handle_init_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift initializer declaration."""
        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)
        parameters = self._extract_function_parameters(node, lines)
        generics = self._extract_generics(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("init")
        if generics:
            signature_parts.append(generics)
        if parameters:
            signature_parts.append(parameters)

        signature = " ".join(signature_parts)

        # Build path
        init_name = f"init{parameters if parameters else '()'}"
        full_path = ".".join(scope_stack + [init_name])
        parent = ".".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "initializer",
                "name": init_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "initializer",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "parameters": parameters,
                    "generics": generics,
                },
                "features": self._get_init_features(access_modifier, modifiers),
            }
        )

    def _handle_deinit_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift deinitializer declaration."""
        # Build path
        full_path = ".".join(scope_stack + ["deinit"])
        parent = ".".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "deinitializer",
                "name": "deinit",
                "path": full_path,
                "signature": "deinit",
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "deinitializer"},
                "features": ["deinitializer"],
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
        """Handle Swift property declaration."""
        property_name = self._get_identifier_from_node(node, lines)
        if not property_name:
            return

        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)
        property_type = self._extract_property_type(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("var" if "var" in modifiers else "let")
        signature_parts.append(property_name)
        if property_type:
            signature_parts.append(f": {property_type}")

        signature = " ".join(signature_parts)

        # Build path
        full_path = ".".join(scope_stack + [property_name])
        parent = ".".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "property",
                "name": property_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "property",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "property_type": property_type,
                },
                "features": self._get_property_features(access_modifier, modifiers),
            }
        )

    def _handle_subscript_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift subscript declaration."""
        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)
        parameters = self._extract_function_parameters(node, lines)
        return_type = self._extract_return_type(node, lines)

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("subscript")
        if parameters:
            signature_parts.append(parameters)
        if return_type:
            signature_parts.append(f"-> {return_type}")

        signature = " ".join(signature_parts)

        # Build path
        subscript_name = f"subscript{parameters if parameters else '()'}"
        full_path = ".".join(scope_stack + [subscript_name])
        parent = ".".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "subscript",
                "name": subscript_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "subscript",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "parameters": parameters,
                    "return_type": return_type,
                },
                "features": self._get_subscript_features(access_modifier, modifiers),
            }
        )

    def _handle_variable_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Swift variable declaration (var/let)."""
        var_name = self._get_identifier_from_node(node, lines)
        if not var_name:
            return

        access_modifier = self._extract_access_modifier(node, lines)
        modifiers = self._extract_modifiers(node, lines)
        var_type = self._extract_property_type(node, lines)
        is_let = node.type == "let_declaration"

        # Build signature
        signature_parts = []
        if access_modifier:
            signature_parts.append(access_modifier)
        if modifiers:
            signature_parts.extend(modifiers)
        signature_parts.append("let" if is_let else "var")
        signature_parts.append(var_name)
        if var_type:
            signature_parts.append(f": {var_type}")

        signature = " ".join(signature_parts)

        # Build path
        full_path = ".".join(scope_stack + [var_name])
        parent = ".".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "variable",
                "name": var_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "variable",
                    "access_modifier": access_modifier,
                    "modifiers": modifiers,
                    "variable_type": var_type,
                    "is_constant": is_let,
                },
                "features": self._get_variable_features(
                    access_modifier, modifiers, is_let
                ),
            }
        )

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Swift constructs from ERROR node text using regex fallback."""
        constructs = []

        # Swift-specific regex patterns
        patterns = {
            "class": r"(?:public|private|internal|fileprivate|open)?\s*(?:final)?\s*class\s+(\w+)(?:\s*<[^>]*>)?(?:\s*:\s*[^{]+)?\s*\{",
            "struct": r"(?:public|private|internal|fileprivate)?\s*struct\s+(\w+)(?:\s*<[^>]*>)?(?:\s*:\s*[^{]+)?\s*\{",
            "protocol": r"(?:public|private|internal|fileprivate)?\s*protocol\s+(\w+)(?:\s*:\s*[^{]+)?\s*\{",
            "extension": r"(?:public|private|internal|fileprivate)?\s*extension\s+(\w+)(?:\s*:\s*[^{]+)?(?:\s*where\s+[^{]+)?\s*\{",
            "enum": r"(?:public|private|internal|fileprivate)?\s*enum\s+(\w+)(?:\s*<[^>]*>)?(?:\s*:\s*[^{]+)?\s*\{",
            "function": r"(?:public|private|internal|fileprivate)?\s*(?:static|class)?\s*func\s+(\w+)(?:\s*<[^>]*>)?\s*\([^)]*\)(?:\s*->\s*[^{]+)?\s*\{",
            "initializer": r"(?:public|private|internal|fileprivate)?\s*(?:convenience|required)?\s*init\s*\([^)]*\)\s*\{",
            "deinitializer": r"deinit\s*\{",
            "property": r"(?:public|private|internal|fileprivate)?\s*(?:static|class)?\s*(?:var|let)\s+(\w+)\s*:\s*[^=\n{]+",
            "subscript": r"(?:public|private|internal|fileprivate)?\s*subscript\s*\([^)]*\)\s*->\s*[^{]+\s*\{",
        }

        lines = error_text.split("\n")

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    # Extract name based on construct type
                    if construct_type in ["initializer", "deinitializer", "subscript"]:
                        name = construct_type
                    else:
                        try:
                            name = match.group(1)
                        except IndexError:
                            name = construct_type

                    # Build construct
                    construct = {
                        "type": construct_type,
                        "name": name,
                        "path": ".".join(scope_stack + [name]),
                        "signature": line.strip(),
                        "parent": ".".join(scope_stack) if scope_stack else None,
                        "scope": scope_stack[-1] if scope_stack else "global",
                        "line_start": start_line + line_idx + 1,
                        "line_end": start_line + line_idx + 1,  # Single line fallback
                        "text": line,
                        "context": {
                            "extracted_from_error": True,
                            "fallback_parsing": True,
                        },
                        "features": [f"{construct_type}_fallback"],
                    }

                    constructs.append(construct)

        return constructs

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        patterns = {
            "class": r"(?:public|private|internal|fileprivate|open)?\s*(?:final)?\s*class\s+(\w+)(?:\s*<[^>]*>)?(?:\s*:\s*[^{]+)?\s*\{",
            "struct": r"(?:public|private|internal|fileprivate)?\s*struct\s+(\w+)(?:\s*<[^>]*>)?(?:\s*:\s*[^{]+)?\s*\{",
            "protocol": r"(?:public|private|internal|fileprivate)?\s*protocol\s+(\w+)(?:\s*:\s*[^{]+)?\s*\{",
            "extension": r"(?:public|private|internal|fileprivate)?\s*extension\s+(\w+)(?:\s*:\s*[^{]+)?(?:\s*where\s+[^{]+)?\s*\{",
            "enum": r"(?:public|private|internal|fileprivate)?\s*enum\s+(\w+)(?:\s*<[^>]*>)?(?:\s*:\s*[^{]+)?\s*\{",
            "function": r"(?:public|private|internal|fileprivate)?\s*(?:static|class)?\s*func\s+(\w+)(?:\s*<[^>]*>)?\s*\([^)]*\)(?:\s*->\s*[^{]+)?\s*\{",
        }

        constructs = self._find_constructs_with_regex(content, patterns, file_path)

        if not constructs:
            # Create a fallback chunk for the entire file
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
                    semantic_type="module",
                    semantic_name=Path(file_path).stem,
                    semantic_path=Path(file_path).stem,
                    semantic_signature=f"module {Path(file_path).stem}",
                    semantic_parent=None,
                    semantic_context={"fallback_parsing": True},
                    semantic_scope="global",
                    semantic_language_features=["fallback_chunk"],
                )
            ]

        # Convert constructs to semantic chunks
        chunks = []
        for i, construct in enumerate(constructs):
            chunk = SemanticChunk(
                text=construct["text"],
                chunk_index=i,
                total_chunks=len(constructs),
                size=len(construct["text"]),
                file_path=file_path,
                file_extension=Path(file_path).suffix,
                line_start=construct["line_start"],
                line_end=construct["line_end"],
                semantic_chunking=False,
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

    # Helper methods for extracting Swift-specific constructs

    def _extract_import_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract import name from import declaration."""
        import_text = self._get_node_text(node, lines)
        match = re.search(r"import\s+([^\s\n]+)", import_text)
        return match.group(1) if match else None

    def _get_extended_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract the type being extended from extension node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "user_type":
                # Look for type_identifier in the user_type
                for grandchild in child.children:
                    if (
                        hasattr(grandchild, "type")
                        and grandchild.type == "type_identifier"
                    ):
                        return self._get_node_text(grandchild, lines)
        return None

    def _extract_inheritance_clause(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract inheritance/protocol conformance clause."""
        # Look for inheritance specifier (: BaseClass)
        inheritance_parts = []
        colon_found = False

        for child in node.children:
            if hasattr(child, "type"):
                if child.type == ":" and not colon_found:
                    inheritance_parts.append(":")
                    colon_found = True
                elif child.type == "inheritance_specifier" or (
                    colon_found and child.type == "user_type"
                ):
                    type_text = self._get_node_text(child, lines).strip()
                    if type_text and type_text != ":":
                        inheritance_parts.append(type_text)

        return " ".join(inheritance_parts) if inheritance_parts else None

    def _extract_generics(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract generic parameters."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "generic_parameter_clause":
                return self._get_node_text(child, lines)
        return None

    def _extract_where_clause(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract where clause from extensions or generics."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "generic_where_clause":
                    return self._get_node_text(child, lines)
                elif child.type == "type_constraints":
                    return self._get_node_text(child, lines)
        return None

    def _extract_access_modifier(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract access control modifier from modifiers node."""
        access_modifiers = ["public", "private", "internal", "fileprivate", "open"]

        # Look for modifiers child node
        for child in node.children:
            if hasattr(child, "type") and child.type == "modifiers":
                modifier_text = self._get_node_text(child, lines).lower()

                for modifier in access_modifiers:
                    if modifier in modifier_text:
                        return modifier

                break  # Found the modifiers node, no need to continue

        return None

    def _extract_modifiers(self, node: Any, lines: List[str]) -> List[str]:
        """Extract declaration modifiers from modifiers node."""
        found_modifiers = []

        # Look for direct modifiers children
        for child in node.children:
            if hasattr(child, "type") and child.type == "modifiers":
                modifier_text = self._get_node_text(child, lines)

                # Extract specific modifiers from the modifiers node
                all_modifiers = [
                    "static",
                    "class",
                    "final",
                    "override",
                    "convenience",
                    "required",
                    "lazy",
                    "weak",
                    "unowned",
                    "indirect",
                    "mutating",
                    "nonmutating",
                ]

                for modifier in all_modifiers:
                    if modifier in modifier_text.lower():
                        found_modifiers.append(modifier)

                break  # Found the modifiers node, no need to continue

        return found_modifiers

    def _extract_function_parameters(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract function parameter list."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "parameter_clause":
                return self._get_node_text(child, lines)
        return None

    def _extract_return_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract function return type."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"->\s*([^{]+)", node_text)
        return match.group(1).strip() if match else None

    def _extract_property_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract property type."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r":\s*([^=\n{]+)", node_text)
        return match.group(1).strip() if match else None

    def _extract_enum_cases(self, node: Any, lines: List[str]) -> List[str]:
        """Extract enum cases from Swift enum body."""
        cases = []

        # Look for enum_class_body
        for child in node.children:
            if hasattr(child, "type") and child.type == "enum_class_body":
                # Look for enum_entry nodes within the body
                for entry in child.children:
                    if hasattr(entry, "type") and entry.type == "enum_entry":
                        # Extract case names from enum_entry
                        for entry_child in entry.children:
                            if (
                                hasattr(entry_child, "type")
                                and entry_child.type == "simple_identifier"
                            ):
                                case_name = self._get_node_text(entry_child, lines)
                                if case_name:
                                    cases.append(case_name)

        return cases

    def _extract_class_members(
        self, node: Any, lines: List[str], scope_stack: List[str], content: str
    ) -> List[Dict[str, Any]]:
        """Extract all members from a class/struct/enum declaration."""
        members: List[Dict[str, Any]] = []

        # Find the class_body or enum_class_body
        for child in node.children:
            if hasattr(child, "type") and child.type in [
                "class_body",
                "enum_class_body",
            ]:
                # Process each member in the body
                for member in child.children:
                    if hasattr(member, "type"):
                        member_type = member.type

                        # Handle different member types
                        if member_type == "property_declaration":
                            self._handle_property_declaration(
                                member, members, lines, scope_stack, content
                            )
                        elif member_type == "function_declaration":
                            self._handle_function_declaration(
                                member, members, lines, scope_stack, content
                            )
                        elif member_type == "init_declaration":
                            self._handle_init_declaration(
                                member, members, lines, scope_stack, content
                            )
                        elif member_type == "deinit_declaration":
                            self._handle_deinit_declaration(
                                member, members, lines, scope_stack, content
                            )
                        elif member_type == "subscript_declaration":
                            self._handle_subscript_declaration(
                                member, members, lines, scope_stack, content
                            )
                break

        return members

    # Feature extraction methods

    def _get_class_features(
        self, access_modifier: Optional[str], modifiers: List[str]
    ) -> List[str]:
        """Get features for class declarations."""
        features = ["class_declaration"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        if "final" in modifiers:
            features.append("final_class")
        if "open" in modifiers:
            features.append("open_class")
        return features

    def _get_struct_features(
        self, access_modifier: Optional[str], modifiers: List[str]
    ) -> List[str]:
        """Get features for struct declarations."""
        features = ["struct_declaration"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        return features

    def _get_protocol_features(
        self, access_modifier: Optional[str], modifiers: List[str]
    ) -> List[str]:
        """Get features for protocol declarations."""
        features = ["protocol_declaration"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        return features

    def _get_extension_features(self, access_modifier: Optional[str]) -> List[str]:
        """Get features for extension declarations."""
        features = ["extension_declaration"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        return features

    def _get_enum_features(
        self, access_modifier: Optional[str], modifiers: List[str], cases: List[str]
    ) -> List[str]:
        """Get features for enum declarations."""
        features = ["enum_declaration"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        if cases:
            features.append("has_cases")
            if any("(" in case for case in cases):
                features.append("associated_values")
        return features

    def _get_function_features(
        self, access_modifier: Optional[str], modifiers: List[str], func_name: str
    ) -> List[str]:
        """Get features for function declarations."""
        features = ["function_declaration"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        if "static" in modifiers:
            features.append("static_function")
        if "class" in modifiers:
            features.append("class_function")
        if "override" in modifiers:
            features.append("override_function")
        if func_name.startswith("_"):
            features.append("private_function")
        return features

    def _get_init_features(
        self, access_modifier: Optional[str], modifiers: List[str]
    ) -> List[str]:
        """Get features for initializer declarations."""
        features = ["initializer"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        if "convenience" in modifiers:
            features.append("convenience_init")
        if "required" in modifiers:
            features.append("required_init")
        return features

    def _get_property_features(
        self, access_modifier: Optional[str], modifiers: List[str]
    ) -> List[str]:
        """Get features for property declarations."""
        features = ["property_declaration"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        if "static" in modifiers:
            features.append("static_property")
        if "class" in modifiers:
            features.append("class_property")
        if "lazy" in modifiers:
            features.append("lazy_property")
        if "weak" in modifiers:
            features.append("weak_property")
        if "unowned" in modifiers:
            features.append("unowned_property")
        return features

    def _get_subscript_features(
        self, access_modifier: Optional[str], modifiers: List[str]
    ) -> List[str]:
        """Get features for subscript declarations."""
        features = ["subscript_declaration"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        if "static" in modifiers:
            features.append("static_subscript")
        return features

    def _get_variable_features(
        self, access_modifier: Optional[str], modifiers: List[str], is_let: bool
    ) -> List[str]:
        """Get features for variable declarations."""
        features = ["constant" if is_let else "variable"]
        if access_modifier:
            features.append(f"access_{access_modifier}")
        if "static" in modifiers:
            features.append("static_variable")
        if "lazy" in modifiers:
            features.append("lazy_variable")
        return features

    def _get_identifier_from_node(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a Swift node."""
        # Swift-specific identifier types
        for child in node.children:
            if hasattr(child, "type"):
                if child.type in ["type_identifier", "simple_identifier", "identifier"]:
                    return str(self._get_node_text(child, lines))
                # For nested identifiers, check grandchildren
                if child.type in ["pattern", "value_binding_pattern"]:
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "simple_identifier"
                        ):
                            return str(self._get_node_text(grandchild, lines))
        return None
