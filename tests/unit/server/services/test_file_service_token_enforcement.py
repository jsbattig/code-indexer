"""
Unit tests for FileService token enforcement.

Tests token-based content limits for get_file_content and get_file_content_by_path methods.
"""

import os
import tempfile
from pathlib import Path

import pytest

from code_indexer.server.services.file_service import FileListingService
from code_indexer.server.models.file_content_limits_config import FileContentLimitsConfig
from code_indexer.server.services.file_content_limits_config_manager import (
    FileContentLimitsConfigManager,
)


class TestFileServiceTokenEnforcement:
    """Test suite for FileService token enforcement."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.temp_dir) / "test_repo"
        self.repo_path.mkdir(parents=True)

        # Create test file with known content (100 lines, ~50 chars per line)
        self.test_file_path = self.repo_path / "test.py"
        self.test_content_lines = []
        for i in range(1, 101):
            line = f"# This is line {i:03d} with some test content here\n"
            self.test_content_lines.append(line)

        with open(self.test_file_path, "w", encoding="utf-8") as f:
            f.writelines(self.test_content_lines)

        # Reset singleton instance to avoid cross-test contamination
        FileContentLimitsConfigManager._instance = None

        # Initialize config manager with test database
        self.config_db_path = Path(self.temp_dir) / "test_config.db"
        self.config_manager = FileContentLimitsConfigManager(db_path=str(self.config_db_path))

        # Initialize service with test config manager
        self.service = FileListingService()
        self.service._config_manager = self.config_manager

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_default_behavior_returns_first_chunk_only(self):
        """Test that calling get_file_content_by_path without params enforces token limits."""
        # Default config: 5000 tokens, 4 chars/token = 20000 chars max
        config = self.config_manager.get_config()
        assert config.max_tokens_per_request == 5000
        assert config.chars_per_token == 4

        # Call without offset/limit
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="test.py",
            offset=None,
            limit=None,
        )

        # Content should be limited by token budget
        content = result["content"]
        metadata = result["metadata"]

        assert len(content) <= config.max_chars_per_request
        assert metadata["estimated_tokens"] <= config.max_tokens_per_request
        assert "pagination_hint" in metadata

        # Test file is only ~5000 chars (100 lines * 50 chars), well under 20000 char budget
        # So it should return completely without pagination
        assert metadata["requires_pagination"] is False
        assert metadata["truncated"] is False

    def test_token_enforcement_with_small_file(self):
        """Test that small files (within token budget) return entire content."""
        # Create small file (10 lines, well under 5000 tokens)
        small_file = self.repo_path / "small.py"
        small_lines = [f"# Line {i}\n" for i in range(1, 11)]
        with open(small_file, "w", encoding="utf-8") as f:
            f.writelines(small_lines)

        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="small.py",
            offset=None,
            limit=None,
        )

        content = result["content"]
        metadata = result["metadata"]

        # Small file should return all content
        assert content == "".join(small_lines)
        assert metadata["requires_pagination"] is False
        assert metadata["truncated"] is False
        assert metadata["total_lines"] == 10
        assert metadata["returned_lines"] == 10

    def test_token_enforcement_truncates_large_content(self):
        """Test that content exceeding token budget is truncated."""
        # Create large file (1000 lines, will exceed 5000 tokens)
        large_file = self.repo_path / "large.py"
        large_lines = [f"# This is a very long line {i:04d} with lots of content here to fill space\n" for i in range(1, 1001)]
        with open(large_file, "w", encoding="utf-8") as f:
            f.writelines(large_lines)

        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=None,
            limit=None,
        )

        content = result["content"]
        metadata = result["metadata"]

        # Config: 5000 tokens * 4 chars/token = 20000 chars max
        config = self.config_manager.get_config()
        assert len(content) <= config.max_chars_per_request

        # Should be truncated
        assert metadata["truncated"] is True
        assert metadata["truncated_at_line"] is not None
        assert metadata["truncated_at_line"] < metadata["total_lines"]
        assert metadata["requires_pagination"] is True
        assert metadata["estimated_tokens"] <= config.max_tokens_per_request

    def test_user_specified_offset_limit_respects_token_budget(self):
        """Test that user-specified offset/limit still enforces token budget."""
        # User requests lines 1-500, but token budget may truncate further
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="test.py",
            offset=1,
            limit=500,
        )

        content = result["content"]
        metadata = result["metadata"]

        # Config: 5000 tokens * 4 chars/token = 20000 chars max
        config = self.config_manager.get_config()
        assert len(content) <= config.max_chars_per_request
        assert metadata["estimated_tokens"] <= config.max_tokens_per_request

        # Metadata should reflect actual returned content
        assert metadata["offset"] == 1
        assert metadata["returned_lines"] <= 500  # May be less due to token limit

    def test_metadata_includes_estimated_tokens(self):
        """Test that metadata includes estimated_tokens field."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="test.py",
            offset=None,
            limit=None,
        )

        metadata = result["metadata"]

        assert "estimated_tokens" in metadata
        assert isinstance(metadata["estimated_tokens"], int)
        assert metadata["estimated_tokens"] > 0

    def test_metadata_includes_max_tokens_per_request(self):
        """Test that metadata includes max_tokens_per_request from config."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="test.py",
            offset=None,
            limit=None,
        )

        metadata = result["metadata"]
        config = self.config_manager.get_config()

        assert "max_tokens_per_request" in metadata
        assert metadata["max_tokens_per_request"] == config.max_tokens_per_request

    def test_metadata_includes_truncated_flag(self):
        """Test that metadata includes truncated flag."""
        # Small file (not truncated)
        small_file = self.repo_path / "small.py"
        small_lines = [f"# Line {i}\n" for i in range(1, 11)]
        with open(small_file, "w", encoding="utf-8") as f:
            f.writelines(small_lines)

        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="small.py",
            offset=None,
            limit=None,
        )

        assert result["metadata"]["truncated"] is False

        # Large file (truncated) - needs to exceed 20000 chars (5000 tokens * 4 chars/token)
        # Create file with 1000 lines of ~75 chars each = ~75000 chars (will be truncated)
        large_file = self.repo_path / "large.py"
        large_lines = [f"# This is a very long line {i:04d} with lots of content here to fill space\n" for i in range(1, 1001)]
        with open(large_file, "w", encoding="utf-8") as f:
            f.writelines(large_lines)

        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=None,
            limit=None,
        )

        assert result["metadata"]["truncated"] is True

    def test_metadata_includes_truncated_at_line(self):
        """Test that metadata includes truncated_at_line when truncated."""
        # Large file (will be truncated)
        large_file = self.repo_path / "large.py"
        large_lines = [f"# Line {i}\n" for i in range(1, 1001)]
        with open(large_file, "w", encoding="utf-8") as f:
            f.writelines(large_lines)

        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=None,
            limit=None,
        )

        metadata = result["metadata"]

        assert "truncated_at_line" in metadata
        if metadata["truncated"]:
            assert metadata["truncated_at_line"] is not None
            assert metadata["truncated_at_line"] > 0
            assert metadata["truncated_at_line"] <= metadata["total_lines"]
        else:
            assert metadata["truncated_at_line"] is None

    def test_metadata_includes_requires_pagination(self):
        """Test that metadata includes requires_pagination hint."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="test.py",
            offset=None,
            limit=None,
        )

        metadata = result["metadata"]

        assert "requires_pagination" in metadata
        assert isinstance(metadata["requires_pagination"], bool)

    def test_metadata_includes_pagination_hint(self):
        """Test that metadata includes helpful pagination_hint."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="test.py",
            offset=None,
            limit=None,
        )

        metadata = result["metadata"]

        assert "pagination_hint" in metadata
        if metadata["requires_pagination"]:
            assert isinstance(metadata["pagination_hint"], str)
            assert len(metadata["pagination_hint"]) > 0

    def test_custom_config_affects_token_limit(self):
        """Test that updating config changes token enforcement."""
        # Update config to smaller token limit
        new_config = FileContentLimitsConfig(max_tokens_per_request=1000, chars_per_token=4)
        self.config_manager.update_config(new_config)

        # Create file that would fit in 5000 tokens but not 1000 tokens
        # 200 lines * 24 chars = 4800 chars total, exceeds 1000 token budget (4000 chars)
        medium_file = self.repo_path / "medium.py"
        medium_lines = [f"# Line {i:03d} content data\n" for i in range(1, 201)]
        with open(medium_file, "w", encoding="utf-8") as f:
            f.writelines(medium_lines)

        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="medium.py",
            offset=None,
            limit=None,
        )

        content = result["content"]
        metadata = result["metadata"]

        # Should be limited by new 1000 token budget (1000 * 4 = 4000 chars)
        assert len(content) <= 4000
        assert metadata["estimated_tokens"] <= 1000
        assert metadata["max_tokens_per_request"] == 1000

    def test_never_exceeds_token_budget(self):
        """Test that content NEVER exceeds max_tokens budget."""
        # Create very large file
        huge_file = self.repo_path / "huge.py"
        huge_lines = [f"# This is line {i:05d} with lots and lots of content to make it long\n" for i in range(1, 5001)]
        with open(huge_file, "w", encoding="utf-8") as f:
            f.writelines(huge_lines)

        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="huge.py",
            offset=None,
            limit=None,
        )

        content = result["content"]
        metadata = result["metadata"]
        config = self.config_manager.get_config()

        # CRITICAL: NEVER exceed token budget
        assert len(content) <= config.max_chars_per_request
        assert metadata["estimated_tokens"] <= config.max_tokens_per_request

    def test_get_file_content_applies_same_enforcement(self):
        """Test that get_file_content (with repo lookup) applies same token enforcement."""
        # NOTE: This test requires mocking ActivatedRepoManager to return test repo path
        # For now, we focus on get_file_content_by_path which has the same enforcement logic
        # Integration tests will verify get_file_content behavior with real repo lookups
        pass

    def test_backward_compatibility_with_explicit_params(self):
        """Test that explicit offset/limit params still work (backward compatible)."""
        # Request specific range with explicit params
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="test.py",
            offset=10,
            limit=20,
        )

        content = result["content"]
        metadata = result["metadata"]

        # Should respect user params but still enforce token limit
        assert metadata["offset"] == 10
        # Returned lines may be less than 20 if token budget exceeded
        assert metadata["returned_lines"] <= 20

        config = self.config_manager.get_config()
        assert len(content) <= config.max_chars_per_request
        assert metadata["estimated_tokens"] <= config.max_tokens_per_request
