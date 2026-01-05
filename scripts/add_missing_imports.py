#!/usr/bin/env python3
"""Add missing correlation import to files that use get_correlation_id()."""

import subprocess
from pathlib import Path

IMPORT_STATEMENT = "from code_indexer.server.middleware.correlation import get_correlation_id"


def get_modified_python_files():
    """Get list of modified Python files from git."""
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        capture_output=True,
        text=True,
        check=True
    )
    return [
        Path(f) for f in result.stdout.strip().split('\n')
        if f.endswith('.py') and Path(f).exists()
    ]


def needs_import(file_path):
    """Check if file uses get_correlation_id but lacks import."""
    content = file_path.read_text()
    uses_function = "get_correlation_id()" in content
    has_import = IMPORT_STATEMENT in content
    return uses_function and not has_import


def add_import(file_path):
    """Add import statement to file."""
    lines = file_path.read_text().split('\n')
    insert_index = 0

    # Find last import
    for i, line in enumerate(lines):
        if line.strip().startswith(('import ', 'from ')):
            insert_index = i + 1
        elif line.strip() and not line.strip().startswith('#'):
            break

    lines.insert(insert_index, IMPORT_STATEMENT)
    file_path.write_text('\n'.join(lines))
    print(f"✓ Added import to: {file_path}")


def main():
    files = get_modified_python_files()
    print(f"Checking {len(files)} modified Python files...")

    count = 0
    for file_path in files:
        if needs_import(file_path):
            add_import(file_path)
            count += 1

    print(f"\n{count} files updated with import statement")


if __name__ == "__main__":
    main()
