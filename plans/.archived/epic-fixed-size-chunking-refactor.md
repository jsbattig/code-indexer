# EPIC: Replace AST-Based Semantic Chunking with Fixed-Size Smart Boundary Chunking

## Epic Intent

As a code indexer user, I need a chunking strategy that produces meaningful, searchable code segments instead of over-segmented fragments, so that I can find relevant code through semantic search and receive useful results with proper context.

**Problem Statement**: The current AST-based semantic chunking creates over-segmented chunks where 76.5% are under 300 characters, with 52% being extremely small (under 100 characters). This results in search results containing meaningless fragments like package declarations, import statements, and partial variable declarations rather than complete, contextual code blocks.

**Solution**: Replace the entire AST-based approach with fixed-size chunking (800-1200 characters) with smart boundary detection that respects natural code structure while maintaining computational efficiency and predictable chunk sizes.

## Story Breakdown

### Story 1: Remove AST/Tree-sitter Dependencies and Infrastructure
As a developer, I need to remove all AST and tree-sitter related dependencies from the codebase so that the system no longer relies on complex parsing that causes over-segmentation.

**Acceptance Criteria:**
- **Given** the current codebase uses tree-sitter dependencies
- **When** I remove tree-sitter infrastructure  
- **Then** the following must be completed:
  - Remove `tree-sitter-language-pack==0.9.0` from requirements.txt
  - Remove all imports of `tree_sitter_language_pack` and `get_parser` 
  - Delete or gut the following source files:
    - `src/code_indexer/indexing/base_tree_sitter_parser.py` (complete removal)
    - `src/code_indexer/indexing/semantic_chunker.py` (complete removal)
    - All language-specific parser files (21 files): `*_parser.py` in `src/code_indexer/indexing/`
      - `python_parser.py`, `java_parser.py`, `javascript_parser.py`, `typescript_parser.py`
      - `go_parser.py`, `kotlin_parser.py`, `csharp_parser.py`, `cpp_parser.py`, `c_parser.py`
      - `ruby_parser.py`, `rust_parser.py`, `swift_parser.py`, `lua_parser.py`
      - `groovy_parser.py`, `sql_parser.py`, `html_parser.py`, `css_parser.py`
      - `xml_parser.py`, `yaml_parser.py`, `pascal_parser.py`
  - Remove all references to `SemanticChunk`, `BaseSemanticParser`, `BaseTreeSitterParser`
  - Update `processor.py` to remove semantic chunker instantiation logic
  - Remove `use_semantic_chunking` configuration option from `config.py`
- **And** no tree-sitter related imports remain in the codebase
- **And** the application builds without tree-sitter dependencies

### Story 2: Remove Semantic Chunking Test Infrastructure  
As a developer, I need to remove all tests related to AST-based semantic chunking so that the test suite only contains relevant tests for the new chunking approach.

**Acceptance Criteria:**
- **Given** the current test suite contains 62+ semantic chunking related tests
- **When** I remove semantic chunking tests
- **Then** the following test files must be deleted:
  - All unit parser tests (19 files): `tests/unit/parsers/test_*_semantic_parser.py`
    - `test_java_semantic_parser.py`, `test_javascript_semantic_parser.py`
    - `test_python_semantic_parser.py`, `test_go_semantic_parser.py`
    - `test_kotlin_semantic_parser.py`, `test_typescript_semantic_parser.py`
    - `test_csharp_semantic_parser.py`, `test_cpp_semantic_parser.py`
    - `test_c_semantic_parser.py`, `test_ruby_semantic_parser.py`
    - `test_rust_semantic_parser.py`, `test_swift_semantic_parser.py`
    - `test_lua_semantic_parser.py`, `test_groovy_semantic_parser.py`
    - `test_sql_semantic_parser.py`, `test_html_semantic_parser.py`
    - `test_css_semantic_parser.py`, `test_xml_semantic_parser.py`
    - `test_yaml_semantic_parser.py`, `test_pascal_semantic_parser.py`
  - Comprehensive parser tests (10 files):
    - `test_*_parser_comprehensive.py` for Java, JavaScript, TypeScript, Go, Kotlin
    - AST-based tests: `test_*_ast_*.py` for Rust, C#, Groovy, Swift, SQL
    - Ruby-specific chunking tests: `test_ruby_*_chunking.py`, `test_ruby_*_patterns.py`
  - Semantic chunker unit tests (5 files):
    - `tests/unit/chunking/test_semantic_chunker.py`
    - `tests/unit/chunking/test_chunk_content_integrity.py`
    - `tests/unit/chunking/test_chunking_boundary_bleeding.py`
    - `tests/unit/chunking/test_chunking_line_numbers_comprehensive.py`
    - Infrastructure tests with semantic dependencies
  - Integration tests (1 file):
    - `tests/integration/services/test_semantic_chunking_integration.py`
  - E2E tests (5 files):
    - `tests/e2e/misc/test_semantic_chunking_ast_fallback_e2e.py`
    - `tests/e2e/display/test_semantic_query_display_e2e.py`  
    - All files in `tests/e2e/semantic_search/` directory
- **And** all references to semantic chunking are removed from remaining tests
- **And** the test suite runs without semantic chunking dependencies

### Story 3: Implement Ultra-Simple Fixed-Size Chunker with Fixed Overlap
As a developer, I need to implement the simplest possible fixed-size chunking algorithm with no boundary detection complexity, so that chunks are consistently sized and implementation is trivial.

**Acceptance Criteria:**
- **Given** the need for consistent chunk sizes with maximum simplicity
- **When** I implement the fixed-size chunker algorithm
- **Then** the algorithm must follow this ultra-simple approach:
  1. **Fixed chunk size**: Every chunk is exactly 1000 characters
  2. **Fixed overlap**: 150 characters overlap between adjacent chunks (15%)
  3. **Simple math**: 
     - Chunk 1: characters 0-999 (1000 chars)
     - Chunk 2: characters 850-1849 (1000 chars, starts 150 chars back from end of chunk 1)
     - Chunk 3: characters 1700-2699 (1000 chars, starts 150 chars back from end of chunk 2)
     - Pattern: `next_start = current_start + 850` (1000 - 150 overlap)
  4. **Last chunk**: Handle remainder text (may be smaller than 1000 chars)
  5. **No boundary detection**: Cut at exact character positions, no looking for delimiters or line breaks
  6. **No parsing**: Pure arithmetic - no string analysis, no regex, no complexity
- **And** create single new file: `src/code_indexer/indexing/fixed_size_chunker.py`
- **And** class `FixedSizeChunker` implements this trivial algorithm (should be ~50 lines of code)
- **And** chunk metadata includes: text, chunk_index, total_chunks, size, file_path, file_extension, line_start, line_end
- **And** update `processor.py` to instantiate `FixedSizeChunker` and remove semantic chunker logic
- **And** algorithm produces 100% consistent chunk sizes (all chunks exactly 1000 chars except final chunk)

### Story 4: Update Configuration and Remove Semantic Options
As a user, I need the configuration system to no longer offer semantic chunking options so that there are no confusing or non-functional settings.

**Acceptance Criteria:**
- **Given** the current config has semantic chunking options
- **When** I update the configuration
- **Then** I must:
  - Remove `use_semantic_chunking` field from `IndexingConfig` in `config.py`
  - Remove all references to semantic chunking from configuration documentation
  - Update default configurations in tests to not reference semantic options
  - Ensure `chunk_size` and `chunk_overlap` settings still function for fixed-size chunking
  - Update configuration validation to reject any semantic chunking related options
- **And** existing configuration files continue to work (ignore unknown semantic options)
- **And** the help documentation reflects only fixed-size chunking options

### Story 5: Create Comprehensive Tests for Fixed-Size Chunking
As a developer, I need thorough test coverage for the new fixed-size chunking so that I can verify it produces high-quality chunks using the simple boundary detection algorithm.

**Acceptance Criteria:**
- **Given** the new fixed-size chunking implementation
- **When** I create comprehensive tests
- **Then** I must implement:
  - Unit tests for `FixedSizeChunker` class:
    - Test fixed chunk size (exactly 1000 characters per chunk)
    - Test fixed overlap calculation (exactly 150 characters overlap)
    - Test chunk positioning math (`next_start = current_start + 850`)
    - Test last chunk handling (remainder text < 1000 chars)
    - Test edge cases: empty files, very small files, very large files  
    - Test line number calculation accuracy
    - Test that 100% of chunks (except last) are exactly 1000 characters
  - Integration tests:
    - Test chunking real code files from different languages
    - Test end-to-end processing with new chunker
    - Test chunk metadata completeness and accuracy
    - Verify chunks contain meaningful code blocks (not fragments)
  - Performance tests:
    - Compare fixed-size chunking speed vs old semantic chunking
    - Test memory usage with large files
    - Test chunking consistency (same input = same output)
  - Regression tests:
    - Test files that previously caused over-segmentation
    - Verify search result quality improvement
    - Test the evolution codebase chunking specifically
- **And** all tests pass with the new chunking implementation
- **And** test coverage is at least 95% for the new chunker

### Story 6: Update Documentation and Help System  
As a user, I need updated documentation that accurately describes the fixed-size chunking approach so that I understand how the system works.

**Acceptance Criteria:**
- **Given** the system now uses fixed-size chunking
- **When** I update documentation
- **Then** I must update:
  - `README.md`: Remove semantic chunking descriptions, add fixed-size chunking explanation
  - `CONFIGURATION_REFERENCE.md`: Remove semantic chunking options, document chunk_size/overlap
  - CLI help text: Update `--help` output to describe current chunking behavior
  - Release notes: Document this major breaking change and its benefits
  - Any other documentation mentioning semantic chunking or AST-based parsing
- **And** the documentation accurately reflects the 800-1200 character chunk sizes
- **And** examples show the expected chunking behavior and overlap
- **And** migration guidance for users coming from semantic chunking

### Story 7: Validate Search Quality Improvement
As a user, I need to verify that the new chunking approach produces better search results so that I can find relevant code more effectively.

**Acceptance Criteria:**
- **Given** the new fixed-size chunking is implemented
- **When** I test search quality in the evolution codebase
- **Then** the results must show:
  - Exactly 1000 characters per chunk (not 549 average like before)
  - 0% of chunks under 1000 characters (except final chunk per file)
  - Massive improvement over 76.5% chunks under 300 chars and 52% under 100 chars
  - Search results contain complete method implementations, not fragments
  - Search for "customer management" returns meaningful code blocks, not package declarations
  - Search for "database connection" returns actual connection logic, not import statements
  - Chunks preserve enough context to understand the code's purpose
  - Line number metadata accurately reflects chunk positions
- **And** chunk distribution analysis confirms improvement over previous approach
- **And** manual testing shows better semantic search experience

### Story 8: Performance Optimization and Memory Efficiency
As a developer, I need the new chunking approach to be more efficient than AST-based parsing so that indexing is faster and uses less memory.

**Acceptance Criteria:**
- **Given** the fixed-size chunking implementation
- **When** I optimize for performance
- **Then** the chunking must:
  - Process files at least 2x faster than semantic chunking (no AST overhead)
  - Use significantly less memory (no tree-sitter parsing structures)
  - Handle large files (>1MB) efficiently without memory issues  
  - Support streaming/chunked file reading for very large files
  - Scale linearly with file size, not exponentially
  - Maintain consistent performance across different programming languages
- **And** benchmark tests confirm performance improvements
- **And** memory profiling shows reduced memory usage
- **And** indexing of large codebases completes faster

### Story 9: Clean Codebase Audit and Dead Code Removal
As a maintainer, I need to ensure no remnants of the old AST-based approach remain in the codebase so that the system is clean and maintainable.

**Acceptance Criteria:**
- **Given** the complete replacement of semantic chunking
- **When** I audit the codebase for dead code
- **Then** I must verify:
  - No imports of tree-sitter, BaseSemanticParser, SemanticChunk remain anywhere
  - No references to semantic chunking in comments, docstrings, or variable names
  - No unused configuration options or dead conditional branches
  - No semantic chunking related error handling or fallback logic
  - All parser classes and their tests are completely removed
  - Clean git history with proper commit messages documenting changes
  - Updated `.gitignore` if any tree-sitter cache files were ignored
  - No semantic chunking references in continuous integration scripts
- **And** static code analysis shows no dead imports or unused variables
- **And** grep searches for semantic/AST keywords return only expected results
- **And** the codebase passes all linting and formatting checks

## Files to be DELETED (Complete Removal)

### Source Files (23 files):
- `src/code_indexer/indexing/base_tree_sitter_parser.py`
- `src/code_indexer/indexing/semantic_chunker.py`
- **All language parsers (21 files):**
  - `src/code_indexer/indexing/python_parser.py`
  - `src/code_indexer/indexing/java_parser.py`
  - `src/code_indexer/indexing/javascript_parser.py`
  - `src/code_indexer/indexing/typescript_parser.py`
  - `src/code_indexer/indexing/go_parser.py`
  - `src/code_indexer/indexing/kotlin_parser.py`
  - `src/code_indexer/indexing/csharp_parser.py`
  - `src/code_indexer/indexing/cpp_parser.py`
  - `src/code_indexer/indexing/c_parser.py`
  - `src/code_indexer/indexing/ruby_parser.py`
  - `src/code_indexer/indexing/rust_parser.py`
  - `src/code_indexer/indexing/swift_parser.py`
  - `src/code_indexer/indexing/lua_parser.py`
  - `src/code_indexer/indexing/groovy_parser.py`
  - `src/code_indexer/indexing/sql_parser.py`
  - `src/code_indexer/indexing/html_parser.py`
  - `src/code_indexer/indexing/css_parser.py`
  - `src/code_indexer/indexing/xml_parser.py`
  - `src/code_indexer/indexing/yaml_parser.py`
  - `src/code_indexer/indexing/pascal_parser.py`

### Test Files (62+ files to be deleted):
- **Unit parser tests (19 files):** `tests/unit/parsers/test_*_semantic_parser.py`
- **Comprehensive parser tests (10+ files):** `tests/unit/parsers/test_*_parser_comprehensive.py` and AST-based tests
- **Semantic chunker tests (5 files):** `tests/unit/chunking/test_semantic_*.py` and related chunking tests
- **Integration tests (1 file):** `tests/integration/services/test_semantic_chunking_integration.py`
- **E2E tests (5 files):** Semantic search and chunking E2E tests
- **Infrastructure tests:** Any test files with semantic/AST dependencies

### Dependencies to be REMOVED from requirements.txt:
- `tree-sitter-language-pack==0.9.0`

## Files to be MODIFIED (Major Changes)

### Core System Files:
- `src/code_indexer/indexing/processor.py` - Remove semantic chunker logic, use fixed-size chunker
- `src/code_indexer/indexing/chunker.py` - May need updates or could be replaced entirely  
- `src/code_indexer/config.py` - Remove `use_semantic_chunking` option and related configuration
- `src/code_indexer/cli.py` - Remove any semantic chunking related CLI options or help text

### Documentation Files:
- `README.md` - Update chunking description, remove AST references
- `CONFIGURATION_REFERENCE.md` - Remove semantic options, document fixed-size options
- `RELEASE_NOTES.md` - Add breaking change documentation

### Remaining Test Files:
- All tests that import semantic chunking components need to be updated or removed
- Integration tests that rely on semantic chunking behavior
- Any configuration tests that test semantic chunking options

## Implementation Notes

### No Backwards Compatibility
- This is a complete replacement with no fallback mechanisms
- All semantic chunking logic is removed entirely  
- Configuration files with semantic options will ignore those settings
- Users will need to re-index their codebases after this change

### Algorithm Simplicity  
- Fixed-size chunking with smart boundaries should be straightforward to implement
- No complex AST parsing or tree traversal
- Language-specific boundary detection uses simple regex patterns
- Overlap calculation is basic arithmetic

### Quality Assurance
- Must verify chunk quality improvement in real codebases like evolution
- Performance benchmarks must show improvement over semantic approach
- Search result quality must demonstrate meaningful code blocks vs fragments
- Line number accuracy is critical for search result display

This epic will result in a cleaner, more maintainable, and higher-quality chunking system that produces useful search results instead of meaningless code fragments.