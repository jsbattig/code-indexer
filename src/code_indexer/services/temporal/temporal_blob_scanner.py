"""TemporalBlobScanner - Discovers blobs in git history."""
import subprocess
from pathlib import Path
from typing import List

from .models import BlobInfo


class TemporalBlobScanner:
    """Discovers blobs in git commit history.

    Uses git ls-tree to enumerate all blobs (files) in a commit's tree.
    Excludes tree objects (directories) and returns only file blobs.
    """

    def __init__(self, codebase_dir: Path):
        """Initialize the scanner.

        Args:
            codebase_dir: Path to git repository root
        """
        self.codebase_dir = Path(codebase_dir)

    def get_blobs_for_commit(self, commit_hash: str) -> List[BlobInfo]:
        """Get all blobs in a commit's tree.

        Args:
            commit_hash: Git commit hash (SHA-1)

        Returns:
            List of BlobInfo objects for all files in the commit

        Raises:
            subprocess.CalledProcessError: If git command fails (invalid commit, etc.)
        """
        # Use git ls-tree to get all objects in commit tree
        # -r: recursive (traverse subdirectories)
        # -l: show object size
        cmd = ["git", "ls-tree", "-r", "-l", commit_hash]

        result = subprocess.run(
            cmd,
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            check=True
        )

        blobs = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            # Format: <mode> <type> <hash> <size>\t<path>
            # Example: 100644 blob abc123def456 1234\tsrc/module.py
            parts = line.split()

            # Need at least 4 parts before the tab-separated path
            if len(parts) < 4:
                continue

            # Only process blob objects (files), skip tree objects (directories)
            if parts[1] != "blob":
                continue

            blob_hash = parts[2]
            size = int(parts[3])

            # Path is after the tab separator
            # Split only on first tab to preserve path with potential spaces
            file_path = line.split("\t", 1)[1]

            blobs.append(BlobInfo(
                blob_hash=blob_hash,
                file_path=file_path,
                commit_hash=commit_hash,
                size=size
            ))

        return blobs
