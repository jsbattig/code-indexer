"""
Lua semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class LuaSemanticParser(BaseTreeSitterParser):
    """Semantic parser for Lua files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "lua")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (require statements, global variables)."""
        # Find require statements and global variable assignments
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "variable_declaration":
                    self._handle_global_variable(child, constructs, lines, scope_stack)
                elif child.type == "assignment_statement":
                    self._handle_global_assignment(
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
        """Handle Lua-specific AST node types."""
        if node_type == "function_declaration":
            self._handle_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "local_function":
            self._handle_local_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "variable_declaration":
            self._handle_variable_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "assignment_statement":
            self._handle_assignment_statement(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "local_variable_declaration":
            self._handle_local_variable_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "table_constructor":
            self._handle_table_constructor(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "return_statement":
            self._handle_return_statement(node, constructs, lines, scope_stack, content)
        elif node_type == "expression_statement":
            self._handle_expression_statement(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "function_call":
            self._handle_function_call(node, constructs, lines, scope_stack, content)
        elif node_type == "function_definition":
            self._handle_function_definition(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "ERROR":
            # Ensure ERROR nodes are handled even if they reach language constructs
            self._extract_from_error_node(node, constructs, lines, scope_stack, content)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        # These node types handle their own children directly
        return node_type in [
            "function_declaration",
            "local_function",
            "function_definition",
            "variable_declaration",  # We handle assignment_statement children directly to avoid duplication
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Lua constructs from ERROR node text using regex fallback."""
        constructs = []
        lines = error_text.split("\n")
        current_parent = ".".join(scope_stack) if scope_stack else None

        # Lua patterns
        patterns = [
            # Function patterns
            (r"^\s*function\s+([A-Za-z_][A-Za-z0-9_.:]*)\s*\(", "function"),
            (r"^\s*local\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "local_function"),
            # Table function assignments
            (r"^\s*([A-Za-z_][A-Za-z0-9_.:]*)\s*=\s*function\s*\(", "function"),
            # Local function assignments
            (
                r"^\s*local\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*function\s*\(",
                "local_function",
            ),
            # Table constructors
            (r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{", "table"),
            (r"^\s*local\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{", "local_table"),
            # Variable assignments
            (r"^\s*([A-Za-z_][A-Za-z0-9_.:]*)\s*=\s*", "variable"),
            (r"^\s*local\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*", "local_variable"),
            # Require statements
            (
                r"^\s*(?:local\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]",
                "require",
            ),
            # Module returns
            (r"^\s*return\s+([A-Za-z_][A-Za-z0-9_.:]*)", "module_return"),
        ]

        for i, line in enumerate(lines):
            line_num = start_line + i
            for pattern, construct_type in patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)

                    # Handle require pattern specially
                    if construct_type == "require" and len(match.groups()) > 1:
                        full_path = (
                            f"{current_parent}.{name}" if current_parent else name
                        )
                    else:
                        full_path = (
                            f"{current_parent}.{name}" if current_parent else name
                        )

                    # Determine if it's a method (contains colon)
                    if ":" in name:
                        construct_type = "method"

                    # Determine scope
                    scope = "local" if construct_type.startswith("local_") else "global"
                    if current_parent:
                        scope = "table"

                    features = []
                    if construct_type.startswith("local_"):
                        features.append("local")
                    if ":" in name:
                        features.append("method")
                    if construct_type == "require":
                        features.append("module_import")

                    context: Dict[str, Any] = {"regex_fallback": True}
                    if construct_type == "require" and len(match.groups()) > 1:
                        module_path = match.group(2)
                        if module_path:
                            context["module_path"] = module_path

                    constructs.append(
                        {
                            "type": construct_type,
                            "name": name,
                            "path": full_path,
                            "signature": line.strip(),
                            "parent": current_parent,
                            "scope": scope,
                            "line_start": line_num,
                            "line_end": line_num,
                            "text": line,
                            "context": context,
                            "features": features,
                        }
                    )
                    break

        return constructs

    def _handle_function_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Lua function declaration."""
        func_name = self._extract_function_name(node, lines)
        if not func_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{func_name}" if current_scope else func_name

        # Check if this is a local function
        is_local = self._is_local_function(node, lines)

        # Check for method syntax (contains colon)
        is_method = ":" in func_name
        features = []
        if is_method:
            features.append("method")
        if is_local:
            features.append("local")

        signature = self._extract_function_signature(node, lines)

        # Determine function type
        if is_local:
            func_type = "local_function"
        elif is_method:
            func_type = "method"
        else:
            func_type = "function"

        constructs.append(
            {
                "type": func_type,
                "name": func_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": (
                    "local" if is_local else ("table" if current_scope else "global")
                ),
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "function"},
                "features": features,
            }
        )

    def _handle_local_function_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Lua local function declaration."""
        func_name = self._extract_identifier(node, lines)
        if not func_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{func_name}" if current_scope else func_name

        signature = self._extract_function_signature(node, lines)

        constructs.append(
            {
                "type": "local_function",
                "name": func_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "local",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "local_function"},
                "features": ["local"],
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
        """Handle Lua variable declarations (local declarations)."""
        # Check if this is a local declaration by looking for 'local' keyword
        has_local = False
        assignment_node = None

        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "local":
                    has_local = True
                elif child.type == "assignment_statement":
                    assignment_node = child

        if assignment_node and has_local:
            # This is a local assignment, handle it with local context
            self._handle_assignment_statement(
                assignment_node, constructs, lines, scope_stack, content, is_local=True
            )
            # Don't traverse children if we already handled the assignment_statement
            # to avoid duplication
            self._traverse_variable_declaration_children_excluding_assignment(
                node, constructs, lines, scope_stack, content
            )
        else:
            # No local assignment found, traverse all children
            self._traverse_variable_declaration_children(
                node, constructs, lines, scope_stack, content
            )

    def _traverse_variable_declaration_children(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Traverse children of variable declaration to find nested constructs."""
        for child in node.children:
            if hasattr(child, "type"):
                # Handle ERROR nodes specially - they might contain function declarations
                if child.type == "ERROR":
                    self._extract_from_error_node(
                        child, constructs, lines, scope_stack, content
                    )
                # Handle assignment_statement specially to find anonymous functions
                elif child.type == "assignment_statement":
                    # Process the assignment but also look for nested function definitions
                    self._handle_assignment_statement(
                        child, constructs, lines, scope_stack, content, is_local=True
                    )
                    # Also traverse deeper to find any nested function_definition nodes
                    self._traverse_for_function_definitions(
                        child, constructs, lines, scope_stack, content
                    )
                elif child.type not in ["function_call"]:
                    self._handle_language_constructs(
                        child, child.type, constructs, lines, scope_stack, content
                    )
                # Only traverse deeper into nodes that might contain constructs we care about
                if hasattr(child, "children") and child.type not in [
                    "assignment_statement",  # We handle assignment_statement above
                    "ERROR",  # We handle ERROR nodes above
                ]:
                    self._traverse_variable_declaration_children(
                        child, constructs, lines, scope_stack, content
                    )

    def _traverse_variable_declaration_children_excluding_assignment(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Traverse children of variable declaration to find nested constructs, excluding assignment_statement to avoid duplication."""
        for child in node.children:
            if hasattr(child, "type"):
                # Handle ERROR nodes specially - they might contain function declarations
                if child.type == "ERROR":
                    self._extract_from_error_node(
                        child, constructs, lines, scope_stack, content
                    )
                # Skip assignment_statement to avoid duplication since we handled it above
                elif child.type == "assignment_statement":
                    # Still traverse deeper to find any nested function_definition nodes
                    self._traverse_for_function_definitions(
                        child, constructs, lines, scope_stack, content
                    )
                elif child.type not in ["function_call"]:
                    self._handle_language_constructs(
                        child, child.type, constructs, lines, scope_stack, content
                    )
                # Only traverse deeper into nodes that might contain constructs we care about
                if hasattr(child, "children") and child.type not in [
                    "assignment_statement",  # We handle assignment_statement above
                    "ERROR",  # We handle ERROR nodes above
                ]:
                    self._traverse_variable_declaration_children_excluding_assignment(
                        child, constructs, lines, scope_stack, content
                    )

    def _traverse_for_function_definitions(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Recursively traverse a node to find function_definition nodes."""
        if hasattr(node, "type"):
            if node.type == "function_definition":
                self._handle_function_definition(
                    node, constructs, lines, scope_stack, content
                )
                return  # Don't traverse children of function_definition

            # Traverse all children looking for function_definition nodes
            if hasattr(node, "children"):
                for child in node.children:
                    self._traverse_for_function_definitions(
                        child, constructs, lines, scope_stack, content
                    )

    def _handle_assignment_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
        is_local: bool = False,
    ):
        """Handle Lua assignment statements (including function assignments)."""
        node_text = self._get_node_text(node, lines)

        # Check if this is a require statement first (before other patterns)
        require_patterns = [
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",  # require("module")
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*require\s+['\"]([^'\"]+)['\"]",  # require "module"
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*require\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",  # require(variable)
        ]

        for pattern in require_patterns:
            require_match = re.search(pattern, node_text)
            if require_match:
                var_name = require_match.group(1)
                module_path = (
                    require_match.group(2) if len(require_match.groups()) > 1 else None
                )

                current_scope = ".".join(scope_stack)
                full_path = f"{current_scope}.{var_name}" if current_scope else var_name

                features = ["module_import"]
                if is_local:
                    features.append("local")

                context = {"declaration_type": "require"}
                if module_path and not module_path.startswith(
                    var_name
                ):  # Don't add if it's a variable name
                    try:
                        # Check if module_path is a valid module string (not a variable)
                        if all(c.isalnum() or c in "._-/" for c in module_path):
                            context["module_path"] = module_path
                    except Exception:
                        pass

                # Get the full text including 'local' keyword if it's a local assignment
                full_text = self._get_node_text(node, lines)
                if is_local and not full_text.strip().startswith("local"):
                    # The assignment node doesn't include the 'local' keyword, so we need to get it
                    # from the parent variable_declaration node or reconstruct it
                    full_text = f"local {full_text}"

                constructs.append(
                    {
                        "type": "require",
                        "name": var_name,
                        "path": full_path,
                        "signature": full_text.strip(),
                        "parent": current_scope if current_scope else None,
                        "scope": (
                            "local"
                            if is_local
                            else ("table" if current_scope else "global")
                        ),
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": full_text,
                        "context": context,
                        "features": features,
                    }
                )
                return  # Don't process as other assignment types

        # Check if this is a direct function assignment (var = function)
        func_name = self._extract_function_assignment_name(node, lines)
        if func_name:
            current_scope = ".".join(scope_stack)
            full_path = f"{current_scope}.{func_name}" if current_scope else func_name

            # Check for method syntax
            is_method = ":" in func_name
            features = []
            if is_method:
                features.append("method")
            if is_local:
                features.append("local")

            signature = node_text.split("\n")[0].strip()

            func_type = (
                "method"
                if is_method
                else ("local_function" if is_local else "function")
            )

            # Get the full text including 'local' keyword if it's a local assignment
            full_text = self._get_node_text(node, lines)
            if is_local and not full_text.strip().startswith("local"):
                full_text = f"local {full_text}"

            constructs.append(
                {
                    "type": func_type,
                    "name": func_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": current_scope if current_scope else None,
                    "scope": (
                        "local"
                        if is_local
                        else ("table" if current_scope else "global")
                    ),
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": full_text,
                    "context": {"declaration_type": "function_assignment"},
                    "features": features,
                }
            )
        # Check if this is a table assignment
        else:
            table_name = self._extract_table_assignment_name(node, lines)
            if table_name:
                current_scope = ".".join(scope_stack)
                full_path = (
                    f"{current_scope}.{table_name}" if current_scope else table_name
                )

                signature = node_text.split("\n")[0].strip()

                features = ["table"]
                if is_local:
                    features.append("local")

                table_type = "local_table" if is_local else "table"
                scope = (
                    "local" if is_local else ("table" if current_scope else "global")
                )

                # Get the full text including 'local' keyword if it's a local assignment
                full_text = self._get_node_text(node, lines)
                if is_local and not full_text.strip().startswith("local"):
                    full_text = f"local {full_text}"

                constructs.append(
                    {
                        "type": table_type,
                        "name": table_name,
                        "path": full_path,
                        "signature": signature,
                        "parent": current_scope if current_scope else None,
                        "scope": scope,
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": full_text,
                        "context": {
                            "declaration_type": (
                                "local_table" if is_local else "table_assignment"
                            )
                        },
                        "features": features,
                    }
                )

                # Process table contents for nested functions
                scope_stack.append(table_name)
                self._process_table_contents(
                    node, constructs, lines, scope_stack, content
                )
                scope_stack.pop()

    def _handle_expression_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Lua expression statements (including bare require calls)."""
        node_text = self._get_node_text(node, lines)

        # Check for bare require statements like require("module")
        bare_require_match = re.search(
            r"^\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", node_text
        )
        if bare_require_match:
            module_path = bare_require_match.group(1)
            current_scope = ".".join(scope_stack)

            # Use module path as the name for bare requires
            module_name = module_path.split(".")[-1]  # Get last part as name
            full_path = (
                f"{current_scope}.{module_name}" if current_scope else module_name
            )

            constructs.append(
                {
                    "type": "require",
                    "name": module_name,
                    "path": full_path,
                    "signature": node_text.strip(),
                    "parent": current_scope if current_scope else None,
                    "scope": "table" if current_scope else "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "bare_require",
                        "module_path": module_path,
                    },
                    "features": ["module_import", "bare_require"],
                }
            )

    def _handle_function_call(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Lua function calls (including bare require calls)."""
        node_text = self._get_node_text(node, lines)

        # Check for bare require calls like require("module")
        bare_require_match = re.search(
            r"^\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", node_text
        )
        if bare_require_match:
            module_path = bare_require_match.group(1)
            current_scope = ".".join(scope_stack)

            # Use module path as the name for bare requires
            module_name = module_path.split(".")[-1]  # Get last part as name
            full_path = (
                f"{current_scope}.{module_name}" if current_scope else module_name
            )

            constructs.append(
                {
                    "type": "require",
                    "name": module_name,
                    "path": full_path,
                    "signature": node_text.strip(),
                    "parent": current_scope if current_scope else None,
                    "scope": "table" if current_scope else "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "bare_require",
                        "module_path": module_path,
                    },
                    "features": ["module_import", "bare_require"],
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
        """Handle Lua function definitions (anonymous functions)."""
        current_scope = ".".join(scope_stack)

        # Generate a unique name for anonymous functions
        line_number = node.start_point[0] + 1
        func_name = f"anonymous_function_{line_number}"
        full_path = f"{current_scope}.{func_name}" if current_scope else func_name

        # Extract function signature
        signature = self._extract_anonymous_function_signature(node, lines)

        constructs.append(
            {
                "type": "function",
                "name": func_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "table" if current_scope else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "anonymous_function"},
                "features": ["anonymous"],
            }
        )

    def _extract_anonymous_function_signature(
        self, func_def_node: Any, lines: List[str]
    ) -> str:
        """Extract signature for an anonymous function definition."""
        func_text = self._get_node_text(func_def_node, lines)
        lines_list = func_text.split("\n")
        first_line = lines_list[0].strip()
        return first_line

    def _handle_local_variable_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Lua local variable declarations."""
        node_text = self._get_node_text(node, lines)

        # Check if this is a local function assignment
        func_name = self._extract_local_function_name(node, lines)
        if func_name:
            current_scope = ".".join(scope_stack)
            full_path = f"{current_scope}.{func_name}" if current_scope else func_name

            signature = node_text.split("\n")[0].strip()

            constructs.append(
                {
                    "type": "local_function",
                    "name": func_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": current_scope if current_scope else None,
                    "scope": "local",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "local_function_assignment"},
                    "features": ["local"],
                }
            )
        # Check if this is a local table
        else:
            table_name = self._extract_local_table_name(node, lines)
            if table_name:
                current_scope = ".".join(scope_stack)
                full_path = (
                    f"{current_scope}.{table_name}" if current_scope else table_name
                )

                signature = node_text.split("\n")[0].strip()

                constructs.append(
                    {
                        "type": "local_table",
                        "name": table_name,
                        "path": full_path,
                        "signature": signature,
                        "parent": current_scope if current_scope else None,
                        "scope": "local",
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": self._get_node_text(node, lines),
                        "context": {"declaration_type": "local_table"},
                        "features": ["local", "table"],
                    }
                )

    def _handle_table_constructor(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Lua table constructors."""
        # Process table fields for nested functions
        for child in node.children:
            if hasattr(child, "type"):
                self._handle_language_constructs(
                    child, child.type, constructs, lines, scope_stack, content
                )

    def _handle_return_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Lua return statements (for module patterns)."""
        node_text = self._get_node_text(node, lines)

        # Check if this looks like a module return
        if len(scope_stack) == 0:  # Top-level return
            module_name = self._extract_module_return_name(node, lines)
            if module_name:

                constructs.append(
                    {
                        "type": "module_return",
                        "name": module_name,
                        "path": module_name,
                        "signature": node_text.strip(),
                        "parent": None,
                        "scope": "global",
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": self._get_node_text(node, lines),
                        "context": {"declaration_type": "module_return"},
                        "features": ["module_export"],
                    }
                )

    def _handle_global_variable(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle global variable declarations."""
        var_name = self._extract_identifier(node, lines)
        if var_name:
            constructs.append(
                {
                    "type": "variable",
                    "name": var_name,
                    "path": var_name,
                    "signature": self._get_node_text(node, lines).strip(),
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "variable"},
                    "features": ["global_variable"],
                }
            )

    def _handle_global_assignment(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Handle global assignments at file level."""
        node_text = self._get_node_text(node, lines)

        # Check for require statements
        require_match = re.search(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]",
            node_text,
        )
        if require_match:
            var_name = require_match.group(1)
            module_path = require_match.group(2)

            constructs.append(
                {
                    "type": "require",
                    "name": var_name,
                    "path": var_name,
                    "signature": node_text.strip(),
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "require",
                        "module_path": module_path,
                    },
                    "features": ["module_import"],
                }
            )

    def _process_table_contents(
        self,
        table_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process contents within a table for nested functions."""
        # Find the table_constructor node within the assignment_statement
        table_constructor = self._find_table_constructor(table_node)
        if table_constructor:
            self._process_table_constructor_contents(
                table_constructor, constructs, lines, scope_stack, content
            )

    def _find_table_constructor(self, node: Any) -> Any:
        """Recursively find the table_constructor node in the AST."""
        if hasattr(node, "type") and node.type == "table_constructor":
            return node

        if hasattr(node, "children"):
            for child in node.children:
                result = self._find_table_constructor(child)
                if result:
                    return result

        return None

    def _process_table_constructor_contents(
        self,
        table_constructor: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process the contents of a table_constructor node."""
        for child in table_constructor.children:
            if hasattr(child, "type"):
                if child.type == "field":
                    self._handle_table_field(
                        child, constructs, lines, scope_stack, content
                    )
                else:
                    self._handle_language_constructs(
                        child, child.type, constructs, lines, scope_stack, content
                    )

    def _handle_table_field(
        self,
        field_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle a field within a table (potentially containing a function)."""
        # Look for function definitions within the field
        for child in field_node.children:
            if hasattr(child, "type"):
                if child.type == "function_definition":
                    # Extract the field name (function name)
                    field_name = self._extract_field_name(field_node, lines)
                    if field_name:
                        self._handle_table_function_definition(
                            child, field_name, constructs, lines, scope_stack, content
                        )
                else:
                    self._handle_language_constructs(
                        child, child.type, constructs, lines, scope_stack, content
                    )

    def _extract_field_name(self, field_node: Any, lines: List[str]) -> Optional[str]:
        """Extract the name of a table field."""
        # Look for identifier children
        for child in field_node.children:
            if hasattr(child, "type") and child.type == "identifier":
                return self._get_node_text(child, lines).strip()
        return None

    def _handle_table_function_definition(
        self,
        func_def_node: Any,
        func_name: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle a function definition within a table field."""
        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{func_name}" if current_scope else func_name

        # Extract function signature
        signature = self._extract_table_function_signature(
            func_def_node, func_name, lines
        )

        constructs.append(
            {
                "type": "function",
                "name": func_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope,
                "scope": "table",
                "line_start": func_def_node.start_point[0] + 1,
                "line_end": func_def_node.end_point[0] + 1,
                "text": self._get_node_text(func_def_node, lines),
                "context": {"declaration_type": "table_function"},
                "features": ["table_function"],
            }
        )

    def _extract_table_function_signature(
        self, func_def_node: Any, func_name: str, lines: List[str]
    ) -> str:
        """Extract signature for a table function definition."""
        func_text = self._get_node_text(func_def_node, lines)
        # Create a signature with the field name
        lines_list = func_text.split("\n")
        first_line = lines_list[0].strip()
        return f"{func_name} = {first_line}"

    def _extract_function_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract function name from function declaration node using pure AST approach."""
        try:
            # Look for the function name in various node structures
            for child in node.children:
                if hasattr(child, "type"):
                    if child.type == "identifier":
                        return self._get_node_text(child, lines).strip()
                    elif child.type == "method_index_expression":
                        # For MyClass:new style methods, return full path
                        return self._get_node_text(child, lines).strip()
                    elif child.type == "dot_index_expression":
                        # For MyClass.new style methods
                        return self._get_node_text(child, lines).strip()
        except Exception:
            pass

        return None

    def _extract_function_signature(self, node: Any, lines: List[str]) -> str:
        """Extract function signature including name and parameters using pure AST approach."""
        try:
            signature_parts = []

            # Check if it's a local function
            is_local = False
            for child in node.children:
                if hasattr(child, "type") and child.type == "local":
                    is_local = True
                    break

            if is_local:
                signature_parts.append("local")

            # Add function keyword
            signature_parts.append("function")

            # Extract function name and parameters
            func_name = None
            params = None

            for child in node.children:
                if hasattr(child, "type"):
                    if child.type in [
                        "identifier",
                        "method_index_expression",
                        "dot_index_expression",
                    ]:
                        func_name = self._get_node_text(child, lines).strip()
                    elif child.type == "parameters":
                        params = self._get_node_text(child, lines).strip()

            if func_name:
                signature_parts.append(func_name)
            if params:
                signature_parts.append(params)

            return " ".join(signature_parts)
        except Exception:
            pass

        return self._get_node_text(node, lines).split("\n")[0].strip()

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

    def _is_local_function(self, node: Any, lines: List[str]) -> bool:
        """Check if a function declaration is local using pure AST approach."""
        # Check if any child is 'local' (it should be first, but be thorough)
        if hasattr(node, "children"):
            for child in node.children:
                if hasattr(child, "type") and child.type == "local":
                    return True
        return False

    def _extract_identifier(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a node."""
        return self._get_identifier_from_node(node, lines)

    def _extract_function_assignment_name(
        self, assignment_node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract function name from assignment statement using pure AST approach."""
        try:
            # Look for: variable_list -> identifier and expression_list -> function_definition
            variable_name = None
            has_function = False

            for child in assignment_node.children:
                if hasattr(child, "type"):
                    if child.type == "variable_list":
                        # Get the identifier from variable_list (can be identifier or dot_index_expression)
                        for grandchild in child.children:
                            if hasattr(grandchild, "type") and grandchild.type in [
                                "identifier",
                                "dot_index_expression",
                            ]:
                                variable_name = self._get_node_text(
                                    grandchild, lines
                                ).strip()
                                break
                    elif child.type == "expression_list":
                        # Check if it contains a function_definition
                        for grandchild in child.children:
                            if (
                                hasattr(grandchild, "type")
                                and grandchild.type == "function_definition"
                            ):
                                has_function = True
                                break

            return variable_name if (variable_name and has_function) else None
        except Exception:
            return None

    def _extract_table_assignment_name(
        self, assignment_node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract table name from assignment statement using pure AST approach."""
        try:
            # Look for: variable_list -> identifier and expression_list -> table_constructor
            variable_name = None
            has_table = False

            for child in assignment_node.children:
                if hasattr(child, "type"):
                    if child.type == "variable_list":
                        # Get the identifier from variable_list (can be identifier or dot_index_expression)
                        for grandchild in child.children:
                            if hasattr(grandchild, "type") and grandchild.type in [
                                "identifier",
                                "dot_index_expression",
                            ]:
                                variable_name = self._get_node_text(
                                    grandchild, lines
                                ).strip()
                                break
                    elif child.type == "expression_list":
                        # Check if it contains a table_constructor
                        for grandchild in child.children:
                            if (
                                hasattr(grandchild, "type")
                                and grandchild.type == "table_constructor"
                            ):
                                has_table = True
                                break

            return variable_name if (variable_name and has_table) else None
        except Exception:
            return None

    def _extract_local_function_name(
        self, local_var_node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract function name from local variable declaration using pure AST approach."""
        try:
            # This is for patterns like: local funcname = function(...)
            # We need to find assignment_statement with function_definition
            for child in local_var_node.children:
                if hasattr(child, "type") and child.type == "assignment_statement":
                    return self._extract_function_assignment_name(child, lines)
            return None
        except Exception:
            return None

    def _extract_local_table_name(
        self, local_var_node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract table name from local variable declaration using pure AST approach."""
        try:
            # This is for patterns like: local tablename = {...}
            # We need to find assignment_statement with table_constructor
            for child in local_var_node.children:
                if hasattr(child, "type") and child.type == "assignment_statement":
                    return self._extract_table_assignment_name(child, lines)
            return None
        except Exception:
            return None

    def _extract_module_return_name(
        self, return_node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract module name from return statement using pure AST approach."""
        try:
            # Look for: return_statement -> expression_list -> identifier
            for child in return_node.children:
                if hasattr(child, "type") and child.type == "expression_list":
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "identifier"
                        ):
                            return self._get_node_text(grandchild, lines).strip()
            return None
        except Exception:
            return None

    def _is_duplicate_construct(
        self, new_construct: Dict[str, Any], existing_constructs: List[Dict[str, Any]]
    ) -> bool:
        """Check if a construct is already in the list with Lua-specific duplicate detection."""
        for existing in existing_constructs:
            # Standard duplicate check from base class
            if (
                existing.get("name") == new_construct.get("name")
                and existing.get("parent") == new_construct.get("parent")
                and existing.get("line_start") == new_construct.get("line_start")
                and existing.get("type") == new_construct.get("type")
            ):
                return True

            # Lua-specific duplicate check: local_table vs table, local_function vs function
            if (
                existing.get("name") == new_construct.get("name")
                and existing.get("parent") == new_construct.get("parent")
                and existing.get("line_start") == new_construct.get("line_start")
                and existing.get("line_end") == new_construct.get("line_end")
            ):
                # Check for local vs non-local versions of the same construct
                existing_type = existing.get("type", "")
                new_type = new_construct.get("type", "")

                # Table duplicates: local_table vs table
                if (existing_type == "local_table" and new_type == "table") or (
                    existing_type == "table" and new_type == "local_table"
                ):
                    return True

                # Function duplicates: local_function vs function
                if (existing_type == "local_function" and new_type == "function") or (
                    existing_type == "function" and new_type == "local_function"
                ):
                    return True

        return False
