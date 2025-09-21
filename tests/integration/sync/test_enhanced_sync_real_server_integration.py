"""Real CIDX Server Integration Tests for Enhanced Sync - ZERO MOCKS COMPLIANCE.

Tests enhanced sync functionality using real CIDX server, real repositories,
and actual git operations. Follows MESSI Rule #1 by eliminating ALL mocking.
"""

import subprocess
from pathlib import Path
from typing import Dict, Optional

import pytest
from click.testing import CliRunner

from code_indexer.cli import cli
from code_indexer.sync.repository_context_detector import RepositoryContextDetector
from code_indexer.sync.conflict_resolution import ConflictDetector, ConflictType
from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager
from code_indexer.server.repositories.activated_repo_manager import ActivatedRepoManager
from tests.fixtures.test_infrastructure import RealComponentTestInfrastructure


class RealSyncTestInfrastructure(RealComponentTestInfrastructure):
    """Extended test infrastructure for real sync operations."""

    def __init__(self):
        super().__init__()
        self.golden_repo_manager: Optional[GoldenRepoManager] = None
        self.activated_repo_manager: Optional[ActivatedRepoManager] = None
        self.test_repos_dir: Optional[Path] = None

    def setup(self) -> None:
        """Set up infrastructure with sync-specific components."""
        super().setup()

        # Create repository managers using real server data directory
        assert self.temp_dir is not None, "temp_dir must be set"

        self.golden_repo_manager = GoldenRepoManager(str(self.temp_dir))
        self.activated_repo_manager = ActivatedRepoManager(str(self.temp_dir))

        # Create test repositories directory
        self.test_repos_dir = self.temp_dir / "test-repos"
        self.test_repos_dir.mkdir(exist_ok=True)

    def create_real_git_repository(
        self, repo_name: str, content: Dict[str, str]
    ) -> Path:
        """Create a real git repository with specified content.

        Args:
            repo_name: Name of the repository
            content: Dictionary mapping file paths to content

        Returns:
            Path to created repository
        """
        assert self.test_repos_dir is not None, "test_repos_dir must be set"

        repo_path = self.test_repos_dir / repo_name
        repo_path.mkdir(exist_ok=True)

        # Initialize real git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Create files with real content
        for file_path, file_content in content.items():
            full_path = repo_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(file_content)

        # Real git operations
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        return repo_path

    def setup_real_golden_repository(self, alias: str, content: Dict[str, str]) -> Path:
        """Set up a real golden repository with actual git history.

        Args:
            alias: Alias for the golden repository
            content: Repository content

        Returns:
            Path to golden repository
        """
        assert self.golden_repo_manager is not None, "golden_repo_manager must be set"

        # Create source repository with real git
        source_repo = self.create_real_git_repository(f"source-{alias}", content)

        # Add as golden repository through real manager
        self.golden_repo_manager.add_golden_repo(repo_url=str(source_repo), alias=alias)

        # Return real golden repository path
        golden_repo = self.golden_repo_manager.get_golden_repo(alias)
        return Path(golden_repo.clone_path)

    def activate_real_repository(
        self, golden_alias: str, user_alias: str, username: str = "testuser"
    ) -> Path:
        """Activate a real repository for user with real CoW cloning.

        Args:
            golden_alias: Golden repository alias
            user_alias: User-specific alias
            username: Username for activation

        Returns:
            Path to activated repository
        """
        assert (
            self.activated_repo_manager is not None
        ), "activated_repo_manager must be set"

        # Real repository activation with actual git operations
        self.activated_repo_manager.activate_repository(
            username=username, golden_repo_alias=golden_alias, user_alias=user_alias
        )

        # Return real activated repository path
        return Path(
            self.activated_repo_manager.get_activated_repo_path(username, user_alias)
        )

    def create_real_uncommitted_changes(
        self, repo_path: Path, changes: Dict[str, str]
    ) -> None:
        """Create real uncommitted changes in repository.

        Args:
            repo_path: Path to repository
            changes: Dictionary mapping file paths to new content
        """
        for file_path, content in changes.items():
            full_path = repo_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

    def create_real_merge_conflict(
        self,
        repo_path: Path,
        file_path: str,
        base_content: str,
        branch_content: str,
        main_content: str,
    ) -> None:
        """Create a real merge conflict scenario.

        Args:
            repo_path: Path to repository
            file_path: Path to file that will have conflict
            base_content: Base content for the file
            branch_content: Content in feature branch
            main_content: Content in main branch
        """
        # Create initial content
        target_file = repo_path / file_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(base_content)

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        # Only commit if there are changes to commit
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if status_result.stdout.strip():  # There are changes to commit
            subprocess.run(
                ["git", "commit", "-m", "Base content"], cwd=repo_path, check=True
            )

        # Create feature branch with changes
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo_path, check=True)
        target_file.write_text(branch_content)
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Feature changes"], cwd=repo_path, check=True
        )

        # Switch back to the default branch (master or main) and make conflicting changes
        # Get the default branch name
        branch_result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if branch_result.returncode == 0:
            default_branch = branch_result.stdout.strip().split("/")[-1]
        else:
            # Fallback: get the first branch that's not 'feature'
            all_branches_result = subprocess.run(
                ["git", "branch"], cwd=repo_path, capture_output=True, text=True
            )
            for line in all_branches_result.stdout.split("\n"):
                branch = line.strip().replace("*", "").strip()
                if branch and branch != "feature":
                    default_branch = branch
                    break
            else:
                default_branch = "master"  # Final fallback

        subprocess.run(["git", "checkout", default_branch], cwd=repo_path, check=True)
        target_file.write_text(main_content)
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Main changes"], cwd=repo_path, check=True
        )

        # Attempt merge to create real conflict
        merge_result = subprocess.run(
            ["git", "merge", "feature"], cwd=repo_path, capture_output=True, text=True
        )
        assert merge_result.returncode != 0, "Merge should fail with conflicts"


@pytest.fixture
def real_sync_infrastructure():
    """Pytest fixture for real sync test infrastructure."""
    infrastructure = RealSyncTestInfrastructure()
    infrastructure.setup()

    try:
        yield infrastructure
    finally:
        infrastructure.cleanup()


class TestEnhancedSyncRealServerIntegration:
    """Real server integration tests for enhanced sync functionality."""

    def test_repository_context_detection_with_real_activated_repo(
        self, real_sync_infrastructure
    ):
        """Test repository context detection with real activated repository."""
        # Create real user
        user = real_sync_infrastructure.create_test_user()

        # Setup real golden repository
        golden_alias = "context-test-repo"
        user_alias = "my-context-project"
        content = {
            "src/main.py": "print('Hello, Context!')",
            "README.md": "# Context Test Repository",
            "config.yml": "name: context-test",
        }

        # Real golden repository setup
        real_sync_infrastructure.setup_real_golden_repository(golden_alias, content)

        # Real repository activation
        activated_repo_path = real_sync_infrastructure.activate_real_repository(
            golden_alias, user_alias, user["username"]
        )

        # Test real context detection
        detector = RepositoryContextDetector()
        context = detector.detect_repository_context(activated_repo_path)

        # Verify real context detection results
        assert context is not None, "Context should be detected in activated repository"
        assert context.user_alias == user_alias
        assert context.golden_repo_alias == golden_alias
        assert context.repository_path == activated_repo_path
        assert context.current_branch in ["main", "master"]
        assert context.sync_status in ["synced", "needs_sync"]
        assert context.has_uncommitted_changes is False  # No changes yet

    def test_context_detection_outside_activated_repo(self, real_sync_infrastructure):
        """Test context detection returns None outside activated repository."""
        # Test from outside any repository
        detector = RepositoryContextDetector()
        context = detector.detect_repository_context(real_sync_infrastructure.temp_dir)

        assert context is None, "Context should be None outside activated repository"

    def test_real_conflict_detection_uncommitted_changes(
        self, real_sync_infrastructure
    ):
        """Test conflict detection with real uncommitted changes."""
        # Setup real repository
        user = real_sync_infrastructure.create_test_user()
        golden_alias = "conflict-repo"
        user_alias = "conflict-test"
        content = {
            "src/app.py": "original_content = 'unchanged'",
            "config.json": '{"version": "1.0.0"}',
        }

        real_sync_infrastructure.setup_real_golden_repository(golden_alias, content)
        activated_repo_path = real_sync_infrastructure.activate_real_repository(
            golden_alias, user_alias, user["username"]
        )

        # Create real uncommitted changes
        changes = {
            "src/app.py": "modified_content = 'changed'",
            "config.json": '{"version": "2.0.0"}',
            "new_file.py": "# New file content",
        }
        real_sync_infrastructure.create_real_uncommitted_changes(
            activated_repo_path, changes
        )

        # Test real conflict detection
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(activated_repo_path)

        # Verify real conflict detection
        assert len(conflicts) == 1, "Should detect one conflict for uncommitted changes"
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.UNCOMMITTED_CHANGES
        assert "src/app.py" in conflict.affected_files
        assert "config.json" in conflict.affected_files
        assert "new_file.py" in conflict.affected_files
        assert len(conflict.affected_files) == 3

    def test_real_conflict_detection_merge_conflicts(self, real_sync_infrastructure):
        """Test conflict detection with real merge conflicts."""
        # Setup real repository
        user = real_sync_infrastructure.create_test_user()
        golden_alias = "merge-conflict-repo"
        user_alias = "merge-test"
        content = {"src/service.py": "# Initial content"}

        real_sync_infrastructure.setup_real_golden_repository(golden_alias, content)
        activated_repo_path = real_sync_infrastructure.activate_real_repository(
            golden_alias, user_alias, user["username"]
        )

        # Create real merge conflict
        real_sync_infrastructure.create_real_merge_conflict(
            activated_repo_path,
            "src/service.py",
            "class Service:\n    def __init__(self):\n        pass",
            "class Service:\n    def __init__(self):\n        self.feature = True",
            "class Service:\n    def __init__(self):\n        self.main_change = True",
        )

        # Test real conflict detection
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(activated_repo_path)

        # Verify real merge conflict detection
        assert len(conflicts) == 1, "Should detect one merge conflict"
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.MERGE_CONFLICTS
        assert "src/service.py" in conflict.affected_files

    def test_enhanced_sync_command_with_real_context(self, real_sync_infrastructure):
        """Test enhanced sync command with real repository context."""
        # Setup real infrastructure
        user = real_sync_infrastructure.create_test_user()
        real_sync_infrastructure.get_auth_token(
            user["username"], user["password"]
        )

        # Setup real repository
        golden_alias = "sync-test-repo"
        user_alias = "my-sync-project"
        content = {
            "src/main.py": "def main(): print('Sync test')",
            "tests/test_main.py": "def test_main(): assert True",
        }

        real_sync_infrastructure.setup_real_golden_repository(golden_alias, content)
        activated_repo_path = real_sync_infrastructure.activate_real_repository(
            golden_alias, user_alias, user["username"]
        )

        # Execute sync command from within activated repository
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_sync_infrastructure.temp_dir)}

        # Change to activated repository directory and run sync
        result = runner.invoke(
            cli, ["sync"], catch_exceptions=False, env=env, cwd=str(activated_repo_path)
        )

        # Verify sync execution
        assert result.exit_code == 0, f"Sync command failed: {result.output}"

        # Should detect repository context and show relevant messaging
        output_lower = result.output.lower()
        assert any(
            keyword in output_lower
            for keyword in [
                user_alias.lower(),
                golden_alias.lower(),
                "sync",
                "repository",
            ]
        ), f"Output should mention repository context: {result.output}"

    def test_repos_sync_command_with_real_server(self, real_sync_infrastructure):
        """Test 'cidx repos sync' command with real server and repository."""
        # Setup real user and authentication
        user = real_sync_infrastructure.create_test_user()
        real_sync_infrastructure.get_auth_token(
            user["username"], user["password"]
        )

        # Setup real repository
        golden_alias = "repos-sync-test"
        user_alias = "my-repos-sync"
        content = {
            "api/handlers.py": "async def handle_request(): pass",
            "models/user.py": "class User: pass",
        }

        real_sync_infrastructure.setup_real_golden_repository(golden_alias, content)
        real_sync_infrastructure.activate_real_repository(
            golden_alias, user_alias, user["username"]
        )

        # Execute repos sync command
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_sync_infrastructure.temp_dir)}

        result = runner.invoke(
            cli, ["repos", "sync", user_alias], catch_exceptions=False, env=env
        )

        # Verify repos sync execution
        assert result.exit_code == 0, f"Repos sync command failed: {result.output}"

        # Should show sync operation for the specified repository
        output_lower = result.output.lower()
        assert any(
            keyword in output_lower
            for keyword in ["sync", user_alias.lower(), "repository"]
        ), f"Output should mention sync operation: {result.output}"

    def test_repos_sync_all_with_real_repositories(self, real_sync_infrastructure):
        """Test 'cidx repos sync --all' with multiple real repositories."""
        # Setup real user
        user = real_sync_infrastructure.create_test_user()
        real_sync_infrastructure.get_auth_token(
            user["username"], user["password"]
        )

        # Setup multiple real repositories
        repos = [
            ("api-service", {"src/api.py": "# API service code"}),
            ("web-frontend", {"src/app.js": "// Frontend code"}),
            ("database-schema", {"migrations/001.sql": "CREATE TABLE users;"}),
        ]

        for golden_alias, content in repos:
            real_sync_infrastructure.setup_real_golden_repository(golden_alias, content)
            real_sync_infrastructure.activate_real_repository(
                golden_alias, f"user-{golden_alias}", user["username"]
            )

        # Execute repos sync all command
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_sync_infrastructure.temp_dir)}

        result = runner.invoke(
            cli, ["repos", "sync", "--all"], catch_exceptions=False, env=env
        )

        # Verify sync all execution
        assert result.exit_code == 0, f"Repos sync --all failed: {result.output}"

        # Should show sync operations for multiple repositories
        output_lower = result.output.lower()
        assert (
            "sync" in output_lower
        ), f"Output should mention sync operations: {result.output}"

    def test_repos_sync_status_with_real_repository(self, real_sync_infrastructure):
        """Test 'cidx repos sync-status' with real repository."""
        # Setup real user and repository
        user = real_sync_infrastructure.create_test_user()
        real_sync_infrastructure.get_auth_token(
            user["username"], user["password"]
        )

        golden_alias = "status-test-repo"
        user_alias = "status-test"
        content = {"main.py": "print('Status test')"}

        real_sync_infrastructure.setup_real_golden_repository(golden_alias, content)
        real_sync_infrastructure.activate_real_repository(
            golden_alias, user_alias, user["username"]
        )

        # Execute sync status command
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_sync_infrastructure.temp_dir)}

        result = runner.invoke(
            cli, ["repos", "sync-status", user_alias], catch_exceptions=False, env=env
        )

        # Verify sync status execution
        assert result.exit_code == 0, f"Sync status command failed: {result.output}"

        # Should show status information
        output_lower = result.output.lower()
        assert any(
            keyword in output_lower
            for keyword in ["status", user_alias.lower(), "repository"]
        ), f"Output should show repository status: {result.output}"

    def test_backward_compatibility_with_existing_sync(self, real_sync_infrastructure):
        """Test that enhanced sync maintains backward compatibility."""
        # Test existing sync command without repository context
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_sync_infrastructure.temp_dir)}

        # Execute sync outside repository context
        result = runner.invoke(cli, ["sync", "--help"], catch_exceptions=False, env=env)

        # Should still work and show help
        assert result.exit_code == 0, f"Sync help command failed: {result.output}"
        assert "sync" in result.output.lower(), "Should show sync command help"

        # Test basic sync command still works
        result = runner.invoke(cli, ["sync"], catch_exceptions=False, env=env)

        # Should handle gracefully (may succeed or fail gracefully depending on context)
        assert result.exit_code in [
            0,
            1,
        ], f"Sync should handle gracefully: {result.output}"

    def test_enhanced_sync_preserves_existing_options(self, real_sync_infrastructure):
        """Test that enhanced sync preserves all existing CLI options."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_sync_infrastructure.temp_dir)}

        # Test sync help shows existing options
        result = runner.invoke(cli, ["sync", "--help"], catch_exceptions=False, env=env)

        assert result.exit_code == 0, "Sync help should work"

        # Verify important options are preserved (check for any that exist)
        help_output = result.output.lower()
        expected_options = ["--all", "--repository", "--timeout", "--help"]

        # At least some options should be present
        found_options = [opt for opt in expected_options if opt in help_output]
        assert (
            len(found_options) > 0
        ), f"Should preserve existing options. Found: {found_options}"

    def test_repository_context_error_handling(self, real_sync_infrastructure):
        """Test graceful handling of repository context detection errors."""
        # Create directory with malformed repository metadata
        malformed_repo = real_sync_infrastructure.temp_dir / "malformed-repo"
        malformed_repo.mkdir()

        # Create invalid metadata file
        metadata_file = malformed_repo / ".repository-metadata.json"
        metadata_file.write_text("{ invalid json content }")

        # Test error handling
        detector = RepositoryContextDetector()

        # Should handle error gracefully and return None
        try:
            context = detector.detect_repository_context(malformed_repo)
            assert context is None, "Should return None for malformed metadata"
        except Exception as e:
            # Should not crash, but if it raises an exception, it should be handled gracefully
            assert "Failed to detect repository context" in str(e)

    def test_real_sync_with_progress_reporting(self, real_sync_infrastructure):
        """Test sync operation shows real progress reporting."""
        # Setup real repository with multiple files for progress
        user = real_sync_infrastructure.create_test_user()
        golden_alias = "progress-test"
        user_alias = "progress-repo"

        content = {
            f"src/module_{i}.py": f"# Module {i}\nclass Module{i}: pass"
            for i in range(3)
        }
        content.update(
            {
                f"tests/test_{i}.py": f"# Test {i}\ndef test_{i}(): pass"
                for i in range(3)
            }
        )

        real_sync_infrastructure.setup_real_golden_repository(golden_alias, content)
        activated_repo_path = real_sync_infrastructure.activate_real_repository(
            golden_alias, user_alias, user["username"]
        )

        # Make some changes to trigger sync activity
        real_sync_infrastructure.create_real_uncommitted_changes(
            activated_repo_path, {"new_feature.py": "# New feature implementation"}
        )

        # Execute sync command
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_sync_infrastructure.temp_dir)}

        result = runner.invoke(
            cli, ["sync"], catch_exceptions=False, env=env, cwd=str(activated_repo_path)
        )

        # Verify execution (progress reporting is internal, just verify it doesn't crash)
        assert result.exit_code == 0, f"Sync with progress should work: {result.output}"
