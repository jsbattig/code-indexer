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
                r"\n\ndef ",
                r"\nclass ",
                r"\nasync def ",
                r"\n# ",
                r'\n"""',
                r"\n'''",
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
        """Split text into chunks with metadata."""
        if not text or not text.strip():
            return []

        # Determine file extension for smart splitting
        file_extension = ""
        if file_path:
            file_extension = file_path.suffix.lstrip(".")

        # Try smart splitting first
        chunks = self._smart_split(text, file_extension)

        # If smart splitting results in chunks that are still too large, use fallback
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= self.chunk_size:
                final_chunks.append(chunk)
            else:
                final_chunks.extend(self._fallback_split(chunk))

        # Create chunk metadata
        result = []
        for i, chunk_text in enumerate(final_chunks):
            chunk_text = chunk_text.strip()
            if chunk_text:  # Skip empty chunks
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
                        "total_chunks": len(final_chunks),
                        "size": len(contextual_chunk),
                        "file_path": str(file_path) if file_path else None,
                        "file_extension": file_extension,
                    }
                )

        return result

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
