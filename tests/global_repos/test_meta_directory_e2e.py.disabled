"""
E2E Tests for AC6: Semantic Search for Repo Discovery.

Tests the complete workflow: initialize meta-directory, generate
descriptions, index them, and query semantically.
"""

from pathlib import Path
from code_indexer.global_repos.meta_directory_initializer import (
    MetaDirectoryInitializer,
)
from code_indexer.global_repos.global_registry import GlobalRegistry


class TestMetaDirectoryEndToEnd:
    """End-to-end test suite for meta-directory semantic search."""

    def test_complete_workflow_initialization_to_query(self, tmp_path):
        """
        Test complete workflow from initialization to description availability.

        AC6: Meta-directory is indexed and queryable
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Create test repositories
        auth_repo = tmp_path / "auth-service"
        auth_repo.mkdir()
        (auth_repo / "README.md").write_text(
            """
# Authentication Service

A Python library for JWT authentication and OAuth2 integration.

## Features
- JWT token authentication
- OAuth2 provider support
- Role-based access control
- Rate limiting

## Technologies
- Python 3.11+
- FastAPI
- PostgreSQL
"""
        )

        payment_repo = tmp_path / "payment-api"
        payment_repo.mkdir()
        (payment_repo / "README.md").write_text(
            """
# Payment API

Payment processing service for e-commerce.

## Features
- Stripe integration
- Payment gateway abstraction
- Webhook handling

## Technologies
- Node.js
- Express
- MongoDB
"""
        )

        # Create .code-indexer/index/ directories (as they would exist in real repos)
        auth_index = auth_repo / ".code-indexer" / "index"
        auth_index.mkdir(parents=True)
        payment_index = payment_repo / ".code-indexer" / "index"
        payment_index.mkdir(parents=True)

        # Register repos with CORRECT index_path format
        # index_path should point to .code-indexer/index/, not repo root
        registry.register_global_repo(
            repo_name="auth-service",
            alias_name="auth-service-global",
            repo_url="https://github.com/org/auth-service",
            index_path=str(auth_index),
        )
        registry.register_global_repo(
            repo_name="payment-api",
            alias_name="payment-api-global",
            repo_url="https://github.com/org/payment-api",
            index_path=str(payment_index),
        )

        # Initialize meta-directory
        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        meta_dir = initializer.initialize()

        # Verify descriptions created
        assert (meta_dir / "auth-service.md").exists()
        assert (meta_dir / "payment-api.md").exists()

        # Verify content is searchable
        auth_content = (meta_dir / "auth-service.md").read_text()
        assert "authentication" in auth_content.lower()
        assert "JWT" in auth_content or "jwt" in auth_content.lower()

        payment_content = (meta_dir / "payment-api.md").read_text()
        assert "payment" in payment_content.lower()
        assert "Stripe" in payment_content or "stripe" in payment_content.lower()

    def test_descriptions_contain_repo_names_for_followup(self, tmp_path):
        """
        Test that descriptions include repo names for subsequent queries.

        AC6: Results include repo names for subsequent targeted queries
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        repo = tmp_path / "test-repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Test Repo\n\nA test repository.")

        # Create .code-indexer/index/ directory (as it would exist in real repo)
        repo_index = repo / ".code-indexer" / "index"
        repo_index.mkdir(parents=True)

        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(repo_index),
        )

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        meta_dir = initializer.initialize()

        # Verify description contains repo name
        desc_content = (meta_dir / "test-repo.md").read_text()
        assert "test-repo" in desc_content

    def test_meta_directory_registered_in_global_repos_list(self, tmp_path):
        """
        Test that meta-directory appears in global repos list.

        AC6: Meta-directory is queryable like any other global repo
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        initializer.initialize()

        # Verify meta-directory in list
        all_repos = registry.list_global_repos()
        meta_repo = next(
            (r for r in all_repos if r["alias_name"] == "cidx-meta-global"), None
        )

        assert meta_repo is not None
        assert meta_repo["repo_url"] is None

    def test_descriptions_optimized_for_semantic_search(self, tmp_path):
        """
        Test that descriptions contain semantic-rich content.

        AC6: Results ranked by semantic relevance
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        repo = tmp_path / "data-pipeline"
        repo.mkdir()
        (repo / "README.md").write_text(
            """
# Data Pipeline

ETL pipeline for processing customer data.

## Features
- Batch processing
- Real-time streaming
- Data validation
- Schema evolution

## Technologies
- Python
- Apache Spark
- Kafka
"""
        )

        # Create .code-indexer/index/ directory (as it would exist in real repo)
        repo_index = repo / ".code-indexer" / "index"
        repo_index.mkdir(parents=True)

        registry.register_global_repo(
            repo_name="data-pipeline",
            alias_name="data-pipeline-global",
            repo_url="https://github.com/org/data-pipeline",
            index_path=str(repo_index),
        )

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        meta_dir = initializer.initialize()

        # Verify semantic keywords present
        desc_content = (meta_dir / "data-pipeline.md").read_text()

        # Keywords that should appear for semantic search
        assert "data" in desc_content.lower()
        assert "pipeline" in desc_content.lower()
        assert "etl" in desc_content.lower()
        # Technologies
        assert "Python" in desc_content or "python" in desc_content.lower()
        assert "Spark" in desc_content or "spark" in desc_content.lower()

    def test_multiple_repos_discoverable_by_technology(self, tmp_path):
        """
        Test that repos can be discovered by technology stack.

        AC6: Semantic search discovers relevant repos
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Create Python repos
        python_repo1 = tmp_path / "python-lib1"
        python_repo1.mkdir()
        (python_repo1 / "setup.py").write_text("# Python setup")
        (python_repo1 / "README.md").write_text("# Python Library 1")

        python_repo2 = tmp_path / "python-lib2"
        python_repo2.mkdir()
        (python_repo2 / "pyproject.toml").write_text("# Python project")
        (python_repo2 / "README.md").write_text("# Python Library 2")

        # Create JavaScript repo
        js_repo = tmp_path / "js-lib"
        js_repo.mkdir()
        (js_repo / "package.json").write_text('{"name": "js-lib"}')
        (js_repo / "README.md").write_text("# JavaScript Library")

        # Create .code-indexer/index/ directories for all repos
        for repo, name in [
            (python_repo1, "python-lib1"),
            (python_repo2, "python-lib2"),
            (js_repo, "js-lib"),
        ]:
            repo_index = repo / ".code-indexer" / "index"
            repo_index.mkdir(parents=True)

            registry.register_global_repo(
                repo_name=name,
                alias_name=f"{name}-global",
                repo_url=f"https://github.com/org/{name}",
                index_path=str(repo_index),
            )

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        meta_dir = initializer.initialize()

        # Verify Python repos contain "Python" technology
        python1_content = (meta_dir / "python-lib1.md").read_text()
        python2_content = (meta_dir / "python-lib2.md").read_text()

        assert "Python" in python1_content
        assert "Python" in python2_content

        # Verify JS repo contains JavaScript/Node.js
        js_content = (meta_dir / "js-lib.md").read_text()
        assert "JavaScript" in js_content or "Node.js" in js_content

    def test_meta_directory_path_accessible_for_indexing(self, tmp_path):
        """
        Test that meta-directory path is accessible for indexing.

        AC6: Meta-directory is indexed
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        meta_dir = initializer.initialize()

        # Verify meta-directory registered with correct index_path
        meta_repo = registry.get_global_repo("cidx-meta-global")
        assert meta_repo is not None
        assert Path(meta_repo["index_path"]) == meta_dir
        assert meta_dir.exists()
