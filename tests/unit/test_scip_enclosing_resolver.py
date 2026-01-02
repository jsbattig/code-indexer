"""Unit tests for SCIP enclosing symbol resolver."""

from code_indexer.scip.database.enclosing_resolver import EnclosingSymbolResolver


class TestEnclosingRangeResolution:
    """Test enclosing symbol resolution using SCIP enclosing_range."""

    def test_resolve_by_enclosing_range(self):
        """
        Test resolution using SCIP enclosing_range field.

        Given occurrences with enclosing_range fields
        When resolving enclosing symbol for a reference
        Then the symbol matching the enclosing_range is returned
        """
        # Create symbol map
        symbol_map = {
            "test.py::func().": 1,
            "test.py::ClassA#": 2,
            "test.py::method().": 3,
        }

        # Create occurrences (definitions and references)
        occurrences = [
            # Definition: func at lines 10-15
            {
                "symbol_name": "test.py::func().",
                "document_index": 0,
                "start_line": 10,
                "start_char": 0,
                "end_line": 15,
                "end_char": 0,
                "role": 1,  # Definition
                "enclosing_range_start_line": None,
                "enclosing_range_start_char": None,
                "enclosing_range_end_line": None,
                "enclosing_range_end_char": None,
            },
            # Reference inside func with enclosing_range pointing to func
            {
                "symbol_name": "test.py::ClassA#",
                "document_index": 0,
                "start_line": 12,
                "start_char": 4,
                "end_line": 12,
                "end_char": 10,
                "role": 2,  # Reference
                "enclosing_range_start_line": 10,
                "enclosing_range_start_char": 0,
                "enclosing_range_end_line": 15,
                "enclosing_range_end_char": 0,
            },
        ]

        # Build resolver
        resolver = EnclosingSymbolResolver()
        resolver.build_enclosing_range_map(occurrences, symbol_map)

        # Resolve enclosing symbol for the reference
        reference = occurrences[1]
        enclosing_id = resolver.resolve(reference)

        # Should resolve to func (symbol_id = 1)
        assert enclosing_id == 1


class TestProximityResolution:
    """Test enclosing symbol resolution using proximity heuristic."""

    def test_resolve_by_proximity_basic(self):
        """
        Test proximity heuristic finds nearest definition before occurrence.

        Given occurrences without enclosing_range fields
        When resolving enclosing symbol for a reference
        Then the nearest definition before the reference line is returned
        """
        # Create symbol map
        symbol_map = {
            "test.py::func_a().": 1,
            "test.py::func_b().": 2,
            "test.py::helper().": 3,
        }

        # Create occurrences with NO enclosing_range (82.5% of cases)
        occurrences = [
            # Definition: func_a at line 10
            {
                "symbol_name": "test.py::func_a().",
                "document_index": 0,
                "start_line": 10,
                "start_char": 0,
                "end_line": 10,
                "end_char": 6,
                "role": 1,  # Definition
                "enclosing_range_start_line": None,
                "enclosing_range_start_char": None,
                "enclosing_range_end_line": None,
                "enclosing_range_end_char": None,
            },
            # Definition: func_b at line 20
            {
                "symbol_name": "test.py::func_b().",
                "document_index": 0,
                "start_line": 20,
                "start_char": 0,
                "end_line": 20,
                "end_char": 6,
                "role": 1,  # Definition
                "enclosing_range_start_line": None,
                "enclosing_range_start_char": None,
                "enclosing_range_end_line": None,
                "enclosing_range_end_char": None,
            },
            # Reference: call to helper at line 15 (inside func_a)
            {
                "symbol_name": "test.py::helper().",
                "document_index": 0,
                "start_line": 15,
                "start_char": 4,
                "end_line": 15,
                "end_char": 10,
                "role": 2,  # Reference
                "enclosing_range_start_line": None,
                "enclosing_range_start_char": None,
                "enclosing_range_end_line": None,
                "enclosing_range_end_char": None,
            },
        ]

        # Build resolver
        resolver = EnclosingSymbolResolver()
        resolver.build_enclosing_range_map(occurrences, symbol_map)

        # Resolve enclosing symbol for the reference at line 15
        reference = occurrences[2]
        enclosing_id = resolver.resolve(reference)

        # Should resolve to func_a (symbol_id = 1) - nearest definition before line 15
        assert enclosing_id == 1
