"""
Pascal/Delphi semantic parser using tree-sitter.

This implementation uses tree-sitter to parse Pascal/Delphi code and extract
semantic information for chunking. Supports:
- Units/Programs
- Classes/Objects/Records
- Procedures/Functions (including nested)
- Properties
- Interfaces
- Constants/Variables/Types
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import tree_sitter_language_pack as tslp

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import BaseSemanticParser, SemanticChunk


class PascalSemanticParser(BaseSemanticParser):
    """Semantic parser for Pascal/Delphi files using tree-sitter."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config)
        self.language = "pascal"

        # Initialize tree-sitter parser
        try:
            self.parser = tslp.get_parser("pascal")
            self.language_obj = tslp.get_language("pascal")
        except Exception as e:
            raise ImportError(f"Failed to initialize Pascal tree-sitter parser: {e}")

        # Cache for parsed tree to avoid re-parsing
        self._parsed_tree: Optional[Any] = None
        self._content_hash: Optional[int] = None

    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse Pascal content and create semantic chunks."""
        try:
            # Parse content with tree-sitter
            tree = self._parse_content(content)
            if not tree or not tree.root_node:
                return []

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
            # Fallback gracefully for malformed code
            return []

    def _parse_content(self, content: str) -> Optional[Any]:
        """Parse content with tree-sitter."""
        try:
            # Convert to bytes as required by tree-sitter
            content_bytes = content.encode("utf-8")

            # Cache parsed tree to avoid re-parsing same content
            content_hash = hash(content)
            if self._content_hash == content_hash and self._parsed_tree:
                return self._parsed_tree

            tree = self.parser.parse(content_bytes)
            self._parsed_tree = tree
            self._content_hash = content_hash

            return tree
        except Exception:
            return None

    def _extract_constructs(
        self, tree: Any, content: str, file_path: str
    ) -> List[Dict[str, Any]]:
        """Extract Pascal constructs from tree-sitter AST."""
        constructs: List[Dict[str, Any]] = []
        lines = content.split("\n")

        # Track scope hierarchy for proper path construction
        scope_stack = []

        # Extract file-level unit/program name
        unit_name = self._extract_unit_name(tree.root_node, lines)
        if unit_name:
            scope_stack.append(unit_name)

        # Traverse the AST to find all constructs
        self._traverse_node(tree.root_node, constructs, lines, scope_stack, content)

        return constructs

    def _extract_unit_name(self, root_node: Any, lines: List[str]) -> Optional[str]:
        """Extract unit or program name from root node."""
        # Look for unit or program declaration
        for child in root_node.children:
            if hasattr(child, "type") and child.type in ["unit", "program"]:
                # Find the moduleName node
                for subchild in child.children:
                    if hasattr(subchild, "type") and subchild.type in [
                        "moduleName",
                        "identifier",
                    ]:
                        return self._get_node_text(subchild, lines)
        return None

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

        # Handle different Pascal construct types based on actual tree-sitter grammar
        if node_type == "unit":
            self._handle_unit_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "program":
            self._handle_program_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declClass":
            self._handle_class_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declRecord":
            self._handle_record_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declInterface":
            self._handle_interface_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declProc":
            self._handle_procedure_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "defProc":
            self._handle_procedure_implementation(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declProp":
            self._handle_property_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declConst":
            self._handle_const_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "declVar":
            self._handle_var_declaration(node, constructs, lines, scope_stack, content)
        elif node_type == "declType":
            self._handle_type_declaration(node, constructs, lines, scope_stack, content)

        # Recursively process children
        # Skip traversing children for nodes that handle their own members
        # But always traverse ERROR nodes to find constructs within them
        # Also skip unit nodes since they have special handling
        if (
            node_type not in ["declClass", "declRecord", "declInterface", "unit"]
            or node_type == "ERROR"
        ):
            for child in node.children:
                self._traverse_node(child, constructs, lines, scope_stack, content)

        # Special handling for ERROR nodes that might contain implementations
        if node_type == "ERROR":
            self._extract_implementations_from_error(
                node, constructs, lines, scope_stack, content
            )

    def _handle_unit_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle unit declaration."""
        unit_name = self._get_identifier_from_node(node, lines)
        if unit_name:
            constructs.append(
                {
                    "type": "unit",
                    "name": unit_name,
                    "path": unit_name,
                    "signature": f"unit {unit_name};",
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "unit"},
                    "features": ["unit_declaration"],
                }
            )

        # Process interface and implementation sections
        for child in node.children:
            if hasattr(child, "type"):
                if child.type in ["interface", "implementation"]:
                    # Traverse all children in these sections
                    for section_child in child.children:
                        self._traverse_node(
                            section_child, constructs, lines, scope_stack, content
                        )

    def _handle_program_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle program declaration."""
        program_name = self._get_identifier_from_node(node, lines)
        if program_name:
            constructs.append(
                {
                    "type": "program",
                    "name": program_name,
                    "path": program_name,
                    "signature": f"program {program_name};",
                    "parent": None,
                    "scope": "global",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "program"},
                    "features": ["program_declaration"],
                }
            )

    def _handle_class_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle class declaration."""
        class_name = self._get_identifier_from_node(node, lines)
        if class_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{class_name}" if parent_path else class_name

            # Extract inheritance info
            inheritance = self._extract_inheritance(node, lines)
            signature = f"class {class_name}"
            if inheritance:
                signature += f"({inheritance})"

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
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "class",
                        "inheritance": inheritance,
                    },
                    "features": ["class_declaration"],
                }
            )

            # Process class members with proper scope
            scope_stack.append(class_name)
            self._process_class_members(node, constructs, lines, scope_stack, content)
            scope_stack.pop()

    def _process_class_members(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Process members of a class/record/interface."""
        # Look for declSection nodes which contain member declarations
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "declSection":
                    # Process all declarations in this section
                    for member in child.children:
                        if hasattr(member, "type"):
                            self._traverse_node(
                                member, constructs, lines, scope_stack, content
                            )
                elif child.type in [
                    "declProc",
                    "declProp",
                    "declVar",
                    "declConst",
                    "declType",
                ]:
                    # Direct member declaration
                    self._traverse_node(child, constructs, lines, scope_stack, content)

    def _handle_record_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle record declaration."""
        record_name = self._get_identifier_from_node(node, lines)
        if record_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{record_name}" if parent_path else record_name

            constructs.append(
                {
                    "type": "record",
                    "name": record_name,
                    "path": full_path,
                    "signature": f"record {record_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "global" if not scope_stack else "type",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "record"},
                    "features": ["record_declaration"],
                }
            )

            # Process record members with proper scope
            scope_stack.append(record_name)
            self._process_class_members(node, constructs, lines, scope_stack, content)
            scope_stack.pop()

    def _handle_interface_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle interface declaration."""
        interface_name = self._get_identifier_from_node(node, lines)
        if interface_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{interface_name}" if parent_path else interface_name
            )

            # Extract GUID if present
            guid = self._extract_interface_guid(node, lines)

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
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "interface", "guid": guid},
                    "features": ["interface_declaration"],
                }
            )

            # Process interface members with proper scope
            scope_stack.append(interface_name)
            self._process_class_members(node, constructs, lines, scope_stack, content)
            scope_stack.pop()

    def _handle_procedure_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle procedure/function declaration."""
        proc_name = self._get_identifier_from_node(node, lines)
        if proc_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{proc_name}" if parent_path else proc_name

            # Determine actual type (procedure, function, constructor, destructor)
            proc_type = self._get_procedure_type(node, lines)

            # Extract parameters and return type
            params = self._extract_parameters(node, lines)
            return_type = self._extract_return_type(node, lines)

            # Check for class/static functions
            is_class = self._is_class_method(node, lines)
            is_static = self._is_static_method(node, lines)

            signature = f"{proc_type} {proc_name}"
            if params:
                signature += f"({params})"
            if return_type:
                signature += f": {return_type}"

            constructs.append(
                {
                    "type": proc_type,
                    "name": proc_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": proc_type,
                        "parameters": params,
                        "return_type": return_type,
                        "is_class": is_class,
                        "is_static": is_static,
                    },
                    "features": [f"{proc_type}_declaration"],
                }
            )

    def _handle_function_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle function declaration."""
        func_name = self._get_identifier_from_node(node, lines)
        if func_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{func_name}" if parent_path else func_name

            # Extract parameters and return type
            params = self._extract_parameters(node, lines)
            return_type = self._extract_return_type(node, lines)

            signature = f"function {func_name}"
            if params:
                signature += f"({params})"
            if return_type:
                signature += f": {return_type}"

            constructs.append(
                {
                    "type": "function",
                    "name": func_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "function",
                        "parameters": params,
                        "return_type": return_type,
                    },
                    "features": ["function_declaration"],
                }
            )

    def _handle_procedure_implementation(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle procedure/function implementation."""
        # defProc contains a declProc child with the signature
        decl_proc = None
        for child in node.children:
            if hasattr(child, "type") and child.type == "declProc":
                decl_proc = child
                break

        if not decl_proc:
            return

        # Extract the name - might be qualified like "TClass.Method"
        method_name = self._extract_qualified_name(decl_proc, lines)
        if not method_name:
            return

        # Split qualified name to get class and method parts
        if "." in method_name:
            parts = method_name.split(".")
            class_name = parts[0]
            simple_name = parts[-1]
            parent_name: Optional[str] = class_name
        else:
            simple_name = method_name
            parent_name = scope_stack[-1] if scope_stack else None

        parent_path = ".".join(scope_stack) if scope_stack else None
        full_path = f"{parent_path}.{method_name}" if parent_path else method_name

        # Determine if it's a constructor, function, or procedure
        proc_type = self._get_procedure_type(decl_proc, lines)

        # Extract parameters and return type
        params = self._extract_parameters(decl_proc, lines)
        return_type = self._extract_return_type(decl_proc, lines)

        signature = f"{proc_type} {simple_name}"
        if params:
            signature += f"({params})"
        if return_type:
            signature += f": {return_type}"

        constructs.append(
            {
                "type": proc_type,
                "name": simple_name,
                "path": full_path,
                "signature": signature,
                "parent": parent_name,
                "scope": "function",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": proc_type,
                    "parameters": params,
                    "return_type": return_type,
                    "qualified_name": method_name,
                },
                "features": [f"{proc_type}_implementation"],
            }
        )

        # Add function to scope stack and process nested functions
        scope_stack.append(simple_name)
        try:
            # Look for nested procedures/functions in the implementation
            for child in node.children:
                if hasattr(child, "type") and child.type == "defProc":
                    # This is a nested procedure/function
                    self._handle_procedure_implementation(
                        child, constructs, lines, scope_stack, content
                    )
                elif hasattr(child, "type") and child.type == "declProc":
                    # This is a nested procedure/function declaration
                    self._handle_procedure_declaration(
                        child, constructs, lines, scope_stack, content
                    )
        finally:
            scope_stack.pop()

    def _handle_constructor_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle constructor declaration."""
        constructor_name = self._get_identifier_from_node(node, lines)
        if constructor_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{constructor_name}" if parent_path else constructor_name
            )

            params = self._extract_parameters(node, lines)
            signature = f"constructor {constructor_name}"
            if params:
                signature += f"({params})"

            constructs.append(
                {
                    "type": "constructor",
                    "name": constructor_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "constructor",
                        "parameters": params,
                    },
                    "features": ["constructor_declaration"],
                }
            )

    def _handle_destructor_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle destructor declaration."""
        destructor_name = self._get_identifier_from_node(node, lines)
        if destructor_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{destructor_name}" if parent_path else destructor_name
            )

            constructs.append(
                {
                    "type": "destructor",
                    "name": destructor_name,
                    "path": full_path,
                    "signature": f"destructor {destructor_name}",
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "function",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "destructor"},
                    "features": ["destructor_declaration"],
                }
            )

    def _handle_property_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle property declaration."""
        property_name = self._get_identifier_from_node(node, lines)
        if property_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = (
                f"{parent_path}.{property_name}" if parent_path else property_name
            )

            # Extract property details
            property_type = self._extract_property_type(node, lines)
            property_params = self._extract_property_parameters(node, lines)
            read_spec = self._extract_property_read(node, lines)
            write_spec = self._extract_property_write(node, lines)
            is_default = self._is_default_property(node, lines)

            signature = f"property {property_name}"
            if property_params:
                signature += f"[{property_params}]"
            if property_type:
                signature += f": {property_type}"
            if read_spec:
                signature += f" read {read_spec}"
            if write_spec:
                signature += f" write {write_spec}"
            if is_default:
                signature += " default"

            constructs.append(
                {
                    "type": "property",
                    "name": property_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "property",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "property",
                        "property_type": property_type,
                        "read_spec": read_spec,
                        "write_spec": write_spec,
                        "is_default": is_default,
                    },
                    "features": ["property_declaration"],
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
        """Handle constant declaration."""
        const_name = self._get_identifier_from_node(node, lines)
        if const_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{const_name}" if parent_path else const_name

            # Extract constant value
            const_value = self._extract_const_value(node, lines)
            signature = f"const {const_name}"
            if const_value:
                signature += f" = {const_value}"

            constructs.append(
                {
                    "type": "constant",
                    "name": const_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "global" if not scope_stack else "local",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "constant", "value": const_value},
                    "features": ["const_declaration"],
                }
            )

    def _handle_var_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle variable declaration."""
        var_name = self._get_identifier_from_node(node, lines)
        if var_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{var_name}" if parent_path else var_name

            # Extract variable type
            var_type = self._extract_var_type(node, lines)
            signature = f"var {var_name}"
            if var_type:
                signature += f": {var_type}"

            constructs.append(
                {
                    "type": "variable",
                    "name": var_name,
                    "path": full_path,
                    "signature": signature,
                    "parent": scope_stack[-1] if scope_stack else None,
                    "scope": "global" if not scope_stack else "local",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {"declaration_type": "variable", "var_type": var_type},
                    "features": ["var_declaration"],
                }
            )

    def _handle_type_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle type declaration."""
        type_name = self._get_identifier_from_node(node, lines)
        if type_name:
            parent_path = ".".join(scope_stack) if scope_stack else None
            full_path = f"{parent_path}.{type_name}" if parent_path else type_name

            # Check if this is a class or interface declaration within the type
            decl_class = None
            decl_intf = None
            for child in node.children:
                if hasattr(child, "type"):
                    if child.type == "declClass":
                        decl_class = child
                        break
                    elif child.type == "declIntf":
                        decl_intf = child
                        break

            if decl_class:
                # Check if this is a record or a class
                is_record = self._is_record_type(decl_class)

                if is_record:
                    # This is a record declaration
                    constructs.append(
                        {
                            "type": "record",
                            "name": type_name,
                            "path": full_path,
                            "signature": f"record {type_name}",
                            "parent": scope_stack[-1] if scope_stack else None,
                            "scope": "global" if not scope_stack else "type",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "text": self._get_node_text(node, lines),
                            "context": {"declaration_type": "record"},
                            "features": ["record_declaration"],
                        }
                    )
                else:
                    # This is a class declaration
                    # Extract inheritance info
                    inheritance = self._extract_inheritance(decl_class, lines)
                    signature = f"class {type_name}"
                    if inheritance:
                        signature += f"({inheritance})"

                    constructs.append(
                        {
                            "type": "class",
                            "name": type_name,
                            "path": full_path,
                            "signature": signature,
                            "parent": scope_stack[-1] if scope_stack else None,
                            "scope": "global" if not scope_stack else "class",
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "text": self._get_node_text(node, lines),
                            "context": {
                                "declaration_type": "class",
                                "inheritance": inheritance,
                            },
                            "features": ["class_declaration"],
                        }
                    )

                # Add class to scope stack and process its members
                scope_stack.append(type_name)
                try:
                    for child in decl_class.children:
                        self._traverse_node(
                            child, constructs, lines, scope_stack, content
                        )
                finally:
                    scope_stack.pop()
            elif decl_intf:
                # This is an interface declaration
                # Extract GUID if present
                guid = self._extract_interface_guid(decl_intf, lines)

                constructs.append(
                    {
                        "type": "interface",
                        "name": type_name,
                        "path": full_path,
                        "signature": f"interface {type_name}",
                        "parent": scope_stack[-1] if scope_stack else None,
                        "scope": "global" if not scope_stack else "interface",
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": self._get_node_text(node, lines),
                        "context": {"declaration_type": "interface", "guid": guid},
                        "features": ["interface_declaration"],
                    }
                )

                # Add interface to scope stack and process its members
                scope_stack.append(type_name)
                try:
                    for child in decl_intf.children:
                        self._traverse_node(
                            child, constructs, lines, scope_stack, content
                        )
                finally:
                    scope_stack.pop()
            else:
                # Regular type declaration
                type_def = self._extract_type_definition(node, lines)
                signature = f"type {type_name}"
                if type_def:
                    signature += f" = {type_def}"

                constructs.append(
                    {
                        "type": "type",
                        "name": type_name,
                        "path": full_path,
                        "signature": signature,
                        "parent": scope_stack[-1] if scope_stack else None,
                        "scope": "global" if not scope_stack else "local",
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "text": self._get_node_text(node, lines),
                        "context": {
                            "declaration_type": "type",
                            "type_definition": type_def,
                        },
                        "features": ["type_declaration"],
                    }
                )

    # Helper methods for extracting specific information from nodes

    def _get_node_text(self, node: Any, lines: List[str]) -> str:
        """Get text content of a node."""
        try:
            start_line = node.start_point[0]
            end_line = node.end_point[0]
            start_col = node.start_point[1]
            end_col = node.end_point[1]

            if start_line == end_line:
                return str(lines[start_line][start_col:end_col])
            else:
                result = lines[start_line][start_col:]
                for line_idx in range(start_line + 1, end_line):
                    result += "\n" + lines[line_idx]
                result += "\n" + lines[end_line][:end_col]
                return str(result)
        except (IndexError, AttributeError):
            return ""

    def _get_identifier_from_node(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract identifier name from a node."""
        for child in node.children:
            if hasattr(child, "type") and child.type in ["identifier", "moduleName"]:
                return self._get_node_text(child, lines)
        return None

    def _extract_inheritance(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract inheritance information from class node."""
        # Look for typeref nodes between parentheses
        inheritance_parts = []
        in_parentheses = False

        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "(":
                    in_parentheses = True
                elif child.type == ")":
                    in_parentheses = False
                elif in_parentheses and child.type == "typeref":
                    inheritance_parts.append(self._get_node_text(child, lines))

        return ", ".join(inheritance_parts) if inheritance_parts else None

    def _extract_interface_guid(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract GUID from interface declaration."""
        # Look for GUID string in interface
        for child in node.children:
            if hasattr(child, "type") and "string" in child.type.lower():
                text = self._get_node_text(child, lines)
                if "{" in text and "}" in text:
                    return text
        return None

    def _extract_parameters(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract parameter list from function/procedure node."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "declArgs":
                # Get the text but remove the outer parentheses
                params_text = self._get_node_text(child, lines)
                if params_text.startswith("(") and params_text.endswith(")"):
                    return params_text[1:-1]  # Remove ( and )
                return params_text
        return None

    def _extract_return_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract return type from function node."""
        # Look for typeref after the colon
        found_colon = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == ":":
                    found_colon = True
                elif found_colon and child.type == "typeref":
                    return self._get_node_text(child, lines)
        return None

    def _extract_property_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract property type."""
        # Look for type node after the colon
        found_colon = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == ":":
                    found_colon = True
                elif found_colon and "type" in child.type.lower():
                    return self._get_node_text(child, lines)
        return None

    def _extract_property_parameters(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract property parameters from indexed properties."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "declPropArgs":
                # Get the text but remove the outer brackets
                params_text = self._get_node_text(child, lines)
                if params_text.startswith("[") and params_text.endswith("]"):
                    return params_text[1:-1]  # Remove [ and ]
                return params_text
        return None

    def _extract_property_read(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract property read specifier."""
        found_read = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "kRead":
                    found_read = True
                elif found_read and child.type == "identifier":
                    return self._get_node_text(child, lines)
        return None

    def _extract_property_write(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract property write specifier."""
        found_write = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "kWrite":
                    found_write = True
                elif found_write and child.type == "identifier":
                    return self._get_node_text(child, lines)
        return None

    def _is_default_property(self, node: Any, lines: List[str]) -> bool:
        """Check if property is marked as default."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "kDefault":
                return True
        # Also check in the node text as fallback
        node_text = self._get_node_text(node, lines).lower()
        return "default" in node_text

    def _extract_const_value(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract constant value."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "defaultValue":
                # Look for the value after the '=' sign
                found_eq = False
                for subchild in child.children:
                    if hasattr(subchild, "type"):
                        if subchild.type == "kEq":
                            found_eq = True
                        elif found_eq and (
                            "literal" in subchild.type.lower()
                            or subchild.type in ["literalNumber", "literalString"]
                        ):
                            return self._get_node_text(subchild, lines)
        return None

    def _extract_var_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract variable type."""
        for child in node.children:
            if hasattr(child, "type") and "type" in child.type.lower():
                return self._get_node_text(child, lines)
        return None

    def _extract_type_definition(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract type definition."""
        # Look for the type definition after the '=' sign
        found_eq = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "kEq":
                    found_eq = True
                elif found_eq and child.type == "type":
                    # Get the full type definition
                    return self._get_node_text(child, lines)
        return None

    def _extract_qualified_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract qualified name (e.g., TClass.Method) from procedure declaration."""
        # Look for genericDot node which contains qualified names
        for child in node.children:
            if hasattr(child, "type") and child.type == "genericDot":
                return self._get_node_text(child, lines)

        # Fall back to simple identifier
        return self._get_identifier_from_node(node, lines)

    def _get_procedure_type(self, node: Any, lines: List[str]) -> str:
        """Determine if procedure is constructor, function, or procedure."""
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "kConstructor":
                    return "constructor"
                elif child.type == "kFunction":
                    return "function"
                elif child.type == "kProcedure":
                    return "procedure"
                elif child.type == "kDestructor":
                    return "destructor"
        return "procedure"  # default

    def _is_record_type(self, decl_class_node: Any) -> bool:
        """Check if a declClass node represents a record type."""
        for child in decl_class_node.children:
            if hasattr(child, "type") and child.type == "kRecord":
                return True
        return False

    def _is_class_method(self, node: Any, lines: List[str]) -> bool:
        """Check if a procedure/function is declared as a class method."""
        for child in node.children:
            if hasattr(child, "type") and child.type == "kClass":
                return True
        return False

    def _is_static_method(self, node: Any, lines: List[str]) -> bool:
        """Check if a procedure/function is declared as static."""
        # Look for "static" keyword in the full text of the node
        node_text = self._get_node_text(node, lines).lower()
        return "static" in node_text

    def _extract_implementations_from_error(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Extract procedure/function implementations from ERROR nodes using regex fallback."""
        import re

        # Get the text of the ERROR node
        start_line = node.start_point[0]
        end_line = node.end_point[0]

        # Look for procedure/function implementations in the error text
        for line_idx in range(start_line, end_line + 1):
            if line_idx >= len(lines):
                break

            line = lines[line_idx]

            # Check if this line starts a procedure/function implementation
            match = re.match(
                r"^(procedure|function|constructor|destructor)\s+(\w+\.)?(\w+)", line
            )
            if match:
                proc_type = match.group(1)
                class_prefix = match.group(2)
                method_name = match.group(3)

                # Skip if it's not a method implementation (no class prefix)
                if not class_prefix:
                    continue

                # Extract the class name
                class_name = class_prefix.rstrip(".")

                # Find the end of the implementation
                impl_start = line_idx
                impl_end = impl_start

                # Collect the full signature (might span multiple lines)
                signature_lines = [line]
                current_line = line_idx

                # Check if signature continues on next lines
                while current_line < len(lines) - 1 and not lines[
                    current_line
                ].rstrip().endswith(";"):
                    current_line += 1
                    if current_line < len(lines):
                        signature_lines.append(lines[current_line])

                full_signature = " ".join(line.strip() for line in signature_lines)

                # Extract parameters from signature
                params_match = re.search(r"\((.*?)\)", full_signature)
                params = params_match.group(1) if params_match else None

                # Extract return type for functions
                return_type = None
                if proc_type == "function":
                    return_match = re.search(r"\)\s*:\s*([^;]+)", full_signature)
                    if return_match:
                        return_type = return_match.group(1).strip()

                # Find the implementation body (from var/begin to end)
                # Look for the corresponding 'end' by counting begin/end pairs
                begin_count = 0
                found_first_begin = False

                for search_idx in range(
                    current_line + 1, min(current_line + 500, len(lines))
                ):
                    search_line = lines[search_idx].strip().lower()

                    if search_line.startswith("begin"):
                        begin_count += 1
                        found_first_begin = True
                    elif search_line.startswith("end"):
                        if found_first_begin:
                            begin_count -= 1
                            if begin_count == 0:
                                impl_end = search_idx
                                break
                    elif (
                        found_first_begin
                        and begin_count == 0
                        and search_line
                        and not search_line.startswith("{")
                    ):
                        # We've gone past the implementation
                        break

                    # Also check for next procedure/function
                    if re.match(
                        r"^(procedure|function|constructor|destructor)\s+",
                        lines[search_idx],
                    ):
                        impl_end = search_idx - 1
                        break

                # If we didn't find an end, use a reasonable default
                if impl_end <= impl_start:
                    impl_end = min(impl_start + 50, len(lines) - 1)

                # Build the implementation text
                impl_lines = lines[impl_start : impl_end + 1]
                impl_text = "\n".join(impl_lines)

                # Create the semantic signature
                semantic_sig = f"{proc_type} {method_name}"
                if params:
                    semantic_sig += f"({params})"
                if return_type:
                    semantic_sig += f": {return_type}"

                # Check if we already have this implementation
                # to avoid duplicates from ERROR node extraction
                duplicate_found = False
                for existing in constructs:
                    if (
                        existing.get("name") == method_name
                        and existing.get("parent") == class_name
                        and existing.get("line_start") == impl_start + 1
                        and f"{proc_type}_implementation"
                        in existing.get("features", [])
                    ):
                        duplicate_found = True
                        break

                if not duplicate_found:
                    # Add the construct
                    constructs.append(
                        {
                            "type": proc_type,
                            "name": method_name,
                            "path": f"{class_name}.{method_name}",
                            "signature": semantic_sig,
                            "parent": class_name,
                            "scope": "function",
                            "line_start": impl_start + 1,
                            "line_end": impl_end + 1,
                            "text": impl_text,
                            "context": {
                                "declaration_type": proc_type,
                                "parameters": params,
                                "return_type": return_type,
                                "qualified_name": f"{class_name}.{method_name}",
                                "extracted_from_error": True,
                            },
                            "features": [f"{proc_type}_implementation"],
                        }
                    )
