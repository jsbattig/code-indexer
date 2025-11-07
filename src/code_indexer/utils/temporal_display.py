"""Display utilities for temporal search results.

Provides rich console formatting for temporal query results including
commit messages, file chunks, and diff context.
"""

from typing import Any, Dict, List
from rich.console import Console

console = Console()


def display_temporal_results(results: Any, quiet: bool = False):
    """Display temporal search results with proper ordering and formatting.

    Args:
        results: Can be either:
            - SearchResult object with .results attribute (from standalone mode)
            - Dict with 'results' key (from daemon mode)
        quiet: If True, suppress headers and metadata
    """
    # Handle both SearchResult objects and dicts
    if hasattr(results, "results"):
        # Standalone mode - SearchResult object
        result_list = results.results
        total_found = getattr(results, "total_found", len(result_list))
        query_time = (
            results.performance.get("total_time", 0)
            if hasattr(results, "performance") and results.performance
            else 0
        )
    else:
        # Daemon mode - dict response
        result_list = results.get("results", [])
        total_found = results.get("total_found", len(result_list))
        query_time = results.get("performance", {}).get("total_time", 0)

    if not quiet:
        console.print(f"\n🔍 Found {total_found} temporal results")
        if query_time:
            console.print(f"⏱️  Query time: {query_time:.3f}s")

    # Separate results by type
    commit_msg_matches = []
    file_chunk_matches = []

    for result in result_list:
        # Handle both SearchResult objects and dicts
        if isinstance(result, dict):
            match_type = result.get("metadata", {}).get("type", "file_chunk")
        else:
            match_type = result.metadata.get("type", "file_chunk")

        if match_type == "commit_message":
            commit_msg_matches.append(result)
        else:
            file_chunk_matches.append(result)

    # Display commit messages first, then file chunks
    index = 1

    for result in commit_msg_matches:
        _display_commit_message_match(result, index)
        index += 1

    for result in file_chunk_matches:
        _display_file_chunk_match(result, index)
        index += 1


def _display_file_chunk_match(result: Any, index: int):
    """Display a file chunk temporal match with diff.

    Args:
        result: Either SearchResult object or dict from daemon
        index: Display index number
    """
    # Handle both dict and object formats
    if isinstance(result, dict):
        metadata = result.get("metadata", {})
        temporal_ctx = result.get("temporal_context", {})
        content = result.get("content", "")
        score = result.get("score", 0.0)
    else:
        metadata = result.metadata
        temporal_ctx = getattr(result, "temporal_context", {})
        content = result.content
        score = result.score

    file_path = metadata.get("path") or metadata.get("file_path", "unknown")
    line_start = metadata.get("line_start", 0)
    line_end = metadata.get("line_end", 0)
    commit_hash = metadata.get("commit_hash", "")
    diff_type = metadata.get("diff_type", "unknown")

    # Get commit details from temporal_context
    commit_date = temporal_ctx.get("commit_date", "Unknown")
    author_name = temporal_ctx.get("author_name", "Unknown")
    commit_message = temporal_ctx.get("commit_message", "[No message available]")

    # For backward compatibility, check metadata too
    if author_name == "Unknown" and "author_name" in metadata:
        author_name = metadata.get("author_name", "Unknown")
    if commit_date == "Unknown" and "commit_date" in metadata:
        commit_date = metadata.get("commit_date", "Unknown")
    if commit_message == "[No message available]" and "commit_message" in metadata:
        commit_message = metadata.get("commit_message", "[No message available]")

    # Get author email from metadata
    author_email = metadata.get("author_email", "unknown@example.com")

    # Smart line number display: suppress :0-0 for temporal diffs
    if line_start == 0 and line_end == 0:
        # Temporal diffs have no specific line range - suppress :0-0
        file_location = file_path
    else:
        # Regular results or temporal with specific lines - show range
        file_location = f"{file_path}:{line_start}-{line_end}"

    # Display header with diff-type marker
    diff_markers = {
        "added": "[ADDED]",
        "deleted": "[DELETED]",
        "modified": "[MODIFIED]",
        "renamed": "[RENAMED]",
        "binary": "[BINARY]",
    }
    marker = diff_markers.get(diff_type, "")

    if marker:
        console.print(f"\n[bold cyan]{index}. {file_location}[/bold cyan] {marker}")
    else:
        console.print(f"\n[bold cyan]{index}. {file_location}[/bold cyan]")
    console.print(f"   Score: {score:.3f}")
    console.print(f"   Commit: {commit_hash[:7]} ({commit_date})")
    console.print(f"   Author: {author_name} <{author_email}>")

    # Display full commit message (NOT truncated)
    message_lines = commit_message.split("\n")
    console.print(f"   Message: {message_lines[0]}")
    for msg_line in message_lines[1:]:
        console.print(f"            {msg_line}")

    console.print()

    # Display rename indicator if present
    if "display_note" in metadata:
        console.print(f"   {metadata['display_note']}", style="yellow")
        console.print()

    # Display content
    console.print()
    lines = content.split("\n")

    # Modified diffs are self-documenting with @@ markers and +/- prefixes
    # Suppress line numbers for them to avoid confusion
    show_line_numbers = diff_type != "modified"

    if show_line_numbers:
        for i, line in enumerate(lines):
            line_num = line_start + i
            console.print(f"{line_num:4d}  {line}")
    else:
        # Modified diff - no line numbers (diff markers are self-documenting)
        for line in lines:
            console.print(f"  {line}")


def _display_commit_message_match(result: Any, index: int):
    """Display a commit message temporal match.

    Args:
        result: Either SearchResult object or dict from daemon
        index: Display index number
    """
    # Handle both dict and object formats
    if isinstance(result, dict):
        metadata = result.get("metadata", {})
        temporal_ctx = result.get("temporal_context", {})
        content = result.get("content", "")
        score = result.get("score", 0.0)
    else:
        metadata = result.metadata
        temporal_ctx = getattr(result, "temporal_context", {})
        content = result.content
        score = result.score

    commit_hash = metadata.get("commit_hash", "")

    # Get commit details from temporal_context
    commit_date = temporal_ctx.get(
        "commit_date", metadata.get("commit_date", "Unknown")
    )
    author_name = temporal_ctx.get(
        "author_name", metadata.get("author_name", "Unknown")
    )
    author_email = metadata.get("author_email", "unknown@example.com")

    # Display header
    console.print(f"\n[bold cyan]{index}. [COMMIT MESSAGE MATCH][/bold cyan]")
    console.print(f"   Score: {score:.3f}")
    console.print(f"   Commit: {commit_hash[:7]} ({commit_date})")
    console.print(f"   Author: {author_name} <{author_email}>")
    console.print()

    # Display matching section of commit message
    console.print("   Message (matching section):")
    for line in content.split("\n"):
        console.print(f"   {line}")
    console.print()
