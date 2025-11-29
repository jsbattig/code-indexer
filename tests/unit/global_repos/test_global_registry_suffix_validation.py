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

    def test_reserved_names_still_checked_before_suffix_validation(self, tmp_path):
        """
        Test that reserved name check happens before suffix validation.

        Reserved names should be rejected even if they have -global suffix
        (unless allow_reserved=True).
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # This has -global suffix BUT is a reserved name
        # Should raise ReservedNameError, not ValueError for missing suffix
        from code_indexer.global_repos.global_registry import ReservedNameError

        with pytest.raises(ReservedNameError) as exc_info:
            registry.register_global_repo(
                repo_name="cidx-meta",
                alias_name="cidx-meta-global",  # Reserved name
                repo_url="https://github.com/org/cidx-meta",
                index_path=str(tmp_path / "index"),
                allow_reserved=False,
            )

        error_msg = str(exc_info.value)
        assert "reserved" in error_msg.lower()

    def test_allow_reserved_still_requires_global_suffix(self, tmp_path):
        """
        Test that allow_reserved=True bypasses reserved check but NOT suffix validation.

        Even with allow_reserved=True, the -global suffix should still be required.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Even with allow_reserved=True, suffix validation should still apply
        with pytest.raises(ValueError) as exc_info:
            registry.register_global_repo(
                repo_name="cidx-meta",
                alias_name="cidx-meta",  # Missing -global suffix
                repo_url=None,
                index_path=str(tmp_path / "index"),
                allow_reserved=True,  # Bypasses reserved check but not suffix check
            )

        error_msg = str(exc_info.value)
        assert "must end with '-global' suffix" in error_msg
