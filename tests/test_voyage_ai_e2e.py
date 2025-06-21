"""End-to-end tests for VoyageAI provider with cloud vectorization service.

Refactored to use NEW STRATEGY with test infrastructure for better performance.
"""

import os
import tempfile
import shutil
import pytest
import json
import time
from pathlib import Path
from unittest.mock import patch

# Import new test infrastructure
from .test_infrastructure import create_fast_e2e_setup, EmbeddingProvider


class TestVoyageAIE2E:
    """End-to-end tests for VoyageAI provider without Ollama dependency."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment using test infrastructure."""
        # NEW STRATEGY: Use test infrastructure for consistent setup
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.VOYAGE_AI
        )

        # Create temporary directory for test
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()

        # Store original environment
        self.original_env = dict(os.environ)

        # NEW STRATEGY: Ensure services ready, then setup project
        services_ready = self.service_manager.ensure_services_ready(
            working_dir=self.test_dir
        )
        if not services_ready:
            pytest.skip("Could not start required services for VoyageAI E2E testing")

        # Change to test directory safely and create test code files
        with self.dir_manager.safe_chdir(self.test_dir):
            self.create_test_codebase()

        yield

        # NEW STRATEGY: Only clean project data, keep services running
        try:
            with self.dir_manager.safe_chdir(self.test_dir):
                self.cli_helper.run_cli_command(["clean-data"], expect_success=False)
        except Exception:
            pass
        finally:
            # Cleanup directory
            try:
                os.chdir(self.original_cwd)
                if self.test_dir.exists():
                    shutil.rmtree(self.test_dir)
            except Exception:
                pass

            # Restore environment
            os.environ.clear()
            os.environ.update(self.original_env)

    def create_test_codebase(self):
        """Create a simple test codebase using test infrastructure."""
        # Use test infrastructure for creating test files
        test_files = {
            "main.py": '''def hello_world():
    """Print hello world message."""
    print("Hello, World!")

def calculate_fibonacci(n):
    """Calculate fibonacci number."""
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

if __name__ == "__main__":
    hello_world()
    print(f"Fibonacci(10) = {calculate_fibonacci(10)}")''',
            "utils.py": '''import math

def calculate_distance(x1, y1, x2, y2):
    """Calculate Euclidean distance between two points."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def format_number(num, decimals=2):
    """Format number with specified decimal places."""
    return f"{num:.{decimals}f}"''',
            "README.md": """# Test Project

This is a test project for VoyageAI E2E testing.

## Features
- Hello world function
- Fibonacci calculation
- Distance calculation utilities""",
        }

        self.dir_manager.create_test_project(self.test_dir, custom_files=test_files)

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
        not os.getenv("VOYAGE_API_KEY"),
        reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
    )
    def test_voyage_ai_full_workflow(self):
        """Test complete VoyageAI workflow with real API using test infrastructure."""
        # Use real VoyageAI API key from environment

        with self.dir_manager.safe_chdir(self.test_dir):
            # NEW STRATEGY: Services should already be running from fixture
            # Just ensure this project is initialized properly
            self.cli_helper.run_cli_command(
                ["init", "--embedding-provider", "voyage-ai", "--force"]
            )

            # Verify provider configuration using test infrastructure
            status_result = self.cli_helper.run_cli_command(["status"])

            # Verify Voyage-AI provider is shown and Ollama is not mentioned
            assert (
                "ollama" not in status_result.stdout.lower()
            ), f"Ollama should not be in status: {status_result.stdout}"
            assert (
                "voyage" in status_result.stdout.lower()
                or "voyage-ai" in status_result.stdout.lower()
            ), f"VoyageAI should be in status: {status_result.stdout}"

            # Step 3: Check status (should show only required services)
            result = self.cli_helper.run_cli_command(["status"])

            # Should show Qdrant and VoyageAI, but not Ollama
            status_output = result.stdout.lower()
            assert "qdrant" in status_output
            assert (
                "voyage" in status_output
            ), f"VoyageAI should be in status: {result.stdout}"
            assert "ollama" not in status_output

            # Step 4: Real indexing with VoyageAI
            self.cli_helper.run_cli_command(["index"], timeout=120)

            # Step 5: Test query functionality with real VoyageAI
            result = self.cli_helper.run_cli_command(
                ["query", "fibonacci function"], timeout=60
            )
            assert len(result.stdout.strip()) > 0, "Query should return results"

            # Step 6: Clean data instead of stopping services (NEW STRATEGY)
            self.cli_helper.run_cli_command(["clean-data"], timeout=60)

            # Step 7: Test start command (should work without Ollama)
            self.cli_helper.run_cli_command(["start"], timeout=120)

            # Verify services are running after restart
            self.cli_helper.run_cli_command(["status"])

        # NOTE: Cleanup handled by fixture using NEW STRATEGY

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

    def test_voyage_ai_idempotent_start(self):
        """Test that start command is idempotent for VoyageAI provider."""
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
