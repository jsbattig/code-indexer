"""Enclosing symbol resolution for SCIP call graph generation."""

from typing import Any, Dict, List, Optional


class EnclosingSymbolResolver:
    """
    Resolves which symbol encloses each occurrence (for call graph caller determination).

    Uses hybrid strategy:
    1. Primary: Use SCIP enclosing_range when present (~17.5% of occurrences)
    2. Fallback: Proximity heuristic - find nearest definition before occurrence (~82.5%)
    """

    def __init__(self):
        """Initialize resolver with empty caches."""
        self._enclosing_range_map: Dict[tuple, int] = {}  # (doc_index, range) -> symbol_id
        self._document_definitions: Dict[int, List[Dict[str, Any]]] = {}  # doc_index -> sorted definitions

    def build_enclosing_range_map(
        self, occurrences: List[Dict[str, Any]], symbol_map: Dict[str, int]
    ) -> None:
        """
        Build mapping from enclosing ranges to symbol IDs and document definitions for proximity.

        Filters out local variables and parameters from proximity resolution to prevent
        incorrect enclosing symbol detection when parameters are defined on same line as methods.

        Args:
            occurrences: List of occurrence dicts (must include definition occurrences)
            symbol_map: Mapping of symbol name to database ID
        """
        self._enclosing_range_map.clear()
        self._document_definitions.clear()

        # Find all definition occurrences and build range -> symbol mapping
        for occ in occurrences:
            # Check if this is a definition (role bit 1)
            if occ["role"] & 1:
                # Create range key
                range_key = (
                    occ["document_index"],
                    occ["start_line"],
                    occ["start_char"],
                    occ["end_line"],
                    occ["end_char"],
                )

                # Map this range to the symbol ID
                symbol_name = occ["symbol_name"]
                if symbol_name in symbol_map:
                    symbol_id = symbol_map[symbol_name]
                    self._enclosing_range_map[range_key] = symbol_id

                    # Also track for proximity resolution (exclude locals/parameters)
                    # Local variables/parameters should NOT be enclosing symbols for call graph
                    if not symbol_name.startswith("local "):
                        doc_index = occ["document_index"]
                        if doc_index not in self._document_definitions:
                            self._document_definitions[doc_index] = []

                        self._document_definitions[doc_index].append({
                            "symbol_id": symbol_id,
                            "line": occ["start_line"],
                        })

        # Sort definitions by line number for each document
        for doc_index in self._document_definitions:
            self._document_definitions[doc_index].sort(key=lambda d: d["line"])

    def resolve(self, occurrence: Dict[str, Any]) -> Optional[int]:
        """
        Resolve the enclosing symbol for an occurrence.

        Strategy:
        1. If occurrence has enclosing_range, look up symbol by range (17.5% of cases)
        2. Else, use proximity heuristic - find nearest definition before occurrence (82.5% of cases)

        Args:
            occurrence: Occurrence dict with location and optional enclosing_range

        Returns:
            Symbol ID of enclosing symbol, or None if not found
        """
        # Primary: Use enclosing_range if present
        if occurrence["enclosing_range_start_line"] is not None:
            range_key = (
                occurrence["document_index"],
                occurrence["enclosing_range_start_line"],
                occurrence["enclosing_range_start_char"],
                occurrence["enclosing_range_end_line"],
                occurrence["enclosing_range_end_char"],
            )

            if range_key in self._enclosing_range_map:
                return self._enclosing_range_map[range_key]

        # Fallback: Use proximity heuristic
        return self._resolve_by_proximity(occurrence)

    def _resolve_by_proximity(self, occurrence: Dict[str, Any]) -> Optional[int]:
        """
        Find nearest definition before occurrence line (proximity heuristic).

        Args:
            occurrence: Occurrence dict with document_index and start_line

        Returns:
            Symbol ID of nearest definition before occurrence, or None if not found
        """
        doc_index = occurrence["document_index"]
        occ_line = occurrence["start_line"]

        # Get definitions for this document
        if doc_index not in self._document_definitions:
            return None

        definitions = self._document_definitions[doc_index]

        # Find last definition before occurrence line
        candidate = None
        for defn in definitions:
            if defn["line"] <= occ_line:
                candidate = defn
            else:
                break

        return candidate["symbol_id"] if candidate else None
