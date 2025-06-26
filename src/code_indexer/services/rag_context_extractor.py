"""
RAG context extraction service for Claude Code integration.

Extracts code context around semantic search matches for use with LLM prompts.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CodeContext:
    """Represents extracted code context around a match."""

    file_path: str
    language: str
    content: str
    line_start: int
    line_end: int
    total_lines: int
    match_score: float
    git_info: Optional[Dict[str, str]] = None
    file_size: int = 0


class RAGContextExtractor:
    """Extracts relevant code context for RAG-based prompts."""

    def __init__(self, codebase_dir: Path):
        """Initialize the context extractor.

        Args:
            codebase_dir: Root directory of the codebase
        """
        self.codebase_dir = Path(codebase_dir)
        self._file_cache: Dict[str, str] = {}

    def extract_context_from_results(
        self,
        search_results: List[Dict[str, Any]],
        context_lines: int = 500,
        max_total_lines: int = 5000,
        ensure_all_files: bool = True,
    ) -> List[CodeContext]:
        """Extract code context from semantic search results.

        Args:
            search_results: List of search results from Qdrant
            context_lines: Number of lines to extract around each match
            max_total_lines: Maximum total lines across all contexts
            ensure_all_files: If True, adjust context size to include all files

        Returns:
            List of CodeContext objects with extracted code
        """
        contexts = []
        total_lines_extracted = 0

        # Group results by file to avoid duplicate file reads
        file_groups = self._group_results_by_file(search_results)

        # If ensure_all_files is True, calculate adjusted context size
        adjusted_context_lines = context_lines
        if ensure_all_files and len(file_groups) > 0:
            # Estimate lines needed per file (conservative estimate)
            estimated_lines_per_file = (
                context_lines + 50
            )  # Add buffer for headers/formatting
            total_estimated_lines = len(file_groups) * estimated_lines_per_file

            if total_estimated_lines > max_total_lines:
                # Adjust context size to fit all files
                adjusted_context_lines = max(
                    50, (max_total_lines // len(file_groups)) - 50
                )
                logger.info(
                    f"Adjusted context size from {context_lines} to {adjusted_context_lines} lines "
                    f"to ensure all {len(file_groups)} files fit within {max_total_lines} line limit"
                )

        for file_path, file_results in file_groups.items():
            if total_lines_extracted >= max_total_lines:
                logger.info(
                    f"Reached max total lines limit ({max_total_lines}), stopping extraction"
                )
                break

            try:
                file_contexts = self._extract_file_contexts(
                    file_path,
                    file_results,
                    adjusted_context_lines,
                    max_total_lines - total_lines_extracted,
                )

                for context in file_contexts:
                    contexts.append(context)
                    total_lines_extracted += context.line_end - context.line_start + 1

            except Exception as e:
                logger.warning(f"Failed to extract context from {file_path}: {e}")
                continue

        logger.info(
            f"Extracted {len(contexts)} contexts from {len(file_groups)} files, "
            f"totaling {total_lines_extracted} lines"
        )
        return contexts

    def _group_results_by_file(
        self, search_results: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group search results by file path."""
        file_groups: Dict[str, List[Dict[str, Any]]] = {}

        for result in search_results:
            payload = result.get("payload", {})
            file_path = payload.get("path", "")

            if file_path:
                if file_path not in file_groups:
                    file_groups[file_path] = []
                file_groups[file_path].append(result)

        return file_groups

    def _extract_file_contexts(
        self,
        file_path: str,
        file_results: List[Dict[str, Any]],
        context_lines: int,
        remaining_lines: int,
    ) -> List[CodeContext]:
        """Extract contexts from a single file."""
        full_file_path = self.codebase_dir / file_path

        if not full_file_path.exists():
            logger.warning(f"File not found: {full_file_path}")
            return []

        # Read file content (with caching)
        file_content = self._read_file_cached(full_file_path)
        if not file_content:
            return []

        lines = file_content.splitlines()
        total_lines = len(lines)

        # Find chunk positions and merge overlapping contexts
        contexts = self._merge_overlapping_contexts(
            file_results, lines, context_lines, remaining_lines
        )

        # Create CodeContext objects
        code_contexts = []
        for start_line, end_line, best_result in contexts:
            if start_line >= total_lines:
                continue

            end_line = min(end_line, total_lines - 1)
            context_content = "\n".join(lines[start_line : end_line + 1])

            payload = best_result.get("payload", {})

            code_context = CodeContext(
                file_path=file_path,
                language=payload.get("language", "unknown"),
                content=context_content,
                line_start=start_line + 1,  # 1-indexed for display
                line_end=end_line + 1,  # 1-indexed for display
                total_lines=total_lines,
                match_score=best_result.get("score", 0.0),
                git_info=self._extract_git_info(payload),
                file_size=payload.get("file_size", 0),
            )

            code_contexts.append(code_context)

        return code_contexts

    def _merge_overlapping_contexts(
        self,
        file_results: List[Dict[str, Any]],
        lines: List[str],
        context_lines: int,
        remaining_lines: int,
    ) -> List[Tuple[int, int, Dict[str, Any]]]:
        """Merge overlapping context windows to avoid duplication."""
        total_lines = len(lines)

        # Calculate context ranges for each result
        ranges = []
        for result in file_results:
            payload = result.get("payload", {})

            # Use actual line numbers from metadata if available
            chunk_start_line = payload.get("line_start")
            chunk_end_line = payload.get("line_end")

            if chunk_start_line is not None and chunk_end_line is not None:
                # Use actual line numbers to expand context around the chunk
                # Convert from 1-indexed to 0-indexed for processing
                chunk_start_0_indexed = chunk_start_line - 1
                chunk_end_0_indexed = chunk_end_line - 1

                # Expand context around the actual chunk boundaries
                start_line = max(0, chunk_start_0_indexed - context_lines)
                end_line = min(total_lines - 1, chunk_end_0_indexed + context_lines)
            else:
                # Fallback to old estimation method if line metadata not available
                chunk_index = payload.get("chunk_index", 0)
                estimated_line = min(chunk_index * 10, total_lines - 1)
                start_line = max(0, estimated_line - context_lines // 2)
                end_line = min(total_lines - 1, estimated_line + context_lines // 2)

            ranges.append((start_line, end_line, result))

        # Sort by start line
        ranges.sort(key=lambda x: x[0])

        # Merge overlapping ranges
        merged: List[Tuple[int, int, Dict[str, Any]]] = []
        current_lines = 0

        for start, end, result in ranges:
            if current_lines >= remaining_lines:
                break

            if merged and start <= merged[-1][1] + 1:
                # Overlapping or adjacent - merge
                prev_start, prev_end, prev_result = merged[-1]

                # Use the result with higher score
                best_result = (
                    result
                    if result.get("score", 0) > prev_result.get("score", 0)
                    else prev_result
                )

                merged[-1] = (prev_start, max(end, prev_end), best_result)
            else:
                # No overlap - add new range
                lines_in_range = end - start + 1
                if current_lines + lines_in_range <= remaining_lines:
                    merged.append((start, end, result))
                    current_lines += lines_in_range
                else:
                    # Truncate to fit remaining lines
                    truncated_end = start + (remaining_lines - current_lines) - 1
                    if truncated_end >= start:
                        merged.append((start, truncated_end, result))
                    break

        return merged

    def _read_file_cached(self, file_path: Path) -> str:
        """Read file content with caching."""
        file_key = str(file_path)

        if file_key in self._file_cache:
            return self._file_cache[file_key]

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Cache file content (with size limit)
            if len(content) < 1024 * 1024:  # Only cache files < 1MB
                self._file_cache[file_key] = content

            return content

        except Exception as e:
            logger.warning(f"Failed to read file {file_path}: {e}")
            return ""

    def _extract_git_info(self, payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Extract git information from result payload."""
        git_info = {}

        if payload.get("git_available", False):
            git_info["branch"] = payload.get("git_branch", "unknown")
            git_info["commit"] = payload.get("git_commit_hash", "unknown")

            # Truncate commit hash for display
            if git_info["commit"] != "unknown" and len(git_info["commit"]) > 8:
                git_info["commit"] = git_info["commit"][:8] + "..."

        return git_info if git_info else None

    def format_contexts_for_prompt(
        self,
        contexts: List[CodeContext],
        include_line_numbers: bool = True,
        max_context_length: int = 50000,
    ) -> str:
        """Format extracted contexts for inclusion in LLM prompt.

        Args:
            contexts: List of CodeContext objects
            include_line_numbers: Whether to include line numbers
            max_context_length: Maximum total character length

        Returns:
            Formatted string ready for prompt inclusion
        """
        if not contexts:
            return "No relevant code contexts found."

        formatted_parts = []
        total_length = 0

        # Add relevance score explanation for prompt engineering
        relevance_explanation = (
            "\n🔬 **EVIDENCE CITATION GUIDE**: Each code context below MUST be used for evidence-backed assertions. "
            "Every statement requires citations with line info in description, not URL. "
            "\n\n**RELEVANCE SCORES**: Each context includes a semantic similarity score (0.0-1.0). "
            "Higher scores (>0.8) indicate strong relevance to your query. "
            "Medium scores (0.5-0.8) suggest related concepts. "
            "Lower scores (<0.5) may provide peripheral context. "
            "\n\n**CITATION REQUIREMENTS**: "
            "- Use exact file paths from contexts below "
            "- Put line numbers in description text only "
            "- Every technical claim needs a source citation "
            "- Treat this like scientific research - no assertion without evidence\n"
        )
        formatted_parts.append(relevance_explanation)
        total_length += len(relevance_explanation)

        for i, context in enumerate(contexts, 1):
            # Format header with enhanced relevance score information - ensure full path is shown
            # If file_path doesn't start with known prefixes, it might be relative to codebase_dir
            display_path = context.file_path
            if not display_path.startswith(("src/", "tests/", "/")):
                # Handle cases where file_path might be just a filename
                # Try to construct full path if needed
                if display_path.endswith(".py") and "/" not in display_path:
                    # This looks like a bare filename, let's check common locations
                    potential_paths = [
                        f"src/code_indexer/services/{display_path}",
                        f"src/code_indexer/{display_path}",
                        f"tests/{display_path}",
                        display_path,  # fallback to original
                    ]
                    # Use the first existing path or fall back to original
                    for potential_path in potential_paths:
                        if (self.codebase_dir / potential_path).exists():
                            display_path = potential_path
                            break

            header = f"\n## Context {i}: {display_path}"
            if context.language != "unknown":
                header += f" ({context.language})"

            # Add relevance score with prompt engineering context
            relevance_level = (
                "HIGH"
                if context.match_score > 0.8
                else "MEDIUM" if context.match_score > 0.5 else "LOW"
            )
            header += f"\n**Lines {context.line_start}-{context.line_end}/{context.total_lines}** | "
            header += f"**Relevance: {context.match_score:.3f} ({relevance_level})** | "
            header += f"**Priority: {'Primary' if context.match_score > 0.8 else 'Secondary' if context.match_score > 0.5 else 'Supporting'}**"

            if context.git_info:
                header += f" | **Branch: {context.git_info['branch']}**"
                if context.git_info["commit"] != "unknown":
                    header += f" | **Commit: {context.git_info['commit']}**"

            header += "\n"

            # Format content
            if include_line_numbers:
                lines = context.content.split("\n")
                numbered_lines = []
                for j, line in enumerate(lines):
                    line_num = context.line_start + j
                    numbered_lines.append(f"{line_num:4d}: {line}")
                content = "\n".join(numbered_lines)
            else:
                content = context.content

            # Code block formatting
            language = context.language if context.language != "unknown" else ""
            formatted_content = f"```{language}\n{content}\n```\n"

            section = header + formatted_content

            # Check length limit
            if total_length + len(section) > max_context_length:
                remaining_chars = max_context_length - total_length
                if remaining_chars > 100:  # Only include if we have meaningful space
                    truncated_section = (
                        section[: remaining_chars - 50] + "\n... [truncated]\n```\n"
                    )
                    formatted_parts.append(truncated_section)
                break

            formatted_parts.append(section)
            total_length += len(section)

        if total_length >= max_context_length:
            formatted_parts.append(
                f"\n*Note: Output truncated at {max_context_length:,} characters. Total contexts available: {len(contexts)}*"
            )

        return "".join(formatted_parts)

    def clear_cache(self):
        """Clear the file content cache."""
        self._file_cache.clear()
        logger.info("File cache cleared")
