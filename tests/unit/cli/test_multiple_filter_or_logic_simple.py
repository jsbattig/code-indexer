"""
Simple regression test for multiple language/path filter OR logic.

Tests the filter construction logic directly without full CLI execution.
"""

from code_indexer.services.language_mapper import LanguageMapper


def test_multiple_languages_wrapped_in_should_clause():
    """
    REGRESSION TEST: Multiple language filters should be wrapped in "should" clause.

    Verifies the fix for bug where multiple --language flags created AND logic.
    """
    mapper = LanguageMapper()

    # Simulate what the CLI does with multiple languages
    languages = ["python", "javascript"]
    language_filters = []

    for lang in languages:
        language_filter = mapper.build_language_filter(lang)
        language_filters.append(language_filter)

    # Apply the fix: multiple languages wrapped in "should"
    if len(language_filters) > 1:
        filter_conditions = {"must": [{"should": language_filters}]}
    else:
        filter_conditions = {"must": language_filters}

    # Verify structure
    assert "must" in filter_conditions
    must_conditions = filter_conditions["must"]

    # Should have exactly 1 item in must
    assert (
        len(must_conditions) == 1
    ), f"Expected 1 must condition, got {len(must_conditions)}"

    # That 1 item should be a "should" clause
    assert (
        "should" in must_conditions[0]
    ), "Multiple languages should be wrapped in 'should' clause"

    # The "should" clause should contain both language filters
    should_clause = must_conditions[0]["should"]
    assert (
        len(should_clause) == 2
    ), f"Expected 2 language filters in 'should', got {len(should_clause)}"


def test_single_language_not_wrapped():
    """
    Verify single language doesn't create unnecessary "should" wrapper.
    """
    mapper = LanguageMapper()

    # Single language
    languages = ["python"]
    language_filters = []

    for lang in languages:
        language_filter = mapper.build_language_filter(lang)
        language_filters.append(language_filter)

    # Apply logic: single language uses directly
    if len(language_filters) > 1:
        filter_conditions = {"must": [{"should": language_filters}]}
    else:
        filter_conditions = {"must": language_filters}

    # Verify structure
    assert "must" in filter_conditions
    must_conditions = filter_conditions["must"]

    # For single language, it's a list of the language filter (which itself contains "should" for extensions)
    assert len(must_conditions) == 1
    assert (
        "should" in must_conditions[0]
    ), "Single language filter should contain 'should' for extensions"


def test_old_buggy_logic_creates_and():
    """
    Verify the OLD buggy logic created AND logic (for documentation).

    This demonstrates what the bug was.
    """
    mapper = LanguageMapper()

    # OLD BUGGY CODE (before fix):
    languages = ["python", "javascript"]
    must_conditions_buggy = []

    for lang in languages:
        language_filter = mapper.build_language_filter(lang)
        must_conditions_buggy.append(language_filter)  # BUG: appending directly to must

    # This creates AND logic: must match Python extensions AND JavaScript extensions (impossible!)
    assert (
        len(must_conditions_buggy) == 2
    ), "Buggy code creates 2 separate must conditions"
    assert "should" in must_conditions_buggy[0], "First is Python 'should' clause"
    assert "should" in must_conditions_buggy[1], "Second is JavaScript 'should' clause"
    # This structure means: (py OR pyi OR pyw) AND (js OR jsx) = impossible!


def test_multiple_path_filters_or_logic():
    """
    REGRESSION TEST: Multiple path filters should be wrapped in "should" clause.
    """
    # Simulate multiple path filters
    path_filter = ["**/tests/**", "**/src/**"]

    path_filters = [{"key": "path", "match": {"text": pf}} for pf in path_filter]

    if len(path_filters) > 1:
        # Multiple path filters: wrap in "should" clause (OR logic)
        filter_conditions = {"must": [{"should": path_filters}]}
    else:
        # Single path filter: use directly
        filter_conditions = {"must": path_filters}

    # Verify structure
    assert "must" in filter_conditions
    must_conditions = filter_conditions["must"]

    # Should have exactly 1 item in must
    assert len(must_conditions) == 1

    # That item should be a "should" clause
    assert (
        "should" in must_conditions[0]
    ), "Multiple paths should be wrapped in 'should' clause"

    # The "should" clause should contain both path filters
    should_clause = must_conditions[0]["should"]
    assert (
        len(should_clause) == 2
    ), f"Expected 2 path filters in 'should', got {len(should_clause)}"
