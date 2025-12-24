"""
Tests for reserved name validation in GlobalRegistry.

Tests Story #524 AC1: Well-Known Discovery Endpoint
- Reserved name 'cidx-meta-global' cannot be used for user repos
- Error message if registration attempted with reserved name
"""

import tempfile
from pathlib import Path
import pytest

from code_indexer.global_repos.global_registry import GlobalRegistry, ReservedNameError


class TestReservedNames:
    """Test reserved name validation for meta-repo discovery endpoint."""

    def test_cidx_meta_global_is_reserved(self):
        """Test that 'cidx-meta-global' cannot be registered as alias."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            # Attempt to register with reserved name
            with pytest.raises(ReservedNameError) as exc_info:
                registry.register_global_repo(
                    repo_name="my-repo",
                    alias_name="cidx-meta-global",
                    repo_url="https://github.com/user/repo.git",
                    index_path="/path/to/index",
                )

            # Verify error message is helpful
            error_msg = str(exc_info.value)
            assert "cidx-meta-global" in error_msg
            assert "reserved" in error_msg.lower()
            assert "discovery" in error_msg.lower() or "meta" in error_msg.lower()

    def test_cidx_meta_is_reserved(self):
        """Test that 'cidx-meta' alias cannot be registered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            with pytest.raises(ReservedNameError) as exc_info:
                registry.register_global_repo(
                    repo_name="my-repo",
                    alias_name="cidx-meta",
                    repo_url="https://github.com/user/repo.git",
                    index_path="/path/to/index",
                )

            error_msg = str(exc_info.value)
            assert "cidx-meta" in error_msg
            assert "reserved" in error_msg.lower()

    def test_non_reserved_names_allowed(self):
        """Test that non-reserved names work normally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            # These should all work fine
            valid_names = [
                "my-repo-global",
                "cidx-user-repo-global",
                "meta-analysis-global",
                "cidx-global",  # Not reserved
            ]

            for alias_name in valid_names:
                registry.register_global_repo(
                    repo_name=alias_name.replace("-global", ""),
                    alias_name=alias_name,
                    repo_url="https://github.com/user/repo.git",
                    index_path=f"/path/to/{alias_name}",
                )

            # Verify all registered
            repos = registry.list_global_repos()
            assert len(repos) == len(valid_names)

    def test_reserved_names_case_sensitive(self):
        """Test that reserved name check is case-sensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            # These should be allowed (different case)
            # Reserved names are lowercase only
            registry.register_global_repo(
                repo_name="CIDX-META-GLOBAL-repo",
                alias_name="CIDX-META-GLOBAL",
                repo_url="https://github.com/user/repo.git",
                index_path="/path/to/index",
            )

            repos = registry.list_global_repos()
            assert len(repos) == 1

    def test_reserved_name_in_repo_name_allowed(self):
        """Test that repo_name can contain reserved words, only alias_name is checked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            # repo_name can be anything, only alias_name is restricted
            registry.register_global_repo(
                repo_name="cidx-meta-global",  # OK in repo_name
                alias_name="my-meta-repo-global",  # Different alias
                repo_url="https://github.com/user/repo.git",
                index_path="/path/to/index",
            )

            repos = registry.list_global_repos()
            assert len(repos) == 1
            assert repos[0]["repo_name"] == "cidx-meta-global"
            assert repos[0]["alias_name"] == "my-meta-repo-global"

    def test_error_message_suggests_alternative(self):
        """Test that error message is helpful and suggests what to do."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))

            with pytest.raises(ReservedNameError) as exc_info:
                registry.register_global_repo(
                    repo_name="my-meta-repo",
                    alias_name="cidx-meta-global",
                    repo_url="https://github.com/user/repo.git",
                    index_path="/path/to/index",
                )

            error_msg = str(exc_info.value)
            # Should explain what the reserved name is for
            assert any(
                word in error_msg.lower()
                for word in ["discovery", "meta-directory", "catalog"]
            )
            # Should suggest alternative (choose different name)
            assert any(
                word in error_msg.lower()
                for word in ["choose", "use", "different", "another"]
            )
