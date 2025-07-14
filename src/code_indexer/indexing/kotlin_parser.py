"""
Kotlin semantic parser using regex-based parsing.

This implementation uses regex patterns to identify common Kotlin constructs
for semantic chunking. While not as robust as a full AST parser,
it covers the most common patterns for semantic chunking.
"""

import re
from pathlib import Path
from typing import List, Dict, Any

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import BaseSemanticParser, SemanticChunk


class KotlinSemanticParser(BaseSemanticParser):
    """Semantic parser for Kotlin files using regex patterns."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config)
        self.language = "kotlin"

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse Kotlin content and create semantic chunks."""
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
        """Find Kotlin constructs using regex patterns."""
        constructs = []

        # Check for obviously malformed content
        if self._is_malformed_kotlin(content):
            return []

        # Extract package information
        package_name = self._extract_package(lines)

        # Find all classes and their boundaries first
        class_boundaries = self._find_class_boundaries(lines)

        # Process each line to find constructs
        current_class = None
        current_class_end = 0
        current_annotations = []

        for line_num, line in enumerate(lines, 1):
            line_stripped = line.strip()

            # Skip empty lines and comments
            if (
                not line_stripped
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
            ):
                continue

            # Update current class context
            for class_info in class_boundaries:
                if class_info["start"] <= line_num <= class_info["end"]:
                    current_class = class_info["name"]
                    current_class_end = class_info["end"]
                    break
            else:
                if line_num > current_class_end:
                    current_class = None

            # Check for annotations
            annotation_match = re.search(r"^\s*@(\w+)(?:\([^)]*\))?\s*$", line)
            if annotation_match:
                current_annotations.append(annotation_match.group(1))
                continue

            # Check for class definitions
            class_match = re.search(
                r"^\s*(?:(public|private|protected|internal|abstract|final|open|sealed|data|inner|enum|annotation|inline|value)\s+)*"
                r"(class|interface|object)\s+(\w+)(?:<[^>]*>)?"
                r"(?:\s*\()?",  # Optional opening parenthesis
                line,
            )
            if class_match:
                modifiers = [
                    m
                    for m in line.split()
                    if m
                    in [
                        "public",
                        "private",
                        "protected",
                        "internal",
                        "abstract",
                        "final",
                        "open",
                        "sealed",
                        "data",
                        "inner",
                        "enum",
                        "annotation",
                        "inline",
                        "value",
                    ]
                ]
                class_type = class_match.group(2)
                class_name = class_match.group(3)

                # Find where the class body actually starts (handle multi-line constructors)
                body_start_line = line_num - 1
                for i in range(line_num - 1, len(lines)):
                    if "{" in lines[i]:
                        body_start_line = i
                        break

                end_line = self._find_block_end(lines, body_start_line)

                # Extract generics if present
                generics = []
                if "<" in line and ">" in line:
                    generic_match = re.search(r"<([^>]+)>", line)
                    if generic_match:
                        generics = [
                            g.strip() for g in generic_match.group(1).split(",")
                        ]

                features = []
                if modifiers:
                    features.extend(modifiers)
                if generics:
                    features.append("generic")
                if current_annotations:
                    features.append("annotation")

                # Determine if this is a nested class
                parent_class = None
                scope = "global"

                for class_info in class_boundaries:
                    if (
                        class_info["start"] < line_num < class_info["end"]
                        and class_info["name"] != class_name
                    ):
                        parent_class = class_info["name"]
                        scope = "class"
                        break

                construct: Dict[str, Any] = {
                    "type": class_type,
                    "name": class_name,
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": line.strip().rstrip("{").strip(),
                    "scope": scope,
                    "parent": parent_class,
                    "features": features,
                    "context": {
                        "package": package_name,
                        "generics": generics,
                        "annotations": current_annotations.copy(),
                        "modifiers": modifiers,
                    },
                }
                constructs.append(construct)
                current_annotations = []
                continue

            # Check for companion object
            companion_match = re.search(
                r"^\s*companion\s+object(?:\s+(\w+))?\s*\{", line
            )
            if companion_match:
                companion_name = companion_match.group(1) or "Companion"
                end_line = self._find_block_end(lines, line_num - 1)

                construct = {
                    "type": "companion_object",
                    "name": companion_name,
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": line.strip().rstrip("{").strip(),
                    "scope": "class" if current_class else "global",
                    "parent": current_class,
                    "features": [],
                    "context": {"annotations": current_annotations.copy()},
                }
                constructs.append(construct)
                current_annotations = []
                continue

            # Check for function definitions
            func_match = re.search(
                r"^\s*(?:(public|private|protected|internal|abstract|final|open|override|suspend|inline|infix|operator|tailrec)\s+)*"
                r"fun\s+(?:<[^>]+>\s+)?(\w+)\s*\([^)]*\)"
                r"(?:\s*:\s*[^{=]+)?"  # Return type
                r"\s*[{=]",  # Function body or expression
                line,
            )
            if func_match:
                modifiers = [
                    m
                    for m in line.split()
                    if m
                    in [
                        "public",
                        "private",
                        "protected",
                        "internal",
                        "abstract",
                        "final",
                        "open",
                        "override",
                        "suspend",
                        "inline",
                        "infix",
                        "operator",
                        "tailrec",
                    ]
                ]
                func_name = func_match.group(2)

                # Check if it's an expression function (single line with =)
                if "=" in line and "{" not in line:
                    end_line = line_num
                else:
                    end_line = self._find_block_end(lines, line_num - 1)

                features = []
                if modifiers:
                    features.extend(modifiers)
                if "suspend" in modifiers:
                    features.append("coroutine")
                if current_annotations:
                    features.append("annotation")

                signature = line.strip().rstrip("{").rstrip("=").strip()

                construct = {
                    "type": "function" if not current_class else "method",
                    "name": func_name,
                    "path": (
                        f"{current_class}.{func_name}" if current_class else func_name
                    ),
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": signature,
                    "scope": "class" if current_class else "global",
                    "parent": current_class,
                    "features": features,
                    "context": {
                        "annotations": current_annotations.copy(),
                        "modifiers": modifiers,
                    },
                }
                constructs.append(construct)
                current_annotations = []
                continue

            # Check for property definitions with custom getters/setters
            property_match = re.search(
                r"^\s*(?:(public|private|protected|internal|open|override|const|lateinit)\s+)*"
                r"(?:val|var)\s+(\w+)\s*:\s*[^=]+(?:\s*=\s*[^{]+)?\s*$",
                line,
            )
            if property_match and current_class:
                # Check if next lines contain get() or set()
                has_accessor = False
                for i in range(line_num, min(line_num + 3, len(lines))):
                    if i < len(lines):
                        next_line = lines[i].strip()
                        if next_line.startswith("get()") or next_line.startswith(
                            "set("
                        ):
                            has_accessor = True
                            break

                if has_accessor:
                    prop_name = property_match.group(2)
                    end_line = line_num
                    # Find the end of the property accessor block
                    for i in range(line_num, len(lines)):
                        if i < len(lines):
                            check_line = lines[i].strip()
                            if check_line and not (
                                check_line.startswith("get")
                                or check_line.startswith("set")
                                or check_line == "}"
                            ):
                                end_line = i
                                break

                    modifiers = [
                        m
                        for m in line.split()
                        if m
                        in [
                            "public",
                            "private",
                            "protected",
                            "internal",
                            "open",
                            "override",
                            "const",
                            "lateinit",
                        ]
                    ]

                    features = ["property"]
                    if modifiers:
                        features.extend(modifiers)

                    construct = {
                        "type": "property",
                        "name": prop_name,
                        "path": f"{current_class}.{prop_name}",
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": line.strip(),
                        "scope": "class",
                        "parent": current_class,
                        "features": features,
                        "context": {
                            "annotations": current_annotations.copy(),
                            "modifiers": modifiers,
                        },
                    }
                    constructs.append(construct)
                    current_annotations = []
                    continue

            # Check for extension functions
            ext_func_match = re.search(
                r"^\s*(?:(public|private|protected|internal|inline|infix|operator)\s+)*"
                r"fun\s+(?:<[^>]+>\s+)?"  # Optional generic parameters
                r"([^.\s]+(?:<[^>]+>)?)\s*\.\s*(\w+)\s*\([^)]*\)"
                r"(?:\s*:\s*[^{=]+)?"
                r"\s*[{=]",
                line,
            )
            if ext_func_match:
                modifiers = [
                    m
                    for m in line.split()
                    if m
                    in [
                        "public",
                        "private",
                        "protected",
                        "internal",
                        "inline",
                        "infix",
                        "operator",
                    ]
                ]
                receiver_type = ext_func_match.group(2)
                func_name = ext_func_match.group(3)

                # Check if it's an expression function
                if "=" in line and "{" not in line:
                    end_line = line_num
                else:
                    end_line = self._find_block_end(lines, line_num - 1)

                features = ["extension"]
                if modifiers:
                    features.extend(modifiers)

                signature = line.strip().rstrip("{").rstrip("=").strip()

                construct = {
                    "type": "extension_function",
                    "name": func_name,
                    "path": f"{receiver_type}.{func_name}",
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": signature,
                    "scope": "global",
                    "parent": None,
                    "features": features,
                    "context": {
                        "receiver_type": receiver_type,
                        "annotations": current_annotations.copy(),
                        "modifiers": modifiers,
                    },
                }
                constructs.append(construct)
                current_annotations = []
                continue

            # Reset annotations if we didn't use them
            if not line_stripped.startswith("@"):
                current_annotations = []

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
                    "context": {"package": package_name},
                }
            )

        return constructs

    def _extract_package(self, lines: List[str]) -> str:
        """Extract package declaration from Kotlin file."""
        for line in lines:
            package_match = re.search(r"^\s*package\s+([\w.]+)\s*$", line)
            if package_match:
                return package_match.group(1)
        return ""

    def _find_class_boundaries(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Find class boundaries to help with method detection."""
        classes = []

        for line_num, line in enumerate(lines, 1):
            class_match = re.search(
                r"^\s*(?:(?:public|private|protected|internal|abstract|final|open|sealed|data|inner|enum|annotation|inline|value)\s+)*"
                r"(class|interface|object)\s+(\w+)(?:<[^>]*>)?",
                line,
            )
            if class_match:
                class_type = class_match.group(1)
                class_name = class_match.group(2)

                # Find where the class body actually starts (handle multi-line constructors)
                body_start_line = line_num - 1
                for i in range(line_num - 1, len(lines)):
                    if "{" in lines[i]:
                        body_start_line = i
                        break

                end_line = self._find_block_end(lines, body_start_line)
                classes.append(
                    {
                        "name": class_name,
                        "type": class_type,
                        "start": line_num,
                        "end": end_line,
                    }
                )

        return classes

    def _find_block_end(self, lines: List[str], start_line: int) -> int:
        """Find the end of a code block starting from start_line."""
        brace_count = 0
        found_opening = False

        for i in range(start_line, len(lines)):
            line = lines[i]
            # Skip string literals and comments to avoid counting braces inside them
            line_cleaned = self._remove_strings_and_comments(line)

            brace_count += line_cleaned.count("{")
            brace_count -= line_cleaned.count("}")

            if brace_count > 0:
                found_opening = True
            elif found_opening and brace_count == 0:
                return i + 1

        return len(lines)

    def _remove_strings_and_comments(self, line: str) -> str:
        """Remove string literals and comments from a line to avoid counting braces inside them."""
        # Simple approach: remove quoted strings and line comments
        result = ""
        in_string = False
        in_char = False
        in_template = False
        escape_next = False
        i = 0

        while i < len(line):
            char = line[i]

            if escape_next:
                escape_next = False
                i += 1
                continue

            if char == "\\" and (in_string or in_char or in_template):
                escape_next = True
                i += 1
                continue

            # Handle template strings in Kotlin
            if char == "$" and i + 1 < len(line) and line[i + 1] == "{" and in_string:
                in_template = True
                i += 2
                continue

            if in_template and char == "}":
                in_template = False
                i += 1
                continue

            if char == '"' and not in_char and not in_template:
                in_string = not in_string
                i += 1
                continue

            if char == "'" and not in_string and not in_template:
                in_char = not in_char
                i += 1
                continue

            if not in_string and not in_char and not in_template:
                if char == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    # Rest of line is comment
                    break
                result += char

            i += 1

        return result

    def _is_malformed_kotlin(self, content: str) -> bool:
        """Detect obviously malformed Kotlin content that should fall back to text chunking."""
        lines = content.split("\n")

        # Look for lines that have obvious non-Kotlin syntax
        for line in lines:
            line_stripped = line.strip()
            if (
                not line_stripped
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
            ):
                continue

            # Skip package/import/class declarations which are valid
            if any(
                line_stripped.startswith(keyword)
                for keyword in [
                    "package",
                    "import",
                    "class",
                    "interface",
                    "object",
                    "fun",
                    "val",
                    "var",
                    "enum",
                    "sealed",
                    "data",
                ]
            ):
                continue

            # Look for lines that are clearly not Kotlin syntax
            if line_stripped and not any(
                char in line_stripped
                for char in [
                    ";",
                    "{",
                    "}",
                    "(",
                    ")",
                    "=",
                    "+",
                    "-",
                    "*",
                    "/",
                    ":",
                    ".",
                    ",",
                ]
            ):
                # Check if it's just random words (common in test malformed content)
                words = line_stripped.split()
                if len(words) >= 3 and all(
                    word.isalpha() and word.islower() for word in words
                ):
                    return True

        return False
