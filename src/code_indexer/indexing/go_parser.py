"""
Go semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class GoSemanticParser(BaseTreeSitterParser):
    """Semantic parser for Go files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "go")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (package, imports)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "package_clause":
                    package_name = self._extract_package_name(child, lines)
                    if package_name:
                        scope_stack.append(package_name)
                        constructs.append(
                            {
                                "type": "package",
                                "name": package_name,
                                "path": package_name,
                                "signature": f"package {package_name}",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "package"},
                                "features": ["package_declaration"],
                            }
                        )
                elif child.type == "import_declaration":
                    self._handle_import_declaration(child, constructs, lines)

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Go-specific AST node types."""
        if node_type == "function_declaration":
            self._handle_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "method_declaration":
            self._handle_method_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "type_declaration":
            self._handle_type_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "const_declaration":
            self._handle_const_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "var_declaration":
            self._handle_var_declaration(node, constructs, lines, scope_stack, content)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        return node_type in [
            "function_declaration",
            "method_declaration",
            "type_declaration",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Go constructs from ERROR node text using regex fallback."""
        constructs = []

        # Go-specific regex patterns
        patterns = {
            "function": r"^\s*func\s+(?:\[([^]]+)\]\s+)?(\w+)\s*\([^)]*\)\s*[^{]*\{",
            "method": r"^\s*func\s+\(([^)]+)\)\s+(\w+)\s*\([^)]*\)\s*[^{]*\{",
            "struct": r"^\s*type\s+(\w+)(?:\[([^]]+)\])?\s+struct\s*\{",
            "interface": r"^\s*type\s+(\w+)(?:\[([^]]+)\])?\s+interface\s*\{",
            "type": r"^\s*type\s+(\w+)(?:\[([^]]+)\])?\s+(.+)",
            "const": r"^\s*const\s+(\w+)\s*=",
            "var": r"^\s*var\s+(\w+)\s*",
        }

        lines = error_text.split("\n")

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    # Extract name based on construct type
                    receiver: Optional[str] = None
                    if construct_type == "method":
                        receiver = str(match.group(1))
                        name = str(match.group(2))
                    else:
                        name = str(match.group(1))

                    # Find the end of this construct
                    end_line = self._find_go_construct_end(
                        lines, line_idx, construct_type
                    )

                    # Build construct text
                    construct_lines = lines[line_idx : end_line + 1]
                    construct_text = "\n".join(construct_lines)

                    parent = scope_stack[-1] if scope_stack else None
                    full_path = f"{parent}.{name}" if parent else name

                    context_dict: Dict[str, Any] = {"extracted_from_error": True}

                    # Add extra context for methods
                    if construct_type == "method" and receiver is not None:
                        context_dict["receiver"] = receiver

                    construct_dict = {
                        "type": construct_type,
                        "name": name,
                        "path": full_path,
                        "signature": line.strip(),
                        "parent": parent,
                        "scope": "global",
                        "line_start": start_line + line_idx + 1,
                        "line_end": start_line + end_line + 1,
                        "text": construct_text,
                        "context": context_dict,
                        "features": [f"{construct_type}_implementation"],
                    }

                    constructs.append(construct_dict)

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

    # Helper methods for Go constructs

    def _extract_package_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract package name from package clause."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "package_identifier":
                return self._get_node_text(child, lines)
        return None

    def _handle_import_declaration(
        self, node: Any, constructs: List[Dict[str, Any]], lines: List[str]
    ):
        """Handle import declaration."""
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
                "features": ["import_declaration"],
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
        """Handle function declaration."""
        function_name = self._get_identifier_from_node(node, lines)
        if function_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{function_name}" if parent_path else function_name
            )

            params = self._extract_go_parameters(node, lines)
            return_type = self._extract_go_return_type(node, lines)
            type_params = self._extract_go_type_parameters(node, lines)

            # Extract full signature from the node text instead of constructing it
            node_text = self._get_node_text(node, lines)
            signature = self._extract_go_function_signature(node_text, function_name)

            # Detect multiple return values
            features = ["function_declaration"]
            if return_type and "," in str(return_type):
                features.append("multiple_returns")

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
                    "text": node_text,
                    "context": {
                        "declaration_type": "function",
                        "parameters": params,
                        "return_type": return_type,
                        "type_parameters": type_params,
                    },
                    "features": features,
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
        """Handle method declaration."""
        method_name = self._get_identifier_from_node(node, lines)
        if method_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{method_name}" if parent_path else method_name

            receiver = self._extract_go_receiver(node, lines)
            params = self._extract_go_parameters(node, lines)
            return_type = self._extract_go_return_type(node, lines)
            type_params = self._extract_go_type_parameters(node, lines)

            # Extract full signature from the node text instead of constructing it
            node_text = self._get_node_text(node, lines)
            signature = self._extract_go_method_signature(node_text, method_name)

            # Detect multiple return values
            features = ["method_declaration"]
            if return_type and "," in str(return_type):
                features.append("multiple_returns")

            constructs.append(
                {
                    "type": "method",
                    "name": method_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "method",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": node_text,
                    "context": {
                        "declaration_type": "method",
                        "receiver": receiver,
                        "parameters": params,
                        "return_type": return_type,
                        "type_parameters": type_params,
                    },
                    "features": features,
                }
            )

    def _handle_type_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle type declaration (struct, interface, type alias)."""
        # For Go, type names are in type_spec children, not directly in type_declaration
        type_name = self._extract_go_type_name(node, lines)
        if type_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{type_name}" if parent_path else type_name

            type_params = self._extract_go_type_parameters(node, lines)
            type_def = self._extract_go_type_definition(node, lines)

            # Determine specific type based on type_def content
            construct_type = "type"  # Default
            if type_def:
                if "struct" in str(type_def):
                    construct_type = "struct"
                elif "interface" in str(type_def):
                    construct_type = "interface"

            # Extract full signature from the node text instead of constructing it
            node_text = self._get_node_text(node, lines)
            signature = self._extract_go_type_signature(
                node_text, type_name, construct_type
            )

            constructs.append(
                {
                    "type": construct_type,
                    "name": type_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": construct_type,
                        "type_parameters": type_params,
                        "type_definition": type_def,
                    },
                    "features": [f"{construct_type}_declaration"],
                }
            )

    def _handle_const_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle const declaration."""
        const_name = self._get_identifier_from_node(node, lines)
        if const_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{const_name}" if parent_path else const_name

            constructs.append(
                {
                    "type": "const",
                    "name": const_name,
                    "path": full_path,
                    "signature": f"const {const_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "const"},
                    "features": ["const_declaration"],
                }
            )

    def _handle_var_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle var declaration."""
        var_name = self._get_identifier_from_node(node, lines)
        if var_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{var_name}" if parent_path else var_name

            constructs.append(
                {
                    "type": "var",
                    "name": var_name,
                    "path": full_path,
                    "signature": f"var {var_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "var"},
                    "features": ["var_declaration"],
                }
            )

    # Go-specific helper methods

    def _extract_go_receiver(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract receiver from method declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "parameter_list":
                # Get the full parameter list text
                param_text = self._get_node_text(child, lines)
                # Extract just the type from "(var_name *Type)" format
                if (
                    param_text
                    and param_text.startswith("(")
                    and param_text.endswith(")")
                ):
                    # Remove parentheses and split to get type part
                    inner = param_text[1:-1].strip()  # Remove ( and )
                    parts = inner.split()  # Split by whitespace
                    if len(parts) >= 2:
                        # Return everything after the variable name (the type)
                        return " ".join(parts[1:])
                    elif len(parts) == 1:
                        # Single part, could be just the type
                        return parts[0]
                return param_text
        return None

    def _extract_go_parameters(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract parameters from function/method."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "parameter_list":
                params_text = self._get_node_text(child, lines)
                # Strip outer parentheses if present to avoid double parentheses
                if (
                    params_text
                    and params_text.startswith("(")
                    and params_text.endswith(")")
                ):
                    params_text = params_text[1:-1]
                return params_text
        return None

    def _extract_go_return_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract return type from function/method."""
        # Look for return type by examining the node structure
        found_params = False
        for child in node.children:
            if hasattr(child, "type"):
                # Skip the parameter list that contains function parameters
                if child.type == "parameter_list" and not found_params:
                    found_params = True
                    continue
                # Now look for return type after function parameters
                elif child.type in [
                    "type_identifier",
                    "pointer_type",
                    "slice_type",
                ]:
                    return self._get_node_text(child, lines)
                # Second parameter_list contains return types for multiple returns
                elif child.type == "parameter_list" and found_params:
                    return self._get_node_text(child, lines)
        return None

    def _extract_go_type_parameters(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract type parameters (generics) from declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_parameter_list":
                return self._get_node_text(child, lines)
        return None

    def _extract_go_type_definition(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract type definition from type declaration."""
        # Look in type_spec child for struct_type, interface_type, etc.
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_spec":
                # First look for struct_type or interface_type (priority over type_identifier)
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type in [
                        "struct_type",
                        "interface_type",
                    ]:
                        return self._get_node_text(grandchild, lines)
                # If no struct/interface found, look for type_identifier (type alias)
                for grandchild in child.children:
                    if (
                        hasattr(grandchild, "type")
                        and grandchild.type == "type_identifier"
                    ):
                        return self._get_node_text(grandchild, lines)
        return None

    def _find_go_construct_end(
        self, lines: List[str], start_line: int, construct_type: str
    ) -> int:
        """Find the end line of a Go construct."""
        if construct_type in ["function", "method", "struct", "interface"]:
            # Find matching braces
            brace_count = 0
            for i in range(start_line, len(lines)):
                line = lines[i]
                brace_count += line.count("{") - line.count("}")
                if brace_count == 0 and "{" in line:
                    return i
        elif construct_type in ["type", "const", "var"]:
            # Single line or until we find a complete statement
            for i in range(start_line, min(start_line + 3, len(lines))):
                if lines[i].strip().endswith(";") or (
                    i > start_line and not lines[i].strip().endswith(",")
                ):
                    return i

        return min(start_line + 10, len(lines) - 1)

    def _extract_go_function_signature(self, node_text: str, function_name: str) -> str:
        """Extract the Go function signature from node text."""
        # Get the function declaration line
        lines = node_text.split("\n")
        for line in lines:
            if "func" in line and function_name in line and "(" in line:
                # Extract everything up to the opening brace or end of line
                signature = line.split("{")[0].strip()
                return signature
        return f"func {function_name}()"

    def _extract_go_method_signature(self, node_text: str, method_name: str) -> str:
        """Extract the Go method signature from node text."""
        # Get the method declaration line
        lines = node_text.split("\n")
        for line in lines:
            if "func" in line and method_name in line and "(" in line:
                # Extract everything up to the opening brace or end of line
                signature = line.split("{")[0].strip()
                return signature
        return f"func {method_name}()"

    def _extract_go_type_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract type name from type_declaration via type_spec."""
        # Look for type_spec child, then type_identifier within it
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_spec":
                return self._get_identifier_from_node(child, lines)
        return None

    def _extract_go_type_signature(
        self, node_text: str, type_name: str, construct_type: str
    ) -> str:
        """Extract the Go type signature from node text."""
        # Get the type declaration line
        lines = node_text.split("\n")
        for line in lines:
            if "type" in line and type_name in line:
                # For single-line type declarations
                if "{" not in line:
                    return line.strip()
                else:
                    # For struct/interface with braces, just return the declaration part
                    signature = line.split("{")[0].strip()
                    return signature
        return f"type {type_name}"
