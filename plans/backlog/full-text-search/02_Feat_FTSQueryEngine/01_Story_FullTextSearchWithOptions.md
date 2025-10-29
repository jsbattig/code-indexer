# Story: Full-Text Search with Configurable Options

## Summary

As a developer searching for specific code patterns, I want to perform exact text searches with fuzzy matching, case sensitivity control, and adjustable context, so that I can find code efficiently with the right detail level and typo tolerance.

## Acceptance Criteria

1. **Default Text Search:**
   - `cidx query` performs semantic search (default behavior preserved)
   - `cidx query --fts` performs full-text search using Tantivy index
   - Clear differentiation between search modes

2. **Case Sensitivity Control:**
   - `--case-sensitive` flag enables exact case matching
   - `--case-insensitive` flag forces case-insensitive (default)
   - Flags properly integrated via Click decorators

3. **Fuzzy Matching Support:**
   - `--fuzzy` flag enables fuzzy matching with default edit distance (1)
   - `--edit-distance N` sets specific Levenshtein distance tolerance
   - Default is exact matching (edit distance 0)
   - Reasonable limits on edit distance (max 3)

4. **Snippet Configuration:**
   - `--snippet-lines N` controls context lines shown
   - N=0 produces list-only output (no code snippets)
   - Default is 5 lines of context
   - Support for large contexts (up to 50 lines)

5. **Position Information:**
   - Exact line and column positions displayed
   - Positions accurate even with multi-byte characters
   - Format: `path/to/file.py:42:15` (line:column)

6. **Result Formatting:**
   - Output format similar to semantic search results
   - Clear indication this is FTS (not semantic) results
   - Proper syntax highlighting in snippets

7. **Performance Requirements:**
   - Query execution <5ms for typical searches
   - Non-blocking operation
   - Efficient memory usage during search

8. **Error Handling:**
   - Graceful error if FTS index not built
   - Suggest running `cidx index --fts` if missing
   - Clear messages for invalid query syntax

## Technical Implementation Details

### CLI Command Integration
```python
@click.command()
@click.argument('query')
@click.option('--fts', is_flag=True, help='Use full-text search instead of semantic')
@click.option('--case-sensitive', is_flag=True, help='Enable case-sensitive matching')
@click.option('--case-insensitive', is_flag=True, help='Force case-insensitive matching')
@click.option('--fuzzy', is_flag=True, help='Enable fuzzy matching (edit distance 1)')
@click.option('--edit-distance', type=int, default=0, help='Set fuzzy match tolerance (0-3)')
@click.option('--snippet-lines', type=int, default=5, help='Context lines to show (0 for list only)')
@click.option('--limit', type=int, default=10, help='Maximum results to return')
@click.option('--language', help='Filter by programming language')
@click.option('--path-filter', help='Filter by path pattern')
def query(
    query: str,
    fts: bool,
    case_sensitive: bool,
    case_insensitive: bool,
    fuzzy: bool,
    edit_distance: int,
    snippet_lines: int,
    limit: int,
    language: Optional[str],
    path_filter: Optional[str]
):
    """Execute semantic or full-text search"""
    if fts:
        if not fts_index_exists():
            click.echo("FTS index not found. Run 'cidx index --fts' first.")
            return

        # Handle conflicting flags
        if case_sensitive and case_insensitive:
            click.echo("Cannot use both --case-sensitive and --case-insensitive")
            return

        # Fuzzy flag shorthand
        if fuzzy and edit_distance == 0:
            edit_distance = 1

        results = execute_fts_search(
            query=query,
            case_sensitive=case_sensitive,
            edit_distance=edit_distance,
            snippet_lines=snippet_lines,
            limit=limit,
            language=language,
            path_filter=path_filter
        )
        display_fts_results(results)
    else:
        # Existing semantic search
        execute_semantic_search(query, limit, language, path_filter)
```

### Query Building Logic
```python
def build_tantivy_query(
    query_text: str,
    case_sensitive: bool,
    edit_distance: int
) -> Query:
    """Build appropriate Tantivy query based on options"""
    # Select field based on case sensitivity
    field = "content_raw" if case_sensitive else "content"

    # Handle fuzzy matching
    if edit_distance > 0:
        return FuzzyTermQuery(
            term=Term.from_field_text(field, query_text),
            distance=edit_distance,
            transpositions=True
        )
    else:
        # Exact term matching
        return TermQuery(Term.from_field_text(field, query_text))
```

### Snippet Extraction Logic
```python
def extract_snippet(
    content: str,
    match_start: int,
    match_end: int,
    snippet_lines: int
) -> Tuple[str, int, int]:
    """Extract snippet with line/column positions"""
    if snippet_lines == 0:
        return "", 0, 0

    lines = content.split('\n')

    # Calculate line and column
    current_pos = 0
    for line_num, line in enumerate(lines):
        if current_pos <= match_start < current_pos + len(line):
            line_number = line_num + 1
            column = match_start - current_pos + 1
            break
        current_pos += len(line) + 1  # +1 for newline

    # Extract surrounding lines
    start_line = max(0, line_num - snippet_lines)
    end_line = min(len(lines), line_num + snippet_lines + 1)

    snippet_lines = lines[start_line:end_line]

    # Highlight match in snippet
    highlight_line = line_num - start_line
    if 0 <= highlight_line < len(snippet_lines):
        # Add highlighting markers
        line = snippet_lines[highlight_line]
        col_start = column - 1
        col_end = col_start + (match_end - match_start)
        snippet_lines[highlight_line] = (
            line[:col_start] + ">>>" +
            line[col_start:col_end] + "<<<" +
            line[col_end:]
        )

    return '\n'.join(snippet_lines), line_number, column
```

### Result Display
```python
def display_fts_results(results: List[FTSResult]):
    """Display FTS results with proper formatting"""
    console = Console()

    console.print("[bold]Full-Text Search Results[/bold]\n")

    if not results:
        console.print("[yellow]No matches found[/yellow]")
        return

    for i, result in enumerate(results, 1):
        # File path with line:column
        console.print(
            f"[cyan]{i}.[/cyan] [green]{result.path}[/green]:"
            f"[yellow]{result.line}:{result.column}[/yellow]"
        )

        # Language if available
        if result.language:
            console.print(f"   Language: [blue]{result.language}[/blue]")

        # Match preview
        console.print(f"   Match: [red]{result.match_text}[/red]")

        # Snippet if requested
        if result.snippet:
            console.print("   Context:")
            # Syntax highlight based on language
            syntax = Syntax(
                result.snippet,
                result.language or "text",
                theme="monokai",
                line_numbers=True,
                start_line=result.snippet_start_line
            )
            console.print(syntax)
        console.print()
```

## Test Scenarios

1. **Basic FTS Test:**
   - Search for function name with `--fts`
   - Verify correct file and position returned
   - Check snippet displays properly

2. **Case Sensitivity Test:**
   - Search for "Config" with `--case-sensitive`
   - Verify only exact case matches returned
   - Search again with `--case-insensitive`
   - Verify both "Config" and "config" matched

3. **Fuzzy Matching Test:**
   - Search for misspelled word with `--fuzzy`
   - Verify correct matches found
   - Test with `--edit-distance 2`
   - Verify broader matches

4. **Snippet Configuration Test:**
   - Search with `--snippet-lines 0`
   - Verify list-only output
   - Search with `--snippet-lines 10`
   - Verify extended context shown

5. **Performance Test:**
   - Execute 100 searches in succession
   - Verify all complete in <5ms
   - Check memory usage stable

6. **Error Handling Test:**
   - Run `--fts` without index
   - Verify helpful error message
   - Use invalid edit distance
   - Verify validation error

## Dependencies

- Tantivy Python bindings
- Existing CLI framework (Click)
- Rich console for formatting
- Syntax highlighting library

## Effort Estimate

- **Development:** 3-4 days
- **Testing:** 2 days
- **Documentation:** 1 day
- **Total:** ~6 days

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Query syntax complexity | Medium | Provide query builder helpers |
| Performance degradation with fuzzy | High | Limit edit distance, use prefix optimization |
| Memory usage with large snippets | Medium | Cap maximum snippet size |
| Unicode handling issues | Medium | Comprehensive UTF-8 testing |

## Conversation References

- **Default Behavior:** "cidx query performs semantic search (default)"
- **FTS Flag:** "cidx query --fts performs full-text search"
- **Case Options:** "--case-sensitive/--case-insensitive flags"
- **Fuzzy Matching:** "--fuzzy or --edit-distance N for typo tolerance"
- **Snippet Control:** "--snippet-lines N for context (0=list only, default 5)"
- **Position Info:** "exact line/column positions shown"
- **Performance:** "non-blocking queries"