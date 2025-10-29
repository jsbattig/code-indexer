# Story: Hybrid Search Execution (Text + Semantic)

## Summary

As a developer exploring unfamiliar code, I want to run both text-matching and semantic searches simultaneously, so that I can find code using multiple strategies.

## Acceptance Criteria

1. **Hybrid Search Activation:**
   - `cidx query "term" --fts --semantic` executes both search types
   - Both searches run in parallel for efficiency
   - Results returned as single response

2. **Result Presentation:**
   - FTS results displayed first
   - Clear header separator between result types
   - Semantic results displayed second
   - NO score merging or interleaving (Approach A from conversation)

3. **Filter Propagation:**
   - Both searches respect `--limit` flag (each gets limit)
   - Both searches respect `--language` filter
   - Both searches respect `--path-filter` patterns
   - Filters apply independently to each search

4. **Graceful Degradation:**
   - If FTS index missing, fall back to semantic-only
   - Display warning about missing FTS index
   - Continue with available search type
   - Never fail completely if one index available

5. **Performance Requirements:**
   - Parallel execution (not sequential)
   - Combined latency comparable to slowest search
   - No significant overhead from coordination
   - Memory usage within acceptable bounds

6. **Configuration Options:**
   - All FTS options available (case, fuzzy, snippets)
   - All semantic options available (min-score, accuracy)
   - Options apply to respective search types only
   - Clear documentation of option scope

## Technical Implementation Details

### Parallel Execution Strategy
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class HybridSearchExecutor:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)

    async def execute_hybrid_search(
        self,
        query: str,
        fts_params: dict,
        semantic_params: dict
    ) -> HybridSearchResults:
        """Execute FTS and semantic searches in parallel"""

        # Create async tasks for parallel execution
        fts_task = asyncio.create_task(
            self._run_fts_search(query, **fts_params)
        )
        semantic_task = asyncio.create_task(
            self._run_semantic_search(query, **semantic_params)
        )

        # Wait for both to complete
        fts_results, semantic_results = await asyncio.gather(
            fts_task,
            semantic_task,
            return_exceptions=True
        )

        # Handle potential failures gracefully
        if isinstance(fts_results, Exception):
            logger.warning(f"FTS search failed: {fts_results}")
            fts_results = []

        if isinstance(semantic_results, Exception):
            logger.warning(f"Semantic search failed: {semantic_results}")
            semantic_results = []

        return HybridSearchResults(
            fts_results=fts_results,
            semantic_results=semantic_results
        )
```

### CLI Integration for Hybrid Mode
```python
@click.command()
@click.option('--fts', is_flag=True, help='Enable full-text search')
@click.option('--semantic', is_flag=True, help='Enable semantic search (default without --fts)')
# ... other options ...
def query(query_text: str, fts: bool, semantic: bool, **kwargs):
    """Execute search based on mode selection"""

    # Determine search mode
    if fts and semantic:
        # Explicit hybrid mode
        search_mode = "hybrid"
    elif fts:
        # FTS only
        search_mode = "fts"
    else:
        # Default semantic (including when --semantic explicitly set)
        search_mode = "semantic"

    # Check index availability
    has_fts = fts_index_exists()
    has_semantic = semantic_index_exists()

    # Adjust mode based on availability
    if search_mode == "hybrid" and not has_fts:
        click.echo("Warning: FTS index not available, falling back to semantic-only")
        search_mode = "semantic"
    elif search_mode == "fts" and not has_fts:
        click.echo("Error: FTS index not found. Run 'cidx index --fts' first.")
        return
    elif search_mode == "semantic" and not has_semantic:
        click.echo("Error: Semantic index not found. Run 'cidx index' first.")
        return

    # Execute appropriate search
    if search_mode == "hybrid":
        results = execute_hybrid_search(query_text, **kwargs)
        display_hybrid_results(results)
    elif search_mode == "fts":
        results = execute_fts_search(query_text, **kwargs)
        display_fts_results(results)
    else:
        results = execute_semantic_search(query_text, **kwargs)
        display_semantic_results(results)
```

### Result Presentation (Approach A)
```python
def display_hybrid_results(results: HybridSearchResults):
    """Display hybrid results with clear separation"""
    console = Console()

    # FTS Results First
    console.print("[bold cyan]━━━ FULL-TEXT SEARCH RESULTS ━━━[/bold cyan]\n")

    if results.fts_results:
        for i, result in enumerate(results.fts_results, 1):
            console.print(
                f"[cyan]{i}.[/cyan] [green]{result.path}[/green]:"
                f"[yellow]{result.line}:{result.column}[/yellow]"
            )
            if result.snippet:
                console.print(f"   {result.snippet}")
            console.print()
    else:
        console.print("[yellow]No text matches found[/yellow]\n")

    # Clear separator
    console.print("[bold]" + "─" * 50 + "[/bold]\n")

    # Semantic Results Second
    console.print("[bold magenta]━━━ SEMANTIC SEARCH RESULTS ━━━[/bold magenta]\n")

    if results.semantic_results:
        for i, result in enumerate(results.semantic_results, 1):
            console.print(
                f"[magenta]{i}.[/magenta] [green]{result.path}[/green] "
                f"[dim](score: {result.score:.3f})[/dim]"
            )
            if result.snippet:
                console.print(f"   {result.snippet}")
            console.print()
    else:
        console.print("[yellow]No semantic matches found[/yellow]\n")
```

### Parameter Routing
```python
def route_search_parameters(kwargs: dict) -> Tuple[dict, dict]:
    """Route parameters to appropriate search type"""

    # Common parameters (apply to both)
    common_params = {
        'limit': kwargs.get('limit', 10),
        'language': kwargs.get('language'),
        'path_filter': kwargs.get('path_filter'),
    }

    # FTS-specific parameters
    fts_params = {
        **common_params,
        'case_sensitive': kwargs.get('case_sensitive', False),
        'edit_distance': kwargs.get('edit_distance', 0),
        'snippet_lines': kwargs.get('snippet_lines', 5),
    }

    # Semantic-specific parameters
    semantic_params = {
        **common_params,
        'min_score': kwargs.get('min_score', 0.0),
        'accuracy': kwargs.get('accuracy', 'balanced'),
    }

    return fts_params, semantic_params
```

## Test Scenarios

1. **Basic Hybrid Test:**
   - Run `cidx query "function" --fts --semantic`
   - Verify both result sections present
   - Verify clear separation between sections
   - Check both respect limit parameter

2. **Missing FTS Index Test:**
   - Remove FTS index
   - Run hybrid search
   - Verify warning displayed
   - Verify semantic results still shown

3. **Filter Propagation Test:**
   - Run hybrid with `--language python`
   - Verify both sections only show Python files
   - Run with `--path-filter "*/tests/*"`
   - Verify both sections respect filter

4. **Performance Comparison Test:**
   - Time hybrid search execution
   - Time individual searches
   - Verify hybrid ≈ max(fts_time, semantic_time)
   - Confirm parallel execution

5. **Option Routing Test:**
   - Use `--case-sensitive` in hybrid mode
   - Verify only affects FTS results
   - Use `--min-score 0.8` in hybrid mode
   - Verify only affects semantic results

6. **Empty Results Test:**
   - Search for non-existent term
   - Verify both sections show "No matches"
   - Verify proper formatting maintained

## Dependencies

- Existing FTS query engine
- Existing semantic search engine
- AsyncIO for parallel execution
- ThreadPoolExecutor for parallelization
- Rich console for formatted output

## Effort Estimate

- **Development:** 2 days
- **Testing:** 1.5 days
- **Documentation:** 0.5 days
- **Total:** ~4 days

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Result confusion | Medium | Clear visual separation, headers |
| Performance overhead | Low | Parallel execution, no blocking |
| Memory pressure | Medium | Stream results, don't buffer all |
| Complex parameter routing | Low | Clear parameter documentation |

## Conversation References

- **Hybrid Activation:** "cidx query 'term' --fts --semantic executes both in parallel"
- **Result Order:** "FTS results displayed first"
- **Separation:** "clear header separator"
- **No Merging:** "Approach A - Separate Presentation (FTS first, header separator, then semantic - NO score merging)"
- **Graceful Degradation:** "graceful handling if FTS missing (semantic only + warning)"
- **Performance:** "comparable performance to individual searches"