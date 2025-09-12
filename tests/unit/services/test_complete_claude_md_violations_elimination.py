"""
Test complete elimination of CLAUDE.md violations.

This test ensures that all violations from the code-reviewer have been
completely eliminated with no fallbacks or compatibility layers.
"""

from pathlib import Path


class TestCompleteViolationsElimination:
    """Test complete elimination of all CLAUDE.md violations."""

    def test_no_slot_based_file_tracker_exists(self):
        """Test that SlotBasedFileTracker file no longer exists."""
        tracker_file = Path("src/code_indexer/services/slot_based_file_tracker.py")
        assert (
            not tracker_file.exists()
        ), "SlotBasedFileTracker file must be completely deleted"

    def test_no_slot_based_file_tracker_imports(self):
        """Test that no files import SlotBasedFileTracker."""
        src_dir = Path("src")
        violations = []

        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
                if "SlotBasedFileTracker" in content:
                    violations.append(str(py_file))
            except Exception:
                # Skip files that can't be read
                continue

        assert not violations, f"Found SlotBasedFileTracker imports in: {violations}"

    def test_no_thread_id_tracking_in_file_chunking_manager(self):
        """Test that FileChunkingManager has no thread_id tracking."""
        file_path = Path("src/code_indexer/services/file_chunking_manager.py")
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Check for thread tracking violations
            violations = []
            if "_get_next_thread_id" in content:
                violations.append("_get_next_thread_id method still exists")
            if "_thread_counter" in content:
                violations.append("_thread_counter attribute still exists")
            if "_thread_lock" in content:
                violations.append("_thread_lock attribute still exists")
            if "thread_id" in content and "thread_count" not in content.replace(
                "thread_id", ""
            ):
                violations.append("thread_id parameters still exist")

            assert not violations, f"Thread tracking violations: {violations}"

    def test_only_clean_slot_tracker_usage(self):
        """Test that only CleanSlotTracker is used system-wide."""
        src_dir = Path("src")
        files_with_clean_tracker = []
        files_with_old_tracker = []

        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
                if "CleanSlotTracker" in content:
                    files_with_clean_tracker.append(str(py_file))
                if "SlotBasedFileTracker" in content:
                    files_with_old_tracker.append(str(py_file))
            except Exception:
                continue

        # Should have CleanSlotTracker usage
        assert files_with_clean_tracker, "No CleanSlotTracker usage found"
        # Should have NO SlotBasedFileTracker usage
        assert (
            not files_with_old_tracker
        ), f"Found legacy SlotBasedFileTracker in: {files_with_old_tracker}"

    def test_mandatory_clean_slot_tracker_parameters(self):
        """Test that CleanSlotTracker is mandatory, not optional."""
        file_path = Path("src/code_indexer/services/file_chunking_manager.py")
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Should have mandatory slot_tracker parameter
            assert (
                "slot_tracker: CleanSlotTracker" in content
            ), "CleanSlotTracker must be mandatory parameter"

            # Should NOT have Optional or Union types for CleanSlotTracker specifically
            violations = []
            if "Optional[CleanSlotTracker]" in content:
                violations.append("CleanSlotTracker is Optional - must be mandatory")
            if "Union[" in content and "CleanSlotTracker" in content:
                violations.append("CleanSlotTracker is in Union - must be single type")
            if "Optional[Union[" in content and "CleanSlotTracker" in content:
                violations.append(
                    "CleanSlotTracker is in Optional Union - must be mandatory single type"
                )

            assert not violations, f"Parameter violations: {violations}"

    def test_single_acquire_release_pattern(self):
        """Test that files use single acquire/try/finally/release pattern."""
        file_path = Path("src/code_indexer/services/file_chunking_manager.py")
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Count acquire_slot calls in clean method
            clean_method_start = content.find("def _process_file_clean_lifecycle")
            if clean_method_start != -1:
                # Extract just the clean method
                next_method = content.find("\n    def ", clean_method_start + 1)
                if next_method == -1:
                    clean_method = content[clean_method_start:]
                else:
                    clean_method = content[clean_method_start:next_method]

                # Should have exactly one acquire_slot call
                acquire_count = clean_method.count("acquire_slot(")
                assert (
                    acquire_count == 1
                ), f"Should have exactly 1 acquire_slot call, found {acquire_count}"

                # Should have exactly one release_slot call in finally block
                release_count = clean_method.count("release_slot(")
                assert (
                    release_count == 1
                ), f"Should have exactly 1 release_slot call, found {release_count}"

                # Release should be in finally block
                assert "finally:" in clean_method, "Must have finally block"
                finally_section = clean_method.split("finally:")[-1]
                assert (
                    "release_slot(" in finally_section
                ), "release_slot must be in finally block"

    def test_no_filename_dictionary_complexity(self):
        """Test that filename dictionaries are eliminated."""
        src_dir = Path("src")
        violations = []

        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
                if "filename_to_slot" in content:
                    violations.append(
                        f"{py_file}: contains filename_to_slot dictionary"
                    )
                if "slot_to_filename" in content:
                    violations.append(
                        f"{py_file}: contains slot_to_filename dictionary"
                    )
            except Exception:
                continue

        assert not violations, f"Filename dictionary violations: {violations}"

    def test_pure_integer_slot_operations(self):
        """Test that slot operations use pure integers, not complex mappings."""
        file_path = Path("src/code_indexer/services/clean_slot_tracker.py")
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Should use integer slot IDs
            assert "slot_id: int" in content, "Slot operations must use integer IDs"

            # Should not have filename-based operations in CleanSlotTracker
            violations = []
            if "def acquire_slot(self, filename" in content:
                violations.append("acquire_slot should not take filename parameter")
            if "def release_slot(self, filename" in content:
                violations.append("release_slot should not take filename parameter")

            assert not violations, f"Complex slot operation violations: {violations}"

    def test_high_throughput_processor_clean_integration(self):
        """Test that HighThroughputProcessor uses only CleanSlotTracker."""
        file_path = Path("src/code_indexer/services/high_throughput_processor.py")
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Should import only CleanSlotTracker
            assert (
                "from .clean_slot_tracker import CleanSlotTracker" in content
            ), "Must import CleanSlotTracker"
            assert (
                "from .slot_based_file_tracker import" not in content
            ), "Must not import SlotBasedFileTracker"

            # Should use slot_tracker parameter name
            assert (
                "slot_tracker=local_slot_tracker" in content
            ), "Must pass slot_tracker parameter"
            assert "file_tracker=" not in content, "Must not use file_tracker parameter"

    def test_async_display_worker_clean_integration(self):
        """Test that AsyncDisplayWorker uses only CleanSlotTracker."""
        file_path = Path("src/code_indexer/progress/async_display_worker.py")
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Should import only CleanSlotTracker
            assert (
                "from ..services.clean_slot_tracker import" in content
            ), "Must import CleanSlotTracker"
            assert (
                "from ..services.slot_based_file_tracker import" not in content
            ), "Must not import SlotBasedFileTracker"

            # Should declare CleanSlotTracker type
            assert (
                "slot_tracker: CleanSlotTracker" in content
            ), "Must declare CleanSlotTracker type"

    def test_no_compatibility_or_fallback_layers(self):
        """Test that no compatibility or fallback layers exist."""
        src_dir = Path("src")
        violations = []

        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")

                # Check for compatibility patterns
                if "backward compatibility" in content.lower():
                    violations.append(
                        f"{py_file}: contains backward compatibility code"
                    )
                if "isinstance(self.file_tracker," in content:
                    violations.append(
                        f"{py_file}: contains type checking for multiple trackers"
                    )
                if "Union[SlotBasedFileTracker," in content:
                    violations.append(
                        f"{py_file}: contains Union type with old tracker"
                    )
                if "Optional[Union[" in content and "SlotBasedFileTracker" in content:
                    violations.append(
                        f"{py_file}: contains optional union with old tracker"
                    )

            except Exception:
                continue

        assert not violations, f"Compatibility/fallback violations: {violations}"

    def test_file_chunking_manager_clean_implementation(self):
        """Test that FileChunkingManager uses only clean implementation."""
        file_path = Path("src/code_indexer/services/file_chunking_manager.py")
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Should have only clean lifecycle method
            assert (
                "_process_file_clean_lifecycle" in content
            ), "Must have clean lifecycle method"
            assert (
                "_process_file_complete_lifecycle" not in content
            ), "Must not have old lifecycle method"

            # Should always use clean implementation
            assert (
                "process_method = self._process_file_clean_lifecycle" in content
            ), "Must always use clean method"

            # Should not have conditional method selection
            violations = []
            if "if isinstance(" in content and "CleanSlotTracker" in content:
                violations.append("Contains conditional tracker type checking")

            assert not violations, f"Implementation selection violations: {violations}"
