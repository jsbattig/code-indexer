"""
Python AST-based semantic parser with regex fallback.

Uses Python's built-in ast module to parse Python code and create
semantic chunks based on code structure. When AST parsing fails,
falls back to regex-based parsing to ensure no content is lost.
"""

import ast
import re
from typing import List, Optional, Tuple, Union, Dict, Any
from pathlib import Path

from code_indexer.config import IndexingConfig
from .semantic_chunker import BaseSemanticParser, SemanticChunk


class PythonSemanticParser(BaseSemanticParser):
    """Parser for Python code using the built-in ast module."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config)
        self.current_class = None
        self.module_chunks: List[SemanticChunk] = []
        self.chunks: List[SemanticChunk] = []

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse Python content and create semantic chunks."""
        self.chunks = []
        self.current_class = None

        try:
            tree = ast.parse(content, filename=file_path)
            lines = content.split("\n")

            # First pass: collect module-level code (imports, globals)
            module_code_lines = self._collect_module_code(tree, lines)
            if module_code_lines:
                module_chunk = self._create_module_chunk(module_code_lines, file_path)
                if module_chunk:
                    self.chunks.append(module_chunk)

            # Second pass: process all definitions
            self._process_node(tree, content, lines, file_path)

            # Update chunk indices
            total_chunks = len(self.chunks)
            for i, chunk in enumerate(self.chunks):
                chunk.chunk_index = i
                chunk.total_chunks = total_chunks

            return self.chunks

        except (SyntaxError, Exception):
            # Fall back to regex-based parsing to ensure no content is lost
            return self._fallback_parse(content, file_path)

    def _collect_module_code(
        self, tree: ast.AST, lines: List[str]
    ) -> List[Tuple[int, str]]:
        """Collect module-level code (imports, globals, etc.)."""
        module_lines = []
        definition_lines = set()

        # Collect line numbers of all definitions including decorators
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, "lineno"):
                    # Include decorators
                    start_line = node.lineno
                    if hasattr(node, "decorator_list") and node.decorator_list:
                        start_line = min(d.lineno for d in node.decorator_list)

                    # Mark all lines from definition start (including decorators) to end
                    end_line = getattr(node, "end_lineno", node.lineno)
                    for line_no in range(start_line, end_line + 1):
                        definition_lines.add(line_no)

        # Collect non-definition lines
        for i, line in enumerate(lines, 1):
            if i not in definition_lines and line.strip():
                module_lines.append((i, line))

        return module_lines

    def _create_module_chunk(
        self, module_lines: List[Tuple[int, str]], file_path: str
    ) -> Optional[SemanticChunk]:
        """Create a chunk for module-level code."""
        if not module_lines:
            return None

        line_numbers = [ln for ln, _ in module_lines]
        line_texts = [text for _, text in module_lines]

        return SemanticChunk(
            text="\n".join(line_texts),
            chunk_index=0,  # Will be updated later
            total_chunks=0,  # Will be updated later
            size=sum(len(text) for _, text in module_lines),
            file_path=file_path,
            file_extension=Path(file_path).suffix,
            line_start=min(line_numbers),
            line_end=max(line_numbers),
            semantic_type="module_code",
            semantic_name="imports_and_globals",
            semantic_path="module",
            semantic_signature=None,
            semantic_parent=None,
            semantic_context={"type": "module_level"},
            semantic_scope="module",
            semantic_language_features=[],
        )

    def _process_node(
        self, node: ast.AST, content: str, lines: List[str], file_path: str
    ):
        """Process AST node and create chunks."""
        if isinstance(node, ast.ClassDef):
            self._process_class(node, content, lines, file_path)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if self.current_class is None:  # Top-level function
                self._process_function(node, content, lines, file_path)
        else:
            # Process child nodes
            for child in ast.iter_child_nodes(node):
                self._process_node(child, content, lines, file_path)

    def _process_class(
        self, node: ast.ClassDef, content: str, lines: List[str], file_path: str
    ):
        """Process class definition."""
        # Calculate size to determine if we need to split
        class_content = self._extract_node_content(node, lines)
        class_size = len(class_content)

        if class_size <= self.max_chunk_size:
            # Create single chunk for entire class
            chunk = self._create_class_chunk(node, class_content, file_path)
            self.chunks.append(chunk)
        else:
            # Split class into multiple chunks
            # First chunk: class definition and __init__ if present
            self._split_large_class(node, content, lines, file_path)

        # Don't process nested functions/classes here as they're included in the class chunk

    def _process_function(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        content: str,
        lines: List[str],
        file_path: str,
    ):
        """Process function definition."""
        # Store original line number
        original_lineno = node.lineno

        # Include decorators
        if node.decorator_list:
            first_decorator_line = min(d.lineno for d in node.decorator_list)
            node.lineno = first_decorator_line

        func_content = self._extract_node_content(node, lines)
        chunk = self._create_function_chunk(node, func_content, file_path)

        # Restore for accurate line numbers in chunk
        if node.decorator_list:
            chunk.line_start = min(d.lineno for d in node.decorator_list)
        else:
            chunk.line_start = original_lineno

        self.chunks.append(chunk)

    def _extract_node_content(self, node: ast.AST, lines: List[str]) -> str:
        """Extract content for a node including decorators."""
        start_line = getattr(node, "lineno", 1) - 1
        end_line = getattr(node, "end_lineno", getattr(node, "lineno", 1)) - 1

        # Include decorators for functions and classes
        if hasattr(node, "decorator_list") and node.decorator_list:
            first_decorator_line = min(d.lineno for d in node.decorator_list) - 1
            start_line = first_decorator_line

        return "\n".join(lines[start_line : end_line + 1])

    def _create_class_chunk(
        self, node: ast.ClassDef, content: str, file_path: str
    ) -> SemanticChunk:
        """Create a chunk for a class."""
        # Get base classes
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                try:
                    base_src = ast.get_source_segment(content, base)
                    bases.append(base_src or "Unknown")
                except (IndexError, Exception):
                    bases.append("Unknown")

        # Count methods
        methods = [
            n
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        return SemanticChunk(
            text=content,
            chunk_index=0,  # Will be updated
            total_chunks=0,  # Will be updated
            size=len(content),
            file_path=file_path,
            file_extension=Path(file_path).suffix,
            line_start=self._get_node_start_line(node),
            line_end=getattr(node, "end_lineno", node.lineno),
            semantic_type="class",
            semantic_name=node.name,
            semantic_path=node.name,
            semantic_signature=(
                f"class {node.name}({', '.join(bases)})"
                if bases
                else f"class {node.name}"
            ),
            semantic_parent=None,
            semantic_context={
                "decorators": self._safe_get_decorators(content, node.decorator_list),
                "bases": bases,
                "method_count": len(methods),
            },
            semantic_scope="module",
            semantic_language_features=[],
        )

    def _create_function_chunk(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        func_content: str,
        file_path: str,
    ) -> SemanticChunk:
        """Create a chunk for a function."""
        # Build signature - extract from actual content
        lines = func_content.split("\n")
        signature_line = None
        for line in lines:
            if line.strip().startswith("def ") or line.strip().startswith("async def "):
                signature_line = line.strip()
                if not signature_line.endswith(":"):
                    signature_line += ":"
                break

        signature = signature_line or f"def {node.name}():"

        # Determine features
        features = []
        if isinstance(node, ast.AsyncFunctionDef):
            features.append("async")
        if node.name.startswith("_"):
            features.append("private")
        if node.name.startswith("__") and node.name.endswith("__"):
            features.append("dunder")

        # Get decorators from content
        decorators = []
        for line in lines:
            if line.strip().startswith("@"):
                decorators.append(line.strip())

        return SemanticChunk(
            text=func_content,
            chunk_index=0,  # Will be updated
            total_chunks=0,  # Will be updated
            size=len(func_content),
            file_path=file_path,
            file_extension=Path(file_path).suffix,
            line_start=self._get_node_start_line(node),
            line_end=getattr(node, "end_lineno", node.lineno),
            semantic_type="function",
            semantic_name=node.name,
            semantic_path=node.name,
            semantic_signature=signature,
            semantic_parent=None,
            semantic_context={
                "decorators": decorators,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "is_private": node.name.startswith("_"),
            },
            semantic_scope="global",
            semantic_language_features=features,
        )

    def _split_large_class(
        self, node: ast.ClassDef, content: str, lines: List[str], file_path: str
    ):
        """Split a large class into multiple chunks."""
        # Extract class header (class definition line + docstring if present)
        class_def_line = lines[node.lineno - 1]
        header_lines = [class_def_line]
        # header_end_line = node.lineno  # Currently unused

        # Check for class docstring
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Str)
        ):
            docstring_node = node.body[0]
            docstring_end = getattr(docstring_node, "end_lineno", docstring_node.lineno)
            for i in range(node.lineno, docstring_end):
                if i - 1 < len(lines):
                    header_lines.append(lines[i])
            # header_end_line = docstring_end  # Currently unused

        # Process each method as a separate chunk
        method_chunks = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_content = self._extract_node_content(item, lines)

                # Create method chunk with class context
                method_chunk = self._create_method_chunk(
                    item,
                    method_content,
                    file_path,
                    class_name=node.name,
                    class_signature=f"class {node.name}",
                )
                method_chunks.append(method_chunk)

        # If we have methods to split
        if method_chunks:
            # Set split tracking for all chunks
            total_parts = len(method_chunks)
            for i, chunk in enumerate(method_chunks):
                chunk.is_split_object = True
                chunk.part_number = i + 1
                chunk.total_parts = total_parts
                chunk.part_of_total = f"{i + 1} of {total_parts}"

            self.chunks.extend(method_chunks)
        else:
            # No methods or still small enough - create single chunk
            class_content = self._extract_node_content(node, lines)
            chunk = self._create_class_chunk(node, class_content, file_path)
            self.chunks.append(chunk)

    def _create_method_chunk(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        content: str,
        file_path: str,
        class_name: str,
        class_signature: str,
    ) -> SemanticChunk:
        """Create a chunk for a method within a class."""
        # Use the regular function chunk creator but adjust metadata
        chunk = self._create_function_chunk(node, content, file_path)

        # Update to reflect this is a method, not a function
        chunk.semantic_type = "method"
        chunk.semantic_path = f"{class_name}.{node.name}"
        chunk.semantic_parent = class_signature
        chunk.semantic_scope = "class"

        return chunk

    def _safe_get_decorators(
        self, content: str, decorator_list: List[ast.expr]
    ) -> List[str]:
        """Safely extract decorator source code, handling parsing errors."""
        decorators = []
        for d in decorator_list:
            try:
                decorator_src = ast.get_source_segment(content, d)
                if decorator_src:
                    decorators.append(decorator_src)
                else:
                    decorators.append("@<unknown>")
            except (IndexError, Exception):
                decorators.append("@<unknown>")
        return decorators

    def _get_node_start_line(self, node: ast.AST) -> int:
        """Get the actual start line of a node, including decorators."""
        if hasattr(node, "decorator_list") and node.decorator_list:
            decorator_lines: List[int] = [
                d.lineno
                for d in node.decorator_list
                if hasattr(d, "lineno") and isinstance(d.lineno, int)
            ]
            if decorator_lines:
                return min(decorator_lines)
        lineno_val = getattr(node, "lineno", None)
        if isinstance(lineno_val, int):
            return lineno_val
        return 1

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Fallback regex-based parsing when AST parsing fails."""
        chunks = []
        lines = content.split("\n")
        file_ext = Path(file_path).suffix

        # Extract constructs using regex patterns
        constructs = self._extract_constructs_from_error_text(content, lines)

        # Create semantic chunks
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
                semantic_chunking=False,
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

        return chunks if chunks else self._create_fallback_chunk(content, file_path)

    def _extract_constructs_from_error_text(
        self, content: str, lines: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Python constructs from content using regex fallback."""
        constructs = []

        # Python-specific regex patterns
        patterns = {
            "class": r"^(\s*)class\s+(\w+)(?:\([^)]*\))?:\s*",
            "function": r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\([^)]*\):\s*",
            "method": r"^(\s+)(?:async\s+)?def\s+(\w+)\s*\([^)]*\):\s*",
        }

        current_class = None
        current_indent = 0

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    indent = len(match.group(1))
                    name = match.group(2)

                    # Determine if this is a class method or top-level function
                    if (
                        construct_type == "function"
                        and current_class
                        and indent > current_indent
                    ):
                        construct_type = "method"

                    # Update current class context
                    if construct_type == "class":
                        current_class = name
                        current_indent = indent
                    elif indent <= current_indent:
                        current_class = None
                        current_indent = 0

                    # Find the end of this construct
                    end_line = self._find_python_construct_end(lines, line_idx, indent)

                    # Build construct text
                    construct_lines = lines[line_idx : end_line + 1]
                    construct_text = "\n".join(construct_lines)

                    # Build path
                    if construct_type == "method" and current_class:
                        path = f"{current_class}.{name}"
                        parent = current_class
                        scope = "class"
                    else:
                        path = name
                        parent = None
                        scope = "global"

                    constructs.append(
                        {
                            "type": construct_type,
                            "name": name,
                            "path": path,
                            "signature": line.strip(),
                            "parent": parent,
                            "scope": scope,
                            "line_start": line_idx + 1,
                            "line_end": end_line + 1,
                            "text": construct_text,
                            "context": {"extracted_from_error": True, "indent": indent},
                            "features": [f"{construct_type}_implementation"],
                        }
                    )

        return constructs

    def _find_python_construct_end(
        self, lines: List[str], start_line: int, base_indent: int
    ) -> int:
        """Find the end line of a Python construct based on indentation."""
        for i in range(start_line + 1, len(lines)):
            line = lines[i]

            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith("#"):
                continue

            # Check indentation
            line_indent = len(line) - len(line.lstrip())

            # If we found a line at the same or lesser indentation, we've reached the end
            if line_indent <= base_indent:
                return i - 1

        return len(lines) - 1

    def _create_fallback_chunk(
        self, content: str, file_path: str
    ) -> List[SemanticChunk]:
        """Create a single fallback chunk when no constructs are found."""
        lines = content.split("\n")
        return [
            SemanticChunk(
                text=content,
                chunk_index=0,
                total_chunks=1,
                size=len(content),
                file_path=file_path,
                file_extension=Path(file_path).suffix,
                line_start=1,
                line_end=len(lines),
                semantic_chunking=False,
                semantic_type="module",
                semantic_name=Path(file_path).stem,
                semantic_path=Path(file_path).stem,
                semantic_signature=f"module {Path(file_path).stem}",
                semantic_parent=None,
                semantic_context={"fallback_parsing": True},
                semantic_scope="global",
                semantic_language_features=["fallback_chunk"],
            )
        ]
