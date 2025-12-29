"""Tests for git operation MCP tool definitions.

Story #628: MCP Tool Definitions
Tests the 17 git operation tool definitions for repository management.
"""

import pytest
from jsonschema import validate, ValidationError

from code_indexer.server.mcp.tools import TOOL_REGISTRY


class TestGitInspectionTools:
    """Test git inspection tools (status only - diff/log already exist)."""

    def test_git_status_exists(self):
        """Verify git_status tool is registered."""
        assert "git_status" in TOOL_REGISTRY

    def test_git_status_schema_valid(self):
        """Verify git_status accepts valid repository_alias."""
        tool = TOOL_REGISTRY["git_status"]
        schema = tool["inputSchema"]

        valid_input = {"repository_alias": "test-repo"}
        validate(instance=valid_input, schema=schema)

    def test_git_status_permission(self):
        """Verify git_status requires repository:read permission."""
        tool = TOOL_REGISTRY["git_status"]
        assert tool["required_permission"] == "repository:read"


class TestGitStagingTools:
    """Test git staging tools (stage, unstage)."""

    def test_git_stage_exists(self):
        """Verify git_stage tool is registered."""
        assert "git_stage" in TOOL_REGISTRY

    def test_git_stage_schema_requires_file_paths(self):
        """Verify git_stage requires file_paths array."""
        tool = TOOL_REGISTRY["git_stage"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "file_paths": ["src/file1.py", "src/file2.py"]
        }
        validate(instance=valid_input, schema=schema)

    def test_git_stage_schema_missing_file_paths(self):
        """Verify git_stage rejects missing file_paths."""
        tool = TOOL_REGISTRY["git_stage"]
        schema = tool["inputSchema"]

        invalid_input = {"repository_alias": "test-repo"}

        with pytest.raises(ValidationError):
            validate(instance=invalid_input, schema=schema)

    def test_git_stage_permission(self):
        """Verify git_stage requires repository:write permission."""
        tool = TOOL_REGISTRY["git_stage"]
        assert tool["required_permission"] == "repository:write"

    def test_git_unstage_exists(self):
        """Verify git_unstage tool is registered."""
        assert "git_unstage" in TOOL_REGISTRY

    def test_git_unstage_schema_requires_file_paths(self):
        """Verify git_unstage requires file_paths array."""
        tool = TOOL_REGISTRY["git_unstage"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "file_paths": ["src/file1.py"]
        }
        validate(instance=valid_input, schema=schema)

    def test_git_unstage_permission(self):
        """Verify git_unstage requires repository:write permission."""
        tool = TOOL_REGISTRY["git_unstage"]
        assert tool["required_permission"] == "repository:write"


class TestGitCommitPushPullTools:
    """Test git commit/push/pull/fetch tools."""

    def test_git_commit_exists(self):
        """Verify git_commit tool is registered."""
        assert "git_commit" in TOOL_REGISTRY

    def test_git_commit_schema_requires_message(self):
        """Verify git_commit requires message."""
        tool = TOOL_REGISTRY["git_commit"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "message": "Fix bug in authentication"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_commit_schema_with_optional_author(self):
        """Verify git_commit accepts optional author_name and author_email."""
        tool = TOOL_REGISTRY["git_commit"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "message": "Add feature",
            "author_name": "John Doe",
            "author_email": "john@example.com"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_commit_permission(self):
        """Verify git_commit requires repository:write permission."""
        tool = TOOL_REGISTRY["git_commit"]
        assert tool["required_permission"] == "repository:write"

    def test_git_push_exists(self):
        """Verify git_push tool is registered."""
        assert "git_push" in TOOL_REGISTRY

    def test_git_push_schema_with_optional_remote_branch(self):
        """Verify git_push accepts optional remote and branch."""
        tool = TOOL_REGISTRY["git_push"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "remote": "origin",
            "branch": "main"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_push_permission(self):
        """Verify git_push requires repository:write permission."""
        tool = TOOL_REGISTRY["git_push"]
        assert tool["required_permission"] == "repository:write"

    def test_git_pull_exists(self):
        """Verify git_pull tool is registered."""
        assert "git_pull" in TOOL_REGISTRY

    def test_git_pull_permission(self):
        """Verify git_pull requires repository:write permission."""
        tool = TOOL_REGISTRY["git_pull"]
        assert tool["required_permission"] == "repository:write"

    def test_git_fetch_exists(self):
        """Verify git_fetch tool is registered."""
        assert "git_fetch" in TOOL_REGISTRY

    def test_git_fetch_permission(self):
        """Verify git_fetch requires repository:write permission."""
        tool = TOOL_REGISTRY["git_fetch"]
        assert tool["required_permission"] == "repository:write"


class TestGitResetCleanTools:
    """Test git reset/clean tools (destructive operations)."""

    def test_git_reset_exists(self):
        """Verify git_reset tool is registered."""
        assert "git_reset" in TOOL_REGISTRY

    def test_git_reset_schema_requires_mode(self):
        """Verify git_reset requires mode parameter."""
        tool = TOOL_REGISTRY["git_reset"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "mode": "soft"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_reset_schema_mode_enum_validation(self):
        """Verify git_reset mode accepts only valid values."""
        tool = TOOL_REGISTRY["git_reset"]
        schema = tool["inputSchema"]

        # Valid modes
        for mode in ["soft", "mixed", "hard"]:
            valid_input = {
                "repository_alias": "test-repo",
                "mode": mode
            }
            validate(instance=valid_input, schema=schema)

    def test_git_reset_permission(self):
        """Verify git_reset requires repository:admin permission."""
        tool = TOOL_REGISTRY["git_reset"]
        assert tool["required_permission"] == "repository:admin"

    def test_git_clean_exists(self):
        """Verify git_clean tool is registered."""
        assert "git_clean" in TOOL_REGISTRY

    def test_git_clean_schema_requires_confirmation(self):
        """Verify git_clean requires confirmation_token."""
        tool = TOOL_REGISTRY["git_clean"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "confirmation_token": "CONFIRM_DELETE_UNTRACKED"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_clean_permission(self):
        """Verify git_clean requires repository:admin permission."""
        tool = TOOL_REGISTRY["git_clean"]
        assert tool["required_permission"] == "repository:admin"

    def test_git_merge_abort_exists(self):
        """Verify git_merge_abort tool is registered."""
        assert "git_merge_abort" in TOOL_REGISTRY

    def test_git_merge_abort_permission(self):
        """Verify git_merge_abort requires repository:write permission."""
        tool = TOOL_REGISTRY["git_merge_abort"]
        assert tool["required_permission"] == "repository:write"

    def test_git_checkout_file_exists(self):
        """Verify git_checkout_file tool is registered."""
        assert "git_checkout_file" in TOOL_REGISTRY

    def test_git_checkout_file_schema_requires_file_path(self):
        """Verify git_checkout_file requires file_path."""
        tool = TOOL_REGISTRY["git_checkout_file"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "file_path": "src/file.py"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_checkout_file_permission(self):
        """Verify git_checkout_file requires repository:write permission."""
        tool = TOOL_REGISTRY["git_checkout_file"]
        assert tool["required_permission"] == "repository:write"


class TestGitBranchTools:
    """Test git branch management tools."""

    def test_git_branch_list_exists(self):
        """Verify git_branch_list tool is registered."""
        assert "git_branch_list" in TOOL_REGISTRY

    def test_git_branch_list_permission(self):
        """Verify git_branch_list requires repository:read permission."""
        tool = TOOL_REGISTRY["git_branch_list"]
        assert tool["required_permission"] == "repository:read"

    def test_git_branch_create_exists(self):
        """Verify git_branch_create tool is registered."""
        assert "git_branch_create" in TOOL_REGISTRY

    def test_git_branch_create_schema_requires_branch_name(self):
        """Verify git_branch_create requires branch_name."""
        tool = TOOL_REGISTRY["git_branch_create"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "branch_name": "feature/new-feature"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_branch_create_permission(self):
        """Verify git_branch_create requires repository:write permission."""
        tool = TOOL_REGISTRY["git_branch_create"]
        assert tool["required_permission"] == "repository:write"

    def test_git_branch_switch_exists(self):
        """Verify git_branch_switch tool is registered."""
        assert "git_branch_switch" in TOOL_REGISTRY

    def test_git_branch_switch_schema_requires_branch_name(self):
        """Verify git_branch_switch requires branch_name."""
        tool = TOOL_REGISTRY["git_branch_switch"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "branch_name": "main"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_branch_switch_permission(self):
        """Verify git_branch_switch requires repository:write permission."""
        tool = TOOL_REGISTRY["git_branch_switch"]
        assert tool["required_permission"] == "repository:write"

    def test_git_branch_delete_exists(self):
        """Verify git_branch_delete tool is registered."""
        assert "git_branch_delete" in TOOL_REGISTRY

    def test_git_branch_delete_schema_requires_confirmation(self):
        """Verify git_branch_delete requires branch_name and confirmation_token."""
        tool = TOOL_REGISTRY["git_branch_delete"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "branch_name": "old-feature",
            "confirmation_token": "CONFIRM_DELETE_BRANCH"
        }
        validate(instance=valid_input, schema=schema)

    def test_git_branch_delete_permission(self):
        """Verify git_branch_delete requires repository:admin permission."""
        tool = TOOL_REGISTRY["git_branch_delete"]
        assert tool["required_permission"] == "repository:admin"
