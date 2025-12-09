"""SCIP CLI commands for code-indexer."""

import sys
import click
from typing import Optional
from pathlib import Path
from datetime import datetime
from rich.console import Console

from .disabled_commands import require_mode

console = Console()


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
@click.pass_context
def scip_generate(ctx, project: Optional[str]):
    """Generate SCIP indexes for all discovered projects.

    Automatically discovers buildable projects (Java/Maven, TypeScript/npm,
    Python/Poetry, etc.) and generates SCIP indexes for precise code navigation.

    SCIP indexes enable:
      • Precise go-to-definition
      • Find all references
      • Cross-repository navigation
      • Symbol documentation

    EXAMPLES:
      cidx scip generate                    # Generate for all projects
      cidx scip generate --project backend  # Generate only for backend/

    STORAGE:
      SCIP indexes stored in: .code-indexer/scip/
      Status file: .code-indexer/scip/status.json
    """
    from code_indexer.scip.generator import SCIPGenerator
    from code_indexer.scip.status import StatusTracker, GenerationStatus, ProjectStatus, OverallStatus

    repo_root = Path.cwd()
    console.print(f"🔍 Discovering projects in {repo_root}", style="cyan")

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
                status=OverallStatus.SUCCESS if pr.indexer_result.is_success() else OverallStatus.FAILED,
                language=pr.project.language,
                build_system=pr.project.build_system,
                timestamp=datetime.now().isoformat(),
                duration_seconds=pr.indexer_result.duration_seconds,
                output_file=str(pr.indexer_result.output_file) if pr.indexer_result.output_file else None,
                error_message=pr.indexer_result.stderr if pr.indexer_result.stderr else None,
                exit_code=pr.indexer_result.exit_code,
                stdout=pr.indexer_result.stdout,
                stderr=pr.indexer_result.stderr,
            )

        status = GenerationStatus(
            overall_status=overall,
            total_projects=result.total_projects,
            successful_projects=result.successful_projects,
            failed_projects=result.failed_projects,
            projects=project_statuses
        )
        tracker.save(status)

        # Report results
        console.print()
        if result.total_projects == 0:
            console.print("ℹ️  No buildable projects discovered", style="yellow")
        elif result.is_complete_success():
            console.print(f"✅ Successfully generated SCIP for {result.successful_projects} project(s)", style="green bold")
        elif result.is_partial_success():
            console.print(f"⚠️  Partial success: {result.successful_projects} succeeded, {result.failed_projects} failed", style="yellow bold")
        else:
            console.print(f"❌ Generation failed for all {result.failed_projects} project(s)", style="red bold")

        console.print(f"   Duration: {result.duration_seconds:.1f}s", style="dim")
        console.print("   Status: .code-indexer/scip/status.json", style="dim")

        # Exit with appropriate code
        if result.is_complete_success() or result.is_partial_success():
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        console.print(f"❌ Error during SCIP generation: {e}", style="red")
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
            console.print("\nRun 'cidx scip generate' to create SCIP indexes", style="dim")
            sys.exit(0)

        # Status indicator
        if status.overall_status == OverallStatus.SUCCESS:
            console.print("Status: SUCCESS ✅", style="green bold")
        elif status.overall_status == OverallStatus.LIMBO:
            console.print("Status: LIMBO (partial success) ⚠️", style="yellow bold")
        elif status.overall_status == OverallStatus.FAILED:
            console.print("Status: FAILED ❌", style="red bold")

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
                    console.print(f"  Build: {project_status.build_system}", style="dim")
                    if project_status.duration_seconds:
                        console.print(f"  Duration: {project_status.duration_seconds:.1f}s", style="dim")
                    if project_status.output_file:
                        console.print(f"  Output: {project_status.output_file}", style="dim")
                else:
                    console.print(f"✗ {project_path}", style="red")
                    console.print(f"  Language: {project_status.language}", style="dim")
                    console.print(f"  Build: {project_status.build_system}", style="dim")
                    if project_status.error_message:
                        console.print(f"  Error: {project_status.error_message[:200]}", style="red dim")
                    if project_status.exit_code:
                        console.print(f"  Exit code: {project_status.exit_code}", style="red dim")
                console.print()

        sys.exit(0)

    except Exception as e:
        console.print(f"❌ Error reading SCIP status: {e}", style="red")
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
        console.print("❌ Error: Must specify project paths or use --failed flag", style="red")
        sys.exit(1)

    if projects and failed:
        console.print("❌ Error: Cannot use both project paths and --failed flag", style="red")
        sys.exit(1)

    try:
        generator = SCIPGenerator(repo_root)
        tracker = StatusTracker(generator.scip_dir)

        # Check if status exists
        current_status = tracker.load()
        if not current_status.projects:
            console.print("❌ Error: No SCIP generation status found", style="red")
            console.print("   Run 'cidx scip generate' first to discover projects", style="dim")
            sys.exit(1)

        # Progress callback
        def progress_callback(discovered_project, status_msg):
            console.print(f"   {status_msg}", style="dim")

        # Determine what to rebuild
        if failed:
            failed_count = current_status.failed_projects
            if failed_count == 0:
                console.print("ℹ️  No failed projects to rebuild", style="yellow")
                console.print(f"   All {current_status.successful_projects} projects are in success state", style="dim")
                sys.exit(0)

            console.print(f"🔄 Rebuilding {failed_count} failed project(s)...", style="cyan")
        else:
            console.print(f"🔄 Rebuilding {len(projects)} project(s)...", style="cyan")

        # Validate project paths
        project_list = list(projects)
        for proj in project_list:
            if proj not in current_status.projects:
                console.print(f"❌ Error: Unknown project path '{proj}'", style="red")
                console.print("   Available projects:", style="dim")
                for available_proj in sorted(current_status.projects.keys()):
                    console.print(f"     • {available_proj}", style="dim")
                console.print("   Run 'cidx scip status' to see all discovered projects", style="dim")
                sys.exit(1)

        # Run rebuild
        rebuild_result = generator.rebuild_projects(
            project_paths=project_list,
            force=force,
            failed_only=failed,
            progress_callback=progress_callback
        )

        # Report results
        console.print()
        if not rebuild_result:
            console.print("ℹ️  No projects rebuilt (all specified projects already succeeded)", style="yellow")
            console.print("   Use --force to rebuild successful projects", style="dim")
            sys.exit(0)

        successful = sum(1 for s in rebuild_result.values() if s.status.value == "success")
        failed_count = sum(1 for s in rebuild_result.values() if s.status.value == "failed")

        if failed_count == 0:
            console.print(f"✅ Successfully rebuilt {successful} project(s)", style="green bold")
        else:
            console.print(f"⚠️  Partial success: {successful} succeeded, {failed_count} failed", style="yellow bold")

        console.print("   Status: .code-indexer/scip/status.json", style="dim")

        # Exit with appropriate code
        sys.exit(0 if failed_count == 0 else 1)

    except ValueError as e:
        console.print(f"❌ Error: {e}", style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Error during SCIP rebuild: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="red dim")
        sys.exit(1)
