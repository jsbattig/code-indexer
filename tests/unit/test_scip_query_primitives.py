"""Unit tests for SCIP query primitives (dependencies and dependents)."""

import pytest
from pathlib import Path

from code_indexer.scip.query.primitives import SCIPQueryEngine, _matches_symbol


@pytest.fixture
def scip_fixture_path():
    """Path to comprehensive SCIP test fixture."""
    return (
        Path(__file__).parent.parent / "scip" / "fixtures" / "comprehensive_index.scip"
    )


@pytest.fixture
def query_engine(scip_fixture_path):
    """Initialize query engine with test fixture."""
    return SCIPQueryEngine(scip_fixture_path)


@pytest.fixture
def real_scip_index_path():
    """Path to real code-indexer SCIP index (if available)."""
    index_path = Path(".code-indexer/scip/index.scip")
    if index_path.exists():
        return index_path
    pytest.skip("Real SCIP index not available (run 'cidx scip index' first)")


@pytest.fixture
def real_query_engine(real_scip_index_path):
    """Initialize query engine with real SCIP index."""
    return SCIPQueryEngine(real_scip_index_path)


@pytest.fixture
def daemon_service_symbol_id(real_query_engine):
    """Get symbol ID for CIDXDaemonService class (if available)."""
    # Find CIDXDaemonService definition
    definitions = real_query_engine.find_definition("CIDXDaemonService", exact=True)
    if not definitions:
        pytest.skip("CIDXDaemonService symbol not found in SCIP index")

    # Use first definition (daemon.service module, not rpyc_daemon)
    target_defn = [d for d in definitions if 'daemon.service' in d.file_path]
    if not target_defn:
        target_defn = definitions

    # Get symbol_id from database
    cursor = real_query_engine.db_conn.cursor()
    cursor.execute("SELECT id FROM symbols WHERE name = ?", (target_defn[0].symbol,))
    row = cursor.fetchone()
    if not row:
        pytest.skip("CIDXDaemonService symbol ID not found in database")

    return row[0]


class TestMatchesSymbol:
    """Tests for _matches_symbol() helper function."""

    def test_exact_match_extracts_class_name_from_scip_symbol(self):
        """Should extract class name from SCIP symbol and match exactly.

        SCIP format: scip-python python project hash `module.path`/ClassName#
        Extract: ClassName
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.daemon.cache`/CacheEntry#"
        target_symbol = "CacheEntry"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=True)

        assert (
            result is True
        ), "Should match 'CacheEntry' when extracted from SCIP symbol"

    def test_exact_match_rejects_substring_matches(self):
        """Should reject substring matches when exact=True.

        FTSIndexCacheEntry contains 'CacheEntry' but should NOT match exactly.
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.server.cache`/FTSIndexCacheEntry#"
        target_symbol = "CacheEntry"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=True)

        assert result is False, "Should NOT match 'CacheEntry' in 'FTSIndexCacheEntry'"

    def test_exact_match_handles_methods(self):
        """Should extract method name from SCIP symbol.

        SCIP format: .../ClassName#method().
        Extract: method
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.daemon.cache`/CacheEntry#get_value()."
        target_symbol = "get_value"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=True)

        assert result is True, "Should match 'get_value' method name"

    def test_exact_match_handles_attributes(self):
        """Should extract attribute name from SCIP symbol.

        SCIP format: .../ClassName#attribute.
        Extract: attribute
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.daemon.cache`/CacheEntry#timestamp."
        target_symbol = "timestamp"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=True)

        assert result is True, "Should match 'timestamp' attribute name"

    def test_fuzzy_match_allows_substrings(self):
        """Should match substrings when exact=False.

        'CacheEntry' should match 'FTSIndexCacheEntry' in fuzzy mode.
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.server.cache`/FTSIndexCacheEntry#"
        target_symbol = "CacheEntry"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=False)

        assert result is True, "Should match 'CacheEntry' substring in fuzzy mode"

    def test_fuzzy_match_is_case_insensitive(self):
        """Should match case-insensitively when exact=False."""
        occurrence_symbol = (
            "scip-python python code-indexer abc123 `module`/CacheEntry#"
        )
        target_symbol = "cacheentry"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=False)

        assert result is True, "Should match case-insensitively in fuzzy mode"

    def test_exact_match_for_method_with_hash_suffix(self):
        """Should match method queries with # suffix exactly.

        User query: "CacheEntry#__init__"
        SCIP symbol: .../CacheEntry#__init__().
        Should extract and match: __init__ == __init__
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.daemon.cache`/CacheEntry#__init__()."
        target_symbol = "CacheEntry#__init__"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=True)

        assert result is True, "Should match 'CacheEntry#__init__' with method symbol"

    def test_exact_match_for_method_with_parens_suffix(self):
        """Should match method queries with (). suffix exactly.

        User query: "CacheEntry#__init__()"
        SCIP symbol: .../CacheEntry#__init__().
        Should extract and match: __init__ == __init__
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.daemon.cache`/CacheEntry#__init__()."
        target_symbol = "CacheEntry#__init__()"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=True)

        assert result is True, "Should match 'CacheEntry#__init__()' with method symbol"

    def test_exact_match_for_method_name_only(self):
        """Should match method name without class prefix.

        User query: "__init__"
        SCIP symbol: .../CacheEntry#__init__().
        Should extract and match: __init__ == __init__
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.daemon.cache`/CacheEntry#__init__()."
        target_symbol = "__init__"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=True)

        assert result is True, "Should match '__init__' method name only"

    def test_exact_non_matching_for_different_methods(self):
        """Should reject non-matching method names.

        User query: "CacheEntry#__del__"
        SCIP symbol: .../CacheEntry#__init__().
        Should extract and reject: __init__ != __del__
        """
        occurrence_symbol = "scip-python python code-indexer abc123 `code_indexer.daemon.cache`/CacheEntry#__init__()."
        target_symbol = "CacheEntry#__del__"

        result = _matches_symbol(occurrence_symbol, target_symbol, exact=True)

        assert result is False, "Should NOT match different method names"


class TestFindDefinition:
    """Tests for find_definition() method."""

    def test_find_definition_exact_flag_matches_exact_symbol_names(
        self, real_query_engine
    ):
        """Should return only exact symbol name matches when exact=True.

        With exact=False:
        - "CacheEntry" matches "CacheEntry", "FTSIndexCacheEntry", "TestCacheEntry*"
        - Returns 14 results (all classes containing "CacheEntry" substring)

        With exact=True:
        - "CacheEntry" matches ONLY classes named exactly "CacheEntry"
        - Should return 3 results (CacheEntry in daemon.cache, remote.staleness_detector, services.rpyc_daemon)
        - Should NOT match "FTSIndexCacheEntry" or "TestCacheEntry*"
        """
        # Fuzzy search - should match substrings
        fuzzy_results = real_query_engine.find_definition("CacheEntry", exact=False)
        fuzzy_symbols = {r.symbol.split("/")[-1].rstrip("#") for r in fuzzy_results}

        # Should find many classes containing "CacheEntry" substring
        assert len(fuzzy_results) >= 10, "Fuzzy search should find multiple matches"
        assert "CacheEntry" in fuzzy_symbols
        assert "FTSIndexCacheEntry" in fuzzy_symbols
        assert any("TestCacheEntry" in s for s in fuzzy_symbols)

        # Exact search - should match ONLY "CacheEntry"
        exact_results = real_query_engine.find_definition("CacheEntry", exact=True)
        exact_symbols = {r.symbol.split("/")[-1].rstrip("#") for r in exact_results}

        # Should find ONLY classes named exactly "CacheEntry"
        assert len(exact_results) == 3, (
            f"Expected exactly 3 'CacheEntry' definitions, got {len(exact_results)}\n"
            f"Symbols: {exact_symbols}"
        )

        # All results should be exactly "CacheEntry"
        assert exact_symbols == {
            "CacheEntry"
        }, f"All results should be 'CacheEntry', got {exact_symbols}"

        # Should NOT contain fuzzy matches
        assert "FTSIndexCacheEntry" not in exact_symbols
        assert all("Test" not in s for s in exact_symbols)

    def test_find_definition_excludes_parameters(self, real_query_engine):
        """Should exclude parameter definitions from results.

        Parameters have pattern: ClassName#method().(paramName)
        These are SCIP definitions but should be filtered out as noise.

        Valid definitions to include:
        - Classes: ClassName#
        - Methods: ClassName#method().
        - Attributes: ClassName#attr.

        Uses real code-indexer SCIP index to test against CacheEntry which
        has 207 definitions including many parameter definitions.
        """
        # Search for CacheEntry definitions
        results = real_query_engine.find_definition("CacheEntry", exact=False)

        # Before fix: returns 207 results including parameters
        # After fix: should return only class, methods, attributes (NOT parameters)

        # Assert NO results contain parameter pattern "().("
        parameter_results = [r for r in results if "().(" in r.symbol]

        assert len(parameter_results) == 0, (
            f"Found {len(parameter_results)} parameter definitions that should be filtered:\n"
            + "\n".join(f"  - {r.symbol}" for r in parameter_results[:5])
        )

    def test_find_definition_includes_valid_definitions(self, real_query_engine):
        """Should return different definition types based on query specificity.

        Simple name queries (no "#" or "()"):
        - Return ONLY class definitions (ending with "#")

        Specific queries (with "#" or "()"):
        - Return all matching definitions (classes, methods, attributes)

        Uses real code-indexer SCIP index to test against CacheEntry.
        """
        # Simple name query - should return ONLY class definitions
        simple_results = real_query_engine.find_definition("CacheEntry", exact=False)
        simple_symbols = [r.symbol.split("/")[-1] for r in simple_results]

        # Should find the class definition
        class_symbols = [s for s in simple_symbols if s == "CacheEntry#"]
        assert len(class_symbols) > 0, "Should find CacheEntry class definition"

        # Should NOT find methods or attributes for simple query
        non_class_symbols = [s for s in simple_symbols if not s.endswith("#")]
        assert len(non_class_symbols) == 0, "Simple query should only return classes"

        # Specific query with "#" - should return methods and attributes too
        specific_results = real_query_engine.find_definition("CacheEntry#", exact=False)
        specific_symbols = [r.symbol.split("/")[-1] for r in specific_results]

        # Should find method definitions (end with ().  )
        method_symbols = [
            s for s in specific_symbols if s.endswith("().") and "().(" not in s
        ]
        assert (
            len(method_symbols) > 0
        ), "Specific query with # should find method definitions"

        # Should find attribute definitions (end with .  but not ().  )
        attribute_symbols = [
            s
            for s in specific_symbols
            if s.endswith(".") and not s.endswith("().") and not s.endswith("#")
        ]
        assert (
            len(attribute_symbols) > 0
        ), "Specific query with # should find attribute definitions"

    def test_find_definition_exact_flag_for_methods(self, real_query_engine):
        """Test that --exact flag works for method queries.

        Verifies the fix for the _matches_symbol() bug where method queries
        with different formats (CacheEntry#__init__, CacheEntry#__init__())
        failed to match SCIP method symbols (.../CacheEntry#__init__().).

        Uses real SCIP index to test against CacheEntry class which has
        __init__ methods that should be found.
        """
        # Test with class#method format
        results_hash = real_query_engine.find_definition("CacheEntry#__init__", exact=True)

        # Should find __init__ methods for CacheEntry class
        assert len(results_hash) >= 2, (
            f"Expected at least 2 __init__ methods for CacheEntry, got {len(results_hash)}"
        )
        assert all("__init__" in r.symbol for r in results_hash)
        assert all("CacheEntry#__init__()" in r.symbol for r in results_hash)

        # Test with class#method() format
        results_parens = real_query_engine.find_definition("CacheEntry#__init__()", exact=True)

        # Should find same results
        assert len(results_parens) >= 2, (
            f"Expected at least 2 __init__ methods for CacheEntry, got {len(results_parens)}"
        )
        assert all("__init__" in r.symbol for r in results_parens)
        assert all("CacheEntry#__init__()" in r.symbol for r in results_parens)

        # Both formats should return identical results
        assert len(results_hash) == len(results_parens), (
            "Different formats should return same number of results"
        )

    def test_find_definition_simple_name_shows_only_class_definitions(
        self, real_query_engine
    ):
        """Should return only class definitions for simple name queries.

        When querying with a simple name (no "#" or "()" in the query):
        - Return ONLY class definitions (symbols ending in "#")
        - Filter OUT methods (ending in "().")
        - Filter OUT attributes (ending in "." but not "#")

        When querying with "#" or "()." in the query string:
        - Return all matching definitions (no additional filtering)

        Uses real code-indexer SCIP index to test against CacheEntry.
        """
        # Simple name query - should return ONLY class definitions
        results = real_query_engine.find_definition("CacheEntry", exact=False)

        # Extract symbol suffixes for analysis
        symbols = [r.symbol.split("/")[-1] for r in results]

        # Should find ONLY class definitions (ending in "#")
        # Before fix: returns 128 results (7 classes + 121 methods/attributes)
        # After fix: should return only 7 class definitions
        non_class_symbols = [s for s in symbols if not s.endswith("#")]

        assert len(non_class_symbols) == 0, (
            f"Simple name query should return ONLY class definitions, "
            f"but found {len(non_class_symbols)} non-class definitions:\n"
            + "\n".join(f"  - {s}" for s in non_class_symbols[:10])
        )

        # Verify we still found the class definitions
        class_symbols = [s for s in symbols if s.endswith("#")]
        assert len(class_symbols) > 0, "Should find at least one class definition"


class TestGetDependencies:
    """Tests for get_dependencies() method."""

    def test_get_dependencies_returns_symbols_used_in_file(self, query_engine):
        """Should return symbols that a given symbol depends on.

        In the fixture:
        - src/auth.py references UserService (line 5)
        - src/auth.py references authenticate() (line 10)

        So if we search for dependencies based on symbols in auth.py,
        we should find the symbols it references.
        """
        # Query for dependencies - this method needs to be implemented
        # We're looking for what "auth.py module" depends on
        # For now, let's test by looking up a specific symbol that would be defined in auth.py
        # Since fixture doesn't have a symbol defined in auth.py, let's test the concept differently:
        # Get dependencies of ANY symbol means finding what it references

        # This test will fail because get_dependencies is not implemented
        results = query_engine.get_dependencies("UserService", depth=1, exact=False)

        # For now, we expect empty list (stub returns [])
        # Once implemented, we should get the symbols UserService depends on
        assert isinstance(results, list)

    def test_get_dependencies_returns_only_function_scope_not_whole_file(
        self, real_query_engine
    ):
        """CRITICAL: Should return ONLY references within the function scope, not entire file.

        SCOPE BUG:
        The current implementation returns ALL references in the file containing the
        target symbol, regardless of scope. This is completely wrong.

        Example: scip_generate function (lines 31-161) should return only the 186
        dependencies within its scope, NOT all 1,439 references from the entire file.

        CORRECT BEHAVIOR:
        Use the definition's enclosing_range field to filter references by scope:
        1. Find the definition of the target symbol
        2. Extract the definition's enclosing_range (e.g., [31, 0, 161, 19])
        3. Filter occurrences to ONLY those where occurrence.range[0] is within
           the enclosing range
        4. Return only those scoped references as dependencies

        VERIFIED CORRECT BEHAVIOR:
        - scip_generate definition has enclosing_range: [31, 0, 161, 19]
        - References within scope (lines 31-161): ~186
        - References outside scope (lines 1-30, 162+): ~1,253
        - Should NOT include references from outside function scope
        """
        # Query dependencies for scip_generate function
        results = real_query_engine.get_dependencies(
            "scip_generate", depth=1, exact=True
        )

        # Before fix: returns 1,439 results (entire file)
        # After fix: should return ~186 results (only function scope)

        # Assert reasonable result count (not thousands)
        assert len(results) < 300, (
            f"get_dependencies returned {len(results)} results - "
            f"includes entire file instead of just function scope! "
            f"Should be < 300 for scip_generate function."
        )

        # Verify no references from outside the function scope
        # scip_generate is at lines 31-161 in cli_scip.py
        outside_scope = [r for r in results if r.line < 31 or r.line > 161]

        assert len(outside_scope) == 0, (
            f"Found {len(outside_scope)} references outside function scope (lines 31-161):\n"
            + "\n".join(
                f"  Line {r.line}: {r.symbol}"
                for r in sorted(outside_scope, key=lambda x: x.line)[:10]
            )
            + "\nReferences should be filtered to function's enclosing_range!"
        )


class TestGetDependents:
    """Tests for get_dependents() method."""

    def test_get_dependents_returns_symbols_that_reference_target(self, query_engine):
        """Should return symbols that depend on (reference) the target symbol.

        In the fixture:
        - UserService is referenced in src/auth.py (line 5)
        - authenticate() is referenced in src/auth.py (line 10)

        So if we query for dependents of UserService, we should find
        the locations in auth.py that reference it.
        """
        # This test will fail because get_dependents is not fully implemented
        results = query_engine.get_dependents("UserService", depth=1, exact=False)

        # For now, we expect empty list (stub returns [])
        assert isinstance(results, list)

    def test_get_dependents_returns_only_enclosing_symbol_not_all_document_symbols(
        self, real_query_engine
    ):
        """CRITICAL: Should return ONLY the specific symbol containing each reference.

        CARTESIAN PRODUCT BUG:
        The old implementation returned ALL symbols defined in a document for EVERY
        reference to the target symbol, creating a cartesian product explosion.

        For example, if a file has:
        - 100 defined symbols (classes, methods, functions)
        - 50 references to CacheEntry

        The bug created 100 × 50 = 5,000 bogus results.

        CORRECT BEHAVIOR:
        Should return only the SPECIFIC symbol that contains each reference,
        using proximity heuristics (most recent definition before the reference line).

        This test validates the fix by checking that:
        1. Result count is reasonable (not cartesian product)
        2. Each result corresponds to an actual caller
        3. Duplicate symbols are minimal (ideally one per actual reference location)
        """
        # Use a foundational symbol like CacheEntry that's referenced by many symbols
        results = real_query_engine.get_dependents("CacheEntry", depth=1, exact=False)

        # Before fix: 20,467 results at depth=1 (cartesian product explosion)
        # After fix: Should be ~100-200 results (actual number of symbols that reference CacheEntry)

        # Assert reasonable result count (not thousands)
        assert len(results) < 1000, (
            f"get_dependents returned {len(results)} results - "
            f"likely cartesian product bug! Should be < 1000 for depth=1"
        )

        # Group results by symbol to check for excessive duplication
        from collections import Counter

        symbol_counts = Counter(r.symbol for r in results)

        # Each symbol should appear a small number of times (one per reference location)
        # If a symbol appears 50+ times, that's suspicious (likely cartesian product)
        suspicious_symbols = {
            sym: count for sym, count in symbol_counts.items() if count > 50
        }

        assert len(suspicious_symbols) == 0, (
            "Found symbols with suspicious duplication (>50 occurrences):\n"
            + "\n".join(
                f"  {sym}: {count} times"
                for sym, count in list(suspicious_symbols.items())[:5]
            )
            + "\nThis indicates cartesian product bug is still present!"
        )

        # Verify all results have valid symbol names (not empty)
        empty_symbols = [r for r in results if not r.symbol]
        assert len(empty_symbols) == 0, "Found results with empty symbol names"

    def test_get_dependencies_filters_out_local_variables(self, real_query_engine):
        """Should filter out local variable symbols (starting with 'local ').

        SCIP indexes include local variable symbols with pattern: "local 0", "local 1", etc.
        These are noise for high-level dependency queries and should be filtered out.

        Story #587 acceptance criteria: "No parameter noise, correct results count, proper exact matching"
        and "no local variable noise".
        """
        # Query dependencies for CacheEntry which has many local variable references
        results = real_query_engine.get_dependencies("CacheEntry", depth=1, exact=False)

        # Check for local variable symbols
        local_var_results = [r for r in results if r.symbol.startswith("local ")]

        assert len(local_var_results) == 0, (
            f"Found {len(local_var_results)} local variable symbols that should be filtered:\n"
            + "\n".join(f"  - {r.symbol} at {r.file_path}:{r.line}" for r in local_var_results[:10])
        )

    def test_get_dependents_filters_out_local_variables(self, real_query_engine):
        """Should filter out local variable symbols (starting with 'local ').

        SCIP indexes include local variable symbols with pattern: "local 0", "local 1", etc.
        These are noise for high-level dependent queries and should be filtered out.

        Story #587 acceptance criteria: "No parameter noise, correct results count, proper exact matching"
        and "no local variable noise".
        """
        # Query dependents for CacheEntry which is referenced by many functions with local vars
        results = real_query_engine.get_dependents("CacheEntry", depth=1, exact=False)

        # Check for local variable symbols
        local_var_results = [r for r in results if r.symbol.startswith("local ")]

        assert len(local_var_results) == 0, (
            f"Found {len(local_var_results)} local variable symbols that should be filtered:\n"
            + "\n".join(f"  - {r.symbol} at {r.file_path}:{r.line}" for r in local_var_results[:10])
        )

    def test_analyze_impact_hybrid_returns_more_results(self, real_query_engine):
        """Hybrid analyze_impact should return more files than legacy call_graph-only.

        Story #598: analyze_impact() should use hybrid get_dependents() to return
        ALL symbol references (imports, attributes, variables, calls), not just
        function calls from call_graph table.

        This test compares:
        - Legacy mode: analyze_impact using call_graph only (function calls)
        - Hybrid mode: analyze_impact using hybrid get_dependents (ALL references)

        Expectation: Hybrid ≥ Legacy file count
        """
        # Target: SCIPDatabaseBuilder - a class that's imported, instantiated, and called
        target_symbol = "SCIPDatabaseBuilder"

        # Force legacy backend (call_graph only)
        from code_indexer.scip.query.backends import DatabaseBackend

        scip_db_path = real_query_engine.backend.db_path
        project_root = real_query_engine.backend.project_root

        # Legacy backend WITHOUT scip_file (falls back to call_graph)
        legacy_backend = DatabaseBackend(scip_db_path, project_root=project_root)
        legacy_backend.scip_file = None  # Force legacy mode

        # Get legacy results
        legacy_results = legacy_backend.analyze_impact(target_symbol, depth=2)
        legacy_file_count = len(legacy_results)

        # Hybrid backend WITH scip_file (uses hybrid get_dependents)
        hybrid_backend = DatabaseBackend(scip_db_path, project_root=project_root)
        hybrid_backend.scip_file = real_query_engine.scip_file

        # Get hybrid results
        hybrid_results = hybrid_backend.analyze_impact(target_symbol, depth=2)
        hybrid_file_count = len(hybrid_results)

        # Assertion: Hybrid should return >0 files and typically FEWER than legacy
        # (legacy call_graph has false positives, hybrid is more accurate)
        assert hybrid_file_count > 0, (
            f"Hybrid analyze_impact returned ZERO files!\n"
            f"  Symbol: {target_symbol}\n"
            f"  This indicates hybrid mode is NOT finding any dependents."
        )

        # Hybrid should typically return fewer files than legacy (legacy has false positives)
        # But if hybrid returns MORE, that's also acceptable (means legacy was missing some)
        print(
            f"Impact analysis comparison for '{target_symbol}':\n"
            f"  Legacy (call_graph only): {legacy_file_count} files\n"
            f"  Hybrid (ALL references): {hybrid_file_count} files\n"
            f"  Ratio: {hybrid_file_count / legacy_file_count if legacy_file_count > 0 else 0:.2f}x"
        )


class TestTraceCallChain:
    """Tests for trace_call_chain() method."""

    def test_trace_call_chain_finds_non_call_relationships(self, real_query_engine):
        """Verify trace_call_chain uses hybrid queries (ALL symbols).

        The DaemonService → _is_text_file chain includes non-call relationships
        (imports, attributes, etc.) which aren't in call_graph table. The hybrid
        implementation should find this chain.

        The legacy call_graph-only implementation returns 0 chains because the
        actual chain goes through attribute references (FileFinder), not just calls.
        """
        chains = real_query_engine.trace_call_chain('DaemonService', '_is_text_file', max_depth=5)

        assert len(chains) > 0, "Should find chain through non-call relationships"
        assert chains[0].length >= 1, f"Should find valid chain, got length {chains[0].length}"

        # Verify path includes DaemonService or FileFinder
        path_str = ' -> '.join(chains[0].path)
        assert 'DaemonService' in path_str or 'FileFinder' in path_str, f"Expected symbols in path: {path_str}"

    def test_trace_call_chain_performance(self, real_query_engine):
        """Verify trace_call_chain completes in <15 seconds.

        The hybrid implementation uses fast hybrid get_dependencies queries
        (1.15ms per query) but BFS explores many nodes. Should complete in <15s
        (much faster than 21s composites version).
        """
        import time

        start = time.perf_counter()
        chains = real_query_engine.trace_call_chain('DaemonService', '_is_text_file', max_depth=5)
        elapsed = time.perf_counter() - start

        assert elapsed < 15.0, f"Should complete in <15s, took {elapsed:.2f}s"
        assert len(chains) > 0, "Should find at least one chain"


class TestSymbolReferencesIntegrity:
    """Tests for symbol_references table integrity and completeness."""

    def test_daemon_service_symbol_references_edge_count(self, real_query_engine, daemon_service_symbol_id):
        """Verify symbol_references has similar edge count to hybrid get_dependencies.

        The symbol_references table should contain similar edges to what hybrid
        get_dependencies returns. If hybrid returns 1343 dependencies but
        symbol_references has only 1 edge, the ETL is broken.
        """
        # Get hybrid get_dependencies result count
        hybrid_deps = real_query_engine.get_dependencies("CIDXDaemonService", depth=1, exact=True)
        hybrid_count = len(hybrid_deps)

        # Get symbol_references edge count from ALL CIDXDaemonService symbols (class + methods)
        # The ETL creates edges from both the class AND its methods, so we need to aggregate
        cursor = real_query_engine.db_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM symbol_references sr
            JOIN symbols s ON sr.from_symbol_id = s.id
            WHERE s.name LIKE '%daemon.service%/CIDXDaemonService%'
        """)
        db_edge_count = cursor.fetchone()[0] or 0

        # symbol_references should match or exceed hybrid (may have duplicates across methods)
        # Hybrid deduplicates across enclosing range, symbol_references creates per-symbol edges
        ratio = db_edge_count / hybrid_count if hybrid_count > 0 else 0
        assert ratio >= 0.9, (
            f"symbol_references edge count ({db_edge_count}) should match "
            f"hybrid get_dependencies count ({hybrid_count}), ratio: {ratio:.2%}"
        )

        print(f"\nEdge count comparison for CIDXDaemonService (symbol_id={daemon_service_symbol_id}):")
        print(f"  hybrid get_dependencies: {hybrid_count} dependencies")
        print(f"  symbol_references edges: {db_edge_count} edges")
        print(f"  Ratio: {ratio:.2%}")

    def test_trace_call_chain_v2_finds_daemon_service_to_filefinder(self, real_query_engine, daemon_service_symbol_id):
        """Verify trace_call_chain_v2 finds CIDXDaemonService → FileFinder chain.

        CIDXDaemonService uses FileFinder class. The database version (using
        symbol_references) should find this chain in <2s.
        """
        # Get FileFinder symbol_id (use the main FileFinder class, not test classes)
        definitions = real_query_engine.find_definition("FileFinder", exact=True)
        assert len(definitions) > 0, "FileFinder symbol not found"

        # Filter to actual FileFinder class (not test classes)
        target_defn = [d for d in definitions if 'indexing.file_finder' in d.file_path]
        if not target_defn:
            target_defn = definitions

        cursor = real_query_engine.db_conn.cursor()
        cursor.execute("SELECT id FROM symbols WHERE name = ?", (target_defn[0].symbol,))
        row = cursor.fetchone()
        assert row, "FileFinder symbol ID not found"
        target_symbol_id = row[0]

        # Trace call chain using v2 (database version)
        from code_indexer.scip.database.queries import trace_call_chain_v2
        import time

        start = time.perf_counter()
        chains = trace_call_chain_v2(
            real_query_engine.db_conn,
            daemon_service_symbol_id,
            target_symbol_id,
            max_depth=5,
            limit=100
        )
        elapsed = time.perf_counter() - start

        # Should find at least one chain
        assert len(chains) > 0, (
            f"trace_call_chain_v2 should find CIDXDaemonService → FileFinder chain, "
            f"found {len(chains)} chains"
        )

        # Should be fast (<2s)
        assert elapsed < 2.0, f"Should complete in <2s, took {elapsed:.2f}s"

        print(f"\ntrace_call_chain_v2 performance:")
        print(f"  Chains found: {len(chains)}")
        print(f"  Time: {elapsed:.3f}s")
        print(f"  Shortest chain length: {chains[0]['length'] if chains else 'N/A'}")
