# Story: CLI Command Updates

## Summary

As a CIDX CLI user, I want clear documentation and help text that reflects all FTS capabilities, so that I can effectively use the new search options.

## Acceptance Criteria

1. **Help Text Updates:**
   - `cidx query --help` shows all FTS-related options
   - Clear indication which options are FTS-specific
   - Examples demonstrate various search modes
   - Default behaviors clearly documented

2. **Teach-AI Template Updates:**
   - CIDX syntax in teach-ai templates includes FTS options
   - Examples show semantic, FTS, and hybrid searches
   - Parameter explanations match actual behavior
   - Common use cases demonstrated

3. **Command Examples:**
   - Basic FTS search example
   - Case-sensitive search example
   - Fuzzy matching example
   - Hybrid search example
   - Filter combination examples

4. **Documentation Consistency:**
   - README.md reflects new capabilities
   - API documentation matches CLI documentation
   - Version changelog includes FTS features
   - Installation guides mention Tantivy dependency

5. **Error Message Clarity:**
   - Missing index errors suggest correct commands
   - Invalid parameter combinations explained
   - Helpful hints for common mistakes
   - Links to documentation where appropriate

## Technical Implementation Details

### CLI Help Text Enhancement
```python
# cli.py updates
@click.command()
@click.argument('query', required=True)
@click.option(
    '--fts',
    is_flag=True,
    help='Use full-text search for exact text matching instead of semantic search'
)
@click.option(
    '--semantic',
    is_flag=True,
    help='Use semantic search (default) or combine with --fts for hybrid mode'
)
@click.option(
    '--case-sensitive',
    is_flag=True,
    help='[FTS only] Enable case-sensitive matching (default: case-insensitive)'
)
@click.option(
    '--case-insensitive',
    is_flag=True,
    help='[FTS only] Force case-insensitive matching (default behavior)'
)
@click.option(
    '--fuzzy',
    is_flag=True,
    help='[FTS only] Enable fuzzy matching with edit distance 1'
)
@click.option(
    '--edit-distance',
    type=click.IntRange(0, 3),
    default=0,
    help='[FTS only] Set fuzzy match tolerance in characters (0=exact, max=3)'
)
@click.option(
    '--snippet-lines',
    type=click.IntRange(0, 50),
    default=5,
    help='[FTS only] Context lines around match (0=list only, default=5)'
)
@click.option(
    '--limit',
    type=int,
    default=10,
    help='Maximum results to return (applies to each search type in hybrid mode)'
)
@click.option(
    '--language',
    type=str,
    help='Filter results by programming language (e.g., python, javascript)'
)
@click.option(
    '--path-filter',
    type=str,
    help='Filter results by path pattern (e.g., "*/tests/*", "*.py")'
)
@click.option(
    '--min-score',
    type=float,
    default=0.0,
    help='[Semantic only] Minimum similarity score (0.0-1.0)'
)
@click.option(
    '--accuracy',
    type=click.Choice(['low', 'balanced', 'high']),
    default='balanced',
    help='[Semantic only] Search accuracy vs speed trade-off'
)
def query(query, **options):
    """
    Search your codebase using semantic understanding or full-text matching.

    SEARCH MODES:

      Semantic (default): Finds conceptually related code using AI embeddings
      Full-text (--fts): Exact text matching with optional fuzzy tolerance
      Hybrid (--fts --semantic): Runs both searches in parallel

    EXAMPLES:

      Semantic search (default):
        cidx query "user authentication"
        cidx query "database connection" --language python

      Full-text search:
        cidx query "authenticate_user" --fts
        cidx query "ParseError" --fts --case-sensitive
        cidx query "conection" --fts --fuzzy  # Typo-tolerant

      Fuzzy matching with custom distance:
        cidx query "authnticate" --fts --edit-distance 2

      Minimal output (list files only):
        cidx query "TODO" --fts --snippet-lines 0

      Extended context:
        cidx query "error" --fts --snippet-lines 10

      Hybrid search (both modes):
        cidx query "login" --fts --semantic
        cidx query "parse" --fts --semantic --limit 5

      With filters:
        cidx query "test" --fts --language python --path-filter "*/tests/*"

    NOTE: FTS requires building an FTS index first with 'cidx index --fts'
    """
    # Implementation
    pass
```

### Teach-AI Template Updates
```markdown
# cidx_instructions.md updates

## CIDX Query Syntax Updates

### Search Modes

**Semantic Search (Default)**
```bash
cidx query "concept or functionality"
cidx query "authentication mechanisms" --limit 20
cidx query "error handling" --language python
```

**Full-Text Search (Exact Matching)**
```bash
cidx query "exact_function_name" --fts
cidx query "ConfigClass" --fts --case-sensitive
cidx query "parse_json" --fts --path-filter "*/utils/*"
```

**Fuzzy Text Search (Typo Tolerant)**
```bash
cidx query "misspeled" --fts --fuzzy  # Edit distance 1
cidx query "athentcate" --fts --edit-distance 2  # More tolerance
```

**Hybrid Search (Both Modes)**
```bash
cidx query "login" --fts --semantic  # Runs both in parallel
```

### FTS-Specific Options

- `--fts`: Enable full-text search mode
- `--case-sensitive`: Exact case matching (FTS only)
- `--fuzzy`: Allow 1-character differences
- `--edit-distance N`: Set fuzzy tolerance (0-3)
- `--snippet-lines N`: Context lines (0=list, default=5)

### Common Options (Both Modes)

- `--limit N`: Maximum results per search type
- `--language LANG`: Filter by programming language
- `--path-filter PATTERN`: Filter by path pattern
- `--quiet`: Minimal output format

### Examples by Use Case

**Finding Specific Functions/Classes:**
```bash
cidx query "UserAuthentication" --fts --case-sensitive
```

**Debugging Typos in Code:**
```bash
cidx query "respnse" --fts --fuzzy  # Find "response" typos
```

**Exploring Concepts:**
```bash
cidx query "caching strategies" --limit 20  # Semantic search
```

**Comprehensive Search:**
```bash
cidx query "parse" --fts --semantic  # Find exact matches AND related code
```
```

### README.md Updates
```markdown
# README.md additions

## Full-Text Search (v7.1.0+)

CIDX now supports fast, index-backed full-text search alongside semantic search.

### Building FTS Index

```bash
# Build both semantic and FTS indexes
cidx index --fts

# Enable FTS in watch mode
cidx watch --fts
```

### Using FTS

```bash
# Exact text search
cidx query "function_name" --fts

# Case-sensitive search
cidx query "ClassName" --fts --case-sensitive

# Fuzzy matching for typos
cidx query "authenticte" --fts --fuzzy

# Hybrid search (both modes)
cidx query "parse" --fts --semantic
```

### FTS Features

- **Sub-5ms query latency** on large codebases
- **Fuzzy matching** with configurable edit distance
- **Case sensitivity control** for precise matching
- **Adjustable context snippets** (0-50 lines)
- **Real-time index updates** in watch mode
- **Language and path filtering** support

### Installation Note

FTS requires the Tantivy Python bindings:

```bash
pip install tantivy==0.25.0
```
```

### Error Message Improvements
```python
# Enhanced error messages
class ErrorMessages:
    FTS_INDEX_MISSING = """
FTS index not found. To use full-text search, first build the index:

  cidx index --fts

This will create both semantic and FTS indexes. For more info:
  cidx index --help
"""

    INVALID_MODE_COMBINATION = """
Invalid option combination. Examples of valid usage:

  cidx query "term"                    # Semantic search (default)
  cidx query "term" --fts             # Full-text search only
  cidx query "term" --fts --semantic  # Hybrid search (both)

Note: --case-sensitive and --edit-distance only work with --fts
"""

    FUZZY_WITHOUT_FTS = """
Fuzzy matching options require --fts flag:

  cidx query "term" --fts --fuzzy
  cidx query "term" --fts --edit-distance 2

These options don't apply to semantic search.
"""
```

### Version and Changelog Updates
```markdown
# CHANGELOG.md

## [7.1.0] - 2024-XX-XX

### Added
- Full-text search support with Tantivy backend
- Hybrid search mode (semantic + full-text)
- Fuzzy matching with configurable edit distance
- Case-sensitive search option for FTS
- Configurable context snippets (0-50 lines)
- Real-time FTS index updates in watch mode
- Server API support for all search modes

### Changed
- Updated CLI help text with FTS examples
- Enhanced teach-ai templates with search modes
- Improved error messages for missing indexes

### Technical Details
- Tantivy v0.25.0 for FTS indexing
- Parallel processing for hybrid searches
- Sub-5ms query latency for text searches
- Storage: .code-indexer/tantivy_index/
```

## Test Scenarios

1. **Help Text Test:**
   - Run `cidx query --help`
   - Verify all FTS options shown
   - Verify examples present
   - Check formatting consistency

2. **Example Execution Test:**
   - Execute each example from help text
   - Verify they work as documented
   - Check output matches description

3. **Error Message Test:**
   - Trigger each error condition
   - Verify helpful messages shown
   - Check suggested commands work

4. **Documentation Consistency Test:**
   - Compare CLI help with README
   - Verify teach-ai templates match
   - Check API docs alignment

5. **Version Info Test:**
   - Run `cidx --version`
   - Verify version includes FTS
   - Check changelog entry present

## Dependencies

- Click framework for CLI
- Existing help text system
- Documentation build process

## Effort Estimate

- **Development:** 1 day
- **Testing:** 0.5 days
- **Documentation review:** 0.5 days
- **Total:** ~2 days

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Documentation drift | Medium | Automated testing of examples |
| User confusion | Medium | Clear separation of FTS vs semantic |
| Breaking changes | Low | Preserve all existing behavior |

## Conversation References

- **CLI Updates:** "CLI Command Updates (Low) - Update teach-ai syntax, add text search flags, documentation"
- **Documentation:** "Clear documentation of option scope"
- **Help Text:** "cidx query --help shows all FTS-related options"
- **Examples:** "Examples demonstrate various search modes"