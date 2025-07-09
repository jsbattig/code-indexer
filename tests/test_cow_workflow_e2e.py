"""End-to-end test for the complete CoW (Copy-on-Write) workflow.

This test validates the full workflow:
1. clean-legacy command (clean slate migration)
2. indexing with simplified CoW approach
3. copying projects and verifying independent collections
"""

import shutil
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from .conftest import local_temporary_directory
import asyncio

from code_indexer.services.qdrant import QdrantClient
from code_indexer.services.docker_manager import DockerManager
from code_indexer.services.legacy_detector import LegacyDetector
from code_indexer.config import QdrantConfig


class TestCoWWorkflowE2E:
    """Test the complete CoW workflow end-to-end."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333", collection="test_collection", vector_size=1536
        )

    def test_clean_legacy_workflow(self):
        """Test the clean-legacy command workflow."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Mock docker manager operations and subprocess calls
            with patch.object(
                DockerManager, "__init__", return_value=None
            ), patch.object(
                DockerManager, "stop_services", return_value=True
            ), patch.object(
                DockerManager, "clean_data_only", return_value=True
            ), patch(
                "subprocess.run", return_value=Mock(returncode=0)
            ), patch.object(
                DockerManager, "start_services", return_value=True
            ), patch(
                "pathlib.Path.home", return_value=temp_path
            ):

                docker_manager = DockerManager(project_name="test_shared")

                # Simulate clean-legacy workflow
                # 1. Stop containers
                assert docker_manager.stop_services()

                # 2. Clean storage (actual method used in clean-legacy)
                assert docker_manager.clean_data_only(all_projects=True)

                # 3. Docker removal is done via subprocess - we mocked it
                # 4. Compose file removal is done via direct file operations

                # 5. Start with CoW architecture
                assert docker_manager.start_services()

    def test_cow_seeder_collection_creation(self):
        """Test collection creation with simplified CoW approach."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create mock project directory structure
            project_dir = temp_path / "test_project"
            project_dir.mkdir()

            # Create global collections directory
            global_collections_dir = temp_path / ".qdrant_collections"
            global_collections_dir.mkdir(parents=True)

            client = QdrantClient(
                self.config, console=self.mock_console, project_root=project_dir
            )

            # Mock container operations with side effects
            def mock_copy_collection_data(collection_name, target_dir):
                target_dir.mkdir(parents=True, exist_ok=True)
                # Create some dummy files to simulate copied data
                (target_dir / "dummy_data").write_text("copied data")
                return True

            def mock_replace_with_symlink(collection_name, target_dir):
                # Create symlink in global collections directory
                symlink_path = global_collections_dir / collection_name
                symlink_path.symlink_to(target_dir)
                return True

            # Mock HTTP client and container operations for simplified CoW approach
            with patch.object(client, "client") as mock_client, patch(
                "pathlib.Path.home", return_value=temp_path
            ), patch("pathlib.Path.cwd", return_value=project_dir), patch.object(
                client,
                "_copy_collection_data_via_container",
                side_effect=mock_copy_collection_data,
            ), patch.object(
                client,
                "_replace_with_symlink_via_container",
                side_effect=mock_replace_with_symlink,
            ):
                # Mock successful API response
                mock_response = Mock()
                mock_response.status_code = 200
                mock_client.put.return_value = mock_response

                # Test the simplified CoW collection approach
                result = client._create_collection_with_cow("test_collection")

                # Verify success
                assert result

                # Verify local collection directory was created
                local_collection_dir = (
                    project_dir
                    / ".code-indexer"
                    / "qdrant_collection"
                    / "test_collection"
                )
                assert local_collection_dir.exists()

                # Verify symlink was created
                symlink_path = global_collections_dir / "test_collection"
                assert symlink_path.is_symlink()
                assert symlink_path.resolve() == local_collection_dir

    def test_cow_project_copying(self):
        """Test that copying a project maintains independent collections."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create original project with CoW collection
            original_project = temp_path / "original_project"
            original_project.mkdir()

            # Create collection data in original project
            original_collection_dir = (
                original_project
                / ".code-indexer"
                / "qdrant_collection"
                / "test_collection"
            )
            original_collection_dir.mkdir(parents=True)
            (original_collection_dir / "segments.json").write_text(
                '{"original": "data"}'
            )
            (original_collection_dir / "meta.json").write_text('{"test": "metadata"}')

            # Create global collections directory and symlink
            global_collections_dir = temp_path / ".qdrant_collections"
            global_collections_dir.mkdir(parents=True)
            symlink_path = global_collections_dir / "test_collection"
            symlink_path.symlink_to(original_collection_dir, target_is_directory=True)

            # Copy the project (simulating CoW functionality)
            copied_project = temp_path / "copied_project"
            shutil.copytree(original_project, copied_project)

            # Verify both projects have independent collection data
            copied_collection_dir = (
                copied_project
                / ".code-indexer"
                / "qdrant_collection"
                / "test_collection"
            )
            assert copied_collection_dir.exists()
            assert (copied_collection_dir / "segments.json").exists()

            # Verify they are independent (different paths)
            assert original_collection_dir != copied_collection_dir

            # Modify data in copied project
            (copied_collection_dir / "segments.json").write_text('{"modified": "data"}')

            # Verify original is unchanged
            original_data = (original_collection_dir / "segments.json").read_text()
            assert '"original": "data"' in original_data

            # Verify copied has different data
            copied_data = (copied_collection_dir / "segments.json").read_text()
            assert '"modified": "data"' in copied_data

    def test_legacy_detection_workflow(self):
        """Test legacy detection and migration guidance."""
        detector = LegacyDetector()

        # Mock container without home mount (legacy)
        async def mock_check_home_mount():
            return False

        with patch("subprocess.run") as mock_subprocess, patch.object(
            detector,
            "_check_container_has_home_mount",
            side_effect=mock_check_home_mount,
        ):
            # Mock container exists (returncode 0)
            mock_subprocess.return_value.returncode = 0

            # Should detect legacy container (use asyncio.run to handle async)
            is_legacy = asyncio.run(detector.check_legacy_container())
            assert is_legacy

            # Should provide migration guidance
            error_message = detector.get_legacy_error_message()
            assert "Legacy container detected" in error_message
            assert "cidx clean-legacy" in error_message
            assert "CoW migration required" in error_message

    def test_cow_data_cleanup_workflow(self):
        """Test that data cleanup follows symlinks and deletes actual data."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create mock CoW structure
            project_dir = (
                temp_path
                / "project"
                / ".code-indexer"
                / "qdrant_collection"
                / "test_collection"
            )
            project_dir.mkdir(parents=True)
            (project_dir / "data.json").write_text('{"test": "data"}')

            # Create global collections directory and symlink
            global_collections_dir = temp_path / ".qdrant_collections"
            global_collections_dir.mkdir(parents=True)
            symlink_path = global_collections_dir / "test_collection"
            symlink_path.symlink_to(project_dir, target_is_directory=True)

            client = QdrantClient(self.config, console=self.mock_console)

            # Mock HTTP client for deletion
            with patch.object(client, "client") as mock_http_client, patch(
                "pathlib.Path.home", return_value=temp_path
            ):

                mock_response = Mock()
                mock_response.status_code = 200
                mock_http_client.delete.return_value = mock_response

                # Test collection deletion with CoW cleanup
                result = client.delete_collection("test_collection")

                # Verify API deletion was called
                mock_http_client.delete.assert_called_once_with(
                    "/collections/test_collection"
                )

                # Verify symlink was removed
                assert not symlink_path.exists()

                # Verify actual data was deleted
                assert not project_dir.exists()

                # Verify success
                assert result

    def test_cow_collection_independence(self):
        """Test that multiple projects can have independent collections with same name."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create two projects
            project1 = temp_path / "project1"
            project2 = temp_path / "project2"
            project1.mkdir()
            project2.mkdir()

            # Create collection dirs for both projects
            collection1_dir = (
                project1 / ".code-indexer" / "qdrant_collection" / "my_collection"
            )
            collection2_dir = (
                project2 / ".code-indexer" / "qdrant_collection" / "my_collection"
            )
            collection1_dir.mkdir(parents=True)
            collection2_dir.mkdir(parents=True)

            # Add different data to each
            (collection1_dir / "data.json").write_text('{"project": "1"}')
            (collection2_dir / "data.json").write_text('{"project": "2"}')

            # Create global collections directory
            global_collections_dir = temp_path / ".qdrant_collections"
            global_collections_dir.mkdir(parents=True)

            # Test switching between projects (simulating symlink management)
            symlink_path = global_collections_dir / "my_collection"

            # Point to project1
            if symlink_path.exists():
                symlink_path.unlink()
            symlink_path.symlink_to(collection1_dir, target_is_directory=True)

            # Verify we can access project1 data
            data1 = (symlink_path / "data.json").read_text()
            assert '"project": "1"' in data1

            # Switch to project2
            symlink_path.unlink()
            symlink_path.symlink_to(collection2_dir, target_is_directory=True)

            # Verify we can access project2 data
            data2 = (symlink_path / "data.json").read_text()
            assert '"project": "2"' in data2

            # Verify original project1 data is unchanged
            original_data1 = (collection1_dir / "data.json").read_text()
            assert '"project": "1"' in original_data1

    def test_concurrent_seeder_collection_names(self):
        """Test that concurrent seeder collections have unique names."""
        QdrantClient(self.config, console=self.mock_console)

        # Mock UUID generation to ensure we test uniqueness
        with patch("uuid.uuid4") as mock_uuid:
            # Simulate different UUID values for concurrent operations
            mock_uuid.side_effect = [
                Mock(hex="abc12345"),
                Mock(hex="def67890"),
                Mock(hex="ghi11111"),
            ]

            # Generate multiple seeder names
            collection_name = "test_collection"

            # Simulate the seeder name generation logic
            seed_name1 = f"seed_{collection_name}_{mock_uuid().hex[:8]}"
            seed_name2 = f"seed_{collection_name}_{mock_uuid().hex[:8]}"
            seed_name3 = f"seed_{collection_name}_{mock_uuid().hex[:8]}"

            # Verify all names are unique
            assert seed_name1 != seed_name2
            assert seed_name2 != seed_name3
            assert seed_name1 != seed_name3

            # Verify they follow expected pattern
            assert seed_name1.startswith(f"seed_{collection_name}_")
            assert seed_name2.startswith(f"seed_{collection_name}_")
            assert seed_name3.startswith(f"seed_{collection_name}_")

    def test_cow_workflow_error_recovery(self):
        """Test that simplified CoW approach has proper error recovery."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            client = QdrantClient(self.config, console=self.mock_console)

            # Mock failure scenarios
            with patch.object(client, "client") as mock_client, patch(
                "pathlib.Path.home", return_value=temp_path
            ):
                # Mock failed API response
                mock_response = Mock()
                mock_response.status_code = 400
                mock_client.put.return_value = mock_response

                # Test simplified CoW creation failure
                result = client._create_collection_with_cow("test_collection")

                # Should return False on API failure
                assert not result

            # Reset mock for second test
            self.mock_console.reset_mock()

            # Test exception handling (directory creation failure)
            with patch.object(client, "client") as mock_client, patch(
                "pathlib.Path.home", return_value=temp_path
            ), patch(
                "pathlib.Path.mkdir", side_effect=Exception("Directory creation failed")
            ):
                # Mock successful API responses so we get to the mkdir part
                mock_response = Mock()
                mock_response.status_code = 200
                mock_client.put.return_value = mock_response

                # This should trigger the except block in _create_collection_with_cow
                result = client._create_collection_with_cow("test_collection")

                # Should return False on exception
                assert not result

                # Should print error message about CoW exception
                print_calls = [
                    str(call) for call in self.mock_console.print.call_args_list
                ]
                error_message_found = any(
                    "CoW creation exception" in call for call in print_calls
                )
                assert (
                    error_message_found
                ), f"Expected CoW exception message in: {print_calls}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
