"""SCIP status tracking and persistence module."""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class OverallStatus(Enum):
    """Overall status of SCIP generation."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    LIMBO = "limbo"  # Partial success (some succeeded, some failed)


@dataclass
class ProjectStatus:
    """Status of SCIP generation for a single project."""

    status: OverallStatus
    language: str
    build_system: str
    timestamp: str
    duration_seconds: Optional[float] = None
    output_file: Optional[str] = None
    error_message: Optional[str] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None


@dataclass
class GenerationStatus:
    """Overall status of SCIP generation for all projects."""

    overall_status: OverallStatus
    total_projects: int
    successful_projects: int
    failed_projects: int
    projects: Dict[str, ProjectStatus]

    def is_limbo(self) -> bool:
        """Check if in limbo state (partial success)."""
        return self.overall_status == OverallStatus.LIMBO

    def is_success(self) -> bool:
        """Check if all projects succeeded."""
        return self.overall_status == OverallStatus.SUCCESS

    def is_failed(self) -> bool:
        """Check if all projects failed."""
        return self.overall_status == OverallStatus.FAILED


class StatusTracker:
    """Tracks and persists SCIP generation status."""

    def __init__(self, scip_dir: Path):
        """
        Initialize status tracker.

        Args:
            scip_dir: Directory containing SCIP indexes (e.g., .code-indexer/scip/)
        """
        self.scip_dir = Path(scip_dir)
        self.status_file = self.scip_dir / "status.json"

    def save(self, status: GenerationStatus) -> None:
        """
        Save generation status to disk.

        Args:
            status: GenerationStatus to persist
        """
        # Ensure directory exists
        self.scip_dir.mkdir(parents=True, exist_ok=True)

        # Convert to dict for JSON serialization
        status_dict = {
            "overall_status": status.overall_status.value,
            "total_projects": status.total_projects,
            "successful_projects": status.successful_projects,
            "failed_projects": status.failed_projects,
            "projects": {
                project_path: {
                    "status": project_status.status.value,
                    "language": project_status.language,
                    "build_system": project_status.build_system,
                    "timestamp": project_status.timestamp,
                    "duration_seconds": project_status.duration_seconds,
                    "output_file": project_status.output_file,
                    "error_message": project_status.error_message,
                    "exit_code": project_status.exit_code,
                    "stdout": project_status.stdout,
                    "stderr": project_status.stderr,
                }
                for project_path, project_status in status.projects.items()
            },
        }

        # Write to file
        with open(self.status_file, "w") as f:
            json.dump(status_dict, f, indent=2)

    def load(self) -> GenerationStatus:
        """
        Load generation status from disk.

        Returns:
            GenerationStatus loaded from disk, or default pending status if not found
        """
        if not self.status_file.exists():
            return GenerationStatus(
                overall_status=OverallStatus.PENDING,
                total_projects=0,
                successful_projects=0,
                failed_projects=0,
                projects={},
            )

        with open(self.status_file, "r") as f:
            data = json.load(f)

        # Convert back to dataclasses
        projects = {
            project_path: ProjectStatus(
                status=OverallStatus(project_data["status"]),
                language=project_data["language"],
                build_system=project_data["build_system"],
                timestamp=project_data["timestamp"],
                duration_seconds=project_data.get("duration_seconds"),
                output_file=project_data.get("output_file"),
                error_message=project_data.get("error_message"),
                exit_code=project_data.get("exit_code"),
                stdout=project_data.get("stdout"),
                stderr=project_data.get("stderr"),
            )
            for project_path, project_data in data["projects"].items()
        }

        return GenerationStatus(
            overall_status=OverallStatus(data["overall_status"]),
            total_projects=data["total_projects"],
            successful_projects=data["successful_projects"],
            failed_projects=data["failed_projects"],
            projects=projects,
        )
