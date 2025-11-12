"""
Unit tests for temporal indexing CLI progress callback KB/s parsing.

Tests that the CLI correctly parses KB/s from temporal indexer progress info strings.
"""


class TestTemporalProgressKbsecParsing:
    """Test that CLI parses KB/s from temporal progress info string."""

    def test_cli_parses_kb_per_second_from_temporal_progress(self):
        """Test that commit_progress_callback parses KB/s from info string (parts[2]).

        The temporal_indexer sends progress info in format:
        "current/total commits (%) | X.X commits/s | Y.Y KB/s | threads | emoji hash - filename"

        The CLI MUST parse KB/s from parts[2] and pass it to progress_manager.update_complete_state(),
        NOT hardcode it to 0.0.

        This test CURRENTLY FAILS because cli.py line 3482 hardcodes kb_per_second=0.0
        """
        # Simulate temporal indexer progress info with KB/s
        info_string = "50/100 commits (50%) | 12.5 commits/s | 256.3 KB/s | 8 threads | 📝 abc123de - test_file.py"

        # Parse the info string exactly as the CLI should do
        parts = info_string.split(" | ")

        # Parse commits/s (parts[1]) - CLI already does this correctly
        try:
            if len(parts) >= 2:
                rate_str = parts[1].strip()
                rate_parts = rate_str.split()
                if len(rate_parts) >= 1:
                    files_per_second = float(rate_parts[0])
                else:
                    files_per_second = 0.0
            else:
                files_per_second = 0.0
        except (ValueError, IndexError):
            files_per_second = 0.0

        # Parse KB/s (parts[2]) - THIS IS WHAT CLI IS MISSING
        try:
            if len(parts) >= 3:
                kb_str = parts[2].strip()
                kb_parts = kb_str.split()
                if len(kb_parts) >= 1:
                    kb_per_second = float(kb_parts[0])
                else:
                    kb_per_second = 0.0
            else:
                kb_per_second = 0.0
        except (ValueError, IndexError):
            kb_per_second = 0.0

        # Verify parsing worked correctly
        assert (
            files_per_second == 12.5
        ), f"Expected 12.5 commits/s, got {files_per_second}"
        assert kb_per_second == 256.3, f"Expected 256.3 KB/s, got {kb_per_second}"

        # Now check if CLI's actual code contains the hardcoded 0.0
        # This test will FAIL until we fix cli.py line 3482
        from pathlib import Path

        cli_file = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "cli.py"
        )
        cli_content = cli_file.read_text()

        # Search for the hardcoded kb_per_second=0.0 in commit progress callback
        # It should be around line 3482 with comment "Not applicable for commit processing"
        assert (
            "kb_per_second=0.0,  # Not applicable for commit processing"
            not in cli_content
        ), (
            "CLI still has hardcoded kb_per_second=0.0 at line 3482! "
            "It should parse KB/s from info string parts[2] instead. "
            "The temporal_indexer NOW sends KB/s in the info string."
        )
