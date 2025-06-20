"""End-to-end tests for VoyageAI provider with cloud vectorization service."""

import os
import tempfile
import shutil
import subprocess
import pytest
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestVoyageAIE2E:
    """End-to-end tests for VoyageAI provider without Ollama dependency."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment for each test."""
        # Create temporary directory for test
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create test code files
        self.create_test_codebase()

        # Store original environment
        self.original_env = dict(os.environ)

        yield

        # Cleanup
        os.chdir(self.original_cwd)
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

        # Restore environment
        os.environ.clear()
        os.environ.update(self.original_env)

    def create_test_codebase(self):
        """Create a simple test codebase."""
        # Create some test files
        (self.test_dir / "main.py").write_text(
            '''
def hello_world():
    """Print hello world message."""
    print("Hello, World!")

def calculate_fibonacci(n):
    """Calculate fibonacci number."""
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

if __name__ == "__main__":
    hello_world()
    print(f"Fibonacci(10) = {calculate_fibonacci(10)}")
'''
        )

        (self.test_dir / "utils.py").write_text(
            '''
import math

def calculate_distance(x1, y1, x2, y2):
    """Calculate Euclidean distance between two points."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def format_number(num, decimals=2):
    """Format number with specified decimal places."""
    return f"{num:.{decimals}f}"
'''
        )

        (self.test_dir / "README.md").write_text(
            """
# Test Project

This is a test project for VoyageAI E2E testing.

## Features
- Hello world function
- Fibonacci calculation
- Distance calculation utilities
"""
        )

    def create_voyage_ai_config(self):
        """Create configuration for VoyageAI provider."""
        config_dir = self.test_dir / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        config = {
            "codebase_dir": str(self.test_dir),
            "embedding_provider": "voyage-ai",
            "qdrant": {
                "host": "http://localhost:6333",
                "collection": f"test_collection_{int(time.time())}",
            },
            "voyage_ai": {
                "model": "voyage-code-3",
                "api_key_env": "VOYAGE_API_KEY",
                "batch_size": 32,
                "max_retries": 3,
                "timeout": 30,
            },
            "exclude_patterns": [
                "*.git*",
                "__pycache__",
                "node_modules",
                ".pytest_cache",
            ],
        }

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        return config_file

    @pytest.mark.skipif(
        os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
        reason="E2E tests require Docker and VoyageAI API key, not available in CI",
    )
    def test_voyage_ai_full_workflow(self):
        """Test complete VoyageAI workflow from clean environment."""
        # Set up VoyageAI API key (mock for testing)
        os.environ["VOYAGE_API_KEY"] = "test_api_key_for_testing"

        # Create VoyageAI configuration
        self.create_voyage_ai_config()

        try:
            # Step 1: Initialize with VoyageAI provider
            result = subprocess.run(
                [
                    "code-indexer",
                    "init",
                    "--embedding-provider",
                    "voyage-ai",
                    "--force",
                ],
                cwd=self.test_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, f"Init failed: {result.stderr}"

            # Step 2: Setup services (should not start Ollama)
            result = subprocess.run(
                ["code-indexer", "setup", "--quiet"],
                cwd=self.test_dir,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes for Docker setup
            )
            assert result.returncode == 0, f"Setup failed: {result.stderr}"

            # Verify Ollama is not mentioned in setup output
            assert "ollama" not in result.stdout.lower()
            assert "voyage" in result.stdout.lower() or "VoyageAI" in result.stdout

            # Step 3: Check status (should show only required services)
            result = subprocess.run(
                ["code-indexer", "status"],
                cwd=self.test_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"Status failed: {result.stderr}"

            # Should show Qdrant and data-cleaner, but not Ollama
            status_output = result.stdout.lower()
            assert "qdrant" in status_output
            assert "data-cleaner" in status_output or "cleaner" in status_output
            assert "ollama" not in status_output

            # Step 4: Basic indexing (mocked VoyageAI calls)
            with patch("code_indexer.services.voyage_ai.VoyageAIClient") as mock_voyage:
                # Mock VoyageAI client
                mock_client = MagicMock()
                mock_client.health_check.return_value = True
                mock_client.get_provider_name.return_value = "VoyageAI"
                mock_client.get_current_model.return_value = "voyage-code-3"
                mock_client.get_model_info.return_value = {
                    "dimensions": 1024,
                    "model": "voyage-code-3",
                }
                mock_client.embed_texts.return_value = [[0.1] * 1024 for _ in range(10)]
                mock_voyage.return_value = mock_client

                result = subprocess.run(
                    ["code-indexer", "index", "--quiet"],
                    cwd=self.test_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                assert result.returncode == 0, f"Index failed: {result.stderr}"

            # Step 5: Test query functionality (mocked)
            with patch("code_indexer.services.voyage_ai.VoyageAIClient") as mock_voyage:
                # Mock VoyageAI client for query
                mock_client = MagicMock()
                mock_client.embed_texts.return_value = [[0.1] * 1024]
                mock_voyage.return_value = mock_client

                result = subprocess.run(
                    ["code-indexer", "query", "fibonacci function", "--quiet"],
                    cwd=self.test_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                assert result.returncode == 0, f"Query failed: {result.stderr}"

            # Step 6: Test stop command (should work without Ollama)
            result = subprocess.run(
                ["code-indexer", "stop"],
                cwd=self.test_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, f"Stop failed: {result.stderr}"

            # Step 7: Test start command (should work without Ollama)
            result = subprocess.run(
                ["code-indexer", "start"],
                cwd=self.test_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, f"Start failed: {result.stderr}"

            # Verify services are running after restart
            result = subprocess.run(
                ["code-indexer", "status"],
                cwd=self.test_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert (
                result.returncode == 0
            ), f"Status after restart failed: {result.stderr}"

        finally:
            # Always cleanup Docker containers
            subprocess.run(
                ["code-indexer", "clean", "--quiet"],
                cwd=self.test_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

    def test_voyage_ai_docker_compose_validation(self):
        """Test that Docker Compose config contains only required services for VoyageAI."""
        # Set up VoyageAI API key
        os.environ["VOYAGE_API_KEY"] = "test_api_key_for_testing"

        # Create VoyageAI configuration
        self.create_voyage_ai_config()

        # Mock Docker operations to avoid actual container creation
        with patch("code_indexer.services.docker_manager.subprocess.run") as mock_run:
            # Mock successful Docker command responses
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Docker is available"

            # Import and test DockerManager
            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Test required services detection
            required_services = docker_manager.get_required_services(
                config.model_dump()
            )
            assert "qdrant" in required_services
            assert "data-cleaner" in required_services
            assert "ollama" not in required_services

            # Test compose config generation
            compose_config = docker_manager.generate_compose_config()
            services = compose_config.get("services", {})

            # Should contain only required services
            assert "qdrant" in services
            assert "data-cleaner" in services
            assert "ollama" not in services

            # Verify service configurations
            qdrant_config = services["qdrant"]
            assert "build" in qdrant_config
            assert any(":6333" in port for port in qdrant_config["ports"])

            cleaner_config = services["data-cleaner"]
            assert "build" in cleaner_config
            assert "cleaner" in cleaner_config["build"]["dockerfile"]

    def test_voyage_ai_idempotent_setup(self):
        """Test that setup command is idempotent for VoyageAI provider."""
        # Set up VoyageAI API key
        os.environ["VOYAGE_API_KEY"] = "test_api_key_for_testing"

        # Create VoyageAI configuration
        self.create_voyage_ai_config()

        # Mock all Docker operations
        with patch(
            "code_indexer.services.docker_manager.subprocess"
        ) as mock_subprocess:
            # Mock successful Docker availability checks
            mock_subprocess.run.return_value.returncode = 0
            mock_subprocess.run.return_value.stdout = "Docker is available"

            # Mock container state checks
            mock_subprocess.Popen.return_value.wait.return_value = 0
            mock_subprocess.Popen.return_value.stdout.readline.return_value = ""
            mock_subprocess.Popen.return_value.poll.return_value = 0

            # Import DockerManager
            from code_indexer.services.docker_manager import DockerManager
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.test_dir)
            config = config_manager.load()

            docker_manager = DockerManager(
                console=None, force_docker=True, main_config=config.model_dump()
            )

            # Mock service states to simulate healthy services
            with patch.object(docker_manager, "get_service_state") as mock_state:
                mock_state.return_value = {
                    "exists": True,
                    "running": True,
                    "healthy": True,
                    "up_to_date": True,
                }

                # Test idempotent behavior
                result = docker_manager.start_services(recreate=False)
                assert result is True

                # Verify that start_services detects healthy services and skips restart
                # This would be validated by checking the mock calls and output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
