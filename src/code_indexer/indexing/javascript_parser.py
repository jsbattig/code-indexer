"""
JavaScript semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class JavaScriptSemanticParser(BaseTreeSitterParser):
    """Semantic parser for JavaScript files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "javascript")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (imports, exports)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "import_statement":
                    self._handle_import_statement(child, constructs, lines)
                elif child.type == "export_statement":
                    self._handle_export_statement(child, constructs, lines)

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle JavaScript-specific AST node types."""
        if node_type == "function_declaration":
            self._handle_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "generator_function_declaration":
            self._handle_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "arrow_function":
            self._handle_arrow_function(node, constructs, lines, scope_stack, content)
        elif node_type == "class_declaration":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "method_definition":
            self._handle_method_definition(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "variable_declaration":
            self._handle_variable_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "lexical_declaration":
            self._handle_lexical_declaration(
                node, constructs, lines, scope_stack, content
            )

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        return node_type in [
            "class_declaration",
            "function_declaration",
            "arrow_function",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract JavaScript constructs from ERROR node text using regex fallback."""
        constructs = []

        # JavaScript-specific regex patterns
        patterns = {
            "function": r"^\s*(?:export\s+)?(?:async\s+)?function\s*\*?\s+(\w+)\s*\(",
            "arrow_function": r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:\([^)]*\)|[^=])\s*=>\s*",
            "class": r"^\s*(?:export\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?\s*{",
            "method": r"^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*{",
            "variable": r"^\s*(?:const|let|var)\s+(\w+)\s*=",
            "import": r"^\s*import\s+(?:\{[^}]+\}|\w+)\s+from\s+['\"]([^'\"]+)['\"]",
            "export": r"^\s*export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)",
        }

        lines = error_text.split("\n")

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)

                    # Find the end of this construct
                    end_line = self._find_js_construct_end(
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

    def _is_function_assignment(self, node_text: str) -> bool:
        """Check if a variable assignment is actually a function assignment."""
        # Look for arrow functions or direct function expressions
        # But exclude object literals that contain functions

        # Check for arrow functions first
        if "=>" in node_text:
            # Make sure it's not inside an object literal by checking the pattern
            # const name = (...) => ... (direct arrow assignment)
            # vs const name = { key: (...) => ... } (object with arrow function)
            lines = [line.strip() for line in node_text.split("\n")]
            first_line = lines[0] if lines else ""

            # More flexible arrow function detection
            if "=" in first_line and "=>" in first_line:
                # Check if the => appears after the = on the same line
                # This handles: const name = (...) => ... (direct arrow assignment)
                equal_pos = first_line.find("=")
                arrow_pos = first_line.find("=>")
                if equal_pos < arrow_pos:
                    return True

            # Handle multi-line arrow functions where => is on the first line after =
            if "=" in first_line and len(lines) > 1:
                for line in lines[1:3]:  # Check next couple of lines
                    if "=>" in line and not line.strip().startswith("//"):
                        return True

        # Check for direct function expressions
        if "function(" in node_text:
            # Check if it's a direct assignment like: const name = function() { ... }
            # vs object literal like: const name = { method: function() { ... } }
            lines = [line.strip() for line in node_text.split("\n")]
            first_line = lines[0] if lines else ""
            # Direct function assignment should have pattern: const/let/var name = function(
            if (
                "=" in first_line
                and "function(" in first_line
                and first_line.count("{") <= 1
            ):
                return True

        return False

    def _extract_function_signature_from_assignment(
        self, node_text: str, function_name: str
    ) -> str:
        """Extract function signature from assignment text."""
        lines = node_text.split("\n")
        for line in lines:
            line = line.strip()
            if function_name in line and ("=>" in line or "function(" in line):
                if "=>" in line:
                    # Arrow function: const name = (params) => ...
                    if "=" in line:
                        right_side = line.split("=", 1)[1].strip()
                        if right_side.startswith("(") and "=>" in right_side:
                            params = right_side.split("=>")[0].strip()
                            return f"const {function_name} = {params} =>"
                        else:
                            return f"const {function_name} = () =>"
                elif "function(" in line:
                    # Function expression: const name = function(params) ...
                    if "=" in line:
                        right_side = line.split("=", 1)[1].strip()
                        return f"const {function_name} = {right_side.split('{')[0].strip()}"
                break
        return f"const {function_name}"

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

    # Helper methods for JavaScript constructs

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

            params = self._extract_js_parameters(node, lines)
            signature = f"function {function_name}"
            if params:
                signature += f"({params})"

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
                    },
                    "features": ["function_declaration"],
                }
            )

            # Process nested functions by adding to scope stack
            scope_stack.append(function_name)
            self._process_function_body(node, constructs, lines, scope_stack, content)
            scope_stack.pop()

    def _handle_arrow_function(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle arrow function."""
        # Arrow functions might be assigned to variables
        function_name = self._extract_arrow_function_name(node, lines)
        if function_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{function_name}" if parent_path else function_name
            )

            params = self._extract_js_parameters(node, lines)
            signature = f"const {function_name} = "
            if params:
                signature += f"({params}) => "

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
                    },
                    "features": ["arrow_function_declaration"],
                }
            )

            # Process nested functions by adding to scope stack
            scope_stack.append(function_name)
            self._process_arrow_function_body(
                node, constructs, lines, scope_stack, content
            )
            scope_stack.pop()
        else:
            # Even anonymous arrow functions can contain nested functions
            # Create a temporary scope name for anonymous arrow functions
            temp_scope = f"anonymous_arrow_{node.start_point[0]}_{node.start_point[1]}"
            scope_stack.append(temp_scope)
            self._process_arrow_function_body(
                node, constructs, lines, scope_stack, content
            )
            scope_stack.pop()

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

            constructs.append(
                {
                    "type": "class",
                    "name": class_name,
                    "path": full_path,
                    "signature": f"class {class_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "class",
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

            params = self._extract_js_parameters(node, lines)
            signature = f"{method_name}"
            if params:
                signature += f"({params})"

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
        """Handle variable declaration (var)."""
        self._handle_variable_like_declaration(
            node, constructs, lines, scope_stack, "variable"
        )

    def _handle_lexical_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle lexical declaration (const/let)."""
        self._handle_variable_like_declaration(
            node, constructs, lines, scope_stack, "variable"
        )

    def _handle_variable_like_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        var_type: str,
    ):
        """Handle variable-like declarations."""
        var_name = self._get_identifier_from_node(node, lines)
        if var_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{var_name}" if parent_path else var_name

            # Check if this is a function assignment (arrow function or function expression)
            node_text = self._get_node_text(node, lines)
            if self._is_function_assignment(node_text):
                # Detect arrow function vs function expression
                is_arrow_function = "=>" in node_text
                function_type = "arrow_function" if is_arrow_function else "function"

                signature = self._extract_function_signature_from_assignment(
                    node_text, var_name
                )
                constructs.append(
                    {
                        "type": function_type,
                        "name": var_name,
                        "path": full_path,
                        "signature": signature,
                        "parent": scope_stack[-1] if scope_stack else None,
                        "scope": "function",
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": node_text,
                        "context": {"declaration_type": function_type},
                        "features": ["function_declaration"]
                        + (["arrow_function"] if is_arrow_function else []),
                    }
                )
            else:
                # Regular variable
                constructs.append(
                    {
                        "type": var_type,
                        "name": var_name,
                        "path": full_path,
                        "signature": f"{var_type} {var_name}",
                        "parent": scope_stack[-1] if scope_stack else None,
                        "scope": "variable",
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": node_text,
                        "context": {"declaration_type": var_type},
                        "features": [f"{var_type}_declaration"],
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
        """Process members of a class."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "class_body":
                    for member in child.children:
                        self._traverse_node(
                            member, constructs, lines, scope_stack, content
                        )

    def _process_function_body(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process the body of a function to find nested functions."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "statement_block":
                    # Process all statements in the function body
                    for statement in child.children:
                        self._traverse_node(
                            statement, constructs, lines, scope_stack, content
                        )

    def _process_arrow_function_body(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process the body of an arrow function to find nested functions."""
        for child in node.children:
            if hasattr(child, "type"):
                # Arrow functions can have statement_block or direct expression
                if child.type in ["statement_block", "expression_statement"]:
                    if child.type == "statement_block":
                        # Block body: { ... }
                        for statement in child.children:
                            self._traverse_node(
                                statement, constructs, lines, scope_stack, content
                            )
                    else:
                        # Expression body
                        self._traverse_node(
                            child, constructs, lines, scope_stack, content
                        )

    def _extract_js_parameters(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract parameters from JavaScript function/method."""
        for child in node.children:
            if hasattr(child, "type") and "parameter" in child.type:
                params_text = self._get_node_text(child, lines)
                # Strip outer parentheses if present
                if (
                    params_text
                    and params_text.startswith("(")
                    and params_text.endswith(")")
                ):
                    params_text = params_text[1:-1]
                return params_text
        return None

    def _extract_arrow_function_name(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract name from arrow function assignment."""
        # Look for parent assignment
        parent = getattr(node, "parent", None)
        if parent and hasattr(parent, "type") and "assignment" in parent.type:
            return self._get_identifier_from_node(parent, lines)
        return None

    def _find_js_construct_end(
        self, lines: List[str], start_line: int, construct_type: str
    ) -> int:
        """Find the end line of a JavaScript construct."""
        if construct_type in ["function", "class", "method"]:
            # Find matching braces
            brace_count = 0
            for i in range(start_line, len(lines)):
                line = lines[i]
                brace_count += line.count("{") - line.count("}")
                if brace_count == 0 and "{" in line:
                    return i
        elif construct_type in ["variable", "arrow_function"]:
            # Single line or until semicolon
            for i in range(start_line, min(start_line + 5, len(lines))):
                if ";" in lines[i] or (
                    i > start_line and not lines[i].strip().endswith(",")
                ):
                    return i

        return min(start_line + 10, len(lines) - 1)

    def _get_identifier_from_node(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a JavaScript node."""
        # For lexical_declaration and variable_declaration, look inside variable_declarator
        if hasattr(node, "type") and node.type in (
            "lexical_declaration",
            "variable_declaration",
        ):
            for child in node.children:
                if hasattr(child, "type") and child.type == "variable_declarator":
                    # Look for identifier inside variable_declarator
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "identifier"
                        ):
                            return str(self._get_node_text(grandchild, lines))

        # For other node types, check for various identifier types including property_identifier
        for child in node.children:
            if hasattr(child, "type") and child.type in [
                "identifier",
                "property_identifier",  # JavaScript methods use property_identifier
            ]:
                return str(self._get_node_text(child, lines))
        return None
