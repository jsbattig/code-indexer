"""MCP Tool Registry - Defines tools with JSON schemas and role requirements."""

from typing import List, Dict, Any
from code_indexer.server.auth.user_manager import User


def filter_tools_by_role(user: User) -> List[Dict[str, Any]]:
    """
    Filter tools based on user role and permissions.

    Args:
        user: Authenticated user with role information

    Returns:
        List of tool definitions available to the user
    """
    return []
