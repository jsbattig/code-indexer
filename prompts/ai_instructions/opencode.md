## SEMANTIC SEARCH - MANDATORY FIRST ACTION

**CIDX FIRST**: Always use `cidx query` before grep/find/rg for semantic searches.

**Decision Rule**:
- "What code does", "Do we support", "Where is X implemented" → CIDX
- Exact text (variable names, config values, log messages) → grep/find

**Key Parameters**: `--limit N` (results, default 10) | `--language python` (filter by language) | `--path */tests/*` (filter by path pattern) | `--min-score 0.8` (similarity threshold) | `--accuracy high` (higher precision) | `--quiet` (minimal output)

**Examples**: `cidx query "authentication login" --quiet` | `cidx query "error handling" --language python --limit 20` | `cidx query "database connection" --path */services/* --min-score 0.8`

**Fallback**: Use grep/find only when cidx unavailable or for exact string matches.
