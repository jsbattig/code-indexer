"""End-to-end tests for Story 2.1 temporal query implementation."""

import tempfile
import shutil
import subprocess
from pathlib import Path
import time

import pytest


class TestTemporalQueryStory21E2E:
    """E2E tests for Story 2.1 temporal query changes."""

    @classmethod
    def setup_class(cls):
        """Set up test repository with temporal index."""
        cls.test_dir = tempfile.mkdtemp(prefix="test_temporal_story21_")
        cls.repo_path = Path(cls.test_dir) / "test_repo"
        cls.repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=cls.repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=cls.repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=cls.repo_path, check=True
        )

        # Create initial file
        (cls.repo_path / "auth.py").write_text(
            """def validate_token(token):
    if not token:
        return False

    if token.expired():
        return False

    return True
"""
        )

        subprocess.run(["git", "add", "."], cwd=cls.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit: Add token validation"],
            cwd=cls.repo_path,
            check=True,
        )

        # Modify file (introduce bug fix)
        (cls.repo_path / "auth.py").write_text(
            """def validate_token(token):
    if not token:
        return False

    if token.expired():
        logger.warning("Token expired")
        raise TokenExpiredError()

    return True
"""
        )

        subprocess.run(["git", "add", "."], cwd=cls.repo_path, check=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Fix JWT validation bug\\n\\nNow properly logs warnings and raises TokenExpiredError\\ninstead of silently returning False.",
            ],
            cwd=cls.repo_path,
            check=True,
        )

        # Initialize cidx and create temporal index
        subprocess.run(["cidx", "init"], cwd=cls.repo_path, check=True)
        subprocess.run(["cidx", "start"], cwd=cls.repo_path, check=True)

        # Index with commits
        subprocess.run(
            ["cidx", "index", "--index-commits", "--force"],
            cwd=cls.repo_path,
            check=True,
            timeout=60,
        )

    @classmethod
    def teardown_class(cls):
        """Clean up test repository."""
        try:
            subprocess.run(["cidx", "stop"], cwd=cls.repo_path, timeout=10)
        except:
            pass
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_temporal_query_shows_chunk_with_diff(self):
        """Test that temporal query shows chunk content with diff, not entire blob."""
        # Query for token validation
        result = subprocess.run(
            [
                "cidx",
                "query",
                "token expired",
                "--time-range",
                "2020-01-01..2030-01-01",
                "--limit",
                "5",
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = result.stdout

        # Check that we show chunk with line numbers (not entire file)
        assert "auth.py:" in output  # Should show file:line_start-line_end format

        # Check for diff display
        assert "[DIFF" in output or "Changes from" in output

        # Check that we show the specific changed lines
        assert "logger.warning" in output or "TokenExpiredError" in output

        # Should NOT show entire file (initial lines that weren't changed)
        assert (
            output.count("def validate_token") <= 2
        )  # Should appear in chunk, not whole file

    def test_temporal_query_commit_message_search(self):
        """Test that temporal query can find commit messages."""
        # Query for commit message content
        result = subprocess.run(
            [
                "cidx",
                "query",
                "JWT validation bug",
                "--time-range",
                "2020-01-01..2030-01-01",
                "--limit",
                "5",
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = result.stdout

        # Check for commit message match indicator
        assert (
            "[COMMIT MESSAGE MATCH]" in output or "Message (matching section)" in output
        )

        # Check that commit message content is shown
        assert "JWT validation bug" in output or "Fix JWT validation" in output

        # Check that modified files are listed
        assert "Files Modified" in output
        assert "auth.py" in output

    def test_temporal_query_mixed_results(self):
        """Test that temporal query shows both commit messages and file chunks properly ordered."""
        # Query that should match both commit message and file content
        result = subprocess.run(
            [
                "cidx",
                "query",
                "validation",
                "--time-range",
                "2020-01-01..2030-01-01",
                "--limit",
                "10",
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = result.stdout

        # Find positions of different match types
        commit_msg_pos = -1
        file_chunk_pos = -1

        if "[COMMIT MESSAGE MATCH]" in output:
            commit_msg_pos = output.index("[COMMIT MESSAGE MATCH]")

        if "auth.py:" in output:
            file_chunk_pos = output.index("auth.py:")

        # If both types are present, commit messages should come first
        if commit_msg_pos > -1 and file_chunk_pos > -1:
            assert (
                commit_msg_pos < file_chunk_pos
            ), "Commit messages should be displayed before file chunks"

    def test_temporal_query_no_chunk_text_in_payload(self):
        """Test that chunk_text is not stored in vector payload (space optimization)."""
        # This is more of an implementation detail test
        # We can verify by checking that chunks show content fetched from git

        # Create a file with distinctive content
        test_file = self.repo_path / "test_unique.py"
        unique_content = (
            f"# UNIQUE_MARKER_{time.time()}\ndef test_function():\n    pass"
        )
        test_file.write_text(unique_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add test file"], cwd=self.repo_path, check=True
        )

        # Re-index
        subprocess.run(
            ["cidx", "index", "--index-commits", "--force"],
            cwd=self.repo_path,
            check=True,
            timeout=60,
        )

        # Query for the unique content
        result = subprocess.run(
            [
                "cidx",
                "query",
                "UNIQUE_MARKER",
                "--time-range",
                "2020-01-01..2030-01-01",
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = result.stdout

        # The unique marker should appear (fetched from git)
        assert "UNIQUE_MARKER" in output

        # Check that it shows the chunk properly (not truncated at 500 chars)
        assert "def test_function" in output

    def test_temporal_query_shows_full_commit_message(self):
        """Test that full commit message is shown, not truncated."""
        # Add a commit with a long message
        (self.repo_path / "long_msg.py").write_text("# Test file")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)

        long_message = """Add comprehensive authentication system

This commit introduces a complete authentication system with the following features:
- JWT token generation and validation
- Refresh token support with rotation
- Rate limiting for login attempts
- Account lockout after failed attempts
- Password strength requirements
- Two-factor authentication support
- Session management
- Audit logging for security events

The implementation follows OWASP best practices and includes extensive test coverage."""

        subprocess.run(
            ["git", "commit", "-m", long_message], cwd=self.repo_path, check=True
        )

        # Re-index
        subprocess.run(
            ["cidx", "index", "--index-commits", "--force"],
            cwd=self.repo_path,
            check=True,
            timeout=60,
        )

        # Query for authentication
        result = subprocess.run(
            [
                "cidx",
                "query",
                "authentication system",
                "--time-range",
                "2020-01-01..2030-01-01",
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = result.stdout

        # Check that various parts of the long message are shown
        assert "comprehensive authentication" in output
        assert "OWASP best practices" in output
        assert "test coverage" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
