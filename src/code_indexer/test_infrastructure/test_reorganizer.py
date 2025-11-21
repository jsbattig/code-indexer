"""
TestReorganizer - Reorganizes test files from flat structure to logical hierarchies.

This module implements the test directory reorganization functionality that moves
tests from a flat structure into organized subdirectories based on test type and
functionality, improving maintainability and discoverability.
"""

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


class FileReorganizer:
    """
    Reorganizes test files from flat structure into logical directory hierarchies.

    This class analyzes test files and categorizes them into:
    - unit/ - Pure unit tests organized by functionality
    - integration/ - Integration tests organized by system/service
    - e2e/ - End-to-end tests organized by workflow/feature
    - shared/ - Shared test utilities
    - fixtures/ - Test fixtures and data
    """

    def __init__(
        self, test_root: Path, dry_run: bool = False, backup_original: bool = True
    ):
        """
        Initialize TestReorganizer.

        Args:
            test_root: Root directory containing test files
            dry_run: If True, only plan moves without executing them
            backup_original: If True, create backup before reorganization

        Raises:
            FileNotFoundError: If test_root doesn't exist
        """
        if not test_root.exists():
            raise FileNotFoundError(f"Test root directory not found: {test_root}")

        self.test_root = test_root
        self.dry_run = dry_run
        self.backup_original = backup_original

        # Define directory structure mapping
        self.directory_structure = {
            "unit": {
                "parsers": "Language parsers and parsing logic",
                "chunking": "Fixed-size chunking logic",
                "config": "Configuration management",
                "cancellation": "Cancellation and interruption handling",
                "services": "Service layer unit tests",
                "cli": "CLI unit tests",
                "git": "Git operations and utilities",
                "infrastructure": "Infrastructure and core utilities",
                "bugfixes": "Bug fix regression tests",
            },
            "integration": {
                "performance": "Performance and throughput tests",
                "docker": "Docker integration and container tests",
                "multiproject": "Multi-project workflow tests",
                "indexing": "Indexing workflow integration tests",
                "cli": "CLI integration tests",
                "services": "Service integration tests",
            },
            "e2e": {
                "git_workflows": "Git workflow end-to-end tests",
                "payload_indexes": "Payload indexing end-to-end tests",
                "providers": "Provider switching and configuration",
                "semantic_search": "Semantic search capabilities",
                "claude_integration": "Claude integration workflows",
                "infrastructure": "Infrastructure end-to-end tests",
                "display": "Display and UI end-to-end tests",
                "misc": "Miscellaneous end-to-end tests",
            },
            "shared": {},
            "fixtures": {},
        }

        # Categorization patterns for test files
        self.categorization_patterns = {
            # Unit test patterns
            "unit": {
                "parsers": [
                    r".*parser.*\.py$",
                    r"test_.*_parser\.py$",
                ],
                "chunking": [
                    r"test_.*chunk.*\.py$",
                    r"test_.*chunking.*\.py$",
                ],
                "config": [
                    r"test_config.*\.py$",
                    r"test_.*config.*\.py$",
                    r"test_timeout_config\.py$",
                ],
                "cancellation": [
                    r"test_cancellation.*\.py$",
                    r"test_.*cancellation.*\.py$",
                    r"test_enhanced_cancellation.*\.py$",
                ],
                "services": [
                    r"test_.*service.*\.py$",
                    r"test_.*_manager\.py$",
                    r"test_vector_calculation.*\.py$",
                ],
                "cli": [
                    r"test_cli_.*\.py$",
                    r"test_.*_cli\.py$",
                ],
                "git": [
                    r"test_git_.*\.py$",
                    r"test_.*_git\.py$",
                    r"test_branch_.*\.py$",
                ],
                "infrastructure": [
                    r"test_infrastructure\.py$",
                    r"test_.*_infrastructure\.py$",
                    r"test_health_checker\.py$",
                ],
                "bugfixes": [
                    r"test_.*_bug.*\.py$",
                    r"test_.*_fix.*\.py$",
                    r"test_fix_.*\.py$",
                ],
            },
            # Integration test patterns
            "integration": {
                "performance": [
                    r"test_.*performance.*\.py$",
                    r"test_.*throughput.*\.py$",
                    r"test_parallel_.*\.py$",
                ],
                "docker": [
                    r"test_docker.*\.py$",
                    r"test_.*docker.*\.py$",
                    r"test_container.*\.py$",
                ],
                "multiproject": [
                    r"test_.*multiproject.*\.py$",
                    r"test_integration_multiproject.*\.py$",
                ],
                "indexing": [
                    r"test_.*indexing.*integration.*\.py$",
                    r"test_smart_indexer.*\.py$",
                    r"test_.*indexer.*\.py$",
                ],
                "cli": [
                    r"test_.*integration.*cli.*\.py$",
                    r"test_override.*integration.*\.py$",
                ],
                "services": [
                    r"test_.*service.*integration.*\.py$",
                    r"test_filesystem.*integration.*\.py$",
                    r"test_filesystem_service_config_integration\.py$",
                ],
            },
            # E2E test patterns
            "e2e": {
                "git_workflows": [
                    r"test_.*git.*e2e\.py$",
                    r"test_reconcile.*e2e\.py$",
                    r"test_.*workflow.*e2e\.py$",
                    r"test_comprehensive_git.*\.py$",
                ],
                "payload_indexes": [
                    r"test_payload_index.*e2e\.py$",
                    r"test_.*payload.*e2e\.py$",
                ],
                "providers": [
                    r"test_.*provider.*e2e\.py$",
                    r"test_.*embedding.*e2e\.py$",
                    r"test_voyage.*e2e\.py$",
                ],
                "semantic_search": [
                    r"test_semantic.*search.*e2e\.py$",
                    r"test_.*search.*e2e\.py$",
                    r"test_compare_search.*\.py$",
                ],
                "claude_integration": [
                    r"test_claude.*e2e\.py$",
                    r"test_.*claude.*e2e\.py$",
                ],
                "infrastructure": [
                    r"test_.*infrastructure.*e2e\.py$",
                    r"test_container.*e2e\.py$",
                ],
                "display": [
                    r"test_.*display.*e2e\.py$",
                    r"test_.*progress.*e2e\.py$",
                    r"test_line_number.*e2e\.py$",
                ],
                "misc": [
                    r"test_.*e2e\.py$",  # Catch-all for other e2e tests
                    r"test_end_to_end.*\.py$",
                ],
            },
        }

    def categorize_test_file(self, filename: str) -> Dict[str, str]:
        """
        Categorize a test file based on its name and content patterns.

        Args:
            filename: Name of the test file to categorize

        Returns:
            Dict containing category and subcategory information
        """
        # Check for e2e tests first (most specific)
        if "_e2e" in filename or "end_to_end" in filename:
            for subcategory, patterns in self.categorization_patterns["e2e"].items():
                for pattern in patterns:
                    if re.match(pattern, filename):
                        return {
                            "category": "e2e",
                            "subcategory": subcategory,
                            "pattern_matched": pattern,
                        }
            # Default e2e categorization
            return {
                "category": "e2e",
                "subcategory": "misc",
                "pattern_matched": "default_e2e",
            }

        # Check for integration tests next
        # This includes explicit integration files AND certain test types that are inherently integration
        if (
            "integration" in filename
            or "performance" in filename
            or "throughput" in filename
            or "docker" in filename
            or "container" in filename
        ):
            for subcategory, patterns in self.categorization_patterns[
                "integration"
            ].items():
                for pattern in patterns:
                    if re.match(pattern, filename):
                        return {
                            "category": "integration",
                            "subcategory": subcategory,
                            "pattern_matched": pattern,
                        }
            # Default integration categorization
            return {
                "category": "integration",
                "subcategory": "services",
                "pattern_matched": "default_integration",
            }

        # Check for unit tests last (most general patterns)
        for subcategory, patterns in self.categorization_patterns["unit"].items():
            for pattern in patterns:
                if re.match(pattern, filename):
                    return {
                        "category": "unit",
                        "subcategory": subcategory,
                        "pattern_matched": pattern,
                    }

        # Default categorization
        return {
            "category": "unit",
            "subcategory": "infrastructure",
            "pattern_matched": "default_unit",
        }

    def create_directory_structure(self) -> None:
        """Create the new directory structure for organized tests."""
        for category, subcategories in self.directory_structure.items():
            category_path = self.test_root / category
            category_path.mkdir(exist_ok=True)

            # Create __init__.py for Python package
            (category_path / "__init__.py").touch()

            for subcategory in subcategories:
                subcategory_path = category_path / subcategory
                subcategory_path.mkdir(exist_ok=True)

                # Create __init__.py for Python package
                (subcategory_path / "__init__.py").touch()

    def get_test_files(self) -> List[Path]:
        """Get all test files in the test root directory."""
        test_files = []
        for file_path in self.test_root.glob("test_*.py"):
            if file_path.is_file():
                test_files.append(file_path)
        return test_files

    def reorganize_tests(self) -> List[Dict[str, Any]]:
        """
        Reorganize test files into the new directory structure.

        Returns:
            List of move operations performed or planned
        """
        test_files = self.get_test_files()
        move_plan = []

        for test_file in test_files:
            # Skip files that are already in subdirectories
            if test_file.parent != self.test_root:
                continue

            categorization = self.categorize_test_file(test_file.name)

            destination_dir = (
                self.test_root
                / categorization["category"]
                / categorization["subcategory"]
            )
            destination_file = destination_dir / test_file.name

            move_operation = {
                "source": str(test_file),
                "destination": f"{categorization['category']}/{categorization['subcategory']}/{test_file.name}",
                "category": categorization["category"],
                "subcategory": categorization["subcategory"],
                "pattern_matched": categorization["pattern_matched"],
            }

            move_plan.append(move_operation)

            if not self.dry_run:
                # Ensure destination directory exists
                destination_dir.mkdir(parents=True, exist_ok=True)

                # Move the file
                shutil.move(str(test_file), str(destination_file))

                # Update import paths in the moved file
                self.update_import_paths(
                    destination_file,
                    f"{categorization['category']}/{categorization['subcategory']}",
                )

        return move_plan

    def update_import_paths(self, file_path: Path, relative_path: str) -> None:
        """
        Update import paths in moved test files to use correct relative imports.

        Args:
            file_path: Path to the moved test file
            relative_path: Relative path from test root (e.g., "unit/parsers")
        """
        content = file_path.read_text()

        # Calculate the number of levels to go up to reach test root
        levels_up = len(relative_path.split("/"))
        prefix = "." * (levels_up + 1)

        # Pattern to match imports from tests directory and subdirectories
        import_patterns = [
            # Handle imports like "from tests.unit.config.conftest" -> "from ...conftest"
            (
                r"from tests\.(unit|integration|e2e)\.([a-zA-Z_][a-zA-Z0-9_.]*)\.([a-zA-Z_][a-zA-Z0-9_]*)",
                rf"from {prefix}\3",
            ),
            # Handle imports like "from tests.conftest" -> "from ...conftest"
            (r"from tests\.([a-zA-Z_][a-zA-Z0-9_]*)", rf"from {prefix}\1"),
            # Handle imports like "import tests.unit.config.conftest" -> "import ...conftest"
            (
                r"import tests\.(unit|integration|e2e)\.([a-zA-Z_][a-zA-Z0-9_.]*)\.([a-zA-Z_][a-zA-Z0-9_]*)",
                rf"import {prefix}\3",
            ),
            # Handle imports like "import tests.conftest" -> "import ...conftest"
            (r"import tests\.([a-zA-Z_][a-zA-Z0-9_]*)", rf"import {prefix}\1"),
            # Handle imports like "from .conftest" which should stay as is
            # (no change needed for relative imports that are already correct)
        ]

        for pattern, replacement in import_patterns:
            content = re.sub(pattern, replacement, content)

        file_path.write_text(content)

    def create_backup(self) -> Path:
        """
        Create a backup of the original test structure.

        Returns:
            Path to the backup directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"tests_backup_{timestamp}"
        backup_path = self.test_root.parent / backup_name

        # Copy the entire test directory
        shutil.copytree(self.test_root, backup_path)

        return backup_path

    def rollback_from_backup(self, backup_path: Path) -> None:
        """
        Rollback to original structure from backup.

        Args:
            backup_path: Path to the backup directory
        """
        if backup_path.exists():
            # Remove current test directory
            shutil.rmtree(self.test_root)

            # Restore from backup
            shutil.copytree(backup_path, self.test_root)

    def validate_reorganization(self) -> Dict[str, Any]:
        """
        Validate that reorganization was successful.

        Returns:
            Dictionary with validation results
        """
        validation_results: Dict[str, Any] = {
            "all_files_moved": True,
            "no_missing_files": True,
            "import_paths_valid": True,
            "discovered_tests": [],
            "errors": [],
        }

        try:
            # Check if any test files remain in root
            remaining_files = list(self.test_root.glob("test_*.py"))
            if remaining_files:
                validation_results["all_files_moved"] = False
                validation_results["errors"].append(
                    f"Files remaining in root: {[f.name for f in remaining_files]}"
                )

            # Count test files in the reorganized structure
            test_count = 0
            for category_dir in ["unit", "integration", "e2e"]:
                category_path = self.test_root / category_dir
                if category_path.exists():
                    test_files = list(category_path.rglob("test_*.py"))
                    test_count += len(test_files)

            validation_results["discovered_tests"] = list(range(test_count))

            # Try pytest collection as additional validation
            try:
                result = subprocess.run(
                    [
                        "python",
                        "-m",
                        "pytest",
                        "--collect-only",
                        "-q",
                        str(self.test_root),
                    ],
                    capture_output=True,
                    text=True,
                    cwd=self.test_root.parent,
                    timeout=10,
                )

                if result.returncode != 0 and result.stderr:
                    validation_results["import_paths_valid"] = False
                    validation_results["errors"].append(
                        f"Pytest collection failed: {result.stderr}"
                    )
            except subprocess.TimeoutExpired:
                validation_results["errors"].append("Pytest collection timed out")

        except Exception as e:
            validation_results["errors"].append(f"Validation error: {str(e)}")

        return validation_results

    def get_file_statistics(self) -> Dict[str, int]:
        """
        Get statistics about file categorization.

        Returns:
            Dictionary with counts per category
        """
        stats = {"unit": 0, "integration": 0, "e2e": 0, "total": 0}

        test_files = self.get_test_files()

        for test_file in test_files:
            categorization = self.categorize_test_file(test_file.name)
            category = categorization["category"]

            if category in stats:
                stats[category] += 1
            stats["total"] += 1

        return stats
