"""Data models for temporal git history indexing."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BlobInfo:
    """Information about a blob in git history.

    Attributes:
        blob_hash: Git's blob hash (SHA-1) for deduplication
        file_path: Relative path in repository
        commit_hash: Which commit this blob appears in
        size: Blob size in bytes
    """

    blob_hash: str
    file_path: str
    commit_hash: str
    size: int


@dataclass(frozen=True)
class CommitInfo:
    """Information about a git commit.

    Attributes:
        hash: Commit SHA-1 hash
        timestamp: Unix timestamp of commit
        author_name: Commit author name
        author_email: Commit author email
        message: Commit message (first line)
        parent_hashes: Space-separated parent commit hashes
    """

    hash: str
    timestamp: int
    author_name: str
    author_email: str
    message: str
    parent_hashes: str
