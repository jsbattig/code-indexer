"""
Unit tests for DelegationFunctionLoader service.

Story #718: Function Discovery for claude.ai Users

Tests follow TDD methodology - tests written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

import tempfile
import shutil
from pathlib import Path

import pytest


class TestDelegationFunction:
    """Tests for DelegationFunction dataclass."""

    def test_delegation_function_has_required_fields(self):
        """
        DelegationFunction should have all required fields.

        Given I create a DelegationFunction
        When I inspect its fields
        Then it has name, description, allowed_groups, impersonation_user,
             required_repos, parameters, and prompt_template fields
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunction,
        )

        func = DelegationFunction(
            name="test-function",
            description="A test function",
            allowed_groups=["engineering"],
            impersonation_user="ci-user",
            required_repos=[{"alias": "main", "remote": "git@example.com:test.git"}],
            parameters=[{"name": "query", "type": "string", "required": True}],
            prompt_template="You are an assistant.",
        )

        assert func.name == "test-function"
        assert func.description == "A test function"
        assert func.allowed_groups == ["engineering"]
        assert func.impersonation_user == "ci-user"
        assert func.required_repos == [
            {"alias": "main", "remote": "git@example.com:test.git"}
        ]
        assert func.parameters == [
            {"name": "query", "type": "string", "required": True}
        ]
        assert func.prompt_template == "You are an assistant."

    def test_delegation_function_impersonation_user_optional(self):
        """
        DelegationFunction impersonation_user should be optional.

        Given I create a DelegationFunction without impersonation_user
        When I inspect its fields
        Then impersonation_user is None
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunction,
        )

        func = DelegationFunction(
            name="test-function",
            description="A test function",
            allowed_groups=["engineering"],
            impersonation_user=None,
            required_repos=[],
            parameters=[],
            prompt_template="Test template",
        )

        assert func.impersonation_user is None


class TestDelegationFunctionLoader:
    """Tests for DelegationFunctionLoader service."""

    @pytest.fixture
    def temp_repo_dir(self):
        """Create a temporary directory simulating function repository."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def sample_function_file(self, temp_repo_dir):
        """Create a sample function definition file."""
        content = """---
name: semantic-code-search
description: "Search for code semantically across configured repositories"
allowed_groups:
  - engineering
  - support
  - sales
impersonation_user: ci-service-account
required_repos:
  - alias: main-product
    remote: git@github.com:company/product.git
    branch: main
parameters:
  - name: repository
    type: string
    required: true
    description: "Repository alias to search"
  - name: query
    type: string
    required: true
    description: "Natural language search query"
---
# Base Prompt Template

You are a code intelligence assistant searching the codebase.
Use semantic search to find relevant code.
"""
        file_path = temp_repo_dir / "semantic-code-search.md"
        file_path.write_text(content)
        return file_path

    def test_loader_initializes_successfully(self):
        """
        DelegationFunctionLoader should initialize without errors.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        assert loader is not None

    def test_load_functions_from_empty_directory(self, temp_repo_dir):
        """
        load_functions should return empty list for empty directory.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        assert functions == []

    def test_load_functions_parses_valid_function_file(
        self, temp_repo_dir, sample_function_file
    ):
        """
        load_functions should parse valid function definition files.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        assert len(functions) == 1
        func = functions[0]
        assert func.name == "semantic-code-search"
        assert (
            func.description
            == "Search for code semantically across configured repositories"
        )
        assert func.allowed_groups == ["engineering", "support", "sales"]
        assert func.impersonation_user == "ci-service-account"

    def test_load_functions_parses_required_repos(
        self, temp_repo_dir, sample_function_file
    ):
        """
        load_functions should parse required_repos field.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        func = functions[0]
        assert len(func.required_repos) == 1
        repo = func.required_repos[0]
        assert repo["alias"] == "main-product"
        assert repo["remote"] == "git@github.com:company/product.git"
        assert repo["branch"] == "main"

    def test_load_functions_parses_parameters(
        self, temp_repo_dir, sample_function_file
    ):
        """
        load_functions should parse parameters field.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        func = functions[0]
        assert len(func.parameters) == 2
        param1 = func.parameters[0]
        assert param1["name"] == "repository"
        assert param1["type"] == "string"
        assert param1["required"] is True
        assert param1["description"] == "Repository alias to search"

    def test_load_functions_parses_prompt_template(
        self, temp_repo_dir, sample_function_file
    ):
        """
        load_functions should parse prompt_template (markdown body after frontmatter).
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        func = functions[0]
        assert "# Base Prompt Template" in func.prompt_template
        assert "You are a code intelligence assistant" in func.prompt_template

    def test_load_functions_multiple_files(self, temp_repo_dir):
        """
        load_functions should load multiple function files.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        content1 = """---
name: function-one
description: "First function"
allowed_groups:
  - engineering
---
Template one
"""
        (temp_repo_dir / "function-one.md").write_text(content1)

        content2 = """---
name: function-two
description: "Second function"
allowed_groups:
  - sales
---
Template two
"""
        (temp_repo_dir / "function-two.md").write_text(content2)

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        assert len(functions) == 2
        names = {f.name for f in functions}
        assert names == {"function-one", "function-two"}

    def test_load_functions_ignores_non_md_files(self, temp_repo_dir):
        """
        load_functions should ignore non-.md files.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        content = """---
name: valid-function
description: "Valid function"
allowed_groups:
  - engineering
---
Template
"""
        (temp_repo_dir / "valid-function.md").write_text(content)
        (temp_repo_dir / "README.txt").write_text("This is a readme")
        (temp_repo_dir / "config.yaml").write_text("key: value")

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        assert len(functions) == 1
        assert functions[0].name == "valid-function"

    def test_load_functions_skips_invalid_yaml(self, temp_repo_dir):
        """
        load_functions should skip files with invalid YAML frontmatter.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        valid_content = """---
name: valid-function
description: "Valid function"
allowed_groups:
  - engineering
---
Template
"""
        (temp_repo_dir / "valid.md").write_text(valid_content)

        invalid_content = """---
name: invalid-function
description: "Missing closing quote
allowed_groups:
  - engineering
---
Template
"""
        (temp_repo_dir / "invalid.md").write_text(invalid_content)

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        assert len(functions) == 1
        assert functions[0].name == "valid-function"

    def test_load_functions_skips_missing_required_fields(self, temp_repo_dir):
        """
        load_functions should skip files missing required fields (name).
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        valid_content = """---
name: valid-function
description: "Valid function"
allowed_groups:
  - engineering
---
Template
"""
        (temp_repo_dir / "valid.md").write_text(valid_content)

        missing_name = """---
description: "Missing name field"
allowed_groups:
  - engineering
---
Template
"""
        (temp_repo_dir / "missing-name.md").write_text(missing_name)

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        assert len(functions) == 1
        assert functions[0].name == "valid-function"

    def test_load_functions_skips_missing_allowed_groups(self, temp_repo_dir):
        """
        load_functions should skip files missing allowed_groups field.

        Given I have a function file missing allowed_groups
        When I call load_functions
        Then the function is skipped and not included in results

        Story #718 Code Review - HIGH-1
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        # Create valid function
        valid_content = """---
name: valid-function
description: "Valid function"
allowed_groups:
  - engineering
---
Template
"""
        (temp_repo_dir / "valid.md").write_text(valid_content)

        # Create function missing allowed_groups
        missing_groups = """---
name: missing-groups
description: "Missing allowed_groups field"
---
Template
"""
        (temp_repo_dir / "missing-groups.md").write_text(missing_groups)

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        assert len(functions) == 1
        assert functions[0].name == "valid-function"

    def test_load_functions_skips_empty_allowed_groups(self, temp_repo_dir):
        """
        load_functions should skip files with empty allowed_groups.

        Given I have a function file with allowed_groups: []
        When I call load_functions
        Then the function is skipped because it has no authorized groups

        Story #718 Code Review - HIGH-1
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        # Create valid function
        valid_content = """---
name: valid-function
description: "Valid function"
allowed_groups:
  - engineering
---
Template
"""
        (temp_repo_dir / "valid.md").write_text(valid_content)

        # Create function with empty allowed_groups
        empty_groups = """---
name: empty-groups
description: "Empty allowed_groups list"
allowed_groups: []
---
Template
"""
        (temp_repo_dir / "empty-groups.md").write_text(empty_groups)

        loader = DelegationFunctionLoader()
        functions = loader.load_functions(temp_repo_dir)

        assert len(functions) == 1
        assert functions[0].name == "valid-function"

    def test_parse_function_file_raises_for_invalid_file(self, temp_repo_dir):
        """
        parse_function_file should raise ValueError for invalid files.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        invalid_file = temp_repo_dir / "invalid.md"
        invalid_file.write_text("No frontmatter here")

        loader = DelegationFunctionLoader()
        with pytest.raises(ValueError):
            loader.parse_function_file(invalid_file)


class TestDelegationFunctionLoaderGroupFiltering:
    """Tests for group-based filtering in DelegationFunctionLoader."""

    @pytest.fixture
    def sample_functions(self):
        """Create sample functions with different allowed_groups."""
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunction,
        )

        return [
            DelegationFunction(
                name="engineering-only",
                description="For engineers",
                allowed_groups=["engineering"],
                impersonation_user=None,
                required_repos=[],
                parameters=[],
                prompt_template="",
            ),
            DelegationFunction(
                name="sales-support",
                description="For sales and support",
                allowed_groups=["sales", "support"],
                impersonation_user=None,
                required_repos=[],
                parameters=[],
                prompt_template="",
            ),
            DelegationFunction(
                name="all-groups",
                description="For everyone",
                allowed_groups=["engineering", "sales", "support"],
                impersonation_user=None,
                required_repos=[],
                parameters=[],
                prompt_template="",
            ),
        ]

    def test_filter_by_groups_returns_matching_functions(self, sample_functions):
        """
        filter_by_groups should return functions accessible to user's groups.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        user_groups = {"engineering"}

        filtered = loader.filter_by_groups(sample_functions, user_groups)

        assert len(filtered) == 2
        names = {f.name for f in filtered}
        assert names == {"engineering-only", "all-groups"}

    def test_filter_by_groups_multiple_user_groups(self, sample_functions):
        """
        filter_by_groups should work with multiple user groups.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        user_groups = {"sales", "support"}

        filtered = loader.filter_by_groups(sample_functions, user_groups)

        assert len(filtered) == 2
        names = {f.name for f in filtered}
        assert names == {"sales-support", "all-groups"}

    def test_filter_by_groups_empty_user_groups(self, sample_functions):
        """
        filter_by_groups with empty user groups returns no functions.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        user_groups: set = set()

        filtered = loader.filter_by_groups(sample_functions, user_groups)

        assert filtered == []

    def test_filter_by_groups_empty_functions_list(self):
        """
        filter_by_groups with empty functions list returns empty list.
        """
        from src.code_indexer.server.services.delegation_function_loader import (
            DelegationFunctionLoader,
        )

        loader = DelegationFunctionLoader()
        user_groups = {"engineering"}

        filtered = loader.filter_by_groups([], user_groups)

        assert filtered == []
