"""Multi-repository query functionality for CIDX CLI (Story #676).

Provides execution and display logic for querying multiple repositories simultaneously
via the /api/query/multi endpoint in remote mode.
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
from rich.console import Console


async def execute_multi_repo_query(
    query_text: str,
    repos: List[str],
    limit: int,
    project_root: Path,
    languages: tuple = (),
    exclude_languages: tuple = (),
    path_filter: tuple = (),
    exclude_paths: tuple = (),
    min_score: Optional[float] = None,
    accuracy: str = "balanced",
) -> dict:
    """Execute multi-repository query via /api/query/multi endpoint.

    Args:
        query_text: Search query text
        repos: List of repository aliases
        limit: Maximum results per repository
        project_root: Project root path
        languages: Language filters
        exclude_languages: Languages to exclude
        path_filter: Path pattern filters
        exclude_paths: Path patterns to exclude
        min_score: Minimum similarity score
        accuracy: Search accuracy profile

    Returns:
        Dictionary with results per repository

    Raises:
        ValueError: If repos list is empty or query_text is invalid
        Exception: If query execution fails
    """
    # Validate inputs
    if not repos:
        raise ValueError(
            "At least one repository must be specified for multi-repo query"
        )

    if not query_text or not query_text.strip():
        raise ValueError("Query text cannot be empty")

    # Warn about parameters not yet supported by server
    unsupported_params = []
    if exclude_languages:
        unsupported_params.append("exclude_languages")
    if exclude_paths:
        unsupported_params.append("exclude_paths")
    if accuracy and accuracy != "balanced":
        unsupported_params.append("accuracy")

    if unsupported_params:
        console = Console(stderr=True)
        console.print(
            f"[yellow]Warning: {', '.join(unsupported_params)} not yet supported in multi-repo queries[/yellow]"
        )

    from .remote.query_execution import (
        _load_remote_configuration,
        _get_decrypted_credentials,
    )
    from .api_clients.remote_query_client import RemoteQueryClient

    # Load remote configuration
    remote_config = _load_remote_configuration(project_root)
    server_url = remote_config["server_url"]

    # Get credentials
    credentials = _get_decrypted_credentials(project_root)

    # Execute multi-repo query
    async with RemoteQueryClient(
        server_url=server_url, credentials=credentials
    ) as query_client:
        # Build request parameters
        query_params = {
            "query": query_text,
            "limit": limit,
        }

        if languages:
            query_params["language"] = list(languages)
        if exclude_languages:
            query_params["exclude_language"] = list(exclude_languages)
        if path_filter:
            query_params["path_filter"] = list(path_filter)
        if exclude_paths:
            query_params["exclude_path"] = list(exclude_paths)
        if min_score is not None:
            query_params["min_score"] = min_score
        if accuracy:
            query_params["accuracy"] = accuracy

        # Call execute_multi_repo_query method
        results: dict = await query_client.execute_multi_repo_query(
            repositories=repos, **query_params
        )

        return results


def format_single_multi_repo_result(
    result: Dict[str, Any], index: int, quiet: bool, console: Console
) -> None:
    """Format and display a single multi-repo search result.

    Args:
        result: Result dictionary with score, file_path, content, etc.
        index: Result index number
        quiet: Whether to use quiet output mode
        console: Rich console for output
    """
    score = result.get("score", 0.0)
    file_path = result.get("file_path", "unknown")
    line_start = result.get("line_start", 0)
    line_end = result.get("line_end", 0)
    content = result.get("content", "")

    # Format file location
    if line_start and line_end:
        file_location = f"{file_path}:{line_start}-{line_end}"
    elif line_start:
        file_location = f"{file_path}:{line_start}"
    else:
        file_location = file_path

    if quiet:
        # Minimal output
        console.print(f"{index}. {score:.3f} {file_location}")
        if content:
            console.print(content, markup=False)
    else:
        # Full output
        console.print(f"[magenta]{index}.[/magenta] Score: {score:.3f}")
        console.print(f"File: [green]{file_location}[/green]")

        if content:
            console.print("Content:")
            console.print("-" * 40)
            console.print(content, markup=False)
            console.print("-" * 40)


def display_multi_repo_results(results: dict, quiet: bool, console: Console) -> None:
    """Display multi-repository query results with repository attribution.

    Args:
        results: Dictionary with 'results' key containing per-repo results
        quiet: Whether to use quiet output mode
        console: Rich console for output
    """
    if not results or "results" not in results:
        console.print(
            "[yellow]No results returned from multi-repository query[/yellow]"
        )
        return

    repo_results = results["results"]

    # Display any errors for repositories that failed (before early return)
    if "errors" in results and results["errors"]:
        if not quiet:
            console.print("\n[yellow]Partial Failures:[/yellow]")
        else:
            console.print("\n=== Errors ===")
        for repo_id, error_msg in results["errors"].items():
            if quiet:
                console.print(f"  {repo_id}: {error_msg}")
            else:
                console.print(f"  [red]{repo_id}:[/red] {error_msg}")

    if not repo_results:
        console.print("[yellow]No matching results found in any repository[/yellow]")
        return

    # Display results grouped by repository
    total_results = sum(len(repo_res) for repo_res in repo_results.values())

    if not quiet:
        console.print("\n[bold]Multi-Repository Search Results[/bold]")
        console.print(
            f"Searched {len(repo_results)} repositories, found {total_results} total results\n"
        )

    for repo_alias, repo_res in repo_results.items():
        if not repo_res:
            if not quiet:
                console.print(
                    f"\n=== Repository: [cyan]{repo_alias}[/cyan] (0 results) ===\n"
                )
            continue

        # Repository header
        if quiet:
            console.print(f"\n=== {repo_alias} ({len(repo_res)} results) ===")
        else:
            console.print(
                f"\n=== Repository: [bold cyan]{repo_alias}[/bold cyan] ({len(repo_res)} results) ===\n"
            )

        # Display each result using helper function
        for i, result in enumerate(repo_res, 1):
            format_single_multi_repo_result(result, i, quiet, console)

    if not quiet:
        console.print(
            f"\n[dim]Total: {total_results} results across {len(repo_results)} repositories[/dim]"
        )
