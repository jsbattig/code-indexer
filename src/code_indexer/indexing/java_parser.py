"""
Java semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class JavaSemanticParser(BaseTreeSitterParser):
    """Semantic parser for Java files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "java")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (package, imports)."""
        # Find package declaration
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "package_declaration":
                    package_name = self._extract_package_name(child, lines)
                    if package_name:
                        scope_stack.append(package_name)
                        constructs.append(
                            {
                                "type": "package",
                                "name": package_name,
                                "path": package_name,
                                "signature": f"package {package_name};",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "package"},
                                "features": ["package_declaration"],
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
        """Handle Java-specific AST node types."""
        if node_type == "class_declaration":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "interface_declaration":
            self._handle_interface_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "method_declaration":
            self._handle_method_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "constructor_declaration":
            self._handle_constructor_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "field_declaration":
            self._handle_field_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "enum_declaration":
            self._handle_enum_declaration(node, constructs, lines, scope_stack, content)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        # Classes and interfaces handle their own members
        return node_type in [
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Java constructs from ERROR node text using regex fallback."""
        constructs = []

        # Java-specific regex patterns
        patterns = {
            "class": r"^\s*(?:(?:public|private|protected|abstract|final|static)\s+)*class\s+(\w+)",
            "interface": r"^\s*(?:(?:public|private|protected)\s+)*interface\s+(\w+)",
            "enum": r"^\s*(?:(?:public|private|protected)\s+)*enum\s+(\w+)",
            "method": r"^\s*(?:(?:public|private|protected|static|final|abstract)\s+)*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?:throws[^{]*)?{",
            "constructor": r"^\s*(?:(?:public|private|protected)\s+)*(\w+)\s*\([^)]*\)\s*(?:throws[^{]*)?{",
            "field": r"^\s*(?:(?:public|private|protected|static|final)\s+)*\w+(?:\[\])?\s+(\w+)\s*[=;]",
        }

        lines = error_text.split("\n")

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line, re.MULTILINE)
                if match:
                    name = match.group(1)

                    # Find the end of this construct
                    end_line = self._find_construct_end(lines, line_idx, construct_type)

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
                                "class"
                                if construct_type in ["method", "constructor", "field"]
                                else "global"
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
        # Fallback to basic text chunking
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

    # Helper methods

    def _extract_package_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract package name from package declaration node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "scoped_identifier":
                return self._get_node_text(child, lines)
        return None

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

            # Extract full signature from the node text
            node_text = self._get_node_text(node, lines)
            signature = self._extract_class_signature(node_text, class_name)
            modifiers = self._extract_modifiers_from_signature(signature)

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
                    "text": node_text,
                    "context": {"declaration_type": "class"},
                    "features": ["class_declaration"] + modifiers,
                }
            )

            # Process class members with proper scope
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

            # Extract full signature from the node text instead of constructing it
            node_text = self._get_node_text(node, lines)
            signature = self._extract_interface_signature(node_text, interface_name)
            modifiers = self._extract_modifiers_from_signature(signature)

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
                    "text": node_text,
                    "context": {"declaration_type": "interface"},
                    "features": ["interface_declaration"] + modifiers,
                }
            )

            # Process interface members
            scope_stack.append(interface_name)
            self._process_class_members(node, constructs, lines, scope_stack, content)
            scope_stack.pop()

    def _handle_method_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle method declaration."""
        method_name = self._get_java_method_name(node, lines)
        if method_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{method_name}" if parent_path else method_name

            # Extract full signature from the node text
            node_text = self._get_node_text(node, lines)
            signature = self._extract_method_signature(node_text, method_name)
            modifiers = self._extract_modifiers_from_signature(signature)

            # Extract parameters and return type for context
            params = self._extract_parameters(node, lines)
            return_type = self._extract_return_type(node, lines)

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
                    "text": node_text,
                    "context": {
                        "declaration_type": "method",
                        "parameters": params,
                        "return_type": return_type,
                    },
                    "features": ["method_declaration"] + modifiers,
                }
            )

    def _handle_constructor_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle constructor declaration."""
        constructor_name = self._get_identifier_from_node(node, lines)
        if constructor_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{constructor_name}" if parent_path else constructor_name
            )

            # Extract full signature from the node text
            node_text = self._get_node_text(node, lines)
            signature = self._extract_constructor_signature(node_text, constructor_name)
            modifiers = self._extract_modifiers_from_signature(signature)

            # Extract parameters for context
            params = self._extract_parameters(node, lines)

            constructs.append(
                {
                    "type": "constructor",  # Comprehensive tests expect constructor type
                    "name": constructor_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": node_text,
                    "context": {
                        "declaration_type": "constructor",
                        "parameters": params,
                    },
                    "features": ["constructor_declaration"] + modifiers,
                }
            )

    def _handle_field_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle field declaration."""
        field_name = self._get_identifier_from_node(node, lines)
        if field_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{field_name}" if parent_path else field_name

            constructs.append(
                {
                    "type": "field",
                    "name": field_name,
                    "path": full_path,
                    "signature": f"field {field_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "field",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "field"},
                    "features": ["field_declaration"],
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
                if child.type in ["class_body", "interface_body"]:
                    # Process all declarations in the class/interface body
                    for member in child.children:
                        self._traverse_node(
                            member, constructs, lines, scope_stack, content
                        )

    def _extract_return_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract return type from method declaration."""
        for child in node.children:
            if hasattr(child, "type") and child.type in [
                "type_identifier",
                "generic_type",
                "array_type",
            ]:
                return self._get_node_text(child, lines)
        return None

    def _find_construct_end(
        self, lines: List[str], start_line: int, construct_type: str
    ) -> int:
        """Find the end line of a construct starting from start_line."""
        if construct_type in ["class", "interface", "enum", "method", "constructor"]:
            # Find matching braces
            brace_count = 0
            for i in range(start_line, len(lines)):
                line = lines[i]
                brace_count += line.count("{") - line.count("}")
                if brace_count == 0 and "{" in line:
                    return i
        elif construct_type == "field":
            # Field ends at semicolon
            for i in range(start_line, min(start_line + 5, len(lines))):
                if ";" in lines[i]:
                    return i

        return min(start_line + 10, len(lines) - 1)  # Default fallback

    def _extract_class_signature(self, node_text: str, class_name: str) -> str:
        """Extract the class signature from node text."""
        # Get the class declaration line
        lines = node_text.split("\n")
        for line in lines:
            if "class" in line and class_name in line:
                # Extract everything up to the opening brace or end of line
                signature = line.split("{")[0].strip()
                return signature
        return f"class {class_name}"

    def _extract_method_signature(self, node_text: str, method_name: str) -> str:
        """Extract the method signature from node text."""
        lines = node_text.split("\n")
        for line in lines:
            if method_name in line and "(" in line:
                # Extract everything up to the opening brace
                signature = line.split("{")[0].strip()
                return signature
        return f"{method_name}()"

    def _extract_constructor_signature(
        self, node_text: str, constructor_name: str
    ) -> str:
        """Extract the constructor signature from node text."""
        lines = node_text.split("\n")
        for line in lines:
            if constructor_name in line and "(" in line:
                # Extract everything up to the opening brace
                signature = line.split("{")[0].strip()
                return signature
        return f"{constructor_name}()"

    def _extract_interface_signature(self, node_text: str, interface_name: str) -> str:
        """Extract the interface signature from node text."""
        # Get the interface declaration line
        lines = node_text.split("\n")
        for line in lines:
            if "interface" in line and interface_name in line:
                # Extract everything up to the opening brace or end of line
                signature = line.split("{")[0].strip()
                return signature
        return f"interface {interface_name}"

    def _get_java_method_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract method name from Java method declaration node.
        Java method declaration structure: modifiers + return_type + identifier + parameters
        We need to find the identifier that comes after the return type.
        """
        identifiers = []
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                identifier_text = self._get_node_text(child, lines)
                identifiers.append(identifier_text)

        # For methods, the method name is typically the last identifier
        # (after modifiers and return type)
        if identifiers:
            return identifiers[-1]
        return None

    def _extract_modifiers_from_signature(self, signature: str) -> List[str]:
        """Extract Java modifiers from signature."""
        java_modifiers = [
            "public",
            "private",
            "protected",
            "static",
            "final",
            "abstract",
            "synchronized",
            "native",
            "strictfp",
            "transient",
            "volatile",
        ]
        modifiers = []
        words = signature.split()
        for word in words:
            if word in java_modifiers:
                modifiers.append(word)
        return modifiers
