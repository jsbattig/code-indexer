"""Text chunking utilities for breaking large files into manageable pieces."""

import re
from typing import List, Optional, Dict, Any
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
        # For simplicity, use a more direct approach
        # Split the text normally, then map chunks back to line positions

        # Use the existing smart split method to get text chunks
        text_chunks = self._smart_split(text, file_extension)

        # Map each text chunk to its line positions
        chunk_data = []
        current_pos = 0

        for chunk_text in text_chunks:
            if not chunk_text.strip():
                continue

            # Find where this chunk starts in the original text
            chunk_start_pos = text.find(chunk_text, current_pos)
            if chunk_start_pos == -1:
                # Fallback: use current position
                chunk_start_pos = current_pos

            chunk_end_pos = chunk_start_pos + len(chunk_text)

            # Calculate line numbers for this text segment
            text_before_chunk = text[:chunk_start_pos]
            text_in_chunk = text[chunk_start_pos:chunk_end_pos]

            line_start = text_before_chunk.count("\n") + 1
            line_end = line_start + text_in_chunk.count("\n")

            chunk_data.append(
                {"text": chunk_text, "line_start": line_start, "line_end": line_end}
            )

            current_pos = chunk_end_pos

        return chunk_data

    def _fallback_split_with_lines(
        self, text: str, start_line: int, text_lines: List[str]
    ) -> List[Dict[str, Any]]:
        """Fallback splitting when smart splitting doesn't work well, with line tracking."""
        # Use existing fallback split, then map to line numbers
        text_chunks = self._fallback_split(text)

        chunk_data = []
        current_pos = 0

        for chunk_text in text_chunks:
            # Find where this chunk starts in the original text
            chunk_start_pos = text.find(chunk_text, current_pos)
            if chunk_start_pos == -1:
                chunk_start_pos = current_pos

            chunk_end_pos = chunk_start_pos + len(chunk_text)

            # Calculate line numbers for this text segment
            text_before_chunk = text[:chunk_start_pos]
            text_in_chunk = text[chunk_start_pos:chunk_end_pos]

            line_start = text_before_chunk.count("\n") + 1
            line_end = line_start + text_in_chunk.count("\n")

            chunk_data.append(
                {"text": chunk_text, "line_start": line_start, "line_end": line_end}
            )

            current_pos = chunk_end_pos

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

            # Add file context to chunk if it's not too long
            contextual_chunk = chunk_text
            if file_path and len(chunk_text) < self.chunk_size - 100:
                file_info = f"// File: {file_path.name}\n"
                if len(file_info + chunk_text) <= self.chunk_size:
                    contextual_chunk = file_info + chunk_text

            result.append(
                {
                    "text": contextual_chunk,
                    "chunk_index": i,
                    "total_chunks": len(filtered_chunk_data),
                    "size": len(contextual_chunk),
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
