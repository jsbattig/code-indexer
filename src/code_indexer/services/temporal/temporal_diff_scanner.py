"""TemporalDiffScanner - Gets file changes (diffs) per commit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..override_filter_service import OverrideFilterService


@dataclass
class DiffInfo:
    """Information about a file change in a commit."""

    file_path: str
    diff_type: str
    commit_hash: str
    diff_content: str
    blob_hash: str = ""  # Git blob hash for deduplication
    old_path: str = ""
    parent_commit_hash: str = ""  # Parent commit for deleted file reconstruction


class TemporalDiffScanner:
    def __init__(
        self,
        codebase_dir,
        override_filter_service: Optional[OverrideFilterService] = None,
    ):
        from pathlib import Path

        self.codebase_dir = Path(codebase_dir)
        self.override_filter_service = override_filter_service

    def _should_include_file(self, file_path: str) -> bool:
        """Check if file should be included based on override filtering.

        Args:
            file_path: Relative file path from git diff

        Returns:
            True if file should be included, False if filtered out
        """
        if self.override_filter_service is None:
            return True  # No filtering - include all files

        from pathlib import Path

        # Convert string path to Path object
        path_obj = Path(file_path)

        # For temporal indexing, base_result is True (include by default)
        # Override filtering applies exclusion rules on top
        base_result = True

        # Apply override filtering
        return self.override_filter_service.should_include_file(path_obj, base_result)

    def get_diffs_for_commit(self, commit_hash):
        import subprocess

        diffs = []

        # Call git to get changed files
        result = subprocess.run(
            ["git", "show", "--name-status", "--format=", commit_hash],
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            errors="replace",
        )

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            status = parts[0][0]  # First character

            # All operations need at least 2 parts (status + path)
            if len(parts) < 2:
                continue

            # Handle rename which needs 3 parts
            # Git rename output: "R100\told_path\tnew_path"
            if status == "R":
                if len(parts) >= 3:
                    # Normal 3-part rename format
                    old_path = parts[1]
                    file_path = parts[2]
                else:
                    # Malformed rename line - skip
                    continue
            else:
                file_path = parts[1]
                old_path = ""

            # Apply override filtering - skip excluded files
            if not self._should_include_file(file_path):
                continue

            if status == "A":  # Added file
                # Check if file is binary first
                is_binary = self._is_binary_file(file_path)

                if is_binary:
                    # Create metadata for binary file
                    diff_content = f"Binary file added: {file_path}"
                    diff_type = "binary"
                else:
                    # Get full content
                    content_result = subprocess.run(
                        ["git", "show", f"{commit_hash}:{file_path}"],
                        cwd=self.codebase_dir,
                        capture_output=True,
                        text=True,
                        errors="replace",
                    )

                    # Format as additions
                    lines = content_result.stdout.split("\n")
                    diff_content = "\n".join(f"+{line}" for line in lines if line)
                    diff_type = "added"

                # Get blob hash for the added file
                blob_hash = self._get_blob_hash(commit_hash, file_path)

                diffs.append(
                    DiffInfo(
                        file_path=file_path,
                        diff_type=diff_type,
                        commit_hash=commit_hash,
                        diff_content=diff_content,
                        blob_hash=blob_hash,
                        old_path="",
                    )
                )
            elif status == "D":  # Deleted file
                # Check if file is binary first
                is_binary = self._is_binary_file(file_path)

                if is_binary:
                    # Create metadata for binary file
                    diff_content = f"Binary file deleted: {file_path}"
                    diff_type = "binary"
                else:
                    # Get content from parent commit
                    content_result = subprocess.run(
                        ["git", "show", f"{commit_hash}^:{file_path}"],
                        cwd=self.codebase_dir,
                        capture_output=True,
                        text=True,
                        errors="replace",
                    )

                    # Format as deletions
                    lines = content_result.stdout.split("\n")
                    diff_content = "\n".join(f"-{line}" for line in lines if line)
                    diff_type = "deleted"

                # For deleted files, get blob hash from parent commit
                blob_hash = self._get_blob_hash(f"{commit_hash}^", file_path)

                # Get parent commit hash for reconstruction
                parent_result = subprocess.run(
                    ["git", "rev-parse", f"{commit_hash}^"],
                    cwd=self.codebase_dir,
                    capture_output=True,
                    text=True,
                    errors="replace",
                )
                parent_commit_hash = (
                    parent_result.stdout.strip()
                    if parent_result.returncode == 0
                    else ""
                )

                diffs.append(
                    DiffInfo(
                        file_path=file_path,
                        diff_type=diff_type,
                        commit_hash=commit_hash,
                        diff_content=diff_content,
                        blob_hash=blob_hash,
                        old_path="",
                        parent_commit_hash=parent_commit_hash,
                    )
                )
            elif status == "M":  # Modified file
                # Check if file is binary first
                is_binary = self._is_binary_file(file_path)

                if is_binary:
                    # Create metadata for binary file
                    diff_content = f"Binary file modified: {file_path}"
                    diff_type = "binary"
                else:
                    # Get diff for modified file
                    content_result = subprocess.run(
                        ["git", "show", commit_hash, "--", file_path],
                        cwd=self.codebase_dir,
                        capture_output=True,
                        text=True,
                        errors="replace",
                    )

                    # Check if git detected it as binary in diff output
                    if "Binary files differ" in content_result.stdout:
                        diff_content = f"Binary file modified: {file_path}"
                        diff_type = "binary"
                    else:
                        # Extract just the diff part (skip header)
                        lines = content_result.stdout.split("\n")
                        diff_lines = []
                        in_diff = False
                        for line in lines:
                            if line.startswith("@@"):
                                in_diff = True
                            if in_diff:
                                diff_lines.append(line)

                        diff_content = "\n".join(diff_lines)
                        diff_type = "modified"

                # For modified files, get blob hash at current commit
                blob_hash = self._get_blob_hash(commit_hash, file_path)

                diffs.append(
                    DiffInfo(
                        file_path=file_path,
                        diff_type=diff_type,
                        commit_hash=commit_hash,
                        diff_content=diff_content,
                        blob_hash=blob_hash,
                        old_path="",
                    )
                )
            elif status == "R":  # Renamed file
                # Create metadata showing rename
                diff_content = f"File renamed from {old_path} to {file_path}"

                diffs.append(
                    DiffInfo(
                        file_path=file_path,
                        diff_type="renamed",
                        commit_hash=commit_hash,
                        diff_content=diff_content,
                        old_path=old_path,
                    )
                )

        return diffs

    def _is_binary_file(self, file_path):
        """Check if a file is binary based on its extension or content."""
        # Common binary file extensions
        binary_extensions = {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".svg",
            ".ico",
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".zip",
            ".tar",
            ".gz",
            ".rar",
            ".7z",
            ".bz2",
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".o",
            ".bin",
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".wav",
            ".flac",
            ".ttf",
            ".otf",
            ".woff",
            ".woff2",
            ".eot",
            ".pyc",
            ".pyo",
            ".class",
            ".jar",
            ".war",
            ".db",
            ".sqlite",
            ".sqlite3",
        }

        from pathlib import Path

        ext = Path(file_path).suffix.lower()
        return ext in binary_extensions

    def _get_blob_hash(self, commit_hash, file_path):
        """Get git blob hash for a file in a specific commit."""
        import subprocess

        # Use git rev-parse to get the blob hash for the file at this commit
        cmd = ["git", "rev-parse", f"{commit_hash}:{file_path}"]
        result = subprocess.run(
            cmd, cwd=self.codebase_dir, capture_output=True, text=True, errors="replace"
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # File might not exist at this commit (deleted), return empty
            return ""
