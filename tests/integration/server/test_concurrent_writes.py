"""
Integration tests for concurrent writes - verifying race condition fix.

Story #702: Migrate Central JSON Files to SQLite

These tests verify that the SQLite migration eliminates the race condition
where concurrent GlobalRegistry instances would overwrite each other's changes.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest


class TestConcurrentGlobalRepoWrites:
    """
    Tests for concurrent GlobalRegistry operations.

    The original race condition occurred when batch auto-discovery registered
    multiple repos concurrently - the last instance to save would overwrite
    changes from other instances.
    """

    def test_concurrent_repo_registration_no_data_loss(self, tmp_path: Path) -> None:
        """
        Given an initialized SQLite database
        When 20 concurrent repo registrations occur from different threads
        Then all repos are persisted without data loss.

        This test reproduces the original GlobalRegistry race condition
        and verifies it is fixed with SQLite backend.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        num_repos = 20
        errors = []

        def register_repo(n: int) -> None:
            """Register a repo from a separate thread."""
            try:
                # Each thread creates its own backend instance
                # This simulates multiple GlobalRegistry instances
                backend = GlobalReposSqliteBackend(str(db_path))
                backend.register_repo(
                    alias_name=f"repo-{n}-global",
                    repo_name=f"repo-{n}",
                    repo_url=f"https://github.com/test/repo-{n}.git",
                    index_path=f"/path/to/repo-{n}",
                    enable_temporal=False,
                    temporal_options=None,
                )
                backend.close()
            except Exception as e:
                errors.append((n, str(e)))

        # Run registrations concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(register_repo, i) for i in range(num_repos)]
            for f in as_completed(futures):
                f.result()

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all repos were registered
        backend = GlobalReposSqliteBackend(str(db_path))
        repos = backend.list_repos()
        backend.close()

        assert len(repos) == num_repos, (
            f"Expected {num_repos} repos, got {len(repos)}. "
            f"Missing: {set(f'repo-{i}-global' for i in range(num_repos)) - set(repos.keys())}"
        )

    def test_concurrent_read_write_operations(self, tmp_path: Path) -> None:
        """
        Given an initialized database with some repos
        When concurrent reads and writes happen
        Then reads return consistent data and writes succeed.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Pre-populate with some repos
        backend = GlobalReposSqliteBackend(str(db_path))
        for i in range(5):
            backend.register_repo(
                alias_name=f"initial-{i}-global",
                repo_name=f"initial-{i}",
                repo_url=None,
                index_path=f"/path/{i}",
                enable_temporal=False,
                temporal_options=None,
            )
        backend.close()

        read_results = []
        write_errors = []

        def read_operation(n: int) -> None:
            """Read repos from a separate thread."""
            backend = GlobalReposSqliteBackend(str(db_path))
            repos = backend.list_repos()
            read_results.append(len(repos))
            backend.close()

        def write_operation(n: int) -> None:
            """Write a new repo from a separate thread."""
            try:
                backend = GlobalReposSqliteBackend(str(db_path))
                backend.register_repo(
                    alias_name=f"new-{n}-global",
                    repo_name=f"new-{n}",
                    repo_url=None,
                    index_path=f"/path/new/{n}",
                    enable_temporal=False,
                    temporal_options=None,
                )
                backend.close()
            except Exception as e:
                write_errors.append((n, str(e)))

        # Run mixed read/write operations concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(10):
                futures.append(executor.submit(read_operation, i))
                futures.append(executor.submit(write_operation, i))

            for f in as_completed(futures):
                f.result()

        # Verify no write errors
        assert len(write_errors) == 0, f"Write errors: {write_errors}"

        # Verify final state has all repos
        backend = GlobalReposSqliteBackend(str(db_path))
        final_repos = backend.list_repos()
        backend.close()

        # 5 initial + 10 new = 15 total
        assert len(final_repos) == 15


class TestConcurrentUserWrites:
    """Tests for concurrent user operations with cascade behavior."""

    def test_concurrent_user_creation(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When multiple users are created concurrently
        Then all users are persisted without conflicts.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        num_users = 10
        errors = []

        def create_user(n: int) -> None:
            try:
                backend = UsersSqliteBackend(str(db_path))
                backend.create_user(
                    username=f"user{n}",
                    password_hash=f"hash{n}",
                    role="user",
                    email=f"user{n}@example.com",
                )
                backend.close()
            except Exception as e:
                errors.append((n, str(e)))

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_user, i) for i in range(num_users)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"

        # Verify all users created
        backend = UsersSqliteBackend(str(db_path))
        for i in range(num_users):
            user = backend.get_user(f"user{i}")
            assert user is not None, f"User user{i} not found"
        backend.close()
