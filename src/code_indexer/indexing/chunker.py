"""Text chunking utilities for breaking large files into manageable pieces."""

import re
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from ..config import IndexingConfig


class TextChunker:
    """Handles chunking of text content."""

    def __init__(self, config: IndexingConfig):
        self.config = config
        self.chunk_size = config.chunk_size
        self.chunk_overlap = config.chunk_overlap

    def _get_language_splitters(self, file_extension: str) -> List[str]:
        """Get appropriate text splitters based on file type."""
        language_splitters = {
            # Programming languages
            "py": [
                # Use more complete patterns to avoid tiny fragments
                r"\n\ndef [a-zA-Z_][a-zA-Z0-9_]*",  # Complete function definitions (including underscores)
                r"\n\nclass [a-zA-Z_][a-zA-Z0-9_]*",  # Complete class definitions (including underscores)
                r"\n\nasync def [a-zA-Z_][a-zA-Z0-9_]*",  # Complete async function definitions
                r"\n# [A-Z][^\\n]{10,}",  # Substantial comment sections (10+ chars, starting with capital)
                r"\nif __name__",  # Main execution blocks
                # Remove docstring splitters that create fragments
                # r'\n"""',  # REMOVED - creates tiny fragments
                # r"\n'''",  # REMOVED - creates tiny fragments
            ],
            "js": [
                r"\nfunction ",
                r"\nconst ",
                r"\nlet ",
                r"\nvar ",
                r"\nclass ",
                r"\n// ",
                r"\n/*",
            ],
            "ts": [
                r"\nfunction ",
                r"\nconst ",
                r"\nlet ",
                r"\nvar ",
                r"\nclass ",
                r"\ninterface ",
                r"\ntype ",
                r"\n// ",
                r"\n/*",
            ],
            "tsx": [
                r"\nfunction ",
                r"\nconst ",
                r"\nlet ",
                r"\nvar ",
                r"\nclass ",
                r"\ninterface ",
                r"\ntype ",
                r"\nexport ",
                r"\n// ",
                r"\n/*",
            ],
            "jsx": [
                r"\nfunction ",
                r"\nconst ",
                r"\nlet ",
                r"\nvar ",
                r"\nclass ",
                r"\nexport ",
                r"\n// ",
                r"\n/*",
            ],
            "java": [
                r"\npublic class ",
                r"\nprivate class ",
                r"\nprotected class ",
                r"\npublic interface ",
                r"\npublic enum ",
                r"\n// ",
                r"\n/*",
            ],
            "c": [
                r"\n#include",
                r"\n#define",
                r"\nint ",
                r"\nvoid ",
                r"\nstatic ",
                r"\n// ",
                r"\n/*",
            ],
            "cpp": [
                r"\n#include",
                r"\n#define",
                r"\nclass ",
                r"\nnamespace ",
                r"\nint ",
                r"\nvoid ",
                r"\nstatic ",
                r"\n// ",
                r"\n/*",
            ],
            "h": [
                r"\n#include",
                r"\n#define",
                r"\n#ifndef",
                r"\n#ifdef",
                r"\ntypedef ",
                r"\nstruct ",
                r"\n// ",
                r"\n/*",
            ],
            "hpp": [
                r"\n#include",
                r"\n#define",
                r"\n#ifndef",
                r"\n#ifdef",
                r"\nclass ",
                r"\nnamespace ",
                r"\ntypedef ",
                r"\n// ",
                r"\n/*",
            ],
            "go": [
                r"\nfunc ",
                r"\ntype ",
                r"\nvar ",
                r"\nconst ",
                r"\npackage ",
                r"\nimport ",
                r"\n// ",
                r"\n/*",
            ],
            "rs": [
                r"\nfn ",
                r"\nstruct ",
                r"\nenum ",
                r"\nimpl ",
                r"\ntrait ",
                r"\nmod ",
                r"\nuse ",
                r"\n// ",
                r"\n/*",
            ],
            "rb": [r"\ndef ", r"\nclass ", r"\nmodule ", r"\n# "],
            "php": [
                r"\nfunction ",
                r"\nclass ",
                r"\ninterface ",
                r"\ntrait ",
                r"\n// ",
                r"\n/*",
            ],
            "sh": [r"\nfunction ", r"\n# "],
            "bash": [r"\nfunction ", r"\n# "],
            # Markup and config
            "html": [
                r"\n<div",
                r"\n<section",
                r"\n<article",
                r"\n<header",
                r"\n<footer",
                r"\n<nav",
                r"\n<!-- ",
            ],
            "css": [r"\n\.", r"\n#", r"\n@media", r"\n@import", r"\n/* "],
            "md": [r"\n# ", r"\n## ", r"\n### ", r"\n#### ", r"\n```"],
            "json": [r'\n  "', r'\n    "'],
            "yaml": [r"\n[a-zA-Z]", r"\n- "],
            "yml": [r"\n[a-zA-Z]", r"\n- "],
            "toml": [r"\n\[", r"\n[a-zA-Z]"],
            "sql": [
                r"\nSELECT",
                r"\nINSERT",
                r"\nUPDATE",
                r"\nDELETE",
                r"\nCREATE",
                r"\nALTER",
                r"\nDROP",
                r"\n-- ",
            ],
        }

        return language_splitters.get(file_extension.lower(), [r"\n\n", r"\n"])

    def _smart_split(self, text: str, file_extension: str) -> List[str]:
        """Split text using language-aware delimiters."""
        splitters = self._get_language_splitters(file_extension)

        # Start with the full text
        chunks = [text]

        # Apply each splitter in order
        for splitter in splitters:
            new_chunks = []
            for chunk in chunks:
                if len(chunk) <= self.chunk_size:
                    new_chunks.append(chunk)
                else:
                    # Split using current splitter
                    parts = re.split(f"({splitter})", chunk, flags=re.MULTILINE)

                    current_chunk = ""
                    for part in parts:
                        if len(current_chunk + part) <= self.chunk_size:
                            current_chunk += part
                        else:
                            if current_chunk:
                                new_chunks.append(current_chunk)
                            current_chunk = part

                    if current_chunk:
                        new_chunks.append(current_chunk)

            chunks = new_chunks

        return [chunk for chunk in chunks if chunk.strip()]

    def _smart_split_with_lines(
        self, text: str, text_lines: List[str], file_extension: str
    ) -> List[Dict[str, Any]]:
        """Split text using language-aware delimiters while tracking line numbers."""
        chunk_data = []
        current_line_idx = 0  # 0-based index into text_lines

        while current_line_idx < len(text_lines):
            # Determine chunk boundaries
            chunk_start_line = current_line_idx + 1  # 1-based line number
            chunk_lines_count = 0
            current_chunk_size = 0

            # Track if we're in a multi-line construct
            in_multiline_construct = False
            multiline_start_idx = None
            construct_type = ""

            # Check if we're starting in the middle of a string continuation
            if current_line_idx > 0:
                line = text_lines[current_line_idx]
                line_stripped = line.strip()

                # If this line starts with a string continuation, look back
                if (
                    line_stripped.startswith('f"')
                    or line_stripped.startswith('"')
                    or line_stripped.startswith("'")
                    or (
                        line_stripped
                        and line_stripped[0] in "fF"
                        and len(line_stripped) > 1
                        and line_stripped[1] in "\"'"
                    )
                ):
                    # Look backward to find the start of the construct
                    look_back_idx = current_line_idx - 1
                    while look_back_idx >= 0:
                        prev_line = text_lines[look_back_idx]
                        if self._is_multiline_construct_start(
                            prev_line, text_lines, look_back_idx, file_extension
                        )[0]:
                            # Found the start, adjust our starting position
                            current_line_idx = look_back_idx
                            chunk_start_line = current_line_idx + 1
                            break
                        look_back_idx -= 1

            # Add lines until we reach size limit or find a good break point
            temp_line_idx = current_line_idx
            while (
                temp_line_idx < len(text_lines) and current_chunk_size < self.chunk_size
            ):
                line = text_lines[temp_line_idx]
                line_size = len(line) + 1  # +1 for newline (except last line)
                if temp_line_idx == len(text_lines) - 1 and not text.endswith("\n"):
                    line_size = len(line)  # Last line without newline

                # Check if we're entering or in a multi-line construct
                if not in_multiline_construct:
                    in_multiline_construct, construct_type = (
                        self._is_multiline_construct_start(
                            line, text_lines, temp_line_idx, file_extension
                        )
                    )
                    if in_multiline_construct:
                        multiline_start_idx = temp_line_idx

                # Check if we're exiting a multi-line construct
                if in_multiline_construct:
                    if self._is_multiline_construct_end(
                        line, text_lines, temp_line_idx, construct_type, file_extension
                    ):
                        in_multiline_construct = False
                        multiline_start_idx = None

                # Check if adding this line would exceed chunk size
                if (
                    current_chunk_size + line_size > self.chunk_size
                    and chunk_lines_count > 0
                ):
                    # Before breaking, check if this line starts a new multi-line construct
                    # Even if we're not currently in one, we should look ahead
                    if not in_multiline_construct:
                        will_start_construct, construct_type = (
                            self._is_multiline_construct_start(
                                line, text_lines, temp_line_idx, file_extension
                            )
                        )
                        if will_start_construct:
                            # Calculate size of the upcoming construct
                            upcoming_construct_size = self._calculate_construct_size(
                                text_lines,
                                temp_line_idx,
                                temp_line_idx,
                                file_extension,
                            )
                            max_construct_size = (
                                self.chunk_size * 2.5
                                if file_extension == "java"
                                else self.chunk_size * 1.5
                            )

                            # If the construct is reasonable size, start it in this chunk
                            if upcoming_construct_size < max_construct_size:
                                in_multiline_construct = True
                                multiline_start_idx = temp_line_idx

                    # If we're in a multi-line construct, try to keep it together
                    if in_multiline_construct and multiline_start_idx is not None:
                        # Calculate the size of the entire construct
                        construct_size = self._calculate_construct_size(
                            text_lines,
                            multiline_start_idx,
                            temp_line_idx,
                            file_extension,
                        )

                        # If the construct is reasonable size, include it entirely
                        # Be more generous for Java string concatenations
                        max_construct_size = (
                            self.chunk_size * 2.5
                            if file_extension == "java"
                            else self.chunk_size * 1.5
                        )
                        if construct_size < max_construct_size:
                            # Continue to include the construct
                            pass
                        else:
                            # Construct is too large, check for break point
                            if self._is_good_break_point(line, file_extension):
                                break
                            elif current_chunk_size + line_size > self.chunk_size * 1.5:
                                break
                    else:
                        # Not in multi-line construct, check for natural break points
                        if self._is_good_break_point(line, file_extension):
                            break
                        # If we're way over the limit, break anyway
                        elif current_chunk_size + line_size > self.chunk_size * 1.2:
                            break

                current_chunk_size += line_size
                chunk_lines_count += 1
                temp_line_idx += 1

            # Ensure we have at least one line
            if chunk_lines_count == 0 and current_line_idx < len(text_lines):
                chunk_lines_count = 1

            if chunk_lines_count > 0:
                chunk_end_line = chunk_start_line + chunk_lines_count - 1

                # Extract the exact text for this line range
                chunk_text = self._extract_line_range(
                    text, text_lines, chunk_start_line, chunk_end_line
                )

                chunk_data.append(
                    {
                        "text": chunk_text,
                        "line_start": chunk_start_line,
                        "line_end": chunk_end_line,
                    }
                )

                # Move to next chunk with overlap
                # Don't create overlap if we've processed all the content
                if temp_line_idx >= len(text_lines):
                    break

                # Be smarter about overlap - avoid starting in the middle of constructs
                overlap_lines = min(
                    self.chunk_overlap // 50,  # Estimate lines from character overlap
                    chunk_lines_count // 4,  # Or 25% of current chunk
                    5,  # But no more than 5 lines
                )

                # Adjust the next starting position
                next_start = current_line_idx + chunk_lines_count - overlap_lines

                # Check if the next start would be in the middle of a construct
                if next_start < len(text_lines):
                    next_line = text_lines[next_start]
                    next_line_stripped = next_line.strip()

                    # If next line is a string continuation, find a better break
                    if (
                        next_line_stripped.startswith('f"')
                        or next_line_stripped.startswith('"')
                        or next_line_stripped.startswith("'")
                    ):
                        # Look for a better starting point
                        better_start = next_start
                        for idx in range(next_start - 1, current_line_idx, -1):
                            if self._is_good_break_point(
                                text_lines[idx], file_extension
                            ):
                                better_start = idx + 1
                                break
                        next_start = better_start

                current_line_idx = max(current_line_idx + 1, next_start)
            else:
                break

        return chunk_data

    def _extract_line_range(
        self, original_text: str, text_lines: List[str], start_line: int, end_line: int
    ) -> str:
        """Extract the exact text for a range of lines, preserving original structure."""
        # Convert to 0-based indices
        start_idx = start_line - 1
        end_idx = end_line - 1

        if start_idx < 0 or end_idx >= len(text_lines):
            return ""

        # Get the lines
        lines = text_lines[start_idx : end_idx + 1]

        # Reconstruct exactly as in original
        if not lines:
            return ""

        result = "\n".join(lines)

        # Add final newline if:
        # 1. This is not the last line of the file, OR
        # 2. This is the last line and original file ended with newline
        if end_line < len(text_lines) or original_text.endswith("\n"):
            result += "\n"

        return result

    def _is_good_break_point(self, line: str, file_extension: str) -> bool:
        """Check if this line is a good place to break a chunk."""
        line_stripped = line.strip()

        # Never break on string continuations or certain patterns
        # Common patterns that indicate we're in the middle of something
        bad_break_patterns = [
            '",',
            '"),',
            '";',
            '");',
            "',",
            "'),",
            "';",
            "');",  # String endings with continuation
            "},",
            "],",
            "),",  # Object/array/call endings with continuation
            "||",
            "&&",  # Logical operators
            "+",
            "-",
            "*",
            "/",
            "%",  # Math operators at end of line
            "=",
            "+=",
            "-=",
            "*=",
            "/=",  # Assignment operators
            ".",  # Member access
        ]

        for pattern in bad_break_patterns:
            if line_stripped.endswith(pattern):
                return False

        # Language-specific checks
        if file_extension == "py":
            # Never break on string continuations
            if (
                line_stripped.startswith('f"')
                or line_stripped.startswith('"')
                or line_stripped.startswith("'")
                or (
                    line_stripped
                    and line_stripped[0] in "fF"
                    and len(line_stripped) > 1
                    and line_stripped[1] in "\"'"
                )
            ):
                return False

            # Good Python break points
            return (
                line_stripped.startswith("def ")
                or line_stripped.startswith("class ")
                or line_stripped.startswith("async def ")
                or line_stripped.startswith("if __name__")
                or (line_stripped.startswith("#") and len(line_stripped) > 10)
                or line_stripped == ""  # Empty lines are good break points
                or line_stripped.startswith("import ")
                or line_stripped.startswith("from ")
                or line_stripped.startswith("@")  # Decorators
            )

        elif file_extension in ["js", "ts", "jsx", "tsx"]:
            # Never break on template literal continuations
            if line_stripped.startswith("`") or line_stripped.endswith("`"):
                return False

            return (
                line_stripped.startswith("function ")
                or line_stripped.startswith("const ")
                or line_stripped.startswith("let ")
                or line_stripped.startswith("var ")
                or line_stripped.startswith("class ")
                or line_stripped.startswith("export ")
                or line_stripped.startswith("import ")
                or line_stripped.startswith("interface ")  # TypeScript
                or line_stripped.startswith("type ")  # TypeScript
                or line_stripped.startswith("enum ")  # TypeScript
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
                or line_stripped == ""
            )

        elif file_extension == "java":
            return (
                line_stripped.startswith("public ")
                or line_stripped.startswith("private ")
                or line_stripped.startswith("protected ")
                or line_stripped.startswith("class ")
                or line_stripped.startswith("interface ")
                or line_stripped.startswith("enum ")
                or line_stripped.startswith("@")  # Annotations
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
                or line_stripped == ""
            )

        elif file_extension == "go":
            return (
                line_stripped.startswith("func ")
                or line_stripped.startswith("type ")
                or line_stripped.startswith("var ")
                or line_stripped.startswith("const ")
                or line_stripped.startswith("package ")
                or line_stripped.startswith("import ")
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
                or line_stripped == ""
            )

        elif file_extension in ["c", "cpp", "h", "hpp"]:
            return (
                line_stripped.startswith("int ")
                or line_stripped.startswith("void ")
                or line_stripped.startswith("class ")  # C++
                or line_stripped.startswith("struct ")
                or line_stripped.startswith("namespace ")  # C++
                or line_stripped.startswith("#")  # Preprocessor
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
                or line_stripped == ""
            )

        elif file_extension == "rs":  # Rust
            return (
                line_stripped.startswith("fn ")
                or line_stripped.startswith("pub ")
                or line_stripped.startswith("struct ")
                or line_stripped.startswith("enum ")
                or line_stripped.startswith("impl ")
                or line_stripped.startswith("trait ")
                or line_stripped.startswith("mod ")
                or line_stripped.startswith("use ")
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
                or line_stripped == ""
            )

        else:
            # Generic break points
            return (
                line_stripped == ""
                or line_stripped.startswith("#")
                or line_stripped.startswith("//")
                or line_stripped.startswith("/*")
                # Avoid breaking on obvious continuations
                and not any(line_stripped.endswith(p) for p in bad_break_patterns)
            )

    def _is_multiline_construct_start(
        self, line: str, text_lines: List[str], line_idx: int, file_extension: str
    ) -> Tuple[bool, str]:
        """Check if this line starts a multi-line construct that should be kept together."""
        line_stripped = line.strip()

        # Common patterns across languages
        # Check for unclosed parentheses, brackets, or braces
        open_parens = line.count("(")
        close_parens = line.count(")")
        open_brackets = line.count("[")
        close_brackets = line.count("]")
        open_braces = line.count("{")
        close_braces = line.count("}")

        # Check if we have unclosed delimiters
        unclosed_parens = open_parens > close_parens
        unclosed_brackets = open_brackets > close_brackets
        unclosed_braces = open_braces > close_braces

        # Language-specific checks
        if file_extension == "py":
            # Check for multi-line strings
            if '"""' in line or "'''" in line:
                # Count quotes to see if string closes on same line
                triple_double = line.count('"""')
                triple_single = line.count("'''")
                if triple_double % 2 == 1 or triple_single % 2 == 1:
                    return True, "string"

            # Check for multi-line statements (raise, assert, etc.)
            if any(line_stripped.startswith(kw + " ") for kw in ["raise", "assert"]):
                if unclosed_parens:
                    return True, "statement"

            # Check for function calls that span multiple lines
            if unclosed_parens and not line_stripped.startswith("def "):
                return True, "call"

            # Check for f-string/string that continues on next line
            if line_idx + 1 < len(text_lines):
                next_line = text_lines[line_idx + 1].strip()
                # Check if current line has unclosed string and next line continues it
                if (line_stripped.endswith("(") or line_stripped.endswith(",")) and (
                    next_line.startswith('f"')
                    or next_line.startswith('"')
                    or next_line.startswith("'")
                    or next_line.startswith("f'")
                ):
                    return True, "multistring"

        elif file_extension in ["js", "ts", "jsx", "tsx"]:
            # Template literals (backticks)
            backtick_count = line.count("`")
            if backtick_count % 2 == 1:
                return True, "template"

            # JSX elements that span multiple lines
            if file_extension in ["jsx", "tsx"]:
                # Check for unclosed JSX tags
                if "<" in line and ">" in line:
                    # Simple check for self-closing tags
                    if "/>" not in line and unclosed_parens:
                        return True, "jsx"

            # Object literals, arrays, function calls
            if unclosed_braces or unclosed_brackets or unclosed_parens:
                if any(
                    kw in line_stripped for kw in ["throw new", "new Error", "console."]
                ):
                    return True, "statement"
                return True, "expression"

        elif file_extension == "java":
            # Check for annotations that span multiple lines
            if line_stripped.startswith("@") and unclosed_parens:
                return True, "annotation"

            # Exception throwing with multi-line messages
            if "throw new" in line and unclosed_parens:
                return True, "exception"

            # String concatenation patterns in Java
            if line_stripped.endswith(" +") or line_stripped.endswith(" + "):
                return True, "string_concat"

            # Check if current line is part of string concatenation
            if line_stripped.startswith('"') and (
                line_stripped.endswith(" +") or line_stripped.endswith(" + ")
            ):
                return True, "string_concat"

            # Check if we're continuing a string concatenation from previous line
            if line_idx > 0:
                prev_line = text_lines[line_idx - 1].strip()
                if (
                    prev_line.endswith(" +") or prev_line.endswith(" + ")
                ) and line_stripped.startswith('"'):
                    return True, "string_concat"

            # Method calls, constructors
            if unclosed_parens:
                return True, "call"

        elif file_extension == "go":
            # Go error formatting
            if "fmt.Errorf(" in line or "errors.New(" in line:
                if unclosed_parens:
                    return True, "error"

            # Struct literals
            if unclosed_braces and "{" in line:
                return True, "struct"

            # Function calls
            if unclosed_parens:
                return True, "call"

        elif file_extension in ["c", "cpp", "h", "hpp"]:
            # Preprocessor directives
            if line_stripped.startswith("#") and line_stripped.endswith("\\"):
                return True, "preprocessor"

            # Function calls, initializers
            if unclosed_parens or unclosed_braces:
                return True, "expression"

        elif file_extension in ["rs"]:  # Rust
            # Rust macros
            if "!" in line and unclosed_parens:
                return True, "macro"

            # Match expressions, closures
            if unclosed_braces:
                return True, "expression"

        # Generic check for any language
        if unclosed_parens or unclosed_brackets or unclosed_braces:
            # Check if next line continues the construct
            if line_idx + 1 < len(text_lines):
                next_line = text_lines[line_idx + 1].strip()
                # If next line is indented or starts with certain characters
                if next_line and (
                    next_line[0] in "\"'}])|,"
                    or next_line.startswith("    ")  # Indented continuation
                    or next_line.startswith("\t")  # Tab indented
                ):
                    return True, "construct"

        return False, ""

    def _is_multiline_construct_end(
        self,
        line: str,
        text_lines: List[str],
        line_idx: int,
        construct_type: str,
        file_extension: str,
    ) -> bool:
        """Check if this line ends a multi-line construct."""
        line_stripped = line.strip()

        # Count delimiters in current line
        open_parens = line.count("(")
        close_parens = line.count(")")
        open_brackets = line.count("[")
        close_brackets = line.count("]")
        open_braces = line.count("{")
        close_braces = line.count("}")

        # Common patterns across languages
        if construct_type in ["call", "statement", "expression", "construct"]:
            # Check if we have more closing delimiters
            if (
                close_parens > open_parens
                or close_brackets > open_brackets
                or close_braces > open_braces
            ):
                return True

            # Check common ending patterns
            if any(
                line_stripped.endswith(end)
                for end in [")", ");", "),", "]", "];", "],", "}", "};", "},"]
            ):
                return True

        # Language-specific checks
        if file_extension == "py":
            if construct_type == "string":
                # Check for closing triple quotes
                return '"""' in line or "'''" in line

            elif construct_type == "multistring":
                # Check if multi-line f-string/string ends
                return (
                    line_stripped.endswith('"')
                    or line_stripped.endswith('")')
                    or line_stripped.endswith('",')
                    or line_stripped.endswith("'")
                    or line_stripped.endswith("')")
                    or line_stripped.endswith("',")
                )

        elif file_extension in ["js", "ts", "jsx", "tsx"]:
            if construct_type == "template":
                # Check for closing backtick
                backtick_count = line.count("`")
                return backtick_count % 2 == 1

            elif construct_type == "jsx":
                # Check for closing JSX tag
                if "/>" in line or (close_parens > open_parens and ">" in line):
                    return True

        elif file_extension == "java":
            if construct_type == "annotation":
                # Annotations typically end with )
                return line_stripped.endswith(")")

            elif construct_type == "exception":
                # Exception messages typically end with ); or )
                return line_stripped.endswith(");") or line_stripped.endswith(")")

            elif construct_type == "string_concat":
                # String concatenation ends when line doesn't end with +
                return not (
                    line_stripped.endswith(" +") or line_stripped.endswith(" + ")
                )

        elif file_extension == "go":
            if construct_type == "error":
                # Go errors typically end with )
                return line_stripped.endswith(")")

            elif construct_type == "struct":
                # Struct literals end with }
                return line_stripped.endswith("}") or line_stripped.endswith("},")

        elif file_extension in ["c", "cpp", "h", "hpp"]:
            if construct_type == "preprocessor":
                # Preprocessor continues if line ends with \
                return not line_stripped.endswith("\\")

        elif file_extension == "rs":
            if construct_type == "macro":
                # Rust macros end with ) or ];
                return line_stripped.endswith(")") or line_stripped.endswith("];")

        # Default check - if the line doesn't look like a continuation
        if line_idx + 1 < len(text_lines):
            next_line = text_lines[line_idx + 1].strip()
            # If next line doesn't look like a continuation
            if next_line and not any(
                [
                    next_line[0] in "\"'}])|,",
                    next_line.startswith("    "),  # Indented
                    next_line.startswith("\t"),  # Tab indented
                    next_line.startswith("."),  # Method chaining
                ]
            ):
                return True

        return False

    def _calculate_construct_size(
        self,
        text_lines: List[str],
        start_idx: int,
        current_idx: int,
        file_extension: str,
    ) -> int:
        """Calculate the size of a multi-line construct by finding its end."""
        size = 0

        # Look ahead to find the actual end of the construct
        construct_type = ""
        max_look_ahead = min(start_idx + 50, len(text_lines))  # Look ahead more lines

        for i in range(start_idx, max_look_ahead):
            line = text_lines[i]
            size += len(line) + 1  # +1 for newline

            # Try to determine construct type from first line if not set
            if i == start_idx and not construct_type:
                line_stripped = line.strip()
                if "throw new" in line:
                    construct_type = "exception"
                elif line_stripped.endswith(" +"):
                    construct_type = "string_concat"
                else:
                    construct_type = "generic"

            # Check if construct ends at this line
            if i > start_idx and self._is_multiline_construct_end(
                line, text_lines, i, construct_type, file_extension
            ):
                break

            # Safety valve - if we've gone too far, break
            if size > self.chunk_size * 3:
                break

        return size

    def _fallback_split_with_lines(
        self, text: str, start_line: int, text_lines: List[str]
    ) -> List[Dict[str, Any]]:
        """Fallback splitting when smart splitting doesn't work well, with line tracking."""
        # Split the text into lines and process line by line
        lines = text.splitlines()
        chunk_data = []
        current_line = 0

        while current_line < len(lines):
            chunk_lines: List[str] = []
            chunk_start_line = start_line + current_line
            current_chunk_size = 0

            # Add lines until we reach the chunk size limit
            while current_line < len(lines) and current_chunk_size < self.chunk_size:
                line = lines[current_line]
                line_with_newline = (
                    line + "\n" if current_line < len(lines) - 1 else line
                )

                # If adding this line would greatly exceed the limit, break
                if (
                    current_chunk_size + len(line_with_newline) > self.chunk_size * 1.2
                    and chunk_lines
                ):
                    break

                chunk_lines.append(line)
                current_chunk_size += len(line_with_newline)
                current_line += 1

            # If we didn't collect any lines, take at least one
            if not chunk_lines and current_line < len(lines):
                chunk_lines.append(lines[current_line])
                current_line += 1

            if chunk_lines:
                chunk_text = "\n".join(chunk_lines)
                chunk_end_line = chunk_start_line + len(chunk_lines) - 1

                chunk_data.append(
                    {
                        "text": chunk_text,
                        "line_start": chunk_start_line,
                        "line_end": chunk_end_line,
                    }
                )

                # Add overlap by backing up some lines
                if current_line < len(lines):
                    overlap_lines = min(
                        self.chunk_overlap
                        // 50,  # Estimate lines from character overlap
                        len(chunk_lines) // 4,  # Or 25% of current chunk
                        3,  # But no more than 3 lines for fallback
                    )
                    current_line = max(
                        current_line - overlap_lines, chunk_start_line - start_line + 1
                    )

        return chunk_data

    def _fallback_split(self, text: str) -> List[str]:
        """Fallback splitting when smart splitting doesn't work well."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            if end >= len(text):
                chunks.append(text[start:])
                break

            # Try to find a good break point
            break_point = end

            # Look for natural break points within overlap distance
            search_start = max(end - self.chunk_overlap, start + 1)

            for pos in range(end, search_start - 1, -1):
                if text[pos] in "\n\r":
                    break_point = pos + 1
                    break
                elif text[pos] in " \t":
                    break_point = pos + 1
                    break

            chunks.append(text[start:break_point])
            start = (
                break_point - self.chunk_overlap
                if break_point > start + self.chunk_overlap
                else break_point
            )

        return chunks

    def chunk_text(
        self, text: str, file_path: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """Split text into chunks with metadata including line numbers."""
        if not text or not text.strip():
            return []

        # Determine file extension for smart splitting
        file_extension = ""
        if file_path:
            file_extension = file_path.suffix.lstrip(".")

        # Split text into lines for line tracking
        text_lines = text.splitlines()

        # Create chunks with line position tracking
        chunk_data = self._smart_split_with_lines(text, text_lines, file_extension)

        # If smart splitting results in chunks that are still too large, use fallback
        final_chunk_data = []
        for chunk_info in chunk_data:
            if len(chunk_info["text"]) <= self.chunk_size:
                final_chunk_data.append(chunk_info)
            else:
                # Use fallback splitting while preserving line information
                fallback_chunks = self._fallback_split_with_lines(
                    chunk_info["text"], chunk_info["line_start"], text_lines
                )
                final_chunk_data.extend(fallback_chunks)

        # Filter out tiny chunks and merge them with adjacent chunks
        MIN_CHUNK_SIZE = 100  # Minimum meaningful chunk size
        filtered_chunk_data: List[Dict[str, Any]] = []

        for i, chunk_info in enumerate(final_chunk_data):
            chunk_text = chunk_info["text"].strip()
            if not chunk_text:  # Skip empty chunks
                continue

            # Check if this chunk is too small and might be a fragment
            if len(chunk_text) < MIN_CHUNK_SIZE:
                # Try to merge with the previous chunk if it exists and won't exceed chunk_size
                if (
                    filtered_chunk_data
                    and len(filtered_chunk_data[-1]["text"] + "\n" + chunk_text)
                    <= self.chunk_size
                ):
                    # Merge with previous chunk, extending line range
                    prev_chunk = filtered_chunk_data[-1]
                    prev_chunk["text"] = prev_chunk["text"] + "\n" + chunk_text
                    prev_chunk["line_end"] = chunk_info["line_end"]
                    continue
                # Try to merge with next chunk if available
                elif (
                    i + 1 < len(final_chunk_data)
                    and len(chunk_text + "\n" + final_chunk_data[i + 1]["text"].strip())
                    <= self.chunk_size
                ):
                    # Merge with next chunk by modifying next iteration
                    next_chunk = final_chunk_data[i + 1]
                    next_chunk["text"] = chunk_text + "\n" + next_chunk["text"]
                    next_chunk["line_start"] = chunk_info["line_start"]
                    continue
                # If we can't merge, only keep it if it has substantial content
                elif not self._is_fragment(chunk_text):
                    filtered_chunk_data.append(chunk_info)
                # Otherwise drop the tiny fragment
            else:
                filtered_chunk_data.append(chunk_info)

        # Create chunk metadata with line numbers
        result = []
        for i, chunk_info in enumerate(filtered_chunk_data):
            chunk_text = chunk_info["text"]

            # Don't add file headers to text chunks as they mess up line numbers
            # The file path is already included in metadata
            result.append(
                {
                    "text": chunk_text,
                    "chunk_index": i,
                    "total_chunks": len(filtered_chunk_data),
                    "size": len(chunk_text),
                    "file_path": str(file_path) if file_path else None,
                    "file_extension": file_extension,
                    "line_start": chunk_info["line_start"],
                    "line_end": chunk_info["line_end"],
                }
            )

        return result

    def _is_fragment(self, text: str) -> bool:
        """Check if text is likely a meaningless fragment that should be dropped."""
        text = text.strip()

        # Remove file header for checking
        if text.startswith("// File:"):
            lines = text.split("\n", 1)
            if len(lines) > 1:
                text = lines[1].strip()
            else:
                return True  # Only file header, definitely a fragment

        # Check for common fragment patterns
        fragment_patterns = [
            r'^"""$',  # Just docstring delimiter
            r"^'''$",  # Just docstring delimiter
            r"^def$",  # Just 'def' keyword
            r"^class$",  # Just 'class' keyword
            r"^async def$",  # Just 'async def' keywords
            r"^def \w+$",  # Just function name without signature
            r"^class \w+$",  # Just class name without body
        ]

        for pattern in fragment_patterns:
            if re.match(pattern, text):
                return True

        # If it's very short and doesn't contain meaningful content, it's likely a fragment
        if len(text) < 20 and not any(
            char in text for char in ["{", "}", "(", ")", "=", ":", ";"]
        ):
            return True

        return False

    def chunk_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Read and chunk a file."""
        try:
            # Try different encodings
            encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
            text = None

            for encoding in encodings:
                try:
                    with open(file_path, "r", encoding=encoding) as f:
                        text = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if text is None:
                raise ValueError(f"Could not decode file {file_path}")

            return self.chunk_text(text, file_path)

        except Exception as e:
            raise ValueError(f"Failed to process file {file_path}: {e}")

    def estimate_chunks(self, text: str) -> int:
        """Estimate number of chunks for given text."""
        if not text:
            return 0

        # Simple estimation based on size
        return max(1, len(text) // (self.chunk_size - self.chunk_overlap) + 1)
