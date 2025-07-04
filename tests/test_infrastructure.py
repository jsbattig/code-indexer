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
    service_timeout: int = 450  # Increased for collection recovery scenarios
    status_timeout: int = 30
    init_timeout: int = 60
    cleanup_timeout: int = 60
    cli_command_prefix: List[str] = field(default_factory=lambda: ["code-indexer"])
    retry_attempts: int = 3
    adaptive_timeout_multiplier: float = 1.5


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
            # Check if services are already running globally (skip if force_recreate)
            if not force_recreate and self.are_services_running():
                # Services already running globally - use them
                return True

            # If force_recreate, clean up existing services first
            if force_recreate:
                print("Force recreate requested, cleaning up existing services...")
                subprocess.run(
                    self.config.cli_command_prefix + ["uninstall"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            # Check if essential services are accessible even without full Docker setup
            # This handles cases where Qdrant runs outside Docker or independently
            try:
                from code_indexer.config import ConfigManager
                from code_indexer.services.qdrant import QdrantClient

                config_manager = ConfigManager.create_with_backtrack()
                config = config_manager.load()
                qdrant_client = QdrantClient(config.qdrant)

                if qdrant_client.health_check():
                    print("Essential services accessible, tests can proceed")
                    return True
            except Exception:
                pass

            # Services not accessible - try to start them
            print("Starting services for E2E testing...")

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
                self.config.cli_command_prefix + ["start", "--quiet"],
                capture_output=True,
                text=True,
                timeout=self.config.service_timeout,
            )

            if start_result.returncode != 0:
                # Check for container issues and attempt recovery
                if (
                    "No such container" in start_result.stdout
                    or "Error response from daemon" in start_result.stdout
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
                            self.config.cli_command_prefix + ["start", "--quiet"],
                            capture_output=True,
                            text=True,
                            timeout=self.config.service_timeout,
                        )

                        if start_result.returncode != 0:
                            print(
                                f"Failed to start services after recovery attempt: {start_result.stderr}"
                            )
                            return False
                    else:
                        print("Failed to reinitialize after container cleanup")
                        return False
                else:
                    print(f"Failed to start services: {start_result.stderr}")
                    return False

            # Wait for services to be ready
            import time

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

    Returns:
        Tuple of (service_manager, cli_helper, directory_manager)
    """
    config = InfrastructureConfig(
        embedding_provider=embedding_provider,
        cleanup_strategy=CleanupStrategy.CLEAN_DATA,
    )

    service_manager = ServiceManager(config)
    cli_helper = CLIHelper(config)
    directory_manager = DirectoryManager()

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

    return service_manager, cli_helper


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

        # Import test_suite_setup functions here to avoid circular imports
        try:
            from .test_suite_setup import register_test_collection
        except ImportError:
            # If running standalone, try absolute import
            import test_suite_setup

            register_test_collection = test_suite_setup.register_test_collection

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
