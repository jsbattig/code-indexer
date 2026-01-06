"""
Tantivy Index Manager for full-text search indexing.

Manages Tantivy-based FTS indexes alongside semantic vector indexes,
providing fast exact text search capabilities.
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

if TYPE_CHECKING:
    from tantivy import Index, Schema  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class TantivyIndexManager:
    """
    Manages Tantivy full-text search index for CIDX.

    Thread Safety:
        The Tantivy writer is thread-safe at the Rust level (Arc<Mutex<...>>).
        However, concurrent calls to update_document() or delete_document()
        from multiple threads may result in unpredictable commit ordering.

        For watch mode with multiple handlers, this is acceptable because:
        - Each file operation is atomic (delete + add + commit)
        - Tantivy's MVCC architecture prevents read/write conflicts
        - Final state is eventually consistent regardless of commit order

    Performance Characteristics:
        - First operation: ~300-600ms (includes index initialization)
        - Subsequent operations: ~50-150ms per commit
        - Search visibility: Immediate after commit completes
        - Commit latency target: 5-50ms (actual: 100-150ms with overhead)
    """

    def __init__(self, index_dir: Path):
        """
        Initialize the Tantivy index manager.

        Args:
            index_dir: Directory where Tantivy index will be stored
        """
        self.index_dir = Path(index_dir)
        self._index: Optional[Index] = None
        self._schema: Optional[Schema] = None
        self._writer: Optional[Any] = None
        self._heap_size = 1_000_000_000  # Fixed 1GB heap size
        self._metadata_file = self.index_dir / "metadata.json"
        self._lock = threading.Lock()  # Thread safety for writer operations

        # Try to import tantivy
        try:
            import tantivy

            self._tantivy = tantivy
        except ImportError as e:
            logger.error("Tantivy library not installed")
            raise ImportError(
                "Tantivy is required for FTS indexing. "
                "Install it with: pip install tantivy==0.25.0"
            ) from e

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the Tantivy schema configuration.

        Returns:
            Dictionary describing the schema fields
        """
        if self._schema is None:
            self._create_schema()

        # Return dictionary representation for testing
        return {
            "path": "stored",
            "content": "tokenized",
            "content_raw": "stored",
            "identifiers": "simple_tokenizer",
            "line_start": "u64_indexed",
            "line_end": "u64_indexed",
            "language": "stored_text",
            "language_facet": "facet",
        }

    def _create_schema(self) -> None:
        """Create the Tantivy schema with required fields."""
        schema_builder = self._tantivy.SchemaBuilder()

        # path: stored field for file path
        schema_builder.add_text_field("path", stored=True)

        # content: tokenized field for full-text search
        schema_builder.add_text_field("content", stored=False)

        # content_raw: stored field for retrieving original content
        schema_builder.add_text_field("content_raw", stored=True)

        # identifiers: simple tokenizer for exact identifier matches
        schema_builder.add_text_field("identifiers", stored=True)

        # line_start/line_end: indexed u64 fields for line number filtering
        schema_builder.add_unsigned_field("line_start", indexed=True, stored=True)
        schema_builder.add_unsigned_field("line_end", indexed=True, stored=True)

        # language: stored as text field for retrieval AND facet for filtering
        schema_builder.add_text_field("language", stored=True)
        schema_builder.add_facet_field("language_facet")

        self._schema = schema_builder.build()

    def initialize_index(self, create_new: bool = True) -> None:
        """
        Initialize the Tantivy index.

        Args:
            create_new: If True, create new index. If False, open existing.

        Raises:
            PermissionError: If directory permissions are insufficient
            ImportError: If Tantivy library is not available
        """
        try:
            # Create directory if it doesn't exist
            if create_new:
                self.index_dir.mkdir(parents=True, exist_ok=True)

            # Check permissions
            if not self.index_dir.exists():
                raise PermissionError(
                    f"Cannot create index directory: {self.index_dir}"
                )

            # Test write permissions
            test_file = self.index_dir / ".permission_test"
            try:
                test_file.touch()
                test_file.unlink()
            except Exception as e:
                raise PermissionError(
                    f"Insufficient permissions for index directory: {self.index_dir}"
                ) from e

            # Create schema if needed
            if self._schema is None:
                self._create_schema()

            # Create or open index
            assert self._schema is not None  # For mypy
            if create_new or not (self.index_dir / "meta.json").exists():
                self._index = self._tantivy.Index(self._schema, str(self.index_dir))
                logger.info(
                    f"🔨 FULL FTS INDEX BUILD: Creating Tantivy index from scratch at {self.index_dir}"
                )
            else:
                self._index = self._tantivy.Index.open(str(self.index_dir))
                logger.info(f"Opened existing Tantivy index at {self.index_dir}")

            # Create writer with fixed heap size
            assert self._index is not None  # For mypy
            self._writer = self._index.writer(self._heap_size)

            # Save metadata
            self._save_metadata()

        except PermissionError:
            logger.error(f"Permission denied for index directory: {self.index_dir}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Tantivy index: {e}")
            raise

    def get_writer_heap_size(self) -> int:
        """
        Get the configured writer heap size.

        Returns:
            Heap size in bytes (1GB)
        """
        return self._heap_size

    def add_document(self, doc: Dict[str, Any]) -> None:
        """
        Add a document to the FTS index.

        Args:
            doc: Document dictionary with required fields

        Raises:
            ValueError: If required fields are missing
            RuntimeError: If writer is not initialized
        """
        if self._writer is None:
            raise RuntimeError(
                "Index writer not initialized. Call initialize_index() first."
            )

        # Validate required fields
        required_fields = [
            "path",
            "content",
            "content_raw",
            "identifiers",
            "line_start",
            "line_end",
            "language",
        ]
        missing_fields = [f for f in required_fields if f not in doc]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        try:
            # Create Tantivy document
            tantivy_doc = self._tantivy.Document()

            # Add fields
            tantivy_doc.add_text("path", doc["path"])
            tantivy_doc.add_text("content", doc["content"])
            tantivy_doc.add_text("content_raw", doc["content_raw"])

            # Add identifiers (convert list to space-separated string)
            identifiers_str = (
                " ".join(doc["identifiers"])
                if isinstance(doc["identifiers"], list)
                else str(doc["identifiers"])
            )
            tantivy_doc.add_text("identifiers", identifiers_str)

            # Add line numbers
            tantivy_doc.add_unsigned("line_start", int(doc["line_start"]))
            tantivy_doc.add_unsigned("line_end", int(doc["line_end"]))

            # Add language as text field (for retrieval) and facet (for filtering)
            tantivy_doc.add_text("language", doc["language"])
            from tantivy import Facet

            language_facet = Facet.from_string(f"/{doc['language']}")
            tantivy_doc.add_facet("language_facet", language_facet)

            # Add to writer (thread-safe)
            with self._lock:
                self._writer.add_document(tantivy_doc)

        except Exception as e:
            logger.error(f"Failed to add document: {e}")
            raise

    def commit(self) -> None:
        """
        Commit pending documents to the index (atomic operation).

        Raises:
            RuntimeError: If writer is not initialized
        """
        if self._writer is None:
            raise RuntimeError("Index writer not initialized")

        try:
            with self._lock:
                self._writer.commit()
            logger.info("Committed documents to Tantivy index")
        except Exception as e:
            logger.error(f"Failed to commit documents: {e}")
            raise

    def rollback(self) -> None:
        """
        Rollback uncommitted changes.

        Raises:
            RuntimeError: If writer is not initialized
        """
        if self._writer is None:
            raise RuntimeError("Index writer not initialized")

        try:
            self._writer.rollback()
            logger.info("Rolled back uncommitted changes")
        except Exception as e:
            logger.error(f"Failed to rollback changes: {e}")
            raise

    def get_document_count(self) -> int:
        """
        Get the number of documents in the index.

        Returns:
            Number of documents

        Raises:
            RuntimeError: If index is not initialized
        """
        if self._index is None:
            raise RuntimeError("Index not initialized")

        try:
            # Reload index to get latest count
            self._index.reload()
            searcher = self._index.searcher()
            # num_docs is a property, not a method
            return cast(int, searcher.num_docs)
        except Exception as e:
            logger.error(f"Failed to get document count: {e}")
            return 0

    def _build_search_query(
        self,
        query_text: str,
        search_field: str,
        edit_distance: int,
        tantivy: Any,
        TantivyQuery: Any,
    ) -> Any:
        """
        Build Tantivy search query with proper AND semantics for multi-word queries.

        Query Building Strategy:
        - Single-term queries: Use existing behavior (backward compatibility)
        - Multi-word exact queries: Require ALL terms to match (AND semantics)
        - Multi-word fuzzy queries: Apply fuzzy matching to each term, combine with AND

        Args:
            query_text: Search query string
            search_field: Field to search ("content" or "content_raw")
            edit_distance: Fuzzy matching tolerance (0 for exact)
            tantivy: Tantivy module instance
            TantivyQuery: Tantivy Query class

        Returns:
            Tantivy query object

        Raises:
            RuntimeError: If index is not initialized
        """
        if self._index is None:
            raise RuntimeError("Index not initialized")

        # Split query into terms to detect single vs multi-word queries
        query_terms = query_text.split()
        is_multi_word = len(query_terms) > 1

        if edit_distance > 0:
            # FUZZY MATCHING: Apply fuzzy matching to each term independently
            if is_multi_word:
                # Multi-word fuzzy query: Apply fuzzy matching to each term, combine with AND
                # Example: "gloc pattern" with edit_distance=1 fuzzy-matches "glob" AND "pattern"
                fuzzy_queries = [
                    TantivyQuery.fuzzy_term_query(
                        self._schema,
                        search_field,
                        term,
                        distance=edit_distance,
                        transposition_cost_one=True,
                    )
                    for term in query_terms
                ]

                # Combine all fuzzy queries with AND semantics (all terms must fuzzy-match)
                subqueries = [(tantivy.Occur.Must, q) for q in fuzzy_queries]
                return TantivyQuery.boolean_query(subqueries)
            else:
                # Single-term fuzzy query: Use fuzzy_term_query directly (backward compatibility)
                return TantivyQuery.fuzzy_term_query(
                    self._schema,
                    search_field,
                    query_text,
                    distance=edit_distance,
                    transposition_cost_one=True,
                )
        else:
            # EXACT MATCHING: Require ALL terms to match
            if is_multi_word:
                # Multi-word exact query: Require ALL terms to exist (AND semantics)
                # Example: "gloc pattern" returns 0 results if "gloc" doesn't exist
                term_queries = [
                    self._index.parse_query(term, [search_field, "identifiers"])
                    for term in query_terms
                ]

                # Combine all term queries with AND semantics (all terms must match)
                subqueries = [(tantivy.Occur.Must, q) for q in term_queries]
                return TantivyQuery.boolean_query(subqueries)
            else:
                # Single-term exact query: Use standard query parser (backward compatibility)
                return self._index.parse_query(
                    query_text, [search_field, "identifiers"]
                )

    def search(
        self,
        query_text: str,
        case_sensitive: bool = False,
        edit_distance: int = 0,
        snippet_lines: int = 5,
        limit: int = 10,
        language_filter: Optional[str] = None,  # Deprecated: use languages
        languages: Optional[List[str]] = None,
        path_filters: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        exclude_languages: Optional[List[str]] = None,
        path_filter: Optional[str] = None,  # Deprecated: use path_filters
        query: Optional[str] = None,  # Backwards compatibility
        use_regex: bool = False,  # NEW: Enable regex pattern matching
    ) -> List[Dict[str, Any]]:
        """
        Search the FTS index with configurable options.

        Args:
            query_text: Search query string (preferred parameter name)
            case_sensitive: Enable case-sensitive matching (default: False)
            edit_distance: Fuzzy matching tolerance (0-3, default: 0)
            snippet_lines: Context lines to include in snippet (0 for list only, default: 5)
            limit: Maximum number of results (default: 10, use 0 for unlimited grep-like output)
            language_filter: Filter by single programming language (deprecated, use languages)
            languages: Filter by multiple programming languages (e.g., ["py", "js"])
            path_filters: Filter by path patterns (e.g., ["*/tests/*", "*/src/*"]) - OR logic
            exclude_paths: Exclude paths matching patterns (e.g., ["*/tests/*", "*.min.js"]) - OR logic, takes precedence
            exclude_languages: Exclude programming languages (e.g., ["javascript", "typescript"]) - OR logic, takes precedence over languages
            path_filter: Filter by single path pattern (deprecated, use path_filters)
            query: Backwards compatibility parameter (deprecated, use query_text)
            use_regex: Interpret query_text as regex pattern (incompatible with edit_distance > 0)

        Returns:
            List of dictionaries with keys:
                - path: File path
                - line: Line number where match occurs
                - column: Column number where match occurs
                - match_text: The matched text
                - snippet: Code snippet with context (empty if snippet_lines=0)
                - language: Programming language
                - score: Relevance score (if available)

        Raises:
            RuntimeError: If index is not initialized
            ValueError: If edit_distance is out of range (0-3) or use_regex combined with edit_distance
        """
        # Handle backwards compatibility
        if query is not None and not query_text:
            query_text = query

        # Handle path filtering: path_filters takes precedence over path_filter
        active_path_filters: Optional[List[str]] = None
        if path_filters is not None:
            active_path_filters = path_filters if path_filters else None
        elif path_filter is not None:
            active_path_filters = [path_filter]

        # Handle language filtering: languages takes precedence over language_filter
        active_language_filter: Optional[List[str]] = None
        if languages is not None:
            active_language_filter = languages if languages else None
        elif language_filter is not None:
            active_language_filter = [language_filter]

        if self._index is None:
            raise RuntimeError("Index not initialized")

        # Validate regex incompatibility with fuzzy matching
        if use_regex and edit_distance > 0:
            raise ValueError(
                "Cannot combine regex matching with fuzzy matching (edit_distance > 0). "
                "Regex provides its own pattern matching capabilities."
            )

        # Validate edit_distance
        if not (0 <= edit_distance <= 3):
            raise ValueError(f"edit_distance must be 0-3, got {edit_distance}")

        try:
            # Import tantivy for query building
            import tantivy
            from tantivy import Query as TantivyQuery

            # Reload index to get latest documents
            self._index.reload()
            searcher = self._index.searcher()

            # Select field based on case sensitivity
            # "content_raw" preserves case, "content" is lowercased during indexing
            search_field = "content_raw" if case_sensitive else "content"

            # Build query based on regex flag
            # IMPORTANT: Tantivy uses DFA-based regex engine (via tantivy-fst crate)
            # which is immune to ReDoS attacks. All regex queries complete in linear
            # time O(n) regardless of pattern complexity. Patterns like (a+)+, (a|a)*b
            # that cause catastrophic backtracking in PCRE/Python are safe here.
            if use_regex:
                # Build regex query using Tantivy's regex_query
                assert self._schema is not None  # For mypy
                try:
                    text_query = TantivyQuery.regex_query(
                        self._schema,
                        search_field,
                        query_text,  # The regex pattern
                    )
                except Exception as e:
                    # Wrap any regex compilation errors with clear message
                    raise ValueError(
                        f"Invalid regex pattern '{query_text}': {str(e)}"
                    ) from e
            else:
                # Build query using existing helper method for non-regex searches
                text_query = self._build_search_query(
                    query_text=query_text,
                    search_field=search_field,
                    edit_distance=edit_distance,
                    tantivy=tantivy,
                    TantivyQuery=TantivyQuery,
                )

            # Add language filter to query if specified AND no exclusions present
            # If exclusions present, we do post-processing for correct precedence
            if active_language_filter and not exclude_languages:
                # Build language facet queries (OR semantics: match any specified language)
                from tantivy import Facet

                assert self._schema is not None  # For mypy
                language_queries = [
                    TantivyQuery.term_query(
                        self._schema, "language_facet", Facet.from_string(f"/{lang}")
                    )
                    for lang in active_language_filter
                ]

                # Combine language queries with OR semantics (any language matches)
                if len(language_queries) == 1:
                    language_query = language_queries[0]
                else:
                    language_subqueries = [
                        (tantivy.Occur.Should, q) for q in language_queries
                    ]
                    language_query = TantivyQuery.boolean_query(language_subqueries)

                # Combine text query AND language filter (both must match)
                tantivy_query = TantivyQuery.boolean_query(
                    [
                        (tantivy.Occur.Must, text_query),
                        (tantivy.Occur.Must, language_query),
                    ]
                )
            else:
                tantivy_query = text_query

            # Handle limit=0 for unlimited results (grep-like output)
            # Tantivy requires limit > 0, so use very large limit and disable snippets
            if limit == 0:
                search_limit = 100000  # Effectively unlimited
                snippet_lines = 0  # Disable snippets for grep-like output
            else:
                # Execute search with increased limit to account for filtering
                # If language exclusions present, we need higher limit for post-processing
                needs_increased_limit = (
                    active_path_filters
                    or exclude_paths
                    or exclude_languages
                    or (languages and exclude_languages)
                )
                search_limit = limit * 3 if needs_increased_limit else limit

            search_results = searcher.search(tantivy_query, search_limit).hits

            # Build allowed and excluded extension sets once before loop
            allowed_extensions = set()
            excluded_extensions = set()

            if languages or exclude_languages:
                from code_indexer.services.language_mapper import LanguageMapper

                mapper = LanguageMapper()

                # Build excluded extensions from excluded languages (processed FIRST)
                if exclude_languages:
                    for lang in exclude_languages:
                        extensions = mapper.get_extensions(lang)
                        if extensions:
                            excluded_extensions.update(extensions)

                # Build allowed extensions from included languages (processed SECOND)
                if languages:
                    for lang in languages:
                        extensions = mapper.get_extensions(lang)
                        if extensions:
                            allowed_extensions.update(extensions)

            # Create PathPatternMatcher once before loop (for path filtering and exclusions)
            path_matcher = None
            exclude_matcher = None
            if active_path_filters or exclude_paths:
                from code_indexer.services.path_pattern_matcher import (
                    PathPatternMatcher,
                )

                path_matcher = PathPatternMatcher()
                exclude_matcher = PathPatternMatcher()  # Use same class for exclusions

            # PERFORMANCE OPTIMIZATION: Compile regex pattern ONCE before loop (not per result)
            # This reduces 100x compilation overhead for searches with many results
            compiled_regex_pattern = None
            if use_regex:
                # Use 'regex' library for enhanced Unicode support
                # Note: Tantivy's DFA-based regex engine is already ReDoS-immune at query execution time (line 489)
                # This Python regex is only for extracting matched text from results, not for query validation
                try:
                    import regex
                except ImportError:
                    import re as regex  # type: ignore

                    logger.debug(
                        "regex library not installed. Using standard 're' module."
                    )

                # Pre-compile pattern with appropriate flags
                try:
                    flags = 0 if case_sensitive else regex.IGNORECASE
                    compiled_regex_pattern = regex.compile(query_text, flags=flags)
                except (regex.error, AttributeError) as e:
                    # Regex compilation failed - raise early before processing results
                    error_msg = f"Invalid regex pattern '{query_text}': {str(e)}"
                    logger.error(error_msg)
                    raise ValueError(error_msg) from e

            # Process results
            docs = []
            for score, address in search_results:
                doc = searcher.doc(address)

                # Extract fields
                path = doc.get_first("path") or ""
                content_raw = doc.get_first("content_raw") or ""
                language = doc.get_first("language")
                line_start = doc.get_first("line_start")

                # Parse language from facet format (/language_name)
                if language:
                    language = str(language).strip("/")

                # CRITICAL FILTER PRECEDENCE ORDER:
                # 1. Language exclusions (FIRST - takes precedence)
                # 2. Language inclusions (SECOND)
                # 3. Path exclusions (THIRD)
                # 4. Path inclusions (FOURTH)

                # 1. Apply language exclusions FIRST (before inclusions)
                # Exclusions take precedence - if language matches any excluded extension, exclude it
                if excluded_extensions and language in excluded_extensions:
                    continue  # Skip this result

                # 2. Apply language inclusions SECOND (after exclusions)
                # Language filtering was already done in query for performance,
                # but we need post-processing for exclude_languages since they're not in query
                if allowed_extensions and language not in allowed_extensions:
                    continue  # Skip this result

                # 3. Apply path exclusions THIRD (before path inclusions)
                # Exclusions take precedence - if path matches any exclusion pattern, exclude it
                if exclude_matcher and exclude_paths:
                    if any(
                        exclude_matcher.matches_pattern(path, pattern)
                        for pattern in exclude_paths
                    ):
                        continue  # Skip this result

                # 4. Apply path inclusions FOURTH (after all exclusions)
                if path_matcher and active_path_filters:
                    # Use PathPatternMatcher for consistency with semantic search
                    # PathPatternMatcher provides cross-platform path normalization
                    # and consistent glob pattern support including ** for recursive matching
                    # Include result if it matches ANY of the path filters (OR semantics)
                    if not any(
                        path_matcher.matches_pattern(path, pattern)
                        for pattern in active_path_filters
                    ):
                        continue

                # Find match position in content
                # CRITICAL: For regex search, use pre-compiled pattern for match extraction
                if use_regex and compiled_regex_pattern:
                    # Extract actual matched text and position using pre-compiled pattern
                    try:
                        # Use pre-compiled pattern to extract matched text from Tantivy result
                        # Note: ReDoS protection is provided by Tantivy's DFA engine, not here
                        match_obj = compiled_regex_pattern.search(content_raw)

                        if match_obj:
                            # Extract actual matched text and position
                            match_text = match_obj.group(0)
                            match_start = match_obj.start()

                            # Validate for zero-length matches
                            if len(match_text) == 0:
                                logger.warning(
                                    f"Regex pattern '{query_text}' produced zero-length match "
                                    f"in {path} at line {line_start}. Consider using a more specific pattern."
                                )
                        else:
                            # No match found (shouldn't happen since Tantivy found it)
                            logger.debug(
                                f"Regex pattern '{query_text}' matched in Tantivy but not in Python regex "
                                f"for file {path}. This may indicate indexing/search inconsistency."
                            )
                            match_text = query_text
                            match_start = -1
                    except AttributeError as e:
                        # Pattern search failed (shouldn't happen with pre-compiled pattern)
                        logger.warning(
                            f"Regex pattern '{query_text}' search failed for {path}: {e}"
                        )
                        match_text = query_text
                        match_start = -1
                else:
                    # Non-regex search: use literal string matching
                    match_text = query_text
                    if case_sensitive:
                        match_start = content_raw.find(query_text)
                    else:
                        match_start = content_raw.lower().find(query_text.lower())

                    if match_start == -1:
                        # Try to find first word from query
                        first_word = query_text.split()[0] if query_text else ""
                        if case_sensitive:
                            match_start = content_raw.find(first_word)
                        else:
                            match_start = content_raw.lower().find(first_word.lower())
                        if match_start != -1:
                            match_text = first_word

                    # If still not found and fuzzy search is enabled, use fuzzy matching
                    if match_start == -1 and edit_distance > 0:
                        fuzzy_start, fuzzy_text = self._find_fuzzy_match(
                            content_raw, query_text, case_sensitive
                        )
                        if fuzzy_start >= 0:
                            match_start = fuzzy_start
                            match_text = fuzzy_text

                # Extract snippet and calculate line/column
                if match_start >= 0:
                    snippet, line, column, snippet_start_line = self._extract_snippet(
                        content_raw, match_start, len(match_text), snippet_lines
                    )
                else:
                    # Fallback: use line_start from document
                    snippet = ""
                    line = int(line_start) if line_start is not None else 1
                    column = 1
                    snippet_start_line = line

                result = {
                    "path": path,
                    "line": line,
                    "column": column,
                    "match_text": match_text,
                    "snippet": snippet if snippet_lines > 0 else "",
                    "snippet_start_line": snippet_start_line,
                    "language": language or "unknown",
                    "score": score,
                }

                docs.append(result)

                # Enforce limit after path filtering (unless limit=0 for unlimited)
                if limit > 0 and len(docs) >= limit:
                    break

            # Return results (slice only if limit > 0)
            return docs if limit == 0 else docs[:limit]

        except ValueError:
            # Re-raise ValueError (includes invalid regex patterns and edit_distance validation)
            # These should not be silently caught
            raise
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _find_fuzzy_match(
        self, content: str, query_text: str, case_sensitive: bool = False
    ) -> tuple[int, str]:
        """
        Find the best fuzzy match location in content using approximate string matching.

        This method uses difflib to find the closest matching substring in the content
        when exact matching fails (e.g., for typos in fuzzy search).

        Args:
            content: Content to search in
            query_text: Text to search for (may have typos)
            case_sensitive: Whether to use case-sensitive matching

        Returns:
            Tuple of (match_start_position, actual_matched_text)
            Returns (-1, "") if no reasonable match found
        """
        from difflib import SequenceMatcher

        # Prepare search content and query
        search_content = content if case_sensitive else content.lower()
        search_query = query_text if case_sensitive else query_text.lower()

        # Split query into words for better matching
        query_words = search_query.split()
        if not query_words:
            return -1, ""

        # Try to find matches for each word and combinations
        best_match_start = -1
        best_match_text = ""
        best_ratio = 0.0

        # Generate sliding windows of content to compare against query
        query_len = len(search_query)
        # Allow some flexibility in match length (±30%)
        min_window = max(1, int(query_len * 0.7))
        max_window = int(query_len * 1.3)

        # Search for best matching substring
        for window_size in range(min_window, max_window + 1):
            for i in range(len(search_content) - window_size + 1):
                window = search_content[i : i + window_size]
                ratio = SequenceMatcher(None, search_query, window).ratio()

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match_start = i
                    best_match_text = content[i : i + window_size]  # Use original case

        # Only return match if similarity is reasonably high (>0.6 threshold)
        if best_ratio >= 0.6 and best_match_start >= 0:
            return best_match_start, best_match_text

        # Fallback: try to find the first word of query
        if query_words:
            first_word = query_words[0]
            # Use fuzzy matching for first word alone
            word_len = len(first_word)
            min_word_window = max(1, int(word_len * 0.7))
            max_word_window = int(word_len * 1.3)

            for window_size in range(min_word_window, max_word_window + 1):
                for i in range(len(search_content) - window_size + 1):
                    window = search_content[i : i + window_size]
                    ratio = SequenceMatcher(None, first_word, window).ratio()

                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match_start = i
                        best_match_text = content[i : i + window_size]

            if best_ratio >= 0.6 and best_match_start >= 0:
                return best_match_start, best_match_text

        return -1, ""

    def _extract_snippet(
        self, content: str, match_start: int, match_len: int, snippet_lines: int
    ) -> tuple[str, int, int, int]:
        """
        Extract code snippet with context lines and calculate line/column position.

        Args:
            content: Full content string
            match_start: Character offset where match starts (NOT byte offset)
            match_len: Length of match in characters
            snippet_lines: Number of context lines before/after match

        Returns:
            Tuple of (snippet_text, line_number, column_number, snippet_start_line)

        CRITICAL: Uses CHARACTER offsets, not byte offsets, for correct Unicode handling.
        Python's match.start() returns character position, so we must use character lengths.
        """
        lines = content.split("\n")

        # Calculate line and column from CHARACTER offset (not bytes)
        # CRITICAL: Use len(line) not len(line.encode("utf-8"))
        # Python regex match.start() returns character positions, not byte positions
        current_pos = 0
        line_number = 1
        column = 1

        for line_idx, line in enumerate(lines):
            line_len = len(line)  # Character length (NOT bytes)
            if current_pos <= match_start < current_pos + line_len:
                line_number = line_idx + 1
                # Calculate column (1-indexed, character position)
                column = match_start - current_pos + 1
                break
            current_pos += line_len + 1  # +1 for newline character

        # If snippet_lines=0, return empty snippet but still return line/column
        if snippet_lines == 0:
            return "", line_number, column, line_number

        # Extract surrounding lines
        line_idx = line_number - 1  # Convert to 0-indexed
        start_line = max(0, line_idx - snippet_lines)
        end_line = min(len(lines), line_idx + snippet_lines + 1)

        snippet_lines_list = lines[start_line:end_line]
        snippet = "\n".join(snippet_lines_list)

        # Return snippet with absolute line number where snippet starts (1-indexed)
        snippet_start_line = start_line + 1

        return snippet, line_number, column, snippet_start_line

    def get_metadata(self) -> Dict[str, Any]:
        """
        Get index metadata.

        Returns:
            Dictionary with index metadata
        """
        if self._metadata_file.exists():
            try:
                with open(self._metadata_file, "r") as f:
                    metadata: Dict[str, Any] = json.load(f)
                    return metadata
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")

        # Return default metadata
        return {
            "fts_enabled": True,
            "fts_index_available": self._index is not None,
            "tantivy_version": "0.25.0",
            "schema_version": "1.0",
            "created_at": datetime.now().isoformat(),
            "index_path": str(self.index_dir),
        }

    def _save_metadata(self) -> None:
        """Save index metadata to disk."""
        metadata = {
            "fts_enabled": True,
            "fts_index_available": True,
            "tantivy_version": "0.25.0",
            "schema_version": "1.0",
            "created_at": datetime.now().isoformat(),
            "index_path": str(self.index_dir),
        }

        try:
            with open(self._metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def update_document(self, file_path: str, doc: Dict[str, Any]) -> None:
        """
        Update a document in the index (atomic operation).

        If the document exists, it will be replaced. If it doesn't exist,
        it will be created. This is an atomic operation that commits immediately.

        Args:
            file_path: Path of the file to update
            doc: Document dictionary with required fields

        Raises:
            RuntimeError: If writer is not initialized
            ValueError: If required fields are missing
        """
        if self._writer is None:
            raise RuntimeError(
                "Index writer not initialized. Call initialize_index() first."
            )

        try:
            # DEBUG: Mark incremental update for manual testing
            total_docs = self.get_document_count()
            logger.info(
                f"⚡ INCREMENTAL FTS UPDATE: Adding/updating 1 document (total index: {total_docs})"
            )

            with self._lock:
                # Delete old version if it exists using query-based deletion (idempotent)
                assert (
                    self._index is not None
                ), "Index must be initialized when writer is initialized"
                delete_query = self._index.parse_query(file_path, ["path"])
                self._writer.delete_documents_by_query(delete_query)

            # Add updated version (has its own lock)
            self.add_document(doc)

            # Commit atomically (5-50ms target)
            with self._lock:
                self._writer.commit()
            logger.debug(f"Updated document: {file_path}")

        except Exception as e:
            logger.error(f"Failed to update document {file_path}: {e}")
            raise

    def delete_document(self, file_path: str) -> None:
        """
        Delete a document from the index (atomic operation).

        This is an atomic operation that commits immediately. If the document
        doesn't exist, this is a no-op (idempotent).

        Args:
            file_path: Path of the file to delete

        Raises:
            RuntimeError: If writer is not initialized
        """
        if self._writer is None:
            raise RuntimeError(
                "Index writer not initialized. Call initialize_index() first."
            )

        try:
            with self._lock:
                # Delete document using query-based deletion (idempotent)
                assert (
                    self._index is not None
                ), "Index must be initialized when writer is initialized"
                delete_query = self._index.parse_query(file_path, ["path"])
                self._writer.delete_documents_by_query(delete_query)

                # Commit atomically (5-50ms target)
                self._writer.commit()
            logger.debug(f"Deleted document: {file_path}")

        except Exception as e:
            logger.error(f"Failed to delete document {file_path}: {e}")
            raise

    def rebuild_from_documents_background(
        self, collection_path: Path, documents: List[Dict[str, Any]]
    ) -> threading.Thread:
        """
        Rebuild Tantivy FTS index in background (non-blocking).

        Uses BackgroundIndexRebuilder for atomic swap pattern matching HNSW/ID
        indexes. This ensures queries continue during rebuild without blocking (AC3).

        Pattern:
            1. Acquire exclusive lock
            2. Cleanup orphaned .tmp directories
            3. Build new FTS index to tantivy_fts.tmp directory
            4. Atomic rename tantivy_fts.tmp → tantivy_fts
            5. Release lock

        Args:
            collection_path: Path to collection directory
            documents: List of document dictionaries with required FTS fields

        Returns:
            threading.Thread: Background rebuild thread (call .join() to wait)

        Note:
            Queries don't need locks - OS-level atomic rename guarantees they
            see either old or new index. This is the same pattern as HNSW/ID.
        """
        from ..storage.background_index_rebuilder import BackgroundIndexRebuilder

        def _build_fts_index_to_temp(temp_dir: Path) -> None:
            """Build Tantivy FTS index to temp directory."""
            # Create temp FTS manager
            temp_fts_manager = TantivyIndexManager(temp_dir)

            # Initialize new index in temp directory
            temp_fts_manager.initialize_index(create_new=True)

            # Add all documents
            for doc in documents:
                temp_fts_manager.add_document(doc)

            # Commit all documents
            temp_fts_manager.commit()

            # Close writer
            temp_fts_manager.close()

            logger.info(f"Built FTS index to temp directory: {temp_dir}")

        # Use BackgroundIndexRebuilder for atomic swap with locking
        rebuilder = BackgroundIndexRebuilder(collection_path)

        # FTS uses directory, not single file
        target_dir = collection_path / "tantivy_fts"
        temp_dir = Path(str(target_dir) + ".tmp")

        def rebuild_thread_fn():
            """Thread function for background rebuild."""
            try:
                with rebuilder.acquire_lock():
                    logger.info(f"Starting FTS background rebuild: {target_dir}")

                    # Cleanup orphaned .tmp directories (AC9)
                    removed_count = rebuilder.cleanup_orphaned_temp_files()
                    if removed_count > 0:
                        logger.info(
                            f"Cleaned up {removed_count} orphaned temp files before FTS rebuild"
                        )

                    # Build to temp directory
                    _build_fts_index_to_temp(temp_dir)

                    # Atomic swap (directory rename)
                    import shutil
                    import os

                    # Remove old target if exists
                    if target_dir.exists():
                        shutil.rmtree(target_dir)

                    # Atomic rename (directory)
                    os.rename(temp_dir, target_dir)

                    logger.info(f"Completed FTS background rebuild: {target_dir}")

            except Exception as e:
                logger.error(f"FTS background rebuild failed: {e}")
                # Cleanup temp directory on error
                if temp_dir.exists():
                    import shutil

                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory after error: {temp_dir}")
                raise

        # Start background thread
        rebuild_thread = threading.Thread(target=rebuild_thread_fn, daemon=False)
        rebuild_thread.start()

        return rebuild_thread

    def set_cached_index(self, index: Any, schema: Any) -> None:
        """
        Set index and schema from external cache.

        Used by server-side caching to inject pre-loaded index
        without re-initializing from disk.

        Args:
            index: tantivy.Index instance from cache
            schema: tantivy.Schema instance from cache

        Note: Writer is NOT set - this is for read-only search operations only.
        """
        self._index = index
        self._schema = schema
        logger.debug(f"Set cached FTS index for {self.index_dir}")

    def get_index_for_caching(self) -> tuple[Any, Any]:
        """
        Get index and schema for external caching.

        Returns:
            Tuple of (tantivy_index, schema) for caching

        Raises:
            RuntimeError: If index is not initialized
        """
        if self._index is None:
            raise RuntimeError("Index not initialized. Call initialize_index() first.")

        return self._index, self._schema

    def close(self) -> None:
        """Close the index and writer."""
        if self._writer is not None:
            try:
                self._writer.commit()
            except Exception as e:
                logger.error(f"Failed to commit on close: {e}")
            self._writer = None

        self._index = None
        logger.info("Closed Tantivy index")
