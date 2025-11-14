"""Repository file browsing helper functions for CLI."""

from pathlib import Path
import asyncio
import click
from code_indexer.api_clients.repos_client import ReposAPIClient


async def get_repo_id_from_alias(user_alias: str, project_root: Path) -> str:
    """Get repository ID from user alias (async version for internal use)."""
    client = ReposAPIClient(server_url="", credentials={}, project_root=project_root)
    try:
        repos = await client.list_activated_repositories()
        for repo in repos:
            if repo.alias == user_alias:
                return user_alias
        raise ValueError(f"Repository '{user_alias}' not found")
    finally:
        await client.close()


def get_repo_id_from_alias_sync(server_url: str, credentials: dict, user_alias: str, project_root: Path) -> str:
    """Get repository ID from user alias (synchronous version for CLI commands)."""
    async def fetch() -> str:
        client = ReposAPIClient(
            server_url=server_url,
            credentials=credentials,
            project_root=project_root
        )
        try:
            repos = await client.list_activated_repositories()
            for repo in repos:
                if repo.alias == user_alias:
                    return user_alias
            raise ValueError(f"Repository '{user_alias}' not found")
        finally:
            await client.close()

    result: str = asyncio.run(fetch())
    return result


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def display_file_tree(files: list, base_path: str = ""):
    """Display files in tree format with icons."""
    if not files:
        click.echo("(empty directory)")
        return

    # Separate directories and files
    # Note: API returns files without 'type' field, only directories have is_directory=True
    dirs = [f for f in files if f.get("type") == "directory" or f.get("is_directory")]
    regular_files = [f for f in files if f.get("type") == "file" or (not f.get("is_directory", False))]

    # Sort alphabetically - handle both 'name' and 'path' fields
    dirs.sort(key=lambda x: x.get("path", x.get("name", "")))
    regular_files.sort(key=lambda x: x.get("path", x.get("name", "")))

    # Display header
    if base_path:
        click.echo(f"\nDirectory: {base_path}\n")

    # Display directories first
    for d in dirs:
        # Use 'path' if available (API response), fallback to 'name' (legacy)
        name = d.get("path", d.get("name", ""))
        click.echo(f"📁 {name}/")

    # Display files
    for f in regular_files:
        # Use 'path' if available (API response), fallback to 'name' (legacy)
        name = f.get("path", f.get("name", ""))
        # Use 'size_bytes' if available (API response), fallback to 'size' (legacy)
        size = f.get("size_bytes", f.get("size", 0))
        size_str = format_file_size(size)
        click.echo(f"📄 {name} ({size_str})")

    # Summary
    total = len(dirs) + len(regular_files)
    click.echo(f"\n{total} items ({len(dirs)} directories, {len(regular_files)} files)")


def display_with_line_numbers(content: str):
    """Display content with line numbers."""
    if not content:
        click.echo("(empty file)")
        return

    lines = content.split("\n")
    max_digits = len(str(len(lines)))

    for i, line in enumerate(lines, 1):
        line_num = str(i).rjust(max_digits)
        click.echo(f"{line_num} │ {line}")


def apply_syntax_highlighting(content: str, file_path: str) -> str:
    """Apply syntax highlighting based on file extension (optional)."""
    try:
        from pygments import highlight
        from pygments.lexers import get_lexer_for_filename
        from pygments.formatters import TerminalFormatter

        lexer = get_lexer_for_filename(file_path)
        result: str = str(highlight(content, lexer, TerminalFormatter()))
        return result
    except ImportError:
        # pygments not available, return plain content
        return content
    except Exception:
        # Any other error (unknown file type, etc.)
        return content
