#!/usr/bin/env python3
"""
Automated script to update all logging calls with correlation_id support.

This script:
1. Parses Python files to find logger.error/warning/exception/info calls
2. Updates them to include extra={"correlation_id": get_correlation_id()}
3. Adds import statement if missing
4. Creates backups before modifying
5. Handles different logging patterns and edge cases

Story #666 - AC3, AC4, AC5: Update P0/P1/P2 files with correlation ID support
"""

import re
import shutil
import argparse
from pathlib import Path
from typing import List, Tuple


class LoggingCorrelationUpdater:
    """Updates Python files to add correlation_id to logging calls."""

    IMPORT_STATEMENT = "from code_indexer.server.middleware.correlation import get_correlation_id"
    LOGGING_METHODS = {"error", "warning", "exception", "info", "debug", "critical"}
    LOGGER_CALL_PATTERN = r'logger\.(error|warning|exception|info|debug|critical)\s*\('

    def __init__(self, dry_run: bool = False, backup: bool = True):
        """
        Initialize updater.

        Args:
            dry_run: If True, show changes without modifying files
            backup: If True, create .bak backups before modifying
        """
        self.dry_run = dry_run
        self.backup = backup
        self.stats = {
            "files_processed": 0,
            "files_modified": 0,
            "logging_calls_updated": 0,
            "imports_added": 0,
            "errors": 0,
        }

    def find_logging_calls(self, source_code: str) -> List[Tuple[int, str, str]]:
        """
        Find all logger.{method}() calls in source code.

        Args:
            source_code: Python source code

        Returns:
            List of tuples: (line_number, method_name, full_line_text)
        """
        calls = []
        lines = source_code.split('\n')

        for line_num, line in enumerate(lines, start=1):
            match = re.search(self.LOGGER_CALL_PATTERN, line)
            if match:
                method = match.group(1)
                calls.append((line_num, method, line))

        return calls

    def has_correlation_id_extra(self, line: str) -> bool:
        """
        Check if logging call already has correlation_id in extra parameter.

        Args:
            line: Line of source code

        Returns:
            True if correlation_id already present
        """
        return bool(re.search(r'extra\s*=\s*\{[^}]*["\']correlation_id["\']', line))

    def has_import_statement(self, source_code: str) -> bool:
        """
        Check if file already has the correlation import statement.

        Args:
            source_code: Python source code

        Returns:
            True if import already exists
        """
        return self.IMPORT_STATEMENT in source_code

    def add_import_statement(self, source_code: str) -> str:
        """
        Add import statement to source code if not present.

        Args:
            source_code: Python source code

        Returns:
            Updated source code with import added
        """
        if self.has_import_statement(source_code):
            return source_code

        lines = source_code.split('\n')
        insert_index = 0

        # Find last import statement
        for i, line in enumerate(lines):
            if line.strip().startswith(('import ', 'from ')):
                insert_index = i + 1
            elif line.strip() and not line.strip().startswith('#'):
                break

        lines.insert(insert_index, self.IMPORT_STATEMENT)
        self.stats["imports_added"] += 1
        return '\n'.join(lines)

    def find_matching_paren(self, text: str, start_pos: int) -> int:
        """
        Find the closing parenthesis matching the opening paren at start_pos.

        Handles nested parentheses, quotes, and escaped characters properly.

        Args:
            text: Source code text
            start_pos: Position of opening parenthesis

        Returns:
            Position of matching closing parenthesis, or -1 if not found
        """
        if start_pos >= len(text) or text[start_pos] != '(':
            return -1

        depth = 0
        in_string = False
        string_char = None
        escaped = False

        for i in range(start_pos, len(text)):
            char = text[i]

            # Handle escape sequences
            if escaped:
                escaped = False
                continue
            if char == '\\':
                escaped = True
                continue

            # Handle string literals
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
                continue
            elif char == string_char and in_string:
                in_string = False
                string_char = None
                continue

            # Only count parentheses outside strings
            if not in_string:
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                    if depth == 0:
                        return i

        return -1

    def update_logging_call(self, line: str, method: str) -> str:
        """
        Update a single logging call to include correlation_id.

        Handles two patterns:
        1. Simple: logger.error("msg") -> logger.error("msg", extra={...})
        2. Existing extra: logger.error("msg", extra={...}) -> merge correlation_id

        Args:
            line: Source code line containing logging call
            method: Logging method name (error/warning/etc)

        Returns:
            Updated line with correlation_id added
        """
        if self.has_correlation_id_extra(line):
            return line

        # Find logger.method( call
        pattern = rf'logger\.{method}\s*\('
        match = re.search(pattern, line)
        if not match:
            return line

        # Find matching closing parenthesis
        open_paren_pos = match.end() - 1
        close_paren_pos = self.find_matching_paren(line, open_paren_pos)

        if close_paren_pos == -1:
            # Can't find matching paren - skip this line
            return line

        # Pattern 1: No extra parameter - add new extra dict
        if 'extra=' not in line[open_paren_pos:close_paren_pos]:
            # Insert before closing paren
            updated = line[:close_paren_pos] + ', extra={"correlation_id": get_correlation_id()}' + line[close_paren_pos:]
            self.stats["logging_calls_updated"] += 1
            return updated

        # Pattern 2: Existing extra dict - merge correlation_id
        extra_pattern = rf'extra\s*=\s*\{{([^}}]*)\}}'
        match = re.search(extra_pattern, line[open_paren_pos:close_paren_pos])
        if match:
            existing_items = match.group(1).strip()
            full_match = match.group(0)

            if existing_items:
                # Has items - add correlation_id to dict
                new_extra = full_match.replace('}', ', "correlation_id": get_correlation_id()}')
            else:
                # Empty dict - just add correlation_id
                new_extra = 'extra={"correlation_id": get_correlation_id()}'

            # Replace in the substring between parentheses
            substring = line[open_paren_pos:close_paren_pos]
            updated_substring = substring.replace(full_match, new_extra, 1)
            updated = line[:open_paren_pos] + updated_substring + line[close_paren_pos:]
            self.stats["logging_calls_updated"] += 1
            return updated

        return line

    def _create_backup(self, file_path: Path) -> None:
        """Create backup of file before modification."""
        if self.backup and not self.dry_run:
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            shutil.copy2(file_path, backup_path)

    def update_file(self, file_path: Path) -> bool:
        """
        Update a single Python file with correlation_id support.

        Args:
            file_path: Path to Python file

        Returns:
            True if file was modified, False otherwise
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_source = f.read()

            logging_calls = self.find_logging_calls(original_source)
            if not logging_calls:
                return False

            self._create_backup(file_path)

            lines = original_source.split('\n')
            modified = False

            for line_num, method, original_line in logging_calls:
                if not self.has_correlation_id_extra(original_line):
                    updated_line = self.update_logging_call(original_line, method)
                    if updated_line != original_line:
                        lines[line_num - 1] = updated_line
                        modified = True

            if not modified:
                return False

            updated_source = '\n'.join(lines)
            updated_source = self.add_import_statement(updated_source)

            if not self.dry_run:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(updated_source)

            self.stats["files_modified"] += 1
            return True

        except Exception as e:
            print(f"ERROR processing {file_path}: {e}")
            self.stats["errors"] += 1
            return False

    def process_files(self, file_paths: List[Path]) -> None:
        """
        Process multiple Python files.

        Args:
            file_paths: List of file paths to process
        """
        for file_path in file_paths:
            self.stats["files_processed"] += 1
            modified = self.update_file(file_path)

            if modified:
                status = "DRY RUN" if self.dry_run else "Updated"
                print(f"✓ {status}: {file_path}")
            else:
                print(f"  Skipped: {file_path}")

    def print_summary(self) -> None:
        """Print processing summary statistics."""
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Files processed:       {self.stats['files_processed']}")
        print(f"Files modified:        {self.stats['files_modified']}")
        print(f"Logging calls updated: {self.stats['logging_calls_updated']}")
        print(f"Imports added:         {self.stats['imports_added']}")
        print(f"Errors:                {self.stats['errors']}")
        print("=" * 60)


def find_python_files(directory: Path, patterns: List[str]) -> List[Path]:
    """
    Find Python files matching glob patterns.

    Args:
        directory: Root directory to search
        patterns: List of glob patterns (e.g., ['auth/**/*.py'])

    Returns:
        List of matching Python file paths
    """
    files = []
    for pattern in patterns:
        files.extend(directory.glob(pattern))
    return sorted(set(files))


def main():
    """Main entry point with CLI argument handling."""
    parser = argparse.ArgumentParser(
        description="Update Python logging calls with correlation_id support"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without modifying files"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create .bak backups"
    )
    parser.add_argument(
        "--priority",
        choices=["p0", "p1", "p2", "all"],
        default="all",
        help="Which priority files to process (default: all)"
    )
    parser.add_argument(
        "--files",
        nargs='+',
        help="Specific files to process (overrides --priority)"
    )

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    src_dir = project_root / "src" / "code_indexer" / "server"

    priority_patterns = {
        "p0": ["auth/oidc/*.py", "auth/oauth/*.py", "sync/*.py"],
        "p1": ["repositories/*.py", "query/*.py"],
        "p2": [
            "routers/*.py", "web/*.py", "mcp/*.py", "services/*.py",
            "validation/*.py", "auto_update/*.py", "middleware/*.py",
            "git/*.py", "cache/*.py", "*.py", "auth/*.py", "omni/*.py"
        ],
    }

    if args.files:
        file_paths = [Path(f) for f in args.files]
    elif args.priority == "all":
        patterns = []
        for p in ["p0", "p1", "p2"]:
            patterns.extend(priority_patterns[p])
        file_paths = find_python_files(src_dir, patterns)
    else:
        patterns = priority_patterns[args.priority]
        file_paths = find_python_files(src_dir, patterns)

    file_paths = [f for f in file_paths if f.exists() and f.is_file()]

    print(f"Found {len(file_paths)} Python files to process")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print(f"Backup: {'DISABLED' if args.no_backup else 'ENABLED'}\n")

    updater = LoggingCorrelationUpdater(
        dry_run=args.dry_run,
        backup=not args.no_backup
    )
    updater.process_files(file_paths)
    updater.print_summary()

    if args.dry_run:
        print("\nRun without --dry-run to apply changes")


if __name__ == "__main__":
    main()
