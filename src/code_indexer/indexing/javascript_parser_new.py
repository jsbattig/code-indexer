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
        return node_type in ["class_declaration", "function_declaration"]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract JavaScript constructs from ERROR node text using regex fallback."""
        constructs = []

        # JavaScript-specific regex patterns
        patterns = {
            "function": r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
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

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing using the original regex-based approach."""
        from .javascript_parser import JavaScriptSemanticParser as OriginalJSParser

        original_parser = OriginalJSParser(self.config)
        return original_parser.chunk(content, file_path)

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
                    "text": self._get_node_text(node, lines),
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

    def _extract_js_parameters(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract parameters from JavaScript function/method."""
        for child in node.children:
            if hasattr(child, "type") and "parameter" in child.type:
                return self._get_node_text(child, lines)
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
