#!/usr/bin/env python3
"""Standalone glob file matching script for subprocess-based file discovery.

This script performs glob pattern matching on filesystem paths and returns
results as JSON. It's designed to be called via subprocess with timeout and
process isolation protections.

Input: JSON config file path as first argument:
    {
        "search_path": "/path/to/search",
        "include_patterns": ["**/*.py", "code/**/Main.java"],
        "exclude_patterns": ["test_*", "*.tmp"]
    }

Output: JSON array of relative file paths to stdout:
    ["path/to/file1.py", "path/to/file2.py", ...]

Exit codes:
    0: Success (even if no matches found)
    1: Error (invalid config, path doesn't exist, etc.)

This script implements the EXACT glob logic from regex_search.py lines 311-379
to ensure pattern matching correctness is preserved during the subprocess transition.
"""

import sys
import json
import fnmatch
from pathlib import Path
from typing import List, Optional, Set, Tuple


def glob_files(
    search_path: Path,
    include_patterns: List[str],
    exclude_patterns: Optional[List[str]],
) -> List[str]:
    """Find files matching glob patterns (exact implementation from regex_search.py).

    Supports the following pattern types to match ripgrep's -g flag behavior:
    - "**/file.java" - Recursive search from search_path
    - "code/**/file.java" - Recursive search from search_path/code
    - "code/src/file.java" - Explicit path (non-recursive)
    - "*.java" - Simple pattern (recursive from search_path)

    Args:
        search_path: Base directory to search from. All patterns resolved relative to this path.
        include_patterns: List of glob patterns following ripgrep -g flag syntax.
        exclude_patterns: Optional list of patterns to exclude from results.

    Returns:
        List of relative file paths as strings for all files matching include patterns
        and not matching exclude patterns. Empty list if no matches found.

    Raises:
        ValueError: If search_path doesn't exist or isn't a directory.
    """
    if not search_path.exists():
        raise ValueError(f"Search path does not exist: {search_path}")
    if not search_path.is_dir():
        raise ValueError(f"Search path is not a directory: {search_path}")

    matched_files: Set[Path] = set()

    # Process include patterns - EXACT logic from regex_search.py lines 315-358
    for pattern in include_patterns:
        # Handle different pattern types to match ripgrep -g behavior
        if pattern.startswith("**/"):
            # Pattern like **/filename.ext or **/dir/*.ext
            # Use rglob for recursive matching from search_path
            sub_pattern = pattern[3:]  # Remove **/ prefix
            for file_path in search_path.rglob(sub_pattern):
                if file_path.is_file():
                    matched_files.add(file_path)

        elif "**" in pattern:
            # Pattern like dir/**/filename.ext (** in middle)
            # Split on /** and use rglob for the recursive part
            parts = pattern.split("/**/")
            if len(parts) == 2:
                prefix, suffix = parts
                # Find all directories matching prefix
                prefix_path = search_path / prefix if prefix else search_path
                if prefix_path.exists() and prefix_path.is_dir():
                    # Use rglob from prefix_path for suffix pattern
                    for file_path in prefix_path.rglob(suffix):
                        if file_path.is_file():
                            matched_files.add(file_path)
            else:
                # Multiple ** in pattern - fall back to walking entire tree
                for file_path in search_path.rglob("*"):
                    if file_path.is_file():
                        rel_path = str(file_path.relative_to(search_path))
                        if fnmatch.fnmatch(rel_path, pattern):
                            matched_files.add(file_path)

        elif "/" in pattern:
            # Explicit path pattern like code/src/Main.java
            # Use glob for non-recursive matching
            for file_path in search_path.glob(pattern):
                if file_path.is_file():
                    matched_files.add(file_path)

        else:
            # Simple filename pattern like *.java
            # Use rglob to find at any depth
            for file_path in search_path.rglob(pattern):
                if file_path.is_file():
                    matched_files.add(file_path)

    # Apply exclude patterns - EXACT logic from regex_search.py lines 360-373
    if exclude_patterns:
        filtered_files: Set[Path] = set()
        for file_path in matched_files:
            rel_path = str(file_path.relative_to(search_path))
            excluded = False
            for exclude_pattern in exclude_patterns:
                # Match exclude pattern anywhere in path
                if fnmatch.fnmatch(rel_path, f"*{exclude_pattern}*"):
                    excluded = True
                    break
            if not excluded:
                filtered_files.add(file_path)
        matched_files = filtered_files

    # Convert to relative paths as strings - EXACT logic from regex_search.py lines 375-379
    return [
        str(file_path.relative_to(search_path))
        for file_path in sorted(matched_files)
    ]


def parse_and_validate_config(config_file: str) -> Tuple[Path, List[str], Optional[List[str]]]:
    """Parse and validate config file.

    Args:
        config_file: Path to JSON config file

    Returns:
        Tuple of (search_path, include_patterns, exclude_patterns)

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file contains invalid JSON
        ValueError: If config is missing required fields or has invalid types
    """
    with open(config_file, 'r') as f:
        config = json.load(f)

    # Validate required fields
    if "search_path" not in config:
        raise ValueError("Config missing required field: search_path")
    if "include_patterns" not in config:
        raise ValueError("Config missing required field: include_patterns")

    # Extract and validate types
    search_path = Path(config["search_path"])
    include_patterns = config["include_patterns"]
    exclude_patterns = config.get("exclude_patterns")

    if not isinstance(include_patterns, list):
        raise ValueError("include_patterns must be a list")
    if exclude_patterns is not None and not isinstance(exclude_patterns, list):
        raise ValueError("exclude_patterns must be a list or null")

    return search_path, include_patterns, exclude_patterns


def main() -> int:
    """Main entry point for subprocess execution.

    Reads JSON config from file specified as first argument, performs glob matching,
    and outputs JSON array of file paths to stdout.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        # Expect config file path as first argument
        if len(sys.argv) != 2:
            print(json.dumps([]))
            sys.stderr.write("Usage: glob_files.py <config_file_path>\n")
            return 1

        config_file = sys.argv[1]

        # Parse and validate config
        search_path, include_patterns, exclude_patterns = parse_and_validate_config(config_file)

        # Perform glob matching
        files = glob_files(search_path, include_patterns, exclude_patterns)

        # Output results as JSON array
        print(json.dumps(files))
        return 0

    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        # Known error types - return empty array and write error to stderr
        print(json.dumps([]))
        sys.stderr.write(f"Error: {e}\n")
        return 1

    except Exception as e:
        # Unexpected errors - return empty array and write error to stderr
        print(json.dumps([]))
        sys.stderr.write(f"Unexpected error: {type(e).__name__}: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
