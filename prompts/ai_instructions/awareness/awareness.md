## SEMANTIC SEARCH - CIDX Code Intelligence

**CIDX FIRST**: Always use `cidx query` for semantic code searches.

**When to use CIDX**:
- Semantic: "What code does", "Where is X implemented" → `cidx query "description" --quiet`
- Exact text: Identifiers, function names → `cidx query "name" --fts --quiet`
- Regex patterns: → `cidx query "pattern" --fts --regex --quiet`

**Key flags**:
- `--limit N` - Results limit (default 10, start with 5-10 to conserve context)
- `--language python` - Filter by language
- `--path-filter */tests/*` - Path pattern matching
- `--exclude-path PATTERN` - Exclude paths
- `--min-score 0.8` - Similarity threshold
- `--accuracy high` - Higher precision
- `--quiet` - Minimal output (ALWAYS use this)

**Context conservation**: Start with low `--limit` values (5-10) on initial queries. High limits consume context window rapidly.

**Full documentation**: Read ~/.claude/skills/cidx/SKILL.md for comprehensive CIDX instructions including:
- Full-text search (FTS) modes
- Regex search capabilities
- Temporal search (Git history)
- SCIP call graph and dependency analysis
- All query flags and options

**Examples**:
```bash
cidx query "authentication" --language python --limit 5 --quiet
cidx query "authenticate_user" --fts --case-sensitive --quiet
cidx query "def.*auth" --fts --regex --language python --quiet
```
