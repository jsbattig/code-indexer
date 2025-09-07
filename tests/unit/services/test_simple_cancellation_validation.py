"""
Simple validation tests for post-write only cancellation.

These tests examine the source code directly to verify that cancellation
checks only occur between files, not during file processing.
"""

import ast
import inspect

from code_indexer.services.file_chunking_manager import FileChunkingManager
from code_indexer.services.high_throughput_processor import HighThroughputProcessor


class TestSimpleCancellationValidation:
    """Simple source code validation for cancellation placement."""

    def test_file_chunking_manager_has_no_mid_process_cancellation_checks(self):
        """
        CRITICAL TEST: Verify that FileChunkingManager._process_file_complete_lifecycle
        does NOT contain any cancellation checks during file processing.

        This test examines the source code directly to find cancellation property access.
        """
        # Get the source code of the main processing method
        method = FileChunkingManager._process_file_complete_lifecycle
        source_code = inspect.getsource(method)

        # Parse the AST to find cancellation-related access
        # Remove indentation to make AST parsing work
        import textwrap

        dedented_source = textwrap.dedent(source_code)
        tree = ast.parse(dedented_source)

        cancellation_checks = []

        class CancellationVisitor(ast.NodeVisitor):
            def visit_Attribute(self, node):
                # Look for any attribute access related to cancellation
                if isinstance(node.attr, str) and "cancel" in node.attr.lower():
                    cancellation_checks.append(f"Line {node.lineno}: {node.attr}")
                self.generic_visit(node)

            def visit_Name(self, node):
                # Look for cancellation-related variable names
                if isinstance(node.id, str) and "cancel" in node.id.lower():
                    cancellation_checks.append(f"Line {node.lineno}: {node.id}")
                self.generic_visit(node)

        visitor = CancellationVisitor()
        visitor.visit(tree)

        # CRITICAL ASSERTION: NO cancellation checks should exist in file processing
        assert len(cancellation_checks) == 0, (
            f"Found {len(cancellation_checks)} cancellation checks in _process_file_complete_lifecycle: "
            f"{cancellation_checks}. This violates post-write only cancellation requirement."
        )

    def test_post_write_cancellation_check_exists_but_only_at_end(self):
        """
        VALIDATION TEST: Verify that if cancellation checks exist in file processing,
        they only occur AFTER the Qdrant write operation completes.

        This ensures file atomicity by allowing the check only post-write.
        """
        method = FileChunkingManager._process_file_complete_lifecycle
        source_code = inspect.getsource(method)

        # Look for the pattern: upsert_points_atomic followed by cancellation check
        lines = source_code.split("\n")

        upsert_line_number = None
        cancellation_check_lines = []

        for i, line in enumerate(lines):
            if "upsert_points_atomic" in line:
                upsert_line_number = i
            if any(
                term in line.lower()
                for term in [
                    "_cancellation_requested",
                    "cancellation_event",
                    "cancelled",
                ]
            ):
                cancellation_check_lines.append(i)

        if upsert_line_number is not None and cancellation_check_lines:
            # If both exist, cancellation checks must come AFTER upsert
            for cancel_line in cancellation_check_lines:
                assert cancel_line > upsert_line_number, (
                    f"Cancellation check at line {cancel_line} occurs BEFORE upsert at line {upsert_line_number}. "
                    f"This can cause partial file writes and violates atomicity."
                )

    def test_high_throughput_processor_cancellation_only_between_files(self):
        """
        CRITICAL TEST: Verify that HighThroughputProcessor only checks cancellation
        between files, not during file processing.

        This examines the main processing loop to ensure cancellation checks
        occur only at the right places.
        """
        # Find the process_files method or similar
        methods_to_check = ["process_files", "_process_batch_files"]

        for method_name in methods_to_check:
            if hasattr(HighThroughputProcessor, method_name):
                method = getattr(HighThroughputProcessor, method_name)
                source_code = inspect.getsource(method)

                # Look for the pattern: as_completed(file_futures) loop
                lines = source_code.split("\n")

                in_file_loop = False
                file_result_line = None
                cancellation_checks_in_loop = []

                for i, line in enumerate(lines):
                    if (
                        "as_completed(file_futures)" in line
                        or "for file_future in" in line
                    ):
                        in_file_loop = True
                        continue

                    if in_file_loop and "file_result = " in line and ".result(" in line:
                        file_result_line = i
                        continue

                    if in_file_loop and any(
                        term in line.lower() for term in ["cancelled", "cancellation"]
                    ):
                        cancellation_checks_in_loop.append((i, line.strip()))

                    # End of loop detection (basic)
                    if (
                        in_file_loop
                        and line.strip()
                        and not line.startswith(" ")
                        and not line.startswith("\t")
                    ):
                        in_file_loop = False

                # CRITICAL ASSERTION: Cancellation checks in file loop must be BEFORE file.result()
                # This ensures we check between files, not during file processing
                if file_result_line and cancellation_checks_in_loop:
                    for cancel_line, cancel_text in cancellation_checks_in_loop:
                        assert cancel_line < file_result_line, (
                            f"Cancellation check '{cancel_text}' at line {cancel_line} occurs AFTER "
                            f"file.result() at line {file_result_line}. This violates between-files-only cancellation."
                        )

    def test_qdrant_atomic_method_name_accuracy(self):
        """
        CRITICAL TEST: Verify that upsert_points_atomic either provides true atomicity
        or is renamed to not claim atomicity.

        This examines the method implementation to verify its atomicity claims.
        """
        from code_indexer.services.qdrant import QdrantClient

        method = QdrantClient.upsert_points_batched
        source_code = inspect.getsource(method)

        # Check if the method actually provides atomicity
        # Look for patterns that indicate non-atomic behavior
        non_atomic_patterns = [
            "for i in range",  # Batch processing loops
            "batch =",  # Batch splitting
            ".upsert_points(",  # Calling non-atomic method
        ]

        found_non_atomic_patterns = []
        lines = source_code.split("\n")

        for i, line in enumerate(lines):
            for pattern in non_atomic_patterns:
                if pattern in line:
                    found_non_atomic_patterns.append((i, line.strip(), pattern))

        if found_non_atomic_patterns:
            # If non-atomic patterns exist, method should not claim atomicity
            method_docstring = inspect.getdoc(method) or ""

            # Check if docstring claims atomicity (but not disclaims it)
            docstring_lower = method_docstring.lower()

            # Look for positive atomic claims, but ignore disclaimers
            atomic_claims = any(
                term in docstring_lower
                for term in ["all-or-nothing", "either all points", "prevents partial"]
            )

            # Check for atomicity claims that aren't disclaimers
            if "atomic" in docstring_lower and "not atomic" not in docstring_lower:
                atomic_claims = True

            if atomic_claims:
                assert False, (
                    f"upsert_points_batched claims atomicity in docstring but contains non-atomic patterns: "
                    f"{found_non_atomic_patterns}. Method should not claim atomicity in documentation."
                )

    def test_file_processing_result_pattern_validates_success(self):
        """
        VALIDATION TEST: Ensure that files either complete successfully or
        fail completely - no partial success states that could indicate
        mid-process cancellation.
        """
        method = FileChunkingManager._process_file_complete_lifecycle
        source_code = inspect.getsource(method)

        # Look for FileProcessingResult creation patterns
        lines = source_code.split("\n")

        result_creations = []
        for i, line in enumerate(lines):
            if "FileProcessingResult(" in line:
                result_creations.append((i, line.strip()))

        # Verify that successful results only occur after complete processing
        for line_num, line_text in result_creations:
            if "success=True" in line_text:
                # This success result should only occur after upsert completion
                # We can't easily validate this in static analysis, but we can
                # ensure that there are no obvious mid-process success returns

                # Check that successful results are not inside chunk processing loops
                context_lines = source_code.split("\n")[
                    max(0, line_num - 10) : line_num
                ]
                context = "\n".join(context_lines)

                if (
                    "for chunk" in context.lower()
                    or "enumerate(chunk" in context.lower()
                ):
                    assert False, (
                        f"Found FileProcessingResult(success=True) at line {line_num} inside chunk processing loop. "
                        f"This suggests mid-process success reporting which violates file atomicity."
                    )

    def test_fixed_implementation_validates_correctly(self):
        """
        VALIDATION TEST: This test verifies that our fixes worked correctly
        by confirming that cancellation checks have been removed from file processing.

        This test should PASS after implementing the simple cancellation strategy.
        """
        # This test documents what we expect to find in the BROKEN current implementation
        method = FileChunkingManager._process_file_complete_lifecycle
        source_code = inspect.getsource(method)

        # We EXPECT to find cancellation checks in the current broken implementation
        cancellation_found = any(
            term in source_code.lower()
            for term in ["_cancellation_requested", "cancellation_event"]
        )

        # FIXED IMPLEMENTATION: Should NOT contain mid-process cancellation checks
        # This proves our fixes worked correctly
        assert not cancellation_found, (
            "Implementation should not contain mid-process cancellation checks after fixes. "
            "Cancellation should only be checked between files, not during file processing."
        )
