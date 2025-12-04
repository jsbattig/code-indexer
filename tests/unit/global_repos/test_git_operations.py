"""Tests for GitOperationsService.

Tests the git history exploration operations:
- get_log: Retrieve commit history with filters
- show_commit: Get detailed commit information
- get_file_at_revision: Get file contents at specific revision

Following TDD methodology - tests written first before implementation.
"""

import pytest
import subprocess


class TestGitOperationsService:
    """Unit tests for GitOperationsService."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository with some commits."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create initial file and commit
        (repo_path / "file1.py").write_text("def hello():\n    print('hello')\n")
        subprocess.run(
            ["git", "add", "file1.py"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        return repo_path

    def test_init_verifies_git_repository(self, tmp_path):
        """Test that GitOperationsService validates the path is a git repo."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        # Non-git directory should raise ValueError
        non_git_path = tmp_path / "not-a-repo"
        non_git_path.mkdir()

        with pytest.raises(ValueError, match="Not a git repository"):
            GitOperationsService(non_git_path)

    def test_init_with_valid_git_repo(self, git_repo):
        """Test that GitOperationsService initializes with valid git repo."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo)
        assert service.repo_path == git_repo


class TestGetLog:
    """Tests for get_log method."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository with some commits."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create commits
        (repo_path / "file1.py").write_text("content 1")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "First commit"],
            cwd=repo_path,
            capture_output=True,
        )

        (repo_path / "file2.py").write_text("content 2")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Second commit"],
            cwd=repo_path,
            capture_output=True,
        )

        (repo_path / "file3.py").write_text("content 3")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Third commit"],
            cwd=repo_path,
            capture_output=True,
        )

        return repo_path

    def test_get_log_returns_commits(self, git_repo):
        """Test get_log returns commit history."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo)
        result = service.get_log()

        assert result.total_count == 3
        assert len(result.commits) == 3
        assert not result.truncated

    def test_get_log_respects_limit(self, git_repo):
        """Test get_log respects the limit parameter."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo)
        result = service.get_log(limit=2)

        assert len(result.commits) == 2
        assert result.truncated is True

    def test_get_log_commit_info_structure(self, git_repo):
        """Test get_log returns proper CommitInfo structure."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo)
        result = service.get_log(limit=1)

        commit = result.commits[0]
        assert commit.hash is not None
        assert len(commit.hash) == 40  # Full SHA
        assert commit.short_hash is not None
        assert len(commit.short_hash) >= 7
        assert commit.author_name == "Test User"
        assert commit.author_email == "test@example.com"
        assert commit.subject == "Third commit"

    def test_get_log_filter_by_path(self, git_repo):
        """Test get_log filters by path."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo)
        result = service.get_log(path="file1.py")

        assert result.total_count == 1
        assert result.commits[0].subject == "First commit"

    def test_get_log_filter_by_author(self, git_repo, tmp_path):
        """Test get_log filters by author."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        # Create a second author commit
        subprocess.run(
            ["git", "config", "user.email", "other@example.com"],
            cwd=git_repo,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Other User"],
            cwd=git_repo,
            capture_output=True,
        )
        (git_repo / "file4.py").write_text("content 4")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Fourth commit by other"],
            cwd=git_repo,
            capture_output=True,
        )

        service = GitOperationsService(git_repo)
        result = service.get_log(author="other@example.com")

        assert result.total_count == 1
        assert result.commits[0].author_email == "other@example.com"

    def test_get_log_filter_by_date_range(self, git_repo):
        """Test get_log filters by date range."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo)
        # Use a date in the past
        result = service.get_log(since="2020-01-01", until="2020-01-02")

        assert result.total_count == 0


class TestShowCommit:
    """Tests for show_commit method."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository with a commit."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        (repo_path / "file1.py").write_text("content 1")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "First commit"],
            cwd=repo_path,
            capture_output=True,
        )

        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        commit_hash = result.stdout.strip()

        return {"path": repo_path, "commit_hash": commit_hash}

    def test_show_commit_returns_commit_detail(self, git_repo):
        """Test show_commit returns detailed commit info."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo["path"])
        result = service.show_commit(git_repo["commit_hash"])

        assert result.commit.hash == git_repo["commit_hash"]
        assert result.commit.subject == "First commit"
        assert result.commit.author_name == "Test User"

    def test_show_commit_includes_stats(self, git_repo):
        """Test show_commit includes file change stats by default."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo["path"])
        result = service.show_commit(git_repo["commit_hash"], include_stats=True)

        assert result.stats is not None
        assert len(result.stats) == 1
        assert result.stats[0].path == "file1.py"
        assert result.stats[0].status == "added"

    def test_show_commit_includes_diff(self, git_repo):
        """Test show_commit can include diff."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo["path"])
        result = service.show_commit(git_repo["commit_hash"], include_diff=True)

        assert result.diff is not None
        assert "content 1" in result.diff

    def test_show_commit_excludes_diff_by_default(self, git_repo):
        """Test show_commit excludes diff by default."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo["path"])
        result = service.show_commit(git_repo["commit_hash"])

        assert result.diff is None

    def test_show_commit_invalid_hash_raises(self, git_repo):
        """Test show_commit raises for invalid commit hash."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo["path"])

        with pytest.raises(ValueError, match="Commit not found"):
            service.show_commit("0000000000000000000000000000000000000000")

    def test_show_commit_with_short_hash(self, git_repo):
        """Test show_commit works with abbreviated hash."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo["path"])
        short_hash = git_repo["commit_hash"][:7]
        result = service.show_commit(short_hash)

        assert result.commit.hash == git_repo["commit_hash"]

    def test_show_commit_with_symbolic_ref(self, git_repo):
        """Test show_commit works with HEAD and other symbolic refs."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo["path"])
        result = service.show_commit("HEAD")

        assert result.commit.hash == git_repo["commit_hash"]


class TestGetFileAtRevision:
    """Tests for get_file_at_revision method."""

    @pytest.fixture
    def git_repo_with_history(self, tmp_path):
        """Create a git repo with file modification history."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Version 1
        (repo_path / "file.py").write_text("version 1\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Version 1"],
            cwd=repo_path,
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        v1_hash = result.stdout.strip()

        # Version 2
        (repo_path / "file.py").write_text("version 2\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Version 2"],
            cwd=repo_path,
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        v2_hash = result.stdout.strip()

        return {"path": repo_path, "v1_hash": v1_hash, "v2_hash": v2_hash}

    def test_get_file_at_revision_returns_content(self, git_repo_with_history):
        """Test get_file_at_revision returns file content."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_history["path"])
        result = service.get_file_at_revision(
            "file.py", git_repo_with_history["v1_hash"]
        )

        assert result.content == "version 1\n"
        assert result.path == "file.py"
        assert result.revision == git_repo_with_history["v1_hash"]

    def test_get_file_at_revision_resolves_revision(self, git_repo_with_history):
        """Test get_file_at_revision includes resolved revision."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_history["path"])
        result = service.get_file_at_revision("file.py", "HEAD")

        assert result.revision == "HEAD"
        assert result.resolved_revision == git_repo_with_history["v2_hash"]

    def test_get_file_at_revision_returns_size(self, git_repo_with_history):
        """Test get_file_at_revision returns file size."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_history["path"])
        result = service.get_file_at_revision(
            "file.py", git_repo_with_history["v1_hash"]
        )

        assert result.size_bytes == len("version 1\n")

    def test_get_file_at_revision_different_versions(self, git_repo_with_history):
        """Test get_file_at_revision returns correct content for different versions."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_history["path"])

        v1_result = service.get_file_at_revision(
            "file.py", git_repo_with_history["v1_hash"]
        )
        v2_result = service.get_file_at_revision(
            "file.py", git_repo_with_history["v2_hash"]
        )

        assert v1_result.content == "version 1\n"
        assert v2_result.content == "version 2\n"

    def test_get_file_at_revision_invalid_file_raises(self, git_repo_with_history):
        """Test get_file_at_revision raises for nonexistent file."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_history["path"])

        with pytest.raises(ValueError, match="File not found"):
            service.get_file_at_revision(
                "nonexistent.py", git_repo_with_history["v1_hash"]
            )

    def test_get_file_at_revision_invalid_revision_raises(self, git_repo_with_history):
        """Test get_file_at_revision raises for invalid revision."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_history["path"])

        with pytest.raises(ValueError, match="Invalid revision"):
            service.get_file_at_revision(
                "file.py", "0000000000000000000000000000000000000000"
            )

    def test_get_file_at_revision_with_branch_name(self, git_repo_with_history):
        """Test get_file_at_revision works with branch names."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_history["path"])

        # Get current branch name
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_repo_with_history["path"],
            capture_output=True,
            text=True,
        )
        branch_name = result.stdout.strip() or "master"

        result = service.get_file_at_revision("file.py", branch_name)
        assert result.content == "version 2\n"

    def test_get_file_at_revision_with_relative_ref(self, git_repo_with_history):
        """Test get_file_at_revision works with relative refs like HEAD~1."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_history["path"])
        result = service.get_file_at_revision("file.py", "HEAD~1")

        assert result.content == "version 1\n"


class TestGetDiff:
    """Tests for get_diff method (Story #555)."""

    @pytest.fixture
    def git_repo_with_changes(self, tmp_path):
        """Create a git repo with multiple commits for diff testing."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # First commit
        (repo_path / "file1.py").write_text("def hello():\n    pass\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "First commit"],
            cwd=repo_path,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        first_hash = result.stdout.strip()

        # Second commit - modify file1 and add file2
        (repo_path / "file1.py").write_text("def hello():\n    print('hello')\n")
        (repo_path / "file2.py").write_text("def world():\n    pass\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Second commit"],
            cwd=repo_path,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        second_hash = result.stdout.strip()

        return {
            "path": repo_path,
            "first_hash": first_hash,
            "second_hash": second_hash,
        }

    def test_get_diff_between_revisions(self, git_repo_with_changes):
        """Test get_diff returns diff between two commits."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_changes["path"])
        result = service.get_diff(
            from_revision=git_repo_with_changes["first_hash"],
            to_revision=git_repo_with_changes["second_hash"],
        )

        assert result.from_revision == git_repo_with_changes["first_hash"]
        assert result.to_revision == git_repo_with_changes["second_hash"]
        assert len(result.files) == 2
        assert result.total_insertions > 0

    def test_get_diff_to_working_directory(self, git_repo_with_changes):
        """Test get_diff compares to working directory when to_revision is None."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        (git_repo_with_changes["path"] / "file1.py").write_text(
            "def hello():\n    print('modified')\n"
        )

        service = GitOperationsService(git_repo_with_changes["path"])
        result = service.get_diff(
            from_revision=git_repo_with_changes["second_hash"],
            to_revision=None,
        )

        assert result.to_revision is None
        assert len(result.files) >= 1
        file_paths = [f.path for f in result.files]
        assert "file1.py" in file_paths

    def test_get_diff_with_path_filter(self, git_repo_with_changes):
        """Test get_diff filters by path."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_changes["path"])
        result = service.get_diff(
            from_revision=git_repo_with_changes["first_hash"],
            to_revision=git_repo_with_changes["second_hash"],
            path="file1.py",
        )

        assert len(result.files) == 1
        assert result.files[0].path == "file1.py"

    def test_get_diff_stat_only(self, git_repo_with_changes):
        """Test get_diff with stat_only returns only statistics."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_changes["path"])
        result = service.get_diff(
            from_revision=git_repo_with_changes["first_hash"],
            to_revision=git_repo_with_changes["second_hash"],
            stat_only=True,
        )

        assert len(result.files) == 2
        for file_diff in result.files:
            assert file_diff.hunks == []

    def test_get_diff_result_structure(self, git_repo_with_changes):
        """Test get_diff returns proper GitDiffResult structure."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_changes["path"])
        result = service.get_diff(
            from_revision=git_repo_with_changes["first_hash"],
            to_revision=git_repo_with_changes["second_hash"],
        )

        assert hasattr(result, "from_revision")
        assert hasattr(result, "to_revision")
        assert hasattr(result, "files")
        assert hasattr(result, "total_insertions")
        assert hasattr(result, "total_deletions")
        assert hasattr(result, "stat_summary")

        for file_diff in result.files:
            assert hasattr(file_diff, "path")
            assert hasattr(file_diff, "old_path")
            assert hasattr(file_diff, "status")
            assert hasattr(file_diff, "insertions")
            assert hasattr(file_diff, "deletions")
            assert hasattr(file_diff, "hunks")
            assert file_diff.status in ("added", "modified", "deleted", "renamed")

    def test_get_diff_file_statuses(self, git_repo_with_changes):
        """Test get_diff correctly identifies file statuses."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_changes["path"])
        result = service.get_diff(
            from_revision=git_repo_with_changes["first_hash"],
            to_revision=git_repo_with_changes["second_hash"],
        )

        statuses = {f.path: f.status for f in result.files}
        assert statuses.get("file1.py") == "modified"
        assert statuses.get("file2.py") == "added"


class TestGetBlame:
    """Tests for get_blame method (Story #555)."""

    @pytest.fixture
    def git_repo_with_blame_history(self, tmp_path):
        """Create a git repo with multiple authors/commits for blame testing."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "user1@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "User One"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # First commit by User One
        (repo_path / "file.py").write_text("line1\nline2\nline3\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=repo_path,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        first_hash = result.stdout.strip()

        # Second commit by User Two (modify line2)
        subprocess.run(
            ["git", "config", "user.email", "user2@example.com"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "User Two"],
            cwd=repo_path,
            capture_output=True,
        )
        (repo_path / "file.py").write_text("line1\nline2_modified\nline3\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify line2"],
            cwd=repo_path,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        second_hash = result.stdout.strip()

        return {
            "path": repo_path,
            "first_hash": first_hash,
            "second_hash": second_hash,
        }

    def test_get_blame_returns_line_annotations(self, git_repo_with_blame_history):
        """Test get_blame returns blame annotations for each line."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_blame_history["path"])
        result = service.get_blame("file.py")

        assert result.path == "file.py"
        assert len(result.lines) == 3
        assert result.unique_commits == 2

    def test_get_blame_line_structure(self, git_repo_with_blame_history):
        """Test get_blame returns proper BlameLine structure."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_blame_history["path"])
        result = service.get_blame("file.py")

        for line in result.lines:
            assert hasattr(line, "line_number")
            assert hasattr(line, "commit_hash")
            assert hasattr(line, "short_hash")
            assert hasattr(line, "author_name")
            assert hasattr(line, "author_email")
            assert hasattr(line, "author_date")
            assert hasattr(line, "original_line_number")
            assert hasattr(line, "content")
            assert len(line.commit_hash) == 40
            assert len(line.short_hash) >= 7

    def test_get_blame_different_authors(self, git_repo_with_blame_history):
        """Test get_blame correctly identifies different authors."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_blame_history["path"])
        result = service.get_blame("file.py")

        # Line 1 and 3 by User One, Line 2 by User Two
        authors = {line.line_number: line.author_email for line in result.lines}
        assert authors[1] == "user1@example.com"
        assert authors[2] == "user2@example.com"
        assert authors[3] == "user1@example.com"

    def test_get_blame_at_revision(self, git_repo_with_blame_history):
        """Test get_blame at specific revision shows historical state."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_blame_history["path"])
        result = service.get_blame(
            "file.py", revision=git_repo_with_blame_history["first_hash"]
        )

        # At first commit, all lines by User One
        for line in result.lines:
            assert line.author_email == "user1@example.com"

    def test_get_blame_with_line_range(self, git_repo_with_blame_history):
        """Test get_blame with start_line and end_line filters."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_blame_history["path"])
        result = service.get_blame("file.py", start_line=2, end_line=2)

        assert len(result.lines) == 1
        assert result.lines[0].line_number == 2
        assert result.lines[0].author_email == "user2@example.com"

    def test_get_blame_invalid_file_raises(self, git_repo_with_blame_history):
        """Test get_blame raises for nonexistent file."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_blame_history["path"])

        with pytest.raises(ValueError, match="File not found"):
            service.get_blame("nonexistent.py")


class TestGetFileHistory:
    """Tests for get_file_history method (Story #555)."""

    @pytest.fixture
    def git_repo_with_file_history(self, tmp_path):
        """Create a git repo with file modification history."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        (repo_path / "file.py").write_text("v1\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Create file"],
            cwd=repo_path,
            capture_output=True,
        )

        (repo_path / "file.py").write_text("v2\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify file"],
            cwd=repo_path,
            capture_output=True,
        )

        (repo_path / "file.py").write_text("v3\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify again"],
            cwd=repo_path,
            capture_output=True,
        )

        (repo_path / "other.py").write_text("other\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add other file"],
            cwd=repo_path,
            capture_output=True,
        )

        return {"path": repo_path}

    def test_get_file_history_returns_commits(self, git_repo_with_file_history):
        """Test get_file_history returns commits affecting the file."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_file_history["path"])
        result = service.get_file_history("file.py")

        assert result.path == "file.py"
        assert result.total_count == 3
        assert len(result.commits) == 3

    def test_get_file_history_respects_limit(self, git_repo_with_file_history):
        """Test get_file_history respects limit parameter."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_file_history["path"])
        result = service.get_file_history("file.py", limit=2)

        assert len(result.commits) == 2
        assert result.truncated is True

    def test_get_file_history_commit_structure(self, git_repo_with_file_history):
        """Test get_file_history returns proper FileHistoryCommit structure."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_file_history["path"])
        result = service.get_file_history("file.py")

        for commit in result.commits:
            assert hasattr(commit, "hash")
            assert hasattr(commit, "short_hash")
            assert hasattr(commit, "author_name")
            assert hasattr(commit, "author_date")
            assert hasattr(commit, "subject")
            assert hasattr(commit, "insertions")
            assert hasattr(commit, "deletions")
            assert len(commit.hash) == 40

    def test_get_file_history_follows_renames(self, git_repo_with_file_history):
        """Test get_file_history follows file renames when follow_renames=True."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        repo_path = git_repo_with_file_history["path"]
        subprocess.run(
            ["git", "mv", "file.py", "renamed.py"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Rename file"],
            cwd=repo_path,
            capture_output=True,
        )

        service = GitOperationsService(repo_path)

        result = service.get_file_history("renamed.py", follow_renames=True)
        assert result.total_count == 4

        result_no_follow = service.get_file_history("renamed.py", follow_renames=False)
        assert result_no_follow.total_count == 1

    def test_get_file_history_order(self, git_repo_with_file_history):
        """Test get_file_history returns commits in reverse chronological order."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_file_history["path"])
        result = service.get_file_history("file.py")

        assert result.commits[0].subject == "Modify again"
        assert result.commits[1].subject == "Modify file"
        assert result.commits[2].subject == "Create file"

    def test_get_file_history_invalid_file(self, git_repo_with_file_history):
        """Test get_file_history with nonexistent file returns empty."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_file_history["path"])
        result = service.get_file_history("nonexistent.py")

        assert result.total_count == 0
        assert len(result.commits) == 0


class TestSearchCommits:
    """Tests for search_commits method (Story #556)."""

    @pytest.fixture
    def git_repo_with_messages(self, tmp_path):
        """Create a git repo with searchable commit messages."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "dev@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Dev User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create commits with specific messages
        messages = [
            "fix: JIRA-123 authentication bug",
            "feat: add user login functionality",
            "refactor: improve database connection",
            "fix: JIRA-456 security vulnerability",
            "docs: update README",
        ]

        for i, msg in enumerate(messages):
            (repo_path / f"file{i}.py").write_text(f"content {i}\n")
            subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=repo_path,
                capture_output=True,
            )

        return {"path": repo_path, "messages": messages}

    def test_search_commits_basic_text(self, git_repo_with_messages):
        """Test search_commits finds commits with matching text."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_messages["path"])
        result = service.search_commits("authentication")

        assert result.total_matches >= 1
        assert len(result.matches) >= 1
        assert "authentication" in result.matches[0].subject.lower()
        assert result.query == "authentication"
        assert result.is_regex is False

    def test_search_commits_case_insensitive(self, git_repo_with_messages):
        """Test search_commits is case insensitive by default."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_messages["path"])
        result = service.search_commits("AUTHENTICATION")

        assert result.total_matches >= 1

    def test_search_commits_with_regex(self, git_repo_with_messages):
        """Test search_commits with regex pattern."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_messages["path"])
        result = service.search_commits("JIRA-[0-9]+", is_regex=True)

        assert result.total_matches == 2
        assert result.is_regex is True

    def test_search_commits_filter_by_author(self, git_repo_with_messages, tmp_path):
        """Test search_commits filters by author."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        repo_path = git_repo_with_messages["path"]
        subprocess.run(
            ["git", "config", "user.email", "other@example.com"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Other User"],
            cwd=repo_path,
            capture_output=True,
        )
        (repo_path / "newfile.py").write_text("new content")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "fix: another bug fix"],
            cwd=repo_path,
            capture_output=True,
        )

        service = GitOperationsService(repo_path)
        result = service.search_commits("fix", author="other@example.com")

        assert result.total_matches == 1
        assert result.matches[0].author_email == "other@example.com"

    def test_search_commits_filter_by_date_range(self, git_repo_with_messages):
        """Test search_commits filters by date range."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_messages["path"])
        result = service.search_commits("fix", since="2020-01-01", until="2020-01-02")

        assert result.total_matches == 0

    def test_search_commits_respects_limit(self, git_repo_with_messages):
        """Test search_commits respects limit parameter."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_messages["path"])
        result = service.search_commits("fix", limit=1)

        assert len(result.matches) <= 1
        assert result.truncated is True

    def test_search_commits_result_structure(self, git_repo_with_messages):
        """Test search_commits returns proper CommitSearchResult structure."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_messages["path"])
        result = service.search_commits("fix")

        assert hasattr(result, "query")
        assert hasattr(result, "is_regex")
        assert hasattr(result, "matches")
        assert hasattr(result, "total_matches")
        assert hasattr(result, "truncated")
        assert hasattr(result, "search_time_ms")
        assert result.search_time_ms >= 0

    def test_search_commits_match_structure(self, git_repo_with_messages):
        """Test search_commits returns proper CommitSearchMatch structure."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_messages["path"])
        result = service.search_commits("fix")

        match = result.matches[0]
        assert hasattr(match, "hash")
        assert hasattr(match, "short_hash")
        assert hasattr(match, "author_name")
        assert hasattr(match, "author_email")
        assert hasattr(match, "author_date")
        assert hasattr(match, "subject")
        assert hasattr(match, "body")
        assert hasattr(match, "match_highlights")
        assert len(match.hash) == 40

    def test_search_commits_no_matches(self, git_repo_with_messages):
        """Test search_commits returns empty result when no matches."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_messages["path"])
        result = service.search_commits("nonexistent_text_xyz123")

        assert result.total_matches == 0
        assert len(result.matches) == 0
        assert result.truncated is False


class TestSearchDiffs:
    """Tests for search_diffs method (Story #556 - pickaxe search)."""

    @pytest.fixture
    def git_repo_with_code_changes(self, tmp_path):
        """Create a git repo with code changes for pickaxe search."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "dev@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Dev User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create initial commit
        (repo_path / "auth.py").write_text(
            "def authenticate(user):\n    return False\n"
        )
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial auth"],
            cwd=repo_path,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        first_hash = result.stdout.strip()

        # Second commit - add a function
        (repo_path / "auth.py").write_text(
            "def authenticate(user):\n    return False\n\n"
            "def validateToken(token):\n    return True\n"
        )
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add token validation"],
            cwd=repo_path,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        second_hash = result.stdout.strip()

        # Third commit - add another file with same function name
        (repo_path / "utils.py").write_text(
            "def validateToken(token):\n    return check(token)\n"
        )
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add utils with token check"],
            cwd=repo_path,
            capture_output=True,
        )

        return {"path": repo_path, "first_hash": first_hash, "second_hash": second_hash}

    def test_search_diffs_literal_string(self, git_repo_with_code_changes):
        """Test search_diffs finds commits that added/removed literal string."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])
        result = service.search_diffs(search_string="validateToken")

        assert result.total_matches >= 1
        assert result.search_term == "validateToken"
        assert result.is_regex is False

    def test_search_diffs_regex_pattern(self, git_repo_with_code_changes):
        """Test search_diffs with regex pattern (-G flag)."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])
        result = service.search_diffs(search_pattern="def.*Token", is_regex=True)

        assert result.total_matches >= 1
        assert result.is_regex is True

    def test_search_diffs_filter_by_path(self, git_repo_with_code_changes):
        """Test search_diffs filters by path."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])
        result = service.search_diffs(search_string="validateToken", path="auth.py")

        # Should only find validateToken in auth.py
        for match in result.matches:
            assert "auth.py" in match.files_changed

    def test_search_diffs_filter_by_date_range(self, git_repo_with_code_changes):
        """Test search_diffs filters by date range."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])
        result = service.search_diffs(
            search_string="validateToken",
            since="2020-01-01",
            until="2020-01-02",
        )

        assert result.total_matches == 0

    def test_search_diffs_respects_limit(self, git_repo_with_code_changes):
        """Test search_diffs respects limit parameter."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])
        result = service.search_diffs(search_string="def", limit=1)

        assert len(result.matches) <= 1

    def test_search_diffs_mutual_exclusivity(self, git_repo_with_code_changes):
        """Test search_diffs validates mutual exclusivity of params."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])

        with pytest.raises(ValueError, match="mutually exclusive"):
            service.search_diffs(
                search_string="validateToken",
                search_pattern="def.*Token",
            )

    def test_search_diffs_requires_search_term(self, git_repo_with_code_changes):
        """Test search_diffs requires either search_string or search_pattern."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])

        with pytest.raises(ValueError, match="either search_string or search_pattern"):
            service.search_diffs()

    def test_search_diffs_result_structure(self, git_repo_with_code_changes):
        """Test search_diffs returns proper DiffSearchResult structure."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])
        result = service.search_diffs(search_string="validateToken")

        assert hasattr(result, "search_term")
        assert hasattr(result, "is_regex")
        assert hasattr(result, "matches")
        assert hasattr(result, "total_matches")
        assert hasattr(result, "truncated")
        assert hasattr(result, "search_time_ms")
        assert result.search_time_ms >= 0

    def test_search_diffs_match_structure(self, git_repo_with_code_changes):
        """Test search_diffs returns proper DiffSearchMatch structure."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])
        result = service.search_diffs(search_string="validateToken")

        match = result.matches[0]
        assert hasattr(match, "hash")
        assert hasattr(match, "short_hash")
        assert hasattr(match, "author_name")
        assert hasattr(match, "author_date")
        assert hasattr(match, "subject")
        assert hasattr(match, "files_changed")
        assert hasattr(match, "diff_snippet")
        assert len(match.hash) == 40

    def test_search_diffs_no_matches(self, git_repo_with_code_changes):
        """Test search_diffs returns empty result when no matches."""
        from code_indexer.global_repos.git_operations import GitOperationsService

        service = GitOperationsService(git_repo_with_code_changes["path"])
        result = service.search_diffs(search_string="nonexistent_function_xyz123")

        assert result.total_matches == 0
        assert len(result.matches) == 0
        assert result.truncated is False
