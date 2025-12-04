"""
Directory exploration service for hierarchical tree view generation.

Provides the DirectoryExplorerService that generates tree views of repository
directory structure, similar to the 'tree' command.
"""

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class TreeNode:
    """A node in the directory tree."""

    name: str
    path: str  # Relative path from repo root
    is_directory: bool
    children: Optional[List["TreeNode"]] = None  # None for files
    truncated: bool = False  # True if max_files exceeded
    hidden_count: int = 0  # Number of hidden children
    size_bytes: Optional[int] = None  # File size if show_stats


@dataclass
class DirectoryTreeResult:
    """Result of directory tree generation."""

    root: TreeNode
    tree_string: str  # Pre-formatted tree output
    total_directories: int
    total_files: int
    max_depth_reached: bool
    root_path: str


class DirectoryExplorerService:
    """Service for directory exploration and tree generation."""

    DEFAULT_EXCLUDE_PATTERNS = [
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        "vendor",
        "__pycache__",
        ".pytest_cache",
        ".tox",
        ".venv",
        "venv",
        ".idea",
        ".vscode",
        "*.pyc",
        "*.pyo",
    ]

    def __init__(self, repo_path: Path):
        """Initialize the directory explorer service.

        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path

    def generate_tree(
        self,
        path: Optional[str] = None,
        max_depth: int = 3,
        max_files_per_dir: int = 50,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        show_stats: bool = False,
        include_hidden: bool = False,
    ) -> DirectoryTreeResult:
        """Generate hierarchical directory tree.

        Args:
            path: Subdirectory to use as tree root (relative to repo root)
            max_depth: Maximum depth of tree to display (default: 3, range: 1-10)
            max_files_per_dir: Maximum files to show per directory (default: 50)
            include_patterns: Glob patterns for files to include
            exclude_patterns: Glob patterns for files/directories to exclude
            show_stats: Show statistics summary at end (default: False)
            include_hidden: Include hidden files/directories (default: False)

        Returns:
            DirectoryTreeResult with tree structure and formatted string

        Raises:
            ValueError: If path doesn't exist
        """
        # Determine the starting path
        if path:
            start_path = self.repo_path / path
            if not start_path.exists():
                raise ValueError(f"Path does not exist: {path}")
        else:
            start_path = self.repo_path

        # Merge exclude patterns with defaults
        all_excludes = list(self.DEFAULT_EXCLUDE_PATTERNS)
        if exclude_patterns:
            all_excludes.extend(exclude_patterns)

        # Track metrics
        total_dirs = 0
        total_files = 0
        max_depth_reached = False

        def should_exclude(name: str, is_dir: bool) -> bool:
            """Check if entry should be excluded."""
            # Always exclude .git
            if name == ".git":
                return True

            # Check hidden files
            if not include_hidden and name.startswith("."):
                return True

            # Check exclude patterns
            for pattern in all_excludes:
                if fnmatch.fnmatch(name, pattern):
                    return True

            return False

        def should_include_file(name: str) -> bool:
            """Check if file matches include patterns."""
            if not include_patterns:
                return True

            for pattern in include_patterns:
                if fnmatch.fnmatch(name, pattern):
                    return True

            return False

        def build_tree(
            current_path: Path, relative_path: str, current_depth: int
        ) -> Optional[TreeNode]:
            """Recursively build tree structure."""
            nonlocal total_dirs, total_files, max_depth_reached

            name = current_path.name or relative_path.split("/")[-1] or start_path.name

            if current_path.is_file():
                # Check include patterns for files
                if not should_include_file(name):
                    return None

                total_files += 1
                return TreeNode(
                    name=name,
                    path=relative_path,
                    is_directory=False,
                    children=None,
                )

            # It's a directory
            if current_depth > 0:
                total_dirs += 1

            # Check depth limit
            if current_depth >= max_depth:
                max_depth_reached = True
                return TreeNode(
                    name=name,
                    path=relative_path,
                    is_directory=True,
                    children=[],  # Empty children indicates truncated by depth
                    truncated=True,
                )

            # Get directory contents
            try:
                entries = list(current_path.iterdir())
            except PermissionError:
                return TreeNode(
                    name=name,
                    path=relative_path,
                    is_directory=True,
                    children=[],
                )

            # Sort entries: directories first, then files, both alphabetically
            dirs = []
            files = []

            for entry in entries:
                # Skip excluded entries
                if should_exclude(entry.name, entry.is_dir()):
                    continue

                # Skip symlinks to prevent loops
                if entry.is_symlink():
                    # Include as a file but don't follow
                    if entry.is_file() or not entry.is_dir():
                        if should_include_file(entry.name):
                            files.append(entry)
                    continue

                if entry.is_dir():
                    dirs.append(entry)
                elif entry.is_file():
                    if should_include_file(entry.name):
                        files.append(entry)

            # Sort alphabetically (case-insensitive)
            dirs.sort(key=lambda e: e.name.lower())
            files.sort(key=lambda e: e.name.lower())

            # Build children nodes
            children: List[TreeNode] = []
            truncated = False
            hidden_count = 0

            # Add directories first
            for entry in dirs:
                child_relative = (
                    f"{relative_path}/{entry.name}" if relative_path else entry.name
                )
                child_node = build_tree(entry, child_relative, current_depth + 1)
                if child_node:
                    # If include_patterns specified, only include dirs with matching descendants
                    if include_patterns:
                        if child_node.is_directory:
                            if child_node.children or not include_patterns:
                                children.append(child_node)
                    else:
                        children.append(child_node)

            # Add files with truncation
            file_count = 0
            for entry in files:
                if file_count >= max_files_per_dir:
                    hidden_count = len(files) - max_files_per_dir
                    truncated = True
                    break

                child_relative = (
                    f"{relative_path}/{entry.name}" if relative_path else entry.name
                )
                child_node = build_tree(entry, child_relative, current_depth + 1)
                if child_node:
                    children.append(child_node)
                    file_count += 1

            return TreeNode(
                name=name,
                path=relative_path,
                is_directory=True,
                children=children,
                truncated=truncated,
                hidden_count=hidden_count,
            )

        # Build the tree starting from start_path
        root_name = start_path.name if start_path != self.repo_path else self.repo_path.name
        root = build_tree(start_path, "", 0)

        if root is None:
            root = TreeNode(
                name=root_name,
                path="",
                is_directory=True,
                children=[],
            )

        root.name = root_name

        # Generate tree string
        tree_string = self._format_tree_string(
            root, show_stats, total_dirs, total_files
        )

        return DirectoryTreeResult(
            root=root,
            tree_string=tree_string,
            total_directories=total_dirs,
            total_files=total_files,
            max_depth_reached=max_depth_reached,
            root_path=str(start_path),
        )

    def _format_tree_string(
        self,
        root: TreeNode,
        show_stats: bool,
        total_dirs: int,
        total_files: int,
    ) -> str:
        """Format the tree as a string.

        Args:
            root: Root TreeNode
            show_stats: Whether to include summary statistics
            total_dirs: Total directory count
            total_files: Total file count

        Returns:
            Formatted tree string
        """
        lines: List[str] = []

        # Root line
        if root.is_directory:
            lines.append(f"{root.name}/")
        else:
            lines.append(root.name)

        def format_children(
            node: TreeNode, prefix: str = "", is_last: bool = True
        ) -> None:
            """Recursively format children."""
            if not node.children:
                return

            children = node.children
            num_children = len(children)

            for i, child in enumerate(children):
                is_last_child = i == num_children - 1 and not node.truncated
                connector = "+--" if is_last_child else "|--"
                extension = "    " if is_last_child else "|   "

                if child.is_directory:
                    # Check if directory was depth-limited
                    if child.truncated and not child.children:
                        lines.append(f"{prefix}{connector} {child.name}/ [...]")
                    else:
                        lines.append(f"{prefix}{connector} {child.name}/")
                        format_children(child, prefix + extension, is_last_child)
                else:
                    lines.append(f"{prefix}{connector} {child.name}")

            # Add truncation indicator if files were hidden
            if node.truncated and node.hidden_count > 0:
                connector = "+--"
                lines.append(
                    f"{prefix}{connector} [+{node.hidden_count} more files]"
                )

        format_children(root)

        # Add statistics if requested
        if show_stats:
            lines.append("")
            lines.append(f"{total_dirs} directories, {total_files} files")

        return "\n".join(lines)
