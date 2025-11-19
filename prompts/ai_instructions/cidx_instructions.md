## SEMANTIC SEARCH - MANDATORY FIRST ACTION

**CIDX FIRST**: Always use `cidx query` before grep/find/rg for semantic searches.

**Decision Rule**:
- "What code does", "Where is X implemented" → CIDX semantic (default)
- Exact text (identifiers, function names) → `--fts`
- Pattern matching (regex) → `--fts --regex` (10-50x faster than grep)
- CIDX unavailable → grep/find (fallback only)

**Key Flags**: `--limit N` (default 10, start with 5-10 to conserve context) | `--language python` | `--path-filter */tests/*` | `--exclude-path PATTERN` | `--exclude-language LANG` | `--min-score 0.8` | `--accuracy high` | `--quiet`

**Context Conservation**: Start with low `--limit` values (5-10) on initial queries. High limits consume context window rapidly when results contain large code files.

**Example**: `cidx query "authentication" --language python --exclude-path "*/tests/*" --limit 5 --quiet`

---

## FULL-TEXT SEARCH (FTS)

**Use For**: Exact names, identifiers, TODO comments, typo debugging.

**Flags**: `--fts` | `--case-sensitive` | `--fuzzy` | `--edit-distance N` | `--snippet-lines N`

**Example**: `cidx query "authenticate_user" --fts --case-sensitive --quiet`

**Hybrid**: `--fts --semantic` runs both in parallel.

---

## REGEX MODE (Grep Replacement)

**Flags**: `--fts --regex` | Incompatible with `--semantic` and `--fuzzy`

**Token-Based**: Matches individual tokens only.
- ✅ Works: `def`, `login.*`, `test_.*`
- ❌ Doesn't work: `def\s+\w+` (whitespace removed)

**Example**: `cidx query "def.*auth" --fts --regex --language python --quiet`

**Fallback**: Use grep only when CIDX unavailable.

---

## TEMPORAL SEARCH (Git History)

**Use For**: Code archaeology, commit message search, bug history, feature evolution.

**Indexing**: `cidx index --index-commits` (required first)

**Flags**: `--time-range-all` | `--time-range YYYY-MM-DD..YYYY-MM-DD` | `--chunk-type commit_message` | `--chunk-type commit_diff` | `--author EMAIL`

**Examples**:
- When added: `cidx query "JWT auth" --time-range-all --quiet`
- Bug history: `cidx query "database bug" --time-range-all --chunk-type commit_message --quiet`
- Author work: `cidx query "refactor" --time-range-all --author "dev@company.com" --quiet`

**Indexing Options**: `--all-branches` | `--max-commits N` | `--since-date YYYY-MM-DD`
