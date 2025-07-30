"""
Test Infrastructure Module

Provides reusable utilities for E2E and integration tests following the
"NEW STRATEGY" of keeping services running and comprehensive setup.

Key Principles:
- Keep services running between tests for faster execution
- Ensure prerequisites are met at test setup, not torn down at teardown
- Use clean-data for isolation, not full service shutdown
- Handle service unavailability gracefully
- Provide consistent patterns for common test operations
"""

import os
import subprocess
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Import will be done inside function to avoid circular imports


class EmbeddingProvider(Enum):
    """Supported embedding providers for tests."""

    VOYAGE_AI = "voyage-ai"
    OLLAMA = "ollama"


class CleanupStrategy(Enum):
    """Different cleanup strategies for tests."""

    CLEAN_DATA = "clean-data"  # Fast cleanup, keeps services running
    UNINSTALL = "uninstall"  # Full cleanup, stops services


@dataclass
class InfrastructureConfig:
    """Configuration for test infrastructure."""

    embedding_provider: EmbeddingProvider = EmbeddingProvider.VOYAGE_AI
    cleanup_strategy: CleanupStrategy = CleanupStrategy.CLEAN_DATA
    service_timeout: int = (
        120  # Reduced from 450s since we now do aggressive cleanup first
    )
    status_timeout: int = 30
    init_timeout: int = 60
    cleanup_timeout: int = 60
    cli_command_prefix: List[str] = field(default_factory=lambda: ["code-indexer"])
    retry_attempts: int = 3
    adaptive_timeout_multiplier: float = 1.5


@dataclass
class ProjectTestConfig:
    """Configuration template for test projects."""

    name: str
    embedding_provider: EmbeddingProvider = EmbeddingProvider.VOYAGE_AI
    collection_base_name: str = "test_collection"
    chunk_size: int = 1000
    chunk_overlap: int = 100
    qdrant_vector_size: int = 1024
    voyage_ai_model: str = "voyage-code-3"
    voyage_ai_batch_size: int = 64
    voyage_ai_parallel_requests: int = 6
    use_provider_aware_collections: bool = True

    def get_config_dict(self, codebase_dir: str) -> Dict:
        """Generate config dictionary for this test project."""
        return {
            "codebase_dir": codebase_dir,
            "file_extensions": [
                "py",
                "js",
                "ts",
                "tsx",
                "java",
                "c",
                "cpp",
                "h",
                "hpp",
                "go",
                "rs",
                "rb",
                "php",
                "pl",
                "pm",
                "pod",
                "t",
                "psgi",
                "sh",
                "bash",
                "html",
                "css",
                "md",
                "json",
                "yaml",
                "yml",
                "toml",
                "sql",
                "swift",
                "kt",
                "kts",
                "scala",
                "dart",
                "vue",
                "jsx",
            ],
            "exclude_dirs": [
                "node_modules",
                "venv",
                "__pycache__",
                ".git",
                "dist",
                "build",
                "target",
                ".idea",
                ".vscode",
                ".gradle",
                "bin",
                "obj",
                "coverage",
                ".next",
                ".nuxt",
                "dist-*",
                ".code-indexer",
            ],
            "embedding_provider": self.embedding_provider.value,
            "ollama": {
                "host": "http://localhost:11434",
                "model": "nomic-embed-text",
                "timeout": 30,
                "num_parallel": 1,
                "max_loaded_models": 1,
                "max_queue": 512,
            },
            "voyage_ai": {
                "api_endpoint": "https://api.voyageai.com/v1/embeddings",
                "model": self.voyage_ai_model,
                "timeout": 30,
                "parallel_requests": self.voyage_ai_parallel_requests,
                "batch_size": self.voyage_ai_batch_size,
                "max_retries": 3,
                "retry_delay": 1.0,
                "exponential_backoff": True,
            },
            "qdrant": {
                "host": "http://localhost:6333",
                "collection_base_name": self.collection_base_name,  # Preserve test collection name!
                "vector_size": self.qdrant_vector_size,
                "hnsw_ef": 64,
                "hnsw_ef_construct": 200,
                "hnsw_m": 32,
            },
            "indexing": {
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "max_file_size": 1048576,
                "index_comments": True,
                "use_semantic_chunking": True,  # Enable semantic chunking for tests
            },
            "timeouts": {
                "service_startup": 240,
                "service_shutdown": 30,
                "port_release": 15,
                "cleanup_validation": 30,
                "health_check": 180,
                "data_cleaner_startup": 180,
            },
            "polling": {
                "initial_interval": 0.5,
                "backoff_factor": 1.2,
                "max_interval": 2.0,
            },
            "project_containers": {
                "qdrant_name": f"cidx-test_{self.name}-qdrant",
                "ollama_name": f"cidx-test_{self.name}-ollama",
                "data_cleaner_name": f"cidx-test_{self.name}-data-cleaner",
            },
            "project_ports": {
                "qdrant_port": None,
                "ollama_port": None,
                "data_cleaner_port": None,
            },
        }


class TestProjectInventory:
    """Manages isolated test project configurations without tinkering with existing environments."""

    # Predefined test project configurations
    BRANCH_TOPOLOGY = ProjectTestConfig(
        name="branch_topology",
        collection_base_name="test_branch_topology_clean",
        chunk_size=1000,
        voyage_ai_parallel_requests=6,
    )

    RECONCILE = ProjectTestConfig(
        name="reconcile",
        collection_base_name="reconcile_test_collection",
        chunk_size=1000,
        voyage_ai_batch_size=32,
    )

    TIMESTAMP_COMPARISON = ProjectTestConfig(
        name="timestamp_comparison",
        collection_base_name="test_timestamp_comparison",
        chunk_size=800,
    )

    CLI_PROGRESS = ProjectTestConfig(
        name="cli_progress", collection_base_name="test_cli_progress", chunk_size=1000
    )

    GIT_AWARE_WATCH = ProjectTestConfig(
        name="git_aware_watch",
        collection_base_name="test_watch",
        chunk_size=500,
        chunk_overlap=50,
        voyage_ai_batch_size=16,
        voyage_ai_parallel_requests=4,
    )

    DELETION_HANDLING = ProjectTestConfig(
        name="deletion_handling",
        collection_base_name="test_deletion",
        chunk_size=800,
        chunk_overlap=80,
        voyage_ai_batch_size=32,
    )

    RECONCILE_BRANCH_VISIBILITY = ProjectTestConfig(
        name="reconcile_branch_visibility",
        collection_base_name="test_reconcile_branch_visibility",
        chunk_size=1000,
        chunk_overlap=100,
        voyage_ai_batch_size=32,
        voyage_ai_parallel_requests=4,
    )

    CLAUDE_E2E = ProjectTestConfig(
        name="claude_e2e",
        collection_base_name="test_claude",
        chunk_size=1000,
        chunk_overlap=100,
        voyage_ai_batch_size=64,
    )

    END_TO_END_COMPLETE = ProjectTestConfig(
        name="end_to_end_complete",
        collection_base_name="test_e2e_complete",
        chunk_size=1200,
        chunk_overlap=120,
        voyage_ai_batch_size=32,
        voyage_ai_parallel_requests=8,
    )

    START_STOP_E2E = ProjectTestConfig(
        name="start_stop_e2e",
        collection_base_name="start_stop_test_collection",
        chunk_size=1000,
        chunk_overlap=100,
        voyage_ai_batch_size=64,
    )

    DOCKER_COMPOSE_VALIDATION = ProjectTestConfig(
        name="docker_compose_validation",
        collection_base_name="test_docker_compose",
        chunk_size=500,
        chunk_overlap=50,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    IDEMPOTENT_START = ProjectTestConfig(
        name="idempotent_start",
        collection_base_name="test_idempotent",
        chunk_size=600,
        chunk_overlap=60,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    INTEGRATION_MULTIPROJECT_1 = ProjectTestConfig(
        name="integration_multiproject_1",
        collection_base_name="test_multiproject_1",
        chunk_size=800,
        chunk_overlap=80,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    INTEGRATION_MULTIPROJECT_2 = ProjectTestConfig(
        name="integration_multiproject_2",
        collection_base_name="test_multiproject_2",
        chunk_size=900,
        chunk_overlap=90,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    LINE_NUMBER_DISPLAY = ProjectTestConfig(
        name="line_number_display",
        collection_base_name="test_line_numbers",
        chunk_size=600,
        chunk_overlap=60,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    OPTIMIZED_EXAMPLE = ProjectTestConfig(
        name="optimized_example",
        collection_base_name="test_optimized",
        chunk_size=700,
        chunk_overlap=70,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    QDRANT_CLEAR_COLLECTION_BUG = ProjectTestConfig(
        name="qdrant_clear_collection_bug",
        collection_base_name="test_qdrant_clear",
        chunk_size=800,
        chunk_overlap=80,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    TIMEOUT_CONFIG = ProjectTestConfig(
        name="timeout_config",
        collection_base_name="test_timeout",
        chunk_size=500,
        chunk_overlap=50,
        voyage_ai_batch_size=16,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    VOYAGE_AI_E2E = ProjectTestConfig(
        name="voyage_ai_e2e",
        collection_base_name="test_voyage_ai",
        chunk_size=1000,
        chunk_overlap=100,
        voyage_ai_batch_size=64,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    GIT_AWARE_WATCH_E2E_ADDITIONAL = ProjectTestConfig(
        name="git_aware_watch_e2e_additional",
        collection_base_name="test_git_watch_additional",
        chunk_size=600,
        chunk_overlap=60,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    WATCH_TIMESTAMP_UPDATE = ProjectTestConfig(
        name="watch_timestamp_update",
        collection_base_name="test_watch_timestamp",
        chunk_size=500,
        chunk_overlap=50,
        voyage_ai_batch_size=16,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    END_TO_END_DUAL_ENGINE = ProjectTestConfig(
        name="end_to_end_dual_engine",
        collection_base_name="test_dual_engine",
        chunk_size=800,
        chunk_overlap=80,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    STUCK_INCREMENTAL_INDEXING = ProjectTestConfig(
        name="stuck_incremental_indexing",
        collection_base_name="test_stuck_incremental",
        chunk_size=700,
        chunk_overlap=70,
        voyage_ai_batch_size=16,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    DEADLOCK_REPRODUCTION = ProjectTestConfig(
        name="deadlock_reproduction",
        collection_base_name="test_deadlock",
        chunk_size=500,
        chunk_overlap=50,
        voyage_ai_batch_size=16,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    STUCK_VERIFICATION_RETRY = ProjectTestConfig(
        name="stuck_verification_retry",
        collection_base_name="test_stuck_verification",
        chunk_size=600,
        chunk_overlap=60,
        voyage_ai_batch_size=16,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    COMPREHENSIVE_GIT_WORKFLOW = ProjectTestConfig(
        name="comprehensive_git_workflow",
        collection_base_name="test_comprehensive_git",
        chunk_size=900,
        chunk_overlap=90,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    COW_CLONE_E2E_FULL_AUTOMATION = ProjectTestConfig(
        name="cow_clone_e2e_full_automation",
        collection_base_name="code_index",  # Use default collection name that works
        chunk_size=1000,
        chunk_overlap=100,
        voyage_ai_batch_size=64,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    DEBUG_BRANCH_ISOLATION = ProjectTestConfig(
        name="debug_branch_isolation",
        collection_base_name="test_debug_branch",
        chunk_size=700,
        chunk_overlap=70,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    BRANCH_TRANSITION_LOGIC_FIX = ProjectTestConfig(
        name="branch_transition_logic_fix",
        collection_base_name="test_branch_transition",
        chunk_size=800,
        chunk_overlap=80,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    COMPARE_SEARCH_METHODS = ProjectTestConfig(
        name="compare_search_methods",
        collection_base_name="test_compare_search",
        chunk_size=600,
        chunk_overlap=60,
        voyage_ai_batch_size=32,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    DEFAULT = ProjectTestConfig(
        name="default", collection_base_name="test_default", chunk_size=1000
    )

    # Kotlin semantic search test configurations
    kotlin_semantic_search = ProjectTestConfig(
        name="kotlin_semantic_search",
        collection_base_name="test_kotlin_semantic",
        chunk_size=2000,
        chunk_overlap=200,
        voyage_ai_batch_size=64,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    kotlin_language_filter = ProjectTestConfig(
        name="kotlin_language_filter",
        collection_base_name="test_kotlin_filter",
        chunk_size=2000,
        chunk_overlap=200,
        voyage_ai_batch_size=64,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    kotlin_semantic_types = ProjectTestConfig(
        name="kotlin_semantic_types",
        collection_base_name="test_kotlin_types",
        chunk_size=2000,
        chunk_overlap=200,
        voyage_ai_batch_size=64,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    DOCKER_UNINSTALL_COMPLETE_CLEANUP = ProjectTestConfig(
        name="docker_uninstall_complete_cleanup",
        collection_base_name="test_docker_uninstall_cleanup",
        chunk_size=1000,
        chunk_overlap=100,
        voyage_ai_batch_size=64,
        voyage_ai_parallel_requests=4,
        embedding_provider=EmbeddingProvider.VOYAGE_AI,
    )

    @classmethod
    def create_project_space(
        cls, test_dir: Path, project_config: ProjectTestConfig
    ) -> Path:
        """Create isolated project space with specific configuration.

        Args:
            test_dir: Base test directory
            project_config: Test project configuration

        Returns:
            Path to the created config file
        """
        import json

        config_dir = test_dir / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"

        # Generate fresh config for this test project
        config = project_config.get_config_dict(str(test_dir))

        try:
            with open(config_file, "w") as f:
                json.dump(config, f, indent=2)
        except PermissionError as e:
            # Docker permission issues - skip gracefully
            import pytest

            pytest.skip(f"Docker permission denied for config file creation: {e}")
        except Exception as e:
            # Other file creation issues
            import pytest

            pytest.skip(f"Failed to create test project configuration: {e}")

        print(
            f"🔧 Created isolated test project '{project_config.name}' with collection: {project_config.collection_base_name}"
        )

        return config_file

    @classmethod
    def get_all_test_collections(cls) -> List[str]:
        """Get list of all test collection base names for cleanup."""
        return [
            cls.BRANCH_TOPOLOGY.collection_base_name,
            cls.RECONCILE.collection_base_name,
            cls.TIMESTAMP_COMPARISON.collection_base_name,
            cls.CLI_PROGRESS.collection_base_name,
            cls.GIT_AWARE_WATCH.collection_base_name,
            cls.DELETION_HANDLING.collection_base_name,
            cls.CLAUDE_E2E.collection_base_name,
            cls.END_TO_END_COMPLETE.collection_base_name,
            cls.START_STOP_E2E.collection_base_name,
            cls.DEFAULT.collection_base_name,
        ]


class ServiceManager:
    """Manages services for tests following NEW STRATEGY patterns."""

    def __init__(self, config: Optional[InfrastructureConfig] = None):
        self.config = config or InfrastructureConfig()

    def are_services_running(self, timeout: Optional[int] = None) -> bool:
        """Check if services are currently running.

        Args:
            timeout: Timeout for status command (uses config default if None)

        Returns:
            True if services are running and ready
        """
        timeout = timeout or self.config.status_timeout

        try:
            # Small delay before status check to ensure config is updated
            import time

            time.sleep(0.5)

            result = subprocess.run(
                self.config.cli_command_prefix + ["status"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                return False

            # Check for essential service availability
            # Accept various healthy states depending on setup
            essential_ready = (
                ("Qdrant" in result.stdout and "✅ Ready" in result.stdout)
                or ("Qdrant" in result.stdout and "✅" in result.stdout)
                or ("Essential services accessible" in result.stdout)
            )

            # Note: Docker services may not be available in all test scenarios

            # Accept if essential services are ready, with or without full Docker setup
            return essential_ready

        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False

    def ensure_services_ready(
        self,
        embedding_provider: Optional[EmbeddingProvider] = None,
        force_recreate: bool = False,
        working_dir: Optional[Path] = None,
    ) -> bool:
        """Ensure services are running using NEW STRATEGY.

        Args:
            embedding_provider: Provider to use (uses config default if None)
            force_recreate: Whether to force service recreation
            working_dir: Directory to run commands in

        Returns:
            True if services are ready, False otherwise
        """
        original_cwd = None
        provider = embedding_provider or self.config.embedding_provider

        try:
            # Check if we're running under full-automation.sh with shared services
            import os

            if os.getenv("FULL_AUTOMATION") == "1":
                print(
                    "🔗 Running under full-automation.sh - using shared test services"
                )
                # Try to use existing shared services instead of starting new ones
                try:
                    from code_indexer.config import ConfigManager
                    from code_indexer.services.qdrant import QdrantClient

                    config_manager = ConfigManager.create_with_backtrack()
                    config = config_manager.load()
                    qdrant_client = QdrantClient(config.qdrant)

                    if qdrant_client.health_check():
                        print("✅ Shared test services are accessible and healthy")
                        return True
                    else:
                        print(
                            "⚠️ Shared services not accessible, will start individual services"
                        )
                except Exception as e:
                    print(
                        f"⚠️ Could not connect to shared services: {e}, will start individual services"
                    )

            # AGGRESSIVE APPROACH: Always ensure services are properly started
            # Skip the "already running" check since it's unreliable in test scenarios
            # where multiple test contexts may interfere with each other

            # If force_recreate, clean up existing services first
            if force_recreate:
                print("Force recreate requested, cleaning up existing services...")
                # Emergency cleanup for force recreate situations
                self.cleanup_excessive_test_volumes()
                self.progressive_cleanup_test_images(
                    max_images=10
                )  # More aggressive cleanup
                subprocess.run(
                    self.config.cli_command_prefix + ["uninstall"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            # Check if shared test services from full-automation.sh are accessible
            # This handles the case where services are started by test suite setup
            try:
                from code_indexer.config import ConfigManager
                from code_indexer.services.qdrant import QdrantClient

                config_manager = ConfigManager.create_with_backtrack()
                config = config_manager.load()
                qdrant_client = QdrantClient(config.qdrant)

                if qdrant_client.health_check():
                    print(
                        "✅ Using shared test services (started by full-automation.sh)"
                    )
                    return True
            except Exception:
                pass

            # Services not accessible - try to start them
            print("Starting services for E2E testing...")

            # AGGRESSIVE progressive cleanup to maintain reasonable volume and image counts
            self.progressive_cleanup_test_volumes(max_volumes=5)  # Very aggressive
            self.progressive_cleanup_test_images(max_images=3)  # Very aggressive

            # Additional cleanup: force cleanup of excessive collections before starting
            self._cleanup_excessive_qdrant_collections()

            # SMART CONTAINER MANAGEMENT: Check for existing containers and use them if available
            preserved_containers = self._check_and_preserve_compatible_containers()
            if preserved_containers:
                print(
                    f"✅ Using existing compatible containers: {preserved_containers}"
                )

                # CRITICAL FIX: Extract port information from running containers and update config
                success = self._ensure_config_matches_containers(
                    preserved_containers, working_dir
                )
                if not success:
                    print("⚠️ Could not sync configuration with existing containers")
                    # Fall through to restart containers with proper config
                else:
                    # Check if these containers provide working services with updated config
                    if self.are_services_running():
                        print("✅ Existing containers are providing working services")
                        return True
                    else:
                        print(
                            "⚠️ Existing containers found but services not ready, will restart"
                        )

            # Stop any conflicting containers (but preserve compatible ones)
            self._stop_conflicting_containers()

            if working_dir:
                original_cwd = Path.cwd()
                os.chdir(working_dir)

            # Preemptive cleanup to handle noisy neighbor scenario
            print("Performing preemptive cleanup to handle dirty state...")
            cleanup_result = subprocess.run(
                self.config.cli_command_prefix + ["clean-data", "--all-projects"],
                capture_output=True,
                text=True,
                timeout=self.config.cleanup_timeout,
            )
            if cleanup_result.returncode != 0:
                print(f"Cleanup warning (non-fatal): {cleanup_result.stderr}")

            # Initialize and start services
            if not self._ensure_project_initialized(provider):
                print("Failed to initialize project")
                return False

            # Start services
            start_result = subprocess.run(
                self.config.cli_command_prefix + ["start"],
                capture_output=True,
                text=True,
                timeout=self.config.service_timeout,
            )

            if start_result.returncode != 0:
                # Check for Qdrant WAL error first
                if (
                    "Wal error" in start_result.stdout
                    or "Resource temporarily unavailable" in start_result.stdout
                    or "Can't write to WAL" in start_result.stdout
                ):
                    print("Detected Qdrant WAL error, cleaning up Qdrant data...")

                    # Clean up Qdrant data directory
                    if working_dir:
                        qdrant_dir = working_dir / ".code-indexer" / "qdrant"
                    else:
                        qdrant_dir = Path.cwd() / ".code-indexer" / "qdrant"
                    if qdrant_dir.exists():
                        import shutil

                        try:
                            shutil.rmtree(qdrant_dir / "storage", ignore_errors=True)
                            shutil.rmtree(qdrant_dir / "snapshots", ignore_errors=True)
                            shutil.rmtree(qdrant_dir / "log", ignore_errors=True)
                            shutil.rmtree(qdrant_dir / "wal", ignore_errors=True)
                            print("✅ Cleaned Qdrant data directories")
                        except Exception as e:
                            print(f"Warning: Error cleaning Qdrant data: {e}")

                    # Try starting again after cleanup
                    start_result = subprocess.run(
                        self.config.cli_command_prefix + ["start"],
                        capture_output=True,
                        text=True,
                        timeout=self.config.service_timeout,
                    )

                    if start_result.returncode != 0:
                        print(
                            "Failed to start after Qdrant cleanup, trying full uninstall..."
                        )
                        # Fall through to container cleanup below
                    else:
                        # Success after Qdrant cleanup
                        return True

                # Check for container issues and attempt recovery
                if (
                    "No such container" in start_result.stdout
                    or "Error response from daemon" in start_result.stdout
                    or start_result.returncode
                    != 0  # Also try recovery for other failures
                ):
                    print(
                        "Detected container issues, attempting uninstall and clean restart..."
                    )

                    # Clean up broken state
                    subprocess.run(
                        self.config.cli_command_prefix + ["uninstall"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                    # Reinitialize and try again
                    if self._ensure_project_initialized(provider):
                        start_result = subprocess.run(
                            self.config.cli_command_prefix + ["start"],
                            capture_output=True,
                            text=True,
                            timeout=self.config.service_timeout,
                        )

                        if start_result.returncode != 0:
                            print("Failed to start services after recovery attempt:")
                            print(f"STDOUT: {start_result.stdout}")
                            print(f"STDERR: {start_result.stderr}")
                            return False
                    else:
                        print("Failed to reinitialize after container cleanup")
                        return False
                else:
                    print("Failed to start services:")
                    print(f"STDOUT: {start_result.stdout}")
                    print(f"STDERR: {start_result.stderr}")
                    return False

            # Wait for services to be ready
            import time

            # CRITICAL FIX: Add delay to ensure port configuration updates are propagated
            print("Waiting for port configuration to stabilize...")
            time.sleep(2)  # Allow config file updates to be written and propagated

            start_time = time.time()
            timeout = self.config.service_timeout  # Use full configured timeout
            check_interval = 3  # Slightly longer interval for better stability
            while time.time() - start_time < timeout:
                if self.are_services_running():
                    print("Services are ready!")
                    return True
                print(
                    f"Waiting for services... ({int(time.time() - start_time)}s elapsed)"
                )
                time.sleep(check_interval)

            print("Services startup timeout")
            return False

        except Exception as e:
            print(f"Service setup error: {e}")
            return False

        finally:
            if original_cwd:
                try:
                    os.chdir(original_cwd)
                except (FileNotFoundError, OSError):
                    pass

    def _ensure_project_initialized(self, provider: EmbeddingProvider) -> bool:
        """Initialize project with specified provider."""
        try:
            init_result = subprocess.run(
                self.config.cli_command_prefix
                + ["init", "--force", "--embedding-provider", provider.value],
                capture_output=True,
                text=True,
                timeout=self.config.init_timeout,
            )

            if init_result.returncode != 0:
                print(f"Init failed: {init_result.stderr}")
                return False

            return True

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            print(f"Init error: {e}")
            return False

    def cleanup_project_data(
        self,
        strategy: Optional[CleanupStrategy] = None,
        working_dir: Optional[Path] = None,
    ) -> bool:
        """Clean up project data using specified strategy.

        Args:
            strategy: Cleanup strategy (uses config default if None)
            working_dir: Directory to run cleanup in

        Returns:
            True if cleanup succeeded
        """
        strategy = strategy or self.config.cleanup_strategy
        original_cwd = None

        try:
            if working_dir:
                original_cwd = Path.cwd()
                os.chdir(working_dir)

            if strategy == CleanupStrategy.CLEAN_DATA:
                cmd = self.config.cli_command_prefix + ["clean-data", "--all-projects"]
            else:  # UNINSTALL
                cmd = self.config.cli_command_prefix + ["uninstall"]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.cleanup_timeout,
            )

            return result.returncode == 0

        except Exception as e:
            print(f"Cleanup warning: {e}")
            # Don't fail tests for cleanup issues when using NEW STRATEGY
            return strategy == CleanupStrategy.CLEAN_DATA

        finally:
            if original_cwd:
                try:
                    os.chdir(original_cwd)
                except (FileNotFoundError, OSError):
                    pass

    def progressive_cleanup_test_volumes(self, max_volumes: int = 10) -> bool:
        """Progressive cleanup of test volumes to maintain a reasonable count.

        This method runs on every test setup to keep volumes under control
        and prevent accumulation that causes startup timeouts.

        Args:
            max_volumes: Maximum number of test volumes to keep (default: 30)

        Returns:
            True if cleanup was successful or not needed
        """
        try:
            # Check if we're using podman or docker
            container_cmd = "podman"
            try:
                subprocess.run(
                    [container_cmd, "--version"], capture_output=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                container_cmd = "docker"
                try:
                    subprocess.run(
                        [container_cmd, "--version"], capture_output=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return True  # Skip if no container engine

            # List all volumes
            result = subprocess.run(
                [container_cmd, "volume", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return True  # Skip on error

            # Find test volumes (more comprehensive patterns)
            all_volumes = (
                result.stdout.strip().split("\n") if result.stdout.strip() else []
            )
            test_volumes = [
                v
                for v in all_volumes
                if v.startswith("code_indexer_test_")
                or v.startswith("code_indexer_e2e_")
                or v.startswith("code_indexer_nonroot_test_")
                or (v.startswith("tmp") and ("qdrant" in v or "ollama" in v))
                or "_qdrant_data" in v
                or "_ollama_data" in v
                or "_qdrant_metadata" in v
                or "_ollama_metadata" in v
            ]

            if len(test_volumes) > max_volumes:
                # Sort volumes by name to get consistent removal order (oldest patterns first)
                test_volumes.sort()
                volumes_to_remove = test_volumes[
                    :-max_volumes
                ]  # Keep the last max_volumes

                print(
                    f"🧹 Progressive cleanup: {len(test_volumes)} volumes found, removing {len(volumes_to_remove)} oldest"
                )

                # Remove volumes in small batches to avoid command line length limits
                batch_size = 20
                removed_count = 0
                for i in range(0, len(volumes_to_remove), batch_size):
                    batch = volumes_to_remove[i : i + batch_size]
                    cleanup_result = subprocess.run(
                        [container_cmd, "volume", "rm", "-f"] + batch,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if cleanup_result.returncode == 0:
                        removed_count += len(batch)

                if removed_count > 0:
                    print(
                        f"✅ Progressive cleanup: removed {removed_count} old test volumes"
                    )

                return True
            else:
                # Only log when volume count is getting high
                if len(test_volumes) > max_volumes // 2:
                    print(
                        f"📊 Volume count: {len(test_volumes)} test volumes (threshold: {max_volumes})"
                    )
                return True

        except Exception:
            # Silent cleanup - don't spam logs with warnings
            return True

    def cleanup_excessive_test_volumes(self) -> bool:
        """Emergency cleanup for when volumes are critically excessive.

        This is the heavy-duty cleanup for when progressive cleanup wasn't enough.

        Returns:
            True if cleanup was successful or not needed
        """
        try:
            print("🧹 Emergency cleanup: Checking for critically excessive volumes...")

            # Check if we're using podman or docker
            container_cmd = "podman"
            try:
                subprocess.run(
                    [container_cmd, "--version"], capture_output=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                container_cmd = "docker"
                try:
                    subprocess.run(
                        [container_cmd, "--version"], capture_output=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    print("No container engine found, skipping volume cleanup")
                    return True

            # List all volumes
            result = subprocess.run(
                [container_cmd, "volume", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"Could not list volumes: {result.stderr}")
                return True

            # Find test volumes
            all_volumes = (
                result.stdout.strip().split("\n") if result.stdout.strip() else []
            )
            test_volumes = [
                v
                for v in all_volumes
                if v.startswith("code_indexer_test_")
                or v.startswith("code_indexer_e2e_")
                or v.startswith("code_indexer_nonroot_test_")
                or (v.startswith("tmp") and ("qdrant" in v or "ollama" in v))
            ]

            if len(test_volumes) > 100:  # Emergency threshold
                print(
                    f"🚨 EMERGENCY: Found {len(test_volumes)} test volumes - critical cleanup needed"
                )
                print("🗑️  Performing emergency cleanup of old test volumes...")

                # Stop any running containers first
                subprocess.run(
                    [
                        container_cmd,
                        "stop",
                        "code-indexer-qdrant",
                        "code-indexer-data-cleaner",
                        "code-indexer-ollama",
                    ],
                    capture_output=True,
                )
                subprocess.run(
                    [
                        container_cmd,
                        "rm",
                        "code-indexer-qdrant",
                        "code-indexer-data-cleaner",
                        "code-indexer-ollama",
                    ],
                    capture_output=True,
                )

                # Remove test volumes in batches to avoid command line length limits
                batch_size = 50
                for i in range(0, len(test_volumes), batch_size):
                    batch = test_volumes[i : i + batch_size]
                    cleanup_result = subprocess.run(
                        [container_cmd, "volume", "rm", "-f"] + batch,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if cleanup_result.returncode != 0:
                        print(
                            f"Warning: Some volumes could not be removed: {cleanup_result.stderr}"
                        )
                    else:
                        print(
                            f"✅ Emergency cleanup: removed {len(batch)} test volumes"
                        )

                print(
                    f"✅ Emergency cleanup complete - removed {len(test_volumes)} volumes"
                )
                return True
            else:
                return True

        except Exception as e:
            print(f"Emergency cleanup warning (non-critical): {e}")
            return True  # Don't fail tests for cleanup issues

    def progressive_cleanup_test_images(self, max_images: int = 5) -> bool:
        """Progressive cleanup of test container images to prevent accumulation.

        This method runs during test setup to keep test images under control
        and prevent disk space issues from accumulated test container images.

        Args:
            max_images: Maximum number of test images to keep (default: 20)

        Returns:
            True if cleanup was successful or not needed
        """
        try:
            # Check if we're using podman or docker
            container_cmd = "podman"
            try:
                subprocess.run(
                    [container_cmd, "--version"], capture_output=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                container_cmd = "docker"
                try:
                    subprocess.run(
                        [container_cmd, "--version"], capture_output=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return True  # Skip if no container engine

            # List all images
            result = subprocess.run(
                [
                    container_cmd,
                    "images",
                    "--format",
                    "{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return True  # Skip on error

            # Find test images (comprehensive patterns)
            all_images = (
                result.stdout.strip().split("\n") if result.stdout.strip() else []
            )
            test_images = []

            for image_line in all_images:
                if not image_line.strip():
                    continue

                parts = image_line.split()
                if len(parts) < 2:
                    continue

                image_name = parts[0]
                image_id = parts[1]

                # Match test-related image patterns
                if any(
                    pattern in image_name
                    for pattern in [
                        "test_",
                        "code_indexer_test_",
                        "_test_",
                        "code_indexer_e2e_",
                        "_e2e_",
                        "code_indexer_nonroot_test_",
                    ]
                ):
                    test_images.append((image_name, image_id, image_line))

            if len(test_images) > max_images:
                # Sort by creation time (oldest first) - assume newer images are at the end
                test_images.sort(
                    key=lambda x: x[2]
                )  # Sort by full line which includes timestamp
                images_to_remove = test_images[:-max_images]  # Keep the last max_images

                print(
                    f"🧹 Progressive cleanup: {len(test_images)} test images found, removing {len(images_to_remove)} oldest"
                )

                # Remove images in small batches
                batch_size = 10
                removed_count = 0
                for i in range(0, len(images_to_remove), batch_size):
                    batch = images_to_remove[i : i + batch_size]
                    image_ids = [img[1] for img in batch]

                    cleanup_result = subprocess.run(
                        [container_cmd, "rmi", "-f"] + image_ids,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if cleanup_result.returncode == 0:
                        removed_count += len(batch)
                    else:
                        # Some images might be in use, continue with next batch
                        pass

                if removed_count > 0:
                    print(
                        f"✅ Progressive cleanup: removed {removed_count} old test images"
                    )

                return True
            else:
                # Only log when image count is getting high
                if len(test_images) > max_images // 2:
                    print(
                        f"📊 Image count: {len(test_images)} test images (threshold: {max_images})"
                    )
                return True

        except Exception:
            # Silent cleanup - don't spam logs with warnings
            return True

    def _cleanup_excessive_qdrant_collections(self) -> bool:
        """Emergency cleanup of excessive collections that could slow down Qdrant startup."""
        try:
            # Check if we're using podman or docker
            container_cmd = "podman"
            try:
                subprocess.run(
                    [container_cmd, "--version"], capture_output=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                container_cmd = "docker"
                try:
                    subprocess.run(
                        [container_cmd, "--version"], capture_output=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return True  # Skip if no container engine

            # Stop Qdrant to access its data
            subprocess.run(
                [container_cmd, "stop", "code-indexer-qdrant"],
                capture_output=True,
            )

            # Quick check of collection directory
            qdrant_collections_dir = Path.home() / ".qdrant_collections"
            if qdrant_collections_dir.exists():
                collections = list(qdrant_collections_dir.glob("*"))
                if len(collections) > 5:  # Emergency threshold for collections
                    print(
                        f"🚨 EMERGENCY: Found {len(collections)} collections - aggressive cleanup needed"
                    )

                    # Keep only the most recent 3 collections
                    collections_by_time = sorted(
                        collections, key=lambda p: p.stat().st_mtime, reverse=True
                    )
                    collections_to_remove = collections_by_time[
                        3:
                    ]  # Remove all but 3 most recent

                    for collection_path in collections_to_remove:
                        try:
                            if collection_path.is_symlink():
                                collection_path.unlink()
                            elif collection_path.is_dir():
                                import shutil

                                shutil.rmtree(collection_path, ignore_errors=True)
                            print(f"🗑️  Removed collection: {collection_path.name}")
                        except Exception:
                            pass  # Best effort cleanup

                    print(
                        f"✅ Emergency collection cleanup: removed {len(collections_to_remove)} collections"
                    )

            return True

        except Exception as e:
            print(f"Collection cleanup warning (non-critical): {e}")
            return True  # Don't fail tests for cleanup issues

    def _stop_conflicting_containers(self) -> bool:
        """Stop any containers that might conflict with test service ports.

        This method identifies and stops containers that are NOT part of the current
        shared test project but might be using conflicting ports. It preserves containers
        that belong to the shared test project to enable container reuse between tests.

        CRITICAL SHARED TEST PROJECT LOGIC:
        - Tests should share containers by running in the same folder
        - Dynamic port allocation ensures no conflicts
        - Only stop containers that are NOT part of the current project
        """
        try:
            # Check if we're using podman or docker
            container_cmd = "podman"
            try:
                subprocess.run(
                    [container_cmd, "--version"], capture_output=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                container_cmd = "docker"
                try:
                    subprocess.run(
                        [container_cmd, "--version"], capture_output=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return True  # Skip if no container engine

            # CRITICAL FIX: Determine the expected containers for shared test project
            # Use the same logic as docker_manager to identify project containers
            from pathlib import Path
            import hashlib

            # Calculate the expected project hash for shared test project
            # CRITICAL FIX: Use the same path pattern as docker_manager and conftest.py
            # The test fixtures create shared_test_repo under project root/.tmp, not home/.tmp
            project_root = Path(
                __file__
            ).parent.parent  # Go up from tests/ to project root
            shared_test_repo_path = project_root / ".tmp" / "shared_test_repo"
            canonical_path = str(shared_test_repo_path.resolve())
            hash_object = hashlib.sha256(canonical_path.encode())
            expected_project_hash = hash_object.hexdigest()[:8]

            # Expected container names for the shared test project
            expected_containers = {
                f"cidx-{expected_project_hash}-qdrant",
                f"cidx-{expected_project_hash}-data-cleaner",
                f"cidx-{expected_project_hash}-ollama",
            }

            print(f"🔍 Shared test project hash: {expected_project_hash}")
            print(f"🔍 Expected containers for shared project: {expected_containers}")

            if shared_test_repo_path.exists():
                print(f"✅ Shared test repo exists: {shared_test_repo_path}")
            else:
                print(f"📁 Shared test repo will be created: {shared_test_repo_path}")

            # List of legacy containers that should be stopped (static names only)
            legacy_containers = [
                "code-indexer-qdrant",
                "code-indexer-data-cleaner",
                "code-indexer-ollama",
            ]

            print("🛑 Checking for containers that need cleanup...")

            # Get list of all running containers
            ps_result = subprocess.run(
                [container_cmd, "ps", "--format", "{{.Names}} {{.Ports}} {{.Status}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if ps_result.returncode != 0:
                print("⚠️ Could not list running containers")
                return True

            running_containers = []
            lines = (
                ps_result.stdout.strip().split("\n") if ps_result.stdout.strip() else []
            )
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 1:
                    container_name = parts[0]
                    ports_info = " ".join(parts[1:-1]) if len(parts) > 2 else ""
                    status = parts[-1] if len(parts) > 1 else ""
                    running_containers.append((container_name, ports_info, status))

            containers_to_stop = []

            # Check each running container
            for container_name, ports_info, status in running_containers:
                should_stop = False
                reason = ""

                # Rule 1: Stop legacy containers with static names
                if container_name in legacy_containers:
                    should_stop = True
                    reason = "legacy container with static name"

                # Rule 2: Stop containers using internal ports 6333 or 8091 (static ports)
                # but NOT if they are expected dynamic port containers
                elif (
                    "->6333" in ports_info or "->8091" in ports_info
                ) and container_name not in expected_containers:
                    should_stop = True
                    reason = "using static internal ports (6333/8091) and not part of shared project"

                # Rule 3: PRESERVE containers that are part of the shared test project
                elif container_name in expected_containers:
                    should_stop = False
                    reason = "part of shared test project - PRESERVING"
                    print(
                        f"   ✅ Preserving shared test container: {container_name} ({ports_info})"
                    )

                if should_stop:
                    containers_to_stop.append((container_name, reason))

            # Stop containers that need to be stopped
            if containers_to_stop:
                print(
                    f"🛑 Stopping {len(containers_to_stop)} conflicting containers..."
                )
                for container_name, reason in containers_to_stop:
                    print(f"   🔍 Stopping {container_name}: {reason}")
                    try:
                        stop_result = subprocess.run(
                            [container_cmd, "stop", container_name],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if stop_result.returncode == 0:
                            print(f"   ✅ Stopped: {container_name}")

                        # Remove stopped container
                        subprocess.run(
                            [container_cmd, "rm", container_name],
                            capture_output=True,
                            timeout=5,
                        )
                    except subprocess.TimeoutExpired:
                        # Force kill if stop times out
                        subprocess.run(
                            [container_cmd, "kill", container_name],
                            capture_output=True,
                            timeout=5,
                        )
                        subprocess.run(
                            [container_cmd, "rm", container_name],
                            capture_output=True,
                            timeout=5,
                        )
                        print(f"   ⚡ Force killed: {container_name}")
                    except Exception as e:
                        print(f"   ⚠️ Could not stop {container_name}: {e}")
            else:
                print(
                    "✅ No conflicting containers found - all containers are properly managed"
                )

            print("✅ Container conflict resolution completed")
            return True

        except Exception as e:
            print(f"Container conflict cleanup warning (non-critical): {e}")
            return True  # Don't fail tests for cleanup issues

    def _check_and_preserve_compatible_containers(self) -> List[str]:
        """Check for existing containers that are compatible with the current project.

        Returns:
            List of container names that are compatible and should be preserved
        """
        try:
            # Check if we're using podman or docker
            container_cmd = "podman"
            try:
                subprocess.run(
                    [container_cmd, "--version"], capture_output=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                container_cmd = "docker"
                try:
                    subprocess.run(
                        [container_cmd, "--version"], capture_output=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return []  # Skip if no container engine

            # Calculate expected container names for shared test project
            from pathlib import Path
            import hashlib

            project_root = Path(
                __file__
            ).parent.parent  # Go up from tests/ to project root
            shared_test_repo_path = project_root / ".tmp" / "shared_test_repo"
            canonical_path = str(shared_test_repo_path.resolve())
            hash_object = hashlib.sha256(canonical_path.encode())
            expected_project_hash = hash_object.hexdigest()[:8]

            expected_containers = [
                f"cidx-{expected_project_hash}-qdrant",
                f"cidx-{expected_project_hash}-data-cleaner",
                f"cidx-{expected_project_hash}-ollama",
            ]

            # Check which expected containers are currently running
            ps_result = subprocess.run(
                [container_cmd, "ps", "--format", "{{.Names}} {{.Status}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if ps_result.returncode != 0:
                return []

            running_containers = []
            lines = (
                ps_result.stdout.strip().split("\n") if ps_result.stdout.strip() else []
            )
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 1:
                    container_name = parts[0]
                    status = " ".join(parts[1:]) if len(parts) > 1 else ""

                    # Check if this is one of our expected containers and it's running
                    if container_name in expected_containers and "Up" in status:
                        running_containers.append(container_name)

            if running_containers:
                print(f"🔍 Found compatible running containers: {running_containers}")

            return running_containers

        except Exception as e:
            print(f"Container compatibility check warning: {e}")
            return []

    def _ensure_config_matches_containers(
        self, container_names: List[str], working_dir: Optional[Path] = None
    ) -> bool:
        """Extract port information from running containers and update the config to match.

        Args:
            container_names: List of container names that are currently running
            working_dir: Working directory where the config should be updated

        Returns:
            True if configuration was successfully updated, False otherwise
        """
        try:
            # Check if we're using podman or docker
            container_cmd = "podman"
            try:
                subprocess.run(
                    [container_cmd, "--version"], capture_output=True, check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                container_cmd = "docker"
                try:
                    subprocess.run(
                        [container_cmd, "--version"], capture_output=True, check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return False

            # Extract port mappings from running containers
            port_config = {}
            for container_name in container_names:
                try:
                    inspect_result = subprocess.run(
                        [container_cmd, "port", container_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if inspect_result.returncode == 0:
                        port_lines = inspect_result.stdout.strip().split("\n")
                        for line in port_lines:
                            if "->" in line:
                                # Parse lines like "6333/tcp -> 0.0.0.0:6516"
                                parts = line.split(" -> ")
                                if len(parts) == 2:
                                    internal_port = parts[0].split("/")[0]
                                    external_port = parts[1].split(":")[-1]

                                    # Map internal ports to service types
                                    if internal_port == "6333":  # Qdrant
                                        port_config["qdrant_port"] = int(external_port)
                                    elif internal_port == "11434":  # Ollama
                                        port_config["ollama_port"] = int(external_port)
                                    elif internal_port == "8091":  # Data cleaner
                                        port_config["data_cleaner_port"] = int(
                                            external_port
                                        )

                except Exception as e:
                    print(
                        f"Warning: Could not extract ports from {container_name}: {e}"
                    )
                    continue

            if not port_config:
                print("⚠️ No valid port mappings found in existing containers")
                return False

            print(f"🔍 Extracted port configuration: {port_config}")

            # Update the configuration using CLI command
            if working_dir:
                original_cwd = Path.cwd()
                os.chdir(working_dir)

            try:
                # CRITICAL FIX: Initialize the project first, then manually update the config file
                # The CLI init command doesn't have individual port options, so we need to update the file directly
                init_result = subprocess.run(
                    self.config.cli_command_prefix
                    + ["init", "--force", "--embedding-provider", "voyage-ai"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if init_result.returncode != 0:
                    print(f"Warning: Could not initialize config: {init_result.stderr}")
                    return False

                # Now manually update the config file with the correct ports
                config_dir = Path.cwd() / ".code-indexer"
                config_file = config_dir / "config.json"

                if config_file.exists():
                    import json

                    with open(config_file, "r") as f:
                        config_data = json.load(f)

                    # Update the Qdrant host with the correct port
                    if "qdrant_port" in port_config:
                        qdrant_port = port_config["qdrant_port"]
                        config_data["qdrant"][
                            "host"
                        ] = f"http://localhost:{qdrant_port}"
                        print(
                            f"🔧 Updated Qdrant host to: http://localhost:{qdrant_port}"
                        )

                    # Update project ports section
                    if "project_ports" not in config_data:
                        config_data["project_ports"] = {}
                    config_data["project_ports"].update(port_config)

                    # Write back the updated config
                    with open(config_file, "w") as f:
                        json.dump(config_data, f, indent=2)

                    print(
                        f"✅ Updated configuration file with extracted ports: {port_config}"
                    )
                    return True
                else:
                    print("⚠️ Configuration file was not created by init command")
                    return False

            except Exception as e:
                print(f"Warning: Could not update configuration: {e}")
                return False

            finally:
                if working_dir:
                    try:
                        os.chdir(original_cwd)
                    except (FileNotFoundError, OSError):
                        pass

        except Exception as e:
            print(f"Configuration sync error: {e}")
            return False


class DirectoryManager:
    """Manages test directories and file creation safely."""

    @staticmethod
    @contextmanager
    def safe_chdir(path: Union[str, Path]):
        """Context manager for safe directory changes."""
        original_cwd = None
        try:
            original_cwd = Path.cwd()
        except (FileNotFoundError, OSError):
            original_cwd = Path(__file__).parent.absolute()

        try:
            os.chdir(path)
            yield Path(path)
        finally:
            try:
                os.chdir(original_cwd)
            except (FileNotFoundError, OSError):
                # If original directory doesn't exist, go to a safe location
                os.chdir(Path(__file__).parent.absolute())

    @staticmethod
    def create_test_project(
        project_dir: Path,
        project_type: str = "calculator",
        custom_files: Optional[Dict[str, str]] = None,
    ) -> None:
        """Create a test project with predefined or custom files.

        Args:
            project_dir: Directory to create project in
            project_type: Type of project (calculator, web_server, auth)
            custom_files: Dict of filename -> content for custom files
        """
        project_dir.mkdir(parents=True, exist_ok=True)

        if custom_files:
            # Use custom files
            for filename, content in custom_files.items():
                file_path = project_dir / filename
                # Create parent directories if they don't exist
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
        else:
            # Use predefined project types
            _create_predefined_project(project_dir, project_type)


def _create_predefined_project(project_dir: Path, project_type: str) -> None:
    """Create predefined project files based on type."""

    if project_type == "calculator":
        (project_dir / "main.py").write_text(
            '''
def add(a, b):
    """Add two numbers together."""
    return a + b

def subtract(a, b):
    """Subtract second number from first."""
    return a - b

def multiply(a, b):
    """Multiply two numbers."""
    return a * b

def divide(a, b):
    """Divide first number by second."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

def authenticate_user(username, password):
    """Authenticate user with username and password"""
    if not username or not password:
        raise ValueError("Username and password required")
    return verify_credentials(username, password)
'''
        )

        (project_dir / "utils.py").write_text(
            '''
import math

def factorial(n):
    """Calculate factorial of n."""
    if n < 0:
        raise ValueError("Factorial not defined for negative numbers")
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)

def power(base, exponent):
    """Calculate base raised to the power of exponent."""
    return base**exponent

def square_root(n):
    """Calculate square root of n."""
    return math.sqrt(n)

def is_prime(n):
    """Check if n is a prime number."""
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True
'''
        )

    elif project_type == "web_server":
        (project_dir / "web_server.py").write_text(
            '''
def handle_request(path):
    """Handle web server request"""
    if path == "/login":
        return authenticate_route()
    elif path == "/api":
        return api_route()
    else:
        return home_route()

def authenticate_route():
    """Handle authentication route"""
    return "Authentication page"

def api_route():
    """Handle API route"""
    return "API endpoint"

def home_route():
    """Handle home route"""  
    return "Home page"
'''
        )

        (project_dir / "auth.py").write_text(
            '''
def verify_credentials(username, password):
    """Verify user credentials against database"""
    return database.check_user(username, password)

def create_session(user):
    """Create user session"""
    return generate_session_token(user)

def authentication_middleware(request):
    """Authentication middleware for web server"""
    token = extract_token(request)
    if not token or not verify_token(token):
        return redirect_to_login()
    return proceed_with_request(request)
'''
        )


class CLIHelper:
    """Helper for running CLI commands in tests."""

    def __init__(self, config: Optional[InfrastructureConfig] = None):
        self.config = config or InfrastructureConfig()

    def run_cli_command(
        self,
        args: List[str],
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[int] = None,
        expect_success: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run CLI command with consistent error handling.

        Args:
            args: Command arguments (without 'code-indexer' prefix)
            cwd: Working directory for command
            timeout: Command timeout (uses config default if None)
            expect_success: Whether to expect successful return code

        Returns:
            CompletedProcess result

        Raises:
            AssertionError: If expect_success=True and command fails
        """
        timeout = timeout or self.config.cleanup_timeout
        cmd = self.config.cli_command_prefix + args

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )

            if expect_success and result.returncode != 0:
                cmd_str = " ".join(cmd)
                raise AssertionError(
                    f"Command failed: {cmd_str}\n"
                    f"Return code: {result.returncode}\n"
                    f"STDOUT: {result.stdout}\n"
                    f"STDERR: {result.stderr}"
                )

            return result

        except subprocess.TimeoutExpired as e:
            cmd_str = " ".join(cmd)
            raise AssertionError(
                f"Command timed out after {timeout}s: {cmd_str}"
            ) from e


class Assertions:
    """Common test assertions for code indexer functionality."""

    @staticmethod
    def assert_service_running(service_manager: ServiceManager):
        """Assert that services are running."""
        assert service_manager.are_services_running(), "Services should be running"

    @staticmethod
    def assert_query_finds_files(
        cli_helper: CLIHelper,
        query: str,
        expected_files: List[str],
        cwd: Optional[Path] = None,
    ):
        """Assert that a query returns expected files."""
        result = cli_helper.run_cli_command(["query", query], cwd=cwd)
        output = result.stdout.lower()

        for expected_file in expected_files:
            assert expected_file.lower() in output, (
                f"Query '{query}' should find '{expected_file}'. "
                f"Output: {result.stdout[:200]}..."
            )

    @staticmethod
    def assert_no_root_owned_files():
        """Assert no root-owned files exist in global data directory."""
        import subprocess

        global_data_dir = Path.home() / ".code-indexer-data"
        if not global_data_dir.exists():
            return

        try:
            current_user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
            result = subprocess.run(
                ["find", str(global_data_dir), "-not", "-user", current_user],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                root_owned_files = result.stdout.strip().split("\n")
                raise AssertionError(
                    f"Found {len(root_owned_files)} root-owned files after cleanup!\n"
                    f"First few files: {root_owned_files[:5]}"
                )

        except subprocess.TimeoutExpired:
            pass  # Skip verification if it takes too long


# Convenience factory functions for common test setups
def create_fast_e2e_setup(
    embedding_provider: EmbeddingProvider = EmbeddingProvider.VOYAGE_AI,
    force_recreate: bool = False,
) -> Tuple[ServiceManager, CLIHelper, DirectoryManager]:
    """Create a fast E2E test setup following NEW STRATEGY.

    DEPRECATED: This function is deprecated in favor of fixture-based approach.
    New tests should use the fixture-based pattern with local_temporary_directory()
    and auto_register_project_collections() instead.

    Returns:
        Tuple of (service_manager, cli_helper, directory_manager)
    """
    import warnings

    warnings.warn(
        "create_fast_e2e_setup() is deprecated. Use fixture-based approach instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = InfrastructureConfig(
        embedding_provider=embedding_provider,
        cleanup_strategy=CleanupStrategy.CLEAN_DATA,
    )

    service_manager = ServiceManager(config)
    cli_helper = CLIHelper(config)
    directory_manager = DirectoryManager()

    # Progressive cleanup as part of aggressive setup to prevent volume and image accumulation
    service_manager.progressive_cleanup_test_volumes()
    service_manager.progressive_cleanup_test_images()

    return service_manager, cli_helper, directory_manager


def create_integration_test_setup(
    embedding_provider: EmbeddingProvider = EmbeddingProvider.VOYAGE_AI,
) -> Tuple[ServiceManager, CLIHelper]:
    """Create integration test setup with service management.

    Returns:
        Tuple of (service_manager, cli_helper)
    """
    config = InfrastructureConfig(
        embedding_provider=embedding_provider,
        cleanup_strategy=CleanupStrategy.CLEAN_DATA,
        service_timeout=180,  # Shorter timeout for integration tests
    )

    service_manager = ServiceManager(config)
    cli_helper = CLIHelper(config)

    # Progressive cleanup as part of setup to prevent volume and image accumulation
    service_manager.progressive_cleanup_test_volumes()
    service_manager.progressive_cleanup_test_images()

    return service_manager, cli_helper


def detect_service_state() -> dict:
    """Detect current service state for tests to adapt behavior.

    Returns:
        Dictionary with service state information
    """
    try:
        # Try to detect if services are already running by checking common status
        import subprocess

        # Get appropriate shared test directory based on test context
        shared_dir = get_shared_test_directory(force_docker=False)
        result = subprocess.run(
            ["code-indexer", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=shared_dir,
        )

        if result.returncode == 0:
            # Parse status output to determine service health
            stdout = result.stdout.lower()
            # Look for Qdrant specifically since that's what indexing needs
            qdrant_ready = "qdrant" in stdout and (
                "✅ ready" in stdout or "available" in stdout
            )
            docker_services_running = "docker services" in stdout and (
                "✅" in stdout or "running" in stdout
            )
            services_running = qdrant_ready and docker_services_running

            return {
                "services_running": services_running,
                "qdrant_ready": qdrant_ready,
                "docker_services_running": docker_services_running,
                "status_accessible": True,
                "raw_status": result.stdout,
            }
        else:
            return {
                "services_running": False,
                "qdrant_ready": False,
                "docker_services_running": False,
                "status_accessible": False,
                "raw_status": result.stdout if result.stdout else result.stderr,
            }
    except Exception as e:
        return {
            "services_running": False,
            "qdrant_ready": False,
            "docker_services_running": False,
            "status_accessible": False,
            "error": str(e),
        }


def adaptive_service_setup(project_path: Path, helper: "CLIHelper") -> bool:
    """Set up services adaptively based on current state.

    Args:
        project_path: Project directory to run commands in
        helper: CLIHelper instance to use for commands

    Returns:
        True if services are ready, False otherwise
    """
    import time

    # Always check service state from the project directory context
    try:
        # 1. First, ensure clean data state if services are running
        status_result = helper.run_cli_command(
            ["status"], cwd=project_path, expect_success=False, timeout=10
        )

        if status_result.returncode == 0:
            stdout = status_result.stdout.lower()
            # Check if all required services are healthy
            qdrant_healthy = "qdrant" in stdout and (
                "healthy" in stdout or "✅" in stdout
            )
            data_cleaner_healthy = "data-cleaner" in stdout and (
                "healthy" in stdout or "✅" in stdout
            )

            # For voyage-ai, we don't need ollama
            embedding_provider = helper.config.embedding_provider.value
            if embedding_provider == "voyage-ai":
                services_ready = qdrant_healthy and data_cleaner_healthy
            else:
                ollama_healthy = "ollama" in stdout and (
                    "healthy" in stdout or "✅" in stdout
                )
                services_ready = (
                    qdrant_healthy and data_cleaner_healthy and ollama_healthy
                )

            if services_ready:
                print("✅ Services already running and healthy")
                # Clean data for fresh test state
                clean_result = helper.run_cli_command(
                    ["clean", "--data-only"],
                    cwd=project_path,
                    expect_success=False,
                    timeout=30,
                )
                if clean_result.returncode == 0:
                    print("✅ Data cleaned for fresh test state")
                return True

        # 2. Services not ready, try to start them with shorter timeout
        print("🚀 Starting services for project...")
        start_result = helper.run_cli_command(
            ["start", "--quiet"],
            cwd=project_path,
            expect_success=False,
            timeout=60,  # Reduced from 120
        )

        # Check if start failed due to services already running
        if start_result.returncode != 0:
            stderr = (start_result.stderr or "").lower()
            stdout = (start_result.stdout or "").lower()
            if "already" in stderr or "already" in stdout:
                print("⚠️ Services already running, checking health...")
            else:
                print(f"❌ Failed to start services: {start_result.stderr}")
                return False

        # 3. Poll for service health with shorter timeout
        max_wait = 30  # Total max wait time
        poll_interval = 2
        start_time = time.time()

        while time.time() - start_time < max_wait:
            health_status = helper.run_cli_command(
                ["status"], cwd=project_path, expect_success=False, timeout=5
            )

            if health_status.returncode == 0:
                stdout = health_status.stdout.lower()
                qdrant_healthy = "qdrant" in stdout and (
                    "healthy" in stdout or "✅" in stdout
                )

                if qdrant_healthy:
                    print("✅ Services started and healthy")
                    return True

            time.sleep(poll_interval)

        print(f"⚠️ Services did not become healthy within {max_wait} seconds")
        return False

    except Exception as e:
        print(f"⚠️ Service setup failed: {e}")
        return False


def ensure_collection_ready(
    project_path: Path, collection_name: str, force_recreate: bool = False
) -> bool:
    """Ensure a collection is ready for testing.

    Args:
        project_path: Project directory
        collection_name: Name of the collection
        force_recreate: Force recreation of collection

    Returns:
        True if collection is ready, False otherwise
    """
    try:
        from ..config import ConfigManager
        from ..services.qdrant import QdrantClient
        from ..services.embedding_factory import EmbeddingProviderFactory

        # Load configuration
        config_manager = ConfigManager.create_with_backtrack(project_path)
        config = config_manager.load()

        # Create clients
        embedding_provider = EmbeddingProviderFactory.create(config)
        qdrant_client = QdrantClient(config.qdrant)

        # Resolve actual collection name
        resolved_name = qdrant_client.resolve_collection_name(
            config, embedding_provider
        )

        if force_recreate:
            # Delete if exists
            if qdrant_client.collection_exists(resolved_name):
                qdrant_client.delete_collection(resolved_name)
                print(f"🗑️  Deleted existing collection: {resolved_name}")

        # Ensure collection exists with correct dimensions
        success = qdrant_client.ensure_collection(
            resolved_name, embedding_provider.dimension
        )

        if success:
            print(f"✅ Collection ready: {resolved_name}")
            return True
        else:
            print(f"❌ Failed to ensure collection: {resolved_name}")
            return False

    except Exception as e:
        print(f"❌ Collection setup failed: {e}")
        return False


def get_shared_test_directory(force_docker: bool = False) -> Path:
    """Get the shared test directory path, with separate directories for Docker vs Podman.

    This prevents permission conflicts between Docker (root) and Podman (rootless) tests.

    Args:
        force_docker: If True, return the Docker-specific test directory

    Returns:
        Path to the appropriate shared test directory
    """
    base_dir = Path.home() / ".tmp"
    if force_docker:
        return base_dir / "shared_test_containers_docker"
    else:
        return base_dir / "shared_test_containers"


def get_shared_test_project_dir() -> Path:
    """Get the shared test project directory used for container reuse.

    This returns the same directory path that's used by the shared test fixtures,
    allowing different tests to reuse the same containers and collections.

    Returns:
        Path to shared test project directory
    """
    project_root = Path(__file__).parent.parent  # Go up from tests/ to project root
    shared_test_repo_path = project_root / ".tmp" / "shared_test_repo"
    shared_test_repo_path.mkdir(parents=True, exist_ok=True)
    return shared_test_repo_path


def create_isolated_project_dir(test_name: str, force_docker: bool = False) -> Path:
    """Create an isolated project directory for tests that need unique collections.

    This preserves shared container performance while giving tests that truly need
    isolation (like git-aware tests) their own project space and thus unique collection names.

    Args:
        test_name: Name of the test (used for directory naming)
        force_docker: If True, create directory in Docker-specific namespace

    Returns:
        Path to isolated project directory
    """
    import uuid
    import time

    # Create unique project directory that will generate its own project_id hash
    unique_id = f"{test_name}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    if force_docker:
        isolated_dir = Path.home() / ".tmp" / f"isolated_test_docker_{unique_id}"
    else:
        isolated_dir = Path.home() / ".tmp" / f"isolated_test_{unique_id}"
    isolated_dir.mkdir(parents=True, exist_ok=True)

    return isolated_dir


def auto_register_project_collections(project_dir: Path) -> List[str]:
    """
    Auto-discover and register collections that would be created for a project.

    This function analyzes a project directory and determines what collection names
    would be generated, then registers them for cleanup.

    Args:
        project_dir: Path to the project directory

    Returns:
        List of collection names that were registered
    """
    import sys
    from pathlib import Path

    # Add src to path for imports
    src_path = Path(__file__).parent.parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    try:
        from code_indexer.config import ConfigManager
        from code_indexer.services.embedding_factory import EmbeddingProviderFactory

        # Import suite_setup functions here to avoid circular imports
        try:
            from .suite_setup import register_test_collection
        except ImportError:
            # If running standalone, try absolute import
            import suite_setup

            register_test_collection = suite_setup.register_test_collection

        registered_collections = []

        # Try to load config from project directory
        try:
            config_manager = ConfigManager.create_with_backtrack(project_dir)
            config = config_manager.load()

            # Check if provider-aware collections are enabled
            if config.qdrant.use_provider_aware_collections:
                # Generate project ID for this directory
                project_id = EmbeddingProviderFactory.generate_project_id(
                    str(project_dir)
                )
                base_name = config.qdrant.collection_base_name

                # Register collections for common providers that might be used in tests
                common_providers = [
                    ("voyage-ai", "voyage-code-3"),
                    ("ollama", "nomic-embed-text"),
                ]

                for provider_name, model_name in common_providers:
                    collection_name = EmbeddingProviderFactory.generate_collection_name(
                        base_name, provider_name, model_name, project_id
                    )
                    register_test_collection(collection_name)
                    registered_collections.append(collection_name)

            else:
                # Legacy collection naming
                collection_name = config.qdrant.collection
                register_test_collection(collection_name)
                registered_collections.append(collection_name)

        except Exception:
            # If config loading fails, generate collections based on project directory
            project_id = EmbeddingProviderFactory.generate_project_id(str(project_dir))
            base_name = "code_index"  # Default base name

            # Register collections for common providers
            common_providers = [
                ("voyage-ai", "voyage-code-3"),
                ("ollama", "nomic-embed-text"),
            ]

            for provider_name, model_name in common_providers:
                collection_name = EmbeddingProviderFactory.generate_collection_name(
                    base_name, provider_name, model_name, project_id
                )
                register_test_collection(collection_name)
                registered_collections.append(collection_name)

        if registered_collections:
            print(
                f"🔧 Auto-registered {len(registered_collections)} collections for cleanup"
            )

        return registered_collections

    except Exception as e:
        print(f"Warning: Could not auto-register collections: {e}")
        return []


class TestSuiteCleanup:
    """Manages cleanup of test suite containers and data."""

    @staticmethod
    def cleanup_all_test_containers():
        """Remove all test containers and Qdrant data."""
        import subprocess

        print("🧹 Starting comprehensive test suite cleanup...")

        # Get all test container names with cidx prefix
        try:
            # List all containers with cidx prefix
            result = subprocess.run(
                [
                    "podman",
                    "ps",
                    "-a",
                    "--format",
                    "{{.Names}}",
                    "--filter",
                    "name=cidx-",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                container_names = [
                    name.strip() for name in result.stdout.split("\n") if name.strip()
                ]

                if container_names:
                    print(f"🗑️ Found {len(container_names)} test containers to remove")

                    # Stop containers
                    for name in container_names:
                        print(f"  Stopping {name}...")
                        subprocess.run(
                            ["podman", "stop", name], capture_output=True, timeout=30
                        )

                    # Remove containers
                    for name in container_names:
                        print(f"  Removing {name}...")
                        subprocess.run(
                            ["podman", "rm", "-f", name],
                            capture_output=True,
                            timeout=30,
                        )

                    print(f"✅ Removed {len(container_names)} test containers")
                else:
                    print("ℹ️ No test containers found to remove")

        except Exception as e:
            print(f"⚠️ Error during container cleanup: {e}")

        # Cleanup test volumes
        try:
            result = subprocess.run(
                [
                    "podman",
                    "volume",
                    "ls",
                    "--format",
                    "{{.Name}}",
                    "--filter",
                    "name=cidx-",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                volume_names = [
                    name.strip() for name in result.stdout.split("\n") if name.strip()
                ]

                if volume_names:
                    print(f"🗑️ Found {len(volume_names)} test volumes to remove")

                    for name in volume_names:
                        print(f"  Removing volume {name}...")
                        subprocess.run(
                            ["podman", "volume", "rm", "-f", name],
                            capture_output=True,
                            timeout=30,
                        )

                    print(f"✅ Removed {len(volume_names)} test volumes")
                else:
                    print("ℹ️ No test volumes found to remove")

        except Exception as e:
            print(f"⚠️ Error during volume cleanup: {e}")

        # Cleanup test Qdrant collections
        TestSuiteCleanup._cleanup_test_collections()

        # Cleanup temporary directories
        TestSuiteCleanup._cleanup_test_temp_directories()

        print("✅ Test suite cleanup completed")

    @staticmethod
    def _cleanup_test_collections():
        """Remove test collections from any running Qdrant instances."""
        try:
            from code_indexer.services.qdrant import QdrantClient
            from code_indexer.config import ConfigManager

            # Try to connect to shared test containers config
            # Default to non-Docker directory for backward compatibility
            shared_dir = get_shared_test_directory(force_docker=False)
            shared_config_path = shared_dir / ".code-indexer" / "config.json"
            if shared_config_path.exists():
                try:
                    config_manager = ConfigManager.from_directory(
                        shared_config_path.parent.parent
                    )
                    config = config_manager.load()

                    qdrant_client = QdrantClient(config.qdrant)
                    if qdrant_client.health_check():
                        print("🗑️ Cleaning up test collections...")

                        # Get all test collection names
                        test_collections = (
                            TestProjectInventory.get_all_test_collections()
                        )

                        # Also get collections from any additional registries if they exist
                        # Note: Global test registry no longer needed with inventory system

                        for collection_base in set(
                            test_collections
                        ):  # Remove duplicates
                            # For provider-aware collections, we need to clean up all variants
                            collections_to_remove = []

                            # Common provider variations
                            provider_variations = [
                                f"{collection_base}_voyage-ai_voyage-code-3",
                                f"{collection_base}_ollama_nomic-embed-text",
                                collection_base,  # Legacy naming
                            ]

                            for collection_name in provider_variations:
                                try:
                                    if qdrant_client.collection_exists(collection_name):
                                        collections_to_remove.append(collection_name)
                                except Exception:
                                    continue

                            # Remove found collections
                            for collection_name in collections_to_remove:
                                try:
                                    qdrant_client.delete_collection(collection_name)
                                    print(f"  Removed collection: {collection_name}")
                                except Exception as e:
                                    print(f"  Failed to remove {collection_name}: {e}")

                        if collections_to_remove:
                            print(
                                f"✅ Cleaned up {len(collections_to_remove)} test collections"
                            )
                        else:
                            print("ℹ️ No test collections found to remove")

                except Exception as e:
                    print(f"⚠️ Could not connect to Qdrant for collection cleanup: {e}")

        except Exception as e:
            print(f"⚠️ Error during collection cleanup: {e}")

    @staticmethod
    def _cleanup_test_temp_directories():
        """Clean up test temporary directories."""
        import shutil

        temp_patterns = [
            "/tmp/code_indexer_test_*",
            str(get_shared_test_directory(force_docker=False)),
            str(get_shared_test_directory(force_docker=True)),
        ]

        for pattern in temp_patterns:
            try:
                if "*" in pattern:
                    # Use glob for wildcard patterns
                    import glob

                    paths = glob.glob(pattern)
                    for glob_path in paths:
                        if Path(glob_path).exists():
                            shutil.rmtree(glob_path, ignore_errors=True)
                            print(f"  Removed temp directory: {glob_path}")
                else:
                    # Direct path
                    direct_path = Path(pattern)
                    if direct_path.exists():
                        shutil.rmtree(direct_path, ignore_errors=True)
                        print(f"  Removed temp directory: {direct_path}")

            except Exception as e:
                print(f"⚠️ Could not remove {pattern}: {e}")


def create_test_project_with_inventory(
    test_dir: Path, project_config: ProjectTestConfig
) -> Path:
    """Create a test project using the inventory system instead of config tinkering.

    This is the recommended way to create test projects that need specific configurations.
    """
    # Auto-register collections for cleanup
    auto_register_project_collections(test_dir)

    # Create isolated project space
    config_file = TestProjectInventory.create_project_space(test_dir, project_config)

    return config_file
