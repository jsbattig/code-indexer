"""
Ruby semantic parser using tree-sitter with regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Handles Ruby-specific constructs like classes, modules, methods, blocks,
metaprogramming constructs, and more.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class RubySemanticParser(BaseTreeSitterParser):
    """Semantic parser for Ruby files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "ruby")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (require statements, global variables)."""
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "call" and self._is_require_statement(child, lines):
                    require_name = self._extract_require_name(child, lines)
                    if require_name:
                        constructs.append(
                            {
                                "type": "require",
                                "name": require_name,
                                "path": require_name,
                                "signature": f"require '{require_name}'",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "require"},
                                "features": ["require_statement"],
                            }
                        )
                elif child.type == "assignment" and self._is_global_variable(
                    child, lines
                ):
                    var_name = self._extract_global_variable_name(child, lines)
                    if var_name:
                        constructs.append(
                            {
                                "type": "global_variable",
                                "name": var_name,
                                "path": var_name,
                                "signature": self._get_node_text(child, lines).split(
                                    "\n"
                                )[0],
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "global_variable"},
                                "features": ["global_variable"],
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
        """Handle Ruby-specific AST node types."""
        if node_type == "class":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "module":
            self._handle_module_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type in ["method", "singleton_method"]:
            self._handle_method_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type in ["block", "do_block"]:
            self._handle_block_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "lambda":
            self._handle_lambda_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "proc":
            self._handle_proc_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "call" and self._is_mixin_call(node, lines):
            self._handle_mixin_call(node, constructs, lines, scope_stack, content)
        elif node_type == "assignment":
            self._handle_assignment(node, constructs, lines, scope_stack, content)
        elif node_type == "constant_assignment":
            self._handle_constant_assignment(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "alias":
            self._handle_alias_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "symbol":
            self._handle_symbol_declaration(
                node, constructs, lines, scope_stack, content
            )

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped."""
        # Skip children for constructs we handle completely ourselves
        return node_type in [
            "class",
            "module",
            "method",
            "singleton_method",
            "block",
            "do_block",
            "lambda",
            "proc",
        ]

    def _handle_class_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby class declaration."""
        class_name = self._get_identifier_from_node(node, lines)
        if not class_name:
            return

        # Extract superclass
        superclass = self._extract_superclass(node, lines)

        # Build signature
        signature_parts = ["class", class_name]
        if superclass:
            signature_parts.extend(["<", superclass])

        signature = " ".join(signature_parts)

        # Build path
        full_path = "::".join(scope_stack + [class_name])
        parent = "::".join(scope_stack) if scope_stack else None

        # Add class to scope stack for nested processing
        scope_stack.append(class_name)

        # Extract class body constructs
        class_members = self._extract_class_members(node, lines, scope_stack, content)

        # Remove from scope stack
        scope_stack.pop()

        # Create the class construct
        constructs.append(
            {
                "type": "class",
                "name": class_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": "class" if parent else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "class",
                    "superclass": superclass,
                    "member_count": len(class_members),
                },
                "features": self._get_class_features(superclass),
            }
        )

        # Add class members
        constructs.extend(class_members)

    def _handle_module_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby module declaration."""
        module_name = self._get_identifier_from_node(node, lines)
        if not module_name:
            return

        # Build signature
        signature = f"module {module_name}"

        # Build path
        full_path = "::".join(scope_stack + [module_name])
        parent = "::".join(scope_stack) if scope_stack else None

        # Add module to scope stack for nested processing
        scope_stack.append(module_name)

        # Extract module body constructs
        module_members = self._extract_module_members(node, lines, scope_stack, content)

        # Remove from scope stack
        scope_stack.pop()

        constructs.append(
            {
                "type": "module",
                "name": module_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": "module" if parent else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "module",
                    "member_count": len(module_members),
                },
                "features": self._get_module_features(),
            }
        )

        # Add module members
        constructs.extend(module_members)

    def _handle_method_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby method declaration."""
        method_name = self._get_identifier_from_node(node, lines)
        if not method_name:
            return

        # Extract method details
        parameters = self._extract_method_parameters(node, lines)
        visibility = self._extract_method_visibility(node, lines, content)
        is_singleton = node.type == "singleton_method"
        is_class_method = self._is_class_method(node, lines)

        # Build signature
        signature_parts = []
        if visibility and visibility != "public":
            signature_parts.append(visibility)

        if is_singleton or is_class_method:
            signature_parts.append("self.")

        signature_parts.append("def")
        signature_parts.append(method_name)

        if parameters:
            signature_parts.append(parameters)

        signature = " ".join(signature_parts)

        # Build path
        method_path_name = (
            f"self.{method_name}" if (is_singleton or is_class_method) else method_name
        )
        full_path = "::".join(scope_stack + [method_path_name])
        parent = "::".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        # Add method to scope stack for nested processing
        scope_stack.append(method_path_name)

        # Extract method body constructs (blocks, lambdas, etc.)
        method_members = self._extract_method_members(node, lines, scope_stack, content)

        # Remove from scope stack
        scope_stack.pop()

        constructs.append(
            {
                "type": "method",
                "name": method_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "method",
                    "parameters": parameters,
                    "visibility": visibility,
                    "is_singleton": is_singleton,
                    "is_class_method": is_class_method,
                    "member_count": len(method_members),
                },
                "features": self._get_method_features(
                    visibility, is_singleton, is_class_method, method_name
                ),
            }
        )

        # Add method members (blocks, lambdas, etc.)
        constructs.extend(method_members)

    def _handle_block_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby block declaration."""
        # Extract block parameters
        parameters = self._extract_block_parameters(node, lines)

        # Generate a block name based on context
        block_name = f"block_{node.start_point[0] + 1}"

        # Build signature
        signature_parts = ["{"]
        if parameters:
            signature_parts.insert(0, parameters)
            signature_parts.insert(1, "|")
            signature_parts.append("|")
        signature_parts.append("}")

        signature = " ".join(signature_parts)

        # Build path
        full_path = "::".join(scope_stack + [block_name])
        parent = "::".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "block",
                "name": block_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "block",
                    "parameters": parameters,
                },
                "features": self._get_block_features(parameters),
            }
        )

    def _handle_lambda_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby lambda declaration."""
        # Extract lambda parameters
        parameters = self._extract_lambda_parameters(node, lines)

        # Generate a lambda name based on context
        lambda_name = f"lambda_{node.start_point[0] + 1}"

        # Build signature
        signature_parts = ["lambda"]
        if parameters:
            signature_parts.extend(["{", parameters, "|"])
        else:
            signature_parts.append("{")
        signature_parts.append("}")

        signature = " ".join(signature_parts)

        # Build path
        full_path = "::".join(scope_stack + [lambda_name])
        parent = "::".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "lambda",
                "name": lambda_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "lambda",
                    "parameters": parameters,
                },
                "features": self._get_lambda_features(parameters),
            }
        )

    def _handle_proc_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby Proc declaration."""
        # Extract proc parameters
        parameters = self._extract_proc_parameters(node, lines)

        # Generate a proc name based on context
        proc_name = f"proc_{node.start_point[0] + 1}"

        # Build signature
        signature_parts = ["Proc.new"]
        if parameters:
            signature_parts.extend(["{", parameters, "|"])
        else:
            signature_parts.append("{")
        signature_parts.append("}")

        signature = " ".join(signature_parts)

        # Build path
        full_path = "::".join(scope_stack + [proc_name])
        parent = "::".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "proc",
                "name": proc_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "proc",
                    "parameters": parameters,
                },
                "features": self._get_proc_features(parameters),
            }
        )

    def _handle_mixin_call(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby mixin calls (include, extend, prepend)."""
        mixin_type = self._extract_mixin_type(node, lines)
        module_name = self._extract_mixin_module_name(node, lines)

        if not mixin_type or not module_name:
            return

        # Build signature
        signature = f"{mixin_type} {module_name}"

        # Build path
        mixin_name = f"{mixin_type}_{module_name}"
        full_path = "::".join(scope_stack + [mixin_name])
        parent = "::".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "mixin",
                "name": mixin_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "mixin",
                    "mixin_type": mixin_type,
                    "module_name": module_name,
                },
                "features": self._get_mixin_features(mixin_type),
            }
        )

    def _handle_assignment(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby variable assignments (instance, class variables).

        CRITICAL FIX: Only create separate chunks for assignments at CLASS/MODULE level.
        Do NOT create separate chunks for assignments inside methods - they should be
        part of the method chunk to maintain cohesion.
        """
        var_name = self._extract_assignment_variable_name_ast(node)
        if not var_name:
            return

        # Determine variable type using AST node properties
        var_type = self._determine_variable_type_ast(node)

        # COHESION FIX: Only create separate chunks for class/module level assignments
        # Skip method-internal assignments - they'll be part of method chunk
        if self._is_inside_method_scope(scope_stack):
            # Skip - let method handle its internal assignments
            return

        if var_type in ["instance_variable", "class_variable"]:
            # Build signature
            assignment_text = self._get_node_text(node, lines).split("\n")[0]
            signature = assignment_text.strip()

            # Build path
            full_path = "::".join(scope_stack + [var_name])
            parent = "::".join(scope_stack) if scope_stack else None
            scope = scope_stack[-1] if scope_stack else "global"

            constructs.append(
                {
                    "type": var_type,
                    "name": var_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": parent,
                    "scope": scope,
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": var_type,
                        "assignment": assignment_text,
                    },
                    "features": self._get_variable_features(var_type),
                }
            )

    def _handle_constant_assignment(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby constant assignments."""
        const_name = self._extract_constant_name(node, lines)
        if not const_name:
            return

        # Build signature
        assignment_text = self._get_node_text(node, lines).split("\n")[0]
        signature = assignment_text.strip()

        # Build path
        full_path = "::".join(scope_stack + [const_name])
        parent = "::".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "constant",
                "name": const_name,
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "constant",
                    "assignment": assignment_text,
                },
                "features": self._get_constant_features(),
            }
        )

    def _handle_alias_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby alias declarations."""
        alias_info = self._extract_alias_info(node, lines)
        if not alias_info:
            return

        new_name, original_name = alias_info

        # Build signature
        signature = f"alias {new_name} {original_name}"

        # Build path
        full_path = "::".join(scope_stack + [f"alias_{new_name}"])
        parent = "::".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "alias",
                "name": f"alias_{new_name}",
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "alias",
                    "new_name": new_name,
                    "original_name": original_name,
                },
                "features": self._get_alias_features(),
            }
        )

    def _handle_symbol_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Ruby symbol declarations (when significant)."""
        symbol_name = self._extract_symbol_name(node, lines)
        if not symbol_name or not self._is_significant_symbol(symbol_name):
            return

        # Build signature
        signature = f":{symbol_name}"

        # Build path
        full_path = "::".join(scope_stack + [f"symbol_{symbol_name}"])
        parent = "::".join(scope_stack) if scope_stack else None
        scope = scope_stack[-1] if scope_stack else "global"

        constructs.append(
            {
                "type": "symbol",
                "name": f"symbol_{symbol_name}",
                "path": full_path,
                "signature": signature,
                "parent": parent,
                "scope": scope,
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "symbol",
                    "symbol_name": symbol_name,
                },
                "features": self._get_symbol_features(),
            }
        )

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract Ruby constructs from ERROR node text using regex fallback."""
        constructs = []

        # Ruby-specific regex patterns
        patterns = {
            "class": r"^\s*class\s+(\w+)(?:\s*<\s*(\w+))?\s*$",
            "module": r"^\s*module\s+(\w+)\s*$",
            "method": r"^\s*def\s+(?:self\.)?(\w+)(?:\([^)]*\))?\s*$",
            "singleton_method": r"^\s*def\s+self\.(\w+)(?:\([^)]*\))?\s*$",
            "instance_variable": r"^\s*@(\w+)\s*=",
            "class_variable": r"^\s*@@(\w+)\s*=",
            "constant": r"^\s*([A-Z][A-Z_]*)\s*=",
            "require": r"^\s*require\s+['\"]([^'\"]+)['\"]",
            "include": r"^\s*include\s+(\w+)",
            "extend": r"^\s*extend\s+(\w+)",
            "prepend": r"^\s*prepend\s+(\w+)",
            "alias": r"^\s*alias\s+(\w+)\s+(\w+)",
        }

        lines = error_text.split("\n")

        for line_idx, line in enumerate(lines):
            for construct_type, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    # Extract name based on construct type
                    if construct_type == "class":
                        name = match.group(1)
                        superclass = (
                            match.group(2)
                            if match.lastindex and match.lastindex >= 2
                            else None
                        )
                        signature = f"class {name}"
                        if superclass:
                            signature += f" < {superclass}"
                    elif construct_type in ["singleton_method", "method"]:
                        name = match.group(1)
                        signature = f"def {name}"
                        if construct_type == "singleton_method":
                            signature = f"def self.{name}"
                    elif construct_type in ["include", "extend", "prepend"]:
                        name = f"{construct_type}_{match.group(1)}"
                        signature = f"{construct_type} {match.group(1)}"
                    elif construct_type == "alias":
                        name = f"alias_{match.group(1)}"
                        signature = f"alias {match.group(1)} {match.group(2)}"
                    else:
                        name = match.group(1)
                        signature = line.strip()

                    # Build construct
                    construct = {
                        "type": construct_type,
                        "name": name,
                        "path": "::".join(scope_stack + [name]),
                        "signature": signature,
                        "parent": "::".join(scope_stack) if scope_stack else None,
                        "scope": scope_stack[-1] if scope_stack else "global",
                        "line_start": start_line + line_idx + 1,
                        "line_end": start_line + line_idx + 1,  # Single line fallback
                        "text": line,
                        "context": {
                            "extracted_from_error": True,
                            "fallback_parsing": True,
                        },
                        "features": [f"{construct_type}_fallback"],
                    }

                    constructs.append(construct)

        return constructs

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        patterns = {
            "class": r"^\s*class\s+(\w+)(?:\s*<\s*(\w+))?\s*$",
            "module": r"^\s*module\s+(\w+)\s*$",
            "method": r"^\s*def\s+(\w+)(?:\([^)]*\))?\s*$",
            "singleton_method": r"^\s*def\s+self\.(\w+)(?:\([^)]*\))?\s*$",
            "constant": r"^\s*([A-Z][A-Z_]*)\s*=",
        }

        constructs = self._find_constructs_with_regex(content, patterns, file_path)

        if not constructs:
            # Create a fallback chunk for the entire file
            lines = content.split("\n")
            return [
                SemanticChunk(
                    text=content,
                    chunk_index=0,
                    total_chunks=1,
                    size=len(content),
                    file_path=file_path,
                    file_extension=Path(file_path).suffix,
                    line_start=1,
                    line_end=len(lines),
                    semantic_chunking=False,
                    semantic_type="module",
                    semantic_name=Path(file_path).stem,
                    semantic_path=Path(file_path).stem,
                    semantic_signature=f"module {Path(file_path).stem}",
                    semantic_parent=None,
                    semantic_context={"fallback_parsing": True},
                    semantic_scope="global",
                    semantic_language_features=["fallback_chunk"],
                )
            ]

        # Convert constructs to semantic chunks
        chunks = []
        for i, construct in enumerate(constructs):
            chunk = SemanticChunk(
                text=construct["text"],
                chunk_index=i,
                total_chunks=len(constructs),
                size=len(construct["text"]),
                file_path=file_path,
                file_extension=Path(file_path).suffix,
                line_start=construct["line_start"],
                line_end=construct["line_end"],
                semantic_chunking=False,
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

    # Override base class methods for Ruby-specific behavior

    def _get_identifier_from_node(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract identifier name from a Ruby node using pure AST."""
        # Ruby uses different node types for names:
        # - classes/modules use "constant"
        # - methods use "identifier"
        for child in node.children:
            if hasattr(child, "type"):
                if child.type in ["identifier", "constant"]:
                    # Use AST text property directly instead of regex
                    if hasattr(child, "text"):
                        return str(child.text.decode("utf-8")).strip()
                    elif lines:
                        return str(self._get_node_text(child, lines)).strip()
        return None

    # Helper methods for extracting Ruby-specific constructs

    def _is_require_statement(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> bool:
        """Check if a call node is a require statement using AST."""
        # Look for method call with identifier 'require'
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                if hasattr(child, "text"):
                    method_name = str(child.text.decode("utf-8"))
                    return method_name in ["require", "require_relative", "load"]
                elif lines:
                    method_name = str(self._get_node_text(child, lines))
                    return method_name in ["require", "require_relative", "load"]
        return False

    def _extract_require_name(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract the name from a require statement using AST."""
        # Look for string argument in the call
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "string":
                    if hasattr(child, "text"):
                        # Remove quotes from string
                        text = str(child.text.decode("utf-8"))
                        return text.strip("\"'")
                    elif lines:
                        text = str(self._get_node_text(child, lines))
                        return text.strip("\"'")
                elif child.type == "argument_list":
                    # Look inside argument list for string
                    for grandchild in child.children:
                        if hasattr(grandchild, "type") and grandchild.type == "string":
                            if hasattr(grandchild, "text"):
                                text = str(grandchild.text.decode("utf-8"))
                                return text.strip("\"'")
                            elif lines:
                                text = str(self._get_node_text(grandchild, lines))
                                return text.strip("\"'")
        return None

    def _is_global_variable(self, node: Any, lines: Optional[List[str]] = None) -> bool:
        """Check if an assignment is to a global variable using AST."""
        # Look for global_variable node type in assignment
        for child in node.children:
            if hasattr(child, "type") and child.type == "global_variable":
                return True
        return False

    def _extract_global_variable_name(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract global variable name from assignment using AST."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "global_variable":
                if hasattr(child, "text"):
                    return str(child.text.decode("utf-8"))
                elif lines:
                    return str(self._get_node_text(child, lines))
        return None

    def _extract_superclass(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract superclass from class declaration using AST."""
        # Look for superclass node in class declaration
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "superclass":
                    # Superclass node contains the parent class name
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "constant"
                        ):
                            if hasattr(grandchild, "text"):
                                return str(grandchild.text.decode("utf-8"))
                            elif lines:
                                return str(self._get_node_text(grandchild, lines))
        return None

    def _extract_method_parameters(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract method parameter list using AST."""
        # Look for method_parameters or parameters node
        for child in node.children:
            if hasattr(child, "type"):
                if child.type in ["method_parameters", "parameters", "parameter_list"]:
                    if hasattr(child, "text"):
                        text = str(child.text.decode("utf-8"))
                        return f"({text})" if not text.startswith("(") else text
                    elif lines:
                        text = str(self._get_node_text(child, lines))
                        return f"({text})" if not text.startswith("(") else text
        return None

    def _extract_method_visibility(
        self, node: Any, lines: List[str], content: str
    ) -> Optional[str]:
        """Extract method visibility (private, protected, public)."""
        # Look for visibility modifiers before the method
        method_line = node.start_point[0]
        for i in range(max(0, method_line - 10), method_line):
            if i < len(lines):
                line = lines[i].strip()
                if line in ["private", "protected", "public"]:
                    return line
        return "public"  # Default visibility

    def _is_class_method(self, node: Any, lines: Optional[List[str]] = None) -> bool:
        """Check if method is a class method (self.method_name) using AST."""
        # Check if this is a singleton_method node type
        if hasattr(node, "type") and node.type == "singleton_method":
            return True

        # Look for 'self' receiver in method definition
        for child in node.children:
            if hasattr(child, "type") and child.type == "self":
                return True
        return False

    def _extract_block_parameters(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract block parameters using AST."""
        # Look for block_parameters node
        for child in node.children:
            if hasattr(child, "type"):
                if child.type in ["block_parameters", "lambda_parameters"]:
                    if hasattr(child, "text"):
                        text = str(child.text.decode("utf-8"))
                        # Remove the pipe characters
                        return text.strip("|").strip()
                    elif lines:
                        text = str(self._get_node_text(child, lines))
                        return text.strip("|").strip()
        return None

    def _extract_lambda_parameters(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract lambda parameters using AST."""
        # Same as block parameters - lambdas use similar parameter structure
        return self._extract_block_parameters(node, lines)

    def _extract_proc_parameters(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract Proc parameters using AST."""
        # Same as block parameters - Procs use similar parameter structure
        return self._extract_block_parameters(node, lines)

    def _is_mixin_call(self, node: Any, lines: Optional[List[str]] = None) -> bool:
        """Check if call is a mixin (include, extend, prepend) using AST."""
        # Look for method call with specific identifiers
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                if hasattr(child, "text"):
                    method_name = child.text.decode("utf-8")
                    return method_name in ["include", "extend", "prepend"]
                elif lines:
                    method_name = self._get_node_text(child, lines)
                    return method_name in ["include", "extend", "prepend"]
        return False

    def _extract_mixin_type(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract mixin type (include, extend, prepend) using AST."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                if hasattr(child, "text"):
                    method_name = str(child.text.decode("utf-8"))
                    if method_name in ["include", "extend", "prepend"]:
                        return method_name
                elif lines:
                    method_name = str(self._get_node_text(child, lines))
                    if method_name in ["include", "extend", "prepend"]:
                        return method_name
        return None

    def _extract_mixin_module_name(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract module name from mixin call using AST."""
        # Look for constant argument after the mixin method
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "constant":
                    if hasattr(child, "text"):
                        return str(child.text.decode("utf-8"))
                    elif lines:
                        return str(self._get_node_text(child, lines))
                elif child.type == "argument_list":
                    # Look inside argument list for constant
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "constant"
                        ):
                            if hasattr(grandchild, "text"):
                                return str(grandchild.text.decode("utf-8"))
                            elif lines:
                                return str(self._get_node_text(grandchild, lines))
        return None

    def _extract_assignment_variable_name_ast(self, node: Any) -> Optional[str]:
        """Extract variable name from assignment using AST node properties."""
        # Use AST structure instead of regex
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "instance_variable":
                    return (
                        str(child.text.decode("utf-8"))
                        if hasattr(child, "text")
                        else None
                    )
                elif child.type == "class_variable":
                    return (
                        str(child.text.decode("utf-8"))
                        if hasattr(child, "text")
                        else None
                    )
                elif child.type == "global_variable":
                    return (
                        str(child.text.decode("utf-8"))
                        if hasattr(child, "text")
                        else None
                    )
        return None

    def _determine_variable_type_ast(self, node: Any) -> str:
        """Determine variable type using AST node properties instead of regex."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "instance_variable":
                    return "instance_variable"
                elif child.type == "class_variable":
                    return "class_variable"
                elif child.type == "global_variable":
                    return "global_variable"
                elif child.type == "constant":
                    return "constant"
        return "local_variable"

    def _is_inside_method_scope(self, scope_stack: List[str]) -> bool:
        """Check if current scope is inside a method using scope stack analysis."""
        # Look for method-like scope names in the stack
        for scope in scope_stack:
            # Method scopes contain method names or self.method names
            if not scope or scope == "global":
                continue
            # If scope contains a method indicator or is a simple name (likely method)
            # and is not a class/module name (those typically start with capital)
            if (
                not scope[0].isupper()
                or "." in scope
                or any(
                    method_name in scope
                    for method_name in ["initialize", "new", "create"]
                )
            ):
                return True
        return False

    def _extract_assignment_variable_name(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract variable name from assignment - LEGACY METHOD for fallback."""
        node_text = self._get_node_text(node, lines)
        # Look for instance or class variables
        match = re.search(r"(@@?\w+)", node_text)
        return match.group(1) if match else None

    def _determine_variable_type(self, var_name: str) -> str:
        """Determine the type of variable based on its name - LEGACY METHOD."""
        if var_name.startswith("@@"):
            return "class_variable"
        elif var_name.startswith("@"):
            return "instance_variable"
        elif var_name.startswith("$"):
            return "global_variable"
        elif var_name.isupper():
            return "constant"
        else:
            return "local_variable"

    def _extract_constant_name(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract constant name from constant assignment using AST."""
        # Look for constant node on left side of assignment
        for child in node.children:
            if hasattr(child, "type") and child.type == "constant":
                if hasattr(child, "text"):
                    return str(child.text.decode("utf-8"))
                elif lines:
                    return str(self._get_node_text(child, lines))
        return None

    def _extract_alias_info(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[tuple]:
        """Extract alias information (new_name, original_name) using AST."""
        # Alias nodes typically have two identifier children
        identifiers = []
        for child in node.children:
            if hasattr(child, "type") and child.type in ["identifier", "symbol"]:
                if hasattr(child, "text"):
                    text = str(child.text.decode("utf-8"))
                    identifiers.append(text.lstrip(":"))  # Remove : from symbols
                elif lines:
                    text = str(self._get_node_text(child, lines))
                    identifiers.append(text.lstrip(":"))

        if len(identifiers) >= 2:
            return (identifiers[0], identifiers[1])
        return None

    def _extract_symbol_name(
        self, node: Any, lines: Optional[List[str]] = None
    ) -> Optional[str]:
        """Extract symbol name using AST."""
        if hasattr(node, "type") and node.type == "symbol":
            if hasattr(node, "text"):
                text = str(node.text.decode("utf-8"))
                return text.lstrip(":")  # Remove the colon prefix
            elif lines:
                text = str(self._get_node_text(node, lines))
                return text.lstrip(":")
        return None

    def _is_significant_symbol(self, symbol_name: str) -> bool:
        """Determine if a symbol is significant enough to track."""
        # Only track symbols that are likely to be important
        # (method names, attribute accessors, etc.)
        return len(symbol_name) > 2 and not symbol_name.isdigit()

    def _extract_class_members(
        self, node: Any, lines: List[str], scope_stack: List[str], content: str
    ) -> List[Dict[str, Any]]:
        """Extract all members from a class declaration."""
        members: List[Dict[str, Any]] = []

        # Process all children to find class members
        for child in node.children:
            if hasattr(child, "type"):
                # Recursively traverse to find methods, constants, etc.
                self._traverse_node(child, members, lines, scope_stack, content)

        return members

    def _extract_module_members(
        self, node: Any, lines: List[str], scope_stack: List[str], content: str
    ) -> List[Dict[str, Any]]:
        """Extract all members from a module declaration."""
        members: List[Dict[str, Any]] = []

        # Process all children to find module members
        for child in node.children:
            if hasattr(child, "type"):
                # Recursively traverse to find methods, constants, etc.
                self._traverse_node(child, members, lines, scope_stack, content)

        return members

    def _extract_method_members(
        self, node: Any, lines: List[str], scope_stack: List[str], content: str
    ) -> List[Dict[str, Any]]:
        """Extract all members from a method declaration (blocks, lambdas, etc.)."""
        members: List[Dict[str, Any]] = []

        # Process all children to find method members
        for child in node.children:
            if hasattr(child, "type"):
                # Recursively traverse to find blocks, lambdas, etc.
                self._traverse_node(child, members, lines, scope_stack, content)

        return members

    # Feature extraction methods

    def _get_class_features(self, superclass: Optional[str]) -> List[str]:
        """Get features for class declarations."""
        features = ["class_declaration"]
        if superclass:
            features.extend(["inheritance", f"inherits_from_{superclass}"])
        return features

    def _get_module_features(self) -> List[str]:
        """Get features for module declarations."""
        return ["module_declaration"]

    def _get_method_features(
        self,
        visibility: Optional[str],
        is_singleton: bool,
        is_class_method: bool,
        method_name: str,
    ) -> List[str]:
        """Get features for method declarations."""
        features = ["method_declaration"]
        if visibility and visibility != "public":
            features.append(f"visibility_{visibility}")
        if is_singleton or is_class_method:
            features.append("class_method")
        if method_name.startswith("_"):
            features.append("private_method")
        if method_name.endswith("?"):
            features.append("predicate_method")
        if method_name.endswith("!"):
            features.append("mutating_method")
        return features

    def _get_block_features(self, parameters: Optional[str]) -> List[str]:
        """Get features for block declarations."""
        features = ["block_declaration"]
        if parameters:
            features.append("parametrized_block")
        return features

    def _get_lambda_features(self, parameters: Optional[str]) -> List[str]:
        """Get features for lambda declarations."""
        features = ["lambda_declaration"]
        if parameters:
            features.append("parametrized_lambda")
        return features

    def _get_proc_features(self, parameters: Optional[str]) -> List[str]:
        """Get features for proc declarations."""
        features = ["proc_declaration"]
        if parameters:
            features.append("parametrized_proc")
        return features

    def _get_mixin_features(self, mixin_type: str) -> List[str]:
        """Get features for mixin declarations."""
        return ["mixin_declaration", f"{mixin_type}_mixin"]

    def _get_variable_features(self, var_type: str) -> List[str]:
        """Get features for variable declarations."""
        return ["variable_declaration", var_type]

    def _get_constant_features(self) -> List[str]:
        """Get features for constant declarations."""
        return ["constant_declaration"]

    def _get_alias_features(self) -> List[str]:
        """Get features for alias declarations."""
        return ["alias_declaration", "metaprogramming"]

    def _get_symbol_features(self) -> List[str]:
        """Get features for symbol declarations."""
        return ["symbol_declaration"]
