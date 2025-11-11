"""Tests for temporal models."""

import pytest
from code_indexer.services.temporal.models import BlobInfo, CommitInfo


class TestBlobInfo:
    """Test BlobInfo dataclass."""

    def test_blob_info_creation(self):
        """Test BlobInfo can be created with all required fields."""
        blob = BlobInfo(
            blob_hash="abc123def456",
            file_path="src/module.py",
            commit_hash="commit789",
            size=1234,
        )

        assert blob.blob_hash == "abc123def456"
        assert blob.file_path == "src/module.py"
        assert blob.commit_hash == "commit789"
        assert blob.size == 1234

    def test_blob_info_equality(self):
        """Test BlobInfo instances with same values are equal."""
        blob1 = BlobInfo(
            blob_hash="abc123", file_path="test.py", commit_hash="commit1", size=100
        )
        blob2 = BlobInfo(
            blob_hash="abc123", file_path="test.py", commit_hash="commit1", size=100
        )

        assert blob1 == blob2

    def test_blob_info_immutability(self):
        """Test BlobInfo is immutable (frozen dataclass)."""
        blob = BlobInfo(
            blob_hash="abc123", file_path="test.py", commit_hash="commit1", size=100
        )

        with pytest.raises(AttributeError):
            blob.blob_hash = "different"  # type: ignore

    def test_blob_info_repr(self):
        """Test BlobInfo has meaningful repr."""
        blob = BlobInfo(
            blob_hash="abc123def456",
            file_path="src/module.py",
            commit_hash="commit789",
            size=1234,
        )

        repr_str = repr(blob)
        assert "BlobInfo" in repr_str
        assert "abc123def456" in repr_str
        assert "src/module.py" in repr_str


class TestCommitInfo:
    """Test CommitInfo dataclass."""

    def test_commit_info_creation(self):
        """Test CommitInfo can be created with all required fields."""
        commit = CommitInfo(
            hash="abc123",
            timestamp=1234567890,
            author_name="John Doe",
            author_email="john@example.com",
            message="Test commit",
            parent_hashes="parent1 parent2",
        )

        assert commit.hash == "abc123"
        assert commit.timestamp == 1234567890
        assert commit.author_name == "John Doe"
        assert commit.author_email == "john@example.com"
        assert commit.message == "Test commit"
        assert commit.parent_hashes == "parent1 parent2"

    def test_commit_info_equality(self):
        """Test CommitInfo instances with same values are equal."""
        commit1 = CommitInfo(
            hash="abc123",
            timestamp=1234567890,
            author_name="John Doe",
            author_email="john@example.com",
            message="Test",
            parent_hashes="parent1",
        )
        commit2 = CommitInfo(
            hash="abc123",
            timestamp=1234567890,
            author_name="John Doe",
            author_email="john@example.com",
            message="Test",
            parent_hashes="parent1",
        )

        assert commit1 == commit2

    def test_commit_info_immutability(self):
        """Test CommitInfo is immutable (frozen dataclass)."""
        commit = CommitInfo(
            hash="abc123",
            timestamp=1234567890,
            author_name="John Doe",
            author_email="john@example.com",
            message="Test",
            parent_hashes="parent1",
        )

        with pytest.raises(AttributeError):
            commit.hash = "different"  # type: ignore
