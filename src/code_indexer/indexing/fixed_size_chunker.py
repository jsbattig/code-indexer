"""Model-aware fixed-size chunker with optimized chunk sizes.

This module implements model-aware fixed-size chunking algorithm:
- Dynamic chunk size: optimized per embedding model (voyage-code-3: 4096, nomic-embed-text: 2048)
- Fixed overlap: 15% of chunk size between adjacent chunks
- Pure arithmetic: no parsing, no regex, no string analysis
- Pattern: next_start = current_start + (chunk_size - overlap_size)
"""

from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from ..config import IndexingConfig, Config


class FixedSizeChunker:
    """Model-aware fixed-size chunker optimized for different embedding providers.

    Algorithm:
    1. Determine optimal chunk size based on embedding model
    2. 15% overlap between adjacent chunks (consistent across models)
    3. Simple math: next_start = current_start + step_size
    4. No boundary detection - cuts at exact character positions
    5. No parsing - pure arithmetic operations

    Model-specific chunk sizes:
    - voyage-code-3: 4096 characters (1024 tokens, research optimal)
    - voyage-code-2: 4096 characters (1024 tokens, research optimal)
    - voyage-large-2: 4096 characters (1024 tokens, research optimal)
    - nomic-embed-text: 2048 characters (512 tokens, Ollama limitation)
    - default: 1000 characters (conservative fallback)
    """

    # Model-aware chunk size mapping based on research and model capabilities
    MODEL_CHUNK_SIZES = {
        "voyage-code-3": 4096,  # 32K token capacity, 1024 tokens optimal
        "voyage-code-2": 4096,  # 16K token capacity, 1024 tokens optimal
        "voyage-large-2": 4096,  # Large context models, 1024 tokens optimal
        "voyage-3": 4096,  # General purpose, 1024 tokens optimal
        "voyage-3-large": 4096,  # Large model, 1024 tokens optimal
        "nomic-embed-text": 2048,  # Ollama 2K token limitation, 512 tokens safe
        "default": 1000,  # Conservative fallback for unknown models
    }

    # Fixed overlap percentage (15% of chunk size)
    OVERLAP_PERCENTAGE = 0.15

    def __init__(self, config: Union[IndexingConfig, Config]):
        """Initialize the model-aware fixed-size chunker.

        Args:
            config: Indexing configuration or full Config with embedding provider info
        """
        self.config = config

        # Determine chunk size based on embedding model
        if hasattr(config, "embedding_provider"):
            # Full Config passed - can determine model-aware chunk size
            embedding_provider = config.embedding_provider
            if embedding_provider == "voyage-ai":
                # Get specific VoyageAI model
                model_name = config.voyage_ai.model
                self.chunk_size = self.MODEL_CHUNK_SIZES.get(
                    model_name, self.MODEL_CHUNK_SIZES["default"]
                )
            elif embedding_provider == "ollama":
                # Get specific Ollama model
                model_name = config.ollama.model
                self.chunk_size = self.MODEL_CHUNK_SIZES.get(
                    model_name, self.MODEL_CHUNK_SIZES["default"]
                )
            else:
                self.chunk_size = self.MODEL_CHUNK_SIZES["default"]
        else:
            # IndexingConfig only - use default for backward compatibility
            self.chunk_size = self.MODEL_CHUNK_SIZES["default"]

        # Calculate derived values
        self.overlap_size = int(self.chunk_size * self.OVERLAP_PERCENTAGE)
        self.step_size = self.chunk_size - self.overlap_size

    def _calculate_line_numbers(
        self, text: str, start_pos: int, end_pos: int
    ) -> tuple[int, int]:
        """Calculate line start and end numbers for a chunk.

        Args:
            text: The full text
            start_pos: Character start position
            end_pos: Character end position

        Returns:
            Tuple of (line_start, line_end) as 1-based line numbers
        """
        if not text or start_pos >= len(text):
            return 1, 1

        # Count newlines up to start position
        line_start = text[:start_pos].count("\n") + 1

        # Count newlines up to end position (but not beyond text length)
        actual_end = min(end_pos, len(text))
        line_end = text[:actual_end].count("\n") + 1

        return line_start, line_end

    def chunk_text(
        self, text: str, file_path: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """Split text into fixed-size chunks using ultra-simple algorithm.

        Args:
            text: Text to chunk
            file_path: Path to the file (for metadata)

        Returns:
            List of chunk dictionaries with metadata
        """
        if not text or not text.strip():
            return []

        # Determine file extension
        file_extension = ""
        if file_path:
            file_extension = file_path.suffix.lstrip(".")

        chunks = []
        current_start = 0
        chunk_index = 0

        # Process text using fixed-size algorithm
        while current_start < len(text):
            # Calculate chunk boundaries
            chunk_end = current_start + self.chunk_size

            # Extract chunk text
            if chunk_end >= len(text):
                # Last chunk - take remaining text
                chunk_text = text[current_start:]
            else:
                # Regular chunk - exactly chunk_size characters
                chunk_text = text[current_start:chunk_end]

            # Calculate line numbers for this chunk
            line_start, line_end = self._calculate_line_numbers(
                text, current_start, current_start + len(chunk_text)
            )

            # Create chunk metadata
            chunk = {
                "text": chunk_text,
                "chunk_index": chunk_index,
                "total_chunks": 0,  # Will be updated after processing all chunks
                "size": len(chunk_text),
                "file_path": str(file_path) if file_path else None,
                "file_extension": file_extension,
                "line_start": line_start,
                "line_end": line_end,
            }
            chunks.append(chunk)

            # If this chunk contains all remaining text, we're done
            if chunk_end >= len(text):
                break

            # Move to next chunk start position
            # Pattern: next_start = current_start + step_size
            current_start += self.step_size
            chunk_index += 1

        # Update total_chunks in all chunk metadata
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk["total_chunks"] = total_chunks

        return chunks

    def chunk_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Read and chunk a file using fixed-size algorithm.

        For very large files (>10MB), uses streaming approach to avoid
        loading the entire file into memory at once.

        Args:
            file_path: Path to file to chunk

        Returns:
            List of chunk dictionaries with metadata

        Raises:
            ValueError: If file cannot be read or processed
        """
        try:
            # Check file size to determine processing approach
            file_size = file_path.stat().st_size
            large_file_threshold = 10 * 1024 * 1024  # 10MB

            if file_size > large_file_threshold:
                # Use streaming approach for very large files
                return self._chunk_file_streaming(file_path)
            else:
                # Standard approach: read entire file into memory
                return self._chunk_file_standard(file_path)

        except Exception as e:
            raise ValueError(f"Failed to process file {file_path}: {e}")

    def _chunk_file_standard(self, file_path: Path) -> List[Dict[str, Any]]:
        """Standard file chunking - reads entire file into memory."""
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

    def _chunk_file_streaming(self, file_path: Path) -> List[Dict[str, Any]]:
        """Streaming file chunking for very large files.

        Processes file in chunks without loading entire content into memory.
        Uses a sliding window approach to maintain proper overlap between chunks.
        """
        # Try different encodings
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

        for encoding in encodings:
            try:
                return self._process_file_streaming(file_path, encoding)
            except UnicodeDecodeError:
                continue

        raise ValueError(f"Could not decode file {file_path} with any encoding")

    def _process_file_streaming(
        self, file_path: Path, encoding: str
    ) -> List[Dict[str, Any]]:
        """Process file using streaming approach with specified encoding."""
        chunks = []
        chunk_index = 0

        # Buffer to handle overlap between reads
        overlap_buffer = ""

        # Read file in chunks
        read_size = 32 * 1024  # 32KB read buffer

        with open(file_path, "r", encoding=encoding, buffering=read_size) as f:
            while True:
                # Read next chunk from file
                file_chunk = f.read(read_size)

                if not file_chunk:
                    # End of file - process any remaining overlap buffer
                    if overlap_buffer:
                        remaining_chunks = self._process_text_buffer(
                            overlap_buffer, file_path, chunk_index, final_buffer=True
                        )
                        chunks.extend(remaining_chunks)
                    break

                # Combine overlap buffer with new data
                current_buffer = overlap_buffer + file_chunk

                # Process complete chunks from current buffer
                processed_chunks, remaining_text = self._extract_complete_chunks(
                    current_buffer, file_path, chunk_index
                )

                chunks.extend(processed_chunks)
                chunk_index += len(processed_chunks)

                # Keep overlap for next iteration
                # We need chunk_size + overlap_size characters to ensure proper overlap
                required_buffer_size = self.chunk_size + self.overlap_size

                if len(remaining_text) >= required_buffer_size:
                    # Keep the last required_buffer_size characters for overlap
                    overlap_buffer = remaining_text[-required_buffer_size:]
                else:
                    # Keep all remaining text
                    overlap_buffer = remaining_text

        # Update total_chunks in all chunk metadata
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk["total_chunks"] = total_chunks

        return chunks

    def _extract_complete_chunks(
        self, text_buffer: str, file_path: Path, start_chunk_index: int
    ) -> tuple[List[Dict[str, Any]], str]:
        """Extract complete chunks from text buffer, leaving remainder for next iteration."""
        chunks = []
        chunk_index = start_chunk_index
        current_pos = 0

        # Extract chunks while we have enough text
        while current_pos + self.chunk_size <= len(text_buffer):
            chunk_end = current_pos + self.chunk_size
            chunk_text = text_buffer[current_pos:chunk_end]

            # Calculate line numbers (simplified for streaming)
            line_start = text_buffer[:current_pos].count("\n") + 1
            line_end = text_buffer[:chunk_end].count("\n") + 1

            # Determine file extension
            file_extension = file_path.suffix.lstrip(".") if file_path else ""

            chunk = {
                "text": chunk_text,
                "chunk_index": chunk_index,
                "total_chunks": 0,  # Will be updated after processing all chunks
                "size": len(chunk_text),
                "file_path": str(file_path) if file_path else None,
                "file_extension": file_extension,
                "line_start": line_start,
                "line_end": line_end,
            }
            chunks.append(chunk)

            # Move to next chunk position
            current_pos += self.step_size
            chunk_index += 1

        # Return chunks and remaining text
        remaining_text = text_buffer[current_pos:]
        return chunks, remaining_text

    def _process_text_buffer(
        self,
        text_buffer: str,
        file_path: Path,
        start_chunk_index: int,
        final_buffer: bool = False,
    ) -> List[Dict[str, Any]]:
        """Process final text buffer (for end of file)."""
        if not text_buffer:
            return []

        # For final buffer, create one chunk with remaining text
        if final_buffer and len(text_buffer) < self.chunk_size:
            file_extension = file_path.suffix.lstrip(".") if file_path else ""

            chunk = {
                "text": text_buffer,
                "chunk_index": start_chunk_index,
                "total_chunks": 0,  # Will be updated after processing
                "size": len(text_buffer),
                "file_path": str(file_path) if file_path else None,
                "file_extension": file_extension,
                "line_start": 1,  # Simplified for final chunk
                "line_end": text_buffer.count("\n") + 1,
            }
            return [chunk]

        # Otherwise use regular chunking
        return self.chunk_text(text_buffer, file_path)

    def estimate_chunks(self, text: str) -> int:
        """Estimate number of chunks for given text using fixed-size algorithm.

        Args:
            text: Text to estimate chunks for

        Returns:
            Estimated number of chunks
        """
        if not text:
            return 0

        # Simple arithmetic estimation
        # First chunk: chunk_size characters
        # Each additional chunk: step_size new characters (accounting for overlap)
        if len(text) <= self.chunk_size:
            return 1

        remaining_after_first = len(text) - self.chunk_size
        additional_chunks = (
            remaining_after_first + self.step_size - 1
        ) // self.step_size  # Ceiling division
        return 1 + additional_chunks
