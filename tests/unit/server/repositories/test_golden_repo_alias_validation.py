"""
Unit tests for golden repository alias validation security.

Tests the security controls that prevent path traversal attacks at the
registration layer by validating aliases BEFORE any filesystem operations.

This is a defense-in-depth measure complementing the existing validation
in get_actual_repo_path().
"""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
)
from src.code_indexer.server.repositories.background_jobs import BackgroundJobManager


class TestGoldenRepoAliasValidationSecurity:
    r"""
    Security tests verifying alias validation at registration layer.

    These tests verify that add_golden_repo properly rejects dangerous aliases
    containing path traversal characters (.., /, \) before any filesystem
    operations or metadata updates.
    """

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with temp directory and mocked background job manager."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)
        # Inject mock BackgroundJobManager
        mock_bg_manager = MagicMock(spec=BackgroundJobManager)
        mock_bg_manager.submit_job.return_value = "test-job-id-12345"
        manager.background_job_manager = mock_bg_manager
        return manager

    def test_rejects_alias_with_double_dots(self, golden_repo_manager):
        """
        Test that add_golden_repo rejects aliases containing '..' (path traversal).

        Security Issue: Alias like 'foo/../bar' could be used to escape the
        golden repos directory during filesystem operations.

        Expected Behavior: Should raise ValueError immediately at registration,
        before any filesystem operations or metadata updates.
        """
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Attempt to register golden repo with dangerous alias
            with pytest.raises(
                ValueError,
                match="Invalid alias.*cannot contain path traversal characters.*\\.\\.",
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias="foo/../bar",  # Path traversal attempt
                    default_branch="main",
                )

    def test_rejects_alias_with_forward_slash(self, golden_repo_manager):
        """
        Test that add_golden_repo rejects aliases containing '/' (path separator).

        Security Issue: Alias like 'foo/bar' could create nested directories
        or reference arbitrary paths during filesystem operations.

        Expected Behavior: Should raise ValueError immediately at registration,
        before any filesystem operations or metadata updates.
        """
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Attempt to register golden repo with dangerous alias
            with pytest.raises(
                ValueError,
                match="Invalid alias.*cannot contain path traversal characters.*/",
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias="foo/bar",  # Path separator attempt
                    default_branch="main",
                )

    def test_rejects_alias_with_backslash(self, golden_repo_manager):
        """
        Test that add_golden_repo rejects aliases containing '\\' (Windows path separator).

        Security Issue: Alias like 'foo\\bar' could create nested directories
        or reference arbitrary paths on Windows systems.

        Expected Behavior: Should raise ValueError immediately at registration,
        before any filesystem operations or metadata updates.
        """
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Attempt to register golden repo with dangerous alias
            with pytest.raises(
                ValueError,
                match="Invalid alias.*cannot contain path traversal characters.*\\\\",
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias="foo\\bar",  # Windows path separator attempt
                    default_branch="main",
                )

    def test_rejects_complex_path_traversal(self, golden_repo_manager):
        """
        Test that add_golden_repo rejects complex path traversal attempts.

        Security Issue: Combinations like '../../etc/passwd' could be used
        to escape the golden repos directory and access system files.

        Expected Behavior: Should raise ValueError immediately at registration.
        """
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Attempt to register golden repo with complex path traversal
            with pytest.raises(
                ValueError,
                match="Invalid alias.*cannot contain path traversal characters.*\\.\\.",
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias="../../etc/passwd",  # Complex path traversal
                    default_branch="main",
                )

    def test_validation_happens_before_filesystem_operations(
        self, golden_repo_manager
    ):
        """
        Test that alias validation happens BEFORE any filesystem operations.

        Security Principle: Fail-fast at the earliest possible point.

        Expected Behavior: Should raise ValueError before background job is submitted
        (since validation happens synchronously before job submission).
        """
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Track whether background job manager was called
            original_submit = golden_repo_manager.background_job_manager.submit_job
            call_count = {"count": 0}

            def tracking_submit(*args, **kwargs):
                call_count["count"] += 1
                return original_submit(*args, **kwargs)

            golden_repo_manager.background_job_manager.submit_job = tracking_submit

            # Attempt to register with dangerous alias
            with pytest.raises(
                ValueError,
                match="Invalid alias.*cannot contain path traversal characters",
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias="../escape",
                    default_branch="main",
                )

            # Verify background job was NEVER submitted
            assert call_count["count"] == 0

    def test_validation_happens_before_git_validation(
        self, golden_repo_manager
    ):
        """
        Test that alias validation happens BEFORE git repository validation.

        Security Principle: Don't waste resources validating a repository
        if the alias itself is invalid.

        Expected Behavior: Should raise ValueError before calling _validate_git_repository.
        """
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            # Attempt to register with dangerous alias
            with pytest.raises(
                ValueError,
                match="Invalid alias.*cannot contain path traversal characters",
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias="foo/bar",
                    default_branch="main",
                )

            # Verify _validate_git_repository was NEVER called
            mock_validate.assert_not_called()

    def test_error_message_is_clear_and_security_focused(
        self, golden_repo_manager
    ):
        """
        Test that error messages clearly indicate the security violation.

        User Experience: Error messages should be helpful and explain WHY
        the alias was rejected.

        Expected Behavior: Error message should mention 'path traversal' or
        'invalid alias' and specify the problematic characters.
        """
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            try:
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias="../dangerous",
                    default_branch="main",
                )
                pytest.fail("Expected ValueError was not raised")
            except ValueError as e:
                error_msg = str(e)
                # Verify error message contains security context
                assert "Invalid alias" in error_msg
                assert "path traversal" in error_msg
                # Verify error message identifies the problematic characters
                assert ".." in error_msg

    def test_error_messages_identify_specific_violation(
        self, golden_repo_manager
    ):
        r"""
        Test that error messages identify the specific path traversal character.

        User Experience: Each type of violation should have a clear error message
        indicating which character is problematic.

        Expected Behavior: Error messages should mention the specific character (.., /, or \).
        """
        test_cases = [
            ("foo/../bar", ".."),
            ("foo/bar", "/"),
            ("foo\\bar", "\\"),
        ]

        for alias, expected_char in test_cases:
            with patch.object(
                golden_repo_manager, "_validate_git_repository"
            ) as mock_validate:
                mock_validate.return_value = True

                try:
                    golden_repo_manager.add_golden_repo(
                        repo_url="https://github.com/test/repo.git",
                        alias=alias,
                        default_branch="main",
                    )
                    pytest.fail(
                        f"Expected ValueError was not raised for alias '{alias}'"
                    )
                except ValueError as e:
                    error_msg = str(e)
                    # Verify error message contains the specific problematic character
                    assert (
                        expected_char in error_msg
                    ), f"Error message should mention '{expected_char}' for alias '{alias}'"


class TestGoldenRepoAliasValidationRegression:
    """
    Regression tests to ensure valid aliases continue working.

    These tests should PASS both before and after the fix.
    """

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with temp directory and mocked background job manager."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)
        # Inject mock BackgroundJobManager
        mock_bg_manager = MagicMock(spec=BackgroundJobManager)
        mock_bg_manager.submit_job.return_value = "test-job-id-12345"
        manager.background_job_manager = mock_bg_manager
        return manager

    def test_accepts_valid_aliases(self, golden_repo_manager):
        """
        Test that add_golden_repo accepts valid aliases without special characters.

        Regression Test: Ensure validation doesn't reject legitimate aliases.

        Expected Behavior: Should accept aliases with alphanumeric, hyphen,
        underscore, and dot characters (when not '..' sequence).
        """
        valid_aliases = [
            "my-repo",
            "my_repo",
            "myRepo123",
            "repo.v2",  # Single dot is OK
            "test-repo-v1.0.0",  # Multiple single dots are OK
        ]

        for alias in valid_aliases:
            with patch.object(
                golden_repo_manager, "_validate_git_repository"
            ) as mock_validate:
                mock_validate.return_value = True

                # Should not raise ValueError - will return job_id
                result = golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo.git",
                    alias=alias,
                    default_branch="main",
                )

                # Verify job_id was returned (mock returns "test-job-id-12345")
                assert result == "test-job-id-12345"

                # Clean up for next iteration
                if alias in golden_repo_manager.golden_repos:
                    del golden_repo_manager.golden_repos[alias]
