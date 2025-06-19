"""
Setup script for E2E tests with real API integration.

This script helps configure and validate the environment for running
E2E tests with real API tokens.
"""

import os
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add parent directory to path so we can import code_indexer modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from code_indexer.config import Config
from code_indexer.services.embedding_factory import EmbeddingProviderFactory


def check_environment():
    """Check if the environment is properly configured for E2E tests."""
    console = Console()
    console.print("\n[bold blue]Code Indexer E2E Test Environment Check[/bold blue]\n")

    # Create status table
    table = Table(title="Environment Status")
    table.add_column("Component", style="bold")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    # Check Python environment
    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    table.add_row("Python", "✓ Available", f"Version {python_version}")

    # Check VoyageAI API Key
    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    if voyage_api_key:
        # Mask the key for security
        masked_key = (
            voyage_api_key[:8] + "..." + voyage_api_key[-4:]
            if len(voyage_api_key) > 12
            else "***"
        )
        table.add_row("VoyageAI API Key", "✓ Available", f"Key: {masked_key}")
    else:
        table.add_row(
            "VoyageAI API Key", "⚠ Missing", "Set VOYAGE_API_KEY environment variable"
        )

    # Check if Ollama might be available (local testing)
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    table.add_row("Ollama Host", "📍 Configured", f"Host: {ollama_host}")

    # Check if Qdrant might be available (local testing)
    qdrant_host = os.getenv("QDRANT_HOST", "http://localhost:6333")
    table.add_row("Qdrant Host", "📍 Configured", f"Host: {qdrant_host}")

    console.print(table)
    console.print()

    return voyage_api_key is not None


def test_voyage_ai_connection():
    """Test connection to VoyageAI API."""
    console = Console()

    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    if not voyage_api_key:
        console.print(
            "[red]❌ VoyageAI API key not found. Set VOYAGE_API_KEY environment variable.[/red]"
        )
        return False

    try:
        console.print("[yellow]Testing VoyageAI connection...[/yellow]")

        # Create VoyageAI configuration
        config = Config()
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-3"

        # Create provider and test connection
        provider = EmbeddingProviderFactory.create(config, console)

        if provider.health_check():
            console.print("[green]✓ VoyageAI connection successful[/green]")

            # Test a simple embedding
            test_embedding = provider.get_embedding("def test_function():")
            console.print(
                f"[green]✓ Test embedding generated ({len(test_embedding)} dimensions)[/green]"
            )

            # Get model info
            model_info = provider.get_model_info()
            console.print(
                f"[green]✓ Model: {model_info['name']} ({model_info['dimensions']} dimensions)[/green]"
            )

            return True
        else:
            console.print("[red]❌ VoyageAI health check failed[/red]")
            return False

    except Exception as e:
        console.print(f"[red]❌ VoyageAI connection error: {e}[/red]")
        return False


def run_e2e_tests():
    """Run the E2E tests with proper environment setup."""
    console = Console()

    console.print("\n[bold blue]Running Code Indexer E2E Tests[/bold blue]\n")

    # Check environment first
    env_ok = check_environment()

    if not env_ok:
        console.print(
            "\n[yellow]⚠ Some environment checks failed. E2E tests may be limited.[/yellow]"
        )
        console.print("\n[bold]To run full VoyageAI tests:[/bold]")
        console.print("1. Get a VoyageAI API key from https://www.voyageai.com/")
        console.print(
            "2. Set the environment variable: export VOYAGE_API_KEY='your_key_here'"
        )
        console.print("3. Run this script again")

    # Test VoyageAI connection if available
    voyage_available = test_voyage_ai_connection()

    console.print("\n[bold]Available E2E Test Categories:[/bold]")

    if voyage_available:
        console.print("✓ VoyageAI Real API Tests")
        console.print("✓ Provider Switching Tests")
        console.print("✓ Full Workflow Tests")
    else:
        console.print("⚠ VoyageAI Real API Tests (skipped - no API key)")
        console.print("✓ Provider Switching Tests (limited)")
        console.print("⚠ Full Workflow Tests (limited)")

    console.print("✓ Qdrant Integration Tests")
    console.print("✓ Factory and Configuration Tests")

    # Run pytest with specific E2E test file
    console.print("\n[bold]Running pytest for E2E tests...[/bold]")

    try:
        import subprocess

        test_file = Path(__file__).parent / "test_e2e_embedding_providers.py"
        cmd = ["python", "-m", "pytest", str(test_file), "-v", "-s"]

        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]\n")

        result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)

        if result.returncode == 0:
            console.print("\n[green]✓ All available E2E tests passed![/green]")
        else:
            console.print(
                f"\n[red]❌ Some E2E tests failed (exit code: {result.returncode})[/red]"
            )

        return result.returncode == 0

    except Exception as e:
        console.print(f"\n[red]❌ Error running E2E tests: {e}[/red]")
        return False


def show_setup_guide():
    """Show setup guide for E2E tests."""
    console = Console()

    guide_text = """
[bold blue]E2E Test Setup Guide[/bold blue]

[bold]1. VoyageAI API Key Setup[/bold]
   • Sign up at https://www.voyageai.com/
   • Get your API key from the dashboard
   • Set environment variable:
     
     [code]export VOYAGE_API_KEY="your_api_key_here"[/code]
   
   • For permanent setup, add to your shell config:
     
     [code]echo 'export VOYAGE_API_KEY="your_key"' >> ~/.bashrc[/code]

[bold]2. Running E2E Tests[/bold]
   • Full test suite: [code]python tests/e2e_test_setup.py[/code]
   • Specific tests: [code]pytest tests/test_e2e_embedding_providers.py -v[/code]
   • With API key only: [code]pytest tests/test_e2e_embedding_providers.py::TestVoyageAIRealAPI -v[/code]

[bold]3. Test Categories[/bold]
   • [green]TestVoyageAIRealAPI[/green]: Real API integration tests (requires VOYAGE_API_KEY)
   • [green]TestE2EProviderSwitching[/green]: Provider switching and compatibility
   • [green]TestE2EQdrantIntegration[/green]: Qdrant model metadata integration
   • [green]TestE2EFullWorkflow[/green]: Complete workflow scenarios

[bold]4. Environment Variables[/bold]
   • [code]VOYAGE_API_KEY[/code]: VoyageAI API key (required for VoyageAI tests)
   • [code]OLLAMA_HOST[/code]: Ollama server URL (default: http://localhost:11434)
   • [code]QDRANT_HOST[/code]: Qdrant server URL (default: http://localhost:6333)

[bold]5. Local Services (Optional)[/bold]
   If you want to test with local services:
   • Start Ollama: [code]docker run -d -p 11434:11434 ollama/ollama[/code]
   • Start Qdrant: [code]docker run -d -p 6333:6333 qdrant/qdrant[/code]
"""

    panel = Panel(guide_text, title="E2E Test Setup", border_style="blue")
    console.print(panel)


def main():
    """Main entry point for E2E test setup."""
    console = Console()

    if len(sys.argv) > 1:
        if sys.argv[1] == "check":
            check_environment()
        elif sys.argv[1] == "test-voyage":
            test_voyage_ai_connection()
        elif sys.argv[1] == "run":
            run_e2e_tests()
        elif sys.argv[1] == "guide":
            show_setup_guide()
        else:
            console.print(f"[red]Unknown command: {sys.argv[1]}[/red]")
            console.print("Available commands: check, test-voyage, run, guide")
    else:
        # Default: run full setup and tests
        show_setup_guide()
        console.print("\n" + "=" * 60 + "\n")
        run_e2e_tests()


if __name__ == "__main__":
    main()
