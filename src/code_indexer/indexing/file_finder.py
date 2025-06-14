"""File discovery and filtering for indexing."""

import os
from pathlib import Path
from typing import Iterator, Dict
import pathspec

from ..config import Config


class FileFinder:
    """Finds and filters files for indexing based on configuration."""

    def __init__(self, config: Config):
        self.config = config
        self._create_gitignore_spec()

    def _create_gitignore_spec(self) -> None:
        """Create pathspec for excluded directories."""
        patterns = []

        # Add configured exclude directories
        for exclude_dir in self.config.exclude_dirs:
            patterns.append(f"{exclude_dir}/")
            patterns.append(f"**/{exclude_dir}/")

        # Add common patterns
        patterns.extend(
            [
                "*.pyc",
                "*.pyo",
                "*.pyd",
                "__pycache__/",
                "*.so",
                "*.dylib",
                "*.dll",
                ".DS_Store",
                "Thumbs.db",
                "*.tmp",
                "*.temp",
                "*.swp",
                "*.swo",
                "*~",
            ]
        )

        # Check for .gitignore file in codebase directory
        gitignore_path = self.config.codebase_dir / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                patterns.extend(
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                )

        self.exclude_spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)

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
