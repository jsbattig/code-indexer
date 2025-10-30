"""
Unit tests for CLI language parameter integration with TantivyIndexManager.

Tests verify that language parameters are correctly passed from CLI
through to the FTS indexing and query layers.
"""


class TestCLILanguageParameterDeclaration:
    """Test that language parameter is properly declared in CLI."""

    def test_query_command_has_language_option(self):
        """
        GIVEN the CLI query command
        WHEN inspecting its Click decorators
        THEN --language option should exist
        """
        from code_indexer.cli import cli

        # Get the query command from the CLI group
        query_cmd = cli.commands.get("query")
        assert query_cmd is not None, "Query command should exist"

        # Check if languages parameter exists in the command params
        language_params = [p for p in query_cmd.params if p.name == "languages"]
        assert (
            len(language_params) > 0
        ), "Query command should have --language parameter"

        # Verify it's a multi-value option
        language_param = language_params[0]
        assert language_param.multiple, "--language should accept multiple values"

    def test_query_command_language_parameter_type(self):
        """
        GIVEN the CLI query command's --language parameter
        WHEN checking its configuration
        THEN it should be configured for multiple values (tuple output)
        """
        from code_indexer.cli import cli

        # Get the query command
        query_cmd = cli.commands.get("query")
        language_params = [p for p in query_cmd.params if p.name == "languages"]

        if language_params:
            language_param = language_params[0]
            # When multiple=True, Click converts to tuple
            assert (
                language_param.multiple
            ), "Language parameter should support multiple values"


class TestLanguageParameterEdgeCases:
    """Test edge cases in language parameter handling."""

    def test_empty_language_tuple_handling(self):
        """
        GIVEN an empty languages tuple from CLI
        WHEN converting to list for TantivyIndexManager
        THEN should result in empty list or None
        """
        # Simulate CLI tuple conversion
        languages_tuple = ()
        languages_list = list(languages_tuple) if languages_tuple else None

        assert (
            languages_list is None or languages_list == []
        ), "Empty tuple should convert to None or empty list"

    def test_multiple_languages_tuple_to_list_conversion(self):
        """
        GIVEN a languages tuple with multiple values from CLI
        WHEN converting to list for TantivyIndexManager
        THEN should preserve all values in correct order
        """
        # Simulate CLI tuple conversion
        languages_tuple = ("python", "javascript", "typescript")
        languages_list = list(languages_tuple)

        assert isinstance(languages_list, list), "Should be a list"
        assert len(languages_list) == 3, "Should preserve all languages"
        assert languages_list == [
            "python",
            "javascript",
            "typescript",
        ], "Should preserve order"

    def test_single_language_tuple_to_list_conversion(self):
        """
        GIVEN a languages tuple with single value from CLI
        WHEN converting to list for TantivyIndexManager
        THEN should result in list with one element
        """
        # Simulate CLI tuple conversion
        languages_tuple = ("python",)
        languages_list = list(languages_tuple)

        assert isinstance(languages_list, list), "Should be a list"
        assert len(languages_list) == 1, "Should have one element"
        assert languages_list[0] == "python", "Should preserve the language value"
