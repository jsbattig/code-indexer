"""
TypeScript semantic parser using regex-based parsing.

Extends the JavaScript parser to handle TypeScript-specific constructs
like interfaces, types, enums, and decorators.
"""

import re
from pathlib import Path
from typing import List, Dict, Any

from code_indexer.config import IndexingConfig
from code_indexer.indexing.javascript_parser import JavaScriptSemanticParser
from code_indexer.indexing.semantic_chunker import SemanticChunk


class TypeScriptSemanticParser(JavaScriptSemanticParser):
    """Semantic parser for TypeScript files."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config)
        self.language = "typescript"

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse TypeScript content and create semantic chunks."""
        chunks = []
        lines = content.split("\n")
        file_ext = Path(file_path).suffix

        # Find all constructs including TypeScript-specific ones
        js_constructs = self._find_constructs(content, lines, file_path)
        ts_constructs = self._find_typescript_constructs(content, lines)

        # Filter out the generic "module" construct if we have specific constructs
        filtered_js_constructs = []
        for construct in js_constructs:
            if construct["type"] == "module" and (
                ts_constructs or len(js_constructs) > 1
            ):
                continue  # Skip module construct if we have other specific constructs
            filtered_js_constructs.append(construct)

        # Combine and sort by line number
        all_constructs = filtered_js_constructs + ts_constructs
        all_constructs.sort(key=lambda x: x["line_start"])

        # Associate decorators with all constructs (both JS and TS)
        self._associate_decorators(lines, all_constructs)

        # If still no constructs, create a module chunk
        if not all_constructs:
            all_constructs = [
                {
                    "type": "module",
                    "name": Path(file_path).stem,
                    "text": content,
                    "line_start": 1,
                    "line_end": len(lines),
                    "signature": f"module {Path(file_path).stem}",
                    "scope": "global",
                    "features": ["typescript"],
                    "context": {},
                }
            ]

        # Create chunks from constructs
        for i, construct in enumerate(all_constructs):
            chunk = SemanticChunk(
                text=construct["text"],
                chunk_index=i,
                total_chunks=len(all_constructs),
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

    def _find_typescript_constructs(
        self, content: str, lines: List[str]
    ) -> List[Dict[str, Any]]:
        """Find TypeScript-specific constructs."""
        constructs = []

        # Patterns for TypeScript constructs
        patterns = {
            "interface": [
                r"^\s*interface\s+(\w+)(?:<[^>]*>)?\s*(?:extends\s+[^{]+)?\s*\{",
            ],
            "type": [
                r"^\s*type\s+(\w+)(?:<[^>]*>)?\s*=",
            ],
            "enum": [
                r"^\s*enum\s+(\w+)\s*\{",
                r"^\s*const\s+enum\s+(\w+)\s*\{",
            ],
            "decorator": [
                r"^\s*@(\w+)(?:\([^)]*\))?\s*$",
            ],
        }

        for line_num, line in enumerate(lines, 1):
            # Check for interfaces
            for pattern in patterns["interface"]:
                match = re.search(pattern, line)
                if match:
                    interface_name = match.group(1)
                    end_line = self._find_block_end(lines, line_num - 1)

                    # Extract generic parameters if present
                    generics = []
                    if "<" in line and ">" in line:
                        generic_match = re.search(r"<([^>]+)>", line)
                        if generic_match:
                            generics = [
                                g.strip() for g in generic_match.group(1).split(",")
                            ]

                    signature = line.strip()
                    if "{" in signature:
                        signature = signature[: signature.index("{")].strip()

                    construct = {
                        "type": "interface",
                        "name": interface_name,
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "global",
                        "features": ["typescript"] + (["generic"] if generics else []),
                        "context": {"generics": generics},
                    }
                    constructs.append(construct)
                    break

            # Check for type aliases
            for pattern in patterns["type"]:
                match = re.search(pattern, line)
                if match:
                    type_name = match.group(1)

                    # Find the complete type definition (may span multiple lines)
                    end_line = self._find_type_end(lines, line_num - 1)

                    # Extract generic parameters if present
                    generics = []
                    if "<" in line and ">" in line:
                        generic_match = re.search(r"<([^>]+)>", line)
                        if generic_match:
                            generics = [
                                g.strip() for g in generic_match.group(1).split(",")
                            ]

                    construct = {
                        "type": "type",
                        "name": type_name,
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": f"type {type_name}",
                        "scope": "global",
                        "features": ["typescript"] + (["generic"] if generics else []),
                        "context": {"generics": generics},
                    }
                    constructs.append(construct)
                    break

            # Check for enums
            for pattern in patterns["enum"]:
                match = re.search(pattern, line)
                if match:
                    enum_name = match.group(1)
                    end_line = self._find_block_end(lines, line_num - 1)

                    features = ["typescript"]
                    if "const enum" in line:
                        features.append("const")

                    signature = line.strip()
                    if "{" in signature:
                        signature = signature[: signature.index("{")].strip()

                    construct = {
                        "type": "enum",
                        "name": enum_name,
                        "text": "\n".join(lines[line_num - 1 : end_line]),
                        "line_start": line_num,
                        "line_end": end_line,
                        "signature": signature,
                        "scope": "global",
                        "features": features,
                        "context": {},
                    }
                    constructs.append(construct)
                    break

        return constructs

    def _find_type_end(self, lines: List[str], start_line: int) -> int:
        """Find the end of a type definition."""
        line = lines[start_line]

        # Simple type (one line)
        if ";" in line:
            return start_line + 1

        # Multi-line type definition
        brace_count = line.count("{") - line.count("}")
        paren_count = line.count("(") - line.count(")")
        angle_count = line.count("<") - line.count(">")

        if brace_count == 0 and paren_count == 0 and angle_count == 0:
            return start_line + 1

        for i in range(start_line + 1, len(lines)):
            line = lines[i]
            brace_count += line.count("{") - line.count("}")
            paren_count += line.count("(") - line.count(")")
            angle_count += line.count("<") - line.count(">")

            if (
                brace_count <= 0
                and paren_count <= 0
                and angle_count <= 0
                and (";" in line or "}" in line)
            ):
                return i + 1

        return len(lines)

    def _associate_decorators(
        self, lines: List[str], constructs: List[Dict[str, Any]]
    ) -> None:
        """Associate decorators with their target constructs."""
        # More flexible decorator patterns
        decorator_patterns = [
            r"^\s*@(\w+)\s*$",  # Simple decorator: @Input
            r"^\s*@(\w+)\([^)]*\)\s*$",  # Single-line decorator with args: @Input()
            r"^\s*@(\w+)\(",  # Multi-line decorator start: @Component({
        ]

        for line_num, line in enumerate(lines, 1):
            decorator_name = None

            # Check each pattern
            for pattern in decorator_patterns:
                match = re.search(pattern, line)
                if match:
                    decorator_name = match.group(1)
                    break

            # Also check for decorators followed by property/method declarations
            inline_decorator_match = re.search(
                r"^\s*@(\w+)(?:\([^)]*\))?\s+(\w+)", line
            )
            if inline_decorator_match:
                decorator_name = inline_decorator_match.group(1)

            if decorator_name:
                # Find the target construct
                target_line = None

                # For inline decorators (like @Input() user: User;), the target is on the same line
                if inline_decorator_match:
                    target_line = line_num
                else:
                    # Find the next non-decorator, non-empty line that looks like a construct
                    for i in range(line_num, len(lines)):
                        next_line = lines[i].strip()
                        if (
                            next_line
                            and not next_line.startswith("@")
                            and next_line not in ["})", "}", "})"]
                            and not next_line.endswith(",")
                            and not next_line.endswith(":")
                            and not next_line.startswith("'")
                            and not next_line.startswith('"')
                        ):
                            # Check if this line looks like a construct definition
                            if any(
                                keyword in next_line
                                for keyword in [
                                    "class",
                                    "function",
                                    "interface",
                                    "enum",
                                    "type",
                                ]
                            ):
                                target_line = i + 1
                                break

                if target_line:
                    # Find the construct that starts at or contains this line
                    for construct in constructs:
                        if (
                            construct["line_start"]
                            <= target_line
                            <= construct["line_end"]
                            or construct["line_start"] == target_line
                        ):
                            if "decorators" not in construct["context"]:
                                construct["context"]["decorators"] = []
                            if decorator_name not in construct["context"]["decorators"]:
                                construct["context"]["decorators"].append(
                                    decorator_name
                                )

                            # Add decorator to language features
                            if "decorator" not in construct["features"]:
                                construct["features"].append("decorator")
                            break

    def _find_constructs(
        self, content: str, lines: List[str], file_path: str = "unknown"
    ) -> List[Dict[str, Any]]:
        """Override to handle TypeScript-specific method signatures."""
        constructs = super()._find_constructs(content, lines, file_path)

        # Add TypeScript-specific method detection
        ts_methods = self._find_typescript_methods(content, lines)
        constructs.extend(ts_methods)

        # Enhance constructs with TypeScript type information
        for construct in constructs:
            if construct["type"] in ["function", "method"]:
                # Extract parameter and return types
                signature = construct.get("signature", "")
                if ": " in signature:
                    construct["features"].append("typed")

                # Extract generic parameters
                if "<" in signature and ">" in signature:
                    construct["features"].append("generic")

        return constructs  # type: ignore[no-any-return]

    def _find_typescript_methods(
        self, content: str, lines: List[str]
    ) -> List[Dict[str, Any]]:
        """Find TypeScript methods with return type annotations."""
        constructs = []

        # Find class boundaries to detect methods inside classes
        class_boundaries = self._find_class_boundaries(lines)

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

            # Only look for methods inside classes
            if current_class:
                # TypeScript method pattern with return types
                ts_method_match = re.search(
                    r"^\s*(?:(async|static|private|public|protected)\s+)?(async\s+)?(\w+)\s*\([^)]*\)\s*:\s*[^{]+\{",
                    line,
                )
                if ts_method_match and not any(
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
                        "constructor",  # Skip constructor, handled by JS parser
                    ]
                ):
                    # Extract modifiers and method name
                    modifier1 = ts_method_match.group(
                        1
                    )  # async/static/private/public/protected
                    modifier2 = ts_method_match.group(
                        2
                    )  # async (if first group wasn't async)
                    method_name = ts_method_match.group(3)

                    end_line = self._find_block_end(lines, line_num - 1)

                    features = []
                    if modifier1 == "async" or modifier2:
                        features.append("async")
                    if modifier1 == "static":
                        features.append("static")
                    if modifier1 in ["private", "public", "protected"]:
                        features.append(modifier1)

                    # Always add typed since TypeScript methods have type annotations
                    features.append("typed")

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

        return constructs
