"""
Tests for set-claude-prompt functionality.

This module tests the functionality to inject CIDX semantic search instructions
into CLAUDE.md files for better Claude Code integration.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner

from code_indexer.services.claude_prompt_setter import ClaudePromptSetter
from code_indexer.cli import cli


class TestClaudePromptSetter:
    """Test cases for ClaudePromptSetter service."""

    def test_find_user_claude_file_exists(self):
        """Test finding user CLAUDE.md file when it exists."""
        with patch.object(Path, "exists", return_value=True):
            setter = ClaudePromptSetter()
            result = setter._find_user_claude_file()
            expected = Path.home() / ".claude" / "CLAUDE.md"
            assert result == expected

    def test_find_user_claude_file_not_exists(self):
        """Test finding user CLAUDE.md file when it doesn't exist."""
        with patch.object(Path, "exists", return_value=False):
            setter = ClaudePromptSetter()
            result = setter._find_user_claude_file()
            assert result is None

    def test_find_project_claude_file_current_dir(self):
        """Test finding CLAUDE.md in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_file = Path(tmpdir) / "CLAUDE.md"
            claude_file.write_text("# Test CLAUDE.md")

            setter = ClaudePromptSetter()
            result = setter._find_project_claude_file(Path(tmpdir))
            assert result == claude_file

    def test_find_project_claude_file_walk_up(self):
        """Test finding CLAUDE.md by walking up directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested directory structure
            root_dir = Path(tmpdir)
            nested_dir = root_dir / "project" / "src" / "deep"
            nested_dir.mkdir(parents=True)

            # Create CLAUDE.md in root
            claude_file = root_dir / "CLAUDE.md"
            claude_file.write_text("# Root CLAUDE.md")

            setter = ClaudePromptSetter()
            result = setter._find_project_claude_file(nested_dir)
            assert result == claude_file

    def test_find_project_claude_file_not_found(self):
        """Test when no CLAUDE.md is found in directory tree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = Path(tmpdir) / "project" / "src"
            nested_dir.mkdir(parents=True)

            setter = ClaudePromptSetter()
            result = setter._find_project_claude_file(nested_dir)
            assert result is None

    def test_detect_existing_cidx_section(self):
        """Test detecting existing CIDX section in CLAUDE.md."""
        content = """
# Project Instructions

Some existing content.

- CIDX SEMANTIC CODE SEARCH INTEGRATION

**SEMANTIC SEARCH PRIORITY**: Always use cidx.

More content after.
"""
        setter = ClaudePromptSetter()
        start, end = setter._detect_cidx_section(content)
        assert start is not None
        assert end is not None
        assert "CIDX SEMANTIC CODE SEARCH" in content[start:end]

    def test_detect_no_cidx_section(self):
        """Test when no CIDX section exists."""
        content = """
# Project Instructions

Some existing content without CIDX.
"""
        setter = ClaudePromptSetter()
        start, end = setter._detect_cidx_section(content)
        assert start is None
        assert end is None

    def test_insert_cidx_section_new_file(self):
        """Test inserting CIDX section into new/empty file."""
        setter = ClaudePromptSetter()
        mock_prompt = "🎯 SEMANTIC SEARCH TOOL\nTest prompt content"

        result = setter._insert_cidx_section("", mock_prompt)

        assert "CIDX SEMANTIC CODE SEARCH INTEGRATION" in result
        assert mock_prompt in result
        assert result.endswith("\n")

    def test_insert_cidx_section_existing_file(self):
        """Test inserting CIDX section into existing file."""
        existing_content = """# Project Rules

- Rule 1: Do this
- Rule 2: Do that

More content here.
"""
        setter = ClaudePromptSetter()
        mock_prompt = "🎯 SEMANTIC SEARCH TOOL\nTest prompt content"

        result = setter._insert_cidx_section(existing_content, mock_prompt)

        assert "Rule 1: Do this" in result  # Preserve existing content
        assert "CIDX SEMANTIC CODE SEARCH INTEGRATION" in result
        assert mock_prompt in result

    def test_replace_cidx_section(self):
        """Test replacing existing CIDX section."""
        content = """# Project Rules

- Rule 1: Do this

- CIDX SEMANTIC CODE SEARCH INTEGRATION

Old CIDX content here.
This should be replaced.

- Rule 2: More rules
"""
        setter = ClaudePromptSetter()
        mock_prompt = "🎯 NEW SEMANTIC SEARCH\nUpdated prompt content"

        result = setter._replace_cidx_section(content, mock_prompt)

        assert "Rule 1: Do this" in result  # Preserve before
        assert "Rule 2: More rules" in result  # Preserve after
        assert "Old CIDX content" not in result  # Remove old
        assert mock_prompt in result  # Add new

    def test_normalize_line_endings(self):
        """Test normalizing line endings to LF."""
        setter = ClaudePromptSetter()

        # Test CRLF to LF
        crlf_content = "Line 1\r\nLine 2\r\nLine 3\r\n"
        result = setter._normalize_line_endings(crlf_content)
        assert result == "Line 1\nLine 2\nLine 3\n"

        # Test mixed endings
        mixed_content = "Line 1\r\nLine 2\nLine 3\r"
        result = setter._normalize_line_endings(mixed_content)
        assert result == "Line 1\nLine 2\nLine 3\n"

    def test_set_user_prompt_new_file(self):
        """Test setting user prompt when file doesn't exist."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch("pathlib.Path.write_text") as mock_write,
        ):
            setter = ClaudePromptSetter()
            result = setter.set_user_prompt()

            assert result is True
            mock_mkdir.assert_called_once()
            mock_write.assert_called_once()

    def test_set_user_prompt_existing_file(self):
        """Test setting user prompt when file exists."""
        existing_content = "# Existing content\n\nSome rules here."

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value=existing_content),
            patch("pathlib.Path.write_text") as mock_write,
        ):
            setter = ClaudePromptSetter()
            result = setter.set_user_prompt()

            assert result is True
            mock_write.assert_called_once()
            written_content = mock_write.call_args[0][0]
            assert "Existing content" in written_content
            assert "CIDX SEMANTIC CODE SEARCH" in written_content

    def test_set_project_prompt_found(self):
        """Test setting project prompt when CLAUDE.md is found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_file = Path(tmpdir) / "CLAUDE.md"
            claude_file.write_text("# Project rules\n\nExisting content.")

            setter = ClaudePromptSetter()
            result = setter.set_project_prompt(Path(tmpdir))

            assert result is True
            updated_content = claude_file.read_text()
            assert "CIDX SEMANTIC CODE SEARCH" in updated_content
            assert "Existing content" in updated_content

    def test_set_project_prompt_not_found(self):
        """Test setting project prompt when no CLAUDE.md is found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            setter = ClaudePromptSetter()
            result = setter.set_project_prompt(Path(tmpdir))
            assert result is False

    def test_generate_cidx_prompt(self):
        """Test generating CIDX prompt content."""
        setter = ClaudePromptSetter()
        prompt = setter._generate_cidx_prompt()

        assert "ABSOLUTE REQUIREMENT" in prompt
        assert "cidx query" in prompt
        assert "--quiet" in prompt
        assert "Mandatory CIDX-First Workflow" in prompt


class TestSetClaudePromptCLI:
    """Test cases for set-claude-prompt CLI command."""

    def test_show_only_flag_displays_content(self):
        """Test --show-only flag displays prompt content without modifying files."""
        runner = CliRunner()

        # Run command with --show-only flag
        result = runner.invoke(cli, ["set-claude-prompt", "--show-only"])

        # Should succeed without error
        assert result.exit_code == 0

        # Should contain the prompt content
        assert "Generated CIDX prompt content" in result.output
        assert "CIDX SEMANTIC CODE SEARCH INTEGRATION" in result.output
        assert "ABSOLUTE REQUIREMENT" in result.output
        assert "cidx query" in result.output

        # Should not contain file modification messages
        assert "Setting CIDX prompt" not in result.output
        assert "prompt set in" not in result.output

    def test_show_only_with_user_prompt_fails(self):
        """Test --show-only with --user-prompt returns error."""
        runner = CliRunner()

        # Run command with conflicting flags
        result = runner.invoke(
            cli, ["set-claude-prompt", "--show-only", "--user-prompt"]
        )

        # Should fail with error
        assert result.exit_code == 1
        assert "Cannot use --show-only with --user-prompt" in result.output
        assert (
            "--show-only displays content without specifying target file"
            in result.output
        )

    def test_show_only_includes_section_header(self):
        """Test --show-only includes the section header as it would appear in CLAUDE.md."""
        runner = CliRunner()

        # Run command with --show-only flag
        result = runner.invoke(cli, ["set-claude-prompt", "--show-only"])

        # Should succeed
        assert result.exit_code == 0

        # Should include the section header
        assert "- CIDX SEMANTIC CODE SEARCH INTEGRATION" in result.output
