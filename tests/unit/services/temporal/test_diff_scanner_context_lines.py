"""Unit tests for TemporalDiffScanner diff_context_lines parameter (Story #443 - AC2).

Tests that TemporalDiffScanner accepts and uses the diff_context_lines parameter.
"""

from unittest.mock import Mock, patch

from src.code_indexer.services.temporal.temporal_diff_scanner import TemporalDiffScanner


class TestDiffScannerContextLines:
    """Test TemporalDiffScanner context lines configuration."""

    def test_scanner_accepts_diff_context_lines_parameter(self, tmp_path):
        """AC2: TemporalDiffScanner accepts diff_context_lines parameter."""
        # Create scanner with custom diff_context_lines
        scanner = TemporalDiffScanner(
            codebase_dir=tmp_path,
            override_filter_service=None,
            diff_context_lines=10,
        )

        # Scanner should store the parameter
        assert hasattr(scanner, "diff_context_lines")
        assert scanner.diff_context_lines == 10

    @patch("subprocess.run")
    def test_scanner_uses_U_flag_in_git_show_command(self, mock_run, tmp_path):
        """AC2: TemporalDiffScanner uses -U flag with configured context lines."""
        # Mock git show response
        mock_run.return_value = Mock(stdout="", returncode=0)

        # Create scanner with diff_context_lines=7
        scanner = TemporalDiffScanner(
            codebase_dir=tmp_path,
            override_filter_service=None,
            diff_context_lines=7,
        )

        # Call get_diffs_for_commit
        scanner.get_diffs_for_commit("abc123")

        # Verify git show was called with -U7 flag
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]

        assert "git" in cmd
        assert "show" in cmd
        assert "-U7" in cmd or "--unified=7" in cmd
        assert "abc123" in cmd
