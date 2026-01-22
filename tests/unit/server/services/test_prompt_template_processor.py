"""
Unit tests for PromptTemplateProcessor.

Story #719: Execute Delegation Function with Async Job

Tests follow TDD methodology - tests written FIRST before implementation.
"""


class TestPromptTemplateProcessorRender:
    """Tests for PromptTemplateProcessor.render() method."""

    def test_render_prepends_impersonation_instruction(self):
        """
        Render should prepend impersonation instruction with correct username.

        Given a template and impersonation_user
        When I render the template
        Then the result starts with impersonation instruction containing the user
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Search for authentication code."
        parameters = {}
        user_prompt = "Find login functions"
        impersonation_user = "service_account_1"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        # Should start with impersonation instruction
        assert result.startswith("CRITICAL:")
        assert "set_session_impersonation" in result
        assert "service_account_1" in result

    def test_render_substitutes_parameter_placeholders(self):
        """
        Render should substitute {{param_name}} placeholders with values.

        Given a template with {{repo}} placeholder and parameters={'repo': 'main-app'}
        When I render the template
        Then {{repo}} is replaced with 'main-app'
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Search in {{repo}} repository for {{pattern}} pattern."
        parameters = {"repo": "main-app", "pattern": "authentication"}
        user_prompt = ""
        impersonation_user = "user1"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        # Parameters should be substituted
        assert "main-app" in result
        assert "authentication" in result
        assert "{{repo}}" not in result
        assert "{{pattern}}" not in result

    def test_render_substitutes_user_prompt_placeholder(self):
        """
        Render should substitute {{user_prompt}} with user's additional prompt.

        Given a template with {{user_prompt}} placeholder
        When I render with user_prompt="Find security bugs"
        Then {{user_prompt}} is replaced with the prompt
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "You are a code assistant.\n\nUser request: {{user_prompt}}"
        parameters = {}
        user_prompt = "Find security bugs in the auth module"
        impersonation_user = "user1"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        assert "Find security bugs in the auth module" in result
        assert "{{user_prompt}}" not in result

    def test_render_handles_missing_parameter_gracefully(self):
        """
        Render should leave placeholder unchanged when parameter not provided.

        Given a template with {{undefined}} placeholder
        When I render without that parameter
        Then {{undefined}} remains in the output
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Search {{repo}} and {{undefined}} for code."
        parameters = {"repo": "main-app"}
        user_prompt = ""
        impersonation_user = "user1"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        # Provided parameter should be substituted
        assert "main-app" in result
        # Missing parameter should remain as-is
        assert "{{undefined}}" in result

    def test_render_preserves_template_structure(self):
        """
        Render should preserve newlines and formatting in template.

        Given a multi-line template
        When I render the template
        Then the structure is preserved
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = """Step 1: Search code
Step 2: Analyze results
Step 3: {{action}}"""
        parameters = {"action": "Report findings"}
        user_prompt = ""
        impersonation_user = "user1"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        # Structure should be preserved after impersonation instruction
        assert "Step 1: Search code" in result
        assert "Step 2: Analyze results" in result
        assert "Step 3: Report findings" in result

    def test_render_with_empty_template(self):
        """
        Render should handle empty template gracefully.

        Given an empty template
        When I render it
        Then result contains only impersonation instruction
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = ""
        parameters = {}
        user_prompt = ""
        impersonation_user = "user1"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        # Should still have impersonation instruction
        assert "CRITICAL:" in result
        assert "set_session_impersonation" in result
        assert "user1" in result

    def test_render_impersonation_instruction_format(self):
        """
        Render should use correct impersonation instruction format.

        The instruction must tell Claude to call set_session_impersonation
        as FIRST action before any other operations.
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Do something."
        parameters = {}
        user_prompt = ""
        impersonation_user = "delegated_user"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        # Verify critical instruction format
        assert "FIRST action" in result
        assert "set_session_impersonation" in result
        assert '"delegated_user"' in result or "'delegated_user'" in result

    def test_render_special_characters_in_parameters(self):
        """
        Render should handle special characters in parameter values.

        Given parameters with special regex/JSON characters
        When I render the template
        Then special characters are preserved correctly
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Search for {{pattern}}"
        parameters = {"pattern": "test.*[a-z]+\\d{2}"}
        user_prompt = ""
        impersonation_user = "user1"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        # Special characters should be preserved
        assert "test.*[a-z]+\\d{2}" in result

    def test_render_multiple_occurrences_of_same_placeholder(self):
        """
        Render should substitute all occurrences of same placeholder.

        Given a template with {{repo}} appearing multiple times
        When I render with repo='myrepo'
        Then all occurrences are substituted
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Clone {{repo}}, analyze {{repo}}, and report on {{repo}}."
        parameters = {"repo": "myrepo"}
        user_prompt = ""
        impersonation_user = "user1"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user=impersonation_user,
        )

        # Count occurrences of 'myrepo'
        assert result.count("myrepo") == 3
        assert "{{repo}}" not in result


class TestPromptTemplateProcessorImpersonationConstant:
    """Tests for the IMPERSONATION_INSTRUCTION constant."""

    def test_impersonation_instruction_contains_placeholder(self):
        """
        IMPERSONATION_INSTRUCTION should contain {impersonation_user} placeholder.
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        instruction = PromptTemplateProcessor.IMPERSONATION_INSTRUCTION
        assert "{impersonation_user}" in instruction

    def test_impersonation_instruction_mentions_mcp_tool(self):
        """
        IMPERSONATION_INSTRUCTION should reference the MCP tool name.
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        instruction = PromptTemplateProcessor.IMPERSONATION_INSTRUCTION
        assert "set_session_impersonation" in instruction

    def test_impersonation_instruction_emphasizes_first_action(self):
        """
        IMPERSONATION_INSTRUCTION should emphasize it must be FIRST action.
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        instruction = PromptTemplateProcessor.IMPERSONATION_INSTRUCTION
        assert "FIRST" in instruction or "first" in instruction.lower()


class TestPromptTemplateProcessorImpersonationPosition:
    """Tests verifying impersonation instruction positioning."""

    def test_render_impersonation_instruction_is_at_very_beginning(self):
        """
        Impersonation instruction MUST be at the very start of rendered output.

        This is a security requirement - the instruction must be at position 0,
        not just "somewhere" in the output. This ensures Claude sees it first.
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Some template content here"

        result = processor.render(
            template=template,
            parameters={},
            user_prompt="user query",
            impersonation_user="target_user",
        )

        # Verify impersonation instruction is at absolute start (position 0)
        assert result.startswith("CRITICAL:"), (
            f"Impersonation instruction must start at position 0. "
            f"Actual start: {result[:50]!r}"
        )

    def test_render_impersonation_instruction_precedes_template_content(self):
        """
        Template content must come AFTER impersonation instruction.

        Given any template content
        When rendered with impersonation_user
        Then impersonation instruction appears before template content
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "TEMPLATE_MARKER_UNIQUE_12345"

        result = processor.render(
            template=template,
            parameters={},
            user_prompt="",
            impersonation_user="test_user",
        )

        # Find positions
        impersonation_pos = result.find("CRITICAL:")
        template_pos = result.find("TEMPLATE_MARKER_UNIQUE_12345")

        assert impersonation_pos == 0, "Impersonation instruction must be at position 0"
        assert (
            template_pos > impersonation_pos
        ), "Template content must come after impersonation instruction"


class TestPromptTemplateProcessorSpaceVariantPlaceholders:
    """
    Tests for space-variant placeholder substitution.

    Bug Fix: Template processor must handle placeholders with various spacing:
    - {{param}} - no spaces
    - {{ param }} - single spaces
    - {{  param  }} - multiple spaces

    Root cause: Line 59 creates "{{" + param_name + "}}" (no spaces)
    but templates often use "{{ param }}" with spaces.
    """

    def test_substitutes_placeholder_with_no_spaces(self):
        """
        Render should substitute {{param}} placeholders (no spaces).

        Given template "Hello {{message}}"
        When I render with parameters={'message': 'World'}
        Then result contains "Hello World"
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Hello {{message}}"
        parameters = {"message": "World"}

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt="",
            impersonation_user="user1",
        )

        assert "Hello World" in result
        assert "{{message}}" not in result

    def test_substitutes_placeholder_with_single_spaces(self):
        """
        Render should substitute {{ param }} placeholders (single spaces).

        Given template "Hello {{ message }}"
        When I render with parameters={'message': 'World'}
        Then result contains "Hello World"
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Hello {{ message }}"
        parameters = {"message": "World"}

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt="",
            impersonation_user="user1",
        )

        assert "Hello World" in result
        assert "{{ message }}" not in result

    def test_substitutes_placeholder_with_multiple_spaces(self):
        """
        Render should substitute {{  param  }} placeholders (multiple spaces).

        Given template "Hello {{  message  }}"
        When I render with parameters={'message': 'World'}
        Then result contains "Hello World"
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Hello {{  message  }}"
        parameters = {"message": "World"}

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt="",
            impersonation_user="user1",
        )

        assert "Hello World" in result
        assert "{{  message  }}" not in result

    def test_substitutes_mixed_spacing_formats_in_same_template(self):
        """
        Render should handle mixed placeholder formats in same template.

        Given template with {{param1}} and {{ param2 }} and {{  param3  }}
        When I render with all three parameters
        Then all placeholders are substituted
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Values: {{param1}}, {{ param2 }}, {{  param3  }}"
        parameters = {"param1": "one", "param2": "two", "param3": "three"}

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt="",
            impersonation_user="user1",
        )

        assert "one" in result
        assert "two" in result
        assert "three" in result
        assert "{{param1}}" not in result
        assert "{{ param2 }}" not in result
        assert "{{  param3  }}" not in result

    def test_user_prompt_placeholder_with_spaces(self):
        """
        Render should substitute {{ user_prompt }} with spaces.

        Given template with {{ user_prompt }} placeholder
        When I render with user_prompt="Find bugs"
        Then {{ user_prompt }} is replaced with the prompt
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "User request: {{ user_prompt }}"
        parameters = {}
        user_prompt = "Find security bugs"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user="user1",
        )

        assert "Find security bugs" in result
        assert "{{ user_prompt }}" not in result

    def test_user_prompt_placeholder_with_multiple_spaces(self):
        """
        Render should substitute {{  user_prompt  }} with multiple spaces.

        Given template with {{  user_prompt  }} placeholder
        When I render with user_prompt="Find bugs"
        Then {{  user_prompt  }} is replaced with the prompt
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "User request: {{  user_prompt  }}"
        parameters = {}
        user_prompt = "Find security bugs"

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt=user_prompt,
            impersonation_user="user1",
        )

        assert "Find security bugs" in result
        assert "{{  user_prompt  }}" not in result

    def test_impersonation_still_prepended_with_spaced_placeholders(self):
        """
        Impersonation instruction should still be prepended when using spaced placeholders.

        Given template with {{ param }} (with spaces)
        When I render the template
        Then result still starts with impersonation instruction
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Search {{ repo }} for code"
        parameters = {"repo": "myrepo"}

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt="",
            impersonation_user="service_user",
        )

        assert result.startswith("CRITICAL:")
        assert "set_session_impersonation" in result
        assert "service_user" in result
        assert "myrepo" in result

    def test_multiple_parameters_with_different_spacing(self):
        """
        Render should handle multiple different parameters with various spacing.

        Given template with {{a}}, {{ b }}, {{  c  }}, and {{ user_prompt }}
        When I render with all parameters
        Then all are correctly substituted
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Params: {{a}}, {{ b }}, {{  c  }}. Query: {{ user_prompt }}"
        parameters = {"a": "alpha", "b": "beta", "c": "gamma"}

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt="my query",
            impersonation_user="user1",
        )

        assert "alpha" in result
        assert "beta" in result
        assert "gamma" in result
        assert "my query" in result
        assert "{{a}}" not in result
        assert "{{ b }}" not in result
        assert "{{  c  }}" not in result
        assert "{{ user_prompt }}" not in result

    def test_unknown_placeholder_with_spaces_left_unchanged(self):
        """
        Unknown placeholders should be left unchanged even with spaces.

        Given template with {{ unknown }} (not in parameters)
        When I render without that parameter
        Then {{ unknown }} remains in the output as-is
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Known: {{known}}, Unknown: {{ unknown }}"
        parameters = {"known": "value"}

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt="",
            impersonation_user="user1",
        )

        # Known parameter should be substituted
        assert "value" in result
        assert "{{known}}" not in result
        # Unknown placeholder should remain unchanged
        assert "{{ unknown }}" in result

    def test_multiple_occurrences_with_different_spacing(self):
        """
        Same parameter appearing with different spacing should all be substituted.

        Given template with {{name}}, {{ name }}, {{  name  }} all referring to 'name'
        When I render with name='Bob'
        Then all occurrences are replaced with 'Bob'
        """
        from code_indexer.server.services.prompt_template_processor import (
            PromptTemplateProcessor,
        )

        processor = PromptTemplateProcessor()
        template = "Hello {{name}}! Welcome {{ name }}. Hi {{  name  }}."
        parameters = {"name": "Bob"}

        result = processor.render(
            template=template,
            parameters=parameters,
            user_prompt="",
            impersonation_user="user1",
        )

        # All three should be replaced
        assert result.count("Bob") == 3
        assert "{{name}}" not in result
        assert "{{ name }}" not in result
        assert "{{  name  }}" not in result
