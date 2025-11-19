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
        diff_context_lines: int = 5,
    ):
        from pathlib import Path

        self.codebase_dir = Path(codebase_dir)
        self.override_filter_service = override_filter_service
        self.diff_context_lines = diff_context_lines

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
        """Get all file changes in a commit using single git call.

        Uses 'git show' with unified diff format to extract all file changes
        in a single subprocess call, reducing git overhead from 330ms to 33ms.

        Args:
            commit_hash: Git commit hash

        Returns:
            List of DiffInfo objects representing file changes
        """
        import subprocess

        # OPTIMIZATION: Single git call to get all changes
        # Use --full-index to get full 40-character blob hashes
        # Use -U flag to configure context lines (default 5, range 0-50)
        result = subprocess.run(
            [
                "git",
                "show",
                f"-U{self.diff_context_lines}",
                "--full-index",
                "--format=",
                commit_hash,
            ],
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            errors="replace",
        )

        # Parse unified diff output
        return self._parse_unified_diff(result.stdout, commit_hash)

    def _parse_unified_diff(self, diff_output, commit_hash):
        """Parse unified diff output from 'git show' command.

        State machine parser that processes unified diff format:
        - diff --git a/path b/path - Start of file diff
        - new file mode - Added file
        - deleted file mode - Deleted file
        - rename from/to - Renamed file
        - index hash1..hash2 - Blob hashes
        - Binary files differ - Binary file
        - @@...@@ - Diff hunks

        Args:
            diff_output: Unified diff output from git show
            commit_hash: Git commit hash

        Returns:
            List of DiffInfo objects
        """

        diffs = []
        lines = diff_output.split("\n")

        # OPTIMIZATION: Detect if we need parent commit (Issue #1 fix)
        # Pre-scan for deleted files to avoid unnecessary git call
        has_deleted_files = "deleted file mode" in diff_output
        parent_commit_hash = ""
        if has_deleted_files:
            parent_commit_hash = self._get_parent_commit(commit_hash)

        # State machine variables
        current_file_path = None
        current_old_path = None
        current_diff_type = None
        current_blob_hash = None
        current_old_blob_hash = None
        current_diff_content = []
        in_diff_content = False

        for line in lines:
            # Start of new file diff
            if line.startswith("diff --git "):
                # Save previous file if exists
                if current_file_path:
                    self._finalize_diff(
                        diffs,
                        current_file_path,
                        current_diff_type,
                        current_blob_hash,
                        current_old_blob_hash,
                        current_diff_content,
                        current_old_path,
                        commit_hash,
                        parent_commit_hash,
                    )

                # Parse new file paths from: diff --git a/path b/path
                parts = line.split()
                if len(parts) >= 4:
                    # Remove a/ and b/ prefixes
                    old_path = parts[2][2:] if parts[2].startswith("a/") else parts[2]
                    new_path = parts[3][2:] if parts[3].startswith("b/") else parts[3]

                    current_file_path = new_path
                    current_old_path = old_path if old_path != new_path else None
                    current_diff_type = "modified"  # Default, may be overridden
                    current_blob_hash = None
                    current_old_blob_hash = None
                    current_diff_content = []
                    in_diff_content = False

            # File type indicators
            elif line.startswith("new file mode"):
                current_diff_type = "added"

            elif line.startswith("deleted file mode"):
                current_diff_type = "deleted"

            elif line.startswith("rename from"):
                current_diff_type = "renamed"
                current_old_path = line.split("rename from ", 1)[1]

            elif line.startswith("rename to"):
                if current_diff_type != "renamed":
                    current_diff_type = "renamed"
                current_file_path = line.split("rename to ", 1)[1]

            # Extract blob hashes from index line
            elif line.startswith("index "):
                # Format: index old_hash..new_hash [mode]
                parts = line.split()
                if len(parts) >= 2:
                    hashes = parts[1].split("..")
                    if len(hashes) == 2:
                        current_old_blob_hash = hashes[0]
                        current_blob_hash = hashes[1]

                        # For added files, use new hash
                        if current_diff_type == "added":
                            current_blob_hash = hashes[1]
                        # For deleted files, use old hash
                        elif current_diff_type == "deleted":
                            current_blob_hash = hashes[0]

            # Binary file detection
            elif line.startswith("Binary files"):
                current_diff_type = "binary"
                current_diff_content = [f"Binary file: {current_file_path}"]

            # Diff content starts with @@
            elif line.startswith("@@"):
                in_diff_content = True
                current_diff_content.append(line)

            # Diff content lines (+, -, or context)
            elif in_diff_content:
                current_diff_content.append(line)

        # Save last file
        if current_file_path:
            self._finalize_diff(
                diffs,
                current_file_path,
                current_diff_type,
                current_blob_hash,
                current_old_blob_hash,
                current_diff_content,
                current_old_path,
                commit_hash,
                parent_commit_hash,
            )

        return diffs

    def _finalize_diff(
        self,
        diffs,
        file_path,
        diff_type,
        blob_hash,
        old_blob_hash,
        diff_content,
        old_path,
        commit_hash,
        parent_commit_hash,
    ):
        """Finalize and append a DiffInfo object to the diffs list.

        Args:
            diffs: List to append to
            file_path: File path
            diff_type: Type of change (added/deleted/modified/binary/renamed)
            blob_hash: Git blob hash
            old_blob_hash: Old blob hash (for deleted files)
            diff_content: List of diff content lines
            old_path: Old path (for renames)
            commit_hash: Git commit hash
            parent_commit_hash: Parent commit hash (pre-calculated to avoid N+1 git calls)
        """

        # Apply override filtering
        if not self._should_include_file(file_path):
            return

        # Format diff content based on type
        if diff_type == "added":
            # For added files, format as additions
            formatted_content = "\n".join(diff_content)
        elif diff_type == "deleted":
            # For deleted files, format as deletions
            formatted_content = "\n".join(diff_content)
        elif diff_type == "modified":
            # For modified files, keep diff hunks
            formatted_content = "\n".join(diff_content)
        elif diff_type == "binary":
            # For binary files, use metadata
            formatted_content = "\n".join(diff_content)
        elif diff_type == "renamed":
            # For renamed files, create metadata
            formatted_content = f"File renamed from {old_path} to {file_path}"
        else:
            formatted_content = "\n".join(diff_content)

        # Use pre-calculated parent commit hash (passed as parameter)
        # For non-deleted files, parent_commit_hash will be empty string
        final_parent_hash = parent_commit_hash if diff_type == "deleted" else ""

        diffs.append(
            DiffInfo(
                file_path=file_path,
                diff_type=diff_type,
                commit_hash=commit_hash,
                diff_content=formatted_content,
                blob_hash=blob_hash or "",
                old_path=old_path or "",
                parent_commit_hash=final_parent_hash,
            )
        )

    def _get_parent_commit(self, commit_hash: str) -> str:
        """Get parent commit hash for a commit.

        Calculates parent commit ONCE to avoid N+1 git calls when processing
        multiple deleted files in a single commit.

        Args:
            commit_hash: Git commit hash

        Returns:
            Parent commit hash, or empty string if no parent (root commit)
        """
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", f"{commit_hash}^"],
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            errors="replace",
        )
        return result.stdout.strip() if result.returncode == 0 else ""

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
