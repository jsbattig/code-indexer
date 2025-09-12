"""
CLAUDE.md Final Compliance Tests for Slot-Based File Tracking System.

Tests to ensure complete elimination of fallback patterns and anti-fallback violations.
These tests enforce CLAUDE.md foundations:
1. Anti-Mock: No fake implementations
2. Anti-Fallback: No alternative execution paths
3. KISS: Single system approach only
4. Anti-Duplication: One file tracking system

These tests MUST pass to demonstrate complete CLAUDE.md compliance.
"""

import inspect
from pathlib import Path
import pytest

from code_indexer.services.file_chunking_manager import FileChunkingManager


class TestClaudeMdFinalCompliance:
    """Tests enforcing complete CLAUDE.md compliance for file tracking system."""

    def test_deletion_fallback_scanner_completely_removed(self):
        """
        CRITICAL: Deletion fallback scanner file must not exist.

        CLAUDE.md Anti-Fallback Foundation: Fallbacks are forbidden.
        This file represents an alternative execution path that must be eliminated.
        """
        fallback_file = Path("src/code_indexer/services/deletion_fallback_scanner.py")
        assert not fallback_file.exists(), (
            f"CLAUDE.md VIOLATION: Fallback scanner still exists at {fallback_file}. "
            "This file represents forbidden fallback logic and must be deleted completely."
        )

    def test_slot_tracker_is_mandatory_not_optional(self):
        """
        CRITICAL: CleanSlotTracker must be mandatory in FileChunkingManager constructor.

        CLAUDE.md Anti-Fallback Foundation: Optional dependencies create alternative paths.
        The slot tracker must be required, not optional.
        """
        # Get FileChunkingManager constructor signature
        sig = inspect.signature(FileChunkingManager.__init__)

        # Check if slot_tracker parameter exists and is properly typed
        params = sig.parameters

        # The parameter should be named slot_tracker
        tracker_param = params.get("slot_tracker")

        assert tracker_param is not None, (
            "CLAUDE.md VIOLATION: No slot_tracker parameter found in FileChunkingManager constructor. "
            "CleanSlotTracker must be mandatory parameter."
        )

        # Check it's not Optional
        param_annotation = tracker_param.annotation
        if hasattr(param_annotation, "__origin__"):
            # It's a generic type like Optional[X] or Union[X, None]
            if param_annotation.__origin__ is type(None):
                pytest.fail(
                    f"CLAUDE.md VIOLATION: {tracker_param.name} is Optional. "
                    "CleanSlotTracker must be mandatory, not optional."
                )

        # Check it has no default (making it mandatory)
        assert tracker_param.default == inspect.Parameter.empty, (
            f"CLAUDE.md VIOLATION: {tracker_param.name} has default value {tracker_param.default}. "
            "CleanSlotTracker must be mandatory parameter with no default."
        )

    def test_no_conditional_slot_tracker_checks(self):
        """
        HIGH: No conditional checks for slot tracker existence.

        CLAUDE.md Anti-Fallback Foundation: Conditional logic creates alternative paths.
        All slot tracker usage must be unconditional.
        """
        from code_indexer.services import file_chunking_manager

        # Read the source code
        source_file = Path(file_chunking_manager.__file__)
        source_code = source_file.read_text()

        # Check for forbidden conditional patterns
        forbidden_patterns = [
            "if self.slot_tracker:",
            "if slot_tracker:",
            "if self.file_tracker:",
            "if file_tracker:",
            "self.slot_tracker and",
            "self.file_tracker and",
        ]

        violations = []
        for pattern in forbidden_patterns:
            if pattern in source_code:
                violations.append(pattern)

        assert not violations, (
            f"CLAUDE.md VIOLATION: Found conditional slot tracker checks: {violations}. "
            "All slot tracker usage must be unconditional - no fallback paths allowed."
        )

    def test_no_legacy_import_patterns(self):
        """
        MEDIUM: No imports of legacy consolidated file tracker.

        CLAUDE.md Anti-Duplication Foundation: Old system must be completely eliminated.
        """
        # Check main source files
        src_path = Path("src/code_indexer")
        python_files = list(src_path.rglob("*.py"))

        violations = []
        for py_file in python_files:
            content = py_file.read_text()
            if "from code_indexer.services.consolidated_file_tracker import" in content:
                violations.append(str(py_file))
            if "import consolidated_file_tracker" in content:
                violations.append(str(py_file))

        assert not violations, (
            f"CLAUDE.md VIOLATION: Found legacy consolidated file tracker imports in: {violations}. "
            "All imports must use CleanSlotTracker only."
        )

    def test_test_files_use_correct_imports(self):
        """
        MEDIUM: Test files must import CleanSlotTracker, not legacy tracker.

        CLAUDE.md Anti-Duplication Foundation: Tests must match production reality.
        """
        test_path = Path("tests")
        python_files = list(test_path.rglob("*.py"))

        violations = []
        for py_file in python_files:
            # Skip compliance test files that are checking for violations
            if (
                "claude_md_final_compliance" in py_file.name
                or "claude_md_compliance" in py_file.name
            ):
                continue

            content = py_file.read_text()
            # Check for actual imports (not error message strings)
            import_lines = [
                line.strip()
                for line in content.split("\n")
                if line.strip().startswith("from") or line.strip().startswith("import")
            ]
            for line in import_lines:
                if "consolidated_file_tracker" in line:
                    violations.append(f"{py_file}: {line}")

        assert not violations, (
            f"CLAUDE.md VIOLATION: Found legacy tracker imports in test files: {violations}. "
            "All test imports must use CleanSlotTracker."
        )

    def test_no_backward_compatibility_comments(self):
        """
        MEDIUM: No legacy/backward compatibility comments allowed.

        CLAUDE.md Anti-Fallback Foundation: Legacy comments indicate fallback thinking.
        """
        src_path = Path("src/code_indexer")
        python_files = list(src_path.rglob("*.py"))

        forbidden_comment_patterns = [
            "legacy fallback",
            "backward compatibility",
            "removed consolidatedfiletracker",
            "fallback scanner",
            "alternative path",
            "just in case",
        ]

        violations = []
        for py_file in python_files:
            content = py_file.read_text().lower()
            for pattern in forbidden_comment_patterns:
                if pattern in content:
                    violations.append(f"{py_file}: contains '{pattern}'")

        assert not violations, (
            f"CLAUDE.md VIOLATION: Found legacy/fallback comments: {violations}. "
            "All legacy comments must be removed to prevent fallback thinking."
        )

    def test_single_file_tracking_system_only(self):
        """
        HIGH: Only CleanSlotTracker should exist as file tracking system.

        CLAUDE.md Anti-Duplication Foundation: One concept, one implementation.
        """
        services_path = Path("src/code_indexer/services")

        # Only CleanSlotTracker should exist as the single file tracking system
        expected_tracker = services_path / "clean_slot_tracker.py"
        assert expected_tracker.exists(), (
            "CLAUDE.md VIOLATION: CleanSlotTracker file missing. "
            "The single file tracking system must exist."
        )

        # ConsolidatedFileTracker should not exist
        forbidden_tracker = services_path / "consolidated_file_tracker.py"
        assert not forbidden_tracker.exists(), (
            "CLAUDE.md VIOLATION: ConsolidatedFileTracker still exists. "
            "Old file tracking system must be completely removed."
        )

        # Deletion fallback scanner should not exist
        forbidden_scanner = services_path / "deletion_fallback_scanner.py"
        assert not forbidden_scanner.exists(), (
            "CLAUDE.md VIOLATION: Deletion fallback scanner still exists. "
            "All fallback systems must be completely eliminated."
        )

    def test_file_chunking_manager_uses_slot_tracker_unconditionally(self):
        """
        CRITICAL: FileChunkingManager must use slot tracker without conditionals.

        CLAUDE.md Anti-Fallback Foundation: No alternative execution paths.
        """
        # Import and inspect the actual implementation
        manager_source = Path(
            "src/code_indexer/services/file_chunking_manager.py"
        ).read_text()

        # Must NOT have these conditional patterns
        forbidden_conditional_patterns = [
            "if slot_tracker",
            "if file_tracker",
            "slot_tracker and",
            "file_tracker and",
            "slot_tracker is not None",
            "file_tracker is not None",
        ]

        violations = []
        for pattern in forbidden_conditional_patterns:
            if pattern in manager_source:
                violations.append(pattern)

        assert not violations, (
            f"CLAUDE.md VIOLATION: Found conditional slot tracker usage: {violations}. "
            "Slot tracker must be used unconditionally - no fallback paths."
        )
