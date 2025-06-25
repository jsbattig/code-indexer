"""
Test Claude result formatting to ensure it matches Claude Code presentation style.

This test verifies that Claude function results are displayed with left-aligned,
clean formatting rather than centered sections and titles.
"""

import pytest
from rich.console import Console
from io import StringIO

from src.code_indexer.services.claude_tool_tracking import (
    ClaudePlanSummary,
    ToolUsageEvent,
)
from src.code_indexer.utils.status_display import (
    StatusDisplayManager,
    StatusDisplayMode,
)
from datetime import datetime


def test_claude_plan_summary_uses_left_aligned_formatting():
    """Test that ClaudePlanSummary generates left-aligned, non-centered output."""

    # Create some sample tool usage events
    events = [
        ToolUsageEvent(
            tool_name="Bash",
            operation_type="cidx_semantic_search",
            visual_cue="🔍✨",
            target="authentication",
            command_detail="Semantic search: 'authentication'",
            timestamp=datetime.now(),
            status="completed",
            duration=1.2,
        ),
        ToolUsageEvent(
            tool_name="Read",
            operation_type="file_operation",
            visual_cue="📖",
            target="src/auth.py",
            command_detail="Reading: src/auth.py",
            timestamp=datetime.now(),
            status="completed",
            duration=0.5,
        ),
    ]

    summary_generator = ClaudePlanSummary()
    summary = summary_generator.generate_complete_summary(events)

    # Check that the summary doesn't use centered formatting indicators
    # These patterns are problematic in the current implementation
    problematic_patterns = [
        "# ",  # Markdown headers that get centered by Rich
        "## ",  # Markdown sub-headers
        "### ",  # Markdown sub-sub-headers
    ]

    for pattern in problematic_patterns:
        assert (
            pattern not in summary
        ), f"Summary should not contain centered header pattern '{pattern}'"

    # Verify the summary contains expected content without centered formatting
    assert "Claude used 2 tools during analysis" in summary
    assert "✅ **Preferred Approach**" in summary
    assert "📊 Tool Usage Statistics" in summary

    # The summary should be plain text with emoji and formatting, not markdown headers
    lines = summary.split("\n")
    for line in lines:
        # No line should start with markdown header syntax
        assert not line.strip().startswith(
            "#"
        ), f"Line should not start with # (markdown header): {line}"


def test_status_display_manager_format_summary_avoids_centering():
    """Test that StatusDisplayManager.format_summary doesn't create centered output."""

    # Capture console output
    string_io = StringIO()
    console = Console(file=string_io, width=80, legacy_windows=False)

    status_manager = StatusDisplayManager(
        mode=StatusDisplayMode.ACTIVITY_LOG, console=console
    )

    # Test summary with problematic content that could be centered
    test_summary = """Claude used 2 tools during analysis:

- ✅ **Preferred Approach**: Used semantic search (1x) with `cidx` for intelligent code discovery
  - Semantic search: 'authentication'

- 📖 **Code Exploration**: Accessed 1 files for detailed analysis

📊 Tool Usage Statistics

Total Operations: 2
Tools Used: Bash, Read
Completed Successfully: 2
Total Execution Time: 1.70s
Average Duration: 0.85s

Operation Breakdown:

🔍✨ cidx_semantic_search: 1
📄 file_operation: 1"""

    # Format the summary
    status_manager.format_summary(
        test_summary, title="Claude's Problem-Solving Approach"
    )

    # Get the output
    output = string_io.getvalue()

    # Verify output doesn't contain excessive spacing or centering artifacts
    lines = output.split("\n")

    # Count indentation to detect centering (centered text would have unusual indentation)
    for line in lines:
        if line.strip():  # Only check non-empty lines
            leading_spaces = len(line) - len(line.lstrip())
            # Reasonable indentation for bullet points and structure is fine,
            # but excessive indentation (>10 spaces) suggests centering
            assert (
                leading_spaces <= 10
            ), f"Line appears to be over-indented (possibly centered): '{line}'"

    # Verify key content is present and properly formatted
    assert "🤖 Claude's Problem-Solving Approach" in output
    assert "─" * 80 in output  # Should have separator line
    assert "Total Operations: 2" in output
    assert "Operation Breakdown:" in output


def test_markdown_processing_for_readability_preserves_left_alignment():
    """Test that markdown processing doesn't introduce centering."""

    from src.code_indexer.utils.status_display import _process_markdown_for_readability

    # Test text with markdown that could be problematic
    test_markdown = """# Centered Header
## Sub Header
**Bold text** and normal text
- List item 1
- List item 2
[file link](file:///path/to/file.py)
[external link](https://example.com)"""

    processed = _process_markdown_for_readability(test_markdown)

    # The processed markdown should convert headers to simple text (no # symbols)
    assert (
        " Centered Header" in processed
    )  # Headers converted to simple text with space prefix
    assert "  Sub Header" in processed  # Sub-headers converted with double space prefix
    assert (
        "Bold text and normal text" in processed
    )  # Bold formatting removed for simplicity
    assert "[file link](file:///path/to/file.py)" in processed  # File links preserved
    # External links should be simplified for readability
    assert "external link (https://example.com)" in processed


@pytest.mark.integration
def test_full_claude_streaming_output_formatting():
    """Integration test for complete Claude result formatting workflow."""

    # This test would require a mock of the full Claude CLI streaming process
    # For now, we'll test the components that we can control

    string_io = StringIO()
    console = Console(file=string_io, width=80, legacy_windows=False)

    # Create a FreeScrollStreamDisplay (used in Claude streaming)
    from src.code_indexer.utils.status_display import FreeScrollStreamDisplay

    display = FreeScrollStreamDisplay(console=console)
    display.start("Claude Analysis")

    # Simulate some content updates
    test_content = """Based on my analysis of the codebase:

## Authentication System

The authentication is handled in `src/auth.py` with the following key components:

- **User validation**: Checks credentials against database
- **Token generation**: Creates JWT tokens for session management
- **Permission checking**: Validates user permissions for resources

### Implementation Details

The `authenticate_user()` function [located here](file:///src/auth.py:45) handles the core logic."""

    display.update_content(test_content)

    # Show final summary
    display.show_final_summary("Tool usage summary would go here")

    display.stop()

    output = string_io.getvalue()

    # Verify the output looks reasonable and isn't overly centered
    assert "🤖 Claude Analysis" in output
    assert "authentication is handled" in output
    assert "🤖 Claude's Problem-Solving Approach" in output

    # Check that content flows naturally without excessive formatting
    lines = output.split("\n")
    content_lines = [
        line for line in lines if line.strip() and not line.startswith("─")
    ]

    # Most content lines should start reasonably close to the left margin
    left_aligned_lines = 0
    for line in content_lines:
        if line.strip():
            leading_spaces = len(line) - len(line.lstrip())
            if leading_spaces <= 4:  # Allow some indentation for structure
                left_aligned_lines += 1

    # At least 70% of content should be left-aligned
    if content_lines:
        left_alignment_ratio = left_aligned_lines / len(content_lines)
        assert (
            left_alignment_ratio >= 0.7
        ), f"Too much content appears centered. Left-aligned ratio: {left_alignment_ratio}"
