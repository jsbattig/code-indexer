"""Unit tests for RegexSearchService initialization and error handling.

Tests the regex search service initialization and error scenarios.

FILE: tests/unit/global_repos/test_regex_search.py
GOAL: Test RegexSearchService init and error handling
"""

import pytest
import json
import shutil
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


class TestBuildGrepCommand:
    """Test _build_grep_command method."""

    @pytest.fixture
    def grep_service(self, test_repo):
        """Create service with grep engine."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_side_effect(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_side_effect
            return RegexSearchService(test_repo)

    def test_includes_h_flag_for_consistent_filename_output(self, grep_service):
        """Test grep command always includes -H flag to force filename output.

        The -H flag ensures grep outputs 'filename:line:content' format
        even when searching a single file, preventing parsing failures.
        """
        cmd = grep_service._build_grep_command(
            pattern="test",
            case_sensitive=True,
            context_lines=0,
            recursive=False,
            file_list=["single_file.py"],
        )

        assert (
            "-H" in cmd
        ), "Grep command must include -H flag for consistent filename output"
        assert cmd.index("-H") < cmd.index("test"), "-H flag must appear before pattern"

    def test_h_flag_present_with_single_file(self, grep_service):
        """Test -H flag is present when searching single file."""
        cmd = grep_service._build_grep_command(
            pattern="pattern",
            case_sensitive=True,
            context_lines=0,
            recursive=False,
            file_list=["one_file.txt"],
        )

        assert "-H" in cmd, "Must include -H flag for single file"

    def test_h_flag_present_with_multiple_files(self, grep_service):
        """Test -H flag is present when searching multiple files."""
        cmd = grep_service._build_grep_command(
            pattern="pattern",
            case_sensitive=True,
            context_lines=0,
            recursive=False,
            file_list=["file1.txt", "file2.txt", "file3.txt"],
        )

        assert "-H" in cmd, "Must include -H flag for multiple files"

    def test_h_flag_present_in_recursive_mode(self, grep_service):
        """Test -H flag is present in recursive mode."""
        cmd = grep_service._build_grep_command(
            pattern="pattern",
            case_sensitive=True,
            context_lines=0,
            recursive=True,
            file_list=None,
        )

        assert "-H" in cmd, "Must include -H flag in recursive mode"


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def ripgrep_service(self, test_repo):
        """Create service with ripgrep engine."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/rg"
            return RegexSearchService(test_repo)

    @pytest.mark.skip(
        reason="Requires complex mocking of SubprocessExecutor - integration test covers this"
    )
    @pytest.mark.asyncio
    async def test_handles_no_matches_gracefully(self, ripgrep_service):
        """Test handles no matches without error."""
        with patch("code_indexer.global_repos.regex_search.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1)
            result = await ripgrep_service.search("nonexistent_pattern")
        assert result.total_matches == 0
        assert result.truncated is False

    @pytest.mark.skip(
        reason="Requires complex mocking of SubprocessExecutor - integration test covers this"
    )
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


class TestGrepPathBasedIncludePatterns:
    """Test grep backend handling of path-based include_patterns."""

    @pytest.fixture
    def test_repo_with_structure(self, tmp_path):
        """Create test repository with nested directory structure."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Create nested structure: src/widgets/Button.java
        widgets_dir = repo_path / "src" / "widgets"
        widgets_dir.mkdir(parents=True)
        (widgets_dir / "Button.java").write_text("class Button { void click() {} }")
        (widgets_dir / "Label.java").write_text("class Label { void setText() {} }")

        # Create other directories that shouldn't match
        utils_dir = repo_path / "src" / "utils"
        utils_dir.mkdir(parents=True)
        (utils_dir / "Helper.java").write_text("class Helper { void assist() {} }")

        # Create root-level file that shouldn't match
        (repo_path / "Main.java").write_text("class Main { void main() {} }")

        return repo_path

    @pytest.fixture
    def grep_service(self, test_repo_with_structure):
        """Create service with grep engine."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_side_effect(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_side_effect
            yield RegexSearchService(test_repo_with_structure)

    @pytest.mark.asyncio
    async def test_grep_handles_path_based_include_patterns(
        self, grep_service, test_repo_with_structure
    ):
        """Test grep backend correctly handles path-based include patterns like **/widgets/*.java."""
        # This test SHOULD pass after fix: grep backend should find files in widgets/ directory
        result = await grep_service.search(
            pattern="class", include_patterns=["**/widgets/*.java"]
        )

        # Should find Button.java and Label.java in src/widgets/
        assert (
            result.total_matches >= 2
        ), "Should find at least 2 matches in widgets directory"
        matched_files = {match.file_path for match in result.matches}
        assert any(
            "widgets" in f and "Button.java" in f for f in matched_files
        ), "Should match Button.java in widgets directory"
        assert any(
            "widgets" in f and "Label.java" in f for f in matched_files
        ), "Should match Label.java in widgets directory"

        # Should NOT find Helper.java or Main.java
        assert not any(
            "Helper.java" in f for f in matched_files
        ), "Should not match Helper.java outside widgets directory"
        assert not any(
            "Main.java" in f for f in matched_files
        ), "Should not match Main.java at root"

    @pytest.mark.asyncio
    async def test_grep_handles_multiple_path_patterns(
        self, grep_service, test_repo_with_structure
    ):
        """Test grep backend handles multiple path-based patterns."""
        result = await grep_service.search(
            pattern="class", include_patterns=["**/widgets/*.java", "**/utils/*.java"]
        )

        # Should find files in both widgets/ and utils/ directories
        matched_files = {match.file_path for match in result.matches}
        assert any(
            "widgets" in f for f in matched_files
        ), "Should match widgets directory"
        assert any("utils" in f for f in matched_files), "Should match utils directory"
        assert not any(
            f.endswith("Main.java") for f in matched_files
        ), "Should not match root-level files"

    @pytest.mark.asyncio
    async def test_grep_handles_simple_filename_patterns(
        self, grep_service, test_repo_with_structure
    ):
        """Test grep backend still handles simple filename patterns correctly."""
        # Simple filename pattern without path separators should work as before
        result = await grep_service.search(pattern="class", include_patterns=["*.java"])

        # Should find all .java files
        assert result.total_matches >= 4, "Should find all 4 .java files"

    @pytest.mark.asyncio
    async def test_grep_mixed_path_and_filename_patterns(
        self, grep_service, test_repo_with_structure
    ):
        """Test grep backend handles mixed path-based and simple filename patterns."""
        # Mix of path-based pattern and simple filename pattern
        result = await grep_service.search(
            pattern="class", include_patterns=["**/widgets/*.java", "Main.java"]
        )

        # Should find widgets files AND Main.java at root
        matched_files = {match.file_path for match in result.matches}
        assert any(
            "widgets" in f for f in matched_files
        ), "Should match widgets directory"
        assert any(
            f.endswith("Main.java") for f in matched_files
        ), "Should match Main.java"
        # Should NOT find Helper.java (not in patterns)
        assert not any(
            "Helper.java" in f for f in matched_files
        ), "Should not match Helper.java (not in patterns)"


class TestFindFilesDoubleStarPattern:
    """Test _find_files_by_patterns method with ** glob patterns.

    REGRESSION TEST: This reproduces the bug where **/filename.ext returns 0 matches
    while the underlying find command works correctly.
    """

    @pytest.fixture
    def deep_repo_structure(self, tmp_path):
        """Create repository with deep nested structure matching production evidence."""
        repo_path = tmp_path / "evolution-repo"
        repo_path.mkdir()

        # Create structure: v_*/code/src/dms/client/system/desktop/widgets/SalesGoalsWidget.java
        for version in ["v_1766032745", "v_1766034456", "v_1766035123", "v_1766036789"]:
            widget_path = (
                repo_path
                / version
                / "code"
                / "src"
                / "dms"
                / "client"
                / "system"
                / "desktop"
                / "widgets"
            )
            widget_path.mkdir(parents=True)
            (widget_path / "SalesGoalsWidget.java").write_text(
                "class SalesGoalsWidget { void render() {} }"
            )

        # Create other files that should NOT match
        (repo_path / "v_1766032745" / "code" / "src" / "Main.java").write_text(
            "class Main { void main() {} }"
        )

        return repo_path

    @pytest.fixture
    def grep_service_deep(self, deep_repo_structure):
        """Create grep service for deep structure testing."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_side_effect(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_side_effect
            yield RegexSearchService(deep_repo_structure)

    @pytest.mark.asyncio
    async def test_double_star_filename_pattern_finds_all_matches(
        self, grep_service_deep, deep_repo_structure
    ):
        """Test **/filename.ext pattern finds files at any depth.

        BUG REPRODUCTION: This test currently FAILS because the API returns 0 matches
        even though the underlying find command works correctly.

        Expected: 4 matches (one SalesGoalsWidget.java in each version directory)
        Actual: 0 matches (BUG)
        """
        result = await grep_service_deep.search(
            pattern="class", include_patterns=["**/SalesGoalsWidget.java"]
        )

        # Should find all 4 SalesGoalsWidget.java files across different versions
        assert result.total_matches == 4, (
            f"Expected 4 matches for **/SalesGoalsWidget.java pattern, "
            f"got {result.total_matches}"
        )

        matched_files = {match.file_path for match in result.matches}

        # Verify each version's widget file was found
        for version in ["v_1766032745", "v_1766034456", "v_1766035123", "v_1766036789"]:
            assert any(
                version in f and "SalesGoalsWidget.java" in f for f in matched_files
            ), f"Should find SalesGoalsWidget.java in {version}"

        # Should NOT find Main.java
        assert not any(
            "Main.java" in f for f in matched_files
        ), "Should not match Main.java (different filename)"

    @pytest.mark.asyncio
    async def test_simple_filename_pattern_works_correctly(
        self, grep_service_deep, deep_repo_structure
    ):
        """Test simple filename.ext pattern (without **/) works as baseline.

        This test SHOULD PASS - verifies that simple patterns work correctly.
        This provides evidence that the bug is specific to **/ prefix.
        """
        result = await grep_service_deep.search(
            pattern="class", include_patterns=["SalesGoalsWidget.java"]
        )

        # Simple pattern should find at least 1 match (current behavior)
        assert (
            result.total_matches >= 1
        ), "Simple pattern SalesGoalsWidget.java should find at least 1 match"

    @pytest.mark.asyncio
    async def test_double_star_directory_pattern_works_correctly(
        self, grep_service_deep, deep_repo_structure
    ):
        """Test **/directory/*.ext pattern works as baseline.

        This test SHOULD PASS - verifies that **/ with directory works.
        This confirms the bug is specific to **/filename.ext (no directory).
        """
        result = await grep_service_deep.search(
            pattern="class", include_patterns=["**/widgets/*.java"]
        )

        # Should find all 4 widget files
        assert (
            result.total_matches >= 4
        ), "Pattern **/widgets/*.java should find at least 4 matches"

    @pytest.fixture
    def ripgrep_service_deep(self, deep_repo_structure):
        """Create ripgrep service for deep structure testing."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/rg"
            yield RegexSearchService(deep_repo_structure)

    @pytest.mark.asyncio
    async def test_single_file_pattern_grep_parsing_bug(
        self, grep_service_deep, deep_repo_structure
    ):
        """Test pattern matching exactly ONE file triggers grep parsing bug.

        BUG REPRODUCTION: When grep receives exactly 1 file, it outputs:
            30:class Main { void main() {} }

        But the parsing regex expects:
            Main.java:30:class Main { void main() {} }

        This causes 0 matches to be returned even though the file exists
        and contains the pattern.

        This is the ACTUAL bug - the test_double_star_filename_pattern_finds_all_matches
        passes because it matches 4 files, and grep outputs filenames for multiple files.
        """
        result = await grep_service_deep.search(
            pattern="class", include_patterns=["**/Main.java"]
        )

        # BUG: This returns 0 matches because Main.java exists in only 1 version directory
        # and grep doesn't output filename when given a single file
        assert result.total_matches == 1, (
            f"Expected 1 match for **/Main.java pattern (single file), "
            f"got {result.total_matches} (BUG: grep single-file parsing)"
        )

        matched_files = {match.file_path for match in result.matches}
        assert any(
            "Main.java" in f for f in matched_files
        ), "Should find Main.java in v_1766032745"

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not shutil.which("rg"),
        reason="ripgrep (rg) not available in PATH - test requires standalone rg binary",
    )
    async def test_double_star_filename_pattern_ripgrep(
        self, ripgrep_service_deep, deep_repo_structure
    ):
        """Test **/filename.ext pattern with ripgrep engine.

        Verifies that ripgrep's -g glob flag handles **/filename.ext correctly.
        This tests the ripgrep code path (lines 235-237 in regex_search.py).

        NOTE: This test is skipped if rg binary is not in PATH. The grep-based test
        (test_double_star_filename_pattern_finds_all_matches) provides equivalent
        coverage for the pattern matching logic.
        """
        result = await ripgrep_service_deep.search(
            pattern="class", include_patterns=["**/SalesGoalsWidget.java"]
        )

        # Should find all 4 SalesGoalsWidget.java files
        assert result.total_matches == 4, (
            f"Ripgrep with **/SalesGoalsWidget.java should find 4 matches, "
            f"got {result.total_matches}"
        )

        matched_files = {match.file_path for match in result.matches}

        # Verify each version's widget file was found
        for version in ["v_1766032745", "v_1766034456", "v_1766035123", "v_1766036789"]:
            assert any(
                version in f and "SalesGoalsWidget.java" in f for f in matched_files
            ), f"Ripgrep should find SalesGoalsWidget.java in {version}"


class TestGlobPatternParity:
    """Test comprehensive glob pattern support matching ripgrep behavior.

    These tests verify that grep backend matches ripgrep's -g flag behavior exactly,
    covering patterns that currently fail with find-based implementation.
    """

    @pytest.fixture
    def glob_test_repo(self, tmp_path):
        """Create test repository with structure for glob pattern testing."""
        repo_path = tmp_path / "glob-test-repo"
        repo_path.mkdir()

        # Create nested structure: code/src/dms/client/widgets/SalesGoalsWidget.java
        widget_path = repo_path / "code" / "src" / "dms" / "client" / "widgets"
        widget_path.mkdir(parents=True)
        (widget_path / "SalesGoalsWidget.java").write_text(
            "class SalesGoalsWidget { void render() {} }"
        )

        # Create explicit path file: code/src/Main.java
        (repo_path / "code" / "src" / "Main.java").write_text(
            "class Main { void main() {} }"
        )

        # Create another nested file: code/tests/TestHelper.java
        test_path = repo_path / "code" / "tests"
        test_path.mkdir(parents=True)
        (test_path / "TestHelper.java").write_text(
            "class TestHelper { void help() {} }"
        )

        return repo_path

    @pytest.fixture
    def grep_service_glob(self, glob_test_repo):
        """Create grep service for glob pattern testing."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_side_effect(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_side_effect
            yield RegexSearchService(glob_test_repo)

    @pytest.mark.asyncio
    async def test_glob_pattern_with_double_star_in_middle_of_path(
        self, grep_service_glob, glob_test_repo
    ):
        """Test pattern with ** in MIDDLE of path: code/**/SalesGoalsWidget.java

        REQUIREMENT: Pattern dir/**/file.ext must match file under dir at any depth.
        CURRENT BUG: find -path doesn't expand ** in middle of path correctly.
        """
        result = await grep_service_glob.search(
            pattern="class", include_patterns=["code/**/SalesGoalsWidget.java"]
        )

        # Should find SalesGoalsWidget.java under code/ at any depth
        assert result.total_matches == 1, (
            f"Pattern code/**/SalesGoalsWidget.java should find 1 match, "
            f"got {result.total_matches}"
        )

        matched_files = {match.file_path for match in result.matches}
        assert any(
            "SalesGoalsWidget.java" in f and "code" in f for f in matched_files
        ), "Should find code/src/dms/client/widgets/SalesGoalsWidget.java"

    @pytest.mark.asyncio
    async def test_glob_pattern_explicit_path(self, grep_service_glob, glob_test_repo):
        """Test explicit path pattern: code/src/Main.java

        REQUIREMENT: Explicit path patterns must work like ripgrep -g.
        CURRENT BUG: find -path requires ./ prefix and doesn't match explicit paths.
        """
        result = await grep_service_glob.search(
            pattern="class", include_patterns=["code/src/Main.java"]
        )

        # Should find exact file at code/src/Main.java
        assert result.total_matches == 1, (
            f"Pattern code/src/Main.java should find 1 match, "
            f"got {result.total_matches}"
        )

        matched_files = {match.file_path for match in result.matches}
        assert any(
            "Main.java" in f and "code/src" in f for f in matched_files
        ), "Should find code/src/Main.java"

    @pytest.mark.asyncio
    async def test_glob_pattern_multiple_mixed_patterns(
        self, grep_service_glob, glob_test_repo
    ):
        """Test multiple patterns with different glob types.

        REQUIREMENT: Mixed patterns (explicit, **, simple) must all work together.
        """
        result = await grep_service_glob.search(
            pattern="class",
            include_patterns=[
                "code/**/SalesGoalsWidget.java",  # ** in middle
                "code/src/Main.java",  # Explicit path
                "**/TestHelper.java",  # ** at start
            ],
        )

        # Should find all 3 files
        assert (
            result.total_matches == 3
        ), f"Mixed patterns should find 3 matches, got {result.total_matches}"

        matched_files = {match.file_path for match in result.matches}
        assert any(
            "SalesGoalsWidget.java" in f for f in matched_files
        ), "Should find SalesGoalsWidget.java via code/**/pattern"
        assert any(
            "Main.java" in f for f in matched_files
        ), "Should find Main.java via explicit path"
        assert any(
            "TestHelper.java" in f for f in matched_files
        ), "Should find TestHelper.java via **/pattern"


class TestGrepContextLines:
    """Test grep parser context line capture from -C flag output.

    Tests verify that grep parser correctly captures context_before and context_after
    from grep's -C flag output, restoring feature parity with ripgrep backend.

    Grep output format:
    - Match lines: filename:linenum:content (colon separators)
    - Context lines: filename-linenum-content (dash separators)
    - Group separators: -- (between match groups)
    """

    @pytest.fixture
    def context_test_repo(self, tmp_path):
        """Create test repository for context line testing."""
        repo_path = tmp_path / "context-test-repo"
        repo_path.mkdir()
        return repo_path

    @pytest.fixture
    def grep_service_context(self, context_test_repo):
        """Create grep service for context line testing."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_side_effect(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_side_effect
            yield RegexSearchService(context_test_repo)

    @pytest.mark.asyncio
    async def test_grep_context_lines_basic(
        self, grep_service_context, context_test_repo
    ):
        """Test basic context line capture with 2 lines before and after match.

        BUG REPRODUCTION: Currently returns empty context_before=[] and context_after=[].
        Expected: context_before=["line 2", "line 3"], context_after=["line 5", "line 6"]
        """
        # Create test file with 7 lines, match will be on line 4
        test_file = context_test_repo / "test.py"
        test_file.write_text(
            "line 1\nline 2\nline 3\nMATCH line 4\nline 5\nline 6\nline 7\n"
        )

        result = await grep_service_context.search(
            pattern="MATCH",
            context_lines=2,
        )

        # Should find 1 match
        assert (
            result.total_matches == 1
        ), f"Expected 1 match, got {result.total_matches}"
        assert (
            len(result.matches) == 1
        ), f"Expected 1 match object, got {len(result.matches)}"

        match = result.matches[0]
        assert match.line_number == 4, f"Expected line 4, got {match.line_number}"

        # BUG: These assertions will FAIL with current implementation
        assert match.context_before == [
            "line 2",
            "line 3",
        ], f"Expected context_before=['line 2', 'line 3'], got {match.context_before}"
        assert match.context_after == [
            "line 5",
            "line 6",
        ], f"Expected context_after=['line 5', 'line 6'], got {match.context_after}"

    @pytest.mark.asyncio
    async def test_grep_context_lines_multiple_matches(
        self, grep_service_context, context_test_repo
    ):
        """Test context lines with multiple matches in same file.

        BUG REPRODUCTION: Both matches return empty context arrays.
        Expected: Each match has correct context_before and context_after.
        """
        # Create test file with 2 matches, separated by enough lines
        test_file = context_test_repo / "multi.py"
        test_file.write_text(
            "line 1\n"
            "line 2\n"
            "MATCH line 3\n"  # First match
            "line 4\n"
            "line 5\n"
            "line 6\n"
            "MATCH line 7\n"  # Second match
            "line 8\n"
        )

        result = await grep_service_context.search(
            pattern="MATCH",
            context_lines=1,
        )

        # Should find 2 matches
        assert (
            result.total_matches == 2
        ), f"Expected 2 matches, got {result.total_matches}"
        assert (
            len(result.matches) == 2
        ), f"Expected 2 match objects, got {len(result.matches)}"

        # First match (line 3)
        match1 = result.matches[0]
        assert match1.line_number == 3, f"Expected line 3, got {match1.line_number}"
        assert match1.context_before == [
            "line 2"
        ], f"Expected context_before=['line 2'], got {match1.context_before}"
        assert match1.context_after == [
            "line 4"
        ], f"Expected context_after=['line 4'], got {match1.context_after}"

        # Second match (line 7)
        match2 = result.matches[1]
        assert match2.line_number == 7, f"Expected line 7, got {match2.line_number}"
        assert match2.context_before == [
            "line 6"
        ], f"Expected context_before=['line 6'], got {match2.context_before}"
        assert match2.context_after == [
            "line 8"
        ], f"Expected context_after=['line 8'], got {match2.context_after}"

    @pytest.mark.asyncio
    async def test_grep_context_lines_file_boundaries(
        self, grep_service_context, context_test_repo
    ):
        """Test context lines at file boundaries (start and end of file).

        BUG REPRODUCTION: Returns empty context arrays at boundaries.
        Expected: Empty context_before for line 1, empty context_after for last line.
        """
        # Create test file with matches at boundaries
        test_file = context_test_repo / "boundary.py"
        test_file.write_text(
            "MATCH line 1\n"  # Match at start (no context before)
            "line 2\n"
            "line 3\n"
            "MATCH line 4\n"  # Match at end (no context after)
        )

        result = await grep_service_context.search(
            pattern="MATCH",
            context_lines=1,
        )

        # Should find 2 matches
        assert (
            result.total_matches == 2
        ), f"Expected 2 matches, got {result.total_matches}"
        assert (
            len(result.matches) == 2
        ), f"Expected 2 match objects, got {len(result.matches)}"

        # First match (line 1) - no context before
        match1 = result.matches[0]
        assert match1.line_number == 1, f"Expected line 1, got {match1.line_number}"
        assert (
            match1.context_before == []
        ), f"Expected empty context_before at file start, got {match1.context_before}"
        assert match1.context_after == [
            "line 2"
        ], f"Expected context_after=['line 2'], got {match1.context_after}"

        # Second match (line 4) - no context after (last line)
        match2 = result.matches[1]
        assert match2.line_number == 4, f"Expected line 4, got {match2.line_number}"
        assert match2.context_before == [
            "line 3"
        ], f"Expected context_before=['line 3'], got {match2.context_before}"
        assert (
            match2.context_after == []
        ), f"Expected empty context_after at file end, got {match2.context_after}"

    @pytest.mark.asyncio
    async def test_grep_context_lines_zero(
        self, grep_service_context, context_test_repo
    ):
        """Test that context_lines=0 returns empty context arrays.

        This should PASS with current implementation (no context requested).
        """
        test_file = context_test_repo / "nocontext.py"
        test_file.write_text("line 1\nMATCH line 2\nline 3\n")

        result = await grep_service_context.search(
            pattern="MATCH",
            context_lines=0,
        )

        # Should find 1 match
        assert (
            result.total_matches == 1
        ), f"Expected 1 match, got {result.total_matches}"
        assert (
            len(result.matches) == 1
        ), f"Expected 1 match object, got {len(result.matches)}"

        match = result.matches[0]
        assert (
            match.context_before == []
        ), f"Expected empty context_before with context_lines=0, got {match.context_before}"
        assert (
            match.context_after == []
        ), f"Expected empty context_after with context_lines=0, got {match.context_after}"

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not shutil.which("rg"),
        reason="ripgrep (rg) not available - test requires rg for parity check",
    )
    async def test_context_lines_parity_grep_vs_ripgrep(self, context_test_repo):
        """Test that grep and ripgrep return identical context lines.

        BUG REPRODUCTION: Grep returns empty context, ripgrep returns correct context.
        Expected: Both return identical context_before and context_after arrays.
        """
        # Create test file
        test_file = context_test_repo / "parity.py"
        test_file.write_text("line 1\nline 2\nMATCH line 3\nline 4\nline 5\n")

        # Create grep service
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_grep(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_grep
            grep_service = RegexSearchService(context_test_repo)

        # Create ripgrep service
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/rg"
            ripgrep_service = RegexSearchService(context_test_repo)

        # Search with both backends
        grep_result = await grep_service.search(pattern="MATCH", context_lines=1)
        ripgrep_result = await ripgrep_service.search(pattern="MATCH", context_lines=1)

        # Both should find 1 match
        assert grep_result.total_matches == 1
        assert ripgrep_result.total_matches == 1

        # Context arrays should be identical
        grep_match = grep_result.matches[0]
        ripgrep_match = ripgrep_result.matches[0]

        assert (
            grep_match.context_before == ripgrep_match.context_before
        ), f"Context before mismatch: grep={grep_match.context_before}, ripgrep={ripgrep_match.context_before}"
        assert (
            grep_match.context_after == ripgrep_match.context_after
        ), f"Context after mismatch: grep={grep_match.context_after}, ripgrep={ripgrep_match.context_after}"


class TestSubprocessGlobProtections:
    """Test subprocess-based glob implementation protections.

    These tests verify that the subprocess-based glob implementation restores
    critical production protections documented in .analysis/glob-protection-loss-analysis.md.
    Tests are organized in batches for incremental development.
    """

    @pytest.fixture
    def large_repo_structure(self, tmp_path):
        """Create repository with many files for performance testing."""
        repo_path = tmp_path / "large-repo"
        repo_path.mkdir()

        # Create 100 Python files across 10 directories
        for dir_num in range(10):
            dir_path = repo_path / f"module_{dir_num}"
            dir_path.mkdir()
            for file_num in range(10):
                (dir_path / f"file_{file_num}.py").write_text(
                    f"# Module {dir_num} File {file_num}\ndef func():\n    pass\n"
                )

        return repo_path

    @pytest.fixture
    def grep_service_large(self, large_repo_structure):
        """Create grep service for large repo testing."""
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_side_effect(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_side_effect
            yield RegexSearchService(large_repo_structure)

    @pytest.mark.asyncio
    async def test_find_files_by_patterns_timeout_enforced(
        self, grep_service_large, large_repo_structure
    ):
        """Test that glob operations respect timeout and raise TimeoutError.

        PROTECTION: Timeout Protection (CRITICAL)
        REQUIREMENT: File discovery must timeout after specified seconds
        """
        # Use a very short timeout that should trigger timeout
        with pytest.raises(TimeoutError, match="timed out after"):
            await grep_service_large._find_files_by_patterns(
                search_path=large_repo_structure,
                include_patterns=["**/*.py"],
                exclude_patterns=None,
                timeout_seconds=0.001,  # 1ms - should timeout
            )

    @pytest.mark.asyncio
    async def test_find_files_by_patterns_async_execution(
        self, grep_service_large, large_repo_structure
    ):
        """Test that glob doesn't block event loop during execution.

        PROTECTION: Async Execution (CRITICAL)
        REQUIREMENT: Event loop must remain responsive during file discovery
        """
        import asyncio

        # Track if event loop processed other work
        other_work_completed = False

        async def other_async_work():
            nonlocal other_work_completed
            await asyncio.sleep(0.01)  # Minimal delay
            other_work_completed = True
            return "completed"

        # Start glob task in background
        glob_task = asyncio.create_task(
            grep_service_large._find_files_by_patterns(
                search_path=large_repo_structure,
                include_patterns=["**/*.py"],
                exclude_patterns=None,
                timeout_seconds=10,
            )
        )

        # Start other work task
        other_task = asyncio.create_task(other_async_work())

        # Both tasks should complete
        results, other_result = await asyncio.gather(glob_task, other_task)

        # Verify event loop was responsive (other work completed)
        assert other_work_completed, "Event loop should remain responsive during glob"
        assert other_result == "completed"

        # Verify glob results are valid
        assert isinstance(results, list), "Glob should return list of file paths"
        assert len(results) > 0, "Should find Python files"

    @pytest.mark.asyncio
    async def test_find_files_by_patterns_subprocess_error_handling(self, tmp_path):
        """Test that subprocess errors are handled gracefully.

        PROTECTION: Process Isolation + Error Isolation (HIGH/MEDIUM)
        REQUIREMENT: Subprocess failures must not crash caller
        """
        with patch("code_indexer.global_repos.regex_search.shutil.which") as mock_which:

            def which_side_effect(cmd):
                return "/usr/bin/grep" if cmd == "grep" else None

            mock_which.side_effect = which_side_effect
            service = RegexSearchService(tmp_path)

        # Test with path that doesn't exist (should handle gracefully)
        nonexistent_path = tmp_path / "nonexistent"

        # Should return empty list or raise appropriate exception, not crash
        try:
            result = await service._find_files_by_patterns(
                search_path=nonexistent_path,
                include_patterns=["**/*.py"],
                exclude_patterns=None,
                timeout_seconds=5,
            )
            # If it succeeds, should return empty list
            assert isinstance(result, list), "Should return list on error"
            assert len(result) == 0, "Should return empty list for nonexistent path"
        except (ValueError, FileNotFoundError, OSError) as e:
            # Appropriate exceptions are acceptable
            assert str(e), "Exception should have meaningful message"

    @pytest.mark.asyncio
    async def test_find_files_by_patterns_large_result_set(
        self, grep_service_large, large_repo_structure
    ):
        """Test that large result sets are handled efficiently.

        PROTECTION: Memory Protection (HIGH)
        REQUIREMENT: Large result sets must not cause memory issues
        """
        # Pattern that matches all 100 Python files
        result = await grep_service_large._find_files_by_patterns(
            search_path=large_repo_structure,
            include_patterns=["**/*.py"],
            exclude_patterns=None,
            timeout_seconds=10,
        )

        # Verify all files found
        assert isinstance(result, list), "Should return list of file paths"
        assert len(result) == 100, f"Should find all 100 .py files, got {len(result)}"

        # Verify results are relative paths (not absolute)
        for file_path in result:
            assert not file_path.startswith(
                "/"
            ), f"Path should be relative: {file_path}"
            assert file_path.endswith(".py"), f"Path should end with .py: {file_path}"

    @pytest.mark.asyncio
    async def test_find_files_by_patterns_invalid_glob_pattern(
        self, grep_service_large, large_repo_structure
    ):
        """Test handling of invalid glob patterns.

        PROTECTION: Error Isolation (MEDIUM)
        REQUIREMENT: Invalid patterns must be handled gracefully
        """
        # Pattern with invalid syntax (unclosed bracket)
        invalid_patterns = [
            "[unclosed",
            "**/*[",
            "file[",
        ]

        for pattern in invalid_patterns:
            # Should either return empty list or raise appropriate exception
            try:
                result = await grep_service_large._find_files_by_patterns(
                    search_path=large_repo_structure,
                    include_patterns=[pattern],
                    exclude_patterns=None,
                    timeout_seconds=5,
                )
                # If it succeeds, verify it's a list
                assert isinstance(
                    result, list
                ), f"Should return list for invalid pattern {pattern}"
            except (ValueError, OSError) as e:
                # Appropriate exceptions are acceptable
                assert str(
                    e
                ), f"Exception for invalid pattern {pattern} should have message"

    @pytest.mark.asyncio
    async def test_find_files_by_patterns_no_matches(
        self, grep_service_large, large_repo_structure
    ):
        """Test that patterns with no matches return empty list.

        PROTECTION: Error Isolation (MEDIUM)
        REQUIREMENT: No matches is success case, not error
        """
        # Pattern that matches nothing
        result = await grep_service_large._find_files_by_patterns(
            search_path=large_repo_structure,
            include_patterns=["**/*.nonexistent"],
            exclude_patterns=None,
            timeout_seconds=5,
        )

        # Should return empty list, not error
        assert isinstance(result, list), "Should return list"
        assert len(result) == 0, "Should return empty list when no matches"

    @pytest.mark.asyncio
    async def test_find_files_by_patterns_concurrent_calls(
        self, grep_service_large, large_repo_structure
    ):
        """Test that multiple concurrent glob operations work correctly.

        PROTECTION: Concurrent Control (MEDIUM)
        REQUIREMENT: Multiple concurrent globs must complete successfully
        """
        import asyncio

        # Launch 5 concurrent glob operations with different patterns
        patterns = [
            ["**/*.py"],
            ["**/module_0/*.py"],
            ["**/module_1/*.py"],
            ["**/file_0.py"],
            ["**/file_1.py"],
        ]

        tasks = [
            grep_service_large._find_files_by_patterns(
                search_path=large_repo_structure,
                include_patterns=pattern,
                exclude_patterns=None,
                timeout_seconds=10,
            )
            for pattern in patterns
        ]

        # All should complete successfully
        results = await asyncio.gather(*tasks)

        # Verify all results are valid
        assert len(results) == 5, "All 5 concurrent operations should complete"

        for i, result in enumerate(results):
            assert isinstance(result, list), f"Result {i} should be list"
            assert len(result) > 0, f"Result {i} should have matches"
