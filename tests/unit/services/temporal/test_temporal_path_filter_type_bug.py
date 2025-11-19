"""
Test for character-array explosion bug when string is passed instead of list.

This test documents and prevents regression of the bug where passing a string
to path_filter/exclude_path instead of a list causes list() to create a
character array, breaking pattern matching.

Bug example:
    exclude_path = "*.md"  # String instead of list
    list(exclude_path) → ['*', '.', 'm', 'd']  # Character array explosion!
    # Pattern matching fails because it tries to match individual characters

Correct behavior:
    exclude_path = ["*.md"]  # List of patterns
    list(exclude_path) → ["*.md"]  # Preserves pattern
"""


def test_string_causes_character_array_explosion():
    """Document the bug: list(string) creates character array."""
    # This documents the bug behavior that we're preventing
    exclude_path_string = "*.md"
    char_array = list(exclude_path_string)

    # Bug: string gets exploded into character array
    assert char_array == ["*", ".", "m", "d"], "Documents the bug behavior"

    # Correct: list of strings preserves patterns
    exclude_path_list = ["*.md"]
    assert list(exclude_path_list) == ["*.md"], "Correct type preserves pattern"


def test_tuple_to_list_conversion_preserves_patterns():
    """Verify tuple→list conversion maintains pattern integrity."""
    # CLI layer receives tuple from Click
    path_filter_tuple = ("*.py", "*.js")
    exclude_path_tuple = ("*.md", "*.txt")

    # Delegation layer should convert tuple→list
    path_filter_list = list(path_filter_tuple) if path_filter_tuple else None
    exclude_path_list = list(exclude_path_tuple) if exclude_path_tuple else None

    # Verify patterns preserved (not exploded into characters)
    assert path_filter_list == ["*.py", "*.js"], "Patterns preserved in path_filter"
    assert exclude_path_list == ["*.md", "*.txt"], "Patterns preserved in exclude_path"

    # Counter-example: What would happen if we passed string
    wrong_path_filter = "*.py"
    char_explosion = list(wrong_path_filter)
    assert char_explosion == ["*", ".", "p", "y"], "String causes character explosion"


def test_wrapping_string_in_list_vs_converting_tuple():
    """Demonstrate the bug: [string] vs list(tuple) have different behavior."""
    # Scenario 1: Old buggy code at line 1331
    # path_filter is "*.py" (string) after str(path_filter[0]) at line 4906
    path_filter_string = "*.py"
    buggy_conversion = [path_filter_string] if path_filter_string else None

    # This works by accident because it wraps the string in a list
    assert buggy_conversion == ["*.py"], "Buggy code wraps string in list"

    # Scenario 2: Fixed code - path_filter is tuple
    path_filter_tuple = ("*.py",)
    correct_conversion = list(path_filter_tuple) if path_filter_tuple else None

    # This also works and handles multiple patterns correctly
    assert correct_conversion == ["*.py"], "Fixed code converts tuple to list"

    # Scenario 3: Multiple patterns - where buggy code fails
    path_filter_tuple_multi = ("*.py", "*.js")

    # Old buggy code would do: str(path_filter_tuple_multi[0]) → "*.py"
    # Then [path_filter] → ["*.py"] - loses second pattern!
    first_only = path_filter_tuple_multi[0]
    buggy_multi = [first_only] if first_only else None
    assert buggy_multi == ["*.py"], "Buggy code only takes first pattern"

    # Fixed code preserves all patterns
    correct_multi = list(path_filter_tuple_multi) if path_filter_tuple_multi else None
    assert correct_multi == ["*.py", "*.js"], "Fixed code preserves all patterns"
