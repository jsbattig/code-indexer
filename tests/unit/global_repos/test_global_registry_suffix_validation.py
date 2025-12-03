"""
Unit tests for GlobalRegistry -global suffix validation.

Tests Epic #520 requirement that all global repo aliases must end with '-global' suffix.
"""

import pytest
from code_indexer.global_repos.global_registry import GlobalRegistry


class TestGlobalRegistrySuffixValidation:
    """Test suite for -global suffix validation in GlobalRegistry."""

    def test_register_global_repo_accepts_valid_global_suffix(self, tmp_path):
        """
        Test that registration succeeds with valid -global suffix.

        This is the baseline behavior - should pass before and after changes.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Should succeed - has -global suffix
        registry.register_global_repo(
            repo_name="my-repo",
            alias_name="my-repo-global",
            repo_url="https://github.com/org/my-repo",
            index_path=str(tmp_path / "index"),
        )

        # Verify registration
        repo = registry.get_global_repo("my-repo-global")
        assert repo is not None
        assert repo["alias_name"] == "my-repo-global"

    def test_register_global_repo_rejects_missing_global_suffix(self, tmp_path):
        """
        Test that registration fails when alias doesn't end with -global suffix.

        Epic #520 requirement: All global repo aliases MUST end with '-global'.
        This test should FAIL initially (RED phase), then PASS after implementation (GREEN phase).
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Should raise ValueError - missing -global suffix
        with pytest.raises(ValueError) as exc_info:
            registry.register_global_repo(
                repo_name="my-repo",
                alias_name="my-repo",  # Missing -global suffix
                repo_url="https://github.com/org/my-repo",
                index_path=str(tmp_path / "index"),
            )

        # Verify error message contains both actual and expected values
        error_msg = str(exc_info.value)
        assert "must end with '-global' suffix" in error_msg
        assert "my-repo" in error_msg
        assert "my-repo-global" in error_msg

    def test_register_global_repo_rejects_wrong_suffix(self, tmp_path):
        """
        Test that registration fails with incorrect suffix (e.g., -repo, -index).

        Only '-global' suffix should be accepted.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Try various invalid suffixes
        invalid_aliases = [
            "my-repo-repo",
            "my-repo-index",
            "my-repo-golden",
            "my-repo-g",  # Incomplete suffix
        ]

        for invalid_alias in invalid_aliases:
            with pytest.raises(ValueError) as exc_info:
                registry.register_global_repo(
                    repo_name="my-repo",
                    alias_name=invalid_alias,
                    repo_url="https://github.com/org/my-repo",
                    index_path=str(tmp_path / "index"),
                )

            error_msg = str(exc_info.value)
            assert "must end with '-global' suffix" in error_msg

    # NOTE: Reserved names tests removed as part of Story #538
    # cidx-meta is now a regular golden repo, not a reserved name
