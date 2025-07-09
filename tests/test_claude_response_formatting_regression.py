"""
Test for Claude response formatting regression.

This test reproduces and verifies fixes for Claude response formatting issues
that may have been introduced when fixing dry-run prompt display.
"""

from .conftest import local_temporary_directory

from pathlib import Path

from src.code_indexer.services.claude_integration import ClaudeIntegrationService


def test_claude_response_should_preserve_formatting():
    """Test that Claude responses maintain proper Claude Code style formatting when displayed."""

    # Create a test ClaudeIntegrationService
    with local_temporary_directory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a simple test project
        (temp_path / "main.py").write_text("print('hello')")

        service = ClaudeIntegrationService(
            codebase_dir=temp_path, project_name="test_project"
        )

        # Mock a Claude response with various formatting elements
        mock_claude_response = """## Analysis Results

This is a **bold** statement with *italic* text.

### Code Examples

Here's some code:
```python
def hello():
    return "world"
```

### Lists

1. First item with `inline code`
2. Second item
   - Nested bullet point
   - Another nested point

**Key findings:**
- The code does something important
- It has proper structure
"""

        # Test the _render_content_with_file_links method which should handle formatting
        from io import StringIO
        from rich.console import Console

        # Capture console output
        string_io = StringIO()
        console = Console(file=string_io, force_terminal=False, width=80)

        # This should format the content like Claude Code (left-aligned, readable)
        result = service._render_content_with_file_links(mock_claude_response, console)

        # Get the captured output
        output = string_io.getvalue()

        # Verify that it processed the content (should return True)
        assert result is True, "Should successfully process the content"

        # Verify output is not empty
        assert len(output.strip()) > 0, "Should produce formatted output"

        # The formatting should be like Claude Code:
        # - Headers should be left-aligned and readable
        # - Bold text should be styled but not centered
        # - Code blocks should be preserved
        # - Lists should be left-aligned

        # Check that headers are present and formatted (not centered)
        lines = output.split("\n")
        header_lines = [
            line
            for line in lines
            if line.strip().startswith("Analysis Results") or "Code Examples" in line
        ]
        assert len(header_lines) > 0, "Should have formatted headers"

        # Headers should not be centered (Claude Code style)
        for header_line in header_lines:
            # Should not have excessive leading/trailing spaces indicating centering
            stripped = header_line.strip()
            if stripped:
                # Should not be centered (would have lots of leading spaces)
                leading_spaces = len(header_line) - len(header_line.lstrip())
                assert (
                    leading_spaces < 20
                ), f"Header '{stripped}' appears to be centered with {leading_spaces} leading spaces"

        # Check that bold formatting is present but readable
        assert (
            "bold" in output.lower() or "**" in output
        ), "Should preserve bold text indicators"

        # Check that code blocks are preserved
        assert (
            "python" in output.lower()
        ), "Should preserve code block language indicators"


def test_claude_response_should_not_lose_markdown_structure():
    """Test that Claude responses preserve markdown structure in display."""

    # This test should verify that when we display Claude responses,
    # we don't lose important structural elements like:
    # - Headers (## ###)
    # - Code blocks (```)
    # - Lists (- 1.)
    # - Bold/italic (**text** *text*)
    # - Links ([text](url))

    # For now, this is a placeholder test that will need to be implemented
    # once we identify exactly how the formatting is being lost

    pass


def test_claude_streaming_response_preserves_formatting():
    """Test that streaming Claude responses maintain formatting."""

    # This test should verify that the streaming response handler
    # preserves formatting when processing chunks of Claude output

    pass
