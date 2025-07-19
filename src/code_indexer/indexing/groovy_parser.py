"""
Groovy semantic parser using tree-sitter.

This implementation uses tree-sitter to parse Groovy code and extract
semantic information for chunking. Supports:
- Classes/Interfaces/Enums/Traits
- Methods/Functions/Closures
- Properties/Fields
- Annotations
- Script mode vs class mode
- Gradle build scripts (Groovy DSL)
- ERROR node handling with regex fallback
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser


class GroovySemanticParser(BaseTreeSitterParser):
    """Semantic parser for Groovy files using tree-sitter."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "groovy")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (package declarations, imports, etc.)."""
        # Look for package declarations
        for child in root_node.children:
            if hasattr(child, "type") and child.type == "command":
                # Check if this is a package declaration
                if self._is_package_declaration(child, lines):
                    package_name = self._extract_package_name(child, lines)
                    if package_name:
                        scope_stack.append(package_name)
                        constructs.append(
                            {
                                "type": "package",
                                "name": package_name,
                                "path": package_name,
                                "signature": f"package {package_name}",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "package"},
                                "features": ["package_declaration"],
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
        """Handle Groovy-specific AST node types."""
        if node_type == "command":
            self._handle_command_node(node, constructs, lines, scope_stack, content)
        elif node_type == "block":
            self._handle_block_node(node, constructs, lines, scope_stack, content)
        elif node_type == "unit":
            self._handle_unit_node(node, constructs, lines, scope_stack, content)

    def _handle_command_node(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle command nodes (class, def, etc.)."""
        # Check if this is a class declaration
        if self._is_class_declaration(node, lines):
            self._extract_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif self._is_interface_declaration(node, lines):
            self._extract_interface_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif self._is_trait_declaration(node, lines):
            self._extract_trait_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif self._is_closure_assignment(node, lines):
            self._extract_closure_assignment(
                node, constructs, lines, scope_stack, content
            )
        elif self._is_method_declaration(node, lines):
            self._extract_method_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif self._is_field_declaration(node, lines):
            self._extract_field_declaration(
                node, constructs, lines, scope_stack, content
            )

    def _handle_block_node(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle block nodes (class bodies, method bodies, etc.)."""
        # Block nodes typically contain the body of classes/methods
        # We'll traverse their children to find constructs
        pass

    def _handle_unit_node(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle unit nodes (identifiers, literals, etc.)."""
        # Unit nodes are typically leaf nodes or simple constructs
        pass

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children of this node type should be skipped."""
        # Skip children for nodes that handle their own members
        return node_type in ["class_body", "method_body"]

    def _is_package_declaration(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents a package declaration."""
        node_text = self._get_node_text(node, lines).strip()
        return node_text.startswith("package ")

    def _extract_package_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract package name from package declaration."""
        node_text = self._get_node_text(node, lines).strip()
        match = re.match(r"package\s+([\w.]+)", node_text)
        return match.group(1) if match else None

    def _is_class_declaration(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents a class declaration."""
        node_text = self._get_node_text(node, lines).strip()
        return (
            re.match(
                r"(@\w+\s*)*\s*(public|private|protected)?\s*class\s+\w+", node_text
            )
            is not None
        )

    def _is_interface_declaration(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents an interface declaration."""
        node_text = self._get_node_text(node, lines).strip()
        return (
            re.match(
                r"(@\w+\s*)*\s*(public|private|protected)?\s*interface\s+\w+", node_text
            )
            is not None
        )

    def _is_trait_declaration(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents a trait declaration."""
        node_text = self._get_node_text(node, lines).strip()
        return (
            re.match(
                r"(@\w+\s*)*\s*(public|private|protected)?\s*trait\s+\w+", node_text
            )
            is not None
        )

    def _is_method_declaration(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents a method declaration."""
        node_text = self._get_node_text(node, lines).strip()
        # Look for def keyword or method signature patterns
        return (
            re.match(
                r"(@\w+\s*)*\s*(public|private|protected|static)?\s*def\s+\w+",
                node_text,
            )
            is not None
            or re.match(
                r"(@\w+\s*)*\s*(public|private|protected|static)?\s*\w+\s+\w+\s*\(",
                node_text,
            )
            is not None
        )

    def _is_closure_assignment(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents a closure assignment."""
        # Look for the specific AST pattern: unit followed by block with { ... }
        if not hasattr(node, "children") or len(node.children) < 3:
            return False

        # Check if we have the pattern: unit(def/type) unit(name) block(= { ... })
        children = list(node.children)
        if len(children) >= 3:
            first_child = children[0]
            second_child = children[1]
            third_child = children[2]

            # Check if we have a valid pattern
            if (
                hasattr(first_child, "type")
                and first_child.type == "unit"
                and hasattr(second_child, "type")
                and second_child.type == "unit"
                and hasattr(third_child, "type")
                and third_child.type == "block"
            ):

                # Check if third child is a block starting with = and containing {
                block_text = self._get_node_text(third_child, lines).strip()
                if block_text.startswith("=") and "{" in block_text:
                    return True

        # Also check text-based pattern as fallback
        node_text = self._get_node_text(node, lines).strip()
        return re.match(r"(def\s+|[\w<>]+\s+)?\w+\s*=\s*\{", node_text) is not None

    def _is_field_declaration(self, node: Any, lines: List[str]) -> bool:
        """Check if node represents a field declaration."""
        node_text = self._get_node_text(node, lines).strip()
        # Look for field patterns (type + name, or just name with assignment)
        return (
            re.match(
                r"(@\w+\s*)*\s*(public|private|protected|static|final)?\s*\w+\s+\w+",
                node_text,
            )
            is not None
            or re.match(
                r"(@\w+\s*)*\s*(public|private|protected|static|final)?\s*\w+\s*=",
                node_text,
            )
            is not None
        )

    def _extract_class_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract class declaration information."""
        node_text = self._get_node_text(node, lines)

        # Extract class name
        class_match = re.search(r"class\s+(\w+)", node_text)
        if not class_match:
            return

        class_name = class_match.group(1)

        # Extract annotations
        annotations = re.findall(r"@(\w+)", node_text)

        # Extract modifiers
        modifiers = []
        for modifier in [
            "public",
            "private",
            "protected",
            "abstract",
            "final",
            "static",
        ]:
            if re.search(rf"\b{modifier}\b", node_text):
                modifiers.append(modifier)

        # Extract inheritance
        inheritance = None
        extends_match = re.search(r"extends\s+([\w.]+)", node_text)
        if extends_match:
            inheritance = extends_match.group(1)

        implements_match = re.search(r"implements\s+([\w.,\s]+)", node_text)
        implements = []
        if implements_match:
            implements = [impl.strip() for impl in implements_match.group(1).split(",")]

        # Build path
        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{class_name}" if parent_path else class_name

        # Build signature
        signature = "class " + class_name
        if inheritance:
            signature += f" extends {inheritance}"
        if implements:
            signature += f" implements {', '.join(implements)}"

        features = ["class_declaration"]
        if annotations:
            features.append("annotated")
        if modifiers:
            features.extend(modifiers)

        constructs.append(
            {
                "type": "class",
                "name": class_name,
                "path": full_path,
                "signature": signature,
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "global" if not scope_stack else "class",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {
                    "declaration_type": "class",
                    "annotations": annotations,
                    "modifiers": modifiers,
                    "extends": inheritance,
                    "implements": implements,
                },
                "features": features,
            }
        )

        # Add class to scope stack for processing members
        scope_stack.append(class_name)
        try:
            # Process class body for members
            self._process_class_body(node, constructs, lines, scope_stack, content)
        finally:
            scope_stack.pop()

    def _extract_interface_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract interface declaration information."""
        node_text = self._get_node_text(node, lines)

        # Extract interface name
        interface_match = re.search(r"interface\s+(\w+)", node_text)
        if not interface_match:
            return

        interface_name = interface_match.group(1)

        # Build path
        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{interface_name}" if parent_path else interface_name

        constructs.append(
            {
                "type": "interface",
                "name": interface_name,
                "path": full_path,
                "signature": f"interface {interface_name}",
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "global" if not scope_stack else "interface",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {"declaration_type": "interface"},
                "features": ["interface_declaration"],
            }
        )

    def _extract_trait_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract trait declaration information."""
        node_text = self._get_node_text(node, lines)

        # Extract trait name
        trait_match = re.search(r"trait\s+(\w+)", node_text)
        if not trait_match:
            return

        trait_name = trait_match.group(1)

        # Build path
        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{trait_name}" if parent_path else trait_name

        constructs.append(
            {
                "type": "trait",
                "name": trait_name,
                "path": full_path,
                "signature": f"trait {trait_name}",
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "global" if not scope_stack else "trait",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {"declaration_type": "trait"},
                "features": ["trait_declaration"],
            }
        )

    def _extract_method_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract method declaration information."""
        node_text = self._get_node_text(node, lines)

        # Extract method name - improved pattern matching
        def_match = re.search(r"def\s+(\w+)", node_text)
        typed_match = re.search(r"(\w+)\s+(\w+)\s*\(", node_text)
        void_match = re.search(r"void\s+(\w+)\s*\(", node_text)

        if def_match:
            method_name = def_match.group(1)
            return_type = None
        elif void_match:
            method_name = void_match.group(1)
            return_type = "void"
        elif typed_match:
            return_type = typed_match.group(1)
            method_name = typed_match.group(2)
        else:
            return

        # Extract annotations from current node and preceding annotation nodes
        annotations = re.findall(r"@(\w+)", node_text, re.MULTILINE)

        # Look for preceding annotation nodes (sibling nodes that are decoration/annotation commands)
        if hasattr(node, "parent") and node.parent:
            preceding_annotations = self._find_preceding_annotations(node, lines)
            annotations.extend(preceding_annotations)

        # Extract modifiers
        modifiers = []
        for modifier in [
            "public",
            "private",
            "protected",
            "static",
            "abstract",
            "final",
        ]:
            if re.search(rf"\b{modifier}\b", node_text):
                modifiers.append(modifier)

        # Extract parameters
        param_match = re.search(r"\(([^)]*)\)", node_text, re.DOTALL)
        parameters = param_match.group(1).strip() if param_match else ""

        # Build path
        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{method_name}" if parent_path else method_name

        # Build signature
        if return_type and return_type != "def":
            signature = f"{return_type} {method_name}"
        else:
            signature = f"def {method_name}"

        if parameters:
            signature += f"({parameters})"

        features = ["method_declaration"]
        if annotations:
            features.append("annotated")
        if modifiers:
            features.extend(modifiers)

        method_type = "method" if scope_stack else "function"

        constructs.append(
            {
                "type": method_type,
                "name": method_name,
                "path": full_path,
                "signature": signature,
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "method",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {
                    "declaration_type": method_type,
                    "annotations": annotations,
                    "modifiers": modifiers,
                    "parameters": parameters,
                    "return_type": return_type,
                },
                "features": features,
            }
        )

    def _extract_closure_assignment(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract closure assignment information."""
        node_text = self._get_node_text(node, lines)

        # Extract closure name and parameters
        # Try different patterns for closure assignment
        closure_match = re.search(
            r"(def\s+)?(\w+)\s*=\s*\{\s*([^}]*?)\s*->", node_text, re.DOTALL
        )
        if not closure_match:
            # Try simple closure assignment without parameters
            simple_match = re.search(r"(def\s+)?(\w+)\s*=\s*\{", node_text)
            if simple_match:
                closure_name = simple_match.group(2)
                parameters = ""
            else:
                return
        else:
            closure_name = closure_match.group(2)
            parameters = (
                closure_match.group(3).strip() if closure_match.group(3) else ""
            )

        # Extract type information if present
        type_match = re.search(r"(\w+(?:<[^>]+>)?)\s+(\w+)\s*=\s*\{", node_text)
        closure_type = None
        if type_match:
            closure_type = type_match.group(1)
            closure_name = type_match.group(2)

        # Build path
        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{closure_name}" if parent_path else closure_name

        # Build signature
        if closure_type:
            signature = f"{closure_type} {closure_name} = {{"
        else:
            signature = f"{closure_name} = {{"

        if parameters:
            signature += f" {parameters} ->"

        constructs.append(
            {
                "type": "closure",
                "name": closure_name,
                "path": full_path,
                "signature": signature,
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "closure",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {
                    "declaration_type": "closure",
                    "parameters": parameters,
                    "closure_type": closure_type,
                },
                "features": ["closure_declaration"],
            }
        )

    def _extract_field_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract field declaration information."""
        node_text = self._get_node_text(node, lines)

        # Extract field name and type with better regex
        # Handle patterns like: [modifiers] Type fieldName [= value]
        field_match = re.search(
            r"(?:@\w+\s*)*\s*(?:(public|private|protected|static|final)\s+)*(?:(\w+(?:<[^>]+>)?)\s+)?(\w+)(?:\s*=|;|$)",
            node_text,
        )

        if not field_match:
            return

        field_type = field_match.group(2)
        field_name = field_match.group(3)

        # Skip if this looks like a method (has parentheses)
        if "(" in node_text and ")" in node_text:
            return

        # Extract annotations from current node and preceding annotation nodes
        annotations = re.findall(r"@(\w+)", node_text)

        # Look for preceding annotation nodes (sibling nodes that are decoration/annotation commands)
        if hasattr(node, "parent") and node.parent:
            preceding_annotations = self._find_preceding_annotations(node, lines)
            annotations.extend(preceding_annotations)

        # Extract modifiers
        modifiers = []
        for modifier in ["public", "private", "protected", "static", "final"]:
            if re.search(rf"\b{modifier}\b", node_text):
                modifiers.append(modifier)

        # Build path
        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{field_name}" if parent_path else field_name

        # Build signature
        if field_type:
            signature = f"{field_type} {field_name}"
        else:
            signature = field_name

        # Add modifiers to signature if present
        if modifiers:
            signature = f"{' '.join(modifiers)} {signature}"

        features = ["field_declaration"]
        if annotations:
            features.append("annotated")
        if modifiers:
            features.extend(modifiers)

        construct_type = (
            "property" if not modifiers or "private" not in modifiers else "field"
        )

        constructs.append(
            {
                "type": construct_type,
                "name": field_name,
                "path": full_path,
                "signature": signature,
                "parent": scope_stack[-1] if scope_stack else None,
                "scope": "global" if not scope_stack else "class",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": node_text,
                "context": {
                    "declaration_type": construct_type,
                    "annotations": annotations,
                    "modifiers": modifiers,
                    "field_type": field_type,
                },
                "features": features,
            }
        )

    def _process_class_body(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process class body to find member declarations."""
        # Find block node containing class body
        for child in node.children:
            if hasattr(child, "type") and child.type == "block":
                # Recursively process all children in the class body
                for body_child in child.children:
                    self._traverse_node(
                        body_child, constructs, lines, scope_stack, content
                    )

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract constructs from ERROR node text using regex fallback."""
        # Define regex patterns for Groovy constructs
        patterns = {
            "class": r"(?:@\w+\s*)*\s*(?:public|private|protected)?\s*class\s+(\w+)",
            "interface": r"(?:@\w+\s*)*\s*(?:public|private|protected)?\s*interface\s+(\w+)",
            "trait": r"(?:@\w+\s*)*\s*(?:public|private|protected)?\s*trait\s+(\w+)",
            "method": r"(?:@\w+\s*)*\s*(?:public|private|protected|static)?\s*def\s+(\w+)",
            "function": r"(?:@\w+\s*)*\s*(?:public|private|protected|static)?\s*(\w+)\s+(\w+)\s*\(",
            "closure": r"(\w+)\s*=\s*\{",
            "field": r"(?:@\w+\s*)*\s*(?:public|private|protected|static|final)?\s*(?:(\w+)\s+)?(\w+)\s*[=;]",
        }

        return self._find_constructs_with_regex(error_text, patterns, "groovy")

    def _fallback_parse(self, content: str, file_path: str) -> List[Any]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        from .semantic_chunker import SemanticChunk

        # Basic fallback: treat as single chunk
        chunks = []

        if content.strip():
            chunks.append(
                SemanticChunk(
                    text=content,
                    chunk_index=0,
                    total_chunks=1,
                    size=len(content),
                    file_path=file_path,
                    file_extension=Path(file_path).suffix,
                    line_start=1,
                    line_end=len(content.split("\n")),
                    semantic_chunking=False,
                    semantic_type="module",
                    semantic_name=Path(file_path).stem,
                    semantic_path=Path(file_path).stem,
                    semantic_signature=f"module {Path(file_path).stem}",
                    semantic_parent=None,
                    semantic_context={"fallback": True},
                    semantic_scope="global",
                    semantic_language_features=["fallback_parsing"],
                )
            )

        return chunks

    def _find_preceding_annotations(self, node: Any, lines: List[str]) -> List[str]:
        """Find annotations in preceding sibling nodes."""
        annotations: List[str] = []

        if not hasattr(node, "parent") or not node.parent:
            return annotations

        parent = node.parent
        if not hasattr(parent, "children"):
            return annotations

        # Find the current node's position among siblings
        node_index = -1
        for i, sibling in enumerate(parent.children):
            if sibling == node:
                node_index = i
                break

        if node_index <= 0:
            return annotations

        # Look backward through preceding siblings for annotation/decoration nodes
        for i in range(node_index - 1, -1, -1):
            sibling = parent.children[i]

            if not hasattr(sibling, "type"):
                continue

            # Check if this is an annotation/decoration command
            if sibling.type == "command":
                sibling_text = self._get_node_text(sibling, lines).strip()

                # Check if this looks like an annotation
                if sibling_text.startswith("@"):
                    # Extract annotation name(s) from this node
                    node_annotations = re.findall(r"@(\w+)", sibling_text)
                    annotations.extend(node_annotations)
                elif sibling_text == "" or sibling_text.isspace():
                    # Skip whitespace nodes
                    continue
                else:
                    # Stop when we hit a non-annotation, non-whitespace node
                    break
            elif sibling.type in ["", "\n"]:
                # Skip whitespace/newline nodes
                continue
            else:
                # Stop when we hit a non-annotation node
                break

        return annotations
