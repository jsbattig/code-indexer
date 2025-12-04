"""Unit tests for grep command generation and result parsing.

FILE: tests/unit/global_repos/test_regex_search_grep.py
GOAL: Test grep fallback functionality for RegexSearchService
"""

import pytest
from unittest.mock import MagicMock, patch
from code_indexer.global_repos.regex_search import RegexSearchService


@pytest.fixture
def test_repo(tmp_path):
    """Create a test repository structure."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    (repo_path / "src").mkdir()
    (repo_path / "src" / "main.py").write_text("def func():\n    pass\n")
    return repo_path


@pytest.fixture
def grep_service(test_repo):
    """Create service with grep engine."""
    with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

        def which_side_effect(cmd):
            return "/usr/bin/grep" if cmd == "grep" else None

        mock_which.side_effect = which_side_effect
        return RegexSearchService(test_repo)


class TestGrepCommandGeneration:
    """Test grep command generation."""

    def test_basic_grep_command(self, grep_service, test_repo):
        """Test basic grep search command."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            grep_service.search("pattern")
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "grep"
            assert "-rn" in cmd
            assert "-E" in cmd
            assert "pattern" in cmd

    def test_case_insensitive_flag_grep(self, grep_service):
        """Test case insensitive search adds -i flag for grep."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            grep_service.search("pattern", case_sensitive=False)
            cmd = mock_run.call_args[0][0]
            assert "-i" in cmd

    def test_context_lines_flag_grep(self, grep_service):
        """Test context lines adds -C flag for grep."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            grep_service.search("pattern", context_lines=2)
            cmd = mock_run.call_args[0][0]
            assert "-C" in cmd
            assert "2" in cmd

    def test_include_patterns_flag_grep(self, grep_service):
        """Test include patterns add --include flags for grep."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            grep_service.search("pattern", include_patterns=["*.py"])
            cmd = mock_run.call_args[0][0]
            assert "--include" in cmd
            assert "*.py" in cmd

    def test_exclude_patterns_flag_grep(self, grep_service):
        """Test exclude patterns add --exclude flags for grep."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            grep_service.search("pattern", exclude_patterns=["*.test.py"])
            cmd = mock_run.call_args[0][0]
            assert "--exclude" in cmd
            assert "*.test.py" in cmd


class TestGrepResultParsing:
    """Test grep plain text result parsing."""

    def test_parses_grep_output_format(self, grep_service, test_repo):
        """Test parsing grep file:line:content format."""
        grep_output = f"{test_repo}/src/main.py:1:def authenticate_user():\n"
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output, stderr="", returncode=0
            )
            result = grep_service.search("def")
        assert result.total_matches == 1
        assert result.matches[0].file_path == "src/main.py"
        assert result.matches[0].line_number == 1
        assert result.matches[0].line_content == "def authenticate_user():"
        assert result.matches[0].column == 1

    def test_parses_multiple_grep_matches(self, grep_service, test_repo):
        """Test parsing multiple grep matches."""
        grep_output = (
            f"{test_repo}/src/main.py:1:def func1():\n"
            f"{test_repo}/src/utils.py:2:def func2():\n"
        )
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output, stderr="", returncode=0
            )
            result = grep_service.search("def")
        assert result.total_matches == 2
        assert result.matches[0].file_path == "src/main.py"
        assert result.matches[1].file_path == "src/utils.py"

    def test_grep_column_defaults_to_1(self, grep_service, test_repo):
        """Test grep column defaults to 1 (grep doesn't provide column)."""
        grep_output = f"{test_repo}/src/main.py:5:    def func():\n"
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output, stderr="", returncode=0
            )
            result = grep_service.search("def")
        assert result.matches[0].column == 1

    def test_grep_handles_no_matches(self, grep_service):
        """Test grep handles no matches gracefully."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            result = grep_service.search("nonexistent")
        assert result.total_matches == 0
        assert len(result.matches) == 0

    def test_grep_max_results_truncates(self, grep_service, test_repo):
        """Test grep results are truncated at max_results."""
        grep_output = ""
        for i in range(10):
            grep_output += f"{test_repo}/file{i}.py:{i + 1}:def func{i}():\n"
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=grep_output, stderr="", returncode=0
            )
            result = grep_service.search("def", max_results=5)
        assert result.total_matches == 10
        assert len(result.matches) == 5
        assert result.truncated is True
