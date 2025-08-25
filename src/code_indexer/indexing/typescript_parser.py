"""
TypeScript semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class TypeScriptSemanticParser(BaseTreeSitterParser):
    """Semantic parser for TypeScript files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "typescript")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (imports, exports, namespaces)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "import_statement":
                    self._handle_import_statement(child, constructs, lines)
                elif child.type == "export_statement":
                    self._handle_export_statement(child, constructs, lines)
                elif child.type == "namespace_declaration":
                    self._handle_namespace_declaration(
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
        """Handle TypeScript-specific AST node types."""
        if node_type == "function_declaration":
            self._handle_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "arrow_function":
            self._handle_arrow_function(node, constructs, lines, scope_stack, content)
        elif node_type == "class_declaration":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "abstract_class_declaration":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "interface_declaration":
            self._handle_interface_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "type_alias_declaration":
            self._handle_type_alias_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "enum_declaration":
            self._handle_enum_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "method_definition":
            self._handle_method_definition(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "variable_declaration":
            self._handle_variable_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "namespace_declaration":
            self._handle_namespace_declaration(node, constructs, lines, scope_stack)
        elif node_type == "internal_module":
            # TypeScript might use "internal_module" for namespace declarations
            self._handle_namespace_declaration(node, constructs, lines, scope_stack)
        elif node_type == "module_declaration":
            # Another possible AST node type for namespaces
            self._handle_namespace_declaration(node, constructs, lines, scope_stack)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        return node_type in [
            "class_declaration",
            "abstract_class_declaration",
            "interface_declaration",
            "function_declaration",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract TypeScript constructs from ERROR node text using regex fallback."""
        constructs = []

        # TypeScript-specific regex patterns
        patterns = {
            "function": r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)(?:\s*<[^>]*>)?(?:\s*\([^)]*\))?",
            "arrow_function": r"^\s*(?:const|let|var)\s+(\w+)\s*:\s*[^=]*=\s*(?:\([^)]*\)|[^=])\s*=>\s*",
            "class": r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:<[^>]*>)?(?:\s+extends\s+\w+)?(?:\s+implements\s+[\w,\s]+)?\s*{",
            "interface": r"^\s*(?:export\s+)?interface\s+(\w+)(?:<[^>]*>)?\s*(?:extends\s+[\w,\s]+)?\s*{",
            "type": r"^\s*(?:export\s+)?type\s+(\w+)(?:<[^>]*>)?\s*=",
            "enum": r"^\s*(?:export\s+)?enum\s+(\w+)\s*{",
            "namespace": r"^\s*(?:export\s+)?namespace\s+(\w+)\s*{",
            "method": r"^\s*(?:public|private|protected|static|async)?\s*(\w+)\s*<[^>]*>?\s*\([^)]*\)\s*:\s*[^{]*{",
            "variable": r"^\s*(?:const|let|var)\s+(\w+)\s*:\s*[^=]*=",
            "import": r"^\s*import\s+(?:\{[^}]+\}|\w+)\s+from\s+['\"]([^'\"]+)['\"]",
            "export": r"^\s*export\s+(?:default\s+)?(?:function|class|interface|type|enum|const|let|var)\s+(\w+)",
        }

        lines = error_text.split("\n")

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)

                    # Find the end of this construct
                    end_line = self._find_ts_construct_end(
                        lines, line_idx, construct_type
                    )

                    # Build construct text
                    construct_lines = lines[line_idx : end_line + 1]
                    construct_text = "\n".join(construct_lines)

                    parent = scope_stack[-1] if scope_stack else None
                    full_path = f"{parent}.{name}" if parent else name

                    constructs.append(
                        {
                            "type": construct_type,
                            "name": name,
                            "path": full_path,
                            "signature": line.strip(),
                            "parent": parent,
                            "scope": (
                                "class" if construct_type == "method" else "global"
                            ),
                            "line_start": start_line + line_idx + 1,
                            "line_end": start_line + end_line + 1,
                            "text": construct_text,
                            "context": {"extracted_from_error": True},
                            "features": [f"{construct_type}_implementation"],
                        }
                    )

        return constructs

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing using text chunking when all else fails."""
        from .semantic_chunker import TextChunker
        from pathlib import Path

        text_chunker = TextChunker(self.config)
        chunk_dicts = text_chunker.chunk_text(content, Path(file_path))

        # Convert dictionary chunks to SemanticChunk objects
        semantic_chunks = []
        for chunk_dict in chunk_dicts:
            semantic_chunk = SemanticChunk(
                text=chunk_dict["text"],
                chunk_index=chunk_dict.get("chunk_index", 0),
                total_chunks=chunk_dict.get("total_chunks", len(chunk_dicts)),
                size=chunk_dict.get("size", len(chunk_dict["text"])),
                file_path=file_path,
                file_extension=chunk_dict.get(
                    "file_extension", Path(file_path).suffix.lstrip(".")
                ),
                line_start=chunk_dict.get("line_start", 1),
                line_end=chunk_dict.get("line_end", 1),
                semantic_chunking=False,  # This is fallback, not semantic
            )
            semantic_chunks.append(semantic_chunk)

        return semantic_chunks

    # Helper methods for TypeScript constructs

    def _handle_import_statement(
        self, node: Any, constructs: List[Dict[str, Any]], lines: List[str]
    ):
        """Handle import statement."""
        import_text = self._get_node_text(node, lines)
        constructs.append(
            {
                "type": "import",
                "name": "import",
                "path": "import",
                "signature": import_text,
                "parent": None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": import_text,
                "context": {"declaration_type": "import"},
                "features": ["import_statement"],
            }
        )

    def _handle_export_statement(
        self, node: Any, constructs: List[Dict[str, Any]], lines: List[str]
    ):
        """Handle export statement."""
        export_text = self._get_node_text(node, lines)
        constructs.append(
            {
                "type": "export",
                "name": "export",
                "path": "export",
                "signature": export_text,
                "parent": None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": export_text,
                "context": {"declaration_type": "export"},
                "features": ["export_statement"],
            }
        )

    def _handle_namespace_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle namespace declaration."""
        namespace_name = self._get_identifier_from_node(node, lines)
        if namespace_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{namespace_name}" if parent_path else namespace_name
            )

            constructs.append(
                {
                    "type": "namespace",
                    "name": namespace_name,
                    "path": full_path,
                    "signature": f"namespace {namespace_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "namespace",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "namespace"},
                    "features": ["namespace_declaration"],
                }
            )

            # Process nested elements within the namespace (including nested namespaces)
            scope_stack.append(namespace_name)
            self._process_namespace_members(node, constructs, lines, scope_stack, "")
            scope_stack.pop()

    def _process_namespace_members(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process members of a namespace including nested namespaces."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "namespace_body":
                    # Process all declarations in the namespace body
                    for member in child.children:
                        self._traverse_node(
                            member, constructs, lines, scope_stack, content
                        )

    def _handle_function_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle function declaration."""
        function_name = self._get_identifier_from_node(node, lines)
        if function_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{function_name}" if parent_path else function_name
            )

            params = self._extract_ts_parameters(node, lines)
            return_type = self._extract_ts_return_type(node, lines)
            generics = self._extract_ts_generics(node, lines)

            signature = f"function {function_name}"
            if generics:
                signature += f"<{generics}>"
            if params:
                signature += f"({params})"
            if return_type:
                signature += f": {return_type}"

            constructs.append(
                {
                    "type": "function",
                    "name": function_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "function",
                        "parameters": params,
                        "return_type": return_type,
                        "generics": generics,
                    },
                    "features": ["function_declaration"],
                }
            )

    def _handle_class_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle class declaration."""
        class_name = self._get_identifier_from_node(node, lines)
        if class_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{class_name}" if parent_path else class_name

            generics = self._extract_ts_generics(node, lines)
            extends = self._extract_ts_extends(node, lines)
            implements = self._extract_ts_implements(node, lines)

            signature = f"class {class_name}"
            if generics:
                signature += f"<{generics}>"
            if extends:
                signature += f" extends {extends}"
            if implements:
                signature += f" implements {implements}"

            constructs.append(
                {
                    "type": "class",
                    "name": class_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "class",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "class",
                        "generics": generics,
                        "extends": extends,
                        "implements": implements,
                    },
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
        """Handle interface declaration."""
        interface_name = self._get_identifier_from_node(node, lines)
        if interface_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{interface_name}" if parent_path else interface_name
            )

            generics = self._extract_ts_generics(node, lines)
            extends = self._extract_ts_extends(node, lines)

            signature = f"interface {interface_name}"
            if generics:
                signature += f"<{generics}>"
            if extends:
                signature += f" extends {extends}"

            constructs.append(
                {
                    "type": "interface",
                    "name": interface_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "interface",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "interface",
                        "generics": generics,
                        "extends": extends,
                    },
                    "features": ["interface_declaration"],
                }
            )

    def _handle_type_alias_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle type alias declaration."""
        type_name = self._get_identifier_from_node(node, lines)
        if type_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{type_name}" if parent_path else type_name

            generics = self._extract_ts_generics(node, lines)

            signature = f"type {type_name}"
            if generics:
                signature += f"<{generics}>"

            constructs.append(
                {
                    "type": "type",
                    "name": type_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "type",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "type",
                        "generics": generics,
                    },
                    "features": ["type_declaration"],
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
        """Handle enum declaration."""
        enum_name = self._get_identifier_from_node(node, lines)
        if enum_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{enum_name}" if parent_path else enum_name

            constructs.append(
                {
                    "type": "enum",
                    "name": enum_name,
                    "path": full_path,
                    "signature": f"enum {enum_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "enum",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "enum"},
                    "features": ["enum_declaration"],
                }
            )

    def _handle_method_definition(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle method definition."""
        method_name = self._get_identifier_from_node(node, lines)
        if method_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{method_name}" if parent_path else method_name

            params = self._extract_ts_parameters(node, lines)
            return_type = self._extract_ts_return_type(node, lines)
            generics = self._extract_ts_generics(node, lines)

            signature = f"{method_name}"
            if generics:
                signature += f"<{generics}>"
            if params:
                signature += f"({params})"
            if return_type:
                signature += f": {return_type}"

            constructs.append(
                {
                    "type": "method",
                    "name": method_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "method",
                        "parameters": params,
                        "return_type": return_type,
                        "generics": generics,
                    },
                    "features": ["method_declaration"],
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
        """Handle variable declaration."""
        var_name = self._get_identifier_from_node(node, lines)
        if var_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{var_name}" if parent_path else var_name

            var_type = self._extract_ts_variable_type(node, lines)

            signature = f"variable {var_name}"
            if var_type:
                signature += f": {var_type}"

            constructs.append(
                {
                    "type": "variable",
                    "name": var_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "variable",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "variable",
                        "type": var_type,
                    },
                    "features": ["variable_declaration"],
                }
            )

    def _handle_arrow_function(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle arrow function."""
        # Try to find the function name from parent assignment
        function_name = self._extract_arrow_function_name(node, lines)
        if function_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{function_name}" if parent_path else function_name
            )

            params = self._extract_ts_parameters(node, lines)
            return_type = self._extract_ts_return_type(node, lines)

            signature = f"const {function_name} = "
            if params:
                signature += f"({params}) => "
            if return_type:
                signature += return_type

            constructs.append(
                {
                    "type": "arrow_function",
                    "name": function_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "arrow_function",
                        "parameters": params,
                        "return_type": return_type,
                    },
                    "features": ["arrow_function_declaration"],
                }
            )

    def _process_class_members(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process members of a class/interface."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "class_body":
                    for member in child.children:
                        self._traverse_node(
                            member, constructs, lines, scope_stack, content
                        )

    # TypeScript-specific helper methods

    def _extract_ts_parameters(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract TypeScript parameters with types."""
        for child in node.children:
            if hasattr(child, "type") and "parameter" in child.type:
                return self._get_node_text(child, lines)
        return None

    def _extract_ts_return_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract TypeScript return type."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_annotation":
                return self._get_node_text(child, lines)
        return None

    def _extract_ts_generics(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract TypeScript generic parameters."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_parameters":
                return self._get_node_text(child, lines)
        return None

    def _extract_ts_extends(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract extends clause."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "class_heritage":
                return self._get_node_text(child, lines)
        return None

    def _extract_ts_implements(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract implements clause."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "implements_clause":
                return self._get_node_text(child, lines)
        return None

    def _extract_ts_variable_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract variable type annotation."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_annotation":
                return self._get_node_text(child, lines)
        return None

    def _extract_arrow_function_name(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract name from arrow function assignment."""
        parent = getattr(node, "parent", None)
        if parent and hasattr(parent, "type") and "assignment" in parent.type:
            return self._get_identifier_from_node(parent, lines)
        return None

    def _get_identifier_from_node(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a TypeScript node."""
        for child in node.children:
            if hasattr(child, "type") and child.type in [
                "identifier",
                "type_identifier",
                "property_identifier",  # TypeScript methods use property_identifier
            ]:
                return str(self._get_node_text(child, lines))
        return None

    def _find_ts_construct_end(
        self, lines: List[str], start_line: int, construct_type: str
    ) -> int:
        """Find the end line of a TypeScript construct."""
        if construct_type in [
            "function",
            "class",
            "interface",
            "enum",
            "namespace",
            "method",
        ]:
            # Find matching braces
            brace_count = 0
            for i in range(start_line, len(lines)):
                line = lines[i]
                brace_count += line.count("{") - line.count("}")
                if brace_count == 0 and "{" in line:
                    return i
        elif construct_type in ["type", "variable", "arrow_function"]:
            # Single line or until semicolon
            for i in range(start_line, min(start_line + 5, len(lines))):
                if ";" in lines[i] or (
                    i > start_line and not lines[i].strip().endswith(",")
                ):
                    return i

        return min(start_line + 10, len(lines) - 1)
