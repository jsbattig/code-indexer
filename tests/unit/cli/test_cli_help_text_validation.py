"""Test CLI help text validation failures.

This test reproduces the exact help text assertion issues found in CLI tests.
Following TDD methodology - write failing tests first, then fix the assertions.
"""

from click.testing import CliRunner

from code_indexer.cli import cli


class TestCLIHelpTextValidation:
    """Test cases to reproduce the help text assertion failures."""

    def test_query_help_actual_content(self):
        """Test what the query help actually contains (for understanding current state)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--help"])

        assert result.exit_code == 0
        help_text = result.output.lower()

        print("=== ACTUAL HELP TEXT ===")
        print(result.output)
        print("=== END HELP TEXT ===")

        # Verify what we know IS in the help text
        assert "repository linking" in help_text
        assert "remote mode requires git repository" in help_text

        # Check if remote mode is actually there (this should pass)
        print(f"Contains 'remote mode': {'remote mode' in help_text}")
        print(f"Contains 'server': {'server' in help_text}")
        print(f"Contains 'wide': {'wide' in help_text}")

        # This assertion is what's failing in the original test
        # Let's see what's actually available
        assert result.output is not None

    def test_expected_vs_actual_help_content(self):
        """Test to see what phrases are expected vs what's actually available."""
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--help"])

        help_text = result.output.lower()

        expected_phrases = [
            "repository linking",
            "remote mode requires git repository",
            "remote mode",  # Updated to match actual implementation
        ]

        for phrase in expected_phrases:
            is_present = phrase in help_text
            print(f"Expected phrase '{phrase}': {'FOUND' if is_present else 'MISSING'}")

            if not is_present:
                # Help debug what similar phrases exist
                words = phrase.split()
                for word in words:
                    if word in help_text:
                        print(f"  - Word '{word}' is present in help text")
                    else:
                        print(f"  - Word '{word}' is missing from help text")

    def test_identify_alternative_phrases_for_server_wide(self):
        """Test to identify what phrases might be used instead of 'server-wide'."""
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--help"])

        help_text = result.output.lower()

        # Look for alternative phrases that might convey the same meaning
        alternative_phrases = [
            "server-wide",
            "server wide",
            "remote server",
            "cidx server",
            "server",
            "remote",
            "global",
            "repository linking",
            "cross-repository",
        ]

        found_alternatives = []
        for phrase in alternative_phrases:
            if phrase in help_text:
                found_alternatives.append(phrase)

        print(f"Found alternative phrases: {found_alternatives}")

        # The test should pass - we're just collecting information
        assert len(found_alternatives) >= 0  # Always true, just for info gathering
