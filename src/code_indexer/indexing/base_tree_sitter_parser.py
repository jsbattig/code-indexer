"""
Base tree-sitter parser with ERROR node fallback handling.

This provides a universal foundation for all parsers to use tree-sitter
as the primary parsing method, with language-specific regex fallbacks
for ERROR nodes to ensure no content is lost.
"""

import re
from abc import abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path

from tree_sitter_language_pack import get_parser

from code_indexer.config import IndexingConfig
from .semantic_chunker import BaseSemanticParser, SemanticChunk


class BaseTreeSitterParser(BaseSemanticParser):
    """Base parser using tree-sitter with ERROR node fallback handling."""

    def __init__(self, config: IndexingConfig, language: str):
        super().__init__(config)
        self.language = language
        self._parser = None

    @property
    def parser(self):
        """Lazy-load the tree-sitter parser."""
        if self._parser is None:
            self._parser = get_parser(self.language)
        return self._parser

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse content using tree-sitter with ERROR node fallback."""
        try:
            # Parse content with tree-sitter
            tree = self._parse_content(content)
            if not tree or not tree.root_node:
                return self._fallback_parse(content, file_path)

            chunks = []
            file_ext = Path(file_path).suffix

            # Extract constructs using tree-sitter AST
            constructs = self._extract_constructs(tree, content, file_path)

            # Create semantic chunks
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

        except Exception:
            # If tree-sitter parsing fails completely, use fallback
            return self._fallback_parse(content, file_path)

    def _parse_content(self, content: str):
        """Parse content with tree-sitter."""
        return self.parser.parse(bytes(content, "utf8"))

    def _extract_constructs(
        self, tree: Any, content: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Extract constructs from tree-sitter AST."""
        constructs: List[Dict[str, Any]] = []
        lines = content.split("\n")

        # Track scope hierarchy for proper path construction
        scope_stack: List[str] = []

        # Extract file-level constructs (package, imports, etc.)
        self._extract_file_level_constructs(
            tree.root_node, constructs, lines, scope_stack
        )

        # Traverse the AST to find all constructs
        self._traverse_node(tree.root_node, constructs, lines, scope_stack, content)

        return constructs

    def _traverse_node(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Recursively traverse AST nodes to extract constructs."""
        if not hasattr(node, "type") or not hasattr(node, "children"):
            return

        node_type = node.type

        # Handle language-specific construct types
        self._handle_language_constructs(
            node, node_type, constructs, lines, scope_stack, content
        )

        # Handle ERROR nodes with fallback extraction
        if node_type == "ERROR":
            self._extract_from_error_node(node, constructs, lines, scope_stack, content)

        # Recursively process children (skip certain nodes that handle their own children)
        skip_children = self._should_skip_children(node_type)
        if not skip_children or node_type == "ERROR":
            for child in node.children:
                self._traverse_node(child, constructs, lines, scope_stack, content)

    def _extract_from_error_node(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract constructs from ERROR nodes using language-specific regex fallback."""
        start_line = node.start_point[0]
        end_line = node.end_point[0]

        # Get the text of the ERROR node
        error_text = "\n".join(lines[start_line : end_line + 1])

        # Use language-specific regex patterns to extract constructs
        error_constructs = self._extract_constructs_from_error_text(
            error_text, start_line, scope_stack
        )

        # Add extracted constructs, avoiding duplicates
        for construct in error_constructs:
            if not self._is_duplicate_construct(construct, constructs):
                constructs.append(construct)

    def _is_duplicate_construct(
        self, new_construct: Dict[str, Any], existing_constructs: List[Dict[str, Any]]
    ) -> bool:
        """Check if a construct is already in the list to avoid duplicates."""
        for existing in existing_constructs:
            if (
                existing.get("name") == new_construct.get("name")
                and existing.get("parent") == new_construct.get("parent")
                and existing.get("line_start") == new_construct.get("line_start")
                and existing.get("type") == new_construct.get("type")
            ):
                return True
        return False

    # Abstract methods that subclasses must implement

    @abstractmethod
    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (packages, imports, etc.)."""
        pass

    @abstractmethod
    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle language-specific AST node types."""
        pass

    @abstractmethod
    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped."""
        pass

    @abstractmethod
    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract constructs from ERROR node text using regex fallback."""
        pass

    @abstractmethod
    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        pass

    # Utility methods

    def _get_node_text(self, node: Any, lines: List[str]) -> str:
        """Extract text from a tree-sitter node."""
        start_line = node.start_point[0]
        start_col = node.start_point[1]
        end_line = node.end_point[0]
        end_col = node.end_point[1]

        if start_line == end_line:
            return str(lines[start_line][start_col:end_col])

        result_lines = [lines[start_line][start_col:]]
        result_lines.extend(lines[start_line + 1 : end_line])
        if end_line < len(lines):
            result_lines.append(lines[end_line][:end_col])

        return "\n".join(result_lines)

    def _get_identifier_from_node(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                return str(self._get_node_text(child, lines))
        return None

    def _extract_parameters(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract parameter list from a function/method node."""
        for child in node.children:
            if hasattr(child, "type") and "parameter" in str(child.type).lower():
                return str(self._get_node_text(child, lines))
        return None

    def _find_constructs_with_regex(
        self, content: str, patterns: Dict[str, str], file_path: str
    ) -> List[Dict[str, Any]]:
        """Find constructs using regex patterns as fallback."""
        constructs = []

        for construct_type, pattern in patterns.items():
            for match in re.finditer(pattern, content, re.MULTILINE):
                start_pos = match.start()
                line_no = content[:start_pos].count("\n")

                # Extract the matched construct
                construct_text = match.group(0)

                # Try to extract name from the match
                name = self._extract_name_from_match(match, construct_type)

                if name:
                    constructs.append(
                        {
                            "type": construct_type,
                            "name": name,
                            "path": name,
                            "signature": construct_text.split("\n")[0].strip(),
                            "parent": None,
                            "scope": "global",
                            "line_start": line_no + 1,
                            "line_end": line_no + construct_text.count("\n") + 1,
                            "text": construct_text,
                            "context": {"extracted_from_regex": True},
                            "features": [f"{construct_type}_fallback"],
                        }
                    )

        return constructs

    def _extract_name_from_match(self, match, construct_type: str) -> Optional[str]:
        """Extract the name from a regex match."""
        # Try common group names
        for group_name in ["name", "identifier", "function_name", "class_name"]:
            try:
                if match.group(group_name):
                    return str(match.group(group_name))
            except IndexError:
                continue

        # Try numbered groups
        try:
            return str(match.group(1))
        except IndexError:
            return None
