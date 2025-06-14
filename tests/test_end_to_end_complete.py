#!/usr/bin/env python3
"""
Comprehensive end-to-end tests that exercise ALL code paths including:
- Single project indexing and search
- Multi-project indexing and search  
- Clean functionality and trace removal
- Container lifecycle management
"""

import os
import subprocess
import tempfile
import time
import shutil
from pathlib import Path
import pytest
import json
from code_indexer.services.docker_manager import DockerManager


class TestEndToEndComplete:
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup test environment and ensure cleanup"""
        self.docker_manager = DockerManager()
        self.test_containers = set()
        self.test_networks = set()
        self.original_cwd = os.getcwd()
        
        yield
        
        # Cleanup containers and networks using CLI
        compose_cmd = self.docker_manager.get_compose_command()
        for project_dir in ["test_project_1", "test_project_2"]:
            project_path = Path(__file__).parent / "projects" / project_dir
            if (project_path / "docker-compose.yml").exists():
                try:
                    subprocess.run(
                        compose_cmd + ["down", "-v"],
                        cwd=project_path,
                        capture_output=True,
                        timeout=30
                    )
                except Exception:
                    pass
                
        os.chdir(self.original_cwd)

    def run_cli_command(self, args, cwd=None, timeout=120):
        """Run code-indexer CLI command and return result"""
        cmd = ["python", "-m", "code_indexer.cli"] + args
        result = subprocess.run(
            cmd,
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result

    def wait_for_container_ready(self, container_name, max_wait=60):
        """Wait for container to be ready and healthy using CLI"""
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                # Check if container exists and is running
                cmd = self.docker_manager.get_compose_command()[0]
                result = subprocess.run(
                    [cmd, "ps", "-q", "-f", f"name={container_name}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Container exists, try health check
                    health_result = subprocess.run(
                        [cmd, "exec", container_name, "curl", "-f", "http://localhost:11434/api/version"],
                        capture_output=True,
                        timeout=5
                    )
                    if health_result.returncode == 0:
                        return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def test_single_project_full_cycle(self):
        """Test complete single project cycle: index -> search -> clean"""
        # Use test_project_1 (calculator)
        project_path = Path(__file__).parent / "projects" / "test_project_1"
        os.chdir(project_path)
        
        try:
            # 1. Start containers and index  
            result = self.run_cli_command(["index"])
            assert result.returncode == 0, f"Index failed: {result.stderr}"
            
            self.test_containers.add("test-project-1-ollama-1")
            self.test_containers.add("test-project-1-qdrant-1")
            self.test_networks.add("test-project-1_default")
            
            # Wait for services to be ready
            assert self.wait_for_container_ready("test-project-1-ollama-1"), "Ollama container not ready"
            
            # 2. Test search functionality with specific queries for calculator code
            search_queries = [
                "add function",
                "calculator implementation", 
                "factorial function",
                "square root calculation",
                "prime number check"
            ]
            
            for query in search_queries:
                result = self.run_cli_command(["search", query])
                assert result.returncode == 0, f"Search '{query}' failed: {result.stderr}"
                assert len(result.stdout.strip()) > 0, f"Search '{query}' returned no results"
                
                # Verify results contain relevant code files
                output = result.stdout.lower()
                assert any(file in output for file in ["main.py", "utils.py"]), \
                    f"Search '{query}' didn't find expected files: {result.stdout}"
            
            # 3. Test list functionality
            result = self.run_cli_command(["list"])
            assert result.returncode == 0, f"List failed: {result.stderr}"
            assert "main.py" in result.stdout
            assert "utils.py" in result.stdout
            
            # 4. Test status
            result = self.run_cli_command(["status"])
            assert result.returncode == 0, f"Status failed: {result.stderr}"
            
            # 5. Clean and verify complete removal
            result = self.run_cli_command(["clean"])
            assert result.returncode == 0, f"Clean failed: {result.stderr}"
            
            # Verify no traces remain
            assert not (project_path / ".code-indexer").exists(), "Config directory not cleaned"
            assert not (project_path / "data").exists(), "Data directory not cleaned"  
            assert not (project_path / "docker-compose.yml").exists(), "Docker compose not cleaned"
            
            # Verify containers are stopped and removed
            time.sleep(5)  # Give containers time to stop
            
            # Check that containers no longer exist
            cmd = self.docker_manager.get_compose_command()[0]
            for container_name in ["test-project-1-ollama-1", "test-project-1-qdrant-1"]:
                result = subprocess.run(
                    [cmd, "ps", "-q", "-f", f"name={container_name}"],
                    capture_output=True,
                    text=True
                )
                assert not result.stdout.strip(), f"Container {container_name} still exists"
                    
        finally:
            # Ensure cleanup even if test fails
            self.run_cli_command(["clean"])

    def test_multi_project_isolation_and_search(self):
        """Test multi-project functionality with proper isolation"""
        project1_path = Path(__file__).parent / "projects" / "test_project_1"
        project2_path = Path(__file__).parent / "projects" / "test_project_2"
        
        try:
            # Index both projects
            os.chdir(project1_path)
            result1 = self.run_cli_command(["index"])
            assert result1.returncode == 0, f"Project 1 index failed: {result1.stderr}"
            
            self.test_containers.update(["test-project-1-ollama-1", "test-project-1-qdrant-1"])
            self.test_networks.add("test-project-1_default")
            
            os.chdir(project2_path)  
            result2 = self.run_cli_command(["index"])
            assert result2.returncode == 0, f"Project 2 index failed: {result2.stderr}"
            
            self.test_containers.update(["test-project-2-ollama-1", "test-project-2-qdrant-1"])
            self.test_networks.add("test-project-2_default")
            
            # Wait for both to be ready
            assert self.wait_for_container_ready("test-project-1-ollama-1"), "Project 1 not ready"
            assert self.wait_for_container_ready("test-project-2-ollama-1"), "Project 2 not ready"
            
            # Test project 1 searches (calculator-specific)
            os.chdir(project1_path)
            calc_queries = ["add function", "factorial", "calculator"]
            for query in calc_queries:
                result = self.run_cli_command(["search", query])
                assert result.returncode == 0, f"Project 1 search '{query}' failed: {result.stderr}"
                output = result.stdout.lower()
                assert "main.py" in output or "utils.py" in output, \
                    f"Project 1 search '{query}' didn't find calculator files"
                # Should NOT find web server files
                assert "web_server.py" not in output, \
                    f"Project 1 search '{query}' incorrectly found web server files"
            
            # Test project 2 searches (web server-specific)  
            os.chdir(project2_path)
            web_queries = ["web server", "route function", "authentication"]
            for query in web_queries:
                result = self.run_cli_command(["search", query])
                assert result.returncode == 0, f"Project 2 search '{query}' failed: {result.stderr}"
                output = result.stdout.lower()
                assert "web_server.py" in output or "auth.py" in output, \
                    f"Project 2 search '{query}' didn't find web server files"
                # Should NOT find calculator files
                assert "main.py" not in output or "calculator" not in output, \
                    f"Project 2 search '{query}' incorrectly found calculator files"
            
            # Test that each project only lists its own files
            os.chdir(project1_path)
            result = self.run_cli_command(["list"])
            assert "main.py" in result.stdout
            assert "utils.py" in result.stdout
            assert "web_server.py" not in result.stdout
            
            os.chdir(project2_path)
            result = self.run_cli_command(["list"])
            assert "web_server.py" in result.stdout
            assert "auth.py" in result.stdout  
            assert "main.py" not in result.stdout or "calculator" not in result.stdout
            
            # Clean both projects
            os.chdir(project1_path)
            result = self.run_cli_command(["clean"])
            assert result.returncode == 0, f"Project 1 clean failed: {result.stderr}"
            
            os.chdir(project2_path)
            result = self.run_cli_command(["clean"])
            assert result.returncode == 0, f"Project 2 clean failed: {result.stderr}"
            
            # Verify complete cleanup
            time.sleep(5)
            
            for project_path in [project1_path, project2_path]:
                assert not (project_path / ".code-indexer").exists()
                assert not (project_path / "data").exists()
                assert not (project_path / "docker-compose.yml").exists()
                
            # Verify all containers removed
            cmd = self.docker_manager.get_compose_command()[0]
            all_containers = ["test-project-1-ollama-1", "test-project-1-qdrant-1", 
                            "test-project-2-ollama-1", "test-project-2-qdrant-1"]
            for container_name in all_containers:
                result = subprocess.run(
                    [cmd, "ps", "-q", "-f", f"name={container_name}"],
                    capture_output=True,
                    text=True
                )
                assert not result.stdout.strip(), f"Container {container_name} still exists"
                    
        finally:
            # Cleanup both projects
            for project_path in [project1_path, project2_path]:
                os.chdir(project_path)
                self.run_cli_command(["clean"])

    def test_error_conditions_and_recovery(self):
        """Test error handling and recovery scenarios"""
        project_path = Path(__file__).parent / "projects" / "test_project_1"
        os.chdir(project_path)
        
        try:
            # Test search without indexing first
            result = self.run_cli_command(["search", "test query"])
            assert result.returncode != 0, "Search should fail without indexing"
            
            # Test list without indexing first  
            result = self.run_cli_command(["list"])
            assert result.returncode != 0, "List should fail without indexing"
            
            # Test clean without containers (should not error)
            result = self.run_cli_command(["clean"])
            assert result.returncode == 0, "Clean should succeed even without containers"
            
            # Test index, then clean, then operations should fail
            result = self.run_cli_command(["index", "--path", ".", "--wait"])
            assert result.returncode == 0
            
            self.test_containers.update(["test-project-1-ollama-1", "test-project-1-qdrant-1"])
            
            result = self.run_cli_command(["clean"])
            assert result.returncode == 0
            
            # Now search should fail again
            result = self.run_cli_command(["search", "test query"])
            assert result.returncode != 0, "Search should fail after clean"
            
        finally:
            self.run_cli_command(["clean"])

    def test_concurrent_operations(self):
        """Test that concurrent operations on different projects work correctly"""
        project1_path = Path(__file__).parent / "projects" / "test_project_1"
        project2_path = Path(__file__).parent / "projects" / "test_project_2"
        
        try:
            # Start indexing both projects concurrently
            os.chdir(project1_path)
            proc1 = subprocess.Popen(
                ["python", "-m", "code_indexer.cli", "index"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            os.chdir(project2_path)
            proc2 = subprocess.Popen(
                ["python", "-m", "code_indexer.cli", "index"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for both to complete
            out1, err1 = proc1.communicate(timeout=180)
            out2, err2 = proc2.communicate(timeout=180)
            
            assert proc1.returncode == 0, f"Concurrent index 1 failed: {err1}"
            assert proc2.returncode == 0, f"Concurrent index 2 failed: {err2}"
            
            self.test_containers.update([
                "test-project-1-ollama-1", "test-project-1-qdrant-1",
                "test-project-2-ollama-1", "test-project-2-qdrant-1"
            ])
            
            # Verify both work independently
            os.chdir(project1_path)
            result = self.run_cli_command(["search", "calculator"])
            assert result.returncode == 0
            assert "main.py" in result.stdout.lower()
            
            os.chdir(project2_path)
            result = self.run_cli_command(["search", "server"])
            assert result.returncode == 0
            assert "web_server.py" in result.stdout.lower()
            
        finally:
            for project_path in [project1_path, project2_path]:
                os.chdir(project_path)
                self.run_cli_command(["clean"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])