"""
End-to-end tests for file content pagination (Story #686 - S8).

Tests the complete pagination workflow with real files and real FileListingService.
Following TDD methodology and anti-mock principle - real systems only.
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path

from code_indexer.server.services.file_service import FileListingService
from code_indexer.server.models.file_content_limits_config import (
    FileContentLimitsConfig,
)
from code_indexer.server.services.file_content_limits_config_manager import (
    FileContentLimitsConfigManager,
)


@pytest.mark.e2e
class TestFileContentPaginationE2E:
    """E2E tests for file content pagination with real files."""

    def setup_method(self):
        """Set up real test repository with various file sizes."""
        self.test_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.test_dir) / "test_repo"
        self.repo_path.mkdir(parents=True)

        # Reset singleton to ensure clean state
        FileContentLimitsConfigManager._instance = None

        # Configure with high token limit so line limits are the deciding factor
        self.config_db_path = Path(self.test_dir) / "config.db"
        self.config_manager = FileContentLimitsConfigManager(
            db_path=str(self.config_db_path)
        )
        self.config_manager.update_config(
            FileContentLimitsConfig(max_tokens_per_request=20000, chars_per_token=4)
        )

        self.service = FileListingService()
        self.service._config_manager = self.config_manager

        # Create test files with known content
        self._create_test_files()

    def teardown_method(self):
        """Clean up test directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _create_test_files(self):
        """Create test files with controlled line counts."""
        # Small file (100 lines) - under default limit
        small_file = self.repo_path / "small.py"
        lines = [f"# Small file line {i+1}\n" for i in range(100)]
        small_file.write_text("".join(lines))

        # Medium file (600 lines) - over default limit but under max
        medium_file = self.repo_path / "medium.py"
        lines = [f"# Medium file line {i+1}\n" for i in range(600)]
        medium_file.write_text("".join(lines))

        # Large file (2000 lines) - well over default limit
        large_file = self.repo_path / "large.py"
        lines = [f"# Large file line {i+1}\n" for i in range(2000)]
        large_file.write_text("".join(lines))

    def test_small_file_returns_all_content(self):
        """File under 500 lines returns all content without pagination."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="small.py",
            offset=None,
            limit=None,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 100

        metadata = result["metadata"]
        assert metadata["total_lines"] == 100
        assert metadata["returned_lines"] == 100
        assert metadata["has_more"] is False
        assert metadata["next_offset"] is None

    def test_medium_file_default_truncation(self):
        """File over 500 lines is truncated to DEFAULT_MAX_LINES (500)."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="medium.py",
            offset=None,
            limit=None,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 500, f"Expected 500, got {len(content_lines)}"
        assert content_lines[0] == "# Medium file line 1"
        assert content_lines[-1] == "# Medium file line 500"

        metadata = result["metadata"]
        assert metadata["total_lines"] == 600
        assert metadata["returned_lines"] == 500
        assert metadata["has_more"] is True
        assert metadata["next_offset"] == 501

    def test_large_file_pagination_workflow(self):
        """Complete pagination workflow for large file."""
        # Page 1: Get first 500 lines (default)
        result1 = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=None,
            limit=None,
        )

        lines1 = result1["content"].strip().split("\n")
        assert len(lines1) == 500
        assert lines1[0] == "# Large file line 1"
        assert lines1[-1] == "# Large file line 500"
        assert result1["metadata"]["has_more"] is True
        assert result1["metadata"]["next_offset"] == 501

        # Page 2: Use next_offset to get next chunk
        result2 = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=result1["metadata"]["next_offset"],
            limit=None,
        )

        lines2 = result2["content"].strip().split("\n")
        assert len(lines2) == 500
        assert lines2[0] == "# Large file line 501"
        assert lines2[-1] == "# Large file line 1000"
        assert result2["metadata"]["has_more"] is True
        assert result2["metadata"]["next_offset"] == 1001

        # Page 3: Use next_offset to get next chunk
        result3 = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=result2["metadata"]["next_offset"],
            limit=None,
        )

        lines3 = result3["content"].strip().split("\n")
        assert len(lines3) == 500
        assert lines3[0] == "# Large file line 1001"
        assert lines3[-1] == "# Large file line 1500"
        assert result3["metadata"]["has_more"] is True
        assert result3["metadata"]["next_offset"] == 1501

        # Page 4: Last page
        result4 = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=result3["metadata"]["next_offset"],
            limit=None,
        )

        lines4 = result4["content"].strip().split("\n")
        assert len(lines4) == 500
        assert lines4[0] == "# Large file line 1501"
        assert lines4[-1] == "# Large file line 2000"
        assert result4["metadata"]["has_more"] is False
        assert result4["metadata"]["next_offset"] is None

    def test_custom_limit_respected(self):
        """Custom limit under MAX_ALLOWED_LIMIT is respected."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=None,
            limit=100,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 100

        metadata = result["metadata"]
        assert metadata["returned_lines"] == 100
        assert metadata["has_more"] is True
        assert metadata["next_offset"] == 101

    def test_limit_capped_at_max_allowed(self):
        """Limit over MAX_ALLOWED_LIMIT (5000) is capped (line limit applies before token limit).

        Story #686: The stricter of (line limit, token limit) wins.
        This test uses very short lines so line limit is stricter.
        """
        # Create a very large file with SHORT lines (3 chars each: "X\n")
        # This ensures line limit (5000) is hit before token limit (80000 chars)
        huge_file = self.repo_path / "huge_short_lines.py"
        lines = [f"{i}\n" for i in range(10000)]  # ~3-5 chars per line
        huge_file.write_text("".join(lines))

        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="huge_short_lines.py",
            offset=None,
            limit=10000,  # Request more than MAX_ALLOWED_LIMIT
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 5000, f"Expected 5000 (capped at MAX_ALLOWED_LIMIT), got {len(content_lines)}"

        metadata = result["metadata"]
        assert metadata["returned_lines"] == 5000
        assert metadata["has_more"] is True
        assert metadata["next_offset"] == 5001

    def test_offset_and_limit_combined(self):
        """Offset and limit work together correctly."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="large.py",
            offset=100,
            limit=50,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 50
        assert content_lines[0] == "# Large file line 100"
        assert content_lines[-1] == "# Large file line 149"

        metadata = result["metadata"]
        assert metadata["offset"] == 100
        assert metadata["returned_lines"] == 50
        assert metadata["has_more"] is True
        assert metadata["next_offset"] == 150

    def test_metadata_fields_complete(self):
        """All required metadata fields are present."""
        result = self.service.get_file_content_by_path(
            repo_path=str(self.repo_path),
            file_path="small.py",
            offset=None,
            limit=None,
        )

        metadata = result["metadata"]

        # Original fields
        assert "size" in metadata
        assert "modified_at" in metadata
        assert "language" in metadata
        assert "path" in metadata
        assert "total_lines" in metadata
        assert "returned_lines" in metadata
        assert "offset" in metadata
        assert "limit" in metadata
        assert "has_more" in metadata

        # Story #686: New field
        assert "next_offset" in metadata

        # Token enforcement fields
        assert "estimated_tokens" in metadata
        assert "max_tokens_per_request" in metadata
        assert "truncated" in metadata
        assert "requires_pagination" in metadata
