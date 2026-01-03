"""
Unit tests for Claude Code Response Protocol.

Tests response validation for Claude Code integration:
- Response structure validation
- pr_description field validation
- Length constraints (max 100 chars)

Story #659: Git State Management for SCIP Self-Healing with PR Workflow
AC4: Enhanced Claude Code Response Protocol
"""

from pathlib import Path

import pytest

from code_indexer.server.services.claude_code_response import (
    ClaudeCodeResponse,
    ResponseValidationError,
)


class TestClaudeCodeResponseValidation:
    """Tests for Claude Code response validation (AC4)."""

    def test_valid_response_with_pr_description(self):
        """AC4: Valid response with pr_description under 100 chars."""
        # ARRANGE & ACT
        response = ClaudeCodeResponse(
            success=True,
            message="Fix completed successfully",
            files_modified=[Path("src/auth.py"), Path("src/utils.py")],
            pr_description="Auto-fix: Missing import statements",
        )

        # ASSERT
        assert response.success is True
        assert response.message == "Fix completed successfully"
        assert len(response.files_modified) == 2
        assert response.pr_description == "Auto-fix: Missing import statements"
        assert len(response.pr_description) <= 100

    def test_valid_response_pr_description_exactly_100_chars(self):
        """AC4: pr_description exactly 100 chars is valid."""
        # ARRANGE
        pr_desc = "A" * 100  # Exactly 100 characters

        # ACT
        response = ClaudeCodeResponse(
            success=True,
            message="Fix applied",
            files_modified=[Path("file.py")],
            pr_description=pr_desc,
        )

        # ASSERT
        assert len(response.pr_description) == 100

    def test_invalid_response_pr_description_exceeds_100_chars(self):
        """AC4: pr_description over 100 chars raises validation error."""
        # ARRANGE
        pr_desc = "A" * 101  # 101 characters - too long

        # ACT & ASSERT
        with pytest.raises(ResponseValidationError) as exc_info:
            ClaudeCodeResponse(
                success=True,
                message="Fix applied",
                files_modified=[Path("file.py")],
                pr_description=pr_desc,
            )

        assert "pr_description exceeds maximum length" in str(exc_info.value)
        assert "100" in str(exc_info.value)

    def test_valid_response_pr_description_defaults_to_empty(self):
        """AC4: pr_description defaults to empty string when omitted."""
        # ACT
        response = ClaudeCodeResponse(
            success=True,
            message="Fix applied",
            files_modified=[Path("file.py")],
            # pr_description omitted - should default to ""
        )

        # ASSERT
        assert response.pr_description == ""

    def test_valid_response_empty_pr_description_allowed(self):
        """AC4: Empty pr_description is valid (for failures)."""
        # ACT
        response = ClaudeCodeResponse(
            success=False, message="Fix failed", files_modified=[], pr_description=""
        )

        # ASSERT
        assert response.success is False
        assert response.pr_description == ""

    def test_response_to_dict(self):
        """AC4: Response serializes to dict correctly."""
        # ARRANGE
        response = ClaudeCodeResponse(
            success=True,
            message="Fixed",
            files_modified=[Path("a.py"), Path("b.py")],
            pr_description="Auto-fix: Type errors",
        )

        # ACT
        data = response.to_dict()

        # ASSERT
        assert data["success"] is True
        assert data["message"] == "Fixed"
        assert data["files_modified"] == ["a.py", "b.py"]  # Paths converted to strings
        assert data["pr_description"] == "Auto-fix: Type errors"

    def test_response_from_dict(self):
        """AC4: Response deserializes from dict correctly."""
        # ARRANGE
        data = {
            "success": True,
            "message": "Fixed",
            "files_modified": ["src/main.py"],
            "pr_description": "Auto-fix: Missing imports",
        }

        # ACT
        response = ClaudeCodeResponse.from_dict(data)

        # ASSERT
        assert response.success is True
        assert response.message == "Fixed"
        assert response.files_modified == [Path("src/main.py")]
        assert response.pr_description == "Auto-fix: Missing imports"

    def test_response_from_dict_invalid_pr_description(self):
        """AC4: Deserialize with invalid pr_description raises error."""
        # ARRANGE
        data = {
            "success": True,
            "message": "Fixed",
            "files_modified": ["file.py"],
            "pr_description": "X" * 101,  # Too long
        }

        # ACT & ASSERT
        with pytest.raises(ResponseValidationError):
            ClaudeCodeResponse.from_dict(data)
