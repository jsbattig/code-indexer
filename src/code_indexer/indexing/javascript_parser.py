"""
JavaScript semantic parser using regex-based parsing.

Since JavaScript/TypeScript AST parsing would require external dependencies
like tree-sitter or babel, this implementation uses regex patterns to identify
common JavaScript constructs. While not as robust as a full AST parser,
it covers the most common patterns for semantic chunking.
"""

import re
from pathlib import Path
from typing import List, Dict, Any

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import BaseSemanticParser, SemanticChunk


class JavaScriptSemanticParser(BaseSemanticParser):
    """Semantic parser for JavaScript files using regex patterns."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config)
        self.language = "javascript"

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse JavaScript content and create semantic chunks."""
        chunks = []
        lines = content.split("\n")
        file_ext = Path(file_path).suffix

        # Find all constructs in the file
        constructs = self._find_constructs(content, lines, file_path)

        # Create chunks from constructs
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

    def _find_constructs(
        self, content: str, lines: List[str], file_path: str = "unknown"
    ) -> List[Dict[str, Any]]:
        """Find JavaScript constructs using regex patterns."""
        constructs = []

        # First pass: find all classes and their boundaries
        class_boundaries = self._find_class_boundaries(lines)

        # Detect React components for component type assignment
        react_components = self._detect_react_components(content)
        react_component_names = {comp["name"] for comp in react_components}

        # Second pass: find all other constructs
        current_class = None
        current_class_end = 0

        for line_num, line in enumerate(lines, 1):
            # Update current class context
            for class_info in class_boundaries:
                if class_info["start"] <= line_num <= class_info["end"]:
                    current_class = class_info["name"]
                    current_class_end = class_info["end"]
                    break
            else:
                if line_num > current_class_end:
                    current_class = None

            # Check for class definitions
            class_match = re.search(
                r"^\s*class\s+(\w+)(?:\s+(?:extends|implements)\s+[^{]+)?\s*\{", line
            )
            if class_match:
                class_name = class_match.group(1)
                end_line = self._find_block_end(lines, line_num - 1)

                construct: Dict[str, Any] = {
                    "type": "class",
                    "name": class_name,
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": f"class {class_name}",
                    "scope": "global",
                    "features": [],
                    "context": {},
                }
                constructs.append(construct)
                continue

            # Check for function definitions (not inside classes)
            if not current_class:
                func_match = re.search(
                    r"^\s*(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*\{", line
                )
                if func_match:
                    func_name = func_match.group(1)
                    end_line = self._find_block_end(lines, line_num - 1)

                    features = []
                    if "async" in line:
                        features.append("async")

                    signature = line.strip()
                    if "{" in signature:
                        signature = signature[: signature.index("{")].strip()

                    # Check if this is a React component
                    construct_type = (
                        "component"
                        if func_name in react_component_names
                        else "function"
                    )

                    construct = {
                        "type": construct_type,
                        "name": func_name,
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "global",
                        "features": features,
                        "context": {},
                    }
                    constructs.append(construct)
                    continue

            # Check for arrow functions (not inside classes)
            if not current_class:
                arrow_match = re.search(
                    r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{",
                    line,
                )
                if arrow_match:
                    func_name = arrow_match.group(1)
                    end_line = self._find_arrow_function_end(lines, line_num - 1)

                    features = []
                    if "async" in line:
                        features.append("async")

                    signature = line.strip()
                    if "=>" in signature and "{" in signature:
                        signature = signature[: signature.index("{")].strip()

                    # Check if this is a React component
                    construct_type = (
                        "component"
                        if func_name in react_component_names
                        else "function"
                    )

                    construct = {
                        "type": construct_type,
                        "name": func_name,
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "global",
                        "features": features,
                        "context": {},
                    }
                    constructs.append(construct)
                    continue

            # Check for methods (inside classes)
            if current_class:
                # Constructor
                constructor_match = re.search(r"^\s*constructor\s*\([^)]*\)\s*\{", line)
                if constructor_match:
                    end_line = self._find_block_end(lines, line_num - 1)

                    signature = line.strip()
                    if "{" in signature:
                        signature = signature[: signature.index("{")].strip()

                    construct = {
                        "type": "method",
                        "name": "constructor",
                        "path": f"{current_class}.constructor",
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "class",
                        "parent": current_class,
                        "features": [],
                        "context": {},
                    }
                    constructs.append(construct)
                    continue

                # Regular methods
                method_match = re.search(
                    r"^\s*(?:(async|static)\s+)?(\w+)\s*\([^)]*\)\s*\{", line
                )
                if method_match and not any(
                    kw in line
                    for kw in [
                        "function",
                        "class",
                        "const",
                        "let",
                        "var",
                        "if",
                        "for",
                        "while",
                    ]
                ):

                    modifier = method_match.group(1)
                    method_name = method_match.group(2)
                    end_line = self._find_block_end(lines, line_num - 1)

                    features = []
                    if modifier == "async":
                        features.append("async")
                    if modifier == "static":
                        features.append("static")

                    signature = line.strip()
                    if "{" in signature:
                        signature = signature[: signature.index("{")].strip()

                    construct = {
                        "type": "method",
                        "name": method_name,
                        "path": f"{current_class}.{method_name}",
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "class",
                        "parent": current_class,
                        "features": features,
                        "context": {},
                    }
                    constructs.append(construct)
                    continue

            # Check for object methods (not inside classes)
            if not current_class:
                obj_method_match = re.search(
                    r"^\s*(\w+)\s*:\s*function\s*\([^)]*\)\s*\{", line
                )
                if obj_method_match:
                    method_name = obj_method_match.group(1)
                    end_line = self._find_block_end(lines, line_num - 1)

                    signature = line.strip()
                    if "{" in signature:
                        signature = signature[: signature.index("{")].strip()

                    construct = {
                        "type": "method",
                        "name": method_name,
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "object",
                        "features": [],
                        "context": {},
                    }
                    constructs.append(construct)
                    continue

                # Object shorthand methods
                obj_shorthand_match = re.search(r"^\s*(\w+)\s*\([^)]*\)\s*\{", line)
                if (
                    obj_shorthand_match
                    and not any(
                        re.search(r"\b" + kw + r"\b", line)
                        for kw in ["function", "class", "if", "for", "while"]
                    )
                    and self._is_likely_object_method(lines, line_num - 1)
                ):

                    method_name = obj_shorthand_match.group(1)
                    end_line = self._find_block_end(lines, line_num - 1)

                    signature = line.strip()
                    if "{" in signature:
                        signature = signature[: signature.index("{")].strip()

                    construct = {
                        "type": "method",
                        "name": method_name,
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "object",
                        "features": [],
                        "context": {},
                    }
                    constructs.append(construct)

        # If no constructs found, treat as one large chunk
        if not constructs:
            constructs.append(
                {
                    "type": "module",
                    "name": Path(file_path).stem,
                    "text": content,
                    "line_start": 1,
                    "line_end": len(lines),
                    "signature": f"module {Path(file_path).stem}",
                    "scope": "global",
                    "features": [],
                    "context": {},
                }
            )

        return constructs

    def _find_class_boundaries(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Find class boundaries to help with method detection."""
        classes = []

        for line_num, line in enumerate(lines, 1):
            class_match = re.search(
                r"^\s*class\s+(\w+)(?:\s+(?:extends|implements)\s+[^{]+)?\s*\{", line
            )
            if class_match:
                class_name = class_match.group(1)
                end_line = self._find_block_end(lines, line_num - 1)
                classes.append({"name": class_name, "start": line_num, "end": end_line})

        return classes

    def _is_likely_object_method(self, lines: List[str], line_index: int) -> bool:
        """Check if a line is likely an object method by looking at context."""
        # Look backwards for object literal indicators
        for i in range(max(0, line_index - 5), line_index):
            line = lines[i].strip()
            if re.search(r"^\s*\w+\s*=\s*\{", line) or re.search(
                r"^\s*const\s+\w+\s*=\s*\{", line
            ):
                return True
            if line.endswith("{") and ("=" in line or "const" in line):
                return True

        # Look for surrounding object-like structure
        for i in range(max(0, line_index - 2), min(len(lines), line_index + 3)):
            line = lines[i].strip()
            if ":" in line and not line.startswith("//"):
                return True

        return False

    def _find_block_end(self, lines: List[str], start_line: int) -> int:
        """Find the end of a code block starting from start_line."""
        brace_count = 0
        found_opening = False

        for i in range(start_line, len(lines)):
            line = lines[i]
            open_braces = line.count("{")
            close_braces = line.count("}")
            brace_count += open_braces - close_braces

            # Check if this line contains both opening and closing braces (single-line block)
            if (
                open_braces > 0
                and close_braces > 0
                and brace_count == 0
                and not found_opening
            ):
                # Single-line block like "constructor() {}"
                return i + 1

            if brace_count > 0:
                found_opening = True
            elif found_opening and brace_count == 0:
                return i + 1

        return len(lines)

    def _find_arrow_function_end(self, lines: List[str], start_line: int) -> int:
        """Find the end of an arrow function, handling both block and expression forms."""
        line = lines[start_line]

        # Check if it's a single expression arrow function
        if "=>" in line and "{" not in line:
            # Single expression, ends at semicolon or end of line
            if ";" in line:
                return start_line + 1
            else:
                # Look for the end in subsequent lines
                for i in range(start_line + 1, len(lines)):
                    if lines[i].strip().endswith(";") or lines[i].strip() == "":
                        return i + 1
                return start_line + 1
        else:
            # Block arrow function, use normal block finding
            return self._find_block_end(lines, start_line)

    def _detect_react_components(self, content: str) -> List[Dict[str, Any]]:
        """Detect React components in the code."""
        components = []

        # Look for function/arrow function patterns that look like React components
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Pattern for arrow functions: const ComponentName = (...) => {
            arrow_match = re.search(
                r"^\s*const\s+(\w+)\s*=\s*\([^)]*\)\s*=>\s*\{", line
            )
            if arrow_match:
                comp_name = arrow_match.group(1)
                # Check if it looks like a React component (starts with uppercase)
                if comp_name[0].isupper():
                    # Look ahead to see if it contains JSX-like patterns
                    if self._contains_jsx_in_function(lines, line_num - 1):
                        components.append(
                            {"type": "component", "name": comp_name, "line": line_num}
                        )

            # Pattern for function declarations: function ComponentName(...) {
            func_match = re.search(r"^\s*function\s+(\w+)\s*\([^)]*\)\s*\{", line)
            if func_match:
                comp_name = func_match.group(1)
                # Check if it looks like a React component (starts with uppercase)
                if comp_name[0].isupper():
                    # Look ahead to see if it contains JSX-like patterns
                    if self._contains_jsx_in_function(lines, line_num - 1):
                        components.append(
                            {"type": "component", "name": comp_name, "line": line_num}
                        )

        return components

    def _contains_jsx_in_function(self, lines: List[str], start_line: int) -> bool:
        """Check if a function contains JSX-like patterns."""
        end_line = self._find_block_end(lines, start_line)

        for i in range(start_line, min(end_line, len(lines))):
            line = lines[i]
            # Look for JSX patterns: <tag>, </tag>, return (<, return <
            if any(
                pattern in line
                for pattern in ["<", "return (", "return<", "jsx", "JSX"]
            ):
                return True

        return False
