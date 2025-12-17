"""SCIP CLI commands for code-indexer."""

import sys
import click
from typing import Optional
from pathlib import Path
from datetime import datetime
from rich.console import Console

from .disabled_commands import require_mode

console = Console()
error_console = Console(stderr=True)


def _extract_short_symbol_name(full_symbol: str) -> str:
    """Extract readable symbol name from full SCIP identifier for find_definition.

    Strips SCIP-specific suffix markers since find_definition expects base names.

    Examples:
        Input:  'scip-python python code-indexer <hash> `module`/ClassName#'
        Output: 'ClassName'

        Input:  '... `module`/ClassName#method().'
        Output: 'ClassName#method'
    """
    if "/" in full_symbol:
        # Extract everything after the last '/'
        short = full_symbol.split("/")[-1]
        # Strip SCIP suffix markers for find_definition compatibility
        # Classes end with #, methods with (). or (), attributes with .
        short = short.rstrip("#").rstrip(".").rstrip(")")
        if short.endswith("("):
            short = short[:-1]
        return short
    return full_symbol


def _extract_display_name(full_symbol: str) -> str:
    """Extract display name with module path but without SCIP preamble.

    Example:
        Input:  'scip-python python code-indexer <hash> `module.path`/ClassName#method().'
        Output: 'module.path/ClassName#method()'
    """
    if "`" in full_symbol and "/" in full_symbol:
        # Extract from module path (backtick) to end
        # Format: ... `module.path`/ClassName#method().
        start = full_symbol.index("`")
        return full_symbol[start + 1 :].replace("`", "")
    return _extract_short_symbol_name(full_symbol)


@click.group("scip")
@click.pass_context
@require_mode("local")
def scip_group(ctx):
    """SCIP index generation and status commands.

    Generate SCIP (Source Code Intelligence Protocol) indexes for precise
    code navigation and cross-references. Supports Java, Kotlin, TypeScript,
    and Python projects.

    Available commands:
      generate       - Generate SCIP indexes for discovered projects
      status         - Show SCIP generation status
    """
    pass


@scip_group.command("generate")
@click.option(
    "--project",
    help="Generate SCIP only for specific project path (relative to repo root)",
)
@click.option(
    "--skip-verify",
    is_flag=True,
    help="Skip automatic database verification after generation (for CI performance)",
)
@click.pass_context
def scip_generate(ctx, project: Optional[str], skip_verify: bool):
    """Generate SCIP indexes for all discovered projects.

    Automatically discovers buildable projects (Java/Maven, TypeScript/npm,
    Python/Poetry, etc.) and generates SCIP indexes for precise code navigation.

    SCIP indexes enable:
      • Precise go-to-definition
      • Find all references
      • Cross-repository navigation
      • Symbol documentation

    By default, runs automatic verification after generation to ensure database integrity.

    EXAMPLES:
      cidx scip generate                    # Generate for all projects with verification
      cidx scip generate --project backend  # Generate only for backend/
      cidx scip generate --skip-verify      # Skip verification for CI performance

    STORAGE:
      SCIP indexes stored in: .code-indexer/scip/
      Status file: .code-indexer/scip/status.json
    """
    from code_indexer.scip.generator import SCIPGenerator
    from code_indexer.scip.status import (
        StatusTracker,
        GenerationStatus,
        ProjectStatus,
        OverallStatus,
    )

    repo_root = Path.cwd()
    console.print(f"Discovering projects in {repo_root}", style="cyan")

    try:
        generator = SCIPGenerator(repo_root)

        # Progress callback
        def progress_callback(discovered_project, status_msg):
            console.print(f"   {status_msg}", style="dim")

        # Run generation
        result = generator.generate(progress_callback=progress_callback)

        # Save status
        tracker = StatusTracker(generator.scip_dir)

        # Determine overall status
        if result.is_complete_success():
            overall = OverallStatus.SUCCESS
        elif result.is_partial_success():
            overall = OverallStatus.LIMBO
        elif result.is_complete_failure():
            overall = OverallStatus.FAILED
        else:
            overall = OverallStatus.PENDING

        # Build project statuses
        project_statuses = {}
        for pr in result.project_results:
            project_key = str(pr.project.relative_path)
            project_statuses[project_key] = ProjectStatus(
                status=(
                    OverallStatus.SUCCESS
                    if pr.indexer_result.is_success()
                    else OverallStatus.FAILED
                ),
                language=pr.project.language,
                build_system=pr.project.build_system,
                timestamp=datetime.now().isoformat(),
                duration_seconds=pr.indexer_result.duration_seconds,
                output_file=(
                    str(pr.indexer_result.output_file)
                    if pr.indexer_result.output_file
                    else None
                ),
                error_message=(
                    pr.indexer_result.stderr if pr.indexer_result.stderr else None
                ),
                exit_code=pr.indexer_result.exit_code,
                stdout=pr.indexer_result.stdout,
                stderr=pr.indexer_result.stderr,
            )

        status = GenerationStatus(
            overall_status=overall,
            total_projects=result.total_projects,
            successful_projects=result.successful_projects,
            failed_projects=result.failed_projects,
            projects=project_statuses,
        )
        tracker.save(status)

        # Report results
        console.print()
        if result.total_projects == 0:
            console.print("No buildable projects discovered", style="yellow")
        elif result.is_complete_success():
            console.print(
                f"Successfully generated SCIP for {result.successful_projects} project(s)",
                style="green bold",
            )
        elif result.is_partial_success():
            console.print(
                f"Partial success: {result.successful_projects} succeeded, {result.failed_projects} failed",
                style="yellow bold",
            )
        else:
            console.print(
                f"Generation failed for all {result.failed_projects} project(s)",
                style="red bold",
            )

        console.print(f"   Duration: {result.duration_seconds:.1f}s", style="dim")
        console.print("   Status: .code-indexer/scip/status.json", style="dim")

        # Run verification for successful projects (unless skipped)
        verification_failed = False
        if not skip_verify and result.successful_projects > 0:
            console.print()
            console.print("Running database verification...", style="cyan")

            for pr in result.project_results:
                if pr.indexer_result.is_success() and pr.indexer_result.output_file:
                    scip_file = Path(pr.indexer_result.output_file)
                    db_file = scip_file.with_suffix(scip_file.suffix + ".db")

                    if db_file.exists():
                        console.print(
                            f"  Verifying {pr.project.relative_path}...", style="dim"
                        )
                        try:
                            from code_indexer.scip.database.verify import (
                                SCIPDatabaseVerifier,
                            )

                            verifier = SCIPDatabaseVerifier(db_file, scip_file)
                            verify_result = verifier.verify()

                            if not verify_result.passed:
                                error_console.print(
                                    f"    ✗ Verification FAILED: {verify_result.total_errors} error(s)",
                                    style="red",
                                )
                                for error in verify_result.errors[
                                    :3
                                ]:  # Show first 3 errors
                                    error_console.print(f"      - {error}", style="red dim")
                                if verify_result.total_errors > 3:
                                    error_console.print(
                                        f"      ... and {verify_result.total_errors - 3} more errors",
                                        style="red dim",
                                    )
                                verification_failed = True
                            else:
                                console.print(
                                    "    ✓ Verification passed", style="green dim"
                                )
                                # Cleanup: Delete .scip file after successful verification
                                # .scip file is only needed for ETL, not for queries
                                if scip_file.exists():
                                    scip_file.unlink()
                                    console.print(
                                        "    ✓ Cleaned up source .scip file", style="dim"
                                    )
                        except Exception as e:
                            error_console.print(f"    ✗ Verification error: {e}", style="red")
                            verification_failed = True

        # Fail if verification failed
        if verification_failed:
            error_console.print()
            error_console.print(
                "Generation failed due to verification errors", style="red bold"
            )
            sys.exit(1)

        # Exit with appropriate code
        if result.is_complete_success() or result.is_partial_success():
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        console.print(f"Error during SCIP generation: {e}", style="red")
        import traceback

        console.print(traceback.format_exc(), style="red dim")
        sys.exit(1)


@scip_group.command("status")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed per-project status including errors",
)
@click.pass_context
def scip_status(ctx, verbose: bool):
    """Show SCIP generation status.

    Displays the current state of SCIP index generation, including
    overall status and per-project results.

    STATUS STATES:
      SUCCESS - All projects successfully generated
      LIMBO   - Some succeeded, some failed (partial success)
      FAILED  - All projects failed to generate
      PENDING - No generation attempted yet

    EXAMPLES:
      cidx scip status           # Show summary
      cidx scip status -v        # Show detailed per-project status
    """
    from code_indexer.scip.status import StatusTracker, OverallStatus

    repo_root = Path.cwd()
    scip_dir = repo_root / ".code-indexer" / "scip"
    tracker = StatusTracker(scip_dir)

    try:
        status = tracker.load()

        # Display overall status
        console.print("\n=== SCIP Generation Status ===\n", style="bold")

        if status.overall_status == OverallStatus.PENDING:
            console.print("Status: PENDING (no generation attempted)", style="yellow")
            console.print(
                "\nRun 'cidx scip generate' to create SCIP indexes", style="dim"
            )
            sys.exit(0)

        # Status indicator
        if status.overall_status == OverallStatus.SUCCESS:
            console.print("Status: SUCCESS", style="green bold")
        elif status.overall_status == OverallStatus.LIMBO:
            console.print("Status: LIMBO (partial success)", style="yellow bold")
        elif status.overall_status == OverallStatus.FAILED:
            console.print("Status: FAILED", style="red bold")

        # Summary
        console.print(f"\nTotal projects: {status.total_projects}", style="cyan")
        console.print(f"Successful: {status.successful_projects}", style="green")
        if status.failed_projects > 0:
            console.print(f"Failed: {status.failed_projects}", style="red")

        # Per-project details
        if verbose and status.projects:
            console.print("\n=== Project Details ===\n", style="bold")
            for project_path, project_status in status.projects.items():
                if project_status.status == OverallStatus.SUCCESS:
                    console.print(f"✓ {project_path}", style="green")
                    console.print(f"  Language: {project_status.language}", style="dim")
                    console.print(
                        f"  Build: {project_status.build_system}", style="dim"
                    )
                    if project_status.duration_seconds:
                        console.print(
                            f"  Duration: {project_status.duration_seconds:.1f}s",
                            style="dim",
                        )
                    if project_status.output_file:
                        console.print(
                            f"  Output: {project_status.output_file}", style="dim"
                        )
                else:
                    console.print(f"✗ {project_path}", style="red")
                    console.print(f"  Language: {project_status.language}", style="dim")
                    console.print(
                        f"  Build: {project_status.build_system}", style="dim"
                    )
                    if project_status.error_message:
                        console.print(
                            f"  Error: {project_status.error_message[:200]}",
                            style="red dim",
                        )
                    if project_status.exit_code:
                        console.print(
                            f"  Exit code: {project_status.exit_code}", style="red dim"
                        )
                console.print()

        sys.exit(0)

    except Exception as e:
        console.print(f"Error reading SCIP status: {e}", style="red")
        sys.exit(1)


@scip_group.command("rebuild")
@click.argument("projects", nargs=-1, type=str)
@click.option(
    "--failed",
    is_flag=True,
    help="Rebuild all previously failed projects",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force rebuild even if project already succeeded",
)
@click.pass_context
def scip_rebuild(ctx, projects: tuple, failed: bool, force: bool):
    """Rebuild SCIP indexes for specific projects.

    Allows targeted regeneration of SCIP indexes without re-running generation
    for all projects. Useful for:
      • Retrying failed projects after fixing issues
      • Updating specific project indexes after code changes
      • Recovering from partial generation failures

    EXAMPLES:
      cidx scip rebuild backend/                 # Rebuild single project
      cidx scip rebuild backend/ frontend/       # Rebuild multiple projects
      cidx scip rebuild --failed                 # Rebuild all failed projects
      cidx scip rebuild --force frontend/        # Force rebuild successful project

    NOTES:
      • Projects must have been previously discovered by 'cidx scip generate'
      • By default, successful projects are skipped (use --force to override)
      • Status file (.code-indexer/scip/status.json) is updated after rebuild
    """
    from code_indexer.scip.generator import SCIPGenerator
    from code_indexer.scip.status import StatusTracker

    repo_root = Path.cwd()

    # Validation
    if not projects and not failed:
        console.print(
            "Error: Must specify project paths or use --failed flag", style="red"
        )
        sys.exit(1)

    if projects and failed:
        console.print(
            "Error: Cannot use both project paths and --failed flag", style="red"
        )
        sys.exit(1)

    try:
        generator = SCIPGenerator(repo_root)
        tracker = StatusTracker(generator.scip_dir)

        # Check if status exists
        current_status = tracker.load()
        if not current_status.projects:
            console.print("Error: No SCIP generation status found", style="red")
            console.print(
                "   Run 'cidx scip generate' first to discover projects", style="dim"
            )
            sys.exit(1)

        # Progress callback
        def progress_callback(discovered_project, status_msg):
            console.print(f"   {status_msg}", style="dim")

        # Determine what to rebuild
        if failed:
            failed_count = current_status.failed_projects
            if failed_count == 0:
                console.print("No failed projects to rebuild", style="yellow")
                console.print(
                    f"   All {current_status.successful_projects} projects are in success state",
                    style="dim",
                )
                sys.exit(0)

            console.print(
                f"Rebuilding {failed_count} failed project(s)...", style="cyan"
            )
        else:
            console.print(f"Rebuilding {len(projects)} project(s)...", style="cyan")

        # Validate project paths
        project_list = list(projects)
        for proj in project_list:
            if proj not in current_status.projects:
                console.print(f"Error: Unknown project path '{proj}'", style="red")
                console.print("   Available projects:", style="dim")
                for available_proj in sorted(current_status.projects.keys()):
                    console.print(f"     • {available_proj}", style="dim")
                console.print(
                    "   Run 'cidx scip status' to see all discovered projects",
                    style="dim",
                )
                sys.exit(1)

        # Run rebuild
        rebuild_result = generator.rebuild_projects(
            project_paths=project_list,
            force=force,
            failed_only=failed,
            progress_callback=progress_callback,
        )

        # Report results
        console.print()
        if not rebuild_result:
            console.print(
                "No projects rebuilt (all specified projects already succeeded)",
                style="yellow",
            )
            console.print("   Use --force to rebuild successful projects", style="dim")
            sys.exit(0)

        successful = sum(
            1 for s in rebuild_result.values() if s.status.value == "success"
        )
        failed_count = sum(
            1 for s in rebuild_result.values() if s.status.value == "failed"
        )

        if failed_count == 0:
            console.print(
                f"Successfully rebuilt {successful} project(s)", style="green bold"
            )
        else:
            console.print(
                f"Partial success: {successful} succeeded, {failed_count} failed",
                style="yellow bold",
            )

        console.print("   Status: .code-indexer/scip/status.json", style="dim")

        # Exit with appropriate code
        sys.exit(0 if failed_count == 0 else 1)

    except ValueError as e:
        console.print(f"Error: {e}", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"Error during SCIP rebuild: {e}", style="red")
        import traceback

        console.print(traceback.format_exc(), style="red dim")
        sys.exit(1)


@scip_group.command("verify")
@click.argument("database_path", type=click.Path(exists=True))
@click.pass_context
def scip_verify(ctx, database_path: str):
    """Verify SCIP database integrity against source protobuf.

    Runs comprehensive verification checks to ensure database contents
    match the source .scip protobuf file with 100% accuracy.

    Verification checks:
      • Symbol count and content (100 random samples)
      • Occurrence count and content (1000 random samples)
      • Document paths and languages (100% verification)
      • Call graph FK integrity (100% + 100 random edge samples)

    EXAMPLES:
      cidx scip verify .code-indexer/scip/index.scip.db
      cidx scip verify path/to/project.scip.db

    EXIT CODES:
      0 - All verification checks passed
      1 - One or more verification checks failed
    """
    from code_indexer.scip.database.verify import SCIPDatabaseVerifier
    from pathlib import Path

    db_path = Path(database_path)

    # Find corresponding .scip file (remove .db extension)
    if db_path.suffix == ".db":
        scip_file = db_path.with_suffix("")
    else:
        console.print("Error: Database path must end with .db extension", style="red")
        sys.exit(1)

    if not scip_file.exists():
        console.print(
            f"Error: Corresponding SCIP file not found: {scip_file}", style="red"
        )
        sys.exit(1)

    console.print(f"Verifying database: {db_path}", style="cyan")
    console.print(f"Against source: {scip_file}", style="cyan")
    console.print()

    try:
        # Run verification
        verifier = SCIPDatabaseVerifier(db_path, scip_file)
        result = verifier.verify()

        # Display results
        if result.passed:
            console.print("Verification PASSED", style="green bold")
            console.print()
            console.print("All checks passed:", style="green")
            console.print(
                f"  ✓ Symbol count match: {result.symbol_count_match}", style="green"
            )
            console.print(
                f"  ✓ Symbol sample verified: {result.symbols_sampled} samples",
                style="green",
            )
            console.print(
                f"  ✓ Occurrence count match: {result.occurrence_count_match}",
                style="green",
            )
            console.print(
                f"  ✓ Occurrence sample verified: {result.occurrences_sampled} samples",
                style="green",
            )
            console.print(
                f"  ✓ Documents verified: {result.documents_verified}", style="green"
            )
            console.print(
                f"  ✓ Call graph FK integrity: {result.call_graph_fk_valid}",
                style="green",
            )
            console.print(
                f"  ✓ Call graph sample verified: {result.call_graph_edges_sampled} edges",
                style="green",
            )
            sys.exit(0)
        else:
            console.print("Verification FAILED", style="red bold")
            console.print()
            console.print(f"Total errors: {result.total_errors}", style="red")
            console.print()
            console.print("Errors:", style="red bold")
            for i, error in enumerate(result.errors, 1):
                console.print(f"  {i}. {error}", style="red")
            console.print()
            console.print("Verification summary:", style="yellow")
            console.print(
                f"  Symbol count match: {result.symbol_count_match}", style="yellow"
            )
            console.print(
                f"  Occurrence count match: {result.occurrence_count_match}",
                style="yellow",
            )
            console.print(
                f"  Documents verified: {result.documents_verified}", style="yellow"
            )
            console.print(
                f"  Call graph FK valid: {result.call_graph_fk_valid}", style="yellow"
            )
            sys.exit(1)

    except Exception as e:
        console.print(f"Error during verification: {e}", style="red")
        import traceback

        console.print(traceback.format_exc(), style="red dim")
        sys.exit(1)


@scip_group.command("definition")
@click.argument("symbol", type=str)
@click.option(
    "--limit",
    type=int,
    default=0,
    help="Maximum results (0 = unlimited)",
)
@click.option(
    "--exact",
    is_flag=True,
    help="Match exact symbol name (no substring matching)",
)
@click.option(
    "--project",
    help="Limit search to specific project path",
)
@click.pass_context
def scip_definition(ctx, symbol: str, limit: int, exact: bool, project: Optional[str]):
    """Find where a symbol is defined.

    Searches SCIP indexes for symbol definitions and returns file locations.
    Uses substring matching by default (e.g., "UserService" matches class and methods).
    Use --exact for precise symbol matching.

    EXAMPLES:
      cidx scip definition UserService            # Find UserService definitions
      cidx scip definition authenticate           # Find authenticate method
      cidx scip definition UserService --exact    # Exact match only

    REQUIRES:
      SCIP indexes must be generated first (run 'cidx scip generate')
    """
    from code_indexer.scip.query import SCIPQueryEngine
    from code_indexer.scip.status import StatusTracker

    repo_root = Path.cwd()
    scip_dir = repo_root / ".code-indexer" / "scip"

    # Check if SCIP indexes exist
    tracker = StatusTracker(scip_dir)
    status = tracker.load()

    if not status.projects:
        console.print("Error: No SCIP indexes found", style="red")
        console.print("   Run 'cidx scip generate' first", style="dim")
        sys.exit(1)

    # Find all .scip files (filter by project if specified)
    if project:
        # Filter to specific project path
        project_scip_dir = scip_dir / project
        scip_files = list(project_scip_dir.glob("**/*.scip"))
    else:
        # Search all projects
        scip_files = list(scip_dir.glob("**/*.scip"))

    if not scip_files:
        if project:
            console.print(
                f"Error: No .scip files found for project '{project}'", style="red"
            )
        else:
            console.print("Error: No .scip files found", style="red")
        sys.exit(1)

    # Search across all SCIP files
    all_results = []
    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            results = engine.find_definition(symbol, exact=exact)
            all_results.extend(results)
        except Exception as e:
            console.print(
                f"Warning: Failed to query {scip_file}: {e}", style="yellow dim"
            )

    # Apply limit if specified
    if limit > 0:
        all_results = all_results[:limit]

    # Display results
    if not all_results:
        console.print(f"No definitions found for '{symbol}'", style="yellow")
        sys.exit(0)

    console.print(
        f"Found {len(all_results)} definition(s) for '{symbol}':\n", style="green bold"
    )

    for result in all_results:
        display_name = _extract_display_name(result.symbol)
        console.print(
            f"  {display_name} ({result.file_path}:{result.line}:{result.column})",
            style="cyan",
        )

    sys.exit(0)


@scip_group.command("references")
@click.argument("symbol", type=str)
@click.option(
    "--limit",
    type=int,
    default=0,
    help="Maximum results (0 = unlimited)",
)
@click.option(
    "--exact",
    is_flag=True,
    help="Match exact symbol name (no substring matching)",
)
@click.option(
    "--project",
    help="Limit search to specific project path",
)
@click.pass_context
def scip_references(ctx, symbol: str, limit: int, exact: bool, project: Optional[str]):
    """Find all references to a symbol.

    Searches SCIP indexes for symbol usages and returns file locations.
    Results are sorted by file path.

    EXAMPLES:
      cidx scip references UserService              # Find all UserService usages
      cidx scip references authenticate --limit 10  # Limit to 10 results
      cidx scip references UserService --exact      # Exact match only

    REQUIRES:
      SCIP indexes must be generated first (run 'cidx scip generate')
    """
    from code_indexer.scip.query import SCIPQueryEngine
    from code_indexer.scip.status import StatusTracker

    repo_root = Path.cwd()
    scip_dir = repo_root / ".code-indexer" / "scip"

    # Check if SCIP indexes exist
    tracker = StatusTracker(scip_dir)
    status = tracker.load()

    if not status.projects:
        console.print("Error: No SCIP indexes found", style="red")
        console.print("   Run 'cidx scip generate' first", style="dim")
        sys.exit(1)

    # Find all .scip files (filter by project if specified)
    if project:
        # Filter to specific project path
        project_scip_dir = scip_dir / project
        scip_files = list(project_scip_dir.glob("**/*.scip"))
    else:
        # Search all projects
        scip_files = list(scip_dir.glob("**/*.scip"))

    if not scip_files:
        if project:
            console.print(
                f"Error: No .scip files found for project '{project}'", style="red"
            )
        else:
            console.print("Error: No .scip files found", style="red")
        sys.exit(1)

    # Search across all SCIP files
    all_results = []
    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            results = engine.find_references(symbol, limit=limit, exact=exact)
            all_results.extend(results)
            if limit > 0 and len(all_results) >= limit:
                break
        except Exception as e:
            console.print(
                f"Warning: Failed to query {scip_file}: {e}", style="yellow dim"
            )

    # Trim to limit if specified
    if limit > 0:
        all_results = all_results[:limit]

    # Display results
    if not all_results:
        console.print(f"No references found for '{symbol}'", style="yellow")
        sys.exit(0)

    console.print(
        f"Found {len(all_results)} reference(s) to '{symbol}':\n", style="green bold"
    )

    for result in all_results:
        display_name = _extract_display_name(result.symbol)
        console.print(
            f"  {display_name} ({result.file_path}:{result.line})",
            style="cyan",
            markup=False,
            highlight=False,
        )

    sys.exit(0)


@scip_group.command("dependencies")
@click.argument("symbol", type=str)
@click.option(
    "--limit",
    type=int,
    default=0,
    help="Maximum results (0 = unlimited)",
)
@click.option(
    "--depth",
    type=int,
    default=1,
    help="Depth of transitive dependencies (default: 1 = direct only)",
)
@click.option(
    "--exact",
    is_flag=True,
    help="Match exact symbol name (no substring matching)",
)
@click.option(
    "--project",
    help="Limit search to specific project path",
)
@click.pass_context
def scip_dependencies(
    ctx, symbol: str, limit: int, depth: int, exact: bool, project: Optional[str]
):
    """Get symbols that this symbol depends on.

    Analyzes a symbol's definition to find all symbols it references or depends on.
    Useful for understanding what a symbol uses and impact analysis.

    EXAMPLES:
      cidx scip dependencies UserService              # Direct dependencies only
      cidx scip dependencies UserService --depth 2    # Include transitive deps
      cidx scip dependencies authenticate --exact     # Exact symbol match

    REQUIRES:
      SCIP indexes must be generated first (run 'cidx scip generate')
    """
    from code_indexer.scip.query import SCIPQueryEngine
    from code_indexer.scip.status import StatusTracker

    repo_root = Path.cwd()
    scip_dir = repo_root / ".code-indexer" / "scip"

    # Check if SCIP indexes exist
    tracker = StatusTracker(scip_dir)
    status = tracker.load()

    if not status.projects:
        console.print("Error: No SCIP indexes found", style="red")
        console.print("   Run 'cidx scip generate' first", style="dim")
        sys.exit(1)

    # Find all .scip files (filter by project if specified)
    if project:
        # Filter to specific project path
        project_scip_dir = scip_dir / project
        scip_files = list(project_scip_dir.glob("**/*.scip"))
    else:
        # Search all projects
        scip_files = list(scip_dir.glob("**/*.scip"))

    if not scip_files:
        if project:
            console.print(
                f"Error: No .scip files found for project '{project}'", style="red"
            )
        else:
            console.print("Error: No .scip files found", style="red")
        sys.exit(1)

    # Search across all SCIP files
    all_results = []
    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            results = engine.get_dependencies(symbol, depth=depth, exact=exact)
            all_results.extend(results)
        except Exception as e:
            console.print(
                f"Warning: Failed to query {scip_file}: {e}", style="yellow dim"
            )

    # Apply limit if specified
    if limit > 0:
        all_results = all_results[:limit]

    # Display results
    if not all_results:
        console.print(f"No dependencies found for '{symbol}'", style="yellow")
        console.print(
            "   Symbol may be a leaf node with no outgoing dependencies", style="dim"
        )
        sys.exit(0)

    console.print(
        f"Found {len(all_results)} dependenc{'y' if len(all_results) == 1 else 'ies'} for '{symbol}':\n",
        style="green bold",
    )

    for result in all_results:
        display_name = _extract_display_name(result.symbol)
        console.print(
            f"  {display_name} ({result.file_path}:{result.line}) [{result.relationship}]",
            style="cyan",
            markup=False,
            highlight=False,
        )

    sys.exit(0)


@scip_group.command("dependents")
@click.argument("symbol", type=str)
@click.option(
    "--limit",
    type=int,
    default=0,
    help="Maximum results (0 = unlimited)",
)
@click.option(
    "--depth",
    type=int,
    default=1,
    help="Depth of transitive dependents (default: 1 = direct only)",
)
@click.option(
    "--exact",
    is_flag=True,
    help="Match exact symbol name (no substring matching)",
)
@click.option(
    "--project",
    help="Limit search to specific project path",
)
@click.pass_context
def scip_dependents(ctx, symbol: str, limit: int, depth: int, exact: bool, project: Optional[str]):
    """Get symbols that depend on this symbol.

    Finds all symbols that reference or use the target symbol.
    Useful for impact analysis and understanding what would be affected by changes.

    EXAMPLES:
      cidx scip dependents Logger                   # Direct dependents only
      cidx scip dependents Logger --depth 2         # Include transitive deps
      cidx scip dependents UserService --exact      # Exact symbol match

    REQUIRES:
      SCIP indexes must be generated first (run 'cidx scip generate')
    """
    from code_indexer.scip.query import SCIPQueryEngine
    from code_indexer.scip.status import StatusTracker

    repo_root = Path.cwd()
    scip_dir = repo_root / ".code-indexer" / "scip"

    # Check if SCIP indexes exist
    tracker = StatusTracker(scip_dir)
    status = tracker.load()

    if not status.projects:
        console.print("Error: No SCIP indexes found", style="red")
        console.print("   Run 'cidx scip generate' first", style="dim")
        sys.exit(1)

    # Find all .scip files (filter by project if specified)
    if project:
        # Filter to specific project path
        project_scip_dir = scip_dir / project
        scip_files = list(project_scip_dir.glob("**/*.scip"))
    else:
        # Search all projects
        scip_files = list(scip_dir.glob("**/*.scip"))

    if not scip_files:
        if project:
            console.print(
                f"Error: No .scip files found for project '{project}'", style="red"
            )
        else:
            console.print("Error: No .scip files found", style="red")
        sys.exit(1)

    # Search across all SCIP files
    all_results = []
    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            results = engine.get_dependents(symbol, depth=depth, exact=exact)
            all_results.extend(results)
        except Exception as e:
            console.print(
                f"Warning: Failed to query {scip_file}: {e}", style="yellow dim"
            )

    # Apply limit if specified
    if limit > 0:
        all_results = all_results[:limit]

    # Display results
    if not all_results:
        console.print(f"No dependents found for '{symbol}'", style="yellow")
        console.print(
            "   Symbol may be unused or at the top of the dependency graph", style="dim"
        )
        sys.exit(0)

    console.print(
        f"Found {len(all_results)} dependent(s) for '{symbol}':\n", style="green bold"
    )

    # Flat output: one line per result
    for result in all_results:
        display_name = _extract_display_name(result.symbol)
        # Format: display_name (file:line) [relationship]
        console.print(
            f"  {display_name} ({result.file_path}:{result.line}) [{result.relationship}]",
            style="dim",
            markup=False,
            highlight=False,
        )

    sys.exit(0)


@scip_group.command("impact")
@click.argument("symbol")
@click.option(
    "--limit",
    type=int,
    default=0,
    help="Maximum results (0 = unlimited)",
)
@click.option("--depth", default=3, help="Analysis depth (default 3, max 10)")
@click.option("--project", help="Filter to specific project path")
@click.option("--exclude", help="Exclude pattern (e.g., */tests/*)")
@click.option("--include", help="Include pattern")
@click.option("--kind", help="Filter by symbol kind (class/function/variable)")
@click.pass_context
def scip_impact(
    ctx,
    symbol: str,
    limit: int,
    depth: int,
    project: Optional[str],
    exclude: Optional[str],
    include: Optional[str],
    kind: Optional[str],
):
    """Analyze impact of changes to a symbol (shows what depends on it).

    Performs transitive analysis to find all code affected by changes to the
    target symbol, including direct dependents and indirect dependents up to
    the specified depth.

    EXAMPLES:
      cidx scip impact UserService                  # Full impact analysis
      cidx scip impact authenticate --depth 1       # Direct dependents only
      cidx scip impact Logger --exclude '*/tests/*' # Exclude test files
      cidx scip impact Config --project backend/    # Limit to backend project

    REQUIRES:
      SCIP indexes must be generated first (run 'cidx scip generate')
    """
    from code_indexer.scip.query.composites import analyze_impact
    from code_indexer.scip.status import StatusTracker

    repo_root = Path.cwd()
    scip_dir = repo_root / ".code-indexer" / "scip"

    # Check if SCIP indexes exist
    tracker = StatusTracker(scip_dir)
    status = tracker.load()

    if not status.projects:
        console.print("Error: No SCIP indexes found", style="red")
        console.print("   Run 'cidx scip generate' first", style="dim")
        sys.exit(1)

    # Run impact analysis
    console.print(f"Analyzing impact for '{symbol}' (depth={depth})...\n", style="blue")
    result = analyze_impact(
        symbol,
        scip_dir,
        depth=depth,
        project=project,
        exclude=exclude,
        include=include,
        kind=kind,
    )

    if result.total_affected == 0:
        console.print(f"No dependents found for '{symbol}'", style="yellow")
        console.print(
            "   Symbol may be unused or at the top of the dependency graph", style="dim"
        )
        sys.exit(0)

    # Apply limit if specified
    affected_symbols = result.affected_symbols
    if limit > 0:
        affected_symbols = affected_symbols[:limit]

    # Display results
    console.print(
        f"Found {result.total_affected} affected symbol(s) in {len(result.affected_files)} file(s):\n",
        style="green bold",
    )

    # Flat output: one line per affected symbol with depth indicator
    for sym in affected_symbols:
        display_name = _extract_display_name(sym.symbol)
        # Format: [depth N] display_name (file:line)
        console.print(
            f"  [depth {sym.depth}] {display_name} ({sym.file_path}:{sym.line})",
            style="dim",
            markup=False,
            highlight=False,
        )

    sys.exit(0)


@scip_group.command("callchain")
@click.argument("from_symbol")
@click.argument("to_symbol")
@click.option(
    "--max-depth", default=10, help="Maximum chain length (default 10, max 20)"
)
@click.option(
    "--limit", type=int, default=0, help="Maximum results (0 = unlimited)"
)
@click.option("--project", help="Filter to specific project path")
@click.pass_context
def scip_callchain(
    ctx,
    from_symbol: str,
    to_symbol: str,
    max_depth: int,
    limit: int,
    project: Optional[str],
):
    """Trace call chains between two symbols.

    Finds all execution paths from one symbol to another, showing the complete
    sequence of calls. Useful for understanding code flow and debugging.

    EXAMPLES:
      cidx scip callchain main Application.run     # Find paths from main to run
      cidx scip callchain Logger UserService       # Trace Logger to UserService
      cidx scip callchain A B --max-depth 5        # Limit to 5 hops max

    REQUIRES:
      SCIP indexes must be generated first (run 'cidx scip generate')
    """
    from code_indexer.scip.query.primitives import SCIPQueryEngine
    from code_indexer.scip.query.composites import (
        CallStep,
        CallChain as CompositeCallChain,
        CallChainResult,
    )
    from code_indexer.scip.status import StatusTracker

    repo_root = Path.cwd()
    scip_dir = repo_root / ".code-indexer" / "scip"

    # Check if SCIP indexes exist
    tracker = StatusTracker(scip_dir)
    status = tracker.load()

    if not status.projects:
        console.print("Error: No SCIP indexes found", style="red")
        console.print("   Run 'cidx scip generate' first", style="dim")
        sys.exit(1)

    # Find SCIP database file
    scip_files = list(scip_dir.glob("**/*.scip"))
    if not scip_files:
        console.print("Error: No SCIP files found", style="red")
        console.print("   Run 'cidx scip generate' first", style="dim")
        sys.exit(1)

    # Prioritize index.scip, otherwise use largest file to avoid test fixtures
    index_scip = scip_dir / "index.scip"
    if index_scip.exists():
        scip_file = index_scip
    else:
        # Use largest SCIP file (main codebase index, not test fixtures)
        scip_file = max(scip_files, key=lambda f: f.stat().st_size)

    engine = SCIPQueryEngine(scip_file)

    # Trace call chain using fast database primitive
    console.print(
        f"Tracing call chains from '{from_symbol}' to '{to_symbol}'...\n", style="blue"
    )

    # Find all matching definitions for from/to symbols (fuzzy matching)
    from_defs = engine.find_definition(from_symbol, exact=False)
    to_defs = engine.find_definition(to_symbol, exact=False)

    if not from_defs:
        console.print(f"Error: Symbol '{from_symbol}' not found", style="red")
        sys.exit(1)

    if not to_defs:
        console.print(f"Error: Symbol '{to_symbol}' not found", style="red")
        sys.exit(1)

    # Try all combinations of from/to symbols and merge results
    all_chains = []
    for from_def in from_defs:
        for to_def in to_defs:
            chains = engine.trace_call_chain(
                from_def.symbol, to_def.symbol, max_depth=max_depth
            )
            all_chains.extend(chains)

    # Deduplicate chains by path
    seen_paths = set()
    unique_chains = []
    for chain in all_chains:
        path_key = tuple(chain.path)
        if path_key not in seen_paths:
            seen_paths.add(path_key)
            unique_chains.append(chain)

    chains = sorted(unique_chains, key=lambda c: c.length)

    # Enrich chains with location details for display
    from typing import List as TypingList

    DEFAULT_CHAIN_LIMIT = 100
    enriched_chains: TypingList[CompositeCallChain] = []
    for chain in chains:
        steps = []
        for symbol_name in chain.path:
            # Extract short name for find_definition (expects short names like "ClassName")
            short_name = _extract_short_symbol_name(symbol_name)
            # Look up location for this symbol
            defs = engine.find_definition(short_name, exact=True)
            if defs:
                step = CallStep(
                    symbol=symbol_name,
                    file_path=Path(defs[0].file_path),
                    line=defs[0].line,
                    column=defs[0].column,
                    call_type="call",
                )
                steps.append(step)
            else:
                # Fallback: create step without location details
                step = CallStep(
                    symbol=symbol_name,
                    file_path=Path("unknown"),
                    line=0,
                    column=0,
                    call_type="call",
                )
                steps.append(step)

        enriched_chain = CompositeCallChain(path=steps, length=chain.length)
        enriched_chains.append(enriched_chain)

    # Create result structure matching composites format
    result = CallChainResult(
        from_symbol=from_symbol,
        to_symbol=to_symbol,
        chains=enriched_chains,
        total_chains_found=len(enriched_chains),
        truncated=len(enriched_chains) >= DEFAULT_CHAIN_LIMIT,
        max_depth_reached=any(c.length == max_depth for c in chains),
    )

    if result.total_chains_found == 0:
        console.print(
            f"No call chain found from '{from_symbol}' to '{to_symbol}'", style="yellow"
        )
        console.print(
            "   Symbols may not be connected or path exceeds max depth", style="dim"
        )
        sys.exit(0)

    # Display results
    console.print(
        f"Found {result.total_chains_found} call chain(s):\n", style="green bold"
    )

    display_chain: CompositeCallChain
    chains_to_show = min(limit, result.total_chains_found) if limit > 0 else result.total_chains_found
    for i, display_chain in enumerate(result.chains[:chains_to_show], 1):
        console.print(f"Chain {i} ({display_chain.length} step(s)):", style="cyan bold")
        display_step: CallStep
        for j, display_step in enumerate(display_chain.path, 1):
            # Extract clean display name (module.path/ClassName#method)
            display_name = _extract_display_name(display_step.symbol)
            console.print(
                f"  {j}. {display_name} ({display_step.file_path}:{display_step.line})",
                style="dim",
            )
        console.print()

    if result.total_chains_found > chains_to_show:
        console.print(
            f"... and {result.total_chains_found - chains_to_show} more chains",
            style="dim",
        )

    if result.truncated:
        console.print(
            f"Warning: Some paths truncated at max depth {max_depth}", style="yellow"
        )

    sys.exit(0)


@scip_group.command("context")
@click.argument("symbol")
@click.option("--limit", type=int, default=0, help="Maximum results (0 = unlimited)")
@click.option("--min-score", default=0.0, help="Minimum relevance score (0.0-1.0)")
@click.option("--project", help="Filter to specific project path")
@click.pass_context
def scip_context(
    ctx, symbol: str, limit: int, min_score: float, project: Optional[str]
):
    """Get smart context for a symbol - curated file list with relevance.

    Combines definition, references, and dependencies into a prioritized
    file list optimized for understanding the symbol. Perfect for AI agents.

    EXAMPLES:
      cidx scip context UserService              # Get context for UserService
      cidx scip context Logger --limit 10        # Limit to top 10 files
      cidx scip context Config --min-score 0.5   # Filter low relevance

    REQUIRES:
      SCIP indexes must be generated first (run 'cidx scip generate')
    """
    from code_indexer.scip.query.composites import get_smart_context
    from code_indexer.scip.status import StatusTracker

    repo_root = Path.cwd()
    scip_dir = repo_root / ".code-indexer" / "scip"

    # Check if SCIP indexes exist
    tracker = StatusTracker(scip_dir)
    status = tracker.load()

    if not status.projects:
        console.print("Error: No SCIP indexes found", style="red")
        console.print("   Run 'cidx scip generate' first", style="dim")
        sys.exit(1)

    # Get smart context
    console.print(f"Building smart context for '{symbol}'...\n", style="blue")
    result = get_smart_context(
        symbol, scip_dir, limit=limit, min_score=min_score, project=project
    )

    if result.total_files == 0:
        console.print(f"No context found for '{symbol}'", style="yellow")
        console.print(
            "   Symbol may not exist or filters are too restrictive", style="dim"
        )
        sys.exit(0)

    # Display summary
    console.print(
        f"Found {result.total_symbols} relevant symbol(s) in {result.total_files} file(s):\n",
        style="green bold",
    )

    # Flat output: one line per symbol with role indicator and score
    for cf in result.files:
        for sym in cf.symbols:
            symbol_attr = getattr(sym, "symbol", None)
            display_name = (
                _extract_display_name(symbol_attr)
                if symbol_attr
                else _extract_display_name(getattr(sym, "name", ""))
            )
            # Abbreviate role: definition -> def, reference -> ref
            # Check relationship first, but only use if it's a string (not a Mock)
            relationship = getattr(sym, "relationship", None)
            role = getattr(sym, "role", "")
            role_value = relationship if isinstance(relationship, str) else role
            role_abbrev = str(role_value)[:3]
            # Format: [role] display_name (file:line) - score: X.XX
            console.print(
                f"  [{role_abbrev}] {display_name} ({cf.path}:{sym.line}) - score: {cf.relevance_score:.2f}",
                style="dim",
                markup=False,
                highlight=False,
            )

    sys.exit(0)
