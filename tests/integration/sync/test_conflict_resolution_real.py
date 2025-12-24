"""Real System Integration Tests for Conflict Resolution - ANTI-MOCK COMPLIANCE.

Tests conflict detection and resolution with real git repositories and actual
conflict scenarios. Follows MESSI Rule #1 by eliminating ALL mocking.
"""

import subprocess

import pytest

from code_indexer.sync.conflict_resolution import (
    ConflictDetector,
    ConflictResolver,
    ConflictType,
    ResolutionAction,
    SyncConflict,
)
from tests.integration.sync.test_enhanced_sync_real_server_integration import (
    RealSyncTestInfrastructure,
)


@pytest.fixture
def real_conflict_infrastructure():
    """Pytest fixture for real conflict resolution test infrastructure."""
    infrastructure = RealSyncTestInfrastructure()
    infrastructure.setup()

    try:
        yield infrastructure
    finally:
        infrastructure.cleanup()


class TestConflictResolutionReal:
    """Real system integration tests for conflict resolution."""

    def test_detect_real_uncommitted_changes_multiple_files(
        self, real_conflict_infrastructure
    ):
        """Test detection of real uncommitted changes across multiple files."""
        # Create real repository
        content = {
            "src/main.py": "def main(): pass",
            "src/utils.py": "def utility(): pass",
            "config.yaml": "version: 1.0",
            "README.md": "# Project",
        }
        repo_path = real_conflict_infrastructure.create_real_git_repository(
            "uncommitted-test", content
        )

        # Make real uncommitted changes
        changes = {
            "src/main.py": "def main(): print('modified')",
            "src/utils.py": "def utility(): return 'changed'",
            "new_module.py": "# New module",
            "config.yaml": "version: 2.0\nnew_setting: true",
        }
        real_conflict_infrastructure.create_real_uncommitted_changes(repo_path, changes)

        # Test real conflict detection
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(repo_path)

        # Verify real detection results
        assert (
            len(conflicts) == 1
        ), "Should detect one conflict group for uncommitted changes"
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.UNCOMMITTED_CHANGES

        # Check all modified files are detected
        expected_files = {"src/main.py", "src/utils.py", "new_module.py", "config.yaml"}
        actual_files = set(conflict.affected_files)
        assert (
            actual_files == expected_files
        ), f"Expected {expected_files}, got {actual_files}"

        # Verify resolution suggestions
        expected_actions = {
            ResolutionAction.STASH,
            ResolutionAction.COMMIT,
            ResolutionAction.ABORT,
        }
        actual_actions = set(conflict.suggested_actions)
        assert (
            actual_actions == expected_actions
        ), "Should suggest stash, commit, or abort"

    def test_detect_real_merge_conflicts_complex_scenario(
        self, real_conflict_infrastructure
    ):
        """Test detection of real merge conflicts in complex scenario."""
        # Create real repository with initial content
        content = {
            "src/app.py": "class App:\n    def __init__(self):\n        self.config = {}"
        }
        repo_path = real_conflict_infrastructure.create_real_git_repository(
            "merge-conflict-test", content
        )

        # Create complex merge conflict scenario
        real_conflict_infrastructure.create_real_merge_conflict(
            repo_path,
            "src/app.py",
            "class App:\n    def __init__(self):\n        self.config = {}",
            "class App:\n    def __init__(self):\n        self.config = {'feature': True}",
            "class App:\n    def __init__(self):\n        self.config = {'main_feature': True}",
        )

        # Test real conflict detection
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(repo_path)

        # Verify real merge conflict detection
        assert len(conflicts) == 1, "Should detect one merge conflict"
        conflict = conflicts[0]
        assert conflict.conflict_type == ConflictType.MERGE_CONFLICTS
        assert "src/app.py" in conflict.affected_files
        assert ResolutionAction.MANUAL_RESOLVE in conflict.suggested_actions

    def test_real_conflict_resolution_stash_changes(self, real_conflict_infrastructure):
        """Test real conflict resolution by stashing changes."""
        # Create repository with uncommitted changes
        content = {"src/service.py": "class Service: pass"}
        repo_path = real_conflict_infrastructure.create_real_git_repository(
            "stash-test", content
        )

        # Make uncommitted changes
        changes = {"src/service.py": "class Service:\n    def enhanced(self): pass"}
        real_conflict_infrastructure.create_real_uncommitted_changes(repo_path, changes)

        # Create conflict object
        conflict = SyncConflict(
            conflict_type=ConflictType.UNCOMMITTED_CHANGES,
            description="Test uncommitted changes",
            affected_files=["src/service.py"],
            suggested_actions=[ResolutionAction.STASH],
        )

        # Test real stash resolution
        resolver = ConflictResolver()
        result = resolver.resolve_conflict(conflict, repo_path, ResolutionAction.STASH)

        # Verify real stash operation
        assert result.success is True, f"Stash should succeed: {result.message}"
        assert "successfully stashed" in result.message.lower()
        assert result.requires_manual_intervention is False

        # Verify working directory is clean after stash
        git_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert (
            git_status.stdout.strip() == ""
        ), "Working directory should be clean after stash"

        # Verify stash entry exists
        git_stash_list = subprocess.run(
            ["git", "stash", "list"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert (
            "Auto-stash before sync" in git_stash_list.stdout
        ), "Stash entry should exist"

    def test_real_conflict_resolution_commit_changes(
        self, real_conflict_infrastructure
    ):
        """Test real conflict resolution by committing changes."""
        # Create repository with uncommitted changes
        content = {"src/model.py": "class Model: pass"}
        repo_path = real_conflict_infrastructure.create_real_git_repository(
            "commit-test", content
        )

        # Make uncommitted changes
        changes = {
            "src/model.py": "class Model:\n    def save(self): pass",
            "src/helper.py": "def helper_function(): return True",
        }
        real_conflict_infrastructure.create_real_uncommitted_changes(repo_path, changes)

        # Create conflict object
        conflict = SyncConflict(
            conflict_type=ConflictType.UNCOMMITTED_CHANGES,
            description="Test uncommitted changes",
            affected_files=["src/model.py", "src/helper.py"],
            suggested_actions=[ResolutionAction.COMMIT],
        )

        # Test real commit resolution
        resolver = ConflictResolver()
        result = resolver.resolve_conflict(conflict, repo_path, ResolutionAction.COMMIT)

        # Verify real commit operation
        assert result.success is True, f"Commit should succeed: {result.message}"
        assert "successfully committed" in result.message.lower()
        assert result.requires_manual_intervention is False

        # Verify working directory is clean after commit
        git_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert (
            git_status.stdout.strip() == ""
        ), "Working directory should be clean after commit"

        # Verify commit exists in history
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-n", "1"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert (
            "Auto-commit before sync" in git_log.stdout
        ), "Commit should exist in history"

    def test_real_conflict_resolution_manual_resolve_merge(
        self, real_conflict_infrastructure
    ):
        """Test real conflict resolution requiring manual intervention."""
        # Create repository with merge conflict
        content = {"src/config.py": "CONFIG = {'default': True}"}
        repo_path = real_conflict_infrastructure.create_real_git_repository(
            "manual-test", content
        )

        # Create real merge conflict
        real_conflict_infrastructure.create_real_merge_conflict(
            repo_path,
            "src/config.py",
            "CONFIG = {'default': True}",
            "CONFIG = {'default': True, 'feature': 'enabled'}",
            "CONFIG = {'default': True, 'main': 'active'}",
        )

        # Create conflict object
        conflict = SyncConflict(
            conflict_type=ConflictType.MERGE_CONFLICTS,
            description="Test merge conflicts",
            affected_files=["src/config.py"],
            suggested_actions=[ResolutionAction.MANUAL_RESOLVE],
        )

        # Test manual resolution requirement
        resolver = ConflictResolver()
        result = resolver.resolve_conflict(
            conflict, repo_path, ResolutionAction.MANUAL_RESOLVE
        )

        # Verify manual intervention is required
        assert result.success is False, "Manual resolution should not auto-succeed"
        assert result.requires_manual_intervention is True
        assert "Manual resolution required" in result.message
        assert "merge conflicts" in result.message.lower()

    def test_conflict_resolution_guidance_generation(
        self, real_conflict_infrastructure
    ):
        """Test generation of real conflict resolution guidance."""
        # Create conflict scenarios
        uncommitted_conflict = SyncConflict(
            conflict_type=ConflictType.UNCOMMITTED_CHANGES,
            description="Uncommitted changes detected",
            affected_files=["src/app.py", "config.json", "new_file.py"],
            suggested_actions=[
                ResolutionAction.STASH,
                ResolutionAction.COMMIT,
                ResolutionAction.ABORT,
            ],
        )

        merge_conflict = SyncConflict(
            conflict_type=ConflictType.MERGE_CONFLICTS,
            description="Merge conflicts in source files",
            affected_files=["src/service.py", "src/model.py"],
            suggested_actions=[ResolutionAction.MANUAL_RESOLVE],
        )

        # Test guidance generation
        resolver = ConflictResolver()

        # Test uncommitted changes guidance
        uncommitted_guidance = resolver.generate_resolution_guidance(
            uncommitted_conflict
        )
        assert "Uncommitted changes detected" in uncommitted_guidance
        assert "src/app.py" in uncommitted_guidance
        assert "config.json" in uncommitted_guidance
        assert "new_file.py" in uncommitted_guidance
        assert "Stash changes" in uncommitted_guidance
        assert "Commit changes" in uncommitted_guidance
        assert "Abort sync" in uncommitted_guidance

        # Test merge conflict guidance
        merge_guidance = resolver.generate_resolution_guidance(merge_conflict)
        assert "Merge conflicts" in merge_guidance
        assert "src/service.py" in merge_guidance
        assert "src/model.py" in merge_guidance
        assert "Manual resolution" in merge_guidance

    def test_no_conflicts_detected_clean_repository(self, real_conflict_infrastructure):
        """Test conflict detection returns empty for clean repository."""
        # Create clean repository
        content = {
            "src/clean.py": "def clean_function(): pass",
            "README.md": "# Clean Repository",
        }
        repo_path = real_conflict_infrastructure.create_real_git_repository(
            "clean-test", content
        )

        # Test conflict detection on clean repository
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(repo_path)

        # Verify no conflicts detected
        assert len(conflicts) == 0, "Clean repository should have no conflicts"

    def test_conflict_priority_merge_over_uncommitted(
        self, real_conflict_infrastructure
    ):
        """Test that merge conflicts take priority over uncommitted changes."""
        # Create repository
        content = {"src/priority.py": "class Priority: pass"}
        repo_path = real_conflict_infrastructure.create_real_git_repository(
            "priority-test", content
        )

        # Create merge conflict
        real_conflict_infrastructure.create_real_merge_conflict(
            repo_path,
            "src/priority.py",
            "class Priority: pass",
            "class Priority:\n    feature = True",
            "class Priority:\n    main = True",
        )

        # Add additional uncommitted changes
        changes = {"new_uncommitted.py": "# New uncommitted file"}
        real_conflict_infrastructure.create_real_uncommitted_changes(repo_path, changes)

        # Test conflict detection
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(repo_path)

        # Should detect merge conflict but not uncommitted changes due to priority
        assert len(conflicts) == 1, "Should detect only merge conflict due to priority"
        assert conflicts[0].conflict_type == ConflictType.MERGE_CONFLICTS
        assert "src/priority.py" in conflicts[0].affected_files

    def test_error_handling_invalid_repository(self, real_conflict_infrastructure):
        """Test error handling for invalid repository paths."""
        # Test with non-existent directory
        non_existent = real_conflict_infrastructure.temp_dir / "non-existent"

        detector = ConflictDetector()

        # Should handle error gracefully
        try:
            conflicts = detector.detect_conflicts(non_existent)
            # If it doesn't raise, should return empty list
            assert isinstance(conflicts, list)
        except Exception as e:
            # If it raises, should be a meaningful error
            assert "ConflictResolutionError" in str(type(e)) or "Failed" in str(e)

    def test_real_diverged_branch_detection(self, real_conflict_infrastructure):
        """Test detection of diverged branches in real repository."""
        # Create repository with remote setup
        content = {"src/diverged.py": "def initial(): pass"}
        repo_path = real_conflict_infrastructure.create_real_git_repository(
            "diverged-test", content
        )

        # Set up origin remote (simulate remote repository)
        origin_path = real_conflict_infrastructure.test_repos_dir / "diverged-origin"
        subprocess.run(
            ["git", "clone", "--bare", str(repo_path), str(origin_path)], check=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(origin_path)],
            cwd=repo_path,
            check=True,
        )

        # Push initial content
        subprocess.run(["git", "push", "origin", "main"], cwd=repo_path, check=True)

        # Create local commit
        local_file = repo_path / "local_change.py"
        local_file.write_text("# Local change")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Local change"], cwd=repo_path, check=True
        )

        # Simulate remote change by working in a separate clone
        temp_clone = real_conflict_infrastructure.test_repos_dir / "temp-clone"
        subprocess.run(["git", "clone", str(origin_path), str(temp_clone)], check=True)
        remote_file = temp_clone / "remote_change.py"
        remote_file.write_text("# Remote change")
        subprocess.run(["git", "add", "."], cwd=temp_clone, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Remote change"], cwd=temp_clone, check=True
        )
        subprocess.run(["git", "push", "origin", "main"], cwd=temp_clone, check=True)

        # Fetch remote changes
        subprocess.run(["git", "fetch", "origin"], cwd=repo_path, check=True)

        # Test diverged branch detection
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts(repo_path)

        # Should detect diverged branches
        diverged_conflicts = [
            c for c in conflicts if c.conflict_type == ConflictType.DIVERGED_BRANCH
        ]
        assert len(diverged_conflicts) == 1, "Should detect diverged branch conflict"
        assert (
            ResolutionAction.MANUAL_RESOLVE in diverged_conflicts[0].suggested_actions
        )
