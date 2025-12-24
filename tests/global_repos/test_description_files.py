"""
Tests for AC2: Repository Description Files.

Tests that each registered repo has a corresponding .md file with
proper structure (YAML frontmatter + markdown body).
"""

import yaml
from code_indexer.global_repos.description_generator import DescriptionGenerator


class TestDescriptionFiles:
    """Test suite for repository description file creation."""

    def test_create_description_file_for_repo(self, tmp_path):
        """
        Test that a description file is created for a repository.

        AC2: One .md file per registered repo
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        repo_info = {
            "name": "test-repo",
            "url": "https://github.com/org/test-repo",
            "path": str(tmp_path / "test-repo"),
        }

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name=repo_info["name"],
            repo_url=repo_info["url"],
            description="A test repository",
            technologies=["Python", "pytest"],
            purpose="testing",
            features=["feature1", "feature2"],
            use_cases=["test case 1"],
        )

        # Verify file created
        assert desc_file.exists()
        assert desc_file.suffix == ".md"

    def test_description_filename_matches_repo_name(self, tmp_path):
        """
        Test that description filename is {repo-name}.md.

        AC2: Filename: {repo-name}.md
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name="my-awesome-repo",
            repo_url="https://github.com/org/my-awesome-repo",
            description="Awesome repo",
            technologies=["Python"],
            purpose="awesome",
            features=[],
            use_cases=[],
        )

        assert desc_file.name == "my-awesome-repo.md"

    def test_description_file_has_yaml_frontmatter(self, tmp_path):
        """
        Test that description file contains YAML frontmatter.

        AC2: File structure: YAML frontmatter + markdown body
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            description="Test repo",
            technologies=["Python", "FastAPI"],
            purpose="backend-api",
            features=["auth", "api"],
            use_cases=["user login"],
        )

        content = desc_file.read_text()

        # Check for YAML frontmatter markers
        assert content.startswith("---\n")
        assert "\n---\n" in content

        # Extract and parse frontmatter
        parts = content.split("---\n", 2)
        assert len(parts) >= 3

        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter is not None

    def test_description_frontmatter_contains_required_fields(self, tmp_path):
        """
        Test that frontmatter contains: name, url, technologies, purpose.

        AC2: Content includes: name, url, description, technologies, purpose
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            description="A test repository",
            technologies=["Python", "pytest"],
            purpose="testing",
            features=["testing"],
            use_cases=["unit tests"],
        )

        content = desc_file.read_text()
        parts = content.split("---\n", 2)
        frontmatter = yaml.safe_load(parts[1])

        # Verify required fields
        assert frontmatter["name"] == "test-repo"
        assert frontmatter["url"] == "https://github.com/org/test-repo"
        assert frontmatter["technologies"] == ["Python", "pytest"]
        assert frontmatter["purpose"] == "testing"
        assert "last_analyzed" in frontmatter

    def test_description_has_markdown_body(self, tmp_path):
        """
        Test that description file has markdown body after frontmatter.

        AC2: File structure: YAML frontmatter + markdown body
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            description="A comprehensive test repository",
            technologies=["Python"],
            purpose="testing",
            features=["feature1", "feature2"],
            use_cases=["use case 1"],
        )

        content = desc_file.read_text()
        parts = content.split("---\n", 2)

        # Markdown body is after second ---
        body = parts[2]

        assert len(body) > 0
        assert "# test-repo" in body
        assert "A comprehensive test repository" in body

    def test_description_body_contains_features_section(self, tmp_path):
        """
        Test that markdown body includes Key Features section.

        AC2: Content includes features
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            description="Test repo",
            technologies=["Python"],
            purpose="testing",
            features=["JWT authentication", "Rate limiting"],
            use_cases=["user login"],
        )

        content = desc_file.read_text()

        assert "## Key Features" in content
        assert "JWT authentication" in content
        assert "Rate limiting" in content

    def test_description_body_contains_technologies_section(self, tmp_path):
        """
        Test that markdown body includes Technologies section.

        AC2: Content includes technologies
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            description="Test repo",
            technologies=["Python 3.11+", "FastAPI"],
            purpose="api",
            features=["auth"],
            use_cases=["api requests"],
        )

        content = desc_file.read_text()

        assert "## Technologies" in content
        assert "Python 3.11+" in content
        assert "FastAPI" in content

    def test_description_body_contains_use_cases_section(self, tmp_path):
        """
        Test that markdown body includes Primary Use Cases section.

        AC2: Content includes use cases
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            description="Test repo",
            technologies=["Python"],
            purpose="testing",
            features=["testing"],
            use_cases=["Unit testing", "Integration testing"],
        )

        content = desc_file.read_text()

        assert "## Primary Use Cases" in content
        assert "Unit testing" in content
        assert "Integration testing" in content

    def test_files_stored_in_meta_directory_root(self, tmp_path):
        """
        Test that description files are stored in meta-directory root.

        AC2: Files stored in meta-directory root
        """
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir(parents=True)

        generator = DescriptionGenerator(str(meta_dir))
        desc_file = generator.create_description(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            description="Test",
            technologies=[],
            purpose="test",
            features=[],
            use_cases=[],
        )

        # Verify file is directly in meta_dir
        assert desc_file.parent == meta_dir
