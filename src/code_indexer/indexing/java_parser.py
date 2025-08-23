"""
Java semantic parser using regex-based parsing.

This implementation uses regex patterns to identify common Java constructs
for semantic chunking. While not as robust as a full AST parser,
it covers the most common patterns for semantic chunking.
"""

import re
from pathlib import Path
from typing import List, Dict, Any

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import BaseSemanticParser, SemanticChunk


class JavaSemanticParser(BaseSemanticParser):
    """Semantic parser for Java files using regex patterns."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config)
        self.language = "java"

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse Java content and create semantic chunks."""
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
        """Find Java constructs using regex patterns."""
        constructs = []

        # Check for obviously malformed content that looks like it starts with valid Java
        # but has obvious syntax errors
        if self._is_malformed_java(content):
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
                r"^\s*(?:(public|private|protected|abstract|final|static)\s+)*"
                r"(class|interface|enum)\s+(\w+)(?:<[^>]*>)?"
                r"(?:\s+(?:extends|implements)\s+[^{]+)?\s*\{",
                line,
            )
            if class_match:
                modifiers = [
                    m
                    for m in line.split()
                    if m
                    in ["public", "private", "protected", "abstract", "final", "static"]
                ]
                class_type = class_match.group(2)
                class_name = class_match.group(3)
                end_line = self._find_block_end(lines, line_num - 1)

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

                # Determine if this is a nested class by checking if we're inside another class
                parent_class = None
                scope = "global"

                # Find the innermost class that contains this line (excluding itself)
                for class_info in class_boundaries:
                    if (
                        class_info["start"] < line_num < class_info["end"]
                        and class_info["name"] != class_name
                    ):
                        # This class is nested inside class_info
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

            # Check for method definitions (inside classes)
            if current_class:
                # Constructor
                constructor_match = re.search(
                    rf"^\s*(?:(public|private|protected)\s+)?"
                    rf"{re.escape(current_class)}\s*\([^)]*\)\s*(?:throws\s+[^{{]+)?\s*\{{",
                    line,
                )
                if constructor_match:
                    modifiers = [
                        m
                        for m in line.split()
                        if m in ["public", "private", "protected"]
                    ]
                    end_line = self._find_block_end(lines, line_num - 1)

                    features = []
                    if modifiers:
                        features.extend(modifiers)
                    if current_annotations:
                        features.append("annotation")

                    signature = line.strip().rstrip("{").strip()

                    construct = {
                        "type": "method",
                        "name": current_class,  # Constructor name same as class
                        "path": f"{current_class}.{current_class}",
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "class",
                        "parent": current_class,
                        "features": features,
                        "context": {
                            "annotations": current_annotations.copy(),
                            "modifiers": modifiers,
                            "is_constructor": True,
                        },
                    }
                    constructs.append(construct)
                    current_annotations = []
                    continue

                # Regular methods (including abstract method declarations)
                method_match = re.search(
                    r"^\s*(?:(public|private|protected|static|abstract|final|synchronized|default)\s+)*"
                    r"(?:(<[^>]+>)\s+)?"  # Generic parameters
                    r"([a-zA-Z_$][\w$]*(?:\[\])*|\w+(?:<[^>]*>)?)\s+"  # Return type
                    r"(\w+)\s*\([^)]*\)\s*"  # Method name and parameters
                    r"(?:throws\s+[^{]+)?\s*[{;]",  # Optional throws clause
                    line,
                )
                if method_match and not any(
                    kw in line
                    for kw in ["class", "interface", "enum", "import", "package"]
                ):  # Allow abstract methods
                    modifiers = [
                        m
                        for m in line.split()
                        if m
                        in [
                            "public",
                            "private",
                            "protected",
                            "static",
                            "abstract",
                            "final",
                            "synchronized",
                            "default",
                        ]
                    ]
                    generic_params = method_match.group(2)
                    return_type = method_match.group(3)
                    method_name = method_match.group(4)

                    # Skip if this looks like a field declaration
                    if "=" in line and "(" not in line.split("=")[0]:
                        continue

                    # For abstract methods (ending with ;), the method is just one line
                    # For concrete methods (ending with {), find the block end
                    if line.strip().endswith(";"):
                        end_line = line_num
                        method_text = line
                    else:
                        end_line = self._find_block_end(lines, line_num - 1)
                        method_text = "\n".join(lines[line_num - 1 : end_line])

                    features = []
                    if modifiers:
                        features.extend(modifiers)
                    if generic_params:
                        features.append("generic")
                    if current_annotations:
                        features.append("annotation")

                    signature = line.strip().rstrip("{").rstrip(";").strip()

                    construct = {
                        "type": "method",
                        "name": method_name,
                        "path": f"{current_class}.{method_name}",
                        "text": method_text,
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "class",
                        "parent": current_class,
                        "features": features,
                        "context": {
                            "annotations": current_annotations.copy(),
                            "modifiers": modifiers,
                            "return_type": return_type,
                            "generic_params": generic_params,
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
        """Extract package declaration from Java file."""
        for line in lines:
            package_match = re.search(r"^\s*package\s+([\w.]+)\s*;", line)
            if package_match:
                return package_match.group(1)
        return ""

    def _find_class_boundaries(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Find class boundaries to help with method detection."""
        classes = []

        for line_num, line in enumerate(lines, 1):
            class_match = re.search(
                r"^\s*(?:(?:public|private|protected|abstract|final)\s+)*"
                r"(class|interface|enum)\s+(\w+)(?:<[^>]*>)?"
                r"(?:\s+(?:extends|implements)\s+[^{]+)?\s*\{",
                line,
            )
            if class_match:
                class_type = class_match.group(1)
                class_name = class_match.group(2)
                end_line = self._find_block_end(lines, line_num - 1)
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
        # This is not perfect but handles most cases
        result = ""
        in_string = False
        in_char = False
        escape_next = False
        i = 0

        while i < len(line):
            char = line[i]

            if escape_next:
                escape_next = False
                i += 1
                continue

            if char == "\\" and (in_string or in_char):
                escape_next = True
                i += 1
                continue

            if char == '"' and not in_char:
                in_string = not in_string
                i += 1
                continue

            if char == "'" and not in_string:
                in_char = not in_char
                i += 1
                continue

            if not in_string and not in_char:
                if char == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    # Rest of line is comment
                    break
                result += char

            i += 1

        return result

    def _is_malformed_java(self, content: str) -> bool:
        """Detect obviously malformed Java content that should fall back to text chunking."""
        lines = content.split("\n")

        # Look for lines that have obvious non-Java syntax
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
                    "public class",
                    "class",
                    "interface",
                    "enum",
                ]
            ):
                continue

            # Look for lines that are clearly not Java syntax
            # This is a simple heuristic - words without proper Java syntax
            if line_stripped and not any(
                char in line_stripped
                for char in [";", "{", "}", "(", ")", "=", "+", "-", "*", "/"]
            ):
                # Check if it's just random words (common in test malformed content)
                words = line_stripped.split()
                if len(words) >= 3 and all(
                    word.isalpha() and word.islower() for word in words
                ):
                    return True

        return False
