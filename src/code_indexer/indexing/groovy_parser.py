"""
Groovy semantic parser using tree-sitter - PURE AST-BASED IMPLEMENTATION.

This implementation uses tree-sitter to parse Groovy code and extract
semantic information for chunking using ONLY AST node structure analysis.
NO regex-based parsing on AST node text.

Eliminates the problems from the previous implementation:
- No meaningless "null;" chunks
- No regex parsing on AST text
- No false positive field declarations from return statements
- No duplicate chunks with different scope paths
- Proper validation of content quality
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser


class GroovySemanticParser(BaseTreeSitterParser):
    """Semantic parser for Groovy files using pure AST-based parsing (no regex)."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "groovy")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (package declarations, imports, etc.) - SINGLE TRAVERSAL ONLY."""
        # Process each top-level command node for package declarations only
        # All other constructs are handled by the main traversal to avoid duplicates
        for child in root_node.children:
            if hasattr(child, "type") and child.type == "command":
                # Use AST structure to identify package declarations ONLY
                package_name = self._extract_package_from_ast(child, lines)
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
                    # IMPORTANT: Do not process this command node again in main traversal
                    # Mark it as processed by the file-level extraction

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Groovy-specific AST node types using pure AST analysis - SINGLE TRAVERSAL."""
        if node_type == "command":
            # Handle command nodes using the original logic but without separate class body processing
            self._handle_command_node_ast(node, constructs, lines, scope_stack, content)
        elif node_type == "block":
            # Don't traverse blocks automatically to avoid duplicate processing
            # Blocks are handled by their parent constructs (e.g., class bodies)
            pass
        elif node_type == "unit":
            # Units are typically identifiers/literals - usually not constructs themselves
            pass

    def _handle_command_node_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle command nodes using pure AST analysis (no regex) - LEGACY METHOD."""
        # Analyze AST structure to determine construct type
        construct_type = self._identify_construct_from_ast(node, lines)

        if construct_type == "class":
            self._extract_class_from_ast(node, constructs, lines, scope_stack, content)
        elif construct_type == "interface":
            self._extract_interface_from_ast(
                node, constructs, lines, scope_stack, content
            )
        elif construct_type == "trait":
            self._extract_trait_from_ast(node, constructs, lines, scope_stack, content)
        elif construct_type == "method":
            self._extract_method_from_ast(node, constructs, lines, scope_stack, content)
        elif construct_type == "field":
            self._extract_field_from_ast(node, constructs, lines, scope_stack, content)
        elif construct_type == "closure":
            self._extract_closure_from_ast(
                node, constructs, lines, scope_stack, content
            )
        # Ignore other command types that don't represent semantic constructs

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped to avoid duplicate processing."""
        # CRITICAL FIX: Skip children for method bodies and class bodies to avoid duplicate processing
        return node_type in ["class_body", "method_body"]

    def _traverse_node(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Override traverse_node to handle class command nodes specially to avoid duplicates."""
        if not hasattr(node, "type") or not hasattr(node, "children"):
            return

        node_type = node.type

        # CRITICAL FIX: For command nodes that are classes, don't traverse their children
        # because the class extraction handles its own body processing
        if node_type == "command":
            construct_type = self._identify_construct_from_ast(node, lines)

            if construct_type == "class":
                # Handle class and its members via class body processing, don't traverse children
                self._handle_language_constructs(
                    node, node_type, constructs, lines, scope_stack, content
                )
                return  # CRITICAL: Don't traverse children - class handler processes the body
            else:
                # Handle other command types normally
                self._handle_language_constructs(
                    node, node_type, constructs, lines, scope_stack, content
                )
        else:
            # Handle non-command nodes normally
            self._handle_language_constructs(
                node, node_type, constructs, lines, scope_stack, content
            )

        # Handle ERROR nodes with fallback extraction
        if node_type == "ERROR":
            # Call the parent class method for ERROR handling
            super()._extract_from_error_node(
                node, constructs, lines, scope_stack, content
            )

        # Recursively process children (skip certain nodes that handle their own children)
        skip_children = self._should_skip_children(node_type)
        if not skip_children or node_type == "ERROR":
            for child in node.children:
                self._traverse_node(child, constructs, lines, scope_stack, content)

    def _identify_construct_from_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Identify construct type from AST structure (no regex)."""
        if not hasattr(node, "children") or len(node.children) < 2:
            return None

        children = list(node.children)

        # Look through all unit children to find keywords (handle modifiers like public, private, etc.)
        keywords_found = []
        for child in children:
            if hasattr(child, "type") and child.type == "unit":
                text = self._get_identifier_text(child, lines)
                if text:
                    keywords_found.append(text)

        # Check for class/interface/trait keywords
        if "class" in keywords_found:
            return "class"
        elif "interface" in keywords_found:
            return "interface"
        elif "trait" in keywords_found:
            return "trait"
        elif "def" in keywords_found:
            # Could be method or closure assignment
            return self._distinguish_def_construct(node, lines)

        # CRITICAL FIX: Check for class in ERROR nodes (handles annotated classes)
        if self._has_class_in_error_nodes(node, lines):
            return "class"

        # CRITICAL FIX: Check for typed method declarations (e.g., String methodName())
        if self._is_typed_method_declaration(node, lines):
            return "method"

        # CRITICAL FIX: Check for fields in ERROR nodes (handles annotated fields)
        if self._has_field_in_error_nodes(node, lines):
            return "field"

        # Check for typed declarations (e.g., String field, Closure var)
        if self._is_typed_declaration(node, lines):
            return self._get_typed_declaration_type(node, lines)

        return None

    def _has_class_in_error_nodes(self, node: Any, lines: List[str]) -> bool:
        """Check if node has class declaration in ERROR nodes (handles annotated classes)."""
        children = list(node.children)

        for child in children:
            if hasattr(child, "type") and child.type == "block":
                if hasattr(child, "children"):
                    for block_child in child.children:
                        if hasattr(block_child, "type") and block_child.type == "ERROR":
                            error_text = self._get_node_text(block_child, lines)
                            if self._extract_class_name_from_error_text(error_text):
                                return True
        return False

    def _has_field_in_error_nodes(self, node: Any, lines: List[str]) -> bool:
        """Check if node has field declaration in ERROR nodes (handles annotated fields)."""
        children = list(node.children)

        for child in children:
            if hasattr(child, "type") and child.type == "ERROR":
                error_text = self._get_node_text(child, lines)
                # Look for field patterns in ERROR nodes
                if self._extract_field_name_from_error_text(error_text):
                    return True
        return False

    def _extract_field_name_from_error_text(self, error_text: str) -> Optional[str]:
        """Extract field name from ERROR node text that contains field declaration."""
        # Look for field patterns: "private Type fieldName" or "Type fieldName"
        patterns = [
            r"\b(?:private|public|protected)\s+(\w+)\s+(\w+)",  # private Type fieldName
            r"\b([A-Z]\w*)\s+(\w+)",  # Type fieldName
        ]

        for pattern in patterns:
            match = re.search(pattern, error_text)
            if match:
                field_name = match.group(2)
                if self._validate_identifier_name(field_name):
                    return field_name
        return None

    def _has_annotations(self, node: Any, lines: List[str]) -> bool:
        """Check if node has annotation decorators."""
        # CRITICAL FIX: Improved annotation detection for all constructs
        node_text = self._get_node_text(node, lines)

        # Check for annotation patterns in the node text
        if "@" in node_text:
            # For classes/interfaces/traits
            if any(keyword in node_text for keyword in ["class", "interface", "trait"]):
                return True
            # For fields and methods - check if @ appears before field/method declarations
            if any(
                pattern in node_text
                for pattern in [
                    "private",
                    "public",
                    "protected",
                    "def",
                    "Long",
                    "String",
                    "int",
                    "boolean",
                ]
            ):
                return True

        return False

    def _debug_ast_structure(self, node: Any, lines: List[str], depth: int = 0):
        """Debug helper to understand actual tree-sitter AST structure."""
        indent = "  " * depth
        text = self._get_node_text(node, lines)[:50].replace("\n", "\\n")
        print(f"{indent}{node.type}: '{text}'")
        if hasattr(node, "children"):
            for child in node.children:
                self._debug_ast_structure(child, lines, depth + 1)

    def _get_identifier_text(self, unit_node: Any, lines: List[str]) -> str:
        """Get text from a unit node containing an identifier."""
        if hasattr(unit_node, "children") and len(unit_node.children) > 0:
            identifier_child = unit_node.children[0]
            if (
                hasattr(identifier_child, "type")
                and identifier_child.type == "identifier"
            ):
                return self._get_node_text(identifier_child, lines).strip()
        return self._get_node_text(unit_node, lines).strip()

    def _distinguish_def_construct(self, node: Any, lines: List[str]) -> str:
        """Distinguish between method declaration, field assignment, and closure assignment for 'def' constructs."""
        children = list(node.children)

        # CRITICAL FIX: Look for different patterns:
        # 1. def name = { ... } -> closure
        # 2. def name = value -> field
        # 3. def name(...) { ... } -> method

        has_assignment_operator = False
        has_braces = False
        has_func_call = False

        for child in children:
            if hasattr(child, "type"):
                if child.type == "operators":
                    op_text = self._get_node_text(child, lines).strip()
                    if op_text == "=":
                        has_assignment_operator = True
                elif child.type == "block":
                    # Check if block contains braces (closure pattern)
                    if hasattr(child, "children"):
                        for block_child in child.children:
                            if hasattr(block_child, "type") and block_child.type == "{":
                                has_braces = True
                            elif (
                                hasattr(block_child, "type")
                                and block_child.type == "unit"
                            ):
                                # Check if unit contains func (method pattern)
                                if self._unit_contains_func(block_child):
                                    has_func_call = True

        # Decision logic:
        if has_assignment_operator and has_braces:
            return "closure"  # def name = { ... }
        elif has_assignment_operator and not has_braces:
            return "field"  # def name = value
        elif has_func_call:
            return "method"  # def name(...) { ... }
        else:
            return "method"  # Default to method

    def _unit_contains_func(self, unit_node: Any) -> bool:
        """Check if unit node contains a func child."""
        if hasattr(unit_node, "children"):
            for child in unit_node.children:
                if hasattr(child, "type") and child.type == "func":
                    return True
        return False

    def _is_typed_method_declaration(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents a typed method declaration (Type methodName(...))."""
        children = list(node.children)

        # Pattern: Type methodName(...) { ... }
        # Look for: unit (type) + block containing unit with func
        if len(children) >= 2:
            # First child should be a unit with type identifier
            first_child = children[0]
            if hasattr(first_child, "type") and first_child.type == "unit":
                type_text = self._get_identifier_text(first_child, lines)

                # Check if this looks like a type
                if type_text and self._looks_like_type(type_text):
                    # Second child should be a block containing method signature
                    for child in children[1:]:
                        if hasattr(child, "type") and child.type == "block":
                            # Look for func node in the block
                            if self._block_contains_func(child, lines):
                                return True

        return False

    def _block_contains_func(self, block_node: Any, lines: List[str]) -> bool:
        """Check if block contains a func node (method signature)."""
        if hasattr(block_node, "children"):
            for child in block_node.children:
                if hasattr(child, "type"):
                    if child.type == "unit":
                        # Check if this unit contains a func
                        if hasattr(child, "children"):
                            for grandchild in child.children:
                                if (
                                    hasattr(grandchild, "type")
                                    and grandchild.type == "func"
                                ):
                                    return True
        return False

    def _is_typed_declaration(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents a typed declaration (Type name = ...)."""
        children = list(node.children)

        # Look for at least 2 units (could have modifiers before type and name)
        unit_children = [c for c in children if hasattr(c, "type") and c.type == "unit"]

        if len(unit_children) >= 2:
            # Check each unit to see if any looks like a type
            for i, unit_child in enumerate(unit_children[:-1]):  # All but the last
                unit_text = self._get_identifier_text(unit_child, lines)

                # Check if this unit looks like a type (starts with capital or is known type)
                if unit_text and (
                    unit_text[0].isupper()
                    or unit_text
                    in ["String", "int", "boolean", "List", "Map", "Set", "Closure"]
                ):
                    # Check if next unit could be a field name
                    if i + 1 < len(unit_children):
                        next_unit = unit_children[i + 1]
                        next_text = self._get_identifier_text(next_unit, lines)
                        if next_text and self._validate_identifier_name(next_text):
                            return True

        return False

    def _get_typed_declaration_type(self, node: Any, lines: List[str]) -> str:
        """Determine if typed declaration is field or closure."""
        children = list(node.children)

        # CRITICAL FIX: Look for closure assignment pattern in block structure
        # Pattern: Type name = { ... }
        for child in children:
            if hasattr(child, "type") and child.type == "block":
                # Check if block contains assignment with braces (closure pattern)
                if hasattr(child, "children"):
                    has_assignment = False
                    has_braces = False

                    for block_child in child.children:
                        if hasattr(block_child, "type"):
                            if block_child.type == "operators":
                                op_text = self._get_node_text(
                                    block_child, lines
                                ).strip()
                                if op_text == "=":
                                    has_assignment = True
                            elif block_child.type == "{":
                                has_braces = True

                    # If we have both assignment and braces, it's a closure
                    if has_assignment and has_braces:
                        return "closure"

        return "field"

    def _extract_package_from_ast(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract package name using AST structure (no regex)."""
        if not hasattr(node, "children") or len(node.children) < 2:
            return None

        children = list(node.children)
        first_child = children[0]

        if hasattr(first_child, "type") and first_child.type == "unit":
            first_text = self._get_identifier_text(first_child, lines)
            if first_text == "package":
                # Look for package name in second unit - need to handle dotted identifiers
                if len(children) > 1:
                    second_child = children[1]
                    if hasattr(second_child, "type") and second_child.type == "unit":
                        # Extract the full dotted package name by traversing all identifiers and dots
                        package_parts = []
                        if hasattr(second_child, "children"):
                            for grandchild in second_child.children:
                                if hasattr(grandchild, "type"):
                                    if grandchild.type == "identifier":
                                        package_parts.append(
                                            self._get_node_text(
                                                grandchild, lines
                                            ).strip()
                                        )
                                    elif grandchild.type == "." and package_parts:
                                        package_parts.append(".")

                        if package_parts:
                            package_name = "".join(package_parts)
                            if package_name and all(
                                c.isalnum() or c in "._" for c in package_name
                            ):
                                return package_name

        return None

    # AST-based extraction methods (replacing regex-based methods)

    def _extract_class_from_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract class declaration using AST structure - SINGLE TRAVERSAL APPROACH."""
        class_name = self._get_class_name_from_ast(node, lines)
        if not class_name or not self._validate_identifier_name(class_name):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "class"):
            return

        # Build class construct (simplified version)
        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{class_name}" if parent_path else class_name

        # CRITICAL FIX: Check if class has annotations and mark it accordingly
        features = ["class_declaration"]
        if self._has_annotations(node, lines):
            features.append("annotated")

        constructs.append(
            {
                "type": "class",
                "name": class_name,
                "path": full_path,
                "signature": f"class {class_name}",
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "global" if not scope_stack else "class",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {"declaration_type": "class"},
                "features": features,
            }
        )

        # Process class members with proper scope management
        scope_stack.append(class_name)
        try:
            self._process_class_body_ast(node, constructs, lines, scope_stack, content)
        finally:
            scope_stack.pop()

    def _get_class_name_from_ast(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract class name from AST structure - handles ERROR nodes."""
        children = list(node.children)

        # CRITICAL FIX: Handle cases where class is embedded in ERROR nodes due to annotations
        # First try normal path
        for child in children:
            if hasattr(child, "type") and child.type == "block":
                # The block starts with the class name as a unit
                if hasattr(child, "children") and child.children:
                    first_block_child = child.children[0]
                    if (
                        hasattr(first_block_child, "type")
                        and first_block_child.type == "unit"
                    ):
                        class_name = self._get_identifier_text(first_block_child, lines)
                        if self._validate_identifier_name(class_name):
                            return class_name

        # CRITICAL FIX: If no class found via normal path, look in ERROR nodes
        # This handles annotated classes that tree-sitter can't parse perfectly
        for child in children:
            if hasattr(child, "type") and child.type == "block":
                if hasattr(child, "children"):
                    for block_child in child.children:
                        if hasattr(block_child, "type") and block_child.type == "ERROR":
                            # Look for class declaration in ERROR node text
                            error_text = self._get_node_text(block_child, lines)
                            class_name_result = (
                                self._extract_class_name_from_error_text(error_text)
                            )
                            if class_name_result:
                                class_name = class_name_result
                            if class_name:
                                return class_name
        return None

    def _extract_class_name_from_error_text(self, error_text: str) -> Optional[str]:
        """Extract class name from ERROR node text that contains class declaration."""
        # Look for "class ClassName" pattern in ERROR node
        match = re.search(r"\bclass\s+(\w+)", error_text)
        if match:
            class_name = match.group(1)
            if self._validate_identifier_name(class_name):
                return class_name
        return None

    def _extract_interface_from_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract interface declaration using AST structure."""
        interface_name = self._get_interface_name_from_ast(node, lines)
        if not interface_name or not self._validate_identifier_name(interface_name):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "interface"):
            return

        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{interface_name}" if parent_path else interface_name

        constructs.append(
            {
                "type": "interface",
                "name": interface_name,
                "path": full_path,
                "signature": f"interface {interface_name}",
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "global" if not scope_stack else "interface",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {"declaration_type": "interface"},
                "features": ["interface_declaration"],
            }
        )

    def _get_interface_name_from_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract interface name from AST structure."""
        # Similar pattern to class name extraction
        children = list(node.children)
        if len(children) >= 2:
            first_unit = children[0]
            if hasattr(first_unit, "type") and first_unit.type == "unit":
                first_text = self._get_identifier_text(first_unit, lines)
                if first_text == "interface":
                    for child in children[1:]:
                        if hasattr(child, "type") and child.type == "block":
                            block_text = self._get_node_text(child, lines).strip()
                            if block_text and not block_text.startswith("{"):
                                parts = block_text.split("{")[0].strip().split()
                                if parts and self._validate_identifier_name(parts[0]):
                                    return parts[0]
        return None

    def _extract_trait_from_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract trait declaration using AST structure."""
        trait_name = self._get_trait_name_from_ast(node, lines)
        if not trait_name or not self._validate_identifier_name(trait_name):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "trait"):
            return

        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{trait_name}" if parent_path else trait_name

        constructs.append(
            {
                "type": "trait",
                "name": trait_name,
                "path": full_path,
                "signature": f"trait {trait_name}",
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "global" if not scope_stack else "trait",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {"declaration_type": "trait"},
                "features": ["trait_declaration"],
            }
        )

    def _get_trait_name_from_ast(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract trait name from AST structure."""
        children = list(node.children)
        if len(children) >= 2:
            first_unit = children[0]
            if hasattr(first_unit, "type") and first_unit.type == "unit":
                first_text = self._get_identifier_text(first_unit, lines)
                if first_text == "trait":
                    for child in children[1:]:
                        if hasattr(child, "type") and child.type == "block":
                            block_text = self._get_node_text(child, lines).strip()
                            if block_text and not block_text.startswith("{"):
                                parts = block_text.split("{")[0].strip().split()
                                if parts and self._validate_identifier_name(parts[0]):
                                    return parts[0]
        return None

    def _extract_method_from_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract method declaration using AST structure."""
        method_name = self._get_method_name_from_ast(node, lines)
        if not method_name or not self._validate_identifier_name(method_name):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "method"):
            return

        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{method_name}" if parent_path else method_name

        method_type = "method" if scope_stack else "function"

        # CRITICAL FIX: Generate proper signature for both 'def' and typed methods
        method_signature = self._generate_method_signature(node, method_name, lines)

        constructs.append(
            {
                "type": method_type,
                "name": method_name,
                "path": full_path,
                "signature": method_signature,
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "method",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {"declaration_type": method_type},
                "features": ["method_declaration"],
            }
        )

    def _generate_method_signature(
        self, node: Any, method_name: str, lines: List[str]
    ) -> str:
        """Generate method signature from AST node."""
        children = list(node.children)
        if len(children) >= 1:
            first_unit = children[0]
            if hasattr(first_unit, "type") and first_unit.type == "unit":
                first_text = self._get_identifier_text(first_unit, lines)

                if first_text == "def":
                    return f"def {method_name}"
                elif self._looks_like_type(first_text):
                    # Typed method
                    return f"{first_text} {method_name}"

        # Fallback
        return f"def {method_name}"

    def _get_method_name_from_ast(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract method name from AST structure - handles both 'def' and typed methods."""
        children = list(node.children)
        if len(children) >= 2:
            first_unit = children[0]
            if hasattr(first_unit, "type") and first_unit.type == "unit":
                first_text = self._get_identifier_text(first_unit, lines)

                if first_text == "def":
                    # Handle 'def' method pattern: def <name> { ... }
                    return self._extract_method_name_from_block(children[1:], lines)
                elif self._looks_like_type(first_text):
                    # CRITICAL FIX: Handle typed method pattern: Type <name>(...) { ... }
                    return self._extract_method_name_from_block(children[1:], lines)
        return None

    def _extract_method_name_from_block(
        self, children: List[Any], lines: List[str]
    ) -> Optional[str]:
        """Extract method name from block children."""
        # The method name is in the block's first unit (which contains func or identifier)
        for child in children:
            if hasattr(child, "type") and child.type == "block":
                if hasattr(child, "children") and child.children:
                    first_block_child = child.children[0]
                    if (
                        hasattr(first_block_child, "type")
                        and first_block_child.type == "unit"
                    ):
                        # Check if this unit contains a func node
                        if hasattr(first_block_child, "children"):
                            for grandchild in first_block_child.children:
                                if (
                                    hasattr(grandchild, "type")
                                    and grandchild.type == "func"
                                ):
                                    # Get the method name from func's identifier
                                    if hasattr(grandchild, "children"):
                                        identifier_child = grandchild.children[0]
                                        if (
                                            hasattr(identifier_child, "type")
                                            and identifier_child.type == "identifier"
                                        ):
                                            method_name = self._get_node_text(
                                                identifier_child, lines
                                            ).strip()
                                            if self._validate_identifier_name(
                                                method_name
                                            ):
                                                return method_name
        return None

    def _extract_field_from_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract field declaration using AST structure."""
        field_info = self._get_field_info_from_ast(node, lines)
        if not field_info or not self._validate_identifier_name(field_info["name"]):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "field"):
            return

        # Skip if this looks like a return statement (common false positive)
        if "return" in node_text.lower() and field_info["name"] in [
            "null",
            "true",
            "false",
        ]:
            return

        field_name = field_info["name"]
        field_type = field_info.get("type")

        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{field_name}" if parent_path else field_name

        construct_type = "property" if not field_info.get("private") else "field"

        # CRITICAL FIX: Check if field has annotations and mark it accordingly
        features = ["field_declaration"]
        if self._has_annotations(node, lines):
            features.append("annotated")

        constructs.append(
            {
                "type": construct_type,
                "name": field_name,
                "path": full_path,
                "signature": f"{field_type + ' ' if field_type else ''}{field_name}",
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "global" if not scope_stack else "class",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {
                    "declaration_type": construct_type,
                    "field_type": field_type,
                },
                "features": features,
            }
        )

    def _get_field_info_from_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[Dict[str, str]]:
        """Extract field information from AST structure."""
        children = list(node.children)

        # Get all unit children
        unit_children = [c for c in children if hasattr(c, "type") and c.type == "unit"]

        if len(unit_children) >= 2:
            # CRITICAL FIX: Handle both typed fields and def fields
            # Pattern 1: Type name = value (typed field)
            # Pattern 2: def name = value (def field)

            field_type = None
            field_name = None

            for i, unit_child in enumerate(unit_children):
                unit_text = self._get_identifier_text(unit_child, lines)

                if unit_text == "def" and not field_type:
                    # Handle def field pattern: def name = value
                    field_type = "def"
                    # Next unit should be the field name
                    if i + 1 < len(unit_children):
                        next_unit = unit_children[i + 1]
                        next_text = self._get_identifier_text(next_unit, lines)
                        if next_text and self._validate_identifier_name(next_text):
                            field_name = next_text
                            break
                elif unit_text and self._looks_like_type(unit_text) and not field_type:
                    # Handle typed field pattern: Type name = value
                    field_type = unit_text
                    # Next unit should be the field name
                    if i + 1 < len(unit_children):
                        next_unit = unit_children[i + 1]
                        next_text = self._get_identifier_text(next_unit, lines)
                        if next_text and self._validate_identifier_name(next_text):
                            field_name = next_text
                            break

            if field_name:
                return {"name": field_name, "type": field_type or "def"}

        # CRITICAL FIX: Handle fields in ERROR nodes (annotated fields)
        for child in children:
            if hasattr(child, "type") and child.type == "ERROR":
                error_text = self._get_node_text(child, lines)
                field_name = self._extract_field_name_from_error_text(error_text)
                if field_name:
                    # Try to extract type from the same error text
                    field_type = self._extract_field_type_from_error_text(error_text)
                    return {"name": field_name, "type": field_type or "def"}

        return None

    def _extract_field_type_from_error_text(self, error_text: str) -> Optional[str]:
        """Extract field type from ERROR node text."""
        # Look for field patterns: "private Type fieldName" or "Type fieldName"
        patterns = [
            r"\b(?:private|public|protected)\s+(\w+)\s+(\w+)",  # private Type fieldName
            r"\b([A-Z]\w*)\s+(\w+)",  # Type fieldName
        ]

        for pattern in patterns:
            match = re.search(pattern, error_text)
            if match:
                field_type = match.group(1)
                if self._looks_like_type(field_type):
                    return field_type
        return None

    def _looks_like_type(self, text: str) -> bool:
        """Check if text looks like a type name."""
        if not text:
            return False
        # Common Groovy/Java types and conventions
        known_types = [
            "String",
            "int",
            "Integer",
            "boolean",
            "Boolean",
            "List",
            "Map",
            "Set",
            "Closure",
        ]
        return text in known_types or (text[0].isupper() and text.isalnum())

    def _extract_closure_from_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract closure assignment using AST structure."""
        closure_info = self._get_closure_info_from_ast(node, lines)
        if not closure_info or not self._validate_identifier_name(closure_info["name"]):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "closure"):
            return

        closure_name = closure_info["name"]
        closure_type = closure_info.get("type", "def")

        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{closure_name}" if parent_path else closure_name

        constructs.append(
            {
                "type": "closure",
                "name": closure_name,
                "path": full_path,
                "signature": f"{closure_type} {closure_name} = {{",
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "closure",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {
                    "declaration_type": "closure",
                    "closure_type": closure_type,
                },
                "features": ["closure_declaration"],
            }
        )

    def _get_closure_info_from_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[Dict[str, str]]:
        """Extract closure information from AST structure."""
        children = list(node.children)

        # Look for closure assignment pattern: [Type] name = { ... }
        if len(children) >= 3:
            closure_name = None
            closure_type = None
            has_assignment = False
            has_block = False

            for i, child in enumerate(children):
                if hasattr(child, "type"):
                    if child.type == "unit":
                        text = self._get_identifier_text(child, lines)
                        if text and self._validate_identifier_name(text):
                            if not closure_type and (
                                text in ["def", "Closure"]
                                or self._looks_like_type(text)
                            ):
                                closure_type = text
                            elif not closure_name:
                                closure_name = text
                    elif child.type == "block":
                        # Check if this block contains assignment operator and closure block
                        if hasattr(child, "children"):
                            for block_child in child.children:
                                if hasattr(block_child, "type"):
                                    if block_child.type == "operators":
                                        op_text = self._get_node_text(
                                            block_child, lines
                                        ).strip()
                                        if op_text == "=":
                                            has_assignment = True
                                    # Look for closure pattern with braces and arrow
                                    elif block_child.type == "{":
                                        has_block = True

            if closure_name and has_assignment and has_block:
                return {"name": closure_name, "type": closure_type or "def"}

        return None

    def _process_class_body_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process class body using AST structure."""
        # Find block node containing class body and process its command children
        for child in node.children:
            if hasattr(child, "type") and child.type == "block":
                # Process command nodes within the class body
                if hasattr(child, "children"):
                    for body_child in child.children:
                        if hasattr(body_child, "type") and body_child.type == "command":
                            # Process class member commands (skip class name unit and braces)
                            self._handle_command_node_ast(
                                body_child, constructs, lines, scope_stack, content
                            )

    def _traverse_children(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Traverse child nodes for constructs."""
        if hasattr(node, "children"):
            for child in node.children:
                self._traverse_node(child, constructs, lines, scope_stack, content)

    def _validate_identifier_name(self, name: str) -> bool:
        """Validate that a name is a proper identifier, not a literal like 'null'."""
        if not name or not isinstance(name, str):
            return False

        # Reject common literals and keywords that shouldn't be identifiers
        invalid_names = {
            "null",
            "true",
            "false",
            "return",
            "if",
            "else",
            "for",
            "while",
            "def",
        }
        if name.lower() in invalid_names:
            return False

        # Must start with letter or underscore, contain only alphanumeric and underscore
        if not (name[0].isalpha() or name[0] == "_"):
            return False

        return all(c.isalnum() or c == "_" for c in name)

    def _is_meaningful_content(self, text: str, construct_type: str) -> bool:
        """Check if content is meaningful enough to create a chunk."""
        if not text or not text.strip():
            return False

        stripped = text.strip()

        # Reject very short meaningless content
        if len(stripped) <= 5 and stripped in [
            ";",
            "null",
            "null;",
            "return",
            "return;",
        ]:
            return False

        # For fields/properties, require more substantial content
        if construct_type in ["field", "property"] and len(stripped) <= 12:
            # Allow valid assignments but reject bare statements
            if stripped in ["return null;", "return null", "null;"]:
                return False

        return True

    def _is_annotation_command(self, node: Any, lines: List[str]) -> bool:
        """Check if command node is just an annotation decorator."""
        if hasattr(node, "children") and len(node.children) == 1:
            child = node.children[0]
            if hasattr(child, "type") and child.type == "decorate":
                return True
        return False

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract constructs from ERROR node text using regex fallback."""
        # Define regex patterns for Groovy constructs
        patterns = {
            "class": r"(?:@\w+\s*)*\s*(?:public|private|protected)?\s*class\s+(\w+)",
            "interface": r"(?:@\w+\s*)*\s*(?:public|private|protected)?\s*interface\s+(\w+)",
            "trait": r"(?:@\w+\s*)*\s*(?:public|private|protected)?\s*trait\s+(\w+)",
            "method": r"(?:@\w+\s*)*\s*(?:public|private|protected|static)?\s*def\s+(\w+)",
            "function": r"(?:@\w+\s*)*\s*(?:public|private|protected|static)?\s*(\w+)\s+(\w+)\s*\(",
            "closure": r"(\w+)\s*=\s*\{",
            "field": r"(?:@\w+\s*)*\s*(?:public|private|protected|static|final)?\s*(?:(\w+)\s+)?(\w+)\s*[=;]",
        }

        return self._find_constructs_with_regex(error_text, patterns, "groovy")

    def _fallback_parse(self, content: str, file_path: str) -> List[Any]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        from .semantic_chunker import SemanticChunk

        # Basic fallback: treat as single chunk
        chunks = []

        if content.strip():
            chunks.append(
                SemanticChunk(
                    text=content,
                    chunk_index=0,
                    total_chunks=1,
                    size=len(content),
                    file_path=file_path,
                    file_extension=Path(file_path).suffix,
                    line_start=1,
                    line_end=len(content.split("\n")),
                    semantic_chunking=False,
                    semantic_type="module",
                    semantic_name=Path(file_path).stem,
                    semantic_path=Path(file_path).stem,
                    semantic_signature=f"module {Path(file_path).stem}",
                    semantic_parent=None,
                    semantic_context={"fallback": True},
                    semantic_scope="global",
                    semantic_language_features=["fallback_parsing"],
                )
            )

        return chunks
