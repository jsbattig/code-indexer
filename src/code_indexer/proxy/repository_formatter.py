"""Repository prefix formatter for multiplexed watch output (Story 5.4).

This module provides formatting functionality to prefix output lines with
repository identifiers, enabling clear identification of which repository
generated each message in multiplexed watch output.
"""

from pathlib import Path


class RepositoryPrefixFormatter:
    """Format repository identifiers for output prefixing.

    Formats repository paths as prefixes for watch output lines, allowing
    clear identification of which repository generated each message when
    watching multiple repositories simultaneously.
    """

    def __init__(self, proxy_root: Path):
        """Initialize formatter with proxy root directory.

        Args:
            proxy_root: Root directory of proxy configuration
        """
        self.proxy_root = Path(proxy_root).resolve()

    def format_prefix(self, repo_path: str, use_relative: bool = True) -> str:
        """Format repository path as prefix.

        Args:
            repo_path: Full or relative repository path
            use_relative: Use relative path from proxy root (default: True)

        Returns:
            Formatted prefix like "[backend/auth-service]"
        """
        if use_relative:
            display_path = self._get_relative_path(repo_path)
        else:
            display_path = repo_path

        return f"[{display_path}]"

    def _get_relative_path(self, repo_path: str) -> str:
        """Get path relative to proxy root.

        Args:
            repo_path: Repository path to convert

        Returns:
            Path relative to proxy root, or original path if not under proxy root
        """
        try:
            repo = Path(repo_path).resolve()
            relative = repo.relative_to(self.proxy_root)
            # Use forward slashes for consistency across platforms
            return str(relative).replace("\\", "/")
        except ValueError:
            # Path not relative to proxy root, use as-is
            return repo_path

    def format_output_line(self, repo_path: str, content: str) -> str:
        """Format complete output line with prefix.

        Args:
            repo_path: Repository path for prefix
            content: Output content to prefix

        Returns:
            Formatted line: "[repo-name] content"
        """
        prefix = self.format_prefix(repo_path)
        return f"{prefix} {content}"
