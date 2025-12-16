"""SCIP generation orchestration module."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Callable
import time
import logging

from .discovery import ProjectDiscovery, DiscoveredProject
from .indexers.base import IndexerResult, IndexerStatus
from .indexers.base import SCIPIndexer
from .indexers.java import JavaIndexer
from .indexers.typescript import TypeScriptIndexer
from .indexers.python import PythonIndexer
from .status import ProjectStatus
from .database.schema import DatabaseManager
from .database.builder import SCIPDatabaseBuilder

logger = logging.getLogger(__name__)


@dataclass
class ProjectGenerationResult:
    """Result of generating SCIP index for a single project."""

    project: DiscoveredProject
    indexer_result: IndexerResult


@dataclass
class GenerationResult:
    """Overall result of SCIP generation for all projects."""

    total_projects: int
    successful_projects: int
    failed_projects: int
    project_results: List[ProjectGenerationResult] = field(default_factory=list)
    duration_seconds: float = 0.0

    def is_complete_success(self) -> bool:
        """Check if all projects succeeded."""
        return self.total_projects > 0 and self.failed_projects == 0

    def is_partial_success(self) -> bool:
        """Check if some (but not all) projects succeeded."""
        return self.successful_projects > 0 and self.failed_projects > 0

    def is_complete_failure(self) -> bool:
        """Check if all projects failed."""
        return self.total_projects > 0 and self.successful_projects == 0


class SCIPGenerator:
    """Orchestrates SCIP index generation for multiple projects."""

    def __init__(self, repo_root: Path, max_workers: int = 4):
        """
        Initialize SCIP generator.

        Args:
            repo_root: Root directory of repository
            max_workers: Maximum number of parallel indexer executions
        """
        self.repo_root = Path(repo_root)
        self.scip_dir = self.repo_root / ".code-indexer" / "scip"
        self.max_workers = max_workers

        # Initialize indexers
        self._indexers: Dict[str, SCIPIndexer] = {
            "java": JavaIndexer(),
            "kotlin": JavaIndexer(),  # Kotlin uses scip-java
            "typescript": TypeScriptIndexer(),
            "python": PythonIndexer(),
        }

    def generate(
        self,
        progress_callback: Optional[Callable[[DiscoveredProject, str], None]] = None,
    ) -> GenerationResult:
        """
        Generate SCIP indexes for all discoverable projects.

        Args:
            progress_callback: Optional callback for progress reporting
                Called with (project, status_message)

        Returns:
            GenerationResult with summary of generation
        """
        start_time = time.time()

        # Discover projects
        discovery = ProjectDiscovery(self.repo_root)
        projects = discovery.discover()

        if not projects:
            return GenerationResult(
                total_projects=0,
                successful_projects=0,
                failed_projects=0,
                duration_seconds=time.time() - start_time,
            )

        # Generate indexes (sequential for now, parallel coming next)
        project_results = []
        successful = 0
        failed = 0

        for project in projects:
            if progress_callback:
                progress_callback(
                    project,
                    f"Generating SCIP for {project.relative_path} [{project.language}]...",
                )

            # Get appropriate indexer
            indexer = self._indexers.get(project.language)
            if not indexer:
                # Create failed result for unsupported language
                result = IndexerResult(
                    status=IndexerStatus.FAILED,
                    duration_seconds=0.0,
                    output_file=None,
                    stdout="",
                    stderr=f"No indexer available for language: {project.language}",
                    exit_code=-1,
                )
                project_results.append(ProjectGenerationResult(project, result))
                failed += 1
                continue

            # Generate index
            project_dir = self.repo_root / project.relative_path
            output_dir = self.scip_dir / project.relative_path

            indexer_result = indexer.generate(
                project_dir, output_dir, project.build_system
            )

            project_results.append(ProjectGenerationResult(project, indexer_result))

            if indexer_result.is_success():
                successful += 1
                if progress_callback:
                    progress_callback(
                        project,
                        f"✓ {project.relative_path} ({indexer_result.duration_seconds:.1f}s)",
                    )

                # Build database from protobuf - REQUIRED FOR SUCCESS
                if indexer_result.output_file:
                    try:
                        scip_file = indexer_result.output_file
                        db_manager = DatabaseManager(scip_file)
                        db_manager.create_schema()

                        builder = SCIPDatabaseBuilder()
                        builder.build(scip_file, db_manager.db_path)

                        db_manager.create_indexes()
                    except Exception as e:
                        # Database build is MANDATORY - failure means generation failed
                        # Per Anti-Fallback Foundation #2: graceful failure over forceful success
                        logger.error(
                            f"Database build failed for {project.relative_path}: {e}",
                            exc_info=True,
                        )
                        # Convert success to failure
                        successful -= 1
                        failed += 1
                        # Update result status
                        indexer_result.status = IndexerStatus.FAILED
                        indexer_result.stderr = f"Database build failed: {e}"
            else:
                failed += 1
                if progress_callback:
                    progress_callback(project, f"✗ {project.relative_path} (failed)")

        duration = time.time() - start_time

        return GenerationResult(
            total_projects=len(projects),
            successful_projects=successful,
            failed_projects=failed,
            project_results=project_results,
            duration_seconds=duration,
        )

    def rebuild_projects(
        self,
        project_paths: List[str],
        force: bool = False,
        failed_only: bool = False,
        progress_callback: Optional[Callable[[DiscoveredProject, str], None]] = None,
    ) -> Dict[str, ProjectStatus]:
        """
        Rebuild SCIP indexes for specific projects.

        Args:
            project_paths: List of project paths to rebuild
            force: Rebuild even if project already succeeded
            failed_only: Rebuild all failed projects (ignores project_paths)
            progress_callback: Optional callback for progress reporting

        Returns:
            Dict mapping project path to updated ProjectStatus
        """
        from .status import StatusTracker, ProjectStatus, OverallStatus
        from datetime import datetime

        # Load current status
        tracker = StatusTracker(self.scip_dir)
        current_status = tracker.load()

        # Determine which projects to rebuild
        if failed_only:
            projects_to_rebuild = [
                path
                for path, status in current_status.projects.items()
                if status.status == OverallStatus.FAILED
            ]
        else:
            projects_to_rebuild = project_paths

        # Validate projects exist in status
        results = {}
        for project_path in projects_to_rebuild:
            if project_path not in current_status.projects:
                raise ValueError(f"Unknown project path: {project_path}")

            project_status = current_status.projects[project_path]

            # Skip if already successful and not forcing
            if not force and project_status.status == OverallStatus.SUCCESS:
                continue

            # Get indexer for this project
            indexer = self._indexers.get(project_status.language)
            if not indexer:
                # No indexer available
                results[project_path] = ProjectStatus(
                    status=OverallStatus.FAILED,
                    language=project_status.language,
                    build_system=project_status.build_system,
                    timestamp=datetime.now().isoformat(),
                    error_message=f"No indexer available for language: {project_status.language}",
                    exit_code=-1,
                )
                continue

            # Progress reporting
            if progress_callback:
                project = DiscoveredProject(
                    relative_path=Path(project_path),
                    language=project_status.language,
                    build_system=project_status.build_system,
                    build_file=Path(project_path),  # Simplified for rebuild
                )
                progress_callback(
                    project,
                    f"Rebuilding SCIP for {project_path} [{project_status.language}]...",
                )

            # Rebuild
            project_dir = self.repo_root / project_path
            output_dir = self.scip_dir / project_path

            indexer_result = indexer.generate(
                project_dir, output_dir, project_status.build_system
            )

            # Build database from protobuf if successful - REQUIRED FOR SUCCESS
            if indexer_result.is_success() and indexer_result.output_file:
                try:
                    scip_file = indexer_result.output_file
                    db_manager = DatabaseManager(scip_file)
                    db_manager.create_schema()

                    builder = SCIPDatabaseBuilder()
                    builder.build(scip_file, db_manager.db_path)

                    db_manager.create_indexes()
                except Exception as e:
                    # Database build is MANDATORY - failure means rebuild failed
                    # Per Anti-Fallback Foundation #2: graceful failure over forceful success
                    logger.error(
                        f"Database build failed for {project_path}: {e}",
                        exc_info=True,
                    )
                    # Update result status to reflect database failure
                    indexer_result.status = IndexerStatus.FAILED
                    indexer_result.stderr = f"Database build failed: {e}"

            # Create updated status
            new_status = ProjectStatus(
                status=(
                    OverallStatus.SUCCESS
                    if indexer_result.is_success()
                    else OverallStatus.FAILED
                ),
                language=project_status.language,
                build_system=project_status.build_system,
                timestamp=datetime.now().isoformat(),
                duration_seconds=indexer_result.duration_seconds,
                output_file=(
                    str(indexer_result.output_file)
                    if indexer_result.output_file
                    else None
                ),
                error_message=indexer_result.stderr if indexer_result.stderr else None,
                exit_code=indexer_result.exit_code,
                stdout=indexer_result.stdout,
                stderr=indexer_result.stderr,
            )

            results[project_path] = new_status

            # Update status in tracker
            current_status.projects[project_path] = new_status

        # Recalculate overall status
        successful = sum(
            1
            for s in current_status.projects.values()
            if s.status == OverallStatus.SUCCESS
        )
        failed = sum(
            1
            for s in current_status.projects.values()
            if s.status == OverallStatus.FAILED
        )

        if failed == 0:
            current_status.overall_status = OverallStatus.SUCCESS
        elif successful > 0 and failed > 0:
            current_status.overall_status = OverallStatus.LIMBO
        elif successful == 0:
            current_status.overall_status = OverallStatus.FAILED

        current_status.successful_projects = successful
        current_status.failed_projects = failed

        # Save updated status
        tracker.save(current_status)

        return results
