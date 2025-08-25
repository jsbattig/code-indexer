"""
Kotlin semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class KotlinSemanticParser(BaseTreeSitterParser):
    """Semantic parser for Kotlin files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "kotlin")

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
                if child.type == "package_header":
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
                elif child.type == "import_list":
                    for import_child in child.children:
                        if (
                            hasattr(import_child, "type")
                            and import_child.type == "import_header"
                        ):
                            self._handle_import_header(import_child, constructs, lines)

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Kotlin-specific AST node types."""
        if node_type == "class_declaration":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "object_declaration":
            self._handle_object_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "function_declaration":
            self._handle_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "property_declaration":
            self._handle_property_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "interface_declaration":
            self._handle_interface_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "type_alias":
            self._handle_type_alias(node, constructs, lines, scope_stack, content)

    def _handle_type_alias(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle type alias declaration."""
        alias_name = self._get_identifier_from_node(node, lines)
        if alias_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{alias_name}" if parent_path else alias_name

            node_text = self._get_node_text(node, lines)
            signature = node_text.split("\n")[0].strip()  # Get first line as signature

            constructs.append(
                {
                    "type": "typealias",
                    "name": alias_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": node_text,
                    "context": {"declaration_type": "typealias"},
                    "features": ["typealias_declaration"],
                }
            )

    def _is_kotlin_interface(self, node: Any, node_text: str) -> bool:
        """Check if a class_declaration node is actually an interface."""
        # Check node children for 'interface' keyword
        for child in node.children:
            if hasattr(child, "type") and child.type == "interface":
                return True
        # Fallback to text-based detection
        return node_text.strip().startswith("interface ")

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        return node_type in [
            "class_declaration",
            "object_declaration",
            "interface_declaration",
            "function_declaration",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Kotlin constructs from ERROR node text using regex fallback."""
        constructs = []

        # Kotlin-specific regex patterns
        patterns = {
            "class": r"^\s*(?:(?:public|private|protected|internal|abstract|final|open|sealed|data|inner|enum|annotation|inline|value)\s+)*class\s+(\w+)(?:<[^>]*>)?",
            "interface": r"^\s*(?:(?:public|private|protected|internal)\s+)*interface\s+(\w+)(?:<[^>]*>)?",
            "object": r"^\s*(?:(?:public|private|protected|internal)\s+)*object\s+(\w+)",
            "function": r"^\s*(?:(?:public|private|protected|internal|abstract|final|open|override|suspend|inline|infix|operator|tailrec)\s+)*fun\s+(?:<[^>]+>\s+)?(\w+)\s*\([^)]*\)",
            "property": r"^\s*(?:(?:public|private|protected|internal|open|override|const|lateinit)\s+)*(?:val|var)\s+(\w+)\s*:",
            "extension_function": r"^\s*(?:(?:public|private|protected|internal|inline|infix|operator)\s+)*fun\s+(?:<[^>]+>\s+)?([^.\s]+(?:<[^>]+>)?)\s*\.\s*(\w+)\s*\([^)]*\)",
        }

        lines = error_text.split("\n")

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    # Extract name based on construct type
                    receiver_type: Optional[str] = None
                    if construct_type == "extension_function":
                        receiver_type = str(match.group(1))
                        name = str(match.group(2))
                    else:
                        name = str(match.group(1))

                    # Find the end of this construct
                    end_line = self._find_kotlin_construct_end(
                        lines, line_idx, construct_type
                    )

                    # Build construct text
                    construct_lines = lines[line_idx : end_line + 1]
                    construct_text = "\n".join(construct_lines)

                    parent = scope_stack[-1] if scope_stack else None
                    full_path = f"{parent}.{name}" if parent else name

                    context_dict: Dict[str, Any] = {"extracted_from_error": True}

                    # Add extra context for extension functions
                    if (
                        construct_type == "extension_function"
                        and receiver_type is not None
                    ):
                        context_dict["receiver_type"] = receiver_type

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

    # Helper methods for Kotlin constructs

    def _extract_package_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract package name from package header."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                return self._get_node_text(child, lines)
        return None

    def _handle_import_header(
        self, node: Any, constructs: List[Dict[str, Any]], lines: List[str]
    ):
        """Handle import header."""
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

            modifiers = self._extract_kotlin_modifiers(node, lines)
            type_params = self._extract_kotlin_type_parameters(node, lines)
            supertype = self._extract_kotlin_supertype(node, lines)

            # Extract full signature from the node text
            node_text = self._get_node_text(node, lines)

            # Check if this is actually an interface
            is_interface = self._is_kotlin_interface(node, node_text)
            construct_type = "interface" if is_interface else "class"

            signature = self._extract_kotlin_class_signature(
                node_text, class_name, construct_type
            )

            constructs.append(
                {
                    "type": construct_type,
                    "name": class_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "class",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": node_text,
                    "context": {
                        "declaration_type": "class",
                        "modifiers": modifiers,
                        "type_parameters": type_params,
                        "supertype": supertype,
                    },
                    "features": ["class_declaration"],
                }
            )

            # Process class members
            scope_stack.append(class_name)
            self._process_class_members(node, constructs, lines, scope_stack, content)
            scope_stack.pop()

    def _handle_object_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle object declaration."""
        object_name = self._get_identifier_from_node(node, lines)
        if object_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{object_name}" if parent_path else object_name

            constructs.append(
                {
                    "type": "object",
                    "name": object_name,
                    "path": full_path,
                    "signature": f"object {object_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "object",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "object"},
                    "features": ["object_declaration"],
                }
            )

            # Process object members
            scope_stack.append(object_name)
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

            constructs.append(
                {
                    "type": "interface",
                    "name": interface_name,
                    "path": full_path,
                    "signature": f"interface {interface_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "interface",
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

            modifiers = self._extract_kotlin_modifiers(node, lines)
            params = self._extract_kotlin_parameters(node, lines)
            return_type = self._extract_kotlin_return_type(node, lines)
            type_params = self._extract_kotlin_type_parameters(node, lines)
            receiver = self._extract_kotlin_receiver(node, lines)

            signature = "fun "
            if type_params:
                signature += f"<{type_params}> "
            if receiver:
                signature += f"{receiver}."
            signature += function_name
            if params:
                signature += f"({params})"
            if return_type:
                signature += f": {return_type}"

            # Determine if this is an extension function, method, or function
            if receiver:
                construct_type = "extension_function"
            else:
                # Check if we're inside a class/object scope by looking at the immediate parent
                # If parent contains a dot, it's likely a package (com.example)
                # If parent is a simple name, it's likely a class/object
                current_parent = scope_stack[-1] if scope_stack else None
                if current_parent and "." not in current_parent:
                    # Simple name parent suggests class/object scope
                    construct_type = "method"
                else:
                    # No parent or package-like parent suggests top-level function
                    construct_type = "function"

            constructs.append(
                {
                    "type": construct_type,
                    "name": function_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": construct_type,
                        "modifiers": modifiers,
                        "parameters": params,
                        "return_type": return_type,
                        "type_parameters": type_params,
                        "receiver": receiver,
                    },
                    "features": ["function_declaration"],
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
        """Handle property declaration."""
        property_name = self._get_identifier_from_node(node, lines)
        if property_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{property_name}" if parent_path else property_name
            )

            modifiers = self._extract_kotlin_modifiers(node, lines)
            prop_type = self._extract_kotlin_property_type(node, lines)

            constructs.append(
                {
                    "type": "property",
                    "name": property_name,
                    "path": full_path,
                    "signature": f"property {property_name}: {prop_type}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "property",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "property",
                        "modifiers": modifiers,
                        "property_type": prop_type,
                    },
                    "features": ["property_declaration"],
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
        """Process members of a class/interface/object."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "class_body":
                    for member in child.children:
                        self._traverse_node(
                            member, constructs, lines, scope_stack, content
                        )

    # Kotlin-specific helper methods

    def _extract_kotlin_modifiers(self, node: Any, lines: List[str]) -> List[str]:
        """Extract modifiers from a Kotlin declaration."""
        modifiers = []
        for child in node.children:
            if hasattr(child, "type") and child.type == "modifiers":
                modifier_text = self._get_node_text(child, lines)
                modifiers.extend(modifier_text.split())
        return modifiers

    def _extract_kotlin_type_parameters(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract type parameters from declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_parameters":
                return self._get_node_text(child, lines)
        return None

    def _extract_kotlin_supertype(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract supertype from class declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "delegation_specifiers":
                return self._get_node_text(child, lines)
        return None

    def _extract_kotlin_parameters(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract parameters from function."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "function_value_parameters":
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

    def _extract_kotlin_return_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract return type from function."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type":
                return self._get_node_text(child, lines)
        return None

    def _extract_kotlin_receiver(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract receiver type from extension function."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "receiver_type":
                return self._get_node_text(child, lines)
        return None

    def _extract_kotlin_property_type(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract property type from property declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "type":
                return self._get_node_text(child, lines)
        return None

    def _find_kotlin_construct_end(
        self, lines: List[str], start_line: int, construct_type: str
    ) -> int:
        """Find the end line of a Kotlin construct."""
        if construct_type in ["class", "interface", "object", "function"]:
            # Find matching braces
            brace_count = 0
            for i in range(start_line, len(lines)):
                line = lines[i]
                brace_count += line.count("{") - line.count("}")
                if brace_count == 0 and "{" in line:
                    return i
        elif construct_type in ["property", "extension_function"]:
            # Single line or until we find a complete statement
            for i in range(start_line, min(start_line + 5, len(lines))):
                if lines[i].strip().endswith(";") or (
                    i > start_line and not lines[i].strip().endswith(",")
                ):
                    return i

        return min(start_line + 10, len(lines) - 1)

    def _extract_kotlin_class_signature(
        self, node_text: str, class_name: str, construct_type: str = "class"
    ) -> str:
        """Extract the Kotlin class/interface signature from node text."""
        # Get the class/interface declaration line
        lines = node_text.split("\n")
        keyword = "interface" if construct_type == "interface" else "class"

        for line in lines:
            if keyword in line and class_name in line:
                # Extract everything up to the opening brace or end of line
                signature = line.split("{")[0].strip()
                return signature
        return f"{keyword} {class_name}"

    def _get_identifier_from_node(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a Kotlin node."""
        for child in node.children:
            if hasattr(child, "type") and child.type in (
                "identifier",
                "simple_identifier",
                "type_identifier",
            ):
                return str(self._get_node_text(child, lines))
        return None
