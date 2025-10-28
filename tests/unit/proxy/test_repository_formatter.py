"""Unit tests for RepositoryPrefixFormatter (Story 5.4).

Tests repository identification and prefix formatting for multiplexed output.
"""

import pytest
from code_indexer.proxy.repository_formatter import RepositoryPrefixFormatter


class TestRepositoryPrefixFormatter:
    """Test repository prefix formatting for output identification."""

    @pytest.fixture
    def proxy_root(self, tmp_path):
        """Create proxy root directory."""
        proxy_root = tmp_path / "proxy-root"
        proxy_root.mkdir()
        return proxy_root

    @pytest.fixture
    def formatter(self, proxy_root):
        """Create formatter with proxy root."""
        return RepositoryPrefixFormatter(proxy_root)

    def test_format_prefix_relative_path(self, formatter, proxy_root):
        """Test formatting repository path as prefix using relative path."""
        # Create repository directory
        repo_path = proxy_root / "backend" / "auth-service"
        repo_path.mkdir(parents=True)

        # Format prefix
        prefix = formatter.format_prefix(str(repo_path), use_relative=True)

        # Verify format: [backend/auth-service]
        assert prefix == "[backend/auth-service]"

    def test_format_prefix_absolute_path(self, formatter, proxy_root):
        """Test formatting repository path using absolute path."""
        repo_path = proxy_root / "backend" / "auth-service"
        repo_path.mkdir(parents=True)

        # Format with absolute path
        prefix = formatter.format_prefix(str(repo_path), use_relative=False)

        # Should contain full path
        assert prefix == f"[{repo_path}]"

    def test_format_prefix_single_level(self, formatter, proxy_root):
        """Test formatting single-level repository path."""
        repo_path = proxy_root / "web-app"
        repo_path.mkdir()

        prefix = formatter.format_prefix(str(repo_path), use_relative=True)

        assert prefix == "[web-app]"

    def test_format_prefix_deep_nesting(self, formatter, proxy_root):
        """Test formatting deeply nested repository path."""
        repo_path = proxy_root / "backend" / "services" / "auth" / "v2"
        repo_path.mkdir(parents=True)

        prefix = formatter.format_prefix(str(repo_path), use_relative=True)

        assert prefix == "[backend/services/auth/v2]"

    def test_format_output_line(self, formatter, proxy_root):
        """Test formatting complete output line with prefix."""
        repo_path = proxy_root / "backend" / "auth-service"
        repo_path.mkdir(parents=True)
        content = "Change detected: src/auth/login.py"

        # Format complete line
        output_line = formatter.format_output_line(str(repo_path), content)

        # Verify format: [repo] content
        assert (
            output_line == "[backend/auth-service] Change detected: src/auth/login.py"
        )

    def test_format_output_line_with_multiline_content(self, formatter, proxy_root):
        """Test formatting output line with multiline content."""
        repo_path = proxy_root / "frontend"
        repo_path.mkdir()
        content = "Re-indexing 1 file...\nIndexing complete"

        # Format line - should only format first line
        output_line = formatter.format_output_line(str(repo_path), content)

        # Each line should get prefix
        assert output_line == "[frontend] Re-indexing 1 file...\nIndexing complete"

    def test_get_relative_path_under_proxy_root(self, formatter, proxy_root):
        """Test relative path calculation for repository under proxy root."""
        repo_path = proxy_root / "backend" / "user-service"
        repo_path.mkdir(parents=True)

        relative = formatter._get_relative_path(str(repo_path))

        assert relative == "backend/user-service"

    def test_get_relative_path_outside_proxy_root(self, formatter, tmp_path):
        """Test relative path calculation for repository outside proxy root."""
        # Create repository outside proxy root
        external_repo = tmp_path / "external" / "repo"
        external_repo.mkdir(parents=True)

        # Should return path as-is when not under proxy root
        relative = formatter._get_relative_path(str(external_repo))

        # Should return original path
        assert str(external_repo) in relative

    def test_format_prefix_handles_symlinks(self, formatter, proxy_root):
        """Test prefix formatting with symlinked repositories."""
        # Create real directory
        real_repo = proxy_root / "real-repo"
        real_repo.mkdir()

        # Create symlink
        symlink_repo = proxy_root / "symlink-repo"
        symlink_repo.symlink_to(real_repo)

        # Format prefix for symlink - should resolve to real path
        prefix = formatter.format_prefix(str(symlink_repo), use_relative=True)

        # Should work with symlinks
        assert "[" in prefix and "]" in prefix

    def test_format_empty_content(self, formatter, proxy_root):
        """Test formatting with empty content."""
        repo_path = proxy_root / "backend"
        repo_path.mkdir()

        output_line = formatter.format_output_line(str(repo_path), "")

        # Should still format properly
        assert output_line == "[backend] "

    def test_format_content_with_special_characters(self, formatter, proxy_root):
        """Test formatting content with special characters."""
        repo_path = proxy_root / "backend"
        repo_path.mkdir()
        content = "Error: [CRITICAL] Failed to parse file: test.py (line 42)"

        output_line = formatter.format_output_line(str(repo_path), content)

        # Should preserve special characters in content
        assert (
            output_line
            == "[backend] Error: [CRITICAL] Failed to parse file: test.py (line 42)"
        )

    def test_multiple_repositories_unique_prefixes(self, proxy_root):
        """Test that different repositories get unique prefixes."""
        formatter = RepositoryPrefixFormatter(proxy_root)

        # Create multiple repositories
        repos = [
            proxy_root / "backend" / "auth",
            proxy_root / "backend" / "user",
            proxy_root / "frontend" / "web",
        ]

        for repo in repos:
            repo.mkdir(parents=True)

        # Get prefixes for all repositories
        prefixes = [formatter.format_prefix(str(repo)) for repo in repos]

        # All prefixes should be unique
        assert len(prefixes) == len(set(prefixes))
        assert "[backend/auth]" in prefixes
        assert "[backend/user]" in prefixes
        assert "[frontend/web]" in prefixes

    def test_format_prefix_default_uses_relative(self, formatter, proxy_root):
        """Test that format_prefix uses relative path by default."""
        repo_path = proxy_root / "backend"
        repo_path.mkdir()

        # Call without use_relative parameter (should default to True)
        prefix = formatter.format_prefix(str(repo_path))

        # Should use relative path
        assert prefix == "[backend]"

    def test_format_with_windows_style_paths(self, formatter, proxy_root):
        """Test formatting with Windows-style paths (if applicable)."""
        # This test ensures cross-platform compatibility
        repo_path = proxy_root / "backend" / "auth-service"
        repo_path.mkdir(parents=True)

        # Use forward slashes in output regardless of OS
        prefix = formatter.format_prefix(str(repo_path), use_relative=True)

        # Should use forward slashes
        assert "/" in prefix or "\\" not in prefix
        assert "backend" in prefix
        assert "auth-service" in prefix
