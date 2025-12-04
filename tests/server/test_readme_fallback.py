"""
Unit tests for README fallback mechanism in meta description hook.

Tests the README fallback that copies repository README to meta directory
when Claude CLI is unavailable or fails, ensuring cidx-meta always has
searchable content.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil


@pytest.fixture
def temp_golden_repos_dir():
    """Create temporary golden repos directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def cidx_meta_path(temp_golden_repos_dir):
    """Create cidx-meta directory."""
    meta_path = Path(temp_golden_repos_dir) / "cidx-meta"
    meta_path.mkdir(parents=True)
    return meta_path


@pytest.fixture
def test_repo_path(temp_golden_repos_dir):
    """Create test repository directory."""
    repo_path = Path(temp_golden_repos_dir) / "test-repo"
    repo_path.mkdir(parents=True)
    return repo_path


class TestFindReadme:
    """Test _find_readme helper function."""

    def test_finds_readme_md(self, test_repo_path):
        """Test that _find_readme finds README.md."""
        from code_indexer.global_repos.meta_description_hook import _find_readme

        # Create README.md
        readme = test_repo_path / "README.md"
        readme.write_text("# Test Repo")

        # Execute
        result = _find_readme(test_repo_path)

        # Verify
        assert result == readme
        assert result.name == "README.md"

    def test_finds_readme_rst_when_md_missing(self, test_repo_path):
        """Test that _find_readme finds README.rst when .md missing."""
        from code_indexer.global_repos.meta_description_hook import _find_readme

        # Create README.rst only
        readme = test_repo_path / "README.rst"
        readme.write_text("Test Repo\n=========")

        # Execute
        result = _find_readme(test_repo_path)

        # Verify
        assert result == readme
        assert result.name == "README.rst"

    def test_finds_readme_txt_when_md_rst_missing(self, test_repo_path):
        """Test that _find_readme finds README.txt when .md/.rst missing."""
        from code_indexer.global_repos.meta_description_hook import _find_readme

        # Create README.txt only
        readme = test_repo_path / "README.txt"
        readme.write_text("Test Repo")

        # Execute
        result = _find_readme(test_repo_path)

        # Verify
        assert result == readme
        assert result.name == "README.txt"

    def test_finds_readme_no_extension(self, test_repo_path):
        """Test that _find_readme finds README with no extension."""
        from code_indexer.global_repos.meta_description_hook import _find_readme

        # Create README with no extension
        readme = test_repo_path / "README"
        readme.write_text("Test Repo")

        # Execute
        result = _find_readme(test_repo_path)

        # Verify
        assert result == readme
        assert result.name == "README"

    def test_finds_lowercase_readme(self, test_repo_path):
        """Test that _find_readme finds lowercase readme.md."""
        from code_indexer.global_repos.meta_description_hook import _find_readme

        # Create lowercase readme.md
        readme = test_repo_path / "readme.md"
        readme.write_text("# Test Repo")

        # Execute
        result = _find_readme(test_repo_path)

        # Verify
        assert result == readme
        assert result.name == "readme.md"

    def test_returns_none_when_no_readme(self, test_repo_path):
        """Test that _find_readme returns None when no README exists."""
        from code_indexer.global_repos.meta_description_hook import _find_readme

        # No README files created

        # Execute
        result = _find_readme(test_repo_path)

        # Verify
        assert result is None


class TestCreateReadmeFallback:
    """Test _create_readme_fallback function."""

    def test_creates_correct_filename(self, test_repo_path, cidx_meta_path):
        """Test that _create_readme_fallback creates correct file name."""
        from code_indexer.global_repos.meta_description_hook import (
            _create_readme_fallback,
        )

        # Setup: Create README.md
        readme = test_repo_path / "README.md"
        readme_content = "# Test Repo\nDescription"
        readme.write_text(readme_content)

        # Execute
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = _create_readme_fallback(
                test_repo_path, "test-repo", cidx_meta_path
            )

        # Verify
        expected_path = cidx_meta_path / "test-repo_README.md"
        assert result == expected_path
        assert result.exists()

    def test_preserves_content_exactly(self, test_repo_path, cidx_meta_path):
        """Test that _create_readme_fallback preserves content exactly."""
        from code_indexer.global_repos.meta_description_hook import (
            _create_readme_fallback,
        )

        # Setup: Create README.md with specific content
        readme = test_repo_path / "README.md"
        readme_content = "# Test Repo\n\nMulti-line\ncontent\nwith special chars: @#$%"
        readme.write_text(readme_content)

        # Execute
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = _create_readme_fallback(
                test_repo_path, "test-repo", cidx_meta_path
            )

        # Verify
        assert result.read_text() == readme_content

    def test_handles_unicode(self, test_repo_path, cidx_meta_path):
        """Test that _create_readme_fallback handles unicode content."""
        from code_indexer.global_repos.meta_description_hook import (
            _create_readme_fallback,
        )

        # Setup: Create README.md with unicode
        readme = test_repo_path / "README.md"
        readme_content = "# Test Repo\n\nUnicode: 中文 日本語 한국어 Ελληνικά"
        readme.write_text(readme_content, encoding="utf-8")

        # Execute
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = _create_readme_fallback(
                test_repo_path, "test-repo", cidx_meta_path
            )

        # Verify
        assert result.read_text(encoding="utf-8") == readme_content

    def test_overwrites_existing_fallback(self, test_repo_path, cidx_meta_path):
        """Test that _create_readme_fallback overwrites existing fallback."""
        from code_indexer.global_repos.meta_description_hook import (
            _create_readme_fallback,
        )

        # Setup: Create existing fallback
        fallback_path = cidx_meta_path / "test-repo_README.md"
        fallback_path.write_text("Old content")

        # Setup: Create new README.md
        readme = test_repo_path / "README.md"
        new_content = "New content"
        readme.write_text(new_content)

        # Execute
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = _create_readme_fallback(
                test_repo_path, "test-repo", cidx_meta_path
            )

        # Verify
        assert result.read_text() == new_content

    def test_triggers_reindex(self, test_repo_path, cidx_meta_path):
        """Test that _create_readme_fallback triggers re-index."""
        from code_indexer.global_repos.meta_description_hook import (
            _create_readme_fallback,
        )

        # Setup: Create README.md
        readme = test_repo_path / "README.md"
        readme.write_text("# Test Repo")

        # Execute
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            _create_readme_fallback(test_repo_path, "test-repo", cidx_meta_path)

        # Verify: cidx index was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["cidx", "index"]
        assert call_args[1]["cwd"] == str(cidx_meta_path)

    def test_returns_none_when_no_readme(self, test_repo_path, cidx_meta_path):
        """Test that _create_readme_fallback returns None when no README."""
        from code_indexer.global_repos.meta_description_hook import (
            _create_readme_fallback,
        )

        # No README created

        # Execute
        with patch("subprocess.run") as mock_run:
            result = _create_readme_fallback(
                test_repo_path, "test-repo", cidx_meta_path
            )

        # Verify
        assert result is None
        # No re-index should be triggered
        mock_run.assert_not_called()


class TestReadmeFallbackOnCliUnavailable:
    """Test README fallback when CLI is unavailable."""

    def test_fallback_created_when_cli_unavailable(
        self, test_repo_path, cidx_meta_path, temp_golden_repos_dir
    ):
        """Test fallback created when CLI unavailable."""
        from code_indexer.global_repos.meta_description_hook import on_repo_added

        # Setup: Create README.md
        readme = test_repo_path / "README.md"
        readme.write_text("# Test Repo\nDescription")

        # Mock CLI manager to return unavailable
        mock_cli_manager = MagicMock()
        mock_cli_manager.check_cli_available.return_value = False

        # Execute
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            with patch(
                "code_indexer.global_repos.meta_description_hook.ClaudeCliManager",
                return_value=mock_cli_manager,
            ):
                on_repo_added(
                    repo_name="test-repo",
                    repo_url="https://github.com/test/repo",
                    clone_path=str(test_repo_path),
                    golden_repos_dir=temp_golden_repos_dir,
                )

        # Verify: Fallback file created
        fallback_path = cidx_meta_path / "test-repo_README.md"
        assert fallback_path.exists()
        assert fallback_path.read_text() == "# Test Repo\nDescription"

    def test_no_fallback_when_cli_unavailable_and_no_readme(
        self, test_repo_path, cidx_meta_path, temp_golden_repos_dir
    ):
        """Test no fallback when CLI unavailable and no README exists."""
        from code_indexer.global_repos.meta_description_hook import on_repo_added

        # No README created

        # Mock CLI manager to return unavailable
        mock_cli_manager = MagicMock()
        mock_cli_manager.check_cli_available.return_value = False

        # Execute
        with patch("subprocess.run") as mock_run:
            with patch(
                "code_indexer.global_repos.meta_description_hook.ClaudeCliManager",
                return_value=mock_cli_manager,
            ):
                on_repo_added(
                    repo_name="test-repo",
                    repo_url="https://github.com/test/repo",
                    clone_path=str(test_repo_path),
                    golden_repos_dir=temp_golden_repos_dir,
                )

        # Verify: No fallback file created
        fallback_path = cidx_meta_path / "test-repo_README.md"
        assert not fallback_path.exists()
        # No re-index should be triggered
        mock_run.assert_not_called()

    def test_warning_logged_when_no_readme(
        self, test_repo_path, cidx_meta_path, temp_golden_repos_dir, caplog
    ):
        """Test warning logged when no README exists."""
        from code_indexer.global_repos.meta_description_hook import on_repo_added
        import logging

        # No README created

        # Mock CLI manager to return unavailable
        mock_cli_manager = MagicMock()
        mock_cli_manager.check_cli_available.return_value = False

        # Execute
        with patch(
            "code_indexer.global_repos.meta_description_hook.ClaudeCliManager",
            return_value=mock_cli_manager,
        ):
            with caplog.at_level(logging.WARNING):
                on_repo_added(
                    repo_name="test-repo",
                    repo_url="https://github.com/test/repo",
                    clone_path=str(test_repo_path),
                    golden_repos_dir=temp_golden_repos_dir,
                )

        # Verify: Warning logged
        assert any("README" in record.message for record in caplog.records)


class TestReadmeFallbackOnCliError:
    """Test README fallback when CLI errors."""

    def test_fallback_created_on_cli_error_callback(
        self, test_repo_path, cidx_meta_path, temp_golden_repos_dir
    ):
        """Test fallback created when description generation throws exception."""
        from code_indexer.global_repos.meta_description_hook import on_repo_added

        # Setup: Create README.md
        readme = test_repo_path / "README.md"
        readme.write_text("# Test Repo\nDescription")

        # Mock CLI manager to be available
        mock_cli_manager = MagicMock()
        mock_cli_manager.check_cli_available.return_value = True

        # Mock _generate_repo_description to raise exception
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            with patch(
                "code_indexer.global_repos.meta_description_hook.ClaudeCliManager",
                return_value=mock_cli_manager,
            ):
                with patch(
                    "code_indexer.global_repos.meta_description_hook._generate_repo_description",
                    side_effect=Exception("CLI error: timeout"),
                ):
                    on_repo_added(
                        repo_name="test-repo",
                        repo_url="https://github.com/test/repo",
                        clone_path=str(test_repo_path),
                        golden_repos_dir=temp_golden_repos_dir,
                    )

        # Verify: Fallback file created
        fallback_path = cidx_meta_path / "test-repo_README.md"
        assert fallback_path.exists()
        assert fallback_path.read_text() == "# Test Repo\nDescription"

    def test_cli_error_logged(
        self, test_repo_path, cidx_meta_path, temp_golden_repos_dir, caplog
    ):
        """Test CLI error is logged for debugging."""
        from code_indexer.global_repos.meta_description_hook import on_repo_added
        import logging

        # Setup: Create README.md
        readme = test_repo_path / "README.md"
        readme.write_text("# Test Repo\nDescription")

        # Mock CLI manager
        mock_cli_manager = MagicMock()
        mock_cli_manager.check_cli_available.return_value = True

        # Mock _generate_repo_description to raise exception
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            with patch(
                "code_indexer.global_repos.meta_description_hook.ClaudeCliManager",
                return_value=mock_cli_manager,
            ):
                with patch(
                    "code_indexer.global_repos.meta_description_hook._generate_repo_description",
                    side_effect=Exception("CLI error: timeout"),
                ):
                    with caplog.at_level(logging.INFO):
                        on_repo_added(
                            repo_name="test-repo",
                            repo_url="https://github.com/test/repo",
                            clone_path=str(test_repo_path),
                            golden_repos_dir=temp_golden_repos_dir,
                        )

        # Verify: Error logged
        assert any(
            "Failed to create meta description" in record.message
            for record in caplog.records
        )
        assert any(
            "Falling back to README copy" in record.message for record in caplog.records
        )
