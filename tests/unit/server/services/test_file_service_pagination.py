"""
Unit tests for FileService get_file_content pagination feature (Story #638).

Tests all 12 acceptance criteria:
1. Default Behavior (Backward Compatibility) - full file when no params
2. First Page - offset=1, limit=2000 returns lines 1-2000
3. Subsequent Page - offset=2001, limit=2000 returns lines 2001-4000
4. Targeted Navigation - offset=8500, limit=100 returns lines 8500-8599
5. Last Page Partial - offset=4500, limit=2000 returns lines 4500-5000 (501 lines)
6. Offset Beyond File - offset=200 when file has 100 lines returns empty
7. Small File Within Limit - offset=1, limit=2000 for 50-line file returns all 50
8. Limit Only (No Offset) - limit=100 returns lines 1-100
9. Invalid Offset - offset=0 or negative returns error (handled in handler)
10. Invalid Limit - limit=0 or negative returns error (handled in handler)
11. MCP Tool Schema - tested separately in test_mcp_tool_definitions.py
12. REST API Parity - tested separately in test_files_router.py

This file tests FileService.get_file_content() and get_file_content_by_path() pagination logic.
"""

import pytest

from src.code_indexer.server.services.file_service import FileListingService


class TestFileContentPagination:
    """Test get_file_content pagination with offset/limit parameters."""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary repository with test files."""
        # Create source directory
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create a file with 5000 lines for pagination tests
        large_file = src_dir / "large_file.py"
        lines = [f"# Line {i+1}\n" for i in range(5000)]
        large_file.write_text("".join(lines))

        # Create a file with 100 lines
        medium_file = src_dir / "medium_file.py"
        lines = [f"# Line {i+1}\n" for i in range(100)]
        medium_file.write_text("".join(lines))

        # Create a file with 50 lines
        small_file = src_dir / "small_file.py"
        lines = [f"# Line {i+1}\n" for i in range(50)]
        small_file.write_text("".join(lines))

        # Create a file with 10000 lines for targeted navigation test
        huge_file = src_dir / "huge_file.py"
        lines = [f"# Line {i+1}\n" for i in range(10000)]
        huge_file.write_text("".join(lines))

        return tmp_path

    @pytest.fixture
    def service(self):
        """Create FileListingService instance without database dependency."""
        service = FileListingService.__new__(FileListingService)
        service.activated_repo_manager = None
        return service

    # -------------------------------------------------------------------------
    # AC1: Default Behavior (Line-Limited First Chunk - Story #686)
    # -------------------------------------------------------------------------
    def test_default_behavior_returns_full_file(self, temp_repo, service):
        """AC1: When no offset or limit provided, return DEFAULT_MAX_LINES (500) lines.

        Story #686 changed behavior: Line limits are applied IN ADDITION to token limits.
        With DEFAULT_MAX_LINES=500, when no limit is specified, only 500 lines are returned
        (stricter than token limit for short lines).
        """
        file_path = "src/large_file.py"

        # Call without offset/limit parameters (new behavior: line-limited chunk)
        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path
        )

        # Story #686: DEFAULT_MAX_LINES (500) is stricter than token limit for short lines
        # File has 5000 lines * 9 chars/line = 45,000 chars total
        # Token limit: 5000 tokens * 4 chars = 20,000 chars (~2222 lines of 9 chars each)
        # Line limit: DEFAULT_MAX_LINES = 500 (stricter, wins)
        content_lines = result["content"].strip().split("\n")
        assert (
            len(content_lines) == 500
        ), f"Should return 500 lines (DEFAULT_MAX_LINES), got {len(content_lines)}"
        assert content_lines[0] == "# Line 1", "First line should be Line 1"
        assert content_lines[-1] == "# Line 500", "Last line should be Line 500"

        # Verify metadata shows pagination required
        metadata = result["metadata"]
        assert metadata["total_lines"] == 5000, "total_lines should be 5000"
        assert (
            metadata["returned_lines"] == 500
        ), f"returned_lines should be 500 (DEFAULT_MAX_LINES), got {metadata['returned_lines']}"
        assert (
            metadata["requires_pagination"] is True
        ), "requires_pagination should be True for large file"
        # truncated is False because line limit was hit before token limit
        assert metadata["offset"] == 1, "offset should default to 1"
        assert metadata["limit"] is None, "limit should be None when not provided"
        assert (
            metadata["has_more"] is True
        ), "has_more should be True when more content exists"
        # Story #686: next_offset should be set for pagination
        assert metadata["next_offset"] == 501, "next_offset should be 501 for next page"

    # -------------------------------------------------------------------------
    # AC2: First Page (User Limit Respected Under MAX_ALLOWED_LIMIT - Story #686)
    # -------------------------------------------------------------------------
    def test_first_page_with_offset_1_limit_2000(self, temp_repo, service):
        """AC2: offset=1, limit=2000 returns 2000 lines (user limit respected).

        Story #686: User-specified limit is respected as long as it's under MAX_ALLOWED_LIMIT (5000).
        For short lines, the token limit (~2222 lines) doesn't kick in before user limit (2000).
        """
        file_path = "src/large_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=1, limit=2000
        )

        # User limit=2000 is respected (under MAX_ALLOWED_LIMIT=5000)
        # Token limit: 20,000 chars = ~2222 lines (not hit for 2000 lines of 9 chars)
        content_lines = result["content"].strip().split("\n")
        assert (
            len(content_lines) == 2000
        ), f"Should return 2000 lines (user limit), got {len(content_lines)}"
        assert content_lines[0] == "# Line 1", "First line should be Line 1"
        assert content_lines[-1] == "# Line 2000", "Last line should be Line 2000"

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["total_lines"] == 5000
        assert (
            metadata["returned_lines"] == 2000
        ), f"returned_lines should be 2000 (user limit), got {metadata['returned_lines']}"
        assert metadata["offset"] == 1
        assert metadata["limit"] == 2000
        # truncated is False because line limit was hit before token limit
        assert (
            metadata["requires_pagination"] is True
        ), "requires_pagination should be True"
        assert metadata["has_more"] is True, "Should have more lines after 2000"
        # Story #686: next_offset should be set
        assert metadata["next_offset"] == 2001, "next_offset should be 2001"

    # -------------------------------------------------------------------------
    # AC3: Subsequent Page (User Limit Respected - Story #686)
    # -------------------------------------------------------------------------
    def test_subsequent_page_offset_2001_limit_2000(self, temp_repo, service):
        """AC3: offset=2001, limit=2000 returns 2000 lines (user limit respected).

        Story #686: User-specified limit is respected. For subsequent pages,
        the user limit of 2000 is still under MAX_ALLOWED_LIMIT=5000.
        """
        file_path = "src/large_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=2001, limit=2000
        )

        # User limit=2000 is respected (under MAX_ALLOWED_LIMIT=5000)
        content_lines = result["content"].strip().split("\n")
        assert (
            len(content_lines) == 2000
        ), f"Should return 2000 lines (user limit), got {len(content_lines)}"
        assert content_lines[0] == "# Line 2001", "First line should be Line 2001"
        assert content_lines[-1] == "# Line 4000", "Last line should be Line 4000"

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["total_lines"] == 5000
        assert (
            metadata["returned_lines"] == 2000
        ), f"returned_lines should be 2000 (user limit), got {metadata['returned_lines']}"
        assert metadata["offset"] == 2001
        assert metadata["limit"] == 2000
        assert (
            metadata["requires_pagination"] is True
        ), "requires_pagination should be True"
        assert metadata["has_more"] is True, "Should have more lines after 4000"
        # Story #686: next_offset should be set
        assert metadata["next_offset"] == 4001, "next_offset should be 4001"

    # -------------------------------------------------------------------------
    # AC4: Targeted Navigation
    # -------------------------------------------------------------------------
    def test_targeted_navigation_offset_8500_limit_100(self, temp_repo, service):
        """AC4: offset=8500, limit=100 returns lines 8500-8599."""
        file_path = "src/huge_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=8500, limit=100
        )

        # Verify correct lines returned
        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 100, "Should return exactly 100 lines"
        assert content_lines[0] == "# Line 8500", "First line should be Line 8500"
        assert content_lines[-1] == "# Line 8599", "Last line should be Line 8599"

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["total_lines"] == 10000
        assert metadata["returned_lines"] == 100
        assert metadata["offset"] == 8500
        assert metadata["limit"] == 100
        assert metadata["has_more"] is True, "Should have more lines after 8599"

    # -------------------------------------------------------------------------
    # AC5: Last Page Partial
    # -------------------------------------------------------------------------
    def test_last_page_partial_offset_4500_limit_2000(self, temp_repo, service):
        """AC5: offset=4500, limit=2000 returns lines 4500-5000 (501 lines)."""
        file_path = "src/large_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=4500, limit=2000
        )

        # Verify correct lines returned (partial last page)
        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 501, "Should return 501 lines (4500-5000)"
        assert content_lines[0] == "# Line 4500", "First line should be Line 4500"
        assert content_lines[-1] == "# Line 5000", "Last line should be Line 5000"

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["total_lines"] == 5000
        assert metadata["returned_lines"] == 501, "returned_lines should be 501"
        assert metadata["offset"] == 4500
        assert metadata["limit"] == 2000
        assert metadata["has_more"] is False, "No more lines after 5000"

    # -------------------------------------------------------------------------
    # AC6: Offset Beyond File
    # -------------------------------------------------------------------------
    def test_offset_beyond_file_returns_empty(self, temp_repo, service):
        """AC6: offset=200 when file has 100 lines returns empty content."""
        file_path = "src/medium_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=200, limit=50
        )

        # Verify empty content
        assert (
            result["content"] == ""
        ), "Content should be empty when offset beyond file"

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["total_lines"] == 100, "total_lines should still be 100"
        assert metadata["returned_lines"] == 0, "returned_lines should be 0"
        assert metadata["offset"] == 200
        assert metadata["limit"] == 50
        assert metadata["has_more"] is False, "No more lines when offset beyond file"

    # -------------------------------------------------------------------------
    # AC7: Small File Within Limit
    # -------------------------------------------------------------------------
    def test_small_file_within_limit(self, temp_repo, service):
        """AC7: offset=1, limit=2000 for 50-line file returns all 50 lines."""
        file_path = "src/small_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=1, limit=2000
        )

        # Verify all lines returned
        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 50, "Should return all 50 lines"
        assert content_lines[0] == "# Line 1"
        assert content_lines[-1] == "# Line 50"

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["total_lines"] == 50
        assert metadata["returned_lines"] == 50
        assert metadata["offset"] == 1
        assert metadata["limit"] == 2000
        assert metadata["has_more"] is False, "No more lines in small file"

    # -------------------------------------------------------------------------
    # AC8: Limit Only (No Offset)
    # -------------------------------------------------------------------------
    def test_limit_only_no_offset(self, temp_repo, service):
        """AC8: limit=100 (no offset) returns lines 1-100."""
        file_path = "src/large_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo),
            file_path=file_path,
            limit=100,  # No offset parameter
        )

        # Verify lines 1-100 returned
        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 100, "Should return exactly 100 lines"
        assert content_lines[0] == "# Line 1", "First line should be Line 1"
        assert content_lines[-1] == "# Line 100", "Last line should be Line 100"

        # Verify metadata
        metadata = result["metadata"]
        assert metadata["total_lines"] == 5000
        assert metadata["returned_lines"] == 100
        assert metadata["offset"] == 1, "offset should default to 1 when not provided"
        assert metadata["limit"] == 100
        assert metadata["has_more"] is True, "Should have more lines after 100"

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------
    def test_offset_at_exact_file_end(self, temp_repo, service):
        """Edge case: offset=5000 (last line) returns just that line."""
        file_path = "src/large_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=5000, limit=100
        )

        # Verify just the last line
        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 1, "Should return just 1 line"
        assert content_lines[0] == "# Line 5000"

        metadata = result["metadata"]
        assert metadata["returned_lines"] == 1
        assert metadata["has_more"] is False

    def test_offset_one_past_file_end(self, temp_repo, service):
        """Edge case: offset=5001 (one past end) returns empty."""
        file_path = "src/large_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=5001, limit=100
        )

        assert result["content"] == ""
        assert result["metadata"]["returned_lines"] == 0
        assert result["metadata"]["has_more"] is False

    def test_limit_exactly_matches_remaining_lines(self, temp_repo, service):
        """Edge case: offset=4001, limit=1000 exactly matches remaining 1000 lines."""
        file_path = "src/large_file.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=4001, limit=1000
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 1000
        assert content_lines[0] == "# Line 4001"
        assert content_lines[-1] == "# Line 5000"

        metadata = result["metadata"]
        assert metadata["returned_lines"] == 1000
        assert metadata["has_more"] is False, "No more lines when exact match"


class TestGetFileContentByPathPagination:
    """Test get_file_content_by_path pagination (mirror of get_file_content)."""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary repository with test files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create a file with 5000 lines
        large_file = src_dir / "test.py"
        lines = [f"# Line {i+1}\n" for i in range(5000)]
        large_file.write_text("".join(lines))

        return tmp_path

    @pytest.fixture
    def service(self):
        """Create FileListingService instance without database dependency."""
        service = FileListingService.__new__(FileListingService)
        service.activated_repo_manager = None
        return service

    def test_get_file_content_by_path_supports_pagination(self, temp_repo, service):
        """Verify get_file_content_by_path has same pagination support."""
        file_path = "src/test.py"

        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path=file_path, offset=100, limit=50
        )

        content_lines = result["content"].strip().split("\n")
        assert len(content_lines) == 50
        assert content_lines[0] == "# Line 100"
        assert content_lines[-1] == "# Line 149"

        metadata = result["metadata"]
        assert metadata["total_lines"] == 5000
        assert metadata["returned_lines"] == 50
        assert metadata["offset"] == 100
        assert metadata["limit"] == 50
        assert metadata["has_more"] is True


class TestMetadataFields:
    """Test that all metadata fields are present and accurate."""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary repository with a test file."""
        (tmp_path / "test.txt").write_text("Line 1\nLine 2\nLine 3\n")
        return tmp_path

    @pytest.fixture
    def service(self):
        """Create FileListingService instance without database dependency."""
        service = FileListingService.__new__(FileListingService)
        service.activated_repo_manager = None
        return service

    def test_metadata_includes_all_pagination_fields(self, temp_repo, service):
        """Verify metadata includes total_lines, returned_lines, offset, limit, has_more."""
        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path="test.txt", offset=1, limit=2
        )

        metadata = result["metadata"]

        # Verify all new pagination fields present
        assert "total_lines" in metadata, "metadata must include total_lines"
        assert "returned_lines" in metadata, "metadata must include returned_lines"
        assert "offset" in metadata, "metadata must include offset"
        assert "limit" in metadata, "metadata must include limit"
        assert "has_more" in metadata, "metadata must include has_more"

        # Verify existing fields still present
        assert "size" in metadata, "existing size field must be preserved"
        assert "modified_at" in metadata, "existing modified_at field must be preserved"
        assert "language" in metadata, "existing language field must be preserved"
        assert "path" in metadata, "existing path field must be preserved"

        # Verify values are correct
        assert metadata["total_lines"] == 3
        assert metadata["returned_lines"] == 2
        assert metadata["offset"] == 1
        assert metadata["limit"] == 2
        assert metadata["has_more"] is True

    def test_metadata_accuracy_for_various_scenarios(self, temp_repo, service):
        """Test metadata accuracy across different pagination scenarios."""
        # Scenario 1: First page with more data
        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path="test.txt", offset=1, limit=2
        )
        assert result["metadata"]["has_more"] is True

        # Scenario 2: Last page (partial)
        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path="test.txt", offset=2, limit=5
        )
        assert result["metadata"]["returned_lines"] == 2  # Only 2 lines left
        assert result["metadata"]["has_more"] is False

        # Scenario 3: Full file (no pagination)
        result = service.get_file_content_by_path(
            repo_path=str(temp_repo), file_path="test.txt"
        )
        assert result["metadata"]["returned_lines"] == 3
        assert result["metadata"]["total_lines"] == 3
        assert result["metadata"]["has_more"] is False
        assert result["metadata"]["limit"] is None
