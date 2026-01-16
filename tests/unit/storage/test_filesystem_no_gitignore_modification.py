"""
Story #726: Tests ensuring CIDX does not modify .gitignore or files outside .code-indexer/.

These tests verify that:
1. FilesystemVectorStore.create_collection() does NOT modify .gitignore
2. No files outside the .code-indexer/ directory are ever created/modified
3. Golden repository refreshes work even with modified files
"""

import subprocess
from pathlib import Path


class TestFilesystemNoGitignoreModification:
    """Test that FilesystemVectorStore does not modify .gitignore."""

    def test_create_collection_does_not_modify_gitignore(self, tmp_path):
        """
        GIVEN a git repository with a .gitignore file
        WHEN create_collection() is called
        THEN .gitignore should NOT be modified

        AC: Collection creation does NOT modify .gitignore or any file outside .code-indexer/
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        # Create initial .gitignore with some content
        gitignore_path = tmp_path / ".gitignore"
        original_content = "*.pyc\n__pycache__/\n"
        gitignore_path.write_text(original_content)

        # Commit the .gitignore so it's tracked
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Set up .code-indexer directory as the base path (simulating real usage)
        code_indexer_path = tmp_path / ".code-indexer" / "index"
        code_indexer_path.mkdir(parents=True)

        # Create FilesystemVectorStore
        store = FilesystemVectorStore(
            base_path=code_indexer_path, project_root=tmp_path
        )

        # Create collection - this should NOT modify .gitignore
        store.create_collection("test_collection", vector_size=1536)

        # Verify .gitignore was NOT modified
        final_content = gitignore_path.read_text()
        assert final_content == original_content, (
            f".gitignore was modified! "
            f"Original: {repr(original_content)}, "
            f"Final: {repr(final_content)}"
        )

        # Verify git status shows no MODIFIED tracked files
        # Note: Untracked files in .code-indexer/ are acceptable (that's where CIDX stores its data)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        # Filter out untracked files (??) - we only care about modified tracked files (M)
        modified_tracked_files = [
            line for line in result.stdout.strip().split("\n")
            if line.strip() and not line.startswith("??")
        ]
        assert len(modified_tracked_files) == 0, (
            f"Tracked files were modified: {modified_tracked_files}"
        )

    def test_create_collection_does_not_modify_gitignore_when_no_gitignore_exists(
        self, tmp_path
    ):
        """
        GIVEN a git repository WITHOUT a .gitignore file
        WHEN create_collection() is called
        THEN .gitignore should NOT be created

        AC: Collection creation does NOT modify .gitignore or any file outside .code-indexer/
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo without .gitignore
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        # Create a dummy file and commit so we have a valid repo
        dummy_file = tmp_path / "README.md"
        dummy_file.write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Verify .gitignore does NOT exist
        gitignore_path = tmp_path / ".gitignore"
        assert not gitignore_path.exists(), ".gitignore should not exist initially"

        # Set up .code-indexer directory as the base path
        code_indexer_path = tmp_path / ".code-indexer" / "index"
        code_indexer_path.mkdir(parents=True)

        # Create FilesystemVectorStore
        store = FilesystemVectorStore(
            base_path=code_indexer_path, project_root=tmp_path
        )

        # Create collection - this should NOT create .gitignore
        store.create_collection("test_collection", vector_size=1536)

        # Verify .gitignore was NOT created
        assert not gitignore_path.exists(), (
            ".gitignore was created when it should not have been!"
        )

    def test_create_collection_does_not_create_files_outside_base_path(self, tmp_path):
        """
        GIVEN a project directory
        WHEN create_collection() is called
        THEN all files should be created ONLY within the base_path (.code-indexer/)

        AC: Collection creation does NOT modify any file outside .code-indexer/
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Set up .code-indexer directory as the base path
        code_indexer_path = tmp_path / ".code-indexer" / "index"
        code_indexer_path.mkdir(parents=True)

        # Get initial state of files outside .code-indexer
        def get_files_outside_code_indexer(root: Path) -> set:
            """Get all files outside .code-indexer/ directory."""
            files = set()
            for item in root.rglob("*"):
                if item.is_file() and ".code-indexer" not in str(item):
                    files.add(item.relative_to(root))
            return files

        initial_files = get_files_outside_code_indexer(tmp_path)

        # Create FilesystemVectorStore
        store = FilesystemVectorStore(
            base_path=code_indexer_path, project_root=tmp_path
        )

        # Create collection
        store.create_collection("test_collection", vector_size=1536)

        # Get files after collection creation
        final_files = get_files_outside_code_indexer(tmp_path)

        # Verify no new files were created outside .code-indexer/
        new_files = final_files - initial_files
        assert len(new_files) == 0, (
            f"Files were created outside .code-indexer/: {new_files}"
        )

    def test_multiple_collections_do_not_modify_gitignore(self, tmp_path):
        """
        GIVEN a git repository with .gitignore
        WHEN multiple collections are created
        THEN .gitignore should remain unchanged

        AC: Collection creation does NOT modify .gitignore
        """
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True
        )

        # Create initial .gitignore
        gitignore_path = tmp_path / ".gitignore"
        original_content = "*.pyc\n__pycache__/\n.env\n"
        gitignore_path.write_text(original_content)

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Set up .code-indexer directory
        code_indexer_path = tmp_path / ".code-indexer" / "index"
        code_indexer_path.mkdir(parents=True)

        store = FilesystemVectorStore(
            base_path=code_indexer_path, project_root=tmp_path
        )

        # Create multiple collections
        for model_name in ["voyage-3", "voyage-3-large", "custom-model"]:
            store.create_collection(model_name, vector_size=1536)

        # Verify .gitignore unchanged
        final_content = gitignore_path.read_text()
        assert final_content == original_content, (
            ".gitignore was modified after creating multiple collections!"
        )
