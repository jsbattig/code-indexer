"""End-to-end tests for query result aggregation in proxy mode.

This test suite validates the complete query aggregation pipeline (Stories 3.1-3.4):
- Parsing query results from each repository
- Merging and sorting results by score
- Applying global limit to final results
- Preserving repository context in output
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import subprocess

from code_indexer.proxy.query_aggregator import QueryResultAggregator


class TestQueryAggregation(unittest.TestCase):
    """E2E tests for query result aggregation across multiple repositories."""

    @classmethod
    def setUpClass(cls):
        """Set up test repositories with different code content."""
        cls.test_dir = Path(tempfile.mkdtemp(prefix="query_aggregation_test_"))

        # Create 3 test repositories with different content
        cls.repos = []

        # Repo 1: Authentication code
        repo1 = cls.test_dir / "auth-service"
        repo1.mkdir(parents=True)
        (repo1 / "auth.py").write_text(
            """
def authenticate(username, password):
    \"\"\"Authenticate user with credentials.\"\"\"
    if not username or not password:
        return False
    return validate_credentials(username, password)

def validate_credentials(username, password):
    \"\"\"Validate user credentials against database.\"\"\"
    return True
"""
        )
        (repo1 / "login.py").write_text(
            """
def login(user):
    \"\"\"Login user to system.\"\"\"
    return authenticate(user.name, user.password)
"""
        )
        cls._init_git_repo(repo1)
        cls.repos.append(str(repo1))

        # Repo 2: User management code
        repo2 = cls.test_dir / "user-service"
        repo2.mkdir(parents=True)
        (repo2 / "user.py").write_text(
            """
class User:
    \"\"\"User model with authentication support.\"\"\"
    def __init__(self, username):
        self.username = username
        self.authenticated = False

    def authenticate(self):
        \"\"\"Mark user as authenticated.\"\"\"
        self.authenticated = True
"""
        )
        cls._init_git_repo(repo2)
        cls.repos.append(str(repo2))

        # Repo 3: API layer code
        repo3 = cls.test_dir / "api-service"
        repo3.mkdir(parents=True)
        (repo3 / "api.py").write_text(
            """
def auth_endpoint(request):
    \"\"\"Authentication API endpoint.\"\"\"
    username = request.get('username')
    password = request.get('password')
    return authenticate_request(username, password)

def authenticate_request(username, password):
    \"\"\"Process authentication request.\"\"\"
    return {'authenticated': True}
"""
        )
        cls._init_git_repo(repo3)
        cls.repos.append(str(repo3))

    @classmethod
    def _init_git_repo(cls, repo_path: Path):
        """Initialize git repository."""
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
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
        subprocess.run(
            ["git", "add", "."], cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

    @classmethod
    def tearDownClass(cls):
        """Clean up test repositories."""
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir)

    def test_aggregate_results_from_mock_outputs(self):
        """Test aggregating results from multiple repositories (mock outputs).

        This test validates Stories 3.1-3.4 using mock query outputs without
        requiring actual indexing/embedding services.
        """
        # Mock query outputs from 3 repositories
        repo_outputs = {
            self.repos[
                0
            ]: """0.95 {}/auth.py:2-7
  2: def authenticate(username, password):
  3:     \"\"\"Authenticate user with credentials.\"\"\"
  4:     if not username or not password:
  5:         return False
  6:     return validate_credentials(username, password)
  7:

0.85 {}/login.py:2-4
  2: def login(user):
  3:     \"\"\"Login user to system.\"\"\"
  4:     return authenticate(user.name, user.password)""".format(
                self.repos[0], self.repos[0]
            ),
            self.repos[
                1
            ]: """0.92 {}/user.py:8-11
  8:     def authenticate(self):
  9:         \"\"\"Mark user as authenticated.\"\"\"
  10:         self.authenticated = True
  11:""".format(
                self.repos[1]
            ),
            self.repos[
                2
            ]: """0.88 {}/api.py:2-6
  2: def auth_endpoint(request):
  3:     \"\"\"Authentication API endpoint.\"\"\"
  4:     username = request.get('username')
  5:     password = request.get('password')
  6:     return authenticate_request(username, password)

0.82 {}/api.py:8-11
  8: def authenticate_request(username, password):
  9:     \"\"\"Process authentication request.\"\"\"
  10:     return {{'authenticated': True}}
  11:""".format(
                self.repos[2], self.repos[2]
            ),
        }

        # Story 3.1-3.4: Aggregate results
        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Verify all results present
        self.assertIn("0.95", output, "Highest score result missing")
        self.assertIn("0.92", output, "Second highest result missing")
        self.assertIn("0.88", output, "Third highest result missing")
        self.assertIn("0.85", output, "Fourth highest result missing")
        self.assertIn("0.82", output, "Fifth highest result missing")

        # Story 3.2: Verify sorted by score (descending)
        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # Extract scores from result lines
        scores = []
        for line in score_lines:
            score = float(line.split()[0])
            scores.append(score)

        # Verify descending order
        self.assertEqual(
            scores,
            sorted(scores, reverse=True),
            "Results not sorted by score descending",
        )

        # Story 3.4: Verify repository context preserved
        self.assertIn(self.repos[0], output, "Repo 1 path missing from output")
        self.assertIn(self.repos[1], output, "Repo 2 path missing from output")
        self.assertIn(self.repos[2], output, "Repo 3 path missing from output")

        # Verify code content preserved
        self.assertIn("def authenticate", output)
        self.assertIn("def login", output)
        self.assertIn("def auth_endpoint", output)

    def test_global_limit_application(self):
        """Test that --limit applies to total results, not per repository (Story 3.3)."""
        # Create mock outputs with 2 results per repo (6 total)
        repo_outputs = {
            self.repos[
                0
            ]: """0.95 {}/auth.py:2-5
  2: code1

0.90 {}/auth.py:8-10
  8: code2""".format(
                self.repos[0], self.repos[0]
            ),
            self.repos[
                1
            ]: """0.92 {}/user.py:2-5
  2: code3

0.88 {}/user.py:8-10
  8: code4""".format(
                self.repos[1], self.repos[1]
            ),
            self.repos[
                2
            ]: """0.85 {}/api.py:2-5
  2: code5

0.80 {}/api.py:8-10
  8: code6""".format(
                self.repos[2], self.repos[2]
            ),
        }

        # Apply limit of 3
        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=3)

        # Count results in output
        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # Should have exactly 3 results (global limit)
        self.assertEqual(
            len(score_lines),
            3,
            f"Expected 3 results with limit=3, got {len(score_lines)}",
        )

        # Should be top 3 by score: 0.95, 0.92, 0.90
        scores = [float(l.split()[0]) for l in score_lines]
        self.assertEqual(
            scores, [0.95, 0.92, 0.90], "Limit did not return top 3 results by score"
        )

    def test_interleaved_results_not_grouped_by_repo(self):
        """Test that results are interleaved by score, not grouped by repository (Story 3.2)."""
        repo_outputs = {
            self.repos[
                0
            ]: """0.95 {}/file1.py:1-5
  1: high score repo1

0.75 {}/file2.py:1-5
  1: low score repo1""".format(
                self.repos[0], self.repos[0]
            ),
            self.repos[
                1
            ]: """0.85 {}/file3.py:1-5
  1: medium score repo2""".format(
                self.repos[1]
            ),
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Extract repo paths in order of appearance
        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        repo_order = []
        for line in score_lines:
            if self.repos[0] in line:
                repo_order.append("repo1")
            elif self.repos[1] in line:
                repo_order.append("repo2")

        # Should be interleaved: repo1 (0.95), repo2 (0.85), repo1 (0.75)
        # NOT grouped: repo1, repo1, repo2
        self.assertEqual(
            repo_order,
            ["repo1", "repo2", "repo1"],
            f"Results grouped by repo instead of interleaved by score: {repo_order}",
        )

    def test_handle_empty_repository_results(self):
        """Test handling repositories with no query results (Story 3.1)."""
        repo_outputs = {
            self.repos[
                0
            ]: """0.9 {}/file.py:1-5
  1: code""".format(
                self.repos[0]
            ),
            self.repos[1]: "",  # Empty output
            self.repos[
                2
            ]: """0.8 {}/file.py:1-5
  1: code""".format(
                self.repos[2]
            ),
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Should include results from repos 0 and 2, skip empty repo 1
        self.assertIn("0.9", output)
        self.assertIn("0.8", output)

        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]
        self.assertEqual(len(score_lines), 2)

    def test_handle_error_outputs(self):
        """Test skipping repositories with error outputs (Story 3.1)."""
        repo_outputs = {
            self.repos[
                0
            ]: """0.9 {}/file.py:1-5
  1: code""".format(
                self.repos[0]
            ),
            self.repos[1]: "Error: Failed to connect to service",
            self.repos[
                2
            ]: """0.8 {}/file.py:1-5
  1: code""".format(
                self.repos[2]
            ),
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Should skip error output, include valid results
        self.assertIn("0.9", output)
        self.assertIn("0.8", output)
        self.assertNotIn("Error", output)

    def test_no_limit_returns_all_results(self):
        """Test that limit=None returns all results (Story 3.3)."""
        repo_outputs = {
            self.repos[
                0
            ]: """0.9 {}/a.py:1-5
  1: a

0.8 {}/b.py:1-5
  1: b""".format(
                self.repos[0], self.repos[0]
            ),
            self.repos[
                1
            ]: """0.85 {}/c.py:1-5
  1: c""".format(
                self.repos[1]
            ),
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=None)

        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # Should return all 3 results
        self.assertEqual(len(score_lines), 3)

    def test_preserve_code_content_and_formatting(self):
        """Test that code content and formatting are preserved (Story 3.4)."""
        repo_outputs = {
            self.repos[
                0
            ]: """0.9 {}/auth.py:1-5
  1: class Authentication:
  2:     def __init__(self):
  3:         self.users = {{}}
  4:     def login(self, user):
  5:         return user in self.users""".format(
                self.repos[0]
            )
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Verify all content lines preserved
        self.assertIn("class Authentication:", output)
        self.assertIn("def __init__(self):", output)
        self.assertIn("self.users = {}", output)
        self.assertIn("def login(self, user):", output)
        self.assertIn("return user in self.users", output)

        # Verify line numbers preserved
        self.assertIn("  1:", output)
        self.assertIn("  2:", output)
        self.assertIn("  3:", output)


if __name__ == "__main__":
    unittest.main()
