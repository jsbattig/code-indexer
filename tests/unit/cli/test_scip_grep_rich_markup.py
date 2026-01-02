"""
Unit tests for Rich markup injection vulnerability in grep-like output.

BUG: Grep-like commands crash when code content contains Rich markup patterns like [bold], [/tag], etc.

ROOT CAUSE: console.print() interprets code content as Rich markup when markup parameter is not disabled.

SOLUTION: Add markup=False to console.print() calls displaying code content with context lines.
"""

import pytest
from rich.console import Console
from rich.markup import MarkupError
from io import StringIO


def test_rich_markup_crash_without_protection():
    """
    Demonstrates Rich markup crash when printing code WITHOUT markup=False.

    This test proves that Rich will crash when code contains markup-like patterns
    (especially closing tags like [/tag]) unless we explicitly disable markup
    parsing with markup=False.
    """
    # Code with Rich markup closing tag pattern - this WILL crash
    # Pattern like [/(lth|ct|rth)/g] is interpreted as closing tag [/...]
    context_line = "    new: [/(lth|ct|rth)/g, /test/i],"

    output = StringIO()
    console = Console(file=output)

    # WITHOUT markup=False, this WILL crash
    with pytest.raises(MarkupError):
        console.print(context_line)  # VULNERABLE - crashes on [/...] pattern


def test_rich_markup_safe_with_markup_false():
    """
    Test that printing code with markup patterns succeeds when using markup=False.

    This test verifies the fix: using markup=False prevents Rich from interpreting
    code content as markup, allowing safe display of any code content.
    """
    # Code with Rich markup patterns that would crash without protection
    # Including the [/(lth|ct|rth)/g] pattern that definitely crashes
    context_before = [
        "const patterns = {",
        "    old: [/(foo|bar)/g],",
    ]

    matching_line = "    new: [/(lth|ct|rth)/g, /test/i],"

    context_after = [
        "};",
        "export default patterns;",
    ]

    # Test WITH markup=False (should succeed)
    output = StringIO()
    console = Console(file=output)

    # This should NOT crash - markup=False protects us
    for ctx_line in context_before:
        console.print(f"  [dim]{ctx_line}[/dim]", markup=False)

    console.print(f"  [bold]{matching_line}[/bold]", markup=False)

    for ctx_line in context_after:
        console.print(f"  [dim]{ctx_line}[/dim]", markup=False)

    result = output.getvalue()

    # Verify content is present (though styles won't be applied due to markup=False)
    assert "(foo|bar)" in result
    assert "(lth|ct|rth)" in result
    assert "[/(lth|ct|rth)/g" in result


def test_rich_markup_with_regex_patterns():
    """
    Test that regex patterns in code don't crash when printed with markup=False.
    """
    # JavaScript regex patterns that look like Rich markup
    context_lines = [
        "const patterns = {",
        "    old: [/(foo|bar)/g],",
        "    new: [/(lth|ct|rth)/g, /test/i],",
        "};",
    ]

    output = StringIO()
    console = Console(file=output)

    # Print with markup=False - should not crash
    for line in context_lines:
        console.print(f"  [dim]{line}[/dim]", markup=False)

    result = output.getvalue()

    # Verify regex patterns are present
    assert "(foo|bar)" in result
    assert "(lth|ct|rth)" in result
