"""
C++ semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Handles C++-specific constructs including:
- Classes, structs (with access specifiers)
- Namespaces
- Templates and template specializations
- Methods, constructors, destructors
- Inheritance
- Operator overloading
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class CppSemanticParser(BaseTreeSitterParser):
    """Semantic parser for C++ files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "cpp")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (includes, namespace declarations, etc.)."""
        # Find preprocessor directives and namespace declarations
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "preproc_include":
                    self._extract_include(child, constructs, lines)
                elif child.type == "preproc_def":
                    self._extract_define(child, constructs, lines)
                elif child.type == "namespace_definition":
                    self._extract_namespace(child, constructs, lines, scope_stack)
                elif child.type == "using_declaration":
                    self._extract_using_declaration(child, constructs, lines)

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C++-specific AST node types."""
        if node_type == "class_specifier":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "struct_specifier":
            self._handle_struct_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "enum_specifier":
            self._handle_enum_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "function_definition":
            self._handle_function_definition(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "template_declaration":
            self._handle_template_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declaration":
            self._handle_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "namespace_definition":
            self._handle_namespace_definition(
                node, constructs, lines, scope_stack, content
            )

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        # These node types handle their own members
        return node_type in [
            "class_specifier",
            "struct_specifier",
            "enum_specifier",
            "function_definition",
            "namespace_definition",
            "template_declaration",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract C++ constructs from ERROR node text using regex fallback."""
        constructs = []
        lines = error_text.split("\n")
        current_parent = ".".join(scope_stack) if scope_stack else None

        # C++ namespace pattern
        namespace_pattern = r"^\s*namespace\s+([A-Za-z_][A-Za-z0-9_]*)\s*[{;]"

        # C++ class pattern with optional template and inheritance
        class_pattern = (
            r"^\s*(?:template\s*<[^>]*>\s*)?class\s+([A-Za-z_][A-Za-z0-9_]*)"
        )

        # C++ struct pattern
        struct_pattern = (
            r"^\s*(?:template\s*<[^>]*>\s*)?struct\s+([A-Za-z_][A-Za-z0-9_]*)"
        )

        # C++ enum class pattern
        enum_class_pattern = r"^\s*enum\s+class\s+([A-Za-z_][A-Za-z0-9_]*)"

        # C++ enum pattern
        enum_pattern = r"^\s*enum\s+([A-Za-z_][A-Za-z0-9_]*)\s*[{;]"

        # C++ method/function pattern (including constructors, destructors, operators)
        method_pattern = r"^\s*(?:virtual\s+|static\s+|inline\s+|explicit\s+)*(?:~?[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>]*>)?(?:\s*\*)*\s+)?([A-Za-z_~][A-Za-z0-9_]*|operator\s*[^\s(]+)\s*\("

        # C++ template pattern
        template_pattern = r"^\s*template\s*<([^>]*)>\s*(?:class|struct|typename)\s+([A-Za-z_][A-Za-z0-9_]*)"

        # C++ using pattern
        using_pattern = r"^\s*using\s+([A-Za-z_][A-Za-z0-9_:]*)\s*="

        # C++ typedef pattern
        typedef_pattern = r"^\s*typedef\s+.*?\s+([A-Za-z_][A-Za-z0-9_]*)\s*[;,]"

        # C++ variable pattern
        variable_pattern = r"^\s*(?:static\s+|extern\s+|const\s+|mutable\s+)*([A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>]*>)?(?:\s*\*)*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[=;,]"

        # Preprocessor patterns
        include_pattern = r"^\s*#\s*include\s*[<\"](.*?)[>\"]"
        define_pattern = r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)"

        patterns = [
            (namespace_pattern, "namespace"),
            (class_pattern, "class"),
            (struct_pattern, "struct"),
            (enum_class_pattern, "enum_class"),
            (enum_pattern, "enum"),
            (method_pattern, "method"),
            (template_pattern, "template"),
            (using_pattern, "using"),
            (typedef_pattern, "typedef"),
            (variable_pattern, "variable"),
            (include_pattern, "include"),
            (define_pattern, "define"),
        ]

        for i, line in enumerate(lines):
            line_num = start_line + i
            for pattern, construct_type in patterns:
                match = re.search(pattern, line)
                if match:
                    if construct_type == "template":
                        name = match.group(2)
                        template_params = match.group(1).strip()
                        signature = f"template<{template_params}> {line.strip()}"
                    elif construct_type == "variable":
                        name = match.group(2)
                        var_type = match.group(1).strip()
                        signature = f"{var_type} {name}"
                    elif construct_type in ["include", "define"]:
                        name = match.group(1)
                        signature = line.strip()
                    else:
                        name = match.group(1)
                        signature = line.strip()

                    full_path = f"{current_parent}.{name}" if current_parent else name

                    # Special handling for operators
                    if construct_type == "method" and "operator" in name:
                        construct_type = "operator"

                    # Special handling for destructors
                    if construct_type == "method" and name.startswith("~"):
                        construct_type = "destructor"

                    constructs.append(
                        {
                            "type": construct_type,
                            "name": name,
                            "path": full_path,
                            "signature": signature,
                            "parent": current_parent,
                            "scope": "global" if not current_parent else "class",
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

    def _extract_namespace(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract namespace declaration."""
        namespace_name = self._extract_namespace_name(node, lines)
        if namespace_name:
            constructs.append(
                {
                    "type": "namespace",
                    "name": namespace_name,
                    "path": namespace_name,
                    "signature": f"namespace {namespace_name}",
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "namespace"},
                    "features": ["namespace_declaration"],
                }
            )
            scope_stack.append(namespace_name)

    def _extract_using_declaration(
        self, node: Any, constructs: List[Dict[str, Any]], lines: List[str]
    ):
        """Extract using declaration."""
        using_text = self._get_node_text(node, lines)
        match = re.search(r"using\s+([A-Za-z_][A-Za-z0-9_:]*)", using_text)
        if match:
            using_name = match.group(1)
            constructs.append(
                {
                    "type": "using",
                    "name": using_name,
                    "path": using_name,
                    "signature": using_text.strip(),
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": using_text,
                    "context": {"declaration_type": "using"},
                    "features": ["using_declaration"],
                }
            )

    def _handle_namespace_definition(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C++ namespace definition."""
        namespace_name = self._extract_namespace_name(node, lines)
        if not namespace_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{namespace_name}" if current_scope else namespace_name
        )

        constructs.append(
            {
                "type": "namespace",
                "name": namespace_name,
                "path": full_path,
                "signature": f"namespace {namespace_name}",
                "parent": current_scope if current_scope else None,
                "scope": "namespace" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "namespace"},
                "features": ["namespace_declaration"],
            }
        )

        # Process namespace members
        scope_stack.append(namespace_name)
        self._process_namespace_members(node, constructs, lines, scope_stack, content)
        scope_stack.pop()

    def _handle_class_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C++ class declaration."""
        class_name = self._extract_class_name(node, lines)
        if not class_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{class_name}" if current_scope else class_name

        # Extract inheritance information
        inheritance_info = self._extract_inheritance_info(node, lines)

        # Get class signature
        signature = self._extract_class_signature(node, lines)

        features = ["class_declaration"]
        if inheritance_info.get("base_classes"):
            features.append("inheritance")

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
                "context": {
                    "declaration_type": "class",
                    "inheritance": inheritance_info,
                },
                "features": features,
            }
        )

        # Process class members
        scope_stack.append(class_name)
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
        """Handle C++ struct declaration."""
        struct_name = self._extract_struct_name(node, lines)
        if not struct_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{struct_name}" if current_scope else struct_name

        # Extract inheritance information
        inheritance_info = self._extract_inheritance_info(node, lines)

        signature = self._extract_struct_signature(node, lines)

        features = ["struct_declaration"]
        if inheritance_info.get("base_classes"):
            features.append("inheritance")

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
                "context": {
                    "declaration_type": "struct",
                    "inheritance": inheritance_info,
                },
                "features": features,
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
        """Handle C++ enum declaration."""
        enum_name = self._extract_enum_name(node, lines)
        if not enum_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{enum_name}" if current_scope else enum_name

        # Check if it's an enum class
        node_text = self._get_node_text(node, lines)
        is_enum_class = "enum class" in node_text or "enum struct" in node_text

        signature = self._extract_enum_signature(node, lines)
        enum_type = "enum_class" if is_enum_class else "enum"

        constructs.append(
            {
                "type": enum_type,
                "name": enum_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "namespace" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": enum_type, "is_scoped": is_enum_class},
                "features": [f"{enum_type}_declaration"],
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
        """Handle C++ function definition."""
        function_name = self._extract_function_name(node, lines)
        if not function_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{function_name}" if current_scope else function_name
        )

        # Determine function type (function, method, constructor, destructor, operator)
        # Check if we're inside a class by examining the node's parent hierarchy
        is_in_class = self._is_function_in_class(node)
        function_type = self._determine_function_type(
            function_name, scope_stack, is_in_class
        )

        signature = self._extract_function_signature(node, lines)

        # Extract template information if present
        template_info = self._extract_template_info(node, lines)

        features = [f"{function_type}_definition"]
        if template_info:
            features.append("template")

        constructs.append(
            {
                "type": function_type,
                "name": function_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "class" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": function_type,
                    "template": template_info,
                },
                "features": features,
            }
        )

    def _handle_template_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle C++ template declaration."""
        # Extract template parameters
        template_params = self._extract_template_parameters(node, lines)

        # Find the templated construct
        templated_construct = self._extract_templated_construct(node, lines)

        if templated_construct:
            template_name = templated_construct.get("name", "unknown")
            current_scope = ".".join(scope_stack)
            full_path = (
                f"{current_scope}.{template_name}" if current_scope else template_name
            )

            signature = f"template<{template_params}> {templated_construct.get('signature', '')}"

            constructs.append(
                {
                    "type": f"template_{templated_construct.get('type', 'unknown')}",
                    "name": template_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": current_scope if current_scope else None,
                    "scope": "namespace" if scope_stack else "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "template",
                        "template_parameters": template_params,
                        "templated_type": templated_construct.get("type"),
                    },
                    "features": [
                        "template_declaration",
                        f"{templated_construct.get('type', 'unknown')}_template",
                    ],
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
        """Handle C++ variable and other declarations."""
        # Try to extract variable declarations from declaration nodes
        node_text = self._get_node_text(node, lines)

        # Skip function declarations (they have parentheses but no equals)
        if "(" in node_text and ")" in node_text and "=" not in node_text:
            return

        # Extract variable name and type
        var_match = re.search(
            r"(?:static\s+|extern\s+|const\s+|mutable\s+)*([A-Za-z_][A-Za-z0-9_]*(?:\s*<[^>]*>)?(?:\s*\*)*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[=;,]",
            node_text,
        )

        if var_match:
            var_type = var_match.group(1).strip()
            var_name = var_match.group(2)

            current_scope = ".".join(scope_stack)
            full_path = f"{current_scope}.{var_name}" if current_scope else var_name

            # Determine scope type
            scope_type = "global"
            if scope_stack:
                scope_type = (
                    "class"
                    if any(cls in scope_stack for cls in ["class", "struct"])
                    else "namespace"
                )

            constructs.append(
                {
                    "type": "variable",
                    "name": var_name,
                    "path": full_path,
                    "signature": f"{var_type} {var_name}",
                    "parent": current_scope if current_scope else None,
                    "scope": scope_type,
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

    def _process_namespace_members(
        self,
        namespace_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process members within a namespace."""
        # Find the declaration list
        for child in namespace_node.children:
            if hasattr(child, "type") and child.type == "declaration_list":
                for member_child in child.children:
                    self._traverse_node(
                        member_child, constructs, lines, scope_stack, content
                    )

    def _process_class_members(
        self,
        class_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process members within a class/struct."""
        # Find the field declaration list
        for child in class_node.children:
            if hasattr(child, "type") and child.type == "field_declaration_list":
                current_access = "private"  # Default for classes

                for member_child in child.children:
                    if hasattr(member_child, "type"):
                        if member_child.type == "access_specifier":
                            current_access = self._extract_access_specifier(
                                member_child, lines
                            )
                        else:
                            # Process member with access specifier context
                            self._process_class_member(
                                member_child,
                                constructs,
                                lines,
                                scope_stack,
                                content,
                                current_access,
                            )

    def _process_class_member(
        self,
        member_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
        access_specifier: str,
    ):
        """Process a single class member with access specifier context."""
        if not hasattr(member_node, "type"):
            return

        # Add access specifier to context and traverse
        original_traverse = self._traverse_node

        def enhanced_traverse(
            node, constructs_list, lines_list, scope_list, content_str
        ):
            # Add access specifier to any construct found
            original_len = len(constructs_list)
            original_traverse(
                node, constructs_list, lines_list, scope_list, content_str
            )

            # Add access specifier to newly added constructs
            for i in range(original_len, len(constructs_list)):
                if "context" not in constructs_list[i]:
                    constructs_list[i]["context"] = {}
                constructs_list[i]["context"]["access_specifier"] = access_specifier
                constructs_list[i]["features"] = constructs_list[i].get(
                    "features", []
                ) + [access_specifier]

        enhanced_traverse(member_node, constructs, lines, scope_stack, content)

    # Helper methods for extracting names and signatures

    def _extract_namespace_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract namespace name from namespace_definition node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "namespace_identifier":
                return self._get_node_text(child, lines).strip()
        return None

    def _extract_class_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract class name from class_specifier node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_identifier":
                return self._get_node_text(child, lines).strip()
        return None

    def _extract_struct_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract struct name from struct_specifier node."""
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
                    if hasattr(subchild, "type"):
                        if subchild.type == "identifier":
                            return self._get_node_text(subchild, lines).strip()
                        elif subchild.type == "destructor_name":
                            return self._get_node_text(subchild, lines).strip()
                        elif subchild.type == "operator_name":
                            return self._get_node_text(subchild, lines).strip()
        return None

    def _extract_inheritance_info(self, node: Any, lines: List[str]) -> Dict[str, Any]:
        """Extract inheritance information from class/struct node."""
        inheritance_info: Dict[str, Any] = {"base_classes": [], "access_specifiers": []}

        for child in node.children:
            if hasattr(child, "type") and child.type == "base_class_clause":
                base_class_text = self._get_node_text(child, lines)
                # Parse base classes
                base_classes = re.findall(
                    r"(?:public|private|protected)?\s*([A-Za-z_][A-Za-z0-9_:]*)",
                    base_class_text,
                )
                inheritance_info["base_classes"].extend(base_classes)

                # Parse access specifiers
                access_specs = re.findall(
                    r"(public|private|protected)", base_class_text
                )
                inheritance_info["access_specifiers"].extend(access_specs)

        return inheritance_info

    def _extract_template_info(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract template information if the function is templated."""
        # Check if there's a template_declaration parent
        current = node
        while hasattr(current, "parent") and current.parent:
            if (
                hasattr(current.parent, "type")
                and current.parent.type == "template_declaration"
            ):
                template_params = self._extract_template_parameters(
                    current.parent, lines
                )
                return template_params
            current = current.parent
        return None

    def _extract_template_parameters(self, template_node: Any, lines: List[str]) -> str:
        """Extract template parameters from template_declaration node."""
        for child in template_node.children:
            if hasattr(child, "type") and child.type == "template_parameter_list":
                return self._get_node_text(child, lines).strip()
        return ""

    def _extract_templated_construct(
        self, template_node: Any, lines: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Extract the construct that is being templated."""
        for child in template_node.children:
            if hasattr(child, "type"):
                if child.type == "class_specifier":
                    class_name = self._extract_class_name(child, lines)
                    return {
                        "name": class_name,
                        "type": "class",
                        "signature": f"class {class_name}",
                    }
                elif child.type == "struct_specifier":
                    struct_name = self._extract_struct_name(child, lines)
                    return {
                        "name": struct_name,
                        "type": "struct",
                        "signature": f"struct {struct_name}",
                    }
                elif child.type == "function_definition":
                    func_name = self._extract_function_name(child, lines)
                    return {
                        "name": func_name,
                        "type": "function",
                        "signature": f"function {func_name}",
                    }
        return None

    def _extract_access_specifier(self, node: Any, lines: List[str]) -> str:
        """Extract access specifier (public, private, protected)."""
        node_text = self._get_node_text(node, lines).strip()
        if "public" in node_text:
            return "public"
        elif "private" in node_text:
            return "private"
        elif "protected" in node_text:
            return "protected"
        return "private"  # Default

    def _determine_function_type(
        self, function_name: str, scope_stack: List[str], is_in_class: bool = False
    ) -> str:
        """Determine the type of function (function, method, constructor, destructor, operator)."""
        if function_name.startswith("~"):
            return "destructor"
        elif function_name.startswith("operator"):
            return "operator"
        elif scope_stack and function_name == scope_stack[-1]:
            return "constructor"
        elif is_in_class:
            return "method"
        else:
            return "function"

    def _is_function_in_class(self, function_node: Any) -> bool:
        """Check if a function definition is inside a class by examining parent nodes."""
        # Walk up the tree to see if we're inside a class_specifier
        current = function_node
        while hasattr(current, "parent") and current.parent:
            current = current.parent
            if hasattr(current, "type") and current.type in [
                "class_specifier",
                "struct_specifier",
            ]:
                return True
            # Stop if we hit a namespace or translation unit
            if hasattr(current, "type") and current.type in [
                "namespace_definition",
                "translation_unit",
            ]:
                return False
        return False

    def _extract_class_signature(self, node: Any, lines: List[str]) -> str:
        """Extract class signature including inheritance."""
        node_text = self._get_node_text(node, lines)
        first_line = node_text.split("\n")[0].strip()
        if "{" in first_line:
            first_line = first_line.split("{")[0].strip()
        return first_line

    def _extract_struct_signature(self, node: Any, lines: List[str]) -> str:
        """Extract struct signature including inheritance."""
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
