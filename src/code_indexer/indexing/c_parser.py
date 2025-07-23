"""
C semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Handles C-specific constructs including:
- Structs, unions, enums
- Functions and function declarations
- Typedefs and type aliases
- Global variables
- Preprocessor directives
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class CSemanticParser(BaseTreeSitterParser):
    """Semantic parser for C files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "c")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (includes, defines, etc.)."""
        # Find preprocessor directives
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "preproc_include":
                    self._extract_include(child, constructs, lines)
                elif child.type == "preproc_def":
                    self._extract_define(child, constructs, lines)
                elif child.type == "preproc_function_def":
                    self._extract_macro_function(child, constructs, lines)

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C-specific AST node types."""
        if node_type == "struct_specifier":
            self._handle_struct_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "union_specifier":
            self._handle_union_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "enum_specifier":
            self._handle_enum_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "function_definition":
            self._handle_function_definition(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declaration":
            self._handle_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "type_definition":
            self._handle_typedef(node, constructs, lines, scope_stack, content)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        # These node types handle their own members
        return node_type in [
            "struct_specifier",
            "union_specifier",
            "enum_specifier",
            "function_definition",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract C constructs from ERROR node text using regex fallback."""
        constructs = []
        lines = error_text.split("\n")
        current_parent = ".".join(scope_stack) if scope_stack else None

        # C struct pattern
        struct_pattern = r"^\s*(?:typedef\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)\s*[{;]"

        # C union pattern
        union_pattern = r"^\s*(?:typedef\s+)?union\s+([A-Za-z_][A-Za-z0-9_]*)\s*[{;]"

        # C enum pattern
        enum_pattern = r"^\s*(?:typedef\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)\s*[{;]"

        # C function pattern (return_type function_name(...))
        function_pattern = r"^\s*(?:static\s+|extern\s+|inline\s+)*(?:const\s+)?([A-Za-z_][A-Za-z0-9_]*(?:\s*\*)*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("

        # C typedef pattern
        typedef_pattern = r"^\s*typedef\s+.*?\s+([A-Za-z_][A-Za-z0-9_]*)\s*[;,]"

        # C global variable pattern
        variable_pattern = r"^\s*(?:static\s+|extern\s+|const\s+)*([A-Za-z_][A-Za-z0-9_]*(?:\s*\*)*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[=;,]"

        # C preprocessor patterns
        include_pattern = r"^\s*#\s*include\s*[<\"](.*?)[>\"]"
        define_pattern = r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)"
        macro_function_pattern = r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("

        patterns = [
            (struct_pattern, "struct"),
            (union_pattern, "union"),
            (enum_pattern, "enum"),
            (function_pattern, "function"),
            (typedef_pattern, "typedef"),
            (variable_pattern, "variable"),
            (include_pattern, "include"),
            (define_pattern, "define"),
            (macro_function_pattern, "macro_function"),
        ]

        for i, line in enumerate(lines):
            line_num = start_line + i
            for pattern, construct_type in patterns:
                match = re.search(pattern, line)
                if match:
                    if construct_type == "function":
                        name = match.group(2)
                        return_type = match.group(1).strip()
                        signature = f"{return_type} {name}(...)"
                    elif construct_type == "variable":
                        name = match.group(2)
                        var_type = match.group(1).strip()
                        signature = f"{var_type} {name}"
                    elif construct_type in ["include", "define", "macro_function"]:
                        name = match.group(1)
                        signature = line.strip()
                    else:
                        name = match.group(1)
                        signature = line.strip()

                    full_path = f"{current_parent}.{name}" if current_parent else name

                    constructs.append(
                        {
                            "type": construct_type,
                            "name": name,
                            "path": full_path,
                            "signature": signature,
                            "parent": current_parent,
                            "scope": "global",
                            "line_start": line_num,
                            "line_end": line_num,
                            "text": line,
                            "context": {"regex_fallback": True},
                            "features": [f"{construct_type}_declaration"],
                        }
                    )
                    break

        return constructs

    def _extract_include(
        self, node: Any, constructs: List[Dict[str, Any]], lines: List[str]
    ):
        """Extract #include directive."""
        include_text = self._get_node_text(node, lines)
        match = re.search(r'#\s*include\s*[<"](.*?)[>"]', include_text)
        if match:
            include_name = match.group(1)
            constructs.append(
                {
                    "type": "include",
                    "name": include_name,
                    "path": include_name,
                    "signature": include_text.strip(),
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": include_text,
                    "context": {"declaration_type": "include"},
                    "features": ["preprocessor_directive"],
                }
            )

    def _extract_define(
        self, node: Any, constructs: List[Dict[str, Any]], lines: List[str]
    ):
        """Extract #define directive."""
        define_text = self._get_node_text(node, lines)
        match = re.search(r"#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)", define_text)
        if match:
            define_name = match.group(1)
            constructs.append(
                {
                    "type": "define",
                    "name": define_name,
                    "path": define_name,
                    "signature": define_text.strip(),
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": define_text,
                    "context": {"declaration_type": "define"},
                    "features": ["preprocessor_directive"],
                }
            )

    def _extract_macro_function(
        self, node: Any, constructs: List[Dict[str, Any]], lines: List[str]
    ):
        """Extract function-like macro definition."""
        macro_text = self._get_node_text(node, lines)
        match = re.search(r"#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", macro_text)
        if match:
            macro_name = match.group(1)
            constructs.append(
                {
                    "type": "macro_function",
                    "name": macro_name,
                    "path": macro_name,
                    "signature": macro_text.strip(),
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": macro_text,
                    "context": {"declaration_type": "macro_function"},
                    "features": ["preprocessor_directive", "function_like_macro"],
                }
            )

    def _handle_struct_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C struct declaration."""
        struct_name = self._extract_struct_name(node, lines)
        if not struct_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{struct_name}" if current_scope else struct_name

        # Get struct signature
        signature = self._extract_struct_signature(node, lines)

        constructs.append(
            {
                "type": "struct",
                "name": struct_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global" if not scope_stack else "struct",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "struct"},
                "features": ["struct_declaration"],
            }
        )

        # Process struct members
        scope_stack.append(struct_name)
        self._process_struct_members(node, constructs, lines, scope_stack, content)
        scope_stack.pop()

    def _handle_union_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C union declaration."""
        union_name = self._extract_union_name(node, lines)
        if not union_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{union_name}" if current_scope else union_name

        signature = self._extract_union_signature(node, lines)

        constructs.append(
            {
                "type": "union",
                "name": union_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global" if not scope_stack else "union",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "union"},
                "features": ["union_declaration"],
            }
        )

        # Process union members
        scope_stack.append(union_name)
        self._process_struct_members(node, constructs, lines, scope_stack, content)
        scope_stack.pop()

    def _handle_enum_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C enum declaration."""
        enum_name = self._extract_enum_name(node, lines)
        if not enum_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{enum_name}" if current_scope else enum_name

        signature = self._extract_enum_signature(node, lines)

        constructs.append(
            {
                "type": "enum",
                "name": enum_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global" if not scope_stack else "enum",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "enum"},
                "features": ["enum_declaration"],
            }
        )

    def _handle_function_definition(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C function definition."""
        function_name = self._extract_function_name(node, lines)
        if not function_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{function_name}" if current_scope else function_name
        )

        signature = self._extract_function_signature(node, lines)

        constructs.append(
            {
                "type": "function",
                "name": function_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global" if not scope_stack else "function",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "function"},
                "features": ["function_definition"],
            }
        )

    def _handle_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C variable declarations."""
        # Try to extract variable declarations from declaration nodes
        node_text = self._get_node_text(node, lines)

        # Skip function declarations (they have parentheses)
        if "(" in node_text and ")" in node_text and "=" not in node_text:
            return

        # Extract variable name and type (including arrays)
        var_match = re.search(
            r"(?:static\s+|extern\s+|const\s+)*([A-Za-z_][A-Za-z0-9_]*(?:\s*\*)*?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[.*?\])?\s*[=;,]",
            node_text,
        )

        if var_match:
            var_type = var_match.group(1).strip()
            var_name = var_match.group(2)

            current_scope = ".".join(scope_stack)
            full_path = f"{current_scope}.{var_name}" if current_scope else var_name

            constructs.append(
                {
                    "type": "variable",
                    "name": var_name,
                    "path": full_path,
                    "signature": f"{var_type} {var_name}",
                    "parent": current_scope if current_scope else None,
                    "scope": "global" if not scope_stack else "local",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": node_text,
                    "context": {
                        "declaration_type": "variable",
                        "variable_type": var_type,
                    },
                    "features": ["variable_declaration"],
                }
            )

    def _handle_typedef(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C typedef declarations."""
        typedef_name = self._extract_typedef_name(node, lines)
        if not typedef_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{typedef_name}" if current_scope else typedef_name

        signature = self._extract_typedef_signature(node, lines)

        constructs.append(
            {
                "type": "typedef",
                "name": typedef_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global" if not scope_stack else "typedef",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "typedef"},
                "features": ["typedef_declaration"],
            }
        )

    def _process_struct_members(
        self,
        struct_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process members within a struct/union."""
        # Find the field declaration list
        for child in struct_node.children:
            if hasattr(child, "type") and child.type == "field_declaration_list":
                for field_child in child.children:
                    if (
                        hasattr(field_child, "type")
                        and field_child.type == "field_declaration"
                    ):
                        self._extract_field_declaration(
                            field_child, constructs, lines, scope_stack
                        )

    def _extract_field_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract field declaration from struct/union member."""
        node_text = self._get_node_text(node, lines)

        # Check if this field_declaration is actually a function (has function_declarator)
        has_function_declarator = False
        for child in node.children:
            if hasattr(child, "type") and child.type == "function_declarator":
                has_function_declarator = True
                break

        if has_function_declarator:
            # This is actually a function misclassified as a field due to parsing errors
            # Extract it as a function instead
            function_name = self._extract_function_name_from_field_declaration(
                node, lines
            )
            if function_name:
                current_scope = ".".join(scope_stack)
                full_path = (
                    f"{current_scope}.{function_name}"
                    if current_scope
                    else function_name
                )

                signature = self._extract_function_signature_from_field_declaration(
                    node, lines
                )

                constructs.append(
                    {
                        "type": "function",
                        "name": function_name,
                        "path": full_path,
                        "signature": signature,
                        "parent": current_scope if current_scope else None,
                        "scope": "global" if not scope_stack else "function",
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": node_text,
                        "context": {
                            "declaration_type": "function",
                            "extracted_from_error": True,
                        },
                        "features": ["function_definition", "error_recovery"],
                    }
                )
            return

        # Extract field type and name for regular fields
        field_match = re.search(
            r"([A-Za-z_][A-Za-z0-9_]*(?:\s*\*)*)\s+([A-Za-z_][A-Za-z0-9_]*)", node_text
        )

        if field_match:
            field_type = field_match.group(1).strip()
            field_name = field_match.group(2)

            current_scope = ".".join(scope_stack)
            full_path = f"{current_scope}.{field_name}" if current_scope else field_name

            constructs.append(
                {
                    "type": "field",
                    "name": field_name,
                    "path": full_path,
                    "signature": f"{field_type} {field_name}",
                    "parent": current_scope if current_scope else None,
                    "scope": "struct" if scope_stack else "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": node_text,
                    "context": {"declaration_type": "field", "field_type": field_type},
                    "features": ["field_declaration"],
                }
            )

    # Helper methods for extracting names and signatures

    def _extract_function_name_from_field_declaration(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract function name from a function_declarator within a field_declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "function_declarator":
                # Look for the identifier within the function_declarator
                for func_child in child.children:
                    if (
                        hasattr(func_child, "type")
                        and func_child.type == "field_identifier"
                    ):
                        return self._get_node_text(func_child, lines)
        return None

    def _extract_function_signature_from_field_declaration(
        self, node: Any, lines: List[str]
    ) -> str:
        """Extract function signature from a function_declarator within a field_declaration."""
        return_type = "int"  # Default since it's hard to parse from malformed context
        function_name = self._extract_function_name_from_field_declaration(node, lines)

        # Extract parameter list
        params = "()"  # Default empty params
        for child in node.children:
            if hasattr(child, "type") and child.type == "function_declarator":
                for func_child in child.children:
                    if (
                        hasattr(func_child, "type")
                        and func_child.type == "parameter_list"
                    ):
                        params = self._get_node_text(func_child, lines)
                        break
                break

        return f"{return_type} {function_name}{params}"

    def _extract_struct_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract struct name from struct_specifier node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_identifier":
                return self._get_node_text(child, lines).strip()
        return None

    def _extract_union_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract union name from union_specifier node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_identifier":
                return self._get_node_text(child, lines).strip()
        return None

    def _extract_enum_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract enum name from enum_specifier node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_identifier":
                return self._get_node_text(child, lines).strip()
        return None

    def _extract_function_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract function name from function_definition node."""
        # Look for function_declarator child
        for child in node.children:
            if hasattr(child, "type") and child.type == "function_declarator":
                for subchild in child.children:
                    if hasattr(subchild, "type") and subchild.type == "identifier":
                        return self._get_node_text(subchild, lines).strip()
        return None

    def _extract_typedef_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract typedef name from type_definition node."""
        # The last identifier is usually the typedef name
        identifiers = []
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_identifier":
                identifiers.append(self._get_node_text(child, lines).strip())
        return identifiers[-1] if identifiers else None

    def _extract_struct_signature(self, node: Any, lines: List[str]) -> str:
        """Extract struct signature."""
        node_text = self._get_node_text(node, lines)
        # Get the first line or until the opening brace
        first_line = node_text.split("\n")[0].strip()
        if "{" in first_line:
            first_line = first_line.split("{")[0].strip()
        return first_line

    def _extract_union_signature(self, node: Any, lines: List[str]) -> str:
        """Extract union signature."""
        node_text = self._get_node_text(node, lines)
        first_line = node_text.split("\n")[0].strip()
        if "{" in first_line:
            first_line = first_line.split("{")[0].strip()
        return first_line

    def _extract_enum_signature(self, node: Any, lines: List[str]) -> str:
        """Extract enum signature."""
        node_text = self._get_node_text(node, lines)
        first_line = node_text.split("\n")[0].strip()
        if "{" in first_line:
            first_line = first_line.split("{")[0].strip()
        return first_line

    def _extract_function_signature(self, node: Any, lines: List[str]) -> str:
        """Extract function signature including return type, name, and parameters."""
        node_text = self._get_node_text(node, lines)
        # Find the signature part (before the opening brace)
        signature_match = re.match(r"([^{]*)", node_text.strip())
        if signature_match:
            return signature_match.group(1).strip()
        return node_text.split("{")[0].strip()

    def _extract_typedef_signature(self, node: Any, lines: List[str]) -> str:
        """Extract typedef signature."""
        node_text = self._get_node_text(node, lines)
        # Remove semicolon and clean up
        signature = node_text.replace(";", "").strip()
        if "\n" in signature:
            signature = signature.split("\n")[0].strip()
        return signature

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
