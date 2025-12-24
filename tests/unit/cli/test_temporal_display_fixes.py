"""
Unit tests for temporal query display fixes.

Tests for:
1. Author email included in payload
2. Line numbers suppressed for modified diffs
3. Line numbers still shown for added files
"""

from unittest.mock import MagicMock, patch

from code_indexer.search.query import SearchResult


class TestAuthorEmailInPayload:
    """Test that author_email is included in temporal indexing payload."""

    def test_temporal_payload_includes_author_email(self, tmp_path):
        """Test that indexed payload includes author_email field."""
        from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
        from code_indexer.config import ConfigManager
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Create test repo
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo with commit
        import subprocess

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test Author"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create and commit a file
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")
        subprocess.run(
            ["git", "add", "test.py"], cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add test file"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create config
        config_manager = ConfigManager.create_with_backtrack(repo_path)

        # Create vector store
        index_path = repo_path / ".code-indexer" / "index"
        vector_store = FilesystemVectorStore(
            base_path=index_path, project_root=repo_path
        )

        # Mock vector store's upsert_points to capture payloads
        captured_payloads = []
        original_upsert_points = vector_store.upsert_points

        def capture_upsert_points(collection_name, points):
            for point in points:
                # Points are dicts with 'payload' key
                captured_payloads.append(point["payload"])
            return original_upsert_points(collection_name, points)

        # Create indexer
        with patch(
            "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as mock_factory:
            mock_factory.get_provider_model_info.return_value = {"dimensions": 1536}
            mock_provider = MagicMock()
            mock_provider.get_embeddings_batch.return_value = [[0.1] * 1536]
            mock_factory.create.return_value = mock_provider

            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Patch upsert_points after indexer initialization
            vector_store.upsert_points = capture_upsert_points

            # Index commits (indexer already knows the repo from config_manager)
            indexer.index_commits(all_branches=False, max_commits=10)

        # Verify author_email in payload
        assert len(captured_payloads) > 0, "No payloads captured"

        # Filter for commit_diff payloads (file chunks in temporal indexing)
        commit_diff_payloads = [
            p for p in captured_payloads if p.get("type") == "commit_diff"
        ]
        assert (
            len(commit_diff_payloads) > 0
        ), f"No commit_diff payloads found. Found types: {[p.get('type') for p in captured_payloads]}"

        for payload in commit_diff_payloads:
            assert "author_email" in payload, "author_email missing from payload"
            assert (
                payload["author_email"] == "test@example.com"
            ), f"Expected test@example.com, got {payload.get('author_email')}"
            assert (
                payload["author_name"] == "Test Author"
            ), f"Expected Test Author, got {payload.get('author_name')}"


class TestModifiedDiffLineNumbers:
    """Test that modified diffs don't show line numbers."""

    def test_modified_diff_display_no_line_numbers(self):
        """Test that modified diffs are displayed without line numbers."""
        from code_indexer.cli import _display_file_chunk_match

        # Create mock result with modified diff
        result = MagicMock(spec=SearchResult)
        result.metadata = {
            "path": "test.py",
            "line_start": 0,
            "line_end": 0,
            "commit_hash": "abc123def456",
            "diff_type": "modified",
            "author_email": "test@example.com",
        }
        result.temporal_context = {
            "commit_date": "2025-11-02",
            "author_name": "Test Author",
            "commit_message": "Fix bug",
        }
        result.score = 0.85
        result.content = "def hello():\n-    print('old')\n+    print('new')"

        # Mock console output
        mock_temporal_service = MagicMock()

        with patch("code_indexer.cli.console") as mock_console:
            _display_file_chunk_match(result, 1, mock_temporal_service)

            # Get all print calls
            print_calls = [str(call) for call in mock_console.print.call_args_list]

            # Check that content lines have line numbers (current buggy behavior)
            # Modified diffs currently show: "   0  def hello():", "   1  -    print('old')", etc
            # They SHOULD show: "  def hello():", "  -    print('old')", etc (no line numbers)
            content_started = False
            found_line_number = False
            for call in print_calls:
                call_str = str(call)

                # Skip until we get past the header
                if "Message:" in call_str:
                    content_started = True
                    continue

                if content_started and call_str.strip():
                    # Look for line number pattern: digits followed by spaces
                    import re

                    if re.search(r"\d{1,4}\s{2}", call_str):
                        found_line_number = True
                        break

            # Test expects NO line numbers for modified diffs
            assert (
                not found_line_number
            ), "Modified diff should not show line numbers, but found them in output"

    def test_added_file_display_shows_line_numbers(self):
        """Test that added files still show line numbers."""
        from code_indexer.cli import _display_file_chunk_match

        # Create mock result with added file
        result = MagicMock(spec=SearchResult)
        result.metadata = {
            "path": "new_file.py",
            "line_start": 1,
            "line_end": 10,
            "commit_hash": "abc123def456",
            "diff_type": "added",
            "author_email": "test@example.com",
        }
        result.temporal_context = {
            "commit_date": "2025-11-02",
            "author_name": "Test Author",
            "commit_message": "Add new file",
        }
        result.score = 0.92
        result.content = "def new_function():\n    return True"

        mock_temporal_service = MagicMock()

        with patch("code_indexer.cli.console") as mock_console:
            _display_file_chunk_match(result, 1, mock_temporal_service)

            # Get all print calls
            print_calls = [str(call) for call in mock_console.print.call_args_list]

            # For added files, we should see line numbers
            found_line_numbers = False
            for call in print_calls:
                call_str = str(call)
                # Look for line number format: "   1  " or "  10  "
                import re

                if re.search(r"\d{1,4}\s{2}", call_str):
                    found_line_numbers = True
                    break

            assert (
                found_line_numbers
            ), "Added files should show line numbers, but none found"
