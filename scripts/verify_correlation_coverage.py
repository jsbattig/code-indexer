#!/usr/bin/env python3
"""
Verify correlation_id coverage in logging calls.

Provides detailed report of which logging calls are missing correlation_id.
Story #666 - AC3, AC4, AC5
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple

# Display constants
MAX_CALL_TEXT_LENGTH = 200  # Maximum chars to capture from call for storage
MAX_DISPLAY_TEXT_LENGTH = 100  # Maximum chars to display in output
MAX_FILES_TO_DISPLAY = 20  # Maximum number of files to show in summary
SEPARATOR_WIDTH = 70  # Width of separator lines in output

# Logging method names to check
LOGGING_METHODS = ("info", "warning", "error", "exception", "debug", "critical")


class LoggingCallVisitor(ast.NodeVisitor):
    """AST visitor to find logger calls."""

    def __init__(self, source_lines: List[str]):
        """Initialize visitor."""
        self.source_lines = source_lines
        self.calls = []

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function call nodes."""
        self.generic_visit(node)

        # Early returns to reduce nesting
        if not isinstance(node.func, ast.Attribute):
            return
        if not isinstance(node.func.value, ast.Name):
            return
        if node.func.value.id != "logger":
            return

        method = node.func.attr
        if method not in LOGGING_METHODS:
            return

        # Check if has correlation_id in extra parameter
        has_correlation_id = self._has_correlation_id(node)

        # Get call text
        line_start = node.lineno
        line_end = node.end_lineno or line_start
        call_text = "\n".join(self.source_lines[line_start - 1 : line_end])

        self.calls.append(
            {
                "line": line_start,
                "method": method,
                "has_correlation_id": has_correlation_id,
                "text": call_text[:MAX_CALL_TEXT_LENGTH],
            }
        )

    def _has_correlation_id(self, node: ast.Call) -> bool:
        """Check if call has correlation_id in extra parameter."""
        for keyword in node.keywords:
            if keyword.arg == "extra":
                # Check if extra dict contains correlation_id
                if isinstance(keyword.value, ast.Dict):
                    for key in keyword.value.keys:
                        if isinstance(key, ast.Constant):
                            if key.value == "correlation_id":
                                return True
        return False


def analyze_file(file_path: Path) -> Tuple[int, int, List[dict]]:
    """
    Analyze a Python file for logging call correlation_id coverage.

    Args:
        file_path: Path to Python file

    Returns:
        Tuple of (total_calls, covered_calls, uncovered_calls_list)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        source_lines = source.split("\n")
        tree = ast.parse(source)
        visitor = LoggingCallVisitor(source_lines)
        visitor.visit(tree)

        uncovered = [call for call in visitor.calls if not call["has_correlation_id"]]
        total = len(visitor.calls)
        covered = total - len(uncovered)

        return total, covered, uncovered

    except SyntaxError as e:
        # Skip files with syntax errors (e.g., invalid Python syntax)
        print(f"Warning: Skipping {file_path} - syntax error: {e}", file=sys.stderr)
        return 0, 0, []
    except Exception as e:
        # Skip files that cannot be processed for any other reason
        print(f"Warning: Skipping {file_path} - error: {e}", file=sys.stderr)
        return 0, 0, []


def parse_arguments():
    """Parse command-line arguments."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify correlation_id coverage")
    parser.add_argument(
        "--detailed", action="store_true", help="Show detailed output per file"
    )
    parser.add_argument(
        "files", nargs="*", help="Files to check (default: all server files)"
    )

    return parser.parse_args()


def get_files_to_check(args) -> List[Path]:
    """Determine which files to check based on arguments."""
    if args.files:
        return [Path(f) for f in args.files if Path(f).exists()]

    # Default: all server Python files
    server_dir = Path(__file__).parent.parent / "src" / "code_indexer" / "server"
    return list(server_dir.rglob("*.py"))


def print_summary(total_calls: int, total_covered: int, files_with_issues: List[Tuple]):
    """Print coverage summary."""
    print("\n" + "=" * SEPARATOR_WIDTH)
    print("CORRELATION ID COVERAGE SUMMARY")
    print("=" * SEPARATOR_WIDTH)
    print(f"Total logging calls:     {total_calls}")
    print(f"Calls with correlation:  {total_covered}")
    print(f"Calls without correlation: {total_calls - total_covered}")

    if total_calls > 0:
        coverage_pct = (total_covered / total_calls) * 100
        print(f"Coverage:                {coverage_pct:.1f}%")

    if files_with_issues:
        print(f"\nFiles needing fixes: {len(files_with_issues)}")
        files_with_issues.sort(key=lambda x: x[0], reverse=True)
        for count, file_path, _ in files_with_issues[:MAX_FILES_TO_DISPLAY]:
            print(f"  {count:4d} calls - {file_path}")
        if len(files_with_issues) > MAX_FILES_TO_DISPLAY:
            remaining = len(files_with_issues) - MAX_FILES_TO_DISPLAY
            print(f"  ... and {remaining} more files")
    else:
        print("\n100% COVERAGE ACHIEVED!")

    print("=" * SEPARATOR_WIDTH)


def main():
    """Main entry point."""
    args = parse_arguments()
    file_paths = get_files_to_check(args)

    total_calls = 0
    total_covered = 0
    files_with_issues = []

    # Analyze each file
    for file_path in sorted(file_paths):
        file_total, file_covered, uncovered_calls = analyze_file(file_path)

        if file_total == 0:
            continue

        total_calls += file_total
        total_covered += file_covered

        if uncovered_calls:
            rel_path = (
                file_path.relative_to(Path.cwd())
                if Path.cwd() in file_path.parents
                else file_path
            )
            files_with_issues.append((len(uncovered_calls), rel_path, uncovered_calls))

            if args.detailed:
                print(
                    f"\n{rel_path}: {len(uncovered_calls)}/{file_total} calls missing correlation_id"
                )
                for call in uncovered_calls:
                    print(f"  Line {call['line']}: logger.{call['method']}(...)")
                    print(f"    {call['text'][:MAX_DISPLAY_TEXT_LENGTH]}...")

    print_summary(total_calls, total_covered, files_with_issues)

    # Exit with error if not 100% coverage
    sys.exit(0 if total_calls == total_covered else 1)


if __name__ == "__main__":
    main()
