"""
Factory for creating properly configured GlobalRegistry instances.

Story #713: This factory ensures all server code uses SQLite backend
for GlobalRegistry, eliminating the storage mismatch between
GoldenRepoManager (SQLite) and GlobalRegistry (JSON).
"""

from pathlib import Path
from typing import Optional

from code_indexer.global_repos.global_registry import GlobalRegistry


def get_server_global_registry(
    golden_repos_dir: str,
    server_data_dir: Optional[str] = None,
) -> GlobalRegistry:
    """
    Create a GlobalRegistry instance configured for server mode (SQLite backend).

    This factory function should be used by ALL server code (MCP handlers,
    REST routes, services) to ensure consistent SQLite storage backend.

    Args:
        golden_repos_dir: Path to golden repos directory
        server_data_dir: Path to server data directory (for db_path).
                        If None, derives from golden_repos_dir parent.

    Returns:
        GlobalRegistry configured with SQLite backend

    Example:
        # Typical usage in handlers.py:
        golden_repos_dir = _get_golden_repos_dir()
        registry = get_server_global_registry(golden_repos_dir)

        # With explicit server_data_dir:
        registry = get_server_global_registry(
            golden_repos_dir=golden_repos_dir,
            server_data_dir=server_data_dir
        )
    """
    golden_repos_path = Path(golden_repos_dir)

    if server_data_dir is None:
        # golden_repos_dir is typically: ~/.cidx-server/data/golden-repos
        # server_data_dir would be: ~/.cidx-server/data
        server_data_dir = str(golden_repos_path.parent)

    db_path = str(Path(server_data_dir) / "cidx_server.db")

    return GlobalRegistry(
        golden_repos_dir=golden_repos_dir,
        use_sqlite=True,
        db_path=db_path,
    )
