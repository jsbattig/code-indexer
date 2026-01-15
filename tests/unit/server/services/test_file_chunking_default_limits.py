"""
Unit tests for FileService line-based default limits (Story #686 - S8).

Tests default_max_lines=500 and max_allowed_limit=5000 behavior.
These line limits work IN ADDITION to existing token limits.
"""

import pytest

from code_indexer.server.services.file_service import FileListingService
from code_indexer.server.models.file_content_limits_config import (
    FileContentLimitsConfig,
)
from code_indexer.server.services.file_content_limits_config_manager import (
    FileContentLimitsConfigManager,
)


@pytest.fixture
def high_token_service(tmp_path):
    """Service with high token limit so line limits are the deciding factor."""
    FileContentLimitsConfigManager._instance = None
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir(parents=True)

    config_manager = FileContentLimitsConfigManager(db_path=str(tmp_path / "config.db"))
    # 20000 tokens * 4 chars = 80000 chars max (max allowed by config)
    # This is enough for 500 lines * 10 chars = 5000 chars for short lines
    config_manager.update_config(
        FileContentLimitsConfig(max_tokens_per_request=20000, chars_per_token=4)
    )

    service = FileListingService()
    service._config_manager = config_manager
    return service, repo_path


class TestDefaultMaxLinesLimit:
    """Test default_max_lines=500 when no explicit limit provided."""

    def test_file_under_500_lines_returns_all_no_limit(self, high_token_service):
        """File with <500 lines returns all lines when no limit specified."""
        service, repo_path = high_token_service
        test_file = repo_path / "small.py"
        lines = [f"# Line {i+1}\n" for i in range(100)]
        test_file.write_text("".join(lines))

        result = service.get_file_content_by_path(
            repo_path=str(repo_path),
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

    def test_file_over_500_lines_returns_500_no_limit(self, high_token_service):
        """File with >500 lines returns first 500 when no limit specified."""
        service, repo_path = high_token_service
        test_file = repo_path / "medium.py"
        lines = [f"# Line {i+1}\n" for i in range(1000)]
        test_file.write_text("".join(lines))

        result = service.get_file_content_by_path(
            repo_path=str(repo_path),
            file_path="medium.py",
            offset=None,
            limit=None,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 500
        assert content_lines[0] == "# Line 1"
        assert content_lines[-1] == "# Line 500"

        metadata = result["metadata"]
        assert metadata["total_lines"] == 1000
        assert metadata["returned_lines"] == 500
        assert metadata["has_more"] is True
        assert metadata["next_offset"] == 501

    def test_file_exactly_500_lines_returns_all(self, high_token_service):
        """File with exactly 500 lines returns all when no limit specified."""
        service, repo_path = high_token_service
        test_file = repo_path / "exact500.py"
        lines = [f"# Line {i+1}\n" for i in range(500)]
        test_file.write_text("".join(lines))

        result = service.get_file_content_by_path(
            repo_path=str(repo_path),
            file_path="exact500.py",
            offset=None,
            limit=None,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 500

        metadata = result["metadata"]
        assert metadata["returned_lines"] == 500
        assert metadata["has_more"] is False
        assert metadata["next_offset"] is None

    def test_offset_501_returns_next_500_lines(self, high_token_service):
        """Offset=501, no limit returns lines 501-1000 (next 500)."""
        service, repo_path = high_token_service
        test_file = repo_path / "large.py"
        lines = [f"# Line {i+1}\n" for i in range(1000)]
        test_file.write_text("".join(lines))

        result = service.get_file_content_by_path(
            repo_path=str(repo_path),
            file_path="large.py",
            offset=501,
            limit=None,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 500
        assert content_lines[0] == "# Line 501"
        assert content_lines[-1] == "# Line 1000"

        metadata = result["metadata"]
        assert metadata["returned_lines"] == 500
        assert metadata["has_more"] is False
        assert metadata["next_offset"] is None


class TestMaxAllowedLimit:
    """Test max_allowed_limit=5000 caps client-specified limits."""

    def test_limit_under_5000_respected(self, high_token_service):
        """Client limit < 5000 is respected."""
        service, repo_path = high_token_service
        test_file = repo_path / "large.py"
        lines = [f"# Line {i+1}\n" for i in range(10000)]
        test_file.write_text("".join(lines))

        result = service.get_file_content_by_path(
            repo_path=str(repo_path),
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

    def test_limit_exactly_5000_respected(self, high_token_service):
        """Client limit = 5000 is respected (max allowed)."""
        service, repo_path = high_token_service
        test_file = repo_path / "large.py"
        lines = [f"# Line {i+1}\n" for i in range(10000)]
        test_file.write_text("".join(lines))

        result = service.get_file_content_by_path(
            repo_path=str(repo_path),
            file_path="large.py",
            offset=None,
            limit=5000,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 5000

        metadata = result["metadata"]
        assert metadata["returned_lines"] == 5000
        assert metadata["has_more"] is True
        assert metadata["next_offset"] == 5001

    def test_limit_over_5000_capped(self, high_token_service):
        """Client limit > 5000 is capped to max_allowed_limit (5000)."""
        service, repo_path = high_token_service
        test_file = repo_path / "large.py"
        lines = [f"# Line {i+1}\n" for i in range(10000)]
        test_file.write_text("".join(lines))

        result = service.get_file_content_by_path(
            repo_path=str(repo_path),
            file_path="large.py",
            offset=None,
            limit=10000,
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 5000

        metadata = result["metadata"]
        assert metadata["returned_lines"] == 5000
        assert metadata["has_more"] is True
        assert metadata["next_offset"] == 5001
