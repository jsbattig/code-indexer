"""E2E test for temporal language and path filters."""
import subprocess
import pytest

from code_indexer.config import ConfigManager
from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.services.temporal.temporal_search_service import TemporalSearchService
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.services.embedding_factory import EmbeddingProviderFactory


class TestTemporalLanguageFilterE2E:
    """End-to-end test that language and path filters work with temporal queries."""

    def test_temporal_language_filter_works(self, tmp_path):
        """Test that language filters work with temporal queries."""
        # Create a test repository
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path)

        # Create files in different languages
        # Python file
        (repo_path / "auth.py").write_text("def authenticate():\n    return True")
        # JavaScript file
        (repo_path / "app.js").write_text("function authenticate() {\n    return true;\n}")
        # Java file
        (repo_path / "Auth.java").write_text("public class Auth {\n    public boolean authenticate() {\n        return true;\n    }\n}")

        # Commit the files
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Add authentication in multiple languages"], cwd=repo_path, check=True)

        # Setup indexing
        config_manager = ConfigManager.create_with_backtrack(repo_path)
        config = config_manager.get_config()

        # Create vector store
        vector_store = FilesystemVectorStore(
            project_root=repo_path,
            collection_name="code-indexer",
            config=config
        )

        # Create temporal indexer
        temporal_indexer = TemporalIndexer(config_manager, vector_store)

        # Index the commits
        result = temporal_indexer.index_commits(
            all_branches=False,
            max_commits=10
        )

        assert result.total_commits > 0, "Should have indexed at least one commit"

        # Create search service
        embedding_service = EmbeddingProviderFactory.create(config=config)
        search_service = TemporalSearchService(
            vector_store=vector_store,
            embedding_service=embedding_service,
            config=config
        )

        # Search for "authenticate" with Python language filter
        results = search_service.search(
            query="authenticate",
            limit=10,
            language="py"
        )

        # Verify only Python results returned
        assert len(results) > 0, "Should find Python authentication code"
        for result in results:
            assert result["file_path"] == "auth.py", f"Expected auth.py but got {result['file_path']}"
            assert result.get("language") == "py", f"Expected language 'py' but got {result.get('language')}"

        # Search for "authenticate" with JavaScript language filter
        results = search_service.search(
            query="authenticate",
            limit=10,
            language="js"
        )

        # Verify only JavaScript results returned
        assert len(results) > 0, "Should find JavaScript authentication code"
        for result in results:
            assert result["file_path"] == "app.js", f"Expected app.js but got {result['file_path']}"
            assert result.get("language") == "js", f"Expected language 'js' but got {result.get('language')}"

        # Search for "authenticate" with Java language filter
        results = search_service.search(
            query="authenticate",
            limit=10,
            language="java"
        )

        # Verify only Java results returned
        assert len(results) > 0, "Should find Java authentication code"
        for result in results:
            assert result["file_path"] == "Auth.java", f"Expected Auth.java but got {result['file_path']}"
            assert result.get("language") == "java", f"Expected language 'java' but got {result.get('language')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])