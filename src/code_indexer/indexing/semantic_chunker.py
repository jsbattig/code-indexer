"""
AST-based semantic code chunking implementation.

This module provides semantic chunking capabilities that parse code using AST
(Abstract Syntax Tree) to create meaningful chunks based on code structure
rather than arbitrary character counts.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field

from code_indexer.config import IndexingConfig
from code_indexer.indexing.chunker import TextChunker


@dataclass
class SemanticChunk:
    """Represents a semantically meaningful code chunk with metadata."""

    # Existing chunk fields
    text: str
    chunk_index: int
    total_chunks: int
    size: int
    file_path: str
    file_extension: str
    line_start: int
    line_end: int

    # Semantic chunking fields
    semantic_chunking: bool = True
    semantic_type: Optional[str] = None  # "function", "class", "method", etc.
    semantic_name: Optional[str] = None  # Name of the semantic unit
    semantic_path: Optional[str] = None  # Full path like "ClassName.methodName"
    semantic_signature: Optional[str] = None  # Function/method signature
    semantic_parent: Optional[str] = None  # Parent context
    semantic_context: Dict[str, Any] = field(default_factory=dict)  # Additional context
    semantic_scope: Optional[str] = None  # "global", "class", "function", etc.
    semantic_language_features: List[str] = field(
        default_factory=list
    )  # Language-specific features

    # Split tracking for large objects
    is_split_object: bool = False
    part_number: Optional[int] = None
    total_parts: Optional[int] = None
    part_of_total: Optional[str] = None  # "1 of 3"

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary for storage."""
        return {
            "text": self.text,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "size": self.size,
            "file_path": self.file_path,
            "file_extension": self.file_extension,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "semantic_chunking": self.semantic_chunking,
            "semantic_type": self.semantic_type,
            "semantic_name": self.semantic_name,
            "semantic_path": self.semantic_path,
            "semantic_signature": self.semantic_signature,
            "semantic_parent": self.semantic_parent,
            "semantic_context": self.semantic_context,
            "semantic_scope": self.semantic_scope,
            "semantic_language_features": self.semantic_language_features,
            "is_split_object": self.is_split_object,
            "part_number": self.part_number,
            "total_parts": self.total_parts,
            "part_of_total": self.part_of_total,
        }


class BaseSemanticParser:
    """Base class for language-specific semantic parsers."""

    def __init__(self, config: IndexingConfig):
        self.config = config
        self.max_chunk_size = config.chunk_size
        self.min_chunk_size = 200  # Avoid tiny fragments

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """
        Parse content and create semantic chunks.
        Must be implemented by language-specific parsers.
        """
        raise NotImplementedError("Subclasses must implement chunk method")

    def _detect_language_from_path(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
        }
        return language_map.get(ext, "unknown")


class SemanticChunker:
    """
    Main semantic chunking class that delegates to language-specific parsers.
    Falls back to text chunking for unsupported languages or parse errors.
    """

    def __init__(self, config: IndexingConfig):
        self.config = config
        self.text_chunker = TextChunker(config)

        # Initialize language-specific parsers
        # We'll implement these one by one
        self.parsers: Dict[str, BaseSemanticParser] = {}

        # These will be implemented in subsequent steps
        try:
            from .python_parser import PythonSemanticParser

            self.parsers["python"] = PythonSemanticParser(config)
        except ImportError:
            pass

        try:
            from .javascript_parser import JavaScriptSemanticParser

            self.parsers["javascript"] = JavaScriptSemanticParser(config)
        except ImportError:
            pass

        try:
            from .typescript_parser import TypeScriptSemanticParser

            self.parsers["typescript"] = TypeScriptSemanticParser(config)
        except ImportError:
            pass

        try:
            from .java_parser import JavaSemanticParser

            self.parsers["java"] = JavaSemanticParser(config)
        except ImportError:
            pass

        try:
            from .go_parser import GoSemanticParser

            self.parsers["go"] = GoSemanticParser(config)
        except ImportError:
            pass

    def chunk_file(self, file_path: Union[Path, str]) -> List[Dict[str, Any]]:
        """
        Chunk file using AST-based semantic chunking or fall back to text chunking.

        Args:
            file_path: Path to the file being chunked (Path object or string)

        Returns:
            List of chunk dictionaries with metadata
        """
        # Convert to Path if string
        path_obj = Path(file_path) if isinstance(file_path, str) else file_path

        # Check if semantic chunking is enabled
        if not self.config.use_semantic_chunking:
            # Use TextChunker's chunk_file method directly
            return self.text_chunker.chunk_file(path_obj)  # type: ignore[no-any-return]

        # Read file content
        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"Failed to read file {path_obj}: {e}")
            return self.text_chunker.chunk_file(path_obj)  # type: ignore[no-any-return]

        # Detect language from file extension
        language = self._detect_language(str(path_obj))

        # Check if we have a parser for this language
        if language not in self.parsers:
            return self.text_chunker.chunk_file(path_obj)  # type: ignore[no-any-return]

        # Try semantic chunking
        try:
            semantic_chunks = self.parsers[language].chunk(content, str(path_obj))

            # If parser returns empty list, fall back to text chunking
            if not semantic_chunks:
                return self.text_chunker.chunk_file(path_obj)  # type: ignore[no-any-return]

            # Convert SemanticChunk objects to dictionaries
            return [chunk.to_dict() for chunk in semantic_chunks]

        except Exception as e:
            # On any parsing error, fall back to text chunking
            print(f"Semantic chunking failed for {path_obj}: {e}")
            return self.text_chunker.chunk_file(path_obj)  # type: ignore[no-any-return]

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()

        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
        }

        return language_map.get(ext, "unknown")

    def chunk_content(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Chunk content directly using AST-based semantic chunking.
        This is used for testing and when content is already available.

        Args:
            content: File content as string
            file_path: Path to the file being chunked

        Returns:
            List of chunk dictionaries with metadata
        """
        # Check if semantic chunking is enabled
        if not self.config.use_semantic_chunking:
            return self._fallback_to_text_chunking(content, file_path)

        # Detect language from file extension
        language = self._detect_language(file_path)

        # Check if we have a parser for this language
        if language not in self.parsers:
            return self._fallback_to_text_chunking(content, file_path)

        # Try semantic chunking
        try:
            semantic_chunks = self.parsers[language].chunk(content, file_path)

            # If parser returns empty list, fall back to text chunking
            if not semantic_chunks:
                return self._fallback_to_text_chunking(content, file_path)

            # Convert SemanticChunk objects to dictionaries
            return [chunk.to_dict() for chunk in semantic_chunks]

        except Exception as e:
            # On any parsing error, fall back to text chunking
            print(f"Semantic chunking failed for {file_path}: {e}")
            return self._fallback_to_text_chunking(content, file_path)

    def _fallback_to_text_chunking(
        self, content: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Fall back to text-based chunking and add semantic_chunking=False flag."""
        # Create a temporary path object for the chunker
        path_obj = Path(file_path)

        # Use the chunk_text method with the content
        chunks = self.text_chunker.chunk_text(text=content, file_path=path_obj)

        # Add semantic_chunking=False to all chunks
        for chunk in chunks:
            chunk["semantic_chunking"] = False

        return chunks  # type: ignore[no-any-return]
