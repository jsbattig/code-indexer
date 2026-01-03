"""Unit tests for RegexSearchService initialization and error handling.

Tests the regex search service initialization and error scenarios.

FILE: tests/unit/global_repos/test_regex_search.py
GOAL: Test RegexSearchService init and error handling
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from code_indexer.global_repos.regex_search import (
    RegexSearchService,
    RegexMatch,
    RegexSearchResult,
)


@pytest.fixture
def test_repo(tmp_path):
    """Create a test repository structure."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    (repo_path / "src").mkdir()
    (repo_path / "src" / "main.py").write_text("def func():\n    pass\n")
    return repo_path


class TestRegexSearchServiceInit:
    """Test RegexSearchService initialization."""

    def test_init_detects_ripgrep(self, test_repo):
        """Test service initialization detects ripgrep availability."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/rg"
            service = RegexSearchService(test_repo)
            assert service._search_engine == "ripgrep"
            mock_which.assert_called_once_with("rg")

    def test_init_detects_grep_fallback(self, test_repo):
        """Test service initialization falls back to grep."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_side_effect(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_side_effect
            service = RegexSearchService(test_repo)
            assert service._search_engine == "grep"

    def test_init_raises_when_no_search_engine(self, test_repo):
        """Test error raised when neither ripgrep nor grep available."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:
            mock_which.return_value = None
            with pytest.raises(RuntimeError, match="Neither ripgrep nor grep found"):
                RegexSearchService(test_repo)

    def test_init_stores_repo_path(self, test_repo):
        """Test service stores repository path."""
        service = RegexSearchService(test_repo)
        assert service.repo_path == test_repo


class TestRegexMatchDataclass:
    """Test RegexMatch dataclass."""

    def test_creates_match_with_all_fields(self):
        """Test creating RegexMatch with all fields."""
        match = RegexMatch(
            file_path="src/main.py",
            line_number=10,
            column=5,
            line_content="def func():",
            context_before=["# comment"],
            context_after=["    pass"],
        )
        assert match.file_path == "src/main.py"
        assert match.line_number == 10
        assert match.column == 5

    def test_default_context_is_empty(self):
        """Test default context lists are empty."""
        match = RegexMatch(
            file_path="test.py", line_number=1, column=1, line_content="content"
        )
        assert match.context_before == []
        assert match.context_after == []


class TestRegexSearchResultDataclass:
    """Test RegexSearchResult dataclass."""

    def test_creates_result_with_all_fields(self):
        """Test creating RegexSearchResult with all fields."""
        match = RegexMatch(
            file_path="test.py", line_number=1, column=1, line_content="test"
        )
        result = RegexSearchResult(
            matches=[match],
            total_matches=10,
            truncated=True,
            search_engine="ripgrep",
            search_time_ms=15.5,
        )
        assert len(result.matches) == 1
        assert result.total_matches == 10
        assert result.truncated is True


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def ripgrep_service(self, test_repo):
        """Create service with ripgrep engine."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/rg"
            return RegexSearchService(test_repo)

    @pytest.mark.skip(reason="Requires complex mocking of SubprocessExecutor - integration test covers this")
    @pytest.mark.asyncio
    async def test_handles_no_matches_gracefully(self, ripgrep_service):
        """Test handles no matches without error."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            result = await ripgrep_service.search("nonexistent_pattern")
        assert result.total_matches == 0
        assert result.truncated is False

    @pytest.mark.skip(reason="Requires complex mocking of SubprocessExecutor - integration test covers this")
    @pytest.mark.asyncio
    async def test_handles_malformed_json_line(self, ripgrep_service, test_repo):
        """Test handles malformed JSON gracefully."""
        rg_output = (
            "not valid json\n"
            + json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": str(test_repo / "test.py")},
                        "line_number": 1,
                        "lines": {"text": "content\n"},
                        "submatches": [{"start": 0, "end": 7}],
                    },
                }
            )
            + "\n"
        )
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=rg_output, stderr="", returncode=0)
            result = await ripgrep_service.search("content")
        assert result.total_matches == 1

    @pytest.mark.asyncio
    async def test_raises_for_nonexistent_path(self, ripgrep_service):
        """Test error raised for nonexistent path."""
        with pytest.raises(ValueError, match="Path does not exist"):
            await ripgrep_service.search("pattern", path="nonexistent")
