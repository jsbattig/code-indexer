"""
Test suite to verify complete removal of tree-sitter and semantic chunking infrastructure.

These tests are designed to FAIL initially and pass only after the dependencies
are properly removed as part of Story 1.
"""

import importlib.util
from pathlib import Path

import pytest


class TestTreeSitterDependencyRemoval:
    """Test that all tree-sitter dependencies are completely removed."""

    def test_requirements_txt_no_tree_sitter(self):
        """Test that requirements.txt does not contain tree-sitter-language-pack."""
        requirements_path = (
            Path(__file__).parent.parent.parent.parent / "requirements.txt"
        )

        with open(requirements_path, "r") as f:
            content = f.read()

        # This should fail initially
        assert (
            "tree-sitter-language-pack" not in content
        ), "tree-sitter-language-pack dependency should be removed from requirements.txt"

    def test_no_tree_sitter_imports_in_codebase(self):
        """Test that no files in src/ directory contain tree-sitter imports."""
        src_path = Path(__file__).parent.parent.parent.parent / "src"
        python_files = list(src_path.rglob("*.py"))

        forbidden_imports = [
            "tree_sitter_language_pack",
            "import tree_sitter_language_pack",
            "from tree_sitter_language_pack",
        ]

        violations = []

        for py_file in python_files:
            if py_file.exists():
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()

                for forbidden_import in forbidden_imports:
                    if forbidden_import in content:
                        violations.append(f"{py_file}: contains '{forbidden_import}'")

        # This should fail initially
        assert len(violations) == 0, f"Found tree-sitter imports: {violations}"


class TestSemanticChunkingInfrastructureRemoval:
    """Test that all semantic chunking infrastructure is removed."""

    def test_semantic_chunker_file_deleted(self):
        """Test that semantic_chunker.py file is deleted."""
        semantic_chunker_path = (
            Path(__file__).parent.parent.parent.parent
            / "src/code_indexer/indexing/semantic_chunker.py"
        )

        # This should fail initially
        assert (
            not semantic_chunker_path.exists()
        ), "semantic_chunker.py file should be deleted"

    def test_base_tree_sitter_parser_deleted(self):
        """Test that base_tree_sitter_parser.py file is deleted."""
        base_parser_path = (
            Path(__file__).parent.parent.parent.parent
            / "src/code_indexer/indexing/base_tree_sitter_parser.py"
        )

        # This should fail initially
        assert (
            not base_parser_path.exists()
        ), "base_tree_sitter_parser.py file should be deleted"

    def test_language_parser_files_deleted(self):
        """Test that all 21 language-specific parser files are deleted."""
        indexing_path = (
            Path(__file__).parent.parent.parent.parent / "src/code_indexer/indexing"
        )

        language_parsers = [
            "python_parser.py",
            "java_parser.py",
            "javascript_parser.py",
            "typescript_parser.py",
            "go_parser.py",
            "kotlin_parser.py",
            "csharp_parser.py",
            "cpp_parser.py",
            "c_parser.py",
            "ruby_parser.py",
            "rust_parser.py",
            "swift_parser.py",
            "lua_parser.py",
            "groovy_parser.py",
            "sql_parser.py",
            "html_parser.py",
            "css_parser.py",
            "xml_parser.py",
            "yaml_parser.py",
            "pascal_parser.py",
        ]

        existing_parsers = []
        for parser_file in language_parsers:
            parser_path = indexing_path / parser_file
            if parser_path.exists():
                existing_parsers.append(str(parser_path))

        # This should fail initially
        assert (
            len(existing_parsers) == 0
        ), f"These language parser files should be deleted: {existing_parsers}"

    def test_no_semantic_chunking_imports(self):
        """Test that no files import semantic chunking classes."""
        src_path = Path(__file__).parent.parent.parent.parent / "src"
        python_files = list(src_path.rglob("*.py"))

        forbidden_imports = [
            "SemanticChunker",
            "BaseSemanticParser",
            "BaseTreeSitterParser",
            "SemanticChunk",
            "from .semantic_chunker",
            "from .base_tree_sitter_parser",
        ]

        violations = []

        for py_file in python_files:
            if py_file.exists():
                try:
                    with open(py_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    for forbidden_import in forbidden_imports:
                        if forbidden_import in content:
                            violations.append(
                                f"{py_file}: contains '{forbidden_import}'"
                            )
                except Exception:
                    # Skip files that can't be read
                    continue

        # This should fail initially
        assert len(violations) == 0, f"Found semantic chunking imports: {violations}"


class TestConfigurationChanges:
    """Test that configuration changes are properly implemented."""

    def test_use_semantic_chunking_removed_from_config(self):
        """Test that use_semantic_chunking option is removed from config.py."""
        config_path = (
            Path(__file__).parent.parent.parent.parent / "src/code_indexer/config.py"
        )

        if config_path.exists():
            with open(config_path, "r") as f:
                content = f.read()

            # This should fail initially
            assert (
                "use_semantic_chunking" not in content
            ), "use_semantic_chunking should be removed from config.py"

    def test_processor_no_semantic_chunker_logic(self):
        """Test that processor.py no longer contains semantic chunker logic."""
        processor_path = (
            Path(__file__).parent.parent.parent.parent
            / "src/code_indexer/indexing/processor.py"
        )

        if processor_path.exists():
            with open(processor_path, "r") as f:
                content = f.read()

            forbidden_patterns = [
                "SemanticChunker",
                "from .semantic_chunker",
                "use_semantic_chunking",
            ]

            violations = []
            for pattern in forbidden_patterns:
                if pattern in content:
                    violations.append(f"processor.py contains: {pattern}")

            # This should fail initially
            assert len(violations) == 0, f"Found semantic chunking logic: {violations}"


class TestApplicationBuilds:
    """Test that the application builds without tree-sitter dependencies."""

    def test_application_imports_without_errors(self):
        """Test that main application modules can be imported without tree-sitter."""
        # Test core application modules
        core_modules = [
            "code_indexer.config",
            "code_indexer.cli",
        ]

        import_errors = []

        for module_name in core_modules:
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                if "tree_sitter" in str(e) or "semantic" in str(e).lower():
                    import_errors.append(f"{module_name}: {str(e)}")

        # This should fail initially if tree-sitter dependencies remain
        assert (
            len(import_errors) == 0
        ), f"Found import errors related to tree-sitter/semantic: {import_errors}"

    def test_indexing_processor_imports_cleanly(self):
        """Test that processor module can be imported without semantic dependencies."""
        try:
            # Test import using importlib to avoid linting warnings
            import importlib

            importlib.import_module("code_indexer.indexing.processor")
            # Import successful - test passes
        except ImportError as e:
            # This should fail initially
            if "semantic" in str(e).lower() or "tree_sitter" in str(e):
                pytest.fail(
                    f"Processor import failed due to semantic/tree-sitter: {str(e)}"
                )
            # Other import errors might be acceptable during refactor
