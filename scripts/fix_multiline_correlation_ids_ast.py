#!/usr/bin/env python3
"""
AST-based script to fix multi-line logging calls with correlation IDs.
Uses proper AST parsing to ensure correct syntax insertion.
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple


def find_logging_calls_needing_fix(file_path: Path) -> List[Tuple[int, int]]:
    """Find logging calls that need correlation_id added.

    Returns list of (lineno, end_lineno) tuples for calls needing fixes.
    """
    try:
        content = file_path.read_text()
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"  ❌ Syntax error parsing {file_path.name}: {e}")
        return []

    calls_to_fix = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check if it's a logger call
            if isinstance(node.func, ast.Attribute):
                if (
                    node.func.attr
                    in ["error", "warning", "exception", "info", "debug", "critical"]
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "logger"
                ):
                    # Check if it already has correlation_id
                    has_correlation = False
                    for keyword in node.keywords:
                        if keyword.arg == "extra":
                            # Check if extra contains correlation_id
                            if isinstance(keyword.value, ast.Dict):
                                for key in keyword.value.keys:
                                    if (
                                        isinstance(key, ast.Constant)
                                        and key.value == "correlation_id"
                                    ):
                                        has_correlation = True
                                        break

                    if (
                        not has_correlation
                        and hasattr(node, "lineno")
                        and hasattr(node, "end_lineno")
                    ):
                        calls_to_fix.append((node.lineno, node.end_lineno))

    return calls_to_fix


def fix_logging_call(lines: List[str], start_line: int, end_line: int) -> List[str]:
    """Fix a single logging call by adding correlation_id.

    Args:
        lines: All lines in the file (0-indexed)
        start_line: Starting line number (1-indexed from AST)
        end_line: Ending line number (1-indexed from AST)

    Returns:
        Modified lines
    """
    # Convert to 0-indexed
    start_idx = start_line - 1
    end_idx = end_line - 1

    # Find the closing parenthesis line
    closing_paren_idx = end_idx
    closing_line = lines[closing_paren_idx]

    # Find the position of the closing parenthesis
    paren_pos = closing_line.rfind(")")
    if paren_pos == -1:
        return lines  # Can't find closing paren, skip

    # Get the indentation of the last parameter line (line before closing paren)
    # or the indentation of arguments if closing paren is on same line
    if closing_paren_idx > start_idx:
        # Multi-line call - get indentation from previous line
        prev_line = lines[closing_paren_idx - 1]
        indent = len(prev_line) - len(prev_line.lstrip())

        # Check if previous line ends with a comma
        stripped_prev = prev_line.rstrip()
        if not stripped_prev.endswith(","):
            # Add comma to previous line
            lines[closing_paren_idx - 1] = prev_line.rstrip() + ",\n"

        # Insert new line with correlation_id before closing paren
        new_line = " " * indent + 'extra={"correlation_id": get_correlation_id()},\n'
        lines.insert(closing_paren_idx, new_line)
    else:
        # Single line call - this shouldn't happen since we're only fixing multi-line
        # But handle it anyway by inserting before closing paren
        before_paren = closing_line[:paren_pos]
        after_paren = closing_line[paren_pos:]

        # Check if we need a comma before extra
        stripped = before_paren.rstrip()
        if not stripped.endswith(",") and not stripped.endswith("("):
            before_paren = before_paren.rstrip() + ", "

        lines[closing_paren_idx] = (
            before_paren
            + 'extra={"correlation_id": get_correlation_id()}'
            + after_paren
        )

    return lines


def process_file(file_path: Path) -> int:
    """Process a file and fix all logging calls.

    Returns number of calls fixed.
    """
    calls_to_fix = find_logging_calls_needing_fix(file_path)

    if not calls_to_fix:
        return 0

    # Read file lines
    lines = file_path.read_text().splitlines(keepends=True)

    # Fix calls in reverse order (bottom to top) to maintain line numbers
    fixed_count = 0
    for start_line, end_line in sorted(calls_to_fix, reverse=True):
        lines = fix_logging_call(lines, start_line, end_line)
        fixed_count += 1

    # Write back
    file_path.write_text("".join(lines))

    return fixed_count


def main():
    """Main entry point."""
    files_to_fix = [
        ("src/code_indexer/server/mcp/handlers.py", 3),
        ("src/code_indexer/server/services/scip_resolution_queue.py", 6),
        ("src/code_indexer/server/sync/reindexing_engine.py", 9),
        ("src/code_indexer/server/web/routes.py", 13),
        ("src/code_indexer/server/app.py", 18),
        ("src/code_indexer/server/services/scip_self_healing.py", 28),
    ]

    print("Fixing remaining multi-line logging calls with AST-based approach...")
    print("=" * 60)

    total_fixed = 0
    for file_path_str, expected_count in files_to_fix:
        file_path = Path(file_path_str)
        if not file_path.exists():
            print(f"  ❌ {file_path.name}: File not found")
            continue

        fixed = process_file(file_path)
        if fixed > 0:
            print(
                f"  ✓ {file_path.name}: Fixed {fixed} calls (expected {expected_count})"
            )
            total_fixed += fixed
        else:
            print(
                f"  ⚠ {file_path.name}: No calls found to fix (expected {expected_count})"
            )

    print("=" * 60)
    print(f"Total calls fixed: {total_fixed}")
    print()

    # Verify syntax
    print("Verifying syntax...")
    all_ok = True
    for file_path_str, _ in files_to_fix:
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue

        try:
            compile(file_path.read_text(), file_path, "exec")
            print(f"  ✓ {file_path.name}: Syntax OK")
        except SyntaxError as e:
            print(f"  ❌ {file_path.name}: Syntax error: {e.msg} (line {e.lineno})")
            all_ok = False

    if all_ok:
        print("\n✅ All files have valid syntax!")
        return 0
    else:
        print("\n❌ Some files have syntax errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
