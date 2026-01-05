from code_indexer.server.middleware.correlation import get_correlation_id
"""
Composite repository file listing implementation.

Provides file listing functionality for composite repositories,
supporting Story 3.3 of the Server Composite Repository Activation epic.
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import List

from ..models.activated_repository import ActivatedRepository
from ..models.composite_file_models import FileInfo
from ...proxy.config_manager import ProxyConfigManager

logger = logging.getLogger(__name__)


def _walk_directory(
    directory: Path, repo_prefix: str, recursive: bool
) -> List[FileInfo]:
    """
    Walk directory and collect file information.

    Args:
        directory: Directory path to walk
        repo_prefix: Component repository prefix for paths
        recursive: Whether to walk recursively

    Returns:
        List of FileInfo objects for files in directory
    """
    files = []

    if recursive:
        # Recursive walk
        for item in directory.rglob("*"):
            # Skip .git and .code-indexer directories
            if ".git" in item.parts or ".code-indexer" in item.parts:
                continue

            if item.is_file():
                try:
                    relative_path = item.relative_to(directory)
                    stat_info = item.stat()

                    files.append(
                        FileInfo(
                            full_path=f"{repo_prefix}/{relative_path}",
                            name=item.name,
                            size=stat_info.st_size,
                            modified=datetime.fromtimestamp(stat_info.st_mtime),
                            is_directory=False,
                            component_repo=repo_prefix,
                        )
                    )
                except (OSError, ValueError) as e:
                    logger.warning(f"Cannot access file {item}: {e}", extra={"correlation_id": get_correlation_id()})
                    continue
    else:
        # Single level listing
        try:
            for item in directory.iterdir():
                # Skip .git and .code-indexer directories
                if item.name in [".git", ".code-indexer"]:
                    continue

                try:
                    relative_path = item.relative_to(directory)
                    stat_info = item.stat()

                    files.append(
                        FileInfo(
                            full_path=f"{repo_prefix}/{relative_path}",
                            name=item.name,
                            size=stat_info.st_size if item.is_file() else 0,
                            modified=datetime.fromtimestamp(stat_info.st_mtime),
                            is_directory=item.is_dir(),
                            component_repo=repo_prefix,
                        )
                    )
                except (OSError, ValueError) as e:
                    logger.warning(f"Cannot access item {item}: {e}", extra={"correlation_id": get_correlation_id()})
                    continue
        except OSError as e:
            logger.warning(f"Cannot access directory {directory}: {e}", extra={"correlation_id": get_correlation_id()})

    return files


def _list_composite_files(
    repo: ActivatedRepository, path: str = "", recursive: bool = False
) -> List[FileInfo]:
    """
    List files across all component repositories.

    Args:
        repo: Activated composite repository
        path: Optional path filter (subdirectory within components)
        recursive: Whether to walk recursively

    Returns:
        List of FileInfo objects sorted by full_path
    """
    files = []

    # Get component repos using ProxyConfigManager
    try:
        proxy_config = ProxyConfigManager(repo.path)
        discovered_repos = proxy_config.get_repositories()
    except Exception as e:
        logger.error(f"Failed to get discovered repos from {repo.path}: {e}", extra={"correlation_id": get_correlation_id()})
        return []

    # Walk each component repository
    for repo_name in discovered_repos:
        subrepo_path = repo.path / repo_name
        target_path = subrepo_path / path if path else subrepo_path

        if not target_path.exists():
            logger.debug(f"Path does not exist: {target_path}", extra={"correlation_id": get_correlation_id()})
            continue

        # Walk the component repository
        repo_files = _walk_directory(target_path, repo_name, recursive)
        files.extend(repo_files)

    # Sort by path for consistent output
    return sorted(files, key=lambda f: f.full_path)
