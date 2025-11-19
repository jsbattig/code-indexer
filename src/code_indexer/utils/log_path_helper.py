"""Helper functions for debug log path management."""

from pathlib import Path


def get_debug_log_path(config_dir: Path, log_name: str) -> Path:
    """
    Get path for debug log file within .code-indexer directory.

    Creates .code-indexer/.tmp directory if it doesn't exist and returns
    the path for the specified debug log file.

    Args:
        config_dir: Path to .code-indexer configuration directory
        log_name: Name of the debug log file (e.g., 'cidx_debug.log')

    Returns:
        Path to debug log file within .code-indexer/.tmp directory
    """
    tmp_dir = config_dir / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir / log_name
