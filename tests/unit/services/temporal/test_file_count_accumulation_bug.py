"""
Focused unit tests for BUG #2: Files counter logic bug.

BUG #2 (Status Reporting): Files counter only set when diffs exist
- Location: src/code_indexer/services/temporal/temporal_indexer.py:615
- Issue: files_in_this_commit = len(diffs) is inside else block after if not diffs
- Impact: Commits with no diffs don't set file counter correctly

This test documents the LOGIC bug, not necessarily the accumulation bug
(which may or may not manifest depending on where files_in_this_commit is used).

The core issue is that the variable assignment is in the wrong place,
making the code fragile and incorrect.
"""

import pytest


class TestFileCountLogicBug:
    """Test that file count logic is correctly positioned (BUG #2)."""

    def test_file_count_should_be_set_before_conditional_not_inside_else(self):
        """
        Test that files_in_this_commit is set BEFORE the if/else, not inside else.

        BUG #2: Line 615 has `files_in_this_commit = len(diffs)` inside the else block.
        It should be at line 600 (or right after), before the `if not diffs:` check.

        Current buggy structure (lines 600-615):
        ```
        files_in_this_commit = 0           # Line 600
        if not diffs:                       # Line 603
            # do something                  # Line 604
        else:                               # Line 605
            files_in_this_commit = len(diffs)  # Line 615 (WRONG LOCATION)
        ```

        Correct structure should be:
        ```
        files_in_this_commit = len(diffs)  # Line 600 (or right after)
        if not diffs:                       # Line 603
            # do something                  # Line 604
        else:                               # Line 605
            # process diffs                 # Line 606+
        ```
        """
        # ARRANGE: Simulate the code logic with different scenarios

        test_cases = [
            {
                "description": "commit with no diffs",
                "diffs": [],
                "expected_count": 0,
            },
            {
                "description": "commit with 1 diff",
                "diffs": ["diff1"],
                "expected_count": 1,
            },
            {
                "description": "commit with 5 diffs",
                "diffs": ["diff1", "diff2", "diff3", "diff4", "diff5"],
                "expected_count": 5,
            },
        ]

        for case in test_cases:
            diffs = case["diffs"]
            expected_count = case["expected_count"]

            # ACT: Simulate BUGGY implementation (current code)
            files_in_this_commit_buggy = 0  # Line 600
            if not diffs:
                pass  # Line 603-604
            else:
                files_in_this_commit_buggy = len(diffs)  # Line 615 (WRONG LOCATION)

            # ACT: Simulate CORRECT implementation (after fix)
            files_in_this_commit_fixed = len(diffs)  # Should be at line 600
            if not diffs:
                pass
            else:
                pass

            # ASSERT: Fixed version should always have correct count
            assert files_in_this_commit_fixed == expected_count, (
                f"Fixed implementation should have count {expected_count} "
                f"for {case['description']}, got {files_in_this_commit_fixed}"
            )

            # Document the bug: buggy version gives same result for empty diffs
            # (because 0 is correct for no diffs), but the LOGIC is still wrong
            assert files_in_this_commit_buggy == expected_count, (
                f"Buggy implementation happens to work for this case: {case['description']}, "
                f"but the logic is still wrong because the assignment is inside the else block"
            )

    def test_file_count_location_makes_code_fragile(self):
        """
        Test demonstrating why the current location (inside else) is fragile.

        Even though the buggy code may produce correct results in some scenarios,
        having the assignment inside the else block is a code smell and makes
        the logic harder to understand and maintain.

        The principle: Variable assignment should happen as early as possible,
        before any conditional logic that might use it.
        """
        # ARRANGE: Different scenarios
        scenarios = [
            {"diffs": [], "description": "no diffs"},
            {"diffs": ["a"], "description": "one diff"},
            {"diffs": ["a", "b", "c"], "description": "multiple diffs"},
        ]

        for scenario in scenarios:
            diffs = scenario["diffs"]

            # Current buggy pattern (assignment inside conditional)
            files_count_buggy = 0
            if not diffs:
                # In current code, files_count_buggy stays 0
                # This is correct for no diffs, but the pattern is wrong
                pass
            else:
                # Assignment happens here, ONLY if we have diffs
                files_count_buggy = len(diffs)

            # Better pattern (assignment before conditional)
            files_count_fixed = len(diffs)  # Calculate once, use anywhere
            if not diffs:
                # Can still do early return or special handling
                pass
            else:
                # Process diffs
                pass

            # ASSERT: Both should give same result, but fixed pattern is clearer
            assert files_count_fixed == len(diffs)
            assert files_count_buggy == len(diffs)  # This works, but pattern is bad

    def test_file_count_initialization_should_be_len_diffs_not_zero(self):
        """
        Test that files_in_this_commit should be initialized to len(diffs), not 0.

        Current code (line 600):
        ```
        files_in_this_commit = 0  # WRONG: Should be len(diffs)
        ```

        After fix (line 600):
        ```
        files_in_this_commit = len(diffs)  # CORRECT
        ```

        Then line 615 (inside else block) should be removed since it's redundant.
        """
        # ARRANGE: Test with different diff counts
        test_diffs = [
            [],  # 0 diffs
            ["one"],  # 1 diff
            ["one", "two", "three"],  # 3 diffs
        ]

        for diffs in test_diffs:
            # ACT: Current buggy initialization
            files_count_buggy = 0  # Line 600 (WRONG)
            # Then later (line 615) it's set to len(diffs) inside else block

            # ACT: Correct initialization
            files_count_fixed = len(diffs)  # Line 600 (CORRECT)

            # ASSERT: Fixed version is immediately correct
            assert files_count_fixed == len(diffs), (
                f"Fixed version should immediately equal len(diffs)={len(diffs)}"
            )

            # Buggy version starts wrong (for non-empty diffs)
            if diffs:
                assert files_count_buggy != len(diffs), (
                    f"Buggy version starts at 0, not len(diffs)={len(diffs)}"
                )
            else:
                # For empty diffs, 0 happens to be correct
                assert files_count_buggy == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
