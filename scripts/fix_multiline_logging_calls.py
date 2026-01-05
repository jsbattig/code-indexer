#!/usr/bin/env python3
"""
Fix multi-line logging calls that were missed by the original automation script.

This script handles logging calls that span multiple lines, which the original
script couldn't handle because it processed line-by-line.

Story #666 - Completing correlation ID coverage for remaining 395 calls
"""

import re
import shutil
from pathlib import Path
from typing import List, Optional


class MultiLineLoggingFixer:
    """Fixes multi-line logging calls to include correlation_id."""

    IMPORT_STATEMENT = "from code_indexer.server.middleware.correlation import get_correlation_id"
    MAX_MULTILINE_SPAN = 10  # Maximum lines to look ahead for call end
    SUMMARY_WIDTH = 60  # Width of summary section separator

    def __init__(self, dry_run: bool = False):
        """Initialize fixer."""
        self.dry_run = dry_run
        self.stats = {
            "files_processed": 0,
            "files_modified": 0,
            "calls_fixed": 0,
            "imports_added": 0,
        }

    def has_import(self, source: str) -> bool:
        """Check if import already exists."""
        return self.IMPORT_STATEMENT in source

    def add_import(self, source: str) -> str:
        """Add import statement if missing."""
        if self.has_import(source):
            return source

        lines = source.split('\n')
        insert_index = 0

        # Find last import statement
        for i, line in enumerate(lines):
            if line.strip().startswith(('import ', 'from ')):
                insert_index = i + 1
            elif line.strip() and not line.strip().startswith(('#', '"""', "'''")):
                break

        lines.insert(insert_index, self.IMPORT_STATEMENT)
        self.stats["imports_added"] += 1
        return '\n'.join(lines)

    def find_function_call_end(self, lines: List[str], start_line: int) -> Optional[int]:
        """
        Find the line where a function call ends.

        LIMITATIONS: This simple parser may not handle:
        - Triple-quoted strings (docstrings)
        - Complex escaped quotes within strings
        - Comments containing parentheses on the same line

        For this use case (fixing logging calls), these limitations are acceptable
        as logging calls rarely contain these patterns.

        Args:
            lines: List of source code lines
            start_line: Line index where function call starts (0-based)

        Returns:
            Line index where call ends, or None if not found
        """
        paren_depth = 0
        in_string = False
        string_char = None

        for i in range(start_line, len(lines)):
            # Safety check - don't go beyond reasonable span
            if i - start_line > self.MAX_MULTILINE_SPAN:
                break

            line = lines[i]

            for char in line:
                # Simple string tracking - handles basic quotes
                # Does not handle triple quotes or complex escape sequences
                if char in ('"', "'") and not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char and in_string:
                    in_string = False
                    string_char = None
                elif not in_string:
                    if char == '(':
                        paren_depth += 1
                    elif char == ')':
                        paren_depth -= 1
                        if paren_depth == 0:
                            return i

        return None

    def extract_call_text(self, lines: List[str], start_line: int, end_line: int) -> str:
        """Extract the full text of a function call spanning multiple lines."""
        if start_line == end_line:
            return lines[start_line]
        return '\n'.join(lines[start_line:end_line + 1])

    def has_correlation_id(self, call_text: str) -> bool:
        """Check if call already has correlation_id."""
        return 'correlation_id' in call_text and 'get_correlation_id' in call_text

    def fix_logging_call(self, call_text: str) -> str:
        """
        Fix a logging call to include correlation_id.

        Args:
            call_text: Full text of logging call (may be multi-line)

        Returns:
            Fixed call text with correlation_id added
        """
        if self.has_correlation_id(call_text):
            return call_text

        # Pattern 1: No extra parameter - add new extra dict
        if 'extra=' not in call_text:
            last_paren = call_text.rfind(')')
            if last_paren == -1:
                return call_text

            fixed = (
                call_text[:last_paren] +
                ', extra={"correlation_id": get_correlation_id()}' +
                call_text[last_paren:]
            )
            return fixed

        # Pattern 2: Has extra parameter - merge correlation_id
        # NOTE: This regex does not handle nested dicts like extra={"foo": {"bar": 1}}
        # For our use case (logging calls), extra dicts are typically flat
        extra_pattern = r'extra\s*=\s*\{([^}]*)\}'
        match = re.search(extra_pattern, call_text, re.DOTALL)

        if match:
            existing_items = match.group(1).strip()
            full_match = match.group(0)

            if existing_items:
                # Has items - add correlation_id
                new_extra = full_match.replace('}', ', "correlation_id": get_correlation_id()}')
            else:
                # Empty dict
                new_extra = 'extra={"correlation_id": get_correlation_id()}'

            fixed = call_text.replace(full_match, new_extra, 1)
            return fixed

        return call_text

    def _process_lines(self, lines: List[str]) -> bool:
        """
        Process lines to fix logger calls.

        Args:
            lines: Mutable list of source code lines

        Returns:
            True if any modifications were made
        """
        modified = False
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check if line has a logger call
            match = re.search(r'logger\.(error|warning|exception|info|debug|critical)\s*\(', line)
            if match and 'correlation_id' not in line:
                # Find where the call ends
                end_line = self.find_function_call_end(lines, i)
                if end_line is None:
                    i += 1
                    continue

                # Extract full call text
                call_text = self.extract_call_text(lines, i, end_line)

                # Skip if already has correlation_id
                if self.has_correlation_id(call_text):
                    i = end_line + 1
                    continue

                # Fix the call
                fixed_text = self.fix_logging_call(call_text)

                if fixed_text != call_text:
                    # Replace lines
                    fixed_lines = fixed_text.split('\n')
                    lines[i:end_line + 1] = fixed_lines
                    modified = True
                    self.stats["calls_fixed"] += 1
                    i += len(fixed_lines)
                else:
                    i = end_line + 1
            else:
                i += 1

        return modified

    def process_file(self, file_path: Path) -> bool:
        """
        Process a single Python file.

        Args:
            file_path: Path to Python file

        Returns:
            True if file was modified
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            lines = source.split('\n')
            modified = self._process_lines(lines)

            if not modified:
                return False

            # Reconstruct source and add import
            new_source = '\n'.join(lines)
            new_source = self.add_import(new_source)

            if not self.dry_run:
                # Create backup
                backup_path = file_path.with_suffix(file_path.suffix + '.bak')
                shutil.copy2(file_path, backup_path)

                # Write modified source
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_source)

            self.stats["files_modified"] += 1
            return True

        except Exception as e:
            print(f"ERROR processing {file_path}: {e}")
            return False

    def process_files(self, file_paths: List[Path]) -> None:
        """Process multiple files."""
        for file_path in file_paths:
            self.stats["files_processed"] += 1
            modified = self.process_file(file_path)

            if modified:
                status = "DRY RUN" if self.dry_run else "Fixed"
                print(f"✓ {status}: {file_path}")
            else:
                print(f"  Skipped: {file_path}")

    def print_summary(self) -> None:
        """Print summary statistics."""
        print("\n" + "=" * self.SUMMARY_WIDTH)
        print("SUMMARY")
        print("=" * self.SUMMARY_WIDTH)
        print(f"Files processed:  {self.stats['files_processed']}")
        print(f"Files modified:   {self.stats['files_modified']}")
        print(f"Calls fixed:      {self.stats['calls_fixed']}")
        print(f"Imports added:    {self.stats['imports_added']}")
        print("=" * self.SUMMARY_WIDTH)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fix multi-line logging calls")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without modifying")
    parser.add_argument("files", nargs='+', help="Files to process")

    args = parser.parse_args()

    file_paths = [Path(f) for f in args.files if Path(f).exists()]

    print(f"Found {len(file_paths)} files to process")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}\n")

    fixer = MultiLineLoggingFixer(dry_run=args.dry_run)
    fixer.process_files(file_paths)
    fixer.print_summary()


if __name__ == "__main__":
    main()
