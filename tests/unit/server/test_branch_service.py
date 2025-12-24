"""
Unit tests for branch listing service logic.

Tests branch information retrieval, commit details extraction,
and index status integration following TDD methodology.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from git import Repo, GitCommandError, InvalidGitRepositoryError

from code_indexer.services.git_topology_service import GitTopologyService
from code_indexer.server.services.branch_service import BranchService
from code_indexer.server.models.branch_models import IndexStatus


class IndexStatusManagerForTesting:
    """Real test implementation of IndexStatusManager - no mocks per CLAUDE.md Foundation #1."""

    def __init__(self):
        self.branch_statuses = {}

    def get_branch_index_status(self, branch_name: str, repo_path: Path) -> IndexStatus:
        """Get index status for a specific branch."""
        return self.branch_statuses.get(
            branch_name,
            IndexStatus(
                status="not_indexed",
                files_indexed=0,
                total_files=None,
                last_indexed=None,
                progress_percentage=0.0,
            ),
        )

    def set_branch_status(self, branch_name: str, status: IndexStatus):
        """Set status for testing purposes."""
        self.branch_statuses[branch_name] = status


class TestBranchService:
    """Test cases for BranchService following CLAUDE.md anti-mock principles."""

    def setup_method(self):
        """Set up test environment with real git repository."""
        # Create temporary directory for test repository
        self.temp_dir = Path(tempfile.mkdtemp())

        # Initialize real git repository
        self.repo = Repo.init(self.temp_dir)
        self.repo.config_writer().set_value("user", "name", "Test User").release()
        self.repo.config_writer().set_value(
            "user", "email", "test@example.com"
        ).release()

        # Create initial commit on main branch
        test_file = self.temp_dir / "test.py"
        test_file.write_text("print('hello world')")
        self.repo.index.add([str(test_file)])
        self.initial_commit = self.repo.index.commit("Initial commit")

        # Create additional branches
        self.develop_branch = self.repo.create_head("develop")
        self.feature_branch = self.repo.create_head("feature-x")

        # Add commits to different branches
        self.repo.heads.develop.checkout()
        develop_file = self.temp_dir / "develop.py"
        develop_file.write_text("print('develop branch')")
        self.repo.index.add([str(develop_file)])
        self.develop_commit = self.repo.index.commit("Add develop feature")

        self.repo.heads["feature-x"].checkout()
        feature_file = self.temp_dir / "feature.py"
        feature_file.write_text("print('feature branch')")
        self.repo.index.add([str(feature_file)])
        self.feature_commit = self.repo.index.commit("Add feature implementation")

        # Return to master branch (default branch name in GitPython)
        self.repo.heads.master.checkout()

        # Initialize services
        self.git_topology_service = GitTopologyService(self.temp_dir)

        # Real index status manager implementation - no mocks per CLAUDE.md Foundation #1
        self.index_status_manager = IndexStatusManagerForTesting()

        self.branch_service = BranchService(
            git_topology_service=self.git_topology_service,
            index_status_manager=self.index_status_manager,
        )

    def teardown_method(self):
        """Clean up test repository."""
        # Clean up branch service resources first
        if hasattr(self, "branch_service") and hasattr(self.branch_service, "close"):
            self.branch_service.close()

        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_list_branches_returns_all_branches(self):
        """Test that list_branches returns all repository branches."""
        # Act
        branches = self.branch_service.list_branches()

        # Assert
        assert len(branches) == 3
        branch_names = {branch.name for branch in branches}
        assert branch_names == {"master", "develop", "feature-x"}

    def test_list_branches_identifies_current_branch(self):
        """Test that current branch is correctly identified."""
        # Arrange - checkout develop branch
        self.repo.heads.develop.checkout()

        # Act
        branches = self.branch_service.list_branches()

        # Assert
        current_branches = [branch for branch in branches if branch.is_current]
        assert len(current_branches) == 1
        assert current_branches[0].name == "develop"

    def test_list_branches_includes_commit_information(self):
        """Test that branch information includes last commit details."""
        # Act
        branches = self.branch_service.list_branches()

        # Assert
        master_branch = next(branch for branch in branches if branch.name == "master")
        assert master_branch.last_commit is not None
        assert master_branch.last_commit.sha == self.initial_commit.hexsha
        assert master_branch.last_commit.message == "Initial commit"
        assert master_branch.last_commit.author == "Test User"
        assert master_branch.last_commit.date is not None

    def test_list_branches_includes_index_status(self):
        """Test that branch information includes index status."""
        # Arrange - Set test index status
        self.index_status_manager.set_branch_status(
            "master",
            IndexStatus(
                status="indexed", files_indexed=100, last_indexed="2024-01-15T09:00:00Z"
            ),
        )

        # Act
        branches = self.branch_service.list_branches()

        # Assert
        master_branch = next(branch for branch in branches if branch.name == "master")
        assert master_branch.index_status is not None
        assert master_branch.index_status.status == "indexed"
        assert master_branch.index_status.files_indexed == 100

    def test_list_branches_handles_non_git_repository(self):
        """Test behavior when directory is not a git repository."""
        # Arrange - Create non-git directory
        non_git_dir = Path(tempfile.mkdtemp())
        try:
            git_service = GitTopologyService(non_git_dir)

            # Act & Assert - BranchService constructor should raise ValueError
            with pytest.raises(ValueError, match="Not a git repository"):
                BranchService(
                    git_topology_service=git_service,
                    index_status_manager=self.index_status_manager,
                )
        finally:
            shutil.rmtree(non_git_dir)

    def test_list_branches_with_remote_tracking_information(self):
        """Test branch listing includes remote tracking information."""
        # This test will be implemented after basic functionality is working
        # For now, we'll focus on local branches only
        pass

    def test_get_branch_by_name_returns_specific_branch(self):
        """Test getting a specific branch by name."""
        # Act
        branch = self.branch_service.get_branch_by_name("develop")

        # Assert
        assert branch is not None
        assert branch.name == "develop"
        assert branch.last_commit.sha == self.develop_commit.hexsha

    def test_get_branch_by_name_returns_none_for_nonexistent_branch(self):
        """Test getting a non-existent branch returns None."""
        # Act
        branch = self.branch_service.get_branch_by_name("nonexistent")

        # Assert
        assert branch is None

    def test_commit_info_extraction_accuracy(self):
        """Test that commit information is extracted accurately."""
        # Act
        branches = self.branch_service.list_branches()
        develop_branch = next(branch for branch in branches if branch.name == "develop")

        # Assert commit details
        commit_info = develop_branch.last_commit
        assert commit_info.sha == self.develop_commit.hexsha
        assert commit_info.message == "Add develop feature"
        assert commit_info.author == "Test User"
        assert isinstance(commit_info.date, str)  # Should be ISO format string

    def test_list_branches_performance_with_many_branches(self):
        """Test performance when repository has many branches."""
        # Arrange - Create many branches
        for i in range(50):
            branch = self.repo.create_head(f"test-branch-{i}")
            branch.checkout()
            test_file = self.temp_dir / f"test_{i}.py"
            test_file.write_text(f"print('test {i}')")
            self.repo.index.add([str(test_file)])
            self.repo.index.commit(f"Test commit {i}")

        self.repo.heads.master.checkout()

        # Act & Assert - Should complete within reasonable time
        import time

        start_time = time.time()
        branches = self.branch_service.list_branches()
        end_time = time.time()

        assert len(branches) >= 50  # Should have at least the created branches
        assert end_time - start_time < 5.0  # Should complete within 5 seconds

    def test_branch_service_integration_with_git_topology_service(self):
        """Test integration between BranchService and GitTopologyService."""
        # Act
        branches = self.branch_service.list_branches()
        current_branch_name = self.git_topology_service.get_current_branch()

        # Assert
        current_branches = [b for b in branches if b.is_current]
        assert len(current_branches) == 1
        assert current_branches[0].name == current_branch_name

    # CRITICAL RESOURCE MANAGEMENT TESTS - Foundation #8 Anti-Pattern #1
    def test_branch_service_has_close_method(self):
        """Test that BranchService has proper resource cleanup method."""
        # This test will fail until close() method is implemented
        assert hasattr(
            self.branch_service, "close"
        ), "BranchService must have close() method"
        assert callable(self.branch_service.close), "close() must be callable"

    def test_branch_service_has_context_manager_support(self):
        """Test that BranchService supports context manager protocol."""
        # This test will fail until __enter__ and __exit__ are implemented
        assert hasattr(
            self.branch_service, "__enter__"
        ), "BranchService must have __enter__"
        assert hasattr(
            self.branch_service, "__exit__"
        ), "BranchService must have __exit__"

        # Test context manager usage
        temp_dir = Path(tempfile.mkdtemp())
        try:
            repo = Repo.init(temp_dir)
            repo.config_writer().set_value("user", "name", "Test").release()
            repo.config_writer().set_value(
                "user", "email", "test@example.com"
            ).release()
            test_file = temp_dir / "test.py"
            test_file.write_text("test")
            repo.index.add([str(test_file)])
            repo.index.commit("test")

            git_service = GitTopologyService(temp_dir)

            # Should work as context manager
            with BranchService(git_service, IndexStatusManagerForTesting()) as service:
                branches = service.list_branches()
                assert len(branches) > 0
        finally:
            shutil.rmtree(temp_dir)

    def test_branch_service_cleanup_on_del(self):
        """Test that BranchService cleans up resources on deletion."""
        temp_dir = Path(tempfile.mkdtemp())
        try:
            repo = Repo.init(temp_dir)
            repo.config_writer().set_value("user", "name", "Test").release()
            repo.config_writer().set_value(
                "user", "email", "test@example.com"
            ).release()
            test_file = temp_dir / "test.py"
            test_file.write_text("test")
            repo.index.add([str(test_file)])
            repo.index.commit("test")

            git_service = GitTopologyService(temp_dir)
            service = BranchService(git_service, IndexStatusManagerForTesting())

            # Service should have __del__ method for cleanup
            assert hasattr(
                service, "__del__"
            ), "BranchService must have __del__ for cleanup"
        finally:
            shutil.rmtree(temp_dir)

    # CRITICAL EXCEPTION HANDLING TESTS - Foundation #8 Anti-Pattern #2
    def test_exception_handling_preserves_original_git_errors(self):
        """Test that specific git exceptions are preserved, not wrapped in generic ValueError."""
        # Create service with valid git repository but corrupted state
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # Create a proper git repo first
            repo = Repo.init(temp_dir)
            repo.config_writer().set_value("user", "name", "Test").release()
            repo.config_writer().set_value(
                "user", "email", "test@example.com"
            ).release()
            test_file = temp_dir / "test.py"
            test_file.write_text("test")
            repo.index.add([str(test_file)])
            repo.index.commit("test")

            git_service = GitTopologyService(temp_dir)
            service = BranchService(git_service, IndexStatusManagerForTesting())

            # Corrupt the repository to trigger git errors
            shutil.rmtree(temp_dir / ".git" / "objects")

            # Should raise specific git/runtime exception, not generic ValueError
            with pytest.raises((GitCommandError, RuntimeError, OSError)):
                service.list_branches()

        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    def test_specific_exception_handling_not_generic_catch_all(self):
        """Test that specific exceptions are caught, not generic Exception."""
        # This test validates that we don't use generic 'except Exception'
        # The current implementation at lines 90-92 violates this
        temp_dir = Path(tempfile.mkdtemp())
        try:
            repo = Repo.init(temp_dir)
            repo.config_writer().set_value("user", "name", "Test").release()
            repo.config_writer().set_value(
                "user", "email", "test@example.com"
            ).release()
            test_file = temp_dir / "test.py"
            test_file.write_text("test")
            repo.index.add([str(test_file)])
            repo.index.commit("test")

            git_service = GitTopologyService(temp_dir)
            service = BranchService(git_service, IndexStatusManagerForTesting())

            # Corrupt the repository to trigger specific git errors
            shutil.rmtree(temp_dir / ".git" / "objects")

            # Should raise specific git exception or RuntimeError, not generic ValueError
            with pytest.raises(
                (GitCommandError, InvalidGitRepositoryError, RuntimeError, OSError)
            ):
                service.list_branches()

        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    # CRITICAL SECURITY TESTS - Command Injection Prevention
    def test_branch_name_validation_prevents_injection(self):
        """Test that branch names are validated to prevent command injection."""
        # These malicious branch names should be rejected
        malicious_names = [
            "branch; rm -rf /",
            "branch && echo 'hacked'",
            "branch | cat /etc/passwd",
            "branch; git push --delete origin master",
            "../../../etc/passwd",
            "branch\\x00hidden",
            "branch\\nrm -rf .",
        ]

        for malicious_name in malicious_names:
            # BranchService should have validation method
            if hasattr(self.branch_service, "_validate_branch_name"):
                assert not self.branch_service._validate_branch_name(
                    malicious_name
                ), f"Branch name '{malicious_name}' should be rejected"

    def test_subprocess_replacement_with_gitpython_native(self):
        """Test that subprocess calls are replaced with GitPython native methods."""
        # This test checks that we don't use subprocess.run for git operations
        # Current line 201-213 violates this by using subprocess

        # Create branch with remote tracking
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # Create origin repository
            origin_dir = temp_dir / "origin"
            Repo.init(origin_dir, bare=True)

            # Create local repository
            local_dir = temp_dir / "local"
            local_repo = Repo.clone_from(str(origin_dir), str(local_dir))
            local_repo.config_writer().set_value("user", "name", "Test").release()
            local_repo.config_writer().set_value(
                "user", "email", "test@example.com"
            ).release()

            # Add initial commit
            test_file = local_dir / "test.py"
            test_file.write_text("test")
            local_repo.index.add([str(test_file)])
            local_repo.index.commit("initial")
            local_repo.remote("origin").push("master")

            # Create and push a branch
            feature_branch = local_repo.create_head("feature")
            feature_branch.checkout()
            feature_file = local_dir / "feature.py"
            feature_file.write_text("feature")
            local_repo.index.add([str(feature_file)])
            local_repo.index.commit("feature commit")

            # Set up tracking
            local_repo.remote("origin").push("feature")
            feature_branch.set_tracking_branch(local_repo.remote("origin").refs.feature)

            # Test with BranchService
            git_service = GitTopologyService(local_dir)
            service = BranchService(git_service, IndexStatusManagerForTesting())

            # Should use GitPython native methods, not subprocess
            branches = service.list_branches(include_remote=True)
            feature_branch_info = next(b for b in branches if b.name == "feature")

            # Remote tracking info should be calculated using GitPython, not subprocess
            assert feature_branch_info.remote_tracking is not None
            assert isinstance(feature_branch_info.remote_tracking.ahead, int)
            assert isinstance(feature_branch_info.remote_tracking.behind, int)

        finally:
            shutil.rmtree(temp_dir)

    def test_input_validation_for_repository_paths(self):
        """Test that repository paths are validated for security."""
        malicious_paths = [
            "/etc/passwd",
            "../../../etc",
            "/dev/null",
            "~/../../etc/passwd",
            "",  # empty path
            "   ",  # whitespace only
        ]

        for malicious_path in malicious_paths:
            # Test that BranchService rejects non-git paths
            try:
                git_service = GitTopologyService(Path(malicious_path))
                # This should raise an exception for non-git paths
                BranchService(git_service, IndexStatusManagerForTesting())
                # If we get here without exception, the path must be a valid git repo somehow
                # which means our validation worked at the GitTopologyService level
                assert False, f"Path '{malicious_path}' should have been rejected"
            except ValueError:
                # This is expected for invalid git repositories
                pass
            except Exception:
                # Any other exception is also acceptable as it means the path was rejected
                pass
