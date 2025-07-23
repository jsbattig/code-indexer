"""
Rust semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class RustSemanticParser(BaseTreeSitterParser):
    """Semantic parser for Rust files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "rust")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (crate, use statements, modules)."""
        # Find use statements and mod declarations
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "use_declaration":
                    use_name = self._extract_use_name(child, lines)
                    if use_name:
                        constructs.append(
                            {
                                "type": "use",
                                "name": use_name,
                                "path": use_name,
                                "signature": f"use {use_name};",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "use"},
                                "features": ["use_declaration"],
                            }
                        )
                elif child.type == "mod_item":
                    mod_name = self._extract_mod_name(child, lines)
                    if mod_name:
                        constructs.append(
                            {
                                "type": "module",
                                "name": mod_name,
                                "path": mod_name,
                                "signature": f"mod {mod_name};",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "module"},
                                "features": ["module_declaration"],
                            }
                        )

    def _handle_language_constructs(
        self,
        node: Any,
        node_type: str,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust-specific AST node types."""
        if node_type == "struct_item":
            self._handle_struct_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "enum_item":
            self._handle_enum_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "union_item":
            self._handle_union_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "trait_item":
            self._handle_trait_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "impl_item":
            self._handle_impl_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "function_item":
            self._handle_function_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "function_signature_item":
            self._handle_function_signature(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "mod_item":
            self._handle_module_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "macro_definition":
            self._handle_macro_definition(node, constructs, lines, scope_stack, content)
        elif node_type == "const_item":
            self._handle_const_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "static_item":
            self._handle_static_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "type_item":
            self._handle_type_alias(node, constructs, lines, scope_stack, content)

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        # These node types handle their own children
        return node_type in [
            "impl_item",
            "mod_item",
        ]

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Rust constructs from ERROR node text using regex fallback."""
        constructs = []
        lines = error_text.split("\n")
        current_parent = "::".join(scope_stack) if scope_stack else None

        # Rust patterns with proper regex escaping
        patterns = [
            # Struct patterns
            (r"^\s*(?:pub\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)", "struct"),
            # Enum patterns
            (r"^\s*(?:pub\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)", "enum"),
            # Union patterns
            (r"^\s*(?:pub\s+)?union\s+([A-Za-z_][A-Za-z0-9_]*)", "union"),
            # Trait patterns
            (r"^\s*(?:pub\s+)?trait\s+([A-Za-z_][A-Za-z0-9_]*)", "trait"),
            # Impl patterns
            (
                r"^\s*impl(?:\s*<[^>]*>)?\s+(?:[A-Za-z_][A-Za-z0-9_:]*\s+for\s+)?([A-Za-z_][A-Za-z0-9_]*)",
                "impl",
            ),
            # Function patterns
            (r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)", "function"),
            # Macro patterns
            (r"^\s*macro_rules!\s+([A-Za-z_][A-Za-z0-9_]*)", "macro"),
            # Const patterns
            (r"^\s*(?:pub\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)", "const"),
            # Static patterns
            (r"^\s*(?:pub\s+)?static\s+([A-Za-z_][A-Za-z0-9_]*)", "static"),
            # Type alias patterns
            (r"^\s*(?:pub\s+)?type\s+([A-Za-z_][A-Za-z0-9_]*)", "type"),
            # Use statements
            (r"^\s*use\s+([A-Za-z_:][A-Za-z0-9_:]*)", "use"),
            # Module patterns
            (r"^\s*(?:pub\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)", "module"),
        ]

        for i, line in enumerate(lines):
            line_num = start_line + i
            for pattern, construct_type in patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)
                    full_path = f"{current_parent}::{name}" if current_parent else name

                    constructs.append(
                        {
                            "type": construct_type,
                            "name": name,
                            "path": full_path,
                            "signature": line.strip(),
                            "parent": current_parent,
                            "scope": "impl" if current_parent else "global",
                            "line_start": line_num,
                            "line_end": line_num,
                            "text": line,
                            "context": {"regex_fallback": True},
                            "features": [f"{construct_type}_declaration"],
                        }
                    )
                    break

        return constructs

    def _extract_use_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract use name from use declaration node."""
        try:
            # Find the use_list or scoped_identifier
            for child in node.children:
                if hasattr(child, "type") and child.type in [
                    "use_list",
                    "scoped_identifier",
                    "identifier",
                ]:
                    return self._get_node_text(child, lines).strip()
        except Exception:
            pass

        # Fallback to regex
        node_text = self._get_node_text(node, lines)
        match = re.search(r"use\s+([^;]+)", node_text)
        return match.group(1).strip() if match else None

    def _extract_mod_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract module name from mod declaration node."""
        try:
            # Find the identifier node
            for child in node.children:
                if hasattr(child, "type") and child.type == "identifier":
                    return self._get_node_text(child, lines).strip()
        except Exception:
            pass

        # Fallback to regex
        node_text = self._get_node_text(node, lines)
        match = re.search(r"mod\s+([A-Za-z_][A-Za-z0-9_]*)", node_text)
        return match.group(1) if match else None

    def _handle_struct_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust struct declaration."""
        struct_name = self._extract_identifier(node, lines)
        if not struct_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{struct_name}" if current_scope else struct_name

        # Check for generics and features
        features = []
        node_text = self._get_node_text(node, lines)
        if "<" in node_text and ">" in node_text:
            features.append("generic")
        if "pub" in node_text:
            features.append("public")

        signature = self._extract_signature(node, lines, "struct")

        constructs.append(
            {
                "type": "struct",
                "name": struct_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "struct"},
                "features": features,
            }
        )

    def _handle_enum_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust enum declaration."""
        enum_name = self._extract_identifier(node, lines)
        if not enum_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{enum_name}" if current_scope else enum_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "<" in node_text and ">" in node_text:
            features.append("generic")
        if "pub" in node_text:
            features.append("public")

        signature = self._extract_signature(node, lines, "enum")

        constructs.append(
            {
                "type": "enum",
                "name": enum_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "enum"},
                "features": features,
            }
        )

    def _handle_union_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust union declaration."""
        union_name = self._extract_identifier(node, lines)
        if not union_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{union_name}" if current_scope else union_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "<" in node_text and ">" in node_text:
            features.append("generic")
        if "pub" in node_text:
            features.append("public")

        signature = self._extract_signature(node, lines, "union")

        constructs.append(
            {
                "type": "union",
                "name": union_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "union"},
                "features": features,
            }
        )

    def _handle_trait_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust trait declaration."""
        trait_name = self._extract_identifier(node, lines)
        if not trait_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{trait_name}" if current_scope else trait_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "<" in node_text and ">" in node_text:
            features.append("generic")
        if "pub" in node_text:
            features.append("public")

        signature = self._extract_signature(node, lines, "trait")

        constructs.append(
            {
                "type": "trait",
                "name": trait_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "trait"},
                "features": features,
            }
        )

        # Process trait methods
        scope_stack.append(trait_name)
        self._process_trait_items(node, constructs, lines, scope_stack, content)
        scope_stack.pop()

    def _handle_impl_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust impl declaration."""
        impl_target = self._extract_impl_target(node, lines)
        if not impl_target:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{impl_target}" if current_scope else impl_target

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "<" in node_text and ">" in node_text:
            features.append("generic")
        if " for " in node_text:
            features.append("trait_impl")

        signature = self._extract_signature(node, lines, "impl")

        constructs.append(
            {
                "type": "impl",
                "name": f"impl {impl_target}",
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "impl", "target": impl_target},
                "features": features,
            }
        )

        # Process impl methods
        scope_stack.append(f"impl {impl_target}")
        self._process_impl_items(node, constructs, lines, scope_stack, content)
        scope_stack.pop()

    def _handle_function_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust function declaration."""
        func_name = self._extract_identifier(node, lines)
        if not func_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{func_name}" if current_scope else func_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "<" in node_text and ">" in node_text:
            features.append("generic")
        if "pub" in node_text:
            features.append("public")
        if "async" in node_text:
            features.append("async")
        if "unsafe" in node_text:
            features.append("unsafe")

        signature = self._extract_function_signature(node, lines)

        constructs.append(
            {
                "type": "function",
                "name": func_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "impl" if "impl" in current_scope else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "function"},
                "features": features,
            }
        )

    def _handle_function_signature(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust function signature (trait method declaration)."""
        func_name = self._extract_identifier(node, lines)
        if not func_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{func_name}" if current_scope else func_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "<" in node_text and ">" in node_text:
            features.append("generic")
        if "pub" in node_text:
            features.append("public")
        if "async" in node_text:
            features.append("async")
        if "unsafe" in node_text:
            features.append("unsafe")

        signature = self._extract_function_signature(node, lines)

        constructs.append(
            {
                "type": "function",
                "name": func_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "impl" if "impl" in current_scope else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "function", "signature_only": True},
                "features": features,
            }
        )

    def _handle_module_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust module declaration."""
        mod_name = self._extract_identifier(node, lines)
        if not mod_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{mod_name}" if current_scope else mod_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "pub" in node_text:
            features.append("public")

        signature = self._extract_signature(node, lines, "mod")

        constructs.append(
            {
                "type": "module",
                "name": mod_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "module"},
                "features": features,
            }
        )

        # Check if this is an inline module (has a declaration_list)
        has_body = any(
            hasattr(child, "type") and child.type == "declaration_list"
            for child in node.children
        )

        if has_body:
            # Process module items
            scope_stack.append(mod_name)
            self._process_module_items(node, constructs, lines, scope_stack, content)
            scope_stack.pop()

    def _process_module_items(
        self,
        module_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process items within a module."""
        for child in module_node.children:
            if hasattr(child, "type"):
                if child.type == "declaration_list":
                    # Process items inside the declaration list
                    for item in child.children:
                        if hasattr(item, "type") and item.type not in ["{", "}"]:
                            self._handle_language_constructs(
                                item, item.type, constructs, lines, scope_stack, content
                            )
                else:
                    self._handle_language_constructs(
                        child, child.type, constructs, lines, scope_stack, content
                    )

    def _handle_macro_definition(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust macro definition."""
        macro_name = self._extract_identifier(node, lines)
        if not macro_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{macro_name}" if current_scope else macro_name

        signature = self._extract_signature(node, lines, "macro_rules!")

        constructs.append(
            {
                "type": "macro",
                "name": macro_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "macro"},
                "features": ["macro_definition"],
            }
        )

    def _handle_const_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust const declaration."""
        const_name = self._extract_identifier(node, lines)
        if not const_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{const_name}" if current_scope else const_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "pub" in node_text:
            features.append("public")

        signature = self._extract_signature(node, lines, "const")

        constructs.append(
            {
                "type": "const",
                "name": const_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "const"},
                "features": features,
            }
        )

    def _handle_static_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust static declaration."""
        static_name = self._extract_identifier(node, lines)
        if not static_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{static_name}" if current_scope else static_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "pub" in node_text:
            features.append("public")
        if "mut" in node_text:
            features.append("mutable")

        signature = self._extract_signature(node, lines, "static")

        constructs.append(
            {
                "type": "static",
                "name": static_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "static"},
                "features": features,
            }
        )

    def _handle_type_alias(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Rust type alias."""
        type_name = self._extract_identifier(node, lines)
        if not type_name:
            return

        current_scope = "::".join(scope_stack)
        full_path = f"{current_scope}::{type_name}" if current_scope else type_name

        # Check for features
        features = []
        node_text = self._get_node_text(node, lines)
        if "<" in node_text and ">" in node_text:
            features.append("generic")
        if "pub" in node_text:
            features.append("public")

        signature = self._extract_signature(node, lines, "type")

        constructs.append(
            {
                "type": "type",
                "name": type_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "type"},
                "features": features,
            }
        )

    def _process_trait_items(
        self,
        trait_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process items within a trait."""
        for child in trait_node.children:
            if hasattr(child, "type"):
                if child.type == "declaration_list":
                    # Process items inside the declaration list
                    for item in child.children:
                        if hasattr(item, "type") and item.type not in ["{", "}"]:
                            self._handle_language_constructs(
                                item, item.type, constructs, lines, scope_stack, content
                            )
                else:
                    self._handle_language_constructs(
                        child, child.type, constructs, lines, scope_stack, content
                    )

    def _process_impl_items(
        self,
        impl_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process items within an impl block."""
        for child in impl_node.children:
            if hasattr(child, "type"):
                if child.type == "declaration_list":
                    # Process items inside the declaration list
                    for item in child.children:
                        if hasattr(item, "type") and item.type not in ["{", "}"]:
                            self._handle_language_constructs(
                                item, item.type, constructs, lines, scope_stack, content
                            )
                else:
                    self._handle_language_constructs(
                        child, child.type, constructs, lines, scope_stack, content
                    )

    def _extract_impl_target(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract the target type/trait for an impl block."""
        try:
            node_text = self._get_node_text(node, lines)
            # Get just the first line (signature) to avoid matching 'for' in comments/code
            first_line = node_text.split("\n")[0].strip()

            # Handle "impl Trait for Type" and "impl Type" patterns
            if " for " in first_line:
                # Updated regex to handle generics in impl target
                match = re.search(
                    r"impl\s*(?:<[^>]*>)?\s*([^<\s]+(?:<[^>]*>)?)\s+for\s+([^<\s{]+(?:<[^>]*>)?)",
                    first_line,
                )
                if match:
                    return f"{match.group(1)} for {match.group(2)}"
            else:
                # Updated regex to handle generics in impl target
                match = re.search(
                    r"impl\s*(?:<[^>]*>)?\s*([^<\s{]+(?:<[^>]*>)?)", first_line
                )
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    def _extract_function_signature(self, node: Any, lines: List[str]) -> str:
        """Extract function signature including modifiers, name, and parameters."""
        try:
            node_text = self._get_node_text(node, lines)
            # Find the signature part (before the opening brace)
            signature_match = re.match(r"([^{]*)", node_text.strip())
            if signature_match:
                return signature_match.group(1).strip()
        except Exception:
            pass

        return self._get_node_text(node, lines).split("{")[0].strip()

    def _extract_signature(
        self, node: Any, lines: List[str], construct_type: str
    ) -> str:
        """Extract signature for various construct types."""
        try:
            node_text = self._get_node_text(node, lines)
            # For most constructs, the signature is the first line
            first_line = node_text.split("\n")[0].strip()

            # Clean up common patterns
            if "{" in first_line:
                first_line = first_line.split("{")[0].strip()

            return first_line
        except Exception:
            return f"{construct_type} [unknown]"

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        # Use the error text extraction as fallback
        constructs = self._extract_constructs_from_error_text(content, 1, [])

        # Convert constructs to SemanticChunk objects
        chunks = []
        file_ext = Path(file_path).suffix

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

    def _extract_identifier(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a node."""
        # First try the standard approach
        result = self._get_identifier_from_node(node, lines)
        if result:
            return result

        # For Rust, also check for type_identifier nodes
        for child in node.children:
            if hasattr(child, "type") and child.type == "type_identifier":
                return str(self._get_node_text(child, lines)).strip()

        return None
