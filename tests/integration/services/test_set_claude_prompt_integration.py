"""
Integration tests for set-claude-prompt functionality.

These tests verify the end-to-end functionality of setting CIDX prompts
in real CLAUDE.md files with proper file handling and content preservation.
"""

import tempfile
from pathlib import Path

from code_indexer.services.claude_prompt_setter import ClaudePromptSetter


class TestClaudePromptSetterIntegration:
    """Integration tests for ClaudePromptSetter."""

    def test_real_file_operations_project_new_file(self):
        """Test creating a new project CLAUDE.md file with real file operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            setter = ClaudePromptSetter(project_dir)

            # Create a new CLAUDE.md file in the project
            claude_file = project_dir / "CLAUDE.md"
            claude_file.write_text(
                "# Project Instructions\n\n- Rule 1: Follow conventions\n"
            )

            # Set the prompt
            result = setter.set_project_prompt(project_dir)
            assert result is True

            # Verify the file was updated correctly
            content = claude_file.read_text()
            assert "Rule 1: Follow conventions" in content  # Preserved
            assert "CIDX SEMANTIC CODE SEARCH INTEGRATION" in content
            assert "🎯 SEMANTIC SEARCH TOOL" in content
            assert "cidx query" in content
            assert content.endswith("\n")  # Proper line ending

    def test_real_file_operations_replace_existing_section(self):
        """Test replacing existing CIDX section in real file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            setter = ClaudePromptSetter(project_dir)

            # Create CLAUDE.md with existing CIDX section
            initial_content = """# Project Instructions

- Rule 1: Follow conventions

- CIDX SEMANTIC CODE SEARCH INTEGRATION

Old CIDX instructions here.
This should be replaced completely.

- Rule 2: More project rules
"""
            claude_file = project_dir / "CLAUDE.md"
            claude_file.write_text(initial_content)

            # Set the prompt (should replace existing)
            result = setter.set_project_prompt(project_dir)
            assert result is True

            # Verify replacement
            content = claude_file.read_text()
            assert "Rule 1: Follow conventions" in content  # Before preserved
            assert "Rule 2: More project rules" in content  # After preserved
            assert "Old CIDX instructions" not in content  # Old removed
            assert "🎯 SEMANTIC SEARCH TOOL" in content  # New added
            assert (
                content.count("CIDX SEMANTIC CODE SEARCH INTEGRATION") == 1
            )  # Only one section

    def test_real_file_operations_preserve_formatting(self):
        """Test that existing file formatting is preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            setter = ClaudePromptSetter(project_dir)

            # Create file with specific formatting
            initial_content = """# My Project

## Section 1
- Item A
- Item B

## Section 2
Some paragraph text here.

- Another bullet point
"""
            claude_file = project_dir / "CLAUDE.md"
            claude_file.write_text(initial_content)

            # Set the prompt
            result = setter.set_project_prompt(project_dir)
            assert result is True

            # Verify formatting preserved
            content = claude_file.read_text()
            assert "## Section 1" in content
            assert "## Section 2" in content
            assert "- Item A" in content
            assert "Some paragraph text here." in content
            assert content.endswith("\n")

    def test_real_file_operations_line_ending_normalization(self):
        """Test that line endings are properly normalized to LF."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            setter = ClaudePromptSetter(project_dir)

            # Create file with CRLF line endings
            crlf_content = "# Project\r\n\r\nRule 1: Test\r\n"
            claude_file = project_dir / "CLAUDE.md"
            claude_file.write_bytes(crlf_content.encode("utf-8"))

            # Set the prompt
            result = setter.set_project_prompt(project_dir)
            assert result is True

            # Verify normalized to LF
            raw_content = claude_file.read_bytes()
            content_str = raw_content.decode("utf-8")

            assert "\r\n" not in content_str  # No CRLF
            assert "\r" not in content_str  # No standalone CR
            assert "Rule 1: Test" in content_str  # Content preserved
            assert content_str.endswith("\n")  # Ends with LF

    def test_walk_up_directory_tree_integration(self):
        """Test walking up directory tree to find CLAUDE.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)

            # Create nested directory structure
            deep_dir = root_dir / "project" / "src" / "components"
            deep_dir.mkdir(parents=True)

            # Create CLAUDE.md at root level
            claude_file = root_dir / "CLAUDE.md"
            claude_file.write_text("# Root Project\n\n- Root rule\n")

            # Set prompt from deep directory
            setter = ClaudePromptSetter(deep_dir)
            result = setter.set_project_prompt(deep_dir)
            assert result is True

            # Verify the root file was updated
            content = claude_file.read_text()
            assert "Root rule" in content
            assert "CIDX SEMANTIC CODE SEARCH INTEGRATION" in content

    def test_no_claude_file_found_integration(self):
        """Test behavior when no CLAUDE.md file is found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            setter = ClaudePromptSetter(project_dir)

            # No CLAUDE.md file exists
            result = setter.set_project_prompt(project_dir)
            assert result is False

            # Verify no file was created
            claude_file = project_dir / "CLAUDE.md"
            assert not claude_file.exists()

    def test_generated_prompt_content_quality(self):
        """Test that generated prompt contains expected high-quality content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            setter = ClaudePromptSetter(project_dir)

            claude_file = project_dir / "CLAUDE.md"
            claude_file.write_text("# Test Project\n")

            # Set the prompt
            result = setter.set_project_prompt(project_dir)
            assert result is True

            content = claude_file.read_text()

            # Verify key instruction elements are present
            assert "SEMANTIC SEARCH TOOL" in content
            assert "YOUR PRIMARY CODE DISCOVERY METHOD" in content
            assert "WHEN TO USE CIDX QUERY" in content
            assert "PRACTICAL EXAMPLES" in content
            assert "--quiet" in content
            assert "cidx query" in content

            # Verify examples are present
            assert "authentication mechanisms" in content
            assert "error handling patterns" in content

            # Verify strategic guidance
            assert "STRATEGIC USAGE PATTERNS" in content
            assert "UNDERSTANDING SCORES" in content

    def test_multiple_operations_on_same_file(self):
        """Test multiple set operations on the same file maintain consistency."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            setter = ClaudePromptSetter(project_dir)

            claude_file = project_dir / "CLAUDE.md"
            claude_file.write_text("# Test Project\n\n- Initial rule\n")

            # First set operation
            result1 = setter.set_project_prompt(project_dir)
            assert result1 is True

            content_after_first = claude_file.read_text()
            first_cidx_count = content_after_first.count(
                "CIDX SEMANTIC CODE SEARCH INTEGRATION"
            )

            # Second set operation (should replace, not duplicate)
            result2 = setter.set_project_prompt(project_dir)
            assert result2 is True

            content_after_second = claude_file.read_text()
            second_cidx_count = content_after_second.count(
                "CIDX SEMANTIC CODE SEARCH INTEGRATION"
            )

            # Should still have exactly one section
            assert first_cidx_count == 1
            assert second_cidx_count == 1
            assert "Initial rule" in content_after_second  # Original content preserved
