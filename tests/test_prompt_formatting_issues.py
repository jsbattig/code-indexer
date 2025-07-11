"""
Test for prompt formatting issues identified by user.

These tests reproduce and verify fixes for:
1. Blank lines at the end of prompts
2. .gitignore files being included in project structure when git-aware
"""

from pathlib import Path

from src.code_indexer.services.claude_integration import ClaudeIntegrationService


def test_prompt_should_not_have_excessive_blank_lines():
    """Test that generated prompts don't have excessive blank lines."""

    # Create a test ClaudeIntegrationService
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a simple test project
        (temp_path / "main.py").write_text("print('hello')")

        service = ClaudeIntegrationService(
            codebase_dir=temp_path, project_name="test_project"
        )

        # Mock project info
        project_info = {
            "project_id": "test_project",
            "git_available": True,
            "current_branch": "main",
            "current_commit": "abc123",
        }

        # Generate a prompt
        prompt = service.create_claude_first_prompt(
            user_query="Test question",
            project_info=project_info,
            include_project_structure=True,
        )

        # Check that prompt doesn't have excessive consecutive blank lines
        lines = prompt.split("\n")

        # Count consecutive empty lines
        max_consecutive_empty = 0
        current_consecutive_empty = 0

        for line in lines:
            if line.strip() == "":
                current_consecutive_empty += 1
                max_consecutive_empty = max(
                    max_consecutive_empty, current_consecutive_empty
                )
            else:
                current_consecutive_empty = 0

        # Should have at most 2 consecutive empty lines
        assert (
            max_consecutive_empty <= 2
        ), f"Prompt has {max_consecutive_empty} consecutive empty lines, should have at most 2"

        # Count trailing empty lines
        trailing_empty_count = 0
        for line in reversed(lines):
            if line.strip() == "":
                trailing_empty_count += 1
            else:
                break

        # Should have at most 1 trailing empty line
        assert (
            trailing_empty_count <= 1
        ), f"Prompt has {trailing_empty_count} trailing empty lines, should have at most 1"

        # The last non-empty line should be meaningful content
        last_meaningful_line = None
        for line in reversed(lines):
            if line.strip():
                last_meaningful_line = line.strip()
                break

        assert last_meaningful_line is not None, "Prompt should have meaningful content"
        assert len(last_meaningful_line) > 0, "Last line should not be empty"


def test_gitignore_files_should_not_appear_in_project_structure():
    """Test that .gitignore files are excluded from project structure when git-aware."""

    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a git repository structure
        (temp_path / ".git").mkdir()
        (temp_path / ".git" / "config").write_text("[core]\n")

        # Create files that should be included
        (temp_path / "main.py").write_text("print('hello')")
        (temp_path / "README.md").write_text("# Test Project")

        # Create .gitignore file
        gitignore_content = """
*.pyc
__pycache__/
.env
node_modules/
.DS_Store
*.log
dist/
build/
"""
        (temp_path / ".gitignore").write_text(gitignore_content)

        # Create files that should be ignored according to .gitignore
        (temp_path / "test.pyc").write_text("compiled python")
        (temp_path / ".env").write_text("SECRET=123")
        (temp_path / ".DS_Store").write_text("mac metadata")
        (temp_path / "app.log").write_text("log content")

        # Create directories that should be ignored
        (temp_path / "__pycache__").mkdir()
        (temp_path / "__pycache__" / "test.pyc").write_text("cache")
        (temp_path / "node_modules").mkdir()
        (temp_path / "node_modules" / "package.json").write_text("{}")
        (temp_path / "dist").mkdir()
        (temp_path / "dist" / "output.js").write_text("built code")

        service = ClaudeIntegrationService(
            codebase_dir=temp_path, project_name="test_project"
        )

        # Mock project info as git-aware
        project_info = {
            "project_id": "test_project",
            "git_available": True,
            "current_branch": "main",
            "current_commit": "abc123",
        }

        # Generate prompt with project structure
        prompt = service.create_claude_first_prompt(
            user_query="Test question",
            project_info=project_info,
            include_project_structure=True,
        )

        # Check that .gitignore files/directories are NOT in the project structure
        gitignored_items = [
            "test.pyc",
            ".env",
            ".DS_Store",
            "app.log",
            "__pycache__",
            "node_modules",
            "dist",
        ]

        for item in gitignored_items:
            assert (
                item not in prompt
            ), f"Gitignored item '{item}' should not appear in project structure"

        # Check that legitimate files ARE included
        legitimate_items = ["main.py", "README.md"]

        for item in legitimate_items:
            assert (
                item in prompt
            ), f"Legitimate file '{item}' should appear in project structure"


def test_project_structure_respects_gitignore_patterns():
    """Test that gitignore pattern matching works correctly."""

    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create git repository
        (temp_path / ".git").mkdir()
        (temp_path / ".git" / "config").write_text("[core]\n")

        # Create .gitignore with various patterns (without negation for now)
        gitignore_content = """# Python
*.pyc
__pycache__/
*.pyo
*.pyd

# Logs
*.log
logs/

# Dependencies  
node_modules/
.pnp.*

# Environment
.env
.env.local
.env.production

# Build outputs
dist/
build/
*.tar.gz

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
"""
        (temp_path / ".gitignore").write_text(gitignore_content)

        # Create files/dirs that should be ignored
        ignored_files = [
            "app.pyc",
            "module.pyo",
            "lib.pyd",
            "debug.log",
            "error.log",
            ".env",
            ".env.local",
            ".env.production",
            "package.tar.gz",
            "app.swp",
            ".DS_Store",
            "Thumbs.db",
        ]

        ignored_dirs = [
            "__pycache__",
            "logs",
            "node_modules",
            "dist",
            "build",
            ".vscode",
            ".idea",
        ]

        # Create files that should NOT be ignored
        included_files = ["main.py", "test.py", "README.md", "config.json"]

        # Create all test files
        for f in ignored_files + included_files:
            (temp_path / f).write_text(f"content of {f}")

        for d in ignored_dirs:
            (temp_path / d).mkdir()
            (temp_path / d / "file.txt").write_text("content")

        service = ClaudeIntegrationService(
            codebase_dir=temp_path, project_name="test_project"
        )

        project_info = {
            "project_id": "test_project",
            "git_available": True,
            "current_branch": "main",
            "current_commit": "abc123",
        }

        prompt = service.create_claude_first_prompt(
            user_query="Test question",
            project_info=project_info,
            include_project_structure=True,
        )

        # Verify ignored items are not in prompt
        for item in ignored_files + ignored_dirs:
            assert (
                item not in prompt
            ), f"Gitignored item '{item}' should not appear in project structure"

        # Verify included items ARE in prompt
        for item in included_files:
            assert (
                item in prompt
            ), f"Non-ignored file '{item}' should appear in project structure"


def test_non_git_project_includes_all_files():
    """Test that non-git projects include all files (no .gitignore filtering)."""

    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create files without initializing git
        (temp_path / "main.py").write_text("print('hello')")
        (temp_path / ".env").write_text("SECRET=123")  # Would normally be ignored
        (temp_path / "debug.log").write_text("logs")  # Would normally be ignored

        # Create .gitignore (but shouldn't be used since not a git repo)
        (temp_path / ".gitignore").write_text("*.log\n.env\n")

        service = ClaudeIntegrationService(
            codebase_dir=temp_path, project_name="test_project"
        )

        # Mock as non-git project
        project_info = {
            "project_id": "test_project",
            "git_available": False,  # Not a git repository
        }

        prompt = service.create_claude_first_prompt(
            user_query="Test question",
            project_info=project_info,
            include_project_structure=True,
        )

        # In non-git projects, all files should be included (except .gitignore which is not needed)
        all_files = ["main.py", ".env", "debug.log"]

        for item in all_files:
            assert (
                item in prompt
            ), f"In non-git project, file '{item}' should appear in project structure"
