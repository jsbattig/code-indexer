## SEMANTIC SEARCH - MANDATORY FIRST ACTION

**CIDX FIRST**: Always use `cidx query` before grep/find/rg for semantic searches.

**Decision Rule**:
- "What code does", "Do we support", "Where is X implemented" → CIDX
- Exact text (variable names, config values, log messages) → grep/find

**Key Parameters**: `--limit N` (results, default 10) | `--language python` (filter by language) | `--path */tests/*` (filter by path pattern) | `--min-score 0.8` (similarity threshold) | `--accuracy high` (higher precision) | `--quiet` (minimal output)

**Examples**: `cidx query "authentication login" --quiet` | `cidx query "error handling" --language python --limit 20` | `cidx query "database connection" --path */services/* --min-score 0.8`

**Exclusion Filters**: `--exclude-language LANG` (filter out languages) | `--exclude-path PATTERN` (filter out path patterns)

**Common Exclusions**:
- Tests: `--exclude-path "*/tests/*" --exclude-path "*_test.py"`
- Dependencies: `--exclude-path "*/node_modules/*" --exclude-path "*/vendor/*"`
- Build artifacts: `--exclude-path "*/build/*" --exclude-path "*/__pycache__/*"`
- Generated: `--exclude-path "*.min.js" --exclude-path "*_pb2.py"`

**Examples**: `cidx query "production code" --exclude-path "*/tests/*" --exclude-language javascript` | `cidx query "api logic" --path */src/* --exclude-path "*/mocks/*" --exclude-language css`

**Fallback**: Use grep/find only when cidx unavailable or for exact string matches.
