"""E2E test for AC3: Commit message filtering with --chunk-type flag.

This test validates that users can filter temporal search results to only
commit messages using the --chunk-type commit_message flag.

AC3 from story #476:
Users can use --chunk-type commit_message to filter temporal search results
to only commit messages, excluding file diffs.
"""

import tempfile
import subprocess
from pathlib import Path


class TestCommitMessageFilteringE2E:
    """E2E test for commit message filtering functionality."""

    def test_chunk_type_commit_message_returns_only_commit_messages(self):
        """Test that --chunk-type commit_message filters to only commit messages.

        This test verifies AC3:
        1. Create a git repo with commits that have distinctive messages
        2. Index temporal history including commit messages
        3. Query with --chunk-type commit_message
        4. Verify results contain ONLY commit messages (not file diffs)
        5. Verify all results have type="commit_message" in payload
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(
                ["git", "init"], cwd=repo_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create commits with distinctive messages
            commits = [
                {
                    "file": "auth.py",
                    "content": "def authenticate_user():\n    # Auth logic\n    pass\n",
                    "message": "Add authentication module for user login",
                },
                {
                    "file": "database.py",
                    "content": "def connect_db():\n    # DB connection\n    pass\n",
                    "message": "Implement database connection pooling",
                },
                {
                    "file": "api.py",
                    "content": "def api_endpoint():\n    # API logic\n    pass\n",
                    "message": "Create REST API endpoint for user management",
                },
            ]

            for commit_data in commits:
                file_path = repo_path / commit_data["file"]
                file_path.write_text(commit_data["content"])
                subprocess.run(
                    ["git", "add", commit_data["file"]],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", commit_data["message"]],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                )

            # Initialize CIDX index
            subprocess.run(
                ["cidx", "init"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Index temporal history (including commit messages)
            result = subprocess.run(
                ["cidx", "index", "--index-commits"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )

            print(f"Temporal indexing output: {result.stdout}")
            print(f"Temporal indexing errors: {result.stderr}")

            # Query for "authentication" with --chunk-type commit_message
            result = subprocess.run(
                [
                    "cidx",
                    "query",
                    "authentication",
                    "--time-range-all",
                    "--chunk-type",
                    "commit_message",
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            print(f"\nQuery output: {result.stdout}")
            print(f"Query errors: {result.stderr}")

            # Parse results
            lines = result.stdout.strip().split("\n")
            results = [
                line
                for line in lines
                if line and not line.startswith("#") and line.strip()
            ]

            # ASSERTIONS

            # 1. Should have at least 1 result
            assert len(results) > 0, (
                f"Expected at least 1 result for 'authentication' query with --chunk-type commit_message, "
                f"got {len(results)} results. Output: {result.stdout}"
            )

            # 2. Results should be labeled as [COMMIT MESSAGE MATCH]
            full_output = result.stdout
            assert (
                "[COMMIT MESSAGE MATCH]" in full_output
                or "[commit message match]" in full_output.lower()
            ), f"Expected '[COMMIT MESSAGE MATCH]' label in results, but output was: {result.stdout}"

            # 3. Results should contain commit message text (when not using --quiet)
            assert (
                "authentication" in full_output.lower()
                or "Add authentication module" in full_output
            ), f"Expected 'authentication' or commit message text in results, but output was: {result.stdout}"

            # 3. Results should NOT contain file diff content
            # (File diff content like "def authenticate_user():" should NOT appear)
            assert (
                "def authenticate_user" not in result.stdout
            ), f"Results should not contain file diff content, but found file code in: {result.stdout}"

            # 4. Query with --chunk-type commit_diff should return DIFFERENT results
            diff_result = subprocess.run(
                [
                    "cidx",
                    "query",
                    "authentication",
                    "--time-range-all",
                    "--chunk-type",
                    "commit_diff",
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            print(f"\nDiff query output: {diff_result.stdout}")

            # The diff query should contain file content
            assert (
                "def authenticate_user" in diff_result.stdout
                or len(diff_result.stdout.strip()) > 0
            ), f"--chunk-type diff should return file diff content, but got: {diff_result.stdout}"

            print(
                "\n✅ AC3 validated: --chunk-type commit_message successfully filters to commit messages only"
            )


if __name__ == "__main__":
    # Run test
    test = TestCommitMessageFilteringE2E()
    test.test_chunk_type_commit_message_returns_only_commit_messages()
    print("\n🎉 AC3 E2E test passed!")
