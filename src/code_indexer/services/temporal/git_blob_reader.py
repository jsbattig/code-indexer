"""GitBlobReader - Reads blob content from git object store."""
import subprocess
from pathlib import Path


class GitBlobReader:
    """Reads blob content from git object store.

    Uses git cat-file to extract the exact content of a blob
    identified by its SHA-1 hash, regardless of whether the blob
    exists in the current working tree.
    """

    def __init__(self, codebase_dir: Path):
        """Initialize the reader.

        Args:
            codebase_dir: Path to git repository root
        """
        self.codebase_dir = Path(codebase_dir)

    def read_blob_content(self, blob_hash: str) -> str:
        """Extract blob content as text.

        Args:
            blob_hash: Git blob hash (SHA-1)

        Returns:
            Blob content as string (UTF-8 decoded)

        Raises:
            ValueError: If blob cannot be read (invalid hash, binary content, etc.)
        """
        cmd = ["git", "cat-file", "blob", blob_hash]

        result = subprocess.run(
            cmd,
            cwd=self.codebase_dir,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise ValueError(f"Failed to read blob {blob_hash}: {result.stderr}")

        return result.stdout
