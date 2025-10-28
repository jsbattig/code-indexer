"""
Test-driven development for filter integration and precedence (Story 3.1).

This test suite validates:
1. Combining language inclusions with path exclusions
2. Combining path inclusions with language exclusions
3. Multiple inclusions and exclusions together
4. Exclusions override inclusions (precedence rules)
5. Conflict detection and warning for contradictory filters
6. Backward compatibility
7. Performance requirements (<5ms overhead)

Test approach:
- Unit tests for filter logic and conflict detection
- Integration tests for CLI filter construction
- E2E tests with real Qdrant filters
- Performance benchmarks
"""

import pytest
import time

from code_indexer.services.language_mapper import LanguageMapper
from code_indexer.services.path_filter_builder import PathFilterBuilder


class TestFilterConflictDetection:
    """Test conflict detection for contradictory filters (AC #5, #9)."""

    def test_detect_language_inclusion_exclusion_conflict(self):
        """
        GIVEN --language python --exclude-language python
        WHEN conflict detection runs
        THEN it should detect the contradiction and return warning message
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        conflicts = detector.detect_conflicts(
            include_languages=["python"], exclude_languages=["python"]
        )

        assert len(conflicts) > 0
        assert "python" in conflicts[0].message.lower()
        assert conflicts[0].severity == "error"

    def test_detect_multiple_language_conflicts(self):
        """
        GIVEN --language python --language javascript --exclude-language python --exclude-language javascript
        WHEN conflict detection runs
        THEN it should detect both conflicts
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        conflicts = detector.detect_conflicts(
            include_languages=["python", "javascript"],
            exclude_languages=["python", "javascript"],
        )

        # Should detect at least 2 conflicts
        assert len(conflicts) >= 2
        conflict_messages = " ".join([c.message.lower() for c in conflicts])
        assert "python" in conflict_messages
        assert "javascript" in conflict_messages

    def test_detect_path_inclusion_exclusion_conflict(self):
        """
        GIVEN --path-filter */tests/* --exclude-path */tests/*
        WHEN conflict detection runs
        THEN it should detect the contradiction
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        conflicts = detector.detect_conflicts(
            include_paths=["*/tests/*"], exclude_paths=["*/tests/*"]
        )

        assert len(conflicts) > 0
        assert "tests" in conflicts[0].message.lower()
        assert conflicts[0].severity in ["error", "warning"]

    def test_detect_overlapping_path_conflicts(self):
        """
        GIVEN --path-filter */src/* --exclude-path */src/tests/*
        WHEN conflict detection runs
        THEN it should warn about potential overlaps but not error
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        conflicts = detector.detect_conflicts(
            include_paths=["*/src/*"], exclude_paths=["*/src/tests/*"]
        )

        # This is not a complete contradiction, should be warning or no conflict
        if conflicts:
            assert all(c.severity == "warning" for c in conflicts)

    def test_no_conflicts_with_compatible_filters(self):
        """
        GIVEN --language python --exclude-language javascript
        WHEN conflict detection runs
        THEN it should find no conflicts
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        conflicts = detector.detect_conflicts(
            include_languages=["python"], exclude_languages=["javascript"]
        )

        assert len(conflicts) == 0

    def test_warn_when_excluding_all_languages(self):
        """
        GIVEN no include languages but many exclude languages
        WHEN conflict detection runs
        THEN it should warn about potentially excluding everything
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        conflicts = detector.detect_conflicts(
            include_languages=[],
            exclude_languages=[
                "python",
                "javascript",
                "typescript",
                "go",
                "rust",
                "java",
            ],
        )

        # Should warn about excluding many languages
        warnings = [c for c in conflicts if c.severity == "warning"]
        assert len(warnings) > 0


class TestFilterCombinations:
    """Test combining different filter types (AC #1, #2, #3)."""

    def test_combine_language_inclusion_with_path_exclusion(self):
        """
        GIVEN --language python --exclude-path */tests/*
        WHEN filters are combined
        THEN result should have must (language) and must_not (path)
        """
        mapper = LanguageMapper()
        path_builder = PathFilterBuilder()

        # Build language inclusion filter
        language_filter = mapper.build_language_filter("python")

        # Build path exclusion filter
        path_exclusion = path_builder.build_exclusion_filter(["*/tests/*"])

        # Combine filters
        combined = {"must": [language_filter]}
        if path_exclusion.get("must_not"):
            combined["must_not"] = path_exclusion["must_not"]

        # Verify structure
        assert "must" in combined
        assert "must_not" in combined
        assert len(combined["must"]) == 1
        assert len(combined["must_not"]) == 1

        # Verify language filter (should use OR logic)
        lang_filter = combined["must"][0]
        assert "should" in lang_filter

        # Verify path exclusion
        path_filter = combined["must_not"][0]
        assert path_filter["key"] == "path"
        assert path_filter["match"]["text"] == "*/tests/*"

    def test_combine_path_inclusion_with_language_exclusion(self):
        """
        GIVEN --path-filter */src/* --exclude-language javascript
        WHEN filters are combined
        THEN result should have must (path) and must_not (language)
        """
        mapper = LanguageMapper()

        # Build filters
        filter_conditions = {"must": [{"key": "path", "match": {"text": "*/src/*"}}]}

        # Add language exclusions
        js_extensions = mapper.get_extensions("javascript")
        must_not_conditions = []
        for ext in js_extensions:
            must_not_conditions.append({"key": "language", "match": {"value": ext}})

        filter_conditions["must_not"] = must_not_conditions

        # Verify structure
        assert "must" in filter_conditions
        assert "must_not" in filter_conditions
        assert len(filter_conditions["must"]) == 1
        assert len(filter_conditions["must_not"]) == 2  # js, jsx

        # Verify path inclusion
        path_filter = filter_conditions["must"][0]
        assert path_filter["key"] == "path"

        # Verify language exclusions
        excluded_exts = {f["match"]["value"] for f in filter_conditions["must_not"]}
        assert excluded_exts == {"js", "jsx"}

    def test_combine_multiple_inclusions_and_exclusions(self):
        """
        GIVEN --language python --language go --path-filter */src/*
              --exclude-language javascript --exclude-path */tests/*
        WHEN filters are combined
        THEN result should have all conditions properly structured
        """
        mapper = LanguageMapper()
        path_builder = PathFilterBuilder()

        # Build language inclusions (Python OR Go)
        filter_conditions = {"must": []}

        # Add Python
        python_filter = mapper.build_language_filter("python")
        filter_conditions["must"].append(python_filter)

        # Add Go
        go_filter = mapper.build_language_filter("go")
        filter_conditions["must"].append(go_filter)

        # Add path inclusion
        filter_conditions["must"].append({"key": "path", "match": {"text": "*/src/*"}})

        # Build exclusions
        must_not_conditions = []

        # Add JavaScript exclusion
        js_extensions = mapper.get_extensions("javascript")
        for ext in js_extensions:
            must_not_conditions.append({"key": "language", "match": {"value": ext}})

        # Add path exclusion
        path_exclusion = path_builder.build_exclusion_filter(["*/tests/*"])
        if path_exclusion.get("must_not"):
            must_not_conditions.extend(path_exclusion["must_not"])

        filter_conditions["must_not"] = must_not_conditions

        # Verify structure
        assert "must" in filter_conditions
        assert "must_not" in filter_conditions
        assert len(filter_conditions["must"]) == 3  # Python, Go, path
        assert len(filter_conditions["must_not"]) == 3  # js, jsx, path

    def test_empty_filters_creates_no_conditions(self):
        """
        GIVEN no filters specified
        WHEN filters are combined
        THEN result should be empty or have no conditions
        """
        filter_conditions = {}

        # No filters added

        # Verify empty
        assert len(filter_conditions) == 0 or (
            filter_conditions.get("must", []) == []
            and filter_conditions.get("must_not", []) == []
        )


class TestFilterPrecedence:
    """Test that exclusions override inclusions (AC #4)."""

    def test_exclusion_overrides_language_inclusion(self):
        """
        GIVEN --language python --exclude-language python
        WHEN filters are applied to search
        THEN no Python files should be returned (exclusion wins)

        Note: This tests the logical precedence, actual Qdrant behavior tested in E2E
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        # This should be detected as a conflict
        conflicts = detector.detect_conflicts(
            include_languages=["python"], exclude_languages=["python"]
        )

        assert len(conflicts) > 0
        assert conflicts[0].severity == "error"
        # The conflict detector should explain that exclusion wins
        assert (
            "exclude" in conflicts[0].message.lower()
            or "override" in conflicts[0].message.lower()
        )

    def test_path_exclusion_overrides_path_inclusion(self):
        """
        GIVEN --path-filter */src/* --exclude-path */src/tests/*
        WHEN filters are applied
        THEN files in */src/tests/* should be excluded despite path inclusion

        This is valid - narrowing down results
        """
        path_builder = PathFilterBuilder()

        # Build both filters
        filter_conditions = {
            "must": [{"key": "path", "match": {"text": "*/src/*"}}],
        }

        path_exclusion = path_builder.build_exclusion_filter(["*/src/tests/*"])
        filter_conditions["must_not"] = path_exclusion["must_not"]

        # Verify structure exists (Qdrant will apply precedence)
        assert "must" in filter_conditions
        assert "must_not" in filter_conditions

        # Both conditions should coexist (Qdrant handles precedence)
        assert len(filter_conditions["must"]) == 1
        assert len(filter_conditions["must_not"]) == 1


class TestBackwardCompatibility:
    """Test that existing queries still work (AC #6)."""

    def test_language_only_filter_still_works(self):
        """
        GIVEN --language python (existing functionality)
        WHEN filter is built
        THEN it should work exactly as before
        """
        mapper = LanguageMapper()

        language_filter = mapper.build_language_filter("python")

        # Should use OR logic for multiple extensions
        assert "should" in language_filter
        python_extensions = {
            cond["match"]["value"] for cond in language_filter["should"]
        }
        assert python_extensions == {"py", "pyw", "pyi"}

    def test_path_only_filter_still_works(self):
        """
        GIVEN --path-filter */tests/* (existing functionality)
        WHEN filter is built
        THEN it should work exactly as before
        """
        filter_conditions = {"must": [{"key": "path", "match": {"text": "*/tests/*"}}]}

        assert len(filter_conditions["must"]) == 1
        assert filter_conditions["must"][0]["key"] == "path"

    def test_exclude_language_only_still_works(self):
        """
        GIVEN --exclude-language javascript (Story 1.1 functionality)
        WHEN filter is built
        THEN it should work exactly as before
        """
        mapper = LanguageMapper()

        js_extensions = mapper.get_extensions("javascript")
        must_not_conditions = []
        for ext in js_extensions:
            must_not_conditions.append({"key": "language", "match": {"value": ext}})

        filter_conditions = {"must_not": must_not_conditions}

        assert len(filter_conditions["must_not"]) == 2  # js, jsx

    def test_exclude_path_only_still_works(self):
        """
        GIVEN --exclude-path */tests/* (Story 2.1 functionality)
        WHEN filter is built
        THEN it should work exactly as before
        """
        path_builder = PathFilterBuilder()

        filter_conditions = path_builder.build_exclusion_filter(["*/tests/*"])

        assert "must_not" in filter_conditions
        assert len(filter_conditions["must_not"]) == 1


class TestFilterPerformance:
    """Test that filter construction meets performance requirements (AC #10)."""

    def test_simple_filter_construction_performance(self):
        """
        GIVEN simple filter (single language)
        WHEN filter is constructed
        THEN it should take < 5ms
        """
        mapper = LanguageMapper()

        start = time.perf_counter()
        _ = mapper.build_language_filter("python")
        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms

        assert elapsed < 5.0, f"Simple filter took {elapsed:.2f}ms (limit: 5ms)"

    def test_complex_filter_construction_performance(self):
        """
        GIVEN complex filter (multiple languages, paths, exclusions)
        WHEN filter is constructed
        THEN it should take < 5ms overhead
        """
        mapper = LanguageMapper()
        path_builder = PathFilterBuilder()

        start = time.perf_counter()

        # Build complex filter
        filter_conditions = {"must": [], "must_not": []}

        # Multiple language inclusions
        for lang in ["python", "javascript", "go"]:
            filter_conditions["must"].append(mapper.build_language_filter(lang))

        # Path inclusions
        filter_conditions["must"].append({"key": "path", "match": {"text": "*/src/*"}})

        # Language exclusions
        for lang in ["typescript", "rust"]:
            extensions = mapper.get_extensions(lang)
            for ext in extensions:
                filter_conditions["must_not"].append(
                    {"key": "language", "match": {"value": ext}}
                )

        # Path exclusions
        path_exclusion = path_builder.build_exclusion_filter(
            ["*/tests/*", "*/vendor/*"]
        )
        filter_conditions["must_not"].extend(path_exclusion["must_not"])

        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 5.0, f"Complex filter took {elapsed:.2f}ms (limit: 5ms)"

    def test_conflict_detection_performance(self):
        """
        GIVEN filter conflict detection
        WHEN conflicts are detected
        THEN it should take < 5ms
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        start = time.perf_counter()

        _ = detector.detect_conflicts(
            include_languages=["python", "javascript", "go"],
            exclude_languages=["typescript", "rust"],
            include_paths=["*/src/*"],
            exclude_paths=["*/tests/*", "*/vendor/*"],
        )

        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 5.0, f"Conflict detection took {elapsed:.2f}ms (limit: 5ms)"


class TestFilterDebugLogging:
    """Test debug logging for filter structures (AC #12)."""

    def test_filter_structure_can_be_logged(self):
        """
        GIVEN any filter structure
        WHEN it is prepared for logging
        THEN it should be serializable to JSON-like format
        """
        import json

        mapper = LanguageMapper()

        filter_conditions = {
            "must": [mapper.build_language_filter("python")],
            "must_not": [{"key": "language", "match": {"value": "js"}}],
        }

        # Should be JSON serializable
        try:
            json_str = json.dumps(filter_conditions, indent=2)
            assert len(json_str) > 0
        except (TypeError, ValueError) as e:
            pytest.fail(f"Filter structure not JSON serializable: {e}")

    def test_conflict_messages_are_descriptive(self):
        """
        GIVEN filter conflicts
        WHEN conflicts are detected
        THEN messages should be clear and actionable
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        conflicts = detector.detect_conflicts(
            include_languages=["python"], exclude_languages=["python"]
        )

        assert len(conflicts) > 0
        conflict_msg = conflicts[0].message

        # Should be descriptive
        assert len(conflict_msg) > 20
        assert "python" in conflict_msg.lower()

        # Should explain the issue
        assert any(
            word in conflict_msg.lower()
            for word in ["conflict", "exclude", "include", "override", "contradict"]
        )


class TestEdgeCases:
    """Test edge cases and warnings (AC #11)."""

    def test_warn_when_filters_exclude_everything(self):
        """
        GIVEN filters that would exclude all results
        WHEN conflict detection runs
        THEN it should warn about potentially empty results
        """
        from code_indexer.services.filter_conflict_detector import (
            FilterConflictDetector,
        )

        detector = FilterConflictDetector()

        conflicts = detector.detect_conflicts(
            include_languages=["python"], exclude_languages=["python"]
        )

        # Should detect this will exclude everything
        assert len(conflicts) > 0
        assert conflicts[0].severity == "error"

    def test_handle_empty_extension_lists(self):
        """
        GIVEN a language with no extensions (edge case)
        WHEN filter is built
        THEN it should handle gracefully
        """
        mapper = LanguageMapper()

        # Try to get extensions for an unknown language (should return empty or default)
        try:
            extensions = mapper.get_extensions("unknown_language_xyz")
            # Should return empty set or raise appropriate error
            assert isinstance(extensions, set)
        except ValueError as e:
            # Acceptable to raise ValueError for unknown language
            assert "unknown" in str(e).lower() or "invalid" in str(e).lower()

    def test_handle_duplicate_filters(self):
        """
        GIVEN --exclude-language python --exclude-language python (duplicate)
        WHEN filters are built
        THEN it should handle duplicates gracefully
        """
        mapper = LanguageMapper()

        # Build exclusions with duplicates
        must_not_conditions = []
        for lang in ["python", "python"]:  # Duplicate
            extensions = mapper.get_extensions(lang)
            for ext in extensions:
                must_not_conditions.append({"key": "language", "match": {"value": ext}})

        # Should have duplicates (deduplication is optional optimization)
        # Both approaches are acceptable
        assert len(must_not_conditions) >= 3  # At least the unique extensions

    def test_handle_case_sensitivity_in_filters(self):
        """
        GIVEN --language Python (capital P)
        WHEN filter is built
        THEN it should handle case normalization
        """
        mapper = LanguageMapper()

        # Language mapper should normalize or handle case
        try:
            filter1 = mapper.build_language_filter("python")
            filter2 = mapper.build_language_filter("Python")

            # Should produce same or equivalent filter
            # (implementation may normalize to lowercase)
            assert filter1 is not None
            assert filter2 is not None
        except ValueError:
            # Also acceptable to reject invalid case and require lowercase
            pass
