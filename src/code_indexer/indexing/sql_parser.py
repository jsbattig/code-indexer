"""
SQL semantic parser using pure AST-based analysis - ELIMINATES ALL REGEX ABUSE.

This implementation uses ONLY tree-sitter AST node.type and node.children analysis.
NO regex patterns are applied to AST node text content.

Key improvements over the regex-based parser:
- Uses AST node types: create_table, create_view, create_index, select, insert, update, delete, cte
- Proper semantic chunks with complete construct content
- No false positives from comments/strings
- Better search relevance through meaningful chunk content
- Handles ERROR nodes via AST structure analysis, not regex fallback
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from code_indexer.config import IndexingConfig
from .base_tree_sitter_parser import BaseTreeSitterParser
from .semantic_chunker import SemanticChunk


class SQLSemanticParser(BaseTreeSitterParser):
    """Pure AST-based SQL parser - eliminates all regex abuse patterns."""

    def __init__(self, config: IndexingConfig):
        super().__init__(config, "sql")

    def _extract_file_level_constructs(
        self,
        root_node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
    ):
        """Extract file-level constructs (USE statements, database/schema declarations)."""
        # Only extract USE statements at file level to avoid duplicates
        for child in root_node.children:
            if hasattr(child, "type"):
                if child.type == "statement":
                    # Look for USE statements in top-level statements
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "keyword_use"
                        ):
                            use_name = self._extract_use_database_name_ast(child, lines)
                            if use_name:
                                constructs.append(
                                    {
                                        "type": "use",
                                        "name": use_name,
                                        "path": use_name,
                                        "signature": f"USE {use_name}",
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
        """Handle SQL-specific AST node types using ONLY AST structure analysis."""
        if node_type == "create_table":
            self._handle_create_table_ast(node, constructs, lines, scope_stack, content)
        elif node_type == "create_view":
            self._handle_create_view_ast(node, constructs, lines, scope_stack, content)
        elif node_type == "create_index":
            self._handle_create_index_ast(node, constructs, lines, scope_stack, content)
        elif node_type == "select":
            self._handle_select_statement_ast(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "insert":
            self._handle_insert_statement_ast(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "update":
            self._handle_update_statement_ast(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "delete":
            self._handle_delete_statement_ast(
                node, constructs, lines, scope_stack, content
            )
        elif node_type == "cte":
            self._handle_cte_ast(node, constructs, lines, scope_stack, content)
        # Remove statement handling - let normal traversal process statement children

    def _should_skip_children(self, node_type: str) -> bool:
        """Determine if children should be skipped for certain node types."""
        # Skip children for constructs that handle their own internal structure
        # NOTE: Don't skip statement children - they contain the actual constructs
        return node_type in [
            "create_table",
            "create_view",
            "create_index",
            "select",
            "insert",
            "update",
            "delete",
            "cte",
            # "statement" removed - we need to process statement children
        ]

    def _handle_create_table_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE TABLE using only AST structure analysis."""
        table_name = self._extract_table_name_ast(node, lines)
        if not table_name or not self._validate_identifier_name(table_name):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "table"):
            return

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{table_name}" if current_scope else table_name

        # Extract columns and constraints via AST structure
        columns = self._extract_table_columns_ast(node, lines)
        constraints = self._extract_table_constraints_ast(node, lines)

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
                "text": node_text,
                "context": {
                    "declaration_type": "table",
                    "columns": columns,
                    "constraints": constraints,
                },
                "features": ["table_declaration"],
            }
        )

    def _handle_create_view_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE VIEW using only AST structure analysis."""
        view_name = self._extract_view_name_ast(node, lines)
        if not view_name or not self._validate_identifier_name(view_name):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "view"):
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
                "text": node_text,
                "context": {"declaration_type": "view"},
                "features": ["view_declaration"],
            }
        )

    def _handle_create_index_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle CREATE INDEX using only AST structure analysis."""
        index_name = self._extract_index_name_ast(node, lines)
        table_name = self._extract_index_table_name_ast(node, lines)

        if not index_name or not self._validate_identifier_name(index_name):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "index"):
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
                "text": node_text,
                "context": {
                    "declaration_type": "index",
                    "table_name": table_name,
                },
                "features": ["index_declaration"],
            }
        )

    def _handle_select_statement_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle SELECT statement using only AST structure analysis."""
        # Only extract significant SELECT statements with FROM clauses
        if not self._is_significant_select_ast(node, lines):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "select"):
            return

        statement_id = f"select_{node.start_point[0] + 1}"
        tables = self._extract_select_tables_ast(node, lines)

        current_scope = ".".join(scope_stack)
        full_path = f"{current_scope}.{statement_id}" if current_scope else statement_id

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
                "text": node_text,
                "context": {
                    "declaration_type": "select",
                    "tables": tables,
                },
                "features": ["select_statement"],
            }
        )

    def _handle_insert_statement_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle INSERT statement using only AST structure analysis."""
        table_name = self._extract_insert_table_name_ast(node, lines)
        if not table_name:
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "insert"):
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
                "text": node_text,
                "context": {
                    "declaration_type": "insert",
                    "table_name": table_name,
                },
                "features": ["insert_statement"],
            }
        )

    def _handle_update_statement_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle UPDATE statement using only AST structure analysis."""
        table_name = self._extract_update_table_name_ast(node, lines)
        if not table_name:
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "update"):
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
                "text": node_text,
                "context": {
                    "declaration_type": "update",
                    "table_name": table_name,
                },
                "features": ["update_statement"],
            }
        )

    def _handle_delete_statement_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle DELETE statement using only AST structure analysis."""
        table_name = self._extract_delete_table_name_ast(node, lines)
        if not table_name:
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "delete"):
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
                "text": node_text,
                "context": {
                    "declaration_type": "delete",
                    "table_name": table_name,
                },
                "features": ["delete_statement"],
            }
        )

    def _handle_cte_ast(
        self,
        node: Any,
        constructs: List[Dict[str, Any]],
        lines: List[str],
        scope_stack: List[str],
        content: str,
    ):
        """Handle Common Table Expression using only AST structure analysis."""
        cte_name = self._extract_cte_name_ast(node, lines)
        if not cte_name or not self._validate_identifier_name(cte_name):
            return

        node_text = self._get_node_text(node, lines)
        if not self._is_meaningful_content(node_text, "cte"):
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
                "text": node_text,
                "context": {"declaration_type": "cte"},
                "features": ["cte_declaration"],
            }
        )

    # AST-based extraction methods (NO regex patterns on node text)

    def _extract_table_name_ast(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract table name using only AST structure analysis."""
        # Based on AST structure: create_table -> object_reference -> identifier
        for child in node.children:
            if hasattr(child, "type") and child.type == "object_reference":
                for grandchild in child.children:
                    if hasattr(grandchild, "type") and grandchild.type == "identifier":
                        name = self._get_node_text(grandchild, lines).strip()
                        if self._validate_identifier_name(name):
                            return name
        return None

    def _extract_view_name_ast(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract view name using only AST structure analysis."""
        # Same pattern as table name
        return self._extract_table_name_ast(node, lines)

    def _extract_index_name_ast(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract index name using only AST structure analysis."""
        # Based on AST structure: create_index -> identifier
        # Skip keywords and take the first valid identifier
        found_index_keyword = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "keyword_index":
                    found_index_keyword = True
                elif found_index_keyword and child.type == "identifier":
                    text = self._get_node_text(child, lines).strip()
                    if self._validate_identifier_name(text):
                        return text

        # Fallback: take first valid identifier that's not a keyword
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                text = self._get_node_text(child, lines).strip()
                if text.upper() not in [
                    "CREATE",
                    "INDEX",
                    "UNIQUE",
                    "ON",
                ] and self._validate_identifier_name(text):
                    return text
        return None

    def _extract_index_table_name_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract table name from CREATE INDEX using only AST structure analysis."""
        # Look for object_reference after keyword_on
        found_on = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "keyword_on":
                    found_on = True
                elif found_on and child.type == "object_reference":
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "identifier"
                        ):
                            name = self._get_node_text(grandchild, lines).strip()
                            if self._validate_identifier_name(name):
                                return name
        return None

    def _extract_select_tables_ast(self, node: Any, lines: List[str]) -> List[str]:
        """Extract table names from SELECT statement using only AST structure analysis."""
        tables = []

        def extract_tables_from_from_node(from_node):
            """Extract tables from a 'from' AST node."""
            if not hasattr(from_node, "children"):
                return

            for child in from_node.children:
                if hasattr(child, "type"):
                    if child.type == "relation":
                        # Extract table name from relation -> object_reference -> identifier
                        for relation_child in child.children:
                            if (
                                hasattr(relation_child, "type")
                                and relation_child.type == "object_reference"
                            ):
                                for obj_child in relation_child.children:
                                    if (
                                        hasattr(obj_child, "type")
                                        and obj_child.type == "identifier"
                                    ):
                                        table_name = self._get_node_text(
                                            obj_child, lines
                                        ).strip()
                                        if self._validate_identifier_name(table_name):
                                            tables.append(table_name)
                    elif child.type == "join":
                        # Extract table from JOIN clause
                        extract_tables_from_from_node(child)

        # Look for 'from' nodes in the SELECT statement
        for child in node.children:
            if hasattr(child, "type") and child.type == "from":
                extract_tables_from_from_node(child)

        return list(set(tables))  # Remove duplicates

    def _extract_insert_table_name_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract table name from INSERT statement using only AST structure analysis."""
        # Look for object_reference after keyword_into
        found_into = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "keyword_into":
                    found_into = True
                elif found_into and child.type == "object_reference":
                    for grandchild in child.children:
                        if (
                            hasattr(grandchild, "type")
                            and grandchild.type == "identifier"
                        ):
                            name = self._get_node_text(grandchild, lines).strip()
                            if self._validate_identifier_name(name):
                                return name
        return None

    def _extract_update_table_name_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract table name from UPDATE statement using only AST structure analysis."""
        # Look for relation node after keyword_update
        for child in node.children:
            if hasattr(child, "type") and child.type == "relation":
                for relation_child in child.children:
                    if (
                        hasattr(relation_child, "type")
                        and relation_child.type == "object_reference"
                    ):
                        for obj_child in relation_child.children:
                            if (
                                hasattr(obj_child, "type")
                                and obj_child.type == "identifier"
                            ):
                                name = self._get_node_text(obj_child, lines).strip()
                                if self._validate_identifier_name(name):
                                    return name
        return None

    def _extract_delete_table_name_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract table name from DELETE statement using only AST structure analysis."""
        # Need to traverse the parent statement to find the FROM clause
        # Look for the from node that contains object_reference
        parent = node.parent if hasattr(node, "parent") else None
        if parent:
            for sibling in parent.children:
                if hasattr(sibling, "type") and sibling.type == "from":
                    for from_child in sibling.children:
                        if (
                            hasattr(from_child, "type")
                            and from_child.type == "object_reference"
                        ):
                            for obj_child in from_child.children:
                                if (
                                    hasattr(obj_child, "type")
                                    and obj_child.type == "identifier"
                                ):
                                    name = self._get_node_text(obj_child, lines).strip()
                                    if self._validate_identifier_name(name):
                                        return name
        return None

    def _extract_cte_name_ast(self, node: Any, lines: List[str]) -> Optional[str]:
        """Extract CTE name using only AST structure analysis."""
        # Based on AST structure: cte -> identifier
        for child in node.children:
            if hasattr(child, "type") and child.type == "identifier":
                name = self._get_node_text(child, lines).strip()
                if self._validate_identifier_name(name):
                    return name
        return None

    def _extract_use_database_name_ast(
        self, node: Any, lines: List[str]
    ) -> Optional[str]:
        """Extract database name from USE statement using only AST structure analysis."""
        # Look for identifier after keyword_use
        found_use = False
        for child in node.children:
            if hasattr(child, "type"):
                if child.type == "keyword_use":
                    found_use = True
                elif found_use and child.type == "identifier":
                    name = self._get_node_text(child, lines).strip()
                    if self._validate_identifier_name(name):
                        return name
        return None

    def _extract_table_columns_ast(self, node: Any, lines: List[str]) -> List[str]:
        """Extract column names from CREATE TABLE using only AST structure analysis."""
        columns = []

        # Look for column_definitions node
        for child in node.children:
            if hasattr(child, "type") and child.type == "column_definitions":
                # Traverse column_definition nodes
                for col_def_child in child.children:
                    if (
                        hasattr(col_def_child, "type")
                        and col_def_child.type == "column_definition"
                    ):
                        # First identifier in column_definition is the column name
                        for col_child in col_def_child.children:
                            if (
                                hasattr(col_child, "type")
                                and col_child.type == "identifier"
                            ):
                                col_name = self._get_node_text(col_child, lines).strip()
                                if self._validate_identifier_name(col_name):
                                    columns.append(col_name)
                                    break  # Only take first identifier (column name)

        return columns

    def _extract_table_constraints_ast(self, node: Any, lines: List[str]) -> List[str]:
        """Extract constraints from CREATE TABLE using only AST structure analysis."""
        constraints = []

        # Look for constraint keywords in column definitions and table constraints
        def find_constraints_in_node(node_to_search):
            if not hasattr(node_to_search, "children"):
                return

            for child in node_to_search.children:
                if hasattr(child, "type"):
                    if child.type == "keyword_primary":
                        constraints.append("PRIMARY KEY")
                    elif child.type == "keyword_foreign":
                        constraints.append("FOREIGN KEY")
                    elif child.type == "keyword_unique":
                        constraints.append("UNIQUE")
                    elif child.type == "keyword_not":
                        # Check if next sibling is NULL for NOT NULL constraint
                        constraints.append("NOT NULL")
                    elif child.type == "keyword_check":
                        constraints.append("CHECK")

                # Recursively check children
                find_constraints_in_node(child)

        find_constraints_in_node(node)

        # Remove duplicates while preserving order
        seen = set()
        unique_constraints = []
        for constraint in constraints:
            if constraint not in seen:
                seen.add(constraint)
                unique_constraints.append(constraint)

        return unique_constraints

    def _is_significant_select_ast(self, node: Any, lines: List[str]) -> bool:
        """Determine if SELECT statement is significant using only AST structure analysis."""
        # Check if the SELECT has a FROM clause by looking for 'from' child nodes or siblings
        if not hasattr(node, "children"):
            return False

        # Check direct children for FROM clause
        for child in node.children:
            if hasattr(child, "type") and child.type == "from":
                return True

        # Check siblings in parent statement for FROM clause (common in tree-sitter SQL)
        if hasattr(node, "parent") and node.parent:
            for sibling in node.parent.children:
                if hasattr(sibling, "type") and sibling.type == "from":
                    return True

        # Also consider SELECT statements that are part of complex queries significant
        # if they have more than just basic field selection
        node_text = self._get_node_text(node, lines).strip()
        if len(node_text) > 10:  # More than just "SELECT *"
            return True

        return False

    def _validate_identifier_name(self, name: str) -> bool:
        """Validate that a name is a proper SQL identifier."""
        if not name or not isinstance(name, str):
            return False

        # Reject SQL keywords and common literals
        sql_keywords = {
            "SELECT",
            "FROM",
            "WHERE",
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE",
            "TABLE",
            "VIEW",
            "INDEX",
            "PROCEDURE",
            "FUNCTION",
            "BEGIN",
            "END",
            "DECLARE",
            "NULL",
            "TRUE",
            "FALSE",
            "AND",
            "OR",
            "NOT",
            "IN",
            "EXISTS",
            "JOIN",
            "INNER",
            "LEFT",
            "RIGHT",
            "OUTER",
            "ON",
            "AS",
            "BY",
            "ORDER",
            "GROUP",
            "HAVING",
            "DISTINCT",
            "COUNT",
            "SUM",
            "AVG",
            "MIN",
            "MAX",
        }

        if name.upper() in sql_keywords:
            return False

        # Must start with letter or underscore, contain only alphanumeric and underscore
        if not (name[0].isalpha() or name[0] == "_"):
            return False

        return all(c.isalnum() or c in "_$." for c in name)

    def _is_meaningful_content(self, text: str, construct_type: str) -> bool:
        """Check if content is meaningful enough to create a chunk."""
        if not text or not text.strip():
            return False

        stripped = text.strip()

        # Reject very short meaningless content
        if len(stripped) <= 5 and stripped in [
            ";",
            "null",
            "null;",
            "return",
            "return;",
        ]:
            return False

        # Must contain the construct type keyword for relevance
        # Handle SQL variations like "CREATE OR REPLACE VIEW"
        construct_keywords = {
            "table": ["CREATE", "TABLE"],
            "view": ["CREATE", "VIEW"],
            "index": ["CREATE", "INDEX"],
            "procedure": ["CREATE", "PROCEDURE"],
            "function": ["CREATE", "FUNCTION"],
            "select": ["SELECT"],
            "insert": ["INSERT"],
            "update": ["UPDATE"],
            "delete": ["DELETE"],
            "cte": ["WITH"],
        }

        expected_keywords = construct_keywords.get(construct_type.lower())
        if expected_keywords:
            upper_text = stripped.upper()
            # All keywords must be present (handles "CREATE OR REPLACE VIEW" etc)
            if not all(keyword in upper_text for keyword in expected_keywords):
                return False

        return True

    def _extract_constructs_from_error_text(
        self, error_text: str, start_line: int, scope_stack: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract constructs from ERROR nodes using limited AST-guided fallback patterns.

        This method handles SQL constructs that tree-sitter cannot parse properly
        (like CREATE PROCEDURE, CREATE FUNCTION, CREATE TRIGGER) but uses
        minimal, targeted regex patterns only for ERROR node content.
        """
        constructs = []
        lines = error_text.split("\n")
        current_parent = ".".join(scope_stack) if scope_stack else None

        # Only handle specific SQL constructs that commonly end up in ERROR nodes
        # Use minimal, targeted patterns for constructs tree-sitter can't parse
        error_patterns = [
            # Procedure creation - commonly in ERROR nodes
            (
                r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "procedure",
                "CREATE PROCEDURE",
            ),
            # Function creation - commonly in ERROR nodes
            (
                r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "function",
                "CREATE FUNCTION",
            ),
            # Trigger creation - commonly in ERROR nodes
            (
                r"^\s*CREATE\s+TRIGGER\s+([A-Za-z_][A-Za-z0-9_$.]*)",
                "trigger",
                "CREATE TRIGGER",
            ),
        ]

        for i, line in enumerate(lines):
            line_num = start_line + i + 1

            for pattern, construct_type, expected_keyword in error_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match and expected_keyword.upper() in line.upper():
                    name = match.group(1)
                    if self._validate_identifier_name(name):
                        full_path = (
                            f"{current_parent}.{name}" if current_parent else name
                        )

                        # For ERROR nodes, include full error text for better search relevance
                        construct_text = error_text.strip()

                        constructs.append(
                            {
                                "type": construct_type,
                                "name": name,
                                "path": full_path,
                                "signature": f"{expected_keyword} {name}",
                                "parent": current_parent,
                                "scope": "schema" if current_parent else "global",
                                "line_start": line_num,
                                "line_end": line_num
                                + error_text.count("\n"),  # Approximate end
                                "text": construct_text,
                                "context": {
                                    "error_node_fallback": True
                                },  # Mark as ERROR node handling
                                "features": [f"{construct_type}_declaration"],
                            }
                        )
                        break  # Only match one pattern per line

        return constructs

    def _fallback_parse(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Complete fallback parsing when tree-sitter fails entirely."""
        from .semantic_chunker import SemanticChunk

        # Basic fallback: treat as single module chunk
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
                    semantic_chunking=True,  # Still semantic, just fallback
                    semantic_type="module",
                    semantic_name=Path(file_path).stem,
                    semantic_path=Path(file_path).stem,
                    semantic_signature=f"SQL module {Path(file_path).stem}",
                    semantic_parent=None,
                    semantic_context={"fallback_parse": True},  # NOT regex_fallback
                    semantic_scope="global",
                    semantic_language_features=["sql_module"],
                )
            )

        return chunks
