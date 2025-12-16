"""Integration test for CLI callchain command performance.

Verifies that CLI callchain uses fast database primitive (not slow BFS composite)
and completes in <1 second (not 21 seconds).
"""

import time
from click.testing import CliRunner


def test_callchain_uses_fast_database_primitive():
    """
    Verify CLI callchain uses fast database primitive, not slow BFS composite.

    Requirements:
    - Execution time < 1 second (not 21 seconds)
    - Successful command execution (exit code 0)
    - Output contains expected chain result format

    Test data:
    - Assumes code-indexer repo with SCIP indexes already generated
    - Uses real symbols: DaemonService -> _is_text_file
    """
    from src.code_indexer.cli import cli

    runner = CliRunner()

    # Time the execution
    start = time.perf_counter()
    result = runner.invoke(
        cli,
        ['scip', 'callchain', 'DaemonService', '_is_text_file', '--max-depth', '5']
    )
    elapsed = time.perf_counter() - start

    # Verify performance requirement
    assert elapsed < 1.0, (
        f"CLI callchain took {elapsed:.2f}s, expected <1s. "
        f"Likely using slow BFS composite instead of fast database primitive."
    )

    # Verify successful execution
    assert result.exit_code == 0, (
        f"Command failed with exit code {result.exit_code}\n"
        f"Output:\n{result.output}"
    )

    # Verify output format (at least one chain found)
    assert 'call chain' in result.output.lower(), (
        f"Expected 'call chain' in output, got:\n{result.output}"
    )
