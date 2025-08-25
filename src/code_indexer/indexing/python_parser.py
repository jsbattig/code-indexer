"""
Python semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from typing import List, Dict, Any

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class PythonSemanticParser(BaseTreeSitterParser):
    """Semantic parser for Python files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "python")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (imports, module docstrings)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if (
                    child.type == "import_statement"
                    or child.type == "import_from_statement"
                ):
                    import_text = self._get_node_text(child, lines)
                    constructs.append(
                        {
                            "type": "import",
                            "name": (
                                import_text.split()[-1] if import_text else "unknown"
                            ),
                            "path": import_text,
                            "signature": import_text,
                            "parent": None,
                            "scope": "global",
                            "line_start": child.start_point[0] + 1,
                            "line_end": child.end_point[0] + 1,
                            "text": import_text,
                            "context": {"declaration_type": "import"},
                            "features": ["import_statement"],
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
        """Handle Python-specific AST node types."""
        if node_type == "class_definition":
            self._handle_class_definition(node, constructs, lines, scope_stack, content)
        elif node_type == "function_definition":
            self._handle_function_definition(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "decorated_definition":
            self._handle_decorated_definition(
                node, constructs, lines, scope_stack, content
            )

    def _handle_class_definition(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Python class definition."""
        class_name = self._get_identifier_from_node(node, lines)
        if class_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{class_name}" if parent_path else class_name

            # Extract class signature
            signature = f"class {class_name}"
            for child in node.children:
                if hasattr(child, "type") and child.type == "argument_list":
                    args = self._get_node_text(child, lines)
                    signature += args
                    break

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
                        "has_inheritance": any(
                            child.type == "argument_list"
                            for child in node.children
                            if hasattr(child, "type")
                        ),
                    },
                    "features": ["class_definition"],
                }
            )

            # For Python, we use class-level chunking - methods are part of the class chunk
            # Do not process individual methods as separate constructs

    def _handle_function_definition(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Python function definition."""
        function_name = self._get_identifier_from_node(node, lines)
        if function_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{function_name}" if parent_path else function_name
            )

            # Extract parameters for context
            parameters = self._extract_parameters(node, lines)

            # Extract full signature from the node text to detect async
            node_text = self._get_node_text(node, lines)
            is_async = self._detect_async_function(node_text)

            # Build signature
            signature = ""
            if is_async:
                signature = "async "
            signature += f"def {function_name}"
            if parameters:
                signature += parameters
            else:
                signature += "()"

            # Check for return type annotation
            for child in node.children:
                if hasattr(child, "type") and child.type == "type":
                    return_type = self._get_node_text(child, lines)
                    signature += f" -> {return_type}"
                    break

            signature += ":"

            # Detect features
            features = ["function_definition"]
            if is_async:
                features.append("async")

            constructs.append(
                {
                    "type": "function",
                    "name": function_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "class" if scope_stack else "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": node_text,
                    "context": {
                        "declaration_type": "function",
                        "parameters": parameters or "()",
                        "is_method": bool(scope_stack),
                        "is_async": is_async,
                    },
                    "features": features,
                }
            )

    def _handle_decorated_definition(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Python decorated function/class definitions."""
        # Find the actual definition within the decorated definition
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "function_definition":
                    self._handle_function_definition(
                        child, constructs, lines, scope_stack, content
                    )
                elif child.type == "class_definition":
                    self._handle_class_definition(
                        child, constructs, lines, scope_stack, content
                    )

    def _process_block_children(
        self,
        block_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process children of a block node (class body, function body, etc.)."""
        for child in block_node.children:
            if hasattr(child, "type"):
                self._handle_language_constructs(
                    child, child.type, constructs, lines, scope_stack, content
                )

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

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        return node_type in [
            "class_definition",
            "function_definition",
            "decorated_definition",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Python constructs from ERROR node text using regex fallback."""
        constructs = []

        # Python-specific regex patterns
        patterns = {
            "class": r"^\s*class\s+(\w+)(?:\([^)]*\))?:",
            "function": r"^\s*(?:async\s+)?def\s+(\w+)\s*\([^)]*\):",
            "decorator": r"^\s*@(\w+)",
        }

        lines = error_text.split("\n")

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)

                    # Find the end of this construct
                    end_line = self._find_python_construct_end(
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
                                "global"
                                if construct_type in ["class", "function"]
                                else "decorator"
                            ),
                            "line_start": start_line + line_idx + 1,
                            "line_end": start_line + end_line + 1,
                            "text": construct_text,
                            "context": {"extracted_from_error": True},
                            "features": [f"{construct_type}_implementation"],
                        }
                    )

        return constructs

    def _find_python_construct_end(
        self, lines: List[str], start_line: int, construct_type: str
    ) -> int:
        """Find the end line of a Python construct."""
        if construct_type in ["class", "function"]:
            # Find matching indentation
            if start_line >= len(lines):
                return start_line

            base_indent = len(lines[start_line]) - len(lines[start_line].lstrip())

            for i in range(start_line + 1, len(lines)):
                line = lines[i].strip()
                if not line:  # Skip empty lines
                    continue

                current_indent = len(lines[i]) - len(lines[i].lstrip())
                if current_indent <= base_indent:
                    return i - 1

            return len(lines) - 1
        elif construct_type == "decorator":
            # Decorators are single line
            return start_line

        return min(start_line + 10, len(lines) - 1)

    def _detect_async_function(self, node_text: str) -> bool:
        """Detect if a function is async by examining the node text."""
        # Look for 'async def' at the beginning of any line
        lines = node_text.split("\n")
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("async def "):
                return True
        return False

    def _extract_python_function_signature(
        self, node_text: str, function_name: str
    ) -> str:
        """Extract the Python function signature from node text."""
        # Find the function definition - it might span multiple lines
        lines = node_text.split("\n")
        signature_lines = []
        found_def = False

        for line in lines:
            line_stripped = line.strip()

            # Look for the def line
            if (
                "def " + function_name in line_stripped
                or "async def " + function_name in line_stripped
            ) and "(" in line_stripped:
                found_def = True
                signature_lines.append(line_stripped)
                if ":" in line_stripped:
                    break  # Single line function def
            elif found_def:
                # Continue collecting lines until we find the colon
                signature_lines.append(line_stripped)
                if ":" in line_stripped:
                    break

        if signature_lines:
            full_signature = " ".join(signature_lines)
            # Extract everything up to the colon
            signature = full_signature.split(":")[0].strip()
            return signature

        return f"def {function_name}()"
