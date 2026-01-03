"""Unit tests for ripgrep command generation and result parsing.

FILE: tests/unit/global_repos/test_regex_search_ripgrep.py
GOAL: Test ripgrep-specific functionality for RegexSearchService
"""

import pytest
import json
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
def ripgrep_service(test_repo):
    """Create service with ripgrep engine."""
    with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/rg"
        return RegexSearchService(test_repo)


class TestRipgrepCommandGeneration:
    """Test ripgrep command generation."""

    def test_basic_search_command(self, ripgrep_service, test_repo):
        """Test basic ripgrep search command."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            ripgrep_service.search("pattern")
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "rg"
            assert "--json" in cmd
            assert "pattern" in cmd
            assert str(test_repo) in cmd

    def test_case_insensitive_flag(self, ripgrep_service):
        """Test case insensitive search adds -i flag."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            ripgrep_service.search("pattern", case_sensitive=False)
            cmd = mock_run.call_args[0][0]
            assert "-i" in cmd

    def test_context_lines_flag(self, ripgrep_service):
        """Test context lines adds -C flag."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            ripgrep_service.search("pattern", context_lines=3)
            cmd = mock_run.call_args[0][0]
            assert "-C" in cmd
            assert "3" in cmd

    def test_include_patterns_flag(self, ripgrep_service):
        """Test include patterns add -g flags."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            ripgrep_service.search("pattern", include_patterns=["*.py", "*.js"])
            cmd = mock_run.call_args[0][0]
            assert cmd.count("-g") >= 2
            assert "*.py" in cmd
            assert "*.js" in cmd

    def test_exclude_patterns_flag(self, ripgrep_service):
        """Test exclude patterns add negated -g flags."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            ripgrep_service.search("pattern", exclude_patterns=["*.test.py"])
            cmd = mock_run.call_args[0][0]
            assert "!*.test.py" in cmd


class TestRipgrepResultParsing:
    """Test ripgrep JSON result parsing."""

    def test_parses_single_match(self, ripgrep_service, test_repo):
        """Test parsing single match from ripgrep JSON output."""
        rg_output = json.dumps(
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_repo / "src" / "main.py")},
                    "line_number": 1,
                    "lines": {"text": "def authenticate_user(username):\n"},
                    "submatches": [{"start": 4, "end": 21}],
                },
            }
        )
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=rg_output + "\n", stderr="", returncode=0
            )
            result = ripgrep_service.search("authenticate_user")
        assert result.total_matches == 1
        assert len(result.matches) == 1
        assert result.matches[0].file_path == "src/main.py"
        assert result.matches[0].line_number == 1
        assert result.matches[0].column == 5

    def test_parses_multiple_matches(self, ripgrep_service, test_repo):
        """Test parsing multiple matches from ripgrep."""
        matches = [
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_repo / "src" / "main.py")},
                    "line_number": 1,
                    "lines": {"text": "def func1():\n"},
                    "submatches": [{"start": 0, "end": 3}],
                },
            },
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_repo / "src" / "utils.py")},
                    "line_number": 2,
                    "lines": {"text": "def func2():\n"},
                    "submatches": [{"start": 0, "end": 3}],
                },
            },
        ]
        rg_output = "\n".join(json.dumps(m) for m in matches)
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=rg_output + "\n", stderr="", returncode=0
            )
            result = ripgrep_service.search("def")
        assert result.total_matches == 2
        assert len(result.matches) == 2

    def test_handles_context_lines(self, ripgrep_service, test_repo):
        """Test parsing context lines from ripgrep."""
        outputs = [
            {
                "type": "context",
                "data": {
                    "path": {"text": str(test_repo / "src" / "main.py")},
                    "line_number": 0,
                    "lines": {"text": "# before context\n"},
                },
            },
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_repo / "src" / "main.py")},
                    "line_number": 1,
                    "lines": {"text": "def func():\n"},
                    "submatches": [{"start": 0, "end": 3}],
                },
            },
            {
                "type": "context",
                "data": {
                    "path": {"text": str(test_repo / "src" / "main.py")},
                    "line_number": 2,
                    "lines": {"text": "    pass\n"},
                },
            },
        ]
        rg_output = "\n".join(json.dumps(o) for o in outputs)
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=rg_output + "\n", stderr="", returncode=0
            )
            result = ripgrep_service.search("def", context_lines=1)
        assert len(result.matches) == 1
        match = result.matches[0]
        assert "# before context" in match.context_before
        assert "    pass" in match.context_after


class TestResultTruncation:
    """Test result truncation with max_results."""

    def test_truncates_results(self, ripgrep_service, test_repo):
        """Test results are truncated at max_results."""
        matches = []
        for i in range(10):
            matches.append(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": str(test_repo / f"file{i}.py")},
                        "line_number": i + 1,
                        "lines": {"text": f"def func{i}():\n"},
                        "submatches": [{"start": 0, "end": 3}],
                    },
                }
            )
        rg_output = "\n".join(json.dumps(m) for m in matches)
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=rg_output + "\n", stderr="", returncode=0
            )
            result = ripgrep_service.search("def", max_results=5)
        assert result.total_matches == 10
        assert len(result.matches) == 5
        assert result.truncated is True

    def test_no_truncation_when_under_limit(self, ripgrep_service, test_repo):
        """Test no truncation when results under max_results."""
        matches = [
            {
                "type": "match",
                "data": {
                    "path": {"text": str(test_repo / "file.py")},
                    "line_number": 1,
                    "lines": {"text": "def func():\n"},
                    "submatches": [{"start": 0, "end": 3}],
                },
            }
        ]
        rg_output = json.dumps(matches[0])
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=rg_output + "\n", stderr="", returncode=0
            )
            result = ripgrep_service.search("def", max_results=100)
        assert result.total_matches == 1
        assert len(result.matches) == 1
        assert result.truncated is False


class TestPathFiltering:
    """Test path-based filtering."""

    def test_search_in_subdirectory(self, ripgrep_service, test_repo):
        """Test searching within subdirectory."""
        (test_repo / "src").mkdir(exist_ok=True)
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            ripgrep_service.search("pattern", path="src")
            cmd = mock_run.call_args[0][0]
            assert str(test_repo / "src") in cmd


class TestSearchTiming:
    """Test search timing measurement."""

    def test_measures_search_time(self, ripgrep_service):
        """Test search time is measured."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            result = ripgrep_service.search("pattern")
        assert result.search_time_ms >= 0
