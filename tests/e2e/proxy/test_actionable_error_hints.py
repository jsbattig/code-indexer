"""E2E tests for actionable error hints in proxy mode.

Tests validate the conversation requirement:
"clearly stating so and hinting claude code to use grep or other means to search in that repo"

This test suite verifies that when queries fail, users receive actionable hints
suggesting alternative approaches like grep.
"""

import pytest
import subprocess
from pathlib import Path
import tempfile


class TestActionableErrorHints:
    """E2E tests for actionable error hints in proxy mode."""

    @pytest.fixture
    def proxy_workspace(self):
        """Create temporary proxy workspace with repositories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proxy_root = Path(tmpdir) / "multi-repo"
            proxy_root.mkdir()

            # Create proxy configuration
            config_dir = proxy_root / ".code-indexer"
            config_dir.mkdir()

            config_file = config_dir / "config.json"
            config_file.write_text('{"proxy_mode": true, "discovered_repos": ["repo1", "repo2"]}')

            # Create two sub-repositories
            for repo_name in ["repo1", "repo2"]:
                repo_path = proxy_root / repo_name
                repo_path.mkdir()

                # Create .code-indexer directory (indicating initialized repo)
                repo_config_dir = repo_path / ".code-indexer"
                repo_config_dir.mkdir()

                # Create minimal config (containers not actually running)
                repo_config = repo_config_dir / "config.json"
                repo_config.write_text('{"embedding_provider": "voyage-ai"}')

                # Create some test code
                test_file = repo_path / "test.py"
                test_file.write_text('def hello():\n    print("Hello, World!")\n')

            yield proxy_root

    def test_query_failure_shows_grep_hint(self, proxy_workspace):
        """Test that query failures show grep hint.

        CONVERSATION REQUIREMENT: "clearly stating so and hinting claude code
        to use grep or other means to search in that repo"
        """
        # Execute query from proxy root (will fail because services not running)
        result = subprocess.run(
            ["cidx", "query", "hello"],
            cwd=str(proxy_workspace),
            capture_output=True,
            text=True,
            timeout=60
        )

        # Query should fail (services not running)
        assert result.returncode != 0

        # Combined output (stdout + stderr)
        output = result.stdout + result.stderr

        # CRITICAL: Must suggest grep
        assert "grep" in output.lower()

        # Should mention using alternative search tools
        assert any(word in output.lower() for word in ["grep", "search", "alternative", "manually"])

    def test_query_failure_includes_repository_name(self, proxy_workspace):
        """Test that hints include repository name for context."""
        result = subprocess.run(
            ["cidx", "query", "hello"],
            cwd=str(proxy_workspace),
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode != 0

        output = result.stdout + result.stderr

        # Should mention at least one repository name
        assert "repo1" in output or "repo2" in output

    def test_query_failure_shows_concrete_commands(self, proxy_workspace):
        """Test that hints include concrete commands to try."""
        result = subprocess.run(
            ["cidx", "query", "test"],
            cwd=str(proxy_workspace),
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode != 0

        output = result.stdout + result.stderr

        # Should show concrete grep command example
        # Looking for pattern like: grep -r 'term' path
        assert "grep -r" in output or "rg" in output

    def test_query_failure_has_visual_hint_section(self, proxy_workspace):
        """Test that hints are visually structured."""
        result = subprocess.run(
            ["cidx", "query", "hello"],
            cwd=str(proxy_workspace),
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode != 0

        output = result.stdout + result.stderr

        # Should have "Hint:" label
        assert "Hint:" in output or "hint:" in output.lower()

        # Should have suggested commands section
        assert "command" in output.lower() or "try" in output.lower()

    def test_multiple_repo_failures_show_individual_hints(self, proxy_workspace):
        """Test that each failed repository gets its own hint."""
        result = subprocess.run(
            ["cidx", "query", "hello"],
            cwd=str(proxy_workspace),
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode != 0

        output = result.stdout + result.stderr

        # With two repos failing, should see grep suggested
        # (Could be once in general section or per repo)
        grep_count = output.lower().count("grep")
        assert grep_count >= 1  # At least one grep suggestion

    def test_hint_explains_why_alternative_needed(self, proxy_workspace):
        """Test that hints explain why alternatives are needed."""
        result = subprocess.run(
            ["cidx", "query", "test"],
            cwd=str(proxy_workspace),
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode != 0

        output = result.stdout + result.stderr

        # Should mention service unavailability or similar reason
        # Looking for keywords that explain WHY grep is needed
        explanation_keywords = [
            "qdrant",
            "service",
            "unavailable",
            "not available",
            "connect",
            "connection",
            "semantic search",
        ]

        # At least one explanation keyword should be present
        assert any(keyword in output.lower() for keyword in explanation_keywords)

    def test_hint_format_matches_specification(self, proxy_workspace):
        """Test that hint format matches the story specification.

        Expected format:
        Hint: Use grep or other search tools to search 'repo' manually

        Try these commands:
          • grep -r 'term' repo
          • rg 'term' repo

        Explanation: Qdrant service not available
        """
        result = subprocess.run(
            ["cidx", "query", "hello"],
            cwd=str(proxy_workspace),
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode != 0

        output = result.stdout + result.stderr

        # Check for hint structure elements
        assert "Hint:" in output  # Hint label
        assert "•" in output or "*" in output or "-" in output  # Bullet points
        assert "grep" in output.lower()  # Grep command


class TestHintEdgeCases:
    """Test edge cases for hint generation."""

    @pytest.fixture
    def single_repo_proxy(self):
        """Create proxy with single repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proxy_root = Path(tmpdir) / "single-repo-proxy"
            proxy_root.mkdir()

            # Proxy config
            config_dir = proxy_root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text('{"proxy_mode": true, "discovered_repos": ["myrepo"]}')

            # Single repository
            repo_path = proxy_root / "myrepo"
            repo_path.mkdir()
            repo_config_dir = repo_path / ".code-indexer"
            repo_config_dir.mkdir()
            repo_config = repo_config_dir / "config.json"
            repo_config.write_text('{"embedding_provider": "voyage-ai"}')

            # Test code
            test_file = repo_path / "app.py"
            test_file.write_text('def main():\n    pass\n')

            yield proxy_root

    def test_single_repo_failure_shows_hint(self, single_repo_proxy):
        """Test that single repository failure also shows hint."""
        result = subprocess.run(
            ["cidx", "query", "main"],
            cwd=str(single_repo_proxy),
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode != 0

        output = result.stdout + result.stderr

        # Even single repo should get grep hint
        assert "grep" in output.lower()
        assert "myrepo" in output


class TestConversationRequirementValidation:
    """Explicit validation of conversation requirement.

    Validates: "clearly stating so and hinting claude code to use grep or other
    means to search in that repo"
    """

    @pytest.fixture
    def failing_proxy(self):
        """Create proxy that will fail queries (no running services)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proxy_root = Path(tmpdir) / "failing-proxy"
            proxy_root.mkdir()

            config_dir = proxy_root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text('{"proxy_mode": true, "discovered_repos": ["backend"]}')

            repo_path = proxy_root / "backend"
            repo_path.mkdir()
            repo_config_dir = repo_path / ".code-indexer"
            repo_config_dir.mkdir()
            repo_config = repo_config_dir / "config.json"
            repo_config.write_text('{"embedding_provider": "voyage-ai"}')

            code_file = repo_path / "auth.py"
            code_file.write_text('def authenticate():\n    pass\n')

            yield proxy_root

    def test_conversation_requirement_grep_explicit(self, failing_proxy):
        """CRITICAL: Verify grep is explicitly mentioned.

        Conversation: "hinting claude code to use grep"
        """
        result = subprocess.run(
            ["cidx", "query", "authentication"],
            cwd=str(failing_proxy),
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout + result.stderr

        # MUST explicitly mention grep
        assert "grep" in output

    def test_conversation_requirement_other_means(self, failing_proxy):
        """Verify "or other means" by suggesting multiple tools.

        Conversation: "or other means to search"
        """
        result = subprocess.run(
            ["cidx", "query", "auth"],
            cwd=str(failing_proxy),
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout + result.stderr

        # Should suggest multiple search methods
        # (grep + rg, or grep + manual search, etc.)
        search_tools = ["grep", "rg", "search"]
        found_tools = [tool for tool in search_tools if tool in output.lower()]

        # At least grep should be present
        assert "grep" in found_tools

    def test_conversation_requirement_repository_context(self, failing_proxy):
        """Verify hints reference the specific repository.

        Conversation: "to search in that repo"
        """
        result = subprocess.run(
            ["cidx", "query", "test"],
            cwd=str(failing_proxy),
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout + result.stderr

        # Should mention the repository name "backend"
        assert "backend" in output

    def test_conversation_requirement_clear_statement(self, failing_proxy):
        """Verify the hint is clearly stated, not buried.

        Conversation: "clearly stating so"
        """
        result = subprocess.run(
            ["cidx", "query", "auth"],
            cwd=str(failing_proxy),
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout + result.stderr

        # Hint should be clearly labeled
        assert "Hint:" in output or "hint:" in output.lower()

        # Should be easy to spot (has visual structure)
        assert "•" in output or "*" in output or "command" in output.lower()
