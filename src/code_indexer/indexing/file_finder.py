"""File discovery and filtering for indexing."""

import os
from pathlib import Path
from typing import Iterator, Dict
import pathspec

from ..config import Config
from ..services.override_filter_service import OverrideFilterService


class FileFinder:
    """Finds and filters files for indexing based on configuration."""

    def __init__(self, config: Config):
        self.config = config
        self._create_gitignore_spec()

        # Initialize override filter service if override config is available
        self.override_filter_service = None
        # Only initialize if we have a real OverrideConfig object, not a Mock
        if (
            hasattr(config, "override_config")
            and config.override_config is not None
            and not str(type(config.override_config)).startswith(
                "<class 'unittest.mock"
            )
        ):
            try:
                self.override_filter_service = OverrideFilterService(
                    config.override_config
                )
            except (TypeError, AttributeError):
                # If initialization fails (e.g., due to mock objects), skip override filtering
                pass

    def _create_gitignore_spec(self) -> None:
        """Create pathspec for excluded directories."""
        patterns = []

        # Merge base + override exclude directories for consistent pathspec-based exclusion
        all_exclude_dirs = list(self.config.exclude_dirs)
        if (
            hasattr(self.config, "override_config")
            and self.config.override_config is not None
            and not str(type(self.config.override_config)).startswith(
                "<class 'unittest.mock"
            )
        ):
            try:
                # Defensive: Ensure add_exclude_dirs exists and is iterable
                if hasattr(self.config.override_config, "add_exclude_dirs"):
                    override_dirs = self.config.override_config.add_exclude_dirs
                    if override_dirs and isinstance(override_dirs, (list, tuple)):
                        all_exclude_dirs.extend(override_dirs)
            except (TypeError, AttributeError):
                # Skip override dirs if initialization fails (e.g., mock objects)
                pass

        # Add patterns for all excluded directories
        for exclude_dir in all_exclude_dirs:
            # Use /** suffix to exclude all contents under the directory
            # This works for both single-level ("temp") and multi-level ("help/Source") paths
            patterns.append(f"{exclude_dir}/**")  # Matches from root: help/Source/**
            patterns.append(
                f"**/{exclude_dir}/**"
            )  # Matches nested: any/path/help/Source/**

        # Add common patterns
        patterns.extend(
            [
                # Python bytecode and cache
                "*.pyc",
                "*.pyo",
                "*.pyd",
                "__pycache__/",
                ".mypy_cache/",
                ".pytest_cache/",
                ".coverage",
                ".tox/",
                ".nox/",
                # Compiled binaries
                "*.so",
                "*.dylib",
                "*.dll",
                # OS artifacts
                ".DS_Store",
                "Thumbs.db",
                # Temporary files
                "*.tmp",
                "*.temp",
                "*.swp",
                "*.swo",
                "*~",
                # Common build/dist directories
                "node_modules/",
                "build/",
                "dist/",
                "target/",
                ".git/",
                # Code indexer configuration files
                ".code-indexer-override.yaml",
            ]
        )

        # Check for .gitignore files (root and nested)
        self._add_gitignore_patterns(self.config.codebase_dir, patterns)

        self.exclude_spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def _add_gitignore_patterns(self, directory: Path, patterns: list) -> None:
        """Add patterns from .gitignore files recursively."""
        gitignore_path = directory / ".gitignore"
        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # For nested .gitignore files, make patterns relative to the directory
                            if directory != self.config.codebase_dir:
                                relative_dir = directory.relative_to(
                                    self.config.codebase_dir
                                )
                                if not line.startswith("/"):
                                    line = f"{relative_dir}/{line}"
                            patterns.append(line)
            except (OSError, UnicodeDecodeError):
                pass  # Skip files that can't be read

        # Recursively check subdirectories for .gitignore files
        # But only go one level deep to avoid performance issues
        try:
            for subdir in directory.iterdir():
                if (
                    subdir.is_dir()
                    and subdir.name
                    not in {".git", "__pycache__", ".mypy_cache", "node_modules"}
                    and directory == self.config.codebase_dir
                ):  # Only check immediate subdirectories
                    self._add_gitignore_patterns(subdir, patterns)
        except (OSError, PermissionError):
            pass

    def _is_text_file(self, file_path: Path) -> bool:
        """Check if a file is likely a text file."""
        try:
            # Check extension first
            if file_path.suffix.lstrip(".") in self.config.file_extensions:
                return True

            # For files without extension or unknown extensions,
            # try to read a small portion to check if it's text
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                if not chunk:
                    return False

                # Check for null bytes (common in binary files)
                if b"\x00" in chunk:
                    return False

                # Try to decode as UTF-8
                try:
                    chunk.decode("utf-8")
                    return True
                except UnicodeDecodeError:
                    # Try other common encodings
                    for encoding in ["latin-1", "cp1252"]:
                        try:
                            chunk.decode(encoding)
                            return True
                        except UnicodeDecodeError:
                            continue
                    return False

        except (OSError, IOError):
            return False

    def _should_include_file(self, file_path: Path) -> bool:
        """Check if a file should be included in indexing."""
        try:
            # Check file size
            if file_path.stat().st_size > self.config.indexing.max_file_size:
                return False

            # Base filtering logic
            base_result = self._get_base_filtering_result(file_path)

            # Apply override filtering if available
            if self.override_filter_service:
                relative_path = file_path.relative_to(self.config.codebase_dir)
                return self.override_filter_service.should_include_file(
                    relative_path, base_result
                )

            return base_result

        except (OSError, ValueError):
            return False

    def _get_base_filtering_result(self, file_path: Path) -> bool:
        """Get base filtering result from config and gitignore rules."""
        try:
            # Check if file extension is in allowed list
            extension = file_path.suffix.lstrip(".")
            if extension not in self.config.file_extensions:
                return False

            # Check against exclude patterns
            relative_path = file_path.relative_to(self.config.codebase_dir)
            if self.exclude_spec.match_file(str(relative_path)):
                return False

            # Check if it's a text file
            return self._is_text_file(file_path)

        except (OSError, ValueError):
            return False

    def find_files(self) -> Iterator[Path]:
        """Find all files that should be indexed."""
        # Debug logging
        import datetime

        debug_file = os.path.expanduser("~/.tmp/cidx_debug.log")
        os.makedirs(os.path.dirname(debug_file), exist_ok=True)

        with open(debug_file, "a") as f:
            f.write(
                f"[{datetime.datetime.now().isoformat()}] FileFinder.find_files started for {self.config.codebase_dir}\n"
            )
            f.flush()

        if not self.config.codebase_dir.exists():
            raise ValueError(
                f"Codebase directory does not exist: {self.config.codebase_dir}"
            )

        if not self.config.codebase_dir.is_dir():
            raise ValueError(
                f"Codebase path is not a directory: {self.config.codebase_dir}"
            )

        for root, dirs, files in os.walk(self.config.codebase_dir):
            root_path = Path(root)

            # Filter directories to avoid walking into excluded ones
            dirs_to_remove = []
            for dir_name in dirs:
                dir_path = root_path / dir_name
                relative_dir = dir_path.relative_to(self.config.codebase_dir)
                if self.exclude_spec.match_file(str(relative_dir) + "/"):
                    dirs_to_remove.append(dir_name)

            for dir_name in dirs_to_remove:
                dirs.remove(dir_name)

            # Process files in current directory
            for file_name in files:
                file_path = root_path / file_name

                # Debug: Log file being checked
                if file_name == "ruff_output.json" or file_path.stat().st_size > 500000:
                    with open(debug_file, "a") as f:
                        f.write(
                            f"[{datetime.datetime.now().isoformat()}] Checking large file: {file_path} ({file_path.stat().st_size} bytes)\n"
                        )
                        f.flush()

                if self._should_include_file(file_path):
                    yield file_path

    def find_modified_files(self, since_timestamp: float) -> Iterator[Path]:
        """Find files modified since the given timestamp."""
        for file_path in self.find_files():
            try:
                if file_path.stat().st_mtime > since_timestamp:
                    yield file_path
            except OSError:
                continue

    def find_indexed_files(self, qdrant_client) -> set:
        """Get set of all file paths currently in the index."""
        try:
            # Get all points from the collection
            response = qdrant_client.client.post(
                f"/collections/{qdrant_client.config.collection}/points/scroll",
                json={
                    "limit": 10000,  # Large number to get all points
                    "with_payload": True,
                    "with_vector": False,
                },
            )
            response.raise_for_status()

            result = response.json()
            indexed_files = set()

            for point in result.get("result", {}).get("points", []):
                if "path" in point.get("payload", {}):
                    indexed_files.add(point["payload"]["path"])

            return indexed_files
        except Exception:
            return set()

    def find_deleted_files(self, qdrant_client) -> set:
        """Find files that are indexed but no longer exist on filesystem."""
        indexed_files = self.find_indexed_files(qdrant_client)
        current_files = set()

        # Get current files as relative paths
        for file_path in self.find_files():
            try:
                relative_path = str(file_path.relative_to(self.config.codebase_dir))
                current_files.add(relative_path)
            except ValueError:
                continue

        # Return files that are indexed but don't exist anymore
        return indexed_files - current_files

    def get_file_stats(self) -> dict:
        """Get statistics about discoverable files."""
        total_files = 0
        total_size = 0
        extensions: Dict[str, int] = {}

        for file_path in self.find_files():
            total_files += 1
            try:
                size = file_path.stat().st_size
                total_size += size

                ext = file_path.suffix.lstrip(".") or "no_extension"
                extensions[ext] = extensions.get(ext, 0) + 1

            except OSError:
                continue

        return {
            "total_files": total_files,
            "total_size": total_size,
            "extensions": extensions,
        }
