"""SCIP project auto-discovery module."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple


# Build file mappings: filename -> (language, build_system)
BUILD_FILE_MAPPINGS: Dict[str, Tuple[str, str]] = {
    "pom.xml": ("java", "maven"),
    "build.gradle": ("java", "gradle"),
    "build.gradle.kts": ("kotlin", "gradle"),
    "package.json": ("typescript", "npm"),
    "pyproject.toml": ("python", "poetry"),
    "setup.py": ("python", "setuptools"),
    "requirements.txt": ("python", "pip"),
}

# Build file priority: lower number = higher priority
# Used for deduplication when multiple build files exist in same directory
BUILD_FILE_PRIORITY: Dict[str, int] = {
    "pyproject.toml": 1,
    "setup.py": 2,
    "requirements.txt": 3,
    "pom.xml": 1,
    "build.gradle": 1,
    "build.gradle.kts": 1,
    "package.json": 1,
}


@dataclass
class DiscoveredProject:
    """Represents a discovered project with its metadata."""

    relative_path: Path
    language: str
    build_system: str
    build_file: Path


class ProjectDiscovery:
    """Discovers buildable projects in a repository."""

    def __init__(self, repo_root: Path):
        """
        Initialize project discovery.

        Args:
            repo_root: Root directory of the repository to scan
        """
        self.repo_root = Path(repo_root)

    def discover(self) -> List[DiscoveredProject]:
        """
        Discover all buildable projects in the repository.

        Scans for known build files (pom.xml, package.json, pyproject.toml, etc.)
        and creates DiscoveredProject instances for each found project.

        When multiple build files exist in the same directory, only the highest
        priority build file is used (based on BUILD_FILE_PRIORITY).

        Returns:
            List of DiscoveredProject instances
        """
        seen_dirs: Dict[Path, DiscoveredProject] = {}

        # Scan for all build files
        for build_file_name, (language, build_system) in BUILD_FILE_MAPPINGS.items():
            for build_file in self.repo_root.rglob(build_file_name):
                # Get project directory (parent of build file)
                project_dir = build_file.parent

                # Check if we've already seen this directory
                if project_dir in seen_dirs:
                    existing = seen_dirs[project_dir]
                    current_priority = BUILD_FILE_PRIORITY.get(build_file_name, 999)
                    existing_priority = BUILD_FILE_PRIORITY.get(
                        existing.build_file.name, 999
                    )
                    # Skip if current build file has lower priority (higher number)
                    if current_priority >= existing_priority:
                        continue

                relative_path = project_dir.relative_to(self.repo_root)
                relative_build_file = build_file.relative_to(self.repo_root)

                project = DiscoveredProject(
                    relative_path=relative_path,
                    language=language,
                    build_system=build_system,
                    build_file=relative_build_file,
                )
                seen_dirs[project_dir] = project

        return list(seen_dirs.values())
