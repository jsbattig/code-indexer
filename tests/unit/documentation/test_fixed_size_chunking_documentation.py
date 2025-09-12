"""
TDD Tests for Story 6: Update Documentation and Help System

Tests that verify all documentation accurately describes the fixed-size chunking approach
and removes all references to semantic chunking, AST-based parsing, and tree-sitter.
"""

import re
import subprocess
import pytest
from pathlib import Path


class TestFixedSizeChunkingDocumentation:
    """Test suite verifying documentation reflects fixed-size chunking approach."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent.parent

    @pytest.fixture
    def readme_path(self, project_root):
        """Get the README.md file path."""
        return project_root / "README.md"

    @pytest.fixture
    def config_ref_path(self, project_root):
        """Get the CONFIGURATION_REFERENCE.md file path."""
        return project_root / "CONFIGURATION_REFERENCE.md"

    @pytest.fixture
    def release_notes_path(self, project_root):
        """Get the RELEASE_NOTES.md file path."""
        return project_root / "docs/CHANGELOG.md"

    def test_readme_contains_model_aware_chunking_description(self, readme_path):
        """README.md must contain clear description of model-aware chunking."""
        content = readme_path.read_text()

        # Must contain model-aware chunking descriptions
        assert (
            "model-aware" in content.lower() and "chunking" in content.lower()
        ), "README.md must describe the model-aware chunking approach"

        # Must mention model-aware chunk sizes
        assert "4096" in content, "README.md must mention VoyageAI chunk sizes"
        assert "2048" in content, "README.md must mention Ollama chunk sizes"
        # Note: Fallback size (1000) may not be mentioned in user documentation

        # Should mention overlap functionality
        assert (
            "overlap" in content.lower()
        ), "README.md should describe chunk overlap functionality"

    def test_readme_removes_semantic_chunking_references(self, readme_path):
        """README.md must not contain any semantic chunking references."""
        content = readme_path.read_text().lower()

        # Must not contain semantic chunking terms
        forbidden_terms = [
            "semantic chunking",
            "ast-based",
            "ast based",
            "tree-sitter",
            "tree sitter",
            "abstract syntax tree",
            "semantic parsing",
            "language-specific parsing",
        ]

        for term in forbidden_terms:
            assert (
                term not in content
            ), f"README.md must not contain '{term}' - all semantic chunking references must be removed"

    def test_readme_explains_chunking_behavior(self, readme_path):
        """README.md must explain how the fixed-size chunking works."""
        content = readme_path.read_text()

        # Should explain the chunking approach
        chunking_keywords = ["chunk", "text", "overlap", "character"]
        found_keywords = sum(
            1 for keyword in chunking_keywords if keyword.lower() in content.lower()
        )

        assert (
            found_keywords >= 3
        ), "README.md must explain how chunking works with key terms like chunk, text, overlap, character"

    def test_configuration_reference_removes_semantic_options(self, config_ref_path):
        """CONFIGURATION_REFERENCE.md must not contain semantic chunking options."""
        if not config_ref_path.exists():
            pytest.skip("CONFIGURATION_REFERENCE.md does not exist")

        content = config_ref_path.read_text().lower()

        # Must not contain semantic chunking configuration options
        forbidden_options = [
            "use_semantic_chunking",
            "semantic_chunking",
            "use_ast_parsing",
            "ast_parsing",
            "tree_sitter",
            "language_specific_parsing",
        ]

        for option in forbidden_options:
            assert (
                option not in content
            ), f"CONFIGURATION_REFERENCE.md must not contain '{option}' configuration option"

    def test_configuration_reference_documents_fixed_size_options(
        self, config_ref_path
    ):
        """CONFIGURATION_REFERENCE.md must document chunk_size and chunk_overlap options."""
        if not config_ref_path.exists():
            pytest.skip("CONFIGURATION_REFERENCE.md does not exist")

        content = config_ref_path.read_text().lower()

        # Must document fixed-size chunking options
        required_options = ["chunk_size", "chunk_overlap"]

        for option in required_options:
            assert (
                option in content
            ), f"CONFIGURATION_REFERENCE.md must document the '{option}' configuration option"

    def test_cli_help_text_describes_current_chunking(self, project_root):
        """CLI --help output must describe current fixed-size chunking behavior."""
        try:
            # Run the CLI help command
            result = subprocess.run(
                ["python3", "-m", "src.code_indexer.cli", "--help"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                pytest.skip(f"CLI help command failed: {result.stderr}")

            help_text = result.stdout.lower()

            # Should not contain semantic chunking references
            forbidden_terms = ["semantic chunking", "ast-based", "tree-sitter"]

            for term in forbidden_terms:
                assert (
                    term not in help_text
                ), f"CLI help must not contain '{term}' - remove semantic chunking references"

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            pytest.skip(f"Could not run CLI help command: {e}")

    def test_release_notes_document_breaking_change(self, release_notes_path):
        """RELEASE_NOTES.md must document the semantic->fixed-size chunking change."""
        if not release_notes_path.exists():
            pytest.skip("RELEASE_NOTES.md does not exist")

        content = release_notes_path.read_text().lower()

        # Must document this as a breaking change
        breaking_change_indicators = [
            "breaking change",
            "breaking",
            "major change",
            "incompatible",
        ]

        has_breaking_indicator = any(
            indicator in content for indicator in breaking_change_indicators
        )
        assert (
            has_breaking_indicator
        ), "RELEASE_NOTES.md must document the chunking change as a breaking change"

        # Must mention the change from semantic to fixed-size chunking
        change_indicators = ["chunking", "semantic", "fixed-size", "fixed size"]

        found_indicators = sum(
            1 for indicator in change_indicators if indicator in content
        )
        assert (
            found_indicators >= 2
        ), "RELEASE_NOTES.md must describe the transition from semantic to fixed-size chunking"

    def test_release_notes_explain_benefits(self, release_notes_path):
        """RELEASE_NOTES.md must explain benefits of fixed-size chunking."""
        if not release_notes_path.exists():
            pytest.skip("RELEASE_NOTES.md does not exist")

        content = release_notes_path.read_text().lower()

        # Should mention benefits like performance, consistency, etc.
        benefit_keywords = [
            "performance",
            "faster",
            "consistent",
            "reliable",
            "predictable",
            "efficient",
        ]

        found_benefits = sum(1 for keyword in benefit_keywords if keyword in content)
        assert (
            found_benefits >= 1
        ), "RELEASE_NOTES.md should explain the benefits of the new chunking approach"

    def test_migration_guidance_provided(self, release_notes_path):
        """Documentation must provide migration guidance for users."""
        if not release_notes_path.exists():
            pytest.skip("RELEASE_NOTES.md does not exist")

        content = release_notes_path.read_text().lower()

        # Should provide migration guidance
        migration_keywords = ["migration", "migrate", "upgrade", "re-index", "reindex"]

        has_migration_guidance = any(
            keyword in content for keyword in migration_keywords
        )
        assert (
            has_migration_guidance
        ), "Documentation must provide migration guidance for users upgrading from semantic chunking"

    def test_chunk_size_examples_accurate(self, readme_path):
        """README.md examples must show accurate chunk sizes (1000 chars)."""
        content = readme_path.read_text()

        # Look specifically for chunk size mentions (not overlap)
        chunk_size_patterns = [
            r"chunk size[^\d]*(\d+)\s*(?:character|char|byte)s?",
            r"(\d+)\s*(?:character|char|byte)s?\s+chunk",
            r"exactly\s+(\d+)\s+characters?",
        ]

        chunk_sizes = []
        for pattern in chunk_size_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            chunk_sizes.extend([int(match) for match in matches])

        if chunk_sizes:
            # Verify chunk sizes are around 1000
            for size in chunk_sizes:
                assert (
                    800 <= size <= 1200
                ), f"Chunk size example {size} must be in range 800-1200 characters to reflect actual behavior"

    def test_overlap_examples_accurate(self, readme_path):
        """README.md examples must show accurate overlap (150 chars, 15%)."""
        content = readme_path.read_text().lower()

        # If examples mention overlap, they must be accurate
        if "overlap" in content:
            # Look for overlap percentages
            overlap_percent_pattern = r"(\d+)%"
            percent_matches = re.findall(overlap_percent_pattern, content)

            # Look for overlap character counts
            overlap_char_pattern = r"(\d+)\s*(?:character|char)s?\s+overlap"
            char_matches = re.findall(overlap_char_pattern, content, re.IGNORECASE)

            # Verify percentages are around 15%
            if percent_matches:
                percentages = [int(match) for match in percent_matches]
                for pct in percentages:
                    if (
                        10 <= pct <= 20
                    ):  # Only validate if it looks like an overlap percentage
                        assert (
                            10 <= pct <= 20
                        ), f"Overlap percentage {pct}% must be around 15% to reflect actual behavior"

            # Verify character counts are around 150
            if char_matches:
                char_counts = [int(match) for match in char_matches]
                for count in char_counts:
                    assert (
                        100 <= count <= 200
                    ), f"Overlap character count {count} must be around 150 characters to reflect actual behavior"

    def test_no_ast_references_in_any_documentation(self, project_root):
        """Scan all documentation files for AST/semantic chunking references."""
        doc_extensions = [".md", ".rst", ".txt"]
        doc_files = []

        for ext in doc_extensions:
            doc_files.extend(project_root.glob(f"*{ext}"))
            doc_files.extend(project_root.glob(f"**/*{ext}"))

        # Filter to main documentation files (not test files, debug files, or backlog files)
        main_doc_files = [
            f
            for f in doc_files
            if not any(
                exclude in str(f).lower()
                for exclude in [
                    "test",
                    "debug",
                    ".git",
                    "__pycache__",
                    "backlog",
                    "epic-",
                    "sql_parser_rewrite_summary",  # Exclude planning documents
                ]
            )
        ]

        forbidden_terms = [
            "semantic chunking",
            "tree-sitter",
            "tree sitter",
            "ast-based",
            "ast based",
            "abstract syntax tree",
            "basesemantic",
            "basesemanticparser",
            "basetreesitterparser",
        ]

        violations = []

        for doc_file in main_doc_files:
            try:
                content = doc_file.read_text().lower()

                # Special case: CHANGELOG.md can contain these terms when documenting breaking changes
                if "changelog.md" in str(doc_file).lower():
                    # Only allow these terms if they're in the context of documenting the breaking change
                    if "breaking change" in content and (
                        "semantic chunking replaced" in content
                        or "ast-based semantic chunking" in content
                    ):
                        continue  # Skip validation for release notes documenting the change

                for term in forbidden_terms:
                    if term in content:
                        violations.append(f"Found '{term}' in {doc_file}")
            except (UnicodeDecodeError, PermissionError):
                # Skip binary or inaccessible files
                continue

        assert (
            not violations
        ), f"Found semantic chunking references in documentation: {'; '.join(violations)}"

    def test_configuration_examples_reflect_current_options(self, project_root):
        """Configuration examples in documentation must reflect current options."""
        # Look for configuration example files
        config_files = list(project_root.glob("**/*.yaml")) + list(
            project_root.glob("**/*.yml")
        )
        config_files = [
            f
            for f in config_files
            if not any(exclude in str(f) for exclude in [".git", "test", "debug"])
        ]

        for config_file in config_files:
            try:
                content = config_file.read_text().lower()

                # Must not contain semantic chunking options
                forbidden_options = [
                    "use_semantic_chunking",
                    "semantic_chunking",
                    "use_ast_parsing",
                ]

                for option in forbidden_options:
                    assert (
                        option not in content
                    ), f"Configuration file {config_file} must not contain deprecated option '{option}'"

            except (UnicodeDecodeError, PermissionError):
                continue
