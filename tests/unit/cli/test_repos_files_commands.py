"""Unit tests for repos files and repos cat CLI commands."""


class TestReposFilesCommand:
    """Test repos files CLI command."""

    def test_command_exists(self):
        """repos files command exists."""
        from code_indexer.cli import repos_files

        assert repos_files is not None
        assert repos_files.name == "files"

    def test_command_has_correct_parameters(self):
        """repos files command has expected parameters."""
        from code_indexer.cli import repos_files

        params = {p.name for p in repos_files.params}
        assert "user_alias" in params
        assert "path" in params


class TestReposCatCommand:
    """Test repos cat CLI command."""

    def test_command_exists(self):
        """repos cat command exists."""
        from code_indexer.cli import repos_cat

        assert repos_cat is not None
        assert repos_cat.name == "cat"

    def test_command_has_correct_parameters(self):
        """repos cat command has expected parameters."""
        from code_indexer.cli import repos_cat

        params = {p.name for p in repos_cat.params}
        assert "user_alias" in params
        assert "file_path" in params
        assert "no_highlight" in params
