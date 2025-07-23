"""
SQL semantic parser using tree-sitter with comprehensive regex fallback.

This implementation uses tree-sitter as the primary parsing method,
with comprehensive regex fallback for ERROR nodes to ensure no content is lost.
Supports multiple SQL dialects including MySQL, PostgreSQL, SQLite, and SQL Server.

Handles:
- Table definitions (CREATE TABLE, ALTER TABLE)
- Views, indexes, sequences
- Stored procedures and functions
- Triggers
- SELECT, INSERT, UPDATE, DELETE statements
- CTEs (Common Table Expressions)
- Window functions
- Variable declarations
- Cursors
- User-defined types
- ERROR nodes with comprehensive regex fallback
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class SQLSemanticParser(BaseTreeSitterParser):
    """Semantic parser for SQL files using tree-sitter with regex fallback."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "sql")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (schema definitions, use statements)."""
        # Look for schema/database declarations
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "create_schema_statement":
                    schema_name = self._extract_schema_name(child, lines)
                    if schema_name:
                        scope_stack.append(schema_name)
                        constructs.append(
                            {
                                "type": "schema",
                                "name": schema_name,
                                "path": schema_name,
                                "signature": f"CREATE SCHEMA {schema_name}",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "schema"},
                                "features": ["schema_declaration"],
                            }
                        )
                elif child.type == "use_statement":
                    database_name = self._extract_database_name(child, lines)
                    if database_name:
                        constructs.append(
                            {
                                "type": "use",
                                "name": database_name,
                                "path": database_name,
                                "signature": f"USE {database_name}",
                                "parent": None,
                                "scope": "global",
                                "line_start": child.start_point[0] + 1,
                                "line_end": child.end_point[0] + 1,
                                "text": self._get_node_text(child, lines),
                                "context": {"declaration_type": "use"},
                                "features": ["use_statement"],
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
        """Handle SQL-specific AST node types."""
        # Handle actual tree-sitter node types for SQL
        if node_type == "create_table":
            self._handle_create_table(node, constructs, lines, scope_stack, content)
        elif node_type == "create_view":
            self._handle_create_view(node, constructs, lines, scope_stack, content)
        elif node_type == "create_index":
            self._handle_create_index(node, constructs, lines, scope_stack, content)
        elif node_type == "create_procedure":
            self._handle_create_procedure(node, constructs, lines, scope_stack, content)
        elif node_type == "create_function":
            self._handle_create_function(node, constructs, lines, scope_stack, content)
        elif node_type == "create_trigger":
            self._handle_create_trigger(node, constructs, lines, scope_stack, content)
        elif node_type == "select" or node_type == "create_query":
            self._handle_select_statement(node, constructs, lines, scope_stack, content)
        elif node_type == "statement":
            self._handle_statement_node(node, constructs, lines, scope_stack, content)
        elif node_type == "insert":
            self._handle_insert_statement(node, constructs, lines, scope_stack, content)
        elif node_type == "update":
            self._handle_update_statement(node, constructs, lines, scope_stack, content)
        elif node_type == "delete":
            self._handle_delete_statement(node, constructs, lines, scope_stack, content)
        elif node_type == "with_clause" or node_type == "cte":
            self._handle_cte(node, constructs, lines, scope_stack, content)
        elif node_type == "alter_table":
            self._handle_alter_table(node, constructs, lines, scope_stack, content)
        elif node_type == "declare" or node_type == "declare_statement":
            self._handle_declare_statement(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "cursor_declaration":
            self._handle_cursor_declaration(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "use":
            self._handle_use_statement(node, constructs, lines, scope_stack, content)

    def _handle_statement_node(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle statement nodes by examining their children."""
        for child in node.children:
            if hasattr(child, "type"):
                child_type = child.type
                if child_type == "create_table":
                    self._handle_create_table(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "create_view":
                    self._handle_create_view(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "create_index":
                    self._handle_create_index(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "create_procedure":
                    self._handle_create_procedure(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "create_function":
                    self._handle_create_function(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "create_trigger":
                    self._handle_create_trigger(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "create_schema":
                    self._handle_create_schema(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "create_database":
                    self._handle_create_database(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "select":
                    # For SELECT statements, pass the parent statement node to get full context
                    self._handle_select_statement(
                        node, constructs, lines, scope_stack, content
                    )
                elif child_type == "insert":
                    self._handle_insert_statement(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "update":
                    self._handle_update_statement(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "delete":
                    # For DELETE statements, pass the parent statement node to get full context
                    self._handle_delete_statement(
                        node, constructs, lines, scope_stack, content
                    )
                elif child_type == "alter_table":
                    self._handle_alter_table(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "with_clause" or child_type == "cte":
                    self._handle_cte(child, constructs, lines, scope_stack, content)
                elif child_type == "declare" or child_type == "declare_statement":
                    self._handle_declare_statement(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "cursor_declaration":
                    self._handle_cursor_declaration(
                        child, constructs, lines, scope_stack, content
                    )
                elif child_type == "use":
                    self._handle_use_statement(
                        child, constructs, lines, scope_stack, content
                    )

    def _handle_create_schema(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE SCHEMA statement."""
        schema_name = self._extract_schema_name(node, lines)
        if not schema_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{schema_name}" if current_scope else schema_name

        constructs.append(
            {
                "type": "schema",
                "name": schema_name,
                "path": full_path,
                "signature": f"CREATE SCHEMA {schema_name}",
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "schema"},
                "features": ["schema_declaration"],
            }
        )

    def _handle_create_database(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE DATABASE statement."""
        database_name = self._extract_database_name_from_create(node, lines)
        if not database_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{database_name}" if current_scope else database_name
        )

        constructs.append(
            {
                "type": "database",
                "name": database_name,
                "path": full_path,
                "signature": f"CREATE DATABASE {database_name}",
                "parent": current_scope if current_scope else None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "database"},
                "features": ["database_declaration"],
            }
        )

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        # Skip children for constructs that handle their own internal structure
        return node_type in [
            "create_table",
            "create_view",
            "create_procedure",
            "create_function",
            "create_trigger",
            "create_index",
            "create_schema",
            "create_database",
            "select",
            "insert",
            "update",
            "delete",
            "alter_table",
            "use",
            "statement",
        ]

    def _handle_create_table(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE TABLE statement."""
        table_name = self._extract_table_name(node, lines)
        if not table_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{table_name}" if current_scope else table_name

        # Extract columns and constraints
        columns = self._extract_table_columns(node, lines)
        constraints = self._extract_table_constraints(node, lines)

        signature = f"CREATE TABLE {table_name}"
        if columns:
            signature += f" ({len(columns)} columns)"

        constructs.append(
            {
                "type": "table",
                "name": table_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "schema" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "table",
                    "columns": columns,
                    "constraints": constraints,
                },
                "features": ["table_declaration"],
            }
        )

    def _handle_create_view(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE VIEW statement."""
        view_name = self._extract_view_name(node, lines)
        if not view_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{view_name}" if current_scope else view_name

        signature = f"CREATE VIEW {view_name}"

        constructs.append(
            {
                "type": "view",
                "name": view_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "schema" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "view"},
                "features": ["view_declaration"],
            }
        )

    def _handle_create_index(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE INDEX statement."""
        index_name = self._extract_index_name(node, lines)
        table_name = self._extract_index_table_name(node, lines)

        if not index_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{index_name}" if current_scope else index_name

        signature = f"CREATE INDEX {index_name}"
        if table_name:
            signature += f" ON {table_name}"

        constructs.append(
            {
                "type": "index",
                "name": index_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "schema" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "index",
                    "table_name": table_name,
                },
                "features": ["index_declaration"],
            }
        )

    def _handle_create_procedure(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE PROCEDURE statement."""
        procedure_name = self._extract_procedure_name(node, lines)
        if not procedure_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{procedure_name}" if current_scope else procedure_name
        )

        parameters = self._extract_procedure_parameters(node, lines)
        signature = f"CREATE PROCEDURE {procedure_name}"
        if parameters:
            signature += f"({parameters})"

        constructs.append(
            {
                "type": "procedure",
                "name": procedure_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "schema" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "procedure",
                    "parameters": parameters,
                },
                "features": ["procedure_declaration"],
            }
        )

    def _handle_create_function(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE FUNCTION statement."""
        function_name = self._extract_function_name(node, lines)
        if not function_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{function_name}" if current_scope else function_name
        )

        parameters = self._extract_function_parameters(node, lines)
        return_type = self._extract_function_return_type(node, lines)

        signature = f"CREATE FUNCTION {function_name}"
        if parameters:
            signature += f"({parameters})"
        if return_type:
            signature += f" RETURNS {return_type}"

        constructs.append(
            {
                "type": "function",
                "name": function_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "schema" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "function",
                    "parameters": parameters,
                    "return_type": return_type,
                },
                "features": ["function_declaration"],
            }
        )

    def _handle_create_trigger(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE TRIGGER statement."""
        trigger_name = self._extract_trigger_name(node, lines)
        table_name = self._extract_trigger_table_name(node, lines)

        if not trigger_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{trigger_name}" if current_scope else trigger_name

        timing = self._extract_trigger_timing(node, lines)
        events = self._extract_trigger_events(node, lines)

        signature = f"CREATE TRIGGER {trigger_name}"
        if timing:
            signature += f" {timing}"
        if events:
            signature += f" {' OR '.join(events)}"
        if table_name:
            signature += f" ON {table_name}"

        constructs.append(
            {
                "type": "trigger",
                "name": trigger_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "schema" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "trigger",
                    "table_name": table_name,
                    "timing": timing,
                    "events": events,
                },
                "features": ["trigger_declaration"],
            }
        )

    def _handle_select_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle SELECT statement."""
        # Only extract significant SELECT statements (not sub-queries)
        if self._is_significant_select(node, lines):
            statement_id = f"select_{node.start_point[0] + 1}"
            tables = self._extract_select_tables(node, lines)

            current_scope = ".".join(scope_stack)
            full_path = (
                f"{current_scope}.{statement_id}" if current_scope else statement_id
            )

            signature = "SELECT"
            if tables:
                signature += f" FROM {', '.join(tables[:3])}"
                if len(tables) > 3:
                    signature += "..."

            constructs.append(
                {
                    "type": "select",
                    "name": statement_id,
                    "path": full_path,
                    "signature": signature,
                    "parent": current_scope if current_scope else None,
                    "scope": "query",
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "text": self._get_node_text(node, lines),
                    "context": {
                        "declaration_type": "select",
                        "tables": tables,
                    },
                    "features": ["select_statement"],
                }
            )

    def _handle_insert_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle INSERT statement."""
        table_name = self._extract_insert_table_name(node, lines)
        if not table_name:
            return

        statement_id = f"insert_{table_name}_{node.start_point[0] + 1}"
        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{statement_id}" if current_scope else statement_id

        signature = f"INSERT INTO {table_name}"

        constructs.append(
            {
                "type": "insert",
                "name": statement_id,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "query",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "insert",
                    "table_name": table_name,
                },
                "features": ["insert_statement"],
            }
        )

    def _handle_update_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle UPDATE statement."""
        table_name = self._extract_update_table_name(node, lines)
        if not table_name:
            return

        statement_id = f"update_{table_name}_{node.start_point[0] + 1}"
        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{statement_id}" if current_scope else statement_id

        signature = f"UPDATE {table_name}"

        constructs.append(
            {
                "type": "update",
                "name": statement_id,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "query",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "update",
                    "table_name": table_name,
                },
                "features": ["update_statement"],
            }
        )

    def _handle_delete_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle DELETE statement."""
        table_name = self._extract_delete_table_name(node, lines)
        if not table_name:
            return

        statement_id = f"delete_{table_name}_{node.start_point[0] + 1}"
        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{statement_id}" if current_scope else statement_id

        signature = f"DELETE FROM {table_name}"

        constructs.append(
            {
                "type": "delete",
                "name": statement_id,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "query",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "delete",
                    "table_name": table_name,
                },
                "features": ["delete_statement"],
            }
        )

    def _handle_cte(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Common Table Expression (CTE)."""
        cte_name = self._extract_cte_name(node, lines)
        if not cte_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{cte_name}" if current_scope else cte_name

        signature = f"WITH {cte_name}"

        constructs.append(
            {
                "type": "cte",
                "name": cte_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "query",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "cte"},
                "features": ["cte_declaration"],
            }
        )

    def _handle_alter_table(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle ALTER TABLE statement."""
        table_name = self._extract_alter_table_name(node, lines)
        if not table_name:
            return

        operation = self._extract_alter_operation(node, lines)
        statement_id = f"alter_{table_name}_{node.start_point[0] + 1}"

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{statement_id}" if current_scope else statement_id

        signature = f"ALTER TABLE {table_name}"
        if operation:
            signature += f" {operation}"

        constructs.append(
            {
                "type": "alter_table",
                "name": statement_id,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "schema" if scope_stack else "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "alter_table",
                    "table_name": table_name,
                    "operation": operation,
                },
                "features": ["alter_table_statement"],
            }
        )

    def _handle_declare_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle DECLARE statement (variables, cursors)."""
        variable_name = self._extract_variable_name(node, lines)
        if not variable_name:
            return

        variable_type = self._extract_variable_type(node, lines)
        current_scope = ".".join(scope_stack)
        full_path = (
            f"{current_scope}.{variable_name}" if current_scope else variable_name
        )

        signature = f"DECLARE {variable_name}"
        if variable_type:
            signature += f" {variable_type}"

        constructs.append(
            {
                "type": "variable",
                "name": variable_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "local",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {
                    "declaration_type": "variable",
                    "variable_type": variable_type,
                },
                "features": ["variable_declaration"],
            }
        )

    def _handle_cursor_declaration(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle cursor declaration."""
        cursor_name = self._extract_cursor_name(node, lines)
        if not cursor_name:
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{cursor_name}" if current_scope else cursor_name

        signature = f"DECLARE {cursor_name} CURSOR"

        constructs.append(
            {
                "type": "cursor",
                "name": cursor_name,
                "path": full_path,
                "signature": signature,
                "parent": current_scope if current_scope else None,
                "scope": "local",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "cursor"},
                "features": ["cursor_declaration"],
            }
        )

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract SQL constructs from ERROR node text using regex fallback."""
        constructs = []
        lines = error_text.split("\n")
        current_parent = ".".join(scope_stack) if scope_stack else None

        # SQL construct patterns (case-insensitive)
        patterns = [
            # Table creation
            (
                r"(?i)^\s*CREATE\s+(TEMPORARY\s+|TEMP\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_$.]*)",
                "table",
            ),
            # View creation
            (
                r"(?i)^\s*CREATE\s+(OR\s+REPLACE\s+)?VIEW\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "view",
            ),
            # Index creation
            (
                r"(?i)^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "index",
            ),
            # Procedure creation
            (
                r"(?i)^\s*CREATE\s+(OR\s+REPLACE\s+)?PROCEDURE\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "procedure",
            ),
            # Function creation
            (
                r"(?i)^\s*CREATE\s+(OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "function",
            ),
            # Trigger creation
            (
                r"(?i)^\s*CREATE\s+TRIGGER\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "trigger",
            ),
            # Sequence creation
            (
                r"(?i)^\s*CREATE\s+SEQUENCE\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "sequence",
            ),
            # Type creation
            (
                r"(?i)^\s*CREATE\s+TYPE\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "type",
            ),
            # Schema creation
            (
                r"(?i)^\s*CREATE\s+SCHEMA\s+(?:AUTHORIZATION\s+)?([A-Za-z_][A-Za-z0-9_$.]*)",
                "schema",
            ),
            # Database creation
            (
                r"(?i)^\s*CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_$.]*)",
                "database",
            ),
            # USE statements
            (
                r"(?i)^\s*USE\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "use",
            ),
            # CTE (WITH clause)
            (r"(?i)^\s*WITH\s+([A-Za-z_][A-Za-z0-9_$.]*)\s+AS", "cte"),
            # Cursor declaration (more specific, must come before variable declaration)
            (
                r"(?i)^\s*DECLARE\s+([A-Za-z_][A-Za-z0-9_$.]*)\s+CURSOR",
                "cursor",
            ),
            # Variable declaration
            (
                r"(?i)^\s*DECLARE\s+([A-Za-z_@][A-Za-z0-9_$]*)\s+",
                "variable",
            ),
            # Significant SELECT statements
            (r"(?i)^\s*SELECT\s+.*FROM\s+([A-Za-z_][A-Za-z0-9_$.,\s]*)", "select"),
            # INSERT statements
            (r"(?i)^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_$.]*)", "insert"),
            # UPDATE statements
            (r"(?i)^\s*UPDATE\s+([A-Za-z_][A-Za-z0-9_$.]*)", "update"),
            # DELETE statements (including MySQL-style with aliases)
            (
                r"(?i)^\s*DELETE\s+(?:[A-Za-z_][A-Za-z0-9_$]*\s+)?FROM\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "delete",
            ),
            # ALTER TABLE statements
            (r"(?i)^\s*ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_$.]*)", "alter_table"),
        ]

        for i, line in enumerate(lines):
            line_num = start_line + i
            for pattern, construct_type in patterns:
                match = re.search(pattern, line)
                if match:
                    # Extract the name from the last non-empty group (handles optional groups)
                    name = None
                    for i in range(len(match.groups()), 0, -1):
                        if match.group(i) and match.group(i).strip():
                            name = match.group(i)
                            break
                    if name:
                        name = name.strip().split()[
                            0
                        ]  # Take first word for multi-word matches
                        full_path = (
                            f"{current_parent}.{name}" if current_parent else name
                        )

                        constructs.append(
                            {
                                "type": construct_type,
                                "name": name,
                                "path": full_path,
                                "signature": line.strip(),
                                "parent": current_parent,
                                "scope": "schema" if current_parent else "global",
                                "line_start": line_num,
                                "line_end": line_num,
                                "text": line,
                                "context": {"regex_fallback": True},
                                "features": [f"{construct_type}_declaration"],
                            }
                        )
                        break

        return constructs

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

    # Helper methods for extracting specific information from nodes

    def _extract_schema_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract schema name from CREATE SCHEMA statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)CREATE\s+SCHEMA\s+(?:AUTHORIZATION\s+)?([A-Za-z_][A-Za-z0-9_$.]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_database_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract database name from USE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)USE\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        return match.group(1) if match else None

    def _extract_database_name_from_create(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract database name from CREATE DATABASE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_$.]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_table_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract table name from CREATE TABLE statement."""
        # Try to find table name in child nodes first (tree-sitter structure)
        for child in node.children:
            if hasattr(child, "type") and child.type == "object_reference":
                # Look for identifier within object_reference
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "identifier":
                        return self._get_node_text(grandchild, lines).strip()
            elif hasattr(child, "type") and child.type == "identifier":
                return self._get_node_text(child, lines).strip()

        # Fallback to regex
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)CREATE\s+(?:TEMPORARY\s+|TEMP\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_$.]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_view_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract view name from CREATE VIEW statement."""
        # Try to find view name in child nodes first (tree-sitter structure)
        for child in node.children:
            if hasattr(child, "type") and child.type == "object_reference":
                # Look for identifier within object_reference
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "identifier":
                        return self._get_node_text(grandchild, lines).strip()
            elif hasattr(child, "type") and child.type == "identifier":
                return self._get_node_text(child, lines).strip()

        # Fallback to regex
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([A-Za-z_][A-Za-z0-9_$.]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_index_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract index name from CREATE INDEX statement."""
        # Try to find index name in child nodes first (tree-sitter structure)
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                # Skip keywords like CREATE, INDEX, etc.
                text = self._get_node_text(child, lines).strip().upper()
                if text not in ["CREATE", "INDEX", "UNIQUE", "ON"]:
                    return self._get_node_text(child, lines).strip()

        # Fallback to regex
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)CREATE\s+(?:UNIQUE\s+)?INDEX\s+([A-Za-z_][A-Za-z0-9_$.]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_index_table_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract table name from CREATE INDEX statement."""
        # Try to find table name in child nodes first (tree-sitter structure)
        for child in node.children:
            if hasattr(child, "type") and child.type == "object_reference":
                # Look for identifier within object_reference
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "identifier":
                        return self._get_node_text(grandchild, lines).strip()

        # Fallback to regex
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)ON\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        return match.group(1) if match else None

    def _extract_procedure_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract procedure name from CREATE PROCEDURE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+([A-Za-z_][A-Za-z0-9_$.]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_function_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract function name from CREATE FUNCTION statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z_][A-Za-z0-9_$.]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_trigger_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract trigger name from CREATE TRIGGER statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)CREATE\s+TRIGGER\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text
        )
        return match.group(1) if match else None

    def _extract_trigger_table_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract table name from CREATE TRIGGER statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)ON\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        return match.group(1) if match else None

    def _extract_trigger_timing(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract trigger timing (BEFORE/AFTER/INSTEAD OF)."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)(BEFORE|AFTER|INSTEAD\s+OF)", node_text)
        return match.group(1).upper() if match else None

    def _extract_trigger_events(self, node: Any, lines: List[str]) -> List[str]:
        """Extract trigger events (INSERT/UPDATE/DELETE)."""
        node_text = self._get_node_text(node, lines)
        events = []
        for event in ["INSERT", "UPDATE", "DELETE"]:
            if re.search(rf"(?i)\b{event}\b", node_text):
                events.append(event)
        return events

    def _extract_cte_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract CTE name from WITH clause."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)([A-Za-z_][A-Za-z0-9_$.]*)\s+AS", node_text)
        return match.group(1) if match else None

    def _extract_table_columns(self, node: Any, lines: List[str]) -> List[str]:
        """Extract column names from CREATE TABLE statement."""
        columns = []
        node_text = self._get_node_text(node, lines)

        # Simple regex to find column definitions
        column_matches = re.findall(
            r"(?i)([A-Za-z_][A-Za-z0-9_]*)\s+(?:INT|VARCHAR|CHAR|TEXT|DECIMAL|FLOAT|DOUBLE|BOOLEAN|DATE|TIMESTAMP|BLOB)",
            node_text,
        )
        columns.extend(column_matches)

        return columns

    def _extract_table_constraints(self, node: Any, lines: List[str]) -> List[str]:
        """Extract constraints from CREATE TABLE statement."""
        constraints = []
        node_text = self._get_node_text(node, lines)

        # Look for common constraints
        if re.search(r"(?i)PRIMARY\s+KEY", node_text):
            constraints.append("PRIMARY KEY")
        if re.search(r"(?i)FOREIGN\s+KEY", node_text):
            constraints.append("FOREIGN KEY")
        if re.search(r"(?i)UNIQUE", node_text):
            constraints.append("UNIQUE")
        if re.search(r"(?i)CHECK", node_text):
            constraints.append("CHECK")
        if re.search(r"(?i)NOT\s+NULL", node_text):
            constraints.append("NOT NULL")

        return constraints

    def _extract_procedure_parameters(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract parameters from CREATE PROCEDURE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"\(([^)]*)\)", node_text, re.DOTALL)
        if match:
            params = match.group(1).strip()
            return params if params else None
        return None

    def _extract_function_parameters(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract parameters from CREATE FUNCTION statement."""
        return self._extract_procedure_parameters(node, lines)

    def _extract_function_return_type(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract return type from CREATE FUNCTION statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)RETURNS\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        return match.group(1) if match else None

    def _extract_select_tables(self, node: Any, lines: List[str]) -> List[str]:
        """Extract table names from SELECT statement."""
        tables = []
        node_text = self._get_node_text(node, lines)

        # Simple regex to find table names after FROM
        from_matches = re.findall(r"(?i)FROM\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        tables.extend(from_matches)

        # Also look for JOIN tables
        join_matches = re.findall(r"(?i)JOIN\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        tables.extend(join_matches)

        return list(set(tables))  # Remove duplicates

    def _handle_use_statement(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle USE statement."""
        database_name = self._extract_database_name(node, lines)
        if not database_name:
            return

        constructs.append(
            {
                "type": "use",
                "name": database_name,
                "path": database_name,
                "signature": f"USE {database_name}",
                "parent": None,
                "scope": "global",
                "line_start": node.start_point[0] + 1,
                "line_end": node.end_point[0] + 1,
                "text": self._get_node_text(node, lines),
                "context": {"declaration_type": "use"},
                "features": ["use_statement"],
            }
        )

    def _extract_insert_table_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract table name from INSERT statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        return match.group(1) if match else None

    def _extract_update_table_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract table name from UPDATE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)UPDATE\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        return match.group(1) if match else None

    def _extract_delete_table_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract table name from DELETE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)DELETE\s+(?:[A-Za-z_][A-Za-z0-9_$]*\s+)?FROM\s+([A-Za-z_][A-Za-z0-9_$.]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_alter_table_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract table name from ALTER TABLE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_$.]*)", node_text)
        return match.group(1) if match else None

    def _extract_alter_operation(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract operation from ALTER TABLE statement."""
        node_text = self._get_node_text(node, lines)
        operations = ["ADD", "DROP", "MODIFY", "ALTER", "RENAME"]
        for op in operations:
            if re.search(rf"(?i)\b{op}\b", node_text):
                return op
        return None

    def _extract_variable_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract variable name from DECLARE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(r"(?i)DECLARE\s+([A-Za-z_@][A-Za-z0-9_$]*)", node_text)
        return match.group(1) if match else None

    def _extract_variable_type(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract variable type from DECLARE statement."""
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)DECLARE\s+[A-Za-z_@][A-Za-z0-9_$]*\s+([A-Za-z_][A-Za-z0-9_$]*)",
            node_text,
        )
        return match.group(1) if match else None

    def _extract_cursor_name(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract cursor name from cursor declaration."""
        node_text = self._get_node_text(node, lines)
        match = re.search(
            r"(?i)DECLARE\s+([A-Za-z_][A-Za-z0-9_$.]*)\s+CURSOR", node_text
        )
        return match.group(1) if match else None

    def _is_significant_select(self, node: Any, lines: List[str]) -> bool:
        """Determine if a SELECT statement is significant enough to extract."""
        node_text = self._get_node_text(node, lines)
        # Consider SELECT statements with FROM clause as significant
        return bool(re.search(r"(?i)FROM\s+", node_text))
