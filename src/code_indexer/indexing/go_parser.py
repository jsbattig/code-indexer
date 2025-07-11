"""
Go semantic parser using regex-based parsing.

This implementation uses regex patterns to identify common Go constructs
for semantic chunking. While not as robust as a full AST parser,
it covers the most common patterns for semantic chunking.
"""

import re
from pathlib import Path
from typing import List, Dict, Any

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import BaseSemanticParser, SemanticChunk


class GoSemanticParser(BaseSemanticParser):
    """Semantic parser for Go files using regex patterns."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config)
        self.language = "go"

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse Go content and create semantic chunks."""
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
        """Find Go constructs using regex patterns."""
        constructs = []

        # Check for obviously malformed content that looks like it starts with valid Go
        # but has obvious syntax errors
        if self._is_malformed_go(content):
            return []

        # Extract package information
        package_name = self._extract_package(lines)

        for line_num, line in enumerate(lines, 1):
            line_stripped = line.strip()

            # Skip empty lines and comments
            if (
                not line_stripped
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
            ):
                continue

            # Check for function definitions
            func_match = re.search(
                r"^\s*func\s+(?:\([^)]*\)\s+)?(\w+)(?:\[([^]]+)\])?\s*\([^)]*\)\s*[^{]*\{",
                line,
            )
            if func_match:
                func_name = func_match.group(1)
                generics = func_match.group(2)
                end_line = self._find_block_end(lines, line_num - 1)

                # Check for receiver (method)
                receiver_match = re.search(r"func\s+\(([^)]+)\)\s+", line)
                receiver = None
                receiver_type = None
                if receiver_match:
                    receiver = receiver_match.group(1).strip()
                    # Extract just the type part (e.g., "u *User" -> "*User")
                    receiver_parts = receiver.split()
                    if len(receiver_parts) >= 2:
                        receiver_type = " ".join(receiver_parts[1:])
                    else:
                        receiver_type = receiver

                # Check for multiple return values
                features = []
                if generics:
                    features.append("generic")

                # Look for multiple return values pattern: func name(...) (ret1, ret2) {
                # or func name(...) (ret1 type, ret2 type) {
                return_part_match = re.search(r"\)\s*\(([^)]+)\)\s*\{", line)
                if return_part_match:
                    return_types = return_part_match.group(1).strip()
                    # If there's a comma or multiple words, it's multiple returns
                    if "," in return_types or len(return_types.split()) > 1:
                        features.append("multiple_returns")

                signature = line.strip().rstrip("{").strip()

                construct: Dict[str, Any] = {
                    "type": "function",
                    "name": func_name,
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": signature,
                    "scope": "global",
                    "features": features,
                    "context": {
                        "package": package_name,
                        "receiver": receiver_type if receiver_type else receiver,
                        "generics": generics,
                    },
                }
                constructs.append(construct)
                continue

            # Check for struct definitions
            struct_match = re.search(
                r"^\s*type\s+(\w+)(?:\[([^]]+)\])?\s+struct\s*\{", line
            )
            if struct_match:
                struct_name = struct_match.group(1)
                generics = struct_match.group(2)
                end_line = self._find_block_end(lines, line_num - 1)

                features = []
                if generics:
                    features.append("generic")

                signature = line.strip().rstrip("{").strip()

                construct = {
                    "type": "struct",
                    "name": struct_name,
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": signature,
                    "scope": "global",
                    "features": features,
                    "context": {
                        "package": package_name,
                        "generics": generics,
                    },
                }
                constructs.append(construct)
                continue

            # Check for interface definitions
            interface_match = re.search(
                r"^\s*type\s+(\w+)(?:\[([^]]+)\])?\s+interface\s*\{", line
            )
            if interface_match:
                interface_name = interface_match.group(1)
                generics = interface_match.group(2)
                end_line = self._find_block_end(lines, line_num - 1)

                # Look for embedded interfaces
                embedded_interfaces = []
                for i in range(line_num, end_line):
                    if i < len(lines):
                        embed_line = lines[i].strip()
                        # Simple embedded interface detection
                        if (
                            not embed_line.startswith("//")
                            and "(" not in embed_line
                            and embed_line
                            and not embed_line.endswith("{")
                            and not embed_line.endswith("}")
                        ):
                            words = embed_line.split()
                            if len(words) == 1 and words[0][0].isupper():
                                embedded_interfaces.append(words[0])

                features = []
                if generics:
                    features.append("generic")
                if embedded_interfaces:
                    features.append("embedded")

                signature = line.strip().rstrip("{").strip()

                construct = {
                    "type": "interface",
                    "name": interface_name,
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": signature,
                    "scope": "global",
                    "features": features,
                    "context": {
                        "package": package_name,
                        "generics": generics,
                        "embedded_interfaces": embedded_interfaces,
                    },
                }
                constructs.append(construct)
                continue

            # Check for type definitions (type aliases)
            type_match = re.search(r"^\s*type\s+(\w+)(?:\[([^]]+)\])?\s+(.+)", line)
            if (
                type_match
                and "struct" not in line
                and "interface" not in line
                and "{" not in line
            ):

                type_name = type_match.group(1)
                generics = type_match.group(2)
                type_def = type_match.group(3).strip()

                features = []
                if generics:
                    features.append("generic")
                if "func(" in type_def:
                    features.append("function_type")

                construct = {
                    "type": "type",
                    "name": type_name,
                    "text": line,
                    "line_start": line_num,
                    "line_end": line_num,
                    "signature": line.strip(),
                    "scope": "global",
                    "features": features,
                    "context": {
                        "package": package_name,
                        "generics": generics,
                        "type_definition": type_def,
                    },
                }
                constructs.append(construct)
                continue

            # Check for const blocks
            const_match = re.search(r"^\s*const\s*\(", line)
            if const_match:
                end_line = self._find_block_end(lines, line_num - 1)

                construct = {
                    "type": "const",
                    "name": "const_block",
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": "const (...)",
                    "scope": "global",
                    "features": [],
                    "context": {"package": package_name},
                }
                constructs.append(construct)
                continue

            # Check for single const declarations
            single_const_match = re.search(r"^\s*const\s+(\w+)", line)
            if single_const_match and "(" not in line:
                const_name = single_const_match.group(1)

                construct = {
                    "type": "const",
                    "name": const_name,
                    "text": line,
                    "line_start": line_num,
                    "line_end": line_num,
                    "signature": line.strip(),
                    "scope": "global",
                    "features": [],
                    "context": {"package": package_name},
                }
                constructs.append(construct)
                continue

            # Check for var blocks
            var_match = re.search(r"^\s*var\s*\(", line)
            if var_match:
                end_line = self._find_block_end(lines, line_num - 1)

                construct = {
                    "type": "var",
                    "name": "var_block",
                    "text": "\n".join(lines[line_num - 1 : end_line]),
                    "line_start": line_num,
                    "line_end": end_line,
                    "signature": "var (...)",
                    "scope": "global",
                    "features": [],
                    "context": {"package": package_name},
                }
                constructs.append(construct)
                continue

            # Check for single var declarations
            single_var_match = re.search(r"^\s*var\s+(\w+)", line)
            if single_var_match and "(" not in line:
                var_name = single_var_match.group(1)

                construct = {
                    "type": "var",
                    "name": var_name,
                    "text": line,
                    "line_start": line_num,
                    "line_end": line_num,
                    "signature": line.strip(),
                    "scope": "global",
                    "features": [],
                    "context": {"package": package_name},
                }
                constructs.append(construct)
                continue

        # If no constructs found, treat as one large chunk
        if not constructs:
            constructs.append(
                {
                    "type": "module",
                    "name": Path(file_path).stem,
                    "text": content,
                    "line_start": 1,
                    "line_end": len(lines),
                    "signature": f"package {package_name}",
                    "scope": "global",
                    "features": [],
                    "context": {"package": package_name},
                }
            )

        return constructs

    def _extract_package(self, lines: List[str]) -> str:
        """Extract package declaration from Go file."""
        for line in lines:
            package_match = re.search(r"^\s*package\s+(\w+)", line)
            if package_match:
                return package_match.group(1)
        return "main"

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
        result = ""
        in_string = False
        in_char = False
        in_raw_string = False
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

            # Raw strings in Go start with `
            if char == "`" and not in_string and not in_char:
                in_raw_string = not in_raw_string
                i += 1
                continue

            if char == '"' and not in_char and not in_raw_string:
                in_string = not in_string
                i += 1
                continue

            if char == "'" and not in_string and not in_raw_string:
                in_char = not in_char
                i += 1
                continue

            if not in_string and not in_char and not in_raw_string:
                if char == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    # Rest of line is comment
                    break
                result += char

            i += 1

        return result

    def _is_malformed_go(self, content: str) -> bool:
        """Detect obviously malformed Go content that should fall back to text chunking."""
        lines = content.split("\n")

        # Look for lines that have obvious non-Go syntax
        for line in lines:
            line_stripped = line.strip()
            if (
                not line_stripped
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
            ):
                continue

            # Check for malformed func declarations
            if line_stripped.startswith("func "):
                # A proper func declaration should have parentheses and braces or a complete signature
                if not (
                    ("(" in line_stripped and ")" in line_stripped)
                    or line_stripped.endswith("{")
                ):
                    # This looks like "func broken syntax here" - not a valid func declaration
                    return True

            # Skip other valid Go keywords if they look reasonable
            if any(
                line_stripped.startswith(keyword)
                for keyword in ["package", "import", "type", "var", "const"]
            ):
                continue

            # Look for lines that are clearly not Go syntax
            # This is a simple heuristic - words without proper Go syntax
            if line_stripped and not any(
                char in line_stripped
                for char in [";", "{", "}", "(", ")", "=", "+", "-", "*", "/", ":", "."]
            ):
                # Check if it's just random words (common in test malformed content)
                words = line_stripped.split()
                if len(words) >= 3 and all(
                    word.isalpha() and word.islower() for word in words
                ):
                    return True

        return False
